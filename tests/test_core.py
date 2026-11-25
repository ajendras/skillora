"""Tests for the core Skillora abstractions.

Covers SkillMetadata and SkillResult Pydantic models (validation,
serialization), the abstract Skill base class, the @skill decorator
(both class and function forms), and the register_skill helper.

All tests are self-contained, test normal paths, edge cases, and
error conditions with clear assertions.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

import pytest
from pydantic import ValidationError

from skillora.core import (
    Skill,
    SkillMetadata,
    SkillResult,
    register_skill,
    skill,
)


def test_skill_metadata_valid() -> None:
    """Valid metadata creation and defaults."""
    meta = SkillMetadata(
        name="weather-lookup",
        description="Fetches current weather for any city.",
        version="1.2.3",
        tags=["weather", "api"],
        author="Skillora Team",
    )
    assert meta.name == "weather-lookup"
    assert meta.description == "Fetches current weather for any city."
    assert meta.version == "1.2.3"
    assert meta.tags == ["weather", "api"]
    assert meta.author == "Skillora Team"
    assert meta.license == "Apache-2.0"
    assert set(meta.compatibility) == {"langgraph", "crewai", "autogen"}


def test_skill_metadata_validation() -> None:
    """Validation errors for required fields and length constraints."""
    with pytest.raises(ValidationError) as exc_info:
        SkillMetadata(name="a", description="Too short name")
    assert "name" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        SkillMetadata(name="weather", description="x")
    assert "description" in str(exc_info.value)

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        SkillMetadata(
            name="test-skill",
            description="Valid description here.",
            extra_field="forbidden",
        )


def test_skill_metadata_serialization() -> None:
    """JSON and dict round-tripping."""
    meta = SkillMetadata(
        name="calculator",
        description="Performs arithmetic operations.",
        tags=["math"],
    )
    data = meta.model_dump()
    assert data["name"] == "calculator"
    assert data["tags"] == ["math"]

    json_str = meta.model_dump_json()
    reloaded = SkillMetadata.model_validate_json(json_str)
    assert reloaded.name == "calculator"
    assert reloaded.description == "Performs arithmetic operations."


def test_skill_result_defaults() -> None:
    """Default values and basic construction."""
    result = SkillResult()
    assert result.success is True
    assert result.output == {}
    assert result.error is None
    assert result.metadata == {}

    result2 = SkillResult(
        success=False,
        output={"error_detail": "timeout"},
        error="API timeout",
        metadata={"attempts": 3},
    )
    assert result2.success is False
    assert result2.output["error_detail"] == "timeout"
    assert result2.error == "API timeout"


def test_skill_result_validation() -> None:
    """Extra fields are forbidden."""
    with pytest.raises(ValidationError):
        SkillResult(success=True, unexpected="boom")


def test_skill_abstract() -> None:
    """Cannot instantiate base Skill directly."""
    with pytest.raises(TypeError) as exc_info:
        Skill()
    assert "abstract" in str(exc_info.value).lower() or "instantiate" in str(exc_info.value).lower()


class ConcreteSkill(Skill):
    """Minimal concrete implementation for testing."""

    metadata = SkillMetadata(
        name="concrete-test",
        description="A test skill that always succeeds.",
    )

    def execute(self, context: dict[str, Any]) -> SkillResult:
        query = context.get("query", "")
        return SkillResult(
            success=True,
            output={"result": f"Processed: {query}"},
            metadata={"source": "test"},
        )


def test_concrete_skill() -> None:
    """Basic usage of a concrete Skill subclass."""
    skill_instance = ConcreteSkill()
    assert skill_instance.metadata.name == "concrete-test"
    assert skill_instance.validate() is True

    result = skill_instance.execute({"query": "hello world"})
    assert result.success is True
    assert "hello world" in str(result.output)

    # Callable interface
    result2 = skill_instance({"query": "via call"})
    assert result2.success is True


def test_skill_metadata_from_init() -> None:
    """Metadata can be injected at construction time."""
    custom_meta = SkillMetadata(
        name="injected", description="Metadata passed to constructor."
    )
    skill_instance = ConcreteSkill(metadata=custom_meta)
    assert skill_instance.metadata.name == "injected"


def test_skill_default_metadata() -> None:
    """Fallback metadata derived from class name when none is defined."""

    class NoMetaSkill(Skill):
        def execute(self, context: dict[str, Any]) -> SkillResult:
            return SkillResult(output={"ok": True})

    instance = NoMetaSkill()
    assert instance.metadata.name == "no-meta"
    assert "reusable capability" in instance.metadata.description.lower()


def test_skill_validate() -> None:
    """Validation returns False for insufficient metadata."""

    class BadMetaSkill(Skill):
        metadata = SkillMetadata(name="x", description="short")
        def execute(self, context: dict[str, Any]) -> SkillResult:
            return SkillResult()

    assert BadMetaSkill().validate() is False


def test_skill_decorator_on_class() -> None:
    """@skill decorator on a Skill subclass attaches metadata."""

    @skill(
        name="decorated-skill",
        description="Decorated via class decorator.",
        tags=["decorated"],
    )
    class DecoratedSkill(Skill):
        def execute(self, context: dict[str, Any]) -> SkillResult:
            return SkillResult(output={"decorated": True})

    assert hasattr(DecoratedSkill, "metadata")
    meta = getattr(DecoratedSkill, "metadata")
    assert meta.name == "decorated-skill"
    assert meta.description == "Decorated via class decorator."
    assert "decorated" in meta.tags

    instance = DecoratedSkill()
    assert instance.metadata.name == "decorated-skill"


def test_skill_decorator_on_function() -> None:
    """@skill decorator on a plain function wraps it into a Skill subclass."""

    @skill(name="adder", description="Adds two numbers from context.")
    def add_numbers(context: dict[str, Any]) -> dict[str, Any]:
        a = context.get("a", 0)
        b = context.get("b", 0)
        return {"sum": a + b}

    assert issubclass(add_numbers, Skill)  # type: ignore[arg-type]
    instance = add_numbers()  # type: ignore[operator]

    result = instance.execute({"a": 5, "b": 7})
    assert result.success is True
    assert result.output == {"sum": 12}

    # Different call style (no context key)
    @skill(name="echo")
    def echo(value: str) -> str:
        return f"Echo: {value}"

    echo_skill = echo()  # type: ignore[operator]
    result2 = echo_skill.execute({"value": "hello"})
    assert "hello" in str(result2.output)


def test_wrapped_function_error_handling() -> None:
    """Function wrapper catches exceptions and returns SkillResult."""

    @skill(name="broken")
    def failing(_context: dict[str, Any]) -> None:
        raise RuntimeError("Intentional failure")

    skill_instance = failing()  # type: ignore[operator]
    result = skill_instance.execute({})
    assert result.success is False
    assert "Intentional failure" in result.error  # type: ignore[operator]
    assert result.metadata["original_exception"] == "RuntimeError"


def test_register_skill() -> None:
    """register_skill accepts instances or classes and populates internal registry."""
    skill_instance = ConcreteSkill()

    registered = register_skill(skill_instance)
    assert registered is skill_instance
    assert hasattr(register_skill, "_registry")
    assert skill_instance in register_skill._registry  # type: ignore[attr-defined]

    # Class registration
    registered_cls = register_skill(ConcreteSkill)
    assert isinstance(registered_cls, ConcreteSkill)

    # Validation failure raises
    class InvalidSkill(Skill):
        metadata = SkillMetadata(name="i", description="short")
        def execute(self, context: dict[str, Any]) -> SkillResult:
            return SkillResult()

    with pytest.raises(ValueError) as exc_info:
        register_skill(InvalidSkill)
    assert "failed validation" in str(exc_info.value).lower()

    # Bad argument
    with pytest.raises(TypeError):
        register_skill("not a skill")  # type: ignore[arg-type]


def test_skill_result_from_dict() -> None:
    """SkillResult can be constructed from dict output of wrapped functions."""
    result = SkillResult(success=True, output={"key": "value"})
    assert result.model_dump()["output"] == {"key": "value"}


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
