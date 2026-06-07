# VideoGenBias

VideoGenBias is the paper code repository for studying unfairness in text-to-video generation. It contains prompt metadata, video manifests, annotation/count tables, analysis code, and reproduction entry points used for the manuscript. The real generated videos are stored in the companion Hugging Face Dataset repository `VideoGenBias-Data`, which is designed for large-file synchronization and community updates.

The repository layout follows a compact research-replication pattern:

```text
data/      prompts, video manifests, annotations, summary counts, metadata
code/      bias metrics, social-distance analysis, reproduction scripts
results/   generated tables, figures, and markdown reports
docs/      data and method documentation
```

## Data Access

The companion dataset repository is hosted on Hugging Face Hub as:

```text
https://huggingface.co/datasets/XiaoranFace/VideoGenBias-Data
```

Download it with:

```bash
pip install -U "huggingface_hub[cli]"
hf download XiaoranFace/VideoGenBias-Data --repo-type dataset --local-dir VideoGenBias-Data
```

The dataset repository contains the real videos under:

```text
VideoGenBias-Data/data/videos/
```

To restore videos inside this code repository, copy or sync that directory to:

```text
VideoGenBias/data/videos/
```

## Data Scope

Videos are organized as:

```text
data/videos/<model>/<category>/<language>/prompt_<NN>/video_<II>.mp4
```

Models:

- `sora`
- `sora2`
- `seedance1.5`
- `seedance2.0`
- `wan2.1`
- `wan2.6`

Categories:

- `illegal_behavior`
- `personality`
- `occupation`
- `social_distance`

Rules used in this release:

- `doubao` videos are treated as `seedance1.5`.
- Directories such as `5_2` and `9_2` are continuations of prompt 5 and prompt 9.
- Each prompt contains up to 18 videos. If fewer than 18 are currently available, the dataset repository stores the available videos only.
- `data/metadata/coverage_report.csv` records cells with fewer than 18 videos.
- The social-distance experiment includes only `sora2` and `seedance2.0`.
- `seedance2.0` videos outside social distance are not part of this repository and are not counted as missing.

The companion dataset repository stores `data/metadata/video_index.csv`, whose `relative_path` column gives the actual path for each available video. This code repository keeps lightweight metadata and analysis code so GitHub remains easy to clone.

Local source-folder assembly and video-copy scripts are not part of this repository. The repository is intended to contain the finalized paper metadata, count tables, annotations, and code needed to reproduce the analyses from the released dataset.

## Reproduction

Create an environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Reproduce tables and figures from repository data:

```bash
python code/reproduce/reproduce_bias_tables.py
python code/reproduce/reproduce_distance_tables.py
python code/reproduce/reproduce_figures.py
```

Outputs are written to:

```text
results/tables/
results/figures/
results/reports/
```

## Repository Contents

- `data/prompts/prompts.csv`: prompt labels and prompt text.
- `data/videos/`: placeholder for restoring the Hugging Face dataset videos locally; generated videos are not committed to GitHub.
- `data/annotations/video_level_annotations.csv`: video-level annotations used in the distance analysis.
- `data/summary_counts/`: count tables and real-world baseline tables used by the bias metrics.
- `data/metadata/video_index.csv`: one row per archived video, with archive-relative path.
- `data/metadata/coverage_report.csv`: expected, available, and missing video counts per model/category/language/prompt cell.
- `code/bias_analysis/`: scalar and vector bias metrics, reports, and visualizations.
- `code/distance_analysis/`: HND-based pairwise distance analysis pipeline.
- `code/reproduce/`: manuscript reproduction entry points.

## Citation

If you use this repository, cite the associated manuscript and this repository. A machine-readable citation file is provided in `CITATION.cff`.
