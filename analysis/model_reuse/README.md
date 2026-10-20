# Actual UniSAR predictions and a new input view

This optional workflow reads a compatible, locally held UniSAR implementation, its provider-processed KuaiSAR data and a previously trained checkpoint. It exports genuine predictions to the SIDDuet interface. The self-trained numerical checkpoint is now included under its separate CC BY-NC-SA4.0 terms. Original implementation, provider rows, vocabularies, histories and scores remain excluded.

The study uses UniSAR source commit `1a14a246066cd1aa6ee789c57ff2c7499f3d7379` from <https://github.com/TengShi-RUC/UniSAR>, and a checkpoint previously trained in this research workflow with seed 20230601 (SHA256 `67d335cdbc08a652f4eebd0e4f0493c01fa50ff388743a28cf34505ce0443de1`). It is not a checkpoint supplied by the original authors. The official repository links the processed KuaiSAR data and training procedure. [The complete replay](REPLAY.md) assembles this matching checkpoint from the package; users can also supply another compatible trained checkpoint for their own analysis. This resource does not reproduce checkpoint training or original-paper performance. Existing GenSAR and GAOQ component evidence remains separate; UniSAR uses atomic items and is not promoted to a shared-SID system.

Optional dependencies are PyTorch, NumPy, pandas, PyYAML and tqdm. The recorded local runtime is CPython 3.9.6, torch 2.8.0, NumPy 1.26.4 and pandas 2.3.3, CPU with four threads. All paths below are user-supplied; keep generated real data outside this checkout and use new output paths.

```sh
export DATA=/local/provider_unisar_kuaisar
export UPSTREAM=/local/pinned/UniSAR
export CHECKPOINT=/local/compatible/best.pt
export WORK=/local/new/rolemap_case

python3 analysis/model_reuse/prepare_observations.py \
  --processed-root "$DATA" --users 1024 --out "$WORK/small"

python3 -I scripts/import_role_counts.py \
  --input "$WORK/small/platform_counts.csv" \
  --config analysis/model_reuse/count_fields.example.json \
  --out-csv "$WORK/imported.csv" --out-json "$WORK/import.json"

python3 -I scripts/build_role_topology.py \
  --role-counts "$WORK/imported.csv" \
  --out-csv "$WORK/small_topology.csv" --out-json "$WORK/small_topology.json"

python3 -I scripts/admit_sid_family.py \
  --topology "$WORK/small_topology.csv" \
  --sid-map "$WORK/small/catalog_path_map.csv" --family catalog_category_path \
  --out-csv "$WORK/admission.csv" --out-json "$WORK/admission.json"
```

The small example validates the field mapping and input path. For broader model diagnostics, construct observations from all 22,699 nonpadding users, then export actual predictions:

```sh
python3 analysis/model_reuse/prepare_observations.py \
  --processed-root "$DATA" --users 22699 --out "$WORK/full"

python3 -I scripts/import_role_counts.py \
  --input "$WORK/full/platform_counts.csv" \
  --config analysis/model_reuse/count_fields.example.json \
  --out-csv "$WORK/full_imported.csv" --out-json "$WORK/full_import.json"

python3 -I scripts/build_role_topology.py \
  --role-counts "$WORK/full_imported.csv" \
  --out-csv "$WORK/full_topology.csv" --out-json "$WORK/full_topology.json"

python3 analysis/model_reuse/export_unisar_scores.py \
  --official-root "$UPSTREAM" --processed-root "$DATA" \
  --checkpoint "$CHECKPOINT" --users "$WORK/full/selected_users.json" \
  --topology "$WORK/full_topology.csv" \
  --out "$WORK/predictions" --per-role 200000 --batch-size 64

python3 -I scripts/adapt_method_scores.py \
  --scores "$WORK/predictions/covered_scores.csv" \
  --topology "$WORK/full_topology.csv" --method-id unisar_processed_kuaisar \
  --method-paradigm discriminative --score-direction higher_is_better \
  --out-csv "$WORK/adapted.csv"

python3 -I scripts/evaluate_fixed_candidates.py \
  --candidates "$WORK/adapted.csv" \
  --out-csv "$WORK/metrics.csv" --out-json "$WORK/metrics.json"

python3 analysis/model_reuse/analyze_predictions.py \
  --units "$WORK/predictions/units.csv" --topology "$WORK/full_topology.csv" \
  --inference "$WORK/predictions/INFERENCE.json" --out "$WORK/analysis"
```

`INFERENCE.json` distinguishes original test size, sampled and scored requests, duplicated-candidate exclusions, topology coverage, exact-score ties and direct metrics. `covered_scores.csv` includes only targets in the topology; compare it with the full inference report before interpreting slices. The evaluator's overall covered metric must match the corresponding direct metric up to displayed rounding. It does not mean the topology-covered cohort represents all requests.

The processed item namespace has no verified inverse map to the raw 97,729-item reference. Observations and predictions therefore join only within `kuaisar_unisar_processed`. Search context uses up to five positive items per stored session, recommendation context uses the next retained positive-history item, and observations are descriptive. These are not the complete-exposure raw-data reference or a new independent dataset. The full-test analysis was expanded after a low-coverage initial sample, so its intervals are descriptive, not untouched confirmation. The locked protocol and aggregate results are linked in `reports/model_reuse/`.

Software checks requiring no provider data:

```sh
python3 analysis/model_reuse/test_score_contract.py
python3 analysis/model_reuse/test_count_import.py
```

The test checks all-tie invariance to candidate renaming, a tie crossing the cutoff and score direction. Synthetic tests demonstrate the calculation, while the actual-prediction report records the real execution. Neither is external adoption.

To check the prior candidate-ID tie policy on exactly the same predictions:

```sh
python3 analysis/model_reuse/tie_policy_sensitivity.py \
  --scores "$WORK/predictions/all_scores.csv" \
  --units "$WORK/predictions/units.csv" \
  --inference "$WORK/predictions/INFERENCE.json" \
  --out "$WORK/tie_sensitivity.json"
```

The recorded full-test comparison is `reports/model_reuse/tie_policy_sensitivity.json`. Covered-versus-all NDCG differences have the same direction under both policies. Historical frozen reports keep their original protocol.
