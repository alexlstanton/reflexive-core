# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in the Reflexive-Core framework, please report it responsibly.

**Email:** security@thinkpurple.io

Please include:
- Description of the vulnerability
- Steps to reproduce
- Framework version (debug or production XML, git commit hash)
- LLM provider and model used
- Test case that demonstrates the issue (if applicable)

We aim to acknowledge reports within 48 hours and provide a substantive response within 7 days.

## Scope

Reflexive-Core is a security research framework. Vulnerabilities in scope include:

- **Framework bypasses:** Prompts that cause the framework to approve requests that should be blocked (false negatives)
- **Persona failures:** Cases where the wrong persona makes the decision or personas fail to activate
- **Confidence manipulation:** Inputs that cause artificially high confidence on incorrect decisions
- **Tag injection:** Attacks that exploit the `<rc:user:>` / `<rc:tool:>` provenance tagging system
- **Output exfiltration:** Techniques that cause the framework to leak system prompt content or internal state

## Out of Scope

- Vulnerabilities in the underlying LLM providers (Anthropic, OpenAI, Google)
- Issues requiring physical access to the testing infrastructure
- Social engineering of project maintainers

## Known Limitations

Reflexive-Core operates within a single inference context. This architecture has inherent limitations that are documented in the research paper:

1. **Token-level vulnerability:** The framework cannot prevent the LLM from processing adversarial tokens before the security personas evaluate them.
2. **Multi-turn persistence:** Each inference call is independent. The framework does not maintain security state across conversation turns (prompt caching re-instantiates the framework fresh each call).
3. **Persona exploitation:** Sufficiently sophisticated attacks may attempt to impersonate or confuse the persona routing system.
4. **Model dependency:** Framework effectiveness varies by LLM provider and model version. Test results from one model do not guarantee equivalent performance on another.

These are architectural constraints, not bugs. They are actively researched and discussed in the project documentation.

## Responsible Disclosure

We follow a 90-day disclosure timeline. If you report a vulnerability:
- We will work with you to understand and validate the issue
- We will develop and test a fix
- We will credit you in the changelog (unless you prefer anonymity)
- After 90 days, or once a fix is released, the vulnerability may be publicly disclosed
