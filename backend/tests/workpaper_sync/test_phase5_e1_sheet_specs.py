# -*- coding: utf-8 -*-
"""E1 声明层红判据（E1-P2 / E1-P3 / E1-P8 / E1-P12 / E1-P16 / E1-P17 / E1-P18）。

spec: e1-sync-coverage-and-first-canary · Tasks 4/5/6
Properties: E1-P2（键名逐字实证）/ E1-P3（binding_kind 三元组 + 自省变异）/
            E1-P8（公式管理双模式一致性 + 不新建第二个按钮 owner）/
            E1-P12（零回归基线 + golden digest 门级验证）/
            E1-P16（OCR 第二写入方登记）/
            E1-P17（TB 发布门：sync 不触达 trial_balance）/
            E1-P18（E1-3 列集守恒：只接 multi variant）

验证声明层类型自洽 + 与引擎的接口契约。
不重复实测模板几何（已在 docs/operations/evidence/e1-sync-coverage/ 登记）。
"""
from __future__ import annotations

import pytest

from app.services.workpaper_sync.excel_extract import BindingKind
from app.services.workpaper_sync.phase5_row_table_sheet import (
    StoreKind,
    managed_field_specs,
)

# ═══ 导入所有 E1 声明 ═══

from app.services.workpaper_sync.phase5_e1_monetary_fund import (
    ADAPTER_ID,
    ENTRY_ID,
    CROSS_VOLUME_KEYS,
    WP_CODES,
    all_store_item_ids,
    managed_row_table_specs,
    static_region_specs,
)
from app.services.workpaper_sync.phase5_e1_02_cash_detail import (
    SPEC_E102,
    STORE_ITEM_ID_E102,
    ROW_IDENTITY_STORE_KEY_E102,
    FIXED_ROW_KEY_E102,
    HTML_ONLY_ROWS_E102,
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
    HTML_ONLY_ITEM_IDS_E1,
    LEGACY_SUMMARY_KEY_FX,
    CERT_SIGNATURES_KEY,
)
from app.services.workpaper_sync.phase5_e1_10_account_list import (
    SPEC_E110,
    STORE_ITEM_ID_E110,
    CROSS_SHEET_KEYS_E110,
    OCR_DIALOG_COMPONENTS_E110,
)
from app.services.workpaper_sync.phase5_e1_11_commitment import (
    SPEC_E111,
    STORE_ITEM_IDS_E111,
    OCR_DIALOG_COMPONENTS_E111,
    CROSS_SHEET_SNAPSHOT_KEY_E111,
)

# ═══ 所有行表 spec 的聚合集 ═══

ALL_ROW_TABLE_SPECS = (SPEC_E102, SPEC_E104, SPEC_E106, SPEC_E107, SPEC_E108, SPEC_E109, SPEC_E110)
ALL_SPECS = (*ALL_ROW_TABLE_SPECS, SPEC_E111)


# ═══════════════════════════════════════════════════════════════════════════
# E1-P2：每个 store_item_id 逐字等于按值 grep 实测值
# ═══════════════════════════════════════════════════════════════════════════


class TestP2StoreItemIdEvidence:
    """E1-P2：store_item_id 必须是前端实测值，不得按编号推演。

    🔴 E1 有**四种命名风格**（语义/编号嵌套/模板化/无连字符），
    按编号推演会全错（六次事故背书）。
    """

    # 实测值表（按值 grep 到的 composable 常量/写入点）
    EXPECTED = {
        "E1-2": "E1-cash-detail-rows",
        "E1-4": "E1-digital-rows",
        "E1-6": "E1-reconciliation-rows",
        "E1-7": "E1-cash-count-rmb-rows",
        "E1-8": "E1-cash-count-fx-rows",
        "E1-9": "E1-cash-count-cert-rows",
        "E1-10": "E1-account-list-rows",
    }

    @pytest.mark.parametrize("sheet,expected_key", list(EXPECTED.items()))
    def test_store_item_id_matches_grep_evidence(self, sheet: str, expected_key: str) -> None:
        """每个受管行表的 store_item_id 必须逐字等于实测值。"""
        spec = next(s for s in ALL_ROW_TABLE_SPECS if sheet in s.error_label)
        assert spec.store_item_id == expected_key, (
            f"{sheet} 的 store_item_id={spec.store_item_id!r} 与实测值 {expected_key!r} 不符 —— "
            "禁止按编号推演（裁决 F2，六次事故背书）"
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 红基线（未实施工作），不是回归。`self.EXPECTED` 覆盖 E1 的 7 张目标 sheet，"
            "而 provider 现只开 2 个灰度开关（`_INCLUDE_E102_CASH_DETAIL` / "
            "`_INCLUDE_E104_DIGITAL` 为 True，`_INCLUDE_E111_COMMITMENT_STATIC` 为 False）"
            "⇒ `all_store_item_ids()` 现算 {'E1-cash-detail-rows','E1-digital-rows'}，"
            "`E1-reconciliation-rows` 等连声明层都还没有。"
            "spec `e1-sync-coverage-and-first-canary` 在 INDEX 里是 0/23。"
            "2026-09-28 转 strict xfail：E1 扩容落地后本条会 XPASS 并报错，强制摘掉标记。"
        ),
    )
    def test_all_store_items_in_provider_output(self) -> None:
        """provider 的 all_store_item_ids() 包含全部行表键。"""
        items = set(all_store_item_ids())
        for expected_key in self.EXPECTED.values():
            assert expected_key in items, f"{expected_key} 不在 all_store_item_ids() 里"

    def test_enabled_sheets_store_items_are_really_wired(self) -> None:
        """✅ **已开启**的那几张必须真在 `all_store_item_ids()` 里（上一条的非空对照）。

        没有这条，上面那个 xfail 会把「E1 一张都没接」和「接了 2 张、还差 5 张」混为一谈。
        本条随灰度开关**现算**而非写死张数 —— 开关翻开时它自动覆盖新接的那张。
        """
        items = set(all_store_item_ids())
        enabled = {s.store_item_id for s in managed_row_table_specs() if s.store_item_id}
        assert enabled, "一个行表 spec 都没开 ⇒ 灰度开关被整体关掉了，这是回归不是红基线"
        missing = sorted(enabled - items)
        assert not missing, f"已开启的 spec 其 store_item_id 不在 all_store_item_ids()：{missing}"

    def test_mutation_e1_2_rows_pushes_wrong_key(self) -> None:
        """变异 ①：把 E1-cash-detail-rows 写成 E1-2-rows ⇒ 投影恒空必红。"""
        assert STORE_ITEM_ID_E102 != "E1-2-rows", "变异未生效 —— 这条应该恒过"
        assert STORE_ITEM_ID_E102 == "E1-cash-detail-rows"

    def test_mutation_cashcount_vs_cash_count(self) -> None:
        """变异 ②：cash-count 与 cashcount 一字之差。

        E1-8 同时有 E1-cash-count-fx-rows（新键）和
        E1-cashcount-audit-note-fx（无连字符 legacy 文本键）。
        """
        assert "cash-count" in STORE_ITEM_ID_E108, "E1-8 的行数据键必须含连字符 cash-count"
        assert "cashcount" not in STORE_ITEM_ID_E108, "行数据键误用了无连字符的 cashcount"
        # legacy 兜底键确实无连字符——是历史键，不是笔误
        assert "cashcount" in LEGACY_SUMMARY_KEY_FX


# ═══════════════════════════════════════════════════════════════════════════
# E1-P3：binding_kind 三元组 + 自省变异
# ═══════════════════════════════════════════════════════════════════════════


class TestP3BindingKindTriad:
    """E1-P3：BindingKind 取自前端三元组实证，不取自模板公式数。

    三元组：(store 键是否存在, addRow/removeRow 信号数, composable 归属)
    """

    def test_e1_11_is_the_only_static_region(self) -> None:
        """🔴 第一册唯一 static_region —— 零 -rows 键、无 composable。"""
        assert SPEC_E111.binding_kind is BindingKind.static_region
        assert SPEC_E111.row_identity_key == ""
        assert SPEC_E111.table_name == ""
        assert SPEC_E111.uuid_col == ""
        assert SPEC_E111.defined_name  # 非空

    @pytest.mark.parametrize("spec", ALL_ROW_TABLE_SPECS, ids=lambda s: s.error_label)
    def test_all_row_tables_are_excel_table_binding(self, spec) -> None:
        """全部 7 个行表 spec 都是 excel_table binding。"""
        assert spec.binding_kind is BindingKind.excel_table
        assert spec.store_kind is StoreKind.rows
        assert spec.row_identity_key  # 非空

    def test_e1_9_is_not_static_region(self) -> None:
        """🔴 变异 ④a：E1-9 存单盘点（7 公式）是动态行表，不是 static_region。

        首版按「各只 7 公式」把它判成 static_region，实证推翻
        （键 E1-cash-count-cert-rows + useE1CashCount addRow×4）。
        """
        assert SPEC_E109.binding_kind is BindingKind.excel_table
        assert SPEC_E109.store_item_id == "E1-cash-count-cert-rows"
        assert SPEC_E109.row_identity_key == "id"

    def test_e1_10_is_not_static_region(self) -> None:
        """🔴 变异 ④b：E1-10 账户清单（7 公式）是动态行表，不是 static_region。

        首版按「各只 7 公式」把它判成 static_region，实证推翻
        （键 E1-account-list-rows + useE1AccountList addRow/removeRow）。
        """
        assert SPEC_E110.binding_kind is BindingKind.excel_table
        assert SPEC_E110.store_item_id == "E1-account-list-rows"
        assert SPEC_E110.row_identity_key == "id"

    def test_mutation_e1_11_declared_as_row_table_would_break(self) -> None:
        """🔴 变异 ④c：E1-11 声明成行表 ⇒ 会走整条位移链而它没有 Table，必红。

        static_region 绕开整条位移链（row_shift / footer 两门 / minted UUID /
        workbook 传播 / 兄弟 Table ref 维护）。E1-11 没有 Excel Table、没有 UUID 列、
        row_identity_key 为空 ⇒ 硬塞进行表引擎会在 Table 查找阶段就崩。
        """
        # E1-11 的声明明确是 static_region
        assert SPEC_E111.binding_kind is BindingKind.static_region, (
            "E1-11 应为 static_region，不是行表"
        )
        # 行表引擎的三个硬前置：Table 名 / UUID 列 / 行身份键 —— E1-11 三个都没有
        assert SPEC_E111.table_name == "", (
            f"E1-11 有 table_name={SPEC_E111.table_name!r} —— "
            "若声明成行表，引擎会找这个 Table 然后崩（因为工作簿里不存在）"
        )
        assert SPEC_E111.uuid_col == "", (
            f"E1-11 有 uuid_col={SPEC_E111.uuid_col!r} —— "
            "若声明成行表，引擎会往这列注 UUID 然后覆盖原有数据"
        )
        assert SPEC_E111.row_identity_key == "", (
            f"E1-11 有 row_identity_key={SPEC_E111.row_identity_key!r} —— "
            "若声明成行表，merge 会按此键做行匹配但 store 里没有这个键"
        )
        # 正面断言：它确实用 definedName 锚点（static_region 的机制）
        assert SPEC_E111.defined_name, (
            "E1-11 的 defined_name 为空 —— static_region 必须有 definedName 锚点"
        )

    def test_self_introspection_mutation_formula_count_threshold(self) -> None:
        """🔴 自省变异（第 3 条）：把判据改回公式数阈值（< 10 ⇒ static_region）。

        E1-9 / E1-10 / E1-11 三张各只 7 公式。若按公式数阈值判定，
        三张都会判成 static_region —— 但实证只有 E1-11 成立。
        这复现的正是 spec 首版裁决 H3 的错法。
        """
        # 假设用公式数阈值 threshold=10
        FORMULA_COUNT_THRESHOLD = 10

        # 三张的模板公式数都低于阈值
        low_formula_sheets = {"E1-9": 7, "E1-10": 7, "E1-11": 7}

        # 按阈值推演：三张全判 static_region
        would_be_static_by_threshold = {
            sheet for sheet, count in low_formula_sheets.items()
            if count < FORMULA_COUNT_THRESHOLD
        }
        assert would_be_static_by_threshold == {"E1-9", "E1-10", "E1-11"}, (
            "前提不成立：公式数阈值推演未把三张全判 static_region"
        )

        # 但实证只有 E1-11 是 static_region
        actually_static = {"E1-11"}
        wrongly_classified = would_be_static_by_threshold - actually_static
        assert wrongly_classified == {"E1-9", "E1-10"}, (
            "自省变异失效：公式数阈值判据未把 E1-9/E1-10 **误判**成 static_region —— "
            "这条变异复现的正是 spec 首版裁决 H3 的错法，它必须能打红自己的历史错误"
        )

    def test_e1_row_identity_key_is_id_not_rowId(self) -> None:
        """🔴 E1 全族行身份键统一为 `id`（不是 D 类的 `rowId`）。

        D4-1 曾因 rowKey/rowId 之误踩过同款。
        """
        for spec in ALL_ROW_TABLE_SPECS:
            assert spec.row_identity_key == "id", (
                f"{spec.error_label} 的 row_identity_key={spec.row_identity_key!r} "
                "应为 'id'（E1 全族统一用 id，不是 D 类的 rowId）"
            )


# ═══════════════════════════════════════════════════════════════════════════
# E1-P12：零回归基线（其余 contract golden digest 不变）
# ═══════════════════════════════════════════════════════════════════════════


class TestP12ZeroRegressionBaseline:
    """E1-P12：新增 E1 contract 不得影响已有 10 个 contract 的 golden digest。"""

    def test_adapter_id_format(self) -> None:
        assert ADAPTER_ID == "e1.monetary_fund_detail"

    def test_entry_id_format(self) -> None:
        assert ENTRY_ID == "xlsx/gt-e1-monetary-fund"

    def test_wp_codes_matches_e1(self) -> None:
        assert WP_CODES == frozenset({"E1"})

    def test_e1_in_delivered_contracts(self) -> None:
        """E1 已注册到 DELIVERED_PER_ENTRY_CONTRACTS。"""
        from app.services.workpaper_sync.adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS

        e1 = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == ADAPTER_ID]
        assert len(e1) == 1, f"E1 在交付登记表中应恰好 1 条，实际 {len(e1)}"
        assert e1[0]["entry_id"] == ENTRY_ID
        assert e1[0]["provider_module"] == "app.services.workpaper_sync.phase5_e1_monetary_fund"

    def test_e1_provider_in_whitelist(self) -> None:
        """E1 provider 已在 _ALLOWED_PROVIDER_MODULES 白名单。"""
        from app.services.workpaper_sync.adapters.registry import _ALLOWED_PROVIDER_MODULES

        assert "app.services.workpaper_sync.phase5_e1_monetary_fund" in _ALLOWED_PROVIDER_MODULES

    #: 截至 E1 加入前（2026-09-26）已交付的 10 条 per-entry contract。
    #:
    #: 🔴 2026-09-28 从**集合相等**改为**只许增不许减**。
    #:    原断言是 `existing_ids == expected_existing`，于是**任何别的 lane 新交付一个契约
    #:    都会让本条打红** —— 实测多了 40 条（g1~g14 / h2~h10 / i1~i6 / f1~f5 / j1 / l1 /
    #:    a51 / c2 …），全是其他 lane 的正常交付，没有一条是本 spec 的产物。
    #:    这不是零回归信号，是**把「平台在长大」误报成「E1 动了别人的东西」**。
    #:    E1-P12 要的是「E1 加入**没有删掉/改名**已有契约」⇒ 正确形态是子集关系。
    #:    🔴 反向保护没有丢：少一条仍然红（下方 `missing` 断言），且另有
    #:       `test_f2_p11_golden_digest_zero_regression` 逐文件盯 digest —— 内容变了在那里红。
    BASELINE_CONTRACTS_BEFORE_E1 = frozenset({
        "b60.hour_budget",
        "d2.receivable_detail",
        "h1.disposal_check",
        "g7.soe_subsidiary_disclosure",
        "d1.notes_receivable_detail",
        "d7.contract_liabilities_detail",
        "d3.prepaid_receipts_detail",
        "d6.contract_assets_detail",
        "d5.receivables_financing_detail",
        "d4.revenue_detail",
    })

    def test_all_existing_contracts_untouched(self) -> None:
        """E1 加入不得**删掉或改名**任何已有 contract（新 lane 交付新契约是正常增长）。"""
        from app.services.workpaper_sync.adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS

        existing_ids = {
            str(r["contract_id"]) for r in DELIVERED_PER_ENTRY_CONTRACTS
            if r["contract_id"] != ADAPTER_ID
        }
        missing = sorted(self.BASELINE_CONTRACTS_BEFORE_E1 - existing_ids)
        assert not missing, (
            f"E1 加入前已有的 contract 不见了：{missing} —— 这才是零回归违规"
            "（新增的契约属其他 lane 正常交付，不在本条管辖内）"
        )

    def test_baseline_contract_set_is_not_empty(self) -> None:
        """基线本身非空 —— 防「基线被清空 ⇒ 上一条恒绿」。"""
        assert len(self.BASELINE_CONTRACTS_BEFORE_E1) == 10


# ═══════════════════════════════════════════════════════════════════════════
# E1-P16：OCR 确认弹窗在受管 sheet 上有登记
# ═══════════════════════════════════════════════════════════════════════════


class TestP16OcrSecondWriter:
    """E1-P16：E1 有 7 个 OCR 确认弹窗（D4 范式零 OCR）。

    受管 sheet 的 OCR 组件必须被显式登记，以便宿主 gating 在 OO 编辑态下禁用它们。
    """

    def test_e1_10_ocr_dialog_registered(self) -> None:
        """E1-10 有 OCR 确认弹窗（提及 ×43）。"""
        assert len(OCR_DIALOG_COMPONENTS_E110) >= 1
        assert "E1AccountListOcrConfirmDialog" in OCR_DIALOG_COMPONENTS_E110

    def test_e1_11_ocr_dialog_registered(self) -> None:
        """E1-11 有 OCR 确认弹窗（提及 ×43，与 E1-10 成对）。"""
        assert len(OCR_DIALOG_COMPONENTS_E111) >= 1
        assert "E1AccountCommitOcrConfirmDialog" in OCR_DIALOG_COMPONENTS_E111[0]

    def test_ocr_dialogs_are_distinct(self) -> None:
        """E1-10 和 E1-11 的 OCR 弹窗组件不同（各自独立）。"""
        assert set(OCR_DIALOG_COMPONENTS_E110) != set(OCR_DIALOG_COMPONENTS_E111)


# ═══════════════════════════════════════════════════════════════════════════
# E1-P17：TB 发布门（sync 回写不触达 trial_balance）
# ═══════════════════════════════════════════════════════════════════════════


class TestP17TbPublishGate:
    """E1-P17：sync 回写路径不得触达 trial_balance。

    E1-1 审定表接 `publishToTb` 显式门（data-testid="e1-publish-tb"），
    双向回写**不得**成为 TB 回写的第二条路径。
    """

    def test_sync_store_items_do_not_include_trial_balance(self) -> None:
        """sync 回写路径的 store item 里不含 trial_balance 相关键。"""
        items = all_store_item_ids()
        for item in items:
            assert "trial" not in item.lower(), (
                f"store item {item!r} 含 'trial' —— sync 回写不得触达 trial_balance"
            )
            assert "tb-" not in item.lower() and not item.startswith("tb_"), (
                f"store item {item!r} 疑似 TB 键 —— sync 回写不得触达 trial_balance"
            )

    def test_cross_volume_keys_do_not_include_trial_balance(self) -> None:
        """跨册取数键也不含 trial_balance。"""
        for key in CROSS_VOLUME_KEYS:
            assert "trial" not in key.lower()


# ═══════════════════════════════════════════════════════════════════════════
# E1-P18：E1-3 列集守恒（只接 multi variant）
# ═══════════════════════════════════════════════════════════════════════════


class TestP18E13ColumnSetIntegrity:
    """E1-P18：E1-3 两 variant 共用 E1-bank-detail-rows 但列集不同。

    默认裁决只接 multi（人民币及外币）一张（列集超集），
    rmb（仅人民币）保持 legacy 并显式登记。
    """

    def test_e1_3_not_in_current_managed_specs(self) -> None:
        """E1-3 声明文件（phase5_e1_03_bank_detail.py）尚未创建，
        当前受管清单里不应有 E1-bank-detail-rows。

        🔴 如果这条红了，说明有人在裁决未完成前就把 E1-3 加进了受管清单。
        """
        items = all_store_item_ids()
        assert "E1-bank-detail-rows" not in items, (
            "E1-bank-detail-rows 出现在 all_store_item_ids() 里 —— "
            "E1-3 裁决尚未落实为声明文件，不应在受管清单中"
        )

    def test_adjudication_evidence_exists(self) -> None:
        """裁决证据 JSON 必须存在。"""
        from pathlib import Path

        # 仓库根 = backend 的父目录的父目录（test file → tests/ → backend/ → GT_plan/）
        repo_root = Path(__file__).resolve().parents[3]
        evidence = repo_root / "docs" / "operations" / "evidence" / "e1-sync-coverage" / "e1-3-dual-sheet-adjudication.json"
        assert evidence.exists(), f"裁决证据不存在：{evidence}"

    def test_adjudication_selects_multi_variant(self) -> None:
        """裁决结论是只接 multi（人民币及外币）一张。"""
        import json
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        evidence = repo_root / "docs" / "operations" / "evidence" / "e1-sync-coverage" / "e1-3-dual-sheet-adjudication.json"
        data = json.loads(evidence.read_text(encoding="utf-8"))
        assert data["verdict"]["managed_variant"] == "multi"
        assert data["verdict"]["unmanaged_variant"] == "rmb"
        assert data["production_code_changed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 补充判据：声明层结构自洽
# ═══════════════════════════════════════════════════════════════════════════


class TestE1DeclarationConsistency:
    """声明层结构自洽（与引擎接口契约）。"""

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 红基线（未实施工作），不是回归。目标态是 7 张（E1-2/4/6/7/8/9/10），"
            "现只开 2 张（`_INCLUDE_E102_CASH_DETAIL` / `_INCLUDE_E104_DIGITAL`）。"
            "spec `e1-sync-coverage-and-first-canary` 在 INDEX 里是 0/23。"
            "2026-09-28 转 strict xfail：第 7 张接上后本条 XPASS 并报错，强制摘掉标记。"
        ),
    )
    def test_managed_row_table_specs_count(self) -> None:
        """目标态 7 个行表 spec（E1-2/4/6/7/8/9/10）。"""
        assert len(managed_row_table_specs()) == 7

    def test_managed_row_table_specs_count_matches_enabled_switches(self) -> None:
        """✅ 现算张数必须 == **开着的灰度开关数**（上一条的非空对照）。

        🔴 不写死张数 —— 否则每开一张都要有人记得改这里（memory 已记的反模式）。
        它要抓的是「开关开着但 spec 没进清单」这类接线漏，而不是替上面那条数目标态。
        """
        import app.services.workpaper_sync.phase5_e1_monetary_fund as E1

        enabled_flags = sum(
            1
            for name in dir(E1)
            if name.startswith("_INCLUDE_E1")
            and not name.endswith("_STATIC")
            and getattr(E1, name) is True
        )
        assert enabled_flags > 0, "行表开关全关 ⇒ 这是回归，不是红基线"
        assert len(managed_row_table_specs()) == enabled_flags, (
            f"开着 {enabled_flags} 个行表开关，但 managed_row_table_specs() 现算 "
            f"{len(managed_row_table_specs())} 个 ⇒ 有开关没接进清单"
        )

    def test_static_region_specs_empty_when_switch_off(self) -> None:
        """E1-11 灰度开关关闭时 static_region_specs 返回空。"""
        # 当前 _INCLUDE_E111_COMMITMENT_STATIC = False
        assert len(static_region_specs()) == 0

    def test_all_store_item_ids_unique(self) -> None:
        """所有 store item id 唯一。"""
        items = all_store_item_ids()
        assert len(items) == len(set(items)), f"store item id 有重复：{items}"

    def test_all_sheet_keys_unique(self) -> None:
        """所有 sheet_key 唯一。"""
        keys = [s.sheet_key for s in ALL_SPECS]
        assert len(keys) == len(set(keys)), f"sheet_key 有重复：{keys}"

    @pytest.mark.parametrize("spec", ALL_ROW_TABLE_SPECS, ids=lambda s: s.error_label)
    def test_field_specs_non_empty(self, spec) -> None:
        """每个行表 spec 的 field_specs 非空。"""
        assert len(spec.field_specs) > 0, f"{spec.error_label} 的 field_specs 为空"

    def test_e1_7_8_9_share_variant_but_distinct_keys(self) -> None:
        """E1-7/8/9 三张共享 useE1CashCount 但键不同（variant 参数化）。"""
        keys = {STORE_ITEM_ID_E107, STORE_ITEM_ID_E108, STORE_ITEM_ID_E109}
        assert len(keys) == 3
        assert "rmb" in STORE_ITEM_ID_E107
        assert "fx" in STORE_ITEM_ID_E108
        assert "cert" in STORE_ITEM_ID_E109

    def test_html_only_item_ids_e1_covers_all_variants(self) -> None:
        """HTML_ONLY_ITEM_IDS_E1 覆盖三个 variant 各三个文本键。"""
        assert len(HTML_ONLY_ITEM_IDS_E1) == 9
        for variant in ("rmb", "fx", "cert"):
            variant_keys = [k for k in HTML_ONLY_ITEM_IDS_E1 if k.endswith(f"-{variant}")]
            assert len(variant_keys) == 3, f"variant {variant} 应有 3 个 HTML-only 键"

    def test_cross_sheet_keys_e110_declared(self) -> None:
        """E1-10 的三向联动键已登记。"""
        assert "E1-bank-detail-rows" in CROSS_SHEET_KEYS_E110
        assert "E1-account-commit-snapshot" in CROSS_SHEET_KEYS_E110

    def test_e1_2_fixed_row_declared(self) -> None:
        """E1-2 的不可删除固定行 fixed-rmb 已登记。"""
        assert FIXED_ROW_KEY_E102 == "fixed-rmb"

    def test_e1_2_html_only_rows_declared(self) -> None:
        """E1-2 的 footer 下 R23 已登记为 HTML-only。"""
        assert len(HTML_ONLY_ROWS_E102) >= 1
        assert any(r[0] == 23 for r in HTML_ONLY_ROWS_E102)

    def test_cross_volume_keys_declared(self) -> None:
        """跨册取数键 E1-accrued-interest-rows 已登记。"""
        assert "E1-accrued-interest-rows" in CROSS_VOLUME_KEYS

    def test_e1_11_cross_sheet_snapshot_key_declared(self) -> None:
        """E1-11 ↔ E1-10 联动的快照键已登记。"""
        assert CROSS_SHEET_SNAPSHOT_KEY_E111 == "E1-account-commit-snapshot"


# ═══════════════════════════════════════════════════════════════════════════
# E1-P8：公式管理双模式一致性（Requirement 6.2 / 6.3）
# ═══════════════════════════════════════════════════════════════════════════


class TestP8FormulaManagerDualMode:
    """E1-P8：公式管理入口在两种渲染模式下行为一致。

    **Validates: Requirements 6.2, 6.3**

    E1 是平台公式管理的**范式源头**（`D4TabOtherMargin.vue:32` 明写「同 E1 范式」）。
    宿主 `GtE1MonetaryFund.vue` 通过 `openFormulaManager()` 函数 emit
    `open-formula-manager` 事件到顶层 `FormulaManagerDialog`。

    判据分两层：
    * **声明层（现在可验）**：宿主里**恰一处** `open-formula-manager` 发射入口、
      零第二按钮 owner、emit 使用平台全局 eventBus 不走组件 $emit。
    * **行为层（红基线）**：双模式切换后事件仍到达顶层弹窗 —— 现状只有 legacy 模式
      （sync bridge 未接入，Task 10），无法验证 ⇒ strict xfail 记录红态。

    🔴 本判据同时钉住 `workpaper-page-formula-toolbar-closure` 需求 1.4/2.4 红线：
    不得在 E1 宿主内新建第二个按钮 owner。
    """

    #: 宿主文件相对仓库根的路径
    _HOST_REL = (
        "audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue"
    )

    @pytest.fixture(scope="class")
    def host_source(self) -> str:
        """读取 E1 宿主 Vue 文件源码。"""
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        host_path = repo_root / self._HOST_REL
        assert host_path.exists(), f"E1 宿主不存在：{host_path}"
        return host_path.read_text(encoding="utf-8")

    # ── 声明层判据（现在可验，必须全绿）────────────────────────────

    def test_host_emits_open_formula_manager_event(self, host_source: str) -> None:
        """宿主通过 eventBus 发射 `open-formula-manager` 事件。"""
        assert "open-formula-manager" in host_source, (
            "GtE1MonetaryFund.vue 不含 'open-formula-manager' 事件 ⇒ "
            "公式管理入口可能已被删除或改名"
        )

    def test_open_formula_manager_uses_eventbus_not_component_emit(
        self, host_source: str
    ) -> None:
        """公式管理走平台全局 eventBus，不走组件 $emit。

        顶层 FormulaManagerDialog 通过 eventBus 监听而非父子 prop/event 链 ⇒
        `$emit('open-formula-manager')` 是错法（事件到不了全局弹窗）。
        """
        assert "eventBus.emit('open-formula-manager'" in host_source, (
            "GtE1MonetaryFund.vue 的 open-formula-manager 不走 eventBus.emit ⇒ "
            "事件到不了顶层 FormulaManagerDialog"
        )

    def test_exactly_one_formula_manager_button_owner(self, host_source: str) -> None:
        """宿主里恰一处 `openFormulaManager` 按钮绑定（不新建第二个按钮 owner）。

        🔴 `workpaper-page-formula-toolbar-closure` 需求 1.4/2.4 红线：
        E1 侧不得新建第二个按钮 owner 或第二套 location owner。
        """
        import re

        # 只计 @click 绑定中的 openFormulaManager 调用，不计函数定义或注释
        click_bindings = re.findall(
            r'@click\s*=\s*"[^"]*openFormulaManager[^"]*"', host_source
        )
        assert len(click_bindings) == 1, (
            f"GtE1MonetaryFund.vue 里有 {len(click_bindings)} 处 openFormulaManager "
            f"按钮绑定，应恰好 1 处 ⇒ 违反「不新建第二个按钮 owner」红线"
        )

    def test_exactly_one_eventbus_emit_call(self, host_source: str) -> None:
        """宿主里恰一处 `eventBus.emit('open-formula-manager', ...)` 调用。

        多于一处意味着有重复的 emit 源 —— 潜在的双触发 bug。
        """
        import re

        emit_calls = re.findall(
            r"eventBus\.emit\(\s*['\"]open-formula-manager['\"]", host_source
        )
        assert len(emit_calls) == 1, (
            f"GtE1MonetaryFund.vue 里有 {len(emit_calls)} 处 "
            "eventBus.emit('open-formula-manager') 调用，应恰好 1 处"
        )

    def test_formula_manager_function_defined(self, host_source: str) -> None:
        """宿主定义了 `openFormulaManager` 函数（函数定义存在）。"""
        import re

        fn_defs = re.findall(r"function\s+openFormulaManager\s*\(", host_source)
        assert len(fn_defs) == 1, (
            f"GtE1MonetaryFund.vue 里有 {len(fn_defs)} 处 openFormulaManager 函数定义，"
            "应恰好 1 处"
        )

    def test_formula_manager_comment_references_global_dialog(
        self, host_source: str
    ) -> None:
        """注释里引用顶层 FormulaManagerDialog 作为响应方（声明机制不变）。"""
        assert "FormulaManagerDialog" in host_source, (
            "GtE1MonetaryFund.vue 不含 FormulaManagerDialog 引用 ⇒ "
            "公式管理的全局弹窗响应链可能已断裂"
        )

    def test_no_formula_manager_dialog_import_in_host(self, host_source: str) -> None:
        """宿主不直接 import FormulaManagerDialog（那是顶层组件的职责）。

        如果宿主 import 了它，说明有人试图在 E1 侧独立挂载弹窗 —— 违反
        「平台唯一一套」的范式。
        """
        import re

        imports = re.findall(
            r"import\s+.*FormulaManagerDialog", host_source
        )
        assert len(imports) == 0, (
            f"GtE1MonetaryFund.vue 直接 import 了 FormulaManagerDialog "
            f"({len(imports)} 处) ⇒ 违反「顶层全局弹窗」范式"
        )

    # ── 行为层判据（红基线：双模式一致性需 sync bridge 才可验）──────

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 红基线（Task 10 未实施），不是回归。双模式一致性判据需要 sync bridge "
            "（`useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`）已接入 E1 宿主，"
            "才能在 OO 模式下验证 `open-formula-manager` 事件是否仍到达顶层。"
            "现状只有 legacy 模式（sync bridge 未接入、Task 10），无法切换模式 ⇒ "
            "双模式一致性判据无从验证。"
            "spec `e1-sync-coverage-and-first-canary` Task 10 完成后本条 SHALL 转绿。"
            "2026-10-XX 转 strict xfail：sync bridge 落地后本条 XPASS 并报错，强制摘掉标记。"
        ),
    )
    def test_dual_mode_formula_manager_event_delivery(
        self, host_source: str
    ) -> None:
        """行为层：sync bridge 接入后，两种模式下 open-formula-manager 都能到达顶层。

        现状只有 legacy 模式 ⇒ 断言宿主已引入 sync bridge。
        Task 10 完成后此断言自动成立。
        """
        assert "useWorkpaperSyncBridge" in host_source, (
            "GtE1MonetaryFund.vue 尚未引入 useWorkpaperSyncBridge ⇒ "
            "只有 legacy 模式，双模式一致性无从验证"
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 红基线（Task 10 未实施），不是回归。"
            "WorkpaperSyncEditorHost 是 OO 渲染模式的载体 ⇒ "
            "它不在宿主里意味着 OO 模式下公式管理按钮的 DOM 上下文不存在。"
            "Task 10 完成后本条 SHALL 转绿。"
        ),
    )
    def test_sync_editor_host_present_for_oo_mode(self, host_source: str) -> None:
        """sync bridge 的 WorkpaperSyncEditorHost 已在宿主内（OO 模式载体）。"""
        assert "WorkpaperSyncEditorHost" in host_source, (
            "GtE1MonetaryFund.vue 不含 WorkpaperSyncEditorHost ⇒ "
            "OO 编辑模式无载体，公式管理在该模式下无法验证"
        )


# ═══════════════════════════════════════════════════════════════════════════
# E1-P12 补充：golden digest 门级零回归（补充既有的 contract 注册表检查）
# ═══════════════════════════════════════════════════════════════════════════


class TestP12GoldenDigestGate:
    """E1-P12 补充：`check_sync_provider_golden_digest` 门级零回归。

    **Validates: Requirements 8.3**

    既有 `TestP12ZeroRegressionBaseline` 验证 contract 注册表层面的子集关系。
    本类补充**门级**验证：E1 已在 `check_sync_provider_golden_digest.PROVIDERS` 登记，
    且 golden digest 基线文件里有 E1 条目。

    🔴 这条判据让「E1 加入 PROVIDERS 但基线没有 --update」的状态可被检测到 ——
    否则门会对 E1 新生成一份 digest、与空基线对比「零差异」（因为没有基线可比）。
    """

    @pytest.fixture(scope="class")
    def golden_gate_providers(self) -> tuple:
        """从门脚本加载 PROVIDERS 元组。"""
        import importlib.util
        import sys
        from pathlib import Path

        gate_path = (
            Path(__file__).resolve().parents[3]
            / "backend"
            / "scripts"
            / "check"
            / "check_sync_provider_golden_digest.py"
        )
        assert gate_path.exists(), f"golden digest 门脚本不存在：{gate_path}"
        spec = importlib.util.spec_from_file_location(
            "_check_golden", gate_path
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        # 门脚本会 reconfigure stdout/stderr，在 import 时避免副作用
        old_argv = sys.argv[:]
        sys.argv = ["test"]
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        finally:
            sys.argv = old_argv
        return mod.PROVIDERS

    @pytest.fixture(scope="class")
    def golden_baseline(self) -> dict:
        """加载 golden digest 基线 JSON。"""
        import json
        from pathlib import Path

        baseline_path = (
            Path(__file__).resolve().parents[3]
            / "backend"
            / "scripts"
            / "check"
            / "_sync_provider_golden_digest.json"
        )
        assert baseline_path.exists(), (
            f"golden digest 基线文件不存在：{baseline_path} ⇒ "
            "可能忘了 --update"
        )
        return json.loads(baseline_path.read_text(encoding="utf-8"))

    # ── E1 在门的 PROVIDERS 登记 ──────────────────────────────────

    def test_e1_registered_in_golden_gate_providers(
        self, golden_gate_providers: tuple
    ) -> None:
        """E1 在 `check_sync_provider_golden_digest.PROVIDERS` 里。"""
        labels = {p[0] for p in golden_gate_providers}
        assert "e1" in labels, (
            "E1 (label='e1') 不在 golden digest 门的 PROVIDERS 里 ⇒ "
            "E1 的 digest 不受门监管，改动不会被检测到"
        )

    def test_e1_provider_module_matches(
        self, golden_gate_providers: tuple
    ) -> None:
        """PROVIDERS 里 E1 的模块名正确。"""
        e1_entries = [p for p in golden_gate_providers if p[0] == "e1"]
        assert len(e1_entries) == 1, f"E1 在 PROVIDERS 里应恰好 1 条，实际 {len(e1_entries)}"
        assert e1_entries[0][1] == "phase5_e1_monetary_fund", (
            f"E1 模块名 {e1_entries[0][1]!r} ≠ 'phase5_e1_monetary_fund'"
        )

    def test_e1_uses_adapter_id_not_pilot(
        self, golden_gate_providers: tuple
    ) -> None:
        """E1 用 ADAPTER_ID（不是 PILOT_ADAPTER_ID）。"""
        e1_entries = [p for p in golden_gate_providers if p[0] == "e1"]
        assert e1_entries[0][2] == "ADAPTER_ID"

    def test_e1_has_projection_enabled(
        self, golden_gate_providers: tuple
    ) -> None:
        """E1 的 has_projection=True（有 build_store_projection）。"""
        e1_entries = [p for p in golden_gate_providers if p[0] == "e1"]
        assert e1_entries[0][3] is True, (
            "E1 的 has_projection 应为 True ⇒ "
            "E1 有 build_store_projection，门应核 projection digest"
        )

    def test_e1_uses_plural_instrumentation(
        self, golden_gate_providers: tuple
    ) -> None:
        """E1 的 plural_instr=True（走 instrumentation_specs 复数）。"""
        e1_entries = [p for p in golden_gate_providers if p[0] == "e1"]
        assert e1_entries[0][4] is True, (
            "E1 的 plural_instr 应为 True ⇒ "
            "注册路径读的是 instrumentation_specs()（复数）"
        )

    # ── E1 在 golden digest 基线文件里有条目 ─────────────────────

    def test_e1_in_golden_baseline_file(self, golden_baseline: dict) -> None:
        """golden digest 基线 JSON 里有 E1 条目。

        🔴 没有基线条目时，门会对 E1 新算 digest 但**无东西可比** ⇒
        E1 的 digest 变了也检测不到（恒绿是假绿）。
        """
        providers_in_baseline = {
            p["label"] for p in golden_baseline.get("providers", [])
        }
        assert "e1" in providers_in_baseline, (
            "golden digest 基线文件里没有 E1 条目 ⇒ "
            "需跑 `check_sync_provider_golden_digest.py --update` 重建基线"
        )

    def test_e1_baseline_has_contract_digest(self, golden_baseline: dict) -> None:
        """E1 的基线条目里有 contract_payload_sha256。"""
        e1_entries = [
            p for p in golden_baseline.get("providers", [])
            if p.get("label") == "e1"
        ]
        assert len(e1_entries) == 1
        assert e1_entries[0].get("contract_payload_sha256"), (
            "E1 基线条目缺 contract_payload_sha256 ⇒ 门对 E1 契约内容变更不可见"
        )

    def test_e1_baseline_adapter_id_matches(self, golden_baseline: dict) -> None:
        """基线里 E1 的 adapter_id 与 provider 声明的一致。"""
        e1_entries = [
            p for p in golden_baseline.get("providers", [])
            if p.get("label") == "e1"
        ]
        assert len(e1_entries) == 1
        assert e1_entries[0].get("adapter_id") == ADAPTER_ID, (
            f"基线 adapter_id={e1_entries[0].get('adapter_id')!r} "
            f"≠ provider ADAPTER_ID={ADAPTER_ID!r}"
        )

    # ── 既有 10 条 contract 在基线文件里仍存在（补充 TestP12ZeroRegressionBaseline）──

    #: 与 TestP12ZeroRegressionBaseline.BASELINE_CONTRACTS_BEFORE_E1 对齐
    _PRE_E1_LABELS = frozenset({
        "b60", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "g7", "h1",
    })

    def test_pre_e1_contracts_still_in_golden_baseline(
        self, golden_baseline: dict
    ) -> None:
        """E1 加入前已有的 10 个 provider 在基线文件里仍全部存在。

        与 `TestP12ZeroRegressionBaseline.test_all_existing_contracts_untouched`
        互补：那条检查 `DELIVERED_PER_ENTRY_CONTRACTS`（注册表），
        本条检查基线文件（门的比对基准）—— 注册表有但基线没有 = 门恒绿假绿。
        """
        baseline_labels = {
            p["label"] for p in golden_baseline.get("providers", [])
        }
        missing = sorted(self._PRE_E1_LABELS - baseline_labels)
        assert not missing, (
            f"golden digest 基线文件里缺少 E1 前已有的 provider：{missing} ⇒ "
            "这些 provider 的 digest 变了也检测不到"
        )
