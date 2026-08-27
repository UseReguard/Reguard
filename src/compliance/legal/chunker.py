"""Chunk law text into RAG-ready segments.

Strategy: Article-paragraph level granularity.
- Each Article → 1+ chunks (one per top-level paragraph)
- Each Recital → 1 chunk
- Each Annex → 1 chunk (full text)

Output: list[dict] with location, text, char_count.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .parser import ParsedLaw, ParsedArticle, ParsedRecital, ParsedAnnex


@dataclass
class Chunk:
    idx: int
    chunk_kind: str          # 'recital', 'article_paragraph', 'annex'
    location: str           # 'Art. 5(1)' or 'Recital 3' or 'Annex III'
    full_text: str
    char_count: int

    def to_dict(self) -> dict:
        return {
            "idx": self.idx,
            "chunk_kind": self.chunk_kind,
            "location": self.location,
            "full_text": self.full_text,
            "char_count": self.char_count,
        }


def chunk_law(parsed: "ParsedLaw") -> list[Chunk]:
    """Convert a ParsedLaw into a list of chunks."""
    chunks: list[Chunk] = []
    idx = 0

    # 1. Recitals (each one is a chunk)
    for recital in parsed.recitals:
        text = recital.text.strip()
        if not text:
            continue
        chunks.append(Chunk(
            idx=idx,
            chunk_kind="recital",
            location=f"Recital {recital.number}",
            full_text=f"Recital {recital.number}: {text}",
            char_count=len(text) + 20,
        ))
        idx += 1

    # 2. Articles — split into paragraphs
    # Pattern: "(N)" or "(a)" or "(i)" at start of a chunk
    for article in parsed.articles:
        title_str = f"Article {article.article_number}" + (f" — {article.title}" if article.title else "")
        # Split by paragraph markers
        paragraphs = _split_article_paragraphs(article.text)
        for sub_path, sub_text in paragraphs:
            if not sub_text.strip():
                continue
            full_text = f"{title_str}\n{sub_text.strip()}"
            location = f"Art. {article.article_number}"
            if sub_path:
                location = f"{location}({sub_path})"
            chunks.append(Chunk(
                idx=idx,
                chunk_kind="article_paragraph",
                location=location,
                full_text=full_text,
                char_count=len(full_text),
            ))
            idx += 1

        # If article has no sub-paragraphs (single chunk), still add it
        if not paragraphs and article.text.strip():
            full_text = f"{title_str}\n{article.text.strip()}"
            chunks.append(Chunk(
                idx=idx,
                chunk_kind="article_paragraph",
                location=f"Art. {article.article_number}",
                full_text=full_text,
                char_count=len(full_text),
            ))
            idx += 1

    # 3. Annexes — each is one chunk (full text)
    for annex in parsed.annexes:
        text = annex.raw_text.strip() if annex.raw_text else annex.title
        if not text:
            continue
        full_text = f"ANNEX {annex.code} — {annex.title}\n{text}"
        chunks.append(Chunk(
            idx=idx,
            chunk_kind="annex",
            location=f"Annex {annex.code}",
            full_text=full_text,
            char_count=len(full_text),
        ))
        idx += 1

    return chunks


def _split_article_paragraphs(text: str) -> list[tuple[str, str]]:
    """Split article text into (sub_path, sub_text) pairs.

    A 'paragraph' here is a numbered sub-paragraph like (1), (a), (i).
    If the article has no such markers, returns [('', full_text)].

    Sub-paragraphs can nest — (1)(a)(i). We capture the full chain.
    """
    text = text.strip()
    if not text:
        return []

    # Find all positions of paragraph markers in the text
    # Markers can be: (N), (a-z), (i-roman)
    # Note: regex requires alternation order — longer patterns first
    marker_pattern = re.compile(
        r"\(\s*(\d+|[a-z]+|[ivxl]+|[IVXL]+)\s*\)(?=\s+[A-Za-z])"
    )
    matches = list(marker_pattern.finditer(text))

    if not matches:
        # No sub-paragraphs — single chunk
        return [("", text)]

    # If the first match isn't at position 0, prepend a "preamble" segment
    segments: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # Build cumulative sub-path
        sub_path = "".join(
            f"({matches[j].group(1)})" for j in range(i + 1)
        )
        segment_text = text[start:end].strip()
        # Remove the leading marker from the text (it's in the path)
        segment_text = re.sub(r"^\(\s*[\w]+\s*\)\s*", "", segment_text, count=1).strip()
        segments.append((sub_path, segment_text))

    # Add preamble if exists
    if matches[0].start() > 0:
        preamble = text[:matches[0].start()].strip()
        if preamble:
            segments.insert(0, ("", preamble))

    return segments


if __name__ == "__main__":
    # Test on AI Act
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 -m src.chunker <path-to-html>")
        sys.exit(1)
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from compliance.legal.parser import parse_law

    with open(sys.argv[1], encoding="utf-8") as f:
        html = f.read()
    parsed = parse_law(html)
    chunks = chunk_law(parsed)
    print(f"Total chunks: {len(chunks)}")
    print(f"Recital chunks: {sum(1 for c in chunks if c.chunk_kind == 'recital')}")
    print(f"Article chunks: {sum(1 for c in chunks if c.chunk_kind == 'article_paragraph')}")
    print(f"Annex chunks: {sum(1 for c in chunks if c.chunk_kind == 'annex')}")
    print()
    print("First 5 chunks:")
    for c in chunks[:5]:
        print(f"  [{c.idx}] {c.chunk_kind:20s} {c.location:20s} ({c.char_count:5d} chars)")
        print(f"      {c.full_text[:200]}...")
    print()
    print("Article 5 chunks (sample):")
    for c in chunks:
        if c.location.startswith("Art. 5("):
            print(f"  {c.location}  ({c.char_count} chars)")