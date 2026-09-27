# -*- coding: utf-8 -*-
"""HF-P4 / HC-4：主表键必须**解析模板拼接**后再比对。

spec: `h-cycle-sync-foundation-and-first-canary`（共同裁决 HC-4）

═══ 为什么从 `test_h_foundation_hc_guards.py` 拆出来 ═══════════════════════════

HC-4 这族判据在 H5 接桥后长了一层（受管清单排除面 + 声明处计数），把母文件顶过了
行数门禁基线。**拆文件而非上调基线** —— 基线上调是「打磨让文件变大」，与门禁的意图相反。

拆分边界取 HC 号（一份文件一条共同裁决），不按「新增/既有」切 —— 后者会让同一条裁决的
判据散在两处，改动时只改到一半。

═══ 这族判据在守什么 ═══════════════════════════════════════════════════════════

H 循环有一个键是**拼接**出来的：`useH5Detail.ts` 里 `ITEM_PREFIX = 'H5-2'`，真键由
`${ITEM_PREFIX}-rows` 在运行时拼出 ⇒ 按值 grep `H5-2-rows` 的字面量**零命中**。

规划期 slice 因为只做了字面量 grep，把这条记成了「孤儿键缺陷」。它不是缺陷，是
守卫的错法。所以这里的判据是**双向**的：
  · 每个主表键都必须能解析出命中（含拼接分支）；
  · 去掉拼接分支时 `H5-2-rows` 必须变成零命中（变异判据，证明分支真的在起作用）。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from tests.workpaper_sync import h_cycle_facts as F  # noqa: E402


class TestHfP4PrimaryKeys:
    """HC-4：键字面量守卫必须带拼接解析分支，否则 `H5-2-rows` 必假红。"""

    @pytest.mark.parametrize("label,key", sorted(F.H_PRIMARY_KEYS.items()))
    def test_every_primary_key_resolves(self, label: str, key: str) -> None:
        hits = F.resolve_item_key_hits(key)
        assert hits.resolved, f"{label} 的主表键 {key} 在生产源码里零命中"

    def test_h5_primary_key_is_literal_absent_and_only_resolves_via_concat(self) -> None:
        """🔴 实测不一致第 4 条：`H5-2-rows` 字面量在**运行时载体**里零命中，语义正确不是缺陷。

        🔴 H5 接桥后，解析出来的真键被登记进 `sync/hManagedSheets.ts`（受管清单 ——
        后端 parity 守护逐字比对的对象）。那是**声明**不是第二个运行时来源：该文件零
        读写形态，`F.assert_declaration_only_surface()` 每次现场核验。
        判据因此分两层：①声明清单里**恰有**这一处登记；②运行时载体里仍然零字面量、
        只能经 `${ITEM_PREFIX}-rows` 拼接解析出来。
        """
        F.assert_declaration_only_surface()
        hits = F.resolve_item_key_hits("H5-2-rows")
        assert hits.literal == (), (
            f"H5-2-rows 在运行时载体里应零字面量，实测 {hits.literal}"
        )
        assert hits.concatenated, "拼接解析分支必须命中"
        assert any("useH5Detail.ts" in rel for rel in hits.concatenated), hits.concatenated
        # ② 声明清单里恰有一处 —— 少了后端 parity 会红，多了说明有人另抄了一份
        manifest = next(
            f for f in F.frontend_files() if f.rel in F.DECLARATION_ONLY_SURFACES
        )
        assert manifest.count("H5-2-rows") == 1, (
            f"受管清单里 H5-2-rows 应恰 1 处登记，实测 {manifest.count('H5-2-rows')}"
        )

    def test_h5_item_prefix_constant_value_is_h5_2(self) -> None:
        """拼接来源是 `useH5Detail.ts` 的 `ITEM_PREFIX`，实值 `H5-2`（按值取，不推演）。"""
        f = next(x for x in F.frontend_files() if x.rel.endswith("composables/useH5Detail.ts"))
        resolved = F.template_concat_keys(f)
        assert resolved.get("H5-2-rows") == "ITEM_PREFIX", resolved

    def test_dropping_the_concat_branch_would_false_red(self) -> None:
        """变异判据：只做字面量 grep ⇒ `H5-2-rows` 判零命中（正是 slice 的错法）。"""
        literal_only = [
            k for k in F.H_PRIMARY_KEYS.values() if not F.resolve_item_key_hits(k).literal
        ]
        assert literal_only == ["H5-2-rows"], literal_only

    def test_h10_identity_field_is_id_not_row_id(self) -> None:
        """HC-4 第 4 条：`H10-detail-rows` 身份字段是 `id`，且行可增删 ⇒ 非模板固定行族。"""
        text = (F.COMPOSABLES / "useH10Detail.ts").read_text(encoding="utf-8", errors="replace")
        assert "addRow" in text and "removeRow" in text
        assert re.search(r"\bid\s*:\s*raw\.id\s*\?\?", text), "应是 `id: raw.id ?? generateId()`"
        assert not re.search(r"rowId\s*:\s*raw\.rowId", text), "H10 不用 rowId 作身份"
