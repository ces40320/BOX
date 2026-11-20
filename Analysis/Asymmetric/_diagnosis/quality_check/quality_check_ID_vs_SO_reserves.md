# ID moment vs SO actuator force (successful SO only)

Question: ID L5–S1 moments look ≫ `optimal_force` (10/5/5 Nm). On trials where SO **finished**, do the SO `torque_L5_S1_*` / `residual_pelvis_*` forces stay near those limits, or do they also go large?

Pairs: HeavyHand SO + HeavyHand ID → `quality_check_ID_vs_SO_reserves.csv` (n=523).

## Result (HeavyHand)

| coord | limit | ID max median | SO force median | ID/limit | SO/limit | % SO>limit |
|-------|-------|---------------|-----------------|----------|----------|------------|
| L5_S1_Flex_Ext | 10 | 201.7 | 3.0 | 20.17 | 0.30 | 10% |
| L5_S1_Lat_Bending | 5 | 49.3 | 0.2 | 9.86 | 0.03 | 7% |
| L5_S1_axial_rotation | 5 | 35.9 | 1.5 | 7.17 | 0.29 | 20% |
| pelvis_list | 80 | 170.4 | 170.4 | 2.13 | 2.13 | 100% |
| pelvis_tilt | 80 | 56.0 | 56.1 | 0.70 | 0.70 | 21% |
| pelvis_ty | 200 | 129.3 | 129.3 | 0.65 | 0.65 | 11% |
| arm_flex_r | 200 | 22.6 | 22.6 | 0.11 | 0.11 | 1% |

## Interpretation

- OpenSim SO `*_force.sto` columns for CoordinateActuators are **actuator forces** ≈ `control × optimal_force`. So `so_ratio = so_max/limit` is approximately **|control|**.
- If SO stayed “within intended capacity”, SO/limit would cluster near ≤1. If SO also exceeds, the optimizer is freely using |control|≫1 (allowed by min/max_control=±10000) — ID’s large moments are then **real demand**, not an ID-only artifact.

**Finding:** Successful SO keeps L5 FE near the limit (SO/limit median=0.30) while ID/limit=20.17 — muscles would then be carrying most of the ID moment.

MeasuredEHF companion table: `quality_check_ID_vs_SO_reserves_MeasuredEHF.csv`.
