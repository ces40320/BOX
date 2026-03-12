"""
OpenSim/일반 시계열 파일 → 가속도 계산 → 업샘플링 파이프라인. 클래스 단위 구현.

지원 포맷:
- OpenSim endheader 형식: .sto, .mot (endheader 위 메타데이터·아래 컬럼 행 보존)
- OpenSim .trc (다중 행 헤더, Frame#/Time 컬럼)
- 일반 테이블: .csv, .tsv (첫 행 헤더만, endheader 없음)

- TimeSeriesStorage: 통합 read/write (포맷 자동 감지, time 컬럼 정규화)
- OpenSimStorage: .sto / .mot endheader 전용
- TrcStorage: .trc 전용
- PlainTableStorage: .csv / .tsv 전용
- BKAccFromPosPipeline: position → acceleration → 업샘플링 파이프라인
- split_storage_by_time_half: 시간 기준 반분할 (endheader/trc/plain 공통)
"""

from pathlib import Path
import re
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from typing import Tuple, Literal

# 지원 확장자
EXT_ENDHEADER = (".sto", ".mot")
EXT_TRC = (".trc",)
EXT_PLAIN = (".csv", ".tsv")

# =========================================================
# 기본 설정 (직접 실행 시에만 사용)
# =========================================================
SOURCE_DIR = Path(r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\c_AddBio_Continous")
POS_STO = SOURCE_DIR / "SUB1" / "APP2_OneCycle" / "trial15_10_1" / "BK_Results" / "SUB1_15_10_1_12sec_1_APP2_OneCycle_BodyKinematics_pos_global.sto"
OUT_STO_1000HZ = SOURCE_DIR / "SUB1" / "APP2_OneCycle" / "trial15_10_1" / "BK_Results" / "SUB1_15_10_1_12sec_1_APP2_OneCycle_BK_acc_global_1000Hz.sto"


# =========================================================
# 포맷 감지 및 통합 read/write
# =========================================================
def _detect_format(path: Path) -> Literal["endheader", "trc", "plain"]:
    """파일 확장자로 포맷을 판별합니다. endheader는 내용으로도 확인합니다."""
    path = Path(path)
    suf = path.suffix.lower()
    if suf in EXT_TRC:
        return "trc"
    if suf in EXT_PLAIN:
        return "plain"
    if suf in EXT_ENDHEADER:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for _ in range(100):
                    line = f.readline()
                    if "endheader" in line.lower():
                        return "endheader"
                    if not line:
                        break
        except (OSError, UnicodeDecodeError):
            pass
        return "endheader"
    # 확장자 미지정 시 첫 줄로 추정
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            first = f.readline()
        if "endheader" in first.lower():
            return "endheader"
        if "PathFileType" in first or "DataRate" in first:
            return "trc"
    except (OSError, UnicodeDecodeError):
        pass
    return "plain"


def _normalize_time_column(df: pd.DataFrame) -> pd.DataFrame:
    """'Time' 컬럼이 있으면 'time'으로 통일해 반환합니다 (복사본)."""
    if "Time" in df.columns and "time" not in df.columns:
        df = df.rename(columns={"Time": "time"})
    return df


def _denormalize_time_for_meta(meta: dict, df: pd.DataFrame) -> pd.DataFrame:
    """쓸 때 meta에 원래 time 컬럼명이 있으면 복원합니다."""
    out = df.copy()
    if meta.get("time_column_original") == "Time" and "time" in out.columns:
        out = out.rename(columns={"time": "Time"})
    return out


class TimeSeriesStorage:
    """
    여러 포맷(.sto, .mot, .trc, .csv, .tsv)을 자동 감지해 읽고,
    동일 포맷으로 쓸 때 메타데이터를 유지합니다.
    """

    @classmethod
    def read(cls, path: Path) -> Tuple[pd.DataFrame, dict]:
        """
        path 확장자/내용으로 포맷을 감지해 읽고 (df, meta)를 반환합니다.
        항상 df에 'time' 컬럼이 있도록 정규화합니다.
        """
        path = Path(path)
        fmt = _detect_format(path)
        if fmt == "endheader":
            df, meta = OpenSimStorage.read(path)
        elif fmt == "trc":
            df, meta = TrcStorage.read(path)
        else:
            df, meta = PlainTableStorage.read(path)
        df = _normalize_time_column(df)
        return df, meta

    @classmethod
    def write(
        cls,
        path: Path,
        df: pd.DataFrame,
        meta: dict,
        float_fmt: str = "%.9f",
    ) -> None:
        """
        meta["format"] 또는 path 확장자에 맞춰 해당 포맷으로 저장합니다.
        """
        path = Path(path)
        fmt = meta.get("format") or _detect_format(path)
        df_out = _denormalize_time_for_meta(meta, df)
        if fmt == "endheader":
            OpenSimStorage.write(path, df_out, meta, float_fmt=float_fmt)
        elif fmt == "trc":
            TrcStorage.write(path, df_out, meta, float_fmt=float_fmt)
        else:
            PlainTableStorage.write(path, df_out, meta, float_fmt=float_fmt)


# =========================================================
# OpenSim .sto / .mot (endheader) Storage 읽기·쓰기
# =========================================================
class OpenSimStorage:
    """
    OpenSim Storage 형식(.sto, .mot) 파일을 읽고 씁니다.
    endheader 위의 메타데이터(nRows/datarows, nColumns/datacolumns, range) 및
    endheader 아래의 컬럼 행을 보존·갱신합니다.
    """

    @staticmethod
    def split_ws(line: str) -> list:
        return re.split(r"\s+", line.strip())

    @classmethod
    def read(cls, path: Path) -> Tuple[pd.DataFrame, dict]:
        """
        .sto 또는 .mot 파일을 읽어 DataFrame과 메타(header_lines, column_line)를 반환합니다.
        """
        path = Path(path)
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        end_idx = next(i for i, line in enumerate(lines) if "endheader" in line.lower())

        col_idx = None
        for i in range(end_idx + 1, len(lines)):
            s = lines[i].strip()
            if not s:
                continue
            if s.lower().startswith("time"):
                col_idx = i
                break

        if col_idx is None:
            for i in range(end_idx + 1, len(lines)):
                s = lines[i].strip()
                if s:
                    col_idx = i
                    break

        if col_idx is None:
            raise ValueError(f"컬럼 줄을 찾지 못했습니다: {path}")

        columns = cls.split_ws(lines[col_idx])

        data_lines = []
        for i in range(col_idx + 1, len(lines)):
            s = lines[i].strip()
            if not s:
                continue
            if s.lower().startswith("time"):
                continue
            data_lines.append(cls.split_ws(s))

        if len(data_lines) == 0:
            raise ValueError(f"데이터 행이 없습니다: {path}")

        df = pd.DataFrame(data_lines, columns=columns).apply(pd.to_numeric, errors="coerce")
        df = df.dropna(how="all")

        meta = {
            "format": "endheader",
            "header_lines": lines[: end_idx + 1],
            "column_line": lines[col_idx],
        }
        return df, meta

    @staticmethod
    def update_header_counts(
        header_lines: list,
        nrows: int,
        ncols: int,
        tmin: float,
        tmax: float,
    ) -> list:
        """
        .sto(nRows=, nColumns=) 및 .mot(datarows, datacolumns) 형식 모두 지원.
        range 행도 tmin, tmax로 갱신합니다.
        """
        new_lines = []
        for line in header_lines:
            low = line.lower().strip()

            if low.startswith("nrows="):
                new_lines.append(f"nRows={nrows}\n")
            elif low.startswith("datarows"):
                new_lines.append(f"datarows {nrows}\n")
            elif low.startswith("ncolumns="):
                new_lines.append(f"nColumns={ncols}\n")
            elif low.startswith("datacolumns"):
                new_lines.append(f"datacolumns {ncols}\n")
            elif low.startswith("range "):
                new_lines.append(f"range {tmin:.6f} {tmax:.6f}\n")
            else:
                new_lines.append(line)

        return new_lines

    @classmethod
    def write(
        cls,
        path: Path,
        df: pd.DataFrame,
        meta: dict,
        float_fmt: str = "%.9f",
    ) -> None:
        """헤더(datarows/nRows, datacolumns/nColumns, range)를 갱신한 뒤 저장합니다."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        header_lines = cls.update_header_counts(
            meta["header_lines"],
            nrows=len(df),
            ncols=len(df.columns),
            tmin=float(df["time"].iloc[0]),
            tmax=float(df["time"].iloc[-1]),
        )

        with path.open("w", encoding="utf-8", newline="") as f:
            for line in header_lines:
                f.write(line)
            f.write("\t".join(df.columns) + "\n")
            df.to_csv(
                f,
                sep="\t",
                index=False,
                header=False,
                float_format=float_fmt,
                lineterminator="\n",
            )


# =========================================================
# OpenSim .trc Storage 읽기·쓰기
# =========================================================
class TrcStorage:
    """
    OpenSim .trc (다중 행 헤더) 파일 읽기·쓰기.
    Frame# / Time 및 마커 X/Y/Z 컬럼을 유지합니다.
    """

    @staticmethod
    def split_tab(line: str) -> list:
        """탭 기준 분리(빈 칸 유지). .trc는 탭 구분."""
        return [c.strip() for c in line.rstrip("\n").split("\t")]

    @classmethod
    def read(cls, path: Path) -> Tuple[pd.DataFrame, dict]:
        path = Path(path)
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        # 헤더: PathFileType, DataRate 행, 데이터 행(1000 1000 NumFrames ...), 컬럼행1, 컬럼행2, 빈 줄
        i = 0
        while i < len(lines) and not lines[i].strip().lower().startswith("frame#"):
            i += 1
        if i >= len(lines):
            raise ValueError(f".trc에서 'Frame#' 컬럼 행을 찾지 못했습니다: {path}")
        col_row1_idx = i
        col_row2_idx = i + 1
        # 빈 줄 또는 데이터 첫 행
        data_start = col_row2_idx + 1
        while data_start < len(lines) and not lines[data_start].strip():
            data_start += 1
        if data_start >= len(lines):
            raise ValueError(f".trc에 데이터 행이 없습니다: {path}")

        parts1 = cls.split_tab(lines[col_row1_idx])
        parts2 = cls.split_tab(lines[col_row2_idx]) if col_row2_idx < len(lines) else []
        # 컬럼명: row1 기준, 빈 칸은 이전 이름 유지. row2가 있으면 name_row1_row2 조합
        columns = []
        prev = ""
        for j, p1 in enumerate(parts1):
            if p1:
                prev = p1
            p2 = parts2[j] if j < len(parts2) else ""
            if p2:
                columns.append(f"{prev}_{p2}" if prev else p2)
            else:
                columns.append(prev or f"col{j}")
        if len(columns) != len(parts1):
            columns = parts1

        data_lines = []
        for idx in range(data_start, len(lines)):
            s = lines[idx].strip()
            if not s:
                continue
            data_lines.append(cls.split_tab(s))
        df = pd.DataFrame(data_lines, columns=columns).apply(pd.to_numeric, errors="coerce")
        df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)

        meta = {
            "format": "trc",
            "time_column_original": "Time",
            "header_lines": lines[:data_start],
            "column_line": lines[col_row1_idx],
            "sub_header_line": lines[col_row2_idx] if col_row2_idx < len(lines) else "",
        }
        return df, meta

    @classmethod
    def write(
        cls,
        path: Path,
        df: pd.DataFrame,
        meta: dict,
        float_fmt: str = "%.9f",
    ) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        header_lines = list(meta.get("header_lines", []))
        # NumFrames 갱신: DataRate 다음 줄이 "1000 1000 158 42 ..." 형태
        for i, line in enumerate(header_lines):
            parts = re.split(r"\s+", line.strip())
            if len(parts) >= 3 and parts[0].isdigit():
                try:
                    parts[2] = str(len(df))
                    header_lines[i] = "\t".join(parts) + "\n"
                except Exception:
                    pass
                break
        with path.open("w", encoding="utf-8", newline="") as f:
            for line in header_lines:
                f.write(line)
            df.to_csv(
                f,
                sep="\t",
                index=False,
                header=False,
                float_format=float_fmt,
                lineterminator="\n",
            )


# =========================================================
# 일반 .csv / .tsv (endheader 없음) 읽기·쓰기
# =========================================================
class PlainTableStorage:
    """첫 행이 헤더인 .csv / .tsv 파일 읽기·쓰기."""

    @classmethod
    def read(cls, path: Path) -> Tuple[pd.DataFrame, dict]:
        path = Path(path)
        suf = path.suffix.lower()
        sep = "\t" if suf == ".tsv" else ","
        df = pd.read_csv(path, sep=sep, encoding="utf-8", on_bad_lines="skip")
        df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)
        meta = {"format": "plain", "sep": sep}
        return df, meta

    @classmethod
    def write(
        cls,
        path: Path,
        df: pd.DataFrame,
        meta: dict,
        float_fmt: str = "%.9f",
    ) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sep = meta.get("sep", "\t" if path.suffix.lower() == ".tsv" else ",")
        df.to_csv(path, sep=sep, index=False, float_format=float_fmt, encoding="utf-8")


# =========================================================
# Position → Acceleration → 업샘플링 파이프라인
# =========================================================
class BKAccFromPosPipeline:
    """
    Position .sto를 읽어 가속도 계산 후 지정 Hz로 업샘플링해 저장하는 파이프라인.
    """

    def __init__(
        self,
        set_time_to_zero: bool = False,
        output_fs_hz: int = 1000,
    ):
        self.set_time_to_zero = set_time_to_zero
        self.output_fs_hz = output_fs_hz

    def compute_acc_from_pos(self, df_pos: pd.DataFrame) -> pd.DataFrame:
        """Position DataFrame을 time 기준 2차 미분해 가속도 DataFrame을 반환합니다."""
        if "time" not in df_pos.columns:
            raise ValueError("time 컬럼이 없습니다.")

        df = df_pos.copy()
        time = df["time"].to_numpy(dtype=float)

        if self.set_time_to_zero:
            time = time - time[0]
            df["time"] = time

        if len(time) < 3:
            raise ValueError("미분하려면 최소 3개 이상의 time point가 필요합니다.")

        dt = np.diff(time)
        if np.any(dt <= 0):
            raise ValueError("time이 strictly increasing이 아닙니다.")

        out = pd.DataFrame({"time": df["time"].to_numpy(dtype=float)})

        for col in df.columns:
            if col == "time":
                continue
            y = df[col].to_numpy(dtype=float)
            vel = np.gradient(y, time, edge_order=2)
            acc = np.gradient(vel, time, edge_order=2)
            out[col] = acc

        return out

    def upsample_to_fs(self, df: pd.DataFrame) -> pd.DataFrame:
        """DataFrame의 time 기준으로 모든 컬럼을 output_fs_hz로 선형 보간 업샘플링합니다."""
        if "time" not in df.columns:
            raise ValueError("time 컬럼이 없습니다.")
        t_orig = df["time"].to_numpy(dtype=float)
        if len(t_orig) < 2:
            raise ValueError("업샘플링하려면 최소 2개 이상의 time point가 필요합니다.")

        t_min, t_max = t_orig[0], t_orig[-1]
        n_new = int(round((t_max - t_min) * self.output_fs_hz)) + 1
        t_new = np.linspace(t_min, t_max, n_new)

        cols_order = list(df.columns)
        out_data = {}
        for col in cols_order:
            y = df[col].to_numpy(dtype=float)
            f = interp1d(
                t_orig,
                y,
                kind="linear",
                bounds_error=False,
                fill_value=(y[0], y[-1]),
            )
            out_data[col] = f(t_new)

        return pd.DataFrame(out_data, columns=cols_order)

    def run(
        self,
        input_path: Path,
        output_path: Path,
    ) -> None:
        """
        시계열 파일(.trc, .mot, .sto, .csv, .tsv) 읽기 → 가속도 계산 → 업샘플링 후
        동일 포맷으로 저장합니다. time 컬럼이 있어야 합니다.
        """
        in_path = Path(input_path)
        out_path = Path(output_path)

        print(f"Reading: {in_path}")
        df_pos, meta = TimeSeriesStorage.read(in_path)

        if "time" not in df_pos.columns:
            raise ValueError("입력에 'time' 또는 'Time' 컬럼이 없습니다.")

        print("Columns:", len(df_pos.columns), "Rows:", len(df_pos))
        print("Time range:", df_pos["time"].iloc[0], "->", df_pos["time"].iloc[-1])

        print("Computing acceleration from position...")
        df_acc = self.compute_acc_from_pos(df_pos)

        print(f"Upsampling to {self.output_fs_hz}Hz...")
        df_upsampled = self.upsample_to_fs(df_acc)

        TimeSeriesStorage.write(out_path, df_upsampled, meta)
        print(f"\nSaved: {out_path} ({len(df_upsampled)} rows)")
        print("Done.")


# =========================================================
# 시간 기준 반분할 (.sto / .mot 공통)
# =========================================================
def split_storage_by_time_half(
    input_path: Path,
    output_dir: Path | None = None,
) -> Tuple[Path, Path]:
    """
    시계열 파일(.sto, .mot, .trc, .csv, .tsv)의 데이터를 시간 기준으로 반으로 나눕니다.
    예: 0~12초 → 1st: 0.000~6.000초, 2nd: 6.000~12.000초

    포맷별 헤더를 유지하며, 각 절반에 맞게 행 수·range 등을 갱신합니다.

    Parameters
    ----------
    input_path : Path
        입력 파일 경로
    output_dir : Path, optional
        저장 디렉터리. None이면 입력 파일과 같은 디렉터리에 저장합니다.

    Returns
    -------
    (path_1st_half, path_2nd_half) : Tuple[Path, Path]
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {input_path}")

    df, meta = TimeSeriesStorage.read(input_path)
    if "time" not in df.columns:
        raise ValueError("time 컬럼이 없습니다.")

    t = df["time"].to_numpy(dtype=float)
    t_min, t_max = t[0], t[-1]
    t_mid = (t_min + t_max) / 2.0

    df_1st = df[df["time"] < t_mid].copy()
    df_2nd = df[df["time"] >= t_mid].copy()

    if len(df_1st) == 0 or len(df_2nd) == 0:
        raise ValueError(
            f"반으로 나눈 뒤 한쪽에 행이 없습니다. time 범위: {t_min} ~ {t_max}"
        )

    suffix = input_path.suffix
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        base = output_dir / input_path.stem
    else:
        base = input_path.parent / input_path.stem
    out_1st = Path(f"{base}_1st_half{suffix}")
    out_2nd = Path(f"{base}_2nd_half{suffix}")

    TimeSeriesStorage.write(out_1st, df_1st, meta)
    TimeSeriesStorage.write(out_2nd, df_2nd, meta)

    return out_1st, out_2nd


# =========================================================
# Main
# =========================================================
def main(
    input_path: Path | None = None,
    output_path: Path | None = None,
    do_split_half: bool = True,
) -> None:
    """
    시계열 파일 → 가속도 계산 → 1000Hz 업샘플링 후 저장.
    do_split_half=True이면 저장된 파일을 시간 기준 반으로 분할합니다.
    """
    in_path = input_path if input_path is not None else POS_STO
    out_path = output_path if output_path is not None else OUT_STO_1000HZ

    pipeline = BKAccFromPosPipeline(set_time_to_zero=False, output_fs_hz=1000)
    pipeline.run(in_path, out_path)

    if do_split_half:
        print("Splitting into 1st half / 2nd half by time...")
        out_1st, out_2nd = split_storage_by_time_half(out_path)
        print(f"  {out_1st.name} ({out_1st})")
        print(f"  {out_2nd.name} ({out_2nd})")


if __name__ == "__main__":
    import argparse
    import sys

    if len(sys.argv) >= 3:
        parser = argparse.ArgumentParser(
            description="시계열 파일(.trc/.mot/.sto/.csv/.tsv) → 가속도 계산 → 1000Hz 업샘플링 후 저장"
        )
        parser.add_argument("input_path", type=Path, help="입력 시계열 파일")
        parser.add_argument("output_path", type=Path, help="출력 1000Hz 가속도 파일")
        parser.add_argument(
            "--no-split",
            action="store_true",
            help="반으로 분할하지 않음",
        )
        args = parser.parse_args()
        main(args.input_path, args.output_path, do_split_half=not args.no_split)
    else:
        main()
