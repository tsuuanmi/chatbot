"""EmbeddingGemma semantic classifier for strict domain routing."""

import asyncio
import math
from dataclasses import dataclass

from loguru import logger

from src.base.components.embeddings.base import BaseEmbedding
from src.common.exceptions import DomainClassifierError
from src.domain.models import DomainDecision, DomainLabel, DomainReason, RiskLevel

_EXEMPLARS: dict[DomainLabel, tuple[str, ...]] = {
    DomainLabel.IN_DOMAIN: (
        "Giải thích STR trong giám định ADN",
        "Phân tích mtDNA để nhận dạng hài cốt",
        "Kiểm soát nhiễm trong xét nghiệm ADN",
        "Đánh giá hỗn hợp DNA, allele và hiện tượng stutter",
        "Tính likelihood ratio trong quan hệ huyết thống",
        "Quy trình PCR và điện di mao quản trong xét nghiệm ADN",
        "Phân tích FST quần thể trong giám định pháp y",
        "AI hỗ trợ phân tích STR như thế nào",
        "Phần mềm phân tích điện di STR",
        "Bảo vệ dữ liệu di truyền pháp y",
        "Cấu trúc phân tử DNA, RNA, gene và nhiễm sắc thể",
        "Giải thích haplogroup và dòng dõi di truyền",
        "Giải thích PCR, ATP, enzyme và sinh học phân tử liên quan ADN",
        "Xin chào trợ lý giám định ADN",
        "Kiểm soát chất lượng phòng xét nghiệm di truyền pháp y",
        "Vai trò của Y-STR trong giám định huyết thống dòng cha",
        "X-STR và ứng dụng trong giám định ADN",
        "Trình tự SNP và giải trình tự ADN trong giám định pháp y",
        "Quy trình trích xuất và định lượng DNA từ mẫu sinh học",
        "Suy giảm DNA và ức chế PCR ảnh hưởng kết quả như thế nào",
        "Xét nghiệm ADN cha con xác định huyết thống như thế nào",
        "Giám định ADN cho người mất tích và nhận dạng hài cốt",
        "Ý nghĩa chỉ số PI và CPI trong giám định huyết thống",
        "Xét nghiệm ADN huyết thống cần loại mẫu nào và mất bao lâu",
    ),
    DomainLabel.OUT_OF_DOMAIN: (
        "Cách nấu phở và món ăn",
        "Kết quả và phân tích trận bóng đá",
        "Phần mềm chỉnh sửa ảnh nào tốt",
        "Dùng AI để viết email và nấu ăn",
        "Phân tích dữ liệu bán hàng",
        "Du lịch và khách sạn",
        "Tư vấn đầu tư chứng khoán",
        "Chẩn đoán và điều trị bệnh",
        "Luật giao thông đường bộ",
        "Mô tả ảnh món ăn",
        "Công nghệ AI và khoa học máy tính nói chung",
        "Giải trí, âm nhạc và phim ảnh",
        "Cách học tiếng Anh hiệu quả",
        "Làm sao để giảm cân và tập gym",
        "Tỷ giá và giá vàng hôm nay",
    ),
    DomainLabel.CLARIFY: (
        "Phân tích kết quả này",
        "Mẫu này có phù hợp không",
        "Giải thích nội dung này",
        "Cho ví dụ",
        "Cấu trúc của nó",
        "Tiếp tục",
        "Phân tích ảnh này",
        "Điều đó có ý nghĩa gì",
        "Hãy xem cái này",
        "Kết quả ra sao",
    ),
}

_HIGH_RISK_EXEMPLARS = (
    "Kết luận người này có phải cha ruột hay không",
    "Xác định danh tính người từ hồ sơ ADN vụ án",
    "Kết luận mẫu hiện trường thuộc về nghi phạm",
    "Đưa ra kết luận chính thức về hỗn hợp DNA của vụ án",
    "Thông số thao tác bắt buộc theo SOP phòng xét nghiệm",
    "Kết luận pháp lý hoặc giá trị chứng cứ của kết quả ADN",
)


@dataclass(frozen=True, slots=True)
class _Prototype:
    label: DomainLabel
    vector: list[float]


class DomainClassifier:
    """Classify intent from semantic similarity to reviewed scope exemplars."""

    def __init__(
        self,
        embedding: BaseEmbedding,
        *,
        minimum_confidence: float,
        minimum_margin: float,
        high_risk_threshold: float,
    ) -> None:
        self._embedding = embedding
        self._minimum_confidence = minimum_confidence
        self._minimum_margin = minimum_margin
        self._high_risk_threshold = high_risk_threshold
        self._prototypes: list[_Prototype] | None = None
        self._high_risk_vectors: list[list[float]] | None = None
        self._lock = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        return self._prototypes is not None and self._high_risk_vectors is not None

    async def warmup(self) -> None:
        """Load and cache all reviewed classifier vectors."""
        try:
            await self._load_vectors()
        except Exception as error:
            raise DomainClassifierError(
                "Semantic domain classifier is unavailable"
            ) from error

    async def classify(
        self,
        query: str,
        *,
        configured_figure: bool = False,
        has_image: bool = False,
        prior_in_domain: bool = False,
    ) -> DomainDecision:
        if configured_figure:
            return DomainDecision(
                label=DomainLabel.IN_DOMAIN,
                risk=RiskLevel.STANDARD,
                reason=DomainReason.CONFIGURED_FIGURE,
                confidence=1.0,
            )

        try:
            prototypes, risk_vectors = await self._load_vectors()
            query_vector = await asyncio.to_thread(self._embedding.embed, query)
        except Exception as error:
            logger.exception(
                "Semantic domain classifier dependency failed ({})",
                type(error).__name__,
            )
            raise DomainClassifierError(
                "Semantic domain classifier is unavailable"
            ) from error
        class_scores = {
            label: max(
                self._cosine(query_vector, prototype.vector)
                for prototype in prototypes
                if prototype.label is label
            )
            for label in DomainLabel
        }
        scores = sorted(class_scores.items(), key=lambda item: item[1], reverse=True)
        label, confidence = scores[0]
        margin = confidence - scores[1][1]

        if prior_in_domain and label is DomainLabel.CLARIFY:
            label = DomainLabel.IN_DOMAIN
            reason = DomainReason.CONTEXTUAL_FOLLOW_UP
        elif has_image and label is not DomainLabel.IN_DOMAIN:
            label = DomainLabel.CLARIFY
            reason = DomainReason.AMBIGUOUS_CONTEXT
        elif confidence < self._minimum_confidence or margin < self._minimum_margin:
            label = DomainLabel.CLARIFY
            reason = DomainReason.AMBIGUOUS_CONTEXT
        elif label is DomainLabel.IN_DOMAIN:
            reason = DomainReason.FORENSIC_GENETICS
        elif label is DomainLabel.OUT_OF_DOMAIN:
            reason = DomainReason.UNRELATED_TOPIC
        else:
            reason = DomainReason.AMBIGUOUS_CONTEXT

        risk_confidence = max(
            self._cosine(query_vector, vector) for vector in risk_vectors
        )
        risk = (
            RiskLevel.HIGH_RISK
            if risk_confidence >= self._high_risk_threshold
            else RiskLevel.STANDARD
        )
        if risk is RiskLevel.HIGH_RISK:
            label = DomainLabel.IN_DOMAIN
            reason = DomainReason.CASE_SPECIFIC_CONCLUSION

        return DomainDecision(
            label=label,
            risk=risk,
            reason=reason,
            confidence=confidence,
        )

    async def _load_vectors(self) -> tuple[list[_Prototype], list[list[float]]]:
        if self._prototypes is not None and self._high_risk_vectors is not None:
            return self._prototypes, self._high_risk_vectors
        async with self._lock:
            if self._prototypes is None or self._high_risk_vectors is None:
                labels: list[DomainLabel] = []
                texts: list[str] = []
                for label, exemplars in _EXEMPLARS.items():
                    labels.extend([label] * len(exemplars))
                    texts.extend(exemplars)
                vectors = await asyncio.to_thread(self._embedding.embed_batch, texts)
                self._prototypes = [
                    _Prototype(label, vector)
                    for label, vector in zip(labels, vectors, strict=True)
                ]
                self._high_risk_vectors = await asyncio.to_thread(
                    self._embedding.embed_batch, list(_HIGH_RISK_EXEMPLARS)
                )
        return self._prototypes, self._high_risk_vectors

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)
