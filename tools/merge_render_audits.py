#!/usr/bin/env python3
"""Merge bounded render-audit batches and require complete viewport coverage."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()

    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    pages: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    for report in reports:
        pages.extend(report.get("pages", []))
        findings.extend(report.get("findings", []))

    def viewport_name(page: dict[str, object]) -> str:
        viewport = page.get("viewport")
        if isinstance(viewport, dict):
            return "mobile" if int(viewport.get("width", 0)) <= 767 else "desktop"
        return str(viewport)

    keys = [(str(page.get("file")), viewport_name(page)) for page in pages]
    duplicates = sorted(key for key, count in Counter(keys).items() if count != 1)
    expected_files = ["index.html", *[f"pg{page:03d}_sec001.html" for page in range(2, 193)]]
    expected = {(file, viewport) for file in expected_files for viewport in ("desktop", "mobile")}
    actual = set(keys)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if duplicates or missing or unexpected:
        raise SystemExit(
            f"Incomplete render coverage: duplicates={len(duplicates)}, "
            f"missing={len(missing)}, unexpected={len(unexpected)}"
        )

    severity_counts = Counter(str(item.get("severity")) for item in findings)
    merged = {
        "schema_version": 2,
        "source_reports": [str(path) for path in args.reports],
        "summary": {
            "pages": 192,
            "rendered_views": len(pages),
            "findings": dict(severity_counts),
        },
        "findings": findings,
        "pages": sorted(
            pages,
            key=lambda item: (
                expected_files.index(str(item["file"])),
                viewport_name(item),
            ),
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(f"Merged render audit: {args.output.resolve()}")
    print(
        f"Pages: 192 | Rendered views: {len(pages)} | "
        f"Errors: {severity_counts.get('error', 0)} | "
        f"Warnings: {severity_counts.get('warning', 0)}"
    )
    if severity_counts.get("error", 0):
        raise SystemExit("Merged render audit contains errors.")


if __name__ == "__main__":
    main()
