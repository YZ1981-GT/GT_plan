"""账号「允许修改」开关的判定（spec citar-manual-edit-permission）。

``users.allow_manual_edit`` 关闭的账号不能人工修改自动生成的数据：税审底稿 / 申报表的公式格、自动取数格与
样表预置数字，报告正文金额、审核说明、审定报表、单体财务报表，科目余额表 / 序时账。
只在项目级鉴权（``require_project_access("edit")``）之上再收一道；查看、导出、手填格、调整分录等不受影响。

所有判定都经本模块，不在各接口里各写一份。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

DENIED_MESSAGE = "你的账号未开通「允许修改」，不能人工修改自动生成的数据，请联系管理员在「账号权限」开启"


def manual_edit_allowed(user: Any) -> bool:
    """账号是否允许人工修改。没有该属性（旧会话对象、测试替身）按允许，与迁移默认值一致。"""
    return bool(getattr(user, "allow_manual_edit", True))


def assert_manual_edit(user: Any) -> None:
    """未开通即 403；只做人工修改的接口在处理函数首句调用。"""
    if not manual_edit_allowed(user):
        raise HTTPException(status_code=403, detail=DENIED_MESSAGE)


def denied_cells_message(cells: list[str]) -> str:
    """整表保存里改到了自动生成的格子：点名前 5 个。"""
    shown = "、".join(cells[:5])
    more = f" 等 {len(cells)} 处" if len(cells) > 5 else ""
    return f"{DENIED_MESSAGE}（本次改动了自动生成的格子：{shown}{more}）"
