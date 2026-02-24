"""
Google Gemini adapter implementation.

Provides interface to Google Gemini models via the Google AI API.
"""

import time
from typing import Any

import google.generativeai as genai

from .base_adapter import BaseAdapter, ModelResponse


class GeminiAdapter(BaseAdapter):
    """Adapter for Google Gemini models."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-pro-latest",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: int = 30,
    ) -> None:
        """
        Initialize Gemini adapter.

        Args:
            api_key: Google AI API key
            model: Gemini model identifier
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            timeout: Request timeout in seconds
        """
        super().__init__(api_key, model, max_tokens, temperature, timeout)

        # Configure API key
        genai.configure(api_key=api_key)

        # Store model name for later initialization with system instruction
        self.model_name = model

        # Generation config
        self.generation_config = genai.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        # Model will be initialized per-request with system instruction
        self.genai_model = None

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        """
        Generate a response from Gemini.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt (via system_instruction)

        Returns:
            ModelResponse with Gemini's response

        Raises:
            ValueError: If prompt is invalid
            Exception: API errors
        """
        self.validate_prompt(prompt)

        start_time = time.perf_counter()

        try:
            # Initialize model with system instruction if provided
            if system_prompt:
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=system_prompt,
                )
            else:
                model = genai.GenerativeModel(model_name=self.model_name)

            # Generate response
            response = await model.generate_content_async(
                prompt,
                generation_config=self.generation_config,
            )

            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000

            # Extract content
            content = ""
            if response.text:
                content = response.text

            # Extract token usage
            tokens_used = None
            if hasattr(response, "usage_metadata"):
                tokens_used = (
                    response.usage_metadata.prompt_token_count +
                    response.usage_metadata.candidates_token_count
                )

            # Extract metadata
            metadata: dict[str, Any] = {}
            if hasattr(response, "usage_metadata"):
                metadata["prompt_tokens"] = response.usage_metadata.prompt_token_count
                metadata["completion_tokens"] = response.usage_metadata.candidates_token_count

            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                metadata["finish_reason"] = candidate.finish_reason.name if hasattr(
                    candidate.finish_reason, "name"
                ) else str(candidate.finish_reason)

                # Safety ratings
                if hasattr(candidate, "safety_ratings"):
                    metadata["safety_ratings"] = [
                        {
                            "category": rating.category.name if hasattr(rating.category, "name") else str(rating.category),
                            "probability": rating.probability.name if hasattr(rating.probability, "name") else str(rating.probability),
                        }
                        for rating in candidate.safety_ratings
                    ]

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
            raise Exception(f"Gemini API error: {str(e)}") from e

    def get_provider_name(self) -> str:
        """Get provider name."""
        return "google"
