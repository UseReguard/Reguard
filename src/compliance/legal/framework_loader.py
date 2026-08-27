"""Multi-format loader for compliance frameworks.

Supports loading compliance framework content from:
- HTML (EUR-Lex XHTML) — already parsed by `parser.py`
- JSON (SOC 2, ISO 27001, NEN 7510)
- YAML (PCI DSS ComplianceAsCode)
- Markdown (ISO 42001 Claude Skill)
- XML (HIPAA eCFR)
- PDF (NIST CSF, ISO 9001 docs)

All formats normalize to a common interface:
    ParsedFramework
        .name           — framework display name
        .source_file    — path to source
        .items          — list of FrameworkItem
            .code       — control/article ID
            .title      — short name
            .content    — full text
            .metadata   — extra fields (severity, category, etc.)
"""
from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("framework_loader")


@dataclass
class FrameworkItem:
    code: str
    title: str
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedFramework:
    name: str
    source_file: str
    items: list[FrameworkItem]
    metadata: dict = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.items)


def load_framework(path: Path | str) -> ParsedFramework:
    """Auto-detect format and load a compliance framework file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    suffix = p.suffix.lower()
    # .skill files are ZIP archives containing markdown
    if suffix == ".skill":
        return _load_skill_zip(p)
    if suffix == ".json":
        return _load_json(p)
    if suffix in (".yml", ".yaml"):
        return _load_yaml(p)
    if suffix == ".md":
        return _load_markdown(p)
    if suffix == ".xml":
        return _load_xml(p)
    if suffix == ".pdf":
        return _load_pdf(p)
    if suffix in (".html", ".htm"):
        return _load_html(p)
    raise ValueError(f"Unsupported format: {suffix}")


def _load_skill_zip(p: Path) -> ParsedFramework:
    """Load a Claude Skill ZIP archive containing markdown references."""
    import zipfile

    with zipfile.ZipFile(p, "r") as z:
        items = []
        for name in z.namelist():
            if not name.endswith(".md"):
                continue
            with z.open(name) as f:
                content = f.read().decode("utf-8")
            # Parse as markdown table
            table_pattern = re.compile(
                r"^\|\s*([A-Z]{1,3}\.?\d+(?:\.\d+)*[a-z]?)\s*\|([^|]+?)\s*\|[^|]*\|(.*?)\|\s*$",
                re.MULTILINE,
            )
            for m in table_pattern.finditer(content):
                code = m.group(1).strip()
                name_part = m.group(2).strip()
                desc = m.group(3).strip()
                if code.startswith("|") or code == "Control ID":
                    continue
                items.append(
                    FrameworkItem(
                        code=code,
                        title=name_part,
                        content=desc,
                        metadata={"source_file_in_zip": name},
                    )
                )
        return ParsedFramework(
            name=p.stem,
            source_file=str(p),
            items=items,
            metadata={"framework_id": p.stem, "format": "skill-zip"},
        )


# ─── JSON loaders ────────────────────────────────────────────────────────


def _load_soc2_json(data: dict, source_file: Path) -> ParsedFramework:
    """Load SOC 2 TSC JSON from AIRiskGuy/aicpa-soc-tsc-json format."""
    items = []
    tsc = data.get("trustServicesCriteria", {})

    def walk_category(category: str, controls: list[dict]) -> None:
        for ctrl in controls:
            if not isinstance(ctrl, dict):
                continue
            ctrl_id = ctrl.get("id", "")
            principle = ctrl.get("principle", "")
            # Each "point of focus" becomes a sub-item
            for pof in ctrl.get("pof", []):
                if not isinstance(pof, dict):
                    continue
                items.append(
                    FrameworkItem(
                        code=pof.get("id", ctrl_id),
                        title=pof.get("title", ""),
                        content=pof.get("requirement", ""),
                        metadata={
                            "category": category,
                            "control_id": ctrl_id,
                            "principle": principle,
                        },
                    )
                )
            # Also include the control-level principle
            if principle:
                items.append(
                    FrameworkItem(
                        code=ctrl_id,
                        title=principle.split(":", 1)[-1].strip()[:80] if ":" in principle else principle[:80],
                        content=principle,
                        metadata={"category": category, "level": "control"},
                    )
                )

    for category, controls in tsc.items():
        if isinstance(controls, list):
            walk_category(category, controls)
        elif isinstance(controls, dict):
            # additionalCriteria structure: availability/confidentiality/privacy
            for sub_cat, sub_controls in controls.items():
                if isinstance(sub_controls, list):
                    walk_category(f"{category}.{sub_cat}", sub_controls)

    return ParsedFramework(
        name="SOC 2 Trust Services Criteria (2017, with 2022 PoF revisions)",
        source_file=str(source_file),
        items=items,
        metadata={"framework_id": "soc2", "format": "tsc-json"},
    )


def _load_iso27001_json(data: list, source_file: Path) -> ParsedFramework:
    """Load ISO 27001:2022 Annex A controls from sahilsinghi/iso27001-compliance-tracker format."""
    items = []
    for ctrl in data:
        items.append(
            FrameworkItem(
                code=ctrl.get("control", ""),
                title=ctrl.get("name", ""),
                content=ctrl.get("implementationHint", ""),
                metadata={
                    "theme": ctrl.get("theme", ""),
                    "themeName": ctrl.get("themeName", ""),
                    "category": ctrl.get("category", ""),
                    "criticality": ctrl.get("criticality", ""),
                    "auditRelevance": ctrl.get("auditRelevance", ""),
                },
            )
        )
    return ParsedFramework(
        name="ISO/IEC 27001:2022 — Annex A Controls (93)",
        source_file=str(source_file),
        items=items,
        metadata={"framework_id": "iso27001", "format": "iso27001-annex-a"},
    )


def _load_nen7510_json(data: dict, source_file: Path) -> ParsedFramework:
    """Load NEN 7510:2017 controls from mazjo0100/dutch-standards-mcp format."""
    framework_meta = data.get("framework", {})
    items = []
    for ctrl in data.get("controls", []):
        # Prefer Dutch description (it's the official one)
        title = ctrl.get("title_nl") or ctrl.get("title") or ""
        desc = ctrl.get("description_nl") or ctrl.get("description") or ""
        items.append(
            FrameworkItem(
                code=ctrl.get("control_number", ""),
                title=title,
                content=desc,
                metadata={
                    "category": ctrl.get("category", ""),
                    "iso_mapping": ctrl.get("iso_mapping", ""),
                    "level": ctrl.get("level", ""),
                },
            )
        )
    return ParsedFramework(
        name=framework_meta.get("name", "NEN 7510:2017"),
        source_file=str(source_file),
        items=items,
        metadata={
            "framework_id": "nen7510",
            "format": "nen7510-extracted",
            "issuing_body": framework_meta.get("issuing_body", ""),
            "scope": framework_meta.get("scope", ""),
        },
    )


def _load_json(p: Path) -> ParsedFramework:
    """Auto-detect JSON format and load."""
    with open(p, encoding="utf-8") as f:
        data = json.load(f)

    # SOC 2 detection
    if isinstance(data, dict) and "trustServicesCriteria" in data:
        return _load_soc2_json(data, p)

    # ISO 27001 detection: list of {control: "A.5.1", name: ..., implementationHint: ...}
    if isinstance(data, list) and data and "control" in data[0] and "implementationHint" in data[0]:
        return _load_iso27001_json(data, p)

    # NEN 7510 detection: dict with framework + controls
    if isinstance(data, dict) and "framework" in data and "controls" in data:
        return _load_nen7510_json(data, p)

    # Generic fallback
    log.warning(f"Unknown JSON format in {p.name}; returning generic parser")
    return ParsedFramework(
        name=p.stem,
        source_file=str(p),
        items=[FrameworkItem(code=p.stem, title=p.stem, content=json.dumps(data)[:1000])],
        metadata={"framework_id": "unknown", "format": "generic-json"},
    )


# ─── YAML loader ────────────────────────────────────────────────────────


def _load_yaml(p: Path) -> ParsedFramework:
    """Load PCI DSS YAML from ComplianceAsCode/content format."""
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML not installed. Run: pip install pyyaml")
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    items = []
    title = data.get("title", p.stem)
    policy_id = data.get("id", p.stem)
    version = data.get("version", "")

    def walk(controls: list[dict], prefix: str = "") -> None:
        for ctrl in controls:
            ctrl_id = ctrl.get("id", "")
            full_id = f"{prefix}{ctrl_id}" if prefix else ctrl_id
            ctrl_title = ctrl.get("title", "")
            notes = ctrl.get("notes", "")
            status = ctrl.get("status", "")
            items.append(
                FrameworkItem(
                    code=str(full_id),
                    title=ctrl_title,
                    content=notes or ctrl_title,
                    metadata={"status": status, "parent": prefix},
                )
            )
            # Recurse into sub-controls
            if "controls" in ctrl and ctrl["controls"]:
                walk(ctrl["controls"], prefix=f"{full_id}.")

    walk(data.get("controls", []))
    return ParsedFramework(
        name=f"{title} v{version}" if version else title,
        source_file=str(p),
        items=items,
        metadata={"framework_id": policy_id, "format": "compliance-ascode-yaml", "version": version},
    )


# ─── Markdown loader ─────────────────────────────────────────────────────


def _load_markdown(p: Path) -> ParsedFramework:
    """Load ISO 42001 (or similar) Claude Skill markdown."""
    with open(p, encoding="utf-8") as f:
        content = f.read()

    items = []

    # Try parsing as markdown table format: | ID | Name | ... | Description |
    # Supports IDs like A.2.2, A.5.1.1, CC1.1, A1.1
    table_pattern = re.compile(
        r"^\|\s*([A-Z]{1,3}\.?\d+(?:\.\d+)*[a-z]?)\s*\|([^|]+?)\s*\|[^|]*\|(.*?)\|\s*$",
        re.MULTILINE,
    )
    for m in table_pattern.finditer(content):
        code, name, desc = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        # Skip header/separator rows
        if code.startswith("|") or code == "Control ID" or set(code) <= set("-: "):
            continue
        if name and name != "Control Name":
            items.append(
                FrameworkItem(
                    code=code,
                    title=name,
                    content=desc,
                    metadata={"source_format": "markdown-table"},
                )
            )

    # Also extract headings as section markers
    heading_pattern = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
    headings = []
    for m in heading_pattern.finditer(content):
        level = len(m.group(1))
        text = m.group(2).strip()
        headings.append((level, text))

    return ParsedFramework(
        name=p.stem,
        source_file=str(p),
        items=items,
        metadata={"framework_id": p.stem, "format": "markdown", "headings": headings[:50]},
    )


# ─── XML loader ─────────────────────────────────────────────────────────


def _load_xml(p: Path) -> ParsedFramework:
    """Load HIPAA eCFR XML format."""
    tree = ET.parse(p)
    root = tree.getroot()
    items = []
    # eCFR uses DIV6 (subpart) → DIV8 (section) → HEAD + P/PSPACE structure
    # We iterate all elements in document order; for each DIV that has a HEAD
    # followed by P/PSPACE children, emit a single item.
    ns_strip = lambda t: t.split("}")[-1] if "}" in t else t
    for elem in root.iter():
        tag = ns_strip(elem.tag)
        # Match any DIVn tag (DIV, DIV1, DIV6, DIV8, ...)
        if not tag.startswith("DIV"):
            continue
        head = None
        paragraphs = []
        for child in elem:
            child_tag = ns_strip(child.tag)
            if child_tag == "HEAD":
                head = (child.text or "").strip()
            elif child_tag in ("P", "PSPACE"):
                ptext = "".join(child.itertext()).strip()
                if ptext:
                    paragraphs.append(ptext)
        if head and paragraphs:
            content = " ".join(paragraphs)
            # Use the section number from attrs if available, else derive from head
            attrs = elem.attrib
            section_id = attrs.get("N", "")
            citation = ""
            # Extract citation from hierarchy_metadata
            meta = attrs.get("hierarchy_metadata", "")
            if "citation" in meta:
                # meta is JSON-encoded in attr, citation value is the value of "citation"
                import re as _re
                m = _re.search(r'"citation":"([^"]+)"', meta)
                if m:
                    citation = m.group(1)
            code = citation or head[:80]
            items.append(
                FrameworkItem(
                    code=code,
                    title=head,
                    content=content,
                    metadata={
                        "source_format": "ecfr-xml",
                        "section_number": section_id,
                    },
                )
            )
    return ParsedFramework(
        name=p.stem,
        source_file=str(p),
        items=items,
        metadata={"framework_id": "hipaa", "format": "ecfr-xml"},
    )


# ─── HTML loader ────────────────────────────────────────────────────────


def _load_html(p: Path) -> ParsedFramework:
    """Load EU law HTML (or CCPA, ISO 9001 Wikipedia) using parser.py."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    # Special-case ISO 9001 Wikipedia: extract principles instead of trying
    # to use the EUR-Lex HTML parser (Wikipedia structure differs).
    if "ISO9001-Wikipedia" in p.name or "ISO_9001" in p.name:
        return _load_iso9001_wikipedia(p)

    from compliance.legal.parser import parse_law  # type: ignore

    html = p.read_text(encoding="utf-8")
    parsed = parse_law(html)
    items = []
    # Add articles
    for art in parsed.articles:
        items.append(
            FrameworkItem(
                code=art.full_path,
                title=art.title or "",
                content=art.text,
                metadata={"kind": "article"},
            )
        )
    # Add recitals (no code)
    for rec in parsed.recitals:
        items.append(
            FrameworkItem(
                code=f"Recital {rec.number}",
                title="",
                content=rec.text,
                metadata={"kind": "recital"},
            )
        )
    # Add annexes
    for ann in parsed.annexes:
        items.append(
            FrameworkItem(
                code=f"Annex {ann.code}",
                title=ann.title,
                content=ann.raw_text,
                metadata={"kind": "annex"},
            )
        )
    return ParsedFramework(
        name=parsed.title or parsed.short_title or p.stem,
        source_file=str(p),
        items=items,
        metadata={"framework_id": p.stem, "format": "eur-lex-html"},
    )


def _load_iso9001_wikipedia(p: Path) -> ParsedFramework:
    """Extract ISO 9001:2015 content from Wikipedia article.

    The Wikipedia article contains:
    - 7 Quality Management Principles (QMPs)
    - Clause structure overview
    - History / context
    """
    html = p.read_text(encoding="utf-8")

    # Extract text content from <p> tags (Wikipedia style)
    text_blocks = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL)
    text_blocks = [
        re.sub(r"<[^>]+>", "", block).strip()
        for block in text_blocks
        if "<p" in block.lower()
    ]

    items = []
    # 7 Quality Management Principles
    qmp_titles = [
        ("QMP 1", "Customer focus"),
        ("QMP 2", "Leadership"),
        ("QMP 3", "Engagement of people"),
        ("QMP 4", "Process approach"),
        ("QMP 5", "Improvement"),
        ("QMP 6", "Evidence-based decision making"),
        ("QMP 7", "Relationship management"),
    ]
    for code, title in qmp_titles:
        items.append(
            FrameworkItem(
                code=code,
                title=title,
                content=f"ISO 9001:2015 Quality Management Principle: {title}. See ISO 9001:2015 for full text.",
                metadata={"kind": "principle", "source_format": "wikipedia-iso9001"},
            )
        )

    # Add extracted paragraphs as context items
    for i, block in enumerate(text_blocks[:30]):
        if len(block) < 100:
            continue
        if any(t.lower() in block.lower() for t in ["ISO 9001", "9001", "quality"]):
            items.append(
                FrameworkItem(
                    code=f"Wiki §{i+1}",
                    title="",
                    content=block[:500],
                    metadata={"kind": "wiki-paragraph"},
                )
            )

    return ParsedFramework(
        name="ISO 9001:2015 (Wikipedia summary)",
        source_file=str(p),
        items=items,
        metadata={
            "framework_id": "iso9001",
            "format": "wikipedia-summary",
            "note": "Full ISO 9001 normative text is paywalled. This is a structural summary only.",
        },
    )


# ─── PDF loader ─────────────────────────────────────────────────────────


def _load_pdf(p: Path) -> ParsedFramework:
    """Extract text from PDF (NIST CSF, ISO 9001, PCI DSS SAQs)."""
    try:
        import pypdf  # type: ignore
    except ImportError:
        try:
            import PyPDF2 as pypdf  # type: ignore
        except ImportError:
            raise ImportError("pypdf not installed. Run: pip install pypdf")

    reader = pypdf.PdfReader(str(p))
    items = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as e:
            log.warning(f"Page {i+1} extraction failed: {e}")
            text = ""
        if text.strip():
            items.append(
                FrameworkItem(
                    code=f"Page {i+1}",
                    title=f"Page {i+1}",
                    content=text,
                    metadata={"page_number": i + 1, "source_format": "pdf"},
                )
            )
    return ParsedFramework(
        name=p.stem,
        source_file=str(p),
        items=items,
        metadata={"framework_id": p.stem, "format": "pdf", "page_count": len(reader.pages)},
    )


# ─── Bulk loader ─────────────────────────────────────────────────────────


def load_all(data_dir: Path | str) -> list[ParsedFramework]:
    """Load all supported framework files in a directory."""
    d = Path(data_dir)
    frameworks = []
    skip_dirs = {"chunks"}  # avoid loading partial chunk outputs
    for p in sorted(d.rglob("*")):
        if not p.is_file():
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        # Skip RDF (not framework content)
        if p.suffix.lower() in (".rdf",):
            continue
        try:
            fw = load_framework(p)
            if fw.count > 0:
                frameworks.append(fw)
                log.info(f"  ✓ {p.relative_to(d) if p.is_relative_to(d) else p.name}: "
                         f"{fw.count} items ({fw.metadata.get('framework_id', '?')})")
        except Exception as e:
            log.warning(f"  ✗ {p.name}: {e}")
    return frameworks


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            p = Path(arg)
            log.info(f"Loading {p}...")
            fw = load_framework(p)
            log.info(f"  {fw.name}: {fw.count} items")
            if fw.items:
                print(f"  First item: {fw.items[0].code} - {fw.items[0].title[:80]}")
    else:
        log.info("Loading all frameworks in data/raw/...")
        frameworks = load_all("data/raw")
        log.info(f"\n=== Summary ===")
        log.info(f"Total frameworks loaded: {len(frameworks)}")
        for fw in frameworks:
            log.info(f"  {fw.name[:60]:60s}  {fw.count:5d} items  ({fw.metadata.get('framework_id', '?')})")
