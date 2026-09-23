# Strategy B · C 로드맵 (현 RiCTO 본선 밖)

- **원 논의**: ~2026-01 (Overleaf `Strategy_B_*.tex`, `Strategy_C_*.tex`, `BOX_2_Intro.tex`)
- **PLAN 정리일**: 2026-09-16
- **상태**: **B = 이 연구에서 배제** / **C = 훨씬 나중** (딥러닝 피팅이 필요하다고 판단될 때)

---

## 1. 한 줄 정의 (오해 방지)

| Strategy | 요지 | 현 연구 |
|----------|------|--------|
| **A** | 수학·알고리즘 (RMO → 오늘의 **RiCTO**). 손 로드셀 없이 EHF·접촉 창 추정. **측정 GRF는 유지.** | **진행 중** |
| **B** | **MuJoCo** soft-contact 등으로 EHF를 물리 시뮬레이션한 뒤 OpenSim으로 넘기는 하이브리드 | **배제** |
| **C** | **Deep-EHFNet** 등 딥러닝으로 운동학→EHF 피팅. 옵션에 따라 **GRF까지 없는** sensorless 트랙 | **장기 보류** |

### “GRF 제거”가 아닌 점

`RICTO_PLAN`에 적혀 있던 “GRF 제거 / Strategy B·C”는 **지금 RiCTO에서 지면반력을 빼겠다**는 뜻이 **아니다**.

- **현재 RiCTO**: 손 로드셀만 제거하고, **GRF(force plate)는 측정값 사용**.
- **Strategy C의 일부 옵션**: 장기적으로 force plate까지 없을 때를 가정한 추정(딥러닝·물리 프록시) — **별 트랙**.

---

## 2. Strategy B — 배제 사유 (이 연구)

- 물리엔진(MuJoCo) soft-contact + domain randomization 등은 논문 한 편의 스코프·검증 부담이 큼.
- 지도·투고 스토리는 Strategy A(RiCTO) vs MeasuredEHF / HeavyHand / 마커 단순법에 집중.
- **재개 조건**: A로 한계가 명확히 남고, soft-contact 물리 추정이 유일한 돌파구일 때 재논의.

---

## 3. Strategy C — 나중 예정

- TCN 등으로 운동학→EHF (Deep-EHFNet 계열).
- A(RiCTO)만으로 오차·일반화가 부족하거나, **GRF조차 없는** 현장 설정이 필수가 되면 검토.
- 할 일 (먼 미래):
  - [ ] A 대비 오차 ceiling·실패 모드 문서화
  - [ ] Option1 (GRF 있음) vs Option2 (GRF 없음) 중 연구 질문 확정
  - [ ] 학습 데이터·누수(MeasuredEHF) 정책
  - [ ] OpenSim 연계 vs end-to-end 부하 추정 범위

---

## 4. 참조

- `E:\Dropbox\…\strategy_tex\Strategy_{B,C}_{Kor,Eng}.tex` (또는 Overleaf `BOX#2`)
- `BOX_2_Intro.tex` (A/B/C 한 줄 소개)
- `Codes/c_Run_Tools/optimization/RICTO_PLAN.md` §11 (건드리지 않는 것 — 문구는 본 md로 정정)
- 7일 갈무리 인덱스: `Codes/PLAN/260916_7일대화갈무리-인덱스.md`
