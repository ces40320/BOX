# a_Get_Exp_Data TODO

기준 시점: 2026-04-17

## 1) 검증 우선 항목 (전처리 산출물)

- [ ] `marker.trc` / `ExtLoad.mot`를 MATLAB 기준 결과와 수치 비교 (허용오차 정의 포함).
- [ ] 최소 1개 Symmetric, 1개 Asymmetric 조건에 대해 샘플 비교 리포트 기록.
- [x] `RIGID_BODY_SKIPROWS`(현재 7) 값이 실제 CSV 헤더 구조와 일치하는지 확인.

## 2) 분할 로직 (의도적 보류)

- [ ] `findpeaks` 기반 Symmetric 분할 구현 (`segment_symmetric.py`) 및 재현 확인.
  - 보류 사유: 기존 Symmetric 처리 재현 이슈로 현재 우선순위 낮음.
- [ ] `bpm_window` 기반 Asymmetric 자동 분할 구현/검증.
  - 보류 사유: 추가 파일럿 실험 결과(윈도우/임계값 검증) 필요.

## 3) 파이프라인 통합 정리

- [ ] `run_get_exp_data.py`의 `process_condition_bpm_window()` 연결 시점에 TODO 제거.
- [ ] `run_get_exp_data.py`이 너무 비대함. `process_condition_findpeaks()`, `process_condition_manual_window()`, `process_condition_bpm_window()`을 각각의 파이썬 파일로 분할 구현하는 것이 필요. (다소 겹치는 필요 헬퍼함수들이 있을 것으로 파악되면, 클래스로 만들어서 wrapper로 만들어도 괜찮을 듯) -> 그때의 파이썬 이름은 직관적으로 `split_lifting_trial2section_*.py`로 설정 하기.
- [ ] `lifting_io.py`에 리팩토링 진행하면 좋을지 검토, 그리고 docstring, 주석 좀 더 이해하기 쉽게 추가.
- [ ] 분할 미사용 모드(full-length 출력 전용) 실행 경로를 명시적으로 문서화.
- [ ] APP별 미구현 항목(`preRiCTO`, `postRiCTO` 등) 구현 범위 확정 후 반영.
- [x] `a_Main.ipynb`파일 생성하여 `run_get_exp_data.py`를 필요에 따라 편하게 실행하도록 configs 불러와서 셀단위로 실행.

