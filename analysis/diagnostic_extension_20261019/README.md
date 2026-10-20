# Optional fixed-resource diagnostics

The [1999-draw precision extension](protocols/MC1999_PRECISION.md) retains the original 199-draw baselines and reports a higher-budget check with unchanged references. See the [aggregate comparison](../../reports/diagnostics_mc1999_20261020/README.md).

The Python sources in `code/` implement the declared primary and supplementary comparisons. The public CLI removes the original author-workflow approval requirement while retaining input hashes, fixed seeds, draw counts, marginals and result checks. The study definitions are in `protocols/`. The aggregate findings and export identities are in [reports/diagnostics_20261019](../../reports/diagnostics_20261019/README.md). These analyses leave the v2 topology, its reference hashes and the release's synthetic quickstart unchanged.

The scripts use an optional installed NumPy runtime. The recorded reference was CPython 3.12.14 + NumPy 2.3.5 on macOS; the standard-library-only core quickstart does not need NumPy. No installation, API, model or GPU is invoked by the commands below.

## Check the code with fabricated observations

Run from the release root with an installed Python that has NumPy 2.3.5. Keep every output outside the release directory:

```sh
TASK_PYTHON=/absolute/path/to/python3
TASK_CHECKS=$(mktemp -d "${TMPDIR:-/tmp}/rolemap-diagnostic-checks.XXXXXX")

"$TASK_PYTHON" -I -B analysis/diagnostic_extension_20261019/code/population_analysis.py \
  test --out "$TASK_CHECKS/population"

"$TASK_PYTHON" -I -B analysis/diagnostic_extension_20261019/code/exact_total_analysis.py \
  --population-code analysis/diagnostic_extension_20261019/code/population_analysis.py \
  test --out "$TASK_CHECKS/exact_total"

"$TASK_PYTHON" -I -B analysis/diagnostic_extension_20261019/code/tie_source_analysis.py \
  --self-test "$TASK_CHECKS/ties"

"$TASK_PYTHON" -I -B analysis/diagnostic_extension_20261019/code/threshold_sensitivity.py \
  --self-test "$TASK_CHECKS/thresholds"
```

Each command reports PASS and writes its fabricated-data checks under the chosen temporary directory. The tie and threshold tests require fresh output paths. They also run small implementation benchmarks, which are not real dataset measurements or model-training results. Use each script's `--help` to inspect its exact frozen interface.

## Real data replay has additional requirements

Real replay needs lawful local source counts/topologies, the same supplied maps and admission metadata, a manifest binding actual paths and hashes, and fresh output directories outside the checkout. Use `--help` and each script's input validation to construct these declared inputs. The fixed protocols specify the grouping, support strata, seeds, 199 simulation draws and weighting rules. No independent approval receipt is required by the public CLI. The optional `--provenance-receipt` checks local input/code hash bindings. The former `--acceptance-receipt` flag remains an alias; no author approval value is required.

For the exact-total supplement, use the shipped `reports/diagnostics_20261019/population/POPULATION_RESULTS.json` as `--primary-results` and the shipped population helper as `--population-code`; both are hash-bound. The supplement checks observed results against that primary reference before comparing its alternative regrouping.

The aggregate reports retain original execution/source hashes, so their provenance refers to the study implementation. Public packaging changes only CLI/provenance handling and the helper/reference hash constants. Complete simulation draws and machine-specific execution manifests are not shipped. Synthetic checks verify the calculations; real-map replay additionally requires the lawful corresponding inputs.

The main [rebuild protocol](../../docs/REBUILD_PROTOCOL.md) describes provider adapters and topology/mapping interfaces. It does not grant upstream access rights or distribute role-count tables, full provider data or restricted joins. The three approved Qilin catalog maps and cohort are the separately documented exception; other complete mappings are not included. Acquire any required upstream inputs under their own terms. No model training or new mapping fit is part of these optional diagnostics.
