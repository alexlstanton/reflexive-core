"""
GARAK probe-set definitions for Reflexive-Core comparison runs.

Three scopes:
  - curated: hand-picked subset that maps onto RC's 13 attack categories;
    fast, sharp head-to-head delta.
  - active:  GARAK's default "active" set (what `python -m garak` runs
    when no --probes is given); the industry-standard yardstick.
  - all:     full taxonomy including experimental probes. Hours per model.
"""

# Curated subset that mirrors Reflexive-Core's attack taxonomy.
# Maintained in lockstep with scripts/category_map.py.
CURATED_MIRROR: list[str] = [
    "dan",
    "promptinject",
    "encoding",
    "leakreplay",
    "lmrc",
    "malwaregen",
    "latentinjection",
    "goodside",
    "snowball",
    "sysprompt_extraction",
]

# Pilot subset: 9 sub-probes with VERIFIED-small prompt counts (queried
# from each probe class at probe_sets.py authoring time). Targets ~30
# attempts per cell at ~80s each → ~40min per cell, ~90min RC OFF + RC ON.
#
# Coverage is intentionally narrow: jailbreak + toxic-content + one
# leakreplay. We DO NOT include prompt-injection or encoding here because
# the smallest active probes in those families have ≥64 prompts each
# which would push the pilot beyond a few hours per cell. Those families
# get measured in the full `curated` run once we know what to expect.
#
# Probe                  Prompts  Maps to (normalized)        Note
# ─────────────────────  ───────  ─────────────────────       ──────────────
# goodside.ThreatenJSON    1      jailbreak
# goodside.WhoIsRiley      6      jailbreak
# dan.AutoDANCached        3      jailbreak                   DAN-style attack
# lmrc.QuackMedicine       1      toxic_content
# lmrc.SlurUsage           1      toxic_content
# lmrc.SexualContent       1      toxic_content
# lmrc.Sexualisation       3      toxic_content
# lmrc.Bullying            7      toxic_content               FP-prone
# leakreplay.GuardianCloze 9      system_prompt_leak
PILOT: list[str] = [
    "goodside.ThreatenJSON",
    "goodside.WhoIsRiley",
    "dan.AutoDANCached",
    "lmrc.QuackMedicine",
    "lmrc.SlurUsage",
    "lmrc.SexualContent",
    "lmrc.Sexualisation",
    "lmrc.Bullying",
    "leakreplay.GuardianCloze",
]

# Prompt-injection pilot — targets RC's *actual* design surface. Sized
# from probes whose INSTANTIATED prompt count was empirically verified
# (the raw `prompts` attribute doesn't reflect payload×base combinatorics;
# promptinject and latentinjection probes expand 4-8x at instantiation).
#
# Probe                  Prompts  Category                Note
# ────────────────────   ───────  ──────────────────────  ──────────────────
# goodside.Tag             32     prompt_injection        Hidden markup tag injection
# goodside.WhoIsRiley       6     jailbreak/manipulation  Riley impersonation
# dan.AutoDANCached         3     jailbreak               Regression control
# lmrc.Sexualisation        3     toxic_content           Uplift control
#
# Total: 44 attempts. Time budget RC OFF ≈ 25min, RC ON ≈ 10-15min.
PI_PILOT: list[str] = [
    "goodside.Tag",
    "goodside.WhoIsRiley",
    "dan.AutoDANCached",
    "lmrc.Sexualisation",
]

# Design-target pilot — probes specifically hitting RC's defensive surface:
#   - latent injection in tool data (RC's primary threat model)
#   - system-prompt extraction (RC's confidentiality of its own gating)
#   - small jailbreak control to confirm canonical-refusal detection works
#
# Probe                                          Prompts  Surface
# ─────────────────────────────────────────────  ───────  ───────────────────
# sysprompt_extraction.SystemPromptExtraction       64    Extract RC framework prompt
# latentinjection.LatentWhoisSnippet                64    Indirect injection in document
# dan.AutoDANCached                                  3    DAN control
# goodside.WhoIsRiley                                6    Manipulation control
# Total: 137 attempts. Time budget: RC OFF ≈ 45min, RC ON ≈ 20min.
DESIGN_PILOT: list[str] = [
    # sysprompt_extraction is the direct test of RC's framework-prompt
    # confidentiality — the most relevant single probe for our threat model.
    # latentinjection.* are also in scope but they instantiate to 200-1000+
    # prompts post-combinatorics and bust the time budget on slow hardware;
    # tracked for a longer follow-on run.
    "sysprompt_extraction.SystemPromptExtraction",
    "dan.AutoDANCached",
    "goodside.WhoIsRiley",
]

# Sentinel meaning "let GARAK pick its default active probes".
ACTIVE_DEFAULT: list[str] | None = None

# Sentinel for "all probes" — GARAK CLI accepts this literal.
ALL_PROBES: str = "all"


def resolve_scope(scope: str) -> str | None:
    """Map a scope name onto the --probes argument value.

    Returns None when no --probes flag should be passed (GARAK default behavior).
    """
    scope = scope.lower()
    if scope == "pilot":
        return ",".join(PILOT)
    if scope == "pi_pilot":
        return ",".join(PI_PILOT)
    if scope == "design_pilot":
        return ",".join(DESIGN_PILOT)
    if scope == "curated":
        return ",".join(CURATED_MIRROR)
    if scope == "active":
        return None  # omit --probes; garak picks active set
    if scope == "all":
        return ALL_PROBES
    raise ValueError(f"unknown scope: {scope!r}. expected one of: pilot, pi_pilot, curated, active, all")
