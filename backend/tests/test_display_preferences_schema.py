"""账号显示偏好 wire 合同测试。

Validates: Requirements R2 / AC-01、AC-02。
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.display_preferences import (
    PLATFORM_DEFAULTS,
    DisplayPreferencesPatch,
)


def test_platform_defaults_are_complete_and_follow_project_by_default() -> None:
    """无记录 GET 的默认 JSON 是稳定、完整的 snake_case 合同。"""

    assert PLATFORM_DEFAULTS.model_dump(mode="json") == {
        "amount_unit_override": None,
        "font_size": "sm",
        "show_zero": False,
        "decimals": 2,
        "negative_red": True,
        "highlight_threshold": 0.2,
        "density": "default",
        "grid_edit_mode": "excel",
        "fixed_columns": {},
        "revision": 0,
        "updated_at": None,
    }


def test_explicit_null_means_follow_project_but_omitted_fields_are_not_written() -> None:
    """Validates: Requirements R2 / design §16 F6。"""

    patch = DisplayPreferencesPatch.model_validate({
        "base_revision": 3,
        "amount_unit_override": None,
    })
    assert patch.business_fields_dict() == {"amount_unit_override": None}

    with pytest.raises(ValidationError, match="font_size 不允许为 null"):
        DisplayPreferencesPatch.model_validate({"base_revision": 3, "font_size": None})
    with pytest.raises(ValidationError, match="fixed_columns 不允许为 null"):
        DisplayPreferencesPatch.model_validate({"base_revision": 3, "fixed_columns": None})
    with pytest.raises(ValidationError, match="至少需要一个业务字段"):
        DisplayPreferencesPatch.model_validate({"base_revision": 3})


@pytest.mark.parametrize(
    "payload",
    [
        {"base_revision": True, "font_size": "sm"},
        {"base_revision": 0.0, "font_size": "sm"},
        {"base_revision": 0, "show_zero": 1},
        {"base_revision": 0, "decimals": "2"},
        {"base_revision": 0, "highlight_threshold": "0.2"},
        {"base_revision": 0, "highlight_threshold": float("nan")},
        {"base_revision": 0, "highlight_threshold": 0.12345},
        {"base_revision": 0, "decimals": 7},
        {"base_revision": 0, "highlight_threshold": 1.1},
        {"base_revision": 0, "font_size": "xxl"},
        {"base_revision": 0, "unexpected": "field"},
    ],
)
def test_patch_rejects_non_strict_or_out_of_range_values(payload: dict[str, object]) -> None:
    """类型、枚举、范围和额外字段均在 wire 边界拒绝。"""

    with pytest.raises(ValidationError):
        DisplayPreferencesPatch.model_validate(payload)


def test_fixed_columns_accepts_only_request_shape_without_saved_at() -> None:
    patch = DisplayPreferencesPatch.model_validate({
        "base_revision": 0,
        "fixed_columns": {
            "trial-balance": {"columns": ["account_code", "audited_amount"]},
        },
    })
    assert patch.business_fields_dict() == {
        "fixed_columns": {
            "trial-balance": {"columns": ["account_code", "audited_amount"]},
        },
    }


@pytest.mark.parametrize(
    "entry",
    [
        {"columns": ["amount"], "saved_at": "2026-01-01T00:00:00+00:00"},
        {"columns": ["amount"], "unknown": True},
        {},
        {"columns": ["amount", "amount"]},
        {"columns": [1]},
        {"columns": ["x"] * 21},
    ],
)
def test_fixed_columns_rejects_saved_at_unknown_or_invalid_columns(entry: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DisplayPreferencesPatch.model_validate({
            "base_revision": 0,
            "fixed_columns": {"trial-balance": entry},
        })


def test_fixed_columns_enforces_page_count_key_length_and_storage_size() -> None:
    with pytest.raises(ValidationError):
        DisplayPreferencesPatch.model_validate({
            "base_revision": 0,
            "fixed_columns": {"": {"columns": []}},
        })
    too_many_pages = {f"page-{index}": {"columns": []} for index in range(101)}
    with pytest.raises(ValidationError):
        DisplayPreferencesPatch.model_validate({
            "base_revision": 0,
            "fixed_columns": too_many_pages,
        })

    # 每项单独合法，但整体超过 wire 边界的 64KiB 粗筛：
    # pydantic 层先拒（请求体阶段），服务端保存前还有一道精确的
    # 规范 JSON 64KiB 校验（含 saved_at 注入后），两层合同互补。
    oversized = {
        f"page-{index:03d}": {"columns": [f"column-{column:03d}-" + "x" * 88 for column in range(20)]}
        for index in range(100)
    }
    with pytest.raises(ValidationError, match="64KiB"):
        DisplayPreferencesPatch.model_validate({
            "base_revision": 0,
            "fixed_columns": oversized,
        })
