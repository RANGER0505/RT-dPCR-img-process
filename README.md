# RT-dPCR 图像处理与交互式结果展示

本项目用于实时荧光数字 PCR（RT-dPCR）实验图像处理、终点微孔分类、曲线数据整理，以及交互式 HTML viewer 生成。当前 viewer 支持终点芯片微孔点击、单孔曲线查看、曲线簇高亮、结果图片浏览、照明场校正对比、筛选结果查看和终点定量分析展示。

## 主要功能

- 原始实验图像预处理：裁剪、照明场校正、稳定帧筛选等。
- 终点微孔识别与分类：区分阳性、阴性、被移除孔和异常曲线。
- RT-dPCR 曲线展示：查看单孔曲线、全部曲线簇，并高亮当前选中孔。
- Cq/Ct 辅助分析：对可判断的阳性扩增曲线给出阈值线和 Cq 标注。
- 结果图浏览：在网页中查看工作流导出的本地图像结果。
- 交互式网页输出：生成静态 HTML viewer，可本地打开，也可部署到 GitHub Pages。

## 目录说明

```text
.
├── run_experiment_viewer.py                 # 一键运行图像工作流并生成 viewer
├── workflow_original_to_endpoint_v2.py      # 标准 RT-dPCR 图像处理工作流
├── workflow_original_to_endpoint_all_positive.py
│                                           # 全阳性实验适用的处理工作流
├── interactive_chip_viewer.py              # 早期 viewer 相关脚本
├── interactive_viewer/                     # 当前生成的静态网页 viewer
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── assets/
└── .gitignore                              # 忽略原始图片、生成结果和临时文件
```

实验数据目录通常建议保持如下结构：

```text
实验目录/
├── original/             # 原始实验图片
├── cropped/              # 裁剪后的图片，由工作流生成
├── corrected/            # 照明场校正后的图片，由工作流生成
├── workflow_result/      # CSV、曲线图、分类图等工作流输出
└── interactive_viewer/   # 生成的交互式网页
```

## 快速开始

在 PowerShell 中进入本仓库目录：

```powershell
cd "D:\RT-dPCR_Device\image process python\test"
```

运行标准工作流并生成 viewer：

```powershell
python run_experiment_viewer.py --base-dir "D:\RT-dPCR IMG\1210-4"
```

如果是全阳性实验，例如 `1210-2`，使用：

```powershell
python run_experiment_viewer.py --base-dir "D:\RT-dPCR IMG\1210-2" --workflow all-positive
```

如果已经有 `workflow_result`，只想重新生成网页：

```powershell
python run_experiment_viewer.py --base-dir "D:\RT-dPCR IMG\1210-4" --skip-workflow
```

## 本地预览网页

生成 viewer 后，可以启动本地服务器：

```powershell
python run_experiment_viewer.py --base-dir "D:\RT-dPCR IMG\1210-4" --skip-workflow --serve --port 8766
```

然后在浏览器中打开：

```text
http://localhost:8766/
```

如果已经生成了 `interactive_viewer`，也可以直接用：

```powershell
python -m http.server 8766 --directory "D:\RT-dPCR_Device\image process python\test\interactive_viewer"
```

## Viewer 页面说明

- **Interactive Viewing Deck**：交互式看台。左侧为真实终点芯片微孔位置，右侧显示单孔曲线和全部曲线簇。
- **RT-dPCR Result Browser**：结果图浏览。用于查看 `workflow_result` 中导出的图像。
- **Image Correction QC**：图像校正质控。显示照明场校正前后、3D map、Stage 1/Stage 2 筛选结果。
- **Endpoint Quantification**：终点定量分析。显示终点荧光分类图、聚类散点图，并给出数字 PCR 泊松校正思路。

## 常用操作

在交互式看台中：

- 点击左侧微孔点：右侧显示对应单孔曲线，并在全部曲线中高亮。
- 输入孔序号并点击 `Go`：定位到指定孔。
- 点击 `Save PNG`：保存当前单孔曲线图片。
- 调整 `Well opacity`：改变芯片微孔叠加层透明度。
- 点击 `Show photo background`：显示终点实拍图背景，方便与原图对照。

## Ct/Cq 计算方法

viewer 中的 Ct/Cq 采用自适应阈值法（adaptive Cq）。在当前实现中，`Ct` 与 `Cq` 指同一个定量循环数：即单孔 RT-dPCR 荧光曲线第一次可靠超过阈值线时对应的循环数。`Cq` 是 MIQE 指南中更推荐的术语，界面中保留 `Ct` 是为了便于和常见 PCR 软件习惯对应。

设某个单孔的荧光曲线为：

```text
y_1, y_2, ..., y_n
```

首先对曲线做轻微移动平均平滑，当前使用半径为 1 的窗口：

```text
s_i = mean(y_{i-1}, y_i, y_{i+1})
```

边界点只使用实际存在的相邻数据。前 8 个循环作为基线区：

```text
B = {s_1, s_2, ..., s_8}
```

基线值使用中位数，减少早期异常点对基线的影响：

```text
baseline = median(B)
```

基线噪声使用稳健标准差估计：

```text
MAD = median(|B_i - median(B)|)
sigma_MAD = 1.4826 × MAD
sigma_STD = std(B)
baselineStd = max(sigma_MAD, 0.35 × sigma_STD)
```

其中 `1.4826 × MAD` 是在近似正态分布下将 MAD 转换为标准差量级的常用系数。随后计算峰值和扩增幅度：

```text
peak = max(s_i)
amplitude = peak - baseline
```

自适应阈值增量为：

```text
thresholdDelta = max(
  4 × baselineStd,
  0.16 × amplitude,
  0.8
)
```

为了避免阈值被放得过高，阈值增量还会被限制在扩增幅度的 35% 以内：

```text
thresholdDelta = min(thresholdDelta, 0.35 × amplitude)
```

最终阈值为：

```text
threshold = baseline + thresholdDelta
```

不是所有曲线都会给出 Ct/Cq。当前实现要求曲线同时满足扩增幅度和上升斜率要求：

```text
amplitude >= max(2, 4 × baselineStd)
```

并且：

```text
maxSlope >= max(2 × slopeNoise, 0.18 × baselineStd, 0.01)
```

其中：

```text
slope_i = s_i - s_{i-1}
slopeNoise = robustSigma({slope_2, ..., slope_8})
maxSlope = max(slope_i)
```

如果曲线不满足这些条件，说明缺少可靠扩增趋势，viewer 不会给出 Ct/Cq，而是显示 `NA`、`N/A` 或 `Review`。

Ct/Cq 的数值通过首次跨阈值点的线性插值得到。若存在某一循环位置满足：

```text
s_{i-1} < threshold 且 s_i >= threshold
```

则：

```text
fraction = (threshold - s_{i-1}) / (s_i - s_{i-1})
Ct = Cq = (i - 1) + fraction
```

因此 Ct/Cq 可以是小数，例如 `21.5` 表示曲线大约在第 21 和第 22 个循环之间穿过阈值线。

阴性孔原则上不应给出 Ct/Cq。阴性孔的荧光波动、基线漂移或偶然穿线不应解释为真实扩增，因此 viewer 对阴性孔直接显示：

```text
Ct/Cq = N/A
```

需要注意的是，终点阳性分类和实时扩增 Ct/Cq 是两个不同层面的判断。终点阳性表示最终荧光强度被分类为阳性，但如果实时曲线没有足够清晰的 S 型扩增趋势，仍然不应强行给出 Ct/Cq。

## Git 与数据管理

仓库主要管理代码和网页前端文件。原始实验图片、校正图片、生成的 CSV/大图等通常体积较大，已通过 `.gitignore` 忽略：

- `*.jpg`、`*.png`、`*.tif` 等图像文件
- `original/`
- `cropped/`
- `corrected/`
- `workflow_result/`
- `interactive_viewer/viewer_data.json`
- `interactive_viewer/assets/endpoint-photo.jpg`

这样可以避免把大型实验数据误提交到 GitHub。需要保存实验数据时，建议另行备份原始数据目录；Git 主要用于管理程序、viewer 页面和关键配置。

保存当前代码版本：

```powershell
git status
git add .
git commit -m "说明本次修改内容"
git push origin main
```

回看历史版本：

```powershell
git log --oneline
```

## 在线展示

本项目可以通过 GitHub Pages 发布为在线网页。需要注意：

- GitHub Pages 只能直接访问仓库中已提交的静态文件。
- 如果 viewer 依赖的 `viewer_data.json`、背景图或结果图片没有提交，线上页面可能会显示空白或缺少数据。
- 为了避免上传过大的实验原始数据，建议只发布经过筛选、压缩和脱敏后的展示用 viewer 数据。

当前仓库地址：

```text
https://github.com/RANGER0505/RT-dPCR-img-process.git
```

## 注意事项

- 阴性孔通常不应强行给出 Cq/Ct 值；Cq/Ct 应用于具有可靠 S 型扩增趋势且超过阈值的曲线。
- 终点阳性分类和实时扩增 Cq/Ct 是不同层面的判断：终点阳性表示最终荧光强度分类为阳性，不一定代表实时曲线具备可靠 Cq/Ct。
- 新实验建议先确认图像裁剪区域、照明场校正效果和异常曲线剔除结果，再生成最终 viewer。
