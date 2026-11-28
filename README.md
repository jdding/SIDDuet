# SIDDuet

[SIDDuet v0.4.2](https://github.com/jdding/SIDDuet/releases/tag/v0.4.2) is an open-source diagnostic toolkit, paired-observation protocol, and benchmark reproduction package for inspecting shared Semantic IDs (SIDs) across search and recommendation.

Without retraining tokenizers, SIDDuet joins existing item-to-code maps to paired search and recommendation observations across **three diagnostic workflows**:

| Workflow | Core question | Entry point |
| --- | --- | --- |
| **1. Shared-code calibration** | Which items drive search vs. recommendation traffic within shared codes, and is the divergence unusual for their count volumes? | `sidduet calibrate` · [`sidduet inspect-groups`](docs/COUNT_REFERENCE_CALIBRATION.md#inspect-individual-groups) · [Calibration guide](docs/COUNT_REFERENCE_CALIBRATION.md) |
| **2. Prediction coverage** | Which test requests have paired observations for their targets, and how do covered ranking scores compare with the full test? | [UniSAR replay & coverage](analysis/model_reuse/REPLAY.md) |
| **3. Temporal pooling** | Does keeping task counts separate reduce future within-code exposure-allocation forecast loss relative to pooled counts? | [Temporal reuse protocol](analysis/reuse_validation/README.md) · [Cohort sensitivity](analysis/cohort_sensitivity/README.md) |

See [what the release supports](docs/RESOURCE_CAPABILITIES.md) for package-only, provider-input, and own-data workflows, and [how SIDDuet complements SIDInspector](docs/RELATION_TO_SIDINSPECTOR.md).

## Try it online (zero install)

Open the [live browser demo](https://jdding.github.io/SIDDuet/) to run all three workflows directly in your browser using a pinned standard-library Pyodide runtime:

- **Workflow 1:** Computes per-group allocation JSD, interactive member share bars, band-matched and exact-total count-matched permutation references on the synthetic fixture, and runs `scripts/verify_table2.py` live on the 1,999 saved Monte Carlo draw means.
- **Workflow 2:** Computes paired-target coverage and both NDCG@10 scores on the same synthetic candidate sets, alongside the archived UniSAR/KuaiSAR Table 3 summary.
- **Workflow 3:** Scores pooled, separate, and shrinkage rules on held-out synthetic counts with fixed smoothing strengths. The Qilin summaries show pooled loss minus the loss of the task-conditioned rule selected on tuning users.

All executed scripts and summary files are SHA-256 verified against `PACKAGE_MANIFEST.json` before execution; nothing leaves your browser.

## Install and Quickstart

Use Python 3.10+ from a SIDDuet checkout. The standard library covers verification and the synthetic workflows. The CLI uses an editable install so it can find scripts and artifacts in the checkout. Add NumPy with `.[calibration]` or NumPy and PyArrow with `.[provider]` for Qilin Parquet replay.

From the root of your SIDDuet checkout or unpacked source archive:

```sh
# Install the sidduet CLI from this checkout
python3 -m pip install -e .

# 1. Verify the six main Table 2 rows from saved draws
sidduet verify-table2          # or: python3 -I -B scripts/verify_table2.py

# 2. Check SHA-256 manifest integrity and run the standard-library smoke suite
sidduet validate               # or: python3 -I -B scripts/validate_release.py

# 3. Launch the local browser interface
sidduet demo --port 8765       # or: python3 -I scripts/serve_demo.py --port 8765
```

For your own counts and item-to-code maps, map local CSV columns with `sidduet import-counts` ([Bring your own data](docs/BRING_YOUR_OWN_DATA.md)) and run `sidduet calibrate` ([Count-reference calibration](docs/COUNT_REFERENCE_CALIBRATION.md)):

```sh
python3 -m pip install -e ".[calibration]"
sidduet calibrate \
  --role-counts /path/to/counts.csv \
  --sid-map baseline=/path/to/baseline.csv \
  --sid-map candidate=/path/to/candidate.csv \
  --draws 1999 --seed 20261104 \
  --out-json /tmp/calibration.json --out-csv /tmp/calibration.csv
```

See [ARTIFACT_QUICKSTART.md](ARTIFACT_QUICKSTART.md) for the Qilin provider-file replay (`sidduet replay-qilin`) and complete command reference.

## Measured CPU Runtime and Memory

Single-machine CPU benchmarks (Python 3 + NumPy, no GPU required):

| Workload | Scale | Wall time | Peak RSS |
| --- | --- | ---: | ---: |
| `sidduet verify-table2` | 6 rows × 2 references × 1,999 saved draws | 0.04 s | 19 MiB |
| `sidduet validate` | Full SHA-256 manifest + smoke suite | 2.8 s | 26 MiB |
| `sidduet calibrate` (Qilin scale) | 20,540 items, 4,021 groups, 1,999 draws × 2 refs | 9.1 s | 58 MiB |
| `sidduet calibrate` (KuaiSAR scale) | 97,729 items, 3,462 groups, 1,999 draws × 2 refs | 61.2 s | 113 MiB |
| Two-window pooling bootstrap | 40,000 paired user-cluster draws, 10 endpoints | 6.9 s | — |

## Relationship to SIDInspector

[SIDInspector](docs/RELATION_TO_SIDINSPECTOR.md) evaluates single-task Semantic-ID mappings (utilization, aliasing, behavioral alignment). SIDDuet operates on a **paired two-task observation contract** `(S_i, R_i)` over shared catalog keys: it calibrates within-code search-vs.-recommendation allocation divergence against count-matched regroupings that preserve each item's task-count pair, audits paired-target prediction coverage on joint models, and compares pooled vs. task-conditioned exposure forecasts across time windows.

## Data and Method Coverage

| Evidence | Verified scope |
| --- | --- |
| Paired task observations | KuaiSAR: 97,729 common items; Qilin: 20,540 common items |
| Native semantic-ID components | GenSAR quantizer and ReSID GAOQ; six declared Qilin code views |
| Real joint-model predictions | UniSAR: 166,981 original 100-candidate test requests (2.93%–3.18% paired target coverage) |
| Historical study preservation | Original `v0.2.8` study reports and `v0.2.4` checkpoint assets preserved unchanged |

See [docs/METHOD_COVERAGE.md](docs/METHOD_COVERAGE.md) and [reports/README.md](reports/README.md) for full provenance and boundaries.

## Reproduce the Real Examples

- **Qilin exposure-allocation forecasts** ([guide](analysis/reuse_validation/README.md)): uses the three shipped 20,540-item native maps and cohort under `data/native_exports/`. Obtain request Parquet files from the Qilin provider; no quantizer retraining is needed.
- **Complete UniSAR replay** ([guide](analysis/model_reuse/REPLAY.md)): download the separately licensed checkpoint parts from [v0.2.4](https://github.com/jdding/SIDDuet/releases/tag/v0.2.4) and obtain the pinned upstream source and processed KuaiSAR files.
- **Provider reconstruction** ([guide](docs/PREPROCESSING_PROTOCOL.md)): rebuild paired observations and contextual-label summaries locally from licensed KuaiSAR/Qilin files.

## License, Privacy, and Compatibility

- **Licenses (per file):** Code in `sidduet/`, `scripts/`, and `analysis/` is MIT; documentation and aggregate summaries are CC BY 4.0; derived Qilin catalog maps under `data/native_exports/` are Apache-2.0; optional UniSAR checkpoint parts under `weights/unisar_kuaisar_v1/` are CC BY-NC-SA 4.0. See [LICENSE](LICENSE) and [docs/ETHICS_AND_LICENSE.md](docs/ETHICS_AND_LICENSE.md).
- **Privacy boundary:** Raw logs, user identifiers, query text, trajectories, and item-level paired label distributions are excluded from the release.
- **Naming compatibility:** SIDDuet was previously named RoleMap; legacy script paths, JSON schemas, and protocol identifiers (`sr_sid_rolemap.topology.value_median.v2`) remain supported unchanged for backward compatibility.
