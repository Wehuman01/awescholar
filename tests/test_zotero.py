"""Tests for zotero.py — key resolution, item mapping, push classification, pull."""

import json

import pytest

from awescholar import zotero


def _item(key, item_type="journalArticle", title="A Paper", doi="10.1/x", **extra):
    data = {"itemType": item_type, "title": title, "DOI": doi}
    data.update(extra)
    return {"key": key, "data": data}


# ── date and creator mapping ─────────────────────────────────


def test_year_from_zotero_date():
    assert zotero._year_from_zotero_date("2026-04-01") == "2026.04"
    assert zotero._year_from_zotero_date("2026-4") == "2026.04"
    assert zotero._year_from_zotero_date("2026") == "2026"
    assert zotero._year_from_zotero_date("April 2026") == "2026"
    assert zotero._year_from_zotero_date("") == ""
    assert zotero._year_from_zotero_date(None) == ""


def test_zotero_date_from_year():
    assert zotero._zotero_date_from_year("2026.04") == "2026-04"
    assert zotero._zotero_date_from_year("2026") == "2026"
    assert zotero._zotero_date_from_year("") == ""


def test_authors_from_creators_prefers_authors_then_falls_back():
    creators = [
        {"creatorType": "editor", "name": "Ed Itor"},
        {"creatorType": "author", "firstName": "Ming", "lastName": "Xu"},
        {"creatorType": "author", "name": "Junhao Chen"},
    ]
    assert zotero._authors_from_creators(creators) == ["Ming Xu", "Junhao Chen"]
    assert zotero._authors_from_creators(
        [{"creatorType": "editor", "name": "Ed Itor"}]) == ["Ed Itor"]
    assert zotero._authors_from_creators(None) == []


# ── zotero item → pipeline record ────────────────────────────


def test_zotero_item_to_record_shape():
    item = _item(
        "JCE74496", item_type="preprint",
        title="Claw4Science: A Dataset and Platform",
        doi="10.64898/2026.03.30.715118",
        repository="bioRxiv", date="2026-04-01", url="https://www.biorxiv.org/x",
        abstractNote="We construct the first curated dataset.",
        creators=[{"creatorType": "author", "name": "Mingyang Xu"},
                  {"creatorType": "author", "name": "Zaixi Zhang"}])
    record = zotero.zotero_item_to_record(item)
    assert record["title"] == "Claw4Science: A Dataset and Platform"
    assert record["doi"] == "10.64898/2026.03.30.715118"
    assert record["venue"] == "bioRxiv"
    assert record["year"] == "2026.04"
    assert record["authors"] == ["Mingyang Xu", "Zaixi Zhang"]
    assert record["team"] == "Zaixi Zhang"
    assert record["paperUrl"] == "https://doi.org/10.64898/2026.03.30.715118"
    assert record["zoteroKey"] == "JCE74496"


def test_zotero_item_to_record_skips_notes_and_untitled():
    assert zotero.zotero_item_to_record(_item("N1", item_type="note")) is None
    assert zotero.zotero_item_to_record(_item("N2", title="")) is None


def test_zotero_item_to_record_url_fallback_without_doi():
    record = zotero.zotero_item_to_record(
        _item("K", doi="", url="https://example.com/paper"))
    assert record["paperUrl"] == "https://example.com/paper"
    assert record["doi"] == ""


# ── pipeline record → zotero item ────────────────────────────


def test_record_to_zotero_item_journal_and_preprint():
    record = {
        "title": "A Paper", "doi": "10.1038/x", "year": "2026.04",
        "venue": "Nature", "paperUrl": "https://doi.org/10.1038/x",
        "abstract": "abs", "authors": ["A B", "C D"],
    }
    item = zotero.record_to_zotero_item(record, "COLLKEY", tags=("AI Agents",))
    assert item["itemType"] == "journalArticle"
    assert item["publicationTitle"] == "Nature"
    assert item["date"] == "2026-04"
    assert item["creators"] == [
        {"creatorType": "author", "name": "A B"},
        {"creatorType": "author", "name": "C D"},
    ]
    assert item["collections"] == ["COLLKEY"]
    assert {"tag": "awescholar"} in item["tags"]
    assert {"tag": "AI Agents"} in item["tags"]

    preprint = {**record, "doi": "10.1101/2026.01.01.001", "venue": "bioRxiv"}
    item = zotero.record_to_zotero_item(preprint, "COLLKEY")
    assert item["itemType"] == "preprint"
    assert item["repository"] == "bioRxiv"
    assert "publicationTitle" not in item


# ── push classification ──────────────────────────────────────


def _fake_api(monkeypatch, *, collections=(), collection_items=(), library_items=(),
              created=None, key_user_id=12345):
    """Stub _request; record calls. Returns (calls, set_body_capture)."""
    calls = []

    def fake_request(path, api_key, *, method="GET", body=None, write_token=None,
                     timeout=20):
        calls.append((method, path, body))
        route = path.split("?")[0]
        if route.startswith("/keys/"):
            return 200, {"userID": key_user_id}
        if route.endswith("/collections") and method == "GET":
            return 200, list(collections)
        if "/collections/" in route and route.endswith("/items/top"):
            return 200, list(collection_items)
        if route.endswith("/items/top"):
            return 200, list(library_items)
        if method == "POST" and route.endswith("/collections"):
            return 201, {"success": {"0": "NEWCOLL"}}
        if method == "POST" and route.endswith("/items"):
            return 200, {"success": {str(i): f"KEY{i}"
                                     for i in range(len(body or []))}}
        return 404, None

    monkeypatch.setattr(zotero, "_request", fake_request)
    return calls


def test_resolve_library_user_key_autodiscovery(monkeypatch):
    calls = _fake_api(monkeypatch)
    assert zotero.resolve_library("KEY", "user", None) == "/users/12345"
    assert calls[0][1] == "/keys/KEY"


def test_resolve_library_group_requires_id():
    with pytest.raises(ValueError, match="library_id"):
        zotero.resolve_library("KEY", "group", None)


def test_push_dry_run_classifies_and_writes_review(monkeypatch, tmp_path):
    collection = {"key": "COLL1", "data": {"name": "Monthly"}}
    # LIB1: same DOI → in collection. LIB2: title match → in library elsewhere.
    calls = _fake_api(
        monkeypatch,
        collections=[collection],
        collection_items=[_item("LIB1", doi="10.1/a")],
        library_items=[
            _item("LIB1", doi="10.1/a", title="Alpha"),
            _item("LIB2", doi="", title="Beta Paper"),
        ])
    records = [
        ("AI Agents", {"title": "Alpha", "doi": "10.1/a"}),
        ("AI Agents", {"title": "Beta Paper", "doi": ""}),
        ("Reviews", {"title": "Gamma", "doi": "10.1/g"}),
    ]
    review = tmp_path / "zotero_review.json"
    result = zotero.push_records(
        records, "Monthly", "KEY", review_path=str(review))

    assert result["counts"] == {"already-in-collection": 1, "in-library": 1,
                                "to-add": 1}
    assert result["created"] == 0
    saved = json.loads(review.read_text(encoding="utf-8"))
    assert [entry["status"] for entry in saved] == [
        "already-in-collection", "in-library", "to-add"]
    assert saved[2]["category"] == "Reviews"
    # A dry run never writes: every call is a GET.
    assert all(method == "GET" for method, _path, _body in calls)


def test_push_apply_creates_only_new_items(monkeypatch, tmp_path):
    collection = {"key": "COLL1", "data": {"name": "Monthly"}}
    calls = _fake_api(monkeypatch, collections=[collection], library_items=[
        _item("LIB1", doi="10.1/a", title="Alpha")])
    records = [
        ("AI Agents", {"title": "Alpha", "doi": "10.1/a"}),
        ("AI Agents", {"title": "New One", "doi": "10.1/n", "year": "2026.04",
                       "venue": "Nature", "authors": ["A B"]}),
    ]
    review = tmp_path / "zotero_review.json"
    result = zotero.push_records(
        records, "Monthly", "KEY", apply=True, review_path=str(review))

    assert result["created"] == 1
    posts = [body for method, path, body in calls if method == "POST"
             and path.endswith("/items")]
    assert len(posts) == 1
    posted = posts[0][0]
    assert posted["title"] == "New One"
    assert posted["collections"] == ["COLL1"]
    assert {"tag": "awescholar"} in posted["tags"]
    assert {"tag": "AI Agents"} in posted["tags"]


def test_push_apply_creates_missing_collection(monkeypatch, tmp_path):
    calls = _fake_api(monkeypatch)
    records = [("AI Agents", {"title": "New One", "doi": "10.1/n"})]
    result = zotero.push_records(
        records, "Brand New", "KEY", apply=True,
        review_path=str(tmp_path / "r.json"))
    assert result["collectionKey"] == "NEWCOLL"
    assert result["created"] == 1
    assert any(method == "POST" and path.endswith("/collections")
               for method, path, _body in calls)


# ── pull ─────────────────────────────────────────────────────


def test_pull_collection_maps_records(monkeypatch):
    collection = {"key": "COLL1", "data": {"name": "Reading List"}}
    _fake_api(
        monkeypatch,
        collections=[collection],
        collection_items=[
            _item("A", doi="10.1/a", title="Alpha", date="2026-01-15"),
            _item("B", item_type="note", title=""),  # defense-in-depth drop
        ])
    result = zotero.pull_collection("Reading List", "KEY")
    assert result["category"] == "Zotero"
    assert len(result["records"]) == 1
    assert result["records"][0]["title"] == "Alpha"
    assert result["records"][0]["year"] == "2026.01"


def test_pull_collection_missing_raises(monkeypatch):
    _fake_api(monkeypatch)
    with pytest.raises(ValueError, match="not found"):
        zotero.pull_collection("Nope", "KEY")


def test_pull_respects_category_and_limit(monkeypatch):
    collection = {"key": "COLL1", "data": {"name": "List"}}
    _fake_api(
        monkeypatch,
        collections=[collection],
        collection_items=[_item(f"K{i}", title=f"P{i}", doi=f"10.1/{i}")
                          for i in range(5)])
    result = zotero.pull_collection("List", "KEY", category="AI Agents", limit=2)
    assert result["category"] == "AI Agents"
    assert [r["title"] for r in result["records"]] == ["P0", "P1"]


def test_pagination_follows_start(monkeypatch):
    pages = {
        0: [_item(f"K{i}", title=f"P{i}", doi=f"10.1/{i}") for i in range(100)],
        100: [_item("LAST", title="LAST", doi="10.1/last")],
    }

    def fake_request(path, api_key, *, method="GET", body=None,
                     write_token=None, timeout=20):
        if "start=100" in path:
            return 200, pages[100]
        if "start=0" in path:
            return 200, pages[0]
        return 200, []

    monkeypatch.setattr(zotero, "_request", fake_request)
    items = zotero.fetch_library_items("/users/1", "KEY")
    assert len(items) == 101
    assert items[-1]["key"] == "LAST"
