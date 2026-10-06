"""Port of agentx-cli snapshot-validate.test.ts."""

import copy

from awescholar.agentx import validate

# Inline copy of agentx-cli/test/fixtures/demo-repo/data/agents-snapshot.json.
FIXTURE = {
    "agents": [
        {
            "slug": "alpha-agent",
            "name": "Alpha Agent",
            "repo": "example/alpha-agent",
            "githubUrl": "https://github.com/example/alpha-agent",
            "homepage": None,
            "paper": "https://doi.org/10.1038/s41586-026-00000-0",
            "paperMeta": {
                "title": "Alpha Agent: an autonomous assistant for biology research",
                "venue": "Nature",
                "doi": "10.1038/s41586-026-00000-0",
                "year": "2026.03",
                "authors": "A. Researcher, B. Author",
                "firstAuthor": "A. Researcher",
                "paperUrl": "https://doi.org/10.1038/s41586-026-00000-0",
                "citations": 4,
            },
            "category": "bio-omics",
            "tags": ["Stanford", "Nature"],
            "language": "Python",
            "stars": 42,
            "pushedAt": "2026-09-01T00:00:00Z",
            "openIssues": 2,
            "license": "MIT",
            "description": "An autonomous assistant for biology research.",
            "status": "active",
            "source": "manual",
            "sourceUrl": None,
        },
        {
            "slug": "beta-agent",
            "name": "Beta Agent",
            "repo": "example/beta-agent",
            "githubUrl": "https://github.com/example/beta-agent",
            "homepage": "https://beta.example.org",
            "paper": None,
            "category": "chem-drug",
            "tags": ["MCP"],
            "language": "TypeScript",
            "stars": 7,
            "pushedAt": "2026-08-15T00:00:00Z",
            "openIssues": 0,
            "license": None,
            "description": "MCP server for molecular workflows.",
            "status": "active",
            "source": "curated",
            "sourceUrl": None,
        },
    ],
    "counts": {"total": 2, "gone": 0},
}


def _fixture() -> dict:
    return copy.deepcopy(FIXTURE)


def test_accepts_the_fixture():
    assert validate.validate_snapshot_file(_fixture()) == []


def test_accepts_optional_listed_at_curation_date():
    fixture = _fixture()
    fixture["agents"][0]["listedAt"] = "2026-09-19"
    assert validate.validate_snapshot_file(fixture) == []


def test_rejects_malformed_listed_at():
    fixture = _fixture()
    fixture["agents"][0]["listedAt"] = "19.09.2026"
    problems = validate.validate_snapshot_file(fixture)
    assert any("listedAt" in p for p in problems)


def test_accepts_optional_generated_at_stamp():
    fixture = _fixture()
    fixture["generatedAt"] = "2026-10-01T02:00:00Z"
    assert validate.validate_snapshot_file(fixture) == []


def test_rejects_malformed_generated_at_stamp():
    fixture = _fixture()
    fixture["generatedAt"] = "yesterday"
    assert validate.validate_snapshot_file(fixture) == [
        "generatedAt is 'yesterday' — expected an ISO-8601 timestamp",
    ]


def test_rejects_non_objects_and_missing_agents_arrays():
    assert validate.validate_snapshot_file(None) == ["top level is not an object"]
    assert validate.validate_snapshot_file({"counts": {}}) == ["agents is not an array"]
    assert validate.validate_snapshot_file({"agents": []}) == ["counts is not an object"]


def test_checks_counts_total_against_the_agents_list():
    file = _fixture()
    file["counts"]["total"] = 99
    assert validate.validate_snapshot_file(file) == [
        "counts.total is 99, but agents has 2 entries",
    ]


def test_rejects_unknown_categories():
    file = _fixture()
    file["agents"][0]["category"] = "wat"
    assert validate.validate_snapshot_file(file) == [
        'agents[0] (alpha-agent): unknown category "wat"',
    ]


def test_enforces_the_tag_policy_and_the_registry():
    file = _fixture()
    file["agents"][0]["tags"] = ["multi-agent", "Not-Registered"]
    problems = validate.validate_snapshot_file(file)
    assert len(problems) == 3
    assert "multi-agent — generic descriptor" in problems[0]
    assert "unregistered tag(s) multi-agent, Not-Registered" in problems[1]
    assert "paperMeta.venue maps to venue tag Nature" in problems[2]


def test_requires_canonical_github_url():
    file = _fixture()
    file["agents"][0]["githubUrl"] = "https://github.com/someone/else"
    assert validate.validate_snapshot_file(file) == [
        (
            "agents[0] (alpha-agent): githubUrl must be null or"
            ' "https://github.com/example/alpha-agent", got "https://github.com/someone/else"'
        ),
    ]


def test_requires_stable_slug_order():
    file = _fixture()
    file["agents"] = list(reversed(file["agents"]))
    assert validate.validate_snapshot_file(file) == [
        "agents are not in stable slug order (writeSnapshot sorts by slug codepoint order)",
    ]


def test_keeps_graveyard_metadata_on_graveyard_records_only():
    file = _fixture()
    file["agents"][0]["retiredReason"] = "idle"
    assert validate.validate_snapshot_file(file) == [
        (
            'agents[0] (alpha-agent): retiredReason set while status is "active"'
            " — only graveyard records carry it"
        ),
    ]


def test_allows_null_citations_for_unindexed_papers():
    file = _fixture()
    file["agents"][0]["paperMeta"]["citations"] = None
    assert validate.validate_snapshot_file(file) == []


def test_requires_registered_paper_venue_tag():
    file = _fixture()
    file["agents"][0]["tags"] = ["Stanford"]
    assert validate.validate_snapshot_file(file) == [
        (
            "agents[0] (alpha-agent): paperMeta.venue maps to venue tag Nature "
            "but tags does not contain it — run `updater backfill --agentx "
            "--fields venue-tags`"
        ),
    ]


def test_unknown_paper_venue_does_not_require_a_tag():
    file = _fixture()
    file["agents"][0]["tags"] = ["Stanford"]
    file["agents"][0]["paperMeta"]["venue"] = "Nvidia's blog"
    assert validate.validate_snapshot_file(file) == []


def test_rejects_booleans_where_numbers_are_required():
    # isinstance(True, int) is True in Python; TS typeof true !== "number".
    file = _fixture()
    file["agents"][0]["stars"] = True
    problems = validate.validate_snapshot_file(file)
    assert problems == [
        "agents[0] (alpha-agent): stars must be a non-negative integer, got True",
    ]


def test_accepts_auto_venue_slug_tag_and_flags_missing_one():
    file = _fixture()
    file["agents"][0]["paperMeta"]["venue"] = "npj Health Systems"
    file["agents"][0]["tags"] = ["Stanford", "npj-Health-Systems"]
    assert validate.validate_snapshot_file(file) == []

    file = _fixture()
    file["agents"][0]["paperMeta"]["venue"] = "npj Health Systems"
    file["agents"][0]["tags"] = ["Stanford"]
    problems = validate.validate_snapshot_file(file)
    assert len(problems) == 1
    assert "maps to venue tag npj-Health-Systems" in problems[0]


def test_non_venue_source_needs_no_tag():
    file = _fixture()
    file["agents"][0]["paperMeta"]["venue"] = "Nvidia's blog"
    file["agents"][0]["tags"] = ["Stanford"]
    assert validate.validate_snapshot_file(file) == []
