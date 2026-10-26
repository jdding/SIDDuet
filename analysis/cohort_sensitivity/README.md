# Training-only item eligibility

This replay checks whether the pooling comparison changes when an item must have an earlier exposure in both tasks. It uses the two fixed Qilin windows and the released GenSAR two-token prefix. The original historical-cohort comparisons remain in `analysis/reuse_validation`.

## Reproduce the results

Use Python 3.12 and install the optional dependency:

```sh
python -m pip install -r analysis/cohort_sensitivity/requirements-replay.txt
python analysis/cohort_sensitivity/replay.py --self-test
```

Obtain Qilin under the provider's terms. Reconstruct the original and additional request directories using [the original workflow](../reuse_validation/README.md) and [the shared-window workflow](../reuse_validation/SHARED_WINDOW_README.md). Each directory must contain `train.jsonl`, `validation.jsonl` and `audit.jsonl`. Their six hashes, the mapping, the cohort and the unchanged estimator are bound in [INPUTS.json](INPUTS.json). Existing fitted models are not required.

From the repository root, run:

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 python analysis/cohort_sensitivity/replay.py \
  --first-inputs /path/to/original_inputs \
  --additional-inputs /path/to/shared_inputs \
  --output /path/to/new/cohort_replay
```

The command verifies the inputs, fits on earlier training observations, selects on tuning users, scores audit users, and compares every aggregate field with the supplied [results](../../reports/cohort_sensitivity/RESULTS.json), using absolute tolerance `1e-12`. Successful completion prints `PASS_COHORT_REPLAY`. Outputs contain aggregate results and a receipt; request rows, user identifiers and fitted probabilities are not exported.

## Fixed analysis

Eligibility is the intersection of the released catalog and items exposed in each task's earlier training requests. Restricting the item set rebuilds collision groups, request weights and scored-request eligibility. The estimator grid and selection rule are unchanged; tuning and evaluation users remain disjoint. Maps still use the historical catalog, so this is a retrospective sensitivity rather than a prospective tokenizer evaluation.

Loss reduction is pooled minus task-conditioned macro request log loss in nats. Bootstrap draws resample the original audit-user population for each window, retaining zero contribution from users with no eligible request after restriction. The run preserves 10,000 draws, seeds 20261020/20261021, and the original four-endpoint Bonferroni family (98.75% marginal intervals). This extraction reports the two eligibility endpoints without narrowing that family. Intervals condition on the maps, fitted estimators and cohort.

Both window outcomes are retained. The first estimate is negative with an interval spanning zero; the additional-window estimate is positive. Compare estimators within each cohort; raw losses across cohorts reflect different groups and requests.
