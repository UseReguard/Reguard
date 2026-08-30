# Technical Requirements Analysis

**Source**: Read all 346 items classified as `code` or `hybrid` across 28 EU laws and 11 standards.

**Date**: 2026-08-22

## Executive Summary

The compliance scanner must detect **8 categories of technical requirements** using **5 detection method families**. We have **346 actionable items** to scan against. A **10-rule MVP** would cover ~60% of customer pain points (AI Act + GDPR + CRA).

## 1. The 8 Categories of Technical Requirements

After reading all code+hybrid items, obligations fall into 8 categories:

### 1.1 User-facing disclosure (UI text, links, notices)

**~80 items** — Compliance requires specific text/content visible to users.

Examples:
- AI Act Art. 50 — chatbot disclosure ("you are talking to an AI")
- AI Act Art. 13 — high-risk AI transparency to deployers
- GDPR Art. 13/14 — privacy notice at data collection
- CCPA — "Do Not Sell or Share My Personal Information" link
- HIPAA 164.520 — Notice of Privacy Practices

**Detection**: Regex in UI templates (*.tsx, *.jsx, *.vue, *.html, *.svelte)

### 1.2 Data subject endpoints (API routes)

**~70 items** — Compliance requires HTTP endpoints to honor data rights.

Examples:
- GDPR Art. 15 — right to access (GET endpoint)
- GDPR Art. 16 — right to rectification (PATCH endpoint)
- GDPR Art. 17 — right to erasure (DELETE endpoint)
- GDPR Art. 18 — right to restriction (PATCH endpoint)
- GDPR Art. 20 — right to data portability (GET/JSON export)
- GDPR Art. 21 — right to object (POST opt-out)
- HIPAA 164.524 — right of access
- HIPAA 164.526 — right to amend
- HIPAA 164.528 — accounting of disclosures

**Detection**: AST pattern matching on route definitions

### 1.3 Logging calls (audit trail in source)

**~50 items** — Compliance requires logging specific events.

Examples:
- AI Act Art. 12 — automatic recording over AI system lifetime
- AI Act Art. 19 — log retention by provider
- ISO 42001 A.6.2.8 — event logs for incident investigation
- ISO 27001 A.8.15 — logging
- NEN 7510 12.4.1, 12.4.3 — logging
- PCI DSS 10.x — audit logs

**Detection**: Regex for `logger.*audit\|audit_log\.\|console\.log.*audit`

### 1.4 Encryption calls (crypto APIs)

**~30 items** — Compliance requires encryption of specific data.

Examples:
- GDPR Art. 32 — security of processing (encryption pseudonymisation)
- ISO 27001 A.5.14 — encryption for confidential data in transit
- ISO 27001 A.8.24 — use of cryptography
- PCI DSS 3.x — PAN protection
- Data Act Art. 11 — encryption of IoT data

**Detection**: Regex for `crypto\.subtle\|AES\|bcrypt\|argon2\|kms\.encrypt\|encrypt(`

### 1.5 Access control patterns (auth middleware, RBAC)

**~50 items** — Compliance requires access control mechanisms.

Examples:
- HIPAA 164.312 — technical safeguards (access control)
- ISO 27001 A.5.16 — identity management
- ISO 27001 A.5.17 — password policies, MFA
- ISO 27001 A.8.3 — information access restriction
- ISO 27001 A.8.5 — secure authentication
- PCI DSS 1.x — network security controls
- PCI DSS 7.x — access restriction
- PCI DSS 8.x — authentication

**Detection**: AST pattern for auth decorators/middleware + regex for `requireAuth\|checkRole\|RBAC\|mfa\|2fa\|totp`

### 1.6 Human oversight hooks (AI-specific)

**~10 items** — Compliance requires human-in-the-loop mechanisms.

Examples:
- AI Act Art. 14 — human oversight for high-risk AI
- AI Act Art. 13 — transparency enabling deployer oversight

**Detection**: AST pattern for `requires_human_review\|hitl_\|manual_approval\|human_review_queue`

### 1.7 File presence (docs, configs, declarations)

**~30 items** — Compliance requires specific files to exist.

Examples:
- CRA Art. 14 — vulnerability disclosure policy (SECURITY.md)
- AI Act Art. 48 — CE marking on product
- CRA Art. 30 — CE marking
- MDR Art. 20 — CE marking
- ISO 42001 A.6.2.3 — design documentation
- ISO 42001 A.8.2 — user documentation

**Detection**: File existence check + content regex

### 1.8 Negative patterns (code MUST NOT do X)

**~10 items** — Compliance forbids certain code patterns.

Examples:
- AI Act Art. 5 — prohibited AI practices:
  - Subliminal manipulation
  - Exploitation of vulnerabilities (age, disability, social/economic)
  - Social scoring
  - Real-time biometric identification in public spaces (law enforcement)
  - Emotion recognition in workplace/education
  - Biometric categorization (race, political opinions, etc.)

**Detection**: Negative regex — finding these patterns is a VIOLATION

## 2. The 5 Detection Method Families

Every scanner rule uses one of these primitives:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. file_presence    → SECURITY.md exists?                       │
│  2. regex_in_source  → /\bdelte.*user.*account\b/i              │
│  3. ast_pattern      → @requireAuth() decorator                  │
│  4. api_query        → AWS IAM: MFA enabled?                     │
│  5. negative_regex   → NOT finding "emotion_recognition"         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 file_presence

Check that a file exists with optional content match.

```yaml
rule_type: file_presence
rule_definition:
  file_path: "SECURITY.md"
  content_pattern: "vulnerability disclosure|security@"  # optional
```

### 2.2 regex_in_source

Grep for regex patterns across source files.

```yaml
rule_type: regex_in_source
rule_definition:
  pattern: "(ai|artificial intelligence).*(chatbot|assistant|system)"
  file_patterns: ["**/*.tsx", "**/*.jsx", "**/*.vue", "**/*.html"]
  case_insensitive: true
```

### 2.3 ast_pattern

Parse source AST and match structural patterns (functions, classes, decorators).

```yaml
rule_type: ast_pattern
rule_definition:
  language: "typescript"
  query: |
    Decorator {
      name: { regex: "^require(Auth|Role|Admin)$" }
    }
  file_patterns: ["**/*.ts"]
```

### 2.4 api_query

For hybrid items — query external systems for configuration evidence.

```yaml
rule_type: api_query
rule_definition:
  integration: "aws_iam"
  query: "list-users | check mfa_enabled"
  assertion: "all users have mfa_enabled == true"
```

### 2.5 negative_regex

Inverted pattern — finding a match indicates a VIOLATION.

```yaml
rule_type: negative_regex
rule_definition:
  pattern: "emotion_recognition|social_scoring|biometric_categorization|subliminal_manipulation"
  file_patterns: ["**/*.{ts,js,py}"]
  severity: "critical"
```

## 3. The 10 Highest-Priority MVP Rules

These 10 rules cover ~60% of customer pain points. They target AI Act + GDPR + CRA — the EU obligations every AI company must address.

| # | Framework | Item | Rule | Type | Severity |
|---|---|---|---|---|---|
| 1 | AI Act | Art. 50 | regex: user-facing UI mentions "AI" or "automated" | regex | warning |
| 2 | AI Act | Art. 14 | AST: function with `requires_human_review` / `hitl_*` / `manual_approval` | ast | critical |
| 3 | AI Act | Art. 12 | regex: source calls logger/audit_log for AI events | regex | critical |
| 4 | AI Act | Art. 5 | negative: NOT finding `emotion_recognition\|social_scoring\|biometric_categorization` | negative | critical |
| 5 | GDPR | Art. 17 | AST: route handler for `DELETE /users/:id` or `/account/delete` | ast | critical |
| 6 | GDPR | Art. 20 | AST: route returning JSON export of user data | ast | warning |
| 7 | GDPR | Art. 32 | regex: `crypto.subtle\|AES\|bcrypt\|argon2\|kms\.encrypt` | regex | critical |
| 8 | CRA | Art. 14 | file_presence: `SECURITY.md` in repo root | file_presence | warning |
| 9 | HIPAA | 164.312 | regex: middleware/decorator with `requireAuth\|checkRole\|RBAC` | regex | critical |
| 10 | ISO 27001 | A.5.17 | regex: `mfa\|two_factor\|2fa\|otp\|totp` in auth code | regex | warning |

### 3.1 Why these 10?

1. **AI Act Art. 50** — every chatbot/customer-facing AI must comply. Universal.
2. **AI Act Art. 14** — high-risk AI is the main regulatory focus.
3. **AI Act Art. 12** — logging is required across all high-risk AI.
4. **AI Act Art. 5** — these are prohibited; finding them is a hard violation.
5. **GDPR Art. 17** — most-requested data right.
6. **GDPR Art. 20** — portability is increasingly required.
7. **GDPR Art. 32** — security is foundational.
8. **CRA Art. 14** — every software product on EU market needs vuln disclosure.
9. **HIPAA 164.312** — common for health-tech AI companies.
10. **ISO 27001 A.5.17** — MFA is the most common security requirement across frameworks.

## 4. Database Schema

### 4.1 scanner_rules table

```sql
CREATE TABLE scanner_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    framework_id TEXT NOT NULL,         -- '32024R1689', '32016R0679', '32024R2847'
    item_code TEXT NOT NULL,            -- 'Article 17', 'CC6.1', 'A.5.17'
    rule_type TEXT NOT NULL,            -- 'file_presence', 'regex_in_source', 'ast_pattern', 'api_query', 'negative_regex'
    rule_definition TEXT NOT NULL,      -- JSON
    severity TEXT NOT NULL,             -- 'critical', 'warning', 'info'
    description TEXT,                   -- human-readable
    remediation TEXT,                   -- what to do if failing
    positive_evidence TEXT,             -- what passing looks like
    negative_evidence TEXT,             -- what failing looks like
    applicable_languages TEXT,          -- JSON list: ['typescript', 'python']
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (framework_id) REFERENCES frameworks(id)
);

CREATE INDEX ix_rules_framework ON scanner_rules(framework_id);
CREATE INDEX ix_rules_enabled ON scanner_rules(enabled);
```

### 4.2 findings table

```sql
CREATE TABLE findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,              -- UUID per scan run
    rule_id INTEGER NOT NULL,
    framework_id TEXT NOT NULL,
    item_code TEXT NOT NULL,
    status TEXT NOT NULL,               -- 'pass', 'fail', 'warning', 'manual', 'skipped', 'not_applicable'
    evidence TEXT,                      -- what we found (snippet, file path, etc.)
    location TEXT,                      -- file:line
    remediation TEXT,
    detected_at TIMESTAMP,
    scan_target TEXT,                   -- 'github:org/repo@commit_sha'
    FOREIGN KEY (rule_id) REFERENCES scanner_rules(id)
);

CREATE INDEX ix_findings_scan ON findings(scan_id);
CREATE INDEX ix_findings_rule ON findings(rule_id);
CREATE INDEX ix_findings_status ON findings(status);
```

### 4.3 scans table (run-level metadata)

```sql
CREATE TABLE scans (
    id TEXT PRIMARY KEY,                -- UUID
    target TEXT NOT NULL,               -- 'github:org/repo', 'local:/path'
    commit_sha TEXT,                    -- git commit if applicable
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    rules_evaluated INTEGER,
    findings_count INTEGER,
    pass_count INTEGER,
    fail_count INTEGER,
    warning_count INTEGER,
    manual_count INTEGER,
    skipped_count INTEGER,
    error TEXT
);
```

## 5. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Scanner System                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│   │  Source      │    │  AST         │    │  API         │     │
│   │  Scanner     │    │  Analyzer    │    │  Checker     │     │
│   │  (regex/     │    │  (TS, Python)│    │  (AWS, Okta) │     │
│   │   file check)│    │              │    │              │     │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘     │
│          │                   │                   │             │
│          └───────────────────┼───────────────────┘             │
│                              ▼                                  │
│                  ┌─────────────────────�                        │
│                  │  Rule Engine        │                        │
│                  │  (loads YAML rules) │                        │
│                  └──────────┬──────────┘                        │
│                             ▼                                   │
│                  ┌─────────────────────┐                        │
│                  │  Finding Emitter    │                        │
│                  │  (pass/fail/warning)│                        │
│                  └──────────�──────────┘                        │
│                             ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  Database (findings + scanner_rules)                    │  │
│   └─────────────────────────────────────────────────────────┘  │
│                             ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  Output Sinks                                            │  │
│   │  - GitHub PR comment                                     │  │
│   │  - Dashboard                                             │  │
│   │  - Slack notification                                    │  │
│   │  - JSON / SARIF export                                   │  │
│   └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.1 Components

**rule_engine.py**
- Loads scanner_rules from DB (or YAML files)
- Dispatches to appropriate scanner based on rule_type
- Returns Finding objects

**source_scanner.py**
- Clones repo (or reads local path)
- Walks files matching file_patterns
- Runs regex_in_source and file_presence rules

**ast_patterns/**
- `typescript.py` — uses TypeScript Compiler API or tree-sitter
- `python.py` — uses Python ast module

**api_checker/**
- `aws.py` — boto3 queries (IAM, KMS, S3)
- `okta.py` — Okta API queries
- `github.py` — GitHub API (Dependabot, branch protection)

**finding_emitter.py**
- Writes to findings table
- Formats output for sinks

**run_scan.py**
- CLI entry point
- Args: --target, --commit, --rules, --output-format

## 6. Phased Build Plan

| Phase | Effort | Deliverable | What it unlocks |
|---|---|---|---|
| 1 | 1 week | 10 MVP rules (AI Act + GDPR + CRA), regex-based CLI | First customer demo |
| 2 | 2 weeks | AST patterns for TypeScript + Python, expand to 50 rules | Better accuracy |
| 3 | 2 weeks | API checks for hybrid items (AWS, Okta, GitHub) | Hybrid coverage |
| 4 | 1 week | GitHub PR comment integration | Developer workflow |
| 5 | 2 weeks | Cross-framework mapping (show all related items) | Killer feature |

**Total MVP**: 6-8 weeks with 1-2 engineers.

## 7. Open Questions

### 7.1 Language priority

- **TypeScript** — most SaaS companies
- **Python** — most AI/ML companies
- **Go / Rust / Java** — secondary

Recommendation: TS + Python for MVP. Add others based on customer demand.

### 7.2 Deployment model

Three options:

**A. CLI tool customer runs in CI**
- Customer owns the data
- We sell SaaS dashboard for aggregation
- Lower security concerns
- Higher friction (setup required)

**B. GitHub Action**
- Pre-built, easy install
- Scans on PR
- We see the code (privacy concerns)

**C. Hosted scanner**
- Customer uploads/pairs repo
- We scan in our infra
- Highest convenience, highest security concerns

Recommendation: **A + B** for MVP. Skip C until we have SOC 2 ourselves.

### 7.3 Cross-framework mapping

Should the scanner automatically surface:
> "AI Act Art. 50 violation → also relevant to: SOC 2 P6.1, ISO 42001 A.8.5"

Requires populating `framework_mappings` table (currently empty).

This is the **killer feature** — no competitor has it. Build this in Phase 5.

### 7.4 False positive tolerance

Realistic estimate based on pattern matching:
- ~10-20% false positives initially
- Improve with customer feedback loop
- Need "ignore" / "suppress" mechanism

## 8. What This Tells Us About the Product

### Strategic implications

1. **The scanner is feasible** — 346 items is manageable, ~10-15 rules cover the bulk.
2. **Most obligations share detection patterns** — "endpoint exists", "logging calls", "encryption used".
3. **EU-specific rules differ** from US/global standards.
4. **Some items need negative detection** (Art. 5 = MUST NOT do X).
5. **Hybrid items need both code + API evidence** — orchestration complexity.

### Competitive moat

The combination of:
- **EU-specific rules** (AI Act, GDPR, CRA) — Vanta/Comp AI don't have depth
- **Code scanning** — Comp AI explicitly does not do this
- **Cross-framework mapping** — no one has it
- **EU AI Act Annex IV documentation generator** — no one has this

...is defensible. No one competitor has all four.

## 9. Next Steps

### Recommended path

1. **Pick 10 rules** (table above) → write as YAML
2. **Build minimal rule engine** (Python script, ~200 LOC)
3. **Test on a real repo** (yours)
4. **Iterate based on false positives/negatives**
5. **Add GitHub Action wrapper** so it surfaces in PRs
6. **Design partner feedback** (3-5 customers)

Estimated effort: **2-3 weeks for working MVP**.

### Alternative path

If scanner feels too engineering-heavy:
- **Documentation generator first** (AI Act Annex IV) — high value, lower code complexity
- **Trust portal first** — like Comp AI's UI but for EU AI compliance

### Decision criteria

Build scanner first if:
- Customer demand is "scan our code"
- Target customers are developers / engineering teams
- Want a true technical moat

Build docs generator first if:
- Customer demand is "produce AI Act technical documentation"
- Target customers are compliance/legal teams
- Want fast time-to-value

## 10. References

- EU laws in `data/raw/` (downloaded from EUR-Lex; not redistributed — see § License)
- Standards (third-party): see `data/raw/` ISO27001, ISO42001, SOC2, PCI-DSS, NEN7510, NIST-CSF — third-party content, removed from public tracking due to redistribution uncertainty
- Classified items in SQLite at `data/eu_ai_compliance.db` (research data; not part of v0.1 release payload)
- Scanner architecture: `docs/scanner-architecture.md`
- Detection method classification: `scripts/classify_detection_methods.py`
