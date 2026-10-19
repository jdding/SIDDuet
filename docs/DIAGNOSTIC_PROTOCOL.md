# Diagnostic Protocol

The diagnostic protocol asks whether one shared semantic item identity carries
compatible roles in search and recommendation.

## Validation Paths

- Matched controls compare topology differences after support, popularity, and
  category matching.
- Oracle/null separation checks that oracle behavior does not leak into
  non-oracle claims.
- The 100-row taxonomy-rule audit reports 100/100 human agreement and supports
  taxonomy-rule interpretability only.

## Main Diagnostic Findings

- Sampled and diagnostic surfaces are not equivalent.
- Controlled role-conflict signal is role- and dataset-specific under matched
  controls.
- Additional SID families can satisfy the same aggregate contract while
  inducing different collision regimes.

## Boundaries

The resource does not claim full item-text semantic validation, production
serving quality, or raw-data redistributability.
