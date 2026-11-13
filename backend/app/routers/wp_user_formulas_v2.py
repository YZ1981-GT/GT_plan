"""已退役的用户公式 v2 实验接口。

该实验版本使用不含项目/底稿维度的进程内全局 store，无法满足项目隔离。
三个历史端点保留为认证后的 410 响应，供旧客户端明确迁移；本模块不再导入、
读取或写入该 store。
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user
from app.models.core import User

router = APIRouter(
    prefix="/api/workpapers/{wp_id}/user-formulas/v2",
    tags=["workpaper-user-formulas-v2"],
)

_RETIRED_DETAIL = {
    "code": "USER_FORMULA_V2_RETIRED",
    "message": "用户公式 v2 实验接口已退役",
    "replacement": "请使用正式的项目级公式接口",
}


def _gone() -> NoReturn:
    raise HTTPException(status_code=410, detail=_RETIRED_DETAIL)


@router.get("")
def list_user_formulas_v2(
    wp_id: str,
    user: User = Depends(get_current_user),
) -> None:
    _ = (wp_id, user)
    _gone()


@router.post(":batchMutate")
def batch_mutate_user_formulas_v2(
    wp_id: str,
    user: User = Depends(get_current_user),
) -> None:
    # 请求体故意不建模：合法旧客户端、空请求体和旧格式都统一得到 410，且不触达 store。
    _ = (wp_id, user)
    _gone()


@router.get("/{formula_id}/history")
def user_formula_v2_history(
    wp_id: str,
    formula_id: str,
    user: User = Depends(get_current_user),
) -> None:
    _ = (wp_id, formula_id, user)
    _gone()
