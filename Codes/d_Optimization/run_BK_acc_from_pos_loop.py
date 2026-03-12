"""
remake_BK_acc_from_pos_class 기반 스크립트. 두 가지 모드를 독립적으로 실행할 수 있습니다.

1) BK 루프 (기본): BK_Results 내 *BodyKinematics_pos_global.sto 를 glob으로 찾아
   position → 가속도 → 1000Hz 저장 → (선택) 시간 기준 반분할
   예: python run_BK_acc_from_pos_loop.py [--no-split]

2) SO 반분할: SO_Results 내 *StaticOptimization_force.sto 에 대해
   1000Hz 업샘플링 → 시간 기준 반분할 순으로 수행, 결과를 PostSim 하위 폴더에 저장 (glob 사용)
   예: python run_BK_acc_from_pos_loop.py --so
"""

import glob
from pathlib import Path

from remake_BK_acc_from_pos_class import (
    BKAccFromPosPipeline,
    TimeSeriesStorage,
    split_storage_by_time_half,
)

# =========================================================
# 공통 / BK 루프 설정
# =========================================================
SOURCE_DIR = Path(r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\c_AddBio_Continous")
SUB = "SUB1"
TRIAL_FOLDER = "trial15_10_1"
BK_RESULTS = "BK_Results"
SO_RESULTS = "SO_Results"

BK_RESULTS_DIR = SOURCE_DIR / SUB / "APP2_OneCycle" / TRIAL_FOLDER / BK_RESULTS
BK_POST_SIM_DIR = BK_RESULTS_DIR / "PostSim"
BK_GLOB_PATTERN = "*BodyKinematics_pos_global.sto"

# position 파일명에서 출력 파일명으로: _BodyKinematics_pos_global.sto → _BK_acc_global_1000Hz.sto
POS_SUFFIX = "_BodyKinematics_pos_global.sto"
OUT_SUFFIX = "_BK_acc_global_1000Hz.sto"


def generate_upsamled_BK_acc_and_split(do_split_half: bool = True) -> None:
    """
    BK_Results 내 *BodyKinematics_pos_global.sto 를 glob으로 찾아
    각각에 대해 position → 가속도 → 1000Hz 저장(BK_Results) → (선택) 시간 기준 반분할(PostSim 하위 폴더) 을 실행합니다.
    """
    if not BK_RESULTS_DIR.exists():
        raise FileNotFoundError(f"경로가 없습니다: {BK_RESULTS_DIR}")

    search = BK_RESULTS_DIR / BK_GLOB_PATTERN
    pos_files = sorted(glob.glob(str(search)))

    if not pos_files:
        print(f"대상 파일 없음: {search}")
        return

    print(f"대상 폴더: {BK_RESULTS_DIR}")
    print(f"반분할 저장: {BK_POST_SIM_DIR}")
    print(f"파일 수: {len(pos_files)}\n")

    pipeline = BKAccFromPosPipeline(set_time_to_zero=False, output_fs_hz=1000)

    for p in pos_files:
        pos_sto = Path(p)
        # 1000Hz 결과: BK_Results 에 저장
        out_name = pos_sto.name.replace(POS_SUFFIX, OUT_SUFFIX)
        out_sto = pos_sto.parent / out_name

        print(f"\n{'='*60}")
        print(f"{pos_sto.name}")
        print(f"{'='*60}")

        try:
            pipeline.run(pos_sto, out_sto)
            if do_split_half:
                print("  Splitting into 1st / 2nd half → PostSim...")
                out_1st, out_2nd = split_storage_by_time_half(out_sto, output_dir=BK_POST_SIM_DIR)
                print(f"    {out_1st.name}")
                print(f"    {out_2nd.name}")
        except Exception as e:
            print(f"  Error: {e}")
            raise

    print("\nAll trials done.")


# =========================================================
# SO 반분할 설정
# =========================================================
SO_RESULTS_DIR = SOURCE_DIR / SUB / "APP2_OneCycle" / TRIAL_FOLDER / SO_RESULTS
POST_SIM_DIR = SO_RESULTS_DIR / "PostSim"
GLOB_PATTERN = "*StaticOptimization_force.sto"


def run_so_split() -> None:
    """
    SO_Results 내 ...StaticOptimization_force.sto 파일들을 glob으로 찾아
    각각에 대해 1000Hz 업샘플링 → 시간 기준 반분할 순으로 수행하고, 결과를 PostSim 하위 폴더에 저장합니다.
    """
    if not SO_RESULTS_DIR.exists():
        raise FileNotFoundError(f"경로가 없습니다: {SO_RESULTS_DIR}")

    POST_SIM_DIR.mkdir(parents=True, exist_ok=True)

    search = SO_RESULTS_DIR / GLOB_PATTERN
    sto_files = sorted(glob.glob(str(search)))

    if not sto_files:
        print(f"대상 파일 없음: {search}")
        return

    print(f"대상 폴더: {SO_RESULTS_DIR}")
    print(f"저장 폴더: {POST_SIM_DIR}")
    print(f"파일 수: {len(sto_files)}\n")

    pipeline = BKAccFromPosPipeline(set_time_to_zero=False, output_fs_hz=1000)

    for p in sto_files:
        path = Path(p)
        print(f"{path.name} ...")
        try:
            df, meta = TimeSeriesStorage.read(path)
            if "time" not in df.columns:
                raise ValueError(f"time 컬럼 없음: {path.name}")
            print("  Upsampling to 1000Hz...")
            df_1000 = pipeline.upsample_to_fs(df)
            t_min, t_max = df_1000["time"].iloc[0], df_1000["time"].iloc[-1]
            t_mid = (t_min + t_max) / 2.0
            df_1st = df_1000[df_1000["time"] < t_mid].copy()
            df_2nd = df_1000[df_1000["time"] >= t_mid].copy()
            if len(df_1st) == 0 or len(df_2nd) == 0:
                raise ValueError(f"반으로 나눈 뒤 한쪽에 행 없음: time {t_min} ~ {t_max}")
            suffix = path.suffix
            out_1st = POST_SIM_DIR / f"{path.stem}_1st_half{suffix}"
            out_2nd = POST_SIM_DIR / f"{path.stem}_2nd_half{suffix}"
            print("  Splitting into 1st / 2nd half...")
            TimeSeriesStorage.write(out_1st, df_1st, meta)
            TimeSeriesStorage.write(out_2nd, df_2nd, meta)
            print(f"  -> {out_1st.name}")
            print(f"  -> {out_2nd.name}")
        except Exception as e:
            print(f"  Error: {e}")
            raise

    print("\nDone.")


# =========================================================
# 진입점
# =========================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="BK 루프(pos→가속도 1000Hz→반분할) 또는 SO force.sto 반분할만 실행"
    )
    parser.add_argument(
        "--so",
        action="store_true",
        help="SO 모드: SO_Results 내 *StaticOptimization_force.sto 반분할 → PostSim 저장",
    )
    parser.add_argument(
        "--no-split",
        action="store_true",
        help="BK 모드: 반으로 분할하지 않음",
    )
    args = parser.parse_args()

    if args.so:
        run_so_split()
    else:
        generate_upsamled_BK_acc_and_split(do_split_half=not args.no_split)
