import os
import pandas as pd
import numpy as np
from scipy.optimize import minimize
# Algorithms 폴더에서 핵심 엔진 불러오기
from Algorithms.rmo_core import rmo_objective, weight_status_curve

# [설정] 데이터 경로 및 저장 경로
base_path = r"C:\Users\612ch\Dropbox\..." # 실제 데이터 경로로 수정
save_dir = "./results"
if not os.path.exists(save_dir): os.makedirs(save_dir)

def read_sto(filename):
    with open(filename, 'r') as f: lines = f.readlines()
    header_end = next(i for i, line in enumerate(lines) if 'endheader' in line)
    col_names = lines[header_end + 1].split()
    data = [line.split() for line in lines[header_end + 2:]]
    return pd.DataFrame(data, columns=col_names).apply(pd.to_numeric, errors='coerce')

summary_list = []

for i in range(1, 11):
    file_name = f"SUB1_15_10_1_12sec_{i}_APP2_OneCycle_StaticOptimization_force.sto"
    full_path = os.path.join(base_path, file_name)
    if not os.path.exists(full_path): continue
    
    # 1. 데이터 전처리
    df = read_sto(full_path)
    df['time'] = df['time'] - df['time'].iloc[0] # 시간 영점 조절
    df = df[df['time'] <= 6.0].reset_index(drop=True)
    
    time = df['time'].values
    target_col = next((c for c in df.columns if 'pelvis' in c.lower() and 'y' in c.lower()), None)
    residual_raw = df[target_col].values
    
    # 2. [핵심] Baseline 추출 (동작 전 0.5초 구간 평균)
    baseline_val = np.mean(residual_raw[time < 0.5]) if any(time < 0.5) else residual_raw[0]

    # 3. RMO 최적화 실행
    init_guess = [2.2, 0.4, 4.0, 0.4] # 초기 추정치 [t1, d1, t2, d2]
    res = minimize(rmo_objective, init_guess, args=(time, residual_raw, baseline_val), method='Nelder-Mead')
    
    if res.success:
        opt_params = res.x
        summary_list.append({
            'Trial': i,
            't1_start': opt_params[0], 'd1_duration': opt_params[1],
            't2_start': opt_params[2], 'd2_duration': opt_params[3],
            'Baseline_N': baseline_val,
            'Final_Cost': res.fun
        })
        print(f"✅ Trial {i} 최적화 완료")

# 4. 결과 저장
pd.DataFrame(summary_list).to_csv(os.path.join(save_dir, "RMO_Batch_Results.csv"), index=False)