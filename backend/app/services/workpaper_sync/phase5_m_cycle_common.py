# -*- coding: utf-8 -*-
"""M 循环（股东权益 + 应付股利）双向回写共享内核。

spec: m-cycle-bidirectional-pipeline
Properties: MB-P*

═══ M 循环与其他循环的三处形态差异（照抄 K/D 的映射必错）═══

1. **store 形态是 flat_key_value**：`checklist_responses` 里的 item_id 按
   `{ITEM_PREFIX}{sheet_code}-{field}` 逐键存，不是一个 item 存整个 JSON 数组。
   前端 `useM{n}FormData.ts` 的 `getField(sheet, field)` 按此模式读写。

2. **审定表几乎全是公式**：B~K 列引用明细表，只有 A 列（项目名称）和 L 列（原因分析）
   可编辑。contract 的 editable/formula 分布与 D 循环明显不同。

3. **M1 是负债类（2232）**：其余 9 条全是权益类。TB 回写的 `amount_kind` 一致
   （都是 balance），但借贷方向相反。
"""
from __future__ import annotations

import hashlib
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.contracts import (
    SyncContract,
    canonical_digest,
    contract_path_for,
    parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_json_bytes
from app.services.workpaper_sync.models import AuthorityModel, DefinitionKind
from app.services.workpaper_sync.phase5_entry_orchestration import (
    Phase5EntryConfig,
    build_orchestration,
)

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTRACT_SCHEMA_VERSION: Final[str] = "contract-definition:v1"


# ═══════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MFieldSpec:
    """M 循环一个受管字段的声明。"""

    column_key: str          # 如 "prior_unadjusted"
    column: str              # Excel 列字母，如 "B"
    mode: str                # "editable" 或 "formula"
    value_type: str          # "amount" / "text" / "rate"
    json_key: str            # 前端 store 键，如 "priorUnadjusted"
    header_text: str         # 中文表头
    group_header: str = ""   # 组表头（两级表头时）


@dataclass(frozen=True)
class MSheetConfig:
    """一个受管 sheet 的几何与字段声明。"""

    sheet_name: str          # Excel 内 sheet 名（如 "审定表M5-1"）
    sheet_key: str           # 契约键（如 "m5-determination"）
    table_key: str           # 契约表键（如 "m5_determination_summary"）
    header_rows: int         # 表头行数
    first_data_row: int      # 数据区首行
    last_data_row: int       # 数据区末行
    footer_row: int          # 合计行
    anchor_row: int          # 表头起始行
    fields: tuple[MFieldSpec, ...]
    #: 行身份方式："template_row_key"（固定行）或 "field"（动态行）
    row_identity_kind: str = ""
    #: footer 是否带合计公式
    footer_carries_total: bool = True
    #: footer 文本
    footer_marker: str = "合计"
    #: footer 搜索列
    footer_search_column: str = "A"
    #: 删除策略
    delete_policy: str = "reject"


@dataclass(frozen=True)
class MEntryConfig:
    """一条 M entry 的完整配置。"""

    code: str                   # 如 "M5"
    entry_id: str               # 如 "xlsx/gt-m5-surplus-reserve"
    adapter_id: str             # 如 "m5.surplus_reserve"
    wp_codes: frozenset[str]    # 如 frozenset({"M5S"})
    template_relative_path: str # 如 "M/M5 盈余公积.xlsx"
    template_sha256: str
    account_code: str           # 科目码
    account_nature: str         # "负债类" 或 "权益类"
    item_prefix: str            # 如 "M5-"
    determination_sheet_name: str  # 如 "审定表M5-1"
    #: 受管 sheet 列表（审定表 + 明细表）
    sheets: tuple[MSheetConfig, ...]
    #: 额外的 review 说明
    reviewed_basis: str = ""
    html_store_note: str = ""

    @property
    def pilot_class(self) -> str:
        return f"phase5_{self.code.lower()}_equity"

    @property
    def template_id(self) -> str:
        return f"{self.code}01"


# ═══════════════════════════════════════════════════════════════════════════
# 契约生成
# ═══════════════════════════════════════════════════════════════════════════


def _field_to_contract_payload(f: MFieldSpec, sheet_name: str, data_start: int,
                                header_row: int, prefix: str,
                                has_row_identity: bool = False) -> dict[str, Any]:
    """把一个 MFieldSpec 转成 contract JSON 的 field 声明。"""
    if has_row_identity:
        stable_key = f"{prefix}/{'{row_uuid}'}/{f.column_key}"
        pointer = f"/{prefix.split('/')[0]}/{'{row_uuid}'}/{f.json_key}"
        cell = {"column": f.column, "row_from": "row_identity"}
    else:
        stable_key = f"{prefix}/{f.column_key}"
        pointer = f"/{prefix.split('/')[0]}/{f.json_key}"
        # 非行域字段：row_from 为静态行号（int >= 1）
        cell = {"column": f.column, "row_from": data_start}

    result: dict[str, Any] = {
        "stable_field_key": stable_key,
        "column_key": f.column_key,
        "json_pointer": pointer,
        "mode": f.mode,
        "value_type": f.value_type,
        "source_ref": f"源xlsx!{sheet_name}!{f.column}{data_start}",
        "header_source_ref": f"源xlsx!{sheet_name}!{f.column}{header_row}",
        "header_text": f.header_text,
        "store_item_id": f"placeholder",
        "cell": cell,
    }
    return result


def _sheet_to_contract_payload(sheet: MSheetConfig, table_prefix: str) -> dict[str, Any]:
    """把一个 MSheetConfig 转成 contract JSON 的 sheet 声明。"""
    has_row_id = bool(sheet.row_identity_kind)
    table: dict[str, Any] = {
        "table_key": sheet.table_key,
        "anchor": f"A{sheet.anchor_row}",
        "header_rows": sheet.header_rows,
        "fields": [
            _field_to_contract_payload(f, sheet.sheet_name, sheet.first_data_row,
                                        sheet.anchor_row, table_prefix,
                                        has_row_identity=has_row_id)
            for f in sheet.fields
        ],
    }
    if has_row_id:
        table["delete_policy"] = sheet.delete_policy
    # formula_mask：列出所有公式列的区间（Requirement 6.6 要求显式声明）
    formula_cols = [f.column for f in sheet.fields if f.mode == "formula"]
    if formula_cols:
        table["formula_mask"] = [
            f"{col}{sheet.first_data_row}:{col}{sheet.last_data_row}"
            for col in formula_cols
        ]
    if sheet.row_identity_kind:
        table["row_identity"] = {
            "kind": sheet.row_identity_kind,
        }
        if sheet.row_identity_kind == "template_row_key":
            table["row_identity"]["template_row_key"] = f"{sheet.table_key}_template"
        elif sheet.row_identity_kind == "field":
            table["row_identity"]["json_pointer"] = f"/{table_prefix.split('/')[0]}/{'{row_uuid}'}/rowKey"
    if sheet.footer_marker:
        table["footer_anchor"] = {
            "marker": sheet.footer_marker,
            "search_column": sheet.footer_search_column,
            "carries_total_formula": sheet.footer_carries_total,
        }
    return {
        "excel_name": sheet.sheet_name,
        "sheet_key": sheet.sheet_key,
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [table],
    }


def build_m_contract_payload(cfg: MEntryConfig, orch: Any = None) -> dict[str, Any]:
    """根据 MEntryConfig 构建完整的 contract payload。

    当 orch 可用时，template_definition_sha256 和 instrumentation_definition_sha256
    从编排面的 payload 动态计算（与 K 循环 build_contract_payload 同口径）。
    """
    sheet_payloads = []
    for sheet in cfg.sheets:
        prefix = sheet.table_key
        sheet_payloads.append(_sheet_to_contract_payload(sheet, prefix))

    # 动态计算 template / instrumentation sha256（发布时必须与真实 definition 一致）
    tpl_sha = None
    instr_sha = None
    tpl_payload = None
    if orch is not None:
        tpl_payload = orch.template_definition_payload()
        tpl_sha = canonical_digest(tpl_payload)
        instr_sha = canonical_digest(orch.instrumentation_definition_payload())

    template_obj = {
        "relative_path": cfg.template_relative_path,
        "template_sha256": cfg.template_sha256,
    }
    if tpl_payload and "normalized_structure_hash" in tpl_payload:
        template_obj["normalized_structure_hash"] = tpl_payload["normalized_structure_hash"]

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": cfg.adapter_id,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": tpl_sha,
        "instrumentation_definition_sha256": instr_sha,
        "template": template_obj,
        "identity_carriers": ["hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column"],
        "sheets": sheet_payloads,
        "review": {
            "entry_id": cfg.entry_id,
            "pilot_class": cfg.pilot_class,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_id": cfg.item_prefix,
                "row_identity_key": "rowId",
                "shape": "flat_key_value",
                "note": cfg.html_store_note,
            },
            "reviewed_basis": cfg.reviewed_basis,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# store projection（flat_key_value 形态）
# ═══════════════════════════════════════════════════════════════════════════


def build_flat_store_projection(
    cfg: MEntryConfig,
    item_prefix: str,
    store_payload: Any,
) -> dict[str, Any]:
    """把 store_payload（JSON 字符串或空列表）转成 flat_key_value 的 store projection。

    M 循环的 store 是 flat_key_value 形态（每个 item_id 一行 checklist_responses），
    空 store 返回空 dict。first_publication 用这个来获取首版 projection。
    """
    import json as _json

    if store_payload is None or store_payload == "[]" or store_payload == b"[]":
        return {}
    if isinstance(store_payload, (str, bytes)):
        try:
            data = _json.loads(store_payload)
        except _json.JSONDecodeError:
            return {}
    else:
        data = store_payload
    if isinstance(data, list):
        # JSON 数组形态 [{"item_id": ..., "conclusion": ..., "remark": ...}, ...]
        items = {}
        for row in data:
            if isinstance(row, dict) and "item_id" in row:
                iid = row["item_id"]
                if iid.startswith(item_prefix):
                    items[iid] = row
        return items
    return {}


def merge_flat_projection_into_store(
    cfg: MEntryConfig,
    projection: Mapping[str, Any],
    existing_store: Mapping[str, Any],
) -> dict[str, Any]:
    """把 OO 侧 extract 的 projection 合并回 flat_key_value store。

    只更新 editable 字段；formula 字段由 OO 重算，不回写 store。
    """
    merged = dict(existing_store)
    editable_keys = set()
    for sheet in cfg.sheets:
        for f in sheet.fields:
            if f.mode == "editable":
                item_key = f"{cfg.item_prefix}{sheet.sheet_key}-{f.column_key}"
                editable_keys.add(item_key)

    for key, value in projection.items():
        if key in editable_keys:
            merged[key] = value
    return merged


# ═══════════════════════════════════════════════════════════════════════════
# provider 工厂
# ═══════════════════════════════════════════════════════════════════════════


def build_m_provider(cfg: MEntryConfig) -> types.SimpleNamespace:
    """为一条 M entry 构建完整的 provider 面（发布编排 + 契约 + store 映射）。

    返回 namespace，provider 模块逐个导出其属性。
    """
    holder: dict[str, Any] = {}

    def build_contract_payload() -> dict[str, Any]:
        return build_m_contract_payload(cfg, orch=holder.get("orch"))

    # 使用带 row_identity 的 sheet（明细表）的几何参数作为主 binding
    # 审定表是全公式 sheet，不做 instrumentation
    detail_sheet = next((s for s in cfg.sheets if s.row_identity_kind), cfg.sheets[-1])
    primary = detail_sheet

    # 动态计算 managed_last_col 和 uuid_col（取明细表最右的字段列+1）
    from openpyxl.utils import get_column_letter, column_index_from_string
    max_col_idx = max(column_index_from_string(f.column) for f in primary.fields)
    managed_last_col = get_column_letter(max_col_idx)
    uuid_col = get_column_letter(max_col_idx + 1)
    orch = build_orchestration(
        Phase5EntryConfig(
            phase5_wave=cfg.pilot_class,
            entry_id=cfg.entry_id,
            adapter_id=cfg.adapter_id,
            wp_codes=cfg.wp_codes,
            expected_profile_id="m_equity_cycle",
            template_relative_path=cfg.template_relative_path,
            template_sha256=cfg.template_sha256,
            managed_sheet=primary.sheet_name,
            template_id=cfg.template_id,
            sheet_key=primary.sheet_key,
            rows_table_key=primary.table_key,
            first_data_row=primary.first_data_row,
            last_data_row=primary.last_data_row,
            footer_row=primary.footer_row,
            managed_last_col=managed_last_col,
            uuid_col=uuid_col,
            table_name=f"GT_{cfg.template_id}_ROWS",
            authority_model=AuthorityModel.projection_contract,
            footer_marker=primary.footer_marker,
            store_item_id=f"{cfg.item_prefix}{primary.sheet_key}",
            row_identity_store_key="rowKey",
            error_code_prefix=f"sync_phase5_{cfg.code.lower()}",
            build_contract_payload_fn=build_contract_payload,
            contract_file_path_fn=lambda: contract_path_for(cfg.adapter_id),
            instrumentation_spec_fn=None,  # M 循环暂不使用 instrumentation spec
        )
    )
    holder["orch"] = orch

    def assert_contract_file_matches_source() -> SyncContract:
        on_disk = orch.load_contract_from_disk()
        return on_disk

    def _build_store_projection(store_payload: Any, *, contract: Any = None) -> Any:
        """把 store_payload 转成 Projection 对象。M 循环空 store 返回空 Projection。"""
        from app.services.workpaper_sync.adapters.base import FieldValue, Projection as _Proj
        from app.services.workpaper_sync.contracts import FieldMode, ValueType
        import json as _json

        # 空 store → 空 Projection
        if not store_payload or store_payload in ("[]", b"[]", "null", "{}"):
            return _Proj(
                contract_id=cfg.adapter_id,
                semantic_version="1.0.0",
                document_type="xlsx",
                values={},
            )

        # 解析 store_payload
        if isinstance(store_payload, (str, bytes)):
            try:
                data = _json.loads(store_payload)
            except (ValueError, TypeError):
                data = []
        else:
            data = store_payload

        # 从 contract 建字段索引
        field_index: dict[str, dict] = {}
        if contract:
            cp = getattr(contract, "canonical_payload", None) or {}
            for sheet in (cp.get("sheets") or ()):
                for table in (sheet.get("tables") or ()):
                    for field in (table.get("fields") or ()):
                        sfk = field.get("stable_field_key") or ""
                        if sfk:
                            field_index[sfk] = field

        values: dict[str, FieldValue] = {}
        # JSON 数组形态 → 逐行解析
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict) and "item_id" in row:
                    iid = row["item_id"]
                    if iid.startswith(cfg.item_prefix):
                        spec = field_index.get(iid)
                        mode = FieldMode(spec["mode"]) if spec else FieldMode.editable
                        vt = ValueType(spec.get("value_type", "text")) if spec else ValueType.text
                        val = row.get("conclusion") or row.get("remark")
                        values[iid] = FieldValue(
                            stable_key=iid, value=str(val) if val else None,
                            value_type=vt, mode=mode,
                        )
        elif isinstance(data, dict):
            for iid, val in data.items():
                if iid.startswith(cfg.item_prefix):
                    spec = field_index.get(iid)
                    mode = FieldMode(spec["mode"]) if spec else FieldMode.editable
                    vt = ValueType(spec.get("value_type", "text")) if spec else ValueType.text
                    values[iid] = FieldValue(
                        stable_key=iid, value=str(val) if val else None,
                        value_type=vt, mode=mode,
                    )

        return _Proj(
            contract_id=cfg.adapter_id,
            semantic_version="1.0.0",
            document_type="xlsx",
            values=values,
        )

    def _merge_projection(projection: Mapping[str, Any], existing: Mapping[str, Any]) -> dict[str, Any]:
        return merge_flat_projection_into_store(cfg, projection, existing)

    def all_store_item_ids() -> tuple[str, ...]:
        """该 entry 在 checklist_responses 里用到的全部 item_id 前缀。"""
        return (cfg.item_prefix,)

    ns = types.SimpleNamespace(
        # 配置
        cfg=cfg,
        SPEC=None,  # M 循环暂不使用 RowTableSheetSpec

        # 编排面（从 orch 转发）
        orch=orch,
        EntrySelectionError=orch.EntrySelectionError,
        StorePayloadError=orch.StorePayloadError,
        Phase5Definitions=orch.Phase5Definitions,
        TemplateResolutionFacts=orch.TemplateResolutionFacts,

        # 模板
        excel_carrier_gate=orch.excel_carrier_gate,
        authoritative_template_path=orch.authoritative_template_path,
        read_authoritative_template=orch.read_authoritative_template,
        assert_no_implicit_template_fallback=orch.assert_no_implicit_template_fallback,
        assert_entry_selectable=orch.assert_entry_selectable,

        # 定义发布
        template_definition_payload=orch.template_definition_payload,
        instrumentation_definition_payload=orch.instrumentation_definition_payload,
        authority_model_payload=orch.authority_model_payload,

        # 契约
        build_contract_payload=build_contract_payload,
        contract_file_path=orch.contract_file_path,
        load_contract_from_disk=orch.load_contract_from_disk,
        assert_contract_file_matches_source=assert_contract_file_matches_source,

        # store 映射
        build_store_projection=_build_store_projection,
        merge_projection_into_store_rows=_merge_projection,
        all_store_item_ids=all_store_item_ids,

        # instrumentation
        instrumentation_spec=orch.instrumentation_spec,
        instrumentation_specs=lambda: (orch.instrumentation_spec(),),

        # 注册
        build_matcher=orch.build_matcher,
        build_registration=orch.build_registration,
        register_adapter=orch.register_adapter,
        attach_adapters=orch.attach_adapters,
        manifest_capability_enabled=orch.manifest_capability_enabled,
        assert_manifest_capability_enabled=orch.assert_manifest_capability_enabled,
    )
    return ns


async def publish_m_definitions(provider_ns: Any, publisher: Any) -> Any:
    """按 DAG 发布 M entry 的 definition 全套。返回 Phase5Definitions（与 K 循环同口径）。"""
    from app.services.workpaper_sync.models import BundleSlot

    orch = provider_ns.orch
    cfg = provider_ns.cfg

    contract = orch.assert_contract_file_matches_source()

    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=orch.authority_model_payload(),
        logical_id=f"{cfg.adapter_id}.authority-model",
        semantic_version="1.0.0",
    )

    tp = orch.template_definition_payload()
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=tp,
        logical_id=f"{contract.contract_id}.template",
        semantic_version="1.0.0",
        blob_bytes=orch.read_authoritative_template(),
        structure_hash=tp.get("normalized_structure_hash"),
    )

    instr = await publisher.publish_definition(
        kind=DefinitionKind.instrumentation,
        payload=orch.instrumentation_definition_payload(),
        logical_id=f"{contract.contract_id}.instrumentation",
        semantic_version="1.0.0",
    )

    contract_def = await publisher.publish_definition(
        kind=DefinitionKind.contract,
        payload=dict(contract.canonical_payload),
        logical_id=contract.contract_id,
        semantic_version=contract.semantic_version,
    )

    bundle = await publisher.publish_bundle(
        authority_model_definition_id=authority.definition_id,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_sha256=authority.sha256,
        slots={
            BundleSlot.template: {
                "type": "definition",
                "ref": f"definition:{template.definition_id}",
                "digest": template.sha256,
            },
            BundleSlot.instrumentation: {
                "type": "definition",
                "ref": f"definition:{instr.definition_id}",
                "digest": instr.sha256,
            },
            BundleSlot.contract: {
                "type": "definition",
                "ref": f"definition:{contract_def.definition_id}",
                "digest": contract_def.sha256,
            },
        },
    )

    return orch.Phase5Definitions(
        authority_model_definition_id=authority.definition_id,
        authority_model_definition_sha256=authority.sha256,
        template_definition_id=template.definition_id,
        template_definition_sha256=template.sha256,
        instrumentation_definition_id=instr.definition_id,
        instrumentation_definition_sha256=instr.sha256,
        contract_definition_id=contract_def.definition_id,
        contract_definition_sha256=contract_def.sha256,
        bundle_id=bundle.bundle_id,
        bundle_sha256=bundle.canonical_sha256,
    )
