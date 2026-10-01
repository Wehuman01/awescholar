---
name: awescholar
description: "Use when working with awescholar CLI — scientific literature discovery, annotation, filtering, and report generation, plus AgentX hub registry management. 中文触发词：文献检索、论文搜索、研究报告、awescholar、文献综述、更新数据、更新readme、agentx、agentx-hub、注册表、snapshot 校验。English: AgentX registry, agent snapshot, agentx hub."
---

# Awescholar

Use `awescholar` CLI directly. Do not add wrapper scripts unless the CLI is missing a needed capability.

## Intent Router

Match the user's intent to a task domain, then follow the workflow below.

| User intent | Domain | First command |
|---|---|---|
| "Create a new awesome paper list repo", "scaffold a curated list" | Init | `awescholar init <dir> --title ... --github-repo ... --website ...` |
| "Search for papers about X", "find recent papers" | Crawler Pipeline | `awescholar --config cfg.json crawler search "query"` |
| "Run the full discovery pipeline" | Crawler Pipeline | `awescholar --config cfg.json crawler run "query"` |
| "Monthly report for 2026-05", "跑上个月的月报" | Crawler Month | `awescholar --config cfg.json crawler run --month 2026-05` |
| "Half-month report for 2026-06-1", "半月刊" | Crawler Period | `awescholar --config cfg.json crawler run --period 2026-06-1` |
| "Update the project", "full update", "merge and update" | Updater Full | `updater update` → `render counts` (website-first) or `render readme` (tables) → `render rss` |
| "Merge new results into project data", "update the archive" | Updater Merge | `awescholar updater update --direction new2old --input X --archive Y` |
| "Digest the archive for a month", "当月入库论文摘要" | Render Digest | `awescholar render digest --archive docs/data.json --month 2026-05` |
| "Update the README table" | Render README | `awescholar render readme --archive data.json` |
| "Refresh README paper counts" | Render Counts | `awescholar render counts --archive docs/data.json` |
| "Generate RSS feed" | Render RSS | `awescholar render rss --archive data.json` |
| "Add a paper by title/DOI search" | Updater Search | `awescholar updater search --json-file papers.json` |
| "Manually add a paper record" | Updater Add | `awescholar updater add --archive data.json` |
| "Find the GitHub repo for papers", "add code links and stars" | Updater Enrich | `awescholar updater enrich --archive docs/data.json` |
| "Refresh AgentX registry stats", "update the agentx snapshot" | Updater Enrich-AgentX | `awescholar updater enrich --archive agents-snapshot.json --agentx` |
| "Backfill citation counts", "fill citations" | Updater Backfill | `awescholar updater backfill --archive docs/data.json --fields citations` |
| "Fill missing affiliations/teams", "补机构信息" | Updater Backfill | `awescholar updater backfill --archive docs/data.json` |
| "Download the PDFs", "下全文", "fetch full text" | Updater Download | `awescholar updater download --archive docs/data.json` |
| "Preprint upgraded to journal?", "升级正式发表版" | Updater Publish-Scan | `awescholar updater publish-scan --archive docs/data.json` |
| "Export papers as agentx agents", "feed the agent registry" | Render AgentX | `awescholar render agentx --archive docs/data.json -o candidates.json` |
| "What's in my archive about X", "search my curated papers" | Reader Query | `awescholar reader query --archive docs/data.json "X" --json` |
| "Papers related to this one", pasted abstract/DOI/title | Reader Related | `awescholar reader related --archive docs/data.json --doi X --json` |
| "Must-read papers for my field", "reading list", "入门必读" | Reader Recommend | `awescholar reader recommend --archive docs/data.json --field "X" --top 10` |
| "Archive stats", "how many papers do I have" | Reader Stats | `awescholar reader stats --archive docs/data.json` |
| "Resolve held-back duplicates", "处理重复论文" | Updater Dedupe | `awescholar updater dedupe --review output/dedupe_review.json --archive docs/data.json --keep published` |
| "Import my Zotero reading list", "把 Zotero collection 导入流水线" | Zotero Pull | `awescholar zotero pull --collection "NAME" -o zotero_papers.json` |
| "Push this month's picks to my Zotero", "生成 Zotero 阅读清单" | Zotero Push | `awescholar zotero push --archive docs/data.json --collection "NAME"` (dry run; add `--apply` to write) |

## First-Time Setup

1. Install: `pip install awescholar`
2. Copy `config.example.json` to `config.json` (or any path)
3. Set API keys in `~/.config/awescholar/.env` (recommended — loaded automatically; do NOT assume shell env vars are set when invoked as an agent)
4. Optional: keep shared model profiles and API key references in `~/.config/awescholar/config.json` — the project config passed via `--config` deep-merges over it key by key
5. Verify: `awescholar -v`

## Core Rules

1. Always use `--config` when running crawler commands — it carries model, API key, and search settings. Without `--config`, `~/.config/awescholar/config.json` supplies global defaults (model profiles, API keys), so key-only commands like `updater enrich` work without a project config.
2. Crawler steps are sequential: search → annotate → filter → report. Each reads from the previous step's output by default, but accepts `--input` to override.
3. `updater` commands operate on the **project data JSON** (long-lived curated file, e.g. `docs/data.json`). `render` commands only read that archive and write derived artifacts (README, RSS, digest, agentx candidates) — they never modify it. Do not confuse either with pipeline intermediates (`updater.json`, `updater_filter.json`).
4. For `updater search`: use `--json-file` to save results for review first, then `updater update --direction new2old` to merge. Use `--archive` only when you want to write directly.
5. For `render readme`: default behavior creates a timestamped `.bak` backup. Use `--no-backup` to skip. Git-clean files are also skipped by the archive backup helper.
6. `reader` commands are read-only: they never modify the archive and need no `--config` (only `recommend --llm` does). Prefer `--json` when consuming programmatically, and answer the user following Response Format.
7. Breaking rename: `updater readme|counts|rss|digest|export-agentx|citations` no longer exist. Use `render readme|counts|rss|digest|agentx` and `updater backfill --fields citations`.

## Two Orientations: Awesome Paper List vs AgentX Project Registry

Awescholar operates in two distinct orientations. The same command family serves both; the `--agentx` flag switches the data target.

**Awesome paper-list orientation** (default, no `--agentx`)
- Data file: `data.json` — a category dict of paper records (`{"AI Agents": [{paper}, …]}`).
- Purpose: curate a bibliography of research papers.
- Typical commands: `updater add/search/enrich/backfill --archive data.json`, `render readme/counts/rss/digest --archive data.json`.

**AgentX project-registry orientation** (`--agentx`)
- Data file: `data/agents-snapshot.json` — a slug-sorted list of agent records (`{agents: [{slug, repo, paperMeta, status, …}], counts: {…}}`).
- Purpose: maintain a hub of projects that have GitHub repos (each "agent" is a project, optionally linked to a paper).
- `--archive` defaults to `data/agents-snapshot.json` in this mode, so you can omit it if the file is at its standard location.

**Relationship between the two**
- A paper with a GitHub repo is a candidate agent. `render agentx --archive data.json -o candidates.json` projects the paper archive into agent-shaped candidate records.
- `updater add --agentx --from-json candidates.json` ingests that candidate file into the snapshot — all-or-nothing, validates category/tag policy, derives initial status.
- `updater enrich --agentx` refreshes GitHub metrics and runs the lifecycle pass (404 → gone, retirement, license fallback) on the snapshot in place.
- `updater backfill --agentx --fields paper-meta` resolves `paperMeta` (DOI/arXiv/title clues → Semantic Scholar) for agents that arrived without a paper reference.

**When to use which**

| Task | Orientation | Commands |
|---|---|---|
| Add / merge new papers, update category tables | Awesome | `updater add/search`, `render readme/counts` |
| Register a new agent, batch-intake candidates | AgentX | `updater add --agentx …`, `updater add --agentx --from-json FILE` |
| Refresh GitHub stars, resolve 404s, lifecycle pass | AgentX | `updater enrich --agentx` |
| Fill missing paperMeta or citation counts for agents | AgentX | `updater backfill --agentx [--fields …]` |
| Validate snapshot invariants before merge (CI) | AgentX | `verify --agentx` |
| Turn paper archive into agent candidate queue | Bridge | `render agentx --archive data.json -o candidates.json` |

## Workflows

### Init (Scaffold a New Repository)

Use when creating a brand-new curated paper-list repository. Generates bilingual website-first READMEs, a searchable statistics website, an empty `docs/data.json` wired into `config.json`, RSS, LICENSE, CONTRIBUTING.md, and `.gitignore`.

```bash
# Everything optional — bare init in an empty dir uses Awesome-AI-Meets-Biology defaults
awescholar init ./my-awesome-list --title "Awesome AI Foo" \
    --subtitle "A curated survey of AI for foo" \
    --github-repo Webioinfo01/Awesome-AI-Foo \
    --website http://foo.webioinfo.top/ \
    --category "AI Agents" --category "Foundation models" --category Reviews

awescholar init --template vt          # Awesome-AI-Virtual-Tumor style website (default: bio)
awescholar init --no-zh --no-branding  # English-only README, no ecosystem/support sections
awescholar init --tables               # also embed classic AWESCHOLAR README table markers
awescholar init --no-serve --port 8123 # skip the docs/ preview (default port 8000, auto-increments while busy)
awescholar init --force                # proceed even if the target directory is not empty
```

After init: edit `config.json` (model keys, search query), then add papers with `updater add` / `updater search`. For website-first repos (no embedded tables), refresh README counts with `render counts` after merging papers.

### Crawler Pipeline

Use when discovering and curating new papers. Each step can run independently with `--input`.

```bash
# Full pipeline (search + annotate + filter + report)
awescholar --config cfg.json crawler run "AI agent" --limit 50 --date 2025-01-01:2025-05-30 -o report.md

# Monthly run: one argument derives dates, output dir, and report name
awescholar --config cfg.json crawler run --month 2026-05   # -> month_reports/2605/report.md

# Half-month run: P=1 is 01–15, P=2 is 16–end
awescholar --config cfg.json crawler run --period 2026-06-1   # -> month_reports/2606_1/report.md

# Step-by-step
awescholar --config cfg.json crawler search "AI agent" --limit 100 --date 2025-01-01:2025-05-30
awescholar --config cfg.json crawler annotate                       # reads from DB
awescholar --config cfg.json crawler annotate --input papers.json   # reads from JSON
awescholar --config cfg.json crawler filter --limit 20              # reads from updater.json
awescholar --config cfg.json crawler report -o report.md            # reads from updater_filter.json
awescholar --config cfg.json crawler report updater_filter.json -o report.md  # explicit input
```

Pipeline config flow control:
- `skip_search: true` — load from DB, do annotate + filter + report
- `use_updater_json: true` — skip annotate, do filter + report
- `use_filtered_json: true` — skip to report only
- `merge_new_to_old: true` + `data_json_path` — auto-merge filtered results into project data JSON after filter step

With `--month` / `--period`, the config's `search.publication_date` and `output.db_path` are overridden by the derived values — keep ONE tracked base config in the repo and pass the month/period per run. `--date`, `--month`, and `--period` are mutually exclusive. The default report filename is `{db_path}/report.md` (the model name lives in a provenance comment inside the report, not the filename). The filter gates on scope before quality: off-scope papers are excluded regardless of venue, and fewer papers than `filter.limit` is a normal outcome — do not re-run to force a count.

### Render Digest

Use when producing a monthly summary of what the curated archive actually holds, instead of running a fresh discovery pipeline.

```bash
# LLM narrative when a model is configured; tables-only with --no-llm
awescholar render digest --archive docs/data.json --month 2026-05            # -> month_reports/2605/digest.md
awescholar render digest --archive docs/data.json --month 2026-05 --no-llm   # offline, no model key needed
```

Selection is by each record's `year` field (`2026.05`, unpadded `2026.5` also matches). An empty month fails with an actionable error — check `--month` or the records' `year` fields before retrying.

### Updater Merge

Use when merging new pipeline results into the project data JSON, or enriching new results with historical data.

```bash
# Merge new filtered results into project data JSON
awescholar updater update --direction new2old --input output/updater_filter.json --archive docs/data.json

# Enrich new results with historical data from project data JSON
awescholar updater update --direction old2new --input output/updater_filter.json --archive docs/data.json
```

Near-duplicates (title similarity ≥ 0.90, or ≥ 0.80 with a shared author) are held back instead of merged — see Updater Dedupe below. Heavily retitled pairs whose author roster almost fully overlaps are also held back.

Decision order:
1. Review `updater_filter.json` before merging — confirm content is appropriate.
2. `new2old` when new papers should be added to the curated collection.
3. `old2new` when the new report should include relevant historical papers.

### Updater Full Update

Use when updating the entire project after new data is ready. Chains merge + render steps.

```bash
# 1. Merge new filtered results into project data
awescholar updater update --direction new2old --input output/updater_filter.json --archive docs/data.json

# 2. Regenerate README table
awescholar render readme --archive docs/data.json --readme readme.md --no-backup

# 3. Regenerate RSS feed
awescholar render rss --archive docs/data.json -o docs/rss.xml
```

Decision order:
1. Review `updater_filter.json` before merging — confirm content is appropriate.
2. Run merge first (`updater update`). If merge fails, stop and fix before continuing.
3. Run readme/counts (`render readme` or `render counts`). If that fails, the data is already merged — check for marker issues.
4. Run RSS last (`render rss`). Skipping RSS means subscribers won't see new papers.

### Updater Search & Add

Use when adding individual papers to the project data JSON.

```bash
# Search Semantic Scholar, save to flat JSON for review
awescholar updater search --json-file papers.json --by title
awescholar updater search --json-file papers.json --by doi

# Search and write directly to project data JSON
awescholar updater search --archive docs/data.json --by title
awescholar updater search --archive docs/data.json --category "AI Agents"         # into a specific category
awescholar updater search --archive docs/data.json --by doi 10.1038/x 10.1038/y  # DOIs as arguments, non-interactive
awescholar updater search --archive docs/data.json --by doi 10.1038/x \
    --code-url owner/repo --annotate   # known repo into codeUrl + annotator LLM fills domain

# Manually add a record (interactive prompt)
awescholar updater add --archive docs/data.json
```

`paperUrl` is written as the DOI link (`https://doi.org/…`) whenever the paper has a DOI. `--code-url owner/repo` (shorthand or full URL) skips repo discovery for a repo you already know — with `archive.stars_style: "badge"` in config it also writes the shields.io badge into `githubStars`. `--annotate` runs the crawler's annotator LLM once over just the added papers to fill the one-line `domain`. After papers land, the command prints the natural next step (`render counts` / `render rss`).

Workflow for reviewed search:
1. `updater search --json-file papers.json` — search and save for review
2. Review and edit `papers.json` as needed
3. `updater update --direction new2old --input papers.json --archive docs/data.json` — merge when ready

### Updater Backfill

Use when records lack `affiliation`/`team` and/or empty `citations` counts. Consults three sources cheapest-per-coverage first: Semantic Scholar author batches, Crossref per-DOI metadata, OpenAlex curated institutions. Only empty fields are filled, entries never move between categories, and the affiliation always comes from the same author as the team. Citations power the website badge under Paper and come from Semantic Scholar `citationCount` (DOI required; existing values preserved).

```bash
awescholar updater backfill --archive docs/data.json
awescholar updater backfill --archive docs/data.json --no-backup
awescholar updater backfill --archive docs/data.json --only XunZi  # DOI exact or title substring, repeatable
awescholar updater backfill --archive docs/data.json --fields citations  # only citation counts
```

There is no separate `updater citations` command — use `backfill --fields citations`.

### Updater Download

Use when the user wants the actual PDFs for archived papers (or a standalone DOI/arXiv ID). Open-access direct links only: arXiv IDs (detected from `10.48550/arXiv.*` DOIs or arxiv.org paperUrls) download from arxiv.org; other DOIs resolve through OpenAlex `best_oa_location.pdf_url`. Every response is checked to start with `%PDF` — bot-gated publisher pages (cell.com and friends) answer HTML and are reported as failures with the article link, never forced. Files land in `--out` (default `pdfs/`) as `<year>-<title-slug>.pdf`; existing files are skipped so re-runs are idempotent. The archive is never modified.

```bash
awescholar updater download --archive docs/data.json            # PDFs for the whole archive -> pdfs/
awescholar updater download --archive docs/data.json --only XunZi   # scope by DOI/title substring
awescholar updater download --archive docs/data.json --out docs/pdf --force  # re-download even if present
awescholar updater download --doi 10.1038/s41467-025-59628-y    # standalone DOI, no archive needed
awescholar updater download --arxiv 2609.11115                  # standalone arXiv ID
```

When a paper fails as "not a PDF", it is bot-gated — fetch it in a real browser; do not retry the CLI on it.

### Reader (Query · Related · Recommend · Stats)

Use when answering questions **about** the curated archive — the reader face. Read-only, offline, no `--config` needed (except `recommend --llm`). Never use these to modify data; if the user wants to add papers, switch to Updater Search.

```bash
# Keyword search over title/domain/abstract/venue/team
awescholar reader query --archive docs/data.json "single cell perturbation"
awescholar reader query --archive docs/data.json "LLM agent" --category "AI Agents" --top 5 --json

# Papers related to a seed: --doi (must be in archive), --title (external ok),
# or --input seed.json (exactly one record — write the pasted abstract here)
awescholar reader related --archive docs/data.json --doi 10.48550/arXiv.2505.23055
awescholar reader related --archive docs/data.json --title "External paper title"
awescholar reader related --archive docs/data.json --input seed.json --top 5 --json

# Must-read ranking for a field. Offline by default; --llm adds model-ranked
# reasons (needs --config)
awescholar reader recommend --archive docs/data.json --field "AI for protein design" --top 10
awescholar --config config.json reader recommend --archive docs/data.json --field "..." --llm --json

# Archive statistics (--category repeatable; default: every category in the archive)
awescholar reader stats --archive docs/data.json --json
awescholar reader stats --archive docs/data.json --category "AI Agents"
```

Paper-to-precedents flow (user pastes an abstract):
1. Write the pasted text to a temp file as `{"title": "...", "abstract": "..."}`.
2. `awescholar reader related --archive docs/data.json --input <temp> --top 5 --json`.
3. Answer following Response Format; offer `updater search` for papers worth adding.

### Render README

Use when regenerating the README table from the project data JSON.

```bash
# Generate with backup (default)
awescholar render readme --archive docs/data.json --readme readme.md

# Generate without backup
awescholar render readme --archive docs/data.json --readme readme.md --no-backup

# Custom title and description
awescholar render readme --archive docs/data.json --readme readme.md --title "My Project" --description "A curated list of papers"
```

Default backup creates `{readme}.{YYYYMMDD_HHMMSS}.bak` before overwriting.

### Render Counts

Use when the repo is website-first (papers live on the website, README shows links and counts only). Refresh after every merge.

```bash
awescholar render counts --archive docs/data.json
# updates readme.md / README.zh-CN.md / README.md (whichever exist in cwd);
# --readme <path> is repeatable to target specific files
```

### Render RSS

Use when generating an RSS feed from the project data JSON.

```bash
awescholar render rss --archive docs/data.json -o docs/rss.xml
awescholar render rss --archive docs/data.json -o docs/rss.xml --title "Paper Updates"
```

### Updater Dedupe

Use when `updater update` reports possible duplicates held back. A held-back pair means a new paper's title nearly matches an archive entry but dodged the exact DOI/title match — the classic preprint-vs-published signature. Pairs land in `dedupe_review.json` next to the `--input` file; nothing is merged until resolved.

```bash
# After: "Merged : N added · M possible duplicates held back"
awescholar updater dedupe --review output/dedupe_review.json --archive docs/data.json --keep published
```

Decision order:
1. `--keep published` — the non-preprint version wins and overwrites in place (default choice for preprint/published pairs).
2. `--keep newer` — later `year` wins.
3. `--keep both` — rare: keep two entries when they are genuinely distinct papers.
4. Use `updater update --no-dedupe` only when the user explicitly wants everything appended blindly.

### Updater Publish-Scan

Use when archived preprints may already have a journal version of record. Proactive mirror of merge-time dedupe: scan the archive instead of waiting for the published paper to collide later.

```bash
# Dry run: write publish_review.json next to the archive
awescholar updater publish-scan --archive docs/data.json

# Scan + upgrade in one shot
awescholar updater publish-scan --archive docs/data.json --apply

# Apply a reviewed queue without rescanning
awescholar updater publish-scan --archive docs/data.json --review publish_review.json --apply

# Scope, manual pair, DOI-only verification
awescholar updater publish-scan --archive docs/data.json --only XunZi --limit 5
awescholar updater publish-scan --archive docs/data.json --pair PREPRINT_DOI PUBLISHED_DOI --apply
awescholar updater publish-scan --archive docs/data.json --no-title-search
```

Covers bioRxiv/medRxiv (old and new prefixes), Research Square, Preprints.org, ChemRxiv, Authorea, SSRN, and arXiv. Verification channels: S2 by DOI → fuzzy S2 title → Crossref `query.title`. Title matches need dedupe-grade similarity + non-empty venue. `--apply` switches venue/DOI/paperUrl/year/authors/citations and keeps category/codeUrl/githubStars/domain/affiliation.

### Zotero Exchange (Pull · Push)

Use when the user's personal Zotero library is the input (a reading collection worth curating into the archive) or the output (a reading list built from the archive). Talks to api.zotero.org — no local Zotero needed; desktop Zotero sees writes after its next sync.

```bash
# Collection -> pipeline JSON, then merge with the usual updater flow
awescholar zotero pull --collection "DROMA" -o zotero_papers.json
awescholar updater update --direction new2old --input zotero_papers.json --archive docs/data.json

# Archive -> Zotero collection: dry run first, apply after review
awescholar zotero push --archive docs/data.json --collection "2605 月报"
awescholar zotero push --archive docs/data.json --collection "2605 月报" --apply

# Scope one category, attach extra tags
awescholar zotero push --archive docs/data.json --collection "X" --category "AI Agents" --tag must-read --apply
```

Rules:
1. Needs a Zotero API key (read/write for push) from https://www.zotero.org/settings/keys — resolved `--zotero-api-key` > config `zotero.api_key` > env `ZOTERO_API_KEY` > `.env`. A user library needs no id; a group library sets `zotero.library_id`.
2. `pull` is read-only and never creates a collection; output lands under `--category` (default `Zotero`). Preprint/published twins inside the pull are caught later by `updater update`'s dedupe — pull itself stays a dumb mapping.
3. `push` classifies every record against the whole library (DOI → normalized title): `already-in-collection` (skip), `in-library` (exists elsewhere — reported only, membership never forced), `to-add`. The dry run writes `zotero_review.json` next to the archive; only `--apply` writes. `--apply` is idempotent — rerun skips what already landed.
4. Created items are tagged `awescholar` + archive category + `--tag` extras; preprint venues become Zotero `preprint` items, others `journalArticle`; authors ride as single-field creators.

### Updater Enrich

Use when papers lack GitHub links or star counts are stale. Fills empty `codeUrl` (GitHub search rounds: arXiv ID, then leading system name, then full title — a round whose candidates all fail falls through to the next; corroborated heuristic match auto-accept, ambiguous races judged by the configured LLM) and refreshes `githubStars` for every linked repo. Only empty `codeUrl` fields are filled. The star shape follows the config convention `archive.stars_style`: `numeric` (default) refreshes bare ints and migrates legacy badge-URL values; `badge` (Awesome-AI-Meets-Biology) writes `https://img.shields.io/github/stars/owner/repo` and never rewrites an existing badge to a number. `--stars-style` overrides per run.

```bash
awescholar updater enrich --archive docs/data.json              # resolve + refresh (LLM tiebreak on when configured)
awescholar updater enrich --archive docs/data.json --limit 20   # cap resolution per run
awescholar updater enrich --archive docs/data.json --no-llm     # heuristics only
awescholar updater enrich --archive docs/data.json --only XunZi # scope to matching entries (DOI or title substring, repeatable)
awescholar updater enrich --archive docs/data.json --since 2026-09-01  # only entries added on/after this date (needs addedAt)

# AgentX mode: refresh an agentx registry snapshot in place (metrics only)
awescholar updater enrich --archive agents-snapshot.json --agentx
```

`--agentx` treats `--archive` as an AgentX registry snapshot (top-level `{agents, counts}`) instead of an awesome-list archive: it refreshes `stars/pushedAt/openIssues/language/license/description/homepage/archived` for every agent repo and strictly preserves every other field (`status`, `slug`, `paperMeta`, category, tags, source), so lifecycle rules stay with the registry's own tooling.

Needs `GITHUB_TOKEN` (config `github.token` > env `GITHUB_TOKEN` > `--github-token`); anonymous limits are 10 searches/min and 60 repo reads/hour. After enriching, regenerate the README so the numeric stars render as live badges.

### AgentX Hub Commands

Use these when the task is maintaining an AgentX-style project registry (the `data/agents-snapshot.json` hub file).

```bash
# Register a single agent (validates repo, fetches live metrics, derives status)
awescholar updater add --agentx owner/repo --category <slug> [--tags "A,B"] [--name NAME] [--paper URL]

# Batch-intake candidates from `render agentx` (all-or-nothing)
awescholar updater add --agentx --from-json candidates.json

# Full metrics + lifecycle refresh (404 → gone, retirement, license fallback)
awescholar updater enrich --agentx

# Backfill missing paper references or citation counts for registered agents
awescholar updater backfill --agentx                        # paper-meta + citations (default)
awescholar updater backfill --agentx --fields paper-meta    # resolve paperMeta from clues
awescholar updater backfill --agentx --fields citations     # refresh citation counts
awescholar updater backfill --agentx --fields paper-meta --refresh  # re-resolve existing paperMeta

# Offline validation gate (CI runs this; exits 1 with itemized list on any violation)
awescholar verify --agentx
```

**Migration from the deprecated `agentx-cli` (TypeScript)**

| Old `agentx-cli` | Awescholar equivalent |
|---|---|
| `agentx add owner/repo` | `awescholar updater add --agentx owner/repo --category <slug>` |
| `agentx add --from-json FILE` | `awescholar updater add --agentx --from-json FILE` |
| `agentx snapshot` | `awescholar updater enrich --agentx` |
| `agentx enrich-papers [--force]` | `awescholar updater backfill --agentx --fields paper-meta [--refresh]` |
| `agentx refresh-citations` | `awescholar updater backfill --agentx --fields citations` |
| `agentx validate` | `awescholar verify --agentx` |

`--archive` defaults to `data/agents-snapshot.json` in `--agentx` mode; omit it when the snapshot is at the standard location.

### Render AgentX

Use when feeding an agentx-style registry (repo-first agent directory). Exports every archive paper with a github.com `codeUrl` as an agentx snapshot-shaped candidate agent (slug/name/repo/paperMeta/category + live metrics when a token is available). The output is a review queue for agentx intake, not a drop-in snapshot.

```bash
awescholar render agentx --archive docs/data.json -o candidates.json
# map archive categories to agentx slugs; unmapped papers land in --default-category
awescholar render agentx --archive docs/data.json -o candidates.json --category-map map.json --default-category platforms
# scope to given archive categories; skip repos already registered in a snapshot
awescholar render agentx --archive docs/data.json -o candidates.json --categories "AI Agents,Reviews" --exclude-snapshot agents-snapshot.json
# emit an executable pnpm agent:add intake script instead of candidate JSON (the last mile into an agentx repo)
awescholar render agentx --archive docs/data.json -o intake.sh --emit commands
# classify each candidate's agentx category with the configured model (needs --exclude-snapshot)
awescholar render agentx --archive docs/data.json -o intake.sh --emit commands --exclude-snapshot agents-snapshot.json --llm-category
```

No category list is hardcoded: when `--exclude-snapshot` points at an agentx snapshot, the categories actually present in that file are the source of truth — mapped or default slugs missing from it draw a warning (no snapshot means no validation). `--source`/`--source-url` record provenance on every exported agent. Run `updater enrich` first so papers carry their repos and stars. `--emit commands` writes one `pnpm agent:add owner/repo --category … --name … --paper …` line per candidate — tags are deliberately not emitted (the tag registry belongs to the target repo, whose agent:add validates at run time). `--llm-category` prefers the paper's system name for display and asks the annotator model for a category slug that exists in the target snapshot.

### Hub Maintenance Cycle (AgentX registry)

Use when refreshing the AgentX hub — e.g. after new papers are curated, or on a scheduled CI run.

```bash
# 1. Project new paper archive entries as agent candidates
awescholar render agentx --archive docs/data.json -o candidates.json

# 2. Ingest candidates (all-or-nothing; validates category/tag policy, derives status)
awescholar updater add --agentx --from-json candidates.json

# 3. Refresh GitHub metrics + run lifecycle pass (404 → gone, retirement, license fallback)
awescholar updater enrich --agentx

# 4. Validate snapshot invariants (CI gate — exits non-zero with itemized problems if any)
awescholar verify --agentx

# 5. Commit the updated snapshot
git add data/agents-snapshot.json && git commit -m "chore: refresh agentx snapshot"
```

## Response Format (reader intents)

When answering a user from reader results, keep the structure stable across sessions and agents:

1. Open with one line: N in-archive hits (+ M outside suggestions, if you also searched the web/Semantic Scholar).
2. At most 5 in-archive picks, relevance-ordered. Per paper:
   - **Title** (year · category)
   - one-sentence contribution — what the paper does
   - why it fits THIS user — tie it to their stated field/question; reuse `reason_for_inclusion` when present
   - link (`paperUrl` or DOI)
3. Keep in-archive and outside results in separate groups; never mix them.
4. Close with: `Archive has N papers across M categories — dig deeper with: awescholar reader query "<keywords>".`
5. Answer only the question asked. If the user wants to add a paper to the archive, say so and route to Updater Search — do not merge anything silently.

## Config Reference

```json
{
    "model_profiles": {
        "glm": { "api_key": "${GLM_API_KEY}", "base_url": "https://open.bigmodel.cn/api/paas/v4" }
    },
    "model": { "profile": "glm", "name": "glm-5.1" },
    "agent_models": null,
    "semantic_scholar": { "api_key": "${SEMANTIC_SCHOLAR_API_KEY}" },
    "github": { "token": "${GITHUB_TOKEN}" },
    "zotero": { "api_key": "${ZOTERO_API_KEY}", "library_type": "user", "library_id": null },
    "search": {
        "query": "AI agent|large language model",
        "fields_of_study": ["Biology", "Medicine"],
        "publication_date": "2025-01-01:2025-05-30",
        "limit": 100, "include_abstracts": true
    },
    "filter": { "limit": 20, "research_interests": null },
    "output": { "db_path": "output", "report_filename": null },
    "pipeline": {
        "skip_search": false,
        "use_updater_json": false,
        "use_filtered_json": false,
        "existing_json_path": null,
        "merge_new_to_old": false,
        "data_json_path": null
    },
    "archive": { "stars_style": "numeric" },
    "categories": ["Foundation Models", "Drug Discovery", "Single Cell Analysis"]
}
```

Key fields:
- **model.name**: Model name only (e.g. `glm-5.1`, `deepseek-chat`). The `openai/` prefix is auto-prepended.
- **model.base_url**: Required for non-default endpoints. Must be OpenAI-compatible.
- **model_profiles**: Reusable profile map. Referenced by `model.profile` or `agent_models.*.profile`.
- **agent_models**: Per-agent overrides for annotator/filterer/reporter. `null` = use global model.
- **github.token**: GitHub token for `updater enrich` / `render agentx` live metrics (else env `GITHUB_TOKEN` / `--github-token`).
- **zotero.api_key / library_type / library_id**: Zotero Web API access for `zotero pull/push` (else env `ZOTERO_API_KEY` / `--zotero-api-key`). `library_type` is `user` (default — id resolved from the key itself) or `group` (requires `library_id`).
- **archive.stars_style**: `numeric` (default — bare ints, refreshed by enrich) or `badge` (shields.io URLs; enrich writes badges and never rewrites one to a number). CLI `--stars-style` overrides per run.
- **pipeline.data_json_path**: Long-lived curated project data JSON. When `merge_new_to_old` is true, filtered results auto-merge here after pipeline completes.
- **pipeline.existing_json_path**: Intermediate annotate output (`updater.json`). Different from `data_json_path`.
- **pipeline.skip_search / use_updater_json / use_filtered_json**: Flow control — see Crawler Pipeline section.
