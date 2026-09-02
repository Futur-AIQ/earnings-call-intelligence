"""OpenRouter LLM client configuration."""

from functools import lru_cache

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM configuration settings."""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        extra="ignore",
    )

    # OpenRouter API key is read without the LLM_ prefix (a bare env var,
    # not pipeline-specific configuration).
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    model_name: str = "openai/gpt-oss-20b"
    fallback_model_name: str = "google/gemma-3-27b-it"  # Fallback when primary returns empty
    temperature: float = 0.0
    request_timeout: int = 120
    num_predict: int = 4096  # Max tokens to generate


class LLMResponse(BaseModel):
    """Wrapper for LLM response with metadata."""

    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@lru_cache
def get_llm_settings() -> LLMSettings:
    """Get cached LLM settings."""
    return LLMSettings()


def create_llm_client(settings: LLMSettings | None = None) -> ChatOpenAI:
    """Create configured OpenRouter (OpenAI-compatible) chat client.

    Args:
        settings: Optional custom settings. Uses defaults if not provided.

    Returns:
        Configured ChatOpenAI instance pointed at OpenRouter.
    """
    settings = settings or get_llm_settings()

    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=settings.temperature,
        timeout=settings.request_timeout,
        max_tokens=settings.num_predict,
        streaming=False,
    )


def create_json_llm_client(
    settings: LLMSettings | None = None,
    use_fallback: bool = False,
    num_predict: int | None = None,
    temperature: float | None = None,
) -> ChatOpenAI:
    """Create LLM client configured for JSON output.

    Args:
        settings: Optional custom settings.
        use_fallback: If True, use the fallback model instead of primary.
        num_predict: Override max tokens to generate (uses settings default if None).
        temperature: Override sampling temperature (uses settings default if None).

    Returns:
        ChatOpenAI instance (via OpenRouter) configured for JSON responses.
    """
    settings = settings or get_llm_settings()
    model = settings.fallback_model_name if use_fallback else settings.model_name

    return ChatOpenAI(
        model=model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=temperature if temperature is not None else settings.temperature,
        timeout=settings.request_timeout,
        max_tokens=num_predict if num_predict is not None else settings.num_predict,
        # Note: response_format={"type": "json_object"} intentionally omitted —
        # not all OpenRouter-routed models honor it, and JSON extraction is
        # handled in chains.py _parse_json_response instead.
        streaming=False,
    )


def get_fallback_model_name() -> str:
    """Get the fallback model name from settings."""
    return get_llm_settings().fallback_model_name


def get_primary_model_name() -> str:
    """Get the primary model name from settings."""
    return get_llm_settings().model_name
