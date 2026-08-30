#!/usr/bin/env python3
"""AI Act runtime-testability assessment pipeline.

Walks the AI Act articles in numeric order. For each article:
    1. Read the canonical text from `law_articles`.
    2. Parse the text into atomic obligations (paragraph [+ point]).
    3. Classify each obligation with the runtime-testability heuristic.
    4. Upsert the proposed assessment into `article_runtime_assessments`.
    5. Append a `### Runtime Testability` subsection to the EXISTING
       Obsidian vault note for the law.

This script does NOT build compliance tests. It only produces the
registry of per-article runtime-testability assessments that humans
review.

Usage:
    python3 scripts/article_runtime_pipeline.py --celex 32024R1689 \\
        --from-article 1 --to-article 50 \\
        --vault <path-to-obsidian-vault> \\
        --classifier user:<name> --dry-run

The pipeline is idempotent: re-running it does not duplicate rows or
duplicate the Obsidian subsection (it replaces the previous block).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC))

from legal_text_parser import (  # noqa: E402
    AtomicObligation, ParseError, atomic_id, parse_article,
)
from article_classifier import (  # noqa: E402
    CLASSIFICATIONS, ProposedAssessment, classify_atomic,
    testability_rule_to_json,
)


AI_ACT_CELEX = "32024R1689"

# Marker for the Runtime Testability subsection in the Obsidian note.
RT_SECTION_HEADER = "### Runtime Testability"
RT_SECTION_END = "<!-- /RT -->\n"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _load_ai_act_articles(
    conn: sqlite3.Connection,
    from_article: int,
    to_article: int,
) -> list[sqlite3.Row]:
    """Return AI Act articles in numeric order, filtered to a range.

    The corpus stores `article_number` as the FULL sub-point label
    sequence (e.g. `12(a)(b)(c)(a)(b)(c)(d)`), not just the bare
    number. We extract the leading integer in Python after fetching —
    SQLite cannot cast the labels to integers.
    """
    rows = conn.execute(
        """
        SELECT id, article_number, title, text
        FROM law_articles
        WHERE celex = ?
        ORDER BY id
        """,
        (AI_ACT_CELEX,),
    ).fetchall()

    def _bare(s: str) -> int:
        m = re.match(r"^(\d+)", s)
        return int(m.group(1)) if m else -1

    return [r for r in rows if from_article <= _bare(r["article_number"]) <= to_article]


def _upsert_assessment(
    conn: sqlite3.Connection,
    *,
    celex: str,
    article_number: str,
    aid: str,
    paragraph: Optional[int],
    point: Optional[str],
    sub_point: Optional[str],
    text_excerpt: str,
    full_text_hash: str,
    proposal: ProposedAssessment,
    classifier: str,
    now: str,
) -> None:
    """Insert or update one assessment row.

    UNIQUE (celex, article_number, atomic_id) prevents duplicates. We
    overwrite the existing proposed row when the same key reappears so
    re-running the pipeline reflects classifier changes.
    """
    conn.execute(
        """
        INSERT INTO article_runtime_assessments (
            celex, article_number, atomic_id,
            paragraph, point, sub_point,
            text_excerpt, full_text_hash,
            classification, agent_system_relevant,
            applicability_note, testability_rule_json,
            notes, status, classifier, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (celex, article_number, atomic_id) DO UPDATE SET
            paragraph          = excluded.paragraph,
            point              = excluded.point,
            sub_point          = excluded.sub_point,
            text_excerpt       = excluded.text_excerpt,
            full_text_hash     = excluded.full_text_hash,
            classification     = excluded.classification,
            agent_system_relevant = excluded.agent_system_relevant,
            applicability_note = excluded.applicability_note,
            testability_rule_json = excluded.testability_rule_json,
            notes              = excluded.notes,
            -- status is preserved on re-run; we only flip to
            -- 'needs_review' if the classifier output CHANGED.
            status             = CASE
                WHEN status = 'proposed' THEN 'proposed'
                WHEN classification <> (
                    SELECT classification FROM article_runtime_assessments
                    WHERE celex = article_runtime_assessments.celex
                      AND article_number = article_runtime_assessments.article_number
                      AND atomic_id = article_runtime_assessments.atomic_id
                ) THEN 'needs_review'
                ELSE status
            END,
            updated_at         = excluded.updated_at
        """,
        (
            celex, article_number, aid,
            paragraph, point, sub_point,
            text_excerpt, full_text_hash,
            proposal.classification, int(proposal.agent_system_relevant),
            proposal.applicability_note,
            testability_rule_to_json(proposal.testability_rule),
            proposal.notes,
            "proposed",          # status field on INSERT only
            classifier,
            now, now,
        ),
    )


# ---------------------------------------------------------------------------
# Obsidian helpers
# ---------------------------------------------------------------------------
def _article_section(note_text: str, article_number: int) -> tuple[int, int] | None:
    """Find the (start, end) line offsets of the `## Article N` section.

    Returns the inclusive start line of the `## Article N` header and
    the exclusive end line (the line BEFORE the next `## Article `
    header, or the end of the file). Returns None if not found.
    """
    lines = note_text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^## Article {article_number}\s*$", line):
            start = i
            break
    if start is None:
        return None
    # Find next `## Article ` header.
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^## Article \d+\s*$", lines[j]):
            end = j
            break
    return start, end


def _replace_rt_section(
    note_text: str,
    section_start: int,
    section_end: int,
    new_block: str,
) -> str:
    """Insert/replace the Runtime Testability subsection within an article.

    Idempotent: if a `### Runtime Testability` block already exists
    inside the section, it is replaced. If not, the block is appended
    just before the section end. Legal text above is never modified.
    """
    lines = note_text.splitlines(keepends=True)
    block_lines = new_block.splitlines(keepends=True)
    rt_start, rt_end = None, None
    for i in range(section_start, section_end):
        if lines[i].rstrip("\n") == RT_SECTION_HEADER:
            rt_start = i
            # Walk forward to the end marker.
            for j in range(i + 1, section_end):
                if lines[j].rstrip("\n") == "<!-- /RT -->":
                    rt_end = j + 1
                    break
            break
    if rt_start is not None and rt_end is not None:
        new_lines = lines[:rt_start] + block_lines + lines[rt_end:]
    else:
        # Insert before the last blank line of the section.
        insert_at = section_end
        # Back up over trailing blank lines.
        while insert_at > section_start and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        new_lines = (
            lines[:insert_at]
            + ["\n"]
            + block_lines
            + lines[insert_at:]
        )
    return "".join(new_lines)


def _build_rt_block(
    *,
    article_number: int,
    article_title: str,
    obligations: list[tuple[str, str, AtomicObligation, ProposedAssessment]],
    now: str,
) -> str:
    """Render the Markdown block for one article's Runtime Testability.

    `obligations` is a list of (atomic_id, classification, obl, proposal)
    tuples. The block is appended (or replaced) inside the existing
    article section in the Obsidian note.
    """
    out: list[str] = []
    out.append(f"{RT_SECTION_HEADER}\n\n")
    out.append(
        f"_Proposed runtime-testability classification of every atomic "
        f"obligation in this article. Generated {now}. Status is "
        f"`proposed` until a human reviewer confirms or rejects each row "
        f"in `article_runtime_assessments`._\n\n"
    )
    out.append("| Atomic ID | Paragraph / Point | Classification | Agent-system relevant | Notes |\n")
    out.append("|-----------|--------------------|----------------|------------------------|-------|\n")
    for aid, classification, obl, proposal in obligations:
        loc = f"¶{obl.paragraph}"
        if obl.point:
            loc += f" ({obl.point})"
        if obl.sub_point:
            loc += f" ({obl.sub_point})"
        relevant = "yes" if proposal.agent_system_relevant else "no"
        notes = (proposal.notes or "").replace("\n", " ").replace("|", "\\|")
        out.append(f"| `{aid}` | {loc} | `{classification}` | {relevant} | {notes} |\n")
    out.append("\n")
    out.append(f"{RT_SECTION_END}\n")
    return "".join(out)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def _bare_article_number(article_number: str) -> int:
    """Extract the bare integer article number from the corpus field.

    The corpus stores `article_number` as the FULL sub-point label
    sequence (e.g. `12(a)(b)(c)`). For routing to the right Obsidian
    section we need just the leading integer.
    """
    m = re.match(r"^(\d+)", article_number)
    if not m:
        raise ValueError(f"cannot parse article number: {article_number!r}")
    return int(m.group(1))


def process_article(
    *,
    conn: sqlite3.Connection,
    vault_note: Path,
    row: sqlite3.Row,
    classifier: str,
    dry_run: bool,
    now: str,
) -> dict:
    """Process one article row. Returns a small report dict."""
    article_number_field = row["article_number"]
    bare = _bare_article_number(article_number_field)
    title = row["title"] or ""
    text = row["text"] or ""

    try:
        obligations = parse_article(article_number_field, text)
    except ParseError as exc:
        # Record a single UNCLEAR row so the article still has a
        # registry entry pointing at the human review queue.
        err_aid = f"{bare}.parse_error"
        proposal = ProposedAssessment(
            classification="UNCLEAR",
            agent_system_relevant=True,
            notes=f"Parser could not decompose article: {exc}",
        )
        if not dry_run:
            _upsert_assessment(
                conn,
                celex=AI_ACT_CELEX,
                article_number=article_number_field,
                aid=err_aid,
                paragraph=None,
                point=None,
                sub_point=None,
                text_excerpt=text[:500],
                full_text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                proposal=proposal,
                classifier=classifier,
                now=now,
            )
        proposals = [(err_aid, proposal.classification,
                      AtomicObligation(paragraph=0, point=None, sub_point=None, text=text[:500]),
                      proposal)]
    else:
        proposals: list[tuple[str, str, AtomicObligation, ProposedAssessment]] = []
        seen_aids: set[str] = set()
        for obl in obligations:
            aid = atomic_id(article_number_field, obl)
            # The corpus flattens sub-point labels into the
            # article_number field (e.g. `5(a)(b)(c)(i)(ii)(d)` treats
            # `(i)` `(ii)` and `(d)` as siblings even though `(i)(ii)`
            # are sub-points of `(c)`). The parser therefore produces
            # duplicates within the same article. We disambiguate by
            # appending a sequence suffix so each row has a unique
            # atomic_id. Reviewers can re-categorize the sub-points
            # during the human pass.
            original_aid = aid
            suffix = 2
            while aid in seen_aids:
                aid = f"{original_aid}#{suffix}"
                suffix += 1
            seen_aids.add(aid)

            proposal = classify_atomic(article_title=title, atomic_text=obl.text)
            if proposal.classification not in CLASSIFICATIONS:
                raise AssertionError(
                    f"classifier produced unknown label: {proposal.classification}"
                )
            if aid != original_aid:
                note_suffix = (
                    f" (de-duplicated from {original_aid}; corpus flattens "
                    f"sub-points — re-categorize during review)"
                )
                proposal.notes = (proposal.notes or "") + note_suffix
            full_text_hash = hashlib.sha256(obl.text.encode("utf-8")).hexdigest()
            if not dry_run:
                _upsert_assessment(
                    conn,
                    celex=AI_ACT_CELEX,
                    article_number=article_number_field,
                    aid=aid,
                    paragraph=obl.paragraph,
                    point=obl.point,
                    sub_point=obl.sub_point,
                    text_excerpt=obl.text,
                    full_text_hash=full_text_hash,
                    proposal=proposal,
                    classifier=classifier,
                    now=now,
                )
            proposals.append((aid, proposal.classification, obl, proposal))

    # Obsidian note append.
    if not dry_run and vault_note.exists():
        note_text = vault_note.read_text(encoding="utf-8")
        section = _article_section(note_text, bare)
        if section is None:
            obs_status = "note_section_missing"
        else:
            rt_block = _build_rt_block(
                article_number=bare,
                article_title=title,
                obligations=proposals,
                now=now,
            )
            new_text = _replace_rt_section(note_text, section[0], section[1], rt_block)
            vault_note.write_text(new_text, encoding="utf-8")
            obs_status = "appended"
    elif dry_run:
        obs_status = "dry_run_skip"
    else:
        obs_status = "vault_note_missing"

    return {
        "article_id": row["id"],
        "article_number": bare,
        "title": title,
        "status": "ok",
        "obs_status": obs_status,
        "obligations": [
            {
                "atomic_id": aid,
                "paragraph": obl.paragraph,
                "point": obl.point,
                "sub_point": obl.sub_point,
                "classification": classification,
            }
            for aid, classification, obl, _ in proposals
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--celex", default=AI_ACT_CELEX)
    ap.add_argument("--from-article", type=int, default=1)
    ap.add_argument("--to-article", type=int, default=50)
    ap.add_argument(
        "--vault",
        default=os.environ.get(
            "OBSIDIAN_VAULT_PATH",
            "<set OBSIDIAN_VAULT_PATH to your local Obsidian vault>",
        ),
        help="Obsidian vault root. The note is expected at "
             "<vault>/<celex> - <short_name>.md. "
             "Or set OBSIDIAN_VAULT_PATH env var.",
    )
    ap.add_argument(
        "--note-name",
        default=None,
        help="Override the note filename (default: derived from laws table)",
    )
    ap.add_argument("--classifier", default="user:marcelo")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute proposals but do NOT write to DB or vault.",
    )
    ap.add_argument(
        "--db",
        default=str(PROJECT_ROOT / "data" / "eu_ai_compliance.db"),
    )
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    # Determine note filename from laws.short_name.
    conn = _connect(db_path)
    try:
        law = conn.execute(
            "SELECT short_name, long_name FROM laws WHERE celex = ?",
            (args.celex,),
        ).fetchone()
        if law is None:
            print(f"law not found: {args.celex}", file=sys.stderr)
            return 1
        note_name = args.note_name or f"{args.celex} - {law['short_name']}.md"
        vault_note = Path(args.vault) / note_name
        if not vault_note.exists() and not args.dry_run:
            print(f"vault note not found: {vault_note}", file=sys.stderr)
            print("(pass --dry-run to compute without writing)", file=sys.stderr)
            return 1

        rows = _load_ai_act_articles(conn, args.from_article, args.to_article)
        if not rows:
            print(
                f"no AI Act articles found in range "
                f"[{args.from_article}, {args.to_article}]",
                file=sys.stderr,
            )
            return 1

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        report: list[dict] = []
        for row in rows:
            report.append(
                process_article(
                    conn=conn,
                    vault_note=vault_note,
                    row=row,
                    classifier=args.classifier,
                    dry_run=args.dry_run,
                    now=now,
                )
            )

        if not args.dry_run:
            conn.commit()
    finally:
        conn.close()

    # Console summary.
    total_articles = len(report)
    total_obligations = sum(len(r["obligations"]) for r in report)
    parse_errors = [r for r in report if r["status"] == "parse_error"]
    print(
        f"processed {total_articles} article(s); "
        f"generated {total_obligations} atomic obligation assessment(s); "
        f"parse errors: {len(parse_errors)}; "
        f"dry_run={args.dry_run}"
    )
    if parse_errors:
        for r in parse_errors:
            print(f"  parse error on article {r['article_number']}: {r['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
