# Expected Local Output

```text
PASS_PUBLIC_RESOURCE_SMOKE
wrote outputs/public_resource_smoke_result.json
```

The summary must have `status: pass` and empty issue lists.
`outputs/interface_contract_checks.json` lists the executed positive and
rejection checks; every `passed` field must be true. The synthetic topology has
eight items in four cells, admission join coverage 1.0, 16 within-code diagnostic
units, and eight fixed-candidate evaluation units. See `ARTIFACT_QUICKSTART.md`
for the output files and the limits of this synthetic replay.
