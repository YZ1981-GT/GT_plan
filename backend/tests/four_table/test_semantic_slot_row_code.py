"""槽级 ``row_code`` 守卫 —— 修「备抵自成报表行 ⇒ 恒报假冲突」（平台级）。

背景（2026-08-08 真实库实证）
============================
:class:`SemanticAccountSpec` 只有**一个** ``row_code``（主槽的报表行），而
:func:`build_conflicts` 拿它的码集**逐槽**比对 ⇒ 「备抵在 ``report_config`` 里
自成一行」的循环恒报假冲突。G7 实测 8 个有 1511 数据的项目里 **7 个**恒亮::

    conflicts = [['provision', '1511', '1512']]

而主行 ``BS-024 长期股权投资 = TB('1511')`` 确实不引用 1512 —— 因为备抵有自己的行
``IMP-009 = TB('1512')``。旧 ``ReportLineAccountSpec`` 的 ``provision_row_code``
能表达这件事，语义解析器迁移时**丢失了该能力**（G7_SPEC 的 docstring 里一直写着
「备抵自成报表行 IMP-009」，只是没有字段承载）。

⚠️ 这是**告警疲劳型**缺陷：常亮假告警会让审计师忽略真冲突，而真冲突正是该机制
存在的理由（``report_config`` 已实证 6 处错码）。

修法（additive）
===============
1. :class:`SemanticAccountSlot` 加可选 ``row_code``（该槽自己的报表行，**仅**用于
   冲突检测的对照基准，**不参与定位** —— 层③本就对多槽规格禁用）；
2. :func:`build_conflicts` 加可选 ``slot_report_codes``，声明了自己 row_code 的槽
   用它比对；
3. :class:`ResolvedSlot` 加 ``report_row_code`` 下发（审计 UI 铁律：告警必须能追溯
   「与哪条报表行比对」）。

缺省 ``None`` / ``None`` ⇒ 行为逐字不变（零回归支点）。

Spec: g-cycle-extraction-mapping-and-disclosure-alignment（G7 全链调查衍生）
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from functools import lru_cache
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.four_table.d_cycle_specs import D1_SPEC, D2_SPEC, D6_SPEC
from app.services.four_table.g_cycle_specs import G4_SPEC, G7_SPEC
from app.services.four_table.h2_account_scope import H2_ACCOUNT_SPEC
from app.services.four_table.h3_account_scope import H3_ACCOUNT_SPEC
from app.services.four_table.h7_account_scope import H7_ACCOUNT_SPEC
from app.services.four_table.i_cycle_specs import I3_SPEC
from app.services.four_table.semantic_account_resolver import (
    RESOLVED_FROM_STANDARD_CHART,
    ResolvedSlot,
    SemanticAccountSlot,
    build_conflicts,
)

#: `backend/` 目录（`app/` 的父级）—— stale 检测要扫生产代码树。
#: 本文件在 `backend/tests/four_table/`，故上溯两级。
_ROOT = Path(__file__).resolve().parents[2]

# ─────────────────────────────────────────────────────────────────────────────
# 影响面登记（stale 检测：某 spec 声明了槽级 row_code 就必须从这里移出）
# ─────────────────────────────────────────────────────────────────────────────

#: 已声明槽级 row_code 的（spec 名, 槽键, row_code）—— 本轮落地范围
DECLARED_SLOT_ROW_CODES: dict[tuple[str, str], str] = {
    ("G4", "provision"): "IMP-008",
    ("G7", "provision"): "IMP-009",
    # ── 2026-08-12 落地（g7-column-alignment-… spec Task 14）─────────────────
    # 前三条**生产真接线**（逐个实证：各 2 处消费方 = per-cycle render +
    # `h0_book_amounts`，且都会流到 `resolve_semantic_accounts` ⇒ `build_conflicts`
    # 真的会对它们跑）⇒ 声明后**真的**消除了线上假告警。
    ("H2", "impairment"): "IMP-012",
    ("H3", "impairment"): "IMP-010",
    ("H7", "impairment"): "IMP-013",
    # D6 **不接线**（`d_cycle_specs` 模块 warning：D 类 7 个 render 走
    # `report_line_accounts` 路径；实证 `D6_SPEC` 的生产引用里 0 处调解析器）
    # ⇒ 此声明修的是**声明式文档的正确性**，不能说它消除了线上假告警。
    # 之所以仍然声明：D 类将来真接线时即刻生效，且让待办登记表能如实清空。
    ("D6", "provision"): "IMP-004",
}

#: 🔴 **已裁决「不声明」**的槽 —— 不是欠账，是有依据的处置。
#:
#: 与 :data:`PENDING_FALSE_CONFLICT_SPECS`（待办）的区别：待办是「该做还没做」，
#: 本表是「查清楚了，声明它解决不了问题或不该在此处声明」。两表必须互斥，
#: 且本表每条都配 **stale 检测**（前提一旦变化即打红，逼迫重新裁决而非永久豁免）。
#:
#: 每条 = (循环, 槽键) -> (目标行, 裁决, 依据)
ADJUDICATED_NOT_DECLARED: dict[tuple[str, str], tuple[str, str, str]] = {
    ("I3", "provision"): (
        "IMP-017",
        "not_applicable",
        "商誉减值准备。① **生产零接线**：`I3_SPEC` 在 backend/app 下的生产引用"
        "只有 `i_cycle_specs.py` 自身（0 处调 `resolve_semantic_accounts`）"
        "⇒ `build_conflicts` 根本不会对它跑，该假告警**在生产上不存在**；"
        "② I 类真实取数路径是 `i_cycle_accounts.resolve_i_cycle_accounts`，"
        "它有**自己的**冲突检测（`detect_chart_conflict` + 行名闸），不经 `build_conflicts`；"
        "③ `I_CYCLE_SPECS` 是段化声明的**二分投影**，其模块 docstring 明确「只供守卫用，"
        "不得反向用于取数」—— 要声明槽级 row_code 需给 `ISegmentSpec` 加字段并穿透 "
        "`_slots_for`，那是往「只供守卫的投影」里注入**零生产消费方**的字段"
        "（平台已记『additive 注入即死代码』），且 `i_cycle_accounts.py` / "
        "`i_cycle_specs.py` 属并发 spec `i-cycle-extraction-formula-and-disclosure-closure` "
        "的作用域。⇒ 裁决：暂不声明；若 I 类改走 `resolve_semantic_accounts`，"
        "由 `test_i3_not_wired_to_build_conflicts` 打红提醒重新裁决。",
    ),
    ("D1", "provision"): (
        "IMP-001",
        "withdrawn",
        "应收票据坏账准备。**声明它解决不了问题**：`IMP-001` 唯一非空公式是 "
        "soe_standalone 的 `TB('1231','期末余额')`（**宽口径一级科目**），而 D1 备抵的"
        "实际码是 `1231-01` ⇒ 两个集合**无交集**，声明后 `build_conflicts` 仍报冲突，"
        "只是把「拿主行比」换成「拿宽口径备抵行比」，反而制造『看起来已修』的假象。"
        "真修法 = 在 `report_config` 侧补 `1231-01` 细分行（属 "
        "`report-config-account-code-integrity` 的半径，需迁移 + 影响面评估）。"
        "另：`D1_SPEC` 与 D6 同处不接线的 `d_cycle_specs`，生产上无此告警。"
        "⇒ 裁决：撤回声明，留证不删。stale 检测 = 该行公式一旦细分即打红。",
    ),
    ("D2", "provision"): (
        "IMP-002",
        "withdrawn",
        "应收账款坏账准备。**真源本身是错码**：`IMP-002` 的 soe_standalone 公式是 "
        "`TB('1231.02','期末余额')` —— 用**点号**，而 `trial_balance` 的标准码体系是"
        "**横杠** `1231-02` ⇒ 该报表行取数恒空，声明它得到的 basis 是 `1231.02`，"
        "与实际码 `1231-02` 仍无交集。真修法 = 改 `report_config` 那一格的点号为横杠"
        "（`report-config-account-code-integrity` 半径；本 spec 不越界改 DB）。"
        "另：`D2_SPEC` 同处不接线的 `d_cycle_specs`，生产上无此告警。"
        "⇒ 裁决：撤回声明，留证不删。stale 检测 = 点号一旦改成横杠即打红。",
    ),
}

#: 🔴 仍未声明、会（或曾）报假冲突的其余 spec —— 按 `report_config` 实际公式逐条判定。
#: 每条 = (循环, 槽键) -> (应声明的报表行, 该行公式状态, 依据)
#: 落地后必须从本表移出并进 :data:`DECLARED_SLOT_ROW_CODES`（由
#: :func:`test_pending_registry_has_no_overlap_with_declared` 强制）。
PENDING_FALSE_CONFLICT_SPECS: dict[tuple[str, str], tuple[str, str, str]] = {
    # 🔴 **已清空**（2026-08-12，g7-column-alignment-… spec Task 14/15）：
    #    原 7 条全部有了归属 ——
    #      H2 / H3 / H7 / D6 → :data:`DECLARED_SLOT_ROW_CODES`（已声明）
    #      I3 / D1 / D2      → :data:`ADJUDICATED_NOT_DECLARED`（已裁决不声明，配 stale 检测）
    #
    #    空表**不是**判据空转：`test_pending_registry_is_capped` 的上限只许缩短，
    #    `test_every_pending_entry_has_a_home` 断言「三张表的并集覆盖历史全部 7 条」，
    #    任何新的假冲突要么落进已声明、要么落进已裁决、要么回到本表（并写明依据）。
}

#: 历史待办全集（**只许保持或缩短**）—— 防「把某条从三张表里一起删掉」的静默逃逸。
#: 每条历史条目必须能在「已声明」或「已裁决不声明」里找到归属。
_HISTORICAL_PENDING_KEYS: frozenset[tuple[str, str]] = frozenset(
    {
        ("H2", "impairment"),
        ("H3", "impairment"),
        ("H7", "impairment"),
        ("D6", "provision"),
        ("I3", "provision"),
        ("D1", "provision"),
        ("D2", "provision"),
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Property 1：纯函数三态
# ─────────────────────────────────────────────────────────────────────────────


def _slot(key: str, standard_codes: list[str]) -> ResolvedSlot:
    return ResolvedSlot(
        key=key,
        label=key,
        standard_codes=list(standard_codes),
        codes=list(standard_codes),
        resolved_from=RESOLVED_FROM_STANDARD_CHART,
    )


class TestBuildConflictsThreeStates:
    """``slot_report_codes`` 的三态：有交集 / 无交集 / 无基准。"""

    def test_slot_basis_with_intersection_is_not_conflict(self):
        slots = {"gross": _slot("gross", ["1511"]), "provision": _slot("provision", ["1512"])}
        out = build_conflicts(slots, ["1511"], {"provision": ["1512"]})
        assert out == [], f"备抵用自己那条报表行比对应无冲突，实际 {out}"

    def test_slot_basis_without_intersection_is_conflict(self):
        """槽级 basis 也对不上 ⇒ **真冲突**必须仍然报（不是无脑放行）。"""
        slots = {"provision": _slot("provision", ["1512"])}
        out = build_conflicts(slots, ["1511"], {"provision": ["9999"]})
        assert out == [("provision", "9999", "1512")], (
            f"槽级 basis 与实际码无交集时必须报冲突，实际 {out}"
        )

    def test_empty_slot_basis_is_skipped_not_conflict(self):
        """该报表行公式为 NULL / 查询失败 ⇒ 「未知」不等于「有冲突」（三态铁律）。"""
        slots = {"provision": _slot("provision", ["1512"])}
        out = build_conflicts(slots, ["1511"], {"provision": []})
        assert out == [], f"无对照基准时不得判冲突，实际 {out}"

    def test_empty_spec_level_basis_is_skipped(self):
        """spec 级也没有基准（row_code=None 或公式 NULL）⇒ 同样跳过。"""
        slots = {"gross": _slot("gross", ["1511"])}
        assert build_conflicts(slots, []) == []
        assert build_conflicts(slots, [], {}) == []

    def test_unfound_slot_is_skipped(self):
        """槽没定位到码 ⇒ 无从比对（这是 G1/G10 的 derivative 槽不报假冲突的原因）。"""
        slots = {"derivative": _slot("derivative", [])}
        out = build_conflicts(slots, ["1101"], {"derivative": ["2102"]})
        assert out == []


class TestBuildConflictsBackwardCompatible:
    """缺省 ``slot_report_codes`` 时行为逐字不变（零回归支点）。"""

    @pytest.mark.parametrize(
        "actual,report,expected",
        [
            (["1511"], ["1511"], []),
            (["1512"], ["1511"], [("provision", "1511", "1512")]),
            ([], ["1511"], []),
            (["1512"], [], []),
        ],
    )
    def test_none_and_empty_dict_equal_legacy(self, actual, report, expected):
        slots = {"provision": _slot("provision", actual)}
        assert build_conflicts(slots, report) == expected
        assert build_conflicts(slots, report, None) == expected
        # 空 dict 与 None 同义（该槽不在 per_slot 里 ⇒ 用 spec 级基准）
        assert build_conflicts(slots, report, {}) == expected

    def test_slot_not_in_map_uses_spec_level_basis(self):
        """map 里没有该槽 key ⇒ 回退 spec 级（部分槽声明、部分不声明的混合场景）。"""
        slots = {
            "gross": _slot("gross", ["1511"]),
            "provision": _slot("provision", ["1512"]),
        }
        out = build_conflicts(slots, ["1511"], {"provision": ["1512"]})
        assert out == [], "gross 用 spec 级基准 1511 命中、provision 用槽级 1512 命中"


# ─────────────────────────────────────────────────────────────────────────────
# Property 2：反向自检 —— 复现旧缺陷
# ─────────────────────────────────────────────────────────────────────────────


class TestReverseSelfCheck:
    """证明修复**必要**：不声明槽级 row_code 时 G7 形态必然报假冲突。"""

    def test_legacy_behaviour_reproduces_false_conflict(self):
        """旧行为（全槽用主行码集）在 G7 真实形态下必然报 provision 冲突。"""
        slots = {
            "gross": _slot("gross", ["1511"]),
            "provision": _slot("provision", ["1512"]),
        }
        legacy = build_conflicts(slots, ["1511"])  # 不传 slot_report_codes = 旧行为
        assert legacy == [("provision", "1511", "1512")], (
            "反向自检失效：旧行为本应复现假冲突，实际 " f"{legacy}"
        )

    def test_slot_row_code_defaults_to_none(self):
        """默认值必须是 None，否则既有 28+ 消费方行为会变。"""
        s = SemanticAccountSlot(key="x", names=("科目",))
        assert s.row_code is None

    def test_resolved_slot_report_row_code_defaults_to_empty(self):
        assert ResolvedSlot(key="x", label="x").report_row_code == ""

    def test_report_row_code_is_in_slot_payload(self):
        """``as_dict()`` 的 slots 里必须带 report_row_code（溯源可追溯红线）。"""
        from app.services.four_table.semantic_account_resolver import (
            SemanticAccountResult,
        )

        res = SemanticAccountResult(
            slots={
                "provision": dataclasses.replace(
                    _slot("provision", ["1512"]), report_row_code="IMP-009"
                )
            },
            row_code="BS-024",
        )
        payload = res.as_dict()
        assert payload["slots"]["provision"]["report_row_code"] == "IMP-009"


# ─────────────────────────────────────────────────────────────────────────────
# Property 3：G 循环声明正确性（源码级）
# ─────────────────────────────────────────────────────────────────────────────


class TestGCycleDeclarations:
    # 🔴 必须覆盖**全部**已声明的 spec（Task 14 落地后从 2 个扩到 6 个）——
    #    少一个就等于那个 spec 的声明没有任何守卫，改歪不会被发现。
    #    `test_declared_registry_covers_every_spec` 反向锁死本字典与登记表同域。
    _SPECS = {
        "G4": G4_SPEC,
        "G7": G7_SPEC,
        "H2": H2_ACCOUNT_SPEC,
        "H3": H3_ACCOUNT_SPEC,
        "H7": H7_ACCOUNT_SPEC,
        "D6": D6_SPEC,
    }

    def test_declared_slots_match_registry(self):
        actual: dict[tuple[str, str], str] = {}
        for name, spec in self._SPECS.items():
            for s in spec.slots:
                if s.row_code:
                    actual[(name, s.key)] = s.row_code
        assert actual == DECLARED_SLOT_ROW_CODES, (
            f"槽级 row_code 声明与登记表不符：实际 {actual} "
            f"vs 登记 {DECLARED_SLOT_ROW_CODES}"
        )

    def test_declared_registry_covers_every_spec(self):
        """登记表的 spec 名集合 == `_SPECS` 的键集合（防「登记了但没纳入扫描」）。"""
        assert {name for name, _key in DECLARED_SLOT_ROW_CODES} == set(self._SPECS), (
            "登记表与 _SPECS 不同域 ⇒ 有 spec 的声明处于无守卫状态"
        )

    def test_declared_row_codes_are_impairment_rows(self):
        """备抵槽的槽级 row_code 必须是 ``IMP-*``（备抵专用报表段）。"""
        for (name, key), rc in DECLARED_SLOT_ROW_CODES.items():
            assert rc.startswith("IMP-"), f"{name}.{key} 的 row_code {rc} 不是 IMP-* 行"

    def test_only_provision_slots_declare_row_code(self):
        """原值槽不得声明槽级 row_code（它就该用主行比对）。"""
        for name, spec in self._SPECS.items():
            for s in spec.slots:
                if s.row_code:
                    assert s.is_provision, (
                        f"{name}.{s.key} 非备抵槽却声明了槽级 row_code={s.row_code}"
                    )

    def test_spec_level_row_code_unchanged(self):
        """spec 级 row_code 不得被顺手改动（定位与溯源都依赖它）。

        🔴 这是 Task 14 的**零回归支点**：声明槽级 row_code 只影响冲突检测的
        对照基准，**绝不能**顺手动了主行 —— 主行既是定位兜底又是溯源展示。
        """
        assert G4_SPEC.row_code == "BS-021"
        assert G7_SPEC.row_code == "BS-024"
        assert H2_ACCOUNT_SPEC.row_code == "BS-029"
        assert H3_ACCOUNT_SPEC.row_code == "BS-027"
        assert H7_ACCOUNT_SPEC.row_code == "BS-030"
        assert D6_SPEC.row_code == "BS-011"

    def test_declaring_slot_row_code_does_not_touch_locating(self):
        """声明槽级 row_code **不改变定位**（兜底码与否决词逐字未动）。

        `row_code` 的契约是「仅用于冲突检测，不参与定位」。本条把这件事
        钉成可执行断言：四个新声明槽的 `fallback_standard_codes` 必须是
        Task 14 之前的实测值。
        """
        expect_fallbacks = {
            ("H2", "impairment"): (),  # 有意为之的空兜底（客户自建科目按名定位）
            ("H3", "impairment"): ("1527",),
            ("H7", "impairment"): (),
            ("D6", "provision"): ("1142", "1231-05"),
        }
        checked = 0
        for name, spec in self._SPECS.items():
            for s in spec.slots:
                key = (name, s.key)
                if key not in expect_fallbacks:
                    continue
                assert tuple(s.fallback_standard_codes) == expect_fallbacks[key], (
                    f"{name}.{s.key} 的兜底码被顺手改了："
                    f"{tuple(s.fallback_standard_codes)} != {expect_fallbacks[key]}"
                )
                checked += 1
        assert checked == len(expect_fallbacks), "断言未覆盖全部新声明槽（空转）"


class TestPendingRegistryHygiene:
    def test_pending_registry_has_no_overlap_with_declared(self):
        overlap = set(PENDING_FALSE_CONFLICT_SPECS) & set(DECLARED_SLOT_ROW_CODES)
        assert not overlap, (
            f"已声明的槽仍留在待办登记表里（stale）：{overlap}"
        )

    def test_pending_entries_document_evidence(self):
        for (cycle, key), (rc, state, why) in PENDING_FALSE_CONFLICT_SPECS.items():
            assert rc.startswith("IMP-"), f"{cycle}.{key} 目标行 {rc} 不是 IMP-*"
            assert state, f"{cycle}.{key} 未写明该行公式状态"
            assert len(why) >= 20, f"{cycle}.{key} 依据过短：{why!r}"

    def test_pending_registry_is_capped(self):
        """上限只许缩短 —— 防「对不齐就往登记表加一条」变成逃逸阀。"""
        assert len(PENDING_FALSE_CONFLICT_SPECS) <= 7


class TestAdjudicatedNotDeclared:
    """「已裁决不声明」三条的卫生 + stale 检测。

    这张表最容易腐化成**豁免逃逸阀**（「对不上就写一条依据放行」），故：
    ① 与另两张表严格互斥；② 历史待办的每一条必须能在三张表里找到归属；
    ③ 每条配 stale 检测（裁决前提一旦变化即打红）；④ 条目数上限只许缩短。
    """

    _CAP = 3
    _VALID_VERDICTS = frozenset({"not_applicable", "withdrawn"})

    def test_three_registries_are_mutually_exclusive(self):
        declared = set(DECLARED_SLOT_ROW_CODES)
        pending = set(PENDING_FALSE_CONFLICT_SPECS)
        adjudicated = set(ADJUDICATED_NOT_DECLARED)
        assert not (declared & adjudicated), f"已声明与已裁决重叠：{declared & adjudicated}"
        assert not (pending & adjudicated), f"待办与已裁决重叠：{pending & adjudicated}"
        assert not (declared & pending), f"已声明与待办重叠：{declared & pending}"

    def test_every_historical_pending_entry_has_a_home(self):
        """历史 7 条待办必须**全部**能在三张表里找到归属（防静默删除）。"""
        homed = (
            set(DECLARED_SLOT_ROW_CODES)
            | set(PENDING_FALSE_CONFLICT_SPECS)
            | set(ADJUDICATED_NOT_DECLARED)
        )
        missing = _HISTORICAL_PENDING_KEYS - homed
        assert not missing, (
            f"历史待办条目凭空消失（既没声明、也没裁决、也不在待办里）：{missing}"
        )

    def test_entries_document_evidence(self):
        for (cycle, key), (rc, verdict, why) in ADJUDICATED_NOT_DECLARED.items():
            assert rc.startswith("IMP-"), f"{cycle}.{key} 目标行 {rc} 不是 IMP-*"
            assert verdict in self._VALID_VERDICTS, f"{cycle}.{key} 裁决值 {verdict!r} 非法"
            # 依据必须足够长（这三条都涉及「为什么声明反而不对」，短依据说不清）
            assert len(why) >= 80, f"{cycle}.{key} 依据过短（{len(why)} 字）：{why[:60]!r}"

    def test_registry_is_capped(self):
        assert len(ADJUDICATED_NOT_DECLARED) <= self._CAP, "上限只许缩短"

    def test_adjudicated_slots_really_have_no_row_code(self):
        """裁决为「不声明」的槽，实际代码里必须确实没声明（防登记与代码打架）。"""
        specs = {"I3": I3_SPEC, "D1": D1_SPEC, "D2": D2_SPEC}
        checked = 0
        for (cycle, key), _entry in ADJUDICATED_NOT_DECLARED.items():
            spec = specs[cycle]
            slot = next((s for s in spec.slots if s.key == key), None)
            assert slot is not None, f"{cycle} 没有名为 {key} 的槽（登记表过时）"
            assert not slot.row_code, (
                f"{cycle}.{key} 登记为「不声明」，但代码里已声明 row_code={slot.row_code!r}"
                " ⇒ 该条应移入 DECLARED_SLOT_ROW_CODES"
            )
            checked += 1
        assert checked == len(ADJUDICATED_NOT_DECLARED), "断言未覆盖全部裁决条目（空转）"

    def test_i3_stale_check_still_not_wired_to_build_conflicts(self):
        """I3 裁决的前提 = `I3_SPEC` 在生产里零接线。前提变了必须重新裁决。

        判据：在 `backend/app/` 里找 `I3_SPEC` / `I_CYCLE_SPECS` 的引用，
        且该文件调用了 `resolve_semantic_accounts`（唯一会触发 `build_conflicts` 的入口）。
        命中即打红 —— 那时该假告警**真的存在**了，应改为声明。
        """
        app_dir = _ROOT / "app"
        wired: list[str] = []
        for path in app_dir.rglob("*.py"):
            src = path.read_text(encoding="utf-8", errors="replace")
            if not re.search(r"\bresolve_semantic_accounts\s*\(", src):
                continue
            if re.search(r"\b(I3_SPEC|I_CYCLE_SPECS)\b", src):
                wired.append(path.relative_to(_ROOT).as_posix())
        assert not wired, (
            "I3_SPEC/I_CYCLE_SPECS 已被接到 resolve_semantic_accounts："
            f"{wired} ⇒ `build_conflicts` 现在会对 I3 跑，"
            "ADJUDICATED_NOT_DECLARED 里 I3 那条的裁决前提已失效，请重新裁决"
        )
        # 反向自检：判据不是恒空 —— 同样的扫法对 H3 必须有命中
        h3_wired = [
            p.relative_to(_ROOT).as_posix()
            for p in app_dir.rglob("*.py")
            if re.search(r"\bresolve_semantic_accounts\s*\(", p.read_text(encoding="utf-8", errors="replace"))
            and re.search(r"\bH3_ACCOUNT_SPEC\b", p.read_text(encoding="utf-8", errors="replace"))
        ]
        assert h3_wired, "扫描逻辑失效（对确有接线的 H3 也扫不到）⇒ 上面的断言是假绿"


# ─────────────────────────────────────────────────────────────────────────────
# Property 4：连库交叉锁死（IMP 行公式必须真含各槽兜底码）
# ─────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class _Snapshot:
    """``IMP-*`` 行公式快照 + G4/G7 的 conflicts 实测。"""

    imp_formulas: dict[tuple[str, str], str | None] = dataclasses.field(
        default_factory=dict
    )
    conflicts: dict[tuple[str, str], list] = dataclasses.field(default_factory=dict)
    projects: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    load_error: str = ""


async def _load_async() -> _Snapshot:
    snap = _Snapshot()
    url = str(settings.DATABASE_URL)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {},
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            rows = (
                await db.execute(
                    sa.text(
                        "SELECT row_code, applicable_standard, formula "
                        "FROM report_config WHERE row_code LIKE 'IMP-%' "
                        "AND is_deleted = false "
                        "AND applicable_standard NOT LIKE 'project:%'"
                    )
                )
            ).fetchall()
            for r in rows:
                snap.imp_formulas[(r.row_code, r.applicable_standard)] = r.formula

            from app.services.four_table.semantic_account_resolver import (
                ResolverContext,
                resolve_semantic_accounts,
            )

            projs = (
                await db.execute(
                    sa.text(
                        "SELECT DISTINCT p.id, p.name, p.audit_year FROM projects p "
                        "JOIN tb_balance b ON b.project_id = p.id "
                        "WHERE p.is_deleted = false AND b.account_code LIKE '1511%' "
                        "ORDER BY p.name"
                    )
                )
            ).fetchall()
            for p in projs:
                snap.projects.append((str(p.id), p.name or ""))
                ctx = ResolverContext(db=db, project_id=p.id, year=int(p.audit_year))
                for name, spec in (("G4", G4_SPEC), ("G7", G7_SPEC)):
                    res = await resolve_semantic_accounts(ctx, spec)
                    snap.conflicts[(name, str(p.id))] = [list(c) for c in res.conflicts]
    finally:
        await engine.dispose()
    return snap


@lru_cache(maxsize=1)
def _snapshot() -> _Snapshot:
    try:
        return asyncio.run(_load_async())
    except Exception as e:  # noqa: BLE001 — 连不上库时如实报告而非静默 skip
        return _Snapshot(load_error=f"{type(e).__name__}: {e}")


def _require_db() -> _Snapshot:
    snap = _snapshot()
    if snap.load_error:
        pytest.skip(f"真实库不可用，本连库守卫无法验证：{snap.load_error}")
    return snap


class TestImpRowCrossLock:
    """交叉锁死：声明的 IMP 行公式必须真含该槽的兜底码。

    没有这条断言，``report_config`` 侧一旦改动（如把 ``IMP-009`` 改指别的科目），
    声明会静默失效并让假冲突以「真冲突」的形态回来。
    """

    #: (spec, slot) -> 该槽兜底标准码（与各 per-cycle `_specs` 的声明交叉比对）。
    #:
    #: 🔴 值为 ``None`` = 该槽**有意为之的空兜底**（客户自建科目按名定位，
    #:    硬编码兜底码会在「客户没有该科目」时取到别的科目的钱 —— H2/H7 的
    #:    模块 docstring 有实证）。这类槽跳过「公式必须引用兜底码」的比对，
    #:    但仍受下面 `test_null_formula_rows_are_really_null` 的三态锁死。
    _EXPECT_CODE: dict[tuple[str, str], str | None] = {
        ("G4", "provision"): "1505",
        ("G7", "provision"): "1512",
        ("H3", "impairment"): "1527",
        ("H2", "impairment"): None,  # 空兜底（在建工程减值准备无独立标准码）
        ("H7", "impairment"): None,  # 空兜底（生产性生物资产减值准备无独立标准码）
        ("D6", "provision"): "1142",
    }

    #: 声明的 IMP 行中**公式实测全为 NULL** 的（2026-08-12 postgres 只读复核）。
    #: 它们靠 `build_conflicts` 的三态跳过消除假告警，故不参与「公式含兜底码」比对。
    _NULL_FORMULA_ROWS = frozenset({"IMP-012", "IMP-013", "IMP-004"})

    def _specs(self):
        return {
            "G4": G4_SPEC,
            "G7": G7_SPEC,
            "H2": H2_ACCOUNT_SPEC,
            "H3": H3_ACCOUNT_SPEC,
            "H7": H7_ACCOUNT_SPEC,
            "D6": D6_SPEC,
        }

    def test_expect_code_table_covers_every_declaration(self):
        """期望表必须与登记表同域（防「新声明了但交叉锁死没覆盖」）。"""
        assert set(self._EXPECT_CODE) == set(DECLARED_SLOT_ROW_CODES), (
            "_EXPECT_CODE 与 DECLARED_SLOT_ROW_CODES 不同域 ⇒ 有声明未被交叉锁死"
        )

    def test_declared_imp_row_formula_contains_slot_fallback_code(self):
        snap = _require_db()
        specs = self._specs()
        checked = 0
        skipped_null: list[str] = []
        skipped_empty: list[str] = []
        for (name, key), rc in DECLARED_SLOT_ROW_CODES.items():
            slot = next(s for s in specs[name].slots if s.key == key)
            want = self._EXPECT_CODE[(name, key)]
            if want is None:
                # 有意为之的空兜底：断言它**确实**是空的（防「悄悄补了个兜底码」）
                assert not slot.fallback_standard_codes, (
                    f"{name}.{key} 登记为空兜底，实际却有 {slot.fallback_standard_codes}"
                    " ⇒ 请更新 _EXPECT_CODE 并复核「硬编码兜底码会取错科目」那条实证"
                )
                skipped_empty.append(f"{name}.{key}")
                continue
            assert want in slot.fallback_standard_codes, (
                f"{name}.{key} 的兜底码 {slot.fallback_standard_codes} 不含 {want}，"
                f"本断言的期望表已过期"
            )
            if rc in self._NULL_FORMULA_ROWS:
                # 公式全 NULL 的行：靠三态跳过，谈不上「公式引用兜底码」
                skipped_null.append(f"{name}.{key}({rc})")
                continue
            found = [
                std
                for (row, std), f in snap.imp_formulas.items()
                if row == rc and f and f"'{want}'" in f
            ]
            assert found, (
                f"{rc} 在 report_config 里没有任何准则的公式引用 '{want}' —— "
                f"{name}.{key} 的槽级 row_code 声明已失效（report_config 侧被改过？）\n"
                f"该行现有公式: "
                f"{[(s, f) for (r, s), f in snap.imp_formulas.items() if r == rc]}"
            )
            checked += 1
        # 防空转：真正做了「公式含兜底码」比对的条数必须等于「非空兜底且公式非 NULL」的条数
        expect_checked = len(
            [
                k
                for k, v in self._EXPECT_CODE.items()
                if v is not None and DECLARED_SLOT_ROW_CODES[k] not in self._NULL_FORMULA_ROWS
            ]
        )
        assert checked == expect_checked, (
            f"交叉锁死实际比对 {checked} 条、应为 {expect_checked} 条"
            f"（空兜底跳过 {skipped_empty}、NULL 公式跳过 {skipped_null}）"
        )
        assert checked >= 3, "非 NULL 公式的声明少于 3 条 ⇒ 该断言几乎空转"

    def test_null_formula_rows_are_really_null(self):
        """三态锁死：登记为「公式全 NULL」的 IMP 行必须**真的**全 NULL。

        它们的假告警靠 `build_conflicts` 的三态跳过消除。若 `report_config` 侧
        哪天补上了公式，跳过就变成了**真比对** —— 此时兜底码若与公式不符会冒出
        新的冲突告警，必须重新裁决，故这里主动打红。
        """
        snap = _require_db()
        offenders: list[str] = []
        for rc in sorted(self._NULL_FORMULA_ROWS):
            for (row, std), formula in snap.imp_formulas.items():
                if row == rc and formula:
                    offenders.append(f"{rc}/{std} = {formula!r}")
        assert not offenders, (
            f"以下 IMP 行已不再是 NULL 公式：{offenders} ⇒ "
            "对应槽的「三态跳过」前提失效，请复核兜底码与新公式是否一致"
        )
        # 反向自检：这些行确实在快照里（否则上面的循环恒空）
        present = {r for (r, _s) in snap.imp_formulas if r in self._NULL_FORMULA_ROWS}
        assert present == self._NULL_FORMULA_ROWS, (
            f"快照里缺 IMP 行 {self._NULL_FORMULA_ROWS - present} ⇒ 上条断言空转"
        )

    def test_imp_rows_exist_at_all(self):
        """反向自检：IMP 段确实存在，否则上一条断言的扫描面为空。"""
        snap = _require_db()
        assert len(snap.imp_formulas) >= 30, (
            f"IMP-* 行数异常（{len(snap.imp_formulas)}），扫描面可能为空"
        )


class TestLiveConflictsAreClean:
    """真实库端到端：G4/G7 在**全部**有数据的项目上都不得报冲突。"""

    def test_no_false_conflicts_in_any_project(self):
        snap = _require_db()
        assert snap.projects, "没有含 1511 数据的项目，本断言空转"
        offenders = [
            f"{name}/{pid[:8]}: {conf}"
            for (name, pid), conf in sorted(snap.conflicts.items())
            if conf
        ]
        assert not offenders, (
            "G4/G7 仍有 conflicts（若是 report_config 真错码请在此登记豁免）:\n  "
            + "\n  ".join(offenders)
        )

    def test_coverage_is_not_vacuous(self):
        snap = _require_db()
        # 8 个项目 × 2 个 spec
        assert len(snap.conflicts) == len(snap.projects) * 2, (
            f"conflicts 覆盖数 {len(snap.conflicts)} != 项目数×2"
        )
