# -*- coding: utf-8 -*-
"""D2 检查工作簿 entry —— ``xlsx/gt-d2-inspection``。

spec: d2-inspection-sync-coverage · Phase 2

═══ 为什么单独建 entry ═══

D2 检查工作簿（``D2-6至D2-13  应收账款 -检查（Leap应对措施-检查）.xlsx``）是独立于
审定表工作簿（D2-1至D2-4）的 xlsx 文件。原因：

1. 模板不同（template_sha256 不同）
2. instrumentation 不共享（注入的 Excel Table / defined names / UUID 列各自独立）
3. 契约 schema 只支持单模板（template 节只能指向一个 workbook）
4. 发布链独立（template → instrumentation → contract → bundle → representation）

═══ 覆盖范围 ═══

8 张检查 sheet（D2-6~D2-13），按 provider 逐张扩容：

| Sheet | provider 模块 | sheet_key | 状态 |
|-------|-------------|-----------|------|
| D2-6 关联方检查 | phase5_d2_06_related_party | d26-managed | ✅ |
| D2-7 检查表 | phase5_d2_07_voucher_check | d27-managed | 待实现 |
| D2-8 坏账政策 | phase5_d2_08_policy | d28-managed | 待实现 |
| D2-9 坏账测算 | phase5_d2_09_ecl_single | d29-managed | 待实现 |
| D2-10 ECL 测试 | phase5_d2_10_ecl_migration | d210-managed | 待实现 |
| D2-11 核销检查 | phase5_d2_11_writeoff | d211-managed | 待实现 |
| D2-12 质押检查 | phase5_d2_12_pledge | d212-managed | 待实现 |
| D2-13 业务模式 | phase5_d2_13_bizmodel | d213-managed | 待实现 |

已实现的 sheet 通过灰度开关控制：开关 = True 时加入 instrumentation_specs() 和
build_contract_payload().sheets[]。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION,
    SyncContract,
    canonical_digest,
    contract_path_for,
    load_contract,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
    build_instrumentation_payload_for_sheets,
    build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    SyncDomainError,
)


class EntrySelectionError(SyncDomainError):
    """检查 entry 选型失败。"""

    error_code = "d2_inspection_entry_selection_error"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PILOT_CLASS: Final[str] = "d2_inspection"
ENTRY_ID: Final[str] = "xlsx/gt-d2-inspection"
ADAPTER_ID: Final[str] = "d2.inspection"

#: matcher 的 wp_code 集合。D2-6 有独立 wp_code。
WP_CODES: Final[frozenset[str]] = frozenset({"D2-6"})

EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"

#: 权威模板。
TEMPLATE_RELATIVE_PATH: Final[str] = (
    "D/D2-6至D2-13  应收账款 -检查（Leap应对措施-检查）.xlsx"
)
TEMPLATE_SHA256: Final[str] = (
    "76c5c721bac37bd3f9cbf92eb3dd6dccb156cb27c8dd26e5452aa8b103ce0813"
)

#: 主受管 sheet（D2-6，Phase 2 首个）—— orchestration config 要求一个 primary。
MANAGED_SHEET: Final[str] = "关联方及交易检查表D2-6"
TEMPLATE_ID: Final[str] = "D26"
SHEET_KEY: Final[str] = "d26-managed"
ROWS_TABLE_KEY: Final[str] = "related_party_rows"

#: 主区几何。
FIRST_DATA_ROW: Final[int] = 13
LAST_DATA_ROW: Final[int] = 15
FOOTER_ROW: Final[int] = 16
MANAGED_LAST_COL: Final[str] = "L"
UUID_COL: Final[str] = "M"
TABLE_NAME: Final[str] = "GT_D26_ROWS"
FOOTER_MARKER: Final[str] = "合计"

AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
STORE_ITEM_ID: Final[str] = "D2-related-party-rows"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"

# ═══════════════════════════════════════════════════════════════════════════
# 2. 灰度开关（已实现的 sibling sheet）
# ═══════════════════════════════════════════════════════════════════════════

#: D2-6 是 primary，永远在。以下开关控制其余 sheet 的灰度接入。
_INCLUDE_D207_VOUCHER_CHECK: Final[bool] = True
_INCLUDE_D208_POLICY_CHECK: Final[bool] = False   # 纯文本描述型，不需 provider
_INCLUDE_D209_ECL_SINGLE: Final[bool] = True
_INCLUDE_D210_ECL_MIGRATION: Final[bool] = True
_INCLUDE_D211_WRITEOFF: Final[bool] = True
_INCLUDE_D212_PLEDGE: Final[bool] = True
_INCLUDE_D213_BIZMODEL: Final[bool] = True


# ═══════════════════════════════════════════════════════════════════════════
# 3. 权威模板
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_REPO_ROOT: Final[Path] = _BACKEND_ROOT.parent


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    """Excel 载体 gate。"""
    return ExcelIdentityCarrierGate.load()


def authoritative_template_path() -> Path:
    """权威模板绝对路径。"""
    return excel_carrier_gate().assert_template_under_authority(TEMPLATE_RELATIVE_PATH)


def read_authoritative_template() -> bytes:
    """读权威模板字节并校验 SHA256 哨兵。"""
    path = authoritative_template_path()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise EntrySelectionError(
            f"权威模板字节已变: {TEMPLATE_RELATIVE_PATH} 实测 sha256={digest}，"
            f"冻结哨兵={TEMPLATE_SHA256}"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 4. Instrumentation specs（复数，随灰度开关增长）
# ═══════════════════════════════════════════════════════════════════════════


def _primary_instrumentation_spec() -> ExcelInstrumentationSpec:
    """D2-6 primary spec。"""
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=TEMPLATE_ID,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=MANAGED_SHEET,
        first_data_row=FIRST_DATA_ROW,
        last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL,
        table_name=TABLE_NAME,
        sheet_key=SHEET_KEY,
    )


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """本 entry 全部受管 sheet 的 instrumentation spec（随灰度开关增长）。"""
    primary = _primary_instrumentation_spec()
    extras: list[ExcelInstrumentationSpec] = []
    if _INCLUDE_D207_VOUCHER_CHECK:
        from app.services.workpaper_sync.phase5_d2_07_voucher_check import (
            instrumentation_spec_d27,
        )
        d27_specs = instrumentation_spec_d27(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH,
        )
        extras.extend(d27_specs)  # tuple of 2 (current + post)
    if _INCLUDE_D211_WRITEOFF:
        from app.services.workpaper_sync.phase5_d2_11_writeoff import (
            instrumentation_spec_d211,
        )
        d211_specs = instrumentation_spec_d211(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH,
        )
        extras.extend(d211_specs)  # tuple of 2 (reversal + writeoff)
    if _INCLUDE_D212_PLEDGE:
        from app.services.workpaper_sync.phase5_d2_12_pledge import (
            instrumentation_spec_d212,
        )
        extras.append(instrumentation_spec_d212(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH,
        ))
    if _INCLUDE_D213_BIZMODEL:
        from app.services.workpaper_sync.phase5_d2_13_bizmodel import (
            instrumentation_spec_d213,
        )
        extras.append(instrumentation_spec_d213(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH,
        ))
    if _INCLUDE_D209_ECL_SINGLE:
        from app.services.workpaper_sync.phase5_d2_09_ecl_single import (
            instrumentation_spec_d29,
        )
        extras.append(instrumentation_spec_d29(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH,
        ))
    if _INCLUDE_D210_ECL_MIGRATION:
        from app.services.workpaper_sync.phase5_d2_10_ecl_test import (
            instrumentation_spec_d210,
        )
        extras.append(instrumentation_spec_d210(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH,
        ))
    return (primary, *extras)


def instrumentation_spec() -> ExcelInstrumentationSpec:
    """单数兼容（orchestration config 需要）。"""
    return _primary_instrumentation_spec()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Definition payloads
# ═══════════════════════════════════════════════════════════════════════════


def template_definition_payload() -> dict[str, Any]:
    """template definition canonical payload。"""
    data = read_authoritative_template()
    return build_template_payload(
        spec=instrumentation_spec(),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    """instrumentation definition canonical payload（复数路径）。"""
    return build_instrumentation_payload_for_sheets(
        specs=instrumentation_specs(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )


def authority_model_payload() -> dict[str, Any]:
    """authority model definition canonical payload。"""
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
        "pilot_class": PILOT_CLASS,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. Store item ids
# ═══════════════════════════════════════════════════════════════════════════


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item 的单一口径。"""
    ids: list[str] = [STORE_ITEM_ID]
    if _INCLUDE_D207_VOUCHER_CHECK:
        from app.services.workpaper_sync.phase5_d2_07_voucher_check import (
            STORE_ITEM_ID_CURRENT, STORE_ITEM_ID_POST,
        )
        ids.extend((STORE_ITEM_ID_CURRENT, STORE_ITEM_ID_POST))
    if _INCLUDE_D211_WRITEOFF:
        from app.services.workpaper_sync.phase5_d2_11_writeoff import (
            STORE_ITEM_ID_REVERSAL, STORE_ITEM_ID_WRITEOFF,
        )
        ids.extend((STORE_ITEM_ID_REVERSAL, STORE_ITEM_ID_WRITEOFF))
    if _INCLUDE_D212_PLEDGE:
        from app.services.workpaper_sync.phase5_d2_12_pledge import (
            STORE_ITEM_ID_PLEDGE,
        )
        ids.append(STORE_ITEM_ID_PLEDGE)
    if _INCLUDE_D213_BIZMODEL:
        from app.services.workpaper_sync.phase5_d2_13_bizmodel import (
            STORE_ITEM_ID as D213_STORE_ITEM_ID,
        )
        ids.append(D213_STORE_ITEM_ID)
    if _INCLUDE_D209_ECL_SINGLE:
        from app.services.workpaper_sync.phase5_d2_09_ecl_single import (
            STORE_ITEM_ID as D29_STORE_ITEM_ID,
        )
        ids.append(D29_STORE_ITEM_ID)
    if _INCLUDE_D210_ECL_MIGRATION:
        from app.services.workpaper_sync.phase5_d2_10_ecl_test import (
            STORE_ITEM_ID as D210_STORE_ITEM_ID,
        )
        ids.append(D210_STORE_ITEM_ID)
    return tuple(ids)


STORE_ITEM_IDS: tuple[str, ...] = all_store_item_ids()


# ═══════════════════════════════════════════════════════════════════════════
# 7. Per-entry contract
# ═══════════════════════════════════════════════════════════════════════════


def build_contract_payload() -> dict[str, Any]:
    """检查 entry 的 per-entry contract canonical payload。"""
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR
    from app.services.workpaper_sync.phase5_d2_06_related_party import (
        assert_mapping_digest_d26,
        sheet_payload_d26,
    )

    assert_mapping_digest_d26()
    template_payload = template_definition_payload()

    sheets: list[dict[str, Any]] = [
        # D2-6 primary（永远在）
        sheet_payload_d26(),
    ]
    # D2-7 应收账款检查表
    if _INCLUDE_D207_VOUCHER_CHECK:
        from app.services.workpaper_sync.phase5_d2_07_voucher_check import (
            assert_mapping_digest_d27,
            sheet_payload_d27,
        )
        assert_mapping_digest_d27()
        sheets.append(sheet_payload_d27())
    # D2-11 核销检查表
    if _INCLUDE_D211_WRITEOFF:
        from app.services.workpaper_sync.phase5_d2_11_writeoff import (
            assert_mapping_digest_d211,
            sheet_payload_d211,
        )
        assert_mapping_digest_d211()
        sheets.append(sheet_payload_d211())
    # D2-12 质押出售检查表
    if _INCLUDE_D212_PLEDGE:
        from app.services.workpaper_sync.phase5_d2_12_pledge import (
            assert_mapping_digest_d212,
            sheet_payload_d212,
        )
        assert_mapping_digest_d212()
        sheets.append(sheet_payload_d212())
    # D2-13 业务模式分析
    if _INCLUDE_D213_BIZMODEL:
        from app.services.workpaper_sync.phase5_d2_13_bizmodel import (
            assert_mapping_digest_d213,
            sheet_payload_d213,
        )
        assert_mapping_digest_d213()
        sheets.append(sheet_payload_d213())
    # D2-9 坏账准备测算
    if _INCLUDE_D209_ECL_SINGLE:
        from app.services.workpaper_sync.phase5_d2_09_ecl_single import (
            assert_mapping_digest_d29,
            sheet_payload_d29,
        )
        assert_mapping_digest_d29()
        sheets.append(sheet_payload_d29())
    # D2-10 ECL 计量测试
    if _INCLUDE_D210_ECL_MIGRATION:
        from app.services.workpaper_sync.phase5_d2_10_ecl_test import (
            assert_mapping_digest_d210,
            sheet_payload_d210,
        )
        assert_mapping_digest_d210()
        sheets.append(sheet_payload_d210())

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": ADAPTER_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(template_payload),
        "instrumentation_definition_sha256": canonical_digest(
            instrumentation_definition_payload()
        ),
        "template": {
            "relative_path": TEMPLATE_RELATIVE_PATH,
            "template_sha256": TEMPLATE_SHA256,
            "normalized_structure_hash": template_payload["normalized_structure_hash"],
        },
        "identity_carriers": [
            "hidden_sheet",
            "defined_name",
            "excel_table",
            "hidden_uuid_column",
        ],
        "sheets": sheets,
        "review": {
            "entry_id": ENTRY_ID,
            "pilot_class": PILOT_CLASS,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_id": STORE_ITEM_ID,
                "row_identity_key": ROW_IDENTITY_STORE_KEY,
                "shape": "json_array_of_row_objects",
            },
            "reviewed_basis": (
                "openpyxl 逐 sheet 直读权威模板 "
                "D/D2-6至D2-13  应收账款 -检查（Leap应对措施-检查）.xlsx 的 12 张 sheet。"
                "当前受管：关联方及交易检查表D2-6（31×14，17 公式，12 字段）。"
            ),
        },
    }


def contract_file_path() -> Path:
    """磁盘契约路径。"""
    return contract_path_for(ADAPTER_ID)


def load_entry_contract() -> SyncContract:
    """加载并强校验本 entry 的生产契约。"""
    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    """磁盘契约 ↔ 本模块现算 payload 双向锁死。"""
    expected = build_contract_payload()
    on_disk = load_entry_contract()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise EntrySelectionError(
            "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} "
            f"source={canonical_digest(expected)}；"
            f"请用生成脚本重生成 {contract_file_path().name}，并复核 diff"
        )
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 8. Store projection（合并全部 provider 的投影）
# ═══════════════════════════════════════════════════════════════════════════


def build_store_projection(
    payload: str | bytes,
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """D2-6 单 store item 的 projection。"""
    from app.services.workpaper_sync.phase5_d2_06_related_party import (
        build_d26_store_projection,
    )

    return build_d26_store_projection(payload, contract=contract, limits=limits)


def build_combined_store_projection(
    payloads: Mapping[str, Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """多 store 合并投影。"""
    from app.services.workpaper_sync.adapters.base import Projection

    # ① D2-6 primary
    d26_payload = payloads.get(STORE_ITEM_ID, "[]")
    d26_proj = build_store_projection(d26_payload, contract=contract, limits=limits)
    all_values = dict(d26_proj.values)
    all_row_keys = dict(d26_proj.row_keys)

    # ② D2-7 应收账款检查表
    if _INCLUDE_D207_VOUCHER_CHECK:
        from app.services.workpaper_sync.phase5_d2_07_voucher_check import (
            build_d27_store_projection,
        )
        d27_proj = build_d27_store_projection(payloads, contract=contract, limits=limits)
        all_values.update(d27_proj.values)
        all_row_keys.update(d27_proj.row_keys)

    # ③ D2-11 核销检查表
    if _INCLUDE_D211_WRITEOFF:
        from app.services.workpaper_sync.phase5_d2_11_writeoff import (
            build_d211_store_projection,
        )
        d211_proj = build_d211_store_projection(payloads, contract=contract, limits=limits)
        all_values.update(d211_proj.values)
        all_row_keys.update(d211_proj.row_keys)

    # ④ D2-12 质押出售检查表
    if _INCLUDE_D212_PLEDGE:
        from app.services.workpaper_sync.phase5_d2_12_pledge import (
            build_d212_store_projection,
        )
        d212_proj = build_d212_store_projection(
            payloads.get("D2-pledge-rows", "[]"), contract=contract, limits=limits,
        )
        all_values.update(d212_proj.values)
        all_row_keys.update(d212_proj.row_keys)

    # ⑤ D2-13 业务模式分析
    if _INCLUDE_D213_BIZMODEL:
        from app.services.workpaper_sync.phase5_d2_13_bizmodel import (
            build_d213_store_projection,
        )
        d213_proj = build_d213_store_projection(
            payloads.get("D2-bizmodel-groups", "[]"), contract=contract, limits=limits,
        )
        all_values.update(d213_proj.values)
        all_row_keys.update(d213_proj.row_keys)

    # ⑥ D2-9 坏账准备测算
    if _INCLUDE_D209_ECL_SINGLE:
        from app.services.workpaper_sync.phase5_d2_09_ecl_single import (
            build_d29_store_projection,
        )
        d29_proj = build_d29_store_projection(
            payloads.get("D2-ecl-single-rows", "[]"), contract=contract, limits=limits,
        )
        all_values.update(d29_proj.values)
        all_row_keys.update(d29_proj.row_keys)

    # ⑦ D2-10 ECL 计量测试
    if _INCLUDE_D210_ECL_MIGRATION:
        from app.services.workpaper_sync.phase5_d2_10_ecl_test import (
            build_d210_store_projection,
        )
        d210_proj = build_d210_store_projection(
            payloads.get("D2-ecl-discount-rows", "[]"), contract=contract, limits=limits,
        )
        all_values.update(d210_proj.values)
        all_row_keys.update(d210_proj.row_keys)

    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=all_values,
        row_keys=all_row_keys,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9. Orchestration 接入
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync.phase5_entry_orchestration import (  # noqa: E402
    Phase5EntryConfig,
    build_orchestration,
)

_orch = build_orchestration(Phase5EntryConfig(
    phase5_wave=PILOT_CLASS,
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    expected_profile_id=EXPECTED_PROFILE_ID,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    managed_sheet=MANAGED_SHEET,
    template_id=TEMPLATE_ID,
    sheet_key=SHEET_KEY,
    rows_table_key=ROWS_TABLE_KEY,
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    managed_last_col=MANAGED_LAST_COL,
    uuid_col=UUID_COL,
    table_name=TABLE_NAME,
    authority_model=AUTHORITY_MODEL,
    footer_marker=FOOTER_MARKER,
    store_item_id=STORE_ITEM_ID,
    error_code_prefix="sync_d2_inspection",
    build_contract_payload_fn=build_contract_payload,
    instrumentation_definition_payload_fn=instrumentation_definition_payload,
    instrumentation_specs_fn=instrumentation_specs,
))

# ── 导出工厂产出 ──────────────────────────────────────────────────────────
Phase5Definitions = _orch.Phase5Definitions
TemplateResolutionFacts = _orch.TemplateResolutionFacts

publish_definitions = _orch.publish_definitions
attach_adapters = _orch.attach_adapters
build_matcher = _orch.build_matcher
build_registration = _orch.build_registration
register_adapter = _orch.register_adapter
resolve_published_frozen_definitions = _orch.resolve_published_frozen_definitions
manifest_capability_enabled = _orch.manifest_capability_enabled
assert_manifest_capability_enabled = _orch.assert_manifest_capability_enabled

# ── pilot 命名别名（fix_task76_provision 脚本要求这两个名字）──────────────
publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
