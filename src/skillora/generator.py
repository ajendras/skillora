"""Template and documentation generators for Skillora.

TemplateRenderer loads Jinja2 templates from the package's templates/
directory and renders them with skill-specific context.

DocsGenerator produces rich Markdown documentation including metadata,
usage examples, parameter descriptions, compatibility matrix and
benchmark guidance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import jinja2
from pydantic import BaseModel, Field

from .core import Skill, SkillMetadata, SkillResult


class RenderedSkill(BaseModel):
    """Metadata about a rendered skill file."""

    path: Path
    class_name: str
    metadata: SkillMetadata


class TemplateRenderer:
    """Renders Jinja2 templates for skill scaffolding.

    Uses PackageLoader so the templates are included when the package
    is installed. Validates context keys required by the skill template.
    """

    REQUIRED_KEYS = {"skill_name", "class_name", "description", "version"}

    def __init__(self) -> None:
        self.env = jinja2.Environment(
            loader=jinja2.PackageLoader("skillora", "templates"),
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=jinja2.StrictUndefined,
        )

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render a named template with context.

        Args:
            template_name: Template filename (e.g. "skill.py.j2").
            context: Dictionary of variables to pass to the template.

        Returns:
            Fully rendered text content.

        Raises:
            ValueError: If required context keys are missing or template is invalid.
            RuntimeError: If rendering fails for any other reason.
        """
        if not isinstance(context, dict):
            raise TypeError("context must be a dict")

        missing = self.REQUIRED_KEYS - context.keys()
        if missing:
            raise ValueError(
                f"Missing required context keys for template: {missing}. "
                f"Got: {list(context.keys())}"
            )

        for key in ("skill_name", "class_name"):
            if not isinstance(context.get(key), str) or not context[key].strip():
                raise ValueError(f"context['{key}'] must be a non-empty string")

        try:
            template = self.env.get_template(template_name)
            return template.render(**context)
        except jinja2.TemplateNotFound as exc:
            raise ValueError(
                f"Template '{template_name}' not found in skillora.templates"
            ) from exc
        except jinja2.TemplateSyntaxError as exc:
            raise RuntimeError(f"Template syntax error in {template_name}: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to render {template_name}: {exc}") from exc

    def render_skill(self, context: Dict[str, Any], output_path: Path) -> RenderedSkill:
        """Convenience method that renders the skill template and writes the file.

        Also ensures the output directory exists and creates an __init__.py.

        Returns:
            RenderedSkill with metadata about what was created.
        """
        content = self.render("skill.py.j2", context)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        (output_path.parent / "__init__.py").touch(exist_ok=True)

        meta = SkillMetadata(
            name=context["skill_name"],
            description=context["description"],
            version=context["version"],
        )

        return RenderedSkill(
            path=output_path,
            class_name=context["class_name"],
            metadata=meta,
        )


class DocsGenerator:
    """Generates Markdown reference documentation for a Skill.

    Produces a complete, ready-to-publish README.md with sections for
    metadata, usage, parameters, examples, testing and benchmark results.
    """

    def write_markdown(self, skill: Skill, output: Path) -> None:
        """Write Markdown documentation for the skill to the given path.

        Args:
            skill: Skill instance (must have valid metadata).
            output: Destination file path (usually README.md).

        Raises:
            TypeError: If skill is not a Skill instance.
            ValueError: If metadata is invalid.
        """
        if not isinstance(skill, Skill):
            raise TypeError(
                f"Expected Skill instance, got {type(skill).__name__}. "
                "Use @skill decorator or inherit from Skill."
            )

        if not skill.metadata or not skill.metadata.name:
            raise ValueError("Skill must have valid metadata")

        output.parent.mkdir(parents=True, exist_ok=True)
        content = self._generate_content(skill)
        output.write_text(content, encoding="utf-8")

    def _generate_content(self, skill: Skill) -> str:
        meta = skill.metadata
        class_name = "".join(part.title() for part in meta.name.split("-"))

        lines = [
            f"# {meta.name.replace('-', ' ').title()}",
            "",
            meta.description,
            "",
            "![Skillora](https://img.shields.io/badge/Skillora-00ff9f?style=flat&logo=python)",
            "",
            "## Metadata",
            "",
            "| Key | Value |",
            "|-----|-------|",
            f"| **Name** | `{meta.name}` |",
            f"| **Version** | `{meta.version}` |",
            f"| **License** | {meta.license} |",
            f"| **Tags** | {', '.join(f'`{t}`' for t in meta.tags) if meta.tags else '_none_'} |",
            f"| **Compatible** | {', '.join(meta.compatibility)} |",
            "",
            "## Installation",
            "",
            "```bash",
            f"pip install skillora",
            f"# Then import from your skill package",
            "```",
            "",
            "## Usage",
            "",
            "```python",
            "from skillora import skill",
            f"from .{meta.name.replace('-', '_')} import {class_name}",
            "",
            "# Using the decorator-wrapped class",
            f"skill_instance = {class_name}()",
            'result = skill_instance.execute({"query": "your input here"})',
            "",
            "print(result.success, result.output)",
            "```",
            "",
            "## Parameters",
            "",
            "The `execute` method accepts a single `context: dict` argument. ",
            "Common keys include:",
            "",
            "* `query` – primary input string or object",
            "* `parameters` – optional configuration dict",
            "* `user_id`, `session` – context for personalization",
            "",
            "All inputs are validated inside the skill; a `SkillResult` is always returned.",
            "",
            "## Example Outputs",
            "",
            "```json",
            json.dumps(
                {
                    "success": True,
                    "output": {
                        "status": "processed",
                        "result": "Example output payload",
                    },
                    "metadata": {"source": "skillora-example"},
                },
                indent=2,
            ),
            "```",
            "",
            "## Testing",
            "",
            "```bash",
            f"skillora test {meta.name}",
            "# or",
            "pytest",
            "```",
            "",
            "The framework auto-generates 12+ deterministic tests plus LLM-as-judge cases.",
            "",
            "## Benchmark",
            "",
            "```bash",
            f"skillora benchmark {meta.name} --scenarios 50 --output report.csv",
            "```",
            "",
            "Reports accuracy, mean latency, token usage and exports a detailed CSV.",
            "",
            "## Compatibility",
            "",
            "Tested against:",
            "",
        ]

        for framework in meta.compatibility:
            lines.append(f"* **{framework.title()}** – full support via standard `Skill` interface")

        lines.extend(
            [
                "",
                "## License",
                "",
                f"{meta.license} – see LICENSE for details.",
                "",
                "---",
                "",
                f"_Generated by Skillora v0.1.0 • {meta.name}_",
            ]
        )

        return "\n".join(lines)


__all__ = ["TemplateRenderer", "DocsGenerator", "RenderedSkill"]
