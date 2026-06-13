import cv2
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

plt.rcParams['font.family'] = 'Arial'
plt.rcParams['mathtext.fontset'] = 'stix'
plt.rcParams['axes.unicode_minus'] = False

GREEN_FLUORESCENCE_CMAP = LinearSegmentedColormap.from_list(
    "green_fluorescence",
    ["#001a0b", "#004f20", "#00a843", "#38e06f", "#f1ff70"],
    N=256
)


def global_illumination_correction(image_gray):
    """
    参考文献的全局不均匀性校正。
    采用大尺寸高斯模糊提取光照背景轮廓，将其作为基准 F(x,y) 来计算校正因子 C(x,y)。
    """
    print("-> 正在执行全局光照不均匀性校正...")
    # 1. 提取低频背景 (模拟平场图像 F)
    # kernel size 必须足够大且为奇数，以抹平微孔的细节，只保留宏观光照分布
    background = cv2.GaussianBlur(image_gray, (301, 301), 0).astype(np.float32)

    # 2. 计算平均背景强度 (Mean_F)
    mean_f = np.mean(background)

    # 避免除以 0 的情况
    background[background == 0] = 1e-5

    # 3. 计算校正因子矩阵 C(x, y) = Mean_F / F(x, y)
    c_matrix = mean_f / background

    # 4. 应用校正 I_corrected = I_original * C(x, y)
    corrected_img = image_gray.astype(np.float32) * c_matrix

    # 截断并转回 uint8
    corrected_img = np.clip(corrected_img, 0, 255).astype(np.uint8)
    return corrected_img


def plot_illumination_correction_figure(roi_gray, roi_gray_corrected, save_path=None):
    """
    生成照明场纠正示意图：
    A 原始图
    B 估计的照明场
    C 纠正后的图
    D 亮度分布直方图
    """
    background = cv2.GaussianBlur(roi_gray, (301, 301), 0).astype(np.float32)
    corrected = roi_gray_corrected

    image_vmin = float(np.percentile(np.concatenate([roi_gray.ravel(), corrected.ravel()]), 1))
    image_vmax = float(np.percentile(np.concatenate([roi_gray.ravel(), corrected.ravel()]), 99.7))

    h, w = roi_gray.shape
    step = max(1, min(h, w) // 120)
    bg_small = background[::step, ::step]
    x = np.arange(bg_small.shape[1])
    y = np.arange(bg_small.shape[0])
    xx, yy = np.meshgrid(x, y)

    fig = plt.figure(figsize=(14, 10), dpi=200)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 0.85])

    ax1 = fig.add_subplot(gs[0, 0])
    ax1.imshow(roi_gray, cmap=GREEN_FLUORESCENCE_CMAP, vmin=image_vmin, vmax=image_vmax)
    ax1.set_title("A  Original ROI", fontsize=14, fontweight="bold")
    ax1.axis("off")

    ax2 = fig.add_subplot(gs[0, 1], projection="3d")
    surf = ax2.plot_surface(xx, yy, bg_small, cmap="viridis", linewidth=0, antialiased=True)
    ax2.set_title("B  Estimated illumination field", fontsize=14, fontweight="bold")
    ax2.set_xlabel("X")
    ax2.set_ylabel("Y")
    ax2.set_zlabel("Intensity")
    ax2.view_init(elev=35, azim=-135)
    fig.colorbar(surf, ax=ax2, shrink=0.6, pad=0.08)

    ax3 = fig.add_subplot(gs[1, 0])
    ax3.imshow(corrected, cmap=GREEN_FLUORESCENCE_CMAP, vmin=image_vmin, vmax=image_vmax)
    ax3.set_title("C  Illumination-corrected ROI", fontsize=14, fontweight="bold")
    ax3.axis("off")

    ax4 = fig.add_subplot(gs[1, 1])
    ax4.hist(roi_gray.ravel(), bins=120, alpha=0.55, color="#2ca02c", label="Original", density=True)
    ax4.hist(corrected.ravel(), bins=120, alpha=0.55, color="#1f77b4", label="Corrected", density=True)
    ax4.set_title("D  F distribution", fontsize=14, fontweight="bold")
    ax4.set_xlabel("Intensity")
    ax4.set_ylabel("Density")
    ax4.legend(frameon=False)
    ax4.grid(alpha=0.2)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, bbox_inches="tight", dpi=300)
        print(f"-> 照明场纠正示意图已保存: {save_path}")
    plt.show()


def plot_before_after_correction_large(roi_gray, roi_gray_corrected, save_path=None):
    """
    Generate a large green pseudocolor before/after comparison figure.
    """
    combined = np.concatenate([roi_gray.ravel(), roi_gray_corrected.ravel()])
    image_vmin = float(np.percentile(combined, 1))
    image_vmax = float(np.percentile(combined, 99.7))

    fig, axes = plt.subplots(1, 2, figsize=(16, 7), dpi=220)
    panels = [
        ("Before correction", roi_gray),
        ("After illumination correction", roi_gray_corrected),
    ]

    for ax, (title, image) in zip(axes, panels):
        ax.imshow(image, cmap=GREEN_FLUORESCENCE_CMAP, vmin=image_vmin, vmax=image_vmax)
        ax.set_title(title, fontsize=20, fontweight="bold")
        ax.axis("off")

    plt.tight_layout(pad=1.2)
    if save_path:
        plt.savefig(save_path, bbox_inches="tight", dpi=300)
        print(f"-> Before/after correction figure saved: {save_path}")
    plt.show()


def plot_original_corrected_3d_maps(roi_gray, roi_gray_corrected, save_path=None, smooth_kernel=151):
    """
    Generate side-by-side 3D intensity maps before and after illumination correction.
    """
    if smooth_kernel % 2 == 0:
        smooth_kernel += 1

    original_display = cv2.GaussianBlur(roi_gray, (smooth_kernel, smooth_kernel), 0).astype(np.float32)
    corrected_display = cv2.GaussianBlur(roi_gray_corrected, (smooth_kernel, smooth_kernel), 0).astype(np.float32)

    h, w = roi_gray.shape
    step = max(1, min(h, w) // 180)
    original_small = original_display[::step, ::step]
    corrected_small = corrected_display[::step, ::step]

    x = np.arange(original_small.shape[1])
    y = np.arange(original_small.shape[0])
    xx, yy = np.meshgrid(x, y)

    z_min = float(np.percentile(np.concatenate([original_small.ravel(), corrected_small.ravel()]), 1))
    z_max = float(np.percentile(np.concatenate([original_small.ravel(), corrected_small.ravel()]), 99.7))

    fig = plt.figure(figsize=(16, 7), dpi=220)
    panels = [
        ("Original 3D Map", original_small),
        ("Corrected 3D Map", corrected_small),
    ]

    for index, (title, surface_data) in enumerate(panels, start=1):
        ax = fig.add_subplot(1, 2, index, projection="3d")
        clipped_surface = np.clip(surface_data, z_min, z_max)
        surf = ax.plot_surface(
            xx,
            yy,
            clipped_surface,
            cmap="viridis",
            vmin=z_min,
            vmax=z_max,
            linewidth=0,
            antialiased=True
        )
        ax.set_title(title, fontsize=18, fontweight="bold")
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Gray value")
        ax.set_zlim(z_min, z_max)
        ax.view_init(elev=32, azim=-135)
        fig.colorbar(surf, ax=ax, shrink=0.65, pad=0.08)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, bbox_inches="tight", dpi=300)
        print(f"-> Original/corrected 3D maps saved: {save_path}")
    plt.show()


def extract_wells_single_image(img_path, top_left, bottom_right,
                               min_area=20, max_area=150, min_circularity=0.65,
                               radius_for_intensity=3):

    print("\n[阶段 1] 读取图像并提取有效微孔...")

    img_bgr = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError(f"无法读取图像，请检查路径: {img_path}")

    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    x1, y1 = top_left
    x2, y2 = bottom_right

    roi_gray = img_gray[y1:y2, x1:x2]
    roi_color = img_bgr[y1:y2, x1:x2].copy()

    #在识别微孔前先进行光照均匀化处理
    roi_gray_corrected = global_illumination_correction(roi_gray)

    # 形态学微孔识别 (基于校正后的图像)
    binary = cv2.adaptiveThreshold(roi_gray_corrected, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 15, 2)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary_opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(binary_opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    valid_wells = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if min_area < area < max_area:
            perimeter = cv2.arcLength(cnt, True)
            if perimeter > 0:
                circularity = 4 * np.pi * (area / (perimeter * perimeter))
                if circularity > min_circularity:
                    M = cv2.moments(cnt)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        valid_wells.append((cx, cy))
                        cv2.circle(roi_color, (cx, cy), radius_for_intensity, (0, 255, 0), 1)

    print(f"-> 共识别到有效微孔: {len(valid_wells)} 个")

    # 对比展示光照校正前后的差异
    plt.figure(figsize=(15, 5))
    plt.subplot(1, 3, 1)
    plt.title('Original ROI')
    plt.imshow(roi_gray, cmap='gray')
    plt.axis('off')

    plt.subplot(1, 3, 2)
    plt.title('Illumination Corrected ROI')
    plt.imshow(roi_gray_corrected, cmap='gray')
    plt.axis('off')

    plt.subplot(1, 3, 3)
    plt.title(f'Detected Wells (N={len(valid_wells)})')
    plt.imshow(cv2.cvtColor(roi_color, cv2.COLOR_BGR2RGB))
    plt.axis('off')

    plt.tight_layout()
    plt.show()

    return roi_gray, roi_gray_corrected, roi_color, valid_wells


def classify_endpoint_fluorescence_single(roi_gray_corrected, roi_color, valid_wells, radius=3, intensity_offset=0.0,
                                          dark_outlier_mad_factor=3.5):
    """
    dark_outlier_mad_factor: robust cutoff factor for removing unusually dark wells.
    单图终点法阴阳性判读与统计图生成 (双重聚类版)。
    intensity_offset: 仅针对阴性孔扣除的亮度数值。
    """
    print(f"\n[阶段 2] 启动终点法阴阳性判读 (阴性孔专属扣除值: {intensity_offset})...")

    result_map = roi_color.copy()
    raw_intensities = []
    wells_coords = []

    # ==========================================
    # 1. 提取所有微孔的原始亮度
    # ==========================================
    for cx, cy in valid_wells:
        y_s, y_e = max(0, cy - radius), min(roi_gray_corrected.shape[0], cy + radius + 1)
        x_s, x_e = max(0, cx - radius), min(roi_gray_corrected.shape[1], cx + radius + 1)
        mean_intensity = np.mean(roi_gray_corrected[y_s:y_e, x_s:x_e])
        raw_intensities.append(mean_intensity)
        wells_coords.append((cx, cy))

    raw_intensities = np.array(raw_intensities, dtype=np.float32)

    # ==========================================
    # 2. 第一轮预聚类：识别出哪些是阴性孔
    # ==========================================
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, labels_pre, centers_pre = cv2.kmeans(raw_intensities.reshape(-1, 1), 2, None, criteria, 10,
                                            cv2.KMEANS_RANDOM_CENTERS)

    if centers_pre[0][0] > centers_pre[1][0]:
        pos_label_pre, neg_label_pre = 0, 1
    else:
        pos_label_pre, neg_label_pre = 1, 0

    neg_pre_mask = (labels_pre.flatten() == neg_label_pre)
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
    labels_pre = labels_pre[keep_mask]
    wells_coords = [coord for coord, keep in zip(wells_coords, keep_mask) if keep]
    valid_wells = wells_coords

    if len(raw_intensities) == 0:
        print("-> No wells remain after dark-outlier removal.")
        return roi_gray_corrected, result_map, []

    # ==========================================
    # 3. 核心修改：定向打压，只对阴性孔扣除可调数值
    # ==========================================
    end_intensities = np.copy(raw_intensities)
    idx_neg_pre = (labels_pre.flatten() == neg_label_pre)

    # 只让阴性孔减去 intensity_offset，并强制下限为 0，防止负数反向破坏归一化
    end_intensities[idx_neg_pre] = np.maximum(0.0, end_intensities[idx_neg_pre] - intensity_offset)

    # 将调整后的数值存入 wells_data 供后续使用
    wells_data = []
    for i, (cx, cy) in enumerate(wells_coords):
        wells_data.append((cx, cy, end_intensities[i]))

    # ==========================================
    # 4. 终点强度归一化 (Min-Max 全局缩放 to 0-1)
    # ==========================================
    i_min = np.min(end_intensities)
    i_max = np.max(end_intensities)
    if i_max == i_min:
        norm_end_intensities = np.zeros_like(end_intensities)
    else:
        norm_end_intensities = (end_intensities - i_min) / (i_max - i_min)

    # ==========================================
    # 5. 第二轮正式聚类 (基于定向调整后的数据)
    # ==========================================
    norm_end_reshaped = norm_end_intensities.reshape(-1, 1)
    _, labels, centers = cv2.kmeans(norm_end_reshaped, 2, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

    if centers[0][0] > centers[1][0]:
        pos_label, neg_label = 0, 1
    else:
        pos_label, neg_label = 1, 0

    norm_pos_center = centers[pos_label][0]
    norm_neg_center = centers[neg_label][0]
    norm_threshold = (norm_pos_center + norm_neg_center) / 2.0

    # 6. 分类统计与可视化标记
    positive_wells = []
    negative_wells = []

    for i, (cx, cy, end_I) in enumerate(wells_data):
        if labels[i][0] == pos_label:
            positive_wells.append((cx, cy))
            cv2.circle(result_map, (cx, cy), radius, (0, 0, 255), -1)  # 阳性标红
        else:
            negative_wells.append((cx, cy))
            cv2.circle(result_map, (cx, cy), radius, (255, 0, 0), 1)  # 阴性标蓝空心

    # 计算泊松分布浓度
    n_total = len(valid_wells)
    n_pos = len(positive_wells)
    lambda_val = 0.0 if n_pos == 0 else (float('inf') if n_pos == n_total else -np.log(1 - (n_pos / n_total)))

    print(f"--- 终点法判读结果 ---")
    print(f"总有效孔数: {n_total}")
    print(f"阴性孔数 (Negative): {len(negative_wells)}")
    print(f"阳性孔数 (Positive): {n_pos}")
    print(f"归一化判定阈值 (Threshold): {norm_threshold:.4f}")
    print(f"计算平均拷贝数 (Lambda): {lambda_val:.4f}")

    # ==========================================
    # 7. 绘图展示 (完全保留 zhongdian.py 格式)
    # ==========================================
    partition_numbers = np.arange(len(valid_wells))

    # 获取布尔索引用于区分阴阳性，方便不同样式绘制
    idx_pos = (labels.flatten() == pos_label)
    idx_neg = (labels.flatten() == neg_label)

    # 创建主画布
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)

    # 阴性孔：灰色
    ax.scatter(
        partition_numbers[idx_neg], norm_end_intensities[idx_neg],
        s=6, c="#A6A6A6", alpha=0.8, linewidths=0
    )

    # 阳性孔：蓝色
    ax.scatter(
        partition_numbers[idx_pos], norm_end_intensities[idx_pos],
        s=6, c="#2F80ED", alpha=0.9, linewidths=0
    )

    # 坐标轴标签
    ax.set_xlabel(
        "Partition number",
        fontsize=16,
        fontname='Arial',
        fontweight='bold',
        fontstyle='italic'
    )
    ax.set_ylabel(
        "Normalized F",
        fontsize=16,
        fontname='Arial',
        fontweight='bold',
        fontstyle='italic'
    )

    # 坐标范围
    ax.set_xlim(0, n_total)
    ax.set_ylim(0, 1.0)

    # x轴科学计数法
    ax.ticklabel_format(style='sci', axis='x', scilimits=(4, 4), useMathText=False)

    # 强制刷新，获取右下角科学计数法文字
    fig.canvas.draw()

    # 设置 offset text 样式
    offset = ax.xaxis.get_offset_text()
    offset.set_fontname('Arial')
    offset.set_fontsize(13)
    offset.set_fontweight('bold')
    offset.set_fontstyle('italic')

    # 设置刻度数字字体
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontname('Arial')
        label.set_fontsize(13)

    # 坐标轴边框加粗
    for spine in ax.spines.values():
        spine.set_linewidth(1.5)

    ax.tick_params(direction='out', length=5, width=1.5)
    ax.grid(False)

    plt.tight_layout()
    plt.show()

    # ------------------------------------------
    # 空间分布图
    # ------------------------------------------
    plt.figure(figsize=(8, 8))
    plt.title(f'Spatial Map: {n_pos} Positives (Red), {len(negative_wells)} Negatives (Blue)')
    plt.imshow(cv2.cvtColor(result_map, cv2.COLOR_BGR2RGB))
    plt.axis('off')
    plt.show()


# ==========================================
# 测试运行
# ==========================================
if __name__ == "__main__":
    # --- 参数配置区 ---
    # 替换为你实际的单张终点图路径（已支持中文路径读取）
    IMAGE_PATH = r"D:\RT-dPCR IMG\1210-4\corrected\IMG_20251210180246331.jpg"

    ROI_TOP_LEFT = (0, 0)
    ROI_BOTTOM_RIGHT = (2329, 1563)

    # 【新增参数】：仅针对阴性群体扣除的背景亮度值。
    # 根据临床样本的底噪严重程度，你可以将其设为 20、40 或更高。
    INTENSITY_OFFSET = 0.0

    # 1. 图像均匀化预处理 & 提取微孔
    roi_gray, roi_gray_corrected, roi_color, valid_wells = extract_wells_single_image(
        img_path=IMAGE_PATH,
        top_left=ROI_TOP_LEFT,
        bottom_right=ROI_BOTTOM_RIGHT,
        min_area=20, max_area=150, min_circularity=0.65,
        radius_for_intensity=3
    )

    illumination_figure_path = os.path.join(os.path.dirname(IMAGE_PATH), "illumination_correction_figure.png")
    plot_illumination_correction_figure(
        roi_gray=roi_gray,
        roi_gray_corrected=roi_gray_corrected,
        save_path=illumination_figure_path
    )

    before_after_figure_path = os.path.join(os.path.dirname(IMAGE_PATH), "illumination_before_after_large.png")
    plot_before_after_correction_large(
        roi_gray=roi_gray,
        roi_gray_corrected=roi_gray_corrected,
        save_path=before_after_figure_path
    )

    maps_3d_figure_path = os.path.join(os.path.dirname(IMAGE_PATH), "original_corrected_3d_maps.png")
    plot_original_corrected_3d_maps(
        roi_gray=roi_gray,
        roi_gray_corrected=roi_gray_corrected,
        save_path=maps_3d_figure_path
    )

    if len(valid_wells) > 0:
        # 2. 终点图阴阳性判读
        classify_endpoint_fluorescence_single(
            roi_gray_corrected=roi_gray_corrected,
            roi_color=roi_color,
            valid_wells=valid_wells,
            radius=3,
            intensity_offset=INTENSITY_OFFSET  # 传递调整数值
        )
        print("\n>>> dPCR 图像处理管线全部执行完毕。")
    else:
        print("提取有效微孔失败，请检查前期提取阈值或 ROI 坐标。")
