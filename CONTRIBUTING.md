# Contributing

Reguard Core welcomes contributions. The architectural
separation is:

> **Observers observe. Normalizers normalize. Requirements decide.**

## Repository layout

```
src/compliance/
  integrations/         config-driven integration layer
    recipe.py           ExecutionRecipe + registry
    observer.py         ObserverSet + registry
    normalizer.py       Normalizer + registry
    integration.py      IntegrationResolver
    config.py           reguard.yml loader + validator
    families/
      langgraph_state/  Family A (langchain / langgraph / deer-flow)
  cli/                  top-level CLI
  pipeline/             evidence + result types (frozen)
  adapters/             legacy per-repo adapters (frozen)
  requirements/         deterministic RequirementTests
  corpus_runner/        corpus orchestration (out of scope for v0.1)
docs/                   documentation
examples/               demo fixtures
action.yml              composite GitHub Action
```

## How to add a new recipe

1. Subclass `ExecutionRecipe` (in
   `src/compliance/integrations/recipe.py`).
2. Set `recipe_id`, `recipe_version`, `supported_scenarios`.
3. Implement `resolve(config)` and `run(resolution, scenario)`.
4. Register the recipe via `register_recipe(MyRecipe())`.
5. Add a unit test in `tests/integrations/`.

Recipes MUST NOT:

- Return PASS / FAIL.
- Reference Article numbers.
- Decide provenance eligibility.
- Invent events.

## How to add a new observer

1. Subclass `ObserverSet` (in
   `src/compliance/integrations/observer.py`).
2. Set `observer_id`, `observer_version`.
3. Implement `prepare`, `observe`, `finalize`.
4. Register via `register_observer(MyObserver())`.

Observers MUST NOT:

- Return PASS / FAIL.
- Reference Article numbers.
- Decide A / B / C / D / E provenance categories.
- Invent events.

## How to add a new normalizer

1. Subclass `Normalizer` (in
   `src/compliance/integrations/normalizer.py`).
2. Set `normalizer_id`, `normalizer_version`.
3. Implement `normalize(observations, *, recipe_id, recipe_version)`.
4. Register via `register_normalizer(MyNormalizer())`.

Normalizers MUST NOT:

- Return PASS / FAIL.
- Reference Article numbers.
- Invent events.

Normalizers translate a free-form `producer` string on each
`NativeObservation` into the canonical EvidenceOrigin value
(SYSTEM_NATIVE / SYSTEM_STATE_EXPORTED_BY_HARNESS /
HARNESS_GENERATED). The RequirementTest decides whether the
provenance is eligible for PASS; the normalizer only translates
it.

## How to add a new built-in integration manifest

Drop a YAML file at `integrations/<owner-repo>.yml`:

```yaml
schema_version: 1

integration:
  recipe: <recipe-id>
  recipe_version: "<version>"
  package_root: .
  entrypoint:
    target: <module:callable>
    mode: sync
  model:
    strategy: deterministic_stub
  observers:
    - <observer-id>
  normalizer:
    id: <normalizer-id>

scenarios:
  - compliance.article12_1.simple
```

Add the manifest to
`src/compliance/integrations/integrations_builtin.py` so the
CLI can list it.

## How to add a new requirement

This is out of scope for v0.1. The frozen requirement is
Article 12(1) v1.4.0. New requirements must:

1. Be evaluated individually for deterministic runtime
   testability.
2. Preserve the A/B/C/D/E provenance taxonomy if applicable.
3. Preserve the SYSTEM_NATIVE / SYSTEM_STATE_EXPORTED_BY_HARNESS
   / HARNESS_GENERATED boundary.
4. NOT collapse UNKNOWN / UNSUPPORTED into FAIL.

## Testing

```bash
pytest
```

The frozen-five regression lives in `tests/pipeline/`. New
integrations must add unit tests under `tests/integrations/`
and CLI tests under `tests/cli/`.

## Code of conduct

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
