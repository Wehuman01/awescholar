"""Tests for zotero_pdf.py — PoW solving, OA candidates, download policy, connector flow."""

import hashlib
import json

import pytest

from awescholar import zotero_pdf

FAKE_PDF = b"%PDF-1.7\n" + b"x" * zotero_pdf.MIN_PDF_BYTES


class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body if isinstance(body, bytes) else body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# ── proof-of-work ─────────────────────────────────────────────


def test_solve_pow_finds_nonce_with_leading_zeros():
    nonce = zotero_pdf.solve_pow("challenge", 1)
    digest = hashlib.sha256(f"challenge{nonce}".encode()).hexdigest()
    assert digest.startswith("0")
    # Smaller nonces must not qualify — the solver returns the first hit.
    for n in range(nonce):
        assert not hashlib.sha256(f"challenge{n}".encode()).hexdigest().startswith("0")


def test_parse_pow_interstitial_extracts_constants():
    html = (
        '<script type="module">\n'
        '    const POW_CHALLENGE = "VwR3BGN5ZQV4ZwxhAwx2Zwp3Vt:HYmS_qK2Qo"\n'
        '    const POW_DIFFICULTY = "4"\n'
        "    window.ncbi.pmc.pow.init(POW_CHALLENGE, POW_DIFFICULTY);\n"
        "</script>"
    )
    challenge, difficulty = zotero_pdf.parse_pow_interstitial(html)
    assert challenge == "VwR3BGN5ZQV4ZwxhAwx2Zwp3Vt:HYmS_qK2Qo"
    assert difficulty == 4


def test_parse_pow_interstitial_rejects_plain_pages():
    assert zotero_pdf.parse_pow_interstitial("<html><body>article</body></html>") is None
    assert zotero_pdf.parse_pow_interstitial("") is None


# ── PDF validation and OA candidates ──────────────────────────


def test_is_pdf_magic_and_floor():
    assert zotero_pdf.is_pdf(FAKE_PDF)
    assert not zotero_pdf.is_pdf(b"%PDF-1.7\n" + b"x" * 100)  # too small
    assert not zotero_pdf.is_pdf(b"<html>" + b"x" * zotero_pdf.MIN_PDF_BYTES)


def test_arxiv_pdf_url_from_datacite_doi():
    assert (zotero_pdf.arxiv_pdf_url("10.48550/arXiv.2505.10468")
            == "https://arxiv.org/pdf/2505.10468")
    assert zotero_pdf.arxiv_pdf_url("10.1038/s41586-025-00001-x") is None
    assert zotero_pdf.arxiv_pdf_url("") is None


def test_unpaywall_urls_direct_links_before_landing_pages(monkeypatch):
    payload = json.dumps({
        "best_oa_location": {"url": "https://doi.org/10.1145/x"},
        "oa_locations": [
            {"url": "https://doi.org/10.1145/x"},
            {"url_for_pdf": "https://arxiv.org/pdf/2502.05151", "url": "https://arxiv.org/abs/2502.05151"},
        ]})

    def fake_urlopen(req, timeout=None):
        return _FakeResponse(200, payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert zotero_pdf.unpaywall_pdf_urls("10.1145/x", "a@b.c") == [
        "https://arxiv.org/pdf/2502.05151", "https://doi.org/10.1145/x"]


def test_unpaywall_urls_swallows_failures(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise OSError("down")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert zotero_pdf.unpaywall_pdf_urls("10.1/x", "a@b.c") == []


def test_candidate_urls_order_and_no_email(monkeypatch):
    monkeypatch.setattr(zotero_pdf, "unpaywall_pdf_urls",
                        lambda doi, email: ["https://x.org/a.pdf"])
    record = {"doi": "10.48550/arXiv.2505.10468"}
    assert zotero_pdf.candidate_pdf_urls(record, "a@b.c") == [
        "https://x.org/a.pdf", "https://arxiv.org/pdf/2505.10468"]
    # Without an email Unpaywall is skipped entirely; arXiv DOI still resolves.
    assert zotero_pdf.candidate_pdf_urls(record, None) == [
        "https://arxiv.org/pdf/2505.10468"]
    assert zotero_pdf.candidate_pdf_urls({"doi": ""}, "a@b.c") == []


def test_candidate_urls_green_twin_behind_journal_doi(monkeypatch):
    """Journal DOI whose publisher copy is a landing page: the arXiv twin
    arrives both through Unpaywall locations and the record's arXiv id."""
    monkeypatch.setattr(zotero_pdf, "unpaywall_pdf_urls", lambda doi, email: [])
    record = {"doi": "10.1145/3845596", "arxiv": "2502.05151"}
    assert zotero_pdf.candidate_pdf_urls(record, "a@b.c") == [
        "https://arxiv.org/pdf/2502.05151"]

    # Unpaywall's direct links stay ahead of the twin.
    monkeypatch.setattr(
        zotero_pdf, "unpaywall_pdf_urls",
        lambda doi, email: ["https://dl.acm.org/a.pdf", "https://doi.org/10.1145/3845596"])
    assert zotero_pdf.candidate_pdf_urls(record, "a@b.c") == [
        "https://dl.acm.org/a.pdf", "https://doi.org/10.1145/3845596",
        "https://arxiv.org/pdf/2502.05151"]


# ── download policy ───────────────────────────────────────────


def test_download_pdf_plain_url(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(200, FAKE_PDF)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert zotero_pdf.download_pdf("https://example.org/paper.pdf") == FAKE_PDF


def test_download_pdf_springer_sends_accept_header(monkeypatch):
    seen = []

    def fake_urlopen(req, timeout=None):
        seen.append(req)
        return _FakeResponse(200, FAKE_PDF)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    zotero_pdf.download_pdf("https://link.springer.com/content/pdf/10.1007%2Fx.pdf")
    assert seen[0].get_header("Accept") == "application/pdf"
    assert seen[0].get_header("User-agent") == zotero_pdf.BROWSER_UA


INTERSTITIAL = (
    "<title>Preparing to download ...</title>\n"
    '<script>const POW_CHALLENGE = "abc123"\n'
    'const POW_DIFFICULTY = "1"\n</script>'
)


def test_download_pdf_pmc_pow_roundtrip(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req)
        # First hit: HTML interstitial. Second hit (with the cookie): the PDF.
        if len(calls) == 1:
            return _FakeResponse(200, INTERSTITIAL)
        return _FakeResponse(200, FAKE_PDF)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC13017847/pdf/bbag110.pdf"
    assert zotero_pdf.download_pdf(url) == FAKE_PDF

    nonce = zotero_pdf.solve_pow("abc123", 1)
    retry = calls[1]
    assert retry.get_header("Cookie") == f"cloudpmc-viewer-pow=abc123,{nonce}"
    assert retry.get_header("Referer") == "https://pmc.ncbi.nlm.nih.gov/articles/PMC13017847/"


def test_download_pdf_pmc_unsolvable_page_returns_none(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(200, "<html>some other page</html>")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/pdf/x.pdf"
    assert zotero_pdf.download_pdf(url) is None


def test_download_pdf_html_junk_returns_none(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(200, "<html>blocked</html>")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert zotero_pdf.download_pdf("https://example.org/paper.pdf") is None


# ── connector mapping and session flow ────────────────────────


def _record(**overrides):
    record = {
        "title": "A Paper", "doi": "10.1038/x", "year": "2026.04",
        "venue": "Nature", "paperUrl": "https://doi.org/10.1038/x",
        "abstract": "abs", "authors": ["A B", "C D"],
    }
    record.update(overrides)
    return record


def test_record_to_connector_item_journal_and_preprint():
    item = zotero_pdf.record_to_connector_item(_record(), "awescholar-0")
    assert item["itemType"] == "journalArticle"
    assert item["publicationTitle"] == "Nature"
    assert item["date"] == "2026-04"
    assert item["creators"] == [
        {"creatorType": "author", "name": "A B"},
        {"creatorType": "author", "name": "C D"},
    ]
    assert item["abstractNote"] == "abs"
    assert {"tag": "awescholar"} in item["tags"]

    preprint = _record(doi="10.1101/2026.01.01.001", venue="bioRxiv")
    item = zotero_pdf.record_to_connector_item(preprint, "awescholar-1")
    assert item["itemType"] == "preprint"
    assert item["repository"] == "bioRxiv"
    assert "publicationTitle" not in item


def test_attachment_title_sanitizes_and_truncates():
    title = zotero_pdf.attachment_title(
        _record(title="Alpha/beta " + "long " * 40, authors=["Ming Xu"], year="2026.04"))
    assert title.startswith("Ming Xu - 2026 - Alpha-beta")
    assert "/" not in title
    assert title.endswith(".pdf")
    assert len(title) < 140


def _fake_connector(monkeypatch, *, selected=None, statuses=None):
    """Stub _connector_call; route by path. Returns the captured (path, body) calls."""
    calls = []

    def fake_call(path, *, json_body=None, raw_body=None, headers=None):
        calls.append((path, json_body, raw_body, headers))
        if path == "/connector/ping":
            return 200, {}
        if path == "/connector/getSelectedCollection":
            return (200, selected) if selected else (0, None)
        if statuses:
            return statuses.pop(0), {}
        return 201, {}

    monkeypatch.setattr(zotero_pdf, "_connector_call", fake_call)
    return calls


def test_selected_target_builds_c_target_and_guards_collection(monkeypatch):
    _fake_connector(monkeypatch, selected={"id": 565, "name": "agentx_paper",
                                           "libraryID": 1, "libraryName": "My Library"})
    assert zotero_pdf.selected_target("Agentx_Paper ") == ("C565", "agentx_paper")

    with pytest.raises(ValueError, match="selected destination is 'agentx_paper'"):
        zotero_pdf.selected_target("other")


def test_selected_target_library_fallback_and_unreachable(monkeypatch):
    _fake_connector(monkeypatch, selected={"id": None, "libraryID": 1,
                                           "libraryName": "My Library"})
    assert zotero_pdf.selected_target(None) == ("L1", "My Library")

    _fake_connector(monkeypatch, selected=None)
    with pytest.raises(ValueError, match="running"):
        zotero_pdf.selected_target(None)


def test_save_to_zotero_one_session_two_attachments(monkeypatch):
    calls = _fake_connector(monkeypatch, selected={"id": 9, "name": "Papers",
                                                   "libraryID": 1, "libraryName": "My Library"})
    result = zotero_pdf.save_to_zotero(
        [(_record(), FAKE_PDF), (_record(title="Second", doi="10.1/y"), FAKE_PDF)],
        "Papers")

    assert result == {"destination": "Papers", "created": 2, "attached": 2, "failures": 0}
    save = next(c for c in calls if c[0] == "/connector/saveItems")
    session_id = save[1]["sessionID"]
    assert save[1]["target"] == "C9"
    assert len(save[1]["items"]) == 2

    attachments = [c for c in calls if c[0] == "/connector/saveAttachment"]
    assert attachments[0][2] == FAKE_PDF  # raw PDF bytes in the request body
    import json
    metadata = json.loads(attachments[0][3]["X-Metadata"])
    assert metadata["sessionID"] == session_id
    assert metadata["parentItemID"] == "awescholar-0"
    assert metadata["title"].endswith(".pdf")


# ── command core ──────────────────────────────────────────────


def test_run_out_mode_writes_files(monkeypatch, tmp_path):
    import awescholar.record as record_mod

    monkeypatch.setattr(record_mod, "_get_client", lambda key=None: object())
    monkeypatch.setattr(record_mod, "search_by_title",
                        lambda q, sch: _record(title=f"Paper {q}"))
    monkeypatch.setattr(zotero_pdf, "find_pdf", lambda rec, email: ("https://x.org/a.pdf", FAKE_PDF))

    out = tmp_path / "pdfs"
    stats = zotero_pdf.run(["query one"], by="title", out_dir=str(out),
                           unpaywall_email="a@b.c")

    assert stats == {"resolved": 1, "not_found": 0, "no_pdf": 0, "written": 1}
    files = list(out.iterdir())
    assert len(files) == 1
    assert files[0].read_bytes() == FAKE_PDF


def test_run_attach_mode_reports_dead_connector(monkeypatch, capsys):
    import awescholar.record as record_mod

    monkeypatch.setattr(record_mod, "_get_client", lambda key=None: object())
    monkeypatch.setattr(record_mod, "search_by_title", lambda q, sch: _record())
    monkeypatch.setattr(zotero_pdf, "find_pdf", lambda rec, email: ("https://x.org/a.pdf", FAKE_PDF))
    monkeypatch.setattr(zotero_pdf, "connector_alive", lambda: False)

    stats = zotero_pdf.run(["query"], by="title", unpaywall_email="a@b.c")

    assert stats["zotero"] == {"created": 0, "attached": 0, "failures": 1}
    assert "not reachable" in capsys.readouterr().err


def test_run_counts_not_found_and_no_pdf(monkeypatch, tmp_path):
    import awescholar.record as record_mod

    monkeypatch.setattr(record_mod, "_get_client", lambda key=None: object())
    monkeypatch.setattr(record_mod, "search_by_title", lambda q, sch: None)
    monkeypatch.setattr(zotero_pdf, "find_pdf", lambda rec, email: (None, None))

    stats = zotero_pdf.run(["missing"], by="title", out_dir=str(tmp_path / "o"),
                           unpaywall_email="a@b.c")
    assert stats["not_found"] == 1

    monkeypatch.setattr(record_mod, "search_by_title", lambda q, sch: _record())
    stats = zotero_pdf.run(["closed access"], by="title", out_dir=str(tmp_path / "o"),
                           unpaywall_email="a@b.c")
    assert stats == {"resolved": 1, "not_found": 0, "no_pdf": 1, "written": 0}
