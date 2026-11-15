"""从 sheet 名解析「实际使用的 wp_code」—— **单一实现**。

## 为什么必须只有一份

`/onlyoffice-config` 签发的 download / callback URL、WOPI 下载、callback 落盘**三者
必须指向同一个文件**。它们全都依赖「`sheet_name` 对应哪个 wp_code」这一个判定：

* 聚合包内的独立 source_wp_code sheet（如 `D4-5`）有自己的模板 ⇒ 要换码；
* 「完整Excel」模式必须始终用整册码（`D4`），否则打开的不是整本底稿。

任何一侧自己重写这段判定，都会让两侧协商出不同的 wp_code ⇒ 读写异地
（历史事故：整册模式的 callback 反推出 `D4A` 并把改动写进 `D4A.xlsx`，
而 config / WOPI 读的是 `D4.xlsx`，整册编辑结果保存后消失）。

## 为什么现在抽出来

spec `workpaper-html-onlyoffice-bidirectional-writeback-closure` 任务 2.8 第 ② 步新增
`GET /sync/entries/entry-identity` —— 它要按 `(wp_id, sheet_name)` 反查 room entry_id，
而 room entry_id 的前缀就是这里算出的 wp_code。两处各写一份判定的后果比上面更直接：
前端问的 entry 与 `onlyoffice-config` 给的 entry 不是同一条 ⇒ readiness 恒 404，
表现为「在线编辑永远不可用」而不是可归因的错误。
"""
from __future__ import annotations

import re

__all__ = ["resolve_sheet_wp_code"]


#: 尾部形态：`营业收入会计政策检查D4-5`、`存货采购入库检查表F2-33-新增`（忽略修订尾缀）
_SHEET_CODE_TAIL = re.compile(r"([A-Z]\d+(?:-\d+)?[A-Z]?)(?:-新增)?\s*$")
#: 头部形态：`C14-2评价控制偏差` / `C14-2 xxx`
_SHEET_CODE_HEAD = re.compile(r"([A-Z]\d+(?:-\d+)?[A-Z]?)\s*")


def resolve_sheet_wp_code(
    wp_code: str,
    sheet_name: str,
    whole_workbook: bool,
    *,
    has_template: callable | None = None,
) -> str:
    """返回本 sheet 实际使用的 wp_code。

    Args:
        wp_code: 底稿自带的 wp_code。
        sheet_name: 目标 sheet 名。
        whole_workbook: 完整Excel 模式 ⇒ **恒**返回整册码，不猜子码。
        has_template: 判定「该候选码是否有自己的模板」的谓词。给 `None` 时不做换码
            （调用方不关心模板存在性时的安全默认）。

    Returns:
        实际使用的 wp_code。`whole_workbook=True` 时恒为 `wp_code`。
    """
    if whole_workbook:
        return wp_code
    if has_template is None:
        return wp_code

    match = _SHEET_CODE_TAIL.search(sheet_name)
    if match is None:
        match = _SHEET_CODE_HEAD.match(sheet_name)
    if match is None:
        return wp_code
    candidate = match.group(1)
    if candidate == wp_code:
        return wp_code
    return candidate if has_template(candidate) else wp_code
