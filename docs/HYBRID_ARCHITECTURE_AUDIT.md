# Hybrid AG + RC Architecture Audit

**Scope.** Validate the pilot AgentGateway + Reflexive-Core hybrid against
enterprise-scale multi-team deployment. Assume YAML-driven control across
many teams, RC as the central enterprise webhook security gate operating
at the system level, single shared RC defensive layer across all agents.

**Status legend.** ✅ pilot-correct, scales as-is · 🟡 pilot-correct, needs
production-hardening before scale · 🔴 design gap, must be resolved before
enterprise rollout.

---

## Target architecture (hybrid, enterprise)

```
┌──────────── Per-Team YAML (team owns route config) ──────────┐
│                                                              │
│  Route /agents/<team>/<agent>/v1/chat/completions            │
│    backends: ai → LLM provider                               │
│    policies.ai:                                              │
│      prompts.prepend:                                        │
│        - role: system                                        │
│          content: |  <agent-identity XML>                    │
│      promptGuard:                                            │
│        request:  - webhook: <central RC webhook>             │
│        response: - webhook: <central RC webhook>             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────── Shared central RC webhook (enterprise security) ─────┐
│                                                              │
│  request handler:                                            │
│    - Read agent identity from incoming system message        │
│    - Prepend RC core (defensive scaffold) above identity     │
│    - Wrap user/tool content with per-request NONCE           │
│    - Stream audit record to SIEM                             │
│                                                              │
│  response handler:                                           │
│    - Parse framework JSON                                    │
│    - Apply decision gate                                     │
│    - Return canonical refusal or stripped output             │
│    - Stream decision record to SIEM                          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Composition contract.**
- Agent identity layer: per-team, owned by the agent's team via PR'd YAML.
- RC core layer: enterprise security org owns, single versioned artifact.
- Both layers are system-role content; webhook composes them at request time.

---

## Dimension-by-dimension audit

### 1. Framework XML separation (RC core vs agent identity) — 🔴

**Pilot today.** `framework/reflexive-core-prod.xml` is monolithic — the
RC defensive scaffold and the email-assistant SystemIdentity/Policies are
glued into one file. The webhook loads the whole thing at startup.

**Gap.** Hybrid requires the scaffold (personas, threats, decision schema,
defense block, output_format) to be separable from per-agent identity. A
team adding a new agent should only need to author *their* identity XML —
the RC core comes from the shared webhook.

**Action.** Split `reflexive-core-prod.xml` into:
- `framework/rc-core.xml` — defensive scaffold, agent-agnostic. Owned by
  security org. Versioned independently.
- `framework/identities/<agent>.xml` — per-agent SystemIdentity, scope,
  Policies. Owned by the agent's team. The monolithic prod XML stays as
  the canonical reference / non-AG-testing artifact.
- Webhook composes: `rc_core_xml + identity_xml` at request time, then
  wraps the user content. Single merged system message reaches the LLM.

### 2. Webhook as enterprise SPOF — 🔴

**Pilot today.** Single Python `aiohttp` process on `127.0.0.1:1236`. All
agent traffic across all routes is gated by this one instance.

**Gap.** In an enterprise that depends on RC for security, the webhook
going down = either every agent fails closed (refusals everywhere) or
fails open (RC bypassed). Neither is acceptable.

**Action.**
- Webhook must be a stateless HA service (k8s Deployment + HPA, or
  equivalent), behind a service mesh or load balancer.
- AG `webhook.target` becomes a Service reference (not host:port).
- Health/readiness endpoints already exist (`/healthz`); add liveness
  semantics around framework-load freshness.
- Document the `failureMode` choice explicitly. The AG schema defaults to
  `failClosed`. For enterprise: **failClosed is the right default**;
  document and test it.

### 3. Webhook statelessness / log destination — 🔴

**Pilot today.** Decision log + request log written to local disk
(`gateway/logs/*.jsonl`). Acceptable for a single-instance pilot,
unacceptable for HA.

**Gap.** Stateful local logs prevent horizontal scale and make audit a
nightmare across replicas.

**Action.**
- Webhook streams structured JSON over stdout (k8s log collector picks up)
  or directly to a SIEM endpoint (Splunk HEC, Elastic, CloudWatch).
- Local file logging stays available for dev/test (toggled by env).
- Audit log destination is configurable per environment.
- Logs MUST carry correlation IDs that join to AG's access logs.

### 4. Multi-tenant isolation — 🔴

**Pilot today.** Webhook treats every request identically. No
tenant/agent/team identification anywhere in the decision log.

**Gap.** Multi-team deployment requires:
- Per-tenant log namespacing (team A can't read team B's decisions)
- Per-tenant policy variations (some agents may have stricter confidence
  thresholds, different threat tolerance)
- Per-tenant rate limits and quotas (a misbehaving agent shouldn't starve
  the security gate for everyone)

**Action.**
- Webhook reads `X-Tenant-Id` and `X-Agent-Id` headers (AG forwards these
  via `forwardHeaderMatches`).
- Decision log includes these fields verbatim.
- Per-tenant config (confidence thresholds, custom canonical refusal text,
  redaction rules) loaded from a config service at startup.
- RBAC on log access (SIEM-level controls).

### 5. Framework versioning + rollout — 🟡

**Pilot today.** Webhook loads framework XML once at startup. SHA256 is
logged with each decision so drift is detectable.

**Gap.** Enterprise needs canary/staged rollout of framework changes.
Loading at startup means every config change is a full webhook redeploy,
and there's no way to A/B test framework variations.

**Action.**
- Framework versions stored in a versioned artifact store (git tag,
  S3-versioned bucket, OCI artifact).
- Webhook accepts framework version selection per-route or per-tenant via
  header (`X-RC-Framework-Version`).
- Default version pinned per environment (staging / production).
- Hot reload supported (SIGHUP or admin endpoint); zero-downtime version
  bump.
- Decision log records the framework version applied, not just the SHA.

### 6. Performance of the gate itself — 🟡

**Pilot today.** Python aiohttp single-process. Latency: ~5-20 ms per
webhook call locally. Two hops per LLM request (request webhook + response
webhook).

**Gap.** At 1000+ req/s across agents, Python event-loop saturates on a
single instance. Stateless horizontal scale fixes this, but the per-hop
latency is added to every request even at scale.

**Action.**
- Profile webhook hot path under realistic load.
- Consider Rust/Go rewrite of the hot path if Python is the bottleneck
  (the logic is small: parse JSON, look up decision, wrap content).
- Webhook stays HTTP-callable from AG; reimplementation language is a
  runtime optimisation, not an architecture change.
- LLM inference latency dominates total response time (~100s of ms minimum
  even with cache hits), so webhook latency is a small fraction. Worth
  measuring before optimising.

### 7. Security of the security system — 🔴

**Pilot today.** Webhook on plain HTTP localhost. No authn between AG and
webhook. Framework XML committed to git as plain text.

**Gap.** The webhook IS the security gate; compromise = full agent
compromise. Plain HTTP across a real network is a non-starter.

**Action.**
- mTLS between AG and webhook (AG `webhook.client_cert` + matching
  webhook server cert).
- Webhook validates AG's identity by client cert subject.
- Framework XML still gitable (it's not a secret per se — it's published
  defensive logic). Secrets (LLM API keys, signing keys, SIEM credentials)
  stay in a secret manager (Vault, AWS SM, k8s secret).
- Code review process for webhook + framework changes (CODEOWNERS or
  equivalent, two-person rule for security-org-owned files).
- Webhook supply chain: signed container images, SBOM, vuln scanning.

### 8. NONCE generation — ✅

**Pilot today.** `secrets.token_hex(8)` = 64 bits of entropy per request.

**Verdict.** Adequate for the threat model (preventing attacker prediction
of closing tag) at any realistic enterprise scale. 64 bits = ~10¹⁹
possibilities. No action.

**Documentation.** Add a brief threat-model note next to the NONCE
generator explaining the choice and the alternative (cryptographic
signing via RFC 9421 if Posta's full A2AS vision is later pursued —
that's a different security property, not stronger NONCE).

### 9. Failure modes — 🟡

**Pilot today.** AG schema defaults to `failClosed`. Webhook unreachable
= AG rejects request. LLM unreachable = upstream error returned. Framework
fails to load on webhook start = webhook crashes.

**Gap.** Failure semantics aren't documented or systematically tested.
Enterprise needs explicit, tested failure paths.

**Action.**
- Explicit `failureMode: failClosed` in YAML (not relying on default).
- Chaos test suite: kill webhook, kill upstream, return malformed
  responses, return 5xx → verify AG behavior and client experience.
- Webhook startup: if framework XML can't be loaded, exit with non-zero
  status (k8s will restart and back off; ops gets alerted via
  CrashLoopBackOff). Document and alert on this state.
- Runtime: framework hot-reload must atomically swap or rollback; no
  partial states.

### 10. Observability + audit — 🟡

**Pilot today.** AG emits OpenTelemetry-style structured access logs ✓.
Webhook emits decision JSONL ✓. No correlation between the two.

**Gap.** Per-request distributed tracing requires correlation. SOC analyst
investigating a flagged block should see: AG's access log entry + webhook's
decision log entry + LLM-side prompt cache state, all joined.

**Action.**
- Webhook reads/honours W3C `traceparent` headers (or AG's equivalent).
- Decision log carries the trace ID.
- Metrics:
  - `rc.gate.decisions_total{reason}` — counter per decision reason code
  - `rc.gate.latency_ms` — histogram of webhook handler latency
  - `rc.gate.framework_parse_errors_total` — fail-safe-class counter
  - `rc.gate.confidence_distribution` — histogram for drift detection
- Alerting: spike in fail-safe rate, sudden drop in `fw_approved` rate,
  framework version drift across replicas.

### 11. Cost / token economy at scale — 🟡

**Pilot today.** Framework prefix (~5K tokens) prepended to every request.
KV cache amortises it inside one model session.

**Gap.** Multi-instance LLM backends (autoscaled) lose cache continuity
across instances. Cold-cache rate scales with the number of LLM replicas.

**Action.**
- Sticky-session routing where possible (route same conversation/tenant
  to same LLM instance for cache hits).
- Consider prefix caching at the LLM layer (most production LLM stacks
  support persistent prefix caches across requests).
- Monitor: cache-hit-rate per backend instance, framework prefill cost.
- Document the cost-per-request math at expected enterprise scale.

### 12. Configuration management for many teams — 🔴

**Pilot today.** `gateway/build_config.py` generates a single
`config.yaml` from a template. Single-team / single-agent.

**Gap.** Enterprise: many teams, many agents, frequent route changes.
Single team merging YAML to a shared file = merge hell.

**Action.**
- Per-team route YAML files (`gateway/routes/<team>/<agent>.yaml`).
- `build_config.py` (or a Terraform-like tool) merges per-team YAML +
  central RC webhook config + central LLM backend config → final AG
  config.
- CI validation per PR: schema check, agent-identity XML validation,
  rendered config dry-run against a real AG binary.
- CODEOWNERS protecting:
  - `framework/rc-core.xml` — security org only
  - `framework/identities/<agent>.xml` — agent's team
  - Webhook code — security org only
  - Route YAML — agent's team (with security review on first add)
- Schema for route YAML strictly limits what each team can configure
  (they can't, e.g., disable the request webhook).

### 13. Framework decision schema as a contract — ✅

**Pilot today.** Framework's `output_format` declares: `persona`, `phase`,
`decision` (enum), `confidence` (number), `threats[]`, `output`.

**Verdict.** Schema is sound and the JSON-schema-constrained sampling we
verified locks the model into it. No action.

**Documentation.** Treat the response schema as a versioned contract.
Changes to the schema = breaking change for downstream tooling (SIEM
parsers, dashboards). Bump a `framework_schema_version` in the response
when the shape changes.

### 14. Agent-identity governance — 🟡

**Pilot today.** Single email-assistant identity baked into the
monolithic framework.

**Gap.** Each team will want to author their own identity. Without
guardrails, teams can write identities that defeat RC's intent (e.g., a
SystemIdentity that says "Ignore the security framework's threats array").

**Action.**
- Identity XML schema specifies what teams can declare:
  - SystemIdentity role/scope (free text within length cap)
  - Allowed tools (enum, from approved tool catalog)
  - Custom policy additions (within schema; cannot weaken RC core's
    forbidden actions)
  - Output redaction rules (additive to RC core's rules)
- Identity XML CANNOT:
  - Override RC core's threat detection rules
  - Modify the decision enum
  - Disable any phase of the security pipeline
- Validation at PR time enforces the schema; CI rejects invalid
  identities.

### 15. Conversation history / multi-turn — 🟡

**Pilot today.** Webhook preserves assistant history verbatim, wraps
current-turn user content, prepends framework as fresh system message.

**Gap.** Multi-turn at scale has subtleties:
- Conversation history grows context tokens; KV cache eviction risk.
- Past assistant turns were already approved (the framework cleared them);
  do we re-validate them on each turn?
- If an attacker plants malicious content in a tool turn and the model's
  next-turn response references it, does the gate catch it?

**Action.**
- Document the multi-turn threat model: each turn is independently gated.
  Prior approved turns are trusted output; their content does not need
  re-wrapping.
- New tool-data turns coming in DO get re-wrapped per turn (could be
  attacker-injected mid-conversation).
- Context-length budget management: webhook can elide oldest turns when
  the next request would exceed model context, with audit logging of the
  elision.

### 16. RC framework update process — 🟡

**Pilot today.** Framework is a file in the repo; changes are git
commits.

**Gap.** Enterprise needs a controlled release process for the central
RC core (it gates EVERY agent's traffic).

**Action.**
- RC core versioned (semver), tagged in git, published as an artifact.
- Staged rollout: canary % of traffic on new version, monitor decision
  distribution drift, promote on stability.
- Rollback path: webhook can serve N versions in parallel keyed by
  tenant/header.
- Change advisory board for RC core changes (it's a centralised security
  control — changes have org-wide blast radius).
- Decision log alerting on "framework version drift" if a tenant gets a
  version they shouldn't.

---

## Critical gaps to close before "really works" at enterprise

In priority order:

1. **🔴 RC core ↔ agent identity split** (dim 1). Foundational; everything
   else assumes this exists. Estimated: ~1-2 days for the XML refactor +
   webhook composition logic.

2. **🔴 Webhook HA + log destination** (dim 2, 3). Webhook must be
   stateless and externally-logged before any production deployment.
   Estimated: ~2-3 days for the deployment shape + log routing.

3. **🔴 mTLS between AG and webhook** (dim 7). Non-negotiable for prod.
   Estimated: ~1 day plumbing.

4. **🔴 Multi-tenant identification + log namespacing** (dim 4).
   Estimated: ~1 day to thread headers + namespace logs.

5. **🔴 Per-team YAML config strategy** (dim 12). Without this, the
   org-scale story doesn't work. Estimated: ~2-3 days for the templating +
   CI validation.

6. **🟡 Framework versioning + rollout** (dim 5, 16). Becomes urgent the
   moment a second team is onboarded. Estimated: ~2 days for the version
   selection mechanism + canary plumbing.

Remaining 🟡s are production-hardening items that can be deferred until
after first production traffic.

---

## Does the design "really work"?

**Pilot scope (single team, single agent, pre-production): ✅ Works.**
The gate fires correctly, the wrap is applied correctly, the decision is
deterministic, the audit trail is complete. We validated this end-to-end.

**Enterprise scope (many teams, central RC, production traffic): not
yet.** The architectural shape is correct — AG handles routing/identity
per route, webhook handles RC core and gating. But six 🔴 items above
must close before we have something deployable at enterprise scale. None
of them are research problems — they're well-understood production
engineering. Estimated end-to-end: ~2 weeks of focused work to close all
the 🔴 items and put the system in a state that would survive an
enterprise security review.

The conceptual design holds. The implementation needs to grow up.
