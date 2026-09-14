# FreeBox 코드·Analysis 산출물 구조

> **배치·이동 결정의 source of truth는 [`FREEBOX_PLAN.md`](./FREEBOX_PLAN.md)이다.**  
> 특히 §3(권고: c_Run_Tools에 **thin** 유지), §4(파일 배치표), §5(모델→`OpenSim_Process/Model/Design_Box`)가 본 요약과 충돌하면 **PLAN을 따른다.**  
> 아래 트리는 **목표(thin) 상태**이며, 아직 `models/`·`build_*`·`_vendor/`가 남아 있으면 이행 전 잔여물이다.

코드·경로 키워드는 **FreeBox**, 문서·플롯 범례/제목용 표기는 **LoadShare**  
(`freebox_config.APP_NAME` / `DISPLAY_NAME`).

## 1. 코드 위치 (목표: thin package)

```
Codes/c_Run_Tools/FreeBox/          # RiCTO optimization/ 과 같은 급 — 미니 레포 아님
├─ run_freebox.py
├─ freebox_config.py                # DEFAULT_BOX_* → Design_Box (패키지 models/ 금지)
├─ freebox_paths.py
├─ freebox_opensim.py
├─ freebox_markers.py               # 런타임·빌드가 공유; 빌드는 b에서 import
├─ freebox_inertia.py
├─ freebox_rotation.py              # OpenSim 검증 필수; RotMat 덤프 금지
├─ freebox_kinematics.py
├─ freebox_allocate.py
├─ freebox_extload.py
├─ FREEBOX_PLAN.md                  # 배치 SoT
└─ FREEBOX_STRUCTURE.md             # 본 요약

Codes/b_Build_Model/
└─ build_freebox_model_with_markers.py   # ← build_* 이전 대상

OpenSim_Process/Model/Design_Box/
├─ BOX.osim / BOX_with_markers.osim / BOX.STL
└─ (기존) BOX_15.02kg_Half_{L,R}.STL
```

**넣지 않음**: `FreeBox/models/`, `FreeBox/_vendor/General`, 런타임 미사용 APP5 덤프.

파이프라인 연동:

| 파일 | 역할 |
|------|------|
| `Codes/PATH_RULE.py` | `freebox_*` Analysis API + (예정) Design_Box free-box osim helper |
| `Codes/c_Run_Tools/pipeline_rules.py` | app `FreeBox` + `OPTIONAL_PIPELINE_APPS` |
| `run_opensim_pipeline.py` | `--apps FreeBox` opt-in |
| `opensim_pipeline_handlers.py` | ExtLoad/SO/JR는 base model (RiCTO와 동일) |

## 2. 분석 파이프라인 (데이터 흐름)

```
TRC (상자 마커)
  → free-box IK          …/IK_Load/*_Load_IK.mot
  → BK vel/pos           …/BK_Load/*_BodyKinematics_*.sto
  → StatesReporter       …/States_Load/*_StatesReporter_states.sto
  → 상자 총 F,M (kinematics)
  → 양손 배분 (allocate)     hand3=L, hand4=R; 토크=0
  → RiCTO timeseries weight  (기본 smooth)
  → ExtLoad_FreeBox.mot      (GRF는 HeavyHand 템플릿 유지)
  → Analysis CSV             (손 힘 timeseries)
```

샘플 기본값: `260526_PJH` / `7kg_10bpm` / `1AB`  
CLI: `python Codes/c_Run_Tools/FreeBox/run_freebox.py --namecode 260526_PJH`

## 3. OpenSim_Process 중간·최종 입력 (세그먼트 기준)

루트: `OpenSim_Process/_Main_/<protocol>/SUB{n}/{cond}/{AB|BC|CA}/`  
(로컬 또는 cowork Dropbox — `freebox_paths`가 기존 TRC가 있는 쪽 우선)

| 종류 | 폴더 | 파일명 예 (`SUB7`, `7kg_10bpm`, `1AB`) |
|------|------|----------------------------------------|
| Markers | `Markers/` | `SUB7_7kg_10bpm_1AB.trc` |
| Free-box IK | `IK_Load/` | `SETUP_IK_7kg_10bpm_1AB_Load.xml`, `SUB7_7kg_10bpm_1AB_Load_IK.mot` |
| Free-box BK | `BK_Load/` | `…_Load_BodyKinematics_vel_global.sto`, `…_pos_global.sto` |
| Free-box States | `States_Load/` | `…_Load_StatesReporter_states.sto` |
| ExtLoad (입력 템플릿) | `ExtLoad/` | `SUB7_7kg_10bpm_1AB_ExtLoad_HeavyHand.mot` |
| ExtLoad (FreeBox 출력) | `ExtLoad/` | `SUB7_7kg_10bpm_1AB_ExtLoad_FreeBox.mot` |

공유 free-box osim(피험자 무관): `OpenSim_Process/Model/Design_Box/` — **Codes 아래 아님**.

## 4. Analysis 폴더 구조·파일명

루트: `Analysis/<protocol>/FreeBox/`  
예: `Analysis/Asymmetric/FreeBox/`

```
Analysis/Asymmetric/FreeBox/
├─ Summary/                          # (예약) 요약 시트
├─ _validation/                      # (예약) 검증 CSV
└─ TimeSeries/SUB{n}/{cond}/
   ├─ SUB{n}_{cond}_{seg}_FreeBox_forces.csv
   ├─ SUB{n}_{cond}_{seg}_FreeBox_timeseries.csv
   └─ plots/
      └─ SUB{n}_{cond}_{seg}_FreeBox_{tag}.png
```

플롯 **파일명**은 `…_FreeBox_….png`, 그림 안 **범례·제목·캡션**은 `LoadShare`.

## 5. PATH_RULE API 요약

```python
rp = ResultPaths("260526_PJH")
rp.freebox_root()                        # Analysis/…/FreeBox
rp.freebox_timeseries_dir("7kg_10bpm")
cp = rp.for_condition("7kg_10bpm")
cp.extload_path("1AB", "FreeBox")
cp.freebox_timeseries_path("1AB")
cp.freebox_plot_path("1AB", tag="overview")
# 예정: design_box_dir() / freebox_box_osim_path(with_markers=…)
```

## 6. 다른 앱과의 구분

| App 키 | 의미 |
|--------|------|
| MeasuredEHF | 로드셀 측정 손외력 |
| HeavyHand | 손 질량 부가 |
| AddBox | 상자 용접/분할 구속 |
| preRiCTO / postRiCTO | RiCTO 시점 게이팅 + BK 기반 EHF |
| **FreeBox** | free-joint 상자 역학 → 양손 배분 (**LoadShare**) |
