# Security model

Reguard Core runs locally and does not send compliance evidence
to Reguard. This document describes what Reguard does, what it
deliberately does not do, and the known limitations of the
v0.1 sandbox.

## What Reguard Core is

- A Python package that runs in a host Python environment.
- A CLI (`reguard`) that drives Recipes.
- A composite GitHub Action that calls the CLI.

## What Reguard does NOT do

- It does NOT upload evidence to Reguard.
- It does NOT call any LLM provider API.
- It does NOT call a hosted Reguard API (none exists in v0.1).
- It does NOT require an account, login, or registration.
- It does NOT send telemetry, analytics, or crash reports.
- It does NOT modify the target repository.
- It does NOT modify third-party code.

## Execution boundary

In v0.1, the default invocation driver is `subprocess` — the
Recipe runs the target factory inside the same Python process
as the harness. The factory call is sandboxed by:

- A deterministic stub model (no LLM calls)
- An explicit forbidden-env list (no provider keys)
- An explicit allowed-env list (only what the recipe needs)
- A short per-run timeout (recipe-defined)

Recipes can opt into `OCI_CONTAINER` invocation. When they do,
the harness invokes the host OCI runtime (podman / docker) with:

- non-root user
- dropped capabilities
- `no-new-privileges`
- `/input` mounted read-only
- `/artifacts` mounted as a tmpfs
- network disabled for the probe container
- host secrets excluded
- the OCI socket is NOT mounted into the target container
- ephemeral workspace (deleted on container exit)
- bounded source cache

## Provider-key policy

The integration layer enforces a forbidden-env allow-list.
The following environment variables, if set in the harness
environment at run time, cause the run to refuse to execute:

```
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
GEMINI_API_KEY
VERTEXAI_PROJECT
AZURE_OPENAI_API_KEY
HUGGINGFACEHUB_API_TOKEN
COHERE_API_KEY
MISTRAL_API_KEY
GROQ_API_KEY
```

The composite GitHub Action explicitly clears these from the
harness environment before invoking `reguard check`.

`GITHUB_TOKEN` is NOT exported into the harness environment.
The Action does not auto-inject any host secret into the
target.

## Target trust model

Target repositories are treated as **untrusted**. The recipe
loads and invokes the user-supplied entrypoint. The integration
layer does not validate that the entrypoint is benign. Users
should only run `reguard check` against repositories they
trust.

## Known limitations of v0.1

- The subprocess invocation driver does not isolate the
  factory call from the harness process. A malicious factory
  could read the harness's memory or filesystem. Use the
  `OCI_CONTAINER` driver when targeting untrusted code.
- The OCI runtime image is not yet distributed publicly; in
  v0.1 the subprocess driver is the default.
- The Reguard runtime depends on PyPI for installation. A
  malicious PyPI release could affect harness integrity.
- The hash-based stable id for `result.json` is for
  reproducibility, NOT for cryptographic trust.

## Vulnerability reporting

Please open a GitHub issue or contact the maintainers.
Security disclosures are handled by the maintainers per the
AGPL-3.0 license.
