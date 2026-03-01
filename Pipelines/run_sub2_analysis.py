import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt # 결과 확인용 (선택 사항)
# 작성한 알고리즘 모듈 임포트
from Algorithms.kinematics_engine import calculate_kinematic_force
from Algorithms.rmo_core import weight_status_curve # RMO 결과 적용 시 필요

# [1] 설정: 데이터 경로 (사용자 환경에 맞게 수정)
base_path = r"./data/SUB2" 
vel_file = "SUB2_vel_global.sto" # 속도 데이터 파일
full_path = os.path.join(base_path, vel_file)

def read_sto(filename):
    with open(filename, 'r') as f: lines = f.readlines()
    header_end = next(i for i, line in enumerate(lines) if 'endheader' in line)
    col_names = lines[header_end + 1].split()
    data = [line.split() for line in lines[header_end + 2:]]
    return pd.DataFrame(data, columns=col_names).apply(pd.to_numeric, errors='coerce')

def main():
    if not os.path.exists(full_path):
        print(f"❌ 파일을 찾을 수 없습니다: {full_path}")
        return

    # [2] 데이터 로드
    df_vel = read_sto(full_path)
    time = df_vel['time'].values
    # 오른쪽 손(hand_r)의 수직 방향(Y) 속도 데이터 추출
    velocity_y = df_vel['hand_r_Y'].values 

    # [3] 알고리즘 엔진 호출: 속도 미분 및 물리 하중(EHF) 계산
    # (내부적으로 미분 -> 스무딩 -> Bias 제거 수행)
    ehf_kinematic = calculate_kinematic_force(time, velocity_y, mass=7.51, g=9.81)

    # [4] 결과 정리 및 저장
    results = pd.DataFrame({
        'time': time,
        'velocity_y': velocity_y,
        'calculated_ehf_y': ehf_kinematic
    })
    
    output_path = "./results/SUB2_EHF_Analysis.csv"
    results.to_csv(output_path, index=False)
    print(f"✅ SUB2 분석 완료! 결과 저장됨: {output_path}")

    # (옵션) 결과 확인용 간단한 시각화
    # plt.plot(time, ehf_kinematic, label='Calculated EHF (SUB2)')
    # plt.legend(); plt.show()

if __name__ == "__main__":
    main()