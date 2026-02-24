"""
LLM Model Adapters for Reflexive-Core Testing

This package provides unified interfaces for interacting with different LLM providers
while testing the Reflexive-Core security framework.
"""

from .base_adapter import BaseAdapter, ModelResponse
from .claude_adapter import ClaudeAdapter
from .openai_adapter import OpenAIAdapter
from .gemini_adapter import GeminiAdapter

__all__ = [
    "BaseAdapter",
    "ModelResponse",
    "ClaudeAdapter",
    "OpenAIAdapter",
    "GeminiAdapter",
]
