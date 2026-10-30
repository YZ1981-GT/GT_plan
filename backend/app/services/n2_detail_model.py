# -*- coding: utf-8 -*-
"""N2-2 应交税费明细表的存储与公式单一口径。

前端 ``useN2Detail16``、长前缀导入导出服务和复核上下文都使用同一张 A:Q 表：
可编辑列写入 ``N2-2-detail-rows.conclusion``，F/M/N/O/P 在读取时重算，不持久化旧值。
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Final, Mapping

N2_DETAIL_ITEM_ID: Final[str] = "N2-2-detail-rows"
N2_DETAIL_STORAGE_FIELD: Final[str] = "conclusion"
N2_DETAIL_IDENTITY_KEY: Final[str] = "id"
N2_DETAIL_HEADERS: Final[tuple[str, ...]] = (
    "项目", "税率或税收优惠",
    "未审·期初数", "未审·本期应交数", "未审·本期已交数", "未审·期末数",
    "期初调整·账项调整", "期初调整·重分类调整",
    "账项调整·本期应交", "账项调整·本期已交",
    "重分类调整·本期应交", "重分类调整·本期已交",
    "审定·期初数", "审定·本期应交数", "审定·本期已交数", "审定·期末数",
    "备注",
)
N2_DETAIL_FIELDS: Final[tuple[str, ...]] = (
    "taxType", "taxRate", "unadjBegin", "unadjPayable", "unadjPaid", "unadjEnd",
    "beginAdjust", "beginRje", "ajePayable", "ajePaid", "rjePayable", "rjePaid",
    "audBegin", "audPayable", "audPaid", "audEnd", "remark",
)
N2_DETAIL_PERSISTED_FIELDS: Final[tuple[str, ...]] = (
    "taxType", "taxRate", "unadjBegin", "unadjPayable", "unadjPaid", "beginAdjust",
    "beginRje", "ajePayable", "ajePaid", "rjePayable", "rjePaid", "remark",
)


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if isfinite(result) else 0.0


def enrich_n2_detail_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    """按权威模板 F/M/N/O/P 公式重算一行，显式覆盖任何陈旧派生值。"""
    row = dict(raw)
    c = _number(raw.get("unadjBegin"))
    d = _number(raw.get("unadjPayable"))
    e = _number(raw.get("unadjPaid"))
    g = _number(raw.get("beginAdjust"))
    h = _number(raw.get("beginRje"))
    i = _number(raw.get("ajePayable"))
    j = _number(raw.get("ajePaid"))
    k = _number(raw.get("rjePayable"))
    paid_rje = _number(raw.get("rjePaid"))
    row.update(
        unadjEnd=c + d - e,
        audBegin=c + g + h,
        audPayable=d + i + k,
        audPaid=e + j + paid_rje,
    )
    row["audEnd"] = row["audBegin"] + row["audPayable"] - row["audPaid"]
    return row


def n2_detail_audited_end(raw: Mapping[str, Any]) -> float:
    """返回 N2-2 一行审定期末 P，供复核上下文求和。"""
    return float(enrich_n2_detail_row(raw)["audEnd"])


def persisted_n2_detail_row(raw: Mapping[str, Any], *, identity: str) -> dict[str, Any]:
    """导入行转成前端持久化形状；公式列不落库，避免缓存值过期。"""
    return {
        N2_DETAIL_IDENTITY_KEY: str(raw.get(N2_DETAIL_IDENTITY_KEY) or identity),
        **{field: raw.get(field) for field in N2_DETAIL_PERSISTED_FIELDS},
    }
