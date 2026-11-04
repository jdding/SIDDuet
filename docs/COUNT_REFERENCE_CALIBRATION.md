# Calibrate paired counts for your own SID maps

This entry point is an unreleased local draft based on v0.2.8. It accepts your
own dataset names, role counts and named SID maps. It reports aggregate
allocation differences relative to two conditional count-regrouping references.
It does not rerun or replace the frozen population study, assess semantic
quality, predict heldout utility, or identify a causal effect.

## Run the shipped tiny example

From the resource repository root, with Python and NumPy available:

```sh
mkdir -p /tmp/sidduet-calibration-example
/opt/homebrew/bin/python3 -I -B scripts/calibrate_task_allocation.py \
  --role-counts samples/synthetic_role_label_counts.csv \
  --sid-map demo-view=samples/synthetic_sid_map.csv \
  --draws 19 --seed 20261104 \
  --out-json /tmp/sidduet-calibration-example/result.json \
  --out-csv /tmp/sidduet-calibration-example/result.csv
```

This is a fabricated eight-item, two-collision-group example, not a scientific
result. The output directory must exist and both output files must be fresh;
choose new filenames to repeat it. Python is loaded in isolated mode (`-I`),
and the CLI resolves its helpers by their explicit repository paths.

## Use your own data

```sh
python3 -I -B scripts/calibrate_task_allocation.py \
  --role-counts /absolute/path/counts.csv \
  --sid-map baseline=/absolute/path/baseline.csv \
  --sid-map candidate=/absolute/path/candidate.csv \
  --draws 1999 --seed 20261104 \
  --out-json /existing/output/directory/calibration.json \
  --out-csv /existing/output/directory/calibration.csv
```

Counts require a unique header containing `dataset,item_id,role,label,count`.
The `role` values are exactly `search` and `rec`. Counts must be finite,
nonnegative integral values. Labels and repeated rows are summed exactly as
Python integers, first to each item/role, then checked against the numerical
safety bound. Each dataset's total, including excluded items, must be at most
`2**53`; larger inputs are rejected before numerical computation. No event
array is materialized. Extra columns are permitted when the header is unique
and every row has exactly the declared width.

Every dataset must have at least one item with positive summed support in both
roles. Only those common items enter calibration. Missing-role and zero-support
items are excluded and counted. Dataset/item keys are exact nonblank strings;
whitespace, leading zeros, case and dataset identity are not normalized or used
to infer a bridge. Role labels are aggregated, not compared as distributions.

Each map requires `dataset,item_id,sid` and must cover every common item in every
supplied dataset. Extra rows, including rows for excluded items or unrelated
datasets, are reported as unused. An item in a different dataset never fills a
coverage gap. The shared strict SID loader rejects duplicate keys (even when
identical), blank/missing codes and malformed CSV widths. Nonempty opaque SID
strings remain supported. JSON token lists are canonically serialized; tokens
are nonblank strings or integers, and integer/string tokens remain distinct.

Repeat `--sid-map name=path` to add views. Names may contain spaces and Unicode;
they must be unique, trimmed, nonblank and free of control characters. The first
`=` separates the name from the path, so names cannot contain `=`. Outputs must
be distinct fresh files, must not alias an input or implementation file, and
must have existing parent directories. Validation and calculation finish before
output creation. Exclusive creation guards against overwriting a file that
appears during computation.

## Groups, metrics and references

Within each dataset/view, SID groups are fixed by the common-item map. All
common items, including items in singleton groups, remain permutation slots.
Only groups of size at least two contribute metrics. A collision-free view is
a structural control: all metric, reference, p and q endpoints are `null`
(blank in CSV), and it is excluded from multiplicity adjustment.

For each collision group, JSD is the base-2 Jensen-Shannon divergence between
the normalized search and recommendation count vectors over its members.
Leader disjointness is one exactly when the complete maximum-support item sets
for search and recommendation have empty intersection. Tied leaders are sets;
an overlapping tied leader makes disjointness zero.

JSON reports six unrounded binary64 summaries:

- `equal_group_jsd`, `item_weighted_jsd`, `observation_weighted_jsd`;
- `equal_group_disjoint`, `item_weighted_disjoint`, `observation_weighted_disjoint`.

Equal-group summaries average collision groups. Item weights are fixed group
sizes. Observation weights are each state's actual group search-plus-rec count,
including in simulated states. They are not held at observed group volumes.

Both references move each item's entire `(search_count, rec_count)` pair among
the common-item slots while holding SID groups fixed:

- `band`: shuffle within `floor(log2(search_count + rec_count))`, computed with
  integer bit lengths to preserve exact power-of-two boundaries.
- `exact_total`: shuffle within identical `search_count + rec_count` values.

The global pair multiset and each slot's reference key are preserved. Exact
group search/rec totals are generally not preserved. No search and rec vectors
are shuffled separately. Each reference/draw/dataset generates one permutation
and evaluates every map on that same permutation. Degenerate reference spaces
are valid, with inclusive-tail p equal to one when the endpoint is unchanged.

Streams use NumPy PCG64. The seed is the big-endian integer of SHA-256 of the
UTF-8 compact JSON encoding
`["sidduet.count_reference.v1", seed, dataset, reference]`, with Unicode emitted
directly. Item IDs, datasets and map names are sorted as exact Python strings;
reference strata use sorted numeric keys. Thus CSV row order, map order and
adding another mapping view do not change an existing view's reference draws.
These draws are not claimed to equal those of the historical population study.
Input hashes still change when input bytes are reordered.

## Inference and output

`equal_group_jsd` is primary. With observed statistic `t`, `B` draws and
reference statistics `T_b`, the two-sided Monte Carlo p is
`min(1, 2 * min((1 + #{T_b >= t})/(B+1), (1 + #{T_b <= t})/(B+1)))`.
Tails include numerical ties: a reference value with absolute difference from
`t` at most **`1e-12`** is counted in both tails. Relative tolerance is zero.
All six metrics are bounded in `[0,1]` (JSD in bits). This fixed absolute
comparison tolerance prevents harmless summation-order roundoff from turning
permutations of an unchanged group multiset into apparent tail differences.
The generic adapter treats those values as `t` only when calling the unchanged
population helper's p kernel. Reported observed values, reference means/ranges
and differences retain their original full precision. The JSON protocol records
both tolerances and this scope. Historical helper code and results are unchanged.
The lower bound is `min(1, 2/(B+1))`; defaults give 0.001 at 1999 draws. This
is conditional reference calibration, not an iid event or causal model.

For each reference separately, the primary multiplicity family contains all
estimable dataset-by-map endpoints from this invocation. JSON lists its exact
members and size. BH adjustment is applied to that family's primary p values;
BY is `min(1, BH_q * H_m)`, where `H_m = sum(1/k, k=1..m)`. BY supplies the
arbitrary-dependence-conservative sensitivity; BH alone does not establish that
guarantee across related views. The two references are separate declared
families, with no joint across-reference FDR claim. Adding a mapping view can
change q values even when its existing views' draws remain unchanged. Secondary
metrics have descriptive reference summaries and unadjusted p values; they are
not included in a secondary FDR claim.

Every metric's reference summary includes its mean, central 2.5th/97.5th
percentiles, observed-minus-reference mean and unadjusted two-sided p. These
are **regrouping reference ranges, not confidence intervals for an effect**.
JSON records schema/status, common/excluded counts, unused map rows, grouping
counts, seed/draws, Python/NumPy/platform, and SHA-256 hashes of inputs, this CLI,
the unchanged population helper and shared map loader. All bound files are
rehashed before output. The population helper's numerical kernels are loaded
directly; its study-specific input reader and runner are never invoked.

CSV contains one row per dataset/map/reference with the full-precision primary
observed value, reference mean/range/difference, p, BH/BY q and grouping counts.
No output contains raw item IDs, paired vectors, SID codes, membership tables,
or per-draw arrays. Dataset/map names and input paths remain in provenance;
review those names before sharing outputs. This command writes only the two
named files and leaves existing study reports untouched.

## Local verification

```sh
/opt/homebrew/bin/python3 -B -m unittest discover \
  -s tests -p test_allocation_calibration.py -v
```

Tests use only fabricated data and temporary outputs. They exercise the real
CLI under isolated Python, independent analytic six-metric expectations,
independent reference calculations, paired-stratum preservation, shared draws,
ties, singleton/exclusion handling, arbitrary dataset/view names, coverage and
malformed-input rejection, reproducibility, multiplicity and output guards.
Numerical regressions also require p/BH/BY equal to one for the mathematically
invariant one-group reference, while retaining sensitivity to a clearly
separated constructed contrast.
