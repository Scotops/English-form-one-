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
CHAPTER_OPENER_SOURCE_PAGES = {7, 15, 30, 46, 66, 91, 106, 129}
COVER_TITLE_ID = "pg001_cover_title"
COVER_TITLE_TEXT = "English for Secondary Schools. Student’s Book Form One."
COVER_TITLE_COMPONENT_IDS = {
    "pg001_n0002",
    "pg001_n0003",
    "pg001_n0005",
    "pg001_n0006",
}

ACKNOWLEDGEMENTS_CREDITS = (
    (
        "pg005_credit_writers",
        "Writers: Ms Neema B. Matingo, Ms Asia M. Akaro, Mr Francis J. Kibadu, "
        "Dr Moshi M. Kimizi and Ms Mercy G. Mandia.",
    ),
    (
        "pg005_credit_editors",
        "Editors: Dr Emmanuel P. Lema, Dr Julius J. Taji, Dr Ponsiano S. Kanijo, "
        "Mr Richard S. Mabala and Mr Justin A. Msuya.",
    ),
    (
        "pg005_credit_designer",
        "Designer: Mr Frank P. Maridadi.",
    ),
    (
        "pg005_credit_illustrators",
        "Illustrators: Mr Yohana P. Mwenda and Mr Gwakisa M. Ulimboka.",
    ),
    (
        "pg005_credit_coordinator",
        "Coordinator: Ms Neema B. Matingo.",
    ),
)
ACKNOWLEDGEMENTS_CREDIT_IDS = {text_id for text_id, _value in ACKNOWLEDGEMENTS_CREDITS}
ACKNOWLEDGEMENTS_CREDIT_COMPONENT_IDS = {
    "pg005_n0010", "pg005_n0012",
    "pg005_n0015", "pg005_n0017",
    "pg005_n0020", "pg005_n0022",
    "pg005_n0025", "pg005_n0027",
    "pg005_n0030", "pg005_n0032",
}

# The source table of contents prints bare page references.  Give those
# references enough context for read-aloud without changing the facsimile.
TOC_PAGE_NUMBER_SPEECH = {
    "pg003_n0007": "Page number Roman number five.",
    "pg003_n0011": "Page number Roman number six.",
    "pg003_n0016": "Page number 1.",
    "pg003_n0021": "Page number 9.",
    "pg003_n0026": "Page number 24.",
    "pg003_n0031": "Page number 40.",
    "pg003_n0036": "Page number 60.",
    "pg003_n0041": "Page number 85.",
    "pg003_n0046": "Page number 100.",
    "pg003_n0051": "Page number 123.",
    "pg004_n0005": "Page number 139.",
    "pg004_n0009": "Page number 158.",
    "pg004_n0012": "Page number 180.",
    "pg004_n0015": "Page number 181.",
    "pg004_n0019": "Page number 182.",
}

# These extracted image labels repeat the adjacent printed contents text.
TOC_DUPLICATE_IMAGE_IDS = {
    "pg003_im004",
    "pg003_im005",
    "pg003_im006",
    "pg003_im007",
    "pg003_im008",
    "pg003_im009",
    "pg003_im010",
    "pg003_im011",
    "pg003_im012",
    "pg003_im013",
    "pg003_im014",
}

TOC_TEXT_IDS = (
    "pg003_n0002",
    "pg003_n0006", "pg003_n0007",
    "pg003_n0010", "pg003_n0011",
    "pg003_n0014", "pg003_n0015", "pg003_n0016",
    "pg003_n0019", "pg003_n0020", "pg003_n0021",
    "pg003_n0024", "pg003_n0025", "pg003_n0026",
    "pg003_n0029", "pg003_n0030", "pg003_n0031",
    "pg003_n0034", "pg003_n0035", "pg003_n0036",
    "pg003_n0039", "pg003_n0040", "pg003_n0041",
    "pg003_n0044", "pg003_n0045", "pg003_n0046",
    "pg003_n0049", "pg003_n0050", "pg003_n0051",
    "pg004_n0003", "pg004_n0004", "pg004_n0005",
    "pg004_n0007", "pg004_n0008", "pg004_n0009",
    "pg004_n0011", "pg004_n0012",
    "pg004_n0014", "pg004_n0015",
    "pg004_n0017", "pg004_n0018", "pg004_n0019",
)

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


def is_prepress_text(value: str) -> bool:
    """Identify printer-only production marks outside the finished page."""
    stripped = value.strip()
    return ".indd" in stripped.lower() or bool(
        re.fullmatch(r"\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}", stripped)
    )


def is_running_decoration_text(source_page: int, value: str) -> bool:
    """Exclude the repeated footer labels hidden with the decorative bands."""
    if source_page == 1:
        return False
    normalized = " ".join(value.replace("’", "'").split()).lower()
    return normalized in {
        "english for secondary schools",
        "student's book form one",
    }


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
    page_card_classes = "adt-page-card"
    if source_page > 1:
        page_card_classes += " adt-page-has-running-decoration"
    if source_page in CHAPTER_OPENER_SOURCE_PAGES:
        page_card_classes += " adt-page-chapter-opener"
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
  <link href="./content/book-fidelity.css?v=5" rel="stylesheet" />
  <link href="./assets/libs/fontawesome/css/all.min.css" rel="stylesheet" />
  <link href="./assets/fonts.css" rel="stylesheet" />
</head>
<body class="adt-reader-shell">
  <main class="adt-reader-main" id="page-top">
    <h1 class="adt-visually-hidden">{html_lib.escape(TITLE)}</h1>
    <div id="content" class="adt-facsimile-shell opacity-0" data-adt-facsimile="true" data-source-pdf-page="{source_page}" data-printed-page="{html_lib.escape(label)}">
      <section class="{page_card_classes}" role="article" data-section-type="facsimile_page" data-section-id="{section_id}" aria-label="Textbook page">
        <img class="adt-facsimile-image" src="images/pages/pg{source_page:03d}_page.jpg" width="{width}" height="{height}" alt="Original textbook page {html_lib.escape(label)}." />
        <span class="adt-printed-page-number" aria-hidden="true">{html_lib.escape(label)}</span>
      </section>
      <section id="accessible-transcript" class="adt-accessible-transcript" aria-label="Accessible text transcript">
{transcript}
      </section>
    </div>
  </main>
  <div class="relative z-50" id="interface-container"></div>
  <div class="relative z-50" id="nav-container"></div>
  <script src="./assets/offline-preloader.js?v=6"></script>
  <script src="./assets/scorm.js"></script>
  <script src="./assets/facsimile-highlight.js?v=4"></script>
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

    # Page numbers remain visible in the facsimile, but they are not standalone
    # read-aloud items.  Their old mappings are removed so the reader never says
    # "front matter page" or "printed book page" while reading page content.
    for source_page in range(1, pdf_page_count + 1):
        text_id = f"pg{source_page:03d}_page_number"
        texts.pop(text_id, None)
        texts.pop(f"{text_id}_easy_read", None)
        audios.pop(text_id, None)
        audios.pop(f"{text_id}_easy_read", None)

    for text_id, value in TOC_PAGE_NUMBER_SPEECH.items():
        texts[text_id] = value
        texts[f"{text_id}_easy_read"] = value
        filename = f"{text_id}_toc_v2.mp3"
        audios[text_id] = filename
        audios[f"{text_id}_easy_read"] = filename
        audio_jobs[text_id] = {"text": value, "filename": filename}

    # A single continuous opening clip prevents the very short standalone word
    # "English" from being skipped while the player initializes on the cover.
    texts[COVER_TITLE_ID] = COVER_TITLE_TEXT
    texts[f"{COVER_TITLE_ID}_easy_read"] = COVER_TITLE_TEXT
    cover_audio = f"{COVER_TITLE_ID}_v2.mp3"
    audios[COVER_TITLE_ID] = cover_audio
    audios[f"{COVER_TITLE_ID}_easy_read"] = cover_audio
    audio_jobs[COVER_TITLE_ID] = {"text": COVER_TITLE_TEXT, "filename": cover_audio}

    # Pair each short acknowledgements credit label with its names.  Keeping
    # labels such as "Editors" inside a substantial clip prevents the player
    # from advancing past them during rapid segment transitions.
    for text_id, value in ACKNOWLEDGEMENTS_CREDITS:
        texts[text_id] = value
        texts[f"{text_id}_easy_read"] = value
        filename = f"{text_id}_v2.mp3"
        audios[text_id] = filename
        audios[f"{text_id}_easy_read"] = filename
        audio_jobs[text_id] = {"text": value, "filename": filename}

    # Easy Read must not paraphrase or renumber contents entries.  Both modes
    # use the book's exact titles and the same standard audio clips so the
    # requested title -> description -> page-number order is deterministic.
    for text_id in TOC_TEXT_IDS:
        texts[f"{text_id}_easy_read"] = texts[text_id]
        audios[f"{text_id}_easy_read"] = audios[text_id]

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
        page_items = []
        if source_page == 1:
            page_items.append((COVER_TITLE_ID, COVER_TITLE_TEXT))
        base_items = list(
            (text_id, value)
            for text_id, value in texts.items()
            if text_id.startswith(prefix)
            and not text_id.endswith("_easy_read")
            and text_id != COVER_TITLE_ID
            and text_id not in COVER_TITLE_COMPONENT_IDS
            and text_id not in ACKNOWLEDGEMENTS_CREDIT_IDS
            and text_id not in ACKNOWLEDGEMENTS_CREDIT_COMPONENT_IDS
            and text_id not in TOC_DUPLICATE_IMAGE_IDS
            and not is_prepress_text(value)
            and not is_running_decoration_text(source_page, value)
        )
        for item in base_items:
            page_items.append(item)
            if source_page == 5 and item[0] == "pg005_n0006":
                page_items.extend(ACKNOWLEDGEMENTS_CREDITS)
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
