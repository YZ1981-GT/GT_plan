# -*- coding: utf-8 -*-
"""Task 41 守卫变异检验 —— D2 大 JSON 子表 Excel pilot。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 41

覆盖面分母 = 本任务新建的两个守卫文件 + Task 13 的契约目录边界判据。

用法（仓库根）::

    py -3 backend/scripts/diagnose/mutate_task41_d2_large_json_pilot_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task41_d2_large_json_pilot_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task41_d2_large_json_pilot_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task41-d2-large-json-pilot/mutation_report.json

🔴 改**数据文件**（契约 JSON）的变异一律带 `scope_check`：契约里 39 个字段形态高度雷同，
只看「新增失败集合」会把「改到了别的字段」误报成 GREEN（Task 58 的 `_ledger_row_field_is`
是范式）。

🔴 同形态锚点（`"adapter_registered": False,` / `contract = assert_contract_file_matches_source()`
在两处出现）一律用 `scope` + `offset` 相对定位，不用绝对 `line`。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

PD = "backend/app/services/workpaper_sync/pilot_d2_large_json.py"
RG = "backend/app/services/workpaper_sync/adapters/registry.py"
ROUTER = "backend/app/routers/wp_sync_router.py"
CONTRACT = "backend/data/workpaper_sync_contracts/d2.receivable_detail.json"

T41 = "test_task41_d2_large_json_pilot.py"
T41PG = "test_task41_d2_large_json_pilot_pg.py"
T13 = "test_task13_contract_registry.py"

_SEL = f"{T41}::TestFrozenEntrySelection"
_TPL = f"{T41}::TestAuthoritativeTemplate"
_GROUND = f"{T41}::TestContractIsGroundedInTheTemplate"
_LOCK = f"{T41}::TestThreeSourceColumnLock"
_DAG = f"{T41}::TestPublishDagIsOneWay"
_SPLIT = f"{T41}::TestStorePayloadSplit"
_BUDGET = f"{T41}::TestProperty60BudgetsFailVisible"
_SIDECAR = f"{T41}::TestChunkedSidecarAndRoundtrip"
_PROP = f"{T41}::TestPropertyOracleLanding"
_DEBT = f"{T41}::TestUpstreamDebtsAreVisibleFacts"
_BOOL = f"{T41}::TestBooleanCellIsAKnownUpstreamIncoherence"
_ORDER = f"{T41}::TestOrderingGate"
_WIRE = f"{T41}::TestProductionWiring"


# ═══════════════════════════════════════════════════════════════════════════
# 作用域自证回调（数据文件变异必带）
# ═══════════════════════════════════════════════════════════════════════════


def _rows_field(column_key: str, key: str, expected: str):
    """契约 JSON 的行域字段某个键必须**恰好**是 `expected`（改动落在我关心的结构里）。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for table in payload["sheets"][0]["tables"]:
            for field in table["fields"]:
                if field.get("column_key") == column_key:
                    return field.get(key) == expected
        return False

    return check


def _semantic_version_is(expected: str):
    def check(data: bytes) -> bool:
        return json.loads(data.decode("utf-8")).get("semantic_version") == expected

    return check


def _ledger_row_field_is(contract_id: str, key: str, expected_literal: str):
    """交付登记表里 `contract_id` 那一行的某个键必须恰好是 `expected_literal`。

    🔴 `expected_literal` 是 **Python 源码字面量**（`True` / `False` / `"x"`），不是 JSON。
    首轮实测把它写成 `json.dumps(True)` ⇒ 比的是 `true`（小写），而 `registry.py` 里是
    `True` ⇒ 作用域自证恒失败、判定 ANCHOR-MISS（脚本缺陷，不是生产代码问题）。
    """

    def check(data: bytes) -> bool:
        text = data.decode("utf-8")
        anchor = f'"contract_id": "{contract_id}"'
        start = text.find(anchor)
        if start < 0:
            return False
        window = text[start : start + 1600]
        return f'"{key}": {expected_literal}' in window

    return check


MUTATIONS: list[Mutation] = [
    # ── ① 权威模板哨兵（Requirement 9.9）─────────────────────────────
    Mutation(
        id="M01", side="be", path=PD, kind="replace",
        anchor='    "31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa"',
        new='    "31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afb"',
        want=f"{_TPL}::test_template_bytes_are_unchanged",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="模板字节哨兵改一位后仍绿 ⇒ 「backend/wp_templates 运行时只读」无人把守，"
            "后面每个 definition digest 都会对着一份错模板算出来",
        tags=("template",),
    ),
    Mutation(
        id="M02", side="be", path=PD, kind="replace",
        anchor="    if digest != TEMPLATE_SHA256:",
        new="    if False and digest != TEMPLATE_SHA256:",
        want=f"{_TPL}::test_template_sentinel_rejects_a_mutated_workbook",
        why="哨兵比对被短路 ⇒ 模板被运行时改写不再抛，静默按新字节继续发布"
            "（fail-open 掩盖接线错误的形态）",
        tags=("template",),
    ),
    # ── ② 选型必要条件（AC 12.1 / Property 49）───────────────────────
    Mutation(
        id="M03", side="be", path=PD, kind="replace",
        anchor="    assessment = assess_pilot_classes(manifest=payload)[PilotClass.d2_large_json]",
        new="    assessment = assess_pilot_classes(manifest=payload)[PilotClass.simple_checklist]",
        want=f"{_SEL}::test_entry_is_frozen_from_the_source_backed_manifest",
        why="pilot 类边界改成 simple_checklist 后 entry 不在候选里却仍绿 ⇒ 「类边界由 harness "
            "判定」退化成本模块自己声明（Property 49 的分母失守）",
        tags=("selection",),
    ),
    Mutation(
        id="M04", side="be", path=PD, kind="replace",
        anchor='    if not entry.get("independent_entry"):',
        new='    if False and not entry.get("independent_entry"):',
        want=f"{_SEL}::test_selection_fails_closed_on_parent_duplicate",
        why="parent_duplicate 不再被拒 ⇒ 43 条重复入口都能拿到自己的 adapter，"
            "同一 OO room 会被两个 adapter 各写一遍（AC 12.1「每个独立 entry」）",
        tags=("selection",),
    ),
    Mutation(
        id="M05", side="be", path=PD, kind="replace",
        anchor="    if codes != set(PILOT_WP_CODES):",
        new="    if False and codes != set(PILOT_WP_CODES):",
        want=f"{_SEL}::test_selection_fails_closed_on_wp_code_drift",
        why="matcher 域与 entry 的 wp_code 不再双向锁死 ⇒ 宿主新增/删掉一个 wp_code 后 "
            "matcher 会漏匹配或越界匹配，而 registry 的重叠判据看不出来",
        tags=("selection",),
    ),
    Mutation(
        id="M06", side="be", path=PD, kind="replace",
        anchor="    if leaked:",
        scope="def assert_no_implicit_template_fallback(",
        offset=14,
        new="    if False and leaked:",
        want=f"{_SEL}::test_fallback_judgement_fails_closed_on_a_non_empty_resolution",
        why="零回退判据被短路 ⇒ 允许给一个会回退到父级程序表的 entry 发契约，"
            "source_ref 会指向另一份底稿的单元格（本 spec 已付两次学费的形态）",
        tags=("selection",),
    ),
    Mutation(
        id="M07", side="be", path=PD, kind="replace",
        anchor="    if missing:",
        scope="def assert_no_implicit_template_fallback(",
        offset=5,
        new="    if False and missing:",
        want=f"{_SEL}::test_fallback_judgement_fails_closed_on_a_non_empty_resolution",
        why="「缺某个 wp_code 的 finder 实测结果」不再打红 ⇒ 未观测的码被默认放行，"
            "零回退判据在新增 wp_code 时静默失效",
        tags=("selection",),
    ),
    Mutation(
        id="M08", side="be", path=PD, kind="replace",
        anchor="    if resolved is None or Path(str(resolved)).resolve() != authoritative_template_path().resolve():",
        new="    if False and resolved is None:",
        want=f"{_SEL}::test_parent_code_canonical_resolver_lands_on_the_same_workbook",
        why="父码 canonical resolver 落点不再核对 ⇒ 配置声明可以指向另一份 D2 工作簿"
            "（D2-5 分析程序 / D2-6至D2-13 检查）而无人发现",
        tags=("selection",),
    ),
    Mutation(
        id="M09", side="be", path=PD, kind="replace",
        anchor='    if "/".join(str(declared).split("\\\\")) != expected:',
        new='    if False and str(declared) != expected:',
        want=f"{_SEL}::test_selection_fails_closed_when_the_render_schema_points_elsewhere",
        why="配置真源声明的 template_path 不再核对 ⇒ 「据另一份底稿建契约」这条学费再交一次",
        tags=("selection",),
    ),
    Mutation(
        id="M10", side="be", path=PD, kind="replace",
        anchor='    if str(payload.get("wp_code") or "") not in PILOT_WP_CODES:',
        new='    if False and str(payload.get("wp_code") or "") not in PILOT_WP_CODES:',
        # 🔴 首轮实测这条写成了 `_TPL::…` = WRONG-TEST：该测试住在
        #    `TestFrozenEntrySelection` 而不是 `TestAuthoritativeTemplate`。
        #    `--list` / `--check-anchors` 的 want 可定位性检查只比 nodeid **末段**
        #    （方法名），类名写错它查不出来（Task 40 的 M14 同款）。
        want=f"{_SEL}::test_render_schema_wp_code_must_stay_inside_the_matcher_domain",
        why="配置的 wp_code 与 matcher 域脱钩不再打红 ⇒ D2A.yaml 改成别的码后依然被当成"
            "本 entry 的权威声明",
        tags=("selection",),
    ),
    # ── ③ 契约 ↔ 源侧双向锁 ─────────────────────────────────────────
    Mutation(
        id="M11", side="be", path=PD, kind="replace",
        anchor='        "semantic_version": "1.0.0",',
        scope='        "contract_id": PILOT_ADAPTER_ID,',
        offset=1,
        new='        "semantic_version": "1.0.1",',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        why="源侧 payload 变了而磁盘契约没跟着变仍绿 ⇒ 双向锁失效，"
            "契约里的 digest 可以与真实 definition payload 悄悄脱钩",
        tags=("contract",),
    ),
    Mutation(
        id="M12", side="be", path=CONTRACT, kind="replace",
        anchor='              "source_ref": "源xlsx!明细表D2-2!B13",',
        new='              "source_ref": "源xlsx!明细表D2-2!B14",',
        want=f"{_GROUND}::test_every_managed_header_matches_the_real_cell_text",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="磁盘契约的 source_ref 被改到别的数据行仍绿 ⇒ 「逐字段有来源」可被事后篡改",
        scope_check=_rows_field("customer_name", "source_ref", "源xlsx!明细表D2-2!B14"),
        tags=("contract", "data"),
    ),
    Mutation(
        id="M13", side="be", path=CONTRACT, kind="replace",
        anchor='              "header_source_ref": "源xlsx!明细表D2-2!B11",',
        new='              "header_source_ref": "源xlsx!明细表D2-2!B12",',
        want=f"{_GROUND}::test_every_managed_header_matches_the_real_cell_text",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="表头依据被改到空格（B12，两级表头下层）仍绿 ⇒ 表头比对不是对着权威模板真读，"
            "而是自证式同义反复",
        scope_check=_rows_field("customer_name", "header_source_ref", "源xlsx!明细表D2-2!B12"),
        tags=("contract", "data"),
    ),
    Mutation(
        id="M14", side="be", path=CONTRACT, kind="replace",
        anchor='              "group_source_ref": "源xlsx!明细表D2-2!I11",',
        scope='              "column_key": "aging_prior_within1",',
        offset=2,
        new='              "group_source_ref": "源xlsx!明细表D2-2!T11",',
        want=f"{_GROUND}::test_every_aging_group_header_matches_the_real_cell_text",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="账龄组标题依据被改到**另一个组**（期末未审账龄）仍绿 ⇒ 三个账龄组会互相串数据，"
            "而两级表头的组归属无人把守",
        scope_check=_rows_field(
            "aging_prior_within1", "group_source_ref", "源xlsx!明细表D2-2!T11"
        ),
        tags=("contract", "data"),
    ),
    Mutation(
        id="M15", side="be", path=CONTRACT, kind="replace",
        anchor='  "semantic_version": "1.0.0",',
        new='  "semantic_version": "9.9.9",',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        why="顶层 semantic_version 被改仍绿 ⇒ 磁盘契约与源侧脱钩（另一侧的同一条锁）",
        scope_check=_semantic_version_is("9.9.9"),
        tags=("contract", "data"),
    ),
    Mutation(
        id="M16", side="be", path=PD, kind="replace",
        anchor='    ("customer_name", "B", "editable", "text", "customerName", "客户名称"),',
        new='    ("customer_name", "B", "editable", "text", "customerName", "客户名 称"),',
        want=f"{_GROUND}::test_every_managed_header_matches_the_real_cell_text",
        why="登记的表头文本与权威模板实测不符仍绿 ⇒ 期望值不是从源侧推导的",
        tags=("contract",),
    ),
    Mutation(
        id="M17", side="be", path=PD, kind="replace",
        anchor='    "Q": "=E{r}+O{r}-P{r}",',
        new='    "Q": "=E{r}+O{r}+P{r}",',
        want=f"{_GROUND}::test_three_formula_columns_are_really_formulas_in_the_template",
        wants=(f"{_SIDECAR}::test_formula_columns_are_read_as_cached_values_with_formula_inventory",),
        why="登记的公式模板与模板逐格实测不符仍绿 ⇒ 公式篡改检测（Property 24）拿错基线，"
            "OO 侧把 `-P` 改成 `+P` 不会被发现",
        tags=("contract",),
    ),
    Mutation(
        id="M18", side="be", path=PD, kind="replace",
        anchor='    ("end_balance", "Q", "formula", "amount", "endBalance", "期末余额"),',
        new='    ("end_balance", "Q", "editable", "amount", "endBalance", "期末余额"),',
        want=f"{_GROUND}::test_three_formula_columns_are_really_formulas_in_the_template",
        wants=(
            f"{_GROUND}::test_field_counts_are_the_real_template_facts",
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        ),
        why="把真公式列声明成 editable 仍绿 ⇒ 受保护格篡改分类在这一列整条不生效，"
            "OO 侧改 Q 列会覆盖 `=E+O-P` 的结果而无人报冲突",
        tags=("contract",),
    ),
    Mutation(
        id="M19", side="be", path=PD, kind="replace",
        anchor='FOOTER_MARKER: Final[str] = "合计"',
        new='FOOTER_MARKER: Final[str] = "总计"',
        want=f"{_GROUND}::test_footer_marker_is_the_real_cell_text",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="footer 标记与权威模板 A26 实测文本不符仍绿 ⇒ footer 定位找不到锚点，"
            "而 contract 层的形态校验（只查非空）看不出来",
        tags=("contract",),
    ),
    Mutation(
        id="M20", side="be", path=PD, kind="replace",
        anchor='UUID_COL: Final[str] = "AN"',
        new='UUID_COL: Final[str] = "AM"',
        want=f"{_GROUND}::test_uuid_column_sits_right_of_the_managed_business_columns",
        why="隐藏 UUID 列落到受管业务列（AM 备注）上仍绿 ⇒ 注入会覆盖可见业务单元格"
            "（Requirement 6.13）",
        tags=("instrumentation",),
    ),
    Mutation(
        id="M21", side="be", path=PD, kind="replace",
        anchor="LAST_DATA_ROW: Final[int] = 25",
        new="LAST_DATA_ROW: Final[int] = 24",
        want=f"{_GROUND}::test_uuid_column_sits_right_of_the_managed_business_columns",
        wants=(
            f"{_GROUND}::test_three_formula_columns_are_really_formulas_in_the_template",
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        ),
        why="数据区末行少一行仍绿 ⇒ 模板留的可增行（第 25 行 `……` 占位）被排除在受管区域外，"
            "OO 在那里录入的值永远读不回来",
        tags=("instrumentation",),
    ),
    Mutation(
        id="M22", side="be", path=PD, kind="replace",
        anchor="HEADER_LEAF_ROW: Final[int] = 12",
        new="HEADER_LEAF_ROW: Final[int] = 11",
        want=f"{_GROUND}::test_every_managed_header_matches_the_real_cell_text",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="两级表头的二级行退化成一级行仍绿 ⇒ 18 个账龄列的表头依据全指到组标题格，"
            "「1年以内 / 1-2年 …」六段的来源整组失守",
        tags=("contract",),
    ),
    # ── ④ 三源锁（源 xlsx ↔ 契约 ↔ 前端列/账龄真源）───────────────────
    Mutation(
        id="M23", side="be", path=PD, kind="replace",
        anchor='    ("y2to3", "2-3年"),',
        new='    ("y2to3", "2—3年"),',
        want=f"{_LOCK}::test_aging_segments_match_the_frontend_aging_preset",
        wants=(
            f"{_LOCK}::test_aging_leaf_labels_match_the_template_second_level_header",
            f"{_GROUND}::test_every_managed_header_matches_the_real_cell_text",
        ),
        why="账龄段 label 与前端 `PRESET_SEGMENTS.FIVE_YEAR`／模板行 12 不再逐字相等仍绿 ⇒ "
            "账龄真源三方脱钩，OO 侧写回会落到错的账龄段",
        tags=("three-source",),
    ),
    Mutation(
        id="M24", side="be", path=PD, kind="replace",
        anchor='    ("post_payment", "AL", "editable", "amount", "postPayment", "期后回款"),',
        new='    ("post_payment", "AL", "editable", "amount", "postpayment", "期后回款"),',
        want=f"{_LOCK}::test_scalar_columns_match_the_frontend_column_defs_in_order",
        wants=(
            f"{_LOCK}::test_column_keys_are_snake_case_projections_of_the_json_paths",
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        ),
        why="json 路径与前端 `DetailRow` 的键名差一个大小写仍绿 ⇒ 拆分读不到值、回写写不进去，"
            "而「39 个字段都在」的计数判据照样通过（静默丢字段）",
        tags=("three-source",),
    ),
    # ── ⑤ authority model / 发布 DAG ────────────────────────────────
    Mutation(
        id="M25", side="be", path=PD, kind="replace",
        anchor="AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract",
        new="AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.opaque_single_onlyoffice",
        want=f"{_DAG}::test_authority_model_is_projection_contract",
        wants=(f"{_PROP}::test_field_level_properties_are_not_substituted_away",),
        why="authority model 换成 opaque 后仍绿 ⇒ AC 12.12 的「字段级两场景替换」被悄悄触发，"
            "Property 25/26 直接从 required set 里消失，而 D2 的整张大表恰恰只能靠字段级三方",
        tags=("authority",),
    ),
    Mutation(
        id="M26", side="be", path=PD, kind="replace",
        anchor='        "template_definition_sha256": canonical_digest(template_payload),',
        new='        "template_definition_sha256": "0" * 63 + "1",',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        wants=(f"{_DAG}::test_contract_payload_references_both_and_no_bundle",),
        why="契约里的 template digest 不再是真实 payload 的 canonical digest 仍绿 ⇒ "
            "`assert_contract_identity_frozen` 只是在比两个都错的值（单向引用断裂）",
        tags=("dag",),
    ),
    # ── ⑥ 866KB 载荷拆分（AC 6.9 / 6.12）────────────────────────────
    Mutation(
        id="M27", side="be", path=PD, kind="replace",
        anchor="    if not isinstance(raw, str) or not raw.strip():",
        new="    if False and not isinstance(raw, str):",
        want=f"{_SPLIT}::test_missing_row_identity_fails_closed",
        wants=(f"{_GROUND}::test_row_identity_pointer_matching_the_real_store_key_is_load_bearing",),
        why="缺 rowId 不再 fail closed ⇒ 行身份会退回数组下标（Requirement 6.5 / Property 23 "
            "明令禁止），删行再新增后旧身份被复用、数据串到新行",
        tags=("split",),
    ),
    Mutation(
        id="M28", side="be", path=PD, kind="replace",
        anchor="        if identity in seen:",
        new="        if False and identity in seen:",
        want=f"{_SPLIT}::test_duplicate_row_identity_fails_closed",
        why="重复 rowId 不再是结构冲突 ⇒ OO 里复制一行产生的重复 UUID 会静默合并成一行，"
            "两行数据被折叠（Requirement 6.15）",
        tags=("split",),
    ),
    Mutation(
        id="M29", side="be", path=PD, kind="replace",
        anchor="    if not isinstance(rows, list):",
        new="    if False and not isinstance(rows, list):",
        want=f"{_SPLIT}::test_non_array_payload_fails_closed",
        why="整张大表被存成别的形态时不再 fail closed ⇒ 静默当成零行，"
            "1260 行明细在一次 merge 里全部「消失」",
        tags=("split",),
    ),
    Mutation(
        id="M30", side="be", path=PD, kind="replace",
        anchor="        budget.add_row(ROWS_TABLE_KEY)",
        new="        _ = ROWS_TABLE_KEY",
        want=f"{_BUDGET}::test_row_budget_boundaries_on_the_store_split",
        wants=(f"{T41PG}::test_row_budget_boundaries_on_the_real_payload",),
        why="行预算不再边读边判 ⇒ 100000 行的表读完才发现越界，Requirement 14.11 要求的"
            "「不得 OOM 或截断」失守",
        tags=("budget",),
    ),
    Mutation(
        id="M31", side="be", path=PD, kind="replace",
        anchor="            budget.add_field()",
        new="            _ = budget",
        want=f"{_BUDGET}::test_field_budget_boundaries_on_the_store_split",
        wants=(f"{T41PG}::test_field_budget_boundaries_on_the_real_payload",),
        why="field 预算不再计数 ⇒ 200000 field 边界永久不可达（真实载荷 49,140 个字段，"
            "四倍规模的项目会静默吃满内存）",
        tags=("budget",),
    ),
    Mutation(
        id="M32", side="be", path=PD, kind="replace",
        anchor='    return f"{ROWS_TABLE_KEY}/{row_identity}/{column_key}"',
        new='    return f"{ROWS_TABLE_KEY}/{column_key}"',
        want=f"{_SPLIT}::test_split_yields_one_field_per_column_per_row",
        wants=(
            f"{_GROUND}::test_row_identity_is_not_positional",
            f"{T41PG}::test_whole_json_is_split_into_one_field_per_column_per_row",
        ),
        why="stable key 里不再带 row 身份 ⇒ 1260 行折叠成 39 个字段，"
            "「不把整 JSON 当一个字段」变成「把整列当一个字段」，任意两行并改必冲突",
        tags=("split",),
    ),
    # ── ⑦ 顺序门与三条登记欠账 ───────────────────────────────────────
    Mutation(
        id="M33", side="be", path=PD, kind="replace",
        anchor="    if capability is not Capability.bidirectional:",
        new="    if False and capability is not Capability.bidirectional:",
        want=f"{_ORDER}::test_capability_is_not_enabled_before_finalize",
        why="capability 启用门被短路 ⇒ 可以在没有 published representation 时宣称双向可用，"
            "前端显示不可兑现的切换（Requirement 1.5）",
        tags=("ordering",),
    ),
    Mutation(
        # 🔴 Task 75 重指锚点：欠账已结清，`raise PilotSelectionError(<欠账>)` 那行不存在了
        #    （原锚点 0 命中 = ANCHOR-MISS）。判据强度不变 —— want 仍是同一条测试，变异仍
        #    精确构造 Task 75 正文逐字禁止的中间形态②「函数改成 `return None`」。
        id="M34", side="be", path=PD, kind="insert",
        scope="    observation = await observe_published_frozen_definitions(",
        offset=-2,
        anchor="    from app.services.workpaper_sync.resolution import CanonicalResolutionService",
        new="    return None",
        want=f"{_DEBT}::test_resolve_published_definitions_never_returns_none",
        why="找不到载体时返回 None 而不抛 ⇒ 上游把「缺观测器」当成「这个 entry 没有身份」，"
            "一路静默走到注册一个没有 identity binding 的 adapter（本 spec 最贵的一类缺陷）",
        tags=("ordering",),
    ),
    Mutation(
        id="M35", side="be", path=PD, kind="replace",
        anchor="    if xlsx_dynamic:",
        new="    if False and xlsx_dynamic:",
        want=f"{_DEBT}::test_debt_note_is_retracted_when_upstream_fixes_the_gate",
        why="「dynamic 家族对 xlsx 不可达」这条欠账的**撤销条件**被短路 ⇒ 上游把门修好之后"
            "登记不会被提醒撤销，AC 6.9 的场景会继续被当成不可达",
        tags=("debt",),
    ),
    Mutation(
        id="M36", side="be", path=PD, kind="replace",
        anchor='    ("is_confirmation", "AK", "editable", "boolean", "isConfirmation", "是否函证"),',
        new='    ("is_confirmation", "AK", "editable", "text", "isConfirmation", "是否函证"),',
        want=f"{_BOOL}::test_materializer_writes_boolean_as_a_bare_number_literal",
        wants=(
            f"{_BOOL}::test_extract_reports_one_anomaly_per_row_on_the_boolean_column_only",
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        ),
        why="把 boolean 列改判成 text 就「绕开」了已登记的 boolean 缺口 ⇒ 缺口从视野里消失，"
            "而拆分侧会拿真 bool 去过 text 规范化（前端 DetailRow.isConfirmation 是布尔）"
            "—— 等于用自造映射掩盖上游问题",
        tags=("debt", "boolean"),
    ),
    # ── ⑧ 交付登记与生产接线 ─────────────────────────────────────────
    Mutation(
        id="M37", side="be", path=RG, kind="replace",
        anchor='        "adapter_registered": False,',
        scope='        "contract_id": "d2.receivable_detail",',
        # 🔴 Task 75 把 `provider_module` 加进了每条登记行 ⇒ 行内偏移 7 → 8。
        offset=8,
        new='        "adapter_registered": True,',
        want=f"{_ORDER}::test_ledger_records_adapter_not_registered_yet",
        why="登记表声称 adapter 已注册而实际没有仍绿 ⇒ 交付登记与事实脱钩，"
            "「契约孤儿」这条可见欠账被账面抹平",
        scope_check=_ledger_row_field_is("d2.receivable_detail", "adapter_registered", "True"),
        tags=("ledger",),
    ),
    Mutation(
        id="M38", side="be", path=RG, kind="replace",
        anchor='        "contract_id": "d2.receivable_detail",',
        new='        "contract_id": "d2.receivable_detail_typo",',
        want=f"{_GROUND}::test_contract_is_registered_in_the_delivery_ledger",
        wants=(
            f"{T13}::TestTask13ScopeBoundary"
            "::test_contract_directory_matches_the_delivery_ledger",
        ),
        why="登记 id 与磁盘契约文件名不符仍绿 ⇒ 契约目录 ↔ 登记表的双向等值失效，"
            "未登记的生产契约可以溜进目录",
        tags=("ledger",),
    ),
    Mutation(
        id="M39", side="be", path=ROUTER, kind="replace",
        anchor="    await attach_d2_pilot_adapters(registry, session=db)",
        new="    _ = attach_d2_pilot_adapters",
        want=f"{_WIRE}::test_router_calls_the_d2_attach_on_both_paths",
        why="callback 之后的 apply 入口不再接 D2 pilot ⇒ 「HTML 侧能开 OO、OO 回写找不到 "
            "adapter」的半接线（additive 死代码）",
        tags=("wiring",),
    ),
    Mutation(
        # 🔴 Task 75 重指锚点：router 的 `_attach_pilot_adapters` 从「两项相加」重构成
        #    `explicit = (四条 attach 相加)` + `register_from_manifest`，原锚点 0 命中。
        #    判据强度不变：把 D2 那一项换成空元组，`_attach_pilot_adapters` 的 AST 里就
        #    再没有 `attach_d2_pilot_adapters` 调用 ⇒ want 那条 AST 判据必红。
        id="M40", side="be", path=ROUTER, kind="replace",
        anchor="        + await attach_d2_pilot_adapters(svc.registry, session=svc.session)",
        new="        + ()",
        want=f"{_WIRE}::test_router_calls_the_d2_attach_on_both_paths",
        why="HTML→OO 的解析入口不再接 D2 pilot ⇒ 契约与 bundle 都在、registry 里永远没有它，"
            "而「函数存在」的判据照样通过",
        tags=("wiring",),
    ),
    Mutation(
        id="M41", side="be", path=PD, kind="replace",
        anchor="    contract = assert_contract_file_matches_source()",
        scope="async def publish_pilot_definitions(publisher: Any) -> PilotDefinitions:",
        offset=11,
        new="    contract = load_pilot_contract()",
        want=f"{_WIRE}::test_both_production_paths_go_through_the_bidirectional_contract_lock",
        why="发布路径改成只读磁盘契约（不比对源侧）⇒ 一份被手改过的契约可以直接发布，"
            "而双向锁只在守卫里被调用（Task 40 实测过的判据与生产路径脱钩形态）",
        tags=("publish",),
    ),
    Mutation(
        id="M42", side="be", path=PD, kind="replace",
        anchor="    contract = assert_contract_file_matches_source()",
        scope="    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)",
        offset=1,
        new="    contract = load_pilot_contract()",
        want=f"{_WIRE}::test_both_production_paths_go_through_the_bidirectional_contract_lock",
        why="接线路径改成只读磁盘契约 ⇒ 同上（两个生产入口必须都走锁，只锁一个等于没锁）",
        tags=("publish",),
    ),
    # ── ⑧-b 接线路径的「今天不是我的回合」分支（辐射面实测缺陷的修法）─────
    Mutation(
        id="M45", side="be", path=PD, kind="replace",
        anchor="    if not manifest_capability_enabled():",
        new="    if False and not manifest_capability_enabled():",
        want=f"{_ORDER}::test_attach_is_a_no_op_before_enablement_and_never_raises",
        why="未启用时不再提前返回 ⇒ 接线会去读库并抛异常，`_registration` / "
            "`_apply_durable_incoming` 对**所有** entry 都 500（辐射面实测：Task 28 的路由"
            "守卫 8 例打红，因为它的 fixture 用的正是本 pilot 冻结的 entry）",
        tags=("wiring",),
    ),
    Mutation(
        id="M46", side="be", path=PD, kind="replace",
        anchor="        return False",
        scope="def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:",
        offset=11,
        new="        return True",
        want=f"{_ORDER}::test_capability_predicate_agrees_with_the_ordering_gate",
        wants=(f"{_ORDER}::test_attach_is_a_no_op_before_enablement_and_never_raises",),
        why="真值判定与顺序门给出相反结论仍绿 ⇒ 「接线路径放行、顺序门仍红」的不一致可以"
            "悄悄发生：manifest 说单向、接线却往下走到注册",
        tags=("wiring",),
    ),
    # ── ⑨ 真库侧：发布与 run 判据 ─────────────────────────────────────
    Mutation(
        id="M43", side="be", path=PD, kind="replace",
        anchor="        semantic_version=contract.semantic_version,",
        scope="        logical_id=PILOT_ADAPTER_ID,",
        offset=1,
        new="        semantic_version=contract.semantic_version, approved=False,",
        want=f"{T41PG}::test_bundle_is_non_null_and_all_children_are_approved",
        wants=(
            f"{T41PG}::test_no_phase_crashed_during_collection",
            f"{T41PG}::test_four_definitions_and_one_bundle_are_published",
        ),
        why="contract child 以 candidate 状态进 bundle 仍绿 ⇒ 未经人工审核的候选契约可以"
            "被 representation 引用（AC 6.19 明令禁止）",
        tags=("publish",),
    ),
    Mutation(
        id="M44", side="be", path=PD, kind="replace",
        anchor="        authority_model_definition_sha256=authority.sha256,",
        scope="    bundle = await publisher.publish_bundle(",
        offset=3,
        new='        authority_model_definition_sha256="0" * 63 + "1",',
        want=f"{T41PG}::test_bundle_digest_matches_the_canonical_recompute",
        wants=(f"{T41PG}::test_bundle_is_non_null_and_all_children_are_approved",),
        why="bundle canonical payload 里的 authority 绑定被换成别的 digest 仍绿 ⇒ bundle 与它"
            "实际指向的 authority definition 脱钩，历史 operation 的身份解析会取到另一个模型",
        tags=("publish",),
    ),
]

GUARD_FILES = {
    T41: "Task 41 新建（离线：冻结 entry 选型、39 字段逐格源侧比对、三源列锁、发布 DAG、"
         "载荷拆分四类 fail-closed、预算 N-1/N/N+1、分块 sidecar、Property oracle 落点、"
         "三条上游欠账的可打红事实、顺序门、生产接线、清册零增债）",
    T41PG: "Task 41 新建（真库：真实 906,239 字节 / 1260 行载荷、49,140 字段拆分、"
           "Property 27 恰 1 条冲突 + 49,101 字段逐字段不变、四个 definition + non-null "
           "bundle 真发布、24 场景逐条落库、无真实 OO ⇒ 不得 verified）",
    T13: "Task 13（契约目录 ↔ 交付登记表双向等值：本任务往登记表追加第二条）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 41 D2 大 JSON 子表 Excel pilot 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task41_d2_large_json_pilot.py",
                "backend/tests/workpaper_sync/test_task41_d2_large_json_pilot_pg.py",
                # 🔴 Task 13 只挑被本任务影响的那一个类：整文件跑会把并发会话在途的其它红
                #    拖进差集（Task 39/40 收口时的同一决定）。
                "backend/tests/workpaper_sync/test_task13_contract_registry.py"
                "::TestTask13ScopeBoundary",
                "-q",
                "--tb=no",
                "-rfE",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=None,
        )
    )
