"""
Persona similarity analysis for Reflexive-Core responses.

Analyzes how closely LLM responses match expected Reflexive-Core persona behavior
using semantic similarity and keyword matching.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class SimilarityScore:
    """Similarity score result."""

    semantic_similarity: float
    keyword_match_score: float
    overall_score: float
    matched_keywords: list[str]
    missing_keywords: list[str]
    metadata: dict[str, Any]


class PersonaSimilarityAnalyzer:
    """Analyzer for comparing responses to expected persona behavior."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> None:
        """
        Initialize persona similarity analyzer.

        Args:
            model_name: Sentence transformer model name
            semantic_weight: Weight for semantic similarity (0-1)
            keyword_weight: Weight for keyword matching (0-1)
        """
        if not 0 <= semantic_weight <= 1 or not 0 <= keyword_weight <= 1:
            raise ValueError("Weights must be between 0 and 1")

        if abs(semantic_weight + keyword_weight - 1.0) > 1e-6:
            raise ValueError("Weights must sum to 1.0")

        self.model = SentenceTransformer(model_name)
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight

    def compute_semantic_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """
        Compute semantic similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        if not text1 or not text2:
            return 0.0

        # Generate embeddings
        embeddings = self.model.encode([text1, text2])

        # Compute cosine similarity
        similarity_matrix = cosine_similarity(
            embeddings[0].reshape(1, -1),
            embeddings[1].reshape(1, -1),
        )

        return float(similarity_matrix[0][0])

    def extract_keywords(self, text: str) -> set[str]:
        """
        Extract keywords from text (simple implementation).

        Args:
            text: Text to extract keywords from

        Returns:
            Set of keywords
        """
        # Simple keyword extraction - lowercase, split, filter short words
        words = text.lower().split()
        keywords = {
            word.strip(".,!?;:")
            for word in words
            if len(word) > 3 and word.isalpha()
        }

        return keywords

    def compute_keyword_similarity(
        self,
        text1: str,
        text2: str,
    ) -> tuple[float, list[str], list[str]]:
        """
        Compute keyword-based similarity.

        Args:
            text1: First text
            text2: Second text (expected/reference)

        Returns:
            Tuple of (score, matched_keywords, missing_keywords)
        """
        keywords1 = self.extract_keywords(text1)
        keywords2 = self.extract_keywords(text2)

        if not keywords2:
            return 0.0, [], []

        # Find matches
        matched = keywords1.intersection(keywords2)
        missing = keywords2.difference(keywords1)

        # Compute score (Jaccard similarity)
        score = len(matched) / len(keywords2) if keywords2 else 0.0

        return score, sorted(matched), sorted(missing)

    def analyze_similarity(
        self,
        response_text: str,
        expected_text: str,
        expected_keywords: list[str] | None = None,
    ) -> SimilarityScore:
        """
        Analyze similarity between response and expected text.

        Args:
            response_text: LLM response text
            expected_text: Expected persona response
            expected_keywords: Optional list of expected keywords

        Returns:
            SimilarityScore object with analysis results
        """
        # Compute semantic similarity
        semantic_sim = self.compute_semantic_similarity(
            response_text,
            expected_text,
        )

        # Compute keyword similarity
        keyword_sim, matched, missing = self.compute_keyword_similarity(
            response_text,
            expected_text,
        )

        # If specific keywords provided, check those
        if expected_keywords:
            response_keywords = self.extract_keywords(response_text)
            expected_set = {kw.lower() for kw in expected_keywords}

            matched_from_list = [
                kw for kw in expected_keywords
                if kw.lower() in response_keywords
            ]
            missing_from_list = [
                kw for kw in expected_keywords
                if kw.lower() not in response_keywords
            ]

            # Override with provided keywords
            matched = matched_from_list
            missing = missing_from_list
            keyword_sim = len(matched) / len(expected_keywords) if expected_keywords else 0.0

        # Compute overall score
        overall = (
            self.semantic_weight * semantic_sim +
            self.keyword_weight * keyword_sim
        )

        return SimilarityScore(
            semantic_similarity=semantic_sim,
            keyword_match_score=keyword_sim,
            overall_score=overall,
            matched_keywords=matched,
            missing_keywords=missing,
            metadata={
                "semantic_weight": self.semantic_weight,
                "keyword_weight": self.keyword_weight,
            },
        )

    def compare_personas(
        self,
        response_persona: str,
        expected_persona: str,
    ) -> bool:
        """
        Compare persona identifiers.

        Args:
            response_persona: Persona from response
            expected_persona: Expected persona

        Returns:
            True if personas match
        """
        if not response_persona or not expected_persona:
            return False

        # Normalize and compare
        return response_persona.lower().strip() == expected_persona.lower().strip()

    def batch_analyze(
        self,
        responses: list[str],
        expected: list[str],
    ) -> list[SimilarityScore]:
        """
        Analyze similarity for multiple response-expected pairs.

        Args:
            responses: List of response texts
            expected: List of expected texts

        Returns:
            List of SimilarityScore objects
        """
        if len(responses) != len(expected):
            raise ValueError("responses and expected must have same length")

        results: list[SimilarityScore] = []

        for resp, exp in zip(responses, expected):
            score = self.analyze_similarity(resp, exp)
            results.append(score)

        return results

    def compute_aggregate_metrics(
        self,
        scores: list[SimilarityScore],
    ) -> dict[str, float]:
        """
        Compute aggregate metrics from multiple similarity scores.

        Args:
            scores: List of SimilarityScore objects

        Returns:
            Dictionary of aggregate metrics
        """
        if not scores:
            return {
                "mean_semantic": 0.0,
                "mean_keyword": 0.0,
                "mean_overall": 0.0,
                "std_semantic": 0.0,
                "std_keyword": 0.0,
                "std_overall": 0.0,
            }

        semantic_scores = [s.semantic_similarity for s in scores]
        keyword_scores = [s.keyword_match_score for s in scores]
        overall_scores = [s.overall_score for s in scores]

        semantic_arr: NDArray[np.floating[Any]] = np.array(semantic_scores, dtype=float)
        keyword_arr: NDArray[np.floating[Any]] = np.array(keyword_scores, dtype=float)
        overall_arr: NDArray[np.floating[Any]] = np.array(overall_scores, dtype=float)

        return {
            "mean_semantic": float(np.mean(semantic_arr)),
            "mean_keyword": float(np.mean(keyword_arr)),
            "mean_overall": float(np.mean(overall_arr)),
            "std_semantic": float(np.std(semantic_arr)),
            "std_keyword": float(np.std(keyword_arr)),
            "std_overall": float(np.std(overall_arr)),
            "min_overall": float(np.min(overall_arr)),
            "max_overall": float(np.max(overall_arr)),
        }
