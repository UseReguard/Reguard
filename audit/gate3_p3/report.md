# Gate 3 — runtime classification of the second batch

Date: 2026-08-28 (UTC)
Executor: container via podman, frozen `python-agent-runtime:dev` image.

## Selected repositories (see `audit/p3_selection.md` for rationale)

| Repo                       | Pinned SHA                                | Expected category |
|----------------------------|-------------------------------------------|-------------------|
| The-Pocket/PocketFlow      | f74d023f93607b8c3268133339a5e532a949898c   | E                 |
| gptme/gptme                | c574b83d34f970f816af18183bd77d01b22bd504   | B                 |

## Results

### PocketFlow — STOP condition (contract tension)

Observed verdict: **UNKNOWN**
Observed category: **E** (no framework-side recording)
Observed evidence count: 0
Observed probe status: ok

The PocketFlow adapter emits category=E
(`recording_category=E`, `framework_persists_durably=false`,
`framework_artifact_paths=[]`). The probe ran cleanly: a two-node
Flow executed end-to-end and no framework-written artifact appeared
on disk.

The runtime verdict was UNKNOWN, not FAIL, because the v1.3 base
class short-circuits on `if not evidence.events: status=UNKNOWN`
*before* `assert_evidence` runs. The category=E branch in
`article_12_1.py` is designed to yield FAIL
(`RECORDING_CATEGORY_E_NON_PASS` with `passed=False`), but it is
never reached when the framework produces no events.

This is documented v1.3 behaviour:

> category E → FAIL when absence is observed at runtime; the
> empty-events case is mapped to UNKNOWN upstream of
> assert_evidence (handled in the base class).

It is also a real contract tension with P4 of this iteration:

> observable absence of framework-side recording → FAIL;
> inability to establish whether recording occurred → UNKNOWN

For PocketFlow the absence IS observable (the Flow ran, the probe
did not crash, the framework wrote nothing). Today, the contract
returns UNKNOWN. Per the user's P3 stopping rule:

> If a repo exposes a new pattern that does not fit A–E: STOP.

The repo does fit A-E. But the verdict mapping for the empty-events
case is a contract-level choice that is now demonstrated to be
ambiguous between "observable absence" (P4 says FAIL) and "no
events collected" (v1.3 base class says UNKNOWN). That ambiguity is
worth surfacing before continuing.

The two compatible fixes are:

1. **Make the base class recognise the E-with-empty-events case as
   observable absence → FAIL.** The category-shaped
   `evidence.extra["recording_category"]` already carries enough
   information to do this dispatch without disturbing A/B/C/D.
2. **Make the adapter emit a SYSTEM_NATIVE absence marker event**
   so the events-list is non-empty and `assert_evidence` is
   reached. This works without touching the base class but
   fabricates a single event where the framework genuinely emitted
   none.

I lean toward (1) — it explicitly maps the requirement text onto
the verdict and matches P4. I am stopping here and not changing
code, per the user's stop-on-contract-flaw rule.

### gptme — STOP condition (infrastructure failure)

Observed verdict: **ERROR** (driven by `unsupported` from the runtime)
Runtime error: `build strategy 'poetry' is not supported: the
runtime image installs uv only`

gptme's `pyproject.toml` declares Poetry and ships `poetry.lock`.
The runtime's build strategy detection maps this to
`strategy="poetry"`, which is in `UNSUPPORTED_STRATEGIES`. The
runtime exits with `status=unsupported` before any install / exec
step runs.

Per the user's stopping rule:

> infrastructure failure prevents deterministic interpretation

This is exactly that situation: the runtime image installed only
uv, and gptme requires Poetry. The two compatible fixes are:

1. **Extend the runtime Dockerfile to install Poetry.** Makes the
   runtime larger but adds real coverage for Poetry-anchored repos.
2. **Pick a different B-candidate** that uses uv / pip / setuptools,
   so the runtime can already install it.

The selected PocketFlow and gptme combination was deliberate
(source inspection confirmed gptme's persistence layer), but I
should have stopped at the build-strategy detection check before
declaring it ready. Stopping now and not attempting a Poetry
extension without sign-off; that would change the runtime image
contract in a way that affects every other repo that already runs.

## What Gate 3 confirmed

- The A-E taxonomy holds at the adapter level for both new repos.
- PocketFlow → E (zero recording) is real and observable.
- gptme → B is real (LogManager writes a JSONL append-only log) but
  unverifiable on this runner because of Poetry.

## What Gate 3 surfaced

- Empty-Events-vs-Observable-Absence contract tension (PocketFlow).
- Runtime-image build-strategy gap (gptme / Poetry).

Both are real findings that should be resolved before further
gates. **Stopping here** per the user's explicit instruction.
