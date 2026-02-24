# Reflexive-Core

**Single-Context Metacognitive Security for Agentic LLMs**

Reflexive-Core is a structured in-context security architecture that transforms how LLMs reason about threats. Instead of relying on passive safety markup that models may inconsistently follow, it partitions inference into four specialized sub-personas — Preflight Analyst, Security Analyst, Controlled Executor, and Compliance Validator — each with explicit checkpoints, fail-closed defaults, and constitutional principles. All within a single context window. No external dependencies.

**Website:** [alexlstanton.github.io/reflexive-core](https://alexlstanton.github.io/reflexive-core/) | **Paper:** [Read online](https://alexlstanton.github.io/reflexive-core/paper/v2-february-2026/reflexive_core_publication_v2.html) &#183; [PDF](https://alexlstanton.github.io/reflexive-core/paper/v2-february-2026/reflexive_core_publication_v2.pdf)

---

## Key Results (February 2026)

Evaluated across 4 Claude model variants on a 28-case test suite spanning 13 attack categories:

| Model | Strict Accuracy | Safety-Acceptable | False Positives | Cost (28 cases) |
|-------|----------------|-------------------|-----------------|-----------------|
| **Sonnet 4.5** | 100.0% | 100.0% | 0/4 | $0.31 |
| **Sonnet 4.6** | 96.4% | 100.0% | 0/4 | $0.33 |
| **Opus 4.5** | 89.3% | 96.4% | 0/4 | $1.20 |
| **Opus 4.6** | 96.4% | 100.0% | 0/4 | $0.51 |

**Baseline comparison** (same prompts, no framework): model-native safety training permits **data leakage in 58% of attack cases** — often through a "comply-then-warn" pattern where the model begins fulfilling a malicious request before catching itself. The framework eliminates this entirely: **0% data leakage across all 4 models**.

With prompt caching, per-evaluation cost is approximately **$0.01 at the Sonnet tier**.

Full results: [Test Results Supplement](https://alexlstanton.github.io/reflexive-core/paper/v2-february-2026/test_results_supplement.html) &#183; [PDF](https://alexlstanton.github.io/reflexive-core/paper/v2-february-2026/test_results_supplement.pdf)

---

## Quick Start

### Prerequisites

```bash
pip install anthropic python-dotenv
cp .env.example .env
# Edit .env with your Anthropic API key
```

### Basic Usage

```python
from anthropic import Anthropic

# Load framework
with open('framework/reflexive-core-prod.xml', 'r') as f:
    framework = f.read()

client = Anthropic()

response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=4096,
    system=[{"type": "text", "text": framework, "cache_control": {"type": "ephemeral"}}],
    messages=[{"role": "user", "content": "Summarize my emails about Q4 planning"}]
)

import json
result = json.loads(response.content[0].text)
print(result['decision'])  # APPROVED, BLOCKED, or REVIEW_REQUIRED
```

### Run the Evaluation Suite

```bash
# Strict mode (publishable results, no bypasses)
python run_sweep.py --models sonnet45 --strict

# Baseline mode (no framework, tests model-native safety)
python run_sweep.py --models sonnet45 --baseline

# Full 4-model sweep
python run_sweep.py --strict
```

Results are saved as timestamped JSON in `data/results/` with full per-case details.

---

## Architecture

Reflexive-Core executes as a strictly ordered routine within one context window:

```
USER REQUEST
  ↓
[DEFENSE]    → Input validation layer (rc:defense)
  ↓
[PREFLIGHT]  → Preflight Analyst: "Is this obviously malicious?"
  ↓            Checkpoint: SAFE | SUSPICIOUS | BLOCKED
[PRESCAN]    → Security Analyst (optional): "What sensitive data needs protection?"
  ↓            Checkpoint: PROCEED | REVIEW | BLOCK
[EXECUTION]  → Controlled Executor: "Can I do this within policy?"
  ↓
[ASSURANCE]  → Compliance Validator: "Does output meet requirements?"
  ↓            Confidence scores + decision
[FINAL]      → Gate: APPROVE | REVIEW | BLOCK
```

Each persona has distinct expertise, explicit checkpoints, and fail-closed defaults. Missing or malformed checkpoints default to BLOCKED. The full audit trail is preserved in the model's output.

---

## Repository Structure

```
reflexive-core/
├── framework/
│   ├── reflexive-core-prod.xml          # Production framework (v1.1)
│   └── reflexive-core-debug.xml         # Debug framework (verbose logging)
├── tests/
│   ├── test_cases.json                  # Test suite v3.2 (28 cases, 13 categories)
│   └── test_xml_parser.py              # Parser unit tests (29 tests)
├── src/
│   ├── analyzers/
│   │   ├── xml_parser.py               # Response parser with malformed JSON recovery
│   │   ├── confidence_validator.py     # Confidence score validation
│   │   └── persona_similarity.py       # Persona similarity analysis
│   └── models/
│       ├── claude_adapter.py           # Anthropic Claude adapter
│       ├── openai_adapter.py           # OpenAI adapter (future)
│       └── gemini_adapter.py           # Google Gemini adapter (future)
├── data/results/
│   ├── sweep_sonnet45_strict_v1.1_28cases.json
│   ├── sweep_sonnet46_strict_v1.1_28cases.json
│   ├── sweep_opus45_strict_v1.1_28cases.json
│   ├── sweep_opus46_strict_v1.1_28cases.json
│   ├── sweep_sonnet45_baseline_v1.1.json
│   └── february-2026-v1.0/             # Archived v1.0 results
├── docs/
│   ├── index.html                          # Project website (GitHub Pages)
│   └── paper/
│       ├── v2-february-2026/
│       │   ├── reflexive_core_publication_v2.html
│       │   ├── reflexive_core_publication_v2.pdf
│       │   ├── test_results_supplement.html
│       │   └── test_results_supplement.pdf
│       └── v1-october-2025/            # Archived v1 paper
├── examples/
│   └── enterprise_wrapper.py           # Example integration
├── run_sweep.py                        # Evaluation runner (--strict, --baseline)
├── run_tests.py                        # Legacy test runner
├── METHODOLOGY.md                      # Testing methodology & scoring
├── CHANGELOG.md                        # Version history
├── CONTRIBUTING.md                     # Contribution guide
├── SECURITY.md                         # Vulnerability reporting
├── requirements.txt                    # Python dependencies
└── LICENSE                             # Apache 2.0
```

---

## How It Works

The framework is grounded in three lines of research:

1. **LLM Metacognition** (Ackerman 2025): Frontier models show partial but measurable metacognitive capabilities (r=0.2–0.3 confidence–behavior correlations). Reflexive-Core provides explicit structures that harvest these limited capabilities and fail safely when absent.

2. **Solo Performance Prompting** (Wang et al. 2023): A single LLM adopting multiple specialized personas achieves +7–18% accuracy gains on GPT-4. Reflexive-Core applies this cognitive synergy to security reasoning.

3. **Constitutional AI** (Bai et al. 2022): Models can self-critique against written principles. Each Reflexive-Core persona applies constitutional principles (authenticity, least privilege, transparency, privacy) from its specialized perspective.

---

## Applicability

Reflexive-Core works in any scenario where an LLM processes potentially untrusted content through a system prompt:

- Enterprise email agents
- Document analysis pipelines
- Agentic tool-use platforms
- Custom agents built in orchestration tools (N8N, Copilot Studio, LangChain)
- Multi-agent systems
- Any system that can set a system prompt and parse model output

The framework is compatible with — but does not require — deterministic intermediary layers (agentgateway, custom middleware, API wrappers). It does not replace or interfere with identity verification, cryptographic signatures, or external access control.

---

## Known Limitations

- **28 test cases** is a preliminary evaluation, not statistically robust coverage
- **Single-run evaluation** (n=1, temperature=0.7) — multi-run confidence intervals are planned
- **Claude-only validation** — cross-family generalization (GPT, Gemini, Grok) remains untested
- **4 benign cases** is insufficient for production false-positive rate claims
- **Single-context architecture** has inherent limits against determined adversaries

See the [paper](https://alexlstanton.github.io/reflexive-core/paper/v2-february-2026/reflexive_core_publication_v2.html) Section 7.3.6 for full limitations discussion.

---

## Background

The single-context security problem was first articulated by the [A2AS](https://a2as.org) (Agent-to-Agent Security) initiative in fall 2025. Reflexive-Core emerged from this work and builds substantially beyond it — introducing metacognitive reasoning, multi-persona architecture, and empirical validation. The production XML currently uses A2AS-compatible tag namespaces; migration to the Reflexive-Core native namespace (`<rc:*>`) is planned.

---

## License

- **Code:** [Apache 2.0](LICENSE)
- **Paper:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

---

## Contact

- **Author:** Alex Stanton
- **Email:** [security@thinkpurple.io](mailto:security@thinkpurple.io)
- **LinkedIn:** [alexlstanton](https://linkedin.com/in/alexlstanton)
