# FreeBox 코드·Analysis 산출물 구조

코드·경로 키워드는 **FreeBox**, 문서·플롯 범례/제목용 표기는 **LoadShare**  
(`freebox_config.APP_NAME` / `DISPLAY_NAME`).

## 1. 코드 위치

```
Codes/c_Run_Tools/FreeBox/
├─ run_freebox.py                 # CLI 진입점
├─ freebox_config.py              # APP_NAME=FreeBox, DISPLAY_NAME=LoadShare
├─ freebox_paths.py               # OpenSim_Process / Dropbox / Analysis 경로
├─ freebox_opensim.py             # free-box IK → BK → StatesReporter
├─ freebox_markers.py             # 코너·핸들 마커 (CAD / Motive 프레임)
├─ freebox_inertia.py             # BOX.osim 질량·관성, 조건 kg 스케일
├─ freebox_rotation.py            # body-fixed XYZ → R
├─ freebox_kinematics.py          # 상자 COM 가속도·각가속도 → 총 F,M
├─ freebox_allocate.py            # 양손 힘·COP 배분 (SLSQP)
├─ freebox_extload.py             # HeavyHand GRF + FreeBox 손열 × RiCTO weight
├─ build_box_model_with_markers.py
├─ models/
│  ├─ BOX.osim                    # 15 kg 기준
│  └─ BOX_with_markers.osim
├─ FREEBOX_PLAN.md                # 구현 메모
└─ _vendor/                       # 원본 참고용만 (런타임 import 금지)
```

파이프라인 연동:

| 파일 | 역할 |
|------|------|
| `Codes/PATH_RULE.py` | `freebox_root` / `freebox_timeseries_*` / `freebox_plot_path` |
| `Codes/c_Run_Tools/pipeline_rules.py` | app `FreeBox` 모델 variant + `OPTIONAL_PIPELINE_APPS` |
| `run_opensim_pipeline.py` | `--apps FreeBox` opt-in |
| `opensim_pipeline_handlers.py` | ExtLoad/SO/JR는 base model (pre/postRiCTO와 동일 패턴) |

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

## 4. Analysis 폴더 구조·파일명

루트: `Analysis/<protocol>/FreeBox/`  
예: `Analysis/Asymmetric/FreeBox/`

```
Analysis/Asymmetric/FreeBox/
├─ Summary/                          # (예약) 요약 시트
├─ _validation/                      # (예약) 검증 CSV
└─ TimeSeries/SUB{n}/{cond}/
   ├─ SUB{n}_{cond}_{seg}_FreeBox_forces.csv      # run_freebox 기본 기록
   ├─ SUB{n}_{cond}_{seg}_FreeBox_timeseries.csv  # PATH_RULE helper
   └─ plots/
      └─ SUB{n}_{cond}_{seg}_FreeBox_{tag}.png    # 파일명 = FreeBox
```

구체 예 (PJH 샘플, SUB 번호는 `SUB_Info`에 따름):

```
Analysis/Asymmetric/FreeBox/TimeSeries/SUB7/7kg_10bpm/
  SUB7_7kg_10bpm_1AB_FreeBox_forces.csv
```

플롯 **파일명**은 `…_FreeBox_….png` 을 쓰고, 그림 안 **범례·제목·캡션** 문자열은 `LoadShare` 를 쓴다 (`DISPLAY_NAME`).

## 5. PATH_RULE API 요약

```python
rp = ResultPaths("260526_PJH")
rp.freebox_root()                        # Analysis/…/FreeBox
rp.freebox_timeseries_dir("7kg_10bpm")   # …/TimeSeries/SUB{n}/7kg_10bpm
cp = rp.for_condition("7kg_10bpm")
cp.extload_path("1AB", "FreeBox")        # …/ExtLoad/…_ExtLoad_FreeBox.mot
cp.freebox_timeseries_path("1AB")
cp.freebox_plot_path("1AB", tag="overview")
```

## 6. 다른 앱과의 구분

| App 키 | 의미 |
|--------|------|
| MeasuredEHF | 로드셀 측정 손외력 |
| HeavyHand | 손 질량 부가 |
| AddBox | 상자 용접/분할 구속 |
| preRiCTO / postRiCTO | RiCTO 시점 게이팅 + BK 기반 EHF |
| **FreeBox** | free-joint 상자 역학 → 양손 배분 (**LoadShare**) |
