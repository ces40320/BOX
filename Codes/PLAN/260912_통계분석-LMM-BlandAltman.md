# 통계 분석 — LMM과 Bland–Altman

- **대화 시작**: 2026-09-12 (LMM·e_statistics 구획) / 피규어 집중은 2026-09-15
- **관련 transcript**: [분석 계획 §5](a7e2d5bd-b4a5-4aa1-9829-2e619648542f), [Bland–Altman·RMSE](2ed7ba15-736c-4ba0-83d0-7d0c8619e676)
- **핵심 산출**: `Codes/e_statistics/`, `Analysis/Asymmetric/_stats/`, `Analysis/Asymmetric/_stats/reports/SUB*_stats_report.md`

---

## 1. 배경·목표

- app(추정법)·템포·박스 질량(체중 정규화)·피험자 키 등 효과 분리에 **Linear Mixed Model** 사용.
- 그립/디파짓 **시점 오차**는 Bland–Altman으로 MeasuredEHF(GT) 대비 BoxMarker vs RiCTO.
- 통계는 본 적 적음 → **이론·문헌 노트**를 코드와 분리해 `e_statistics/research/`에 둠.

---

## 2. 처리·정리한 내용

### 2.1 코드·문서 구획

```
Codes/e_statistics/
  research/          # LMM 문헌·개념
  implementation/    # LMM_DESIGN, ANALYSIS_PLAN, STATS_REPORT_TEMPLATE
  stats_lmm.py, stats_bland_altman.py, stats_timing_error.py
  render_stats_report.py, run_statistics.py
```

### 2.2 LMM (진행된 것)

- 종속: 예) EHF Resultant RMSE (MeasuredEHF 대비), jamovi GAMLj 스타일 리포트 구조.
- 고정효과: `app`, `tempo_bpm`, `mass_norm_z` (+ 2-way interaction).
- 랜덤: `(1 | sub)`.
- SUB3/4/6/7 및 **SUBALL** 리포트 md/csv/png 생성 (`SUBALL_stats_report.md` 등, 2026-09-15 일자).
- Omnibus에서 app·질량·상호작용 등 유의 패턴이 리포트에 정리됨 (세부 수치는 해당 md).

### 2.3 Bland–Altman (09-15 집중)

- 점 색: **condition**(7kg_10bpm … 15kg_16bpm); 16 bpm은 채우기 없음·테두리 강조 등 반복 조정.
- 범례: condition 2×2, bias / limits of agreement 표기 (LoA 약어 대신 풀네임 쪽으로).
- 0선 얇은 검정 점선; ylim을 Combined Grip/Deposit에서 축소.
- **Combined**: BoxMarker(원·빨강) + RiCTO(세모·파랑) 동시 플롯, 각각 bias·LoA.
- 산출: `_stats/models/BlandAltman_*.png` 및 manuscript_figures 쪽 복사본.

### 2.4 시점·RMSE와 통계의 연결

- timing validation / quarter RMSE가 `_validation`·long csv로 들어가 LMM long 템플릿과 연결.
- EHF·L5S1 피규어에 체중정규화 RMSE±SD (분석 구조 PLAN과 공유).

---

## 3. 미완

- [ ] 피험자 **키** 등 anthropometry를 LMM에 본격 투입 (초기 희망; 현재는 app·tempo·mass 중심).
- [ ] Random effect singular/boundary (`SUBALL`) — 해석·모델 단순화.
- [ ] LMM을 L5S1 JR/모멘트·Residual로 확장.
- [ ] 통계 → 논문 Results 문장·표.
- [ ] Bland–Altman `_figures` vs `_stats` 동기화.
- [ ] 마커 공란: long 테이블 `marker_ok`/n과 LMM available-case 규칙 정렬 ([260914…](./260914_마커기반-접촉시점-검출.md) §3.1).

---

## 4. 연구 발전 방향 논의

- app × 질량·템포 상호작용이 논문 스토리.
- 시점 Bland–Altman으로 마커 vs RiCTO를 GT에 붙여 한계 주장과 연결.
- **불완전 균형**: 마커 미배정이 남아도 Mixed Model available-case + 셀별 n으로 해석 가능 (공란을 0으로 채우지 말 것).

---

## 5. 시도하다 만 것 / 반복 조정

| 시도 | 결과 |
|------|------|
| BA 범례 1행·과도한 여백 | condition 2×2 + bias/LoA 컴팩트로 수렴 |
| LoA 약어 | 풀네임 요구 |
| RMSE 패널 AB만 | BC·CA 포함 |

---

## 6. 참조

- `Analysis/Asymmetric/_stats/reports/SUBALL_stats_report.md`
- `Codes/e_statistics/implementation/LMM_DESIGN.md`
- `Codes/e_statistics/README.md`
