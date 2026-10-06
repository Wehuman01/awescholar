"""Tests for papers_fill.py — the enrich-papers / refresh-citations ports.

All Semantic Scholar and arXiv access is monkeypatched at the
awescholar.agentx.papers_fill namespace; no test touches the network.
"""

import json
import urllib.request
from pathlib import Path

import pytest

from awescholar.agentx import papers_fill
from awescholar.agentx.papers_fill import enrich_papers, refresh_citations, sync_venue_tags

# --- Fixtures -----------------------------------------------------------------


def _agent(slug: str, **over) -> dict:
    """One snapshot agent in the agentx-cli demo-repo fixture shape."""
    agent = {
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "repo": f"example/{slug}",
        "githubUrl": f"https://github.com/example/{slug}",
        "homepage": None,
        "paper": None,
        "paperMeta": None,
        "category": "bio-omics",
        "tags": [],
        "language": "Python",
        "stars": 42,
        "pushedAt": "2026-09-01T00:00:00Z",
        "openIssues": 2,
        "license": "MIT",
        "description": "An autonomous assistant for biology research.",
        "status": "active",
        "source": "manual",
        "sourceUrl": None,
    }
    agent.update(over)
    return agent


def _record(title: str, doi: str, citations: int | None = 12, **over) -> dict:
    """One updater-shaped S2 record (what search_by_doi/search_by_title return)."""
    record = {
        "year": "2026.03",
        "title": title,
        "team": "A. Researcher",
        "authors": ["A. Researcher", "B. Author"],
        "venue": "Nature",
        "paperUrl": f"https://doi.org/{doi}" if doi else "",
        "doi": doi,
        "citations": citations,
    }
    record.update(over)
    return record


def _meta(doi: str, title: str, citations: int | None) -> dict:
    """A stored paperMeta in the snapshot shape."""
    return {
        "title": title,
        "venue": "",
        "doi": doi,
        "year": "",
        "authors": "",
        "firstAuthor": "",
        "paperUrl": "",
        "citations": citations,
    }


def _snapshot_file(tmp_path: Path, agents: list[dict]) -> str:
    path = tmp_path / "agents-snapshot.json"
    path.write_text(json.dumps({"agents": agents, "counts": {"total": len(agents)}}))
    return str(path)


def _must_not_call(name):
    def fn(*args, **kwargs):
        raise AssertionError(f"{name} should not have been called")

    return fn


@pytest.fixture(autouse=True)
def no_s2(monkeypatch):
    """Never construct a real SemanticScholar client in tests."""
    monkeypatch.setattr(papers_fill, "_get_client", lambda api_key=None: object())


def _by_slug(path: str) -> dict:
    return {a["slug"]: a for a in json.loads(Path(path).read_text())["agents"]}


# --- enrich_papers ------------------------------------------------------------


def test_enrich_doi_clue_writes_paper_meta(tmp_path, monkeypatch):
    doi_calls = []

    def fake_doi(doi, sch):
        doi_calls.append(doi)
        return _record("Alpha: Agents for Biology", "10.1038/s41586-026-00000-0", citations=12)

    monkeypatch.setattr(papers_fill, "search_by_doi", fake_doi)
    monkeypatch.setattr(papers_fill, "search_by_title", _must_not_call("search_by_title"))
    path = _snapshot_file(
        tmp_path,
        [
            # Quiet repo: the journal-venue promotion only surfaces on quiet
            # records — an actively-pushed one reads active (freshness
            # outranks the stable verdict).
            _agent(
                "alpha-agent",
                paper="https://doi.org/10.1038/s41586-026-00000-0",
                pushedAt="2020-01-01T00:00:00Z",
            ),
            _agent("beta-agent"),  # description carries no precise clue
        ],
    )
    lines: list[str] = []

    stats = enrich_papers(path, status_cb=lines.append)

    assert doi_calls == ["10.1038/s41586-026-00000-0"]
    assert (
        "Enriching 2/2 agents — clues: 1 DOI, 0 arXiv, 0 S2, 0 title, "
        "1 without a precise clue." in lines
    )
    assert stats == {
        "enriched": 1,
        "filled_link": 0,
        "promoted": 1,  # Nature is a journal venue -> auto-stable at any stars
        "unresolved": 0,
        "skipped": 0,
        "misses": [],
    }
    agent = _by_slug(path)["alpha-agent"]
    assert agent["status"] == "stable"
    meta = agent["paperMeta"]
    assert meta == {
        "title": "Alpha: Agents for Biology",
        "venue": "Nature",
        "doi": "10.1038/s41586-026-00000-0",
        "year": "2026.03",
        "authors": "A. Researcher, B. Author",
        "firstAuthor": "",
        "paperUrl": "https://doi.org/10.1038/s41586-026-00000-0",
        "citations": 12,
    }


def test_enrich_s2_clue_resolves_by_paper_id(tmp_path, monkeypatch):
    paper_id = "F5AF8E3F7ACD968B7BAEB788F5B33CF7D868616E"
    id_calls = []

    def fake_paper_id(pid, sch):
        id_calls.append(pid)
        return _record(
            "scCompass: An Integrated Multi-Species scRNA-seq Database",
            "10.1002/advs.202500870",
            citations=11,
            venue="",  # not a registered journal tier -> no status promotion
            year="2025.06",
        )

    monkeypatch.setattr(papers_fill, "search_by_paper_id", fake_paper_id)
    monkeypatch.setattr(papers_fill, "search_by_doi", _must_not_call("search_by_doi"))
    monkeypatch.setattr(papers_fill, "search_by_title", _must_not_call("search_by_title"))
    path = _snapshot_file(
        tmp_path,
        [_agent("sccompass", paper=f"https://www.semanticscholar.org/paper/{paper_id}")],
    )
    lines: list[str] = []

    stats = enrich_papers(path, status_cb=lines.append)

    assert id_calls == [paper_id.lower()]
    assert (
        "Enriching 1/1 agents — clues: 0 DOI, 0 arXiv, 1 S2, 0 title, "
        "0 without a precise clue." in lines
    )
    assert stats["enriched"] == 1 and stats["promoted"] == 0 and stats["misses"] == []
    agent = _by_slug(path)["sccompass"]
    assert agent["status"] == "active"
    # The existing paper link is never overwritten, even though a canonical
    # DOI link is now known.
    assert agent["paper"] == f"https://www.semanticscholar.org/paper/{paper_id}"
    assert agent["paperMeta"]["doi"] == "10.1002/advs.202500870"
    assert agent["paperMeta"]["citations"] == 11


def test_enrich_arxiv_clue_queries_datacite_doi(tmp_path, monkeypatch):
    doi_calls = []

    def fake_doi(doi, sch):
        doi_calls.append(doi)
        return _record("Agents in the Wild", "10.48550/arXiv.2505.20286", citations=3)

    monkeypatch.setattr(papers_fill, "search_by_doi", fake_doi)
    monkeypatch.setattr(papers_fill, "search_by_title", _must_not_call("search_by_title"))
    path = _snapshot_file(tmp_path, [_agent("gamma-agent", paper="https://arxiv.org/abs/2505.20286")])

    stats = enrich_papers(path)

    assert doi_calls == ["10.48550/arXiv.2505.20286"]
    assert stats["enriched"] == 1
    assert _by_slug(path)["gamma-agent"]["paperMeta"]["doi"] == "10.48550/arXiv.2505.20286"


def test_enrich_doi_miss_falls_back_to_quoted_title(tmp_path, monkeypatch):
    monkeypatch.setattr(papers_fill, "search_by_doi", lambda doi, sch: None)
    title_calls = []

    def fake_title(query, sch):
        title_calls.append(query)
        return _record("Quoted Title for Missing DOI", "10.2000/quoted", citations=1)

    monkeypatch.setattr(papers_fill, "search_by_title", fake_title)
    path = _snapshot_file(
        tmp_path,
        [
            _agent(
                "delta-agent",
                paper="https://doi.org/10.2000/missing",
                description='A tool for "Quoted Title for Missing DOI" (2026).',
            )
        ],
    )

    stats = enrich_papers(path)

    assert title_calls == ["Quoted Title for Missing DOI"]
    assert stats["enriched"] == 1 and stats["unresolved"] == 0
    assert _by_slug(path)["delta-agent"]["paperMeta"]["doi"] == "10.2000/quoted"


def test_enrich_description_fallback_is_strict(tmp_path, monkeypatch):
    monkeypatch.setattr(papers_fill, "search_by_doi", lambda doi, sch: None)
    titles = {
        # Covers 6 of the description's 8 tokens: clears the loose bar (0.7)
        # but not the strict one (0.9) a whole-description guess requires.
        "Automated Discovery of Chemical Reactions Using Language": _record(
            "Automated Discovery of Chemical Reactions Using Language", "10.3000/partial"
        ),
        "Exact Description As A Title": _record("Exact Description As A Title", "10.3000/exact"),
    }
    monkeypatch.setattr(papers_fill, "search_by_title", lambda q, sch: titles.get(q))
    path = _snapshot_file(
        tmp_path,
        [
            _agent(
                "partial-agent",
                paper="https://doi.org/10.3000/partial",
                description="Automated Discovery of Chemical Reactions Using Language Models",
            ),
            _agent(
                "exact-agent",
                paper="https://doi.org/10.3000/exact",
                description="Exact Description As A Title",
            ),
        ],
    )

    stats = enrich_papers(path)

    assert stats["enriched"] == 1 and stats["unresolved"] == 1
    assert stats["misses"] == ["partial-agent"]
    enriched = {
        slug for slug, a in _by_slug(path).items() if a["paperMeta"] is not None
    }
    assert enriched == {"exact-agent"}


def test_enrich_arxiv_doi_miss_falls_back_to_arxiv_title_and_fills_link(tmp_path, monkeypatch):
    monkeypatch.setattr(papers_fill, "search_by_doi", lambda doi, sch: None)
    arxiv_ids = []

    def fake_arxiv(ids, attempts=3):
        arxiv_ids.extend(ids)
        return {i: f"arXiv Title {i}" for i in ids}

    monkeypatch.setattr(papers_fill, "arxiv_titles", fake_arxiv)
    title_calls = []

    def fake_title(query, sch):
        title_calls.append(query)
        return _record(
            "arXiv Title 2505.20286",
            "",
            citations=5,
            paperUrl="https://arxiv.org/abs/2505.20286v1",
        )

    monkeypatch.setattr(papers_fill, "search_by_title", fake_title)
    path = _snapshot_file(
        tmp_path, [_agent("gamma-agent", description="Implementation of the paper arXiv 2505.20286")]
    )

    stats = enrich_papers(path)

    assert arxiv_ids == ["2505.20286"]
    assert title_calls == ["arXiv Title 2505.20286"]
    # The agent had no paper link; the clue's canonical URL fills it.
    assert stats["enriched"] == 1 and stats["filled_link"] == 1
    agent = _by_slug(path)["gamma-agent"]
    assert agent["paper"] == "https://arxiv.org/abs/2505.20286"
    assert agent["paperMeta"]["paperUrl"] == "https://arxiv.org/abs/2505.20286v1"


def test_enrich_skips_existing_meta_unless_forced(tmp_path, monkeypatch):
    monkeypatch.setattr(
        papers_fill, "search_by_doi", lambda doi, sch: _record("Fresh Meta", doi)
    )
    path = _snapshot_file(
        tmp_path,
        [
            _agent("alpha-agent", paper="https://doi.org/10.1/alpha",
                   paperMeta=_meta("10.0/old", "Old Title", 1)),
            _agent("beta-agent", paper="https://doi.org/10.1/beta"),
        ],
    )

    stats = enrich_papers(path)

    assert stats["enriched"] == 1 and stats["skipped"] == 1
    by_slug = _by_slug(path)
    assert by_slug["alpha-agent"]["paperMeta"]["title"] == "Old Title"
    assert by_slug["beta-agent"]["paperMeta"]["title"] == "Fresh Meta"

    stats = enrich_papers(path, force=True)

    assert stats["enriched"] == 2 and stats["skipped"] == 0
    by_slug = _by_slug(path)
    assert by_slug["alpha-agent"]["paperMeta"]["title"] == "Fresh Meta"


def test_enrich_only_scopes_to_matching_slugs(tmp_path, monkeypatch):
    doi_calls = []

    def fake_doi(doi, sch):
        doi_calls.append(doi)
        return _record("Scoped Meta", doi)

    monkeypatch.setattr(papers_fill, "search_by_doi", fake_doi)
    path = _snapshot_file(
        tmp_path,
        [
            _agent("alpha-agent", paper="https://doi.org/10.1/alpha"),
            _agent("beta-agent", paper="https://doi.org/10.1/beta"),
        ],
    )

    stats = enrich_papers(path, only=["beta"])

    assert doi_calls == ["10.1/beta"]
    assert stats["enriched"] == 1 and stats["skipped"] == 1
    by_slug = _by_slug(path)
    assert by_slug["alpha-agent"]["paperMeta"] is None
    assert by_slug["beta-agent"]["paperMeta"]["title"] == "Scoped Meta"


def test_enrich_only_matches_case_insensitively_across_fields(tmp_path, monkeypatch):
    """--only scopes beyond the slug — name, repo, paperMeta — case-insensitively.

    Regression: slug-only matching selected nothing for "Paper2Agent" because
    the slug is lowercase.
    """
    monkeypatch.setattr(papers_fill, "search_by_doi", lambda doi, sch: None)
    monkeypatch.setattr(papers_fill, "search_by_title", lambda q, sch: None)
    path = _snapshot_file(
        tmp_path,
        [
            _agent("paper2agent", paper="https://doi.org/10.1/p2a"),  # name "Paper2Agent"
            _agent("other-agent", repo="example/Paper2Agent-clone", paper="https://doi.org/10.1/oth"),
            _agent("unrelated-agent", paper="https://doi.org/10.1/unrel"),
        ],
    )

    stats = enrich_papers(path, only=["Paper2Agent"])

    assert stats["enriched"] == 0 and stats["skipped"] == 1
    assert stats["misses"] == ["paper2agent", "other-agent"]


def test_enrich_excludes_archived_and_gone(tmp_path, monkeypatch):
    monkeypatch.setattr(papers_fill, "search_by_doi", _must_not_call("search_by_doi"))
    path = _snapshot_file(
        tmp_path,
        [
            _agent("old-agent", paper="https://doi.org/10.1/old", status="archived"),
            _agent("dead-agent", paper="https://doi.org/10.1/dead", status="gone"),
        ],
    )

    stats = enrich_papers(path)

    assert stats == {
        "enriched": 0,
        "filled_link": 0,
        "promoted": 0,
        "unresolved": 0,
        "skipped": 2,
        "misses": [],
    }
    for a in _by_slug(path).values():
        assert a["paperMeta"] is None


def test_enrich_writes_snapshot_even_when_nothing_resolves(tmp_path, monkeypatch):
    # The TypeScript command always wrote the snapshot at the end of the run,
    # even with zero enrichments — re-runs then retry the misses.
    monkeypatch.setattr(papers_fill, "search_by_doi", lambda doi, sch: None)
    monkeypatch.setattr(papers_fill, "search_by_title", lambda q, sch: None)
    writes = []
    monkeypatch.setattr(papers_fill, "write_snapshot", lambda f, s: writes.append(f))
    path = _snapshot_file(
        tmp_path,
        [
            _agent(
                "delta-agent",
                paper="https://doi.org/10.2000/missing",
                description='A tool for "Quoted Title for Missing DOI" (2026).',
            )
        ],
    )

    stats = enrich_papers(path)

    assert stats["enriched"] == 0 and stats["misses"] == ["delta-agent"]
    assert writes == [path]


# --- enrich_papers: status re-derivation --------------------------------------


def test_enrich_preprint_venue_keeps_low_star_agent_active(tmp_path, monkeypatch):
    """Only journal/conference venues auto-stable; an arXiv preprint with
    42 stars stays active — paperMeta lands, status does not move."""
    monkeypatch.setattr(
        papers_fill, "search_by_doi", lambda doi, sch: _record("Preprint Tool", doi, venue="arXiv")
    )
    path = _snapshot_file(
        tmp_path, [_agent("preprint-agent", paper="https://doi.org/10.48550/arXiv.2505.1")]
    )

    stats = enrich_papers(path)

    assert stats["promoted"] == 0
    agent = _by_slug(path)["preprint-agent"]
    assert agent["paperMeta"]["venue"] == "arXiv" and agent["status"] == "active"


def test_enrich_never_touches_protected_no_repo_status(tmp_path, monkeypatch):
    monkeypatch.setattr(
        papers_fill,
        "search_by_doi",
        lambda doi, sch: _record("Atlas Paper", doi, venue="Cell"),
    )
    path = _snapshot_file(
        tmp_path,
        [
            _agent(
                "atlas-agent",
                repo="cell.com/atlas",
                status="no-repo",
                paper="https://doi.org/10.1/atlas",
            )
        ],
    )

    stats = enrich_papers(path)

    agent = _by_slug(path)["atlas-agent"]
    assert stats["enriched"] == 1 and stats["promoted"] == 0
    assert agent["paperMeta"]["venue"] == "Cell" and agent["status"] == "no-repo"


# --- sync_venue_tags ----------------------------------------------------------


def test_sync_venue_tags_adds_canonical_registered_venue_and_is_idempotent(tmp_path):
    path = _snapshot_file(
        tmp_path,
        [
            _agent("nature-agent", tags=["Stanford"], paperMeta=_meta("", "Nature paper", 1)),
            _agent("alias-agent", paperMeta={**_meta("", "BME paper", 1), "venue": "Nature Biomedical Engineering"}),
            _agent("unknown-agent", paperMeta={**_meta("", "Unknown paper", 1), "venue": "Nvidia's blog"}),
        ],
    )
    by_slug = _by_slug(path)
    by_slug["nature-agent"]["paperMeta"]["venue"] = "Nature"
    Path(path).write_text(json.dumps({"agents": list(by_slug.values()), "counts": {"total": 3}}))

    first = sync_venue_tags(path)
    assert first == {"updated": 2, "unknown_venues_skipped": 1}
    agents = _by_slug(path)
    assert agents["nature-agent"]["tags"] == ["Stanford", "Nature"]
    assert agents["alias-agent"]["tags"] == ["Nature-BME"]
    assert agents["unknown-agent"]["tags"] == []

    second = sync_venue_tags(path)
    assert second == {"updated": 0, "unknown_venues_skipped": 1}


def test_sync_venue_tags_respects_only(tmp_path):
    path = _snapshot_file(
        tmp_path,
        [
            _agent("alpha-agent", paperMeta={**_meta("", "Alpha", 1), "venue": "Nature"}),
            _agent("beta-agent", paperMeta={**_meta("", "Beta", 1), "venue": "Nature"}),
        ],
    )

    result = sync_venue_tags(path, only=["BETA"])

    assert result["updated"] == 1
    agents = _by_slug(path)
    assert agents["alpha-agent"]["tags"] == []
    assert agents["beta-agent"]["tags"] == ["Nature"]


# --- refresh_citations --------------------------------------------------------


def test_refresh_citations_updates_changed_counts_and_uses_title_fallback(
    tmp_path, monkeypatch
):
    def fake_doi(doi, sch):
        counts = {"10.1/alpha": 4, "10.1/beta": 12}
        n = counts.get(doi)
        return _record("T", doi, citations=n) if n is not None else None

    monkeypatch.setattr(papers_fill, "search_by_doi", fake_doi)
    title_calls = []

    def fake_title(query, sch):
        title_calls.append(query)
        return _record("Gamma Paper Title", "", citations=7)

    monkeypatch.setattr(papers_fill, "search_by_title", fake_title)
    path = _snapshot_file(
        tmp_path,
        [
            # alpha already current, beta drifted, gamma has no DOI (title pass)
            _agent("alpha-agent", paperMeta=_meta("10.1/alpha", "T Alpha", 4)),
            _agent("beta-agent", paperMeta=_meta("10.1/beta", "T Beta", 9)),
            _agent("gamma-agent", paperMeta=_meta("", "Gamma Paper Title", 1)),
        ],
    )

    stats = refresh_citations(path)

    assert title_calls == ["Gamma Paper Title"]
    assert stats["updated"] == 2 and stats["unchanged"] == 1 and stats["unresolved"] == 0
    by_slug = _by_slug(path)
    assert by_slug["alpha-agent"]["paperMeta"]["citations"] == 4
    assert by_slug["beta-agent"]["paperMeta"]["citations"] == 12
    assert by_slug["gamma-agent"]["paperMeta"]["citations"] == 7


def test_refresh_citations_keeps_value_and_skips_write_when_unresolved(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(papers_fill, "search_by_doi", lambda doi, sch: None)
    monkeypatch.setattr(papers_fill, "search_by_title", lambda q, sch: None)
    writes = []
    monkeypatch.setattr(papers_fill, "write_snapshot", lambda f, s: writes.append(f))
    path = _snapshot_file(
        tmp_path, [_agent("alpha-agent", paperMeta=_meta("10.1/alpha", "T Alpha", 4))]
    )

    stats = refresh_citations(path)

    assert stats == {"updated": 0, "unchanged": 0, "unresolved": 1,
                     "misses": ["alpha-agent"]}
    # Nothing changed -> the TypeScript command did not write; keep that.
    assert writes == []
    assert _by_slug(path)["alpha-agent"]["paperMeta"]["citations"] == 4


def test_refresh_citations_skips_write_when_all_current(tmp_path, monkeypatch):
    monkeypatch.setattr(
        papers_fill, "search_by_doi", lambda doi, sch: _record("T", "10.1/alpha", citations=4)
    )
    monkeypatch.setattr(papers_fill, "search_by_title", _must_not_call("search_by_title"))
    writes = []
    monkeypatch.setattr(papers_fill, "write_snapshot", lambda f, s: writes.append(f))
    path = _snapshot_file(
        tmp_path, [_agent("alpha-agent", paperMeta=_meta("10.1/alpha", "T Alpha", 4))]
    )

    stats = refresh_citations(path)

    assert stats["updated"] == 0 and stats["unchanged"] == 1
    assert writes == []


def test_refresh_citations_excludes_archived_gone_and_empty_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(papers_fill, "search_by_doi", _must_not_call("search_by_doi"))
    path = _snapshot_file(
        tmp_path,
        [
            _agent("old-agent", paperMeta=_meta("10.1/old", "T", 1), status="archived"),
            _agent("no-meta-agent"),
        ],
    )

    stats = refresh_citations(path)

    assert stats == {"updated": 0, "unchanged": 0, "unresolved": 0, "misses": []}


# --- arxiv_titles -------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: str):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload.encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def test_arxiv_titles_retries_rate_limit_and_maps_in_order(monkeypatch):
    rate_xml = "<feed><title>Rate exceeded.</title></feed>"
    ok_xml = (
        "<feed><title>ArXiv Query: id_list</title>"
        "<entry><title>First   Real  Title</title></entry>"
        "<entry><title>Error feed misbehaved</title></entry>"
        "</feed>"
    )
    responses = iter([_FakeResponse(rate_xml), _FakeResponse(ok_xml)])
    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        return next(responses)

    sleeps = []
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(papers_fill.time, "sleep", lambda s: sleeps.append(s))

    out = papers_fill.arxiv_titles(["2505.20286", "2401.00001"])

    # Titles collapse whitespace, map in request order; "Error…" entries and
    # the feed's own <title> are dropped.
    assert out == {"2505.20286": "First Real Title"}
    assert len(calls) == 2
    assert "id_list=2505.20286,2401.00001&max_results=2" in calls[0]
    assert sleeps == [5]  # backoff after the first rate-limited attempt


def test_arxiv_titles_empty_ids_makes_no_request():
    assert papers_fill.arxiv_titles([]) == {}


def test_sync_venue_tags_auto_slugs_unknown_journals(tmp_path):
    path = _snapshot_file(
        tmp_path,
        [
            _agent(
                "npj-agent",
                paperMeta={**_meta("", "ICDT paper", 1), "venue": "npj Health Systems"},
            ),
            _agent(
                "cancer-agent",
                paperMeta={**_meta("", "VT paper", 1), "venue": "Cancer Research"},
            ),
            _agent(
                "report-agent",
                paperMeta={**_meta("", "Report paper", 1), "venue": "Technical report"},
            ),
        ],
    )

    first = sync_venue_tags(path)
    assert first == {"updated": 2, "unknown_venues_skipped": 1}
    agents = _by_slug(path)
    assert agents["npj-agent"]["tags"] == ["npj-Health-Systems"]
    assert agents["cancer-agent"]["tags"] == ["Cancer-Research"]
    assert agents["report-agent"]["tags"] == []

    second = sync_venue_tags(path)
    assert second == {"updated": 0, "unknown_venues_skipped": 1}
