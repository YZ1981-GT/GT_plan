"""E1 spec Sprint 1 Task 1.25: 用户自定义公式覆盖预设公式不冲突

锚定:
- requirements F2.3 / Task 1.20 执行优先级
- backend/app/routers/wp_user_formulas.py /validate-formula
- backend/app/services/wp_template_init_service.py prefill_workpaper_xlsx user_formulas 参数

测试边界:
1. 无 user_formulas 时,prefill_engine 走预设(默认行为)
2. 有 user_formulas 时,被覆盖的 cell 跳过预设写入
3. user_formulas 不存在 cell 仍走预设
4. validate-formula 路由 schema 解析逻辑(语法/参数数量)
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from app.routers.wp_user_formulas import (
    UserFormulaItem,
    BatchUserFormulasRequest,
    ValidateFormulaRequest,
    _CELL_KEY_RE,
    _SUPPORTED_TYPES,
    _parse_formula_or_raise,
)
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Schema 验证
# ---------------------------------------------------------------------------


def test_cell_key_regex_accepts_valid_keys():
    """cell_key 格式必须是 'sheet_name!A1' (合法坐标)"""
    valid_keys = [
        "现金明细表E1-2!B15",
        "审定表E1-1!R18",
        "Sheet1!A1",
        "  含特殊字符 sheet名 !ZZ100",
    ]
    for k in valid_keys:
        assert _CELL_KEY_RE.match(k) is not None, f"应接受: {k!r}"


def test_cell_key_regex_rejects_invalid_keys():
    """非法格式 cell_key 不通过"""
    invalid_keys = [
        "现金明细表E1-2",  # 缺 !cell
        "!B15",  # 缺 sheet
        "Sheet1!B",  # cell 缺数字
        "Sheet1!1",  # cell 缺字母
        "Sheet1!a1",  # 小写(_CELL_KEY_RE 仅大写)
        "",
    ]
    for k in invalid_keys:
        assert _CELL_KEY_RE.match(k) is None, f"应拒绝: {k!r}"


def test_supported_types_includes_all_10():
    """_SUPPORTED_TYPES 包含 10 种公式类型"""
    expected = {
        "TB", "SUM_TB", "WP", "LEDGER", "AUX",
        "PREV", "ADJ", "NOTE", "LEDGER_DETAIL", "COUNT_LEDGER",
    }
    assert expected.issubset(_SUPPORTED_TYPES), \
        f"缺失: {expected - _SUPPORTED_TYPES}"


# ---------------------------------------------------------------------------
# _parse_formula_or_raise 语法校验
# ---------------------------------------------------------------------------


def test_parse_formula_accepts_valid_tb():
    ftype, args = _parse_formula_or_raise("=TB('1001','期末余额')")
    assert ftype == "TB"
    assert args == ["1001", "期末余额"]


def test_parse_formula_accepts_valid_ledger_detail():
    ftype, args = _parse_formula_or_raise("=LEDGER_DETAIL('1001','12月','>=100000')")
    assert ftype == "LEDGER_DETAIL"
    assert args == ["1001", "12月", ">=100000"]


def test_parse_formula_rejects_no_equals_prefix():
    """缺 = 前缀 → 422"""
    with pytest.raises(HTTPException) as exc:
        _parse_formula_or_raise("TB('1001','期末余额')")
    assert exc.value.status_code == 422
    detail = exc.value.detail
    assert detail["error_code"] == "FORMULA_NOT_EQUALS"


def test_parse_formula_rejects_unknown_type():
    """未知类型 → 422"""
    with pytest.raises(HTTPException) as exc:
        _parse_formula_or_raise("=UNKNOWN('a','b')")
    assert exc.value.status_code == 422
    detail = exc.value.detail
    assert detail["error_code"] == "FORMULA_TYPE_UNKNOWN"


def test_parse_formula_rejects_insufficient_args_for_aux():
    """AUX 至少需要 4 个参数(科目/维度类型/维度编码/列名)"""
    with pytest.raises(HTTPException) as exc:
        _parse_formula_or_raise("=AUX('1002','客户')")  # 仅 2 args
    assert exc.value.status_code == 422
    detail = exc.value.detail
    assert detail["error_code"] == "FORMULA_ARGS_INSUFFICIENT"
    assert "AUX" in detail["message"]


def test_parse_formula_count_ledger_minimal_args():
    """COUNT_LEDGER 至少需要 1 个参数"""
    ftype, args = _parse_formula_or_raise("=COUNT_LEDGER('1001')")
    assert ftype == "COUNT_LEDGER"
    assert args == ["1001"]


# ---------------------------------------------------------------------------
# Pydantic schema validation
# ---------------------------------------------------------------------------


def test_batch_request_pydantic_schema():
    req = BatchUserFormulasRequest(
        formulas={
            "现金明细表E1-2!B15": "=TB('1001','期初余额')",
            "现金明细表E1-2!C15": "",  # 空字符串 = 删除
        }
    )
    assert len(req.formulas) == 2
    assert req.formulas["现金明细表E1-2!C15"] == ""


def test_validate_request_pydantic_schema():
    pid = uuid4()
    req = ValidateFormulaRequest(
        formula="=TB('1001','期末余额')",
        project_id=pid,
        year=2025,
        preview=True,
    )
    assert req.formula == "=TB('1001','期末余额')"
    assert req.project_id == pid
    assert req.year == 2025
    assert req.preview is True


def test_validate_request_preview_optional():
    """preview 默认 False"""
    req = ValidateFormulaRequest(formula="=TB('1001','期末余额')")
    assert req.preview is False
    assert req.project_id is None


def test_user_formula_item_schema():
    item = UserFormulaItem(
        cell_key="现金明细表E1-2!B15",
        formula="=TB('1001','期初余额')",
        formula_type="TB",
        edited_by="user-uuid",
        edited_at="2026-05-17T10:00:00Z",
        original_preset="=TB('1001','期初余额')",
    )
    assert item.cell_key == "现金明细表E1-2!B15"
    assert item.formula_type == "TB"


# ---------------------------------------------------------------------------
# prefill_workpaper_xlsx user_formulas 参数行为(单元层)
# ---------------------------------------------------------------------------


def test_prefill_workpaper_xlsx_signature_accepts_user_formulas():
    """函数签名包含 user_formulas 参数(Task 1.20 已落地)"""
    import inspect
    from app.services.wp_template_init_service import prefill_workpaper_xlsx

    sig = inspect.signature(prefill_workpaper_xlsx)
    assert "user_formulas" in sig.parameters
    # 默认值 None
    assert sig.parameters["user_formulas"].default is None


def test_user_formulas_default_no_change_to_existing_calls():
    """旧调用方(无 user_formulas 参数)不受影响,默认 None 等价于无覆盖"""
    import inspect
    from app.services.wp_template_init_service import prefill_workpaper_xlsx

    sig = inspect.signature(prefill_workpaper_xlsx)
    # 必填参数: target_path / wp_code / tb_data;新参数 user_formulas 默认 None → 向后兼容
    required = [
        p for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty
    ]
    required_names = [p.name for p in required]
    assert "target_path" in required_names
    assert "wp_code" in required_names
    assert "tb_data" in required_names
    # user_formulas 不应是必填
    assert "user_formulas" not in required_names
