# Contributing to Reflexive-Core Research

**Status**: ALPHA Research Concept

This is early-stage research. We need help validating whether this approach actually works.

---

## What We Need

### 1. Validation & Testing

**Run the tests on different models:**
- GPT-4.1+ / GPT-5
- Claude Sonnet 4.5+ / Opus 4.5+
- Gemini 2.5 Pro+ / Flash
- Grok 4+

Share your results! How do they compare to our 28-case sweep?

**Add new test cases:**
- Attack patterns we missed
- Edge cases that break the framework
- False positives (benign requests incorrectly blocked)

**Try to break it:**
- Can you find prompts that bypass all personas?
- Can you jailbreak it with novel techniques?
- What happens with adversarial inputs?

### 2. Research Questions

Help answer open questions:

- **Does this scale?** What happens at 10K, 100K, 1M requests?
- **False positive rate?** Test with thousands of legitimate requests
- **Cross-model behavior?** How do results differ across LLMs?
- **Minimum viable framework?** Can we get similar results with fewer personas/phases?
- **Attack taxonomy?** What threat categories are we missing?
- **Prompt engineering?** Can simpler prompts achieve similar results?

### 3. Documentation

- Better explanations of how it works
- More examples of usage patterns
- Clarifications where things are confusing
- Corrections where we're wrong

---

## How to Contribute

### Report Issues

Found a bug or unexpected behavior? [Open an issue](https://github.com/alexlstanton/reflexive-core/issues)

**Include:**
- What you tried
- What you expected
- What actually happened
- Model/version used
- Test case (if applicable)

### Share Test Results

Ran the test suite on a different model? Share results:

1. Run tests: `python run_sweep.py --models [model] --strict`
2. Create issue or discussion with results
3. Include model name, version, date tested
4. Note any interesting failures or surprises

### Submit Test Cases

Add new tests to `tests/test_cases.json`:

```json
{
  "id": "your_test_001",
  "name": "Your Attack Pattern",
  "user_input": "Test input here",
  "expected_behavior": "BLOCKED",
  "expected_persona": "Security Analyst",
  "expected_phase": "prescan",
  "min_confidence": 0.85
}
```

Then submit a PR or share in discussions.

### Code Contributions

**Simple process:**
1. Fork the repo
2. Make your changes
3. Test that it works: `python run_sweep.py --models sonnet45 --strict`
4. Submit a PR with description of what you changed and why

**No strict requirements** - this is research, not enterprise software. Just make sure tests still pass (or document why they shouldn't).

---

## What We're NOT Looking For

This is research, so we're keeping it simple:

- ❌ Enterprise features (SSO, RBAC, etc.)
- ❌ Production hardening (we're not claiming production-ready)
- ❌ Extensive CI/CD pipelines
- ❌ Marketing materials

Focus on: **Does this actually work? Can we prove it? What are the limits?**

---

## Research Ethics

If you're testing Reflexive-Core:

- **Don't use real sensitive data** - use test data only
- **Don't deploy to production without thorough testing** - this is ALPHA research
- **Share negative results too** - failures are valuable data
- **Credit others** - if you build on someone else's work, acknowledge it

---

## Communication

- **GitHub Issues**: Bug reports, feature requests
- **GitHub Discussions**: Research questions, results sharing, brainstorming
- **Email**: security@thinkpurple.io for collaboration inquiries

---

## License

By contributing, you agree your contributions will be licensed under Apache 2.0 (same as the project).

---

## Recognition

Contributors who make significant contributions (new test cases, validation results, bug fixes, documentation) will be acknowledged in:
- README.md
- CHANGELOG.md
- Any research papers or publications

---

## The Goal

**We're trying to figure out if multi-persona metacognitive security frameworks are a viable approach to LLM security.**

Help us answer that question with data, not speculation.

Your contributions - whether it's finding a bug, breaking the framework, validating results, or asking good questions - are all valuable.

**This might be the future of LLM security. Or it might not work at scale. Let's find out together.**

---

**Questions?** Open a discussion or email security@thinkpurple.io
