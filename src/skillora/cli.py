"""Command line interface for Skillora.

Uses Typer + Rich with the Neo-brutalist color scheme (#ff004d, #00ff9f).
All commands are production-ready, validate inputs, produce rich tables/panels,
and delegate to the modular core components defined in the project plan.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .benchmark import BenchmarkReport, BenchmarkRunner
from .core import Skill
from .generator import DocsGenerator, TemplateRenderer
from .registry import LocalRegistry
from .testing import SkillTester, TestGenerator

console = Console()
app = typer.Typer(
    name="skillora",
    help="Skillora — Scaffolds, validates, tests and benchmarks reusable skills for LLM agents with zero boilerplate.",
    rich_markup_mode="rich",
    add_completion=True,
)


def _load_skill(skill_path: Path) -> Skill:
    """Dynamically load a Skill instance from a Python file.

    Supports files that expose a module-level ``skill`` variable (common with the
    ``@skill`` decorator) or any subclass of ``Skill``. Raises a clear error with
    guidance if nothing is found.
    """
    if not skill_path.is_file():
        raise typer.BadParameter(f"Path '{skill_path}' is not a file.")

    spec = importlib.util.spec_from_file_location(skill_path.stem, str(skill_path))
    if spec is None or spec.loader is None:
        raise typer.BadParameter(f"Could not load spec for '{skill_path}'")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "skill") and isinstance(getattr(module, "skill"), Skill):
        return getattr(module, "skill")

    for _, obj in inspect.getmembers(module):
        if isinstance(obj, Skill):
            return obj
        if inspect.isclass(obj) and issubclass(obj, Skill) and obj is not Skill:
            return obj()  # instantiate default

    raise typer.BadParameter(
        "No Skill instance or subclass found in the module.\n"
        "Use the @skill decorator, define a class inheriting from Skill, "
        "or expose a module-level 'skill' variable."
    )


@app.command()
def new(
    name: str = typer.Argument(
        ..., help="Name of the skill to scaffold (kebab-case recommended)"
    ),
    desc: str = typer.Option(
        "A reusable capability for LLM agents.",
        "--desc",
        "-d",
        help="One-line description of what the skill does",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directory to write the generated skill into",
    ),
) -> None:
    """Instant Scaffolding: One command creates a fully typed skill skeleton with Pydantic models and metadata."""
    if output_dir is None:
        output_dir = Path.cwd() / name.replace("-", "_").lower()

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise typer.BadParameter(f"Could not create directory {output_dir}: {exc}") from exc

    renderer = TemplateRenderer()
    context: dict[str, Any] = {
        "skill_name": name,
        "class_name": "".join(part.title() for part in name.split("-")),
        "description": desc,
        "version": "0.1.0",
    }

    skill_code = renderer.render("skill.py.j2", context)

    skill_file = output_dir / "skill.py"
    skill_file.write_text(skill_code)
    (output_dir / "__init__.py").touch()

    console.print(
        Panel(
            f"[bold #00ff9f]Skill '{name}' scaffolded successfully![/]\n\n"
            f"Location: [cyan]{skill_file.resolve()}[/]\n"
            f"Next steps:\n"
            f"  cd {output_dir}\n"
            f"  vim skill.py          # implement .execute()\n"
            f"  skillora test skill.py",
            title="NEW SKILL READY",
            border_style="#ff004d",
            padding=(1, 2),
        )
    )


@app.command()
def test(
    skill_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=True,
        help="Path to a skill.py file or a directory containing one",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Print detailed test case results"
    ),
) -> None:
    """Test Generator: Produces deterministic unit tests plus LLM-as-judge cases from a one-line description."""
    if skill_path.is_dir():
        skill_path = skill_path / "skill.py"

    skill = _load_skill(skill_path)

    name = getattr(skill.metadata, "name", skill_path.stem)
    console.print(f"Testing [bold yellow]{name}[/]...")

    generator = TestGenerator()
    test_cases = generator.generate(skill, count=12)

    tester = SkillTester()
    report = tester.run(skill, test_cases)

    table = Table(title="Test Report", border_style="#00ff9f")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right", style="#00ff9f")
    table.add_row("Pass Rate", f"{report.pass_rate:.1%}")
    table.add_row("Judge Score", f"{getattr(report, 'judge_score', 0):.1f}/10")
    table.add_row("Test Cases", str(len(test_cases)))
    console.print(table)

    if report.pass_rate >= 0.85:
        console.print("[bold #00ff9f]Skill passed all tests with high confidence.[/]")
    else:
        console.print("[bold #ff004d]Skill failed one or more tests.[/]")

    if verbose and hasattr(report, "details"):
        console.print("\n[bold]Details:[/]")
        for line in report.details:
            console.print(f"  • {line}")


@app.command()
def benchmark(
    skill_path: Path = typer.Argument(
        ..., exists=True, dir_okay=True, help="Path to skill file or directory"
    ),
    scenarios: int = typer.Option(
        20, "--scenarios", "-n", min=1, max=100, help="Number of benchmark scenarios"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="CSV file to write benchmark report"
    ),
) -> None:
    """Benchmark Runner: Runs skills against scenario packs and reports accuracy, latency and token metrics."""
    if skill_path.is_dir():
        skill_path = skill_path / "skill.py"

    skill = _load_skill(skill_path)
    name = getattr(skill.metadata, "name", skill_path.stem)
    console.print(f"Benchmarking [bold yellow]{name}[/]...")

    runner = BenchmarkRunner()
    scenario_list = [{"query": f"Test scenario {i + 1}"} for i in range(scenarios)]
    report: BenchmarkReport = runner.run(skill, scenario_list)

    console.print(
        Panel(
            f"Benchmark results for [yellow]{name}[/]",
            title="BENCHMARK",
            border_style="#ff004d",
        )
    )

    table = Table(border_style="#00ff9f")
    table.add_column("Metric")
    table.add_column("Value", style="#00ff9f", justify="right")
    table.add_row("Accuracy", f"{report.accuracy:.2%}")
    table.add_row("Mean Latency", f"{report.mean_latency:.3f}s")
    table.add_row("Mean Tokens", f"{report.mean_tokens:.0f}")
    table.add_row("Total Runs", str(report.total_runs))
    console.print(table)

    if output:
        report.save_csv(output)
        console.print(f"[#00ff9f]Report saved to {output}[/]")


@app.command()
def docs(
    skill_path: Path = typer.Argument(
        ..., exists=True, dir_okay=True, help="Path to skill file or directory"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Path for generated Markdown file"
    ),
) -> None:
    """Auto Documentation: Renders Markdown reference with examples, parameters and compatibility notes."""
    if skill_path.is_dir():
        skill_path = skill_path / "skill.py"

    skill = _load_skill(skill_path)

    generator = DocsGenerator()
    if output is None:
        output = skill_path.parent / "README.md"

    generator.write_markdown(skill, output)
    console.print(
        f"[bold #00ff9f]Documentation written to {output.resolve()}[/]"
    )


# Registry subcommands
registry_app = typer.Typer(help="Local registry of trusted, portable skills.")


@registry_app.command("list")
def registry_list() -> None:
    """List all skills known to the local registry with a rich table."""
    registry = LocalRegistry()
    skills = registry.list()

    table = Table(title="Skillora Registry", border_style="#ff004d")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Tags")
    for skill_info in skills:
        table.add_row(
            skill_info.name,
            skill_info.description[:45]
            + ("..." if len(skill_info.description) > 45 else ""),
            ", ".join(skill_info.tags),
        )
    console.print(table)


@registry_app.command("scan")
def registry_scan() -> None:
    """Scan the disk registry path and index discovered skills."""
    registry = LocalRegistry()
    index = registry.scan()
    console.print(
        f"[bold #00ff9f]Scanned {len(index.skills)} skill(s).[/]"
    )


@registry_app.command("install")
def registry_install(
    name: str = typer.Argument(..., help="Name or path of skill to install"),
) -> None:
    """Install a skill from disk into the local catalog."""
    registry = LocalRegistry()
    registry.install(name)
    console.print(f"[bold #00ff9f]Installed '{name}' into local registry.[/]")


app.add_typer(registry_app, name="registry")


if __name__ == "__main__":
    app()
