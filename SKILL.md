---
name: shutterstock-upload
description: Upload photos to Shutterstock Contributor via FTPS with AI-generated descriptions, keywords, and categories using a local Ollama vision model
license: MIT
compatibility: opencode
metadata:
  domain: stock-photography
  workflow: publishing
---

## What this skill does

Takes JPEG/TIFF photos from a target folder and:

1. **Analyzes** each image with a local Ollama vision model → generates a Shutterstock-compliant title/description (≤200 chars), 20-35 keywords, and a category from Shutterstock's 26 categories
2. **Uploads** each file to ftp.shutterstock.com via FTPS using contributor credentials
3. **Generates** a shutterstock_metadata.csv file ready to upload on submit.shutterstock.com

## Prerequisites

| Requirement | Check |
|---|---|
| Ollama installed and running | `ollama --version` and `curl -s http://localhost:11434/api/tags` |
| Vision model pulled | `ollama list` shows gemma3:4b or gemma3:12b |
| Python 3.10+ | `python3 --version` |
| pillow + requests | `pip install pillow requests` (or use venv) |
| Shutterstock credentials | `~/.env` has SHUTTERSTOCK_USER and SHUTTERSTOCK_PASSWORD |
| Photo folder | JPEG/TIFF files each >= 4 megapixels |

## Execution steps

### 1 — Gather inputs

Ask the user for:
- **Photo folder path** — where their JPEG/TIFF files are
- **Model preference** — gemma3:4b (faster) or gemma3:12b (better quality)

### 2 — Verify setup

Check Ollama is running, the vision model is available, Python deps are installed, and credentials exist in .env.

### 3 — Copy and configure the scripts

Copy the bundled tools/upload_to_shutterstock.py and tools/preflight_check.py to the photo folder.
If the user chose gemma3:12b, edit the ollama_model config key in tools/upload_to_shutterstock.py.
Create/activate a Python venv and install pillow + requests if needed.

### 4 — Run the preflight check

Run the preflight check before any upload (pass the photo folder or omit to use current directory):

```
python3 tools/preflight_check.py [image_folder]
```

This will:
- Scan all JPEG/TIFF files in the folder
- Validate each file (image integrity, minimum 4MP)
- Compute SHA-256 checksums for all files
- Detect duplicate files (identical content) and move extras to `_duplicates_trash/`
- Print a summary report with warnings

Exit codes:
- **0** — ready for upload
- **1** — issues found (no valid images, or below-threshold files)

### 5 — Run the upload script

Activate the venv and run the script (pass the photo folder or omit to use current directory):

```
python3 tools/upload_to_shutterstock.py [image_folder]
```

It will:
- Scan all JPEG/TIFF files in the folder
- Skip files under 4MP
- For each valid image: Ollama analysis → FTPS upload → collect metadata
- Generate shutterstock_metadata.csv

### 6 — Handle failures

If Ollama crashes (500 error, possible on CPU-only systems):
- Restart Ollama: killall ollama; sleep 2; ollama serve &
- Resume with: python3 tools/upload_to_shutterstock.py --resume-from N [image_folder]

### 7 — User completes on Shutterstock

Tell the user:
1. Go to https://submit.shutterstock.com/
2. Click the CSV button on the Submit page
3. Upload the generated shutterstock_metadata.csv
4. Review metadata and click Submit for review

## Configuration

Edit these in tools/upload_to_shutterstock.py:

| Key | Default | Notes |
|---|---|---|
| ollama_model | gemma3:4b | Change to gemma3:12b for quality |
| min_megapixels | 4.0 | Shutterstock minimum |
| max_keywords | 50 | Shutterstock max |
| min_keywords | 7 | Shutterstock min |

## Files in this skill

| File | Purpose |
|---|---|
| SKILL.md | This file — agent instructions |
| tools/preflight_check.py | Pre-flight validation script (duplicate detection via SHA-256, megapixel check) |
| tools/upload_to_shutterstock.py | Python script that performs the full workflow |

### Configuration (tools/preflight_check.py)

| Key | Default | Notes |
|---|---|---|
| min_megapixels | 4.0 | Shutterstock minimum |
| trash_folder | _duplicates_trash | Where duplicate files are moved instead of deleted |
