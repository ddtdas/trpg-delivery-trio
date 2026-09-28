"""仓库根目录集合 (可注入, 便于测试隔离) —— additive。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import APP_ROOT


@dataclass(frozen=True)
class RepoRoots:
    """四个物理根 + 导入日志。默认全部落在 APP_ROOT 下。"""

    modules: Path
    rulepacks: Path
    prep: Path
    imports: Path
    staging: Path
    log: Path

    def ensure(self) -> "RepoRoots":
        for p in (self.modules, self.rulepacks, self.prep, self.imports, self.staging):
            p.mkdir(parents=True, exist_ok=True)
        return self

    def with_base(self, base: Path) -> "RepoRoots":
        base = Path(base)
        return RepoRoots(modules=base / "modules", rulepacks=base / "rulepacks",
                         prep=base / "data" / "module_prep",
                         imports=base / "data" / "imports",
                         staging=base / "data" / ".repo_staging",
                         log=base / "data" / "repo_imports.jsonl")

    @classmethod
    def default(cls) -> "RepoRoots":
        return cls(
            modules=APP_ROOT / "modules",
            rulepacks=APP_ROOT / "rulepacks",
            prep=APP_ROOT / "data" / "module_prep",
            imports=APP_ROOT / "data" / "imports",
            staging=APP_ROOT / "data" / ".repo_staging",
            log=APP_ROOT / "data" / "repo_imports.jsonl",
        )
