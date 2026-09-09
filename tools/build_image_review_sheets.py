#!/usr/bin/env python3
"""Create labelled contact sheets for source images lacking text descriptions."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lxml import html as lxml_html
from PIL import Image, ImageDraw, ImageFont, ImageOps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("book", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.book.resolve()
    source = (args.source or root / "content/source-fragments").resolve()
    output = (args.output or root / "tmp/adt-book-builder/image-review").resolve()
    output.mkdir(parents=True, exist_ok=True)
    texts = json.loads((root / "content/i18n/en/texts.json").read_text(encoding="utf-8"))
    records: list[tuple[str, Path]] = []
    for page in source.glob("*.html"):
        document = lxml_html.fromstring(page.read_bytes())
        for image in document.xpath("//img[@data-id]"):
            identifier = image.get("data-id") or ""
            mapped = str(texts.get(identifier) or "").strip()
            if mapped and mapped != "Illustration supporting the surrounding textbook content.":
                continue
            src = (image.get("src") or "").lstrip("./")
            image_path = root / src
            if image_path.is_file() and (identifier, image_path) not in records:
                records.append((identifier, image_path))
    records.sort()

    font = ImageFont.load_default()
    cell_width, cell_height = 560, 430
    columns, rows_per_sheet = 3, 3
    per_sheet = columns * rows_per_sheet
    for sheet_index in range(math.ceil(len(records) / per_sheet)):
        sheet = Image.new("RGB", (columns * cell_width, rows_per_sheet * cell_height), "white")
        draw = ImageDraw.Draw(sheet)
        for offset, (identifier, image_path) in enumerate(
            records[sheet_index * per_sheet : (sheet_index + 1) * per_sheet]
        ):
            column, row = offset % columns, offset // columns
            x, y = column * cell_width, row * cell_height
            with Image.open(image_path) as source_image:
                preview = ImageOps.contain(source_image.convert("RGB"), (cell_width - 28, cell_height - 58))
            px = x + (cell_width - preview.width) // 2
            py = y + 32 + (cell_height - 48 - preview.height) // 2
            sheet.paste(preview, (px, py))
            draw.rectangle((x, y, x + cell_width - 1, y + cell_height - 1), outline="#777", width=2)
            draw.text((x + 10, y + 9), f"{identifier} — {image_path.name}", fill="black", font=font)
        sheet.save(output / f"missing-descriptions-{sheet_index + 1:02d}.png")
    (output / "inventory.json").write_text(
        json.dumps(
            [{"id": identifier, "path": str(path)} for identifier, path in records],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Created {math.ceil(len(records) / per_sheet)} sheets for {len(records)} images in {output}")


if __name__ == "__main__":
    main()
