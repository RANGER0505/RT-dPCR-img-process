import cv2
import os
import glob
import re
import numpy as np
import matplotlib.pyplot as plt


def two_stage_spatiotemporal_filter(img1_path, img2_path, top_left, bottom_right,
                                    min_area=20, max_area=150, min_circularity=0.65,
                                    radius_for_intensity=3, std_multiplier=2.0,
                                    min_retention_ratio=0.7):
    """
    双阶段微孔筛选：
    Stage 1: 基于 Image 1 提取物理基准 Mask（形态学 + 初始灰度正态剔除）
    Stage 2: 将 Base Mask 应用于 Image 2，通过“荧光保留率”剔除中途异常孔

    参数:
        min_retention_ratio: 荧光保留率下限。默认0.7(即Image2亮度不得低于Image1的70%)
    """

    # ==========================================
    # 准备工作：读取并裁剪两张图的 ROI
    # ==========================================
    img1_bgr = cv2.imread(img1_path)
    img2_bgr = cv2.imread(img2_path)

    if img1_bgr is None: raise ValueError(f"无法读取基准图像: {img1_path}")
    if img2_bgr is None: raise ValueError(f"无法读取目标图像: {img2_path}")

    img1_gray = cv2.cvtColor(img1_bgr, cv2.COLOR_BGR2GRAY)
    img2_gray = cv2.cvtColor(img2_bgr, cv2.COLOR_BGR2GRAY)

    x1, y1 = top_left
    x2, y2 = bottom_right

    roi1_gray = img1_gray[y1:y2, x1:x2]
    roi1_color = img1_bgr[y1:y2, x1:x2].copy()
    roi2_gray = img2_gray[y1:y2, x1:x2]
    roi2_color = img2_bgr[y1:y2, x1:x2].copy()

    # ==========================================
    # Stage 1: 基于 Image 1 生成 Base Mask
    # ==========================================
    binary = cv2.adaptiveThreshold(roi1_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 15, 2)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary_opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(binary_opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidate_wells = []  # 记录：(cx, cy, I1_intensity)
    intensities_1 = []

    # 1.1 形态学初筛
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

                        y_s, y_e = max(0, cy - radius_for_intensity), min(roi1_gray.shape[0],
                                                                          cy + radius_for_intensity + 1)
                        x_s, x_e = max(0, cx - radius_for_intensity), min(roi1_gray.shape[1],
                                                                          cx + radius_for_intensity + 1)
                        mean_i1 = np.mean(roi1_gray[y_s:y_e, x_s:x_e])

                        candidate_wells.append((cx, cy, mean_i1))
                        intensities_1.append(mean_i1)

    # 1.2 基于局部灰度剔除 Image 1 中的异常孔
    mean_val = np.mean(intensities_1)
    std_val = np.std(intensities_1)
    lower_bound = mean_val - std_multiplier * std_val
    upper_bound = mean_val + std_multiplier * std_val

    base_valid_wells = []  # Image 1 认定存活的孔
    mask_stage_1 = np.zeros_like(roi1_gray)

    for cx, cy, mean_i1 in candidate_wells:
        if lower_bound <= mean_i1 <= upper_bound:
            base_valid_wells.append((cx, cy, mean_i1))
            cv2.circle(mask_stage_1, (cx, cy), radius_for_intensity, 255, -1)
            cv2.circle(roi1_color, (cx, cy), radius_for_intensity, (0, 255, 0), 1)
        else:
            cv2.drawMarker(roi1_color, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 6, 1)

    # ==========================================
    # Stage 2: 用 Base Mask 验证 Image 2
    # ==========================================
    final_valid_wells = []
    ratios = []
    final_mask = np.zeros_like(roi2_gray)

    for cx, cy, mean_i1 in base_valid_wells:
        # 在 Image 2 中读取相同坐标的亮度
        y_s, y_e = max(0, cy - radius_for_intensity), min(roi2_gray.shape[0], cy + radius_for_intensity + 1)
        x_s, x_e = max(0, cx - radius_for_intensity), min(roi2_gray.shape[1], cx + radius_for_intensity + 1)
        mean_i2 = np.mean(roi2_gray[y_s:y_e, x_s:x_e])

        # 计算荧光保留率 (Image 2 亮度 / Image 1 亮度)
        retention_ratio = mean_i2 / mean_i1
        ratios.append(retention_ratio)

        # 判断：如果跌幅过大，视为干涸/气泡移位，予以剔除
        if retention_ratio >= min_retention_ratio:
            final_valid_wells.append((cx, cy))
            cv2.circle(final_mask, (cx, cy), radius_for_intensity, 255, -1)
            cv2.circle(roi2_color, (cx, cy), radius_for_intensity, (0, 255, 0), 1)  # Image2 存活标绿
        else:
            cv2.drawMarker(roi2_color, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 6, 1)  # Image2 死亡标红

    print(f"--- 筛选报告 ---")
    print(f"1. 形态学初筛: {len(candidate_wells)} 个")
    print(f"2. Stage 1 (Image 1 基准掩膜) 剩余: {len(base_valid_wells)} 个")
    print(f"3. Stage 2 (Image 2 时序验证) 最终保留: {len(final_valid_wells)} 个")

    # ==========================================
    # 绘图展示 (2x3 布局)
    # ==========================================
    plt.figure(figsize=(18, 10))

    # Row 1: Image 1 的情况
    plt.subplot(2, 3, 1)
    plt.title('Stage 1: Image 1 ROI & Wells')
    plt.imshow(cv2.cvtColor(roi1_color, cv2.COLOR_BGR2RGB))
    plt.axis('off')

    plt.subplot(2, 3, 2)
    plt.title('Stage 1: Base Mask')
    plt.imshow(mask_stage_1, cmap='gray')
    plt.axis('off')

    plt.subplot(2, 3, 3)
    plt.title('Stage 1: Intensity Histogram')
    plt.hist(intensities_1, bins=40, color='skyblue', edgecolor='black')
    plt.axvline(lower_bound, color='red', linestyle='dashed')
    plt.axvline(upper_bound, color='red', linestyle='dashed')

    # Row 2: Image 2 的情况
    plt.subplot(2, 3, 4)
    plt.title('Stage 2: Image 2 ROI (Tracking)')
    plt.imshow(cv2.cvtColor(roi2_color, cv2.COLOR_BGR2RGB))
    plt.axis('off')

    plt.subplot(2, 3, 5)
    plt.title('Stage 2: Final Mask')
    plt.imshow(final_mask, cmap='gray')
    plt.axis('off')

    plt.subplot(2, 3, 6)
    plt.title('Stage 2: Retention Ratio Distribution')
    plt.hist(ratios, bins=40, color='lightgreen', edgecolor='black')
    plt.axvline(min_retention_ratio, color='red', linestyle='dashed', label=f'Threshold: {min_retention_ratio}')
    plt.legend()

    plt.tight_layout()
    plt.show()

    return mask_stage_1, final_mask, final_valid_wells


def extract_and_normalize_curves(image_files, valid_wells, top_left, bottom_right, radius=3, baseline_cycles=(1, 5)):
    """
    遍历时序图像列表，提取微孔荧光曲线并进行生理学意义上的归一化 (Delta F / F0)。
    """
    num_cycles = len(image_files)
    num_wells = len(valid_wells)
    print(f"\n[阶段 2.5] 成功加载！准备提取 {num_wells} 个有效微孔的荧光曲线...")

    # 初始化数据矩阵: 行为微孔，列为循环数 (用 float 类型防止溢出)
    raw_data = np.zeros((num_wells, num_cycles), dtype=float)
    x1, y1 = top_left
    x2, y2 = bottom_right

    # 遍历所有图像，提取绝对荧光强度
    for t, img_path in enumerate(image_files):
        img_bgr = cv2.imread(img_path)
        if img_bgr is None: continue

        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        roi_gray = img_gray[y1:y2, x1:x2]

        for i, (cx, cy) in enumerate(valid_wells):
            y_s, y_e = max(0, cy - radius), min(roi_gray.shape[0], cy + radius + 1)
            x_s, x_e = max(0, cx - radius), min(roi_gray.shape[1], cx + radius + 1)
            raw_data[i, t] = np.mean(roi_gray[y_s:y_e, x_s:x_e])

        if (t + 1) % 10 == 0 or (t + 1) == num_cycles:
            print(f" -> 已处理至第 {t + 1}/{num_cycles} 个循环...")

    # 黄金归一化：Delta F / F0
    base_start, base_end = baseline_cycles
    baseline_vals = np.mean(raw_data[:, (base_start - 1):base_end], axis=1, keepdims=True)
    baseline_vals[baseline_vals == 0] = 1e-5  # 防止除零
    norm_data = (raw_data - baseline_vals) / baseline_vals

    # 大数据量可视化绘图
    cycles = np.arange(1, num_cycles + 1)
    plt.figure(figsize=(16, 7))

    plt.subplot(1, 2, 1)
    plt.title(f'Raw Fluorescence Curves (N={num_wells})')
    for i in range(num_wells):
        plt.plot(cycles, raw_data[i, :], color='gray', alpha=0.03)
    plt.xlabel('Cycle Number')
    plt.ylabel('Absolute Intensity (0-255)')
    plt.grid(True, linestyle='--', alpha=0.5)

    plt.subplot(1, 2, 2)
    plt.title('Normalized Curves (\u0394F / F\u2080)')
    for i in range(num_wells):
        plt.plot(cycles, norm_data[i, :], color='dodgerblue', alpha=0.03)
    plt.axhline(0, color='red', linestyle='dashed', linewidth=2)
    plt.xlabel('Cycle Number')
    plt.ylabel('Relative Fold Change')
    plt.grid(True, linestyle='--', alpha=0.5)

    plt.tight_layout()
    plt.show()

    return raw_data, norm_data


def check_spatial_alignment(folder_path, valid_wells, top_left, bottom_right, radius=3):
    """
    将基于基准图提取的有效微孔坐标，绘制到文件夹内的所有时序图片上，并输出到新文件夹。
    用于肉眼排查加热过程中是否发生物理位移（Thermal Drift）。
    """
    print("\n[附加诊断] 启动时序物理偏移校验...")

    # 1. 智能读取并排序图像
    all_images = glob.glob(os.path.join(folder_path, '*.[jt][pi][g]*'))
    if not all_images:
        print("错误：找不到图像。")
        return

    def sort_key(f):
        nums = re.findall(r'\d+', os.path.basename(f))
        return int(nums[-1]) if nums else 0

    all_images.sort(key=sort_key)

    # 2. 创建输出文件夹
    output_dir = os.path.join(folder_path, "Alignment_Check_Output")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    x1, y1 = top_left
    x2, y2 = bottom_right

    # 3. 遍历并绘制
    num_images = len(all_images)
    for t, img_path in enumerate(all_images):
        img_bgr = cv2.imread(img_path)
        if img_bgr is None: continue

        # 裁剪 ROI
        roi_color = img_bgr[y1:y2, x1:x2].copy()

        # 在该帧上画出绝对固定的微孔位置 (绿色细线空心圆)
        for cx, cy in valid_wells:
            cv2.circle(roi_color, (cx, cy), radius, (0, 255, 0), 1)

        # 生成输出文件名并保存
        base_name = os.path.basename(img_path)
        save_path = os.path.join(output_dir, f"Check_{base_name}")
        cv2.imwrite(save_path, roi_color)

        if (t + 1) % 10 == 0 or (t + 1) == num_images:
            print(f" -> 已生成校验图: {t + 1}/{num_images}")

    print(f"校验图已全部保存至: {output_dir}")
    print(">>> 建议：打开该文件夹，使用 Windows 照片查看器快速翻页，观察绿色圆圈与实际微孔是否发生相对移动。")

def classify_endpoint_fluorescence(img1_path, last_img_path, valid_wells, top_left, bottom_right, radius=3):
    """
    读取循环起点图 (img1) 和最后一张图 (last_img)，计算有效微孔的绝对亮度差值。
    使用 K-Means 自动聚类区分阴性孔和阳性孔，并绘制统计图和空间分布图。
    """
    print("\n[阶段 3] 启动终点法阴阳性判读 (End-point Classification)...")

    # 1. 读取并裁剪图像
    img1_bgr = cv2.imread(img1_path)
    last_img_bgr = cv2.imread(last_img_path)

    if img1_bgr is None: raise ValueError(f"无法读取基底图像: {img1_path}")
    if last_img_bgr is None: raise ValueError(f"无法读取终点图像: {last_img_path}")

    img1_gray = cv2.cvtColor(img1_bgr, cv2.COLOR_BGR2GRAY)
    last_img_gray = cv2.cvtColor(last_img_bgr, cv2.COLOR_BGR2GRAY)

    x1, y1 = top_left
    x2, y2 = bottom_right
    roi1_gray = img1_gray[y1:y2, x1:x2]
    roi_last_gray = last_img_gray[y1:y2, x1:x2]

    # 用于最终展示空间分布的彩色背景底图
    result_map = last_img_bgr[y1:y2, x1:x2].copy()

    # 2. 计算每个微孔的绝对亮度差值 (Last - img1)
    differences = []
    wells_data = []  # 存储详细信息 (cx, cy, diff)

    for cx, cy in valid_wells:
        y_s, y_e = max(0, cy - radius), min(roi1_gray.shape[0], cy + radius + 1)
        x_s, x_e = max(0, cx - radius), min(roi1_gray.shape[1], cx + radius + 1)

        mean_i1 = np.mean(roi1_gray[y_s:y_e, x_s:x_e])
        mean_last = np.mean(roi_last_gray[y_s:y_e, x_s:x_e])

        diff = mean_last - mean_i1
        differences.append(diff)
        wells_data.append((cx, cy, diff))

    differences = np.array(differences, dtype=np.float32)

    # 3. 自动聚类 (K-Means K=2) 寻找阴阳性分界线
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, labels, centers = cv2.kmeans(differences, 2, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

    if centers[0][0] > centers[1][0]:
        pos_label, neg_label = 0, 1
    else:
        pos_label, neg_label = 1, 0

    pos_center = centers[pos_label][0]
    neg_center = centers[neg_label][0]

    threshold = (pos_center + neg_center) / 2.0

    # 4. 分类统计与可视化标记
    positive_wells = []
    negative_wells = []

    for i, (cx, cy, diff) in enumerate(wells_data):
        if labels[i][0] == pos_label:
            positive_wells.append((cx, cy))
            cv2.circle(result_map, (cx, cy), radius, (0, 0, 255), -1)  # 阳性标红
        else:
            negative_wells.append((cx, cy))
            cv2.circle(result_map, (cx, cy), radius, (255, 0, 0), 1)  # 阴性标蓝空心

    # 计算泊松分布浓度
    n_total = len(valid_wells)
    n_pos = len(positive_wells)
    if n_pos == 0:
        lambda_val = 0.0
    elif n_pos == n_total:
        lambda_val = float('inf')
    else:
        lambda_val = -np.log(1 - (n_pos / n_total))

    print(f"--- 终点法判读结果 ---")
    print(f"总有效孔数: {n_total}")
    print(f"阴性孔数 (Negative): {len(negative_wells)}")
    print(f"阳性孔数 (Positive): {n_pos}")
    print(f"自动计算判定阈值 (Threshold): {threshold:.2f}")
    print(f"计算平均拷贝数 (Lambda, 拷贝/孔): {lambda_val:.4f}")

    # 5. 绘图展示
    plt.figure(figsize=(16, 7))

    plt.subplot(1, 2, 1)
    plt.title('End-point Intensity Difference (Last Cycle - Cycle 1)')
    plt.hist(differences[labels.flatten() == neg_label], bins=30, color='dodgerblue', alpha=0.7, label='Negative')
    plt.hist(differences[labels.flatten() == pos_label], bins=30, color='tomato', alpha=0.7, label='Positive')
    plt.axvline(threshold, color='black', linestyle='dashed', linewidth=2, label=f'Threshold: {threshold:.1f}')
    plt.xlabel('Intensity Difference (\u0394F)')
    plt.ylabel('Frequency (Number of Wells)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.5)

    plt.subplot(1, 2, 2)
    plt.title(f'Spatial Map: {n_pos} Positives (Red), {len(negative_wells)} Negatives (Blue)')
    plt.imshow(cv2.cvtColor(result_map, cv2.COLOR_BGR2RGB))
    plt.axis('off')

    plt.tight_layout()
    plt.show()

    return positive_wells, negative_wells, threshold
# ==========================================

# 测试运行
# ==========================================
if __name__ == "__main__":
    # --- 1. 全局功能开关 (Toggle) ---
    ENABLE_ALIGNMENT_CHECK = False  # 改为 True 开启：生成绿色圆圈对准校验图集
    ENABLE_CURVE_PLOT = False  # 改为 True 开启：提取并绘制全流程 S 型扩增曲线

    # --- 2. 参数配置区 ---
    FOLDER_PATH = r"D:\RT-dPCR IMG\1210-4\original"
    image1_file = "IMG_20251210180246331.jpg"  # 基准图1 (绝对本底)
    image2_file = "IMG_20251210164024289.jpg"  # 时序验证校验图 (仅用于滤除干涸孔)

    ROI_TOP_LEFT = (1273, 1285)
    ROI_BOTTOM_RIGHT = (3485, 2899)

    img1_path = os.path.join(FOLDER_PATH, image1_file)
    img2_path = os.path.join(FOLDER_PATH, image2_file)

    # --- 3. 自动获取全部图像序列并排序 ---
    all_images = glob.glob(os.path.join(FOLDER_PATH, '*.[jt][pi][g]*'))


    def sort_key(f):
        nums = re.findall(r'\d+', os.path.basename(f))
        return int(nums[-1]) if nums else 0


    all_images.sort(key=sort_key)

    if not all_images:
        print("错误：未找到任何图像文件，请检查文件夹路径。")
        exit()

    last_img_path = all_images[-1]
    print(f"已锁定终点图像: {os.path.basename(last_img_path)}")

    # [阶段 1 & 2]：执行微孔提取与时序筛查
    mask1, mask2, valid_wells = two_stage_spatiotemporal_filter(
        img1_path=img1_path,
        img2_path=img2_path,
        top_left=ROI_TOP_LEFT,
        bottom_right=ROI_BOTTOM_RIGHT,
        min_area=20, max_area=150, min_circularity=0.65,
        radius_for_intensity=3, std_multiplier=2.0, min_retention_ratio=0.85
    )

    if 'valid_wells' in locals() and len(valid_wells) > 0:

        # [开关控制]：生成对准校验图集
        if ENABLE_ALIGNMENT_CHECK:
            check_spatial_alignment(
                folder_path=FOLDER_PATH,
                valid_wells=valid_wells,
                top_left=ROI_TOP_LEFT,
                bottom_right=ROI_BOTTOM_RIGHT,
                radius=3
            )
        else:
            print("\n[跳过] 对准校验图集生成已关闭 (ENABLE_ALIGNMENT_CHECK = False)")

        # [开关控制]：提取全流程时序扩增曲线并绘制
        if ENABLE_CURVE_PLOT:
            raw_curves, norm_curves = extract_and_normalize_curves(
                image_files=all_images,  # 修复了报错：直接传入图片列表
                valid_wells=valid_wells,
                top_left=ROI_TOP_LEFT,
                bottom_right=ROI_BOTTOM_RIGHT,
                radius=3,
                baseline_cycles=(1, 5)
            )
        else:
            print("\n[跳过] 动态扩增曲线绘制已关闭 (ENABLE_CURVE_PLOT = False)")

        # [阶段 3]：终点荧光判读 (核心功能，常驻开启)
        pos_wells, neg_wells, cut_off = classify_endpoint_fluorescence(
            img1_path=img1_path,
            last_img_path=last_img_path,
            valid_wells=valid_wells,
            top_left=ROI_TOP_LEFT,
            bottom_right=ROI_BOTTOM_RIGHT,
            radius=3
        )

        print("\n>>> dPCR 图像处理管线全部执行完毕。")
    else:
        print("提取有效微孔失败，请检查前期提取阈值。")

