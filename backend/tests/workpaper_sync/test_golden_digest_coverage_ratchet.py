# -*- coding: utf-8 -*-
r"""golden digest **覆盖面**棘轮 —— 「门是绿的」与「门在看这一家」是两回事。

起因（2026-09-30，H 循环翻 capability 前的前置审计）：
`check_sync_provider_golden_digest.py` 跑出来是
「✅ golden digest 零回归：161 个 digest 逐个不变（覆盖 24 家，**零跳过**）」，
但现算台账 `DELIVERED_PER_ENTRY_CONTRACTS` 有 **51 条 / 48 个 family** ——
也就是说**另外 24 个 family 从未进过基线**，门对它们恒绿，因为没有东西可比。

═══ 与既有判据的关系 ═══════════════════════════════════════════════════════════

脚本自己已经修过一次同类缺陷：f1 曾被 `[SKIP]` 吞掉（登记了 24 家、基线只有 23 家），
修法是「把 skip 当失败」+「已登记 provider 必须在基线里有条目」。
🔴 但那两条判据的分母都是 **`PROVIDERS` 本身** —— 「**压根没登记**」比「登记了被跳过」
更隐蔽：不会有 `[SKIP]`，不会有 stderr，连退出码都不受影响。
本文件补的就是这个分母之外的洞：拿**台账**（已交付的事实）去比 `PROVIDERS`（被看管的集合）。

═══ 为什么是棘轮而不是硬修 ═══════════════════════════════════════════════════

补齐 24 家需要为每家取真实 digest 基线，而 digest 的三段里有两段直接依赖
`excel_instrumentation.py` / 引擎层。现算工作树那一层有 **11 个文件被并发会话改动但未提交**
（`excel_instrumentation.py` +473 / `oo_to_html.py` −477 是一次进行中的搬迁重构）。
在脏树上取基线 = 把别人没写完的状态冻成「已验证」，正是本仓反复登记的假绿形态。
⇒ 本文件只把缺口**钉成会打红的事实**并禁止它变大；补齐由引擎重构落地后的专项轮次做。
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from tests.workpaper_sync import h_cycle_facts as F

_CHECK_SCRIPT = F.BACKEND / "scripts/check/check_sync_provider_golden_digest.py"
_MANIFEST = F.BACKEND / "data/workpaper_sync_entry_manifest.json"


def _load_registered_labels() -> tuple[str, ...]:
    """从检查脚本现读 `PROVIDERS`（它在 `scripts/check` 下，不是包，只能按路径加载）。"""
    spec = importlib.util.spec_from_file_location("_chk_golden_for_test", _CHECK_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return tuple(str(p[0]) for p in mod.PROVIDERS)


def _delivered_families() -> dict[str, tuple[str, ...]]:
    """台账 family（`contract_id` 的点号前缀）→ 该 family 下的 contract_id。"""
    from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )

    out: dict[str, list[str]] = {}
    for row in DELIVERED_PER_ENTRY_CONTRACTS:
        cid = str(row["contract_id"])
        out.setdefault(cid.split(".", 1)[0], []).append(cid)
    return {k: tuple(sorted(v)) for k, v in out.items()}


#: 🔴 **只许变短的棘轮**：已交付但尚未纳入 golden 零回归门的 family（2026-09-30 现算 24 个）。
#:
#: 每补齐一家就从这里删一行；**新增一行必须写明理由**，而且下面那条
#: `bidirectional` 不变量会独立把「带着缺口上线」拦下来。
_UNCOVERED_BY_GOLDEN_GATE: frozenset[str] = frozenset({
    # ── 已 bidirectional 却不在门内（见 test_no_bidirectional_entry_escapes…）──
    "g7",   # pilot_g7_two_level_dynamic —— pilot_* 命名，当初按 phase5_* 收录时漏了
    "h1",   # pilot_h1_grouped_dynamic  —— 同上
    # ── 其余 22 家：契约与 provider 已交付，capability 仍 single_onlyoffice ──
    "a51", "c2",
    "f2", "f3", "f4", "f5",
    "h2", "h3", "h4", "h5", "h6", "h7", "h8", "h10",
    "i1", "i2", "i3", "i4", "i5", "i6",
    "j1", "l1",
})

#: 🔴 当前**违反**「bidirectional ⟹ 在门内」的 family。两条都是早期 pilot。
#: 这个集合**只许变空**：任何新 entry 翻 bidirectional 之前必须先进 golden 门。
_BIDIRECTIONAL_BUT_UNCOVERED: frozenset[str] = frozenset({"g7", "h1"})


@pytest.fixture(scope="module")
def registered() -> tuple[str, ...]:
    return _load_registered_labels()


@pytest.fixture(scope="module")
def delivered() -> dict[str, tuple[str, ...]]:
    return _delivered_families()


def test_registered_labels_are_a_subset_of_delivered_families(
    registered: tuple[str, ...], delivered: dict[str, tuple[str, ...]]
) -> None:
    """反向：门里不该有台账上没有的 family（否则基线在守一个已下线的东西）。"""
    extra = sorted(set(registered) - set(delivered))
    assert extra == [], f"PROVIDERS 登记了台账里不存在的 family：{extra}"


def test_coverage_gap_matches_the_ratchet_exactly(
    registered: tuple[str, ...], delivered: dict[str, tuple[str, ...]]
) -> None:
    """🔴 核心判据：台账 − 登记表 **恰好等于**棘轮登记的缺口集合。

    两个方向都断言，缺一个方向就会 fail-open：
      · 只查「缺口 ⊆ 棘轮」⇒ 新交付一家而忘了登记也不会红（洞变大却没人知道）；
      · 只查「棘轮 ⊆ 缺口」⇒ 补齐了一家而忘了从棘轮删掉也不会红（棘轮失去意义）。
    """
    gap = set(delivered) - set(registered)
    newly_uncovered = sorted(gap - _UNCOVERED_BY_GOLDEN_GATE)
    stale_entries = sorted(_UNCOVERED_BY_GOLDEN_GATE - gap)
    assert newly_uncovered == [], (
        f"新增了未纳入 golden 零回归门的已交付 family：{newly_uncovered} —— "
        "要么把它加进 check_sync_provider_golden_digest.PROVIDERS 并取基线，"
        "要么加进 _UNCOVERED_BY_GOLDEN_GATE 并写明为什么现在不能取"
    )
    assert stale_entries == [], (
        f"这些 family 已经进门了，但棘轮里还挂着：{stale_entries} —— 请从 "
        "_UNCOVERED_BY_GOLDEN_GATE 删掉（棘轮只许变短）"
    )


def test_gap_is_half_the_delivered_surface_and_that_is_computed_not_asserted(
    registered: tuple[str, ...], delivered: dict[str, tuple[str, ...]]
) -> None:
    """覆盖率**现算**，不写死百分比。

    🔴 不设「覆盖率 ≥ X%」这种阈值判据：阈值允许静默退化，而且 X 是拍脑袋数字。
    这里只断言「登记数 + 缺口数 == 台账 family 数」这条**记账等式**，
    任一侧漏算都会立刻不平（口径同 `register_from_manifest` 的三集合实录思路）。
    """
    gap = set(delivered) - set(registered)
    assert len(registered) + len(gap) == len(delivered), (
        f"记账不平：登记 {len(registered)} + 缺口 {len(gap)} != 台账 family {len(delivered)}"
    )


def _bidirectional_families() -> set[str]:
    """manifest 里 `capability == bidirectional` 的 entry → 其 adapter_id 的 family。

    🔴 **逐条扫 `entries`，不读 `stats`**：HEAD 上 `stats.capability_counts.bidirectional`
    写 4 而逐条扫是 5（漏了 d1）—— 那个字段比它自己的 entries 还旧。本轮就栽在读 stats 上。
    """
    data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    fams: set[str] = set()
    for e in data["entries"]:
        if e.get("capability") != "bidirectional":
            continue
        adapter = str(e.get("adapter_id") or "")
        m = re.match(r"^([a-z]\d*)\.", adapter)
        if m:
            fams.add(m.group(1))
    return fams


def test_no_bidirectional_entry_escapes_the_golden_gate_beyond_the_two_pilots(
    registered: tuple[str, ...]
) -> None:
    """🔴 真正要守的不变量：**`capability=bidirectional` ⟹ 该 family 在 golden 门内**。

    现状有两个历史违反（`g7` / `h1`，都是 `pilot_*` 命名的早期 pilot）。本判据把它们钉死，
    并让**第三个**违反立刻打红 —— 也就是：任何 entry 想翻 bidirectional，
    必须先把它的 provider 纳入 golden 零回归门。这正是 H 循环翻门前置六项里的第⑤项，
    此前只写在 spec 文字里、没有任何机制保证。

    判据对「工作树 vs HEAD」稳定：HEAD 的 bidirectional 是 {d1,d2,d4,g7,h1}、
    工作树是那 5 条 + G 循环 13 条，而新增的 13 条**全都已在门内** ⇒ 两种状态下
    违反集合都恰好是 {g7, h1}。
    """
    violations = _bidirectional_families() - set(registered)
    assert violations == set(_BIDIRECTIONAL_BUT_UNCOVERED), (
        f"bidirectional 但不在 golden 门内的 family = {sorted(violations)}，"
        f"登记的历史违反 = {sorted(_BIDIRECTIONAL_BUT_UNCOVERED)}。"
        "新增违反必须先把 provider 纳入 PROVIDERS 并取基线；"
        "修掉历史违反后请同步收缩 _BIDIRECTIONAL_BUT_UNCOVERED（它只许变空）"
    )


def test_the_two_known_violations_really_are_pilot_named_modules() -> None:
    """豁免必须是**可伪证的声明**，不能只留一句理由文本。

    棘轮里给 `g7` / `h1` 写的理由是「`pilot_*` 命名，按 `phase5_*` 收录时漏了」——
    这里就去台账里核实它们的 `provider_module` 真的是 `pilot_*`。
    理由若不成立（比如哪天改名成 `phase5_*` 了），这条判据会红，豁免也就该重新评估。
    """
    from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )

    by_family = {
        str(r["contract_id"]).split(".", 1)[0]: str(r.get("provider_module") or "")
        for r in DELIVERED_PER_ENTRY_CONTRACTS
    }
    for fam in sorted(_BIDIRECTIONAL_BUT_UNCOVERED):
        mod = by_family.get(fam, "")
        assert mod, f"{fam} 不在台账里，豁免理由无从核实"
        assert ".pilot_" in mod, (
            f"{fam} 的 provider_module 是 {mod!r}，已不是 pilot_* 命名 ⇒ "
            "「当初按 phase5_* 收录时漏了」这条豁免理由不再成立，请纳入 golden 门"
        )
