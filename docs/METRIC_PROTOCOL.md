# Metric Protocol

Active profile: `sr_sid_rolemap.topology.value_median.v2`. The resource records
continuous role evidence; its bins provide a compact navigation view.

## Coordinates

For each item, compare the search and recommendation label distributions:

| Component | Meaning |
| --- | --- |
| `J` | Base-2 Jensen-Shannon divergence. |
| `N` | Jaccard distance between the top-three label sets. |
| `T` | Whether their top labels differ. |

Components receive descending within-dataset average ranks. Role-Specific
Divergence is `RSD(i) = sum_c 1/(60 + rank_c(i))`. The v2 implementation groups
component ties by Q12 keys, stores twice-ranks as integers, and evaluates this
sum as an exact fraction. Float display columns never decide membership.

Role-Specific Imbalance is
`RSI(i) = (H_rec-H_search)/max(H_rec,H_search,1e-12)` with base-2 entropies.
Its sign describes which role has broader label evidence; absolute magnitude
compares the breadths. Values above `0.05` or below `-0.05` are annotated
recommendation-broader or search-broader; the rest are direction-balanced.
This annotation is separate from median binning and from support frequency.

## Tie-preserving navigation

Within a dataset, use the ordinary value median. H means strictly greater;
L means at or below. RSD compares exact RRF fractions; absolute RSI compares
Q12 integer keys. Equal values always receive the same bin. Item IDs affect
output order only. HH/HL/LH/LL name RSD first and absolute RSI second.

A bin label is dataset-relative. L can include a saturated divergence or an
imbalance magnitude of one. Empty high bins are valid: in the current reference
KuaiSAR has LL only; Qilin has LL and LH. Report the continuous values, boundary
tie counts and occupied cells before interpreting a partition. The full
arithmetic and hash contract is in `TOPOLOGY_PROFILE_V2.md`.

## Observation interfaces

Collision diagnostics rank support within exact SID groups. Fixed-candidate
evaluation ranks supplied scores in their declared candidate domain. SID
admission reports mapping coverage and collision structure. These observations
answer different questions and are not combined into a leaderboard score.

Neither role-label disagreement nor a collision alone establishes semantic
error, model harm or heldout utility. Legacy high-minus-low ranking, stability
and alternative-cut sensitivity reports retain their original profile; they
do not validate the v2 coordinates or bins. Use
`reports/PROFILE_EVIDENCE_INDEX.json` to identify current and historical files.

## Limit of the all-member support-rank average

The collision diagnostic treats every member once as the target in each role.
For a group of n items, the mean is the sum of rank discounts from 1 through
min(n,10), divided by n. Reordering which member takes which rank does not
change that mean. Its all-unit average therefore describes collision-group
sizes, not how well role support ranks targets. This is not model utility.
Inspect role-support leaders and allocation separately; use declared heldout
candidate/decoding evidence for claims about predictive performance.


## Population and threshold diagnostics (2026-10-19)

The [diagnostic extension](../reports/diagnostics_20261019/README.md) distinguishes
label divergence within one item from task-allocation divergence over members
of a shared code. It records all collision groups and both paired-count
regrouping references, preserving every tied maximum in leader comparisons.
The exact-total analysis is supplementary and was designed after the primary
results. The original fixed-margin reference permits per-item task zeros and
does not condition on the common-item positive-support selection.

Changing numerical cuts can produce four occupied regions. The full optional
threshold results and occupancy upper bounds do not select a replacement
protocol or establish predictive usefulness. The value-median v2 default,
comparison keys and exact-rank computation are unchanged.

## Fixed-candidate exact-score ties (evaluation v3)

The fixed-candidate evaluator averages target gain and Hit@10 over every rank occupied by its exact-score tie block. Candidate IDs and row order do not break score ties. This preserves finite-score direction and the original candidate universe. Hit@10 can be fractional when a tie crosses rank 10. Version v2 used candidate-ID order; its archived results retain that protocol and are not silently reinterpreted. The topology value-median v2 and the temporal allocation log-loss comparison are unchanged.
