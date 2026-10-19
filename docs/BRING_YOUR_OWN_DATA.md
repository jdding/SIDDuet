# Analyze your own catalog

Run RoleMap inside the environment that holds your data. The basic workflow needs a task-specific count table and, for code-group analysis, a mapping over the same item keys. It does not require uploading logs or retraining a recommender.

## 1. Define the observation

Export four columns from your existing processing: item key, task, contextual label and positive integer count. Use the same label vocabulary across search and recommendation. State what a count means (for example, one exposure, one positive interaction or one retained transition), how labels were assigned and which time interval was included. RoleMap does not infer these meanings or make differently constructed observations equivalent.

For a source CSV with `catalog_item,service,context_category,observations`, create a local JSON configuration:

```json
{
  "dataset": "my_catalog_v1",
  "fields": {"item_id": "catalog_item", "role": "service", "label": "context_category", "count": "observations"},
  "role_values": {"query": "search", "feed": "rec"}
}
```

Use a distinct dataset identity for a changed item namespace or preprocessing view. Missing item keys or labels, unknown task values and nonpositive or noninteger counts fail explicitly. Repeated item/task/label rows are summed.

```sh
python3 -I scripts/import_role_counts.py \
  --input /local/business_counts.csv --config /local/fields.json \
  --out-csv /local/new/counts.csv --out-json /local/new/import.json

python3 -I scripts/build_role_topology.py \
  --role-counts /local/new/counts.csv \
  --out-csv /local/new/topology.csv --out-json /local/new/topology.json
```

Keep real counts and item rows local. Only items with positive observations in both tasks enter this topology. Inspect the resulting item count, boundary ties and all four cells, including empty cells. A changed input view can produce different bins under the same numerical algorithm.

## 2. Supply a mapping

Export `dataset,item_id,sid` in CSV; `sid` is a JSON token list quoted as one CSV field. The dataset and item keys must match the count table. A privately remapped catalog needs its actual bridge; equal-looking integers are not a bridge. The Qilin-specific native converter is not needed for this generic path.

```sh
python3 -I scripts/admit_sid_family.py \
  --topology /local/new/topology.csv --sid-map /local/map.csv \
  --family my_supplied_map \
  --out-csv /local/new/admission.csv --out-json /local/new/admission.json
```

The report gives map coverage, collisions and group composition. A category-path map can exercise the interface; label it as a catalog grouping rather than a learned tokenizer.

## 3. Attach predictions or test pooling

For model inspection, export the actual finite scores with
`dataset,unit_id,role,candidate_id,is_target,score`. Each request needs one target and distinct candidates. Report targets outside the paired-observation topology before selecting covered requests; the strict adapter rejects a missing target. Use `scripts/adapt_method_scores.py` and `scripts/evaluate_fixed_candidates.py` as shown in `REBUILD_PROTOCOL.md`. Evaluation v3 averages gain within exact score ties, so candidate renaming cannot change a result. It evaluates the supplied candidate set, not full-catalog retrieval.

For a later exposure-allocation comparison, use the separate request and map interfaces in `analysis/reuse_validation/README.md`. That workflow needs declared temporal splits and stable local user identifiers for clustered intervals. It has additional input requirements beyond the count table.

## A real input-conversion check

`analysis/model_reuse/prepare_observations.py` reads the provider-processed UniSAR KuaiSAR files and produces a business-style CSV, a direct reference count table and an illustrative category-path map. The documented 1,024-user sample yields 320 common items; importing the business-style CSV reproduces the direct topology byte for byte and joins all 320 mapped items. It uses positive histories and truncated clicked-item sessions. It is a portability example on another view of KuaiSAR, not an additional independent dataset or evidence of outside adoption. See `analysis/model_reuse/README.md` for the reproducible commands and exact source requirements.
