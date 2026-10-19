# Quickstart

Use Python 3.10+ for the standard-library workflow. Run commands from the repository root.
Keep generated provider data and real model outputs in a separate local directory.

The [online example](https://jdding.github.io/rolemap/) runs the same core scripts
in your browser with fabricated inputs. It needs no account or local installation.
For the full source-integrity and interface checks, use the command below.

The [capability guide](docs/RESOURCE_CAPABILITIES.md) states which analyses run from the package alone and which need provider or user inputs.

## 1. Check the resource and run the synthetic example

```sh
python3 -I scripts/validate_release.py
```

Expected: `PASS_PUBLIC_RESOURCE_SMOKE`. The command checks file integrity, the current
protocol references, and the actual count, topology, mapping and prediction interfaces.
It uses eight fabricated items. No downloads, model calls or training are performed.
The optional checkpoint is not needed; downloaded parts are hash-checked when present.

| Output under `outputs/` | Read it for |
| --- | --- |
| `synthetic_role_topology.csv` | Task support, scores, tie-preserving cells and protocol identity |
| `synthetic_role_topology.json` | Medians, all four cell counts and source/output hashes |
| `synthetic_admission.json` | Map coverage and collision composition |
| `synthetic_collision_metrics.json` | Within-code support diagnostics |
| `synthetic_fixed_candidate_metrics.json` | Supplied-score metrics and their candidate domain |
| `interface_contract_checks.json` | Accepted inputs and explicit rejection cases |
| `public_resource_smoke_result.json` | Resource checks and their scope |

For a browser view, run `python3 -I scripts/serve_demo.py --port 8765`, open
<http://127.0.0.1:8765>, and select **Run synthetic workflow**.

## 2. Supply your own observations or model scores

Follow [Bring your own data](docs/BRING_YOUR_OWN_DATA.md). Configure your field names and
task values, import counts, then build a topology. Add a map over the same real item keys
for code-group analysis; add actual candidate scores for model inspection.
[The reconstruction protocol](docs/REBUILD_PROTOCOL.md) lists each command and schema.

## 3. Choose a real-data replay

| Workflow | Additional inputs | Entry point |
| --- | --- | --- |
| KuaiSAR or Qilin topology | Licensed provider files; optional provider readers | [Preprocessing](docs/PREPROCESSING_PROTOCOL.md) |
| Qilin temporal forecasts | Provider Parquet requests; shipped fixed maps and cohort | [Temporal reuse](analysis/reuse_validation/README.md) |
| Fixed UniSAR case | Release checkpoint; pinned source and processed KuaiSAR | [Complete replay](analysis/model_reuse/REPLAY.md) |

The full UniSAR runtime has separately pinned Python and package versions. The synthetic
workflow does not certify cross-platform numerical identity for a real model.
