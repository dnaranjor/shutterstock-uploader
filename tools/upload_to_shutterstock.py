#!/usr/bin/env python3
"""
Upload photos to Shutterstock Contributor via FTPS with AI-generated metadata.

Requirements:
  - Ollama running with a vision model (gemma3:12b installed)
  - pillow, requests installed (via venv)
  - .env file with SHUTTERSTOCK_USER and SHUTTERSTOCK_PASSWORD

Usage:
  python3 upload_to_shutterstock.py [image_folder]
  python3 upload_to_shutterstock.py --resume-from N [image_folder]

If image_folder is omitted, the current working directory is used.
"""

import os
import re
import csv
import json
import base64
import time
import sys
import logging
from pathlib import Path
from ftplib import FTP_TLS
from typing import Optional

import requests
from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

CONFIG = {
    "env_file": Path.home() / ".env",
    "ollama_model": "gemma3:4b",
    "ollama_url": "http://localhost:11434/api/chat",
    "ftps_host": "ftp.shutterstock.com",
    "ftps_port": 21,
    "min_megapixels": 4.0,
    "allowed_extensions": {".jpg", ".jpeg", ".tif", ".tiff"},
    "max_keywords": 50,
    "min_keywords": 7,
}

SHUTTERSTOCK_CATEGORIES = [
    "Abstract", "Animals/Wildlife", "Arts", "Backgrounds/Textures",
    "Beauty/Fashion", "Buildings/Landmarks", "Business/Finance",
    "Celebrities", "Education", "Food and Drink", "Healthcare/Medical",
    "Holidays", "Industrial", "Interiors", "Miscellaneous", "Nature",
    "Objects", "Parks/Outdoor", "People", "Religion", "Science",
    "Signs/Symbols", "Sports/Recreation", "Technology", "Transportation",
    "Vintage",
]


def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        log.error(f".env file not found at {path}")
        raise FileNotFoundError(f"missing .env: {path}")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def find_images(folder: Path) -> list[Path]:
    images = []
    for ext in CONFIG["allowed_extensions"]:
        images.extend(folder.glob(f"*{ext}"))
        images.extend(folder.glob(f"*{ext.upper()}"))
    images.sort()
    return images


def validate_image(img_path: Path) -> Optional[dict]:
    try:
        with Image.open(img_path) as img:
            w, h = img.size
            mp = (w * h) / 1_000_000
            if mp < CONFIG["min_megapixels"]:
                log.warning(f"  SKIP: {img_path.name} — only {mp:.1f}MP (min {CONFIG['min_megapixels']}MP)")
                return None
            return {"path": img_path, "width": w, "height": h, "megapixels": mp}
    except Exception as e:
        log.warning(f"  SKIP: {img_path.name} — invalid image ({e})")
        return None


def image_to_base64(img_path: Path) -> str:
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_with_ollama(img_path: Path) -> dict:
    b64 = image_to_base64(img_path)
    categories_str = ", ".join(SHUTTERSTOCK_CATEGORIES)

    prompt = (
        "You are a Shutterstock metadata expert. Analyze this image and return ONLY valid JSON "
        "with exactly these three keys (no markdown, no extra text):\n"
        "{\n"
        '  "description": "A detailed single sentence describing who, what, where, mood, angle, focus.",\n'
        '  "keywords": "20-35 relevant comma-separated keywords for stock photo search",\n'
        '  "category": "one category from the list below"\n'
        "}\n\n"
        "Rules:\n"
        "- Description: max 200 characters, reads like a news headline, no keyword lists\n"
        "- Keywords: 20-35 specific words, no duplicates, no spamming\n"
        f"- Category: choose ONE from: {categories_str}\n"
    )

    payload = {
        "model": CONFIG["ollama_model"],
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64],
            }
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }

    resp = requests.post(CONFIG["ollama_url"], json=payload, timeout=600)
    resp.raise_for_status()
    data = resp.json()
    content = data["message"]["content"]

    json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
    if json_match:
        content = json_match.group()

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        log.warning(f"  Ollama returned non-JSON for {img_path.name}, attempting manual parse")
        desc_match = re.search(r'description["\s:]+([^"]+)', content)
        kw_match = re.search(r'keywords["\s:]+([^"]+)', content)
        cat_match = re.search(r'category["\s:]+([^"]+)', content)
        result = {
            "description": desc_match.group(1).strip() if desc_match else img_path.stem,
            "keywords": kw_match.group(1).strip() if kw_match else img_path.stem,
            "category": cat_match.group(1).strip() if cat_match else "Miscellaneous",
        }

    result.setdefault("description", img_path.stem)
    result.setdefault("keywords", img_path.stem)
    result.setdefault("category", "Miscellaneous")

    result["keywords"] = clean_keywords(result["keywords"], img_path.stem)
    result["category"] = validate_category(result["category"])
    result["description"] = result["description"][:200]

    return result


def clean_keywords(kw_str: str, fallback_stem: str = "") -> str:
    parts = [k.strip() for k in kw_str.replace("\n", ",").split(",")]
    seen = set()
    cleaned = []
    for kw in parts:
        kw_lower = kw.lower().strip()
        if kw_lower and kw_lower not in seen and len(kw) > 1:
            seen.add(kw_lower)
            cleaned.append(kw)
    if len(cleaned) < CONFIG["min_keywords"] and fallback_stem:
        cleaned.append(fallback_stem.replace("_", " ").replace("-", " "))
    return ", ".join(cleaned[:CONFIG["max_keywords"]])


def validate_category(cat: str) -> str:
    for c in SHUTTERSTOCK_CATEGORIES:
        if cat.lower().strip() == c.lower():
            return c
    log.warning(f"  Category '{cat}' not in Shutterstock list, using 'Miscellaneous'")
    return "Miscellaneous"


def ftps_upload(env: dict, local_path: Path, remote_filename: str) -> bool:
    log.info(f"  Uploading to Shutterstock via FTPS...")
    try:
        ftp = FTP_TLS()
        ftp.connect(CONFIG["ftps_host"], CONFIG["ftps_port"])
        ftp.login(env["SHUTTERSTOCK_USER"], env["SHUTTERSTOCK_PASSWORD"])
        ftp.prot_p()
        ftp.cwd("/")
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {remote_filename}", f)
        ftp.quit()
        log.info(f"  Uploaded successfully")
        return True
    except Exception as e:
        log.error(f"  FTPS upload failed: {e}")
        return False


def verify_ollama_ready():
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = resp.json().get("models", [])
        model_names = [m["name"] for m in models]
        if CONFIG["ollama_model"] not in model_names:
            log.warning(
                f"Model '{CONFIG['ollama_model']}' not found. "
                f"Run: ollama pull {CONFIG['ollama_model']}"
            )
            return False
        return True
    except requests.exceptions.ConnectionError:
        log.error("Ollama is not running. Start it with: ollama serve")
        return False


def generate_csv(results: list[dict], csv_path: Path):

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "Filename": r["filename"],
                "Description": r["description"],
                "Keywords": r["keywords"],
                "Categories": r["category"],
                "Editorial": "",
            })

    log.info(f"\nCSV saved to: {csv_path}")
    log.info(f"Upload this file on https://submit.shutterstock.com/ → Submit → CSV button")


def resolve_image_folder() -> Path:
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--resume-from":
            continue
        if i > 0 and args[i - 1] == "--resume-from":
            continue
        return Path(a).resolve()
    return Path.cwd()


def main():
    log.info("=" * 60)
    log.info("Shutterstock Contributor Upload Tool")
    log.info("=" * 60)

    image_folder = resolve_image_folder()
    csv_output = image_folder / "shutterstock_metadata.csv"

    skip_count = 0
    if len(sys.argv) > 1 and sys.argv[1] == "--resume-from":
        skip_count = int(sys.argv[2])
        log.info(f"Resuming from image {skip_count + 1}")

    env = load_env(CONFIG["env_file"])
    user = env.get("SHUTTERSTOCK_USER", "")
    if not user:
        log.error("SHUTTERSTOCK_USER not found in .env")
        return
    log.info(f"Account: {user}")

    if not verify_ollama_ready():
        return

    images = find_images(image_folder)
    if not images:
        log.warning(f"No images found in {image_folder}")
        log.info("Add JPEG/TIFF files (≥4MP) to the folder and re-run.")
        return

    log.info(f"Found {len(images)} image(s) to process")

    valid = []
    for img in images:
        info = validate_image(img)
        if info:
            valid.append(info)

    if not valid:
        log.warning("No valid images to process")
        return

    log.info(f"Valid images: {len(valid)}")
    log.info(f"Ollama model: {CONFIG['ollama_model']}")
    log.info(f"  Tip: Vision analysis on CPU may take 1-5 min per image.")
    log.info(f"  For faster processing, use a smaller model: ollama pull gemma3:4b")
    log.info("")

    results = []
    for idx, info in enumerate(valid, 1):
        if idx <= skip_count:
            log.info(f"[{idx}/{len(valid)}] {info['path'].name} — SKIP (resume)")
            results.append({
                "filename": info["path"].name,
                "description": "(resumed)",
                "keywords": "(resumed)",
                "category": "Miscellaneous",
                "uploaded": True,
            })
            continue

        img_path = info["path"]
        log.info(f"[{idx}/{len(valid)}] {img_path.name} ({info['width']}x{info['height']})")
        log.info(f"  Analyzing with vision model... (may take several minutes)")

        t0 = time.time()
        meta = analyze_with_ollama(img_path)
        elapsed = time.time() - t0

        log.info(f"  ✓ Analysis done ({elapsed:.0f}s)")
        log.info(f"  Description: {meta['description'][:80]}...")
        kw_count = len(meta["keywords"].split(", "))
        log.info(f"  Keywords: {kw_count} words")
        log.info(f"  Category: {meta['category']}")

        remote_name = img_path.name
        uploaded = ftps_upload(env, img_path, remote_name)

        results.append({
            "filename": remote_name,
            "description": meta["description"],
            "keywords": meta["keywords"],
            "category": meta["category"],
            "uploaded": uploaded,
        })

        log.info("")

    generate_csv(results, csv_output)

    uploaded_count = sum(1 for r in results if r["uploaded"])
    log.info(f"Uploaded: {uploaded_count}/{len(results)} images")
    log.info(f"Failed: {len(results) - uploaded_count}")
    log.info("")
    log.info("NEXT STEPS:")
    log.info(f"  1. Go to https://submit.shutterstock.com/")
    log.info(f"  2. Click the 'CSV' button on the Submit page")
    log.info(f"  3. Upload: {csv_output}")
    log.info(f"  4. Review metadata and click Submit for review")


if __name__ == "__main__":
    main()
