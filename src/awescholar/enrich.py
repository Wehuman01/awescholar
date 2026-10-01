"""Enrich archive entries with GitHub repository links and live star counts.

Two jobs, one command:
1. Papers without a codeUrl are matched to their official GitHub repository
   (arXiv-ID search first, title search second; heuristic scoring with an
   optional LLM tiebreak for ambiguous cases).
2. Papers with a github.com codeUrl get their githubStars refreshed as a
   numeric count (legacy badge-URL values are migrated along the way).

Only empty codeUrl fields are filled; entries never move between categories.
"""

import json
import re
from datetime import datetime

from pydantic import BaseModel

from .agentx.snapshot import merge_snapshot_agent, unique_slug, write_snapshot
from .agentx.transform import resolve_repo_status, resolve_retirement
from .backup import backup_file
from .github import (
    arxiv_id_from_paper,
    fetch_repo,
    owner_repo_from_url,
    repo_exists,
    resolve_repo_license,
    search_repositories,
    stars_from_repo,
)
from .llm import complete
from .utils import matches_only, since_filter

AUTO_ACCEPT_SCORE = 5
SCORE_MARGIN = 2
OWNER_MATCH_SCORE = 2
DESCRIPTION_SIMILARITY_SCORE = 3
# Academic repos often have an empty description and no arXiv citation, so the
# only officiality evidence is the name plus the community's verdict. A repo
# with the paper's system name and a decisive star lead over same-name rivals
# is the one the community already picked.
POPULARITY_MIN_STARS = 30
POPULARITY_STAR_RATIO = 5
# The description must restate the part of the title the repo/owner name
# cannot explain: enough rest tokens, most of them present.
DESCRIPTION_MIN_REST_TOKENS = 3
DESCRIPTION_SIMILARITY_THRESHOLD = 0.5

STOPWORDS = {
    "the", "for", "and", "with", "from", "using", "toward", "towards", "via",
    "based", "new", "study", "approach", "framework", "leveraging", "under",
}
# Repo names made only of these words match almost any paper; they must not
# earn the name-subset bonus on their own.
GENERIC_REPO_WORDS = {
    "agent", "agents", "llm", "paper", "papers", "code", "benchmark",
    "benchmarks", "model", "models", "toolkit", "library", "ai", "deep",
}
_CAMEL_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")
_BADGE_URL_RE = re.compile(r"img\.shields\.io/github/stars/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")


class RepoPick(BaseModel):
    """LLM verdict on which candidate is the paper's official repository."""
    repo: str = ""
    reason: str = ""


REPO_PICK_SYSTEM = (
    "You link scientific papers to their official code repositories. Given a "
    "paper and candidate GitHub repositories, pick the one repository that is "
    "the authors' official implementation. Third-party reimplementations, "
    "awesome lists, and repos that merely cite the paper do not count. The "
    "official repo is typically named after the paper's system and created "
    "around or after the paper; a candidate created or last pushed years "
    "before the paper is usually an unrelated older project that shares the "
    "name by coincidence. Reply "
    'with JSON: {"repo": "owner/name", "reason": "short justification"}. Use '
    "an empty repo string when none of the candidates is official."
)


def _repo_tokens(name: str) -> set[str]:
    """Camel/separator-split tokens plus the unsplit whole word, lowercased.

    Titles write system names as one word (BioAgent) while repos split them
    (bio-agent), and vice versa, so both forms are kept as evidence.
    """
    tokens = {m.group(0).lower() for m in _CAMEL_RE.finditer(name or "") if len(m.group(0)) >= 2}
    whole = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    if len(whole) >= 2:
        tokens.add(whole)
    return tokens


def _title_tokens(title: str) -> set[str]:
    """Significant title words, camel-split so compound names match repo names.

    Paper titles write system names as one word (BioAgent) while repos
    camelCase or hyphenate them (bio-agent), so both forms are kept.
    """
    tokens: set[str] = set()
    for word in re.findall(r"[A-Za-z]{3,}", title or ""):
        parts = [word.lower()] + [p.lower() for p in _CAMEL_RE.findall(word)]
        for part in parts:
            if len(part) >= 2 and part not in STOPWORDS:
                tokens.add(part)
    return tokens


def _score_candidate(title_tokens: set[str], arxiv_id: str, repo: dict,
                     arxiv_via_search: bool = False) -> int:
    """Heuristic evidence that a repo is the paper's official implementation.

    Core signal: the repo name derives from the title (official repos are
    named after the system the paper describes). Near-conclusive: the repo
    cites the paper's arXiv ID — directly, or by surfacing from the arXiv
    search (the index matched name, description, or README). Supporting:
    a dedicated owner (org named after the system) and a description that
    restates the paper title. No single signal clears the auto-accept bar —
    one corroborates another, and ambiguous races go to the LLM tiebreak.
    """
    distinctive = _repo_tokens(repo.get("name") or "") - GENERIC_REPO_WORDS
    description = str(repo.get("description") or "").lower()
    score = 0
    name_subset = bool(title_tokens and distinctive and distinctive <= title_tokens)
    if name_subset:
        score += 4
    elif distinctive & title_tokens:
        score += 1
    if arxiv_id and (arxiv_via_search
                     or arxiv_id.lower() in f"{repo.get('full_name') or ''} {description}".lower()):
        score += 4
    owner = _repo_tokens(str(repo.get("full_name") or "").split("/")[0]) - GENERIC_REPO_WORDS
    # Dedicated-org signal: every owner token is title-derived (an org named
    # after the system, MetaBeeAI), not a coincidental substring (ruby-grape).
    if owner and owner <= title_tokens:
        score += OWNER_MATCH_SCORE
    explained = distinctive | owner
    if title_tokens and _description_similarity(
            title_tokens, description, explained) >= DESCRIPTION_SIMILARITY_THRESHOLD:
        score += DESCRIPTION_SIMILARITY_SCORE
    topics = {t.lower() for t in repo.get("topics") or []}
    if distinctive & topics:
        score += 1
    repo["_name_subset"] = name_subset
    return score


def _description_similarity(title_tokens: set[str], description: str,
                            explained: set[str]) -> float:
    """How much of the title the description covers beyond the repo/owner name.

    Tokens already explained by the name are excluded, so echoing the repo
    name earns nothing — only title content the name cannot account for
    counts as the description restating the paper.
    """
    rest = title_tokens - explained
    if len(rest) < DESCRIPTION_MIN_REST_TOKENS:
        return 0.0
    words = set(re.findall(r"[a-z0-9]{2,}", description)) - STOPWORDS
    return len(rest & words) / len(rest)


def _popularity_accept(best: dict, ranked: list, paper_year: int | None) -> bool:
    """Exact system name plus a decisive star lead over every same-name rival.

    Catches real official repos whose bare description defeats description-
    based corroboration; the star gap substitutes for it. A repo whose age
    cannot be verified, or that was created years before the paper, is a
    name collision (an older tool sharing the system name) — both close
    this path.
    """
    if not best.get("_name_subset"):
        return False
    stars = int(best.get("stargazers_count") or 0)
    if stars < POPULARITY_MIN_STARS:
        return False
    created = str(best.get("created_at") or "")[:4]
    if paper_year is not None and (not created or int(created) < paper_year - 1):
        return False
    rival_stars = max((int(c.get("stargazers_count") or 0) for _, c in ranked[1:]), default=0)
    return stars >= POPULARITY_STAR_RATIO * max(rival_stars, 1)


def _auto_pick(title_tokens: set[str], arxiv_id: str, candidates: list[dict],
               paper_year: int | None = None) -> dict | None:
    """Return the clear heuristic winner, or None when the race is ambiguous."""
    ranked = sorted(
        ((_score_candidate(title_tokens, arxiv_id, c,
                           arxiv_via_search=c.get("_arxiv_via_search", False)), c)
         for c in candidates),
        key=lambda pair: -pair[0],
    )
    best_score, best = ranked[0]
    # A lone candidate whose repo name derives from the title is the official
    # repo in practice — but only when its age verifies: a creation date that
    # is present and no earlier than the paper's own window. Unverifiable age
    # (missing created_at or year) keeps the old corroboration bar, because a
    # name match alone is exactly how coincidental older tools slip through.
    if len(candidates) == 1 and best.get("_name_subset") and paper_year is not None:
        created = str(best.get("created_at") or "")[:4]
        if created and int(created) >= paper_year - 1:
            return best
    if best_score < AUTO_ACCEPT_SCORE:
        return best if _popularity_accept(best, ranked, paper_year) else None
    if len(ranked) > 1 and best_score - ranked[1][0] < SCORE_MARGIN:
        return best if _popularity_accept(best, ranked, paper_year) else None
    return best


def _llm_pick(paper: dict, candidates: list[dict], model: str,
              api_key: str | None, base_url: str | None,
              temperature: float = 0.0) -> dict | None:
    """Ask the configured LLM which candidate is official; None on no pick."""
    payload = {
        "paper": {
            "title": paper.get("title") or "",
            "team": paper.get("team") or "",
            "venue": paper.get("venue") or "",
            "year": paper.get("year") or "",
        },
        "candidates": [
            {
                "repo": c.get("full_name") or "",
                "stars": c.get("stargazers_count") or 0,
                "created": str(c.get("created_at") or "")[:10],
                "pushed": str(c.get("pushed_at") or "")[:10],
                "topics": c.get("topics") or [],
                "description": c.get("description") or "",
            }
            for c in candidates
        ],
    }
    try:
        pick = complete(
            model, REPO_PICK_SYSTEM, json.dumps(payload, ensure_ascii=False),
            response_format=RepoPick, api_key=api_key, base_url=base_url,
            temperature=temperature,
        )
    except Exception:  # noqa: BLE001 — one failed verdict must not abort the run
        return None
    wanted = (pick.repo or "").strip().lower()
    if not wanted:
        return None
    for c in candidates:
        if str(c.get("full_name") or "").lower() == wanted:
            return c
    return None


def _system_name(title: str) -> str:
    """The leading system name of a 'Name: description' title, or ''. Repos
    are named after the system, and GitHub's phrase search over the full
    title misses repos whose metadata only carries the name."""
    head = re.split(r"[:：—–]", str(title or ""), maxsplit=1)[0].strip()
    if 2 <= len(head) <= 40 and len(head.split()) <= 5:
        return head
    return ""


def _system_name_fallback(title: str) -> str:
    """First distinctive proper-noun token when the title has no ':' head.

    'NetMedGPT - A network medicine...' and 'MGM as a Large-Scale...' carry
    their system name as the opening token, not before a colon, so the
    colon-split round never fires for them. A token qualifies when it is
    ≥3 chars and contains a digit or an interior capital — the shape of
    system names (NetMedGPT, MGM, DualPG-DTA, h5adify) — and never when it
    is a plain capitalized word ('Predicting', 'Towards').
    """
    title = (title or "").strip()
    if not title:
        return ""
    first = re.split(r"\s+", title, maxsplit=1)[0].strip(",.;:()[]{}\"'")
    if len(first) < 3 or first.lower() in {"a", "an", "the", "this", "that"}:
        return ""
    has_digit = any(c.isdigit() for c in first)
    has_internal_cap = any(c.isupper() for c in first[1:])
    if not (has_digit or has_internal_cap):
        return ""
    return first[:40]


def resolve_repo(paper: dict, token: str | None, model: str = "",
                 api_key: str | None = None, base_url: str | None = None,
                 temperature: float = 0.0) -> dict | None:
    """Find the official GitHub repository for a paper, or None.

    Search rounds: arXiv ID (a hit there means the repo cites the ID in its
    name, description, or README), leading system name, full title. Clear
    heuristic winners are accepted directly; ambiguous races go to the LLM
    when one is configured. A round whose candidates all fail resolution
    falls through to the next round instead of ending the search.
    """
    arxiv_id = arxiv_id_from_paper(paper)
    title_tokens = _title_tokens(paper.get("title") or "")
    year = str(paper.get("year") or "")[:4]
    paper_year = int(year) if year.isdigit() else None
    queries = []
    if arxiv_id:
        fields = "name,description,readme" if token else "name,description"
        queries.append((f'"{arxiv_id}" in:{fields}', True))
    name = _system_name(paper.get("title") or "") \
        or _system_name_fallback(paper.get("title") or "")
    if name:
        queries.append((f'"{name}" in:name,description', False))
    if paper.get("title"):
        queries.append((f'"{paper["title"]}" in:name,description', False))

    for query, via_arxiv in queries:
        candidates = search_repositories(query, token)
        if via_arxiv:
            for c in candidates:
                c["_arxiv_via_search"] = True
        if not candidates:
            continue
        pick = _auto_pick(title_tokens, arxiv_id, candidates, paper_year)
        if pick is None and model and api_key:
            pick = _llm_pick(paper, candidates, model, api_key, base_url, temperature)
        if pick is not None:
            return pick
    return None


def _enrich_archive_shape(archive_path: str, *, token: str | None, model: str = "",
                          api_key: str | None = None, base_url: str | None = None,
                          temperature: float = 0.0,
                          use_llm: bool = True, limit: int | None = None,
                          no_backup: bool = False, status_cb=print,
                          only: list[str] | None = None,
                          since: str | None = None,
                          stars_style: str = "numeric") -> dict:
    """Fill empty codeUrl fields and refresh githubStars in place (awesome-list mode)."""
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    def _in_scope(p: dict) -> bool:
        return matches_only(p, only or []) and since_filter(p, since)

    # codeUrl -> [titles]: two papers on one official repo is the strongest
    # preprint-vs-published signal the archive carries (title rewrites defeat
    # text similarity; repos are not shared between unrelated papers).
    repo_owners: dict[str, list[str]] = {}
    for papers in archive.values():
        for p in papers:
            owner = owner_repo_from_url(str(p.get("codeUrl") or ""))
            if owner:
                repo_owners.setdefault(owner.lower(), []).append(str(p.get("title") or ""))

    # Legacy entries store a shields.io badge URL in githubStars; the repo it
    # renders is itself the missing codeUrl.
    for papers in archive.values():
        for p in papers:
            if not p.get("codeUrl") and _in_scope(p):
                badge = _BADGE_URL_RE.search(str(p.get("githubStars") or ""))
                if badge:
                    p["codeUrl"] = f"https://github.com/{badge.group(1)}"

    to_resolve = []  # (category, entry)
    to_refresh = []  # (category, entry)
    for category, papers in archive.items():
        for p in papers:
            if not p.get("codeUrl") and _in_scope(p):
                if p.get("title"):
                    to_resolve.append((category, p))
            elif owner_repo_from_url(p["codeUrl"]) and _in_scope(p):
                to_refresh.append((category, p))

    raw_to_resolve = to_resolve
    if limit is not None:
        to_resolve = to_resolve[:limit]

    scoped_total = len(raw_to_resolve) + len(to_refresh)
    scoped_note = f"Scoped to {scoped_total} entries (--only). " if only else ""
    llm_ready = use_llm and model and api_key
    status_cb(
        f"{scoped_note}Resolving repositories for {len(to_resolve)} papers, "
        f"refreshing metrics for {len(to_refresh)} linked repos"
        + ("" if llm_ready else " (LLM tiebreak off — only clear matches resolve)")
    )

    resolved = collisions = 0
    for i, (_, p) in enumerate(to_resolve, 1):
        repo = resolve_repo(p, token, model if llm_ready else "",
                            api_key if llm_ready else None, base_url,
                            temperature)
        if repo:
            p["codeUrl"] = repo.get("html_url") or f"https://github.com/{repo.get('full_name')}"
            if stars_style == "badge":
                owner_repo = owner_repo_from_url(p["codeUrl"])
                if owner_repo:
                    p["githubStars"] = f"https://img.shields.io/github/stars/{owner_repo}"
                else:
                    p["githubStars"] = stars_from_repo(repo)
            else:
                p["githubStars"] = stars_from_repo(repo)
            resolved += 1
            status_cb(f"  [{i}/{len(to_resolve)}] {repo.get('full_name')}  <-  "
                      f"{str(p.get('title'))[:60]}")
            owner = owner_repo_from_url(p["codeUrl"] or "")
            rivals = [t for t in repo_owners.get((owner or "").lower(), [])]
            if rivals:
                collisions += 1
                status_cb(f"  [!] Repo collision: '{str(p.get('title'))[:50]}' now shares "
                          f"{owner} with '{rivals[0][:50]}' — likely a preprint/published "
                          f"pair; check `updater dedupe` or drop the older entry.")
            repo_owners.setdefault((owner or "").lower(), []).append(str(p.get("title") or ""))
        elif i % 10 == 0 or i == len(to_resolve):
            status_cb(f"  [{i}/{len(to_resolve)}] unresolved: {str(p.get('title'))[:60]}")

    refreshed = missing = 0
    for _, p in to_refresh:
        owner_repo = owner_repo_from_url(p["codeUrl"])
        repo = fetch_repo(owner_repo, token)
        if repo:
            if stars_style == "badge":
                badge_url = f"https://img.shields.io/github/stars/{owner_repo}"
                existing = str(p.get("githubStars") or "")
                existing_match = _BADGE_URL_RE.search(existing)
                if existing_match and existing_match.group(1) == owner_repo:
                    pass  # already the same-repo badge; leave untouched
                else:
                    p["githubStars"] = badge_url
                    refreshed += 1
            else:
                p["githubStars"] = stars_from_repo(repo)
                refreshed += 1
        else:
            missing += 1
    if to_refresh:
        status_cb(f"Refreshed stars for {refreshed} repos"
                  + (f"; {missing} unreachable" if missing else ""))

    if not no_backup:
        backup_path = backup_file(archive_path)
        if backup_path:
            status_cb(f"Created backup: {backup_path}")

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)

    return {
        "resolve_candidates": len(to_resolve),
        "resolved": resolved,
        "repo_collisions": collisions,
        "refresh_candidates": len(to_refresh),
        "refreshed": refreshed,
        "missing_repos": missing,
    }


def _repo_field_updates(agent: dict, repo: dict) -> dict:
    """GitHub-derived fields for an AgentX agent entry; respects curated-first.

    License writes only when the SPDX id is a real identifier (NOASSERTION,
    null, and missing are skipped so a curated or previously fetched value
    stays untouched). Homepage is only filled for an explicit empty string —
    agentx snapshots use null for "deliberately no homepage", so curated
    silence is never clobbered by a generic GitHub project page. The repo's
    archived flag is persisted so agentx's lifecycle pass can mark
    owner-archived repos gone in the same run. Everything else
    (stars/pushedAt/openIssues/language/description) is overwritten — GitHub
    is the source of truth for live metrics.
    """
    updates: dict = {
        "stars": stars_from_repo(repo),
        "pushedAt": repo.get("pushed_at"),
        "openIssues": repo.get("open_issues_count", 0),
        "language": repo.get("language"),
        "description": repo.get("description"),
        "archived": bool(repo.get("archived")),
    }
    license_info = repo.get("license") or {}
    spdx = license_info.get("spdx_id")
    if spdx and spdx != "NOASSERTION":
        updates["license"] = spdx
    if agent.get("homepage") == "":
        repo_home = repo.get("homepage")
        if repo_home:
            updates["homepage"] = repo_home
    return updates


def _enrich_agentx_snapshot(archive_path: str, *, token: str | None,
                            no_backup: bool = False, status_cb=print) -> dict:
    """Refresh an AgentX `{agents, counts}` snapshot from GitHub in place.

    Two passes, matching the former `agentx snapshot` command end to end:
    the metrics pass refreshes the GitHub-derived field set on each agent
    (stars, pushedAt, openIssues, language, description, license, homepage
    when curated-empty, and the `archived` flag), then the lifecycle pass
    applies the registry's status policy — 404 → "gone" via a lightweight
    HEAD check, status derivation and retirement freezing for everything
    alive — and writes the file through agentx.snapshot.write_snapshot
    (slug-sorted, counts recomputed, no timestamp).
    """
    with open(archive_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    agents = snapshot.get("agents") if isinstance(snapshot, dict) else None
    if not isinstance(agents, list):
        raise ValueError(  # noqa: TRY004 — shape mismatch, not a builtin-type check
            f"{archive_path}: expected top-level {{agents, counts}} (AgentX snapshot), "
            "not a category-dict archive; pass --agentx on the CLI, or run "
            "awescholar updater enrich without --agentx for awesome-list archives.")

    # Pass 1: metrics refresh in memory.
    refreshed = missing = skipped = 0
    for agent in agents:
        repo_field = str(agent.get("repo") or "")
        if not repo_field:
            skipped += 1
            continue
        repo = fetch_repo(repo_field, token)
        if not repo:
            missing += 1
            continue
        for key, value in _repo_field_updates(agent, repo).items():
            agent[key] = value
        refreshed += 1

    # Pass 2: lifecycle policy — no-repo records pass through untouched, 404s
    # go to the graveyard, live repos get their status re-derived; retirement
    # freezes on first retirement and clears on recovery.
    out: list[dict] = []
    used_slugs: set[str] = set()
    seen_repos: set[str] = set()
    gone = 0
    for agent in agents:
        current_status = str(agent.get("status") or "")
        if current_status == "no-repo":
            slug = unique_slug(str(agent.get("slug") or "agent"), used_slugs)
            out.append(merge_snapshot_agent(
                agent, slug, None, current_status, agent.get("license")))
            continue
        repo_field = str(agent.get("repo") or "")
        repo_key = repo_field.lower()
        if repo_key in seen_repos:
            status_cb(f"  duplicate repo in snapshot skipped: {repo_field}")
            continue
        seen_repos.add(repo_key)
        slug = unique_slug(str(agent.get("slug") or "agent"), used_slugs)

        exists = repo_exists(repo_field, token)
        not_found = exists is False
        status = current_status
        if not_found:
            status = "gone"
            gone += 1
        elif exists:
            pushed_at = None
            if agent.get("pushedAt"):
                try:
                    pushed_at = datetime.fromisoformat(str(agent["pushedAt"]))
                except ValueError:
                    pushed_at = None
            paper_meta = agent.get("paperMeta") or {}
            status = resolve_repo_status(
                current_status=current_status,
                archived=bool(agent.get("archived")),
                stars=int(agent.get("stars") or 0),
                pushed_at=pushed_at,
                paper_venue=str(paper_meta.get("venue") or ""),
                auto_stable_exempt=bool(agent.get("autoStableExempt")),
            )

        retirement = resolve_retirement(
            current_status=current_status,
            next_status=status,
            archived=bool(agent.get("archived")),
            not_found=not_found,
            stars=int(agent.get("stars") or 0),
            retired_reason=agent.get("retiredReason"),
            retired_stars=agent.get("retiredStars"),
        )

        # NOASSERTION licenses skipped by pass 1 get the /license text
        # fallback here; existing SPDX values stay untouched.
        license_spdx = agent.get("license")
        if license_spdx is None and exists is not False:
            license_spdx = resolve_repo_license(
                repo_field, {"spdx_id": "NOASSERTION"}, token)

        merged = merge_snapshot_agent(agent, slug, None, status, license_spdx)
        merged["retiredReason"] = retirement.retired_reason
        merged["retiredStars"] = retirement.retired_stars
        out.append(merged)

    if not no_backup:
        backup_path = backup_file(archive_path)
        if backup_path:
            status_cb(f"Created backup: {backup_path}")

    write_snapshot(archive_path,
                   {"agents": out, "counts": {"total": len(out), "gone": gone}})

    return {"refreshed": refreshed, "missing_repos": missing,
            "skipped_no_repo": skipped, "gone": gone}


def enrich_archive(archive_path: str, token: str | None = None, *, mode: str = "archive",
                   model: str = "", api_key: str | None = None, base_url: str | None = None,
                   temperature: float = 0.0,
                   use_llm: bool = True, limit: int | None = None,
                   no_backup: bool = False, status_cb=print,
                   only: list[str] | None = None,
                   since: str | None = None,
                   stars_style: str = "numeric") -> dict:
    """Refresh an archive in place — dispatches on `mode`.

    - `mode="archive"` (default, awesome-list): fill empty `codeUrl` from
      GitHub search (LLM tiebreak on ambiguous matches) and overwrite
      `githubStars` to a bare int. Legacy badge-URL `githubStars` are
      migrated along the way.
    - `mode="agentx"` (AgentX snapshot): overwrite only the GitHub-derived
      field set on each agent; `status` and every other curated field are
      strictly preserved.
    """
    if mode == "archive":
        return _enrich_archive_shape(
            archive_path, token=token, model=model, api_key=api_key,
            base_url=base_url, temperature=temperature, use_llm=use_llm, limit=limit,
            no_backup=no_backup, status_cb=status_cb,
            only=only, since=since, stars_style=stars_style)
    if mode == "agentx":
        return _enrich_agentx_snapshot(
            archive_path, token=token, no_backup=no_backup, status_cb=status_cb)
    raise ValueError(f"unknown mode: {mode!r}")
