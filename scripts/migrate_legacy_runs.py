#!/usr/bin/env python3
"""
One-shot migration of legacy artifacts into data/experiments/.

Migrates:
  data/results/local/sweep_*.json          -> data/experiments/<model>/rc_{framework|baseline}/<run_id>/
  garak/reports/<model>/<scope>/*.report.jsonl
                                          -> data/experiments/<model>/garak_<scope>_baseline/<run_id>/
  (Always treated as baseline — legacy garak runs predate --with-framework.)

Idempotent: if a destination dir already contains a manifest.json, the
source is skipped. Source files are *copied*, not moved, so the old
paths stay intact.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

sys.path.insert(0, str(HERE))
from experiment_manifest import (  # noqa: E402
    EXPERIMENTS_ROOT, FrameworkInfo, ModelInfo, ModelSettings, RunManifest,
    SuiteInfo, cell_name, make_run_id, sha256_of_file, write_manifest,
)

sys.path.insert(0, str(REPO_ROOT))
from config.local_models import LOCAL_MODELS  # noqa: E402


def _parse_garak_jsonl(path: Path) -> dict:
    """Inline copy of garak/run_garak.py::parse_garak_jsonl (different venv)."""
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
                p = summary["probes"].setdefault(
                    probe,
                    {"detectors": {}, "totals": {"passed": 0, "fails": 0, "total_evaluated": 0}},
                )
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


def _model_key_for(model_id: str) -> str | None:
    for k, v in LOCAL_MODELS.items():
        if v["model_id"] == model_id:
            return k
    return None


def _id_from_timestamp(ts: str | None, sweep_path: Path | None = None) -> str:
    """Derive a stable run_id from a timestamp; fall back to file mtime."""
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ") + "_legacy"
        except ValueError:
            pass
    if sweep_path and sweep_path.exists():
        mt = datetime.fromtimestamp(sweep_path.stat().st_mtime, tz=timezone.utc)
        return mt.strftime("%Y-%m-%dT%H-%M-%SZ") + "_legacy"
    return make_run_id()


def migrate_rc_sweep(path: Path) -> list[Path]:
    """Migrate one legacy sweep_*.json into one run dir per model_result inside it."""
    with path.open() as f:
        rep = json.load(f)
    framework_enabled = (rep.get("framework_token_count") or 0) >= 100
    framework_path = rep.get("framework") if framework_enabled else None
    framework_sha = sha256_of_file(REPO_ROOT / framework_path) if framework_path else None

    migrated: list[Path] = []
    for mr in rep.get("model_results", []):
        model_id = mr.get("model_id", "")
        mk = _model_key_for(model_id)
        if mk is None:
            print(f"  ↷ skipping unknown model_id {model_id!r}")
            continue
        run_id = _id_from_timestamp(rep.get("sweep_start"), path)
        cell = cell_name("rc", framework_enabled)
        run_dir = REPO_ROOT / EXPERIMENTS_ROOT / mk / cell / run_id
        if (run_dir / "manifest.json").exists():
            print(f"  ↷ {run_dir} already migrated")
            continue
        run_dir.mkdir(parents=True, exist_ok=True)
        # Write the per-model sweep.json (single ModelSweepResult-shaped).
        with (run_dir / "sweep.json").open("w") as f:
            json.dump(mr, f, indent=2)
        manifest = RunManifest(
            run_id=run_id,
            schema_version=1,
            started_at=rep.get("sweep_start") or "",
            ended_at=rep.get("sweep_end") or "",
            model=ModelInfo(short_name=mk, model_id=model_id, provider="lmstudio"),
            framework=FrameworkInfo(
                enabled=framework_enabled,
                framework_path=framework_path,
                framework_sha256=framework_sha,
                framework_token_estimate=rep.get("framework_token_count"),
            ),
            suite=SuiteInfo(
                kind="rc",
                rc_test_cases_path="tests/test_cases.json",
                rc_test_cases_version=None,  # unknown for legacy
                rc_total_cases=mr.get("total_cases"),
                rc_strict_mode=framework_enabled,  # legacy strict runs used framework; baseline didn't
            ),
            settings=ModelSettings(temperature=0.7, max_tokens=4096, timeout=120),
            notes={"migrated_from": str(path.relative_to(REPO_ROOT))},
            outputs={"sweep": "sweep.json"},
        )
        write_manifest(run_dir, manifest)
        migrated.append(run_dir)
        print(f"  ✓ {path.name} -> {run_dir}")
    return migrated


def migrate_garak_reports() -> list[Path]:
    """Migrate every reflexive-core/garak/reports/<model>/<scope>/run.report.jsonl into a cell."""
    src_root = REPO_ROOT / "garak" / "reports"
    if not src_root.exists():
        return []
    migrated: list[Path] = []
    for jsonl in src_root.glob("*/*/*.report.jsonl"):
        model_short = jsonl.parents[1].name
        scope = jsonl.parent.name
        if model_short not in LOCAL_MODELS:
            print(f"  ↷ skipping {jsonl} (unknown model)")
            continue
        # Legacy garak runs always had framework OFF.
        cell = cell_name("garak", framework_enabled=False, scope=scope)
        # Pull start_time from the JSONL init row.
        start_time = None
        garak_version = None
        with jsonl.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("entry_type") == "init":
                    start_time = r.get("start_time")
                    garak_version = r.get("garak_version")
                    break
        run_id = _id_from_timestamp(start_time, jsonl)
        run_dir = REPO_ROOT / EXPERIMENTS_ROOT / model_short / cell / run_id
        if (run_dir / "manifest.json").exists():
            print(f"  ↷ {run_dir} already migrated")
            continue
        run_dir.mkdir(parents=True, exist_ok=True)
        # Copy the jsonl + html if present
        shutil.copy(jsonl, run_dir / "garak.report.jsonl")
        html = jsonl.with_suffix(".html")
        if html.exists():
            shutil.copy(html, run_dir / "garak.report.html")
        # Parse and persist the summary (inline copy of the helper in
        # garak/run_garak.py — that file lives in a different venv so we
        # can't import it from here).
        summary = _parse_garak_jsonl(jsonl)
        with (run_dir / "garak.summary.json").open("w") as f:
            json.dump(summary, f, indent=2)
        manifest = RunManifest(
            run_id=run_id,
            schema_version=1,
            started_at=start_time or "",
            ended_at=summary.get("end_time") or "",
            model=ModelInfo(
                short_name=model_short,
                model_id=LOCAL_MODELS[model_short]["model_id"],
                provider="lmstudio",
            ),
            framework=FrameworkInfo(enabled=False),
            suite=SuiteInfo(
                kind="garak",
                garak_version=garak_version,
                garak_scope=scope,
                garak_probes=sorted(summary.get("probes", {}).keys()),
                garak_generations=None,
            ),
            settings=ModelSettings(temperature=0.7, max_tokens=2048, timeout=300),
            notes={"migrated_from": str(jsonl.relative_to(REPO_ROOT))},
            outputs={
                "garak_jsonl": "garak.report.jsonl",
                "garak_summary": "garak.summary.json",
            },
        )
        write_manifest(run_dir, manifest)
        migrated.append(run_dir)
        print(f"  ✓ {jsonl.relative_to(REPO_ROOT)} -> {run_dir}")
    return migrated


def main() -> int:
    print("== Migrating legacy RC sweeps ==")
    local_dir = REPO_ROOT / "data" / "results" / "local"
    rc_migrated: list[Path] = []
    if local_dir.exists():
        for sweep in sorted(local_dir.glob("sweep_*.json")):
            rc_migrated += migrate_rc_sweep(sweep)
    else:
        print("  (no data/results/local/ — nothing to migrate)")
    print(f"  total: {len(rc_migrated)}")

    print("\n== Migrating legacy GARAK reports ==")
    garak_migrated = migrate_garak_reports()
    print(f"  total: {len(garak_migrated)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
