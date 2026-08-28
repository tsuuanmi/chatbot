"""Server-sent event serialization for chat streams."""

from src.common.schemas import StreamingChatChunk


def format_sse(chunk: StreamingChatChunk) -> str:
    return f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"
