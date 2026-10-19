# Multiplicity sensitivity of the historical audit

This posthoc analysis keeps the original fits, user partition, maps, point estimates and primary designation. GenSAR's shared two-token prefix was designated before this audit; the cohort and source data had already been used, so this is retrospective validation. The two complete GenSAR views share this prefix, providing an outcome-independent reason to inspect it.

Five views have estimable macro-role loss differences. The GAOQ full-code row has no collisions and no loss endpoint; it is a control, not a sixth hypothesis.

The script reproduces the original 2,000-draw pointwise intervals, then extends the same paired user-cluster random stream to 20,000 draws. For a five-view family at nominal 95% coverage, each marginal percentile interval uses the 0.005 and 0.995 quantiles (99%). Bonferroni does not require independence among views. Bootstrap coverage is approximate and conditional on the fixed cohort, fit, mapping and time window. Increasing the draw count adds no new observations.

## Run

First reconstruct and evaluate the historical requests with `allocation_forecast.py`; keep its per-request losses local. Then run:

```sh
python3 analysis/reuse_validation/multiplicity_sensitivity.py \
  --scores-dir /local/audit_results/restricted \
  --reference-results /local/audit_results/RESULTS.json \
  --out /local/new/multiplicity_results
```

It needs NumPy and the original loss-row fields `request_hash,user_hash,role,blind_loss,aware_loss,delta`. It checks all original point estimates and task/macro intervals within 1e-12 before emitting new results. Only aggregates and input hashes are written. The release does not contain these private loss rows; obtain provider inputs and reconstruct them using the temporal instructions.

## Interpretation

The GenSAR primary estimate stays 0.012686 nats. Its original pointwise 95% interval excludes zero, but the conservative five-view interval includes zero. The secondary GAOQ two-token prefix remains positive after this adjustment. The primary has not been switched to that view. Complete-code results do not supply consistent evidence of an advantage.

`results/multiplicity_audit/` contains all five estimates, both interval conventions and reconstruction checks. These results support comparing pooling choices separately for each evaluation view; they do not establish universal task separation, ranking gains, cross-dataset replication or repeated-window robustness.

## Comparison families

This sensitivity covers the five macro-role temporal loss endpoints, not every exploratory statistic in the resource. The population analysis separately defines six primary band-matched comparisons and six supplementary exact-total comparisons, with BH and BY summaries within each six-comparison family. Checkpoint coverage and label-stratified NDCG intervals are descriptive analyses; no familywise confirmatory claim is made for them.

## Additional shared-calendar window

The original 20,000-draw five-view analysis above remains frozen. The [two-window analysis](SHARED_WINDOW_README.md) extends the streams to 40,000 draws and adds a ten-endpoint sensitivity. The original point estimates are unchanged; extended marginal interval endpoints vary slightly with the longer Monte Carlo stream. The GenSAR primary interval still includes zero for the original window, while its additional-window interval is positive. This does not promote the secondary GAOQ view to primary.
