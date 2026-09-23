# e_statistics

Linear Mixed Model (LMM) 및 추론 통계 전용 디렉터리.  
시계열·RMSE 산출(`d_Results_Analysis` → `Analysis/Asymmetric`)과 **분리**한다.

## Layout

```text
Codes/e_statistics/
  README.md
  implementation/           ← 코드 구현용 분석·설계 MD
    LMM_ANALYSIS_PLAN.md
    LMM_DESIGN.md
    RICTO_RESULTS_REPORT_PLAN.md   ← Results figures / sheets / stats I/O
    STATS_REPORT_TEMPLATE.md       ← fill-in statistics report MD
  research/                 ← 사전 연구·문헌 노트
    README.md
    LMM_LITERATURE_NOTES.md
  stats_lmm.py              ← long table + OLS + SUBALL MixedLM
  stats_timing_error.py     ← Grip/Deposit abs error long table
  stats_bland_altman.py     ← Bland–Altman timing
  stats_rm_anova.py         ← L5S1 peak rmANOVA
  render_stats_report.py    ← fill `_stats/reports/*.md`
  run_statistics.py         ← CLI
```

Manuscript figures: `d_Results_Analysis/manuscript_figures.py` → `_figures/RiCTO_manuscript/`.

## 역할 분담

| 폴더 | 내용 | 넣지 말 것 |
|------|------|------------|
| `implementation/` | 모델 식, 고정/랜덤효과, 입력 long-table 스키마, CLI, SUB7 고정효과 경로(A+B) | PDF·논문 원문 덤프 |
| `research/` | 문헌 요약, 인용, 유사 연구 설계, 용어 정리 | 실행 스크립트·CSV 경로 하드코딩 |

## 데이터 흐름

```text
Analysis/Asymmetric/{EHF,L5S1,...}/_metrics/*.csv
        │
        ▼
  e_statistics/ (long table 빌드 → LMM / 고정효과 / rmANOVA / Bland–Altman)
        │
        ▼
  Analysis/Asymmetric/_stats/   ← long/, models/, reports/ (현행 경로)
```

Results 보고(피규어·시트·통계 MD) 전체 맵:  
[`implementation/RICTO_RESULTS_REPORT_PLAN.md`](implementation/RICTO_RESULTS_REPORT_PLAN.md).  
보고서 채움 골격: [`implementation/STATS_REPORT_TEMPLATE.md`](implementation/STATS_REPORT_TEMPLATE.md).  
**폴더/약어 설명(사람이 읽는 가이드):** `Analysis/Asymmetric/_stats/README.md`.  
**jamovi형 보고서:** `Analysis/Asymmetric/_stats/reports/SUB*_stats_report.md`, `SUBALL_stats_report.md`  
(`python render_stats_report.py --all-reports`).

## 범위 (기존 합의)

- **A**: 문헌·이론 + multi-subject LMM 코드 골격 (SUBALL 피험자)
- **B**: SUB7만으로 가능한 고정효과 / 반복측정 분석
- **C**: 전 피험자 대기 시나리오는 개요만 (`implementation/LMM_ANALYSIS_PLAN.md`)
- **Results report**: figures / RiCTO sheets / stats report MD — `RICTO_RESULTS_REPORT_PLAN.md`
