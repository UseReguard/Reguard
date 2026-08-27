"""Verify the import: count laws, articles, recitals, chunks. Show samples."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from compliance.db import init_db, session_scope
from compliance.models import Law, LawArticle, LawRecital, LawAnnex, LawChunk, DiscoveryCandidate


def main():
    init_db()
    with session_scope() as s:
        laws = s.query(Law).all()
        print(f"Laws: {len(laws)}")
        print(f"  Tier 1 (Core): {sum(1 for l in laws if l.tier == 1)}")
        print(f"  Tier 2: {sum(1 for l in laws if l.tier == 2)}")
        print(f"  Tier 3: {sum(1 for l in laws if l.tier == 3)}")
        print(f"  Tier 4: {sum(1 for l in laws if l.tier == 4)}")

        n_articles = s.query(LawArticle).count()
        n_recitals = s.query(LawRecital).count()
        n_annexes = s.query(LawAnnex).count()
        n_chunks = s.query(LawChunk).count()
        n_candidates = s.query(DiscoveryCandidate).count()

        print(f"\nStructural content:")
        print(f"  Articles:  {n_articles}")
        print(f"  Recitals:  {n_recitals}")
        print(f"  Annexes:   {n_annexes}")
        print(f"  Chunks:    {n_chunks}")
        print(f"  Discovery candidates: {n_candidates}")

        print(f"\nLargest laws by chunk count:")
        ranked = sorted(laws, key=lambda l: s.query(LawChunk).filter(LawChunk.celex == l.celex).count(), reverse=True)
        for l in ranked[:10]:
            n_c = s.query(LawChunk).filter(LawChunk.celex == l.celex).count()
            n_a = s.query(LawArticle).filter(LawArticle.celex == l.celex).count()
            n_r = s.query(LawRecital).filter(LawRecital.celex == l.celex).count()
            print(f"  {l.celex:<14} T{l.tier}  {n_chunks:3d} chunks  ({n_a} articles, {n_r} recitals) — {l.short_name[:40]}")

        print(f"\nSample chunks from AI Act:")
        for c in s.query(LawChunk).filter(LawChunk.celex == "32024R1689").order_by(LawChunk.idx).limit(5).all():
            print(f"  [{c.idx}] {c.chunk_kind:20s} {c.location:25s} ({c.char_count} chars)")
            print(f"      {c.full_text[:150]}...")


if __name__ == "__main__":
    main()