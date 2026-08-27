# Reguard

**Deterministic runtime compliance checks for AI agents.**

Reguard converts concrete, machine-observable regulatory
requirements into deterministic runtime tests for AI agent
systems. Each test exercises a real agent system against a
controlled scenario, captures the runtime evidence it produced,
and evaluates a deterministic assertion. The result is a
structured PASS / FAIL / UNKNOWN / UNSUPPORTED / ERROR verdict
attached to a specific Git commit SHA.

Reguard does not certify legal compliance. It tests one
technical property at a time and reports what it observed.

Reguard's core engine in this repository is **open source**
under the **GNU Affero General Public License, version 3
(AGPL-3.0-only)**. Subject to the AGPL terms, anyone may
inspect the source, run the engine, modify it, and
redistribute it in source or compiled form. See
[`LICENSE`](./LICENSE) for the binding text and
[`docs/licensing.md`](./docs/licensing.md) for the
architectural and commercial framing.

**Reguard Cloud** is the planned managed commercial product
layer on top of the engine: hosted execution, GitHub App
integration, multi-tenant accounts, history, alerts, and
reporting. Reguard Cloud is **not yet available**; its
pricing, scope, and license boundary require qualified
legal review and design-partner validation before launch.
See [`docs/product-model.md`](./docs/product-model.md) and
[`docs/design-partner-plan.md`](./docs/design-partner-plan.md).

The product name `Reguard` is a **provisional working name**
pending trademark and naming-collision review. It must not
be treated as a final brand until that review is complete.

## Why Reguard

Most "AI governance" tooling today decides compliance by reading
the source code, parsing README claims, or asking an LLM.
Reguard takes a different position:

> We verify compliance-relevant properties of the agent
> execution system, not intrinsic properties of the foundation
> model.

The thing being tested is the agent runtime itself: its logging
behavior, its oversight hooks, its fault handling, its
interaction disclosure. Compliance verdicts are derived from
observed runtime behavior, not from textual analysis.

## How it works

```
controlled execution
    -> observable runtime evidence
        -> deterministic assertion
            -> structured result
```

1. The engine checks out the target repository at an exact Git
   commit SHA.
2. A per-framework adapter installs the agent system into a
   fresh, isolated runtime and exercises it with a fixed
   deterministic scenario.
3. The runtime produces evidence (events, trajectories, state
   exports). Each event is tagged with a provenance label
   describing who actually created it.
4. A registered `RequirementTest` evaluates the evidence
   against the technical assertion that corresponds to a legal
   obligation.
5. The result, evidence, and all version metadata are recorded
   and can be re-evaluated deterministically.

## Current status

The first production requirement is implemented and verified:

- **EU AI Act Article 12(1)** — Automatic recording of events
  over the lifetime of the system.
  Requirement ID: `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING`.

The Article 12(1) engine has been verified:

- locally
- in GitHub Actions
- against exact pinned Git SHAs
- using deterministic model stubs (no public LLM API is called)
- with per-event evidence provenance tracking
- with local and CI results that match exactly

The engine was tested against three pinned Python agent
repositories at the following SHAs:

| Repository | SHA |
|---|---|
| SWE-agent/mini-swe-agent | `25941c89cfbc91eb40b3f8756348c91d9977d57e` |
| he-yufeng/CoreCoder | `a03ef36412e432fc49d972d4007b36ce44ec5d9a` |
| HKUDS/nanobot | `4d204ba077a86dc42225c16f8f90032013ea1969` |

Each repository passed the implemented Article 12(1) runtime
test at the tested SHA under the tested scenario. This does not
imply that any of these repositories is generally compliant
with the EU AI Act, with Article 12 as a whole, or with any
other regulation.

## Example: EU AI Act Article 12(1)

Legal requirement (Article 12(1)):
> High-risk AI systems shall have technical capability to
> automatically record events ("logs") over the lifetime of the
> system.

Operationalisation in Reguard:

- **Legal requirement**: the system technically allows automatic
  event recording over its lifetime.
- **Controlled test**: execute a fixed, deterministic agent
  scenario.
- **Evidence**: events recorded by the agent runtime during
  execution.
- **Assertion**: at least one observable step/tool event and
  one completion event were produced by the system itself,
  not fabricated by the harness.
- **Result**: `PASS` / `FAIL` / `UNKNOWN` / `UNSUPPORTED` /
  `ERROR`.

This is a test of one technical property. It is not a
certification of full Article 12 or of the AI Act as a whole.

## Architecture

The engine is split into five layers:

```
src/compliance/
  legal/       canonical law ingestion and parsing
  corpus/      discovery and curated agent-repository corpus
  adapters/    deterministic instructions for exercising
               individual agent frameworks
  pipeline/    orchestration, evidence collection,
               persistence and result types
  requirements/ deterministic legal runtime tests
runtime/      isolated execution environment
```

The three responsibilities that must remain separated:

- **`RepoAdapter`** — "How do I exercise this agent system?"
- **`Evidence`** — "What happened during execution?"
- **`RequirementTest`** — "Does the observed behavior satisfy
  this technical requirement?"

A new repository requires an adapter. A new legal requirement
requires a `RequirementTest`. Neither requires changes to the
other.

## Deterministic result model

Every result carries exactly one of five statuses:

| Status | Meaning |
|---|---|
| `PASS` | The tested runtime behavior satisfies the implemented deterministic assertion. |
| `FAIL` | The tested runtime behavior positively contradicts the implemented assertion. |
| `UNKNOWN` | Execution succeeded but available evidence is insufficient to decide. |
| `UNSUPPORTED` | Reguard cannot currently exercise this repository or requirement combination. |
| `ERROR` | The testing infrastructure or probe failed; this is not a compliance verdict. |

CI policy may choose to fail the build for any non-`PASS`
result, but that policy is separate from the engine's
semantics. The engine reports what it observed; whether to
treat `UNKNOWN` or `ERROR` as a release blocker is the
caller's decision.

## Evidence provenance

Every event in an evidence bundle is tagged with a provenance
label describing who actually created the event:

- `SYSTEM_NATIVE` — the agent runtime itself generated the
  evidence.
- `SYSTEM_STATE_EXPORTED_BY_HARNESS` — the agent runtime
  generated the underlying state and the harness only
  exported it.
- `HARNESS_GENERATED` — the harness created the event itself.
  This is never eligible to establish `PASS`.

This boundary exists so an adapter cannot slip invented events
past a requirement test.

## GitHub Actions

The same engine runs locally and inside GitHub Actions. A
workflow is included:

```
.github/workflows/compliance-article-12-1.yml
```

It supports `workflow_dispatch` with `repository` and `sha`
inputs, checks out the target at the exact SHA, runs the
engine, writes `compliance-result.json`, and uploads the
result and evidence as workflow artifacts. The workflow does
not embed target-specific logic.

The intended next step on the GitHub side is:

```
GitHub App (Reguard Cloud, paid tier)
  -> repository event
    -> entitlement check
      -> exact SHA checkout
        -> Reguard engine (open source)
          -> structured evidence
            -> GitHub Check Run
```

The GitHub App is part of Reguard Cloud. It does not yet
exist. See [`docs/architecture.md`](./docs/architecture.md)
for the planned separation between the open-source engine
and the managed Cloud layer.

## Roadmap

### Phase 1 — Runtime foundation

- [x] Python repository corpus
- [x] Isolated deterministic runtime
- [x] Repository adapter interface
- [x] Requirement-test interface
- [x] Structured evidence
- [x] Evidence provenance
- [x] Exact Git SHA tracking
- [x] Result persistence
- [x] Local execution
- [x] GitHub Actions reproducibility
- [x] EU AI Act Article 12(1)

### Phase 2 — AI Act coverage

- [ ] Expand Article 12(1) across more gold-set Python agent
      repositories
- [ ] Article 12(2)(a) — logging for risk / substantial
      modification events
- [ ] Article 12(2)(b)–(c) — monitoring-support logging
- [ ] Article 14(4)(d) — human override / reverse
- [ ] Article 14(4)(e) — interruption / safe halt
- [ ] Article 15(4) — fault resilience / fail-safe behavior
- [ ] Article 15(5) — agent-runtime cybersecurity controls
- [ ] Article 50(1) + 50(5) — AI interaction disclosure
- [ ] Article 50(2) — machine-readable synthetic-content marking

Applicability is evaluated separately from runtime testability.
Provisions that cannot be expressed as a deterministic runtime
assertion are excluded from this list.

### Phase 3 — Corpus scale

- [ ] Add adapters for more Python agent frameworks
- [ ] Run the full curated gold corpus
- [ ] Adapter capability metadata
- [ ] Adapter compatibility / version tracking
- [ ] Regression detection across commit SHAs
- [ ] Scheduled re-evaluation of upstream repositories

### Phase 4 — GitHub product

- [ ] Reusable GitHub Action
- [ ] GitHub Check Run integration
- [ ] Pull-request status checks
- [ ] GitHub App
- [ ] Repository installation / authorization
- [ ] Automatic checks on push / PR / release
- [ ] Historical results per repository
- [ ] Regression diff between commits
- [ ] Evidence artifact viewer

### Phase 5 — SaaS

- [ ] Organization accounts
- [ ] Repository dashboard
- [ ] Requirement coverage dashboard
- [ ] Commit-to-commit compliance history
- [ ] Alerts / notifications
- [ ] Configurable enforcement policies
- [ ] API
- [ ] Evidence retention
- [ ] Organization-level reporting

### Phase 6 — Additional regulation

- [ ] GDPR technical controls
- [ ] EU Cyber Resilience Act / cybersecurity requirements
- [ ] Additional cybersecurity frameworks and regulations

Each legal requirement must be evaluated individually for
deterministic runtime testability before implementation.

### Phase 7 — Language expansion

- [ ] Evaluate TypeScript / JavaScript agent ecosystem
- [ ] Add language-specific runtime support only after the
      Python architecture stabilizes

## Non-goals

Reguard currently does not:

- certify legal compliance
- replace lawyers, auditors or conformity assessment bodies
- evaluate the intrinsic safety or fairness of a foundation
  model
- use LLMs to make compliance verdicts
- infer compliance from source-code patterns
- prove organisational / process obligations through runtime
  tests
- claim that every legal obligation can be reduced to software
  testing

## Development

Python 3.12 or newer is required.

Install the project in editable mode and the development
extras:

```
pip install -e ".[dev]"
```

Run the full test suite:

```
pytest
```

List the registered requirement tests:

```
python -m compliance.pipeline list-requirements
```

Run Article 12(1) locally against one of the verified
repositories:

```
python scripts/compliance-check.py \
  --repo SWE-agent/mini-swe-agent \
  --sha 25941c89cfbc91eb40b3f8756348c91d9977d57e \
  --output compliance-result.json
```

Run Article 12(1) against an already-checked-out repository
(the path the GitHub Actions workflow uses):

```
python scripts/compliance-check.py \
  --repo SWE-agent/mini-swe-agent \
  --sha 25941c89cfbc91eb40b3f8756348c91d9977d57e \
  --repo-path /path/to/checkout \
  --output compliance-result.json
```

The CLI exits with a deterministic code that maps to the
result status: `PASS` → 0, `FAIL` → 1, `UNKNOWN` → 2,
`UNSUPPORTED` → 3, `ERROR` → 4. `UNKNOWN` and `UNSUPPORTED`
are never collapsed into `FAIL`.

## Reproducibility

Every result is tied to:

- repository
- Git commit SHA
- runtime version
- adapter name and version
- requirement identifier and test version
- the controlled scenario that was executed

The same combination always produces the same result. A
result is never described as applying indefinitely to a
repository regardless of commit.

## Project status / disclaimer

Reguard is an early-stage open-source project. The Article
12(1) engine is the first production requirement; everything
else on the roadmap is planned but not yet implemented. The
project is moving toward a SaaS + GitHub App product but does
not provide hosted services, a GitHub App, or any commercial
offering at this time.

Reguard provides deterministic technical testing and evidence
for specific implemented controls. It does not provide legal
advice or certify overall regulatory compliance.