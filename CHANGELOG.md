# Changelog

## 0.4.1 — 2026-11-24

- Add `--allow-unpaired-targets` (`adapt_method_scores.py`) and `--paired-target-slices` (`evaluate_fixed_candidates.py`) so the live browser and local demos compute paired-target coverage alongside full-test and covered NDCG@10 on the same candidate sets.
- Compare pooled, separate, and shrinkage rules with fixed smoothing strengths (`alpha = beta = 10`) on held-out synthetic counts, and align Table 4 captions with task-conditioned shrinkage selection.
- Report actionable `pip install -e '.[calibration]'` / `'.[provider]'` guidance when running optional CLI subcommands without NumPy or PyArrow.
- Clarify the six saved-draw Table 2 comparisons versus the separate Qilin GenSAR shared-prefix replay across quickstart and demos.
- Preserve all historical study summaries (`v0.2.8`), checkpoint assets (`v0.2.4`), and prior immutable tags (`v0.4.0` and earlier).

## 0.4.0 — 2026-11-23

- Upgrade the zero-install browser demo (`https://jdding.github.io/SIDDuet/`) and local HTTP demo to execute and display all three paper workflows directly: shared-code allocation JSD with interactive member share bars, pure-Python count-matched calibration, live `verify_table2.py` execution, paired-target prediction coverage (Table 3), and pooled vs. task-conditioned forecasting (Table 4 and training-only cohort sensitivity).
- Add standard Python packaging (`pyproject.toml`) and a unified `sidduet` CLI (`verify-table2`, `validate`, `calibrate`, `import-counts`, `replay-qilin`, `demo`) with zero core dependencies.
- Document measured single-CPU runtime and peak RSS benchmarks across Qilin (20,540 items) and KuaiSAR (97,729 items) scales.
- Clarify maintenance governance, sustainability practices, and the boundary relative to `SIDInspector` in top-level documentation.
- Preserve all historical `v0.2.8` study reports, `v0.2.4` checkpoint assets, and backward-compatible script paths unchanged.

## 0.3.0 — 2026-11-19

- Verify all six Table 2 rows from saved aggregate reference draws.
- Add a public-input Qilin replay of the GenSAR two-token prefix.

- Add a general paired-count calibration CLI for user-supplied datasets and maps.
- Average collision-support rank discounts over exact-support ties (diagnostic
  schema v2); topology v2 and fixed-candidate evaluation v3 stay unchanged.
- Reject missing SID values, malformed map rows and duplicate item keys.
- Normalize JSON token-list spelling consistently across map consumers.
- Preserve the published v0.2.8 checkout and all historical scientific results.

## 0.2.8 — 2026-10-26

- Add a standalone replay of training-only item eligibility, preserving both window outcomes, fixed input hashes and the original uncertainty correction.
- Document the exact UTC windows, request-loss calculation and distinction between raw and processed KuaiSAR views.
- Keep the main comparisons, mappings, checkpoint and measurement protocols unchanged.

## 0.2.7 — 2026-10-20

- Rename the toolbox display name to SIDDuet; retain the repository URL, commands and protocol identifiers.

- Clarify the decisions supported by paired coverage, count references and temporal pooling comparisons.
- Extend both paired-count reference simulations to 1999 draws, preserving the original 199-draw streams and all observed statistics.
- Report the larger Monte Carlo mean change in the sparse Qilin/ReSID-GAOQ stratum.
- Clarify that native-map export-time publication flags describe the historical export state.

## 0.2.6 — 2026-10-19

- Add a four-hour Qilin window selected from both tasks' actual calendar coverage before loss evaluation.
- Retain the primary, maps and estimators; report both windows with five- and ten-endpoint uncertainty sensitivities.

- Distinguish package-only analyses from provider-input reconstruction and private-data use.
- Explain the contribution relative to SIDInspector without excluding its interaction probes.
- Add the five-view Bonferroni bootstrap sensitivity, preserving all original fits and primary designation.

## 0.2.5 — 2026-10-19

- Readable source layout and CLI names, with the canonical topology implementation preserved.
- Optional input/code provenance receipts; the earlier flag remains a compatibility alias.
- A browser example that executes the actual Python core on synthetic inputs.
- The v0.2.4 checkpoint remains a separately licensed, fixed download.

## 0.2.4 — 2026-10-19

Initial public RoleMap release.

- Paired-observation topology, tie-preserving v2 protocol and explicit input contracts.
- Configurable count import, supplied-map admission and fixed-candidate score evaluation.
- Current aggregate references for KuaiSAR and Qilin, diagnostic analyses and local demo.
- Fixed Qilin maps and cohort for exposure-allocation replay.
- Real UniSAR prediction case, pinned replay inputs and a separately licensed checkpoint download.
