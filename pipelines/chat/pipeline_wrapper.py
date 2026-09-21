"""Policy-controlled forensic chat endpoint."""

from uuid import UUID

from fastapi import HTTPException

from hayhooks import BasePipelineWrapper

from chatbot_app.forensic_chat import (
    get_forensic_chat,
)
from chatbot_app.history import (
    ConversationOwnershipError,
)


class PipelineWrapper(BasePipelineWrapper):
    skip_mcp = True

    def setup(self) -> None:
        self.chat = get_forensic_chat()

    async def run_api_async(
        self,
        message: str,
        conversation_id: UUID | None = None,
        figure_id: str | None = None,
        image: str | None = None,
    ) -> dict[str, object]:
        try:
            return await self.chat.answer(
                message,
                conversation_id=(
                    str(conversation_id)
                    if conversation_id
                    is not None
                    else None
                ),
                figure_id=figure_id,
                image=image,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error),
            ) from error
        except ConversationOwnershipError as error:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            ) from error
