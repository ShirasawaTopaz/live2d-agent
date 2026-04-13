"""Tool version management for dynamically generated tools.

Supports:
- Automatic version numbering (major.minor.patch)
- Version history tracking
- Metadata for each version
- Rollback capability
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from internal.agent.tool.dynamic.audit import get_audit_logger


audit = get_audit_logger()


class VersionInfo:
    """Information about a single version of a tool."""

    def __init__(
        self,
        version: str,
        created_at: str,
        code_hash: str,
        description: Optional[str] = None,
        file_path: Optional[str] = None,
    ):
        self.version = version
        self.created_at = created_at
        self.code_hash = code_hash
        self.description = description
        self.file_path = file_path

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "code_hash": self.code_hash,
            "description": self.description,
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "VersionInfo":
        """Create from dictionary."""
        return cls(
            version=data["version"],
            created_at=data["created_at"],
            code_hash=data["code_hash"],
            description=data.get("description"),
            file_path=data.get("file_path"),
        )


class VersionManager:
    """Manager for version tracking of dynamically generated tools."""

    def __init__(self, storage_path: Path):
        """Initialize the version manager.
        
        Args:
            storage_path: Base storage path for dynamic tools
        """
        self.storage_path = storage_path / "versions"
        self.version_index_path = self.storage_path / "version_index.json"
        self.index: Dict[str, List[VersionInfo]] = {}  # tool_name -> list of versions
        self._ensure_storage()
        self._load_index()

    def _ensure_storage(self):
        """Ensure the versions directory exists."""
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _load_index(self):
        """Load the version index from disk."""
        if self.version_index_path.exists():
            try:
                with open(self.version_index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.index = {}
                    for tool_name, versions_data in data.items():
                        self.index[tool_name] = [
                            VersionInfo.from_dict(v) for v in versions_data
                        ]
            except Exception as e:
                audit.log_error(
                    error_type="version_index_load_failed",
                    message=f"Failed to load version index: {e}",
                )
                self.index = {}
        else:
            self.index = {}

    def _save_index(self):
        """Save the version index to disk."""
        try:
            data = {}
            for tool_name, versions in self.index.items():
                data[tool_name] = [v.to_dict() for v in versions]
            with open(self.version_index_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            audit.log_error(
                error_type="version_index_save_failed",
                message=f"Failed to save version index: {e}",
            )

    def _get_next_version(self, tool_name: str) -> str:
        """Get the next version number for a tool.
        
        Follows semantic versioning: major.minor.patch
        New tools start at 1.0.0
        Subsequent updates increment patch version.
        """
        if tool_name not in self.index or not self.index[tool_name]:
            return "1.0.0"

        # Get latest version
        latest = self.index[tool_name][-1]
        major, minor, patch = latest.version.split(".")
        major = int(major)
        minor = int(minor)
        patch = int(patch)
        patch += 1
        return f"{major}.{minor}.{patch}"

    @staticmethod
    def _hash_code(code: str) -> str:
        """Simple hash of code for change detection."""
        import hashlib
        return hashlib.sha256(code.encode()).hexdigest()[:12]

    def add_version(
        self,
        tool_name: str,
        code: str,
        description: Optional[str] = None,
    ) -> VersionInfo:
        """Add a new version for a tool.
        
        Args:
            tool_name: Name of the tool
            code: The source code for this version
            description: Optional description of this version
        
        Returns:
            VersionInfo for the new version
        """
        version = self._get_next_version(tool_name)
        code_hash = self._hash_code(code)
        created_at = datetime.now().isoformat()

        # Save the versioned copy
        version_file_name = f"{tool_name}_v{version.replace('.', '_')}_tool.py"
        version_file = self.storage_path / version_file_name
        version_file.write_text(code, encoding="utf-8")

        # Create version info
        info = VersionInfo(
            version=version,
            created_at=created_at,
            code_hash=code_hash,
            description=description,
            file_path=str(version_file.relative_to(self.storage_path)),
        )

        # Add to index
        if tool_name not in self.index:
            self.index[tool_name] = []
        self.index[tool_name].append(info)
        self._save_index()

        audit.log_error(  # Actually this isn't an error but using existing logging
            error_type="new_version_added",
            message=f"Added version {version} for tool {tool_name}",
            tool_name=tool_name,
        )

        return info

    def get_versions(self, tool_name: str) -> List[VersionInfo]:
        """Get all versions for a tool.
        
        Returns ordered from oldest to newest.
        """
        return self.index.get(tool_name, [])

    def get_latest_version(self, tool_name: str) -> Optional[VersionInfo]:
        """Get the latest version of a tool."""
        versions = self.get_versions(tool_name)
        if not versions:
            return None
        return versions[-1]

    def get_version(self, tool_name: str, version: str) -> Optional[VersionInfo]:
        """Get a specific version of a tool."""
        versions = self.get_versions(tool_name)
        for v in versions:
            if v.version == version:
                return v
        return None

    def get_version_code(self, tool_name: str, version: str) -> Optional[str]:
        """Get the source code for a specific version."""
        info = self.get_version(tool_name, version)
        if not info or not info.file_path:
            return None
        file_path = self.storage_path / info.file_path
        if not file_path.exists():
            return None
        return file_path.read_text(encoding="utf-8")

    def rollback_to(self, tool_name: str, version: str) -> Tuple[bool, Optional[str]]:
        """Rollback to a specific version.
        
        After rollback, the current code becomes the latest version,
        and the rolled-back version is still kept in history.
        
        Returns:
            (success, error_message)
        """
        info = self.get_version(tool_name, version)
        if not info:
            return False, f"Version {version} not found for tool {tool_name}"

        code = self.get_version_code(tool_name, version)
        if code is None:
            return False, f"Code file missing for version {version}"

        # Add a new version that's a copy of the rolled-back version
        description = f"Rollback to version {version}"
        self.add_version(tool_name, code, description=description)

        audit.log_error(
            error_type="tool_rollback",
            message=f"Rolled back {tool_name} to version {version}",
            tool_name=tool_name,
        )

        return True, None

    def delete_versions(self, tool_name: str) -> int:
        """Delete all versions for a tool (called when tool is deleted).
        
        Returns:
            Number of version files deleted
        """
        if tool_name not in self.index:
            return 0

        count = 0
        for version in self.index[tool_name]:
            if version.file_path:
                version_file = self.storage_path / version.file_path
                if version_file.exists():
                    version_file.unlink()
                    count += 1

        del self.index[tool_name]
        self._save_index()

        return count

    def check_for_changes(self, tool_name: str, new_code: str) -> bool:
        """Check if new code is different from latest version.
        
        Returns:
            True if code has changed, False if identical
        """
        latest = self.get_latest_version(tool_name)
        if latest is None:
            return True

        new_hash = self._hash_code(new_code)
        return new_hash != latest.code_hash

    def get_version_count(self, tool_name: str) -> int:
        """Get number of versions for a tool."""
        return len(self.get_versions(tool_name))

    def list_all_tools(self) -> List[str]:
        """List all tool names that have version history."""
        return list(self.index.keys())
