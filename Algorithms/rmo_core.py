import numpy as np

def smoothstep_ramp(t, t_start, duration):
    """
    Smoothstep Function (3t^2 - 2t^3)
    하중이 물리적으로 급격하게 변하지 않도록 S-커브 형태의 전이 구간을 생성합니다.
    관습적으로 Sigmoid-like curve라고도 불리지만, 시작과 끝이 0과 1로 명확히 떨어지는 다항식을 사용합니다.
    """
    if duration < 0.01: 
        return np.where(t >= t_start, 1.0, 0.0)
    
    # 시간 정규화 및 클리핑 (0 ~ 1 범위로 제한)
    tau = (t - t_start) / duration
    tau = np.clip(tau, 0, 1)
    
    # Hermite interpolation (3차 다항식)을 이용한 부드러운 하중 전이 계산
    return 3 * tau**2 - 2 * tau**3

def weight_status_curve(t, params):
    """
    Weight-Status Schedule Function (Lift - Lower)
    Params: [t1(들기 시작), d1(들기 소요시간), t2(놓기 시작), d2(놓기 소요시간)]
    전체 사이클 동안 물체가 손에 들려있는 하중의 비중(0~1)을 계산합니다.
    """
    t1, d1, t2, d2 = params
    
    # Lifting phase와 Lowering phase를 각각 계산
    ramp_up = smoothstep_ramp(t, t1, d1)     
    ramp_down = smoothstep_ramp(t, t2, d2)   
    
    # 현재 하중 상태 결정 (0: 바닥에 있음, 1: 완전히 들고 있음)
    return np.clip(ramp_up - ramp_down, 0, 1)

def rmo_objective(params, time_arr, residual_raw, baseline):
    """
    Residual Minimization Optimization (RMO) 목적 함수
    모델이 예측한 보정값과 실제 골반 잔차(Residual) 사이의 오차 제곱합을 최소화합니다.
    """
    t1, d1, t2, d2 = params
    
    # 파라미터 제약 조건 (Penalty)
    # 시간의 논리적 순서 및 최소 전이 시간(0.1s) 보장
    if (t1 < 0) or (t2 > 6.0) or (d1 < 0.1) or (d2 < 0.1) or (t1 + d1 >= t2):
        return 1e9 
    
    # 하중 전이 곡선(Weight Schedule) 생성
    w_curve = weight_status_curve(time_arr, params)
    
    # Baseline(시스템 오프셋) 기반 보정 논리 적용
    # 보정량 = 초기 잔차 오차 * (1 - 현재 하중 상태)
    correction = baseline * (1 - w_curve)
    
    # 보정 적용 후 잔차 오차 계산
    residual_adjusted = residual_raw - correction
    
    # 최적화 엔진(Nelder-Mead 등)이 사용할 오차 제곱 합 반환
    return np.sum(residual_adjusted**2)