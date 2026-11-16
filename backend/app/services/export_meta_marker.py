"""data_exchange 导出的 `_GT_EXPORT_META` 标记（spec platform-global-display-settings-closure 任务 10 / AC-21）。

用途：`data_exchange` 类出口（合并试算表 / 差额表 / 合并附注的本地数据导出）
输出的是**原始元值**，不是正式交付件。为了让下游一眼看出「这是数据交换、
不是最终交付、单位是元」，在工作表里写一段可机读的标记。

三条设计约束（design §6.3）：

1. **原始元值**：data_exchange 一律输出元口径原值，**不做** `ExportUnitPolicy`
   折算——它服务的是「把数据搬走」，不是「给人看金额」。
2. **非正式说明**：必须有一句人类可读的中文说明（放在第一个单元格）。
3. **可机读 marker**：紧随其后写 `_GT_EXPORT_META` JSON，含
   `schema_version` / `surface_id` / `classification` / `source_unit` /
   `generated_at` / `note`。下游据此判定来源单位与类别，不靠猜表头文字。

🔴 本模块只构造单元格值，不碰 openpyxl / 文件 IO：
   谁写文件谁按自己的写入方式调用 `rows()`，避免把两套写入路径绑在一起。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

#: marker 的固定前缀（下游据此定位，不许改）。
MARKER_KEY = "_GT_EXPORT_META"

#: marker schema 版本。
MARKER_SCHEMA_VERSION = 1

#: data_exchange 的固定人类说明（中文，用户可见）。
DATA_EXCHANGE_NOTE = (
    "本文件为数据交换用途，金额为原始元值（未按项目显示单位折算），"
    "不作为正式交付件使用。"
)


class DataExchangeMetaError(ValueError):
    """marker 构造参数非法。"""


@dataclass(frozen=True)
class ExportMeta:
    """`_GT_EXPORT_META` 的内容。"""

    surface_id: str
    classification: str
    source_unit: str = "yuan"
    note: str = DATA_EXCHANGE_NOTE
    generated_at: str | None = None

    def __post_init__(self) -> None:
        if self.classification != "data_exchange":
            raise DataExchangeMetaError(
                f"`_GT_EXPORT_META` 只用于 data_exchange 出口，收到 {self.classification!r}"
            )
        if not self.surface_id:
            raise DataExchangeMetaError("surface_id 不能为空（下游据此判定来源）")
        if self.source_unit not in ("yuan", "qian", "wan"):
            raise DataExchangeMetaError(f"非法 source_unit {self.source_unit!r}")

    def to_json(self) -> str:
        """canonical JSON（键排序、无空格）——便于下游逐字节比对。"""
        payload: dict[str, Any] = {
            "schema_version": MARKER_SCHEMA_VERSION,
            "surface_id": self.surface_id,
            "classification": self.classification,
            "source_unit": self.source_unit,
            "generated_at": self.generated_at
            or datetime.now(timezone.utc).isoformat(),
            "note": self.note,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def marker_rows(meta: ExportMeta) -> list[list[str | None]]:
    """返回插在工作表最前面的三行：

    ```
    [DATA_EXCHANGE_NOTE]          ← 人类可读说明
    [_GT_EXPORT_META, {json}]     ← 可机读标记（键 + JSON 两列）
    []                            ← 空行，与数据区分隔
    ```
    """
    return [
        [meta.note],
        [MARKER_KEY, meta.to_json()],
        [],
    ]


def parse_marker(value: str) -> dict[str, Any]:
    """解析 `_GT_EXPORT_META` 的 JSON（下游 / 测试用）。"""
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise DataExchangeMetaError(f"_GT_EXPORT_META 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise DataExchangeMetaError("_GT_EXPORT_META 必须是 JSON 对象")
    if data.get("classification") != "data_exchange":
        raise DataExchangeMetaError(
            f"_GT_EXPORT_META.classification 必须是 data_exchange，实得 {data.get('classification')!r}"
        )
    if data.get("schema_version") != MARKER_SCHEMA_VERSION:
        raise DataExchangeMetaError(
            f"_GT_EXPORT_META.schema_version 必须是 {MARKER_SCHEMA_VERSION}，"
            f"实得 {data.get('schema_version')!r}"
        )
    return data


def assert_raw_yuan(values: list[Any]) -> None:
    """断言值列是**原始元值**（没有被按显示单位折算过）。

    🔴 这只是启发式防线：真正的保证是 data_exchange 路径**不调**
    `applyFormalExportUnit` / `ExportUnitPolicy`。本函数用于测试与探针：
    若某列出现了「整数且能被 10000 整除」的等比例特征，很可能是已折成万元。
    """
    amounts = [Decimal(str(v)) for v in values if v is not None and str(v).strip()]
    if not amounts:
        return
    if all(a == a.to_integral_value() and a % Decimal("10000") == 0 for a in amounts) and any(
        a != 0 for a in amounts
    ):
        raise DataExchangeMetaError(
            "疑似已按万元折算（所有值都能被 10000 整除）；"
            "data_exchange 必须输出原始元值"
        )
