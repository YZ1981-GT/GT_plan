"""`EditorLaunchDescriptor` 的视图身份：封闭域、归一化与校验。

spec: `onlyoffice-sheet-open-via-published-artifact` task 2.4

═══ 为什么单独一个模块 ═══

`materialize_coordinator.py` 已在行数门禁的白名单里（基线 3342 +5%），任何新逻辑都必须
外移而不是抬基线。视图身份恰好是**纯判据**（无 session、无 room、无 I/O），与 coordinator
的编排职责不同层 —— 抽出来不是为了凑行数，它本来就是独立的一层。

═══ 两个字段的语义 ═══

* `document_scope`：`single_sheet` 可带 `target_sheet` 定位；`whole_workbook` 必须不带
  （否则其它 sheet tab 被悄悄藏起来 = Requirement 3.4 禁止的「通过隐藏 sheet 改写
  artifact」的后门形态之一）。
* `target_sheet`：artifact 内的**物理** sheet 名，不是路径、不由请求期正则猜。空串与
  `None` 是两种不同的事：`None` 是显式「不定位」，空串是「既想定位又没定位到」的歧义
  形态 ⇒ 构造期拒收，归一化时统一成 `None`。

═══ 为什么必须在 descriptor 里冻结 ═══

`document.url`（DS 按 token claim 派生 activeTab）与
`onlyoffice_config.editorConfig.actionLink`（客户端每次打开都执行定位）是**同一份
artifact 的两种视图表达**。只要有一处从别处（模板目录、route query、客户端 sheet 名）
取目标 sheet，就会出现「DS 给的是 A 表、客户端定位到 B 表」—— 用户看到 A、改动落 B。
"""

from __future__ import annotations

from typing import Any, Final

#: `document_scope` 的封闭枚举。未知值一律拒绝：让第三个值静默通过等于留后门。
DOCUMENT_SCOPES: Final[frozenset[str]] = frozenset({"single_sheet", "whole_workbook"})


class DescriptorViewIdentityError(ValueError):
    """视图身份非法。调用方（`assert_descriptor_mountable`）译为 `DescriptorFieldMissingError`。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_target_sheet(
    *, document_scope: str, target_sheet: str | None
) -> str | None:
    """视图身份的**唯一**归一化点：整册 ⇒ `None`；空串 ⇒ `None`。

    不在 `MaterializeRequest.__post_init__` 归一：那会让「调用方传了什么」不可观测，
    而 descriptor 才是对外契约。
    """
    if str(document_scope) == "whole_workbook":
        return None
    if target_sheet is None:
        return None
    text = str(target_sheet).strip()
    return text or None


def assert_view_identity(*, document_scope: Any, target_sheet: Any) -> None:
    """构造期校验。逐项判据，**不是**「非空即可」。

    与 `assert_descriptor_mountable` 的其余判据同层：任一不满足则半个 descriptor 造不出来。
    """
    if document_scope not in DOCUMENT_SCOPES:
        raise DescriptorViewIdentityError(
            "document_scope_not_closed",
            f"launch descriptor 的 document_scope={document_scope!r} 不在封闭域 "
            f"{sorted(DOCUMENT_SCOPES)} 里 —— 未知 scope 会让「隐藏 sheet 改写 artifact」"
            "这类旧式做法借第三个值复活",
        )
    if target_sheet is not None and not isinstance(target_sheet, str):
        raise DescriptorViewIdentityError(
            "target_sheet_type",
            f"launch descriptor 的 target_sheet 必须是 str 或 None，"
            f"实得 {type(target_sheet).__name__}",
        )
    if isinstance(target_sheet, str) and target_sheet != target_sheet.strip():
        # 不做归一化：artifact 里的 sheet 名可能真的带首尾空格，半 strip 的输入必须拒。
        raise DescriptorViewIdentityError(
            "target_sheet_padded",
            f"launch descriptor 的 target_sheet={target_sheet!r} 带首尾空白 —— "
            "必须给出 artifact 内的物理 sheet 名（不做归一化，因为真实 sheet 名可能含空格）",
        )
    if document_scope == "whole_workbook" and target_sheet:
        raise DescriptorViewIdentityError(
            "whole_workbook_with_target",
            f"document_scope=whole_workbook 却带 target_sheet={target_sheet!r} —— "
            "整册视图必须打开全部 sheet tab，带定位会把其它 sheet 悄悄藏起来",
        )
    if document_scope == "single_sheet" and target_sheet is not None and not target_sheet.strip():
        raise DescriptorViewIdentityError(
            "single_sheet_empty_target",
            "document_scope=single_sheet 的 target_sheet 只能是 None（不定位）或非空物理名，"
            "空串是「既想定位又没定位到」的歧义形态",
        )


__all__ = [
    "DOCUMENT_SCOPES",
    "DescriptorViewIdentityError",
    "assert_view_identity",
    "normalize_target_sheet",
]
