# Deployment Ideas

**Status**: ALPHA Research Concept - Use at your own risk

This document outlines potential ways to use Reflexive-Core. These are theoretical deployment patterns, not battle-tested production recipes.

---

## Three Ways to Use This

### 1. Direct System Prompt

Simplest approach - just use the XML as your system prompt:

```python
from anthropic import Anthropic
import json

with open('reflexive-core-prod.xml', 'r') as f:
    framework = f.read()

client = Anthropic()

response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=4000,
    system=[{
        "type": "text",
        "text": framework,
        "cache_control": {"type": "ephemeral"}
    }],
    messages=[{"role": "user", "content": user_input}]
)

result = json.loads(response.content[0].text)
# result = {decision: "APPROVED|BLOCKED|REVIEW_REQUIRED", confidence: 0.95, ...}
```

**Use case**: Quick experiments, single-agent systems, personal projects

---

### 2. Multi-Agent Gateway

Wrap agent communications with security analysis:

```python
class AgentGateway:
    def agent_call(self, source_agent, target_agent, message):
        # Analyze message with Reflexive-Core
        result = self.analyze_with_reflexive_core(message)

        if result['decision'] == 'BLOCKED':
            return {"error": "Security threat detected", "details": result}

        # Forward to target agent
        return target_agent.process(message)
```

**Use case**: Multi-agent systems, agent orchestration platforms

---

### 3. Security Microservice

Deploy as a standalone service that other apps can call:

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/analyze")
def analyze_request(user_input: str):
    result = reflexive_core_analyze(user_input)
    return {
        "safe_to_process": result['decision'] == 'APPROVED',
        "decision": result['decision'],
        "confidence": result['confidence']
    }
```

**Use case**: Multiple apps need security analysis, centralized logging

---

## A2AS Integration (Optional)

Reflexive-Core can work with the Agent-to-Agent Security (A2AS) standard. This is a research initiative to create security primitives for agent systems.

### A2AS Concept

A2AS defines two XML primitives:
- `<a2as:defense>` - Security wrapper (this is where Reflexive-Core goes)
- `<a2as:policy>` - Organization-specific policy

### How It Works

**With A2AS** (full standard):
```xml
<a2as:defense>
  <!-- Reflexive-Core XML framework -->
  <system_identity>
    <name>Executive Email Assistant</name>
    ...
  </system_identity>
</a2as:defense>

<a2as:policy>
  <!-- Your organization's policy -->
  <allowed_actions>
    <action>email_query</action>
    <action>calendar_query</action>
  </allowed_actions>
  <blocked_actions>
    <action>code_execution</action>
  </blocked_actions>
</a2as:policy>

<user_request>
  Tell me about Q4 planning emails
</user_request>
```

The LLM sees both the defense (security threats) and policy (allowed actions) together.

**Without A2AS** (standalone):
```xml
<!-- Just use Reflexive-Core XML directly as system prompt -->
<system_identity>
  <name>Executive Email Assistant</name>
  ...
</system_identity>
```

No A2AS tags needed. Reflexive-Core works fine standalone.

### Important: A2AS Structure Requirements

If you DO use A2AS primitives, you must follow our strict structure:

1. **Defense must include Reflexive-Core's full XML** - Don't strip out the personas, phases, or system_identity
2. **Policy must be separate** - Don't merge policy into the defense XML
3. **Both must wrap the request** - Defense + Policy come before the user request

**Why strict?** The framework was designed with specific personas and phases. Modifying the structure breaks the multi-perspective threat detection.

**Can I customize?** Yes, but test thoroughly. The test suite is your validation that it still works.

---

## Performance Notes

- **Latency**: ~10s average (Claude Sonnet 4.5)
- **Tokens**: ~5.5K average
- **Prompt caching**: Use `cache_control: {"type": "ephemeral"}` to cache the system prompt (90%+ hit rate)

---

## Monitoring (Recommended)

Log all BLOCKED decisions:

```python
if result['decision'] == 'BLOCKED':
    logger.warning(f"Security threat: {result.get('risk_summary')}")
    logger.info(f"Threats: {result.get('threat_indicators')}")
```

This gives you visibility into what attacks are being attempted.

---

## Disclaimers

- **ALPHA research**: Not production-tested at scale
- **Single model**: Only tested on Claude Sonnet 4.5
- **No guarantees**: Security frameworks can be bypassed
- **Your risk**: Test thoroughly before using with real data

---

## Potential Use Cases

Where this *might* be useful (untested):

- **Email assistants**: Protect against prompt injection via email content
- **Agent systems**: Security layer between agents
- **Code review**: Detect hardcoded credentials before display
- **Chatbots**: Multi-layer defense against jailbreaks
- **API gateways**: Validate requests before processing

---

## What We Don't Know

Open questions for research:

- How does this perform at scale (1M+ requests)?
- What's the false positive rate with thousands of benign requests?
- Can sophisticated adversarial attacks bypass all personas?
- How does this work with streaming responses?
- Does this work well with non-Claude models?
- What's the minimum viable framework (fewer personas/phases)?

**Help us find out!** Run your own tests and share results.

---

**Remember**: This is experimental research. Use at your own risk. But if it works for your use case, we'd love to hear about it.
