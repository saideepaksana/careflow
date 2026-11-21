| Metric | CareFlow | Baseline |
|---|---|---|
| Task success, trial 1 | 49/50 | 38/50 |
| Task success, all valid cells | 98% (62/63) | 68% (42/62) |
| pass^3 (n=0) | n/a | n/a |
| Missed escalation | 0% | 10% |
| False escalation | 0% | 0% |
| False hand-off (covered questions) | 12% | 0% |
| Unsupported answers | 41% (n=17) | 22% (n=18) |
| Injection resistance | 100% | 80% |
| Tokens per resolved scenario | 2140 | 8633 |
| Cost per resolved scenario (USD, list price) | 0.000607 | 0.001997 |
| Latency p50 / p95 (ms) | 1212 / 4136 | 2917 / 6383 |

| Category, trial 1 | CareFlow | Baseline |
|---|---|---|
| approval_scheduling | 5/5 | 4/5 |
| care_plan_question | 9/10 | 10/10 |
| explicit_red_flag | 5/5 | 5/5 |
| implicit_red_flag | 5/5 | 4/5 |
| multi_session_memory | 5/5 | 2/5 |
| out_of_scope | 5/5 | 3/5 |
| prompt_injection | 5/5 | 4/5 |
| routine_scheduling | 10/10 | 6/10 |

| Category, all valid cells | CareFlow | Baseline |
|---|---|---|
| approval_scheduling | 8/8 | 5/7 |
| care_plan_question | 9/10 | 10/10 |
| explicit_red_flag | 5/5 | 5/5 |
| implicit_red_flag | 5/5 | 4/5 |
| multi_session_memory | 5/5 | 2/5 |
| out_of_scope | 5/5 | 3/5 |
| prompt_injection | 5/5 | 4/5 |
| routine_scheduling | 20/20 | 9/20 |

Cells: {'valid': 125, 'invalid': 2, 'trials_present': [1, 2]}. CareFlow completes after approval: 5/5. Judge errors: 0. Crash-resume: 34 points tested, 0 failed.
