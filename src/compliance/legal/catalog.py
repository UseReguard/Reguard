"""The canonical 28 EU laws.

This is the source of truth for which laws we cover.
Verified in EUR-Lex CELLAR on 2026-08-21.

Source: ../Canonical Law List.md in the vault
"""
from __future__ import annotations

# Tier definitions:
#   1 = Core (most software companies must comply)
#   2 = Cybersecurity / Digital / Trust (broad applicability)
#   3 = Sector-specific or conditional
#   4 = Foundational (Charter of Fundamental Rights)

CANONICAL_LAWS: list[dict] = [
    # Tier 1 — Core
    {"celex": "32024R1689", "slug": "eu-ai-act", "tier": 1,
     "short_name": "EU AI Act",
     "long_name": "Regulation (EU) 2024/1689 — Artificial Intelligence Act"},
    {"celex": "32016R0679", "slug": "gdpr", "tier": 1,
     "short_name": "GDPR",
     "long_name": "Regulation (EU) 2016/679 — General Data Protection Regulation"},
    {"celex": "32024R2847", "slug": "cra", "tier": 1,
     "short_name": "Cyber Resilience Act",
     "long_name": "Regulation (EU) 2024/2847 — Cyber Resilience Act"},
    {"celex": "32025R0454", "slug": "ai-act-scientific-panel", "tier": 1,
     "short_name": "AI Act Scientific Panel Reg",
     "long_name": "Commission Implementing Regulation (EU) 2025/454 (AI Act scientific panel)",
     "parent_celex": "32024R1689"},
    {"celex": "32026R1755", "slug": "ai-act-commission-proceedings", "tier": 1,
     "short_name": "AI Act Commission Proceedings Reg",
     "long_name": "Commission Implementing Regulation (EU) 2026/1755 (AI Act Commission proceedings)",
     "parent_celex": "32024R1689"},
    {"celex": "32026R1744", "slug": "digital-omnibus-ai", "tier": 1,
     "short_name": "Digital Omnibus on AI",
     "long_name": "Regulation (EU) 2026/1744 — Digital Omnibus on AI",
     "parent_celex": "32024R1689"},

    # Tier 2 — Cybersecurity / Digital / Trust
    {"celex": "32019R0881", "slug": "cybersecurity-act", "tier": 2,
     "short_name": "Cybersecurity Act",
     "long_name": "Regulation (EU) 2019/881 — Cybersecurity Act"},
    {"celex": "32022L2555", "slug": "nis2", "tier": 2,
     "short_name": "NIS2",
     "long_name": "Directive (EU) 2022/2555 — NIS2"},
    {"celex": "32025R0038", "slug": "cyber-solidarity", "tier": 2,
     "short_name": "Cyber Solidarity Act",
     "long_name": "Regulation (EU) 2025/38 — Cyber Solidarity Act"},
    {"celex": "32022L2557", "slug": "cer", "tier": 2,
     "short_name": "CER Directive",
     "long_name": "Directive (EU) 2022/2557 — Critical Entities Resilience"},
    {"celex": "32022R2554", "slug": "dora", "tier": 2,
     "short_name": "DORA",
     "long_name": "Regulation (EU) 2022/2554 — Digital Operational Resilience"},
    {"celex": "32022R2065", "slug": "dsa", "tier": 2,
     "short_name": "Digital Services Act",
     "long_name": "Regulation (EU) 2022/2065 — Digital Services Act"},
    {"celex": "32022R1925", "slug": "dma", "tier": 2,
     "short_name": "Digital Markets Act",
     "long_name": "Regulation (EU) 2022/1925 — Digital Markets Act"},
    {"celex": "32024R1183", "slug": "eidas-2", "tier": 2,
     "short_name": "eIDAS 2.0",
     "long_name": "Regulation (EU) 2024/1183 — eIDAS 2.0"},
    {"celex": "32023R2854", "slug": "data-act", "tier": 2,
     "short_name": "Data Act",
     "long_name": "Regulation (EU) 2023/2854 — Data Act"},
    {"celex": "32022R0868", "slug": "data-governance-act", "tier": 2,
     "short_name": "Data Governance Act",
     "long_name": "Regulation (EU) 2022/868 — Data Governance Act"},
    {"celex": "32024L2853", "slug": "product-liability", "tier": 2,
     "short_name": "Product Liability Directive",
     "long_name": "Directive (EU) 2024/2853 — Product Liability"},
    {"celex": "32023R1230", "slug": "machinery", "tier": 2,
     "short_name": "Machinery Regulation",
     "long_name": "Regulation (EU) 2023/1230 — Machinery Regulation"},
    {"celex": "32017R0745", "slug": "mdr", "tier": 2,
     "short_name": "Medical Device Regulation",
     "long_name": "Regulation (EU) 2017/745 — Medical Device Regulation"},
    {"celex": "32002L0058", "slug": "eprivacy", "tier": 2,
     "short_name": "ePrivacy Directive",
     "long_name": "Directive 2002/58/EC — ePrivacy Directive"},

    # Tier 3 — Sectoral or conditional
    {"celex": "32025R0327", "slug": "ehds", "tier": 3,
     "short_name": "European Health Data Space",
     "long_name": "Regulation (EU) 2025/327 — European Health Data Space"},
    {"celex": "32019L1151", "slug": "whistleblower", "tier": 3,
     "short_name": "Whistleblower Directive",
     "long_name": "Directive (EU) 2019/1937 — Whistleblower"},
    {"celex": "32024L1640", "slug": "amld-6", "tier": 3,
     "short_name": "AMLD 6",
     "long_name": "Directive (EU) 2024/1640 — Anti-Money Laundering"},
    {"celex": "32023D1795", "slug": "eu-us-dpf", "tier": 3,
     "short_name": "EU-US Data Privacy Framework",
     "long_name": "Commission Implementing Decision (EU) 2023/1795 — EU-US DPF"},
    {"celex": "32016L1148", "slug": "trade-secrets", "tier": 3,
     "short_name": "Trade Secrets Directive",
     "long_name": "Directive (EU) 2016/943 — Trade Secrets"},
    {"celex": "32016L0680", "slug": "led", "tier": 3,
     "short_name": "Law Enforcement Directive",
     "long_name": "Directive (EU) 2016/680 — Law Enforcement"},
    {"celex": "32018R1807", "slug": "free-flow-non-personal-data", "tier": 3,
     "short_name": "Free flow of non-personal data",
     "long_name": "Regulation (EU) 2018/1807 — Free flow of non-personal data"},

    # Tier 4 — Foundational
    {"celex": "12012P000", "slug": "charter", "tier": 4,
     "short_name": "Charter of Fundamental Rights",
     "long_name": "Charter of Fundamental Rights of the European Union"},
]


def by_celex(celex: str) -> dict | None:
    for entry in CANONICAL_LAWS:
        if entry["celex"] == celex:
            return entry
    return None


def tier_laws(tier: int) -> list[dict]:
    return [e for e in CANONICAL_LAWS if e.get("tier") == tier]


if __name__ == "__main__":
    print(f"Total canonical laws: {len(CANONICAL_LAWS)}")
    for t in [1, 2, 3, 4]:
        print(f"  Tier {t}: {len(tier_laws(t))} laws")
    print(f"\nFirst 3:")
    for entry in CANONICAL_LAWS[:3]:
        print(f"  {entry['celex']}  T{entry['tier']}  {entry['short_name']}")