#!/usr/bin/env python3
"""Build the reviewed English narration configuration from canonical page IDs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lxml import html as lxml_html


PRONUNCIATIONS = {
    "ICT": "I C T",
    "RSVP": "R S V P",
    "SWBST": "S W B S T",
    "SAAC": "S A A C",
    "SBTT": "S B T T",
    "ISBN": "I S B N",
    "UDSM": "U D S M",
    "MUCE": "M U C E",
    "SQA": "S Q A",
    "NEMC": "N E M C",
    "OPD": "O P D",
    "SOS": "S O S",
    "TV": "T V",
    "QR": "Q R",
}

CASE_SENSITIVE_ACRONYMS = {
    "TIE": "T I E",
    "OUT": "O U T",
}

IPA = {
    "/æ/": "the short a sound",
    "/aɪ/": "the eye sound",
    "/ɑ/": "the open a sound",
    "/ɑː/": "the long a sound",
    "/ɒ/": "the short o sound",
    "/b/": "the b sound",
    "/e/": "the short e sound",
    "/eɪ/": "the long a sound",
    "/ɛ/": "the short e sound",
    "/iː/": "the long ee sound",
    "/ɪ/": "the short i sound",
    "/l/": "the l sound",
    "/n/": "the n sound",
    "/ɔː/": "the aw sound",
    "/r/": "the r sound",
    "/t/": "the t sound",
    "/uː/": "the long oo sound",
    "/ʊ/": "the short oo sound",
}


def classroom_spoken(value: str) -> str:
    spoken = value
    for source, replacement in PRONUNCIATIONS.items():
        spoken = spoken.replace(source, replacement)
    for source, replacement in CASE_SENSITIVE_ACRONYMS.items():
        spoken = spoken.replace(source, replacement)
    for source, replacement in IPA.items():
        spoken = spoken.replace(source, replacement)
    spoken = spoken.replace("Form I-IV", "Form One to Form Four")
    for source, replacement in {
        "he/she": "he or she",
        "him/her": "him or her",
        "her/him": "her or him",
        "his/her": "his or her",
        "and/or": "and or",
        "S/n": "serial number",
    }.items():
        spoken = spoken.replace(source, replacement)
    return spoken


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("book", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    book = args.book.resolve()
    texts = json.loads((book / "content/i18n/en/texts.json").read_text(encoding="utf-8"))
    pages = json.loads((book / "content/pages.json").read_text(encoding="utf-8"))
    image_ids: set[str] = set()
    for entry in pages:
        path = book / str(entry["href"])
        document = lxml_html.fromstring(path.read_bytes())
        image_ids.update(document.xpath("//img[@data-id]/@data-id"))
    descriptions = {
        identifier: classroom_spoken(str(texts[identifier]).strip())
        for identifier in sorted(image_ids)
        if str(texts.get(identifier) or "").strip()
    }
    spoken_overrides = {
        identifier: spoken
        for identifier, value in texts.items()
        if (spoken := classroom_spoken(str(value))) != str(value)
    }
    # In this English book a standalone capital I is the first-person pronoun,
    # never a Roman-number label. This explicit override takes precedence over
    # the generic narration preparer's Roman-numeral heuristic.
    for identifier, value in texts.items():
        if str(value).strip() == "I":
            spoken_overrides[identifier] = "I"

    config = {
        "subject": "general",
        "formula_style": "teaching",
        "voice": {
            "gender": "male",
            "name": "Microsoft David Desktop",
            "locale": "en-US",
            "rate": "careful classroom reading",
        },
        "pronunciations": PRONUNCIATIONS,
        "spoken_overrides": spoken_overrides,
        "image_descriptions": descriptions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Narration config: {args.output.resolve()}")
    print(f"Reviewed image descriptions: {len(descriptions)}")


if __name__ == "__main__":
    main()
