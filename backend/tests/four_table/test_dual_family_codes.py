"""双族并存科目（使用权资产 / 租赁负债）判据守卫。

**本文件在 Wave 2 之前必须打红** —— `TestReportConfigCurrentState` 断言
`BS-031`/`BS-063` 当前**只含 primary 码**，Task 8 的 V145 迁移落地后
该类转绿判据翻面（见 `TestReportConfigAfterMigration`，用 skipif 控制）。

🔴 连库测试一律「一次 ``asyncio.run`` 取快照 + 全部断言同步」：
`app.core.database` 的连接池绑定**首个**事件循环，pytest-asyncio
默认每个测试新建 loop → 第二个测试起报
``AttributeError: 'NoneType' object has no attribute 'send'``，
若 fixture 里 ``except → pytest.skip`` 就变成**静默跳过 = 假绿**。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 1.1~1.7 / Property 1~4
"""
from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.four_table.dual_family_codes import (  # noqa: E402
    ALL_DUAL_FAMILY_CODES,
    ALTERNATE_CODES,
    BS031_GROUPS,
    BS063_GROUPS,
    DUAL_FAMILY_BY_SLOT,
    DUAL_FAMILY_ROW_FORMULAS,
    ROU_LEASE_DUAL_FAMILIES,
    DualFamilyGroup,
    codes_for_slot,
    dual_family_formula,
    tb_expression,
)


# ─────────────────────────────────────────────────────────────────────────────
# 真实库快照（一次取全，后续断言全同步）
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Snapshot:
    ok: bool = False
    reason: str = ""
    #: (row_code, applicable_standard) → formula
    report_formulas: dict[tuple[str, str], str | None] = field(default_factory=dict)
    #: project_id → {code: unadjusted_amount}（trial_balance，仅本族码）
    tb_by_project: dict[str, dict[str, Decimal | None]] = field(default_factory=dict)
    #: code → 全库合计（trial_balance）
    tb_totals: dict[str, Decimal] = field(default_factory=dict)


async def _load() -> Snapshot:
    snap = Snapshot()
    try:
        from app.core.database import async_session
    except Exception as exc:  # pragma: no cover - 环境缺依赖
        snap.reason = f"无法导入 async_session: {exc}"
        return snap

    try:
        async with async_session() as db:
            rows = (
                await db.execute(
                    sa.text(
                        "SELECT row_code, applicable_standard, formula "
                        "FROM report_config "
                        "WHERE row_code IN ('BS-031','BS-063') "
                        "AND is_deleted = false"
                    )
                )
            ).fetchall()
            for r in rows:
                snap.report_formulas[(r[0], r[1])] = r[2]

            codes = list(ALL_DUAL_FAMILY_CODES)
            rows = (
                await db.execute(
                    sa.text(
                        "SELECT project_id::text, standard_account_code, "
                        "       SUM(unadjusted_amount) AS amt "
                        "FROM trial_balance "
                        "WHERE standard_account_code = ANY(:codes) "
                        "AND is_deleted = false "
                        "GROUP BY 1, 2"
                    ),
                    {"codes": codes},
                )
            ).fetchall()
            for pid, code, amt in rows:
                snap.tb_by_project.setdefault(pid, {})[code] = amt
                snap.tb_totals[code] = snap.tb_totals.get(code, Decimal(0)) + (
                    amt or Decimal(0)
                )
        snap.ok = True
    except Exception as exc:
        snap.reason = f"查询失败: {exc}"
    return snap


_SNAP: Snapshot = asyncio.run(_load())

_needs_db = pytest.mark.skipif(not _SNAP.ok, reason=f"无法连库: {_SNAP.reason}")


# ─────────────────────────────────────────────────────────────────────────────
# Property 1：真源常量自洽（不连库）
# ─────────────────────────────────────────────────────────────────────────────
class TestSourceOfTruthSelfConsistency:
    def test_slot_keys_unique(self):
        keys = [g.slot_key for g in ROU_LEASE_DUAL_FAMILIES]
        assert len(keys) == len(set(keys)), f"槽键重复: {keys}"

    def test_every_group_has_evidence_and_source_ref(self):
        for g in ROU_LEASE_DUAL_FAMILIES:
            assert len(g.source_ref) >= 10, f"{g.slot_key} 缺 source_ref"
            # evidence 必须含具体金额（防写成「已实证」这类空话）
            assert any(ch.isdigit() for ch in g.evidence), (
                f"{g.slot_key} 的 evidence 不含任何数字，"
                f"必须写明真实库金额供后来者复核: {g.evidence!r}"
            )
            assert len(g.evidence) >= 30, f"{g.slot_key} evidence 过短"

    def test_codes_dedupe_and_order(self):
        g = DUAL_FAMILY_BY_SLOT["gross"]
        assert g.codes == ("1641", "1651"), "primary 必须在前（公式顺序依赖它）"
        # alternate 为 None 时只返回 primary
        assert DUAL_FAMILY_BY_SLOT["impairment"].codes == ("1643",)

    def test_codes_converge_when_alternate_equals_primary(self):
        """🔴 `alternate == primary` 必须收敛为单码，否则公式里同码被加两次。

        2026-08-06 变异检验（M4）抓出的守卫缺口：既有断言只覆盖
        「真双族（alternate != primary）」与「无 alternate（None）」两种形态，
        **从未走过收敛分支** → 把 `codes` 里的 `or self.alternate == self.primary`
        判断整段删掉，全部断言仍绿，而生产侧会产出
        ``TB('1641',..)+TB('1641',..)`` = 该科目余额翻倍。

        这条分支不是假想：登记新语义时若一时不确定新族码，
        很容易把 `alternate` 填成与 `primary` 相同的值。
        """
        probe = DualFamilyGroup(
            slot_key="__probe_same__",
            label="探针：两族同码",
            primary="1641",
            alternate="1641",
            is_provision=False,
            source_ref="unit-test probe",
            evidence="探针用：alternate 与 primary 同码时必须收敛为单码，金额 0",
        )
        assert probe.codes == ("1641",), (
            f"两族同码未收敛，公式会把同一科目加两次: {probe.codes}"
        )
        assert tb_expression(probe.codes, "期末余额") == "TB('1641','期末余额')"

    def test_dual_family_formula_no_duplicate_code_in_output(self):
        """任一报表行公式里，同一科目码不得出现两次（结构性防双算）。"""
        for row_code, formula in DUAL_FAMILY_ROW_FORMULAS.items():
            codes = re.findall(r"TB\('(\d+)'", formula)
            dup = [c for c in set(codes) if codes.count(c) > 1]
            assert not dup, f"{row_code} 公式内科目码重复（双算）: {dup} :: {formula}"

    def test_codes_for_slot_unknown_returns_empty(self):
        assert codes_for_slot("不存在的槽") == ()

    def test_tb_expression_rejects_empty(self):
        """空码集必须抛错 —— 空串会被 prefill 引擎当合法公式吞掉。"""
        with pytest.raises(ValueError):
            tb_expression((), "期末余额")

    def test_tb_expression_shape(self):
        assert tb_expression(("1641", "1651"), "期末余额") == (
            "TB('1641','期末余额')+TB('1651','期末余额')"
        )

    def test_bs031_formula_shape(self):
        got = DUAL_FAMILY_ROW_FORMULAS["BS-031"]
        assert got == (
            "TB('1641','期末余额')+TB('1651','期末余额')"
            "-TB('1642','期末余额')-TB('1652','期末余额')"
            "-TB('1643','期末余额')"
        ), got

    def test_bs063_formula_shape(self):
        got = DUAL_FAMILY_ROW_FORMULAS["BS-063"]
        assert got == (
            "TB('2601','期末余额')+TB('2651','期末余额')"
            "-TB('2602','期末余额')"
        ), got

    def test_bs063_does_not_double_deduct_unearned_finance(self):
        """新族把未确认融资费用做成 2651.02 子科目 ⇒ 不得再出现 2651 的减项。

        `account_mapping` 实证：``2651.02 租赁负债_未确认融资费用 → 2651``
        （auto_exact，5 项目）⇒ 它已含在 2651 父额内。
        """
        f = DUAL_FAMILY_ROW_FORMULAS["BS-063"]
        assert f.count("TB('2651'") == 1, "2651 只应作为加项出现一次"
        assert "-TB('2651'" not in f

    def test_provision_groups_are_subtracted(self):
        for g in BS031_GROUPS + BS063_GROUPS:
            for code in g.codes:
                token = f"TB('{code}','期末余额')"
                row = "BS-031" if g in BS031_GROUPS else "BS-063"
                f = DUAL_FAMILY_ROW_FORMULAS[row]
                idx = f.index(token)
                sign = f[idx - 1] if idx > 0 else "+"
                if g.is_provision:
                    assert sign == "-", f"{code} 是备抵却不是减项"
                else:
                    assert sign != "-", f"{code} 不是备抵却被减"

    def test_dual_family_formula_rejects_empty(self):
        with pytest.raises(ValueError):
            dual_family_formula(())

    def test_alternate_codes_nonempty(self):
        """反向自检：alternate 全为 None 时本文件的核心断言就失去意义。"""
        assert ALTERNATE_CODES, "至少要有一个新族码，否则整份守卫是空转"
        assert set(ALTERNATE_CODES) == {"1651", "1652", "2651"}


# ─────────────────────────────────────────────────────────────────────────────
# Property 2：两族逐项目互斥（连库）→ 证明加和零双算
# ─────────────────────────────────────────────────────────────────────────────
@_needs_db
class TestFamiliesAreMutuallyExclusive:
    def test_snapshot_nonempty(self):
        """锚点：快照必须非空，否则下面的断言全是空转。"""
        assert _SNAP.tb_by_project, "trial_balance 未取到任何双族科目记录"
        assert _SNAP.tb_totals, "合计为空"

    @pytest.mark.parametrize(
        "primary,alternate",
        [(g.primary, g.alternate) for g in ROU_LEASE_DUAL_FAMILIES if g.alternate],
    )
    def test_no_project_has_both_families_nonzero(self, primary, alternate):
        """同一项目内两族不得同时有非零值 —— 这是加和不双算的前提。

        当前实证为空集；此断言是**未来防线**：一旦某项目开始两族并用，
        它会立刻打红，提醒重新裁决「加和 vs 改码」。
        """
        offenders = []
        for pid, codes in _SNAP.tb_by_project.items():
            a = codes.get(primary)
            b = codes.get(alternate)
            if a is None or b is None:
                continue
            if a and b and a != 0 and b != 0:
                offenders.append((pid, primary, a, alternate, b))
        assert not offenders, (
            f"发现项目两族同时非零，加和会双算，必须重新裁决: {offenders}"
        )

    def test_alternate_family_dominates(self):
        """新族金额必须远大于旧族 —— 这是「按 primary 取数只取到 0.04%」的判据。"""
        gross = DUAL_FAMILY_BY_SLOT["gross"]
        primary_total = _SNAP.tb_totals.get(gross.primary, Decimal(0))
        alt_total = _SNAP.tb_totals.get(gross.alternate or "", Decimal(0))
        assert alt_total > primary_total, (
            f"实证前提已变：{gross.primary}={primary_total} "
            f"vs {gross.alternate}={alt_total}。"
            "若新族不再占主导，本 spec 的 Requirement 1 需重新评估。"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Property 3：`report_config` 当前只含 primary（本类现在必红，V145 后翻面）
# ─────────────────────────────────────────────────────────────────────────────
_MIGRATED = _SNAP.ok and all(
    (_SNAP.report_formulas.get((row, std)) or "").find(alt) >= 0
    for row, alt in (("BS-031", "1651"), ("BS-063", "2651"))
    for std in (
        "listed_standalone",
        "listed_consolidated",
        "soe_standalone",
        "soe_consolidated",
    )
)


@_needs_db
class TestReportConfigDualFamilyCoverage:
    def test_all_four_variants_exist(self):
        for row in ("BS-031", "BS-063"):
            got = {
                std
                for (rc, std) in _SNAP.report_formulas
                if rc == row
            }
            assert got >= {
                "listed_standalone",
                "listed_consolidated",
                "soe_standalone",
                "soe_consolidated",
            }, f"{row} 变体缺失: {got}"

    @pytest.mark.skipif(
        _MIGRATED, reason="V145 已应用，改由 test_after_migration 断言"
    )
    def test_before_migration_only_primary(self):
        """**Wave 1 期望红**：当前公式只含 primary 族 ⇒ 取数只有 0.04%。"""
        missing = []
        for (row, std), formula in sorted(_SNAP.report_formulas.items()):
            f = formula or ""
            for alt in ALTERNATE_CODES:
                if alt in f:
                    continue
                group = next(
                    (g for g in ROU_LEASE_DUAL_FAMILIES if g.alternate == alt), None
                )
                if group is None:
                    continue
                expected_row = "BS-031" if group in BS031_GROUPS else "BS-063"
                if expected_row != row:
                    continue
                missing.append((row, std, alt))
        assert missing, (
            "预期在 V145 之前应发现缺失的新族码，但一条都没有 —— "
            "说明本守卫的匹配逻辑失效（空转）"
        )
        pytest.fail(
            "【Wave 1 预期红】report_config 缺新族码，取数只覆盖 0.04%："
            + "; ".join(f"{r}/{s} 缺 {a}" for r, s, a in missing)
        )

    @pytest.mark.skipif(
        not _MIGRATED, reason="V145 尚未应用（Wave 1 阶段预期如此）"
    )
    def test_after_migration_formula_matches_source_of_truth(self):
        """V145 后：八条 formula 必须与单一真源逐字相等。"""
        for (row, std), formula in sorted(_SNAP.report_formulas.items()):
            expected = DUAL_FAMILY_ROW_FORMULAS[row]
            got = (formula or "").replace(" ", "")
            assert got == expected.replace(" ", ""), (
                f"{row}/{std} 公式与真源不符\n实际: {got}\n期望: {expected}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Property：消费方必须真的引了双族真源（Task 6 / Task 17 变异检验补强）
#
# 🔴 **本节是 Task 6 假绿的直接教训**：改造前 `h8_account_scope.py` /
# `h9_account_scope.py` 的槽仍写单族字面量 `fallback_standard_codes=("1641",)`，
# 而 tasks.md 标 `[x]`、`test_dual_family_codes.py` 全绿 —— 因为本文件当时**只测
# 真源自身**，一条断言都没钉「谁在用它」。2026-08-06 Task 17 变异检验（把兜底码
# 改回单族字面量）判出 GREEN 才暴露。
#
# 判据两层，缺一都会被绕过：
#   1. **运行时值比对** —— 槽的 `fallback_standard_codes` 必须**逐字等于**
#      `codes_for_cycle_slot(cycle, slot_key)`（源码字符串断言挡不住「引了常量
#      但引错槽」）；
#   2. **源码级禁字面量** —— 槽定义里不得直接写族内码（引常量才能让「改一处漏
#      一处」立刻暴露；这条挡的是「值恰好对但退回了硬编码」）。
# ═══════════════════════════════════════════════════════════════════════════

import re as _re
from pathlib import Path as _Path

import pytest as _pytest

from app.services.four_table.dual_family_codes import (
    ALL_DUAL_FAMILY_CODES as _ALL_DUAL_CODES,
    CYCLE_SLOT_TO_DUAL_FAMILY as _CYCLE_SLOT_MAP,
    codes_for_cycle_slot as _codes_for_cycle_slot,
)

_FOUR_TABLE_DIR = _Path(__file__).resolve().parents[2] / "app" / "services" / "four_table"

#: 双族消费方：(循环, scope 模块文件名, spec 常量名)
_DUAL_FAMILY_CONSUMERS = (
    ("H8", "h8_account_scope.py", "H8_ACCOUNT_SPEC"),
    ("H9", "h9_account_scope.py", "H9_ACCOUNT_SPEC"),
)


def _load_spec(module_file: str, const_name: str):
    import importlib

    mod = importlib.import_module(
        f"app.services.four_table.{module_file[:-3]}"
    )
    return getattr(mod, const_name)


def _strip_py_comments_and_docstrings(src: str) -> str:
    """剥 `#` 注释与三引号块 —— 注释里会写「改造前是 ("1641",)」这类反例。"""
    src = _re.sub(r'"""[\s\S]*?"""', "", src)
    src = _re.sub(r"'''[\s\S]*?'''", "", src)
    return _re.sub(r"(^|[^\"'])#[^\n]*", r"\1", src)


class TestConsumersUseTheSourceOfTruth:
    """H8/H9 的槽兜底码必须来自双族真源，且不得退回单族字面量。"""

    def test_consumer_map_covers_registered_cycle_slots(self):
        """登记表里的每个 (循环, 槽) 都要有对应消费方模块（防漏接第三个循环）。"""
        cycles = {c for (c, _s) in _CYCLE_SLOT_MAP}
        declared = {c for (c, _f, _n) in _DUAL_FAMILY_CONSUMERS}
        assert cycles == declared, (
            f"CYCLE_SLOT_TO_DUAL_FAMILY 覆盖循环 {sorted(cycles)}，"
            f"而消费方清单只声明 {sorted(declared)} —— 新增循环必须同时登记消费方"
        )

    @_pytest.mark.parametrize(("cycle", "module_file", "const_name"), _DUAL_FAMILY_CONSUMERS)
    def test_slot_fallback_codes_equal_source_of_truth(self, cycle, module_file, const_name):
        """运行时值比对：槽的兜底码 == `codes_for_cycle_slot(cycle, slot_key)`。"""
        spec = _load_spec(module_file, const_name)
        checked = 0
        for slot in spec.slots:
            expected = _codes_for_cycle_slot(cycle, slot.key)
            if not expected:
                # 该槽未登记双族 → 调用方保留自己的兜底码，本断言不管
                continue
            got = tuple(slot.fallback_standard_codes or ())
            assert got == expected, (
                f"{cycle} 槽 {slot.key!r} 的兜底码 {got} != 双族真源 {expected}。"
                f"退回单族会让在用新族的项目只取到极小比例（实证 0.04%）—— "
                f"比恒空更隐蔽，界面有值、零报错。"
            )
            checked += 1
        assert checked >= 1, (
            f"{cycle} 一个双族槽都没比对到 —— 槽键与 CYCLE_SLOT_TO_DUAL_FAMILY "
            f"的键不一致（登记表键: "
            f"{sorted(s for (c, s) in _CYCLE_SLOT_MAP if c == cycle)}，"
            f"spec 槽键: {[s.key for s in spec.slots]}）"
        )

    @_pytest.mark.parametrize(("cycle", "module_file", "const_name"), _DUAL_FAMILY_CONSUMERS)
    def test_slot_definition_has_no_single_family_literal(self, cycle, module_file, const_name):
        """源码级：槽定义里不得直接写族内码（必须引 `codes_for_cycle_slot`）。"""
        src = _strip_py_comments_and_docstrings(
            (_FOUR_TABLE_DIR / module_file).read_text(encoding="utf-8")
        )
        assert "codes_for_cycle_slot(" in src, (
            f"{module_file} 未引双族真源 `codes_for_cycle_slot` —— "
            f"写字面量时「改一处漏一处」不会被任何断言发现"
        )
        # 双族码不得作为字面量出现在 fallback 位置
        bad = [
            code
            for code in _ALL_DUAL_CODES
            if _re.search(rf'fallback_standard_codes\s*=\s*\(\s*["\']{code}["\']', src)
        ]
        assert bad == [], (
            f"{module_file} 的 fallback_standard_codes 直接写了族内码 {bad} —— "
            f"应改引 codes_for_cycle_slot({cycle!r}, <slot_key>)"
        )

    def test_selfcheck_single_family_literal_would_be_detected(self):
        """反向自检：单族字面量形态确实会被上一条检出。"""
        fake = 'fallback_standard_codes=("1641",),'
        hit = [
            c
            for c in _ALL_DUAL_CODES
            if _re.search(rf'fallback_standard_codes\s*=\s*\(\s*["\']{c}["\']', fake)
        ]
        assert hit == ["1641"], hit
        # 引常量的形态不得命中
        good = 'fallback_standard_codes=_GROSS_CODES,'
        assert [
            c
            for c in _ALL_DUAL_CODES
            if _re.search(rf'fallback_standard_codes\s*=\s*\(\s*["\']{c}["\']', good)
        ] == []

    def test_selfcheck_comment_stripping_is_effective(self):
        """反向自检：注释/docstring 里的反例不参与判定。"""
        src = '# 改造前: fallback_standard_codes=("1641",)\nx = 1'
        assert 'fallback_standard_codes=("1641"' in src
        assert 'fallback_standard_codes=("1641"' not in _strip_py_comments_and_docstrings(src)
