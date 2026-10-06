"""Fill paperMeta on the AgentX snapshot and refresh its citation counts —
the Python ports of agentx-cli's `enrich-papers` and `refresh-citations`.

`enrich_papers` resolves a paper record for every agent that carries a
precise paper clue — a DOI, arXiv ID, or Semantic Scholar paperId in its
paper/homepage URL, an arXiv mention or verbatim quoted title in its
description — through Semantic Scholar (Crossref backstops DOIs S2 has not
indexed yet) and stores the record as `paperMeta`. Agents whose only clue is an
arXiv ID whose DataCite DOI is not indexed fall back to resolving the title
via the arXiv API and re-querying by title.

Fills a missing `paper` link from the clue's canonical URL; an existing link
is never overwritten. Agents that already have `paperMeta` are skipped, so
re-runs only retry the misses (`force=True` re-enriches all). `only` scopes
the run to agents whose slug, name, repo, or paperMeta title/DOI contains a
given substring (case-insensitive) — for adding one record without churning
the rest. When a record lands, the agent's status is re-derived with the
fresh venue: a journal/conference paper qualifies for auto-stable at any
star count, so paper-backed agents promote instead of lingering in the
pre-paper status their add-time derivation froze in.

`refresh_citations` refreshes the `citations` field (Semantic Scholar
citationCount) on every agent that already has a `paperMeta` record. Nothing
else is touched — full re-enrichment would clobber fields that later
backfills filled in, so this stays surgical. Lookups go DOI-first (exact);
agents whose DOI is an unindexed DataCite arXiv DOI, or that carry no DOI,
fall back to a title lookup matched against the stored title. Records with a
citation count already set are re-queried too — counts drift, and this
command exists to refresh them.

Where the TypeScript CLI shelled out to `awescholar updater search`, these
functions call awescholar's own Semantic Scholar helpers directly. Env:
SEMANTICSCHOLAR_API_KEY (optional but recommended — the anonymous pool
rate-limits aggressively and shows up as "not found" misses).
"""

from __future__ import annotations

import re
import time
import urllib.request
from datetime import datetime

from ..record import _get_client, search_by_doi, search_by_paper_id, search_by_title
from .papers import (
    DESCRIPTION_MATCH_THRESHOLD,
    TITLE_MATCH_THRESHOLD,
    PaperClue,
    PaperMeta,
    arxiv_id_to_doi,
    best_title_match,
    clue_paper_url,
    extract_paper_clue,
)
from .policy import venue_tag_for
from .snapshot import read_snapshot, write_snapshot
from .transform import resolve_repo_status

ARXIV_API_TIMEOUT_SECONDS = 20


def _parse_pushed_at(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _to_meta(r: dict) -> PaperMeta:
    """Project an updater-shaped S2 record onto the snapshot's paperMeta."""
    authors = r.get("authors") or []
    return {
        "title": r.get("title") or "",
        "venue": r.get("venue") or "",
        "doi": r.get("doi") or "",
        "year": r.get("year") or "",
        # Prefer the full ordered author list; older CLI records only carry
        # the corresponding author in `team`.
        "authors": ", ".join(authors) if authors else (r.get("team") or ""),
        # S2 records carry no ordered author list, so the first author is
        # filled in later by a backfill pass on the website side.
        "firstAuthor": "",
        "paperUrl": r.get("paperUrl") or "",
        "citations": r["citations"] if r.get("citations") is not None else None,
    }


def arxiv_titles(ids: list[str], attempts: int = 3) -> dict[str, str]:
    """Resolve arXiv IDs to titles via the arXiv API (id_list supports batches).

    The API rate-limits bursts (3s window, "Rate exceeded." text response,
    HTTP 200) — retry each failed batch with backoff instead of silently
    giving up.
    """
    out: dict[str, str] = {}
    if not ids:
        return out
    url = f"https://export.arxiv.org/api/query?id_list={','.join(ids)}&max_results={len(ids)}"
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=ARXIV_API_TIMEOUT_SECONDS) as resp:
                xml = resp.read().decode("utf-8")
        except Exception:  # noqa: BLE001 — unreachable API retries, then yields no titles
            xml = None  # unreachable API: fall through to the backoff below
        if xml is not None:
            # Atom: <entry><title>…</title> — one entry per id, in request order.
            titles = [
                re.sub(r"\s+", " ", t).strip()
                for t in re.findall(r"<title>(.*?)</title>", xml, re.DOTALL)
            ]
            if not re.search(r"Rate exceeded", xml, re.IGNORECASE):
                titles.pop(0)  # the first <title> is the feed's, not an entry's
                for i, arxiv_id in enumerate(ids):
                    if i < len(titles) and not titles[i].startswith("Error"):
                        out[arxiv_id] = titles[i]
                return out
        if attempt < attempts:
            time.sleep(5 * attempt)
    return out


def _add_query(queries: dict[str, dict], value: str, slug: str, strict: bool) -> None:
    """Register a slug under a query value; identical queries deduplicate."""
    entry = queries.get(value)
    if entry:
        entry["slugs"].append(slug)
    else:
        queries[value] = {"slugs": [slug], "strict": strict}


def _matches_only(agent: dict, only: list[str]) -> bool:
    """Case-insensitive --only scope: slug, name, repo, or paperMeta title/DOI.

    Slugs are lowercase while display names are not, so "Paper2Agent" must
    still find slug "paper2agent" — slug-only matching silently selected
    nothing for mixed-case patterns.
    """
    if not only:
        return True
    meta = agent.get("paperMeta") or {}
    fields = [agent.get(k) or "" for k in ("slug", "name", "repo")]
    fields += [meta.get(k) or "" for k in ("title", "doi")]
    hay = " ".join(str(f) for f in fields).lower()
    return any(o.lower() in hay for o in only)


def enrich_papers(
    snapshot_file: str,
    *,
    force: bool = False,
    only: list[str] | None = None,
    ss_api_key: str | None = None,
    status_cb=print,
) -> dict:
    """Fill paperMeta from Semantic Scholar for every agent with a precise clue.

    Skips agents that already have paperMeta unless ``force``; scopes to
    agents matching ``only`` (see :func:`_matches_only`) when given. After a
    record lands, the agent's status is re-derived with the fresh venue —
    a journal/conference paper qualifies for auto-stable at any star count,
    so a paper-backed agent never lingers in its pre-paper status. Always
    rewrites the snapshot at the end (even with nothing enriched), matching
    the TypeScript command. Returns {"enriched", "filled_link", "promoted",
    "unresolved", "skipped", "misses"}.
    """
    snapshot = read_snapshot(snapshot_file)
    agents = snapshot["agents"]
    pending = [
        a
        for a in agents
        if (force or not a.get("paperMeta"))
        and a.get("status") != "archived"
        and a.get("status") != "gone"
        and (not only or _matches_only(a, only))
    ]
    clues: dict[str, PaperClue] = {}
    no_clue = 0
    for a in pending:
        clue = extract_paper_clue(a)
        if clue:
            clues[a["slug"]] = clue
        else:
            no_clue += 1

    def by_kind(kind: str) -> list[tuple[str, PaperClue]]:
        return [(slug, c) for slug, c in clues.items() if c.kind == kind]

    status_cb(
        f"Enriching {len(pending)}/{len(agents)} agents — "
        f"clues: {len(by_kind('doi'))} DOI, {len(by_kind('arxiv'))} arXiv, "
        f"{len(by_kind('s2'))} S2, {len(by_kind('title'))} title, "
        f"{no_clue} without a precise clue."
    )
    if not clues:
        return {
            "enriched": 0,
            "filled_link": 0,
            "promoted": 0,
            "unresolved": 0,
            "skipped": len(agents) - len(pending),
            "misses": [],
        }

    sch = _get_client(ss_api_key)

    # Pass 1: DOI lookups (paper-URL DOIs + arXiv IDs in DataCite DOI form).
    doi_query: dict[str, dict] = {}  # query value -> {slugs, strict}
    for slug, clue in by_kind("doi"):
        _add_query(doi_query, clue.value, slug, False)
    for slug, clue in by_kind("arxiv"):
        _add_query(doi_query, arxiv_id_to_doi(clue.value), slug, False)
    doi_records: dict[str, dict] = {}  # doi (lowercase) -> record
    if doi_query:
        hits = 0
        for doi in doi_query:
            record = search_by_doi(doi, sch)
            if record:
                hits += 1
                if record.get("doi"):
                    doi_records[record["doi"].lower()] = record
        status_cb(f"  S2 DOI lookups: {len(doi_query)} queries -> {hits} records")

    # Pass 1b: S2 page links carry the paperId itself — one exact lookup per
    # id, no title fuzzing needed.
    s2_query: dict[str, list[str]] = {}  # paperId (lowercase) -> slugs
    for slug, clue in by_kind("s2"):
        s2_query.setdefault(clue.value.lower(), []).append(slug)
    s2_records: dict[str, dict] = {}  # paperId (lowercase) -> record
    if s2_query:
        hits = 0
        for paper_id in s2_query:
            record = search_by_paper_id(paper_id, sch)
            if record:
                hits += 1
                s2_records[paper_id] = record
        status_cb(f"  S2 paperId lookups: {len(s2_query)} queries -> {hits} records")

    # Pass 2: agents whose DOI lookup missed -> retry by title. arXiv clues
    # get their title from the arXiv API; DOI clues try the description —
    # first a verbatim quoted title, then (strictly gated) the whole
    # description, which for paper-first repos is the title itself. S2's
    # title endpoint is a separate pool from its DOI endpoint, so one being
    # rate-limited does not imply the other is.
    title_query: dict[str, dict] = {}  # query value -> {slugs, strict}
    for slug, clue in by_kind("title"):
        _add_query(title_query, clue.value, slug, False)
    doi_missed = [
        (slug, clue)
        for slug, clue in clues.items()
        if (clue.kind == "arxiv" and arxiv_id_to_doi(clue.value).lower() not in doi_records)
        or (clue.kind == "doi" and clue.value.lower() not in doi_records)
    ]
    arxiv_resolved = arxiv_titles([c.value for _, c in doi_missed if c.kind == "arxiv"])
    quoted_fallbacks = description_fallbacks = 0
    for slug, clue in doi_missed:
        title = None
        strict = True  # whole-description guesses need near-complete cover
        if clue.kind == "arxiv":
            title = arxiv_resolved.get(clue.value)
            strict = False  # arXiv API titles are the paper's own
        else:
            # DOI clue: reuse the quoted-title extraction — the same
            # description that named the paper often carries its full title
            # in quotes.
            agent = next(a for a in agents if a["slug"] == slug)
            quoted = extract_paper_clue({"paper": "", "description": agent.get("description")})
            if quoted is not None and quoted.kind == "title":
                title = quoted.value
                quoted_fallbacks += 1
                strict = False  # verbatim quote, same bar as a normal title clue
            elif agent.get("description"):
                # Last resort: a GitHub repo description that IS the paper
                # title (no quotes, single sentence). Treated as a strict guess.
                title = re.split(r"(?<=[.!?])\s", agent["description"])[0].strip()
                description_fallbacks += 1
        if title:
            _add_query(title_query, title, slug, strict)
    if doi_missed:
        status_cb(
            f"  DOI/arXiv misses: {len(doi_missed)} — {len(arxiv_resolved)} via arXiv API, "
            f"{quoted_fallbacks} quoted / {description_fallbacks} description titles as fallback"
        )
    title_records: list[dict] = []
    if title_query:
        for title in title_query:
            record = search_by_title(title, sch)
            if record:
                title_records.append(record)
        status_cb(f"  S2 title lookups: {len(title_query)} queries -> {len(title_records)} records")

    # Merge: map each query value to its record, then each slug to metadata.
    resolved: dict[str, tuple[PaperClue, PaperMeta]] = {}
    for query, entry in doi_query.items():
        record = doi_records.get(query.lower())
        if not record:
            continue
        for slug in entry["slugs"]:
            resolved[slug] = (clues[slug], _to_meta(record))
    for paper_id, slugs in s2_query.items():
        record = s2_records.get(paper_id)
        if not record:
            continue
        for slug in slugs:
            resolved[slug] = (clues[slug], _to_meta(record))
    for query, entry in title_query.items():
        # Title clues match fuzzily: accept the record covering the query best.
        # Strict queries (whole-description guesses) need near-complete cover.
        best = best_title_match(
            query,
            title_records,
            DESCRIPTION_MATCH_THRESHOLD if entry["strict"] else TITLE_MATCH_THRESHOLD,
        )
        if not best:
            continue
        for slug in entry["slugs"]:
            resolved[slug] = (clues[slug], _to_meta(best))

    enriched = filled_link = promoted = 0
    misses: list[str] = []
    for a in agents:
        hit = resolved.get(a["slug"])
        if hit is None:
            if a["slug"] in clues:
                misses.append(a["slug"])
            continue
        clue, meta = hit
        a["paperMeta"] = meta
        # A freshly attached venue can change the status verdict — journal/
        # conference papers qualify for auto-stable at any star count, though
        # the verdict only surfaces on quiet records (an actively-pushed one
        # reads active; freshness outranks the stable verdict). Without this
        # re-derivation, paper-backed agents linger in the pre-paper status
        # their add-time derivation froze in. Protected no-repo resolves to
        # itself, so that status never moves here.
        prev_status = str(a.get("status") or "")
        status = resolve_repo_status(
            current_status=prev_status,
            archived=bool(a.get("archived")),
            stars=int(a.get("stars") or 0),
            pushed_at=_parse_pushed_at(a.get("pushedAt")),
            paper_venue=str(meta.get("venue") or ""),
            auto_stable_exempt=bool(a.get("autoStableExempt")),
        )
        if status != prev_status:
            a["status"] = status
            promoted += 1
        if not a.get("paper"):
            url = clue_paper_url(clue, meta)
            if url:
                a["paper"] = url
                filled_link += 1
        enriched += 1

    write_snapshot(snapshot_file, snapshot)
    status_cb(
        f"\nDone. enriched={enriched} paper-links-filled={filled_link} "
        f"status-promoted={promoted} "
        f"unresolved={len(misses)} skipped={len(agents) - len(pending)}"
    )
    if filled_link > 0:
        status_cb("Newly filled paper links are listed in the snapshot diff.")
    if misses:
        status_cb(f"Unresolved (re-run retries these): {', '.join(misses)}")
        status_cb(
            "Persistent misses are usually papers Semantic Scholar has not indexed — "
            "set SEMANTICSCHOLAR_API_KEY to rule out rate limits."
        )
    return {
        "enriched": enriched,
        "filled_link": filled_link,
        "promoted": promoted,
        "unresolved": len(misses),
        "skipped": len(agents) - len(pending),
        "misses": misses,
    }


def sync_venue_tags(
    snapshot_file: str,
    *,
    only: list[str] | None = None,
    status_cb=print,
) -> dict:
    """Project paper venues onto an agent's attribution tags.

    paperMeta.venue remains the source record from the publication database;
    this local, idempotent pass adds its venue tag when absent — the
    registered canonical tag for known venues, an auto-generated slug
    (npj-Health-Systems) for unknown ones. Non-venue sources (blogs,
    technical reports) and every existing tag are left untouched.
    """
    snapshot = read_snapshot(snapshot_file)
    updated = skipped_unknown = 0
    for agent in snapshot["agents"]:
        if only and not _matches_only(agent, only):
            continue
        meta = agent.get("paperMeta") or {}
        venue_tag = venue_tag_for(str(meta.get("venue") or ""))
        if venue_tag is None:
            if str(meta.get("venue") or "").strip():
                skipped_unknown += 1
            continue
        tags = agent.get("tags")
        if not isinstance(tags, list):
            continue
        if venue_tag in tags:
            continue
        agent["tags"] = [*tags, venue_tag]
        updated += 1

    if updated:
        write_snapshot(snapshot_file, snapshot)
    status_cb(
        f"Venue tags synced: updated={updated} unknown-venues-skipped={skipped_unknown}"
    )
    return {"updated": updated, "unknown_venues_skipped": skipped_unknown}


def refresh_citations(
    snapshot_file: str,
    *,
    ss_api_key: str | None = None,
    status_cb=print,
) -> dict:
    """Refresh paperMeta.citations from Semantic Scholar.

    Every agent with a paperMeta record is re-queried (counts drift);
    nothing but the citations field is touched, and the snapshot is written
    back only when at least one count changed. Returns {"updated",
    "unchanged", "unresolved", "misses"}.
    """
    snapshot = read_snapshot(snapshot_file)
    agents = snapshot["agents"]
    with_paper = [
        a
        for a in agents
        if a.get("paperMeta") and a.get("status") != "archived" and a.get("status") != "gone"
    ]
    status_cb(f"Refreshing citations for {len(with_paper)} agents with a paper record.")
    if not with_paper:
        return {"updated": 0, "unchanged": 0, "unresolved": 0, "misses": []}

    sch = _get_client(ss_api_key)

    # Pass 1: DOI lookups — exact, one pass.
    doi_to_slugs: dict[str, list[str]] = {}
    for a in with_paper:
        doi = (a["paperMeta"].get("doi") or "").strip()
        if not doi:
            continue
        doi_to_slugs.setdefault(doi.lower(), []).append(a["slug"])
    citations: dict[str, int] = {}  # doi (lowercase) -> citation count
    hits = 0
    for doi in doi_to_slugs:
        record = search_by_doi(doi, sch)
        if record:
            hits += 1
        # Only records with a numeric count and a DOI can refresh anything.
        if record and isinstance(record.get("citations"), int) and record.get("doi"):
            citations[record["doi"].lower()] = record["citations"]
    status_cb(f"  S2 DOI lookups: {len(doi_to_slugs)} queries -> {hits} records")

    # Pass 2: DOI misses and no-DOI records — retry by stored title.
    missed = [
        a
        for a in with_paper
        if not (a["paperMeta"].get("doi") or "").strip()
        or (a["paperMeta"].get("doi") or "").strip().lower() not in citations
    ]
    title_query: dict[str, list[str]] = {}
    for a in missed:
        title_query.setdefault(a["paperMeta"]["title"], []).append(a["slug"])
    title_records: list[dict] = []
    if title_query:
        for title in title_query:
            record = search_by_title(title, sch)
            if record:
                title_records.append(record)
        status_cb(f"  S2 title lookups: {len(title_query)} queries -> {len(title_records)} records")
    # The query is the stored S2 title, so the true record matches at ~1.0;
    # the default threshold only filters lookalikes.
    title_hits: dict[str, int] = {}
    for title, slugs in title_query.items():
        best = best_title_match(title, title_records)
        n = best.get("citations") if best else None
        if best and isinstance(n, int):
            for slug in slugs:
                title_hits[slug] = n

    updated = unchanged = 0
    misses: list[str] = []
    for a in with_paper:
        meta = a["paperMeta"]
        doi = (meta.get("doi") or "").strip().lower()
        n = citations.get(doi) if doi else None
        if n is None:
            n = title_hits.get(a["slug"])
        if n is None:
            misses.append(a["slug"])
            continue
        if meta.get("citations") == n:
            unchanged += 1
            continue
        meta["citations"] = n
        updated += 1

    if updated > 0:
        write_snapshot(snapshot_file, snapshot)
    status_cb(
        f"\nDone. citations updated={updated} already-current={unchanged} "
        f"unresolved={len(misses)}"
    )
    if misses:
        status_cb(f"Unresolved (kept previous value): {', '.join(misses)}")
        status_cb(
            "Persistent misses are usually papers Semantic Scholar has not indexed — "
            "set SEMANTICSCHOLAR_API_KEY to rule out rate limits."
        )
    return {"updated": updated, "unchanged": unchanged, "unresolved": len(misses), "misses": misses}
