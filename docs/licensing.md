# Licensing

This document explains the licensing position of this
repository. It is descriptive, not legal advice. The
binding license is the [`LICENSE`](../LICENSE) file at the
repository root.

## What this project is

This project is **open source**.

The Reguard compliance engine — the deterministic runtime
test engine in `src/compliance/` — is distributed under the
**GNU Affero General Public License, version 3 (AGPL-3.0-only)**.
SPDX-License-Identifier: `AGPL-3.0-only`.

Copyright (c) 2026 Marcelo.

The full license text is at the repository root in the
`LICENSE` file and is identical to the version published by
the Free Software Foundation. It has not been modified.

## What the AGPL permits

Subject to the AGPL terms, recipients may, among other
things:

- run the software for any purpose, including commercial
  purposes and as a network-accessible service;
- inspect the source, including every requirement test, every
  adapter, every evidence-formatting decision;
- modify the software for their own purposes;
- redistribute the software and modifications, with or
  without changes, in source or compiled form.

The AGPL also imposes obligations. Notable obligations
include:

- the copyleft requirement that derivative works distributed
  (or, for AGPL, made accessible over a network) under the
  same license retain the same freedoms;
- the requirement to provide Corresponding Source to users of
  a network-accessible modified version (this is the
  "Affero" half of AGPL);
- the obligation to license contributions under compatible
  terms;
- the standard "no warranty" disclaimer.

This document is not a summary of the AGPL. Read the
`LICENSE` file for the binding text.

## The two layers of the product

The repository contains the open-source **Reguard engine**.
The repository does not yet contain the managed **Reguard
Cloud** product. The intended split is:

- **Reguard engine** (this repository, AGPL-3.0).
  The deterministic compliance-checking engine:
  repository adapter interface, evidence-provenance rules,
  requirement tests, persistence, CLI entry points, GitHub
  Actions workflow, the synthetic test suite. Anyone can run,
  audit, modify, and redistribute it under AGPL terms.
- **Reguard Cloud** (separate, planned).
  The managed hosted product: orchestrating checks against
  public repositories on behalf of free-tier users, the
  GitHub App integration for paid customers, multi-tenant
  account management, evidence retention, alerting,
  reporting, and the organization dashboard. Cloud code is
  not yet published. When published, it will live in a
  separate repository or package.

The AGPL does **not** become inapplicable simply because
orchestration or integration code lives in a different
package. The architectural separation is a product decision
about where each kind of code lives, not an automatic
license boundary. The license position of a derived or
combined work depends on its actual composition and the
applicable copyright rules, not on which folder it lives
in. This is intentional: the architectural boundary and the
license boundary are not the same thing.

## Why a free hosted check remains useful

The hosted free manual-check service is a **product
acquisition channel**, not a software license restriction.
AGPL already grants the right to run the engine; the hosted
service simply gives users a way to obtain a result without
running the engine themselves. Its value is convenience, not
permission.

## Why Reguard Cloud is paid

Reguard Cloud sells **management, automation, persistence,
and operational convenience**, not the right to execute the
checker. The right to execute the checker comes from AGPL.
What Cloud adds:

- managed isolated execution infrastructure so users do not
  have to operate it themselves;
- a GitHub App that wires push / pull-request / release
  events to the open-source engine;
- private repository management and credential handling;
- multi-tenant accounts, organizations, and policies;
- history, regression detection, evidence retention, and
  alerts;
- organization dashboards and reports;
- support, SLAs, and managed adapter compatibility.

Pricing is not defined yet (see `docs/product-model.md` and
`docs/design-partner-plan.md`).

## Dual licensing (provisional, not active)

A future commercial **dual-license** option may be evaluated
for organizations that require terms different from AGPL.
It is not implemented and not offered. Evaluation requires
qualified legal review of:

- whether AGPL's terms can be supplemented with a
  separately-negotiated commercial license for the same
  code;
- the contributor copyright and CLA strategy required to
  preserve that option;
- which entities, if any, would be eligible;
- pricing and territory;
- interaction with the public open-source release.

Until a qualified lawyer signs off, no commercial license
is offered and no CLA exists.

## Contributions

A contributor license agreement (CLA) does **not** exist yet.
Before accepting substantial external contributions we must
decide which of the following applies:

- contributions remain under AGPL only, and we accept no
  obligation to relicense; or
- contributors grant sufficient rights to permit future
  dual licensing under a commercial license that does not
  conflict with AGPL's copyleft.

This decision **requires qualified legal review**. Until the
review and the CLA exist, treat the project as accepting no
outside copyright contributions to source. Bug reports,
discussions, and small documentation fixes are welcome
through normal GitHub channels and do not require a CLA;
substantial code contributions do not.

## What still needs qualified legal review

The engine is open source under AGPL. Beyond the engine,
the following still need a qualified software / IP lawyer
before any commercial product launch:

- the dual-licensing evaluation above;
- the contributor license agreement text and process;
- the Reguard Cloud terms of service for free and paid
  users;
- the data-processing addendum covering evidence bundles
  that may contain user-submitted repository contents;
- the trademark strategy for the product name (see
  `docs/product-model.md` for the open items).

Until those documents are finalized, treat the items above
as the project's current intent, not as binding legal
instruments.

## Reading order

If you came here for the license:

1. read [`LICENSE`](../LICENSE) — that is the binding text;
2. read this document for the architectural and commercial
   framing;
3. read [`docs/product-model.md`](./product-model.md) for the
   product context.

If you came here for the commercial model, read
[`docs/product-model.md`](./product-model.md) and
[`docs/architecture.md`](./architecture.md) next.
