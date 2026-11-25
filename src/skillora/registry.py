"""Local registry for Skillora skills.

Provides disk-based cataloging, installation from paths, scanning of known
locations, and search by name, description or tag. Uses a JSON index stored
in ~/.skillora/registry/index.json for persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .core import Skill, SkillMetadata, register_skill


class SkillInfo(BaseModel):
    """Index entry for a single skill."""

    name: str = Field(..., min_length=2)
    description: str = Field(..., min_length=10)
    version: str = "0.1.0"
    tags: List[str] = Field(default_factory=list)
    path: Optional[str] = None
    installed_at: Optional[str] = None

    class Config:
        extra = "forbid"


class SkillIndex(BaseModel):
    """Collection of indexed skills with search capabilities."""

    skills: List[SkillInfo] = Field(default_factory=list)
    registry_path: Path

    def search(self, query: str = "", tag: str = "") -> List[SkillInfo]:
        """Search skills by partial name/description or by tag.

        Args:
            query: Substring to match in name or description.
            tag: Exact tag to filter by.

        Returns:
            List of matching SkillInfo entries.
        """
        results = self.skills[:]

        if query:
            q = query.lower()
            results = [
                s
                for s in results
                if q in s.name.lower() or q in s.description.lower()
            ]

        if tag:
            results = [s for s in results if tag.lower() in [t.lower() for t in s.tags]]

        return results

    def add(self, info: SkillInfo) -> None:
        """Add or replace a skill entry by name."""
        self.skills = [s for s in self.skills if s.name != info.name]
        self.skills.append(info)


class LocalRegistry:
    """Manages a local on-disk registry of Skillora skills.

    Supports installation from file paths, scanning for registered or
    discovered skills, listing, and search via SkillIndex.
    """

    DEFAULT_REGISTRY_ROOT = Path.home() / ".skillora" / "registry"

    def __init__(self, registry_root: Optional[Path] = None) -> None:
        self.registry_root = registry_root or self.DEFAULT_REGISTRY_ROOT
        self.registry_root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.registry_root / "index.json"
        self.index: SkillIndex = self._load_or_create_index()

    def _load_or_create_index(self) -> SkillIndex:
        if self.index_path.exists():
            try:
                data: Dict[str, Any] = json.loads(
                    self.index_path.read_text(encoding="utf-8")
                )
                # registry_path is set by us, not stored
                data.pop("registry_path", None)
                return SkillIndex(registry_path=self.registry_root, **data)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass  # fall back to empty index
        return SkillIndex(registry_path=self.registry_root)

    def _save_index(self) -> None:
        self.index_path.write_text(
            self.index.json(indent=2),
            encoding="utf-8",
        )

    def scan(self) -> SkillIndex:
        """Scan registry directory and global register_skill registry.

        Discovers any installed skill.py files and merges with in-memory
        registered skills. Updates the index on disk.

        Returns:
            Current SkillIndex.
        """
        discovered: List[SkillInfo] = []

        # 1. Load from global registry populated by register_skill()
        if hasattr(register_skill, "_registry"):
            for skill_obj in getattr(register_skill, "_registry", []):
                if isinstance(skill_obj, Skill):
                    discovered.append(
                        SkillInfo(
                            name=skill_obj.metadata.name,
                            description=skill_obj.metadata.description,
                            version=skill_obj.metadata.version,
                            tags=skill_obj.metadata.tags,
                        )
                    )

        # 2. Scan disk for any skill.py files under registry_root
        for skill_file in self.registry_root.glob("**/skill.py"):
            try:
                # Minimal metadata extraction without full import
                content = skill_file.read_text(encoding="utf-8")
                name = skill_file.parent.name
                # Look for a metadata dict or class attribute (naive)
                if "name=" in content or "SkillMetadata" in content:
                    discovered.append(
                        SkillInfo(
                            name=name,
                            description="Discovered local skill",
                            version="0.1.0",
                            tags=["local"],
                            path=str(skill_file),
                        )
                    )
            except Exception:
                continue  # ignore unreadable files

        # Merge discovered items
        for info in discovered:
            self.index.add(info)

        self._save_index()
        return self.index

    def list(self) -> List[SkillInfo]:
        """Return all skills in the index (scanning first if empty)."""
        if not self.index.skills:
            self.scan()
        return self.index.skills

    def install(self, name_or_path: str) -> SkillInfo:
        """Install a skill from a filesystem path into the registry.

        Copies the skill files into a subdirectory of the registry root
        and updates the index. If a Skill instance is passed it is also
        registered via register_skill.

        Args:
            name_or_path: Path to a skill.py file or a directory containing one.

        Returns:
            The SkillInfo that was installed.

        Raises:
            ValueError: If the path does not exist or is invalid.
            TypeError: If an unsupported type is provided.
        """
        if not name_or_path:
            raise ValueError("name_or_path cannot be empty")

        src = Path(name_or_path)
        if not src.exists():
            raise ValueError(f"Path '{name_or_path}' does not exist")

        # Determine target directory name
        if src.is_file() and src.name == "skill.py":
            target_name = src.parent.name
        else:
            target_name = src.stem.replace("_", "-").lower()

        target_dir = self.registry_root / target_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "skill.py"

        if src.is_file():
            target_file.write_text(src.read_text(encoding="utf-8"))
        elif (src / "skill.py").exists():
            target_file.write_text((src / "skill.py").read_text(encoding="utf-8"))
        else:
            raise ValueError(f"No skill.py found in {src}")

        # Try to load metadata for accurate index entry
        try:
            from .cli import _load_skill  # avoid circular import at top level

            loaded_skill = _load_skill(target_file)
            meta = loaded_skill.metadata
            info = SkillInfo(
                name=meta.name,
                description=meta.description,
                version=meta.version,
                tags=meta.tags,
                path=str(target_file),
            )
        except Exception:
            # Fallback
            info = SkillInfo(
                name=target_name,
                description="Installed via Skillora registry",
                version="0.1.0",
                tags=["installed"],
                path=str(target_file),
            )

        self.index.add(info)
        self._save_index()

        # Also register it globally
        try:
            register_skill(info)  # type: ignore[arg-type]  # will be handled gracefully
        except Exception:
            pass  # best effort

        return info

    def get(self, name: str) -> Optional[SkillInfo]:
        """Retrieve a skill by exact name."""
        for skill_info in self.list():
            if skill_info.name == name:
                return skill_info
        return None


__all__ = ["LocalRegistry", "SkillIndex", "SkillInfo"]
