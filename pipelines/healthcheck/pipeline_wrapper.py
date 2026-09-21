"""Application dependency readiness endpoint."""

from hayhooks import BasePipelineWrapper

from chatbot_app.readiness import (
    get_readiness,
)


class PipelineWrapper(BasePipelineWrapper):
    skip_mcp = True

    def setup(self) -> None:
        self.readiness = get_readiness()

    async def run_api_async(
        self,
    ) -> dict[str, str]:
        return await self.readiness.check()
