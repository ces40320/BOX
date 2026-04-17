# `detect_neutral_phase` 설계 메모 (neutral quiet standing 구간 검출)

> **상태 (2026-04-09)**: 이 설계에 따른 **코드 구현·파이프라인 연동은 전면 취소**되었다. 아래는 당시 문헌·아이디어 정리를 **보관용**으로만 둔다.  
> **관련 플랜**: [`PLAN_m2py_verification.md`](PLAN_m2py_verification.md) §5 (프로토콜별 세그먼트 분할)  
> **작성일**: 2026-04-09

---

## 1. 목적

한 조건(condition)에 대응하는 C3D에서 이미 로드한 마커 사전(`read_c3d_markers` 결과와 동일한 구조: `markers["time"]`, 각 마커 `(n_frames, 3)` 등)을 입력으로,

- **리프팅/작업 구간**(신호에 맞춘 동작)과  
- **차렷·조용한 서기(neutral quiet standing, 이하 neutral)** 구간  

을 **시간(초)** 기준으로 구분한다.  
출력은 **프레임 인덱스가 아니라 `time` 배열상의 연속 구간**(예: `(t_start, t_end)` 리스트)을 목표로 한다.

초기 1~2초는 피험자가 차렷을 유지한다는 **교정(calibration) 가정**을 이용해, 그 구간의 위치·속도 통계를 “정답(neutral) 분포”로 저장한다.

---

## 2. 실험 좌표계와 코드베이스 좌표계 정합

- **실험실 서술(기획)**: 글로벌 기준 **Z축 음의 방향쪽으로 시선을 향하여 정면**을 본다고 가정.
- **현재 파이프라인 설정** (`config_exp_settings.py`): Motive export가 **OpenSim 관례(Y-up)** 이라서 `read_c3d_markers(..., rotations=None)` 사용을 전제로 함.  
  박스 이벤트 검출(`lifting_io.detect_box_event_pairs`)은 박스 마커의 **Y좌표** 평균을 “수직 방향 변화”로 사용함.

**구현 시 주의**: “머리 높이” 등 **수직축**은 사용자의 Z 서술이 아니라, **실제 TRC/C3D에 기록된 세 번째 성분 중 어느 축이 중력에 대응하는지**를 한 번 확인하는 것이 안전하다.  
`detect_neutral_phase` 내부에서는 `vertical_axis ∈ {0,1,2}` 또는 설정으로 두고, calibration 구간에서 중력 방향 일관성만 맞추면 된다.

해부학적 마커 정의는 논문 `e:\Dropbox\SEL\BOX\Documents\Master Thesis\석사학위논문_최은식.pdf` (목차 15–17쪽 / 슬라이드 25–27 부근 표)와 정합시키면 된다. (이 저장소 밖 경로이므로 CI/다른 PC에서는 해당 PDF가 없을 수 있음.)

---

## 3. 문헌·관행 요약 (웹 조사 기반)

조용한 서기(quiet standing)는 생체역학에서 **작은 진폭의 자세 흔들림(postural sway)** 으로 기술된다.

| 아이디어 | 내용 | 본 설계에의 함의 |
|----------|------|------------------|
| **전신 CoM의 수평 흔들림** | 조용한 서기에서 CoM은 작은 범위에서 진동; 리프팅 시에는 큰 이동·가속 | 마커만 있을 때 **골반/몸통/발목 근처 마커의 가속도·속도 RMS** 또는 **단순 CoM 프록시**(예: 골반+흉곽 가중 평균)의 이탈로 구분 가능 |
| **역진자(inverted pendulum)** | 발목–엉덩이 전략으로 AP sway가 지배적 | 수직축 주변 **저주파 성분**은 neutral에도 존재하므로, **고주파·대진폭 이동**과 **저주파 소진폭**을 함께 봐야 함 |
| **속도/가속도 임계 + 안정 구간** | 보행 후 “서기” 검출에서는 발·발가락 속도 영교차, 감속 구간 제외 등 시간 임계를 씀 | 리프팅 과제에서는 **calibration 대비 z-score** + **최소 지속 시간(min dwell)** 이 실무적으로 견고함 |
| **PCA / 주성분 움직임** | sway를 저차원으로 분해해 AP/ML 전략 설명 | 데이터가 쌓이면 neutral vs lifting을 **캘리브레이션 공간에서의 거리**로 정의하는 데 활용 가능 (1차 구현은 선택) |

참고 링크(개념 확인용):

- [Attainment of Quiet Standing… (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6593307/)
- [Kinematic and kinetic validity of the inverted pendulum model in quiet standing (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0966636203000377)
- [Estimating whole-body centre of mass sway during quiet standing with IMUs (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11730423/) — 마커 대신 IMU이나, “CoM sway” 개념은 동일

**요약**: “neutral = 절대 좌표가 한 점에 고정”이 아니라 **작은 범위에서의 랜덤 sway** 이므로, **calibration 구간의 평균·공분산 + 속도 상한** 조합이 문헌과도 맞고 구현도 단순하다.

---

## 4. 기획안(직관) 검토

| 직관 | 타당성 | 한계·보완 |
|------|--------|-----------|
| **머리 마커의 수직축(‘높이’)이 크면 서 있는 경향** | 대체로 타당(상체 기립) | 리프팅 중에도 상체는 서 있으므로 **단독 지표로는 lifting vs neutral 구분 불가**. 골반 대비 **상대 높이** 또는 **calibration 대비 변화**가 필요 |
| **손–박스 거리가 크면 핸들링 종료 가능성** | 이 과제에 특히 유력 | 박스를 놓은 뒤 neutral에서 거리가 멀어짐. 다만 **박스를 안 잡은 채 몸 옆에만 둔 자세**와 구분은 추가 규칙 필요 |
| **손–골반 거리가 가까우면 neutral 가능성** | 어느 정도 타당 | 팔을 앞으로 뻗은 준비 자세·회전에 민감. **좌우 평균·최소값** 등으로 완화 |

**결론**: 세 가지 모두 **보조 feature**로는 강하고, **단일 임계값**보다는 §5의 **다변량 점수 + 지속시간**이 견고하다.

---

## 5. 권장 알고리즘 스케치 (`detect_neutral_phase` 구현 시)

입력:

- `markers`: `lifting_io.read_c3d_markers`와 동일 형식 (`"time"`, 마커명 → `(n,3)`).
- `calibration_duration_s`: 기본 1.0~2.0 (설정 가능).
- (선택) 마커 이름: 골반/머리/손/박스 등 — `config_exp_settings.py`의 `LTA_BOX`, `RTA_BOX`, `LFN2`, `RFN2` 및 논문 표의 ASIS/PSIS 등과 연동.

단계:

1. **전처리**  
   - 기존 파이프라인과 동일하게 **저역통과**(예: `MARKER_FILTER_HZ = 10 Hz`) 후 미분하여 속도 추정(중앙차분 + 경계 처리).  
   - 또는 짧은 윈도우(0.25~0.5 s) **RMS 속도**로 노이즈 완화.

2. **Calibration**  
   - `t0`부터 `t0 + calibration_duration_s`에 해당하는 프레임 집합 `C`.  
   - feature 벡터 예시(프레임별):  
     - 골반(또는 좌우 ASIS 평균) 기준 **상대 위치**: 머리, 양 손가락(`LFN2`, `RFN2`), 양 박스(`LTA_BOX`, `RTA_BOX`) 등.  
     - 동일 마커들의 **속도 노름** 또는 수직·수평 성분.  
   - `C`에서 각 feature의 **평균 μ**와 **공분산 Σ**(차원이 작으면 대각 근사도 가능) 추정.

3. **프레임별 점수**  
   - **Mahalanobis 거리** `d(t) = sqrt((x(t)-μ)ᵀ Σ⁻¹ (x(t)-μ))` 또는 표준화 **유클리드 거리**.  
   - **속도 게이트**: 예) 주요 마커 속도 노름이 calibration 구간의 (중앙값 + k·MAD) 이하일 때만 neutral 후보.  
   - 최종 `score_neutral(t)` = 거리 임계 이하 **且** 속도 게이트 통과.

4. **시간 구간화**  
   - 이진 마스크에 **최소 지속 시간** `min_segment_s`(예: 0.3~0.5 s) 적용해 짧은 깜빡임 제거.  
   - (선택) **히스테리시스**: neutral 진입은 엄격, 이탈은 느슨하게 해 경계 떨림 감소.  
   - 연속 구간을 `(t_start, t_end)`로 변환해 반환.

5. **출력**  
   - `List[Tuple[float, float]]` (초).  
   - 디버깅용으로 `time`, `score`, `mask`를 dict에 넣는 반환 형태도 고려.

**강건성 팁**

- 마커 결측(NaN) 프레임은 마스크 False 또는 이전값 홀드 후 짧은 구간만 허용.  
- calibration 구간에 실제로 움직임이 섞였으면 μ, Σ가 왜곡되므로, **calibration 품질 검사**(예: 해당 구간 속도 RMS가 전 trial 대비 과도하면 경고)를 로그로 남기기.

---

## 6. `run_get_exp_data.py` 연동 (구현 시)

- `_METHOD_DISPATCH`에 **`neutral_phase` 또는 세 번째 파이프라인**을 추가할지, 기존 `findpeaks`/`bpm_window` **전에** 공통 전처리로 `detect_neutral_phase`를 호출할지는 프로토콜별로 결정.  
- 함수 시그니처 예 (의사코드 수준):

```python
def detect_neutral_phase(
    markers: dict,
    *,
    calibration_duration_s: float = 1.5,
    min_segment_s: float = 0.4,
    marker_filter_hz: float | None = 10.0,
) -> list[tuple[float, float]]:
    ...
```

실제 마커 키 이름은 C3D 라벨(접두사 `ModelName:` 등)과 일치해야 하므로, `write_trc`와 동일한 **라벨 정규화** 규칙을 재사용하는 것이 좋다.

---

## 7. (항목 2) 핵심 마커만 추리기 — **별도 스크립트** 계획

요청대로 **기존 파이프라인 밖**에서 수행. 신규 파일 예: `Codes/a_Get_Exp_Data/analyze_neutral_marker_subset.py` (이름은 구현 시 조정).

**목표**: 전체 마커 집합 대비 **작은 부분집합**으로도 `detect_neutral_phase`와 유사한 구간 일치도를 유지하는지 정량화.

**절차 제안**

1. **라벨 확보**  
   - 수동 구간 라벨(영상/force 동기화) 또는 **현재 제안 알고리즘의 “full feature” 결과**를 pseudo-ground-truth로 사용(반복 개선 시 주의).

2. **후보 feature**  
   - §5의 상대위치·거리·속도를 **마커 단위/쌍 단위**로 나열.

3. **중요도 분석**  
   - **Permutation importance** 또는 **L1 정규화 회귀(LASSO)** 로 구간 분류(또는 score 회귀)에 기여하는 마커 순위.  
   - **Greedy backward elimination**: 마커 하나씩 제거하며 F1/IoU(시간축 겹침) 측정.

4. **산출물**  
   - 피험자·조건별 권장 마커 목록 CSV,  
   - 최소 집합(예: 골반+머리+양손+양박스 6개)이 full set 대비 손실이 얼마인지 표.

**주의**: subset은 **특정 코호트에 과적합**되기 쉬우므로, leave-one-subject-out 등으로 검증하는 것을 문서화해 두는 것이 좋다.

---

## 8. 다음 액션 (체크리스트)

구현 취소로 **이 섹션의 실행 항목은 보류·무효**이다.

---

## 9. 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-04-09 | 초안: 문헌·직관 정리, 알고리즘 스케치, 핵심 마커 분석 스크립트 계획. 코드 미구현. |
| 2026-04-09 | 설계·구현 경로 전면 취소. `run_get_exp_data.py` 내 구현 및 임시 스크립트 제거, 본 문서만 보관. |
