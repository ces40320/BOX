"""I/O helpers for OpenSim .sto/.mot and Analysis CSV outputs."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

_THIS = os.path.dirname(os.path.abspath(__file__))
_CODES = os.path.dirname(os.path.dirname(_THIS))
if _CODES not in sys.path:
    sys.path.insert(0, _CODES)


def read_opensim_storage(path: str | Path) -> Tuple[pd.DataFrame, dict]:
    """Read OpenSim Storage (.sto/.mot) with endheader."""
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    end_idx = next(i for i, line in enumerate(lines) if "endheader" in line.lower())
    j = end_idx + 1
    while j < len(lines) and not lines[j].strip():
        j += 1

    columns = lines[j].strip().split()
    rows = [ln.strip().split() for ln in lines[j + 1 :] if ln.strip()]
    df = pd.DataFrame(rows, columns=columns).apply(pd.to_numeric, errors="coerce")
    df = df.dropna(how="all")
    if "Time" in df.columns and "time" not in df.columns:
        df = df.rename(columns={"Time": "time"})

    meta = {
        "path": str(path),
        "header_lines": lines[: end_idx + 1],
        "blank_lines_after_header": lines[end_idx + 1 : j],
        "column_line": lines[j],
        "columns": list(df.columns),
    }
    return df, meta


def write_opensim_storage(
    path: str | Path,
    df: pd.DataFrame,
    meta: dict,
    float_fmt: str = "%.8f",
) -> None:
    """Write OpenSim Storage using template meta headers when available."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    with path.open("w", encoding="utf-8") as f:
        for line in meta.get("header_lines", ["nRows=0\nnColumns=0\nendheader\n"]):
            # refresh nRows / nColumns if present
            low = line.lower()
            if low.startswith("nrows"):
                f.write(f"nRows={len(out)}\n")
            elif low.startswith("ncolumns") or low.startswith("datacolumns"):
                key = line.split("=")[0] if "=" in line else line.split()[0]
                if "=" in line:
                    f.write(f"{key}={out.shape[1]}\n")
                else:
                    f.write(f"{key}\t{out.shape[1]}\n")
            else:
                f.write(line if line.endswith("\n") else line + "\n")
        f.write("\t".join(map(str, out.columns)) + "\n")
        out.to_csv(
            f,
            sep="\t",
            index=False,
            header=False,
            float_format=float_fmt,
            lineterminator="\n",
        )


def write_mot_simple(path: str | Path, time_s: np.ndarray, columns: Dict[str, np.ndarray]) -> None:
    """Write a minimal OpenSim MOT (no template)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    names = list(columns.keys())
    arr = np.column_stack([time_s] + [np.asarray(columns[n], dtype=float) for n in names])
    with path.open("w", encoding="utf-8") as f:
        f.write(f"name {path.name}\n")
        f.write(f"nRows={arr.shape[0]}\n")
        f.write(f"nColumns={arr.shape[1]}\n")
        f.write("inDegrees=no\n")
        f.write("endheader\n")
        f.write("time\t" + "\t".join(names) + "\n")
        for row in arr:
            f.write("\t".join(f"{v:.8f}" for v in row) + "\n")


def flatten_extload_columns(ext: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Expand f/p/m × plates 1..4 into OpenSim ExtLoad scalar columns."""
    if "time" not in ext:
        raise KeyError("ext must include 'time'")
    n = len(ext["time"])

    def _vec3(key: str) -> np.ndarray:
        v = ext.get(key)
        if v is None:
            return np.zeros((n, 3), dtype=float)
        a = np.asarray(v, dtype=float)
        if a.shape != (n, 3):
            raise ValueError(f"{key}: expected ({n},3), got {a.shape}")
        return a

    out: Dict[str, np.ndarray] = {}

    def _add(plate: int, force_prefix: str, torque_prefix: str) -> None:
        f_ = _vec3(f"f{plate}")
        p_ = _vec3(f"p{plate}")
        m_ = _vec3(f"m{plate}")
        for i, ax in enumerate(("x", "y", "z")):
            out[f"{force_prefix}_v{ax}"] = f_[:, i].copy()
        for i, ax in enumerate(("x", "y", "z")):
            out[f"{force_prefix}_p{ax}"] = p_[:, i].copy()
        for i, ax in enumerate(("x", "y", "z")):
            out[f"{torque_prefix}_{ax}"] = m_[:, i].copy()

    for plate in (1, 2):
        _add(plate, f"ground_force{plate}", f"ground_torque{plate}")
    for plate in (3, 4):
        _add(plate, f"hand_force{plate}", f"hand_torque{plate}")
    return out


def write_extload_mot(path: str | Path, ext: Dict[str, np.ndarray]) -> None:
    write_mot_simple(path, np.asarray(ext["time"], float), flatten_extload_columns(ext))


def mot_df_to_ext_dict(df: pd.DataFrame) -> Dict[str, np.ndarray]:
    """Inverse of flatten: MOT dataframe → f/p/m dict."""
    n = len(df)
    out: Dict[str, np.ndarray] = {"time": df["time"].to_numpy(dtype=float)}

    def _pack(force_prefix: str, torque_prefix: str, plate: int) -> None:
        f = np.zeros((n, 3), dtype=float)
        p = np.zeros((n, 3), dtype=float)
        m = np.zeros((n, 3), dtype=float)
        for i, ax in enumerate(("x", "y", "z")):
            fc = f"{force_prefix}_v{ax}"
            pc = f"{force_prefix}_p{ax}"
            mc = f"{torque_prefix}_{ax}"
            if fc in df.columns:
                f[:, i] = df[fc].to_numpy(dtype=float)
            if pc in df.columns:
                p[:, i] = df[pc].to_numpy(dtype=float)
            if mc in df.columns:
                m[:, i] = df[mc].to_numpy(dtype=float)
        out[f"f{plate}"] = f
        out[f"p{plate}"] = p
        out[f"m{plate}"] = m

    _pack("ground_force1", "ground_torque1", 1)
    _pack("ground_force2", "ground_torque2", 2)
    _pack("hand_force3", "hand_torque3", 3)
    _pack("hand_force4", "hand_torque4", 4)
    return out


def save_csv(path: str | Path, df: pd.DataFrame) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return str(path)


def extract_residual(
    df: pd.DataFrame,
    *,
    prefer: str = "id",
    id_col: str = "pelvis_ty_force",
    so_col: str = "residual_pelvis_ty",
) -> Tuple[np.ndarray, np.ndarray, str]:
    """Return (time, residual, source_tag)."""
    t = df["time"].to_numpy(dtype=float)
    if prefer == "id" and id_col in df.columns:
        return t, df[id_col].to_numpy(dtype=float), f"id:{id_col}"
    if so_col in df.columns:
        return t, df[so_col].to_numpy(dtype=float), f"so:{so_col}"
    if id_col in df.columns:
        return t, df[id_col].to_numpy(dtype=float), f"id:{id_col}"
    raise KeyError(
        f"Neither {id_col!r} nor {so_col!r} found in columns: {list(df.columns)[:20]}..."
    )
