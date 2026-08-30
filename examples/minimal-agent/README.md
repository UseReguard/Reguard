# examples/minimal-agent

A deterministic, no-network fixture that demonstrates how to run
Reguard against a LangGraph-shaped agent.

This fixture is a product demo, not a real agent. The
`build_graph` factory in `my_agent.py` returns a placeholder
object; `reguard check` runs in **dry-run mode** (set by the
`params.invocation_mode: dry-run` line in `reguard.yml`) which
exercises the full Recipe → ObserverSet → Normalizer → Evidence
path without importing the placeholder or any third-party
framework.

## Quickstart

```bash
cd examples/minimal-agent
PYTHONPATH=../../src python -m compliance.cli doctor --repo-path .
PYTHONPATH=../../src python -m compliance.cli check  --repo-path .
```

Expected result: **PASS** for `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING`.

## Use your own graph

Replace `my_agent.py` with a real langgraph `CompiledStateGraph`
factory and set `params.invocation_mode: live`. The
langgraph-state Recipe will inject the deterministic stub model
and a single `echo` probe tool. See
`docs/integrations.md` for the full list of supported recipes
and families.
