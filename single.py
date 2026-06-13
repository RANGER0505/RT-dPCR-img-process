import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def analyze_microwells(image_path, output_csv, output_image, brightness_threshold=128):
    """
    识别微孔、提取亮度、判断阴阳性并输出结果。

    参数:
        image_path (str): 输入图像的路径
        output_csv (str): 输出表格(CSV)的路径
        output_image (str): 输出标记后图像的路径
        brightness_threshold (int): 判断阴阳性的亮度阈值 (0-255)
    """
    # 1. 读取图像并转换为灰度图
    img = cv2.imread(image_path)
    if img is None:
        print(f"错误: 无法读取图像 '{image_path}'，请检查文件路径！")
        return None

    # 转换为灰度图以进行亮度分析和形状检测
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 使用中值滤波降噪，这对于去除图像上的小斑点很有帮助
    gray_blurred = cv2.medianBlur(gray, 5)

    # 2. 识别微孔 (使用霍夫圆变换)
    # 注意：这里的参数 (minDist, param1, param2, minRadius, maxRadius)
    # 非常依赖于你实际图片的微孔大小和密集度，通常需要微调。
    circles = cv2.HoughCircles(
        gray_blurred,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=30,  # 两个圆心之间的最小距离
        param1=50,  # 边缘检测的高阈值
        param2=30,  # 圆心检测阈值 (越小检测到的假圆越多)
        minRadius=15,  # 微孔的最小半径 (像素)
        maxRadius=40  # 微孔的最大半径 (像素)
    )

    results = []
    output_img = img.copy()

    if circles is not None:
        # 将坐标和半径转换为整数
        circles = np.uint16(np.around(circles))[0, :]

        for i, (x, y, r) in enumerate(circles):
            # 3. 提取微孔区域并计算平均亮度
            # 创建一个与原图大小相同的全黑掩码
            mask = np.zeros_like(gray)
            # 在掩码上画出一个白色的实心圆，代表当前微孔区域
            cv2.circle(mask, (x, y), r, 255, thickness=-1)

            # 计算在掩码区域内（即微孔内部）的平均灰度值（亮度）
            mean_val = cv2.mean(gray, mask=mask)[0]

            # 4. 判断阴阳性
            is_positive = mean_val >= brightness_threshold
            status = "阳性" if is_positive else "阴性"

            results.append({
                "微孔编号": i + 1,
                "X坐标": x,
                "Y坐标": y,
                "半径": r,
                "平均亮度": round(mean_val, 2),
                "结果": status
            })

            # 5. 在输出图像上绘制结果
            # 阳性画绿圈，阴性画红圈
            color = (0, 255, 0) if is_positive else (0, 0, 255)
            cv2.circle(output_img, (x, y), r, color, 2)

            # 在孔旁边标上编号
            cv2.putText(output_img, str(i + 1), (x - 10, y + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        # 6. 生成表格并保存
        df = pd.DataFrame(results)
        # 使用 utf-8-sig 编码以防止在 Excel 中打开时中文乱码
        df.to_csv(output_csv, index=False, encoding='utf-8-sig')
        print(f"✅ 成功! 分析了 {len(circles)} 个微孔。")
        print(f"📄 表格已保存至: {output_csv}")

        # 7. 显示并保存带有标记的图片
        plt.figure(figsize=(10, 8))
        # OpenCV 默认使用 BGR 颜色空间，Matplotlib 使用 RGB，需要转换一下
        plt.imshow(cv2.cvtColor(output_img, cv2.COLOR_BGR2RGB))
        plt.title(f"Microwell Analysis (Green=Positive, Red=Negative) | Threshold: {brightness_threshold}")
        plt.axis('off')
        plt.savefig(output_image, bbox_inches='tight', dpi=300)
        plt.show()
        print(f"🖼️ 图片已保存至: {output_image}")

        return df
    else:
        print("⚠️ 未检测到任何微孔，请尝试调整 HoughCircles 函数的参数！")
        return None


# ==========================================
# 运行示例
# ==========================================
if __name__ == "__main__":
    # 请将 "your_image.jpg" 替换为你实际的图片路径
    IMAGE_INPUT = r"D:\RT-dPCR IMG\dPCR-YR\test\9-40.jpg"
    CSV_OUTPUT = "microwell_results.csv"
    IMAGE_OUTPUT = "microwell_annotated.jpg"

    # 假设亮度大于 150 为阳性，可根据实际情况修改
    THRESHOLD = 150

    # 执行分析
    # 注意：如果没有准备好测试图片，直接运行会提示“无法读取图像”
    # result_df = analyze_microwells(IMAGE_INPUT, CSV_OUTPUT, IMAGE_OUTPUT, brightness_threshold=THRESHOLD)

    # 如果检测成功，可以在控制台打印出前 5 行数据看看
    # if result_df is not None:
    #    print("\n部分数据预览:")
    #    print(result_df.head())