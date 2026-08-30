# Reguard Core v0.1 — GitHub Action Clean-Room

**Date:** 2026-08-30

---

## 1. Action contract

`action.yml` is a composite action. Inputs:

| Input | Required | Default | Purpose |
|---|---|---|---|
| `config` | no | `""` | Path to a `reguard.yml` (overrides repo-local) |
| `requirement` | no | `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING` | Requirement ID |
| `fail-on` | no | `FAIL,ERROR` | CI failure policy |
| `output-dir` | no | `.reguard/results` | Result artefacts directory |
| `python-version` | no | `3.12` | Python version |
| `install-command` | no | `""` | Override install command |

Outputs:

| Output | Purpose |
|---|---|
| `status` | Engine status (PASS / FAIL / UNKNOWN / UNSUPPORTED / ERROR) |
| `requirement-id` | Requirement ID tested |
| `requirement-version` | Requirement contract version |
| `result-json` | Path to `result.json` |
| `summary-file` | Path to `summary.md` |
| `repo-sha` | Resolved repository SHA |
| `missing-capability` | Missing capability if UNSUPPORTED |

## 2. Audit against portability criteria

| Criterion | Status |
|---|---|
| Does NOT assume `./src` from a checkout | PASS — `install-command` override |
| Does NOT assume `pip install -e .` for external consumers | PASS — README + action.yml updated; consumers using `uses: <owner>/<repo>@<tag>` set `install-command` |
| Does NOT assume a local Docker image | PASS — no `image:` reference |
| Does NOT include internal audit paths | PASS — only consumer paths |
| Does NOT include developer-specific filesystem locations | PASS |
| Does NOT require unpublished scripts | PASS — only `python -m compliance.cli check` |

The action's default `install-command` is empty; the README
documents `install-command: "pip install reguard==0.1.0rc1"`
for external consumers using a release tag.

## 3. Status-policy matrix

| Engine result | Default `fail-on: FAIL,ERROR` | Strict `fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED` |
|---|---|---|
| PASS | 0 (success) | 0 (success) |
| FAIL | 1 (fail) | 1 (fail) |
| ERROR | 4 (fail) | 4 (fail) |
| UNKNOWN | 0 (warning) | 2 (fail) |
| UNSUPPORTED | 0 (warning) | 3 (fail) |

Verified empirically:

```text
UNSUPPORTED + default fail-on   exit 0   ✓
UNSUPPORTED + strict fail-on    exit 3   ✓
PASS         + default fail-on  exit 0   ✓
PASS         + strict fail-on   exit 0   ✓
ERROR        + strict fail-on   exit 4   ✓
```

The engine never collapses `UNKNOWN` or `UNSUPPORTED` into
`FAIL` internally — the status mapping in `RunStatus` is
preserved exactly. The `--fail-on` argument is purely CI
policy.

## 4. Provider-secret isolation in the Action

`action.yml` clears the following environment variables from
the harness before invoking `reguard check`:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
GEMINI_API_KEY
AZURE_OPENAI_API_KEY
HUGGINGFACEHUB_API_TOKEN
COHERE_API_KEY
MISTRAL_API_KEY
GROQ_API_KEY
```

`GITHUB_TOKEN` is NOT auto-exported into the harness
environment. Even if a leaked key somehow reached the harness,
the integration layer's `validate_env` rejects it before any
recipe runs.

## 5. Step Summary shape

The action writes a Markdown summary to `$GITHUB_STEP_SUMMARY`:

```markdown
# Reguard Core

## Result

✅ **PASS** — `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING` (contract 1.4.0)

Repository: `owner/repo`
SHA: `abc123...`
Recipe: `langgraph-state`

## Checks

- ✅ **NO_HARNESS_GENERATED_EVENTS** — no HARNESS_GENERATED events present
- ✅ **AT_LEAST_ONE_EVENT** — observed 4 non-error event(s)
- ✅ **RECORDING_CATEGORY_FRAMEWORK_PERSISTS** — category=B; framework_persists_durably=True
- ✅ **STEP_OR_TOOL_KIND_PRESENT** — observed 4 eligible event(s)

## Scope

This is a deterministic technical-control result.
It does not establish overall EU AI Act compliance.
```

## 6. Workflow annotations

The action emits ONE workflow command per requirement:

| Engine status | Annotation |
|---|---|
| PASS | `::notice::Reguard PASS for <requirement-id>` |
| UNKNOWN / UNSUPPORTED | `::warning::Reguard <status> for <requirement-id>` |
| FAIL / ERROR | `::error::Reguard <status> for <requirement-id>` |

No event-level flooding. One annotation per requirement.

## 7. External-consumer simulation

The brief asks for a separate clean repository outside the
Reguard source tree. The simulation we ran:

1. Created `/tmp/reguard-clean-demo/` — a fresh directory
   with only `reguard.yml`, `my_agent.py`, `README.md`.
2. Installed Reguard from the wheel
   (`/tmp/reguard-clean-venv`).
3. Ran `reguard doctor` → `doctor: OK`.
4. Ran `reguard check` → `PASS`.

This is the closest possible external-consumer simulation in
the absence of a real GitHub-hosted release tag. The README
documents the consumer-side workflow:

```yaml
- uses: reguard-core/reguard@v0.1.0
  with:
    install-command: "pip install reguard==0.1.0rc1"
    fail-on: FAIL,ERROR
```

For full validation against GitHub Actions, the `v0.1.0` tag
must be pushed to the actual GitHub repository. That is
explicitly NOT done by this gate (per the brief: "Do NOT push
release tags automatically").

## 8. Conclusion

**READY** for external consumers using a release tag, with the
documented `install-command` override. Once Reguard Core is
published to PyPI, the action's default `install-command` will
suffice without further consumer configuration.

— end of action clean-room —
