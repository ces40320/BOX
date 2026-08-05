"""Batch RMO optimization over repeated trials.

Data and output locations are configured through environment variables so that
the script is portable:

    BOX_DATA_DIR    directory holding the static-optimization .sto files
                    (default: ./data)
    BOX_RESULT_DIR  directory for the result table (default: ./results)

    BOX_DATA_DIR=/path/to/sto python Pipelines/run_batch_optimization.py
"""
import os
import pandas as pd
import numpy as np
# Algorithms 폴더에서 핵심 엔진 불러오기
from Algorithms.ricto_core import optimize_transition

# [설정] 데이터 경로 및 저장 경로 (환경변수로 지정, 없으면 기본값)
base_path = os.environ.get("BOX_DATA_DIR", os.path.join(".", "data"))
save_dir = os.environ.get("BOX_RESULT_DIR", os.path.join(".", "results"))
os.makedirs(save_dir, exist_ok=True)
if not os.path.isdir(base_path):
    raise SystemExit(f"data directory not found: {base_path}\n"
                     f"set BOX_DATA_DIR to the folder containing the .sto files")

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
    
    # 1. 데이터 전처리 (시간 영점 조절)
    df = read_sto(full_path)
    df['time'] = df['time'] - df['time'].iloc[0]

    time = df['time'].values
    target_col = next((c for c in df.columns if 'pelvis' in c.lower() and 'y' in c.lower()), None)
    residual_raw = df[target_col].values

    # 2. 전이 파라미터 추정 (baseline 과 초기 추정치는 잔차에서 자동 산출)
    result = optimize_transition(time, residual_raw)

    if result['success']:
        t1, d1, t2, d2 = result['params']
        summary_list.append({
            'Trial': i,
            't1_start': t1, 'd1_duration': d1,
            't2_start': t2, 'd2_duration': d2,
            'Baseline_N': result['baseline'],
            'Final_Cost': result['cost']
        })
        print(f"✅ Trial {i} 최적화 완료")

# 4. 결과 저장
pd.DataFrame(summary_list).to_csv(os.path.join(save_dir, "RMO_Batch_Results.csv"), index=False)