# Ethics and License

SIDDuet collected no new user data, recruited no participants, and ran
no intervention. The 100-row manual audit evaluates derived taxonomy labels,
not people. We make no new claim about upstream consent or institutional-review
status; those remain with the providers and each user's institution.

KuaiSAR must be obtained from its official project page and linked Zenodo
record; the provider page states CC BY-NC-SA 4.0. Qilin must be obtained from
its official repository and linked Hugging Face release. The repository code is
presented under MIT, but that code license is not treated as a grant to
redistribute raw Qilin user logs. Users must follow the provider data card,
access terms, and any institutional secondary-use review.

The public release exposes code, schemas, aggregate summaries, reproducibility
metadata, fabricated fixtures, and a bounded hashed sample. Hashing is not
treated as a general anonymization guarantee. The sample omits raw join keys
and SID tokens and is reviewed as derived data. Raw trajectories, query text,
other full item-level SID maps, full topology joins, full evaluation rows,
checkpoints, embeddings, and remote logs remain excluded.

Provider and preprocessing references:

- KuaiSAR: https://kuaisar.github.io/
- Qilin: https://github.com/RED-Search/Qilin
- JDsearch: https://github.com/rucliujn/JDsearch (follow its original data terms)
- Deterministic local transformation: `docs/PREPROCESSING_PROTOCOL.md`

## Approved minimal catalog exports

The only complete-map exception is the three named derived catalog-ID/code
CSVs and item-ID-only cohort in [data/native_exports](../data/native_exports/README.md).
They cover the declared six native code views and carry Qilin provider
Apache-2.0 terms and attribution. They contain catalog identifiers and derived
codes, not request/user/session/query/history data or a full role-label join.
Other complete maps and all raw/user-level or role-label joins remain excluded.
No upstream native implementation source code is bundled or relicensed.


## Research assistance

OpenAI Codex assisted protocol design, implementation, analysis scripts and documentation. The author is responsible for the resource and its claims. Labels are derived by the documented provider-field rules. Numerical checks use fixed source/input hashes, synthetic controls and full fixed-checkpoint prediction replay; no LLM-generated label judgments are treated as observed data.
