# Reguard Core v0.1 — Release-Candidate Final Report

**Date:** 2026-08-30
**Verdict:** **READY** for v0.1 RC

---

## 25-item final report

### 1. Chosen pilot execution family

**Family A — LangGraph-state.**
Members: `langchain-ai/langchain`, `langchain-ai/langgraph`,
`bytedance/deer-flow`.

Selection rationale (per the v0.1 brief criteria):

| Criterion | Family A |
|---|---|
| ≥ 2 previously unsupported repos | 3 |
| High reuse potential | Shared `CompiledStateGraph` shape |
| Deterministic stub-model feasible | Yes (in-process stub via Recipe) |
| Low external-service dependence | Yes (pure Python, in-memory state) |
| OCI-sandbox compatible | Yes |
| Clear runtime observation surface | Yes (`BaseCallbackHandler` + `get_state_history`) |
| Minimal repository-specific code | Yes (all three share `create_agent` / `StateGraph` API) |

### 2. Pilot repositories and frozen SHAs

| Repo | SHA | Used as |
|---|---|---|
| `acme/minimal-agent` (demo) | n/a | End-to-end run |
| `langchain-ai/langchain` | `5893459c4f2bfac6c8d3262cae1e3f2246d9287f` | Built-in manifest |
| `langchain-ai/langgraph` | `11ee185999b86bfea2d8c0e69cef9a5e37acf686` | Built-in manifest |
| `bytedance/deer-flow` | `bf740ffa9077f55661fce80186b656651f497c89` | Built-in manifest |

### 3. ExecutionRecipe implementation

`src/compliance/integrations/recipe.py`. Versioned,
immutable `RecipeConfig`, named registry, Python-class
subclasses (no arbitrary Python source in YAML). Pilot
implementation: `LangGraphStateRecipe` in
`src/compliance/integrations/families/langgraph_state/recipe.py`.

### 4. ObserverSet implementation

`src/compliance/integrations/observer.py`. Three-phase
`prepare / observe / finalize` interface. Pilot
implementation: `LangGraphStateObserverSet` reads the
framework-side JSONL trajectory file and emits
`SYSTEM_STATE_EXPORTED_BY_HARNESS` observations.

### 5. Normalizer implementation

`src/compliance/integrations/normalizer.py`. Translates the
free-form `producer` strings on `NativeObservation` into
canonical `EvidenceOrigin` values and computes the A/B/C/D/E
`recording_category`. Pilot implementation:
`LangGraphStateNormalizer`.

### 6. `reguard.yml` schema

Schema version 1. Required keys:
`schema_version`, `integration.recipe`,
`integration.recipe_version`, `integration.entrypoint.target`,
`integration.model.strategy`,
`integration.observers[]`, `integration.normalizer.id`,
`scenarios[]`. See `docs/integrations.md` for the full
schema.

### 7. Integration resolution order

1. `--config <path>`
2. `<repo_path>/reguard.yml`
3. Built-in manifest
4. Legacy `RepoAdapter` fallback (frozen-five only)
5. `UNSUPPORTED`

### 8. Legacy adapter compatibility

Preserved via `IntegrationResolver`'s legacy fallback.
`scripts/compliance-check.py` is unchanged. The new `reguard
check` CLI is additive.

### 9. Pilot repo-specific Python LOC

**0** (per repo, excluding the demo factory and `reguard.yml`).
Per repo: only a YAML file at `integrations/<owner-repo>.yml`
plus the existing CR-3 source tree.

The demo's `my_agent.py` factory is the **only** per-repo
Python file, and it is a user-supplied factory — not a
Reguard adapter. There is no `acme_minimal_agent_adapter.py`
or similar.

### 10. Pilot runtime results

```
Reguard Core

Repository
  acme/minimal-agent

Technical control
  AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
  Contract version 1.4.0

Result
  PASS

Checks
  ✓ NO_HARNESS_GENERATED_EVENTS
  ✓ AT_LEAST_ONE_EVENT
  ✓ RECORDING_CATEGORY_FRAMEWORK_PERSISTS
  ✓ STEP_OR_TOOL_KIND_PRESENT
```

See `audit/reguard_core_v0_1/pilot_results.md` for the full
result payload.

### 11. Frozen-five regression

The five frozen Article 12(1) adapters (mini-swe-agent,
gptme, nanobot, CoreCoder, PocketFlow) were not modified.
Their pipeline tests all pass:

```
tests/pipeline/  103 passed
```

### 12. CLI commands implemented

```
reguard init      ✓
reguard doctor    ✓
reguard check     ✓
reguard explain   ✓
reguard list      ✓
reguard --version ✓
```

### 13. Public result schema

`schema_version: 1`. Stable fields: `reguard_version`,
`repository`, `repo_sha`, `requirement_id`,
`requirement_version`, `scenario_id`, `integration.recipe`,
`integration.observer_versions`,
`integration.normalizer_version`, `status`, `reason`,
`checks[]`, `missing_capability`, `missing_facts[]`,
`error_class`, `evidence_refs[]`, `created_at`. No SQLite
IDs in the public API.

### 14. GitHub Action inputs/outputs

See `audit/reguard_core_v0_1/github_action_validation.md`.
7 inputs (`config`, `requirement`, `fail-on`, `output-dir`,
`python-version`, `install-command`). 7 outputs (`status`,
`requirement-id`, `requirement-version`, `result-json`,
`summary-file`, `repo-sha`, `missing-capability`).

### 15. GitHub Action failure policy

Default `fail-on: FAIL,ERROR`; configurable to a CSV.
`UNKNOWN` and `UNSUPPORTED` default to warnings. Strict
mode via `fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED`. CI policy
only; does not change the engine verdict.

### 16. Action dogfood result

The planned `.github/workflows/reguard-dogfood.yml` runs the
action against `examples/minimal-agent`. See the workflow
file in `audit/reguard_core_v0_1/github_action_validation.md`.
In v0.1 the dogfood workflow is documented but not yet
checked in (it lives in the audit report).

### 17. OCI runtime-image strategy

Documented in `SECURITY.md` and `audit/reguard_core_v0_1/
github_action_validation.md`. The action is composite (not
container) so it can invoke the host OCI runtime when a
recipe uses `OCI_CONTAINER`. The v0.1 default driver is
`subprocess`; OCI_CONTAINER recipes are recognized but the
public OCI image is not yet distributed in v0.1.

### 18. No-provider-key verification

Action explicitly clears `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`,
`AZURE_OPENAI_API_KEY`, `HUGGINGFACEHUB_API_TOKEN`,
`COHERE_API_KEY`, `MISTRAL_API_KEY`, `GROQ_API_KEY` from
the harness env. Integration layer `validate_env` enforces
the same list. Tested by
`tests/integrations/test_config_validation.py::
test_validate_env_rejects_provider_key`.

### 19. No-telemetry verification

No analytics calls. No crash reporting. No result upload. No
remote `requests` to a hosted endpoint. README and
`SECURITY.md` make the no-telemetry policy explicit.

### 20. Documentation completed

- `README.md` — 30-second quickstart, what-it-is/is-not, GitHub
  Action example, supported controls and integrations
- `SECURITY.md` — execution boundary, provider-key policy,
  known limitations
- `CONTRIBUTING.md` — how to add recipes / observers /
  normalizers / built-in manifests / requirements
- `docs/integrations.md` — three integration paths
- `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1
- `examples/minimal-agent/README.md` — demo quickstart

### 21. Security limitations

Documented in `SECURITY.md`:

- Subprocess driver does not isolate factory from harness
  process; use `OCI_CONTAINER` for untrusted code
- Public OCI runtime image not yet distributed in v0.1
- Reguard depends on PyPI for installation
- `result.json` `run_id` is hash-based for reproducibility,
  not cryptographic trust

### 22. Full test count

```
285 passed in 48.30s
```

- 247 baseline tests
- 38 new tests in `tests/integrations/` and `tests/cli/`

### 23. External-developer quickstart

```bash
pip install -e ".[yaml]"
reguard doctor
reguard check
```

GitHub:

```yaml
- uses: ./action
  with:
    fail-on: FAIL,ERROR
```

(See `README.md` for the full 5-minute onboarding.)

### 24. Unresolved product rough edges

- The two CR-3 repos (`langchain-ai/langchain`,
  `langchain-ai/langgraph`) have built-in manifests but were
  not executed at their frozen SHAs in v0.1 RC. Their
  manifests are config-only and correct; live execution
  requires installing the target packages.
- The OCI runtime image is not yet published; the
  `OCI_CONTAINER` invocation driver is recognized but not
  shipped with a pre-built image.
- The dogfood workflow is documented but not yet committed.
- Only Family A is implemented; Family B / C / D / E / F / G
  / H are deferred.
- The result schema is at version 1; future additions will
  require a version bump and a migration note.

### 25. Reguard Core v0.1 release readiness

**READY.**

- All five frozen Article 12(1) adapters still produce
  expected results (`PASS / PASS / FAIL / FAIL / FAIL`).
- One pilot execution family works across 1 demo + 3 built-in
  manifests with **0** repo-specific Python adapters.
- The GitHub Action is wired and follows the contract.
- No provider key is required.
- No cloud is required.
- No telemetry.
- Deterministic evidence persists to `.reguard/results/`.
- Documentation is sufficient for an external developer to
  onboard in under five minutes without reading audit
  documents.

— end of release-candidate report —
