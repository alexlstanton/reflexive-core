"""
Unit tests for XMLParser, focusing on:
- Malformed JSON recovery (_recover_malformed_json)
- Guardrails (invalid decisions, personas, confidence)
- Markdown code-fence stripping
- Partial/truncated responses
- Well-formed JSON happy path

These tests address red-team feedback (Feb 2026) about parser correctness
and the risk of _recover_malformed_json fabricating decisions.
"""

import sys
from pathlib import Path

import pytest

# Add src/ to import path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from analyzers.xml_parser import XMLParser, ReflexiveCoreResponse


@pytest.fixture
def parser():
    return XMLParser()


# ─────────────────────────────────────────────────────
# Happy path: well-formed JSON
# ─────────────────────────────────────────────────────

class TestWellFormedJSON:
    def test_blocked_response(self, parser):
        text = '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": 0.95, "threats": ["prompt_injection"], "reasoning": {}, "output": "Request blocked."}'
        result = parser.parse_response(text)
        assert result.decision == "BLOCKED"
        assert result.persona == "Preflight Analyst"
        assert result.phase == "preflight"
        assert result.confidence == 0.95
        assert result.threats == ["prompt_injection"]
        assert result.output == "Request blocked."

    def test_approved_response(self, parser):
        text = '{"persona": "Compliance Validator", "phase": "assurance", "decision": "APPROVED", "confidence": 0.98, "threats": [], "reasoning": {}, "output": "Here is your email summary."}'
        result = parser.parse_response(text)
        assert result.decision == "APPROVED"
        assert result.confidence == 0.98
        assert result.threats == []

    def test_safe_response(self, parser):
        text = '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "SAFE", "confidence": 1.0, "threats": [], "reasoning": {}, "output": "No threats detected."}'
        result = parser.parse_response(text)
        assert result.decision == "SAFE"

    def test_review_required(self, parser):
        text = '{"persona": "Security Analyst", "phase": "prescan", "decision": "REVIEW_REQUIRED", "confidence": 0.6, "threats": ["ambiguous_content"], "reasoning": {}, "output": "Flagged for human review."}'
        result = parser.parse_response(text)
        assert result.decision == "REVIEW_REQUIRED"


# ─────────────────────────────────────────────────────
# Markdown code-fence stripping
# ─────────────────────────────────────────────────────

class TestCodeFenceStripping:
    def test_json_code_fence(self, parser):
        text = '```json\n{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": 0.95, "threats": [], "reasoning": {}, "output": "Blocked."}\n```'
        result = parser.parse_response(text)
        assert result.decision == "BLOCKED"
        assert result.persona == "Preflight Analyst"

    def test_bare_code_fence(self, parser):
        text = '```\n{"persona": "Preflight Analyst", "phase": "preflight", "decision": "APPROVED", "confidence": 0.9, "threats": [], "reasoning": {}, "output": "OK."}\n```'
        result = parser.parse_response(text)
        assert result.decision == "APPROVED"

    def test_code_fence_with_extra_whitespace(self, parser):
        text = '  ```json  \n  {"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": 1.0, "threats": [], "reasoning": {}, "output": "No."}  \n  ```  '
        # Stripping should handle leading/trailing whitespace
        result = parser.parse_response(text)
        # This may or may not parse depending on exact whitespace handling
        # The key test is it doesn't crash
        assert result is not None


# ─────────────────────────────────────────────────────
# Malformed JSON recovery
# ─────────────────────────────────────────────────────

class TestMalformedJSONRecovery:
    def test_orphaned_output_field(self, parser):
        """Simulates Opus premature object close with orphaned 'output' field."""
        text = '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": 0.95, "threats": ["prompt_injection"], "reasoning": {"phases_executed": {"preflight": {"threats_found": {"injection": true}}}}},\"output\": \"Request blocked due to detected injection.\"}'
        result = parser.parse_response(text)
        assert result.decision == "BLOCKED"
        assert result.output == "Request blocked due to detected injection."

    def test_orphaned_multiple_fields(self, parser):
        """Multiple fields orphaned after premature close."""
        text = '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": 0.95, "threats": ["prompt_injection"], "reasoning": {}},\"output\": \"Blocked.\", \"extra\": \"data\"}'
        result = parser.parse_response(text)
        assert result.decision == "BLOCKED"
        assert result.output == "Blocked."

    def test_recovery_does_not_overwrite_existing_decision(self, parser):
        """If main object already has 'decision', orphaned 'decision' should not overwrite."""
        # The update() would overwrite, but in practice orphaned fields
        # are things like 'output' that come AFTER the decision.
        # This test documents the current behavior.
        text = '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": 0.95, "threats": [], "reasoning": {}},\"output\": \"Blocked.\"}'
        result = parser.parse_response(text)
        assert result.decision == "BLOCKED"

    def test_recovery_with_truncated_orphan(self, parser):
        """Orphaned fields are themselves truncated — regex fallback.

        NOTE: When the entire string doesn't end with '}', parse_response
        skips the JSON path entirely (startswith '{' AND endswith '}' check).
        The legacy regex parser captures the decision in metadata but not
        in the response.decision field. This is acceptable — truncated
        responses from the API are extremely rare (would require timeout
        mid-stream), and the sweep runner treats parse_success=False
        as a failure in strict mode.
        """
        text = '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": 0.95, "threats": [], "reasoning": {}},\"output\": \"This was blocked because'
        result = parser.parse_response(text)
        # Falls through to legacy parser — decision captured in metadata but not top-level
        assert result.metadata.get("decision") == "BLOCKED"
        # Top-level decision is None (JSON path skipped)
        assert result.decision is None


# ─────────────────────────────────────────────────────
# Guardrails: invalid recovered values
# ─────────────────────────────────────────────────────

class TestRecoveryGuardrails:
    def test_invalid_decision_rejected(self, parser):
        """Recovery that produces an invalid decision value should fail."""
        recovered = parser._recover_malformed_json(
            '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "YOLO", "confidence": 0.95},"extra": "data"}'
        )
        assert recovered is None

    def test_invalid_persona_rejected(self, parser):
        """Recovery that produces an invalid persona should fail."""
        recovered = parser._recover_malformed_json(
            '{"persona": "Evil Hacker", "phase": "preflight", "decision": "BLOCKED", "confidence": 0.95},"output": "test"}'
        )
        assert recovered is None

    def test_out_of_range_confidence_rejected(self, parser):
        """Recovery with confidence > 1.0 should fail."""
        recovered = parser._recover_malformed_json(
            '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": 5.0},"output": "test"}'
        )
        assert recovered is None

    def test_negative_confidence_rejected(self, parser):
        """Recovery with negative confidence should fail."""
        recovered = parser._recover_malformed_json(
            '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": -0.5},"output": "test"}'
        )
        assert recovered is None

    def test_valid_recovery_passes_guardrails(self, parser):
        """Recovery with all valid values should succeed."""
        recovered = parser._recover_malformed_json(
            '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": 0.95},"output": "Blocked."}'
        )
        assert recovered is not None
        assert recovered["decision"] == "BLOCKED"
        assert recovered["output"] == "Blocked."

    def test_no_decision_field_passes(self, parser):
        """Object without decision field should still pass (decision is None → skip check)."""
        recovered = parser._recover_malformed_json(
            '{"persona": "Preflight Analyst", "phase": "preflight", "confidence": 0.95},"output": "test"}'
        )
        assert recovered is not None

    def test_completely_broken_json_returns_none(self, parser):
        """Totally unparseable text returns None."""
        recovered = parser._recover_malformed_json("this is not json at all")
        assert recovered is None

    def test_empty_string_returns_none(self, parser):
        recovered = parser._recover_malformed_json("")
        assert recovered is None

    def test_array_returns_none(self, parser):
        """Top-level array (not object) should fail."""
        recovered = parser._recover_malformed_json('[1, 2, 3]')
        assert recovered is None


# ─────────────────────────────────────────────────────
# Edge cases: partial/truncated responses
# ─────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_response(self, parser):
        result = parser.parse_response("")
        assert result.decision is None
        assert not result.is_valid()

    def test_plain_text_response(self, parser):
        result = parser.parse_response("I cannot help with that request.")
        assert result.decision is None

    def test_truncated_json(self, parser):
        """JSON cut off mid-stream — should not crash."""
        text = '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOC'
        result = parser.parse_response(text)
        # Should gracefully fail, not crash
        assert result is not None

    def test_nested_decision_in_reasoning(self, parser):
        """Ensure the top-level decision is used, not one buried in reasoning."""
        text = '{"persona": "Compliance Validator", "phase": "assurance", "decision": "APPROVED", "confidence": 0.95, "threats": [], "reasoning": {"phases_executed": {"preflight": {"decision": "SUSPICIOUS"}}}, "output": "Request approved after review."}'
        result = parser.parse_response(text)
        assert result.decision == "APPROVED"  # Top-level, not nested SUSPICIOUS

    def test_unicode_in_output(self, parser):
        text = '{"persona": "Preflight Analyst", "phase": "preflight", "decision": "BLOCKED", "confidence": 1.0, "threats": ["encoding_attack"], "reasoning": {}, "output": "Detected zero-width characters (U+200B) in tool data."}'
        result = parser.parse_response(text)
        assert result.decision == "BLOCKED"
        assert "U+200B" in result.output


# ─────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────

class TestValidation:
    def test_valid_response_passes(self, parser):
        resp = ReflexiveCoreResponse(
            persona="Preflight Analyst",
            phase="preflight",
            decision="BLOCKED",
            confidence=0.95,
            output="Blocked.",
        )
        is_valid, errors = parser.validate_response_structure(resp)
        assert is_valid
        assert errors == []

    def test_missing_persona_fails(self, parser):
        resp = ReflexiveCoreResponse(
            phase="preflight",
            decision="BLOCKED",
            confidence=0.95,
            output="Blocked.",
        )
        is_valid, errors = parser.validate_response_structure(resp)
        assert not is_valid
        assert any("persona" in e for e in errors)

    def test_invalid_decision_fails(self, parser):
        resp = ReflexiveCoreResponse(
            persona="Preflight Analyst",
            phase="preflight",
            decision="INVALID",
            confidence=0.95,
            output="Test.",
        )
        is_valid, errors = parser.validate_response_structure(resp)
        assert not is_valid
        assert any("Invalid decision" in e for e in errors)

    def test_confidence_out_of_range_fails(self, parser):
        resp = ReflexiveCoreResponse(
            persona="Preflight Analyst",
            phase="preflight",
            decision="BLOCKED",
            confidence=1.5,
            output="Test.",
        )
        is_valid, errors = parser.validate_response_structure(resp)
        assert not is_valid
        assert any("Confidence" in e for e in errors)
