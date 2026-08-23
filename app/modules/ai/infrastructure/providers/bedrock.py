"""Amazon Bedrock provider, over the Converse API.

Two things make this simpler than Bedrock usually is.

**A Bedrock API key, not SigV4.** The key goes in an `Authorization: Bearer`
header, so this is a plain HTTP call and needs no boto3, no credential chain
and no request signing. That keeps this a small adapter instead of a dependency
with its own opinions about threads inside an async application.

**One class, several providers.** Every remote model family in the fallback
chain is a Bedrock model, so what distinguishes one link of the chain from the
next is the *family* it addresses, not the vendor it talks to: Anthropic's
Claude, Amazon's Nova and OpenAI's open-weight models are three instances of
this class over one transport and one credential. The tier still picks the
size within a family, which is why each instance carries two model ids.

A consequence worth being honest about: three families behind one vendor means
three circuit breakers that are not independent failure domains. They protect
against a single family being throttled or losing access — which is real, since
Bedrock quotas are per model — but not against Bedrock itself being down. That
is what the local Ollama at the end of the chain is for.

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
from app.modules.ai.domain.tiers import Tier
from app.modules.ai.domain.usage import Completion, TokenUsage
from app.modules.ai.infrastructure.providers.base import HTTPLLMProvider


class BedrockProvider(HTTPLLMProvider):
    """Generates text via Amazon Bedrock's Converse API.

    ``name`` is the model family as the chain and ``GET /ai/health`` know it
    ("claude", "nova", "openai"), not the vendor: the vendor is Bedrock for all
    of them, and naming three links "bedrock" would make the chain unreadable.
    """

    def __init__(self, *, name: str, model: str, fast_model: str = "") -> None:
        settings = get_settings()
        super().__init__(timeout=settings.llm_timeout_seconds)
        self.name = name
        self._api_key = settings.bedrock_api_key
        self._region = settings.bedrock_region
        self._model = model
        self._fast_model = fast_model
        self._max_tokens = settings.llm_max_tokens

    def _endpoint(self, model: str) -> str:
        return (
            f"https://bedrock-runtime.{self._region}.amazonaws.com"
            f"/model/{model}/converse"
        )

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        tier: Tier = Tier.STANDARD,
    ) -> Completion:
        model = self._model_for(tier)
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
            self._endpoint(model),
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
            # billed, so the id that was called is the honest answer.
            model=model,
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
