"""
LM Studio adapter for local OpenAI-compatible servers.

Targets the LM Studio server's /v1/chat/completions endpoint. Reuses the
AsyncOpenAI client from OpenAIAdapter with a base_url override.

Handles the reasoning-model response shape (e.g. Gemma 4) where the model
emits a separate `reasoning_content` field alongside `content`. The
user-facing `content` is returned as ModelResponse.content; the internal
monologue is preserved in metadata for inspection.
"""

import os
import time
from typing import Any

from openai import AsyncOpenAI

from .base_adapter import ModelResponse
from .openai_adapter import OpenAIAdapter


class LMStudioAdapter(OpenAIAdapter):
    """Adapter for LM Studio local server (OpenAI-compatible)."""

    DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str = "lm-studio",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: int = 120,
    ) -> None:
        # Skip OpenAIAdapter.__init__ — it instantiates AsyncOpenAI without
        # a base_url. Call BaseAdapter directly via grandparent then build
        # our own client.
        from .base_adapter import BaseAdapter
        BaseAdapter.__init__(
            self,
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        self.base_url = base_url or os.getenv("LM_STUDIO_BASE_URL", self.DEFAULT_BASE_URL)
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        self.validate_prompt(prompt)
        start_time = time.perf_counter()

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000

        content = ""
        reasoning_content = ""
        finish_reason = None
        if response.choices:
            choice = response.choices[0]
            content = choice.message.content or ""
            reasoning_content = getattr(choice.message, "reasoning_content", "") or ""
            finish_reason = choice.finish_reason

        # ModelResponse rejects empty content. For reasoning models that
        # exhausted their budget mid-thought, fall back to reasoning_content
        # so downstream parsers still get something to inspect.
        effective_content = content if content else (
            reasoning_content if reasoning_content else "[empty response]"
        )

        tokens_used = response.usage.total_tokens if response.usage else None
        prompt_tokens = response.usage.prompt_tokens if response.usage else None
        completion_tokens = response.usage.completion_tokens if response.usage else None
        reasoning_tokens = None
        if response.usage and hasattr(response.usage, "completion_tokens_details"):
            details = response.usage.completion_tokens_details
            if details is not None:
                reasoning_tokens = getattr(details, "reasoning_tokens", None)

        return ModelResponse(
            content=effective_content,
            model=self.model,
            provider=self.get_provider_name(),
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            metadata={
                "finish_reason": finish_reason,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "reasoning_tokens": reasoning_tokens,
                "reasoning_content": reasoning_content,
                "content_empty": not content,
                "base_url": self.base_url,
            },
            raw_response=response,
        )

    def get_provider_name(self) -> str:
        return "lmstudio"
