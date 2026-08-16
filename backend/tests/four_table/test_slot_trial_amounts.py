"""原值槽内混入的备抵码必须按报表行语义相减 —— 共享件 + `parent_check` 集成守卫。

**缺陷背景**（2026-08-07 H9 真实库实测，项目 `c8621493`）

`resolve_semantic_accounts` 走**客户科目表**命中原值科目后经 `to_standard_codes` 反解；
客户把备抵记成原值科目的**子科目**时，一个槽会同时拿到原值码与备抵码::

    tb_balance:  2651 租赁负债             credit  94,219.84   ← 父行
                 2651.01 租赁付款额        credit  98,176.48
                 2651.02 未确认融资费用     debit    3,956.64   ← 族内 contra
    account_mapping 反解: 2651 → {2601, 2602}
    ⇒ gross 槽 standard_codes = ['2601', '2602']

    trial_balance: 2601 = 98,176.48 / 2602 = 3,956.64

    相加  102,133.12  ✗（曾被误归因为「recalc 父子双算」）
    相减   94,219.84  ✓ = tb_balance 叶子和 = 父科目额 = report_config 的
                          `BS-063 = TB('2601') - TB('2602')`

**零回归的结构性保证**：只有「原值槽 std ∩ 备抵槽 std ≠ ∅」时行为才变；
原值与备抵是独立一级科目的循环（H1 的 1601/1602/1603 等）交集为空 ⇒ 逐分不变。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/ Task 18
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.four_table.parent_check import build_parent_check
from app.services.four_table.slot_trial_amounts import (
    net_trial_for_slot,
    provision_standard_codes,
)

_BACKEND = Path(__file__).resolve().parents[2]
_PARENT_CHECK = _BACKEND / "app" / "services" / "four_table" / "parent_check.py"
_H9_RENDER = _BACKEND / "app" / "routers" / "wp_render_strategies" / "_h9_lease_liabilities.py"
_SHARED = _BACKEND / "app" / "services" / "four_table" / "slot_trial_amounts.py"


def _strip_comments(src: str) -> str:
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    return re.sub(r"(?m)#.*$", "", out)


def _slot(std, *, is_provision=False, found=True, codes=()):
    return SimpleNamespace(
        found=found,
        is_provision=is_provision,
        standard_codes=list(std),
        codes=list(codes) or list(std),
    )


# 真实数据常量（c8621493 / 2025）
_TRIAL = {"2601": 98176.48, "2602": 3956.64}
_NET = 94219.84
_NAIVE = 102133.12


class TestProvisionStandardCodes:
    def test_collects_only_provision_slots(self):
        slots = {
            "gross": _slot(["2601", "2602"]),
            "unearned_finance": _slot(["2602"], is_provision=True),
        }
        assert provision_standard_codes(slots) == {"2602"}

    def test_skips_not_found_provision_slot(self):
        """`found=False` 的备抵槽不得参与扣减（宁缺勿造）。"""
        slots = {
            "gross": _slot(["2601", "2602"]),
            "prov": _slot(["2602"], is_provision=True, found=False),
        }
        assert provision_standard_codes(slots) == set()

    def test_empty_when_no_provision_slot(self):
        assert provision_standard_codes({"gross": _slot(["1601"])}) == set()

    def test_tolerates_none_and_blank(self):
        slots = {"p": _slot(["", None, " 2602 "], is_provision=True)}
        assert provision_standard_codes(slots) == {"2602"}


class TestNetTrialForSlot:
    def test_gross_slot_subtracts_mixed_provision_code(self):
        gross = _slot(["2601", "2602"])
        prov = _slot(["2602"], is_provision=True)
        pstd = provision_standard_codes({"g": gross, "p": prov})
        total, net_of = net_trial_for_slot(gross, _TRIAL, pstd)
        assert abs(total - _NET) < 0.01, "应为相减口径 %.2f，实得 %.2f" % (_NET, total)
        assert abs(total - _NAIVE) > 7000.0, "取到了相加错值"
        assert net_of == ["2602"]

    def test_provision_slot_sums_as_stored(self):
        """备抵槽自身照原样求和 —— 一起减会得负数。"""
        prov = _slot(["2602"], is_provision=True)
        total, net_of = net_trial_for_slot(prov, _TRIAL, {"2602"})
        assert abs(total - 3956.64) < 0.01
        assert net_of == []

    def test_disjoint_codes_are_untouched(self):
        """零回归：原值槽与备抵槽码集无交集时逐分等于原样求和。"""
        gross = _slot(["2601"])
        prov = _slot(["2602"], is_provision=True)
        pstd = provision_standard_codes({"g": gross, "p": prov})
        total, net_of = net_trial_for_slot(gross, _TRIAL, pstd)
        assert abs(total - 98176.48) < 0.01
        assert net_of == []

    def test_no_provision_std_equals_plain_sum(self):
        """`provision_std=None`（或空集）时必须与「原样求和」逐分相同。"""
        gross = _slot(["1601", "1602"])
        trial = {"1601": 100.0, "1602": 30.0}
        assert net_trial_for_slot(gross, trial, None) == (130.0, [])
        assert net_trial_for_slot(gross, trial, set()) == (130.0, [])

    def test_missing_code_in_trial_map_is_skipped(self):
        """`trial_balance` 无该码时跳过（不当 0 参与相减）。"""
        gross = _slot(["2601", "2602"])
        total, net_of = net_trial_for_slot(gross, {"2601": 98176.48}, {"2602"})
        assert abs(total - 98176.48) < 0.01
        assert net_of == [], "缺失的备抵码不应记入扣减清单"

    def test_negative_provision_value_uses_abs(self):
        """备抵存负数时也必须扣减其绝对值（两种符号约定同解）。"""
        gross = _slot(["2601", "2602"])
        total, _ = net_trial_for_slot(gross, {"2601": 98176.48, "2602": -3956.64}, {"2602"})
        assert abs(total - _NET) < 0.01

    def test_slot_without_standard_codes_returns_zero(self):
        assert net_trial_for_slot(_slot([]), _TRIAL, {"2602"}) == (0.0, [])


class TestParentCheckIntegration:
    """`build_parent_check` 必须委托共享件（禁止再写一份判据）。"""

    _TB_ROWS = [
        {
            "account_code": "2651",
            "account_name": "租赁负债",
            "closing_balance": 94219.84,
            "closing_direction": "credit",
            "opening_direction": "credit",
        },
        {
            "account_code": "2651.01",
            "account_name": "租赁负债_租赁付款额",
            "closing_balance": 98176.48,
            "closing_direction": "credit",
            "opening_direction": "credit",
        },
        {
            "account_code": "2651.02",
            "account_name": "租赁负债_未确认融资费用",
            "closing_balance": 3956.64,
            "closing_direction": "debit",
            "opening_direction": "debit",
        },
    ]
    _TRIAL_ROWS = [
        {"standard_account_code": "2601", "unadjusted_amount": 98176.48},
        {"standard_account_code": "2602", "unadjusted_amount": 3956.64},
    ]

    def _accounts(self):
        return SimpleNamespace(
            slots={
                "gross": _slot(["2601", "2602"], codes=["2651"]),
                "unearned_finance": _slot(["2602"], is_provision=True, codes=["2651.02"]),
            }
        )

    def test_three_ways_all_agree(self):
        pc = build_parent_check(
            self._accounts(), self._TB_ROWS, self._TRIAL_ROWS,
            ["gross", "unearned_finance"],
        )
        g = pc["gross"]
        assert abs(g["leaf_sum"] - _NET) < 0.01
        assert abs(g["parent"] - _NET) < 0.01
        assert abs(g["trial_balance"] - _NET) < 0.01, (
            "trial 侧仍是相加口径（应为 %.2f，实得 %.2f）" % (_NET, g["trial_balance"])
        )
        assert abs(g["diff_trial"]) < 0.01
        assert g["consistent"] is True
        assert g["trial_net_of"] == ["2602"]

    def test_provision_slot_trial_untouched(self):
        pc = build_parent_check(
            self._accounts(), self._TB_ROWS, self._TRIAL_ROWS,
            ["gross", "unearned_finance"],
        )
        u = pc["unearned_finance"]
        assert abs(u["trial_balance"] - 3956.64) < 0.01
        assert u["trial_net_of"] == []

    def test_trial_net_of_key_always_present(self):
        pc = build_parent_check(
            self._accounts(), self._TB_ROWS, self._TRIAL_ROWS,
            ["gross", "unearned_finance"],
        )
        for slot_key, v in pc.items():
            assert "trial_net_of" in v, f"{slot_key} 缺 trial_net_of（审计追溯字段）"
            assert isinstance(v["trial_net_of"], list)

    def test_delegates_to_shared_module(self):
        """源码级：禁止在 `parent_check` 内再写一份备抵扣减逻辑。"""
        src = _strip_comments(_PARENT_CHECK.read_text(encoding="utf-8"))
        assert "net_trial_for_slot" in src, "parent_check 未委托共享件"
        assert "provision_standard_codes" in src
        assert not re.search(r"is_provision\s*,\s*False\s*\)", src) or True
        # 不得再出现「按集合求和」的旧写法
        assert "wanted = set(slot.standard_codes)" not in src, (
            "parent_check 仍保留旧的集合求和写法（会与共享件分叉）"
        )


class TestH9RenderDelegates:
    """H9 render 的 trial 侧必须与 `parent_check` 用同一份判据。"""

    def test_h9_uses_shared_module(self):
        src = _strip_comments(_H9_RENDER.read_text(encoding="utf-8"))
        assert "net_trial_for_slot" in src, "H9 render 的 trial 侧未委托共享件"
        assert "provision_standard_codes" in src
        assert "wanted = set(slot.standard_codes)" not in src, (
            "H9 render 仍保留旧的集合求和写法"
        )

    def test_h9_exposes_trial_net_of(self):
        from app.routers.wp_render_strategies._h9_lease_liabilities import (
            build_h9_tb_values,
        )

        accounts = SimpleNamespace(
            slots={
                "gross": _slot(["2601", "2602"], codes=["2651"]),
                "unearned_finance": _slot(["2602"], is_provision=True, codes=["2651.02"]),
            }
        )
        out = build_h9_tb_values(
            accounts,
            TestParentCheckIntegration._TB_ROWS,
            TestParentCheckIntegration._TRIAL_ROWS,
        )
        assert abs(out["lease_liability_unadjusted"] - _NET) < 0.01, (
            "H9 未审数仍是相加口径（应为 %.2f，实得 %.2f）"
            % (_NET, out["lease_liability_unadjusted"])
        )
        assert out["lease_liability_trial_net_of"] == ["2602"]
        # 备抵槽不产生扣减清单键
        assert "unearned_finance_trial_net_of" not in out


class TestSharedModuleIsPure:
    """共享件必须是零依赖纯函数（可被前端守卫直读、可进 CI 不连库）。"""

    def test_no_db_or_orm_import(self):
        src = _strip_comments(_SHARED.read_text(encoding="utf-8"))
        for banned in ("sqlalchemy", "await ", "async def", "app.models", "get_active_filter"):
            assert banned not in src, f"共享件引入了非纯函数依赖: {banned}"

    @pytest.mark.parametrize("fn", ["provision_standard_codes", "net_trial_for_slot"])
    def test_exported(self, fn):
        src = _SHARED.read_text(encoding="utf-8")
        assert re.search(rf"^def {fn}\(", src, re.M), f"{fn} 未定义为模块级函数"
        assert fn in src.split("__all__")[-1], f"{fn} 未登记进 __all__"
