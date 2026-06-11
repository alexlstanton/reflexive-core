# 4-Cell Local-Model Testing Methodology

Per-model experiment grid (one model loaded in LM Studio at a time):

|              | Reflexive-Core OFF (baseline)            | Reflexive-Core ON (framework)           |
|--------------|------------------------------------------|------------------------------------------|
| **RC suite** | `rc_baseline`                            | `rc_framework`                           |
| **GARAK**    | `garak_<scope>_baseline`                 | `garak_<scope>_framework`                |

`<scope>` ∈ `{curated, active, all, smoke}`. Each combination is one *cell*.
A *run* is one execution of a cell. We keep every run because output is
non-deterministic — comparing means/stds across multiple runs is the
only way to read the signal.

## Why all four cells

- `rc_framework` alone tells us how the model behaves with our framework on our prompts. Self-graded.
- `rc_baseline` strips the framework so we can measure model-native safety against the same prompts.
  The lift `(baseline − framework)` is the framework's contribution on our own tests.
- `garak_*_baseline` measures model-native safety against the industry-standard pack.
  Lets us calibrate our test pack — is ours harder, easier, or differently-shaped?
- `garak_*_framework` shows whether the framework's wrap defeats the industry probes too. **This is
  the headline number for a paper-style claim.** If the framework only catches our own attacks
  it isn't generalizable; if it catches GARAK probes the model alone fails on, that's real lift.

## How to run each cell

Pre-flight: load the target model in LM Studio (one at a time on
constrained hardware). Confirm with `curl http://127.0.0.1:1234/v1/models`.

```bash
# rc_framework  — RC's 28 cases, framework system prompt on
python run_sweep.py --provider lmstudio --models gemma4-e4b --strict

# rc_baseline   — same 28 cases, minimal "helpful assistant" system prompt
python run_sweep.py --provider lmstudio --models gemma4-e4b --baseline

# garak_<scope>_baseline  — industry probes, framework off
garak/.venv/bin/python garak/run_garak.py --model gemma4-e4b --scope curated --generations 1

# garak_<scope>_framework — industry probes, framework on
garak/.venv/bin/python garak/run_garak.py --model gemma4-e4b --scope curated --generations 1 \
    --with-framework
```

Every command writes one run into
`data/experiments/<model>/<cell>/<run_id>/` with a `manifest.json` plus the
suite-specific artifacts (`sweep.json` or `garak.report.jsonl` +
`garak.summary.json`).

`<run_id>` is `YYYY-MM-DDTHH-MM-SSZ_<6hex>` so they sort and stay unique.
Re-running the same command never overwrites — it adds a new run.

## Aggregating reruns

After ≥2 runs of any cell:

```bash
python scripts/aggregate.py --model gemma4-e4b
# writes data/experiments/gemma4-e4b/_aggregated.json
# writes data/experiments/_aggregated_summary.md  (table)
```

`_aggregated.json` keeps each run's per-category failure rate in a list
(`per_run_failure_rates`) so you can plot dots, draw error bars, or
re-aggregate with different statistics later. Pooled totals are also
preserved.

## 3-way / 4-way comparison

`scripts/compare_suites.py` builds a per-category table across:
framework / baseline / garak. With both RC modes present it reports
`framework_lift_pct` = `baseline_rate − framework_rate`.

```bash
python scripts/compare_suites.py --model gemma4-e4b --scope curated
# data/results/comparison/gemma4-e4b_curated_delta.{md,json}
```

The compare script auto-picks the most recent matching sweep — pass
`--rc-framework-path` / `--rc-baseline-path` to pin specific runs.

## Caveats / known limits

- **Baseline scoring uses a refusal-keyword heuristic.** The bare model
  can't emit RC's JSON schema, so we can't reuse the `passed` field
  from sweep.json. We instead flag failure when the model failed to
  refuse a BLOCKED-expected attack, or refused a benign request. This
  is coarse — false negatives if the model declines in unusual phrasing,
  false positives if a benign reply happens to include a refusal verb.
  Improve later with a judge model or per-case rubric.

- **Reasoning models (Gemma 4) burn output budget on `reasoning_content`.**
  We set `max_tokens=4096` for the RC suite and `2048` for GARAK. If a
  case returns empty `content`, the adapter falls back to
  `reasoning_content` so downstream scoring sees *something*.

- **GARAK + framework increases prompt size by ~5k tokens per attempt.**
  Real cost on the time axis: framework-on GARAK runs are slower than
  baseline. Plan accordingly when sizing scope.

- **LM Studio rejects empty content (HTTP 400).** `test.Blank` will fail.
  `lmrc.QuackMedicine` is the recommended single-prompt smoke probe.

## File map

```
config/local_models.py        – dep-free registry of local model keys
src/models/lmstudio_adapter.py – OpenAI-compat client w/ reasoning fallback
run_sweep.py                  – RC sweep, writes sweep.json + manifest
garak/run_garak.py            – GARAK wrapper, --with-framework flag, writes manifest
garak/configs/lmstudio.json   – REST generator template
garak/probe_sets.py           – curated / active / all scope definitions
scripts/experiment_manifest.py – manifest schema + iter_runs()
scripts/category_map.py       – RC ↔ GARAK ↔ normalized taxonomy
scripts/compare_suites.py     – 3-way delta report
scripts/aggregate.py          – mean / std / per-run across reruns
scripts/migrate_legacy_runs.py – one-shot folder of pre-experiments data
data/experiments/             – durable storage, one dir per run
```
