# Quickstart

Use Python 3.10+ for the standard-library workflows. Run commands from the repository root, or install the lightweight `sidduet` CLI with `python3 -m pip install -e .`. Keep generated provider data and real model outputs in a separate local directory.

The [online browser demo](https://jdding.github.io/SIDDuet/) executes the released Python scripts in your browser (pinned Pyodide, SHA-256 verified against `PACKAGE_MANIFEST.json`) across all three workflows with no account or local installation.

See [docs/RESOURCE_CAPABILITIES.md](docs/RESOURCE_CAPABILITIES.md) for what runs from the release alone versus provider or user inputs.

## 1. Verify Table 2 from the release

From a checkout of `v0.4.0`, run:

```sh
python3 -I -B scripts/verify_table2.py
# or, after `pip install -e .`:
sidduet verify-table2
```

The command prints all six primary Table 2 rows as CSV in ~0.04 s (<20 MiB RAM). It recomputes each reference mean and two-sided Monte Carlo p-value from the 1,999 saved draw means, then reapplies BH and BY across both six-comparison families. For KuaiSAR/GRID the printed row is `kuaisar,grid,3462,0.132,0.158,0.154,60.60%`. To rerun permutations from raw observations and normalized maps, follow the [study replay protocol](analysis/diagnostic_extension_20261019/protocols/MC1999_PRECISION.md).

## 2. Replay Qilin GenSAR shared-prefix calibration from public inputs

Obtain the `notes` shards and search/recommendation train and test Parquet files from the [pinned Qilin provider snapshot](https://huggingface.co/datasets/THUIR/Qilin/tree/2d79000cef450b99f6423357ce86e5c132d32dd5) under provider terms. Keep the five subdirectories and original filenames; [data/native_exports/QILIN_CALIBRATION_INPUTS.json](data/native_exports/QILIN_CALIBRATION_INPUTS.json) lists the nine files and their SHA-256 hashes.

In an environment with NumPy and PyArrow (`pip install -e ".[provider]"`):

```sh
python3 -I -B scripts/replay_qilin_calibration.py \
  --provider-root /path/to/qilin/snapshot --out-json /tmp/qilin-calibration.json
# or:
sidduet replay-qilin --provider-root /path/to/qilin/snapshot --out-json /tmp/qilin-calibration.json
```

Expected: `PASS_QILIN_CALIBRATION_EXAMPLE`. The report joins 20,540 of 20,540 paired items (100.00%) across 4,021 collision groups, with observed equal-group allocation JSD `0.069` vs. band-matched `0.087` and exact-total `0.086` (1,999 draws each; `p = 0.001`) and disjoint-leader rate `30.74%`. This bridges the calibration workflow to the primary GenSAR prefix view evaluated in Table 4.

## 3. Validate the release and run the synthetic workflows

```sh
python3 -I -B scripts/validate_release.py
# or:
sidduet validate
```

Expected: `PASS_PUBLIC_RESOURCE_SMOKE` (~2.8 s, ~26 MiB RAM). This checks complete SHA-256 manifest integrity, protocol contracts, and the synthetic count, map-join, collision, and fixed-candidate interfaces.

## 4. Calibrate your own counts and SID maps

With NumPy installed (`pip install -e ".[calibration]"`):

```sh
sidduet calibrate \
  --role-counts samples/synthetic_role_label_counts.csv \
  --sid-map demo-view=samples/synthetic_sid_map.csv \
  --draws 199 --seed 20261104 \
  --out-json /tmp/demo-cal.json --out-csv /tmp/demo-cal.csv
```

On a single CPU, 1,999 draws across both count-matched references take ~9.1 s (58 MiB peak RSS) at Qilin scale (20,540 items, 4,021 collision groups) and ~61.2 s (113 MiB peak RSS) at KuaiSAR scale (97,729 items, 3,462 groups). See [docs/COUNT_REFERENCE_CALIBRATION.md](docs/COUNT_REFERENCE_CALIBRATION.md) and [docs/BRING_YOUR_OWN_DATA.md](docs/BRING_YOUR_OWN_DATA.md) for custom schemas.

## 5. Run the local three-workflow web demo

```sh
sidduet demo --port 8765
# or:
python3 -I scripts/serve_demo.py --port 8765
```

Open <http://127.0.0.1:8765> and click **Run all three workflows**.
