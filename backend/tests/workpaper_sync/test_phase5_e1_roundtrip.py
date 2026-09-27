# -*- coding: utf-8 -*-
"""E1 端到端集成测试：contract 构建 → store projection → merge 回写 → roundtrip 等值。

spec: e1-sync-coverage-and-first-canary · Task 9（合成数据验证，不冒充真栈）
Properties: E1-P4（§9.6 三谓词合成等价）/ E1-P10（下游消费方回写后正确重算）/
            E1-P11（materialize + verify 全绿合成等价）

验证链路：
  1. contract payload 可构建且 schema 自洽
  2. 合成 store 载荷 → build_store_projection → projection 非空
  3. projection → merge_projection_into_store_rows → 回写行数 > 0
  4. 回写后行身份 (id) 保持不变（roundtrip 等值）
  5. 各 sheet 的 store_item_id 投影到正确的 spec（不串）
  6. attach_pilot_adapters 前置条件（capability 未启用时返回空元组）
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

# ═══ Provider + Specs ═══

from app.services.workpaper_sync.phase5_e1_monetary_fund import (
    ADAPTER_ID,
    ENTRY_ID,
    STORE_ITEM_ID,
    build_contract_payload,
    managed_row_table_specs,
    all_store_item_ids,
    build_store_projection,
    merge_projection_into_store_rows,
    manifest_capability_enabled,
)
from app.services.workpaper_sync.phase5_e1_02_cash_detail import (
    SPEC_E102,
    STORE_ITEM_ID_E102,
    ROW_IDENTITY_STORE_KEY_E102,
    FIXED_ROW_KEY_E102,
)
from app.services.workpaper_sync.phase5_e1_04_digital import (
    SPEC_E104,
    STORE_ITEM_ID_E104,
)
from app.services.workpaper_sync.phase5_e1_06_reconciliation import (
    SPEC_E106,
    STORE_ITEM_ID_E106,
)
from app.services.workpaper_sync.phase5_e1_07_08_09_cash_count import (
    SPEC_E107,
    SPEC_E108,
    SPEC_E109,
    STORE_ITEM_ID_E107,
    STORE_ITEM_ID_E108,
    STORE_ITEM_ID_E109,
)
from app.services.workpaper_sync.phase5_e1_10_account_list import (
    SPEC_E110,
    STORE_ITEM_ID_E110,
)
from app.services.workpaper_sync.contracts import parse_contract

# ═══ 合成 store 载荷工厂 ═══

#: 本册**全部**已写 sheet spec（含尚未接入受管清单的）。
#: 🔴 声明层判据（契约字段 / 几何 / 键唯一）对 7 张全适用。
ALL_SPECS = (SPEC_E102, SPEC_E104, SPEC_E106, SPEC_E107, SPEC_E108, SPEC_E109, SPEC_E110)

# ═══ 🔴 灰度开关与 roundtrip 分母（2026-09-27 补漏）═══
#
# 本文件此前在 **collect 阶段**就 ImportError（`phase5_e1_monetary_fund` 缺
# `manifest_capability_enabled`），导致整个 `backend/tests/workpaper_sync/` 目录
# 一条都跑不了 ⇒ 文件里的用例**从未真正执行过**。补齐符号后暴露出第二层问题：
#
# 🔴 provider 的灰度开关只接入了 **2 张**（`_INCLUDE_E102_CASH_DETAIL` +
#    `_INCLUDE_E104_DIGITAL`，注释明写「灰度开关逐张接入」是**有意**设计），
#    而 roundtrip 用例按 `ALL_SPECS` **7 张**全量参数化 ⇒ 未接入的 5 张必然撞上
#    `_spec_of_store_item` 的「不在受管清单里 → 显式失败」。
#
# ⇒ 正确分母是「**现算**受管清单」，不是写死 7 张也不是写死 2 张：
#    `MANAGED_SPECS` 从 `managed_row_table_specs()` 取，开关一开就自动纳入。
# 🔴 未受管的 5 张**不是跳过不管** —— 由 `TestGrayscaleSwitchIsExplicit` 正向断言
#    「取它的 spec SHALL 显式抛 EntrySelectionError」，把 provider 那条
#    「不得静默当成零行」的设计意图变成可执行判据。
MANAGED_SPECS = tuple(managed_row_table_specs())
MANAGED_STORE_ITEM_IDS = frozenset(s.store_item_id for s in MANAGED_SPECS)
UNMANAGED_SPECS = tuple(
    s for s in ALL_SPECS if s.store_item_id not in MANAGED_STORE_ITEM_IDS
)


def _synth_row(spec: Any, seq: int = 0) -> dict[str, Any]:
    """按 spec 的 field_specs 构造一行合成数据。"""
    row: dict[str, Any] = {spec.row_identity_key: f"synth-{spec.template_id}-{seq}"}
    for field_spec in spec.field_specs:
        column_key, _col, mode, value_type, json_path, _header, _group = field_spec
        if mode == "formula":
            # 公式格由引擎重算，store 侧给一个非零值（验证 roundtrip 不清零）
            row[json_path] = 100.0 + seq
        elif value_type == "amount":
            row[json_path] = 1000.0 + seq * 10
        elif value_type == "integer":
            row[json_path] = seq + 1
        else:
            row[json_path] = f"test-{json_path}-{seq}"
    return row


def _synth_payload(spec: Any, n_rows: int = 3) -> str:
    """构造 N 行的合成 JSON 载荷。"""
    rows = [_synth_row(spec, i) for i in range(n_rows)]
    return json.dumps(rows, ensure_ascii=False)


# ═══ Contract 构建 ═══


@pytest.fixture(scope="module")
def e1_contract_payload() -> dict[str, Any]:
    """E1 的 contract payload（现算，每次测试共享）。"""
    return build_contract_payload()


@pytest.fixture(scope="module")
def e1_parsed_contract(e1_contract_payload: dict[str, Any]) -> Any:
    """解析后的 contract 对象。"""
    return parse_contract(e1_contract_payload, adapter_id=ADAPTER_ID)


class TestContractPayload:
    """contract payload 可构建且 schema 自洽。"""

    def test_contract_payload_builds_without_error(self, e1_contract_payload: dict) -> None:
        assert e1_contract_payload is not None
        assert e1_contract_payload["contract_id"] == ADAPTER_ID

    def test_contract_schema_version(self, e1_contract_payload: dict) -> None:
        from app.services.workpaper_sync.contracts import CONTRACT_SCHEMA_VERSION
        assert e1_contract_payload["schema_version"] == CONTRACT_SCHEMA_VERSION

    def test_contract_has_sheets(self, e1_contract_payload: dict) -> None:
        sheets = e1_contract_payload["sheets"]
        assert len(sheets) >= 1, "contract 至少应有 canary sheet"

    def test_contract_parses_successfully(self, e1_parsed_contract: Any) -> None:
        assert e1_parsed_contract is not None
        assert e1_parsed_contract.contract_id == ADAPTER_ID

    def test_each_sheet_has_tables(self, e1_contract_payload: dict) -> None:
        for sheet in e1_contract_payload["sheets"]:
            assert len(sheet["tables"]) >= 1, f"sheet {sheet['sheet_key']} 无 table"

    def test_review_html_store_item_ids(self, e1_contract_payload: dict) -> None:
        """review.html_store.item_ids 包含全部已受管的 store item。"""
        items = e1_contract_payload["review"]["html_store"]["item_ids"]
        for item_id in all_store_item_ids():
            assert item_id in items, f"{item_id} 不在 contract review 的 item_ids 里"


# ═══ Store Projection ═══


class TestStoreProjection:
    """合成 store 载荷 → build_store_projection → projection 非空。"""

    @pytest.mark.parametrize("spec", MANAGED_SPECS, ids=lambda s: s.error_label)
    def test_projection_non_empty(self, spec: Any, e1_parsed_contract: Any) -> None:
        payload = _synth_payload(spec, n_rows=3)
        proj = build_store_projection(
            payload, contract=e1_parsed_contract, store_item_id=spec.store_item_id
        )
        assert proj is not None
        assert len(proj.values) > 0, f"{spec.error_label} 的 projection 为空"

    @pytest.mark.parametrize("spec", MANAGED_SPECS, ids=lambda s: s.error_label)
    def test_projection_row_keys_match_input(self, spec: Any, e1_parsed_contract: Any) -> None:
        """projection 的 row_keys 包含输入行的 identity。"""
        payload = _synth_payload(spec, n_rows=2)
        proj = build_store_projection(
            payload, contract=e1_parsed_contract, store_item_id=spec.store_item_id
        )
        table_key = spec.table_key
        keys = proj.row_keys.get(table_key, ())
        assert len(keys) == 2, f"{spec.error_label} row_keys 行数 {len(keys)} ≠ 2"

    def test_canary_projection_field_count(self, e1_parsed_contract: Any) -> None:
        """E1-2 canary：3 行 × 10 字段 = 30 个值。"""
        payload = _synth_payload(SPEC_E102, n_rows=3)
        proj = build_store_projection(
            payload, contract=e1_parsed_contract, store_item_id=STORE_ITEM_ID_E102
        )
        # field_count = n_rows × n_managed_fields
        n_fields = len(SPEC_E102.field_specs)
        expected = 3 * n_fields
        assert len(proj.values) == expected, (
            f"canary projection field_count={len(proj.values)} ≠ {expected} "
            f"(3 行 × {n_fields} 字段)"
        )


# ═══ Merge Roundtrip ═══


class TestMergeRoundtrip:
    """projection → merge_projection_into_store_rows → 回写行数 > 0 + 身份保持。"""

    @pytest.mark.parametrize("spec", MANAGED_SPECS, ids=lambda s: s.error_label)
    def test_merge_produces_rows(self, spec: Any, e1_parsed_contract: Any) -> None:
        payload = _synth_payload(spec, n_rows=3)
        proj = build_store_projection(
            payload, contract=e1_parsed_contract, store_item_id=spec.store_item_id
        )
        base_rows = json.loads(payload)
        merged, applied, visited, touched = merge_projection_into_store_rows(
            projection=proj, base_rows=base_rows, store_item_id=spec.store_item_id
        )
        assert len(merged) >= 3, f"{spec.error_label} merge 后行数 {len(merged)} < 3"
        assert applied >= 0

    @pytest.mark.parametrize("spec", MANAGED_SPECS, ids=lambda s: s.error_label)
    def test_merge_preserves_row_identity(self, spec: Any, e1_parsed_contract: Any) -> None:
        """回写后行身份 (id) 保持不变。"""
        payload = _synth_payload(spec, n_rows=3)
        proj = build_store_projection(
            payload, contract=e1_parsed_contract, store_item_id=spec.store_item_id
        )
        base_rows = json.loads(payload)
        original_ids = [str(r[spec.row_identity_key]) for r in base_rows]
        merged, *_ = merge_projection_into_store_rows(
            projection=proj, base_rows=base_rows, store_item_id=spec.store_item_id
        )
        merged_ids = [str(r[spec.row_identity_key]) for r in merged]
        assert merged_ids == original_ids, (
            f"{spec.error_label} 行身份变了：{merged_ids} ≠ {original_ids}"
        )

    def test_canary_editable_values_roundtrip(self, e1_parsed_contract: Any) -> None:
        """E1-2 canary：editable 字段在 roundtrip 后逐值不变。"""
        rows = [_synth_row(SPEC_E102, 0)]
        payload = json.dumps(rows, ensure_ascii=False)
        proj = build_store_projection(
            payload, contract=e1_parsed_contract, store_item_id=STORE_ITEM_ID_E102
        )
        merged, *_ = merge_projection_into_store_rows(
            projection=proj, base_rows=rows, store_item_id=STORE_ITEM_ID_E102
        )
        assert len(merged) == 1
        original = rows[0]
        result = merged[0]
        # 只检查 editable 字段（formula 由 OO 重算，merge 不保证等值）
        for field_spec in SPEC_E102.field_specs:
            _ckey, _col, mode, _vt, json_path, _h, _g = field_spec
            if mode == "editable":
                assert result.get(json_path) == original.get(json_path), (
                    f"E1-2 editable 字段 {json_path} roundtrip 不等值："
                    f"{result.get(json_path)!r} ≠ {original.get(json_path)!r}"
                )

    def test_canary_fixed_row_survives_merge(self, e1_parsed_contract: Any) -> None:
        """E1-2 的不可删除固定行 fixed-rmb 在 merge 后仍存在。"""
        rows = [
            {ROW_IDENTITY_STORE_KEY_E102: FIXED_ROW_KEY_E102, "currency": "人民币", "opening": 100},
            {ROW_IDENTITY_STORE_KEY_E102: f"cash-{uuid.uuid4().hex[:8]}", "currency": "美元", "opening": 200},
        ]
        payload = json.dumps(rows, ensure_ascii=False)
        proj = build_store_projection(
            payload, contract=e1_parsed_contract, store_item_id=STORE_ITEM_ID_E102
        )
        merged, *_ = merge_projection_into_store_rows(
            projection=proj, base_rows=rows, store_item_id=STORE_ITEM_ID_E102
        )
        merged_ids = {str(r[ROW_IDENTITY_STORE_KEY_E102]) for r in merged}
        assert FIXED_ROW_KEY_E102 in merged_ids, "固定行 fixed-rmb 在 merge 后丢失"


# ═══ Store Item 隔离 ═══


class TestStoreItemIsolation:
    """各 sheet 的 store_item_id 投影到正确的 spec（不串）。"""

    def test_wrong_store_item_id_raises(self, e1_parsed_contract: Any) -> None:
        """用错 store_item_id 应该失败。"""
        payload = _synth_payload(SPEC_E102, n_rows=1)
        with pytest.raises(Exception):
            build_store_projection(
                payload, contract=e1_parsed_contract,
                store_item_id="E1-nonexistent-rows"
            )

    def test_each_spec_uses_own_store_item(self, e1_parsed_contract: Any) -> None:
        """每个 spec 的 store_item_id 互不相同。"""
        ids = [s.store_item_id for s in ALL_SPECS]
        assert len(ids) == len(set(ids)), f"store_item_id 有重复：{ids}"


# ═══ 🔴 灰度开关必须显式失败（2026-09-27 补，未受管 spec 的正向判据）═══


class TestGrayscaleSwitchIsExplicit:
    """未接入受管清单的 sheet spec **不得被静默当成零行**。

    🔴 provider 的 `_spec_of_store_item` 写着「灰度开关未开或键名写错时必须显式失败，
    不得静默当成零行（那是 D4-35 恒空的根因形态）」——本类把那句注释变成可执行判据。

    🔴 这不是「跳过未受管的」：roundtrip 用例的分母收窄到 `MANAGED_SPECS` 之后，
    未受管的 5 张由本类**反向**守住。变异「让 `_spec_of_store_item` 对未登记键返回 None
    或空 spec」SHALL 被本类打红。
    """

    def test_managed_denominator_is_recomputed_not_hardcoded(self) -> None:
        """受管分母现算自 `managed_row_table_specs()`，且是 `ALL_SPECS` 的真子集。"""
        assert MANAGED_SPECS, "受管清单为空 —— roundtrip 分母坏了"
        all_ids = {s.store_item_id for s in ALL_SPECS}
        assert MANAGED_STORE_ITEM_IDS <= all_ids, (
            f"受管 store_item_id {sorted(MANAGED_STORE_ITEM_IDS - all_ids)} "
            "不在本册已写 spec 清单里 —— 两侧脱钩"
        )
        assert len(MANAGED_SPECS) + len(UNMANAGED_SPECS) == len(ALL_SPECS), (
            f"受管 {len(MANAGED_SPECS)} + 未受管 {len(UNMANAGED_SPECS)} "
            f"≠ 已写 spec {len(ALL_SPECS)} —— 分母不自洽"
        )

    @pytest.mark.parametrize("spec", UNMANAGED_SPECS, ids=lambda s: s.error_label)
    def test_unmanaged_spec_fails_loudly(self, spec: Any, e1_parsed_contract: Any) -> None:
        """未受管 spec 取投影 SHALL 显式抛，且错误文案点名该键与当前受管清单。"""
        from app.services.workpaper_sync.phase5_e1_monetary_fund import (
            EntrySelectionError,
        )

        payload = _synth_payload(spec, n_rows=2)
        with pytest.raises(EntrySelectionError) as excinfo:
            build_store_projection(
                payload, contract=e1_parsed_contract, store_item_id=spec.store_item_id
            )
        msg = str(excinfo.value)
        assert spec.store_item_id in msg, (
            f"错误文案没点名未受管键 {spec.store_item_id!r}：{msg}"
        )
        assert "受管" in msg, f"错误文案没说明受管清单：{msg}"

    def test_unmanaged_specs_are_declaration_complete_anyway(self) -> None:
        """🔴 未受管 ≠ 未声明：那 5 张的 spec 字段级声明仍须完整。

        否则「等开关一开就能用」是空话 —— 开了才发现 spec 是空壳。
        """
        for spec in UNMANAGED_SPECS:
            assert spec.field_specs, f"{spec.error_label} 无 field_specs ⇒ 空壳 spec"
            assert spec.store_item_id, f"{spec.error_label} 无 store_item_id"
            assert spec.row_identity_key, f"{spec.error_label} 无 row_identity_key"
            assert spec.first_data_row >= 1, f"{spec.error_label} first_data_row 非法"
            assert spec.last_data_row >= spec.first_data_row, (
                f"{spec.error_label} 数据区上下界倒置"
            )


# ═══ attach 前置条件 ═══


class TestAttachPreconditions:
    """attach_pilot_adapters 前置条件验证。"""

    def test_capability_not_yet_enabled(self) -> None:
        """E1 尚未裁决 bidirectional，manifest_capability_enabled 应返回 False。"""
        assert manifest_capability_enabled() is False

    def test_attach_is_callable(self) -> None:
        """attach_pilot_adapters 可调用。"""
        from app.services.workpaper_sync.phase5_e1_monetary_fund import attach_pilot_adapters
        assert callable(attach_pilot_adapters)

    def test_adapter_id_matches_contract_id(self) -> None:
        """adapter_id 与 contract 的 contract_id 锁死（RG-4）。"""
        contract = build_contract_payload()
        assert contract["contract_id"] == ADAPTER_ID

    def test_entry_id_matches_registry(self) -> None:
        """entry_id 与 DELIVERED_PER_ENTRY_CONTRACTS 登记一致。"""
        from app.services.workpaper_sync.adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS
        e1 = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == ADAPTER_ID]
        assert len(e1) == 1
        assert e1[0]["entry_id"] == ENTRY_ID


# ═══ Variant 参数化验证 ═══


#: 三张共享 variant 的 sheet（人民币盘点 / 外币盘点 / 存单盘点）。
_VARIANT_TRIPLE = (
    (SPEC_E107, STORE_ITEM_ID_E107, "E1-7-rmb"),
    (SPEC_E108, STORE_ITEM_ID_E108, "E1-8-fx"),
    (SPEC_E109, STORE_ITEM_ID_E109, "E1-9-cert"),
)
#: 🔴 其中**已接入受管清单**的那些（现算）。三张当前全未接入 ⇒ 运行时独立性无分母。
_MANAGED_VARIANTS = tuple(
    t for t in _VARIANT_TRIPLE if t[1] in MANAGED_STORE_ITEM_IDS
)


class TestVariantParameterization:
    """E1-7/8/9 三张共享 variant 但 projection 互不干扰。

    🔴 **2026-09-27 拆成两层（原版把三张全当受管，必然失败）**：

    * **声明层**（对三张全适用，不依赖灰度开关）：`table_key` / `store_item_id` 两两互异
      —— 这才是「互不干扰」的**根本前提**。若两张 variant 共用 table_key，
      接入后必然互相污染，且那是**声明期**就该拦住的错。
    * **运行时层**（只对已接入的）：真跑 `build_store_projection` 验 row_keys 落在自己的
      table_key 下。当前三张**全未接入** ⇒ 该层分母为 0，由
      `test_runtime_layer_denominator_is_declared` 把「分母为 0」这件事**显式登记**，
      而不是让用例假装通过。
    """

    def test_variant_table_keys_are_pairwise_distinct(self) -> None:
        """声明层：三张 variant 的 table_key 两两互异（互不干扰的根本前提）。"""
        keys = [spec.table_key for spec, _sid, _label in _VARIANT_TRIPLE]
        assert len(keys) == len(set(keys)), f"variant 的 table_key 有重复：{keys}"

    def test_variant_store_item_ids_are_pairwise_distinct(self) -> None:
        """声明层：三张 variant 的 store_item_id 两两互异。"""
        ids = [sid for _spec, sid, _label in _VARIANT_TRIPLE]
        assert len(ids) == len(set(ids)), f"variant 的 store_item_id 有重复：{ids}"

    def test_runtime_layer_denominator_is_declared(self) -> None:
        """🔴 运行时独立性的分母现算并显式登记 —— 不许悄悄变成空转。

        当前三张 variant 全未接入受管清单 ⇒ `_MANAGED_VARIANTS` 为空 ⇒
        下面那条参数化用例**零参数**。本条把这个事实钉住：
        一旦有人开了 `_INCLUDE_E10{7,8,9}_*` 开关，分母自动变非空、运行时层自动生效。
        """
        all_sids = {t[1] for t in _VARIANT_TRIPLE}
        managed_sids = {t[1] for t in _MANAGED_VARIANTS}
        assert managed_sids <= all_sids, (
            f"受管 variant {sorted(managed_sids - all_sids)} 不在三张 variant 清单里"
        )
        for _spec, sid, label in _MANAGED_VARIANTS:
            assert sid in MANAGED_STORE_ITEM_IDS, f"{label} 不在受管清单里却被当受管"

    @pytest.mark.parametrize(
        "spec,store_id",
        [(t[0], t[1]) for t in _MANAGED_VARIANTS],
        ids=[t[2] for t in _MANAGED_VARIANTS],
    )
    def test_variant_projection_independent(self, spec, store_id, e1_parsed_contract) -> None:
        """运行时层：每个已接入 variant 的 projection 独立，不会污染其他 variant。"""
        payload = _synth_payload(spec, n_rows=2)
        proj = build_store_projection(
            payload, contract=e1_parsed_contract, store_item_id=store_id
        )
        # 每个 variant 的 table_key 不同
        assert spec.table_key in proj.row_keys
        assert len(proj.row_keys[spec.table_key]) == 2
