"""
Grip event detection from ExtLoadAPP1.mot loadcell data.
Detects Up_grip, Up_deposit, Down_grip, Down_deposit as threshold (3 N) crossing times.
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt


# Default path: OneCycle_TrcMot folder with *ExtLoadAPP1.mot (10 files, task 1..10)
DEFAULT_MOT_DIR = Path(r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\c_AddBio_Continous\SUB1\OneCycle_TrcMot")
DEFAULT_KG_BPM = "15_10"
DEFAULT_TRIAL = "1"
DEFAULT_TASK_NUMS = list(range(1, 11))  # 1..10
THRESHOLD_N = 2.0

EVENT_KEYS = ("Up_grip", "Up_deposit", "Down_grip", "Down_deposit")

FORCE_COLS = [
    "hand_force3_vx", "hand_force3_vy", "hand_force3_vz",
    "hand_force4_vx", "hand_force4_vy", "hand_force4_vz",
]


def read_opensim_mot(path):
    """Read OpenSim .mot file; return DataFrame with numeric data and time column."""
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    end_idx = next(i for i, line in enumerate(lines) if "endheader" in line.lower())
    j = end_idx + 1
    while j < len(lines) and not lines[j].strip():
        j += 1

    columns = lines[j].strip().split()
    rows = [ln.strip().split() for ln in lines[j + 1:] if ln.strip()]
    df = pd.DataFrame(rows, columns=columns).apply(pd.to_numeric, errors="coerce")
    df = df.dropna(how="all")
    return df


def load_force_and_time(df):
    """Extract time and force columns; compute resultant (Euclidean norm) of hand_force3 + hand_force4."""
    time = df["time"].values
    required = ["time"] + FORCE_COLS
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing columns: {missing}. Available: {list(df.columns)}")

    v3 = df[["hand_force3_vx", "hand_force3_vy", "hand_force3_vz"]].values
    v4 = df[["hand_force4_vx", "hand_force4_vy", "hand_force4_vz"]].values
    # 합력 벡터 후 유클리디안 norm
    F_total = v3 + v4
    resultant = np.linalg.norm(F_total, axis=1)
    return time, resultant


def find_crossing_times(time, resultant, threshold, dead_time_sec=0.5):
    """
    Find exactly 8 events: first two upward (below->above) and first two downward (above->below) crossings.
    Returns (Up_grip, Up_deposit, Down_grip, Down_deposit) as time values.
    '직전' 시점: 7을 넘기 직전 = crossing 직전 샘플의 time (마지막으로 threshold 미만인 시점).
    한 번 이벤트가 발견되면 dead_time_sec(기본 0.5초) 동안은 다른 이벤트를 인정하지 않는다.
    """
    above = resultant >= threshold
    below = resultant < threshold

    # Upward: 이전은 below, 현재는 above → 직전 샘플의 time
    up_cross_idx = []
    for i in range(1, len(above)):
        if below[i - 1] and above[i]:
            up_cross_idx.append(i - 1)
    # Downward: 이전은 above, 현재는 below → 직전 샘플의 time
    down_cross_idx = []
    for i in range(1, len(above)):
        if above[i - 1] and below[i]:
            down_cross_idx.append(i - 1)

    # (시간, 'up'|'down') 리스트를 시간순으로 정렬 후, 0.5초 데드타임 적용
    events_raw = [(time[i], "up") for i in up_cross_idx] + [(time[i], "down") for i in down_cross_idx]
    events_raw.sort(key=lambda x: x[0])
    accepted = []
    for t, typ in events_raw:
        if not accepted or (t - accepted[-1][0]) >= dead_time_sec:
            accepted.append((t, typ))
        if len(accepted) >= 4:
            break

    # accepted에서 1번째 up -> Up_grip, 1번째 down -> Up_deposit, 2번째 up -> Down_grip, 2번째 down -> Down_deposit
    #
    ups = [t for t, typ in accepted if typ == "up"]
    downs = [t for t, typ in accepted if typ == "down"]
    Up_grip = ups[0] if len(ups) > 0 else np.nan
    Up_deposit = downs[0] if len(downs) > 0 else np.nan
    Down_grip = ups[1] if len(ups) > 1 else np.nan
    Down_deposit = downs[1] if len(downs) > 1 else np.nan

    return Up_grip, Up_deposit, Down_grip, Down_deposit


def get_extload_app1_mot_paths(mot_dir, kg_bpm, trial, task_nums):
    """Build sorted list of ExtLoadAPP1.mot file paths for given task numbers."""
    mot_dir = Path(mot_dir)
    paths = []
    for k in task_nums:
        name = f"{kg_bpm}_trial{trial}_12sec_{k}_ExtLoadAPP1.mot"
        p = mot_dir / name
        if p.exists():
            paths.append(p)
        else:
            paths.append(None)
    return paths


def run_detection(
    mot_dir=DEFAULT_MOT_DIR,
    kg_bpm=DEFAULT_KG_BPM,
    trial=DEFAULT_TRIAL,
    task_nums=None,
    threshold=THRESHOLD_N,
):
    """
    Run grip event detection on all ExtLoadAPP1.mot files in order.
    Returns dict with keys Up_grip, Up_deposit, Down_grip, Down_deposit;
    each value is a 1D array of length n_tasks (e.g. 10).
    Use as_events_array(events_dict, rows_trials=True) for (10, 4) or (4, 10).
    """
    if task_nums is None:
        task_nums = DEFAULT_TASK_NUMS

    events_dict = {k: [] for k in EVENT_KEYS}

    paths = get_extload_app1_mot_paths(mot_dir, kg_bpm, trial, task_nums)

    for p in paths:
        if p is None:
            for k in EVENT_KEYS:
                events_dict[k].append(np.nan)
            continue
        df = read_opensim_mot(p)
        time, resultant = load_force_and_time(df)
        ug, ud, dg, dd = find_crossing_times(time, resultant, threshold)
        events_dict["Up_grip"].append(ug)
        events_dict["Up_deposit"].append(ud)
        events_dict["Down_grip"].append(dg)
        events_dict["Down_deposit"].append(dd)

    for k in EVENT_KEYS:
        events_dict[k] = np.array(events_dict[k])

    return events_dict


def as_events_array(events_dict, rows_trials=True):
    """
    Stack event times into a single array.
    rows_trials=True  -> shape (n_trials, 4) e.g. (10, 4), columns = Up_grip, Up_deposit, Down_grip, Down_deposit
    rows_trials=False -> shape (4, n_trials) e.g. (4, 10)
    """
    cols = [events_dict[k] for k in EVENT_KEYS]
    stacked = np.column_stack(cols)
    if not rows_trials:
        stacked = stacked.T
    return stacked


def save_events_dict(events_dict, path):
    """
    Up_grip, Up_deposit, Down_grip, Down_deposit 배열을 가진 딕셔너리를 .npz로 저장.
    path: 저장 경로 (예: 'grip_events.npz')
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **{k: events_dict[k] for k in EVENT_KEYS})
    return path


def load_events_dict(path):
    """
    save_events_dict로 저장한 .npz에서 이벤트 딕셔너리 복원.
    Returns dict with keys EVENT_KEYS, each value ndarray shape (n_trials,).
    """
    data = np.load(path)
    return {k: data[k] for k in EVENT_KEYS}


def plot_all_trials(
    mot_dir=DEFAULT_MOT_DIR,
    kg_bpm=DEFAULT_KG_BPM,
    trial=DEFAULT_TRIAL,
    task_nums=None,
    threshold=THRESHOLD_N,
    events_dict=None,
    figsize=(14, 10),
):
    """
    확인용: 10개 트라이얼에 대해 서브플롯으로 resultant force와 4개 이벤트 시점을 그린다.
    events_dict가 None이면 run_detection()으로 계산한다.
    """
    if task_nums is None:
        task_nums = DEFAULT_TASK_NUMS
    if events_dict is None:
        events_dict = run_detection(mot_dir=mot_dir, kg_bpm=kg_bpm, trial=trial, task_nums=task_nums, threshold=threshold)

    paths = get_extload_app1_mot_paths(mot_dir, kg_bpm, trial, task_nums)
    n = len(paths)
    ncols = 5
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize)
    if n == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    event_colors = {"Up_grip": "green", "Up_deposit": "orange", "Down_grip": "teal", "Down_deposit": "red"}
    event_labels = {"Up_grip": "Up_grip", "Up_deposit": "Up_dep", "Down_grip": "Down_grip", "Down_deposit": "Down_dep"}

    for idx, (ax, p) in enumerate(zip(axes, paths)):
        if p is None or not p.exists():
            ax.set_visible(False)
            continue
        df = read_opensim_mot(p)
        time, resultant = load_force_and_time(df)
        ax.plot(time, resultant, "b-", lw=0.8, label="resultant (N)")
        ax.axhline(threshold, color="gray", ls="--", lw=0.8, label=f"threshold {threshold} N")

        for ek in EVENT_KEYS:
            t_ev = events_dict[ek][idx]
            if np.isfinite(t_ev):
                ax.axvline(t_ev, color=event_colors[ek], alpha=0.8, lw=0.9, label=event_labels[ek])

        ax.set_title(f"Trial {task_nums[idx]}", fontsize=10)
        ax.set_xlabel("time (s)")
        ax.set_ylabel("Force (N)")
        ax.legend(loc="upper right", fontsize=6)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(time[0], time[-1])

    for j in range(n, len(axes)):
        axes[j].set_visible(False)

    plt.suptitle("Grip events (loadcell resultant, threshold=3 N)", fontsize=12)
    plt.tight_layout()
    return fig, axes


# 기본 저장 경로 (스크립트 위치 기준)
DEFAULT_EVENTS_SAVE_PATH = Path(__file__).resolve().parent / "grip_events.npz"


if __name__ == "__main__":
    events = run_detection()
    print("Event keys:", list(events.keys()))
    for k in EVENT_KEYS:
        print(k, events[k].shape, events[k])

    # 딕셔너리 저장
    save_events_dict(events, DEFAULT_EVENTS_SAVE_PATH)
    print("Saved:", DEFAULT_EVENTS_SAVE_PATH)

    # (10, 4): 행=트라이얼, 열=이벤트
    arr_trials_rows = as_events_array(events, rows_trials=True)
    print("as_events_array(events, rows_trials=True).shape:", arr_trials_rows.shape)

    # (4, 10): 행=이벤트, 열=트라이얼
    arr_events_rows = as_events_array(events, rows_trials=False)
    print("as_events_array(events, rows_trials=False).shape:", arr_events_rows.shape)

    # 확인용: 10개 트라이얼 서브플롯
    fig, axes = plot_all_trials(events_dict=events)
    plt.show()
