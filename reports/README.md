# Result guide

The [1999-draw precision comparison](diagnostics_mc1999_20261020/README.md) updates the reference estimates while preserving the original 199-draw records.

| Evidence | Location | Interpretation |
| --- | --- | --- |
| Current paired-observation references | [`v2/`](v2/) | KuaiSAR and Qilin under the value-median v2 protocol |
| Population, tie and cut diagnostics | [Diagnostic results](diagnostics_20261019/README.md) | Descriptive support/label structure and declared regrouping references |
| Qilin temporal reuse | [Forecast tables](../analysis/reuse_validation/README.md) | Later exposure-allocation loss; no relevance or ranking-gain claim |
| Real UniSAR case | [Model results](model_reuse/README.md) | Coverage, fixed-candidate metrics and support-stratified comparisons |

The current core contains 118,269 common items: 97,729 KuaiSAR and 20,540 Qilin.
`v2/fixed_275_case.json` records the structural example under the current protocol.
Older protocol reports, draft tables and internal audits are kept outside this public release.
Aggregate results retain their scientific values. Local source-path metadata in four temporal
result JSONs has been normalized; the provider identities and source hashes remain available.
Complete simulation draws are reproducible research outputs and are not included in the code checkout.

The [result interpretation guide](../docs/READING_THE_RESULTS.md) explains the metric units, exact windows and processed-data coverage. [Training-only cohort results](cohort_sensitivity/README.md) retain both fixed-window outcomes and link to their standalone replay.
