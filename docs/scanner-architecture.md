# Scanner Architecture

## Overview

The compliance scanner reads source code and queries external integrations to detect compliance violations. Each compliance item in the database has a `detection_method` field that determines how it's checked.

## Detection Methods

| Method | Checked by | Examples |
|---|---|---|
| `code` | Reading source code (regex, AST) | AI Act Art. 50 (chatbot disclosure in UI), GDPR Art. 17 (deletion endpoint) |
| `api` | Querying external integrations | SOC 2 CC6.1 (Okta MFA enabled), GDPR Art. 32 (AWS KMS keys) |
| `hybrid` | Both code AND API evidence required | AI Act Art. 14 (human oversight hook + audit log), GDPR Art. 32 (encryption code + KMS) |
| `process` | Manual attestation only (not auto-scanned) | AI Act Art. 9 (risk assessment docs), ISO 27001 A.5.1 (policy documents) |

## Scanner Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                       Compliance Scanner                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  �─────────────────────┐  ┌─────────────────────┐               │
│  │  Code Scanner       │  │  API Checker        │               │
│  │  (clones repo)      │  │  (queries clouds)   │               │
│  │  - regex            │  │  - AWS/GCP/Azure    │               │
│  │  - AST (TS/Python)  │  │  - Okta/Auth0       │               │
│  │  - grep             │  │  - GitHub/GitLab    │               │
│  └──────────┬──────────┘  └──────────┬──────────┘               │
│             │                        │                          │
│             └────────┬───────────────┘                          │
│                      ▼                                          │
│             ┌─────────────────┐                                 │
│             │  Finding        │  (pass/fail/warning/manual)     │
│             └─────────────────┘                                 │
│                                                                  │
│  For process items:                                              │
│  ┌─────────────────────┐                                        │
│  │  Manual Checklist   │  → user uploads evidence              │
│  └─────────────────────┘                                        │
└──────────────────────────────────────────────────────────────────┘
```

## Scanning Pipeline

For each `framework_item` / `law_article` with `detection_method` in ('code', 'hybrid'):

1. **Load rule** — fetch scanner rule from rules database
2. **Execute check** — code regex/AST OR API query OR both
3. **Emit finding** — pass / fail / warning / manual
4. **Update dashboard** — show status + remediation guidance

For `process` items: skip auto-scan, surface as "manual review required"

## Scanner Rule Schema (proposed)

```sql
CREATE TABLE scanner_rules (
    id INTEGER PRIMARY KEY,
    framework_id TEXT,        -- '32024R1689', 'soc2', etc.
    item_code TEXT,           -- 'Article 50', 'CC6.1', etc.
    rule_type TEXT,           -- 'regex', 'ast', 'api_query', 'hybrid'
    rule_definition TEXT,     -- JSON: regex pattern, AST query, API call
    severity TEXT,            -- 'critical', 'warning', 'info'
    description TEXT,
    remediation TEXT,         -- how to fix if failing
    positive_evidence TEXT,   -- what "compliant" looks like
    created_at TIMESTAMP
);
```

## Output Schema

```sql
CREATE TABLE findings (
    id INTEGER PRIMARY KEY,
    scan_id INTEGER,
    rule_id INTEGER,
    framework_id TEXT,
    item_code TEXT,
    status TEXT,              -- 'pass', 'fail', 'warning', 'manual', 'skipped'
    evidence TEXT,            -- what we found
    location TEXT,            -- file:line if applicable
    remediation TEXT,
    detected_at TIMESTAMP
);
```

## MVP Implementation Path

### Phase 1: Code-only scanner (1-2 weeks)
- Target: AI Act + GDPR + CRA `code` items (~50-100 items)
- Rules: regex on source files
- Output: GitHub PR comments

### Phase 2: API checker (2-3 weeks)
- Target: SOC 2 + ISO 27001 `api` items
- Rules: AWS IAM queries, Okta API, GitHub Dependabot
- Output: dashboard widgets

### Phase 3: Hybrid scanner (3-4 weeks)
- Target: items needing both code + API evidence
- Rules: combined checks
- Output: full coverage

### Phase 4: Cross-framework mapping (killer feature)
- "Article 50 violation" → also shows SOC 2 P6.1, ISO 42001 A.8.5
- Single PR comment lists ALL applicable frameworks

## What this means for the scanner

After full classification:
- ~30-40% of items are `code` or `hybrid` → scanner handles these
- ~30-40% are `api` or `hybrid` → API integrations needed
- ~30-40% are `process` → manual checklist only

## Integration targets (priority order)

1. **GitHub/GitLab** — code scanning via PR comments
2. **AWS IAM / KMS / S3** — encryption, access control, MFA
3. **Okta / Auth0** — authentication, MFA enforcement
4. **Vercel / cloud providers** — deployment, environment config
5. **OpenAI / Anthropic API** — AI-specific controls (logging, etc.)

## Open questions

- How do we handle partial coverage? (only some articles of AI Act apply to a given company)
- How do we handle exemptions? (Art. 50 doesn't apply to internal-only AI systems)
- How do we version rules when laws change?
