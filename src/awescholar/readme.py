"""README generation and update from project archive data."""

import glob
import json
import os
import re
import shutil
from datetime import datetime

from .categories import find_matching_category, normalize_category_name
from .data_fields import first_present, normalize_project_paper_fields
from .github import owner_repo_from_url

README_START_MARKER = "<!-- AWESCHOLAR:START -->"
README_END_MARKER = "<!-- AWESCHOLAR:END -->"


def discover_readme_targets(search_dir: str) -> list[str]:
    """Find README files in search_dir that contain AWESCHOLAR markers."""
    targets = []
    for pattern in ("README*.md", "readme*.md"):
        for path in glob.glob(os.path.join(search_dir, pattern)):
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                if README_START_MARKER in f.read():
                    targets.append(path)
    return sorted(set(targets))


def _escape_md(text: str) -> str:
    """Escape pipe characters for markdown tables."""
    if not text:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ")


def _format_anchor(category: str) -> str:
    return (
        str(category)
        .strip()
        .lower()
        .replace("&", "")
        .replace("/", "")
        .replace(" ", "-")
    )


def _canonical_archive_sections(archive: dict) -> dict:
    sections = {}
    for category, papers in archive.items():
        if not papers:
            continue
        target_category = find_matching_category(category, sections.keys()) or category
        sections.setdefault(target_category, [])
        for paper in papers:
            entry = normalize_project_paper_fields(paper)
            if "category" in entry:
                entry["category"] = target_category
            sections[target_category].append(entry)
    return sections


def _format_link(url: str) -> str:
    if not url:
        return ""
    if str(url).startswith("["):
        return str(url)
    return f"[Link]({url})"


def _stars_badge(code_url: str, github_stars) -> str:
    """Render the stars cell: numeric counts become a live badge derived
    from the repo URL; legacy entries store the badge image URL directly."""
    if github_stars in (None, ""):
        return ""
    value = str(github_stars)
    if value.startswith(("http://", "https://")):
        return f"![GitHub Stars]({value})"
    owner_repo = owner_repo_from_url(code_url)
    if not owner_repo:
        return ""
    return f"![GitHub Stars](https://img.shields.io/github/stars/{owner_repo})"


def _format_code_product(code_url: str, github_stars: str) -> str:
    parts = []
    if code_url:
        parts.append(_format_link(code_url))
    badge = _stars_badge(code_url, github_stars)
    if badge:
        parts.append(badge)
    return " ".join(parts)


def _parse_existing_sections(content: str) -> dict:
    """Parse existing section headers and their boundaries from content.

    Returns {normalized_name: original_header_line} for each ## section.
    """
    sections = {}
    for line in content.splitlines():
        if line.startswith("## "):
            key = normalize_category_name(line[3:].strip())
            if key:
                sections[key] = line
    return sections


def _parse_existing_toc(content: str) -> list:
    """Extract existing TOC lines from content (lines starting with '- [')."""
    toc = []
    in_toc = False
    for line in content.splitlines():
        if line.startswith("## "):
            if in_toc:
                break
            if "table of contents" in line.lower():
                in_toc = True
                continue
        elif in_toc and line.startswith("- ["):
            toc.append(line)
    return toc


def _split_sections(content: str) -> tuple:
    """Split content into (toc_block, section_blocks).

    Returns (toc_text, {normalized_name: section_text}).
    """
    lines = content.splitlines(keepends=True)
    toc_block = ""
    sections = {}
    current_key = None
    current_lines = []
    in_toc = False
    toc_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            header_text = stripped[3:].strip()
            if "table of contents" in header_text.lower():
                in_toc = True
                continue
            # Save previous section
            if current_key is not None:
                sections[current_key] = "".join(current_lines)
            elif in_toc:
                toc_block = "".join(toc_lines)
                in_toc = False
            current_key = normalize_category_name(header_text)
            current_lines = [line]
        elif in_toc:
            toc_lines.append(line)
        elif current_key is not None:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "".join(current_lines)
    if in_toc:
        toc_block = "".join(toc_lines)

    return toc_block, sections


def update_readme(
    archive_path: str,
    readme_path: str,
    project_title: str = "Awesome Scholar",
    project_description: str = "",
    website_url: str = "",
    github_repo: str = "",
    no_backup: bool = False,
):
    """Generate/update README.md tables from archive JSON.

    Preserves existing TOC entries and section headers (including emojis,
    custom names, custom anchors). Only updates table rows for existing
    categories and appends new categories at the end.
    """
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    archive = _canonical_archive_sections(archive)

    def _sort_year(p):
        # Pad unpadded months ("2025.3") so string sort matches chronological order
        y = str(p.get("year") or "")
        parts = y.split(".")
        if len(parts) == 2 and parts[1].isdigit():
            return f"{parts[0]}.{parts[1].zfill(2)}"
        return y

    def _make_table_rows(papers):
        """Generate only the table header + rows (no ## heading)."""
        sorted_papers = sorted(papers, key=_sort_year, reverse=True)
        lines = [
            "| Year | Title | Team | Team Website | Affiliation | Domain | Venue | Paper/ Source | Code/Product |",
            "| -----| ------| -----| -------------| ------------| -------| ------| --------------| -------------|",
        ]
        for p in sorted_papers:
            year = p.get("year") or p.get("publication_date", "")
            if isinstance(year, str) and len(year) >= 7:
                year = year[:7]
            title = _escape_md(p.get("title", ""))
            team = _escape_md(p.get("team", ""))
            team_website = _format_link(first_present(p, "team website", "team_website"))
            affiliation = _escape_md(p.get("affiliation", ""))
            domain = _escape_md(p.get("domain", ""))
            venue = _escape_md(p.get("venue", ""))
            doi = p.get("doi", "")
            paper_url = first_present(p, "paperUrl", "paper_url", "url")
            if not paper_url and doi:
                paper_url = f"https://doi.org/{doi}"
            paper_link = _format_link(paper_url)
            code_url = first_present(p, "codeUrl", "code_url")
            github_stars = first_present(p, "githubStars", "github_stars")
            code_link = _format_code_product(code_url, github_stars)
            lines.append(
                f"| {year} | **{title}** | {team} | {team_website} | {affiliation} | {domain} | {venue} | {paper_link} | {code_link} |"
            )
        return "\n".join(lines)

    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            existing_content = f.read()
        if README_START_MARKER not in existing_content or README_END_MARKER not in existing_content:
            raise RuntimeError(
                f"README update requires {README_START_MARKER} and {README_END_MARKER} markers."
            )
        before, rest = existing_content.split(README_START_MARKER, 1)
        inner, after = rest.split(README_END_MARKER, 1)

        _, existing_sections = _split_sections(inner)

        section_parts = []
        new_toc_entries = []

        for category, papers in archive.items():
            if not papers:
                continue
            norm = normalize_category_name(category)
            if norm in existing_sections:
                existing_block = existing_sections[norm]
                header_line = existing_block.splitlines()[0] if existing_block.splitlines() else f"## {category}"
                table_rows = _make_table_rows(papers)
                section_parts.append(f"{header_line}\n\n{table_rows}")
            else:
                table_rows = _make_table_rows(papers)
                section_parts.append(f"## {category}\n\n{table_rows}")
                anchor = _format_anchor(category)
                new_toc_entries.append(f"- [{category}](#{anchor})")

        generated_content = "\n\n".join(section_parts) + "\n"

        if new_toc_entries:
            before_lines = before.rstrip("\n").split("\n")
            last_toc_idx = -1
            for i, line in enumerate(before_lines):
                if line.strip().startswith("- ["):
                    last_toc_idx = i
            if last_toc_idx >= 0:
                for entry in reversed(new_toc_entries):
                    before_lines.insert(last_toc_idx + 1, entry)
                before = "\n".join(before_lines) + "\n"

        content = (
            f"{before}{README_START_MARKER}\n"
            f"{generated_content}"
            f"{README_END_MARKER}{after}"
        )
    else:
        toc_lines = []
        section_parts = []
        for category, papers in archive.items():
            if not papers:
                continue
            toc_lines.append(f"- [{category}](#{_format_anchor(category)})")
            table_rows = _make_table_rows(papers)
            section_parts.append(f"## {category}\n\n{table_rows}")

        toc_block = "\n".join(toc_lines)
        generated_content = "\n\n".join(section_parts) + "\n"

        parts = [f"# {project_title}"]
        if project_description:
            parts.append(f"\n{project_description}")
        parts.append("")
        if toc_lines:
            parts.append("## Table of Contents")
            parts.append(toc_block)
            parts.append("")
        parts.append(README_START_MARKER)
        parts.append(generated_content.rstrip())
        parts.append(README_END_MARKER)
        parts.append("")
        content = "\n".join(parts)

    if not no_backup and os.path.exists(readme_path):
        ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{readme_path}.{ts}.bak"
        try:
            shutil.copy2(readme_path, backup_path)
            print(f"Created backup: {backup_path}")
        except Exception as e:  # noqa: BLE001 — backup failure must not abort the README update
            print(f"Warning: Could not create backup of {readme_path}: {e}")

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)

    return readme_path


def update_readme_counts(archive_path: str, readme_path: str) -> str:
    """Refresh paper counts in a website-first README from the project data JSON.

    Updates the papers badge, the per-category counts on "Browse the Collection"
    bullets (both the short format and the description-bearing format), and the
    total-count sentences. Lines that do not match the known patterns are left
    untouched.
    """
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    slug_counts: dict[str, int] = {}
    for category, papers in archive.items():
        if isinstance(papers, list):
            slug = re.sub(r"[^a-z0-9]+", "-", str(category).lower()).strip("-")
            slug_counts[slug] = slug_counts.get(slug, 0) + len(papers)
    total = sum(slug_counts.values())
    n_categories = len([v for v in archive.values() if isinstance(v, list)])

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    # bullets like "- 🌟 [AI Agents](http://site/#ai-agents) — 12 papers" (or "篇", optional trailing text)
    def _bullet_repl(match: re.Match) -> str:
        slug = match.group("slug")
        if slug in slug_counts:
            count = slug_counts[slug]
        else:
            # README anchors carry the website's section id, which can be shorter
            # than the category-derived slug ("Databases/Simulation" -> "#databases").
            prefixes = [s for s in slug_counts if s.startswith(slug + "-")]
            if len(prefixes) != 1:
                return match.group(0)
            count = slug_counts[prefixes[0]]
        if "篇" in match.group("unit"):
            unit = " 篇"
        else:
            unit = " paper" if count == 1 else " papers"
        return f"{match.group('prefix')}{count}{unit}"

    content = re.sub(
        r"(?P<prefix>^\s*-\s+.*?\[[^\]]+\]\([^)#]+#(?P<slug>[a-z0-9-]+)\)\s+—\s+)"
        r"\d+(?P<unit>\s+(?:papers?\b|篇))",
        _bullet_repl,
        content,
        flags=re.MULTILINE,
    )
    # totals: "All 351 papers live on", "— 351 entries with full metadata", "全部 351 篇论文都在"
    content = re.sub(r"\bAll \d+ papers live on\b", f"All {total} papers live on", content)
    content = re.sub(r"— \d+ entries with full metadata", f"— {total} entries with full metadata", content)
    content = re.sub(r"全部 \d+ 篇论文都在", f"全部 {total} 篇论文都在", content)
    # badges: papers-N (optionally with %2B), categories-N
    content = re.sub(r"papers-\d+(?:%2B)?", f"papers-{total}", content)
    content = re.sub(r"categories-\d+", f"categories-{n_categories}", content)

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)

    return readme_path
