"""Performance benchmarks against live Docker services.

Run with: pytest -m performance
Prerequisite: make start [ACCELERATOR=auto|cpu|gpu] (all services healthy)

These tests hit real LLM (llama.cpp/gemma-4-2b), real PostgreSQL,
real ChromaDB — no mocking. Measures end-to-end latency and token
throughput across real workflow paths.
"""

import gc
import json
import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import psutil
import pytest

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8080")
API_KEY = os.getenv("TEST_API_KEY")
VERIFY: bool | str = os.getenv("TEST_CA_CERT", True)
AUTH_HEADERS = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_memory_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024


@dataclass
class CPUTimes:
    user: float
    system: float

    def total(self) -> float:
        return self.user + self.system


def snapshot_cpu() -> CPUTimes:
    t = psutil.Process(os.getpid()).cpu_times()
    return CPUTimes(user=t.user, system=t.system)


def cpu_util_pct(start: CPUTimes, end: CPUTimes, wall: float) -> float:
    if wall <= 0:
        return 0.0
    return ((end.total() - start.total()) / wall) * 100


@dataclass(frozen=True)
class GPUSample:
    name: str
    memory_used_mib: int
    memory_total_mib: int
    utilization_pct: int


def sample_gpu() -> GPUSample | None:
    """Read the first NVIDIA GPU, or return None when NVIDIA is unavailable."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        name, used, total, utilization = result.stdout.splitlines()[0].split(", ")
        return GPUSample(name, int(used), int(total), int(utilization))
    except (ValueError, IndexError):
        return None


class GPUMonitor:
    """Poll NVIDIA usage while one or more requests are running."""

    def __init__(self, interval: float = 0.1) -> None:
        self.interval = interval
        self.samples: list[GPUSample] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "GPUMonitor":
        initial = sample_gpu()
        if initial is not None:
            self.samples.append(initial)
            self._thread = threading.Thread(target=self._poll, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        final = sample_gpu()
        if final is not None:
            self.samples.append(final)

    def _poll(self) -> None:
        while not self._stop.wait(self.interval):
            sample = sample_gpu()
            if sample is not None:
                self.samples.append(sample)

    def summary(self) -> str:
        if not self.samples:
            return "gpu=unavailable"
        peak_memory = max(sample.memory_used_mib for sample in self.samples)
        peak_utilization = max(sample.utilization_pct for sample in self.samples)
        avg_utilization = sum(sample.utilization_pct for sample in self.samples) / len(
            self.samples
        )
        latest = self.samples[-1]
        return (
            f"gpu={latest.name} memory_peak={peak_memory}/{latest.memory_total_mib}MiB "
            f"util_peak={peak_utilization}% util_avg={avg_utilization:.1f}%"
        )


def _metric_number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def response_timing(data: dict, text: str, wall: float) -> tuple[int, float, str]:
    """Return completion tokens, tok/s, and whether the rate is measured or estimated."""
    usage = data.get("usage")
    if isinstance(usage, dict):
        completion_tokens = _metric_number(usage.get("completion_tokens"))
        if completion_tokens is not None:
            return (
                int(completion_tokens),
                completion_tokens / wall if wall > 0 else 0.0,
                "usage",
            )

    timings = data.get("timings")
    if isinstance(timings, dict):
        predicted_tokens = _metric_number(timings.get("predicted_n"))
        predicted_rate = _metric_number(timings.get("predicted_per_second"))
        if predicted_tokens is not None:
            return (
                int(predicted_tokens),
                predicted_rate or (predicted_tokens / wall if wall > 0 else 0.0),
                "llama.cpp",
            )

    estimated_tokens = max(1, len(text.split()))
    return estimated_tokens, estimated_tokens / wall if wall > 0 else 0.0, "estimated"


@dataclass(frozen=True)
class StreamResult:
    text: str
    token_count: int
    tokens_per_second: float
    token_rate_source: str
    ttft_ms: float | None


def consume_stream(client, query: str, conversation_id: str) -> StreamResult:
    """Consume SSE incrementally so TTFT is measured at the first content event."""
    started = time.perf_counter()
    pieces: list[str] = []
    ttft_ms: float | None = None
    completion_tokens: float | None = None
    predicted_rate: float | None = None

    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"query": query, "conversation_id": conversation_id},
    ) as response:
        assert response.status_code == 200, response.text
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            content = event.get("content")
            if content:
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - started) * 1000
                pieces.append(content)
            usage = event.get("usage")
            if isinstance(usage, dict):
                completion_tokens = _metric_number(usage.get("completion_tokens"))
            timings = event.get("timings")
            if isinstance(timings, dict):
                completion_tokens = _metric_number(timings.get("predicted_n"))
                predicted_rate = _metric_number(timings.get("predicted_per_second"))

    total_wall = time.perf_counter() - started
    text = "".join(pieces)
    if completion_tokens is not None:
        token_count = int(completion_tokens)
        token_rate = predicted_rate or (
            token_count / total_wall if total_wall > 0 else 0.0
        )
        source = "server"
    else:
        token_count = max(1, len(text.split()))
        token_rate = token_count / total_wall if total_wall > 0 else 0.0
        source = "estimated"
    return StreamResult(text, token_count, token_rate, source, ttft_ms)


def _show(label: str, query: str, answer: str) -> None:
    """Print the request and answer for the test log."""
    print(f"\n  [{label}]")
    print(f"  request:  {query}")
    print(f"  answer:   {answer}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.integration,
    pytest.mark.performance,
]


@pytest.fixture(scope="session")
def requires_chatbot_service():
    """Fail-fast if chatbot service is not reachable."""
    import httpx

    start = time.monotonic()
    while time.monotonic() - start < 300:
        try:
            resp = httpx.get(f"{BASE_URL}/api/v1/health", verify=VERIFY, timeout=10.0)
            if resp.status_code == 200:
                return
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
            pass
        time.sleep(2)
    pytest.fail(
        f"Chatbot service not reachable at {BASE_URL}. "
        "Run 'make start ACCELERATOR=cpu' or 'make start ACCELERATOR=gpu' first."
    )


@pytest.fixture
def http(requires_chatbot_service):
    """Live HTTPX client against running chatbot."""
    import httpx

    with httpx.Client(
        base_url=BASE_URL,
        headers=AUTH_HEADERS,
        verify=VERIFY,
        timeout=120.0,
    ) as client:
        yield client


@pytest.fixture
def http_stream(requires_chatbot_service):
    """Live HTTPX client for streaming (auto-closes)."""
    import httpx

    with httpx.Client(
        base_url=BASE_URL,
        headers=AUTH_HEADERS,
        verify=VERIFY,
        timeout=120.0,
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# /api/v1/chat — non-streaming latency
# ---------------------------------------------------------------------------


class TestGPUAvailability:
    """Report GPU availability without failing CPU-only environments."""

    def test_gpu_available(self) -> None:
        sample = sample_gpu()
        if sample is None:
            pytest.skip("NVIDIA GPU is unavailable; GPU metrics are skipped")
        print(
            f"\n  GPU available: {sample.name}  "
            f"memory={sample.memory_used_mib}/{sample.memory_total_mib}MiB  "
            f"utilization={sample.utilization_pct}%"
        )
        assert sample.memory_total_mib > 0


class TestChatNonStreamingPerformance:
    """Measures real LLM + Postgres + ChromaDB pipeline (non-streaming)."""

    def test_chat_text_only_latency(self, http):
        """Text-only query, no figure — full RAG + LLM path."""
        gc.collect()
        mem_start = get_memory_mb()
        s_cpu = snapshot_cpu()
        query = "mtDNA là gì?"
        conv_id = str(uuid.uuid4())
        with GPUMonitor() as gpu:
            t0 = time.perf_counter()
            r = http.post(
                "/api/v1/chat",
                json={"query": query, "conversation_id": conv_id},
            )
            wall = time.perf_counter() - t0
        e_cpu = snapshot_cpu()
        mem_end = get_memory_mb()

        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        data = r.json()
        assert data["response"], "LLM response should be non-empty"
        token_count, token_rate, rate_source = response_timing(
            data, data["response"], wall
        )

        print(
            f"\n  chat text-only                 wall={wall * 1000:8.1f}ms  "
            f"tokens={token_count} tok/s={token_rate:.1f} ({rate_source})  "
            f"cpu={e_cpu.total() - s_cpu.total():.3f}s  "
            f"cpu_util={cpu_util_pct(s_cpu, e_cpu, wall):5.1f}%  "
            f"mem={mem_end:.1f}MB  Δ={mem_end - mem_start:+.1f}MB\n  {gpu.summary()}"
        )
        print(f"  response chars: {len(data['response'])}  conv={conv_id}")
        _show("chat text-only", query, data["response"])

    def test_chat_multi_turn_latency(self, http):
        """3 consecutive /chat calls — tests Postgres history load + RAG."""
        conv_id = str(uuid.uuid4())
        queries = ["DNA là gì?", "Cấu trúc của nó?", "Cho ví dụ?"]
        timings = []

        for q in queries:
            gc.collect()
            mem_before = get_memory_mb()
            with GPUMonitor() as gpu:
                t0 = time.perf_counter()
                r = http.post(
                    "/api/v1/chat",
                    json={"query": q, "conversation_id": conv_id},
                )
                wall = time.perf_counter() - t0
            timings.append(wall * 1000)
            assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
            data = r.json()
            answer = data["response"]
            assert answer, f"Empty response for: {q}"
            token_count, token_rate, rate_source = response_timing(data, answer, wall)
            print(
                f"  turn {len(timings)}: {wall * 1000:8.1f}ms  "
                f"tokens={token_count} tok/s={token_rate:.1f} ({rate_source})  "
                f"Δmem={get_memory_mb() - mem_before:+.1f}MB  {gpu.summary()}"
            )
            _show(f"multi-turn turn {len(timings)}", q, answer)

        print(
            f"\n  multi-turn avg: {sum(timings) / len(timings):.1f}ms  max: {max(timings):.1f}ms"
        )

    @pytest.mark.parametrize("request_count", [5, 10])
    def test_concurrent_requests(self, requires_chatbot_service, request_count):
        """Five and ten independent generated requests, measured concurrently."""
        import httpx

        query_pool = [
            "Giải thích vai trò của RNA trong biểu hiện gene.",
            "STR được sử dụng như thế nào trong giám định ADN?",
            "So sánh DNA nhân và DNA ty thể.",
            "PCR có vai trò gì trong phân tích di truyền?",
            "Haplogroup có ý nghĩa gì trong nghiên cứu quần thể?",
            "ADN ty thể được truyền qua các thế hệ như thế nào?",
            "Marker di truyền có ý nghĩa gì trong giám định ADN?",
            "Độ tin cậy của kết quả giám định ADN phụ thuộc vào yếu tố nào?",
            "Phân tích DNA có thể hỗ trợ nhận dạng mẫu vật ra sao?",
            "Nguồn gốc di truyền được nghiên cứu bằng dữ liệu nào?",
        ]
        queries = query_pool[:request_count]

        def request(query: str) -> tuple[str, float, int, dict]:
            started = time.perf_counter()
            with httpx.Client(
                base_url=BASE_URL,
                headers=AUTH_HEADERS,
                verify=VERIFY,
                timeout=120.0,
            ) as client:
                response = client.post(
                    "/api/v1/chat",
                    json={"query": query, "conversation_id": str(uuid.uuid4())},
                )
            elapsed = time.perf_counter() - started
            if response.status_code not in {200, 429}:
                response.raise_for_status()
            return query, elapsed, response.status_code, response.json()

        with GPUMonitor() as gpu:
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=request_count) as executor:
                results = list(executor.map(request, queries))
            total_wall = time.perf_counter() - started

        assert len(results) == request_count
        successful = [result for result in results if result[2] == 200]
        busy = [result for result in results if result[2] == 429]
        assert successful, "At least one request must complete successfully"
        assert all(result[3]["response"] for result in successful)
        timings = [
            response_timing(data, data["response"], elapsed)
            for _, elapsed, _, data in successful
        ]
        total_tokens = sum(result[0] for result in timings)
        aggregate_rate = total_tokens / total_wall if total_wall > 0 else 0.0
        print(
            f"\n  concurrent requests={request_count:<2}        "
            f"wall={total_wall * 1000:8.1f}ms  "
            f"completed={len(successful)} busy={len(busy)}  "
            f"throughput={len(successful) / total_wall:.2f} req/s  "
            f"aggregate={total_tokens} tokens tok/s={aggregate_rate:.1f}\n  "
            f"{gpu.summary()}"
        )
        for (query, elapsed, _, data), (
            token_count,
            token_rate,
            rate_source,
        ) in zip(successful, timings):
            print(
                f"  request wall={elapsed * 1000:8.1f}ms  "
                f"tokens={token_count} tok/s={token_rate:.1f} ({rate_source})  "
                f"source={data['source']}  query={query}"
            )


# ---------------------------------------------------------------------------
# /api/v1/chat/stream — streaming throughput
# ---------------------------------------------------------------------------


class TestChatStreamPerformance:
    """Measures real LLM streaming — TTFT, tokens/sec, total wall."""

    def test_stream_ttft_and_throughput(self, http_stream):
        """Single streaming call — measure TTFT, token count, tok/s."""
        gc.collect()
        mem_start = get_memory_mb()
        query = "Giải thích STR là gì?"
        conv_id = str(uuid.uuid4())
        with GPUMonitor() as gpu:
            result = consume_stream(http_stream, query, conv_id)
        mem_end = get_memory_mb()

        print(
            f"\n  stream text                  ttft={result.ttft_ms or -1:6.0f}ms  "
            f"tokens={result.token_count} tok/s={result.tokens_per_second:.1f} "
            f"({result.token_rate_source})  resp_len={len(result.text)}chars\n  "
            f"{gpu.summary()}  mem={mem_end:.1f}MB  Δ={mem_end - mem_start:+.1f}MB"
        )
        _show("stream text", query, result.text)
        assert result.token_count > 0, "Should yield at least one token"
        assert result.text, "Full response should be non-empty"


# ---------------------------------------------------------------------------
# Authoritative chat + approved evidence performance
# ---------------------------------------------------------------------------


class TestEvidencePerformance:
    """Approved evidence retrieval through the authoritative chat cascade."""

    def test_grounded_chat_latency(self, http):
        """Semantic classifier + hybrid retrieval + grounded generation."""
        gc.collect()
        mem_start = get_memory_mb()
        s_cpu = snapshot_cpu()

        query = "Trong trường hợp nào dữ liệu STR nên được ưu tiên trong giám định?"
        conv_id = str(uuid.uuid4())
        with GPUMonitor() as gpu:
            t0 = time.perf_counter()
            r = http.post(
                "/api/v1/chat",
                json={"query": query, "conversation_id": conv_id},
            )
            wall = time.perf_counter() - t0
        e_cpu = snapshot_cpu()
        mem_end = get_memory_mb()

        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        data = r.json()
        assert data["response"], "Grounded response should be non-empty"
        assert data["source"] == "generated"
        assert data["citations"]
        token_count, token_rate, rate_source = response_timing(
            data, data["response"], wall
        )

        print(
            f"\n  grounded_chat                 wall={wall * 1000:8.1f}ms  "
            f"tokens={token_count} tok/s={token_rate:.1f} ({rate_source})  "
            f"cpu={e_cpu.total() - s_cpu.total():.3f}s  "
            f"cpu_util={cpu_util_pct(s_cpu, e_cpu, wall):5.1f}%  "
            f"mem={mem_end:.1f}MB  Δ={mem_end - mem_start:+.1f}MB\n  {gpu.summary()}"
        )
        _show("grounded_chat", query, data["response"])

    def test_grounded_chat_stream_latency(self, http_stream):
        """Streaming grounded chat — measures TTFT + throughput."""
        gc.collect()
        query = "Trong tình huống giám định nào mtDNA thường được ưu tiên sử dụng?"
        conv_id = str(uuid.uuid4())
        with GPUMonitor() as gpu:
            result = consume_stream(http_stream, query, conv_id)

        print(
            f"\n  grounded_chat_stream          ttft={result.ttft_ms or -1:6.0f}ms  "
            f"tokens={result.token_count} tok/s={result.tokens_per_second:.1f} "
            f"({result.token_rate_source})\n  {gpu.summary()}"
        )
        _show("grounded_chat_stream", query, result.text)
        assert result.token_count > 0
