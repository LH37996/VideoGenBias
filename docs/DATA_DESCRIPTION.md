# Data Description

This repository stores the code-side metadata used for the VideoGenBias manuscript. The real generated videos are stored in the companion Hugging Face Dataset repository `XiaoranFace/VideoGenBias-Data`: <https://huggingface.co/datasets/XiaoranFace/VideoGenBias-Data>.

## Directory Structure

```text
data/
  prompts/
    prompts.csv
  videos/
    README.md      # placeholder in GitHub; real videos live in VideoGenBias-Data
  annotations/
    video_level_annotations.csv
  summary_counts/
    results_cn.csv
    results_en.csv
    real_world_baselines.csv
  metadata/
    video_index.csv
```

## Models

The main non-distance dimensions use:

- `genie3`
- `sora`
- `sora2`
- `seedance1.5`
- `veo3.1`
- `wan2.1`
- `wan2.6`

The social-distance dimension uses:

- `genie3`
- `sora2`
- `seedance2.0`
- `veo3.1`

`doubao` source videos are normalized to `seedance1.5`. `seedance2.0` videos
outside social distance, and social-distance folders for models other than
`genie3`, `sora2`, `seedance2.0`, and `veo3.1`, are not included in this
release.

## Categories

| Category | Description | Main sensitive attribute |
| --- | --- | --- |
| `illegal_behavior` | illegal or suspicious behavior prompts | gender and skin tone |
| `personality` | personality/behavioral trait prompts | gender |
| `occupation` | occupation prompts | gender and skin tone |
| `social_distance` | pedestrian interpersonal-distance prompts | race/skin tone |

## Prompt and Video Organization

Each category contains 10 prompts in Chinese and English. Each prompt cell follows the canonical target of 18 generated videos. The released video files are enumerated in `data/metadata/video_index.csv`.

Video files are handled in a Hugging Face Dataset repository and are not committed to GitHub. The companion dataset uses this path convention:

```text
data/videos/<model>/<category>/<language>/prompt_<NN>/video_<II>.mp4
```

The code repository can be used together with a local copy of the dataset by placing the dataset's `data/videos/` directory at `VideoGenBias/data/videos/`.

## Metadata Tables

`video_index.csv` contains one row per available archived video.

Key columns:

- `video_id`: stable video identifier.
- `model`: normalized model name.
- `category`: normalized category name.
- `language`: `zh` or `en`.
- `prompt_id`: integer prompt identifier, 1 through 10.
- `video_number`: integer video identifier within the prompt cell.
- `archive_relative_path`: path inside the video archive, relative to the dataset's `data/` directory.
- `source_collection`: source collection label used during assembly.
- `source_file_name`: original file name, without local source directory.
- `file_size_bytes`: source file size in bytes.

## Notes

Directories with suffixes such as `_2` are treated as additional outputs for the same prompt number, not as a new prompt. For example, `5_2` contributes to prompt 5.
