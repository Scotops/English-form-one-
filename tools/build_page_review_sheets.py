#!/usr/bin/env python3
"""Create labelled overview sheets from source/HTML comparison panels."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparisons", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--per-sheet", type=int, default=16)
    args = parser.parse_args()
    files = sorted(args.comparisons.glob("page-*.png"))
    args.output.mkdir(parents=True, exist_ok=True)
    columns = 4
    rows = math.ceil(args.per_sheet / columns)
    cell_width = 700
    cell_height = 290
    label_height = 24
    font = ImageFont.load_default()
    for start in range(0, len(files), args.per_sheet):
        batch = files[start : start + args.per_sheet]
        sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#e8edf3")
        draw = ImageDraw.Draw(sheet)
        for offset, path in enumerate(batch):
            image = Image.open(path).convert("RGB")
            # The generated comparison has four equal panels. Retain only the
            # original and HTML render so each book page stays readable here.
            pair = image.crop((0, 0, image.width // 2, image.height))
            pair.thumbnail((cell_width - 8, cell_height - label_height - 8), Image.Resampling.LANCZOS)
            column = offset % columns
            row = offset // columns
            x = column * cell_width + (cell_width - pair.width) // 2
            y = row * cell_height + label_height
            sheet.paste(pair, (x, y))
            draw.text((column * cell_width + 6, row * cell_height + 5), path.stem, fill="#111", font=font)
        number = start // args.per_sheet + 1
        sheet.save(args.output / f"book-review-{number:02d}.jpg", quality=90, optimize=True)
    print(f"Review sheets: {math.ceil(len(files) / args.per_sheet)} for {len(files)} pages")


if __name__ == "__main__":
    main()
