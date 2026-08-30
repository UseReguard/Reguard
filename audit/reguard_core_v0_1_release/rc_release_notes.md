# Reguard Core v0.1.0-rc.1 — Release Notes

## Reguard Core v0.1.0-rc.1

Reguard Core is an open-source CLI and GitHub Action that runs
deterministic, evidence-producing technical-control checks against
an AI-agent repository. It does not certify legal compliance.
This is the first public release candidate.

### What ships

- Deterministic runtime checks for one EU AI Act technical control
  (`AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING`, contract v1.4.0).
- Polished top-level CLI: `init`, `doctor`, `check`, `explain`,
  `list`.
- Composite GitHub Action.
- Config-driven integration system: `ExecutionRecipe` +
  `ObserverSet` + `Normalizer` three-abstraction model.
- Built-in integrations: `langchain-ai/langchain`,
  `langchain-ai/langgraph`, `bytedance/deer-flow`.
- Five frozen Article 12(1) v1.4.0 adapters, preserved verbatim
  via the legacy CLI path: mini-swe-agent, gptme, nanobot,
  CoreCoder, PocketFlow.
- Structured per-run artefacts (`result.json`, `evidence.json`,
  `summary.md`) with OCI runtime-image provenance fields.

### Properties

- No LLM judge.
- No provider API key required.
- No telemetry.
- No source-code guessing.
- Local-first; runs entirely on the user's machine or on a
  GitHub Actions runner.
- License: AGPL-3.0-only.

### Known limitations

- One technical control is implemented (Article 12(1) Automatic
  Event Logging). Other Articles (12(2), 14, 15, 50) are on the
  roadmap but NOT implemented.
- One config-driven execution family (`langgraph-state`).
- No framework auto-detection; users opt-in by writing
  `reguard.yml` or relying on a built-in manifest.
- Runtime-image publication is pending; the subprocess driver
  is the v0.1 default and the demo PASSes without OCI.
- Reguard Cloud does not exist; there is no hosted dashboard,
  no Runtime Gate.
- Reguard tests a single technical property at a time. A `PASS`
  is not a legal-compliance certification.

### Install

```bash
pip install reguard==0.1.0rc1
reguard doctor
reguard check
```

### Deterministic example

```bash
git clone https://github.com/UseReguard/Reguard
cd reguard/examples/minimal-agent
reguard check --repo-path .
```

Expected:

```text
PASS — AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING (contract v1.4.0)
```

### GitHub Action

```yaml
name: Reguard
on: [pull_request, push]
jobs:
  reguard:
    permissions:
      contents: read
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: UseReguard/Reguard@v0.1.0-rc.1
        with:
          reguard-version: 0.1.0rc1
          fail-on: FAIL,ERROR
```

### Platform support

- Linux (Ubuntu) and GitHub Actions `ubuntu-latest`.
- Container runtime: Podman or Docker.
- Python 3.12 and 3.14.

### Source SHA / hashes

The exact SHA-256 hashes for this RC's wheel and sdist, plus the
source-tree commit that produced them, are recorded in
`audit/reguard_core_v0_1_release/release_artifact_manifest.json`.

— end of release notes —