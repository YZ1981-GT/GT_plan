"""AC 1.4 通知真源（`workpaperEntrySyncNotice.ts`）的**单一解析器**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure

为什么单独成模块
────────────────
`SYNC_ADAPTER_REGISTERED_ENTRY_IDS` 是 7+ 个 per-cycle 守卫共读的同一个事实。2026-09-22
真源从手写数组改成

    export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] =
      Object.freeze(
        WORKPAPER_SYNC_MANIFEST.filter((e) => e.capability === 'bidirectional').map(
          (e) => e.entryId,
        ),
      )

之后，各守卫里那份假定字面量的正则 `=\\s*\\[` 一律匹配不到，报的却是
**「找不到 SYNC_ADAPTER_REGISTERED_ENTRY_IDS 的声明」**—— 把「形态变了」误报成
「东西没了」，恰是这条判据最该区分的两件事。F/G/H 三个 cycle 的守卫都栽在这里。

所以解析逻辑收敛到这里一份：先无偏取出**完整初始化表达式**（括号配平、跨行），
再按形态分派（字面量数组 / manifest 现算），两条路径都返回**具体 id 列表**。
它**不退化成「存在即通过」**：声明整体缺失仍断言失败；现算形态的 filter 谓词或
`.map(e => e.entryId)` 认不出来也断言失败（fail closed）。

TODO(单一真源收尾)：`test_task46_d_cycle_migration.py` / `test_task52_j_cycle_migration.py`
/ `test_task56_n_cycle_migration.py` 各自还留着一份同形态的本地实现（它们当前是绿的）。
把那三份换成本模块即可把 4 份收成 1 份 —— 本轮不动绿测试，登记在
`docs/operations/evidence/suite-triage/manifest-slice-drift.md`。
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
SYNC_DIR = (
    ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
)
#: AC 1.4 的 UI 义务落点（Task 46 收口新建的单一真源）。
NOTICE_MODULE = SYNC_DIR / "workpaperEntrySyncNotice.ts"
#: `SYNC_ADAPTER_REGISTERED_ENTRY_IDS` 现算形态所依赖的 generated manifest（真源之真源）。
SYNC_MANIFEST_TS = SYNC_DIR / "workpaperSyncManifest.generated.ts"

CONST_NAME = "SYNC_ADAPTER_REGISTERED_ENTRY_IDS"


def strip_ts_comments(source: str) -> str:
    """剥掉 TS/Vue 注释 —— 说明文字不得充当判据证据（不吞字符串字面量）。"""
    source = re.sub(r"/\*[\s\S]*?\*/", "", source)
    source = re.sub(r"(?m)^\s*//.*$", "", source)
    source = re.sub(r"(?m)//[^\n\"'`]*$", "", source)
    source = re.sub(r"<!--[\s\S]*?-->", "", source)
    return source


def initializer_of(source: str, const_name: str) -> str:
    """取 `const_name = ...` 的**完整初始化表达式**（括号配平，跨行）。

    🔴 不能用 `=\\s*\\[` 这种「假定字面量」的正则：真源可以是字面量数组，也可以是现算
    表达式，形态一变正则就 `None`。这里先无偏取出表达式，再由调用方按形态解析。
    """
    anchor = re.search(re.escape(const_name) + r"\b[^=\n]*=", source)
    if not anchor:
        return ""
    depth = 0
    taken: list[str] = []
    for ch in source[anchor.end():]:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "\n" and depth <= 0 and taken and taken[-1].strip():
            break
        taken.append(ch)
    return "".join(taken)


def generated_manifest_entries(source: str) -> list[dict]:
    """从 `workpaperSyncManifest.generated.ts` 取出 entry 数组（合法 JSON 字面量）。"""
    block = re.search(
        r"WORKPAPER_SYNC_MANIFEST\s*(?::[^=]*)?=\s*(\[[\s\S]*?\n\])\s*as const", source
    )
    assert block, "读不出 WORKPAPER_SYNC_MANIFEST 数组 ⇒ 现算形态无从复算"
    return json.loads(block.group(1))


def registered_entry_ids() -> list[str]:
    """解析「已注册 adapter」集合：字面量数组 → 取 id；manifest 现算 → 同谓词复算。"""
    init = initializer_of(
        strip_ts_comments(NOTICE_MODULE.read_text(encoding="utf-8")), CONST_NAME
    )
    assert init.strip(), f"找不到 {CONST_NAME} 的声明"
    if "WORKPAPER_SYNC_MANIFEST" in init:
        predicate = re.search(
            r"WORKPAPER_SYNC_MANIFEST\s*\.filter\(\s*\(?\s*(\w+)\s*\)?\s*=>"
            r"\s*\1\.capability\s*===\s*['\"]([^'\"]+)['\"]",
            init,
        )
        assert predicate, f"现算形态的 filter 谓词无法识别：{init.strip()[:200]!r}"
        assert re.search(r"\.map\(\s*\n?\s*\(?\s*(\w+)\s*\)?\s*=>\s*\1\.entryId", init), (
            f"现算形态没有 map 到 entryId：{init.strip()[:200]!r}"
        )
        wanted = predicate.group(2)
        entries = generated_manifest_entries(SYNC_MANIFEST_TS.read_text(encoding="utf-8"))
        return sorted({e["entryId"] for e in entries if e["capability"] == wanted})
    literal = re.search(r"\[([\s\S]*)\]", init)
    assert literal, f"既不是现算也不是字面量数组：{init.strip()[:200]!r}"
    return sorted(set(re.findall(r"['\"]([^'\"]+)['\"]", literal.group(1))))
