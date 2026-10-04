# -*- coding: utf-8 -*-
"""A5-1 现金流量表审计 —— Phase 5 entry 模块（A 循环 canary）。

spec: a-cycle-sync-foundation-and-first-canary · Task 12/13

═══ A5-1 与 D/H 循环的根本不同 ═══

1. **纯静态 entry（0 个动态行表）**：A5-1 的审定表/勾稽核对/核查表全是固定行，不需要
   `RowTableSheetSpec` 的行新增/删除/UUID 列机制。store 是扁平键值对
   （`a51-audit-1.unadjusted` 等）。本册是 `review_status == "reviewed"` 分母下**唯一**
   0 动态表的契约（分母与成员一律**现算**：
   `backend/data/workpaper_sync_contracts/*.json` 里 `review_status == "reviewed"`
   的份数 × 其中 `sheets[].tables[].row_identity` 全为 `None` 的份数；
   原文写死的那个分母快照已过期，禁再写死分母数字） ⇒ 受管区走 workbook-scope definedName 锚点（`region_kind="static"`），
   **不造**退化动态表当载体（归档 spec `workpaper-sync-static-cell-sheet-writeback`
   的 DEC-3 明确否决）。
2. **无 TB 发布门**：A 类底稿不回写试算表（AC-3 空分母裁定）。
3. **持久化走 checklist_responses**：通过 import 闭包（AC-42），宿主内直调 = 0。
4. **公式保护**：审定表 G 列 = D + E（审定数 = 年初 + 调整），勾稽核对 B 列有 SUM 公式。
   它们在契约里是 `mode=formula` 字段且被该 table 的 `formula_mask` 覆盖
   （`contracts._parse_table` 的 CS-13 判据），回写时不覆盖。
5. **static-only instrumentation**：payload 走平台一等静态入口
   `excel_instrumentation.build_static_only_instrumentation_payload()`
   （`managed_sheets: []` + 非空 `static_sheets`），本模块只提供入参 ——
   通用构建器 `build_instrumentation_payload_for_sheets()` 拒空 specs 且要行表几何，
   故纯静态走**兄弟通道**而不是放宽它（spec
   workpaper-sync-pure-static-lane-and-combined-workbook-resolution）。
   理由与平台接受该形态的实证见 `build_instrumentation_payload()` 的 docstring。

═══ 改线状态 ═══

canary 宿主 GtA51CashflowAudit.vue 已改线到 sync bridge（useA51SyncMode.ts），
capability 当前 single_onlyoffice。本模块注册 adapter 后升级到 bidirectional。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME
from app.services.workpaper_sync import excel_instrumentation as _xi
from app.services.workpaper_sync import phase5_a51_sheets as _sheets
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    SyncContract,
    contract_path_for,
    load_contract,
    parse_contract,
)
from app.services.workpaper_sync.definitions import (
    canonical_digest,
    validate_instrumentation_payload,
    validate_template_payload,
)
from app.services.workpaper_sync.entry_profile import (
    Capability,
    DescriptorFacts,
    RoomFacts,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    normalized_structure_hash,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    DefinitionKind,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

ENTRY_ID: Final[str] = _sheets.ENTRY_ID
ADAPTER_ID: Final[str] = _sheets.ADAPTER_ID
WP_CODES: Final[frozenset[str]] = _sheets.WP_CODES
TEMPLATE_RELATIVE_PATH: Final[str] = _sheets.TEMPLATE_RELATIVE_PATH
TEMPLATE_SHA256: Final[str] = _sheets.TEMPLATE_SHA256
TEMPLATE_ID: Final[str] = _sheets.TEMPLATE_ID

#: 与交付登记表 `delivered_contracts_ledger` 的 `authority_model` / `pilot_class` 同值。
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
PHASE5_WAVE: Final[str] = "phase5_a51"

#: 纯静态区实际用到的两个 identity 载体（都是 Task 5 探针 `passed`）：
#: `defined_name` 承区域锚点、`hidden_sheet` 承 `_GT_SYNC` 元数据。
#: **不声明** `excel_table` / `hidden_uuid_column` —— 静态区不建 Table、不注 UUID 列，
#: 声明了它们等于宣称有一套本 entry 根本不写的载体。
IDENTITY_CARRIERS: Final[tuple[str, ...]] = ("defined_name", "hidden_sheet")
#: 静态区只用 `defined_name_ref`（`excel_table_sheet_association` 是动态表专用）。
IDENTITY_ANCHORS: Final[tuple[str, ...]] = ("defined_name_ref",)

_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class A51EntryError(Exception):
    """A5-1 选型/注册/投影错误。"""


# ═══════════════════════════════════════════════════════════════════════════
# 2. 模板路径
# ═══════════════════════════════════════════════════════════════════════════


def authoritative_template_path() -> Path:
    return _BACKEND_ROOT / "wp_templates" / TEMPLATE_RELATIVE_PATH


def read_authoritative_template() -> bytes:
    p = authoritative_template_path()
    if not p.exists():
        raise A51EntryError(f"权威模板不存在: {p}")
    return p.read_bytes()


def verify_template_sha256() -> str:
    """验证模板 sha256 并返回。"""
    data = read_authoritative_template()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise A51EntryError(
            f"模板 sha256 不一致: 期望 {TEMPLATE_SHA256[:16]}…, "
            f"实际 {digest[:16]}…"
        )
    return digest


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    """Task 5 真实 OO 9.4 载体 gate（单一真源，本模块不复制裁决）。"""
    return ExcelIdentityCarrierGate.load()


def template_definition_payload() -> dict[str, Any]:
    """template definition 的 canonical payload（发布 DAG 第一段）。

    🔴 **不调** `excel_instrumentation.build_template_payload()`：它要一个
    `ExcelInstrumentationSpec`（行表几何：Table 名 / UUID 列 / footer 行），A5-1 纯静态
    没有也不该有（DEC-3）。故这里手工组装同一批键，并过平台同一个
    `definitions.validate_template_payload()`。键集与 `build_template_payload` 的输出
    **逐字段对齐**（schema_version / template_id / template_relative_path /
    template_sha256 / normalized_structure_hash / authority_root）。

    🔴 `normalized_structure_hash` 是**结构哈希**（`excel_instrumentation.
    normalized_structure_hash(bytes)`），与文件 sha256 是两种不同计算。改造前这里与
    契约的 `template.normalized_structure_hash` / `template_definition_sha256` 三处
    全填了同一个文件 sha256 —— 三个语义不同的字段填同一个值，任一处漂了都看不出来。
    """
    data = read_authoritative_template()
    verify_template_sha256()
    payload = {
        "schema_version": _xi.TEMPLATE_SCHEMA_VERSION,
        "template_id": TEMPLATE_ID,
        "template_relative_path": f"backend/wp_templates/{TEMPLATE_RELATIVE_PATH}",
        "template_sha256": TEMPLATE_SHA256,
        "normalized_structure_hash": normalized_structure_hash(data),
        "authority_root": "backend/wp_templates",
    }
    validate_template_payload(payload)
    return payload


def authority_model_payload() -> dict[str, Any]:
    """authority model definition 的 canonical payload（照 D4 范式）。"""
    return {
        "schema_version": "authority-model-definition:v1",
        "authority_model": AUTHORITY_MODEL.value,
        "content_authority": "structured_projection",
        "merge_model": "stable_field_three_way",
        "required_slots": [
            BundleSlot.template.value,
            BundleSlot.instrumentation.value,
            BundleSlot.contract.value,
        ],
        "entry_id": ENTRY_ID,
        "pilot_class": PHASE5_WAVE,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. 契约构建
# ═══════════════════════════════════════════════════════════════════════════


def _instrumentation_digest() -> str:
    """instrumentation payload 的 canonical digest（用于契约的单向引用）。"""
    return canonical_digest(build_instrumentation_payload())


#: 两张静态受管区的声明（真源在 sheet 层 `static_region_declarations()`）。
_STATIC_REGIONS: Final[tuple[dict[str, Any], ...]] = _sheets.static_region_declarations()
_REGION_AUDIT: Final[dict[str, Any]] = _STATIC_REGIONS[0]
_REGION_RECONCILE: Final[dict[str, Any]] = _STATIC_REGIONS[1]


def _region_boundary_locator(region: Mapping[str, Any]) -> dict[str, Any]:
    """静态受管区的区域锚点（形态照 `phase5_d4_other_margin_sheet` 的 D4-33 范式）。

    `region_kind="static"` 是引擎侧的分派键：`published_identity_observer.
    _frozen_sheet_anchors` 读到它才走 `_collect_static_region_physical`（绝对坐标），
    缺省会被当成 D4-29 那种「列=entity」的转置表。
    """
    return {
        "anchor": "defined_name_ref",
        "defined_name": str(region["defined_name"]),
        "range": str(region["managed_ref"]),
        "region_kind": "static",
    }


def _static_contract_sheet_payload(
    region: Mapping[str, Any], *, fields: list[dict[str, Any]]
) -> dict[str, Any]:
    """契约 `sheets[]` 元素（静态区形态）。

    与改造前的差别：补了 `template_id` / `locator.defined_name` /
    `region_boundary_locator` / `has_dynamic_rows`。改造前 `locator` 只有
    `{"anchor": "defined_name_ref"}` 却**没给 definedName**，`region_boundary_locator`
    整个缺失 ⇒ 声明了「按 definedName 定位」但没说按哪个名字，运行时只能回落到猜。
    """
    return {
        "sheet_key": str(region["sheet_key"]),
        "excel_name": str(region["excel_name"]),
        "template_id": str(region["template_id"]),
        "locator": {
            "anchor": "defined_name_ref",
            "defined_name": str(region["defined_name"]),
        },
        "region_boundary_locator": _region_boundary_locator(region),
        "tables": [
            {
                "table_key": str(region["table_key"]),
                "anchor": f"A{int(region['header_row'])}",
                "header_rows": 1,
                # 🔴 显式 False：A5-1 全固定行。契约层「有无动态行」此前只能由
                #    `row_identity` 缺席**隐式**推出（`TableSpec.has_dynamic_rows` 是
                #    派生属性），磁盘契约里读不到 ⇒ 审阅者分不清「静态」与「漏声明」。
                "has_dynamic_rows": False,
                "formula_mask": list(region["formula_mask"]),
                "fields": fields,
            }
        ],
    }


def static_sheet_payloads() -> tuple[dict[str, Any], ...]:
    """instrumentation `static_sheets` 元素。

    🔴 形态**不在本模块重写**：委派平台的 `_static_sheet_payload_entry()`，与
    `build_static_only_instrumentation_payload()` 用的是同一个形态函数 ⇒ 两处不可能各自漂。
    注入时只写 definedName，不注 Excel Table / UUID 列 / 隐藏行。
    """
    return tuple(
        _xi._static_sheet_payload_entry(region)
        for region in static_only_instrumentation_spec().static_regions
    )


def static_identity_bindings() -> tuple[Any, ...]:
    """每张静态受管区一个 `ExcelIdentityBinding`（静态形态：只有 defined_name）。

    🔴 **不走** `projection_first_publication._static_region_bindings(provider=…)`：
    那个通用生成器从 `provider.instrumentation_specs()` 的各 spec 的 `static_sheets`
    里收（静态区寄生在动态 primary spec 上的挂法）。A5-1 一个 `ExcelInstrumentationSpec`
    都没有（纯静态），它对本 entry 恒返回 `[]` —— 是空分母而不是「没有静态区」。
    故这里照 `phase5_d4_other_margin_sheet.static_binding_d433()` 直接建。
    """
    from app.services.workpaper_sync.excel_extract import ExcelIdentityBinding

    return tuple(
        ExcelIdentityBinding(
            table_key=str(region["table_key"]),
            defined_name=str(region["defined_name"]),
            metadata_sheet=GT_SYNC_SHEET_NAME,
        )
        for region in _STATIC_REGIONS
    )


def build_contract_payload() -> dict[str, Any]:
    """构建 A5-1 的语义契约 JSON payload。

    A5-1 的契约比 D/H 循环简单：
    - 无动态行（全固定布局）
    - 5 张受管 sheet，每张有一组固定 cell 映射
    - 公式 cell 标为 protected（回写不覆盖）
    """
    sheets = []

    # Sheet 1: 审定表 A5-1-1
    # 🔴 column_key 是**语义键**（snake_case），不是 Excel 列标；
    #    Excel 列位置在 cell.column。
    audit_fields = []
    for suffix, col, row, mode, desc in _sheets.AUDIT_FIELD_MAP:
        # suffix 形如 "1.unadjusted" → 语义键 "row1_unadjusted"
        row_no, field_name = suffix.split(".", 1)
        audit_fields.append({
            "stable_field_key": f"a51-audit-{suffix}",
            "json_pointer": f"/a51-audit-{suffix}",
            "mode": mode,
            "value_type": "amount" if field_name in ("unadjusted", "adjustment") else "text",
            "source_ref": f"{_sheets.MANAGED_SHEET_AUDIT}!{col}{row}",
            "row_scoped": False,
            "column_key": f"row{row_no}_{field_name}",
            "cell": {"column": col, "row_from": row, "static_row": row},
        })

    # 公式 cell 作为 protected field
    for col, row, formula in _sheets.AUDIT_FORMULA_CELLS:
        audit_fields.append({
            "stable_field_key": f"a51-audit-formula-{col.lower()}{row}",
            "json_pointer": f"/a51-audit-formula-{col.lower()}{row}",
            "mode": "formula",
            "value_type": "amount",
            "source_ref": f"{_sheets.MANAGED_SHEET_AUDIT}!{col}{row}",
            "row_scoped": False,
            "column_key": f"audit_formula_{col.lower()}{row}",
            "cell": {"column": col, "row_from": row, "static_row": row},
        })

    sheets.append(_static_contract_sheet_payload(_REGION_AUDIT, fields=audit_fields))

    # Sheet 2: 勾稽核对 A5-1-3
    reconcile_fields = []
    for col, row, formula in _sheets.RECONCILE_FORMULA_CELLS:
        reconcile_fields.append({
            "stable_field_key": f"a51-reconcile-formula-{col.lower()}{row}",
            "json_pointer": f"/a51-reconcile-formula-{col.lower()}{row}",
            "mode": "formula",
            "value_type": "amount",
            "source_ref": f"{_sheets.MANAGED_SHEET_RECONCILE}!{col}{row}",
            "row_scoped": False,
            "column_key": f"reconcile_formula_{col.lower()}{row}",
            "cell": {"column": col, "row_from": row, "static_row": row},
        })

    sheets.append(
        _static_contract_sheet_payload(_REGION_RECONCILE, fields=reconcile_fields)
    )

    template_payload = template_definition_payload()
    payload = {
        "schema_version": "contract-definition:v1",
        "contract_id": ADAPTER_ID,
        "semantic_version": "1.0.0",
        "document_type": "xlsx",
        # 🔴 reviewed：A5-1 册已逐格 openpyxl 实测（9 sheets / 57 公式格 / 22 definedName），
        #    审定表 24 个 editable cell 与勾稽核对 7 个公式 cell 的映射由实测确认。
        "review_status": "reviewed",
        "template": {
            "relative_path": TEMPLATE_RELATIVE_PATH,
            "template_sha256": TEMPLATE_SHA256,
            # 🔴 真结构哈希（`normalized_structure_hash(bytes)`），**不是**文件 sha256。
            "normalized_structure_hash": template_payload["normalized_structure_hash"],
        },
        # 🔴 已发布 template definition 的 canonical digest（**不是**文件 sha256）——
        #    `publish_definitions()` 会断言二者相等，脱钩即单向引用断裂。
        "template_definition_sha256": canonical_digest(template_payload),
        "instrumentation_definition_sha256": _instrumentation_digest(),
        # 🔴 A5-1 是固定布局（无动态行/无 UUID 列）⇒ 载体是隐藏 sheet + definedName。
        #    册内实测有 GT_Custom 隐藏 sheet 与 22 个 definedName。
        "identity_carriers": ["hidden_sheet", "defined_name"],
        "sheets": sheets,
        "note": (
            "A5-1 现金流量表审计——扁平键值对型契约（非行表型）。"
            "5 张受管 sheet 全固定行、0 个动态行表 ⇒ 受管区走 workbook-scope "
            "definedName 锚点（region_kind=static），不建 Excel Table / UUID 列"
            "（归档 spec workpaper-sync-static-cell-sheet-writeback 的 DEC-3）。"
            "审定表公式列 G 和勾稽核对公式列 B 标为 protected，回写不覆盖。"
            "A 类底稿无 TB 发布门（AC-3 空分母裁定）。"
        ),
    }
    return payload


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    return load_contract(ADAPTER_ID)


def write_contract_to_disk() -> Path:
    """构建契约 payload 并写入磁盘（canonical JSON 字节）。

    🔴 字节格式由 `test_platform_contract_disk_byte_stability` 钉死：
    LF 换行（禁 CRLF）+ `json.dumps(ensure_ascii=False, indent=2, sort_keys=True)` + 末尾 `\\n`。
    用 `write_bytes` 而非 `write_text`——后者在 Windows 上会把 `\\n` 变成 `\\r\\n`。
    """
    payload = build_contract_payload()
    path = contract_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    canonical = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.write_bytes(canonical)
    return path


def assert_contract_file_matches_source() -> SyncContract:
    """磁盘契约 ↔ 本模块现算 payload **双向**锁死（照 D4 范式）。

    `load_projection_supply(...).contract` 就走这个函数 —— 它是
    `review_status != reviewed` 的单点拒绝处（经 `contracts.parse_contract`）。
    """
    expected = build_contract_payload()
    on_disk = load_contract_from_disk()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise A51EntryError(
            "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} "
            f"source={canonical_digest(expected)}；"
            "请调 `phase5_a51_cashflow_audit.write_contract_to_disk()` 重新落盘"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 4. Store 投影 / 合并（扁平键值对型）
# ═══════════════════════════════════════════════════════════════════════════


def build_store_projection(
    responses: Mapping[str, str],
    *,
    contract: SyncContract | None = None,
) -> dict[str, Any]:
    """HTML store (checklist_responses 键值对) → Excel cell 投影。

    遍历 AUDIT_FIELD_MAP 中的 editable 字段，生成 {sheet_key: {cell_ref: value}} 形态。
    """
    projection: dict[str, dict[str, Any]] = {}

    # 审定表
    audit_cells: dict[str, Any] = {}
    for suffix, col, row, mode, _desc in _sheets.AUDIT_FIELD_MAP:
        if mode != "editable":
            continue
        item_id = f"a51-audit-{suffix}"
        value = responses.get(item_id, "")
        if value:
            audit_cells[f"{col}{row}"] = value
    if audit_cells:
        projection[_sheets.SHEET_KEY_AUDIT] = audit_cells

    return {
        "entry_id": ENTRY_ID,
        "sheets": projection,
    }


def merge_projection_into_responses(
    *,
    projection: dict[str, Any],
    base_responses: dict[str, str],
) -> dict[str, str]:
    """Excel cell 投影 → HTML store (checklist_responses) 合并。

    从投影的 {sheet_key: {cell_ref: value}} 中提取值，写回 base_responses。
    """
    result = dict(base_responses)
    sheets = projection.get("sheets", {})

    # 审定表
    audit_cells = sheets.get(_sheets.SHEET_KEY_AUDIT, {})
    for suffix, col, row, mode, _desc in _sheets.AUDIT_FIELD_MAP:
        if mode != "editable":
            continue
        cell_ref = f"{col}{row}"
        if cell_ref in audit_cells:
            item_id = f"a51-audit-{suffix}"
            result[item_id] = str(audit_cells[cell_ref])

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 5. Excel Instrumentation（受管 cell + 公式保护）
# ═══════════════════════════════════════════════════════════════════════════


def static_only_instrumentation_spec() -> _xi.ExcelStaticOnlyInstrumentationSpec:
    """本 entry 的**纯静态** instrumentation 声明（平台第三条分派臂的入口）。

    🔴 刻意**不叫** `instrumentation_spec` / `instrumentation_specs`：那两个名字的类型是
    `ExcelInstrumentationSpec`（行表几何），A5-1 一个都没有也不该有（DEC-3）。
    `stage_instrumented_substrate` 的第三臂按本名字取，且在进入第三臂前 fail-closed
    断言「有 static_only 即不得有行表 spec」。

    区声明的真源在 sheet 层 `static_region_declarations()`，本函数只做类型转换 ——
    三处消费方（契约 / instrumentation / binding）读同一份声明。
    """
    return _xi.ExcelStaticOnlyInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=TEMPLATE_ID,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        static_regions=tuple(
            _xi.StaticRegionSpec(
                sheet_key=str(region["sheet_key"]),
                excel_name=str(region["excel_name"]),
                template_id=str(region["template_id"]),
                defined_name=str(region["defined_name"]),
                managed_ref=str(region["managed_ref"]),
                table_key=str(region["table_key"]),
            )
            for region in _STATIC_REGIONS
        ),
    )


def build_instrumentation_payload() -> dict[str, Any]:
    """instrumentation definition 的 canonical payload —— **委派平台 static-only 入口**。

    ═══ 本函数曾是一份自组装，现在是门面 ═══

    改造前这里手工拼了整份 static-only payload，理由是平台通用构建器
    `build_instrumentation_payload_for_sheets()` 第一行就是 `if not specs: raise` ——
    它要至少一个 `ExcelInstrumentationSpec`（行表几何），而 A5-1 纯静态没有这些，
    归档 spec `workpaper-sync-static-cell-sheet-writeback` 的 **DEC-3 明确否决**
    「给纯静态 sheet 注入退化动态表当载体」。

    平台现已有一等的静态通道
    （`excel_instrumentation.build_static_only_instrumentation_payload`），故本函数
    收缩为**委派门面**：形态与差异点全部由平台表达，本模块只提供入参。

    🔴 上提是**纯重构**：`canonical_digest(本函数输出)` 与改造前逐位相等
    （该 digest 已 `approved` 落库，同时出现在契约的
    `instrumentation_definition_sha256`、守卫常量 `CANARY_INSTRUMENTATION_DEFINITION_SHA256`
    与真库 artifact 行三处）。不相等时只能修平台构建器，**禁**改契约 / 守卫常量 /
    真库 artifact 去迁就。

    ═══ 为什么 `managed_sheets` 是空的 ═══

    空的**不是**缺声明：A5-1 是 `review_status == "reviewed"` 分母下**唯一**一份
    「整个 entry 无任何动态行表」的契约（该分母与成员一律**现算** ——
    `backend/data/workpaper_sync_contracts/*.json` 里 `review_status == "reviewed"` 的
    份数 × 其中 `sheets[].tables[].row_identity` 全为 `None` 的份数）。改造前此处写死了
    一个分母快照，那个数字在写入之后就过期了 ⇒ 现已改成现算口径描述，**不再写死分母数字**。
    受管面全在 `static_sheets`。
    """
    return _xi.build_static_only_instrumentation_payload(
        spec=static_only_instrumentation_spec(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
        identity_carriers=IDENTITY_CARRIERS,
        identity_anchors=IDENTITY_ANCHORS,
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    """发布链用的门面（与 D4/H 循环 provider 同名，便于通用守卫按名取）。"""
    return build_instrumentation_payload()


# ═══════════════════════════════════════════════════════════════════════════
# 5b. 发布链（authority → template → instrumentation → contract → bundle）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Phase5Definitions:
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    template_definition_id: uuid.UUID
    template_definition_sha256: str
    instrumentation_definition_id: uuid.UUID
    instrumentation_definition_sha256: str
    contract_definition_id: uuid.UUID
    contract_definition_sha256: str
    bundle_id: uuid.UUID
    bundle_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": ENTRY_ID,
            "adapter_id": ADAPTER_ID,
            "authority_model": AUTHORITY_MODEL.value,
            "authority_model_definition_id": str(self.authority_model_definition_id),
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "template_definition_id": str(self.template_definition_id),
            "template_definition_sha256": self.template_definition_sha256,
            "instrumentation_definition_id": str(self.instrumentation_definition_id),
            "instrumentation_definition_sha256": self.instrumentation_definition_sha256,
            "contract_definition_id": str(self.contract_definition_id),
            "contract_definition_sha256": self.contract_definition_sha256,
            "definition_bundle_id": str(self.bundle_id),
            "definition_bundle_sha256": self.bundle_sha256,
        }


async def publish_definitions(publisher: Any) -> Phase5Definitions:
    """发布 DAG 固定序：authority → template → instrumentation → contract → bundle。

    形态与 `phase5_d4_revenue_detail.publish_definitions` 逐段对齐（含两条单向引用
    断言）。唯一差别是 template / instrumentation payload 由本模块手工组装（纯静态无
    `ExcelInstrumentationSpec`，见各自 docstring）。
    """
    contract = assert_contract_file_matches_source()
    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(),
        logical_id=f"{ADAPTER_ID}.authority-model",
        semantic_version="1.0.0",
    )
    template_payload = template_definition_payload()
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=template_payload,
        logical_id=f"{ADAPTER_ID}.template",
        semantic_version="1.0.0",
        blob_bytes=read_authoritative_template(),
        structure_hash=template_payload["normalized_structure_hash"],
    )
    instrumentation = await publisher.publish_definition(
        kind=DefinitionKind.instrumentation,
        payload=instrumentation_definition_payload(),
        logical_id=f"{ADAPTER_ID}.instrumentation",
        semantic_version="1.0.0",
    )
    contract_definition = await publisher.publish_definition(
        kind=DefinitionKind.contract,
        payload=dict(contract.canonical_payload),
        logical_id=ADAPTER_ID,
        semantic_version=contract.semantic_version,
    )
    if template.sha256 != contract.template_definition_sha256:
        raise A51EntryError(
            f"已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        raise A51EntryError(
            f"已发布 instrumentation digest {instrumentation.sha256} 与契约声明 "
            f"{contract.instrumentation_definition_sha256} 不一致 —— 单向引用断裂"
        )
    bundle = await publisher.publish_bundle(
        authority_model_definition_id=authority.definition_id,
        authority_model=AUTHORITY_MODEL,
        authority_model_definition_sha256=authority.sha256,
        slots={
            BundleSlot.template: {
                "type": "definition",
                "ref": f"definition:{template.definition_id}",
                "digest": template.sha256,
            },
            BundleSlot.instrumentation: {
                "type": "definition",
                "ref": f"definition:{instrumentation.definition_id}",
                "digest": instrumentation.sha256,
            },
            BundleSlot.contract: {
                "type": "definition",
                "ref": f"definition:{contract_definition.definition_id}",
                "digest": contract_definition.sha256,
            },
        },
    )
    return Phase5Definitions(
        authority_model_definition_id=authority.definition_id,
        authority_model_definition_sha256=authority.sha256,
        template_definition_id=template.definition_id,
        template_definition_sha256=template.sha256,
        instrumentation_definition_id=instrumentation.definition_id,
        instrumentation_definition_sha256=instrumentation.sha256,
        contract_definition_id=contract_definition.definition_id,
        contract_definition_sha256=contract_definition.sha256,
        bundle_id=bundle.bundle_id,
        bundle_sha256=bundle.canonical_sha256,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. Matcher / Registration
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)


def manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None,
) -> bool:
    """检查 manifest 是否启用了 A5-1 的双向回写。"""
    m = manifest or load_entry_manifest()
    entries = manifest_entries_by_id(m)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        return False
    # capability 非 null 且非 unreachable 即为启用
    cap = entry.get("capability")
    return cap is not None and cap != "unreachable"


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return AdapterRegistration(
        adapter=adapter,
        entry_id=ENTRY_ID,
        matcher=build_matcher(),
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        declared_capability=Capability.bidirectional,
        contract=contract if contract is not None else load_contract_from_disk(),
    )


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    registration = build_registration(
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
    )
    registry.register(registration)
    return registration


# ═══════════════════════════════════════════════════════════════════════════
# 7. 启动链入口（registry 调用）
# ═══════════════════════════════════════════════════════════════════════════


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None,
) -> None:
    if not manifest_capability_enabled(manifest=manifest):
        raise A51EntryError(
            f"entry {ENTRY_ID} 在 manifest 中未启用双向回写能力"
        )


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """观测已发布的冻结定义（与 H 循环同一真源）。"""
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(
            session, CanonicalArtifactRepository(_BACKEND_ROOT)
        ),
        representation=representation,
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise A51EntryError(
            f"entry {ENTRY_ID}: 观测器读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} 与本模块 source-locked 的 "
            f"{contract.canonical_sha256} 不一致 —— 冻结身份与生产契约脱钩"
        )
    return observation


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """启动链入口：注册 A5-1 adapter。

    🔴 形态与 `phase5_h_cycle_common.attach_h_entry_adapter` 逐字对齐 ——
    第③环（published representation）缺供给时**返回空元组**而不是伪造通过，
    BP-1~BP-3 是平台级欠账，如实登记为 `upstream_gap`。

    🔴 **已知下游欠账（平台级，代码现读所得，未在此绕开）**：
    `published_identity_observer._build_identity_binding()` 只有动态路径 —— 它先求
    「契约里带 `row_identity` 的表」，为空即抛
    `FrozenChildUnusableError("契约未声明任何带 row_identity 的表 —— 隐藏 UUID 列无从绑定")`，
    随后又取 `anchors["table_name"]` / `anchors["uuid_column_letter"]`，而静态锚点
    （`_frozen_sheet_anchors` 的 `static_sheets` 支）只带 `sheet_key` / `defined_name` /
    `anchor` / `region_kind` 三四项，没有这两个键。
    ⇒ 纯静态 entry 走到观测器的**主 binding** 构造时必失败。
    本模块**不**为了绕开它而在契约里编一个退化 `row_identity` 表（DEC-3 明确否决），
    修法应是给观测器补一条静态主 binding 分支（`region_kind == "static"` → 用
    `defined_name` 建 binding，`table_key` 取该 sheet 的静态表 key），属平台改动。
    静态区自身的 binding 形态本模块已备好（见 `static_identity_bindings()`）。
    """
    if ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    representation_id = await resolve_visible_current_representation_id(
        session, entry_id=ENTRY_ID
    )
    if representation_id is None:
        return ()
    representation = (
        await session.execute(
            sa.select(WorkpaperContentRepresentation).where(
                WorkpaperContentRepresentation.id == representation_id
            )
        )
    ).scalar_one_or_none()
    if representation is None or representation.definition_bundle_id is None:
        return ()

    resolution = CanonicalResolutionService(
        session, CanonicalArtifactRepository(_BACKEND_ROOT)
    )
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = load_contract_from_disk()
    entry = manifest_entries_by_id(load_entry_manifest()).get(ENTRY_ID)
    if entry is None:
        return ()
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise A51EntryError(f"entry {ENTRY_ID} 的宿主实测不可达（产不出 descriptor 事实）")
    observation = await resolve_published_frozen_definitions(
        session=session, representation=representation, contract=contract
    )
    # 静态受管区 binding：主 binding 由观测器给出，其余静态区进 sibling_bindings
    # （形态照 `phase5_d4_other_margin_sheet.static_binding_d433()`；A5-1 没有
    #  `instrumentation_specs()`，故通用生成器 `_static_region_bindings` 对本 entry
    #  是空分母，见 `static_identity_bindings()` 的说明）。
    primary_table_key = getattr(observation.identity_binding, "table_key", None)
    sibling_bindings = tuple(
        binding
        for binding in static_identity_bindings()
        if binding.table_key != primary_table_key
    )
    register_adapter(
        registry,
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding,
            direction="html_to_oo",
            sibling_bindings=sibling_bindings,
        ),
        bundle=bundle,
        descriptor=descriptor,
        room=facts.observe_room_facts(entry),
        contract=contract,
    )
    return (ADAPTER_ID,)


# ═══════════════════════════════════════════════════════════════════════════
# 8. 统一别名（平台通用守卫 / provisioning 按这些名字取）
# ═══════════════════════════════════════════════════════════════════════════
#
# 形态照 `phase5_d1_notes_receivable` 结尾：`projection_provisioning.
# load_projection_supply()` 硬要求 provider 有可调用的 `publish_pilot_definitions` 与
# `assert_contract_file_matches_source`；`fix_task76_provision_projection_definitions.py`
# 也按 `publish_pilot_definitions` 调发布链。`attach_pilot_adapters` 已在上面定义。

publish_pilot_definitions = publish_definitions
PILOT_WP_CODES = WP_CODES
