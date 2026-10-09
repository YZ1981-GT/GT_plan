# -*- coding: utf-8 -*-
r"""HF-P9 / HC-9 猜键回退链（BP-12）—— 从 `test_h_foundation_hc_guards.py` 抽出的伴生文件。

spec: `h-cycle-sync-foundation-and-first-canary`（HC-9）+
`h2-h6-h10-pilot-cross-reference-lanes`（Task 3 收口）

═══ 为什么独立成文 ═══════════════════════════════════════════════════════════

lane3 Task 3 把 BP-12 从「冻结缺陷」推进到「断言已修」，判据从 2 条长到 6 条
（三站点各两条 parametrize + 清册棘轮 + 翻面后的反向断言）。继续留在
`test_h_foundation_hc_guards.py` 里会把那个文件顶过行数门禁，而门禁给的首选处置正是
「抽伴生模块」。本仓已有同范式先例：HC-4 独立成
`test_h_foundation_hc4_key_resolution.py`。

🔴 **本文件是逐行搬运，判据一字未改**（搬运本身不得顺手改判据 —— 那会让「行数超限」
这件小事掩盖一次真实的判据变更）。
"""
from __future__ import annotations

import re

import pytest

from tests.workpaper_sync import h_cycle_facts as F


# ═══════════════════════════════════════════════════════════════════════════
# HF-P9　HC-9 猜键回退链（BP-12）
# ═══════════════════════════════════════════════════════════════════════════


#: 🔴 **BP-12 收敛轨迹：4 处 → 3 处 → 1 处**。
#:
#: * 第一轮（foundation）：`h10RelatedH6Pull.ts` 三键 → 单一权威键 `H6-2-rows`；
#: * 第二轮（lane3 Task 3 收口，2026-09-30）：另两条 **H↔H 内部**链一并收敛 ——
#:   `h6H10Pull.ts` 四键（**全部零生产**）→ `H10-1-adjudicated-amount`；
#:   `useH6Check.ts` 四键（前 3 个零生产且**排在真键前面**）→ `H10-detail-rows`。
#:
#: 只剩 `h3MortgageReconcile.ts` 一条：它的两个键指向 **L 循环**，而 L1 侧从未写过任何
#: 质押行键（现算 L1 生产键只有 `L1-2-rows` / `L1-chk-conclusion` /
#: `L1-disclosure-listed-transfer-in`）⇒ **不是改键能修的**，缺的是上游生产者本身。
#: 保留登记而不改键：改成一个同样没人写的键只会把死路换个名字。
EXPECTED_FALLBACK_CHAINS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # 🔴 跨循环到 L1，**两键全部**零生产 ⇒ H3 抵押核对恒取不到；缺口在 L 循环侧
    "components/workpaper/composables/h3MortgageReconcile.ts#L75": (
        ("L1-L1-8-rows", "L1-pledge-rows"),
        ("L1-L1-8-rows", "L1-pledge-rows"),
    ),
}

#: lane3 Task 3 收敛后的**单一权威键**：站点 → (键, 载荷列)。
#: 判据双向：站点里必须出现该键、且**不得**再出现被删掉的猜测键。
CONVERGED_SINGLE_KEY_SITES: dict[str, tuple[str, tuple[str, ...]]] = {
    "h10RelatedH6Pull.ts": ("H6-2-rows", ("H6-detail-rows", "H6-clearing-rows")),
    "h6H10Pull.ts": (
        "H10-1-adjudicated-amount",
        ("H10-1-audited-total", "H10-adj-total", "H10-1-end-audited", "H10-1-disposal-gain-loss", "H10-1-rows"),
    ),
    "useH6Check.ts": (
        "H10-detail-rows",
        ("H10-2-rows", "H10-rows", "H10-1-gain-loss-total"),
    ),
}


class TestHfP9GuessedKeyFallbackChain:
    """HC-9：多键回退链里每个键都必须「H 侧生产命中 > 0」，否则是猜测键。"""

    def test_h_cycle_fallback_chain_inventory_is_one_after_lane3_convergence(self) -> None:
        """🔴 4 → 3 → **1**：仅剩跨到 L 循环的 `h3MortgageReconcile.ts`（缺上游生产者）。

        这条判据是**只减不增**的棘轮：新增任何一条多键回退链都会让 `sorted` 不等而打红。
        """
        chains = F.multi_key_fallback_chains()
        assert sorted(chains) == sorted(EXPECTED_FALLBACK_CHAINS), sorted(chains)
        for site, (all_keys, _guessed) in EXPECTED_FALLBACK_CHAINS.items():
            assert chains[site] == all_keys, (site, chains[site])

    @pytest.mark.parametrize("fname", sorted(CONVERGED_SINGLE_KEY_SITES))
    def test_converged_sites_use_exactly_one_authoritative_key(self, fname: str) -> None:
        """三个已收敛站点：权威键在、猜测键**一个都不许剩**（含注释外的可执行语句）。

        🔴 反向断言不可省：只查「权威键在」的话，把猜测键留着当「兜底」也能过 ——
        而那正是缺陷形态（假键排在真键前面就会抢先生效）。
        """
        key, removed = CONVERGED_SINGLE_KEY_SITES[fname]
        text = (F.COMPOSABLES / fname).read_text(encoding="utf-8", errors="replace")
        assert key in text, f"{fname}: 权威键 {key} 不在文件里"
        for gone in removed:
            for line in text.splitlines():
                s = line.strip()
                if gone not in s:
                    continue
                assert s.startswith("//") or s.startswith("*"), (
                    f"{fname}: 已废弃的猜测键 {gone} 仍在可执行语句里：{s[:120]}"
                )

    @pytest.mark.parametrize("fname", sorted(CONVERGED_SINGLE_KEY_SITES))
    def test_converged_authoritative_keys_really_have_a_producer(self, fname: str) -> None:
        """收敛到的键必须**真有生产者**，否则只是把死路换了个名字。"""
        key, _removed = CONVERGED_SINGLE_KEY_SITES[fname]
        owners = F.producers_in_owning_entry_scope(key)
        assert owners, f"{fname}: 收敛到 {key}，但它在自己 entry 侧零生产"

    @pytest.mark.parametrize("site", sorted(EXPECTED_FALLBACK_CHAINS))
    def test_guessed_keys_in_every_chain_have_zero_producer(self, site: str) -> None:
        """判定口径 = 「**该键所属 entry 的作业面**里有没有生产者」。

        🔴 用「消费方文件之外还有没有命中」会误判：`H6-detail-rows` 在
        `h10RelatedH6Pull.ts` 与 `useH10CrossSheet.ts` 两处出现，但两处都是 **H10 侧**消费方。
        """
        all_keys, guessed = EXPECTED_FALLBACK_CHAINS[site]
        for key in all_keys:
            owners = F.producers_in_owning_entry_scope(key)
            if key in guessed:
                assert owners == (), f"{key} 本应在自己 entry 侧零生产，实测 {owners}"
            else:
                assert owners, f"{key} 本应是权威键（自己 entry 侧有生产者），实测零生产"

    def test_h6_to_h10_reverse_pull_is_no_longer_dead(self) -> None:
        """🔴 本判据是前一版 `..._is_entirely_dead` 的**反面**（lane3 Task 3 收口后翻面）。

        原判据断言「4 键全零生产 ⇒ 恒落到『H10 暂无审定数』」。现在这条反向勾稽读的是
        真源 `H10-1-adjudicated-amount`，所以要断言的是三件事：
          ① 权威键在且**有生产者**；② 「暂无审定数」只作为 `null` 分支的文案保留
          （不是恒走的路径）；③ 载荷列取 `conclusion` 在前 —— 写入方存的就是它，
          顺序写反会恒读空，那会把这条链悄悄退回死路。
        """
        text = (F.COMPOSABLES / "h6H10Pull.ts").read_text(encoding="utf-8", errors="replace")
        assert "H10-1-adjudicated-amount" in text
        assert F.producers_in_owning_entry_scope("H10-1-adjudicated-amount")
        assert "H10 暂无审定数" in text, "键不存在时的文案应保留（fail-loud，不静默取 0）"
        m = re.search(r"item\.(conclusion|remark)\s*\?\?\s*item\.(conclusion|remark)", text)
        assert m and m.group(1) == "conclusion", (
            f"载荷列顺序必须 conclusion 优先，实测 {m.group(0) if m else '<未找到>'}"
        )

    def test_guessed_keys_are_gone_from_h10_after_bp12_fix(self) -> None:
        """🔴 BP-12 修复后 `H6-detail-rows` / `H6-clearing-rows` 在可执行代码里**零命中**。

        注释里的历史记录不影响运行时。
        """
        for key in F.H_GUESSED_KEYS:
            hits = F.resolve_item_key_hits(key)
            for rel in hits.production_files:
                text = next(f.text for f in F.frontend_files() if f.rel == rel)
                for line in text.splitlines():
                    stripped = line.strip()
                    if key in stripped:
                        assert stripped.startswith("//") or stripped.startswith("*"), (
                            f"{rel}: {key} 出现在可执行语句：{stripped[:120]}"
                        )

    def test_authoritative_key_is_documented_in_the_same_file(self) -> None:
        """同文件注释已写明真源是 `H6-2-rows` ⇒ 后两键是防御性猜测，不是历史别名。"""
        text = (F.COMPOSABLES / "h10RelatedH6Pull.ts").read_text(encoding="utf-8", errors="replace")
        assert "H6-2-rows" in text
        assert "checklist" in text.lower()
