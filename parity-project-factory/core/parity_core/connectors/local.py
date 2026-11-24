"""Local folder connector: files are placed manually in a project folder."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional


class LocalConnector:
    """Resolves dataset files from `connector.folder` + `connector.file_pattern`.

    `connector.selection`:
      - "latest" (default): newest matching file by modification time
      - "all": every matching file, oldest first (useful for append/history tables)
      - "single": exactly one matching file must exist, otherwise ask the user
    """

    def __init__(self, dataset_name: str, cfg: Dict, project_root: Path):
        self.dataset_name = dataset_name
        self.cfg = cfg
        folder = Path(cfg.get("folder", "input"))
        self.folder = folder if folder.is_absolute() else project_root / folder
        self.pattern = cfg.get("file_pattern", "*")
        self.selection = cfg.get("selection", "latest")

    def check(self) -> Dict:
        exists = self.folder.is_dir()
        matches = self.list_files() if exists else []
        return {
            "dataset": self.dataset_name,
            "folder": str(self.folder),
            "pattern": self.pattern,
            "folder_exists": exists,
            "matching_files": [p.name for p in matches],
        }

    def list_files(self) -> List[Path]:
        if not self.folder.is_dir():
            return []
        files = [p for p in self.folder.glob(self.pattern) if p.is_file() and not p.name.lower().startswith("readme")]
        return sorted(files, key=lambda p: (p.stat().st_mtime, p.name))

    def resolve(self, explicit: Optional[List[str]] = None) -> List[Path]:
        if explicit:
            resolved = []
            for item in explicit:
                path = Path(item)
                if not path.is_absolute():
                    candidate = self.folder / path
                    path = candidate if candidate.exists() else path.resolve()
                if not path.is_file():
                    raise FileNotFoundError(f"[{self.dataset_name}] file not found: {item}")
                resolved.append(path)
            return resolved
        files = self.list_files()
        if not files:
            raise FileNotFoundError(
                f"[{self.dataset_name}] no files matching '{self.pattern}' in {self.folder}. "
                f"Place the file there (see the folder README) or pass --file."
            )
        if self.selection == "all":
            return files
        if self.selection == "single":
            if len(files) > 1:
                names = ", ".join(p.name for p in files)
                raise ValueError(
                    f"[{self.dataset_name}] expected exactly one file but found {len(files)}: {names}. "
                    f"Ask the user which file to use and pass it with --file."
                )
            return files
        return [files[-1]]
