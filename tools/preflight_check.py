#!/usr/bin/env python3
"""
Pre-flight check for Shutterstock upload.
Scans image folder for duplicates (via SHA-256) and validates
megapixel requirements before the main upload runs.

Usage:
  python3 preflight_check.py [image_folder]

If image_folder is omitted, the current working directory is used.
"""

import hashlib
import logging
import shutil
import sys
from pathlib import Path
from typing import Optional

from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

CONFIG = {
    "min_megapixels": 4.0,
    "allowed_extensions": {".jpg", ".jpeg", ".tif", ".tiff"},
    "trash_folder": "_duplicates_trash",
}


def find_images(folder: Path) -> list[Path]:
    images = []
    for ext in CONFIG["allowed_extensions"]:
        images.extend(folder.glob(f"*{ext}"))
        images.extend(folder.glob(f"*{ext.upper()}"))
    images.sort()
    return images


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def validate_image(img_path: Path) -> Optional[dict]:
    try:
        with Image.open(img_path) as img:
            w, h = img.size
            mp = (w * h) / 1_000_000
            if mp < CONFIG["min_megapixels"]:
                log.warning(f"  BELOW {CONFIG['min_megapixels']}MP: {img_path.name} ({mp:.1f}MP)")
                return None
            return {"path": img_path, "name": img_path.name, "width": w, "height": h, "megapixels": mp}
    except Exception as e:
        log.warning(f"  INVALID: {img_path.name} — {e}")
        return None


def format_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def main():
    log.info("=" * 60)
    log.info("Shutterstock Preflight Check")
    log.info("=" * 60)

    folder = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else Path.cwd()
    images = find_images(folder)

    if not images:
        log.warning(f"No JPEG/TIFF images found in {folder}")
        sys.exit(1)

    log.info(f"Found {len(images)} file(s) to check")

    valid = []
    for img in images:
        info = validate_image(img)
        if info:
            info["size"] = img.stat().st_size
            valid.append(info)

    total_below_mp = len(images) - len(valid)

    log.info("Computing SHA-256 checksums...")
    for v in valid:
        v["sha256"] = sha256_of_file(v["path"])
    log.info(f"  Done — {len(valid)} checksums computed")

    checksum_groups: dict[str, list[dict]] = {}
    for v in valid:
        checksum_groups.setdefault(v["sha256"], []).append(v)

    duplicate_groups = {k: v for k, v in checksum_groups.items() if len(v) > 1}

    print()
    print("=" * 60)
    print("PREFLIGHT CHECK REPORT")
    print("=" * 60)
    print(f"  Folder:            {folder}")
    print(f"  Files scanned:     {len(images)}")
    print(f"  Valid images:      {len(valid)}")
    print(f"  Below threshold:   {total_below_mp}")
    print(f"  Duplicate groups:  {len(duplicate_groups)}")
    print()

    trash_dir = folder / CONFIG["trash_folder"]

    if duplicate_groups:
        print("DUPLICATES FOUND")
        print("-" * 60)
        total_moved = 0
        for cksum, group in duplicate_groups.items():
            keeper = group[0]
            duplicates = group[1:]
            print(f"  Checksum: {cksum[:16]}...")
            print(f"    KEEP:    {keeper['name']}  ({keeper['width']}x{keeper['height']}, {format_bytes(keeper['size'])})")
            for dup in duplicates:
                print(f"    TRASH:   {dup['name']}  ({dup['width']}x{dup['height']}, {format_bytes(dup['size'])})")
            print()

            trash_dir.mkdir(parents=True, exist_ok=True)
            for dup in duplicates:
                dest = trash_dir / dup["name"]
                suffix = 1
                while dest.exists():
                    stem = Path(dup["name"]).stem
                    ext = Path(dup["name"]).suffix
                    dest = trash_dir / f"{stem}_{suffix}{ext}"
                    suffix += 1
                shutil.move(str(dup["path"]), str(dest))
                total_moved += 1

        print(f"  Moved {total_moved} duplicate(s) to: {trash_dir}/")
        print()
    else:
        print("  No duplicates found.")
        print()

    if total_below_mp > 0:
        print("WARNINGS")
        print("-" * 60)
        print(f"  {total_below_mp} file(s) are below {CONFIG['min_megapixels']}MP and will be skipped.")
        print("  Remove or replace them before the main upload.")
        print()

    print("=" * 60)
    ready_count = len(valid) - sum(len(g) - 1 for g in duplicate_groups.values())
    print(f"  {ready_count} file(s) ready for upload.")
    print("  Run: python3 upload_to_shutterstock.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
