"""Compliance requirements: deterministic legal assertions.

A requirement is a single legal clause (e.g. AI Act Article 12(1))
turned into a deterministic runtime test. The pipeline discovers which
requirement applies to a repository, runs the matching adapter,
collects evidence, and asks the requirement to score it.

Modules
-------
legal_text_parser    EU article text → atomic obligations (paragraph × point).
article_classifier   Heuristic runtime-testability classifier (audit-side).
base                 RequirementTest base class + registry.
ai_act               Concrete AI Act requirements (e.g. article_12_1).
"""