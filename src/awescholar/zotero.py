"""Zotero Web API exchange: pull a collection into pipeline JSON, push an archive into one.

Thin stdlib-urllib client in the github.py best-effort style. The Zotero
library is the reader's personal store, so writes are conservative: push is a
dry run by default, item creation goes through single-shot Zotero-Write-Token
posts, and duplicate matching reuses the archive's identity rules (exact DOI,
then normalized title).
"""

import json
import re
import sys
import urllib.error
import urllib.request
import uuid

from .archive import is_preprint
from .data_fields import normalize_title

API_BASE = "https://api.zotero.org"
API_VERSION = "3"
USER_AGENT = "awescholar (https://github.com/wehuman01/awescholar)"
PAGE_LIMIT = 100
# Zotero caps one write post at 50 items.
WRITE_BATCH = 50
TIMEOUT_SECONDS = 20

DEFAULT_REVIEW_FILENAME = "zotero_review.json"
DEFAULT_PULL_FILENAME = "zotero_papers.json"
DEFAULT_PULL_CATEGORY = "Zotero"

_4DIGIT_YEAR_RE = re.compile(r"(\d{4})(?:[-/](\d{1,2}))?")


def _request(path: str, api_key: str, *, method: str = "GET", body=None,
             write_token: str | None = None, timeout: float = TIMEOUT_SECONDS):
    """One Zotero API call. Returns (status, parsed_json_or_None)."""
    headers = {
        "Zotero-API-Version": API_VERSION,
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {api_key}",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if write_token:
        headers["Zotero-Write-Token"] = write_token
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            print(f"Warning: Zotero API denied {path} (HTTP {exc.code}) — bad key or "
                  "rate limit; nothing was written.", file=sys.stderr)
        return exc.code, None
    except Exception:  # noqa: BLE001 — network hiccups are normal outcomes, never fatal silently
        return 0, None


def resolve_library(api_key: str, library_type: str, library_id: str | None) -> str:
    """Return the API path prefix ('/users/12345' or '/groups/67890').

    A user library needs no configured id: the key itself knows its owner via
    /keys/. A group library must name its id explicitly.
    """
    if library_type not in ("user", "group"):
        raise ValueError("zotero.library_type must be 'user' or 'group'")
    if library_id:
        return f"/{library_type}s/{library_id}"
    if library_type == "group":
        raise ValueError("a group library needs zotero.library_id")
    status, data = _request(f"/keys/{api_key}", api_key)
    if status != 200 or not (data or {}).get("userID"):
        raise ValueError(
            "could not resolve the Zotero user id from the API key — "
            "check zotero.api_key or set zotero.library_id")
    return f"/users/{data['userID']}"


def _paginate(path: str, api_key: str) -> list[dict]:
    """Follow limit/start pagination; each page returns up to PAGE_LIMIT items."""
    items = []
    start = 0
    while True:
        sep = "&" if "?" in path else "?"
        status, data = _request(
            f"{path}{sep}format=json&limit={PAGE_LIMIT}&start={start}", api_key)
        if status != 200 or not isinstance(data, list):
            if start == 0:
                print(f"Warning: Zotero fetch failed for {path} "
                      f"(HTTP {status}).", file=sys.stderr)
            break
        items.extend(data)
        if len(data) < PAGE_LIMIT:
            return items
        start += PAGE_LIMIT
    return items


def fetch_collections(lib: str, api_key: str) -> list[dict]:
    return _paginate(f"{lib}/collections", api_key)


def find_collection(lib: str, name: str, api_key: str) -> dict | None:
    """First collection whose name matches exactly, case-insensitively."""
    lowered = name.strip().lower()
    for coll in fetch_collections(lib, api_key):
        if str((coll.get("data") or {}).get("name") or "").strip().lower() == lowered:
            return coll
    return None


def create_collection(lib: str, name: str, api_key: str) -> str | None:
    """Create one top-level collection; returns its key, or None on failure."""
    status, data = _request(
        f"{lib}/collections", api_key, method="POST", body=[{"name": name}],
        write_token=uuid.uuid4().hex)
    key = None
    if status in (200, 201) and data:
        key = (data.get("success") or {}).get("0")
    if not key:
        print(f"Warning: failed to create Zotero collection '{name}' "
              f"(HTTP {status}).", file=sys.stderr)
    return key


def fetch_collection_items(lib: str, collection_key: str, api_key: str) -> list[dict]:
    """Top-level items of one collection (attachments and notes excluded)."""
    return _paginate(f"{lib}/collections/{collection_key}/items/top", api_key)


def fetch_library_items(lib: str, api_key: str) -> list[dict]:
    """Every top-level item of the library — the push-side dedupe universe."""
    return _paginate(f"{lib}/items/top", api_key)


def _year_from_zotero_date(value) -> str:
    """'2026-04-01' -> '2026.04'; 'April 2026' or '2026' -> '2026'; junk -> ''."""
    match = _4DIGIT_YEAR_RE.search(str(value or ""))
    if not match:
        return ""
    year, month = match.group(1), match.group(2)
    return f"{year}.{int(month):02d}" if month else year


def _zotero_date_from_year(value) -> str:
    """'2026.04' -> '2026-04'; anything else passes through untouched."""
    match = re.fullmatch(r"(\d{4})\.(\d{2})", str(value or ""))
    return f"{match.group(1)}-{match.group(2)}" if match else str(value or "")


def _authors_from_creators(creators) -> list[str]:
    """Author names from Zotero creators; non-author creators only when no author exists."""
    rows = creators if isinstance(creators, list) else []
    names = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or " ".join(
            part for part in (row.get("firstName"), row.get("lastName")) if part)
        if name:
            names.append((row.get("creatorType") == "author", name))
    authors = [name for is_author, name in names if is_author]
    return authors or [name for _is_author, name in names]


def zotero_item_to_record(item: dict) -> dict | None:
    """Map a Zotero item JSON to the pipeline record shape (see record.py).

    Extra 'zoteroKey' and 'abstract' fields ride along for inspection; the
    updater's normalize step strips them before anything reaches data.json.
    """
    data = item.get("data") or {}
    title = str(data.get("title") or "").strip()
    if not title or data.get("itemType") in ("attachment", "note"):
        return None
    authors = _authors_from_creators(data.get("creators"))
    doi = str(data.get("DOI") or "").strip()
    venue = (data.get("publicationTitle") or data.get("repository")
             or data.get("proceedingsTitle") or data.get("publisher") or "")
    return {
        "year": _year_from_zotero_date(data.get("date")),
        "title": title,
        "team": authors[-1] if authors else "",
        "authors": authors,
        "team website": "",
        "affiliation": "",
        "domain": "",
        "venue": str(venue or ""),
        # DOI links are canonical; the stored URL is the fallback (record.py rule).
        "paperUrl": f"https://doi.org/{doi}" if doi else str(data.get("url") or ""),
        "codeUrl": "",
        "githubStars": "",
        "citations": None,
        "doi": doi,
        "abstract": str(data.get("abstractNote") or ""),
        "zoteroKey": item.get("key", ""),
    }


def record_to_zotero_item(record: dict, collection_key: str, tags=()) -> dict:
    """Map a pipeline record to a Zotero item template carrying one collection."""
    item_type = "preprint" if is_preprint(record) else "journalArticle"
    item = {
        "itemType": item_type,
        "title": str(record.get("title") or ""),
        "creators": [
            {"creatorType": "author", "name": name}
            for name in (record.get("authors") or []) if name
        ],
        "DOI": str(record.get("doi") or ""),
        "url": str(record.get("paperUrl") or ""),
        "date": _zotero_date_from_year(record.get("year")),
        "abstractNote": str(record.get("abstract") or ""),
        # Single-field creators keep names verbatim — no invented name splitting.
        "tags": [{"tag": tag} for tag in ("awescholar", *tags) if tag],
        "collections": [collection_key],
    }
    venue = str(record.get("venue") or "")
    if item_type == "preprint":
        item["repository"] = venue
    else:
        item["publicationTitle"] = venue
    return item


def create_items(lib: str, items: list[dict], api_key: str) -> tuple[int, list[str]]:
    """Create items in single-shot batches. Returns (created_count, failures)."""
    created = 0
    failures: list[str] = []
    for start in range(0, len(items), WRITE_BATCH):
        batch = items[start:start + WRITE_BATCH]
        status, data = _request(
            f"{lib}/items", api_key, method="POST", body=batch,
            write_token=uuid.uuid4().hex)
        if status not in (200, 201) or not data:
            failures.append(f"batch of {len(batch)} rejected (HTTP {status})")
            continue
        created += len(data.get("success") or {})
        for index, reason in (data.get("failure") or {}).items():
            title = batch[int(index)].get("title", "?") if index.isdigit() else "?"
            failures.append(f"{title}: {json.dumps(reason, ensure_ascii=False)}")
    return created, failures


def _identity(doi_value, title_value) -> tuple[str, str]:
    return (str(doi_value or "").strip(), normalize_title(title_value))


def push_records(records: list[tuple[str, dict]], collection_name: str, api_key: str,
                 library_type: str = "user", library_id: str | None = None, *,
                 apply: bool = False, tags=(), review_path: str | None = None) -> dict:
    """Push archive records into a Zotero collection.

    Every record is classified against the whole library by DOI then
    normalized title: 'already-in-collection' (no-op), 'in-library' (exists
    elsewhere — held back, membership is never forced), or 'to-add'. The dry
    run writes the classified queue to a review file; --apply rescans and
    creates the 'to-add' items (idempotent — created items classify as
    already-in-collection on rerun).
    """
    lib = resolve_library(api_key, library_type, library_id)
    collection = find_collection(lib, collection_name, api_key)
    collection_key = None
    if collection:
        collection_key = collection.get("key")
    elif apply:
        collection_key = create_collection(lib, collection_name, api_key)
        if collection_key:
            print(f"Created Zotero collection '{collection_name}'")

    in_collection_keys: set[str] = set()
    if collection_key:
        in_collection_keys = {
            item.get("key", "") for item in
            fetch_collection_items(lib, collection_key, api_key)}

    doi_index: dict[str, dict] = {}
    title_index: dict[str, dict] = {}
    for item in fetch_library_items(lib, api_key):
        data = item.get("data") or {}
        if data.get("itemType") in ("attachment", "note"):
            continue
        doi, title = _identity(data.get("DOI"), data.get("title"))
        if doi:
            doi_index.setdefault(doi, item)
        if title:
            title_index.setdefault(title, item)

    def _find(doi: str, title: str) -> dict | None:
        if doi and doi in doi_index:
            return doi_index[doi]
        return title_index.get(title) if title else None

    review = []
    for category, record in records:
        doi, title = _identity(record.get("doi"), record.get("title"))
        hit = _find(doi, title)
        if hit is not None:
            status = ("already-in-collection" if hit.get("key") in in_collection_keys
                      else "in-library")
            review.append({
                "status": status,
                "category": category,
                "title": record.get("title"),
                "doi": record.get("doi"),
                "zoteroKey": hit.get("key"),
                "zoteroTitle": (hit.get("data") or {}).get("title"),
            })
            continue
        review.append({
            "status": "to-add",
            "category": category,
            "paper": record,
        })

    counts: dict[str, int] = {}
    for entry in review:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    to_add = [entry for entry in review if entry["status"] == "to-add"]

    path = review_path or DEFAULT_REVIEW_FILENAME
    if to_add or not apply:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(review, f, indent=2, ensure_ascii=False)

    created = 0
    failures: list[str] = []
    if apply and collection_key and to_add:
        items = [
            record_to_zotero_item(entry["paper"], collection_key,
                                  tags=(*tags, entry["category"]))
            for entry in to_add]
        created, failures = create_items(lib, items, api_key)

    return {
        "library": lib,
        "collection": collection_name,
        "collectionKey": collection_key,
        "counts": counts,
        "reviewPath": path if (to_add or not apply) else None,
        "created": created,
        "failures": failures,
    }


def pull_collection(collection_name: str, api_key: str,
                    library_type: str = "user", library_id: str | None = None, *,
                    category: str = DEFAULT_PULL_CATEGORY,
                    limit: int | None = None) -> dict:
    """Map one Zotero collection into a {category: [records]} pipeline file.

    The output feeds 'updater update --direction new2old' unchanged; the
    archive's own dedupe handles preprint/published twins inside the pull.
    """
    lib = resolve_library(api_key, library_type, library_id)
    collection = find_collection(lib, collection_name, api_key)
    if collection is None:
        raise ValueError(
            f"Zotero collection '{collection_name}' not found in {lib} "
            "(pull never creates one)")
    records = []
    for item in fetch_collection_items(lib, collection["key"], api_key):
        record = zotero_item_to_record(item)
        if record is not None:
            records.append(record)
    if limit:
        records = records[:limit]
    return {"category": category, "records": records}
