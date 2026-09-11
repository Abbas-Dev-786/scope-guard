from __future__ import annotations

from typing import Any

from bedrock_agentcore import BedrockAgentCoreApp
from pydantic import BaseModel, ConfigDict, Field
from strands import Agent
from strands.models import BedrockModel

from services.api.config import get_settings

runtime = BedrockAgentCoreApp()


class ReadinessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=500)


@runtime.entrypoint
async def handler(payload: dict[str, Any]) -> dict[str, str]:
    request = ReadinessRequest.model_validate(payload)
    settings = get_settings()
    if settings.bedrock_model_id == "replace-after-readiness-verification":
        raise RuntimeError("SCOPEGUARD_BEDROCK_MODEL_ID must be verified and configured")
    model = BedrockModel(model_id=settings.bedrock_model_id, temperature=0.0)
    agent = Agent(
        model=model,
        system_prompt=(
            "You are the ScopeGuard readiness role. Return a brief factual response. "
            "You have no tools and cannot send messages, price work, or mutate business state."
        ),
        tools=[],
    )
    result = await agent.invoke_async(request.prompt)
    return {"output": str(result), "role": "readiness"}


if __name__ == "__main__":
    runtime.run()
