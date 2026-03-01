import numpy as np
from scipy.signal import savgol_filter

def calculate_kinematic_force(time, velocity, mass=75.1, g=9.81):
    """속도 미분 기반 가속도 산출 및 외부 하중(EHF) 계산"""
    dt = time[1] - time[0]
    acc_raw = np.gradient(velocity, dt) # 속도 미분
    acc_smooth = savgol_filter(acc_raw, 11, 3) # 노이즈 제거
    
    # 정지 구간(1초 미만) 기반 Bias 제거
    bias = np.mean(acc_smooth[time < 1.0]) if any(time < 1.0) else 0
    acc_clean = acc_smooth - bias
    
    return -mass * (g + acc_clean) # F = ma