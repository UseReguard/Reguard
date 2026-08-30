# Integrations

Reguard supports three integration paths in v0.1:

1. **Built-in** — the repository is already known to Reguard
2. **Repository-local** — the repository ships a `reguard.yml`
3. **Unsupported** — no compatible integration; structured
   `UNSUPPORTED` result is returned

## Built-in

If a repository's full name (e.g. `langchain-ai/langchain`)
matches a built-in manifest shipped with Reguard, no further
configuration is required:

```bash
cd langchain
reguard check --repo-path .
```

Built-in manifests in v0.1:

| Repository | Recipe |
|---|---|
| `langchain-ai/langchain` | `langgraph-state` |
| `langchain-ai/langgraph` | `langgraph-state` |
| `bytedance/deer-flow` | `langgraph-state` |

## Repository-local

If you want Reguard to integrate with a repository Reguard does
not ship a manifest for, drop a `reguard.yml` at the
repository root:

```bash
reguard init
```

Edit the generated file to point `entrypoint.target` at the
factory the recipe should call, then run:

```bash
reguard check --repo-path .
```

The smallest possible reguard.yml selects the
`langgraph-state` recipe and a single observer:

```yaml
schema_version: 1

integration:
  recipe: langgraph-state
  recipe_version: 1.0.0
  package_root: .

  entrypoint:
    target: my_agent:build_graph
    mode: sync

  model:
    strategy: deterministic_stub

  observers:
    - langgraph-state.callback-observer

  normalizer:
    id: langgraph-state.canonical-normalizer

scenarios:
  - compliance.article12_1.simple
```

## Unsupported

If neither a built-in manifest nor a `reguard.yml` matches,
`reguard check` returns `UNSUPPORTED` with `missing_capability:
NO_EXECUTION_RECIPE`. The Action surfaces this as a warning
annotation; the job does not fail by default.

To extend support, add a `reguard.yml` (option 2) or open a
PR adding a built-in manifest under `integrations/`.

## Resolution order

`reguard check` resolves a target repository in this order:

1. `--config <path>` (explicit override)
2. `<repo_path>/reguard.yml`
3. Built-in integration manifest
4. Legacy `RepoAdapter` (frozen-five adapters only)
5. UNSUPPORTED

The legacy adapter fallback exists so the five frozen
Article 12(1) adapters (`mini-swe-agent`, `gptme`, `nanobot`,
`CoreCoder`, `PocketFlow`) continue to work via the existing
`scripts/compliance-check.py` path. New repositories should
NOT use this fallback; they should ship a `reguard.yml`.

## What Reguard does NOT do (yet)

- **No framework auto-detection.** Reguard does not read your
  `pyproject.toml` or `requirements.txt` to decide which family
  you are. You declare your family explicitly in `reguard.yml`.
- **No provider auto-detection.** Reguard does not detect that
  you have `OPENAI_API_KEY` set and switch to a real model.
  Recipes must declare `model.strategy: deterministic_stub` in
  v0.1; any other value is rejected.
- **No legacy-adapter auto-coercion.** If a repository has a
  legacy adapter but no `reguard.yml`, `reguard check` returns
  `UNSUPPORTED` and tells you to use `scripts/compliance-check.py`.

These are deliberate. They keep the v0.1 product surface
small, predictable, and free of hidden behaviour.
