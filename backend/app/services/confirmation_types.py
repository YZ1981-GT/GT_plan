"""函证类型单一来源（spec attachment-confirmation-evidence-loop 需求 5.1，ADR-ACE-05）。

合法值由 ``ConfirmationType`` 枚举派生；创建 / 更新 / 批量同步三个请求体用 ``ConfirmTypeStr`` 校验，其余值 422。
改造前创建不校验类型，任意字符串都能落库。「从底稿导入」候选只认有科目前缀的四类
（``confirmation_service._CONFIRM_TYPE_ACCOUNT_PREFIXES``），律师 / 其他返回空。
"""
from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator

from app.models.confirmation_models import ConfirmationType

CONFIRM_TYPE_LABELS: dict[str, str] = {
    ConfirmationType.receivable.value: "应收",
    ConfirmationType.payable.value: "应付",
    ConfirmationType.bank.value: "银行",
    ConfirmationType.loan.value: "借款",
    ConfirmationType.legal.value: "律师",
    ConfirmationType.other.value: "其他",
}
VALID_CONFIRM_TYPES: tuple[str, ...] = tuple(t.value for t in ConfirmationType)


def check_confirm_type(value: str) -> str:
    """不在枚举里 ⇒ ValueError（pydantic 转 422）；前后空白去掉。"""
    text = (value or "").strip()
    if text not in VALID_CONFIRM_TYPES:
        choices = "、".join(f"{v}（{CONFIRM_TYPE_LABELS.get(v, v)}）" for v in VALID_CONFIRM_TYPES)
        raise ValueError(f"不支持的函证类型「{value}」，可选：{choices}")
    return text


ConfirmTypeStr = Annotated[str, AfterValidator(check_confirm_type)]
