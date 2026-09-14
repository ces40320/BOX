# FreeBox — planning doc (document label: LoadShare)

- **Code / PATH_RULE app**: **FreeBox**
- **Document / figure legend label**: **LoadShare**
- **Branch** (historical remote name): `cursor/boxwrench-0490`
- **Location**: `Codes/c_Run_Tools/FreeBox/`
- **Vendor reference only**: `_vendor/` (runtime must **not** import General)
- **Structure report**: `FREEBOX_STRUCTURE.md`

## Status (2026-09-15)

| Asset | Status |
|-------|--------|
| Vendor APP5 + General (reference only) | Present under `_vendor/` |
| Reference `BOX.osim` (15.03 kg, no markers) | `models/BOX.osim` |
| Marked free box | `models/BOX_with_markers.osim` (8 corners + L/R handle) |
| Mass scale 15 kg → condition kg | `freebox_inertia.py` |
| Allocation × RiCTO gate → ExtLoad | Wired; synthetic smoke **OK** |
| Free-box IK + BK + States | `freebox_opensim.py` (vendor Load* pattern) |
| Real sample **260526_PJH** (SUB7) | `7kg_10bpm` / `1AB` path wired |

## Sample subject: 260526_PJH (SUB7)

| Item | Value |
|------|--------|
| SUB_Info key | `260526_PJH` |
| Protocol | Asymmetric |
| SUB label | SUB7 |
| Sample condition / segment | `7kg_10bpm` / `1AB` (error_log excludes `2CA`, `4CA`, `9AB`) |

### Experiment (Dropbox)

- `E:\Dropbox\SEL\BOX\Experiment\260526_PJH\RigidBody\7kg_10bpm_rigidbody.csv` (+ 15 kg / 16 bpm)
- `E:\Dropbox\SEL\BOX\Experiment\260526_PJH\Labeled\7kg_10bpm.c3d` (+ static / other conditions)

### OpenSim_Process (Dropbox `_Main_`; local tree may be empty)

- Markers: `…/Asymmetric/SUB7/7kg_10bpm/AB/Markers/SUB7_7kg_10bpm_1AB.trc` (includes LTA_BOX…RBP_BOX)
- HeavyHand ExtLoad: `…/AB/ExtLoad/SUB7_7kg_10bpm_1AB_ExtLoad_HeavyHand.mot`
- Free-box outputs (written by FreeBox):
  - `…/AB/IK_Load/SUB7_7kg_10bpm_1AB_Load_IK.mot`
  - `…/AB/BK_Load/SUB7_7kg_10bpm_1AB_Load_BodyKinematics_{pos,vel}_global.sto`
  - `…/AB/States_Load/SUB7_7kg_10bpm_1AB_Load_StatesReporter_states.sto`
  - ExtLoad: `…/AB/ExtLoad/SUB7_7kg_10bpm_1AB_ExtLoad_FreeBox.mot`

### RiCTO / Analysis

- PATH_RULE: `Analysis/Asymmetric/RiCTO/TimeSeries/SUB7/7kg_10bpm/SUB7_7kg_10bpm_1AB_RiCTO_timeseries.csv`
- FreeBox forces CSV: `Analysis/Asymmetric/FreeBox/TimeSeries/SUB7/7kg_10bpm/SUB7_7kg_10bpm_1AB_FreeBox_forces.csv`
- Gate: RiCTO contact window (`w_smooth` / `w_rect`); **no** MeasuredEHF hand-column copy; hand torques **0**; hand3=L, hand4=R

## CAD / excel findings (handle + markers)

### Handle centers (physical ML ≈ ±0.160 m)

| Frame | L (hand3) | R (hand4) | Source |
|-------|-----------|-----------|--------|
| **Motive RB / MeasuredEHF** | `(-0.16001, 0.0158, 0.00041)` m | `(0.16007, 0.0158, 0.00041)` m | Excel “Transverse in OpenSim”; `config_exp_settings.D3/D4` |
| **CAD / BOX body (ADDBOX)** | `(0.0, 0.0158, -0.16001)` m | `(0.0, 0.0158, 0.16007)` m | Same offset; ML on **Z** after STL import |

FreeBox OpenSim allocation uses the **CAD body** row (`HANDLE_L_NOM` / `HANDLE_R_NOM`).

### Corner markers → Motive Marker1–8

| Motive | OpenSim / C3D |
|--------|----------------|
| Marker1…4 | LTA/LTP/LBA/LBP_BOX |
| Marker5…8 | RTA/RTP/RBA/RBP_BOX |

## Method

1. **Free-box IK** on segment TRC (8 box corners) with `BOX_with_markers.osim`.
2. **BodyKinematics** (pos/vel) + **StatesReporter** (ω) on that IK MOT.
3. **Box COM wrench** — COM accel + ω̇ → `F`, `M` (`freebox_kinematics`).
4. **L/R allocation** — SLSQP at CAD handle centers (`freebox_allocate`).
5. **RiCTO gate** — multiply hand forces by smooth/rect weight during handle contact window.
6. **ExtLoad** — HeavyHand GRF template; hand3=L, hand4=R (`freebox_extload`).

## Module layout

```
FreeBox/
├─ FREEBOX_PLAN.md
├─ run_freebox.py              # CLI; --synthetic | --namecode 260526_PJH
├─ build_box_model_with_markers.py
├─ freebox_config.py           # SAMPLE_* defaults = 260526_PJH
├─ freebox_paths.py            # Dropbox vs local OpenSim_Process resolve
├─ freebox_opensim.py          # free-box IK / BK / States (no vendor import)
├─ freebox_markers.py
├─ freebox_rotation.py
├─ freebox_inertia.py
├─ freebox_kinematics.py
├─ freebox_allocate.py
├─ freebox_extload.py
├─ models/BOX.osim, BOX_with_markers.osim
└─ _vendor/APP5, General         # reference only
```

## Commands

```bat
:: Prefer conda env with OpenSim 4.5 bindings
C:\Users\ok\anaconda3\envs\osim\python.exe Codes\c_Run_Tools\FreeBox\run_freebox.py --namecode 260526_PJH

:: Optional overrides
…\python.exe …\run_freebox.py --namecode 260526_PJH --condition 7kg_10bpm --segment 1AB --force-kinematics

:: Synthetic (no OpenSim)
…\python.exe …\run_freebox.py --synthetic --box-mass 7
```

## Done

- [x] Package + PATH_RULE / pipeline opt-in for app `FreeBox`
- [x] Vendor APP5 adapted (no General runtime import)
- [x] CAD handle ±0.160 m; marker tables; Motive Marker1–8 map
- [x] `BOX_with_markers.osim` builder
- [x] Synthetic smoke
- [x] Free-box IK + BK + States helpers + path resolve for Dropbox `_Main_`
- [x] Sample CLI for **260526_PJH** (not 260512_HSH)

## Sample run result (2026-09-15)

Command (conda ``osim`` env):

```bat
C:\Users\ok\anaconda3\envs\osim\python.exe Codes\c_Run_Tools\FreeBox\run_freebox.py --namecode 260526_PJH --condition 7kg_10bpm --segment 1AB --force-kinematics
```

| Check | Result |
|-------|--------|
| Free-box IK | OK (~600 frames; marker RMS ≈ 4 mm) |
| BK vel/pos + States | Written under Dropbox `…/AB/BK_Load` + `States_Load` |
| RiCTO gate | `Analysis/Asymmetric/RiCTO/TimeSeries/SUB7/7kg_10bpm/…_1AB_….csv` |
| ExtLoad FreeBox | `…/ExtLoad/SUB7_7kg_10bpm_1AB_ExtLoad_FreeBox.mot` |
| Analysis CSV | `Analysis/Asymmetric/FreeBox/TimeSeries/SUB7/7kg_10bpm/…_forces.csv` |
| Allocation | `n_active≈197`, `n_success≈196` (7 kg mass scale); SLSQP bound warnings on some frames |

Default Python without OpenSim → use the ``osim`` conda interpreter above.

## Remaining

1. Validate free-BOX marker frame ASSUMPTION vs TRC residuals (tune marker locals if needed; current RMS ~4 mm is usable).
2. Optional: add `FreeBox` to default protocol `APPs` once MOT generation is routine.
3. Soften allocation bounds / init to reduce SLSQP clipping warnings during contact window.
