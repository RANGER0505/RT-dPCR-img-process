# 实时数字 PCR 图像处理与结果作图标准工作流

日期：2026-06-25

本文档用于回顾并规范当前 RT-dPCR 项目的数据处理、单实验探索和跨实验总图绘制流程。核心原则是：**每次实验先独立、标准化地产生可追溯数据；随后在该实验内部做探索和人工复核；最后只把已经整理好的结果汇总到跨实验图和线性度分析中。**

## 1. 总体判断

你提出的工作流是合理的，而且很适合当前课题阶段。它把工作分成三层：

```text
原始实验图像
    |
    v
阶段 1：单实验标准图像处理
    输出：workflow_result + 单实验 feature table
    |
    v
阶段 2：单实验探索、复核和科学问题分析
    输出：reviewed feature table + 探索图 + 复核记录
    |
    v
阶段 3：跨实验汇总作图和定量分析
    输出：总图、R2、Poisson 定量、论文/答辩图
```

这样做的好处是：

- 标准处理与探索性修改分开，避免为了某一张图临时改分类逻辑；
- 每次实验都有自己的原始输出、探索输出和复核记录；
- 跨实验分析只读取已经定稿的单实验结果，不直接修改单实验数据；
- 以后增加新浓度、新芯片或新批次时，只需要复制模板目录并更新配置。

## 2. 推荐目录结构

以后每次实验建议在 `D:\RT-dPCR IMG` 下单独建立一个实验文件夹。例如：

```text
D:\RT-dPCR IMG\
└── 2026-06-25_L858R_1e-4\
    ├── raw_images\                         # 原始采集图像，不覆盖、不手动改名
    ├── workflow_template\                  # 当次使用的标准图像处理脚本副本
    ├── workflow_result\                    # 阶段 1 标准处理输出
    ├── exploration\                        # 阶段 2 探索分析
    │   ├── scripts\
    │   ├── figures\
    │   ├── review\
    │   └── tables\
    ├── final\                              # 当次实验确认后的结果
    │   ├── reviewed_well_feature_table.csv
    │   ├── reviewed_classification_summary.csv
    │   └── figure_manifest.csv
    └── experiment_manifest.yaml            # 样本、浓度、芯片、循环数、脚本版本等元数据
```

跨实验总图建议单独放在一个 group 目录：

```text
D:\RT-dPCR IMG\
└── group\
    ├── experiment_index.csv                # 指向每次实验 final 结果
    ├── merged_reviewed_feature_table.csv   # 由各实验 final 表合并而来
    └── figure_outputs\
        ├── literature_style_four_concentration_curves.png
        ├── nature_new_method_endpoint_well_maps.png
        └── lambda_linearity_summary.csv
```

## 3. 阶段 1：单实验标准图像处理

### 目标

拿到一组实验图像后，先用统一模板完成图像处理和初始分类，生成稳定、可复现的单实验结果。

### 输入

- 原始荧光图像序列；
- 芯片参数；
- 实验参数：靶标、浓度、循环程序、曝光时间、FAM 通道等；
- 标准脚本模板，例如当前的 `workflow-template-v2.py` 或从它派生的实验脚本。

### 主要处理步骤

```text
图像读取
  -> 裁剪/校正/有效帧确认
  -> 微孔定位
  -> 图像特征筛孔
  -> 单孔曲线提取
  -> 终点分类
  -> mode-aware + kinetic 特征计算
  -> 阳性/阴性/异常/不确定初步标记
  -> 输出 workflow_result
```

### 单实验输出建议

每次实验应该在自己的 `workflow_result` 中输出：

| 文件 | 作用 |
|---|---|
| `positive_well_curves.csv` | 初始阳性孔逐循环曲线 |
| `negative_well_curves.csv` | 初始阴性孔逐循环曲线 |
| `combined_curve_outliers.csv` | 隐藏孔、气泡、漂移、异常曲线等标记 |
| `well_kinetic_feature_table.csv` | 单实验 mode-aware + kinetic 特征表 |
| `classification_summary.csv` | 阳性数、阴性数、有效孔数、阳性率 |
| `endpoint_well_map.png` | 终点芯片图 |
| `amplification_curves.png` | 单实验曲线图 |

### 单实验还是合并输出？

建议采用：**单实验先独立输出，跨实验时再合并。**

不要让阶段 1 直接只生成一个全局的 `auto_well_kinetic_feature_table.csv`。更稳妥的做法是：

```text
每次实验：
workflow_result/well_kinetic_feature_table.csv

跨实验汇总时：
group/merged_reviewed_feature_table.csv
```

理由：

- 单实验结果可以独立复核和重跑；
- 某次实验的人工修正不会误伤其他实验；
- 不同浓度、不同批次、不同芯片的参数差异可以保留在各自 manifest 中；
- 跨实验分析可以明确知道每一行来自哪个实验。

推荐每个孔至少保留这些字段：

```text
experiment_id
concentration_label
concentration_ng_uL
xy_key
x
y
classification_before
classification_after
display_call
is_uncertain
is_rejected
is_plot_outlier
cq
kinetic_score
occupancy_mode
review_status
reviewer_note
source_workflow_version
```

## 4. 阶段 2：单实验探索和人工复核

### 目标

这一层是最具探索性的。它不应该破坏阶段 1 的标准输出，而是在标准输出基础上提出科学问题、生成复核图、记录人工判断。

典型问题包括：

- 为什么阴性簇中出现上升曲线？
- 是否存在“雨滴效应”或边界孔？
- uncertain 孔是否应排除、显示为灰色，还是临时作为阳性显示？
- 某次实验是否存在蒸发、回填、气泡、芯片位移或局部温度异常？
- 单孔 Cq 分布是否与占有率、模板数或扩增效率有关？

### 推荐输入

阶段 2 读取阶段 1 的结果：

```text
workflow_result/positive_well_curves.csv
workflow_result/negative_well_curves.csv
workflow_result/combined_curve_outliers.csv
workflow_result/well_kinetic_feature_table.csv
```

### 推荐输出

```text
exploration/
├── figures/
│   ├── literature_style_curves.png
│   ├── uncertain_candidates_curves.png
│   ├── endpoint_map_review.png
│   └── rain_effect_diagnostics.png
├── review/
│   ├── manual_review_table.csv
│   └── reviewer_notes.md
└── tables/
    ├── reviewed_well_feature_table.csv
    └── uncertainty_candidate_table.csv
```

### 人工复核原则

人工复核一定要写入表格，而不是只留在聊天记录或图像里。建议使用：

| 字段 | 含义 |
|---|---|
| `manual_call` | 人工确认的 positive / negative / uncertain / rejected |
| `manual_reason` | 例如 rising negative、bubble、edge fill、late nonspecific |
| `review_time` | 复核时间 |
| `reviewer` | 复核者 |
| `source_figure` | 判断来自哪张图或哪个 viewer |

阶段 2 可以有多个探索脚本，但要遵守一个规则：

> 探索脚本可以产生新的显示口径和候选判断，但不能覆盖阶段 1 的原始标准结果。

例如这次 `10^-4 uncertain 暂时按阳性画红色` 就应该记录为：

```text
display_call = positive
classification_after = 原始分类结果不变
display_rule = ten4_uncertain_as_positive_for_visualization
```

## 5. 阶段 3：跨实验汇总作图和定量分析

### 目标

将多个已经完成阶段 2 的实验结果汇总，用统一风格绘制总图，并进行浓度线性、泊松校正、阳性率、Cq 分布等分析。

### 输入

阶段 3 不建议直接读取各实验的原始 `workflow_result`，而应读取每次实验确认后的 `final` 结果：

```text
group/experiment_index.csv
每次实验/final/reviewed_well_feature_table.csv
每次实验/final/reviewed_classification_summary.csv
```

### 推荐跨实验汇总表

`experiment_index.csv` 可以这样设计：

| 字段 | 示例 |
|---|---|
| `experiment_id` | `2026-06-25_L858R_1e-4` |
| `concentration_label` | `10^-4` |
| `concentration_ng_uL` | `1e-4` |
| `result_dir` | `D:\RT-dPCR IMG\2026-06-25_L858R_1e-4\final` |
| `feature_table` | `reviewed_well_feature_table.csv` |
| `curve_dir` | `workflow_result` |
| `display_rule` | `standard` / `uncertain_excluded` / `uncertain_as_positive` |

### 作图风格

跨实验总图可以沿用两套风格：

1. **Nature style**  
   用于论文、答辩、方法学总结，强调信息密度、科学逻辑和多面板一致性。

2. **Literature style**  
   用于和已有文献图对齐，例如荧光单位显示到 `10000-40000 a.u.`，曲线图更接近参考文献样式。

曲线图建议继续使用当前确定的显示方式：

```text
display_curve = smoothed_plotted_value - 同次实验早期循环 97.5% 分位 offset
scaled_display_curve = display_curve × scale_factor
```

其中 `scale_factor` 只是线性显示系数，不是归一化，不改变曲线形状和分类结果。

## 6. 当前代码如何对应这个工作流

| 当前文件 | 现在的角色 | 建议未来角色 |
|---|---|---|
| `workflow-template-v2.py` | 标准图像处理模板 | 阶段 1 单实验标准模板 |
| `workflow-1210-2.py` 等 | 某次实验的具体脚本 | 建议逐步改成配置驱动，减少复制代码 |
| `explore_kinetic_classifier_nature.py` | 跨四次实验探索 mode-aware + kinetic | 拆成单实验 kinetic 模板 + 跨实验汇总脚本 |
| `draw_new_method_nature_figures.py` | 当前 Nature 总图脚本 | 阶段 3 总图脚本模板 |
| `plot_literature_style_curves.py` | 当前文献风格总图脚本 | 阶段 3 literature-style 总图模板 |
| `build_rescued_well_reviewer.py` | 人工复核 viewer | 阶段 2 单实验复核工具 |

## 7. 建议优化后的脚本分层

未来可以逐步整理成下面结构：

```text
scripts/
├── experiment_processing/
│   ├── run_single_experiment.py
│   ├── workflow_template_v2.py
│   └── configs/
│       └── example_experiment.yaml
├── experiment_exploration/
│   ├── explore_single_experiment.py
│   ├── build_review_viewer.py
│   └── plot_single_experiment_curves.py
└── group_figures/
    ├── build_group_table.py
    ├── plot_nature_summary.py
    └── plot_literature_style_summary.py
```

短期不必大重构，可以先这样做：

1. 保留当前脚本；
2. 每次新实验复制 `workflow-template-v2.py` 到实验文件夹；
3. 每次实验生成自己的 `well_kinetic_feature_table.csv`；
4. 探索脚本只写入 `exploration/`；
5. 总图脚本只读取 `final/` 或 group 合并表。

## 8. 关于把绘图风格做成 Codex skill

可以，而且很适合。这个 skill 不应该负责重新发明分类算法，而应该负责：

- 读取 RT-dPCR 标准目录；
- 识别 `workflow_result`、`reviewed_well_feature_table.csv`、`experiment_index.csv`；
- 按你的固定风格输出 Nature style 或 literature style 图；
- 自动使用实验级 raw 曲线上下平移；
- 强制记录 `display_rule`，避免“图上改了分类但表里没记录”；
- 输出图像、source data 和简短审计表。

建议 skill 名称：

```text
rt-dpcr-figure-workflow
```

其实当前已经有一个接近的方向，后续可以继续扩展成你的个人标准技能。推荐先把本文档作为 skill 的方法规范，再单独创建 `SKILL.md`。

## 9. 推荐的最终标准流程

```text
Step 0  建立实验文件夹和 manifest
Step 1  复制标准 workflow 模板或调用统一 run_single_experiment.py
Step 2  运行标准图像处理，生成 workflow_result
Step 3  生成单实验 well_kinetic_feature_table.csv
Step 4  单实验探索：雨滴效应、uncertain、异常曲线、人工复核
Step 5  写入 reviewed_well_feature_table.csv
Step 6  将 reviewed 结果登记到 group/experiment_index.csv
Step 7  运行跨实验总图脚本
Step 8  输出总图、source data、R2、Poisson lambda 和图注说明
```

## 10. 关键结论

你的总体工作流应该定为：

> **标准化单实验处理 + 单实验探索复核 + 跨实验汇总作图。**

其中，`auto_well_kinetic_feature_table.csv` 这种表不应该再作为唯一原始来源，而应该升级为两级结构：

```text
单实验 feature table：每个实验自己生成、自己复核
跨实验 merged table：只用于总图和统计分析
```

这样最符合你课题的真实状态：仪器和算法已经跑通，后续重点不是每次临时改图，而是建立一个可解释、可追溯、能不断扩展的 RT-dPCR 数据处理体系。
