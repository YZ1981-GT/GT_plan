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


def _f2_61_headers() -> list[str]:
    """F2-61 扁平表头：材料 + 12月×(金额/数量/市场单价) + 上期对比列."""
    heads = ["材料名称", "单位"]
    for m in range(1, 13):
        heads += [f"{m}月金额", f"{m}月数量", f"{m}月市场单价"]
    heads += [
        "上期末金额", "上期末数量", "上期末市场单价",
        "上期合计金额", "上期合计数量", "上期平均市场单价", "备注",
    ]
    return heads


def _f2_61_field_keys() -> list[str]:
    keys = ["materialName", "unit"]
    for m in range(12):
        keys += [f"m{m}_amount", f"m{m}_qty", f"m{m}_marketPrice"]
    keys += [
        "priorEndAmount", "priorEndQty", "priorEndMarketPrice",
        "priorTotalAmount", "priorTotalQty", "priorAvgMarketPrice", "remark",
    ]
    return keys


def _f2_61_materials_to_flat(materials: list[dict]) -> list[dict]:
    out: list[dict] = []
    for mat in materials:
        months = mat.get("months") or []
        flat: dict[str, Any] = {
            "materialName": mat.get("materialName", ""),
            "unit": mat.get("unit", ""),
            "remark": mat.get("remark", ""),
        }
        for i in range(12):
            cell = months[i] if i < len(months) and isinstance(months[i], dict) else {}
            flat[f"m{i}_amount"] = cell.get("amount", 0)
            flat[f"m{i}_qty"] = cell.get("qty", 0)
            flat[f"m{i}_marketPrice"] = cell.get("marketPrice", 0)
        prior_end = mat.get("priorEnd") or {}
        flat["priorEndAmount"] = prior_end.get("amount", 0)
        flat["priorEndQty"] = prior_end.get("qty", 0)
        flat["priorEndMarketPrice"] = prior_end.get("marketPrice", 0)
        flat["priorTotalAmount"] = mat.get("priorTotalAmount", 0)
        flat["priorTotalQty"] = mat.get("priorTotalQty", 0)
        flat["priorAvgMarketPrice"] = mat.get("priorAvgMarketPrice", 0)
        out.append(flat)
    return out


def _f2_61_flat_to_materials(rows: list[dict]) -> list[dict]:
    materials: list[dict] = []
    for r in rows:
        months = [
            {
                "amount": _num(r.get(f"m{i}_amount")),
                "qty": _num(r.get(f"m{i}_qty")),
                "marketPrice": _num(r.get(f"m{i}_marketPrice")),
            }
            for i in range(12)
        ]
        materials.append({
            "id": r.get("id") or f"imp-{uuid.uuid4().hex[:12]}",
            "materialName": str(r.get("materialName") or ""),
            "unit": str(r.get("unit") or ""),
            "months": months,
            "priorEnd": {
                "amount": _num(r.get("priorEndAmount")),
                "qty": _num(r.get("priorEndQty")),
                "marketPrice": _num(r.get("priorEndMarketPrice")),
            },
            "priorTotalAmount": _num(r.get("priorTotalAmount")),
            "priorTotalQty": _num(r.get("priorTotalQty")),
            "priorAvgMarketPrice": _num(r.get("priorAvgMarketPrice")),
            "remark": str(r.get("remark") or ""),
        })
    return materials


def _f2_62_to_flat(data: dict) -> list[dict]:
    """F2-62 三层嵌套模型展开为易导入的长表."""
    out: list[dict] = []
    month_labels = [f"{i}月" for i in range(1, 13)]
    monthly_sections = [
        ("同一供应商不同物料", "supplierGroups"),
        ("同一原材料不同供应商", "materialGroups"),
    ]
    for section_label, key in monthly_sections:
        for group in data.get(key) or []:
            for item in group.get("items") or []:
                months = item.get("months") or []
                for i, period in enumerate(month_labels):
                    cell = months[i] if i < len(months) and isinstance(months[i], dict) else {}
                    out.append({
                        "section": section_label,
                        "groupName": group.get("name", ""),
                        "itemName": item.get("name", ""),
                        "period": period,
                        "amount": cell.get("amount", 0),
                        "qty": cell.get("qty", 0),
                    })
    for group in data.get("specGroups") or []:
        for item in group.get("items") or []:
            for period in item.get("periods") or []:
                out.append({
                    "section": "同类原材料不同规格",
                    "groupName": group.get("categoryName", ""),
                    "itemName": item.get("spec", ""),
                    "period": period.get("label", ""),
                    "amount": period.get("amount", 0),
                    "qty": period.get("qty", 0),
                })
    return out


def _f2_62_flat_to_object(rows: list[dict]) -> dict:
    """长表还原为 F2-62 三层嵌套模型."""
    result: dict[str, list[dict]] = {
        "supplierGroups": [],
        "materialGroups": [],
        "specGroups": [],
    }
    monthly_sections = {
        "同一供应商不同物料": "supplierGroups",
        "同一原材料不同供应商": "materialGroups",
    }
    month_index = {f"{i}月": i - 1 for i in range(1, 13)}

    for section_label, target_key in monthly_sections.items():
        grouped: dict[str, dict[str, list[dict]]] = {}
        for row in rows:
            if str(row.get("section") or "").strip() != section_label:
                continue
            group_name = str(row.get("groupName") or "").strip()
            item_name = str(row.get("itemName") or "").strip()
            grouped.setdefault(group_name, {}).setdefault(item_name, []).append(row)
        for group_name, items in grouped.items():
            out_items = []
            for item_name, item_rows in items.items():
                months = [{"amount": 0, "qty": 0} for _ in range(12)]
                for row in item_rows:
                    idx = month_index.get(str(row.get("period") or "").strip())
                    if idx is not None:
                        months[idx] = {
                            "amount": _num(row.get("amount")),
                            "qty": _num(row.get("qty")),
                        }
                out_items.append({
                    "id": f"imp-{uuid.uuid4().hex[:12]}",
                    "name": item_name,
                    "months": months,
                })
            result[target_key].append({
                "id": f"imp-{uuid.uuid4().hex[:12]}",
                "name": group_name,
                "items": out_items,
            })

    spec_grouped: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        if str(row.get("section") or "").strip() != "同类原材料不同规格":
            continue
        group_name = str(row.get("groupName") or "").strip()
        item_name = str(row.get("itemName") or "").strip()
        spec_grouped.setdefault(group_name, {}).setdefault(item_name, []).append(row)
    default_periods = ["本期", "上期", "上上期"]
    for group_name, items in spec_grouped.items():
        out_items = []
        for item_name, item_rows in items.items():
            by_period = {
                str(row.get("period") or "").strip(): row
                for row in item_rows
            }
            periods = []
            for label in default_periods:
                row = by_period.get(label, {})
                periods.append({
                    "label": label,
                    "amount": _num(row.get("amount")),
                    "qty": _num(row.get("qty")),
                })
            out_items.append({
                "id": f"imp-{uuid.uuid4().hex[:12]}",
                "spec": item_name,
                "periods": periods,
            })
        result["specGroups"].append({
            "id": f"imp-{uuid.uuid4().hex[:12]}",
            "categoryName": group_name,
            "items": out_items,
        })
    return result


_F2_63_SECTION_CAPACITY = "产能比较"
_F2_63_SECTION_STORAGE = "库存容量"
_F2_63_SECTION_ENERGY = "能源采购"
_F2_63_SECTION_PRODUCT = "产品能耗"


def _f2_63_to_flat(data: dict) -> list[dict]:
    """F2-63 四区块模型展开为统一列的长表（数值列含义随数据区变化，见导入说明行）."""
    out: list[dict] = []
    for r in data.get("capacityRows") or []:
        out.append({
            "section": _F2_63_SECTION_CAPACITY,
            "name": r.get("inventoryName", ""),
            "subName": "",
            "v1": _num(r.get("annualOutput")),
            "v2": _num(r.get("annualCapacity")),
            "v3": 0, "v4": 0, "v5": 0, "v6": 0,
            "remark": r.get("remark", ""),
        })
    for r in data.get("storageRows") or []:
        out.append({
            "section": _F2_63_SECTION_STORAGE,
            "name": r.get("warehouseName", ""),
            "subName": r.get("inventoryName", ""),
            "v1": _num(r.get("actualStock")),
            "v2": _num(r.get("storageCapacity")),
            "v3": _num(r.get("orderQty")),
            "v4": _num(r.get("orderAmount")),
            "v5": _num(r.get("postSaleQty")),
            "v6": _num(r.get("postSaleAmount")),
            "remark": "",
        })
    for r in data.get("energyRows") or []:
        out.append({
            "section": _F2_63_SECTION_ENERGY,
            "name": r.get("itemName", ""),
            "subName": "",
            "v1": _num(r.get("currentQty")),
            "v2": _num(r.get("currentAmount")),
            "v3": _num(r.get("priorQty")),
            "v4": _num(r.get("priorAmount")),
            "v5": 0, "v6": 0,
            "remark": "",
        })
    for r in data.get("productEnergyRows") or []:
        out.append({
            "section": _F2_63_SECTION_PRODUCT,
            "name": r.get("productName", ""),
            "subName": "",
            "v1": _num(r.get("annualOutput")),
            "v2": _num(r.get("waterUsage")),
            "v3": _num(r.get("elecUsage")),
            "v4": _num(r.get("gasUsage")),
            "v5": _num(r.get("priorUnitEnergy")),
            "v6": 0,
            "remark": "",
        })
    return out


def _f2_63_flat_to_object(rows: list[dict]) -> dict:
    """长表还原为 F2-63 四区块模型."""
    result: dict[str, list[dict]] = {
        "capacityRows": [],
        "storageRows": [],
        "energyRows": [],
        "productEnergyRows": [],
    }

    def _rid() -> str:
        return f"imp-{uuid.uuid4().hex[:12]}"

    for row in rows:
        section = str(row.get("section") or "").strip()
        name = str(row.get("name") or "").strip()
        sub_name = str(row.get("subName") or "").strip()
        remark = str(row.get("remark") or "").strip()
        if section == _F2_63_SECTION_CAPACITY:
            result["capacityRows"].append({
                "id": _rid(),
                "inventoryName": name,
                "annualOutput": _num(row.get("v1")),
                "annualCapacity": _num(row.get("v2")),
                "remark": remark,
            })
        elif section == _F2_63_SECTION_STORAGE:
            result["storageRows"].append({
                "id": _rid(),
                "warehouseName": name,
                "inventoryName": sub_name,
                "actualStock": _num(row.get("v1")),
                "storageCapacity": _num(row.get("v2")),
                "orderQty": _num(row.get("v3")),
                "orderAmount": _num(row.get("v4")),
                "postSaleQty": _num(row.get("v5")),
                "postSaleAmount": _num(row.get("v6")),
            })
        elif section == _F2_63_SECTION_ENERGY:
            result["energyRows"].append({
                "id": _rid(),
                "itemName": name,
                "currentQty": _num(row.get("v1")),
                "currentAmount": _num(row.get("v2")),
                "priorQty": _num(row.get("v3")),
                "priorAmount": _num(row.get("v4")),
            })
        elif section == _F2_63_SECTION_PRODUCT:
            result["productEnergyRows"].append({
                "id": _rid(),
                "productName": name,
                "annualOutput": _num(row.get("v1")),
                "waterUsage": _num(row.get("v2")),
                "elecUsage": _num(row.get("v3")),
                "gasUsage": _num(row.get("v4")),
                "priorUnitEnergy": _num(row.get("v5")),
            })
    return result


def _f2_64_to_flat(data: dict) -> list[dict]:
    """F2-64 四区块月度模型展开为长表。自动计算列不导出为输入值。"""
    out: list[dict] = [{
        "section": "基本信息",
        "period": "",
        "month": 0,
        "name": data.get("productName", ""),
        "v1": 0, "v2": 0, "v3": 0, "v4": 0, "v5": 0, "v6": 0,
        "text1": data.get("currentYear", "本年"),
        "text2": data.get("priorYear", "上年"),
        "text3": "|".join(data.get("materialNames") or []),
        "remark": "|".join(data.get("consumptionMaterialNames") or [])
            + "||" + "|".join(data.get("peerCompanies") or []),
    }]
    mappings = [
        ("成本构成", "costStructureRows",
         ["material1", "material2", "material3", "otherMaterial", "directLabor", "manufacturing"]),
        ("成本衔接", "costFlowRows",
         ["openingWip", "materialInput", "laborInput", "manufacturingInput", "endingWip", "outputQty"]),
        ("单位成本", "unitCostRows",
         ["openingFinished", "directMaterial", "directLabor", "manufacturing", "endingFinished", "outputQty"]),
    ]
    for section, key, fields in mappings:
        for row in data.get(key) or []:
            item = {
                "section": section,
                "period": row.get("period", ""),
                "month": row.get("month", 0),
                "name": "",
                "text1": "", "text2": "", "text3": "", "remark": "",
            }
            item.update({f"v{i + 1}": _num(row.get(field)) for i, field in enumerate(fields)})
            out.append(item)
    for row in data.get("peerRows") or []:
        out.append({
            "section": "同行比较", "period": "", "month": 0,
            "name": row.get("item", ""),
            "v1": _num(row.get("auditedUnit")),
            "v2": _num(row.get("peer1Unit")),
            "v3": _num(row.get("peer2Unit")),
            "v4": _num(row.get("peer3Unit")),
            "v5": 0, "v6": 0,
            "text1": "", "text2": "", "text3": "", "remark": "",
        })
    for row in data.get("materialConsumptionRows") or []:
        m1 = row.get("material1") or {}
        m2 = row.get("material2") or {}
        out.append({
            "section": "材料耗用",
            "period": row.get("period", ""),
            "month": row.get("month", 0),
            "name": "",
            "v1": _num(row.get("outputQty")),
            "v2": _num(m1.get("inputQty")),
            "v3": _num(m1.get("inputAmount")),
            "v4": _num(m2.get("inputQty")),
            "v5": _num(m2.get("inputAmount")),
            "v6": 0,
            "text1": m1.get("unit", ""),
            "text2": m2.get("unit", ""),
            "text3": "", "remark": "",
        })
    return out


def _f2_64_flat_to_object(rows: list[dict]) -> dict:
    """F2-64 长表还原为四区块月度模型。"""
    defaults = {
        "productName": "",
        "currentYear": "本年",
        "priorYear": "上年",
        "materialNames": ["主要原材料1", "主要原材料2", "主要原材料3"],
        "consumptionMaterialNames": ["主要原材料1", "主要原材料2"],
        "peerCompanies": ["同行业公司1", "同行业公司2", "同行业公司3"],
        "costStructureRows": [],
        "costFlowRows": [],
        "unitCostRows": [],
        "peerRows": [],
        "materialConsumptionRows": [],
    }
    meta = next((r for r in rows if str(r.get("section") or "").strip() == "基本信息"), None)
    if meta:
        defaults["productName"] = str(meta.get("name") or "")
        defaults["currentYear"] = str(meta.get("text1") or "本年")
        defaults["priorYear"] = str(meta.get("text2") or "上年")
        material_names = [x for x in str(meta.get("text3") or "").split("|") if x]
        if material_names:
            defaults["materialNames"] = (material_names + defaults["materialNames"])[:3]
        remark_parts = str(meta.get("remark") or "").split("||", 1)
        consumption_names = [x for x in remark_parts[0].split("|") if x]
        if consumption_names:
            defaults["consumptionMaterialNames"] = (
                consumption_names + defaults["consumptionMaterialNames"]
            )[:2]
        if len(remark_parts) > 1:
            peer_names = [x for x in remark_parts[1].split("|") if x]
            if peer_names:
                defaults["peerCompanies"] = (peer_names + defaults["peerCompanies"])[:3]

    def _id() -> str:
        return f"imp-{uuid.uuid4().hex[:12]}"

    field_maps = {
        "成本构成": ("costStructureRows",
            ["material1", "material2", "material3", "otherMaterial", "directLabor", "manufacturing"]),
        "成本衔接": ("costFlowRows",
            ["openingWip", "materialInput", "laborInput", "manufacturingInput", "endingWip", "outputQty"]),
        "单位成本": ("unitCostRows",
            ["openingFinished", "directMaterial", "directLabor", "manufacturing", "endingFinished", "outputQty"]),
    }
    for row in rows:
        section = str(row.get("section") or "").strip()
        if section in field_maps:
            target, fields = field_maps[section]
            item = {
                "id": _id(),
                "period": "prior" if str(row.get("period") or "").strip() == "prior" else "current",
                "month": int(_num(row.get("month")) or 1),
            }
            item.update({field: _num(row.get(f"v{i + 1}")) for i, field in enumerate(fields)})
            defaults[target].append(item)
        elif section == "同行比较":
            defaults["peerRows"].append({
                "id": _id(),
                "item": str(row.get("name") or ""),
                "auditedUnit": _num(row.get("v1")),
                "peer1Unit": _num(row.get("v2")),
                "peer2Unit": _num(row.get("v3")),
                "peer3Unit": _num(row.get("v4")),
            })
        elif section == "材料耗用":
            defaults["materialConsumptionRows"].append({
                "id": _id(),
                "period": "prior" if str(row.get("period") or "").strip() == "prior" else "current",
                "month": int(_num(row.get("month")) or 1),
                "outputQty": _num(row.get("v1")),
                "material1": {
                    "inputQty": _num(row.get("v2")),
                    "unit": str(row.get("text1") or ""),
                    "inputAmount": _num(row.get("v3")),
                },
                "material2": {
                    "inputQty": _num(row.get("v4")),
                    "unit": str(row.get("text2") or ""),
                    "inputAmount": _num(row.get("v5")),
                },
            })
    return defaults


def _f2_65_to_flat(data: dict) -> list[dict]:
    """F2-65 分组月度询价模型展开为普通表。"""
    out: list[dict] = []
    for group in data.get("groups") or []:
        suppliers = list(group.get("comparableSuppliers") or [])
        suppliers += ["", "", "", ""]
        for row in group.get("rows") or []:
            prices = list(row.get("comparablePrices") or [])
            prices += [0, 0, 0, 0]
            out.append({
                "relatedParty": group.get("relatedParty", ""),
                "productName": group.get("productName", ""),
                "month": row.get("month", 0),
                "productSpec": row.get("productSpec", ""),
                "relatedPrice": _num(row.get("relatedPrice")),
                "supplier1": suppliers[0],
                "price1": _num(prices[0]),
                "supplier2": suppliers[1],
                "price2": _num(prices[1]),
                "supplier3": suppliers[2],
                "price3": _num(prices[2]),
                "supplier4": suppliers[3],
                "price4": _num(prices[3]),
                "judgment": row.get("judgment", ""),
                "remark": row.get("remark", ""),
            })
    return out


def _f2_65_flat_to_object(rows: list[dict]) -> dict:
    """普通表按关联方+产品还原为F2-65分组月度模型。"""
    grouped: dict[str, dict] = {}
    for row in rows:
        party = str(row.get("relatedParty") or "").strip()
        product = str(row.get("productName") or "").strip()
        key = f"{party}\x00{product}"
        if key not in grouped:
            grouped[key] = {
                "id": f"imp-{uuid.uuid4().hex[:12]}",
                "relatedParty": party,
                "productName": product,
                "comparableSuppliers": [
                    str(row.get("supplier1") or "询价单位1"),
                    str(row.get("supplier2") or "询价单位2"),
                    str(row.get("supplier3") or "询价单位3"),
                    str(row.get("supplier4") or "询价单位4"),
                ],
                "rows": [],
            }
        month = max(1, min(12, int(_num(row.get("month")) or 1)))
        grouped[key]["rows"].append({
            "id": f"imp-{uuid.uuid4().hex[:12]}",
            "month": month,
            "productSpec": str(row.get("productSpec") or ""),
            "relatedPrice": _num(row.get("relatedPrice")),
            "comparablePrices": [
                _num(row.get("price1")), _num(row.get("price2")),
                _num(row.get("price3")), _num(row.get("price4")),
            ],
            "judgment": str(row.get("judgment") or ""),
            "remark": str(row.get("remark") or ""),
        })
    return {"groups": list(grouped.values())}


def _f2_66_to_flat(data: dict) -> list[dict]:
    """F2-66 分组月度市场价模型展开为普通表。"""
    out: list[dict] = []
    for group in data.get("groups") or []:
        for row in group.get("rows") or []:
            out.append({
                "relatedParty": group.get("relatedParty", ""),
                "productName": group.get("productName", ""),
                "month": row.get("month", 0),
                "purchaseAvgPrice": _num(row.get("purchaseAvgPrice")),
                "marketPriceStart": _num(row.get("marketPriceStart")),
                "marketPriceEnd": _num(row.get("marketPriceEnd")),
                "judgment": row.get("judgment", ""),
                "remark": row.get("remark", ""),
            })
    return out


def _f2_66_flat_to_object(rows: list[dict]) -> dict:
    """普通表按关联方+产品还原为F2-66分组月度模型。"""
    grouped: dict[str, dict] = {}
    for row in rows:
        party = str(row.get("relatedParty") or "").strip()
        product = str(row.get("productName") or "").strip()
        key = f"{party}\x00{product}"
        if key not in grouped:
            grouped[key] = {
                "id": f"imp-{uuid.uuid4().hex[:12]}",
                "relatedParty": party,
                "productName": product,
                "rows": [],
            }
        month = max(1, min(12, int(_num(row.get("month")) or 1)))
        judgment = str(row.get("judgment") or "")
        grouped[key]["rows"].append({
            "id": f"imp-{uuid.uuid4().hex[:12]}",
            "month": month,
            "purchaseAvgPrice": _num(row.get("purchaseAvgPrice")),
            "marketPriceStart": _num(row.get("marketPriceStart")),
            "marketPriceEnd": _num(row.get("marketPriceEnd")),
            "judgment": judgment if judgment in ("是", "否") else "",
            "remark": str(row.get("remark") or ""),
        })
    return {"groups": list(grouped.values())}


def _f2_68_to_flat(data: dict) -> list[dict]:
    """F2-68 本年/上年双区模型展开为普通表。"""
    out: list[dict] = []
    for period, key in (("本年", "currentRows"), ("上年", "priorRows")):
        for row in data.get(key) or []:
            out.append({
                "period": period,
                "supplierName": row.get("supplierName", ""),
                "purchaseAmount": _num(row.get("purchaseAmount")),
                "relatedProduct": row.get("relatedProduct", ""),
                "purchaseQuantity": _num(row.get("purchaseQuantity")),
                "unitPrice": _num(row.get("unitPrice")),
                "creditPeriod": row.get("creditPeriod", ""),
                "paymentMethod": row.get("paymentMethod", ""),
                "transportMethod": row.get("transportMethod", ""),
                "otherTerms": row.get("otherTerms", ""),
                "isRelatedParty": row.get("isRelatedParty", ""),
                "scaleMatches": row.get("scaleMatches", ""),
                "scopeMatches": row.get("scopeMatches", ""),
                "remark": row.get("remark", ""),
                "indexRef": row.get("indexRef", ""),
            })
    return out


def _f2_68_flat_to_object(rows: list[dict]) -> dict:
    """普通表按期间还原为F2-68本年/上年双区模型。"""
    result: dict[str, list[dict]] = {"currentRows": [], "priorRows": []}
    for row in rows:
        period = str(row.get("period") or "本年").strip()
        key = "priorRows" if period in ("上年", "上期", "prior", "T-1") else "currentRows"
        result[key].append({
            "id": f"imp-{uuid.uuid4().hex[:12]}",
            "supplierName": str(row.get("supplierName") or ""),
            "purchaseAmount": _num(row.get("purchaseAmount")),
            "relatedProduct": str(row.get("relatedProduct") or ""),
            "purchaseQuantity": _num(row.get("purchaseQuantity")),
            "unitPrice": _num(row.get("unitPrice")),
            "creditPeriod": str(row.get("creditPeriod") or ""),
            "paymentMethod": str(row.get("paymentMethod") or ""),
            "transportMethod": str(row.get("transportMethod") or ""),
            "otherTerms": str(row.get("otherTerms") or ""),
            "isRelatedParty": str(row.get("isRelatedParty") or ""),
            "scaleMatches": str(row.get("scaleMatches") or ""),
            "scopeMatches": str(row.get("scopeMatches") or ""),
            "remark": str(row.get("remark") or ""),
            "indexRef": str(row.get("indexRef") or ""),
        })
    return result


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
        "object_key": "materials",
        "title": "F2-61 采购价格分析",
        "headers": _f2_61_headers(),
        "field_keys": _f2_61_field_keys(),
        "guidance": [
            "F2-61 采购价格分析 编制说明",
            "",
            "按材料逐月填写入库金额/数量/市场单价，入库单价由系统自动计算（金额÷数量）。",
            "月度单价偏离本期平均±30%、采购均价偏离市场均价±10%系统自动标识。",
        ],
    },
    "F2-64": {
        "item_id": "F2-64-rows",
        "object_mode": "f2_64",
        "title": "F2-64 主要产品生产成本及单耗分析",
        "headers": ["数据区", "期间", "月份", "项目名称", "数值1", "数值2", "数值3", "数值4", "数值5", "数值6", "文本1", "文本2", "文本3", "备注"],
        "field_keys": ["section", "period", "month", "name", "v1", "v2", "v3", "v4", "v5", "v6", "text1", "text2", "text3", "remark"],
        "guidance": [
            "F2-64 主要产品生产成本及单耗分析 编制说明",
            "",
            "数据区填写：基本信息 / 成本构成 / 成本衔接 / 单位成本 / 同行比较 / 材料耗用；期间填写 current 或 prior，月份填写1~12。",
            "成本构成数值1~6：主要材料1/2/3、其他材料、直接人工、制造费用。",
            "成本衔接数值1~6：期初在产品、材料投入、人工投入、制造费用投入、期末在产品、产量。",
            "单位成本数值1~6：期初产成品、直接材料、直接人工、制造费用、期末产成品、产量。",
            "材料耗用数值1~5：产量、材料1投入量/金额、材料2投入量/金额；文本1/2为材料单位。",
            "金额小计、占比、单位成本、单位产量耗用均由系统自动计算。",
        ],
    },
    "F2-62": {
        "item_id": "F2-62-rows",
        "object_mode": "f2_62",
        "title": "F2-62 原材料单价分析",
        "headers": ["分析层次", "分析组", "比较项目", "月份/期间", "采购金额", "采购数量"],
        "field_keys": ["section", "groupName", "itemName", "period", "amount", "qty"],
        "guidance": [
            "F2-62 原材料单价分析 编制说明",
            "",
            "分析层次仅填写：同一供应商不同物料 / 同一原材料不同供应商 / 同类原材料不同规格。",
            "前两层期间填写1月~12月；第三层期间填写本期/上期/上上期。",
            "采购单价由系统按采购金额÷采购数量自动计算，不在导入表中手工填写。",
        ],
    },
    "F2-63": {
        "item_id": "F2-63-rows",
        "object_mode": "f2_63",
        "title": "F2-63 产量与产能/能耗分析",
        "headers": ["数据区", "名称", "存货名称", "数值1", "数值2", "数值3", "数值4", "数值5", "数值6", "备注"],
        "field_keys": ["section", "name", "subName", "v1", "v2", "v3", "v4", "v5", "v6", "remark"],
        "guidance": [
            "F2-63 存货产量与产能、能耗分析 编制说明",
            "",
            "数据区仅填写：产能比较 / 库存容量 / 能源采购 / 产品能耗。",
            "产能比较：名称=存货名称，数值1=本年产量，数值2=全年产能；产能利用率自动计算。",
            "库存容量：名称=仓库名称，存货名称=存货，数值1=实际库存量，数值2=库存容量，数值3/4=已有订单数量/金额，数值5/6=期后销售数量/金额。",
            "能源采购：名称=采购项目（水/电/燃气/蒸汽…），数值1/2=本期采购数量/金额，数值3/4=上期采购数量/金额；单价自动计算。",
            "产品能耗：名称=产品，数值1=本年产量，数值2/3/4=水/电/燃气耗用，数值5=上年单位能耗；单位能耗与变动率自动计算。",
        ],
    },
    "F2-65": {
        "item_id": "F2-65-rows",
        "object_mode": "f2_65",
        "title": "F2-65 关联方采购定价公允性核查（询价函）",
        "headers": [
            "关联方", "产品", "月份", "产品规格", "关联方采购价格",
            "询价单位1", "可比价格1", "询价单位2", "可比价格2",
            "询价单位3", "可比价格3", "询价单位4", "可比价格4",
            "合理性判断", "备注",
        ],
        "field_keys": [
            "relatedParty", "productName", "month", "productSpec", "relatedPrice",
            "supplier1", "price1", "supplier2", "price2",
            "supplier3", "price3", "supplier4", "price4", "judgment", "remark",
        ],
        "guidance": [
            "F2-65 关联方采购定价公允性核查（询价函）编制说明",
            "",
            "同一关联方+产品的12个月数据填写为一组；月份填写1~12。",
            "每组最多维护4家独立询价单位；可比均价与价差率由系统自动计算。",
            "价差率绝对值超过10%应在备注及审计说明中解释，并结合规格、采购量及交易条款评价公允性。",
        ],
    },
    "F2-66": {
        "item_id": "F2-66-rows",
        "object_mode": "f2_66",
        "title": "F2-66 关联方采购定价公允性核查（市场价）",
        "headers": [
            "关联方", "产品", "月份", "采购均价",
            "市场价月初均价", "市场价月末均价", "是否处于市场价区间", "备注",
        ],
        "field_keys": [
            "relatedParty", "productName", "month", "purchaseAvgPrice",
            "marketPriceStart", "marketPriceEnd", "judgment", "remark",
        ],
        "guidance": [
            "F2-66 关联方采购定价公允性核查（市场价）编制说明",
            "",
            "同一关联方+产品的12个月数据填写为一组；月份填写1~12。",
            "市场价区间及是否处于区间由系统按月初/月末均价自动判断，是否列可留空。",
            "采购均价落在区间外的月份应在备注中记录取价来源及差异原因。",
        ],
    },
    "F2-67": {
        "item_id": "F2-67-rows",
        "title": "F2-67 识别未披露的关联方",
        "headers": [
            "姓名", "个人供应商", "供应商法人", "合同签订人", "离职采购",
            "财务部门", "管理部门", "技术部门", "生产部门", "营销部门", "其他部门",
            "是否存在关系(Y/N)", "公司股东/高管/亲属/员工",
            "本年度采购额", "说明", "索引号",
        ],
        "field_keys": [
            "name", "personalSupplier", "supplierLegalPerson", "contractSignee",
            "formerPurchasingStaff", "financeDept", "managementDept", "technologyDept",
            "productionDept", "marketingDept", "otherDept", "isRelated", "identity",
            "annualPurchaseAmount", "note", "indexRef",
        ],
        "guidance": [
            "F2-67 识别未披露关联方编制说明",
            "",
            "每行填写一个需比对的自然人姓名，各身份/部门列填写该姓名出现次数。",
            "合计及Y/N建议由系统自动计算；同名不等于关联方，需进一步核对身份证、地址、任职及亲属关系。",
            "对确认或疑似关系填写身份、涉及采购额、说明及支持性证据索引。",
        ],
    },
    "F2-68": {
        "item_id": "F2-68-rows",
        "object_mode": "f2_68",
        "title": "F2-68 重要供应商结构分析",
        "headers": [
            "期间", "重要供应商名称", "采购金额", "主要采购产品", "采购数量", "采购单价",
            "信用期", "支付方式", "运输方式", "其他条款", "是否关联方",
            "采购额与供应商规模是否匹配", "采购产品与经营范围是否匹配", "备注", "索引号",
        ],
        "field_keys": [
            "period", "supplierName", "purchaseAmount", "relatedProduct", "purchaseQuantity",
            "unitPrice", "creditPeriod", "paymentMethod", "transportMethod", "otherTerms",
            "isRelatedParty", "scaleMatches", "scopeMatches", "remark", "indexRef",
        ],
        "guidance": [
            "F2-68 重要供应商结构分析编制说明",
            "",
            "期间填写“本年”或“上年”，每行填写一家重要供应商。",
            "占比、排名、前五/前十大集中度及同比变化由系统自动计算。",
            "重点说明新增或异常供应商、交易条件变化、规模/经营范围不匹配及关联方风险。",
        ],
    },
    "F2-69": {
        "item_id": "F2-69-rows",
        "title": "F2-69 供应商核查清单",
        "headers": [
            "供应商名称", "选取原因", "走访结论", "上次实访时间",
            "反向核查期末余额", "反向核查本期采购额",
            "函证期末余额", "函证本期采购额",
            "工商资料查询", "互联网信息查询", "访谈/电话访谈", "函证", "实地走访",
            "差异/未执行原因", "最终索引号",
        ],
        "field_keys": [
            "supplierName", "selectionReason", "visitConclusion", "lastVisitDate",
            "reverseEndingBalance", "reversePurchaseAmount",
            "confirmationEndingBalance", "confirmationPurchaseAmount",
            "registryChecked", "internetChecked", "interviewChecked",
            "confirmationChecked", "siteVisitChecked", "remark", "finalIndexRef",
        ],
        "guidance": [
            "F2-69 供应商核查清单编制说明",
            "",
            "核查方式列填写“是/否”或“√”；每家供应商应至少执行一种核查方式。",
            "反向核查与函证资料的期末余额、本期采购额差异超过1%时系统提示关注。",
            "存在差异、程序未执行或索引不完整时，应填写原因及替代程序。",
        ],
    },
    "F2-71": {
        "item_id": "F2-71-rows",
        "title": "F2-71 供应商访谈记录汇总表",
        "headers": [
            "内部ID", "供应商", "访谈时间", "访谈原因", "访谈方式",
            "被访谈公司注册地址", "实地走访公司地址",
            "接受访谈人员及身份", "参与访谈的审计人员", "参与访谈的其他人员", "访谈人员行程信息",
            "是否现场函证", "访谈关注要点", "合同执行核对情况",
            "交易金额核对是否一致", "往来金额核对是否一致",
            "访谈结论", "访谈记录索引",
        ],
        "field_keys": [
            "id", "supplierName", "interviewDate", "reason", "method",
            "registeredAddress", "visitAddress",
            "interviewee", "auditors", "otherParticipants", "tripInfo",
            "onSiteConfirmation", "focusPoints", "contractCheck",
            "transactionAmountMatch", "balanceMatch",
            "conclusion", "recordIndex",
        ],
        "guidance": [
            "F2-71 供应商访谈记录汇总表 编制说明",
            "",
            "每行对应一家受访供应商（页面按访谈项目×供应商转置显示）。",
            "访谈方式：实地走访/视频访谈/电话访谈/书面问询。",
            "是否现场函证/交易金额核对是否一致/往来金额核对是否一致 填写“是/否”。",
            "行程票据、现场照片等证据请在页面附件区上传；访谈记录索引联动 F2-72。",
            "内部ID 用于再次导入时保留实体标识，可留空由系统生成。",
        ],
    },
    "F2-70": {
        "item_id": "F2-70-entities",
        "title": "F2-70 供应商信息核查表",
        "headers": [
            "内部ID", "供应商", "统一社会信用代码", "注册地址", "办公地址",
            "网站地址", "网站IP地址", "企业邮箱", "成立时间", "注册资本/实缴资本",
            "经营范围", "人员规模/缴纳社保人数", "法定代表人",
            "股东1及持股比例", "股东2及持股比例", "股东3及持股比例", "股东4及持股比例", "股东5及持股比例",
            "董事长", "总经理", "其他关键管理人员", "关键经办人员",
            "实际控制人", "是否为关联方", "是否同时为客户", "经营状态", "是否列入失信名单",
            "信息来源", "备注/异常说明",
        ],
        "field_keys": [
            "id", "supplierName", "creditCode", "registeredAddress", "officeAddress",
            "websiteUrl", "websiteIp", "companyEmail", "establishDate", "registeredCapital",
            "businessScope", "staffScale", "legalRepresentative",
            "shareholder1", "shareholder2", "shareholder3", "shareholder4", "shareholder5",
            "chairman", "generalManager", "otherManagers", "keyHandlers",
            "actualController", "isRelatedParty", "isAlsoCustomer", "businessStatus", "isDishonest",
            "infoSource", "remark",
        ],
        "guidance": [
            "F2-70 供应商信息核查表 编制说明",
            "",
            "每行对应一家供应商档案（页面按核查项目×供应商转置显示）。",
            "是否为关联方/是否同时为客户/是否列入失信名单 填写“是/否”。",
            "股东及持股比例格式示例：张三 60%。",
            "内部ID 用于再次导入时保留实体标识，可留空由系统生成。",
        ],
    },
    "F2-72": {
        "item_id": "F2-72-entities",
        "entity_mode": True,
        "entity_kind": "interview",
        "title": "F2-72 供应商访谈记录",
        "headers": [
            "内部ID", "供应商", "访谈对象", "访谈日期", "访谈时间及地点", "参与人员",
            "问答摘要", "被访谈人员签字", "审计人员签字", "其他人员签字", "签字日期",
            "真实性声明已确认", "本份访谈结论", "备注",
        ],
        "field_keys": [
            "id", "supplierName", "interviewee", "interviewDate", "interviewTimePlace", "participants",
            "qaSummary", "intervieweeSign", "auditorSign", "otherSign", "signDate",
            "declarationAck", "conclusion", "remark",
        ],
        "guidance": [
            "F2-72 供应商访谈记录 编制说明",
            "",
            "每行对应一份正式访谈问卷（页面按十一项提纲填写）。",
            "问答摘要格式：Q:问题 A:回答，多组换行；导入后按题序回填到问卷。",
            "真实性声明已确认 填写“是/否”或 true/false。",
            "工商资料、函证回函、银行流水等请在页面附件区上传。",
            "内部ID 用于再次导入时保留实体标识，可留空由系统生成。",
        ],
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


async def _load_json_object(db: AsyncSession, wp_id: str, item_id: str) -> dict:
    """加载对象存储（如 F2-61 {materials: []}），兼容旧扁平数组格式."""
    import json as _json

    import sqlalchemy as sa

    result = await db.execute(
        sa.text(
            f"SELECT {_STORAGE_FIELD} FROM checklist_responses"
            " WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"
        ),
        {"wp_id": wp_id, "iid": item_id},
    )
    row = result.fetchone()
    raw = getattr(row, _STORAGE_FIELD, None) if row else None
    if not raw:
        return {}
    try:
        parsed = _json.loads(raw)
    except (_json.JSONDecodeError, TypeError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):  # 旧扁平数组：包一层视为 materials
        return {"materials": parsed}
    return {}


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
            # 新模型 qaItems；兼容旧 qaPairs
            for qa in (e.get("qaItems") or e.get("qaPairs") or []):
                q = (qa.get("prompt") or qa.get("question") or "").strip()
                a = (qa.get("answer") or "").strip()
                if q or a:
                    qa_lines.append(f"Q:{q} A:{a}")
            flat = {k: e.get(k, "") for k in keys if k != "qaSummary"}
            if "declarationAck" in keys:
                flat["declarationAck"] = "是" if e.get("declarationAck") else "否"
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
        for idx, r in enumerate(rows):
            eid = r.get("id") or f"imp-{uuid.uuid4().hex[:12]}"
            qa_items: list[dict] = []
            summary = str(r.get("qaSummary") or "").strip()
            if summary:
                for i, line in enumerate(summary.splitlines()):
                    line = line.strip()
                    if not line:
                        continue
                    q, _, a = line.partition(" A:")
                    q = q.removeprefix("Q:").strip()
                    qa_items.append({
                        "key": f"q{i + 1}" if i < 11 else f"custom-{i + 1}",
                        "prompt": q,
                        "answer": a.strip(),
                    })
            ack_raw = str(r.get("declarationAck") or "").strip().lower()
            entities.append({
                "id": eid,
                "attSlot": idx + 1,
                "supplierName": r.get("supplierName") or "",
                "interviewee": r.get("interviewee") or "",
                "interviewDate": r.get("interviewDate") or "",
                "interviewTimePlace": r.get("interviewTimePlace") or "",
                "participants": r.get("participants") or "",
                "location": "",
                "qaItems": qa_items,
                "qaPairs": [
                    {"id": f"qa-{uuid.uuid4().hex[:8]}", "question": x["prompt"], "answer": x["answer"]}
                    for x in qa_items
                ] or [{"id": f"qa-{uuid.uuid4().hex[:8]}", "question": "", "answer": ""}],
                "intervieweeSign": r.get("intervieweeSign") or "",
                "auditorSign": r.get("auditorSign") or "",
                "otherSign": r.get("otherSign") or "",
                "signDate": r.get("signDate") or "",
                "declarationAck": ack_raw in ("是", "true", "1", "yes", "y"),
                "conclusion": r.get("conclusion") or r.get("auditFocus") or "",
                "remark": r.get("remark") or r.get("topic") or "",
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
    if sp.get("object_mode") == "f2_62":
        raw_obj = await _load_json_object(db, wp_id, sp["item_id"])
        rows = _f2_62_to_flat(raw_obj)
    elif sp.get("object_mode") == "f2_63":
        raw_obj = await _load_json_object(db, wp_id, sp["item_id"])
        rows = _f2_63_to_flat(raw_obj)
    elif sp.get("object_mode") == "f2_64":
        raw_obj = await _load_json_object(db, wp_id, sp["item_id"])
        rows = _f2_64_to_flat(raw_obj)
    elif sp.get("object_mode") == "f2_65":
        raw_obj = await _load_json_object(db, wp_id, sp["item_id"])
        rows = _f2_65_to_flat(raw_obj)
    elif sp.get("object_mode") == "f2_66":
        raw_obj = await _load_json_object(db, wp_id, sp["item_id"])
        rows = _f2_66_to_flat(raw_obj)
    elif sp.get("object_mode") == "f2_68":
        raw_obj = await _load_json_object(db, wp_id, sp["item_id"])
        rows = _f2_68_to_flat(raw_obj)
    elif sp.get("object_key"):
        raw_obj = await _load_json_object(db, wp_id, sp["item_id"])
        rows = _f2_61_materials_to_flat(raw_obj.get(sp["object_key"]) or [])
    else:
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
    if sp.get("object_mode") == "f2_62":
        payload = _f2_62_flat_to_object(rows)
        count = len(rows)
    elif sp.get("object_mode") == "f2_63":
        payload = _f2_63_flat_to_object(rows)
        count = len(rows)
    elif sp.get("object_mode") == "f2_64":
        payload = _f2_64_flat_to_object(rows)
        count = len(rows)
    elif sp.get("object_mode") == "f2_65":
        payload = _f2_65_flat_to_object(rows)
        count = len(rows)
    elif sp.get("object_mode") == "f2_66":
        payload = _f2_66_flat_to_object(rows)
        count = len(rows)
    elif sp.get("object_mode") == "f2_68":
        payload = _f2_68_flat_to_object(rows)
        count = len(rows)
    elif sp.get("object_key"):
        payload: Any = {sp["object_key"]: _f2_61_flat_to_materials(rows)}
        count = len(payload[sp["object_key"]])
    elif sp.get("entity_mode"):
        payload = _flat_to_entities(sheet, rows)
        count = len(payload)
    else:
        payload = _normalize(rows)
        count = len(payload)
    await upsert_json_rows(db, wp_id, sp["item_id"], payload, field=_STORAGE_FIELD)
    out: dict[str, Any] = {"ok": True, "imported_count": count, "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
