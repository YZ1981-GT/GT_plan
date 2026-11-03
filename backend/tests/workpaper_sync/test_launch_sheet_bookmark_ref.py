"""打开即定位：`actionLink` 必须写成表格编辑器能跳转的单元格引用。

2026-11-03 真库实测（OnlyOffice 9.4，D4 整册 47 张，起点 D4-1，目标 D4-3）：
表格编辑器把 `actionLink.action.data` 交给 `asc_findCell`，按单元格引用解析 ——

* 裸表名                       → 不跳（原实现，「打开 D4-2 / D4-3 都停在 D4-1」）
* `表名!A1`（不带引号）         → 不跳
* `'表名'!A1`                  → 跳到目标表

整册工作簿各表共用一个文档 key（协同编辑需要），DocServer 缓存命中时 contents 的
activeTab 字节不生效，`actionLink` 是唯一每次打开都执行的定位，写错即整条定位失效。
"""
from __future__ import annotations

import uuid

from app.services.workpaper_sync.room_launch import (
    LaunchUserIdentity,
    build_signed_launch_config,
    sheet_bookmark_ref,
)

D4_3 = "其他业务收入明细表D4-3"


def test_reference_is_quoted_sheet_with_a1() -> None:
    assert sheet_bookmark_ref(D4_3) == f"'{D4_3}'!A1"


def test_sheet_name_with_space_and_quote_is_escaped() -> None:
    # Excel 规则：表名里的单引号写成两个
    assert sheet_bookmark_ref("客户访谈记录 D4-31") == "'客户访谈记录 D4-31'!A1"
    assert sheet_bookmark_ref("O'Brien") == "'O''Brien'!A1"


def _config(document_type: str, target_sheet: str) -> dict:
    return build_signed_launch_config(
        raw_config={"document": {"key": "k"}, "editorConfig": {}},
        document_url="http://x/contents",
        callback_url="http://x/callback",
        document_type=document_type,
        user=LaunchUserIdentity(id=str(uuid.uuid4()), name="u"),
        secret="",
        target_sheet=target_sheet,
    )


def test_sync_launch_config_uses_the_cell_reference() -> None:
    action = _config("xlsx", D4_3)["editorConfig"]["actionLink"]["action"]
    assert action == {"type": "bookmark", "data": f"'{D4_3}'!A1"}


def test_no_action_link_without_target_or_for_word() -> None:
    assert "actionLink" not in _config("xlsx", "")["editorConfig"]
    assert "actionLink" not in _config("docx", D4_3)["editorConfig"]
