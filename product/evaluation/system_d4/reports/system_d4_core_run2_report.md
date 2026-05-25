# System D4 — D3 regression check

Confirms every D3 field is forwarded verbatim by the D4 wrapper across Run 2 core and the four stress axes. Match rates must be 1.000.

| field | match rate |
|---|---:|
| intent | 1.000 |
| answerability | 1.000 |
| warnings | 1.000 |
| evidence_paths | 1.000 |
| missing_fields | 1.000 |
| next_actions | 1.000 |
| behavior_class | 1.000 |
| **all_fields** | **1.000** |

n_cases: 156

### Per-axis breakdown

| axis | n | all_fields_match |
|---|---:|---:|
| axis1_lookalike | 24 | 1.000 |
| axis2_ood_premises | 24 | 1.000 |
| axis3_semantic | 24 | 1.000 |
| axis4_payload | 24 | 1.000 |
| core_run2 | 60 | 1.000 |
