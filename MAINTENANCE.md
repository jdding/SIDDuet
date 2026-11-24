# Maintenance and Sustainability

SIDDuet is maintained publicly at <https://github.com/jdding/SIDDuet>.

## Issue Tracking and Scope

Report adapter errors, numerical reproducibility discrepancies, mapping compatibility issues, schema fixes, and documentation bugs via [GitHub Issues](https://github.com/jdding/SIDDuet/issues). Please include the release tag (`sidduet --version`), exact command, Python/NumPy versions, and a minimal synthetic reproducer; never upload private logs or licensed provider rows. Issues are triaged on a best-effort basis by the repository maintainer, prioritizing correctness bugs and breaking dependency updates.

## Versioning and Long-Term Availability

- **Immutable release tags:** Every published release is identified by an annotated Git tag (e.g., `v0.4.1`) with a complete SHA-256 inventory (`PACKAGE_MANIFEST.json` and `CHECKSUMS.sha256`) verified by `sidduet validate`.
- **Protocol stability:** Corrections to code, adapters, documentation, or packaging receive a new semantic version tag with updated checksums and a `CHANGELOG.md` entry. Changes to measurement definitions increment the protocol version identifier so historical comparisons remain unambiguous.
- **Preservation of prior baselines:** Historical study reports and the separately licensed UniSAR checkpoint assets (`v0.2.4`) are preserved across releases without rewriting prior tags.

## External Dependencies Boundary

Provider datasets (KuaiSAR, Qilin) and upstream model implementations remain external and governed by their original terms. Only the derived Qilin catalog code exports (`data/native_exports/`) and self-trained UniSAR checkpoint parts (`v0.2.4`) are distributed under their respective license notices.
