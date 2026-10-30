"""
Shared types for the LLM runtime and the model catalog.

A ModelConfig is everything the runtime needs to call one model. The catalog
builds it from an llm_models row joined with its llm_providers row (with the API
key decrypted), and model_from_env() builds one from the OPENAI_* / ANTHROPIC_*
environment variables when the catalog is empty.
"""
import os
from dataclasses import dataclass, field, replace
from typing import Optional

# Provider kinds: which client the runtime uses
KIND_OPENAI_COMPATIBLE = "openai_compatible"
KIND_ANTHROPIC = "anthropic"
PROVIDER_KINDS = (KIND_OPENAI_COMPATIBLE, KIND_ANTHROPIC)

# Privacy tiers, see docs/model_provider_strategy.md
PRIVACY_TIERS = ("local", "eu", "trusted", "untrusted")

# Whether a model thinks: never, when asked (reasoning_effort set), or always
REASONING_MODES = ("none", "optional", "always")

CURRENCIES = ("USD", "EUR")


@dataclass(frozen=True)
class ModelConfig:
    """Everything the runtime needs to call one model."""

    # Identity
    id: Optional[int]                   # llm_models.id; None for the environment fallback
    display_name: str                   # "DeepSeek V4.1 Flash (Cortecs)"
    model_id: str                       # API model name: "deepseek-v4.1-flash-1017"

    # Provider
    provider_id: Optional[int]
    provider_name: str
    kind: str                           # one of PROVIDER_KINDS
    base_url: Optional[str]             # None = the SDK default
    api_key: Optional[str] = field(default=None, repr=False)
    default_headers: dict = field(default_factory=dict)
    privacy_tier: str = "trusted"       # the model's override, else the provider's tier
    currency: str = "USD"               # currency of the prices below

    # Capabilities
    supports_tools: bool = True
    supports_vision: bool = False
    reasoning: str = "none"             # one of REASONING_MODES
    reasoning_passback: bool = False    # send reasoning_content back on assistant messages in tool loops
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None

    # Default request settings; None = leave it to the provider
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    reasoning_effort: Optional[str] = None
    extra_body: dict = field(default_factory=dict)  # merged into the request body as-is

    # Prices per million tokens, for cost display
    input_price_per_mtok: Optional[float] = None
    output_price_per_mtok: Optional[float] = None

    def cost(self, usage: "Usage") -> Optional[float]:
        """Cost of a usage record in this model's currency, or None without prices."""
        if self.input_price_per_mtok is None or self.output_price_per_mtok is None:
            return None
        return (usage.input_tokens * self.input_price_per_mtok
                + usage.output_tokens * self.output_price_per_mtok) / 1_000_000


@dataclass
class Usage:
    """Token usage of one assistant message, summed over all model calls of the agent loop."""

    input_tokens: int = 0
    output_tokens: int = 0              # includes reasoning tokens
    reasoning_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None

    def add(self, other: "Usage") -> None:
        """Add another usage record (one model call) to this one."""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        if other.reasoning_tokens is not None:
            self.reasoning_tokens = (self.reasoning_tokens or 0) + other.reasoning_tokens
        if other.cached_input_tokens is not None:
            self.cached_input_tokens = (self.cached_input_tokens or 0) + other.cached_input_tokens

    def to_api(self, config: Optional[ModelConfig] = None) -> dict:
        """The camelCase dict stored in messages.usage and sent to the frontend."""
        cost = config.cost(self) if config else None
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "reasoningTokens": self.reasoning_tokens,
            "cachedInputTokens": self.cached_input_tokens,
            "cost": round(cost, 6) if cost is not None else None,
            "currency": config.currency if config and cost is not None else None,
        }


def model_from_env() -> Optional[ModelConfig]:
    """
    Build the fallback model from the environment variables, as before the catalog.

    The provider is LLM_PROVIDER, else whichever of OPENAI_API_KEY and
    ANTHROPIC_API_KEY is set. Returns None when neither key is set.
    """
    provider = (os.getenv("LLM_PROVIDER") or "").lower()
    if not provider:
        if os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"

    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        model = os.getenv("OPENAI_MODEL", "gpt-5.2")
        base_url = os.getenv("OPENAI_BASE_URL") or None
        # OpenAI's own models take images; a custom endpoint only with MODEL_RECEIVE_IMAGES=true
        custom_endpoint = base_url is not None and "api.openai.com" not in base_url
        supports_vision = (not custom_endpoint
                           or os.getenv("MODEL_RECEIVE_IMAGES", "false").lower() == "true")
        return ModelConfig(
            id=None,
            display_name=model,
            model_id=model,
            provider_id=None,
            provider_name="OpenAI (environment)",
            kind=KIND_OPENAI_COMPATIBLE,
            base_url=base_url,
            api_key=os.getenv("OPENAI_API_KEY"),
            privacy_tier="trusted",
            supports_vision=supports_vision,
            reasoning="optional",
            reasoning_effort=os.getenv("REASONING_LEVEL") or None,
        )

    if provider == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        return ModelConfig(
            id=None,
            display_name=model,
            model_id=model,
            provider_id=None,
            provider_name="Anthropic (environment)",
            kind=KIND_ANTHROPIC,
            base_url=os.getenv("ANTHROPIC_BASE_URL") or None,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            privacy_tier="trusted",
            supports_vision=True,
            reasoning="optional",
        )

    return None


def auxiliary_model_from_env() -> Optional[ModelConfig]:
    """
    The environment model for auxiliary tasks (titles, speech preprocessing).

    Same as model_from_env(), with AUXILIARY_REASONING_LEVEL as the reasoning
    effort when that variable is set, so these short tasks can think less.
    """
    config = model_from_env()
    effort = (os.getenv("AUXILIARY_REASONING_LEVEL") or "").strip().lower()
    if config is not None and effort:
        config = replace(config, reasoning_effort=effort)
    return config
