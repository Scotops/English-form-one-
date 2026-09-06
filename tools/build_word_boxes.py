#!/usr/bin/env python3
"""Map ADT transcript words to their printed positions in the source PDF."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber
from lxml import html


WORD_RE = re.compile(r"[^\W_]+(?:[’'\-][^\W_]+)*", re.UNICODE)
IMAGE_ID_RE = re.compile(r"_im\d", re.IGNORECASE)


@dataclass(frozen=True)
class Token:
    text_id: str
    word_index: int
    text: str
    normalized: str


@dataclass(frozen=True)
class PdfToken:
    text: str
    normalized: str
    box: tuple[float, float, float, float]


def normalize_word(value: str) -> str:
    value = value.replace("’", "'").replace("‘", "'").replace("�", "")
    value = unicodedata.normalize("NFKD", value).lower()
    return "".join(character for character in value if character.isalnum())


def transcript_items(page_path: Path) -> list[tuple[str, list[Token]]]:
    tree = html.fromstring(page_path.read_text(encoding="utf-8"))
    items: list[tuple[str, list[Token]]] = []
    for element in tree.xpath("//section[@id='accessible-transcript']//*[@data-id]"):
        text_id = element.get("data-id")
        if not text_id:
            continue
        source = "".join(element.itertext())
        words: list[Token] = []
        for word_index, match in enumerate(WORD_RE.finditer(source)):
            normalized = normalize_word(match.group(0))
            if normalized:
                words.append(Token(text_id, word_index, match.group(0), normalized))
        if words:
            items.append((text_id, words))
    return items


def pdf_tokens(page: pdfplumber.page.Page) -> list[PdfToken]:
    output: list[PdfToken] = []
    for word in page.extract_words(use_text_flow=True, keep_blank_chars=False):
        source = str(word.get("text", ""))
        matches = list(WORD_RE.finditer(source))
        if not matches:
            continue
        x0 = float(word["x0"])
        x1 = float(word["x1"])
        top = float(word["top"])
        bottom = float(word["bottom"])
        span = max(len(source), 1)
        width = x1 - x0
        for match in matches:
            normalized = normalize_word(match.group(0))
            if not normalized:
                continue
            token_x0 = x0 + width * (match.start() / span)
            token_x1 = x0 + width * (match.end() / span)
            output.append(
                PdfToken(
                    text=match.group(0),
                    normalized=normalized,
                    box=(token_x0, top, token_x1 - token_x0, bottom - top),
                )
            )
    return output


def exact_starts(needle: list[str], haystack: list[str]) -> list[int]:
    if not needle or len(needle) > len(haystack):
        return []
    first = needle[0]
    size = len(needle)
    return [
        index
        for index, value in enumerate(haystack)
        if value == first and haystack[index : index + size] == needle
    ]


def map_page(
    items: list[tuple[str, list[Token]]],
    printed: list[PdfToken],
    page_width: float,
    page_height: float,
) -> tuple[dict[str, list[list[float] | None]], int, int]:
    boxes_by_token: dict[tuple[str, int], tuple[float, float, float, float]] = {}
    pdf_words = [token.normalized for token in printed]
    cursor = 0

    mappable_items = [
        (text_id, tokens)
        for text_id, tokens in items
        if not IMAGE_ID_RE.search(text_id) and not text_id.endswith("_page_number")
    ]

    # First take exact whole-segment matches. This prevents repeated common
    # words from drifting to unrelated lines elsewhere on a page.
    for text_id, tokens in mappable_items:
        wanted = [token.normalized for token in tokens]
        starts = exact_starts(wanted, pdf_words)
        if not starts:
            continue
        forward = [start for start in starts if start >= max(0, cursor - 3)]
        start = min(forward, key=lambda value: abs(value - cursor)) if forward else min(
            starts, key=lambda value: abs(value - cursor)
        )
        for offset, token in enumerate(tokens):
            boxes_by_token[(text_id, token.word_index)] = printed[start + offset].box
        cursor = start + len(tokens)

    # Align the remaining readable body text as one sequence. Inserted image
    # descriptions and the spoken page label are deliberately excluded because
    # they do not have printed word positions.
    flat_tokens = [token for _text_id, tokens in mappable_items for token in tokens]
    matcher = SequenceMatcher(
        None,
        [token.normalized for token in flat_tokens],
        pdf_words,
        autojunk=False,
    )
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            token = flat_tokens[block.a + offset]
            boxes_by_token.setdefault(
                (token.text_id, token.word_index), printed[block.b + offset].box
            )

    result: dict[str, list[list[float] | None]] = {}
    eligible = 0
    matched = 0
    for text_id, tokens in items:
        word_boxes: list[list[float] | None] = [None] * len(tokens)
        if not IMAGE_ID_RE.search(text_id) and not text_id.endswith("_page_number"):
            eligible += len(tokens)
        for token in tokens:
            box = boxes_by_token.get((text_id, token.word_index))
            if box is None:
                continue
            x, y, width, height = box
            word_boxes[token.word_index] = [
                round(x / page_width, 6),
                round(y / page_height, 6),
                round(width / page_width, 6),
                round(height / page_height, 6),
            ]
            matched += 1
        if any(box is not None for box in word_boxes):
            result[text_id] = word_boxes
    return result, matched, eligible


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    manifest = json.loads((root / "content/pages.json").read_text(encoding="utf-8"))
    output_dir = root / "content/word-boxes"
    output_dir.mkdir(parents=True, exist_ok=True)

    matched_total = 0
    eligible_total = 0
    with pdfplumber.open(args.pdf) as pdf:
        if len(pdf.pages) != len(manifest):
            raise ValueError(
                f"PDF has {len(pdf.pages)} pages but the reader has {len(manifest)} pages"
            )
        for source_page, (pdf_page, entry) in enumerate(zip(pdf.pages, manifest), start=1):
            page_path = root / entry["href"]
            items = transcript_items(page_path)
            printed = pdf_tokens(pdf_page)
            mappings, matched, eligible = map_page(
                items,
                printed,
                float(pdf_page.width),
                float(pdf_page.height),
            )
            matched_total += matched
            eligible_total += eligible
            payload = {
                "source_page": source_page,
                "printed_page": entry.get("page_number"),
                "page": {
                    "width": round(float(pdf_page.width), 4),
                    "height": round(float(pdf_page.height), 4),
                },
                "items": mappings,
            }
            (output_dir / f"pg{source_page:03d}.json").write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
                newline="\n",
            )

    coverage = matched_total / eligible_total if eligible_total else 1.0
    print(
        f"Mapped {matched_total:,} of {eligible_total:,} printed transcript words "
        f"({coverage:.1%}) across {len(manifest)} pages."
    )


if __name__ == "__main__":
    main()
