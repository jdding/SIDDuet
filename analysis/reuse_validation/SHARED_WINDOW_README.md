# A shared-calendar temporal check

The question is whether keeping task-specific observations improves later exposed-member forecasts within a supplied code group. This check uses the original estimators, tuning rule, smoothing grid, GenSAR primary and maps. Only the chronological partition and its earlier data change. It is retrospective and conditions on the previously selected 20,540-item cohort.

## Choose the period from coverage

The census reads the four pinned provider train/test Parquet files using user/session/request indices and result details. It uses times and exposures; clicks, query/history text, fitted predictions and losses do not select the window. Each calendar bin counts requests wholly contained within that half-hour.

After the first audit ending at 2024-11-27 11:14:47 UTC, the earliest and only continuous run with real requests in both tasks spans eight bins: 11:30–15:30 UTC. The whole four-hour run was fixed before fitting. The [calendar census](results/shared_window_coverage/CALENDAR_BINS.csv) lists occupied half-hour bins and task-specific zero counts; an absent bin has no wholly contained request from either task. Requests crossing either selected boundary are excluded rather than truncated.

The [protocol](SHARED_WINDOW_PROTOCOL.md) and [window definition](SHARED_WINDOW.json) retain the original shared user-hash partition. Earlier requests train the count estimators; the later window supplies tuning and evaluation users, disjoint across both tasks. Provider split labels remain provenance. The new evaluation partly reuses the recommendation period of the earlier disjoint-calendar transport check; it is not a new official benchmark split or an untouched independent dataset.

## Reconstruct locally

Use the original Qilin provider files and the optional research dependencies. From the repository root, set absolute paths outside the checkout. No request rows are shipped.

```sh
export ROLEMAP_ROOT="$PWD"
export QILIN_PROVIDER=/local/provider/qilin/hf_snapshot
export WINDOW_WORK=/local/new/shared_window_replay

python3 analysis/reuse_validation/shared_window.py --mode coverage \
  --provider-root "$QILIN_PROVIDER" \
  --cohort data/native_exports/cohort.csv \
  --primary-map data/native_exports/native_maps/gensar_semantic.csv \
  --cache "$WINDOW_WORK/restricted/calendar.jsonl" \
  --out "$WINDOW_WORK/coverage"

python3 analysis/reuse_validation/export_shared_window.py \
  --cache "$WINDOW_WORK/restricted/calendar.jsonl" \
  --coverage "$WINDOW_WORK/coverage/COVERAGE.json" \
  --window analysis/reuse_validation/SHARED_WINDOW.json \
  --protocol analysis/reuse_validation/SHARED_WINDOW_PROTOCOL.md \
  --primary-map data/native_exports/native_maps/gensar_semantic.csv \
  --out "$WINDOW_WORK/restricted/inputs"

(
  cd "$ROLEMAP_ROOT/data/native_exports"
  python3 "$ROLEMAP_ROOT/analysis/reuse_validation/allocation_forecast.py" \
    --mode fit --input "$WINDOW_WORK/restricted/inputs" \
    --out "$WINDOW_WORK/restricted/fit" --maps-manifest MAPS.json \
    --manifest "$WINDOW_WORK/restricted/inputs/EXTRACTION_RECEIPT.json" \
    --protocol "$ROLEMAP_ROOT/analysis/reuse_validation/SHARED_WINDOW_PROTOCOL.md"

  python3 "$ROLEMAP_ROOT/analysis/reuse_validation/allocation_forecast.py" \
    --mode evaluate --evaluation-split audit \
    --input "$WINDOW_WORK/restricted/inputs" \
    --fitted "$WINDOW_WORK/restricted/fit/restricted/FITTED.json" \
    --out "$WINDOW_WORK/restricted/evaluation" --maps-manifest MAPS.json \
    --manifest "$WINDOW_WORK/restricted/inputs/EXTRACTION_RECEIPT.json" \
    --protocol "$ROLEMAP_ROOT/analysis/reuse_validation/SHARED_WINDOW_PROTOCOL.md"
)
```

To obtain the simultaneous intervals, reconstruct the original-window losses using the [original instructions](README.md), then supply both local loss directories:

```sh
python3 analysis/reuse_validation/compare_time_windows.py \
  --original-scores /local/original_evaluation/restricted \
  --original-results /local/original_evaluation/RESULTS.json \
  --shared-scores "$WINDOW_WORK/restricted/evaluation/restricted" \
  --shared-results "$WINDOW_WORK/restricted/evaluation/RESULTS.json" \
  --out "$WINDOW_WORK/two_window_sensitivity" --draws 40000
```

The script first reconstructs each view's 2,000-draw pointwise intervals and means within 1e-12. It then reports five-view 99% marginal intervals per window and ten-endpoint 99.5% marginal intervals across the two windows, each targeting nominal 95% family coverage by Bonferroni. The percentile bootstrap is approximate and conditional on the fixed cohort, maps and fits. Shared users do not violate the Bonferroni construction, which does not require independent endpoints.

## What changes in the conclusion

The primary loss reductions are 0.012686 and 0.008504 nats (0.74% and 0.48% of baseline macro loss). Their original pointwise intervals are positive, while only the additional window excludes zero under the ten-endpoint sensitivity. GAOQ's two-token prefix has positive adjusted intervals in both windows; GenSAR's collaborative complete view remains near zero. All ten estimates and both sensitivity families are supplied in [the aggregate result](results/two_window_sensitivity/TWO_WINDOW_SENSITIVITY.json).

The original primary tuning selects pooled/separate estimates with alpha 10; the additional window selects pooled alpha 100 and shrinkage beta 100. These are outputs of the unchanged tuning procedure, not manually selected replacements. The larger estimated task decrease changes from search to recommendation. This experiment does not isolate temporal distribution changes from changes in fitted counts or selected shrinkage.

Both windows lie on one day; 563 primary-view users appear in both. This strengthens the concrete temporal-use example while leaving longer-term and cross-dataset transfer untested. It does not establish ranking gains, causal task interference or predictive validity of the contextual-label indices. Numerical results are reproducible with the declared runtime; receipt metadata containing elapsed times and local paths can differ.
