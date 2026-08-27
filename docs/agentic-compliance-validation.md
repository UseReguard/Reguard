# Agentic AI Compliance Validation — EU AI Act Articles

**Date**: 2026-08-22
**Status**: Design document
**Goal**: Define what we can deterministically verify in code for each agentic-relevant AI Act article, and how we implement it as a GitHub Action.

## Scope: 8 agentic-relevant articles

We focus on articles that impose **code-level** obligations on agentic AI systems:

| Article | Topic | Verifiable in code? |
|---|---|---|
| Art. 5 | Prohibited practices | ✅ Negative pattern detection |
| Art. 10 | Data governance | �️ Partially (script presence) |
| Art. 12 | Record-keeping (logging) | ✅ AST pattern (log near LLM call) |
| Art. 13 | Transparency to deployers | ✅ File presence (README/INSTRUCTIONS) |
| Art. 14 | Human oversight | ✅ AST pattern (kill switch, approval gates) |
| Art. 19 | Log retention | �️ Config file regex |
| Art. 50 | Transparency to users | ✅ Regex (UI disclosure text) |
| Art. 86 | Right to explanation | ⚠️ API endpoint detection |

**Out of scope** (process, not code): Art. 9 (risk management), Art. 11 (technical documentation), Art. 21 (cooperation), Art. 55 (GPAI risk), Art. 72-78 (post-market monitoring).

---

## Article 5 — Prohibited AI practices

### What the law requires (verbatim, abbreviated)

> "The following AI practices shall be prohibited: (a) subliminal techniques... manipulative or deceptive techniques... (b) exploiting vulnerabilities of natural persons due to age, disability or social/economic situation... (c) social scoring based on social behaviour or personality characteristics... (d) risk assessments predicting criminal offence based solely on profiling... (e) [unscrambled text continues with biometric categorisation, real-time biometric ID, emotion recognition in workplace/education, etc.]"

### Code-level property

**Negative pattern**: code does NOT reference or implement prohibited functionality.

### Scanner rule

**Pattern type**: regex (negative)
**Detection logic**: If ANY of these terms appear in code with implementation context → VIOLATION.

```
Prohibited terms (case-insensitive):
  - social_scor*, socialscore, social-scor*
  - emotion_recognition, emotion-recognition, emotion_recog*
  - subliminal_manipulation, subliminal-manipulation
  - biometric_categorization, biometric-categorisation
  - real_time_biometric, real-time-biometric
  - predictive_policing, predictive-policing (Art. 5(d) context)
```

**False positive guard**: only flag if used as a function/class/variable name, not in comments or documentation explaining why the feature is NOT implemented.

### GitHub Action integration

```yaml
- uses: eu-ai-compliance/scan-action@v1
  with:
    rule: ai-act-art-5
```

**Output (SARIF)**:
```json
{
  "ruleId": "ai-act-art-5",
  "level": "error",
  "message": "Prohibited practice detected (AI Act Art. 5)",
  "locations": [{
    "physicalLocation": {
      "artifactLocation": {"uri": "src/services/scoring.py"},
      "region": {"startLine": 42}
    }
  }]
}
```

### Honest limits

- Cannot detect if prohibited feature is **actually executed** — only that it's referenced
- Cannot determine **intent** — code that mentions `social_score` in a comment explaining why it's NOT used will still flag
- Requires human review of each finding

---

## Article 10 — Data and data governance

### What the law requires (verbatim)

> "High-risk AI systems... shall be developed on the basis of training, validation and testing data sets that meet the quality criteria... data governance and management practices appropriate for the intended purpose... [include] (a) relevant design choices; (b) data collection processes... (c) data-preparation processing operations, such as annotation, labelling, cleaning... (f) examination in view of possible biases..."

### Code-level property

**Process-script presence**: training pipeline includes documented bias examination.

### Scanner rule

**Pattern type**: file presence + content regex

```python
# Detect training pipeline
training_files = find_files_matching([
    "**/train*.py", "**/train*.ipynb",
    "**/preprocess*.py", "**/prepare*.py",
    "**/data/**/*.py"
])

# Check for bias examination
for file in training_files:
    content = file.read_text()
    if not has_bias_check(content):
        emit_warning("Art. 10(f): training pipeline lacks bias examination")
```

**Patterns suggesting bias examination**:
- `bias_check`, `bias_detection`, `bias_audit`
- `fairness_metrics`, `demographic_parity`, `equal_opportunity`
- `aif360`, `fairlearn` (libraries)
- Comments containing "bias", "fairness", "discrimination"

### GitHub Action integration

Output: warning (not error — process is documented but bias is runtime property)

### Honest limits

- **Cannot measure bias** — only that the codebase attempts to
- Cannot verify training data quality
- Cannot verify data lineage (where data came from, original purpose)
- This is **mostly process**, not code

---

## Article 12 — Record-keeping (logging)

### What the law requires (verbatim)

> "High-risk AI systems shall technically allow for the automatic recording of events (logs) over the lifetime of the system... logging capabilities shall enable the recording of events relevant for: (a) identifying situations that may result in... risk... (b) facilitating post-market monitoring... (c) monitoring the operation of high-risk AI systems..."

### Code-level property

**LLM/AI calls are logged**: every invocation of an AI service has a corresponding log call.

### Scanner rule

**Pattern type**: AST pattern with proximity check

```python
# Pseudo-code
for function_def in repo:
    if calls_llm_api(function_def):  # openai.*, anthropic.*, etc.
        if not has_log_call_within(function_def, lines=5):
            emit_error("Art. 12: LLM call without logging within 5 lines")
```

**Tree-sitter query (Python)**:
```scheme
; Find function calls to LLM APIs
(call
  function: (attribute
    object: (identifier) @obj
    attribute: (identifier) @attr)
  (#match? @attr "^(create|invoke|chat|complete|generate)$"))

; Check that logger call exists in same scope (simplified)
```

**Pattern variations by language**:
- Python: `logger.info(...)`, `logging.info(...)`, `audit_log.record(...)`
- TypeScript: `logger.info(...)`, `console.log(...)`, `auditLog.record(...)`
- Go: `log.Info(...)`, `slog.Info(...)`

### GitHub Action integration

Output: error (missing logging is a violation)

### Honest limits

- Cannot verify **what is logged** (must include required fields per Art. 12(3))
- Cannot verify **retention** (covered by Art. 19)
- Cannot verify **log integrity** (not tampered with)
- Pattern detection is approximate (5-line proximity is heuristic)

---

## Article 13 — Transparency to deployers

### What the law requires (verbatim)

> "High-risk AI systems shall be designed and developed in such a way as to ensure that their operation is sufficiently transparent to enable deployers to interpret a system's output... shall be accompanied by instructions for use... that include: (a) identity and contact details of the provider; (b) characteristics, capabilities and limitations... (ii) level of accuracy... (iii) foreseeable circumstances... (iv) technical capabilities to explain output..."

### Code-level property

**Instructions for use exist** as documentation with required sections.

### Scanner rule

**Pattern type**: file presence + section header detection

```python
required_files = ["README.md", "INSTRUCTIONS.md", "INSTRUCTIONS_FOR_USE.md"]
required_sections = [
    "intended purpose", "intended use",
    "capabilities", "limitations",
    "accuracy", "performance metrics",
    "risk", "foreseeable misuse"
]

for doc_file in required_files:
    if exists(doc_file):
        content = read(doc_file)
        missing = [s for s in required_sections if s not in content.lower()]
        if missing:
            emit_warning(f"Art. 13: documentation missing sections: {missing}")
    else:
        emit_warning("Art. 13: no instructions for use found")
```

### GitHub Action integration

Output: warning (documentation completeness)

### Honest limits

- Cannot verify **content quality** — only that section headers exist
- Cannot verify **accuracy metrics are real** — only that the field is filled
- Cannot verify the docs match the code (drift detection not implemented)

---

## Article 14 — Human oversight

### What the law requires (verbatim)

> "High-risk AI systems shall be designed and developed... that they can be effectively overseen by natural persons... Human oversight shall aim to prevent or minimise risks... oversight measures shall be commensurate with the risks, level of autonomy and context of use... natural persons to whom human oversight is assigned are enabled... (a) to properly understand the relevant capacities and limitations... (b) to remain aware of... automation bias... (c) to correctly interpret the high-risk AI system's output... (d) to decide, in any particular situation, not to use the high-risk AI system or to otherwise disregard, override or reverse the output... (e) to intervene in the operation of the high-risk AI system or interrupt the system through a 'stop' button or a similar procedure..."

### Code-level property (5 sub-rules)

This article maps to **multiple code patterns**:

#### 14(a) — Tool inventory
```python
# Find all @tool decorated functions
tools = ast.find_all_decorated_functions(repo, decorator="tool")
# Emit: list of tools for review
```

#### 14(d) — Override mechanism exists
```python
override_patterns = ["override", "manual_approval", "human_review", "require_human"]
if not any_function_named(repo, override_patterns):
    emit_error("Art. 14(4)(d): no override mechanism found")
```

#### 14(e) — Kill switch exists
```python
kill_patterns = ["stop", "halt", "kill_switch", "interrupt", "emergency_stop", "abort"]
if not any_function_named(repo, kill_patterns):
    emit_error("Art. 14(4)(e): no kill switch found")
```

#### 14 — Destructive tools lack approval
```python
# AST: find @tool functions with destructive verbs
destructive_verbs = ["delete", "remove", "drop", "send", "transfer", "charge", "pay", "deploy", "terminate"]
for tool in tools:
    if any(verb in tool.name for verb in destructive_verbs):
        if not has_decorator(tool, "require_approval"):
            emit_error(f"Art. 14: destructive tool '{tool.name}' lacks approval gate")
```

#### 14 — Loop iteration limit
```python
# AST: agent.run() loops should have iteration limits
for loop in repo:
    if contains_call(loop, "agent.run") or contains_call(loop, "agent.invoke"):
        if not has_break_condition(loop) and not has_max_iteration(loop):
            emit_warning("Art. 14: agent loop without iteration limit")
```

### GitHub Action integration

Output: error (these are required controls)

### Honest limits

- Cannot verify **kill switch is reachable from production** — only that the function exists
- Cannot verify **override is actually exposed to deployers** — only that the function exists
- Cannot verify **approval gate actually runs** (runtime property)
- Cannot verify **iteration limits are sane** (just that they exist)

---

## Article 19 — Automatically generated logs (retention)

### What the law requires (verbatim)

> "Providers of high-risk AI systems shall keep the logs referred to in Article 12(1)... Logs shall be kept for a period appropriate to the intended purpose of the high-risk AI system, of at least six months, unless provided otherwise..."

### Code-level property

**Log retention is configured for ≥180 days**.

### Scanner rule

**Pattern type**: config file regex

```python
config_patterns = [
    # Cloud storage lifecycle
    ("**/lifecycle*.json", r'"ExpirationInDays":\s*(\d+)'),
    ("**/s3*.tf", r"lifecycle_rule.*expiration_days\s*=\s*(\d+)"),
    ("**/cloudformation*.yaml", r"ExpirationInDays:\s*(\d+)"),
    
    # Application log retention
    ("**/logging*.py", r"retention_days\s*=\s*(\d+)"),
    ("**/log_config*.yaml", r"retention:\s*(\d+)\s*days?"),
    ("**/docker-compose*.yml", r"LOG_RETENTION\s*=\s*(\d+)"),
]

for pattern, regex in config_patterns:
    for file in glob(pattern):
        matches = re.findall(regex, file.read_text())
        for days in matches:
            if int(days) < 180:
                emit_warning(f"Art. 19: retention {days} days < 180 required")
```

### GitHub Action integration

Output: warning

### Honest limits

- Cannot verify **retention is actually enforced** (just configured)
- Cannot verify **logs are kept in tamper-resistant storage**
- Only checks common config formats — customer-specific configs may be missed

---

## Article 50 — Transparency obligations for users

### What the law requires (verbatim)

> "Providers shall ensure that AI systems intended to interact directly with natural persons are designed and developed in such a way that the natural persons concerned are informed that they are interacting with an AI system... Providers of AI systems... generating synthetic audio, image, video or text content, shall ensure that the outputs of the AI system are marked in a machine-readable format and detectable as artificially generated or manipulated..."

### Code-level property (2 sub-rules)

#### 50(1) — User-facing AI disclosure
```python
# Detect UI components that handle AI responses
ui_files = find_files_matching([
    "**/*.tsx", "**/*.jsx", "**/*.vue", "**/*.svelte",
    "**/templates/**/*.html"
])

# Check for disclosure text patterns
disclosure_patterns = [
    r"AI\s+(assistant|chatbot|system)",
    r"(powered by|talking to|chatting with)\s+(an?\s+)?AI",
    r"automated\s+(response|message)",
    r"this (is|response is)\s+(generated|automated)",
]

for ui_file in ui_files:
    content = ui_file.read_text()
    if is_ai_response_component(content):  # heuristic: contains LLM call result
        if not has_disclosure(content, disclosure_patterns):
            emit_error(f"Art. 50(1): AI disclosure missing in {ui_file}")
```

#### 50(2) — AI-generated output marked
```python
# Detect output rendering code that doesn't mark AI origin
output_files = find_files_handling_llm_response()
for file in output_files:
    if not marks_ai_origin(file):  # contains C2PA, ai_generated flag, etc.
        emit_warning("Art. 50(2): AI-generated output not marked")
```

### GitHub Action integration

Output: error (Art. 50(1)) / warning (Art. 50(2))

### Honest limits

- Cannot verify **disclosure is visible to user** — only that text exists in code
- Cannot verify **disclosure language is clear** — only that strings match patterns
- Cannot verify **watermarking effectiveness** (C2PA, etc.)
- Multi-language support needed for non-English UIs

---

## Article 86 — Right to explanation of individual decision-making

### What the law requires (verbatim)

> "Any affected person subject to a decision which is taken by the deployer on the basis of the output from a high-risk AI system... shall have the right to obtain from the deployer clear and meaningful explanations of the role of the AI system in the decision-making procedure and the main elements of the decision taken."

### Code-level property

**Explanation API endpoint exists** for affected persons to request explanations.

### Scanner rule

**Pattern type**: route definition regex

```python
# Find API routes
routes = find_routes(repo)

# Check for explanation endpoint
explanation_patterns = [
    r"/explain", r"/decision/.*/explain",
    r"/appeals?", r"/review",
    r"/api/v\d+/decisions?/.*"
]

if not any_route_matches(routes, explanation_patterns):
    emit_warning("Art. 86: no explanation endpoint found")
```

### GitHub Action integration

Output: warning (explanation endpoint is a process requirement)

### Honest limits

- Cannot verify **explanation quality** — only that endpoint exists
- Cannot verify **endpoint returns useful explanations**
- Cannot verify **explanation is provided in timely manner**
- This is **mostly process**

---

## GitHub Action architecture

### Repository structure

```
eu-ai-compliance/
├── action.yml                    # GitHub Action manifest
├── Dockerfile                    # Container image
├── entrypoint.sh                 # Runs scanner
├── scanner/
│   ├── main.py                   # CLI entry, SARIF output
│   ├── tree_sitter_runner.py     # AST runner
│   ├── rule_engine.py            # Rule loader
│   └── rules/
│       ├── ai_act/
│       │   ├── art_5_prohibited.py
│       │   ├── art_10_governance.py
│       │   ├── art_12_logging.py
│       │   ├── art_13_documentation.py
│       │   ├── art_14_oversight.py
│       │   ├── art_19_retention.py
│       │   ├── art_50_disclosure.py
│       │   └── art_86_explanation.py
│       └── shared/
│           ├── destructive_verbs.py
│           └── llm_api_patterns.py
└── tests/
    ├── fixtures/
    └── test_rules.py
```

### action.yml

```yaml
name: 'EU AI Compliance Scanner'
description: 'Static analysis for EU AI Act, GDPR, CRA compliance'
inputs:
  framework:
    description: 'Frameworks to check (ai-act, gdpr, cra)'
    required: false
    default: 'ai-act'
  fail-on:
    description: 'Severity to fail on (error, warning, none)'
    required: false
    default: 'error'
runs:
  using: 'docker'
  image: 'Dockerfile'
  args:
    - ${{ github.workspace }}
    - ${{ github.workspace }}/compliance.sarif
```

### Dockerfile

```dockerfile
FROM python:3.12-slim
RUN pip install tree-sitter tree-sitter-python tree-sitter-typescript \
    tree-sitter-go tree-sitter-rust
COPY scanner/ /scanner/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

### entrypoint.sh

```bash
#!/bin/bash
set -e
REPO_PATH=$1
OUTPUT_PATH=$2
python3 /scanner/main.py \
  --repo "$REPO_PATH" \
  --output "$OUTPUT_PATH" \
  --framework "${FRAMEWORK:-ai-act}"
```

### Customer workflow

```yaml
# .github/workflows/eu-ai-compliance.yml
name: EU AI Compliance
on:
  pull_request:
    paths: ['**/*.py', '**/*.ts', '**/*.tsx']
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: eu-ai-compliance/scan-action@v1
        with:
          framework: ai-act
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: compliance.sarif
```

### PR comment output

```
## EU AI Compliance Report

❌ **FAIL** — 2 errors, 1 warning

### AI Act Art. 14(4)(e) — Kill switch missing
📄 `src/agent/index.ts` — line 1
> No `stop()`, `halt()`, or `kill_switch()` function detected in agent code.

### AI Act Art. 12 — LLM call without logging
📄 `src/services/openai.ts` — line 18
> `openai.chat.completions.create()` lacks `logger.*` call within 5 lines.

### AI Act Art. 50(1) — User disclosure missing
� `src/components/ChatWindow.tsx` — line 42
> No "AI" disclosure text found in user-facing chat component.

[View raw SARIF](../blob/main/compliance.sarif)
```

---

## What we CAN verify (deterministic, in code)

| Article | Verification |
|---|---|
| Art. 5 | ✅ Negative pattern: prohibited terms in code |
| Art. 12 | ✅ AST: log call within proximity of LLM call |
| Art. 13 | ✅ File presence + section headers |
| Art. 14 | ✅ AST: kill switch, override, approval gates, tool inventory, loop bounds |
| Art. 19 | ⚠️ Config regex: retention ≥180 days |
| Art. 50 | ✅ Regex: UI disclosure text, output marking |

## What we CANNOT verify (process, runtime, runtime)

| Article | Why not |
|---|---|
| Art. 10 | Bias is runtime property; we can only detect scripts exist |
| Art. 9 | Risk management is process documentation |
| Art. 11 | Technical documentation generation is separate feature |
| Art. 21 | Cooperation with authorities is process |
| Art. 55 | GPAI systemic risk requires testing infrastructure |
| Art. 86 | Explanation quality is process |
| Art. 5 | Cannot verify prohibited features are NOT executed (only NOT referenced) |
| Art. 14 | Cannot verify kill switch is reachable from production |
| Art. 19 | Cannot verify retention is actually enforced |

## What we explicitly do NOT do

- ❌ Evaluate model bias or fairness metrics
- ❌ Verify LLM output quality or safety
- ❌ Test prompt injection resistance (runtime property)
- ❌ Detect training data poisoning
- ❌ Verify explanation quality
- ❌ Assess whether human oversight is "effective" (subjective)
- ❌ Stream runtime audit logs to anywhere
- ❌ Require customer SDK adoption

## Honest scope statement

> **"We detect code patterns that indicate non-compliance with EU AI Act articles. We do not evaluate runtime behavior, model quality, training data, or human oversight effectiveness. Those require running the system or human review."**

## Buildable in 4 weeks

- Week 1: Engine + Art. 5, 12, 14(e), 48, 50
- Week 2: Art. 14(d), 14 tool inventory, 19, 13
- Week 3: GitHub Action wrapper, testing on 10 repos
- Week 4: Polish, docs, publish to GitHub Marketplace

**Total**: 11 deterministic rules, GitHub Action, $0 infrastructure.

## Open question for product

Do we publish the rules as **open source** (community contributions) or **proprietary** (controlled)?

**Open source pros**: faster rule development, community trust, easier adoption
**Proprietary pros**: differentiation, monetization, controlled quality

My recommendation: **hybrid** — engine is open source, rules are proprietary + premium rule packs.

---

## Next steps

1. ✅ Document each article (this file)
2. ⏭ Write the engine (Python + tree-sitter, ~200 LOC)
3. ⏭ Implement 5 HIGH-confidence rules
4. ⏭ Test on 10 of our 100 EU repos
5. ⏭ Build GitHub Action wrapper
6. � Publish to GitHub Marketplace

**The product is: a GitHub Action that runs 11 static analysis rules on customer PRs and posts findings as PR comments. No backend. No SDK. No streaming. Just deterministic code checks.**
