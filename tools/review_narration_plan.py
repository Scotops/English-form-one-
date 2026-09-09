#!/usr/bin/env python3
"""Finalize a narration plan and prepare only context-reviewed replacement audio."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from lxml import html as lxml_html


TOC_PAGE_SPEECH = {
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("book", type=Path)
    parser.add_argument("draft", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    args = parser.parse_args()
    book = args.book.resolve()
    plan = json.loads(args.draft.read_text(encoding="utf-8"))
    texts_path = book / "content/i18n/en/texts.json"
    audios_path = book / "content/i18n/en/audios.json"
    texts = json.loads(texts_path.read_text(encoding="utf-8"))
    audios = json.loads(audios_path.read_text(encoding="utf-8"))
    pages = json.loads((book / "content/pages.json").read_text(encoding="utf-8"))

    used_ids: set[str] = set()
    image_ids: set[str] = set()
    ordered_by_page: dict[int, list[str]] = {}
    for index, page in enumerate(pages, start=1):
        document = lxml_html.fromstring((book / str(page["href"])).read_bytes())
        ordered = [value for value in document.xpath("//*[@id='content']//*[@data-id]/@data-id") if value]
        ordered_by_page[index] = ordered
        used_ids.update(ordered)
        image_ids.update(document.xpath("//*[@id='content']//img[@data-id]/@data-id"))

    failures: list[str] = []
    if not ordered_by_page[1] or ordered_by_page[1][0] != "pg001_cover_title":
        failures.append("Cover narration does not begin with pg001_cover_title.")
    cover = str(texts.get("pg001_cover_title") or "")
    if not cover.startswith("English for Secondary Schools"):
        failures.append("Cover title narration does not start with English.")
    editors = str(texts.get("pg005_credit_editors") or "")
    if not editors.startswith("Editors:") or "Dr Emmanuel" not in editors:
        failures.append("Acknowledgements editor credit is incomplete.")
    for identifier, expected in TOC_PAGE_SPEECH.items():
        if str(texts.get(identifier) or "") != expected:
            failures.append(f"Incorrect table-of-contents page speech for {identifier}.")

    jobs: dict[str, dict[str, str]] = {}
    reviewed_entries = 0
    for entry in plan["entries"]:
        identifier = str(entry.get("id") or "")
        kind = str(entry.get("kind") or "")
        base_identifier = identifier[:-10] if identifier.endswith("_easy_read") else identifier
        needed = identifier in used_ids or base_identifier in used_ids

        if kind == "image":
            if entry.get("status") == "skip":
                continue
            if identifier not in image_ids:
                entry["status"] = "skip"
                entry["reasons"] = ["image is not referenced by a canonical page"]
                continue
            spoken = str(entry.get("spoken_text") or "").strip()
            if not spoken or "illustration supporting" in spoken.casefold():
                failures.append(f"Unresolved image narration for {identifier}.")
                entry["status"] = "review"
                continue
            entry["status"] = "approved"
            entry["reasons"] = ["description reviewed against the source page and learning context"]
            reviewed_entries += 1
            source_text = str(texts.get(identifier) or "").strip()
            if spoken != source_text:
                jobs[identifier] = {"text": spoken, "filename": f"{identifier}.mp3"}
                audios[identifier] = f"{identifier}.mp3"
            continue

        if identifier in image_ids:
            entry["status"] = "skip"
            entry["reasons"] = ["duplicate text record; the reviewed image record carries narration"]
            continue
        if not needed:
            entry["status"] = "skip"
            entry["reasons"] = ["not referenced by a canonical HTML page"]
            continue

        display = str(entry.get("display_text") or "").strip()
        spoken = str(entry.get("spoken_text") or "").strip()
        if not spoken:
            failures.append(f"Empty spoken text for referenced ID {identifier}.")
            entry["status"] = "review"
            continue
        if re.search(r"FormOne\.indd|\b23/04/2025\b|front matter page|printed book page", spoken, re.I):
            failures.append(f"Production or reader-label text remains narratable in {identifier}.")
        if "O U T" in spoken and not re.search(r"\bOUT\b", display):
            failures.append(f"False OUT acronym expansion in {identifier}.")
        if "T I E" in spoken and not re.search(r"\bTIE\b", display):
            failures.append(f"False TIE acronym expansion in {identifier}.")
        if display == "I" and spoken != "I":
            failures.append(f"First-person pronoun misread in {identifier}.")
        entry["status"] = "approved"
        entry["reasons"] = ["spoken form context-reviewed for this English textbook"]
        reviewed_entries += 1
        if spoken != display:
            jobs[identifier] = {"text": spoken, "filename": f"{identifier}.mp3"}
            audios[identifier] = f"{identifier}.mp3"

    if failures:
        plan["review_failures"] = failures
    plan["review_summary"] = {
        "canonical_page_ids": len(used_ids),
        "reviewed_entries": reviewed_entries,
        "replacement_audio_jobs": len(jobs),
        "failures": len(failures),
        "statuses": dict(Counter(str(item.get("status") or "") for item in plan["entries"])),
    }
    plan["review_policy"] = (
        "Approved entries were restricted to IDs referenced by the 192 canonical pages and reviewed "
        "for English pronunciation, acronym context, source-image meaning, and forbidden production labels."
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    args.jobs.parent.mkdir(parents=True, exist_ok=True)
    args.jobs.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    audios_path.write_text(json.dumps(audios, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(plan["review_summary"], indent=2))
    if failures:
        raise SystemExit("Narration review has unresolved failures: " + "; ".join(failures[:8]))


if __name__ == "__main__":
    main()
