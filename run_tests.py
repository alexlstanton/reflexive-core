#!/usr/bin/env python3
"""
Main test execution script for Reflexive-Core testbed.

Runs security tests against LLM models using the Reflexive-Core framework,
analyzes responses, and generates comprehensive reports.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src/ to import path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from analyzers import (
    ConfidenceValidator,
    PersonaSimilarityAnalyzer,
    XMLParser,
)
from models import (
    BaseAdapter,
    ClaudeAdapter,
    GeminiAdapter,
    ModelResponse,
    OpenAIAdapter,
)


@dataclass
class TestResult:
    """Result from a single test case execution."""

    test_id: str
    test_name: str
    model: str
    provider: str
    success: bool
    response: str
    persona_detected: str | None
    confidence: float | None
    expected_persona: str
    similarity_score: float | None
    latency_ms: float | None
    tokens_used: int | None
    errors: list[str]
    timestamp: str


@dataclass
class TestSummary:
    """Summary statistics for test execution."""

    total_tests: int
    passed: int
    failed: int
    success_rate: float
    avg_latency_ms: float
    total_tokens: int
    avg_confidence: float
    timestamp: str


class ReflexiveCoreTestRunner:
    """Test runner for Reflexive-Core security framework."""

    def __init__(
        self,
        framework_xml_path: str = "framework/reflexive-core-debug.xml",
        test_cases_path: str = "tests/test_cases.json",
        verbose: bool = False,
    ) -> None:
        """
        Initialize test runner.

        Args:
            framework_xml_path: Path to Reflexive-Core framework XML
            test_cases_path: Path to test cases JSON
            verbose: Enable verbose logging
        """
        self.framework_xml_path = framework_xml_path
        self.test_cases_path = test_cases_path
        self.verbose = verbose

        # Initialize components
        # Note: XMLParser doesn't need framework file - it parses LLM responses
        self.xml_parser = XMLParser()
        self.confidence_validator = ConfidenceValidator()
        self.similarity_analyzer = PersonaSimilarityAnalyzer() if PersonaSimilarityAnalyzer else None

        # Console for rich output
        self.console = Console()

        # Setup logging
        self._setup_logging()

        # Load test cases
        self.test_cases = self._load_test_cases()

        # Results storage
        self.results: list[TestResult] = []

    def _setup_logging(self) -> None:
        """Setup logging configuration."""
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

    def _load_test_cases(self) -> list[dict[str, Any]]:
        """
        Load test cases from JSON file.

        Returns:
            List of test case dictionaries

        Raises:
            FileNotFoundError: If test cases file not found
        """
        try:
            with open(self.test_cases_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("test_cases", [])
        except FileNotFoundError:
            self.logger.error(f"Test cases file not found: {self.test_cases_path}")
            raise

    def _create_adapter(self, model_type: str) -> BaseAdapter:
        """
        Create model adapter based on type.

        Args:
            model_type: Type of model (claude, openai, gemini)

        Returns:
            Initialized adapter instance

        Raises:
            ValueError: If model type is invalid or API key missing
        """
        model_type = model_type.lower()

        if model_type == "claude":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in environment")
            model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
            return ClaudeAdapter(api_key=api_key, model=model)

        elif model_type == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment")
            model = os.getenv("OPENAI_MODEL", "gpt-5")
            return OpenAIAdapter(api_key=api_key, model=model)

        elif model_type == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found in environment")
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro-latest")
            return GeminiAdapter(api_key=api_key, model=model)

        else:
            raise ValueError(f"Unknown model type: {model_type}")

    async def _run_single_test(
        self,
        test_case: dict[str, Any],
        adapter: BaseAdapter,
    ) -> TestResult:
        """
        Run a single test case.

        Args:
            test_case: Test case dictionary
            adapter: Model adapter to use

        Returns:
            TestResult object
        """
        test_id = test_case.get("id", "unknown")
        test_name = test_case.get("name", "Unnamed Test")
        user_input = test_case.get("user_input", "")
        tool_data = test_case.get("tool_data", "")
        expected_persona = test_case.get("expected_persona", "")
        expected_phase = test_case.get("expected_phase", "")
        expected_behavior = test_case.get("expected_behavior", "")  # Maps to decision field

        errors: list[str] = []

        try:
            # Load framework XML as system prompt
            system_prompt = None
            if os.path.exists(self.framework_xml_path):
                with open(self.framework_xml_path, "r", encoding="utf-8") as f:
                    system_prompt = f.read()

            # Construct tagged user message for Reflexive-Core framework
            user_message = f"""<rc:user:{test_id}>
{user_input}
</rc:user:{test_id}>

<rc:tool:{test_id}>
{tool_data}
</rc:tool:{test_id}>"""

            # Generate response
            response: ModelResponse = await adapter.generate(
                prompt=user_message,
                system_prompt=system_prompt,
            )

            # Parse XML response
            parsed = self.xml_parser.parse_response(response.content)

            # Validate structure
            is_valid, validation_errors = self.xml_parser.validate_response_structure(parsed)
            if not is_valid:
                errors.extend(validation_errors)

            # Validate confidence
            if parsed.confidence is not None:
                if not self.confidence_validator.is_valid(parsed.confidence):
                    errors.append(f"Invalid confidence: {parsed.confidence}")

            # Validate expected_persona match
            if expected_persona and parsed.persona != expected_persona:
                errors.append(f"Persona mismatch: expected '{expected_persona}', got '{parsed.persona}'")

            # Validate expected_phase match
            if expected_phase and parsed.phase != expected_phase:
                errors.append(f"Phase mismatch: expected '{expected_phase}', got '{parsed.phase}'")

            # Validate expected_behavior (maps to decision field)
            if expected_behavior and parsed.decision != expected_behavior:
                errors.append(f"Decision mismatch: expected '{expected_behavior}', got '{parsed.decision}'")

            # Compute similarity (legacy - for backward compatibility)
            similarity_score = None
            if expected_persona:
                similarity_score = 1.0 if parsed.persona == expected_persona else 0.0

            # Determine success
            success = len(errors) == 0 and parsed.is_valid()

            return TestResult(
                test_id=test_id,
                test_name=test_name,
                model=adapter.model,
                provider=adapter.get_provider_name(),
                success=success,
                response=response.content,
                persona_detected=parsed.persona,
                confidence=parsed.confidence,
                expected_persona=expected_persona,
                similarity_score=similarity_score,
                latency_ms=response.latency_ms,
                tokens_used=response.tokens_used,
                errors=errors,
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            self.logger.error(f"Error running test {test_id}: {e}")
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                model=adapter.model,
                provider=adapter.get_provider_name(),
                success=False,
                response="",
                persona_detected=None,
                confidence=None,
                expected_persona=expected_persona,
                similarity_score=None,
                latency_ms=None,
                tokens_used=None,
                errors=[str(e)],
                timestamp=datetime.now().isoformat(),
            )

    async def run_tests(
        self,
        model_type: str,
        test_filter: str | None = None,
    ) -> list[TestResult]:
        """
        Run all tests for a specific model.

        Args:
            model_type: Type of model to test
            test_filter: Optional filter for test IDs

        Returns:
            List of test results
        """
        # Display framework mode
        mode_indicator = "PROD" if "prod" in self.framework_xml_path.lower() else "DEBUG"
        mode_color = "green" if mode_indicator == "PROD" else "yellow"

        self.console.print(f"\n[bold blue]Running tests for {model_type}...[/bold blue]")
        self.console.print(f"[{mode_color}]Framework Mode: {mode_indicator} ({self.framework_xml_path})[/{mode_color}]")

        # Create adapter
        adapter = self._create_adapter(model_type)

        # Filter test cases
        tests_to_run = self.test_cases
        if test_filter:
            tests_to_run = [
                tc for tc in self.test_cases
                if test_filter in tc.get("id", "")
            ]

        # Run tests with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task(
                f"Running {len(tests_to_run)} tests...",
                total=len(tests_to_run),
            )

            results: list[TestResult] = []
            for test_case in tests_to_run:
                result = await self._run_single_test(test_case, adapter)
                results.append(result)
                progress.advance(task)

                if self.verbose:
                    status = "✓" if result.success else "✗"
                    self.console.print(
                        f"  {status} {result.test_id}: {result.test_name}"
                    )

        self.results.extend(results)
        return results

    def generate_summary(self, results: list[TestResult]) -> TestSummary:
        """
        Generate summary statistics from results.

        Args:
            results: List of test results

        Returns:
            TestSummary object
        """
        total = len(results)
        passed = sum(1 for r in results if r.success)
        failed = total - passed

        # Calculate averages
        latencies = [r.latency_ms for r in results if r.latency_ms is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        tokens = [r.tokens_used for r in results if r.tokens_used is not None]
        total_tokens = sum(tokens)

        confidences = [r.confidence for r in results if r.confidence is not None]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        success_rate = (passed / total * 100) if total > 0 else 0.0

        return TestSummary(
            total_tests=total,
            passed=passed,
            failed=failed,
            success_rate=success_rate,
            avg_latency_ms=avg_latency,
            total_tokens=total_tokens,
            avg_confidence=avg_confidence,
            timestamp=datetime.now().isoformat(),
        )

    def print_summary(self, summary: TestSummary) -> None:
        """
        Print summary table.

        Args:
            summary: TestSummary object
        """
        table = Table(title="Test Summary")

        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Tests", str(summary.total_tests))
        table.add_row("Passed", str(summary.passed))
        table.add_row("Failed", str(summary.failed))
        table.add_row("Success Rate", f"{summary.success_rate:.1f}%")
        table.add_row("Avg Latency", f"{summary.avg_latency_ms:.0f} ms")
        table.add_row("Total Tokens", str(summary.total_tokens))
        table.add_row("Avg Confidence", f"{summary.avg_confidence:.2f}")

        self.console.print("\n")
        self.console.print(table)

    def save_results(self, output_path: str) -> None:
        """
        Save results to JSON file.

        Args:
            output_path: Path to output file
        """
        output_data = {
            "results": [asdict(r) for r in self.results],
            "summary": asdict(self.generate_summary(self.results)),
        }

        # Create directory if needed
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)

        self.console.print(f"\n[green]Results saved to {output_path}[/green]")


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run Reflexive-Core security tests"
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["claude", "openai", "gemini", "all"],
        default="all",
        help="Model to test",
    )
    parser.add_argument(
        "--filter",
        type=str,
        help="Filter tests by ID substring",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output path for results JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Use production mode (reflexive-core-prod.xml) with minimal token responses",
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Determine framework file based on mode
    framework_file = "framework/reflexive-core-prod.xml" if args.prod else "framework/reflexive-core-debug.xml"

    # Create test runner
    runner = ReflexiveCoreTestRunner(
        framework_xml_path=framework_file,
        verbose=args.verbose
    )

    # Run tests
    try:
        if args.model == "all":
            for model in ["claude", "openai", "gemini"]:
                try:
                    await runner.run_tests(model, args.filter)
                except ValueError as e:
                    runner.console.print(f"[yellow]Skipping {model}: {e}[/yellow]")
        else:
            await runner.run_tests(args.model, args.filter)

        # Generate and print summary
        summary = runner.generate_summary(runner.results)
        runner.print_summary(summary)

        # Save results if output specified
        if args.output:
            runner.save_results(args.output)
        else:
            # Default output location
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_output = f"data/results/test_run_{timestamp}.json"
            runner.save_results(default_output)

        # Return exit code based on success
        return 0 if summary.success_rate == 100.0 else 1

    except Exception as e:
        runner.console.print(f"[bold red]Error: {e}[/bold red]")
        runner.logger.exception("Test execution failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
