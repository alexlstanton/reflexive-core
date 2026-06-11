#!/usr/bin/env python3
"""
Run GARAK against a local LM Studio model. The model is *always* reached
through the agentgateway proxy, configured to enforce Reflexive-Core on or
off based on which port the request hits:

  --rc-mode on   →  AG :1235 (promptEnrichment + webhook gate + JSON-mode)
  --rc-mode off  →  AG :1237 (transparent passthrough, no framework, no JSON-mode)
  --rc-mode direct → LM Studio :1234 directly (used only for the A/B sanity
                    test that confirms AG-OFF doesn't change GARAK's measurement)

The model dispatch comes from config/local_models.py. Output lands at
data/experiments/<model>/garak_<scope>_rc_<mode>/<run_id>/ with a manifest,
the raw garak.report.jsonl, a parsed summary, and a copy of the rest_config
that was actually used.

Usage:
    python garak/run_garak.py --model gemma4-e4b --scope pilot --rc-mode off
    python garak/run_garak.py --model gemma4-e4b --scope pilot --rc-mode on
    python garak/run_garak.py --model gemma4-e4b --scope pilot --rc-mode direct  # A/B baseline only
    python garak/run_garak.py --model gemma4-e4b --scope pilot --rc-mode on --smoke
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

sys.path.insert(0, str(REPO_ROOT))
from config.local_models import LOCAL_MODELS  # noqa: E402
from scripts.experiment_manifest import (  # noqa: E402
    EXPERIMENTS_ROOT, FrameworkInfo, ModelInfo, ModelSettings, RunManifest,
    SuiteInfo, make_run_id, sha256_of_file, write_manifest,
)

sys.path.insert(0, str(HERE))
from probe_sets import resolve_scope  # noqa: E402

VENV_PYTHON = HERE / ".venv" / "bin" / "python"
RUNTIME_DIR = HERE / "configs" / ".runtime"

# Per-mode templates. Each is templated with the model id before invocation.
TEMPLATE_BY_MODE = {
    "on":     HERE / "configs" / "gateway_rc_on.json",
    "off":    HERE / "configs" / "gateway_rc_off.json",
    "direct": HERE / "configs" / "lmstudio.json",
}

# RC-ON cell exists at this URI; we hit it once before GARAK runs so the
# framework prefill is in the KV cache when the first probe lands.
RC_ON_WARM_URI = "http://127.0.0.1:1235/v1/chat/completions"
FRAMEWORK_PATH_REL = "framework/reflexive-core-prod.xml"


def build_runtime_config(template_path: Path, model_id: str, model_key: str, scope: str, rc_mode: str) -> Path:
    """Substitute $MODEL in the template and write a per-run config file."""
    with template_path.open() as f:
        cfg = json.load(f)
    rest = cfg["rest"]["RestGenerator"]
    rest["req_template_json_object"]["model"] = model_id
    rest["name"] = f"{rest.get('name', 'gateway')}-{model_key}"
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    out = RUNTIME_DIR / f"{model_key}_{scope}_rc_{rc_mode}.json"
    with out.open("w") as f:
        json.dump(cfg, f, indent=2)
    return out


def warm_kv_cache(uri: str, model_id: str, framework_xml: str, timeout: int = 600) -> tuple[bool, float]:
    """One identical-prefix call so the next request hits the KV cache.

    When hitting AG (RC ON port 1235), we send only the user message — AG
    prepends the framework system prompt itself. Sending our own system
    message would result in a double prepend that breaks parity with the
    actual GARAK requests (which also send no system message).
    """
    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": "Reply OK."},
        ],
        # Generous budget — framework reasons through several hundred
        # tokens before emitting content. With max_tokens too small the
        # webhook sees empty content and fail-safes (fw_empty_response).
        "max_tokens": 1024,
        "temperature": 0.0,
    }
    req = urllib.request.Request(
        uri,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer lm-studio"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return (True, time.perf_counter() - t0)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[run_garak] warm-up failed: {e}", file=sys.stderr)
        return (False, time.perf_counter() - t0)


def parse_garak_jsonl(path: Path) -> dict:
    summary: dict = {"probes": {}, "garak_version": None, "start_time": None, "end_time": None}
    if not path.exists():
        return summary
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            et = rec.get("entry_type")
            if et == "init":
                summary["garak_version"] = rec.get("garak_version")
                summary["start_time"] = rec.get("start_time")
            elif et == "completion":
                summary["end_time"] = rec.get("end_time")
            elif et == "eval":
                probe = rec.get("probe")
                if not probe:
                    continue
                p = summary["probes"].setdefault(probe, {"detectors": {}, "totals": {"passed": 0, "fails": 0, "total_evaluated": 0}})
                det = rec.get("detector") or "default"
                p["detectors"][det] = {
                    "passed": int(rec.get("passed") or 0),
                    "fails": int(rec.get("fails") or 0),
                    "nones": int(rec.get("nones") or 0),
                    "total_evaluated": int(rec.get("total_evaluated") or 0),
                }
                p["totals"]["passed"] += int(rec.get("passed") or 0)
                p["totals"]["fails"] += int(rec.get("fails") or 0)
                p["totals"]["total_evaluated"] += int(rec.get("total_evaluated") or 0)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=list(LOCAL_MODELS.keys()))
    parser.add_argument(
        "--scope", choices=["pilot", "pi_pilot", "design_pilot", "curated", "active", "all"], default="pilot",
        help="Probe scope. design_pilot = hits RC's actual defensive surface (latent injection + sysprompt extraction); pilot = small jailbreak+toxic mix; pi_pilot = early prompt-injection set; curated = mirror of RC's 28-case taxonomy; active/all = GARAK defaults.",
    )
    parser.add_argument(
        "--rc-mode", required=True, choices=["on", "off", "direct"],
        help="on = framework + JSON-mode + webhook via AG :1235; "
             "off = AG passthrough on :1237; "
             "direct = bypass AG, hit LM Studio at :1234 (A/B baseline only).",
    )
    parser.add_argument("--smoke", action="store_true", help="Single probe (lmrc.QuackMedicine), one attempt.")
    parser.add_argument("--generations", type=int, default=None)
    parser.add_argument(
        "--parallel-attempts", type=int, default=8,
        help="GARAK --parallel_attempts. LM Studio + AG handle concurrent requests; "
             "empirical ~1.9x speedup on 4-way fan-out, more on longer probes. Default 8.",
    )
    parser.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    args = parser.parse_args()

    if not VENV_PYTHON.exists():
        print(f"ERROR: garak venv not found at {VENV_PYTHON}", file=sys.stderr)
        return 1

    model_info = LOCAL_MODELS[args.model]
    model_id = model_info["model_id"]
    template = TEMPLATE_BY_MODE[args.rc_mode]
    if not template.exists():
        print(f"ERROR: config template not found: {template}", file=sys.stderr)
        return 1

    scope_label = "smoke" if args.smoke else args.scope
    cell = f"garak_{scope_label}_rc_{args.rc_mode}"
    run_id = make_run_id()
    run_dir = REPO_ROOT / EXPERIMENTS_ROOT / args.model / cell / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report_prefix = str(run_dir / "garak")

    config_path = build_runtime_config(template, model_id, args.model, scope_label, args.rc_mode)
    shutil.copy(config_path, run_dir / "rest_config.json")

    cmd: list[str] = [
        str(VENV_PYTHON), "-m", "garak",
        "--target_type", "rest",
        "--generator_option_file", str(config_path),
        "--report_prefix", report_prefix,
    ]
    if args.smoke:
        probes_arg = "lmrc.QuackMedicine"
        generations_arg = 1
    else:
        probes_arg = resolve_scope(args.scope)
        generations_arg = args.generations
    if probes_arg is not None:
        cmd += ["--probes", probes_arg]
    if generations_arg is not None:
        cmd += ["--generations", str(generations_arg)]
    if args.parallel_attempts and args.parallel_attempts > 1:
        cmd += ["--parallel_attempts", str(args.parallel_attempts)]
    cmd += args.extra

    print(f"[run_garak] model={args.model} ({model_id})")
    print(f"[run_garak] cell={cell}  run_id={run_id}")
    print(f"[run_garak] rc_mode={args.rc_mode}")
    print(f"[run_garak] run_dir={run_dir}")
    print(f"[run_garak] cmd: {' '.join(cmd)}")
    print()

    (run_dir / "command.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")

    # Pre-flight manifest so even a crashed run has provenance.
    framework_path_abs = REPO_ROOT / FRAMEWORK_PATH_REL
    framework_xml = framework_path_abs.read_text(encoding="utf-8") if framework_path_abs.exists() else ""
    framework_sha = sha256_of_file(framework_path_abs)
    probes_recorded = []
    if probes_arg and probes_arg != "all":
        probes_recorded = probes_arg.split(",")
    elif probes_arg == "all":
        probes_recorded = ["all"]

    def _build_manifest(status: str, gx_version, gx_exit, gx_probes_seen, end_iso, warm_secs) -> RunManifest:
        return RunManifest(
            run_id=run_id,
            schema_version=1,
            started_at=started,
            ended_at=end_iso,
            model=ModelInfo(short_name=args.model, model_id=model_id, provider="lmstudio"),
            framework=FrameworkInfo(
                enabled=(args.rc_mode == "on"),
                framework_path=FRAMEWORK_PATH_REL if args.rc_mode == "on" else None,
                framework_sha256=framework_sha if args.rc_mode == "on" else None,
                framework_token_estimate=(len(framework_xml) // 4) if args.rc_mode == "on" else 0,
            ),
            suite=SuiteInfo(
                kind="garak",
                garak_version=gx_version,
                garak_scope=scope_label,
                garak_probes=probes_recorded,
                garak_generations=generations_arg,
            ),
            settings=ModelSettings(temperature=0.7, max_tokens=2048, timeout=600),
            notes={
                "status": status,
                "rc_mode": args.rc_mode,
                "garak_exit_code": gx_exit,
                "garak_command": " ".join(cmd),
                "rest_config_sha256": sha256_of_file(run_dir / "rest_config.json"),
                "probes_requested": probes_recorded,
                "probes_expanded": gx_probes_seen,
                "warm_up_seconds": warm_secs,
            },
            outputs={
                "garak_jsonl": "garak.report.jsonl",
                "garak_summary": "garak.summary.json",
                "rest_config": "rest_config.json",
                "command": "command.txt",
            },
        )

    started = _dt.datetime.now(_dt.timezone.utc).isoformat()
    write_manifest(run_dir, _build_manifest("in_progress", None, None, [], None, None))
    print(f"[run_garak] pre-flight manifest written")

    # Warm cache only for RC ON — the framework prefix is what benefits.
    warm_secs = None
    if args.rc_mode == "on" and framework_xml:
        warmed, ws = warm_kv_cache(RC_ON_WARM_URI, model_id, framework_xml)
        warm_secs = round(ws, 2)
        print(f"[run_garak] KV-cache warm-up: {warm_secs}s ({'OK' if warmed else 'FAILED'})")

    env = os.environ.copy()
    env.setdefault("REST_API_KEY", "lm-studio")
    rc = subprocess.call(cmd, env=env)
    ended = _dt.datetime.now(_dt.timezone.utc).isoformat()

    report_jsonl = Path(f"{report_prefix}.report.jsonl")
    summary = parse_garak_jsonl(report_jsonl)
    with (run_dir / "garak.summary.json").open("w") as f:
        json.dump(summary, f, indent=2)
    expanded = sorted((summary.get("probes") or {}).keys())

    final = _build_manifest(
        "completed" if rc == 0 else "errored",
        summary.get("garak_version"),
        rc,
        expanded,
        ended,
        warm_secs,
    )
    write_manifest(run_dir, final)
    print(f"[run_garak] manifest finalised: {run_dir / 'manifest.json'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
