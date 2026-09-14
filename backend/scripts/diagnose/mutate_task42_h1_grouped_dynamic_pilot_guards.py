# -*- coding: utf-8 -*-
"""Task 42 守卫变异检验 —— H1 分组/动态结构 Excel pilot。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 42

覆盖面分母 = 本任务新建的两个守卫文件 + 本任务修掉的三条生产缺陷 + 契约 JSON +
registry 交付登记表 + router 两处接线。

用法（仓库根）::

    py -3 backend/scripts/diagnose/mutate_task42_h1_grouped_dynamic_pilot_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task42_h1_grouped_dynamic_pilot_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task42_h1_grouped_dynamic_pilot_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task42-h1-grouped-dynamic-pilot/mutation_report.json

🔴 改**数据文件**（契约 JSON）的变异一律带 `scope_check`：契约里 25 个字段形态高度雷同，
只看「新增失败集合」会把「改到了别的字段」误报成 GREEN（Task 58 的 `_ledger_row_field_is`
是范式）。`scope_check` 比的是**源码字面量**（`True` 而不是 `true`）—— Task 41 的 M37 在
这里踩过一次。

🔴 同形态锚点（`contract = assert_contract_file_matches_source()` 在两处出现）一律用
`scope` + `offset` 相对定位，不用绝对 `line`。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

PH1 = "backend/app/services/workpaper_sync/pilot_h1_grouped_dynamic.py"
EI = "backend/app/services/workpaper_sync/excel_instrumentation.py"
EM = "backend/app/services/workpaper_sync/excel_materialize.py"
RG = "backend/app/services/workpaper_sync/adapters/registry.py"
ROUTER = "backend/app/routers/wp_sync_router.py"
CONTRACT = "backend/data/workpaper_sync_contracts/h1.disposal_check.json"

T42 = "test_task42_h1_grouped_dynamic_pilot.py"
T42PG = "test_task42_h1_grouped_dynamic_pilot_pg.py"

_SEL = f"{T42}::TestFrozenEntrySelection"
_TPL = f"{T42}::TestAuthoritativeTemplate"
_GROUND = f"{T42}::TestContractIsGroundedInTheTemplate"
_P22 = f"{T42}::TestProperty22ColumnIdentityIsDecoupledFromLabel"
_SKEL = f"{T42}::TestSkeletonRowPolicy"
_DAG = f"{T42}::TestPublishDagIsOneWay"
_BASE = f"{T42}::TestBaselineExtractOnTheRealTemplate"
_STRUCT = f"{T42}::TestProperty23And66StructuralOperations"
_SPLIT = f"{T42}::TestStorePayloadSplit"
_P27 = f"{T42}::TestProperty27DeleteUpdateDoesNotOverwriteTheWholeTable"
_PROP = f"{T42}::TestPropertyOracleLanding"
_DEBT = f"{T42}::TestUpstreamDebtsAreVisibleFacts"
_FIX = f"{T42}::TestUpstreamRelsAndNamespaceDefectsAreFixed"
_ORDER = f"{T42}::TestOrderingGate"
_WIRE = f"{T42}::TestProductionWiring"
_NODEBT = f"{T42}::TestPilotIntroducesNoResolverDebt"


# ═══════════════════════════════════════════════════════════════════════════
# 作用域自证回调（数据文件变异必带）
# ═══════════════════════════════════════════════════════════════════════════


def _rows_field(column_key: str, key: str, expected: object):
    """契约 JSON 的行域字段某个键必须**恰好**是 `expected`（改动落在我关心的结构里）。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for table in payload["sheets"][0]["tables"]:
            for field in table["fields"]:
                if field.get("column_key") == column_key:
                    return field.get(key) == expected
        return False

    return check


def _table_field_is(key: str, expected: object):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        return payload["sheets"][0]["tables"][0].get(key) == expected

    return check


def _review_field_is(path: tuple[str, ...], expected: object):
    def check(data: bytes) -> bool:
        cursor: object = json.loads(data.decode("utf-8"))["review"]
        for part in path:
            if not isinstance(cursor, dict):
                return False
            cursor = cursor.get(part)
        return cursor == expected

    return check


def _ledger_row_field_is(contract_id: str, key: str, expected_literal: str):
    """交付登记表里 `contract_id` 那一行的某个键必须恰好是 `expected_literal`。

    🔴 `expected_literal` 是 **Python 源码字面量**（`True` / `False` / `"x"`），不是 JSON
    —— Task 41 的 M37 用 `json.dumps(True)` 得到小写 `true`，作用域自证恒失败判 ANCHOR-MISS。
    """

    def check(data: bytes) -> bool:
        text = data.decode("utf-8")
        anchor = f'"contract_id": "{contract_id}"'
        start = text.find(anchor)
        if start < 0:
            return False
        window = text[start : start + 2600]
        return f'"{key}": {expected_literal}' in window

    return check


MUTATIONS: list[Mutation] = [
    # ── ① 权威模板哨兵（Requirement 9.9）─────────────────────────────
    Mutation(
        id="M01", side="be", path=PH1, kind="replace",
        anchor='    "344f83216b9024e3c3fde7c1ed545eb0026a6cf088a0b0dfd0916e47b64fdc87"',
        new='    "344f83216b9024e3c3fde7c1ed545eb0026a6cf088a0b0dfd0916e47b64fdc88"',
        want=f"{_TPL}::test_template_bytes_are_unchanged",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="模板字节哨兵改一位后仍绿 ⇒ 「backend/wp_templates 运行时只读」无人把守，"
            "后面每个 definition digest 都会对着一份错模板算出来",
        tags=("template",),
    ),
    Mutation(
        id="M02", side="be", path=PH1, kind="replace",
        anchor="    if digest != TEMPLATE_SHA256:",
        new="    if False and digest != TEMPLATE_SHA256:",
        want=f"{_TPL}::test_template_sentinel_rejects_a_mutated_workbook",
        why="哨兵比对被短路 ⇒ 模板被运行时改写不再抛，静默按新字节继续发布"
            "（fail-open 掩盖接线错误的形态）",
        tags=("template",),
    ),
    # ── ② 选型：H1F 是名字提取产物（本任务独有的第三种形态）──────────
    Mutation(
        id="M03", side="be", path=PH1, kind="replace",
        anchor="    assessment = assess_pilot_classes(manifest=payload)[PilotClass.h1_grouped_dynamic]",
        new="    assessment = assess_pilot_classes(manifest=payload)[PilotClass.simple_checklist]",
        want=f"{_SEL}::test_entry_is_frozen_from_the_source_backed_manifest",
        why="pilot 类边界改成 simple_checklist 后 entry 不在候选里却仍绿 ⇒ 「类边界由 harness "
            "判定」退化成本模块自己声明（Property 49 的分母失守）",
        tags=("selection",),
    ),
    Mutation(
        id="M04", side="be", path=PH1, kind="replace",
        anchor='    if not entry.get("independent_entry"):',
        new='    if False and not entry.get("independent_entry"):',
        want=f"{_SEL}::test_selection_fails_closed_on_parent_duplicate",
        why="parent_duplicate 不再被拒 ⇒ 43 条重复入口都能拿到自己的 adapter，"
            "同一 OO room 会被两个 adapter 各写一遍（AC 12.1「每个独立 entry」）",
        tags=("selection",),
    ),
    Mutation(
        id="M05", side="be", path=PH1, kind="replace",
        anchor="    if codes != set(PILOT_WP_CODES):",
        new="    if False and codes != set(PILOT_WP_CODES):",
        want=f"{_SEL}::test_selection_fails_closed_on_wp_code_drift",
        why="matcher 域与 entry 的 wp_code 不再双向锁死 ⇒ 宿主新增/删掉一个 wp_code 后 "
            "matcher 会漏匹配或越界匹配，而 registry 的重叠判据看不出来",
        tags=("selection",),
    ),
    Mutation(
        id="M06", side="be", path=PH1, kind="replace",
        anchor="        if code in set(resolution.index_wp_codes):",
        new="        if False and code in set(resolution.index_wp_codes):",
        want=f"{_SEL}::test_name_extraction_judgement_fails_closed_when_the_code_is_real",
        why="「H1F 不在索引 wp_code 值域里」这一条被短路 ⇒ 哪天 H1F 真成了 wp_code，"
            "本 pilot 仍按「名字提取产物」处置，而那时零回退判据必须换成精确唯一形态",
        tags=("selection", "name-extraction"),
    ),
    Mutation(
        id="M07", side="be", path=PH1, kind="replace",
        anchor="        if any(str(name).startswith(code) for name in resolution.index_filenames):",
        new="        if False and any(str(name).startswith(code) for name in resolution.index_filenames):",
        want=f"{_SEL}::test_name_extraction_judgement_fails_closed_on_a_filename_prefix",
        why="前缀判据被短路 ⇒ 出现 `H1F*.xlsx` 后 `find_template_file_any` 的前缀回退分支"
            "变可达，「零回退 = 根本没有回退」不再成立，契约 source_ref 可能指向别的底稿",
        tags=("selection", "name-extraction"),
    ),
    Mutation(
        id="M08", side="be", path=PH1, kind="replace",
        anchor="        if code not in extracted:",
        new="        if False and code not in extracted:",
        want=f"{_SEL}::test_name_extraction_judgement_fails_closed_on_a_different_host",
        why="「生成器正则能复现 H1F」这一条被短路 ⇒ 宿主改名后推导前提失效却仍放行，"
            "本 pilot 的第 2 条必要条件整体失去依据",
        tags=("selection", "name-extraction"),
    ),
    Mutation(
        id="M09", side="be", path=PH1, kind="replace",
        anchor="    if leaked:",
        new="    if False and leaked:",
        want=f"{_SEL}::test_fallback_judgement_fails_closed_on_a_non_empty_resolution",
        why="零回退判据被短路 ⇒ H1F 一旦解析到某份工作簿，契约的 25 个 source_ref 会指向"
            "另一份底稿的单元格而无人发现（本 spec 已付两次学费的形态）",
        tags=("selection",),
    ),
    Mutation(
        id="M10", side="be", path=PH1, kind="replace",
        anchor="    if len(rows) != 1:",
        new="    if False and len(rows) != 1:",
        want=f"{_SEL}::test_fallback_judgement_fails_closed_on_a_non_unique_family_row",
        why="码族「精确唯一」被短路 ⇒ 索引里出现两份 H1 工作簿时 find_template_file 会挑"
            "一份，契约的 source_ref 失去唯一归属",
        tags=("selection",),
    ),
    Mutation(
        id="M11", side="be", path=PH1, kind="replace",
        anchor=r'    if not re.fullmatch(rf"{re.escape(PILOT_WP_CODE_FAMILY)}(-\d+)?", declared_code):',
        new=r'    if False and not re.fullmatch(rf"{re.escape(PILOT_WP_CODE_FAMILY)}(-\d+)?", declared_code):',
        want=f"{_SEL}::test_render_schema_wp_code_must_stay_inside_the_code_family",
        why="配置真源的码族判据被短路 ⇒ `H1-1.yaml` 改成任意 wp_code 都放行，"
            "「权威模板由配置唯一声明」失守",
        tags=("selection", "config"),
    ),
    Mutation(
        id="M12", side="be", path=PH1, kind="replace",
        anchor='    if "/".join(str(declared).split("\\\\")) != expected:',
        new='    if False and "/".join(str(declared).split("\\\\")) != expected:',
        want=f"{_SEL}::test_selection_fails_closed_when_the_render_schema_points_elsewhere",
        why="配置声明的 template_path 与冻结模板的一致性被短路 ⇒ 配置指到 H6 固定资产清理"
            "也照发契约，等于「据另一份底稿建契约」",
        tags=("selection", "config"),
    ),
    Mutation(
        id="M13", side="be", path=PH1, kind="replace",
        anchor="    entry = entries.get(PILOT_ENTRY_ID)",
        new="    entry = entries.get(PILOT_ENTRY_ID) or {\"independent_entry\": True}",
        want=f"{_SEL}::test_selection_fails_closed_when_the_entry_disappears",
        why="entry 消失时用空壳兜底 ⇒ 宿主挂载点已删掉，契约却继续按旧单元格发布"
            "（fail-open 掩盖接线错误）",
        tags=("selection",),
    ),
]


MUTATIONS += [
    # ── ③ 三级分组表头（AC 6.3）────────────────────────────────────
    Mutation(
        id="M14", side="be", path=PH1, kind="replace",
        anchor='    (f"I{GROUP_HEADER_ROW}", ("I", "J", "K", "L", "M", "N", "O"), "减少情况"),',
        new='    (f"I{GROUP_HEADER_ROW}", ("I", "J", "K", "L", "M", "N"), "减少情况"),',
        want=f"{_GROUND}::test_group_spans_match_the_real_merged_ranges",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_GROUND}::test_every_group_header_matches_the_real_cell_text",
        ),
        why="组的列跨度少一列（O 掉出 `减少情况`）后仍绿 ⇒ 组声明与源 xlsx 行 10 的真实"
            "横向 merge 脱钩，审计师看到的分组与契约表达的分组不是一回事",
        tags=("grouped-header",),
    ),
    Mutation(
        id="M15", side="be", path=PH1, kind="replace",
        anchor='    (f"I{HEADER_MID_ROW}", ("I", "J", "K", "L"), "转入清理的固定资产"),',
        new='    (f"I{HEADER_MID_ROW}", ("I", "J", "K"), "转入清理的固定资产"),',
        want=f"{_GROUND}::test_mid_spans_match_the_real_merged_ranges",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_GROUND}::test_every_mid_header_matches_the_real_cell_text",
        ),
        why="中层列跨度少一列后仍绿 ⇒ 三级表头的第二级与源 xlsx 行 11 的 merge 脱钩，"
            "`L 净值` 会丢掉它的中层归属（三级退化成二级而无人发现）",
        tags=("grouped-header",),
    ),
    Mutation(
        id="M16", side="be", path=PH1, kind="replace",
        anchor='HEADER_ROW_COUNT: Final[int] = HEADER_LEAF_ROW - GROUP_HEADER_ROW + 1',
        new="HEADER_ROW_COUNT: Final[int] = 2",
        want=f"{_GROUND}::test_header_rows_is_three_and_is_the_schema_upper_bound",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="`header_rows` 从三行推导改成写死 2 ⇒ 契约宣称两级表头而源表是三级，"
            "OO 侧按两级解析会把行 12 的叶子当数据行",
        tags=("grouped-header",),
    ),
    Mutation(
        id="M17", side="be", path=PH1, kind="replace",
        anchor="        leaf = leaf_header_cell_of(column)",
        new='        leaf = ""',
        want=f"{_GROUND}::test_every_mid_header_matches_the_real_cell_text",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="「中层锚点与叶子锚点同格时不重复声明」被短路 ⇒ `O11:O12` 那种纵向合并会同时"
            "被算成 mid 与 leaf，「三级」名义上成立而实际只有两级（自欺式层级）",
        tags=("grouped-header",),
    ),
    Mutation(
        id="M18", side="be", path=PH1, kind="replace",
        anchor='        "original_cost", "I", "editable", "amount", "originalCost",',
        new='        "original_cost", "I", "editable", "amount", "orginalCost",',
        want=f"{_P22}::test_frontend_row_shape_covers_every_declared_json_path",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="json 路径拼错一个字母后仍绿 ⇒ 三源锁死的第二源（前端 `DisposalRow`）失效，"
            "该字段在真实载荷上永远取 None 而 extract 只当它 MISSING（静默丢数据）",
        tags=("three-source-lock",),
    ),
    Mutation(
        id="M19", side="be", path=PH1, kind="replace",
        anchor='        f"I{HEADER_LEAF_ROW}", "原值",',
        new='        f"I{HEADER_LEAF_ROW}", "原始价值",',
        want=f"{_GROUND}::test_every_leaf_header_matches_the_real_cell_text",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="叶子表头文本自拟后仍绿 ⇒ `header_source_ref` 指向的单元格与声明的 label 脱钩，"
            "契约变成「据常识造表」（Requirement 6.1 明令禁止）",
        tags=("grounding",),
    ),
    Mutation(
        id="M20", side="be", path=PH1, kind="replace",
        anchor='    "L": "=I{r}-J{r}-K{r}",',
        new='    "L": "=I{r}-J{r}",',
        want=f"{_GROUND}::test_two_formula_columns_are_really_formulas_in_the_template",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="公式模板少一项后仍绿 ⇒ 逐行公式比对退化成不比对，模板改了公式（或契约抄错）"
            "都察觉不到，而受保护格的还原基线正来自它",
        tags=("formula",),
    ),
    Mutation(
        id="M21", side="be", path=PH1, kind="replace",
        anchor='FOOTER_MARKER: Final[str] = "合计"',
        new='FOOTER_MARKER: Final[str] = "总计"',
        want=f"{_GROUND}::test_footer_marker_is_the_real_cell_text",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_STRUCT}::test_footer_formula_range_still_covers_the_managed_rows",
        ),
        why="footer marker 与源 xlsx 的 `A28` 文本脱钩后仍绿 ⇒ 运行时定位不到 footer，"
            "materialize 的「footer 是否下移」与「SUM 区间是否覆盖受管行」两道门全部失效",
        tags=("footer",),
    ),
    Mutation(
        id="M22", side="be", path=PH1, kind="replace",
        anchor='    (f"I{FOOTER_ROW + 1}", "=\'明细表H1-2\'!O33"),',
        new='    (f"I{FOOTER_ROW + 1}", "=0"),',
        want=f"{_GROUND}::test_unmanaged_below_footer_cells_are_the_real_contents",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="未管理区域里那条**跨 sheet** 公式被换成常量后仍绿 ⇒ 「插删行不得动未管理区域」"
            "的关键形态（跨 sheet 引用）从判据里消失",
        tags=("unmanaged",),
    ),
    # ── ④ Property 22：列 identity 与 label 解耦 ───────────────────
    Mutation(
        id="M23", side="be", path=PH1, kind="replace",
        anchor='    return f"{ROWS_TABLE_KEY}/{row_identity}/{column_key}"',
        new='    return f"{ROWS_TABLE_KEY}/{row_identity}/{column_key}/x"',
        want=f"{_P22}::test_stable_key_builder_is_the_only_assembly_point",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_P22}::test_renaming_a_header_label_does_not_change_any_stable_key",
        ),
        why="stable key 的唯一拼装处被改形后仍绿 ⇒ 「键里只有 column_key、没有 label」这条"
            "结构性保证退化成偶然（Property 22 的核心）",
        tags=("property22",),
    ),
    Mutation(
        id="M24", side="be", path=PH1, kind="replace",
        anchor='        "contract_ref", "R", "editable", "text", "contractRef",',
        new='        "application_ref", "R", "editable", "text", "contractRef",',
        want=f"{_P22}::test_stable_keys_stay_distinct_despite_duplicate_labels",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_GROUND}::test_field_counts_are_the_real_template_facts",
        ),
        why="让两个 `日期/编号` 列共用同一个 column_key（撞键）⇒ 若仍绿，Property 22 的"
            "「重复 label 不发生键冲突」就没有判据；本表 7 列共用 3 个 label，正是 H7 那条"
            "「key 不能用 label 会撞键」学费的复现场景",
        tags=("property22",),
    ),
    Mutation(
        id="M25", side="be", path=PH1, kind="replace",
        anchor='        "header_rows": HEADER_ROW_COUNT,',
        new='        "header_rows": HEADER_ROW_COUNT, "dynamic_columns": {"identity": "{slot}_{seq}", "source_ref": _src(f"A{GROUP_HEADER_ROW}")},',
        want=f"{_P22}::test_no_dynamic_columns_are_declared_for_this_entry",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="凭空给本表声明 `dynamic_columns` ⇒ 本表列是固定的 A..Z，`{slot}_{seq}` 是 G7 那种"
            "按公司横向展开的形态；无来源自造结构若仍绿，Requirement 6.1 在契约结构层面失守。"
            "🔴 用单行 replace 而不是 insert 整段函数：`insert` 把 new 放在 anchor **之后**，"
            "在 new 里重复函数头会留下一个空体的函数 ⇒ IndentationError ⇒ collection error ⇒ "
            "被误判成 WRONG-TEST（首轮实测）",
        tags=("property22",),
    ),
    Mutation(
        id="M26", side="be", path=PH1, kind="replace",
        anchor='CATEGORY_DV_VALUES: Final[tuple[str, ...]] = (',
        new='CATEGORY_DV_VALUES: Final[tuple[str, ...]] = ("房屋",) + (',
        want=f"{_GROUND}::test_enum_value_domains_come_from_the_real_data_validations",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_P22}::test_category_domain_matches_the_frontend_truth_source",
        ),
        why="类别枚举值域多塞一项后仍绿 ⇒ 三源锁死的第三源（模板 DV ↔ 前端 "
            "`H1_2_CATEGORY_OPTIONS`）失效，OO 侧可以选一个前端不认的值",
        tags=("three-source-lock", "style-source"),
    ),
    # ── ⑤ 骨架行数取 max(seed,1)（平台铁律）────────────────────────
    Mutation(
        id="M27", side="be", path=PH1, kind="replace",
        anchor="    return max(int(seed), 1)",
        new="    return max(int(seed), TEMPLATE_SKELETON_ROWS)",
        want=f"{_SKEL}::test_skeleton_row_count_is_max_seed_one",
        wants=(
            f"{_SKEL}::test_zero_seed_does_not_yield_the_template_skeleton",
            f"{T42PG}::test_skeleton_policy_is_max_seed_one",
        ),
        why="`max(seed,1)` 变成 `max(seed,15)` ⇒ seed=0 时预置 15 行空占位，会被下游推成"
            "占位披露行（平台铁律「动态区骨架行数禁写死」正是为这条形态定的）",
        tags=("skeleton",),
    ),
    Mutation(
        id="M28", side="be", path=PH1, kind="replace",
        anchor="LAST_DATA_ROW: Final[int] = FIRST_DATA_ROW + skeleton_row_count(TEMPLATE_SKELETON_ROWS) - 1",
        new="LAST_DATA_ROW: Final[int] = FIRST_DATA_ROW + 14",
        want=f"{_SKEL}::test_skeleton_row_count_is_the_only_row_arithmetic",
        why="行区间上界改成写死的常量加法 ⇒ 「骨架行数只由 skeleton_row_count 决定」退化，"
            "以后改策略会漏掉这一处（本 spec 反复付学费的「第二处真源」形态）",
        tags=("skeleton",),
    ),
    Mutation(
        id="M29", side="be", path=PH1, kind="replace",
        anchor='                "skeleton_row_policy": "max(seed,1)",',
        new='                "skeleton_row_policy": "template_fixed",',
        want=f"{_SKEL}::test_contract_declares_the_policy_not_a_hardcoded_count",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="契约里登记的骨架策略被改掉后仍绿 ⇒ 「策略而不是行数」这条声明没有判据，"
            "下游读契约的人会以为骨架是模板固定的",
        tags=("skeleton",),
    ),
    Mutation(
        id="M30", side="be", path=CONTRACT, kind="replace",
        anchor='          "header_rows": 3,',
        new='          "header_rows": 2,',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        wants=(f"{_GROUND}::test_header_rows_is_three_and_is_the_schema_upper_bound",),
        why="只改磁盘契约不改代码 ⇒ 双向锁死必须打红；单向锁（只验「磁盘能被 parse 接受」）"
            "会让这种漂移悄悄通过",
        scope_check=_table_field_is("header_rows", 2),
        tags=("contract-lock",),
    ),
    Mutation(
        id="M31", side="be", path=CONTRACT, kind="replace",
        anchor='              "column_key": "net_value",',
        new='              "column_key": "netvalue",',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        why="只改磁盘契约里一个 column_key ⇒ 双向锁死必须打红（25 个字段形态雷同，"
            "作用域自证保证改到的确实是 net_value 这一条）",
        scope_check=_rows_field("netvalue", "mode", "formula"),
        tags=("contract-lock",),
    ),
    Mutation(
        id="M32", side="be", path=CONTRACT, kind="replace",
        anchor='          "delete_policy": "tombstone",',
        new='          "delete_policy": "reject",',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        why="删除策略被改后仍绿 ⇒ 动态行的删除语义（tombstone vs reject）可以在磁盘上被"
            "单方面改写，而 merge 的 delete/update 判定正依赖它",
        scope_check=_table_field_is("delete_policy", "reject"),
        tags=("contract-lock",),
    ),
    Mutation(
        id="M33", side="be", path=CONTRACT, kind="replace",
        anchor='      "observed_empty_in_reference_database": true,',
        new='      "observed_empty_in_reference_database": false,',
        want=f"{T42PG}::test_contract_declares_the_observed_emptiness",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="「参考库里这条 item 为空」这条**观测登记**被改掉后仍绿 ⇒ 合成行 oracle 失去"
            "书面理由，将来真实数据出现时没人知道该改回真实载荷",
        scope_check=_review_field_is(
            ("html_store", "observed_empty_in_reference_database"), False
        ),
        tags=("contract-lock", "observation"),
    ),
]


MUTATIONS += [
    # ── ⑥ 载荷拆分与分型可达 ───────────────────────────────────────
    Mutation(
        id="M34", side="be", path=PH1, kind="replace",
        anchor="    if not isinstance(raw, str) or not raw.strip():",
        new="    if False and (not isinstance(raw, str) or not raw.strip()):",
        want=f"{_SPLIT}::test_missing_row_identity_fails_closed",
        wants=(f"{_SPLIT}::test_failure_kinds_are_reachable_and_mutually_distinct",),
        why="缺 `rowId` 不再 fail closed ⇒ 行身份会静默退回 None，下游按位置对齐"
            "（Requirement 6.5 / Property 23 明令禁止的形态）",
        tags=("payload",),
    ),
    Mutation(
        id="M35", side="be", path=PH1, kind="replace",
        anchor="        if identity in seen:",
        new="        if False and identity in seen:",
        want=f"{_SPLIT}::test_duplicate_row_identity_fails_closed",
        wants=(f"{_SPLIT}::test_failure_kinds_are_reachable_and_mutually_distinct",),
        why="重复行身份不再 fail closed ⇒ 复制行产生的重复 UUID 被静默合并成一行"
            "（Requirement 6.15）",
        tags=("payload",),
    ),
    Mutation(
        id="M36", side="be", path=PH1, kind="replace",
        anchor="    if not isinstance(rows, list):",
        new="    if False and not isinstance(rows, list):",
        want=f"{_SPLIT}::test_non_array_payload_fails_closed",
        wants=(f"{_SPLIT}::test_failure_kinds_are_reachable_and_mutually_distinct",),
        why="载荷不是数组时不再 fail closed ⇒ 整张表被存成别的形态时静默当成零行"
            "（表面上「同步成功但什么都没变」）",
        tags=("payload",),
    ),
    Mutation(
        id="M37", side="be", path=PH1, kind="replace",
        anchor="    error_code = \"sync_pilot_store_payload_invalid\"",
        new="    error_code = \"sync_pilot_selection_invalid\"",
        want=f"{_SPLIT}::test_failure_kinds_are_reachable_and_mutually_distinct",
        why="「载荷坏了」与「选型漂移」共用同一个 error_code ⇒ 较早的分支永久不可分辨"
            "（本 spec 已实测 3 次的假绿形态：共享错误码让分支永久 GREEN）",
        tags=("payload", "error-code"),
    ),
    Mutation(
        id="M38", side="be", path=PH1, kind="replace",
        anchor="        spec = contract.field_by_stable_key(stable_key_for(column_key))",
        new="        spec = MANAGED_FIELD_SPECS[0]  # type: ignore[assignment]",
        want=f"{_SPLIT}::test_split_uses_the_contract_as_the_spec_source",
        why="spec 不再从契约取 ⇒ 写错一个 column_key 不会立刻炸，而是静默产出一个契约里"
            "没有的字段（additive 死代码 + 类型信息全错）",
        tags=("payload",),
    ),
    Mutation(
        id="M39", side="be", path=PH1, kind="replace",
        anchor="        budget.add_row(ROWS_TABLE_KEY)",
        new="        pass",
        want=f"{_SPLIT}::test_row_and_field_budgets_are_wired_into_the_split",
        why="行预算不再喂给 `StreamingProjectionBudget` ⇒ Property 60 的「大文件 fail visible」"
            "在拆分路径上整段失效，越界时静默继续吃内存",
        tags=("budget",),
    ),
    # ── ⑦ Property 23 / 66：结构操作 ───────────────────────────────
    Mutation(
        id="M40", side="be", path=PH1, kind="replace",
        anchor='UUID_COL: Final[str] = "AB"',
        new='UUID_COL: Final[str] = "AA"',
        want=f"{_GROUND}::test_uuid_column_sits_right_of_the_managed_business_columns",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_BASE}::test_instrumentation_produces_all_four_carriers",
        ),
        why="UUID 列挪到 `AA` ⇒ 那一格有可见注解（`检查的关键证据和要素…`），隐藏该列会藏掉"
            "它（Requirement 6.13「不得改变业务公式/标签」）",
        tags=("identity",),
    ),
    Mutation(
        id="M41", side="be", path=PH1, kind="replace",
        anchor='MANAGED_LAST_COL: Final[str] = "Z"',
        new='MANAGED_LAST_COL: Final[str] = "W"',
        want=f"{_GROUND}::test_column_letters_are_a_to_z_minus_the_placeholder",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_BASE}::test_instrumentation_produces_all_four_carriers",
        ),
        why="受管最后一列缩到 W ⇒ Table 圈不住 `Y 索引号` / `Z 是否异常` 两列，"
            "它们的字段解析会落到 Table 之外（受管矩形与契约声明脱钩）",
        tags=("identity",),
    ),
    Mutation(
        id="M42", side="be", path=PH1, kind="replace",
        anchor='PLACEHOLDER_COLUMN: Final[str] = "X"',
        new='PLACEHOLDER_COLUMN: Final[str] = "Y"',
        want=f"{_GROUND}::test_column_letters_are_a_to_z_minus_the_placeholder",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="占位列指到 `Y 索引号` ⇒ 一个有业务语义的列被当成占位而不声明，同时真占位列 `X`"
            "（表头 `……`）反被当成业务列 —— 正是 Requirement 6.1「禁止无来源自造字段」两侧"
            "同时失守",
        tags=("grounding",),
    ),
    # ── ⑧ 本任务修掉的三条生产缺陷：退回旧行为必须打红 ─────────────
    Mutation(
        id="M43", side="be", path=EI, kind="replace",
        anchor='        if re.search(r\'\\bId="\' + re.escape(rid) + r\'"\', candidate.group(0)):',
        new='        if re.search(r\'\\bId="\' + re.escape(rid) + r\'"[^>]*Target=\', candidate.group(0)):',
        want=f"{_FIX}::test_sheet_part_resolution_is_attribute_order_independent",
        wants=(
            f"{_FIX}::test_old_id_before_target_regex_would_have_failed",
            f"{_BASE}::test_instrumentation_produces_all_four_carriers",
        ),
        why="rels 解析退回「Id 必须排在 Target 之前」⇒ 369 个权威模板里 10 个（含 Task 40 的"
            " B60 与 Task 43 的 G7）整份不可注入。这条缺陷此前潜伏，正是本任务在真实数据上"
            "撞出来的",
        tags=("defect-rels",),
    ),
    Mutation(
        id="M44", side="be", path=EI, kind="replace",
        anchor='    _rel_ns_decl = "" if \'xmlns:r="\' in _root_tag else f\' xmlns:r="{_REL_NS}"\'',
        new='    _rel_ns_decl = ""',
        want=f"{_FIX}::test_instrumented_workbook_and_sheet_xml_are_well_formed",
        wants=(f"{_BASE}::test_instrumentation_produces_all_four_carriers",),
        why="注入的 `<sheet>` 退回「不带 xmlns:r」⇒ 根元素不声明该前缀的工作簿产出未绑定"
            "前缀的 workbook.xml，`ET.fromstring` 抛 unbound prefix，identity_inventory 全线不可用",
        tags=("defect-namespace",),
    ),
    Mutation(
        id="M45", side="be", path=EI, kind="replace",
        anchor='    rel_ns_decl = "" if \'xmlns:r="\' in root_tag else f\' xmlns:r="{_REL_NS}"\'',
        new='    rel_ns_decl = ""',
        want=f"{_FIX}::test_instrumented_workbook_and_sheet_xml_are_well_formed",
        wants=(f"{_BASE}::test_instrumentation_produces_all_four_carriers",),
        why="注入的 `<tableParts>` 退回「不带 xmlns:r」⇒ 受管 sheet XML 未绑定前缀，"
            "`_parse_tables` 抛 unbound prefix（与 M44 是同源缺陷的另一半，故各自一条）",
        tags=("defect-namespace",),
    ),
    Mutation(
        id="M46", side="be", path=EI, kind="replace",
        anchor='    rel_ns_decl = "" if \'xmlns:r="\' in root_tag else f\' xmlns:r="{_REL_NS}"\'',
        new='    rel_ns_decl = f\' xmlns:r="{_REL_NS}"\'',
        want=f"{_FIX}::test_namespace_is_not_added_when_the_root_already_declares_it",
        why="改成**无条件**加 xmlns:r ⇒ 另外 358 个工作簿的注入字节都会变，从而改掉 Task "
            "40/41 已冻结的 structure hash；「只在缺失时补」这条约束若无判据，下一个人很容易"
            "顺手改成无条件",
        tags=("defect-namespace",),
    ),
    Mutation(
        id="M47", side="be", path=EM, kind="replace",
        anchor="    out = _decode_numeric_char_refs(text)",
        new="    out = text",
        want=f"{_FIX}::test_numeric_character_references_are_decoded",
        wants=(
            f"{_FIX}::test_footer_marker_is_found_through_the_decoder",
            f"{_STRUCT}::test_footer_formula_range_still_covers_the_managed_rows",
        ),
        why="数字字符引用解码被摘掉 ⇒ 10 个权威模板（把中文写成 `&#21512;&#35745;`）的 footer "
            "marker 定位不到，`assert_footer_anchor_stable` 抛 FooterAnchorDriftError，"
            "materialize 与「SUM 区间覆盖受管行」两道门全线不可用",
        tags=("defect-numref",),
    ),
    Mutation(
        id="M48", side="be", path=EM, kind="replace",
        anchor='        return chr(code) if 0 < code <= 0x10FFFF else match.group(0)',
        new='        return chr(code) if 0 <= code <= 0x110000 else match.group(0)',
        want=f"{_FIX}::test_numeric_character_references_are_decoded",
        why="非法码位不再原样保留 ⇒ `&#0;` / `&#1114112;` 会抛 ValueError 或产出 NUL 字符；"
            "「静默丢字符比留下引用更难查」这条决定失去判据",
        tags=("defect-numref",),
    ),
    # ── ⑨ 顺序门与接线 ────────────────────────────────────────────
    Mutation(
        id="M49", side="be", path=PH1, kind="replace",
        anchor="    if capability is not Capability.bidirectional:",
        new="    if False and capability is not Capability.bidirectional:",
        want=f"{_ORDER}::test_capability_is_not_enabled_before_finalize",
        wants=(f"{_ORDER}::test_capability_predicate_agrees_with_the_ordering_gate",),
        why="顺序门被短路 ⇒ finalize 还没做就宣称 capability 已启用，而 registry 里一个"
            " adapter 都没有（伪双向）",
        tags=("ordering",),
    ),
    Mutation(
        id="M50", side="be", path=PH1, kind="replace",
        anchor="    if str(entry.get(\"adapter_id\") or \"\") != PILOT_ADAPTER_ID:",
        new="    if False and str(entry.get(\"adapter_id\") or \"\") != PILOT_ADAPTER_ID:",
        want=f"{_ORDER}::test_capability_predicate_agrees_with_the_ordering_gate",
        why="顺序门只看 capability 不看 adapter_id ⇒ manifest 可以把本 entry 指到别的 pilot 的"
            " adapter_id 而照样放行（跨 entry 复用 identity 的入口）",
        tags=("ordering",),
    ),
    Mutation(
        id="M51", side="be", path=PH1, kind="replace",
        anchor="    except PilotSelectionError:",
        new="    except Exception:  # noqa: BLE001",
        want=f"{_ORDER}::test_capability_predicate_agrees_with_the_ordering_gate",
        why="窄类型换成宽 `except Exception` ⇒ manifest 读不出来这类**真故障**会被吞成"
            "「未启用」（本 spec 最贵的 fail-open 形态）",
        tags=("ordering", "fail-open"),
    ),
    Mutation(
        # 🔴 Task 75 重指锚点：欠账已结清，`raise PilotSelectionError(<欠账>)` 那行不存在了
        #    （原锚点 0 命中 = ANCHOR-MISS）。判据强度不变 —— want 仍是同一条测试，变异仍
        #    精确构造 Task 75 正文逐字禁止的中间形态②「函数改成 `return None`」。
        id="M52", side="be", path=PH1, kind="insert",
        scope="    observation = await observe_published_frozen_definitions(",
        offset=-2,
        anchor="    from app.services.workpaper_sync.resolution import CanonicalResolutionService",
        new="    return None",
        want=f"{_DEBT}::test_resolve_published_definitions_never_returns_none",
        why="找不到 identity 载体时返回 None ⇒ 上游把「缺观测器」表现成「这个 entry 没有身份」，"
            "一路静默走到「注册一个没有 identity binding 的 adapter」（fail-open 掩盖接线错误）",
        tags=("debt", "fail-open"),
    ),
    Mutation(
        id="M53", side="be", path=PH1, kind="replace",
        anchor="    contract = assert_contract_file_matches_source()",
        scope="async def publish_pilot_definitions(publisher: Any) -> PilotDefinitions:",
        offset=11,
        new="    contract = load_pilot_contract()",
        want=f"{_WIRE}::test_both_production_paths_go_through_the_bidirectional_contract_lock",
        why="发布路径绕过双向锁改成直接 load ⇒ 磁盘契约与现算 payload 漂移时照样发布，"
            "而契约里的 digest 一旦与真实 definition payload 脱钩，"
            "`assert_contract_identity_frozen` 只是在比两个都错的值。"
            "🔴 用 scope+offset 相对定位：这行在两个生产入口各出现一次",
        tags=("wiring", "contract-lock"),
    ),
    Mutation(
        id="M54", side="be", path=PH1, kind="replace",
        anchor="    if not manifest_capability_enabled():",
        new="    if False and not manifest_capability_enabled():",
        want=f"{_ORDER}::test_attach_is_a_no_op_before_enablement_and_never_raises",
        why="接线路径不再检查 capability ⇒ 未启用时也会去读库（session=None 直接炸），"
            "把「这个 entry 今天不是双向 pilot」变成 500",
        tags=("wiring",),
    ),
    Mutation(
        id="M55", side="be", path=ROUTER, kind="replace",
        anchor="        + await attach_h1_pilot_adapters(svc.registry, session=svc.session)",
        new="        + ()",
        want=f"{_WIRE}::test_router_calls_the_h1_attach_on_both_paths",
        why="第一个生产接线点（`_registration` 前）被摘掉 ⇒ HTML 侧开 OO 时解析不到本 pilot 的"
            " adapter，形成半接线（另一半仍在 callback 路径上）",
        tags=("wiring",),
    ),
    Mutation(
        id="M56", side="be", path=ROUTER, kind="replace",
        anchor="    await attach_h1_pilot_adapters(registry, session=db)",
        new="    pass",
        want=f"{_WIRE}::test_router_calls_the_h1_attach_on_both_paths",
        why="第二个生产接线点（callback 后 apply）被摘掉 ⇒「OO 回写却找不到 adapter」，"
            "durable incoming 静默丢弃",
        tags=("wiring",),
    ),
    Mutation(
        id="M57", side="be", path=RG, kind="replace",
        anchor='        "contract_id": "h1.disposal_check",',
        new='        "contract_id": "h1.disposal_checks",',
        want=f"{_GROUND}::test_contract_is_registered_in_the_delivery_ledger",
        wants=(f"{_ORDER}::test_ledger_records_adapter_not_registered_yet",),
        why="交付登记表里的 contract_id 拼错 ⇒ 契约目录边界判据（登记 ↔ "
            "`available_contract_ids()` 双向等值）失效，等于「有人绕过 pilot 门放了个契约」"
            "不再被发现",
        scope_check=_ledger_row_field_is("h1.disposal_checks", "delivered_by_task", '"42"'),
        tags=("ledger",),
    ),
    Mutation(
        id="M58", side="be", path=RG, kind="replace",
        anchor='        "adapter_registered": False,',
        scope='        "contract_id": "h1.disposal_check",',
        # 🔴 Task 75 把 `provider_module` 加进了每条登记行 ⇒ 行内偏移 7 → 8。
        offset=8,
        new='        "adapter_registered": True,',
        want=f"{_ORDER}::test_ledger_records_adapter_not_registered_yet",
        why="登记表宣称 adapter 已注册 ⇒「顺序未过」这一事实被抹掉，收口报告会把契约孤儿"
            "算成已接线。🔴 用 scope+offset：这行在三个 pilot 的登记里各出现一次",
        scope_check=_ledger_row_field_is("h1.disposal_check", "adapter_registered", "True"),
        tags=("ledger",),
    ),
    # ── ⑩ 上游缺口登记 ────────────────────────────────────────────
    Mutation(
        id="M59", side="be", path=PH1, kind="replace",
        anchor="    if xlsx_dynamic:",
        new="    if False and xlsx_dynamic:",
        want=f"{_DEBT}::test_dynamic_debt_is_retracted_when_upstream_fixes_the_gate",
        why="「上游修好就抛错提醒撤销登记」的反向自检被短路 ⇒ 缺口修好后欠账登记永远留着，"
            "Property 22/23/27 也永远落在 merge 家族而不回到自己的场景",
        tags=("debt",),
    ),
    Mutation(
        id="M60", side="be", path=PH1, kind="replace",
        anchor='    "Task 42 欠账：per-entry contract 的 `header_rows` 值域被 "',
        new='    "备注：per-entry contract 的 `header_rows` 值域被 "',
        want=f"{_DEBT}::test_four_debts_are_registered_and_mutually_distinct",
        wants=(f"{_DEBT}::test_four_level_header_debt_is_a_measured_schema_limit",),
        why="四级表头欠账的文案不再以 `Task 42 欠账` 起始 ⇒ 「四条欠账各自独立可辨」的"
            "集合基数与前缀判据必须打红，否则合并/删除欠账时无人发现。"
            "🔴 首轮写的是 `Final[str] = \"\" + (`，而空串拼接是**恒等**⇒ 什么都没改，"
            "判 GREEN 是对的（无效变异，脚本缺陷不是守卫缺陷）",
        tags=("debt",),
    ),
    Mutation(
        id="M61", side="be", path=PH1, kind="replace",
        anchor='DISPOSAL_METHOD_DV_VALUES: Final[tuple[str, ...]] = ("处置", "其他减少")',
        new='DISPOSAL_METHOD_DV_VALUES: Final[tuple[str, ...]] = ("出售", "报废")',
        want=f"{_DEBT}::test_disposal_method_enum_domain_split_is_a_measured_fact",
        wants=(
            f"{_GROUND}::test_enum_value_domains_come_from_the_real_data_validations",
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        ),
        why="把模板 DV 值域**改成前端口径**（自造映射）⇒ 正是 Requirement 6.1 禁止的「无来源"
            "自造字段」：契约的 enum_source_ref 指向模板 DV 单元格，值域却成了业务口径，"
            "OO 写回的值会静默改变审计含义",
        tags=("debt", "enum-domain"),
    ),
    Mutation(
        id="M62", side="be", path=PH1, kind="insert",
        anchor='        if column_key == "disposal_method":',
        new='            spec["value_domain_mapping"] = {"出售": "处置", "报废": "其他减少"}',
        want=f"{_DEBT}::test_contract_never_invents_a_domain_mapping",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="往契约里塞一个 `出售→处置` 的自造映射 ⇒ Requirement 6.1 的反向判据若失效，"
            "「不为绕开缺口自造映射」这条决定就只是注释。🔴 `new` 里**不**重复 `if` 头 —— "
            "`insert` 会把它放在 anchor 之后，重复一次就留下空体 if ⇒ IndentationError"
            "（首轮实测判 WRONG-TEST）",
        tags=("debt", "enum-domain"),
    ),
    # ── ⑪ 未管理区域与非空覆盖 ────────────────────────────────────
    Mutation(
        id="M63", side="be", path=PH1, kind="replace",
        anchor='    ("AA11", "检查的关键证据和要素根据被审计单位具体情况修改"),',
        new='    ("AA11", "检查的关键证据"),',
        want=f"{_GROUND}::test_unmanaged_below_footer_cells_are_the_real_contents",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="列外注解的登记文本被截短后仍绿 ⇒ 「未管理区域的真实内容」这份清单与源 xlsx 脱钩，"
            "而它正是「UUID 列为何取 AB 而非 AA」的依据",
        tags=("unmanaged",),
    ),
    Mutation(
        id="M64", side="be", path=PH1, kind="replace",
        anchor='                "conditional_formatting_count": 0,',
        new='                "conditional_formatting_count": 1,',
        want=f"{_BASE}::test_managed_sheet_structure_aspect_covers_the_style_sources",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="样式源登记里条件格式数目被改后仍绿 ⇒ 「样式源」这一段变成自由文本，"
            "而 `managed_sheet_structure` aspect 的覆盖面正靠它对账",
        tags=("style-source",),
    ),
]

GUARD_FILES = {
    T42: "Task 42 新建（离线：选型/分组表头/骨架策略/identity/Property 落点/缺陷反向自检）",
    T42PG: "Task 42 新建（真库：definitions+bundle 真发布/全场景 run/真实库观测冻结）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            backend_args=[
                "backend/tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py",
                "backend/tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot_pg.py",
                "-q",
                "--tb=no",
                "-rfE",
            ],
            baseline_backend_passed=176,
        )
    )
