"""Offline validation for data/agents-snapshot.json — the mechanical backstop
for "the snapshot is never hand-edited". Every writer (intake, the refresh,
the enrichment passes) maintains these invariants; `verify --agentx` runs
this so a bad merge or a manual edit fails loudly instead of drifting into
the published site.

Pure on purpose: no fs, no network, no DB — unit-testable and safe in any
environment.
"""

import json
import re
from datetime import datetime

from .policy import CATEGORIES, find_tag_policy_violations, registered_venue_tag, tag_type

# resolve_repo_status (transform) can emit every status below; "no-repo"
# only ever enters through a writer, but it is protected there, so it stays
# a legal stored value. Tuple, not set: the problem message joins these in
# this order (TypeScript Sets keep insertion order; Python sets do not).
VALID_STATUSES = ("active", "stale", "stable", "archived", "gone", "no-repo")

# githubUrl is either null — no-repo records carry an external identity in
# repo ("anthropic.com/claude-science"), which is string-indistinguishable
# from a dotted GitHub owner — or the canonical URL built from repo. Writers
# never produce anything else. Underscore is grandfathered in slugs: the
# legacy slugify kept it, and one such slug (paper_claw-pigeondan1) predates
# the current writer.
RETIRED_REASONS = frozenset({"idle", "owner-archived", "not-found"})

HTTP_URL = re.compile(r"^https?://\S+$")


def _is_int(value) -> bool:
    """JSON integer. Bools are ints in Python but not numbers in TS/JSON."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_http_url(value) -> bool:
    return isinstance(value, str) and HTTP_URL.fullmatch(value) is not None


def _slug_shaped(slug: str) -> bool:
    """Stand-in for `^[\\p{L}\\p{N}_]+(-[\\p{L}\\p{N}_]+)*$` (stdlib `re` has
    no `\\p{}`): dash-separated segments of letters/digits/underscores."""
    return all(
        seg and all(ch.isalnum() or ch == "_" for ch in seg) for seg in slug.split("-")
    )


def _iso_parseable(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_snapshot_file(file: object) -> list[str]:
    """All problems found, as human-readable lines; empty means the file is valid."""
    problems: list[str] = []

    if not isinstance(file, dict):
        return ["top level is not an object"]
    agents = file.get("agents")
    if not isinstance(agents, list):
        return ["agents is not an array"]
    counts = file.get("counts")
    if not isinstance(counts, dict):
        return ["counts is not an object"]

    # counts.gone counts the 404s of the last refresh run, NOT the agents
    # currently in status "gone" (owner-archived repos flip status without
    # being 404s), so only total is strictly derivable from the agents list.
    total = counts.get("total")
    gone = counts.get("gone")
    if total != len(agents):
        problems.append(f"counts.total is {total}, but agents has {len(agents)} entries")
    if not _is_int(gone) or gone < 0 or gone > len(agents):
        problems.append(f"counts.gone is {gone} — expected an integer in [0, {len(agents)}]")

    # Version clock stamped by write_snapshot on every real write; absent on
    # files older than the stamping itself. Never fabricated here.
    stamp = file.get("generatedAt")
    if stamp is not None and (not isinstance(stamp, str) or not _iso_parseable(stamp)):
        problems.append(f"generatedAt is {stamp!r} — expected an ISO-8601 timestamp")

    def where(i: int, slug) -> str:
        if isinstance(slug, str) and slug:
            return f"agents[{i}] ({slug})"
        return f"agents[{i}]"

    seen_slugs: dict[str, int] = {}
    seen_repos: dict[str, int] = {}

    for i, agent in enumerate(agents):
        spot = where(i, agent.get("slug")) if isinstance(agent, dict) else where(i, None)

        if not isinstance(agent, dict):
            problems.append(f"{where(i, None)} is not an object")
            continue

        slug = agent.get("slug")
        name = agent.get("name")
        repo = agent.get("repo")
        github_url = agent.get("githubUrl")

        if not isinstance(slug, str) or not slug:
            problems.append(f"{spot}: slug must be a non-empty string")
        else:
            if not _slug_shaped(slug):
                problems.append(
                    f'{spot}: slug "{slug}" is not slug-shaped (lowercase words joined by "-")'
                )
            if len(slug) > 64:
                problems.append(f"{spot}: slug is {len(slug)} chars — writeSnapshot caps at 64")
            dup_at = seen_slugs.get(slug)
            if dup_at is not None:
                problems.append(f"{spot}: duplicate slug — also at agents[{dup_at}]")
            else:
                seen_slugs[slug] = i

        if not isinstance(name, str) or not name.strip():
            problems.append(f"{spot}: name must be a non-empty string")

        if not isinstance(repo, str) or not repo.strip():
            problems.append(f"{spot}: repo must be a non-empty string")
        else:
            if re.search(r"\s", repo):
                problems.append(f'{spot}: repo "{repo}" contains whitespace')
            key = repo.lower()
            dup_at = seen_repos.get(key)
            if dup_at is not None:
                problems.append(f"{spot}: duplicate repo {repo} — also at agents[{dup_at}]")
            else:
                seen_repos[key] = i

            if github_url is not None and github_url != f"https://github.com/{repo}":
                problems.append(
                    f'{spot}: githubUrl must be null or "https://github.com/{repo}",'
                    f" got {json.dumps(github_url, ensure_ascii=False)}"
                )

        category = agent.get("category")
        if not isinstance(category, str) or category not in CATEGORIES:
            problems.append(f'{spot}: unknown category "{category}"')

        status = agent.get("status")
        if not isinstance(status, str) or status not in VALID_STATUSES:
            problems.append(
                f'{spot}: status "{status}" is not one of {", ".join(VALID_STATUSES)}'
            )

        for field in ("stars", "openIssues"):
            value = agent.get(field)
            if not _is_int(value) or value < 0:
                problems.append(f"{spot}: {field} must be a non-negative integer, got {value}")

        pushed_at = agent.get("pushedAt")
        if pushed_at is not None and (
            not isinstance(pushed_at, str) or not _iso_parseable(pushed_at)
        ):
            problems.append(f"{spot}: pushedAt is not an ISO date string — {pushed_at}")

        for field in ("homepage", "paper"):
            value = agent.get(field)
            if value is not None and not _is_http_url(value):
                problems.append(f"{spot}: {field} must be null or an http(s) URL, got {value}")

        if "tags" in agent:
            tags = agent["tags"]
            if not isinstance(tags, list) or any(not isinstance(t, str) or not t for t in tags):
                problems.append(f"{spot}: tags must be an array of non-empty strings")
            else:
                for violation in find_tag_policy_violations(tags):
                    problems.append(f"{spot}: tag policy — {violation}")
                unregistered = [t for t in tags if tag_type(t) is None]
                if unregistered:
                    problems.append(
                        f"{spot}: unregistered tag(s) {', '.join(unregistered)}"
                        " — add to TAG_TYPE in agentx/policy.py first"
                    )

        paper_meta = agent.get("paperMeta")
        if paper_meta is not None:
            if not isinstance(paper_meta, dict):
                problems.append(f"{spot}: paperMeta must be an object or null")
            else:
                title = paper_meta.get("title")
                if not isinstance(title, str) or not title.strip():
                    problems.append(f"{spot}: paperMeta.title must be a non-empty string")
                # null is legal: refresh-citations stores it for papers Semantic
                # Scholar does not index (bionemo-framework, STELLA).
                citations = paper_meta.get("citations")
                if citations is not None and not _is_int(citations):
                    problems.append(
                        f"{spot}: paperMeta.citations must be an integer or null, got {citations}"
                    )
                for meta_key in ("venue", "year", "authors", "firstAuthor", "doi", "paperUrl"):
                    value = paper_meta.get(meta_key)
                    if value is not None and not isinstance(value, str):
                        problems.append(f"{spot}: paperMeta.{meta_key} must be a string")
                venue_tag = registered_venue_tag(str(paper_meta.get("venue") or ""))
                tags = agent.get("tags")
                if not isinstance(tags, list):
                    tags = []
                if venue_tag is not None and venue_tag not in tags:
                    problems.append(
                        f"{spot}: paperMeta.venue maps to registered tag {venue_tag} "
                        "but tags does not contain it — run `updater backfill --agentx "
                        "--fields venue-tags`"
                    )

        retired_reason = agent.get("retiredReason")
        if retired_reason is not None:
            if not isinstance(retired_reason, str) or retired_reason not in RETIRED_REASONS:
                problems.append(
                    f'{spot}: retiredReason "{retired_reason}"'
                    " is not one of idle, owner-archived, not-found"
                )
            elif status not in ("archived", "gone"):
                problems.append(
                    f'{spot}: retiredReason set while status is "{status}"'
                    " — only graveyard records carry it"
                )
        retired_stars = agent.get("retiredStars")
        if retired_stars is not None and not _is_int(retired_stars):
            problems.append(f"{spot}: retiredStars must be an integer, got {retired_stars}")

        source_url = agent.get("sourceUrl")
        if source_url is not None and not _is_http_url(source_url):
            problems.append(f"{spot}: sourceUrl must be null or an http(s) URL")

        # Curation date: date-only ISO string stamped at intake; optional
        # because records that predate the field carry none.
        listed_at = agent.get("listedAt")
        if listed_at is not None and (
            not isinstance(listed_at, str) or not _iso_parseable(listed_at)
        ):
            problems.append(f"{spot}: listedAt is not an ISO date string — {listed_at}")

    # writeSnapshot sorts by slug so diffs stay deterministic — a file that
    # drifted out of order was not written by the pipeline. Codepoint order
    # (`sorted`), not localeCompare: the two collations disagree on
    # digit-vs-underscore slugs (paper2agent vs paper_claw-pigeondan1), and
    # the TypeScript writer/validator sort by codepoint for the same reason.
    slugs = [
        a["slug"] for a in agents if isinstance(a, dict) and isinstance(a.get("slug"), str)
    ]
    if any(s != t for s, t in zip(slugs, sorted(slugs))):
        problems.append(
            "agents are not in stable slug order (writeSnapshot sorts by slug codepoint order)"
        )

    return problems
