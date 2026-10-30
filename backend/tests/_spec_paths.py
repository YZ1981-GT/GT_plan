"""测试里定位 spec 目录 / 文件：active 优先、已归档回退 `_archive/*/`。

单一来源是 `backend/scripts/check/_spec_dir.resolve_spec_dir`（守卫脚本共用），这里按文件路径加载它，
不复制回退逻辑。

背景（spec writeback-followup-issue-closure R12）：spec 归档后，写死 `.kiro/specs/<name>/…` 的测试在
干净检出上恒红，报的是误导性的「文件不存在」。`workpaper-html-onlyoffice-bidirectional-writeback-closure`
归档进 `_archive/17-…` 之后一次打红了十几个守卫。
"""
from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Callable

_RESOLVER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check" / "_spec_dir.py"


@lru_cache(maxsize=1)
def _resolver() -> Callable[..., Path]:
    spec = importlib.util.spec_from_file_location("_spec_dir_for_tests", _RESOLVER_PATH)
    assert spec is not None and spec.loader is not None, _RESOLVER_PATH
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve_spec_dir


def spec_dir(name: str, *require_files: str) -> Path:
    """spec 目录（同时含 `require_files` 的那一份）。都找不到时返回 active 路径，让调用方报清楚的错。"""
    return _resolver()(name, require_files=list(require_files) or None)


def spec_file(name: str, relative: str) -> Path:
    """spec 目录下的一个文件：按这个文件在哪一份里存在来选 active / 归档。"""
    return spec_dir(name, relative) / relative


def repo_ref_path(ref: str, repo: Path) -> Path:
    """仓库相对路径（登记表里的 `source_ref` 一类）；指向 `.kiro/specs/<name>/…` 而该 spec 已归档时，
    换成归档里那一份。登记表本身不改：它记的是写入时的出处。"""
    path = repo / ref
    if path.exists():
        return path
    parts = Path(ref).parts
    if len(parts) >= 4 and parts[0] == ".kiro" and parts[1] == "specs":
        return spec_file(parts[2], Path(*parts[3:]).as_posix())
    return path
