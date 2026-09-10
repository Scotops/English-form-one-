#!/usr/bin/env python3
"""Compose the retained semantic ADT fragments into canonical PDF-page HTML."""

from __future__ import annotations

import argparse
import copy
import html as html_lib
import json
import re
from collections import defaultdict
from pathlib import Path

from lxml import etree
from lxml import html as lxml_html
from pypdf import PdfReader


TITLE = "English for Secondary Schools Student’s Book Form One"
ROMAN_PAGES = ("i", "ii", "iii", "iv", "v", "vi")
COVER_TITLE_ID = "pg001_cover_title"
COVER_TITLE_TEXT = "English for Secondary Schools. Student’s Book. Form One."
COVER_COMPONENT_IDS = {
    "pg001_n0002",
    "pg001_n0003",
    "pg001_n0005",
    "pg001_n0006",
}
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
TOC_PRINTED_VALUES = {
    "pg003_n0007": "v",
    "pg003_n0011": "vi",
    "pg003_n0016": "1",
    "pg003_n0021": "9",
    "pg003_n0026": "24",
    "pg003_n0031": "40",
    "pg003_n0036": "60",
    "pg003_n0041": "85",
    "pg003_n0046": "100",
    "pg003_n0051": "123",
    "pg004_n0005": "139",
    "pg004_n0009": "158",
    "pg004_n0012": "180",
    "pg004_n0015": "181",
    "pg004_n0019": "182",
}
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
ACKNOWLEDGEMENT_GROUPS = (
    (
        "pg005_credit_writers",
        ("pg005_n0010", "pg005_n0012"),
        "Writers: Ms Neema B. Matingo, Ms Asia M. Akaro, Mr Francis J. Kibadu, "
        "Dr Moshi M. Kimizi and Ms Mercy G. Mandia.",
    ),
    (
        "pg005_credit_editors",
        ("pg005_n0015", "pg005_n0017"),
        "Editors: Dr Emmanuel P. Lema, Dr Julius J. Taji, Dr Ponsiano S. Kanijo, "
        "Mr Richard S. Mabala and Mr Justin A. Msuya.",
    ),
    (
        "pg005_credit_designer",
        ("pg005_n0020", "pg005_n0022"),
        "Designer: Mr Frank P. Maridadi.",
    ),
    (
        "pg005_credit_illustrators",
        ("pg005_n0025", "pg005_n0027"),
        "Illustrators: Mr Yohana P. Mwenda and Mr Gwakisa M. Ulimboka.",
    ),
    (
        "pg005_credit_coordinator",
        ("pg005_n0030", "pg005_n0032"),
        "Coordinator: Ms Neema B. Matingo.",
    ),
)
RUNNING_TEXT = {
    "english for secondary schools",
    "student's book form one",
}
ACTIVITY_PATTERN = re.compile(
    r"\b(activity|exercise|task|questions?|answer|write|complete|match|fill|"
    r"discuss|read aloud|listen|role[- ]?play|practise|practice|choose|rewrite|"
    r"imagine|compose|construct|identify|pronounce)\b",
    re.IGNORECASE,
)
HEADING_PATTERN = re.compile(
    r"^(chapter\s+\w+|introduction|preface|acknowledgements|bibliography|"
    r"glossary|appendix|table of contents)$",
    re.IGNORECASE,
)
HEADING_ICON_CROPS = {
    "pg007_im003": "images/pg007_im003_icon.png",
    "pg015_im003": "images/pg015_im003_icon.png",
    "pg106_im003": "images/pg106_im003_icon.png",
    "pg087_im006_crop_v1": "images/pg087_im006_bar.png",
}
HEADING_STRIP_IDS = {"pg087_im006_crop_v1"}
IMAGE_SRC_OVERRIDES = {
    # The original composite repeats the live adverb paragraph. The companion
    # extraction retains the five children and their speech bubbles only.
    "pg087_im007": "images/pg087_im002.png",
}
SUBHEADING_PATTERN = re.compile(
    r"^(activity\s*\d*|exercise\s*\d*|task|questions?|think about)\b",
    re.IGNORECASE,
)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def element_text(element: etree._Element) -> str:
    return "".join(element.itertext())


def printed_page(source_page: int) -> str:
    return ROMAN_PAGES[source_page - 1] if source_page <= 6 else str(source_page - 6)


def is_prepress(value: str) -> bool:
    value = clean_text(value)
    return ".indd" in value.lower() or bool(
        re.fullmatch(r"\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}", value)
    )


def class_tokens(element: etree._Element) -> list[str]:
    return (element.get("class") or "").split()


def is_visually_exposed(element: etree._Element, boundary: etree._Element) -> bool:
    hidden_classes = {"hidden", "sr-only", "adt-visually-hidden", "adt-narration-only"}
    current: etree._Element | None = element
    while current is not None:
        if current.get("aria-hidden") == "true" or current.get("hidden") is not None:
            return False
        if hidden_classes.intersection(class_tokens(current)):
            return False
        if current is boundary:
            break
        current = current.getparent()
    return True


def has_visible_semantic_companion(image: etree._Element) -> bool:
    """Return true when nearby live HTML already renders the image's words."""
    image_id = image.get("data-id") or image.get("data-source-id") or ""
    boundary = image.getparent()
    for _ in range(4):
        if boundary is None:
            return False
        candidates = boundary.xpath(".//*[@data-id and not(self::img)]")
        for candidate in candidates:
            if candidate.get("data-id") != image_id and is_visually_exposed(candidate, boundary):
                return True
        boundary = boundary.getparent()
    return False


def image_words_are_repeated_in_parent(image: etree._Element, description: str) -> bool:
    """Detect a text-bearing template whose words already exist as live HTML.

    The retained source fragments sometimes use a raster panel as the visual
    background and place a complete semantic transcript directly over it.  In
    that case the raster must be suppressed so words are not displayed or
    narrated twice, while its box still reserves the source-derived geometry.
    """
    parent = image.getparent()
    if parent is None:
        return False
    description_tokens = set(re.findall(r"[a-z0-9]+", description.casefold()))
    if not description_tokens:
        return False
    matched_nodes = 0
    for candidate in parent.xpath(".//*[@data-id and not(self::img)]"):
        if not is_visually_exposed(candidate, parent):
            continue
        candidate_tokens = set(
            re.findall(r"[a-z0-9]+", clean_text(element_text(candidate)).casefold())
        )
        if not candidate_tokens:
            continue
        coverage = len(candidate_tokens & description_tokens) / len(candidate_tokens)
        if coverage >= 0.8:
            matched_nodes += 1
    return matched_nodes >= 2


def repeated_words_use_absolute_overlay(image: etree._Element, description: str) -> bool:
    """Return true when repeated live words are positioned over the image box."""
    parent = image.getparent()
    if parent is None:
        return False
    description_tokens = set(re.findall(r"[a-z0-9]+", description.casefold()))
    matched_absolute_nodes = 0
    for candidate in parent.xpath(".//*[@data-id and not(self::img)]"):
        candidate_tokens = set(
            re.findall(r"[a-z0-9]+", clean_text(element_text(candidate)).casefold())
        )
        if not candidate_tokens:
            continue
        coverage = len(candidate_tokens & description_tokens) / len(candidate_tokens)
        if coverage < 0.8:
            continue
        current: etree._Element | None = candidate
        uses_absolute_positioning = False
        while current is not None and current is not parent:
            if "absolute" in class_tokens(current):
                uses_absolute_positioning = True
                break
            current = current.getparent()
        if uses_absolute_positioning:
            matched_absolute_nodes += 1
    return matched_absolute_nodes >= 2


def set_class_tokens(element: etree._Element, tokens: list[str]) -> None:
    if tokens:
        element.set("class", " ".join(dict.fromkeys(tokens)))
    else:
        element.attrib.pop("class", None)


def remove_element(element: etree._Element) -> None:
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def narration_only(identifier: str, text: str) -> etree._Element:
    node = etree.Element("span")
    node.set("class", "adt-narration-only")
    node.set("data-id", identifier)
    node.text = text
    return node


def source_files_for_page(source_dir: Path, page: int) -> list[Path]:
    if page == 1:
        candidates = [source_dir / "index.html"]
        candidates.extend(sorted(source_dir.glob("pg001_sec*.html")))
        return [path for path in candidates if path.is_file()]
    return sorted(
        source_dir.glob(f"pg{page:03d}_sec*.html"),
        key=lambda path: int(re.search(r"_sec(\d+)", path.stem).group(1)),
    )


def mark_long_description(
    image: etree._Element,
    identifier: str,
    description: str,
    assessment_page: bool,
) -> None:
    description = clean_text(description)
    if not description:
        description = "Illustration supporting the surrounding textbook content."
    # Every textbook figure receives a concise alternative plus its complete
    # description through aria-describedby. The same data-id drives narration.
    if assessment_page or len(description) > 150 or description:
        concise = "Textbook illustration; a detailed description follows."
        lowered = description.lower()
        if any(word in lowered for word in ("table", "chart", "grid", "diagram")):
            concise = "Structured textbook figure; a detailed description follows."
        elif any(word in lowered for word in ("activity", "task", "question", "exercise")):
            concise = "Figure used in the textbook activity; instructions follow in detail."
        image.set("alt", concise)
        description_id = f"{identifier}-long-description"
        image.set("aria-describedby", description_id)
        long_description = etree.Element("span")
        long_description.set("id", description_id)
        long_description.set("class", "adt-visually-hidden adt-long-description")
        long_description.text = description
        image.addnext(long_description)
    else:
        image.set("alt", description)


def normalize_tables(root: etree._Element, page: int) -> None:
    for index, table in enumerate(root.xpath(".//table"), start=1):
        if not table.xpath("./caption"):
            caption = etree.Element("caption")
            caption.set("class", "adt-visually-hidden")
            caption.text = f"Table on printed page {printed_page(page)}"
            table.insert(0, caption)
        rows = table.xpath(".//tr")
        if rows and not table.xpath(".//th"):
            first_cells = rows[0].xpath("./td")
            for cell in first_cells:
                cell.tag = "th"
                cell.set("scope", "col")
        for header in table.xpath(".//th"):
            if not header.get("scope") and not header.get("headers"):
                header.set("scope", "col")
        table.set("data-table-index", str(index))


def promote_headings(root: etree._Element) -> None:
    for heading in root.xpath(".//h1"):
        heading.tag = "h2"
    for element in root.xpath(".//*[@data-id]"):
        if element.tag not in {"div", "span", "p"} or element.xpath(".//*[@data-id]"):
            continue
        value = clean_text(element_text(element))
        if HEADING_PATTERN.match(value):
            element.tag = "h2"
        elif SUBHEADING_PATTERN.match(value):
            element.tag = "h3"


def suppress_boundary_decoration(section: etree._Element, page: int) -> None:
    if page == 1:
        return
    for child in list(section):
        classes = " ".join(class_tokens(child)).lower()
        if "absolute" not in classes:
            continue
        at_boundary = any(
            token in classes
            for token in ("top-0", "bottom-0", "inset-y-0", "top-[", "bottom-[")
        )
        has_source_content = bool(child.xpath(".//*[@data-id or @data-source-id or self::img]"))
        has_image = bool(child.xpath(".//img"))
        if at_boundary and not has_source_content and not has_image and not clean_text(element_text(child)):
            remove_element(child)


def semantic_panel(
    root: etree._Element,
    identifiers: list[str],
    panel_class: str,
    child_classes: list[str],
) -> None:
    """Expose an existing hidden transcript as a styled live HTML panel."""
    nodes: list[etree._Element] = []
    for identifier in identifiers:
        matches = root.xpath(f'.//*[@data-id="{identifier}"]')
        if not matches:
            return
        nodes.append(matches[0])

    common_parent = nodes[0].getparent()
    if common_parent is not None and all(node.getparent() is common_parent for node in nodes):
        parent_classes = class_tokens(common_parent)
        parent_is_hidden_transcript = any(
            token in parent_classes
            for token in ("sr-only", "opacity-0", "h-px", "w-px", "pointer-events-none")
        ) or any(token.startswith("-left-") for token in parent_classes)
        if parent_is_hidden_transcript:
            common_parent.attrib.clear()
            common_parent.set("class", panel_class)
            for node, node_class in zip(nodes, child_classes):
                node.set("class", node_class)
            return

    first = nodes[0]
    parent = first.getparent()
    if parent is None:
        return
    position = parent.index(first)
    panel = etree.Element("div")
    panel.set("class", panel_class)
    parent.insert(position, panel)
    for node, node_class in zip(nodes, child_classes):
        node.set("class", node_class)
        panel.append(node)


def restore_hidden_semantic_panels(root: etree._Element, page: int) -> None:
    """Restore live headings that source fragments placed off-screen."""
    chapter_panels = {
        15: ("pg015_n0002", "pg015_n0003"),
        66: ("pg066_n0002", "pg066_n0003"),
        106: ("pg106_n0004", "pg106_n0005"),
    }
    if page in chapter_panels:
        semantic_panel(
            root,
            list(chapter_panels[page]),
            "adt-chapter-heading",
            ["adt-chapter-kicker", "adt-chapter-title"],
        )
    if page == 15:
        semantic_panel(
            root,
            ["pg015_n0020", "pg015_n0021"],
            "adt-activity-heading",
            ["adt-panel-label", "adt-panel-number"],
        )
    if page == 106:
        semantic_panel(
            root,
            ["pg106_n0017", "pg106_n0020", "pg106_n0022"],
            "adt-think-panel",
            ["adt-panel-label", "adt-panel-copy", "adt-panel-copy"],
        )
        semantic_panel(
            root,
            ["pg106_n0024", "pg106_n0025"],
            "adt-activity-heading",
            ["adt-panel-label", "adt-panel-copy"],
        )


def subtree_is_effectively_empty(node: etree._Element) -> bool:
    if node.get("data-id") or node.xpath(".//*[@data-id]") or node.xpath(".//img"):
        return False
    value = clean_text(element_text(node))
    return not value or bool(re.fullmatch(r"[ivxlcdm]+|\d+", value, re.IGNORECASE))


def is_effective_edge(
    node: etree._Element,
    boundary: etree._Element,
    from_start: bool,
) -> bool:
    current = node
    while current is not boundary:
        parent = current.getparent()
        if parent is None:
            return False
        siblings = list(parent)
        position = siblings.index(current)
        others = siblings[:position] if from_start else siblings[position + 1 :]
        if any(not subtree_is_effectively_empty(sibling) for sibling in others):
            return False
        current = parent
    return True


def suppress_running_decoration(wrappers: list[etree._Element], page: int) -> None:
    """Hide only repeated running-page artwork, retaining its page spacing.

    Earlier corrections explicitly removed the green/orange running bands,
    InDesign marks, and duplicate decorative folios.  A few generated source
    fragments express those bands as ordinary first/last blocks rather than
    absolute elements, so the older boundary cleaner did not catch them.
    """
    if page == 1:
        return
    sections = [section for wrapper in wrappers for section in wrapper.xpath("./section")]
    if not sections:
        return
    for section, from_start in ((sections[0], True), (sections[-1], False)):
        for child in section.iterdescendants():
            if not subtree_is_effectively_empty(child):
                continue
            if not is_effective_edge(child, section, from_start):
                continue
            classes = " ".join(class_tokens(child)).casefold()
            descendant_classes = " ".join(
                " ".join(class_tokens(node)).casefold() for node in child.iter()
            )
            style_signature = f"{classes} {descendant_classes}"
            looks_like_running_band = (
                "pointer-events-none" in style_signature
                or "bg-teal-500" in style_signature
                or "bg-orange-500" in style_signature
                or "from-teal" in style_signature
                or "to-teal" in style_signature
                or "via-orange" in style_signature
                or "bg-cyan" in style_signature
            )
            if not looks_like_running_band:
                continue
            # Preserve the source vertical rhythm but remove all visible and
            # spoken production artwork.  The canonical folio is added later.
            if child.tag == "img":
                remove_element(child)
                continue
            retained_classes = class_tokens(child)
            for nested in list(child):
                child.remove(nested)
            child.text = None
            child.attrib.clear()
            child.set(
                "class",
                " ".join([*retained_classes, "adt-running-decoration-removed"]),
            )
            child.set("aria-hidden", "true")


def clean_fragment(
    root: etree._Element,
    page: int,
    texts: dict[str, str],
    missing_descriptions: dict[str, str],
    question_transcripts: dict[str, str],
) -> None:
    assessment_page = bool(ACTIVITY_PATTERN.search(clean_text(element_text(root))))

    for element in list(root.xpath(".//*[@data-id]")):
        identifier = element.get("data-id") or ""
        inline = clean_text(element_text(element))
        mapped = clean_text(str(texts.get(identifier) or inline))
        normalized = clean_text(inline).replace("’", "'").lower()
        if is_prepress(inline) or (page > 1 and normalized in RUNNING_TEXT):
            remove_element(element)
            continue
        if element.tag != "img" and not re.search(r"[A-Za-z0-9]", mapped):
            element.attrib.pop("data-id", None)
            element.set("aria-hidden", "true")
            continue
        tokens = class_tokens(element)
        if "hidden" in tokens:
            tokens = [token for token in tokens if token != "hidden"]
            tokens.append("adt-narration-only")
            set_class_tokens(element, tokens)
        if identifier in TOC_PRINTED_VALUES and element.tag != "img":
            element.attrib.pop("data-id", None)
            element.set("aria-hidden", "true")
            element.text = TOC_PRINTED_VALUES[identifier]
            element.addnext(narration_only(identifier, TOC_PAGE_SPEECH[identifier]))
        elif identifier in COVER_COMPONENT_IDS:
            element.attrib.pop("data-id", None)
        elif page == 5 and any(identifier in components for _, components, _ in ACKNOWLEDGEMENT_GROUPS):
            element.attrib.pop("data-id", None)
        elif not mapped and element.tag != "img":
            texts[identifier] = inline

    if page == 1:
        first = root[0] if len(root) else None
        if first is not None:
            first.insert(0, narration_only(COVER_TITLE_ID, COVER_TITLE_TEXT))
        certificate = root.xpath('.//img[@data-id="pg001_im001"]')
        if certificate:
            certificate[0].attrib.pop("data-id", None)
            certificate[0].set("alt", "")
            certificate[0].set("role", "presentation")
            certificate[0].set("aria-hidden", "true")

    if page == 5:
        grids = root.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " grid ")]')
        host = grids[0] if grids else (root[0] if len(root) else root)
        for identifier, _components, spoken in reversed(ACKNOWLEDGEMENT_GROUPS):
            host.insert(0, narration_only(identifier, spoken))

    described_image_ids: set[str] = set()
    for image in list(root.xpath(".//img")):
        identifier = image.get("data-id") or image.get("data-source-id") or ""
        if identifier in TOC_DUPLICATE_IMAGE_IDS:
            image.attrib.pop("data-id", None)
            image.set("alt", "")
            image.set("role", "presentation")
            image.set("aria-hidden", "true")
            continue
        if not identifier:
            image.set("alt", image.get("alt") or "")
            if not image.get("alt"):
                image.set("role", "presentation")
                image.set("aria-hidden", "true")
            continue
        if identifier in described_image_ids:
            image.attrib.pop("data-id", None)
            image.attrib.pop("aria-describedby", None)
            image.set("alt", "")
            image.set("role", "presentation")
            image.set("aria-hidden", "true")
            continue
        described_image_ids.add(identifier)
        if identifier in IMAGE_SRC_OVERRIDES:
            image.set("src", IMAGE_SRC_OVERRIDES[identifier])
        description = clean_text(
            str(
                missing_descriptions.get(identifier)
                or texts.get(identifier)
                or image.get("alt")
                or ""
            )
        )
        if not description:
            description = missing_descriptions.get(
                identifier,
                "Illustration supporting the surrounding textbook content.",
            )
            texts[identifier] = description
        lowered_description = description.casefold()
        repeated_in_parent = image_words_are_repeated_in_parent(image, description)
        redundant_heading = (
            identifier in question_transcripts
            or lowered_description.startswith(
                (
                    "questions",
                    "activity",
                    "chapter",
                    "exercise",
                    "task heading",
                    "think about",
                )
            )
            or repeated_in_parent
        ) and has_visible_semantic_companion(image)
        if redundant_heading:
            image.set("data-source-id", identifier)
            image.attrib.pop("data-id", None)
            image.set("alt", "")
            image.set("role", "presentation")
            image.set("aria-hidden", "true")
            # A source `hidden` class may already have been converted to the
            # one-pixel narration helper.  Template images are decorative and
            # must keep either their natural box or no box at all, never the
            # helper's forced 1px by 1px geometry.
            classes = [
                token for token in class_tokens(image)
                if token != "adt-narration-only"
            ]
            if repeated_in_parent and repeated_words_use_absolute_overlay(image, description):
                # The complete semantic copy is already positioned over the
                # source template.  Keep the template's dimensions as a hidden
                # spacer so the live words remain in their exact source box.
                classes.append("adt-layout-template-spacer")
                parent = image.getparent()
                if parent is not None and "question" in lowered_description:
                    parent_classes = class_tokens(parent)
                    parent_classes.append("adt-semantic-question-shell")
                    set_class_tokens(parent, parent_classes)
            elif repeated_in_parent:
                # A normal-flow semantic replacement follows the obsolete
                # source template; collapse the template to avoid a blank box.
                classes.append("adt-layout-template-hidden")
            elif identifier in question_transcripts:
                classes.append("adt-layout-template-hidden")
                parent = image.getparent()
                if parent is not None:
                    parent_classes = class_tokens(parent)
                    parent_classes.append("adt-live-question-panel")
                    set_class_tokens(parent, parent_classes)
                    copy_node = etree.Element("p")
                    copy_node.set("class", "adt-live-question-copy")
                    copy_node.set("data-id", identifier)
                    copy_node.text = question_transcripts[identifier]
                    parent.append(copy_node)
                    texts[identifier] = question_transcripts[identifier]
                    texts[f"{identifier}_easy_read"] = question_transcripts[identifier]
            elif lowered_description.startswith(("exercise", "task heading", "think about")):
                if identifier in HEADING_ICON_CROPS:
                    image.set("src", HEADING_ICON_CROPS[identifier])
                classes.append(
                    "adt-heading-strip"
                    if identifier in HEADING_STRIP_IDS
                    else "adt-heading-icon-crop"
                )
            else:
                classes.append("adt-layout-template-hidden")
            image.set("class", " ".join(dict.fromkeys(classes)))
            continue
        mark_long_description(image, identifier, description, assessment_page)
        image.set("loading", "eager")
        style = image.get("style") or ""
        if "object-fit" not in style:
            image.set("style", (style.rstrip("; ") + "; object-fit: contain;").lstrip("; "))

    for section in root.xpath(".//section"):
        suppress_boundary_decoration(section, page)
        section_text = clean_text(element_text(section))
        if ACTIVITY_PATTERN.search(section_text):
            section.set("data-activity-id", section.get("data-section-id") or f"page-{page}")

    promote_headings(root)
    restore_hidden_semantic_panels(root, page)
    normalize_tables(root, page)

    seen: set[str] = set()
    for element in root.xpath(".//*[@data-id]"):
        identifier = element.get("data-id") or ""
        if identifier in seen:
            element.attrib.pop("data-id", None)
            element.set("aria-hidden", "true")
        else:
            seen.add(identifier)

    # The source conversion placed HTML transcripts of text-bearing figures in
    # display:none/aria-hidden containers. Keep them visually suppressed so the
    # printed layout is unchanged, but expose every unique data-id for read-aloud
    # and screen readers. Duplicate responsive copies were stripped just above.
    for container in root.xpath(".//*[@aria-hidden='true'][descendant::*[@data-id]]"):
        container.attrib.pop("aria-hidden", None)
        tokens = class_tokens(container)
        if "hidden" in tokens:
            tokens = ["adt-visually-hidden" if token == "hidden" else token for token in tokens]
            container.set("class", " ".join(tokens))


def fragment_wrapper(
    path: Path,
    page: int,
    texts: dict[str, str],
    missing: dict[str, str],
    question_transcripts: dict[str, str],
) -> etree._Element:
    document = lxml_html.fromstring(path.read_bytes())
    content = document.xpath('//*[@id="content"]')
    if not content:
        raise ValueError(f"No #content element in {path}")
    source_content = content[0]
    wrapper = etree.Element("div")
    outer_classes = [token for token in class_tokens(source_content) if token != "opacity-0"]
    wrapper.set("class", " ".join(["adt-source-fragment", *outer_classes]))
    wrapper.set("data-fragment-source", path.name)
    for child in source_content:
        wrapper.append(copy.deepcopy(child))
    clean_fragment(wrapper, page, texts, missing, question_transcripts)
    return wrapper


def bibliography_wrapper(texts: dict[str, str]) -> etree._Element:
    wrapper = etree.Element("div")
    wrapper.set("class", "adt-source-fragment adt-generated-bibliography")
    wrapper.set("data-fragment-source", "generated-from-pdf-text")
    section = etree.SubElement(wrapper, "section")
    section.set("data-section-type", "bibliography")
    section.set("data-section-id", "pg186_sec001")
    heading = etree.SubElement(section, "h2")
    heading.set("data-id", "pg186_n0003")
    heading.text = str(texts.get("pg186_n0003") or "Bibliography")
    entries = etree.SubElement(section, "ol")
    entries.set("class", "adt-bibliography-list")
    for number in range(4, 15):
        identifier = f"pg186_n{number:04d}"
        value = clean_text(str(texts.get(identifier) or ""))
        if not value:
            continue
        item = etree.SubElement(entries, "li")
        item.set("data-id", identifier)
        item.text = value
    return wrapper


def page_html(page: int, wrappers: list[etree._Element], width: float, height: float) -> str:
    folio = printed_page(page)
    section_id = f"pg{page:03d}_sec001"
    fragments = "\n".join(
        etree.tostring(wrapper, encoding="unicode", method="html") for wrapper in wrappers
    )
    activity_count = sum(len(wrapper.xpath('.//*[@data-activity-id]')) for wrapper in wrappers)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html_lib.escape(TITLE)} — printed page {html_lib.escape(folio)}</title>
  <meta name="title-id" content="{section_id}" />
  <meta name="page-section-id" content="{page}" />
  <meta name="printed-page-number" content="{html_lib.escape(folio)}" />
  <meta name="source-page-width-points" content="{width:.3f}" />
  <meta name="source-page-height-points" content="{height:.3f}" />
  <link href="./content/tailwind_output.css" rel="stylesheet" />
  <link href="./content/semantic-book.css?v=1" rel="stylesheet" />
  <link href="./assets/libs/fontawesome/css/all.min.css" rel="stylesheet" />
  <link href="./assets/fonts.css" rel="stylesheet" />
</head>
<body class="adt-semantic-reader">
  <main class="adt-reader-main" id="page-top">
    <div id="content" class="adt-book-page opacity-0" data-source-page="{page}" data-printed-page="{html_lib.escape(folio)}" style="--source-page-ratio:{width / height:.8f}">
      <h1 class="adt-visually-hidden">{html_lib.escape(TITLE)}, printed page {html_lib.escape(folio)}</h1>
      <div class="adt-page-canvas">
        <div class="adt-page-flow">
{fragments}
        </div>
        <span class="adt-printed-page-number" aria-hidden="true">{html_lib.escape(folio)}</span>
      </div>
    </div>
    <aside class="adt-exercise-workspace" id="adt-exercise-workspace" aria-label="Exercise response workspace" data-activity-count="{activity_count}">
      <button class="adt-workspace-toggle" type="button" aria-expanded="false" aria-controls="adt-workspace-panel">Exercise workspace</button>
      <div class="adt-workspace-panel" id="adt-workspace-panel" hidden>
        <label for="adt-activity-select">Choose an activity</label>
        <select id="adt-activity-select"></select>
        <label for="adt-activity-response">Your response</label>
        <textarea id="adt-activity-response" rows="8"></textarea>
        <div class="adt-workspace-actions">
          <button type="button" id="adt-response-save">Save response</button>
          <button type="button" id="adt-response-clear">Clear response</button>
        </div>
        <p class="adt-workspace-status" id="adt-workspace-status" role="status" aria-live="polite"></p>
      </div>
    </aside>
  </main>
  <div class="relative z-50" id="interface-container"></div>
  <div class="relative z-50" id="nav-container"></div>
  <script src="./assets/offline-preloader.js?v=8"></script>
  <script src="./assets/scorm.js"></script>
  <script src="./assets/facsimile-highlight.js?v=5"></script>
  <script src="./assets/semantic-layout.js?v=1"></script>
  <script src="./assets/adt-activities.js?v=1"></script>
  <script src="./assets/base.bundle.local.js"></script>
</body>
</html>
"""


def update_inline_json(root: Path) -> None:
    path = root / "assets/offline-preloader.js"
    source = path.read_text(encoding="utf-8")
    marker = "  var INLINE = "
    start = source.index(marker) + len(marker)
    end = source.index(";\n  var BASE_DIR", start)
    inline = json.loads(source[start:end])
    for key in list(inline):
        if key.startswith("./") and key.endswith(".json"):
            disk = root / key[2:]
            if disk.is_file():
                inline[key] = json.loads(disk.read_text(encoding="utf-8"))
    encoded = json.dumps(inline, ensure_ascii=False, separators=(",", ":"))
    path.write_text(source[:start] + encoded + source[end:], encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("book", type=Path)
    parser.add_argument("--source-fragments", type=Path)
    parser.add_argument("--descriptions", type=Path)
    parser.add_argument("--question-transcripts", type=Path)
    args = parser.parse_args()
    root = args.book.resolve()
    source_dir = (
        args.source_fragments.resolve()
        if args.source_fragments
        else (root / "content/source-fragments")
    )
    if not source_dir.is_dir():
        source_dir = root / "tmp/adt-book-builder/source-fragments"
    if not source_dir.is_dir():
        raise FileNotFoundError("The retained semantic source fragments were not found.")

    descriptions_path = args.descriptions or (root / "tools/image-description-overrides.json")
    missing_descriptions = (
        json.loads(descriptions_path.read_text(encoding="utf-8"))
        if descriptions_path.is_file()
        else {}
    )
    question_transcripts_path = args.question_transcripts or (root / "tools/question-transcripts.json")
    question_transcripts = (
        json.loads(question_transcripts_path.read_text(encoding="utf-8"))
        if question_transcripts_path.is_file()
        else {}
    )
    texts_path = root / "content/i18n/en/texts.json"
    audios_path = root / "content/i18n/en/audios.json"
    texts = json.loads(texts_path.read_text(encoding="utf-8"))
    audios = json.loads(audios_path.read_text(encoding="utf-8"))
    # A solitary punctuation extraction is neither visible nor narratable.
    texts.pop("pg181_n0027", None)
    audios.pop("pg181_n0027", None)
    # Preserve the useful easy-read word with its own valid audio target.
    audios["pg181_n0027_easy_read"] = "pg181_n0027_easy_read.mp3"
    reader = PdfReader(args.pdf)
    if len(reader.pages) != 192:
        raise ValueError(f"Expected 192 PDF pages, found {len(reader.pages)}")

    missing_pages: list[int] = []
    manifest: list[dict[str, object]] = []
    for page_number, pdf_page in enumerate(reader.pages, start=1):
        source_files = source_files_for_page(source_dir, page_number)
        if not source_files and page_number != 186:
            missing_pages.append(page_number)
            continue
        wrappers = (
            [bibliography_wrapper(texts)]
            if page_number == 186 and not source_files
            else [
                fragment_wrapper(
                    path,
                    page_number,
                    texts,
                    missing_descriptions,
                    question_transcripts,
                )
                for path in source_files
            ]
        )
        suppress_running_decoration(wrappers, page_number)
        box = pdf_page.mediabox
        width = float(box.width)
        height = float(box.height)
        section_id = f"pg{page_number:03d}_sec001"
        href = "index.html" if page_number == 1 else f"{section_id}.html"
        (root / href).write_text(
            page_html(page_number, wrappers, width, height),
            encoding="utf-8",
            newline="\n",
        )
        manifest.append(
            {
                "section_id": section_id,
                "href": href,
                "page_number": printed_page(page_number)
                if page_number <= 6
                else page_number - 6,
                "pdf_page": page_number,
            }
        )
    if missing_pages:
        raise RuntimeError(f"Missing source fragments for PDF pages: {missing_pages}")

    for identifier, spoken in TOC_PAGE_SPEECH.items():
        texts[identifier] = spoken
        texts[f"{identifier}_easy_read"] = spoken
    texts[COVER_TITLE_ID] = COVER_TITLE_TEXT
    texts[f"{COVER_TITLE_ID}_easy_read"] = COVER_TITLE_TEXT
    for identifier, _components, spoken in ACKNOWLEDGEMENT_GROUPS:
        texts[identifier] = spoken
        texts[f"{identifier}_easy_read"] = spoken

    missing_audio_jobs: dict[str, dict[str, str]] = {}
    for identifier, description in missing_descriptions.items():
        texts[identifier] = description
        texts[f"{identifier}_easy_read"] = description
        existing_file = root / "content/i18n/en/audio" / f"{identifier}.mp3"
        filename = f"{identifier}.mp3"
        audios[identifier] = filename
        audios[f"{identifier}_easy_read"] = filename
        if not existing_file.is_file() or existing_file.stat().st_size < 500:
            missing_audio_jobs[identifier] = {"text": description, "filename": filename}

    for identifier, transcript in question_transcripts.items():
        texts[identifier] = transcript
        texts[f"{identifier}_easy_read"] = transcript
        # These corrected transcripts are regenerated locally with the same
        # Microsoft David male voice as PCM WAV. Browsers support the format
        # directly, avoiding a lossy recode and any external speech service.
        filename = f"{identifier}.wav"
        audios[identifier] = filename
        audios[f"{identifier}_easy_read"] = filename

    used_ids: set[str] = set()
    for entry in manifest:
        document = lxml_html.fromstring((root / str(entry["href"])).read_bytes())
        used_ids.update(
            identifier
            for identifier in document.xpath('//*[@data-id]/@data-id')
            if identifier
        )
    audio_dir = root / "content/i18n/en/audio"
    for identifier in sorted(used_ids):
        existing_filename = str(audios.get(identifier) or f"{identifier}.mp3")
        existing_audio = audio_dir / existing_filename
        if (
            identifier in audios
            and existing_audio.is_file()
            and existing_audio.stat().st_size >= 500
        ):
            continue
        filename = existing_filename
        candidate = audio_dir / filename
        audios[identifier] = filename
        if f"{identifier}_easy_read" in texts:
            audios[f"{identifier}_easy_read"] = filename
        if not candidate.is_file() or candidate.stat().st_size < 500:
            missing_audio_jobs[identifier] = {
                "text": clean_text(str(texts.get(identifier) or "")),
                "filename": filename,
            }
    for identifier in list(audios):
        base_identifier = identifier.removesuffix("_easy_read")
        if (
            identifier.startswith("pg")
            and base_identifier not in used_ids
            and not re.search(r"[A-Za-z0-9]", str(texts.get(identifier) or ""))
            and not (audio_dir / str(audios[identifier])).is_file()
        ):
            audios.pop(identifier, None)

    texts_path.write_text(
        json.dumps(texts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    audios_path.write_text(
        json.dumps(audios, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "content/pages.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "tools/missing-image-audio-jobs.json").write_text(
        json.dumps(missing_audio_jobs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    update_inline_json(root)
    print(
        f"Built {len(manifest)} canonical semantic pages from "
        f"{sum(len(source_files_for_page(source_dir, page)) for page in range(1, 193)) + 1} fragments."
    )
    print(f"New narration jobs: {len(missing_audio_jobs)}")


if __name__ == "__main__":
    main()
