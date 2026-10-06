"""NoteDirectBinding 族 binding 单元测试。

spec: formula-push-note-rollout-batch-d · Task 1~3
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.formula_push.bindings import (
    PushBinding,
    _validate_binding,
    register_binding,
    get_binding,
)
from app.services.formula_push.bindings.note_direct import (
    NoteDirectBinding,
    NoteDirectSources,
    note_direct_for,
)


# ── 工厂 + 协议 ────────────────────────────────────────────────────────────


class TestNoteDirectFactory:
    """note_direct_for 工厂按 wp_account_mapping 实例化。"""

    def test_single_account_code(self):
        binding = note_direct_for("D1")
        assert binding.wp_code == "D1"
        assert binding.account_prefixes == ("1121",)
        assert binding._is_income is False
        assert binding._account_name == "应收票据"

    def test_income_account_detected(self):
        """损益类科目（6 开头）自动识别。"""
        binding = note_direct_for("K8")
        assert binding._is_income is True
        assert "6601" in binding.account_prefixes

    def test_multi_account_codes(self):
        """F2 存货有 6 个科目码。"""
        binding = note_direct_for("F2")
        assert len(binding.account_prefixes) == 6
        assert "1401" in binding.account_prefixes

    def test_unknown_code_raises(self):
        with pytest.raises(KeyError, match="不存在"):
            note_direct_for("ZZ")

    def test_passes_protocol_validation(self):
        """工厂产物通过 PushBinding 协议校验。"""
        binding = note_direct_for("G1")
        validated = _validate_binding("G1", binding)
        assert isinstance(validated, PushBinding)

    def test_registry_string_form(self):
        """注册表字符串形式能正确解析和实例化（用未注册码测试）。"""
        # G11 仍在 NoteDirectBinding _REGISTRY，用 get_binding 直接验证
        binding = get_binding("G11")
        assert binding.wp_code == "G11"
        assert isinstance(binding, NoteDirectBinding)


# ── note_rows ───────────────────────────────────────────────────────────────


def _make_tb_data(codes_values: dict[str, dict[str, float]]) -> dict[str, dict[str, Decimal]]:
    """构造 TB 快照数据。"""
    return {
        code: {col: Decimal(str(val)) for col, val in cols.items()}
        for code, cols in codes_values.items()
    }


class TestNoteRows:
    """note_rows() 从 TB 取审定数构建附注行。"""

    def test_single_code_balance_sheet(self):
        """非损益、单科目：一行，ending=期末余额, opening=年初余额。"""
        binding = NoteDirectBinding("G1", ("1101",), "交易性金融资产")
        binding._last_tb_data = _make_tb_data({
            "1101": {"期末余额": 100000.0, "年初余额": 80000.0, "本期发生额": 20000.0},
        })
        rule = SimpleNamespace(rule_id="G1.note.main", target=SimpleNamespace(domain="note"))
        rows = binding.note_rows({}, "listed", rule)
        assert len(rows) == 1
        r = rows[0]
        assert r["key"] == "G1-note-1101"
        assert r["label"] == "交易性金融资产"
        assert r["ending"] == 100000.0
        assert r["opening"] == 80000.0
        assert r["is_total"] is False
        assert r["ending_resolved"] is True

    def test_single_code_income_statement(self):
        """损益类科目：ending=本期发生额, opening=年初余额。"""
        binding = NoteDirectBinding("K8", ("6601",), "销售费用", is_income=True)
        binding._last_tb_data = _make_tb_data({
            "6601": {"期末余额": 500000.0, "年初余额": 400000.0, "本期发生额": 100000.0},
        })
        rule = SimpleNamespace(rule_id="K8.note.main", target=SimpleNamespace(domain="note"))
        rows = binding.note_rows({}, "listed", rule)
        assert len(rows) == 1
        r = rows[0]
        assert r["ending"] == 100000.0  # 本期发生额，非期末余额
        assert r["opening"] == 400000.0  # 年初余额

    def test_multi_code_with_total(self):
        """多科目（F2 存货）：每码一行 + 合计行。"""
        codes = ("1401", "1402")
        binding = NoteDirectBinding("F2", codes, "存货")
        binding._last_tb_data = _make_tb_data({
            "1401": {"期末余额": 200000.0, "年初余额": 150000.0, "本期发生额": 50000.0},
            "1402": {"期末余额": 100000.0, "年初余额": 80000.0, "本期发生额": 20000.0},
        })
        rule = SimpleNamespace(rule_id="F2.note.main", target=SimpleNamespace(domain="note"))
        rows = binding.note_rows({}, "listed", rule)
        assert len(rows) == 3  # 2 明细 + 1 合计
        assert rows[0]["label"] == "存货_1401"
        assert rows[1]["label"] == "存货_1402"
        assert rows[2]["is_total"] is True
        assert rows[2]["ending"] == 300000.0
        assert rows[2]["opening"] == 230000.0
        assert rows[2]["label"] == "存货"

    def test_no_tb_data_returns_empty(self):
        """TB 不可用时返回空列表。"""
        binding = NoteDirectBinding("G1", ("1101",), "交易性金融资产")
        binding._last_tb_data = None
        rule = SimpleNamespace(rule_id="G1.note.main", target=SimpleNamespace(domain="note"))
        rows = binding.note_rows({}, "listed", rule)
        assert rows == []

    def test_missing_code_in_tb_returns_zero_unresolved(self):
        """TB 中无该科目，值为 0 且 resolved=False。"""
        binding = NoteDirectBinding("G1", ("1101",), "交易性金融资产")
        binding._last_tb_data = _make_tb_data({})  # 空 TB
        rule = SimpleNamespace(rule_id="G1.note.main", target=SimpleNamespace(domain="note"))
        rows = binding.note_rows({}, "listed", rule)
        assert len(rows) == 1
        assert rows[0]["ending"] == 0.0
        assert rows[0]["ending_resolved"] is False


# ── apply ───────────────────────────────────────────────────────────────────


class TestApply:
    """apply() 单值键写入。"""

    def test_writes_formatted_value(self):
        binding = NoteDirectBinding("G1", ("1101",), "交易性金融资产")
        entries: dict = {}
        target = SimpleNamespace(item_id="G1-1-tb-amount-ending")
        changed = binding.apply(entries, target, 123456.0)
        assert changed is True
        assert entries["G1-1-tb-amount-ending"] == "123456"

    def test_none_writes_empty_string(self):
        binding = NoteDirectBinding("G1", ("1101",), "交易性金融资产")
        entries: dict = {}
        target = SimpleNamespace(item_id="G1-1-tb-amount-ending")
        binding.apply(entries, target, None)
        assert entries["G1-1-tb-amount-ending"] == ""

    def test_no_change_returns_false(self):
        binding = NoteDirectBinding("G1", ("1101",), "交易性金融资产")
        entries = {"G1-1-tb-amount-ending": "100"}
        target = SimpleNamespace(item_id="G1-1-tb-amount-ending")
        changed = binding.apply(entries, target, 100.0)
        assert changed is False


# ── entry_warnings ──────────────────────────────────────────────────────────


def test_entry_warnings_returns_empty():
    binding = NoteDirectBinding("G1", ("1101",), "交易性金融资产")
    assert binding.entry_warnings({}) == []
