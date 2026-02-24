"""
OpenAI adapter implementation.

Provides interface to OpenAI models (GPT-4, GPT-3.5, etc.) via the OpenAI API.
"""

import time
from typing import Any

from openai import AsyncOpenAI

from .base_adapter import BaseAdapter, ModelResponse


class OpenAIAdapter(BaseAdapter):
    """Adapter for OpenAI models."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: int = 30,
    ) -> None:
        """
        Initialize OpenAI adapter.

        Args:
            api_key: OpenAI API key
            model: OpenAI model identifier
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            timeout: Request timeout in seconds
        """
        super().__init__(api_key, model, max_tokens, temperature, timeout)
        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        """
        Generate a response from OpenAI.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            ModelResponse with OpenAI's response

        Raises:
            ValueError: If prompt is invalid
            Exception: API errors
        """
        self.validate_prompt(prompt)

        start_time = time.perf_counter()

        try:
            # Build messages
            messages: list[dict[str, str]] = []

            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            messages.append({"role": "user", "content": prompt})

            # Call OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000

            # Extract content
            content = ""
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content or ""

            # Extract token usage
            tokens_used = None
            if response.usage:
                tokens_used = response.usage.total_tokens

            # Extract finish reason
            finish_reason = None
            if response.choices and len(response.choices) > 0:
                finish_reason = response.choices[0].finish_reason

            return ModelResponse(
                content=content,
                model=self.model,
                provider=self.get_provider_name(),
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                metadata={
                    "finish_reason": finish_reason,
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                    "completion_tokens": response.usage.completion_tokens if response.usage else None,
                },
                raw_response=response,
            )

        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}") from e

    def get_provider_name(self) -> str:
        """Get provider name."""
        return "openai"
