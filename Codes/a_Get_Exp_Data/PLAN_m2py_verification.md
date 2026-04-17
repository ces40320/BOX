# MATLAB → Python 변환 검증 계획서

> **원본**: `MOT_TRC_UPDOWN_APP123_Modified.m` (Symmetric 프로토콜)  
> **번역본**: `lifting_io.py`, `config_exp_settings.py`, `segment_asymmetric.py` (Asymmetric 프로토콜)  
> **참조**: `E:\Dropbox\SEL\_LAB_PROJECT_\REHAB_Project_Folder\SEL\Analysis\Obstacle\Codes\a_GetExpData\tak2TrcMot.py` (OpenSim API 사용 예시)  
> **작성일**: 2026-04-07  
> **최종 갱신**: 2026-04-09 — `lifting_io.py` ExtLoad 변환 함수명을 `MeasuredEHF` / `HeavyHand` / `AddBox`와 정합되게 변경 (아래 **로그** 참고).

---

## 로그

| 날짜 | 파일 | 내용 |
|------|------|------|
| 2026-04-17 | `run_get_exp_data.py`, `lifting_io.py`, `config_exp_settings.py` | `marker.trc`, `ExtLoad.mot`를 출력하는 전처리(비분할, full-length) 파이프라인 실행 가능 상태 확인. 이벤트 split(`findpeaks`, `bpm_window`)는 우선 미실행/보류. |
| 2026-04-09 | `lifting_io.py` | `assemble_app1` → `transform_ExtLoad_MeasuredEHF`, `assemble_app2` → `transform_ExtLoad_HeavyHand`, `assemble_app3` → `transform_ExtLoad_AddBox`. `transform_ExtLoad_AddBox` 내부는 `transform_ExtLoad_HeavyHand`를 호출. 과거 이슈·커밋 검색 시 구명칭(`assemble_app*`)으로 찾을 수 있음. |

---

## 0. 전체 파이프라인 개요

```
C3D 파일 ──┐
            ├─→ 마커 데이터 (100 Hz) ──→ 필터링 ──→ [이벤트 기준 분할] ──→ .trc
            ├─→ 외력 데이터 (1000 Hz) ──→ 로드셀 회전변환/COP 처리 ──→ 필터링 ──→ [이벤트 기준 분할] ──→ .mot (MeasuredEHF/HeavyHand/AddBox)
RigidBody CSV ─┘
```

---

## 현재 상태 업데이트 (2026-04-17)

- [x] `config_exp_settings.py` + `lifting_io.py` + `run_get_exp_data.py` 조합으로 **full-length 전처리 출력**( `marker.trc`, `ExtLoad.mot`) 가능.
- [ ] 이벤트 기반 분할(`findpeaks`, `bpm_window`)은 아직 실행하지 않음.
  - `findpeaks` 분할은 Symmetric 재현 성격으로 현재 우선순위 낮음.
  - `bpm_window` 자동 분할은 추가 파일럿 실험 결과로 검증 기준 확정 후 구현 예정.
- [ ] 따라서 현재 단계의 1차 목표는 “분할 없는 입력 파일 생성 안정화 + 수치 검증”으로 유지.

---

## 1. 문제1: ezc3d vs OpenSim API — C3D 읽기 방식 결정

### 1.1 현재 상태

| 항목 | MATLAB 원본 | Python 번역 (lifting_io.py) | 참조 (`tak2TrcMot.py`) |
|------|------------|---------------------------|----------------------|
| C3D 리더 | `osimC3D(c3dpath, 1)` | `ezc3d.c3d(path, extract_forceplat_data=True)` | `osim.C3DFileAdapter()` |
| COP 표현 | COP 모드 (`1`) | `extract_forceplat_data=True` | `adapter.setLocationForForceExpression(1)` |
| 패키지 | OpenSim MATLAB API | `pip install ezc3d` | `pip install opensim` |

> **참조 파일 절대경로**: `E:\Dropbox\SEL\_LAB_PROJECT_\REHAB_Project_Folder\SEL\Analysis\Obstacle\Codes\a_GetExpData\tak2TrcMot.py`

### 1.2 분석 — Windows DLL 충돌 문제 (확인됨)

- **OpenSim은 내부적으로 ezc3d를 C++ DLL로 번들링** (현재 main branch: ezc3d `Release_1.5.19`).
- conda-forge 또는 pip으로 ezc3d를 별도 설치하면, 동일 이름(`ezc3d.dll`)의 DLL이 두 개 존재하게 됨.
- Windows의 PATH 순서에 따라 한쪽이 깨짐 → `ImportError: DLL load failed` 발생.
- **버전을 맞춰도 해결 불가**: OpenSim은 `RelWithDebInfo`로, conda/pip의 ezc3d는 `Release`로 빌드. 동일 버전이라도 빌드 설정이 다르면 DLL 호환 불가.
- 관련 이슈: [pyomeca/ezc3d#220](https://github.com/pyomeca/ezc3d/issues/220), [opensim-core#3681](https://github.com/opensim-org/opensim-core/issues/3681) (2024년 기준 미해결)

### 1.3 결론

**ezc3d를 사용하지 않고 `import opensim`(`osim.C3DFileAdapter`)만으로 진행한다.**

이유:
1. 이후 파이프라인(IK, ID 등)에서 `import opensim`이 필수적이므로, 동일 환경에 ezc3d가 공존하면 DLL 충돌 위험이 상존함.
2. `tak2TrcMot.py` (`E:\Dropbox\SEL\_LAB_PROJECT_\...\tak2TrcMot.py`)가 `osim.C3DFileAdapter()`를 사용하여 마커/힘 데이터 읽기, 필터링, TRC/MOT 쓰기를 모두 수행하고 있으므로 기능 부족 없음.
3. 환경 분리(ezc3d 전용 env / opensim 전용 env)는 유지보수 복잡성을 높여 비권장.

### 1.4 액션 아이템

- [x] `lifting_io.py`의 C3D 읽기 부분을 `ezc3d` → `opensim.C3DFileAdapter` 기반으로 재작성 완료
  - `_opensim_import()` → `osim.C3DFileAdapter()` 사용
  - `read_c3d_markers()` → `adapter.getMarkersTable(tables)` → `_osim_table_to_dict()`
  - `read_c3d_force_platforms()` → `adapter.getForcesTable(tables)` → f/p/m 배열로 매핑
- [x] `ezc3d` import 및 관련 함수 제거 완료 (현재 코드에 ezc3d 참조 없음)
- [x] `write_trc()` 좌표는 입력(m) 그대로 기록, TRC 헤더 `Units=m` (2026-04-09: 기존 mm 출력에서 변경)

---

## 2. 문제2: 로드셀 Force/Moment 회전변환 + COP Threshold 처리 — `transform_ExtLoad_MeasuredEHF()` (구명칭 `assemble_app1`) 버그

### 2.1 MATLAB 원본 로직 (line 191–242)

```
매 프레임 t에 대해:
  R = euler_to_rotation_matrix(RotX(t), RotY(t), RotZ(t))

  # 0) 부호 반전 (로드셀 LCS 관례 → 분석 관례)
  #    Force/Moment: HAND3_FORCE_SIGN, HAND3_MOMENT_SIGN  → X,Y 반전 (-1,-1,1)
  #    COP:          HAND3_COP_SIGN                        → X만 반전  (-1, 1,1)
  F3_signed(t) = F3_raw(t) * HAND3_FORCE_SIGN
  M3_signed(t) = M3_raw(t) * HAND3_MOMENT_SIGN
  P3_signed(t) = P3_raw(t) * HAND3_COP_SIGN

  # 1) Force, Moment 회전변환 (load cell local → global)
  F3(t) = R * F3_signed(t)
  F4(t) = R * F4_signed(t)
  M3(t) = R * M3_signed(t)
  M4(t) = R * M4_signed(t)

  Box_Center = [X(t), Y(t), Z(t)]

  # 2) COP 처리
  if |F3(t, y)| < THRESHOLD:
      # 힘 작으면 → COP = 핸들 위치 (로컬→글로벌)
      P3(t) = R * D3_local + Box_Center
  else:
      # 힘 충분하면 → COP = (raw_cop - offset + D3_local) 전체를 회전 후 이동
      P3(t) = R * (P3_signed(t) - P3_offset + D3_local) + Box_Center
```

> **COP 부호 (`HAND3_COP_SIGN`, `HAND4_COP_SIGN`)**: Force/Moment 부호와 달리 X축만 반전 `(-1, 1, 1)`. 로드셀 COP 출력의 X축 방향 관례가 Force/Moment와 다르기 때문.

### 2.2 Python 번역 로직 — ~~이전 버그~~ → 수정 완료

이전 코드 (버그):
```python
p3[t] = p3[t] - p3_offset + d3_global + box_center[t]   # ← 회전변환 누락
```

현재 코드 (수정됨, line 411–421):
```python
p3_signed = p3_raw * sign_p3   # COP 부호 반전 (line 397)

if abs(f3[t, 1]) < force_threshold_n:
    p3[t] = r @ d3_local + box_center[t]
else:
    local_cop_3 = p3_signed[t] - p3_offset + d3_local
    p3[t] = r @ local_cop_3 + box_center[t]      # ✓ MATLAB과 동일
```

### 2.3 핵심 버그

**else 분기에서 COP의 회전변환이 누락됨.**

| | MATLAB | Python (현재) |
|--|--------|--------------|
| else 분기 | `R * (P3_raw - P3_offset + D3_local) + Box_Center` | `P3_raw - P3_offset + R*D3_local + Box_Center` |

MATLAB은 `(P3_raw - P3_offset + D3_local)` **전체**를 R로 회전시킨 뒤 Box_Center를 더한다. 즉, raw COP도 로드셀 로컬 좌표계이므로 회전 필요.

Python은 `D3_local`만 R로 회전시키고, `P3_raw - P3_offset`은 회전 없이 그대로 더한다. **이것은 로컬 좌표계의 COP를 글로벌 좌표계에 직접 더하는 것이므로 오류.**

### 2.4 수정 방안

```python
# 수정 전 (버그)
if abs(f3[t, 1]) < force_threshold_n:
    p3[t] = box_center[t] + d3_global
else:
    p3[t] = p3[t] - p3_offset + d3_global + box_center[t]

# 수정 후 (MATLAB과 동일)
# COP raw 데이터에 부호 반전 적용 (X축만: HAND3_COP_SIGN = (-1,1,1))
p3_signed = p3_raw * np.array(HAND3_COP_SIGN)

if abs(f3[t, 1]) < force_threshold_n:
    p3[t] = r @ d3_local + box_center[t]
else:
    local_cop = p3_signed[t] - p3_offset + d3_local
    p3[t] = r @ local_cop + box_center[t]
```

P4도 동일하게 수정.

### 2.5 액션 아이템

- [x] `lifting_io.py` → `transform_ExtLoad_MeasuredEHF()` (구 `assemble_app1`) else 분기 수정 완료: `local_cop = p3_signed[t] - p3_offset + d3_local` → `r @ local_cop + box_center[t]`
- [ ] 수정 후 MATLAB 출력과 수치 비교 검증

---

## 3. 문제3: 좌표계 회전이 불필요하게 적용되고 있음

### 3.1 현재 상태

**MATLAB 원본** (line 40–41):
```matlab
%% Rotate the data 
% c3d.rotateData('z',180)   ← 주석 처리됨 = 회전 안 함
```
→ 마커와 외력 데이터에 좌표계 회전을 적용하지 않음. C3D export 시 이미 XYZ 좌표계로 설정했기 때문.

**Python 설정** (`config_exp_settings.py` line 16):
```python
DYNAMIC_C3D_ROTATIONS = [("x", -90.0)]
```

**Python 호출** (`segment_asymmetric.py` line 152–153):
```python
markers = read_c3d_markers(c3d_path, rotations=cfg.DYNAMIC_C3D_ROTATIONS)
forces = read_c3d_force_platforms(c3d_path, rotations=cfg.DYNAMIC_C3D_ROTATIONS)
```
→ 마커와 외력 모두에 X축 -90도 회전이 적용되고 있음.

### 3.2 원인

동료가 QTM(Z-up) → OpenSim(Y-up) 변환을 위해 넣었으나, 이 실험에서는 Motive에서 c3d export 시 이미 Y-up(OpenSim 좌표계)으로 export하므로 추가 회전이 불필요.

### 3.3 수정 방안

`config_exp_settings.py`의 `DYNAMIC_C3D_ROTATIONS` 값은 그대로 유지한다 (다른 소프트웨어/프로젝트에서 필요할 수 있으므로).
대신 **실행 파일(호출부)** 에서 `rotations=None`으로 명시하여 회전을 적용하지 않는다:

```python
# config_exp_settings.py — 참조용으로 유지 (주석 참고)
DYNAMIC_C3D_ROTATIONS = [("x", -90.0)]   # QTM Z-up → OpenSim Y-up 용 (필요한 경우에만 사용)

# 실행 파일 (segment_symmetric.py / segment_asymmetric.py 등) — 호출 시 None 지정
markers = read_c3d_markers(c3d_path, rotations=None)       # Motive export는 이미 Y-up
forces  = read_c3d_force_platforms(c3d_path, rotations=None)
```

> **참고**: `read_c3d_markers()`와 `read_c3d_force_platforms()`는 `rotations=None`이면 회전을 건너뛰도록 이미 구현되어 있음.

### 3.4 액션 아이템

- [x] `config_exp_settings.py`에 `DYNAMIC_C3D_ROTATIONS` 참조용으로 유지 + `rotations=None` 사용 주석 명시 완료
- [x] `read_c3d_markers()` / `read_c3d_force_platforms()` 기본값이 `rotations=None` → 호출 시 명시 불필요
- [ ] 다른 소프트웨어(QTM 등)에서 Z-up으로 export하는 피험자가 있다면, `SUB_Info.py` 또는 피험자별 config에서 개별 지정하는 구조 고려

---

## 4. 문제4: write_trc 접두사 제거 로직 조건부 처리

### 4.1 현재 상태

**MATLAB 원본** (`writetrc.m`): 접두사 제거 로직 없음. 레이블을 그대로 출력.
```matlab
fprintf(fid,'\t%s\t\t%s',MLabels{i});
```

**Python — ~~이전 코드~~ → 수정 완료** (`lifting_io.py` line 301–307):
```python
# 현재 코드 (수정됨)
if ":" in label:
    short = label.split(":")[-1]
    if short.startswith("Static_"):
        short = short[len("Static_"):]
else:
    short = label
f.write(f"\t{short}\t\t")
```
→ 콜론 유무 조건 분기 구현 완료.

### 4.2 수정 방안

콜론(`:`)이 포함된 경우에만 접두사 제거를 수행:

```python
for label in mlabels:
    if ":" in label:
        short = label.split(":")[-1]
        if short.startswith("Static_"):
            short = short[len("Static_"):]
    else:
        short = label
    f.write(f"\t{short}\t\t")
```

### 4.3 액션 아이템

- [x] `lifting_io.py` → `write_trc()` 함수의 접두사 제거 로직을 콜론 유무 조건으로 분기 완료

---

## 5. 프로토콜별 세그먼트 분할 전략

### 5.1 현재 상태

| 항목 | MATLAB 원본 (Symmetric) | Python 번역 (Asymmetric) |
|------|------------------------|----------------------------------|
| 이벤트 검출 | `findpeaks(-Mean_box(:,2))` → 인접 peak 차이 > threshold | 3D box velocity → 동기화 끝 시점 검출 |
| 분할 기준 | Up_grip~Up_deposit, Down_grip~Down_deposit (각 10회) | 동기화 끝 시점부터 BPM 기반 고정 윈도우 |
| 파일명 | `{trial}_U1.trc`, `{trial}_D1.trc` 등 | `{trial}_seg001.trc` 등 |
| APP 종류 | APP1→MeasuredEHF, APP2→HeavyHand, APP3→AddBox | MeasuredEHF, HeavyHand |

### 5.2 요구사항

1. **Symmetric 프로토콜**: MATLAB 원본 방식 그대로 구현 (findpeaks 기반 Up/Down 분할)
2. **Asymmetric 프로토콜**: 현재 Python 방식 유지 (BPM 기반 고정 윈도우)
3. 피험자의 프로토콜 정보는 `SUB_Info.py` → `subjects[namecode]["protocol"]`에서 가져옴
4. `config_methods.py` → `PROTOCOL_Candidates`에서 프로토콜별 APP 목록, trial 수 참조

### 5.3 프로토콜별 APP 구성

```python
# config_methods.py (현재 코드 반영)
PROTOCOL_Candidates = {
    "Symmetric": {
        "APPs": ["MeasuredEHF", "HeavyHand", "AddBox"],
        "segment_style": "UpDown",
        "segmentation": {"method": "findpeaks", "pair_threshold": 0.5},
    },
    "Asymmetric_Pilot": {
        "APPs": ["MeasuredEHF", "HeavyHand"],
        "segment_style": "UpDown",
        "segmentation": {"method": "findpeaks", "pair_threshold": 0.005},
    },
    "Asymmetric": {
        "APPs": ["MeasuredEHF", "HeavyHand", "preRiCTO", "postRiCTO"],
        "segment_style": "ABC",
        "segmentation": {
            "method": "bpm_window",
            "BPM_DURATION": {10: 6.0, 16: 3.75},
            "CONTACT_THRESHOLD_N": 5.0,
            "CONTACT_MIN_DUR_SEC": 0.5,
            "SKIP_FIRST_N": 1,
            "CYCLE_OFFSET_SEC": -1.5,
        },
    },
}
# + phase_info(), segment_labels(), phase_segment_labels() 함수 구현 완료
```

### 5.4 구현 계획

#### A. Symmetric 프로토콜 세그먼트 분할 (신규 구현)

MATLAB 원본 로직을 Python으로 포팅:

1. **이벤트 검출**: `lifting_io.py`의 `detect_box_event_pairs()` 사용 (이미 구현됨)
   - `pair_threshold = 0.5` (대칭) vs `0.005` (비대칭) → 프로토콜별 값
2. **Up/Down 분리**: `split_up_down_events()` 사용 (이미 구현됨)
3. **세그먼트별 TRC/MOT 저장** (파일명은 `PATH_RULE.ResultPaths` 클래스에서 생성):
   - `{SUB}_{cond}_{seg}.trc` (e.g. `SUB1_7kg_10bpm_trial1_U1.trc`)
   - `{SUB}_{cond}_{seg}_ExtLoad_{APP}.mot` (e.g. `SUB1_7kg_10bpm_trial1_U1_ExtLoad_MeasuredEHF.mot`)
   - APP 목록: `MeasuredEHF`, `HeavyHand`, `AddBox` (Symmetric)
4. **AddBox APP 조립**: MATLAB의 APP3 로직 Python 구현 필요 (손가락 마커 위치를 COP로 사용)
   - `LFN2`, `RFN2` 마커를 force rate(1000Hz)로 업샘플링 (마커 이름은 `config_exp_settings.py`에 정의)
   - 3,4번 포스플랫폼 force/moment = 0, COP = 손가락 마커 위치

#### B. Asymmetric 프로토콜 (기존 segment_asymmetric.py 유지 + 보완)

- 현재 구현 유지 (ABC 세그먼트 스타일, bpm_window 방식)
- `preRiCTO`, `postRiCTO` APP 구현은 별도 단계

#### C. 통합 진입점 ✅ 구현 완료

`run_get_exp_data.py`에 `_METHOD_DISPATCH` 딕셔너리로 프로토콜별 분기 구현:

```python
# run_get_exp_data.py (현재 코드)
_METHOD_DISPATCH = {
    "findpeaks": process_condition_findpeaks,
    "bpm_window": process_condition_bpm_window,
}

# process_subject() 내부:
rp = _path.ResultPaths(namecode)
for cond_key in rp.conditions:
    cp = rp.for_condition(cond_key)
    pipeline_fn = _METHOD_DISPATCH[rp.segmentation["method"]]
    pipeline_fn(rp, cp, dry_run=dry_run)
```

### 5.5 액션 아이템

- [x] `lifting_io.py`에 `transform_ExtLoad_AddBox()` (구 `assemble_app3`) 추가 완료 (finger marker COP interpolation)
- [ ] Symmetric 프로토콜용 세그먼트 분할 함수 구현 (`segment_symmetric.py`) — **보류(우선순위 낮음)**
- [x] 프로토콜 분기 진입점 구현 → `run_get_exp_data.py`의 `_METHOD_DISPATCH` 완료
- [x] `pair_threshold` 프로토콜별 분리 → `config_methods.py`의 `segmentation` 딕셔너리에 내장 완료
- [x] FULL TRC/MOT 출력 기능 유지 (세그먼트 분할 전 전체 데이터 저장)
- [ ] Asymmetric `bpm_window` 자동 분할 구현/검증 — **파일럿 실험 후 진행**

---

## 6. 기타 확인 사항

### 6.1 Butterworth 필터 cutoff frequency 보정

| | MATLAB 원본 | Python 번역 | 참조 tak2TrcMot.py |
|--|------------|-------------|-------------------|
| 마커 | `butter(4, 10/(100/2))` → fc=10 Hz | `butterworth_lowpass(data, 100, 10, 4)` → 동일 | `cutoff / (sqrt(2)-1)^(0.5/order)` 보정 적용 |
| 외력 | `butter(4, 10/(1000/2))` → fc=10 Hz | `butterworth_lowpass(data, 1000, 10, 4)` → 동일 | 동일 보정 |

- MATLAB 원본과 Python 번역은 동일한 cutoff 사용 (보정 없음).
- `tak2TrcMot.py`는 `cutoff / (sqrt(2)-1)^(0.5/order)` 보정을 적용. 이는 `filtfilt`의 double-pass 특성 보상인데, MATLAB 원본에는 없으므로 **적용하지 않는 것이 원본과 일치**.
- **결론**: Python 번역의 필터링은 MATLAB과 동일. 변경 불필요.

### 6.2 Force plate COP y=0 처리

MATLAB 원본 (line 245–256): 지면반력(FP1, FP2)의 COP_y를 `axis_zero`로 강제:
```matlab
forceStruct.p1(:,1), axis_zero, forceStruct.p1(:,3)
```

Python 번역 (`transform_ExtLoad_MeasuredEHF`, 구 `assemble_app1`): 동일하게 처리:
```python
g1p[:, 0], axis_zero[:, 0], g1p[:, 2],
```
→ 일치 ✓

### 6.3 Force plate Moment 처리

MATLAB 원본: `axis_zero, forceStruct.m1(:,2), axis_zero` → My만 사용
Python 번역: `axis_zero[:, 0], g1m[:, 1], axis_zero[:, 0]` → 동일
→ 일치 ✓

### 6.4 NaN → 0 변환

MATLAB: `FPinput(isnan(FPinput))=0;`
Python: `fpinput = np.nan_to_num(fpinput, nan=0.0)`
→ 일치 ✓

### 6.5 euler_to_rotation_matrix 일치 여부

MATLAB (`euler_to_rotation_matrix.m`): `R = Rz * (Ry * Rx)`
Python (`lifting_io.py` line 116): `return rz @ (ry @ rx)`
→ 회전 행렬 구성, 개별 Rx/Ry/Rz 정의 모두 일치 ✓

### 6.6 로드셀 포스플랫폼 인덱스

MATLAB 원본에서 대칭/비대칭 모드별로 `f3,f4` vs `f4,f5`를 사용하는 코드가 주석으로 나뉘어 있으나, 이는 비대칭 실험 당시 사용하지 않는 FP를 끄지 않고 실험한 이례적 상황에서의 하드코딩이었음. **프로토콜에 따라 인덱스가 달라지는 것이 아님.**

앞으로 모든 프로토콜에서 포스플랫폼 구성은 다음과 같이 통일 (OpenSim/MATLAB 관례에 맞춰 **1-based**):

| FP 번호 | 역할 | OpenSim 레이블 |
|---------|------|---------------|
| FP1 | 지면반력 (왼발) | `f1`, `p1`, `m1` |
| FP2 | 지면반력 (오른발) | `f2`, `p2`, `m2` |
| FP3 | 로드셀 — 손 외력 (왼손) | `f3`, `p3`, `m3` |
| FP4 | 로드셀 — 손 외력 (오른손) | `f4`, `p4`, `m4` |

코드에서도 `tak2TrcMot.py`처럼 `'f' + str(fpID)` 형태의 1-based 레이블로 접근. 프로토콜별 분리 불필요.

### 6.7 RigidBody CSV 읽기

MATLAB: `dataLines = [9, Inf]` (9번째 줄부터)
Python: `skiprows=7` → `pd.read_csv(..., skiprows=7)` → 8번째 줄이 첫 데이터 행

MATLAB의 `dataLines = [9, Inf]`는 9번째 줄부터 읽는 것. Python의 `skiprows=7`은 첫 7줄 스킵 → 8번째 줄부터 읽음.

→ **1줄 차이 가능성**. `config_exp_settings.py`에서는 `RIGID_BODY_SKIPROWS = 7`. MATLAB은 9번째 줄부터. 실제 CSV 헤더 구조를 확인하여 정확한 skiprows 값 결정 필요.

### 6.8 RigidBody CSV 샘플링 레이트 — `_upsample_rigid()` 오해

**사실**: RigidBody CSV는 **1000Hz**로 기록됨 (force 데이터와 동일 레이트).

MATLAB 원본에서도 `for t = 1:length(xtime)`로 force 프레임(1000Hz)만큼 루프를 돌면서 `RigidBody.RotX(t)`에 동일 인덱스로 직접 접근. 즉, 업샘플링 없음.

**Python 코드 (`lifting_io.py`)에서의 영향:**

`_upsample_rigid()` 함수는 rigid body가 100Hz라고 가정하고 작성된 이름/주석이지만, 실제 로직은 프레임 수가 같으면 그대로 반환(`n_rigid == n_force → return rigid`)하므로 **기능적 오류는 없다.**

~~아래 위치의 잘못된 주석/네이밍은 수정 필요~~ → **수정 완료**:
- ✅ 함수 이름: `_match_rigid_length()` (line 223)
- ✅ docstring: "Match rigid-body sequence length to force length."
- ✅ `transform_ExtLoad_MeasuredEHF` 내 호출: `_match_rigid_length(rigid, n)` (line 363)

---

## 7. 실행 순서 (우선순위)

| 순서 | 작업 | 관련 문제 | 난이도 | 상태 |
|------|------|----------|--------|------|
| 1 | ~~`rotations=None` 지정~~ | 문제3 | 즉시 | ✅ 기본값 `None` + config 주석 |
| 2 | ~~`write_trc()` 접두사 제거 조건부 처리~~ | 문제4 | 간단 | ✅ 콜론 유무 분기 구현 |
| 3 | ~~`transform_ExtLoad_MeasuredEHF()` COP 회전변환 버그 수정~~ | 문제2 | 핵심 | ✅ `r @ local_cop` 적용 |
| 4 | ~~C3D 읽기를 `opensim.C3DFileAdapter` 기반으로 재작성~~ | 문제1 | 중간 | ✅ ezc3d 완전 제거 |
| 5 | ~~`_upsample_rigid` → `_match_rigid_length` 이름/주석 정정~~ | 6.8 | 간단 | ✅ |
| 6 | ~~`transform_ExtLoad_AddBox()` 함수 추가~~ | 5.4-A | 중간 | ✅ finger marker COP |
| 7 | Symmetric 세그먼트 분할 구현 (`segment_symmetric.py`) | 5.4-A | 중간~큰 | ⬜ |
| 8 | ~~프로토콜 분기 진입점 구현~~ | 5.4-C | 중간 | ✅ `run_get_exp_data.py` |
| 9 | ~~RigidBody CSV skiprows 검증~~ | 6.7 | ✅ 완료 |
| — | **인프라**: `config_methods.py` APP/세그먼트 구조 정비 | 5.3 | — | ✅ 완료 |
| — | **인프라**: `PATH_RULE.py` → `ResultPaths`/`ConditionPaths` 클래스 | §9 | — | ✅ 완료 |
| — | **인프라**: `config_exp_settings.py` 물리 상수 분리 | §8 | — | ✅ 완료 |

---

## 8. 파일 구조 계획

```
Codes/
├── SUB_Info.py                    # 피험자 메타데이터 (protocol, conditions, body_mass 등)  ✅
├── config_methods.py              # 프로토콜별 APP 목록, segment_style, 세그먼트 파라미터  ✅
│                                  #   + phase_info(), segment_labels(), phase_segment_labels()
├── PATH_RULE.py                   # 경로 관리 (ResultPaths / ConditionPaths 클래스)  ✅
│                                  #   + 모듈 레벨: ROOT_DIR, DATA_DIR, OPENSIM_DIR 등
│                                  #   + ResultPaths(namecode): 입출력 경로 & 파일명 생성
│                                  #   + ConditionPaths: condition 바인딩된 경로 컨텍스트
├── a_Get_Exp_Data/
│   ├── PLAN_m2py_verification.md  # 이 문서
│   ├── lifting_io.py              # 데이터 I/O 함수 (수정 대상 — 아직 미수정)
│   ├── config_exp_settings.py     # 장비 상수, 필터, threshold, 로드셀 부호/오프셋  ✅
│   ├── segment_symmetric.py       # Symmetric 프로토콜 세그먼트 분할 (미구현)
│   ├── segment_asymmetric.py      # Asymmetric 프로토콜 세그먼트 분할 (기존 코드 기반, 리팩토링 필요)
│   └── run_get_exp_data.py        # 통합 진입점 (프로토콜 분기 구현 완료)  ✅
│   
│   # MATLAB 원본 헬퍼 (참조용 유지)
│   ├── euler_to_rotation_matrix.m
│   ├── Import_RigidBody_csv.m
│   ├── writetrc.m
│   ├── writeMot.m
│   ├── generateMotLabels.m
│   └── RotMat.m
```

설정 파일 역할 분담:

- **SUB_Info.py** → 피험자 메타데이터 (protocol, conditions, body_mass 등)
- **PATH_RULE.py** → `ResultPaths(namecode)` 클래스로 모든 입출력 경로 관리 (디렉토리 생성, 파일명 생성, condition/phase/segment 자동 해석)
- **config_methods.py** → 프로토콜별 APP 목록, `segment_style`, 세그먼트 분할 파라미터, `_PHASE_MAP`
- **config_exp_settings.py** → 장비 상수 (로드셀 부호, 오프셋, 필터, threshold, 좌표계 회전)

---

## 9. 결과 폴더 및 파일 구조 계획 ✅ `PATH_RULE.ResultPaths` / `ConditionPaths`로 구현 완료

> 아래 구조는 `PATH_RULE.py`의 `ResultPaths` 클래스 메서드들이 자동 생성하는 디렉토리/파일명 규칙과 일치함.

---

## 10. 검증 체크리스트

각 수정 후 아래 항목을 확인:

- [ ] 마커 TRC 파일: 좌표값이 MATLAB 출력과 1e-4 이내 일치
- [ ] MeasuredEHF MOT 파일: Force, Moment, COP 값이 MATLAB 출력과 1e-4 이내 일치
- [ ] HeavyHand MOT 파일: GRF only 값 일치
- [ ] AddBox MOT 파일 (Symmetric): 손가락 마커 COP 일치
- [ ] 세그먼트 분할 이벤트 시점이 MATLAB BoxEvents와 일치 (Symmetric)
- [ ] 세그먼트 분할 윈도우가 BPM 기반으로 정확히 잘림 (Asymmetric)
- [ ] 접두사 있는 C3D / 없는 C3D 모두 정상 TRC 출력
