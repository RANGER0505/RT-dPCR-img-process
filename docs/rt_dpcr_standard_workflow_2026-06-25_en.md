# Standard Workflow for Real-Time Digital PCR Image Processing and Figure Generation

Date: 2026-06-25

This document reviews and standardizes the current RT-dPCR workflow for image processing, single-experiment exploration, manual review, and multi-experiment figure generation. The guiding principle is: **process each experiment independently with a stable template, explore and review that experiment locally, and only then merge reviewed results for group-level figures and quantitative analysis.**

## 1. Overall Assessment

The workflow you proposed is well aligned with the current project stage. It can be organized into three layers:

```text
Raw experimental images
    |
    v
Stage 1: Standard single-experiment image processing
    Output: workflow_result + single-experiment feature table
    |
    v
Stage 2: Single-experiment exploration and manual review
    Output: reviewed feature table + exploratory figures + review records
    |
    v
Stage 3: Multi-experiment summary figures and quantitative analysis
    Output: summary figures, R2 analysis, Poisson quantification, thesis/presentation figures
```

This separation is important because:

- standard processing is not mixed with exploratory adjustments;
- each experiment remains independently reproducible;
- manual review decisions are traceable;
- group-level analyses read finalized experiment-level outputs instead of modifying raw experiment results;
- new concentrations, chips, or batches can be added by copying a standard template and updating metadata.

## 2. Recommended Directory Structure

Each future experiment should have its own folder under `D:\RT-dPCR IMG`. For example:

```text
D:\RT-dPCR IMG\
└── 2026-06-25_L858R_1e-4\
    ├── raw_images\                         # Raw image sequence; never overwrite
    ├── workflow_template\                  # Copy of the standard processing template used for this run
    ├── workflow_result\                    # Stage 1 standard outputs
    ├── exploration\                        # Stage 2 exploratory analysis
    │   ├── scripts\
    │   ├── figures\
    │   ├── review\
    │   └── tables\
    ├── final\                              # Reviewed and finalized outputs for this experiment
    │   ├── reviewed_well_feature_table.csv
    │   ├── reviewed_classification_summary.csv
    │   └── figure_manifest.csv
    └── experiment_manifest.yaml            # Target, concentration, chip, cycles, script version, etc.
```

Group-level analysis should live in a separate directory:

```text
D:\RT-dPCR IMG\
└── group\
    ├── experiment_index.csv                # Points to finalized experiment outputs
    ├── merged_reviewed_feature_table.csv   # Built from single-experiment final tables
    └── figure_outputs\
        ├── literature_style_four_concentration_curves.png
        ├── nature_new_method_endpoint_well_maps.png
        └── lambda_linearity_summary.csv
```

## 3. Stage 1: Standard Single-Experiment Processing

### Goal

Given one experimental image sequence, run a fixed and reproducible image-processing template to generate well curves, endpoint calls, and kinetic features.

### Inputs

- raw fluorescence images;
- chip parameters;
- experimental metadata: target, concentration, thermal cycling program, exposure time, FAM channel, etc.;
- a standard workflow script, such as the current `workflow-template-v2.py` or a derived per-experiment script.

### Main Steps

```text
Read images
  -> crop / correct / validate frames
  -> locate microwells
  -> filter wells by image features
  -> extract single-well fluorescence curves
  -> endpoint classification
  -> compute mode-aware + kinetic features
  -> flag positive / negative / abnormal / uncertain wells
  -> export workflow_result
```

### Recommended Outputs

Each experiment should export its own `workflow_result`:

| File | Purpose |
|---|---|
| `positive_well_curves.csv` | Cycle-by-cycle curves for initially positive wells |
| `negative_well_curves.csv` | Cycle-by-cycle curves for initially negative wells |
| `combined_curve_outliers.csv` | Hidden, bubble-like, shifted, or abnormal curve flags |
| `well_kinetic_feature_table.csv` | Single-experiment mode-aware + kinetic feature table |
| `classification_summary.csv` | Positive wells, negative wells, valid wells, positive fraction |
| `endpoint_well_map.png` | Endpoint chip map |
| `amplification_curves.png` | Single-experiment curve plot |

### Per-Experiment or Merged Output?

The recommended answer is: **export each experiment independently first, then merge later.**

Avoid making Stage 1 directly produce only one global `auto_well_kinetic_feature_table.csv`. A safer structure is:

```text
Per experiment:
workflow_result/well_kinetic_feature_table.csv

For group analysis:
group/merged_reviewed_feature_table.csv
```

Reasons:

- each experiment can be reviewed and rerun independently;
- manual corrections from one experiment do not affect another experiment;
- batch-specific differences remain documented in each manifest;
- group-level analysis can always trace every row back to its source experiment.

Recommended per-well fields:

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

## 4. Stage 2: Single-Experiment Exploration and Manual Review

### Goal

This is the most exploratory layer. It should not overwrite Stage 1 outputs. Instead, it should generate diagnostic figures, candidate flags, and manual review records based on the standard outputs.

Typical scientific questions include:

- Why do some endpoint-negative wells show rising curves?
- Is there a droplet/rain-like population?
- Should uncertain wells be excluded, plotted in gray, or temporarily displayed as positives?
- Is there evidence of evaporation, refilling, bubbles, chip drift, or local thermal non-uniformity?
- Does the single-well Cq distribution reflect occupancy, template number, or amplification efficiency?

### Recommended Inputs

Stage 2 should read Stage 1 outputs:

```text
workflow_result/positive_well_curves.csv
workflow_result/negative_well_curves.csv
workflow_result/combined_curve_outliers.csv
workflow_result/well_kinetic_feature_table.csv
```

### Recommended Outputs

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

### Manual Review Rules

Manual review should be stored as data, not only remembered in chat or figures. Recommended fields:

| Field | Meaning |
|---|---|
| `manual_call` | Manual positive / negative / uncertain / rejected decision |
| `manual_reason` | For example: rising negative, bubble, edge fill, late nonspecific |
| `review_time` | Review timestamp |
| `reviewer` | Reviewer name |
| `source_figure` | Figure or viewer used for review |

Exploration scripts may generate new display rules, but they should not overwrite the original Stage 1 classification.

For example, if `10^-4` uncertain wells are temporarily drawn as red positives:

```text
display_call = positive
classification_after = original classification remains unchanged
display_rule = ten4_uncertain_as_positive_for_visualization
```

## 5. Stage 3: Multi-Experiment Summary Figures and Quantitative Analysis

### Goal

Merge finalized outputs from multiple experiments and generate summary figures, concentration linearity analysis, Poisson lambda estimates, positive fractions, and Cq distributions.

### Inputs

Stage 3 should read reviewed experiment-level results:

```text
group/experiment_index.csv
each experiment/final/reviewed_well_feature_table.csv
each experiment/final/reviewed_classification_summary.csv
```

### Recommended Group Index

`experiment_index.csv` may use:

| Field | Example |
|---|---|
| `experiment_id` | `2026-06-25_L858R_1e-4` |
| `concentration_label` | `10^-4` |
| `concentration_ng_uL` | `1e-4` |
| `result_dir` | `D:\RT-dPCR IMG\2026-06-25_L858R_1e-4\final` |
| `feature_table` | `reviewed_well_feature_table.csv` |
| `curve_dir` | `workflow_result` |
| `display_rule` | `standard` / `uncertain_excluded` / `uncertain_as_positive` |

### Figure Styles

Two figure styles should be kept:

1. **Nature style**  
   For thesis, defense, and method-oriented figures. It emphasizes evidence logic, consistency, and dense but readable multi-panel layout.

2. **Literature style**  
   For comparison with published figures, such as amplification curves displayed in the `10000-40000 a.u.` range.

For curve plots, continue using the experiment-level raw-curve vertical shift:

```text
display_curve = smoothed_plotted_value - early-cycle 97.5th percentile offset of the same experiment
scaled_display_curve = display_curve × scale_factor
```

The `scale_factor` is only a linear display conversion. It is not normalization and does not change curve shape or classification.

## 6. Mapping to Current Code

| Current file | Current role | Suggested future role |
|---|---|---|
| `workflow-template-v2.py` | Standard image-processing template | Stage 1 single-experiment template |
| `workflow-1210-2.py`, etc. | Experiment-specific scripts | Gradually replace with config-driven runs |
| `explore_kinetic_classifier_nature.py` | Multi-experiment mode-aware + kinetic exploration | Split into single-experiment kinetic template and group summary script |
| `draw_new_method_nature_figures.py` | Current Nature-style summary figure script | Stage 3 Nature-style group figure template |
| `plot_literature_style_curves.py` | Current literature-style summary curve script | Stage 3 literature-style group figure template |
| `build_rescued_well_reviewer.py` | Manual review viewer | Stage 2 single-experiment review tool |

## 7. Suggested Script Layers

A future cleaned-up structure could be:

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

Short term, no large refactor is required. A practical next step is:

1. keep current scripts;
2. copy `workflow-template-v2.py` into each new experiment folder;
3. export a per-experiment `well_kinetic_feature_table.csv`;
4. keep all exploratory outputs inside `exploration/`;
5. make group-level scripts read only `final/` or a group merged table.

## 8. Turning the Style into a Codex Skill

Yes, the plotting style can be turned into a Codex skill. The skill should not replace the classification algorithm. Instead, it should:

- read the RT-dPCR standard directory structure;
- detect `workflow_result`, `reviewed_well_feature_table.csv`, and `experiment_index.csv`;
- generate Nature-style or literature-style RT-dPCR figures;
- use experiment-level raw-curve vertical shifting automatically;
- require an explicit `display_rule`;
- export figures, source data, and a short audit table.

Suggested skill name:

```text
rt-dpcr-figure-workflow
```

The current project already has the foundation for this. This document can serve as the method specification before writing the actual `SKILL.md`.

## 9. Recommended Final SOP

```text
Step 0  Create experiment folder and manifest
Step 1  Copy the standard workflow template or run a unified single-experiment script
Step 2  Run standard image processing and export workflow_result
Step 3  Generate single-experiment well_kinetic_feature_table.csv
Step 4  Explore rain effect, uncertain wells, abnormal curves, and manual review
Step 5  Write reviewed_well_feature_table.csv
Step 6  Register reviewed results in group/experiment_index.csv
Step 7  Run group-level figure scripts
Step 8  Export summary figures, source data, R2, Poisson lambda, and figure notes
```

## 10. Key Conclusion

The recommended workflow is:

> **standardized single-experiment processing + single-experiment exploration/review + multi-experiment summary figure generation.**

The current global `auto_well_kinetic_feature_table.csv` should evolve into a two-level structure:

```text
single-experiment feature table: generated and reviewed within each experiment
merged group table: used only for summary figures and statistical analysis
```

This structure matches the real state of the project: the instrument and image-processing pipeline already work, and the next step is to build a traceable and extensible RT-dPCR data analysis system rather than repeatedly editing one-off figures.
