# Design partner plan

This document defines how we validate demand before
committing to the paid GitHub App. The goal is to learn
whether teams will pay for continuous, commit-level
regulatory evidence. The work below is a validation plan,
not a build plan.

## Why design partners first

The technical engine is already demonstrated. The remaining
risk is commercial: whether engineering and security teams
will actually pay for automated runtime checks tied to
exact commits. We will not learn that by building more SaaS
infrastructure. We will learn it by talking to real teams
that ship real agent products into real customer
environments.

## Goal

Recruit five design partners and use their feedback to
decide whether to invest in the paid GitHub App.

This is not a survey and not a marketing exercise. It is a
short series of structured conversations with teams who
could plausibly pay.

## Target

Five design partners, each from a different organization if
possible.

Strong candidate profiles:

- a B2B SaaS team shipping an AI agent feature into
  regulated customers;
- a security / platform team at a company whose customers
  ask about AI Act compliance;
- an open-source agent-framework maintainer with a clear
  enterprise user base;
- a consultancy or systems integrator that runs AI-act
  questionnaires on behalf of customers;
- an enterprise buyer (security, GRC, or legal) evaluating
  agent-runtime evidence as part of procurement.

We are not looking for "developers curious about AI
compliance" as the primary persona.

## Intake per partner

For each design partner we collect the following in a
short, structured conversation. The intent is to record the
shape of the problem, not to extract contractual commitments.

Per partner, capture:

- the number of agent repositories they maintain or depend
  on;
- whether those repositories are public, private, or both;
- the primary Python framework(s) in use;
- whether they sell into EU customers and whether those
  customers already ask about AI Act compliance;
- which compliance or security review triggered their
  interest;
- who owns the problem internally: engineering, security,
  GRC, legal, or product;
- the way they currently prove runtime controls across
  releases;
- the frequency of code changes that could affect the
  tested controls;
- whether automated GitHub checks would replace a manual
  step they already run;
- which result or evidence artifact they would actually
  need to show a customer, an auditor, or a procurement
  reviewer;
- their initial reaction to the pricing shape: would they
  pay for continuous monitoring, would they prefer a
  per-check price, or is budget the blocker;
- the contacts and roles of the people involved.

Store the intake in a private document, not in this
repository. Do not publish partner names, contract values,
or pipeline data here.

## Success criteria

We treat the design-partner phase as successful — and
therefore worth continuing to the paid GitHub App — when
**all** of the following are true:

- at least three real organizations have connected a real
  agent repository, either through the free hosted service
  or in a private evaluation;
- at least two of those organizations explicitly state that
  continuous checks on every commit or PR would replace a
  manual workflow they currently run;
- at least one of those organizations is willing to pay
  for continuous monitoring once the controls they need
  are covered.

These criteria are deliberately strict. Design-partner
validation succeeds only when a paying customer can be
named, not when a survey is positive.

## What we do not do

During the design-partner phase we do not:

- manufacture survey results;
- count exploratory conversations as design partners;
- count open-source maintainers using the free tier as a
  signal of paid demand;
- count "would be useful" answers as a willingness to pay;
- build billing, authentication, or a dashboard before the
  criteria above are met.

## Stop conditions

We stop the design-partner phase and revisit the strategy if
any of the following happens:

- fewer than three organizations connect a real repository
  within the recruitment window;
- the connected organizations ask for capabilities that
  the engine does not cover, in proportions that mean the
  current Article 12(1) wedge is too narrow;
- every connected organization is in the secondary
  segment (open-source maintainers, academic users) and
  none is in the primary B2B-regulated segment;
- the connected organizations explicitly say they would
  not pay for continuous checks even if the relevant
  controls were covered;
- the qualified legal review surfaces an issue that blocks
  the commercial model.

A stop condition is data, not a failure. It informs the
next decision.

## After success

If the success criteria are met, the next concrete step is
to scope the paid GitHub App: minimum install flow,
entitlement check, and a single automated check per push.
That work begins after this phase, not before.
