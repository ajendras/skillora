"""Skillora — Scaffolds, validates, tests and benchmarks reusable skills for LLM agents with zero boilerplate.

Public API re-exports the core types and decorator so users can do:

    from skillora import Skill, skill, SkillMetadata, SkillResult, register_skill
"""

__version__ = "0.1.0"

from .core import Skill  # BaseSkill aliased to Skill for public API
from .core import skill
from .core import SkillMetadata
from .core import SkillResult
from .core import register_skill

__all__ = [
    "Skill",
    "skill",
    "SkillMetadata",
    "SkillResult",
    "register_skill",
    "__version__",
]
