"""ORM models for the EU AI Compliance law database.

Schema is PostgreSQL-compatible. When migrating to PostgreSQL + pgvector:
- Replace `Text` fields that need full-text search with `tsvector` columns
- Add `vector(1536)` columns for embeddings (use pgvector)
- The relationships and indexes work as-is.

Entities:
- Law: a binding EU act (one row per CELEX)
- LawArticle: an Article with its paragraphs/sub-points
- LawRecital: a numbered recital
- LawAnnex: an Annex with its title
- LawChunk: a chunk of text ready for RAG search
- DiscoveryCandidate: candidate laws from RSS/CELLAR discovery (audit trail)
- ReviewAction: log of accept/reject decisions on candidates
- AgentRepository: a curated GitHub repository URL (Python AI-agent corpus)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Integer, Text, Boolean, Date, DateTime, ForeignKey,
    Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from compliance.db import Base


class Law(Base):
    """A binding EU act — one row per CELEX."""
    __tablename__ = "laws"

    celex: Mapped[str] = mapped_column(String(20), primary_key=True)
    slug: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    tier: Mapped[Optional[int]] = mapped_column(Integer, index=True)  # 1, 2, 3, 4
    short_name: Mapped[str] = mapped_column(String(200))
    long_name: Mapped[str] = mapped_column(Text)
    document_date: Mapped[Optional[date]] = mapped_column(Date)
    in_force: Mapped[Optional[bool]] = mapped_column(Boolean)
    work_uri: Mapped[Optional[str]] = mapped_column(String(500))
    source_url: Mapped[Optional[str]] = mapped_column(String(500))  # EUR-Lex URL
    raw_html_path: Mapped[Optional[str]] = mapped_column(String(500))  # data/raw/{celex}.html
    in_scope: Mapped[bool] = mapped_column(Boolean, default=True)
    parent_celex: Mapped[Optional[str]] = mapped_column(String(20), index=True)  # for implementing regs
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    added_by: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    articles: Mapped[list["LawArticle"]] = relationship(
        back_populates="law", cascade="all, delete-orphan"
    )
    recitals: Mapped[list["LawRecital"]] = relationship(
        back_populates="law", cascade="all, delete-orphan", order_by="LawRecital.number"
    )
    annexes: Mapped[list["LawAnnex"]] = relationship(
        back_populates="law", cascade="all, delete-orphan", order_by="LawAnnex.code"
    )
    chunks: Mapped[list["LawChunk"]] = relationship(
        back_populates="law", cascade="all, delete-orphan", order_by="LawChunk.idx"
    )


class LawArticle(Base):
    """An Article of a law, with its paragraph structure."""
    __tablename__ = "law_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    celex: Mapped[str] = mapped_column(String(20), ForeignKey("laws.celex"), index=True)
    article_number: Mapped[str] = mapped_column(String(20))  # "5", "50bis"
    title: Mapped[Optional[str]] = mapped_column(String(500))
    full_path: Mapped[str] = mapped_column(String(200))  # "Article 5" or "Article 5(1)(a)"
    text: Mapped[str] = mapped_column(Text)
    parent_article_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("law_articles.id"), index=True
    )  # for sub-paragraphs

    # ────── Detection method classification (LLM-assisted) ──────
    # 'code' | 'api' | 'hybrid' | 'process'
    detection_method: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    detection_confidence: Mapped[Optional[float]] = mapped_column()  # 0.0–1.0
    detection_classified_by: Mapped[Optional[str]] = mapped_column(String(30))  # 'llm' | 'human'
    detection_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    detection_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    law: Mapped["Law"] = relationship(back_populates="articles")
    parent: Mapped[Optional["LawArticle"]] = relationship(remote_side=[id])

    __table_args__ = (
        UniqueConstraint("celex", "full_path", name="uq_article_celex_path"),
        Index("ix_law_articles_celex_number", "celex", "article_number"),
    )


class LawRecital(Base):
    """A numbered recital (the 'whereas' clauses at the start of an act)."""
    __tablename__ = "law_recitals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    celex: Mapped[str] = mapped_column(String(20), ForeignKey("laws.celex"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    law: Mapped["Law"] = relationship(back_populates="recitals")

    __table_args__ = (
        UniqueConstraint("celex", "number", name="uq_recital_celex_number"),
    )


class LawAnnex(Base):
    """An annex of a law."""
    __tablename__ = "law_annexes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    celex: Mapped[str] = mapped_column(String(20), ForeignKey("laws.celex"), index=True)
    code: Mapped[str] = mapped_column(String(10))  # "I", "II", "III", "A", "B"
    title: Mapped[str] = mapped_column(String(1000))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)  # full text (potentially large)

    law: Mapped["Law"] = relationship(back_populates="annexes")

    __table_args__ = (
        UniqueConstraint("celex", "code", name="uq_annex_celex_code"),
    )


class LawChunk(Base):
    """A chunk of law text for RAG retrieval.

    Chunks are typically Article-paragraph level granularity.
    Migration to PostgreSQL will add a `vector(1536)` column for embeddings.
    """
    __tablename__ = "law_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    celex: Mapped[str] = mapped_column(String(20), ForeignKey("laws.celex"), index=True)
    idx: Mapped[int] = mapped_column(Integer)  # ordering within a law
    chunk_kind: Mapped[str] = mapped_column(String(30))  # 'recital', 'article', 'article_paragraph', 'annex'
    location: Mapped[str] = mapped_column(String(200))  # 'Art. 5(1)' or 'Recital 3' or 'Annex III'
    full_text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    # embedding column added via migration for PostgreSQL+pgvector
    # For now we keep it as nullable so SQLite works.
    embedding_model: Mapped[Optional[str]] = mapped_column(String(50))  # 'gemma3:12b' or future
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    law: Mapped["Law"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("celex", "idx", name="uq_chunk_celex_idx"),
        Index("ix_law_chunks_kind", "celex", "chunk_kind"),
    )


class DiscoveryCandidate(Base):
    """A candidate law surfaced by the discovery pipeline (RSS / CELLAR / manual)."""
    __tablename__ = "discovery_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    celex: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(30))  # 'RSS_161' | 'RSS_162' | 'RSS_222' | 'CELLAR_REL' | 'MANUAL'
    feed_id: Mapped[Optional[int]] = mapped_column(Integer)
    parent_celex: Mapped[Optional[str]] = mapped_column(String(20))
    title: Mapped[Optional[str]] = mapped_column(Text)
    pub_date: Mapped[Optional[str]] = mapped_column(String(100))
    creator: Mapped[Optional[str]] = mapped_column(String(200))
    keyword_match: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cellar_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    cellar_title: Mapped[Optional[str]] = mapped_column(Text)
    cellar_date: Mapped[Optional[str]] = mapped_column(String(20))
    cellar_in_force: Mapped[Optional[str]] = mapped_column(String(5))
    llm_in_scope: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    llm_tier: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    llm_confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    llm_reason: Mapped[Optional[str]] = mapped_column(Text)
    llm_backend: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    review_note: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("celex", "source", name="uq_candidate_celex_source"),
        Index("ix_candidates_status", "status"),
    )


class ReviewAction(Base):
    """Audit log of accept/reject decisions on discovery candidates."""
    __tablename__ = "review_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    celex: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(30))  # 'accept' | 'reject' | 'auto_added' | 'auto_rejected'
    tier: Mapped[Optional[int]] = mapped_column(Integer)
    short_name: Mapped[Optional[str]] = mapped_column(String(200))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    actor: Mapped[Optional[str]] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Framework(Base):
    """A compliance framework (SOC 2, ISO 27001, HIPAA, PCI DSS, etc.) or non-EU law.

    Each Framework has one source file (HTML/JSON/YAML/MD/XML/PDF) and produces
    many FrameworkItem rows (controls, criteria, sections, principles).
    """
    __tablename__ = "frameworks"

    # Primary key — canonical framework ID
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    # e.g., "soc2", "iso27001", "iso42001", "pci-dss", "hipaa-privacy",
    # "nist-csf", "ccpa", "iso9001", "nen7510", "gdpr"
    category: Mapped[str] = mapped_column(String(30), index=True)
    # "eu_law", "iso_standard", "industry_standard", "us_law",
    # "global_standard", "regional_standard", "us_state_law"
    name: Mapped[str] = mapped_column(String(300))  # display name
    version: Mapped[Optional[str]] = mapped_column(String(50))
    issuing_body: Mapped[Optional[str]] = mapped_column(String(200))
    tier: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    # Tier 1 = universal, Tier 2 = common, Tier 3 = sectoral
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("frameworks.id"), index=True
    )  # for implementing regs / sub-frameworks
    source_format: Mapped[str] = mapped_column(String(30))
    # "html", "json", "yaml", "markdown", "xml", "pdf"
    source_file: Mapped[Optional[str]] = mapped_column(String(500))
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    license: Mapped[Optional[str]] = mapped_column(String(200))
    # Description / scope
    description: Mapped[Optional[str]] = mapped_column(Text)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    # Metadata as JSON
    framework_metadata: Mapped[Optional[str]] = mapped_column(Text)  # JSON blob
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    items: Mapped[list["FrameworkItem"]] = relationship(
        back_populates="framework", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_frameworks_category_tier", "category", "tier"),
    )


class FrameworkItem(Base):
    """A single item in a compliance framework.

    Could be:
    - Control (SOC 2 CC1.1.a, ISO 27001 A.5.1, PCI DSS 1.1.1, ISO 42001 A.2.2)
    - Principle (ISO 9001 QMP 1)
    - Section (HIPAA § 164.502)
    - Article (EU law — but use law_articles for those)
    """
    __tablename__ = "framework_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    framework_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("frameworks.id"), index=True
    )
    # Item code (e.g., "A.5.1", "CC1.1", "§ 164.502", "QMP 1")
    code: Mapped[str] = mapped_column(String(100), index=True)
    # Item title / short name
    title: Mapped[Optional[str]] = mapped_column(String(500))
    # Full text content
    content: Mapped[str] = mapped_column(Text)
    # Item type: "control", "principle", "section", "criterion", "point_of_focus"
    item_type: Mapped[str] = mapped_column(String(30), index=True)
    # Char count for indexing/sorting
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    # Parent item for nested hierarchies (e.g., sub-requirements)
    parent_code: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    # Original source path within the framework
    source_path: Mapped[Optional[str]] = mapped_column(String(500))
    # JSON blob for format-specific metadata
    item_metadata: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ────── Detection method classification (LLM-assisted) ──────
    # 'code' | 'api' | 'hybrid' | 'process'
    detection_method: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    detection_confidence: Mapped[Optional[float]] = mapped_column()  # 0.0–1.0
    detection_classified_by: Mapped[Optional[str]] = mapped_column(String(30))  # 'llm' | 'human'
    detection_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    detection_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    framework: Mapped["Framework"] = relationship(back_populates="items")

    __table_args__ = (
        Index("ix_fw_items_framework_code", "framework_id", "code"),
        Index("ix_fw_items_type", "framework_id", "item_type"),
    )


class FrameworkMapping(Base):
    """Cross-framework mappings between items.

    Used for the "single PR comment shows all applicable frameworks" feature.
    E.g., AI Act Article 14 ↔ ISO 42001 A.6.2.2 ↔ SOC 2 CC8.1
    """
    __tablename__ = "framework_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_framework: Mapped[str] = mapped_column(String(50), index=True)
    source_code: Mapped[str] = mapped_column(String(100), index=True)
    target_framework: Mapped[str] = mapped_column(String(50), index=True)
    target_code: Mapped[str] = mapped_column(String(100), index=True)
    relationship_type: Mapped[str] = mapped_column(String(50))
    # "equivalent", "subset", "superset", "related"
    confidence: Mapped[Optional[float]] = mapped_column()  # 0.0 - 1.0
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_mappings_source", "source_framework", "source_code"),
        Index("ix_mappings_target", "target_framework", "target_code"),
    )


class AgentRepository(Base):
    """A curated open-source Python AI-agent GitHub repository.

    This table stores metadata + URLs only — never the repository source
    code. The compliance scanner worker is expected to clone enabled rows
    one at a time, run analysis, store the scan result, then delete the
    temporary clone.

    Fields grouped by purpose:

    GitHub identity
        github_id, full_name, owner, name, html_url, clone_url
    Metadata snapshot
        description, primary_language, topics_json, license_spdx,
        stars, forks
    GitHub timestamps
        github_created_at, github_updated_at, github_pushed_at
    Repo flags
        archived, fork
    Corpus classification (NOT a compliance classification)
        agent_category, relevance_status, relevance_confidence,
        relevance_reason
    Provenance + pipeline control
        discovery_query, discovered_at, last_metadata_refresh, enabled
    """
    __tablename__ = "agent_repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # GitHub identity
    github_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True)   # "owner/name"
    owner: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    html_url: Mapped[str] = mapped_column(String(500), unique=True)
    clone_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Metadata snapshot
    description: Mapped[Optional[str]] = mapped_column(Text)
    primary_language: Mapped[Optional[str]] = mapped_column(String(50))
    topics_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    license_spdx: Mapped[Optional[str]] = mapped_column(String(100))
    stars: Mapped[int] = mapped_column(Integer, default=0)
    forks: Mapped[int] = mapped_column(Integer, default=0)

    # GitHub timestamps
    github_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    github_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    github_pushed_at:  Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Repo flags
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    fork:     Mapped[bool] = mapped_column(Boolean, default=False)

    # Corpus classification
    agent_category:   Mapped[Optional[str]] = mapped_column(String(30), index=True)
    relevance_status: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    relevance_confidence: Mapped[Optional[float]] = mapped_column()
    relevance_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Provenance + pipeline control
    discovery_query:  Mapped[Optional[str]] = mapped_column(String(200))
    discovered_at:    Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_metadata_refresh: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reclassified_at:  Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    enabled:          Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (
        Index("ix_agent_repos_pushed", "github_pushed_at"),
        Index("ix_agent_repos_language", "primary_language"),
    )


class AgentRepositoryAudit(Base):
    """A single inspection verdict on an AgentRepository.

    Each row is one audit event. A repository can accumulate many audits
    over time (different batches, different auditors, different verdicts);
    history is preserved. The latest verdict per repository is exposed
    via the ``agent_repository_current_status`` view.

    Lifecycle separation:
      - ``AgentRepository.relevance_status`` is mutable machine state
        (recomputed by reclassify, etc.).
      - ``AgentRepositoryAudit`` is inspection evidence that we don't
        overwrite. Nothing becomes gold until a human records an audit
        row with ``verdict='gold'``.

    Verdict values:
      - gold       human-confirmed real Python AI agent runtime
      - reject     inspected and out of scope
      - borderline ambiguous; flagged for deeper review

    Auditor type:
      - human              a person reviewed and recorded this verdict
      - llm-judge          LLM-produced proposal (NOT yet gold)
      - heuristic-review   deterministic classifier self-review
      - deterministic-review  any other rule-based review
    """
    __tablename__ = "agent_repository_audits"

    id:            Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_repositories.id"), index=True)
    verdict:       Mapped[str] = mapped_column(String(20), index=True)
    auditor_type:  Mapped[str] = mapped_column(String(30))
    auditor:       Mapped[Optional[str]] = mapped_column(String(100))
    reason:        Mapped[Optional[str]] = mapped_column(Text)
    audit_batch:   Mapped[Optional[str]] = mapped_column(String(100), index=True)
    audited_at:    Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    repository: Mapped["AgentRepository"] = relationship()