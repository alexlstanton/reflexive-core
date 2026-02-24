"""
Anthropic Claude adapter implementation.

Provides interface to Claude models via the Anthropic API,
with prompt caching support for Reflexive-Core framework.
"""

import os
import time
from typing import Any

import httpx
from anthropic import AsyncAnthropic

from .base_adapter import BaseAdapter, ModelResponse


class ClaudeAdapter(BaseAdapter):
    """Adapter for Anthropic Claude models."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: int = 60,
        enable_cache: bool = True,
    ) -> None:
        """
        Initialize Claude adapter.

        Args:
            api_key: Anthropic API key
            model: Claude model identifier
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            timeout: Request timeout in seconds
            enable_cache: Enable prompt caching for system prompts
        """
        super().__init__(api_key, model, max_tokens, temperature, timeout)
        self.enable_cache = enable_cache

        # Build client kwargs, handling proxy environments (e.g., sandboxed VMs)
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout,
        }

        # If HTTP(S) proxy is set and ALL_PROXY is SOCKS (common in sandboxes),
        # create an explicit httpx client with the HTTP proxy and skip SSL
        # verification for self-signed proxy certs.
        http_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        all_proxy = os.environ.get("ALL_PROXY", "")
        if http_proxy and "socks" in all_proxy.lower():
            # Remove SOCKS proxy so httpx doesn't try to use it
            os.environ.pop("ALL_PROXY", None)
            os.environ.pop("all_proxy", None)
            client_kwargs["http_client"] = httpx.AsyncClient(
                proxy=http_proxy,
                verify=False,
            )

        self.client = AsyncAnthropic(**client_kwargs)

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        """
        Generate a response from Claude.

        When enable_cache=True, the system prompt is sent with
        cache_control to enable Anthropic's prompt caching. This
        means the framework XML is cached server-side and subsequent
        calls only pay for cache reads, not full re-processing.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            ModelResponse with Claude's response and cache metrics

        Raises:
            ValueError: If prompt is invalid
            Exception: API errors
        """
        self.validate_prompt(prompt)

        start_time = time.perf_counter()

        try:
            # Build message list
            messages: list[dict[str, str]] = [
                {"role": "user", "content": prompt}
            ]

            # Build system prompt with optional cache control
            system: Any = ""
            if system_prompt:
                if self.enable_cache:
                    # Use structured format with cache_control
                    # This tells Anthropic to cache the system prompt
                    system = [{
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }]
                else:
                    system = system_prompt

            # Call Claude API
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=messages,
            )

            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000

            # Extract content
            content = ""
            if response.content:
                # Handle both text and tool use content blocks
                for block in response.content:
                    if hasattr(block, "text"):
                        content += block.text

            # Extract token usage including cache metrics
            tokens_used = None
            metadata: dict[str, Any] = {
                "stop_reason": response.stop_reason,
            }

            if response.usage:
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                tokens_used = input_tokens + output_tokens

                metadata["input_tokens"] = input_tokens
                metadata["output_tokens"] = output_tokens

                # Cache metrics (available when prompt caching is used)
                cache_creation = getattr(response.usage, "cache_creation_input_tokens", None)
                cache_read = getattr(response.usage, "cache_read_input_tokens", None)

                metadata["cache_creation_input_tokens"] = cache_creation or 0
                metadata["cache_read_input_tokens"] = cache_read or 0

                # Determine cache status
                if cache_read and cache_read > 0:
                    metadata["cache_status"] = "hit"
                elif cache_creation and cache_creation > 0:
                    metadata["cache_status"] = "created"
                else:
                    metadata["cache_status"] = "none"

            return ModelResponse(
                content=content,
                model=self.model,
                provider=self.get_provider_name(),
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                metadata=metadata,
                raw_response=response,
            )

        except Exception as e:
            raise Exception(f"Claude API error: {str(e)}") from e

    def get_provider_name(self) -> str:
        """Get provider name."""
        return "anthropic"
