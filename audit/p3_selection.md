# P3 selection — second batch

Date: 2026-08-28 (UTC)

Two new repositories selected from the existing curated corpus
(`audit/gold_article12_v1_repos.json`). Each is one pinned SHA.

| Repo                       | Pinned SHA                                | Pattern probe | Why this repo                                                                  |
|----------------------------|-------------------------------------------|---------------|--------------------------------------------------------------------------------|
| The-Pocket/PocketFlow      | f74d023f93607b8c3268133339a5e532a949898c   | E             | Minimal in-memory graph library. No logger, no DB, no file artifact hooks.     |
| gptme/gptme                | c574b83d34f970f816af18183bd77d01b22bd504   | B             | Per-session LogManager persists JSONL conversation logs to disk automatically.  |

## PocketFlow — why this repo is useful

PocketFlow is a single-file graph-execution library (~100 lines of
actual logic in `pocketflow/__init__.py`):

- A `Flow` / `Node` runtime driven by a `shared` dict. Nodes call
  `prep` / `exec` / `post` against that dict.
- No built-in logger, no DB, no `log.info(...)`, no `print(...)` to
  any persistent sink.
- All "memory" lives in the in-memory `shared` dict; nothing leaves
  the process.

This makes PocketFlow a *clean* test of category **E** — no
framework-side recording exists, so the probe must confirm that the
adapter observes no framework-created artifacts even when the flow
runs to completion.

If this clears E, the A-E taxonomy's empty axis is real (not
just an accident of which repos we happened to pick).

## gptme — why this repo is useful

gptme is a real shell-aware agent with a `LogManager` that:

- Persists each conversation turn as a structured JSONL append-only
  log under `~/.local/share/gptme/logs/<conversation>.jsonl`.
- Records role/content pairs, tool-call records, hash-chained
  message ordering, and a small per-session metadata header.
- The `LogManager` is constructed at agent start, regardless of
  what the agent does or whether the user asked for it.

This makes gptme a clean test of category **B** — the framework
provides *durable, structured, recoverable* session state that
survives process exit. The B axis is currently only implicit in
the v1.3 narrative; this run pins B to a concrete repo.

## Source inspection used for (the user-permitted purposes)

PocketFlow:
- `cat pocketflow/__init__.py` — confirmed there is no `logging`,
  no `open(...)`, no `pickle`, no file path constant of any kind.
- `cat setup.py` — confirmed `install_requires=[]` (zero runtime
  deps). The only way the framework could "record" anything is to
  call into the OS or stdlib directly, which it doesn't.

gptme:
- `find gptme -maxdepth 3 -name 'logmanager*'` — confirmed the
  module exists at `gptme/logmanager/manager.py`.
- `head -60 gptme/session.py` — confirmed `BaseSession.log:
  LogManager | None` is a first-class field.
- `head gptme/chat.py` and `grep` for `LogManager(` — confirmed
  `LogManager` is constructed on every chat step path.

Source inspection stopped at identifying the launch path and the
candidate recording sinks. The adapter logic interprets these
without picking an answer about the verdict.

## Out of scope for this batch

- Significant-Gravitas/AutoGPT (B candidate), Microsoft agent-framework
  (B candidate), and MetaGPT (B candidate) were considered but
  ruled out for v1 because their monorepo layouts (with sub-modules
  fetched by separate `git submodule` steps) make the runtime's
  in-place `git clone --depth 1` checkout either fail or fetch an
  incomplete repo, and their launch paths require non-trivial
  service surface (a web backend, a Postgres instance, a Docker
  daemon) that would compromise the deterministic / no-LLM-creds
  invariant the probe relies on.
- edmar/whenx (general_agent, 52 stars) was considered but its
  `services/create_autogpt.py` calls `OpenAIEmbeddings()` and
  `SerpAPIWrapper()` at module-import time, which would require
  real API keys at the probe boundary; that pushes it firmly into
  P4 rather than the deterministic P3 path.

They remain candidates for later batches once the v1 audit
settles which additional patterns v1 should claim.
