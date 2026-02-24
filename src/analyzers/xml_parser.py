"""
XML parsing utilities for Reflexive-Core responses.

Extracts and validates XML-structured responses from LLM outputs,
including persona information, confidence scores, and structured data.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from lxml import etree


@dataclass
class ReflexiveCoreResponse:
    """Parsed Reflexive-Core response structure (new format)."""

    # Top-level fields from new JSON schema
    persona: str | None = None          # Decision-maker persona
    phase: str | None = None            # Phase where decision was made
    decision: str | None = None         # SAFE|SUSPICIOUS|BLOCKED|APPROVED|REVIEW_REQUIRED
    confidence: float | None = None     # Decision-maker's confidence
    threats: list[str] = field(default_factory=list)  # All threats detected
    output: str | None = None           # Final user-facing message

    # Legacy fields for backward compatibility
    severity: str | None = None         # Deprecated: use decision instead
    threat_type: str | None = None      # Deprecated: use threats list instead
    message: str | None = None          # Deprecated: use output instead

    # Raw response and metadata
    raw_xml: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if response has minimum required fields for A2AS."""
        # New format requires: persona, phase, decision, confidence
        # Allow legacy validation for backward compatibility
        has_new_fields = (
            self.persona is not None
            and self.phase is not None
            and self.decision is not None
            and self.confidence is not None
        )
        has_legacy_fields = self.persona is not None or self.confidence is not None
        return has_new_fields or has_legacy_fields


class XMLParser:
    """Parser for extracting and validating XML from LLM responses."""

    def __init__(self, framework_xml_path: str | None = None) -> None:
        """
        Initialize XML parser.

        Args:
            framework_xml_path: Optional path to Reflexive-Core framework XML
        """
        self.framework_xml_path = framework_xml_path
        self.framework_tree: etree._Element | None = None

        if framework_xml_path:
            self.load_framework(framework_xml_path)

    def load_framework(self, xml_path: str) -> None:
        """
        Load Reflexive-Core framework XML.

        Args:
            xml_path: Path to framework XML file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If XML is malformed
        """
        try:
            with open(xml_path, "r", encoding="utf-8") as f:
                xml_content = f.read()
                self.framework_tree = etree.fromstring(xml_content.encode("utf-8"))
        except FileNotFoundError:
            raise FileNotFoundError(f"Framework XML not found: {xml_path}")
        except etree.XMLSyntaxError as e:
            raise ValueError(
                f"Invalid XML in framework file '{xml_path}': {str(e)}\n"
                f"Hint: XML comments cannot contain double hyphens (--) except in closing tag (-->)"
            )

    def extract_xml_from_text(self, text: str) -> list[str]:
        """
        Extract XML blocks from text.

        Args:
            text: Text potentially containing XML

        Returns:
            List of extracted XML strings
        """
        # Pattern to match XML declarations and root elements
        patterns = [
            r"<\?xml[^>]*\?>.*?</[^>]+>",  # Full XML with declaration
            r"<reflexive-core[^>]*>.*?</reflexive-core>",  # Reflexive-core tags
            r"<response[^>]*>.*?</response>",  # Generic response tags
            r"<analysis[^>]*>.*?</analysis>",  # Analysis tags
        ]

        xml_blocks: list[str] = []

        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            xml_blocks.extend(matches)

        return xml_blocks

    def parse_response(self, text: str) -> ReflexiveCoreResponse:
        """
        Parse Reflexive-Core A2AS response (JSON or legacy XML format).

        Args:
            text: Text containing A2AS response (JSON or XML)

        Returns:
            ReflexiveCoreResponse object with extracted data
        """
        response = ReflexiveCoreResponse()
        response.raw_xml = text

        # Try parsing as pure JSON first (new output_protocol format)
        try:
            # Strip any whitespace and markdown code blocks
            text_stripped = text.strip()

            # Remove markdown code block syntax if present
            # Matches: ```json\n{...}\n``` or ```\n{...}\n```
            json_block_pattern = r'^```(?:json)?\s*\n?(.*?)\n?```$'
            match = re.match(json_block_pattern, text_stripped, re.DOTALL)
            if match:
                text_stripped = match.group(1).strip()

            # Try to parse as JSON
            if text_stripped.startswith('{') and text_stripped.endswith('}'):
                data = json.loads(text_stripped)
                return self._parse_json_response(data, text)
        except json.JSONDecodeError:
            # Handle malformed JSON from deeply nested model responses.
            # Models sometimes lose track of brace depth in complex reasoning
            # structures, causing the top-level object to close prematurely
            # while orphaning trailing fields like "output".
            if text_stripped.startswith('{'):
                data = self._recover_malformed_json(text_stripped)
                if data is not None:
                    return self._parse_json_response(data, text)
            # Fall back to XML/hybrid parsing

        # Legacy parsing: Look for assurance_output JSON embedded in XML
        assurance_pattern = r'<assurance_output>\s*(\{[^}]*\})\s*</assurance_output>'
        assurance_match = re.search(assurance_pattern, text, re.DOTALL | re.IGNORECASE)

        if assurance_match:
            try:
                # Extract and clean the JSON
                json_str = assurance_match.group(1)
                # Handle potential formatting issues
                json_str = re.sub(r'\s+', ' ', json_str)  # Normalize whitespace
                assurance_data = json.loads(json_str)

                # Extract confidence from JSON
                response.confidence = assurance_data.get("overall_confidence")

                # Extract threat level as severity
                response.severity = assurance_data.get("threat_level")

                # Extract decision
                decision = assurance_data.get("decision")
                response.metadata["decision"] = decision

                # Store all assurance data in metadata
                response.metadata.update(assurance_data)

            except (json.JSONDecodeError, AttributeError) as e:
                # If JSON parsing fails, continue with text extraction
                pass

        # Determine active persona based on which phases executed
        # Supports both legacy <a2as:> and current <rc:> tag prefixes
        if "<rc:preflight>" in text or "<a2as:preflight>" in text:
            response.persona = "Preflight Analyst"
        elif "<rc:pre_scan>" in text or "<a2as:pre_scan>" in text:
            response.persona = "Security Analyst"
        elif "<rc:execution>" in text or "<a2as:execution>" in text:
            response.persona = "Controlled Executor"
        elif "<rc:assurance>" in text or "<a2as:assurance>" in text:
            response.persona = "Compliance Validator"

        # Extract decision from checkpoint or final
        decision_patterns = [
            r'DECISION:\s*(\w+)',
            r'"decision":\s*"(\w+)"',
            r'<FINAL_(\w+)>',
        ]

        for pattern in decision_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                decision_value = match.group(1).upper()
                if "decision" not in response.metadata:
                    response.metadata["decision"] = decision_value
                break

        # Extract threat types from analysis
        threat_patterns = [
            r'Role_confusion:\s*(\w+)',
            r'Override_attempts:\s*(\w+)',
            r'Privilege_escalation:\s*(\w+)',
        ]

        threats_detected = []
        for pattern in threat_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and match.group(1).lower() == 'yes':
                threat_name = pattern.split(':')[0].replace('\\s*', '').replace('\\w+', '')
                threats_detected.append(threat_name)

        if threats_detected:
            response.threat_type = ", ".join(threats_detected)

        # Extract message from FINAL blocks
        final_patterns = [
            r'<FINAL_BLOCKED>\s*(.*?)\s*</FINAL_BLOCKED>',
            r'<FINAL_APPROVED>\s*(.*?)\s*</FINAL_APPROVED>',
            r'<FINAL_REVIEW_REQUIRED>\s*(.*?)\s*</FINAL_REVIEW_REQUIRED>',
        ]

        for pattern in final_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                response.message = match.group(1).strip()[:500]  # First 500 chars
                break

        return response

    def _recover_malformed_json(self, text: str) -> dict[str, Any] | None:
        """
        Recover JSON from malformed model responses.

        RESEARCH FINDING (Feb 2026 sweep):
        Opus-tier models (4.5, 4.6) occasionally produce structurally
        malformed JSON when generating deeply nested reasoning structures.
        The pattern: the model generates the "reasoning.phases_executed.
        preflight.threats_found" object with quoted attack payloads and
        detailed analysis, accumulating 4-5 levels of nested braces.
        When closing this structure, the model emits too many closing
        braces (}}}}), prematurely terminating the top-level JSON object.
        The trailing "output" field then appears *after* the object close
        as orphaned content: }}},"output":"Request blocked..."}

        This appears correlated with our multi-persona gatekeeping exit
        structure — the framework asks models to produce a single JSON
        response containing nested per-phase reasoning, each with its
        own sub-objects for threats, policy checks, and confidence
        breakdowns. When a BLOCKED decision triggers detailed preflight
        reporting (with verbatim threat quotes), the resulting structure
        pushes models past the nesting depth where they reliably track
        brace parity.

        Observed: 2/22 Opus 4.5 responses, 2/21 Opus 4.6 responses.
        Not observed in any Sonnet responses (Sonnet wraps in markdown
        code blocks which may provide additional structural scaffolding).

        This recovery method uses incremental JSON decoding to extract
        the main object and merge orphaned fields back in.

        Args:
            text: JSON-like string that failed json.loads()

        Returns:
            Recovered dict or None if recovery fails
        """
        # Valid values for guardrail validation after recovery
        valid_decisions = {"SAFE", "SUSPICIOUS", "BLOCKED", "APPROVED", "REVIEW_REQUIRED"}
        valid_personas = {
            "Preflight Analyst", "Security Analyst",
            "Controlled Executor", "Compliance Validator",
        }

        try:
            decoder = json.JSONDecoder()
            obj, end_idx = decoder.raw_decode(text)

            if not isinstance(obj, dict):
                return None

            remaining = text[end_idx:].strip()

            # If remaining starts with comma, there are orphaned fields
            if remaining.startswith(','):
                # Wrap orphaned fields into a JSON object
                patched = '{' + remaining[1:]
                if not patched.endswith('}'):
                    patched += '}'
                try:
                    extra = json.loads(patched)
                    obj.update(extra)
                except json.JSONDecodeError:
                    # Orphaned fields themselves may be truncated.
                    # Try to extract at least the key decision fields.
                    for field_name in ['output', 'decision', 'confidence', 'persona']:
                        pattern = rf'"{field_name}"\s*:\s*("(?:[^"\\]|\\.)*"|[\d.]+|true|false|null)'
                        match = re.search(pattern, remaining)
                        if match and field_name not in obj:
                            val_str = match.group(1)
                            try:
                                obj[field_name] = json.loads(val_str)
                            except json.JSONDecodeError:
                                pass

            # ── Guardrails: validate recovered data ──
            # If we recovered a decision, it must be in the valid set.
            # Otherwise the recovery fabricated garbage → reject.
            recovered_decision = obj.get("decision")
            if recovered_decision is not None and recovered_decision not in valid_decisions:
                return None  # Invalid decision → recovery failed

            recovered_persona = obj.get("persona")
            if recovered_persona is not None and recovered_persona not in valid_personas:
                return None  # Invalid persona → recovery failed

            recovered_confidence = obj.get("confidence")
            if recovered_confidence is not None:
                try:
                    conf_val = float(recovered_confidence)
                    if not (0.0 <= conf_val <= 1.0):
                        return None  # Out-of-range confidence → recovery failed
                except (TypeError, ValueError):
                    return None

            return obj

        except (json.JSONDecodeError, ValueError):
            return None

    def _parse_json_response(self, data: dict[str, Any], raw_text: str) -> ReflexiveCoreResponse:
        """
        Parse JSON-formatted A2AS response (new output_format).

        New format structure:
        {
          "persona": "Decision-maker persona",
          "phase": "Decision phase",
          "decision": "SAFE|SUSPICIOUS|BLOCKED|APPROVED|REVIEW_REQUIRED",
          "confidence": 0.00-1.00,
          "threats": ["array"],
          "reasoning": {
            "decision_phase": "string",
            "decision_persona": "string",
            "phases_executed": {}
          },
          "output": "Final message"
        }

        Args:
            data: Parsed JSON dictionary
            raw_text: Original response text

        Returns:
            ReflexiveCoreResponse object
        """
        response = ReflexiveCoreResponse()
        response.raw_xml = raw_text

        # Extract new top-level fields
        response.persona = data.get("persona")
        response.phase = data.get("phase")
        response.decision = data.get("decision")
        response.confidence = data.get("confidence")

        # Extract threats and ensure they're strings
        threats_raw = data.get("threats", [])
        if isinstance(threats_raw, list):
            response.threats = [str(t) if not isinstance(t, str) else t for t in threats_raw]
        else:
            response.threats = []

        response.output = data.get("output")

        # Also populate legacy fields for backward compatibility
        response.message = response.output  # Legacy alias
        if response.threats:
            response.threat_type = ", ".join(response.threats)  # Legacy format

        # Map decision to legacy severity field
        decision_to_severity = {
            "BLOCKED": "high",
            "REVIEW_REQUIRED": "medium",
            "SUSPICIOUS": "medium",
            "APPROVED": "low",
            "SAFE": "low"
        }
        if response.decision:
            response.severity = decision_to_severity.get(response.decision, "medium")

        # Extract reasoning section
        reasoning = data.get("reasoning", {})
        response.metadata["decision_phase"] = reasoning.get("decision_phase")
        response.metadata["decision_persona"] = reasoning.get("decision_persona")

        # Store phases_executed (this replaces old "phases" structure)
        phases_executed = reasoning.get("phases_executed", {})
        response.metadata["phases_executed"] = phases_executed

        # For backward compatibility, also store as "phases"
        response.metadata["phases"] = phases_executed

        # Store complete JSON data for debugging
        response.metadata["json_response"] = data

        return response

    def validate_response_structure(
        self,
        response: ReflexiveCoreResponse,
    ) -> tuple[bool, list[str]]:
        """
        Validate A2AS response structure (new format).

        New format requires:
        - persona: Decision-maker persona
        - phase: Decision phase
        - decision: SAFE|SUSPICIOUS|BLOCKED|APPROVED|REVIEW_REQUIRED
        - confidence: 0.0-1.0 (NEVER 0.0 except system errors)

        Args:
            response: Parsed response to validate

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors: list[str] = []

        # Validate required fields for new format
        if not response.persona:
            errors.append("Response missing 'persona' field (decision-maker)")

        if not response.phase:
            errors.append("Response missing 'phase' field (decision point)")

        if not response.decision:
            errors.append("Response missing 'decision' field")

        if response.confidence is None:
            errors.append("Response missing 'confidence' field")

        # Validate confidence range and usage
        if response.confidence is not None:
            if not 0.0 <= response.confidence <= 1.0:
                errors.append(f"Confidence {response.confidence} outside valid range [0.0, 1.0]")

            # Warning: 0.0 should only be used for system errors per new framework
            if response.confidence == 0.0 and response.decision in ["BLOCKED", "REVIEW_REQUIRED"]:
                response.metadata["confidence_warning"] = (
                    "Confidence 0.0 detected. Per new framework, confident blocks should use 1.0; "
                    "0.0 reserved for system errors only."
                )

        # Validate persona values
        if response.persona:
            valid_personas = [
                "Preflight Analyst",
                "Security Analyst",
                "Controlled Executor",
                "Compliance Validator"
            ]
            if response.persona not in valid_personas:
                errors.append(f"Invalid persona: '{response.persona}'. Must be one of {valid_personas}")

        # Validate phase values
        if response.phase:
            valid_phases = ["preflight", "prescan", "execution", "assurance"]
            if response.phase not in valid_phases:
                errors.append(f"Invalid phase: '{response.phase}'. Must be one of {valid_phases}")

        # Validate decision values
        if response.decision:
            valid_decisions = ["SAFE", "SUSPICIOUS", "BLOCKED", "APPROVED", "REVIEW_REQUIRED"]
            if response.decision not in valid_decisions:
                errors.append(f"Invalid decision: '{response.decision}'. Must be one of {valid_decisions}")

        # Validate output exists
        if not response.output:
            errors.append("Response missing 'output' field (final user message)")

        return len(errors) == 0, errors

    def get_framework_personas(self) -> list[dict[str, Any]]:
        """
        Extract persona definitions from framework.

        Returns:
            List of persona definitions with metadata
        """
        if self.framework_tree is None:
            return []

        personas: list[dict[str, Any]] = []

        for persona_elem in self.framework_tree.findall(".//persona"):
            persona: dict[str, Any] = {
                "id": persona_elem.get("id"),
                "priority": persona_elem.get("priority"),
            }

            # Extract description
            desc_elem = persona_elem.find("description")
            if desc_elem is not None and desc_elem.text:
                persona["description"] = desc_elem.text.strip()

            # Extract triggers
            triggers = []
            for trigger_elem in persona_elem.findall(".//trigger"):
                trigger = {
                    "type": trigger_elem.get("type"),
                    "confidence": float(trigger_elem.get("confidence", 0.0)),
                }
                triggers.append(trigger)

            if triggers:
                persona["triggers"] = triggers

            personas.append(persona)

        return personas
