# Run Tools Refactoring Plan (Aligned to `OpenSim_Process` Structure)

## 1) 목적

`OpenSim_Process/STRUCTURE_PLAN.md` 기준 디렉토리 구조를 표준으로 삼아,  
현재 `c_Run_Tools`의 분산 실행 방식(`*_SET.py` / `*_RUN.py` 개별 실행)을 **단일 파이프라인 실행 방식**으로 전환한다.

핵심 목표:

- 경로/파일명 규칙을 `PATH_RULE.py`로 완전 일원화
- 실행 단위를 `subject -> condition -> section -> segment -> app`으로 정규화
- 결과물을 `OpenSim_Process/_Main_/...` 계획 구조와 1:1 매핑


## 2) 구조 기준 (Source of Truth)

디렉토리/파일 배치의 기준 문서는 다음 2개다.

1. `OpenSim_Process/STRUCTURE_PLAN.md`
2. `Codes/PATH_RULE.py` (`ResultPaths`, `ConditionPaths`)

즉, 리팩토링 후 `c_Run_Tools`는 경로를 직접 조합하지 않고 다음만 사용한다.

- `rp = ResultPaths(namecode)`
- `cp = rp.for_condition(cond)`
- `cp.<tool>_path(...)`, `cp.setup_<tool>_path(...)`


## 3) 계획 구조 반영 포인트

### 3.1 레벨 구조 고정

모든 생성 파일은 아래 계층을 강제한다.

- `OpenSim_Process/_Main_/<Protocol>/<SUB>/Model_osim/`
- `OpenSim_Process/_Main_/<Protocol>/<SUB>/<Condition>/<Section>/`
- `<Section>` 하위 고정 폴더:
  - `Markers/`
  - `ExtLoad/`
  - `IK/` 또는 `IK_<suffix>/`
  - `BK/`
  - `SO_<App>/`
  - `JR_<App>/`

### 3.2 프로토콜별 section 스타일 반영

- `Symmetric` -> `Up`, `Down` (`UpDown` style)
- `Asymmetric` -> `AB`, `BC`, `CA` (`ABC` style)

섹션/세그먼트 생성은 반드시 `config_methods.py` 함수 사용:

- `section_info(style)`
- `section_labels(n_cycles, style)`
- `section_segment_labels(n_cycles, style)`

### 3.3 파일명 규칙 반영

`STRUCTURE_PLAN.md`에 나온 파일명 패턴을 `PATH_RULE.py` 메서드로 고정:

- TRC: `trc_name()`
- ExtLoad mot/xml: `extload_name()`, `setup_extload_name()`
- IK mot/xml: `ik_name()`, `setup_ik_name()`
- BK sto/xml: `bk_name()`, `setup_bk_name()`
- SO sto/xml: `so_name()`, `setup_so_name()`
- JR sto/xml: `jr_name()`, `setup_jr_name()`

### 3.4 kg-aware 모델 선택 규칙 (b_Build_Model 산출물 정합성)

`Codes/b_Build_Model/` 파이프라인은 피험자 conditions 의 `{w}kg` prefix 별로 다음을
**전부 사전 생성**한다 (`STRUCTURE_PLAN.md` Notes 참고):

- `SUB{n}_Scaled.osim`                          (베이스, kg 무관)
- `SUB{n}_Scaled_HeavyHand_{w}kg.osim`
- `SUB{n}_Scaled_WeldBox_{w}kg.osim`
- `SUB{n}_Scaled_SplitBox_{w}kg.osim`

따라서 `c_Run_Tools` 의 모든 핸들러는 condition 문자열에서 kg 를 파싱해
**해당 kg variant osim 만** 사용해야 한다.

기준 매핑 (잠정, `pipeline_rules.py` 에 표로 고정):

| App           | 모델 선택 규칙                                          |
|---------------|---------------------------------------------------------|
| `MeasuredEHF` | `rp.model_path("")`                                     |
| `HeavyHand`   | `rp.model_path(f"HeavyHand_{w}kg")`                     |
| `AddBox`      | `rp.model_path(f"WeldBox_{w}kg")` *or* `f"SplitBox_{w}kg"` *(미정, §7 참조)* |
| `preRiCTO`    | `rp.model_path("")` (베이스 모델; RiCTO 분기는 외력/세팅 단)   |
| `postRiCTO`   | `rp.model_path("")` (베이스 모델; RiCTO 분기는 외력/세팅 단)   |

요구사항:

- condition 문자열 → `w_kg` 추출 유틸을 단일 위치에 둔다.
  - 권장: `PATH_RULE.ResultPaths` 또는 `ConditionPaths` 에 `box_kg(cond) -> int` 추가
  - 또는 `Codes/b_Build_Model/add_hand_mass_model.py:box_weights_from_conditions` 와
    동일 로직을 `pipeline_rules.py` 로 일원화 (중복 구현 금지).
- 핸들러는 모델 경로를 **문자열 조합 없이** `rp.model_path(<variant_with_kg>)` 로만 획득.
- 모델 파일이 없으면 즉시 `FileNotFoundError` 로 실패 (no silent fallback).
  - 메시지에 `b_Build_Model/b_Main.ipynb` 선행 실행을 안내.


## 4) 타겟 아키텍처

### 4.1 단일 엔트리포인트

신규: `Codes/c_Run_Tools/run_opensim_pipeline.py`

- 입력: `--namecode`, `--condition`, `--tools`, `--apps`, `--dry-run`
- 내부 컨텍스트:
  - `rp = ResultPaths(namecode)`
  - `cp = rp.for_condition(condition)`
  - `cp.build_tree()`로 구조 선생성
- 루프:
  - `for seg in cp.all_sections():`
  - `error_log` skip
  - tool 실행 순서대로 handler 호출

### 4.2 핸들러 분리

신규: `Codes/c_Run_Tools/opensim_pipeline_handlers.py`

- `set_extload()`
- `run_ik()`
- `set_so()`, `run_so()`
- `set_bk()`, `run_bk()`
- `set_jr()`, `run_jr()`

핸들러 규칙:

- 경로 직접 문자열 조합 금지
- 모든 I/O 경로는 `ConditionPaths` API로만 획득
- 출력 위치는 `STRUCTURE_PLAN.md`의 폴더 체계에 100% 일치

### 4.3 정책 모듈

신규: `Codes/c_Run_Tools/pipeline_rules.py`

- 앱 선택/제외 정책
- 과거 APP 네이밍 alias 정책 (`APP1~4` -> 신 네이밍)
- ground/child frame 등 JR 옵션 정책
- (필요시) protocol별 예외 동작
- **kg-aware 모델 선택 정책** (§3.4 표를 단일 dict 로 보유)
  - 입력: `(app, w_kg)` → 출력: `model_type` 문자열 (`""`, `"HeavyHand_{w}kg"`,
    `"WeldBox_{w}kg"`, `"SplitBox_{w}kg"` 등)
  - 핸들러는 이 정책 함수만 호출하고 직접 분기 금지


## 5) 단계별 실행 전략 (구조 개편 반영)

## Phase 0 — 구조 정합성 확보

1. `cp.build_tree()` 기준으로 대상 condition 디렉토리 선생성
2. `--dry-run`에서 생성/사용될 절대 경로 출력
3. `STRUCTURE_PLAN.md` 예시와 경로/파일명 비교 체크

완료 기준:

- 경로가 `OpenSim_Process/_Main_/...` 체계로만 출력됨
- 기존 `root_dir + '\\'` 스타일 경로 조합 없음

## Phase 1 — IK/ExtLoad 우선 전환

1. `ExtLoad_XML_SET`, `IK_RUN` 로직을 handler로 이동
2. 출력 폴더를 `ExtLoad/`, `IK/`로 고정
3. condition/section/segment별 생성 파일 위치 검증

완료 기준:

- `SETUP_ExtLoad_*.xml`, `*_IK.mot`, `SETUP_IK_*.xml`가 계획 구조에 생성

## Phase 2 — SO/BK/JR 전환

1. `ANALYZE_SO_*`, `ANALYZE_BK_*`, `ANALYZE_JR_*` 핵심 로직 이관
2. 폴더 강제 매핑:
   - `SO_<App>/`
   - `BK/`
   - `JR_<App>/`
3. JR ground 결과/일반 결과 구분 규칙을 정책화

완료 기준:

- 도구별 산출물이 structure plan의 위치와 이름 규칙을 만족

## Phase 3 — 레거시 래핑 및 문서화

1. 기존 `ANALYZE_*` 파일은 thin-wrapper 또는 `legacy/`로 이동
2. README 실행법을 `run_opensim_pipeline.py` 중심으로 갱신
3. 구조/네이밍 기준 문서를 `STRUCTURE_PLAN.md`로 단일화

완료 기준:

- 신규 실행 경로가 단일화되고, 개별 파일 직접 실행이 선택사항이 됨


## 6) 검증 전략 (구조 중심)

### 6.1 구조 검증

- Subject 1개, condition 1개 실행 후:
  - `<Condition>/<Section>/` 생성 여부
  - `Markers/ExtLoad/IK/BK/SO_*/JR_*` 폴더 생성 여부
  - setup/result 파일명 패턴 일치 여부
  - **모델 선택 검증**: 각 핸들러가 사용한 osim 의 basename 이
    condition kg 와 일치하는지 (예: condition `7kg_10bpm` 에서
    `..._HeavyHand_7kg.osim` / `..._WeldBox_7kg.osim` / `..._SplitBox_7kg.osim`
    만 참조되어야 함). `--dry-run` 로그에 `[MODEL] cond=... app=... -> <basename>`
    한 줄씩 출력

### 6.2 결과 검증

- 기존 방식 대비 동일 세그먼트에서:
  - setup xml 존재
  - 핵심 결과 파일(sto/mot) 존재
  - tool별 결과 디렉토리 동일 의도인지 확인

### 6.3 운영 검증

- `--dry-run` 로그에 다음 정보 출력:
  - 대상 세그먼트
  - skip된 세그먼트(error_log)
  - tool/app 매트릭스
  - output 경로


## 7) 확인 필요 사항 (Assumptions)

1. `SUB_Info.py`의 condition key 포맷 통일 필요  
   (예: `7kg_10bpm` vs `7kg_10bpm_trial1`)
   - kg 추출은 첫 토큰 (`split("_", 1)[0]`) 기반이므로 모든 키가 `{w}kg_...` 로 시작해야 함
2. APP 명칭 마이그레이션 정책 확정 필요  
   (`APP1~4`와 `MeasuredEHF/HeavyHand/preRiCTO/postRiCTO`)
3. `STRUCTURE_PLAN.md`의 `(미정)` 항목(AddBox/WeldBox/SplitBox)을 정책에서 enabled/disabled로 명시 필요
4. **AddBox 앱 ↔ 모델 variant 매핑 결정 필요**  
   `b_Build_Model` 은 `WeldBox_{w}kg` 와 `SplitBox_{w}kg` 두 osim 을 모두 생성하지만,
   `config_methods.PROTOCOL_Candidates["Symmetric"]["APPs"]` 는 단일 `"AddBox"` 만 보유.
   결정 옵션:
    - (a) APPs 를 `["MeasuredEHF","HeavyHand","WeldBox","SplitBox"]` 로 분리
      → `SO_WeldBox/`, `SO_SplitBox/`, `JR_WeldBox/`, `JR_SplitBox/` 폴더 분기
    - (b) `AddBox` 단일 유지 + `pipeline_rules.py` 에서 한 variant 만 선택
   결정 시 본 문서 §3.4 표 및 `STRUCTURE_PLAN.md` Notes 양측 동시 갱신.
5. **preRiCTO / postRiCTO 는 베이스 모델 사용 (확정)**  
   `b_Build_Model` 에 RiCTO 변형 모델 빌더가 없는 것은 의도된 설계로, 두 앱 모두
   `SUB{n}_Scaled.osim` 을 사용한다. RiCTO 분기는 모델 단이 아니라 외력 / 세팅
   단계에서 처리됨 (상세 근거는 `STRUCTURE_PLAN.md` Notes 의 추후 보강 항목 참조).


## 8) 바로 다음 구현 액션

1. `run_opensim_pipeline.py` 생성 (`--dry-run` 포함)
2. `cp.build_tree()` 기반 구조 생성 코드 우선 반영
3. **kg-aware 모델 해석 유틸 단일화** (§3.4)
   - `box_kg(cond)` 한 곳에 정의
   - `pipeline_rules.resolve_model(app, w_kg) -> model_type` 정책 표 도입
4. IK + ExtLoad 핸들러부터 이관 (이때부터 위 (3) 사용)
5. 샘플 대상 1개로 structure validation 로그 출력 (모델 basename 포함)
