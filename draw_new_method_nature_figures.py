import os
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


BASE = Path(r"D:\RT-dPCR IMG\group")
FEATURE_TABLE = BASE / "kinetic_classifier_exploration" / "auto_well_kinetic_feature_table.csv"
OUT = BASE / "kinetic_classifier_exploration" / "new_method_nature_figures"
if os.environ.get("RT_DPCR_FEATURE_TABLE"):
    FEATURE_TABLE = Path(os.environ["RT_DPCR_FEATURE_TABLE"])
if os.environ.get("RT_DPCR_FIGURE_OUT"):
    OUT = Path(os.environ["RT_DPCR_FIGURE_OUT"])

EXPERIMENTS = [
    {
        "label": "10^-2",
        "title": r"$10^{-2}$ ng $\mu$L$^{-1}$",
        "curve_dir": BASE / "10-2" / "workflow_result",
        "outlier_file": BASE / "10-2" / "workflow_result" / "all_positive_curve_outliers.csv",
    },
    {
        "label": "10^-3",
        "title": r"$10^{-3}$ ng $\mu$L$^{-1}$",
        "curve_dir": BASE / "10-3" / "workflow_result_early_blob_filter",
        "outlier_file": BASE / "10-3" / "workflow_result_early_blob_filter" / "combined_curve_outliers.csv",
    },
    {
        "label": "10^-4",
        "title": r"$10^{-4}$ ng $\mu$L$^{-1}$",
        "curve_dir": BASE / "10-4" / "workflow_result",
        "outlier_file": BASE / "10-4" / "workflow_result" / "combined_curve_outliers.csv",
    },
    {
        "label": "10^-5",
        "title": r"$10^{-5}$ ng $\mu$L$^{-1}$",
        "curve_dir": BASE / "10-5" / "workflow_result",
        "outlier_file": BASE / "10-5" / "workflow_result" / "combined_curve_outliers.csv",
    },
]

COLORS = {
    "positive": "#D73027",
    "negative": "#2C7BB6",
    "uncertain": "#9CA3AF",
    "rejected": "#F2D98D",
}


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 7,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.8,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "legend.frameon": False,
    }
)


def save_pub(fig, stem, dpi=600):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(OUT / f"{stem}.svg", bbox_inches="tight")
    fig.savefig(OUT / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{stem}.tiff", dpi=dpi, bbox_inches="tight")


def key_from_xy(df):
    return df["x"].round().astype(int).astype(str) + "_" + df["y"].round().astype(int).astype(str)


def read_curve_table(curve_dir):
    parts = []
    for name in ("positive_well_curves.csv", "negative_well_curves.csv"):
        path = curve_dir / name
        if path.exists():
            usecols = ["x", "y", "cycle", "image_name", "raw_intensity", "smoothed_plotted_value"]
            df = pd.read_csv(path, usecols=usecols)
            df["xy_key"] = key_from_xy(df)
            parts.append(df)
    if not parts:
        raise FileNotFoundError(f"No curve files found in {curve_dir}")
    return pd.concat(parts, ignore_index=True)


def read_outlier_flags(path):
    if not path.exists():
        return pd.DataFrame(columns=["xy_key", "is_plot_outlier"])
    outliers = pd.read_csv(path)
    outliers["xy_key"] = key_from_xy(outliers)
    flag_cols = [
        c
        for c in ["is_hidden", "is_curve_outlier", "is_early_cycle_outlier", "is_late_drop_outlier"]
        if c in outliers.columns
    ]
    if flag_cols:
        outliers["is_plot_outlier"] = outliers[flag_cols].fillna(False).any(axis=1)
    else:
        outliers["is_plot_outlier"] = True
    return outliers[["xy_key", "is_plot_outlier"]].drop_duplicates("xy_key")


def add_experiment_upper_offset(curves, early_cycles=5, upper_quantile=0.975):
    curves = curves.copy()
    curves = curves.sort_values(["xy_key", "cycle"])
    min_cycle = curves.groupby("xy_key")["cycle"].transform("min")
    baseline_mask = curves["cycle"].le(min_cycle + early_cycles - 1)
    offset = float(curves.loc[baseline_mask, "smoothed_plotted_value"].quantile(upper_quantile))
    curves["experiment_upper_offset_value"] = offset
    curves["experiment_upper_offset_smoothed"] = curves["smoothed_plotted_value"] - offset
    return curves


def build_source_data():
    features = pd.read_csv(
        FEATURE_TABLE,
        usecols=[
            "concentration_label",
            "xy_key",
            "x",
            "y",
            "classification_after",
            "classification_before",
            "is_rescued",
            "is_rejected",
            "is_uncertain",
            "decision_status",
            "cq",
            "kinetic_score",
        ],
    )
    features["xy_key"] = features["xy_key"].astype(str)

    curve_tables = {}
    endpoint_tables = []
    summary_rows = []

    for exp in EXPERIMENTS:
        label = exp["label"]
        f = features[features["concentration_label"].eq(label)].copy()
        curves = read_curve_table(exp["curve_dir"])
        curves = curves.merge(
            f[
                [
                    "xy_key",
                    "classification_after",
                    "classification_before",
                    "is_rescued",
                    "is_rejected",
                    "is_uncertain",
                    "decision_status",
                    "cq",
                    "kinetic_score",
                ]
            ],
            on="xy_key",
            how="inner",
        )
        outlier_flags = read_outlier_flags(exp["outlier_file"])
        curves = curves.merge(outlier_flags, on="xy_key", how="left")
        curves["is_plot_outlier"] = curves["is_plot_outlier"].fillna(False).astype(bool)
        curves = curves.rename(columns={"classification_after": "final_call"})
        curves = add_experiment_upper_offset(curves)
        curve_tables[label] = curves

        last_cycle = curves["cycle"].max()
        endpoint = curves[curves["cycle"].eq(last_cycle)].copy()
        endpoint_tables.append(endpoint.assign(concentration_label=label))

        n_pos = int(f["classification_after"].eq("positive").sum())
        n_neg = int(f["classification_after"].eq("negative").sum())
        summary_rows.append(
            {
                "concentration_label": label,
                "positive_wells": n_pos,
                "negative_wells": n_neg,
                "total_wells": n_pos + n_neg,
                "positive_fraction": n_pos / (n_pos + n_neg),
                "last_cycle": int(last_cycle),
            }
        )

    endpoint_all = pd.concat(endpoint_tables, ignore_index=True)
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "new_method_positive_negative_summary.csv", index=False)
    endpoint_all[
        [
            "concentration_label",
            "xy_key",
            "x",
            "y",
            "cycle",
            "raw_intensity",
            "smoothed_plotted_value",
            "experiment_upper_offset_value",
            "experiment_upper_offset_smoothed",
            "final_call",
            "classification_before",
            "is_rescued",
            "is_rejected",
            "is_uncertain",
            "decision_status",
            "is_plot_outlier",
            "cq",
            "kinetic_score",
        ]
    ].to_csv(OUT / "new_method_endpoint_source_data.csv", index=False)
    return curve_tables, summary


def downsample_wells(df, max_wells=900):
    keys = df["xy_key"].drop_duplicates().to_numpy()
    if len(keys) <= max_wells:
        return df
    rng = np.random.default_rng(20260624)
    keep = set(rng.choice(keys, size=max_wells, replace=False))
    return df[df["xy_key"].isin(keep)].copy()


def make_segments(df, value_col="experiment_upper_offset_smoothed"):
    segments = []
    for _, g in df.sort_values(["xy_key", "cycle"]).groupby("xy_key", sort=False):
        xy = g[["cycle", value_col]].to_numpy(float)
        if len(xy) >= 2 and np.isfinite(xy).all():
            segments.append(xy)
    return segments


def draw_curve_panel(ax, curves, title, summary_row):
    rejected = curves[curves["is_plot_outlier"].astype(bool)].copy()
    rejected = downsample_wells(rejected, max_wells=300)
    if not rejected.empty:
        lc = LineCollection(
            make_segments(rejected),
            colors=COLORS["rejected"],
            linewidths=0.34,
            alpha=0.22,
            rasterized=True,
            zorder=1,
        )
        ax.add_collection(lc)

    for call in ("negative", "positive"):
        sub = curves[curves["final_call"].eq(call) & ~curves["is_plot_outlier"].astype(bool)]
        if sub.empty:
            continue
        sub = downsample_wells(sub, max_wells=900)
        segments = make_segments(sub)
        lc = LineCollection(
            segments,
            colors=COLORS[call],
            linewidths=0.48 if call == "positive" else 0.44,
            alpha=0.22 if call == "positive" else 0.20,
            rasterized=True,
            zorder=1 if call == "negative" else 2,
        )
        ax.add_collection(lc)

    ax.autoscale()
    ax.margins(x=0.01, y=0.08)
    ax.axhline(0, color="#9aa4b2", lw=0.55, alpha=0.7, zorder=0)
    ax.grid(True, color="#d8dee8", lw=0.6, alpha=0.75)
    ax.set_title(title, loc="left", pad=3, fontweight="bold")
    ax.text(
        0.98,
        0.05,
        f"pos {int(summary_row.positive_wells):,} / {int(summary_row.total_wells):,}\n"
        f"{summary_row.positive_fraction:.3f}",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color="#253142",
        fontsize=6.8,
    )


def draw_curve_panel_ten4_uncertain(ax, curves, title, summary_row):
    rejected = curves[curves["is_plot_outlier"].astype(bool)].copy()
    rejected = downsample_wells(rejected, max_wells=300)
    if not rejected.empty:
        ax.add_collection(
            LineCollection(
                make_segments(rejected),
                colors=COLORS["rejected"],
                linewidths=0.34,
                alpha=0.22,
                rasterized=True,
                zorder=1,
            )
        )

    uncertain_keys = set(curves.loc[curves["is_uncertain"].astype(bool), "xy_key"].astype(str).unique())
    uncertain = curves[
        curves["xy_key"].astype(str).isin(uncertain_keys)
        & ~curves["is_plot_outlier"].astype(bool)
    ].copy()
    if not uncertain.empty:
        uncertain = downsample_wells(uncertain, max_wells=900)
        ax.add_collection(
            LineCollection(
                make_segments(uncertain),
                colors=COLORS["uncertain"],
                linewidths=0.52,
                alpha=0.36,
                rasterized=True,
                zorder=2,
            )
        )

    for call in ("negative", "positive"):
        sub = curves[curves["final_call"].eq(call) & ~curves["is_plot_outlier"].astype(bool)].copy()
        if uncertain_keys:
            sub = sub[~sub["xy_key"].astype(str).isin(uncertain_keys)]
        if sub.empty:
            continue
        sub = downsample_wells(sub, max_wells=900)
        ax.add_collection(
            LineCollection(
                make_segments(sub),
                colors=COLORS[call],
                linewidths=0.48 if call == "positive" else 0.44,
                alpha=0.22 if call == "positive" else 0.20,
                rasterized=True,
                zorder=1 if call == "negative" else 3,
            )
        )

    ax.autoscale()
    ax.margins(x=0.01, y=0.08)
    ax.axhline(0, color="#9aa4b2", lw=0.55, alpha=0.7, zorder=0)
    ax.grid(True, color="#d8dee8", lw=0.6, alpha=0.75)
    ax.set_title(title, loc="left", pad=3, fontweight="bold")

    well_level = curves.drop_duplicates("xy_key")
    n_uncertain = len(uncertain_keys)
    n_positive = int(
        (
            well_level["final_call"].eq("positive")
            & ~well_level["is_uncertain"].astype(bool)
        ).sum()
    )
    n_total = int(len(well_level) - n_uncertain)
    ax.text(
        0.98,
        0.05,
        f"pos {n_positive:,} / {n_total:,}\nuncertain {n_uncertain:,}",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color="#253142",
        fontsize=6.8,
    )


def plot_curves(curve_tables, summary):
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.2), sharex=False, sharey=True)
    for ax, exp in zip(axes.flat, EXPERIMENTS):
        label = exp["label"]
        row = summary[summary["concentration_label"].eq(label)].iloc[0]
        draw_curve_panel(ax, curve_tables[label], exp["title"], row)
    for ax in axes[:, 0]:
        ax.set_ylabel("Experiment-offset fluorescence (a.u.)")
    for ax in axes[1, :]:
        ax.set_xlabel("Cycle")
    handles = [
        Line2D([0], [0], color=COLORS["positive"], lw=2, label="positive"),
        Line2D([0], [0], color=COLORS["negative"], lw=2, label="negative"),
        Line2D([0], [0], color=COLORS["rejected"], lw=2, alpha=0.7, label="rejected"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=3, bbox_to_anchor=(0.54, 1.02))
    fig.suptitle("Real-time dPCR amplification curves classified by the mode-aware kinetic method", y=1.045, fontsize=9, fontweight="bold")
    fig.subplots_adjust(wspace=0.12, hspace=0.23)
    save_pub(fig, "nature_new_method_positive_negative_curves")
    plt.close(fig)


def plot_curves_ten4_uncertain(curve_tables, summary):
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.2), sharex=False, sharey=True)
    audit_rows = []
    for ax, exp in zip(axes.flat, EXPERIMENTS):
        label = exp["label"]
        row = summary[summary["concentration_label"].eq(label)].iloc[0]
        if label == "10^-4":
            curves = curve_tables[label]
            draw_curve_panel_ten4_uncertain(ax, curves, exp["title"], row)
            audit = curves.drop_duplicates("xy_key")[
                ["xy_key", "final_call", "is_uncertain", "is_plot_outlier"]
            ].copy()
            audit["display_call"] = audit["final_call"]
            audit.loc[audit["is_uncertain"].astype(bool), "display_call"] = "uncertain"
            audit_rows.append(audit.assign(concentration_label=label))
        else:
            draw_curve_panel(ax, curve_tables[label], exp["title"], row)
    for ax in axes[:, 0]:
        ax.set_ylabel("Experiment-offset fluorescence (a.u.)")
    for ax in axes[1, :]:
        ax.set_xlabel("Cycle")
    handles = [
        Line2D([0], [0], color=COLORS["positive"], lw=2, label="positive"),
        Line2D([0], [0], color=COLORS["negative"], lw=2, label="negative"),
        Line2D([0], [0], color=COLORS["uncertain"], lw=2, label="uncertain (10^-4)"),
        Line2D([0], [0], color=COLORS["rejected"], lw=2, alpha=0.7, label="rejected"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=4, bbox_to_anchor=(0.54, 1.02))
    fig.suptitle(
        "Real-time dPCR amplification curves classified by the mode-aware kinetic method",
        y=1.045,
        fontsize=9,
        fontweight="bold",
    )
    fig.subplots_adjust(wspace=0.12, hspace=0.23)
    save_pub(fig, "nature_new_method_positive_negative_curves_ten4_uncertain")
    plt.close(fig)

    if audit_rows:
        pd.concat(audit_rows, ignore_index=True).to_csv(
            OUT / "ten4_uncertain_overlay_audit.csv",
            index=False,
        )


def draw_endpoint_panel(ax, endpoint, title, summary_row):
    neg = endpoint[endpoint["final_call"].eq("negative")]
    pos = endpoint[endpoint["final_call"].eq("positive")]
    if not neg.empty:
        ax.scatter(
            neg["x"],
            neg["y"],
            s=2.0,
            c=COLORS["negative"],
            alpha=0.46,
            linewidths=0,
            rasterized=True,
            label="negative",
        )
    if not pos.empty:
        ax.scatter(
            pos["x"],
            pos["y"],
            s=2.6,
            c=COLORS["positive"],
            alpha=0.72,
            linewidths=0,
            rasterized=True,
            label="positive",
        )
    ax.set_aspect("equal", adjustable="box")
    ax.invert_yaxis()
    ax.set_title(title, loc="left", pad=3, fontweight="bold")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(
        0.02,
        0.98,
        f"+ {int(summary_row.positive_wells):,}\n- {int(summary_row.negative_wells):,}",
        transform=ax.transAxes,
        ha="left",
        va="top",
        color="#253142",
        fontsize=6.8,
        bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor="none", alpha=0.82),
    )


def plot_endpoint_maps(curve_tables, summary):
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.15))
    for ax, exp in zip(axes.flat, EXPERIMENTS):
        label = exp["label"]
        curves = curve_tables[label]
        endpoint = curves[curves["cycle"].eq(curves["cycle"].max())].copy()
        row = summary[summary["concentration_label"].eq(label)].iloc[0]
        draw_endpoint_panel(ax, endpoint, exp["title"], row)
    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=COLORS["positive"], markersize=5, label="positive"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=COLORS["negative"], markersize=5, label="negative"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=2, bbox_to_anchor=(0.54, 1.02))
    fig.suptitle("Endpoint well map after mode-aware kinetic classification", y=1.045, fontsize=9, fontweight="bold")
    fig.subplots_adjust(wspace=0.04, hspace=0.18)
    save_pub(fig, "nature_new_method_endpoint_well_maps")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    curve_tables, summary = build_source_data()
    plot_curves(curve_tables, summary)
    plot_curves_ten4_uncertain(curve_tables, summary)
    plot_endpoint_maps(curve_tables, summary)
    print(OUT)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
