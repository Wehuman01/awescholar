"""Single-record operations: search by title/DOI and interactive manual entry."""

import json
import os
import sqlite3
import urllib.request
from pathlib import Path

from semanticscholar import SemanticScholar

from .categories import canonicalize_category
from .config import ss_env_api_key, warn_missing_ss_key
from .data_fields import normalize_title, utc_now_iso
from .utils import retry_with_backoff


def _now_iso() -> str:
    return utc_now_iso()

FIELDS = [
    "year", "title", "team", "team website", "affiliation",
    "domain", "venue", "paperUrl", "codeUrl", "githubStars",
]

CROSSREF_TIMEOUT_SECONDS = 15
CROSSREF_URL = "https://api.crossref.org/works/{doi}"
CROSSREF_UA = "awescholar (https://github.com/wehuman01/awescholar)"


def _get_client(api_key: str | None = None) -> SemanticScholar:
    key = api_key or ss_env_api_key()
    if not key:
        warn_missing_ss_key()
    return SemanticScholar(api_key=key) if key else SemanticScholar()


def _open_access_pdf_url(paper) -> str:
    """S2 openAccessPdf.url as a plain string ('' when absent or not a string)."""
    url = getattr(getattr(paper, "openAccessPdf", None), "url", None)
    return url if isinstance(url, str) else ""


def _paper_to_record(paper) -> dict | None:
    if not paper:
        return None

    team = ""
    author_names = []
    if paper.authors:
        author_names = [a.name for a in paper.authors if a.name]
        team = paper.authors[-1].name or ""

    year = ""
    pub_date = getattr(paper, "publicationDate", None)
    if pub_date:
        if isinstance(pub_date, str):
            year = pub_date[:7].replace("-", ".")
        else:
            year = pub_date.strftime("%Y.%m")
    elif getattr(paper, "year", None):
        year = str(paper.year)

    ext_ids = getattr(paper, "externalIds", None) or {}
    doi = ext_ids.get("DOI", "")
    arxiv_id = ext_ids.get("ArXiv", "")

    venue = getattr(paper, "venue", None) or ""
    if not venue:
        journal = getattr(paper, "journal", None)
        if journal and hasattr(journal, "name"):
            venue = journal.name or ""

    # Fresh preprints lag in S2 metadata: empty venue and DOI long after
    # indexing. The ArXiv external ID is present from day one and every arXiv
    # paper carries a DataCite DOI, so both fields are derived here instead of
    # persisting empty and waiting for a later backfill to heal.
    if arxiv_id:
        if not doi:
            doi = f"10.48550/arXiv.{arxiv_id}"
        if not venue:
            venue = "arXiv"

    # DOI links are canonical; S2 page URL is the last resort, never the first choice.
    if doi:
        paper_url = f"https://doi.org/{doi}"
    else:
        paper_url = getattr(paper, "url", None) or ""
        if not paper_url and paper.paperId:
            paper_url = f"https://www.semanticscholar.org/paper/{paper.paperId}"

    return {
        "year": year,
        "title": paper.title or "",
        "team": team,
        "authors": author_names,
        "team website": "",
        "affiliation": "",
        "domain": "",
        "venue": venue,
        "paperUrl": paper_url,
        "codeUrl": "",
        "githubStars": "",
        "citations": getattr(paper, "citationCount", None),
        "doi": doi,
        # Temporary: stripped from records before persisting (archive has no abstract field).
        "abstract": getattr(paper, "abstract", None) or "",
        # Temporary, same rule as abstract: the green-OA twin URL S2 knows
        # (often the arXiv PDF of a published paper) — consumed by zotero pdf.
        # The isinstance guard keeps mock papers (tests) and odd payloads out.
        "openAccessPdf": _open_access_pdf_url(paper),
        # Temporary: the arXiv id rides along even when a journal DOI won,
        # so the OA finder can reach the green twin of a paywalled version.
        "arxiv": arxiv_id if isinstance(arxiv_id, str) else "",
    }


def search_by_title(title: str, sch: SemanticScholar) -> dict | None:
    if not title.strip():
        return None
    try:
        paper = retry_with_backoff(
            sch.search_paper,
            title, limit=1, match_title=True,
            fields=["paperId", "title", "venue", "year",
                    "publicationDate", "authors", "externalIds", "url", "journal",
                    "citationCount", "abstract", "openAccessPdf"],
        )
        return _paper_to_record(paper)
    except Exception as e:  # noqa: BLE001 — one failed lookup must not abort the batch
        print(f"  Error: {e}")
        return None


def search_by_paper_id(paper_id: str, sch: SemanticScholar) -> dict | None:
    """Resolve a bare Semantic Scholar paperId (from an S2 page link) exactly."""
    if not paper_id.strip():
        return None
    try:
        paper = retry_with_backoff(
            sch.get_paper,
            paper_id,
            fields=["paperId", "title", "venue", "year",
                    "publicationDate", "authors", "externalIds", "url", "journal",
                    "citationCount", "abstract", "openAccessPdf"],
        )
        rec = _paper_to_record(paper)
        if rec and rec.get("title"):
            return rec
    except Exception as e:  # noqa: BLE001 — one failed lookup must not abort the batch
        print(f"  Error: {e}")
    return None


def _lookup_doi_local(doi: str) -> dict | None:
    """Find a DOI in recent pipeline outputs under cwd.

    Walks ``month_reports/*/papers.db`` and ``month_reports/*/updater_filter.json``
    to find papers the crawler already saw. This rescues lookups that
    Semantic Scholar hasn't fully indexed yet (e.g. the new bioRxiv
    ``10.64898`` prefix), where the pipeline saved the paper but a fresh
    DOI lookup returns 404.
    """
    needle = doi.strip().lower()
    if not needle:
        return None
    # Prefer the most recent pipeline output when multiple match.
    best: dict | None = None
    for db in sorted(Path(".").glob("month_reports/*/papers.db"), reverse=True):
        try:
            with sqlite3.connect(db) as con:
                row = con.execute(
                    "SELECT title, abstract, year, venue, citation_count "
                    "FROM papers WHERE LOWER(doi)=?",
                    (needle,),
                ).fetchone()
            if row and row[0]:
                best = {
                    "title": row[0], "abstract": row[1] or "",
                    "year": row[2] or "", "venue": row[3] or "",
                    "citationCount": row[4],
                    "_source": str(db),
                }
                break
        except Exception:  # noqa: BLE001, S112 — corrupt db must not abort the lookup
            continue
    if best is None:
        for jf in sorted(Path(".").glob("month_reports/*/updater_filter.json"), reverse=True):
            try:
                data = json.loads(jf.read_text())
            except Exception:  # noqa: BLE001, S112 — corrupt file must not abort the lookup
                continue
            for cat, papers in (data.items() if isinstance(data, dict) else []):
                if not isinstance(papers, list):
                    continue
                for p in papers:
                    if isinstance(p, dict) and (p.get("doi") or "").lower() == needle:
                        best = {**p, "_source": str(jf)}
                        break
                if best:
                    break
            if best:
                break
    return best


def _local_doi_record(doi: str, found: dict) -> dict:
    """Build a record-shaped payload from a cached lookup row."""
    pub_date = found.get("publicationDate") or found.get("publication_date") or ""
    year = ""
    if isinstance(pub_date, str) and pub_date:
        year = pub_date[:7].replace("-", ".")
    elif found.get("year"):
        year = str(found["year"])
    return {
        "year": year,
        "title": found.get("title") or "",
        "team": "",
        "authors": [],
        "team website": "",
        "affiliation": "",
        "domain": "",
        "venue": found.get("venue") or "",
        "paperUrl": f"https://doi.org/{doi}",
        "codeUrl": "",
        "githubStars": "",
        "citations": found.get("citationCount") or found.get("citation_count"),
        "doi": doi,
        "abstract": found.get("abstract") or "",
    }


def _crossref_doi_record(doi: str) -> dict | None:
    """Fetch a work from Crossref and shape it like an S2 record.

    Publisher-deposited metadata lands in Crossref within days of
    publication, long before Semantic Scholar indexes the paper, so this
    rescues brand-new DOIs that S2 answers 404 for. Returns None when the
    DOI is unknown to Crossref (e.g. DataCite-registered arXiv DOIs) or the
    request fails — a missing record is a normal outcome, not an error.
    """
    req = urllib.request.Request(
        CROSSREF_URL.format(doi=doi),
        headers={"User-Agent": CROSSREF_UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=CROSSREF_TIMEOUT_SECONDS) as resp:
            msg = json.load(resp)["message"]
    except Exception:  # noqa: BLE001 — unknown DOIs and transient failures are normal outcomes
        return None
    title = next((t for t in msg.get("title") or []), "")
    if not title:
        return None
    authors = [
        " ".join(x for x in (a.get("given"), a.get("family")) if x).strip()
        for a in msg.get("author") or []
    ]
    authors = [a for a in authors if a]
    year = ""
    for field in ("published", "issued"):
        parts = ((msg.get(field) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            month = parts[1] if len(parts) > 1 and parts[1] else None
            year = f"{parts[0]}.{month:02d}" if month else str(parts[0])
            break
    doi_norm = msg.get("DOI") or doi
    return {
        "year": year,
        "title": title,
        "team": authors[-1] if authors else "",
        "authors": authors,
        "team website": "",
        "affiliation": "",
        "domain": "",
        "venue": next((v for v in msg.get("container-title") or []), ""),
        "paperUrl": f"https://doi.org/{doi_norm}",
        "codeUrl": "",
        "githubStars": "",
        "citations": msg.get("is-referenced-by-count"),
        "doi": doi_norm,
        "abstract": "",
    }


def search_by_doi(doi: str, sch: SemanticScholar) -> dict | None:
    if not doi.strip():
        return None
    try:
        paper = retry_with_backoff(
            sch.get_paper,
            f"DOI:{doi}",
            fields=["paperId", "title", "venue", "year",
                    "publicationDate", "authors", "externalIds", "url", "journal",
                    "citationCount", "abstract", "openAccessPdf"],
        )
        rec = _paper_to_record(paper)
        if rec and rec.get("title"):
            return rec
        print("  Not found in Semantic Scholar; trying local cache...")
    except Exception as e:  # noqa: BLE001 — one failed lookup must not abort the batch
        print(f"  Error: {e}")
        print("  Falling back to local cache...")
    local = _lookup_doi_local(doi)
    if local:
        print(f"  Resolved from local cache: {local.get('_source')}")
        return _local_doi_record(doi, local)
    print("  Not in the local cache; trying Crossref (new DOIs land there first)...")
    record = _crossref_doi_record(doi)
    if record:
        print(f"  Resolved from Crossref: {record['title'][:60]}")
    return record


def _load_archive(archive_path: str) -> dict | list:
    if not os.path.exists(archive_path):
        return {}
    with open(archive_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_archive(archive_path: str, data) -> None:
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_flat_json(path: str) -> list:
    """Load a flat JSON list file. Returns empty list if not found."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Flatten dict format to list if needed
    if isinstance(data, dict):
        flat = []
        for papers in data.values():
            if isinstance(papers, list):
                flat.extend(papers)
        return flat
    return data


def _save_flat_json(path: str, papers: list) -> None:
    """Save papers as a flat JSON list."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)


def _is_duplicate(papers: list, record: dict) -> bool:
    rec_title = normalize_title(record.get("title"))
    rec_doi = record.get("doi")
    for existing in papers:
        if rec_title and normalize_title(existing.get("title")) == rec_title:
            return True
        if rec_doi and existing.get("doi") == rec_doi:
            return True
    return False


def _normalize_code_url(code_url: str) -> str | None:
    """Accept owner/repo shorthand or a full URL; return https://github.com/{owner}/{repo}."""
    url = code_url.strip()
    if not url:
        return None
    if url.startswith("https://github.com/"):
        owner_repo = url[len("https://github.com/"):]
    elif url.startswith("github.com/"):
        owner_repo = url[len("github.com/"):]
    else:
        owner_repo = url
    if "/" not in owner_repo:
        return None
    owner, repo = owner_repo.strip("/").split("/", 1)
    if not owner or not repo:
        return None
    return f"https://github.com/{owner}/{repo}"


def _annotate_records(
    records: list[dict],
    stats: dict,
    annotate: bool,
    annotate_model: str,
    annotate_api_key: str | None,
    annotate_base_url: str | None,
    annotate_temperature: float,
    categories: list[str] | None,
) -> None:
    """Fill `domain` for added records with a DOI via run_annotate (in place)."""
    if not annotate:
        return
    if not annotate_api_key:
        print("  Skipping annotation: no annotate_api_key provided.")
        return
    doi_records = [r for r in records if r.get("doi")]
    if not doi_records:
        return
    # Lazy import to avoid import cycles.
    from .pipeline import run_annotate

    try:
        result = run_annotate(
            papers=[
                {"doi": r["doi"], "title": r["title"], "abstract": r["abstract"]}
                for r in doi_records
            ],
            model=annotate_model,
            categories=categories,
            api_key=annotate_api_key,
            base_url=annotate_base_url,
            temperature=annotate_temperature,
        )
    except Exception as e:  # noqa: BLE001 — an LLM failure must not lose added records
        print(f"  Annotation failed: {e}")
        return

    doi_to_domain: dict[str, str] = {}
    for entries in result.values():
        for entry in entries:
            domain = entry.get("domain") or ""
            if domain and entry.get("doi"):
                doi_to_domain[entry["doi"]] = domain

    for record in doi_records:
        domain = doi_to_domain.get(record["doi"])
        if domain:
            record["domain"] = domain
            stats["annotated"] += 1

    print(f"  Annotated domain for {stats['annotated']}/{len(doi_records)} added paper(s)")


def _apply_code(
    record: dict,
    norm_code_url: str | None,
    stars_style: str,
) -> None:
    """Write normalized codeUrl and (for badge style) the shields stars URL into a record."""
    if not norm_code_url:
        return
    record["codeUrl"] = norm_code_url
    if stars_style == "badge" and norm_code_url.startswith("https://github.com/"):
        owner, repo = norm_code_url[len("https://github.com/"):].split("/")
        record["githubStars"] = f"https://img.shields.io/github/stars/{owner}/{repo}"


def search_and_add(
    archive_path: str | None = None,
    by: str = "title",
    api_key: str | None = None,
    json_file: str | None = None,
    category: str | None = None,
    queries: list[str] | None = None,
    code_url: str | None = None,
    stars_style: str = "numeric",
    annotate: bool = False,
    annotate_model: str = "",
    annotate_api_key: str | None = None,
    annotate_base_url: str | None = None,
    annotate_temperature: float = 0.0,
) -> dict:
    """Search Semantic Scholar by title or DOI and add records to archive or json file.

    Pass ``queries`` for non-interactive use; when omitted, titles/DOIs are
    read interactively until an empty line. Returns a stats dict with counts
    of ``added``, ``not_found``, ``duplicates`` and ``annotated`` records.
    """
    target = json_file or archive_path
    print("\nSemantic Scholar Paper Search")
    print(f"Search by: {by}")
    print(f"Target: {target}")

    if queries is None:
        queries = []
        print(f"\nEnter paper {by} (empty line to finish):")
        while True:
            line = input(f"  [{len(queries) + 1}] ").strip()
            if not line:
                break
            queries.append(line)

    if not queries:
        print("\nNo papers to search.")
        return {"added": 0, "not_found": 0, "duplicates": 0, "annotated": 0}

    sch = _get_client(api_key)

    norm_code_url = _normalize_code_url(code_url) if code_url else None

    stats = {"added": 0, "not_found": 0, "duplicates": 0, "annotated": 0}
    added_records: list[dict] = []

    def _search(query: str) -> dict | None:
        if not query.strip():
            return None
        return search_by_title(query, sch) if by == "title" else search_by_doi(query, sch)

    if json_file:
        # Flat list mode: save to a standalone JSON file for review
        papers_list = _load_flat_json(json_file)
        for i, query in enumerate(queries, 1):
            print(f"\n[{i}/{len(queries)}] Searching: {query}")
            record = _search(query)

            if not record:
                stats["not_found"] += 1
                print("  Not found.")
                continue

            if _is_duplicate(papers_list, record):
                stats["duplicates"] += 1
                print(f"  Already exists: {record['title'][:60]}")
                continue

            added_records.append(record)
            stats["added"] += 1
            print(f"  Added: {record['title'][:60]}")

        if added_records:
            _annotate_records(added_records, stats, annotate, annotate_model,
                              annotate_api_key, annotate_base_url,
                              annotate_temperature, categories=None)
            for record in added_records:
                _apply_code(record, norm_code_url, stars_style)
                record.pop("abstract", None)
                record.setdefault("addedAt", _now_iso())
                papers_list.append(record)
            _save_flat_json(json_file, papers_list)
            print(f"\nAdded {stats['added']} paper(s) to {json_file}")
        else:
            print("\nNo new papers were added.")
    else:
        # Archive mode: save to categorized archive dict
        archive = _load_archive(archive_path)
        if not isinstance(archive, dict):
            archive = {"papers": archive}

        # Add to the requested category (normalized to an existing spelling),
        # falling back to the first category as before
        if category:
            target = canonicalize_category(category, archive.keys())
        else:
            categories = list(archive.keys())
            target = categories[0] if categories else "papers"

        # Flatten all papers across categories for dedup
        all_papers = []
        for cat_papers in archive.values():
            if isinstance(cat_papers, list):
                all_papers.extend(cat_papers)

        categories = list(archive.keys())

        for i, query in enumerate(queries, 1):
            print(f"\n[{i}/{len(queries)}] Searching: {query}")
            record = _search(query)

            if not record:
                stats["not_found"] += 1
                print("  Not found.")
                continue

            if _is_duplicate(all_papers, record):
                stats["duplicates"] += 1
                print(f"  Already exists: {record['title'][:60]}")
                continue

            added_records.append(record)
            stats["added"] += 1
            print(f"  Added: {record['title'][:60]}")

        if added_records:
            _annotate_records(added_records, stats, annotate, annotate_model,
                              annotate_api_key, annotate_base_url,
                              annotate_temperature, categories=categories)
            if target not in archive:
                archive[target] = []
            for record in added_records:
                _apply_code(record, norm_code_url, stars_style)
                record.pop("abstract", None)
                record.setdefault("addedAt", _now_iso())
                archive[target].append(record)
            _save_archive(archive_path, archive)
            print(f"\nAdded {stats['added']} paper(s) to {archive_path}")
        else:
            print("\nNo new papers were added.")

    return stats


def add_interactive(archive_path: str, categories: list[str] | None = None) -> None:
    """Interactively add a single record to the archive."""
    if categories is None:
        categories = ["ai-agents", "foundation-models", "databases", "benchmarks", "reviews"]

    print("\nSelect category:")
    for i, cat in enumerate(categories, 1):
        print(f"  {i}. {cat}")

    while True:
        choice = input("Enter number or name: ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(categories):
                category = categories[idx]
                break
        elif choice in categories:
            category = choice
            break
        print("Invalid choice.")

    print(f"\nCategory: {category}")
    print("Enter fields separated by semicolons (;). Use \"\" for empty values.")
    print("Fields: year; title; team; team website; affiliation; domain; venue; paperUrl; codeUrl; githubStars")

    while True:
        line = input("Record: ").strip()
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < len(FIELDS):
            parts.extend([""] * (len(FIELDS) - len(parts)))
        elif len(parts) > len(FIELDS):
            print(f"Too many fields. Expected {len(FIELDS)}, got {len(parts)}.")
            continue
        parts = ["" if p == '""' else p for p in parts]
        if not parts[0]:
            print("Year is mandatory.")
            continue
        if not parts[1]:
            print("Title is mandatory.")
            continue
        break

    record = dict(zip(FIELDS, parts))

    archive = _load_archive(archive_path)
    if not isinstance(archive, dict):
        archive = {}

    if category not in archive:
        archive[category] = []
    archive[category].append(record)
    archive[category].sort(key=lambda x: x.get("year", "0"), reverse=True)

    _save_archive(archive_path, archive)
    print(f"\nRecord added to '{category}' in {archive_path}")
