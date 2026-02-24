# Reflexive-Core Alpha Release

**Date**: October 25, 2025
**Status**: ALPHA Research Concept
**Test Results**: 20/20 on Claude Sonnet 4.5

---

## What is This?

This is the first public release of Reflexive-Core, an experimental multi-persona metacognitive security framework for LLMs.

**The Big Idea**: Instead of one security prompt, use multiple "personas" with different threat models to analyze requests. Each persona brings different expertise and catches threats the others might miss.

**Current State**: Tested on 20 security test cases using Claude Sonnet 4.5. Got 20/20 (100%) on the production framework.

**Is this production-ready?** No. This is ALPHA research. We need validation from others.

**Could this change LLM security?** Maybe. That's what we're trying to figure out.

---

## What We Built

### Two Framework Variants

**reflexive-core-prod.xml** (Recommended)
- Optimized with adaptive verbosity
- Returns minimal JSON for routine operations
- Full detail for security events
- 20/20 test pass rate
- ~10.7s avg latency, ~5.5K tokens

**reflexive_core.xml** (Debug)
- Verbose logging for all phases
- Useful for understanding behavior
- 19/20 test pass rate (one known issue)
- ~21.6s avg latency, ~5.9K tokens

### Architecture

**4 Personas:**
- Preflight Analyst (ADVERSARIAL) - Quick policy/scope checks
- Security Analyst (PARANOID) - Deep threat analysis
- Controlled Executor (SERVICE-ORIENTED) - Safe task execution
- Compliance Validator (SKEPTICAL) - Output validation

**6 Processing Phases:**
DEFENSE → PREFLIGHT → PRESCAN → EXECUTION → ASSURANCE → FINAL

**Key Innovation**: ~75% of threats caught in Preflight (first phase). Early detection = faster, more efficient.

### Test Suite v2.3

20 test cases covering:
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

All test expectations validated by security expert review.

---

## Test Results

**Model**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`)
**Date**: October 25, 2025

| Metric | Production Framework | Debug Framework |
|--------|---------------------|-----------------|
| Tests Passed | 20/20 (100%) | 19/20 (95%) |
| Avg Latency | 10.7s | 21.6s |
| Avg Tokens | 5,556 | 5,872 |
| Avg Confidence | 0.989 | 0.980 |

**All 14 security threats detected. Zero false positives on benign requests.**

See [data/results/comparison/V23_FINAL_RESULTS.md](data/results/comparison/V23_FINAL_RESULTS.md) for full analysis.

---

## How to Use

### Quick Start

```bash
# Install
pip install anthropic
export ANTHROPIC_API_KEY='your-key'

# Test
python3 run_tests.py --model claude --prod

# Use in code
from anthropic import Anthropic
import json

with open('reflexive-core-prod.xml', 'r') as f:
    framework = f.read()

client = Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=4000,
    system=[{"type": "text", "text": framework, "cache_control": {"type": "ephemeral"}}],
    messages=[{"role": "user", "content": "Your request here"}]
)

result = json.loads(response.content[0].text)
print(result['decision'])  # APPROVED, BLOCKED, or REVIEW_REQUIRED
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for more usage patterns.

---

## A2AS Integration

Reflexive-Core can work with the Agent-to-Agent Security (A2AS) standard:

```xml
<a2as:defense>
  <!-- Reflexive-Core framework -->
</a2as:defense>

<a2as:policy>
  <!-- Your organization policy -->
</a2as:policy>
```

But it also works standalone - A2AS is optional.

**Important**: If using A2AS, follow the strict structure requirements. Don't modify the persona/phase architecture or results may degrade.

---

## Known Limitations

### What We Know Doesn't Work

- **Debug framework**: Fails sensitive_001 (incorrectly approves hardcoded API keys)
- **Single model tested**: Only Claude Sonnet 4.5. Other models unknown.
- **English only**: Framework operates in English.

### What We Don't Know

Open research questions:

- Does this work on GPT-4, Gemini, other models?
- What's the false positive rate at scale (1000+ benign requests)?
- Can sophisticated adversarial attacks bypass all personas?
- How does this perform at 100K, 1M requests?
- What's the minimum viable framework (fewer personas/phases)?
- Does this work with streaming responses?

**Help us find out!** Run your own tests and share results.

---

## Design Decisions

### Why These Choices?

**1. Credentials in Code → Always BLOCKED**

Even "test" credentials get blocked. Rationale: Displaying code with hardcoded credentials normalizes dangerous practices. Blocked entirely to reinforce zero-tolerance.

Distinction:
- Credentials in code → BLOCKED
- PII in legitimate emails → APPROVED with [REDACTED]

**2. Early Detection Preferred**

75% of threats caught in Preflight. Why run all 6 phases if you can detect the threat early? More efficient, same security outcome.

**3. Expertise-Based, Not Rule-Based**

The XML provides structure, but relies on the LLM's built-in security knowledge. No explicit if-then rules. This might make it more resilient to novel attacks (or might not - needs validation).

**4. Adaptive Verbosity**

Routine approvals return minimal JSON. Security events return full detail. Saves tokens on the 90% of requests that are benign.

---

## What's Included

```
.
├── README.md                         # Start here
├── DEPLOYMENT.md                     # How to use it
├── CONTRIBUTING.md                   # How to help
├── TESTING.md                        # Detailed test documentation
├── CHANGELOG.md                      # Version history
├── reflexive-core-prod.xml          # Production framework (20/20)
├── reflexive_core.xml               # Debug framework (19/20)
├── tests/test_cases.json            # 20 test cases
├── run_tests.py                     # Test runner
└── data/results/                    # Test results + analysis
```

---

## How to Contribute

**We need validation from the research community.**

1. **Run tests on other models** - GPT-4, Gemini, Claude 3.5, etc.
2. **Try to break it** - Find attacks that bypass all personas
3. **Test at scale** - What happens with 10K, 100K requests?
4. **Add test cases** - What attack patterns are we missing?
5. **Answer research questions** - False positive rate? Minimum viable framework?

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## Disclaimers

**Use at Your Own Risk**

- This is ALPHA research, not production-tested software
- Only tested on one model (Claude Sonnet 4.5)
- Security frameworks can be bypassed
- No guarantees, warranties, or SLAs
- Test thoroughly before using with real data

**But Also...**

If multi-persona metacognitive security works, this could be a significant advance in LLM security. We need help figuring out if it actually works.

---

## License

Licensed under Apache 2.0 (code) and CC BY 4.0 (paper)

---

## Contact

- **GitHub Issues**: Bug reports, questions
- **GitHub Discussions**: Research collaboration, result sharing
- **Email**: security@thinkpurple.com

---

## What's Next?

This is a research release. Next steps depend on community feedback and validation:

**If this works:**
- Test on more models
- Scale testing (1M+ requests)
- Add more test cases
- Research minimum viable framework
- Investigate streaming support

**If this doesn't work:**
- Learn why
- Document failure modes
- Try alternative architectures

**Either way, we learn something valuable about LLM security.**

---

**Help us figure out if this is the future of LLM security.**

Test it. Break it. Validate it. Share results.

This might change how we secure LLM systems. Or it might not scale. Let's find out together.

---

**Released**: October 25, 2025
**Status**: ALPHA Research
**Test Results**: 20/20 (Claude Sonnet 4.5)
**Next**: Community validation
