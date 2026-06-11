r"""
Run-provenance manifest and storage layout for the 4-cell experiment matrix.

Every run is one cell of:

  | suite \ framework | OFF (baseline)              | ON                          |
  |-------------------|-----------------------------|-----------------------------|
  | RC 28-case        | rc_baseline                 | rc_framework                |
  | GARAK <scope>     | garak_<scope>_baseline      | garak_<scope>_framework     |

Each run is preserved on disk so we can re-run, average, and dot-plot
across executions (LLM nondeterminism means a single run can mislead).

Filesystem layout:

  data/experiments/
    <model>/
      <cell>/
        <run_id>/
          manifest.json          ← this module writes/reads this
          sweep.json             ← RC sweep output (rc_* cells)
          garak.report.jsonl     ← raw GARAK output (garak_* cells)
          garak.summary.json     ← parsed per-probe eval rows (garak_* cells)

`<cell>` is `<suite>_<framework>` with optional `_<scope>` for GARAK.
`<run_id>` is an ISO-ish timestamp safe for filesystems: `2026-06-10T11-09-26Z`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EXPERIMENTS_ROOT = "data/experiments"


@dataclass
class ModelInfo:
    short_name: str
    model_id: str
    provider: str


@dataclass
class FrameworkInfo:
    enabled: bool
    framework_path: str | None = None
    framework_sha256: str | None = None
    framework_token_estimate: int | None = None


@dataclass
class SuiteInfo:
    kind: str  # "rc" | "garak"
    # RC-only
    rc_test_cases_path: str | None = None
    rc_test_cases_version: str | None = None
    rc_total_cases: int | None = None
    rc_strict_mode: bool | None = None
    # GARAK-only
    garak_version: str | None = None
    garak_scope: str | None = None  # curated | active | all | smoke
    garak_probes: list[str] = field(default_factory=list)
    garak_generations: int | None = None


@dataclass
class ModelSettings:
    temperature: float
    max_tokens: int
    timeout: int


@dataclass
class RunManifest:
    run_id: str
    schema_version: int
    started_at: str
    ended_at: str | None
    model: ModelInfo
    framework: FrameworkInfo
    suite: SuiteInfo
    settings: ModelSettings
    notes: dict[str, Any] = field(default_factory=dict)
    # Output paths are relative to this manifest's directory.
    outputs: dict[str, str] = field(default_factory=dict)


def make_run_id(when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return when.strftime("%Y-%m-%dT%H-%M-%SZ") + "_" + uuid.uuid4().hex[:6]


def cell_name(suite_kind: str, framework_enabled: bool, scope: str | None = None) -> str:
    """Build the per-cell directory name.

    rc_framework / rc_baseline / garak_curated_framework / garak_curated_baseline / ...
    """
    fw_label = "framework" if framework_enabled else "baseline"
    if suite_kind == "garak":
        if not scope:
            raise ValueError("garak cell requires scope")
        return f"garak_{scope}_{fw_label}"
    if suite_kind == "rc":
        return f"rc_{fw_label}"
    raise ValueError(f"unknown suite_kind: {suite_kind!r}")


def run_dir(repo_root: Path, model_short: str, cell: str, run_id: str) -> Path:
    return repo_root / EXPERIMENTS_ROOT / model_short / cell / run_id


def sha256_of_file(path: str | Path) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(target_dir: Path, manifest: RunManifest) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "manifest.json"
    # Atomic write: tmp + rename.
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(asdict(manifest), f, indent=2)
    os.replace(tmp, path)
    return path


def load_manifest(path: Path) -> RunManifest:
    with path.open() as f:
        data = json.load(f)
    return RunManifest(
        run_id=data["run_id"],
        schema_version=data["schema_version"],
        started_at=data["started_at"],
        ended_at=data.get("ended_at"),
        model=ModelInfo(**data["model"]),
        framework=FrameworkInfo(**data["framework"]),
        suite=SuiteInfo(**data["suite"]),
        settings=ModelSettings(**data["settings"]),
        notes=data.get("notes", {}),
        outputs=data.get("outputs", {}),
    )


def iter_runs(repo_root: Path, model_short: str | None = None) -> list[tuple[Path, RunManifest]]:
    """Walk experiments root and return (run_dir, manifest) for every run found."""
    base = repo_root / EXPERIMENTS_ROOT
    if not base.exists():
        return []
    out: list[tuple[Path, RunManifest]] = []
    pattern = f"{model_short}/*/*/manifest.json" if model_short else "*/*/*/manifest.json"
    for m_path in base.glob(pattern):
        try:
            out.append((m_path.parent, load_manifest(m_path)))
        except (json.JSONDecodeError, KeyError, TypeError):
            print(f"WARN: skipping bad manifest {m_path}", file=sys.stderr)
            continue
    return out
