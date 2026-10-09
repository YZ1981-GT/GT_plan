# -*- coding: utf-8 -*-
"""GF-P5：GC-1 —— representation pointer 按 `entry_id`，同码三条不互顶。

spec: `g-cycle-sync-foundation-and-first-canary` · Task 10　Requirements 2.2

同时是下游 `g4-g6-shared-workbook-three-entry-lanes` 的 **G46-P1 / P2 / P3** 的地基判据
（那份 spec 引用本裁决、不复述）。

═══ 复用 F2 的真构造 helper，不重造 ═══

`registration()` / `manifest_of()` / `install_contract()` / `StubAdapter` 等一套
「真跑 `WorkpaperSyncAdapterRegistry.register()`」的脚手架已在
`test_f2_p2_rg3_matcher_overlap.py` 里（F2 spec 的 P2）。F2 与 G4/G6 的形态**同型**
（一册多 entry 共用幻影码 ⇒ 靠互斥 `sheet_keys` 分域），抄一份会变成判据双真源：
改一处另一处不红。故**直接 import**。

═══ 为什么 BP-8 的真危险在 representation 层不在 matcher 层 ═══

slice BP-8 原文：「若 representation entry_id 只用 wp_code（或 wp_code_pattern），
G4 的三条与 G6 的三条会各自互相顶掉对方的 entry pointer / representation generation。」
matcher 层的重叠有 `MatcherOverlapError` 兜（RG-3，启动即拒）；
**pointer 层没有那道机械门** —— 三条 entry 若用 wp_code 作主键，第三条发布时会静静覆盖前两条。
⇒ 判据必须构造「三条先后发布」并证明前两条**仍在**（这是 BP-8 的真验收点）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import sqlalchemy as sa  # noqa: E402

from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402

# 🔴 复用 F2 spec 的真构造脚手架（见模块 docstring）。`contracts_dir` 是 fixture，
#    pytest 不会跨模块自动发现 ⇒ 显式 import 后在本模块用同名 fixture 转发。
from tests.workpaper_sync.test_f2_p2_rg3_matcher_overlap import (  # noqa: E402
    contracts_dir as _f2_contracts_dir,
    install_contract,
    manifest_entry,
    manifest_of,
    registration,
    xlsx_payload,
)

contracts_dir = _f2_contracts_dir


# ═══════════════════════════════════════════════════════════════════════════
# G4 / G6 的六条 entry（slice `independent_entries` + design §受管区清单）
# ═══════════════════════════════════════════════════════════════════════════

#: 🔴 三条共用**一个** `wp_code_pattern`（幻影码），靠互斥 `sheet_keys` 分域。
G4B = frozenset({"G4B"})
G6O = frozenset({"G6O"})

#: (entry_id, adapter_id, sheet_keys) —— sheet_keys 取 design 的受管区 sheet_key。
G4_LANES: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("xlsx/gt-g4-bond-investment-main", "g4.bond_main", frozenset({"g402-managed"})),
    ("xlsx/gt-g4-bond-investment-sppi", "g4.sppi_inventory", frozenset({"g407-managed"})),
    ("xlsx/gt-g4-bond-investment-ecl", "g4.ecl_stage", frozenset({"g409-managed"})),
)
G6_LANES: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("xlsx/gt-g6-other-bond-main", "g6.other_bond_main", frozenset({"g602-managed"})),
    ("xlsx/gt-g6-other-bond-sppi", "g6.sppi_fair_value", frozenset({"g605-managed"})),
    (
        "xlsx/gt-g6-other-bond-investment-ecl",
        "g6.ecl_stage",
        frozenset({"g611-managed"}),
    ),
)

GROUPS = {"G4": (G4B, G4_LANES), "G6": (G6O, G6_LANES)}


def _registry_with(group: str):
    """真构造 registry，manifest 里放该组三条 entry。"""
    _, lanes = GROUPS[group]
    return RG.WorkpaperSyncAdapterRegistry(
        manifest=manifest_of(*(manifest_entry(e) for e, _, _ in lanes))
    )


class TestGfP5Gc1PointerByEntryId:
    """Validates: 2.2"""

    @pytest.mark.parametrize("group", sorted(GROUPS))
    def test_three_same_code_entries_register_and_resolve_independently(
        self, group: str, contracts_dir: Path
    ) -> None:
        """🔴 BP-8 真验收点：三条同码 entry **依次**注册，第三条注册后前两条仍可解析。

        「依次」不是形式 —— 只验前两条会漏掉「第三条顶掉前两条」这一形态。
        每注册一条就重新解析**已注册的全部**，任一条被顶掉即打红。
        """
        wp_codes, lanes = GROUPS[group]
        registry = _registry_with(group)
        done: list[tuple[str, str]] = []
        for entry_id, adapter_id, sheet_keys in lanes:
            contract = install_contract(contracts_dir, xlsx_payload(adapter_id))
            registry.register(
                registration(
                    contract=contract,
                    entry_id=entry_id,
                    adapter_id=adapter_id,
                    wp_codes=wp_codes,
                    sheet_keys=sheet_keys,
                )
            )
            done.append((entry_id, adapter_id))
            for eid, aid in done:
                got = registry.resolve_for_entry(eid)
                assert got.adapter_id == aid, (
                    f"注册 {adapter_id} 后，{eid} 解析到 {got.adapter_id!r}（应为 {aid!r}）"
                    " ⇒ pointer 被同码 entry 顶掉了（BP-8）"
                )
        # `registrations` 是**方法**不是 property（registry.py:615）
        assert len(registry.registrations()) == 3, (
            f"三条同码 entry 注册后 registry 只剩 {len(registry.registrations())} 条"
        )

    @pytest.mark.parametrize("group", sorted(GROUPS))
    def test_sheet_keys_are_pairwise_disjoint(self, group: str) -> None:
        """三条的 `sheet_keys` 两两不相交，且 `overlaps()` 返回空。"""
        wp_codes, lanes = GROUPS[group]
        matchers = {
            eid: RG.EntryMatcher(document_type="xlsx", wp_codes=wp_codes, sheet_keys=sk)
            for eid, _, sk in lanes
        }
        ids = sorted(matchers)
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                assert matchers[a].overlaps(matchers[b]) == (), (
                    f"{a} 与 {b} 的 matcher 域重叠: {matchers[a].overlaps(matchers[b])}"
                )
                assert not (matchers[a].sheet_keys & matchers[b].sheet_keys)

    @pytest.mark.parametrize("group", sorted(GROUPS))
    def test_mutation_pointer_by_wp_code_makes_them_collide(
        self, group: str, contracts_dir: Path
    ) -> None:
        """变异：pointer 改用 wp_code（= `sheet_keys` 置空，匹配域退化为整册）⇒ 必红。

        这是「按 wp_code 做 pointer」在 matcher 层的等价表达：域退化成整册后，
        同码第二条一注册就撞 `MatcherOverlapError`。
        """
        wp_codes, lanes = GROUPS[group]
        registry = _registry_with(group)
        first_e, first_a, _ = lanes[0]
        second_e, second_a, _ = lanes[1]
        c1 = install_contract(contracts_dir, xlsx_payload(first_a))
        c2 = install_contract(contracts_dir, xlsx_payload(second_a))
        registry.register(
            registration(
                contract=c1,
                entry_id=first_e,
                adapter_id=first_a,
                wp_codes=wp_codes,
                sheet_keys=frozenset(),  # 退化：整册
            )
        )
        with pytest.raises(RG.MatcherOverlapError, match="重叠"):
            registry.register(
                registration(
                    contract=c2,
                    entry_id=second_e,
                    adapter_id=second_a,
                    wp_codes=wp_codes,
                    sheet_keys=frozenset(),
                )
            )

    def test_g4_and_g6_do_not_collide_with_each_other(self, contracts_dir: Path) -> None:
        """两组之间不冲突（不同幻影码）—— 否则「分域」这个解法本身不成立。"""
        all_lanes = [*G4_LANES, *G6_LANES]
        registry = RG.WorkpaperSyncAdapterRegistry(
            manifest=manifest_of(*(manifest_entry(e) for e, _, _ in all_lanes))
        )
        for group, (wp_codes, lanes) in GROUPS.items():
            for entry_id, adapter_id, sheet_keys in lanes:
                contract = install_contract(contracts_dir, xlsx_payload(adapter_id))
                registry.register(
                    registration(
                        contract=contract,
                        entry_id=entry_id,
                        adapter_id=adapter_id,
                        wp_codes=wp_codes,
                        sheet_keys=sheet_keys,
                    )
                )
        assert len(registry.registrations()) == 6
        for entry_id, adapter_id, _ in all_lanes:
            assert registry.resolve_for_entry(entry_id).adapter_id == adapter_id

    def test_entry_state_primary_key_is_entry_id_not_wp_code(self) -> None:
        """🔴 GC-1 的另一半：`working_paper_sync_entry_state` 的主键/唯一键是 `entry_id`。

        判据读 ORM 定义（不是散文）—— 若主键含 wp_code 或只按 wp 维度唯一，
        同码三条会互相 upsert 掉。
        """
        from app.models import workpaper_sync_models as M  # type: ignore

        state = next(
            (
                obj
                for name, obj in vars(M).items()
                if hasattr(obj, "__tablename__")
                and getattr(obj, "__tablename__", "") == "working_paper_sync_entry_state"
            ),
            None,
        )
        assert state is not None, (
            "找不到 working_paper_sync_entry_state 的 ORM ⇒ GC-1 的 pointer 主键无从核"
        )
        cols = {c.name for c in state.__table__.columns}
        assert "entry_id" in cols, f"entry_state 没有 entry_id 列: {sorted(cols)}"

        # 🔴 只看**主键 + 唯一约束 + 唯一索引**。
        #    不能遍历 `__table__.constraints` 的全部 —— 那里还有 `ForeignKeyConstraint`
        #    与 `CheckConstraint`，它们也有 `.columns`。本轮实测踩过一次：
        #    `wp_id` 的外键约束被当成「只按 wp_id 唯一」，判出一个**并不存在**的 BP-8 缺陷
        #    （真实 ORM 是复合主键 `(wp_id, entry_id)`，完全正确）。
        pk = frozenset(c.name for c in state.__table__.primary_key.columns)
        uniques: list[frozenset[str]] = [pk]
        for con in state.__table__.constraints:
            if isinstance(con, sa.UniqueConstraint):
                uniques.append(frozenset(c.name for c in con.columns))
        for idx in state.__table__.indexes:
            if idx.unique:
                uniques.append(frozenset(c.name for c in idx.columns))

        assert "entry_id" in pk, (
            f"entry_state 的主键是 {sorted(pk)}，**不含** entry_id ⇒ "
            "同码三条 entry 的 current representation pointer 会互相 upsert 掉（BP-8）"
        )
        assert pk == frozenset({"wp_id", "entry_id"}), (
            f"主键实测 {sorted(pk)}，基线是复合键 (wp_id, entry_id)。"
            "主键收窄到 wp_id 即 BP-8 成真；放宽也要复核 pointer 语义"
        )
        bad = [sorted(u) for u in uniques if "entry_id" not in u]
        assert not bad, (
            f"存在**不含** entry_id 的唯一约束/唯一索引: {bad} ⇒ pointer 会按 wp 维度收敛"
        )

    def test_reverse_self_check_fk_constraints_are_not_counted_as_unique(self) -> None:
        """反向自检：`wp_id` 上确实有外键约束 —— 证明上一条必须过滤 FK，不是多余的防御。"""
        from app.models import workpaper_sync_models as M  # type: ignore

        state = M.WorkpaperSyncEntryState
        fks = [
            frozenset(c.name for c in con.columns)
            for con in state.__table__.constraints
            if isinstance(con, sa.ForeignKeyConstraint)
        ]
        assert frozenset({"wp_id"}) in fks, (
            f"wp_id 上没有单列外键（实测 {[sorted(f) for f in fks]}）⇒ "
            "上一条判据的「必须过滤 FK」不再有实证基础，注释须改"
        )
