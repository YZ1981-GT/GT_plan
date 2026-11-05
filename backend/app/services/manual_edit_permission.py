"""账号「允许修改」开关的判定（spec citar-manual-edit-permission）。

``users.allow_manual_edit`` 关闭的账号只能查看：不能修改任何表格数据与底稿内容——
税审底稿 / 申报表的全部格子（含手填格）、表头信息、是否填报，报告日期与摘录表金额、审核说明，
审定报表、单体财务报表，科目余额表 / 序时账，调整分录（新增 / 修改 / 删除 / 导入），科目映射（新增 / 修改 / 智能匹配）。
只在项目级鉴权（``require_project_access("edit")`` 等）之上再收一道；查看、导出、取数、重算、生成报表、导入账套、复核流转不受影响。

所有判定都经本模块，不在各接口里各写一份。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

DENIED_MESSAGE = "你的账号未开通「允许修改」，只能查看，不能修改数据，请联系管理员在「账号权限」开启"


def manual_edit_allowed(user: Any) -> bool:
    """账号是否允许修改：只有明确为 False 才算关闭。

    没有该属性（旧会话对象、测试替身）或为 None（内存里新建、尚未写库的 ORM 对象——列默认值写库时才生效）
    都按允许，与迁移默认值、前端 ``allow_manual_edit !== false`` 同口径。
    """
    return getattr(user, "allow_manual_edit", True) is not False


def assert_manual_edit(user: Any) -> None:
    """未开通即 403；修改数据的接口在处理函数首句调用（先于任何写入）。"""
    if not manual_edit_allowed(user):
        raise HTTPException(status_code=403, detail=DENIED_MESSAGE)
