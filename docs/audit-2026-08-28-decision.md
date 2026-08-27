# Audit Decision Framework

Once the fresh audit metrics are in, the framework for whether to scale
discoveries to 5,000 is:

| Strict accepted precision | Next step |
|---|---|
| ≥ 90% | Resume discovery: run remaining queries, target 5,000 candidates |
| 80–89% | Iteratively tune classifier; expand domain hints / positive categories; re-run reclassify; re-audit |
| < 80% | Halt. Treat current 1,105 as final corpus; flag for manual review |

Confidence-interval check:
- 95% CI half-width = 1.96 × √(p(1−p)/n)
- At n = 100, p = 0.90 → half-width = ±5.9pp → CI [84.1%, 95.9%]
- At n = 100, p = 0.85 → half-width = ±7.0pp → CI [78.0%, 92.0%]

If strict precision is close to 90% but the CI crosses 90%, prefer more
samples in the contested precision range or hand-audit contested rows.
