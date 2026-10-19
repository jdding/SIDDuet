# Real prediction and input-portability protocol, v1

Frozen before scoring, 2026-10-19. This is a descriptive diagnostic and software integration study, not a leaderboard reproduction or a new training comparison.

## Selection and identities

GenSAR full generator checkpoints were not found among the available local matching artifacts. Its prior independent native quantizer evidence is retained. Use the available UniSAR official implementation (commit 1a14a246066cd1aa6ee789c57ff2c7499f3d7379) and the previously trained seed-20230601 checkpoint, SHA256 67d335cdbc08a652f4eebd0e4f0493c01fa50ff388743a28cf34505ce0443de1. This is a checkpoint trained earlier by this research workflow, not an original-author released checkpoint. Source and data must match their recorded hashes before inference. No new neural training, remote compute, LLM or paid API is used.

Processed item IDs have no verified inverse bridge to the raw RoleMap reference. Construct all observations and prediction joins within their existing namespace, dataset=kuaisar_unisar_processed. Do not attach these IDs to the 97,729-item raw-data topology by numeric coincidence.

## Input conversion

Select 1,024 users by the first SHA256(seed:user:processed_user_id) values with seed rolemap-external-20261019-v1. Convert their stored histories to dataset,item_id,role,label,count. Recommendation labels use the next retained item's second-level category after chronological ordering. Search labels use the lexically tie-broken modal category of the up-to-five positive items in each stored search session; count each session once per user. Only items observed in both tasks enter the diagnostic topology. This positive-history view is descriptive and distinct from the full-exposure raw-data reference; it does not add a new dataset or a prospective prediction claim.

## Actual model outputs

Within each role's original test file, retain selected-user requests and choose the first at most 1,024 rows by SHA256(seed:role:original_row_index). Preserve each original one-target plus 99-negative candidate list. Record duplicated-candidate units explicitly and do not silently alter them. Score all chosen units; report topology-covered and uncovered targets separately. Export unrounded finite model scores, the exact same item keys and declared score direction. Keep requests, users, checkpoints and scores local.

Use a CPU pilot of at most 16 requests per role to measure setup/inference, compare batched and single-request results and verify candidate ordering. Retain the fixed checkpoint; do not choose another seed by its diagnostic result. Disable PyTorch nested-tensor fastpath only as an explicitly recorded runtime execution choice; preserve upstream model source and weights.

## Metrics and diagnostic question

Compare the independent direct NDCG@10 and Hit@10 with the RoleMap public adapter/evaluator. Average over every possible target rank within each exact score tie, making the result invariant to candidate IDs and input order. Report the prior ID-tie-broken metric as a sensitivity if ties occur; do not rewrite old observations under the new policy. All unjoined requests and exact-score ties are counted.

Question: does maximal label separation (base-2 label JSD=1, tolerance 1e-12) identify different observed prediction performance beyond support? Within each task, stratify by floor(log2(search_count+rec_count)) and floor(abs(log2((search_count+1)/(rec_count+1)))). Compare maximal with nonmaximal separation in strata with at least five requests in each group. Weight strata by their smaller group size. Report retained support, all raw group means and an explicitly descriptive user-cluster bootstrap interval (2,000 draws; fixed seed 20261019). If there are fewer than three eligible strata or fewer than 20 users, report insufficient support rather than a significance result. Do not infer causal task effects, semantic error or ranking gain. The existing separate temporal allocation experiment remains the resource's evaluated decision example.

## Completion

Require hash-matched actual predictions, input conversion and a fresh process replay of public scripts using only documented inputs. A same-agent/process receiver test is software evidence, not external adoption. A new empirical association may be null; its sign is not an execution gate. Keep the original v2 reference/results unchanged and version this input view and score-tie evaluation separately.

## Input-coverage amendment before formal scoring

The 1,024-user input-portability example produces only 320 common items. The 16-per-role pilot covers zero target items in that small topology; this is an input-coverage failure, not a negative diagnostic finding. Retain that complete pilot unchanged. For the real-model diagnostic, use all 22,699 nonpadding provider users to construct observations, while keeping the originally selected 1,024 prediction users and the same request-sampling rule. No model scores, effect direction, threshold or significance determined this amendment. The small view remains the portability example, not a replacement full provider reference. The converter also exports an illustrative two-level catalog-category mapping to exercise the supplied-map interface; it is not called a new learned tokenizer.

## Descriptive full-test expansion

The initial fixed-user inference scored 562 search and 1,024 recommendation requests, with only 19 and 34 topology-covered targets. Preserve this run as the initial sample. To report applicability precisely, expand inference to every request in both original provider test files and all provider users. Use the same source, checkpoint, topology, candidate lists and exact-tie metric. This is an expanded descriptive census after inspecting the initial sample, not an untouched confirmatory test. No model/threshold/candidate choices are changed.

Additional descriptive question: how do metrics on the paired-observation cohort differ from metrics on all supplied test requests? Report both denominators, all original candidate lists, per-role mean NDCG@10, coverage and the difference between cohort and full-test means with user-cluster resampling. This measures a selection association, not a causal effect or a model-ranking gain. The counts/topology are descriptive inputs; no claim of out-of-time prediction is made by this analysis. Retain the original protocol's support-stratified maximal-JSD diagnostic, including insufficient-support outcomes.
