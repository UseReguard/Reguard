"""GitHub search queries used by the discovery pipeline.

Two kinds of queries:

- ``TOPIC_QUERIES`` — narrowly-scoped GitHub topic searches. High precision
  but GitHub topics are noisy and incomplete on their own.
- ``TEXT_QUERIES`` — free-text searches. Lower precision but pick up
  repositories whose owners did not bother to set topics.

We deliberately overlap both kinds because no single query is enough:
  * topics miss projects whose authors skip tagging
  * free-text misses well-tagged niche projects

Each query already constrains ``language:Python archived:false`` so we
do not waste rate-limit on language-mismatched or archived repositories.

If the user wants fewer / different queries, pass ``--query`` to the CLI
to override the default list entirely.
"""
from __future__ import annotations

LANGUAGE_FILTER = "language:Python"
ARCHIVE_FILTER = "archived:false"

# Each entry is the bare search predicate; the pipeline prepends the
# language + archive filters at runtime so callers can mix-and-match.
TOPIC_QUERIES: list[str] = [
    "topic:ai-agents",
    "topic:ai-agent",
    "topic:autonomous-agents",
    "topic:agentic-ai",
    "topic:ai-agent-framework",
    "topic:coding-agent",
    "topic:multi-agent",
    "topic:browser-agent",
]

TEXT_QUERIES: list[str] = [
    '"AI agent"',
    '"autonomous agent"',
    '"coding agent"',
    '"agent framework"',
    '"browser agent"',
    '"computer use agent"',
    '"tool using agent"',
    '"multi agent"',
]


def all_queries() -> list[str]:
    """Return the full default query list with the language + archive filter
    already applied. The order is topic-first (high precision) followed by
    text queries (high recall) — both kinds are needed for a good corpus."""
    out: list[str] = []
    for q in TOPIC_QUERIES:
        out.append(f"{q} {LANGUAGE_FILTER} {ARCHIVE_FILTER}")
    for q in TEXT_QUERIES:
        out.append(f"{q} {LANGUAGE_FILTER} {ARCHIVE_FILTER}")
    return out


def parse_user_query(raw: str) -> str:
    """Apply the default filters to a user-supplied query so callers do not
    accidentally discover archived or non-Python repositories."""
    q = raw.strip()
    if LANGUAGE_FILTER not in q:
        q = f"{q} {LANGUAGE_FILTER}"
    if ARCHIVE_FILTER not in q:
        q = f"{q} {ARCHIVE_FILTER}"
    return q
