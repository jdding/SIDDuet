# Result scope and sensitivity

An independent local numerical review accepted the original analysis with a bounded claim before the multiplicity sensitivity was added. This is a review within the same model family, not an externally attested independent-family evaluation. Review report SHA256: `d35a1ee825d2e5ba1c1dbe19d9e210ce5022f0ca268faa64ca61f7fc927ce228`.

The review checked source/fitted hashes, deterministic tuning choices, exact fractional train counts, every saved request score and user-cluster uncertainty calculations. No audit outcome selected the estimator or hyperparameters. This summary includes aggregate findings only.

| Primary shared-prefix audit | Loss, nats |
| --- | ---: |
| Selected pooled forecast | 1.70561434 |
| Selected role-aware forecast | 1.69292816 |
| Pooled minus role-aware | 0.01268618 |
| Paired user-cluster 95% interval | 0.00158374 to 0.02418106 |

A later [posthoc multiplicity sensitivity](MULTIPLICITY_README.md) reproduces every original point estimate and task/macro interval within 1e-12, then uses 20,000 paired user-cluster draws. Its five-view Bonferroni interval for the primary is [-0.001756, 0.027320] nats and includes zero. The secondary GAOQ two-token prefix remains positive, [0.004840, 0.011992]. This added sensitivity was self-reviewed locally; the earlier numerical review does not attest to it. Neither the original primary designation nor the fits were changed.

This modest change is about 0.74% of baseline macro loss. The audit scores 528 search and 1,067 recommendation requests from 1,019 users, corresponding to 27.46% and 29.65% of valid source requests after cohort/collision conditions. Recommendation's own interval includes zero. Complete-code views are mixed; raw losses across granularities are not method rankings.

The common-training-window restriction removes only 10 of 70,125 training requests; just one removed request contains a primary collision exposure. No changed member probability is scored in the primary audit, so its scores are exactly unchanged. This is a very mild sensitivity, not a second independent replication or proof of calendar invariance.

The historical official-test transport checks use nonoverlapping search/recommendation periods. They cannot isolate a causal role effect independent of time or serving policy. The historical cohort was selected using pooled observations and is not an unbiased prospective full-catalog population.

[The posthoc uniform diagnostic](UNIFORM_BASELINE_DIAGNOSTIC.md) compares the obvious no-fit predictor without changing the frozen primary comparison. Uniform is worse on the primary macro tuning/audit comparison, although it beats selected pooling for search alone. The pooled estimator was selected for the macro objective, not separately as the best predictor of each role. Equal alpha grids also do not equalize effective shrinkage; the result supports the tested estimator choice, not an isolated causal role signal.

This demonstration does not validate custom RSD/RSI indices, semantic incompatibility, ranking benefits, full native systems or superiority to every possible roleblind predictor. It shows a concrete use of linked role counts and supplied groups. The released fixed maps and minimal cohort now supply all six study views; exact historical replay still requires the corresponding upstream Qilin Parquet request inputs, reconstructed locally under provider terms.
