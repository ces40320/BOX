import os
import sys
import matplotlib

# 노트북 실행 위치가 어디든 동작하도록 경로를 정렬
repo_root = os.getcwd()
if not os.path.isdir(os.path.join(repo_root, "Codes")): # if you want to run this notebook from other directory, change the path below
    repo_root = r"C:/Users/ok/Documents/GitHub/BOX"     # (optional)TODO: change to your path

work_dir = os.path.join(repo_root, "Codes", "a_Get_Exp_Data")
os.chdir(work_dir)

if work_dir not in sys.path:
    sys.path.insert(0, work_dir)
codes_dir = os.path.dirname(work_dir)
if codes_dir not in sys.path:
    sys.path.insert(0, codes_dir)

print("cwd:", os.getcwd())
print("work_dir:", work_dir)


import PATH_RULE as _path
from run_get_exp_data import process_subject

print("Available subjects:", _path.DATA_SUB_NAMECODE_li)



# [GUI 매뉴얼 tap 선택]  bpm_window 의 t_tap 을 matplotlib 창에서 직접 클릭
#
# 주의: Jupyter 의 기본 backend (%matplotlib inline) 는 GUI 창을 띄울 수 없으므로
#       아래 매직으로 별도 창을 띄우는 backend 로 전환해야 한다.
#       - 환경에 따라 둘 중 하나 사용: `%matplotlib qt`  또는  `%matplotlib tk`
#       - 한 번 전환하면 커널 재시작 전까지 유지됨.
#
# 단축키:
#   좌클릭         : t_tap 위치 설정 (0.01s 그리드로 스냅)
#   ← / →          : ±0.01s 미세 조정
#   Shift + ← / →  : ±0.1s 조정
#   r              : 자동 검출값으로 reset
#   Enter / 창 닫기: 현재 선택값 확정 → 다음 condition 으로 진행
#   왼쪽 한계      : 1AB 시작이 0초가 되는 t_tap (= -BPM_DURATION). 음수 허용.
#
# t_tap_offset 은 GUI 의 "초기 선택 위치" 로 사용된다 (없으면 자동 검출값).
# scalar 또는 dict 두 가지 형태 지원:
#   - scalar  : 모든 condition 에 동일 적용              → t_tap_offset=-2.3
#   - dict    : condition 별로 다른 값                   → t_tap_offset={"7kg_10bpm": -2.3, "7kg_16bpm": -1.5}
#     · dict 에 없는 cond_key 는 "_default" 값으로 폴백  → t_tap_offset={"_default": -2.0, "7kg_16bpm": -1.5}
#     · "_default" 도 없으면 0.0 으로 폴백 (정보 print)

# %matplotlib qt
# % matplotlib tk

dry_run  = True            # True: tap_onset_check.png 만 저장,  False: 실제 TRC/MOT 생성
namecode = "260306_KTY"    # TODO: 필요 시 변경

# condition 별로 다른 초기 offset 을 주는 예시.
# (인터랙티브 1회 후 콘솔에 출력되는 effective offset 을 채워넣고 재실행하면
#  동일한 결과를 자동으로 재현할 수 있음.)
t_tap_offset_per_cond = {
    # "_default":  -2.00,   # 명시 안 한 cond 에 적용할 기본값 (선택)
    # "7kg_10bpm":  -2.30,
    # "7kg_16bpm": 0.30,
    # "15kg_10bpm": -1.45,
    # "15kg_16bpm": -2.45,
}

process_subject(
    namecode,
    dry_run=dry_run,
    interactive_tap=True,
    t_tap_offset=t_tap_offset_per_cond,
)
