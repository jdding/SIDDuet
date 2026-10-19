# Reconstruction Protocol

The synthetic workflow uses the standard library. Provider readers are optional.
The active topology profile is `sr_sid_rolemap.topology.value_median.v2`; its
numeric and tie contract is in `TOPOLOGY_PROFILE_V2.md`. Full counts, maps and
joins stay local.

## 1. Materialize role-label counts

```bash
python3 -I scripts/materialize_role_label_counts.py \
  --events samples/synthetic_role_events.csv \
  --out-csv outputs/synthetic_materialized_role_label_counts.csv \
  --out-json outputs/synthetic_role_label_materialization.json
```

Normalized events use
`dataset,role,event_id,item_id,item_label,engaged,weight`. The materializer chooses
the dominant engaged label, falls back to exposures, and emits
`dataset,item_id,role,label,count`. Provider rules and direct KuaiSAR/Qilin
commands are in `PREPROCESSING_PROTOCOL.md`.

## 2. Build the topology

```bash
python3 -I scripts/build_role_topology.py \
  --role-counts outputs/synthetic_materialized_role_label_counts.csv \
  --out-csv outputs/synthetic_role_topology.csv \
  --out-json outputs/synthetic_role_topology.json
```

The builder retains items with positive support in both roles. It uses sorted
stable summation, Q12 component equivalence, average component ranks, exact
RRF fractions with `k=60`, and value medians. H is strictly above the median;
L includes it. IDs order output rows but never split tied values. Empty high
bins and zero-count cells are valid output, not reconstruction failures.

The summary binds the input, builder, contract, output CSV, and semantic
key/rank/partition hashes. Reference results use CPython 3.12.14 on macOS arm64;
other runtimes must check the decision-key hashes before calling a build
compatible.

## 3. Admit a SID family

```bash
python3 -I scripts/admit_sid_family.py \
  --topology outputs/synthetic_role_topology.csv \
  --sid-map samples/synthetic_sid_map.csv \
  --family synthetic_demo \
  --out-csv outputs/synthetic_admission_cells.csv \
  --out-json outputs/synthetic_admission.json
```

A SID map uses `dataset,item_id,sid`. Admission reports coverage and collision
structure. Outputs retain `topology_profile_id` and the exact topology-file
`topology_sha256`; item-level joins are not emitted.

## 4. Inspect within-code support

```bash
python3 -I scripts/evaluate_collision_diagnostic.py \
  --topology outputs/synthetic_role_topology.csv \
  --sid-map samples/synthetic_sid_map.csv \
  --out-csv outputs/synthetic_collision_metrics.csv \
  --out-json outputs/synthetic_collision_metrics.json
```

The command ranks items by each role's support within an exact SID group and
emits aggregate NDCG@10. This is a support diagnostic, not model ranking or an
independent semantic-harm test. Its outputs carry the same topology identity.

## 5. Attach existing scores

```bash
python3 -I scripts/adapt_method_scores.py \
  --scores samples/synthetic_method_scores.csv \
  --topology outputs/synthetic_role_topology.csv \
  --method-id synthetic_discriminative_ranker \
  --method-paradigm discriminative \
  --score-direction higher_is_better \
  --out-csv outputs/synthetic_adapted_candidates.csv

python3 -I scripts/evaluate_fixed_candidates.py \
  --candidates outputs/synthetic_adapted_candidates.csv \
  --out-csv outputs/synthetic_fixed_candidate_metrics.csv \
  --out-json outputs/synthetic_fixed_candidate_metrics.json
```

Score inputs use `dataset,unit_id,role,candidate_id,is_target,score`. The adapter
requires one target per unit and distinct finite-scored candidates, preserves
the candidate domain, and attaches the target's topology to every candidate.
Its output adds `method_id`, `method_paradigm`, `score_direction`,
`topology_cell`, `rsd_bucket`, `rsi_mag_bucket`, `topology_profile_id` and
`topology_sha256`. Paradigms are `generative`, `discriminative` or `hybrid`;
score direction is `higher_is_better` or `lower_is_better`.

All topology consumers reject missing, old or mixed profile IDs and duplicate
item keys. The fixed evaluator requires one v2 profile and one topology SHA256
across its input, groups by method, and retains that identity in its outputs.
The historical fixed-candidate fixture is not a current
adapter export.

The evaluator reads supplied predictions; it does not train or reproduce the
supplying model. Old model observations remain tied to their original samples
and protocols. Do not relabel historical cell-balanced ranking or bootstrap
intervals as v2 results.

Record and registry validation are included in `scripts/validate_release.py`.
See `ROLEMAP_RECORD_PROTOCOL.md`, `METHOD_ADMISSION_PROTOCOL.md` and
`reports/PROFILE_EVIDENCE_INDEX.json` for their scope and evidence versions.
