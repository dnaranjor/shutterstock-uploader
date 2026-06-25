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

Takes JPEG/TIFF photos from a target folder (PNG is **not** accepted by Shutterstock) and:

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
| Photo folder | JPEG/TIFF files each >= 4 megapixels (PNG not accepted) |

## Execution steps

### 1 — Gather inputs

Ask the user for:
- **Photo folder path** — where their JPEG/TIFF files are
- **Model preference** — gemma3:4b (faster) or gemma3:12b (better quality)
- If the folder contains PNG files: note that Shutterstock only accepts JPEG/TIFF. PNG files must be converted to JPEG before proceeding.

### 2 — Verify setup

Check Ollama is running, the vision model is available, Python deps are installed, and credentials exist in .env.

### 3 — Copy and configure the scripts

Copy the bundled tools/upload_to_shutterstock.py, tools/preflight_check.py, and tools/fix_metadata.py to the photo folder.
If the user chose gemma3:12b, edit the ollama_model config key in tools/upload_to_shutterstock.py.
Create/activate a Python venv and install pillow + requests if needed.
If the folder contains any PNG files, convert them to JPEG before proceeding (Shutterstock only accepts JPEG/TIFF):

```
python3 -c "
from PIL import Image
from pathlib import Path
for png in Path('.').glob('*.png'):
    jpg = png.with_suffix('.jpg')
    img = Image.open(png)
    if img.mode not in ('RGB', 'L'): img = img.convert('RGB')
    img.save(jpg, 'JPEG', quality=95, icc_profile=img.info.get('icc_profile'))
    print(f'{png.name} -> {jpg.name}')
"
```

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

**Timeout / interruption:** The upload script saves CSV incrementally after each image.
If the script times out, re-run with the same command — already-processed files
are read from the existing CSV and skipped automatically:

```
python3 tools/upload_to_shutterstock.py [image_folder]
```

(No `--resume-from` flag needed anymore — the script detects prior progress from the CSV.)

If Ollama crashes (500 error, possible on CPU-only systems):
- Restart Ollama: killall ollama; sleep 2; ollama serve &
- Re-run the upload script (it resumes from the existing CSV automatically)

**Fixing placeholder entries:** If an older run produced `(resumed)` placeholders
in the CSV, run the fix tool to re-analyze only those files:

```
python3 tools/fix_metadata.py [image_folder]
```

This reads the CSV, finds entries with `(resumed)`, re-analyzes them with Ollama,
and updates the CSV (saving incrementally after each fix).

**FTP processing behavior:** After upload, files disappear from the FTP server —
this is normal. Shutterstock ingests them into its internal queue. There may be a
delay (30-60 seconds) before they appear under "Not submitted" on
submit.shutterstock.com.

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
| tools/upload_to_shutterstock.py | Python script that performs the full workflow (saves CSV incrementally for timeout safety; auto-resumes from existing CSV) |
| tools/fix_metadata.py | Helper to fix `(resumed)` placeholder entries in CSV from older runs |

### Configuration (tools/preflight_check.py)

| Key | Default | Notes |
|---|---|---|
| min_megapixels | 4.0 | Shutterstock minimum |
| trash_folder | _duplicates_trash | Where duplicate files are moved instead of deleted |
