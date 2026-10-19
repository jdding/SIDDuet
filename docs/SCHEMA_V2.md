# Public Resource Schema

## Dataset Profile

Required fields: `dataset`, `common_items`, `topology_cells`,
`min_cell_items`, and `release_level`.

## Reconstruction Inputs

- Normalized role events:
  `dataset,role,event_id,item_id,item_label,engaged,weight`, where `weight` is
  optional and defaults to one.
- Role-label counts: `dataset,item_id,role,label,count`, with role in
  `search,rec`.
- SID family map: `dataset,item_id,sid`.
- External method scores:
  `dataset,unit_id,role,candidate_id,is_target,score`.
- Adapter-generated v2 fixed candidates:
  `method_id,method_paradigm,score_direction,dataset,unit_id,role,candidate_id,is_target,score,topology_cell,rsd_bucket,rsi_mag_bucket`.

Each method/unit/role has exactly one target and distinct candidate identifiers.
Scores must be finite; score direction is explicit. The adapter requires the
target to exist in the topology. The v1 fixed-candidate sample is retained as a
historical fixture. Typed-record fields and evidence-state rules are specified
in `schemas/rolemap_record.schema.json` and `docs/ROLEMAP_RECORD_PROTOCOL.md`.

The public fixtures are fabricated. Licensed item-level inputs remain local;
the admission and evaluation commands emit aggregate outputs.

## Evidence Surface

Required fields: `dataset`, `surface`, `metric`, `value`, `secondary`,
`release`, and `boundary`.

Allowed surfaces:

- `sampled ranking`;
- `collision diagnostic`;
- `SID-family admission (RQ-VAE)`;
- `SID-family admission (ReSID-GAOQ)`.

## Taxonomy-Rule Audit

Required fields: `labeled_rows`, `human_agreement`, `agreement_rate`,
`unsure_rate`, `disagree_rate`, and `claim_scope`.

## Release Scope

Required fields: `public` and `restricted`.

## Inspection Samples

Samples must not expose raw item ids, raw query text, raw SID maps, or full
topology joins. Public samples may expose synthetic identifiers or hashed keys
plus coarse bins for schema inspection; hashing does not guarantee anonymity.
