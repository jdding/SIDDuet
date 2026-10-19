# Fixed native code exports for all six views

These author-approved derived inputs make the temporal allocation workflow
replayable without retraining a quantizer. The three maps each contain only
20,540 public-provider catalog item keys and their derived codes. The cohort
CSV/JSON contain only catalog keys. They contain no requests, users, sessions,
query/history text, role counts/labels, embeddings or checkpoints.

| File | Declared views |
| --- | --- |
| `native_maps/gensar_semantic.csv` | GenSAR shared two-token prefix; semantic complete code |
| `native_maps/gensar_collaborative.csv` | GenSAR collaborative complete code; shared-prefix equality check |
| `native_maps/gaoq_complete.csv` | GAOQ depth1, depth2 and full depth3 |
| `cohort.csv` / `cohort.json` | Fixed 20,540-item catalog cohort; no role-label join |

`MAPS.json` resolves all paths relative to this directory. It checks that the
GenSAR complete views share the same first two tokens for every item. Views and
prefixes are granularities of two native components, not six independent
methods or full serving-system reproductions.

## Replay from provider Qilin files

Obtain the original Qilin Parquet snapshot from the
[official dataset release](https://huggingface.co/datasets/THUIR/Qilin), under
its access terms. Keep those files and all generated request/fitted/score files
outside this public checkout. The extractor verifies the original source hashes;
a newer or different snapshot requires an explicitly revised protocol. The
included maps avoid quantizer retraining; fitting categorical counts remains
part of the replay.

From the resource root, first install the optional NumPy/PyArrow dependencies
in your own environment if needed, then change into this directory:

```bash
cd data/native_exports
export RESEARCH=../../analysis/reuse_validation
export PROVIDER_ROOT=/path/to/original/qilin/provider_snapshot
export REPLAY=/path/to/new/local/replay

python3 "$RESEARCH/extract_exposures.py" \
  --provider-root "$PROVIDER_ROOT" --universe ./cohort.csv \
  --protocol "$RESEARCH/PROTOCOL.md" \
  --out "$REPLAY/requests" --phase trainval

python3 "$RESEARCH/allocation_forecast.py" --mode fit \
  --input "$REPLAY/requests" --out "$REPLAY/fit" \
  --maps-manifest ./MAPS.json --protocol "$RESEARCH/PROTOCOL.md" \
  --manifest "$REPLAY/requests/EXTRACTION_RECEIPT.json"

python3 "$RESEARCH/allocation_forecast.py" --mode evaluate \
  --input "$REPLAY/requests" --out "$REPLAY/audit_results" \
  --fitted "$REPLAY/fit/restricted/FITTED.json" --evaluation-split audit \
  --maps-manifest ./MAPS.json --protocol "$RESEARCH/PROTOCOL.md" \
  --manifest "$REPLAY/requests/EXTRACTION_RECEIPT.json"
```

Output directories must be new. The fixed split keeps all earlier training
requests and partitions the common later interval into tuning and audit users
jointly across roles. The engine never opens audit/test outcomes during fitting.
The audit reports aggregate losses, coverage and paired user-cluster intervals;
its generated restricted score rows and fitted probabilities stay local.

To replay `audit_common_r1`, repeat the fit into a fresh output with
`--common-window`, then evaluate that frozen fit on the same audit. The
restriction removes only 10 of 70,125 training requests and is a mild sensitivity.
The separate `--phase test` extractor can reconstruct historical official-test
requests into another fresh directory after fitting. Evaluate them with
`--evaluation-split test` and their own extraction manifest. Search and
recommendation occupy nonoverlapping calendars there, so those results are
transport checks, not evidence of a causal role effect independent of time.

Exact-input substitution was checked before inclusion: all three map CSVs match
the original fixed exports, all six groups and fitted view payloads match,
request-export hashes match, and original audit points/intervals and score files
are unchanged. `PROVENANCE.json` records the source and local validation hashes.
This verifies substitution of the supplied inputs, not a new scientific result.

## Terms and release boundary

The derived catalog exports retain Qilin provider Apache-2.0 terms and
attribution; see `LICENSE-QILIN.txt` and `NOTICE.md`. The dataset metadata
license and repository source-code presentation are distinguished in the
notice. No upstream native implementation source code is bundled or relicensed.
The exception is limited to these three maps and the minimal cohort; it does
not authorize redistribution of raw request/user/query data, role-label joins,
other complete maps or fitted models. This remains an unpublished local
candidate; public access, hosted demo and tag are not advertised as complete.
