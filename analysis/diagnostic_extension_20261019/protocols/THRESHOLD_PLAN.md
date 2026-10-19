# Post-primary threshold sensitivity and geometric feasibility

This lane is declared after reading the completed population and tie-source diagnostics. It is not a preregistration of the primary analyses. The observed maximum-RSD plateau motivates the question: does the empty quadrant reflect the particular median cut, or is balanced four-way navigation geometrically impossible under any numerical, tie-preserving pair of cuts? This is a descriptive diagnostic of the fixed scores; it does not choose a protocol or test downstream usefulness.

The original `sr_sid_rolemap.topology.value_median.v2`, its reference files, earlier analysis contract, primary results, manuscript and release remain unchanged. No model, training, API, GPU, new weight, label depth, precision or item tiebreak is used. Only the two hash-bound serialized v2 topologies in `INPUTS.json` are read. Local installed CPython 3.12.14 + NumPy 2.3.5 is used without installation. All outputs are aggregate; no item ID is written.

## Fixed nine-pair comparison

For each axis q belongs to {0.25, 0.50, 0.75}; all nine pairs are reported. RSD comparisons use the existing exact numerator/denominator Fractions; absolute RSI comparisons use the existing Q12 integer keys, represented as exact Fractions for a possible even-N median. For q = 0.50 use the ordinary median: average the two central values for even N, exactly as v2. For q = 0.25 or 0.75 use the empirical nearest-rank value at `ceil(q*N)-1`. Every item is L iff its value is <= cut, H iff > cut. Equal values are never split.

Each pair reports HH, HL, LH and LL counts, the minimum quadrant count / whole-universe denominator, occupied quadrants and item conservation. Axis diagnostics report unique values, largest atomic tie count / N, exact cut value, items equal to the cut, below/above counts, unique values on each side and whether the cut equals the largest tie value. Each quadrant reports distinct RSD values, RSI keys and observed coordinate pairs. The .50/.50 allocation is checked itemwise against the serialized v2 flags/bucket labels, so sensitivity cannot silently replace the reference. No winning quantile is selected and no p-value or utility claim is assigned.

## Exhaustive numerical-cut feasibility bound

An axis with U observed unique values has U+1 possible tie-preserving numerical partitions: no values in L; each successive complete equality block in L; and all values in L. Boundary i = 0 represents a cut below the minimum, 0 < i < U represents any cut in [value[i−1], value[i]), and i = U represents any cut >= maximum. Thus all numerical cuts induce one of these partition classes; scanning every distinct class is exhaustive without pretending that arbitrary real cutoffs are separately meaningful.

Build an integer (U+1) × (V+1) prefix-count matrix using the unique exact RSD and RSI-key coordinates. Compute prefix sums in place. For each RSD boundary i and all RSI boundaries j, compute LL, LH, HL and HH from the prefix count and the axis marginals, then take their minimum. The maximum of that quantity over all boundaries is a descriptive upper bound on the smallest attainable quadrant under any numerical tie-preserving pair of axis cuts.

Retain the number of all maximizing boundary pairs and every maximizing pair, compressed losslessly as contiguous RSI boundary-index runs for each RSD boundary. Save their exact numerical cut equivalence intervals, including unbounded edge intervals. Report the lexicographically smallest boundary-index pair as a deterministic representative. For that representative, canonical finite cuts are `minimum−1` for the empty-L boundary and otherwise the included maximum value. This is a canonical representative of the earliest partition class, not a claim that the unbounded real interval has a smallest number. Report all four resulting counts and their distinct-value diagnostics. Do not adopt it as a new protocol, optimize old counts, interpret nonempty bins as useful bins, or imply predictive improvement.

The exact score ties are atomic throughout. The prefix matrix and all boundary classes include edge cases with empty quadrants. Even a favorable bound establishes only capacity for populated quadrants, not scientific meaning, independence, fairness or generalization.

## Resource budget and checks

Expected largest matrix is approximately 4,421 × 3,264 int64 entries, about 115 MB; in-place cumsum and rowwise minima avoid multiple full matrices. Target peak memory <500 MB and execution <2 minutes per dataset. The diagnostic retains all nine quantile pairs and all maximizing cut classes; it never reduces coverage or selects a cutoff in response to a result. If resource use fails, preserve the failure receipt and optimize equivalent computation.

Fabricated tests must include proportional/empty/all-tied and plateau universes, all four quadrant conservation, exact Fraction ordinary median, nearest-rank quartile boundaries, equality-block preservation, current-v2 median correspondence, row-order invariance, lossless maximizing-run expansion, a small exhaustive brute-force comparison, no-ID aggregate outputs, input-hash mismatch refusal and fresh-output refusal. A matrix-scale synthetic benchmark checks memory/runtime before any real computation.

