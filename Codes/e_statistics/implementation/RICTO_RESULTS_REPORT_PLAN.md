# RiCTO Results 보고 계획

Status: **implemented** (see `run_statistics.py`, `manuscript_figures.py`).  
시계열·RMSE 스키마는 [`STRUCTURE.md`](../../d_Results_Analysis/STRUCTURE.md) 동결.  
LMM 골격은 [`LMM_ANALYSIS_PLAN.md`](LMM_ANALYSIS_PLAN.md) / [`LMM_DESIGN.md`](LMM_DESIGN.md).  
최적화 모듈은 [`RICTO_PLAN.md`](../../c_Run_Tools/optimization/RICTO_PLAN.md).  
채워 넣는 통계 보고서 골격: [`STATS_REPORT_TEMPLATE.md`](STATS_REPORT_TEMPLATE.md).

Primary protocol: **Asymmetric** (`MeasuredEHF`, `HeavyHand`, `preRiCTO`, `postRiCTO`).  
Symmetric `SUB1(AddBiomech)` jamovi / Prism / ANOVA txt는 **보고 포맷 참고만** (경로·앱 이름을 그대로 이식하지 않음).

---

## 1. Results 서사 (PDF → 도메인 용어)

### 1.1 RiCTO optimization

| 항목 | 합의 |
|------|------|
| GT 접촉창 | MeasuredEHF **수직축만**: 양손 `\|Fy_L\| + \|Fy_R\| ≥ 5 N` (`hand_force3_vy`, `hand_force4_vy`). **resultant(‖F‖) 아님.** |
| 근거 | `analysis_utils.contact_windows_fy` / `measured_contact_window`; STRUCTURE crop; validation `*_fy5.csv` |
| HeavyHand | 양손 각각 박스 질량의 절반 + BK 가속도 → 뉴턴 2법칙 |
| 타이밍 (마커) | 박스 마커 trajectory peak pair (세그먼트 AB·BC·CA; AB/CA 규칙과 BC 규칙을 혼용하지 않음) |
| preRiCTO | 전이 타이밍만 (무-스무딩 / rect weight) |
| postRiCTO | 타이밍 + duration 스무딩 |

혼동 주의: `config_methods` 일부 cycle/onset 주석의 ‖F‖는 **다른 경로**. Asymmetric Results crop·5 N GT·본 보고는 전부 **Fy 합**.

### 1.2 EHF comparison

- Resultant mean±std (접촉창 → 101 pt) + 하단 Q1–Q4 RMSE 막대.
- AP / ML / Vertical도 동일 레이아웃.
- 추론: LMM on RMSE (아래 §5); tempo(bpm), `mass_norm = box_mass / body_mass`.

### 1.3 L5S1 JRF & moment

- JRF: Resultant(+축별). JRM: 축별만.
- 세그먼트별 **initial peak (0–50%)** / **final peak (50–100%)** — magnitude·timing.
- one-way rmANOVA (within = app). 플롯: JScience형 (시계열 + 피크 막대 + 피크 시각 점).

### 1.4 앱·색 강조

공식 오버레이는 네 앱 전부 [`APP_PLOT_STYLE`](../../d_Results_Analysis/analysis_utils.py).  
논문 메인 패널도 MeasuredEHF / HeavyHand / **preRiCTO** / postRiCTO를 주 비교로 둔다 (손글씨 3색 스케치는 레거시 APP1/2/4 참고일 뿐).

---

## 2. 데이터 입출력

```text
Analysis/Asymmetric/{EHF,L5S1}/…/*.csv          → mean±std / peak plots
…/{EHF,L5S1}/{app}/_metrics/RMSE_*.csv          → RMSE long / LMM / bars
…/EHF/MeasuredEHF/_metrics/RMSE_all_apps_*.csv  → preferred EHF stack
RiCTO/Summary/SUB{n}_RiCTO_report.xlsx          → timing sheets (SSOT)
RiCTO/_validation/*_fy5.csv                     → GT 5 N onset/offset
RiCTO/TimeSeries/…                              → residual, w, f_est
Codes/SUB_Info.py                               → height, body_mass, sex, age
OpenSim …/pipeline_progress.xlsx                → SUBALL roster
```

기존 통계 산출 (현행): `Analysis/Asymmetric/_stats/lmm_long_template_EHF_RMSE_SUB*.csv`, `SUB*_OLS_*.txt`.

**참고 전용 (Dropbox Symmetric)**

- `e:\Dropbox\SEL\BOX\Analysis\Symmetric\Statistics\SUB1(AddBiomech)\`
  - `L5S1_*_statistics.omv` — RM ANOVA + Greenhouse–Geisser + Bonferroni
  - `L5S1 One-way rm ANOVA Reports (F scores, p values).txt`
  - `Figures/*Prism*.pptx` — 패널 배치 레퍼런스

---

## 3. 플롯 스타일 (레포 규칙)

소스: `analysis_utils.mean_std_plot` / `APP_PLOT_STYLE`.  
원고용 vault 저장 시 **dpi 300** (파이프라인 QC 기본 150과 분리 가능).

| 항목 | 값 |
|------|-----|
| Font | Arial; label/title **14**, legend **11** |
| figsize | mean±std **(10, 7)**; RiCTO QC overlay **(12.5, 6.5)** 허용 |
| dpi (manuscript) | **300** |
| linewidth | **2.0**; band alpha **0.15** |
| spines | top/right off; ticks `direction=in` |
| MeasuredEHF | black, `--` |
| HeavyHand | red, `-` |
| preRiCTO | darkorange, `-` |
| postRiCTO | blue, `-` |

논문 캡션·축 라벨: FreeBox가 등장하면 **LoadShare** (코드 경로·파일명은 FreeBox).

`ricto_plot.py` 디버그 스타일(preRiCTO=red)은 QC 전용. **공식 Results 플롯은 APP_PLOT_STYLE로 통일.**

---

## 4. Figure 세트·정장 관리

### 4.1 Results 배치 순서

| ID | 내용 | 주 데이터 |
|----|------|-----------|
| Fig-RiCTO-1 | Plot ① `w*(t)` 3단: (A) pelvis residual (B) EHF (C) load-transfer % | `RiCTO/TimeSeries` + ExtLoad |
| Fig-RiCTO-2 | Plot ② Grip·Deposit 절대오차 (Box-marker vs RiCTO vs GT) | Summary `timing_error_summary` + 마커 이벤트; 없으면 fy5 onset/offset |
| Fig-EHF-1 | Resultant mean±std + Q1–Q4 RMSE bars | `EHF/*/Resultant`, `_metrics` |
| Fig-EHF-2..4 | AP / ML / Vertical 동일 | `EHF/*/{AP,ML,Vertical}` |
| Fig-L5S1-1 | Force_Resultant mean±std + RMSE | `L5S1/*/Force_Resultant` |
| Fig-L5S1-2 | Peak analysis (mag bars + peak time) + rmANOVA 표시 | L5S1 timeseries → peak table |

Tempo별 편차가 크면 Fig-RiCTO-2 / EHF를 `kg_bpm` facet 또는 SUBALL per-condition 폴더로 분리.

### 4.2 디렉터리

```text
Analysis/Asymmetric/
  _figures/{EHF|L5S1|Residual}/     # 파이프라인 자동 (재생성 가능)
  _figures/RiCTO_manuscript/        # 논문·보고 확정본 (수동/플래그 복사)
    README.md                       # figure id → script → data path
    Fig-RiCTO-1.png
    …
  RiCTO/Summary/                    # xlsx SSOT (upsert)
  _stats/
    long/                           # long tables
    models/                         # OLS / rmANOVA / LMM / Bland–Altman
    reports/                        # filled STATS_REPORT_TEMPLATE instances
```

규칙:

- `_figures/{domain}/` = 재생성 가능.
- `RiCTO_manuscript/` = 버전 고정; 복사 시에만 갱신.
- 시트 SSOT = xlsx; MD는 요약·해석만.

---

## 5. 통계

| 분석 | 대상 | 구현 (예정) | 저장 |
|------|------|-------------|------|
| RMSE / Q1–Q4 | EHF·L5S1 vs MeasuredEHF | 기존 `d_Results_Analysis` | `{app}/_metrics/`, `_stats/long/` |
| 절대 오차 (Grip/Deposit) | 마커·RiCTO vs GT 5 N 창 | `stats_timing_error.py` | `_stats/long/timing_abserr_*.csv` |
| Bland–Altman | 타이밍 오차 또는 피크 (방법×GT) | `stats_bland_altman.py` | `_stats/models/` + PNG |
| one-way rmANOVA | L5S1 initial/final peak mag·time; within=app | `pingouin.rm_anova` (+ GG) | `_stats/models/rmANOVA_*.csv` + report MD |
| LMM | RMSE (타이밍 오차 확장 가능) | `statsmodels` MixedLM | `_stats/models/LMM_*.csv` |

### 5.1 LMM

- **다피험자**: `pipeline_progress` 기준 **SUBALL** 피험자만.  
  `value ~ C(app) * C(tempo_bpm) + scale(mass_norm) + (1|sub)`  
  `mass_norm = mass_kg / body_mass_kg`
- **단피험자 (Path B)**: 기존 OLS  
  `RMSE_full ~ C(app)*C(tempo_bpm)*C(mass_kg)+C(hand)`  
  피크는 rmANOVA 우선.

### 5.2 rmANOVA 보고 문장 (Symmetric txt 미러)

```text
{Outcome}  F(df1, df2) = …, p = …   [significant|non-significant]
Post-hoc (Bonferroni): AppA vs AppB …
Sphericity: Mauchly W, GG ε …
```

### 5.3 의존성

`requirement.txt`에 `statsmodels`, `pingouin` 명시 (현재 MixedLM은 optional import).

---

## 6. 코드 구현 스케치 (후속)

이번 산출물은 **MD 계획·템플릿**만. 실행 코드는 별도 작업.

| 위치 | 역할 |
|------|------|
| `d_Results_Analysis/` | 원고용 복합 플롯 (EHF RMSE 패널, L5S1 peak), manuscript export 헬퍼 |
| `c_Run_Tools/optimization/ricto_plot.py` | Fig-RiCTO-1 triplet; 공식 색은 APP_PLOT_STYLE |
| `d_Results_Analysis/abc_marker_events.py` | Fig-RiCTO-2 마커 Grip/Deposit (배선 시) |
| `e_statistics/stats_timing_error.py` | 절대오차 long table |
| `e_statistics/stats_bland_altman.py` | Bland–Altman CSV+PNG |
| `e_statistics/stats_rm_anova.py` | peak rmANOVA |
| `e_statistics/stats_lmm.py` | MixedLM 실fit (SUBALL) |
| `e_statistics/run_statistics.py` | CLI 모드 통합 + report MD 렌더 |

```bash
python Codes/d_Results_Analysis/run_all_analysis.py --namecode 260526_PJH --plot
python Codes/e_statistics/run_statistics.py --namecode 260526_PJH --mode all
# LMM: SUBALL roster only
python Codes/e_statistics/run_statistics.py --mode lmm --suball
```

### 6.1 Fig-RiCTO-2 폴백

박스 마커 peak pair가 Asymmetric에 완전히 배선되지 않은 동안:

1. 1차: RiCTO vs MeasuredEHF 5 N 창 onset/offset 절대오차.
2. 마커 비교는 `abc_marker_events` / export 경로 확정 후 추가.

---

## 7. 통계 보고서 인스턴스

템플릿: [`STATS_REPORT_TEMPLATE.md`](STATS_REPORT_TEMPLATE.md).  
채움 결과: `Analysis/Asymmetric/_stats/reports/SUB{n}_stats_report.md`  
및 `SUBALL_stats_report.md` (LMM·집단 기술통계).

섹션 순서: Meta → Methods → Descriptives → Agreement → Inferential → Figures → QC.

---

## 8. 이해 한계

- PDF 손글씨 스케치의 축 단위·facet는 STRUCTURE·본 MD로 보강.
- Dropbox Prism은 pptx 중심; 픽셀 레퍼런스는 Official pptx.
- 현재 `_stats/` vs README의 `Stats/` 표기: **실제 경로는 `_stats/`** (본 계획·코드 `stats_lmm._stats_dir`와 일치).
