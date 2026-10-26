# Training-only cohort sensitivity

Loss reduction is pooled minus task-conditioned exposure-allocation log loss. Intervals retain the original four-endpoint correction.

| Window (UTC, 27 Nov 2024) | Eligible items | Scored requests | Reduction (nats) | Adjusted interval |
| --- | ---: | ---: | ---: | --- |
| 09:43:45–11:14:48 | 4,088 | 266 | -0.0162 | [-0.0648, 0.0280] |
| 11:30–15:30 | 6,217 | 1,058 | 0.0141 | [0.0065, 0.0216] |

Full-precision values, task-specific losses, selected estimators and coverage counts are in [RESULTS.json](RESULTS.json). Reproduction instructions are in [the cohort replay guide](../../analysis/cohort_sensitivity/README.md).
