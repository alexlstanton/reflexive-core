# Reflexive-Core Research

**Experimental metacognitive security framework for LLM-based systems**

This repository contains research on using multi-persona prompt architecture to detect security threats in LLM interactions. The framework has been tested against 20 security test cases on Claude Sonnet 4.5.

**Status**: Early research / experimental. Not claiming production-ready.

---

## What is This?

Reflexive-Core is an XML-based system prompt that creates multiple security "personas" to analyze user requests before execution. The idea is that different personas with different threat models might catch threats that a single-perspective prompt would miss.

**Key concepts:**
- Multi-persona architecture (4 personas with different expertise)
- Phase-based processing (6 stages from defense to final decision)
- Adaptive verbosity (minimal JSON for routine, full JSON for threats)
- Early detection (try to catch threats in first phase when possible)

**Two frameworks included:**
- `reflexive-core-prod.xml` - Optimized version with adaptive verbosity
- `reflexive_core.xml` - Verbose version with detailed logging

---

## Test Results (Claude Sonnet 4.5)

Tested on October 25, 2025 using `claude-sonnet-4-5-20250929`:

| Framework | Tests Passed | Avg Latency | Avg Tokens |
|-----------|--------------|-------------|------------|
| **Production** | 20/20 (100%) | 10.7s | 5,556 |
| **Debug** | 19/20 (95%) | 21.6s | 5,872 |

**Test categories (20 total):**
- Jailbreak attempts (2)
- Prompt injection (2)
- Social engineering (2)
- Obfuscation (1)
- Email content injection (3)
- Persona redirection (2)
- Sensitive data handling (2)
- Policy violations (2)
- Legitimate operations (2)
- Edge cases (2)

See [data/results/comparison/V23_FINAL_RESULTS.md](data/results/comparison/V23_FINAL_RESULTS.md) for detailed results.

---

## Quick Start

### Prerequisites

```bash
pip install anthropic
export ANTHROPIC_API_KEY='your-key-here'
```

### Run Tests

```bash
# Test production framework
python3 run_tests.py --model claude --prod

# Test debug framework
python3 run_tests.py --model claude --verbose

# Save results to file
python3 run_tests.py --model claude --prod --output my_results.json
```

### Basic Usage

```python
from anthropic import Anthropic
import json

# Load framework
with open('reflexive-core-prod.xml', 'r') as f:
    framework = f.read()

client = Anthropic()

response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=4000,
    system=[{"type": "text", "text": framework, "cache_control": {"type": "ephemeral"}}],
    messages=[{"role": "user", "content": "Summarize my emails about Q4 planning"}]
)

result = json.loads(response.content[0].text)
print(result['decision'])  # APPROVED, BLOCKED, or REVIEW_REQUIRED
```

---

## Testing on Other Models

Want to test on GPT-4, Gemini, or other models? The testbed supports multiple providers:

```bash
# Test on OpenAI models (requires OPENAI_API_KEY)
python3 run_tests.py --model openai

# Test on Google Gemini (requires GEMINI_API_KEY)
python3 run_tests.py --model gemini
```

**Note**: The framework XML was designed for Claude. Results on other models are unknown and would be interesting to compare!

---

## Adding Your Own Tests

Tests are defined in `tests/test_cases.json`. Add a new test:

```json
{
  "id": "your_test_001",
  "name": "Your Test Name",
  "user_input": "The user's request text",
  "tool_data": "Optional email/data content",
  "attack_type": "jailbreak|prompt_injection|social_engineering|policy_violation|none",
  "severity": "critical|high|medium|low|none",
  "expected_persona": "Preflight Analyst|Security Analyst|Controlled Executor|Compliance Validator",
  "expected_phase": "preflight|prescan|execution|assurance",
  "expected_behavior": "APPROVED|BLOCKED|REVIEW_REQUIRED",
  "expected_keywords": ["keyword1", "keyword2"],
  "min_confidence": 0.85
}
```

Then run:
```bash
python3 run_tests.py --model claude --prod
```

---

## Architecture

### 4 Personas

| Persona | Threat Model | Role |
|---------|--------------|------|
| **Preflight Analyst** | ADVERSARIAL | Policy/scope validation (catches ~75% of threats here) |
| **Security Analyst** | PARANOID | Deep security analysis (credentials, injection patterns) |
| **Controlled Executor** | SERVICE-ORIENTED | Safe task execution |
| **Compliance Validator** | SKEPTICAL | Output validation (PII redaction, leak detection) |

### 6 Processing Phases

```
USER REQUEST
  ↓
[DEFENSE] - Initialize threat context
  ↓
[PREFLIGHT] - Quick policy/scope check (most threats caught here)
  ↓
[PRESCAN] - Deep security analysis
  ↓
[EXECUTION] - Task execution (if approved)
  ↓
[ASSURANCE] - Output validation
  ↓
[FINAL] - Decision synthesis
```

### Adaptive Verbosity

- **MINIMAL mode**: Returns just `{decision, confidence, user_response}` for approved requests
- **FULL mode**: Returns complete JSON with `{decision, confidence, persona, phase, risk_summary, threat_indicators, reasoning, user_response}` for blocked/review-required

This reduces token usage for routine operations while providing full detail for security events.

---

## A2AS Integration (Optional)

The framework can work with Agent-to-Agent Security (A2AS) primitives:

```xml
<a2as:defense>
  <!-- reflexive-core XML here -->
</a2as:defense>

<a2as:policy>
  <!-- organization policy XML -->
</a2as:policy>
```

But it also works standalone - the A2AS tags are optional.

---

## Key Design Decisions

### 1. Credentials in Code → Always BLOCKED

The framework takes a paranoid stance: any credentials in code (even test data) are blocked entirely, not just redacted. Rationale: displaying code with hardcoded credentials normalizes dangerous practices.

**Distinction:**
- Credentials in code → BLOCKED
- PII in legitimate emails → APPROVED with [REDACTED] tokens

### 2. Early Detection Preferred

If a threat can be caught in Preflight (phase 1), it should be - no need to run all 6 phases. This is why ~75% of threats are caught early.

### 3. Expertise-Based, Not Rule-Based

The framework relies on the LLM's baked-in security knowledge rather than explicit if-then rules. The XML provides structure and context, but doesn't micromanage decisions.

---

## Known Issues

- **Debug framework**: Has one failure (sensitive_001) where it incorrectly approves hardcoded API keys. Production framework doesn't have this issue.
- **Model-specific**: Only tested on Claude Sonnet 4.5. Behavior on other models unknown.
- **English only**: Framework operates in English.

---

## Files

```
.
├── reflexive-core-prod.xml           # Production framework
├── reflexive_core.xml                # Debug framework (verbose)
├── tests/test_cases.json             # 20 test cases (v2.3)
├── run_tests.py                      # Test runner
├── CHANGELOG.md                      # Version history
└── data/results/
    ├── prod_final_run_20251025.json  # Latest production test run
    └── comparison/                    # Detailed analysis docs
```

---

## Reproducing Results

```bash
# 1. Clone and setup
git clone <this-repo>
cd reflexive-core-testbed
pip install -r requirements.txt

# 2. Set API key
export ANTHROPIC_API_KEY='your-key'

# 3. Run tests
python3 run_tests.py --model claude --prod --output my_test_run.json

# 4. Compare with our results
diff my_test_run.json data/results/prod_final_run_20251025.json
```

---

## Questions to Explore

Some interesting research directions:

1. **Cross-model comparison**: How do GPT-4, Gemini, Claude 3.5 Sonnet compare on the same test suite?
2. **Attack taxonomy**: What threat categories are missing from the test suite?
3. **False positive rate**: Need more benign test cases to measure false positive rate thoroughly
4. **Prompt engineering**: Can simpler prompts achieve similar results? Is the complexity necessary?
5. **Adversarial testing**: Can we find attacks that bypass all personas?
6. **Token efficiency**: What's the minimum viable framework (fewer personas/phases)?

---

## License

Dual-licensed: Apache 2.0 or MIT (your choice)

---

## Contact

For questions or collaboration: security@thinkpurple.com

---

**This is research/experimental work. Use at your own risk. Contributions and feedback welcome!**
