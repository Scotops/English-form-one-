#!/usr/bin/env python3
"""Build a source-faithful, one-PDF-page-per-screen ADT reader."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import shutil
from pathlib import Path

from PIL import Image
from pypdf import PdfReader


TITLE = "English for Secondary Schools Student’s Book Form One"
ROMAN_PAGES = ("i", "ii", "iii", "iv", "v", "vi")

BIBLIOGRAPHY = [
    ("pg186_n0001", "Student’s Book Form One"),
    ("pg186_n0002", "English for Secondary Schools"),
    ("pg186_n0003", "Bibliography"),
    ("pg186_n0004", "Cunningham, S., & Moor, P. (2007). New cutting age elementary: Mini-dictionary. Pearson Longman."),
    ("pg186_n0005", "Dosi, S., & Esmail, N. (2013). English for secondary schools: Form 2. Oxford University Press."),
    ("pg186_n0006", "Hewings, M. (2013). Advanced English grammar in use: Questions with answers. Cambridge University Press."),
    ("pg186_n0007", "Longman active study dictionary (New Edition). (2004). Pearson Education Ltd."),
    ("pg186_n0008", "McIntosh, C. (Ed.). (2015). Cambridge advanced learner’s dictionary, 4th Edition. Cambridge University Press."),
    ("pg186_n0009", "Ministry of Education. (1977). Learning Through Language. Tanzania Publishing House."),
    ("pg186_n0010", "Murphy, R. (1998). Essential English grammar: A self-study reference and practice book for elementary students of English. Cambridge University Press."),
    ("pg186_n0011", "Mutiso, N., & Sendora, J. (2015). Fundamentals of English: Form 2. Longhorn."),
    ("pg186_n0012", "Shekighenda, A. T., & Durkin, J. (2009). Secondary English: Form 2. Oxford University Press."),
    ("pg186_n0013", "Tanzania Institute of Education. (1996). Selected poems. Printpack (T) Ltd."),
    ("pg186_n0014", "Webb, B., & Grant, N. (2007). English in use: Student’s book 3. Pearson Education."),
    ("pg186_n0015", "English FormOne.indd 180"),
    ("pg186_n0016", "23/04/2025 17:12"),
]

ENHANCED_DESCRIPTIONS = {
    "pg039_im005_crop_v1": (
        "Long vowel words table. Long ‘a’, /ɑː/: bar, car, tar, far, star, cigar, scar, mart, cart, dart. "
        "Long ‘a’, /eɪ/: bake, cake, lake, fake, grate, bake, baby, play, maid, jail. "
        "Long ‘e’, /iː/: tree, bee, feel, be, sea, seen, beach, clean, steal, read. "
        "Long ‘i’, /aɪ/: shine, pine, light, tie, fine, why, delight, white, nice, apply. "
        "Long ‘o’, /ɔː/: more, shore, chore, sore, core, door, store, straw, phone, roast. "
        "Long ‘u’, /uː/: food, human, soup, school, uniform, blue, huge, fruit, cute, room."
    ),
    "pg064_im001": (
        "Vocabulary bingo card. Row one: apartment, intend, opinion, labour, repair. "
        "Row two: indulge, embrace, summary, rapid, vivid. "
        "Row three: avail, urgent, BINGO, occupation, portion. "
        "Row four: weary, pledge, hygiene, essential, awful. "
        "Row five: exhaust, compile, accurate, similar, recycle. "
        "Colored markers are placed on avail, pledge, hygiene, and awful."
    ),
    "pg067_im004": (
        "Health-related word-search grid. Read each row from left to right: "
        "c a s t d i a g n o s i s; "
        "b x y b q e t y o p u f h; "
        "u z r w y w o u n d r g e; "
        "r a i q d u k o q o g n a; "
        "n d n u r s e l d c e q l; "
        "e f g z h e l y i t o p t; "
        "p r e s r i p t i o n j h; "
        "p a i n k i l l e r z v q; "
        "j k m f g m e d i c i n e."
    ),
}


def printed_page(source_page: int) -> str:
    return ROMAN_PAGES[source_page - 1] if source_page <= 6 else str(source_page - 6)


def spoken_page(source_page: int) -> str:
    if source_page <= 6:
        words = ("one", "two", "three", "four", "five", "six")
        return f"Front matter page {words[source_page - 1]}, shown as Roman numeral {ROMAN_PAGES[source_page - 1]}."
    return f"Printed book page {source_page - 6}."


def update_inline_json(root: Path) -> None:
    path = root / "assets/offline-preloader.js"
    source = path.read_text(encoding="utf-8")
    marker = "  var INLINE = "
    start = source.index(marker) + len(marker)
    end = source.index(";\n  var BASE_DIR", start)
    inline = json.loads(source[start:end])
    for key in list(inline):
        if not key.startswith("./") or not key.endswith(".json"):
            continue
        disk_path = root / key[2:]
        if disk_path.is_file():
            inline[key] = json.loads(disk_path.read_text(encoding="utf-8"))
    encoded = json.dumps(inline, ensure_ascii=False, separators=(",", ":"))
    path.write_text(source[:start] + encoded + source[end:], encoding="utf-8", newline="\n")


def page_html(
    *,
    source_page: int,
    section_index: int,
    image_path: Path,
    text_items: list[tuple[str, str]],
) -> str:
    section_id = f"pg{source_page:03d}_sec001"
    label = printed_page(source_page)
    with Image.open(image_path) as image:
        width, height = image.size
    transcript = "\n".join(
        "        <span class=\"adt-transcript-segment\" data-id=\"{}\">{}</span>".format(
            html_lib.escape(text_id, quote=True), html_lib.escape(value)
        )
        for text_id, value in text_items
        if any(character.isalnum() for character in value)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html_lib.escape(TITLE)} - Page {html_lib.escape(label)}</title>
  <meta name="title-id" content="{section_id}" />
  <meta name="page-section-id" content="{section_index}" />
  <meta name="printed-page-number" content="{html_lib.escape(label)}" />
  <link href="./content/tailwind_output.css" rel="stylesheet" />
  <link href="./content/book-fidelity.css?v=3" rel="stylesheet" />
  <link href="./assets/libs/fontawesome/css/all.min.css" rel="stylesheet" />
  <link href="./assets/fonts.css" rel="stylesheet" />
</head>
<body class="adt-reader-shell">
  <main class="adt-reader-main" id="page-top">
    <h1 class="adt-visually-hidden">{html_lib.escape(TITLE)}, printed page {html_lib.escape(label)}</h1>
    <div id="content" class="adt-facsimile-shell opacity-0" data-adt-facsimile="true" data-source-pdf-page="{source_page}" data-printed-page="{html_lib.escape(label)}">
      <section class="adt-page-card" role="article" data-section-type="facsimile_page" data-section-id="{section_id}" aria-label="Printed page {html_lib.escape(label)}">
        <img class="adt-facsimile-image" src="images/pages/pg{source_page:03d}_page.jpg" width="{width}" height="{height}" alt="Original textbook page {html_lib.escape(label)}." />
      </section>
      <section id="accessible-transcript" class="adt-accessible-transcript" aria-label="Accessible text transcript for printed page {html_lib.escape(label)}">
{transcript}
      </section>
    </div>
  </main>
  <div class="relative z-50" id="interface-container"></div>
  <div class="relative z-50" id="nav-container"></div>
  <script src="./assets/offline-preloader.js?v=4"></script>
  <script src="./assets/scorm.js"></script>
  <script src="./assets/facsimile-highlight.js?v=1"></script>
  <script src="./assets/base.bundle.local.js"></script>
</body>
</html>
"""


def write_manifest(root: Path) -> None:
    excluded_parts = {".git", "tmp", "tools", "source-fragments", "__pycache__"}
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name in {
            ".gitignore",
            ".nojekyll",
            "AGENTS.md",
            "README.md",
            "imsmanifest.xml",
        }:
            continue
        relative = path.relative_to(root)
        if any(part in excluded_parts for part in relative.parts):
            continue
        files.append(relative.as_posix())
    files.sort(key=lambda value: (value != "index.html", value))
    file_lines = "\n".join(f'      <file href="{html_lib.escape(value, quote=True)}"/>' for value in files)
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="ADT_ENGLISH_FORMONE_APRIL_23" version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ADT_ORG">
    <organization identifier="ADT_ORG">
      <title>{html_lib.escape(TITLE)}</title>
      <item identifier="ITEM_1" identifierref="RESOURCE_1">
        <title>{html_lib.escape(TITLE)}</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RESOURCE_1" type="webcontent" adlcp:scormtype="sco" href="index.html">
{file_lines}
    </resource>
  </resources>
</manifest>
"""
    (root / "imsmanifest.xml").write_text(manifest, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    pdf_page_count = len(PdfReader(args.pdf).pages)
    if pdf_page_count != 192:
        raise ValueError(f"Expected 192 source pages, found {pdf_page_count}")

    image_dir = root / "images/pages"
    missing_images = [page for page in range(1, pdf_page_count + 1) if not (image_dir / f"pg{page:03d}_page.jpg").is_file()]
    if missing_images:
        raise FileNotFoundError(f"Missing rendered page images: {missing_images}")

    texts_path = root / "content/i18n/en/texts.json"
    audios_path = root / "content/i18n/en/audios.json"
    texts = json.loads(texts_path.read_text(encoding="utf-8"))
    audios = json.loads(audios_path.read_text(encoding="utf-8"))
    audio_jobs: dict[str, dict[str, str]] = {}

    for text_id, value in ENHANCED_DESCRIPTIONS.items():
        texts[text_id] = value
        filename = f"{text_id}.mp3"
        audios[text_id] = filename
        audio_jobs[text_id] = {"text": value, "filename": filename}

    for text_id, value in BIBLIOGRAPHY:
        texts[text_id] = value
        texts[f"{text_id}_easy_read"] = value
        filename = f"{text_id}.mp3"
        audios[text_id] = filename
        audios[f"{text_id}_easy_read"] = filename
        audio_jobs[text_id] = {"text": value, "filename": filename}

    for source_page in range(1, pdf_page_count + 1):
        text_id = f"pg{source_page:03d}_page_number"
        value = spoken_page(source_page)
        texts[text_id] = value
        texts[f"{text_id}_easy_read"] = value
        filename = f"{text_id}.mp3"
        audios[text_id] = filename
        audios[f"{text_id}_easy_read"] = filename
        audio_jobs[text_id] = {"text": value, "filename": filename}

    texts_path.write_text(json.dumps(texts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    audios_path.write_text(json.dumps(audios, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (root / "tools/audio_jobs.json").write_text(
        json.dumps(audio_jobs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    archive_dir = root / "content/source-fragments"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for path in root.glob("*.html"):
        source = path.read_text(encoding="utf-8")
        if 'data-adt-facsimile="true"' in source:
            continue
        destination = archive_dir / path.name
        if not destination.exists():
            shutil.move(str(path), destination)
        else:
            path.unlink()

    manifest: list[dict[str, object]] = []
    for source_page in range(1, pdf_page_count + 1):
        section_id = f"pg{source_page:03d}_sec001"
        href = "index.html" if source_page == 1 else f"{section_id}.html"
        manifest.append(
            {
                "section_id": section_id,
                "href": href,
                "page_number": printed_page(source_page) if source_page <= 6 else source_page - 6,
                "pdf_page": source_page,
            }
        )
    (root / "content/pages.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    toc_path = root / "content/toc.json"
    toc = json.loads(toc_path.read_text(encoding="utf-8"))
    for entry in toc:
        match = re.match(r"pg(\d{3})_", entry["section_id"])
        if not match:
            continue
        source_page = int(match.group(1))
        entry["section_id"] = f"pg{source_page:03d}_sec001"
        entry["href"] = "index.html" if source_page == 1 else f"pg{source_page:03d}_sec001.html"
    bibliography_entry = {
        "section_id": "pg186_sec001",
        "href": "pg186_sec001.html",
        "title": "Bibliography",
        "chapter_id": "pg186_n0003",
        "level": 1,
    }
    if not any(entry.get("chapter_id") == "pg186_n0003" for entry in toc):
        insert_at = next((index for index, entry in enumerate(toc) if entry.get("section_id", "") >= "pg187_"), len(toc))
        toc.insert(insert_at, bibliography_entry)
    toc_path.write_text(json.dumps(toc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    for source_page in range(1, pdf_page_count + 1):
        prefix = f"pg{source_page:03d}_"
        page_label_id = f"pg{source_page:03d}_page_number"
        page_items = [(page_label_id, texts[page_label_id])]
        page_items.extend(
            (text_id, value)
            for text_id, value in texts.items()
            if text_id.startswith(prefix)
            and text_id != page_label_id
            and not text_id.endswith("_easy_read")
        )
        section_id = f"pg{source_page:03d}_sec001"
        href = root / ("index.html" if source_page == 1 else f"{section_id}.html")
        href.write_text(
            page_html(
                source_page=source_page,
                section_index=source_page,
                image_path=image_dir / f"pg{source_page:03d}_page.jpg",
                text_items=page_items,
            ),
            encoding="utf-8",
            newline="\n",
        )

    update_inline_json(root)
    write_manifest(root)
    print(f"Built {pdf_page_count} source-faithful pages and {len(audio_jobs)} audio jobs.")


if __name__ == "__main__":
    main()
