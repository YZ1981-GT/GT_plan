# -*- coding: utf-8 -*-
"""D4-30/31/32 IPO访谈与资金流水的结构化投影 provider。

三张表共享 D4 revenue entry；这里只负责 store projection/merge 与受管 sheet 声明。
动态客户、问卷字段和未知分组均通过稳定 key 保留，禁止按数组下标定位。
"""
from __future__ import annotations

import json
from typing import Any, Final, Mapping

from app.services.workpaper_sync.json_path import (
    JsonPathMissingSegmentError,
    resolve_json_path,
    set_json_path,
)

TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"

_SHEETS: dict[str, dict[str, Any]] = {
    "D4-30": {
        "managed_sheet": "客户访谈记录汇总表D4-30", "template_id": "D430",
        "sheet_key": "d4-30-managed", "store_item_id": "D4-30-customers",
        "table_key": "d4_30_customers", "identity_key": "id", "first_data_row": 6,
        "last_data_row": 21, "footer_row": 22, "managed_last_col": "W", "uuid_col": "X",
        "fields": (
            ("name", "B", "editable", "text", "name", "客户名称"),
            ("time", "C", "editable", "text", "fields/time", "访谈时间"),
            ("reason", "D", "editable", "text", "fields/reason", "访谈原因"),
            ("method", "E", "editable", "text", "fields/method", "访谈方式"),
            ("reg_address", "F", "editable", "text", "fields/regAddress", "被访谈公司注册地址"),
            ("visit_address", "G", "editable", "text", "fields/visitAddress", "实地走访公司地址"),
            ("interviewee", "H", "editable", "text", "fields/interviewee", "接受访谈人员及身份"),
            ("auditor", "I", "editable", "text", "fields/auditor", "参与访谈的审计人员"),
            ("others", "J", "editable", "text", "fields/others", "参与访谈的其他人员"),
            ("travel_info", "K", "editable", "text", "fields/travelInfo", "访谈人员行程信息"),
            ("on_site_confirm", "L", "editable", "text", "fields/onSiteConfirm", "是否现场函证"),
            ("key_points", "M", "editable", "text", "fields/keyPoints", "访谈关注要点"),
            ("contract_check", "N", "editable", "text", "fields/contractCheck", "合同执行核对情况"),
            ("amount_match", "O", "editable", "text", "fields/amountMatch", "交易金额核对是否一致"),
            ("balance_match", "P", "editable", "text", "fields/balanceMatch", "往来余额核对是否一致"),
            ("conclusion", "Q", "editable", "text", "fields/conclusion", "访谈结论"),
            ("index_ref", "R", "editable", "text", "fields/indexRef", "访谈表索引"),
            ("custom_dimensions", "S", "editable", "json", "customDimensions", "自定义检查项"),
        ),
        # Marker must exist in frozen template col A (A22); template lacks「三、审计说明：」.
        "footer_marker": "访谈表索引", "formula_mask": (),
    },
    "D4-31": {
        "managed_sheet": "客户访谈记录 D4-31", "template_id": "D431",
        "sheet_key": "d4-31-managed", "store_item_id": "D4-31-interview",
        "table_key": "d4_31_interview", "identity_key": "singleton", "first_data_row": 5,
        "last_data_row": 5, "footer_row": 63, "managed_last_col": "J", "uuid_col": "K",
        "fields": tuple((k, col, "editable", "json" if k == "q1_relation" else "text", k, label) for k, col, label in (
            ("target", "A", "访谈对象"), ("timePlace", "B", "访谈时间及地点"), ("interviewee", "C", "接受访谈人员及职务"),
            ("interviewer", "D", "访谈人"), ("introduction", "E", "接受访谈人介绍"), ("companyName", "F", "公司名称"),
            ("regCapital", "G", "注册资本"), ("establishDate", "H", "成立日期"), ("bizNature", "I", "经济性质"),
            ("legalRep", "J", "法定代表人"), ("equityStructure", "A", "股权结构"), ("q1_relation", "B", "业务关系"),
            ("q2a_payment", "C", "采购结算"), ("q2b_collection", "D", "销售结算"), ("q3a_hasContract", "E", "是否有合同"),
            ("q3b_quality", "F", "产品质量"), ("q3c_returnClause", "G", "退货条款"), ("q3d_returnAmount", "H", "退货金额"),
            ("q3e_acceptance", "I", "验收方式"), ("q3f_hasRebate", "J", "是否返利"), ("q3f_rebateMethod", "A", "返利方式"),
            ("q3f_rebateAmount", "B", "返利金额"), ("q3g_finalSold", "C", "是否终端销售"), ("q4_otherFunds", "D", "其他资金往来"),
            ("q5_otherMatters", "E", "其他事项"), ("q6_hasShares", "F", "持有股份"), ("q6_hasPosition", "G", "担任职务"),
            ("q6_hasTransaction", "H", "关联交易"), ("signInterviewee", "I", "受访人签字"), ("signAuditor", "J", "审计人员签字"),
            ("signOther", "A", "其他签字"), ("signDate", "B", "签字日期"),
        )),
        # Marker must match frozen template A63 text (sheet lacks「五、访谈人员承诺」).
        "footer_marker": "2.针对识别出的第三方配合实施财务舞弊的风险，可以考虑采用跟函方式进行函证，观察函证处理过程，评估回函可靠性。", "formula_mask": (),
    },
    "D4-32": {
        "managed_sheet": "客户、供应商等资金流水检查D4-32", "template_id": "D432",
        "sheet_key": "d4-32-managed", "store_item_id": "D4-32-groups", "table_key": "d4_32_groups",
        "identity_key": "id", "first_data_row": 13, "last_data_row": 46, "footer_row": 48,
        # Frozen template A48 is「三、审计说明」without full-width colon.
        "managed_last_col": "I", "uuid_col": "J", "footer_marker": "三、审计说明", "formula_mask": (),
        "fields": (
            ("group_label", "A", "editable", "text", "groupLabel", "分组"),
            ("name", "B", "editable", "text", "name", "单位名称/姓名"),
            ("amount", "C", "editable", "amount", "amount", "本期交易金额"),
            ("ratio", "D", "editable", "text", "ratio", "占同类交易比例"),
            ("bank", "E", "editable", "text", "bank", "开户银行"),
            ("account", "F", "editable", "text", "account", "账号"),
            ("method", "G", "editable", "text", "method", "资金流水获取途径"),
            ("hasAnomaly", "H", "editable", "text", "hasAnomaly", "是否发现异常交易"),
            ("indexRef", "I", "editable", "text", "indexRef", "索引号"),
        ),
    },
}


def _s(code: str) -> dict[str, Any]: return _SHEETS[code]
def stable_key_for(code: str, field: str, identity: str = "{row_uuid}") -> str:
    import re
    field = re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)
    return f"{_s(code)['table_key']}/{identity}/{field}"
def store_item_id(code: str) -> str: return _s(code)["store_item_id"]
def sheet_key(code: str) -> str: return _s(code)["sheet_key"]
def codes() -> tuple[str, ...]: return tuple(_SHEETS)


def instrumentation_spec(code: str, *, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec
    s = _s(code)
    return ExcelInstrumentationSpec(entry_id=entry_id, template_id=s["template_id"], template_relative_path=template_relative_path,
        managed_sheet=s["managed_sheet"], first_data_row=s["first_data_row"], last_data_row=s["last_data_row"],
        footer_row=s["footer_row"], managed_last_col=s["managed_last_col"], uuid_col=s["uuid_col"],
        table_name=f"GT_{s['template_id']}_ROWS", sheet_key=s["sheet_key"])


def sheet_payload(code: str) -> dict[str, Any]:
    s = _s(code)
    fields = [{"stable_field_key": stable_key_for(code, f[0]), "json_pointer": f"/rows/{{row_uuid}}/{f[4]}",
               "column_key": __import__('re').sub(r'([A-Z])', lambda m: '_' + m.group(1).lower(), f[0]), "cell": {"column": f[1], "row_from": "row_identity"}, "mode": f[2],
               "value_type": f[3], "source_ref": f"源xlsx!{s['managed_sheet']}!{f[1]}{s['first_data_row']}",
               "header_source_ref": f"源xlsx!{s['managed_sheet']}!{f[1]}11", "store_item_id": s['store_item_id'], "header_text": f[5]} for f in s["fields"]]
    return {"sheet_key": s["sheet_key"], "excel_name": s["managed_sheet"], "template_id": s["template_id"],
            "locator": {"anchor": "excel_table_sheet_association"}, "tables": [{"table_key": s["table_key"], "anchor": f"A{s['first_data_row']-1}", "header_rows": 1,
            "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{s['identity_key']}"}, "delete_policy": "tombstone",
            "footer_anchor": {"marker": s["footer_marker"], "search_column": "A", "carries_total_formula": False},
            "formula_mask": list(s["formula_mask"]), "fields": fields}]}


def _decode(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray)): payload = payload.decode("utf-8")
    if isinstance(payload, str): return json.loads(payload)
    return payload


def _rows(code: str, payload: Any) -> list[tuple[str, Mapping[str, Any]]]:
    s = _s(code); value = _decode(payload)
    if code == "D4-31":
        if not isinstance(value, Mapping): raise ValueError("D4-31 必须是单对象问卷")
        # 空问卷不注入 singleton：否则 overlay 会丢掉 None 占位，materialize 却写入
        # orphan identity，extract 读到模板残值 → RoundtripEquivalenceError extras。
        if not value:
            return []
        return [("singleton", value)]
    if code == "D4-30": value = value.get("customers", []) if isinstance(value, Mapping) else value
    if not isinstance(value, list): raise ValueError(f"{code} 必须是数组")
    out = []
    for row in value:
        if not isinstance(row, Mapping) or not str(row.get(s["identity_key"]) or "").strip(): raise ValueError(f"{code} 缺稳定身份")
        out.append((str(row[s["identity_key"]]).strip(), row))
    return out


def build_store_projection(code: str, payload: Any, *, contract: Any, limits: Any | None = None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.contracts import FieldMode, ValueType
    values: dict[str, FieldValue] = {}; row_keys: list[str] = []
    s = _s(code)
    for identity, row in _rows(code, payload):
        row_keys.append(identity)
        for field, _col, mode, value_type, path, _label in s["fields"]:
            # 🔴 嵌套 scalar 字段（D4-30 `fields/时间/原因/方式…` 等访谈内容）缺失段 → None：
            #    一条访谈客户行可能只填了 id/name、尚未填 `fields` 子对象（合法半成品）。
            #    resolve_json_path fail-closed 抛 JsonPathMissingSegmentError 会把整个 entry 的
            #    combined store-projection 打成 422（真栈实测 D4-30 只有 {id,name} 时复现），
            #    连累 D4-2..36 全部无法进在线编辑。与主 provider `_resolve_store_path` 同一
            #    「标量缺失段 → None、数组路径 fail closed」口径：这里 fields/* 是嵌套 scalar，
            #    缺失投空（未填），不软化任何数组路径（interview 无数组字段）。
            # 🔴 嵌套 scalar 字段（D4-30 `fields/时间/原因/方式…` 等访谈内容）缺失段 → None：
            #    一条访谈客户行可能只填了 id/name、尚未填 `fields` 子对象（合法半成品）。
            #    resolve_json_path fail-closed 抛 JsonPathMissingSegmentError 会把整个 entry 的
            #    combined store-projection 打成 422（真栈实测 D4-30 只有 {id,name} 时复现），
            #    连累 D4-2..36 全部无法进在线编辑。与主 provider `_resolve_store_path` 同一
            #    「标量缺失段 → None、数组路径 fail closed」口径：这里 fields/* 是嵌套 scalar，
            #    缺失投空（未填），不软化任何数组路径（interview 无数组字段）。
            if "/" in path:
                try:
                    value = resolve_json_path(row, path)
                except JsonPathMissingSegmentError:
                    value = None
            else:
                value = row.get(path)
            if code == "D4-31" and field == "q1_relation": value = json.dumps(value if isinstance(value, list) else [], ensure_ascii=False)
            if field == "custom_dimensions" and value is None: value = {}
            sk = stable_key_for(code, field, identity)
            # 🔴 2026-09-21 修复既有 bug：`value_type`/`mode` 此前是字段元组里的**裸
            # 字符串**（"text"/"json"/"editable"），FieldValue 从未把它们转换成
            # ValueType/FieldMode 枚举。多数校验路径用 `==` 比较（str 混入枚举与裸
            # 字符串相等）掩盖了这个问题，但 `content_mutation._assert_roundtrip_
            # equivalent`（`is` 恒等分派）与 `_projection_payload`（`.mode.value`
            # 属性访问）会直接炸——这次 D4-13 rematerialize（全 entry 范围）首次真正
            # 跑通这两条路径时暴露。修复：统一转换成真枚举实例，其余逻辑不变。
            values[sk] = FieldValue(stable_key=sk, value=value, value_type=ValueType(value_type), mode=FieldMode(mode), row_key=identity)
    return Projection(contract_id=contract.contract_id, semantic_version=contract.semantic_version, document_type=contract.document_type, values=values, row_keys={s["table_key"]: tuple(row_keys)})


def merge_projection_into_store(code: str, *, projection: Any, base_payload: Any) -> Any:
    code_s = _s(code); base = _decode(base_payload)
    if code == "D4-31": rows = [("singleton", dict(base) if isinstance(base, Mapping) else {})]
    else:
        container = base if isinstance(base, list) else []
        if code == "D4-30" and isinstance(base, Mapping): container = base.get("customers", [])
        rows = [(str(r.get(code_s["identity_key"])), dict(r)) for r in container if isinstance(r, Mapping) and r.get(code_s["identity_key"])]
    by_id = {i: r for i, r in rows}; order = [i for i, _ in rows]; prefix = code_s["table_key"] + "/"
    for sk in projection.stable_keys():
        if not str(sk).startswith(prefix): continue
        fv = projection.get(sk); identity = getattr(fv, "row_key", None)
        if not identity: continue
        identity = str(identity); target = by_id.setdefault(identity, {code_s["identity_key"]: identity});
        if identity not in order: order.append(identity)
        field = str(sk).rsplit("/", 1)[-1]; spec = next((f for f in code_s["fields"] if f[0] == field), None)
        if spec is None: continue
        value = getattr(fv, "value", None)
        if code == "D4-31" and field == "q1_relation":
            try: value = json.loads(value) if isinstance(value, str) else value
            except (TypeError, ValueError): value = []
        if field == "custom_dimensions" and value is None: value = {}
        path = spec[4]
        if "/" in path: set_json_path(target, path, value)
        else: target[path] = value
    result = [by_id[i] for i in order]
    if code == "D4-31": return result[0] if result else {}
    if code == "D4-30": return {"customers": result, "customDimensions": (base.get("customDimensions", []) if isinstance(base, Mapping) else [])}
    return result


def mapping_digest_payload(code: str) -> dict[str, Any]:
    s = _s(code); return {"managed_sheet": s["managed_sheet"], "template_relative_path": TEMPLATE_RELATIVE_PATH, "fields": s["fields"], "first_data_row": s["first_data_row"], "last_data_row": s["last_data_row"]}
