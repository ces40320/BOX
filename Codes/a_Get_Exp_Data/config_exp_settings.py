"""
전처리 로직에 필요한 물리적 상수와 설정값.

경로는 포함하지 않음 → PATH_RULE.py
프로토콜별 세그먼트 파라미터 → config_methods.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── C3D 좌표계 회전 (참조용) ─────────────────────────────────
# QTM Z-up → OpenSim Y-up 필요 시.  
# Motive export setting은 이미 Y-up이므로 실행 파일에서 rotations=None 으로 호출 해야 함.
DYNAMIC_C3D_ROTATIONS = [("x", -90.0)]

# ── 박스 마커 이름 (접두사 없는 marker name) ───────────────────
BOX_LEFT_MARKER = "LTA_BOX"
BOX_RIGHT_MARKER = "RTA_BOX"

# ── Butterworth 저역통과 필터 ─────────────────────────────────
MARKER_FILTER_HZ = 10.0
FORCE_FILTER_HZ = 10.0
FILTER_ORDER = 4

# ── 로드셀 부호 (Force) ──────────────────────────────────────
HAND3_FORCE_SIGN = (-1.0, -1.0,  1.0)   # FP3 (왼손) X,Y축 반전
HAND4_FORCE_SIGN = (-1.0, -1.0,  1.0)   # FP4 (오른손)

# ── 로드셀 부호 (Moment) ─────────────────────────────────────
HAND3_MOMENT_SIGN = (-1.0, -1.0,  1.0)  # FP3 X,Y축 반전
HAND4_MOMENT_SIGN = (-1.0, -1.0,  1.0)  # FP4

# ── 로드셀 부호 (COP) ────────────────────────────────────────
HAND3_COP_SIGN = (-1.0,  1.0,  1.0)     # FP3 X축만 반전 (<- Motive 상에서 force를 visualize하려면 이렇게 뒤집어서 설정해야 했음. 그래서 그걸 원상복구하는 것임.)
HAND4_COP_SIGN = (-1.0,  1.0,  1.0)     # FP4

# ── 로드셀 원점 오프셋 (m) ────────────────────────────────────
P3_OFFSET_M = (-0.0573115,  0.152248, -0.1595505)
P4_OFFSET_M = (-0.3834540,  0.152248, -0.1591615)

# ── 박스 중심 → 핸들 벡터 (m, 로컬 좌표계) ───────────────────
D3_CENTER_TO_HANDLE_M = (-0.16001,  0.0158,  0.00041)  # FP3 왼손
D4_CENTER_TO_HANDLE_M = ( 0.16007,  0.0158,  0.00041)  # FP4 오른손

# ── Force threshold ───────────────────────────────────────────
FORCE_THRESHOLD_N = 10.0

# ── RigidBody CSV ─────────────────────────────────────────────
# MATLAB은 dataLines=[9,Inf] (9행부터), Python skiprows=7 → 8행부터.
# 1줄 차이 가능성 있으므로 실제 CSV 헤더 구조 확인 필요.
RIGID_BODY_SKIPROWS = 7

# ── 손가락 마커 이름 (APP3용) ─────────────────────────────────
LEFT_FINGER_MARKER = "LFN2"
RIGHT_FINGER_MARKER = "RFN2"
