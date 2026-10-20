# Method Admission Protocol

SIDDuet first separates systems that actually expose a shared SID
from adjacent joint S&R methods, then records literature coverage, interface
specification, adapter verification, and executed evidence. A paper citation,
joint objective, generative label, or model-agnostic score column is not by
itself an admitted core system.

## Core Scope Gate

A core system must construct or consume a non-atomic multi-token SID, use the
same SID or an explicitly shared prefix/codebook in both roles, expose an
item-to-SID map, and provide at least one SID-specific diagnostic surface such
as collision groups, prefix survival, complete-SID recovery, shared-code use,
or role-specific suffix behavior. Systems that only share atomic item identity
remain in the adjacent-method partition.

Dataset coverage is tracked separately in
`docs/DATASET_ADMISSION_REGISTRY.json`. Candidate or derived-role datasets do
not enter the manuscript's registered-topology table until their topology is
materialized and passes the same QA as the registered datasets.

## Levels

- `literature_only`: the method is relevant, but its public artifacts do not support
  a reproducible SIDDuet path.
- `interface_specified`: a concrete mapping to one or more registered SIDDuet
  surfaces is documented, but the named implementation has not run on that declared surface.
- `adapter_verified`: pinned implementation and real data complete an
  end-to-end canary, including an exact topology join and aggregate QA.
- `rolemap_executed`: aggregate results from that adapter are included in the
  resource evidence.

## Required Manifest Fields

Each registry row declares `method_id`, `title`, `year`, `paradigm`, `sid_use`,
`code_status`, `data_status`, `admission_level`, `supported_surfaces`, and a primary
source URL. `paradigm` is `generative`, `discriminative`, or `hybrid`. `sid_use`
distinguishes actual shared SID consumers from joint S&R methods that only share
atomic item identity or model parameters. The top-level `scope_partitions`
field assigns every method to exactly one resource scope.

## Fixed-Candidate Export

Methods export only
`dataset,unit_id,role,candidate_id,is_target,score`. The deterministic score
adapter joins each unit's single target item to the registered SIDDuet topology
and adds `method_id`, `method_paradigm`, `score_direction`, and topology slices.
The evaluator then groups by method before computing metrics, so scores from
different models cannot be pooled accidentally. This interface evaluates supplied
scores; a synthetic schema smoke does not upgrade a named method to
`adapter_verified` or `rolemap_executed`.

## Admission Boundary

SID construction families and shared-SID systems are separate axes. A new SID
family must pass the SID-map/topology join contract. A new core system must also
pass the scope gate and identify the evaluation surface and candidate universe
that produced its scores. Full-catalog generation claims require the
full-catalog reach schema rather than the fixed-candidate interface.

## Current execution scopes

The GenSAR and native GAOQ exports are independently executed quantizer components. They do not establish complete published-system reproductions. UniSAR now has an actually executed candidate-score interface on its provider-processed KuaiSAR view, with a verified earlier-trained checkpoint. It remains in the adjacent atomic-item partition. The registry records these scopes independently; a successful score adapter does not make a model a shared-SID system. Other named interfaces remain specified rather than executed until a real input/output chain is supplied. See `METHOD_COVERAGE.md`.
