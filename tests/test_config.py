"""Tests for CLI config loading."""

import json

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from pathlib import Path

import pytest

from awescholar import __version__
from awescholar.config import (
    load_config,
    resolve_agent_config,
    ss_env_api_key,
    warn_missing_ss_key,
)


def test_load_config_defaults_data_json_path_to_none(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    config = load_config(None)

    assert config["data_json_path"] is None


def test_load_config_reads_pipeline_data_json_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"pipeline": {"data_json_path": "data/data.json"}}),
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config["data_json_path"] == "data/data.json"


def test_load_config_fails_fast_for_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    missing_path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config(str(missing_path))


def test_ss_env_api_key_prefers_underscored_name(monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "key-with-underscore")
    monkeypatch.setenv("SEMANTICSCHOLAR_API_KEY", "key-without-underscore")

    assert ss_env_api_key() == "key-with-underscore"


def test_ss_env_api_key_falls_back_to_legacy_name(monkeypatch):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.setenv("SEMANTICSCHOLAR_API_KEY", "legacy-key")

    assert ss_env_api_key() == "legacy-key"


def test_ss_env_api_key_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTICSCHOLAR_API_KEY", raising=False)

    assert ss_env_api_key() is None


def test_load_config_reads_ss_api_key_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "env-key")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}), encoding="utf-8")

    config = load_config(str(config_path))

    assert config["ss_api_key"] == "env-key"


def test_load_config_config_value_beats_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "env-key")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"semantic_scholar": {"api_key": "config-key"}}),
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config["ss_api_key"] == "config-key"


def test_load_config_reads_ss_api_key_from_user_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTICSCHOLAR_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    user_dotenv = tmp_path / ".config" / "awescholar" / ".env"
    user_dotenv.parent.mkdir(parents=True)
    user_dotenv.write_text("SEMANTIC_SCHOLAR_API_KEY=user-key\n", encoding="utf-8")

    config = load_config(None)

    assert config["ss_api_key"] == "user-key"


def test_load_config_project_dotenv_beats_user_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTICSCHOLAR_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    (project_dir / ".env").write_text("SEMANTIC_SCHOLAR_API_KEY=project-key\n", encoding="utf-8")
    user_dotenv = tmp_path / "home" / ".config" / "awescholar" / ".env"
    user_dotenv.parent.mkdir(parents=True)
    user_dotenv.write_text("SEMANTIC_SCHOLAR_API_KEY=user-key\n", encoding="utf-8")

    config = load_config(None)

    assert config["ss_api_key"] == "project-key"


def test_load_config_environment_beats_dotenv_files(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "environment-key")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("SEMANTIC_SCHOLAR_API_KEY=project-key\n", encoding="utf-8")
    user_dotenv = tmp_path / ".config" / "awescholar" / ".env"
    user_dotenv.parent.mkdir(parents=True)
    user_dotenv.write_text("SEMANTIC_SCHOLAR_API_KEY=user-key\n", encoding="utf-8")

    config = load_config(None)

    assert config["ss_api_key"] == "environment-key"


def test_load_config_config_value_beats_dotenv_files(monkeypatch, tmp_path):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTICSCHOLAR_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    user_dotenv = tmp_path / ".config" / "awescholar" / ".env"
    user_dotenv.parent.mkdir(parents=True)
    user_dotenv.write_text("SEMANTIC_SCHOLAR_API_KEY=user-key\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"semantic_scholar": {"api_key": "config-key"}}),
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config["ss_api_key"] == "config-key"


def _write_global_config(home: Path, payload: dict) -> None:
    global_dir = home / ".config" / "awescholar"
    global_dir.mkdir(parents=True, exist_ok=True)
    (global_dir / "config.json").write_text(json.dumps(payload), encoding="utf-8")


def test_load_config_reads_global_config_without_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_global_config(
        tmp_path,
        {
            "model": {"profile": "glm", "name": "glm-5.3"},
            "model_profiles": {
                "glm": {"api_key": "global-glm-key", "base_url": "https://glm.example"}
            },
        },
    )

    config = load_config(None)

    assert config["model"] == "openai/glm-5.3"
    assert config["api_key"] == "global-glm-key"
    assert config["base_url"] == "https://glm.example"


def test_project_config_overrides_global_leaves(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_global_config(
        tmp_path,
        {
            "model": {"profile": "glm", "name": "glm-5.3"},
            "search": {"limit": 100},
        },
    )
    project = tmp_path / "config.json"
    project.write_text(
        json.dumps({"model": {"name": "glm-5.1"}, "categories": ["AI Agents"]}),
        encoding="utf-8",
    )

    config = load_config(str(project))

    assert config["model"] == "openai/glm-5.1"
    assert config["limit_search"] == 100
    assert config["categories"] == ["AI Agents"]


def test_model_profiles_merge_per_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_global_config(
        tmp_path,
        {
            "model_profiles": {
                "glm": {"api_key": "old-key", "base_url": "https://glm.example"},
                "gemini": {"api_key": "gemini-key", "base_url": "https://gemini.example"},
            }
        },
    )
    project = tmp_path / "config.json"
    project.write_text(
        json.dumps(
            {
                "model_profiles": {
                    "glm": {"api_key": "new-key"},
                    "mimo": {"api_key": "mimo-key"},
                },
                "model": {"profile": "glm"},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(str(project))

    assert config["model_profiles"]["glm"] == {
        "api_key": "new-key",
        "base_url": "https://glm.example",
    }
    assert config["model_profiles"]["gemini"]["api_key"] == "gemini-key"
    assert config["model_profiles"]["mimo"]["api_key"] == "mimo-key"
    assert config["api_key"] == "new-key"


def test_global_config_env_refs_expand(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GITHUB_TOKEN", "gh-from-env")
    _write_global_config(tmp_path, {"github": {"token": "${GITHUB_TOKEN}"}})

    config = load_config(None)

    assert config["github_token"] == "gh-from-env"


def test_resolve_agent_config_prefixes_agent_model_names():
    config = {
        "model": "openai/global-model",
        "api_key": "global-key",
        "base_url": "https://global.example",
        "model_profiles": {
            "glm": {
                "api_key": "profile-key",
                "base_url": "https://profile.example",
            }
        },
        "agent_models": {
            "reporter": {
                "profile": "glm",
                "name": "glm-5.1",
            }
        },
    }

    model, api_key, base_url, temperature = resolve_agent_config(config, "reporter")

    assert model == "openai/glm-5.1"
    assert api_key == "profile-key"
    assert base_url == "https://profile.example"
    assert temperature == 0.0


def test_resolve_agent_temperature_precedence():
    """Profile temperature wins, then agent-level, then the global fallback."""
    profiles = {"kimi": {"api_key": "k", "base_url": "https://k.example", "temperature": 1}}
    base = {"model": "openai/m", "api_key": "gk", "base_url": "https://g.example",
            "model_profiles": profiles}

    # Profile sets it -> 1 even when the global fallback is 0.0.
    _, _, _, temperature = resolve_agent_config(
        {**base, "agent_models": {"reporter": {"profile": "kimi", "name": "k3"}}}, "reporter")
    assert temperature == 1

    # Agent-level entry without a profile temperature -> agent value.
    _, _, _, temperature = resolve_agent_config(
        {**base, "agent_models": {"reporter": {"name": "m", "temperature": 0.7}}}, "reporter")
    assert temperature == 0.7

    # Nothing configured -> fallback.
    _, _, _, temperature = resolve_agent_config(
        {**base, "agent_models": {"reporter": {"name": "m"}}}, "reporter")
    assert temperature == 0.0

    # A profile temperature of 0.0 is honored, not treated as unset.
    _, _, _, temperature = resolve_agent_config(
        {**base, "model_profiles": {"cold": {"api_key": "k", "temperature": 0.0}},
         "agent_models": {"reporter": {"profile": "cold", "name": "m"}}}, "reporter")
    assert temperature == 0.0


def test_load_config_reads_model_temperature(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    global_dir = tmp_path / ".config" / "awescholar"
    global_dir.mkdir(parents=True)
    (global_dir / "config.json").write_text(json.dumps(
        {"model_profiles": {"kimi": {"api_key": "k", "base_url": "https://k.example",
                                      "temperature": 1}}}), encoding="utf-8")
    config_path = tmp_path / "project.json"
    config_path.write_text(json.dumps(
        {"model": {"profile": "kimi", "name": "kimi/k3"}}), encoding="utf-8")

    assert load_config(str(config_path))["temperature"] == 1

    config_path.write_text(json.dumps(
        {"model": {"profile": "kimi", "name": "kimi/k3", "temperature": 0.5}}),
        encoding="utf-8")
    # Profile still wins over the model-level value.
    assert load_config(str(config_path))["temperature"] == 1

    config_path.write_text(json.dumps(
        {"model": {"name": "glm-5.1", "temperature": 0.5}}), encoding="utf-8")
    assert load_config(str(config_path))["temperature"] == 0.5

    config_path.write_text(json.dumps({"model": {"name": "glm-5.1"}}), encoding="utf-8")
    assert load_config(str(config_path))["temperature"] == 0.0


def test_version_constant_matches_package_metadata():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    metadata = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert __version__ == metadata["project"]["version"]


def test_warn_missing_ss_key_writes_actionable_hint_to_stderr(capsys):
    warn_missing_ss_key()

    err = capsys.readouterr().err
    assert "no Semantic Scholar API key" in err
    assert "anonymous free tier" in err
    assert "SEMANTIC_SCHOLAR_API_KEY" in err


def test_load_config_defaults_stars_style_to_numeric(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    config = load_config(None)

    assert config["stars_style"] == "numeric"


def test_load_config_reads_archive_stars_style(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"archive": {"stars_style": "badge"}}),
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config["stars_style"] == "badge"


def test_load_config_reads_zotero_unpaywall_email(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"zotero": {"unpaywall_email": "peng@example.org"}}),
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config["zotero_unpaywall_email"] == "peng@example.org"
