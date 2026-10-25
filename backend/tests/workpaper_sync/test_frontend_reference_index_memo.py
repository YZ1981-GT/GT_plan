# -*- coding: utf-8 -*-
"""入边索引记忆化守卫（spec startup-prewarm-event-loop-unblocking Requirement 3）。

记忆化只改「解析几次」，不改「解析出什么」：产物必须与逐条解析的参考实现逐字段相等。
合成前端树刻意放进四种会让「键太粗」出错的形态：
* 同名相对 import（``./Widget.vue``）在两个目录指向两个不同文件 —— 键不含 importer 目录就会串；
* 同一目标分别经别名 ``@/`` 与相对路径引用；
* 目录 import 解析到 ``index.ts``；
* 指向不存在文件的 import（必须仍然不计入）。
真实前端树上的等价性另由一次性探针实测（tasks.md 记证据），这里不扫真实树（冷算数秒）。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.workpaper_sync import entry_source_facts as F


def _reference(src: Path) -> F.FrontendReferenceIndex:
    """改前实现（逐条 `_resolve_import` + `_relative`，无记忆化）。"""
    imports: dict[str, set[str]] = {}
    tags: dict[str, set[str]] = {}
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [n for n in dirnames if n.lower() not in F._EXCLUDED_SEGMENTS]
        for name in filenames:
            path = Path(dirpath) / name
            if not F._is_production_source(path):
                continue
            scanned += 1
            relative = F._relative(path)
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in F._IMPORT_RE.finditer(text):
                target = F._resolve_import(path, match.group(1))
                if target is not None:
                    imports.setdefault(F._relative(target), set()).add(relative)
            for match in F._TAG_RE.finditer(text):
                tags.setdefault(match.group(1), set()).add(relative)
    return F.FrontendReferenceIndex(
        scanned_files=scanned,
        imports={k: tuple(sorted(v)) for k, v in imports.items()},
        tags={k: tuple(sorted(v)) for k, v in tags.items()},
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def synthetic_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    src = repo / "audit-platform" / "frontend" / "src"
    _write(src / "a" / "Widget.vue", "<template><div/></template>\n")
    _write(src / "b" / "Widget.vue", "<template><span/></template>\n")
    _write(src / "a" / "HostA.vue",
           "<script setup>\nimport W from './Widget.vue'\nimport G from '../ghost/Missing.vue'\n</script>\n"
           "<template><Widget /></template>\n")
    _write(src / "b" / "HostB.vue",
           "<script setup>\nimport W from './Widget.vue'\nimport U from '@/utils'\n</script>\n")
    _write(src / "utils" / "index.ts", "export const x = 1\n")
    _write(src / "c" / "Page.vue",
           "<script setup>\nimport W from '@/a/Widget.vue'\nimport X from '../a/Widget.vue'\n"
           "import Y from './../a/Widget'\nimport U from '../utils'\nimport V from 'vue'\n</script>\n")
    _write(src / "c" / "__tests__" / "Page.spec.ts", "import W from '../../b/Widget.vue'\n")
    _write(src / "components.d.ts", "import W from './a/Widget.vue'\n")
    monkeypatch.setattr(F, "_REPO", repo)
    monkeypatch.setattr(F, "_FRONTEND_SRC", src)
    F.frontend_reference_index.cache_clear()
    yield src
    F.frontend_reference_index.cache_clear()


def test_memoized_index_equals_the_reference_algorithm(synthetic_tree: Path) -> None:
    got = F.frontend_reference_index()
    want = _reference(synthetic_tree)
    assert got.scanned_files == want.scanned_files
    assert dict(got.imports) == dict(want.imports)
    assert dict(got.tags) == dict(want.tags)


def test_same_relative_specifier_in_two_directories_stays_two_targets(synthetic_tree: Path) -> None:
    """键必须含 importer 目录：`./Widget.vue` 在 a/ 与 b/ 是两个文件。"""
    got = F.frontend_reference_index()
    prefix = "audit-platform/frontend/src/"
    assert got.imports[prefix + "a/Widget.vue"] == (prefix + "a/HostA.vue", prefix + "c/Page.vue")
    assert got.imports[prefix + "b/Widget.vue"] == (prefix + "b/HostB.vue",), (
        "b/Widget.vue 的入边被并到了 a/Widget.vue（记忆化键丢了 importer 目录）"
    )


def test_alias_relative_index_and_missing_targets(synthetic_tree: Path) -> None:
    got = F.frontend_reference_index()
    prefix = "audit-platform/frontend/src/"
    # 别名 + 目录 index 解析
    assert got.imports[prefix + "utils/index.ts"] == (prefix + "b/HostB.vue", prefix + "c/Page.vue")
    # 不存在的目标不计入；测试目录与 .d.ts 不是生产源码
    assert not any("ghost" in key for key in got.imports)
    assert got.scanned_files == 6
    for referrers in got.imports.values():
        assert not any("__tests__" in r or r.endswith(".d.ts") for r in referrers)


def test_memo_key_separates_kinds_and_importer_directories(tmp_path: Path) -> None:
    a = tmp_path / "a" / "Host.vue"
    b = tmp_path / "b" / "Host.vue"
    assert F._import_memo_key(a, "./W.vue") != F._import_memo_key(b, "./W.vue")
    assert F._import_memo_key(a, "@/W.vue")[0] == "alias"
    assert F._import_memo_key(a, "../W.vue")[0] == "relative"
    assert F._import_memo_key(a, "vue") is None
