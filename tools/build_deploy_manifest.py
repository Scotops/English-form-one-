#!/usr/bin/env python3
"""Generate a SCORM manifest containing only the deployable semantic reader."""

from __future__ import annotations

import html
from pathlib import Path


ROOT_FILES = {
    ".nojekyll",
    "adlcp_rootv1p2.xsd",
    "cover.png",
    "imscp_rootv1p1p2.xsd",
    "imsmd_rootv1p2p1.xsd",
    "ims_xml.xsd",
}


def deployable(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    if path.name == "imsmanifest.xml":
        return False
    if path.parent == root:
        return path.name == "index.html" or path.name in ROOT_FILES or (
            path.suffix == ".html" and path.stem.startswith("pg")
        )
    if rel.startswith("assets/"):
        return not rel.endswith(".map")
    if rel.startswith("content/"):
        return True
    if rel.startswith("images/"):
        return not rel.startswith("images/pages/")
    return False


def main() -> None:
    root = Path.cwd().resolve()
    files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and deployable(path, root)
    )
    file_nodes = "\n".join(f'      <file href="{html.escape(name, quote=True)}"/>' for name in files)
    manifest = f'''<?xml version="1.0" encoding="UTF-8"?>
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
      <title>English for Secondary Schools Student’s Book Form One</title>
      <item identifier="ITEM_1" identifierref="RESOURCE_1">
        <title>English for Secondary Schools Student’s Book Form One</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RESOURCE_1" type="webcontent" adlcp:scormtype="sco" href="index.html">
{file_nodes}
    </resource>
  </resources>
</manifest>
'''
    (root / "imsmanifest.xml").write_text(manifest, encoding="utf-8", newline="\n")
    print(f"Deploy manifest files: {len(files)}")


if __name__ == "__main__":
    main()
