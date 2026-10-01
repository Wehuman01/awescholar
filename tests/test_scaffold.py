"""Tests for the repository scaffolding (awescholar init) and README count refresh."""

import json
import os
import tempfile

from awescholar.readme import update_readme_counts
from awescholar.scaffold import DEFAULT_CATEGORIES, run_init, slugify


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _init(tmp: str, **kwargs) -> str:
    run_init(target_dir=tmp, **kwargs)
    return tmp


def test_init_creates_default_file_set_and_content():
    with tempfile.TemporaryDirectory() as tmp:
        run_init(target_dir=tmp)
        for rel in [
            "readme.md", "README.zh-CN.md", "CONTRIBUTING.md", "LICENSE", ".gitignore",
            "config.json", "docs/index.html", "docs/data.json", "docs/rss.xml", "docs/CNAME",
            "assets/images/wechat-pay.jpg",
        ]:
            assert os.path.exists(os.path.join(tmp, rel)), f"missing {rel}"

        data = json.loads(_read(os.path.join(tmp, "docs", "data.json")))
        assert list(data) == DEFAULT_CATEGORIES
        assert all(papers == [] for papers in data.values())

        config = json.loads(_read(os.path.join(tmp, "config.json")))
        assert config["categories"] == DEFAULT_CATEGORIES
        assert config["pipeline"]["data_json_path"] == "docs/data.json"

        readme = _read(os.path.join(tmp, "readme.md"))
        assert "Awesome AI Meets Biology" in readme
        assert "## 🌐 Browse the Collection" in readme
        for category in DEFAULT_CATEGORIES:
            assert f"[{category}](http://awesomebio.webioinfo.top/#{slugify(category)})" in readme
        assert "papers-0-" in readme

        site = _read(os.path.join(tmp, "docs", "index.html"))
        for category in DEFAULT_CATEGORIES:
            assert f'id="{slugify(category)}-tbody"' in site
            assert f'data-section="{slugify(category)}"' in site
        assert "{{" not in site and "{{" not in readme


def test_init_vt_template_renders_category_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        run_init(
            target_dir=tmp, template="vt",
            title="Awesome Test", github_repo="someone/Awesome-Test",
            website="http://test.example.com/",
            categories=["Static Models", "Dynamic Models"],
        )
        site = _read(os.path.join(tmp, "docs", "index.html"))
        assert "'static-models': { icon: 'fa-cube', name: 'Static Models' }," in site
        assert "'dynamic-models': { icon: 'fa-wave-square', name: 'Dynamic Models' }," in site
        assert "function categoryToSectionId" in site
        assert "{{" not in site


def test_init_custom_identity_propagates():
    with tempfile.TemporaryDirectory() as tmp:
        run_init(
            target_dir=tmp, title="Awesome AI Foo",
            subtitle="A curated survey of foo",
            github_repo="someone/Awesome-AI-Foo", website="http://foo.example.com/",
            categories=["Alpha Widgets", "Beta Widgets"],
        )
        readme = _read(os.path.join(tmp, "readme.md"))
        assert "<h1>Awesome AI Foo " in readme
        assert "someone/Awesome-AI-Foo" in readme
        assert '"Alpha Widgets", "Beta Widgets"' in readme.replace(" and ", ", ")
        site = _read(os.path.join(tmp, "docs", "index.html"))
        assert 'id="alpha-widgets-tbody"' in site
        assert "Awesome AI Foo" in site


def test_init_refuses_non_empty_directory_without_force():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "existing.txt"), "w") as f:
            f.write("x")
        try:
            run_init(target_dir=tmp)
            raise AssertionError("expected FileExistsError")
        except FileExistsError:
            pass
        run_init(target_dir=tmp, force=True)
        assert os.path.exists(os.path.join(tmp, "readme.md"))


def test_init_no_zh_and_no_branding():
    with tempfile.TemporaryDirectory() as tmp:
        run_init(target_dir=tmp, include_zh=False, branding=False)
        assert not os.path.exists(os.path.join(tmp, "README.zh-CN.md"))
        assert not os.path.exists(os.path.join(tmp, "assets"))
        readme = _read(os.path.join(tmp, "readme.md"))
        assert "Awesome Ecosystem" not in readme
        assert "we.webioinfo.top" not in readme
        assert "aweskill companion" not in readme


def test_init_tables_embeds_markers():
    with tempfile.TemporaryDirectory() as tmp:
        run_init(target_dir=tmp, embed_tables=True)
        readme = _read(os.path.join(tmp, "readme.md"))
        assert "<!-- AWESCHOLAR:START -->" in readme
        assert "<!-- AWESCHOLAR:END -->" in readme


def test_init_cname_only_for_custom_domain():
    with tempfile.TemporaryDirectory() as tmp:
        run_init(target_dir=tmp, website="http://custom.example.com/")
        assert _read(os.path.join(tmp, "docs", "CNAME")).strip() == "custom.example.com"
    with tempfile.TemporaryDirectory() as tmp:
        run_init(target_dir=tmp, website="https://someone.github.io/Awesome-Test/")
        assert not os.path.exists(os.path.join(tmp, "docs", "CNAME"))


def _write_archive(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def test_update_readme_counts_refreshes_all_formats():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {
            "AI Agents": [{"title": "p1"}, {"title": "p2"}],
            "Reviews": [{"title": "r1"}],
            "Foundation models": [],
        })
        readme = os.path.join(tmp, "readme.md")
        with open(readme, "w", encoding="utf-8") as f:
            f.write(
                "![papers-999](x)\n![categories-9](x)\n"
                "All 999 papers live on the website.\n"
                "- 🌟 [AI Agents](http://s.example/#ai-agents) — 999 papers\n"
                "- 🎯 [Foundation models](http://s.example/#foundation-models) — 999 papers\n"
                "- 📚 [Reviews](http://s.example/#reviews) — 999 papers. Long description kept.\n"
                "- 🌟 [AI Agents（智能体）](http://s.example/#ai-agents) — 999 篇\n"
                "Machine-readable data: docs/data.json — 999 entries with full metadata.\n"
            )
        update_readme_counts(archive_path=archive, readme_path=readme)
        content = _read(readme)
        assert "![papers-3]" in content       # 2 + 1 + 0
        assert "![categories-3]" in content
        assert "All 3 papers live on" in content
        assert "[AI Agents](http://s.example/#ai-agents) — 2 papers" in content
        assert "[Foundation models](http://s.example/#foundation-models) — 0 papers" in content
        assert "[Reviews](http://s.example/#reviews) — 1 paper. Long description kept." in content
        assert "— 2 篇" in content
        assert "— 3 entries" in content


def test_update_readme_counts_leaves_unknown_categories_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {"AI Agents": [{"title": "p1"}]})
        readme = os.path.join(tmp, "readme.md")
        with open(readme, "w", encoding="utf-8") as f:
            f.write("- 🌟 [Unknown Cat](http://s.example/#unknown-cat) — 57 papers\n")
        update_readme_counts(archive_path=archive, readme_path=readme)
        assert "— 57 papers" in _read(readme)


def test_update_readme_counts_matches_shorter_anchor_by_prefix():
    # the website section id ("#databases") is shorter than the category slug
    # ("databases-simulation") — the bullet must still refresh
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {"Databases/Simulation": [{"title": "d1"}, {"title": "d2"}]})
        readme = os.path.join(tmp, "readme.md")
        with open(readme, "w", encoding="utf-8") as f:
            f.write("- 💾 [Databases/Simulation](http://s.example/#databases) — 999 papers\n")
        update_readme_counts(archive_path=archive, readme_path=readme)
        assert "— 2 papers" in _read(readme)


def test_update_readme_counts_leaves_ambiguous_prefix_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {
            "Databases/Simulation": [{"title": "d1"}],
            "Databases/Other": [{"title": "d2"}],
        })
        readme = os.path.join(tmp, "readme.md")
        with open(readme, "w", encoding="utf-8") as f:
            f.write("- 💾 [Databases](http://s.example/#databases) — 57 papers\n")
        update_readme_counts(archive_path=archive, readme_path=readme)
        assert "— 57 papers" in _read(readme)
