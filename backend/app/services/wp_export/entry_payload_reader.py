"""底稿录入载荷读取 — 导出侧数据源（workpaper-import-export-lifecycle-closure Task 7）

## 为什么需要这个模块

`export-xlsx` 唯一数据源是 `parsed_data.html_data`，而底稿录入的真实落点是
`checklist_responses`。真实库实测（2026-08-10，2802 份未软删底稿）：

| 存储 | 有内容的底稿数 |
|---|---|
| `checklist_responses`（录入真实落点） | **131 份** |
| `parsed_data.html_data`（导出唯一数据源） | **73 份** |
| **两者交集** | **5 份** |

两集合几乎不相交 ⇒ 那 131 份里 126 份的 `html_data` 键根本不存在 ⇒ 模板被原样
另存 ⇒ 用户看到空模板。本模块是把录入接进导出的取值层。

## 🔴 它读的不是「行」，而是「item_id 的 JSON 载荷」

立项需求文档把这里写成「行含 item_id / 值 / 结论 / 备注」，实测**结构上不成立**：

- 全库 `checklist_responses` **1,034,515 行**，其中 `conclusion` 与 `remark`
  **双 NULL 达 1,033,715 行**（99.93%）—— 单份 C24 分录测试底稿独占 1,033,230 行
- 真正非空只有 **约 695 行**，形态分布：

| 存放列 | json_array | json_object | plain_text | 单行最长 |
|---|---|---|---|---|
| `remark` | 284 | 120 | 194 | **866,845 字符** |
| `conclusion` | 17 | 6 | 75 | 5,974 字符 |

⇒ 三条设计结论：

1. **必须读两列**：`conclusion` 与 `remark` 各自都在承载全部三种形态，
   只读一列会丢数据。返回 `source_field` 标注实际来源。
2. **必须剔空行**：99.93% 是空骨架，全量倾倒会把有效内容彻底淹没。
3. **必须设上限**：单行可达 **86 万字符**、单份可达 103 万行，不设限必 OOM。
   阈值按**条数与总字符数双闸**，任一超限即截断并如实标注。

## 与 R2.2 的偏离（已登记）

AC 字面要求列含「item_id / 值 / 结论 / 备注」四列，把 `conclusion` 与 `remark`
当成两个业务字段。实测二者是**同一份载荷的两个候选存放列**（哪列非空就用哪列），
不是两个并列字段。故本模块返回 `source_field` 标注来源列，由渲染层写进 sheet
承担 R2.8 的「数据来源」语义。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PayloadShape = Literal["json_array", "json_object", "plain_text"]
SourceField = Literal["conclusion", "remark"]

#: 单份底稿最多取多少个 item_id（条数闸）。
#:
#: 实测单份 C24 有 1,033,230 行、其中非空仅 10 行，故此闸主要防的是
#: 「将来某底稿真有大量非空 item」而非 C24 那种空骨架。
MAX_ITEMS_PER_WP = 500

#: 单份底稿载荷总字符上限（总量闸）。
#:
#: 实测单行最长 **866,845 字符**（`remark` 里的 json_array）。取 2MB 作总闸：
#: 既容得下最大单行，又不会让一份产物膨胀到不可用。
MAX_TOTAL_CHARS = 2_000_000

#: 单个载荷字符上限（个体闸）—— 超限则截断该条正文但保留 item_id 与形态。
MAX_ONE_CHARS = 200_000


@dataclass(frozen=True)
class EntryPayload:
    """单个 `item_id` 的录入载荷。

    Attributes:
        item_id: `checklist_responses.item_id`。
        shape: 载荷形态。**解析失败一律降级 `plain_text`**（不抛、不丢）。
        rows: `json_array` 解析结果（元素非 dict 时包装成 `{"值": elem}`）。
        obj: `json_object` 解析结果。
        text: `plain_text` 原文；也用于承载解析失败的原始串。
        source_field: 实际取值列（`remark` 优先，两列都非空时以 `remark` 为准）。
        raw_len: 原始字符数（截断前），用于产物标注。
        truncated: 该条正文是否被个体闸截断。
    """

    item_id: str
    shape: PayloadShape
    rows: list[dict[str, Any]] | None
    obj: dict[str, Any] | None
    text: str | None
    source_field: SourceField
    raw_len: int
    truncated: bool = False


@dataclass(frozen=True)
class EntryPayloadResult:
    """读取结果。

    Attributes:
        payloads: 非空载荷列表（已按 `item_id` 排序，便于产物稳定可比）。
        skipped_blank: 被剔除的空行数（`conclusion` 与 `remark` 均空）。
        dropped_by_cap: 因条数/总量闸被丢弃的载荷数。
        total_chars: 实际保留的字符总数。
        parse_failures: JSON 解析失败并降级为 `plain_text` 的条数。
    """

    payloads: list[EntryPayload]
    skipped_blank: int
    dropped_by_cap: int
    total_chars: int
    parse_failures: int

    @property
    def has_content(self) -> bool:
        """是否有可导出的录入内容（供 `needs_self_evidence` 的 `has_entry_rows` 用）。"""
        return bool(self.payloads)

    @property
    def truncated(self) -> bool:
        """是否发生了任何形式的截断（条数闸 / 总量闸 / 个体闸）。"""
        return self.dropped_by_cap > 0 or any(p.truncated for p in self.payloads)


def _classify(raw: str) -> tuple[PayloadShape, list[dict] | None, dict | None, bool]:
    """判形态并解析。返回 `(shape, rows, obj, parse_failed)`。

    🔴 解析失败**降级不抛**：实测 269 行本就是纯文本（结论/备注的自然形态），
    把它们当异常会让整份导出崩掉。但降级要**记 WARNING** —— 否则真损坏的 JSON
    也会被静默当成纯文本，属 memory 记的「fail-open 掩盖错误」。
    """
    s = raw.lstrip()
    if s.startswith("["):
        try:
            data = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return "plain_text", None, None, True
        if isinstance(data, list):
            rows: list[dict[str, Any]] = []
            for elem in data:
                rows.append(elem if isinstance(elem, dict) else {"值": elem})
            return "json_array", rows, None, False
        return "plain_text", None, None, True

    if s.startswith("{"):
        try:
            data = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return "plain_text", None, None, True
        if isinstance(data, dict):
            return "json_object", None, data, False
        return "plain_text", None, None, True

    return "plain_text", None, None, False


async def read_entry_payloads(
    db: AsyncSession,
    wp_id: Any,
    *,
    max_items: int = MAX_ITEMS_PER_WP,
    max_total_chars: int = MAX_TOTAL_CHARS,
    max_one_chars: int = MAX_ONE_CHARS,
) -> EntryPayloadResult:
    """读取某底稿的全部非空录入载荷。

    Args:
        db: async session。
        wp_id: `checklist_responses.wp_id`（UUID 或其字符串形态）。
        max_items: 条数闸。
        max_total_chars: 总量闸。
        max_one_chars: 个体闸。

    Returns:
        `EntryPayloadResult`。**查询异常不抛**：导出不应因取值层失败而整体崩掉，
        但会记 ERROR（不是 WARNING）—— memory 铁律：取值层异常必须留 ERROR 痕，
        否则「本项目无此数据」与「SQL 写错了」不可区分。

    Note:
        `checklist_responses` **无 ORM 模型**（平台既有事实，见
        `auto_data_resolvers/_control_b.py` 注释），故此处走裸 SQL。
        列名是 `wp_id` 而非 `workpaper_id` —— 后者曾导致整条取值链被
        `except` 吞成 WARNING（memory 已记该 P0）。
    """
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses "
                "WHERE wp_id = :wp_id "
                "ORDER BY item_id"
            ),
            {"wp_id": str(wp_id)},
        )
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001
        # 🔴 ERROR 而非 WARNING：这里失败意味着「导出少了录入内容」，
        #    而表现形式与「本底稿确实没录入」完全一致，必须能从日志区分。
        logger.error(
            "read_entry_payloads 查询失败 wp_id=%s: %s", wp_id, exc, exc_info=True
        )
        return EntryPayloadResult([], 0, 0, 0, 0)

    payloads: list[EntryPayload] = []
    skipped_blank = 0
    dropped = 0
    total_chars = 0
    parse_failures = 0

    for item_id, conclusion, remark in rows:
        # ─── 剔空行（99.93% 的行走这条）──────────────────────────────
        r = (remark or "").strip()
        c = (conclusion or "").strip()
        if not r and not c:
            skipped_blank += 1
            continue

        # `remark` 优先 —— 实测它承载 598/696 条非空载荷
        raw, src = (r, "remark") if r else (c, "conclusion")

        # ─── 条数闸 / 总量闸 ────────────────────────────────────────
        if len(payloads) >= max_items or total_chars >= max_total_chars:
            dropped += 1
            continue

        shape, parsed_rows, parsed_obj, failed = _classify(raw)
        if failed:
            parse_failures += 1
            logger.warning(
                "载荷 JSON 解析失败已降级 plain_text: wp_id=%s item_id=%s len=%d",
                wp_id,
                item_id,
                len(raw),
            )

        # ─── 个体闸 ────────────────────────────────────────────────
        truncated = len(raw) > max_one_chars
        text_val = raw[:max_one_chars] if shape == "plain_text" or truncated else None
        if truncated:
            # 超限则不保留结构化解析结果（可能是 86 万字符的巨型数组）
            shape, parsed_rows, parsed_obj = "plain_text", None, None

        payloads.append(
            EntryPayload(
                item_id=str(item_id),
                shape=shape,
                rows=parsed_rows,
                obj=parsed_obj,
                text=text_val,
                source_field=src,  # type: ignore[arg-type]
                raw_len=len(raw),
                truncated=truncated,
            )
        )
        total_chars += min(len(raw), max_one_chars)

    return EntryPayloadResult(
        payloads=payloads,
        skipped_blank=skipped_blank,
        dropped_by_cap=dropped,
        total_chars=total_chars,
        parse_failures=parse_failures,
    )


__all__ = [
    "MAX_ITEMS_PER_WP",
    "MAX_ONE_CHARS",
    "MAX_TOTAL_CHARS",
    "EntryPayload",
    "EntryPayloadResult",
    "PayloadShape",
    "SourceField",
    "read_entry_payloads",
]
