# Development

Runtime dependencies are listed per workflow. The synthetic command needs only the
standard library; real-model and provider workflows have their own pinned environments.

Source layout uses Ruff 0.14.1 with `ruff.toml` (100 columns, Python 3.9 syntax).
The byte-bound canonical `scripts/build_role_topology.py` is intentionally excluded
from mechanical formatting. Its algorithm and source identity are fixed by the v2 references.

Before changing code, run the relevant checks from the root:

```sh
python3 -I scripts/validate_release.py
python3 -I analysis/model_reuse/test_checkpoint_assembly.py
python3 analysis/model_reuse/test_count_import.py
python3 analysis/model_reuse/test_score_contract.py
```

With the optional NumPy analysis environment, also run
`python3 -m unittest discover -s analysis/reuse_validation -p test_allocation_forecast.py`.
The diagnostic extension README lists its fabricated-data checks; the real UniSAR replay
checks the pinned provider/source/checkpoint inputs and original prediction hashes.

Generated outputs, provider data and caches stay outside Git. Update the release manifest
and checksums when source changes. Use a new tag for published corrections; keep old tags fixed.
