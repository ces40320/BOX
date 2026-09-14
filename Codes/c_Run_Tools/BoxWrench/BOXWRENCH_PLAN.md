# BoxWrench — planning doc (Approach-5 inspired, RiCTO-gated)

- **Branch (conceptual name)**: `BoxWrench`
- **Cloud / git branch used**: `cursor/boxwrench-0490` (environment requires `cursor/<name>-0490`; intended product name remains **BoxWrench**)
- **Location**: `Codes/c_Run_Tools/BoxWrench/`
- **Literature reference**: Akhavanfar et al. (2022), “Sharing the load” — Approach 5 (box 6DOF wrench → constrained L/R hand allocation). Folder/app name is **BoxWrench**, not APP5 / app5.

## Status (this scaffolding pass)

| Asset | Status |
|-------|--------|
| Approach-5 Python sources (vendor) | **NOT in workspace** — blocked |
| Box `.osim` model for Approach-5 kinematics | **NOT in workspace** — blocked |
| Repo RiCTO timing / weight API | Present (`optimization/`) |
| Repo ExtLoad MOT I/O | Present (`optimization/ricto_io.py`) |
| Repo rotation utilities | **None found** (no safe `RotMat` equivalent yet) |

**Decision**: ship folder + config/CLI stubs + PATH_RULE / pipeline hooks only. Do **not** invent a full numerical reimplementation from the paper alone.

## Method summary (target design)

1. **Box 6DOF wrench**  
   From box rigid-body pose (markers / IK / body kinematics): linear COM acceleration + angular velocity/acceleration → net force and moment at box COM (Newton–Euler). Mass / inertia come from the box model (user-provided `.osim` or documented constants).

2. **Constrained L/R allocation**  
   Allocate the net wrench to left/right hand contact forces (and optionally moments) under Approach-5-style constraints (equal/unequal share, force direction / grip assumptions as in vendor code). Mapping for this repo: **hand3 = left, hand4 = right** (same as RiCTO / ExtLoad SETUP).

3. **RiCTO timing gate (not MeasuredEHF)**  
   Contact / load timing comes from RiCTO optimized `(t1, d1, t2, d2)` and weight curves (`rect_w` / `smooth_w`) under `Codes/c_Run_Tools/optimization/`.  
   **Chosen coupling (default, documented)**: multiply allocated hand forces by RiCTO **smooth** weight (`post`-style) unless CLI overrides to `rect`. Outside contact windows, hand forces → 0.  
   **No MeasuredEHF leakage**: never copy MeasuredEHF hand force / torque / COP into BoxWrench ExtLoad.

4. **Torque policy (provisional until vendor review)**  
   Default stub policy matches RiCTO / HeavyHand: **`hand_torque3_* = hand_torque4_* = 0`** unless Approach-5 vendor code requires nonzero contact moments — then document axis frames and enable via config flag after integration.

5. **ExtLoad write**  
   Template = HeavyHand MOT (GRF plates 1–2 kept). Hand columns overwritten with BoxWrench allocation × RiCTO weight. Paths follow `PATH_RULE` (`…/ExtLoad/SUB*_…_ExtLoad_BoxWrench.mot`). Analysis CSVs under `Analysis/<protocol>/BoxWrench/`.

## Rotation / axis signs (open)

- Vendor `RotMat.py` may contain incorrect rotation matrices — **do not copy blindly**.
- This repo currently has **no** shared rotation helper under `Codes/`. After vendor sources arrive: prefer re-deriving with explicit OpenSim/ground frame assumptions, or extract only verified transforms; document R convention (body→ground vs ground→body) and marker order.
- Open questions until vendor + box model arrive:
  - Box local axes vs OpenSim ground (`+Y` up).
  - Sign of force applied **to hand** vs **to box** (RiCTO uses force of box on hand: static `fy ≈ −m|g|`).
  - Whether Approach-5 moments are about hand COP or box COM, and in which frame they enter ExtLoad.

## Reuse (do not vendor-dump “General”)

| Need | Repo equivalent |
|------|-----------------|
| Read/write ExtLoad `.mot` | `optimization/ricto_io.py` |
| Weight curves / `(t1,d1,t2,d2)` | `optimization/ricto_optimize.py`, RiCTO Analysis CSV |
| 2nd derivative / filtering | `optimization/ricto_ehf.py` (`second_derivative`) |
| Paths | `PATH_RULE.ResultPaths` / `ConditionPaths` |
| Pipeline ExtLoad SETUP / SO / JR | existing handlers; app label `BoxWrench` |

## Pipeline integration

- **Model variant**: base `SUB{n}_Scaled.osim` (same as pre/postRiCTO) — differentiation is ExtLoad, not mass variant. Revisit if box geometry model is required for SO/JR.
- **Default protocol `APPs`**: unchanged (BoxWrench is **opt-in** via `--apps BoxWrench` so existing runs are not broken).
- **Progress sheet** (`update_pipeline_progress.APPS`): not expanded yet — avoid mass “missing” rows until MOT generation is real.

## Module layout

```
Codes/c_Run_Tools/BoxWrench/
├─ BOXWRENCH_PLAN.md          ← this file
├─ __init__.py
├─ boxwrench_config.py
├─ boxwrench_kinematics.py    ← stub (needs box pose + model)
├─ boxwrench_allocate.py      ← stub (needs Approach-5 allocation)
├─ boxwrench_extload.py       ← stub skeleton (reuses ricto_io when filled)
└─ run_boxwrench.py           ← CLI stub
```

## Blocked checklist (user assets still needed)

1. Approach-5 Python sources (allocation + kinematics entry points; any deps beyond a bloated “General” tree).
2. Box `.osim` (or explicit mass, COM, inertia, marker definitions used by Approach-5).
3. Confirmation of ExtLoad torque policy from vendor method.
4. Confirmation of RiCTO weight choice (`smooth` vs `rect`) for the paper comparison arm.

## Implementation checklist

- [x] Branch + this plan
- [x] Stub package + CLI
- [x] PATH_RULE `boxwrench_*` helpers
- [x] `pipeline_rules` + runner opt-in for app `BoxWrench`
- [ ] Integrate vendor Approach-5 (adapt, no raw dump)
- [ ] Wire real kinematics / allocation / ExtLoad write
- [ ] Validate against MeasuredEHF (timing GT only; no hand-column copy)
- [ ] Optional: add `BoxWrench` to protocol `APPs` / progress sheet
