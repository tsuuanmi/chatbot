"""Application configuration."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "/app/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llama_base_url: str
    llama_api_key: str
    llama_model_name: str
    llama_max_output_tokens: int = 4096
    llama_temperature: float = 0.3
    llama_top_p: float = 0.9
    llama_top_k: int = 10
    llama_presence_penalty: float = 0.0
    llama_repeat_penalty: float = 1.05
    llama_ctx_size: int = 32768

    embedding_base_url: str
    embedding_api_key: str
    embedding_model_name: str

    database_url: str
    chroma_collection_name: str
    chroma_figure_collection_name: str = "chatbot_figures"
    chroma_host: str = "localhost"
    chroma_port: int = 8002

    figures_dir: str = "./data/figures"
    figure_description_max_tokens: int = Field(default=768, ge=64, le=4096)
    domain_min_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    domain_min_margin: float = Field(default=0.03, ge=0.0, le=1.0)
    domain_high_risk_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    rag_top_k: int = Field(default=5, ge=1, le=20)
    rag_max_distance: float = Field(default=0.85, ge=0.0)
    rag_max_chars: int = Field(default=2000, ge=100)
    history_turn_limit: int = Field(default=4, ge=1)
    startup_max_attempts: int = Field(default=12, ge=1, le=60)
    startup_retry_seconds: float = Field(default=2.0, ge=0.1, le=30.0)

    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_auth_enabled: bool = True
    api_keys_file: str = "./config/auth/api_keys.json"
    api_docs_enabled: bool = False
    api_max_concurrent_requests: int = Field(default=2, ge=1, le=32)
    api_queue_timeout_seconds: float = Field(default=30.0, ge=0.1, le=900.0)
    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values are loaded from environment
