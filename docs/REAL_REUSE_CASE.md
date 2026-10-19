# Real-input Qilin Reconstruction

This CPU example starts from provider Parquet files and an existing local SID
export. It rebuilds paired role evidence under
`sr_sid_rolemap.topology.value_median.v2`, joins the supplied map, and checks a
declared shared time boundary. It trains no model and generates no new SIDs.

The reference map is resource-native and frozen-train. This is an internal
reconstruction and transfer check, not external adoption or reproduction of
an independent method. The map is not redistributed.

## Inputs and environment

Use the provider dataset at <https://huggingface.co/datasets/THUIR/qilin>,
revision `2d79000cef450b99f6423357ce86e5c132d32dd5`: five `notes` shards and
search/recommendation train/test Parquet files. The pinned card has Apache-2.0
metadata and MIT wording in its body; retain its notices and check applicable
terms. This package does not relicense provider data or model exports.

```sh
ROLEMAP_ENV_ROOT=/path/outside/resource/rolemap-provider-env
python3.12 -m venv "$ROLEMAP_ENV_ROOT"
"$ROLEMAP_ENV_ROOT/bin/python" -m pip install -r requirements-provider.txt
ROLEMAP_PYTHON="$ROLEMAP_ENV_ROOT/bin/python"
ROLEMAP_QILIN_ROOT=/path/to/qilin/provider_snapshot
ROLEMAP_SID_SOURCE=/path/to/existing/shared_sid_export.csv
```

Keep the environment outside the resource root. The Qilin reader uses PyArrow
21.0.0; the reference runtime is CPython 3.12.14. The synthetic quickstart uses
only the standard library.

The native SID CSV has seven fields:
`schema_version,dataset,item_id,system_id,sid_family,sid_role,sid_tokens`.
It must identify one Qilin shared system using provider `note_idx` keys and a
JSON list of at least two string tokens per item. A remapped index needs its
verified bridge. Conversion changes representation only; it does not attest
fitting provenance or automatically import an arbitrary native JSON export.

## Rebuild and join

```sh
"$ROLEMAP_PYTHON" -I scripts/materialize_qilin_role_counts.py \
  --qilin-root "$ROLEMAP_QILIN_ROOT" \
  --out-counts outputs/local_only/qilin_counts.csv \
  --out-summary outputs/qilin_counts_summary.json --hash-inputs

"$ROLEMAP_PYTHON" -I scripts/build_role_topology.py \
  --role-counts outputs/local_only/qilin_counts.csv \
  --out-csv outputs/local_only/qilin_topology_v2.csv \
  --out-json outputs/qilin_topology_v2_summary.json

"$ROLEMAP_PYTHON" -I scripts/normalize_sid_export.py \
  --input "$ROLEMAP_SID_SOURCE" \
  --out-csv outputs/local_only/qilin_sid_map.csv \
  --out-summary outputs/qilin_sid_conversion.json

"$ROLEMAP_PYTHON" -I scripts/admit_sid_family.py \
  --topology outputs/local_only/qilin_topology_v2.csv \
  --sid-map outputs/local_only/qilin_sid_map.csv \
  --family locally_supplied_shared_sid \
  --out-csv outputs/qilin_admission_cells_v2.csv \
  --out-json outputs/qilin_admission_v2.json
```

Use fresh output paths. Keep counts, maps and joins local. The materializer
reads category/item fields and result details without query text or user IDs.
Both train and test contribute to a descriptive topology; the counts are not
a train-only model feature. Dataset keys are lowercase `qilin`.

## Current reference

The role-count file has 1,988,519 rows, SHA256
`dff45018241d29a4cf25f76d1365fb3d3aad1d7fef63adb56a60f5e0d054c390`.
It recovers 20,540 common items and the historical per-item support counts.
This does not establish identity of every historical label counter.

| V2 check | Qilin reference |
| --- | ---: |
| HH / HL / LH / LL | 0 / 0 / 8,595 / 11,945 |
| Items tied at the RSD median | 14,884 |
| Items tied at the absolute-RSI median | 11,945 |
| Zero absolute RSI assigned H | 0 |

The topology CSV SHA256 is
`8096e7ca68166e120591568185cc0fd3a763c246e0c586cca369140b21f0cbed`;
the semantic key/rank/partition SHA256 is
`aa51f5cca429a9eea5a3f17d730c2c6f6921dfdb307a7e108ced817737ae7d4e`.
Current structural references are indexed in `reports/PROFILE_EVIDENCE_INDEX.json`.
The unchanged global SID-map identity does not make old sliced observations
compatible with these new bins.

## Check the declared shared time boundary

```sh
"$ROLEMAP_PYTHON" -I scripts/audit_shared_time_boundary.py \
  --qilin-root "$ROLEMAP_QILIN_ROOT" \
  --sid-map "$ROLEMAP_SID_SOURCE" \
  --out-json outputs/qilin_shared_time_check.json
```

Determine event intervals from all finite detail timestamps before positive
or map filtering. The test anchor is the earliest event start in either test
role. Retain train requests ending before it as development data; exclude
crossing and post-anchor requests without moving them into test. For sorted
development end times, validation uses nearest-rank index `ceil(0.85*n)-1`.
Keep provider test partitions intact.

The existing reference excludes 3,115 crossing and 41,841 post-anchor requests
from 127,461 provider-train requests and preserves 17,307 provider-test
requests. This is a conditional temporal-protocol finding, independent of v2
RSD bins and SID assignment; it is not a leakage-effect or performance result.
Asynchronous provider splits are not erroneous because a user chooses another
global cutoff.

A map join checks identity coverage, not semantic quality, training provenance,
decoding or utility. Compare the profile and both topology hashes before
reusing its slices; see `TOPOLOGY_COMPATIBILITY.md`. A receiver must lawfully
hold its declared existing map. Hosted access and outside adoption remain
separate release steps.
