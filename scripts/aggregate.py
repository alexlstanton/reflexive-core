#!/usr/bin/env python3
"""
Aggregate experiment runs into per-cell mean/std/per-run failure rates.

Walks data/experiments/<model>/<cell>/<run_id>/manifest.json, groups by
(model, cell), and computes per-normalized-category aggregates suitable
for dot-plots, error bars, or simple "is the framework helping?" deltas.

Output:
  data/experiments/<model>/_aggregated.json   — one per model
  data/experiments/_aggregated_summary.md      — terse cross-cell table
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

sys.path.insert(0, str(HERE))
from experiment_manifest import EXPERIMENTS_ROOT, RunManifest, iter_runs  # noqa: E402
from category_map import garak_family, normalize_garak, normalize_rc  # noqa: E402
from compare_suites import (  # noqa: E402
    _model_refused,
    _is_baseline,
)


# ─────────────────────────────────────────────────────────────────────────────
# Per-run failure rates by normalized category
# ─────────────────────────────────────────────────────────────────────────────

def rc_buckets_for_run(run_dir: Path, manifest: RunManifest) -> dict[str, dict[str, int]]:
    """Walk the per-model sweep.json in this run and return per-category {n_attempts, n_failures}."""
    sweep_path = run_dir / manifest.outputs.get("sweep", "sweep.json")
    if not sweep_path.exists():
        return {}
    with sweep_path.open() as f:
        mr = json.load(f)
    # save_experiment_runs writes a per-model ModelSweepResult, not a SweepReport.
    case_results = mr.get("case_results", [])
    is_baseline_run = not manifest.framework.enabled
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"n_attempts": 0, "n_failures": 0})
    for cr in case_results:
        cat = normalize_rc(cr.get("attack_type", "unknown"))
        b = buckets[cat]
        b["n_attempts"] += 1
        if is_baseline_run:
            raw = cr.get("raw_response") or ""
            refused = _model_refused(raw)
            expected = cr.get("expected_decision") or ""
            if expected == "BLOCKED":
                failed = not refused
            elif expected == "APPROVED":
                failed = refused
            else:
                failed = False
        else:
            failed = not cr.get("passed", False)
        if failed:
            b["n_failures"] += 1
    return dict(buckets)


def garak_buckets_for_run(run_dir: Path, manifest: RunManifest) -> dict[str, dict[str, int]]:
    """Use the per-probe garak.summary.json (eval rollups) bucketed by normalized cat."""
    summary_path = run_dir / manifest.outputs.get("garak_summary", "garak.summary.json")
    if not summary_path.exists():
        return {}
    with summary_path.open() as f:
        summary = json.load(f)
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"n_attempts": 0, "n_failures": 0})
    for probe, info in (summary.get("probes") or {}).items():
        cat = normalize_garak(probe)
        totals = info.get("totals") or {}
        buckets[cat]["n_attempts"] += int(totals.get("total_evaluated") or 0)
        buckets[cat]["n_failures"] += int(totals.get("fails") or 0)
    return dict(buckets)


# ─────────────────────────────────────────────────────────────────────────────
# Cell-level aggregation
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_cell(runs: list[tuple[Path, RunManifest]]) -> dict[str, Any]:
    """Aggregate a list of runs from the same cell into per-category stats."""
    per_run_rates: dict[str, list[float]] = defaultdict(list)
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"n_attempts": 0, "n_failures": 0})
    run_ids: list[str] = []

    for rd, m in runs:
        run_ids.append(m.run_id)
        if m.suite.kind == "rc":
            buckets = rc_buckets_for_run(rd, m)
        elif m.suite.kind == "garak":
            buckets = garak_buckets_for_run(rd, m)
        else:
            continue
        for cat, b in buckets.items():
            totals[cat]["n_attempts"] += b["n_attempts"]
            totals[cat]["n_failures"] += b["n_failures"]
            if b["n_attempts"] > 0:
                per_run_rates[cat].append(b["n_failures"] / b["n_attempts"])

    categories = {}
    for cat in sorted(set(totals) | set(per_run_rates)):
        rates = per_run_rates.get(cat, [])
        n_runs = len(rates)
        mean = stats.fmean(rates) if rates else 0.0
        stdev = stats.stdev(rates) if n_runs > 1 else 0.0
        agg = totals[cat]
        categories[cat] = {
            "n_runs": n_runs,
            "mean_failure_rate": mean,
            "stdev_failure_rate": stdev,
            "per_run_failure_rates": rates,
            "pooled_attempts": agg["n_attempts"],
            "pooled_failures": agg["n_failures"],
            "pooled_failure_rate": (agg["n_failures"] / agg["n_attempts"]) if agg["n_attempts"] else 0.0,
        }

    return {"run_ids": run_ids, "n_runs": len(run_ids), "categories": categories}


# ─────────────────────────────────────────────────────────────────────────────
# Main: group by (model, cell), aggregate each, write per-model summary
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="Aggregate runs for a single model (default: all).")
    parser.add_argument("--out-dir", default=EXPERIMENTS_ROOT)
    args = parser.parse_args()

    runs = iter_runs(REPO_ROOT, args.model)
    if not runs:
        print(f"No runs found under {REPO_ROOT / EXPERIMENTS_ROOT}.", file=sys.stderr)
        return 1

    # group by (model_short, cell)
    grouped: dict[tuple[str, str], list[tuple[Path, RunManifest]]] = defaultdict(list)
    for rd, m in runs:
        cell = rd.parent.name
        grouped[(m.model.short_name, cell)].append((rd, m))

    # aggregate per-model
    by_model: dict[str, dict[str, Any]] = defaultdict(lambda: {"cells": {}})
    for (model, cell), rs in sorted(grouped.items()):
        by_model[model]["cells"][cell] = aggregate_cell(rs)

    out_root = REPO_ROOT / args.out_dir
    summary_rows: list[dict[str, Any]] = []
    for model, data in by_model.items():
        out_path = out_root / model / "_aggregated.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as f:
            json.dump({"model": model, **data}, f, indent=2)
        print(f"[aggregate] {model}: {len(data['cells'])} cells -> {out_path}")
        for cell, agg in data["cells"].items():
            for cat, stats_ in agg["categories"].items():
                summary_rows.append({
                    "model": model,
                    "cell": cell,
                    "category": cat,
                    "n_runs": stats_["n_runs"],
                    "mean": stats_["mean_failure_rate"],
                    "stdev": stats_["stdev_failure_rate"],
                    "pooled_attempts": stats_["pooled_attempts"],
                    "pooled_failures": stats_["pooled_failures"],
                })

    # Markdown summary
    md_path = out_root / "_aggregated_summary.md"
    lines = ["# Aggregated experiments\n",
             "Mean ± stdev failure-rate per (model, cell, normalized category) "
             "across all completed runs.\n"]
    if not summary_rows:
        lines.append("\n_(no runs)_\n")
    else:
        lines.append("\n| Model | Cell | Category | Runs | Mean | Stdev | Pooled |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in summary_rows:
            pooled = f"{r['pooled_failures']}/{r['pooled_attempts']}"
            lines.append(
                f"| `{r['model']}` | `{r['cell']}` | `{r['category']}` | "
                f"{r['n_runs']} | {r['mean']*100:.1f}% | {r['stdev']*100:.1f} | {pooled} |"
            )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[aggregate] summary written: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
