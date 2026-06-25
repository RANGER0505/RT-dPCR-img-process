"""
RT-dPCR workflow v3: mode-aware + kinetic classification template.

This script is designed as the standard upgrade layer after workflow v2.
It does not replace image preprocessing, well detection, or curve extraction.
Instead, it consumes a v2-style workflow_result directory and produces a
single-experiment mode-aware + kinetic feature table.

Typical use:
    python workflow-template-v3-mode-aware-kinetic.py --base-dir "D:\\RT-dPCR IMG\\1210-4" --concentration-label 10^-4 --concentration-ng-ul 1e-4
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


CURVE_VALUE_COLUMN = "smoothed_plotted_value"
BASELINE_CYCLES = 6
EARLY_CYCLES = 8
LATE_CYCLES = 8
MIN_AMPLITUDE = 5.0

COLORS = {
    "positive": "#D73027",
    "negative": "#2C7BB6",
    "uncertain": "#9CA3AF",
    "rejected": "#F2D98D",
    "grid": "#D9DEE7",
}


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 8,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.9,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "legend.frameon": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


def key_xy(df: pd.DataFrame) -> pd.Series:
    return df["x"].round().astype(int).astype(str) + "_" + df["y"].round().astype(int).astype(str)


def robust_z(values) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    med = np.nanmedian(arr)
    mad = np.nanmedian(np.abs(arr - med))
    if not np.isfinite(mad) or mad < 1e-9:
        q75, q25 = np.nanpercentile(arr, [75, 25])
        mad = (q75 - q25) / 1.349
    if not np.isfinite(mad) or mad < 1e-9:
        mad = np.nanstd(arr)
    if not np.isfinite(mad) or mad < 1e-9:
        mad = 1.0
    return (arr - med) / (1.4826 * mad)


def linear_slope(x, y) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2:
        return np.nan
    x0 = x - np.mean(x)
    den = np.sum(x0 * x0)
    if den == 0:
        return np.nan
    return float(np.sum(x0 * (y - np.mean(y))) / den)


def longest_positive_run(diffs) -> int:
    best = 0
    current = 0
    for value in diffs:
        if value > 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def estimate_cq(cycles, y) -> float:
    cycles = np.asarray(cycles, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(y) < 12:
        return np.nan
    b_end = min(BASELINE_CYCLES, len(y))
    base = y[:b_end]
    baseline = float(np.mean(base))
    noise = float(np.std(base, ddof=1)) if len(base) > 1 else 0.0
    amplitude = float(np.nanmax(y) - np.nanmin(y))
    if amplitude < MIN_AMPLITUDE:
        return np.nan
    increment = max(4.0 * noise, 0.16 * amplitude, 0.8)
    increment = min(increment, 0.35 * amplitude)
    threshold = baseline + increment
    candidates = np.where(y >= threshold)[0]
    candidates = candidates[candidates >= max(2, b_end - 2)]
    if len(candidates) == 0:
        return np.nan
    idx = int(candidates[0])
    if idx == 0:
        return float(cycles[idx])
    x0, x1 = cycles[idx - 1], cycles[idx]
    y0, y1 = y[idx - 1], y[idx]
    if y1 == y0:
        return float(x1)
    return float(x0 + (threshold - y0) * (x1 - x0) / (y1 - y0))


def read_classification(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["xy_key"] = key_xy(df)
    if "classification" not in df.columns:
        raise ValueError(f"classification column not found: {path}")
    keep = ["xy_key", "x", "y", "classification"]
    for optional in ["well_id", "raw_intensity", "normalized_intensity"]:
        if optional in df.columns:
            keep.append(optional)
    return df[keep].drop_duplicates("xy_key")


def read_curve_file(path: Path, endpoint_label: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    usecols = ["x", "y", "cycle", CURVE_VALUE_COLUMN]
    df = pd.read_csv(path, usecols=usecols)
    df["endpoint_curve_source"] = endpoint_label
    df["xy_key"] = key_xy(df)
    return df


def read_curves(result_dir: Path) -> pd.DataFrame:
    parts = [
        read_curve_file(result_dir / "positive_well_curves.csv", "positive"),
        read_curve_file(result_dir / "negative_well_curves.csv", "negative"),
    ]
    curves = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    if curves.empty:
        raise ValueError(f"No positive/negative curve CSV files found in {result_dir}")
    return curves


def read_outlier_flags(result_dir: Path) -> pd.DataFrame:
    path = result_dir / "combined_curve_outliers.csv"
    if not path.exists():
        return pd.DataFrame(columns=["xy_key", "is_plot_outlier"])
    outliers = pd.read_csv(path)
    outliers["xy_key"] = key_xy(outliers)
    flag_cols = [
        col
        for col in ["is_curve_outlier", "is_early_cycle_outlier"]
        if col in outliers.columns
    ]
    if flag_cols:
        outliers["is_plot_outlier"] = outliers[flag_cols].fillna(False).any(axis=1)
    else:
        outliers["is_plot_outlier"] = True
    return outliers[["xy_key", "is_plot_outlier"]].drop_duplicates("xy_key")


def extract_features(curves: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for xy_key, group in curves.groupby("xy_key", sort=False):
        group = group.sort_values("cycle")
        cycles = group["cycle"].to_numpy(dtype=float)
        y = group[CURVE_VALUE_COLUMN].to_numpy(dtype=float)
        n = len(y)
        if n < 6:
            continue
        b = min(BASELINE_CYCLES, n)
        e = min(EARLY_CYCLES, n)
        l = min(LATE_CYCLES, n)
        baseline = float(np.mean(y[:b]))
        early_noise = float(np.std(y[:e], ddof=1)) if e > 1 else 0.0
        endpoint = float(np.mean(y[-3:]))
        late_mean = float(np.mean(y[-l:]))
        mid_start = min(b, n - 1)
        mid_end = max(mid_start + 1, min(n, int(n * 0.65)))
        mid_min = float(np.min(y[mid_start:mid_end]))
        diffs = np.diff(y)
        max_slope = float(np.max(diffs)) if len(diffs) else 0.0
        cycle_max_slope = float(cycles[1 + int(np.argmax(diffs))]) if len(diffs) else np.nan
        late_slope = linear_slope(cycles[-l:], y[-l:])
        full_slope = linear_slope(cycles, y)
        monotonic_frac = float(np.mean(diffs[b - 1 :] > 0)) if len(diffs[b - 1 :]) else 0.0
        rise_len = int(longest_positive_run(diffs[b - 1 :]))
        amplitude = float(np.max(y) - np.min(y))
        cq = estimate_cq(cycles, y)
        rows.append(
            {
                "xy_key": xy_key,
                "x": float(group["x"].iloc[0]),
                "y": float(group["y"].iloc[0]),
                "n_cycles": n,
                "baseline": baseline,
                "early_noise": early_noise,
                "endpoint_delta": endpoint - baseline,
                "late_delta": late_mean - baseline,
                "gain": late_mean - mid_min,
                "max_slope": max_slope,
                "cycle_max_slope": cycle_max_slope,
                "late_slope": late_slope,
                "full_slope": full_slope,
                "monotonic_frac": monotonic_frac,
                "rise_len": rise_len,
                "amplitude": amplitude,
                "cq": cq,
                "cq_valid": bool(np.isfinite(cq)),
            }
        )
    return pd.DataFrame(rows)


def add_robust_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    z_cols = [
        "endpoint_delta",
        "late_delta",
        "gain",
        "max_slope",
        "late_slope",
        "amplitude",
        "early_noise",
    ]
    for col in z_cols:
        df[f"{col}_rz"] = robust_z(df[col].to_numpy(dtype=float))

    cq = df["cq"].to_numpy(dtype=float)
    valid = np.isfinite(cq)
    cq_score = np.full(len(df), -1.0)
    if np.sum(valid) >= 5:
        cq_score[valid] = -robust_z(cq[valid])
    df["early_cq_score"] = cq_score
    df["kinetic_score"] = (
        0.95 * df["gain_rz"]
        + 0.80 * df["endpoint_delta_rz"]
        + 0.80 * df["max_slope_rz"]
        + 0.55 * df["late_slope_rz"]
        + 1.60 * (df["monotonic_frac"] - 0.50)
        + 0.35 * df["early_cq_score"]
        - 0.25 * np.maximum(df["early_noise_rz"], 0)
    )
    return df


def infer_occupancy_mode(before_fraction: float, total_wells: int) -> tuple[str, str]:
    if not np.isfinite(before_fraction) or total_wells <= 0:
        return "mixed", "fallback: invalid positive fraction"
    if before_fraction >= 0.97:
        return "saturated", "positive fraction >= 0.97"
    if before_fraction >= 0.70:
        return "high", "0.70 <= positive fraction < 0.97"
    if before_fraction <= 0.03:
        return "sparse", "positive fraction <= 0.03"
    return "mixed", "0.03 < positive fraction < 0.70"


def classify_with_kinetics(df: pd.DataFrame, occupancy_mode: str = "mixed") -> pd.DataFrame:
    df = df.copy()
    before_positive = df["classification_before"].eq("positive")
    enough_shape = (
        df["cq_valid"]
        & (df["amplitude"] >= MIN_AMPLITUDE)
        & (df["monotonic_frac"] >= 0.48)
        & (df["gain_rz"] > -0.5)
    )
    strong_kinetic = (
        enough_shape
        & (df["kinetic_score"] >= 8.0)
        & (df["gain_rz"] >= 4.0)
        & (df["max_slope_rz"] >= 2.0)
        & (df["monotonic_frac"] >= 0.65)
    )
    low_occupancy_rescue = (
        df["cq_valid"]
        & df["cq"].between(22.0, 39.0)
        & (df["gain_rz"] >= 3.0)
        & (df["endpoint_delta_rz"] >= 2.0)
        & (df["monotonic_frac"] >= 0.55)
        & (df["amplitude"] >= MIN_AMPLITUDE)
    )
    weak_kinetic = (
        enough_shape
        & (df["kinetic_score"] >= 2.0)
        & (df["gain_rz"] >= 1.0)
        & (df["max_slope_rz"] >= 0.5)
    )
    noise_like = (df["early_noise_rz"] >= 5.0) & (df["gain_rz"] < 1.0)
    strong_curve_contradiction = (
        (df["kinetic_score"] < -6.0)
        & (df["gain_rz"] < -2.0)
        & (df["max_slope_rz"] < -1.0)
        & (~df["cq_valid"])
    )

    if occupancy_mode == "saturated":
        after = np.full(len(df), "positive", dtype=object)
    elif occupancy_mode == "high":
        strong_negative = (
            (~before_positive)
            & (df["kinetic_score"] < -8.0)
            & (df["gain_rz"] < -3.0)
            & (df["max_slope_rz"] < -0.5)
        )
        after = np.where(strong_negative, "negative", "positive")
    else:
        after = np.where(before_positive, "positive", "negative")
        after = np.where((~before_positive) & low_occupancy_rescue, "positive", after)

    uncertain = (
        before_positive & (noise_like | strong_curve_contradiction | (~df["cq_valid"]))
    ) | ((~before_positive) & weak_kinetic & (~strong_kinetic))

    df["classification_after"] = after
    df["is_rescued"] = (~before_positive) & df["classification_after"].eq("positive")
    df["is_rejected"] = False
    df["is_uncertain"] = uncertain
    df["decision_status"] = np.where(df["is_rescued"], "rescued", "unchanged")
    df["decision_status"] = np.where(df["is_uncertain"], "uncertain", df["decision_status"])
    return df


def lambda_from_counts(pos: int, total: int) -> float:
    if total <= 0:
        return np.nan
    frac = pos / total
    if frac <= 0:
        return 0.0
    if frac >= 1:
        return np.inf
    return float(-np.log(1 - frac))


def experiment_offset_curves(curves: pd.DataFrame, early_cycles: int = 5) -> pd.DataFrame:
    curves = curves.copy().sort_values(["xy_key", "cycle"])
    min_cycle = curves.groupby("xy_key")["cycle"].transform("min")
    baseline_mask = curves["cycle"].le(min_cycle + early_cycles - 1)
    offset = float(curves.loc[baseline_mask, CURVE_VALUE_COLUMN].quantile(0.975))
    curves["experiment_upper_offset_value"] = offset
    curves["experiment_upper_offset_smoothed"] = curves[CURVE_VALUE_COLUMN] - offset
    curves["plot_cycle_zero"] = curves["cycle"] - curves["cycle"].min()
    return curves


def make_segments(df: pd.DataFrame, value_col: str = "experiment_upper_offset_smoothed") -> list[np.ndarray]:
    segments = []
    for _, group in df.sort_values(["xy_key", "cycle"]).groupby("xy_key", sort=False):
        xy = group[["plot_cycle_zero", value_col]].to_numpy(float)
        if len(xy) >= 2 and np.isfinite(xy).all():
            segments.append(xy)
    return segments


def downsample_wells(df: pd.DataFrame, max_wells: int, seed: int = 20260625) -> pd.DataFrame:
    keys = df["xy_key"].drop_duplicates().to_numpy()
    if len(keys) <= max_wells:
        return df
    rng = np.random.default_rng(seed)
    keep = set(rng.choice(keys, size=max_wells, replace=False))
    return df[df["xy_key"].isin(keep)].copy()


def plot_curves(curves: pd.DataFrame, out_dir: Path, title: str) -> None:
    curves = experiment_offset_curves(curves)
    fig, ax = plt.subplots(figsize=(4.6, 3.3))
    for call, color, alpha, zorder in [
        ("negative", COLORS["negative"], 0.22, 1),
        ("uncertain", COLORS["uncertain"], 0.32, 2),
        ("positive", COLORS["positive"], 0.36, 3),
    ]:
        if call == "uncertain":
            sub = curves[curves["is_uncertain"].astype(bool)]
        else:
            sub = curves[
                curves["classification_after"].eq(call)
                & ~curves["is_uncertain"].astype(bool)
            ]
        if sub.empty:
            continue
        sub = downsample_wells(sub, max_wells=1200)
        ax.add_collection(
            LineCollection(
                make_segments(sub),
                colors=color,
                linewidths=0.55 if call == "positive" else 0.45,
                alpha=alpha,
                rasterized=True,
                zorder=zorder,
            )
        )
    ax.autoscale()
    ax.margins(x=0.01, y=0.08)
    ax.axhline(0, color="#9aa4b2", lw=0.6, alpha=0.8)
    ax.grid(True, color=COLORS["grid"], lw=0.6, alpha=0.75)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Experiment-offset fluorescence (a.u.)")
    ax.legend(
        handles=[
            Line2D([0], [0], color=COLORS["positive"], lw=2, label="positive"),
            Line2D([0], [0], color=COLORS["negative"], lw=2, label="negative"),
            Line2D([0], [0], color=COLORS["uncertain"], lw=2, label="uncertain"),
        ],
        loc="upper left",
    )
    for ext in ("png", "svg", "pdf"):
        fig.savefig(out_dir / f"mode_aware_kinetic_curves.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_endpoint_map(features: pd.DataFrame, out_dir: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(4.6, 3.3))
    layers = [
        ("negative", features["classification_after"].eq("negative") & ~features["is_uncertain"].astype(bool), COLORS["negative"], 0.46, 2.0),
        ("uncertain", features["is_uncertain"].astype(bool), COLORS["uncertain"], 0.58, 2.3),
        ("positive", features["classification_after"].eq("positive") & ~features["is_uncertain"].astype(bool), COLORS["positive"], 0.68, 2.5),
    ]
    for _, mask, color, alpha, size in layers:
        sub = features[mask]
        if sub.empty:
            continue
        ax.scatter(sub["x"], sub["y"], s=size, c=color, alpha=alpha, linewidths=0, rasterized=True)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_xlabel("x (px)")
    ax.set_ylabel("y (px)")
    ax.set_aspect("equal", adjustable="box")
    ax.invert_yaxis()
    ax.grid(True, color=COLORS["grid"], lw=0.5, alpha=0.65)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(out_dir / f"mode_aware_kinetic_endpoint_map.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def resolve_classification_file(result_dir: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    candidates = [
        result_dir / "kmeans_classification.csv",
        result_dir / "all_positive_classification.csv",
        result_dir / "target_balanced_classification.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "No classification file found. Expected kmeans_classification.csv, "
        "all_positive_classification.csv, or target_balanced_classification.csv."
    )


def run(args) -> None:
    base_dir = Path(args.base_dir) if args.base_dir else None
    result_dir = Path(args.result_dir) if args.result_dir else base_dir / "workflow_result"
    out_dir = Path(args.out_dir) if args.out_dir else result_dir / "mode_aware_kinetic"
    out_dir.mkdir(parents=True, exist_ok=True)

    classification_file = resolve_classification_file(result_dir, args.classification_file)
    class_df = read_classification(classification_file)
    curves = read_curves(result_dir)
    features = extract_features(curves)
    merged = features.merge(class_df[["xy_key", "classification"]], on="xy_key", how="inner")
    merged["classification_before"] = merged["classification"].fillna("missing")
    merged = merged.drop(columns=["classification"])
    merged = add_robust_scores(merged)

    total = len(merged)
    before_pos = int(merged["classification_before"].eq("positive").sum())
    before_fraction = before_pos / total if total else np.nan
    inferred_mode, inferred_reason = infer_occupancy_mode(before_fraction, total)
    occupancy_mode = inferred_mode if args.occupancy_mode == "auto" else args.occupancy_mode
    occupancy_reason = inferred_reason if args.occupancy_mode == "auto" else f"manual override: {args.occupancy_mode}; auto would be {inferred_mode} ({inferred_reason})"

    merged = classify_with_kinetics(merged, occupancy_mode=occupancy_mode)
    outliers = read_outlier_flags(result_dir)
    merged = merged.merge(outliers, on="xy_key", how="left")
    merged["is_plot_outlier"] = merged["is_plot_outlier"].fillna(False).astype(bool)

    label = args.concentration_label or result_dir.parent.name
    merged["experiment_id"] = args.experiment_id or result_dir.parent.name
    merged["concentration_label"] = label
    merged["concentration_ng_uL"] = args.concentration_ng_ul
    merged["occupancy_mode"] = occupancy_mode
    merged["occupancy_source"] = args.occupancy_mode
    merged["auto_inferred_mode"] = inferred_mode
    merged["occupancy_reason"] = occupancy_reason
    merged["source_result_dir"] = str(result_dir)
    merged["source_classification_file"] = str(classification_file)

    after_pos = int(merged["classification_after"].eq("positive").sum())
    uncertain = int(merged["is_uncertain"].sum())
    included_total = int((~merged["is_uncertain"].astype(bool)).sum())
    included_pos = int(
        (merged["classification_after"].eq("positive") & ~merged["is_uncertain"].astype(bool)).sum()
    )
    summary = pd.DataFrame(
        [
            {
                "experiment_id": merged["experiment_id"].iloc[0],
                "concentration_label": label,
                "concentration_ng_uL": args.concentration_ng_ul,
                "n_wells_with_curves": total,
                "classification_file": str(classification_file),
                "before_positive": before_pos,
                "before_negative": int(merged["classification_before"].eq("negative").sum()),
                "before_fraction": before_fraction,
                "before_lambda": lambda_from_counts(before_pos, total),
                "auto_inferred_mode": inferred_mode,
                "occupancy_mode": occupancy_mode,
                "occupancy_reason": occupancy_reason,
                "after_positive": after_pos,
                "after_negative": int(merged["classification_after"].eq("negative").sum()),
                "after_fraction": after_pos / total if total else np.nan,
                "after_lambda": lambda_from_counts(after_pos, total),
                "uncertain": uncertain,
                "included_positive_excluding_uncertain": included_pos,
                "included_total_excluding_uncertain": included_total,
                "included_fraction_excluding_uncertain": included_pos / included_total if included_total else np.nan,
                "included_lambda_excluding_uncertain": lambda_from_counts(included_pos, included_total),
                "rescued_negative_to_positive": int(merged["is_rescued"].sum()),
                "median_cq_positive_after": float(np.nanmedian(merged.loc[merged["classification_after"].eq("positive"), "cq"])),
            }
        ]
    )

    feature_path = out_dir / "mode_aware_kinetic_feature_table.csv"
    summary_path = out_dir / "mode_aware_kinetic_summary.csv"
    merged.to_csv(feature_path, index=False)
    summary.to_csv(summary_path, index=False)

    curve_meta = merged[
        ["xy_key", "classification_after", "is_uncertain", "is_plot_outlier"]
    ]
    classified_curves = curves.merge(curve_meta, on="xy_key", how="inner")
    plot_title = f"{label} mode-aware + kinetic"
    plot_curves(classified_curves, out_dir, plot_title)
    plot_endpoint_map(merged, out_dir, plot_title)

    print(f"Feature table: {feature_path}")
    print(f"Summary: {summary_path}")
    print(f"Auto mode: {inferred_mode} ({inferred_reason})")
    print(f"Used mode: {occupancy_mode}")
    print(f"Before: {before_pos}/{total} positive")
    print(f"After: {after_pos}/{total} positive; uncertain={uncertain}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Upgrade v2 RT-dPCR workflow_result with mode-aware + kinetic classification."
    )
    parser.add_argument("--base-dir", help="Experiment base directory. Defaults result-dir to base-dir/workflow_result.")
    parser.add_argument("--result-dir", help="Existing v2 workflow_result directory.")
    parser.add_argument("--classification-file", help="Optional endpoint/kmeans classification CSV.")
    parser.add_argument("--out-dir", help="Output directory. Defaults to result-dir/mode_aware_kinetic.")
    parser.add_argument("--experiment-id", help="Experiment identifier stored in output tables.")
    parser.add_argument("--concentration-label", help="Display label such as 10^-4.")
    parser.add_argument("--concentration-ng-ul", type=float, help="Input concentration in ng/uL.")
    parser.add_argument(
        "--occupancy-mode",
        choices=["auto", "saturated", "high", "mixed", "sparse"],
        default="auto",
        help="Occupancy mode. Use auto for the standard template.",
    )
    args = parser.parse_args()
    if not args.base_dir and not args.result_dir:
        parser.error("Provide --base-dir or --result-dir.")
    return args


if __name__ == "__main__":
    run(parse_args())
