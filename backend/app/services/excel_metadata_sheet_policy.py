# -*- coding: utf-8 -*-
"""平台注入的隐藏 metadata sheet 在**业务侧的排除策略**（单一真源）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 17
Requirements: 6.13 / 6.17（后半句：「隐藏元数据 sheet 必须被业务导入、报表与 sheet
枚举显式排除」）

═══ 为什么单独一个模块 ═══

Task 17 的 instrumentation 会往权威模板的副本里加一张隐藏 `_GT_SYNC` sheet。它对
审计师不可见（OO 标签栏不显示，Task 5 截图已证），但**平台自己的业务代码**默认是
可见的：`xlsx_read_adapter.list_sheet_names()` 直接 `list(wb.sheetnames)`、
`xlsx_to_univer` 逐 sheet 转 Univer 快照。也就是说不显式排除的话，一份 instrumented
底稿会在「sheet 下拉」「模板 diff」「程序表抽取」「Univer 编辑器标签栏」里多出一张
`_GT_SYNC`，审计师会看到一张自己没法解释的表。

sheet 名的**单一真源**是 Task 5 交付的 :data:`~app.services.excel_structure_fingerprint
.GT_SYNC_SHEET_NAME`；本模块只从那里 import，**不复制字面量**（复制就是第二真源，
改一处漏一处）。

═══ 判据是行为不是字符串 ═══

「已排除」不能靠 grep `_GT_SYNC` 出现在某个 `if` 里来证明 —— 那正是假绿第②源。
守卫的做法是：拿真实权威模板做一次真实 instrumentation，再调用**生产函数本体**
（`list_sheet_names` / `xlsx_to_univer_data`），断言返回结果里没有该 sheet、且业务
sheet 一张不少。删掉本模块的调用即打红。
"""

from __future__ import annotations

from typing import Iterable

from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME

__all__ = [
    "PLATFORM_METADATA_SHEETS",
    "is_platform_metadata_sheet",
    "exclude_metadata_sheets",
]

#: 平台注入、业务侧必须显式排除的隐藏 metadata sheet 名。
#:
#: 目前只有 Excel instrumentation 的 `_GT_SYNC` 一张。**刻意不包含** `_meta_`：
#: 那是 `wp_offline_import_service` / `note_offline_import_service` 的离线导入自有
#: 隐藏 sheet，它们**必须**能枚举到自己的 `_meta_`（`if "_meta_" not in wb.sheetnames:
#: return 缺少 _meta_ 隐藏 sheet，无法导入`）。把它塞进本集合会让离线导入全线失效
#: —— 这是「排除策略」最容易踩的越界。
PLATFORM_METADATA_SHEETS: frozenset[str] = frozenset({GT_SYNC_SHEET_NAME})


def is_platform_metadata_sheet(name: object) -> bool:
    """`name` 是否为平台注入的隐藏 metadata sheet。

    大小写与首尾空白都归一后比对：OO 与 openpyxl 在往返中都不改 sheet 名，但导入的
    第三方文件可能带空白，宁可多排除一个同名变体也不让它漏进业务枚举。
    """
    if not isinstance(name, str):
        return False
    return name.strip().casefold() in {
        s.casefold() for s in PLATFORM_METADATA_SHEETS
    }


def exclude_metadata_sheets(names: Iterable[object]) -> list[str]:
    """过滤掉平台隐藏 metadata sheet，**保持原顺序**。

    顺序必须保留：多处业务代码按「第一个 sheet」取默认表
    （`xlsx_read_adapter.read_sheet_values(sheet_name=None)`），重排会静默换表。
    """
    return [str(n) for n in names if not is_platform_metadata_sheet(n)]
