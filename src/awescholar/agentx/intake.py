"""Intake new agent records into the AgentX snapshot.

Single source of truth for registry writes:
- ``add_agent`` adds one validated record.
- ``add_from_json`` batch-intakes a candidate file (snapshot-shaped
  ``{"agents": [...]}`` or a bare record array).  The file is data, not
  decisions: categories and tags are re-checked here, metrics are re-fetched
  live, and already-registered repos are skipped.  The whole batch is
  all-or-nothing — nothing is written unless every new record passes.

Caller owns the GitHub token; one request per new record.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from awescholar.agentx.policy import (
    CATEGORIES,
    find_tag_policy_violations,
    tag_type,
    venue_tag_for,
)
from awescholar.agentx.snapshot import (
    _coalesce,
    read_snapshot,
    slugify,
    unique_slug,
    write_snapshot,
)
from awescholar.agentx.transform import normalize_homepage, resolve_repo_status
from awescholar.github import fetch_repo_ex, resolve_repo_license


class IntakeError(Exception):
    """A candidate record failed registry rules; message is user-facing."""


# ---------------------------------------------------------------------------
# Single-record path
# ---------------------------------------------------------------------------

def add_agent(
    snapshot_file: str,
    repo: str,
    *,
    category: str | None = None,
    name: str | None = None,
    tags: list[str] | None = None,
    paper: str | None = None,
    homepage: str | None = None,
    description: str | None = None,
    token: str | None = None,
    status_cb=print,
) -> dict:
    """Add one validated agent to *snapshot_file*.

    Returns the newly-built agent dict on success.
    """
    tags = tags or []
    record = {
        "repo": repo,
        "category": category,
        "name": name,
        "tags": tags,
        "paper": paper,
        "homepage": homepage,
        "description": description,
        "source": "manual",
        "sourceUrl": None,
    }

    snapshot = read_snapshot(snapshot_file)
    if snapshot["agents"] and any(
        a["repo"].lower() == repo.lower() for a in snapshot["agents"]
    ):
        raise IntakeError(f"{repo} is already in the snapshot.")

    used_slugs = {a["slug"] for a in snapshot["agents"]}
    agent = _agent_from_intake(record, used_slugs, token)

    snapshot["agents"].append(agent)
    write_snapshot(snapshot_file, snapshot)

    tag_part = f", tags: {', '.join(agent['tags'])}" if agent["tags"] else ""
    status_cb(f"Added {agent['slug']} ({agent['repo']}) → category {agent['category']}{tag_part}")
    return agent


# ---------------------------------------------------------------------------
# Batch JSON path
# ---------------------------------------------------------------------------

def add_from_json(
    snapshot_file: str,
    intake_path: str,
    *,
    token: str | None = None,
    status_cb=print,
) -> int:
    """Batch-intake candidates from *intake_path* into *snapshot_file*.

    Returns the number of agents written.
    """
    with open(intake_path, encoding="utf-8") as f:
        raw_json = f.read()

    # --- parse & shape-check ---------------------------------------------------
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as err:
        raise IntakeError(f"{intake_path} is not valid JSON: {err}") from err

    if isinstance(parsed, list):
        records = parsed
    elif isinstance(parsed, dict) and isinstance(parsed.get("agents"), list):
        records = parsed["agents"]
    else:
        raise IntakeError(
            f'{intake_path}: expected {{"agents": [...]}} or a top-level record array.'
        )

    if not records:
        raise IntakeError(f"{intake_path} contains no candidate agents.")

    candidates = [
        r for r in records
        if isinstance(r, dict) and isinstance(r.get("repo"), str)
    ]

    # --- load snapshot & skip already-registered -------------------------------
    snapshot = read_snapshot(snapshot_file)
    registered = {a["repo"].lower() for a in snapshot["agents"]}

    fresh: list[dict[str, Any]] = []
    for rec in candidates:
        if rec["repo"].lower() in registered:
            status_cb(f"{rec['repo']} already in the snapshot, skipped")
        else:
            fresh.append(rec)

    if not fresh:
        status_cb(
            f"Nothing new in {intake_path}: all {len(candidates)} candidate "
            f"repos are already registered."
        )
        return 0

    # --- all-or-nothing: build every record before the first write -------------
    used_slugs = {a["slug"] for a in snapshot["agents"]}
    added: list[dict[str, Any]] = []
    for rec in fresh:
        added.append(_agent_from_intake(rec, used_slugs, token))

    snapshot["agents"].extend(added)
    write_snapshot(snapshot_file, snapshot)

    status_cb(f"Added {len(added)} agent{'s' if len(added) != 1 else ''} from {intake_path}:")
    for agent in added:
        status_cb(f"  {agent['slug']} ({agent['repo']}) → category {agent['category']}")

    skipped = len(candidates) - len(added)
    if skipped:
        status_cb(f"Skipped {skipped} already-registered repo{'s' if skipped != 1 else ''}.")

    return len(added)


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------

def _agent_from_intake(
    rec: dict[str, Any],
    used_slugs: set[str],
    token: str | None,
) -> dict[str, Any]:
    """Validate one intake record and build a SnapshotAgent from live GitHub data."""
    repo = rec["repo"]

    # --- repo format -----------------------------------------------------------
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo):
        raise IntakeError(f"Not an owner/repo pair: {repo}")

    # --- category --------------------------------------------------------------
    category = rec.get("category") or ""
    if category not in CATEGORIES:
        raise IntakeError(
            f'Unknown category "{category}" for {repo}. Valid slugs: '
            f'{", ".join(CATEGORIES)}'
        )

    # --- tags ------------------------------------------------------------------
    tags: list[str] = rec.get("tags") or []
    tag_problems = find_tag_policy_violations(tags)
    if tag_problems:
        lines = "\n".join(f"  - {p}" for p in tag_problems)
        raise IntakeError(
            f"Tag policy violations for {repo} (tags are objective proper-noun "
            f"attributions only):\n{lines}"
        )

    # The record's own venue tag — registered canonical or auto-generated
    # slug — is the one unregistered tag intake accepts.
    auto_venue_tag = venue_tag_for(
        str((rec.get("paperMeta") or {}).get("venue") or "")
    )
    unregistered = [t for t in tags if tag_type(t) is None and t != auto_venue_tag]
    if unregistered:
        raise IntakeError(
            f"Unregistered tags on {repo}: {', '.join(unregistered)}. "
            f"Add them to TAG_TYPE in agentx/policy.py first; a venue tag "
            f"may also be the auto slug of the record's own venue."
        )

    # --- live GitHub fetch -----------------------------------------------------
    gh, not_found = fetch_repo_ex(repo, token)
    if not_found:
        raise IntakeError(f"{repo} not found on GitHub (404).")
    if gh is None:
        raise IntakeError(
            f"Could not fetch {repo} (network or rate limit). "
            f"Retry, or set GITHUB_TOKEN."
        )

    # --- name ------------------------------------------------------------------
    name = rec.get("name") or repo.split("/")[1]

    # --- metrics ---------------------------------------------------------------
    pushed_at_str = gh.get("pushed_at")
    pushed_at_dt: datetime | None = None
    if pushed_at_str:
        try:
            pushed_at_dt = datetime.fromisoformat(pushed_at_str)
        except ValueError:
            pushed_at_dt = None

    status = resolve_repo_status(
        current_status="active",
        archived=gh.get("archived", False),
        stars=gh.get("stargazers_count") or 0,
        pushed_at=pushed_at_dt,
    )

    # --- build dict in TS field order ------------------------------------------
    slug = unique_slug(slugify(name), used_slugs)
    homepage_rec = normalize_homepage(rec.get("homepage"))
    homepage_gh = normalize_homepage(gh.get("homepage"))

    agent: dict[str, Any] = {
        "slug": slug,
        "name": name,
        "repo": gh["full_name"],
        "githubUrl": f"https://github.com/{gh['full_name']}",
        "homepage": _coalesce(homepage_rec, homepage_gh),
        "paper": rec.get("paper") or None,
        "category": category,
        "tags": tags,
        "language": _coalesce(gh.get("language"), None),
        "stars": _coalesce(gh.get("stargazers_count"), 0),
        "pushedAt": pushed_at_str,
        "openIssues": _coalesce(gh.get("open_issues_count"), 0),
        "license": resolve_repo_license(repo, gh.get("license"), token),
        "description": _coalesce(rec.get("description"), gh.get("description")),
        "status": status,
        "source": _coalesce(rec.get("source"), "manual"),
        "sourceUrl": rec.get("sourceUrl") or None,
        # Curation date (date-only, UTC): when the curator listed the agent.
        # Stamped once at intake, never refreshed — enrich carries it along
        # untouched. The website parses the bare date as UTC midnight, so the
        # stamp and the badge window share one clock.
        "listedAt": datetime.now(tz=UTC).date().isoformat(),
    }
    return agent
