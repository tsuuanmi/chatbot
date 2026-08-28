"""Controlled knowledge indexing."""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from pypdf import PdfReader

from src.base.components.vector_databases.base import BaseVectorDatabase
from src.common.knowledge_base import load_knowledge_base
from src.knowledge.manifest import SourceManifest, SourceStatus
from src.knowledge.models import ApprovalStatus

_PACKAGED_SOURCE = "knowledge_base.tsv"


@dataclass(frozen=True, slots=True)
class _PreparedSource:
    manifest: SourceManifest
    chunks: list[str]
    metadata: list[dict[str, str | int]]


class KnowledgeIndexer:
    """Index approved project records and manifest-controlled PDF sources."""

    def __init__(self, vector_database: BaseVectorDatabase) -> None:
        self._vector_database = vector_database

    async def index_directory(self, directory: Path) -> int:
        prepared = await self._prepare_directory(directory)
        total = 0
        for source in prepared:
            manifest = source.manifest
            total += await self._replace_source(
                manifest.source_id,
                [
                    f"pdf:{manifest.source_id}:chunk:{index}"
                    for index in range(1, len(source.chunks) + 1)
                ],
                source.chunks,
                source.metadata,
            )
            if manifest.approval_status is not SourceStatus.APPROVED:
                logger.info(
                    "Removed {} source {}",
                    manifest.approval_status,
                    manifest.source_id,
                )
        return total

    async def index_knowledge_base(self, path: Path) -> int:
        entries = [
            entry
            for entry in await asyncio.to_thread(load_knowledge_base, path)
            if entry.approval_status == ApprovalStatus.APPROVED
        ]
        texts = [
            f"Câu hỏi: {entry.question}\nTrả lời: {entry.answer}"
            + (f"\nTừ khóa: {entry.keywords}" if entry.keywords else "")
            for entry in entries
        ]
        metadata: list[dict[str, str | int]] = [
            {
                "source": path.name,
                "entry": entry.number,
                "topic": entry.topic,
                "figure_id": entry.figure_id or "",
                "source_id": entry.source_id,
                "source_title": entry.source_title,
                "source_authority": entry.source_authority,
                "source_version": entry.source_version,
                "source_page_or_section": entry.source_page_or_section,
                "effective_date": entry.effective_date,
                "reviewed_at": entry.reviewed_at,
                "reviewer": entry.reviewer,
                "approval_status": entry.approval_status,
            }
            for entry in entries
        ]
        ids = [f"knowledge:{entry.number}" for entry in entries]
        return await self._replace_source(path.name, ids, texts, metadata)

    async def _prepare_directory(self, directory: Path) -> list[_PreparedSource]:
        manifests = [
            SourceManifest.load(path)
            for path in sorted(directory.glob("*.manifest.json"))
        ]
        self._validate_manifests(directory, manifests)

        verified_paths = {
            manifest.source_id: manifest.verify_file(directory)
            for manifest in manifests
            if manifest.approval_status is SourceStatus.APPROVED
        }

        prepared: list[_PreparedSource] = []
        for manifest in manifests:
            if manifest.approval_status is not SourceStatus.APPROVED:
                prepared.append(_PreparedSource(manifest, [], []))
                continue
            try:
                chunks, metadata = await asyncio.to_thread(
                    self._read_pdf_chunks,
                    verified_paths[manifest.source_id],
                    manifest,
                )
            except Exception as error:
                raise ValueError(f"Invalid PDF source: {manifest.file}") from error
            if not chunks:
                raise ValueError(
                    f"Approved PDF has no extractable text: {manifest.file}"
                )
            prepared.append(_PreparedSource(manifest, chunks, metadata))
        return prepared

    async def _replace_source(
        self,
        source_id: str,
        ids: list[str],
        texts: list[str],
        metadata: list[dict[str, str | int]],
    ) -> int:
        await asyncio.to_thread(
            self._vector_database.replace_source,
            source_id,
            ids,
            texts,
            metadata,
        )
        logger.info("Indexed {} records from {}", len(texts), source_id)
        return len(texts)

    @staticmethod
    def _validate_manifests(directory: Path, manifests: list[SourceManifest]) -> None:
        source_ids = [manifest.source_id for manifest in manifests]
        if _PACKAGED_SOURCE in source_ids:
            raise ValueError(f"Reserved source_id: {_PACKAGED_SOURCE}")
        files = [manifest.file for manifest in manifests]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Duplicate source_id in PDF manifests")
        if len(files) != len(set(files)):
            raise ValueError("Multiple manifests reference the same PDF")

        manifest_files = set(files)
        unmanifested = sorted(
            path.name
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix.casefold() == ".pdf"
            and path.name not in manifest_files
        )
        if unmanifested:
            raise ValueError(
                "Every PDF requires one source manifest: " + ", ".join(unmanifested)
            )

    @classmethod
    def _read_pdf_chunks(
        cls, path: Path, manifest: SourceManifest
    ) -> tuple[list[str], list[dict[str, str | int]]]:
        reader = PdfReader(path)
        chunks: list[str] = []
        metadata: list[dict[str, str | int]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            for page_chunk in cls._chunk_text(page.extract_text() or ""):
                chunks.append(page_chunk)
                metadata.append(
                    {
                        "source": manifest.source_id,
                        "source_id": manifest.source_id,
                        "source_title": manifest.title,
                        "source_authority": manifest.authority,
                        "source_version": manifest.version,
                        "source_page_or_section": str(page_number),
                        "effective_date": manifest.effective_date.isoformat(),
                        "reviewed_at": manifest.reviewed_at.isoformat(),
                        "reviewer": manifest.reviewer,
                        "approver": manifest.approver,
                        "approval_status": manifest.approval_status,
                        "access_class": manifest.access_class,
                        "content_hash": manifest.sha256,
                        "supersedes": manifest.supersedes or "",
                        "page": page_number,
                        "chunk": len(chunks),
                    }
                )
                if len(chunks) >= manifest.max_chunks:
                    return chunks, metadata
        return chunks, metadata

    @staticmethod
    def _chunk_text(
        text: str, chunk_size: int = 1200, overlap: int = 200
    ) -> Iterable[str]:
        normalized = " ".join(text.split())
        if not normalized:
            return
        start = 0
        while start < len(normalized):
            end = min(start + chunk_size, len(normalized))
            if end < len(normalized):
                boundary = normalized.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            yield normalized[start:end]
            if end == len(normalized):
                return
            start = max(end - overlap, start + 1)
