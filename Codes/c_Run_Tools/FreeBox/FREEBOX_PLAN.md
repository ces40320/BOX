# FreeBox 배치 재계획 (문서 표기: LoadShare)

- **코드 / PATH_RULE / 파일명**: **FreeBox**
- **논문·플롯 범례·제목·캡션**: **LoadShare**
- **브랜치**: `cursor/boxwrench-0490`
- **본 문서 역할**: 레포 a/b/c 구획에 맞춘 **구조 재배치의 source of truth**  
  (`FREEBOX_STRUCTURE.md`는 요약만; 배치 결정은 여기가 우선)
- **작성일**: 2026-09-15 (구조 비판 검토 후 전면 재작성)

---

## 1. 현재 문제

FreeBox는 동작 검증(샘플 `260526_PJH` / `7kg_10bpm` / `1AB`)까지 왔지만, **폴더 형태가 “독립 미니 레포”**처럼 잡혀 있다. 이 레포는 이미 단계별로 일을 나눈다.

| 증상 | 왜 문제인가 |
|------|-------------|
| `Codes/c_Run_Tools/FreeBox/` 아래에 `freebox_*` + `models/*.osim` + `build_*.py` + `_vendor/` 전부 | `c_Run_Tools`는 **실행·파이프라인** 자리인데, 모델 자산·빌드·외부 벤더 덤프까지 한곳에 몰림 |
| `models/BOX.osim`, `BOX.STL`, `BOX_with_markers.osim` 을 Codes 아래 보관 | 박스 메시·기준 osim은 이미 `OpenSim_Process/Model/Design_Box/` 관례 (`ADDBOX.DEFAULT_MESH_DIR`) |
| `build_box_model_with_markers.py` 가 FreeBox 안 | 모델 조립은 `Codes/b_Build_Model/` (`ADDBOX.py`, `add_box_weldjoint_model.py` 등) |
| `_vendor/General/` (RotMat, OriCalc, …) 복사 | “참고용”이라도 Codes에 General 덤프를 두는 순간 기본값이 됨. 회전은 OpenSim과 검증해야 하며 RotMat 복제가 기본이 되면 안 됨 |
| `freebox_config`만으로도 “앱 루트 = 이 폴더”처럼 보임 | PATH_RULE·파이프라인은 이미 `Analysis/…/FreeBox`, `IK_Load`/`BK_Load` 등으로 레포 전역을 쓰는데, 코드 트리는 그 전역과 어긋남 |

**결론**: FreeBox를 “앱 전용 미니 레포”로 키울 필요가 없다. 레포 구획에 맞춰 **자산 / 빌드 / 실행**을 쪼개야 한다.

---

## 2. 레포 구획 원칙 (증거)

| 구획 | 책임 | 실제 경로 증거 |
|------|------|----------------|
| `Codes/a_Get_Exp_Data/` | 실험 CSV/C3D → TRC·측정 ExtLoad 등 입력 | `run_get_exp_data.py`, `config_exp_settings.py`, `lifting_io.py` |
| `Codes/b_Build_Model/` | 스케일·HeavyHand·Weld/Split 박스 osim 생성 | `ADDBOX.py` (`DEFAULT_MESH_DIR → OpenSim_Process/Model/Design_Box`), `add_box_weldjoint_model.py`, `add_hand_mass_model.py` |
| `Codes/c_Run_Tools/` | OpenSim 파이프라인·앱별 ExtLoad/분석 러너 | `run_opensim_pipeline.py`, `pipeline_rules.py`, `optimization/` (RiCTO), `FreeBox/` |
| `OpenSim_Process/Model/` | **공유 모델·메시 자산** (피험자 무관) | `Design_Box/BOX_15.02kg_Half_{L,R}.STL`, `unscaled_LFB_Toggle_*.osim` |
| `OpenSim_Process/_Main_/` | 피험자별 중간·최종 OpenSim 산출 | `…/Model_osim/SUB{n}_Scaled_*.osim`, `…/{cond}/{AB}/Markers|IK|ExtLoad|…` (`STRUCTURE_PLAN.md`, `PATH_RULE.ResultPaths`) |
| `Analysis/` | 논문·시계열·플롯 (앱별) | `PATH_RULE`: `Analysis/<protocol>/FreeBox/…`, RiCTO와 동일 패턴 |
| `Codes/d_Results_Analysis/` | 집계·리포트 스크립트 | `run_ehf_analysis.py`, `run_ricto_report_sheets.py` 등 — FreeBox **코어 역학이 올 자리 아님** |

기준 문서:

- `OpenSim_Process/STRUCTURE_PLAN.md` — `_Main_` 폴더·파일명, kg-aware WeldBox/SplitBox
- `Codes/c_Run_Tools/REFAC_RUN_TOOLS_PLAN.md` — c_Run_Tools는 PATH_RULE만으로 경로 조합
- `Codes/c_Run_Tools/optimization/RICTO_PLAN.md` — **얇은 앱 패키지** 선례 (`run_ricto` + `ricto_*`, 모델·벤더 미포함)

---

## 3. FreeBox를 `c_Run_Tools`에 둘지 — 권고

### 권고: **유지하되 얇게 (thin package)** — RiCTO `optimization/`과 같은 급

**남길 것** (`Codes/c_Run_Tools/FreeBox/`):

- CLI / 파이프라인 진입: `run_freebox.py`
- 세그먼트 경로 해석·Dropbox/local resolve: `freebox_paths.py` (장기적으로 PATH_RULE로 흡수 가능)
- free-box IK → BK → States 오케스트레이션: `freebox_opensim.py` (공유 analyze 헬퍼가 생기면 얇은 래퍼로)
- 상자 역학·배분·ExtLoad: `freebox_kinematics` / `allocate` / `extload` / `inertia` / `rotation`
- 앱 상수: `freebox_config.py` (단, **osim 기본 경로는 Model/Design_Box를 가리키도록 변경**)

**빼낼 것**:

| 항목 | 이동처 |
|------|--------|
| `models/*` (osim/STL) | `OpenSim_Process/Model/Design_Box/` |
| `build_box_model_with_markers.py` | `Codes/b_Build_Model/` |
| `_vendor/General/` | **삭제** (덤프 금지) |
| `_vendor/APP5/` | 이식 완료 후 **삭제** (Codes에 “참고용 벤더”로 잔류 금지) |

### 기각한 대안

| 대안 | 기각 이유 |
|------|-----------|
| FreeBox 전체를 `b_Build_Model`로 이동 | 빌드만 해당; ExtLoad·IK/BK 오케스트레이션·파이프라인 opt-in은 c 책임 |
| FreeBox를 `d_Results_Analysis`로 이동 | d는 집계/리포트; MOT 생성·역학 코어와 역할 불일치 |
| `Codes/FreeBox/` 같은 새 top-level 앱 트리 | a/b/c 관례를 깨는 미니 레포 재현 |
| 현 상태(모델+빌드+vendor 동봉) 유지 | Design_Box / ADDBOX / PATH_RULE와 충돌; independence bias 지속 |

**한 줄**: FreeBox는 **`c_Run_Tools`에 남기되**, 모델·빌드·General 덤프는 빼고 RiCTO급 얇은 실행 패키지로 만든다.

---

## 4. 타깃 파일 배치표

| 현재 (`FreeBox/…`) | 제안 위치 | 조치 | 이유 |
|--------------------|-----------|------|------|
| `run_freebox.py` | `c_Run_Tools/FreeBox/` | 유지 | 실행 진입점 |
| `freebox_config.py` | 동상 | 유지·경로만 수정 | APP_NAME / 샘플 기본값; `DEFAULT_BOX_*` → Design_Box |
| `freebox_paths.py` | 동상 (→ 이후 PATH_RULE 흡수) | 유지 | Dropbox/local TRC·Load 폴더 resolve |
| `freebox_opensim.py` | 동상 | 유지 | free-box IK/BK/States; 공유 helper 생기면 위임 |
| `freebox_kinematics.py` | 동상 | 유지 | COM wrench 수학 (이미 `ricto_io` 재사용) |
| `freebox_allocate.py` | 동상 | 유지 | L/R 배분 |
| `freebox_extload.py` | 동상 | 유지 | ExtLoad 기록 + RiCTO gate |
| `freebox_inertia.py` | 동상 | 유지 | Design_Box의 BOX.osim 읽어 kg 스케일 |
| `freebox_rotation.py` | 동상 | 유지·**검증 필수** | RotMat 복제 기본값 금지; OpenSim과 대조 |
| `freebox_markers.py` | 동상 (빌드 스크립트가 import) **또는** CAD 표만 `b_Build_Model`로 이전 후 FreeBox는 import | 유지 우선, 빌드 이전 시 import 방향만 정리 | 런타임 핸들 좌표·빌드 마커 표가 공유됨 |
| `build_box_model_with_markers.py` | `Codes/b_Build_Model/build_freebox_model_with_markers.py` (이름 선택) | **이동** | WeldBox 빌더와 동렬 |
| `models/BOX.osim` | `OpenSim_Process/Model/Design_Box/BOX.osim` | **이동** | ADDBOX 메시와 동일 자산 루트 |
| `models/BOX_with_markers.osim` | `OpenSim_Process/Model/Design_Box/BOX_with_markers.osim` | **이동** (빌드 산출물) | Codes 아래 모델 금지 |
| `models/BOX.STL` | `OpenSim_Process/Model/Design_Box/BOX.STL` | **이동** | 반쪽 STL과 함께 |
| `models/.gitignore` | 삭제 또는 Design_Box 정책에 맞춤 | 정리 | |
| `_vendor/General/*` | — | **삭제** | 덤프 금지; 필요 util만 최소 작성 |
| `_vendor/APP5/*` | — | **삭제** (이식 확인 후) | 런타임 미사용이면 Codes에 두지 않음 |
| `_vendor/README.pdf` | 레포 밖 아카이브 또는 `docs/` 한곳 (선택) | 제거 권장 | FreeBox 패키지 비대 방지 |
| `FREEBOX_PLAN.md` | 동상 | 유지 | **배치 SoT** |
| `FREEBOX_STRUCTURE.md` | 동상 | 요약만; PLAN 우선 | |
| `__init__.py` | 동상 | 유지 | |

파이프라인 연동(위치 유지, 경로 상수만 갱신):

- `Codes/PATH_RULE.py` — `freebox_*` Analysis API + (추가) Design_Box free-box osim helper
- `Codes/c_Run_Tools/pipeline_rules.py` — app `FreeBox` opt-in, SO/JR는 base model
- `opensim_pipeline_handlers.py` / `run_opensim_pipeline.py` — `--apps FreeBox`

---

## 5. 모델·마커 자산

### 원칙

- **피험자 무관** 박스 기준 모델·메시 → `OpenSim_Process/Model/…`
- **피험자별** Weld/Split/HeavyHand → `OpenSim_Process/_Main_/<protocol>/SUB{n}/Model_osim/` (`rp.model_path(...)`)
- FreeBox free-joint 상자는 **인체 모델에 weld하지 않는 공유 자산**이므로 Design_Box 쪽이 맞다 (SUB Model_osim에 kg별 복제하지 않음; 질량은 런타임 `freebox_inertia` 스케일).

### 타깃 트리

```
OpenSim_Process/Model/Design_Box/
  BOX_15.02kg_Half_L.STL          # 기존 (ADDBOX)
  BOX_15.02kg_Half_R.STL          # 기존
  BOX.STL                         # ← FreeBox/models 에서 이동
  BOX.osim                        # ← 15 kg 기준 free-joint (마커 없음)
  BOX_with_markers.osim           # ← b_Build_Model 빌드 산출
```

### PATH_RULE 훅 (구현 시)

권장 API (이름은 구현 시 확정):

```python
# 예: ResultPaths 또는 모듈 함수
design_box_dir() -> …/OpenSim_Process/Model/Design_Box
freebox_box_osim_path(*, with_markers: bool = True) -> …/BOX_with_markers.osim | BOX.osim
```

`freebox_config.DEFAULT_BOX_OSIM` / `DEFAULT_BOX_WITH_MARKERS_OSIM` 는 **패키지 상대 `models/`가 아니라** 위 helper를 가리킨다.

### 빌드

- `Codes/b_Build_Model/build_freebox_model_with_markers.py`  
  - 입력: `Design_Box/BOX.osim`  
  - 출력: `Design_Box/BOX_with_markers.osim`  
  - 마커 좌표: 기존 `freebox_markers` (또는 b로 옮긴 CAD 표)  
- `_b_Main.ipynb` / 일괄 빌드 흐름에 **한 스텝으로 연결** (WeldBox 생성과 병렬 개념: “공유 free-box 자산 준비”)

### OpenSim 중간 산출 (변경 없음 — 이미 관례 준수)

| 종류 | 폴더 | 예 (`SUB7`, `7kg_10bpm`, `1AB`) |
|------|------|--------------------------------|
| Markers | `Markers/` | `…_1AB.trc` |
| Free-box IK | `IK_Load/` | `…_Load_IK.mot` |
| Free-box BK | `BK_Load/` | `…_Load_BodyKinematics_{pos,vel}_global.sto` |
| Free-box States | `States_Load/` | `…_Load_StatesReporter_states.sto` |
| ExtLoad | `ExtLoad/` | `…_ExtLoad_FreeBox.mot` (템플릿: HeavyHand) |

Analysis: `Analysis/<protocol>/FreeBox/TimeSeries/…` (파일명 FreeBox, 범례 LoadShare).

---

## 6. General / RotMat 정책

1. **`_vendor/General` 덤프 금지·삭제.** “reference only”로 Codes에 남겨 두지 않는다.
2. **이미 있는 공유 I/O를 재사용**: `optimization/ricto_io` (`read_opensim_storage`, MOT/CSV), `ricto_optimize` weight 곡선 — FreeBox가 이미 쓰는 경로를 유지·확대.
3. **정말 없는 util만** FreeBox 내부 소함수 또는 (재사용 확정 시) `Codes` 공용 최소 모듈로 추가. General 폴더 통째 복원 금지.
4. **회전**: `freebox_rotation.rotmat_body_fixed_xyz_deg`는 현재 vendor `Rx@Ry@Rz`와 동일 조성이지만, 이는 **가설**이다.  
   - BodyKinematics orientation ↔ OpenSim `Rotation` / 알려진 자세로 **수치 검증** 후 확정.  
   - 검증 전·후 모두 RotMat.py를 소스 오브 트루스로 두지 말 것.  
   - 불일치 시 OpenSim 규약에 맞게 수정하고, vendor 식은 폐기.

`_vendor/APP5`: 런타임 import가 없다면 이식 체크리스트만 남기고 디렉터리 삭제.

---

## 7. 구현 순서 (big-bang 금지)

1. **문서·합의** — 본 PLAN 확정 (현재 단계).
2. **모델 자산 이동** — `BOX.osim` / `BOX.STL` / `BOX_with_markers.osim` → `OpenSim_Process/Model/Design_Box/`; `freebox_config`·inertia·opensim·build 기본 경로 갱신; `FreeBox/models/` 제거.
3. **PATH_RULE helper** — Design_Box free-box osim 경로 함수 추가; FreeBox는 문자열 하드코드 최소화.
4. **`build_*` 이전** — `b_Build_Model`로 옮기고 Design_Box 입출력을 쓰게 함; `_b_Main`에 호출 한 줄 수준으로 연결.
5. **`_vendor/General` 삭제** — import 잔존 grep; 없으면 삭제. APP5도 동일.
6. **회전 검증** — OpenSim 대조 스크립트/노트; 필요 시 `freebox_rotation`만 수정.
7. **경로 smoke** — 기존 산출물이 있는 세그먼트에서 “경로만” 확인 (전체 PJH 재실행은 비범위; 필요 시 단일 세그먼트 선택).
8. **STRUCTURE.md 정리** — 얇은 패키지 트리만 반영; 배치 상세는 PLAN 링크.

---

## 8. 비범위

- 본 문서는 **배치 재계획**이다. 전 파일 이동·파이프라인 전체 재실행은 후속 작업.
- **전체 PJH / 전 condition 재런은 하지 않는다** (경로 검증용 단발만 허용).
- LoadShare 방법론·배분 수식 재도출, SLSQP bound 튜닝, 마커 local 재피팅은 별 이슈.
- `d_Results_Analysis` FreeBox 리포트 추가는 배치 안정화 이후.

---

## 부록 A — 방법 요약 (동작은 유지, 위치만 재배치)

1. Free-box IK (8 코너) on `BOX_with_markers.osim` (Design_Box)
2. BK pos/vel + StatesReporter (ω)
3. COM wrench → 총 F, M
4. CAD 핸들 중심 L/R 배분 (hand3=L, hand4=R; 토크 0)
5. RiCTO weight gate
6. ExtLoad_FreeBox.mot + Analysis CSV

샘플: `260526_PJH` / `7kg_10bpm` / `1AB` (기존 smoke 결과 유효; 경로만 Design_Box로 옮긴 뒤 재확인).

## 부록 B — CLI (경로 이전 후에도 진입점은 동일 계열)

```bat
C:\Users\ok\anaconda3\envs\osim\python.exe Codes\c_Run_Tools\FreeBox\run_freebox.py --namecode 260526_PJH
```
