# -*- coding: utf-8 -*-
"""seeded_ik.py — 세그먼트 순차 시드 IK (sequential-seed inverse kinematics)

무엇을 하는가
-------------
세그먼트를 시간 순서대로 IK 하되, **직전 세그먼트 마지막 프레임의 왼팔 3개 좌표를
다음 세그먼트 모델의 `default_value` 로 써 넣는다.** OpenSim IK 는 각 프레임의 초기 추정을
모델의 `default_value` 에서 시작하므로, 이렇게 하면 세그먼트 경계에서 해가 이어진다.

왜 하는가
---------
`pro_sup_l` 은 ±90° 부근에서 Euler gimbal wrap 이 일어난다. 팔을 머리 위로 드는 구간
(우리 프로토콜의 BC) 에서 IK 가 물리적으로 같은 자세의 다른 분지(branch)로 넘어가 버리고,
그러면 `wrist_flex_l` / `wrist_dev_l` / `arm_rot_l` 에 4 Hz 대 채터가 생긴다.
그 채터는 BodyKinematics 가속도 -> 손 외력 추정으로 그대로 번진다.

시드는 **해를 바꾸는 게 아니라 같은 해의 분지를 고정**하는 장치다.
우리 데이터에서 세그먼트 경계 불연속은 0.08° 수준이었다.

같이 들어있는 것
----------------
1. 마커 가중치 (골반 800 : 체간 1). 골반을 강하게 잡아야 요추가 마커 노이즈에 안 흔들린다.
2. 좌표 잠금 4개 (subtalar/mtp 좌우). 발 안쪽 자유도는 이 과제에서 정보가 없어 풀어두면 떠돈다.
3. IK 후 distal arm 회전 좌표만 3 Hz 저역통과. wrap 채터의 잔재를 지운다.
   체간·골반·하지 좌표는 건드리지 않는다.

이 세 가지는 서로 독립이라 `--no-seed`, `--no-smooth` 로 껐다 켰다 하며 비교할 수 있다.

실행
----
    python seeded_ik.py --model SUB1_Scaled.osim --trc-dir <TRC 폴더> --out-dir <결과 폴더>

    옵션
      --no-seed      시드 없이 매번 base 모델로 IK (대조군)
      --no-smooth    IK 후 3 Hz 평활 생략
      --order-file   세그먼트 순서를 한 줄에 하나씩 적은 텍스트 파일
                     (기본은 파일명 자연정렬 -- 2AB 가 10AB 보다 앞)

출력 (세그먼트마다)
      <out-dir>/<세그먼트>/<세그먼트>_IK.mot
      <out-dir>/<세그먼트>/SETUP_IK.xml
      <out-dir>/<세그먼트>/model_seeded.osim     <- 시드 모드일 때만
      <out-dir>/seed_chain.csv                   <- 시드 값과 경계 불연속 점검표

주의
----
* **순서가 곧 알고리즘이다.** 세그먼트가 시간 순서대로 이어져야 시드가 의미가 있다.
  파일명이 시간 순이 아니면 `--order-file` 로 순서를 직접 주는 편이 안전하다.
* 모델에 `arm_flex_l` / `arm_add_l` / `pro_sup_l` 좌표가 있어야 한다. 이름이 다르면
  `SEED_COORDS` 를 고쳐라.
* 마커 이름이 다르면 `IK_MARKER_WEIGHTS` 를 그쪽 마커셋에 맞춰야 한다. 여기 없는 마커는
  OpenSim 기본 가중치 1 로 들어간다 (0 이 아니다).
* TRC 시간은 세그먼트마다 0 부터 시작한다고 가정한다. 절대시간 TRC 면 `--abs-time` 를 쓴다.
* OpenSim 4.5 Python API 기준.

출처: KTY/KCH 파이프라인 `pipeline.py` 의 `_make_seeded_model` / `_run_ik` /
`_smooth_distal_arm` / `stage_ik` 를 값 변경 없이 단일 파일로 옮긴 것.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt

import opensim as osim

# ==============================================================================
# 설정 — 우리가 실제로 돌린 값 그대로
# ==============================================================================

# 시드를 물려주는 좌표 3개와, 첫 세그먼트의 출발값(해부학적 neutral, deg)
SEED_COORDS = ['arm_flex_l', 'arm_add_l', 'pro_sup_l']
NEUTRAL_SEED_DEG = (10.0, -10.0, 0.0)

# 마커 가중치. 골반 800 : 체간(C7/T10) 1 이 핵심 비율.
# 좌팔 distal 만 상향(LELB 500, LWRA/B 400, LFN2/5 300) — 분지 전환 억제용.
IK_MARKER_WEIGHTS = [
    ("LSHO", 250), ("RSHO", 250), ("C7", 1), ("T10", 1),
    ("LASI", 800), ("RASI", 800), ("LPSI", 800), ("RPSI", 800),
    ("LGTR", 350), ("RGTR", 350), ("LKNE", 600), ("RKNE", 600),
    ("LANK", 200), ("RANK", 200), ("LTOE", 350), ("RTOE", 350),
    ("LMT5", 100), ("RMT5", 100), ("LHEE", 250), ("RHEE", 250),
    ("LELB", 500), ("RELB", 250), ("LWRA", 400), ("LWRB", 400),
    ("RWRA", 150), ("RWRB", 150), ("LFN2", 300), ("LFN5", 300),
    ("RFN2", 100), ("RFN5", 100),
]

# 기본값으로 잠그는 좌표 (가중치 1000)
IK_COORD_LOCK = ["subtalar_angle_r", "mtp_angle_r", "subtalar_angle_l", "mtp_angle_l"]

# IK 후 평활할 좌표 — 회전 자유도만. 체간/골반/하지는 제외.
DISTAL_ARM_COORDS = [
    'pro_sup_l', 'wrist_flex_l', 'wrist_dev_l', 'arm_rot_l',
    'pro_sup_r', 'wrist_flex_r', 'wrist_dev_r', 'arm_rot_r',
]
SMOOTH_CUTOFF_HZ = 3.0
SMOOTH_ORDER = 2


# ==============================================================================
# .sto / .mot 입출력
# ==============================================================================

def read_sto(path):
    """OpenSim .sto/.mot -> (DataFrame, meta)."""
    path = Path(path)
    with path.open('r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    end_idx = next(i for i, line in enumerate(lines) if 'endheader' in line.lower())
    col_idx = None
    for i in range(end_idx + 1, len(lines)):
        s = lines[i].strip()
        if not s:
            continue
        if s.lower().startswith('time'):
            col_idx = i
            break
    if col_idx is None:
        for i in range(end_idx + 1, len(lines)):
            if lines[i].strip():
                col_idx = i
                break
    if col_idx is None:
        raise ValueError(f'컬럼 행 없음: {path}')
    columns = re.split(r'\s+', lines[col_idx].strip())
    rows = []
    for line in lines[col_idx + 1:]:
        s = line.strip()
        if not s or s.lower().startswith('time'):
            continue
        rows.append(re.split(r'\s+', s))
    df = pd.DataFrame(rows, columns=columns).apply(pd.to_numeric, errors='coerce')
    df = df.dropna(how='all')
    return df, {'header_lines': lines[:end_idx + 1], 'column_line': lines[col_idx]}


def write_sto(path, df, meta, float_fmt='%.8f'):
    """DataFrame -> .sto. 헤더의 행/열/구간 값을 갱신한다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nrows, ncols = len(df), len(df.columns)
    tmin, tmax = float(df['time'].iloc[0]), float(df['time'].iloc[-1])
    new_header = []
    for line in meta['header_lines']:
        low = line.lower().strip()
        if low.startswith('nrows='):
            new_header.append(f'nRows={nrows}\n')
        elif low.startswith('datarows '):
            new_header.append(f'datarows {nrows}\n')
        elif low.startswith('ncolumns='):
            new_header.append(f'nColumns={ncols}\n')
        elif low.startswith('datacolumns '):
            new_header.append(f'datacolumns {ncols}\n')
        elif low.startswith('range '):
            new_header.append(f'range {tmin:.6f} {tmax:.6f}\n')
        else:
            new_header.append(line)
    with path.open('w', encoding='utf-8') as f:
        for line in new_header:
            f.write(line)
        f.write('\t'.join(df.columns) + '\n')
        df.to_csv(f, sep='\t', index=False, header=False,
                  float_format=float_fmt, lineterminator='\n')


# ==============================================================================
# 핵심 1 — 시드 모델 만들기
# ==============================================================================

def make_seeded_model(base_path, seed_deg, out_path):
    """base osim 의 SEED_COORDS 3개 `default_value` 를 seed_deg(도) 로 덮어써서 저장.

    .osim 은 XML 이지만 여기서는 텍스트 치환으로 처리한다. OpenSim API 로 열고 저장하면
    파일 전체가 재작성되면서 다른 필드까지 바뀔 수 있어서, 건드릴 값만 정확히 바꾸는 쪽을 택했다.
    """
    text = Path(base_path).read_text()
    for cn, vdeg in zip(SEED_COORDS, seed_deg):
        vrad = vdeg * np.pi / 180
        pat = re.compile(
            r'(<Coordinate name="' + re.escape(cn) + r'">.*?<default_value>)([^<]+)(</default_value>)',
            flags=re.DOTALL)
        text, n = pat.subn(lambda m: m.group(1) + f'{vrad:.10g}' + m.group(3), text, count=1)
        if n == 0:
            raise RuntimeError(f'default_value 를 못 찾음: {cn} (모델에 그 좌표가 있는지 확인)')
    Path(out_path).write_text(text)
    return out_path


# ==============================================================================
# 핵심 2 — IK 실행
# ==============================================================================

def run_ik(model_path, trc, ik_mot, results_dir, t0=0.0, t1=None):
    ik = osim.InverseKinematicsTool()
    ik.set_model_file(str(model_path))
    ik.setMarkerDataFileName(str(trc))
    ik.setOutputMotionFileName(str(ik_mot))
    ik.setStartTime(float(t0))
    ik.setEndTime(float(t1))
    ik.setResultsDir(str(results_dir))
    ik.set_report_errors(True)

    tasks = ik.getIKTaskSet()
    for name, w in IK_MARKER_WEIGHTS:
        tk = osim.IKMarkerTask()
        tk.setName(name)
        tk.setWeight(float(w))
        tk.setApply(True)
        tasks.cloneAndAppend(tk)
    for cn in IK_COORD_LOCK:
        ct = osim.IKCoordinateTask()
        ct.setName(cn)
        ct.setApply(True)
        ct.setWeight(1000)
        ct.setValueType(osim.IKCoordinateTask.DefaultValue)
        tasks.cloneAndAppend(ct)

    ik.printToXML(str(Path(results_dir) / 'SETUP_IK.xml'))
    ik.run()


# ==============================================================================
# 핵심 3 — IK 후 distal arm 평활
# ==============================================================================

def smooth_distal_arm(ik_mot, cutoff_hz=SMOOTH_CUTOFF_HZ, order=SMOOTH_ORDER):
    """distal arm 회전 좌표만 unwrap 후 zero-phase 저역통과. 나머지 좌표는 그대로 둔다."""
    df, meta = read_sto(ik_mot)
    t = df['time'].to_numpy(float)
    if len(t) < max(20, 4 * order + 1):
        return 0
    fs = 1.0 / float(np.median(np.diff(t)))
    b, a = butter(order, cutoff_hz / (fs / 2), btype='low')
    touched = 0
    for c in DISTAL_ARM_COORDS:
        if c in df.columns:
            x = np.unwrap(np.deg2rad(df[c].to_numpy(float)))
            df[c] = np.rad2deg(filtfilt(b, a, x))
            touched += 1
    if touched:
        write_sto(ik_mot, df, meta)
    return touched


# ==============================================================================
# 유틸
# ==============================================================================

def natural_key(s):
    """'2AB' 가 '10AB' 보다 앞에 오도록 하는 정렬 키."""
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', str(s))]


def trc_time_range(trc_path):
    """TRC 의 첫/마지막 시간 (2번째 열)."""
    lines = [l for l in Path(trc_path).read_text().splitlines() if l.strip()]
    data = [l for l in lines[5:] if l.split('\t')[0].strip().isdigit()]
    t0 = float(data[0].split('\t')[1])
    t1 = float(data[-1].split('\t')[1])
    return t0, t1


# ==============================================================================
# main
# ==============================================================================

def main():
    ap = argparse.ArgumentParser(description='세그먼트 순차 시드 IK')
    ap.add_argument('--model', required=True, help='스케일된 base osim (근육/액추에이터 없어도 됨)')
    ap.add_argument('--trc-dir', required=True, help='세그먼트 TRC 들이 있는 폴더')
    ap.add_argument('--out-dir', required=True, help='결과를 쓸 폴더')
    ap.add_argument('--order-file', default=None, help='세그먼트 순서를 한 줄에 하나씩 적은 텍스트')
    ap.add_argument('--no-seed', action='store_true', help='시드 없이 매번 base 모델로 IK')
    ap.add_argument('--no-smooth', action='store_true', help='IK 후 3 Hz 평활 생략')
    ap.add_argument('--abs-time', action='store_true',
                    help='TRC 가 절대시간이면 지정 (기본은 세그먼트마다 0 부터 시작한다고 가정)')
    args = ap.parse_args()

    model = Path(args.model).resolve()
    trc_dir = Path(args.trc_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    if not model.is_file():
        sys.exit(f'모델 없음: {model}')
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.order_file:
        names = [l.strip() for l in Path(args.order_file).read_text().splitlines() if l.strip()]
        trcs = [trc_dir / (n if n.lower().endswith('.trc') else n + '.trc') for n in names]
        missing = [p.name for p in trcs if not p.is_file()]
        if missing:
            sys.exit(f'order-file 에 적힌 TRC 를 못 찾음: {missing[:5]}')
    else:
        trcs = sorted(trc_dir.glob('*.trc'), key=lambda p: natural_key(p.stem))
    if not trcs:
        sys.exit(f'TRC 없음: {trc_dir}')

    mode = 'no seed (base model)' if args.no_seed else 'sequential seed'
    print(f'[IK] {len(trcs)} segments, {mode}, smooth={"off" if args.no_smooth else "3 Hz"}')
    print(f'  순서: {", ".join(p.stem for p in trcs[:6])}{" ..." if len(trcs) > 6 else ""}')

    rows = []
    prev_seed = NEUTRAL_SEED_DEG
    prev_name = '(neutral)'
    for i, trc in enumerate(trcs, 1):
        seg = trc.stem
        seg_dir = out_dir / seg
        seg_dir.mkdir(parents=True, exist_ok=True)
        ik_mot = seg_dir / f'{seg}_IK.mot'

        t0, t1 = trc_time_range(trc)
        if not args.abs_time:
            t0 = 0.0

        if args.no_seed:
            model_used = model
        else:
            model_used = make_seeded_model(model, prev_seed, seg_dir / 'model_seeded.osim')

        run_ik(model_used, trc, ik_mot, seg_dir, t0=t0, t1=t1)
        n_sm = 0 if args.no_smooth else smooth_distal_arm(ik_mot)

        df, _ = read_sto(ik_mot)
        first = df.iloc[0]
        last = df.iloc[-1]
        # 경계 불연속: 이번 세그 첫 프레임이 직전 세그 마지막 값과 얼마나 벌어졌나
        gap = [abs(float(first[c]) - prev_seed[k]) for k, c in enumerate(SEED_COORDS)
               if c in df.columns]
        rows.append(dict(
            order=i, segment=seg, model='base' if args.no_seed else 'seeded',
            seed_arm_flex_l=prev_seed[0], seed_arm_add_l=prev_seed[1], seed_pro_sup_l=prev_seed[2],
            first_arm_flex_l=float(first['arm_flex_l']) if 'arm_flex_l' in df else np.nan,
            last_arm_flex_l=float(last['arm_flex_l']) if 'arm_flex_l' in df else np.nan,
            last_arm_add_l=float(last['arm_add_l']) if 'arm_add_l' in df else np.nan,
            last_pro_sup_l=float(last['pro_sup_l']) if 'pro_sup_l' in df else np.nan,
            boundary_gap_deg=max(gap) if gap else np.nan,
            n_frames=len(df), n_smoothed_coords=n_sm,
        ))
        print(f'  [{i:3d}/{len(trcs)}] {seg}  {len(df)} frames  '
              f'seed<-{prev_name}  경계차 {rows[-1]["boundary_gap_deg"]:.2f}deg')

        if not args.no_seed:
            prev_seed = tuple(float(last[c]) for c in SEED_COORDS)
            prev_name = seg

    rep = pd.DataFrame(rows)
    rep.to_csv(out_dir / 'seed_chain.csv', index=False, encoding='utf-8-sig')
    g = rep['boundary_gap_deg'].dropna()
    if len(g) > 1:
        # 첫 세그먼트는 neutral 에서 출발하므로 경계차 개념이 없다 -> 제외
        g = g.iloc[1:]
        print(f'\n경계 불연속 (2번째 세그부터, n={len(g)}): '
              f'중앙 {g.median():.3f}deg, 최대 {g.max():.3f}deg')
    print(f'-> {out_dir / "seed_chain.csv"}')


if __name__ == '__main__':
    main()
