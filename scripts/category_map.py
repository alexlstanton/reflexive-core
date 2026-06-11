"""
Taxonomy bridge: Reflexive-Core attack_type ↔ GARAK probe family ↔ normalized.

The "normalized" axis is the only thing scripts/compare_suites.py compares on,
so any RC category or GARAK probe that doesn't appear here will be reported in
the {RC,GARAK}-unique sections of the delta — never silently dropped.

Keep CURATED_MIRROR in garak/probe_sets.py in lockstep with the
RC↔GARAK rows that have a non-None GARAK column.
"""

from __future__ import annotations

# Normalized category labels — the comparison axis.
NORMALIZED = {
    "jailbreak",
    "prompt_injection",
    "encoding_obfuscation",
    "system_prompt_leak",
    "malware_gen",
    "toxic_content",
    "data_leak",
    "code_injection",
    "social_engineering",
    "benign",
    "other",
}


# RC attack_type -> normalized
RC_TO_NORM: dict[str, str] = {
    "jailbreak": "jailbreak",
    "prompt_injection": "prompt_injection",
    "indirect_prompt_injection": "prompt_injection",
    "tool_injection": "prompt_injection",
    "tool_poisoning": "prompt_injection",
    "obfuscation": "encoding_obfuscation",
    "semantic_obfuscation": "encoding_obfuscation",
    "semantic_proxy": "jailbreak",
    "social_engineering": "social_engineering",
    "mcp_poisoning": "prompt_injection",
    "encoding": "encoding_obfuscation",
    "policy_violation": "jailbreak",
    "privilege_escalation": "code_injection",
    "data_exfiltration": "data_leak",
    "reconnaissance": "data_leak",
    "edge_case": "other",
    "none": "benign",
    "benign": "benign",
}


# GARAK probe family (lowercase, no submodule) -> normalized
GARAK_TO_NORM: dict[str, str] = {
    "dan": "jailbreak",
    "grandma": "jailbreak",
    "goodside": "jailbreak",
    "promptinject": "prompt_injection",
    "latentinjection": "prompt_injection",
    "web_injection": "prompt_injection",
    "encoding": "encoding_obfuscation",
    "ansiescape": "encoding_obfuscation",
    "smuggling": "encoding_obfuscation",
    "badchars": "encoding_obfuscation",
    "misleading": "jailbreak",
    "snowball": "jailbreak",
    "fitd": "social_engineering",
    "malwaregen": "malware_gen",
    "packagehallucination": "malware_gen",
    "realtoxicityprompts": "toxic_content",
    "lmrc": "toxic_content",
    "donotanswer": "toxic_content",
    "leakreplay": "system_prompt_leak",
    "sysprompt_extraction": "system_prompt_leak",
    "propile": "data_leak",
    "apikey": "data_leak",
    "xss": "code_injection",
    "exploitation": "code_injection",
    "atkgen": "jailbreak",
    "tap": "jailbreak",
    "goat": "jailbreak",
    "agent_breaker": "prompt_injection",
    "av_spam_scanning": "other",
    "continuation": "other",
    "glitch": "other",
    "divergence": "other",
    "fileformats": "other",
    "phrasing": "other",
    "topic": "other",
    "doctor": "other",
    "dra": "jailbreak",
    "audio": "other",
    "visual_jailbreak": "jailbreak",
    "sata": "other",
    "suffix": "jailbreak",
    "test": "other",
}


def normalize_rc(attack_type: str) -> str:
    return RC_TO_NORM.get(attack_type, "other")


def normalize_garak(probe_classname: str) -> str:
    """Take a GARAK probe class name like 'probes.dan.Dan_11_0' and return the normalized label."""
    # Family is the segment after 'probes.' and before the next '.'.
    parts = probe_classname.split(".")
    family = parts[1].lower() if len(parts) >= 2 and parts[0] == "probes" else parts[0].lower()
    return GARAK_TO_NORM.get(family, "other")


def garak_family(probe_classname: str) -> str:
    parts = probe_classname.split(".")
    return parts[1].lower() if len(parts) >= 2 and parts[0] == "probes" else parts[0].lower()
