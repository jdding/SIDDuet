# Representation Protocol

SID artifacts enter the resource by mapping item identifiers to the registered
shared item universe and declaring an evidence layer:

- collision diagnostic;
- fixed-candidate sampled ranking;
- SID-family admission through aggregate coverage plus topology-sliced diagnostics.

Each artifact must declare release level, topology coverage, and claim boundary.
Other full SID maps, raw embeddings, checkpoints, and item-level joins are excluded
from the public release.

## Approved minimal catalog exports

The only complete-map exception is the three named derived catalog-ID/code
CSVs and item-ID-only cohort in [data/native_exports](../data/native_exports/README.md).
They cover the declared six native code views and carry Qilin provider
Apache-2.0 terms and attribution. They contain catalog identifiers and derived
codes, not request/user/session/query/history data or a full role-label join.
Other complete maps and all raw/user-level or role-label joins remain excluded.
No upstream native implementation source code is bundled or relicensed.
