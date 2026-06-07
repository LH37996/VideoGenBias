# Hosting And Upload

This project uses two public repositories:

```text
GitHub:              VideoGenBias
Hugging Face Dataset: VideoGenBias-Data
```

Replace the placeholders below before running commands:

- `<your-github-username>`: your GitHub username or organization.
- `<your-hf-username>`: your Hugging Face username or organization.

Keep the split strict:

- GitHub stores only code, documentation, prompts, metadata tables, annotations, summary counts, figures, and reports.
- Hugging Face stores the real generated video files and the dataset metadata needed to download them.
- Do not upload `VideoGenBias-Data` or raw video files to GitHub.

## GitHub Code Repository

GitHub stores the paper-facing code, documentation, metadata tables, and result tables. It does not store generated videos.

Create the GitHub repository in the browser:

1. Open <https://github.com/new>.
2. Set **Repository name** to `VideoGenBias`.
3. Choose the account or organization that should own the repository.
4. Choose **Public** or **Private**.
5. Leave **Add a README file**, **Add .gitignore**, and **Choose a license** unchecked, because this local repository already contains those files.
6. Click **Create repository**.

After the empty repository exists, push this local repository from Terminal:

```bash
cd "/Users/lihan/Documents/研究生科研/VideoUnfairness/VideoGenBias"
git init
git add .
git commit -m "Initial VideoGenBias code release"
git branch -M main
git remote add origin https://github.com/<your-github-username>/VideoGenBias.git
git push -u origin main
```

If this repository already has the initial commit, use the shorter push sequence:

```bash
cd "/Users/lihan/Documents/研究生科研/VideoUnfairness/VideoGenBias"
git branch -M main
git remote add origin https://github.com/<your-github-username>/VideoGenBias.git
git push -u origin main
```

If `git remote add origin ...` says that `origin` already exists, update it instead:

```bash
git remote set-url origin https://github.com/<your-github-username>/VideoGenBias.git
git push -u origin main
```

Before pushing, confirm that videos are not tracked:

```bash
git status --short
find . -type f \( -iname "*.mp4" -o -iname "*.mov" -o -iname "*.m4v" -o -iname "*.avi" -o -iname "*.mkv" -o -iname "*.webm" \)
```

The `find` command should print nothing inside the GitHub code repository.

## Hugging Face Dataset Repository

Hugging Face stores the real generated videos and dataset metadata.

Create the Hugging Face Dataset repository in the browser:

1. Open <https://huggingface.co/new-dataset>.
2. Set **Dataset name** to `VideoGenBias-Data`.
3. Choose the owner namespace that matches `<your-hf-username>`.
4. Choose **Public** or **Private**.
5. Click **Create dataset**.

Local folder:

```text
/Users/lihan/Documents/研究生科研/VideoUnfairness/VideoGenBias-Data
```

Upload the dataset folder from Terminal after the dataset repository exists:

```bash
pip install -U "huggingface_hub[cli]"
hf auth login
HF_XET_HIGH_PERFORMANCE=1 hf upload-large-folder \
  <your-hf-username>/VideoGenBias-Data \
  "/Users/lihan/Documents/研究生科研/VideoUnfairness/VideoGenBias-Data" \
  --repo-type=dataset \
  --num-workers=16
```

Use the real Hugging Face namespace in place of `<your-hf-username>`. For example, if the dataset URL should be `https://huggingface.co/datasets/alice/VideoGenBias-Data`, the first upload argument should be `alice/VideoGenBias-Data`.

Users can download the dataset with:

```bash
hf download <your-hf-username>/VideoGenBias-Data --repo-type dataset --local-dir VideoGenBias-Data
```

After downloading, users can restore videos next to the code repository or copy them into `VideoGenBias/data/videos/` for local analysis. The restored videos remain ignored by Git and should stay out of GitHub commits.
