import argparse
import csv
import glob
import os
import re

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["font.serif"] = ["Times New Roman", "Times", "DejaVu Serif"]
plt.rcParams["mathtext.fontset"] = "stix"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["ps.fonttype"] = 42
plt.rcParams["axes.unicode_minus"] = False

# =========================
# Configuration
# =========================
BASE_DIR = r"D:\RT-dPCR IMG\1210-2"
ORIGINAL_DIR = os.path.join(BASE_DIR, "original")
CROPPED_DIR = os.path.join(BASE_DIR, "cropped")
CORRECTED_DIR = os.path.join(BASE_DIR, "corrected")
RESULT_DIR = os.path.join(BASE_DIR, "workflow_result")

ROI_TOP_LEFT = (1, 1)
ROI_BOTTOM_RIGHT = (2933,1496)

STABLE_START_INDEX = 1
STAGE1_IMAGE_NAME = ""
STAGE2_IMAGE_NAME = ""

MIN_AREA = 20
MAX_AREA = 150
MIN_CIRCULARITY = 0.65
RADIUS = 3
STD_MULTIPLIER = 2.0
MIN_RETENTION_RATIO = 0.85

CURVE_SMOOTH_WINDOW = 5
CURVE_BASELINE_CYCLES = 5
CURVE_USE_STABLE_RANGE_ONLY = True
CURVE_Y_TOP = 0.30
CURVE_Y_BOTTOM = -0.15
POSITIVE_CURVE_Y_TOP = 0.0
CURVE_HEADROOM_RATIO = 0.20
CURVE_VALUE_MODE = "early_max_zero"

CURVE_OUTLIER_MAD_FACTOR = 3.5
CURVE_FIG_WIDTH = 9.0
CURVE_FIG_HEIGHT = 7.0
MANUAL_Y_MIN = None
MANUAL_Y_MAX = None
COMBINED_HIDE_OUTLIER_CURVES = True

POSITIVE_COMBINED_SMOOTH_WINDOW = 5
POSITIVE_COMBINED_SHRINK_FACTOR = 0.75
COMBINED_REZERO_AFTER_SMOOTH = True
COMBINED_REZERO_CYCLES = 5

EARLY_CYCLE_FILTER_ENABLED = True
EARLY_CYCLE_COUNT = 8
EARLY_CYCLE_OUTLIER_MAD_FACTOR = 3.0

PLOT_TITLE_FONTSIZE = 22
PLOT_LABEL_FONTSIZE = 18
PLOT_TICK_FONTSIZE = 18
PLOT_FONT_WEIGHT = "bold"

def read_image_bgr(path):
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot read image: {path}")
    return image


def write_image(path, image):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ext = os.path.splitext(path)[1] or ".jpg"
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        raise ValueError(f"Cannot encode image: {path}")
    encoded.tofile(path)


def numeric_sort_key(path):
    nums = re.findall(r"\d+", os.path.basename(path))
    return tuple(int(num) for num in nums) if nums else (0,)


def list_images(folder):
    patterns = ["*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff", "*.bmp"]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(folder, pattern)))
    return sorted(files, key=numeric_sort_key)


def apply_axis_font_style(ax):
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontname("Times New Roman")
        label.set_fontsize(PLOT_TICK_FONTSIZE)
        label.set_fontweight(PLOT_FONT_WEIGHT)


def get_display_ylim(curve_matrix, y_bottom, y_top):
    if MANUAL_Y_MIN is not None and MANUAL_Y_MAX is not None:
        return float(MANUAL_Y_MIN), float(MANUAL_Y_MAX)

    y_min = float(np.percentile(curve_matrix, 0.5))
    y_max = float(np.percentile(curve_matrix, 99.5))
    y_span = max(0.05, y_max - y_min)

    if CURVE_VALUE_MODE == "raw":
        bottom = y_min - max(1.0, y_span * 0.08)
        top = y_max + max(1.0, y_span * 0.10)
        return bottom, top

    auto_bottom = y_min - max(0.02, y_span * 0.18)
    auto_top = y_max + max(0.03, y_span * CURVE_HEADROOM_RATIO)
    top_limit = auto_top if y_top <= 0 else max(y_top, auto_top)
    return min(y_bottom, auto_bottom), top_limit


def crop_original_images(original_dir, cropped_dir, top_left, bottom_right):
    image_files = list_images(original_dir)
    if not image_files:
        raise ValueError(f"No images found in original folder: {original_dir}")

    x1, y1 = top_left
    x2, y2 = bottom_right
    os.makedirs(cropped_dir, exist_ok=True)

    cropped_paths = []
    for image_path in image_files:
        image = read_image_bgr(image_path)
        height, width = image.shape[:2]
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError(
                f"ROI {top_left}->{bottom_right} is outside image "
                f"{os.path.basename(image_path)} size {(width, height)}"
            )

        cropped = image[y1:y2, x1:x2].copy()
        save_path = os.path.join(cropped_dir, os.path.basename(image_path))
        write_image(save_path, cropped)
        cropped_paths.append(save_path)

    print(f"[1] Cropped {len(cropped_paths)} images -> {cropped_dir}")
    return cropped_paths


def detect_stage1_candidates(roi_gray):
    binary = cv2.adaptiveThreshold(
        roi_gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        15,
        2,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary_opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(binary_opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not (MIN_AREA < area < MAX_AREA):
            continue

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue

        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity <= MIN_CIRCULARITY:
            continue

        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue

        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])
        y_start = max(0, cy - RADIUS)
        y_end = min(roi_gray.shape[0], cy + RADIUS + 1)
        x_start = max(0, cx - RADIUS)
        x_end = min(roi_gray.shape[1], cx + RADIUS + 1)
        mean_i1 = float(np.mean(roi_gray[y_start:y_end, x_start:x_end]))
        candidates.append((cx, cy, area, circularity, mean_i1))

    return candidates


def get_stable_paths(image_paths, stable_start_index):
    start = stable_start_index - 1
    if start < 0:
        raise ValueError("Stable start index must be >= 1.")

    stable_paths = image_paths[start:]
    if len(stable_paths) < 2:
        raise ValueError(
            f"At least two stable images are required from sorted image #{stable_start_index}; "
            f"only {len(stable_paths)} available."
        )
    return stable_paths


def two_stage_filter(cropped_paths, stage1_name="", stage2_name="", stable_start_index=3):
    stable_paths = get_stable_paths(cropped_paths, stable_start_index)

    by_name = {os.path.basename(path): path for path in cropped_paths}
    stage1_path = by_name.get(stage1_name) if stage1_name else stable_paths[0]
    stage2_path = by_name.get(stage2_name) if stage2_name else stable_paths[1]
    if stage1_path is None:
        raise ValueError(f"Stage1 image not found in cropped folder: {stage1_name}")
    if stage2_path is None:
        raise ValueError(f"Stage2 image not found in cropped folder: {stage2_name}")
    stable_path_set = set(stable_paths)
    if stage1_path not in stable_path_set or stage2_path not in stable_path_set:
        raise ValueError(
            "Stage1/Stage2 images must come from the stable image range. "
            f"Current stable range starts at sorted image #{stable_start_index}."
        )

    stage1_gray = cv2.cvtColor(read_image_bgr(stage1_path), cv2.COLOR_BGR2GRAY)
    stage2_gray = cv2.cvtColor(read_image_bgr(stage2_path), cv2.COLOR_BGR2GRAY)
    stage1_map = read_image_bgr(stage1_path)
    stage2_map = read_image_bgr(stage2_path)

    candidates = detect_stage1_candidates(stage1_gray)
    intensities = np.array([item[4] for item in candidates], dtype=np.float32)
    if len(intensities) == 0:
        raise ValueError("Stage1 did not detect any candidate wells.")

    mean_val = float(np.mean(intensities))
    std_val = float(np.std(intensities))
    lower_bound = mean_val - STD_MULTIPLIER * std_val
    upper_bound = mean_val + STD_MULTIPLIER * std_val

    stage1_valid = []
    for cx, cy, area, circularity, mean_i1 in candidates:
        if lower_bound <= mean_i1 <= upper_bound:
            stage1_valid.append((cx, cy, area, circularity, mean_i1))
            cv2.circle(stage1_map, (cx, cy), RADIUS, (0, 255, 0), 1)
        else:
            cv2.drawMarker(stage1_map, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 6, 1)

    final_wells = []
    stage2_rows = []
    for cx, cy, area, circularity, mean_i1 in stage1_valid:
        y_start = max(0, cy - RADIUS)
        y_end = min(stage2_gray.shape[0], cy + RADIUS + 1)
        x_start = max(0, cx - RADIUS)
        x_end = min(stage2_gray.shape[1], cx + RADIUS + 1)
        mean_i2 = float(np.mean(stage2_gray[y_start:y_end, x_start:x_end]))
        retention_ratio = mean_i2 / mean_i1 if mean_i1 != 0 else 0.0
        keep = retention_ratio >= MIN_RETENTION_RATIO
        stage2_rows.append((cx, cy, area, circularity, mean_i1, mean_i2, retention_ratio, keep))
        if keep:
            final_wells.append((cx, cy))
            cv2.circle(stage2_map, (cx, cy), RADIUS, (0, 255, 0), 1)
        else:
            cv2.drawMarker(stage2_map, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 6, 1)

    os.makedirs(RESULT_DIR, exist_ok=True)
    write_image(os.path.join(RESULT_DIR, "stage1_valid_wells.jpg"), stage1_map)
    write_image(os.path.join(RESULT_DIR, "stage2_final_wells.jpg"), stage2_map)
    save_wells_csv(os.path.join(RESULT_DIR, "valid_wells.csv"), final_wells)
    save_stage2_detail_csv(os.path.join(RESULT_DIR, "stage2_detail.csv"), stage2_rows)

    print("[2] Stage filter finished")
    print(f"    Stable range starts at sorted image #{stable_start_index}")
    print(f"    Stage1 image: {os.path.basename(stage1_path)}")
    print(f"    Stage2 image: {os.path.basename(stage2_path)}")
    print(f"    Morphology candidates: {len(candidates)}")
    print(f"    Stage1 valid wells: {len(stage1_valid)}")
    print(f"    Final valid wells: {len(final_wells)}")
    return final_wells


def save_wells_csv(path, wells):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["well_id", "x", "y"])
        for index, (cx, cy) in enumerate(wells, start=1):
            writer.writerow([index, cx, cy])


def save_stage2_detail_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["x", "y", "area", "circularity", "stage1_intensity", "stage2_intensity", "retention_ratio", "keep"]
        )
        writer.writerows(rows)


def global_illumination_correction(image_gray):
    background = cv2.GaussianBlur(image_gray, (301, 301), 0).astype(np.float32)
    mean_background = np.mean(background)
    background[background == 0] = 1e-5
    correction_matrix = mean_background / background
    corrected_img = image_gray.astype(np.float32) * correction_matrix
    return np.clip(corrected_img, 0, 255).astype(np.uint8)


def correct_cropped_images(cropped_paths, corrected_dir):
    os.makedirs(corrected_dir, exist_ok=True)
    corrected_paths = []

    for cropped_path in cropped_paths:
        image = read_image_bgr(cropped_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corrected_gray = global_illumination_correction(gray)
        save_path = os.path.join(corrected_dir, os.path.basename(cropped_path))
        write_image(save_path, corrected_gray)
        corrected_paths.append(save_path)

    print(f"[3] Corrected {len(corrected_paths)} cropped images -> {corrected_dir}")
    return corrected_paths


def sample_well_intensities(roi_gray_corrected, valid_wells):
    raw_intensities = []
    kept_wells = []
    for cx, cy in valid_wells:
        y_start = max(0, cy - RADIUS)
        y_end = min(roi_gray_corrected.shape[0], cy + RADIUS + 1)
        x_start = max(0, cx - RADIUS)
        x_end = min(roi_gray_corrected.shape[1], cx + RADIUS + 1)
        raw_intensities.append(float(np.mean(roi_gray_corrected[y_start:y_end, x_start:x_end])))
        kept_wells.append((cx, cy))
    return np.array(raw_intensities, dtype=np.float32), kept_wells


def classify_all_positive(endpoint_gray, endpoint_color, valid_wells):
    raw_intensities, wells = sample_well_intensities(endpoint_gray, valid_wells)
    if len(raw_intensities) == 0:
        raise ValueError("No valid wells were found for all-positive analysis.")

    min_i = float(np.min(raw_intensities))
    max_i = float(np.max(raw_intensities))
    normalized = np.zeros_like(raw_intensities) if max_i == min_i else (raw_intensities - min_i) / (max_i - min_i)
    positive_mask = np.ones(len(wells), dtype=bool)

    return build_classification_result(
        method="all_positive",
        endpoint_color=endpoint_color,
        wells=wells,
        raw_intensities=raw_intensities,
        normalized=normalized,
        positive_mask=positive_mask,
    )


def build_classification_result(
    method,
    endpoint_color,
    wells,
    raw_intensities,
    normalized,
    positive_mask,
):
    result_map = endpoint_color.copy()
    positive_wells = []

    for cx, cy in wells:
        positive_wells.append((cx, cy))
        cv2.circle(result_map, (cx, cy), RADIUS, (0, 0, 255), -1)

    n_total = len(wells)
    lambda_value = float("inf") if n_total else 0.0

    return {
        "method": method,
        "wells": wells,
        "positive_wells": positive_wells,
        "raw_intensities": raw_intensities,
        "normalized": normalized,
        "positive_mask": positive_mask,
        "lambda": lambda_value,
        "result_map": result_map,
    }


def save_classification_outputs(result):
    os.makedirs(RESULT_DIR, exist_ok=True)
    method = result["method"]
    map_path = os.path.join(RESULT_DIR, f"{method}_endpoint_map.jpg")
    scatter_path = os.path.join(RESULT_DIR, f"{method}_scatter.png")
    csv_path = os.path.join(RESULT_DIR, f"{method}_classification.csv")

    write_image(map_path, result["result_map"])

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["well_id", "x", "y", "raw_intensity", "normalized_intensity", "classification"])
        for index, ((cx, cy), raw_i, norm_i, is_positive) in enumerate(
            zip(result["wells"], result["raw_intensities"], result["normalized"], result["positive_mask"]),
            start=1,
        ):
            writer.writerow([index, cx, cy, float(raw_i), float(norm_i), "positive"])

    x_axis = np.arange(len(result["wells"]))
    positive_mask = result["positive_mask"]
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    ax.scatter(x_axis[~positive_mask], result["normalized"][~positive_mask], s=6, c="#A6A6A6", linewidths=0)
    ax.scatter(x_axis[positive_mask], result["normalized"][positive_mask], s=6, c="#2F80ED", linewidths=0)
    ax.set_xlabel("Partition number", fontsize=PLOT_LABEL_FONTSIZE, fontweight=PLOT_FONT_WEIGHT)
    ax.set_ylabel("Normalized F", fontsize=PLOT_LABEL_FONTSIZE, fontweight=PLOT_FONT_WEIGHT)
    ax.set_xlim(0, max(1, len(result["wells"])))
    ax.set_ylim(0, 1.0)
    ax.ticklabel_format(style="sci", axis="x", scilimits=(4, 4), useMathText=False)
    for spine in ax.spines.values():
        spine.set_linewidth(1.5)
    ax.tick_params(direction="out", length=5, width=1.5, labelsize=PLOT_TICK_FONTSIZE)
    apply_axis_font_style(ax)
    ax.grid(False)
    plt.tight_layout()
    plt.savefig(scatter_path, bbox_inches="tight", dpi=300)
    plt.close(fig)

    print(f"[4] {method} endpoint map finished")
    print(f"    Total valid wells: {len(result['wells'])}")
    print(f"    All valid wells are treated as positive: {len(result['positive_wells'])}")
    print("    Threshold: not used")
    print("    Lambda: inf")
    print(f"    Classification CSV: {csv_path}")
    print(f"    Endpoint map: {map_path}")
    print(f"    Scatter figure: {scatter_path}")


def smooth_curve_1d(values, window_size):
    if window_size <= 1 or len(values) < 3:
        return values.astype(np.float32)

    window_size = int(window_size)
    if window_size % 2 == 0:
        window_size += 1
    window_size = min(window_size, len(values))
    if window_size % 2 == 0:
        window_size -= 1
    if window_size <= 1:
        return values.astype(np.float32)

    pad = window_size // 2
    padded = np.pad(values, (pad, pad), mode="reflect")
    sigma = max(1.0, window_size / 3.0)
    positions = np.arange(window_size, dtype=np.float32) - pad
    kernel = np.exp(-0.5 * (positions / sigma) ** 2)
    kernel = kernel / np.sum(kernel)
    return np.convolve(padded, kernel, mode="valid").astype(np.float32)


def extract_well_curve_matrices(corrected_paths, wells):
    mean_matrix = np.zeros((len(wells), len(corrected_paths)), dtype=np.float32)
    sum_matrix = np.zeros((len(wells), len(corrected_paths)), dtype=np.float32)
    for image_index, image_path in enumerate(corrected_paths):
        image = read_image_bgr(image_path)
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        for well_index, (cx, cy) in enumerate(wells):
            y_start = max(0, cy - RADIUS)
            y_end = min(image.shape[0], cy + RADIUS + 1)
            x_start = max(0, cx - RADIUS)
            x_end = min(image.shape[1], cx + RADIUS + 1)
            patch = image[y_start:y_end, x_start:x_end].astype(np.float32)
            mean_matrix[well_index, image_index] = float(np.mean(patch))
            sum_matrix[well_index, image_index] = float(np.sum(patch))

    return mean_matrix, sum_matrix


def extract_well_curve_matrix(corrected_paths, wells):
    mean_matrix, _ = extract_well_curve_matrices(corrected_paths, wells)
    return mean_matrix


def normalize_curve_matrix(raw_matrix, baseline_cycles):
    if raw_matrix.size == 0:
        return raw_matrix.copy()

    baseline_end = max(1, min(int(baseline_cycles), raw_matrix.shape[1]))
    baseline = np.mean(raw_matrix[:, :baseline_end], axis=1, keepdims=True)
    baseline[baseline == 0] = 1e-5
    return ((raw_matrix - baseline) / baseline).astype(np.float32)


def delta_curve_matrix(raw_matrix, baseline_cycles):
    if raw_matrix.size == 0:
        return raw_matrix.copy()

    baseline_end = max(1, min(int(baseline_cycles), raw_matrix.shape[1]))
    baseline = np.mean(raw_matrix[:, :baseline_end], axis=1, keepdims=True)
    return (raw_matrix - baseline).astype(np.float32)


def early_max_zero_curve_matrix(raw_matrix, baseline_cycles, reference_mask=None):
    if raw_matrix.size == 0:
        return raw_matrix.copy()

    baseline_end = max(1, min(int(baseline_cycles), raw_matrix.shape[1]))
    reference_matrix = raw_matrix
    if reference_mask is not None:
        reference_mask = np.asarray(reference_mask, dtype=bool)
        if reference_mask.shape[0] == raw_matrix.shape[0] and np.any(reference_mask):
            reference_matrix = raw_matrix[reference_mask]
    early_max = float(np.max(reference_matrix[:, :baseline_end]))
    return (raw_matrix - early_max).astype(np.float32)


def rebaseline_curve_matrix(curve_matrix, baseline_cycles):
    if curve_matrix.size == 0:
        return curve_matrix.copy()

    baseline_end = max(1, min(int(baseline_cycles), curve_matrix.shape[1]))
    baseline = np.mean(curve_matrix[:, :baseline_end], axis=1, keepdims=True)
    return (curve_matrix - baseline).astype(np.float32)


def smooth_curve_matrix(curve_matrix, window_size):
    smoothed = np.zeros_like(curve_matrix, dtype=np.float32)
    for row_index in range(curve_matrix.shape[0]):
        smoothed[row_index, :] = smooth_curve_1d(curve_matrix[row_index, :], window_size)
    return smoothed


def select_curve_matrix(raw_matrix, sum_matrix=None):
    delta_matrix = delta_curve_matrix(raw_matrix, CURVE_BASELINE_CYCLES)
    normalized_matrix = normalize_curve_matrix(raw_matrix, CURVE_BASELINE_CYCLES)

    if CURVE_VALUE_MODE == "raw":
        return raw_matrix, delta_matrix, normalized_matrix, None, raw_matrix, "Green gray value"
    if CURVE_VALUE_MODE == "delta":
        return raw_matrix, delta_matrix, normalized_matrix, None, delta_matrix, "Green gray value change"
    if CURVE_VALUE_MODE == "early_max_zero":
        early_zero_matrix = early_max_zero_curve_matrix(raw_matrix, CURVE_BASELINE_CYCLES)
        return raw_matrix, delta_matrix, normalized_matrix, None, early_zero_matrix, "Fluorescence relative to initial max (a.u.)"
    if CURVE_VALUE_MODE == "sum_delta":
        if sum_matrix is None:
            raise ValueError("sum_delta mode requires summed well intensities.")
        sum_delta_matrix = delta_curve_matrix(sum_matrix, CURVE_BASELINE_CYCLES)
        return raw_matrix, delta_matrix, normalized_matrix, sum_delta_matrix, sum_delta_matrix, "Integrated fluorescence change (a.u.)"
    if CURVE_VALUE_MODE == "normalized":
        return raw_matrix, delta_matrix, normalized_matrix, None, normalized_matrix, "Normalized F"
    raise ValueError(f"Unknown curve value mode: {CURVE_VALUE_MODE}")


def detect_curve_outliers(smoothed_matrix):
    if smoothed_matrix.shape[0] < 4:
        return np.zeros(smoothed_matrix.shape[0], dtype=bool), np.zeros(smoothed_matrix.shape[0], dtype=np.float32), 0.0

    center_curve = np.median(smoothed_matrix, axis=0)
    distances = np.sqrt(np.mean((smoothed_matrix - center_curve) ** 2, axis=1))
    distance_median = float(np.median(distances))
    distance_mad = float(np.median(np.abs(distances - distance_median)))
    if distance_mad == 0:
        threshold = float(np.percentile(distances, 97.5))
    else:
        threshold = distance_median + CURVE_OUTLIER_MAD_FACTOR * 1.4826 * distance_mad
    return distances > threshold, distances.astype(np.float32), float(threshold)


def detect_early_cycle_outliers(curve_matrix, cycle_count, mad_factor):
    if curve_matrix.shape[0] < 4 or curve_matrix.shape[1] == 0:
        return np.zeros(curve_matrix.shape[0], dtype=bool), np.zeros(curve_matrix.shape[0], dtype=np.float32), 0.0

    early_count = max(1, min(int(cycle_count), curve_matrix.shape[1]))
    early_matrix = curve_matrix[:, :early_count]
    early_center = np.median(early_matrix, axis=0)
    distances = np.sqrt(np.mean((early_matrix - early_center) ** 2, axis=1))
    distance_median = float(np.median(distances))
    distance_mad = float(np.median(np.abs(distances - distance_median)))
    if distance_mad == 0:
        threshold = float(np.percentile(distances, 97.5))
    else:
        threshold = distance_median + mad_factor * 1.4826 * distance_mad
    return distances > threshold, distances.astype(np.float32), float(threshold)


def shrink_curves_toward_median(curve_matrix, shrink_factor):
    if curve_matrix.size == 0:
        return curve_matrix
    shrink_factor = float(np.clip(shrink_factor, 0.0, 1.0))
    center_curve = np.median(curve_matrix, axis=0, keepdims=True)
    return (center_curve + shrink_factor * (curve_matrix - center_curve)).astype(np.float32)


def save_well_curve_csv(path, corrected_paths, wells, raw_matrix, delta_matrix, normalized_matrix, sum_delta_matrix, smoothed_matrix):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "well_id",
                "x",
                "y",
                "cycle",
                "image_name",
                "raw_intensity",
                "delta_gray_value",
                "normalized_delta_f_over_f0",
                "sum_delta_intensity",
                "smoothed_plotted_value",
            ]
        )
        if sum_delta_matrix is None:
            sum_delta_matrix = np.full_like(raw_matrix, np.nan, dtype=np.float32)
        for well_index, (cx, cy) in enumerate(wells, start=1):
            for image_index, image_path in enumerate(corrected_paths, start=1):
                writer.writerow(
                    [
                        well_index,
                        cx,
                        cy,
                        image_index,
                        os.path.basename(image_path),
                        float(raw_matrix[well_index - 1, image_index - 1]),
                        float(delta_matrix[well_index - 1, image_index - 1]),
                        float(normalized_matrix[well_index - 1, image_index - 1]),
                        float(sum_delta_matrix[well_index - 1, image_index - 1]),
                        float(smoothed_matrix[well_index - 1, image_index - 1]),
                    ]
                )


def plot_classified_well_curves(corrected_paths, wells, label, line_alpha, y_top, y_bottom):
    if not wells:
        print(f"[5] No {label} wells available for curve plotting.")
        return
    if not corrected_paths:
        print("[5] No corrected images available for curve plotting.")
        return

    raw_matrix, sum_matrix = extract_well_curve_matrices(corrected_paths, wells)
    raw_matrix, delta_matrix, normalized_matrix, sum_delta_matrix, plot_matrix, y_label = select_curve_matrix(raw_matrix, sum_matrix)
    smoothed_matrix = smooth_curve_matrix(plot_matrix, CURVE_SMOOTH_WINDOW)
    if CURVE_VALUE_MODE == "early_max_zero":
        smoothed_matrix = early_max_zero_curve_matrix(smoothed_matrix, CURVE_BASELINE_CYCLES)

    csv_path = os.path.join(RESULT_DIR, f"{label}_well_curves.csv")
    curve_path = os.path.join(RESULT_DIR, f"{label}_well_smoothed_{CURVE_VALUE_MODE}_curves.png")
    save_well_curve_csv(csv_path, corrected_paths, wells, raw_matrix, delta_matrix, normalized_matrix, sum_delta_matrix, smoothed_matrix)

    cycles = np.arange(1, len(corrected_paths) + 1)
    fig, ax = plt.subplots(figsize=(CURVE_FIG_WIDTH, CURVE_FIG_HEIGHT), dpi=220)

    color_map = plt.get_cmap("tab20")
    for index, curve in enumerate(smoothed_matrix):
        ax.plot(
            cycles,
            curve,
            color=color_map(index % color_map.N),
            alpha=line_alpha,
            linewidth=0.7,
            solid_capstyle="round",
        )

    ax.set_title(
        f"{label.capitalize()} wells smoothed curves",
        fontsize=PLOT_TITLE_FONTSIZE,
        fontweight=PLOT_FONT_WEIGHT,
        pad=10,
    )
    ax.set_xlabel("Cycle", fontsize=PLOT_LABEL_FONTSIZE, fontweight=PLOT_FONT_WEIGHT)
    ax.set_ylabel(y_label, fontsize=PLOT_LABEL_FONTSIZE, fontweight=PLOT_FONT_WEIGHT)
    ax.set_xlim(1, max(1, len(corrected_paths)))

    bottom_limit, top_limit = get_display_ylim(smoothed_matrix, y_bottom, y_top)
    ax.set_ylim(bottom_limit, top_limit)

    for spine in ax.spines.values():
        spine.set_linewidth(1.0)
    ax.tick_params(direction="out", length=5, width=1.0, labelsize=PLOT_TICK_FONTSIZE)
    apply_axis_font_style(ax)
    ax.grid(True, color="#B0B0B0", alpha=0.28, linewidth=0.8)
    plt.tight_layout()
    plt.savefig(curve_path, bbox_inches="tight", dpi=300)
    plt.close(fig)

    print(f"[5] {label.capitalize()}-well curves finished")
    print(f"    {label.capitalize()} wells plotted: {len(wells)}")
    print(f"    Corrected images used: {len(corrected_paths)}")
    print(f"    Smooth window: {CURVE_SMOOTH_WINDOW}")
    print(f"    Curve CSV: {csv_path}")
    print(f"    Curve figure: {curve_path}")


def plot_positive_well_curves(corrected_paths, positive_wells):
    plot_classified_well_curves(
        corrected_paths=corrected_paths,
        wells=positive_wells,
        label="positive",
        line_alpha=0.24,
        y_top=POSITIVE_CURVE_Y_TOP,
        y_bottom=CURVE_Y_BOTTOM,
    )


def save_all_positive_curve_summary(path, wells, distances, outliers, early_outliers):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["well_id", "x", "y", "curve_distance", "is_curve_outlier", "is_early_cycle_outlier", "is_hidden"])
        for index, ((cx, cy), distance, is_outlier, is_early_outlier) in enumerate(
            zip(wells, distances, outliers, early_outliers),
            start=1,
        ):
            writer.writerow([index, cx, cy, float(distance), bool(is_outlier), bool(is_early_outlier), bool(is_outlier or is_early_outlier)])


def plot_all_positive_combined_well_curves(corrected_paths, wells):
    if not corrected_paths:
        print("[6] No corrected images available for all-positive curve plotting.")
        return
    if not wells:
        print("[6] No valid wells available for all-positive curve plotting.")
        return

    cycles = np.arange(1, len(corrected_paths) + 1)
    raw_matrix, sum_matrix = extract_well_curve_matrices(corrected_paths, wells)
    _, _, _, _, plot_matrix, y_label = select_curve_matrix(raw_matrix, sum_matrix)
    smooth_window = max(CURVE_SMOOTH_WINDOW, POSITIVE_COMBINED_SMOOTH_WINDOW)
    smoothed_matrix = smooth_curve_matrix(plot_matrix, smooth_window)

    if COMBINED_REZERO_AFTER_SMOOTH and CURVE_VALUE_MODE in {"delta", "normalized"}:
        smoothed_matrix = rebaseline_curve_matrix(smoothed_matrix, COMBINED_REZERO_CYCLES)

    outliers, distances, outlier_threshold = detect_curve_outliers(smoothed_matrix)
    early_outliers = np.zeros_like(outliers)
    early_threshold = 0.0
    if EARLY_CYCLE_FILTER_ENABLED:
        early_outliers, _, early_threshold = detect_early_cycle_outliers(
            smoothed_matrix,
            EARLY_CYCLE_COUNT,
            EARLY_CYCLE_OUTLIER_MAD_FACTOR,
        )
    hidden_mask = outliers | early_outliers

    display_matrix = smoothed_matrix.copy()
    non_outlier_mask = ~hidden_mask
    if np.any(non_outlier_mask):
        display_matrix[non_outlier_mask] = shrink_curves_toward_median(
            display_matrix[non_outlier_mask],
            POSITIVE_COMBINED_SHRINK_FACTOR,
        )
    if CURVE_VALUE_MODE == "early_max_zero":
        display_matrix = early_max_zero_curve_matrix(
            display_matrix,
            CURVE_BASELINE_CYCLES,
            reference_mask=non_outlier_mask,
        )

    fig, ax = plt.subplots(figsize=(CURVE_FIG_WIDTH, CURVE_FIG_HEIGHT), dpi=220)
    for curve, is_hidden in zip(display_matrix, hidden_mask):
        if not is_hidden:
            ax.plot(cycles, curve, color="#E31A1C", alpha=0.58, linewidth=1.05, solid_capstyle="round", zorder=2)

    for curve, is_outlier in zip(display_matrix, outliers):
        if is_outlier and not COMBINED_HIDE_OUTLIER_CURVES and not EARLY_CYCLE_FILTER_ENABLED:
            ax.plot(cycles, curve, color="#FFD900", alpha=0.95, linewidth=1.45, solid_capstyle="round", zorder=5)

    visible_matrix = display_matrix[~hidden_mask]
    if not visible_matrix.size:
        visible_matrix = np.zeros((1, len(corrected_paths)), dtype=np.float32)

    ax.set_title("All-positive RT-dPCR smoothed curves", fontsize=PLOT_TITLE_FONTSIZE, fontweight=PLOT_FONT_WEIGHT, pad=10)
    ax.set_xlabel("Cycle", fontsize=PLOT_LABEL_FONTSIZE, fontweight=PLOT_FONT_WEIGHT)
    ax.set_ylabel(y_label, fontsize=PLOT_LABEL_FONTSIZE, fontweight=PLOT_FONT_WEIGHT)
    ax.set_xlim(1, max(1, len(corrected_paths)))
    bottom_limit, top_limit = get_display_ylim(visible_matrix, CURVE_Y_BOTTOM, POSITIVE_CURVE_Y_TOP)
    ax.set_ylim(bottom_limit, top_limit)

    for spine in ax.spines.values():
        spine.set_linewidth(1.0)
    ax.tick_params(direction="out", length=5, width=1.0, labelsize=PLOT_TICK_FONTSIZE)
    apply_axis_font_style(ax)
    ax.grid(True, color="#B0B0B0", alpha=0.28, linewidth=0.8)
    plt.tight_layout()

    figure_path = os.path.join(RESULT_DIR, f"all_positive_well_smoothed_{CURVE_VALUE_MODE}_curves.png")
    summary_path = os.path.join(RESULT_DIR, "all_positive_curve_outliers.csv")
    plt.savefig(figure_path, bbox_inches="tight", dpi=300)
    plt.close(fig)
    save_all_positive_curve_summary(summary_path, wells, distances, outliers, early_outliers)

    print("[6] All-positive combined curves finished")
    print(f"    Curves: {len(wells)}; outliers: {int(np.sum(outliers))}; threshold={outlier_threshold:.4f}")
    print(f"    Early-cycle filter: {EARLY_CYCLE_FILTER_ENABLED}; cycles={EARLY_CYCLE_COUNT}; MAD factor={EARLY_CYCLE_OUTLIER_MAD_FACTOR:.2f}")
    print(f"    Hidden early curves: {int(np.sum(early_outliers))}; threshold={early_threshold:.4f}")
    print(f"    Hide outlier curves: {COMBINED_HIDE_OUTLIER_CURVES}")
    print(f"    Display smooth window: {smooth_window}; shrink factor={POSITIVE_COMBINED_SHRINK_FACTOR:.2f}")
    print(f"    Mean re-zero after smoothing: {COMBINED_REZERO_AFTER_SMOOTH and CURVE_VALUE_MODE in {'delta', 'normalized'}}; cycles={COMBINED_REZERO_CYCLES}")
    print(f"    Combined figure: {figure_path}")
    print(f"    Outlier summary: {summary_path}")


def run_workflow():
    cropped_paths = crop_original_images(ORIGINAL_DIR, CROPPED_DIR, ROI_TOP_LEFT, ROI_BOTTOM_RIGHT)
    stable_cropped_paths = get_stable_paths(cropped_paths, STABLE_START_INDEX)
    valid_wells = two_stage_filter(cropped_paths, STAGE1_IMAGE_NAME, STAGE2_IMAGE_NAME, STABLE_START_INDEX)
    corrected_paths = correct_cropped_images(cropped_paths, CORRECTED_DIR)
    corrected_by_name = {os.path.basename(path): path for path in corrected_paths}
    stable_corrected_paths = [corrected_by_name[os.path.basename(path)] for path in stable_cropped_paths]

    if not valid_wells:
        raise ValueError("No final valid wells were found; all-positive analysis cannot continue.")

    endpoint_name = os.path.basename(stable_cropped_paths[-1])
    endpoint_path = corrected_by_name[endpoint_name]
    print(f"    Endpoint image: {endpoint_name}")
    endpoint_gray = read_image_bgr(endpoint_path)
    if endpoint_gray.ndim == 3:
        endpoint_gray = cv2.cvtColor(endpoint_gray, cv2.COLOR_BGR2GRAY)
    endpoint_color = cv2.cvtColor(endpoint_gray, cv2.COLOR_GRAY2BGR)

    result = classify_all_positive(endpoint_gray, endpoint_color, valid_wells)

    save_classification_outputs(result)
    curve_corrected_paths = stable_corrected_paths if CURVE_USE_STABLE_RANGE_ONLY else corrected_paths
    plot_positive_well_curves(curve_corrected_paths, result["positive_wells"])
    plot_all_positive_combined_well_curves(curve_corrected_paths, result["positive_wells"])
    print("\n>>> Workflow completed.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Crop original images, filter wells, correct illumination, and plot all-positive RT-dPCR S curves."
    )
    parser.add_argument("--base-dir", default=BASE_DIR, help="Folder containing original/cropped/corrected/result folders.")
    parser.add_argument("--original-dir", default=None, help="Input original image folder.")
    parser.add_argument("--cropped-dir", default=None, help="Output cropped image folder.")
    parser.add_argument("--corrected-dir", default=None, help="Output corrected image folder.")
    parser.add_argument("--result-dir", default=None, help="Output result folder.")
    parser.add_argument("--roi-top-left", default=None, help="ROI top-left coordinate, format: x,y")
    parser.add_argument("--roi-bottom-right", default=None, help="ROI bottom-right coordinate, format: x,y")
    parser.add_argument(
        "--stable-start-index",
        type=int,
        default=STABLE_START_INDEX,
        help="1-based sorted image index where the no-shift stable range starts. Default: 3.",
    )
    parser.add_argument("--stage1-image", default=STAGE1_IMAGE_NAME, help="Stage1 baseline image file name.")
    parser.add_argument("--stage2-image", default=STAGE2_IMAGE_NAME, help="Stage2 validation image file name.")
    parser.add_argument("--curve-smooth-window", type=int, default=CURVE_SMOOTH_WINDOW)
    parser.add_argument("--curve-baseline-cycles", type=int, default=CURVE_BASELINE_CYCLES)
    parser.add_argument("--curve-y-top", type=float, default=CURVE_Y_TOP)
    parser.add_argument("--curve-y-bottom", type=float, default=CURVE_Y_BOTTOM)
    parser.add_argument("--positive-curve-y-top", type=float, default=POSITIVE_CURVE_Y_TOP)
    parser.add_argument("--manual-y-min", type=float, default=MANUAL_Y_MIN)
    parser.add_argument("--manual-y-max", type=float, default=MANUAL_Y_MAX)
    parser.add_argument("--curve-headroom-ratio", type=float, default=CURVE_HEADROOM_RATIO)
    parser.add_argument("--curve-outlier-mad-factor", type=float, default=CURVE_OUTLIER_MAD_FACTOR)
    parser.add_argument("--curve-fig-width", type=float, default=CURVE_FIG_WIDTH)
    parser.add_argument("--curve-fig-height", type=float, default=CURVE_FIG_HEIGHT)
    parser.add_argument("--plot-title-fontsize", type=float, default=PLOT_TITLE_FONTSIZE)
    parser.add_argument("--plot-label-fontsize", type=float, default=PLOT_LABEL_FONTSIZE)
    parser.add_argument("--plot-tick-fontsize", type=float, default=PLOT_TICK_FONTSIZE)
    parser.add_argument("--plot-font-weight", default=PLOT_FONT_WEIGHT, choices=["normal", "bold", "semibold", "heavy"])
    parser.add_argument(
        "--combined-hide-outlier-curves",
        action="store_true",
        default=COMBINED_HIDE_OUTLIER_CURVES,
        help="Hide curve outliers in the all-positive combined curve figure.",
    )
    parser.add_argument("--positive-combined-smooth-window", type=int, default=POSITIVE_COMBINED_SMOOTH_WINDOW)
    parser.add_argument(
        "--positive-combined-shrink-factor",
        type=float,
        default=POSITIVE_COMBINED_SHRINK_FACTOR,
        help="Display-only shrink factor for non-outlier positive curves in the combined figure. 1=no shrink, 0=median curve.",
    )
    parser.add_argument(
        "--combined-disable-rezero-after-smooth",
        action="store_true",
        help="Disable the display-only re-zero step applied after smoothing in the combined curve figure.",
    )
    parser.add_argument("--combined-rezero-cycles", type=int, default=COMBINED_REZERO_CYCLES)
    parser.add_argument(
        "--disable-early-cycle-filter",
        action="store_true",
        help="Disable the display-only filter that hides curves deviating strongly in the first few cycles.",
    )
    parser.add_argument("--early-cycle-count", type=int, default=EARLY_CYCLE_COUNT)
    parser.add_argument("--early-cycle-outlier-mad-factor", type=float, default=EARLY_CYCLE_OUTLIER_MAD_FACTOR)
    parser.add_argument(
        "--curve-value-mode",
        choices=["normalized", "delta", "raw", "sum_delta", "early_max_zero"],
        default=CURVE_VALUE_MODE,
        help="Curve y-value mode: normalized=DeltaF/F0, delta=gray value change, raw=corrected gray value, sum_delta=integrated gray value change, early_max_zero=raw minus the global maximum in the initial cycles.",
    )
    parser.add_argument(
        "--curve-include-shifted-images",
        action="store_true",
        help="Plot curves from all corrected images, including images before the stable range.",
    )
    return parser.parse_args()


def parse_xy(text):
    try:
        x_text, y_text = text.split(",", 1)
        return int(x_text.strip()), int(y_text.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid coordinate '{text}', expected x,y") from exc


if __name__ == "__main__":
    args = parse_args()
    BASE_DIR = args.base_dir
    ORIGINAL_DIR = args.original_dir or os.path.join(BASE_DIR, "original")
    CROPPED_DIR = args.cropped_dir or os.path.join(BASE_DIR, "cropped")
    CORRECTED_DIR = args.corrected_dir or os.path.join(BASE_DIR, "corrected")
    RESULT_DIR = args.result_dir or os.path.join(BASE_DIR, "workflow_result")
    STABLE_START_INDEX = args.stable_start_index
    STAGE1_IMAGE_NAME = args.stage1_image
    STAGE2_IMAGE_NAME = args.stage2_image
    CURVE_SMOOTH_WINDOW = args.curve_smooth_window
    CURVE_BASELINE_CYCLES = args.curve_baseline_cycles
    CURVE_Y_TOP = args.curve_y_top
    CURVE_Y_BOTTOM = args.curve_y_bottom
    POSITIVE_CURVE_Y_TOP = args.positive_curve_y_top
    MANUAL_Y_MIN = args.manual_y_min
    MANUAL_Y_MAX = args.manual_y_max
    CURVE_HEADROOM_RATIO = args.curve_headroom_ratio
    CURVE_OUTLIER_MAD_FACTOR = args.curve_outlier_mad_factor
    CURVE_FIG_WIDTH = args.curve_fig_width
    CURVE_FIG_HEIGHT = args.curve_fig_height
    PLOT_TITLE_FONTSIZE = args.plot_title_fontsize
    PLOT_LABEL_FONTSIZE = args.plot_label_fontsize
    PLOT_TICK_FONTSIZE = args.plot_tick_fontsize
    PLOT_FONT_WEIGHT = args.plot_font_weight
    COMBINED_HIDE_OUTLIER_CURVES = args.combined_hide_outlier_curves
    POSITIVE_COMBINED_SMOOTH_WINDOW = args.positive_combined_smooth_window
    POSITIVE_COMBINED_SHRINK_FACTOR = args.positive_combined_shrink_factor
    COMBINED_REZERO_AFTER_SMOOTH = not args.combined_disable_rezero_after_smooth
    COMBINED_REZERO_CYCLES = args.combined_rezero_cycles
    EARLY_CYCLE_FILTER_ENABLED = not args.disable_early_cycle_filter
    EARLY_CYCLE_COUNT = args.early_cycle_count
    EARLY_CYCLE_OUTLIER_MAD_FACTOR = args.early_cycle_outlier_mad_factor
    CURVE_VALUE_MODE = args.curve_value_mode
    CURVE_USE_STABLE_RANGE_ONLY = not args.curve_include_shifted_images
    if args.roi_top_left:
        ROI_TOP_LEFT = parse_xy(args.roi_top_left)
    if args.roi_bottom_right:
        ROI_BOTTOM_RIGHT = parse_xy(args.roi_bottom_right)

    run_workflow()
