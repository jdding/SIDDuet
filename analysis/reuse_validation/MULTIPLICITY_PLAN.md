# Posthoc multiplicity sensitivity plan

Declared before this sensitivity is computed, 2026-10-19. This is a posthoc robustness analysis of the previously reported audit, not a new primary experiment or retrospective preregistration.

Input: original audit_main_r1 paired per-request losses from the fixed fit and the original aggregate RESULTS.json. The five estimable views are gensar_shared2 (previously designated primary), gensar_semantic_complete, gensar_collaborative_complete, gaoq_depth1 and gaoq_depth2. gaoq_depth3 has no catalog collisions and no loss endpoint; retain it as a control and exclude it from the five-endpoint family.

First reproduce all original macro point estimates and search/recommendation/macro 95% intervals with the original 2,000 draws, seed 20261019 and sorted user identifiers. Require agreement within 1e-12. Reuse each user's observations from both roles jointly. Averaging remains request means within role, then equal role means. Model choices, data partitions, mappings, loss and frozen fit are unchanged.

Then extend the same random stream to 20,000 user-cluster draws, CPU only, no model calls. Report 99% marginal percentile intervals for each of the five views (quantiles 0.005 and 0.995). By the Bonferroni construction these target nominal 95% family coverage, without assuming independence among views. The bootstrap remains an approximation conditional on the fixed cohort, map and fit. More draws reduce tail Monte Carlo noise; they add no data.

Report both the original pointwise result and all-view sensitivity. Do not switch the primary to a surviving secondary view. Do not infer a ranking gain or new independent replication. No p-values inferred from a non-null bootstrap distribution. Output only aggregate estimates, intervals, coverage, hashes and analysis settings; original private loss rows remain in their source directory.

Synthetic verification: joint-user resampling must preserve cancellation between opposite task effects; the wider interval must contain the narrower interval on the same draws. An exact original-result reconstruction is the real-data validation.
