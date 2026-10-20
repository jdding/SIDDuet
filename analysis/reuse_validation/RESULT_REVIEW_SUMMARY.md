# Result scope

SIDDuet compares selected task-blind and task-conditioned member distributions using future exposure requests. The fixed maps, grid and tuning rule are identical across the two shared-calendar windows; the counts are refitted using each window's earlier data.

| GenSAR shared-prefix primary | First window | Additional window |
| --- | ---: | ---: |
| Task-blind macro loss | 1.7056 | 1.7613 |
| Task-conditioned macro loss | 1.6929 | 1.7528 |
| Reduction, nats | 0.012686 | 0.008504 |
| Pointwise 95% interval | [0.001584, 0.024181] | [0.006503, 0.010595] |
| Ten-endpoint sensitivity | [-0.003324, 0.028212] | [0.005618, 0.011448] |
| Scored requests | 1,595 | 4,719 |
| Users | 1,019 | 2,373 |

The [additional-window protocol](SHARED_WINDOW_PROTOCOL.md) was fixed from request coverage before fitting or reading its losses. The complete [two-window output](results/two_window_sensitivity/TWO_WINDOW_SENSITIVITY.json) includes all code views. GAOQ's two-token prefix has positive adjusted intervals in both windows; the GenSAR collaborative full view does not. The primary has not been replaced.

The first-window common-training-range restriction removes only 10 of 70,125 requests and changes no scored primary probability. It is a mild sensitivity. The earlier official-test transport check has nonoverlapping task calendars and is not a shared-window replication. The new shared-calendar window partly reuses its recommendation period. Both shared-calendar windows are on the same day and share 563 primary users.

The [no-fit uniform diagnostic](UNIFORM_BASELINE_DIAGNOSTIC.md) remains a separate qualification of the first window. Equal smoothing grids do not isolate a causal task effect or guarantee equal effective shrinkage. The selected procedure forecasts observed exposure allocation; it does not establish relevance or ranking improvement, validate RSD/RSI, or prove semantic incompatibility.

The package ships all six fixed map views and the cohort. Exact historical reconstruction still requires the provider Parquet observations under their terms. Source hashes and numerical reconstruction checks accompany the protocol; request-level losses and fitted member probabilities remain local.
