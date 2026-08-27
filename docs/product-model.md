# Product model

This document describes the current product hypothesis. It is
explicitly provisional; the model will change once real
customers are interviewed.

## Positioning

> Deterministic regulatory runtime tests for AI agents.

The supporting claim:

> The system executes an agent under controlled conditions
> and evaluates specific machine-observable regulatory and
> security controls. Every result is tied to a repository, a
> commit SHA, a runtime version, an adapter version, a
> requirement version, and a scenario.

Do not market the product as any of the following:

- automated AI Act certification
- AI compliance guaranteed
- complete AI governance platform
- AI auditor
- legal advice
- conformity assessment

Individual runtime tests do not establish overall legal
compliance. Results are deterministic technical evidence for
specific implemented controls.

## Free tier (provisional)

The free experience is a hosted manual check on our
infrastructure. No software license is granted.

Scope:

- public repositories only;
- user submits one GitHub URL at a time;
- the check is manually triggered;
- one repository / one commit per check;
- request frequency is limited;
- check executes on our infrastructure;
- result page shows status and evidence;
- evidence bundle is downloadable;
- no continuous monitoring;
- no GitHub App installation;
- no private repositories;
- no compliance-certification claim;
- no persistent account.

Design intent: a free user gets one real, useful result, sees
the determinism and the evidence format, and can show the
artifact to a colleague or security reviewer.

## Paid tier (provisional)

The paid experience is automated GitHub-native continuous
monitoring, gated by a commercial agreement (see
`docs/licensing.md`).

Scope:

- GitHub App installation in the customer's organization or
  user account;
- private and public repositories;
- multiple repositories in one organization;
- automatic checks on push, pull request, and release;
- scheduled re-checks against upstream references;
- commit history with per-commit results;
- regression detection across commits;
- evidence retention;
- status checks and merge-gating through GitHub Checks;
- notifications and alerting;
- an organization dashboard later.

Pricing is not defined yet. Pricing will be set after the
design-partner plan (see `docs/design-partner-plan.md`)
produces enough signal to know what to charge.

## Initial ideal customer profile

The hypothesis is that paying customers are teams building
commercial AI-agent products, especially B2B vendors
shipping into regulated or European customers.

Primary:

- engineering and security teams building commercial
  AI-agent products;
- B2B SaaS vendors serving regulated industries;
- B2B vendors with EU customers facing AI Act questions;
- teams that already answer security questionnaires and
  AI-Act questionnaires today.

Likely pain:

- customer security reviews that ask about agent runtime
  controls;
- AI Act questionnaires that ask about logging,
  oversight, fault handling, and interaction disclosure;
- a need to produce runtime evidence rather than
  policy statements;
- a need to keep that evidence current across releases;
- a need to detect regressions in implemented controls
  after code changes.

Secondary:

- open-source agent / framework maintainers who can use the
  free tier;
- research teams and academic groups that benefit from the
  free tier.

The secondary segment is useful for validating adapters and
collecting feedback, but is not assumed to be the primary
paying customer.

## Brand and naming

> The current working name **"Reguard"** is provisional.

The word *Reguard* already appears in compliance and risk
contexts (existing AI-compliance vendors, enterprise risk
platforms). A full trademark, domain, and name-collision
review must happen before any public product launch that
involves:

- the product name in marketing;
- a domain registration;
- a GitHub App slug;
- paid search or social accounts.

Until that review is complete:

- do not register the `Reguard` name as a domain;
- do not publish the GitHub App under the `Reguard` slug;
- do not print the name on user-facing artifacts other
  than this repository;
- treat any reference to "Reguard" in this repository as a
  placeholder.

## Pre-launch checklist

Before any public product launch the following items must
close. These are deliberately blocked, not parking-lot items.

- [ ] trademark, domain, and name-collision review for the
      product name;
- [ ] qualified legal review of the `LICENSE`, hosted
      service terms, paid subscription agreement, and
      contributor license agreement;
- [ ] at least three design partners connected or with a
      real agent repository submitted through the free
      service (see `docs/design-partner-plan.md`);
- [ ] at least one design partner explicitly asking for
      continuous automated checks;
- [ ] at least one design partner willing to pay for
      continuous monitoring once the relevant controls are
      covered;
- [ ] a final pricing model, decided after design-partner
      interviews, not before.

## What this product model is not

It is not:

- an open-source product;
- a self-hosted free checker for everyone;
- a one-size-fits-all compliance platform;
- a replacement for legal review or conformity
  assessment;
- a static source-code scanner.

The product model and the technical engine are deliberately
narrow. The narrowness is the wedge.
