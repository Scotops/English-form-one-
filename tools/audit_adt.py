#!/usr/bin/env python3
"""Validate structural, text, image, pagination, and audio coverage in the ADT."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from lxml import html
from pypdf import PdfReader


PAGE_RE = re.compile(r"pg(\d{3})_sec\d{3}$")
WORD_RE = re.compile(r"[a-z0-9]+(?:['’][a-z0-9]+)?", re.IGNORECASE)
PREPRESS_TIMESTAMP_RE = re.compile(r"^\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}$")


def ordered_data_ids(path: Path) -> list[str]:
    tree = html.fromstring(path.read_text(encoding="utf-8"))
    result: list[str] = []
    seen: set[str] = set()
    for element in tree.xpath("//*[@data-id]"):
        text_id = element.get("data-id")
        if text_id and text_id not in seen:
            seen.add(text_id)
            result.append(text_id)
    return result


def words(value: str) -> list[str]:
    return [token.lower().replace("’", "'") for token in WORD_RE.findall(value)]


def coverage(reference: str, candidate: str) -> float:
    wanted = Counter(words(reference))
    available = Counter(words(candidate))
    if not wanted:
        return 1.0
    matched = sum((wanted & available).values())
    return matched / sum(wanted.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    manifest = json.loads((root / "content/pages.json").read_text(encoding="utf-8"))
    texts = json.loads((root / "content/i18n/en/texts.json").read_text(encoding="utf-8"))
    audios = json.loads((root / "content/i18n/en/audios.json").read_text(encoding="utf-8"))
    audio_dir = root / "content/i18n/en/audio"

    manifest_ids: list[str] = []
    missing_hrefs: list[str] = []
    bad_meta_indices: list[dict[str, object]] = []
    bad_section_ids: list[dict[str, str]] = []
    ids_by_page: dict[int, list[str]] = defaultdict(list)
    all_ids: list[str] = []
    missing_word_box_files: list[str] = []
    missing_highlight_scripts: list[str] = []
    visible_page_overlays: list[str] = []
    prepress_transcript_text: list[dict[str, str]] = []

    for index, entry in enumerate(manifest, start=1):
        section_id = entry["section_id"]
        manifest_ids.append(section_id)
        page_match = PAGE_RE.match(section_id)
        if page_match:
            source_page = int(page_match.group(1))
        else:
            source_page = -1
        href = root / entry["href"]
        if not href.exists():
            missing_hrefs.append(entry["href"])
            continue
        tree = html.fromstring(href.read_text(encoding="utf-8"))
        title_meta = tree.xpath("//meta[@name='title-id']/@content")
        index_meta = tree.xpath("//meta[@name='page-section-id']/@content")
        if not title_meta or title_meta[0] != section_id:
            bad_section_ids.append(
                {"href": entry["href"], "manifest": section_id, "html": title_meta[0] if title_meta else ""}
            )
        if not index_meta or index_meta[0] != str(index):
            bad_meta_indices.append(
                {"href": entry["href"], "expected": index, "actual": index_meta[0] if index_meta else ""}
            )
        if not tree.xpath("//script[contains(@src, 'facsimile-highlight.js')]"):
            missing_highlight_scripts.append(entry["href"])
        if tree.xpath(
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' adt-page-toolbar ')]"
            " | //a[contains(concat(' ', normalize-space(@class), ' '), ' adt-transcript-link ')]"
        ):
            visible_page_overlays.append(entry["href"])
        for segment in tree.xpath("//section[@id='accessible-transcript']//*[@data-id]"):
            value = " ".join("".join(segment.itertext()).split())
            if ".indd" in value.lower() or PREPRESS_TIMESTAMP_RE.fullmatch(value):
                prepress_transcript_text.append(
                    {"href": entry["href"], "id": segment.get("data-id") or "", "text": value}
                )
        page_ids = ordered_data_ids(href)
        all_ids.extend(page_ids)
        if source_page > 0:
            word_box_path = root / "content/word-boxes" / f"pg{source_page:03d}.json"
            if not word_box_path.is_file():
                missing_word_box_files.append(word_box_path.relative_to(root).as_posix())
            for text_id in page_ids:
                if text_id not in ids_by_page[source_page]:
                    ids_by_page[source_page].append(text_id)

    html_ids = set(all_ids)
    text_ids = set(texts)
    audio_ids = set(audios)
    missing_audio_files = [
        {"id": key, "file": filename}
        for key, filename in audios.items()
        if not (audio_dir / filename).is_file() or (audio_dir / filename).stat().st_size == 0
    ]

    source_page_numbers = sorted(ids_by_page)
    missing_source_pages = [
        page for page in range(source_page_numbers[0], source_page_numbers[-1] + 1) if page not in ids_by_page
    ] if source_page_numbers else []

    result: dict[str, object] = {
        "manifest_entries": len(manifest),
        "unique_manifest_ids": len(set(manifest_ids)),
        "missing_hrefs": missing_hrefs,
        "bad_page_section_meta": bad_meta_indices,
        "bad_title_meta": bad_section_ids,
        "html_data_ids": len(html_ids),
        "text_entries": len(texts),
        "audio_mappings": len(audios),
        "html_ids_missing_text": sorted(html_ids - text_ids),
        "html_ids_missing_audio": sorted(html_ids - audio_ids),
        "text_ids_missing_html": sorted(text_ids - html_ids),
        "audio_ids_missing_text": sorted(audio_ids - text_ids),
        "missing_or_empty_audio_files": missing_audio_files,
        "source_pages_represented": len(source_page_numbers),
        "missing_source_pages": missing_source_pages,
        "duplicate_ids_across_manifest_pages": {
            key: count for key, count in Counter(all_ids).items() if count > 1
        },
        "missing_word_box_files": missing_word_box_files,
        "missing_highlight_scripts": missing_highlight_scripts,
        "visible_page_overlays": visible_page_overlays,
        "prepress_transcript_text": prepress_transcript_text,
        "floating_highlight_fallback_present": (
            "adt-reading-word" in (root / "assets/facsimile-highlight.js").read_text(encoding="utf-8")
            or "adt-reading-word" in (root / "content/book-fidelity.css").read_text(encoding="utf-8")
        ),
    }

    if args.pdf:
        reader = PdfReader(args.pdf)
        per_page: list[dict[str, object]] = []
        for page_number, pdf_page in enumerate(reader.pages, start=1):
            reference = pdf_page.extract_text() or ""
            candidate = " ".join(texts.get(text_id, "") for text_id in ids_by_page.get(page_number, []))
            per_page.append(
                {
                    "source_page": page_number,
                    "printed_page": (
                        ["i", "ii", "iii", "iv", "v", "vi"][page_number - 1]
                        if page_number <= 6
                        else str(page_number - 6)
                    ),
                    "coverage": round(coverage(reference, candidate), 4),
                    "pdf_words": len(words(reference)),
                    "adt_words": len(words(candidate)),
                }
            )
        result["pdf_pages"] = len(reader.pages)
        result["text_coverage_by_page"] = per_page
        result["text_coverage_summary"] = {
            "below_0_75": sum(item["coverage"] < 0.75 for item in per_page),
            "below_0_90": sum(item["coverage"] < 0.90 for item in per_page),
            "below_0_95": sum(item["coverage"] < 0.95 for item in per_page),
            "mean": round(sum(item["coverage"] for item in per_page) / len(per_page), 4),
        }
        result["lowest_text_coverage"] = sorted(per_page, key=lambda item: item["coverage"])[:20]

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, value in result.items():
            if isinstance(value, list) and len(value) > 20:
                print(f"{key}: {len(value)} items (first 20: {value[:20]})")
            elif isinstance(value, dict) and len(value) > 20:
                sample = list(value.items())[:20]
                print(f"{key}: {len(value)} items (first 20: {sample})")
            else:
                print(f"{key}: {value}")

    errors = any(
        result[key]
        for key in (
            "missing_hrefs",
            "bad_page_section_meta",
            "bad_title_meta",
            "html_ids_missing_text",
            "html_ids_missing_audio",
            "audio_ids_missing_text",
            "missing_or_empty_audio_files",
            "missing_source_pages",
            "missing_word_box_files",
            "missing_highlight_scripts",
            "visible_page_overlays",
            "prepress_transcript_text",
            "floating_highlight_fallback_present",
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
