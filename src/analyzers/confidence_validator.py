"""
Confidence score validation and analysis.

Validates confidence scores from Reflexive-Core responses,
checks for consistency, and provides statistical analysis.
"""

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numpy.typing import NDArray


@dataclass
class ConfidenceMetrics:
    """Statistical metrics for confidence scores."""

    mean: float
    median: float
    std: float
    min: float
    max: float
    count: int
    valid_count: int
    invalid_count: int
    out_of_range_count: int


class ConfidenceValidator:
    """Validator for Reflexive-Core confidence scores."""

    def __init__(
        self,
        min_confidence: float = 0.0,
        max_confidence: float = 1.0,
        warning_threshold: float = 0.5,
    ) -> None:
        """
        Initialize confidence validator.

        Args:
            min_confidence: Minimum valid confidence value
            max_confidence: Maximum valid confidence value
            warning_threshold: Threshold for low confidence warnings
        """
        if min_confidence >= max_confidence:
            raise ValueError("min_confidence must be less than max_confidence")

        self.min_confidence = min_confidence
        self.max_confidence = max_confidence
        self.warning_threshold = warning_threshold

    def is_valid(self, confidence: float | None) -> bool:
        """
        Check if confidence score is valid.

        Args:
            confidence: Confidence score to validate

        Returns:
            True if valid, False otherwise
        """
        if confidence is None:
            return False

        return self.min_confidence <= confidence <= self.max_confidence

    def is_in_range(self, confidence: float) -> bool:
        """
        Check if confidence is within expected range.

        Args:
            confidence: Confidence score to check

        Returns:
            True if in range, False otherwise
        """
        return self.min_confidence <= confidence <= self.max_confidence

    def needs_warning(self, confidence: float) -> bool:
        """
        Check if confidence is below warning threshold.

        Args:
            confidence: Confidence score to check

        Returns:
            True if below threshold, False otherwise
        """
        return confidence < self.warning_threshold

    def validate_batch(
        self,
        confidences: Sequence[float | None],
    ) -> tuple[list[bool], list[str]]:
        """
        Validate a batch of confidence scores.

        Args:
            confidences: Sequence of confidence scores

        Returns:
            Tuple of (validity_list, error_messages)
        """
        results: list[bool] = []
        errors: list[str] = []

        for i, conf in enumerate(confidences):
            if conf is None:
                results.append(False)
                errors.append(f"Index {i}: Confidence is None")
            elif not self.is_valid(conf):
                results.append(False)
                if not self.is_in_range(conf):
                    errors.append(
                        f"Index {i}: Confidence {conf} out of range "
                        f"[{self.min_confidence}, {self.max_confidence}]"
                    )
                else:
                    errors.append(f"Index {i}: Invalid confidence value {conf}")
            else:
                results.append(True)

        return results, errors

    def compute_metrics(
        self,
        confidences: Sequence[float | None],
    ) -> ConfidenceMetrics:
        """
        Compute statistical metrics for confidence scores.

        Args:
            confidences: Sequence of confidence scores

        Returns:
            ConfidenceMetrics object with statistics
        """
        # Filter valid values
        valid_values: list[float] = [
            c for c in confidences if c is not None and self.is_valid(c)
        ]

        invalid_count = len([c for c in confidences if c is None])
        out_of_range = len([
            c for c in confidences
            if c is not None and not self.is_in_range(c)
        ])

        if not valid_values:
            return ConfidenceMetrics(
                mean=0.0,
                median=0.0,
                std=0.0,
                min=0.0,
                max=0.0,
                count=len(confidences),
                valid_count=0,
                invalid_count=invalid_count,
                out_of_range_count=out_of_range,
            )

        arr: NDArray[np.floating[Any]] = np.array(valid_values, dtype=float)

        return ConfidenceMetrics(
            mean=float(np.mean(arr)),
            median=float(np.median(arr)),
            std=float(np.std(arr)),
            min=float(np.min(arr)),
            max=float(np.max(arr)),
            count=len(confidences),
            valid_count=len(valid_values),
            invalid_count=invalid_count,
            out_of_range_count=out_of_range,
        )

    def detect_anomalies(
        self,
        confidences: Sequence[float],
        std_threshold: float = 2.0,
    ) -> list[int]:
        """
        Detect anomalous confidence scores using standard deviation.

        Args:
            confidences: Sequence of confidence scores
            std_threshold: Number of standard deviations for anomaly detection

        Returns:
            List of indices with anomalous values
        """
        if len(confidences) < 3:
            return []

        arr: NDArray[np.floating[Any]] = np.array(confidences, dtype=float)
        mean = np.mean(arr)
        std = np.std(arr)

        if std == 0:
            return []

        anomalies: list[int] = []
        for i, conf in enumerate(confidences):
            z_score = abs((conf - mean) / std)
            if z_score > std_threshold:
                anomalies.append(i)

        return anomalies

    def compare_confidences(
        self,
        confidence1: float,
        confidence2: float,
        threshold: float = 0.1,
    ) -> tuple[bool, float]:
        """
        Compare two confidence scores.

        Args:
            confidence1: First confidence score
            confidence2: Second confidence score
            threshold: Maximum acceptable difference

        Returns:
            Tuple of (are_similar, difference)
        """
        diff = abs(confidence1 - confidence2)
        are_similar = diff <= threshold

        return are_similar, diff

    def get_confidence_level(self, confidence: float) -> str:
        """
        Categorize confidence score into levels.

        Args:
            confidence: Confidence score

        Returns:
            Confidence level as string (low/medium/high/very_high)
        """
        if confidence < 0.3:
            return "low"
        elif confidence < 0.6:
            return "medium"
        elif confidence < 0.85:
            return "high"
        else:
            return "very_high"
