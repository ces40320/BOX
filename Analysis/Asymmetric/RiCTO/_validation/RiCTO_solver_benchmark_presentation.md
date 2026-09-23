# RiCTO 솔버 비교 · 발표용 정리 (검증 재실행본)

- **작성일**: 2026-09-15 · **개정**: 2026-09-16 (`_synthetic` / `solver_compare_synthetic.csv` Analysis 보관 **폐기**)
- **핵심**: 본 문서는 **실데이터** (`solver_compare_all.csv`)를 1차 근거로 쓴다.
- **재실행 명령**:
  ```bash
  cd Codes/c_Run_Tools/optimization
  python validate_ricto.py --solvers-real --protocols Asymmetric --fy-thresh 5
  python validate_ricto.py --solvers --box-mass 7   # 콘솔 유닛 테스트만 (파일 미작성)
  ```

---

## 0. 파일 성격 정리 (중요)


| 파일                                     | 내용                                                 | 피험자?         | 발표에서                    |
| -------------------------------------- | -------------------------------------------------- | ------------ | ----------------------- |
| *(폐기)* `solver_compare_synthetic.csv` | 가짜 residual 유닛 테스트 — **Analysis에 저장하지 않음** (콘솔만) | ❌            | 인용하지 않음                 |
| `solver_compare_all.csv`               | Asymmetric residual × 4 솔버, MeasuredEHF 5 N GT     | ✅ 8명·980 seg | **메인 벤치마크**             |
| `solver_compare_summary_by_solver.csv` | 솔버별 집계                                             | ✅            | 요약 표                    |
| `all_summary_fy5.csv`                  | 기본 솔버(LS)만으로 돌린 EHF/타이밍 검증                         | ✅            | 파이프라인 적용 결과             |


`_synthetic/` 폴더·synthetic CSV는 2026-09-16 기준 **삭제·비생성**. 발표 표는 실데이터만.

이번 재실행 (`--solvers-real`):

- jobs 시도 1073 → **GT 있는 성공 980 seg** (fail 61 = residual 부재 등, skip 32 = GT 접촉창 없음)
- 행 수 **3920** = 980 × 4 solvers
- 피험자 **SUB1–SUB8** (session: KTY, KCH, SHY, KMJ, JSY, KJA, PJH, PJM)

---


## 1. 30초 요약 (발표 오프닝)

RiCTO는 pelvis residual로 grip–deposit 파라미터 `(t1,d1,t2,d2)`를 찾는다.  
**실데이터 8명·980 세그먼트**에서 네 솔버를 동일 조건으로 비교한 결과:

- **접촉 시각 정확도**는 솔버 간 큰 차이가 없다 (onset median |err| ≈ 26–27 ms).
- **Nonlinear Least Squares**만 함수 평가·시간이 뚜렷히 적다 (평균 nfev ≈ 26, 타 솔버 318–1651).
- Deposit offset MAE도 Least Squares가 가장 좋다 (112 ms).
- 따라서 **정확도는 동급, 비용만 다른** 상황에서 Least Squares를 기본으로 채택한다.

---



## 2. 약어 → 정식 명칭


| CSV `solver`    | 정식 명칭                                                          | 한 줄                        |
| --------------- | -------------------------------------------------------------- | -------------------------- |
| `least_squares` | **Nonlinear Least Squares** (Trust Region Reflective, soft-L1) | 잔차 벡터 최소화, bounds 네이티브     |
| `nm`            | **Nelder–Mead**                                                | SSE 스칼라 + simplex; 경계는 페널티 |
| `de`            | **Differential Evolution**                                     | 전역 개체군 탐색                  |
| `grid_local`    | **Grid Search + Local Nelder–Mead**                            | `(t1,t2)` 격자 후 지역 polish   |


---



## 3. 무엇을 / 어떻게 최적화하는가



### 물리

- 비접촉: residual ≈ `B = m_box·|g|` (HeavyHand 상시 질량)
- 접촉: residual 하락 → 가중치 `w(t; t1,d1,t2,d2)`로 모델링  
`r(t) ≈ B(1 − w(t))`
- MeasuredEHF 5 N 창 = **검증 GT** (onset / offset)



### Nonlinear Least Squares가 “최적”을 찾는 방식

1. 샘플별 잔차 `e(t) = r(t) − B(1 − w(t;θ))` 구성
2. soft-L1 손실로 벡터 `e` 최소화
3. Trust Region Reflective가 **파라미터 경계 안에서** 스텝
4. `ftol` 등 수렴 시 소수 회 평가로 종료

→ RiCTO 목적(시계열 피팅 + 물리 bounds)과 형식이 맞다.

---



## 4. 실데이터 솔버 벤치마크 (메인 표)

**조건**: Asymmetric · MeasuredEHF `|Fy_L|+|Fy_R|≥5 N` GT · 동일 residual  
**원본**: `solver_compare_summary_by_solver.csv` (2026-09-15 재실행)


| 솔버 (정식명)                    | N seg | Success | MAE onset (ms) | MAE offset (ms) | Median |onset| (ms) | Median |offset| (ms) | Mean nfev | Mean time (ms) | nfev vs LS | time vs LS |
| --------------------------- | ----- | ------- | -------------- | --------------- | ------------------- | -------------------- | --------- | -------------- | ---------- | ---------- |
| **Nonlinear Least Squares** | 980   | 100%    | 48.0           | **111.8**       | 26.7                | **62.8**             | **25.8**  | **7.1**        | **1×**     | **1×**     |
| Nelder–Mead                 | 980   | 100%    | 44.7           | 121.8           | 26.5                | 66.2                 | 341       | 10.6           | 13×        | 1.5×       |
| Grid Search + Local NM      | 980   | 100%    | **39.5**       | 119.0           | 26.5                | 66.1                 | 318       | 12.9           | 12×        | 1.8×       |
| Differential Evolution      | 980   | 100%    | 40.3           | 128.1           | 26.3                | 71.1                 | 1651      | 70.4           | **64×**    | **10×**    |




### 세그먼트별 “승자” 비율 (참고)


| 기준              | Least Squares | Nelder–Mead | Grid+Local | DE        |
| --------------- | ------------- | ----------- | ---------- | --------- |
| 최저 cost         | 0%            | 5.0%        | 6.3%       | **88.7%** |
| 최저 |onset err|  | **35.4%**     | 23.6%       | 23.2%      | 17.9%     |
| 최저 |offset err| | **55.4%**     | 17.1%       | 17.2%      | 10.2%     |


**발표 멘트**

- DE는 cost를 자주 이기지만, **GT 접촉 시각**(실제로 중요한 지표)에서는 Least Squares가 offset에서 뚜렷하고 onset에서도 가장 자주 이긴다.
- Median onset 오차는 네 솔버가 사실상 같다 → **효율이 차별점**.

---



## 5. 피험자 × 솔버 벤치마크 (onset MAE, ms)

원본: `solver_compare_all.csv`


| Subject         | N       | Least Squares | Nelder–Mead | Grid+Local | DE       |
| --------------- | ------- | ------------- | ----------- | ---------- | -------- |
| SUB1            | 124     | 37.9          | 27.0        | 26.9       | 38.6     |
| SUB2            | 122     | 104.2         | 101.3       | 59.3       | 55.2     |
| SUB3            | 129     | 65.2          | 64.2        | 64.7       | 64.2     |
| SUB4            | 98      | 33.2          | 31.4        | 32.2       | 31.7     |
| SUB5            | 122     | 42.7          | 43.1        | 42.8       | 42.4     |
| SUB6            | 126     | 46.7          | 47.1        | 46.5       | 46.8     |
| SUB7            | 132     | 19.6          | 15.6        | 15.9       | 15.5     |
| SUB8            | 127     | 33.5          | 27.6        | 27.5       | 27.5     |
| **Overall MAE** | **980** | **48.0**      | **44.7**    | **39.5**   | **40.3** |




### Offset MAE (ms)


| Subject     | Least Squares | Nelder–Mead | Grid+Local | DE    |
| ----------- | ------------- | ----------- | ---------- | ----- |
| SUB1        | **95.6**      | 122.0       | 121.1      | 132.1 |
| SUB2        | 173.0         | 180.3       | 155.7      | 157.4 |
| SUB3        | **125.6**     | 130.9       | 126.0      | 144.5 |
| SUB4        | **122.7**     | 130.1       | 132.0      | 131.4 |
| SUB5        | **110.7**     | 115.8       | 117.1      | 121.1 |
| SUB6        | **107.2**     | 132.6       | 129.8      | 139.4 |
| SUB7        | **96.8**      | 98.4        | 103.3      | 118.0 |
| SUB8        | **67.4**      | 69.4        | 72.0       | 83.0  |
| **Overall** | **111.8**     | 121.8       | 119.0      | 128.1 |


> SUB2 onset은 전 솔버에서 크게 흔들림(조건 이상치). 전체 이야기할 때는 **median**과 함께 말할 것.



### 피험자별 mean nfev (효율)


| Subject      | Least Squares | Nelder–Mead | Grid+Local | DE             |
| ------------ | ------------- | ----------- | ---------- | -------------- |
| SUB1–8 공통 패턴 | **~22–32**    | ~325–356    | ~286–345   | **~1576–1781** |


---



## 6. 왜 Least Squares를 기본으로 잡았는가

1. **문제 구조**: residual 시계열 피팅 → 잔차 벡터 Least Squares가 자연스럽다.
2. **제약**: grip/deposit bounds → TRF가 네이티브 지원.
3. **실데이터 실증 (본 벤치마크)**:
  - 시각 오차 동급 (특히 median)  
  - **nfev 1× vs 12–64×**, 시간 1× vs 1.5–10×  
  - offset MAE·세그먼트 승률에서 LS 우위
4. **운영**: 세그먼트 수백~수천 배치에서 평가 횟수가 파이프라인 비용.
5. **여지**: DE/Grid는 플러그인으로 유지 (전역·조대 탐색 옵션).



### Cost만 보면 DE가 유리해 보이는데?

- Cost 최저: DE 88.7%  
- 그러나 GT offset 최저: LS 55.4%, DE 10.2%  
- → **잔차 SSE ≠ 접촉 시각 정확도**. 발표에서는 GT 타이밍을 1차 지표로 둔다.

---



## 7. 합성 residual (콘솔 유닛 테스트만 · 발표 비인용)

**성격**: 피험자 데이터 아님. 알려진 truth로 솔버 동작만 확인.  
**파일**: Analysis에 **저장하지 않음** (`validate_ricto.py --solvers` → 콘솔 출력만, 2026-09-16).

참고 수치(과거 콘솔/표와 동일 패턴):


| 솔버                      | ‖Δt1‖ (ms) | ‖Δt2‖ (ms) | nfev   | time (ms) |
| ----------------------- | ---------- | ---------- | ------ | --------- |
| Nonlinear Least Squares | 4.5        | 0.8        | **14** | **4.0**   |
| Nelder–Mead             | 4.6        | 1.2        | 290    | 9.5       |
| Grid+Local              | 4.6        | 1.2        | 233    | 10.8      |
| Differential Evolution  | 4.6        | 1.2        | 2815   | 122.7     |


→ “오차 동급 · LS 최소 비용”은 실데이터와 같은 방향. **슬라이드 메인 표에는 넣지 않음.**

---


## 8. 슬라이드 초안 불릿



### A. Title

- RiCTO solver selection: real-data head-to-head
- 8 subjects · 980 segments · 4 solvers



### B. What was wrong with the old CSV?

- Old `solver_compare_synthetic` = **one fake residual**, not a subject benchmark (file retired)
- Use `--solvers-real` → `solver_compare_all.csv` only



### C. Candidates (formal names)

- Nonlinear Least Squares (TRF, soft-L1)
- Nelder–Mead / Differential Evolution / Grid+Local NM



### D. Real-data summary table (§4)

- Accuracy: comparable (onset median ~27 ms)
- Cost: LS **26 nfev / 7 ms** vs DE **1651 / 70 ms**



### E. Why Least Squares

- Fits residual-vector problem + bounds
- Best/tied timing with **far fewer evaluations**
- Wins most segments on GT offset error



### F. Subject table (§5)

- Per-subject onset/offset MAE
- Note SUB2 outlier; use medians



### G. Take-home

- Default = **Nonlinear Least Squares**
- DE optional for global search, not default

---



## 9. 예상 Q&A

**Q. synthetic 파일이 피험자 결과인가?**  
A. 아니다. 예전에 있던 가짜 residual CSV는 폐기했다. 피험자 비교는 `solver_compare_all.csv` / `solver_compare_summary_by_solver.csv`만.

**Q. DE cost가 더 낮은데 왜 LS?**  
A. Cost ≠ 접촉 시각. GT 기준 offset·효율에서 LS가 유리.

**Q. 980이면 SUBALL인가?**  
A. Asymmetric에서 MeasuredEHF GT가 있는 전 세그먼트(SUB1–8). residual/GT 없는 시도는 fail/skip으로 제외.

**Q. 재현은?**  
A. `python validate_ricto.py --solvers-real --protocols Asymmetric --fy-thresh 5`

---



## 10. PPT용 체크리스트

- [x] 메인 표는 **실데이터** summary (§4); synthetic CSV는 Analysis에 두지 않음
- [ ] 솔버 정식명 사용 (§2)
- [ ] 지표 우선순위: GT timing → nfev/time → (참고) cost
- [ ] SUB2 outlier + median 병기
- [ ] 채택 한 줄: *정확도 동급, 비용 최소, 경계·잔차 형식 적합*