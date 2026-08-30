"""Smoke tests for the legal-text parser.

Validates the deterministic decomposition against AI Act Article 12
text stored as a text fixture in this repository.

The fixture files live under ``tests/fixtures/legal/`` so the test
suite is self-contained on a clean checkout and does not require the
research corpus database (which is gitignored).

Note on article identification:
    The fixture text is the verbatim Article 12 (and Article 9)
    provision from Regulation (EU) 2024/1689 (the AI Act). Paragraph
    numbering is preserved exactly as published; sub-point labels are
    ``(a)``, ``(b)``, ``(c)``, ``(d)``.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from compliance.requirements.legal_text_parser import (
    AtomicObligation, atomic_id, parse_article,
    split_paragraphs, split_points,
)


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "legal"


def _load_article_text(article_id: int) -> str:
    """Read the article text from a local text fixture.

    The fixture is the verbatim Regulation (EU) 2024/1689 text for
    the article; it does NOT require the gitignored research corpus
    database and so works on a clean runner.
    """
    path = FIXTURES_DIR / f"eu_ai_act_article_{article_id}.txt"
    if not path.exists():
        raise AssertionError(
            f"missing legal text fixture: {path}. "
            "tests/fixtures/legal/ must contain the AI Act text "
            "snapshots used by these tests."
        )
    return path.read_text(encoding="utf-8")


def test_split_paragraphs_article_12_returns_three_paragraphs():
    text = _load_article_text(12)
    paragraphs = split_paragraphs(text)
    assert [n for n, _ in paragraphs] == [1, 2, 3]


def test_split_points_article_12_paragraph_1_returns_one_obligation():
    text = _load_article_text(12)
    para1 = next(b for n, b in split_paragraphs(text) if n == 1)
    obs = split_points(1, para1)
    assert len(obs) == 1
    assert obs[0].point is None
    assert "automatic recording of events" in obs[0].text


def test_split_points_article_12_paragraph_2_returns_three_points():
    text = _load_article_text(12)
    para2 = next(b for n, b in split_paragraphs(text) if n == 2)
    obs = split_points(2, para2)
    assert len(obs) == 3
    assert [o.point for o in obs] == ["a", "b", "c"]
    # First point absorbs the introductory lead-in.
    assert "logging capabilities shall enable" in obs[0].text
    assert "identifying situations" in obs[0].text


def test_split_points_article_12_paragraph_3_returns_four_points():
    text = _load_article_text(12)
    para3 = next(b for n, b in split_paragraphs(text) if n == 3)
    obs = split_points(3, para3)
    assert len(obs) == 4
    assert [o.point for o in obs] == ["a", "b", "c", "d"]
    # The biometric-only provision (d) refers to Article 14(5) — the
    # parser must not have split on `14(5)`.
    assert "identification of the natural persons" in obs[3].text
    assert "Article 14(5)" in obs[3].text


def test_parse_article_12_returns_eight_atomic_obligations():
    text = _load_article_text(12)
    obligations = parse_article("12", text)
    # paragraph 1 (1 obligation) + paragraph 2 (a,b,c) (3) +
    # paragraph 3 (a,b,c,d) (4) = 8 obligations.
    assert len(obligations) == 8


def test_atomic_id_format():
    obs = [
        AtomicObligation(paragraph=1, point=None, sub_point=None, text="x"),
        AtomicObligation(paragraph=2, point="a", sub_point=None, text="x"),
        AtomicObligation(paragraph=3, point="d", sub_point=None, text="x"),
    ]
    assert atomic_id("12", obs[0]) == "12.1"
    assert atomic_id("12", obs[1]) == "12.2.a"
    assert atomic_id("12", obs[2]) == "12.3.d"


def test_parse_article_9_risk_management():
    """Article 9 has 10 paragraphs. Spot-check the parser on it."""
    text = _load_article_text(9)
    obligations = parse_article("9", text)
    para_numbers = sorted({o.paragraph for o in obligations})
    assert para_numbers == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    p2_points = [o.point for o in obligations if o.paragraph == 2]
    assert p2_points == ["a", "b", "c", "d"]
    p5_points = [o.point for o in obligations if o.paragraph == 5]
    assert p5_points == ["a", "b", "c"]


def test_legal_text_fixtures_are_present():
    """The fixtures must be tracked in the repo so a clean checkout
    can run the parser tests offline."""
    assert (FIXTURES_DIR / "eu_ai_act_article_9.txt").exists()
    assert (FIXTURES_DIR / "eu_ai_act_article_12.txt").exists()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
