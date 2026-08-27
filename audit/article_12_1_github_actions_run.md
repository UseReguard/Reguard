# Article 12(1) GitHub Actions — Live Run Report

Date: 2026-08-27
Requirement: `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING` v1.1.0
Engine: compliance.pipeline 1.0.0
Workflow: `.github/workflows/compliance-article-12-1.yml`
Remote repo: https://github.com/m-urculu/compliance-tool

## GitHub Actions run URLs

| Target | Run URL | Status |
|---|---|---|
| SWE-agent/mini-swe-agent | https://github.com/m-urculu/compliance-tool/actions/runs/33076823454 | success |
| he-yufeng/CoreCoder | https://github.com/m-urculu/compliance-tool/actions/runs/33076826741 | success |
| HKUDS/nanobot | https://github.com/m-urculu/compliance-tool/actions/runs/33076829758 | success |

## Result per target (from compliance-result.json artifacts)

### SWE-agent/mini-swe-agent @ 25941c89cfbc91eb40b3f8756348c91d9977d57e

```
repository      = SWE-agent/mini-swe-agent
sha             = 25941c89cfbc91eb40b3f8756348c91d9977d57e
requirement_id  = AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
status          = PASS
reason          = all checks passed
duration_seconds= 38.129
event_count     = 5
evidence_origins= ['SYSTEM_NATIVE']
adapter         = minisweagent v1.1.0
requirement_ver = 1.1.0
runtime_version = 1.0.0
```

### he-yufeng/CoreCoder @ a03ef36412e432fc49d972d4007b36ce44ec5d9a

```
repository      = he-yufeng/CoreCoder
sha             = a03ef36412e432fc49d972d4007b36ce44ec5d9a
requirement_id  = AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
status          = PASS
reason          = all checks passed
duration_seconds= 11.544
event_count     = 3
evidence_origins= ['SYSTEM_STATE_EXPORTED_BY_HARNESS']
adapter         = corecoder v1.1.0
requirement_ver = 1.1.0
runtime_version = 1.0.0
```

### HKUDS/nanobot @ 4d204ba077a86dc42225c16f8f90032013ea1969

```
repository      = HKUDS/nanobot
sha             = 4d204ba077a86dc42225c16f8f90032013ea1969
requirement_id  = AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
status          = PASS
reason          = all checks passed
duration_seconds= 23.064
event_count     = 5
evidence_origins= ['SYSTEM_NATIVE']
adapter         = nanobot v1.1.0
requirement_ver = 1.1.0
runtime_version = 1.0.0
```

## Local vs GitHub Actions — exact match

| Target | Local status | Local event count | GHA status | GHA event count | Match? |
|---|---|---|---|---|---|
| SWE-agent/mini-swe-agent | PASS | 5 | PASS | 5 | **yes** |
| he-yufeng/CoreCoder | PASS | 3 | PASS | 3 | **yes** |
| HKUDS/nanobot | PASS | 5 | PASS | 5 | **yes** |

Provenance field matches in every bundle:
- mini-swe-agent: `SYSTEM_NATIVE` both locally and in GHA
- CoreCoder: `SYSTEM_STATE_EXPORTED_BY_HARNESS` both locally and in GHA
- nanobot: `SYSTEM_NATIVE` both locally and in GHA

The same Article 12(1) engine produces the same verdict in
both environments. No reproducibility defect.

## Artifact uploads

Both compliance-result.json and the evidence/ directory uploaded
correctly after the slug-safe name fix.

```
article-12-1-SWE-agent-mini-swe-agent-25941c89cfbc  (798 bytes)
article-12-1-evidence-SWE-agent-mini-swe-agent-25941c89cfbc  (665 bytes)
article-12-1-he-yufeng-CoreCoder-a03ef36412e4  (786 bytes)
article-12-1-evidence-he-yufeng-CoreCoder-a03ef36412e4  (536 bytes)
article-12-1-HKUDS-nanobot-4d204ba077a8  (775 bytes)
article-12-1-evidence-HKUDS-nanobot-4d204ba077a8  (590 bytes)
```

## Environment-specific differences discovered

1. **GHA expression parser does NOT support `replace()`** or `//` style
   string replacement. The fix is to compute the slug-safe name in
   a pre-step (`tr '/' '-'` + `cut -c1-12`) and reference
   `${{ steps.slug.outputs.* }}` in the artifact name. Documented
   in the workflow as `Compute slug-safe artifact name` step.
2. **GHA upload-artifact does not permit `/` in artifact names** even
   inside `${{ ... }}` expression output. Same fix.
3. **Node 20 deprecated warning** on every step that uses an
   action — informational only, not blocking.
4. **GHA Python is 3.12.14**, local sandbox is 3.14. Both runtimes
   work because the engine only uses the standard library at the
   top; third-party packages are pulled in by `pip install -e .`
   of each target.
5. **GHA duration is slightly longer** than local for each target
   (38s vs 25s, 11s vs 8s, 23s vs 19s) — expected because the
   runner has to clone both repos and install pip dependencies
   from scratch.

## Verdict

The Article 12(1) engine works reproducibly in GitHub Actions:

- 3/3 required targets PASS
- Local and GHA results match exactly (status, event count, provenance)
- Artifacts upload correctly
- Step summary table renders correctly on the run page
- Workflow file is structurally valid

Stop.