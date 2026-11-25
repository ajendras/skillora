"""Core abstractions for Skillora.

Defines the standard Skill interface, Pydantic models for metadata and results,
the @skill decorator, and a register_skill helper. All skills must inherit from
Skill (or be wrapped by the decorator) and implement execute(context: dict) -> SkillResult.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type, Union, cast

from pydantic import BaseModel, Field


class SkillMetadata(BaseModel):
    """Metadata describing a skill.

    Used for scaffolding, documentation, registry indexing, compatibility
    checks with agent frameworks (LangGraph, CrewAI, etc.) and search.
    """

    name: str = Field(..., min_length=2, description="Skill identifier (kebab-case preferred)")
    description: str = Field(
        ..., min_length=10, description="One-line purpose of the skill"
    )
    version: str = Field("0.1.0", description="Semantic version string")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    author: Optional[str] = Field(None, description="Author or organization")
    license: str = "Apache-2.0"
    compatibility: List[str] = Field(
        default_factory=lambda: ["langgraph", "crewai", "autogen"],
        description="Supported agent runtimes",
    )

    class Config:
        extra = "forbid"


class SkillResult(BaseModel):
    """Standardized return value from every skill execution.

    Guarantees a consistent contract for all LLM-agent skills.
    """

    success: bool = True
    output: Any = Field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


class Skill(ABC):
    """Base class for all reusable skills.

    Every skill must implement ``execute`` and expose ``metadata``.
    The class supports both class-level metadata (preferred) and
    instance-level injection.
    """

    metadata: SkillMetadata

    def __init__(self, metadata: Optional[SkillMetadata] = None) -> None:
        """Initialize a skill, ensuring metadata is always present.

        Args:
            metadata: Optional explicit metadata (overrides class attribute).

        Raises:
            ValueError: If no metadata can be determined.
        """
        if metadata is not None:
            self.metadata = metadata
            return

        # Prefer class attribute set by decorator or manually
        cls = self.__class__
        if hasattr(cls, "metadata") and isinstance(
            getattr(cls, "metadata"), (SkillMetadata, dict)
        ):
            meta = getattr(cls, "metadata")
            self.metadata = meta if isinstance(meta, SkillMetadata) else SkillMetadata(**meta)
            return

        # Fallback to sensible defaults derived from class name
        name = cls.__name__.lower()
        if name.endswith("skill"):
            name = name[:-5].strip("-_")
        if not name:
            name = "unnamed"

        self.metadata = SkillMetadata(
            name=name,
            description=(
                getattr(cls, "__doc__", None) or "A reusable capability for LLM agents."
            ).strip(),
        )

    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> SkillResult:
        """Execute the skill.

        All input data must be passed via the context dictionary.
        Must always return a SkillResult (never raise unless truly unrecoverable).

        Args:
            context: Input parameters and runtime context (query, user data, etc).

        Returns:
            SkillResult containing success status, output or error.
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def __call__(self, context: Dict[str, Any]) -> SkillResult:
        """Convenience callable interface for frameworks that treat skills as functions."""
        return self.execute(context)

    def validate(self) -> bool:
        """Perform basic compatibility and contract validation.

        Returns:
            True if the skill meets minimum Skillora standards.
        """
        if not self.metadata.name or len(self.metadata.description) < 10:
            return False
        # Future: could inspect execute signature, required fields, etc.
        return True


def skill(
    name: Optional[str] = None,
    description: Optional[str] = None,
    version: str = "0.1.0",
    tags: Optional[List[str]] = None,
    **meta_kwargs: Any,
) -> Callable[[Union[Type[Skill], Callable[..., Any]]], Union[Type[Skill], Type[Skill]]]:
    """Decorator to attach metadata to a Skill subclass or wrap a plain function.

    Supports two usage styles:

        @skill(name="weather-lookup", description="Retrieves current weather")
        class WeatherSkill(Skill):
            def execute(self, context: dict) -> SkillResult:
                ...

        @skill(name="calculator")
        def add(context: dict) -> dict:
            ...
    """

    def decorator(
        target: Union[Type[Skill], Callable[..., Any]]
    ) -> Union[Type[Skill], Type[Skill]]:
        if inspect.isclass(target) and issubclass(target, Skill):
            # Class decorator path
            meta = SkillMetadata(
                name=name or meta_kwargs.get("name") or target.__name__.lower().replace("skill", ""),
                description=description
                or meta_kwargs.get("description")
                or (target.__doc__ or "No description provided.").strip(),
                version=version,
                tags=tags or meta_kwargs.get("tags") or [],
            )
            target.metadata = meta  # type: ignore[attr-defined]
            return cast(Type[Skill], target)

        # Function decorator path - wrap in a Skill subclass
        meta = SkillMetadata(
            name=name or meta_kwargs.get("name") or getattr(target, "__name__", "function-skill"),
            description=description
            or meta_kwargs.get("description")
            or (getattr(target, "__doc__", None) or "Wrapped function skill").strip(),
            version=version,
            tags=tags or meta_kwargs.get("tags") or ["function"],
        )

        class _WrappedSkill(Skill):
            metadata = meta

            def execute(self, context: Dict[str, Any]) -> SkillResult:
                try:
                    if inspect.ismethod(target) or inspect.isfunction(target):
                        sig = inspect.signature(target)
                        if "context" in sig.parameters or len(sig.parameters) == 0:
                            raw_result = target(context)
                        else:
                            raw_result = target(**context) if isinstance(context, dict) else target(context)
                    else:
                        raw_result = target(context)

                    if isinstance(raw_result, SkillResult):
                        return raw_result
                    if isinstance(raw_result, dict):
                        return SkillResult(success=True, output=raw_result)
                    return SkillResult(success=True, output={"result": raw_result})
                except Exception as exc:
                    return SkillResult(
                        success=False,
                        error=str(exc),
                        metadata={"original_exception": type(exc).__name__},
                    )

        _WrappedSkill.__name__ = getattr(target, "__name__", "WrappedSkill")
        _WrappedSkill.__doc__ = getattr(target, "__doc__", None)
        return _WrappedSkill

    return decorator


def register_skill(skill: Union[Skill, Type[Skill]]) -> Skill:
    """Register a skill instance or class for global discovery.

    Primarily used by frameworks or when building a skill catalog programmatically.
    Returns the (instantiated) skill for fluent usage.

    Args:
        skill: A Skill instance or subclass.

    Raises:
        TypeError: If argument is not a Skill or subclass.
    """
    if inspect.isclass(skill) and issubclass(skill, Skill):
        instance: Skill = skill()  # type: ignore[call-arg]
    elif isinstance(skill, Skill):
        instance = skill
    else:
        raise TypeError(
            "register_skill expects a Skill instance or subclass. "
            f"Got {type(skill).__name__}."
        )

    if not instance.validate():
        raise ValueError(
            f"Skill '{instance.metadata.name}' failed validation. "
            "Ensure metadata.name and metadata.description are set."
        )

    # Global registry (used by registry.py when scanning)
    if not hasattr(register_skill, "_registry"):
        register_skill._registry = []  # type: ignore[attr-defined]
    register_skill._registry.append(instance)  # type: ignore[attr-defined]

    return instance


__all__ = [
    "Skill",
    "SkillMetadata",
    "SkillResult",
    "skill",
    "register_skill",
]
