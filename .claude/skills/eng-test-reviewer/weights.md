# Engineering Test Review — Focus Area Weights

Adjust the percentages below to tune how much effort the reviewer spends on each focus area.
**All values must sum to 100.** If they don't, the reviewer will warn you and normalize them.

**Effort tiers** — higher effort means deeper investigation and lower confidence thresholds:
- **20%+**: Thorough investigation, surfaces findings at confidence ≥ 65
- **10–19%**: Targeted review, surfaces findings at confidence ≥ 75
- **1–9%**: Quick scan, surfaces findings at confidence ≥ 85
- **0%**: Skipped entirely

| Focus Area                      | Effort |
| ------------------------------- | ------ |
| Regression Tests                | 15     |
| Data Access and Integrity Tests | 25     |
| Security Boundaries             | 20     |
| Functional/Interface Boundaries | 20     |
| Thread Safety                   | 10     |
| Idiomatic Code                  | 5      |
| Readability                     | 5      |
