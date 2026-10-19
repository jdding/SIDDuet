# Role-Label Preprocessing Protocol

Provider adapters construct `dataset,item_id,role,label,count` locally. Raw
files, user identities and query text are not released. The current rebuilt
scope is KuaiSAR and Qilin; the shipped JDsearch adapter remains available
without a new full-input v2 reconstruction.

## Normalized events

The generic materializer requires `dataset,role,event_id,item_id,item_label,
engaged`; optional positive-integer `weight` defaults to one and must be constant
within an event. Roles are `search` and `rec`.

For each `(dataset,role,event_id)`, count labels among engaged rows, fall back
to all exposures if none is engaged, and choose the most frequent label with a
lexical string tie break. Assign that label to every appearance and aggregate
by `(dataset,item_id,role,label)`. Repeated appearances count separately.
Missing identifiers or category labels are handled by the provider adapter.

```bash
python3 -I scripts/materialize_role_label_counts.py \
  --events samples/synthetic_role_events.csv \
  --out-csv outputs/synthetic_materialized_role_label_counts.csv \
  --out-json outputs/synthetic_role_label_materialization.json
```

## Optional provider environment

Create the provider environment with Python 3.12 and keep it outside the
resource root:

```sh
ROLEMAP_ENV_ROOT=/path/outside/resource/rolemap-provider-env
python3.12 -m venv "$ROLEMAP_ENV_ROOT"
"$ROLEMAP_ENV_ROOT/bin/python" -m pip install -r requirements-provider.txt
ROLEMAP_PYTHON="$ROLEMAP_ENV_ROOT/bin/python"
```

The reference readers use pandas 2.2.3 and NumPy 2.3.5 for KuaiSAR, and PyArrow
21.0.0 for Qilin. Core topology construction and the synthetic workflow use the
standard library.

## KuaiSAR

Obtain `src_inter.csv`, `rec_inter.csv` and `item_features.csv` from the
[official project](https://kuaisar.github.io/).

- Labels use `second_level_category_id`; retain the first nonmissing metadata
  row for each item.
- Search is two-pass: use exposures with metadata to choose each keyword's
  dominant category, breaking label ties lexically. Assign that keyword label
  to every retained exposure, including items without their own metadata.
- Recommendation sorts by `user_id,timestamp,item_id` and pairs each item with
  the next item within that user. The next item's available category labels
  the current item; terminal or unlabeled-next transitions are excluded.

```sh
"$ROLEMAP_PYTHON" -I scripts/materialize_kuaisar_role_counts.py \
  --kuaisar-root /path/to/KuaiSAR_final \
  --out-counts outputs/local_only/kuaisar_counts.csv \
  --out-summary outputs/kuaisar_counts_summary.json --hash-inputs
```

This descriptive extraction recovers 97,729 shared items in the v2 reference.
Keywords and user identities are used locally to construct labels or
transitions and are absent from the count table.

## Qilin

Obtain the provider files linked by the
[official repository](https://github.com/RED-Search/Qilin). Use the five `notes`
shards and search/recommendation train and test splits.

- Labels use `taxonomy2_id`, with `taxonomy1_id` fallback; missing taxonomy is
  excluded.
- Flatten `search_result_details_with_idx` or `rec_result_details_with_idx`.
- Engagement means a finite positive `click`, `like`, `collect`, `comment`,
  `share` or `page_time`. Choose the dominant engaged category; use exposures
  when none is engaged. Label ties are lexical string ties.
- Count every retained result appearance, including duplicates. Both provider
  train and test contribute to a descriptive topology, not training features.

```sh
"$ROLEMAP_PYTHON" -I scripts/materialize_qilin_role_counts.py \
  --qilin-root /path/to/qilin/provider_snapshot \
  --out-counts outputs/local_only/qilin_counts.csv \
  --out-summary outputs/qilin_counts_summary.json --hash-inputs
```

The reference recovers 20,540 shared items. `REAL_REUSE_CASE.md` records the
pinned provider revision and existing-map workflow. Agreement in common keys
and role support does not attest every historical label counter or recreate
legacy ranks.

## JDsearch historical proxy adapter

The [provider](https://github.com/rucliujn/JDsearch) supplies
`user_behavior_data.txt` and `product_meta_data.txt` under its own terms.
The adapter chooses the deepest category from level 4 down to 1. For search,
it takes the dominant category among clicked, carted or purchased candidates,
with exposure fallback; ties choose the smallest numeric category ID. For
reverse-chronological query-less histories, each older item receives the
category of the next newer query-less interaction.

```bash
python3 -I scripts/materialize_jdsearch_role_counts.py \
  --behavior /path/to/JDsearch/user_behavior_data.txt \
  --metadata /path/to/JDsearch/product_meta_data.txt \
  --out-counts outputs/local_only/jdsearch_counts.csv \
  --out-summary outputs/jdsearch_adapter_summary.json --hash-inputs
```

Query-less interactions can include recommendation or ordinary browsing. The legacy adapter’s `rec` label is therefore a proxy, not an observed recommendation-service label. JDsearch is outside the current genuine search/recommendation core.

Historical aggregate QA reports 1,248,451 shared items. The complete source,
count and topology files were unavailable in the current reconstruction, so
that historical result is not included in the 118,269-item v2 total. A canary
or successful CLI check cannot replace a full-input rebuild. All four cells
must be reported, including zeros; four occupied cells are not a pass gate.

## Topology handoff

Only items with positive support in both roles enter the topology. Numeric
component ranking and binning are fixed separately in `TOPOLOGY_PROFILE_V2.md`.
Keep full counts, maps and joins local and export only permitted aggregates.
