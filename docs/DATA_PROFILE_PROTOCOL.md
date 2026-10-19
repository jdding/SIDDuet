# Data and topology profile identity

The current profile is `sr_sid_rolemap.topology.value_median.v2`; its full
contract and reference hashes are in `TOPOLOGY_PROFILE_REGISTRY.json` and
`TOPOLOGY_PROFILE_V2_CONTRACT.md`. Current reconstruction covers KuaiSAR and
Qilin (118,269 common items). The registry gives all four cell counts,
including zeros, and median-tie diagnostics. Continuous evidence is primary;
H means strictly above the dataset median and L means at or below it.

Provider extraction is specified in `PREPROCESSING_PROTOCOL.md`. Obtain inputs
under upstream terms; full counts, maps and joins remain local. A profile
name alone does not establish numeric equivalence: verify input, builder,
output and decision hashes against the references. Consumers reject absent,
old or mixed topology identities. Other runtime builds must match reference
keys/ranks/partitions before being treated as equivalent.

Historical equal-size slices and their evaluation reports are archived,
with exact file hashes in `reports/PROFILE_EVIDENCE_INDEX.json`. Their apparent
four-cell support relied on splitting ties and is not v2 evidence. The old
JDsearch full aggregate is also historical; its full raw/counts inputs were
not available for this reconstruction. No canary replaces that full run.
