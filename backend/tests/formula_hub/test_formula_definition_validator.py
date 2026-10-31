"""服务端统一公式定义校验（需求 12.1、12.2，ADR-FHIC-09）。

域 × 入口参数化测试 + 常量零除数检查。
变异 #33：validator 在 write_project 处摘除 → 本文件红。
变异 #34：常量零除数检查摘除 → 本文件 ``1/(2-2)`` 红。
"""
from __future__ import annotations

import pytest

from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.validator import validate_formula_definition

# ── 域 × 样例参数化 ──────────────────────────────────────────────────────────

# 各域应拒绝的坏式
REPORT_BAD = [
    ("EVIL(((", "解析失败"),
    ("TB('1001'", "不闭合"),
    ("1/0", "常量零除数"),
    ("1/(2-2)", "常量零除数（表达式折叠）"),
    ("100/(5*2-10)", "常量零除数（复杂折叠）"),
]

# 各域应通过的正常公式
REPORT_GOOD = [
    "TB('1001','审定数')",
    "1/TB('1001','审定数')",
    "ROW('BS-001')+ROW('BS-002')",
    "IF(TB('1001','审定数')>0,ROW('BS-001'),0)",
    "ABS(TB('1002','期末余额'))",
    "TB('1001','期末余额')/TB('1002','期末余额')",  # 运行时除法，不拒
]

# 报表族三域（report / tb_detail / cross_check）共享校验逻辑
REPORT_FAMILY_DOMAINS = ["report", "tb_detail", "cross_check"]

# 附注正向用例
NOTE_GOOD = ["cell(1,2)"]
# 底稿正向用例（须经过 checked_wp_definition + classify_formula）
WP_GOOD = ["TB('1001','审定数')"]


class TestReportFamilyRejectBadFormulas:
    """report / tb_detail / cross_check 域拒绝坏式（需求 12.1）。"""

    @pytest.mark.parametrize("domain", REPORT_FAMILY_DOMAINS)
    @pytest.mark.parametrize("formula,reason", REPORT_BAD, ids=[b[1] for b in REPORT_BAD])
    def test_bad_formula_rejected(self, domain: str, formula: str, reason: str) -> None:
        defn = _make_definition(domain, formula)
        with pytest.raises(FormulaSettingError) as exc_info:
            validate_formula_definition(domain, defn, label=f"测试-{domain}")
        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "FORMULA_DEFINITION_INVALID"


class TestReportFamilyAcceptGoodFormulas:
    """report / tb_detail / cross_check 域通过正常公式（需求 12.1）。"""

    @pytest.mark.parametrize("domain", REPORT_FAMILY_DOMAINS)
    @pytest.mark.parametrize("formula", REPORT_GOOD)
    def test_good_formula_accepted(self, domain: str, formula: str) -> None:
        defn = _make_definition(domain, formula)
        validate_formula_definition(domain, defn, label=f"测试-{domain}")


class TestConstantZeroDivisor:
    """常量零除数检查（需求 12.1）：``1/(2-2)`` 拒、``1/TB(...)`` 过。"""

    def test_direct_zero_rejected(self) -> None:
        with pytest.raises(FormulaSettingError) as exc_info:
            validate_formula_definition("report", {"formula": "1/0"}, label="测试")
        assert exc_info.value.status_code == 422
        assert "除数恒为 0" in exc_info.value.message

    def test_expression_folding_rejected(self) -> None:
        """``1/(2-2)`` → 折叠为 0 → 拒绝。"""
        with pytest.raises(FormulaSettingError) as exc_info:
            validate_formula_definition("report", {"formula": "1/(2-2)"}, label="测试")
        assert exc_info.value.status_code == 422
        assert "除数恒为 0" in exc_info.value.message

    def test_complex_folding_rejected(self) -> None:
        """``100/(5*2-10)`` → 折叠为 0 → 拒绝。"""
        with pytest.raises(FormulaSettingError) as exc_info:
            validate_formula_definition("report", {"formula": "100/(5*2-10)"}, label="测试")
        assert exc_info.value.status_code == 422

    def test_runtime_divisor_accepted(self) -> None:
        """``1/TB('1001','审定数')`` → 运行时取数，不在编译期拒。"""
        validate_formula_definition("report", {"formula": "1/TB('1001','审定数')"}, label="测试")

    def test_runtime_row_divisor_accepted(self) -> None:
        """``1/ROW('BS-001')`` → 运行时引用，不拒。"""
        validate_formula_definition("report", {"formula": "1/ROW('BS-001')"}, label="测试")


class TestLengthAndNesting:
    """长度 ≤4000、括号嵌套 ≤50。"""

    def test_length_exceeded(self) -> None:
        long_formula = "TB('1001','审定数')" + "+1" * 2000
        with pytest.raises(FormulaSettingError) as exc_info:
            validate_formula_definition("report", {"formula": long_formula}, label="测试")
        assert exc_info.value.status_code == 422
        assert "长度" in exc_info.value.message

    def test_nesting_exceeded(self) -> None:
        nested = "(" * 51 + "1" + ")" * 51
        with pytest.raises(FormulaSettingError) as exc_info:
            validate_formula_definition("report", {"formula": nested}, label="测试")
        assert exc_info.value.status_code == 422
        assert "嵌套" in exc_info.value.message

    def test_within_limits_ok(self) -> None:
        formula = "(" * 50 + "1" + ")" * 50
        validate_formula_definition("report", {"formula": formula}, label="测试")


class TestNoneAndDisabledPassThrough:
    """None 定义不校验；disabled=true 只做结构检查。"""

    @pytest.mark.parametrize("domain", REPORT_FAMILY_DOMAINS + ["wp", "note", "consol_note", "push"])
    def test_none_definition_ok(self, domain: str) -> None:
        validate_formula_definition(domain, None, label="测试")

    @pytest.mark.parametrize("domain", REPORT_FAMILY_DOMAINS)
    def test_disabled_definition_ok(self, domain: str) -> None:
        validate_formula_definition(domain, {"disabled": True}, label="测试")


class TestDomainSpecificPassthrough:
    """各域正向用例。"""

    def test_note_good(self) -> None:
        for formula in NOTE_GOOD:
            validate_formula_definition("note", {"formula": formula, "category": "auto_calc"}, label="测试")

    def test_wp_good(self) -> None:
        for formula in WP_GOOD:
            validate_formula_definition("wp", {"expression": formula, "formula_type": "auto_calc"}, label="测试")


class TestStoreWriteEntryPoints:
    """通过 store 写入方法验证 validator 接入（变异 #33 守卫）。

    SettingStore 是 tb_detail / cross_check / note 等域的基类存储，
    必须在 write_global 和 write_project 里调 validate_formula_definition。
    """

    @pytest.mark.asyncio
    async def test_setting_store_write_project_rejects_bad_formula(self) -> None:
        """SettingStore.write_project 拒绝坏式（变异 #33 目标）。"""
        from unittest.mock import AsyncMock

        from app.services.formula_settings.stores import SettingStore
        store = SettingStore("tb_detail")
        store._find = AsyncMock(return_value=None)  # 不真正查库
        db = AsyncMock()
        import uuid
        with pytest.raises(FormulaSettingError) as exc_info:
            await store.write_project(
                db, uuid.uuid4(), "test_slot",
                definition={"formula": "1/(2-2)"},
                base_definition=None, base_version=None,
                pinned=False, base_origin=None, base_template_id=None,
                user_id=uuid.uuid4(),
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_setting_store_write_global_rejects_bad_formula(self) -> None:
        """SettingStore.write_global 拒绝坏式。"""
        from unittest.mock import AsyncMock

        from app.services.formula_settings.stores import SettingStore
        store = SettingStore("tb_detail")
        store._find = AsyncMock(return_value=None)
        db = AsyncMock()
        import uuid
        with pytest.raises(FormulaSettingError) as exc_info:
            await store.write_global(
                db, "soe", "test_slot",
                definition={"formula": "EVIL((("},
                user_id=uuid.uuid4(),
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_report_store_write_project_rejects_bad_formula(self) -> None:
        """ReportStore.write_project 拒绝坏式。"""
        from unittest.mock import AsyncMock

        from app.services.formula_settings.stores import ReportStore
        store = ReportStore()
        store._find = AsyncMock(return_value=None)
        store.project_scope = AsyncMock(return_value="soe")
        db = AsyncMock()
        import uuid
        with pytest.raises(FormulaSettingError) as exc_info:
            await store.write_project(
                db, uuid.uuid4(), "balance_sheet:BS-001",
                definition={"formula": "1/0"},
                base_definition=None, base_version=None,
                pinned=False, base_origin=None, base_template_id=None,
                user_id=uuid.uuid4(),
            )
        assert exc_info.value.status_code == 422


# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _make_definition(domain: str, formula: str) -> dict:
    """根据域构造包含公式的定义字典。"""
    if domain == "wp":
        return {"expression": formula, "formula_type": "auto_calc"}
    if domain == "push":
        return {"expression": formula}
    if domain == "cross_check":
        # cross_check 域把公式放在 left_ref 里校验
        return {"left_ref": formula, "operator": "=", "right_ref": "0", "tolerance": "0"}
    return {"formula": formula}
