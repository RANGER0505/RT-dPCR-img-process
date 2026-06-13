import cv2
import os
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Arial"
plt.rcParams["mathtext.fontset"] = "stix"
plt.rcParams["axes.unicode_minus"] = False


def read_image_bgr(img_path):
    img_bgr = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError(f"Cannot read image: {img_path}")
    return img_bgr


def global_illumination_correction(image_gray):
    print("-> Running global illumination correction...")
    background = cv2.GaussianBlur(image_gray, (301, 301), 0).astype(np.float32)
    mean_background = np.mean(background)
    background[background == 0] = 1e-5
    correction_matrix = mean_background / background
    corrected_img = image_gray.astype(np.float32) * correction_matrix
    return np.clip(corrected_img, 0, 255).astype(np.uint8)


def extract_wells_single_image(
    img_path,
    top_left,
    bottom_right,
    min_area=20,
    max_area=150,
    min_circularity=0.65,
    radius_for_display=3,
):
    print("\n[Stage 1] Reading image and extracting wells...")
    img_bgr = read_image_bgr(img_path)
    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    x1, y1 = top_left
    x2, y2 = bottom_right
    roi_gray = img_gray[y1:y2, x1:x2]
    roi_color = img_bgr[y1:y2, x1:x2].copy()

    roi_gray_corrected = global_illumination_correction(roi_gray)

    binary = cv2.adaptiveThreshold(
        roi_gray_corrected,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        15,
        2,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary_opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(binary_opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    valid_wells = []
    detected_map = roi_color.copy()

    for contour in contours:
        area = cv2.contourArea(contour)
        if not (min_area < area < max_area):
            continue

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue

        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity <= min_circularity:
            continue

        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue

        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])
        valid_wells.append((cx, cy))
        cv2.circle(detected_map, (cx, cy), radius_for_display, (0, 255, 0), 1)

    print(f"-> Valid wells detected: {len(valid_wells)}")

    plt.figure(figsize=(15, 5))
    plt.subplot(1, 3, 1)
    plt.title("Original ROI")
    plt.imshow(roi_gray, cmap="gray")
    plt.axis("off")

    plt.subplot(1, 3, 2)
    plt.title("Illumination Corrected ROI")
    plt.imshow(roi_gray_corrected, cmap="gray")
    plt.axis("off")

    plt.subplot(1, 3, 3)
    plt.title(f"Detected Wells (N={len(valid_wells)})")
    plt.imshow(cv2.cvtColor(detected_map, cv2.COLOR_BGR2RGB))
    plt.axis("off")

    plt.tight_layout()
    plt.show()

    return roi_gray, roi_gray_corrected, roi_color, valid_wells


def classify_wells_by_threshold(
    roi_gray_corrected,
    roi_color,
    valid_wells,
    threshold=0.45,
    radius=3,
    threshold_is_normalized=True,
    dark_outlier_mad_factor=3.5,
    output_dir=None,
):
    print("\n[Stage 2] Classifying wells by adjustable threshold...")
    result_map = roi_color.copy()
    raw_intensities = []
    wells_coords = []

    for cx, cy in valid_wells:
        y_start = max(0, cy - radius)
        y_end = min(roi_gray_corrected.shape[0], cy + radius + 1)
        x_start = max(0, cx - radius)
        x_end = min(roi_gray_corrected.shape[1], cx + radius + 1)
        mean_intensity = np.mean(roi_gray_corrected[y_start:y_end, x_start:x_end])
        raw_intensities.append(mean_intensity)
        wells_coords.append((cx, cy))

    raw_intensities = np.array(raw_intensities, dtype=np.float32)
    if len(raw_intensities) == 0:
        print("-> No valid wells to classify.")
        return [], []

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, labels_pre, centers_pre = cv2.kmeans(
        raw_intensities.reshape(-1, 1),
        2,
        None,
        criteria,
        10,
        cv2.KMEANS_RANDOM_CENTERS,
    )

    if centers_pre[0][0] > centers_pre[1][0]:
        neg_label_pre = 1
    else:
        neg_label_pre = 0

    neg_pre_mask = labels_pre.flatten() == neg_label_pre
    neg_pre_intensities = raw_intensities[neg_pre_mask]

    if len(neg_pre_intensities) > 0:
        neg_median = float(np.median(neg_pre_intensities))
        neg_mad = float(np.median(np.abs(neg_pre_intensities - neg_median)))
        dark_cutoff = max(0.0, neg_median - dark_outlier_mad_factor * 1.4826 * neg_mad)
    else:
        dark_cutoff = 0.0

    keep_mask = raw_intensities >= dark_cutoff
    removed_dark_count = int(np.sum(~keep_mask))
    if removed_dark_count > 0:
        print(f"-> Removed {removed_dark_count} unusually dark wells; cutoff={dark_cutoff:.3f}")

    raw_intensities = raw_intensities[keep_mask]
    wells_coords = [coord for coord, keep in zip(wells_coords, keep_mask) if keep]

    if len(raw_intensities) == 0:
        print("-> No wells remain after dark-outlier removal.")
        return [], []

    intensity_min = float(np.min(raw_intensities))
    intensity_max = float(np.max(raw_intensities))
    if intensity_max == intensity_min:
        normalized_intensities = np.zeros_like(raw_intensities)
    else:
        normalized_intensities = (raw_intensities - intensity_min) / (intensity_max - intensity_min)

    classify_values = normalized_intensities if threshold_is_normalized else raw_intensities
    positive_mask = classify_values >= threshold

    positive_wells = []
    negative_wells = []
    for (cx, cy), is_positive in zip(wells_coords, positive_mask):
        if is_positive:
            positive_wells.append((cx, cy))
            cv2.circle(result_map, (cx, cy), radius, (0, 0, 255), -1)
        else:
            negative_wells.append((cx, cy))
            cv2.circle(result_map, (cx, cy), radius, (255, 0, 0), 1)

    n_total = len(wells_coords)
    n_pos = len(positive_wells)
    lambda_val = 0.0 if n_pos == 0 else (float("inf") if n_pos == n_total else -np.log(1 - n_pos / n_total))

    threshold_name = "Normalized threshold" if threshold_is_normalized else "Raw intensity threshold"
    print("--- Threshold classification result ---")
    print(f"Total valid wells: {n_total}")
    print(f"Negative wells: {len(negative_wells)}")
    print(f"Positive wells: {n_pos}")
    print(f"{threshold_name}: {threshold:.4f}")
    print(f"Lambda: {lambda_val:.4f}")

    partition_numbers = np.arange(n_total)
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    ax.scatter(
        partition_numbers[~positive_mask],
        normalized_intensities[~positive_mask],
        s=6,
        c="#A6A6A6",
        alpha=0.8,
        linewidths=0,
        label="Negative",
    )
    ax.scatter(
        partition_numbers[positive_mask],
        normalized_intensities[positive_mask],
        s=6,
        c="#2F80ED",
        alpha=0.9,
        linewidths=0,
        label="Positive",
    )

    # if threshold_is_normalized:
    #     plt.axhline(threshold, color="#D62728", linewidth=1.5, linestyle="--", label="Threshold")

    ax.set_xlabel("Partition number", fontsize=16, fontweight="bold", fontstyle="italic")
    ax.set_ylabel("Normalized F", fontsize=16, fontweight="bold", fontstyle="italic")
    ax.set_xlim(0, n_total)
    ax.set_ylim(0, 1.0)
    ax.ticklabel_format(style="sci", axis="x", scilimits=(4, 4), useMathText=False)
    for spine in ax.spines.values():
        spine.set_linewidth(1.5)
    ax.tick_params(direction="out", length=5, width=1.5)
    # plt.legend(frameon=False)
    ax.grid(False)
    plt.tight_layout()

    if output_dir:
        scatter_path = os.path.join(output_dir, "threshold_scatter.png")
        plt.savefig(scatter_path, bbox_inches="tight", dpi=300)
        print(f"-> Threshold scatter saved: {scatter_path}")
    plt.show()

    plt.figure(figsize=(8, 8))
    plt.title(f"Threshold Map: {n_pos} Positives (Red), {len(negative_wells)} Negatives (Blue)")
    plt.imshow(cv2.cvtColor(result_map, cv2.COLOR_BGR2RGB))
    plt.axis("off")
    plt.tight_layout()

    if output_dir:
        map_path = os.path.join(output_dir, "threshold_spatial_map.png")
        plt.savefig(map_path, bbox_inches="tight", dpi=300)
        print(f"-> Threshold spatial map saved: {map_path}")
    plt.show()

    return positive_wells, negative_wells


if __name__ == "__main__":
    IMAGE_PATH = r"D:\RT-dPCR IMG\linchuang\72-10\72-10.jpg"
    ROI_TOP_LEFT = (2195, 634)
    ROI_BOTTOM_RIGHT = (4593, 2412)

    POSITIVE_THRESHOLD = 0.25
    THRESHOLD_IS_NORMALIZED = True
    DARK_OUTLIER_MAD_FACTOR = 3.5

    roi_gray, roi_gray_corrected, roi_color, valid_wells = extract_wells_single_image(
        img_path=IMAGE_PATH,
        top_left=ROI_TOP_LEFT,
        bottom_right=ROI_BOTTOM_RIGHT,
        min_area=20,
        max_area=150,
        min_circularity=0.65,
        radius_for_display=3,
    )

    classify_wells_by_threshold(
        roi_gray_corrected=roi_gray_corrected,
        roi_color=roi_color,

        valid_wells=valid_wells,
        threshold=POSITIVE_THRESHOLD,
        radius=3,
        threshold_is_normalized=THRESHOLD_IS_NORMALIZED,
        dark_outlier_mad_factor=DARK_OUTLIER_MAD_FACTOR,
        output_dir=os.path.dirname(IMAGE_PATH),
    )

    print("\n>>> Threshold-based dPCR image processing pipeline completed.")
