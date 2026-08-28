"""llama.cpp OpenAI-compatible embedding client."""

import httpx

from src.base.components.embeddings.base import BaseEmbedding
from src.config.settings import Settings, get_settings


class LlamaCppEmbedding(BaseEmbedding):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url=self.settings.embedding_base_url,
            headers={"Authorization": f"Bearer {self.settings.embedding_api_key}"},
            timeout=60.0,
        )

    def healthcheck(self) -> None:
        """Verify that the configured model can produce an embedding."""
        vector = self.embed("health check")
        if not vector:
            raise RuntimeError("Embedding server returned an empty vector")

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.post(
            "/embeddings",
            json={"model": self.settings.embedding_model_name, "input": texts},
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        vectors = [item["embedding"] for item in data]
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise RuntimeError("Embedding server returned an invalid response")
        return vectors

    def close(self) -> None:
        self._client.close()
