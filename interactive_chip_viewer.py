import argparse
import csv
import json
import os
from collections import defaultdict


BASE_DIR = r"D:\RT-dPCR IMG\1210-4"
RESULT_DIR = os.path.join(BASE_DIR, "workflow_result")

CURVE_SMOOTH_WINDOW = 5
POSITIVE_COMBINED_SHRINK_FACTOR = 0.75
NEGATIVE_COMBINED_SMOOTH_WINDOW = 11
NEGATIVE_COMBINED_SHRINK_FACTOR = 0.60


def read_csv_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def moving_average(values, window_size):
    if window_size <= 1 or len(values) <= 2:
        return list(values)
    half = window_size // 2
    smoothed = []
    for index in range(len(values)):
        start = max(0, index - half)
        end = min(len(values), index + half + 1)
        smoothed.append(sum(values[start:end]) / (end - start))
    return smoothed


def median(values):
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        return 0.0
    mid = count // 2
    if count % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def shrink_curves(curves, shrink_factor):
    if not curves:
        return curves
    cycle_count = len(next(iter(curves.values())))
    center = [median([curve[i] for curve in curves.values()]) for i in range(cycle_count)]
    return {
        key: [center[i] + shrink_factor * (value - center[i]) for i, value in enumerate(curve)]
        for key, curve in curves.items()
    }


def load_curve_file(path, group):
    curves = {}
    meta = {}
    cycles = []
    grouped = defaultdict(list)
    for row in read_csv_rows(path):
        well_key = f"{group}:{row['well_id']}"
        grouped[well_key].append(row)

    for well_key, rows in grouped.items():
        rows.sort(key=lambda row: int(row["cycle"]))
        curves[well_key] = [float(row["smoothed_plotted_value"]) for row in rows]
        first = rows[0]
        meta[well_key] = {
            "x": float(first["x"]),
            "y": float(first["y"]),
            "curveWellId": int(first["well_id"]),
            "group": group,
        }
        if len(rows) > len(cycles):
            cycles = [int(row["cycle"]) for row in rows]
    return curves, meta, cycles


def build_viewer_data(result_dir):
    stage_rows = read_csv_rows(os.path.join(result_dir, "stage2_detail.csv"))
    class_rows = read_csv_rows(os.path.join(result_dir, "kmeans_classification.csv"))
    outlier_rows = read_csv_rows(os.path.join(result_dir, "combined_curve_outliers.csv"))

    class_by_xy = {
        (int(float(row["x"])), int(float(row["y"]))): row
        for row in class_rows
    }
    outlier_by_key = {
        f"{row['group']}:{row['well_id']}": row
        for row in outlier_rows
    }

    negative_curves, negative_meta, neg_cycles = load_curve_file(
        os.path.join(result_dir, "negative_well_curves.csv"),
        "negative",
    )
    positive_curves, positive_meta, pos_cycles = load_curve_file(
        os.path.join(result_dir, "positive_well_curves.csv"),
        "positive",
    )
    cycles = neg_cycles if len(neg_cycles) >= len(pos_cycles) else pos_cycles
    curve_key_by_xy = {}
    curve_meta_by_key = {}
    for key, item in {**negative_meta, **positive_meta}.items():
        xy = (int(round(item["x"])), int(round(item["y"])))
        curve_key_by_xy[xy] = key
        curve_meta_by_key[key] = item

    negative_hidden = {
        key: outlier_by_key.get(key, {}).get("is_hidden", "False").lower() == "true"
        for key in negative_curves
    }
    positive_hidden = {
        key: outlier_by_key.get(key, {}).get("is_hidden", "False").lower() == "true"
        for key in positive_curves
    }

    negative_visible = {key: value for key, value in negative_curves.items() if not negative_hidden.get(key, False)}
    positive_visible = {key: value for key, value in positive_curves.items() if not positive_hidden.get(key, False)}

    negative_display = {
        key: moving_average(curve, max(CURVE_SMOOTH_WINDOW, NEGATIVE_COMBINED_SMOOTH_WINDOW))
        for key, curve in negative_curves.items()
    }
    negative_display_visible = {
        key: curve for key, curve in negative_display.items() if not negative_hidden.get(key, False)
    }
    negative_shrunk_visible = shrink_curves(negative_display_visible, NEGATIVE_COMBINED_SHRINK_FACTOR)
    negative_display.update(negative_shrunk_visible)

    positive_shrunk_visible = shrink_curves(positive_visible, POSITIVE_COMBINED_SHRINK_FACTOR)
    positive_display = dict(positive_curves)
    positive_display.update(positive_shrunk_visible)

    wells = []
    deleted_count = 0
    hidden_count = 0
    for index, row in enumerate(stage_rows, start=1):
        x = int(round(float(row["x"])))
        y = int(round(float(row["y"])))
        class_row = class_by_xy.get((x, y))
        keep = row.get("keep", "False").lower() == "true"
        if class_row:
            group = class_row["classification"].lower()
            curve_key = curve_key_by_xy.get((x, y), "")
            curve_meta = curve_meta_by_key.get(curve_key, {})
            outlier = outlier_by_key.get(curve_key, {})
            hidden = outlier.get("is_hidden", "False").lower() == "true"
            hidden_count += int(hidden)
            wells.append(
                {
                    "id": len(wells) + 1,
                    "x": x,
                    "y": y,
                    "classification": group,
                    "curveKey": curve_key,
                    "curveWellId": int(curve_meta.get("curveWellId", 0)),
                    "classificationWellId": int(class_row["well_id"]),
                    "rawIntensity": round(float(class_row["raw_intensity"]), 4),
                    "normalizedIntensity": round(float(class_row["normalized_intensity"]), 6),
                    "hidden": hidden,
                    "curveOutlier": outlier.get("is_curve_outlier", "False").lower() == "true",
                    "earlyOutlier": outlier.get("is_early_cycle_outlier", "False").lower() == "true",
                    "deleted": False,
                }
            )
        else:
            deleted_count += 1
            wells.append(
                {
                    "id": len(wells) + 1,
                    "x": x,
                    "y": y,
                    "classification": "deleted" if keep else "filtered",
                    "curveKey": "",
                    "deleted": True,
                    "hidden": False,
                    "stage1Intensity": round(float(row["stage1_intensity"]), 4),
                    "stage2Intensity": round(float(row["stage2_intensity"]), 4),
                    "retentionRatio": round(float(row["retention_ratio"]), 6),
                }
            )

    all_curves = {}
    for key, curve in negative_display.items():
        if not negative_hidden.get(key, False):
            all_curves[key] = [round(value, 4) for value in curve]
    for key, curve in positive_display.items():
        if not positive_hidden.get(key, False):
            all_curves[key] = [round(value, 4) for value in curve]

    single_curves = {}
    for key, curve in negative_curves.items():
        single_curves[key] = [round(value, 4) for value in curve]
    for key, curve in positive_curves.items():
        single_curves[key] = [round(value, 4) for value in curve]

    xs = [well["x"] for well in wells]
    ys = [well["y"] for well in wells]
    visible_values = [value for curve in all_curves.values() for value in curve]
    y_min = min(visible_values) if visible_values else 80
    y_max = max(visible_values) if visible_values else 160

    return {
        "meta": {
            "title": "XJTU Real-time dPCR",
            "sourceResultDir": result_dir,
            "cycleCount": len(cycles),
            "totalWells": len(wells),
            "positiveCount": sum(1 for well in wells if well["classification"] == "positive"),
            "negativeCount": sum(1 for well in wells if well["classification"] == "negative"),
            "deletedCount": deleted_count,
            "hiddenCurveCount": hidden_count,
            "bounds": {"minX": min(xs), "maxX": max(xs), "minY": min(ys), "maxY": max(ys)},
            "curveY": {
                "min": round(y_min - max(2.0, (y_max - y_min) * 0.08), 3),
                "max": round(y_max + max(2.0, (y_max - y_min) * 0.10), 3),
            },
        },
        "cycles": cycles,
        "wells": wells,
        "displayCurves": all_curves,
        "singleCurves": single_curves,
    }


def main():
    parser = argparse.ArgumentParser(description="Export data for the interactive dPCR chip viewer.")
    parser.add_argument("--result-dir", default=RESULT_DIR)
    parser.add_argument("--output", default=os.path.join("interactive_viewer", "viewer_data.json"))
    args = parser.parse_args()

    data = build_viewer_data(args.result_dir)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"Exported {data['meta']['totalWells']} wells to {args.output}")


if __name__ == "__main__":
    main()
