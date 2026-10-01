"""Core pipeline: search -> annotate -> filter -> report."""

import html
import json
import os
from collections.abc import Callable

from . import prompts
from .archive import DateEncoder
from .categories import canonicalize_category
from .config import resolve_agent_settings
from .data_fields import normalize_updater_paper_fields
from .llm import complete
from .schemas import AnnotationResult, FilterResult
from .search import search_papers

StatusCallback = Callable[[str], None] | None


def _noop(msg: str) -> None:
    pass


def run_search(
    query: str,
    db_path: str = "output",
    api_key: str | None = None,
    limit: int = 100,
    fields_of_study: list[str] | None = None,
    publication_date_or_year: str | None = None,
    pubmed: bool = False,
    status_cb: StatusCallback = None,
) -> list[dict]:
    """Search Semantic Scholar and optionally PubMed, then save to DB."""
    cb = status_cb or _noop
    sources = "Semantic Scholar + PubMed" if pubmed else "Semantic Scholar"
    cb(f"Searching {sources} (limit={limit})...")
    papers = search_papers(
        query=query,
        db_path=db_path,
        api_key=api_key,
        limit=limit,
        fields_of_study=fields_of_study,
        publication_date_or_year=publication_date_or_year,
        pubmed=pubmed,
    )
    cb(f"Found {len(papers)} papers.")
    return papers


def run_annotate(
    papers: list[dict],
    model: str,
    categories: list[str] | None = None,
    include_abstracts: bool = True,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.0,
    status_cb: StatusCallback = None,
) -> dict[str, list[dict]]:
    """Annotate papers with domain and category. Returns structured dict by category."""
    cb = status_cb or _noop
    cb("Annotating papers...")

    cat_str = json.dumps(categories) if categories else "[]"
    papers_xml = "<papers>\n"
    for p in papers:
        abstract_part = f"\n  <abstract>{html.escape(p.get('abstract', '') or '')}</abstract>" if include_abstracts else ""
        papers_xml += f"<paper>\n  <doi>{html.escape(p['doi'])}</doi>\n  <title>{html.escape(p['title'])}</title>{abstract_part}\n</paper>\n"
    papers_xml += f"</papers>\n<predefined_category_list>\n{cat_str}\n</predefined_category_list>"

    max_retries = 3
    result = None
    for attempt in range(max_retries):
        try:
            result = complete(
                model=model, system=prompts.ANNOTATOR, user=papers_xml,
                response_format=AnnotationResult, api_key=api_key, base_url=base_url,
                temperature=temperature,
            )
            if isinstance(result, AnnotationResult):
                break
        except Exception:
            if attempt == max_retries - 1:
                raise
    if not isinstance(result, AnnotationResult):
        raise RuntimeError(  # noqa: TRY004 — invalid LLM output, not a caller type error
            f"Annotator LLM returned invalid response after {max_retries} attempts."
        )

    paper_map = {p["doi"]: p for p in papers}
    structured: dict[str, list[dict]] = {}
    for ann in result.paper_list:
        paper_data = paper_map.get(ann.doi)
        if not paper_data:
            continue
        category = canonicalize_category(ann.category, categories or [])
        entry = normalize_updater_paper_fields(
            {**paper_data, "domain": ann.domain, "category": category}
        )
        structured.setdefault(category, []).append(entry)

    cb(f"Annotated {len(result.paper_list)} papers into {len(structured)} categories.")
    return structured


def run_filter(
    structured_data: dict[str, list[dict]],
    model: str,
    limit: int = 20,
    research_interests: str | list[str] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.0,
    status_cb: StatusCallback = None,
) -> dict[str, list[dict]]:
    """Filter papers for quality and relevance. Returns filtered structured data."""
    cb = status_cb or _noop
    cb("Filtering papers...")

    minimal = {}
    for cat, papers in structured_data.items():
        minimal[cat] = [
            {
                "doi": p["doi"],
                "title": p["title"],
                "domain": p.get("domain", ""),
                "venue": p.get("venue", ""),
                "affiliation": p.get("affiliation", ""),
            }
            for p in papers
        ]

    user_payload: dict = {"papers": minimal, "limit_filter": limit}
    if research_interests:
        user_payload["research_interests"] = research_interests

    result = complete(
        model=model, system=prompts.FILTER,
        user=json.dumps(user_payload, indent=2, cls=DateEncoder),
        response_format=FilterResult, api_key=api_key, base_url=base_url,
        temperature=temperature,
    )
    if isinstance(result, str):
        raise RuntimeError(f"Filter LLM returned invalid response. Raw: {result[:200]}")  # noqa: TRY004

    # Collect DOIs in LLM's ranked order, then hard-truncate to limit
    ordered_dois: list[str] = []
    reasons: dict[str, str] = {}
    for cat_papers in result.papers.values():
        for p in cat_papers:
            if p.doi not in reasons:
                ordered_dois.append(p.doi)
            reasons[p.doi] = p.reason

    if len(ordered_dois) > limit:
        ordered_dois = ordered_dois[:limit]

    kept_set = set(ordered_dois)
    filtered: dict[str, list[dict]] = {}
    for cat, papers in structured_data.items():
        kept = [
            normalize_updater_paper_fields({**p, "reason_for_inclusion": reasons[p["doi"]]})
            for p in papers
            if p["doi"] in kept_set
        ]
        if kept:
            filtered[cat] = kept

    cb(f"Selected {sum(len(v) for v in filtered.values())} papers after filtering.")
    return filtered


def run_report(
    filtered_data: dict[str, list[dict]],
    model: str,
    date_range: str = "N/A",
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.0,
    status_cb: StatusCallback = None,
    system_prompt: str | None = None,
) -> str:
    """Generate Markdown report from filtered papers.

    The returned markdown opens with a provenance comment recording the model
    and date range, so the report file itself carries its recipe.
    """
    cb = status_cb or _noop
    cb("Generating report...")

    system = (system_prompt or prompts.REPORTER).replace("{date_range}", date_range)
    result = complete(
        model=model, system=system,
        user=json.dumps(filtered_data, indent=2, ensure_ascii=False, cls=DateEncoder),
        api_key=api_key, base_url=base_url, temperature=temperature,
    )
    cb("Report generated.")
    return report_provenance(model, date_range) + result


def report_provenance(model: str, scope: str) -> str:
    """HTML comment recording which model and scope produced a report."""
    from . import __version__

    return f"<!-- awescholar {__version__} · model: {model.split('/')[-1]} · scope: {scope} -->\n\n"


def _merge_filtered_to_data(
    filtered_path: str,
    data_json_path: str | None,
    merge_new_to_old: bool,
    status_cb: StatusCallback,
) -> None:
    if not merge_new_to_old:
        return
    if not data_json_path:
        raise RuntimeError("pipeline.data_json_path is required when pipeline.merge_new_to_old is true")

    from .archive import merge_new_to_archive

    parent = os.path.dirname(data_json_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    merge_new_to_archive(filtered_path, data_json_path)
    cb = status_cb or _noop
    cb(f"Merged filtered data into {data_json_path}")


def run_pipeline(
    query: str | None,
    model: str,
    db_path: str = "output",
    api_key: str | None = None,
    ss_api_key: str | None = None,
    base_url: str | None = None,
    agent_models: dict | None = None,
    limit_search: int = 100,
    limit_filter: int = 20,
    categories: list[str] | None = None,
    include_abstracts: bool = True,
    fields_of_study: list[str] | None = None,
    publication_date_or_year: str | None = None,
    skip_search: bool = False,
    use_updater_json: bool = False,
    use_filtered_json: bool = False,
    existing_json_path: str | None = None,
    merge_new_to_old: bool = False,
    data_json_path: str | None = None,
    model_profiles: dict | None = None,
    research_interests: str | list[str] | None = None,
    temperature: float = 0.0,
    status_cb: StatusCallback = None,
) -> tuple[dict, str]:
    """Run full pipeline with optional skip/resume controls.

    Returns (filtered_data, report_markdown).
    """
    from .db import Paper, get_session

    cb = status_cb or _noop
    os.makedirs(db_path, exist_ok=True)

    updater_path = existing_json_path or os.path.join(db_path, "updater.json")
    filtered_path = os.path.join(db_path, "updater_filter.json")

    # --- Fast path: reuse filtered results ---
    if use_filtered_json:
        cb("Skipping search + annotate + filter (use_filtered_json=true)")
        if not os.path.exists(filtered_path):
            raise FileNotFoundError(f"Not found: {filtered_path}")
        with open(filtered_path, "r", encoding="utf-8") as f:
            filtered = json.load(f)
        _merge_filtered_to_data(filtered_path, data_json_path, merge_new_to_old, cb)
        m, k, u, t = resolve_agent_settings(agent_models, "reporter", model, api_key, base_url,
                                            model_profiles, fallback_temperature=temperature)
        report = run_report(
            filtered_data=filtered, model=m,
            date_range=publication_date_or_year or "N/A",
            api_key=k, base_url=u, temperature=t, status_cb=cb,
        )
        return filtered, report

    # --- Skip annotate: reuse updater.json ---
    if use_updater_json:
        cb("Skipping search + annotate (use_updater_json=true)")
        if not os.path.exists(updater_path):
            raise FileNotFoundError(f"Not found: {updater_path}")
        with open(updater_path, "r", encoding="utf-8") as f:
            structured = json.load(f)
        m, k, u, t = resolve_agent_settings(agent_models, "filterer", model, api_key, base_url,
                                            model_profiles, fallback_temperature=temperature)
        filtered = run_filter(
            structured_data=structured, model=m, limit=limit_filter,
            research_interests=research_interests,
            api_key=k, base_url=u, temperature=t, status_cb=cb,
        )
        with open(filtered_path, "w", encoding="utf-8") as f:
            json.dump(filtered, f, indent=2, ensure_ascii=False, cls=DateEncoder)
        cb(f"Saved filtered data to {filtered_path}")
        _merge_filtered_to_data(filtered_path, data_json_path, merge_new_to_old, cb)
        m, k, u, t = resolve_agent_settings(agent_models, "reporter", model, api_key, base_url,
                                            model_profiles, fallback_temperature=temperature)
        report = run_report(
            filtered_data=filtered, model=m,
            date_range=publication_date_or_year or "N/A",
            api_key=k, base_url=u, temperature=t, status_cb=cb,
        )
        return filtered, report

    # --- Search phase ---
    if skip_search:
        cb("Skipping search (skip_search=true), loading from DB")
        session = get_session(db_path)
        db_papers = session.query(Paper).all()
        session.close()
        if not db_papers:
            raise RuntimeError("No papers in database. Run search first.")
        papers = [
            {"doi": p.doi, "title": p.title, "abstract": p.abstract, "venue": p.venue,
             "authors": p.authors}
            for p in db_papers
        ]
    else:
        if not query:
            raise RuntimeError("query is required when skip_search is false")
        from .db import clear_db
        clear_db(db_path)
        cb("Cleared previous database for fresh search.")
        papers = run_search(
            query=query, db_path=db_path, api_key=ss_api_key, limit=limit_search,
            fields_of_study=fields_of_study, publication_date_or_year=publication_date_or_year,
            status_cb=cb,
        )
        if not papers:
            raise RuntimeError("No papers found for the given query. Try broadening your search terms.")

    # --- Annotate phase ---
    m, k, u, t = resolve_agent_settings(agent_models, "annotator", model, api_key, base_url,
                                        model_profiles, fallback_temperature=temperature)
    structured = run_annotate(
        papers=papers, model=m, categories=categories,
        include_abstracts=include_abstracts, api_key=k, base_url=u, temperature=t, status_cb=cb,
    )
    with open(updater_path, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2, ensure_ascii=False, cls=DateEncoder)
    cb(f"Saved annotated data to {updater_path}")

    # --- Filter phase ---
    m, k, u, t = resolve_agent_settings(agent_models, "filterer", model, api_key, base_url,
                                        model_profiles, fallback_temperature=temperature)
    filtered = run_filter(
        structured_data=structured, model=m, limit=limit_filter,
        research_interests=research_interests,
        api_key=k, base_url=u, temperature=t, status_cb=cb,
    )
    with open(filtered_path, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False, cls=DateEncoder)
    cb(f"Saved filtered data to {filtered_path}")
    _merge_filtered_to_data(filtered_path, data_json_path, merge_new_to_old, cb)

    # --- Report phase ---
    m, k, u, t = resolve_agent_settings(agent_models, "reporter", model, api_key, base_url,
                                        model_profiles, fallback_temperature=temperature)
    report = run_report(
        filtered_data=filtered, model=m,
        date_range=publication_date_or_year or "N/A",
        api_key=k, base_url=u, temperature=t, status_cb=cb,
    )

    return filtered, report
