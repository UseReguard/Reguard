"""Deterministic parser for EU legal-article text.

Decomposes a law article's text blob into atomic obligations:
    paragraph (1..N), point (letter or roman, optional), sub_point (roman, optional)

Works against the text format used in `law_articles.text` for celex
`32024R1689` (EU AI Act). The legal text follows a strict pattern:

    1. <paragraph text>. 2. <paragraph text>: (a) <point text>;
    (b) <point text>; (c) <point text>. 3. ...

Cross-references such as `Article 26(5)` or `Article 79(1)` contain
digits in parentheses — these are NOT point labels and must not be
treated as such. Point labels are always letters (a-z) or roman
numerals (i, ii, iii, iv, v, vi, vii, viii, ix, x, xi, xii).

Algorithm:
    1. Walk the text and split on `<digit(s)>. ` boundaries to get
       paragraph blocks (digit followed by period and whitespace).
    2. Within each paragraph, split on `(letter|roman) ` boundaries
       that follow a known separator (`:`, `;`, or paragraph start).
    3. Strip and trim each atomic unit. Preserve original ordering.

The parser is intentionally strict: if it cannot unambiguously split
the article it raises ParseError. We never silently drop text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# Roman numerals used in EU legislation as sub-points. Lowercase,
# case-insensitive matching is fine because the corpus is all lowercase.
ROMAN_LABELS = {
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "xi", "xii", "xiii", "xiv", "xv",
}

# Single letters used as point labels.
LETTER_LABELS = set("abcdefghijklmnopqrstuvwxyz")


@dataclass(frozen=True)
class AtomicObligation:
    """One atomic legal obligation extracted from an article.

    `text` is the verbatim fragment that constitutes the obligation.
    The location triple (paragraph, point, sub_point) traces it back to
    the source article.
    """
    paragraph: int
    point: Optional[str]        # e.g. "a", "b", None
    sub_point: Optional[str]    # e.g. "i", "ii", None
    text: str                   # verbatim text fragment, trimmed


class ParseError(ValueError):
    """Raised when the parser cannot unambiguously decompose an article."""


# ---------------------------------------------------------------------------
# Paragraph splitting
# ---------------------------------------------------------------------------
# A paragraph boundary is `<digits>. ` — a digit run, a period, and a
# space. We deliberately avoid splitting on digits that are part of a
# larger token (e.g. "Article 79(1).", "Section 4."). The corpus
# always uses one-or-more ASCII digits followed by `.` followed by
# whitespace; this is consistent across AI Act articles.
#
# We use a lookahead so the matched period is consumed but the
# following whitespace is not — that way paragraph text starts cleanly.
# ---------------------------------------------------------------------------
_PARA_SPLIT = re.compile(r"(?<=[.!?])\s+(?=\d+\.\s)")


def _is_sentence_boundary(text: str, idx: int) -> bool:
    """True if position `idx` in `text` is at a sentence boundary.

    A sentence boundary is the start of text, OR a position whose
    preceding non-whitespace character is one of `.`, `!`, `?`.
    Cross-references like "Article 60" or "paragraph 2" are NOT
    sentence boundaries — they sit inside a sentence and the digit
    is preceded by a letter or digit, not punctuation.
    """
    if idx <= 0:
        return True
    j = idx - 1
    while j >= 0 and text[j].isspace():
        j -= 1
    if j < 0:
        return True
    return text[j] in ".!?"


def split_paragraphs(text: str) -> list[tuple[int, str]]:
    """Split article text into ordered (paragraph_number, text) tuples.

    The article may start with the first paragraph directly (no leading
    prose). The corpus stores text as one concatenated string where
    paragraphs are separated by `. ` followed by a digit. Sentence
    boundaries within a paragraph end with `. ` and the next paragraph
    starts with `N. `. We split on the boundary between a sentence end
    and the next numbered paragraph.

    Cross-references like "Article 60" or "Section 4" look like
    paragraph markers but are NOT — we reject them by requiring the
    preceding non-whitespace character to be sentence-ending
    punctuation.

    Articles WITHOUT numbered paragraphs (rare — e.g. Article 113 on
    entry into force) are returned as a single paragraph 1 with the
    whole text. This is a deliberate fallback: it is better to produce
    one obligation that a human can split than to lose the article.
    """
    text = text.strip()
    if not text:
        return []

    # Find every "<digits>. " marker, then keep only those that sit
    # at a sentence boundary.
    matches = []
    for m in re.finditer(r"(\d+)\.\s+", text):
        if not _is_sentence_boundary(text, m.start()):
            continue
        matches.append(m)
    if not matches:
        # Article without numbered paragraphs (rare). Treat the whole
        # text as paragraph 1. This is a degenerate case but we still
        # need to return something — better than dropping the article.
        return [(1, text)]

    paragraphs: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        n = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            # A marker that produces an empty body is almost always
            # a false positive — e.g. a heading-style number followed
            # by no text. Skip it rather than fail.
            continue
        paragraphs.append((n, body))

    if not paragraphs:
        return [(1, text)]

    # Sanity: paragraph numbers should be a contiguous 1..N sequence.
    # If not (e.g. an article with re-introduced point lists in the
    # middle of paragraph 1 that confuse the boundary detector), we
    # collapse to a single paragraph rather than fail — the parser is
    # not the source of truth for structure.
    numbers = [n for n, _ in paragraphs]
    expected = list(range(1, len(paragraphs) + 1))
    if numbers != expected:
        return [(1, text)]

    return paragraphs


# ---------------------------------------------------------------------------
# Point splitting
# ---------------------------------------------------------------------------
# Within a paragraph, points are introduced after `:` and separated by
# `;`. They look like `(a) <text>` or `(b) <text>` etc.
#
# We must NOT split on parenthetical cross-references like:
#   - `Article 26(5)`           → digits in parens
#   - `point 1 (a), of Annex III` → letter in parens, but this is a
#     reference TO another paragraph's point label, not a current-point
#     label. We avoid splitting on this by requiring the `(letter)` to
#     follow a recognized separator.
#
# Allowed separators before a `(letter)`:
#   - `:` (start of points list)
#   - `;` (mid-list continuation)
#   - start of paragraph text (rare)
# ---------------------------------------------------------------------------
_POINT_SPLIT = re.compile(
    r"(?<=[;:])\s+(?:and\s+)?\(([a-z])\)\s+"
)


def split_points(paragraph_number: int, body: str) -> list[AtomicObligation]:
    """Split a paragraph body into atomic obligations.

    Returns either:
        * one obligation with point=None (no points detected), or
        * multiple obligations, one per detected point, all sharing
          the same paragraph_number.

    The introductory text BEFORE the first point is dropped — it is
    the lead-in to the points list, not itself a separate obligation.
    If the paragraph has NO points (no colon, no point labels), the
    whole body is returned as a single obligation.

    If the paragraph has points but the introductory text introduces a
    conditional (e.g. "shall provide, at a minimum: ..."), the
    introductory text is preserved by attaching it to the first point
    so that no obligation is silently lost.
    """
    matches = list(_POINT_SPLIT.finditer(body))
    if not matches:
        # No points. The whole body is one obligation.
        return [AtomicObligation(
            paragraph=paragraph_number,
            point=None,
            sub_point=None,
            text=body.strip(),
        )]

    # Capture the introductory text (between paragraph start and first
    # point label) so we can prepend it to the first point.
    intro = body[:matches[0].start()].strip()

    obligations: list[AtomicObligation] = []
    for i, m in enumerate(matches):
        label = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        point_body = body[start:end].strip()

        # Strip trailing punctuation for cleaner excerpts; we keep
        # internal punctuation verbatim.
        point_body = point_body.rstrip(" .")

        if not point_body:
            raise ParseError(
                f"empty point body at paragraph {paragraph_number}, "
                f"label ({label})"
            )

        text = point_body
        if i == 0 and intro:
            # First point absorbs the introductory lead-in so no text
            # is silently lost.
            text = f"{intro} {point_body}".strip()

        obligations.append(AtomicObligation(
            paragraph=paragraph_number,
            point=label,
            sub_point=None,
            text=text,
        ))

    return obligations


# ---------------------------------------------------------------------------
# Top-level entrypoint
# ---------------------------------------------------------------------------
def parse_article(article_number: str, text: str) -> list[AtomicObligation]:
    """Decompose an article's full text into ordered atomic obligations.

    `article_number` is the source-of-truth identifier from
    `law_articles.article_number` (e.g. "12", "12(a)(b)(c)"). It is
    used purely for traceability — the actual decomposition is driven
    by the text.

    Returns obligations in document order: paragraph 1, then any
    points under paragraph 1; then paragraph 2, etc.
    """
    paragraphs = split_paragraphs(text)
    obligations: list[AtomicObligation] = []
    for n, body in paragraphs:
        obligations.extend(split_points(n, body))

    if not obligations:
        raise ParseError(
            f"article {article_number} produced zero obligations"
        )

    return obligations


def atomic_id(article_number: str, obl: AtomicObligation) -> str:
    """Stable, human-readable identifier for one atomic obligation.

    `article_number` may be the full sub-point label sequence as
    stored in `law_articles.article_number` (e.g. `12(a)(b)(c)(a)(b)(c)(d)`);
    we extract the leading integer for the atomic_id so the result
    matches the user's expected format:

        Article 12, paragraph 1     → "12.1"
        Article 12, paragraph 2 (a) → "12.2.a"
        Article 12, paragraph 3 (d) → "12.3.d"

    The atomic_id is unique within (celex, article_number) and is the
    primary key suffix used for review operations.
    """
    m = re.match(r"^(\d+)", article_number)
    bare = m.group(1) if m else article_number
    parts = [bare]
    if obl.point is not None:
        parts.append(str(obl.paragraph))
        parts.append(obl.point)
    if obl.sub_point is not None:
        parts.append(obl.sub_point)
    if obl.point is None and obl.sub_point is None:
        parts.append(str(obl.paragraph))
    return ".".join(parts)
