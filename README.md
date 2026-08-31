# Reguard

> **Open-source runtime assurance for AI agents.**

Reguard runs deterministic technical-control checks against AI-agent systems and produces inspectable runtime evidence.

**No LLM judge. No source-code guessing. No telemetry.**

`CLI` · `GitHub Action` · `Local-first` · `AGPL-3.0`

---

## About

Reguard turns compliance-relevant technical requirements into deterministic runtime tests for AI-agent systems.

Reguard Core is implemented in Python. **v0.1 currently supports Python-based AI-agent systems and explicitly supported execution recipes.** The evidence model and requirement contracts are designed to be runtime-agnostic, but Reguard does not yet claim universal language or backend support.

Reguard evaluates observable properties of the **agent execution system**, not intrinsic properties of the foundation model.

```text
requirement
→ controlled execution
→ runtime evidence
→ deterministic assertion
→ PASS / FAIL / UNKNOWN / UNSUPPORTED / ERROR
```

AI agents are increasingly subject to requirements around logging, human oversight, resilience, cybersecurity, and transparency. Reguard focuses on requirements that can be reduced to deterministic observations of runtime behaviour.

It does **not** certify legal compliance.

### Support and licensing

**Runtime support**

- Reguard Core itself is implemented in Python.
- v0.1 currently targets supported Python-based AI-agent systems.
- Built-in integrations and compatible `reguard.yml` execution recipes define the currently supported execution surface.
- The underlying evidence and requirement architecture is designed to support additional languages and backends in the future.
- Reguard does **not** currently claim universal support for every AI-agent framework, language, or backend.

**Open source**

Reguard Core is open source under **AGPL-3.0-only**.

Commercial use is permitted. The AGPL is a strong copyleft license and carries source-sharing obligations in circumstances covered by the license.

See [LICENSE](LICENSE) for the full license terms.

### Article 12(1) — what Reguard actually tests

Reguard tests whether, during a controlled invocation, the **agent execution system itself** automatically produces a recoverable runtime record of actual agent activity.

A `PASS` is a deterministic technical-control result. It does **not** establish overall compliance with Article 12(1), Article 12, or the EU AI Act.

For the full technical contract, see:

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

Install the current release candidate:

```bash
pip install reguard==0.1.0rc2
```

Then:

```bash
reguard doctor
reguard check
```

Try the deterministic example:

```bash
git clone https://github.com/UseReguard/Reguard
cd Reguard/examples/minimal-agent

reguard doctor --repo-path .
reguard check --repo-path .
```

Expected:

```text
PASS — AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
```

No model-provider API key is required for the supported deterministic scenarios.

---

## GitHub Actions

Run Reguard on every pull request and push:

```yaml
name: Reguard

on:
  pull_request:
  push:

jobs:
  reguard:
    permissions:
      contents: read

    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: UseReguard/Reguard@v0.1.0-rc.2
        with:
          reguard-version: 0.1.0rc2
          fail-on: FAIL,ERROR
```

Reguard writes a human-readable GitHub summary and structured evidence for the run.

Default CI behaviour:

| Result | CI |
| --- | --- |
| `PASS` | ✅ Pass |
| `FAIL` | ❌ Fail |
| `ERROR` | ❌ Fail |
| `UNKNOWN` | ⚠️ Warn |
| `UNSUPPORTED` | ⚠️ Warn |

---

## Example

```text
Reguard Core

Technical control
  AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING
  Contract v1.4.0

Result
  PASS

Evidence
  4 events
  2 framework artifacts
```

Every run also produces structured artifacts:

```text
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

```bash
reguard init
```

See [docs/integrations.md](docs/integrations.md).

Support for an integration means Reguard has an execution and observation path for that integration. It does not imply that every project built with the framework will automatically be executable without configuration.

---

## How it works

Reguard separates framework integration from compliance decisions:

```text
Agent system
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

Framework adapters and execution recipes collect evidence. They do not declare a system compliant.

Requirement tests operate on normalized runtime evidence.

---

## Why deterministic?

Reguard does not ask an AI model:

> "Does this look compliant?"

Instead, each check has a versioned technical contract.

For example, the current Article 12(1) check asks whether, during a controlled invocation, the agent execution system itself automatically produces a recoverable record of actual runtime activity.

The evidence either satisfies the contract, contradicts it, cannot establish it, or cannot currently be collected.

That makes results:

- reproducible;
- inspectable;
- versioned;
- CI-friendly;
- independent of an LLM acting as the compliance judge.

---

## Result semantics

| Status | Meaning |
| --- | --- |
| `PASS` | ✅ Technical contract satisfied |
| `FAIL` | ❌ Evidence contradicts the contract |
| `UNKNOWN` | ❔ Required fact could not be established |
| `UNSUPPORTED` | ⚠️ Reguard cannot currently execute or observe the system |
| `ERROR` | 💥 Execution or infrastructure failed |

These states are deliberately kept separate.

A `PASS` means the specific versioned technical contract was satisfied during the controlled evaluation. It is not a legal-compliance certification.

---

## Security

Reguard treats target repositories as untrusted.

- ✅ Local-first
- ✅ No Reguard telemetry
- ✅ No evidence upload
- ✅ Provider keys excluded from supported deterministic target execution
- ✅ Controlled runtime execution
- ✅ Isolated result artifacts
- ✅ Deterministic model stubs for supported scenarios

See [SECURITY.md](SECURITY.md).

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
- ✅ Frozen regression corpus
- ✅ Public OCI runtime
- ✅ No telemetry
- ✅ No cloud dependency
- ✅ No LLM judge

### Next

- ⬜ More EU AI Act runtime checks
- ⬜ More execution families
- ⬜ Broader framework support
- ⬜ Better zero-config onboarding

### Longer term

```text
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

Reguard verifies compliance-relevant properties of the **agent execution system**, not intrinsic properties of the foundation model.

A `PASS` does not mean that a system is legally compliant with the EU AI Act.

Reguard does not determine:

- whether the EU AI Act applies;
- whether a system is high-risk;
- organizational compliance;
- conformity assessment;
- governance obligations;
- documentation obligations;
- intrinsic foundation-model compliance;
- overall legal compliance.

Current v0.1 support is also intentionally narrower than the architecture:

- Reguard Core is implemented in Python;
- supported targets are currently Python-based AI-agent systems with supported integrations or compatible execution recipes;
- universal language/backend support is not currently claimed.

---

## Contributing

Contributions are welcome.

See [CONTRIBUTING.md](CONTRIBUTING.md).

> **Observers observe. Normalizers normalize. Requirements decide.**

---

## License

Reguard Core is licensed under **AGPL-3.0-only**.

It is open-source software. Commercial use is permitted, subject to the terms and obligations of the AGPL.

See [LICENSE](LICENSE).
