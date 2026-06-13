import cv2
import os
import numpy as np
import matplotlib.pyplot as plt

# ==============================
# 全局字体设置 (引入 zhongdian.py 格式)
# ==============================
plt.rcParams['font.family'] = 'Arial'
plt.rcParams['mathtext.fontset'] = 'stix'
plt.rcParams['axes.unicode_minus'] = False


def global_illumination_correction(image_gray):
    """
    参考文献的全局不均匀性校正。
    由于缺乏真实的平场荧光图像(Flat-field image)，这里采用大尺寸高斯模糊提取光照背景轮廓，
    将其作为基准 F(x,y) 来计算校正因子 C(x,y)。
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


def extract_wells_single_image(img_path, top_left, bottom_right,
                               min_area=20, max_area=150, min_circularity=0.65,
                               radius_for_intensity=3):
    """
    针对单张终点图的微孔提取 (仅保留 Stage 1 的形态学提取逻辑)
    """
    print("\n[阶段 1] 读取图像并提取有效微孔...")

    # 1. 使用支持中文路径的读取方式
    img_bgr = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError(f"无法读取图像，请检查路径: {img_path}")

    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    x1, y1 = top_left
    x2, y2 = bottom_right

    roi_gray = img_gray[y1:y2, x1:x2]
    roi_color = img_bgr[y1:y2, x1:x2].copy()

    # 2. 核心：在识别微孔前，先进行光照均匀化处理
    roi_gray_corrected = global_illumination_correction(roi_gray)

    # 3. 形态学微孔识别 (基于校正后的图像)
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

    return roi_gray_corrected, roi_color, valid_wells


def classify_endpoint_fluorescence_single(roi_gray_corrected, roi_color, valid_wells, radius=3):
    """
    单图终点法阴阳性判读与统计图生成。
    利用光照校正后的灰度图直接提取绝对亮度进行 K-Means 聚类。
    """
    print("\n[阶段 2] 启动终点法阴阳性判读...")

    result_map = roi_color.copy()
    end_intensities = []
    wells_data = []

    # 1. 提取所有微孔的亮度
    for cx, cy in valid_wells:
        y_s, y_e = max(0, cy - radius), min(roi_gray_corrected.shape[0], cy + radius + 1)
        x_s, x_e = max(0, cx - radius), min(roi_gray_corrected.shape[1], cx + radius + 1)

        mean_intensity = np.mean(roi_gray_corrected[y_s:y_e, x_s:x_e])
        end_intensities.append(mean_intensity)
        wells_data.append((cx, cy, mean_intensity))

    end_intensities = np.array(end_intensities, dtype=np.float32)

    # 2. 终点强度归一化 (Min-Max 全局缩放 to 0-1)
    i_min = np.min(end_intensities)
    i_max = np.max(end_intensities)
    if i_max == i_min:
        norm_end_intensities = np.zeros_like(end_intensities)
    else:
        norm_end_intensities = (end_intensities - i_min) / (i_max - i_min)

    # 3. 自动聚类 (K-Means K=2) 寻找归一化终点亮度的分界线
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    norm_end_reshaped = norm_end_intensities.reshape(-1, 1)
    _, labels, centers = cv2.kmeans(norm_end_reshaped, 2, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

    if centers[0][0] > centers[1][0]:
        pos_label, neg_label = 0, 1
    else:
        pos_label, neg_label = 1, 0

    norm_pos_center = centers[pos_label][0]
    norm_neg_center = centers[neg_label][0]
    norm_threshold = (norm_pos_center + norm_neg_center) / 2.0

    # 4. 分类统计与可视化标记
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
    # 5. 绘图展示 (完全替换为 zhongdian.py 格式)
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

    # # 阈值线 (原代码逻辑，匹配新图格式)
    # ax.axhline(norm_threshold, color='black', linestyle='--', linewidth=1)

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
    # 空间分布图 (单独开一个窗口显示，避免破坏上面严格定义的 figsize)
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
    IMAGE_PATH = r"D:\RT-dPCR IMG\dPCR-YR\test\9-40.jpg"

    ROI_TOP_LEFT = (2195, 634)
    ROI_BOTTOM_RIGHT = (4593, 2412)

    # 1. 图像均匀化预处理 & 提取微孔
    roi_gray_corrected, roi_color, valid_wells = extract_wells_single_image(
        img_path=IMAGE_PATH,
        top_left=ROI_TOP_LEFT,
        bottom_right=ROI_BOTTOM_RIGHT,
        min_area=20, max_area=150, min_circularity=0.65,
        radius_for_intensity=3
    )

    if len(valid_wells) > 0:
        # 2. 终点图阴阳性判读
        classify_endpoint_fluorescence_single(
            roi_gray_corrected=roi_gray_corrected,
            roi_color=roi_color,
            valid_wells=valid_wells,
            radius=3
        )
        print("\n>>> dPCR 图像处理管线全部执行完毕。")
    else:
        print("提取有效微孔失败，请检查前期提取阈值或 ROI 坐标。")