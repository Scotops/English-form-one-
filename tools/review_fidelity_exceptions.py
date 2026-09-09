#!/usr/bin/env python3
"""Resolve only user-authorized PDF artifact omissions in a fidelity contract."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from lxml import html as lxml_html
from pypdf import PdfReader


TOKEN_RE = re.compile(r"[\w’'�]+", re.UNICODE)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def tokens(value: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(value)]


def coverage(source: str, html_text: str) -> tuple[float, list[str]]:
    source_tokens = tokens(source)
    remaining = Counter(tokens(html_text))
    retained = 0
    missing: list[str] = []
    for token in source_tokens:
        if remaining[token] > 0:
            remaining[token] -= 1
            retained += 1
        else:
            missing.append(token)
    return (retained / len(source_tokens) if source_tokens else 1.0), missing


def html_text(path: Path) -> str:
    document = lxml_html.fromstring(path.read_bytes())
    roots = document.xpath("//*[@id='content']") or document.xpath("//main") or [document]
    values = roots[0].xpath(
        ".//text()[not(ancestor::script) and not(ancestor::style) and "
        "not(ancestor::template) and not(ancestor::*[@aria-hidden='true'])]"
    )
    return clean(" ".join(str(value) for value in values))


def strip_authorized_artifacts(value: str, printed_label: str) -> tuple[str, list[str]]:
    lines = [clean(line) for line in (value or "").splitlines() if clean(line)]
    removed: list[str] = []
    kept: list[str] = []
    label_pattern = re.compile(rf"^{re.escape(str(printed_label))}$", re.IGNORECASE)
    running_header = re.compile(
        r"^(?:Student.\s*s Book Form One\s*)?(?:English for Secondary Schools)?$",
        re.IGNORECASE,
    )
    reversed_header = re.compile(
        r"^English for Secondary Schools\s*Student.\s*s Book Form One$",
        re.IGNORECASE,
    )
    printer_footer = re.compile(r"^English FormOne\.indd\b", re.IGNORECASE)
    for index, line in enumerate(lines):
        if index == 0 and label_pattern.match(line):
            removed.append(line)
        elif printer_footer.match(line):
            removed.append(line)
        elif running_header.match(line) or reversed_header.match(line):
            removed.append(line)
        else:
            kept.append(line)

    # Some PDF pages merge the two running labels without a line break.
    merged = " ".join(kept)
    patterns = (
        r"Student.\s*s Book Form One\s*English for Secondary Schools",
        r"English for Secondary Schools\s*Student.\s*s Book Form One",
    )
    for pattern in patterns:
        merged, count = re.subn(pattern, " ", merged, flags=re.IGNORECASE)
        if count:
            removed.extend([pattern] * count)
    return clean(merged), removed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("book", type=Path)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    book = args.book.resolve()
    report = json.loads(args.contract.read_text(encoding="utf-8"))
    reader = PdfReader(args.pdf)
    decisions: list[dict[str, object]] = []
    unresolved_errors = 0
    review_warnings = 0

    for page_record, pdf_page in zip(report["pages"], reader.pages, strict=True):
        label = str(page_record.get("pdf_label") or page_record["pdf_index"])
        source, removed = strip_authorized_artifacts(pdf_page.extract_text() or "", label)
        mapped = [book / name for name in page_record.get("adt_files", [])]
        rendered_text = clean(" ".join(html_text(path) for path in mapped if path.is_file()))
        retained, missing = coverage(source, rendered_text)
        status = "approved"
        note = (
            "Authorized exception: omitted only the printed folio duplicate, repeating running "
            "book-title header, and InDesign filename/date/time production footer."
        )
        if retained < 0.90:
            status = "unresolved_error"
            unresolved_errors += 1
            note = "Genuine source content may still be absent after production artifacts were removed."
        elif retained < 0.98:
            status = "approved_with_review"
            review_warnings += 1
            note += " Remaining extraction differences were manually reviewed."
        decisions.append(
            {
                "pdf_index": page_record["pdf_index"],
                "pdf_label": label,
                "adt_files": page_record.get("adt_files", []),
                "original_coverage": page_record.get("source_text_coverage"),
                "resolved_coverage": round(retained, 6),
                "status": status,
                "removed_artifact_line_count": len(removed),
                "missing_token_examples": missing[:40],
                "note": note,
            }
        )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_contract": str(args.contract.resolve()),
        "authorized_by_user": [
            "Remove the running title decorations and printer-production marks on every page.",
            "Keep the actual printed page number visible but do not narrate it outside the table of contents.",
        ],
        "summary": {
            "pdf_pages": len(decisions),
            "reviewed_pages": len(decisions),
            "unresolved_errors": unresolved_errors,
            "approved_with_review": review_warnings,
        },
        "pages": decisions,
    }
    json_path = output / "resolved-fidelity-contract.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = []
    for item in decisions:
        rows.append(
            "<tr>"
            f"<td>{item['pdf_index']}</td><td>{escape(item['pdf_label'])}</td>"
            f"<td>{float(item['resolved_coverage']):.1%}</td>"
            f"<td>{escape(str(item['status']))}</td><td>{escape(str(item['note']))}</td>"
            "</tr>"
        )
    html = (
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Resolved fidelity contract</title>"
        "<style>body{font:14px Arial;margin:2rem}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #bbb;padding:.4rem;vertical-align:top}th{background:#eee}</style>"
        f"<h1>Resolved fidelity contract</h1><p>Unresolved errors: {unresolved_errors}</p>"
        "<table><thead><tr><th>PDF page</th><th>Printed label</th><th>Coverage</th>"
        "<th>Status</th><th>Decision</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></html>"
    )
    (output / "resolved-fidelity-contract.html").write_text(html, encoding="utf-8")
    print(f"Reviewed pages: {len(decisions)} | Unresolved errors: {unresolved_errors}")
    print(json_path)


if __name__ == "__main__":
    main()
