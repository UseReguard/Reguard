# Laws for our Product: EU AI Code Compliance

This document lists which EU laws our product actually needs to cover.
The product is a **code compliance scanner** for EU AI software companies.

## Customer profile

The target customer is an **EU AI software company** that:
- Develops or deploys AI systems
- Sells software with digital elements in the EU
- Processes personal data (almost always)
- May operate in regulated sectors (finance, healthcare, etc.)

The laws that apply depend on the customer's profile, role, and sector.

## Tier 1 — Always needed (every customer)

These three apply to every EU AI software company.

### EU AI Act — Reg. (EU) 2024/1689
- **CELEX:** `32024R1689`
- **Why:** Defines obligations for AI system providers/deployers in the EU market.
- **Code-relevant articles:**
  - Article 5 (prohibited practices)
  - Article 6 + Annex III (high-risk classification)
  - Article 9 (risk management system)
  - Article 10 (data governance)
  - Article 12 (logging)
  - Article 14 (human oversight)
  - Article 15 (accuracy, robustness, cybersecurity)
  - Article 50 (transparency)
  - Annex IV (technical documentation)

### GDPR — Reg. (EU) 2016/679
- **CELEX:** `32016R0679`
- **Why:** Any processing of personal data — applies to nearly all AI companies.
- **Code-relevant articles:**
  - Article 22 (automated decision-making)
  - Article 25 (data protection by design and by default)
  - Article 32 (security of processing)
  - Article 35 (DPIA)

### Cyber Resilience Act — Reg. (EU) 2024/2847
- **CELEX:** `32024R2847`
- **Why:** Any software with digital elements placed on the EU market.
- **Code-relevant requirements:**
  - Annex I (cybersecurity requirements)
  - Annex II (vulnerability handling)
  - Article 13 (conformity assessment)

## Tier 2 — Needed for most B2B SaaS

Apply to most customers in the B2B SaaS / AI space.

### NIS2 — Dir. (EU) 2022/2555
- **CELEX:** `32022L2555`
- **Why:** Applies to "important" and "essential" entities. Most B2B SaaS serving
  energy, transport, banking, health, digital infrastructure, etc. qualifies.
- **Code-relevant:** Article 21 (cybersecurity risk management measures)

### Product Liability Directive — Dir. (EU) 2024/2853
- **CELEX:** `32024L2853`
- **Why:** New directive explicitly covers AI products and software. Applies when
  selling AI products to consumers.
- **Code-relevant:** Disclosure obligations for AI involvement

### Data Act — Reg. (EU) 2023/2854
- **CELEX:** `32023R2854`
- **Why:** Applies to connected products (IoT), B2B data sharing, cloud switching.
- **Code-relevant:** Articles 3–7 (B2B data sharing clauses), cloud portability

## Tier 3 — Sectoral (defer to vertical-specific customer)

Only relevant for customers in specific verticals. Build support on demand.

| Law | CELEX | Sector | When |
|---|---|---|---|
| DORA | 32022R2554 | Financial | Financial services customers |
| MDR | 32017R0745 | Medical | Medical device software (SaMD) |
| Machinery Reg | 32023R1230 | Industrial | AI in machinery products |
| ePrivacy | 32002L0058 | Telecom | Cookies, direct marketing, telecoms |
| eIDAS 2.0 | 32024R1183 | Identity | Trust services, electronic signatures |
| EHDS | 32025R0327 | Health | Health data processing |
| AMLD 6 | 32024L1640 | Financial | AML-obligated entities |

## Implementing regulations (subordinate to AI Act)

These modify or operationalize the AI Act. Defer to v2.

| Regulation | CELEX | Status |
|---|---|---|
| Digital Omnibus on AI | 32026R1744 | Modifies AI Act — read after base AI Act is in place |
| AI Act Scientific Panel | 32025R0454 | Procedural only — no compliance obligations |
| AI Act Commission Proceedings | 32026R1755 | Procedural only — no compliance obligations |

## Excluded (not code-relevant)

These are not relevant to a code compliance product:

- **DSA** (32022R2065) — platform/content moderation, not code
- **DMA** (32022R1925) — gatekeeper obligations, not code
- **Cybersecurity Act** (32019R0881) — voluntary certification framework, not direct obligations
- **CER** (32022L2557) — critical infrastructure resilience, mostly organizational
- **Whistleblower Directive** (32019L1937) — reporting obligations, not code
- **Trade Secrets Directive** (32016L0943) — legal protection, not code
- **Law Enforcement Directive** (32016L0680) — police data processing, not relevant
- **EU-US DPF** (32023D1795) — transfer mechanism, not code
- **Free Flow of Non-Personal Data** (32018R1807) — already superseded by Data Act
- **Charter** (12012P000) — interpretive only, not compliance basis

## Coverage matrix

| Tier | Laws | Code-relevant articles | Status |
|---|---|---|---|
| **Tier 1** (MVP) | 3 | ~15 articles | Need HTML text |
| **Tier 2** (B2B SaaS) | 3 | ~10 articles | Need HTML text |
| **Tier 3** (sectoral) | 7 | varies | Defer |
| **Implementing** | 3 | varies | Defer |

## What's on disk today

```
data/raw/
├── *.rdf (10 files, 76 MB total)        ← CELLAR metadata + cross-refs only
│   32024R1689.rdf  AI Act                (3.7 MB)
│   32016R0679.rdf  GDPR                 (60.8 MB)
│   32024R2847.rdf  CRA                   (1.9 MB)
│   32022L2555.rdf  NIS2                  (8.4 MB)
│   32023R2854.rdf  Data Act              (1.8 MB)
│   32024L2853.rdf  Product Liability     (0.6 MB)
│   32026R1744.rdf  Digital Omnibus       (0.2 MB)
│   32025R0454.rdf  Scientific Panel      (0.04 MB)
│   32026R1755.rdf  Commission Proc.      (0.04 MB)
│   32022R0868.rdf  Data Governance Act   (2.1 MB)  ← can drop
│
└── 32024R1689.html  AI Act               (1.26 MB, 113 articles, Wayback)
```

**Gap:** Full HTML text of CRA, GDPR, NIS2, Data Act, Product Liability. EUR-Lex
HTML is WAF-blocked from our IP. Web Archive has older snapshots only.

## Next steps

1. **Use AI Act HTML** (we have it) to define the scanner's first compliance checks
2. **Wait for EUR-Lex WAF ban to expire**, then download HTML for Tier 1 + Tier 2 (6 laws)
3. **Build compliance check rules** against the 25 code-relevant articles listed above
4. **Defer Tier 3 and implementing regs** until we have paying customers in those verticals
