# Reading the reported comparisons

## Context labels and observations within a code

The [metric protocol](METRIC_PROTOCOL.md) defines item-level RSD as the sum of reciprocal ranks of label JS divergence, top-three set distance and leading-label mismatch. Ranks are descending within each dataset and ties receive their average rank; the fixed reciprocal-rank constant is 60. RSI is the signed difference in the two label entropies divided by their maximum (with a 1e-12 floor).

These item-level label comparisons differ from allocation JS divergence: the latter normalizes search and recommendation counts separately across all members of a code group. The [count-reference results](../reports/diagnostics_mc1999_20261020/README.md) compare those allocations with paired-count regroupings.

## Temporal exposure forecasts

Each request has total weight one. Divide it equally among exposed collision groups, then equally among distinct exposed members in each group. Training counts use those weights. For a scored request, average minus the natural logarithm of the predicted member probability with the same weights. The predictor is normalized over the group's entire eligible catalog, not just the members exposed in that request. Average request losses within each task, then average the two task means.

The fixed smoothing grid is 0.1, 1, 10, 100 and 1000. [The original protocol](../analysis/reuse_validation/PROTOCOL.md) specifies the pooled, balanced, separate and shrinkage estimators and tuning-only selection. The two evaluation windows on 27 November 2024 are [09:43:45, 11:14:48) and [11:30:00, 15:30:00) UTC. The first lasts 91 minutes and 3 seconds. The additional window is the complete contiguous run of eight later half-hour bins with requests from both tasks; [coverage selection](../analysis/reuse_validation/SHARED_WINDOW_PROTOCOL.md) preceded its fit and loss computation.

[Training-only eligibility](../analysis/cohort_sensitivity/README.md) restricts the existing mapping catalog to items exposed in both tasks before each window. It changes eligible groups and requests as well as training counts. Both sensitivity outcomes are supplied; compare estimators within each cohort.

## Raw and processed KuaiSAR views

The 97,729-item raw-data reference and the 9,104-item UniSAR view use different observation sources and ID namespaces. The processed view is constructed from retained positive histories and truncated search sessions for all 22,699 nonpadding provider users. No verified inverse ID bridge establishes a raw-to-processed subset relationship.

The 2.93% and 3.18% coverage rates count targets in that processed paired-observation view among all 9,789 search and 157,192 recommendation test requests. The fixed model still scores every original 100-candidate request. These rates describe this observation view and test population; they are not estimates of coverage for every possible paired-data construction. See [the model-reuse protocol](../reports/model_reuse/PROTOCOL.md) and [complete replay](../analysis/model_reuse/REPLAY.md).
