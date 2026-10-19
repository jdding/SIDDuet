# Topology Compatibility

The public release uses the explicit profile,
`sr_sid_rolemap.topology.value_median.v2`. It supersedes the old public builder
for new topology construction. Historical coordinates and model observations
remain archived under their original identities.

## What is reproducible

| Evidence | Scope |
| --- | --- |
| Saved legacy coordinates | Itemwise verification of stored ranks, RRF, RSI and bins against one exact archived CSV. |
| Current provider reconstruction | KuaiSAR 97,729 and Qilin 20,540 shared items under v2; input, builder, CSV and semantic hashes are recorded. |
| JDsearch historical QA | Adapter and old aggregate receipts only; no current complete-input v2 build. |
| Historical model observations | Their original carrier, evaluation units, candidate domain and saved protocol. |

The legacy coordinate artifact has SHA256
`0ece7e55541a3535fe0afe66f261da885cf15e457b244112afb4a82f4d71e3d9`.
Its full itemwise file stays restricted. Legacy archives are retained outside the public checkout. Mutable labels such as
`MAIN_B2_B3_REGISTERED_V1` do not uniquely identify numerical coordinates:
the separate old earlier metric reports have different cell totals.

Verifying saved algebra is not reconstructing the old role-label counters.
Their exact contents and insertion order, original process hash state, runtime
and execution provenance were not preserved well enough to attest a raw
legacy rebuild. The old JS loop used unordered labels and ordinary floating
addition; forced rank halves also split equal values by item order.

## What changed

V2 fixes sorted stable summation, explicit Q12 equivalence, average component
ranks, exact RRF fractions, and value-median bins. All ties stay together;
H is strictly above the median and L includes it. The rule was fixed before
reading the new dataset totals. Old totals and occupied cells are not targets.

| Dataset | HH | HL | LH | LL |
| --- | ---: | ---: | ---: | ---: |
| KuaiSAR v2 | 0 | 0 | 0 | 97,729 |
| Qilin v2 | 0 | 0 | 8,595 | 11,945 |

These empty regions expose concentrated or tied coordinates; they are not
repaired by another cut. Continuous values remain the evidence. In particular,
L is not an absolute claim of low divergence or role compatibility.

## Attaching evidence

Topology consumers require the exact v2 `profile_id`, unique dataset/item keys
and an explicit topology-file hash. Score exports carry that identity on every
row; fixed-candidate evaluation rejects old, absent or mixed identities.

Whole-map coverage and global collision rates can be compared when the mapping
and item universe are unchanged. Cell counts, selected-case cells, sliced
ranking, leave-one-component-out correlations and binning-sensitivity claims
cannot be inherited. The current 275-item case keeps the same SID group and
support counts but recomputes region assignments; all its members are LL in v2.

Older root-level reports and hashed samples are retained locally as historical
archives. Current structural references live under `reports/v2/`. Consult
`reports/PROFILE_EVIDENCE_INDEX.json` before choosing a report. No training,
SID generation or new model evaluation was used for this protocol repair.
