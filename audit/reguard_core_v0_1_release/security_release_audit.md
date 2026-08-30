# Reguard Core v0.1 — Security Release Audit

**Date:** 2026-08-30

---

## 1. No-telemetry audit

Searched source tree (`src/`, `tests/`, `action.yml`,
`scripts/`) and the installed package for the following
patterns:

```text
analytics
telemetry
sentry
segment
posthog
amplitude
mixpanel
```

**Findings:** All matches are false positives:

| File | Match | Context |
|---|---|---|
| `src/compliance/pipeline/container_runner.py` | "segment" | "failed to map segment" — mmap address-space segment, not analytics |
| `src/compliance/legal/chunker.py` | "segment" | RAG text segmentation |
| `scripts/maintenance/collect_eu_ai_repos.py` | "analytics" | data-signal classification keyword |

**Verdict:** Zero actual telemetry calls. PASS.

Searched for outbound Reguard-controlled HTTP calls
(`reguard[_-]?(cloud|api|hosted|telemetry|analytics)`):

**Findings:** Zero matches. PASS.

## 2. Provider-secret isolation

Verified by setting dummy values for all known provider env
vars and running `reguard check` against the demo:

```text
ERROR — env validation failed: forbidden env var 'OPENAI_API_KEY' is set
```

Reguard refuses to execute the recipe when any provider key is
in the harness environment. The integration layer's
`validate_env` enforces this before any Recipe runs.

The GitHub Action additionally clears the following env vars
from the harness environment before invoking `reguard check`:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
GEMINI_API_KEY
AZURE_OPENAI_API_KEY
HUGGINGFACEHUB_API_TOKEN
COHERE_API_KEY
MISTRAL_API_KEY
GROQ_API_KEY
```

PASS.

## 3. Package-content audit

The wheel contains 78 entries. Audited for:

| Pattern | Match |
|---|---|
| `.env*` | 0 |
| `*.sqlite*` / `*.db` | 0 |
| `.git/` | 0 |
| `audit/` | 0 |
| `workspace/` (data) | 0 |
| `cache/` (data) | 0 |
| `credentials*` | 0 |
| `compliance.db` | 0 |
| Obsidian vault | 0 |

The wheel contains only:

- `compliance/` (Python package)
- `reguard-0.1.0rc1.dist-info/` (PEP 427 metadata)

The `compliance/corpus_runner/cache/` and
`compliance/corpus_runner/workspace/` paths that appear in the
wheel are **source-code module names** (`cache/source_cache.py`,
`workspace/manager.py`), not data directories.

PASS.

## 4. Secret scan

No `.env`, `*.pem`, `*.key`, `*credentials*`, `*.sqlite*`,
`compliance.db` files exist at the repository root. The
gitignore excludes:

```text
.env
.env.*
.cache
.reguard/
audit/corpus_runner_v1/*.db
data/
out/
```

PASS.

## 5. Dependency vulnerability check

| Package | Version | Known CVE |
|---|---|---|
| `sqlalchemy` | 2.0.52 | none known |
| `httpx` | 0.28.1 | none known |
| `pydantic` | 2.13.5 | none known |
| `PyYAML` | 6.0.3 | none known |

No known high-severity CVEs at v0.1 RC. Transitive deps
(`anyio`, `certifi`, `h11`, `httpcore`, `idna`, `sniffio`,
`typing-extensions`, `annotated-types`) — all current as of
this gate.

PASS.

## 6. License audit

| File | Present? |
|---|---|
| `LICENSE` | ✓ (AGPL-3.0-only, 35,331 bytes) |
| `SECURITY.md` | ✓ |
| `CONTRIBUTING.md` | ✓ |
| `CODE_OF_CONDUCT.md` | ✓ |
| `README.md` | ✓ |

Third-party dependencies — no copyleft transitive deps
that would conflict with AGPL-3.0-only distribution.

PASS.

## 7. Known limitations (carried over)

Documented in `SECURITY.md`:

- Subprocess invocation driver does not isolate factory call
  from harness process; use `OCI_CONTAINER` for untrusted code.
- Public OCI runtime image not yet distributed in v0.1.
- Reguard runtime depends on PyPI for installation.

These are documented and out-of-scope for v0.1 RC.

## 8. Conclusion

**READY.** No telemetry, no secret leakage, no provider-key
risk, no private data in the wheel, all OSS hygiene files
present.

— end of security release audit —
