#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "pillow", "numpy"]
# ///
"""
Optimizes your own images for the Frame: takes everything in raw/, crops it to 16:9
around its focal area, scales it to 3840x2160 and saves a JPEG to art/. See readme.md.

    uv run optimize.py [--only Magritte] [--keep] [--matte] [--anchor 0.3]
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

# Same crop, colour handling and JPEG settings as get.py, so both scripts' output matches.
from get import (HERE, IMAGE_EXT, MATTE_IF_KEPT_BELOW, display_name, find_existing,
                 load_image, make_crop, make_matted, save_jpeg)


def output_name(stem: str) -> str:
    """Keep the file's own name; turn hyphen-only names like 'A-B-(1953)---C' into 'A B (1953) - C'."""
    stem = unicodedata.normalize("NFC", stem)
    if " " not in stem:  # e.g. a downloaded file: hyphens/underscores instead of spaces
        stem = " - ".join(re.sub(r"[-_]", " ", part).strip() for part in re.split(r"-{2,}|_{2,}", stem))
    return display_name("", "", stem)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(HERE / "raw"), help="folder of images to optimize (default: raw/)")
    ap.add_argument("--out", default=str(HERE / "art"), help="where results go (default: art/)")
    ap.add_argument("--only", default="", help="comma-separated, case-insensitive parts of filenames")
    ap.add_argument("--keep", action="store_true", help="leave images already in art/ as they are")
    ap.add_argument("--matte", action="store_true",
                    help="for portrait images, also write a version showing the whole picture on a mat")
    ap.add_argument("--anchor", type=float, default=None,
                    help="crop position instead of the focal area: 0 = left/top, 1 = right/bottom")
    args = ap.parse_args()

    raw, out = Path(args.raw), Path(args.out)
    if not raw.is_dir():
        sys.exit(f"No {raw.name}/ folder: create it and put images in it.")
    if args.anchor is not None and not 0 <= args.anchor <= 1:
        sys.exit("--anchor must be between 0 and 1")
    only = [o.strip().casefold() for o in args.only.split(",") if o.strip()]
    files = sorted(p for p in raw.iterdir() if p.suffix.lower() in IMAGE_EXT and not p.name.startswith("."))
    files = [p for p in files if not only or any(o in p.stem.casefold() for o in only)]
    if not files:
        sys.exit(f"No images in {raw.name}/" + (f" matching {args.only}" if only else ""))
    out.mkdir(parents=True, exist_ok=True)

    done = 0
    for i, p in enumerate(files, 1):
        name = output_name(p.stem)
        print(f"[{i}/{len(files)}] {p.name}", flush=True)
        if args.keep and find_existing(out, name):
            print(f"      = already in {out.name}/, kept")
            continue
        try:
            im = load_image(p)
        except Exception as e:
            print(f"      ! can't read it: {e}")
            continue
        cropped, info = make_crop(im, args.anchor)
        save_jpeg(cropped, out / f"{name}.jpg")
        written = [f"{name}.jpg"]
        if args.matte and info["kept"] < MATTE_IF_KEPT_BELOW:
            save_jpeg(make_matted(im), out / f"{name} (matted).jpg")
            written.append(f"{name} (matted).jpg")
        notes = [f"from {info['src']}", f"kept {info['kept']:.0%}"]
        if info["upscale"] > 1.01:
            notes.append(f"upscaled {info['upscale']:.2f}x, source is small")
        print(f"      ✓ {' + '.join(written)}  ({', '.join(notes)})")
        done += 1
    print(f"\n{done}/{len(files)} written to {out}")


if __name__ == "__main__":
    main()
