# OpenSim 파이프라인 운영 (진행·멀티워커·SO 고착)

- **대화 시작**: 2026-09-10
- **관련 transcript (대표)**: [진행시트](8086f4e4-0696-4421-a0d3-1202512cb8a2), [멀티코어](8f5a4905-d7c8-49fe-9881-1b3047013d9f), [SO 엣지](2671f701-2524-48a1-a96f-41cab8a2cfb4), [ID](0af1afda-ccf2-4e7a-b88a-19746ac7b927), [타임아웃](6eccaa44-b062-48b0-9307-428ba01c9c00)·[원인](7b48e37d-d636-49bf-b4e8-10db9d0b0d73), [감시·게이트](dfeba12f-cce8-44c6-b493-73643bbeaf58)·[b932a006](b932a006-3f6b-4d41-a6b7-5b35a0a09a94), [5분 로그 타임아웃](1113974c-8809-40ec-af1e-0aed77e1d9db), [워커 단위 롤백](c428cea1-fdd7-46d6-9110-daa41d3d863b)
- **핵심 산출**: `run_opensim_pipeline.py`, `update_pipeline_progress.py`, `retry_so_edge.py`, `OpenSim_Process/_Main_/Asymmetric/pipeline_progress.xlsx` · `pipeline_trouble.json`

---

## 1. 배경·목표

8명(이후 확장) 피험자 × 조건 × AB·BC·CA × app(MeasuredEHF, HeavyHand, preRiCTO, postRiCTO) × 툴(ExtLoad, IK, BK, SO, JR, ID)을 돌리면서 **무엇이 끝났는지·어디서 막혔는지**를 한눈에 보고, CPU를 쓰되 OpenSim 안정성을 지키려 함.

---

## 2. 처리·정리한 내용

### 2.1 진행 체크시트 (09-10)

- `OpenSim_Process/_Main_/Asymmetric/pipeline_progress.xlsx` 생성.
- `update_pipeline_progress.py`: PATH_RULE에 맞는 결과 파일 존재 여부로 체크박스 갱신 (`run_opensim_pipeline.py`는 건드리지 않는 조건으로 시작 → 이후 파이프라인과 연동 강화).
- Matrix에 **BK** 열 추가; 실패 세그먼트는 Detail에 ☒; **복구되면 failed에서 제거** 로직 추가.
- CLI: `--namecode` / 조건 파싱, 미지정 시 전체 리스트.

### 2.2 멀티프로세싱·메모리 (09-10~12)

- `run_opensim_pipeline.py` workers, 세그먼트 단위 처리 후 메모리 정리 방향.
- `--skip-existing`: 이미 mot/sto 있으면 스킵.
- SO 동시 다발 실패 → **동시 SO 개수/경합** 가설, 워커 수·실행 전략 조정.
- `--max-tasks-per-child`: 워커 재생으로 RAM 누수 완화 시도 → **체감 속도 저하**로 사용자 불만 → 해당 구현 **롤백** 후, 묶음 단위를 조건이 아니라 **피험자 단위**로 워커가 쉬지 않게 하는 쪽으로 재설계 논의·반영.

### 2.3 ID 툴 (09-11)

- OpenSim Inverse Dynamics를 파이프라인에 추가; **HeavyHand만** 루프.
- 초기 `setModelFilename` AttributeError → API 호출 방식으로 수정 후 커밋.

### 2.4 SO 초반 실패 · `retry_so_edge` (09-11)

- 일부 trial: 시작 직 근처에서 SO 실패 → **0.05 s부터** 돌리면 통과하는 패턴.
- 전략: IK/ExtLoad를 덮어쓰지 않고, trouble 목록을 읽어 SO(+JR,BK)를 **잘라 재시도**한 뒤, 0.01–0.04 s 행을 0.05 s 값으로 **패딩 복원**.
- MeasuredEHF/HeavyHand(및 pre/post) **앱 구분 없이** 같이 재시도; ExtLoad XML 없는 건 제외.
- 수동 단일 trial 모드 지원; 커밋.

### 2.5 SO freeze · 타임아웃 (09-11~13) — **현행 확정**

- 오류 없이 최적화 **고착** → 워커 타임아웃 후 trouble 기록·다음 세그먼트.
- 한때 wall-clock **30분**을 썼으나 **너무 김** → 폐기.
- **확정 (2026-09-16)**: OpenSim 로그가 **5분 동안 무변동**이면 고착으로 보고 다음 세그먼트로 넘김. 얼어붙은 **sim-time을 json에 기록**.
- 코드: `pipeline_rules.DEFAULT_ANALYZE_TIMEOUT_S = 300` (log-stall), `opensim_pipeline_handlers` stall 감시.

### 2.6 원인 조사 (09-12)

- OpenSim/simTK best practice: 입력(모델·모션·힘) 품질, IK 노이즈 → 가속도 스파이크.
- HeavyHand **ID**로 문제 프레임 후보 조사 (KTY 7kg_10bpm 1AB, KCH 동조건 등).
- 사용자 피드백: Ctrl+C 중단·early-window로 안 되는 KTY(~3.54 s 동일 고착)는 후보에서 제외하고 좁힘.
- 가설: coordinate ROM 한계/특이점 근처 — **완전 확정 전 중단·추가 조사 여지**.
- 피험자 편중 → AddBiomechanics 스케일링/모델링 이슈 가능성도 조사 요청.

### 2.7 감시·게이트·워커 모니터 (09-12~14)

- 10분(또는 15분)마다 `update_pipeline_progress`로 완료 감지 → 다음 app/피험자 커맨드 자동 기동 (`watch_gate_*` 류).
- 워커별 조건·cycle·segment·app·tool 표 모니터; IDLE 의미 설명; pre 돌리는 동안 **같은 trial post 병렬** 가능 여부 논의.
- trouble 시각 set을 json에 누적.
- KMJ 실패 17건을 `retry_so_edge` **워커 17**로 임시 재시도 등 운영 대응.

### 2.8 기타 운영

- 기능별·시간순 **커밋** 여러 차례 (노트북 제외, 체리픽).
- CPU: workers↑해도 총사용량 고정이면 **시분할**일 수 있음 — 코어/논리 프로세서 기준 워커 수 가이드 (i9-14900K 논의).

---

## 3. 미완·열린 이슈

- [ ] **전 cohort SO/JR 완주** 및 trouble 전량 소진 (피험자·조건별로 계속 잔여).
- [ ] SO가 **서로 다른 trial인데 같은 sim-time에서 멈춘다**는 보고의 진위·원인 (로그 해석 논쟁 후, “코드 회귀 여부”를 다른 창에서 보라는 요청 — **근본 해결 미완**).
- [ ] 타임아웃 시 **에러 로그 + 고착 초**를 항상 남기는 UX — 요구는 강하게 반영 중이었으나, 운영 중 누락 재발 가능 → 지속 점검.
- [ ] KTY류 **재현 가능한 동일 시각 freeze** — early-window로 안 되는 케이스의 모델링/ROM/입력 수정 프로토콜.
- [ ] Dropbox(`E:\Dropbox\SEL\BOX`)로 `OpenSim_Process` 전체 + `Analysis/Asymmetric/RiCTO` **미러** — 터미널/robocopy 커맨드만 안내, **상시 동기화 미구현**.
- [ ] 자동 게이트가 파이프라인을 **느리게 만드는지**에 대한 우려 → 모니터 취소·간격 조정으로 완화했으나, 장기 자동 오케스트레이션은 여전히 수동+감시 혼재.

---

## 4. 연구·공학 발전 방향 논의

- 대량 OpenSim 배치를 **연구 병목**으로 인식 → 진행 가시화·재시도·타임아웃이 “분석 과학”과 동급의 인프라.
- SO 실패를 “랜덤”이 아니라 **입력·모델 품질** 문제로 좁히는 방향 (ID로 프레임 진단).
- 워커 스케줄: app 직렬 vs pre/post 병렬, max-tasks-per-child vs 피험자 단위 큐 — **처리량 vs 안정성** 트레이드오프가 반복 주제.

---

## 5. 시도하다 만 것 / 되돌린 것

| 시도 | 결과 |
|------|------|
| `--max-tasks-per-child`로 RAM 관리 | 속도 저하 → **롤백**, 피험자 단위 스케줄로 선회 |
| 고정 30분 wall-clock 타임아웃 | **폐기** → **5분 로그 무변동**으로 확정 |
| 게이트 스크립트로 PJH→다음 자동 | 느림/좀비 프로세스 이슈로 **취소·수동 재기동** 반복 |
| 클라우드 에이전트로 타임아웃 PR | 타임아웃만 체리픽 머지; 무관 삭제 변경은 버림 |
| IK/ExtLoad 앞 0.01–0.04를 0.05로 덮어쓰기 | **기각** (덮어쓰기 관리 부담) → sidecar `retry_so_edge` |

---

## 6. 자주 쓴 커맨드 패턴 (참고)

```text
python run_opensim_pipeline.py --namecode <CODE> --tools so,jr --apps MeasuredEHF,HeavyHand,preRiCTO,postRiCTO --workers N --skip-existing
python update_pipeline_progress.py
python retry_so_edge.py --namecode <CODE>
```
