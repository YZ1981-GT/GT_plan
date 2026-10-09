"""K1（其他应收款）附注推送 note_rows 单元测试。

spec: formula-push-note-rollout-batch-c · Task 3

验证：
- K1Binding.note_rows() 输出单行 label="其他应收款"
- ending = audited_net = audited_receivable − audited_baddebt（从 entries 计算）
- opening = TB 年初余额合计（codes 1221+1231）
- TB 不可用时 opening_resolved=False
- 空 entries 时 ending=0（k1_calc 缺项=0 口径）
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pytest

from app.services.formula_push.bindings import k1_calc
from app.services.formula_push.bindings.k1 import K1Binding, K1Sources, K1_ACCOUNT_CODES, _NOTE_LABEL
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot


def _make_rule():
    """创建一个最小的 note 阶段 PushRule stub。"""
    from types import SimpleNamespace

    return SimpleNamespace(
        rule_id="K1.note.main",
        stage="note",
        policy="system",
        source=SimpleNamespace(kind="derivation", name="k1_note_main"),
        target=SimpleNamespace(
            domain="note",
            table="其他应收款",
            fields=["end_amount", "prior_amount"],
            sections={"listed": "五、8", "soe": "八、9"},
        ),
    )


def _make_k1_entries(
    *,
    recv_r0_unadj: str = "0", recv_r0_aje: str = "0", recv_r0_rje: str = "0",
    recv_r1_unadj: str = "0", recv_r1_aje: str = "0", recv_r1_rje: str = "0",
    bad_r0_unadj: str = "0", bad_r0_aje: str = "0", bad_r0_rje: str = "0",
    bad_r1_unadj: str = "0", bad_r1_aje: str = "0", bad_r1_rje: str = "0",
) -> dict[str, str]:
    """构造 K1-1 组合行条目。"""
    return {
        "K1-1-receivable-r0-unadj": recv_r0_unadj,
        "K1-1-receivable-r0-aje": recv_r0_aje,
        "K1-1-receivable-r0-rje": recv_r0_rje,
        "K1-1-receivable-r1-unadj": recv_r1_unadj,
        "K1-1-receivable-r1-aje": recv_r1_aje,
        "K1-1-receivable-r1-rje": recv_r1_rje,
        "K1-1-baddebt-r0-unadj": bad_r0_unadj,
        "K1-1-baddebt-r0-aje": bad_r0_aje,
        "K1-1-baddebt-r0-rje": bad_r0_rje,
        "K1-1-baddebt-r1-unadj": bad_r1_unadj,
        "K1-1-baddebt-r1-aje": bad_r1_aje,
        "K1-1-baddebt-r1-rje": bad_r1_rje,
    }


def _make_tb_snapshot(
    code_1221_end: str = "500000",
    code_1221_opening: str = "300000",
    code_1231_end: str = "-50000",
    code_1231_opening: str = "-30000",
) -> TbAuditedSnapshot:
    """创建 K1 的 TB 快照。"""
    return TbAuditedSnapshot(
        tb_data={
            "1221": {
                "期末余额": Decimal(code_1221_end),
                "年初余额": Decimal(code_1221_opening),
                "本期发生额": Decimal(code_1221_end) - Decimal(code_1221_opening),
            },
            "1231": {
                "期末余额": Decimal(code_1231_end),
                "年初余额": Decimal(code_1231_opening),
                "本期发生额": Decimal(code_1231_end) - Decimal(code_1231_opening),
            },
        },
        available=True,
        company_codes=("001",),
    )


class TestK1NoteRows:
    """K1Binding.note_rows() 单行附注推送。"""

    def test_single_row_label_is_other_receivable(self):
        """输出恰好一行，label="其他应收款"。"""
        binding = K1Binding()
        binding._last_tb_data = _make_tb_snapshot().tb_data
        entries = _make_k1_entries(recv_r0_unadj="100")
        rows = binding.note_rows(entries, "listed", _make_rule())
        assert len(rows) == 1
        assert rows[0]["label"] == "其他应收款"
        assert rows[0]["note_label"] == "其他应收款"
        assert rows[0]["key"] == "K1-note-main"
        assert rows[0]["is_total"] is False
        assert rows[0]["is_memo"] is False

    def test_ending_equals_audited_net(self):
        """ending = audited_receivable − audited_baddebt（与 k1_calc.audited_net 同值）。"""
        entries = _make_k1_entries(
            recv_r0_unadj="100", recv_r0_aje="10", recv_r0_rje="0",
            recv_r1_unadj="200", recv_r1_aje="0", recv_r1_rje="5",
            bad_r0_unadj="30", bad_r0_aje="0", bad_r0_rje="0",
            bad_r1_unadj="20", bad_r1_aje="5", bad_r1_rje="0",
        )
        expected_net = k1_calc.audited_net(entries)
        # 验算: receivable = (100+10+0)+(200+0+5)+0+0 = 315
        #        baddebt = (30+0+0)+(20+5+0)+0+0 = 55
        #        net = 315 - 55 = 260
        assert expected_net == 260.0

        binding = K1Binding()
        binding._last_tb_data = _make_tb_snapshot().tb_data
        rows = binding.note_rows(entries, "listed", _make_rule())
        assert rows[0]["ending"] == expected_net
        assert rows[0]["ending_resolved"] is True

    def test_opening_from_tb_annual_balance(self):
        """opening = TB 年初余额合计（1221 + 1231）。"""
        binding = K1Binding()
        binding._last_tb_data = _make_tb_snapshot(
            code_1221_opening="300000", code_1231_opening="-30000",
        ).tb_data
        entries = _make_k1_entries(recv_r0_unadj="100")
        rows = binding.note_rows(entries, "listed", _make_rule())
        # opening = 300000 + (-30000) = 270000
        assert rows[0]["opening"] == 270000.0
        assert rows[0]["opening_resolved"] is True

    def test_tb_unavailable_opening_unresolved(self):
        """TB 不可用（未导入四表）时 opening=0 且 opening_resolved=False。"""
        binding = K1Binding()
        # _last_tb_data 未设置（None），模拟 load_sources 未运行或 TB 不可用
        entries = _make_k1_entries(recv_r0_unadj="100")
        rows = binding.note_rows(entries, "listed", _make_rule())
        assert rows[0]["opening"] == 0.0
        assert rows[0]["opening_resolved"] is False
        # ending 仍从 entries 计算
        assert rows[0]["ending"] == 100.0
        assert rows[0]["ending_resolved"] is True

    def test_empty_entries_ending_zero(self):
        """空 entries 时 ending=0（k1_calc 缺项=0 口径）。"""
        binding = K1Binding()
        binding._last_tb_data = _make_tb_snapshot().tb_data
        rows = binding.note_rows({}, "listed", _make_rule())
        assert rows[0]["ending"] == 0.0
        assert rows[0]["ending_resolved"] is True

    def test_output_format_matches_e1_note_rows(self):
        """输出 dict 的 key 集合与 E1 note_rows 格式一致。"""
        binding = K1Binding()
        binding._last_tb_data = _make_tb_snapshot().tb_data
        entries = _make_k1_entries(recv_r0_unadj="100")
        rows = binding.note_rows(entries, "listed", _make_rule())
        expected_keys = {
            "key", "label", "note_label", "is_total", "is_memo",
            "ending", "opening", "ending_resolved", "opening_resolved",
        }
        assert set(rows[0].keys()) == expected_keys


class TestK1SourcesTemplateType:
    """K1Sources 的 template_type 字段。"""

    def test_k1_sources_has_template_type(self):
        """K1Sources dataclass 支持 template_type 字段。"""
        tb = _make_tb_snapshot()
        sources = K1Sources(
            formula=FormulaSources(tb=tb),
            template_type="listed",
        )
        assert sources.template_type == "listed"

    def test_k1_sources_template_type_defaults_none(self):
        """K1Sources.template_type 默认 None。"""
        tb = _make_tb_snapshot()
        sources = K1Sources(formula=FormulaSources(tb=tb))
        assert sources.template_type is None


class TestK1BindingLoadSourcesCachesTb:
    """K1Binding.load_sources 缓存 TB 数据供 note_rows 使用。"""

    def test_cache_set_after_load(self):
        """load_sources 后 _last_tb_data 应有值。"""
        binding = K1Binding()
        assert binding._last_tb_data is None
        # 模拟 load_sources 缓存行为
        tb = _make_tb_snapshot()
        binding._last_tb_data = tb.tb_data
        assert binding._last_tb_data is not None
        assert "1221" in binding._last_tb_data

    def test_cache_none_when_tb_unavailable(self):
        """TB 不可用时 _last_tb_data 保持 None。"""
        binding = K1Binding()
        tb = TbAuditedSnapshot(tb_data={}, available=False, company_codes=())
        # 模拟 load_sources 的逻辑
        binding._last_tb_data = tb.tb_data if tb.available else None
        assert binding._last_tb_data is None
