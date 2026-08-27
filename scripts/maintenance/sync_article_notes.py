#!/usr/bin/env python3
"""Materialize one Obsidian note per AI Act article.

Reads the existing `article_runtime_assessments` rows from the
canonical SQLite database and projects them into per-article notes
under `<vault>/EU AI Act/Article N - Title.md`.

This script does NOT recompute classifications. It only reads
existing DB rows and writes them into the vault. The legal text for
each article comes verbatim from `law_articles.text`.

Each generated note uses explicit markers so re-runs are idempotent
and any human-written content outside the generated blocks is
preserved:

    <!-- ARTICLE_TEXT:START --> ... <!-- ARTICLE_TEXT:END -->
    <!-- RUNTIME_TESTABILITY:START --> ... <!-- RUNTIME_TESTABILITY:END -->

Usage:
    python3 scripts/sync_article_notes.py \\
        --celex 32024R1689 \\
        --vault /mnt/c/Users/mrcel/Desktop/Obsidian\\ Vaults/EU-AI-Compliance
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


ARTICLE_TEXT_START = "<!-- ARTICLE_TEXT:START -->"
ARTICLE_TEXT_END = "<!-- ARTICLE_TEXT:END -->"
RT_START = "<!-- RUNTIME_TESTABILITY:START -->"
RT_END = "<!-- RUNTIME_TESTABILITY:END -->"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _bare_article_number(article_number: str) -> int:
    m = re.match(r"^(\d+)", article_number)
    if not m:
        raise ValueError(f"cannot parse article number: {article_number!r}")
    return int(m.group(1))


def _load_articles(
    conn: sqlite3.Connection, celex: str
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, article_number, title, text
        FROM law_articles
        WHERE celex = ?
        ORDER BY id
        """,
        (celex,),
    ).fetchall()


def _load_assessments(
    conn: sqlite3.Connection, celex: str
) -> dict[int, list[sqlite3.Row]]:
    """Return {bare_article_number: [assessment rows]}."""
    rows = conn.execute(
        """
        SELECT article_number, atomic_id, paragraph, point, sub_point,
               text_excerpt, full_text_hash, classification,
               agent_system_relevant, applicability_note,
               testability_rule_json, notes, status, classifier,
               reviewer, created_at, updated_at
        FROM article_runtime_assessments
        WHERE celex = ?
        ORDER BY id
        """,
        (celex,),
    ).fetchall()
    out: dict[int, list[sqlite3.Row]] = {}
    for r in rows:
        bare = _bare_article_number(r["article_number"])
        out.setdefault(bare, []).append(r)
    return out


# ---------------------------------------------------------------------------
# Note rendering
# ---------------------------------------------------------------------------
def _safe_title(title: str) -> str:
    """Return the title for use inside note CONTENT (heading, frontmatter).

    This is the verbatim title from `law_articles.title`. We do not
    alter it because the user wants the canonical name preserved in
    the note body.
    """
    t = (title or "").strip().replace("\n", " ").replace("\r", " ")
    return t


def _filename_safe_title(title: str) -> str:
    """Return a sanitized title suitable for use as a FILENAME.

    Obsidian rejects certain characters in filenames (`/`, `:`, backtick,
    leading/trailing dots). The corpus occasionally contains stray
    backticks (e.g. Article 1's title is literally "Subject matter`").
    We strip those for filenames but keep the original in the heading.
    """
    t = _safe_title(title)
    t = re.sub(r"[`/\\:*?\"<>|]", "", t)
    t = t.strip(" .")
    return t or "Untitled"


def _render_article_text(text: str) -> str:
    """Wrap the canonical article text in ARTICLE_TEXT markers.

    The marker layout is `START\n<text>\nEND\n`. The substring between
    START and END is `\n<text>\n` — the leading newline is part of the
    block separator, not part of the article text itself. This is
    conventional Markdown whitespace.
    """
    body = (text or "").rstrip() + "\n"
    return f"{ARTICLE_TEXT_START}\n{body}{ARTICLE_TEXT_END}\n"


def _render_rt_section(assessments: list[sqlite3.Row]) -> str:
    """Render the Runtime Testability block from existing DB rows.

    The block shows:
        - requirement ID (= atomic_id)
        - atomic requirement (text excerpt)
        - classification
        - applicability (applicability_note)
        - precondition / stimulus / observable / assertion (from
          testability_rule_json when present)
        - review status (status, classifier)

    The table does NOT recompute anything — every field comes from
    the stored row.
    """
    lines: list[str] = []
    lines.append(f"{RT_START}\n")
    lines.append(
        "Existing runtime-testability assessments stored in "
        "`article_runtime_assessments`. Generated by `sync_article_notes.py`. "
        "Do not recompute classifications here; edit the DB row to update.\n\n"
    )
    if not assessments:
        lines.append("_No assessments recorded for this article._\n\n")
    else:
        for r in assessments:
            atomic_id = r["atomic_id"]
            loc_parts: list[str] = []
            if r["paragraph"] is not None:
                loc_parts.append(f"¶{r['paragraph']}")
            if r["point"]:
                loc_parts.append(f"({r['point']})")
            if r["sub_point"]:
                loc_parts.append(f"({r['sub_point']})")
            loc = " ".join(loc_parts) or "—"
            text_excerpt = (r["text_excerpt"] or "").strip().replace("\n", " ")
            if len(text_excerpt) > 240:
                text_excerpt = text_excerpt[:237] + "..."

            tr = _parse_testability_rule(r["testability_rule_json"])

            lines.append(f"### `{atomic_id}` — {loc}\n\n")
            lines.append(f"- **Atomic requirement:** {text_excerpt}\n")
            lines.append(f"- **Classification:** `{r['classification']}`\n")
            lines.append(
                f"- **Agent-system relevant:** "
                f"{'yes' if r['agent_system_relevant'] else 'no'}\n"
            )
            if r["applicability_note"]:
                lines.append(f"- **Applicability:** {r['applicability_note']}\n")
            if tr is not None:
                lines.append(f"- **Precondition:** {tr.get('precondition', '—')}\n")
                lines.append(f"- **Stimulus:** {tr.get('stimulus', '—')}\n")
                lines.append(f"- **Observable:** {tr.get('observable', '—')}\n")
                lines.append(f"- **Assertion:** {tr.get('assertion', '—')}\n")
            else:
                lines.append(
                    "- **Testability rule:** _(not applicable — "
                    "classification is not RUNTIME_TESTABLE)_\n"
                )
            if r["notes"]:
                notes = (r["notes"] or "").strip().replace("\n", " ")
                lines.append(f"- **Classifier notes:** {notes}\n")
            lines.append(
                f"- **Review status:** `{r['status']}` "
                f"(classifier: `{r['classifier']}`"
                f"{', reviewer: `' + r['reviewer'] + '`' if r['reviewer'] else ''}"
                f"; updated {r['updated_at']})\n"
            )
            lines.append("\n")

    lines.append(f"{RT_END}\n")
    return "".join(lines)


def _parse_testability_rule(blob) -> dict | None:
    if not blob:
        return None
    import json
    try:
        return json.loads(blob)
    except (ValueError, TypeError):
        return None


def _render_note(
    *,
    bare_n: int,
    title: str,
    text: str,
    assessments: list[sqlite3.Row],
    law: str,
    celex: str,
) -> str:
    """Render the full note content (frontmatter + body)."""
    safe_title = _safe_title(title)
    frontmatter = (
        "---\n"
        f"celex: {celex}\n"
        f"article: {bare_n}\n"
        f"title: {safe_title}\n"
        f"law: {law}\n"
        "---\n\n"
    )
    heading = f"# Article {bare_n} — {safe_title}\n\n"
    rt_section_heading = "## Runtime Testability\n\n"
    return (
        frontmatter
        + heading
        + _render_article_text(text)
        + "\n"
        + rt_section_heading
        + _render_rt_section(assessments)
    )


def _note_filename(bare_n: int, title: str) -> str:
    safe = _filename_safe_title(title)
    return f"Article {bare_n} - {safe}.md"


# ---------------------------------------------------------------------------
# Idempotent note writer
# ---------------------------------------------------------------------------
def _write_note_idempotent(path: Path, new_body: str) -> str:
    """Replace generated blocks in an existing note, preserving human content.

    Strategy:
        - If `path` does not exist, write `new_body` verbatim.
        - Otherwise, locate ARTICLE_TEXT and RUNTIME_TESTABILITY markers.
          Replace the body between each pair. If a marker pair is missing,
          append a new generated block at the end of the file (without
          disturbing content outside the markers).
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_body, encoding="utf-8")
        return "created"

    existing = path.read_text(encoding="utf-8")
    new_at_block = _extract_block(new_body, ARTICLE_TEXT_START, ARTICLE_TEXT_END)
    new_rt_block = _extract_block(new_body, RT_START, RT_END)
    if new_at_block is None or new_rt_block is None:
        raise AssertionError("new_body is missing expected markers")

    updated = _replace_or_append_block(
        existing, ARTICLE_TEXT_START, ARTICLE_TEXT_END, new_at_block
    )
    updated = _replace_or_append_block(
        updated, RT_START, RT_END, new_rt_block
    )
    path.write_text(updated, encoding="utf-8")
    return "updated"


def _extract_block(text: str, start_marker: str, end_marker: str) -> str | None:
    """Return the substring from start_marker through end_marker (inclusive)."""
    s = text.find(start_marker)
    if s == -1:
        return None
    e = text.find(end_marker, s)
    if e == -1:
        return None
    e += len(end_marker)
    return text[s:e]


def _replace_or_append_block(
    text: str, start_marker: str, end_marker: str, new_block: str
) -> str:
    """If `text` contains a start..end marker pair, replace that range.
    Otherwise append `new_block` (with a leading newline) at the end.
    Human-written content outside the markers is preserved.
    """
    s = text.find(start_marker)
    if s == -1:
        # No existing block — append at end with a blank line separator.
        sep = "" if text.endswith("\n") else "\n"
        return text + sep + "\n" + new_block
    e = text.find(end_marker, s)
    if e == -1:
        # Open marker but no close marker — append a fresh block at end
        # so we don't mangle human content.
        sep = "" if text.endswith("\n") else "\n"
        return text + sep + "\n" + new_block
    e += len(end_marker)
    return text[:s] + new_block + text[e:]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def _short_law_name(celex: str, short_name: str | None) -> str:
    """Map a CELEX to the short law name used in frontmatter."""
    if celex == "32024R1689":
        return "EU AI Act"
    if short_name:
        return short_name
    return celex


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--celex", default="32024R1689")
    ap.add_argument(
        "--vault",
        default="/mnt/c/Users/mrcel/Desktop/Obsidian Vaults/EU-AI-Compliance",
        help="Obsidian vault root",
    )
    ap.add_argument(
        "--subdir",
        default="EU AI Act",
        help="Subdirectory under the vault for per-article notes",
    )
    ap.add_argument(
        "--db",
        default=str(PROJECT_ROOT / "data" / "eu_ai_compliance.db"),
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing",
    )
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1
    vault_root = Path(args.vault)
    if not vault_root.exists():
        print(f"Vault root not found: {vault_root}", file=sys.stderr)
        return 1

    conn = _connect(db_path)
    try:
        law_row = conn.execute(
            "SELECT short_name FROM laws WHERE celex = ?", (args.celex,)
        ).fetchone()
        if law_row is None:
            print(f"Law not found in DB: {args.celex}", file=sys.stderr)
            return 1
        articles = _load_articles(conn, args.celex)
        assessments = _load_assessments(conn, args.celex)
    finally:
        conn.close()

    if not articles:
        print(f"No articles found for celex={args.celex}", file=sys.stderr)
        return 1

    law_name = _short_law_name(args.celex, law_row["short_name"])
    article_dir = vault_root / args.subdir

    created = 0
    updated = 0
    missing_assessments: list[int] = []
    for row in articles:
        bare = _bare_article_number(row["article_number"])
        title = row["title"] or f"Article {bare}"
        note_path = article_dir / _note_filename(bare, title)
        rows = assessments.get(bare, [])
        if not rows:
            missing_assessments.append(bare)
        body = _render_note(
            bare_n=bare,
            title=title,
            text=row["text"] or "",
            assessments=rows,
            law=law_name,
            celex=args.celex,
        )
        if args.dry_run:
            print(f"[dry-run] would write {note_path}")
            continue
        result = _write_note_idempotent(note_path, body)
        if result == "created":
            created += 1
        else:
            updated += 1

    print(
        f"vault path: {article_dir}\n"
        f"articles: {len(articles)} "
        f"(created: {created}, updated: {updated})\n"
        f"articles with no assessments: {missing_assessments}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
