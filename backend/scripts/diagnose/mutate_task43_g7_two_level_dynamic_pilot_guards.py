# -*- coding: utf-8 -*-
"""Task 43 守卫变异检验 —— G7 两级动态表 Excel pilot。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 43

覆盖面分母 = 本任务新建的两个守卫文件 + 本任务修掉的一条生产缺陷 + 契约 JSON +
registry 交付登记表 + router 两处接线 + 四边真源的四个来源。

用法（仓库根）::

    py -3 backend/scripts/diagnose/mutate_task43_g7_two_level_dynamic_pilot_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task43_g7_two_level_dynamic_pilot_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task43_g7_two_level_dynamic_pilot_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task43-g7-two-level-dynamic-pilot/mutation_report.json

🔴 改**数据文件**（契约 JSON）的变异一律带 `scope_check`：契约里 107 个字段形态高度雷同，
只看「新增失败集合」会把「改到了别的字段」误报成 GREEN。`scope_check` 比的是**源码字面量**
（`True` 而不是 `true`）—— Task 41 的 M37 在这里踩过一次。

🔴 `insert` 的 `new` 里**不**重复 `if` / `def` 头（会留下空体 ⇒ IndentationError ⇒
collection error ⇒ 误判 WRONG-TEST；Task 42 的 M25/M62 都是这个）。

🔴 同形态锚点一律用 `scope` + `offset` 相对定位，不用绝对 `line`。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

PG7 = "backend/app/services/workpaper_sync/pilot_g7_two_level_dynamic.py"
EI = "backend/app/services/workpaper_sync/excel_instrumentation.py"
EG = "backend/app/services/workpaper_sync/excel_entry_gate.py"
RG = "backend/app/services/workpaper_sync/adapters/registry.py"
ROUTER = "backend/app/routers/wp_sync_router.py"
CONTRACT = "backend/data/workpaper_sync_contracts/g7.soe_subsidiary_disclosure.json"
FACTS = "backend/data/g7_column_source_facts.json"
SLOTCOLS = "audit-platform/frontend/src/components/workpaper/composables/g7SlotColumns.ts"
SOEMODEL = (
    "audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/"
    "disclosure/g7SoeDisclosureModel.ts"
)
SOETAB = (
    "audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/"
    "disclosure/G7TabDisclosureSOE.vue"
)

T43 = "test_task43_g7_two_level_dynamic_pilot.py"
T43PG = "test_task43_g7_two_level_dynamic_pilot_pg.py"

_SEL = f"{T43}::TestFrozenEntrySelection"
_TPL = f"{T43}::TestAuthoritativeTemplate"
_PICK = f"{T43}::TestManagedSheetSelectionIsMeasured"
_GROUND = f"{T43}::TestContractIsGroundedInTheTemplate"
_P22 = f"{T43}::TestProperty22ColumnIdentityIsDecoupledFromLabel"
_SEED = f"{T43}::TestSecondEdgeSeed"
_RENDER = f"{T43}::TestFourthEdgeRenderLayer"
_DAG = f"{T43}::TestPublishDagIsOneWay"
_RUNTIME = f"{T43}::TestThirdEdgeRuntimeExtract"
_P28 = f"{T43}::TestProperty28DefinitionDriftFailsClosed"
_P66 = f"{T43}::TestProperty66StructuralOperations"
_FOOTER = f"{T43}::TestFooterHasNoTotalFormula"
_SPLIT = f"{T43}::TestStorePayloadSplit"
_PROP = f"{T43}::TestPropertyOracleLanding"
_DEBT = f"{T43}::TestUpstreamDebtsAreVisibleFacts"
_UUIDFIX = f"{T43}::TestUuidCellDuplicationDefectIsFixed"
_SHAPES = f"{T43}::TestUpstreamRelsAndNamespaceShapesStillHold"
_ORDER = f"{T43}::TestOrderingGate"
_WIRE = f"{T43}::TestProductionWiring"
_NODEBT = f"{T43}::TestPilotIntroducesNoResolverDebt"
_KEYS = f"{T43}::TestStoreKeyShapesComeFromTheRenderModel"


# ═══════════════════════════════════════════════════════════════════════════
# 作用域自证回调（数据文件变异必带）
# ═══════════════════════════════════════════════════════════════════════════


def _table_field_is(table_key: str, key: str, expected: object):
    """契约 JSON 里某张表的某个键必须**恰好**是 `expected`。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for table in payload["sheets"][0]["tables"]:
            if table["table_key"] == table_key:
                return table.get(key) == expected
        return False

    return check


def _matrix_field_key_present(stable_field_key: str, expected: bool):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        keys = {
            field["stable_field_key"]
            for table in payload["sheets"][0]["tables"]
            for field in table["fields"]
        }
        return (stable_field_key in keys) is expected

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


def _facts_field_is(section: str, table: str, key: str, expected: object):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        entry = (payload["soe"].get(section) or {}).get(table)
        return isinstance(entry, dict) and entry.get(key) == expected

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
        window = text[start : start + 3200]
        return f'"{key}": {expected_literal}' in window

    return check


def _source_line_counts_are(expected: dict[str, int]):
    """**Python 源码**变异的作用域自证：整行逐字计数必须恰好等于期望。

    🔴 不得把 `_table_field_is` / `_review_field_is` / `_facts_field_is` 这一族喂给
    `path=PG7` 之类的 **.py** 目标 —— 它们内部 `json.loads(data)`，拿到 Python 源码字节
    只会抛 `JSONDecodeError`，被 `cli._run_one` 的宽 `except Exception` 记成
    `verdict=ERROR` / `hit=None`：**pytest 从未跑过**，这条变异却在报告里占了一格。
    Task 43 首轮 M31 正是这个形态（见 `tmp_task43_mut_c.json`），而它偏偏是一条
    **同值**变异 —— 没有作用域自证就更没有别的信号能证明它落对了地方。

    判据取「整行相等」而非子串包含：本任务两处 `"identity": …` 只差缩进（12 / 16 空格），
    子串计数会把 16 空格那行也算进 12 空格的模式里（实测 count 2 而非 1）。这与
    `anchor.find_anchor` 的整行相等语义一致。
    """

    def check(data: bytes) -> bool:
        lines = [line.rstrip("\r\n") for line in data.decode("utf-8").splitlines()]
        return all(
            sum(1 for line in lines if line == text) == count
            for text, count in expected.items()
        )

    return check


MUTATIONS: list[Mutation] = [
    # ── ① 权威模板哨兵（Requirement 9.9）─────────────────────────────
    Mutation(
        id="M01", side="be", path=PG7, kind="replace",
        anchor='    "6bf9e2ebcdf50a1c4a32f8733353dd1de994e7dc483232ad43680043577c3335"',
        new='    "6bf9e2ebcdf50a1c4a32f8733353dd1de994e7dc483232ad43680043577c3336"',
        want=f"{_TPL}::test_template_bytes_are_unchanged",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_PICK}::test_four_edge_seed_covers_exactly_the_two_disclosure_sheets",
        ),
        why="模板字节哨兵改一位后仍绿 ⇒ 「backend/wp_templates 运行时只读」无人把守，"
            "后面每个 definition digest 都会对着一份错模板算出来",
        tags=("template",),
    ),
    Mutation(
        id="M02", side="be", path=PG7, kind="replace",
        anchor="    if digest != TEMPLATE_SHA256:",
        new="    if False and digest != TEMPLATE_SHA256:",
        want=f"{_TPL}::test_template_sentinel_rejects_a_mutated_workbook",
        why="哨兵比对被短路 ⇒ 模板被运行时改写不再抛，静默按新字节继续发布"
            "（fail-open 掩盖接线错误的形态）",
        tags=("template",),
    ),
    # ── ② 选型：matcher 域独占（本 pilot 独有的第四种形态）────────────
    Mutation(
        id="M03", side="be", path=PG7, kind="replace",
        anchor="        if owners != (PILOT_ENTRY_ID,):",
        new="        if False and owners != (PILOT_ENTRY_ID,):",
        want=f"{_SEL}::test_selection_fails_closed_when_the_matcher_domain_is_shared",
        wants=(f"{_SEL}::test_matcher_domain_is_exclusive_and_siblings_share_one_code",),
        why="matcher 域独占判据被短路 ⇒ 以 `G7E`（被两个 entry 共用）为 matcher 的 pilot "
            "会在 registry RG-3 上撞车、`resolve()` 抛 AmbiguousAdapterError，而选型却放行 ——"
            "这正是把三个 G7 候选收敛到一个的那条判据",
        tags=("selection", "matcher"),
    ),
    Mutation(
        id="M04", side="be", path=PG7, kind="replace",
        anchor="        if len(owners) < 2:",
        new="        if False and len(owners) < 2:",
        want=f"{_SEL}::test_selection_fails_closed_when_the_shared_code_becomes_exclusive",
        why="「G7E 仍被共用」这一条被短路 ⇒ 哪天它变独占，当初排除另外两个候选的理由已失效"
            "却无人提醒重做选型（选型结论与依据脱钩）",
        tags=("selection", "matcher"),
    ),
    Mutation(
        id="M05", side="be", path=PG7, kind="replace",
        anchor="        if sibling not in owners:",
        new="        if False and sibling not in owners:",
        want=f"{_SEL}::test_selection_fails_closed_when_a_sibling_stops_using_the_shared_code",
        wants=(f"{_SEL}::test_matcher_domain_is_exclusive_and_siblings_share_one_code",),
        why="「同类候选确实在用共用码」被短路 ⇒ 孪生 entry 换了码之后推导前提失效仍放行",
        tags=("selection", "matcher"),
    ),
    Mutation(
        id="M06", side="be", path=PG7, kind="replace",
        anchor="        if sibling not in assessment.candidate_entry_ids:",
        new="        if False and sibling not in assessment.candidate_entry_ids:",
        want=f"{_SEL}::test_selection_fails_closed_when_a_sibling_leaves_the_candidate_set",
        why="「三个候选」这一前提被短路 ⇒ harness 的类边界变了（候选只剩一个）也照发契约，"
            "matcher 独占性的排除理由无从复核",
        tags=("selection",),
    ),
    Mutation(
        id="M07", side="be", path=PG7, kind="replace",
        anchor="    assessment = assess_pilot_classes(manifest=payload)[PilotClass.g7_two_level_dynamic]",
        new="    assessment = assess_pilot_classes(manifest=payload)[PilotClass.simple_checklist]",
        want=f"{_SEL}::test_selection_passes_on_the_real_manifest",
        wants=(f"{_SEL}::test_class_really_has_three_candidates",),
        why="pilot 类边界改成 simple_checklist ⇒ 「类边界由 harness 判定」退化成本模块自己"
            "声明（Property 49 的分母失守）",
        tags=("selection",),
    ),
    Mutation(
        id="M08", side="be", path=PG7, kind="replace",
        anchor='    if not entry.get("independent_entry"):',
        new='    if False and not entry.get("independent_entry"):',
        want=f"{_SEL}::test_selection_fails_closed_on_parent_duplicate",
        why="parent_duplicate 不再被拒 ⇒ 43 条重复入口都能拿到自己的 adapter，"
            "同一 OO room 会被两个 adapter 各写一遍（AC 12.1「每个独立 entry」）",
        tags=("selection",),
    ),
    Mutation(
        id="M09", side="be", path=PG7, kind="replace",
        anchor="    if codes != set(PILOT_WP_CODES):",
        new="    if False and codes != set(PILOT_WP_CODES):",
        want=f"{_SEL}::test_selection_fails_closed_on_wp_code_drift",
        why="matcher 域与 entry 的 wp_code 不再双向锁死 ⇒ 宿主新增/删掉一个 wp_code 后 "
            "matcher 会漏匹配或越界匹配",
        tags=("selection",),
    ),
    Mutation(
        id="M10", side="be", path=PG7, kind="replace",
        anchor="        if code in set(resolution.index_wp_codes):",
        new="        if False and code in set(resolution.index_wp_codes):",
        want=f"{_SEL}::test_name_extraction_judgement_fails_closed_when_the_code_is_real",
        why="「G7L 不在索引 wp_code 值域里」被短路 ⇒ 哪天 G7L 真成了 wp_code，本 pilot 仍按"
            "「名字提取产物」处置，而那时零回退判据必须换成精确唯一形态",
        tags=("selection", "name-extraction"),
    ),
    Mutation(
        id="M11", side="be", path=PG7, kind="replace",
        anchor="        if any(str(name).startswith(code) for name in resolution.index_filenames):",
        new="        if False and any(str(name).startswith(code) for name in resolution.index_filenames):",
        want=f"{_SEL}::test_name_extraction_judgement_fails_closed_on_a_filename_prefix",
        why="前缀判据被短路 ⇒ 出现 `G7L*.xlsx` 后 `find_template_file_any` 的前缀回退分支"
            "变可达，「零回退 = 根本没有回退」不再成立",
        tags=("selection", "name-extraction"),
    ),
    Mutation(
        id="M12", side="be", path=PG7, kind="replace",
        anchor="        if code not in extracted:",
        new="        if False and code not in extracted:",
        want=f"{_SEL}::test_name_extraction_judgement_fails_closed_on_a_different_host",
        why="「生成器正则能复现 G7L」被短路 ⇒ 宿主改名后推导前提失效却仍放行",
        tags=("selection", "name-extraction"),
    ),
    Mutation(
        id="M13", side="be", path=PG7, kind="replace",
        anchor="    if leaked:",
        new="    if False and leaked:",
        want=f"{_SEL}::test_fallback_judgement_fails_closed_on_a_non_empty_resolution",
        why="零回退判据被短路 ⇒ G7L 一旦解析到某份工作簿，契约的 107 个 source_ref 会指向"
            "另一份底稿的单元格而无人发现",
        tags=("selection",),
    ),
    Mutation(
        id="M14", side="be", path=PG7, kind="replace",
        anchor="    if len(rows) != 1:",
        new="    if False and len(rows) != 1:",
        want=f"{_SEL}::test_fallback_judgement_fails_closed_on_a_non_unique_family_row",
        why="码族「精确唯一」被短路 ⇒ 索引里出现两份 G7 工作簿时 find_template_file 会挑一份，"
            "契约的 source_ref 失去唯一归属",
        tags=("selection",),
    ),
    Mutation(
        id="M15", side="be", path=PG7, kind="replace",
        anchor=r'        if not re.fullmatch(rf"{re.escape(PILOT_WP_CODE_FAMILY)}(-\d+)?[A-Z]?", declared_code):',
        new=r'        if False and not re.fullmatch(rf"{re.escape(PILOT_WP_CODE_FAMILY)}(-\d+)?[A-Z]?", declared_code):',
        want=f"{_SEL}::test_render_schema_wp_code_must_stay_inside_the_code_family",
        why="配置真源的码族判据被短路 ⇒ 两份 YAML 改成任意 wp_code 都放行，"
            "「权威模板由配置唯一声明」失守",
        tags=("selection", "config"),
    ),
    Mutation(
        id="M16", side="be", path=PG7, kind="replace",
        anchor="        if relative not in declared:",
        new="        if False and relative not in declared:",
        want=f"{_SEL}::test_selection_fails_closed_when_a_render_schema_is_unobserved",
        why="「不得对未观测的配置放行」被短路 ⇒ 只观测一份 YAML 也算通过，"
            "另一份指到别的工作簿时无人发现（fail-open 的常见形态）",
        tags=("selection", "config"),
    ),
    Mutation(
        id="M17", side="be", path=PG7, kind="replace",
        anchor='        if "/".join(str(declared[relative]).split("\\\\")) != expected:',
        new='        if False and "/".join(str(declared[relative]).split("\\\\")) != expected:',
        want=f"{_SEL}::test_selection_fails_closed_when_a_render_schema_points_elsewhere",
        why="配置声明的 template_path 与冻结模板的一致性被短路 ⇒ 配置指到 H1 固定资产也照发"
            "契约，等于「据另一份底稿建契约」",
        tags=("selection", "config"),
    ),
    Mutation(
        id="M18", side="be", path=PG7, kind="replace",
        anchor="    entry = entries.get(PILOT_ENTRY_ID)",
        new='    entry = entries.get(PILOT_ENTRY_ID) or {"independent_entry": True}',
        want=f"{_SEL}::test_selection_fails_closed_when_the_entry_disappears",
        why="entry 消失时用空壳兜底 ⇒ 宿主挂载点已删掉，契约却继续按旧单元格发布",
        tags=("selection",),
    ),
]

MUTATIONS += [
    # ── ③ 两级表头与受管 sheet 选择（AC 6.3）───────────────────────
    Mutation(
        id="M19", side="be", path=PG7, kind="replace",
        anchor="LEAF_HEADER_ROW: Final[int] = 63",
        new="LEAF_HEADER_ROW: Final[int] = 64",
        want=f"{_GROUND}::test_every_matrix_leaf_header_matches_the_real_cell_text",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_GROUND}::test_matrix_header_rows_is_two",
            f"{_P22}::test_duplicate_leaf_labels_really_exist_in_the_template",
        ),
        why="叶子表头行下移一行 ⇒ 契约的 100 个 header_source_ref 全部指到 metric 数据行，"
            "「两级表头」变成「表头 + 数据行」；仍绿说明表头文本从未与源 xlsx 比对",
        tags=("two-level",),
    ),
    Mutation(
        id="M20", side="be", path=PG7, kind="replace",
        anchor='    (f"C{GROUP_HEADER_ROW}:D{GROUP_HEADER_ROW}", "C", "<DYNAMIC:c3>"),',
        new='    (f"C{GROUP_HEADER_ROW}:E{GROUP_HEADER_ROW}", "C", "<DYNAMIC:c3>"),',
        want=f"{_GROUND}::test_every_matrix_group_header_is_a_real_blank_merge",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_SEED}::test_seed_describes_my_matrix_exactly",
        ),
        why="第一个动态列占位的合并跨度被改成 3 列 ⇒ 与源 xlsx 的 `C62:D62` 不符；仍绿说明"
            "「组标题指向真实合并区」这条判据没跑在 openpyxl 实测上",
        tags=("two-level", "dynamic-columns"),
    ),
    Mutation(
        id="M21", side="be", path=PG7, kind="replace",
        anchor='    ("minority-fs-3", "资产合计"),',
        new='    ("minority-fs-3", "资产总计"),',
        want=f"{_GROUND}::test_every_metric_row_label_matches_the_real_merged_cell",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_GROUND}::test_metric_ids_and_labels_are_source_ordered",
            f"{_RENDER}::test_render_model_metric_labels_match_the_source_rows",
        ),
        why="metric 标签改一个字 ⇒ 与源 `A66` 及渲染层 `minorityFsLabels` 双双不符；"
            "仍绿说明 metric 标签是自由文本（Requirement 6.1 禁止无来源自造字段）",
        tags=("two-level", "metrics"),
    ),
    Mutation(
        id="M22", side="be", path=PG7, kind="replace",
        anchor='MATRIX_LABEL_HEADER: Final[str] = "项  目"',
        new='MATRIX_LABEL_HEADER: Final[str] = "项 目"',
        want=f"{_GROUND}::test_label_header_text_is_the_real_cell_text",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_SEED}::test_seed_describes_my_matrix_exactly",
        ),
        why="标签列表头由**双空格**改成单空格 ⇒ 与源 `A62` 及 seed 的 `label_header_raw` 不符。"
            "上市侧同名表恰恰是单空格，混用就是「据另一张表建契约」",
        tags=("two-level",),
    ),
    Mutation(
        id="M23", side="be", path=PG7, kind="replace",
        anchor="        \"header_rows\": MATRIX_HEADER_ROW_COUNT,",
        new="        \"header_rows\": 1,",
        want=f"{_GROUND}::test_matrix_header_rows_is_two",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="矩阵的 header_rows 写成 1 ⇒ 契约不再表达两级表头（Requirement 6.3 的本体），"
            "而两级表头正是本 pilot 的类特征",
        tags=("two-level",),
    ),
    Mutation(
        id="M24", side="be", path=PG7, kind="replace",
        anchor="    for metric_key, metric_label in MATRIX_METRICS:",
        new="    for metric_key, metric_label in MATRIX_METRICS[:5]:",
        want=f"{_GROUND}::test_field_counts_are_the_real_template_facts",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_GROUND}::test_every_matrix_leaf_header_matches_the_real_cell_text",
        ),
        why="只声明前 5 个 metric ⇒ 后 5 行（营业收入/净利润/综合收益总额/经营活动现金流量 等）"
            "的披露格彻底不受管；仍绿说明字段计数不是实测事实",
        tags=("coverage",),
    ),
    Mutation(
        id="M25", side="be", path=PG7, kind="replace",
        anchor='MANAGED_SHEET: Final[str] = "附注披露信息（国企）"',
        new='MANAGED_SHEET: Final[str] = "附注披露信息（上市公司）"',
        want=f"{_PICK}::test_my_matrix_data_cells_are_all_empty_in_the_source",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_TPL}::test_workbook_has_twenty_two_sheets_and_only_one_is_declared",
        ),
        why="受管 sheet 改成上市侧 ⇒ 那张 sheet 的同构矩阵数据格**全是公式**（零 editable），"
            "merge 家族两条 required scenario 结构性不可满足。仍绿说明「为什么选国企侧」"
            "只是文档声明",
        tags=("sheet-selection",),
    ),
    Mutation(
        id="M26", side="be", path=PG7, kind="replace",
        anchor='UUID_COL: Final[str] = "N"',
        new='UUID_COL: Final[str] = "M"',
        want=f"{_PICK}::test_uuid_column_choice_is_forced_by_real_column_usage",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="UUID 列取 `M` ⇒ 隐藏该列会藏掉 `M9..M19` 共 13 格可见业务内容"
            "（Requirement 6.13 不得改变业务公式/标签）",
        tags=("geometry",),
    ),
]

MUTATIONS += [
    # ── ④ Property 22：动态列 key 与 label 解耦 ─────────────────────
    Mutation(
        id="M27", side="be", path=PG7, kind="replace",
        anchor="    count = len(tuple(entity_names)) * len(RENDER_SUB_COLUMNS)",
        new="    count = 10",
        want=f"{_P22}::test_column_count_is_never_hardcoded",
        why="列数写死成 10 ⇒ 平台铁律「按公司/单位横向展开的表禁写死列数」失守：删到 3 家仍"
            "产 10 列（多出的列在契约里对不上）、增到 6 家会截断第 6 家",
        tags=("dynamic-columns", "hardcode"),
    ),
    Mutation(
        id="M28", side="be", path=PG7, kind="replace",
        anchor="    return dynamic_column_stable_keys(slot=MATRIX_TABLE_KEY, count=count)",
        new='    return tuple(f"{MATRIX_TABLE_KEY}_{seq}" for seq in range(1, count + 1))',
        want=f"{_P22}::test_module_delegates_key_generation_and_never_reimplements_it",
        why="键生成从委派上游改成本模块自拼 ⇒ 出现第二真源：`DYNAMIC_COLUMN_IDENTITY_TEMPLATE` "
            "一改形状（比如 `{slot}#{seq}`），本模块仍按旧形状产键而契约校验器按新形状判",
        tags=("dynamic-columns",),
    ),
    Mutation(
        id="M29", side="be", path=PG7, kind="replace",
        anchor="    sub_key = RENDER_SUB_COLUMNS[(seq - 1) % width][0]",
        new="    sub_key = RENDER_SUB_COLUMNS[0][0]",
        want=f"{_P22}::test_seq_to_column_and_render_key_are_bijective",
        wants=(
            f"{_RENDER}::test_slot_key_rule_matches_my_conversion",
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_SPLIT}::test_split_yields_one_field_per_metric_per_dynamic_column",
        ),
        why="子列换算恒取第一个 ⇒ 每个实体的「期初」列被映到「期末」渲染键，两套键空间的"
            "双射断裂：HTML 侧改期初、Excel 侧写期末（静默错值路径）",
        tags=("dynamic-columns", "key-space"),
    ),
    Mutation(
        id="M30", side="be", path=PG7, kind="replace",
        anchor="    return _col_letter(_col_index(DYNAMIC_FIRST_COLUMN) + seq - 1)",
        new="    return _col_letter(_col_index(DYNAMIC_FIRST_COLUMN) + (seq - 1) * 2)",
        want=f"{_P22}::test_binding_maps_each_key_to_its_own_column",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_RUNTIME}::test_baseline_extract_reads_back_every_managed_field",
        ),
        why="seq→列标改成隔列取 ⇒ 第 6..10 个键落到 M..V（越出受管区域），前 5 个键落到"
            "C/E/G/I/K：某家公司的期初金额会被读到另一家的期末列（AC 6.4 明令要防的那件事）",
        tags=("dynamic-columns",),
    ),
    Mutation(
        id="M31", side="be", path=PG7, kind="replace",
        anchor='            "identity": DYNAMIC_COLUMN_IDENTITY_TEMPLATE,',
        new='            "identity": "{slot}_{seq}",',
        want=f"{_P22}::test_contract_identity_is_the_imported_constant_never_a_literal",
        why="把 identity 从常量改成硬编码字面量 ⇒ 与 `contracts.DYNAMIC_COLUMN_IDENTITY_TEMPLATE` "
            "脱钩：模板一改形状，契约里仍是旧字面量。🔴 本条**故意**写成同值 —— 它检验的是"
            "「契约的 identity 是否引用单一真源」这条源码级判据，而不是值是否相等。"
            "🔴 `want` 只能是源码级判据：同值变异下磁盘契约逐字节相同，"
            "`test_disk_contract_matches_the_source_of_truth` / "
            "`test_key_space_split_debt_is_a_measured_fact` 这类值判据**必然**照绿"
            "（首轮把 want 指到后者 ⇒ 实测 GREEN，见 tmp_task43_mut_d_probe.json）",
        tags=("dynamic-columns", "key-space"),
        # 同值变异 ⇒ 作用域自证是唯一能证明它落对地方的信号：12 空格那行（矩阵 payload）
        # 被换成字面量、16 空格那行（`build_contract_payload` 的事实块）原样存活。
        scope_check=_source_line_counts_are(
            {
                '            "identity": "{slot}_{seq}",': 1,
                '                "identity": DYNAMIC_COLUMN_IDENTITY_TEMPLATE,': 1,
            }
        ),
    ),
    Mutation(
        id="M32", side="be", path=PG7, kind="replace",
        anchor='    return f"{MATRIX_TABLE_KEY}/{metric_key}/{column_key}"',
        new='    return f"{MATRIX_TABLE_KEY}/{metric_key}/{RENDER_SUB_COLUMNS[0][1]}"',
        want=f"{_P22}::test_stable_field_keys_are_distinct_and_carry_no_chinese_label",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_GROUND}::test_field_counts_are_the_real_template_facts",
        ),
        why="stable key 用**可改 label** 代替 column_key ⇒ 10 列共用 2 个 label ⇒ 100 个键塌成 "
            "10 个（撞键），且键里出现中文（Requirement 6.14 明禁）。这正是 H7 付过学费的形态",
        tags=("dynamic-columns", "property22"),
    ),
    Mutation(
        id="M33", side="be", path=PG7, kind="replace",
        anchor="    keys = dynamic_column_keys_for_entities(names)",
        new="    keys = dynamic_column_keys_for_entities(names)[:1] * (len(names) * 2)",
        want=f"{_P22}::test_renaming_every_entity_does_not_change_any_key",
        wants=(f"{_P22}::test_duplicate_keys_in_observed_pairs_fail_closed",),
        why="实测 `(label, key)` 对全部共用第一个键 ⇒ 「重复 label 不撞键」这条 Property 22 的"
            "核心断言若失效，10 列会全部写到同一列",
        tags=("dynamic-columns", "property22"),
    ),
    Mutation(
        id="M34", side="be", path=EG, kind="replace",
        anchor="    if len(set(observed_keys)) != len(observed_keys):",
        new="    if False and len(set(observed_keys)) != len(observed_keys):",
        want=f"{_P22}::test_duplicate_keys_in_observed_pairs_fail_closed",
        why="上游「实测键互不相同」这一条被短路 ⇒ 两家同名公司共用一个键时不再打红"
            "（顺序不可交换：它必须排在「与派生结果逐项相等」之前，否则永久不可达）",
        tags=("dynamic-columns", "upstream-gate"),
    ),
]

MUTATIONS += [
    # ── ⑤ 四边真源：seed 与渲染层 ────────────────────────────────
    Mutation(
        id="M35", side="be", path=PG7, kind="replace",
        anchor='    if str(meta.get("source_sha256") or "") != TEMPLATE_SHA256:',
        new='    if False and str(meta.get("source_sha256") or "") != TEMPLATE_SHA256:',
        want=f"{_SEED}::test_seed_lookup_fails_closed_on_a_different_workbook",
        why="seed 侧「描述的是同一份工作簿」判据被短路 ⇒ facts 与源 xlsx 脱钩后仍当第 2 边用，"
            "四边真源退化成三边",
        tags=("four-edge", "seed"),
    ),
    Mutation(
        id="M36", side="be", path=PG7, kind="replace",
        anchor="        if table is None:",
        new="        if False and table is None:",
        want=f"{_SEED}::test_seed_lookup_fails_closed_when_my_table_disappears",
        why="seed 里找不到本表时不再抛 ⇒ 返回 `{table_key: None}`，第 2 边的逐字比对在 None 上"
            "静默通过（fail-open 掩盖接线错误）",
        tags=("four-edge", "seed"),
    ),
    Mutation(
        id="M37", side="be", path=PG7, kind="replace",
        anchor="    return two_level, exempt, two_level - exempt",
        new="    return two_level, exempt, two_level",
        want=f"{_PICK}::test_seed_counts_reproduce_the_archived_spec_numbers",
        why="「应渲染两级」的期望不再剔除 `single_slot_exemption` ⇒ 24 而不是 20，"
            "而 `is_two_level` 是源侧物理结构字段、把父行为空的占位合并也算两级"
            "（归档 spec 实测过的那条口径）",
        tags=("four-edge", "seed", "exemption"),
    ),
    Mutation(
        id="M38", side="be", path=PG7, kind="replace",
        anchor='        if "single_slot_exemption" in table:',
        new='        if False and "single_slot_exemption" in table:',
        want=f"{_PICK}::test_exemption_judgement_fails_closed_when_my_table_becomes_exempt",
        why="「本表不在豁免登记里」被短路 ⇒ 已裁决为「单槽 flat、不声明 group」的表也能当"
            "两级动态表 pilot，等于把已裁决豁免当待修偏差",
        tags=("four-edge", "exemption"),
    ),
    Mutation(
        id="M39", side="be", path=FACTS, kind="replace",
        anchor='        "is_two_level": true,',
        new='        "is_two_level": false,',
        want=f"{_SEED}::test_seed_describes_my_matrix_exactly",
        wants=(f"{_PICK}::test_seed_counts_reproduce_the_archived_spec_numbers",),
        why="seed 里本表的 `is_two_level` 改成 false ⇒ 第 2 边与源 xlsx（行 62/63 两级）矛盾；"
            "仍绿说明第 2 边只是摆设",
        tags=("four-edge", "seed"),
        # 🔴 `"is_two_level": true,` 在 facts 里出现 24 次 ⇒ 用**唯一**的 `source_rows`
        #    （`A62:L63` 全库仅 1 处）作 scope 相对定位，不用绝对行号。
        scope='        "source_rows": "A62:L63",',
        offset=-2,
        scope_check=_facts_field_is(
            "七、重要非全资子公司", "主要财务信息", "is_two_level", False
        ),
    ),
    Mutation(
        id="M40", side="be", path=PG7, kind="replace",
        anchor='    if not facts["header_block_symbols_used_by_tab"]:',
        new='    if False and not facts["header_block_symbols_used_by_tab"]:',
        want=f"{_RENDER}::test_each_missing_element_turns_the_fourth_edge_red",
        why="第四边的「符号真被引用」判据被短路 ⇒ 归档 spec 实测过的「声明了 group 但零渲染」"
            "（0/38 张）会重新变成绿的",
        tags=("four-edge", "render"),
    ),
    Mutation(
        id="M41", side="be", path=PG7, kind="replace",
        anchor="        if not facts[key]:",
        new="        if False and not facts[key]:",
        want=f"{_RENDER}::test_each_missing_element_turns_the_fourth_edge_red",
        wants=(f"{_RENDER}::test_render_layer_really_renders_two_level_headers",),
        why="第四边的三要素（遍历 + 外层门控 + 内层嵌套）判据被短路 ⇒ 只要模型里有 group 字段"
            "就算两级已渲染，DOM 层的真相不再被检查",
        tags=("four-edge", "render"),
    ),
    Mutation(
        id="M42", side="be", path=PG7, kind="replace",
        anchor="    renderers: set[str] = set(used_symbols)",
        new="    renderers: set[str] = set(used_symbols) | {'headerBlocks'}",
        want=f"{_RENDER}::test_each_missing_element_turns_the_fourth_edge_red",
        why="把本地包装名写死进渲染源集合 ⇒ 包装链解析退化成硬编码名字，`buildG7HeaderBlocks` "
            "被删掉后 `headerBlocks` 仍能命中，第四边判据失去与导入符号的联系",
        tags=("four-edge", "render"),
    ),
    Mutation(
        id="M43", side="fe", path=SOETAB, kind="replace",
        anchor='                      <el-table-column v-if="blk.group" :label="blk.group" align="center">',
        new='                      <el-table-column v-show="blk.group" :label="blk.group" align="center">',
        want=f"{_RENDER}::test_render_layer_really_renders_two_level_headers",
        wants=(f"{_RENDER}::test_each_missing_element_turns_the_fourth_edge_red",),
        why="两级门控从 `v-if` 换成 `v-show` ⇒ `el-table-column` 的父列节点仍会被创建，"
            "无 group 的列会多出一层空表头（真实渲染形态变了）。仍绿说明第四边只在数字上比对",
        tags=("four-edge", "render"),
    ),
    Mutation(
        id="M44", side="fe", path=SLOTCOLS, kind="replace",
        anchor="        key: `${slot}_${seq}_${s.key}`,",
        new="        key: `${slot}_${seq}-${s.key}`,",
        want=f"{_RENDER}::test_slot_key_rule_matches_my_conversion",
        wants=(f"{_RENDER}::test_render_layer_really_renders_two_level_headers",),
        why="渲染层的子列键分隔符从 `_` 改成 `-` ⇒ 本模块的 `render_column_key_for_seq` 换算"
            "与它脱钩，contract 的 json_pointer 指向的键在 store 里根本不存在（静默丢整列）",
        tags=("four-edge", "key-space"),
    ),
    Mutation(
        id="M45", side="fe", path=SOEMODEL, kind="replace",
        anchor="  { key: 'current', label: '期末数/本期发生额' },",
        new="  { key: 'current', label: '期末/本期' },",
        want=f"{_RENDER}::test_render_model_declares_my_slot_and_sub_columns",
        wants=(
            f"{_GROUND}::test_every_matrix_leaf_header_matches_the_real_cell_text",
        ),
        why="渲染层子列 label 简写 ⇒ 与源 `C63` 逐字不符（归档 spec 明确修过这条「不得简写」）；"
            "仍绿说明第 4 边的 label 比对没跑",
        tags=("four-edge", "render"),
    ),
    Mutation(
        id="M46", side="be", path=PG7, kind="replace",
        anchor='RENDER_MATRIX_TABLE_ID: Final[str] = "minority-financials"',
        new='RENDER_MATRIX_TABLE_ID: Final[str] = "minority-fs"',
        want=f"{_KEYS}::test_store_table_key_is_the_table_id_not_the_metric_prefix",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{T43PG}::test_every_real_payload_carries_my_two_tables",
        ),
        why="store 表键写成 metric 行 id 前缀（首轮真踩过的错）⇒ `state.tables` 里取不到那张表，"
            "真实库三条载荷全部读成「无此表」，Property 22 的真实载荷 oracle 变成空集",
        tags=("store", "key-space"),
    ),
]

MUTATIONS += [
    # ── ⑥ Property 28：漂移 fail closed ─────────────────────────────
    Mutation(
        id="M47", side="be", path=PG7, kind="replace",
        anchor="    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):",
        new="    if False and canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):",
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        why="磁盘契约 ↔ 现算 payload 的双向锁被短路 ⇒ 改代码不改契约、或改契约不改代码都能"
            "悄悄漂移，而 `assert_contract_identity_frozen` 就只是在比两个都错的值",
        tags=("property28", "contract-lock"),
    ),
    Mutation(
        id="M48", side="be", path=PG7, kind="replace",
        anchor="    parse_contract(expected, adapter_id=PILOT_ADAPTER_ID)",
        new="    _ = expected",
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        why="现算 payload 不再过强校验 ⇒ 磁盘与代码两边都非法时仍放行"
            "（双向锁只证「两边相等」，不证「两边合法」）",
        tags=("property28", "contract-lock"),
    ),
    Mutation(
        id="M49", side="be", path=CONTRACT, kind="replace",
        anchor='          "header_rows": 2,',
        new='          "header_rows": 3,',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        wants=(f"{_GROUND}::test_matrix_header_rows_is_two",),
        why="直接改磁盘契约的 header_rows ⇒ 双向锁的**磁盘侧**若无人把守，任何人手改契约都能"
            "生效而代码侧毫不知情",
        tags=("property28", "contract-lock"),
        scope_check=_table_field_is("minority_financials", "header_rows", 3),
    ),
    Mutation(
        id="M50", side="be", path=CONTRACT, kind="replace",
        anchor='          "row_identity": {',
        new='          "row_identity_DISABLED": {',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        wants=(f"{_GROUND}::test_record_table_is_the_dynamic_row_table",),
        why="把动态行表的 `row_identity` 声明改名 ⇒ 契约校验器（CS-14）本该拒「有 delete_policy "
            "却没有 row_identity」；磁盘侧无人把守时这份契约会被当合法契约发布，"
            "而 `managed_tables_of` 会因为找不到动态行表而 fail closed",
        tags=("property28", "row-identity"),
        scope_check=lambda data: '"row_identity_DISABLED"' in data.decode("utf-8"),
    ),
    Mutation(
        id="M51", side="be", path=PG7, kind="replace",
        anchor="    for column_key, column, mode, value_type, render_key, header_text in RECORD_COLUMNS:",
        new="    for column_key, column, mode, value_type, render_key, header_text in RECORD_COLUMNS[:1]:",
        want=f"{_GROUND}::test_every_record_header_matches_the_real_cell_text",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_GROUND}::test_formula_mask_covers_every_formula_field",
        ),
        why="记录表只声明第 1 列 ⇒ 六个公式列全部脱管，`formula_mask` 覆盖不到任何 formula 字段，"
            "受保护集合塌成空集（Property 24 的分母失守）",
        tags=("coverage", "formula-mask"),
    ),
    Mutation(
        id="M52", side="be", path=PG7, kind="replace",
        anchor='    f"B{RECORD_FIRST_ROW}:G{RECORD_LAST_ROW}",',
        new='    f"B{RECORD_FIRST_ROW}:C{RECORD_LAST_ROW}",',
        want=f"{_GROUND}::test_formula_mask_covers_every_formula_field",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="公式 mask 只覆盖 B:C ⇒ D..G 四个 formula 字段落在只读区域之外，"
            "契约校验器（CS-13）本该拒；仍绿说明 mask 与 formula 字段没有双向锁",
        tags=("formula-mask",),
    ),
    Mutation(
        id="M53", side="be", path=PG7, kind="replace",
        anchor="RECORD_FORMULA_SOURCE_FIRST_ROW: Final[int] = 9",
        new="RECORD_FORMULA_SOURCE_FIRST_ROW: Final[int] = 10",
        want=f"{_GROUND}::test_record_formula_cells_match_the_declared_template",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="公式源表首行错一行 ⇒ 契约声明的 30 条公式全部比源 `B79..G83` 的实测公式偏移一行"
            "（本表第 79 行拉源表第 10 行而不是第 9 行）；仍绿说明公式来源是自由文本",
        tags=("formula-mask",),
    ),
]

MUTATIONS += [
    # ── ⑦ footer / 未管理区域 / metadata sheet ────────────────────
    Mutation(
        id="M54", side="be", path=PG7, kind="replace",
        anchor='FOOTER_MARKER: Final[str] = "（2）本期出售的子公司出售日的财务状况"',
        new='FOOTER_MARKER: Final[str] = "合计"',
        want=f"{_GROUND}::test_footer_marker_is_the_real_cell_text",
        wants=(
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_P66}::test_footer_anchor_drift_is_detected",
            f"{_P66}::test_footer_marker_is_found_through_the_numeric_reference_decoder",
        ),
        why="footer marker 改成「合计」（本 sheet 的受管区域**没有**合计行）⇒ "
            "`assert_footer_anchor_stable` 一处都找不到、直接 FooterAnchorDriftError；"
            "仍绿说明 marker 从未与源 `A85` 比对",
        tags=("footer",),
    ),
    Mutation(
        id="M55", side="be", path=PG7, kind="replace",
        anchor='        f"A{MATRIX_TERMINATOR_ROW}",',
        new='        f"A{MATRIX_TERMINATOR_ROW + 1}",',
        want=f"{_GROUND}::test_unmanaged_neighbour_cells_are_the_real_contents",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="未管理区域邻域登记的坐标下移一行 ⇒ 那条 `【提示：…】` 与登记文本不再对应；"
            "仍绿说明「未管理区域的真实内容」这份清单与源 xlsx 脱钩",
        tags=("unmanaged",),
    ),
    Mutation(
        id="M56", side="be", path=PG7, kind="replace",
        anchor='RECORD_FOOTER_ROW: Final[int] = 85',
        new='RECORD_FOOTER_ROW: Final[int] = 84',
        want=f"{_P66}::test_footer_anchor_drift_is_detected",
        wants=(
            f"{_GROUND}::test_footer_marker_is_the_real_cell_text",
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
            f"{_FOOTER}::test_footer_formula_gate_returns_an_empty_checked_list",
        ),
        why="footer 行改成 84（空行）⇒ `_GT_SYNC` 冻结的 GT_FOOTER_ROW 与 marker 实测行不一致，"
            "写入侧本该 fail closed；仍绿说明 footer 的两个独立载体没有交叉验证",
        tags=("footer",),
    ),
    Mutation(
        id="M57", side="be", path=PG7, kind="insert",
        anchor='                "locator": {"anchor": TABLE_SHEET_ANCHOR},',
        new='                "metadata_sheet": "_GT_SYNC",',
        want=f"{_GROUND}::test_contract_declares_no_metadata_sheet",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="往契约的 sheet 块里塞 `_GT_SYNC` ⇒ 隐藏元数据表出现在受管业务声明里"
            "（Requirement 6.13/6.17 明禁，任务正文也点名「metadata sheet 不进入披露表」）",
        tags=("metadata-sheet",),
    ),
]

MUTATIONS += [
    # ── ⑧ store 拆分与历史键 ──────────────────────────────────────
    Mutation(
        id="M58", side="be", path=PG7, kind="replace",
        anchor="        if matched == 0 and cells:",
        new="        if False and matched == 0 and cells:",
        want=f"{_KEYS}::test_legacy_column_keys_fail_closed_instead_of_dropping_a_row",
        wants=(f"{T43PG}::test_legacy_payload_fails_closed_instead_of_dropping_the_rows",),
        why="「一整行有值却一个键都对不上」不再 fail closed ⇒ 真实库里那条历史键载荷会被静默"
            "拆成 0 个字段（整块披露数据被扔掉）—— 本 spec 最贵的 fail-open 形态",
        tags=("store", "legacy-keys"),
    ),
    Mutation(
        id="M59", side="be", path=PG7, kind="replace",
        anchor='    if not isinstance(names, (list, tuple)) or not names:',
        new='    if False and (not isinstance(names, (list, tuple)) or not names):',
        want=f"{_SPLIT}::test_entities_missing_fails_closed",
        why="实体列表缺失/为空时不再抛 ⇒ 「审计师删到 0 家」会被静默当成 0 列，"
            "而正确行为是 fail closed（否则回退默认名 = 写死列数的另一种形态）",
        tags=("store",),
    ),
    Mutation(
        id="M60", side="be", path=PG7, kind="replace",
        anchor="        if metric_key in seen:",
        new="        if False and metric_key in seen:",
        want=f"{_SPLIT}::test_duplicate_metric_id_fails_closed",
        why="重复 metric id 不再判结构冲突 ⇒ 复制行产生的重复身份被静默合并成一行"
            "（Requirement 6.15）",
        tags=("store",),
    ),
    Mutation(
        id="M61", side="be", path=PG7, kind="replace",
        anchor="        if not isinstance(metric_key, str) or metric_key not in known:",
        new="        if False and (not isinstance(metric_key, str) or metric_key not in known):",
        want=f"{_SPLIT}::test_unknown_metric_id_fails_closed",
        why="未登记 metric id 不再被拒 ⇒ 按数组下标推 metric（Requirement 6.5 明禁），"
            "行序一变值就串行",
        tags=("store",),
    ),
    Mutation(
        id="M62", side="be", path=PG7, kind="replace",
        anchor="    if version != STORE_STATE_VERSION:",
        new="    if False and version != STORE_STATE_VERSION:",
        want=f"{_SPLIT}::test_wrong_state_version_fails_closed",
        why="state version 不匹配时不再抛 ⇒ 前端 `applySavedState` 对不匹配版本直接 return，"
            "拆分侧却按旧结构猜（两侧语义分叉）",
        tags=("store",),
    ),
    Mutation(
        id="M63", side="be", path=PG7, kind="replace",
        anchor="            spec = contract.field_by_stable_key(stable_key)",
        new="            spec = next(iter(contract.all_fields()))",
        want=f"{_SPLIT}::test_split_uses_the_contract_as_the_spec_source",
        wants=(
            f"{_SPLIT}::test_split_yields_one_field_per_metric_per_dynamic_column",
            f"{_SPLIT}::test_more_entities_than_the_contract_declares_fail_closed",
        ),
        why="`value_type`/`mode` 不再从契约取 ⇒ 写错一个 column_key 会静默产出一个契约里没有的"
            "字段，而不是立刻炸（本 spec 反复强调的「找不到契约必须抛」）",
        tags=("store",),
    ),
]

MUTATIONS += [
    # ── ⑨ 本任务修掉的生产缺陷（UUID 格重复）─────────────────────
    Mutation(
        id="M64", side="be", path=EI, kind="replace",
        anchor="        if existing is not None:",
        new="        if False and existing is not None:",
        want=f"{_UUIDFIX}::test_instrumented_uuid_cells_are_unique_per_row",
        wants=(
            f"{_UUIDFIX}::test_old_append_only_behaviour_would_have_duplicated",
            f"{_P66}::test_lost_row_identity_is_a_retention_failure",
            f"{_P66}::test_reorder_keeps_values_attached_to_identity",
        ),
        why="退回「无条件在 </row> 前追加 UUID 格」⇒ 本 sheet 的 `N79..N83` 出现两个相同 `r` 的 "
            "`<c>`（非法 OOXML）：Excel/OO 可能拒绝打开或静默丢一个，而结构操作 fixture 会改到"
            "模板那一个（首轮实测的静默失效）",
        tags=("uuid-cell", "engine-defect"),
    ),
    Mutation(
        id="M65", side="be", path=EI, kind="replace",
        anchor="            sheet_xml = sheet_xml[: existing.start()] + cell + sheet_xml[existing.end() :]",
        new="            sheet_xml = sheet_xml",
        want=f"{_UUIDFIX}::test_instrumented_uuid_cells_are_unique_per_row",
        wants=(
            f"{_UUIDFIX}::test_old_append_only_behaviour_would_have_duplicated",
            f"{_RUNTIME}::test_instrumentation_produces_all_four_carriers",
        ),
        why="既有格被识别出来却**不替换** ⇒ 那五行根本没有 row UUID（identity inventory 为空），"
            "extract 一开就 IdentityCarrierMissing。与 M64 同源但故障点不同：这条检验的是"
            "**替换动作**本身，M64 检验的是分支门控",
        tags=("uuid-cell", "engine-defect"),
    ),
    # ── ⑩ 顺序门与接线 ───────────────────────────────────────────
    Mutation(
        id="M66", side="be", path=PG7, kind="replace",
        anchor="    if capability is not Capability.bidirectional:",
        new="    if False and capability is not Capability.bidirectional:",
        want=f"{_ORDER}::test_capability_is_not_enabled_before_finalize",
        wants=(f"{_ORDER}::test_capability_predicate_agrees_with_the_ordering_gate",),
        why="顺序门被短路 ⇒ finalize 之前就能注册 bidirectional adapter，"
            "而 representation 尚未 published（任务正文的顺序被跳过）",
        tags=("ordering",),
    ),
    Mutation(
        id="M67", side="be", path=PG7, kind="replace",
        anchor='    if str(entry.get("adapter_id") or "") != PILOT_ADAPTER_ID:',
        new='    if False and str(entry.get("adapter_id") or "") != PILOT_ADAPTER_ID:',
        want=f"{_ORDER}::test_capability_predicate_agrees_with_the_ordering_gate",
        why="顺序门的第二条判据（manifest adapter_id 必须是本 pilot）被短路 ⇒ manifest 指向别的"
            "adapter 时也放行，两个 pilot 会抢同一个 entry",
        tags=("ordering",),
    ),
    Mutation(
        id="M68", side="be", path=PG7, kind="replace",
        anchor="    except PilotSelectionError:",
        new="    except Exception:",
        want=f"{_ORDER}::test_capability_predicate_agrees_with_the_ordering_gate",
        why="窄 except 改成宽 except ⇒ manifest 读不出来之类的真故障被吞成「未启用」"
            "（本 spec 最贵的 fail-open 形态）",
        tags=("ordering", "fail-open"),
    ),
    Mutation(
        # 🔴 Task 75 重指锚点：欠账已结清，`raise PilotSelectionError(<欠账>)` 那行不存在了
        #    （原锚点 0 命中 = ANCHOR-MISS）。判据强度不变 —— want 仍是同一条测试，变异仍
        #    精确构造 Task 75 正文逐字禁止的中间形态②「函数改成 `return None`」。
        id="M69", side="be", path=PG7, kind="insert",
        scope="    observation = await observe_published_frozen_definitions(",
        offset=-2,
        anchor="    from app.services.workpaper_sync.resolution import CanonicalResolutionService",
        new="    return None",
        want=f"{_DEBT}::test_resolve_published_definitions_never_returns_none",
        why="缺观测器时返回 None 而不是抛 ⇒ 上游把「缺观测器」表现成「这个 entry 没有身份」，"
            "一路静默走到「注册一个没有 identity binding 的 adapter」",
        tags=("fail-open",),
    ),
    Mutation(
        id="M70", side="be", path=PG7, kind="replace",
        anchor="    if xlsx_dynamic:",
        new="    if False and xlsx_dynamic:",
        want=f"{_DEBT}::test_dynamic_debt_is_retracted_when_upstream_fixes_the_gate",
        why="欠账的**撤销条件**被短路 ⇒ 上游把门修好后无人提醒撤销登记，"
            "Property 22 会永久落在替代场景上（欠账变成永久注释）",
        tags=("debt",),
    ),
    Mutation(
        id="M71", side="be", path=RG, kind="replace",
        anchor='        "adapter_registered": False,',
        new='        "adapter_registered": True,',
        want=f"{_ORDER}::test_ledger_records_adapter_not_registered_yet",
        why="交付登记表宣称 adapter 已注册 ⇒ 「契约孤儿」这条可见欠账被抹掉，"
            "而 registry 里其实一个 adapter 都没有（伪双向的账面形态）",
        tags=("ledger",),
        scope='        "contract_id": "g7.soe_subsidiary_disclosure",',
        # 🔴 Task 75 把 `provider_module` 加进了每条登记行 ⇒ 行内偏移 7 → 8。
        offset=8,
        scope_check=_ledger_row_field_is("g7.soe_subsidiary_disclosure", "adapter_registered", "True"),
    ),
    Mutation(
        id="M72", side="be", path=ROUTER, kind="replace",
        anchor="        + await attach_g7_pilot_adapters(svc.registry, session=svc.session)",
        new="        + ()",
        want=f"{_WIRE}::test_router_calls_the_g7_attach_on_both_paths",
        why="第一个生产接线点被摘掉 ⇒ HTML 侧能开 OO 但 registry 里没有本 pilot 的 adapter，"
            "形成半接线（Task 40 起明令两处都要接）",
        tags=("wiring",),
    ),
    Mutation(
        id="M73", side="be", path=ROUTER, kind="replace",
        anchor="    await attach_g7_pilot_adapters(registry, session=db)",
        new="    pass",
        want=f"{_WIRE}::test_router_calls_the_g7_attach_on_both_paths",
        why="第二个生产接线点（callback 之后的 apply）被摘掉 ⇒ 「OO 改值回写却找不到 adapter」，"
            "同样是半接线",
        tags=("wiring",),
    ),
    Mutation(
        id="M74", side="be", path=PG7, kind="replace",
        anchor="    contract = assert_contract_file_matches_source()",
        new="    contract = load_pilot_contract()",
        want=f"{_WIRE}::test_both_production_paths_go_through_the_contract_lock",
        why="发布路径绕过双向锁 ⇒ 磁盘契约与代码脱钩时也能照发 definition"
            "（Task 40 实测过「守卫自己调锁、从不检查生产路径」会让整组变异判 GREEN）",
        tags=("wiring", "contract-lock"),
        scope="async def publish_pilot_definitions(publisher: Any) -> PilotDefinitions:",
        offset=11,
    ),
]

GUARD_FILES = {
    T43: "Task 43 新建（离线：选型/两级表头/动态列绑定/四边真源/Property 28 漂移/结构操作）",
    T43PG: "Task 43 新建（真库：definitions+bundle 真发布/全场景 run/真实载荷 Property 22）",
}


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            backend_args=[
                "backend/tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py",
                "backend/tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot_pg.py",
                "-q",
                "--tb=no",
                "-rfE",
            ],
            # 239 → 240：收口轮补了
            # `TestProperty22…::test_contract_identity_is_the_imported_constant_never_a_literal`
            # （M31 这条同值变异首轮实测 GREEN 暴露的守卫缺口，见该变异的 why）。
            baseline_backend_passed=240,
        )
    )
