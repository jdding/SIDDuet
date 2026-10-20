# What the release supports

RoleMap is software for joining task observations to supplied code maps. The release includes runnable synthetic inputs, aggregate references and the approved Qilin catalog exports. Real observation rows and request losses must be reconstructed locally or supplied by the user.

| Inputs available | Executable use | Additional requirements |
| --- | --- | --- |
| Release alone | Eight-item end-to-end example; verify current aggregate references | Python standard library, or the online example |
| Shipped Qilin catalog exports | Inspect three 20,540-row maps as six complete/prefix views | Standard-library CSV/JSON reading; example below |
| Licensed KuaiSAR/Qilin provider files | Reconstruct paired observations and contextual labels | Provider files and the relevant reader dependencies |
| Historical Qilin request files plus shipped maps/cohort | Reproduce both temporal windows and multiplicity sensitivity | NumPy; local train/tuning/audit request exports |
| Fixed checkpoint plus pinned UniSAR source and processed data | Replay the full 166,981-request prediction case | Separate v0.2.4 checkpoint assets and the declared CPU environment |
| Own counts/labels and item-to-code map | Inspect task support and code-group allocation | Local schema conversion; actual common item keys |
| Own request exposures or candidate scores | Compare pooling choices or evaluate supplied predictions | Declared temporal splits/user clusters, or actual scored candidates |

## Use the outputs to choose an analysis

1. Check which items and prediction targets have observations in both tasks. Keep the full candidate-domain evaluation as the reference, and report covered and uncovered requests separately. A missing task observation means the paired diagnostic is unavailable for that item.
2. Inspect the two tasks' member counts within each shared code. Compare allocation divergence with the count-matched references before interpreting different leaders as unusual task separation.
3. To decide whether to pool observations for exposure forecasting, declare a cohort, mapping and time window, fit the supplied candidate estimators on earlier requests, select on tuning users, and compare their later losses and uncertainty. Keep all declared code views and report their coverage.

The forecast comparison chooses between the tested estimation procedures on the declared data. It does not provide a universal pooling rule or an RSD/RSI threshold for model selection. Role conditioning changes both the member frequencies and effective smoothing; the existing [baseline diagnostic](../analysis/reuse_validation/UNIFORM_BASELINE_DIAGNOSTIC.md) explains that boundary.

## Run without provider inputs

`python3 -I scripts/validate_release.py` runs the synthetic interfaces and checks the shipped references. The reference checks verify the released reports; they do not reconstruct real observations from aggregates.

The native catalog exports contain three numeric item-to-code maps and a 20,540-item cohort. `MAPS.json` defines six views. They contain no task-count or contextual-label joins. This command reads only those public files and reports code-group structure:

```sh
python3 - <<'PYCODE'
import collections, csv, json
from pathlib import Path
root = Path('data/native_exports')
manifest = json.loads((root / 'MAPS.json').read_text())
for view in manifest['maps']:
    counts = collections.Counter()
    with (root / view['path']).open(newline='') as handle:
        for row in csv.DictReader(handle):
            tokens = json.loads(row['sid'])
            if 'depth' in view:
                tokens = tokens[:view['depth']]
            counts[tuple(tokens)] += 1
    print(view['name'], 'items=', sum(counts.values()),
          'codes=', len(counts),
          'collision_groups=', sum(n > 1 for n in counts.values()))
PYCODE
```

## Rebuild observations and new analyses

The original pairing and population analyses require provider observations. Follow [preprocessing](PREPROCESSING_PROTOCOL.md), then [rebuilding](REBUILD_PROTOCOL.md). Published collision references alone cannot recover per-item task allocations or substitute a different labeling rule.

[Temporal reuse](../analysis/reuse_validation/README.md), including the [additional shared window](../analysis/reuse_validation/SHARED_WINDOW_README.md), uses actual request exposures, not only item counts. The shipped maps remove the need to retrain quantizers; the provider Parquet requests are still required. The new [multiplicity instructions](../analysis/reuse_validation/MULTIPLICITY_README.md) use the resulting local score rows and emit aggregates only.

[Complete checkpoint replay](../analysis/model_reuse/REPLAY.md) additionally needs the separately licensed weights, upstream source and processed data. Source cloning never downloads those weights.

For internal or another public dataset, use [Bring your own data](BRING_YOUR_OWN_DATA.md). Counts, mappings and scores remain local. Their actual item keys must join; equal-looking integers from private remappings do not establish correspondence. A field-mapped processed-KuaiSAR example verifies the importer on 320 common items. This is a second input view of KuaiSAR, not a third independent dataset or outside adoption.
