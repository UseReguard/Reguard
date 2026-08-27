"""Taxonomy + rule-based classifier for runtime-testability of AI Act provisions.

This module encodes the assessment taxonomy the user defined and a
deterministic rule-based heuristic that proposes a classification for
each atomic obligation. The heuristic is intentionally conservative —
its job is to surface a candidate classification that a human reviewer
confirms or rejects, not to make final calls.

Taxonomy (per the user spec):

    RUNTIME_TESTABLE
        The obligation can be verified or falsified by executing an
        AI-agent system under controlled conditions. Must satisfy all
        four testability rule elements:
            precondition, stimulus, observable, assertion.

    PARTIALLY_RUNTIME_TESTABLE
        The obligation has SOME testable elements but also requires
        evidence outside runtime observation (e.g. a documented
        process, a vendor attestation, a deployed-system check).

    AGENT_RELEVANT_NOT_RUNTIME_TESTABLE
        The obligation is about AI-agent systems but cannot be reduced
        to a deterministic runtime observation (e.g. "appropriate"
        judgment, "reasonable" effort, organisational governance).

    PROCESS_OR_DOCUMENTATION
        The obligation is satisfied by producing a document, a record,
        a notification, or by following a process. It is testable in
        the sense that the artifact's existence can be observed, but
        the substantive judgment lives in the document content.

    MODEL_LEVEL
        The obligation governs the model itself (training data,
        training procedure, accuracy metrics on benchmarks) — not the
        runtime behaviour of a deployed agent. Outside the agent-
        system boundary for our compliance work.

    APPLICABILITY_ONLY
        The article is conditional on a scope trigger (e.g. "high-risk
        AI systems", "providers established in the Union"). It declares
        WHO the obligation applies to, but is not itself an obligation
        a runtime can verify in isolation.

    NOT_AGENT_SYSTEM_RELEVANT
        The provision is not about AI-agent systems (definitions,
        committee structures, dates of application, etc.). Out of scope.

    UNCLEAR
        The classifier could not determine a category. Human review
        required.

The classifier is a thin heuristic. It uses the article title and the
obligation text to pick a label. Anything it is not confident about
falls through to UNCLEAR. The point is to make the review queue
manageable, not to make final calls.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional


# Allowed classification labels — used as a CHECK CONSTRAINT surrogate.
CLASSIFICATIONS = frozenset({
    "RUNTIME_TESTABLE",
    "PARTIALLY_RUNTIME_TESTABLE",
    "AGENT_RELEVANT_NOT_RUNTIME_TESTABLE",
    "PROCESS_OR_DOCUMENTATION",
    "MODEL_LEVEL",
    "APPLICABILITY_ONLY",
    "NOT_AGENT_SYSTEM_RELEVANT",
    "UNCLEAR",
})


@dataclass(frozen=True)
class TestabilityRule:
    """The strict testability rule from the user spec.

    All four fields are required for a RUNTIME_TESTABLE verdict.
    """
    precondition: str   # setup that must hold before the test runs
    stimulus: str       # input / action applied to the system
    observable: str     # what the runtime can record / measure
    assertion: str      # the pass/fail condition


@dataclass
class ProposedAssessment:
    """The classifier's proposal for one atomic obligation."""
    classification: str
    agent_system_relevant: bool
    applicability_note: Optional[str] = None
    testability_rule: Optional[TestabilityRule] = None
    notes: str = ""


# ---------------------------------------------------------------------------
# Heuristic signals — keyword bags keyed by classification
# ---------------------------------------------------------------------------

# Titles of articles that are pure applicability / scope gates.
APPLICABILITY_TITLE_KEYWORDS = (
    "subject matter", "scope",
)

# Titles of articles that are pure definitions (NOT_AGENT_SYSTEM_RELEVANT
# for the obligation table — definitions support interpretation, they
# are not obligations).
DEFINITIONS_TITLE_KEYWORDS = (
    "definitions",
)

# Verb / noun signals that suggest the obligation is a documentation
# / process requirement rather than a runtime behaviour. Matched as
# regex on the lower-cased text so intervening adverbs do not break
# the match (e.g. "shall be appropriately documented" still fires).
DOCUMENTATION_VERB_SIGNALS = (
    r"shall (?:be )?(?:appropriately )?documented",
    r"shall (?:be )?(?:kept|retained|preserved)",
    r"shall (?:be )?made available",
    r"shall provide documentation",
    r"technical documentation",
    r"instructions for use",
    r"shall (?:keep|retain|preserve|draw up|maintain)",
    r"record-keeping",
    r"documentation (?:keeping|and )",
    r"quality management system",
    r"post-market monitoring",
    r"serious incident reporting",
    r"notification",
    r"cooperation with",
    r"corrective action",
    r"shall (?:be )?(?:accompanied|supported) by",
    r"shall (?:put|place) (?:on the market|into service)",
)

# Verbs that suggest the obligation is about system behaviour that
# could be observed at runtime. Same adverb-tolerant regex approach.
BEHAVIOUR_VERB_SIGNALS = (
    r"shall (?:[\w-]+ )?allow for",
    r"shall (?:[\w-]+ )?enable",
    r"shall (?:[\w-]+ )?provide",
    r"shall (?:be )?(?:designed|developed|tested|equipped|displayed|overseen|transparent|capable of)",
    r"shall (?:be )?able to",
    r"shall (?:automatically|continuously|by default)",
    r"shall (?:log|record|detect|prevent|mitigate|monitor|trace|track|flag|warn|alert|refuse|reject|interrupt|halt|stop|pause|continue|resume)",
    r"shall (?:be )?(?:interoperable|resilient|robust|secure)",
    r"shall (?:ensure|guarantee|maintain)",
    r"shall (?:bear|have|include|contain)",
    r"shall (?:be )?interpreted",
    r"shall (?:be )?(?:resistant|protected)",
)

# Title signals for prohibited practices and bans (Article 5) — these
# are runtime-testable in principle: an agent performing a banned
# practice fails compliance. But they require specific stimuli.
PROHIBITED_TITLE_KEYWORDS = (
    "prohibited",
)

# Signals suggesting the obligation is model-level (training, accuracy,
# dataset characteristics).
MODEL_LEVEL_SIGNALS = (
    r"training (?:data|procedure|process)",
    r"validation and testing data sets?",
    r"data sets? shall",
    r"accuracy",
    r"robustness",
    r"cybersecurity",
    r"data governance",
    r"data[- ]preparation",
    r"annotation",
    r"labelling",
    r"biases?",
)


def _has_any(text_lower: str, signals: tuple[str, ...]) -> bool:
    return any(re.search(s, text_lower) for s in signals)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
def classify_atomic(
    *,
    article_title: str,
    atomic_text: str,
) -> ProposedAssessment:
    """Propose a classification for one atomic obligation.

    The classifier is deterministic and conservative. Where multiple
    categories could apply, it picks the MOST SPECIFIC (deepest in the
    taxonomy) and falls back to UNCLEAR when no signal fits.
    """
    title_lower = (article_title or "").strip().lower()
    text_lower = (atomic_text or "").strip().lower()

    # 1. Definitions article → every atomic is a definition, not an
    #    obligation. Mark NOT_AGENT_SYSTEM_RELEVANT so the review queue
    #    can confirm and skip.
    if any(k in title_lower for k in DEFINITIONS_TITLE_KEYWORDS):
        return ProposedAssessment(
            classification="NOT_AGENT_SYSTEM_RELEVANT",
            agent_system_relevant=False,
            notes="Definitions article: obligations are definitions, not "
                  "testable requirements.",
        )

    # 2. Subject matter / scope article → applicability gate.
    if any(k in title_lower for k in APPLICABILITY_TITLE_KEYWORDS):
        return ProposedAssessment(
            classification="APPLICABILITY_ONLY",
            agent_system_relevant=False,
            notes="Scope / subject-matter article: declares applicability, "
                  "not a runtime obligation.",
        )

    # 3. Prohibited practices → runtime-testable in principle (a
    #    banned behaviour either occurs or doesn't).
    if any(k in title_lower for k in PROHIBITED_TITLE_KEYWORDS):
        return ProposedAssessment(
            classification="PARTIALLY_RUNTIME_TESTABLE",
            agent_system_relevant=True,
            applicability_note="Triggers: Article 5 list — applies to any "
                               "AI system, not only high-risk.",
            testability_rule=TestabilityRule(
                precondition="system presents the stimulus described in "
                             "the provision",
                stimulus="the specific prohibited input / use case",
                observable="system output / behaviour",
                assertion="system does not produce the prohibited outcome",
            ),
            notes="Banned practice. Runtime check needs the precise "
                  "stimulus described in the provision; some prohibited "
                  "practices require subjective judgement (e.g. "
                  "'manipulative') and may be PARTIALLY rather than "
                  "fully runtime-testable.",
        )

    # 4. Heuristic on the obligation text.
    is_doc = _has_any(text_lower, DOCUMENTATION_VERB_SIGNALS)
    is_beh = _has_any(text_lower, BEHAVIOUR_VERB_SIGNALS)
    is_model = _has_any(text_lower, MODEL_LEVEL_SIGNALS)

    # When BOTH behaviour AND model signals fire, the obligation is
    # about dataset / model properties but expressed with behaviour
    # verbs ("data sets shall have...", "the model shall detect...").
    # This is genuinely ambiguous — fall through to UNCLEAR rather
    # than picking one bucket, so the human reviewer decides.
    if is_model and is_beh:
        return ProposedAssessment(
            classification="UNCLEAR",
            agent_system_relevant=False,
            notes="Both model-level and behaviour-verb signals fired. "
                  "Likely a model-level obligation expressed with "
                  "behaviour verbs (e.g. \"data sets shall have\"). "
                  "Reviewer: decide between MODEL_LEVEL and "
                  "RUNTIME_TESTABLE.",
        )

    # Model-level obligations are about training/eval, not runtime.
    if is_model:
        return ProposedAssessment(
            classification="MODEL_LEVEL",
            agent_system_relevant=False,
            notes="Concerns training data, accuracy benchmarks, or "
                  "model-level properties — outside the agent-system "
                  "runtime boundary.",
        )

    # Documentation-first: when an obligation has doc signals AND
    # behaviour signals (e.g. "the technical documentation shall
    # contain..."), classify as PROCESS_OR_DOCUMENTATION. The
    # behaviour verb just describes what the document contains, not
    # runtime behaviour.
    if is_doc:
        return ProposedAssessment(
            classification="PROCESS_OR_DOCUMENTATION",
            agent_system_relevant=True,
            notes="Document/process obligation. Runtime can only verify "
                  "the artifact exists at the right path; the "
                  "substantive judgment lives in the document content.",
        )

    # Behaviour-shape obligations with a behavioural verb are the
    # primary RUNTIME_TESTABLE candidates — IF the four-element
    # rule can be satisfied.
    if is_beh:
        return ProposedAssessment(
            classification="RUNTIME_TESTABLE",
            agent_system_relevant=True,
            testability_rule=TestabilityRule(
                precondition="system is deployed in a controlled runtime "
                             "with logging enabled",
                stimulus="normal operation of the system in scope",
                observable="system logs / output / interface state",
                assertion="observable matches the obligation's required "
                          "behaviour",
            ),
            notes="Behaviour-shaped obligation. Runtime testability "
                  "proposed — confirm that the obligation's "
                  "behaviour is unambiguous and observable.",
        )

    # Nothing matched → review needed.
    return ProposedAssessment(
        classification="UNCLEAR",
        agent_system_relevant=True,
        notes="Classifier could not assign a category with confidence. "
              "Human review required.",
    )


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def testability_rule_to_json(rule: Optional[TestabilityRule]) -> Optional[str]:
    if rule is None:
        return None
    return json.dumps({
        "precondition": rule.precondition,
        "stimulus": rule.stimulus,
        "observable": rule.observable,
        "assertion": rule.assertion,
    }, ensure_ascii=False, indent=2)


def testability_rule_from_json(blob: Optional[str]) -> Optional[dict]:
    if not blob:
        return None
    return json.loads(blob)
