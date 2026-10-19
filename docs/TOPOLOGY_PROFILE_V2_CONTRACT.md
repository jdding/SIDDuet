# Value-median topology protocol v2

Profile ID: `sr_sid_rolemap.topology.value_median.v2`. Draft local release:
`0.2.0-www2027-local-candidate`. This contract is fixed before building the real
input v2 summaries. Historical totals, balanced cell sizes, positive utility
or acceptance outcomes are not targets. No fitting, training, SID generation,
model inference, new threshold/precision sweep, or closed route is authorized.

## Identity and historical boundary

Historical topology is an artifact profile bound to its exact file SHA256,
not an interchangeable use of a mutable label such as MAIN_B2_B3_REGISTERED_V1.
Its archived coordinates/ranks/bins can be verified from that file. A successful
archive self-check is not raw-count reconstruction. Keep archived reports,
old model rankings and frozen author PDFs intact. New scientific summaries
must identify v2 and their actual inputs; unavailable raw sources must be
excluded from the new reconstruction scope rather than imputed.

## Continuous evidence and numerical contract

Input schema remains dataset,item_id,role,label,count. IDs are preserved.
Every input count must be finite nonnegative binary64. Aggregate label and
role support must be finite for retained common items; excluded single-role
items receive row-level validation but are not aggregated. Zero counts do not
establish role presence. Each label's duplicate counts and
role support use math.fsum in fixed sorted order. The common universe contains
only items with positive support in both roles. Labels are ordered by their
original Unicode strings. Output rows use canonical integer item IDs in
numeric order, followed by opaque IDs in Unicode order; output order must
never affect a coordinate, component rank, median, or bucket.

Normalized distributions, base-2 entropies and JS use sorted labels and
math.fsum. Identical distributions yield JS=0; disjoint supports yield JS=1;
other computed JS is clamped to [0,1]. Top-3 neighborhoods use descending
count then lexical label order. RSI remains (H_rec-H_search) divided by
max(H_rec,H_search,1e-12); its directional annotation retains epsilon 0.05.
These quantities describe provider-label evidence, not semantic incompatibility,
model harm, or utility.

For component ranking and abs(RSI) splitting, Q12(x) is Decimal(str(x)) rounded
half-even to 12 places after the decimal point, serialized as integer units of
1e-12. Q12 is an explicit numerical equivalence relation, inherited from the
pre-existing stable prototype before this repair; it is not a calibrated
error bound or a tunable hyperparameter. Use the same rule for all three RSD
components. Average descending one-based component ranks are stored exactly as
twice-rank integers. RSD is the exact Fraction sum of 2/(120+twice_rank) over
JS, top-3 disagreement and top-label mismatch. Store reduced numerator and
denominator and use them directly for comparisons. Do not quantize RSD again.
Display floats are not decision keys.

## Tie-preserving bins

Within each dataset, let m be the ordinary median of the decision values:
the middle value for odd n, or the exact arithmetic mean of the two central
values for even n. RSD values are exact RRF Fractions; abs(RSI) values are
Q12 integer units. H iff value > m; L iff value <= m. All equal decision
values receive one bin; item ID is never a tie breaker for a scientific bin.
Expose at_median flags and counts separately. In particular zero abs(RSI)
can never enter H. Equal-valued or saturated data may have an empty H half
or empty cells; never force balance or substitute another cut to fill them.
Report all four cell counts including zeros, occupied cells, exact medians,
tie cohort size, raw-zero/key-zero counts, and any empty high axis. RSD/RSI
continuous evidence is primary; the 2x2 partition is a navigation summary.

## Reproducibility scope and required binding

The reference run uses the already installed isolated CPython 3.12.14 runtime
on the current macOS arm64 host. Record exact Python version/build, OS/arch,
platform/libc description, input SHA256, builder SHA256, output CSV SHA256,
and semantic key/rank/partition SHA256. Sorted evaluation, Q12 and exact RRF
are tested for repeatability, input row/label order and effective hash seeds.
This does not promise equivalence across every libm/platform: other runtimes
must compare decision-key/rank/partition hashes to the published reference;
a mismatch is incompatible, never silently called an equivalent build.
No timing, absolute local paths, or private full maps enter public references.

## Acceptance before migration

Fabricated CLI cases must verify equal distributions, disjoint JS endpoints,
all-identical and all-zero axes (no forced H), even and odd medians,
nonzero median ties kept together, numeric/opaque ID renaming invariance,
row/label/duplicate order changes, near-one component ties, exact RRF keys,
effective PYTHONHASHSEED values, repeatability, and rejection of nonfinite or
overflowed counts. Independent checks must recompute bins from serialized exact
keys without importing the builder, and reject an old/mixed/absent profile at
all public topology consumers. Synthetic fixtures test interfaces only.

Build each available real provider-count source once to generate new v2
coordinates; an independent clean receiver then rebuilds a declared real
source and verifies full output/key hashes. Only affected structural summaries,
SID admissions and the selected inspection case are migrated. Existing model
or decoding observations remain historical evidence with their own identity
and no inherited v2 sliced claim. Full counts/maps/joins stay local restricted;
only aggregate references, synthetic probes, source and documentation ship.
