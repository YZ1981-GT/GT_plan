# -*- coding: utf-8 -*-
"""test_task47_e_cycle_migration — E 循环 Excel 独立 entry 迁移验证

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 47
Requirements: 6.5, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1

验证 Properties:
  - Property 23: 动态行身份不使用下标（本文件管**登记侧与模板侧**；行为侧由
    `audit-platform/frontend/src/components/workpaper/composables/__tests__/
    e1SyncEntryRowIdentity.spec.ts` 真跑 composable 断言）
  - Property 69: evidence 由逐 scenario 实体与服务端重算闭合
  - Property 70: scenario/evidence 不得跨 entry 或跨场景复用

═══ 本文件的判据都不是「字符串存在」═══

1. **模板判据真读字节**：slice 里冻结的 size/sha256 由 `hashlib` 现算比对，
   `currency_variant_model` 里两个 variant 的 sheet 名、表头行、列数、identity 列
   由 `openpyxl` 真读权威 xlsx 比对 —— 这样「variant 只影响字段集、不影响行身份」
   不是一句声明，而是从源模板派生出来的事实。
2. **manifest 判据真做集合运算**：slice 的 entry 集合必须**恰好等于**按选取规则从
   全量 manifest 算出来的 E 循环 entry 集合。多写一条（凑数）或少写一条（漏迁）都红。
3. **裁决判据是蕴含关系**：`capability` 与 `adapter_id / authority_model /
   definition_bundle / instrumentation_candidate / published_representation` 的空值
   必须自洽；`single_*` 却带 adapter 或 `bidirectional` 却缺 bundle 都红。
4. **删除判据查磁盘真相**：被删文件必须真不在了，宿主的 import 必须真只剩一个。

依赖：
  - backend/data/workpaper_sync_e_cycle_manifest_slice.json（frozen slice）
  - backend/data/workpaper_sync_e_cycle_deletion_plan.json（deletion plan）
  - backend/data/workpaper_sync_entry_manifest.json（source-backed 全量 manifest）
  - backend/data/workpaper_sync_migration_paradigm.json（Task 45 冻结范式）
  - backend/wp_templates/E/*.xlsx（运行时权威模板）
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

import pytest

# ────────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────────
_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]  # D:\GT_plan
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP = FRONTEND / "components" / "workpaper"
COMPOSABLES = WP / "composables"
FE_TESTS = COMPOSABLES / "__tests__"
DATA = ROOT / "backend" / "data"
TEMPLATE_DIR = ROOT / "backend" / "wp_templates"
E_TEMPLATE_DIR = TEMPLATE_DIR / "E"

SLICE_PATH = DATA / "workpaper_sync_e_cycle_manifest_slice.json"
DELETION_PLAN_PATH = DATA / "workpaper_sync_e_cycle_deletion_plan.json"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
D_SLICE_PATH = DATA / "workpaper_sync_d_cycle_manifest_slice.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"

E1_HOST = WP / "GtE1MonetaryFund.vue"
DEAD_COMPOSABLE = COMPOSABLES / "useE1DualMode.ts"
DEAD_COMPOSABLE_SPEC = FE_TESTS / "useE1DualMode.spec.ts"
SHARED_DUAL_MODE = COMPOSABLES / "useG1DualMode.ts"
IDENTITY_GUARD = FE_TESTS / "e1SyncEntryRowIdentity.spec.ts"
VARIANT_GUARD = FE_TESTS / "e1BankVariantIntegrity.spec.ts"

#: 裁决为 `single_*` 时必须为空的五个身份字段（Requirement 12.1 / 12.8 / 12.9）。
_MUST_BE_NULL_FOR_SINGLE = (
    "adapter_id",
    "authority_model",
    "definition_bundle",
    "instrumentation_candidate",
    "published_representation",
)

#: 行身份禁用形态（Requirement 6.5 / Property 23）。
_FORBIDDEN_IDENTITY_KINDS = frozenset(
    {"index", "ordinal", "position", "row_number", "array_index"}
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────
def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return _load(SLICE_PATH)


@pytest.fixture(scope="module")
def deletion_plan() -> dict:
    return _load(DELETION_PLAN_PATH)


@pytest.fixture(scope="module")
def paradigm() -> dict:
    return _load(PARADIGM_PATH)


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    return _load(FULL_MANIFEST_PATH)


@pytest.fixture(scope="module")
def e_entry(slice_doc: dict) -> dict:
    entries = slice_doc["independent_entries"]
    assert len(entries) == 1, "E 循环冻结 slice 应恰好一个独立 entry"
    return entries[0]


def _is_e_cycle_xlsx_entry(entry: dict) -> bool:
    """slice 的选取规则，与 slice_scope.selection_rule 一字不差地对应。

    刻意写成**可执行的**规则而不是抄一份 entry_id 名单：抄名单时，全量 manifest
    新增一个 E 循环 entry 不会让任何测试打红（漏迁不可见）。
    """
    if entry.get("document_type") != "xlsx":
        return False
    patterns = entry.get("wp_match", {}).get("wp_code_patterns") or []
    if any(str(p).upper().startswith("E") for p in patterns):
        return True
    host = str(entry.get("host_path") or "")
    return re.match(r"^GtE\d", host.split("/")[-1]) is not None


# ═══════════════════════════════════════════════════════════════════════════
# Property 23：行身份（登记侧 + 模板侧）
# ═══════════════════════════════════════════════════════════════════════════
class TestProperty23RowIdentityNotIndex:
    """**Validates: Requirements 6.5**

    动态行 SHALL 使用模板行 key 或 row_uuid；不得使用数组下标作为持久化身份。
    """

    def test_every_dynamic_table_declares_field_based_identity(self, slice_doc: dict) -> None:
        tables = slice_doc["dynamic_row_identity"]["tables"]
        assert tables, "E 循环有两张动态行表，slice 不得为空"
        for table in tables:
            identity = table["row_identity"]
            assert identity["kind"] in ("field", "template_row_key"), (
                f"{table['table_key']} 的 row_identity.kind={identity['kind']!r} 非法 —— "
                "只能是 field / template_row_key"
            )
            assert identity["kind"] not in _FORBIDDEN_IDENTITY_KINDS

    def test_identity_template_has_no_index_placeholder(self, slice_doc: dict) -> None:
        """id 模板里不得出现下标类占位（`{index}` / `{seq}` / `{i}`）。"""
        for table in slice_doc["dynamic_row_identity"]["tables"]:
            template = table["row_identity"]["template"]
            placeholders = set(re.findall(r"\{(\w+)\}", template))
            assert placeholders, f"{table['table_key']} 的 id 模板没有任何占位符 —— 写死了行身份"
            forbidden = placeholders & {"index", "i", "seq", "ordinal", "row", "n"}
            assert not forbidden, (
                f"{table['table_key']} 的 id 模板 {template!r} 含下标类占位 {sorted(forbidden)}"
            )
            assert "account" in template, (
                f"{table['table_key']} 的 id 模板 {template!r} 未由账号派生"
            )

    def test_identity_field_is_account_number(self, slice_doc: dict) -> None:
        for table in slice_doc["dynamic_row_identity"]["tables"]:
            identity = table["row_identity"]
            assert identity["identity_field"] == "account_no"
            assert identity["identity_fallback_field"] == "account_code"
            assert "下标" in identity["duplicate_policy"], (
                "去重策略必须显式声明「不改用下标」，否则重复账号会退化成位置身份"
            )

    def test_identity_is_variant_independent(self, slice_doc: dict) -> None:
        for table in slice_doc["dynamic_row_identity"]["tables"]:
            assert table["variant_independent_identity"] is True, (
                f"{table['table_key']} 的行身份不得与 variant 耦合"
            )

    def test_forbidden_row_count_patterns_registered(self, slice_doc: dict) -> None:
        """写死行数/列数的反模式必须被登记（平台已登记的两类）。"""
        forbidden = slice_doc["dynamic_row_identity"]["forbidden_row_count_patterns"]
        joined = " ".join(forbidden)
        assert "blankRows" in joined, "写死骨架行数的反模式必须登记"
        assert "列数" in joined, "写死列数的反模式必须登记"

    def test_seed_builders_and_consumers_exist_on_disk(self, slice_doc: dict) -> None:
        """登记的种子构造器/消费方必须是真实存在的文件，且导出登记的符号。

        「文件存在」不够 —— 符号被改名后 slice 会指向一个不存在的函数，而运行时
        由宿主静态 import 保证不会静默失效，但**登记表**会变成第二真源。
        """
        for table in slice_doc["dynamic_row_identity"]["tables"]:
            for path_key, symbol_key in (
                ("seed_builder_path", "seed_builder"),
                ("consumer_path", "consumer"),
            ):
                path = ROOT / table[path_key]
                assert path.is_file(), f"{table['table_key']} 的 {path_key} 不存在: {path}"
                text = path.read_text(encoding="utf-8")
                symbol = table[symbol_key]
                assert re.search(rf"export function {re.escape(symbol)}\b", text), (
                    f"{path.name} 未导出 {symbol} —— slice 登记与源码脱节"
                )

    def test_behaviour_level_identity_guard_exists(self, slice_doc: dict) -> None:
        """行为侧守卫必须存在且归属本任务（结构侧不能替代真跑）。"""
        guard = slice_doc["currency_variant_model"]["zeroing_defect"]["identity_guard"]
        assert guard["owner_task"] == "Task 47"
        path = ROOT / guard["path"]
        assert path == IDENTITY_GUARD and path.is_file(), (
            f"Task 47 的行为侧身份守卫缺失: {guard['path']}"
        )
        text = path.read_text(encoding="utf-8")
        assert "**Validates: Requirements 6.5**" in text, "行为侧守卫必须标注 Requirement 链接"
        # 真跑 composable 而不是扫源码：必须挂载真实组件
        assert "useE1BankDetail(" in text and "mount(" in text, (
            "身份守卫必须真挂载 composable，不能只做源码字符串检查"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 币种 variant 模型 ↔ 权威模板（source-backed，不是声明）
# ═══════════════════════════════════════════════════════════════════════════
class TestCurrencyVariantAgainstAuthoritativeTemplate:
    """**Validates: Requirements 6.5**

    「variant 只影响字段集、不影响行身份」这句话必须从源 xlsx 派生。
    """

    def test_authoritative_template_dir_is_the_only_source(self, slice_doc: dict) -> None:
        tpl = slice_doc["authoritative_templates"]
        assert tpl["root"] == "backend/wp_templates/E"
        assert (ROOT / tpl["root"]).is_dir()
        # 参考副本状态必须如实登记（本工作树里它不存在）
        ref_absent = not (ROOT / "基础数据").exists()
        recorded = tpl["reference_copy_status"] == "absent_from_working_tree"
        assert recorded == ref_absent, (
            "参考副本状态登记与磁盘不符 —— `基础数据/` 是否存在决定能否做两处 size 比对"
        )

    def test_frozen_template_digests_match_disk(self, slice_doc: dict) -> None:
        """size + sha256 现算比对（Requirement 6.10：模板漂移 fail closed）。"""
        for spec in slice_doc["authoritative_templates"]["files"]:
            path = E_TEMPLATE_DIR / spec["name"]
            assert path.is_file(), f"权威模板缺失: {spec['name']}"
            assert path.stat().st_size == spec["size"], (
                f"{spec['name']} size 漂移: 实测 {path.stat().st_size} != 冻结 {spec['size']}"
            )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == spec["sha256"], (
                f"{spec['name']} sha256 漂移: 实测 {digest} != 冻结 {spec['sha256']}"
            )

    def test_lock_files_are_skipped_in_enumeration(self, slice_doc: dict) -> None:
        """`~$` 锁文件不得被当成模板登记（用户开着 WPS 时会出现）。"""
        names = {spec["name"] for spec in slice_doc["authoritative_templates"]["files"]}
        assert not any(n.startswith("~$") for n in names)
        on_disk = {
            p.name for p in E_TEMPLATE_DIR.glob("*.xlsx") if not p.name.startswith("~$")
        }
        assert names == on_disk, (
            f"权威目录清册与磁盘不符：只在磁盘 {sorted(on_disk - names)}，"
            f"只在 slice {sorted(names - on_disk)}"
        )

    def test_variant_sheets_exist_in_authoritative_workbook(self, slice_doc: dict) -> None:
        """两个 variant 的 sheet 名必须在权威 workbook 里真实存在。"""
        openpyxl = pytest.importorskip("openpyxl")
        entry_tpl = next(
            spec
            for spec in slice_doc["authoritative_templates"]["files"]
            if spec.get("belongs_to_entry") == "xlsx/gt-e1-monetary-fund"
            and spec["name"].startswith("E1-1至E1-11")
        )
        wb = openpyxl.load_workbook(E_TEMPLATE_DIR / entry_tpl["name"], read_only=True)
        try:
            assert len(wb.sheetnames) == entry_tpl["sheet_count"]
            for variant in slice_doc["currency_variant_model"]["variants"]:
                assert variant["template_sheet"] in wb.sheetnames, (
                    f"variant {variant['variant']} 声明的 sheet "
                    f"{variant['template_sheet']!r} 不在权威 workbook 里"
                )
        finally:
            wb.close()

    def test_variant_column_counts_and_identity_columns_derived_from_source(
        self, slice_doc: dict
    ) -> None:
        """列数、表头行与 identity 列全部按源 xlsx 现读比对。

        这条是「stable field key 与 variant 解耦」的**源侧证据**：两个 variant 的
        identity 列（开户银行/总账银行名称/银行账号/账户性质）逐字相同，只有金额列
        集不同。任一侧改了都会打红。
        """
        openpyxl = pytest.importorskip("openpyxl")
        entry_tpl = next(
            spec
            for spec in slice_doc["authoritative_templates"]["files"]
            if spec["name"].startswith("E1-1至E1-11")
        )
        wb = openpyxl.load_workbook(E_TEMPLATE_DIR / entry_tpl["name"], data_only=True)
        try:
            identity_label_sets: list[tuple[str, ...]] = []
            max_columns: list[int] = []
            for variant in slice_doc["currency_variant_model"]["variants"]:
                ws = wb[variant["template_sheet"]]
                assert ws.dimensions == variant["dimensions"], (
                    f"{variant['variant']}: 实测 dimensions {ws.dimensions} != 登记 "
                    f"{variant['dimensions']}"
                )
                assert ws.max_column == variant["max_column"], (
                    f"{variant['variant']}: 实测 max_column {ws.max_column} != 登记 "
                    f"{variant['max_column']}"
                )
                labels: list[str] = []
                for coord, expected in variant["identity_columns"].items():
                    actual = ws[coord].value
                    assert actual is not None, f"{variant['variant']}: {coord} 为空"
                    assert str(actual).strip() == expected, (
                        f"{variant['variant']}: {coord} 实为 {actual!r}，登记 {expected!r}"
                    )
                    labels.append(str(actual).strip())
                identity_label_sets.append(tuple(labels))
                max_columns.append(ws.max_column)
                # identity 列必须全部落在登记的 identity_header_row 上
                for coord in variant["identity_columns"]:
                    row = int(re.sub(r"[A-Z]", "", coord))
                    assert row == variant["identity_header_row"], (
                        f"{variant['variant']}: identity 列 {coord} 的行 {row} != 登记 "
                        f"identity_header_row {variant['identity_header_row']}"
                    )
                    assert row in set(variant["header_rows"])
            assert len(identity_label_sets) == 2
            assert identity_label_sets[0] == identity_label_sets[1], (
                "两个 variant 的 identity 列标签必须逐字相同 —— 这是行身份与 variant "
                f"解耦的源侧依据，实测 {identity_label_sets}"
            )
            assert max_columns[0] != max_columns[1], (
                "两个 variant 的 max_column 必须不同（rmb 无原币列）—— 相同则「variant "
                "只影响字段集」这条判据空转"
            )
        finally:
            wb.close()

    def test_foreign_currency_columns_only_in_multi(self, slice_doc: dict) -> None:
        """`has_foreign_currency_columns` 必须由源 xlsx 的 label 现扫决定。

        这是「variant 只影响字段集」最直接的源侧判据：`原币币种` / `期末汇率` / `原币`
        三个 label 在 rmb 版的表头区**一个都不出现**，在 multi 版全出现。只断言
        JSON 里的布尔值等于自己是同义反复。
        """
        openpyxl = pytest.importorskip("openpyxl")
        variants = {v["variant"]: v for v in slice_doc["currency_variant_model"]["variants"]}
        assert variants["rmb"]["has_foreign_currency_columns"] is False
        assert variants["multi"]["has_foreign_currency_columns"] is True
        assert "foreign_currency_columns" not in variants["rmb"]
        assert variants["multi"]["foreign_currency_columns"], "multi 版必须登记原币列坐标"

        entry_tpl = next(
            spec
            for spec in slice_doc["authoritative_templates"]["files"]
            if spec["name"].startswith("E1-1至E1-11")
        )
        wb = openpyxl.load_workbook(E_TEMPLATE_DIR / entry_tpl["name"], data_only=True)
        try:
            for variant in variants.values():
                ws = wb[variant["template_sheet"]]
                lo, hi = variant["foreign_currency_labels_scanned_rows"]
                seen: set[str] = set()
                for row in range(lo, hi + 1):
                    for col in range(1, ws.max_column + 1):
                        value = ws.cell(row=row, column=col).value
                        if value is not None:
                            seen.add(str(value).strip())
                observed = {"原币币种", "期末汇率", "原币"} & seen
                if variant["has_foreign_currency_columns"]:
                    assert observed == {"原币币种", "期末汇率", "原币"}, (
                        f"{variant['variant']}: 登记有原币列，但源模板表头区只见 {observed}"
                    )
                else:
                    assert not observed, (
                        f"{variant['variant']}: 登记无原币列，但源模板表头区出现 {observed}"
                    )
        finally:
            wb.close()

    def test_decoupling_rule_field_sets_are_consistent(self, slice_doc: dict) -> None:
        rule = slice_doc["currency_variant_model"]["decoupling_rule"]["seed_field_sets"]
        assert rule["shared_field_count"] + len(rule["multi_only_fields"]) == (
            rule["multi_field_count"]
        ), "字段集计数自相矛盾"
        assert "fxRate" in rule["multi_only_fields"]
        assert "openingFc" in rule["multi_only_fields"]


# ═══════════════════════════════════════════════════════════════════════════
# 防 variant 切换抹零：修复位置与跨 variant 守卫必须真实存在
# ═══════════════════════════════════════════════════════════════════════════
class TestVariantSwitchZeroingClosed:
    """**Validates: Requirements 6.5**"""

    def test_zeroing_defect_status_is_backed_by_source(self, slice_doc: dict) -> None:
        """登记为 FIXED_AND_GUARDED 时，修复点必须真在源码里。

        判据落在**函数体作用域**上而不是全文 grep：`classifyFxForm` 与
        `recalcRow` 的 multi 分支必须真的存在，且 multi 分支里真的按形态分派。
        """
        defect = slice_doc["currency_variant_model"]["zeroing_defect"]
        assert defect["current_status"] == "FIXED_AND_GUARDED"
        src = (COMPOSABLES / "useE1BankDetail.ts").read_text(encoding="utf-8")
        assert re.search(r"export function classifyFxForm\b", src), (
            "登记的修复点 classifyFxForm 不在 useE1BankDetail.ts 里"
        )
        body = _fn_body(src, "recalcRow")
        assert "variant === 'multi'" in body, "recalcRow 里没有 multi 分支"
        assert "classifyFxForm(row)" in body, (
            "recalcRow 的 multi 分支未按 fx 形态分派 —— 无条件由原币派生就是抹零缺陷本体"
        )
        assert "'base-identity'" in body, "multi 分支缺 base-identity 形态处置"

    def test_fx_form_is_classified_by_currency_not_rate(self, slice_doc: dict) -> None:
        """形态判据必须用 fxCurrency —— 用 fxRate 会把外币待录入误判成本位币恒等。"""
        src = (COMPOSABLES / "useE1BankDetail.ts").read_text(encoding="utf-8")
        body = _fn_body(src, "classifyFxForm")
        assert "isBaseCurrency(" in body and "fxCurrency" in body
        assert not re.search(r"\bisBaseCurrency\([^)]*fxRate", body), (
            "形态判定不得由 fxRate 决定（缺失会回落 1，外币待录入被误判成恒等）"
        )
        notes = slice_doc["currency_variant_model"]["zeroing_defect"]["fix_reason_notes"]
        assert "fxCurrency" in notes and "fxRate" in notes

    def test_cross_variant_guard_exists_and_is_cross_layer(self, slice_doc: dict) -> None:
        guard = slice_doc["currency_variant_model"]["zeroing_defect"]["cross_variant_guard"]
        path = ROOT / guard["path"]
        assert path == VARIANT_GUARD and path.is_file()
        text = path.read_text(encoding="utf-8")
        # 「写入侧 variant × 消费侧 variant」必须真做双重循环，而不是只测单侧
        assert re.search(r"for \(const va of VARIANTS\)", text)
        assert re.search(r"for \(const vb of VARIANTS\)", text)
        assert "mountBankDetail(" in text, "跨层守卫必须真挂载消费侧"

    def test_root_cause_chain_records_all_four_links(self, slice_doc: dict) -> None:
        """根因链必须四环齐全，缺一环就会被后来者当成「只是显示问题」。"""
        chain = slice_doc["currency_variant_model"]["zeroing_defect"]["root_cause_chain"]
        assert len(chain) == 4
        joined = " ".join(chain)
        for token in ("seedFromFourTable", "persist-first", "recalcRow", "fmtAmount"):
            assert token in joined, f"根因链缺少 {token} 这一环"


# ═══════════════════════════════════════════════════════════════════════════
# 裁决自洽 + slice ↔ 全量 manifest（Requirement 12.1 / 12.4）
# ═══════════════════════════════════════════════════════════════════════════
class TestAdjudicationHonesty:
    """**Validates: Requirements 12.1**"""

    def test_slice_entry_set_equals_manifest_derived_set(
        self, slice_doc: dict, full_manifest: dict
    ) -> None:
        """slice 的 entry 集合 == 按选取规则从全量 manifest 算出的集合。"""
        derived = {
            e["entry_id"]
            for e in full_manifest["entries"]
            if _is_e_cycle_xlsx_entry(e) and e.get("independent_entry") is True
        }
        declared = {e["entry_id"] for e in slice_doc["independent_entries"]}
        assert declared == derived, (
            f"slice 与全量 manifest 不符：漏迁 {sorted(derived - declared)}，"
            f"凑数 {sorted(declared - derived)}"
        )
        assert slice_doc["slice_scope"]["independent_entry_count"] == len(derived)

    def test_no_parent_duplicate_in_e_cycle(
        self, slice_doc: dict, full_manifest: dict
    ) -> None:
        dupes = [
            e["entry_id"]
            for e in full_manifest["entries"]
            if _is_e_cycle_xlsx_entry(e) and e.get("independent_entry") is False
        ]
        assert slice_doc["slice_scope"]["parent_duplicate_count"] == len(dupes) == 0

    def test_capability_matches_full_manifest(
        self, slice_doc: dict, full_manifest: dict
    ) -> None:
        full = {e["entry_id"]: e for e in full_manifest["entries"]}
        for entry in slice_doc["independent_entries"]:
            source = full[entry["entry_id"]]
            for field in ("capability", "migration_state", "editability", "room_model",
                          "canonical_resolver", "host_path"):
                assert entry[field] == source[field], (
                    f"{entry['entry_id']} 的 {field} 与全量 manifest 不符："
                    f"slice={entry[field]!r} manifest={source[field]!r}"
                )
            assert entry["scenario_profile_id"] == source["scenario_profile"]["profile_id"]
            assert entry["mount_count"] == source["scenario_profile"]["mount_count"]

    def test_single_capability_implies_all_identity_fields_null(self, e_entry: dict) -> None:
        assert e_entry["capability"].startswith("single_")
        for field in _MUST_BE_NULL_FOR_SINGLE:
            assert e_entry[field] is None, (
                f"裁决为 {e_entry['capability']} 却带 {field}={e_entry[field]!r} —— "
                "single 裁决不得伪造 contract/bundle/candidate/representation"
            )

    def test_adjudication_argues_both_directions(self, e_entry: dict) -> None:
        """裁决必须同时论证「为什么不是 bidirectional」和「为什么不是 single_html」。

        只写一侧时，`single_onlyoffice` 会变成一个没人复核过的默认值。
        """
        adj = e_entry["adjudication"]
        assert adj["honest_capability"] == e_entry["capability"]
        assert len(adj["reason"]) > 40
        assert len(adj["not_bidirectional_because"]) > 20
        assert len(adj["not_single_html_because"]) > 20

    def test_manifest_legacy_reasons_copied_verbatim(
        self, e_entry: dict, full_manifest: dict
    ) -> None:
        source = next(
            e for e in full_manifest["entries"] if e["entry_id"] == e_entry["entry_id"]
        )
        assert e_entry["adjudication"]["manifest_legacy_reasons"] == (
            source["evidence"]["legacy_reasons"]
        )

    def test_summary_counters_match_entries(self, slice_doc: dict) -> None:
        summary = slice_doc["honest_adjudication_summary"]
        entries = slice_doc["independent_entries"]
        caps = [e["capability"] for e in entries]
        assert summary["total_independent"] == len(entries)
        assert summary["adjudicated_as_single_onlyoffice"] == caps.count("single_onlyoffice")
        assert summary["adjudicated_as_single_html"] == caps.count("single_html")
        assert summary["adjudicated_as_bidirectional"] == caps.count("bidirectional")
        assert summary["adjudicated_as_unreachable"] == caps.count("unreachable")
        assert summary["finalized_published_representations"] == sum(
            1 for e in entries if e["published_representation"] is not None
        )
        assert summary["entries_left_unverifiable"] == sum(
            1 for e in entries if e["evidence"]["verification_state"] == "UNVERIFIABLE"
        )

    def test_slice_counters_carry_the_disclaimer(self, slice_doc: dict) -> None:
        """四个 0 计数必须显式说明含义，不得被读成「已具备双向能力」。"""
        counters = slice_doc["honest_adjudication_summary"]["slice_counters"]
        for key in ("unadjudicated", "fake_bidirectional_claimed_verified",
                    "bidirectional_unverified", "stale_evidence"):
            assert counters[key] == 0
        assert "不是" in counters["note"]

    def test_excluded_scope_is_argued(self, slice_doc: dict) -> None:
        """被排除的东西必须写明去哪个 Task，不能悄悄少算。"""
        excluded = slice_doc["slice_scope"]["excluded_from_slice"]
        assert excluded, "E0 函证必须显式排除并说明归属"
        for item in excluded:
            assert "Task" in item["reason"]


# ═══════════════════════════════════════════════════════════════════════════
# Property 69：evidence 逐 entry 且未验收
# ═══════════════════════════════════════════════════════════════════════════
class TestProperty69EvidencePerEntry:
    """**Validates: Requirements 12.10**"""

    def test_evidence_is_unverifiable_with_enumerated_reasons(self, e_entry: dict) -> None:
        ev = e_entry["evidence"]
        assert ev["verification_state"] == "UNVERIFIABLE"
        assert ev["browser_case"] is None
        assert ev["contract_test"] is None
        assert ev["sync_test_run_id"] is None
        assert ev["required_scenario_set_digest"] is None
        assert len(ev["unverifiable_reasons"]) >= 4, (
            "UNVERIFIABLE 必须逐条列出原因，不能只写一句「未验证」"
        )

    def test_unverifiable_reasons_align_with_null_identity_fields(self, e_entry: dict) -> None:
        """UNVERIFIABLE 的原因必须与空身份字段一一对上（防原因表与事实脱节）。"""
        reasons = set(e_entry["evidence"]["unverifiable_reasons"])
        expected_pairs = {
            "instrumentation_candidate": "no_instrumentation_candidate_for_this_entry",
            "definition_bundle": "no_non_null_approved_definition_bundle",
            "published_representation": "no_published_result_representation",
        }
        for field, reason in expected_pairs.items():
            assert (e_entry[field] is None) == (reason in reasons), (
                f"{field} 的空值状态与原因 {reason!r} 的登记不一致"
            )

    def test_full_manifest_has_no_completed_evidence_for_e_entry(
        self, e_entry: dict, full_manifest: dict
    ) -> None:
        source = next(
            e for e in full_manifest["entries"] if e["entry_id"] == e_entry["entry_id"]
        )
        assert source["evidence"]["browser_case"] is None
        assert source["evidence"]["contract_test"] is None
        assert source["adapter_id"] is None

    def test_blocking_preconditions_are_complete_and_argued(self, slice_doc: dict) -> None:
        bps = slice_doc["blocking_preconditions"]
        assert len(bps) >= 4
        ids = [bp["id"] for bp in bps]
        assert len(ids) == len(set(ids)), "BP id 必须唯一"
        for bp in bps:
            assert bp["blocks"], f"{bp['id']} 未说明它阻断什么"
            assert len(bp["what"]) > 15, f"{bp['id']} 的 what 过短"
            assert bp.get("consequence") or bp.get("observable_consequences"), (
                f"{bp['id']} 未写后果 —— 没有后果的阻断项无法被复核"
            )

    def test_bp4_source_refs_point_at_real_symbols(self, slice_doc: dict) -> None:
        """BP-4 登记的 source_refs 必须指向真实文件与真实符号。

        `file#symbol` 形态时，符号必须真的在那个文件里；文件被重构后本条打红，
        逼登记表跟着更新（否则阻断项会指向不存在的代码）。
        """
        bp4 = next(bp for bp in slice_doc["blocking_preconditions"] if bp["id"] == "BP-4")
        assert bp4["status"] == "REGISTERED_NOT_FIXED"
        assert bp4["must_fix_before"]
        assert bp4["why_not_fixed_here"]
        assert bp4["source_refs"], "BP-4 必须给出 source_refs"
        for ref in bp4["source_refs"]:
            rel, _, symbol = ref.partition("#")
            path = ROOT / rel
            assert path.is_file(), f"BP-4 的 source_ref 文件不存在: {rel}"
            if symbol:
                text = path.read_text(encoding="utf-8")
                assert symbol in text, f"BP-4 的 source_ref 符号 {symbol!r} 不在 {rel} 里"


# ═══════════════════════════════════════════════════════════════════════════
# Property 70：不得跨 entry 复用
# ═══════════════════════════════════════════════════════════════════════════
class TestProperty70NoCrossEntryReuse:
    """**Validates: Requirements 12.12**"""

    def test_no_e_cycle_contract_file_exists(self) -> None:
        """裁决为 single 的 entry 不伪造 contract —— 生产清册里不得有 e*.json。"""
        if not CONTRACT_DIR.is_dir():
            return
        offenders = [
            p.name
            for p in CONTRACT_DIR.glob("*.json")
            if not p.name.startswith("_") and re.match(r"^e\d", p.stem.lower())
        ]
        assert not offenders, (
            f"发现 E 循环 contract 文件 {offenders} —— 本 entry 裁决为 single_onlyoffice，"
            "不得伪造 per-entry contract"
        )

    def test_e_entry_absent_from_sibling_slices(self, e_entry: dict) -> None:
        """本 entry 不得同时出现在别的循环 slice 里（重复计数 = 假迁移进度）。"""
        if not D_SLICE_PATH.is_file():
            pytest.skip("D slice 不存在")
        d_ids = {e["entry_id"] for e in _load(D_SLICE_PATH)["independent_entries"]}
        assert e_entry["entry_id"] not in d_ids

    def test_slice_borrows_no_other_entry_identity(self, slice_doc: dict) -> None:
        """slice 全文不得出现其它 entry 的 contract_id / adapter_id。"""
        blob = json.dumps(slice_doc, ensure_ascii=False)
        borrowed = [
            cid
            for cid in ("d2.receivable_detail", "g7.soe_subsidiary_disclosure",
                        "h1.disposal_check", "b60.hour_budget")
            if cid in blob
        ]
        assert not borrowed, f"E slice 引用了其它 entry 的契约身份 {borrowed}"

    def test_isolation_assertions_are_declared(self, slice_doc: dict) -> None:
        iso = slice_doc["cross_entry_isolation"]
        assert len(iso["assertions"]) >= 4
        assert "contract" in iso["rule"] and "evidence" in iso["rule"]

    def test_guards_bind_this_entry_not_a_pilot(self, slice_doc: dict) -> None:
        """两个守卫必须绑本 entry 的真实 composable，不是 pilot 的 scenario。"""
        defect = slice_doc["currency_variant_model"]["zeroing_defect"]
        for guard_key in ("cross_variant_guard", "identity_guard"):
            text = (ROOT / defect[guard_key]["path"]).read_text(encoding="utf-8")
            assert "useE1BankDetail" in text, (
                f"{guard_key} 未绑 E1 的真实 composable"
            )
            for pilot in ("pilot_d2_large_json", "pilot_g7_two_level_dynamic",
                          "pilot_h1_grouped_dynamic"):
                assert pilot not in text, f"{guard_key} 复用了 pilot 实体 {pilot}"


# ═══════════════════════════════════════════════════════════════════════════
# 删除计划：磁盘真相
# ═══════════════════════════════════════════════════════════════════════════
class TestDeletionPlanExecuted:
    """**Validates: Requirements 12.4**"""

    def test_plan_references_paradigm_and_slice(self, deletion_plan: dict) -> None:
        assert deletion_plan["paradigm_ref"] == (
            "backend/data/workpaper_sync_migration_paradigm.json"
        )
        assert deletion_plan["slice_ref"] == (
            "backend/data/workpaper_sync_e_cycle_manifest_slice.json"
        )

    def test_dead_composable_and_spec_are_gone(self, deletion_plan: dict) -> None:
        """登记为 executed 的删除必须在磁盘上真的完成。"""
        entry = deletion_plan["entries"][0]
        for item in entry["legacy_composables_to_delete"]:
            if item["action_status"] != "executed_in_task_47":
                continue
            assert not (ROOT / item["file"]).exists(), (
                f"登记为已删除但文件仍在: {item['file']}"
            )
            companion = item.get("companion_spec")
            if companion:
                assert not (ROOT / companion).exists(), (
                    f"被删 composable 的 spec 未一并删除: {companion}"
                )

    def test_deleted_symbol_has_no_remaining_reference(self, deletion_plan: dict) -> None:
        """删完之后全前端不得再有该符号的引用（否则是构建期断裂）。"""
        entry = deletion_plan["entries"][0]
        for item in entry["legacy_composables_to_delete"]:
            symbol = pathlib.Path(item["file"]).stem
            hits = [
                str(p.relative_to(ROOT))
                for p in FRONTEND.rglob("*.ts")
                if symbol in p.read_text(encoding="utf-8", errors="ignore")
            ] + [
                str(p.relative_to(ROOT))
                for p in FRONTEND.rglob("*.vue")
                if symbol in p.read_text(encoding="utf-8", errors="ignore")
            ]
            assert not hits, f"被删符号 {symbol} 仍被引用: {hits}"

    def test_delete_justification_is_source_backed(self, deletion_plan: dict) -> None:
        entry = deletion_plan["entries"][0]
        for item in entry["legacy_composables_to_delete"]:
            assert item["inbound_production_reference_count"] == 0
            assert item["consumers"] == []
            assert len(item["delete_justification"]) >= 3
            assert item["gated_on_real_oo_verification"] is False
            assert item["gate_exemption_reason"], (
                "免 gate 必须写明理由，否则等于绕过 Task 45 范式"
            )

    def test_shared_dual_mode_is_preserved_with_both_consumers(
        self, deletion_plan: dict
    ) -> None:
        """在用的共享 composable 必须保留，且登记的消费方与源码一致。"""
        preserved = deletion_plan["shared_base_preserved"]
        path = ROOT / preserved["file"]
        assert path == SHARED_DUAL_MODE and path.is_file()
        symbol = "useG1DualMode"
        actual = sorted(
            str(p.relative_to(ROOT)).replace("\\", "/")
            for p in WP.glob("*.vue")
            if re.search(rf"import \{{[^}}]*{symbol}", p.read_text(encoding="utf-8"))
        )
        assert actual == sorted(preserved["remaining_consumers_after_e_cycle"]), (
            f"共享 dual-mode 的消费方登记与源码不符：实测 {actual}"
        )

    def test_localstorage_collision_verdict_is_derived(self, deletion_plan: dict) -> None:
        """localStorage 冲突结论必须由 key 形态推出，不能凭前缀名下结论。"""
        preserved = deletion_plan["shared_base_preserved"]
        src = SHARED_DUAL_MODE.read_text(encoding="utf-8")
        prefix_match = re.search(r"const STORAGE_PREFIX = '([^']+)'", src)
        assert prefix_match, "共享 composable 未声明 STORAGE_PREFIX"
        assert prefix_match.group(1) == preserved["localStorage_prefix"]
        # key 以 wpId 收尾 ⇒ 不会跨底稿冲突；登记结论必须与之一致
        assert re.search(r"STORAGE_PREFIX \+ wpId\.value", src), (
            "key 形态改了 —— localStorage 冲突结论需要重新推导"
        )
        assert preserved["localStorage_collision_verdict"] == "no_actual_collision"

    def test_deferred_path_lists_unblock_preconditions(self, deletion_plan: dict) -> None:
        """未删的在用路径必须写明阻塞原因与解锁条件（不写就是有意驻留还是忘了删分不清）。"""
        entry = deletion_plan["entries"][0]
        deferred = entry["legacy_paths_deferred"]
        assert deferred
        for item in deferred:
            assert item["action"] == "defer"
            assert len(item["defer_reasons"]) >= 2
            assert len(item["unblock_preconditions"]) >= 2
            assert (ROOT / item["file"]).is_file()

    def test_host_still_imports_only_the_shared_dual_mode(self) -> None:
        """宿主的 dual-mode import 必须只剩一个（不得双路并存）。"""
        host = E1_HOST.read_text(encoding="utf-8")
        dual_imports = re.findall(r"import \{[^}]*\b(use\w*DualMode)\b", host)
        assert dual_imports == ["useG1DualMode"], (
            f"E1 宿主的 dual-mode import 应恰为 useG1DualMode，实测 {dual_imports}"
        )

    def test_no_e1_specific_legacy_endpoint_claim_is_checked(
        self, deletion_plan: dict
    ) -> None:
        """「没有 E1 专属半闭环端点」这个结论必须可核：后端不得有 e1 专属 OO 端点。"""
        entry = deletion_plan["entries"][0]
        claim = entry["no_legacy_backend_endpoint_to_delete"]
        assert claim["verdict"] is True
        routers = ROOT / "backend" / "app" / "routers"
        offenders = [
            p.name
            for p in routers.glob("*.py")
            if re.search(r"e1[_-]monetary", p.name, re.IGNORECASE)
        ]
        assert not offenders, f"发现 E1 专属 router {offenders} —— 结论需要重新推导"

    def test_post_delete_verification_does_not_overclaim(self, deletion_plan: dict) -> None:
        post = deletion_plan["post_delete_verification"]
        assert post["required"]
        assert post["not_claimed"], (
            "必须显式声明本任务**没有**做到什么（真实 OO 场景 / 在用路径删除）"
        )
        joined = " ".join(post["not_claimed"])
        assert "UNVERIFIABLE" in joined


# ═══════════════════════════════════════════════════════════════════════════
# 范式合规
# ═══════════════════════════════════════════════════════════════════════════
class TestParadigmCompliance:
    def test_paradigm_frozen_by_task_45(self, paradigm: dict) -> None:
        assert paradigm["schema_version"] == "migration-paradigm:v1"
        assert paradigm["frozen_by"] == "Task 45"

    def test_plan_covers_the_paradigm_steps_it_claims(
        self, deletion_plan: dict, paradigm: dict
    ) -> None:
        """本计划执行/延后的步骤必须落在范式的 7 步之内，不自造步骤。"""
        step_names = {s["name"] for s in paradigm["paradigm"]["steps"]}
        assert "identify_legacy" in step_names
        assert "create_deletion_plan" in step_names
        assert "delete_legacy_composable" in step_names
        assert "run_post_delete_tests" in step_names
        # 计划必须体现「先识别、再计划、后删除、末验证」的顺序
        entry = deletion_plan["entries"][0]
        assert entry["legacy_composables_to_delete"], "identify_legacy 结果不得为空"
        assert deletion_plan["post_delete_verification"]["required"]

    def test_properties_and_requirements_are_declared(
        self, slice_doc: dict, deletion_plan: dict
    ) -> None:
        for doc in (slice_doc, deletion_plan):
            assert doc["properties_verified"] == [23, 69, 70]
            assert doc["requirements_covered"] == [
                "6.5", "12.1", "12.4", "12.10", "12.11", "12.12", "14.1",
            ]


# ────────────────────────────────────────────────────────────────────────────
# 源码截取 helper（花括号配对 + 先跳参数列表；不用固定字符窗口）
# ────────────────────────────────────────────────────────────────────────────
def _fn_body(text: str, name: str) -> str:
    """截 TS 函数体。

    🔴 两段跳，缺一段都会截错：

    1. **跳参数列表** —— 参数里的 `{ x: number }`（对象类型/解构）会骗到「第一个 `{`」；
    2. **跳返回类型注解** —— `): Promise<{ ok: boolean }> {` 的 `{` 在尖括号里，
       必须按角括号深度过滤，否则截到的是返回类型而不是函数体。

    随后按花括号配对截到函数结束。
    """
    m = re.search(rf"function {re.escape(name)}\s*(?:<[^>]*>)?\s*\(", text)
    if m is None:
        raise AssertionError(f"未找到函数 {name}")
    i = m.end() - 1
    depth = 0
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                i += 1
                break
        i += 1
    # 返回类型注解里的 `{` 位于角括号内；按角括号深度过滤后再取函数体开括号。
    angle = 0
    start = -1
    while i < len(text):
        ch = text[i]
        if ch == "<":
            angle += 1
        elif ch == ">":
            angle = max(0, angle - 1)
        elif ch == "{" and angle == 0:
            start = i
            break
        i += 1
    if start < 0:
        raise AssertionError(f"函数 {name} 找不到函数体开括号")
    depth = 0
    for j in range(start, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    raise AssertionError(f"函数 {name} 的花括号未配平")


class TestHelperSelfCheck:
    """helper 自检 —— 防「截错范围导致判据空转」。"""

    def test_skips_return_type_annotation_braces(self) -> None:
        fake = (
            "function f(a: { x: number }): Promise<{ ok: boolean }> {\n"
            "  const marker = 1\n"
            "}\n"
        )
        body = _fn_body(fake, "f")
        assert "marker" in body
        assert "ok: boolean" not in body

    def test_does_not_swallow_next_function(self) -> None:
        fake = (
            "function a(): void {\n  const one = 1\n}\n"
            "function b(): void {\n  const two = 2\n}\n"
        )
        assert "one" in _fn_body(fake, "a")
        assert "two" not in _fn_body(fake, "a")

    def test_raises_when_missing(self) -> None:
        with pytest.raises(AssertionError):
            _fn_body("const x = 1", "nope")
