"""Tests for agentx/intake.py — ports of add-from-json.test.ts plus single-add
happy path, already-registered error, and 404 error.
"""

import json
from datetime import UTC, datetime

import pytest

from awescholar.agentx import intake
from awescholar.agentx.snapshot import read_snapshot

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURE_SNAPSHOT = {
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


def _write_snapshot(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _gh(*, full_name, **overrides):
    base = {
        "full_name": full_name,
        "homepage": None,
        "language": "Python",
        "stargazers_count": 10,
        "pushed_at": "2026-09-01T00:00:00Z",
        "open_issues_count": 1,
        "archived": False,
        "license": None,
        "description": "Mock repo description",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# add_from_json tests
# ---------------------------------------------------------------------------

class TestAddFromJson:
    def test_skips_already_registered_and_adds_fresh(self, tmp_path, monkeypatch, capsys):
        snapshot_path = str(tmp_path / "agents-snapshot.json")
        _write_snapshot(snapshot_path, FIXTURE_SNAPSHOT)

        candidate_path = str(tmp_path / "candidates.json")
        with open(candidate_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "agents": [
                        {
                            "repo": "example/gamma-agent",
                            "category": "bio-omics",
                            "name": "Gamma Agent",
                            "tags": [],
                            "source": "awescholar",
                            "sourceUrl": "https://example.org",
                        },
                        {
                            "repo": "example/alpha-agent",
                            "category": "bio-omics",
                            "tags": [],
                        },
                    ],
                    "counts": {"total": 2, "gone": 0},
                },
                f,
            )

        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (_gh(full_name="example/gamma-agent"), False),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        count = intake.add_from_json(snapshot_path, candidate_path)
        assert count == 1

        data = read_snapshot(snapshot_path)
        assert len(data["agents"]) == 3
        gamma = next(a for a in data["agents"] if a["repo"] == "example/gamma-agent")
        assert gamma["slug"] == "gamma-agent"
        assert gamma["source"] == "awescholar"
        assert gamma["sourceUrl"] == "https://example.org"
        assert gamma["description"] == "Mock repo description"

        out = capsys.readouterr().out
        assert "example/alpha-agent already in the snapshot, skipped" in out
        assert "Added 1 agent" in out

    def test_accepts_bare_top_level_array(self, tmp_path, monkeypatch):
        snapshot_path = str(tmp_path / "agents-snapshot.json")
        _write_snapshot(snapshot_path, FIXTURE_SNAPSHOT)

        candidate_path = str(tmp_path / "bare.json")
        with open(candidate_path, "w", encoding="utf-8") as f:
            json.dump(
                [{"repo": "example/delta-agent", "category": "chem-drug", "tags": []}],
                f,
            )

        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (_gh(full_name="example/delta-agent"), False),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        count = intake.add_from_json(snapshot_path, candidate_path)
        assert count == 1
        assert "delta-agent" in {
            a["slug"] for a in read_snapshot(snapshot_path)["agents"]
        }

    def test_all_or_nothing_leaves_snapshot_untouched(self, tmp_path, monkeypatch):
        snapshot_path = str(tmp_path / "agents-snapshot.json")
        _write_snapshot(snapshot_path, FIXTURE_SNAPSHOT)
        with open(snapshot_path, encoding="utf-8") as f:
            before = f.read()

        candidate_path = str(tmp_path / "bad.json")
        with open(candidate_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "agents": [
                        {"repo": "example/gamma-agent", "category": "bio-omics", "tags": []},
                        {"repo": "example/epsilon-agent", "category": "not-a-slug", "tags": []},
                    ]
                },
                f,
            )

        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (_gh(full_name=repo), False),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        with pytest.raises(intake.IntakeError, match="not-a-slug"):
            intake.add_from_json(snapshot_path, candidate_path)

        with open(snapshot_path, encoding="utf-8") as f:
            assert f.read() == before

    def test_rejects_malformed_or_empty_candidate_files(self, tmp_path):
        snapshot_path = str(tmp_path / "agents-snapshot.json")
        _write_snapshot(snapshot_path, FIXTURE_SNAPSHOT)

        bad = str(tmp_path / "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write('{"agents": []}')
        with pytest.raises(intake.IntakeError, match="contains no candidate agents"):
            intake.add_from_json(snapshot_path, bad)

        with open(bad, "w", encoding="utf-8") as f:
            f.write('{"unexpected": 1}')
        with pytest.raises(intake.IntakeError, match=r"expected \{\"agents\": \[\.\.\.\]\}"):
            intake.add_from_json(snapshot_path, bad)

    def test_nothing_new_prints_and_returns_zero(self, tmp_path, capsys):
        snapshot_path = str(tmp_path / "agents-snapshot.json")
        _write_snapshot(snapshot_path, FIXTURE_SNAPSHOT)

        candidate_path = str(tmp_path / "c4.json")
        with open(candidate_path, "w", encoding="utf-8") as f:
            json.dump(
                {"agents": [{"repo": "example/beta-agent", "category": "chem-drug", "tags": []}]},
                f,
            )

        count = intake.add_from_json(snapshot_path, candidate_path)
        assert count == 0
        assert len(read_snapshot(snapshot_path)["agents"]) == 2

        out = capsys.readouterr().out
        assert "Nothing new" in out


# ---------------------------------------------------------------------------
# add_agent tests
# ---------------------------------------------------------------------------

class TestAddAgent:
    def test_happy_path(self, tmp_path, monkeypatch, capsys):
        snapshot_path = str(tmp_path / "agents-snapshot.json")
        _write_snapshot(snapshot_path, FIXTURE_SNAPSHOT)

        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (_gh(full_name="example/gamma-agent"), False),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        agent = intake.add_agent(
            snapshot_path,
            "example/gamma-agent",
            category="bio-omics",
            name="Gamma Agent",
            tags=["Stanford"],
            paper="https://doi.org/10.1",
            description="Test description",
        )

        assert agent["slug"] == "gamma-agent"
        assert agent["repo"] == "example/gamma-agent"
        assert agent["source"] == "manual"
        assert agent["sourceUrl"] is None
        assert len(read_snapshot(snapshot_path)["agents"]) == 3

        out = capsys.readouterr().out
        assert "Added gamma-agent (example/gamma-agent) → category bio-omics" in out
        assert "tags: Stanford" in out

    def test_already_registered_raises(self, tmp_path):
        snapshot_path = str(tmp_path / "agents-snapshot.json")
        _write_snapshot(snapshot_path, FIXTURE_SNAPSHOT)

        with pytest.raises(intake.IntakeError, match="already in the snapshot"):
            intake.add_agent(
                snapshot_path,
                "example/alpha-agent",
                category="bio-omics",
            )

    def test_404_raises(self, tmp_path, monkeypatch):
        snapshot_path = str(tmp_path / "agents-snapshot.json")
        _write_snapshot(snapshot_path, FIXTURE_SNAPSHOT)

        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (None, True),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        with pytest.raises(intake.IntakeError, match=r"not found on GitHub \(404\)"):
            intake.add_agent(
                snapshot_path,
                "example/ghost-agent",
                category="bio-omics",
            )


# ---------------------------------------------------------------------------
# _agent_from_intake validation tests
# ---------------------------------------------------------------------------

class TestAgentFromIntake:
    def test_invalid_repo_format(self):
        with pytest.raises(intake.IntakeError, match="Not an owner/repo pair"):
            intake._agent_from_intake(
                {"repo": "bad-format", "category": "bio-omics", "tags": []},
                set(),
                None,
            )

    def test_unknown_category(self):
        with pytest.raises(intake.IntakeError, match="Unknown category"):
            intake._agent_from_intake(
                {"repo": "x/y", "category": "not-a-slug", "tags": []},
                set(),
                None,
            )

    def test_tag_policy_violation(self):
        with pytest.raises(intake.IntakeError, match="Tag policy violations"):
            intake._agent_from_intake(
                {"repo": "x/y", "category": "bio-omics", "tags": ["multi-agent"]},
                set(),
                None,
            )

    def test_unregistered_tag(self):
        with pytest.raises(intake.IntakeError, match="Unregistered tags"):
            intake._agent_from_intake(
                {"repo": "x/y", "category": "bio-omics", "tags": ["not-a-tag"]},
                set(),
                None,
            )

    def test_fetch_network_failure(self, monkeypatch):
        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (None, False),
        )
        with pytest.raises(intake.IntakeError, match="Could not fetch"):
            intake._agent_from_intake(
                {"repo": "x/y", "category": "bio-omics", "tags": []},
                set(),
                None,
            )

    def test_happy_path_builds_agent(self, monkeypatch):
        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (_gh(full_name="x/y"), False),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        agent = intake._agent_from_intake(
            {"repo": "x/y", "category": "bio-omics", "name": "Y Agent", "tags": ["Stanford"]},
            set(),
            None,
        )
        assert agent["slug"] == "y-agent"
        assert agent["repo"] == "x/y"
        assert agent["githubUrl"] == "https://github.com/x/y"
        assert agent["category"] == "bio-omics"
        assert agent["tags"] == ["Stanford"]
        assert agent["source"] == "manual"
        assert agent["sourceUrl"] is None
        # Curation date is stamped at intake, date-only UTC.
        assert agent["listedAt"] == datetime.now(tz=UTC).date().isoformat()

    def test_rec_fields_override_github(self, monkeypatch):
        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (
                _gh(
                    full_name="x/y",
                    description="GH desc",
                    homepage="https://gh.example",
                    stargazers_count=0,
                    pushed_at="2026-01-01T00:00:00Z",
                ),
                False,
            ),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        agent = intake._agent_from_intake(
            {
                "repo": "x/y",
                "category": "bio-omics",
                "name": "Y Agent",
                "tags": [],
                "homepage": "https://rec.example",
                "description": "Rec desc",
                "source": "awescholar",
                "sourceUrl": "https://example.org",
            },
            set(),
            None,
        )
        assert agent["homepage"] == "https://rec.example"
        assert agent["description"] == "Rec desc"
        assert agent["source"] == "awescholar"
        assert agent["sourceUrl"] == "https://example.org"

    def test_github_homepage_when_rec_none(self, monkeypatch):
        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (
                _gh(full_name="x/y", homepage="https://gh.example"),
                False,
            ),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        agent = intake._agent_from_intake(
            {"repo": "x/y", "category": "bio-omics", "tags": []},
            set(),
            None,
        )
        assert agent["homepage"] == "https://gh.example"

    def test_none_coalesce_preserves_falsy_github_values(self, monkeypatch):
        """stars=0 and empty description from GitHub must survive."""
        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (
                _gh(full_name="x/y", stargazers_count=0, description=""),
                False,
            ),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        agent = intake._agent_from_intake(
            {"repo": "x/y", "category": "bio-omics", "tags": []},
            set(),
            None,
        )
        assert agent["stars"] == 0
        assert agent["description"] == ""

    def test_rec_empty_string_homepage_falls_through_to_github(self, monkeypatch):
        """Empty string homepage should be treated as absent and fall through."""
        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (
                _gh(full_name="x/y", homepage="https://gh.example"),
                False,
            ),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        agent = intake._agent_from_intake(
            {"repo": "x/y", "category": "bio-omics", "homepage": "", "tags": []},
            set(),
            None,
        )
        assert agent["homepage"] == "https://gh.example"

    def test_slug_collision_suffixes(self, monkeypatch):
        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (_gh(full_name="x/y"), False),
        )
        monkeypatch.setattr(intake, "resolve_repo_license", lambda *a, **kw: None)

        agent1 = intake._agent_from_intake(
            {"repo": "x/y", "category": "bio-omics", "name": "Y Agent", "tags": []},
            {"y-agent"},
            None,
        )
        assert agent1["slug"] == "y-agent-2"

    def test_auto_venue_slug_tag_is_accepted(self, monkeypatch):
        """An unregistered tag that is the auto slug of the record's own
        venue passes the registry gate (it fails later at the fetch)."""
        monkeypatch.setattr(
            intake,
            "fetch_repo_ex",
            lambda repo, token: (None, False),
        )
        with pytest.raises(intake.IntakeError, match="Could not fetch"):
            intake._agent_from_intake(
                {
                    "repo": "x/y",
                    "category": "bio-omics",
                    "tags": ["Cancer-Research"],
                    "paperMeta": {"venue": "Cancer Research"},
                },
                set(),
                None,
            )
