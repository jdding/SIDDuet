# 1999-draw precision extension

This extends the band-matched and exact-total paired-count references from 199 to 1999 draws. Both reference definitions, data, mappings, strata, statistics, weighting and random streams are unchanged. Original 199-draw reports remain the baseline. No Control A, new observation, model fitting or threshold change is involved.

One PCG64 permutation stream is shared across the three mapping families within each dataset. KuaiSAR/Qilin seeds are 20262018/20262019 for band matching and 20263018/20263019 for exact totals. The first 199 aggregate draws reconstruct the old summaries; the local study also checked every retained aggregate value and all available exact-total permutation hashes.

Each of the two six-comparison families retains its own plus-one two-sided p calculation, BH adjustment and BY sensitivity. At 1999 draws, the two-sided resolution floor is 0.001. Reference ranges are central 95% simulation ranges, not confidence intervals for an observed effect.

The precision replay uses CPython 3.12.14 and NumPy 2.3.5, one CPU process with BLAS threads limited to one. The recorded local run took 114.35 seconds and 155.4 MiB peak RSS. The driver preserves a 600-second/1 GiB limit and refuses to overwrite output directories. Full streams, private manifests and execution paths are excluded from the reader package; reviewed aggregate comparisons are in reports/diagnostics_mc1999_20261020.

## Replay with lawful local inputs

Use the same five scientific inputs as the original analysis: two v2 topology CSVs and three normalized mapping CSVs. The manifest format is read by population_analysis.py. Files must match their declared SHA256 and byte lengths; real observations are not included here.

Set an installed matching Python and fresh paths outside the checkout:

    ROLEMAP_PY=/absolute/path/to/python3
    ROLEMAP_INPUTS=/absolute/path/to/INPUTS.json
    ROLEMAP_OUT=/absolute/path/to/new-mc1999-output
    ROLEMAP_PREFLIGHT=/absolute/path/to/new-mc1999-preflight.json

From the repository root, use the following options, first with --mode preflight and then --mode run:

    "$ROLEMAP_PY" -I -B analysis/diagnostic_extension_20261019/code/precision_extension.py \
    --mode preflight \
    --inputs "$ROLEMAP_INPUTS" \
    --population-code analysis/diagnostic_extension_20261019/code/population_analysis.py \
    --exact-code analysis/diagnostic_extension_20261019/code/exact_total_analysis.py \
    --primary-baseline reports/diagnostics_20261019/population/POPULATION_RESULTS.json \
    --exact-baseline reports/diagnostics_20261019/exact_total/EXACT_TOTAL_RESULTS.json \
    --out "$ROLEMAP_OUT" \
    --plan analysis/diagnostic_extension_20261019/protocols/MC1999_PRECISION.md \
    --preflight-record "$ROLEMAP_PREFLIGHT"

The output includes aggregate results and a 199-to-1999 comparison. Optional --primary-draws and --exact-draws paths provide value-by-value prefix checks when both original aggregate streams are available; they are not required to reconstruct the supplied baseline summaries.
