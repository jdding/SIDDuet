# SIDDuet

A toolkit for comparing semantic IDs across search and recommendation.

SIDDuet was previously named RoleMap. The repository is now jdding/SIDDuet; command names, record schemas and protocol identifiers retain their existing names for compatibility.

SIDDuet helps researchers inspect shared semantic IDs across search and recommendation.
It joins item-to-code mappings to task-specific observations, reports which items contribute
support to each task, and attaches model predictions with explicit coverage and candidate sets.

| Research question | Start here |
| --- | --- |
| Do shared codes contain different task contributors? | [Topology and code-group analysis](docs/REBUILD_PROTOCOL.md) |
| Can I use my own catalog and field names? | [Bring your own data](docs/BRING_YOUR_OWN_DATA.md) |
| Should task counts be pooled for later exposure-allocation forecasts? | [Temporal reuse example](analysis/reuse_validation/README.md) |
| Which requests does the diagnostic cover for a real joint model? | [UniSAR predictions and complete replay](analysis/model_reuse/REPLAY.md) |

For a new dataset, first check paired-observation coverage, then compare within-code task allocations against the count references. Use later requests to compare pooling choices within a declared cohort and window; keep the full-request prediction evaluation alongside the covered diagnostic.

The [additional shared-calendar example](analysis/reuse_validation/SHARED_WINDOW_README.md) selects a later period using actual task coverage, then repeats the pooling comparison with fixed methods.

See [what the release supports](docs/RESOURCE_CAPABILITIES.md) for package-only, provider-input and own-data workflows, and [the relationship to SIDInspector](docs/RELATION_TO_SIDINSPECTOR.md).

## Try it online

[Run the browser example](https://jdding.github.io/SIDDuet/) without installing Python.
It executes six shipped Python scripts on the eight-item synthetic fixture, checks
source hashes and shows the computed topology, map coverage and candidate metrics.
The first run loads a pinned Pyodide runtime; data stay in your browser.

## Quickstart

Python 3.10+ and the standard library are enough for the synthetic example:

```sh
git clone --branch v0.2.7 https://github.com/jdding/SIDDuet.git
cd SIDDuet
python3 -I scripts/validate_release.py
```

Expected: `PASS_PUBLIC_RESOURCE_SMOKE`. Results appear under `outputs/`.
This checks input contracts and the shipped reference files; it does not download data,
run a neural model, or establish real-data findings. See the [quickstart](ARTIFACT_QUICKSTART.md)
for the output tables and commands for your own inputs.

For the local browser interface:

```sh
python3 -I scripts/serve_demo.py --port 8765
```

Open <http://127.0.0.1:8765> and run the eight-item synthetic workflow.

## Data and method coverage

| Evidence | Verified scope |
| --- | --- |
| Paired task observations | KuaiSAR: 97,729 common items; Qilin: 20,540 |
| Native semantic-ID components | GenSAR quantizer and ReSID GAOQ; six declared code views |
| Real joint-model predictions | UniSAR: 166,981 original 100-candidate test requests |
| New input format | Field-mapped processed-KuaiSAR example: 320 common items |

GenSAR and GAOQ execution covers encoding components. UniSAR is an atomic-item joint
model; it validates the prediction interface, not a complete shared-SID generative system.
The processed-KuaiSAR example is another view of KuaiSAR, not a third dataset.
JDsearch's query-less history also includes browsing and is outside the observed paired core.
The [method coverage](docs/METHOD_COVERAGE.md) and [result guide](reports/README.md) explain these boundaries.

The active topology protocol is `sr_sid_rolemap.topology.value_median.v2`.
It preserves ties, including empty bins. Context-label differences describe observed
support and do not by themselves demonstrate semantic incompatibility, causal model
conflict, or ranking improvements.

## Reproduce the real examples

- [Qilin exposure-allocation forecasts](analysis/reuse_validation/README.md): includes
  the three approved fixed maps and minimal cohort, representing six views. Obtain
  request files from the provider; no quantizer retraining is needed.
- [Complete UniSAR replay](analysis/model_reuse/REPLAY.md): download the separately
  licensed checkpoint from the [fixed checkpoint assets](https://github.com/jdding/SIDDuet/releases/tag/v0.2.4)
  and obtain the pinned upstream source and processed data. The recorded CPU environment
  reproduced 16,698,100 score values byte for byte.
- [Provider reconstruction](docs/PREPROCESSING_PROTOCOL.md): build paired observations
  locally from licensed KuaiSAR or Qilin inputs.

## Contents and licenses

The repository contains usage documentation, analysis code, synthetic fixtures,
current aggregate references, a local demo, and the approved minimal Qilin catalog exports.
Raw logs, user/query/request rows, prediction rows, upstream source, paper drafts, and
internal review records are excluded. Checkpoint binaries are release attachments,
so cloning the code does not download model weights.

Own code: MIT. Documentation and aggregate summaries: CC BY 4.0. The approved Qilin
exports: Apache-2.0. The self-trained UniSAR checkpoint: **CC BY-NC-SA 4.0**, including
noncommercial and ShareAlike terms. See [LICENSE](LICENSE) and the
[model card](weights/unisar_kuaisar_v1/MODEL_CARD.md).

Use [CITATION.cff](CITATION.cff) to cite the software version. Report reproducibility
issues through [GitHub Issues](https://github.com/jdding/SIDDuet/issues).
