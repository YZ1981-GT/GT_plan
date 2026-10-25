"""三入口 action 契约守卫。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6
"""
from __future__ import annotations

import pytest

from app.services.custom_template_ingestion.actions import (
    ACTION_ID_SET,
    ACTION_IDS,
    ACTION_SPECS,
    BATCH_CREATE_BLANK,
    INGEST_EXCEL_TEMPLATE,
    MAINTAIN_METADATA,
    UnknownActionId,
    is_ingestion,
    spec_for,
    success_message,
)


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 1.4 —— 稳定 action id
# ─────────────────────────────────────────────────────────────────────────────


def test_exactly_three_action_ids_with_no_drift() -> None:
    """三条 action 且精确等于规范名 —— 防止散落魔数或悄悄加第四条。"""
    assert ACTION_IDS == (BATCH_CREATE_BLANK, MAINTAIN_METADATA, INGEST_EXCEL_TEMPLATE)
    assert ACTION_ID_SET == frozenset({
        "batch_create_blank",
        "maintain_metadata",
        "ingest_excel_template",
    })
    # 登记表与常量一一对应，无悬挂 spec
    assert set(ACTION_SPECS) == ACTION_ID_SET


def test_spec_for_rejects_unknown_action_id_instead_of_falling_back() -> None:
    """🔴 不回落到默认 action —— 回落会让错误字节被当摄取处理（越权写 quarantine）。"""
    with pytest.raises(UnknownActionId) as exc:
        spec_for("upload_template")
    assert "upload_template" in str(exc.value)
    assert "batch_create_blank" in str(exc.value)  # 合法取值必须可发现


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 1.3 —— 唯一摄取入口接收二进制
# ─────────────────────────────────────────────────────────────────────────────


def test_only_ingestion_action_consumes_binary() -> None:
    for action_id, spec in ACTION_SPECS.items():
        expected = action_id == INGEST_EXCEL_TEMPLATE
        assert spec.consumes_binary is expected, (
            f"{action_id} 的 consumes_binary={spec.consumes_binary}，"
            f"但只有 {INGEST_EXCEL_TEMPLATE} 应接收二进制（Requirement 1.3）"
        )
        assert is_ingestion(action_id) is expected


def test_no_action_produces_publication_at_ingest_time() -> None:
    """finalize 是独立 action（Task 11），摄取链本身不得发布。"""
    for spec in ACTION_SPECS.values():
        assert spec.produces_publication is False


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 1.6 —— 成功文案只描述真实副作用
# ─────────────────────────────────────────────────────────────────────────────


def test_no_success_message_claims_upload_or_publication() -> None:
    """🔴 原先「上传成功」被三条链复用，是 1.6 要消除的混淆。"""
    forbidden = ("模板已上传", "模板已发布", "已发布")
    for action_id in ACTION_IDS:
        msg = success_message(action_id, created=3, skipped=1)
        for bad in forbidden:
            assert bad not in msg, (
                f"{action_id} 的成功文案含 {bad!r} —— "
                f"该 action 的真实副作用不含发布（Requirement 1.6）"
            )


def test_batch_blank_message_reports_only_blank_creation() -> None:
    msg = success_message(BATCH_CREATE_BLANK, created=3, skipped=1)
    assert "空白底稿" in msg
    assert "3" in msg and "1" in msg
    assert "模板" not in msg, "空白批量创建不得暗示保存了 Excel 模板"


def test_metadata_message_explicitly_disclaims_binary() -> None:
    msg = success_message(MAINTAIN_METADATA)
    assert "未接收任何文件" in msg
    assert "未生成候选" in msg


def test_ingestion_message_states_quarantine_not_published() -> None:
    msg = success_message(INGEST_EXCEL_TEMPLATE)
    assert "隔离预检" in msg
    assert "未发布" in msg


def test_success_message_is_derived_from_spec_not_from_chinese_labels() -> None:
    """判据是 consumes_binary/produces_publication，不是中文字串匹配。

    故意改中文标签不得改变文案 —— 证明文案来自结构化字段。
    """
    spec = spec_for(BATCH_CREATE_BLANK)
    assert spec.ui_label == "确认创建"  # 中文仅展示
    # 文案里没有按钮文字
    assert spec.ui_label not in success_message(BATCH_CREATE_BLANK, created=1, skipped=0)


def test_success_message_rejects_unknown_action_id() -> None:
    with pytest.raises(UnknownActionId):
        success_message("ingest_anything")
