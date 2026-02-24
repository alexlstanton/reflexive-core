"""
Analysis and validation tools for Reflexive-Core testing.

This package provides utilities for analyzing LLM responses,
validating confidence scores, and parsing XML structures.
"""

from .confidence_validator import ConfidenceValidator
from .xml_parser import XMLParser, ReflexiveCoreResponse

# PersonaSimilarityAnalyzer requires sentence-transformers and scikit-learn,
# which are heavy optional dependencies. Import lazily to avoid breaking
# the core framework when they're not installed.
try:
    from .persona_similarity import PersonaSimilarityAnalyzer
except ImportError:
    PersonaSimilarityAnalyzer = None  # type: ignore[assignment, misc]

__all__ = [
    "PersonaSimilarityAnalyzer",
    "ConfidenceValidator",
    "XMLParser",
    "ReflexiveCoreResponse",
]
