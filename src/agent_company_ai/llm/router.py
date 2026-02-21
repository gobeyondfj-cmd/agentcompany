"""LLM provider router that maps provider names to concrete instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_company_ai.config import LLMConfig
from agent_company_ai.llm.base import BaseLLMProvider

if TYPE_CHECKING:
    from agent_company_ai.config import LLMProviderConfig

logger = logging.getLogger(__name__)

# Registry of supported provider names -> their implementation classes.
# Imports are deferred to avoid pulling in optional SDK dependencies at
# module load time.
_PROVIDER_FACTORIES: dict[str, str] = {
    "anthropic": "agent_company_ai.llm.anthropic.AnthropicProvider",
    "openai": "agent_company_ai.llm.openai.OpenAIProvider",
}


def _import_provider_class(dotted_path: str) -> type[BaseLLMProvider]:
    """Dynamically import a provider class from its fully-qualified path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not (isinstance(cls, type) and issubclass(cls, BaseLLMProvider)):
        raise TypeError(
            f"Expected a BaseLLMProvider subclass at '{dotted_path}', "
            f"got {cls!r}"
        )
    return cls


class LLMRouter:
    """Routes agents to their configured LLM provider.

    Provider instances are created lazily on first access and cached for
    the lifetime of this router so that multiple agents sharing the same
    provider/model combination reuse a single client.

    Parameters
    ----------
    llm_config:
        The ``LLMConfig`` section from the company configuration.
    """

    def __init__(self, llm_config: LLMConfig):
        self._config = llm_config
        self._providers: dict[str, BaseLLMProvider] = {}

    def _resolve_provider_name(self, provider_name: str | None) -> str:
        """Return an explicit provider name, falling back to the default."""
        name = provider_name or self._config.default_provider
        if not name:
            raise ValueError(
                "No provider name specified and no default_provider configured "
                "in the LLM configuration."
            )
        return name

    def _get_provider_config(self, provider_name: str) -> "LLMProviderConfig":
        """Retrieve the provider-specific config block or raise."""
        config_block = getattr(self._config, provider_name, None)
        if config_block is None:
            available = [
                attr
                for attr in ("anthropic", "openai")
                if getattr(self._config, attr, None) is not None
            ]
            raise ValueError(
                f"Provider '{provider_name}' is not configured. "
                f"Available configured providers: {available or 'none'}. "
                f"Add a '{provider_name}' section to your LLM configuration."
            )
        return config_block

    def get_provider(
        self,
        provider_name: str | None = None,
        model_override: str | None = None,
    ) -> BaseLLMProvider:
        """Get or create a provider instance.

        Parameters
        ----------
        provider_name:
            The name of the provider to use (e.g. ``"anthropic"`` or
            ``"openai"``).  Falls back to ``default_provider`` from the
            configuration when ``None``.
        model_override:
            If given, overrides the model specified in the provider's
            configuration.  This causes a distinct provider instance to be
            created and cached separately.

        Returns
        -------
        BaseLLMProvider
            A ready-to-use provider instance.

        Raises
        ------
        ValueError
            If the requested provider is not configured or the provider
            name is unknown.
        """
        name = self._resolve_provider_name(provider_name)

        # Build a cache key that accounts for model overrides so that
        # agents requesting different models get distinct instances.
        cache_key = f"{name}:{model_override}" if model_override else name

        if cache_key in self._providers:
            return self._providers[cache_key]

        # Validate that we know how to build this provider
        if name not in _PROVIDER_FACTORIES:
            raise ValueError(
                f"Unknown provider '{name}'. "
                f"Supported providers: {sorted(_PROVIDER_FACTORIES.keys())}"
            )

        provider_config = self._get_provider_config(name)

        # Validate API key early for a clear error message
        if not provider_config.api_key:
            raise ValueError(
                f"API key for provider '{name}' is empty. "
                f"Set the appropriate API key in your configuration file or "
                f"via environment variables (e.g. ${{ANTHROPIC_API_KEY}})."
            )

        model = model_override or provider_config.model
        if not model:
            raise ValueError(
                f"No model specified for provider '{name}'. "
                f"Set a 'model' in the provider configuration or pass a "
                f"model_override."
            )

        # Dynamically import and instantiate the provider
        provider_cls = _import_provider_class(_PROVIDER_FACTORIES[name])
        provider = provider_cls(
            api_key=provider_config.api_key,
            model=model,
            base_url=provider_config.base_url,
            max_tokens=provider_config.max_tokens,
        )

        self._providers[cache_key] = provider
        logger.info(
            "Created %s provider (model=%s, base_url=%s)",
            name,
            model,
            provider_config.base_url or "default",
        )
        return provider
