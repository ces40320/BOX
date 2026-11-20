# SO freeze vs quality metrics — culprit candidates

Cross of `pipeline_trouble.json` freeze events with `quality_check_IK/ID_reserves/scaling.csv`.
Detail table: `quality_check_SO_freeze_cross.csv` (233 freeze rows).

## Freeze landscape

- Trouble entries with `freeze_sim_time`: **233**
- SO-tagged freeze rows: **233**
- Freeze time: median **1.43 s**, range 0.02–4.85 s

| freeze window (s) | n |
|-------------------|---|
| [0.0, 0.05) | 2 |
| [0.05, 0.1) | 5 |
| [0.1, 0.2) | 3 |
| [0.2, 0.5) | 21 |
| [0.5, 1.0) | 41 |
| [1.0, 2.0) | 70 |
| [2.0, 6.0) | 91 |

## Association with quality metrics

Compared segment-level ID/IK/scaling between segments that **ever SO-froze** vs never, and HeavyHand SO **missing** vs OK:

| metric | freeze median | never median | freeze/never | HH-miss / HH-ok |
|--------|---------------|--------------|--------------|-----------------|
| `worst_ratio` | 16.55 | 21.8 | 0.759 | 0.99 |
| `ratio__L5_S1_Flex_Ext` | 16.55 | 21.8 | 0.759 | 0.99 |
| `ratio__L5_S1_axial_rotation` | 4.197 | 7.758 | 0.541 | 0.924 |
| `ratio__pelvis_list` | 2.003 | 2.286 | 0.876 | 1.09 |
| `ratio__pelvis_ty` | 0.6136 | 0.6729 | 0.912 | 1.05 |
| `ratio__arm_flex_r` | 0.09959 | 0.1173 | 0.849 | 1.03 |
| `ik_rms_mean_m` | 0.03097 | 0.03146 | 0.984 | 1.06 |
| `scale_rmse_mm` | 40.13 | 20.14 | 1.99 | 2.04 |
| `n_over_limit` | 4 | 4 | 1 | 1 |

## Interpretation (ranked suspects)

1. **L5–S1 ID demand ≫ torque actuator `optimal_force` (10/5/5 Nm)** — universal on all ID segments; not a separator of freeze vs success by itself (everyone is over), but it is the structural SO stressor. Segments with **extreme** Flex_Ext / axial ratios and **high window peaks near freeze_s** are the strongest local suspects.
2. **`pelvis_list` residual overload (80 Nm)** — also chronically over; check whether freeze windows coincide with list-moment spikes.
3. **IK marker RMS (~3 cm cohort)** — weak/moderate separator unless freeze/never or miss/ok ratios clearly >1; SUB2 nan-TRC 16 bpm are hard failures upstream of SO.
4. **Scaling (SUB1/SUB5 ~4 cm)** — subject-level risk factor; does not explain within-subject freeze times.
5. **Limb reserve 200 Nm** — rarely over limit; **unlikely primary SO freeze driver**.

## Practical next checks

- For a freeze at time `T`, plot ID `L5_S1_*_moment` and `pelvis_list_moment` and SO `torque_*` / `residual_*` controls in `[T−0.2, T+0.2]`.
- Prioritize raising L5–S1 / pelvis_list `optimal_force` (or relaxing SO) before chasing limb reserves or mild IK RMS differences.

## Confound check (important)

SO freezes in `pipeline_trouble.json` are **almost only MeasuredEHF** (230/233) and cluster on **SUB1 / SUB5 / SUB8** — the subjects that still lack nearly all HeavyHand SO outputs.

SO force.sto coverage (approx):
- SUB3/4/6/7: essentially complete all apps
- SUB1: MeasuredEHF ~14 only; HeavyHand ~0
- SUB5: ~1 per app
- SUB8: MeasuredEHF ~23; HeavyHand ~2

Therefore **scale RMSE freeze/never ≈ 2×** is largely a **subject confound** (SUB1/SUB5 bad scale + unfinished SO), not proof that scale error causes each freeze.

Within unfinished subjects, ID L5 / pelvis / arm ratios and IK RMS differ only mildly between MEHF SO-ok vs still-missing segments (see script stdout).

## Freeze-time local ID / hand-force

Sampled local peaks (`quality_check_SO_freeze_local.csv`, n=130):
- Freeze times are mostly **1–3 s into the segment** (not only t≈0 edge).
- At freeze, L5 Flex_Ext and pelvis_list moments are often a **large fraction of the segment peak** (loc/segmax frequently ≳ 0.6–0.8) → SO dies near a high-demand frame, not a random quiet frame.
- Limb arm/elbow moments stay small vs 200 Nm reserve (not the bottleneck).
- MeasuredEHF ExtLoad hand-force spikes at freeze should be inspected case-by-case (column names vary); early freezes (≤0.2 s) are few and may be edge/init issues (`RETRY_so_early_window` target).

## Ranked culprit narrative

1. **Primary structural stressor (all apps): L5–S1 torque actuators too small (10/5/5 Nm) + pelvis_list residual (80 Nm)** relative to ID. Present on *every* ID segment; explains why SO is fragile, not why SUB3 succeeded and SUB5 did not.
2. **Primary failure cluster: MeasuredEHF on unfinished subjects (SUB1/5/8)** — freeze tickets and missing SO align here. HeavyHand freezes are rare in the trouble log.
3. **Subject risk amplifiers: SUB1/SUB5 scaling (~4 cm mean body RMSE)** and SUB8 high L5 ID demand (worst_ratio often 30–40× on 15kg_16bpm) — make MeasuredEHF SO more likely to stall when demand peaks mid-segment.
4. **Weak separators: segment-mean IK RMS (~3 cm) and limb reserve usage** — do not cleanly predict freeze vs success once subject/app are controlled.
5. **Upstream hard fails: SUB2 16 bpm nan TRC** — never reach healthy SO.

## What to do next

1. Re-run / finish **HeavyHand SO** for SUB1/5/8 first (isolates ExtLoad-app effect).
2. Raise **L5–S1 and pelvis_list `optimal_force`** in model bake, regenerate osims, retry a freeze cohort (e.g. SUB8 15kg_16bpm BC).
3. For a few freezes, overlay ID L5/pelvis_list and MeasuredEHF hand force at `freeze_s` (use `quality_check_SO_freeze_cross.csv` + `*_local.csv`).
4. Keep early-edge retry for the small ≤0.2 s freeze set; most freezes need mid-trial fixes.

## opensim.log warnings on freezes (update)

See `quality_check_SO_log_warnings.md` and `quality_check_SO_log_warnings.csv`.
