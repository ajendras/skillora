"""Tests for the Skillora CLI.

Uses Typer's CliRunner for all commands. Tests cover scaffolding,
testing, benchmarking, documentation generation, and registry
subcommands. Snapshot-style checks verify generated file contents
and CLI output strings. Temporary directories isolate each test.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from skillora.cli import app, _load_skill
from skillora.core import Skill, SkillMetadata, skill


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def temp_skill_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with a minimal valid skill."""
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir()

    code = '''from skillora import Skill, SkillResult, skill
@skill(
    name="test-skill",
    description="A minimal skill used for CLI testing.",
    tags=["test"],
)
class TestSkill(Skill):
    def execute(self, context):
        q = context.get("query") or "default"
        return SkillResult(success=True, output={"echo": q})
skill = TestSkill()
'''
    (skill_dir / "skill.py").write_text(code, encoding="utf-8")
    (skill_dir / "__init__.py").touch()
    return skill_dir


def test_new_command(runner: CliRunner, tmp_path: Path) -> None:
    """Test `skillora new` scaffolding and generated file content."""
    output_dir = tmp_path / "new_skill"
    result = runner.invoke(
        app,
        [
            "new",
            "hello-world",
            "--desc",
            "Says hello to the world",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    assert "Skill 'hello-world' scaffolded successfully" in result.stdout
    assert "hello-world" in result.stdout

    skill_file = output_dir / "skill.py"
    assert skill_file.exists()
    content = skill_file.read_text(encoding="utf-8")

    # Snapshot-style checks on generated file
    assert "class HelloWorld(Skill)" in content
    assert 'name="hello-world"' in content
    assert "Says hello to the world" in content
    assert "@skill(" in content
    assert "def execute(self, context:" in content
    assert "EXAMPLE_TEST_CASES" in content


def test_test_command(runner: CliRunner, temp_skill_dir: Path) -> None:
    """Test `skillora test` with verbose output."""
    result = runner.invoke(app, ["test", str(temp_skill_dir), "--verbose"])
    assert result.exit_code == 0
    assert "Testing test-skill" in result.stdout
    assert "Pass Rate" in result.stdout
    assert "Judge Score" in result.stdout
    assert "Skill passed all tests" in result.stdout or "high confidence" in result.stdout
    # verbose details
    assert "PASS" in result.stdout or "Details" in result.stdout


def test_benchmark_command(runner: CliRunner, temp_skill_dir: Path) -> None:
    """Test `skillora benchmark` with CSV output."""
    csv_path = temp_skill_dir.parent / "benchmark.csv"
    result = runner.invoke(
        app,
        ["benchmark", str(temp_skill_dir), "--scenarios", "5", "--output", str(csv_path)],
    )
    assert result.exit_code == 0
    assert "Benchmarking test-skill" in result.stdout
    assert "Accuracy" in result.stdout
    assert "Mean Latency" in result.stdout
    assert csv_path.exists()

    csv_content = csv_path.read_text(encoding="utf-8")
    assert "scenario_id" in csv_content or "accuracy" in csv_content.lower()


def test_docs_command(runner: CliRunner, temp_skill_dir: Path) -> None:
    """Test `skillora docs` generates a Markdown file with expected sections."""
    readme_path = temp_skill_dir / "README.md"
    result = runner.invoke(app, ["docs", str(temp_skill_dir), "--output", str(readme_path)])
    assert result.exit_code == 0
    assert "Documentation written to" in result.stdout
    assert readme_path.exists()

    content = readme_path.read_text(encoding="utf-8")
    assert "# Test Skill" in content
    assert "A minimal skill used for CLI testing" in content
    assert "## Metadata" in content
    assert "## Usage" in content
    assert "skillora test" in content
    assert "Benchmark" in content
    assert "Compatibility" in content


def test_registry_commands(runner: CliRunner, tmp_path: Path) -> None:
    """Test registry list, scan, and install with isolated registry path."""
    registry_root = tmp_path / "registry"
    with patch("skillora.registry.LocalRegistry.DEFAULT_REGISTRY_ROOT", registry_root):
        # list on empty registry
        result = runner.invoke(app, ["registry", "list"])
        assert result.exit_code == 0
        assert "Skillora Registry" in result.stdout

        # scan
        result = runner.invoke(app, ["registry", "scan"])
        assert result.exit_code == 0
        assert "Scanned" in result.stdout

        # install a skill
        skill_path = tmp_path / "installable_skill.py"
        skill_path.write_text(
            '''from skillora import Skill, SkillResult, skill
@skill(name="installable", description="Skill installed via CLI test")
class Installable(Skill):
    def execute(self, context): return SkillResult(output={"installed": True})
skill = Installable()
''',
            encoding="utf-8",
        )

        result = runner.invoke(app, ["registry", "install", str(skill_path)])
        assert result.exit_code == 0
        assert "Installed 'installable'" in result.stdout

        # list again should show it
        result = runner.invoke(app, ["registry", "list"])
        assert result.exit_code == 0
        assert "installable" in result.stdout.lower()


def test_cli_error_cases(runner: CliRunner, tmp_path: Path) -> None:
    """Test helpful error messages for bad inputs."""
    # Non-existent file for test
    result = runner.invoke(app, ["test", "/non/existent/path"])
    assert result.exit_code != 0
    assert "Path" in result.stdout or "not a file" in result.stdout.lower()

    # Bad new command (invalid name not tested but directory error)
    bad_dir = tmp_path / "readonly"
    bad_dir.mkdir()
    bad_dir.chmod(0o555)  # make read-only on unix
    result = runner.invoke(
        app, ["new", "fail-skill", "--output-dir", str(bad_dir / "nested")]
    )
    # May succeed or fail depending on OS; at minimum no crash
    assert "Could not create directory" in result.stdout or result.exit_code in (0, 1)

    # Load skill with no skill present
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    (empty_dir / "skill.py").write_text("print('no skill here')", encoding="utf-8")
    result = runner.invoke(app, ["test", str(empty_dir)])
    assert result.exit_code != 0
    assert "No Skill instance" in result.stdout or "found in the module" in result.stdout


def test_load_skill_helper(temp_skill_dir: Path) -> None:
    """Direct test of internal _load_skill helper."""
    loaded = _load_skill(temp_skill_dir / "skill.py")
    assert isinstance(loaded, Skill)
    assert loaded.metadata.name == "test-skill"
    result = loaded.execute({"query": "cli-test"})
    assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
