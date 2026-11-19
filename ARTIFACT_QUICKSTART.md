# Quickstart

Use Python 3.10+ for the standard-library workflow. Run commands from the repository root.
Keep generated provider data and real model outputs in a separate local directory.

The [online example](https://jdding.github.io/SIDDuet/) runs the same core scripts
in your browser with fabricated inputs. It needs no account or local installation.
For the full source-integrity and interface checks, use the command below.

The [capability guide](docs/RESOURCE_CAPABILITIES.md) states which analyses run from the package alone and which need provider or user inputs.

## 1. Verify Table 2 from the release

From a checkout of the cited release, run:

~~~sh
python3 -I -B scripts/verify_table2.py
~~~

The command prints all six Table 2 rows as CSV. It computes each reference
mean and two-sided Monte Carlo p value from the 1,999 saved draw means,
then reapplies BH and BY to the two six-comparison families. For KuaiSAR/GRID
the printed row is `kuaisar,grid,3462,0.132,0.158,0.154,60.60%`.
Observed JSD and leader counts are read from the shipped study report. To
rerun the permutations, use the original paired observations and three
normalized maps listed in the [study replay protocol](analysis/diagnostic_extension_20261019/protocols/MC1999_PRECISION.md).

## 2. Run a calibration from public Qilin inputs

Get the `notes` shards and the search and recommendation train and test
Parquet files from the [pinned Qilin provider snapshot](https://huggingface.co/datasets/THUIR/Qilin/tree/2d79000cef450b99f6423357ce86e5c132d32dd5)
under the provider terms. Keep the five subdirectories and original filenames.
The [input inventory](data/native_exports/QILIN_CALIBRATION_INPUTS.json)
lists the nine files and their hashes.

Use Python 3.12 in a fresh environment. This command reads the provider files
locally, joins the paired item counts to the released GenSAR two-token prefix,
and runs both count references. Replace the input directory and choose a
fresh report path in an existing directory.

~~~sh
python3.12 -m venv /tmp/sidduet-provider-env
/tmp/sidduet-provider-env/bin/python -m pip install numpy==2.3.5 pyarrow==21.0.0
/tmp/sidduet-provider-env/bin/python -I -B scripts/replay_qilin_calibration.py \
  --provider-root /path/to/qilin/snapshot --out-json /tmp/qilin-calibration.json
~~~

Expected: `PASS_QILIN_CALIBRATION_EXAMPLE`. The report joins 20,540 of 20,540
paired items (100.00%), with 4,021 collision groups. The disjoint-leader rate is
30.74%. Observed equal-group JSD is 0.069, with band-matched and exact-total
reference means of 0.087 and 0.086 (1,999 draws each). Read the leader rate
alongside the reference means before interpreting the difference in task
support. The report is an example of the general calibration interface on
the declared Qilin prefix. It uses a different code view from the historical
Table 2 comparisons and does not fit an exposure forecast.

## 3. Check the resource and run the synthetic example

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

## 4. Supply your own observations or model scores

Follow [Bring your own data](docs/BRING_YOUR_OWN_DATA.md). Configure your field names and
task values, import counts, then build a topology. Add a map over the same real item keys
for code-group analysis; add actual candidate scores for model inspection.
[The reconstruction protocol](docs/REBUILD_PROTOCOL.md) lists each command and schema.
Use [count-reference calibration](docs/COUNT_REFERENCE_CALIBRATION.md) to
compare your own member allocations with band-matched and exact-total
regroupings, with no fixed dataset names or catalog sizes.

## 5. Choose a real-data replay

| Workflow | Additional inputs | Entry point |
| --- | --- | --- |
| KuaiSAR or Qilin topology | Licensed provider files; optional provider readers | [Preprocessing](docs/PREPROCESSING_PROTOCOL.md) |
| Qilin temporal forecasts | Provider Parquet requests; shipped fixed maps and cohort | [Temporal reuse](analysis/reuse_validation/README.md) |
| Fixed UniSAR case | Release checkpoint; pinned source and processed KuaiSAR | [Complete replay](analysis/model_reuse/REPLAY.md) |

The full UniSAR runtime has separately pinned Python and package versions. The synthetic
workflow does not certify cross-platform numerical identity for a real model.
