# -*- coding: utf-8 -*-
"""spec 文档（三件套 / evidence）的目录解析 —— 全仓**唯一**实现。

## 为什么需要它

spec 完成后会从 active 目录 `.kiro/specs/<name>/` 归档到
`.kiro/specs/_archive/<nn>-xxx/<name>/`。把 active 路径写死的门禁，一归档就对任何
clean checkout 恒红 —— 而恒红的门禁等价于门禁失效（红成常态 → 没人看 → 真缺陷藏在
里面）。更糟的是它报的是误导性的「文件不存在」，而不是 spec 的真实状态。

## 为什么还需要内容标记（`require_matches`）

2026-11-01 实测：spec 可以被**重写**，而不是只被归档。
`workpaper-html-onlyoffice-bidirectional-writeback-closure` 重建了 active 目录，三件套
换成「7 条扁平 AC + 两级任务号」的新形态；而若干历史门禁解析的是旧形态
（`### Requirement N` 标题、`## Acceptance Oracle Matrix`、整数任务号、AC 7.7 / 14.10
原文）。此时 active **存在且三件套齐全** ⇒ 只看「目录在不在 / 文件在不在」的判据一路
放行，于是这些门绑到了一份它们根本解析不了的文档上，报出「找不到 Task 68」「AC 先于
requirement 标题出现」这类**指错地方**的错误。

`require_matches` 让调用方声明「我要的是哪一种文档形态」，解析就从「目录对不对」升级为
「**契约**对不对」：

* 旧形态还在归档里 ⇒ 自动绑归档快照，门恢复可运行；
* 形态哪天回到 active ⇒ 自动改回 active，不用改脚本；
* 不像写死归档路径那样，会把一个**错误的**快照静默选中。

## 位置

放在 `app/core/` 而不是 `backend/scripts/check/` 下，是因为消费方同时有三类：
check 脚本、gen 脚本，以及**生产代码**（`app/services/workpaper_sync/capacity_profile.py`
按 AC 原文校验容量登记值）。三类都能 import 的地方只有 `app/`。
`backend/scripts/check/_spec_dir.py` 保留为薄壳 re-export，老调用方一个字都不用改。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping, Sequence

#: 仓库根：本文件位于 backend/app/core/spec_docs.py，parents[3] = 根
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPECS_ROOT = _REPO_ROOT / ".kiro" / "specs"

__all__ = ["resolve_spec_dir", "specs_root"]


def specs_root(repo_root: Path | None = None) -> Path:
    return (repo_root / ".kiro" / "specs") if repo_root is not None else _SPECS_ROOT


def resolve_spec_dir(
    spec_name: str,
    *,
    require_files: Sequence[str] | None = None,
    require_matches: Mapping[str, Sequence[str]] | None = None,
    repo_root: Path | None = None,
) -> Path:
    """定位名为 ``spec_name`` 的 spec 目录。

    active 优先；否则回退到 `_archive/*/` 下的同名目录（取第一个**合格**的）。
    两者都找不到时返回 active 路径，让下游报出清晰的「目录/文件不存在」错误，
    而不是在这里静默吞掉。

    Args:
        spec_name: spec 目录名，例如 ``"formula-runtime-convergence"``。
        require_files: 候选目录必须存在的相对文件名。省略时只要目录存在即合格
            （向后兼容）。

            🔴 实战踩到：active 目录可能是只落了一个产物文件的**空壳**，真正的三件套
            已经归档。只按「目录存在」选 active 会读不到文件而误红。
        require_matches: ``{相对文件名: (正则, ...)}``。候选目录必须让**每个**正则在
            对应文件里命中（``re.M``）才算合格。用于区分**同名 spec 的不同文档形态**，
            见模块 docstring。
        repo_root: 覆盖仓库根（便于测试）。

    Returns:
        解析到的 spec 目录 Path。
    """
    root = specs_root(repo_root)

    def qualifies(candidate: Path) -> bool:
        if not candidate.exists():
            return False
        if require_files and not all((candidate / name).exists() for name in require_files):
            return False
        for rel, patterns in (require_matches or {}).items():
            target = candidate / rel
            if not target.is_file():
                return False
            text = target.read_text(encoding="utf-8", errors="replace")
            if not all(re.search(pattern, text, re.M) for pattern in patterns):
                return False
        return True

    active = root / spec_name
    if qualifies(active):
        return active

    archive_root = root / "_archive"
    if archive_root.exists():
        for candidate in sorted(archive_root.glob(f"*/{spec_name}")):
            if qualifies(candidate):
                return candidate

    return active
