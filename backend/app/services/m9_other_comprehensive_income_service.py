"""M9 其他综合收益 — 明细表 M9-2 导入导出 + 审定表 M9-1 行读取（权益类公式校验）。

``routers/m9_other_comprehensive_income.py`` 惰性 import 本模块的四个函数。

* 明细表的列与存储键逐字对齐前端：行字段与顺序取自 ``useM9Detail.ts`` 的 ``_syncFullData``；
  界面恢复经 ``getField('2', 'detail-rows')`` 读 ``M9-2-detail-rows`` 的 **conclusion** 列。
* 审定表行与 ``M9TabAdjudication._restoreRows`` 同口径：全部 ``M9-1-*-data``（remark JSON），
  按 item_id 排序（与 checklist-responses 读接口同序）。

科目：其他综合收益（贷方 / 权益类）—— 期末 = 期初 + 贷方 − 借方；各项目按税后净额列示。
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any, Mapping, Sequence

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.m_detail_sheet_io import (
    ComputedColumn,
    DetailSheetSpec,
    InputColumn,
    export_data,
    export_template,
    import_sheet,
    lenient_number,
    like_prefix,
    require_wp_uuid,
    unknown_sheet_message,
)

logger = logging.getLogger(__name__)

DETAIL_SHEET = "M9-2"
ADJUDICATION_ITEM_PREFIX = "M9-1-"
ADJUDICATION_ITEM_SUFFIX = "-data"

#: 分类存储值 → 界面显示（``useM9Detail.M9OciCategory``）
OCI_CATEGORIES: dict[str, str] = {"nonReclass": "不可重分类", "reclass": "可重分类"}
#: 审定表 / 附注里的长名称也认
OCI_CATEGORY_ALIASES: dict[str, str] = {
    "以后不能重分类进损益的其他综合收益": "nonReclass",
    "以后不能重分类进损益": "nonReclass",
    "不能重分类进损益": "nonReclass",
    "以后能重分类进损益的其他综合收益": "reclass",
    "以后能重分类进损益": "reclass",
    "能重分类进损益": "reclass",
}


def _change_rate(audited_end: float, prior_end: float) -> float:
    """变动率：上期期末为 0 时审定期末非 0 记 100%（与界面同式）。"""
    if prior_end == 0:
        return 0.0 if audited_end == 0 else 1.0
    return (audited_end - prior_end) / prior_end


def _compute_detail(row: Mapping[str, Any]) -> dict[str, float]:
    """单行公式列，逐式照抄 ``useM9Detail.computedRows``（含运算顺序，与界面逐位相等）。"""
    audited_begin = row["beginning"] + row["beginAje"] + row["beginRje"]
    audited_pre_tax = row["preTaxAmount"] + row["preTaxAje"] + row["preTaxRje"]
    audited_tax = row["taxEffect"] + row["taxAje"] + row["taxRje"]
    audited_after_tax_net = audited_pre_tax - audited_tax
    audited_end = audited_begin + audited_after_tax_net
    return {
        "afterTaxNet": row["preTaxAmount"] - row["taxEffect"],
        "endBalance": row["beginning"] + row["creditAmount"] - row["debitAmount"],
        "auditedBegin": audited_begin,
        "auditedPreTax": audited_pre_tax,
        "auditedTax": audited_tax,
        "auditedAfterTaxNet": audited_after_tax_net,
        "auditedEnd": audited_end,
        "changeAmount": audited_end - row["priorEnd"],
        "changeRate": _change_rate(audited_end, row["priorEnd"]),
    }


def _audited_end_total(computed: Sequence[Mapping[str, float]]) -> float:
    """审定期末合计，照抄 ``useM9Detail.totals.auditedEnd``（审定期初合计 + 审定税后净额合计）。"""
    audited_begin = sum(c["auditedBegin"] for c in computed)
    audited_pre_tax = sum(c["auditedPreTax"] for c in computed)
    audited_tax = sum(c["auditedTax"] for c in computed)
    return audited_begin + (audited_pre_tax - audited_tax)


M9_DETAIL_SPEC = DetailSheetSpec(
    sheet_code=DETAIL_SHEET,
    sheet_title="明细表M9-2",
    full_item_id="M9-2-detail-rows",
    full_storage="conclusion",
    fallback_sources=(),
    row_item_prefix="M9-2-row-",
    total_item_id="M9-2-auditedEndTotal",
    row_key_prefix="m9-detail-import",
    input_columns=(
        InputColumn("OCI项目", "itemName", "text"),
        InputColumn(
            "分类",
            "ociCategory",
            "choice",
            choices=OCI_CATEGORIES,
            choice_aliases=OCI_CATEGORY_ALIASES,
            choice_default="nonReclass",
        ),
        InputColumn("期初", "beginning"),
        InputColumn("本期税前发生", "preTaxAmount"),
        InputColumn("所得税影响", "taxEffect"),
        InputColumn("贷方(增加)", "creditAmount"),
        InputColumn("借方(减少)", "debitAmount"),
        InputColumn("期初AJE", "beginAje"),
        InputColumn("期初RJE", "beginRje"),
        InputColumn("税前AJE", "preTaxAje"),
        InputColumn("税前RJE", "preTaxRje"),
        InputColumn("税额AJE", "taxAje"),
        InputColumn("税额RJE", "taxRje"),
        InputColumn("上期期初", "priorBeginning"),
        InputColumn("上期税后净额", "priorAfterTaxNet"),
        InputColumn("上期期末", "priorEnd"),
        InputColumn("来源底稿", "sourceWpCode", "text"),
        InputColumn("备注", "remark", "text"),
    ),
    computed_columns=(
        ComputedColumn("税后净额", "afterTaxNet"),
        ComputedColumn("期末", "endBalance"),
        ComputedColumn("审定期初", "auditedBegin"),
        ComputedColumn("审定税前", "auditedPreTax"),
        ComputedColumn("审定税额", "auditedTax"),
        ComputedColumn("审定税后净额", "auditedAfterTaxNet"),
        ComputedColumn("审定期末", "auditedEnd"),
        ComputedColumn("变动额", "changeAmount"),
        ComputedColumn("变动率", "changeRate", "ratio"),
    ),
    compute=_compute_detail,
    audited_end_total=_audited_end_total,
    guidance=(
        "分类填「不可重分类」或「可重分类」（也认「以后不能 / 能重分类进损益」）",
        "税后净额 = 本期税前发生 − 所得税影响；期末 = 期初 + 贷方(增加) − 借方(减少)（权益类贷方）",
        "审定期初 = 期初 + 期初AJE + 期初RJE；审定税前 = 本期税前发生 + 税前AJE + 税前RJE",
        "审定税额 = 所得税影响 + 税额AJE + 税额RJE；审定税后净额 = 审定税前 − 审定税额",
        "审定期末 = 审定期初 + 审定税后净额；变动额 = 审定期末 − 上期期末",
    ),
)

#: 本前缀长路由三态支持的 sheet（白名单唯一真源）。界面只有 M9-2 有导入导出入口。
SUPPORTED_SHEETS: dict[str, DetailSheetSpec] = {DETAIL_SHEET: M9_DETAIL_SPEC}


def resolve_sheets(sheet: str | None) -> list[DetailSheetSpec]:
    """``None`` / 空 ⇒ 全部支持的 sheet；不认识的 sheet ⇒ 400，不静默回退成导出全部。"""
    code = (sheet or "").strip()
    if not code:
        return list(SUPPORTED_SHEETS.values())
    spec = SUPPORTED_SHEETS.get(code)
    if spec is None:
        raise HTTPException(status_code=400, detail=unknown_sheet_message(code, list(SUPPORTED_SHEETS)))
    return [spec]


async def generate_export_template(wp_id: str, db: AsyncSession, *, sheet: str | None = None) -> io.BytesIO:
    """空白模板（输入列表头 +「编制说明」）。不读库，``wp_id`` / ``db`` 只为与路由签名一致。"""
    return export_template(resolve_sheets(sheet))


async def generate_export_data(wp_id: str, db: AsyncSession, *, sheet: str | None = None) -> io.BytesIO:
    """当前数据（按界面恢复口径读回 + 公式列 + 合计行）。"""
    return await export_data(db, wp_id, resolve_sheets(sheet))


async def import_data(
    wp_id: str,
    content: bytes,
    db: AsyncSession,
    *,
    sheet: str | None = None,
    updated_by: Any = None,
) -> dict[str, Any]:
    """导入并整表替换明细行。前端把 sheet 放在表单字段里（路由收不到）⇒ 缺省按 M9-2。"""
    (spec,) = resolve_sheets(sheet or DETAIL_SHEET)
    return await import_sheet(db, wp_id, content, spec, updated_by=updated_by)


# ── 审定表 M9-1 行（权益类公式校验的取数）──────────────────────────────────


async def get_adjudication_rows(
    wp_id: str, db: AsyncSession
) -> tuple[list[dict[str, Any]], list[str]]:
    """读审定表已保存的行，返回 ``(rows, warnings)``。

    每行 ``{rowKey, itemName, begin, credit, debit, reportedEnd}``：期初 / 贷方 / 借方取界面的
    未审期初与本期发生，``reportedEnd`` 取该行「未审数」（期末账面数）—— 校验的就是
    「期初 + 贷方 − 借方」能否与账面期末对上。库里没有未审数字段的行 ``reportedEnd`` 为 None
    （只算期末不比对）。坏 JSON 不静默跳过，写进 warnings。
    """
    wp_uuid = require_wp_uuid(wp_id)
    result = await db.execute(
        sa.text(
            "SELECT item_id, remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE :pattern ESCAPE '\\' ORDER BY item_id"
        ),
        {"wp_id": str(wp_uuid), "pattern": like_prefix(ADJUDICATION_ITEM_PREFIX)},
    )
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item_id, remark in result.fetchall():
        if not item_id.endswith(ADJUDICATION_ITEM_SUFFIX) or not remark:
            continue
        try:
            data = json.loads(remark)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("M9-1 审定表行读取：%s 不是有效 JSON（wp=%s）：%s", item_id, wp_uuid, exc)
            warnings.append(f"「{item_id}」的内容不是有效的 JSON，未参与校验")
            continue
        if not isinstance(data, Mapping):
            warnings.append(f"「{item_id}」不是行对象，未参与校验")
            continue
        rows.append(
            {
                "rowKey": str(data.get("key") or item_id),
                "itemName": str(data.get("itemName") or ""),
                "begin": lenient_number(data.get("beginning")),
                "credit": lenient_number(data.get("creditAmount")),
                "debit": lenient_number(data.get("debitAmount")),
                "reportedEnd": lenient_number(data.get("unadjusted")) if "unadjusted" in data else None,
            }
        )
    return rows, warnings
