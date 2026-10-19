# Sample Schema

The release contains one fabricated schema sample and one public-safe
inspection sample for reviewer inspection.

## `samples/synthetic_sid_topology_sample.csv`

This file is fabricated and can be used to inspect the expected shape of a SID
topology row without any upstream-derived item identifiers.

Fields: `dataset`, `synthetic_item_id`, `synthetic_sid`, `rsd_bucket`,
`rsi_mag_bucket`, `rsi_direction`, `topology_cell`, `search_support_bin`,
`rec_support_bin`, and `sample_type`.

## `samples/public_inspection_sample_1000.csv`

This file is a 1,000-row stratified inspection sample from derived topology
rows: 2 datasets x 4 topology cells x 125 hashed items. It keeps hashed item
and SID identifiers, topology labels, rounded diagnostics, coarse role
statistics, and aggregate collision-group summaries. It intentionally omits raw
item ids, raw SID tokens, raw text, full support values, embeddings, and
item-level joins.

The legacy alias `samples/hashed_inspection_topology_sample.csv` contains the
same rows for compatibility with earlier validators.

Key fields: `dataset`, `hashed_item_id`, `topology_cell`, `rsd_bucket`,
`rsi_mag_bucket`, `rsi_direction`, `rsd_score`, `rsi_signed`, `js_divergence`,
`neighbor_disagreement`, `top_label_mismatch`, role-support/entropy/count bins,
`grid_sid_hash`, `grid_sid_token_hashes`, `grid_group_size`,
`grid_group_unique_topology_cells`, `rqvae_sid_hash`,
`rqvae_sid_token_hashes`, `rqvae_group_size`,
`rqvae_group_unique_topology_cells`, and `sample_type`.

## `samples/public_collision_group_summary.csv`

This file summarizes the SID collision groups touched by the public inspection
sample. It reports only hashed SID identifiers, sampled item counts, full
aggregate group size, topology-cell coverage, and dominant-cell share.

## Diagnostic cases

`reports/killer_diagnostic_example.json` and
`samples/killer_diagnostic_hashed_items.csv` contain the primary 275-item
ReSID-GAOQ case used by the paper. `reports/diagnostic_case_study.json` is an
earlier GRID inspection record retained as package provenance rather than as a
second load-bearing case.

## `reports/cross_system_cell_evidence.csv`

This file reports topology-cell sampled NDCG@10 for GRID and resource-native
RQ-VAE-style SIDs, plus GRID support-rank diagnostic NDCG@10 for the same
dataset, role, and topology cell.
