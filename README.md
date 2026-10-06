<div align="center">
  <img src="./logo/hero.png" alt="awescholar" width="800">
  <h1>awescholar: Scientific Literature Curator <a href="https://github.com/wehuman01/aweskill"><img src="https://raw.githubusercontent.com/wehuman01/aweskill/main/logo/aweskill-badge2.svg" alt="aweskill companion"></a></h1>
  <p><strong>AI-agent-operable scientific literature discovery and curation.</strong></p>
  <p>Search, annotate, filter, and report on academic papers — tell your agent to do it, or run the CLI yourself.</p>
  <p>
    <strong>English</strong> ·
    <a href="./README_cn.md">简体中文</a> ·
    <a href="https://we.webioinfo.top/">Webioinfo</a>
  </p>
  <p>
    <img src="https://img.shields.io/pypi/v/awescholar?style=flat-square&color=7C3AED" alt="Version">
    <img src="https://img.shields.io/badge/python-%E2%89%A53.11-0EA5E9?style=flat-square" alt="Python">
  </p>
  <p>
    <img src="https://img.shields.io/badge/status-alpha-c96a3d?style=flat-square" alt="Status">
    <img src="https://img.shields.io/badge/install-pip-22C55E?style=flat-square" alt="pip install">
    <img src="https://img.shields.io/badge/platform-cli-334155?style=flat-square" alt="Platform">
    <img src="https://img.shields.io/pypi/dm/awescholar?style=flat-square" alt="PyPI downloads">
    <img src="https://img.shields.io/github/stars/wehuman01/awescholar?style=flat-square" alt="GitHub stars">
  </p>
</div>


> Search, annotate, filter, and report on academic papers — tell your agent to do it, or run the CLI yourself.

A lightweight CLI that automates the paper curation workflow: query Semantic Scholar, annotate with LLM, filter by quality, generate Markdown reports, and incrementally merge into a maintained project data JSON. Designed for both human and AI-agent operation — install the skill, and your coding agent can run the entire pipeline from natural-language requests.

awescholar now serves two orientations with one tool — **paper-oriented awesome lists** (data.json archive: crawler → updater → render → reader) and the **project-oriented AgentX hub** (data/agents-snapshot.json snapshot: updater --agentx commands + verify). The same entity is both a paper record and an agent record; `render agentx` bridges them.

> **Note:** the standalone `agentx-cli` (npm `agentx-hub-cli`) was deprecated and absorbed into awescholar 0.2.6. The v0.3.0 `agentx` console script aliases were removed in v0.3.2 — curation uses awescholar's native `--agentx` commands; the npm package was reborn (v0.2.0) as the hub **operations** CLI.

## Powered by awescholar

- **[Awesome AI Meets Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)** — AI x biology paper curation powered by awescholar for automated discovery, filtering, and README updates.

## Install

### Ask an AI agent

If you are working inside Claude Code, Codex, Cursor, or another coding agent, tell it:

```text
Read https://github.com/wehuman01/awescholar/blob/main/README.ai.md and follow it to install awescholar for this agent.
```

The agent will first install the `awescholar` CLI, then choose one of two awescholar skill management options:

1. **Via [aweskill](https://aweskill.wehuman.top/)** — installs and manages the skill from GitHub with update, projection, and backup support. Requires Node.js. Powered by [aweskill](https://aweskill.wehuman.top/) — the universal skill manager for AI coding agents.
2. **Direct copy** — downloads `SKILL.md` into the agent's skill directory. No extra dependencies beyond Python, but future updates require copying the file again manually.

### pip

```bash
pip install awescholar
```

## Supported by aweskill

awescholar is powered by [aweskill](https://github.com/wehuman01/aweskill) — a CLI-first skill package manager that AI agents can operate themselves. aweskill handles skill installation, updates, projection, and backup across 47+ coding agents including Claude Code, Codex, Cursor, Gemini CLI, and more.

## Usage

### AI Agent

Install the awescholar skill (see [Install](#install)), then just tell your agent what to do — no manual CLI steps needed. If the agent hasn't configured `config.json` yet or you need to change model/search settings, see [Detailed Config](#detailed-config) below.

**What an AI agent can do:**

- Run the full discovery pipeline: search, annotate, filter, report — in one command
- Merge new results into the project data JSON and regenerate the README
- Search Semantic Scholar by title or DOI and add papers to the archive
- Answer reader questions from the archive without touching it: keyword search, related work for a pasted abstract, must-read lists per field (`reader query / related / recommend`)
- Resolve suspected preprint/published duplicates held back during merge
- Exchange with your Zotero library: pull a reading collection into the pipeline, push filtered picks into a Zotero collection (dry run first)
- Generate RSS feeds for curated collections
- Re-run any pipeline step independently with custom input

**Example requests:**

> "Search for recent papers about AI agents in biology, filter the top 20, and update the README."

> "Run the awescholar pipeline with my config, then merge the results into docs/data.json."

> "Find this paper by DOI and add it to the project data JSON."

The agent uses the [SKILL.md](resources/skills/awescholar/SKILL.md) to understand all available commands, config options, and workflows.

### Human

```bash
# Store API keys once in the user keyring (recommended — works for agents and
# cron too, where ~/.zshrc is never sourced):
mkdir -p ~/.config/awescholar
cat >> ~/.config/awescholar/.env <<'EOF'
GLM_API_KEY=sk-...
SEMANTIC_SCHOLAR_API_KEY=your-key   # optional, without it uses free tier
GITHUB_TOKEN=ghp-...                 # optional, for repo enrichment
EOF

# Run the full pipeline
awescholar --config config.json crawler run

# Or pass query directly
awescholar --config config.json crawler run "perturbation prediction|single cell" --date 2025-01-01:2025-05-30

# Monthly report: --month derives the date range, output dir (month_reports/YYMM), and report name
awescholar --config config.json crawler run --month 2026-05
```

Exporting the same variables in `~/.zshrc` also works and takes precedence over the `.env` files; the `.env` keyring is the reliable option when awescholar is invoked from non-interactive shells.

The Semantic Scholar API key is resolved in this order: `--ss-api-key` CLI flag > `semantic_scholar.api_key` in the project config.json > `semantic_scholar.api_key` in `~/.config/awescholar/config.json` > `SEMANTIC_SCHOLAR_API_KEY` (or legacy `SEMANTICSCHOLAR_API_KEY`) environment variable > `.env` files (project `.env` > `~/.config/awescholar/.env`). When no key is found anywhere, awescholar prints a warning to stderr and falls back to the anonymous free tier.

```bash
awescholar --ss-api-key "your-key" crawler search "AI agent" --limit 10
```

The Zotero API key follows the same pattern: `--zotero-api-key` CLI flag > `zotero.api_key` in config.json > `ZOTERO_API_KEY` environment variable > `.env` files. Create one at https://www.zotero.org/settings/keys with read/write access for `zotero push`. A user library needs no id (the key knows its owner); a group library sets `zotero.library_id`. Zotero writes land on api.zotero.org, so the desktop app sees them after its next sync.

See [Commands](#commands) below for the full CLI reference.

## Detailed Config

Config resolves in two layers, deep-merged so the project file only overrides what it actually sets:

1. `~/.config/awescholar/config.json` — global defaults. Put shared `model_profiles`, `semantic_scholar`, and `github` entries here once.
2. The `--config` file (e.g. `month_reports/config.json`) — per-project overrides: search query and dates, filter settings, output paths, categories, and the `model.profile`/`model.name` choice.

Copy `config.example.json` from the [repo root](https://github.com/wehuman01/awescholar/blob/main/config.example.json) to either location and fill in your values — or set env vars directly and skip the config files. Commands run without `--config` use the global file alone, so key-dependent commands like `enrich` and `render agentx` work out of the box.

```json
{
    "model_profiles": {
        "glm": {
            "api_key": "${GLM_API_KEY}",
            "base_url": "https://open.bigmodel.cn/api/paas/v4"
        },
        "deepseek": {
            "api_key": "${DEEPSEEK_API_KEY}",
            "base_url": null
        }
    },
    "model": {
        "profile": "glm",
        "name": "glm-5.1"
    },
    "agent_models": null,
    "semantic_scholar": {
        "api_key": "${SEMANTIC_SCHOLAR_API_KEY}"
    },
    "github": {
        "token": "${GITHUB_TOKEN}"
    },
    "zotero": {
        "api_key": "${ZOTERO_API_KEY}",
        "library_type": "user",
        "library_id": null
    },
    "search": {
        "query": "AI agent|large language model|foundation model",
        "fields_of_study": ["Biology", "Medicine", "Computer Science"],
        "publication_date": "2025-01-01:2025-05-30",
        "limit": 100,
        "include_abstracts": true
    },
    "filter": {
        "limit": 20,
        "research_interests": null
    },
    "output": {
        "db_path": "output",
        "report_filename": null
    },
    "pipeline": {
        "skip_search": false,
        "use_updater_json": false,
        "use_filtered_json": false,
        "existing_json_path": null,
        "merge_new_to_old": false,
        "data_json_path": null
    },
    "categories": ["Foundation Models", "Drug Discovery", "Perturbation Study"]
}
```

`${VAR}` patterns are expanded from environment variables at load time.

**`model.name`** — just the model name, e.g. `glm-5.1`, `deepseek-chat`, `gpt-4o`. The `openai/` prefix is auto-prepended for OpenAI-compatible endpoints — do NOT add it manually.

**`temperature`** — sampling temperature for every LLM call (default `0.0`). Settable at three levels; more specific wins: `model_profiles.<p>.temperature` > `model.temperature` (and `agent_models.<agent>.temperature`) > default. Endpoints that only accept one value need this — kimi's coding API, for example, rejects anything but `1`.

**`model_profiles`** — reusable profile map. Each profile defines `api_key`, `base_url`, and optionally `temperature`. Referenced by `model.profile` or `agent_models.*.profile`, avoiding credential duplication.

**`agent_models`** — override model per agent (annotator, filterer, reporter). Each entry can use `profile` to reference a `model_profiles` entry, or set `name`/`api_key`/`base_url` directly:
```json
"agent_models": {
    "annotator": { "profile": "deepseek", "name": "deepseek-chat" },
    "filterer":  { "profile": "glm", "name": "glm-5.1" },
    "reporter":  { "profile": "glm", "name": "glm-5.1" }
}
```

**`pipeline`** — control flow to skip/reuse intermediate results:
- `skip_search`: load papers from DB instead of searching
- `use_updater_json`: reuse existing `updater.json` (skip search + annotate)
- `use_filtered_json`: reuse existing `updater_filter.json` (skip to report)
- `existing_json_path`: custom path for updater JSON
- `merge_new_to_old`: auto-merge filtered results into your project data JSON after pipeline
- `data_json_path`: project data JSON path used by `merge_new_to_old`; required when `merge_new_to_old` is `true`

`existing_json_path` and `data_json_path` are different files. `existing_json_path` points to the annotation intermediate file (`updater.json`) used to resume or write the annotate step. `data_json_path` points to the long-lived curated project data JSON that receives filtered papers when `merge_new_to_old` is enabled.

**`filter.research_interests`** — optional string describing research focus, passed to filterer for relevance weighting.

**`search.query`** — if set, `crawler run` can be called without a CLI query argument.

**`archive.stars_style`** — the shape `githubStars` keeps in the project data JSON: `numeric` (default, a bare int refreshed by `updater enrich`) or `badge` (a shields.io URL; enrich then writes badge URLs and never rewrites them to ints).

Supported LLM providers: any OpenAI-compatible API via `base_url` (e.g. GLM, DeepSeek, Gemini, Mistral, local endpoints).

## Commands

```bash
awescholar -v                                         # Show version

# Scaffold a new curated paper-list repository
awescholar init                                       # Website-first repo in the current directory (Biology defaults)
awescholar init awesome-ai-foo                        # Scaffold into a subdirectory
awescholar init --template vt                         # Awesome-AI-Virtual-Tumor style website (default: bio)
awescholar init --title "Awesome AI Foo" --github-repo Webioinfo01/Awesome-AI-Foo \
                 --website http://foo.webioinfo.top/ --category "AI Agents" --category Reviews
awescholar init --no-zh --no-branding                 # English-only README, no ecosystem/support sections
awescholar init --tables                              # Classic mode: also embed README table markers
awescholar init --no-serve                            # Skip the local preview server (e.g. in scripts)
awescholar init --port 8123                           # Preview on another port (default: 8000)
awescholar init --force                               # Proceed even if the target directory is not empty

# Paper discovery pipeline
awescholar crawler search "query"                     # Search Semantic Scholar
awescholar crawler annotate                           # Annotate papers in DB
awescholar crawler annotate --input papers.json       # Annotate from JSON (skip DB)
awescholar crawler filter --limit 20                  # Select top papers
awescholar crawler filter --input updater.json        # Filter from custom JSON
awescholar crawler report                             # Generate report (stdout)
awescholar crawler report updater_filter.json -o report.md  # Report from custom JSON
awescholar crawler run ["query"]                      # Full pipeline (query optional if set in config)
awescholar crawler run --month 2026-05                # Full pipeline for one month -> month_reports/2605/report.md
awescholar crawler run --period 2026-06-1             # Half-month: P=1 is 01–15, P=2 is 16–end -> month_reports/2606_1/report.md

# Archive management
awescholar updater update --direction new2old --input X --archive data.json  # Merge (suspected duplicates held back)
awescholar updater update --direction new2old --input X --archive data.json --no-dedupe  # Merge everything, skip duplicate detection
awescholar updater dedupe --review output/dedupe_review.json --archive data.json --keep published  # Resolve held-back pairs
awescholar updater publish-scan --archive data.json   # Check archived preprints for published versions (dry run -> publish_review.json)
awescholar updater publish-scan --archive data.json --apply  # Scan + upgrade in one shot (venue/DOI/paperUrl/citations switch, curation fields stay)
awescholar updater publish-scan --archive data.json --review publish_review.json --apply  # Apply a reviewed queue without rescanning
awescholar updater publish-scan --archive data.json --only XunZi --limit 5   # Scope by DOI/title substring, cap the scan
awescholar updater publish-scan --archive data.json --pair 10.48550/arXiv.2508.10492 10.1038/x  # Manual pair for retitled work no database links
awescholar updater search --json-file papers.json --by title   # Search, save for review
awescholar updater search --archive data.json --by title       # Search and add directly
awescholar updater search --archive data.json --category "AI Agents"  # Add to a specific category
awescholar updater search --archive data.json --by doi 10.1038/s41467-025-59628-y  # Non-interactive: DOIs as arguments
awescholar updater search --archive data.json --by doi 10.1038/x --code-url owner/repo --annotate  # Known repo + LLM-written domain line
awescholar updater add --archive data.json            # Interactively add a record to project data JSON
awescholar updater backfill --archive data.json       # Fill empty affiliation/team/citations (Semantic Scholar + Crossref + OpenAlex)
awescholar updater backfill --archive data.json --only XunZi   # Scope to entries by DOI or title substring (repeatable)
awescholar updater backfill --archive data.json --fields citations  # Only citation counts
awescholar updater enrich --archive data.json         # Fill empty codeUrl from GitHub search + refresh githubStars
awescholar updater enrich --archive data.json --limit 20 --no-llm  # Resolve at most 20 papers, heuristic matches only
awescholar updater enrich --archive data.json --only XunZi   # Resolve/refresh matching entries only
awescholar updater enrich --archive data.json --since 2026-09-01  # Only entries added on/after this date (needs addedAt)
awescholar updater enrich --archive agents-snapshot.json --agentx  # Refresh an AgentX registry snapshot (stars/pushedAt/openIssues/language/license/description/homepage/archived; status strictly preserved)
awescholar updater download --archive data.json       # Download open-access PDFs -> pdfs/ (arXiv direct + OpenAlex OA links; bot-gated pages reported, never forced)
awescholar updater download --archive data.json --only XunZi   # Download matching entries only (DOI or title substring, repeatable)
awescholar updater download --archive data.json --out docs/pdf --force  # Other directory; re-download existing files
awescholar updater download --doi 10.1038/s41467-025-59628-y  # Standalone DOI, no archive needed
awescholar updater download --arxiv 2609.11115        # Standalone arXiv ID

# Render artifacts (render) — derived from project data JSON, never modify it
awescholar render readme --archive data.json         # Generate README tables (with .bak backup)
awescholar render readme --archive data.json --no-backup  # Generate README without backup
awescholar render counts --archive data.json         # Refresh website-first README paper counts
awescholar render rss --archive data.json            # Generate RSS feed
awescholar render digest --archive data.json --month 2026-05   # Digest of the month's archive papers -> month_reports/2605/digest.md
awescholar render digest --archive data.json --month 2026-05 --no-llm   # Tables only, no model key needed
awescholar render agentx --archive data.json -o candidates.json  # Papers with GitHub repos as AgentX candidate agents
awescholar render agentx --archive data.json -o c.json --category-map map.json --default-category platforms
awescholar render agentx --archive data.json -o c.json --categories "AI Agents,Reviews" --exclude-snapshot agents-snapshot.json  # Scope categories, skip already-registered repos
awescholar render agentx --archive data.json -o c.json --exclude-snapshot agents-snapshot.json --llm-category  # LLM-picked category slugs that exist in the snapshot

# Read-only archive queries (reader) — no config needed, never modify data
awescholar reader query --archive data.json "single cell perturbation"   # Keyword search over the archive
awescholar reader query --archive data.json "LLM agent" --category "AI Agents" --top 5 --json
awescholar reader related --archive data.json --doi 10.1/x   # Papers related to one seed (in-archive or external)
awescholar reader related --archive data.json --title "Some paper title" --top 5 --json  # External seed by title
awescholar reader recommend --archive data.json --field "AI for biology" --top 10   # Must-read ranking (offline)
awescholar --config config.json reader recommend --archive data.json --field "..." --llm   # LLM-ranked with reasons
awescholar reader stats --archive data.json           # Archive statistics
awescholar reader stats --archive data.json --category "AI Agents"   # Stats for one category (repeatable)

# Zotero library exchange — the reader's personal library as pipeline input/output
awescholar zotero pull --collection "Reading List"    # Collection -> zotero_papers.json for `updater update` (read-only)
awescholar zotero pull --collection "DROMA" -o papers.json --category "AI Agents"   # Custom output/category
awescholar zotero push --archive data.json --collection "2605 Monthly"   # Dry run: classify + write zotero_review.json
awescholar zotero push --archive data.json --collection "2605 Monthly" --apply    # Create the to-add items in Zotero
awescholar zotero push --archive data.json --collection "2605" --category "AI Agents" --tag must-read --apply
```

## AgentX hub

The typical hub workflow (native commands; curation always runs through `awescholar` itself):

```text
render agentx → updater add --agentx --from-json → updater enrich --agentx → verify --agentx → commit
```

```bash
awescholar updater add --agentx owner/repo --category <slug> [--tags "A,B"] [--paper URL]
awescholar updater enrich --agentx
awescholar updater backfill --agentx [--fields paper-meta,venue-tags,citations]
awescholar verify --agentx
```

> The v0.3.0 `agentx` console script (short aliases over these commands)
> was removed in v0.3.2 — one command name, one owner. Hub **operations**
> (sync the snapshot into the hub database, moderate reviews, mirror to
> the public hub) live in the separate
> [`agentx-hub-cli`](https://github.com/Webioinfo01/agentx-hub-cli) npm
> package (v0.2.0+), which wraps the hub website's own scripts and
> workflows.

Command mapping (old `agentx-cli` v0.1.x → `awescholar`):

| Old `agentx-cli` | New `awescholar` |
|---|---|
| `agentx add owner/repo --category X --tags A,B` | `awescholar updater add --agentx owner/repo --category X [--tags "A,B"] [--name] [--paper] [--homepage] [--description]` |
| `agentx add --from-json F` | `awescholar updater add --agentx --from-json F` (batch, all-or-nothing) |
| `agentx snapshot` | `awescholar updater enrich --agentx [--archive data/agents-snapshot.json]` (metrics + lifecycle: 404→gone, status re-derivation, retirement freeze, license fallback; `--archive` defaults to `data/agents-snapshot.json` in `--agentx` mode) |
| `agentx enrich-papers` | `awescholar updater backfill --agentx --fields paper-meta [--refresh] [--only substring]` (also syncs venue tags) |
| `agentx refresh-citations` | `awescholar updater backfill --agentx --fields citations` |
| — | `awescholar updater backfill --agentx --fields venue-tags [--only substring]` (sync paper venues into tags: registered canonical tag for known venues, auto-generated slug for new ones; non-venue sources are skipped) |
| `agentx validate` | `awescholar verify --agentx` (offline invariants gate; CI runs this) |

Environment variables: `GITHUB_TOKEN` (recommended), `SEMANTIC_SCHOLAR_API_KEY` or `SEMANTICSCHOLAR_API_KEY` (recommended for backfill).

Each subcommand accepts `--input` (or positional `input` for report) to read from a specific file instead of the default path. This lets you re-run any step independently without re-running the full pipeline.

`crawler run --month 2026-05` replaces the copy-a-config-per-month workflow: it derives the search dates (`2026-05-01:2026-05-31`, leap years included), the output directory (`month_reports/2605`), and the report name (`report.md`) from one argument, so a single tracked base config serves every month. `--period 2026-06-1` is the half-month face of the same idea (`P=1` is 01–15, `P=2` is 16–end; output lands in `month_reports/YYMM_P`). `--month`, `--period`, and `--date` are mutually exclusive. The default report filename is `{db_path}/report.md` — the model name no longer leaks into it; instead every report opens with a provenance comment recording the awescholar version, the model, and the date scope. `render digest --month 2026-05` is the other face of a monthly report: it summarizes the papers already curated in `data.json` for that month (by their `year` field), with an LLM narrative when a model is configured or structured tables with `--no-llm` — useful for publishing a digest that always matches what the archive actually holds.

The filter step gates on scope before quality: papers whose subject falls outside the research interests (a shared technique like an LLM applied in an unrelated domain) are excluded regardless of venue, `filter.limit` is an upper bound rather than a quota, and selecting fewer papers when fewer qualify is the expected outcome.

`updater enrich` links papers to their official GitHub repositories. Papers without a `codeUrl` are searched on GitHub (arXiv ID first, then the leading system name, then the full title — a round whose candidates are all rejected falls through to the next); a heuristic scorer accepts only corroborated matches — a repo name derivable from the paper title plus an arXiv ID cited by the repo itself — and ambiguous races go to the configured LLM for a final verdict (`--no-llm` keeps heuristics only). The star shape is a config convention, not a flag decision: with `archive.stars_style: "badge"` (e.g. [Awesome-AI-Meets-Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)) enrich writes `https://img.shields.io/github/stars/owner/repo` into `githubStars` and never rewrites an existing badge URL to a number; the default `numeric` refreshes bare ints and migrates legacy badge values. `--only "DOI or title substring"` (repeatable) scopes the run to matching entries — the same flag exists on `updater backfill` — so one entry can be topped up without touching the rest of the archive. A `GITHUB_TOKEN` is strongly recommended (config `github.token`, `GITHUB_TOKEN` env, or `--github-token`): the anonymous tier allows only 10 searches/minute and 60 repo reads/hour.

`render agentx` turns archive papers that carry a github.com repo into candidate agents for an [AgentX](https://github.com/Webioinfo01/agentx-hub)-style registry: the output matches the agentx snapshot entry shape (slug/name/repo/paperMeta/category plus live metrics when a token is available), with slugs generated by agentx rules. Map your archive categories to agentx category slugs via a `--category-map` JSON file; unmapped papers fall into `--default-category`. No category list is hardcoded here: when `--exclude-snapshot` points at an agentx snapshot, the categories actually present in that file are the source of truth, and mapped or default slugs missing from it draw a warning (without a snapshot there is no validation). The file is a review queue for agentx intake, not a drop-in snapshot — `source`/`sourceUrl` record provenance on every exported agent. Ingestion is the maintainer's `awescholar updater add --agentx --from-json <file>` (replaces the former `agentx add --from-json` from agentx-cli) inside the hub checkout, which re-validates categories and re-fetches live metrics on its side (tags are deliberately not exported; the tag registry belongs to the target repo). `--llm-category` (needs `--exclude-snapshot` for the category list) asks the configured annotator model to pick each candidate's agentx category instead of leaving everything on the `--default-category` floor; picks are kept only when the slug exists in the target snapshot.

`updater search` writes canonical links and can carry known facts: `paperUrl` prefers the DOI link (`https://doi.org/…`) over the Semantic Scholar page, `--code-url owner/repo` writes a repo you already know into `codeUrl` (with `archive.stars_style: "badge"` it also writes the shields.io badge into `githubStars`), and `--annotate` fills the one-line `domain` of the added papers with the configured annotator LLM — the same annotator the crawler pipeline uses, run once over just the new records. After papers land, `updater search --archive` and `updater update --direction new2old` print the natural next step (`render counts` / `render rss`) so README counts and the RSS feed never silently go stale.

`reader` commands are the read-only face of the curated archive: keyword search (`query`), find related work for a seed paper — including one pasted from outside the archive via `--input` (`related`), must-read ranking per research field (`recommend`, offline or `--llm`), and archive statistics (`stats`). They never modify data and need no config, so an AI agent can answer "what's in my archive about X" instantly. During `updater update`, papers whose titles near-match an existing entry (the preprint-vs-published signature) are held back into `dedupe_review.json` next to the input file instead of being merged; a heavily retitled pair that dodges the title bars is still held back when its author roster almost fully overlaps; resolve them with `updater dedupe --keep newer|published|both`, or bypass detection with `--no-dedupe`.

`updater publish-scan` is the proactive mirror of that flow: instead of waiting for a published version to arrive as new input and collide with the archived preprint, it scans the archive for preprints (by preprint-server DOI prefix or venue — bioRxiv/medRxiv old and new, arXiv, ChemRxiv, Research Square, Preprints.org, Authorea, SSRN), verifies each through three channels — Semantic Scholar by DOI, fuzzy S2 title search, then Crossref `query.title` (title drift between preprint and version of record is the norm: "AlphaFold3" vs "AlphaFold 3"), with title-matched candidates gated by dedupe-grade similarity plus a non-empty venue so repost copies never win — and queues upgrades into `publish_review.json` next to the archive. The dry run is the default; `--apply` upgrades in place — venue, DOI, paperUrl, year, authors and citations switch to the version of record while category, codeUrl, githubStars, domain and affiliation stay — and `--review <file> --apply` applies a reviewed queue without rescanning. `--pair PREPRINT PUBLISHED` queues a manual upgrade for retitled twins the scan cannot prove. The same fixed preprint detection lets `updater dedupe --keep published` correctly prefer a journal version over a bioRxiv preprint.

`zotero` connects the curation pipeline to the reader's personal Zotero library through the Zotero Web API (api.zotero.org — no local Zotero needed). `zotero pull` maps one collection into the pipeline record shape (`{category: [papers]}` under `--category`, default `Zotero`), ready for `updater update --direction new2old`; preprint/published twins inside the pull are held back by the updater's usual dedupe, so pull never needs its own. `zotero push` is the month-end mirror: it classifies every archive record (or `--category` subset) against the whole library by DOI then normalized title — `already-in-collection` (no-op), `in-library` (exists outside the target collection — reported, membership never forced), or `to-add` — writes the queue to `zotero_review.json` next to the archive, and only `--apply` creates the missing items (collection included, tagged `awescholar` + archive category + `--tag` extras; preprint venues become Zotero `preprint` items, everything else `journalArticle`; authors ride as single-field creators, no invented name splitting). Writes are single-shot `Zotero-Write-Token` posts, rerunning `--apply` is idempotent — created items classify as already-in-collection — and everything lands cloud-side, so the desktop app picks it up on its next sync.

`render readme` updates only the generated region between `<!-- AWESCHOLAR:START -->` and `<!-- AWESCHOLAR:END -->`. That generated region contains the awescholar table of contents and category tables. Keep custom headings, citation, and project text outside that region. Existing README files without those markers are rejected instead of being overwritten. If the README does not exist yet, `--title` controls the generated top-level heading.

When `--readme` is not specified, `render readme` auto-discovers all `README*.md` / `readme*.md` files in the current working directory that contain `<!-- AWESCHOLAR:START -->` markers and updates each one. This is useful for maintaining multilingual READMEs (e.g., `readme.md` + `README.zh-CN.md`) — the table content stays in sync automatically.

`awescholar init` scaffolds a complete website-first repository — like [Awesome-AI-Meets-Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology) — in one command: bilingual landing-page READMEs, a searchable statistics website (`--template bio` or `--template vt`), an empty `docs/data.json` wired into `config.json`, an RSS feed, MPL-2.0 `LICENSE`, `CONTRIBUTING.md`, and `.gitignore`. A custom `--website` domain also writes `docs/CNAME` for GitHub Pages. All options are optional: bare `awescholar init` in an empty directory uses the Awesome-AI-Meets-Biology identity and defaults. After scaffolding, init serves `docs/` at `http://127.0.0.1:8000/` so you can review the site before pushing (the page fetches `data.json`, so it needs an HTTP server rather than a double-click); stop it with Ctrl+C, skip it with `--no-serve`, or pick another port with `--port`. For repos whose papers live on the website (no embedded tables), run `awescholar render counts --archive docs/data.json` after merging new papers — it refreshes the per-category counts, totals, and badges in `readme.md` / `README.zh-CN.md` / `README.md` (whichever exist in the working directory; pass `--readme` to target other files).

## Development

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for setup, architecture, testing, and code style.

```bash
pip install -e ".[dev]"
pytest
```

## Workflow

```
crawler search -> crawler annotate -> crawler filter -> crawler report
                                                        |
                                                        v
                                              updater_filter.json
                                    (or auto-merge if merge_new_to_old=true)
                                                        |
                                  +---------------------+---------------------+
                                  |                                         |
                          updater update new2old                  updater search --json-file
                                  |                                         |
                                  v                                         v
                            data.json                               papers.json (review)
                                  |                                         |
                          render readme / rss                    updater update new2old
                                                                          |
                                                                          v
                                                                    data.json
```

Each step produces a JSON intermediate file. You can re-run any step independently. `data.json` also feeds the read-only `reader` commands (query / related / recommend / stats) — the daily-use query face on top of the monthly curation pipeline.

## Awesome Ecosystem

awescholar is part of a growing family of "awesome" tools — CLI-first, local-first, and operable by AI agents.

### CLI Tools

- **[aweskill](https://aweskill.wehuman.top/)** — CLI-first skill package manager supporting 47+ AI coding agents.
- **[aweswitch](https://github.com/wehuman01/aweswitch)** — Agent profile switcher for Claude Code, Codex, and OpenCode.
- **[awerouter](https://github.com/wehuman01/awerouter)** — Smart router that splits requests between Flash and Pro models using structural signals, cutting unnecessary model spend.
- **[aweshelf](https://github.com/wehuman01/aweshelf)** — Bookmark, categorize, and restore AI coding sessions; pairs with aweswitch to save profiles and launch with one command.
- **[aweshare](https://github.com/wehuman01/aweshare)** — Share local Ollama/vLLM backends, domestic coding plans, or authorized OpenAI/Anthropic subscriptions through a self-hosted hub — a sharing economy for tokens.
- **[awewarm](https://github.com/wehuman01/awewarm)** — Subscription window warmer that keeps AI coding-plan windows active, for local setups and through a remote hub server.
- **[awescholar](https://github.com/wehuman01/awescholar)** — AI-agent-operable scientific literature discovery and curation.
- **[awecontrib](https://github.com/wehuman01/awecontrib)** — One verify entry per repo: writes a small `verify` file and a minimal CI, so local and CI run the exact same checks.

### Desktop Apps

- **[awefork](https://github.com/wehuman01/awefork)** — Desktop workbench that turns AI coding-agent sessions into a tree: fork any turn, keep every branch. Pairs with aweswitch — launch a session with a profile, then fork its history.
- **[awedot](https://awedot.wehuman.top/)** — A floating orb at your screen edge keeps track of the current AI session: bookmark it in one click, resume anytime, and pair with aweswitch to pin the agent's config (e.g., relaunch with the GLM model).

### Project Collections

- **[Awesome AI Meets Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)** — A curated survey of AI applications in biology, bioinformatics, and biomedical research. Powered by awescholar.
- **[Awesome AI Virtual Tumor](https://github.com/Webioinfo01/Awesome-AI-Virtual-Tumor)** — A curated collection of state-of-the-art AI systems for virtual tumor modeling and simulation: static models, dynamic models, agents, benchmarks, and reviews.

## Support

If awescholar saves you time, consider supporting it:

- ⭐ Star the repo — it helps others find it.
- ☕ [Ko-fi](https://ko-fi.com/mugpeng) — buy me a coffee.
- 💬 WeChat — scan the QR code below.

<p align="center">
  <img src="assets/images/wechat-pay.jpg" alt="WeChat Pay" width="240">
</p>

> Sponsors keep this project maintained — thank you.
