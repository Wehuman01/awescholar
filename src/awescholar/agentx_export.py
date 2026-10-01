"""Export archive papers with GitHub repos as AgentX candidate agents.

AgentX (the repo-first agent registry) consumes records shaped like its
data/agents-snapshot.json entries. This exporter turns paper-first archive
entries that carry a github.com codeUrl into that shape, so agentx can review
and ingest them without a paper-side re-format. Live repo metrics are fetched
when a token is available; otherwise the exporter falls back to what the
archive already knows and agentx's own refresh fills the rest.

Category validation is driven entirely by the agentx exclude snapshot when one
is passed: its agents' `category` values are the source of truth for known
slugs. With no snapshot there is no validation, since awescholar has no other
way to know agentx's categories.
"""

import json

from pydantic import BaseModel

from .agentx.snapshot import slugify
from .github import fetch_repo, owner_repo_from_url, stars_from_repo


def agentx_slugify(text: str) -> str:
    """The registry slugify, Unicode-aware like the former agentx-cli."""
    return slugify(text or "")


def _first_author(team: str) -> str:
    for separator in (",", ";", " and "):
        if separator in team:
            return team.split(separator)[0].strip()
    return team.strip()


# Words that mark a title prefix as a descriptive phrase, not a system name.
_NAME_STOPWORDS = frozenset([
    "a", "an", "the", "for", "with", "of", "and", "in", "using",
    "toward", "towards", "via", "by", "on", "to", "from"])


def _system_name(title: str) -> str | None:
    """Leading system name of a paper title: "MutexaGPT: an intuition-to-design
    translator..." -> "MutexaGPT". Name-shaped prefixes only — short, free of
    articles, connectors, and commas — so descriptive prefixes ("Bridging the
    Computational-Experimental Gap: ...") return None and the caller falls
    back to the repo name."""
    prefix = (title or "").split(":", 1)[0].strip() if title and ":" in title else ""
    words = prefix.split()
    if not words or len(words) > 4 or "," in prefix:
        return None
    if any(w.lower() in _NAME_STOPWORDS for w in words):
        return None
    return prefix


def _archive_stars(value) -> int:
    """Numeric star count from an archive field that may hold a legacy badge URL."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _paper_meta(paper: dict) -> dict:
    # The archive's full author list is authoritative when it was backfilled;
    # team (often just the first author) is the legacy fallback.
    authors = str(paper.get("authors") or paper.get("team") or "")
    return {
        "title": paper.get("title") or "",
        "venue": paper.get("venue") or "",
        "doi": paper.get("doi") or "",
        "year": paper.get("year") or "",
        "authors": authors,
        "firstAuthor": _first_author(authors),
        "paperUrl": paper.get("paperUrl") or "",
        "citations": paper.get("citations") or 0,
    }


def _paper_url(paper: dict) -> str | None:
    url = paper.get("paperUrl") or ""
    if url:
        return url
    doi = paper.get("doi") or ""
    return f"https://doi.org/{doi}" if doi else None


def _category_for(archive_category: str, category_map: dict,
                  default_category: str, known_categories: set[str],
                  status_cb) -> str:
    slug = category_map.get(archive_category) or category_map.get(
        archive_category.strip().lower())
    if not slug:
        return default_category
    if known_categories and slug not in known_categories:
        status_cb(f"  Warning: '{slug}' is not a category in the agentx snapshot "
                  f"(from '{archive_category}'); keeping it as-is")
    return slug


def _load_snapshot(path: str) -> tuple[set[str], set[str]]:
    """Load an agentx snapshot file: repo dedup set and known category slugs."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("agents", []) if isinstance(data, dict) else data
    repos = {str(a.get("repo") or "").lower() for a in entries if a.get("repo")}
    categories = {str(a["category"]) for a in entries if a.get("category")}
    return repos, categories


# --- LLM category pass -------------------------------------------------------

class _CategoryPick(BaseModel):
    repo: str
    category: str


class _CategoryPicks(BaseModel):
    picks: list[_CategoryPick]


_CATEGORY_SYSTEM = (
    "You classify AI-agent research tools into a fixed registry taxonomy. "
    "For each candidate repo pick exactly one allowed category slug, judged "
    "by what a user would open the repo for. Pick 'others' only when nothing "
    'fits. Answer with JSON: {"picks": [{"repo": "owner/name", "category": "slug"}]}.')


def _classify_categories(agents: list[dict], known_categories: set[str],
                         model: str, api_key: str | None, base_url: str | None,
                         temperature: float = 0.0,
                         status_cb=print, complete_fn=None) -> dict[str, str]:
    """LLM pick of an agentx category per candidate, as a repo->slug map.

    A pick is kept only when its slug is in the known set, so a hallucinated
    category can never reach the intake script. Slugs or repos the model
    leaves out are simply absent — the caller keeps the mapped default."""
    if complete_fn is None:
        from .llm import complete as complete_fn
    picks: dict[str, str] = {}
    allowed = ", ".join(sorted(known_categories))
    batch = 25
    for i in range(0, len(agents), batch):
        chunk = agents[i:i + batch]
        lines = "\n".join(
            f"- {a['repo']} :: {(a.get('paperMeta') or {}).get('title', '')}"
            f" :: {a.get('description') or ''}" for a in chunk)
        try:
            result = complete_fn(model=model, system=_CATEGORY_SYSTEM,
                                 user=f"Allowed category slugs: {allowed}\n"
                                      f"Candidates (repo :: paper title :: repo description):\n{lines}",
                                 response_format=_CategoryPicks,
                                 api_key=api_key, base_url=base_url,
                                 temperature=temperature)
        except Exception as exc:  # noqa: BLE001 - an LLM hiccup must not kill the export
            status_cb(f"  Warning: LLM category pass failed ({exc}); keeping defaults")
            return picks
        if isinstance(result, _CategoryPicks):
            for pick in result.picks:
                if pick.category in known_categories:
                    picks[pick.repo.lower()] = pick.category
    return picks


def export_agentx(archive_path: str, output_path: str, token: str | None = None,
                  category_map: dict | None = None, default_category: str = "platforms",
                  source: str = "awescholar", source_url: str | None = None,
                  categories: list[str] | None = None,
                  exclude_snapshot: str | None = None,
                  llm_model: str | None = None, llm_api_key: str | None = None,
                  llm_base_url: str | None = None, llm_temperature: float = 0.0,
                  classify_fn=None,
                  status_cb=print) -> dict:
    """Write an AgentX-shaped candidate file from papers with GitHub repos.

    The output is data, not commands: ingestion into a hub is the maintainer's
    `awescholar updater add --agentx --from-json <file>`, which re-validates
    and re-fetches live metrics — so this exporter hardcodes nothing about
    the intake command's invocation shape.

    With `llm_model` set (and a snapshot for the category list), each
    candidate's agentx category is picked by the configured model instead of
    relying on the static map + default fallback.
    """
    category_map = category_map or {}
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)
    if categories is not None:
        wanted = {c.strip().lower() for c in categories}
        dropped = [c for c in archive if c.strip().lower() not in wanted]
        for c in dropped:
            archive.pop(c)
        if dropped:
            status_cb(f"Scoped to {sorted(archive)}; skipped categories: {dropped}")
    exclude_repos = set()
    known_categories = set()
    if exclude_snapshot:
        exclude_repos, known_categories = _load_snapshot(exclude_snapshot)

    if known_categories and default_category not in known_categories:
        status_cb(f"  Warning: '{default_category}' is not a category in the agentx "
                  f"snapshot; using it as the default fallback")

    agents = []
    used_slugs: set[str] = set()
    seen_repos: set[str] = set()
    skipped_no_repo = deduped_repos = excluded_snapshot = 0

    for archive_category, papers in archive.items():
        category = _category_for(archive_category, category_map, default_category,
                                 known_categories, status_cb)
        for p in papers:
            owner_repo = owner_repo_from_url(str(p.get("codeUrl") or ""))
            if not owner_repo:
                skipped_no_repo += 1
                continue
            if owner_repo.lower() in exclude_repos:
                excluded_snapshot += 1
                continue
            if owner_repo.lower() in seen_repos:
                deduped_repos += 1
                continue
            seen_repos.add(owner_repo.lower())

            repo = fetch_repo(owner_repo, token) if token else None
            # The paper's system name ("MutexaGPT", from the title) is the
            # display name agents are known by; the repo segment is a fallback.
            name = (_system_name(str(p.get("title") or ""))
                    or (repo or {}).get("name") or owner_repo.split("/")[1])
            slug = agentx_slugify(name)
            while slug in used_slugs:
                slug = f"{slug}-2"
            used_slugs.add(slug)

            license_info = (repo or {}).get("license") or {}
            license_id = license_info.get("spdx_id")
            agents.append({
                "slug": slug,
                "name": name,
                "repo": owner_repo,
                "githubUrl": f"https://github.com/{owner_repo}",
                "homepage": p.get("team website") or (repo or {}).get("homepage"),
                "paper": _paper_url(p),
                "paperMeta": _paper_meta(p),
                "category": category,
                "tags": [],
                "language": (repo or {}).get("language"),
                "stars": stars_from_repo(repo) if repo else _archive_stars(p.get("githubStars")),
                "pushedAt": (repo or {}).get("pushed_at"),
                "openIssues": (repo or {}).get("open_issues_count", 0),
                "license": license_id if license_id not in (None, "NOASSERTION") else None,
                "description": (repo or {}).get("description"),
                "status": "active",
                "source": source,
                "sourceUrl": source_url,
            })

    if llm_model and known_categories and agents:
        picks = (classify_fn or _classify_categories)(
            agents, known_categories, llm_model, llm_api_key, llm_base_url,
            temperature=llm_temperature, status_cb=status_cb)
        applied = 0
        for a in agents:
            slug = picks.get(a["repo"].lower())
            if slug:
                a["category"] = slug
                applied += 1
        status_cb(f"  LLM category pass classified {applied}/{len(agents)} candidates "
                  "(the rest keep the mapped/default category)")
    elif llm_model:
        status_cb("  Warning: --llm-category needs --exclude-snapshot for the "
                  "category list; keeping mapped/default categories")

    with open(output_path, "w", encoding="utf-8") as f:
        # agentx SnapshotFile counts contract is {total, gone}.
        json.dump({"agents": agents, "counts": {"total": len(agents), "gone": 0}},
                  f, indent=2, ensure_ascii=False)
        f.write("\n")

    status_cb(f"Exported {len(agents)} agent candidates to {output_path} "
              f"({skipped_no_repo} papers without a GitHub repo skipped, "
              f"{deduped_repos} duplicate repos collapsed"
              + (f", {excluded_snapshot} repos already in the exclude snapshot"
                 if excluded_snapshot else "") + ")")
    return {"exported": len(agents), "skipped_no_repo": skipped_no_repo,
            "deduped_repos": deduped_repos, "excluded_snapshot": excluded_snapshot}
