# Contributing

## Development Setup

```bash
git clone https://github.com/wehuman01/awescholar.git
cd awescholar
pip install -e ".[dev]"
pytest
```

Requires Python >= 3.11.

## Project Structure

```
src/awescholar/
  __init__.py       # Version
  cli.py            # CLI wiring, config loading, argument parsing
  config.py         # Config loading and ${VAR} expansion
  pipeline.py       # Step orchestration: search -> annotate -> filter -> report
  search.py         # Semantic Scholar API client
  llm.py            # LiteLLM completion wrapper
  prompts.py        # System prompt strings
  schemas.py        # Pydantic models for annotation and filtering
  categories.py     # Category normalization and matching
  data_fields.py    # Data field definitions
  record.py         # Record construction and helpers
  db.py             # SQLAlchemy ORM (Paper model) and session factory
  utils.py          # Re-export facade (imports from archive, readme, rss)
  archive.py        # Archive merge operations (new2old, old2new)
  backup.py         # Timestamped archive backups; skips git-clean files
  months.py         # --month / --period date and output-dir derivation
  readme.py         # README generation and update
  rss.py            # RSS feed generation
  digest.py         # Monthly digest rendering from the archive
  github.py         # GitHub REST access (repo search, metrics, URL parsing)
  enrich.py         # Paper -> official GitHub repo resolution and stars refresh
  publish_scan.py   # Preprint -> published-version scan and in-place upgrade
  reader.py         # Offline query/related/recommend/stats over the archive
  scaffold.py       # awescholar init repository scaffolding
  agentx_export.py  # Export repo-backed papers as AgentX candidate agents
tests/
  test_cli.py       # CLI argument parsing and config tests
  test_config.py    # Config expansion tests
  test_db.py        # DB and Paper model tests
  test_pipeline.py  # Pipeline orchestration tests
  test_record.py    # Record construction tests
  test_schemas.py   # Pydantic schema tests
  test_utils.py     # Merge, README, RSS utility tests
```

Separation: `cli.py` handles I/O and config. `pipeline.py` orchestrates steps. Other modules handle domain logic.

## Architecture

**4-step pipeline** — each step takes input and returns output. Search writes to SQLite; Annotate, Filter, and Report call LLMs. The transformation logic within each step is functional, but the steps themselves have side effects (DB writes, API calls, file I/O):

1. **Search** — Query Semantic Scholar API, deduplicate against SQLite DB
2. **Annotate** — LLM classifies papers by domain and category
3. **Filter** — LLM selects top N papers by quality and relevance
4. **Report** — LLM generates a Markdown summary

Steps are composable. Run the full pipeline with `awescholar crawler run` or individual steps.

**Data flow**: Each step reads/writes JSON files (`updater.json`, `updater_filter.json`, `report.md`). Re-run any step independently.

**Merge model**: `updater update --direction new2old` merges new results into a persistent project data JSON. Category names are matched case-insensitively and separator-insensitively, so `AI Agents`, `ai-agents`, and `ai agents` resolve to the existing category key instead of creating duplicate sections. `old2new` enriches new results with project data entries.

**README update model**: `render readme` only replaces content between `<!-- AWESCHOLAR:START -->` and `<!-- AWESCHOLAR:END -->`. The generated region contains the awescholar table of contents and category tables. Hand-written headers, citations, and other project text must live outside that generated region. Existing README files without markers fail fast instead of being overwritten.

## Data Model

`Paper` (SQLAlchemy) — stores raw search results with deduplication by `paper_id`.

`PaperAnnotation` / `FilteredPaper` (Pydantic) — structured LLM output for annotation and filtering stages.

## Config

Config uses `${ENV_VAR}` expansion. Sensitive values (API keys) must use `${VAR}` syntax in `config.example.json`, never hardcoded. The CLI resolves these from environment variables at load time.

Top-level keys: `model_profiles`, `model`, `agent_models`, `semantic_scholar`, `github`, `search`, `filter`, `output`, `pipeline`, `categories`.

**`model_profiles`**: reusable profile map — each profile defines `api_key`, `base_url`, and optionally `temperature`. Referenced by `model.profile` or `agent_models.*.profile`.

**`model.name`**: just the model name (e.g. `glm-5.1`). The `openai/` prefix is auto-prepended by `_prefix_model()`.

**`temperature`**: sampling temperature for LLM calls, default `0.0`. Precedence: `model_profiles.<p>.temperature` > `model.temperature` / `agent_models.<agent>.temperature` > default. Exists for endpoints that only accept one value (kimi coding API requires `1`).

**`agent_models`**: per-agent model overrides for annotator, filterer, reporter. Each entry can use `profile` to reference `model_profiles`. Falls back to global `model` config if not set.

**`filter.research_interests`**: optional string for relevance weighting during filtering.

**`pipeline`**: flow control flags — `skip_search`, `use_updater_json`, `use_filtered_json`, `existing_json_path`, `merge_new_to_old`, `data_json_path`. Allows reusing intermediate JSON files to skip pipeline steps and optionally merge filtered results into the project data JSON.

**`search.query`**: if set, `crawler run` can omit the CLI query argument.

## Engineering Taste

Prefer solutions that are simple, clear, decoupled, honest, focused, and durable.

- Simple: make the smallest change that solves the real problem.
- Clear: optimize for the next reader, not for cleverness.
- Decoupled: keep boundaries clean, but do not add abstractions without a real need.
- Honest: make complexity, state, side effects, assumptions, and failure modes visible; do not hide complexity or create extra complexity.
- Focused: preserve boundaries between modules, and keep top-level convenience commands minimal.
- Durable: choose behavior that is easy to maintain, test, and extend.
- First principles: identify the real problem, hard constraints, and known facts before reaching for patterns, abstractions, or prior solutions.

## Code Style

- Functional over OOP — no classes except SQLAlchemy models and Pydantic schemas
- Pure transformation logic (category normalization, field normalization, JSON merge) is separated from side-effectful orchestration (DB writes, LLM calls, file I/O)
- Error messages are user-facing and actionable
- Imports: stdlib first, blank line, then third-party

## Testing

```bash
pytest
```

One test file per source module. Tests use real SQLite databases (in-memory or temp files), no filesystem mocking.

## Branch Model

- `main` — stable, always deployable
- Feature branches: `feat/short-description`
- Fix branches: `fix/short-description`

## Release Workflow

1. Update `docs/CHANGELOG.md` with version notes
2. Update version in `pyproject.toml` and `src/awescholar/__init__.py`
3. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
4. CI creates GitHub Release and publishes to PyPI

## Pull Requests

- One logical change per PR
- Include tests for new functionality
- Update docs if behavior changes
- Reference related issues
