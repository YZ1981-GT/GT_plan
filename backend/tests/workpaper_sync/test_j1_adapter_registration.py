# -*- coding: utf-8 -*-
"""J1 真双向改线 —— provider 接口 / store 注册 / wp_code 裁决（参照 L1 `test_l1_adapter_registration`）。

spec: `j-cycle-sync-foundation-and-first-canary`（2026-10-01 续：Task 22 交付契约后缺的三环）

🔴 本文件钉住本轮修的三处真缺陷，防回退：
  ① provider 缺 store 门面（`build_store_projection` 等）⇒ `STORE_MERGE_REGISTRY` 无法登记；
  ② `build_registration` / `register_adapter` 按错签名调 `HC`（从未被执行，一调即 TypeError）；
  ③ 缺 `publish_pilot_definitions` / `PILOT_WP_CODES` ⇒ task76 provisioning 判「provider 是空壳」。
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from app.services.workpaper_sync import phase5_j1_employee_compensation as J1
from app.services.workpaper_sync import store_item_registry as SIR

BACKEND = Path(__file__).resolve().parents[2]
ADJ_PATH = BACKEND / "data" / "workpaper_sync_entry_wp_code_adjudication.json"


class TestProviderInterface:
    _REQUIRED = (
        "build_contract_payload", "assert_contract_file_matches_source",
        "build_store_projection", "merge_projection_into_store_rows", "iter_store_rows",
        "build_registration", "register_adapter", "attach_pilot_adapters",
        "resolve_published_frozen_definitions", "publish_definitions",
        "publish_pilot_definitions", "authority_model_payload",
    )

    def test_all_interfaces_callable(self) -> None:
        missing = [n for n in self._REQUIRED if not callable(getattr(J1, n, None))]
        assert not missing, f"J1 provider 缺接口：{missing}"
        assert J1.publish_pilot_definitions is J1.publish_definitions
        assert J1.PILOT_WP_CODES == J1.WP_CODES

    def test_build_store_projection_payload_is_first_positional(self) -> None:
        """golden digest 门按 `mod.build_store_projection(rows, contract=…)` 调用。"""
        params = list(inspect.signature(J1.build_store_projection).parameters.values())
        assert params[0].name == "payload"
        assert params[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params[1:])

    @pytest.mark.parametrize("fn", ["build_registration", "register_adapter"])
    def test_registration_signature_matches_h_common(self, fn: str) -> None:
        """🔴 原签名是 `(*, manifest=…)` —— 与 HC 不符，一调即 TypeError。"""
        kw = set(inspect.signature(getattr(J1, fn)).parameters)
        assert {"adapter", "bundle", "descriptor", "room", "contract"} <= kw
        assert "manifest" not in kw

    def test_store_projection_runs_on_empty_payload(self) -> None:
        contract = J1.assert_contract_file_matches_source()
        projection = J1.build_store_projection(J1.EMPTY_STORE_PAYLOAD, contract=contract)
        assert projection is not None

    def test_unknown_store_item_is_rejected(self) -> None:
        with pytest.raises(J1.EntrySelectionError):
            J1.iter_store_rows("[]", store_item_id="J1-6-questions")

    def test_authority_payload_declares_this_entry(self) -> None:
        payload = J1.authority_model_payload()
        assert payload["entry_id"] == J1.ENTRY_ID
        assert payload["authority_model"] == "projection_contract"


class TestSkeletonRowIdentityAlignment:
    """🔴 行翻倍缺陷的静态防回退（真 OO 往返是运行期证据，这里锁两侧身份口径一致）。

    模板 R17:R35 骨架行由 instrumentation 盖 `GTROW-{template_id}-{行号4位}`；前端短期薪酬区
    骨架行必须用同一身份，否则 OO 物化把 HTML 行当新行插在骨架后（实测 38 行）。
    """

    FRONT = BACKEND.parent / "audit-platform/frontend/src/components/workpaper/j1/inspection"

    def test_frontend_constants_equal_backend_spec(self) -> None:
        from app.services.workpaper_sync import phase5_j1_06_accrual_check as S

        ts = (self.FRONT / "j1AccrualRowIdentity.ts").read_text(encoding="utf-8")
        assert f"SHORT_TERM_TEMPLATE_ID = '{S.TEMPLATE_ID_J106}'" in ts
        assert f"SHORT_TERM_TEMPLATE_FIRST_ROW = {S.FIRST_DATA_ROW_J106}" in ts
        assert "TEMPLATE_ROW_ID_PREFIX = 'GTROW-'" in ts

    def test_instrumented_template_stamps_the_same_ids(self) -> None:
        import io

        import openpyxl

        from app.services.workpaper_sync import phase5_j1_06_accrual_check as S
        from app.services.workpaper_sync.excel_instrumentation import instrument_workbook_bytes

        out = instrument_workbook_bytes(
            J1.read_authoritative_template(), J1.instrumentation_spec(), gate=J1.excel_carrier_gate()
        )
        ws = openpyxl.load_workbook(io.BytesIO(out.instrumented_bytes))[S.MANAGED_SHEET_J106]
        got = [ws[f"{S.UUID_COL_J106}{r}"].value for r in range(S.FIRST_DATA_ROW_J106, S.LAST_DATA_ROW_J106 + 1)]
        assert got == [f"GTROW-{S.TEMPLATE_ID_J106}-{r:04d}" for r in range(17, 36)]

    def test_short_term_skeleton_no_longer_mints_random_ids(self) -> None:
        vue = (self.FRONT / "J1TabAccrualCheck.vue").read_text(encoding="utf-8")
        assert "createRows(SHORT_TERM_DEFAULTS, shortTermTemplateRowId)" in vue
        assert "bindShortTermTemplateIds(rows, SHORT_TERM_DEFAULTS.length)" in vue


class TestStoreRegistration:
    def test_plan_registered_with_single_item(self) -> None:
        plan = SIR.resolve_store_merge_plan(J1.ADAPTER_ID)
        assert plan.provider_module == "phase5_j1_employee_compensation"
        assert [i.item_id for i in plan.items] == [J1.STORE_ITEM_ID] == list(J1.all_store_item_ids())
        assert plan.oo_crash_neutralization_fn == "neutralize_oo_crash_if_formulas"

    def test_sibling_free_text_keys_are_not_preregistered(self) -> None:
        items = {i.item_id for i in SIR.resolve_store_merge_plan(J1.ADAPTER_ID).items}
        assert not items & {"J1-6-questions", "J1-6-conclusion", "J1-6-post-employment"}


class TestWpCodeAdjudication:
    def test_entry_adjudicated_to_real_code_not_phantom(self) -> None:
        doc = json.loads(ADJ_PATH.read_text(encoding="utf-8"))
        row = next(r for r in doc["adjudications"] if r["entry_id"] == J1.ENTRY_ID)
        assert row["wp_codes"] == ["J1"]
        assert row["contract_id"] == J1.ADAPTER_ID
        assert row["basis"]["heuristic_would_say"] == sorted(J1.WP_CODES)
        assert "J1" not in J1.WP_CODES, "裁决码与幻影码相同 ⇒ 裁决条目失去意义"


class TestManifestGate:
    """22e 终态：真库首版发布 + 真 OO 两轮往返全绿后，经 overlay override 重生成 manifest（未手改 JSON）。"""

    def test_manifest_flipped_after_roundtrip_passed(self) -> None:
        assert J1.manifest_capability_enabled()
        J1.assert_manifest_capability_enabled()

    def test_overlay_override_matches_manifest(self) -> None:
        overlay = json.loads((BACKEND / "data/workpaper_sync_entry_overlay.json").read_text(encoding="utf-8"))
        hits = [o for o in overlay["overrides"] if o.get("adapter_id") == J1.ADAPTER_ID]
        assert len(hits) == 1
        assert hits[0]["file_glob"].endswith("j1/GtJ1EmployeeCompensation.vue")

    def test_gate_still_rejects_a_legacy_manifest(self) -> None:
        """顺序门本身仍生效：喂一份 J1 仍是 legacy 的 manifest 必须挡住（变异证明）。"""
        manifest = json.loads((BACKEND / "data/workpaper_sync_entry_manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["entries"]:
            if entry["entry_id"] == J1.ENTRY_ID:
                entry["capability"] = "single_onlyoffice"
        assert not J1.manifest_capability_enabled(manifest=manifest)
        with pytest.raises(Exception):
            J1.assert_manifest_capability_enabled(manifest=manifest)

    def test_child_parent_duplicate_not_flipped(self) -> None:
        manifest = json.loads((BACKEND / "data/workpaper_sync_entry_manifest.json").read_text(encoding="utf-8"))
        child = next(e for e in manifest["entries"] if e["entry_id"] == "xlsx/j1/inspection/j1-tab-general-check")
        assert child["migration_state"] == "parent_duplicate"
        assert child["adapter_id"] is None
