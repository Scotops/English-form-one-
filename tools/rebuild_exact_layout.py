#!/usr/bin/env python3
"""Rebuild the English ADT with one source-positioned HTML page per PDF page.

Desktop pages use live, individually positioned PDF glyphs plus regional
graphics-only assets.  The structured ADT markup remains the accessible and
mobile view.  No complete PDF page or page-sized raster is shipped.
"""

from __future__ import annotations

import argparse
import ctypes
import html
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pdfplumber
import pypdfium2 as pdfium
from lxml import etree, html as lxml_html
from PIL import Image
from pypdf import PdfReader


TITLE = "English for Secondary Schools Student’s Book Form One"
ROMAN = ("i", "ii", "iii", "iv", "v", "vi")
RUNNING_TEXT = {
    "english for secondary schools",
    "student's book form one",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("book", type=Path)
    parser.add_argument("--pages", help="Comma-separated physical PDF page numbers")
    return parser.parse_args()


def fmt(value: float | int | None) -> str:
    return f"{float(value or 0):.3f}".rstrip("0").rstrip(".") or "0"


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize(value: str) -> str:
    return clean(value).replace("’", "'").casefold()


def printed_folio(page_number: int) -> str:
    return ROMAN[page_number - 1] if page_number <= len(ROMAN) else str(page_number - len(ROMAN))


def output_path(book: Path, page_number: int) -> Path:
    return book / ("index.html" if page_number == 1 else f"pg{page_number:03d}_sec001.html")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def color_css(value: Any) -> str:
    if value is None or isinstance(value, str):
        return "#111"
    if isinstance(value, (int, float)):
        level = max(0, min(255, round(float(value) * 255)))
        return f"rgb({level} {level} {level})"
    try:
        parts = [float(part) for part in value]
    except (TypeError, ValueError):
        return "#111"
    if len(parts) == 1:
        level = max(0, min(255, round(parts[0] * 255)))
        return f"rgb({level} {level} {level})"
    if len(parts) == 3:
        rgb = [max(0, min(255, round(part * 255))) for part in parts]
        return f"rgb({rgb[0]} {rgb[1]} {rgb[2]})"
    if len(parts) >= 4:
        c, m, y, k = parts[:4]
        rgb = [round(255 * (1 - min(1, channel * (1 - k) + k))) for channel in (c, m, y)]
        return f"rgb({rgb[0]} {rgb[1]} {rgb[2]})"
    return "#111"


def font_family(fontname: str) -> str:
    name = (fontname or "").split("+")[-1].casefold()
    if "times" in name:
        return "'Times New Roman', Times, serif"
    if "minion" in name or "palatino" in name or "bookman" in name:
        return "Georgia, 'Times New Roman', serif"
    if any(token in name for token in ("arial", "helvetica", "myriad", "gill", "franklin")):
        return "Arial, Helvetica, sans-serif"
    if "rockwell" in name:
        return "Rockwell, 'Arial Black', serif"
    if "comic" in name:
        return "'Comic Sans MS', cursive"
    if "courier" in name:
        return "'Courier New', monospace"
    if "symbol" in name or "wingdings" in name or "zapf" in name:
        return "Symbol, 'Segoe UI Symbol', sans-serif"
    return "'Times New Roman', Times, serif"


def char_style(character: dict[str, Any], color: str) -> str:
    fontname = str(character.get("fontname") or "")
    weight = "700" if re.search(r"bold|black|heavy|semibold", fontname, re.I) else "400"
    style = "italic" if re.search(r"italic|oblique", fontname, re.I) else "normal"
    size = max(1.0, float(character.get("size") or 10))
    return (
        f"font-family:{font_family(fontname)};font-size:{fmt(size)}px;"
        f"font-weight:{weight};font-style:{style};color:{color}"
    )


def pdfium_text_colors(page: Any, page_height: float) -> list[tuple[float, float, float, float, str]]:
    """Read PDFium's rendered sRGB text colours and their page rectangles."""
    raw = pdfium.raw
    records: list[tuple[float, float, float, float, str]] = []
    for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_TEXT]):
        left, bottom, right, top = obj.get_bounds()
        red = ctypes.c_uint()
        green = ctypes.c_uint()
        blue = ctypes.c_uint()
        alpha = ctypes.c_uint()
        if not raw.FPDFPageObj_GetFillColor(
            obj.raw,
            ctypes.byref(red),
            ctypes.byref(green),
            ctypes.byref(blue),
            ctypes.byref(alpha),
        ):
            continue
        css = f"rgb({red.value} {green.value} {blue.value} / {alpha.value / 255:.3f})"
        records.append((float(left), page_height - float(top), float(right), page_height - float(bottom), css))
    return records


def rendered_text_color(
    character: dict[str, Any],
    records: list[tuple[float, float, float, float, str]],
) -> str:
    x = (float(character.get("x0") or 0) + float(character.get("x1") or 0)) / 2
    y = (float(character.get("top") or 0) + float(character.get("bottom") or 0)) / 2
    candidates = [
        record
        for record in records
        if record[0] - 0.5 <= x <= record[2] + 0.5 and record[1] - 0.5 <= y <= record[3] + 0.5
    ]
    if not candidates:
        return color_css(character.get("non_stroking_color"))
    return min(candidates, key=lambda record: (record[2] - record[0]) * (record[3] - record[1]))[4]


def metadata_line(value: str, folio: str, top: float, height: float) -> bool:
    normalized = normalize(value)
    if not normalized:
        return False
    if ".indd" in normalized:
        return True
    if re.search(r"\b\d{2}/\d{2}/\d{4}\b", normalized) and re.search(r"\b\d{1,2}:\d{2}\b", normalized):
        return True
    if normalized in RUNNING_TEXT:
        return True
    if top > height * 0.78 and normalized == normalize(folio):
        return True
    return False


def excluded_text_rectangles(page: Any, folio: str) -> list[tuple[float, float, float, float]]:
    rectangles: list[tuple[float, float, float, float]] = []
    for line in page.extract_text_lines(layout=False, return_chars=False):
        value = str(line.get("text") or "")
        top = float(line.get("top") or 0)
        if metadata_line(value, folio, top, float(page.height)):
            rectangles.append(
                (
                    float(line.get("x0") or 0) - 1,
                    top - 1,
                    float(line.get("x1") or 0) + 1,
                    float(line.get("bottom") or top) + 1,
                )
            )
    return rectangles


def within_any_rect(character: dict[str, Any], rectangles: list[tuple[float, float, float, float]]) -> bool:
    x = (float(character.get("x0") or 0) + float(character.get("x1") or 0)) / 2
    y = (float(character.get("top") or 0) + float(character.get("bottom") or 0)) / 2
    return any(left <= x <= right and top <= y <= bottom for left, top, right, bottom in rectangles)


def render_text_layer(page: Any, pdfium_page: Any, page_number: int, folio: str) -> tuple[str, str]:
    excluded = excluded_text_rectangles(page, folio)
    pdfium_colors = pdfium_text_colors(pdfium_page, float(page.height))
    style_ids: dict[str, str] = {}
    style_rules: list[str] = []
    glyphs: list[str] = []
    for character in page.chars:
        raw = str(character.get("text") or "")
        top = float(character.get("top") or 0)
        content_bottom = 690 if page_number == 1 else 674
        if not raw or top >= content_bottom or within_any_rect(character, excluded):
            continue
        rule = char_style(character, rendered_text_color(character, pdfium_colors))
        if rule not in style_ids:
            class_name = f"f{len(style_ids) + 1}"
            style_ids[rule] = class_name
            style_rules.append(f".{class_name}{{{rule}}}")
        class_name = style_ids[rule]
        left = float(character.get("x0") or 0)
        width = max(0.2, float(character.get("x1") or left) - left)
        height = max(0.2, float(character.get("bottom") or top) - top)
        matrix = character.get("matrix") or (1, 0, 0, 1, 0, 0)
        try:
            angle = math.degrees(math.atan2(float(matrix[1]), float(matrix[0])))
        except (TypeError, ValueError, IndexError):
            angle = 0.0
        transform = f";transform:rotate({fmt(-angle)}deg)" if abs(angle) > 1 else ""
        visible = "&nbsp;" if raw == " " else html.escape(raw)
        glyphs.append(
            f'<span class="g {class_name}" style="left:{fmt(left)}px;top:{fmt(top)}px;'
            f'width:{fmt(width)}px;height:{fmt(height)}px{transform}">{visible}</span>'
        )
    return "".join(glyphs), "".join(style_rules)


def graphics_mask(page_number: int, artwork: Image.Image, page_height: float, scale: int) -> Image.Image:
    pixels = np.asarray(artwork).copy()
    if page_number > 1:
        top_end = min(pixels.shape[0], round(89 * scale))
        bottom_start = max(0, round(min(page_height, 674) * scale))
        pixels[:top_end, :, 3] = 0
        pixels[bottom_start:, :, 3] = 0
    else:
        pixels[: min(pixels.shape[0], round(60 * scale)), :, 3] = 0
        pixels[max(0, round(min(page_height, 690) * scale)) :, :, 3] = 0
    # If the PDF contains a full white page rectangle, remove it. White remains
    # supplied by CSS, and photographs/illustrations stay as regional assets.
    white = (
        (pixels[:, :, 0] >= 250)
        & (pixels[:, :, 1] >= 250)
        & (pixels[:, :, 2] >= 250)
        & (pixels[:, :, 3] >= 250)
    )
    if float(white.mean()) > 0.55:
        pixels[white, 3] = 0
    return Image.fromarray(pixels, "RGBA")


def render_graphic_components(
    page: Any,
    output_dir: Path,
    page_number: int,
    page_height: float,
    scale: int = 2,
) -> tuple[str, list[dict[str, Any]]]:
    """Render non-text PDF objects and split them into bounded regional assets."""
    raw = pdfium.raw
    objects = list(page.get_objects())
    text_objects = [obj for obj in objects if obj.type == raw.FPDF_PAGEOBJ_TEXT]
    for obj in text_objects:
        raw.FPDFPageObj_SetIsActive(obj.raw, False)
    try:
        artwork = page.render(
            scale=scale,
            fill_color=(0, 0, 0, 0),
            rev_byteorder=True,
            optimize_mode="print",
        ).to_pil().convert("RGBA")
    finally:
        for obj in text_objects:
            raw.FPDFPageObj_SetIsActive(obj.raw, True)
    artwork = graphics_mask(page_number, artwork, page_height, scale)

    output_dir.mkdir(parents=True, exist_ok=True)
    for old_path in output_dir.glob(f"pg{page_number:03d}_art*.png"):
        old_path.unlink()
    alpha = np.asarray(artwork.getchannel("A"))
    occupied_rows = np.flatnonzero((alpha > 4).any(axis=1))
    if occupied_rows.size == 0:
        return "", []

    row_groups: list[tuple[int, int]] = []
    start = previous = int(occupied_rows[0])
    max_gap = scale * 7
    for row in occupied_rows[1:]:
        row = int(row)
        if row - previous > max_gap:
            row_groups.append((start, previous + 1))
            start = row
        previous = row
    row_groups.append((start, previous + 1))

    max_height = int(artwork.height * 0.30)
    bands: list[tuple[int, int]] = []
    for top, bottom in row_groups:
        cursor = top
        while cursor < bottom:
            band_bottom = min(bottom, cursor + max_height)
            bands.append((cursor, band_bottom))
            cursor = band_bottom

    tags: list[str] = []
    records: list[dict[str, Any]] = []
    component_index = 0
    for top, bottom in bands:
        occupied_columns = np.flatnonzero((alpha[top:bottom] > 4).any(axis=0))
        if occupied_columns.size == 0:
            continue
        left = max(0, int(occupied_columns[0]) - 2)
        right = min(artwork.width, int(occupied_columns[-1]) + 3)
        crop_top = max(0, top - 2)
        crop_bottom = min(artwork.height, bottom + 2)
        component = artwork.crop((left, crop_top, right, crop_bottom))
        if component.width < 2 or component.height < 2:
            continue
        component_index += 1
        filename = f"pg{page_number:03d}_art{component_index:03d}.png"
        component.save(output_dir / filename, format="PNG", optimize=True)
        x, y = left / scale, crop_top / scale
        width, height = component.width / scale, component.height / scale
        tags.append(
            f'<img class="source-art" src="images/source-layout/{filename}" alt="" aria-hidden="true" '
            f'style="left:{fmt(x)}px;top:{fmt(y)}px;width:{fmt(width)}px;height:{fmt(height)}px">'
        )
        records.append(
            {
                "file": filename,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "page_fraction": (width * height) / max(1.0, (artwork.width / scale) * (artwork.height / scale)),
            }
        )
    return "".join(tags), records


def semantic_markup(path: Path) -> tuple[str, int]:
    document = lxml_html.fromstring(path.read_bytes())
    exact = document.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " semantic-layer ")]')
    if exact:
        container = exact[0]
        children = [
            etree.tostring(child, encoding="unicode", method="html")
            for child in container
            if "adt-page-title" not in str(child.get("class") or "").split()
        ]
        activity_count = len(container.xpath('.//*[@data-activity-id]'))
        return "".join(children).strip(), activity_count
    flows = document.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " adt-page-flow ")]')
    if not flows:
        raise ValueError(f"No semantic page flow found in {path}")
    flow = flows[0]
    children = [etree.tostring(child, encoding="unicode", method="html") for child in flow]
    activity_count = len(flow.xpath('.//*[@data-activity-id]'))
    return "".join(children).strip(), activity_count


def converted_word_map(book: Path, reader_page: Any, page_number: int) -> dict[str, Any]:
    source = book / "content" / "word-boxes" / f"pg{page_number:03d}.json"
    if not source.is_file():
        return {}
    payload = load_json(source)
    trim = reader_page.trimbox
    trim_left = float(trim.left)
    trim_top = float(reader_page.mediabox.top) - float(trim.top)
    trim_width = float(trim.width)
    trim_height = float(trim.height)
    result: dict[str, Any] = {}
    for identifier, boxes in (payload.get("items") or {}).items():
        converted: list[Any] = []
        for box in boxes:
            if not isinstance(box, list) or len(box) != 4:
                converted.append(None)
                continue
            converted.append(
                [
                    round(trim_left + float(box[0]) * trim_width, 3),
                    round(trim_top + float(box[1]) * trim_height, 3),
                    round(float(box[2]) * trim_width, 3),
                    round(float(box[3]) * trim_height, 3),
                ]
            )
        result[identifier] = converted
    return result


def page_template(
    page_number: int,
    folio: str,
    width: float,
    height: float,
    visual_art: str,
    visual_text: str,
    font_rules: str,
    semantics: str,
    word_map: dict[str, Any],
) -> str:
    section_id = f"pg{page_number:03d}_sec001"
    title = f"{TITLE} — printed page {folio}"
    map_json = json.dumps(word_map, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="title-id" content="{section_id}">
  <meta name="page-section-id" content="{page_number}">
  <meta name="source-pdf-page" content="{page_number}">
  <meta name="printed-page-number" content="{html.escape(folio)}">
  <link href="./content/tailwind_output.css" rel="stylesheet">
  <link href="./assets/libs/fontawesome/css/all.min.css" rel="stylesheet">
  <link href="./assets/fonts.css" rel="stylesheet">
  <link href="./content/exact-layout.css?v=1" rel="stylesheet">
  <style>{font_rules}</style>
</head>
<body>
  <main id="page-top">
    <div id="content" class="exact-page opacity-0" data-source-page="{page_number}" data-printed-page="{html.escape(folio)}" style="--page-width:{fmt(width)}px;--page-height:{fmt(height)}px">
      <article class="canonical-page" data-section-id="{section_id}" aria-label="Physical source page {page_number}, printed page {html.escape(folio)}">
        <div class="pdf-visual activity-text" aria-hidden="true">
          <div class="background-images">{visual_art}</div>
          <div class="source-text">{visual_text}</div>
          <span class="adt-printed-page-number">{html.escape(folio)}</span>
          <span class="adt-tts-source-word-highlight"></span>
        </div>
        <div class="semantic-layer">
          <h1 class="adt-page-title">{html.escape(title)}</h1>
          {semantics}
        </div>
      </article>
    </div>
  </main>
  <div id="interface-container"></div>
  <div id="nav-container"></div>
  <script type="application/json" id="adt-word-highlight-map">{map_json}</script>
  <script src="./assets/auto-fit.js?v=1"></script>
  <script src="./assets/offline-preloader.js?v=8"></script>
  <script src="./assets/scorm.js"></script>
  <script src="./assets/word-highlight-sync.js?v=1"></script>
  <script src="./assets/base.bundle.local.js"></script>
</body>
</html>
'''


def main() -> int:
    args = parse_args()
    pdf_path = args.pdf.expanduser().resolve()
    book = args.book.expanduser().resolve()
    reader = PdfReader(str(pdf_path))
    pdfium_document = pdfium.PdfDocument(str(pdf_path))
    if len(reader.pages) != 192:
        raise ValueError(f"Expected 192 source pages, found {len(reader.pages)}")
    selected = None
    if args.pages:
        selected = {int(value.strip()) for value in args.pages.split(",") if value.strip()}
    art_dir = book / "images" / "source-layout"
    build_records: list[dict[str, Any]] = []

    with pdfplumber.open(str(pdf_path)) as source:
        for page_number, plumber_page in enumerate(source.pages, start=1):
            if selected is not None and page_number not in selected:
                continue
            path = output_path(book, page_number)
            semantics, activity_count = semantic_markup(path)
            folio = printed_folio(page_number)
            visual_text, font_rules = render_text_layer(
                plumber_page,
                pdfium_document[page_number - 1],
                page_number,
                folio,
            )
            visual_art, components = render_graphic_components(
                pdfium_document[page_number - 1],
                art_dir,
                page_number,
                float(plumber_page.height),
            )
            word_map = converted_word_map(book, reader.pages[page_number - 1], page_number)
            generated_html = page_template(
                    page_number,
                    folio,
                    float(plumber_page.width),
                    float(plumber_page.height),
                    visual_art,
                    visual_text,
                    font_rules,
                    semantics,
                    word_map,
                )
            generated_html = re.sub(r"[ \t]+(?=\n)", "", generated_html)
            path.write_text(generated_html, encoding="utf-8", newline="\n")
            build_records.append(
                {
                    "page": page_number,
                    "folio": folio,
                    "width": float(plumber_page.width),
                    "height": float(plumber_page.height),
                    "glyphs": len(plumber_page.chars),
                    "art_components": components,
                    "activity_count": activity_count,
                    "highlight_ids": len(word_map),
                }
            )
            print(
                f"page {page_number:03d}: glyphs={len(plumber_page.chars)} "
                f"art={len(components)} activities={activity_count} highlights={len(word_map)}",
                flush=True,
            )

    report_path = book / "tmp" / "adt-book-builder" / "exact-layout-build.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "pdf": str(pdf_path),
                "physical_pages": len(reader.pages),
                "selected_pages": sorted(selected) if selected is not None else "all",
                "pages_built": len(build_records),
                "page_records": build_records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
