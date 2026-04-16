"""Tests for skill frontmatter parsing."""

from pathlib import Path

from weavbot.agent.skills import SkillsLoader


def _write_skill(workspace: Path, name: str, frontmatter: str, body: str = "") -> None:
    d = workspace / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")


class TestGetSkillMetadata:
    def test_basic_frontmatter(self, tmp_path):
        _write_skill(tmp_path, "demo", "name: demo\ndescription: A demo skill.")
        loader = SkillsLoader(tmp_path)
        meta = loader.get_skill_metadata("demo")
        assert meta == {"name": "demo", "description": "A demo skill."}

    def test_boolean_always(self, tmp_path):
        _write_skill(
            tmp_path, "always-on", "name: always-on\ndescription: Always active\nalways: true"
        )
        loader = SkillsLoader(tmp_path)
        meta = loader.get_skill_metadata("always-on")
        assert meta is not None
        assert meta["always"] is True

    def test_quoted_description(self, tmp_path):
        _write_skill(
            tmp_path, "quoted", "name: quoted\ndescription: \"A skill with 'quotes' and: colons\""
        )
        loader = SkillsLoader(tmp_path)
        meta = loader.get_skill_metadata("quoted")
        assert meta is not None
        assert meta["description"] == "A skill with 'quotes' and: colons"

    def test_single_quoted_description(self, tmp_path):
        _write_skill(tmp_path, "sq", "name: sq\ndescription: 'contains \"double\" quotes'")
        loader = SkillsLoader(tmp_path)
        meta = loader.get_skill_metadata("sq")
        assert meta is not None
        assert meta["description"] == 'contains "double" quotes'

    def test_skips_blank_and_comment_lines(self, tmp_path):
        _write_skill(
            tmp_path,
            "comments",
            "name: comments\n\n# a comment\ndescription: has comments",
        )
        loader = SkillsLoader(tmp_path)
        meta = loader.get_skill_metadata("comments")
        assert meta == {"name": "comments", "description": "has comments"}

    def test_no_frontmatter(self, tmp_path):
        d = tmp_path / "skills" / "bare"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("# No frontmatter\n\nJust content.\n", encoding="utf-8")
        loader = SkillsLoader(tmp_path)
        assert loader.get_skill_metadata("bare") is None

    def test_value_with_colons(self, tmp_path):
        _write_skill(tmp_path, "colons", "name: colons\ndescription: http://example.com:8080/path")
        loader = SkillsLoader(tmp_path)
        meta = loader.get_skill_metadata("colons")
        assert meta is not None
        assert meta["description"] == "http://example.com:8080/path"

    def test_missing_skill(self, tmp_path):
        loader = SkillsLoader(tmp_path)
        assert loader.get_skill_metadata("nonexistent") is None

    def test_empty_frontmatter(self, tmp_path):
        _write_skill(tmp_path, "empty", "")
        loader = SkillsLoader(tmp_path)
        assert loader.get_skill_metadata("empty") is None

    def test_multiline_value(self, tmp_path):
        _write_skill(
            tmp_path,
            "multi",
            "name: multi\ndescription: |\n  Line one.\n  Line two.",
        )
        loader = SkillsLoader(tmp_path)
        meta = loader.get_skill_metadata("multi")
        assert meta is not None
        assert "Line one." in meta["description"]
        assert "Line two." in meta["description"]

    def test_integer_value(self, tmp_path):
        _write_skill(tmp_path, "intval", "name: intval\ndescription: test\nversion: 2")
        loader = SkillsLoader(tmp_path)
        meta = loader.get_skill_metadata("intval")
        assert meta is not None
        assert meta["version"] == 2

    def test_flow_sequence_value(self, tmp_path):
        _write_skill(tmp_path, "seq", "name: seq\ndescription: test\ntags: [a, b, c]")
        loader = SkillsLoader(tmp_path)
        meta = loader.get_skill_metadata("seq")
        assert meta is not None
        assert meta["tags"] == ["a", "b", "c"]

    def test_invalid_yaml_returns_none(self, tmp_path):
        _write_skill(tmp_path, "bad", "name: [invalid: {broken")
        loader = SkillsLoader(tmp_path)
        assert loader.get_skill_metadata("bad") is None

    def test_null_values(self, tmp_path):
        _write_skill(tmp_path, "nulls", "name: nulls\ndescription: desc\nalways:")
        loader = SkillsLoader(tmp_path)
        meta = loader.get_skill_metadata("nulls")
        assert meta is not None
        assert meta["always"] is None


class TestAlwaysSkills:
    def test_always_true(self, tmp_path):
        _write_skill(
            tmp_path, "always-skill", "name: always-skill\ndescription: test\nalways: true"
        )
        loader = SkillsLoader(tmp_path)
        assert "always-skill" in loader.get_always_skills()

    def test_always_false(self, tmp_path):
        _write_skill(tmp_path, "not-always", "name: not-always\ndescription: test\nalways: false")
        loader = SkillsLoader(tmp_path)
        assert "not-always" not in loader.get_always_skills()

    def test_always_absent(self, tmp_path):
        _write_skill(tmp_path, "no-always", "name: no-always\ndescription: test")
        loader = SkillsLoader(tmp_path)
        assert "no-always" not in loader.get_always_skills()


class TestLoadSkillsForContext:
    def test_excludes_frontmatter(self, tmp_path):
        _write_skill(tmp_path, "ctx", "name: ctx\ndescription: test", "Body content here.")
        loader = SkillsLoader(tmp_path)
        result = loader.load_skills_for_context(["ctx"])
        assert "Body content here." in result
        assert "name: ctx" not in result

    def test_missing_skill_skipped(self, tmp_path):
        loader = SkillsLoader(tmp_path)
        assert loader.load_skills_for_context(["nonexistent"]) == ""
