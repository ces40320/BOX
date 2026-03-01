import numpy as np
import pandas as pd
import os
from Algorithms.rmo_core import smoothstep_ramp # 핵심 수식만 호출

# [참고] 이 코드는 그래프를 그리는 대신 데이터(CSV)로 저장하도록 정제했습니다.
def run_landscape_scan(time, residual, baseline, save_path):
    print("🚀 [Cost Landscape] 전수 조사 채점 시작...")
    
    # 1.5초부터 3.5초까지 0.02초 간격으로 스캔
    test_times = np.arange(1.5, 3.5, 0.02)
    scores = []

    for t_start in test_times:
        # 고정된 duration(0.45s)으로 가정했을 때의 RMSE 계산
        fixed_dur = 0.45
        w_curve = smoothstep_ramp(time, t_start, fixed_dur)
        correction = baseline * (1 - w_curve)
        rmse = np.sqrt(np.mean((residual - correction)**2))
        scores.append(rmse)

    # 결과를 데이터프레임으로 저장
    df_landscape = pd.DataFrame({
        'Tested_Time': test_times,
        'RMSE_Score': scores
    })
    df_landscape.to_csv(save_path, index=False)
    print(f"✅ 검증 데이터 저장 완료: {save_path}")