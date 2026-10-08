from app.config import Settings
from app.providers.base import ProviderError
from app.providers.http import ClaudeProvider, GeminiProvider


def create_provider(settings: Settings):
    match settings.llm_provider:
        case "claude":
            return ClaudeProvider(
                settings.llm_model,
                settings.anthropic_api_key,
                workspace_id=settings.anthropic_workspace_id,
            )
        case "gemini":
            return GeminiProvider(settings.llm_model, settings.gemini_api_key)
        case _:
            raise ProviderError(
                "PROVIDER_CONFIGURATION", "LLM_PROVIDER must be claude or gemini.", True
            )
