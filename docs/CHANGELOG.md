# Changelog

## v0.3.7

model profiles and model/agent_models entries accept a temperature override (default 0.0, previous behavior); resolves endpoints that only accept one value, e.g. kimi's coding API requires temperature=1 — resolve_agent_settings/resolve_agent_config now return (model, api_key, base_url, temperature) and every LLM call site (crawler annotate/filter/report, digest, enrich tiebreak, agentx export --llm-category, reader recommend --llm, updater search --annotate) honors it

## v0.3.6 - 2026-10-01

### Added

- New venue tag `Innovation` for Cell-partner journal *The Innovation*, with `VENUE_ALIASES` entries for the full title ("The Innovation") and Semantic Scholar's venue spelling ("Innovation (Cambridge (Mass.))") — the hub's battery-LLM review entry carries `paperMeta.venue: "The Innovation"`, which now resolves to the tag and passes the venue-tags invariant once the entry carries `tags: ["Innovation"]`.

### Fixed

- `render counts` now refreshes a "Browse the Collection" bullet whose anchor uses the website's shorter section id when it uniquely prefixes the category-derived slug — Awesome-AI-Meets-Biology's `Databases/Simulation` bullet links to `#databases`, which never matched `databases-simulation`, so that line's count silently went stale on every render. Ambiguous prefixes (two categories sharing the short slug) are still left untouched.


## v0.3.5 - 2026-10-01

### Added

- AgentX snapshot version stamp: `write_snapshot` now writes a top-level `generatedAt` (UTC, second precision) on every write that actually changes agents+counts. The website's snapshot apply becomes monotonic on this clock — a stale copy of the file (an old deployment bundle, an unpulled working tree) can no longer roll the registry database back to older metrics, which is how a local dev boot silently reverted a fresh CI refresh. A write that changes nothing leaves the file byte-identical (no restamp, no diff), so quiet days stay commit-free exactly as before. `validate.py` accepts the stamp when present and rejects a non-ISO value.

## v0.3.4 - 2026-09-30

### Added

- New primary AgentX category 'models' ("Models & Simulation") — registry entries whose deliverable is a model rather than an agent workflow or an analysis library: representation-learning frameworks (MitoSpace4D), particle-based simulation engines and digital twins (ReaDDy-Cell, scMultiSim). Slots after 'datasets' in CATEGORY_ORDER. validate.py accepts the slug; intake via 'updater add --agentx --category models'.

### Changes

- AgentX status policy: active freshness now outranks the `stable` verdict — a stable (or stable-qualifying) repo that keeps pushing within `ACTIVE_IDLE_DAYS` (120) reads `active`; once quiet past 120 days the stable verdict resurfaces on its own, so a quiet stable record still never slides into `stale` or `archived` (`resolve_repo_status` reorders the freshness check ahead of the verdict). Two consequences: `stable` leaves `_PROTECTED_STATUSES` (only `no-repo` is never rederived), and a stable record whose owner archives the repo on GitHub now maps to `gone` like every other status — the verdict was never a shield against the repo disappearing.

## v0.3.3

New primary AgentX category 'reviews' ("Reviews & Surveys") — registry entries whose deliverable is a curated reading list: survey/awesome-list companion repos. Slots between 'datasets' and 'safety-security' in CATEGORY_ORDER. validate.py accepts the slug; intake via 'updater add --agentx --category reviews'.

## v0.3.2 - 2026-09-19

### Changes

- Removed the `agentx` console script introduced in v0.3.0 — one command
  name, one owner. Registry curation uses awescholar's native commands
  (`updater add/enrich/backfill --agentx`, `verify --agentx`); hub
  **operations** (sync the snapshot into the hub database, moderate
  reviews, mirror to the public hub) moved to the reborn npm package
  [`agentx-hub-cli` v0.2.0+](https://github.com/Webioinfo01/agentx-hub-cli),
  which wraps the hub website's own scripts and workflows. Upgrading the
  package removes the stale `agentx` entry point.

## v0.3.1 - 2026-09-19

### Features

- AgentX snapshot records now carry an optional `listedAt` curation date (date-only ISO, stamped by `updater add --agentx` at intake): `updater enrich --agentx` carries it along untouched instead of dropping it, and `verify --agentx` validates the shape when present. Records that predate the field simply omit it — the AgentX Hub website reads it as the editorial "when this agent entered the registry" clock (New today / New badges), decoupled from database row timestamps.

## v0.3.0 - 2026-09-18

### Features

- New `agentx` console script, installed alongside `awescholar`: `agentx add | enrich | backfill | validate` are short aliases over the AgentX modes of the existing subcommands (`updater add/enrich/backfill --agentx`, `verify --agentx`). A pure argv rewrite — every flag, default and validation is inherited, nothing re-implemented; the old npm `agentx-hub-cli` surface maps 1:1 except `snapshot` → `enrich` and `enrich-papers`/`refresh-citations` → `backfill` fields.
- `cli.main` now accepts optional `argv` and `prog` arguments (console-script behavior unchanged); the alias passes `prog="agentx"` so help and `-v` output carry the invoked name.

## v0.2.9 - 2026-09-18

### Fixes

- `updater backfill --agentx --fields paper-meta` now re-derives the agent's status with the freshly resolved venue: a journal/conference paper promotes to `stable` at any star count instead of lingering in the pre-paper status its add-time derivation froze in (the "published but stuck in nursery" bug class). Protected statuses (`stable`, `no-repo`) resolve to themselves; the run reports a `status-promoted` count.

### Features

- New registered venue tags: `Cell`, `Nature-Medicine`, `NEJM-AI`, `JCST`, `Advanced-Materials`, `ACL-Findings`, `EMNLP-Findings` — venue spellings that fold onto these tags now project onto agent tags via venue-tags backfill. Aliases include Journal of Computational Science and Technology → `JCST`, the Semantic Scholar misspelling "Advances in Materials" → `Advanced-Materials` (10.1002/adma), and both Findings-track spellings.

## v0.2.8 - 2026-09-18

### Features

- New primary AgentX category `datasets` ("Datasets") — for registry entries whose deliverable is the data itself, hosted off-GitHub (HuggingFace datasets, portals) and registered via the existing `no-repo` shape; slots between `benchmarks` and `safety-security` in `CATEGORY_ORDER`. First entry: Tahoe-100M.
- Optional PubMed search source for the crawler pipeline: set `search.pubmed: true` to also query NCBI E-utilities and merge normalized PubMed records into the search step (off by default)

## v0.2.7 - 2026-09-18

### Features

- `updater backfill --agentx --fields venue-tags`: projects `paperMeta.venue` onto tags via the registered-venue lookup (offline, no network); `--fields paper-meta` and the default run sync it after resolving papers, and `verify --agentx` enforces the invariant — a venue that maps to a registered tag must carry that tag
- S2 records for fresh arXiv preprints (empty DOI and venue) now derive both from the `externalIds.ArXiv` ID — `doi = 10.48550/arXiv.<id>` (DataCite mints one for every arXiv paper) and `venue = arXiv` — in every search/backfill projection, both orientations; existing DOI/venue values are never overridden

## v0.2.6 - 2026-09-18

AgentX absorption release — the standalone agentx-cli (TypeScript) is fully replaced by awescholar, one tool for both orientations: awesome-list projects are paper-oriented (the archive is a category dict of paper records) and the AgentX hub is project-oriented (the snapshot is a slug-sorted agent list keyed by GitHub repo). The registry logic — tag policy, lifecycle rules, writer invariants — now lives in `awescholar.agentx`, and every former agentx-cli command has an awescholar equivalent. No Node runtime, no subprocess bridge, no shape-sniffing version detection.

### Highlights

- `updater add --agentx owner/repo --category <slug> [--tags "A,B"]` replaces `agentx add`: validates the repo against the registry category/tag policy, fetches live GitHub metrics, derives the initial status, appends in stable slug order
- `updater add --agentx --from-json candidates.json` replaces `agentx add --from-json`: batch-intakes a `render agentx` candidate file, all-or-nothing
- `updater enrich --agentx` now covers the full former `agentx snapshot`: the GitHub metrics refresh (existing) plus the lifecycle pass (new) — 404 → gone via HEAD checks, status re-derivation, retirement freeze/clear, NOASSERTION license text fallback — and writes slug-sorted with recomputed counts
- `updater backfill --agentx` replaces `agentx enrich-papers` and `agentx refresh-citations`: `--fields paper-meta` resolves paperMeta from DOI/arXiv/title clues via Semantic Scholar (`--refresh` re-resolves existing records), `--fields citations` refreshes citation counts; default fills both
- New top-level `verify --agentx` replaces `agentx validate`: the offline writer-invariants gate (CI runs exactly this), exit 1 with an itemized problem list on any violation
- `render agentx` unchanged in behavior; its output now documents the new intake command
- `agentx_slugify` is now Unicode-aware, matching the former TypeScript slugify (CJK and accented names slug identically on both sides); newly exported slugs with non-ASCII names may differ from previous ASCII-only exports
- Breaking: the `agentx` npm binary is deprecated — replace `agentx add|snapshot|enrich-papers|refresh-citations|validate` with the awescholar commands above; `--archive` defaults to `data/agents-snapshot.json` in `--agentx` mode

## v0.2.5 - 2026-09-17

### Features
- Single-paper curation: `updater search` now writes DOI-first `paperUrl`, new `--code-url owner/repo` and `--annotate` flags for direct repo annotation with one LLM batch call; `--only` repeatable scoping on `updater enrich`, `updater backfill`, and citation fills; new `archive.stars_style` config (`numeric` or `badge`); agentx `--emit commands` now writes an executable `pnpm agent:add` script instead of candidate JSON
- Monthly-report workflow: `crawler run --month YYYY-MM` derives dates, output dir (`month_reports/YYMM`), and report name from one argument; `render digest --month` summarizes a month straight from the archive with LLM narrative or `--no-llm` structured tables; report filenames no longer embed model names; filter gates on scope before venue prestige with `filter.limit` as an upper bound
- `updater publish-scan --archive`: checks every archived preprint against Semantic Scholar (DOI → fuzzy S2 title search → Crossref) and queues version-of-record metadata into `publish_review.json`; `--apply` upgrades venue/DOI/paperUrl/year/authors/citations in place; preprint detection now covers bioRxiv/medRxiv, Research Square, Preprints.org, ChemRxiv, Authorea, and SSRN (not just arXiv)
- Agentx: candidates now named from the paper's system name; new `--llm-category` flag uses configured LLM to derive agent category names

### Refactor
- CLI regroup: `render` group holds all artifact-derivation commands (`render readme`, `render counts`, `render rss`, `render digest`, `render agentx`); `updater citations` folds into `updater backfill --fields citations`; `updater` retains only archive-data lifecycle (search, add, update, dedupe, enrich, backfill) — 12 subcommands reduced to 6
- Breaking: the old names `updater readme`, `updater counts`, `updater rss`, `updater digest`, `updater export-agentx`, and `updater citations` are gone without aliases; switch scripts to `render` names or `backfill --fields citations`

### Fixes
- Dedupe now holds back author-roster-overlap and `codeUrl`-collision pairs for review, not only title similarity; new records stamp `addedAt`; `updater enrich --since YYYY-MM-DD` scopes to entries added on/after that date; `updater publish-scan --pair PREPRINT PUBLISHED` queues manual preprint→published upgrades for retitled twins; `retry_with_backoff` wraps network, LLM, and Semantic Scholar calls for transient-failure resilience
- Archive backups skip timestamped copies when the target file is git-clean; half-month period support via `crawler run --period`

## v0.2.2

Citation-surface + GitHub-enrichment release — the website shows a citation badge under Paper, `updater search` records carry Semantic Scholar citation counts, `updater citations` fills empty counts, `updater enrich` links papers to their official GitHub repositories with live star counts, and `updater export-agentx` turns repo-backed papers into candidate agents for an AgentX-style registry.

### Highlights

- Website templates (`bio` and `vt`) render a citation badge under the Paper link in the Links column: amber pill with a quote icon, compact `1.2k`/`15k` formatting, and a full-count tooltip sourced from Semantic Scholar
- New `awescholar updater citations --archive docs/data.json` batch-fills empty `citations` fields from Semantic Scholar `citationCount` (DOI required; existing counts are never overwritten)
- `CONTRIBUTING.md` documents the `citations` field in the paper schema and points to the backfill command
- New `updater enrich --archive data.json` fills empty `codeUrl` fields: each paper is searched on GitHub (arXiv ID first, then the leading system name, then the full title), a heuristic scorer accepts only corroborated matches (repo name derivable from the title plus an arXiv ID cited by the repo itself — either signal alone stays below the bar), and ambiguous races go to the configured LLM for a final verdict (`--no-llm` keeps heuristics only, `--limit N` caps resolution per run). Papers that already link a github.com repo get `githubStars` refreshed as a numeric count; legacy badge-URL values migrate automatically, including recovering the repo from badge URLs in entries whose `codeUrl` is empty
- New `updater export-agentx --archive data.json -o candidates.json` exports every paper with a github.com repo as an AgentX snapshot-shaped candidate agent (slug/name/repo/paperMeta/category plus live metrics when a token is available), with slugs generated by agentx rules and duplicate repos collapsed; `--category-map` maps archive categories to agentx slugs, unmapped papers land in `--default-category`, `--categories` scopes the export to given archive categories, `--exclude-snapshot` skips repos already registered in an agentx snapshot, and `source`/`--source-url` record provenance. The file is a review queue for agentx intake, not a drop-in snapshot
- Category handling hardcodes neither side's taxonomy: the previously hardcoded nine agentx slugs are gone — `updater export-agentx` now validates mapped and default slugs against the categories actually present in the `--exclude-snapshot` file (the agentx snapshot is the source of truth; no snapshot means no validation), and `reader stats` gains a repeatable `--category` filter that defaults to every category in the archive instead of any fixed list
- GitHub token resolution follows the Semantic Scholar key pattern: `--github-token` > config `github.token` > env `GITHUB_TOKEN`/`GH_TOKEN` > project or `~/.config/awescholar/.env` (auto-loaded); a stderr warning fires when none is found because anonymous limits (10 searches/min, 60 repo reads/hour) are severe
- The README table now derives the stars badge from the repo URL when `githubStars` holds a numeric count, so stars stay live without re-running enrich; legacy badge-URL values still render unchanged. `updater add` no longer writes badge URLs into new records
- Config now resolves in two deep-merged layers: `~/.config/awescholar/config.json` holds global defaults (shared `model_profiles`, `semantic_scholar`, `github`), and the `--config` project file overrides it key by key (nested dicts merge, so a project can override one profile field or one model name without restating the rest). Commands run without `--config` use the global file alone, so key-dependent commands like `updater enrich` work standalone
- Docs now recommend `~/.config/awescholar/.env` as the primary key store: it is loaded by awescholar itself, so keys stay visible to agents and cron invocations whose shells never source `~/.zshrc`; shell env vars still win when present
- The enrich LLM tiebreak now sees each candidate's `created`/`pushed` dates and topics, and the prompt states the collision rule (a repo created or last pushed years before the paper is usually an unrelated older project sharing the name) — acronym collisions such as an HPC tool matching a same-named dataset paper no longer win the tiebreak
- `updater enrich` learns `--agentx`, treating `--archive` as an AgentX registry snapshot (top-level `{agents, counts}`) instead of an awesome-list archive. It refreshes the same field set the agentx registry's own refresh used to inline-fetch (`stars/pushedAt/openIssues/language/license/description/homepage/archived`; license skipped when `NOASSERTION`, homepage filled only for an explicit empty string because agentx snapshots use `null` for "deliberately no homepage") and strictly preserves every other field — `status`, `slug`, `repo`, `githubUrl`, `paperMeta`, category, tags, source — so the registry's `scripts/snapshot.ts` keeps owning the lifecycle (404 → `gone`, retirement resolution, slug dedup, `writeSnapshot`). The existing awesome-list mode is untouched and the new shape mismatches fail loud
- Enrich search rounds now fall through: when the arXiv-ID round surfaces only candidates the scorer and the LLM both reject, the system-name and full-title rounds still run instead of the search silently ending at the first round with any candidates
- The persisted `archived` flag lets the agentx registry's lifecycle pass mark owner-archived repos `gone` in the same run instead of waiting for `pushedAt` to age out
- `updater export-agentx` writes `counts.gone` (the agentx `SnapshotFile` contract; was `graveyard`) and prefers the archive's full `authors` list over the legacy `team` value when building `paperMeta`
- GitHub 403/429 responses now print a stderr warning instead of silently degrading to "no results", so a rate-limited run is distinguishable from an empty one
- `updater search` (by title or DOI) requests `citationCount` and writes it into each record as `citations`, so `--json-file` output and archive additions carry live citation counts; the alias map accepts `citations`, `citationCount`, and `citation_count`, and archive merges keep existing counts when the incoming value is empty. `citations` is data-only — the README table gains no column
- Search now stores the complete Semantic Scholar author list in a new `authors` field instead of keeping only the last author as `team`: `updater search` records and the crawler DB carry the full name list, normalization accepts both the DB blob (`all`) and plain-list forms so the list survives merging into project data, and archive merges treat an empty list as empty so gaps never wipe an existing list (project data records are now 13 fields, the updater pipeline 15)

## v0.2.1

Repository-scaffolding, read-only query, and duplicate-review release — `awescholar init` generates a complete website-first curated list, a new `reader` group gives the archive a query/recommend face, and `updater` holds back suspected preprint-vs-published duplicates for explicit review.

### Highlights

- New `awescholar init` command scaffolds a complete website-first curated-repo — like Awesome-AI-Meets-Biology — in one step: bilingual landing-page READMEs, a searchable statistics website (`--template bio` or `--template vt`), an empty `docs/data.json` wired into `config.json`, an RSS feed, MPL-2.0 `LICENSE`, `CONTRIBUTING.md`, and `.gitignore`; a custom `--website` domain also writes `docs/CNAME`. After scaffolding it serves `docs/` on `127.0.0.1:8000` for local review (skip with `--no-serve`, pick a port with `--port`, auto-increment while a port is busy). New `updater counts` refreshes per-category counts, totals, and badges in website-first READMEs
- New `reader` command group gives the curated archive a read-only query face: `reader query` (keyword search over title/domain/abstract/venue/team with weighted scoring), `reader related` (in-archive neighbors of a seed paper — by `--doi`, `--title`, or a pasted record via `--input`), `reader recommend` (must-read ranking per research field; offline by default, `--llm` adds model-ranked one-line reasons), and `reader stats`. All reader commands are offline, never modify data, and need no config — `--json` serves agent consumption. SKILL.md ships the reader intents in its router plus a response-format contract for reader answers
- `updater update` now holds back suspected duplicates before merging: entries whose normalized-title similarity to an archive entry is ≥ 0.90 (or ≥ 0.80 with a shared author token) but that dodge the exact DOI/title match — the preprint-vs-published signature — land in `dedupe_review.json` next to the input file instead of being appended; `--no-dedupe` restores the old append-everything behavior. New `updater dedupe --review <file> --archive <data.json> --keep newer|published|both` resolves held-back pairs: the winner's non-empty fields overwrite in place (or both entries are kept), and the review file is removed once applied
- The Semantic Scholar API key resolution order is now documented and explicit: `--ss-api-key` CLI flag > `semantic_scholar.api_key` in config.json > `SEMANTIC_SCHOLAR_API_KEY` environment variable (legacy `SEMANTICSCHOLAR_API_KEY` still honored)
- CI and the release workflow now run a single `./verify` entry point (ruff + pytest) so the local gate matches CI exactly
- `updater search` now accepts paper titles/DOIs as positional arguments for non-interactive use (`awescholar updater search --archive data.json --by doi <doi1> <doi2>`); omitting them keeps the previous interactive prompt

## v0.2.0

Backfill release — a new `updater backfill` command recovers missing affiliation/team fields from three web sources, and archive merges stop duplicating papers across categories.

### Highlights

- New `awescholar updater backfill` command fills empty affiliation/team fields in an existing archive, consulting three sources cheapest-per-coverage first: Semantic Scholar batch endpoints (covers names and teams well), Crossref per-DOI work metadata, and OpenAlex curated institution data. Only empty fields are filled, entries never move between categories, and the affiliation always comes from the same author as the team so the pair can never mismatch; the archive is backed up first unless `--no-backup`
- Backfill reliability fixes: paper batches now request `externalIds` (missing DOIs were the real cause of all-null batch results) and all-empty batch responses are retried instead of trusted
- Pathological affiliation blobs from Crossref deposits (worst live case: 710 chars of department + address + author biography) are shortened at write time — values over 200 chars keep only segments naming an institution, max two, capped at 160 chars
- Archive merge now deduplicates globally across categories by DOI, falling back to normalized-title match for papers without a DOI (which also backfills the DOI onto the existing entry) — previously dedup was per-category by DOI only, so the same paper could appear under two categories
- `updater search` accepts `--category` to add papers to a specific category (normalized to an existing spelling, default remains the first category), and its dedup matches titles case/whitespace-insensitively
- New regression test suites for backfill, record dedup, and merge behavior

## v0.1.9

Dependency-health release — minimum Python 3.11, verified dependency floors, leaner install, and CI hardening.

### Highlights

- Require Python >= 3.11: litellm 1.98.0 (2026-08-22) imports `typing.NotRequired` (3.11+) while its metadata still claims 3.10 support, so fresh installs on 3.10 were broken; 3.10 reaches end-of-life in October 2026. CI matrix is now 3.11/3.12/3.13
- Dependencies declare tested lower bounds (`litellm>=1.86`, `semanticscholar>=0.12`, `sqlalchemy>=2.0`, `python-dotenv>=1.0`) — pip can no longer resolve to untested ancient versions
- Drop unused `rich` dependency — never imported by awescholar (litellm brings its own); one less upstream to break
- CI now runs `ruff check` alongside pytest, on Node 24 action versions (`checkout@v7`, `setup-python@v7`, `action-gh-release@v3`) — removes the Node.js 20 deprecation warning; ruff is pinned (`==0.16.5`) so the lint gate is reproducible
- README version badges are now dynamic PyPI badges — no more manual badge bumps at release time (the Chinese README badge had drifted to v0.1.6)
- Remove the `tomli` test fallback and dev dependency — 3.11+ always has `tomllib`

## v0.1.8

Bugfix release — restore the author affiliation data chain that silently broke paper filtering.

### Highlights

- Fix: author detail lookups failed silently on every search — `get_authors` returns objects, not dicts, so the affiliations lookup threw and the exception was swallowed. Author names and affiliations are now fetched and stored correctly (as JSON in the `authors` field)
- Fix: the filter step now receives real `affiliation` values (extracted from stored author data) instead of always-empty strings — the filterer's top ranking priority (premier venues and institutions) finally has data to work with
- Fix: papers loaded from the DB (`skip_search` / `crawler annotate`) now include the `authors` field so team and affiliation extraction also works on resumed runs
- Fix: README table sorting pads unpadded months, so `2025.3` no longer sorts after `2025.12`
- Fix: RSS `lastBuildDate` is now UTC instead of local time labeled as GMT
- Chore: remove unused import, fix `_split_sections` docstring; new regression tests for search persistence, affiliation extraction, and filter payload

## v0.1.7

Documentation restructure — AI agent usage guide, install/usage flow, and contributing docs.

### Highlights

- New `README.ai.md` — dedicated install and usage guide for AI coding agents
- README restructure: move "Powered by aweskill" to top, merge Quick Start into Usage after Config, add AI/human usage sections
- Add aweskill badge to README titles
- Add Webioinfo org link to README
- Update CONTRIBUTING.md with missing modules and cross-reference from README
- Add `docs/todo/refactor_0528.md` planning notes

## v0.1.6

Module refactor, multi-README auto-discovery, and Python 3.10 compatibility fix.

### Highlights

- Refactor: split monolithic `utils.py` into focused modules — `archive.py` (merge operations), `readme.py` (README generation), `rss.py` (RSS feed), with `utils.py` as a backwards-compatible re-export facade
- `updater readme` auto-discovers all README files containing `<!-- AWESCHOLAR:START -->` markers when `--readme` is not specified — supports multilingual READMEs out of the box
- Fix: `html.escape` in XML paper snippets to prevent injection in LLM prompts
- Fix: use `tomli` fallback for Python 3.10 compatibility in tests
- Update CONTRIBUTING.md architecture docs to reflect new module layout

## v0.1.5

Agent install flow, filtering config propagation, licensing metadata, and test maintenance.

### Highlights

- Agent bootstrap docs now install the `awescholar` CLI first, then choose a skill management path (`aweskill` or direct copy)
- README install sections clarify that `aweskill` and direct copy are two ways to manage the awescholar skill, not two separate CLI install methods
- Fix: `filter.research_interests` now reaches the normal full `crawler run` filter path
- Version metadata is kept aligned between package metadata, `__version__`, README badges, and CLI version tests
- Project license metadata changed to MPL-2.0 and a repository LICENSE file was added
- Test suite cleanup removes low-value schema tests, parameterizes duplicate detection coverage, and makes README backup assertions time-independent
- Ruff cleanup removes unused code found during release validation

## v0.1.4

Marker-based README update, data field normalization, and robust merge/readme/rss handling.

### Highlights

- Marker-based README update — `updater readme` now only modifies content between `<!-- AWESCHOLAR:START -->` and `<!-- AWESCHOLAR:END -->`, preserving custom headings, citations, and project text outside that region
- Category normalization — new `categories.py` module for consistent category mapping across pipeline
- Data field normalization (`data_fields.py`) — normalize project data fields and preserve code/product links during merge
- Robust merge/readme/rss — handle missing DOI, mixed year types, and normalized fields without crashing
- Preserve existing README TOC and headers on update
- Hero image and AI agent install guide added to README
- Expanded SKILL.md with full workflow diagrams and command reference

## v0.1.3

Config module extraction, auto-merge pipeline, and filter limit fix.

### Highlights

- Extract `config.py` module — `load_config`, `prefix_model`, `resolve_agent_settings` moved out of `cli.py` for reuse and testability
- `pipeline.data_json_path` — auto-merge filtered results into project data JSON after pipeline completes
- `updater search --json-file` — save search results to flat JSON for review before merging into project data
- `updater readme --no-backup` — skip timestamped README backup creation
- Fix: filter now respects `limit` by truncating in LLM ranking order (previously kept all papers)
- Add ruff as dev dependency (`py310`, `line-length = 100`)
- Add install and PyPI downloads badges to README
- Terminology: "archive" → "project data JSON" across docs and CLI help
- New tests: config loading, agent resolution, CLI help/version, pipeline auto-merge

## v0.1.2

Model profiles, research interests filter, and PyPI publish fix.

### Highlights

- `model_profiles` — named LLM provider presets (api_key + base_url) referenced by `profile` field in `model` and `agent_models`, so switching providers only requires changing one field
- `research_interests` in `filter` config — user-defined interests passed to the filterer for priority-based selection
- `--input` flags on `annotate`, `filter`, `report` subcommands for step reuse without re-running earlier stages
- Reporter prompt: enforce consecutive global index, every paper must appear in report
- Filter prompt: quality-first priority, then relevance to research interests
- PyPI publish switched from OIDC (`pypa/gh-action-pypi-publish`) to `twine upload` with API token
- `config.example.json` updated with `model_profiles` usage

## v0.1.1

CLI restructure, grouped config format, and new single-record commands.

### Highlights

- Group CLI commands into `crawler` (search, annotate, filter, report, run) and `updater` (update, readme, rss, search, add)
- Grouped config format: `model`, `search`, `filter`, `output`, `pipeline`, `agent_models`
- `agent_models` — override LLM model per agent (annotator, filterer, reporter)
- Pipeline flow control: `skip_search`, `use_updater_json`, `use_filtered_json`
- `search.query` in config allows `crawler run` without CLI query argument
- `awescholar updater search` — search Semantic Scholar by title/DOI and add to archive
- `awescholar updater add` — interactively add a single record to archive
- Document `fields_of_study` valid values (23 fields) in search module
- Add Chinese README (README_cn.md), CONTRIBUTING.md, CI/CD workflows
- Add "Scientific Literature Curator" subtitle to README

## v0.1.0

Initial release. Simplified rewrite of AweAgent without agent framework dependency.

### Highlights

- Pure Python + LiteLLM — no Agno or other agent framework
- 4-step pipeline: search, annotate, filter, report
- Semantic Scholar integration with SQLite deduplication
- Incremental merge for maintaining curated Awesome lists
- README table generation and RSS feed from archive JSON
- Multi-provider LLM support via LiteLLM (OpenAI, DeepSeek, Gemini, Mistral)
- Config via JSON file with `${ENV_VAR}` expansion or direct environment variables
