"""Demonstrate the full pipeline works on a synthetic HTML file.

This proves the parser, chunker, and database import all work correctly,
even though EUR-Lex is currently WAF-blocked.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Synthetic minimal AI Act HTML
SYNTHETIC_HTML = """<!DOCTYPE html>
<html lang="en">
<body>
<div class="eli-main-title">REGULATION (EU) 2024/1689 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL</div>
<p class="oj-doc-ti">laying down harmonised rules on artificial intelligence (Artificial Intelligence Act)</p>
<p class="oj-normal">(1) The purpose of this Regulation is to improve the functioning of the internal market by laying down a uniform legal framework for the development, the placing on the market, the putting into service and the use of artificial intelligence systems (AI systems) in the Union.</p>
<p class="oj-normal">(2) This Regulation should be applied in accordance with the values of the Union enshrined in the Charter, facilitating the protection of natural persons, undertakings, democracy, the rule of law and environmental protection, while boosting innovation and employment.</p>
<p class="oj-normal">(3) AI systems can be easily deployed in a large variety of sectors and parts of the Union, including cross-border, and easily circulate throughout the Union.</p>
<b>Article 1</b>
<p class="oj-ti-art">Subject matter</p>
<p class="oj-normal">1. The purpose of this Regulation is to improve the functioning of the internal market and promote the uptake of human-centric and trustworthy artificial intelligence (AI), while ensuring a high level of protection of health, safety, fundamental rights.</p>
<p class="oj-normal">2. This Regulation lays down: (a) harmonised rules for the placing on the market, putting into service, and use of AI systems; (b) prohibitions of certain AI practices; (c) specific requirements for high-risk AI systems; (d) transparency obligations for providers and deployers of certain AI systems.</p>
<b>Article 2</b>
<p class="oj-ti-art">Definitions</p>
<p class="oj-normal">For the purposes of this Regulation, the following definitions apply: (1) 'AI system' means a machine-based system that is designed to operate with varying levels of autonomy and that may exhibit adaptiveness after deployment.</p>
<b>Article 5</b>
<p class="oj-ti-art">Prohibited AI practices</p>
<p class="oj-normal">1. The following AI practices shall be prohibited: (a) the placing on the market, the putting into service or the use of an AI system that employs subliminal techniques beyond a person's consciousness; (b) the placing on the market, the putting into service or the use of an AI system that exploits any of the vulnerabilities of natural persons.</p>
<b>ANNEX I</b>
<p class="oj-annex-title">List of Union harmonisation legislation</p>
<p class="oj-normal">Section A. List of Union harmonisation legislation based on the New Legislative Framework</p>
<p class="oj-normal">1. Directive 2014/35/EU (low voltage)</p>
<p class="oj-normal">2. Directive 2014/30/EU (electromagnetic compatibility)</p>
<b>ANNEX III</b>
<p class="oj-annex-title">High-risk AI systems referred to in Article 6(2)</p>
<p class="oj-normal">High-risk AI systems pursuant to Article 6(2) are the AI systems listed in any of the following areas:</p>
<p class="oj-normal">(a) Biometrics, to the extent that their use is permitted under relevant Union or national law.</p>
</body>
</html>"""


def main():
    from compliance.db import init_db, session_scope
    from compliance.legal.parser import parse_law
    from compliance.legal.chunker import chunk_law
    from compliance.models import Law, LawArticle, LawRecital, LawAnnex, LawChunk, ReviewAction
    from compliance.legal.catalog import CANONICAL_LAWS

    print("=== Pipeline test on synthetic AI Act HTML ===\n")

    # 1. Parse
    print("1. Parsing...")
    parsed = parse_law(SYNTHETIC_HTML)
    print(f"   Title: {parsed.title[:80]}")
    print(f"   Short title: {parsed.short_title[:80]}")
    print(f"   Recitals: {len(parsed.recitals)}")
    for r in parsed.recitals:
        print(f"     ({r.number}) {r.text[:80]}...")
    print(f"   Articles: {len(parsed.articles)}")
    for a in parsed.articles:
        print(f"     Article {a.article_number} ({a.full_path}): {len(a.text)} chars")
    print(f"   Annexes: {len(parsed.annexes)}")
    for ax in parsed.annexes:
        print(f"     ANNEX {ax.code}: {ax.title[:60]}")

    # 2. Chunk
    print("\n2. Chunking...")
    chunks = chunk_law(parsed)
    print(f"   Total chunks: {len(chunks)}")
    for c in chunks[:8]:
        print(f"   [{c.idx}] {c.chunk_kind:20s} {c.location:20s} ({c.char_count:5d} chars)")
        print(f"        {c.full_text[:120]}...")

    # 3. Init + insert
    print("\n3. Initializing database and inserting...")
    init_db()
    celex = "32024R1689"
    entry = next(e for e in CANONICAL_LAWS if e["celex"] == celex)
    with session_scope() as s:
        law = Law(
            celex=celex,
            slug=entry["slug"],
            tier=entry["tier"],
            short_name=entry["short_name"],
            long_name=entry["long_name"],
            source_url=f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}",
            raw_html_path="data/raw/32024R1689.html",
            in_scope=True,
        )
        s.add(law)
        s.flush()

        for r in parsed.recitals:
            if r.text.strip():
                s.add(LawRecital(celex=celex, number=r.number, text=r.text.strip()))
        for a in parsed.articles:
            if a.text.strip():
                s.add(LawArticle(
                    celex=celex, article_number=a.article_number,
                    title=a.title, full_path=a.full_path, text=a.text.strip()
                ))
        for ax in parsed.annexes:
            s.add(LawAnnex(celex=celex, code=ax.code, title=ax.title, raw_text=ax.title))

        for c in chunks:
            s.add(LawChunk(
                celex=celex, idx=c.idx, chunk_kind=c.chunk_kind,
                location=c.location, full_text=c.full_text, char_count=c.char_count
            ))

        s.add(ReviewAction(
            celex=celex, action="ingested", tier=entry["tier"],
            short_name=entry["short_name"], reason="Synthetic test import", actor="test_script"
        ))

    # 4. Verify
    print("\n4. Verifying...")
    with session_scope() as s:
        from sqlalchemy import select
        n_articles = s.execute(select(LawArticle).where(LawArticle.celex == celex)).all()
        n_recitals = s.execute(select(LawRecital).where(LawRecital.celex == celex)).all()
        n_annexes = s.execute(select(LawAnnex).where(LawAnnex.celex == celex)).all()
        n_chunks = s.execute(select(LawChunk).where(LawChunk.celex == celex)).all()
        print(f"   Articles:  {len(n_articles)}")
        print(f"   Recitals:  {len(n_recitals)}")
        print(f"   Annexes:   {len(n_annexes)}")
        print(f"   Chunks:    {len(n_chunks)}")

    print("\n=== Pipeline works end-to-end ===")


if __name__ == "__main__":
    main()