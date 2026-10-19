# Value-median Topology Profile v2

Profile ID: `sr_sid_rolemap.topology.value_median.v2`.

The protocol was fixed before the new dataset cell totals were inspected.
Historical counts, balanced cells and positive model outcomes were not targets.
It changes numerical identity and binning without retraining or regenerating
SID assignments.

## Input and continuous evidence

Input columns are `dataset,item_id,role,label,count`. Preserve item and label
identities. Each count must be finite, nonnegative binary64. Zero counts do
not establish role presence. Only items with positive support in both roles
enter the common universe. Aggregate retained-item label counts and role
supports with `math.fsum` in a fixed sorted order; overflow is rejected.
Single-role excluded items receive row validation without aggregation.

Normalize in sorted label order. Compute base-2 entropies and JS with stable
summation. Identical distributions have JS=0, disjoint supports JS=1, and other
JS values are clamped to [0,1]. Top-three neighborhoods use descending count
then lexical label order. RSI is
`(H_rec-H_search)/max(H_rec,H_search,1e-12)`; the direction annotation keeps
its separate epsilon of 0.05.

For component ranks and absolute-RSI splitting, Q12 converts `Decimal(str(x))`
to twelve decimal places with half-even rounding and stores integer units of
`1e-12`. It is an explicit numerical equivalence rule, inherited from the
prior stable prototype. It is neither an error guarantee nor a fitted
parameter. Use it for all three RSD components.

Components receive descending one-based average ranks, stored exactly as
twice-rank integers. RSD is the exact sum of `Fraction(2,120+twice_rank)` for
JS, top-three disagreement and top-label mismatch. Store the reduced numerator
and denominator. Do not round RSD again for comparisons. Display floats are
not decision keys.

## Bins preserve values

Within each dataset use the ordinary median: the central value for odd counts
or the exact mean of the two central values for even counts. Compare RSD as
fractions and absolute RSI as Q12 integers.

- H iff the decision value is strictly greater than the median.
- L iff it is at or below the median.
- Every equal decision value receives the same bin; item IDs never break a
  scientific-bin tie. In particular zero absolute RSI never enters H.

HH/HL/LH/LL name RSD first, absolute RSI second. L is relative to the dataset;
it need not mean a small absolute value. Report all four cells including
zeros, occupied cells, exact medians, median-tie counts, raw/key-zero counts
and empty high axes. Continuous coordinates remain primary. Do not change a
cut to fill empty cells.

## Current reference scope

| Dataset | Shared items | HH | HL | LH | LL | RSD median ties | Absolute-RSI median ties |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| KuaiSAR | 97,729 | 0 | 0 | 0 | 97,729 | 65,354 | 54,510 |
| Qilin | 20,540 | 0 | 0 | 8,595 | 11,945 | 14,884 | 11,945 |

The rebuilt scope totals 118,269 items. JDsearch's adapter and old aggregate
receipts are retained; its complete source/count/topology files were not
available for this reconstruction. It is not part of the current-profile total.

The fixed archived 275-item ReSID-GAOQ group is not reselected. All 275 members
are LL under v2, while the distinct support leaders retain S46/R1 and S1/R478.
This illustrates within-code support allocation and the limit of coarse bins;
it does not independently establish semantic error, harm or benefit.

## Identity and runtime

Every topology row identifies the profile. Summaries bind input SHA256,
builder and contract SHA256, output CSV SHA256, and the semantic key/rank/
partition SHA256. Serialized keys and the declared hash encoding support an
independent decision check. Admission and score outputs retain the topology
profile and file hash; old, missing or mixed profiles are rejected.

The reference runtime is CPython 3.12.14 on macOS arm64. Sorted arithmetic,
Q12 and exact RRF are checked against input order changes and hash seeds.
This is not a universal libm/platform equivalence promise. A different runtime
must compare the published semantic hashes; a mismatch is incompatible until
resolved.

`reports/PROFILE_EVIDENCE_INDEX.json` separates current structural references,
synthetic fixtures and exact-byte historical archives. Old cell-balanced
ranking intervals, leave-one-component-out stability and alternative-cut
sensitivity are not v2 findings. Historical overall ranking/decoding results
may be read under their own carrier and evaluation protocol. No new model
experiment is needed to maintain that boundary.
