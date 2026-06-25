# Workflow v3：mode-aware + kinetic 标准分类模板说明

日期：2026-06-25

本文档说明当前新增的 `workflow-template-v3-mode-aware-kinetic.py`。它是现有 workflow v2 的升级后处理层，用于把 v2 的 endpoint/kmeans 初始分类升级为更适合实时数字 PCR 的 **mode-aware + kinetic** 分类结果。

## 1. 这个脚本是哪一个？

新增脚本：

```text
workflow-template-v3-mode-aware-kinetic.py
```

自动识别模式的原始探索代码来自：

```text
explore_kinetic_classifier_nature.py
```

其中核心函数是：

```python
infer_occupancy_mode()
classify_with_kinetics()
```

## 2. 它和 workflow v2 的关系

workflow v2 负责：

```text
原始图像
  -> 图像校正
  -> 微孔定位
  -> 有效孔筛选
  -> 单孔曲线提取
  -> endpoint/kmeans 初步分类
  -> workflow_result
```

workflow v3 负责：

```text
workflow_result
  -> 读取 positive/negative 曲线
  -> 读取 kmeans 或 endpoint 初始分类
  -> 提取单孔扩增动力学特征
  -> 根据阳性率自动判断 occupancy mode
  -> 用 mode-aware + kinetic 规则修正分类
  -> 输出 feature table、summary 和质控图
```

因此，v3 不是替代 v2 的图像处理部分，而是作为 v2 后面的标准分类升级层。

## 3. 为什么它比单纯 kmeans 更适合作为标准模板？

v2 的 kmeans 本质上主要看终点荧光强度：

```text
这个孔最后亮不亮？
```

但实时数字 PCR 已经有了每个循环的曲线，所以 v3 进一步利用：

```text
这个孔是不是按 PCR 扩增规律逐步变亮？
它什么时候起峰？
斜率是否合理？
后段是否持续上升？
是否只是噪声、气泡或晚期漂移？
```

因此 v3 的优势是：

| 维度 | v2 endpoint/kmeans | v3 mode-aware + kinetic |
|---|---|---|
| 主要依据 | 终点强度 | 终点强度 + 实时扩增曲线 |
| 是否考虑浓度状态 | 否 | 是，自动识别 saturated/high/mixed/sparse |
| 弱阳性识别 | 容易漏掉 | 可通过动力学特征救回 |
| 假阳性控制 | 主要靠终点阈值 | 可用 Cq、斜率、单调性、噪声标记 uncertain |
| 可解释性 | “终点亮/不亮” | “终点结果是否符合扩增动力学” |
| 适合 RT-dPCR 论文故事 | 一般 | 更强，因为体现实时采集价值 |

## 4. 自动识别 occupancy mode

v3 先根据 v2 初始阳性率判断实验所处模式：

```text
positive fraction >= 0.97      -> saturated
0.70 <= positive fraction <0.97 -> high
positive fraction <= 0.03      -> sparse
其他                           -> mixed
```

这些模式对应不同实验状态：

| 模式 | 含义 | 典型情况 |
|---|---|---|
| `saturated` | 几乎全阳 | 高浓度，接近或达到全阳 |
| `high` | 大多数阳性 | 高占有率，还有少量阴性 |
| `mixed` | 阳性和阴性都明显存在 | 中等浓度 |
| `sparse` | 只有少数阳性 | 低丰度/低浓度 |

这就是“mode-aware”的含义：分类规则不是对所有浓度一刀切，而是先判断这次实验处于什么占有状态。

## 5. kinetic 特征

每个孔会从实时曲线中提取以下特征：

| 特征 | 含义 |
|---|---|
| `baseline` | 前几个循环的基线均值 |
| `early_noise` | 早期噪声 |
| `endpoint_delta` | 终点相对基线增量 |
| `late_delta` | 后段相对基线增量 |
| `gain` | 后段信号相对中段低点的增益 |
| `max_slope` | 最大单循环上升斜率 |
| `late_slope` | 后段线性斜率 |
| `monotonic_frac` | 扩增段中上升步数比例 |
| `rise_len` | 最长连续上升长度 |
| `amplitude` | 全曲线幅度 |
| `cq` | 自适应阈值估计的单孔起峰循环 |
| `kinetic_score` | 综合动力学评分 |

其中 `robust z-score` 在每次实验内部计算，因此能适应不同批次的整体亮度差异。

## 6. 分类逻辑

### saturated 模式

如果初始阳性率已经超过 0.97，说明这次实验几乎全阳。此时不适合用少量终点低值硬判阴性，默认全部作为阳性。

### high 模式

大多数孔应该为阳性。只有当一个孔在动力学上表现为强阴性，才保留为阴性。

### mixed / sparse 模式

先继承 v2 的 endpoint/kmeans 分类，然后用动力学规则修正：

- 原本阴性但具有可靠扩增曲线的孔，可以救回为阳性；
- 原本阳性但曲线噪声大、无有效 Cq 或动力学矛盾的孔，会标记为 `uncertain`；
- 弱上升但证据不足的孔，也标记为 `uncertain`，后续人工复核或从定量中排除。

## 7. 默认输出

运行后会在：

```text
workflow_result/mode_aware_kinetic/
```

生成：

| 文件 | 作用 |
|---|---|
| `mode_aware_kinetic_feature_table.csv` | 单孔 v3 特征表和最终分类 |
| `mode_aware_kinetic_summary.csv` | 单实验汇总，含自动模式、阳性数、uncertain 数、lambda |
| `mode_aware_kinetic_curves.png/svg/pdf` | v3 分类曲线质控图 |
| `mode_aware_kinetic_endpoint_map.png/svg/pdf` | v3 endpoint 芯片图 |

## 8. 推荐运行方式

如果 v2 输出在：

```text
D:\RT-dPCR IMG\1210-4\workflow_result
```

运行：

```powershell
python workflow-template-v3-mode-aware-kinetic.py `
  --base-dir "D:\RT-dPCR IMG\1210-4" `
  --concentration-label "10^-4" `
  --concentration-ng-ul 1e-4
```

如果分类文件不在默认 `workflow_result/kmeans_classification.csv`，可以显式指定：

```powershell
python workflow-template-v3-mode-aware-kinetic.py `
  --result-dir "D:\RT-dPCR IMG\group\10-4\workflow_result" `
  --classification-file "D:\RT-dPCR IMG\group\10-4\workflow_result_target_balanced\target_balanced_classification.csv" `
  --concentration-label "10^-4" `
  --concentration-ng-ul 1e-4
```

默认使用：

```text
--occupancy-mode auto
```

如果你明确知道某次实验应该是什么模式，也可以手动覆盖：

```powershell
--occupancy-mode sparse
```

## 9. 本次验证结果

用 `10^-4` 实验验证：

```text
Auto mode: mixed
Before: 1254 / 7822 positive
After: 1255 / 7822 positive
Uncertain: 1558
```

输出路径：

```text
D:\RT-dPCR IMG\group\10-4\workflow_result\mode_aware_kinetic\
```

说明该模板能复现之前探索脚本中的 mode-aware + kinetic 核心结果。

## 10. 后续建议

短期建议：

1. 以后每次实验先跑 workflow v2；
2. 再跑 `workflow-template-v3-mode-aware-kinetic.py`；
3. 将 `mode_aware_kinetic_feature_table.csv` 作为该实验的标准分类结果；
4. 如果发现雨滴效应、uncertain 孔或特殊异常，再进入单实验探索脚本；
5. 最后把人工复核后的结果写入 `final/reviewed_well_feature_table.csv`。

长期建议：

- 将 v2 图像处理和 v3 kinetic 分类整合成一个统一入口；
- 用 `experiment_manifest.yaml` 管理浓度、样本、芯片、脚本版本和分类参数；
- 将 v3 输出作为后续 Nature style / literature style 总图的标准数据来源。
