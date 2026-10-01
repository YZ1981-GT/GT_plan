# -*- coding: utf-8 -*-
"""K 循环「调整分录汇总」受管表 —— 六条 entry（K8/K9/K10/K11/K12/K13）的共享 provider 内核。

spec: k-cycle-sync-foundation-and-first-canary Task 22/23（K10 canary）
      k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub Task 18（其余 5 条）

═══ 为什么共享一个内核 ═══

六册的「调整分录汇总K{n}-3」**模板层完全同构**（foundation KC-20 现算 13/13：单级表头 R5
十列 A..J、数据区纯空白待填、footer 是 A 列合并的「提示：」文字、数据区公式格 0、
裸 IF 0、merged 3），只有三处逐册不同：① 数据区末行 / footer 行号 ② store item_id
③ 前端行对象的字段名（K8 用 `summary` 当说明、K9/K11 的 `summary` 是 F 列「……」、
K10 用 `refIndex`、K8/K9/K11 用 `indexRef`……）。把这三处做成 `KAdjustmentEntryConfig`，
其余全部走同一份实现，六家不可能各自漂移。

═══ 与 D4-4（同型参照）的差异 ═══

1. 行身份键是 `id`（K 前端真源），不是 D4-4 的 `rowId`。
2. 模板 K~O 全空 ⇒ UUID 载体取紧邻受管末列 J 右侧的 **K 列**（无需注入，同 D4-4）。
3. footer 行是提示文字、**无合计公式** ⇒ `footer_carries_total_formula=False`；
   借贷平衡由前端 computed 在应用层校验（foundation KC-16）。
4. 走 `RowTableSheetSpec` 引擎（L1 范式），不手写 sheet payload。

🔴 本模块**不是** registry 白名单成员 —— 白名单要求「一个 entry 一个 provider 模块」
（`len(白名单) == len(台账)` 判据），故六个 `phase5_k{n}_*.py` 各自持有身份常量并
调用 :func:`build_k_adjustment_provider`。
"""
from __future__ import annotations

import types
from dataclasses import dataclass
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION,
    SyncContract,
    contract_path_for,
    parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec
from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_entry_orchestration import (
    Phase5EntryConfig,
    build_orchestration,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

#: 六册共同的几何（现算 13/13 同构）。
HEADER_ROW: Final[int] = 5
FIRST_DATA_ROW: Final[int] = 6
MANAGED_LAST_COL: Final[str] = "J"
UUID_COL: Final[str] = "K"
#: 🔴 必须是**整格全文**：`excel_materialize._find_marker_row` 按 `text.strip() == marker`
#:    精确匹配，不是前缀。六册 footer 文字逐字相同（openpyxl 现算）。首版写成前缀「提示：」
#:    ⇒ 首版发布第 7 阶段 `FooterAnchorDriftError`（真库预演实测）。
FOOTER_MARKER: Final[str] = (
    "提示：本底稿适用于调整分录较多、较复杂的项目，且仅列示与本报表项目相关的审计调整。"
    "项目组可根据项目实际情况选择是否使用该底稿。"
)
ROW_IDENTITY_STORE_KEY: Final[str] = "id"
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
ROWS_TABLE_KEY: Final[str] = "adjustment_summary_rows"
PHASE5_WAVE: Final[str] = "k_cycle_adjustment_summary"

#: 模板 R5 十列表头（逐册逐字相同）。
HEADER_TEXT: Final[Mapping[str, str]] = {
    "A": "调整事项说明",
    "B": "类别（报表调整/账项调整/其他）",
    "C": "报表项目",
    "D": "科目名称",
    "E": "附注项目",
    "F": "……",
    "G": "借方调整金额",
    "H": "贷方调整金额",
    "I": "索引",
    "J": "备注",
}
#: 列 → (column_key 契约侧 snake, value_type)。column_key 是**模板语义**，六册统一；
#: json_key（前端字段名）才逐册不同。
COLUMN_SEMANTICS: Final[Mapping[str, tuple[str, str]]] = {
    "A": ("description", "text"),
    "B": ("category", "text"),
    "C": ("report_item", "text"),
    "D": ("account_name", "text"),
    "E": ("note_item", "text"),
    "F": ("placeholder", "text"),
    "G": ("debit_amount", "amount"),
    "H": ("credit_amount", "amount"),
    "I": ("ref_index", "text"),
    "J": ("remark", "text"),
}


@dataclass(frozen=True)
class KAdjustmentEntryConfig:
    """一条 K entry 的「调整分录汇总」身份与逐册差异。"""

    n: int
    entry_id: str
    adapter_id: str
    wp_codes: frozenset[str]
    template_relative_path: str
    template_sha256: str
    managed_sheet: str
    store_item_id: str
    last_data_row: int
    footer_row: int
    #: 列 → 前端行对象 json 键（A..J 十列全给；HTML 无对应字段的列给 `placeholder` 等
    #: 新键 —— 前端加载时须 `...e` 保留未知键，否则 OO 侧填的那一格回 HTML 后被下次保存擦掉）。
    json_keys: Mapping[str, str]
    #: 只在 store 里、模板无列的键（如 K10 的 `type` AJE/RJE 分组维度）。
    store_only_keys: tuple[str, ...] = ()
    html_store_note: str = ""
    reviewed_basis: str = ""

    @property
    def template_id(self) -> str:
        return f"K{self.n}03"

    @property
    def sheet_key(self) -> str:
        return f"k{self.n}03-managed"

    @property
    def table_name(self) -> str:
        return f"GT_{self.template_id}_ROWS"

    @property
    def pilot_class(self) -> str:
        """交付台账要求每个 provider 的 pilot_class 唯一；共享内核不等于共享身份。"""
        return f"k{self.n}_adjustment_summary"


def _field_specs(cfg: KAdjustmentEntryConfig) -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    missing = [c for c in HEADER_TEXT if c not in cfg.json_keys]
    if missing:
        raise ValueError(f"K{cfg.n} 缺列 {missing} 的 json_key —— A..J 十列必须全部声明")
    out: list[tuple[str, str, str, str, str, str, str]] = []
    for col, header in HEADER_TEXT.items():
        column_key, value_type = COLUMN_SEMANTICS[col]
        out.append((column_key, col, "editable", value_type, cfg.json_keys[col], header, ""))
    return tuple(out)


def build_spec(cfg: KAdjustmentEntryConfig) -> RowTableSheetSpec:
    return RowTableSheetSpec(
        managed_sheet=cfg.managed_sheet,
        sheet_key=cfg.sheet_key,
        table_key=ROWS_TABLE_KEY,
        template_id=cfg.template_id,
        table_name=cfg.table_name,
        uuid_col=UUID_COL,
        first_data_row=FIRST_DATA_ROW,
        last_data_row=cfg.last_data_row,
        footer_row=cfg.footer_row,
        header_row=HEADER_ROW,
        store_item_id=cfg.store_item_id,
        empty_payload="[]",
        row_identity_key=ROW_IDENTITY_STORE_KEY,
        store_kind=StoreKind.rows,
        field_specs=_field_specs(cfg),
        #: 数据区公式格现算 0 ⇒ 无公式列、formula_mask 为空（CS-13 空分母成立）。
        formula_columns=(),
        footer_marker=FOOTER_MARKER,
        #: footer 是合并的提示文字，不承载 SUM（13 册「调整分录汇总」SUM 数现算全 0）。
        footer_carries_total_formula=False,
        error_label=f"{cfg.managed_sheet}",
        #: 幽灵行锚点 = A 列「调整事项说明」（[0]，真业务名称）。
        ghost_row_anchor_index=0,
    )


def build_k_adjustment_provider(cfg: KAdjustmentEntryConfig) -> types.SimpleNamespace:
    """一条 K entry 的完整 provider 面（契约 / 投影 / 合并 / 发布编排 / 注册）。"""
    spec = build_spec(cfg)

    def instrumentation_spec() -> ExcelInstrumentationSpec:
        return ExcelInstrumentationSpec(
            entry_id=cfg.entry_id,
            template_id=cfg.template_id,
            template_relative_path=cfg.template_relative_path,
            managed_sheet=cfg.managed_sheet,
            first_data_row=FIRST_DATA_ROW,
            last_data_row=cfg.last_data_row,
            footer_row=cfg.footer_row,
            managed_last_col=MANAGED_LAST_COL,
            uuid_col=UUID_COL,
            table_name=cfg.table_name,
        )

    def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
        return (instrumentation_spec(),)

    # 契约装配要用到编排面的 template / instrumentation payload ⇒ 先建编排再回填契约 fn。
    holder: dict[str, Any] = {}

    def build_contract_payload() -> dict[str, Any]:
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            spec_to_contract_sheet_payload,
        )

        orch = holder["orch"]
        template_payload = orch.template_definition_payload()
        return {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "contract_id": cfg.adapter_id,
            "semantic_version": "1.0.0",
            "review_status": "reviewed",
            "document_type": "xlsx",
            "template_definition_sha256": canonical_digest(template_payload),
            "instrumentation_definition_sha256": canonical_digest(
                orch.instrumentation_definition_payload()
            ),
            "template": {
                "relative_path": cfg.template_relative_path,
                "template_sha256": cfg.template_sha256,
                "normalized_structure_hash": template_payload["normalized_structure_hash"],
            },
            "identity_carriers": ["hidden_sheet", "excel_table", "hidden_uuid_column"],
            "sheets": [spec_to_contract_sheet_payload(spec)],
            "review": {
                "entry_id": cfg.entry_id,
                "pilot_class": cfg.pilot_class,
                "authority_root": "backend/wp_templates",
                "html_store": {
                    "table": "checklist_responses",
                    "item_id": cfg.store_item_id,
                    "row_identity_key": ROW_IDENTITY_STORE_KEY,
                    "shape": "json_array_of_row_objects",
                    "store_only_keys": list(cfg.store_only_keys),
                    "note": cfg.html_store_note,
                },
                "reviewed_basis": cfg.reviewed_basis,
            },
        }

    orch = build_orchestration(
        Phase5EntryConfig(
            phase5_wave=cfg.pilot_class,
            entry_id=cfg.entry_id,
            adapter_id=cfg.adapter_id,
            wp_codes=cfg.wp_codes,
            expected_profile_id=EXPECTED_PROFILE_ID,
            template_relative_path=cfg.template_relative_path,
            template_sha256=cfg.template_sha256,
            managed_sheet=cfg.managed_sheet,
            template_id=cfg.template_id,
            sheet_key=cfg.sheet_key,
            rows_table_key=ROWS_TABLE_KEY,
            first_data_row=FIRST_DATA_ROW,
            last_data_row=cfg.last_data_row,
            footer_row=cfg.footer_row,
            managed_last_col=MANAGED_LAST_COL,
            uuid_col=UUID_COL,
            table_name=cfg.table_name,
            authority_model=AuthorityModel.projection_contract,
            footer_marker=FOOTER_MARKER,
            store_item_id=cfg.store_item_id,
            row_identity_store_key=ROW_IDENTITY_STORE_KEY,
            error_code_prefix=f"sync_phase5_k{cfg.n}",
            build_contract_payload_fn=build_contract_payload,
            #: 🔴 必须显式给：编排工厂的默认路径是 `_BACKEND_ROOT / "backend/data/…"`，
            #:    而它的 `_BACKEND_ROOT` 已经是 `backend/` ⇒ 拼成 `backend/backend/data`
            #:    （D3/D5/D6/D7 都在模块里自定义了 `contract_file_path` 才没踩到）。
            contract_file_path_fn=lambda: contract_path_for(cfg.adapter_id),
            instrumentation_spec_fn=instrumentation_spec,
        )
    )
    holder["orch"] = orch

    def assert_contract_file_matches_source() -> SyncContract:
        expected = build_contract_payload()
        on_disk = orch.load_contract_from_disk()
        if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
            raise orch.EntrySelectionError(
                "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
                f"disk={canonical_digest(on_disk.canonical_payload)} "
                f"source={canonical_digest(expected)}；请运行 "
                "`backend/scripts/gen/generate_phase5_k_contracts.py --apply` 重生成"
            )
        parse_contract(expected, adapter_id=cfg.adapter_id)
        return on_disk

    def build_store_projection(
        payload: str | bytes | Sequence[Any], *, contract: SyncContract, limits: Any | None = None
    ) -> Any:
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            RowTableStorePayloadError,
            build_store_projection as _engine,
        )

        try:
            return _engine(spec, payload, contract=contract, limits=limits)
        except RowTableStorePayloadError as exc:
            raise orch.StorePayloadError(str(exc)) from exc

    def merge_projection_into_store_rows(
        *, projection: Any, base_rows: list[Mapping[str, Any]]
    ) -> tuple[list[dict[str, Any]], int, int, set[str]]:
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            merge_projection_into_store_rows as _engine_merge,
        )

        return _engine_merge(spec, projection=projection, base_rows=base_rows)

    def iter_store_rows(payload: Any, *, store_item_id: str | None = None):
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            iter_store_rows as _engine_iter,
        )

        return _engine_iter(spec, payload)

    def all_store_item_ids() -> tuple[str, ...]:
        return (cfg.store_item_id,)

    def managed_row_table_specs() -> tuple[RowTableSheetSpec, ...]:
        return (spec,)

    return types.SimpleNamespace(
        SPEC=spec,
        orch=orch,
        instrumentation_spec=instrumentation_spec,
        instrumentation_specs=instrumentation_specs,
        build_contract_payload=build_contract_payload,
        assert_contract_file_matches_source=assert_contract_file_matches_source,
        build_store_projection=build_store_projection,
        merge_projection_into_store_rows=merge_projection_into_store_rows,
        iter_store_rows=iter_store_rows,
        all_store_item_ids=all_store_item_ids,
        managed_row_table_specs=managed_row_table_specs,
    )


async def publish_with_authority(orch: Any, publisher: Any, authority: Any) -> Any:
    """五环发布：authority 已由调用方（per-entry 模块）发布，这里接着发 template→bundle。

    🔴 为什么 authority 那一环在 per-entry 模块里：`projection_lane_registry.
    assert_authority_logical_suffix_matches_providers` 用 AST 在**每个白名单模块源码**里找
    `publish_definition(kind=…authority_model…, logical_id=f"….authority-model")` 调用，
    用于反向构造 authority artifact 的查询键。把这一环留在 per-entry 模块 = 判据有真实对象；
    把它藏进共享内核 = 判据找不到、只能登记进「未实现编排」欠账清单（那是假账）。
    """
    from app.services.workpaper_sync.models import BundleSlot, DefinitionKind

    contract = orch.assert_contract_file_matches_source()
    tp = orch.template_definition_payload()
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=tp,
        logical_id=f"{contract.contract_id}.template",
        semantic_version="1.0.0",
        blob_bytes=orch.read_authoritative_template(),
        structure_hash=tp["normalized_structure_hash"],
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
    if template.sha256 != contract.template_definition_sha256:
        raise orch.EntrySelectionError(
            f"已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instr.sha256 != contract.instrumentation_definition_sha256:
        raise orch.EntrySelectionError(
            f"已发布 instrumentation digest {instr.sha256} 与契约声明 "
            f"{contract.instrumentation_definition_sha256} 不一致 —— 单向引用断裂"
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
