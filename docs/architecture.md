# Architecture sketches (provisional)

This document sketches two future architectures:

1. the hosted free manual-check service (Reguard Cloud,
   free tier);
2. the paid GitHub App for continuous automated checks
   (Reguard Cloud, paid tier).

Both architectures are **proposals only**. They describe a
future separation of concerns. Neither has been built, and
neither should be built before the design-partner phase
(see `docs/design-partner-plan.md`) validates demand.

The compliance engine itself is open source (AGPL-3.0,
see `docs/licensing.md`). The architectures below describe
Reguard Cloud: the orchestrated, managed product layer
that calls the engine as a library.

## Architectural boundary

The repository contains the open-source engine. Reguard
Cloud and the GitHub App will live in a separate codebase
or package. The split is a **product** decision, not an
automatic **license** decision.

In other words: putting orchestration code in a separate
package does not automatically exempt it from the AGPL
copyleft obligation that arises when it links with or
extends the engine. Whether Reguard Cloud ends up under
AGPL or under a separately-negotiated commercial license is
a question for qualified legal review at the time the
Cloud code is published. This document does not commit to
either outcome.

The split below is described as a product boundary, with
the explicit reminder that the license boundary may be
different.

## What the open-source engine is

This repository. Anyone can, under AGPL terms:

- run `scripts/compliance-check.py` locally against any
  pinned SHA they choose;
- call `compliance.pipeline.run_one()` /
  `compliance.pipeline.run_path_mode()` from their own
  automation;
- write and ship new adapters in `src/compliance/adapters/`;
- write and ship new requirement tests in
  `src/compliance/requirements/`;
- use the GitHub Actions workflow
  (`.github/workflows/compliance-article-12-1.yml`)
  unchanged in their own forks or repositories.

The engine does not require any cloud-side component to
function. Local, CI, and self-hosted automation are
first-class paths under AGPL, not degraded fallbacks.

## What Reguard Cloud is

Reguard Cloud is the managed product layer around the
engine. Its scope is operational, not licensing:
multi-tenant accounts, hosted execution, GitHub App,
scheduled triggers, persistence, alerting, regression
history, and reporting. The engine is invoked as a
library. Architectural rules below ensure Cloud does not
sully the engine's licensing position through accidental
coupling.

## 1. Hosted free manual-check service

### User flow

```
browser
  -> user submits public GitHub URL + optional SHA
    -> backend validates repository visibility
      -> resolves default branch / exact commit SHA
        -> enqueues an isolated check
          -> invokes the existing compliance engine
            -> persists the run + evidence bundle
              -> frontend result page (status + evidence)
                -> evidence bundle is downloadable
```

### Components

- **Frontend**: a single-page form. Accepts a
  `https://github.com/owner/name` URL, optionally a commit
  SHA, and a captcha or equivalent anti-abuse signal.
- **Backend**: a thin service that validates the URL,
  looks up the repository metadata, and enqueues a job.
- **Job runner**: an isolated worker that performs the
  same steps the local CLI performs today: clone the
  repository at the requested SHA into an ephemeral
  workspace; invoke `scripts/compliance-check.py`;
  collect the resulting JSON; capture the evidence bundle.
- **Persistence**: an append-only table of submitted
  checks, results, and evidence paths, separate from the
  development SQLite database used to track the engine
  itself.
- **Result page**: a server-rendered page with the result
  summary, the evidence bundle, and a download link.

### What the existing engine provides

- The current `run_path_mode()` entry point: a checkout is
  provided, the SHA is verified, and the engine runs
  against it.
- The same exit-code contract, the same evidence schema,
  the same result model.

### What is not built

- the queue (a simple in-process or short-lived worker at
  first);
- a user-account system (no logins for free users);
- rate-limiting infrastructure beyond a basic per-IP
  cap;
- payment integration (this is the free tier);
- dashboards, history, alerts.

### Anti-abuse

The free service must not become an open relay for
arbitrary GitHub repositories to be checked by anyone. A
minimum set of guard-rails:

- a per-IP rate limit;
- a captcha or equivalent challenge;
- a public allow-list and block-list of repositories;
- a hard ceiling on the total number of checks per day;
- isolation between runs so that two users cannot
  influence each other's evidence.

No implementation details beyond this are decided.

## 2. Paid GitHub App for continuous checks

### Event flow

```
GitHub App installed
  -> push / pull_request / release event
    -> entitlement check (subscription active?)
      -> checkout exact SHA
        -> invoke the existing compliance engine
          -> store result + evidence
            -> post GitHub Check Run
              -> update commit history
                -> optional regression alert
```

### Components

- **GitHub App**: registered under the chosen product
  name (which is still provisional — see
  `docs/product-model.md`). Permissions:
  `contents: read`, `checks: write`, and whatever else is
  minimally required for the desired flows.
- **Webhook handler**: receives events, normalizes them,
  routes to the entitlement check. No compliance logic
  here.
- **Entitlement service**: a separate component that
  answers "is this organization allowed to schedule a
  check against this repository?" It is the only place
  where subscription / commercial decisions live.
- **Job runner**: identical to the hosted free runner.
  This is intentional — the runner does not care who
  scheduled the check, only what to do.
- **Persistence**: results keyed by installation,
  repository, SHA, and dedup tuple as today.
- **Check Run publisher**: turns a result into a GitHub
  Check Run with status (`queued`, `in_progress`,
  `completed`), conclusion (`success`, `failure`,
  `neutral`, `timed_out`, …), and a markdown summary that
  links to the evidence bundle.
- **History and regression views**: per-repository and
  per-organization history of results and a regression
  detector keyed on adapter + requirement versions.

### Architectural rules

These rules are not implementation details; they shape the
design.

- **The compliance engine must not import, query, or
  branch on subscription state.** It must not know
  whether an organization has paid. A `RequirementTest`
  sees only the evidence and the requirement. The
  entitlement check is upstream of the run.
- **The compliance engine must remain a pure deterministic
  function** for a given (repository, SHA, runtime,
  adapter, requirement, scenario) tuple. The host can
  change around it; the engine stays the same.
- **Provenance boundaries are unchanged.** The compliance
  engine's evidence-provenance rules still apply in the
  hosted and GitHub App environments.
- **The same persistence schema applies.** Whether a run
  came from a local CLI, GitHub Actions, the hosted free
  service, or the GitHub App, the result is recorded the
  same way.

### What is not built

- the GitHub App itself;
- the entitlement service;
- the Check Run publisher;
- the dashboard;
- the regression detector;
- the pricing / billing integration.

## Summary

The Reguard engine in this repository is open source under
AGPL-3.0. Reguard Cloud and the GitHub App are planned
managed products that wrap that engine in a hosted
service. Putting Cloud in a separate package is a product
decision, not an automatic license boundary; whether Cloud
ends up AGPL or under a separately-negotiated commercial
license is a legal-review question we have not yet
answered.

The full SaaS dashboard is a later milestone that depends
on the design-partner phase succeeding (see
`docs/design-partner-plan.md`).
