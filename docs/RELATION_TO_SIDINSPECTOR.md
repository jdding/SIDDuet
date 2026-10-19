# Relationship to SIDInspector

SIDInspector v2 (https://arxiv.org/html/2606.10375v2) already accepts metadata and interactions. Its D3 probe measures co-occurrence neighborhood alignment, D4 examines popularity allocation, and optional probes cover refresh pairs and generator traces. Calling it a toolkit that reads only isolated mappings would be inaccurate.

| Research question | SIDInspector v2 | RoleMap contribution |
| --- | --- | --- |
| Are codes well formed; how many items share codes? | Mapping contract, utilization and aliasing probes | Shared prerequisite; not claimed as new |
| Do prefixes recover interaction neighborhoods? | D3 train-co-occurrence probe and bounded candidate-exposure checks | Not the new question tested here |
| Which task supplies each member's observations within one code? | Not a native paired-task report in the published v2 workflow | Paired task counts and contextual distributions joined before comparing maps |
| Are observed allocations unusual for comparable count volumes? | Not the reported D1--D7 population comparison | Band-matched and exact-total paired-count references |
| Should task observations be pooled for a later allocation forecast? | Not the reported temporal pooling workflow | Tuned pooled/task-conditioned estimators and heldout-user temporal comparison |
| Which model requests can the paired observation view cover? | Generator-trace hook; no empirical D7 results in v2 | Full fixed UniSAR prediction replay with explicit target coverage |

The difference is in the represented observations and completed analyses. A user could extend another toolkit to implement these analyses; no claim of software impossibility is made.

For example, the same code can contain one item supplying most search observations and another supplying most recommendation observations. Mapping utilization and alias size alone do not identify this task allocation. RoleMap keeps the two task observations separate and tests whether collapsing them loses information for a later exposure forecast. The 275-item example is located within the full population rather than treated as representative.

The forecast experiment uses counts and code groups. It does not validate RSD/RSI as predictors, semantic ground truth, causal interference or ranking improvement.
