"""
Base adapter interface for LLM providers.

Defines the abstract interface that all model adapters must implement
for consistent interaction with different LLM providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ModelResponse:
    """Standardized response format from LLM models."""

    content: str
    model: str
    provider: str
    timestamp: datetime = field(default_factory=datetime.now)
    tokens_used: int | None = None
    latency_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_response: Any | None = None

    def __post_init__(self) -> None:
        """Validate response data after initialization."""
        if not self.content:
            raise ValueError("Response content cannot be empty")
        if not self.model:
            raise ValueError("Model name cannot be empty")
        if not self.provider:
            raise ValueError("Provider name cannot be empty")


class BaseAdapter(ABC):
    """Abstract base class for LLM model adapters."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: int = 30,
    ) -> None:
        """
        Initialize the adapter.

        Args:
            api_key: API key for the LLM provider
            model: Model identifier
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0-1.0)
            timeout: Request timeout in seconds
        """
        if not api_key:
            raise ValueError(f"{self.__class__.__name__}: API key cannot be empty")
        if not model:
            raise ValueError(f"{self.__class__.__name__}: Model name cannot be empty")
        if max_tokens <= 0:
            raise ValueError(f"{self.__class__.__name__}: max_tokens must be positive")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError(f"{self.__class__.__name__}: temperature must be between 0.0 and 2.0")
        if timeout <= 0:
            raise ValueError(f"{self.__class__.__name__}: timeout must be positive")

        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        """
        Generate a response from the model.

        Args:
            prompt: User prompt to send to the model
            system_prompt: Optional system prompt for context

        Returns:
            ModelResponse object containing the model's response

        Raises:
            ValueError: If prompt is empty
            Exception: Provider-specific errors
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get the name of the LLM provider.

        Returns:
            Provider name as string
        """
        pass

    def validate_prompt(self, prompt: str) -> None:
        """
        Validate prompt before sending to model.

        Args:
            prompt: User prompt to validate

        Raises:
            ValueError: If prompt is empty or invalid
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        # Additional validation can be added here
        if len(prompt) > 1_000_000:  # 1M characters
            raise ValueError("Prompt exceeds maximum length")
