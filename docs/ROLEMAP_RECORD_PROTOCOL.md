# RoleMap Record Contract

`schemas/rolemap_record.schema.json` specifies the v1 fields and value types.
`scripts/validate_rolemap_record.py` checks that fixed contract and the evidence
state rules without third-party dependencies. Its `--schema` option checks the
schema identity and version; it is not a general JSON Schema interpreter.

Each record binds a dataset split and preprocessing profile, item bridge,
paired role evidence, topology coordinates, SID artifact version, observations,
claim permissions, provenance, and release scope. The fabricated example in
`samples/synthetic_rolemap_record.json` is independent of the eight-item replay.

L0 stores the paired role topology. L1 stores structural observations; L2 stores
ranking or decoding observations; L3 stores evaluated utility. An `observed`
level must contain an observed surface. A `null` level contains null surfaces.
A `blocked` or `not_evaluated` level cannot contain observed surfaces.
A supported L1–L3 permission requires an observed level. Unresolved permissions
require a non-empty next check. The validator checks these consistency rules;
it does not independently verify the truth of an attached measurement.

Run:

```bash
python3 -I scripts/validate_rolemap_record.py \
  --record samples/synthetic_rolemap_record.json \
  --schema schemas/rolemap_record.schema.json
```

The one-command release validation also executes invalid record examples,
including empty dataset/SID identity, contradictory blocked observations, and
an observed level containing only a null surface.
