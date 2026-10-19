# Post-primary robustness: paired regrouping with exact item totals


## Scientific question

The original paired regrouping B preserves each SID slot's floor-log2 support band, but can change its exact total support and therefore each group's exact total. Does its six-layer direction persist when this residual total-count variation is removed? A result that weakens, reverses or disappears must be retained, as must an unchanged direction. No threshold, mapping, population, weighting or null is selected according to its significance.

## Frozen population and metrics

- Exactly the same KuaiSAR 97,729 and Qilin 20,540 common items, and GRID / RQ-VAE / ReSID-GAOQ supplied normalized maps, are used; no new fit, SID, raw corpus or labels are introduced.
- All six dataset × supplied-map strata remain in the table. Singletons remain in scope accounting and are excluded from collision-group metrics.
- Use the original definitions and code for member-allocation base-2 JSD; retain all tied search/recommendation argmax sets for disjointness. Provider-label JSD is a different measure.
- Primary summary is equal weight per collision group. Item-weighted and observation-weighted JSD and disjoint fractions are fixed secondary descriptions, not selection options. Retain the same five group-size strata and five support strata, defined from observed groups.
- Validate universe size, coverage, unique SID count and original admission rates. Observed summaries must match the archived primary results, with exact group denominators and numerical tolerance 1e-14 for floating summaries.

## Supplementary B_exact reference

Jointly permute paired `(S_i,R_i)` only among item slots with exactly the same positive integer `n_i=S_i+R_i`. Use 199 independent draws with NumPy PCG64, seed `20263018 + dataset_index` for the fixed dataset order KuaiSAR, Qilin. Canonical item order and exact-total class order are deterministic. The same dataset permutation in each draw is shared across all three supplied mapping families.

Every draw must preserve the paired-count multiset, each fixed slot's exact total count, positivity, group membership/size and each group's exact **combined** task count. It does **not** preserve each group's search total and recommendation total separately, semantic neighborhoods, item identity relationships, or temporal structure. Identity permutations and exchanges of identical paired counts are retained, without redraw. No event expansion is used.

Predeclared mobility descriptors: number of exact-total classes; singleton exact-total classes/items; classes/items with at least two slots; classes/items with at least two distinct paired count values; item fraction within these nontrivial classes. These describe how restrictive the conditioning is. No low-mobility group or dataset is removed. If a null becomes constant, report that fact, its zero-width range and the prescribed empirical p rather than changing the reference.

## Outputs and interpretation

For every one of the six strata, report observed summaries, null means, central 95% simulation ranges and observed-minus-null effects for all three weighting modes and the secondary disjoint fraction. Save every fixed descriptive stratum including empty strata as JSON null. Save all 199 aggregate draws and restricted complete group tables; public aggregate reports must not expose raw SID or item identifiers.

The six primary supplementary equal-group JSD comparisons use the same two-sided finite-Monte-Carlo formula as the original primary analysis:

`p = min(1, 2*min((1 + #null >= observed)/(199+1), (1 + #null <= observed)/(199+1)))`.

Report BH-adjusted values across these six **supplementary** comparisons only, plus fixed BY(H6) dependency-conservative sensitivity. Mark them post-primary; do not combine them with the original six comparisons to imply an outcome-blind confirmatory family. The smallest attainable two-sided p is .01; ties count in both tails. BH alone is not an arbitrary-dependence FDR guarantee. No significance tests for secondary metrics or strata.

A persistent lower observed JSD would mean less member-allocation heterogeneity than this exact-total count-regrouping reference, and narrow the residual total-count explanation of original B. It would still not establish semantic compatibility, causal SID benefits, harmful collisions or heldout model utility. An unchanged direction across two related nulls is not independent replication. Null exchangeability is a reference assumption about count pairs among equal-total slots, not a model of the actual assignment process. Conditional classes can differ in semantics and role exposure; the mapping and these associations are not randomized in the real data.

## Runtime, identity and stop rules

Local installed CPython 3.12.14 / NumPy 2.3.5, CPU only, one thread, no paid backend/API, model call, GPU, training or SID fit. Expected runtime below 60 seconds and peak memory below 2 GB. Cap at 5 minutes; retain a failure/partial receipt if exceeded, optimize only equivalent computation and never reduce 199 draws or alter definitions based on the outcome.

Reuse the frozen original population helper through explicit importlib loading after checking its SHA256 `84df7129b1cbc146b0ae9da754a772de667e361a7ad3acf5619d1f11cf4c6b29`. The primary result SHA256 is `b9e5ade19db56479e2ad164503e1d1b17bcff2316c03d354f0fcce0ce82a28e9`. All five used scientific input hashes, primary result, helpers, this plan, new code, admissions and manifest are checked before and after execution. Existing directories/files are never overwritten. Save exact command, runtime actor, Python/NumPy versions, thread variables, timings, peak RSS, checks and output hashes in a dedicated receipt. No training launcher is involved because this is a standalone local CPU randomization reference, fully covered by its dedicated receipt.

Before real execution, synthetic checks cover exact slot totals, paired multiset, group combined totals, positive supports, same draws shared across maps, fixed strata/denominators, tie/null boundaries, a frozen 2-item-total enumeration with independently computed expected mean JSD, all-identical/unique-total degeneracy, both positive and negative controlled directions, reordering invariance of observed metrics, and equality with the original metrics. All outcomes and failed checks remain recorded.
