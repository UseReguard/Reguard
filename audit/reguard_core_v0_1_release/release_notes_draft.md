# Reguard Core v0.1 — Release Notes Draft

**Release:** Reguard Core v0.1.0rc1
**Date:** 2026-08-30
**Status:** Release candidate

---

## What is Reguard Core?

Reguard Core is an open-source, local-first CLI and GitHub
Action for deterministic technical-control checks against
AI-agent repositories. It does **not** certify legal
compliance. It tests one technical property at a time and
reports what it observed.

## What v0.1 does

- **`reguard` CLI** with subcommands `init`, `doctor`, `check`,
  `explain`, `list`.
- **Config-driven integration layer**: an `ExecutionRecipe`,
  `ObserverSet`, and `Normalizer` per execution family. No
  per-repository Python adapter required for supported
  integrations.
- **One pilot execution family**: `langgraph-state` (covers
  `langchain-ai/langchain`, `langchain-ai/langgraph`,
  `bytedance/deer-flow`).
- **Composite GitHub Action** with configurable inputs, outputs,
  CI failure policy, and step summary.
- **Deterministic Article 12(1) v1.4.0** technical-control
  check (frozen).
- **Five frozen legacy adapters** preserved verbatim:
  `mini-swe-agent`, `gptme`, `nanobot`, `CoreCoder`,
  `PocketFlow`.
- **Result artefacts** under `.reguard/results/<run-id>/`:
  `result.json`, `evidence.json`, `summary.md`.

## What v0.1 does NOT do

- Does **not** certify EU AI Act compliance.
- Does **not** call any LLM provider.
- Does **not** require an account, login, or hosted service.
- Does **not** send telemetry, analytics, or crash reports.
- Does **not** modify the target repository.
- Does **not** auto-detect framework family.
- Does **not** implement Article 12(2).
- Does **not** implement every legal requirement.

## Security model

Reguard Core runs locally and does not upload evidence to
Reguard. The integration layer enforces a forbidden
environment-variable allow-list (any `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, etc. in the harness environment causes
the run to refuse with `ERROR`). The GitHub Action explicitly
clears provider keys before invoking `reguard check`.

Target repositories are treated as untrusted. The v0.1 default
invocation driver is `subprocess`; an `OCI_CONTAINER` driver
is recognized but its public OCI image is not yet distributed
in v0.1.

See `SECURITY.md` for the full security model and its known
limitations.

## Supported integrations

| Repository | Recipe |
|---|---|
| `langchain-ai/langchain` | `langgraph-state` |
| `langchain-ai/langgraph` | `langgraph-state` |
| `bytedance/deer-flow` | `langgraph-state` |

Plus any repository that ships a `reguard.yml` selecting a
supported recipe.

## Install

```bash
pip install reguard==0.1.0rc1
reguard --version
```

## 30-second quickstart

```bash
pip install reguard==0.1.0rc1
git clone https://github.com/Reguard-Core/reguard-core
cd reguard-core/examples/minimal-agent
reguard doctor --repo-path .
reguard check  --repo-path .
```

## GitHub Action

```yaml
- uses: reguard-core/reguard@v0.1.0
  with:
    install-command: "pip install reguard==0.1.0rc1"
    fail-on: FAIL,ERROR
```

## Limitations

- Only Family A (LangGraph-state) is implemented in v0.1.
- Public OCI runtime image is not yet published.
- PyPI publication is not yet performed.
- The subprocess invocation driver does not isolate factory
  calls from the harness process. Use the OCI container
  driver for untrusted code.

## Roadmap

The v0.2+ roadmap (NOT in v0.1):

- Additional execution families (B–H)
- Public OCI runtime image
- PyPI publication
- Action dogfood workflow on every push
- Result schema version 2 (with deprecation policy)
- More requirements (each evaluated individually for
  deterministic runtime testability)

## License

AGPL-3.0-only.

— end of release notes draft —
