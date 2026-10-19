# Role-conditioned allocation: optional analysis

Use this analysis to ask whether one pooled distribution adequately forecasts which members of a supplied code group appear in search and recommendation. The comparison holds the item-to-code grouping fixed and evaluates pooled, role-balanced pooled, role-specific and shrunk categorical distributions using future requests. It forecasts observed exposures. It does not estimate relevance, improve ranking or train a recommender.

This directory is optional. The ordinary resource validator and dependency-free quickstart remain unchanged. Optional research dependencies are pinned in `requirements-research.txt`; the categorical engine needs NumPy and the provider extractor additionally needs PyArrow.

## Run the included checks

From this directory:

```bash
python3 allocation_forecast.py --mode self-test
python3 extract_exposures.py --self-test
```

These use fabricated fixtures and temporary files. They do not read provider data, native exports or heldout request files. They verify the software calculations, not the original study inputs or trained native code components.

## Analyze a supplied mapping

Provide your own item-to-code CSVs with `item_id,sid` columns. Each `sid` value is a nonempty JSON token list; quote it as a CSV field. Optional `depth` compares a prefix of that same token list. Copy `maps_manifest.example.json` to a local configuration and replace its paths. The optional `paired_shared_prefix` assertion checks that two complete views have the same prefix for every item. Optional `universe` is a JSON list of allowed item IDs. Paths in the manifest are resolved from the working directory. The example configuration is for user-supplied mappings. The study's three fixed maps and minimal catalog cohort are now included separately in [data/native_exports](../../data/native_exports/README.md), with all six view definitions and provider notices.

The engine accepts restricted JSONL request files named `train.jsonl`, `validation.jsonl` and `audit.jsonl` (or `test.jsonl`). Each row has `request_hash,user_hash,role,split,timestamp_start,timestamp_end,exposed_item_ids`. Roles are `search` and either `rec` or `recommendation`. Item IDs must join the CSV keys. Exposure lists are deduplicated. Distinct requests may share a user; keep that user hash stable across roles so the paired bootstrap retains dependence. `clicked_item_ids` may be present but is not used in fitting or scoring.

Use temporally earlier training requests. For a shared later audit interval, assign whole users jointly across roles to tuning or audit before comparing outcomes. The original protocol uses SHA256 of a fixed prefix plus the user hash, with the first 64 bits modulo 2 selecting the partition. The included historical extractor implements that rule. A new dataset/protocol should declare its own split, cohort and primary grouping before fitting.

Set the following paths to your local inputs and new output directories outside the public checkout:

```bash
export LOCAL_INPUT=/path/to/restricted/extracted
export LOCAL_MAPS=/path/to/your/maps_manifest.json
export LOCAL_PROTOCOL=/path/to/your/declared_protocol.md
export LOCAL_FIT=/path/to/new/restricted/fit
export LOCAL_AUDIT=/path/to/new/restricted/audit_results

python3 allocation_forecast.py --mode fit \
  --input "$LOCAL_INPUT" --out "$LOCAL_FIT" \
  --maps-manifest "$LOCAL_MAPS" --protocol "$LOCAL_PROTOCOL" \
  --manifest "$LOCAL_INPUT/EXTRACTION_RECEIPT.json"

python3 allocation_forecast.py --mode evaluate \
  --input "$LOCAL_INPUT" --out "$LOCAL_AUDIT" \
  --fitted "$LOCAL_FIT/restricted/FITTED.json" \
  --evaluation-split audit \
  --maps-manifest "$LOCAL_MAPS" --protocol "$LOCAL_PROTOCOL" \
  --manifest "$LOCAL_INPUT/EXTRACTION_RECEIPT.json"
```

The optional exporter manifest binds output SHA256 values. If your request producer uses another provenance system, omit `--manifest`; the engine still binds the actual train/tuning files, protocol, maps and its source. Do not silently edit any bound input after fitting. The evaluated audit must have request hashes distinct from training/tuning, user hashes distinct from tuning, and follow training in time.

Always supply `--maps-manifest` and `--protocol`. The byte-identical reviewed engine retains historical convenience defaults that refer to the original research checkout; this portable workflow does not use those defaults. The engine's historical `primary` flag recognizes the name `gensar_shared2`; that name identifies the original grouping and must not be used to relabel your own method. For a new map, use an accurate name and state its status in your declared protocol. Differences in raw loss across different groupings are not a method ranking.

The fit contains member probabilities and request/user hashes; evaluation writes restricted request-level scores. Keep those generated artifacts local. Share only reviewed aggregate outputs with the appropriate source/licensing permissions.

## Historical provider reconstruction

The included `extract_exposures.py` reconstructs the study's Qilin request/cohort surface using original provider Parquet files and the released minimal [cohort CSV](../../data/native_exports/cohort.csv). Provider requests are not redistributed. The three fixed derived maps and cohort avoid native quantizer retraining; [the replay recipe](../../data/native_exports/README.md) supplies all six views. It verifies the four known provider SHA256 values, the fixed cohort SHA256, request identities and whole-request time intervals. It rejects source changes and never opens provider-test sources during `trainval`.

```bash
python3 extract_exposures.py \
  --provider-root /path/to/original/qilin/provider_snapshot \
  --universe ../../data/native_exports/cohort.csv \
  --protocol ./PROTOCOL.md \
  --out /path/to/new/restricted/extracted \
  --phase trainval
```

This emits train, tuning `validation`, and user-disjoint `audit` files, preserving `source_chronological_split`. It retains requests without cohort exposure to report coverage. A separate `--phase test` can reconstruct the historical provider test after fit freeze. Output directories must be new. `PORTABILITY_CHANGES.md` documents the extractor's interface-only adaptation.

## Reading the aggregate results

`results/audit_main_r1` is the primary retrospective audit in a shared later time interval, using heldout tuning-disjoint users. `audit_common_r1` restricts training to the roles' common time range; it is a sensitivity, not an independent replication. The restriction removes only 10 of 70,125 training requests (one removed request contains a primary collision exposure). No changed primary probability is scored in the audit, so this is a very mild sensitivity rather than strong evidence of temporal invariance.

`test_main_r1` and `test_common_r1` apply the frozen fits to the previously used official test. Recommendation and search occupy nonoverlapping periods there, so these are historical transport checks; they cannot separate role association from calendar or serving-policy differences. The cohort and source data have also been used in earlier project work. None is described as untouched confirmation.

Each result set includes aggregate JSON and CSV only. Source bindings are file-path-to-hash metadata; no request/user/session identifiers, role-label joins, fitted probabilities, checkpoints or restricted scores are included in those reports. The explicitly approved catalog-only maps/cohort are separate derived inputs under provider terms. GenSAR complete views and prefixes are granularities of one native component; GAOQ is another component. They are not full serving-system reproductions or independent dataset replications. Full-code uniqueness is a no-collision control.

The primary GenSAR shared-prefix audit supports a modest improvement in this exposure-allocation forecast after retaining role. Its recommendation-only interval includes zero; the macro reduction is about 0.744% of baseline loss. Complete-view results are mixed. [The reviewed result summary](RESULT_REVIEW_SUMMARY.md) and [posthoc uniform diagnostic](UNIFORM_BASELINE_DIAGNOSTIC.md) show these qualifications and the no-fit baseline without changing the original comparison. Use the supplied coverage, intervals and full result table rather than generalize from the primary positive estimate.

## Reproduction limits

The synthetic checks are runnable with the optional dependencies. Supplied-map analysis remains available for other compatible maps and request protocols. The study's fixed three maps, minimal cohort and all six views are included under [data/native_exports](../../data/native_exports/README.md). Historical numerical replay requires obtaining the hash-matched provider Qilin Parquet files upstream, then running extraction, closed-form fitting and evaluation; it requires no quantizer retraining. The original raw requests, user/query data and role-label joins remain excluded. The release reproduces the declared allocation experiment from supplied derived maps plus lawful upstream provider files; it does not reproduce native component training or the entire original project pipeline.
