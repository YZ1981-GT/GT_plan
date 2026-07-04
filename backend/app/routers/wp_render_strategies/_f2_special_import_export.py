"""F2 特殊组（合同履约+IPO）— 导入导出."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    export_row_by_keys,
    import_rows_generic,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    upsert_json_rows,
    workbook_to_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f2-spe-import-export"])

_STORAGE_FIELD = "remark"

_F2_SPE_SPECS: dict[str, dict[str, Any]] = {
    "F2-55": {
        "item_id": "F2-55-rows",
        "title": "F2-55 合同履约成本明细",
        "headers": ["项目编码", "项目名称", "合同名称", "合同金额", "期初设备", "期初建安", "期初人工", "期初其他", "备注"],
        "field_keys": ["projectCode", "projectName", "contractName", "contractAmount", "opening_equipment", "opening_construction", "opening_labor", "opening_other", "remark"],
        "guidance": ["F2-55 合同履约成本 编制说明", "", "37列宽表，导入核心列后系统可扩展。"],
    },
    "F2-56": {
        "item_id": "F2-56-rows",
        "title": "F2-56 合同履约成本检查",
        "headers": ["项目", "凭证日期", "凭证号", "合同号", "金额", "设备材料", "建安", "是否正确", "备注"],
        "field_keys": ["projectName", "voucherDate", "voucherNo", "contractNo", "amount", "equipmentAmt", "constructionAmt", "isCorrect", "remark"],
        "guidance": ["F2-56 检查表 编制说明", "", "科目1405合同履约成本。"],
    },
    "F2-57": {
        "item_id": "F2-57-rows",
        "title": "F2-57 减值准备测算",
        "headers": ["项目", "预计总收入", "预计总成本", "已确认收入", "已发生成本", "账面价值", "管理层计提", "备注"],
        "field_keys": ["projectName", "totalRevenue", "totalCost", "recognizedRevenue", "incurredCost", "bookValue", "mgmtProvision", "remark"],
        "guidance": ["F2-57 减值测算 编制说明", "", "减值=max(0,账面-可收回)。"],
    },
    "F2-58": {
        "item_id": "F2-58-rows",
        "title": "F2-58 亏损合同测算",
        "headers": ["项目", "预计总收入", "预计总成本", "完工进度", "已确认预计损失", "管理层计提", "备注"],
        "field_keys": ["projectName", "totalRevenue", "totalCost", "completionRate", "recognizedLoss", "mgmtProvision", "remark"],
        "guidance": ["F2-58 亏损合同 编制说明", "", "亏损=总成本>总收入。"],
    },
    "F2-61": {
        "item_id": "F2-61-rows",
        "title": "F2-61 采购价格分析",
        "headers": ["材料名称", "规格", "上半年均价", "下半年均价", "年度均价", "备注"],
        "field_keys": ["materialName", "spec", "h1AvgPrice", "h2AvgPrice", "yearAvgPrice", "remark"],
        "guidance": ["F2-61 IPO采购价格 编制说明", "", "单价异常±30%需关注。"],
    },
    "F2-64": {
        "item_id": "F2-64-rows",
        "title": "F2-64 单耗分析",
        "headers": ["产品", "材料", "投入量", "产出量", "标准单耗", "实际单耗", "差异率", "备注"],
        "field_keys": ["productName", "materialName", "inputQty", "outputQty", "standardConsumption", "actualConsumption", "varianceRate", "remark"],
        "guidance": ["F2-64 单耗分析 编制说明", "", "差异率>10%需关注。"],
    },
    "F2-62": {
        "item_id": "F2-62-rows",
        "title": "F2-62 原材料单价分析",
        "headers": ["材料名称", "规格", "单位", "T期单价", "T-1单价", "T-2单价", "行业均价", "备注"],
        "field_keys": ["materialName", "spec", "unit", "priceT", "priceT1", "priceT2", "industryAvgPrice", "remark"],
        "guidance": ["F2-62 单价分析 编制说明", "", "偏离度>20%需关注。"],
    },
    "F2-63": {
        "item_id": "F2-63-rows",
        "title": "F2-63 产量与产能/能耗",
        "headers": ["产品名称", "生产线", "设计产能", "实际产量", "电耗", "水耗", "气耗", "备注"],
        "field_keys": ["productName", "productLine", "designCapacity", "actualOutput", "elecTotal", "waterTotal", "gasTotal", "remark"],
        "guidance": ["F2-63 产能能耗 编制说明", "", "超产能/能耗异常需关注。"],
    },
    "F2-65": {
        "item_id": "F2-65-rows",
        "title": "F2-65 关联方定价-询价函",
        "headers": ["关联方", "品名", "关联价格", "第三方", "询价价格", "结论", "备注"],
        "field_keys": ["relatedParty", "itemName", "relatedPrice", "thirdPartyName", "inquiryPrice", "conclusion", "remark"],
        "guidance": ["F2-65 询价函 编制说明", "", "价差>10%需关注。"],
    },
    "F2-66": {
        "item_id": "F2-66-rows",
        "title": "F2-66 关联方定价-市场价",
        "headers": ["关联方", "品名", "关联价格", "市场价格", "结论", "备注"],
        "field_keys": ["relatedParty", "itemName", "relatedPrice", "marketPrice", "conclusion", "remark"],
        "guidance": ["F2-66 市场价 编制说明", "", "价差>10%需关注。"],
    },
    "F2-67": {
        "item_id": "F2-67-rows",
        "title": "F2-67 未披露关联方",
        "headers": ["供应商", "统一社会信用代码", "关系类型", "是否披露", "核查结论", "风险等级", "备注"],
        "field_keys": ["supplierName", "creditCode", "relationType", "isDisclosed", "checkConclusion", "riskLevel", "remark"],
        "guidance": ["F2-67 未披露关联方 编制说明", "", "未披露关联方需重点核查。"],
    },
    "F2-68": {
        "item_id": "F2-68-rows",
        "title": "F2-68 供应商结构",
        "headers": ["供应商", "采购金额", "占比", "排名", "上期排名", "是否新增", "备注"],
        "field_keys": ["supplierName", "purchaseAmount", "sharePct", "rank", "priorRank", "isNew", "remark"],
        "guidance": ["F2-68 供应商结构 编制说明", "", "前5/前10集中度自动汇总。"],
    },
    "F2-69": {
        "item_id": "F2-69-rows",
        "title": "F2-69 供应商核查清单",
        "headers": ["供应商", "总体评价", "风险分类", "跟进事项", "负责人", "备注"],
        "field_keys": ["supplierName", "overallEval", "riskCategory", "followUp", "owner", "remark"],
        "guidance": ["F2-69 核查清单 编制说明", "", "10项核查进度自动汇总。"],
    },
    "F2-71": {
        "item_id": "F2-71-rows",
        "title": "F2-71 访谈记录汇总",
        "headers": ["供应商", "访谈日期", "方式", "受访人", "职务", "结论", "备注"],
        "field_keys": ["supplierName", "interviewDate", "method", "interviewee", "intervieweeTitle", "conclusion", "remark"],
        "guidance": ["F2-71 访谈汇总 编制说明", "", "异常/疑点结论需跟进。"],
    },
    "F2-70": {
        "item_id": "F2-70-entities",
        "entity_mode": True,
        "entity_kind": "supplier",
        "title": "F2-70 供应商信息核查",
        "headers": ["内部ID", "供应商", "信用代码", "法定代表人", "注册资本", "核查方式", "核查结论", "合作年限", "交易金额"],
        "field_keys": ["id", "supplierName", "creditCode", "legalRepresentative", "registeredCapital", "checkMethod", "checkConclusion", "cooperationYears", "transactionAmount"],
        "guidance": ["F2-70 供应商核查 编制说明", "", "每行对应一家供应商实体。", "内部ID 用于再次导入时保留实体标识，可留空由系统生成。"],
    },
    "F2-72": {
        "item_id": "F2-72-entities",
        "entity_mode": True,
        "entity_kind": "interview",
        "title": "F2-72 供应商访谈记录",
        "headers": ["内部ID", "供应商", "访谈日期", "受访人", "主题", "审计关注点", "结论", "问答摘要"],
        "field_keys": ["id", "supplierName", "interviewDate", "interviewee", "topic", "auditFocus", "conclusion", "qaSummary"],
        "guidance": ["F2-72 访谈记录 编制说明", "", "问答摘要格式：Q:问题 A:回答，多组换行。", "内部ID 用于再次导入时保留实体标识，可留空由系统生成。"],
    },
}

_SUPPORTED = set(_F2_SPE_SPECS.keys())


def _validate(sheet: str) -> None:
    if sheet not in _SUPPORTED:
        raise HTTPException(400, f"不支持的sheet: {sheet}")


def _spec(sheet: str) -> dict[str, Any]:
    return _F2_SPE_SPECS[sheet]


def _normalize(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, row in enumerate(rows):
        r = dict(row)
        if not r.get("id"):
            r["id"] = r.get("rowId") or f"imp-{uuid.uuid4().hex[:12]}"
        if not r.get("rowId"):
            r["rowId"] = r["id"]
        if not r.get("seq"):
            r["seq"] = i + 1
        out.append(r)
    return out


def _num(val: Any, default: float = 0) -> float:
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _entities_to_flat(sheet: str, entities: list[dict]) -> list[dict]:
    sp = _F2_SPE_SPECS[sheet]
    keys = sp["field_keys"]
    if sp.get("entity_kind") == "supplier":
        out: list[dict] = []
        for e in entities:
            out.append({k: e.get(k, "") for k in keys})
        return out
    if sp.get("entity_kind") == "interview":
        out = []
        for e in entities:
            qa_lines = []
            for qa in e.get("qaPairs") or []:
                q = (qa.get("question") or "").strip()
                a = (qa.get("answer") or "").strip()
                if q or a:
                    qa_lines.append(f"Q:{q} A:{a}")
            flat = {k: e.get(k, "") for k in keys if k != "qaSummary"}
            flat["qaSummary"] = "\n".join(qa_lines)
            out.append(flat)
        return out
    return entities


def _flat_to_entities(sheet: str, rows: list[dict]) -> list[dict]:
    sp = _F2_SPE_SPECS[sheet]
    if sp.get("entity_kind") == "supplier":
        entities: list[dict] = []
        for r in rows:
            eid = r.get("id") or f"imp-{uuid.uuid4().hex[:12]}"
            entities.append({
                "id": eid,
                "supplierName": r.get("supplierName") or "",
                "creditCode": r.get("creditCode") or "",
                "legalRepresentative": r.get("legalRepresentative") or "",
                "registeredCapital": str(r.get("registeredCapital") or ""),
                "establishDate": r.get("establishDate") or "",
                "businessScope": r.get("businessScope") or "",
                "operatingAddress": r.get("operatingAddress") or "",
                "employeeCount": int(_num(r.get("employeeCount"))),
                "mainCustomers": r.get("mainCustomers") or "",
                "financialStatus": r.get("financialStatus") or "",
                "cooperationYears": int(_num(r.get("cooperationYears"))),
                "transactionAmount": _num(r.get("transactionAmount")),
                "checkMethod": r.get("checkMethod") or "",
                "checkConclusion": r.get("checkConclusion") or "",
            })
        return entities
    if sp.get("entity_kind") == "interview":
        entities = []
        for r in rows:
            eid = r.get("id") or f"imp-{uuid.uuid4().hex[:12]}"
            qa_pairs: list[dict] = []
            summary = str(r.get("qaSummary") or "").strip()
            if summary:
                for line in summary.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    q, _, a = line.partition(" A:")
                    q = q.removeprefix("Q:").strip()
                    qa_pairs.append({"id": f"qa-{uuid.uuid4().hex[:8]}", "question": q, "answer": a.strip()})
            if not qa_pairs:
                qa_pairs = [{"id": f"qa-{uuid.uuid4().hex[:8]}", "question": "", "answer": ""}]
            entities.append({
                "id": eid,
                "supplierName": r.get("supplierName") or "",
                "interviewDate": r.get("interviewDate") or "",
                "interviewee": r.get("interviewee") or "",
                "topic": r.get("topic") or "",
                "auditFocus": r.get("auditFocus") or "",
                "conclusion": r.get("conclusion") or "",
                "qaPairs": qa_pairs,
            })
        return entities
    return _normalize(rows)


@router.post("/api/workpapers/{wp_id}/f2-spe/export-template")
async def f2_spe_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate(sheet)
    sp = _spec(sheet)
    wb = build_workbook_template(sheet, sp["headers"], title=sp["title"], guidance=sp["guidance"])
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/f2-spe/export-data")
async def f2_spe_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate(sheet)
    sp = _spec(sheet)
    raw_rows = await load_json_rows(db, wp_id, sp["item_id"], field=_STORAGE_FIELD)
    rows = _entities_to_flat(sheet, raw_rows) if sp.get("entity_mode") else raw_rows
    wb = build_workbook_template(sheet, sp["headers"], title=sp["title"], guidance=sp["guidance"])
    ws = wb[sheet]
    for d in rows:
        ws.append(export_row_by_keys(d, sp["field_keys"]))
    return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/f2-spe/import-data")
async def f2_spe_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _validate(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")
    sp = _spec(sheet)
    try:
        actual, raw = parse_upload_xlsx(content, sp["headers"], header_row=2)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "imported_count": 0}
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件")
    rows, truncated = import_rows_generic(
        raw, actual, sp["field_keys"],
        parse_fn=lambda r, h: parse_row_by_headers(r, h, sp["field_keys"]),
    )
    payload = _flat_to_entities(sheet, rows) if sp.get("entity_mode") else _normalize(rows)
    await upsert_json_rows(db, wp_id, sp["item_id"], payload, field=_STORAGE_FIELD)
    out: dict[str, Any] = {"ok": True, "imported_count": len(payload), "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
