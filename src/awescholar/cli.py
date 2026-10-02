"""CLI entry point for awescholar."""

import argparse
import json
import os
import sys

from . import __version__
from .archive import DateEncoder
from .config import load_config, resolve_agent_config, warn_missing_github_token
from .months import (
    month_date_range,
    month_report_dir,
    parse_month,
    parse_period,
    period_date_range,
    period_report_dir,
)


def get_version() -> str:
    return __version__


def status(msg: str) -> None:
    print(f"  -> {msg}")


def _apply_month(args: argparse.Namespace, config: dict) -> int | None:
    """Derive the date range and db_path from --month; returns 1 on a bad value."""
    month = getattr(args, "month", None)
    if not month:
        return None
    try:
        year, mon = parse_month(month)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    config["publication_date"] = month_date_range(year, mon)
    config["db_path"] = month_report_dir(year, mon)
    status(f"--month {year:04d}-{mon:02d}: dates {config['publication_date']}, "
           f"output {config['db_path']}/")
    return None


def _apply_when(args: argparse.Namespace, config: dict) -> int | None:
    """Derive date range and db_path from --month or --period; 1 on a bad value."""
    period = getattr(args, "period", None)
    if period:
        try:
            year, mon, half = parse_period(period)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        config["publication_date"] = period_date_range(year, mon, half)
        config["db_path"] = period_report_dir(year, mon, half)
        status(f"--period {period}: dates {config['publication_date']}, "
               f"output {config['db_path']}/")
        return None
    return _apply_month(args, config)


# ── Subcommands ──────────────────────────────────────────────

def cmd_search(args: argparse.Namespace, config: dict) -> int | None:
    from .pipeline import run_search

    if _apply_when(args, config):
        return 1
    papers = run_search(
        query=args.query,
        db_path=config["db_path"],
        api_key=config["ss_api_key"],
        limit=args.limit or config["limit_search"],
        fields_of_study=config["fields_of_study"],
        publication_date_or_year=args.date or config["publication_date"],
        pubmed=config["pubmed"],
        status_cb=status,
    )
    print(f"\nSaved {len(papers)} papers to {config['db_path']}/papers.db")


def cmd_annotate(args: argparse.Namespace, config: dict) -> int | None:
    from .pipeline import run_annotate

    if args.input:
        if not os.path.exists(args.input):
            print(f"Not found: {args.input}")
            return 1
        with open(args.input, "r", encoding="utf-8") as f:
            papers = json.load(f)
    else:
        from .db import Paper, get_session
        session = get_session(config["db_path"])
        db_papers = session.query(Paper).all()
        session.close()
        if not db_papers:
            print("No papers in database. Run 'awescholar crawler search <query>' first.")
            return 1
        papers = [
            {"doi": p.doi, "title": p.title, "abstract": p.abstract, "venue": p.venue,
             "authors": p.authors}
            for p in db_papers
        ]

    model, api_key, base_url, temperature = resolve_agent_config(config, "annotator")
    structured = run_annotate(
        papers=papers, model=model, categories=config["categories"],
        include_abstracts=config["include_abstracts"],
        api_key=api_key, base_url=base_url, temperature=temperature, status_cb=status,
    )

    out_path = os.path.join(config["db_path"], "updater.json")
    os.makedirs(config["db_path"], exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2, ensure_ascii=False, cls=DateEncoder)
    print(f"\nSaved annotated data to {out_path}")


def cmd_filter(args: argparse.Namespace, config: dict) -> int | None:
    from .pipeline import run_filter

    updater_path = args.input or os.path.join(config["db_path"], "updater.json")
    if not os.path.exists(updater_path):
        print(f"Not found: {updater_path}. Run 'awescholar crawler annotate' first.")
        return 1

    with open(updater_path, "r", encoding="utf-8") as f:
        structured = json.load(f)

    model, api_key, base_url, temperature = resolve_agent_config(config, "filterer")
    filtered = run_filter(
        structured_data=structured, model=model,
        limit=args.limit or config["limit_filter"],
        research_interests=config.get("research_interests"),
        api_key=api_key, base_url=base_url, temperature=temperature, status_cb=status,
    )

    out_path = os.path.join(config["db_path"], "updater_filter.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False, cls=DateEncoder)
    print(f"\nSaved filtered data to {out_path}")


def cmd_report(args: argparse.Namespace, config: dict) -> int | None:
    from .pipeline import run_report

    filtered_path = args.input or os.path.join(config["db_path"], "updater_filter.json")
    if not os.path.exists(filtered_path):
        print(f"Not found: {filtered_path}. Run 'awescholar crawler filter' first.")
        return 1

    with open(filtered_path, "r", encoding="utf-8") as f:
        filtered = json.load(f)

    model, api_key, base_url, temperature = resolve_agent_config(config, "reporter")
    report = run_report(
        filtered_data=filtered, model=model,
        date_range=config.get("publication_date") or "N/A",
        api_key=api_key, base_url=base_url, temperature=temperature, status_cb=status,
    )

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nReport saved to {args.output}")
    else:
        print("\n" + report)


def cmd_run(args: argparse.Namespace, config: dict) -> int | None:
    from .pipeline import run_pipeline

    if _apply_when(args, config):
        return 1
    query = args.query or config.get("search_query")
    if not query and not config.get("skip_search"):
        print("Error: query is required (via CLI arg or config search.query)")
        return 1

    _, report = run_pipeline(
        query=query, model=config["model"], db_path=config["db_path"],
        api_key=config["api_key"], ss_api_key=config["ss_api_key"], base_url=config["base_url"],
        agent_models=config.get("agent_models"),
        model_profiles=config.get("model_profiles"),
        limit_search=args.limit_search or config["limit_search"],
        limit_filter=args.limit_filter or config["limit_filter"],
        categories=config["categories"], include_abstracts=config["include_abstracts"],
        fields_of_study=config["fields_of_study"],
        publication_date_or_year=args.date or config["publication_date"],
        skip_search=config["skip_search"],
        use_updater_json=config["use_updater_json"],
        use_filtered_json=config["use_filtered_json"],
        existing_json_path=config["existing_json_path"],
        merge_new_to_old=config["merge_new_to_old"],
        data_json_path=config["data_json_path"],
        research_interests=config.get("research_interests"),
        temperature=config.get("temperature", 0.0),
        status_cb=status,
    )

    output = args.output or config.get("report_filename") \
        or os.path.join(config["db_path"], "report.md")
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport saved to {output}")


def cmd_update(args: argparse.Namespace, config: dict) -> int | None:
    from .archive import DEFAULT_REVIEW_FILENAME, merge_archive_to_new, merge_new_to_archive

    new_path = args.input or os.path.join(config["db_path"], "updater_filter.json")
    if not os.path.exists(new_path):
        print(f"Not found: {new_path}. Run 'awescholar crawler run' first.")
        return 1

    if args.direction == "new2old":
        before = _count_papers(args.archive)
        merge_new_to_archive(new_path, args.archive, dedupe=not args.no_dedupe)
        added = _count_papers(args.archive) - before
        review_path = os.path.join(os.path.dirname(new_path) or ".", DEFAULT_REVIEW_FILENAME)
        if not args.no_dedupe and os.path.exists(review_path):
            with open(review_path, "r", encoding="utf-8") as f:
                held = len(json.load(f))
            print(f"Merged  : {added} added · {held} possible duplicates held back")
            print(f"Review  : {review_path}")
            print(f"Resolve : awescholar updater dedupe --review {review_path} "
                  f"--archive {args.archive} --keep newer|published|both")
        else:
            print(f"Merged {added} papers into {args.archive}")
        if added > 0:
            print(f"Next  : awescholar render counts --archive {args.archive}"
                  "   # website-first README counts (render readme for table READMEs)")
            print(f"        awescholar render rss --archive {args.archive} -o docs/rss.xml")
    elif args.direction == "old2new":
        merge_archive_to_new(new_path, args.archive)
        print(f"Enriched {new_path} with archive papers")


def _count_papers(archive_path: str) -> int:
    if not os.path.exists(archive_path):
        return 0
    with open(archive_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return sum(len(v) for v in data.values() if isinstance(v, list))


def cmd_dedupe(args: argparse.Namespace, config: dict) -> int | None:
    from .archive import apply_dedupe_review

    if not os.path.exists(args.review):
        print(f"Not found: {args.review}. Held-back duplicates appear here after "
              "'updater update --direction new2old'.")
        return 1
    applied = apply_dedupe_review(args.review, args.archive, keep=args.keep)
    for item in applied:
        title = str(item.get("incoming", {}).get("title") or "")[:60]
        print(f"  [{item.get('title_similarity', 0):.2f}] {item['resolution']}: {title}")
    print(f"\nResolved {len(applied)} pair(s) in {args.archive}; removed {args.review}")


def cmd_publish_scan(args: argparse.Namespace, config: dict) -> int | None:
    from .publish_scan import DEFAULT_REVIEW_FILENAME, apply_review, publish_scan, queue_pair

    review_path = args.review or os.path.join(
        os.path.dirname(args.archive) or ".", DEFAULT_REVIEW_FILENAME)

    if getattr(args, "pair", None):
        if len(args.pair) != 2:
            print("Error: --pair needs exactly two DOIs: --pair PREPRINT_PUBLISHED",
                  file=sys.stderr)
            return 1
        try:
            queue_pair(args.archive, args.pair[0], args.pair[1],
                       api_key=config["ss_api_key"], review_path=review_path)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if args.apply:
            applied = apply_review(review_path, args.archive, no_backup=args.no_backup)
            upgraded = sum(1 for a in applied if a["resolution"].startswith("upgraded"))
            print(f"Upgraded {upgraded} preprint(s) in {args.archive}")
            if upgraded:
                print(f"Next  : awescholar render counts --archive {args.archive}")
                print(f"        awescholar render rss --archive {args.archive} -o docs/rss.xml")
        return None

    if args.apply and os.path.exists(review_path) and args.review:
        # Two-step flow: apply a reviewed file without rescanning.
        applied = apply_review(review_path, args.archive, no_backup=args.no_backup)
        upgraded = sum(1 for a in applied if a["resolution"].startswith("upgraded"))
        for item in applied:
            title = str(item.get("published", {}).get("title") or "")[:60]
            print(f"  {item['resolution']}: {title}")
        print(f"\nUpgraded {upgraded} preprint(s) in {args.archive}; removed {review_path}")
        if upgraded:
            print(f"Next  : awescholar render counts --archive {args.archive}"
                  "   # venue changes reshuffle README tables/counts")
            print(f"        awescholar render rss --archive {args.archive} -o docs/rss.xml")
        return None

    stats = publish_scan(
        args.archive, api_key=config["ss_api_key"],
        apply=args.apply, review_path=review_path, only=args.only,
        limit=args.limit, use_title_search=not args.no_title_search,
        no_backup=args.no_backup,
    )
    if stats["applied"]:
        print(f"Next  : awescholar render counts --archive {args.archive}"
              "   # venue changes reshuffle README tables/counts")
        print(f"        awescholar render rss --archive {args.archive} -o docs/rss.xml")


def cmd_readme(args: argparse.Namespace, config: dict) -> int | None:
    from .readme import discover_readme_targets, update_readme

    if args.readme:
        targets = [args.readme]
    else:
        targets = discover_readme_targets(".")
        if not targets:
            targets = [os.path.join(os.path.dirname(args.archive), "readme.md")]

    for readme_path in targets:
        update_readme(
            archive_path=args.archive, readme_path=readme_path,
            project_title=args.title or "Awesome Scholar",
            project_description=args.description or "",
            no_backup=args.no_backup,
        )
        print(f"README updated at {readme_path}")


def cmd_rss(args: argparse.Namespace, config: dict) -> int | None:
    from .rss import generate_rss

    output = args.output or "rss.xml"
    generate_rss(
        archive_path=args.archive, output_path=output,
        title=args.title or "Awesome Scholar Updates",
        link=args.link or "",
        description=args.description or "Latest papers from curated collection",
        rss_url=args.rss_url or "",
    )
    print(f"RSS feed generated at {output}")


def cmd_search_record(args: argparse.Namespace, config: dict) -> int | None:
    from .record import search_and_add

    if not args.archive and not args.json_file:
        print("Error: provide --archive or --json-file")
        return 1

    model = api_key = base_url = None
    temperature = 0.0
    if args.annotate:
        model, api_key, base_url, temperature = resolve_agent_config(config, "annotator")
        if not api_key:
            print("Error: --annotate needs a model API key (set --config or AWESCHOLAR_API_KEY).")
            return 1

    stars_style = args.stars_style or config.get("stars_style") or "numeric"
    stats = search_and_add(
        archive_path=args.archive, by=args.by,
        api_key=config["ss_api_key"], json_file=args.json_file,
        category=args.category, queries=args.queries or None,
        code_url=args.code_url, stars_style=stars_style,
        annotate=args.annotate, annotate_model=model or "",
        annotate_api_key=api_key, annotate_base_url=base_url,
        annotate_temperature=temperature,
    )

    if stats["added"] and args.archive:
        print(f"Next  : awescholar render counts --archive {args.archive}"
              "   # website-first README counts (render readme for table READMEs)")
        print(f"        awescholar render rss --archive {args.archive} -o docs/rss.xml")


def cmd_backfill(args: argparse.Namespace, config: dict) -> int | None:
    if getattr(args, "agentx", False):
        from .agentx.papers_fill import enrich_papers, refresh_citations, sync_venue_tags

        archive = args.archive or "data/agents-snapshot.json"
        fields = args.fields or ["paper-meta", "citations"]
        if "affiliation" in fields:
            print("Error: --fields affiliation is paper-archive only; an AgentX "
                  "snapshot has no affiliation field.", file=sys.stderr)
            return 1
        if "paper-meta" in fields:
            enrich_papers(archive, force=bool(getattr(args, "refresh", False)),
                          only=args.only, ss_api_key=config["ss_api_key"])
        if "paper-meta" in fields or "venue-tags" in fields:
            sync_venue_tags(archive, only=args.only)
        if "citations" in fields:
            # Citation counts always refresh — null means "not indexed", not "empty".
            refresh_citations(archive, ss_api_key=config["ss_api_key"])
        return 0

    from .backfill import backfill_affiliations, backfill_citations

    if not args.archive:
        print("Error: --archive is required (or pass --agentx to backfill an "
              "AgentX snapshot)", file=sys.stderr)
        return 1
    fields = args.fields or ["affiliation", "citations"]
    if "venue-tags" in fields:
        print("Error: --fields venue-tags is AgentX-only; pass --agentx.", file=sys.stderr)
        return 1
    if "affiliation" in fields:
        backfill_affiliations(
            archive_path=args.archive, api_key=config["ss_api_key"],
            no_backup=args.no_backup, only=args.only,
        )
    if "citations" in fields:
        stats = backfill_citations(
            archive_path=args.archive, api_key=config["ss_api_key"],
            no_backup=args.no_backup, only=args.only,
        )
        print(f"\nFilled {stats['filled_citations']}/{stats['candidates']} citation counts")


def cmd_enrich(args: argparse.Namespace, config: dict) -> int | None:
    from .enrich import enrich_archive

    if not args.archive and not args.agentx:
        print("Error: --archive is required (or pass --agentx to refresh an "
              "AgentX snapshot)", file=sys.stderr)
        return 1
    archive = args.archive or "data/agents-snapshot.json"

    model = api_key = base_url = None
    temperature = 0.0
    if not args.no_llm:
        model, api_key, base_url, temperature = resolve_agent_config(config, "enricher")

    token = config.get("github_token")
    if not token:
        warn_missing_github_token()

    stars_style = args.stars_style or config.get("stars_style") or "numeric"
    stats = enrich_archive(
        archive_path=archive, token=token,
        mode="agentx" if args.agentx else "archive",
        model=model or "", api_key=api_key, base_url=base_url,
        temperature=temperature,
        use_llm=not args.no_llm, limit=args.limit,
        no_backup=args.no_backup, status_cb=status,
        only=args.only, since=getattr(args, "since", None), stars_style=stars_style,
    )
    if args.agentx:
        suffix = ""
        if stats["missing_repos"]:
            suffix += f"; {stats['missing_repos']} unreachable"
        if stats["skipped_no_repo"]:
            suffix += f"; {stats['skipped_no_repo']} without a repo"
        if stats.get("gone"):
            suffix += f"; {stats['gone']} newly gone (404)"
        print(f"\nRefreshed {stats['refreshed']} agents{suffix}")
    else:
        print(f"\nResolved {stats['resolved']}/{stats['resolve_candidates']} repos · "
              f"refreshed stars for {stats['refreshed']}/{stats['refresh_candidates']}")


def cmd_download(args: argparse.Namespace, config: dict) -> int | None:
    from .downloader import download_pdfs

    if not args.archive and not args.doi and not args.arxiv:
        print("Error: --archive is required (or pass --doi/--arxiv to download "
              "standalone papers)", file=sys.stderr)
        return 1
    download_pdfs(
        archive_path=args.archive, out_dir=args.out, only=args.only,
        force=args.force, dois=args.doi, arxiv_ids=args.arxiv,
    )


def cmd_export_agentx(args: argparse.Namespace, config: dict) -> int | None:
    from .agentx_export import export_agentx

    category_map = {}
    if args.category_map:
        try:
            with open(args.category_map, "r", encoding="utf-8") as f:
                category_map = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error reading category map {args.category_map}: {exc}", file=sys.stderr)
            return 1

    llm_model = llm_api_key = llm_base_url = None
    llm_temperature = 0.0
    if args.llm_category:
        llm_model, llm_api_key, llm_base_url, llm_temperature = resolve_agent_config(config, "annotator")
        if not llm_api_key:
            print("Error: --llm-category needs a model API key (set --config or AWESCHOLAR_API_KEY).",
                  file=sys.stderr)
            return 1

    export_agentx(
        archive_path=args.archive, output_path=args.output,
        token=config.get("github_token"), category_map=category_map,
        default_category=args.default_category, source=args.source,
        source_url=args.source_url,
        categories=args.categories.split(",") if args.categories else None,
        exclude_snapshot=args.exclude_snapshot,
        llm_model=llm_model, llm_api_key=llm_api_key, llm_base_url=llm_base_url,
        llm_temperature=llm_temperature,
        status_cb=status,
    )


def cmd_digest(args: argparse.Namespace, config: dict) -> int | None:
    from .digest import run_digest, write_digest

    try:
        year, month = parse_month(args.month)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not os.path.exists(args.archive):
        print(f"Error: archive not found: {args.archive}", file=sys.stderr)
        return 1

    model = api_key = base_url = None
    temperature = 0.0
    if not args.no_llm and config.get("api_key"):
        model, api_key, base_url, temperature = resolve_agent_config(config, "reporter")

    try:
        markdown = run_digest(
            archive_path=args.archive, year=year, month=month,
            model=model or "", api_key=api_key, base_url=base_url,
            temperature=temperature, status_cb=status,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output = args.output or os.path.join(month_report_dir(year, month), "digest.md")
    write_digest(markdown, output)
    print(f"\nDigest saved to {output}")


def cmd_add(args: argparse.Namespace, config: dict) -> int | None:
    if getattr(args, "agentx", False):
        from .agentx.intake import IntakeError, add_agent, add_from_json

        archive = args.archive or "data/agents-snapshot.json"
        if not args.from_json and not args.repo:
            print("Error: pass owner/repo (single form) or --from-json FILE (batch)",
                  file=sys.stderr)
            return 1
        if args.from_json and args.repo:
            print("Error: --from-json takes no repo positional", file=sys.stderr)
            return 1
        try:
            if getattr(args, "from_json", None):
                add_from_json(archive, args.from_json,
                              token=config.get("github_token"))
            else:
                tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
                add_agent(archive, args.repo, category=args.category, name=args.name,
                          tags=tags, paper=args.paper, homepage=args.homepage,
                          description=args.description,
                          token=config.get("github_token"))
        except IntakeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print("Next: awescholar verify --agentx   # offline snapshot check")
        print("      git add data/agents-snapshot.json && git commit")
        return 0

    if args.repo or args.from_json:
        print("Error: repo intake needs --agentx (paper records go interactive, "
              "or use `updater search`)", file=sys.stderr)
        return 1
    if not args.archive:
        print("Error: --archive is required (or pass --agentx to register repos "
              "into an AgentX snapshot)", file=sys.stderr)
        return 1
    from .record import add_interactive

    add_interactive(archive_path=args.archive, categories=config.get("categories"))


def cmd_zotero_pull(args: argparse.Namespace, config: dict) -> int | None:
    """Zotero collection → pipeline JSON, ready for `updater update`."""
    from .zotero import DEFAULT_PULL_CATEGORY, DEFAULT_PULL_FILENAME, pull_collection

    api_key = _zotero_api_key(args, config)
    if not api_key:
        return 1
    try:
        result = pull_collection(
            args.collection, api_key,
            config.get("zotero_library_type") or "user",
            config.get("zotero_library_id"),
            category=args.category or DEFAULT_PULL_CATEGORY,
            limit=args.limit)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output = args.output or DEFAULT_PULL_FILENAME
    with open(output, "w", encoding="utf-8") as f:
        json.dump({result["category"]: result["records"]}, f,
                  indent=2, ensure_ascii=False)
    print(f"Pulled {len(result['records'])} item(s) from '{args.collection}' "
          f"into {output} (category '{result['category']}')")
    if result["records"]:
        print(f"Next : awescholar updater update --direction new2old "
              f"--input {output} --archive <your data.json>")
    return 0


def cmd_zotero_push(args: argparse.Namespace, config: dict) -> int | None:
    """Archive → Zotero collection. Dry run by default; --apply writes."""
    from .zotero import DEFAULT_REVIEW_FILENAME, push_records

    api_key = _zotero_api_key(args, config)
    if not api_key:
        return 1
    if not args.archive:
        print("Error: --archive is required", file=sys.stderr)
        return 1
    try:
        with open(args.archive, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: cannot read {args.archive}: {exc}", file=sys.stderr)
        return 1

    wanted = {c for c in (args.category or []) if c}
    records = [
        (category, paper)
        for category, papers in data.items()
        if not wanted or category in wanted
        for paper in papers
    ]
    if not records:
        print("Nothing to push"
              + (f" for categor{'y' if len(wanted) == 1 else 'ies'} "
                 f"{', '.join(sorted(wanted))}" if wanted else "")
              + f" in {args.archive}")
        return 0

    review_path = args.review or os.path.join(
        os.path.dirname(args.archive) or ".", DEFAULT_REVIEW_FILENAME)
    try:
        result = push_records(
            records, args.collection, api_key,
            config.get("zotero_library_type") or "user",
            config.get("zotero_library_id"),
            apply=args.apply, tags=args.tag or (), review_path=review_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    counts = result["counts"]
    print(f"Collection '{result['collection']}' on {result['library']}:")
    print(f"  to add               : {counts.get('to-add', 0)}")
    print(f"  already in collection: {counts.get('already-in-collection', 0)}")
    print(f"  in library elsewhere : {counts.get('in-library', 0)}")
    if not args.apply:
        if counts.get("to-add", 0):
            print(f"Dry run — review {result['reviewPath']}, "
                  "then rerun with --apply")
        return 0
    if not result["collectionKey"]:
        print("Error: collection could not be created or found; "
              "nothing was written", file=sys.stderr)
        return 1
    print(f"Created {result['created']} item(s) in Zotero")
    for failure in result["failures"]:
        print(f"  Warning: {failure}", file=sys.stderr)
    return 0


def _zotero_api_key(args: argparse.Namespace, config: dict) -> str | None:
    from .config import warn_missing_zotero_key

    key = (getattr(args, "zotero_api_key", None) or config.get("zotero_api_key"))
    if not key:
        warn_missing_zotero_key()
        return None
    return key


def cmd_zotero_pdf(args: argparse.Namespace, config: dict) -> int | None:
    """Title/DOI → OA PDF → files (--out) or item+PDF in the running Zotero."""
    from . import zotero_pdf

    email = args.unpaywall_email or config.get("zotero_unpaywall_email")
    if not email:
        print("Warning: no --unpaywall-email / config zotero.unpaywall_email — "
              "Unpaywall skipped; only arXiv DOI links remain.",
              file=sys.stderr)
    stats = zotero_pdf.run(
        args.queries, by=args.by, out_dir=args.out,
        collection=args.collection, unpaywall_email=email,
        ss_api_key=config.get("ss_api_key"))
    if stats["not_found"] or stats["no_pdf"] or stats.get("zotero", {}).get("failures"):
        return 1
    return 0


def cmd_verify(args: argparse.Namespace, config: dict) -> int | None:
    """Offline artifact gate — no network, no writes; CI runs this on PRs."""
    from .agentx.snapshot import read_snapshot
    from .agentx.validate import validate_snapshot_file

    if not args.agentx:
        print("Error: pass --agentx (only AgentX snapshot validation exists today)",
              file=sys.stderr)
        return 1
    archive = args.archive or "data/agents-snapshot.json"
    try:
        file = read_snapshot(archive)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Error: cannot read {archive}: {exc}", file=sys.stderr)
        return 1
    problems = validate_snapshot_file(file)
    if problems:
        print(f"{len(problems)} problem(s) in {archive}:")
        for line in problems:
            print(f"  - {line}")
        return 1
    agents = file.get("agents") if isinstance(file, dict) else None
    print(f"Snapshot OK: {len(agents) if isinstance(agents, list) else 0} agents, "
          "counts consistent.")
    return 0


# ── Reader (read-only archive queries) ───────────────────────

def cmd_reader_query(args: argparse.Namespace, config: dict) -> int | None:
    from .reader import run_query

    run_query(args.archive, args.query, top=args.top, category=args.category,
              as_json=args.json)


def cmd_reader_related(args: argparse.Namespace, config: dict) -> int | None:
    from .reader import load_seed, run_related

    seed = load_seed(args.archive, doi=args.doi, title=args.title, input_path=args.input)
    run_related(args.archive, seed, top=args.top, as_json=args.json)


def cmd_reader_recommend(args: argparse.Namespace, config: dict) -> int | None:
    from .reader import run_recommend

    model = api_key = base_url = None
    temperature = 0.0
    if args.llm:
        model, api_key, base_url, temperature = resolve_agent_config(config, "recommender")
        if not api_key:
            print("Error: --llm needs a model API key (set --config or AWESCHOLAR_API_KEY).")
            return 1
    run_recommend(args.archive, args.field, top=args.top, as_json=args.json, llm=args.llm,
                  model=model or "", api_key=api_key, base_url=base_url,
                  temperature=temperature, status_cb=status)


def cmd_reader_stats(args: argparse.Namespace, config: dict) -> int | None:
    from .reader import run_stats

    run_stats(args.archive, as_json=args.json, categories=args.category)


def _bind_preview_server(docs_dir: str, port: int):
    """Bind a 127.0.0.1 static server for docs_dir; tries up to 10 consecutive ports."""
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    handler = partial(SimpleHTTPRequestHandler, directory=docs_dir)
    for candidate in range(port, port + 10):
        try:
            return ThreadingHTTPServer(("127.0.0.1", candidate), handler)
        except OSError:
            continue
    return None


def serve_preview(docs_dir: str, port: int = 8000) -> None:
    """Serve docs_dir on 127.0.0.1 for local review; blocks until Ctrl+C."""
    server = _bind_preview_server(docs_dir, port)
    if server is None:
        print(f"Warning: ports {port}-{port + 9} on 127.0.0.1 are busy; skipping local preview.",
              flush=True)
        return
    print(f"\nLocal preview: http://127.0.0.1:{server.server_address[1]}/  (Ctrl+C to stop)",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("\nPreview stopped.")


def cmd_init(args: argparse.Namespace, config: dict) -> int | None:
    from .scaffold import run_init

    try:
        created = run_init(
            target_dir=args.target_dir,
            title=args.title,
            subtitle=args.subtitle,
            github_repo=args.github_repo,
            website=args.website,
            template=args.template,
            categories=args.category,
            include_zh=not args.no_zh,
            branding=not args.no_branding,
            embed_tables=args.tables,
            force=args.force,
        )
    except (FileExistsError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    for path in created:
        status(f"created {path}")
    print(f"\nScaffolded {len(created)} files. Next: edit config.json, then add papers with"
          " 'awescholar updater add --archive docs/data.json'.")
    if not args.no_serve:
        serve_preview(os.path.join(args.target_dir, "docs"), port=args.port)


def cmd_counts(args: argparse.Namespace, config: dict) -> int | None:
    from .readme import update_readme_counts

    readme_paths = args.readme or []
    if not readme_paths:
        seen: set[str] = set()
        for candidate in ("readme.md", "README.zh-CN.md", "README.md"):
            # case-insensitive filesystems make README.md match an existing readme.md
            if os.path.exists(candidate) and candidate.lower() not in seen:
                seen.add(candidate.lower())
                readme_paths.append(candidate)
    if not readme_paths:
        print("Error: no readme.md/README.md found in the current directory (use --readme)")
        return 1

    for readme_path in readme_paths:
        update_readme_counts(archive_path=args.archive, readme_path=readme_path)
        print(f"README counts refreshed at {readme_path}")


# ── Main ─────────────────────────────────────────────────────

def main(argv: list[str] | None = None, prog: str = "awescholar") -> int:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Automated scientific literature discovery and curation.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"{prog} {get_version()}")
    parser.add_argument("--config", type=str, help="Path to config.json")
    parser.add_argument("--ss-api-key", type=str,
                        help="Semantic Scholar API key (overrides config.json and environment)")
    parser.add_argument("--github-token", type=str,
                        help="GitHub API token (overrides config.json and environment)")
    sub = parser.add_subparsers(dest="command")

    # crawler
    crawler = sub.add_parser("crawler", help="Paper discovery pipeline")
    crawler_sub = crawler.add_subparsers(dest="crawler_command")

    p = crawler_sub.add_parser("search", help="Search Semantic Scholar for papers")
    p.add_argument("query", type=str, help="Search query string")
    p.add_argument("--limit", type=int, help="Max results (default: 100)")
    when = p.add_mutually_exclusive_group()
    when.add_argument("--date", type=str, help="Date range, e.g. 2025-01-01:2025-05-30")
    when.add_argument("--month", type=str,
                      help="Calendar month YYYY-MM, e.g. 2026-05 — sets the date range "
                           "and writes to month_reports/YYMM")
    when.add_argument("--period", type=str,
                      help="Half-month YYYY-MM-P (P=1|2), e.g. 2026-06-1 — days 01–15 or "
                           "16–end; writes to month_reports/YYMM_P")

    p = crawler_sub.add_parser("annotate", help="Annotate papers with domain and category")
    p.add_argument("--input", type=str, help="Path to papers JSON (default: read from DB)")

    p = crawler_sub.add_parser("filter", help="Select top papers by quality and relevance")
    p.add_argument("--input", type=str, help="Path to annotated JSON (default: {db_path}/updater.json)")
    p.add_argument("--limit", type=int, help="Number of papers to keep (default: 20)")

    p = crawler_sub.add_parser("report", help="Generate Markdown report from filtered data")
    p.add_argument("input", type=str, nargs="?", help="Path to filtered JSON (default: {db_path}/updater_filter.json)")
    p.add_argument("-o", "--output", type=str, help="Output file path")

    p = crawler_sub.add_parser("run", help="Run full pipeline: search, annotate, filter, report")
    p.add_argument("query", type=str, nargs="?", help="Search query string (or set in config)")
    p.add_argument("--limit-search", type=int, help="Max search results (default: 100)")
    p.add_argument("--limit-filter", type=int, help="Papers to keep after filter (default: 20)")
    when = p.add_mutually_exclusive_group()
    when.add_argument("--date", type=str, help="Date range, e.g. 2025-01-01:2025-05-30")
    when.add_argument("--month", type=str,
                      help="Calendar month YYYY-MM, e.g. 2026-05 — sets the date range, "
                           "db_path (month_reports/YYMM), and the report name (report.md)")
    when.add_argument("--period", type=str,
                      help="Half-month YYYY-MM-P (P=1|2), e.g. 2026-06-1 — sets the date "
                           "range (01–15 or 16–end), db_path (month_reports/YYMM_P), and "
                           "the report name (report.md)")
    p.add_argument("-o", "--output", type=str, help="Report output path")

    # updater — every subcommand mutates the project data JSON (or its review files)
    updater = sub.add_parser("updater", help="Archive data management")
    updater_sub = updater.add_subparsers(dest="updater_command")

    p = updater_sub.add_parser("update", help="Merge data between new results and project data JSON")
    p.add_argument("--direction", choices=["new2old", "old2new"], required=True)
    p.add_argument("--input", type=str, help="Path to new data JSON")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--no-dedupe", action="store_true",
                   help="Append everything; skip near-duplicate detection "
                        "(preprint/published pairs would both be added)")

    p = updater_sub.add_parser("dedupe", help="Resolve held-back duplicate pairs from a dedupe review file")
    p.add_argument("--review", type=str, required=True,
                   help="Path to dedupe_review.json written by 'updater update'")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--keep", choices=["newer", "published", "both"], required=True,
                   help="newer: latest year wins · published: non-preprint wins · both: keep two entries")

    p = updater_sub.add_parser("publish-scan",
                               help="Scan archived preprints for published versions (Semantic Scholar); "
                                    "queue upgrades into a review file, apply with --apply")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--apply", action="store_true",
                   help="Upgrade the archive after scanning (default: dry run, review file only). "
                        "With --review pointing at an existing file, apply it without rescanning")
    p.add_argument("--review", type=str,
                   help="Review file path (default: publish_review.json next to the archive)")
    p.add_argument("--only", action="append",
                   help="Scope to entries whose DOI equals this or whose title contains it (repeatable)")
    p.add_argument("--pair", type=str, nargs=2, metavar=("PREPRINT", "PUBLISHED"),
                   help="Manual pair for retitled work no database links: queue the upgrade "
                        "from these two DOIs instead of scanning (add --apply to upgrade at once)")
    p.add_argument("--limit", type=int, help="Check at most N preprints (default: all)")
    p.add_argument("--no-title-search", action="store_true",
                   help="Only verify by DOI; skip the title-search fallback for DOI misses")
    p.add_argument("--no-backup", action="store_true", help="Do not create a backup of the archive before applying")

    p = updater_sub.add_parser("search", help="Search Semantic Scholar by title/DOI and add to project data JSON")
    p.add_argument("queries", nargs="*", help="Paper titles or DOIs (omit to enter interactively)")
    p.add_argument("--archive", type=str, help="Path to project data JSON")
    p.add_argument("--json-file", type=str, help="Save to a flat JSON list for review (instead of archive)")
    p.add_argument("--by", choices=["title", "doi"], default="title", help="Search by title or DOI (default: title)")
    p.add_argument("--category", type=str, help="Category for added papers (default: first category in archive)")
    p.add_argument("--code-url", type=str,
                   help="Known code repo (owner/repo or full URL) written into codeUrl of every added paper")
    p.add_argument("--stars-style", choices=["badge", "numeric"],
                   help="githubStars shape for --code-url writes (default: archive.stars_style config, else numeric)")
    p.add_argument("--annotate", action="store_true",
                   help="Fill the domain line of added papers with the configured annotator LLM")

    p = updater_sub.add_parser(
        "add", help="Interactively add a single record to project data JSON; "
                    "with --agentx, register a GitHub repo into an AgentX snapshot")
    p.add_argument("repo", nargs="?", type=str, metavar="owner/repo",
                   help="repo to register (with --agentx, single form)")
    p.add_argument("--archive", type=str,
                   help="Path to project data JSON; with --agentx, the AgentX "
                        "snapshot (default: data/agents-snapshot.json)")
    p.add_argument("--agentx", action="store_true",
                   help="Treat --archive as an AgentX snapshot; validate the repo, "
                        "fetch live metrics, apply the registry tag/category policy")
    p.add_argument("--from-json", type=str, metavar="FILE",
                   help="Batch-intake a candidate file from `awescholar render agentx` "
                        "(with --agentx): {\"agents\": [...]} or a bare record array; "
                        "all-or-nothing")
    p.add_argument("--category", type=str, metavar="SLUG",
                   help="AgentX category slug (with --agentx, single form; required)")
    p.add_argument("--tags", type=str, metavar='"A,B"',
                   help="Comma-separated objective attributions (with --agentx)")
    p.add_argument("--name", type=str, help="Display name (default: repo name segment)")
    p.add_argument("--paper", type=str, help="Peer-reviewed paper link")
    p.add_argument("--homepage", type=str, help="Project homepage")
    p.add_argument("--description", type=str,
                   help="One-line summary (default: the GitHub repo description)")

    p = updater_sub.add_parser("backfill", help="Fill empty fields from publication databases "
                                                "(Semantic Scholar, Crossref, OpenAlex)")
    p.add_argument("--archive", type=str,
                   help="Path to project data JSON; with --agentx, the AgentX "
                        "snapshot (default: data/agents-snapshot.json)")
    p.add_argument("--fields", action="append",
                   choices=["affiliation", "citations", "paper-meta", "venue-tags"],
                   metavar="FIELD",
                   help="Fill only these fields (repeatable): affiliation = affiliation+team, "
                        "citations = citation counts (default: both). With --agentx: "
                        "paper-meta = resolve paperMeta and its registered venue tag from paper clues, "
                        "venue-tags = sync registered paper venues into tags, citations = refresh citation "
                        "counts (default: paper-meta + citations)")
    p.add_argument("--only", action="append",
                   help="Scope to entries whose DOI equals this or whose title contains it "
                        "(repeatable; with --agentx, slug/name/repo/paper-meta title·DOI "
                        "containing it instead)")
    p.add_argument("--agentx", action="store_true",
                   help="Backfill an AgentX snapshot instead of a paper archive")
    p.add_argument("--refresh", action="store_true",
                   help="With --agentx --fields paper-meta: re-resolve records that "
                        "already have paperMeta (like the old enrich-papers --force)")
    p.add_argument("--no-backup", action="store_true", help="Do not create a backup of the archive before updating")

    p = updater_sub.add_parser("enrich", help="Fill empty codeUrl from GitHub search and refresh "
                                              "githubStars; with --agentx, refresh an AgentX registry snapshot instead")
    p.add_argument("--archive", type=str,
                   help="Path to project data JSON (awesome-list) or, with --agentx, an AgentX snapshot "
                        "JSON (default with --agentx: data/agents-snapshot.json)")
    p.add_argument("--limit", type=int, help="Resolve at most N papers without a repo (metrics refresh is unbounded; ignored in --agentx)")
    p.add_argument("--only", action="append",
                   help="Scope to entries whose DOI equals this or whose title contains it (repeatable)")
    p.add_argument("--since", type=str, metavar="YYYY-MM-DD",
                   help="Scope to entries added on/after this date (needs addedAt, written by "
                        "updater search/update since this release); legacy entries without "
                        "addedAt are always included")
    p.add_argument("--stars-style", choices=["badge", "numeric"],
                   help="githubStars shape this archive keeps (default: archive.stars_style config, else numeric)")
    p.add_argument("--no-llm", action="store_true",
                   help="Skip the LLM tiebreak; only unambiguous matches resolve (ignored in --agentx)")
    p.add_argument("--no-backup", action="store_true", help="Do not create a backup of the archive before updating")
    p.add_argument("--agentx", action="store_true",
                   help="Treat --archive as an AgentX snapshot (top-level {agents, counts}); refresh "
                        "stars/pushedAt/openIssues/language/license/description/homepage/archived "
                        "and preserve status, slug, paperMeta, category, etc.")

    p = updater_sub.add_parser("download", help="Download open-access PDFs (arXiv direct + OpenAlex "
                                                "OA links; bot-gated publisher pages are skipped, not forced)")
    p.add_argument("--archive", type=str,
                   help="Path to project data JSON; download PDFs for its records")
    p.add_argument("--only", action="append",
                   help="Scope to entries whose DOI equals this or whose title contains it (repeatable)")
    p.add_argument("--doi", action="append", metavar="DOI",
                   help="Download this DOI directly, no archive needed (repeatable)")
    p.add_argument("--arxiv", action="append", metavar="ID",
                   help="Download this arXiv ID directly, no archive needed (repeatable)")
    p.add_argument("--out", type=str, default="pdfs", help="Output directory (default: pdfs/)")
    p.add_argument("--force", action="store_true",
                   help="Re-download even when the target file already exists")

    # render — derive artifacts from the project data JSON; the archive is never modified
    render = sub.add_parser("render", help="Render artifacts (README tables, counts, RSS, digests, agentx exports) "
                                           "from project data JSON")
    render_sub = render.add_subparsers(dest="render_command")

    p = render_sub.add_parser("readme", help="Generate README tables from project data JSON")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--readme", type=str, help="Output README path")
    p.add_argument("--title", type=str, help="Project title")
    p.add_argument("--description", type=str, help="Project description")
    p.add_argument("--no-backup", action="store_true", help="Do not create a backup of the README before updating")

    p = render_sub.add_parser("counts", help="Refresh website-first README paper counts from project data JSON")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--readme", action="append",
                   help="README path, repeatable (default: readme.md + README.zh-CN.md in cwd)")

    p = render_sub.add_parser("rss", help="Generate RSS feed from project data JSON")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("-o", "--output", type=str, help="Output RSS file path")
    p.add_argument("--title", type=str, help="Feed title")
    p.add_argument("--link", type=str, help="Channel link URL")
    p.add_argument("--rss-url", type=str, help="RSS self-link URL")
    p.add_argument("--description", type=str, help="Channel description")

    p = render_sub.add_parser("digest", help="Summarize archive papers from one month as a Markdown digest")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--month", type=str, required=True, help="Month to summarize, e.g. 2026-05")
    p.add_argument("-o", "--output", type=str,
                   help="Output file (default: month_reports/YYMM/digest.md)")
    p.add_argument("--no-llm", action="store_true",
                   help="Skip the LLM narrative; emit tables only (no model key needed)")

    p = render_sub.add_parser("agentx", help="Export papers with GitHub repos as AgentX candidate agents "
                                              "(snapshot-shaped JSON for `awescholar updater add --agentx --from-json`)")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("-o", "--output", type=str, required=True, help="Output candidate JSON path")
    p.add_argument("--category-map", type=str,
                   help="JSON file mapping archive categories to agentx category slugs")
    p.add_argument("--default-category", type=str, default="platforms",
                   help="agentx category slug for unmapped papers (default: platforms)")
    p.add_argument("--source", type=str, default="awescholar",
                   help="Provenance source recorded on exported agents (default: awescholar)")
    p.add_argument("--source-url", type=str, help="Provenance URL recorded on exported agents")
    p.add_argument("--categories", type=str,
                   help="Comma-separated archive categories to export (default: all)")
    p.add_argument("--exclude-snapshot", type=str,
                   help="agentx agents-snapshot.json whose repos are skipped as already registered")
    p.add_argument("--llm-category", action="store_true",
                   help="classify each candidate's agentx category with the configured model "
                        "(needs --exclude-snapshot for the category list)")

    # reader
    reader = sub.add_parser("reader", help="Read-only queries over the project data JSON")
    reader_sub = reader.add_subparsers(dest="reader_command")

    p = reader_sub.add_parser("query", help="Search the archive by keywords (offline)")
    p.add_argument("query", type=str, help="Keyword query over title/domain/abstract/venue/team")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--top", type=int, default=10, help="Max hits (default: 10)")
    p.add_argument("--category", type=str, help="Restrict to one category")
    p.add_argument("--json", action="store_true", help="Machine-readable output for agents")

    p = reader_sub.add_parser("related", help="Find archive papers related to a seed paper")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--doi", type=str, help="Seed DOI (must exist in the archive)")
    p.add_argument("--title", type=str, help="Seed title (external titles are fine)")
    p.add_argument("--input", type=str, help="Path to a JSON file with exactly one paper record")
    p.add_argument("--top", type=int, default=5, help="Max hits (default: 5)")
    p.add_argument("--json", action="store_true", help="Machine-readable output for agents")

    p = reader_sub.add_parser("recommend", help="Recommend must-read papers for a research field")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--field", type=str, required=True, help="Research field or interests")
    p.add_argument("--top", type=int, default=10, help="Picks to return (default: 10)")
    p.add_argument("--llm", action="store_true",
                   help="Rank candidates with the configured LLM (needs --config)")
    p.add_argument("--json", action="store_true", help="Machine-readable output for agents")

    p = reader_sub.add_parser("stats", help="Archive statistics: counts, categories, date range")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--category", type=str, action="append",
                   help="Restrict to one or more categories (default: all categories in the archive)")
    p.add_argument("--json", action="store_true", help="Machine-readable output for agents")

    # zotero — exchange with the reader's personal Zotero library
    zotero = sub.add_parser("zotero", help="Zotero library exchange: pull a collection "
                                           "into pipeline JSON, push an archive into a collection")
    zotero.add_argument("--zotero-api-key", type=str,
                        help="Zotero Web API key (default: config zotero.api_key / ZOTERO_API_KEY)")
    zotero.add_argument("--zotero-library-type", choices=["user", "group"], default=None,
                        help="Zotero library to read/write (default: user)")
    zotero.add_argument("--zotero-library-id", type=str,
                        help="Library id (a user library resolves it from the key; "
                             "a group library requires it)")
    zotero_sub = zotero.add_subparsers(dest="zotero_command")

    p = zotero_sub.add_parser("pull", help="Map one Zotero collection into pipeline JSON "
                                           "for `updater update` (read-only, never creates)")
    p.add_argument("--collection", type=str, required=True, help="Zotero collection name")
    p.add_argument("-o", "--output", type=str, default=None,
                   help="Output JSON path (default: zotero_papers.json)")
    p.add_argument("--category", type=str, default=None,
                   help="Category key for the output records (default: Zotero)")
    p.add_argument("--limit", type=int, default=None,
                   help="Cap the number of pulled records")

    p = zotero_sub.add_parser("push", help="Push archive records into a Zotero collection "
                                           "(dry run by default; --apply writes)")
    p.add_argument("--archive", type=str, required=True,
                   help="Path to the project data JSON")
    p.add_argument("--collection", type=str, required=True,
                   help="Target Zotero collection name (created on --apply when missing)")
    p.add_argument("--category", type=str, action="append",
                   help="Restrict to one archive category (repeatable; default: all)")
    p.add_argument("--tag", type=str, action="append",
                   help="Extra Zotero tag to attach (repeatable; every item also "
                        "gets 'awescholar' plus its archive category)")
    p.add_argument("--apply", action="store_true",
                   help="Create the 'to-add' items in Zotero (default: dry run + review file)")
    p.add_argument("--review", type=str,
                   help="Review queue path (default: zotero_review.json next to the archive)")

    p = zotero_sub.add_parser("pdf", help="Find open-access PDFs by title/DOI; save into "
                                          "the running Zotero desktop, or --out DIR for files only")
    p.add_argument("queries", nargs="+", metavar="QUERY",
                   help="Paper titles or DOIs")
    p.add_argument("--by", choices=["title", "doi"], default="title",
                   help="Interpret queries as titles or DOIs (default: title)")
    p.add_argument("--out", type=str, metavar="DIR",
                   help="Write the PDFs into this directory instead of Zotero "
                        "(no Zotero needed; attach by drag for existing items)")
    p.add_argument("--collection", type=str, metavar="NAME",
                   help="Refuse to save unless this collection is selected in Zotero "
                        "(the save lands in the selected collection, like the browser extension)")
    p.add_argument("--unpaywall-email", type=str,
                   help="Email for the Unpaywall API (default: config zotero.unpaywall_email)")

    # verify — offline artifact gate (CI runs exactly this)
    p = sub.add_parser("verify", help="Offline artifact validation (no network, no writes); "
                                      "CI runs this on every PR")
    p.add_argument("--agentx", action="store_true",
                   help="Validate an AgentX snapshot (default: data/agents-snapshot.json)")
    p.add_argument("--archive", type=str,
                   help="Path to the artifact; with --agentx, the AgentX snapshot "
                        "(default: data/agents-snapshot.json)")

    # init
    p = sub.add_parser("init", help="Scaffold a new curated paper-list repository")
    p.add_argument("target_dir", type=str, nargs="?", default=".",
                   help="Target directory (default: current directory)")
    p.add_argument("--title", type=str, help="Project title (default: Awesome AI Meets Biology)")
    p.add_argument("--subtitle", type=str, help="Short description used in header, site tagline, and meta")
    p.add_argument("--github-repo", type=str, help="owner/repo for badges and links")
    p.add_argument("--website", type=str, help="Website URL (custom domain writes docs/CNAME)")
    p.add_argument("--template", choices=["bio", "vt"], default="bio",
                   help="Website template: bio = Awesome-AI-Meets-Biology style, vt = Awesome-AI-Virtual-Tumor style")
    p.add_argument("--category", action="append", dest="category",
                   help="Category name (repeatable; default: Biology-themed starter categories)")
    p.add_argument("--no-zh", action="store_true", help="Skip README.zh-CN.md")
    p.add_argument("--no-branding", action="store_true", help="Skip ecosystem/support sections and Webioinfo links")
    p.add_argument("--tables", action="store_true",
                   help="Also embed AWESCHOLAR table markers (classic in-README tables)")
    p.add_argument("--no-serve", action="store_true",
                   help="Skip serving a local preview of docs/ after scaffolding")
    p.add_argument("--port", type=int, default=8000,
                   help="Local preview port (default: 8000; auto-increments while busy)")
    p.add_argument("--force", action="store_true", help="Proceed even if the target directory is not empty")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "ss_api_key", None):
        config["ss_api_key"] = args.ss_api_key

    if getattr(args, "github_token", None):
        config["github_token"] = args.github_token

    if args.command == "zotero":
        if not args.zotero_command:
            zotero.print_help()
            return 0
        if args.zotero_api_key:
            config["zotero_api_key"] = args.zotero_api_key
        if args.zotero_library_type:
            config["zotero_library_type"] = args.zotero_library_type
        if args.zotero_library_id:
            config["zotero_library_id"] = args.zotero_library_id
        handlers = {"pull": cmd_zotero_pull, "push": cmd_zotero_push,
                    "pdf": cmd_zotero_pdf}
        return handlers[args.zotero_command](args, config) or 0

    if args.command == "verify":
        return cmd_verify(args, config) or 0

    if args.command == "init":
        return cmd_init(args, config) or 0

    if args.command == "crawler":
        if not args.crawler_command:
            crawler.print_help()
            return 0
        handlers = {
            "search": cmd_search, "annotate": cmd_annotate, "filter": cmd_filter,
            "report": cmd_report, "run": cmd_run,
        }
        return handlers[args.crawler_command](args, config) or 0

    if args.command == "updater":
        if not args.updater_command:
            updater.print_help()
            return 0
        handlers = {
            "update": cmd_update, "search": cmd_search_record, "add": cmd_add,
            "dedupe": cmd_dedupe, "publish-scan": cmd_publish_scan,
            "backfill": cmd_backfill, "enrich": cmd_enrich, "download": cmd_download,
        }
        return handlers[args.updater_command](args, config) or 0

    if args.command == "render":
        if not args.render_command:
            render.print_help()
            return 0
        handlers = {
            "readme": cmd_readme, "counts": cmd_counts, "rss": cmd_rss,
            "digest": cmd_digest, "agentx": cmd_export_agentx,
        }
        return handlers[args.render_command](args, config) or 0

    if args.command == "reader":
        if not args.reader_command:
            reader.print_help()
            return 0
        try:
            handlers = {
                "query": cmd_reader_query, "related": cmd_reader_related,
                "recommend": cmd_reader_recommend, "stats": cmd_reader_stats,
            }
            return handlers[args.reader_command](args, config) or 0
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
