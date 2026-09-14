# BoxWrench — planning doc (Approach-5 inspired, RiCTO-gated)

- **Branch**: `cursor/boxwrench-0490` (product name **BoxWrench**)
- **Location**: `Codes/c_Run_Tools/BoxWrench/`
- **Literature**: Akhavanfar et al. (2022) Approach 5 — vendor scripts under `_vendor/` (runtime must **not** import General)

## Status (2026-09-14)

| Asset | Status |
|-------|--------|
| Vendor APP5 + General (reference only) | Present under `_vendor/` |
| Reference `BOX.osim` (15.03 kg, no markers) | `models/BOX.osim` |
| Marked free box | `models/BOX_with_markers.osim` (8 corners + L/R handle) |
| CAD excel + workflow | Read from Dropbox `…/to OpenSim/1212/` |
| Mass scale 15 kg → condition kg | `boxwrench_inertia.py` |
| Allocation × RiCTO gate → ExtLoad | Wired; synthetic smoke **OK** |
| Box IK + BK pipeline (trial) | **Still needed** (see blockers) |

## CAD / excel findings (handle + markers)

### Handle centers (physical ML ≈ ±0.160 m)

| Frame | L (hand3) | R (hand4) | Source |
|-------|-----------|-----------|--------|
| **Motive RB / MeasuredEHF** | `(-0.16001, 0.0158, 0.00041)` m | `(0.16007, 0.0158, 0.00041)` m | Excel “Transverse in OpenSim”; `config_exp_settings.D3/D4` |
| **CAD / BOX body (ADDBOX)** | `(0.0, 0.0158, -0.16001)` m | `(0.0, 0.0158, 0.16007)` m | Same offset; ML on **Z** after STL import |

BoxWrench OpenSim allocation uses the **CAD body** row (`HANDLE_L_NOM` / `HANDLE_R_NOM`). Vendor paper-box `HANDLE_Z_NOM=0.17` replaced by **0.160**.

### Corner markers (workflow step 8 / ADDBOX / 마커셋 위치 조절.xlsx)

On `box_15kg_half_l` / `_r` (m):

| Marker | Parent | Location |
|--------|--------|----------|
| LTA/LTP/LBA/LBP | half_l | `(0.3496,0.295,0.01539)` … `(0.0704,0.015,-0.01461)` |
| RTA/RTP/RBA/RBP | half_r | `(0.3496,0.295,0.19312)` … `(0.0704,0.015,0.22312)` |

Free `BOX_with_markers.osim` maps R → left-half frame via weld Δz = 0.205 m (**ASSUMPTION**: free BOX body ≈ left-half CAD frame).

### Motive `*_rigidbody.csv` → box markers

- Path rule: `E:\Dropbox\SEL\BOX\Experiment\<namecode>\RigidBody\*_<cond>_rigidbody.csv` (`PATH_RULE.DATA_DIR`, `ResultPaths.rigid_dir`).
- Reader: `a_Get_Exp_Data/lifting_io.read_rigid_body_csv` (RB center + Euler; skiprows=7).
- Marker columns: `RigidBody:Marker1`…`Marker8` (XYZ + quality). Empirically vs CAD local offsets:

| Motive | OpenSim / C3D |
|--------|----------------|
| Marker1 | LTA_BOX |
| Marker2 | LTP_BOX |
| Marker3 | LBA_BOX |
| Marker4 | LBP_BOX |
| Marker5 | RTA_BOX |
| Marker6 | RTP_BOX |
| Marker7 | RBA_BOX |
| Marker8 | RBP_BOX |

`abc_marker_events` already uses Marker1/Marker5 (LTA/RTA) for ABC events. MeasuredEHF places hand COP with `D3/D4` + Motive `R`.

### Workflow summary (`박스 모델 생성 Workflow.txt`)

1. Add half bodies (mass/COM/inertia from SolidWorks PDFs); joints `handle_l` / `handle_r`.
2. Mesh scale 0.001.
3. Weld offset frames L/R: `(0.21, 0.11303, 0.20676)` / `(0.21, 0.11303, 0.00176)`.
4–7. Handle ↔ hand / box offsets + ±90° orientations; pro_sup defaults.
8. Attach eight markers (table above).
9–10. WeldConstraint between half offset frames.

Human welded box: `b_Build_Model/ADDBOX.py`. Free box for Approach-5 BK: `BoxWrench/models/BOX*.osim` + `build_box_model_with_markers.py`.

## Method (implemented)

1. **Box 6DOF wrench** — COM accel + ω̇ → `F`, `M` (`boxwrench_kinematics`; vendor diagonal-I, no ω×Iω).
2. **L/R allocation** — SLSQP min ‖F_r‖²+‖F_l‖² with force/moment equality; COP near CAD handles (`boxwrench_allocate`).
3. **RiCTO gate** — multiply hand forces by smooth/rect weight; **no MeasuredEHF** hand copy; torques **0**.
4. **ExtLoad** — HeavyHand GRF template; hand3=L, hand4=R (`boxwrench_extload`).

## Module layout

```
BoxWrench/
├─ BOXWRENCH_PLAN.md
├─ run_boxwrench.py              # CLI; --synthetic smoke test
├─ build_box_model_with_markers.py
├─ boxwrench_config.py
├─ boxwrench_markers.py          # CAD / Motive geometry tables
├─ boxwrench_rotation.py         # Rx@Ry@Rz reimplementation (not vendor import)
├─ boxwrench_inertia.py
├─ boxwrench_kinematics.py
├─ boxwrench_allocate.py
├─ boxwrench_extload.py
├─ models/BOX.osim, BOX_with_markers.osim  (+ *.STL gitignored)
└─ _vendor/APP5, General         # reference only
```

## Done

- [x] Package + PATH_RULE / pipeline opt-in for app `BoxWrench`
- [x] Vendor APP5 adapted (no General runtime import)
- [x] CAD handle ±0.160 m; marker tables; Motive Marker1–8 map
- [x] `BOX_with_markers.osim` builder
- [x] `python run_boxwrench.py --synthetic --box-mass 7` — success (fy≈−mg/2 each in contact window)

## Blockers / next

1. **Trial box IK + BK**: run free-joint box IK on segment TRC (box markers) → BodyKinematics / States → `run_boxwrench.py --bk-vel …`.
2. **Validate** free-BOX marker frame ASSUMPTION vs static TRC / Motive Marker locals (adjust if residuals high).
3. Optional: add `BoxWrench` to default protocol `APPs` / progress sheet once MOT generation is routine.
4. Example rigidbody for docs: e.g. `Experiment/260512_HSH/RigidBody/7kg_10bpm_rigidbody.csv` (not vendored into git).
