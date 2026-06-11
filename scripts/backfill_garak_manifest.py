#!/usr/bin/env python3
"""
Back-fill a manifest.json for a GARAK run directory that's missing one
or has a stale one — reads the live garak.report.jsonl and the local
rest_config.json to reconstruct full provenance.

Use when a run was launched before run_garak.py wrote pre-flight manifests
(or to refresh a manifest mid-run for a still-in-progress job).

Usage:
    python scripts/backfill_garak_manifest.py <run_dir> \
        [--model <short>] [--with-framework] [--scope <s>] [--generations N] \
        [--framework-path PATH] [--command 'cmd...']
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

sys.path.insert(0, str(HERE))
from experiment_manifest import (  # noqa: E402
    FrameworkInfo, ModelInfo, ModelSettings, RunManifest, SuiteInfo,
    sha256_of_file, write_manifest,
)

sys.path.insert(0, str(REPO_ROOT))
from config.local_models import LOCAL_MODELS  # noqa: E402


def parse_jsonl(path: Path) -> dict:
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
            elif et == "attempt":
                probe = rec.get("probe_classname")
                if probe:
                    summary["probes"].setdefault(probe, {"detectors": {}, "totals": {"passed": 0, "fails": 0, "total_evaluated": 0}})
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
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--model", required=True, choices=list(LOCAL_MODELS.keys()))
    parser.add_argument("--with-framework", action="store_true")
    parser.add_argument("--scope", default="curated")
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--framework-path", default="framework/reflexive-core-prod.xml")
    parser.add_argument("--command", default="")
    parser.add_argument("--mark", choices=["in_progress", "completed", "errored"], default="in_progress")
    args = parser.parse_args()

    run_dir: Path = args.run_dir
    if not run_dir.is_dir():
        print(f"ERROR: {run_dir} is not a directory", file=sys.stderr)
        return 1
    jsonl = run_dir / "garak.report.jsonl"
    if not jsonl.exists():
        print(f"ERROR: no garak.report.jsonl in {run_dir}", file=sys.stderr)
        return 1

    summary = parse_jsonl(jsonl)
    # Also write/refresh the summary file so the aggregator picks it up.
    with (run_dir / "garak.summary.json").open("w") as f:
        json.dump(summary, f, indent=2)

    framework_path_abs = REPO_ROOT / args.framework_path if args.with_framework else None
    framework_sha = sha256_of_file(framework_path_abs) if framework_path_abs else None
    framework_token_estimate = 0
    if framework_path_abs and framework_path_abs.exists():
        framework_token_estimate = (framework_path_abs.stat().st_size // 4)

    run_id = run_dir.name
    started_iso = summary.get("start_time") or datetime.now(timezone.utc).isoformat()
    ended_iso = summary.get("end_time")

    rest_cfg = run_dir / "rest_config.json"
    model_id = LOCAL_MODELS[args.model]["model_id"]
    expanded = sorted(summary.get("probes", {}).keys())

    manifest = RunManifest(
        run_id=run_id,
        schema_version=1,
        started_at=started_iso,
        ended_at=ended_iso,
        model=ModelInfo(short_name=args.model, model_id=model_id, provider="lmstudio"),
        framework=FrameworkInfo(
            enabled=args.with_framework,
            framework_path=args.framework_path if args.with_framework else None,
            framework_sha256=framework_sha,
            framework_token_estimate=framework_token_estimate,
        ),
        suite=SuiteInfo(
            kind="garak",
            garak_version=summary.get("garak_version"),
            garak_scope=args.scope,
            garak_probes=[],  # unknown — original --probes arg not preserved here
            garak_generations=args.generations,
        ),
        settings=ModelSettings(temperature=0.7, max_tokens=2048, timeout=300),
        notes={
            "status": args.mark,
            "garak_exit_code": None,
            "garak_command": args.command or None,
            "rest_config_sha256": sha256_of_file(rest_cfg),
            "probes_requested": None,
            "probes_expanded": expanded,
            "backfilled": True,
            "backfilled_at": datetime.now(timezone.utc).isoformat(),
        },
        outputs={
            "garak_jsonl": "garak.report.jsonl",
            "garak_summary": "garak.summary.json",
            "rest_config": "rest_config.json",
        },
    )
    write_manifest(run_dir, manifest)
    print(f"[backfill] wrote {run_dir / 'manifest.json'}")
    print(f"[backfill] {len(expanded)} sub-probes seen so far")
    print(f"[backfill] eval rows captured: "
          f"{sum(p['totals']['total_evaluated'] for p in summary['probes'].values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
