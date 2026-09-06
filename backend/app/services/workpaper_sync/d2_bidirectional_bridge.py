"""D2 明细表 HTML↔OnlyOffice 双向回写：可运行的最小闭环。

═══ 为什么新增这一层 ═══

`workpaper-html-onlyoffice-bidirectional-writeback-closure` 已交付全部引擎件
（`build_store_projection` / `materialize_projection` / `extract_projection`），
2026-09-06 离线实测 **756 行 → 29,484 字段 → xlsx → 读回 diff=0** 完全跑通。
但生产链路上没有任何调用方：

* `usePilotBridgeAdapter.switchMode()` 只翻 ref + 写 localStorage，零 API 调用；
* `useWorkpaperSyncBridge` 只在 `__tests__` 里被实例化；
* 前端 `SYNC_ADAPTER_REGISTERED_ENTRY_IDS = []` 硬编码，恒显「两侧数据未互通」。

⇒ 缺的是**接线**，不是能力。本模块就是那根线：把已验证的引擎接到 OnlyOffice
真正打开的那份文件（`_resolve_wp_file` 的 `{project}/workpapers/onlyoffice/{wp_code}.xlsx`）。

═══ 两个方向 ═══

`push_html_to_excel`  HTML store（`checklist_responses.remark` 的 756 行 JSON）
                      → projection → 写入 OO 文件的受管 sheet `明细表D2-2`
`pull_excel_to_html`  OO 文件 → extract projection → 合回 store JSON → 落库

═══ 为什么不直接用 room/descriptor 全协议 ═══

全协议要求 `working_paper_sync_entry_state` 有 current published representation +
room/descriptor 确认 + forcesave ack。D2 的 representation 已存在（实测 generation=1），
但 room 生命周期需要 OnlyOffice 回调联动，属更大改造。本模块走**同一批引擎函数**
但用「文件即真源」的简化基底：受管区之外的字节一律不动（`zip_patch` 策略保证），
因此不会污染模板公式、drawing、数据验证。

🔴 受管边界严格等于契约声明：只写 `明细表D2-2` 的 `FIRST_DATA_ROW..` 数据行
与 39 个受管列，`FieldMode.formula` 列不写（留模板公式自算）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.services.excel_structure_fingerprint import identity_inventory
from app.services.workpaper_sync import excel_extract as XE
from app.services.workpaper_sync import excel_instrumentation as EI
from app.services.workpaper_sync import excel_materialize as XM  # noqa: F401  (插行/写入)
from app.services.workpaper_sync import pilot_d2_large_json as P
from app.services.workpaper_sync.adapters.base import SubstrateRole
from app.services.workpaper_sync.excel_entry_gate import (
    AdapterBuild,
    FrozenEntryDefinitions,
    parse_identity_inventory,
)
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot

logger = logging.getLogger(__name__)

__all__ = [
    "D2BridgeError",
    "D2SyncReport",
    "INDEX_SHEET_HEADER_CELLS",
    "NARRATIVE_BLOCKS",
    "STORE_ITEM_ID",
    "MANAGED_SHEET",
    "locate_narrative_titles",
    "marker_of",
    "read_narrative_blocks",
    "write_index_sheet_header",
    "write_narrative_blocks",
    "build_frozen_definitions",
    "ensure_instrumented",
    "identity_binding",
    "inspect_artifact",
    "pull_excel_to_html",
    "push_html_to_excel",
    "rows_to_projection",
]

#: store 载荷所在的 `checklist_responses.item_id`
STORE_ITEM_ID = P.STORE_ITEM_ID

#: 受管 sheet 名（转发 pilot 声明，避免调用方各写一份字面量）
MANAGED_SHEET = P.MANAGED_SHEET


class D2BridgeError(RuntimeError):
    """D2 双向回写失败。**不吞异常** —— fail-open 会把接线错误伪装成「本项目无数据」。"""


@dataclass(frozen=True)
class D2SyncReport:
    """一次同步的可观测结果。字段全部由真实执行填充，不是声明值。"""

    direction: str
    rows: int
    fields: int
    managed_sheet: str
    artifact_path: str
    artifact_bytes: int
    detail: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "rows": self.rows,
            "fields": self.fields,
            "managed_sheet": self.managed_sheet,
            "artifact_path": self.artifact_path,
            "artifact_bytes": self.artifact_bytes,
            "detail": dict(self.detail or {}),
        }


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def identity_binding() -> XE.ExcelIdentityBinding:
    """契约声明的行身份绑定（表名 / UUID 列 / 表键）。"""
    return XE.ExcelIdentityBinding(
        table_name=P.TABLE_NAME,
        uuid_column=P.UUID_COL,
        table_key=P.ROWS_TABLE_KEY,
    )


def build_frozen_definitions(
    *, contract: Any, workbook_bytes: bytes
) -> FrozenEntryDefinitions:
    """按已审契约 + 目标工作簿的实际行身份清单组装 frozen definitions。

    `identity_inventory` 必须从**目标工作簿字节**现读，不能用模板的 —— 否则
    materialize 会按模板的空清单规划写入，落不到已有行上。
    """

    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    bundle = DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_digest("d2-bridge-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_digest("d2-bridge-authority"),
        slots={
            BundleSlot.template: slot(
                BundleSlot.template, contract.template_definition_sha256
            ),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation,
                contract.instrumentation_definition_sha256,
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )
    return FrozenEntryDefinitions(
        entry_id=P.PILOT_ENTRY_ID,
        bundle=bundle,
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=P.PILOT_ADAPTER_ID,
            adapter_build_digest=_digest("d2-bridge-adapter"),
            document_type="xlsx",
            contract_version="1.0.0",
        ),
        identity_inventory=parse_identity_inventory(
            identity_inventory(
                workbook_bytes,
                expected_table=P.TABLE_NAME,
                uuid_column_letter=P.UUID_COL,
            )
        ),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


def rows_to_projection(rows: list[Mapping[str, Any]], *, contract: Any) -> Any:
    """HTML store 行 → Projection（走 pilot 的生产投影器，不自造映射）。"""
    return P.build_store_projection(
        json.dumps(rows, ensure_ascii=False), contract=contract
    )


def ensure_instrumented(workbook_bytes: bytes) -> tuple[bytes, bool]:
    """确保工作簿带**身份载体**（隐藏 `_GT_SYNC` 表 + 命名表 + UUID 列）。

    ═══ 为什么必须这一步（2026-09-06 实测根因）═══

    OO 打开的 `{project}/workpapers/onlyoffice/{wp_code}.xlsx` 是
    `_resolve_wp_file` 从**未插桩的原始模板**复制的，实测：
    `_GT_SYNC` 缺失 / 命名表 `GT_D22_ROWS` 缺失 / AN 列 0 行非空。
    而 `identity_inventory` 正是按「命名表 + UUID 列」读行身份 ⇒ 清单恒空 ⇒
    `materialize_projection` 无处落行。这就是「两侧数据未互通」的物理根因。

    插桩是幂等的：已带载体的直接返回，避免每次同步都重写结构。

    :returns: (工作簿字节, 本次是否新插桩)
    """
    inv = identity_inventory(
        workbook_bytes,
        expected_table=P.TABLE_NAME,
        uuid_column_letter=P.UUID_COL,
    )
    table_present = bool(
        (inv.get("excel_table") or {}).get("present") if isinstance(inv, dict) else False
    )
    if table_present:
        return workbook_bytes, False

    gate = EI.ExcelIdentityCarrierGate.load()
    instrumented = EI.instrument_workbook_bytes(
        workbook_bytes, P.instrumentation_spec(), gate=gate
    )
    return instrumented.instrumented_bytes, True


#: footer 合计公式的匹配式：`SUM(<列><起><:><列><止>)`，只认单列纵向 SUM。
_SUM_RANGE_RE = re.compile(
    r"(?P<head>SUM\(\s*)(?P<col1>\$?[A-Z]{1,3})(?P<r1>\$?\d+)\s*:\s*"
    r"(?P<col2>\$?[A-Z]{1,3})(?P<r2>\$?\d+)(?P<tail>\s*\))",
    re.IGNORECASE,
)


def _find_footer_row(ws: Any) -> int | None:
    """按契约声明的 marker 在 A 列定位 footer 行（**不信固定行号**）。

    引擎的 `assert_footer_anchor_stable` 也是按 marker 找；这里保持同一判据，
    否则「我以为在 26 行、引擎按 marker 找不到」就会各说各话。
    """
    for r in range(1, (ws.max_row or 1) + 1):
        if str(ws[f"A{r}"].value or "").strip() == P.FOOTER_MARKER:
            return r
    return None


_NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_NS_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _sheet_part_by_name(entries: Mapping[str, bytes], sheet_name: str) -> str | None:
    """按 sheet 名解析它在 zip 里的 part 名（`xl/worksheets/sheetN.xml`）。

    🔴 用 `xml.etree` 正规解析 `workbook.xml` + rels，**不用正则、不按次序回推**：
    * 正则会被属性顺序/命名空间前缀差异打败（实测第二次 push 因 `rId8`
      匹配不到而失败）；
    * 按 `wb.sheetnames` 次序回推对**隐藏表**（`_GT_SYNC`）不成立 —— openpyxl
      的可见枚举与 zip 里的 `sheetN.xml` 编号不是同一口径（实测找不到 `_GT_SYNC`）。
    """
    import xml.etree.ElementTree as ET

    try:
        wb_root = ET.fromstring(entries.get("xl/workbook.xml", b""))
        rel_root = ET.fromstring(entries.get("xl/_rels/workbook.xml.rels", b""))
    except ET.ParseError:
        return None

    rid: str | None = None
    for sheet in wb_root.iter(f"{_NS_MAIN}sheet"):
        if sheet.get("name") == sheet_name:
            rid = sheet.get(_NS_REL_ATTR)
            break
    if not rid:
        return None

    for rel in rel_root.iter(f"{_NS_PKG_REL}Relationship"):
        if rel.get("Id") == rid:
            target = (rel.get("Target") or "").lstrip("/")
            if not target:
                return None
            cand = target if target.startswith("xl/") else f"xl/{target}"
            return cand if cand in entries else None
    return None


def entries_to_bytes(entries: Mapping[str, bytes]) -> bytes:
    """把 zip 条目字典打包回 xlsx 字节。"""
    import zipfile

    out = io_bytes(b"")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return out.getvalue()


def _managed_sheet_part(entries: Mapping[str, bytes]) -> str:
    """受管 sheet 在 zip 里的 part 名（`xl/worksheets/sheetN.xml`）。"""
    part = _sheet_part_by_name(entries, P.MANAGED_SHEET)
    if part is None:
        raise D2BridgeError(f"找不到 sheet {P.MANAGED_SHEET!r} 对应的 worksheet part")
    return part


def _ensure_row_capacity(workbook_bytes: bytes, needed_rows: int) -> bytes:
    """用引擎的**声明式结构性插行**把受管区扩到能放下 `needed_rows` 行。

    ═══ 为什么必须走 `shift_sheet_rows` 而不是 openpyxl ═══

    模板受管区是 13..24（12 行）、footer 在 26 行。要放 756 行就得把 footer 推到
    数据之后。但 footer 位置被冻结在插桩元数据 `GT_FOOTER_ROW` 里，引擎的
    `assert_footer_anchor_stable` 明确拒绝「跟着 marker 走」：extract 仍按契约
    `static_row` 反读，偷偷搬 footer 会造成**写在新行、反读旧行**的静默错值。

    合规路径是声明位移：`plan_workbook_row_change_for_insert` 产出 `RowShiftPlan`，
    `shift_sheet_rows` 在 XML 层插行 —— 它同时
    ① 位移 footer 与所有携带行号的结构，
    ② 只在 `total_formula_rows` 声明的行上**扩张**合计公式区间（其余仅位移），
    ③ 按 `style_from` 行给新行造格与样式。

    2026-09-06 实测：自己用 openpyxl 搬 footer 连撞两个不同的 fail-closed
    （`FooterAnchorDriftError` / `IdentityRetentionError`），都指向这一条。
    """
    import zipfile

    with zipfile.ZipFile(io_bytes(workbook_bytes)) as zf:
        entries = {n: zf.read(n) for n in zf.namelist()}

    # 🔴 容量判据读**当前实际** footer 位置，不用模板骨架常量。
    # 否则第二次 push 会在已扩好的文件上再插 744 行（实测第二次失败的同族问题）：
    # 幂等性要求「已够放就直接返回」。
    current_footer = _frozen_footer_row(entries)
    current_capacity = max(current_footer - 1 - P.FIRST_DATA_ROW + 1, 0)
    if needed_rows <= current_capacity:
        return workbook_bytes

    skeleton = current_capacity

    part = _managed_sheet_part(entries)
    insert_count = needed_rows - skeleton

    region_last = P.FIRST_DATA_ROW + current_capacity - 1
    plan = XM.plan_workbook_row_change_for_insert(
        entries,
        managed_sheet_name=P.MANAGED_SHEET,
        managed_sheet_part=part,
        # 在当前受管区末行之后插：既有行的格式与公式作样式来源
        insert_at=region_last + 1,
        count=insert_count,
        style_from=region_last,
        region_first_row=P.FIRST_DATA_ROW,
        region_last_row=region_last,
    )
    if plan is None:
        raise D2BridgeError(
            f"结构性插行计划为空（需插 {insert_count} 行）—— 无法扩容受管区"
        )

    # `WorkbookRowChangePlan` 是工作簿级计划（含传播/删除等），`shift_sheet_rows`
    # 要的是 sheet 级 `RowShiftPlan` —— 从前者的字段现造，不另立第二份参数真源。
    shift = XM.RowShiftPlan(
        insert_at=plan.at,
        count=plan.count,
        style_from=plan.style_from,
        table_key=P.ROWS_TABLE_KEY,
    )
    shifted_xml, _report = XM.shift_sheet_rows(
        entries[part].decode("utf-8"),
        shift,
        total_formula_rows=(current_footer,),
        managed_columns=tuple(
            {str(spec[1]) for spec in P.MANAGED_FIELD_SPECS} | {P.UUID_COL}
        ),
    )
    entries[part] = shifted_xml.encode("utf-8")

    # ── 位移后必须同步冻结元数据 ──────────────────────────────────────
    # `materialize_projection` 内部以 `row_shift=None` 调 `assert_footer_anchor_stable`，
    # 它比对的是隐藏 `_GT_SYNC` 表里的 `GT_FOOTER_ROW`。插行把 footer 从 26 推到
    # 26+count 之后，若不更新该值，写入侧会判「footer 已下移」并 fail closed
    # （2026-09-06 实测：位移正确、仍被拒，因为冻结预期还是旧值）。
    # 一并更新受管区末行与 UUID 末行，保持元数据与真实结构自洽。
    _rebind_frozen_rows(entries, count=insert_count, last_data_row=needed_rows + P.FIRST_DATA_ROW - 1)

    return entries_to_bytes(entries)


def io_bytes(data: bytes) -> Any:
    """`BytesIO` 的小包装（避免在多处 import io）。"""
    import io

    return io.BytesIO(data)


#: `_GT_SYNC` 里随插行位移的行号键 → 是否按 count 平移。
#: `GT_MANAGED_RANGE` 与 `GT_ROW_UUID_LAST_ROW` 要跟着受管区末行走。
_SHIFTED_BINDING_KEYS = ("GT_FOOTER_ROW", "GT_ROW_UUID_LAST_ROW")


def _rebind_frozen_rows(
    entries: dict[str, bytes], *, count: int, last_data_row: int
) -> None:
    """把 `_GT_SYNC` 里的行号型冻结值按插行结果更新（就地改 entries）。

    只改**行号**，不动 schema 版本/模板 digest/entry_id 等身份类键 —— 那些是
    identity 的一部分，动了等于伪造另一个模板。
    """
    import re as _re

    part = _sheet_part_by_name(entries, "_GT_SYNC")
    if part is None or part not in entries:
        raise D2BridgeError("找不到 _GT_SYNC 隐藏表 —— 无法同步 footer 冻结行号")

    xml = entries[part].decode("utf-8")
    shared = _shared_strings_list(entries)

    def _cell_text(row_xml: str) -> str:
        mm = _re.search(r'<c[^>]*r="B\d+"[^>]*?(?:/>|>(.*?)</c>)', row_xml, _re.S)
        if not mm or not mm.group(1):
            return ""
        inner = mm.group(1)
        if 't="s"' in row_xml:
            iv = _re.search(r"<v>(\d+)</v>", inner)
            if iv and int(iv.group(1)) < len(shared):
                return shared[int(iv.group(1))]
        tv = _re.search(r"<t[^>]*>(.*?)</t>", inner, _re.S)
        if tv:
            return tv.group(1)
        vv = _re.search(r"<v>(.*?)</v>", inner, _re.S)
        return vv.group(1) if vv else ""

    updates: dict[str, str] = {
        "GT_FOOTER_ROW": str(_frozen_footer_row(entries) + count),
        "GT_ROW_UUID_LAST_ROW": str(last_data_row),
        "GT_MANAGED_RANGE": f"A{P.FIRST_DATA_ROW}:{P.MANAGED_LAST_COL}{last_data_row}",
    }

    for row_m in list(_re.finditer(r"<row[^>]*>.*?</row>", xml, _re.S)):
        block = row_m.group(0)
        key = _key_of_row(block, shared)
        if key not in updates:
            continue
        new_block = _set_row_b_value(block, updates[key], xml_has_shared=True)
        xml = xml.replace(block, new_block, 1)

    entries[part] = xml.encode("utf-8")


def _frozen_footer_row(entries: Mapping[str, bytes]) -> int:
    """读 `_GT_SYNC` 里冻结的 `GT_FOOTER_ROW`。

    这是「当前受管容量」的唯一真源：受管区 = `FIRST_DATA_ROW .. footer-1`。
    没有该键（未插桩）时回退模板常量。
    """
    inv = identity_inventory(
        entries_to_bytes(entries),
        expected_table=P.TABLE_NAME,
        uuid_column_letter=P.UUID_COL,
    )
    pairs = ((inv.get("hidden_sheet") or {}).get("pairs") or {}) if isinstance(inv, dict) else {}
    raw = str(pairs.get("GT_FOOTER_ROW") or "").strip()
    return int(raw) if raw.isdigit() else P.FOOTER_ROW


def _shared_strings_list(entries: Mapping[str, bytes]) -> list[str]:
    import re as _re

    raw = entries.get("xl/sharedStrings.xml", b"").decode("utf-8", "ignore")
    return [
        _re.sub(r"<.*?>", "", si)
        for si in _re.findall(r"<si>(.*?)</si>", raw, _re.S)
    ]


def _key_of_row(row_xml: str, shared: list[str]) -> str:
    """取该行 A 列的文本（`_GT_SYNC` 的键列）。"""
    import re as _re

    m = _re.search(r'<c r="A\d+"([^>]*)(?:/>|>(.*?)</c>)', row_xml, _re.S)
    if not m:
        return ""
    attrs, inner = m.group(1) or "", m.group(2) or ""
    if 't="s"' in attrs:
        iv = _re.search(r"<v>(\d+)</v>", inner)
        if iv and int(iv.group(1)) < len(shared):
            return shared[int(iv.group(1))]
    tv = _re.search(r"<t[^>]*>(.*?)</t>", inner, _re.S)
    if tv:
        return tv.group(1)
    vv = _re.search(r"<v>(.*?)</v>", inner, _re.S)
    return vv.group(1) if vv else ""


def _set_row_b_value(row_xml: str, value: str, *, xml_has_shared: bool) -> str:
    """把该行 B 列改成 inline string `value`（避免动 sharedStrings 表）。"""
    import re as _re

    m = _re.search(r'<c r="(B\d+)"[^>]*(?:/>|>.*?</c>)', row_xml, _re.S)
    if not m:
        return row_xml
    ref = m.group(1)
    replacement = f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'
    return row_xml.replace(m.group(0), replacement, 1)


def _seed_row_identity(
    workbook_bytes: bytes, rows: list[Mapping[str, Any]]
) -> bytes:
    """把 store 的 `rowId` 写进受管 sheet 的身份列，并让命名表覆盖全部数据行。

    模板骨架只有 `FIRST_DATA_ROW..LAST_DATA_ROW`（13..24，12 行），而真实数据有
    756 行 ⇒ 必须同时扩展**命名表范围**与 footer 位置，否则超出部分不在身份清单里。

    受管数据列**一格不写**（那是 materialize 的职责，它会保护公式/drawing/数据验证）。

    ═══ 前置条件：容量已由 `_ensure_row_capacity` 用引擎的结构性插行扩好 ═══

    本函数**只在既有物理行上写身份/公式/表范围**，不负责把 footer 挪开。
    footer 的位移必须走 `shift_sheet_rows`（声明式 `RowShiftPlan`）—— 用 openpyxl
    自己搬会撞 `FooterAnchorDriftError`：引擎把 `GT_FOOTER_ROW` 冻结在插桩元数据里，
    且 extract 仍按契约 `static_row` 反读，跟着 marker 写会造成
    「写在新行、反读旧行」的静默错值（2026-09-06 实测，两次不同报错都指向这里）。

    ═══ 三步顺序是判据（各有实测反例）═══

    1. **播种身份** —— 逐行写 `rowId` 到 UUID 列，并清理尾部残留。
    2. **铺公式** —— 契约声明的 formula 列必须每行都有公式 ⇒ 否则
       `ProtectedRegionWriteError`。
    3. **扩命名表** —— 表范围是身份清单的取值域，起始行必须是 `FIRST_DATA_ROW`
       而非表头行（12）⇒ 否则给表头 mint 身份、撞 `RowIdentityWriteError`。
    """
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes), data_only=False)
    if P.MANAGED_SHEET not in wb.sheetnames:
        raise D2BridgeError(
            f"目标工作簿缺受管 sheet {P.MANAGED_SHEET!r}，实际有 {wb.sheetnames!r}"
        )
    ws = wb[P.MANAGED_SHEET]
    last_row = P.FIRST_DATA_ROW + max(len(rows), 1) - 1

    seen: set[str] = set()
    for offset, row in enumerate(rows):
        row_id = str(row.get(P.ROW_IDENTITY_STORE_KEY) or "").strip()
        if not row_id:
            raise D2BridgeError(
                f"第 {offset + 1} 行缺行身份 {P.ROW_IDENTITY_STORE_KEY!r} —— "
                "行身份是合并的唯一依据，缺失会导致 Excel 侧改动无法回写到正确行"
            )
        if row_id in seen:
            raise D2BridgeError(f"行身份重复: {row_id!r}")
        seen.add(row_id)
        ws[f"{P.UUID_COL}{P.FIRST_DATA_ROW + offset}"] = row_id

    # ── 清掉受管区之外的一切身份 ──────────────────────────────────────
    # 🔴 2026-09-06 实测缺陷：每轮往返行数 +1（756→757→…）。根因是插行后 footer
    # 所在行（及其后）残留/继承了身份值，而它不是 store 行 ⇒ extract 把它当一行
    # 真数据读回，下一轮 push 又按 757 行扩容 ⇒ 无限增长。
    # 因此清理范围必须覆盖到**物理末行**（含 footer 行本身），不能只从 last_row+1
    # 清到 max_row —— openpyxl 的 `max_row` 在插行后可能小于真实使用范围。
    tail_start = last_row + 1
    tail_end = max(int(ws.max_row or 0), tail_start, last_row + 8)
    for r in range(tail_start, tail_end + 1):
        if ws[f"{P.UUID_COL}{r}"].value not in (None, ""):
            ws[f"{P.UUID_COL}{r}"] = None

    # ── 公式列必须铺到每一行 ──────────────────────────────────────────
    # 契约把 Q/S/AB 声明为 formula 列。模板只在骨架 13..24 行有公式，超出部分为空 ⇒
    # `plan_managed_writes` 判「契约说是公式但 substrate 没公式」= 模板漂移，
    # 抛 `ProtectedRegionWriteError`（AC 6.6，正确的 fail-closed）。
    # 这里按 pilot 声明的 `FORMULA_TEMPLATES` 逐行实例化，不自己拼公式字符串。
    for col, tpl in P.FORMULA_TEMPLATES.items():
        for r in range(P.FIRST_DATA_ROW, last_row + 1):
            cell = ws[f"{col}{r}"]
            if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                cell.value = tpl.format(r=r)

    # ── 命名表必须覆盖全部数据行 ──────────────────────────────────────
    # 表范围是身份清单的取值域；不扩展则第 25 行起的数据不在清单里、写不进去。
    tables = dict(getattr(ws, "tables", {}) or {})
    table = tables.get(P.TABLE_NAME)
    if table is None:
        raise D2BridgeError(
            f"受管 sheet 缺命名表 {P.TABLE_NAME!r} —— 应先 ensure_instrumented()"
        )
    # 🔴 起始行是 FIRST_DATA_ROW(13)，**不是** HEADER_LEAF_ROW(12)。把表头行圈进
    # 范围会让插桩给表头 mint 一个行身份，而 projection 里没有它 ⇒
    # `RowIdentityWriteError`（引擎不许静默丢弃 Excel 侧的行）。
    # 插桩自己产出的范围就是 `A13:AN24`，扩展时只动末行。
    table.ref = f"A{P.FIRST_DATA_ROW}:{P.UUID_COL}{last_row}"

    # ── fail closed：身份行数必须**恰好**等于 store 行数 ────────────────
    # 多一个 ⇒ extract 读回幽灵行、下轮按 N+1 扩容（实测 756→757 的无限增长）；
    # 少一个 ⇒ 该行的编辑无法回写。两侧都是数据正确性问题，不能静默放过。
    seeded = sum(
        1
        for r in range(P.FIRST_DATA_ROW, last_row + 1)
        if ws[f"{P.UUID_COL}{r}"].value not in (None, "")
    )
    stray = [
        r
        for r in range(last_row + 1, max(int(ws.max_row or 0), last_row + 8) + 1)
        if ws[f"{P.UUID_COL}{r}"].value not in (None, "")
    ]
    if seeded != len(rows) or stray:
        raise D2BridgeError(
            f"身份行数校验失败：受管区内 {seeded} 个身份、store {len(rows)} 行"
            f"，受管区外残留 {stray[:5]}（共 {len(stray)}）—— "
            "多余身份会被读回成幽灵行并逐轮累积，缺失身份会让该行编辑无法回写"
        )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def push_html_to_excel(
    *,
    rows: list[Mapping[str, Any]],
    artifact: Path,
    narratives: Mapping[str, str] | None = None,
    header: Mapping[str, Any] | None = None,
) -> D2SyncReport:
    """HTML → Excel：把结构化视图的内容写进 OnlyOffice 打开的那份 xlsx。

    三块内容、三种语义：

    * `rows`      明细行 —— 走契约受管区，**双向**
    * `narratives` 审计说明 / 审计结论 —— 走标量格通道，**双向**
    * `header`    编制信息 —— 写「底稿目录」的引用源格，**单向下行**
      （真源是 `Project` / `working_paper`，见 `INDEX_SHEET_HEADER_CELLS` 注释）

    :param rows: `checklist_responses.remark` 解析出的 store 行（含 `rowId`）
    :param artifact: OO 实际打开的文件（`{project}/workpapers/onlyoffice/{wp_code}.xlsx`）
    :param narratives: `{item_id: 文本}`，键见 :data:`NARRATIVE_BLOCKS`
    :param header: `wp_header_data_service.get_header_data()` 的返回
    :raises D2BridgeError: 任何一步失败都抛，**不静默降级**
    """
    if not artifact.is_file():
        raise D2BridgeError(f"目标 xlsx 不存在: {artifact}")

    contract = P.load_pilot_contract()
    projection = rows_to_projection(list(rows), contract=contract)

    original = artifact.read_bytes()
    carrier, newly_instrumented = ensure_instrumented(original)
    # 先用引擎的声明式插行扩容（含 footer 位移 + 合计区间扩张），再写身份/公式/表范围
    expanded = _ensure_row_capacity(carrier, len(rows))
    seeded = _seed_row_identity(expanded, list(rows))

    binding = identity_binding()
    definitions = build_frozen_definitions(contract=contract, workbook_bytes=seeded)

    # 🔴 属性名是 `row_uuids`（EntryIdentityInventory）。写成 `row_keys` 会拿到
    # 默认空元组 ⇒ 守卫恒判「清单为空」，而真实清单其实是满的（假红）。
    inventory_rows = len(getattr(definitions.identity_inventory, "row_uuids", ()) or ())
    if inventory_rows == 0:
        raise D2BridgeError(
            "播种后行身份清单仍为空 —— materialize 无处落行；"
            f"检查受管 sheet {P.MANAGED_SHEET!r} 的 {P.UUID_COL} 列与 "
            f"表 {P.TABLE_NAME!r} 的覆盖范围"
        )

    work = artifact.parent / f".{artifact.stem}.sync-tmp{artifact.suffix}"
    substrate = artifact.parent / f".{artifact.stem}.sync-base{artifact.suffix}"
    try:
        substrate.write_bytes(seeded)
        outcome = XM.materialize_projection(
            substrate=substrate,
            projection=projection,
            output=work,
            definitions=definitions,
            binding=binding,
            substrate_role=SubstrateRole.published_representation,
            substrate_kind=ArtifactKind.canonical,
            substrate_state=ArtifactState.published,
        )
        # ── 叙述块与表头：在 materialize **之后**写 ────────────────────
        # 它们在受管区之外，materialize 不碰；放在之后写可确保引擎的
        # 受管区规划（含 footer 锚点校验）看到的是未被我扰动的结构。
        narrative_lines = 0
        header_cells = 0
        if narratives or header:
            narrative_lines, header_cells = _write_scalar_blocks(
                work, narratives=narratives or {}, header=header or {}
            )

        # 原子替换：materialize 成功才覆盖 OO 正在读的文件
        artifact.write_bytes(work.read_bytes())
    finally:
        for tmp in (work, substrate):
            tmp.unlink(missing_ok=True)

    return D2SyncReport(
        direction="html_to_excel",
        rows=len(rows),
        fields=len(projection.stable_keys()),
        managed_sheet=P.MANAGED_SHEET,
        artifact_path=str(artifact),
        artifact_bytes=artifact.stat().st_size,
        detail={
            "identity_rows": inventory_rows,
            "newly_instrumented": newly_instrumented,
            "narrative_lines": narrative_lines,
            "header_cells": header_cells,
            "write_strategy": str(
                getattr(getattr(outcome, "strategy", None), "strategy", "")
                or getattr(outcome, "strategy", "")
            )[:120],
        },
    )


def _write_scalar_blocks(
    path: Path, *, narratives: Mapping[str, str], header: Mapping[str, Any]
) -> tuple[int, int]:
    """在已 materialize 的工作簿上写叙述块与目录页表头。

    :returns: `(写入的叙述行数, 写入的表头格数)`
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=False)
    if P.MANAGED_SHEET not in wb.sheetnames:
        raise D2BridgeError(f"缺受管 sheet {P.MANAGED_SHEET!r}，无法写叙述块")

    lines = write_narrative_blocks(wb[P.MANAGED_SHEET], narratives) if narratives else 0
    cells = write_index_sheet_header(wb, header) if header else 0

    wb.save(path)
    return lines, cells


#: 受管字段的 `field_id -> store_key` 映射（从契约字段规格现算，不写第二份清单）。
#: MANAGED_FIELD_SPECS 的 tuple 形态 = (field_id, column, mode, value_type, store_key, label)
_FIELD_TO_STORE: Mapping[str, str] = {
    str(spec[0]): str(spec[4]) for spec in P.MANAGED_FIELD_SPECS
}

def _assign_store_value(target: dict[str, Any], field_id: str, value: Any) -> bool:
    """把一个受管字段值写回 store 行的正确位置。

    嵌套路径**直接取契约声明的 store_key**（形如 `agingPrior/within1`，`/` 分段），
    不在这里自造前缀表 —— 那会变成与契约并行的第二份映射真源，契约改了不会跟着改。

    :returns: 是否真的写了（用于统计，避免把「没写」算成「已同步」）
    """
    store_key = _FIELD_TO_STORE.get(field_id)
    if not store_key:
        return False

    segments = [s for s in store_key.split("/") if s]
    if not segments:
        return False

    cursor: dict[str, Any] = target
    for seg in segments[:-1]:
        nxt = cursor.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[seg] = nxt
        cursor = nxt
    cursor[segments[-1]] = value
    return True


def pull_excel_to_html(
    *, artifact: Path, base_rows: list[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], D2SyncReport]:
    """Excel → HTML：读回 OO 文件的受管值，按行身份合进 store 行。

    以 **Excel 侧为准**覆盖受管字段；`base_rows` 提供行顺序与非受管字段
    （如前端自用的展示态），因此不会因为一次回写丢掉 store 里的额外键。

    :returns: (合并后的 store 行, 报告)
    """
    if not artifact.is_file():
        raise D2BridgeError(f"目标 xlsx 不存在: {artifact}")

    contract = P.load_pilot_contract()
    workbook_bytes = artifact.read_bytes()
    inv_probe = identity_inventory(
        workbook_bytes,
        expected_table=P.TABLE_NAME,
        uuid_column_letter=P.UUID_COL,
    )
    if not bool((inv_probe.get("excel_table") or {}).get("present")):
        raise D2BridgeError(
            f"{artifact.name} 无身份载体（命名表 {P.TABLE_NAME!r} 缺失）—— "
            "该文件从未经 HTML→Excel 同步过，Excel 侧没有可回写的行身份。"
            "请先在结构化视图保存一次以建立身份载体。"
        )
    binding = identity_binding()
    definitions = build_frozen_definitions(
        contract=contract, workbook_bytes=workbook_bytes
    )

    outcome = XE.extract_projection(
        artifact=artifact,
        definitions=definitions,
        binding=binding,
        substrate_role=SubstrateRole.incoming,
        artifact_kind=ArtifactKind.incoming,
        artifact_state=ArtifactState.durable,
    )
    projection = getattr(outcome, "projection", None)
    if projection is None:
        raise D2BridgeError("extract_projection 未返回 projection")

    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(P.ROW_IDENTITY_STORE_KEY) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    applied = 0
    touched_rows: set[str] = set()
    for key in projection.stable_keys():
        fv = projection.get(key)
        if fv is None or fv.is_protected:
            continue  # 公式/自动取数列不回写 store
        rid = fv.row_key
        if not rid:
            continue
        target = by_id.get(rid)
        if target is None:
            target = {P.ROW_IDENTITY_STORE_KEY: rid}
            by_id[rid] = target
            order.append(rid)
        field_id = key.rsplit("/", 1)[-1]
        if _assign_store_value(target, field_id, fv.value):
            applied += 1
            touched_rows.add(rid)

    merged = [by_id[rid] for rid in order]

    # ── 叙述块（审计说明 / 审计结论）也要读回 ─────────────────────────
    # 表头**不读**：真源是 Project / working_paper，从 Excel 回写会越权改主数据
    # 并被下次渲染覆盖（见 INDEX_SHEET_HEADER_CELLS 注释）。
    import openpyxl

    wb = openpyxl.load_workbook(artifact, data_only=False)
    narratives = read_narrative_blocks(wb[P.MANAGED_SHEET])

    return merged, D2SyncReport(
        direction="excel_to_html",
        rows=len(touched_rows),
        fields=applied,
        managed_sheet=P.MANAGED_SHEET,
        artifact_path=str(artifact),
        artifact_bytes=len(workbook_bytes),
        detail={
            "extracted_keys": len(projection.stable_keys()),
            "narratives": narratives,
        },
    )


def inspect_artifact(artifact: Path) -> dict[str, Any]:
    """观测 xlsx 的受管区现状：业务行数 / 身份行数 / 是否带身份载体。

    供 `status` 端点向 UI 暴露**真实**两侧状态，替代前端硬编码的能力常量。
    """
    import openpyxl

    data = artifact.read_bytes()
    inv = identity_inventory(
        data, expected_table=P.TABLE_NAME, uuid_column_letter=P.UUID_COL
    )
    table = (inv.get("excel_table") or {}) if isinstance(inv, dict) else {}

    wb = openpyxl.load_workbook(artifact, data_only=False)
    if P.MANAGED_SHEET not in wb.sheetnames:
        return {
            "instrumented": bool(table.get("present")),
            "managed_sheet_present": False,
            "business_rows": 0,
            "identity_rows": 0,
        }
    ws = wb[P.MANAGED_SHEET]
    business = sum(
        1
        for r in range(P.FIRST_DATA_ROW, ws.max_row + 1)
        if ws[f"B{r}"].value not in (None, "")
    )
    identity = sum(
        1
        for r in range(P.FIRST_DATA_ROW, ws.max_row + 1)
        if ws[f"{P.UUID_COL}{r}"].value not in (None, "")
    )
    return {
        "instrumented": bool(table.get("present")),
        "table_ref": table.get("table_ref"),
        "managed_sheet_present": True,
        "business_rows": business,
        "identity_rows": identity,
        "bytes": len(data),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 表头区 / 审计说明 / 审计结论 —— 受管区之外的「叙述与编制信息」双向同步
#
# 为什么单独一段而不是塞进 `MANAGED_FIELD_SPECS`：
# 契约 `d2.receivable_detail` 的受管区严格是 `A13:AM{last}`（行级明细），
# 它的 projection 按 `{table}/{row_uuid}/{field}` 索引 —— 表头与叙述文本
# **没有行身份**，塞进去会破坏 row identity 语义（且 materialize 会拿它们
# 当行数据去对齐行）。所以这里走独立的「标量格」通道，仍复用同一份
# openpyxl 写盘 + 同一份 store 落库，不另起第二条同步链路。
# ═══════════════════════════════════════════════════════════════════════════

#: 审计说明 / 审计结论：`(store item_id, 标题行, 正文起, 正文止)`
#:
#: 坐标取自权威模板实测（2026-09-06）：
#:   A29='三、审计说明：'  正文 30..32（全空、无合并）
#:   A33='四、审计结论：'  正文 34..35（全空、无合并）
#: 标题行**不写**（那是模板字面量，属结构）；只写正文行。
NARRATIVE_BLOCKS: tuple[tuple[str, int, int, int], ...] = (
    ("D2-detail-audit-note", 29, 30, 32),
    ("D2-detail-audit-conclusion", 33, 34, 35),
)

#: 正文写入列（A 列整行，与模板一致：说明/结论都从 A 列起排）
NARRATIVE_COL = "A"

#: 表头区字段 → 单元格。**只下行（系统→Excel），不回写**。
#:
#: 🔴 为什么不双向：模板里这些格是 `=底稿目录!A2` 之类的**跨表引用公式**
#: （实测 `A3/A4/F3/F4/J3/J4` 全部 `data_type='f'`），真源在「底稿目录」sheet；
#: 而平台侧真源是 `Project`（客户名/审计期间）与 `working_paper`（编制人/复核人/
#: 日期，由派工与复核流程写）。从 Excel 往回写等于让一张明细表去改项目主数据
#: 与派工结果 —— 既越权也会被下一次渲染覆盖。
#: 因此这里的义务只有一条：**把系统的权威值填到「底稿目录」的引用源格**，
#: 让 Excel 的表头公式自然算出正确值（而不是覆盖公式本身）。
#: 键名口径 = `wp_preparation_info_service.build_preparation_info` 的返回
#: （即前端「编制信息」面板真正显示的那 6 个字段），**不是** `wp_header_data_service`
#: 的 camelCase 口径。混用会导致填进 Excel 的值与 UI 显示的不是同一个。
INDEX_SHEET_HEADER_CELLS: Mapping[str, str] = {
    # 底稿目录!A2..A7 —— D2-2 表头公式的引用源
    "entity_name": "A2",
    "period_end": "A3",
    "preparer": "A4",
    "prep_date": "A5",
    "reviewer": "A6",
    "review_date": "A7",
}

#: 「底稿目录」sheet 名（模板实测）。
INDEX_SHEET_NAME = "底稿目录"

#: 目录页各字段的中文前缀（模板里是「被审计单位名称：」这种带标签的写法）。
#: 回填时保留标签、只替换值，避免把标签擦掉。
_INDEX_LABELS: Mapping[str, str] = {
    "entity_name": "被审计单位名称：",
    "period_end": "截止日：",
    "preparer": "编制人：",
    "prep_date": "编制日期：",
    "reviewer": "复核人：",
    "review_date": "复核日期：",
}


def _split_narrative(text: str, *, max_lines: int) -> list[str]:
    """把一段文本切成不超过 `max_lines` 行；超出的**全部并入最后一行**。

    绝不截断丢字：审计说明是审计证据，丢内容比排版难看严重得多。
    """
    lines = [ln.rstrip() for ln in str(text or "").replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return []
    if len(lines) <= max_lines:
        return lines
    head = lines[: max_lines - 1]
    tail = " ".join(ln for ln in lines[max_lines - 1 :] if ln)
    return [*head, tail]


def locate_narrative_titles(ws: Any) -> dict[str, int]:
    """按**标题 marker** 在 A 列定位每个叙述块的标题行。

    🔴 不按「模板行号 + 行数推算的 offset」定位（2026-09-06 实测教训）：
    `shift_sheet_rows` 只位移受管区内携带行号的结构，**叙述块标题会不会跟着动、
    动多少，取决于插入点与它的相对位置**，用行数反推必错（实测算出 773 而实际
    仍在 29）。引擎的 `assert_footer_anchor_stable` 也是按 marker 找，这里保持同一
    判据，两侧才不会各说各话。

    :returns: `{item_id: 标题行号}`；找不到的 item 不出现在结果里
    """
    wanted = {marker_of(item_id): item_id for item_id, *_ in NARRATIVE_BLOCKS}
    found: dict[str, int] = {}
    for r in range(1, (ws.max_row or 1) + 1):
        text = str(ws[f"{NARRATIVE_COL}{r}"].value or "").strip()
        if text in wanted:
            found.setdefault(wanted[text], r)
    return found


#: 叙述块的标题字面量（源模板 A29 / A33 原文，逐字相等）。
_NARRATIVE_MARKERS: Mapping[str, str] = {
    "D2-detail-audit-note": "三、审计说明：",
    "D2-detail-audit-conclusion": "四、审计结论：",
}


def marker_of(item_id: str) -> str:
    """该叙述块在 Excel A 列的标题字面量。"""
    return _NARRATIVE_MARKERS.get(item_id, "")


def write_narrative_blocks(ws: Any, store: Mapping[str, str]) -> int:
    """把审计说明 / 审计结论写进 Excel 正文行（按 marker 定位，不用 offset）。

    正文容量 = 本块标题的下一行 .. 下一块标题的前一行（末块用模板声明的行数）。
    这样即使插行把两块之间的距离改变了，也不会写到别人的区里。

    :returns: 写入的行数
    """
    titles = locate_narrative_titles(ws)
    missing = [item for item, *_ in NARRATIVE_BLOCKS if item not in titles]
    if missing:
        raise D2BridgeError(
            f"在 {NARRATIVE_COL} 列找不到叙述块标题：{missing}（marker="
            f"{[marker_of(m) for m in missing]}）—— 拒绝把正文写到不确定的位置"
        )

    ordered = sorted(titles.items(), key=lambda kv: kv[1])
    written = 0
    for idx, (item_id, title_row) in enumerate(ordered):
        spec = next(s for s in NARRATIVE_BLOCKS if s[0] == item_id)
        template_capacity = spec[3] - spec[2] + 1
        if idx + 1 < len(ordered):
            capacity = max(ordered[idx + 1][1] - title_row - 1, 1)
        else:
            capacity = template_capacity

        lines = _split_narrative(store.get(item_id, ""), max_lines=capacity)
        for i in range(capacity):
            ref = f"{NARRATIVE_COL}{title_row + 1 + i}"
            ws[ref] = lines[i] if i < len(lines) else None
        written += len(lines)
    return written


def read_narrative_blocks(ws: Any) -> dict[str, str]:
    """从 Excel 读回审计说明 / 审计结论（按 marker 定位）。

    多行以 `\\n` 连接；全空返回空串（不返回 None，便于与 store 直接比较）。
    定位不到标题时返回空 dict —— 由调用方决定是否算失败，**不猜行号**。
    """
    titles = locate_narrative_titles(ws)
    if len(titles) < len(NARRATIVE_BLOCKS):
        return {}

    ordered = sorted(titles.items(), key=lambda kv: kv[1])
    out: dict[str, str] = {}
    for idx, (item_id, title_row) in enumerate(ordered):
        spec = next(s for s in NARRATIVE_BLOCKS if s[0] == item_id)
        if idx + 1 < len(ordered):
            capacity = max(ordered[idx + 1][1] - title_row - 1, 1)
        else:
            capacity = spec[3] - spec[2] + 1

        lines: list[str] = []
        for i in range(capacity):
            v = ws[f"{NARRATIVE_COL}{title_row + 1 + i}"].value
            lines.append("" if v is None else str(v).rstrip())
        while lines and not lines[-1]:
            lines.pop()
        out[item_id] = "\n".join(lines)
    return out


def write_index_sheet_header(wb: Any, header: Mapping[str, Any]) -> int:
    """把系统权威表头值填到「底稿目录」的引用源格（单向，系统 → Excel）。

    ═══ 为什么写目录页而不写 D2-2 的表头格 ═══

    D2-2 的 `A3/A4/F3/F4/J3/J4` 是 `=底稿目录!A2` 之类的跨表引用公式。
    直接写那些格会**覆盖公式**，模板的联动就永久坏掉（而且下次打开别的 sheet
    还会发现表头对不上）。正确做法是喂它的数据源，让公式自己算。

    :returns: 实际写入的格数
    """
    if INDEX_SHEET_NAME not in wb.sheetnames:
        # 不是致命错误：有些项目存储里的副本可能没有目录页
        logger.warning(
            "工作簿缺「%s」sheet —— 跳过表头回填（D2-2 表头公式将取不到值）",
            INDEX_SHEET_NAME,
        )
        return 0

    ws = wb[INDEX_SHEET_NAME]
    written = 0
    for field, ref in INDEX_SHEET_HEADER_CELLS.items():
        value = str(header.get(field) or "").strip()
        if not value:
            continue
        label = _INDEX_LABELS.get(field, "")
        ws[ref] = f"{label}{value}" if label else value
        written += 1
    return written
