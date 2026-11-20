"""One-shot: SUB8 MeasuredEHF wrap_fbp vs normal SO/JR means. Delete after use."""
from __future__ import annotations
import collections
import glob
import json
import os
import re
import numpy as np
ROOT = r"c:\Users\ok\Documents\GitHub\BOX\OpenSim_Process\_Main_\Asymmetric\SUB8"
APP = "MeasuredEHF"
WRAP_MUSCLES = ["LTpT_T3_l", "LTpT_T3_r", "LTpT_T4_l", "LTpT_T4_r"]
JR_AX = {
    "fx": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fx",
    "fy": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fy",
    "fz": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fz",
}
CONDS = ["7kg_10bpm", "7kg_16bpm", "15kg_10bpm", "15kg_16bpm"]
GROUPS = ["normal", "wrap_fbp"]
OUT = (
    r"c:\Users\ok\Documents\GitHub\BOX\Analysis\Asymmetric\_diagnosis"
    r"\wrap_fbp\SUB8\tmp_wrap_vs_normal_stats.json"
)
def load_sto(path: str):
    lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip().lower() == "endheader")
    h = lines[i + 1].split("\t")
    d = np.loadtxt(lines[i + 2 :])
    if d.ndim == 1:
        d = d.reshape(1, -1)
    return h, d
def trial_mean(path: str, cols: list[str]) -> dict[str, float]:
    h, d = load_sto(path)
    out = {}
    for c in cols:
        if c in h:
            out[c] = float(np.mean(d[:, h.index(c)]))
    return out
def agg(rows: list[dict], key: str) -> list[dict]:
    out = []
    for c in CONDS:
        for g in GROUPS:
            vals = [
                r[key]
                for r in rows
                if r["condition"] == c and r["group"] == g and r.get(key) is not None
            ]
            if not vals:
                continue
            out.append(
                {
                    "condition": c,
                    "group": g,
                    "n": len(vals),
                    "mean": float(np.mean(vals)),
                    "sd": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
                }
            )
    return out
def main() -> None:
    rows_so: list[dict] = []
    rows_jr: list[dict] = []
    for force in glob.glob(
        os.path.join(ROOT, "**", f"SO_{APP}", "*_StaticOptimization_force.sto"),
        recursive=True,
    ):
        if "troubleshoot_so" in force or ".front" in force or ".back" in force:
            continue
        bn = os.path.basename(force)
        m = re.match(
            rf"SUB8_(.+)_(\d+[ABC]{{2}})_{APP}_StaticOptimization_force\.sto$", bn
        )
        if not m:
            continue
        cond, seg = m.group(1), m.group(2)
        wrap_model = os.path.join(
            os.path.dirname(force),
            "troubleshoot_so",
            "wrap_fbp",
            bn.replace("_StaticOptimization_force.sto", "_WrapFBP.osim"),
        )
        group = "wrap_fbp" if os.path.isfile(wrap_model) else "normal"
        try:
            mm = trial_mean(force, WRAP_MUSCLES)
        except Exception:
            continue
        if len(mm) < 4:
            continue
        rows_so.append(
            {
                "condition": cond,
                "segment": seg,
                "group": group,
                "wrap_sum_N": sum(mm.values()),
                **{f"{k}_N": v for k, v in mm.items()},
            }
        )
        jr = force.replace(f"SO_{APP}", f"JR_{APP}").replace(
            "_StaticOptimization_force.sto", "_JointReaction_ReactionLoads.sto"
        )
        if not os.path.isfile(jr):
            continue
        try:
            jm = trial_mean(jr, list(JR_AX.values()))
        except Exception:
            continue
        rows_jr.append(
            {
                "condition": cond,
                "segment": seg,
                "group": group,
                "fx": jm.get(JR_AX["fx"]),
                "fy": jm.get(JR_AX["fy"]),
                "fz": jm.get(JR_AX["fz"]),
            }
        )
    stats = {
        "wrap_sum_N": agg(rows_so, "wrap_sum_N"),
        "fx": agg(rows_jr, "fx"),
        "fy": agg(rows_jr, "fy"),
        "fz": agg(rows_jr, "fz"),
    }
    for mname in WRAP_MUSCLES:
        stats[mname] = agg(rows_so, f"{mname}_N")
    payload = {
        "scope": "SUB8 MeasuredEHF",
        "muscles": WRAP_MUSCLES,
        "jr_axes": JR_AX,
        "n_so": len(rows_so),
        "n_jr": len(rows_jr),
        "counts": {
            "so": dict(collections.Counter((r["group"], r["condition"]) for r in rows_so)),
            "jr": dict(collections.Counter((r["group"], r["condition"]) for r in rows_jr)),
        },
        "stats": stats,
    }
    # JSON keys must be strings
    payload["counts"]["so"] = {
        f"{g}|{c}": n for (g, c), n in collections.Counter(
            (r["group"], r["condition"]) for r in rows_so
        ).items()
    }
    payload["counts"]["jr"] = {
        f"{g}|{c}": n for (g, c), n in collections.Counter(
            (r["group"], r["condition"]) for r in rows_jr
        ).items()
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(payload, open(OUT, "w", encoding="utf-8"), indent=2)
    print("wrote", OUT)
    print("n_so", len(rows_so), "n_jr", len(rows_jr))
    for key in ["wrap_sum_N", "fx", "fy", "fz"]:
        print("==", key)
        for r in stats[key]:
            print(
                f"  {r['condition']:12} {r['group']:9} n={r['n']:2} "
                f"mean={r['mean']:8.1f} sd={r['sd']:7.1f}"
            )
    plot_cycle()


def cycle_curves(path: str, cols: list[str]) -> dict[str, np.ndarray]:
    h, d = load_sto(path)
    t = d[:, 0]
    tn = np.linspace(t[0], t[-1], 101)
    return {c: np.interp(tn, t, d[:, h.index(c)]) for c in cols if c in h}


def plot_cycle() -> None:
    import matplotlib.pyplot as plt

    curves: dict = collections.defaultdict(list)  # (var, cond, group) -> [101]
    for force in glob.glob(
        os.path.join(ROOT, "**", f"SO_{APP}", "*_StaticOptimization_force.sto"),
        recursive=True,
    ):
        if "troubleshoot_so" in force or ".front" in force or ".back" in force:
            continue
        bn = os.path.basename(force)
        m = re.match(rf"SUB8_(.+)_(\d+[ABC]{{2}})_{APP}_StaticOptimization_force\.sto$", bn)
        if not m:
            continue
        cond = m.group(1)
        wrap_model = os.path.join(
            os.path.dirname(force), "troubleshoot_so", "wrap_fbp",
            bn.replace("_StaticOptimization_force.sto", "_WrapFBP.osim"),
        )
        g = "wrap_fbp" if os.path.isfile(wrap_model) else "normal"
        try:
            so = cycle_curves(force, WRAP_MUSCLES)
        except Exception:
            continue
        if len(so) == 4:
            for k, v in so.items():
                curves[(k, cond, g)].append(v)
        jr = force.replace(f"SO_{APP}", f"JR_{APP}").replace(
            "_StaticOptimization_force.sto", "_JointReaction_ReactionLoads.sto"
        )
        if os.path.isfile(jr):
            try:
                jc = cycle_curves(jr, list(JR_AX.values()))
            except Exception:
                continue
            for ax_name, col in JR_AX.items():
                if col in jc:
                    curves[(ax_name, cond, g)].append(jc[col])

    x = np.arange(101)
    colors = {"normal": "tab:blue", "wrap_fbp": "tab:orange"}
    labels = {"normal": "Normal SO", "wrap_fbp": "Wrap→FBP SO"}
    for title, vars_ in [("LTpT muscle force (N)", WRAP_MUSCLES), ("L5/S1 JR (N)", list(JR_AX))]:
        fig, axes = plt.subplots(len(vars_), len(CONDS), figsize=(4.2 * len(CONDS), 2.6 * len(vars_)),
                                 sharex=True, squeeze=False)
        for i, v in enumerate(vars_):
            for j, c in enumerate(CONDS):
                ax = axes[i, j]
                for g in GROUPS:
                    arr = np.array(curves.get((v, c, g), []))
                    if not len(arr):
                        continue
                    for tr in arr:
                        ax.plot(x, tr, color=colors[g], lw=0.4, alpha=0.5)
                    mu, sd = arr.mean(0), arr.std(0, ddof=1) if len(arr) > 1 else np.zeros(101)
                    ax.plot(x, mu, color=colors[g], label=f"{labels[g]} (n={len(arr)})")
                    ax.fill_between(x, mu - sd, mu + sd, color=colors[g], alpha=0.25)
                ax.legend(fontsize=7)
                if i == 0:
                    ax.set_title(c)
                if j == 0:
                    ax.set_ylabel(v)
                if i == len(vars_) - 1:
                    ax.set_xlabel("Lifting cycle (%)")
        fig.suptitle(f"SUB8 MeasuredEHF — {title}, mean ± SD")
        fig.tight_layout()
        tag = "muscle" if vars_ is WRAP_MUSCLES else "jr"
        fig.savefig(OUT.replace(".json", f"_cycle_{tag}.png"), dpi=110)
    plt.show()


def plot(stats: dict) -> None:
    import matplotlib.pyplot as plt

    panels = [(m, f"{m} (N)") for m in WRAP_MUSCLES] + [("wrap_sum_N", "LTpT T3+T4 sum (N)")]
    panels += [(a, f"L5/S1 {a} (N)") for a in ("fx", "fy", "fz")]
    colors = {"normal": "tab:blue", "wrap_fbp": "tab:orange"}
    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    x = np.arange(len(CONDS))
    w = 0.38
    for ax, (key, title) in zip(axes.flat, panels):
        for gi, g in enumerate(GROUPS):
            recs = {r["condition"]: r for r in stats[key] if r["group"] == g}
            means = [recs[c]["mean"] if c in recs else np.nan for c in CONDS]
            sds = [recs[c]["sd"] if c in recs else 0.0 for c in CONDS]
            ns = [recs[c]["n"] if c in recs else 0 for c in CONDS]
            xs = x + (gi - 0.5) * w
            ax.bar(xs, means, w, yerr=sds, capsize=3, color=colors[g],
                   label="Normal SO" if g == "normal" else "Wrap→FBP SO")
            for xi, mu, n in zip(xs, means, ns):
                if n:
                    ax.text(xi, 0, f"n={n}", ha="center", va="bottom", fontsize=7)
        ax.set_xticks(x, CONDS, fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.axhline(0, color="k", lw=0.5)
    axes.flat[0].legend(fontsize=8)
    fig.suptitle("SUB8 MeasuredEHF: normal vs wrap→FBP (trial-mean, mean ± SD)")
    fig.tight_layout()
    png = OUT.replace(".json", ".png")
    # fig.savefig(png, dpi=120)
    print("wrote", png)
    plt.show()
if __name__ == "__main__":
    main()