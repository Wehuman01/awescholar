"""Open-access PDF retrieval: query → OA link → validated bytes → Zotero or file.

One core, two landings. A title or DOI resolves to a pipeline record via
Semantic Scholar (record.py's single-paper lookups); the record's DOI
resolves to an open-access PDF through Unpaywall, with arXiv DOIs mapped
directly; the bytes are validated by PDF magic and minimum size, then
either written into a directory (``--out``, no Zotero involved) or saved
into the running Zotero desktop through its connector server — the same
protocol the browser extension speaks (saveItems + saveAttachment).

Two honest limits shape the design:

- The connector attaches PDFs only to items from its own save session,
  so attach mode always creates the item; it cannot backfill a PDF onto
  an item that already exists in the library (use ``--out`` + drag for
  that).
- The connector saves into whatever collection is selected in the
  Zotero pane, exactly like the browser extension; ``--collection``
  only verifies that selection and refuses on a mismatch.

Publisher quirks live in one place (``download_pdf``): Springer serves
PDF bytes only when the retry carries ``Accept: application/pdf``, and
pmc.ncbi.nlm.nih.gov fronts its PDFs with a proof-of-work interstitial
whose challenge is solved locally (sha256 with N leading zeros) and
presented as the ``cloudpmc-viewer-pow`` cookie.

Boundary against downloader.py (`updater download`): that one is the
archive-batch flow over OpenAlex links and treats bot-gated publishers
as honest failures; this one resolves single papers from arbitrary
queries and pushes through the gates the batch flow declines.
"""

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid

from .archive import is_preprint
from .zotero import _zotero_date_from_year

CONNECTOR_BASE = "http://localhost:23119"
CONNECTOR_API_VERSION = "3"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
DOWNLOAD_TIMEOUT = 60
CONNECTOR_TIMEOUT = 30
MIN_PDF_BYTES = 10_000
# Publisher sites rate-limit or route plain-client UAs to HTML walls.
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36")

_POW_CHALLENGE_RE = re.compile(r'POW_CHALLENGE\s*=\s*"([^"]+)"')
_POW_DIFFICULTY_RE = re.compile(r'POW_DIFFICULTY\s*=\s*"(\d+)"')
_PMC_PDF_PATH_RE = re.compile(r"^(/articles/PMC\d+/pdf/.+)$")
_ARXIV_DOI_RE = re.compile(r"^10\.48550/arXiv\.(.+)$")


# ── proof-of-work (PMC's PDF gate) ────────────────────────────


def solve_pow(challenge: str, difficulty: int) -> int:
    """Smallest nonce whose sha256(challenge + nonce) hex leads with `difficulty` zeros."""
    prefix = "0" * difficulty
    nonce = 0
    while True:
        digest = hashlib.sha256(f"{challenge}{nonce}".encode()).hexdigest()
        if digest.startswith(prefix):
            return nonce
        nonce += 1


def parse_pow_interstitial(html: str) -> tuple[str, int] | None:
    """(challenge, difficulty) from a 'Preparing to download …' page, or None."""
    challenge = _POW_CHALLENGE_RE.search(html)
    difficulty = _POW_DIFFICULTY_RE.search(html)
    if not challenge or not difficulty:
        return None
    return challenge.group(1), int(difficulty.group(1))


def is_pdf(data: bytes) -> bool:
    """Plausible PDF: magic bytes plus a floor that rules out error pages."""
    return len(data) >= MIN_PDF_BYTES and data[:5] == b"%PDF-"


# ── OA link resolution ────────────────────────────────────────


def arxiv_pdf_url(doi: str) -> str | None:
    """DataCite arXiv DOI → direct PDF link (works for every arXiv paper)."""
    match = _ARXIV_DOI_RE.match(str(doi or "").strip())
    return f"https://arxiv.org/pdf/{match.group(1)}" if match else None


def unpaywall_pdf_url(doi: str, email: str) -> str | None:
    """Best OA location from Unpaywall; None on any failure or closed access."""
    url = f"{UNPAYWALL_BASE}/{doi}?email={email}"
    req = urllib.request.Request(url, headers={"User-Agent": "awescholar"})
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None
    location = (data.get("best_oa_location") or {})
    return location.get("url_for_pdf") or location.get("url") or None


def candidate_pdf_urls(record: dict, email: str | None) -> list[str]:
    """Ordered, de-duplicated candidates: Unpaywall first, arXiv DOI second."""
    doi = str(record.get("doi") or "").strip()
    if not doi:
        return []
    candidates: list[str] = []
    if email:
        url = unpaywall_pdf_url(doi, email)
        if url:
            candidates.append(url)
    url = arxiv_pdf_url(doi)
    if url:
        candidates.append(url)
    return list(dict.fromkeys(candidates))


# ── download with per-publisher handling ──────────────────────


def _http_get(url: str, *, headers: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, OSError):
        return 0, b""


def _pmc_referer(url: str) -> str:
    """/articles/PMC123/pdf/x.pdf → the article page the PDF hangs off."""
    path = re.sub(r"^https?://[^/]+", "", url).split("?")[0]
    match = _PMC_PDF_PATH_RE.match(path)
    if match:
        return f"https://pmc.ncbi.nlm.nih.gov{match.group(1).rsplit('/pdf/', 1)[0]}/"
    return "https://pmc.ncbi.nlm.nih.gov/"


def download_pdf(url: str) -> bytes | None:
    """One candidate URL → validated PDF bytes, or None.

    Handles the two publishers that do not serve PDFs to a plain request:
    link.springer.com (retry with ``Accept: application/pdf``) and
    pmc.ncbi.nlm.nih.gov (solve the PoW interstitial, retry with the cookie).
    """
    headers: dict[str, str] = {}
    if "link.springer.com" in url:
        headers["Accept"] = "application/pdf"
    _status, body = _http_get(url, headers=headers)
    if is_pdf(body):
        return body

    if "pmc.ncbi.nlm.nih.gov" in url:
        parsed = parse_pow_interstitial(body.decode("utf-8", "ignore"))
        if parsed:
            challenge, difficulty = parsed
            nonce = solve_pow(challenge, difficulty)
            _status, body = _http_get(url, headers={
                "Cookie": f"cloudpmc-viewer-pow={challenge},{nonce}",
                "Referer": _pmc_referer(url),
            })
            if is_pdf(body):
                return body
    return None


def find_pdf(record: dict, email: str | None) -> tuple[str | None, bytes | None]:
    """First candidate that yields a valid PDF → (url, bytes); (None, None) when closed."""
    for url in candidate_pdf_urls(record, email):
        data = download_pdf(url)
        if data:
            return url, data
    return None, None


# ── Zotero desktop connector ──────────────────────────────────


def _connector_call(path: str, *, json_body=None, raw_body: bytes | None = None,
                    headers: dict | None = None) -> tuple[int, dict | None]:
    """One connector request. Returns (status, parsed_json_or_None)."""
    data = json.dumps(json_body).encode() if json_body is not None else raw_body
    req = urllib.request.Request(
        f"{CONNECTOR_BASE}{path}", data=data, method="POST",
        headers={
            "X-Zotero-Connector-API-Version": CONNECTOR_API_VERSION,
            **(headers or {}),
        })
    try:
        with urllib.request.urlopen(req, timeout=CONNECTOR_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, OSError):
        return 0, None


def connector_alive() -> bool:
    status, _ = _connector_call("/connector/ping", json_body={})
    return status == 200


def selected_target(expected: str | None) -> tuple[str, str]:
    """Connector save target from the Zotero pane; --collection acts as a guard.

    Returns (targetID like 'C565'/'L1', destination label). Raises ValueError
    when Zotero is unreachable or the selected destination is not the expected
    collection — the command never re-points the user's selection.
    """
    status, data = _connector_call("/connector/getSelectedCollection", json_body={})
    if status != 200 or not data:
        raise ValueError(
            "cannot read Zotero's selected collection — is the Zotero desktop "
            "app running? (or use --out DIR to fetch PDFs without Zotero)")
    if data.get("id") is not None:
        target, name = f"C{data['id']}", str(data.get("name") or "")
    else:
        target, name = f"L{data['libraryID']}", str(data.get("libraryName") or "the library")
    if expected and expected.strip().lower() != name.strip().lower():
        raise ValueError(
            f"Zotero's selected destination is '{name}', not '{expected}' — click the "
            "target collection in the Zotero pane and rerun, or drop --collection "
            "to accept the current selection")
    return target, name


def record_to_connector_item(record: dict, item_id: str) -> dict:
    """Pipeline record → connector saveItems item (translation-server shape).

    Single-field creators keep names verbatim — same policy as the Web API
    push mapping, no invented name splitting.
    """
    item_type = "preprint" if is_preprint(record) else "journalArticle"
    item = {
        "id": item_id,
        "itemType": item_type,
        "title": str(record.get("title") or ""),
        "creators": [{"creatorType": "author", "name": name}
                     for name in (record.get("authors") or []) if name],
        "DOI": str(record.get("doi") or ""),
        "url": str(record.get("paperUrl") or ""),
        "date": _zotero_date_from_year(record.get("year")),
        "abstractNote": str(record.get("abstract") or ""),
        "tags": [{"tag": "awescholar"}],
    }
    venue = str(record.get("venue") or "")
    if item_type == "preprint":
        item["repository"] = venue
    else:
        item["publicationTitle"] = venue
    return item


def attachment_title(record: dict) -> str:
    """"First Author - Year - Short Title.pdf" — display title for the attachment."""
    authors = record.get("authors") or ["Unknown"]
    year = str(record.get("year") or "").split(".")[0] or "n.d."
    title = re.sub(r"\s+", " ", str(record.get("title") or "Paper")).strip()[:100]
    name = f"{authors[0]} - {year} - {title}.pdf"
    return name.replace("/", "-")


def save_to_zotero(papers: list[tuple[dict, bytes]], expected_collection: str | None) -> dict:
    """One connector session: create every item, then attach its PDF bytes.

    saveAttachment accepts only items from the same saveItems session, so
    item creation and attachment are one atomic flow here.
    """
    target, label = selected_target(expected_collection)
    session_id = str(uuid.uuid4())
    items = [record_to_connector_item(record, f"awescholar-{i}")
             for i, (record, _data) in enumerate(papers)]
    status, _ = _connector_call("/connector/saveItems", json_body={
        "sessionID": session_id,
        "target": target,
        "uri": items[0].get("url") or "https://www.semanticscholar.org/",
        "items": items,
    })
    if status != 201:
        raise ValueError(f"Zotero rejected the save (HTTP {status}); nothing was written")

    attached: list[bool] = []
    for (record, data), item in zip(papers, items):
        metadata = json.dumps({
            "sessionID": session_id,
            "parentItemID": item["id"],
            "title": attachment_title(record),
            "url": str(record.get("paperUrl") or ""),
        })
        status, _ = _connector_call(
            "/connector/saveAttachment", raw_body=data,
            headers={"X-Metadata": metadata, "Content-Type": "application/pdf"})
        attached.append(status == 201)
    return {"destination": label, "created": len(items),
            "attached": sum(attached), "failures": len(attached) - sum(attached)}


# ── command core ──────────────────────────────────────────────


def run(queries: list[str], *, by: str = "title", out_dir: str | None = None,
        collection: str | None = None, unpaywall_email: str | None = None,
        ss_api_key: str | None = None) -> dict:
    """Resolve queries, fetch OA PDFs, land them in a directory or Zotero."""
    from .record import _get_client, search_by_doi, search_by_title

    sch = _get_client(ss_api_key)
    stats: dict = {"resolved": 0, "not_found": 0, "no_pdf": 0, "written": 0}
    for_zotero: list[tuple[dict, bytes]] = []

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    for query in queries:
        print(f"\nSearching: {query}")
        record = (search_by_doi(query, sch) if by == "doi"
                  else search_by_title(query, sch))
        if not record:
            stats["not_found"] += 1
            print("  Not found.")
            continue
        stats["resolved"] += 1
        print(f"  Resolved: {record['title'][:70]}")

        url, data = find_pdf(record, unpaywall_email)
        if not data:
            stats["no_pdf"] += 1
            print("  No open-access PDF found.", file=sys.stderr)
            continue
        print(f"  PDF: {url}")

        if out_dir:
            path = os.path.join(out_dir, attachment_title(record))
            with open(path, "wb") as f:
                f.write(data)
            stats["written"] += 1
            print(f"  Written: {path}")
        else:
            for_zotero.append((record, data))

    if not out_dir and for_zotero:
        if not connector_alive():
            print("Error: Zotero desktop is not reachable at "
                  f"{CONNECTOR_BASE} — start Zotero, or use --out DIR.",
                  file=sys.stderr)
            stats["zotero"] = {"created": 0, "attached": 0,
                               "failures": len(for_zotero)}
            return stats
        try:
            result = save_to_zotero(for_zotero, collection)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            result = {"created": 0, "attached": 0, "failures": len(for_zotero)}
        stats["zotero"] = result
        print(f"\nSaved {result['created']} item(s) to '{result['destination']}' "
              f"with {result['attached']} PDF(s) attached"
              + (f" ({result['failures']} attachment failure(s))" if result["failures"] else ""))
    return stats
