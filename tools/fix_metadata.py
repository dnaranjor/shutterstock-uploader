#!/usr/bin/env python3
import csv
import json
import base64
import re
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from upload_to_shutterstock import analyze_with_ollama, CONFIG, SHUTTERSTOCK_CATEGORIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

folder = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
csv_path = folder / "shutterstock_metadata.csv"

# Read current CSV
rows = []
# Read and fix incrementally
with open(csv_path, newline="", encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

def write_csv():
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

fixed = 0
for i, row in enumerate(rows):
    if row[1] == "(resumed)":
        filename = row[0]
        img_path = folder / filename
        if not img_path.exists():
            log.warning(f"File not found: {filename}")
            continue
        log.info(f"[{i+1}] Fixing {filename}...")
        meta = analyze_with_ollama(img_path)
        rows[i] = [filename, meta["description"], meta["keywords"], meta["category"], ""]
        fixed += 1
        write_csv()
        log.info(f"  -> {meta['description'][:60]}... | {len(meta['keywords'].split(', '))} kw | {meta['category']}")

log.info(f"\nFixed {fixed} entries. CSV updated: {csv_path}")
