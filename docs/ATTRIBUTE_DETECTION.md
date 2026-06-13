# Attribute Detection Methodology

This document describes the paper-facing code in `code/attribute_detection/`.
The module is for rerunning face-level gender and race/skin-tone attribute
extraction from generated videos or images.

## Scope

The attribute detector provides:

- Gender detection with DeepFace or Face++.
- Race/skin-tone detection with CLIP prompt classification.
- Face detection with RetinaFace.
- Video-level aggregation through frame sampling and lightweight face-track
  matching.

Face++ credentials are never stored in this repository. If Face++ is used, set:

```bash
export FACEPP_API_KEY="..."
export FACEPP_API_SECRET="..."
```

## Algorithm

For each image or sampled video frame:

1. Detect faces with RetinaFace.
2. Optionally verify each crop as a face with CLIP prompts.
3. For race/skin-tone, extract an HSV skin-colored crop when available.
4. Classify the crop with two CLIP prompt sets:
   - Detailed prompts for six skin-tone descriptions.
   - Auxiliary prompts for fair/light/medium/tan/dark/very dark skin color.
5. Fuse the two probability vectors with a 0.7/0.3 weighted average.
6. Map six detailed labels to the paper categories:
   - `white`
   - `yellow`
   - `black`
7. For gender, use either:
   - DeepFace local inference, or
   - Face++ API with explicit user-provided credentials.

For videos, sampled frame detections are matched into face tracks using IoU and,
when enabled, CLIP image-feature cosine similarity. Track-level summaries report
dominant gender, dominant race/skin label, and per-track category counts.

## Usage

Install the base environment first:

```bash
pip install -r requirements.txt
```

Install optional attribute-detection dependencies:

```bash
pip install -r requirements-detection.txt
```

Run on one video with DeepFace gender detection:

```bash
python code/attribute_detection/run_attribute_detection.py \
  --input data/videos/sora/illegal_behavior/en/prompt_01/video_01.mp4 \
  --output-dir results/reports/attribute_detection/example \
  --gender-backend deepface \
  --sample-frames 30
```

Run with Face++ gender detection:

```bash
export FACEPP_API_KEY="..."
export FACEPP_API_SECRET="..."
python code/attribute_detection/run_attribute_detection.py \
  --input data/videos/sora/illegal_behavior/en/prompt_01/video_01.mp4 \
  --output-dir results/reports/attribute_detection/example_facepp \
  --gender-backend facepp
```

Outputs:

- `frame_detections.csv`
- `track_summaries.csv`
- `attribute_detection.json`

These outputs can be aggregated into the count tables consumed by
`code/bias_analysis/`.
