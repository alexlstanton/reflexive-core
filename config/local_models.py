"""
Dependency-free registry of local LM Studio models.

Both run_sweep.py (RC venv) and garak/run_garak.py (GARAK venv) import
from here. Keeping this module free of any third-party imports means it
can be loaded from either environment without dragging in stack-specific
deps like lxml or torch.
"""

from __future__ import annotations

LOCAL_MODELS: dict[str, dict[str, object]] = {
    "gemma4-e4b": {
        "provider": "lmstudio",
        "model_id": "google/gemma-4-e4b",
        "display_name": "Gemma 4 E4B",
        "generation": "4",
        "tier": "small",
        "cost_per_mtok_input": 0.0,
        "cost_per_mtok_output": 0.0,
        "cost_per_mtok_cache_write": 0.0,
        "cost_per_mtok_cache_read": 0.0,
    },
    "gemma4-26b": {
        "provider": "lmstudio",
        "model_id": "google/gemma-4-26b-a4b-qat",
        "display_name": "Gemma 4 26B-a4b-QAT",
        "generation": "4",
        "tier": "medium",
        "cost_per_mtok_input": 0.0,
        "cost_per_mtok_output": 0.0,
        "cost_per_mtok_cache_write": 0.0,
        "cost_per_mtok_cache_read": 0.0,
    },
    "qwen36-27b": {
        "provider": "lmstudio",
        "model_id": "qwen/qwen3.6-27b",
        "display_name": "Qwen 3.6 27B",
        "generation": "3.6",
        "tier": "medium",
        "cost_per_mtok_input": 0.0,
        "cost_per_mtok_output": 0.0,
        "cost_per_mtok_cache_write": 0.0,
        "cost_per_mtok_cache_read": 0.0,
    },
}
