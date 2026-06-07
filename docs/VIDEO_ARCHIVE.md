# Video Archive

Generated videos are handled in the companion Hugging Face Dataset repository `XiaoranFace/VideoGenBias-Data` rather than as files committed to GitHub: <https://huggingface.co/datasets/XiaoranFace/VideoGenBias-Data>.

The Git repository stores:

- `data/metadata/video_index.csv`: one row per archived video.
- `data/metadata/coverage_report.csv`: availability and missing-count report.
- `data/videos/README.md`: placeholder explaining archive restoration.

The Hugging Face Dataset repository stores the real videos under:

```text
data/videos/<model>/<category>/<language>/prompt_<NN>/video_<II>.mp4
```

The code repository's `data/metadata/video_index.csv` records the corresponding archive paths under `archive_relative_path`.

Example archive path:

```text
videos/sora2/social_distance/en/prompt_01/video_01.mp4
```

When restoring the dataset locally for analysis, place or sync the dataset's video directory under:

```text
data/videos/
```

This yields local paths such as:

```text
data/videos/sora2/social_distance/en/prompt_01/video_01.mp4
```

If you maintain a private/local assembly workflow, copy videos into this structure only outside normal GitHub commits. The paper reproduction code does not depend on local source folders.

Any local assembly scripts should remain outside this repository and should not be committed.
