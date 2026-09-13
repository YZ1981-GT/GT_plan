# -*- coding: utf-8 -*-
"""D4-1 TB 发布决策守卫（Task 4.2 / Req 2.4, 1.5, 2.2, 2.5）。

行为级断言 + 变异反向自检。覆盖：模式切换不触发、差异阈值二次确认、只读 fail-closed、
发布来源是快照不偷换 TB、非法入参拒绝。
"""

from __future__ import annotations

from decimal import Decimal

from app.services.d4_extraction.d4_1_tb_publish import (
    D4_1_MAIN_ACCOUNT_CODE,
    D4_1_OTHER_ACCOUNT_CODE,
    D4_1_TB_DIFF_THRESHOLD,
    decide_d4_1_tb_publish,
)


def _publish_ok_kwargs(**overrides):
    base = dict(
        trigger="manual_confirm",
        snapshot_audited_total="1000.00",
        tb_check_value="1000.00",
        main_audited="800.00",
        other_audited="200.00",
        is_readonly=False,
        second_confirmed=False,
    )
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Req 1.5：模式切换恒不发布（优先级最高）
# ─────────────────────────────────────────────────────────────────────────────
class TestModeSwitchNeverPublishes:
    def test_mode_switch_blocked_even_when_diff_zero(self):
        d = decide_d4_1_tb_publish(**_publish_ok_kwargs(trigger="mode_switch"))
        assert d.outcome == "blocked_mode_switch"
        assert d.should_publish is False

    def test_mode_switch_blocked_even_when_confirmed(self):
        d = decide_d4_1_tb_publish(
            **_publish_ok_kwargs(trigger="mode_switch", second_confirmed=True)
        )
        assert d.outcome == "blocked_mode_switch"
        assert d.should_publish is False


# ─────────────────────────────────────────────────────────────────────────────
# Req 2.4：差异阈值二次确认
# ─────────────────────────────────────────────────────────────────────────────
class TestDiffThreshold:
    def test_within_threshold_publishes(self):
        # 差异 0.004 < 0.005 → 直接发布
        d = decide_d4_1_tb_publish(
            **_publish_ok_kwargs(snapshot_audited_total="1000.004", tb_check_value="1000.000")
        )
        assert d.outcome == "publish"
        assert d.should_publish is True
        assert d.needs_confirm is False

    def test_over_threshold_needs_confirm(self):
        # 差异 0.01 > 0.005 → 需二次确认
        d = decide_d4_1_tb_publish(
            **_publish_ok_kwargs(snapshot_audited_total="1000.01", tb_check_value="1000.00")
        )
        assert d.outcome == "needs_second_confirm"
        assert d.should_publish is False
        assert d.needs_confirm is True
        assert d.diff == Decimal("0.01")

    def test_over_threshold_confirmed_publishes(self):
        d = decide_d4_1_tb_publish(
            **_publish_ok_kwargs(
                snapshot_audited_total="1000.01", tb_check_value="1000.00", second_confirmed=True
            )
        )
        assert d.outcome == "publish"
        assert d.should_publish is True

    def test_exactly_at_threshold_no_confirm(self):
        # 差异恰为 0.005，不 > 阈值 → 直接发布（阈值是「大于」）
        d = decide_d4_1_tb_publish(
            **_publish_ok_kwargs(snapshot_audited_total="1000.005", tb_check_value="1000.000")
        )
        assert d.outcome == "publish"
        assert d.needs_confirm is False


# ─────────────────────────────────────────────────────────────────────────────
# Req 2.5：只读 fail-closed
# ─────────────────────────────────────────────────────────────────────────────
class TestReadonly:
    def test_readonly_blocked(self):
        d = decide_d4_1_tb_publish(**_publish_ok_kwargs(is_readonly=True))
        assert d.outcome == "blocked_readonly"
        assert d.should_publish is False


# ─────────────────────────────────────────────────────────────────────────────
# Req 2.2/2.4：发布来源是快照拆分金额，不偷换 TB
# ─────────────────────────────────────────────────────────────────────────────
class TestPublishSourceIsSnapshot:
    def test_publish_amounts_from_snapshot_not_tb(self):
        d = decide_d4_1_tb_publish(
            **_publish_ok_kwargs(
                snapshot_audited_total="1000.00",
                tb_check_value="9999.00",  # TB 值故意不同
                main_audited="800.00",
                other_audited="200.00",
                second_confirmed=True,  # 差异超阈值，确认后发布
            )
        )
        assert d.outcome == "publish"
        # 发布金额来自快照拆分（6001/6051），不是 TB 值
        assert d.publish_amounts[D4_1_MAIN_ACCOUNT_CODE] == Decimal("800.00")
        assert d.publish_amounts[D4_1_OTHER_ACCOUNT_CODE] == Decimal("200.00")
        assert Decimal("9999.00") not in d.publish_amounts.values()

    def test_no_publish_amounts_when_not_publishing(self):
        d = decide_d4_1_tb_publish(**_publish_ok_kwargs(trigger="mode_switch"))
        assert d.publish_amounts == {}


# ─────────────────────────────────────────────────────────────────────────────
# 非法入参 fail-closed
# ─────────────────────────────────────────────────────────────────────────────
class TestInvalidInputs:
    def test_missing_snapshot_invalid(self):
        d = decide_d4_1_tb_publish(**_publish_ok_kwargs(snapshot_audited_total=None))
        assert d.outcome == "invalid"
        assert d.should_publish is False

    def test_nonnumeric_tb_invalid(self):
        d = decide_d4_1_tb_publish(**_publish_ok_kwargs(tb_check_value="abc"))
        assert d.outcome == "invalid"

    def test_missing_publish_amount_invalid(self):
        d = decide_d4_1_tb_publish(**_publish_ok_kwargs(main_audited=None, second_confirmed=True))
        assert d.outcome == "invalid"


# ─────────────────────────────────────────────────────────────────────────────
# 常量锁死
# ─────────────────────────────────────────────────────────────────────────────
class TestConstants:
    def test_threshold_value(self):
        assert D4_1_TB_DIFF_THRESHOLD == Decimal("0.005")

    def test_account_codes(self):
        assert D4_1_MAIN_ACCOUNT_CODE == "6001"
        assert D4_1_OTHER_ACCOUNT_CODE == "6051"


# ─────────────────────────────────────────────────────────────────────────────
# 变异反向自检：模式切换若被误判为可发布，测试必红
# ─────────────────────────────────────────────────────────────────────────────
class TestMutationReverseCheck:
    def test_manual_confirm_is_the_only_publish_trigger(self):
        """反向：只有 manual_confirm 能进入发布路径。"""
        d = decide_d4_1_tb_publish(**_publish_ok_kwargs(trigger="mode_switch"))
        assert not d.should_publish
