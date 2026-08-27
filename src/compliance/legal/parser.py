"""EUR-Lex XHTML parser.

Extracts structured data from an EU act's HTML:
- Title
- Articles (with paragraph structure)
- Recitals (numbered (1), (2), ...)
- Annexes (ANNEX I, ANNEX II, ...)

The HTML has semantic classes we can target:
- .eli-main-title — top-level title
- .oj-doc-ti — official title
- .oj-normal — body paragraph
- p.oj-ti-art — article title
- p.doc-ti — document title
- bold "Article N" — article start
- bold "ANNEX" — annex start
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional


@dataclass
class ParsedRecital:
    number: int
    text: str


@dataclass
class ParsedAnnex:
    code: str  # "I", "II", "A"
    title: str
    raw_text: str = ""


@dataclass
class ParsedArticle:
    article_number: str  # "5"
    full_path: str       # "Article 5" or "Article 5(1)(a)"
    title: Optional[str]
    text: str
    parent_path: Optional[str] = None  # for sub-paragraphs


@dataclass
class ParsedLaw:
    title: str = ""
    short_title: str = ""  # e.g., "Artificial Intelligence Act"
    recitals: list[ParsedRecital] = field(default_factory=list)
    articles: list[ParsedArticle] = field(default_factory=list)
    annexes: list[ParsedAnnex] = field(default_factory=list)


class _StructuredExtractor(HTMLParser):
    """Extract a sequence of (kind, text) blocks from EUR-Lex XHTML.

    Emits:
      - ('main_title', text)        — top-level title
      - ('doc_title', text)         — official long title
      - ('article_marker', text)    — e.g., 'Article 5' (bold)
      - ('article_title', text)     — e.g., 'Subject matter'
      - ('paragraph', text)         — body paragraph (recital or article body)
      - ('annex_marker', text)      — e.g., 'ANNEX I' (bold)
      - ('annex_title', text)       — annex title
    """

    def __init__(self):
        super().__init__()
        self.blocks: list[tuple[str, str]] = []
        self._current_text: list[str] = []
        self._current_kind: str | None = None
        self._in_bold = False
        self._bold_buf: list[str] = []
        # Used to suppress content inside tables (e.g., TOC) at the start
        self._in_table = 0
        # When we see <p class="oj-ti-art">Article N</p>, we don't know at
        # start-tag time whether it's the marker or the title. We use a
        # sentinel kind and let handle_endtag decide based on the text.
        self._pending_oj_ti_art: bool = False

    def handle_starttag(self, tag, attrs):
        attrd = dict(attrs)
        a_class = attrd.get("class", "")

        if tag == "b":
            self._in_bold = True
            self._bold_buf = []
        elif tag == "table":
            self._in_table += 1
        elif tag == "td":
            # Start of a new table cell: clear any pending paragraph state so
            # that the cell content becomes a fresh paragraph block.
            self._current_kind = None
            self._current_text = []
        elif tag in ("p", "div"):
            # EUR-Lex HTML uses two class name formats:
            #   Modern:  oj-ti-art, oj-sti-art, oj-normal, oj-doc-ti
            #   Older:   ti-art, sti-art, normal, ti-section-1
            # Both should map to the same block kinds.
            classes = a_class.split()
            is_subtitle = "oj-sti-art" in classes or "sti-art" in classes
            is_art_marker_or_title = (
                "oj-ti-art" in classes
                or ("ti-art" in classes and not is_subtitle)
                or "ti-section-2" in classes
            )
            is_doc_title = "oj-ti" in classes or "ti-section-1" in classes or "doc-ti" in classes
            is_main_title = "eli-main-title" in classes
            is_annex_title = (
                "oj-annex" in classes
                or "oj-annex-title" in classes
                or any("annex" in c.lower() for c in classes)
            )
            is_paragraph = (
                "oj-normal" in classes
                or "oj-note" in classes
                or a_class == ""
                or "normal" in classes
            )

            if is_art_marker_or_title:
                # The EUR-Lex HTML has two shapes:
                #   1. <p class="oj-ti-art">Article N</p> — the article marker
                #   2. <p class="oj-ti-art">Subject matter</p> — the article title
                # We can't tell which is which at start-tag time without seeing the
                # text, so we default to article_title and let the parser logic in
                # parse_law() split when the text doesn't start with "Article".
                self._current_kind = "article_title_or_marker"
                self._current_text = []
            elif is_doc_title:
                self._current_kind = "doc_title"
                self._current_text = []
            elif is_main_title:
                self._current_kind = "main_title"
                self._current_text = []
            elif is_annex_title:
                self._current_kind = "annex_title"
                self._current_text = []
            elif is_subtitle:
                # Subtitle of the article (e.g., "Human dignity" in Charter)
                self._current_kind = "article_subtitle"
                self._current_text = []
            elif is_paragraph:
                # Body paragraph — always emit, even if we're "in" an article
                self._current_kind = "paragraph"
                self._current_text = []

    def handle_endtag(self, tag):
        if tag == "b":
            bold_text = re.sub(r"\s+", " ", "".join(self._bold_buf)).strip()
            self._in_bold = False
            self._bold_buf = []
            if re.match(r"^Article\s+\d", bold_text):
                self.blocks.append(("article_marker", bold_text))
            elif re.match(r"^ANNEX\s+[IVXL]", bold_text):
                self.blocks.append(("annex_marker", bold_text))

        elif tag == "table":
            self._in_table = max(0, self._in_table - 1)

        elif tag == "p":
            # Emit paragraph block whether inside or outside a table.
            # Recital rows are: <table><tr><td><p>(N)</p></td><td><p>text</p></td></tr>
            if self._current_kind:
                text = re.sub(r"\s+", " ", "".join(self._current_text)).strip()
                if text:
                    # oj-ti-art can be either an article marker or the article
                    # title, depending on whether the text starts with "Article N".
                    if self._current_kind == "article_title_or_marker":
                        if re.match(r"^Article\s+\d", text):
                            self.blocks.append(("article_marker", text))
                        else:
                            self.blocks.append(("article_title", text))
                    else:
                        self.blocks.append((self._current_kind, text))
            self._current_kind = None
            self._current_text = []

    def handle_data(self, data):
        if self._in_bold:
            self._bold_buf.append(data)
        # Allow content from table cells too, but only if it's a paragraph
        # (recital rows). The _in_table flag prevents capturing <table>/<tr>
        # layout markup. We capture oj-normal paragraphs inside tables (which
        # is the recital pattern: <table><tr><td>(N)</td><td>text</td></tr>).
        elif self._current_kind is not None:
            self._current_text.append(data)


def _parse_recital_text(text: str) -> tuple[Optional[int], str]:
    """If text starts with '(N)', return (N, rest). Else (None, text)."""
    m = re.match(r"^\(\s*(\d+)\s*\)", text)
    if m:
        return int(m.group(1)), text[m.end():].strip()
    return None, text


def parse_law(html: str) -> ParsedLaw:
    """Parse EUR-Lex XHTML into a structured ParsedLaw."""
    extractor = _StructuredExtractor()
    extractor.feed(html)

    law = ParsedLaw()
    current_article: Optional[ParsedArticle] = None
    current_annex: Optional[ParsedAnnex] = None
    in_articles_section: bool = False  # becomes True after first "Article N"

    for kind, text in extractor.blocks:
        if kind == "main_title":
            law.title = text
        elif kind == "doc_title":
            if not law.short_title:
                law.short_title = text
        elif kind == "article_marker":
            # Finalise previous article
            if current_article:
                law.articles.append(current_article)
            # New article
            m = re.match(r"^Article\s+(\d+(?:[a-z]+)?)\s*(.*)?$", text, re.IGNORECASE)
            if m:
                article_number = m.group(1)
                title = m.group(2).strip() if m.group(2) else None
                current_article = ParsedArticle(
                    article_number=article_number,
                    full_path=f"Article {article_number}",
                    title=title,
                    text="",
                )
                in_articles_section = True
        elif kind == "article_title":
            if current_article and text.startswith("Article"):
                current_article.title = text
            elif current_article and not current_article.title:
                current_article.title = text
        elif kind == "article_subtitle":
            # Older EUR-Lex format: <p class="sti-art">Subtitle text</p>
            if current_article and not current_article.title:
                current_article.title = text
        elif kind == "paragraph":
            # Recital: appears before any article
            if not in_articles_section:
                recital_num, rest = _parse_recital_text(text)
                if recital_num is not None:
                    # New recital (starts with (N))
                    law.recitals.append(ParsedRecital(number=recital_num, text=rest))
                else:
                    # Continuation of previous recital
                    if law.recitals:
                        law.recitals[-1].text += " " + text
                continue

            # We're in the articles section
            if current_article is not None:
                current_article.text += (" " if current_article.text else "") + text
                _extract_subparagraphs(current_article, text)

        elif kind == "annex_marker":
            if current_annex:
                law.annexes.append(current_annex)
            m = re.match(r"^ANNEX\s+([IVXL]+)", text, re.IGNORECASE)
            if m:
                current_annex = ParsedAnnex(code=m.group(1), title="")
                # Articles end when we hit an annex
                in_articles_section = False
        elif kind == "annex_title":
            if current_annex:
                current_annex.title = text

    # Don't forget the last article/annex
    if current_article:
        law.articles.append(current_article)
    if current_annex:
        law.annexes.append(current_annex)

    return law


def _extract_subparagraphs(article: ParsedArticle, text: str):
    """Detect and record sub-paragraph structure (1)(a)(i) etc."""
    # Pattern: starts with (1), (a), (i), etc.
    m = re.match(r"^\(([\d]+|[a-z]+|[ivxl]+)\)", text.strip())
    if m:
        article.full_path = f"{article.full_path}({m.group(1)})"


def extract_plain_text(html: str) -> str:
    """Simple HTML stripper for plain-text view."""
    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
        def handle_data(self, data):
            self.parts.append(data)

    p = TextExtractor()
    p.feed(html)
    plain = " ".join(p.parts)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 -m src.parser <path-to-html>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        html = f.read()
    parsed = parse_law(html)
    print(f"Title: {parsed.title[:200]}")
    print(f"Short title: {parsed.short_title[:200]}")
    print(f"Recitals: {len(parsed.recitals)}")
    print(f"  First: ({parsed.recitals[0].number}) {parsed.recitals[0].text[:200]}" if parsed.recitals else "  (none)")
    print(f"Articles: {len(parsed.articles)}")
    print(f"  First 5:")
    for a in parsed.articles[:5]:
        print(f"    Article {a.article_number}: {a.full_path}  ({len(a.text)} chars)")
        if a.title:
            print(f"      title: {a.title[:80]}")
    print(f"Annexes: {len(parsed.annexes)}")
    for a in parsed.annexes[:5]:
        print(f"  ANNEX {a.code}: {a.title[:100]}")