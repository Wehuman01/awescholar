"""Read-only queries over the curated project data JSON (the reader face).

Everything here answers questions about an existing archive — it never writes,
backs up, or mutates any file. Archives hold the 11 project fields (no
abstract); updater pipeline JSON also carries `abstract` and
`reason_for_inclusion`, and scoring uses those whenever present.
"""

import json
import os
import re
from collections import Counter
from difflib import SequenceMatcher

from pydantic import BaseModel

from .data_fields import normalize_name, normalize_title

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(["a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from", "has", "have", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "using", "via", "with", "without", "toward", "towards", "between", "among", "across", "can", "could", "will", "would", "may", "might", "shall", "should", "must", "not", "no", "nor", "but", "if", "then", "than", "when", "where", "which", "who", "whom", "whose", "what", "how", "why", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "only", "own", "same", "so", "too", "very", "just", "don", "now", "based", "paper", "study", "work", "novel", "new"])

# Field weights for term-overlap scoring: a title hit says more than a venue hit.
FIELD_WEIGHTS = (
    ("title", 3.0),
    ("domain", 2.0),
    ("abstract", 1.5),
    ("venue", 1.0),
    ("team", 0.5),
)


class RecommendationPick(BaseModel):
    title: str
    doi: str = ""
    reason: str = ""


class Recommendation(BaseModel):
    picks: list[RecommendationPick]


def tokenize(text) -> list[str]:
    """Lowercase word tokens, minus stopwords, with naive plural folding."""
    out = []
    for token in _TOKEN_RE.findall(str(text or "").casefold()):
        if len(token) <= 1 or token in _STOPWORDS:
            continue
        if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
            token = token[:-1]
        out.append(token)
    return out


def parse_stars(value) -> int:
    """Parse githubStars (int, '1.2k', '3,400', ...) to an int for ranking."""
    s = str(value or "").strip().casefold().replace(",", "")
    if not s:
        return 0
    mult = 1
    if s.endswith("k"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


def paper_year(paper: dict) -> str:
    return str(paper.get("year") or "")[:10]


def load_papers(archive_path: str) -> list[dict]:
    """Flatten an archive (categorized dict or plain list) into paper dicts
    tagged with their `category`."""
    if not os.path.exists(archive_path):
        raise FileNotFoundError(f"Archive not found: {archive_path}")
    with open(archive_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return [dict(p) for p in data if isinstance(p, dict)]

    papers = []
    for category, entries in data.items():
        if isinstance(entries, list):
            papers.extend({**p, "category": category} for p in entries if isinstance(p, dict))
    return papers


def score_paper(paper: dict, terms: list[str]) -> tuple[float, list[str]]:
    """Weighted term overlap in [0, 1]. A term counts once, at its best field:
    score = sum(best weight per matched term) / (title weight × distinct terms)."""
    term_order = list(dict.fromkeys(terms))
    if not term_order:
        return 0.0, []
    best: dict[str, float] = {}
    for field, weight in FIELD_WEIGHTS:
        tokens = set(tokenize(paper.get(field)))
        for term in term_order:
            if term in tokens and weight > best.get(term, 0.0):
                best[term] = weight
    if not best:
        return 0.0, []
    score = min(sum(best.values()) / (3.0 * len(term_order)), 1.0)
    return score, [t for t in term_order if t in best]


def _hit(paper: dict, score: float, matched: list[str]) -> dict:
    hit = {
        "score": round(score, 2),
        "matched": matched,
        "category": paper.get("category", ""),
        "title": paper.get("title", ""),
        "year": paper_year(paper)[:7],
        "team": paper.get("team", ""),
        "domain": paper.get("domain", ""),
        "venue": paper.get("venue", ""),
        "doi": paper.get("doi", ""),
        "paperUrl": paper.get("paperUrl", ""),
        "githubStars": paper.get("githubStars", ""),
    }
    if paper.get("codeUrl"):
        hit["codeUrl"] = paper["codeUrl"]
    if paper.get("reason_for_inclusion"):
        hit["reason_for_inclusion"] = paper["reason_for_inclusion"]
    return hit


def _resolve_category(papers: list[dict], category: str) -> str:
    names = {p.get("category", "") for p in papers}
    wanted = category.casefold()
    match = next((n for n in names if n.casefold() == wanted), None)
    if match is None:
        match = next((n for n in names if wanted in n.casefold() or n.casefold() in wanted), None)
    if match is None:
        raise ValueError(
            f"Unknown category: {category}. Available: {', '.join(sorted(n for n in names if n))}"
        )
    return match


# ── query ────────────────────────────────────────────────────

def query(archive_path: str, query_str: str, top: int = 10,
          category: str | None = None) -> tuple[list[dict], dict]:
    """Keyword search over title/domain/abstract/venue/team. Returns (hits, meta)."""
    papers = load_papers(archive_path)
    if category:
        match = _resolve_category(papers, category)
        papers = [p for p in papers if p.get("category") == match]

    terms = tokenize(query_str)
    scored = []
    for paper in papers:
        score, matched = score_paper(paper, terms)
        if score > 0:
            scored.append(_hit(paper, score, matched))
    scored.sort(key=lambda h: (-h["score"], h["title"].casefold()))
    meta = {
        "query": query_str,
        "terms": terms,
        "total": len(papers),
        "categories": len({p.get("category", "") for p in papers}),
    }
    return scored[:top], meta


# ── related ──────────────────────────────────────────────────

def load_seed(archive_path: str, doi: str | None = None, title: str | None = None,
              input_path: str | None = None) -> dict:
    """Resolve the seed paper for `reader related`.

    `--doi` must exist in the archive; `--title` falls back to an external seed
    (title-only) when not found; `--input` takes a JSON file holding exactly
    one paper record (a categorized dict counts its total entries).
    """
    if input_path:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Not found: {input_path}")
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and any(isinstance(v, list) for v in data.values()):
            flat = [{**p, "category": c} for c, entries in data.items()
                    if isinstance(entries, list) for p in entries if isinstance(p, dict)]
            data = flat
        if not isinstance(data, list):
            data = [data]
        if len(data) != 1:
            raise ValueError(
                f"--input must contain exactly one paper record (found {len(data)}). "
                "Extract the one you want into its own file."
            )
        return data[0]

    if doi:
        for paper in load_papers(archive_path):
            if str(paper.get("doi") or "").casefold() == doi.casefold():
                return paper
        raise ValueError(
            f"DOI {doi} not found in archive. For a paper outside the archive, use "
            "--input with a record containing at least a title (ideally an abstract)."
        )

    if title:
        wanted = normalize_title(title)
        for paper in load_papers(archive_path):
            if normalize_title(paper.get("title")) == wanted:
                return paper
        return {"title": title}

    raise ValueError("Provide --doi, --title, or --input to identify the seed paper.")


def _seed_terms(seed: dict) -> list[str]:
    terms = tokenize(seed.get("title")) + tokenize(seed.get("domain"))
    if seed.get("abstract"):
        terms += [t for t, _ in Counter(tokenize(seed["abstract"])).most_common(15)]
    return list(dict.fromkeys(terms))


def related(archive_path: str, seed: dict, top: int = 5) -> tuple[list[dict], dict]:
    """Score archive papers against a seed paper (in-archive or external)."""
    papers = load_papers(archive_path)
    terms = _seed_terms(seed)
    seed_doi = str(seed.get("doi") or "").casefold()
    seed_title = normalize_title(seed.get("title"))
    seed_team = normalize_name(seed.get("team"))

    scored = []
    for paper in papers:
        if seed_doi and str(paper.get("doi") or "").casefold() == seed_doi:
            continue
        if seed_title and normalize_title(paper.get("title")) == seed_title:
            continue
        score, matched = score_paper(paper, terms)
        if score <= 0:
            continue
        if seed.get("category") and paper.get("category") == seed.get("category"):
            score += 0.05
        if seed_team and normalize_name(paper.get("team")) == seed_team:
            score += 0.05
        scored.append(_hit(paper, score, matched))

    scored.sort(key=lambda h: (-h["score"], h["title"].casefold()))
    meta = {"seed": seed.get("title", ""), "terms": terms[:8]}
    return scored[:top], meta


# ── recommend ────────────────────────────────────────────────

def recommend(archive_path: str, field: str, top: int = 10) -> tuple[list[dict], dict]:
    """Offline must-read ranking: route to categories whose names match the
    field terms, then rank by term relevance, GitHub stars, and recency."""
    papers = load_papers(archive_path)
    terms = tokenize(field)
    category_names = sorted({p.get("category", "") for p in papers})
    field_set = set(terms)
    routed = [c for c in category_names if set(tokenize(c)) & field_set]
    pool = [p for p in papers if p.get("category") in routed] if routed else papers

    ranked = []
    for paper in pool:
        score, matched = score_paper(paper, terms)
        ranked.append((score, parse_stars(paper.get("githubStars")), paper_year(paper),
                       normalize_title(paper.get("title")), paper, matched))
    ranked.sort(key=lambda r: r[3])               # title asc
    ranked.sort(key=lambda r: r[2], reverse=True)  # year desc
    ranked.sort(key=lambda r: r[1], reverse=True)  # stars desc
    ranked.sort(key=lambda r: r[0], reverse=True)  # relevance desc

    hits = [_hit(paper, score, matched) for score, _, _, _, paper, matched in ranked[:top]]
    meta = {"field": field, "mode": "offline", "routed_categories": routed,
            "candidates": len(pool)}
    return hits, meta


def recommend_with_llm(archive_path: str, field: str, top: int = 10,
                       model: str = "", api_key: str | None = None,
                       base_url: str | None = None, temperature: float = 0.0,
                       status_cb=None) -> tuple[list[dict], dict]:
    """LLM-ranked must-read list. Candidates come from offline relevance (top
    40); the model picks and motivates; picks are matched back to archive
    entries so every recommendation carries a link and a category."""
    from .llm import complete
    from .prompts import RECOMMENDER

    status = status_cb or (lambda msg: None)
    candidates, _ = recommend(archive_path, field, top=40)
    if not candidates:
        return [], {"field": field, "mode": "llm", "model": model,
                    "candidates": 0, "unmatched": 0}

    payload = [{"title": h["title"], "domain": h["domain"], "venue": h["venue"],
                "year": h["year"]} for h in candidates]
    status(f"ranking {len(payload)} candidates with {model}")
    user = (f"Researcher field/interests: {field}\n"
            f"Picks requested: {top}\n\nCandidates:\n{json.dumps(payload, ensure_ascii=False)}")
    result = complete(model=model, system=RECOMMENDER, user=user,
                      response_format=Recommendation, api_key=api_key, base_url=base_url,
                      temperature=temperature)

    by_title = {normalize_title(p.get("title")): p for p in load_papers(archive_path)}
    hits, unmatched = [], 0
    for pick in result.picks[:top]:
        paper = by_title.get(normalize_title(pick.title))
        if paper is None:
            near = next((p for t, p in by_title.items()
                         if SequenceMatcher(None, normalize_title(pick.title), t).ratio() >= 0.95), None)
            paper = near
        if paper is None:
            unmatched += 1
            continue
        hit = _hit(paper, 0.0, [])
        hit["reason"] = pick.reason
        hits.append(hit)

    meta = {"field": field, "mode": "llm", "model": model,
            "candidates": len(payload), "unmatched": unmatched}
    return hits, meta


# ── stats ────────────────────────────────────────────────────

def stats(archive_path: str, categories: list[str] | None = None) -> dict:
    papers = load_papers(archive_path)
    if categories is not None:
        wanted = set(categories)
        papers = [p for p in papers if p.get("category") in wanted]

    counts: dict[str, dict] = {}
    for paper in papers:
        name = paper.get("category", "")
        entry = counts.setdefault(name, {"count": 0, "newest": ""})
        entry["count"] += 1
        entry["newest"] = max(entry["newest"], paper_year(paper))

    if categories is not None:
        ordered = [name for name in categories if name in counts]
    else:
        ordered = [name for name, _ in sorted(counts.items(),
                                              key=lambda kv: (-kv[1]["count"], kv[0]))]

    years = [paper_year(p) for p in papers if paper_year(p)]
    return {
        "total": len(papers),
        "categories": [
            {"name": name, **counts[name]}
            for name in ordered
        ],
        "date_range": [min(years), max(years)] if years else ["", ""],
        "venues": len({p.get("venue") for p in papers if p.get("venue")}),
        "teams": len({p.get("team") for p in papers if p.get("team")}),
    }


# ── rendering ────────────────────────────────────────────────

def _trunc(text: str, width: int) -> str:
    text = str(text or "")
    return text if len(text) <= width else text[: width - 1] + "..."


def _print_table(rows: list[dict], show_matched: bool = False) -> None:
    print(f"\n  {'RANK':<5} {'SCORE':<5} {'DATE':<7}  {'TITLE':<44}  CATEGORY")
    for rank, hit in enumerate(rows, 1):
        title = _trunc(hit["title"], 44)
        print(f"  {rank:<5} {hit['score']:<5.2f} {hit['year'] or '-':<7}  {title:<44}  {hit['category']}")
        if show_matched and hit.get("matched"):
            print(f"        {'':5} {'':7}  matched: {', '.join(hit['matched'])}")


def _print_detail(hit: dict) -> None:
    print("\n  Detail (rank 1):")
    print(f"    Title    {hit['title']}")
    print(f"    Author   {_trunc(hit['team'], 60)} · {hit['venue']}")
    if hit["doi"]:
        print(f"    DOI      {hit['doi']}")
    if hit.get("reason_for_inclusion"):
        print(f"    Curated  {_trunc(hit['reason_for_inclusion'], 200)}")
    if hit.get("reason"):
        print(f"    Why      {_trunc(hit['reason'], 200)}")
    if hit["paperUrl"]:
        print(f"    Link     {hit['paperUrl']}")


def run_query(archive_path: str, query_str: str, top: int = 10,
              category: str | None = None, as_json: bool = False) -> None:
    hits, meta = query(archive_path, query_str, top=top, category=category)
    if as_json:
        print(json.dumps({"archive": archive_path, **meta, "hits": hits},
                         ensure_ascii=False, indent=2))
        return
    print(f"\n  Archive : {archive_path} · {meta['total']} papers · "
          f"{meta['categories']} categories   [offline]")
    print(f"  Query   : {query_str}")
    print(f"  Hits    : {len(hits)}")
    if hits:
        _print_table(hits)
        _print_detail(hits[0])
    else:
        print("\n  No matches. Try broader or fewer terms.")
    print("\n  Agents: add --json for machine-readable output.")


def run_related(archive_path: str, seed: dict, top: int = 5, as_json: bool = False) -> None:
    hits, meta = related(archive_path, seed, top=top)
    if as_json:
        print(json.dumps({"archive": archive_path, **meta, "hits": hits},
                         ensure_ascii=False, indent=2))
        return
    print(f"\n  Seed    : {_trunc(meta['seed'], 66)}")
    print(f"  Terms   : {', '.join(meta['terms'])}")
    print(f"  Hits    : {len(hits)}")
    if hits:
        _print_table(hits, show_matched=True)
    else:
        print("\n  No related papers found in the archive.")


def run_recommend(archive_path: str, field: str, top: int = 10, as_json: bool = False,
                  llm: bool = False, model: str = "", api_key: str | None = None,
                  base_url: str | None = None, temperature: float = 0.0,
                  status_cb=None) -> None:
    if llm:
        hits, meta = recommend_with_llm(archive_path, field, top=top, model=model,
                                        api_key=api_key, base_url=base_url,
                                        temperature=temperature, status_cb=status_cb)
    else:
        hits, meta = recommend(archive_path, field, top=top)

    if as_json:
        print(json.dumps({"archive": archive_path, **meta, "hits": hits},
                         ensure_ascii=False, indent=2))
        return

    mode = f"LLM ranking ({meta['model']})" if meta["mode"] == "llm" else "offline ranking"
    print(f"\n  Field   : {field}")
    print(f"  Mode    : {mode} over {meta['candidates']} candidates")
    if meta.get("routed_categories"):
        print(f"  Routed  : {', '.join(meta['routed_categories'])}")
    if meta.get("unmatched"):
        print(f"  Note    : {meta['unmatched']} model picks not found in archive (dropped)")
    if hits:
        print()
        for rank, hit in enumerate(hits, 1):
            stars = f" · ★{hit['githubStars']}" if hit.get("githubStars") else ""
            print(f"  {rank}. [{hit['score']:.2f}] {hit['title']}{stars}")
            print(f"     {hit['category']} · {hit['year']} · {hit['doi'] or hit['paperUrl']}")
            if hit.get("reason"):
                print(f"     {hit['reason']}")
    else:
        print("\n  No candidates matched. Try a broader field description.")


def run_stats(archive_path: str, as_json: bool = False, categories: list[str] | None = None) -> None:
    data = stats(archive_path, categories=categories)
    if as_json:
        print(json.dumps({"archive": archive_path, **data}, ensure_ascii=False, indent=2))
        return
    lo, hi = data["date_range"]
    span = f" ({lo} .. {hi})" if lo else ""
    print(f"\n  Archive : {archive_path}")
    print(f"  Papers  : {data['total']} in {len(data['categories'])} categories{span}")
    print(f"\n  {'CATEGORY':<44}  {'COUNT':>5}  NEWEST")
    for cat in data["categories"]:
        print(f"  {cat['name']:<44}  {cat['count']:>5}  {cat['newest'][:7]}")
    print(f"\n  Venues: {data['venues']} · Teams: {data['teams']}")
