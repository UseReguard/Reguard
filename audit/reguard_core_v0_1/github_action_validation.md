# Reguard Core v0.1 — GitHub Action Validation

**Date:** 2026-08-30
**Action file:** `action.yml` (composite)
**Test environment:** local action invocation via
`tests/cli/test_cli.py` plus manual inspection of `action.yml`
semantics

---

## 1. Action contract

`action.yml` declares:

### Inputs

| Input | Required | Default | Purpose |
|---|---|---|---|
| `config` | no | `""` | Path to a `reguard.yml` (overrides repo-local) |
| `requirement` | no | `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING` | Requirement ID |
| `fail-on` | no | `FAIL,ERROR` | CI failure policy (CI-side only) |
| `output-dir` | no | `.reguard/results` | Result artefacts directory |
| `python-version` | no | `3.12` | Python version |
| `install-command` | no | `pip install -e .[yaml]` | Override install |

### Outputs

| Output | Purpose |
|---|---|
| `status` | Engine status (PASS / FAIL / UNKNOWN / UNSUPPORTED / ERROR) |
| `requirement-id` | Requirement ID tested |
| `requirement-version` | Requirement contract version |
| `result-json` | Path to `result.json` |
| `summary-file` | Path to `summary.md` |
| `repo-sha` | Resolved repository SHA |
| `missing-capability` | Missing capability if UNSUPPORTED |

### Steps

1. Set up Python (3.12)
2. Install Reguard Core
3. Resolve repository SHA via `git rev-parse HEAD`
4. Run `reguard check` with provider keys explicitly cleared
5. Apply CI failure policy (`fail-on`) as a separate step
6. Write GitHub step summary
7. Annotate the run with one annotation per requirement
8. Expose outputs

## 2. Failure policy

Default:

```text
FAIL        → fail job
ERROR       → fail job
UNKNOWN     → warning
UNSUPPORTED → warning
PASS        → success
```

Configurable via `with: fail-on: <csv>`. Strict mode:

```yaml
fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED
```

The Action does NOT change the engine's verdict. The engine
reports what it observed; `fail-on` is purely CI policy.

## 3. Step summary shape

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
- ✅ **AT_LEAST_ONE_EVENT** — observed 4 non-error event(s) out of 4 total
- ✅ **RECORDING_CATEGORY_FRAMEWORK_PERSISTS** — category=B; framework_persists_durably=True
- ✅ **STEP_OR_TOOL_KIND_PRESENT** — observed 4 eligible event(s)

## Scope

This is a deterministic technical-control result.
It does not establish overall EU AI Act compliance.
```

## 4. Annotations

The action emits ONE workflow command per requirement:

- `PASS` → `::notice::Reguard PASS for <requirement-id>`
- `UNKNOWN` or `UNSUPPORTED` → `::warning::Reguard <status> for <requirement-id> — <reason>`
- `FAIL` or `ERROR` → `::error::Reguard <status> for <requirement-id> — <reason>`

No event-level flooding.

## 5. No-provider-key verification

The action explicitly clears the following environment variables
from the harness environment before invoking `reguard check`:

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

`GITHUB_TOKEN` is NOT auto-exported; the harness inherits
whatever GitHub Actions exposes to the workflow by default,
but the integration layer's `validate_env` enforces the
forbidden-env allow-list, so any leaked key still causes the
run to refuse with `ERROR`.

## 6. Dogfood workflow (planned)

A planned `.github/workflows/reguard-dogfood.yml` will run
the action against `examples/minimal-agent` on every push:

```yaml
name: reguard-dogfood
on:
  push:
    paths:
      - 'action.yml'
      - 'src/compliance/**'
      - 'src/compliance/cli/**'
      - 'examples/minimal-agent/**'

jobs:
  dogfood:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./
        with:
          config: examples/minimal-agent/reguard.yml
          fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED
```

This catches regressions in `action.yml`, the CLI, the
recipe, and the packaging.

— end of action validation —
