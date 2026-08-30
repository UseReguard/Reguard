# Reguard

> **Open-source runtime assurance for AI agents.**

Reguard runs deterministic technical-control checks against AI-agent systems and produces inspectable runtime evidence.

**No LLM judge. No source-code guessing. No telemetry.**

`CLI` · `GitHub Action` · `Local-first` · `AGPL-3.0`

---

## About

AI agents are increasingly subject to requirements around logging, human oversight, resilience, cybersecurity, and transparency.

Reguard turns those requirements into deterministic runtime tests:

```text id="zsh18g">
requirement
→ controlled execution
→ runtime evidence
→ deterministic assertion
→ PASS / FAIL / UNKNOWN / UNSUPPORTED / ERROR
```

Reguard tests technical properties of the **agent execution system**.

It does **not** certify legal compliance.

### Article 12(1) — what Reguard actually tests

Reguard tests whether, during a controlled invocation, the **agent execution system itself** automatically produces a recoverable runtime record of actual agent activity.

A `PASS` is a deterministic technical-control result. It does **not** establish overall compliance with Article 12(1), Article 12, or the EU AI Act.

For the full technical contract — including the four observable checks and the framework-artifact taxonomy — see:

```bash
reguard explain AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
```

---

## EU AI Act coverage

### Available now

- ✅ **Article 12(1)** — Automatic event logging  
  `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING` · v1.4.0

### Runtime checks on the roadmap

- ⬜ **Article 12(2)(a)** — Logging relevant to risks or substantial modification
- ⬜ **Article 12(2)(b)–(c)** — Logging supporting operational and post-market monitoring
- ⬜ **Article 14(4)(d)** — Human override, disregard, reversal, or non-use
- ⬜ **Article 14(4)(e)** — Human intervention, interruption, and safe halt
- ⬜ **Article 15(4)** — Resilience to errors, faults, and inconsistencies
- ⬜ **Article 15(5)** — Agent-runtime cybersecurity
- ⬜ **Article 50(1) + 50(5)** — AI interaction disclosure
- ⬜ **Article 50(2)** — Machine-readable marking of synthetic outputs

The roadmap only includes requirements that appear reducible to deterministic observations of agent-runtime behaviour.

Governance processes, conformity assessment, registration, CE marking, organizational duties, and intrinsic foundation-model properties are outside Reguard Core's current scope.

---

## Getting started

```bash id="m9vbhk"
pip install reguard==0.1.0rc1

reguard doctor
reguard check
```

Try the deterministic example:

```bash id="40bzg4"
git clone https://github.com/UseReguard/Reguard
cd reguard/examples/minimal-agent

reguard doctor --repo-path .
reguard check --repo-path .
```

Expected:

```text id="vn0ttg"
PASS — AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
```

No model API key is required.

---

## GitHub Actions

Run Reguard on every pull request:

```yaml id="i6dm3r"
name: Reguard

on:
  pull_request:
  push:

jobs:
  reguard:
    # Reguard only needs to read the repository contents.
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

Reguard writes a human-readable GitHub summary and structured evidence for the run.

Default CI behaviour:

| Result | CI |
|---|---|
| `PASS` | ✅ Pass |
| `FAIL` | ❌ Fail |
| `ERROR` | ❌ Fail |
| `UNKNOWN` | ⚠️ Warn |
| `UNSUPPORTED` | ⚠️ Warn |

---

## Example

```text id="dhhowh"
Reguard Core

Technical control
  AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
  Contract v1.4.0

Result
  PASS

Checks
  ✓ framework-produced runtime record
  ✓ runtime activity observed
  ✓ recoverable framework state

Evidence
  4 events
  2 framework artifacts
```

Every run also produces:

```text id="kp18ap"
.reguard/
└── results/
    └── <run-id>/
        ├── result.json
        ├── evidence.json
        └── summary.md
```

---

## Current integrations

Built-in config-driven integrations:

- ✅ `langchain-ai/langchain`
- ✅ `langchain-ai/langgraph`
- ✅ `bytedance/deer-flow`

Reguard also supports repositories with their own `reguard.yml` using a compatible execution recipe.

```bash id="05eue0"
reguard init
```

See [`docs/integrations.md`](docs/integrations.md).

---

## How it works

Reguard separates framework integration from compliance decisions:

```text id="1ks3vi"
Agent
  ↓
Execution Recipe
  ↓
Observer
  ↓
Normalizer
  ↓
Evidence
  ↓
Requirement Test
```

**Recipes execute. Observers observe. Normalizers normalize. Requirements decide.**

No framework adapter gets to declare itself compliant.

---

## Why deterministic?

Reguard does not ask an AI model:

> "Does this look compliant?"

Instead, each check has a versioned technical contract.

For example, the current Article 12(1) check asks whether, during a controlled invocation, the agent system itself automatically produces a recoverable record of actual runtime activity.

The evidence either satisfies the contract or it does not.

That makes results:

- reproducible;
- inspectable;
- versioned;
- CI-friendly;
- independent of model-provider API keys.

---

## Result semantics

| Status | Meaning |
|---|---|
| `PASS` | ✅ Technical contract satisfied |
| `FAIL` | ❌ Evidence contradicts the contract |
| `UNKNOWN` | ❔ Required fact could not be established |
| `UNSUPPORTED` | ⚠️ Reguard cannot currently execute/observe the system |
| `ERROR` | 💥 Execution or infrastructure failed |

These states are deliberately kept separate.

---

## Security

Reguard treats target repositories as untrusted.

- ✅ Local-first
- ✅ No Reguard telemetry
- ✅ No evidence upload
- ✅ Provider keys excluded from target execution
- ✅ Controlled runtime execution
- ✅ Isolated result artifacts
- ✅ Deterministic model stubs for supported scenarios

See [`SECURITY.md`](SECURITY.md).

---

## Status

### Reguard Core v0.1

- ✅ Deterministic evidence model
- ✅ Article 12(1) runtime contract
- ✅ CLI
- ✅ GitHub Action
- ✅ Config-driven integrations
- ✅ Structured evidence
- ✅ Reproducible release artifacts
- ✅ 285 automated tests
- ✅ Frozen regression corpus
- ✅ No telemetry
- ✅ No cloud dependency
- ✅ No LLM judge

### Next

- ⬜ More EU AI Act runtime checks
- ⬜ More execution families
- ⬜ Public OCI runtime
- ⬜ Better zero-config onboarding

### Longer term

```text id="wxu61s"
DEFINE
  ↓
VERIFY
  ↓
ENFORCE
  ↓
PROVE
```

---

## Scope

Reguard produces deterministic **technical-control evaluations**.

A `PASS` does not mean that a system is legally compliant with the EU AI Act.

Reguard does not determine:

- whether the AI Act applies;
- whether a system is high-risk;
- organizational compliance;
- conformity assessment;
- governance obligations;
- documentation obligations;
- overall legal compliance.

---

## Contributing

Contributions are welcome.

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

> **Observers observe. Normalizers normalize. Requirements decide.**

---

## License

Reguard is licensed under **AGPL-3.0-only**.

See [`LICENSE`](LICENSE).