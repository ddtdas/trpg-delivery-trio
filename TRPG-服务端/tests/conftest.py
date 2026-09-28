"""pytest 引导: 把服务端根加入 sys.path, 并提供仓库根/样例包 fixture。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from app.repository.roots import RepoRoots  # noqa: E402


@pytest.fixture()
def repo_roots(tmp_path: Path) -> RepoRoots:
    r = RepoRoots.default().with_base(tmp_path / "repo")
    r.ensure()
    # 让 ruleset 校验通过: 预置一个最小 coc7 规则包
    rp = r.rulepacks / "coc7"
    rp.mkdir(parents=True, exist_ok=True)
    (rp / "rulepack.yaml").write_text(
        "id: coc7\nversion: \"1.0.0\"\ndisplay_name: \"CoC7 (test)\"\n", encoding="utf-8")
    return r


@pytest.fixture()
def good_module(tmp_path: Path):
    from _pkgbuild import build_module

    return build_module(tmp_path / "pkgs" / "good")
