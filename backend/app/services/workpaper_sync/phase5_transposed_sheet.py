"""通用转置表引擎 —— 把 D4-29「逻辑行渲染成携带身份的 Excel 列」范式参数化。

spec: d4-12-transposed-writeback / Requirement 1（GENERALIZE 不回归 D4-29）

## 为什么存在

`phase5_d4_29_customer_detail.py` 原本把几何/身份常量与算法糅在一起、绑死单张
D4-29。D4-12「合同检查表」是同范式转置表（一列=一份合同，一行=一个字段），但首列、
字段数、store 形态都不同。本模块把算法抽成读 :class:`TransposedSheetSpec` 的通用
函数；D4-29 与 D4-12 各实例化一份 spec，`phase5_d4_29_customer_detail` 退化为薄壳。

## 关键泛化点（D4-12 逼出的两处参数化）

* ``header_field_key``：header_row 是否承载一个受管字段。D4-29 = ``"name"``（客户名称
  写在 R10）；D4-12 = ``None``（R10 是模板预画的索引号 ``D4-12-N``，非业务字段）。
* ``nested_fields_key``：store item 的字段是嵌套在某子对象里，还是平铺在顶层。
  D4-29 = ``"fields"``（``{id, name, fields:{...}}``）；D4-12 = ``None``（``{id, ...21 平铺字段}``）。

## 零回归纪律

SPEC_D429 经本引擎产出的 ``sheet_payload`` / materialize 字节 / extract 字段必须与
泛化前逐字/逐字节相同 —— 由 `test_d4_29_customer_detail_sync.py` + Task 5 零回归门
钉死。因此本引擎对「header_field_key 非空 + nested_fields_key 非空」路径的行为，
必须严格复刻原 D4-29 实现。
"""
from __future__ import annotations

import copy
import io
import json
import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Mapping, Sequence

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.styles import Protection

from app.services.workpaper_sync.adapters.base import FieldValue, Projection


@dataclass(frozen=True)
class TransposedSheetSpec:
    """一张转置表的全部几何 + 身份 + store 形态参数。

    D4-29 与 D4-12 各实例化一份；通用引擎的所有行为都由这些字段驱动，无隐藏常量。
    """

    managed_sheet: str
    sheet_key: str
    table_key: str
    template_id: str
    store_item_id: str
    identity_key: str
    #: 表头行（承载列身份标签 / 可选受管字段）。
    header_row: int
    #: 有序字段 key → 物理行号（转置表每字段一行）。
    field_rows: Mapping[str, int]
    #: footer 静态区起讫行（受管区之外，materialize 不动、extract 不读）。
    footer_rows: tuple[int, int]
    #: 静态提示区首行（footer 下方 HTML-only 文本）。
    static_prompt_first_row: int
    #: 首个实体列（一列=一个逻辑行）。D4-29=C，D4-12=B。
    first_entity_column: str
    #: 模板预画的末实体列（超出即样式克隆扩列）。
    initial_entity_column: str
    #: 隐藏身份载体行（逐实体列写 ``{prefix}{id}``）。
    identity_carrier_row: int
    identity_carrier_prefix: str
    #: workbook-scope RANGE definedName 名与几何。
    defined_name: str
    managed_ref: str
    #: header_row 承载的受管字段 key；None 表示 header 只是标签（D4-12）。
    header_field_key: str | None = None
    #: store item 字段嵌套子对象名；None 表示字段平铺在顶层（D4-12）。
    nested_fields_key: str | None = None
    #: 数值语义字段 key（小写化后比对）；用于 sheet_payload 的 value_type=number。
    numeric_fields: tuple[str, ...] = ()
    #: json_pointer 根容器名（store payload 的逻辑容器名）。D4-29=customers。
    pointer_root: str = "rows"
    #: 错误消息前缀标签（零回归：D4-29 保持 "D4-29"）。
    error_label: str = ""
    #: 实体名词单/复数（错误消息用；零回归：D4-29=customer/customers）。
    entity_noun: str = "row"
    entity_noun_plural: str = "rows"

    # ── 派生 helper ────────────────────────────────────────────────
    @property
    def field_keys(self) -> tuple[str, ...]:
        return tuple(self.field_rows)

    @property
    def managed_field_keys(self) -> tuple[str, ...]:
        """受管字段迭代顺序：header_field_key（若有）在前，其余按 field_rows。"""
        if self.header_field_key is not None:
            return (self.header_field_key, *self.field_keys)
        return self.field_keys

    def row_of(self, key: str) -> int:
        if self.header_field_key is not None and key == self.header_field_key:
            return self.header_row
        return self.field_rows[key]

    @property
    def last_field_row(self) -> int:
        return max(self.field_rows.values())


# ═══════════════════════════════════════════════════════════════════════
# 身份与 payload 归一
# ═══════════════════════════════════════════════════════════════════════


def _label(spec: TransposedSheetSpec) -> str:
    """错误消息前缀（零回归：D4-29 用 'D4-29'；缺省回退 sheet_key）。"""
    return spec.error_label or spec.sheet_key


def normalize_payload(payload, *, spec: TransposedSheetSpec) -> list[dict]:
    """把 store payload 归一成 ``[{id, <字段>}]`` 内部表示（保留未受管元字段）。

    * 嵌套形态（D4-29）：``{id, name, fields:{...}}`` → 保持 ``{id, name, fields}``。
    * 扁平形态（D4-12）：``{id, ...平铺字段}`` → 原样保留全部顶层 key（含 indexNo/label
      等未受管元字段）。
    """
    if payload is None:
        return []
    if isinstance(payload, (str, bytes, bytearray)):
        payload = json.loads(payload or "[]")
    if isinstance(payload, Mapping):
        # 兼容 D4-29 历史 {"customers": [...]} 顶层包裹。
        payload = payload.get(spec.table_key, payload.get("customers", []))
    label, noun, nouns = _label(spec), spec.entity_noun, spec.entity_noun_plural
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes, bytearray)):
        raise ValueError(f"{label} {nouns} must be a JSON array")
    out, seen = [], set()
    for raw in payload:
        if not isinstance(raw, Mapping):
            raise ValueError(f"{label} {noun} must be an object")
        ident = str(raw.get(spec.identity_key, "")).strip()
        if not ident or ident in seen or any(c in ident for c in "/~{}"):
            raise ValueError(f"{label} {noun}.{spec.identity_key} must be unique and safe")
        if spec.nested_fields_key is not None:
            fields = raw.get(spec.nested_fields_key, {})
            if not isinstance(fields, Mapping):
                raise ValueError(f"{label} {noun}.{spec.nested_fields_key} must be an object")
            row: dict[str, Any] = {spec.identity_key: ident}
            if spec.header_field_key is not None:
                row[spec.header_field_key] = str(raw.get(spec.header_field_key, "") or "")
            row[spec.nested_fields_key] = dict(fields)
            out.append(row)
        else:
            # 扁平：原样保留全部顶层键（未受管元字段随之携带回写）。
            # 🔴 受管字段 vs 元字段的 merge 冲突约定（复盘 #3 明确）：merge_projection_into_store
            # 以 base_payload 打底、只用 projection 覆盖 spec.managed_field_keys 里的受管字段；
            # 未受管元字段（D4-12 的 indexNo/label/attachmentId/ocrStatus 等）**以 base 为准**。
            # 因 base 由前端最新 store（flushHtml 先 flushPendingSave 落库）提供，故元字段冲突
            # 以 HTML 侧为准——OO 侧不承载这些元字段（转置受管区只含 21 业务字段），不会覆盖它们。
            row = dict(raw)
            row[spec.identity_key] = ident
            out.append(row)
        seen.add(ident)
    return out


def _get_field(row: Mapping, key: str, *, spec: TransposedSheetSpec):
    """从归一 row 读一个受管字段值。"""
    if spec.header_field_key is not None and key == spec.header_field_key:
        return row.get(key, "")
    if spec.nested_fields_key is not None:
        return row.get(spec.nested_fields_key, {}).get(key, "")
    return row.get(key, "")


def _set_field(row: dict, key: str, value, *, spec: TransposedSheetSpec) -> None:
    """把一个受管字段值写回归一 row。"""
    if spec.header_field_key is not None and key == spec.header_field_key:
        row[key] = value
        return
    if spec.nested_fields_key is not None:
        row.setdefault(spec.nested_fields_key, {})[key] = value
        return
    row[key] = value


def _new_row(ident: str, *, spec: TransposedSheetSpec) -> dict:
    row: dict[str, Any] = {spec.identity_key: ident}
    if spec.header_field_key is not None:
        row[spec.header_field_key] = ""
    if spec.nested_fields_key is not None:
        row[spec.nested_fields_key] = {}
    return row


def stable_key_for(row_id, field_key, *, spec: TransposedSheetSpec) -> str:
    return f"{spec.table_key}/{row_id}/{field_key.lower()}"


# ═══════════════════════════════════════════════════════════════════════
# store projection / merge
# ═══════════════════════════════════════════════════════════════════════


def build_store_projection(payload, *, contract, spec: TransposedSheetSpec, limits=None) -> Projection:
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    budget = StreamingProjectionBudget(limits or load_limits())
    values = {}
    rows = normalize_payload(payload, spec=spec)
    for row in rows:
        budget.add_row(spec.table_key)
        for key in spec.managed_field_keys:
            field_spec = contract.field_by_stable_key(stable_key_for("{row_uuid}", key, spec=spec))
            stable = stable_key_for(row[spec.identity_key], key, spec=spec)
            budget.add_field()
            values[stable] = FieldValue(
                stable,
                _get_field(row, key, spec=spec),
                field_spec.value_type,
                field_spec.mode,
                row_key=row[spec.identity_key],
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={spec.table_key: tuple(r[spec.identity_key] for r in rows)},
    )


def merge_projection_into_store(*, projection, base_payload, spec: TransposedSheetSpec):
    rows = normalize_payload(base_payload, spec=spec)
    by = {r[spec.identity_key]: r for r in rows}
    original = set(by)
    order = list(by)
    applied = visited = 0
    keys = {k.lower(): k for k in spec.managed_field_keys}
    prefix = spec.table_key + "/"
    for stable in projection.stable_keys():
        if not str(stable).startswith(prefix):
            continue
        _, ident, key = str(stable).split("/", 2)
        field = projection.get(stable)
        if field is None or field.is_protected or key not in keys:
            continue
        key = keys[key]
        if ident not in by:
            by[ident] = _new_row(ident, spec=spec)
            order.append(ident)
            applied += 1
        value = "" if field.value is None else field.value
        visited += 1
        if _get_field(by[ident], key, spec=spec) != value:
            _set_field(by[ident], key, value, spec=spec)
            applied += 1
    ids = list(projection.row_keys[spec.table_key]) if spec.table_key in projection.row_keys else order
    if len(ids) != len(set(ids)) or any(i not in by for i in ids):
        missing = [i for i in ids if i not in by]
        raise ValueError(
            f"{_label(spec)} invalid projection {spec.entity_noun} identities: missing={missing[:10]} "
            f"row_keys={len(ids)} base={len(by)}"
        )
    removed = original - set(ids)
    applied += len(removed) + int(ids != order and not removed)
    return [by[i] for i in ids], applied, visited, removed


# ═══════════════════════════════════════════════════════════════════════
# 契约 sheet_payload / mapping_digest
# ═══════════════════════════════════════════════════════════════════════


def _src(cell, *, spec: TransposedSheetSpec) -> str:
    return f"源xlsx!{spec.managed_sheet}!{cell}"


def _parse_field_pointer(key: str, *, spec: TransposedSheetSpec, row_uuid: str) -> str:
    root = spec.pointer_root
    if spec.nested_fields_key is not None:
        if spec.header_field_key is not None and key == spec.header_field_key:
            return f"/{root}/{row_uuid}/{key}"
        return f"/{root}/{row_uuid}/{spec.nested_fields_key}/{key}"
    return f"/{root}/{row_uuid}/{key}"


def sheet_payload(*, spec: TransposedSheetSpec) -> dict:
    first = spec.first_entity_column
    last = spec.initial_entity_column
    fields = []
    for key in spec.managed_field_keys:
        row = spec.row_of(key)
        fields.append({
            "stable_field_key": stable_key_for("{row_uuid}", key, spec=spec),
            "json_pointer": _parse_field_pointer(key, spec=spec, row_uuid="{row_uuid}"),
            "source_ref": _src(f"{first}{row}:{last}{row}", spec=spec),
            "header_source_ref": _src(f"A{row}:B{row}", spec=spec) if spec.nested_fields_key is not None
                                 else _src(f"A{row}", spec=spec),
            "cell": {"column": first, "row_from": "row_identity"},
            "transposed_row": row, "mode": "editable", "value_type": _value_type_of(key, spec=spec),
            "instances": "many",
        })
    label_columns = "A:B" if spec.nested_fields_key is not None else "A"
    return {
        "sheet_key": spec.sheet_key, "template_id": spec.template_id, "excel_name": spec.managed_sheet,
        "locator": {"anchor": "defined_name_ref", "defined_name": spec.defined_name},
        "region_boundary_locator": {"anchor": "defined_name_ref", "defined_name": spec.defined_name,
                                    "range": spec.managed_ref},
        "tables": [{
            "table_key": spec.table_key, "anchor": f"{first}{spec.header_row}", "header_rows": 1,
            "layout": "customer_columns",
            "row_identity": {"kind": "field", "json_pointer": f"/{spec.pointer_root}/*/{spec.identity_key}"},
            "delete_policy": "tombstone",
            "transposed_columns": {"source_ref": _src(f"{first}{spec.header_row}:{last}{spec.header_row}", spec=spec),
                                   "identity_row": spec.identity_carrier_row,
                                   "identity_prefix": spec.identity_carrier_prefix, "identity": spec.identity_key},
            "protected_regions": {"label_columns": label_columns, "footer_rows": list(spec.footer_rows),
                                  "static_prompt": f"A{spec.static_prompt_first_row}:XFD1048576"},
            "fields": fields}]}


def _value_type_of(key: str, *, spec: TransposedSheetSpec) -> str:
    """字段值类型。默认 text；spec.numeric_fields 声明的字段为 amount（金额语义）。

    注意 ValueType 枚举无 'number'，金额字段用 'amount'（见 contracts.ValueType）。
    """
    if key.lower() in spec.numeric_fields:
        return "amount"
    return "text"


# ═══════════════════════════════════════════════════════════════════════
# resolve_managed_sheet — definedName 强校验
# ═══════════════════════════════════════════════════════════════════════


def resolve_managed_sheet(workbook_bytes, *, spec: TransposedSheetSpec):
    """校验 raw name list（在 openpyxl 折叠重复名之前），返回 (wb, ws)。"""
    import zipfile
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as archive:
        root = ET.fromstring(archive.read("xl/workbook.xml"))
    label = _label(spec)
    names = [n for n in root.findall("{*}definedNames/{*}definedName")
             if n.get("name", "").lower() == spec.defined_name.lower()]
    if len(names) != 1 or "localSheetId" in names[0].attrib:
        raise ValueError(f"{label} requires one workbook-scope definedName")
    from openpyxl.workbook.defined_name import DefinedName
    name = DefinedName(spec.defined_name, attr_text=names[0].text)
    if name.type != "RANGE":
        raise ValueError(f"{label} invalid managed region anchor")
    destinations = list(name.destinations)
    if len(destinations) != 1 or destinations[0][1] != spec.managed_ref:
        raise ValueError(f"{label} managed region geometry drift")
    wb = load_workbook(io.BytesIO(workbook_bytes), data_only=False)
    title = destinations[0][0].replace("''", "'")
    if title not in wb.sheetnames:
        raise ValueError(f"{label} managed region sheet missing")
    ws = wb[title]
    last_col_needed = column_index_from_string(spec.initial_entity_column)
    if ws.max_row < spec.last_field_row or ws.max_column < last_col_needed:
        raise ValueError(f"{label} managed region extent missing")
    return wb, ws


# ═══════════════════════════════════════════════════════════════════════
# materialize / extract
# ═══════════════════════════════════════════════════════════════════════


def _copy_column(ws, src, dst, *, spec: TransposedSheetSpec) -> None:
    source, target = get_column_letter(src), get_column_letter(dst)
    dimension = copy.copy(ws.column_dimensions[source])
    dimension.index = target
    dimension.min = dimension.max = dst
    ws.column_dimensions[target] = dimension
    footer_top = spec.footer_rows[0]
    for row in range(1, ws.max_row + 1):
        a, b = ws.cell(row, src), ws.cell(row, dst)
        b._style = copy.copy(a._style)
        if row < footer_top:
            b.value = a.value
            if a.comment:
                b.comment = copy.copy(a.comment)
            if a.hyperlink:
                b.hyperlink = copy.copy(a.hyperlink)
    for merged in list(ws.merged_cells.ranges):
        if merged.min_col == merged.max_col == src and merged.max_row < footer_top:
            ws.merge_cells(start_row=merged.min_row, end_row=merged.max_row, start_column=dst, end_column=dst)


def materialize_transposed_workbook(workbook_bytes: bytes, payload, *, spec: TransposedSheetSpec) -> bytes:
    wb, ws = resolve_managed_sheet(workbook_bytes, spec=spec)
    sheet_name = ws.title
    rows = normalize_payload(payload, spec=spec)
    start = column_index_from_string(spec.first_entity_column)
    last = column_index_from_string(spec.initial_entity_column)
    if start + len(rows) - 1 > 16384:
        raise ValueError(f"{_label(spec)} exceeds Excel column limit")
    for i in range(len(rows)):
        col = start + i
        if col > last:
            _copy_column(ws, last, col, spec=spec)
    for col in range(start, ws.max_column + 1):
        for row in (spec.identity_carrier_row, spec.header_row, *spec.field_rows.values()):
            ws.cell(row, col).value = None
    ws.row_dimensions[spec.identity_carrier_row].hidden = True
    for i, row_data in enumerate(rows):
        col = start + i
        carrier = ws.cell(spec.identity_carrier_row, col)
        carrier.value = spec.identity_carrier_prefix + row_data[spec.identity_key]
        carrier.protection = Protection(locked=True)
        for key in spec.managed_field_keys:
            r = spec.row_of(key)
            cell = ws.cell(r, col)
            cell.value = _get_field(row_data, key, spec=spec)
            cell.data_type = "s" if isinstance(cell.value, str) else cell.data_type
            cell.protection = Protection(locked=False)
    ws.protection.sheet = True
    out = io.BytesIO()
    wb.save(out)
    # 保留其它 sheet / 缓存 / 关系 / 不支持的 OOXML —— 只替换目标 sheet part + styles。
    import zipfile
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as original, zipfile.ZipFile(io.BytesIO(out.getvalue())) as edited:
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        sheets = ET.fromstring(original.read("xl/workbook.xml"))
        rid = next(s.attrib[rel_ns] for s in sheets.findall("m:sheets/m:sheet", ns) if s.attrib["name"] == sheet_name)
        rels = ET.fromstring(original.read("xl/_rels/workbook.xml.rels"))
        target = next(r.attrib["Target"] for r in rels if r.attrib["Id"] == rid)
        part = target.lstrip("/") if target.startswith("/") else "xl/" + target
        edited_sheets = ET.fromstring(edited.read("xl/workbook.xml"))
        edited_rid = next(s.attrib[rel_ns] for s in edited_sheets.findall("m:sheets/m:sheet", ns) if s.attrib["name"] == sheet_name)
        edited_rels = ET.fromstring(edited.read("xl/_rels/workbook.xml.rels"))
        edited_target = next(r.attrib["Target"] for r in edited_rels if r.attrib["Id"] == edited_rid)
        edited_part = edited_target.lstrip("/") if edited_target.startswith("/") else "xl/" + edited_target
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
            for info in original.infolist():
                data = edited.read(edited_part) if info.filename == part else (
                    edited.read("xl/styles.xml") if info.filename == "xl/styles.xml" else original.read(info.filename))
                archive.writestr(info, data)
        return result.getvalue()


def materialize_file(output, projection, *, spec: TransposedSheetSpec) -> None:
    """把 projection 里本转置表的列覆盖写回 output（adapter 逐 spec 调用）。

    projection 不含本表的行则 no-op（多转置 sheet 分派时其它 spec 的 projection
    不应误触发本表写盘）。
    """
    if spec.table_key not in projection.row_keys:
        return
    current = extract_transposed_workbook(output.read_bytes(), spec=spec)
    rows, _, _, _ = merge_projection_into_store(projection=projection, base_payload=current, spec=spec)
    output.write_bytes(materialize_transposed_workbook(output.read_bytes(), rows, spec=spec))


def extract_file(artifact, contract, *, spec: TransposedSheetSpec):
    """反读本转置表并构造 store projection（adapter 逐 spec 调用）。"""
    return build_store_projection(
        extract_transposed_workbook(artifact.read_bytes(), spec=spec), contract=contract, spec=spec
    )


def extract_transposed_workbook(workbook_bytes: bytes, *, spec: TransposedSheetSpec):
    _, ws = resolve_managed_sheet(workbook_bytes, spec=spec)
    label, noun = _label(spec), spec.entity_noun
    if not ws.row_dimensions[spec.identity_carrier_row].hidden:
        raise ValueError(f"{label} {noun} identity row must be hidden")
    result = []
    field_rows = tuple(spec.field_rows.values())
    header_is_field = spec.header_field_key is not None
    for col in range(column_index_from_string(spec.first_entity_column), ws.max_column + 1):
        carrier = ws.cell(spec.identity_carrier_row, col)
        raw = carrier.value
        if raw is None or raw == "":
            # 空实体列 = 模板预画的占位槽（非业务列）。校验其无遗留业务数据后跳过。
            if header_is_field:
                # D4-29 复刻：business = 字段行（排除 header，header 单独判 placeholder），
                # header 存的是 name，可能是占位 `客户NXXX`。
                business_values = [ws.cell(r, col).value for r in field_rows]
                header_value = ws.cell(spec.header_row, col).value
                placeholder_header = (
                    header_value in (None, "", "……")
                    or bool(re.fullmatch(r"客户\d+XXX", str(header_value)))
                )
            else:
                # D4-12：header 是模板预画索引号（D4-12-N），非业务字段。business = 全部字段行；
                # header 行不算业务数据（其占位标签始终存在，不参与空槽判定）。
                business_values = [ws.cell(r, col).value for r in field_rows]
                placeholder_header = True
            if any(v not in (None, "") for v in business_values) or not placeholder_header:
                raise ValueError(f"{label} missing {noun} identity carrier for populated column")
            continue
        if (carrier.data_type == "f" or not isinstance(raw, str)
                or not raw.startswith(spec.identity_carrier_prefix)):
            raise ValueError(f"{label} invalid {noun} identity carrier")

        def value(row):
            cell = ws.cell(row, col)
            if cell.data_type == "f":
                raise ValueError(f"{label} text field cannot contain a formula")
            return "" if cell.value is None else cell.value

        ident = raw[len(spec.identity_carrier_prefix):]
        if spec.nested_fields_key is not None:
            row: dict[str, Any] = {spec.identity_key: ident}
            if header_is_field:
                row[spec.header_field_key] = value(spec.header_row)
            row[spec.nested_fields_key] = {key: value(r) for key, r in spec.field_rows.items()}
            result.append(row)
        else:
            row = {spec.identity_key: ident}
            for key, r in spec.field_rows.items():
                row[key] = value(r)
            result.append(row)
    return normalize_payload(result, spec=spec)
