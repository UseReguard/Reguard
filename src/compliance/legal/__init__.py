"""Legal sources: catalog of canonical laws, parsing, ingestion.

Modules
-------
catalog            The 28+ EU AI/cybersecurity/data laws we cover (source of truth).
framework_catalog  Non-EU frameworks (ISO, SOC 2, HIPAA, PCI DSS, …).
parser             EUR-Lex XHTML → structured ParsedLaw.
chunker            Structured law → RAG-ready Chunk list.
framework_loader   Multi-format loader (HTML/JSON/YAML/MD/XML/PDF) for frameworks.
ingest             End-to-end: download → parse → chunk → store.
"""