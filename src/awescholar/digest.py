"""Monthly digest — summarize the papers a curated archive holds for one month."""

import json
import os
from collections.abc import Callable

from . import __version__, prompts
from .pipeline import run_report

StatusCallback = Callable[[str], None] | None


def _noop(msg: str) -> None:
    pass


def _parse_record_year(value) -> tuple[int, int] | None:
    """Parse a record's 'year' field ('2026.05' or '2026.5') into (year, month)."""
    parts = str(value or "").strip().split(".")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    return None


def select_month_papers(archive: dict, year: int, month: int) -> dict[str, list[dict]]:
    """Archive entries whose 'year' matches the month, preserving category order."""
    selected: dict[str, list[dict]] = {}
    for category, papers in archive.items():
        if not isinstance(papers, list):
            continue
        kept = [
            p for p in papers
            if isinstance(p, dict) and _parse_record_year(p.get("year")) == (year, month)
        ]
        if kept:
            selected[category] = kept
    return selected


def _cell(value) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def render_month_digest(
    month_papers: dict[str, list[dict]], year: int, month: int, archive_total: int,
) -> str:
    """Structured digest without an LLM: stats line plus per-category tables."""
    count = sum(len(v) for v in month_papers.values())
    month_label = f"{year:04d}-{month:02d}"
    plural = "" if count == 1 else "s"
    lines = [
        f"# Monthly Research Digest — {month_label}",
        "",
        f"{count} paper{plural} across {len(month_papers)} categories (archive total: {archive_total}).",
        "",
    ]
    index = 0
    for category, papers in month_papers.items():
        lines += [
            f"## {category}",
            "",
            "| Index | Title | Domain | Venue | Team | DOI | Affiliation | Paper URL |",
            "|-------|-------|--------|-------|------|-----|-------------|------------|",
        ]
        for p in papers:
            index += 1
            url = p.get("paperUrl") or ""
            link = f"[Link]({_cell(url)})" if url else ""
            lines.append(
                f"| {index} | {_cell(p.get('title'))} | {_cell(p.get('domain'))} | "
                f"{_cell(p.get('venue'))} | {_cell(p.get('team'))} | {_cell(p.get('doi'))} | "
                f"{_cell(p.get('affiliation'))} | {link} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_digest(
    archive_path: str,
    year: int,
    month: int,
    model: str = "",
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.0,
    status_cb: StatusCallback = None,
) -> str:
    """Render the monthly digest markdown for one month of a curated archive.

    With a model and API key the digest gets an LLM narrative (same report shape
    as the crawler pipeline); without them it degrades to structured tables.
    """
    cb = status_cb or _noop
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    month_papers = select_month_papers(archive, year, month)
    month_label = f"{year:04d}-{month:02d}"
    if not month_papers:
        raise ValueError(
            f"no papers with year {year:04d}.{month:02d} in {archive_path} — "
            f"check --month or the records' year fields"
        )
    archive_total = sum(len(v) for v in archive.values() if isinstance(v, list))

    if model and api_key:
        cb(f"Generating {month_label} digest with {model.split('/')[-1]}...")
        return run_report(
            filtered_data=month_papers, model=model, date_range=month_label,
            api_key=api_key, base_url=base_url, temperature=temperature, status_cb=cb,
            system_prompt=prompts.DIGEST_REPORTER.replace("{month}", month_label),
        )

    cb(f"Rendering {month_label} digest offline (no model configured)...")
    body = render_month_digest(month_papers, year, month, archive_total)
    return f"<!-- awescholar {__version__} · digest (offline) · month: {month_label} -->\n\n{body}"


def write_digest(markdown: str, output_path: str) -> None:
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)
