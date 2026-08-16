"""Amazon Bedrock provider, over the Converse API.

Two things make this simpler than Bedrock usually is.

**A Bedrock API key, not SigV4.** The key goes in an `Authorization: Bearer`
header, so this is an HTTP call like every other provider here and needs no
boto3, no credential chain and no request signing. That keeps the provider a
thirty-line adapter instead of a dependency with its own opinions about
threads, and it is why this file looks like `claude.py`.

**Converse, not InvokeModel.** Converse is Bedrock's model-agnostic shape:
`messages`, `system`, `inferenceConfig`, and a `usage` block that reports the
tokens the same way whatever model answered. InvokeModel would mean speaking
each vendor's own body format and reading token counts out of response headers.

The model id is the whole configuration. Anthropic's newer models are
`INFERENCE_PROFILE` only on Bedrock, which means the foundation-model id
(`anthropic.claude-sonnet-5`) is not callable and the profile id
(`us.anthropic.claude-sonnet-5`) is. Getting that wrong answers "not available
for this account", which reads like a permissions problem and is not one.
"""

from typing import Any

from app.core.config import get_settings
from app.modules.ai.domain.exceptions import ProviderUnavailableError
from app.modules.ai.domain.usage import Completion, TokenUsage
from app.modules.ai.infrastructure.providers.base import HTTPLLMProvider


class BedrockProvider(HTTPLLMProvider):
    """Generates text via Amazon Bedrock's Converse API."""

    name = "bedrock"

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(timeout=settings.llm_timeout_seconds)
        self._api_key = settings.bedrock_api_key
        self._region = settings.bedrock_region
        self._model = settings.bedrock_model
        self._max_tokens = settings.llm_max_tokens

    @property
    def _endpoint(self) -> str:
        return (
            f"https://bedrock-runtime.{self._region}.amazonaws.com"
            f"/model/{self._model}/converse"
        )

    async def generate(self, prompt: str, *, system: str | None = None) -> Completion:
        if not self._api_key:
            raise ProviderUnavailableError("Bedrock API key not configured")

        body: dict[str, Any] = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {
                "maxTokens": self._max_tokens,
                "temperature": 0.2,
            },
        }
        if system:
            # A first-class field on Converse rather than a message with a
            # role, which is what makes a system prompt actually behave like
            # one on the models that distinguish them.
            body["system"] = [{"text": system}]

        data = await self._post(
            self._endpoint,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
            },
            json=body,
        )

        blocks = (data.get("output") or {}).get("message", {}).get("content") or []
        text = "".join(block.get("text", "") for block in blocks)
        if not text:
            # An empty answer with a stop reason is a refusal or a truncation,
            # and the gateway should treat it as this provider failing rather
            # than hand an empty plan to the planner.
            raise ValueError(
                f"Bedrock returned no text (stopReason={data.get('stopReason')})"
            )

        usage = data.get("usage") or {}
        return Completion(
            text=text,
            # Converse does not echo the model, and the profile id is what was
            # billed, so the configured id is the honest answer.
            model=self._model,
            usage=TokenUsage(
                # Cache reads and writes are billed differently and are
                # reported apart. They are added in rather than dropped:
                # under-reporting is the one failure a cost report must not
                # have. Their different rate is a refinement for the day
                # prompt caching is actually switched on.
                input_tokens=(
                    usage.get("inputTokens", 0)
                    + usage.get("cacheReadInputTokens", 0)
                    + usage.get("cacheWriteInputTokens", 0)
                ),
                output_tokens=usage.get("outputTokens", 0),
            )
            if usage
            else None,
        )
