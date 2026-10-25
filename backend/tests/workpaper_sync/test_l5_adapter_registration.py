# -*- coding: utf-8 -*-
"""L5 长期应付款真双向接线守卫（spec `l5-true-bidirectional-2026-10-01` · T4）。

受管表 `明细表L5-2`（科目 2701 长期应付款，负债余额口径）。🔴 两处前所未见的组合：
**两区同键**（售后租回 R11:15 / 分期付款 R18:22，共享 store 键 L5-L5-2-rows +
section 字段分区，逐区 uuid_col AD/AE + template_id L52R1/R2）+ **flat 账龄**（T~X 单组 5 桶）。

🔴 R24「其他」段作模板静态骨架不进受管区（用户裁决 A，2026-10-02）：A24='…'(U+2026) 占位续行，
平台 typography 门 BP-21 对纯省略号占位行 fail-closed；现查坐实 R24 非业务行 ⇒ 两区，零能力损失。
T1 候选 C 判「三区」但漏测 typography 门，本轮勘误为两区。

与 L7 的差异（照抄 L7 会错）：
* 两个 RowTableSheetSpec（L7 单区）；契约 sheets[0] 有 2 条 tables[]。
* 公式列 7 个 E/L/M/N/O/R/S（L7 5 个）；账龄 flat 5 桶（L7 无账龄）。
* 小计 A16/A23 + 合计 A25（非连续枚举 SUM）+ 标题 A10/A17 + R24 其他占位续行作模板静态骨架。
* 融资属性 + HTML 旧标量退 html_only（13 键）；受管区只覆盖 Excel A..S + 账龄 T~X。
* store 走多区门面 `phase5_l5_store_facade`（iter/merge/projection 遍历两段）。
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest
from openpyxl import load_workbook

from app.services.workpaper_sync import phase5_l5_long_term_payables as L5
from app.services.workpaper_sync import phase5_l_cycle_common as L
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.definitions import canonical_digest
from tests.workpaper_sync.l1_adapter_facts import ROOT, _count_bare_if, _is_formula, _query

TEMPLATE = ROOT / "backend" / "wp_templates" / L5.TEMPLATE_RELATIVE_PATH
FRONTEND = ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
DETAIL_TS = FRONTEND / "composables" / "useL5Detail.ts"


@pytest.fixture(scope="module")
def wb():
    return load_workbook(TEMPLATE, data_only=False)


@pytest.fixture(scope="module")
def ws(wb):
    return wb[L5.MANAGED_SHEET]


# ═══════════════════════════════════════════════════════════════════════════
# 几何（openpyxl 现算）
# ═══════════════════════════════════════════════════════════════════════════


class TestManagedSheetSelection:
    def test_template_sha256_matches_frozen(self) -> None:
        assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == L5.TEMPLATE_SHA256

    def test_managed_sheet_present_and_adjudication_is_derived(self, wb) -> None:
        assert L5.MANAGED_SHEET in wb.sheetnames
        s1 = wb["审定表L5-1"]
        cross = sum(
            isinstance(c.value, str) and "明细表L5-2" in c.value
            for r in s1.iter_rows() for c in r
        )
        assert cross > 0, "审定表L5-1 应有跨 sheet 引用 明细表L5-2 的公式（下游视图）"

    def test_two_regions_geometry(self, ws) -> None:
        """两区数据/footer 区间 + 区标题/小计/合计/R24占位 静态骨架行实测。"""
        assert ws.max_column == 30, "物理 max_column=AD(30)"
        assert (L5.HEADER_GROUP_ROW, L5.HEADER_LEAF_ROW) == (8, 9)
        # 区标题行（静态骨架）
        assert ws["A10"].value == "售后租回业务形成的融资"
        assert ws["A17"].value == "分期付款方式购入固定资产"
        # R24「其他」占位续行（静态骨架，不进受管区）
        assert ws["A24"].value == "…" and ord(str(ws["A24"].value)) == 0x2026
        # 小计/合计行（静态骨架）
        assert ws["A16"].value == "小计" and ws["B16"].value == "=SUM(B11:B15)"
        assert ws["A23"].value == "小计" and ws["B23"].value == "=SUM(B18:B22)"
        assert ws["A25"].value == "合计" and ws["B25"].value == "=SUM(B16,B23,B24)"
        geo = {(s.first_data_row, s.last_data_row, s.footer_row) for s in L5.SPECS}
        assert geo == {(11, 15, 16), (18, 22, 23)}

    def test_two_regions_share_store_key_distinct_uuid_and_template(self) -> None:
        assert len(L5.SPECS) == 2
        assert {s.store_item_id for s in L5.SPECS} == {"L5-L5-2-rows"}
        assert {s.sheet_key for s in L5.SPECS} == {"l52-managed"}  # 共享 sheet_key
        assert [s.uuid_col for s in L5.SPECS] == ["AD", "AE"]
        assert [s.template_id for s in L5.SPECS] == ["L52R1", "L52R2"]
        assert [s.row_section_value for s in L5.SPECS] == ["saleLeaseback", "installment"]
        assert all(s.row_section_field == "section" for s in L5.SPECS)

    def test_region_uuid_columns_empty_in_data_region(self, ws) -> None:
        for col in ("AD", "AE"):
            vals = [ws[f"{col}{r}"].value for r in range(11, 24)]
            assert all(v in (None, "") for v in vals), f"{col} 应全空（受管区 UUID 列）"

    def test_r24_is_typography_placeholder_not_managed(self) -> None:
        """R24「其他」占位续行不是任何受管区（typography 门 BP-21 拒它，用户裁决 A）。"""
        from app.services.workpaper_sync import excel_typography_rows as T

        assert T.is_typography_placeholder("…") is True
        # 没有任何 spec 的区间覆盖 R24
        assert all(not (s.first_data_row <= 24 <= s.last_data_row) for s in L5.SPECS)

    def test_seven_formula_columns_same_shape_each_input_row(self, ws) -> None:
        """E/L/M/N/O/R/S 七列每一受管输入行同形（负债余额口径）；R24 占位行公式骨架幸存。"""
        for r in list(range(11, 16)) + list(range(18, 23)):
            assert ws[f"E{r}"].value == f"=B{r}-C{r}+D{r}"
            assert ws[f"L{r}"].value == f"=B{r}+F{r}+G{r}"
            assert ws[f"M{r}"].value == f"=C{r}+H{r}+J{r}"
            assert ws[f"N{r}"].value == f"=D{r}+I{r}+K{r}"
            assert ws[f"O{r}"].value == f"=L{r}-M{r}+N{r}"
            assert ws[f"R{r}"].value == f"=L{r}-P{r}"
            assert ws[f"S{r}"].value == f"=O{r}-Q{r}"
        assert L5.FORMULA_COLUMNS == ("E", "L", "M", "N", "O", "R", "S")
        # R24 占位行的 roll-forward 公式骨架在（静态骨架幸存，但不受管）
        assert ws["E24"].value == "=B24-C24+D24" and ws["O24"].value == "=L24-M24+N24"

    def test_flat_aging_five_buckets_full_width_labels(self, ws) -> None:
        """账龄单组 5 桶 flat；叶子标签逐字实测全角字符（禁半角替换）。"""
        group = L5.AGING_GROUPS_L52
        assert len(group) == 1 and group[0].group_header_cell == "T8"
        segs = group[0].segments
        assert len(segs) == 5
        assert [s[0] for s in segs] == [
            "agingWithin6m", "aging6to12m", "aging1to2y", "aging2to3y", "agingOver3y",
        ]
        assert [s[1] for s in segs] == ["T", "U", "V", "W", "X"]
        labels = [s[2] for s in segs]
        assert labels == ["6个月以内", "6-12月", "1～2年", "２～3年", "3年以上"]
        # 模板实测字符与声明逐字一致（全角 ～=U+FF5E / ２=U+FF12）
        assert ws["V9"].value == "1～2年" and ord("1～2年"[1]) == 0xFF5E
        assert ws["W9"].value == "２～3年" and ord("２～3年"[0]) == 0xFF12
        for col, label in zip(["T", "U", "V", "W", "X"], labels):
            assert ws[f"{col}9"].value == label

    def test_managed_sheet_has_no_bare_if_but_workbook_does(self, wb, ws) -> None:
        """受管表零裸 IF（bare_IF=0，不需 neutralize），整册裸 IF 仅 审定表L5-1 12 格。"""
        assert _count_bare_if(ws) == 0
        total = sum(_count_bare_if(wb[n]) for n in wb.sheetnames)
        assert total == 12 and _count_bare_if(wb["审定表L5-1"]) == 12


# ═══════════════════════════════════════════════════════════════════════════
# 契约
# ═══════════════════════════════════════════════════════════════════════════


class TestContract:
    def test_disk_and_source_are_locked(self) -> None:
        contract = L5.assert_contract_file_matches_source()
        assert contract.canonical_sha256 == canonical_digest(L5.build_contract_payload())

    def test_payload_parses_with_two_tables_one_sheet(self) -> None:
        p = L5.build_contract_payload()
        parse_contract(dict(p), adapter_id=L5.ADAPTER_ID)
        assert p["review_status"] == "reviewed"
        assert p["review"]["entry_id"] == L5.ENTRY_ID
        assert len(p["sheets"]) == 1
        tables = p["sheets"][0]["tables"]
        assert len(tables) == 2
        assert [t["uuid_col"] for t in tables] == ["AD", "AE"]
        for t in tables:
            assert t["header_rows"] == 2 and t["anchor"] == "A8"
            assert t["footer_anchor"]["search_column"] == "A"
            assert len(t["fields"]) == 24  # 19 标量 + 5 账龄

    def test_formula_mask_seven_cols_per_region(self) -> None:
        tables = L5.build_contract_payload()["sheets"][0]["tables"]
        assert tables[0]["formula_mask"] == [
            "E11:E15", "L11:L15", "M11:M15", "N11:N15", "O11:O15", "R11:R15", "S11:S15",
        ]
        assert tables[1]["formula_mask"] == [
            "E18:E22", "L18:L22", "M18:M22", "N18:N22", "O18:O22", "R18:R22", "S18:S22",
        ]
        formula_keys = {
            f["json_pointer"].rsplit("/", 1)[-1]
            for f in tables[0]["fields"] if f["mode"] == "formula"
        }
        assert formula_keys == {
            "endBalance", "auditedBeginning", "auditedDebit", "auditedCredit",
            "auditedEnding", "disclosureBeginning", "disclosureEnding",
        }

    def test_html_store_single_item_and_section_declared(self) -> None:
        review = L5.build_contract_payload()["review"]
        hs = review["html_store"]
        assert hs["item_id"] == "L5-L5-2-rows"
        assert hs["row_identity_key"] == "key"
        assert sorted(hs["html_only_keys"]) == sorted(L5.HTML_ONLY_ROW_KEYS)
        assert review["row_sections"]["field"] == "section"
        assert review["row_sections"]["values"] == ["saleLeaseback", "installment"]

    def test_derived_readonly_sheet_declared(self) -> None:
        drs = L5.build_contract_payload()["review"]["derived_readonly_sheet"]
        assert drs["excel_name"] == "审定表L5-1"
        assert "明细表L5-2" in drs["reason"]

    def test_routes_through_common_skeleton(self) -> None:
        assert L5.EntrySelectionError is L.LEntrySelectionError
        assert L5.build_contract_payload() == L.build_contract_payload(L5.IDENTITY, L5.SPECS)


# ═══════════════════════════════════════════════════════════════════════════
# 三区 store 门面
# ═══════════════════════════════════════════════════════════════════════════


class TestTwoRegionStoreFacade:
    def _payload(self) -> str:
        # 含一行 section=other（R24 其他段）：它不对应任何受管区 ⇒ iter/projection 不收它，
        # split 归入未知桶 "" —— 坐实「其他段作静态骨架、不进受管区」。
        return json.dumps([
            {"key": "l52det-a", "section": "saleLeaseback", "payableName": "甲", "beginning": 100},
            {"key": "l52det-b", "section": "installment", "payableName": "乙", "beginning": 200},
            {"key": "l52det-c", "section": "other", "payableName": "丙", "beginning": 300},
        ], ensure_ascii=False)

    def test_iter_store_rows_concats_two_managed_sections_only(self) -> None:
        rows = list(L5.iter_store_rows(self._payload()))
        ids = [rid for rid, _ in rows]
        assert ids == ["l52det-a", "l52det-b"]  # other 不进任何受管区

    def test_split_by_section_other_goes_to_unknown_bucket(self) -> None:
        buckets = L5.split_store_payload_by_section(self._payload())
        assert {k: len(v) for k, v in buckets.items() if v} == {
            "saleLeaseback": 1, "installment": 1, "": 1,  # other → 未知桶
        }

    def test_build_projection_merges_two_managed_sections(self) -> None:
        contract = L5.load_contract_from_disk()
        proj = L5.build_store_projection(self._payload(), contract=contract)
        # 两段各 1 行（other 不收）⇒ row_keys 覆盖两个 table_key，各 1 行
        assert sum(len(v) for v in proj.row_keys.values()) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 注册
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistration:
    def test_provider_aliases_present(self) -> None:
        assert L5.publish_pilot_definitions is L5.publish_definitions
        assert L5.attach_pilot_adapters is L5.attach_adapters
        assert L5.PILOT_WP_CODES == frozenset({"L5L"})

    def test_store_registry_entry(self) -> None:
        from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

        plan = STORE_MERGE_REGISTRY["l5.long_term_payables"]
        assert plan.provider_module == "phase5_l5_long_term_payables"
        assert [i.item_id for i in plan.items] == ["L5-L5-2-rows"]
        assert plan.oo_crash_neutralization_fn == "neutralize_oo_crash_if_formulas"

    def test_whitelist_and_ledger_are_paired(self) -> None:
        from app.services.workpaper_sync.adapters import registry as R
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        mod = "app.services.workpaper_sync.phase5_l5_long_term_payables"
        assert mod in R._ALLOWED_PROVIDER_MODULES
        rows = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == "l5.long_term_payables"]
        assert len(rows) == 1 and rows[0]["provider_module"] == mod

    def test_l_cycle_whitelist_ledger_counts_paired(self) -> None:
        """配对不变式：L 域白名单条数 == ledger 的 L 条数（现 7→8）。"""
        from app.services.workpaper_sync.adapters import registry as R
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        wl_l = [m for m in R._ALLOWED_PROVIDER_MODULES if ".phase5_l" in m and "_cycle_common" not in m]
        ledger_l = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if re.match(r"l\d", str(r["contract_id"]))]
        assert len(wl_l) == len(ledger_l) == 8, (len(wl_l), len(ledger_l))

    def test_wp_code_adjudication_targets_whole_workbook_code(self) -> None:
        doc = json.loads(
            (ROOT / "backend/data/workpaper_sync_entry_wp_code_adjudication.json").read_text("utf-8")
        )
        row = next(a for a in doc["adjudications"] if a["entry_id"] == L5.ENTRY_ID)
        assert row["wp_codes"] == ["L5"] and row["contract_id"] == L5.ADAPTER_ID
        assert row["basis"]["heuristic_would_say"] == ["L5L"]


# ═══════════════════════════════════════════════════════════════════════════
# HTML 侧对齐（前端 json 键 == 契约 json_pointer 段）
# ═══════════════════════════════════════════════════════════════════════════


class TestHtmlAlignment:
    def test_store_item_id_and_minter_agree(self) -> None:
        ts = DETAIL_TS.read_text("utf-8")
        assert f"'{L5.STORE_ITEM_ID}'" in ts
        assert "newRowIdentity('l52det')" in ts
        assert "l5-detail-${Date.now()}" not in ts

    def test_html_only_keys_match_frontend(self) -> None:
        """后端 html_only 键必须与前端 L5_HTML_ONLY_KEYS 逐值一致。"""
        ts = DETAIL_TS.read_text("utf-8")
        block = ts.split("export const L5_HTML_ONLY_KEYS = [", 1)[1].split("]", 1)[0]
        frontend = set(re.findall(r"'(\w+)'", block))
        assert frontend == set(L5.HTML_ONLY_ROW_KEYS)

    def test_frontend_row_keys_cover_every_contract_field(self) -> None:
        src = DETAIL_TS.read_text("utf-8")
        iface = src.split("export interface L5DetailRow {", 1)[1].split("\n}", 1)[0]
        frontend = set(re.findall(r"^\s+(\w+)\s*[?]?:", iface, re.M))
        contract = {
            f["json_pointer"].rsplit("/", 1)[-1]
            for t in L5.build_contract_payload()["sheets"][0]["tables"]
            for f in t["fields"]
        }
        assert contract - frontend == set(), f"契约有、前端缺：{sorted(contract - frontend)}"


# ═══════════════════════════════════════════════════════════════════════════
# 真库：干净命名空间
# ═══════════════════════════════════════════════════════════════════════════


class TestRealDbNamespace:
    def test_managed_namespace_is_clean(self) -> None:
        rows = _query(
            "SELECT count(*) FILTER (WHERE item_id = 'L5-L5-2-rows'), "
            "count(*) FILTER (WHERE item_id LIKE 'L5-L5-2-row-%') FROM checklist_responses"
        )
        full_data, old_positional = rows[0]
        assert old_positional == 0, "L5-2 旧 per-row 键有真数据 ⇒ 切换前须先核对"
        assert full_data == 0, "受管表两区同键从未录入，应 0 行"


# ═══════════════════════════════════════════════════════════════════════════
# 🔴 平台 observer 同键多区消歧（spec T7 根因修复 —— L5 两区同键首次真实命中逼出）
#
# 修改文件：`published_identity_observer.PublishedIdentityObserver._build_identity_binding`
# + 新增 `_primary_table_key_by_frozen_table_name` / `_resolve_provider_for_contract`。
# 受影响面：所有「同一 sheet_key 下多张 row_identity 表」的 entry（当前真实命中仅 L5；
# G9 范式 manifest_capability_enabled()==False、从未翻、不走此路径，改后它若翻 manifest 直接受益）。
# ═══════════════════════════════════════════════════════════════════════════


class TestObserverSameSheetKeyDisambiguation:
    """同 sheet_key 多受管区：用冻结 anchors['table_name'] 选主表 + table_name 对不上仍 fail-closed。"""

    def _observer(self):
        from app.services.workpaper_sync.published_identity_observer import (
            PublishedIdentityObserver,
        )
        # 本测试只调纯函数 `_primary_table_key_by_frozen_table_name`（不碰 DB/字节），
        # 故 observer 的构造依赖用 None 占位即可（该方法不触达它们）。
        return PublishedIdentityObserver.__new__(PublishedIdentityObserver)

    def test_picks_primary_region_by_frozen_table_name(self) -> None:
        """主区 anchors['table_name']=GT_L52_..._R1 ⇒ 选 long_term_payable_rows_r1。"""
        obs = self._observer()
        contract = L5.load_contract_from_disk()
        anchors = {"table_name": "GT_L52_LONG_TERM_PAYABLE_ROWS_R1"}
        matched = ["long_term_payable_rows_r1", "long_term_payable_rows_r2"]
        picked = obs._primary_table_key_by_frozen_table_name(
            contract=contract, anchors=anchors, matched=matched, ctx={},
        )
        assert picked == "long_term_payable_rows_r1"

    def test_picks_second_region_when_anchor_is_r2(self) -> None:
        """若冻结锚点是区② ⇒ 选 long_term_payable_rows_r2（证明不是写死挑第一张）。"""
        obs = self._observer()
        contract = L5.load_contract_from_disk()
        anchors = {"table_name": "GT_L52_LONG_TERM_PAYABLE_ROWS_R2"}
        matched = ["long_term_payable_rows_r1", "long_term_payable_rows_r2"]
        picked = obs._primary_table_key_by_frozen_table_name(
            contract=contract, anchors=anchors, matched=matched, ctx={},
        )
        assert picked == "long_term_payable_rows_r2"

    def test_fail_closed_when_table_name_matches_nothing(self) -> None:
        """🔴 变异证明：table_name 对不上任何一张 ⇒ fail-closed，不得随手挑第一张。"""
        from app.services.workpaper_sync.published_identity_observer import (
            FrozenChildUnusableError,
        )

        obs = self._observer()
        contract = L5.load_contract_from_disk()
        anchors = {"table_name": "GT_L52_BOGUS_TABLE_NAME"}  # 故意传错
        matched = ["long_term_payable_rows_r1", "long_term_payable_rows_r2"]
        with pytest.raises(FrozenChildUnusableError, match="消歧命中 0 张"):
            obs._primary_table_key_by_frozen_table_name(
                contract=contract, anchors=anchors, matched=matched, ctx={},
            )

    def test_fail_closed_when_frozen_table_name_empty(self) -> None:
        """🔴 变异证明：冻结锚点缺 table_name ⇒ fail-closed（空集上不恒真放行）。"""
        from app.services.workpaper_sync.published_identity_observer import (
            FrozenChildUnusableError,
        )

        obs = self._observer()
        contract = L5.load_contract_from_disk()
        with pytest.raises(FrozenChildUnusableError, match="anchors\\['table_name'\\]"):
            obs._primary_table_key_by_frozen_table_name(
                contract=contract, anchors={"table_name": ""},
                matched=["long_term_payable_rows_r1", "long_term_payable_rows_r2"], ctx={},
            )

    def test_resolve_provider_for_contract_maps_adapter_to_module(self) -> None:
        """observer 按 contract_id 经 STORE_MERGE_REGISTRY 解析到 L5 provider 模块。"""
        obs = self._observer()
        contract = L5.load_contract_from_disk()
        provider = obs._resolve_provider_for_contract(contract=contract, ctx={})
        assert provider.__name__.endswith("phase5_l5_long_term_payables")
        assert callable(getattr(provider, "managed_row_table_specs", None))
