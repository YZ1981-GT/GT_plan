# -*- coding: utf-8 -*-
"""Task 58 守卫变异检验 —— 统一 Word canonical resolver + 模板裁决清册。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 58
Requirements: 7.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.11, 9.12, 12.5
Properties: P39 / P40 / P41 / P42

## 变异分四组（互锁的四个方向）

* **路径层（M01–M09）** —— `canonical_paths`：安全门、CWD 免疫、段名单一真源、
  具体度排序与类型门。验证 P42 与 P40/P41 的底层判据被真正锁住。
* **resolver 层（M10–M25）** —— `word_resolution`：五意图策略、安全门顺序、桥的两条
  限制、失败 kind 的互异性、派生归属。验证「共享错误码让较早分支永久不可达」这一类
  假绿被拦住。
* **调用点（M26–M29）** —— `wp_template_finder` / `wp_onlyoffice_router`：把委派改回
  自写路径 / 自拼分叉路径。验证「旧调用点真的改到了」而不是「新函数存在」。
* **清册（M30–M42）** —— 生成器的分母、裁决派生纯函数、AC 7.7 对账，以及清册 JSON
  本体。验证清册不是可以手改的字符串表。

## 已知坑（本脚本逐条规避）

* `want` 用**短 nodeid**（`file.py::Class::test`，不带目录前缀）；
* pytest 参数传 `-rfE`（`-rf` 收不进 error 态用例名）；
* 锚点一律**单行**（工作树 CRLF，跨行锚点必 ANCHOR-MISS）；
* 替换体保持**语法合法** —— 整行替换让后续行悬空会 collection error，被误判成
  WRONG-TEST 而不是 RED。故条件语句一律用短路式 `if False and <原式>:` 或
  `if False:`（其缩进块本身仍合法）。

## 用法（仓库根）

    py -3 backend/scripts/diagnose/mutate_task58_word_resolver_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task58_word_resolver_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task58_word_resolver_guards.py --run all --out <evidence>/mutation_report.json
    py -3 backend/scripts/diagnose/mutate_task58_word_resolver_guards.py --run M01,M10

只改本 Task 的生产/生成器/清册文件；不写业务库、不发网络请求、不触碰
`backend/wp_templates/`（权威模板只读）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

CP = "backend/app/services/workpaper_sync/canonical_paths.py"
WR = "backend/app/services/workpaper_sync/word_resolution.py"
FINDER = "backend/app/services/wp_template_finder.py"
ROUTER = "backend/app/routers/wp_onlyoffice_router.py"
GEN = "backend/scripts/gen/generate_workpaper_word_template_adjudication.py"
LEDGER = "backend/data/workpaper_word_template_adjudication.json"

U = "test_task58_word_canonical_resolver"

#: 覆盖面分母：本 Task 新建的守卫文件。
GUARD_FILES = {
    f"{U}.py": "Task 58 新建（统一 Word canonical resolver + 模板裁决清册）",
}


def _ledger_row_field_is(wp_code: str, field: str, expected: object):
    """作用域自证：变异确实落在清册**那一行**的那个字段上。

    没有它时，锚点若命中了别处同形态的行，四态判定会报 GREEN（守卫缺陷），
    而真实原因是脚本缺陷 —— 本平台已实测过这个误判。
    """

    def _check(mutated: bytes) -> bool:
        try:
            payload = json.loads(mutated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        for row in payload.get("rows") or []:
            if row.get("wp_code") == wp_code:
                return row.get(field) == expected
        return False

    return _check


MUTATIONS: list[Mutation] = [
    # ═══ 路径层（canonical_paths）═══════════════════════════════════════
    Mutation(
        id="M01", side="be", path=CP, kind="replace",
        anchor="    if not _WP_CODE_FILENAME_RE.match(code):",
        new="    if False and not _WP_CODE_FILENAME_RE.match(code):",
        want=f"{U}.py::TestProperty42PathSafety::test_project_segment_traversal_rejected",
        wants=(
            f"{U}.py::TestProperty42PathSafety::"
            "test_wp_code_segment_traversal_rejected_before_template_lookup",
            f"{U}.py::TestGuardSelfCheck::test_prefix_only_boundary_check_is_fooled_by_traversal",
        ),
        why="短路掉文件名段形态白名单 ⇒ `../../etc` / `..` 直接拼进路径。"
            "不能只删 raise（下方 return 会把非法值原样放行，行为等价但不可读）",
    ),
    Mutation(
        id="M02", side="be", path=CP, kind="replace",
        anchor="    resolve_within_root(root, relative, boundary=boundary)",
        new="    pass  # boundary check removed",
        want=f"{U}.py::TestProperty42PathSafety::test_symlink_escape_rejected",
        wants=(
            f"{U}.py::TestProperty42PathSafety::test_project_segment_traversal_rejected",
        ),
        why="`join_within_root` 把边界判据整条去掉 ⇒ 软链接越界与穿越都放行。"
            "这条专门验证「返回未 realpath 展开的路径」没有顺手把判据也弱化",
    ),
    Mutation(
        id="M03", side="be", path=CP, kind="replace",
        anchor="    return raw if raw.is_absolute() else (BACKEND_ROOT / raw)",
        new="    return raw",
        want=f"{U}.py::TestProperty42PathSafety::test_storage_root_is_cwd_immune",
        why="相对 `STORAGE_ROOT` 不再锚到 BACKEND_ROOT ⇒ 回到 CWD 依赖，"
            "正是 `storage/{pid}/workpapers/` 下 25 份孤儿 docx 的成因",
    ),
    Mutation(
        id="M04", side="be", path=CP, kind="replace",
        anchor="    if document_type not in CANONICAL_SUFFIX_BY_TYPE:",
        new="    if False:",
        want=f"{U}.py::TestProperty42PathSafety::test_extension_spoofing_rejected",
        why="canonical 路径的类型门被短路 ⇒ `document_type='pdf'` 会走到 KeyError "
            "而不是可分辨的 DocumentTypeMismatchError（Requirement 5.12 的定位失效）",
    ),
    Mutation(
        id="M05", side="be", path=CP, kind="replace",
        anchor='ONLYOFFICE_EDITOR_DIRNAME: Final[str] = "onlyoffice"',
        new='ONLYOFFICE_EDITOR_DIRNAME: Final[str] = "oo"',
        want=f"{U}.py::TestProperty42PathSafety::test_absolute_storage_root_is_preserved_verbatim",
        wants=(f"{U}.py::TestGuardSelfCheck::test_canonical_dir_segments_are_declared_once",),
        why="改段名 ⇒ 与存量磁盘上 `.../workpapers/onlyoffice/` 的 140 份产物脱钩。"
            "这条同时验证「段名只在此声明一次」的判据没有退化成 grep",
    ),
    Mutation(
        id="M06", side="be", path=CP, kind="replace",
        anchor='ONLYOFFICE_PROJECTS_DIRNAME: Final[str] = "projects"',
        new='ONLYOFFICE_PROJECTS_DIRNAME: Final[str] = "proj"',
        want=f"{U}.py::TestProperty42PathSafety::test_absolute_storage_root_is_preserved_verbatim",
        why="缺 `projects/` 段正是存量写侧分叉的形态之一（`storage/{pid}/workpapers/`）",
    ),
    Mutation(
        id="M07", side="be", path=CP, kind="replace",
        anchor="        if applicable:",
        new="        if False:",
        want=f"{U}.py::TestProperty41NoCrossTypeFallback::"
             "test_workbook_only_parent_fails_as_type_mismatch_not_missing",
        why="「有异类型候选但无同类型候选」不再报 type mismatch 而落到 missing ⇒ "
            "Requirement 9.4 与 9.5 分不开（两类异常合并是本 spec 已实测 3 次的假绿形态）",
    ),
    Mutation(
        id="M08", side="be", path=CP, kind="replace",
        anchor='    if b.startswith(f"{a}-"):',
        new="    if False:",
        want=f"{U}.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources",
        wants=(f"{U}.py::TestAdjudicationLedger::test_carrier_inventory_and_resolver_agree",),
        why="祖先码不再「适用」⇒ `ancestor_carriers` 全空、清册 digest 变，"
            "且「只有父级 XLSX ⇒ type mismatch」的候选集合被抽空",
    ),
    Mutation(
        id="M09", side="be", path=CP, kind="replace",
        anchor="    typed = [c for c in applicable if c.document_type == expected_document_type]",
        new="    typed = list(applicable)",
        want=f"{U}.py::TestProperty40MostSpecificSubCode::"
             "test_type_filter_precedes_specificity_sort",
        why="类型过滤挪到具体度排序之后 ⇒ `B30-13-1` 的 exact XLSX 先胜出、再被末尾"
            "类型门打回，表现成「明明有父级 DOCX 可用却报类型不符」。"
            "🔴 首轮此条判 GREEN：只测 A16（无 DOCX 可用）时两种顺序抛同一异常类型，"
            "故补了 B30-13-1 这个「有 DOCX 但不是 exact」的真实反例",
    ),
    # ═══ resolver 层（word_resolution）═════════════════════════════════
    Mutation(
        id="M10", side="be", path=WR, kind="replace",
        anchor="        assert_wp_code_segment(wp_code)",
        new="        pass  # security gate moved after template lookup",
        want=f"{U}.py::TestProperty42PathSafety::"
             "test_wp_code_segment_traversal_rejected_before_template_lookup",
        why="把安全门从模板解析**之前**去掉 ⇒ `../B2-1` 先撞 TemplateMissingError，"
            "路径穿越判据落在永久不可达分支（首轮实测正是这个形态）",
    ),
    Mutation(
        id="M11", side="be", path=WR, kind="replace",
        anchor="        if policy.requires_existing_canonical and not exists:",
        new="        if False:",
        want=f"{U}.py::TestFailureKindsDistinctAndReachable::"
             "test_failure_kinds_are_reachable_and_mutually_distinct",
        why="extract 不再要求 canonical 已存在 ⇒ 会拿原始模板顶替，"
            "模板占位符被当成审计师填的值回写 HTML；且该失败 kind 变不可达",
    ),
    Mutation(
        id="M12", side="be", path=WR, kind="replace",
        anchor='    if own_template_carriers(code, document_type="xlsx"):',
        new="    if False:",
        want=f"{U}.py::TestProperty40MostSpecificSubCode::test_own_workbook_blocks_format_flip",
        why="桥的第 2 条限制被短路 ⇒ `S33-1` 从自有工作簿翻成 Word（无授权格式翻转）",
    ),
    Mutation(
        id="M13", side="be", path=WR, kind="replace",
        anchor="    except (TemplateMissingError, DocumentTypeMismatchError) as err:",
        new="    except (TemplateMissingError, DocumentTypeMismatchError, PathBoundaryError) as err:",
        want=f"{U}.py::TestProperty41NoCrossTypeFallback::"
             "test_path_boundary_error_is_not_swallowed_by_bridge",
        why="把安全事件也吞进桥 ⇒ 越界被降级成「本 wp_code 无 Word 载体」，"
            "正是 memory 记的「最贵的一类」fail-open",
    ),
    Mutation(
        id="M14", side="be", path=WR, kind="replace",
        anchor="    WordResolutionIntent.config: WordIntentPolicy(True, False, False),",
        new="    WordResolutionIntent.config: WordIntentPolicy(True, True, False),",
        want=f"{U}.py::TestProperty39SingleWordResolver::test_only_callback_may_write",
        wants=(
            f"{U}.py::TestProperty39SingleWordResolver::"
            "test_read_only_intent_cannot_be_used_to_write",
        ),
        why="给只读意图开写权限 ⇒ config 路径可覆盖 canonical 文件",
    ),
    Mutation(
        id="M15", side="be", path=WR, kind="replace",
        anchor="    WordResolutionIntent.callback: WordIntentPolicy(False, True, False),",
        new="    WordResolutionIntent.callback: WordIntentPolicy(False, False, False),",
        want=f"{U}.py::TestProperty39SingleWordResolver::test_only_callback_may_write",
        why="唯一写侧被取消 ⇒ callback 落盘无授权判据（写权限表退化成空集）",
    ),
    Mutation(
        id="M16", side="be", path=WR, kind="replace",
        anchor="    WordResolutionIntent.extract: WordIntentPolicy(False, False, True),",
        new="    WordResolutionIntent.extract: WordIntentPolicy(False, False, False),",
        want=f"{U}.py::TestProperty39SingleWordResolver::"
             "test_only_extract_requires_existing_canonical",
        why="extract 的「必须已有 canonical」被撤 ⇒ 与 M11 同一后果，但入口在策略表侧；"
            "两处都要各自可被抓到，否则改一处不红",
    ),
    Mutation(
        id="M17", side="be", path=WR, kind="replace",
        anchor="        if not WORD_INTENT_POLICY[resolution.intent].may_write_canonical:",
        new="        if False:",
        want=f"{U}.py::TestProperty39SingleWordResolver::"
             "test_read_only_intent_cannot_be_used_to_write",
        wants=(
            f"{U}.py::TestFailureKindsDistinctAndReachable::"
            "test_failure_kinds_are_reachable_and_mutually_distinct",
        ),
        why="写侧不再校验意图 ⇒ `word_intent_not_permitted` 这个 kind 永久不可达"
            "（假绿第④源：真实数据上分支不可达 = 永久 GREEN）",
    ),
    Mutation(
        id="M18", side="be", path=WR, kind="replace",
        anchor='    r"^([A-Z]+\\d+[A-Z]*(?:-[0-9A-Za-z]+)*)"',
        new='    r"^([A-Z]+\\d+(?:-[0-9A-Za-z]+)*)"',
        want=f"{U}.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources",
        wants=(f"{U}.py::TestAdjudicationLedger::test_carrier_inventory_and_resolver_agree",),
        why="派生正则去掉尾字母段 ⇒ `S12A` 派生成 `S12`，它的自有 DOCX 归属丢失"
            "（`S12A` 正是 18 个 generic 之一）",
    ),
    Mutation(
        id="M19", side="be", path=WR, kind="replace",
        anchor="    return match.group(1) if match else None",
        new='    return match.group(1).split("-")[0] if match else None',
        want=f"{U}.py::TestProperty40MostSpecificSubCode::"
             "test_derived_attribution_beats_prefix_attribution",
        wants=(f"{U}.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources",),
        why="派生只保留主码 ⇒ 所有子码载体都归到父码，最具体匹配退化成父码匹配",
    ),
    Mutation(
        id="M20", side="be", path=WR, kind="replace",
        anchor="        if carrier.wp_code.upper() == target",
        new="        if specificity_rank(carrier.wp_code, target) >= 0",
        want=f"{U}.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources",
        wants=(
            f"{U}.py::TestProperty40MostSpecificSubCode::"
            "test_derived_attribution_beats_prefix_attribution",
        ),
        why="`own_template_carriers` 把祖先也算成「自有」⇒ 清册的 own/ancestor 两列"
            "失去区分度，桥的两条限制条件全部失效",
    ),
    Mutation(
        id="M21", side="be", path=WR, kind="replace",
        anchor='TEMPLATE_INDEX_PATH: Final[Path] = TEMPLATE_ROOT / "_index.json"',
        new='TEMPLATE_INDEX_PATH: Final[Path] = TEMPLATE_ROOT / "_index_v2.json"',
        want=f"{U}.py::TestAdjudicationLedger::test_template_index_path_is_single_source",
        why="模板索引指向另一份文件 ⇒ 与 `wp_template_finder.INDEX_FILE` 形成第二真源",
    ),
    Mutation(
        id="M22", side="be", path=WR, kind="replace",
        anchor='WORD_DOCUMENT_TYPE: Final[str] = "docx"',
        new='WORD_DOCUMENT_TYPE: Final[str] = "xlsx"',
        want=f"{U}.py::TestProperty41NoCrossTypeFallback::test_bridge_never_returns_cross_type_file",
        wants=(
            f"{U}.py::TestProperty40MostSpecificSubCode::"
            "test_registered_b_sub_codes_resolve_own_docx_not_parent_xlsx",
        ),
        why="Word 域的文档类型常量被换成 xlsx ⇒ 整条 Word lane 解析工作簿",
    ),
    Mutation(
        id="M23", side="be", path=WR, kind="replace",
        anchor="    WordCanonicalArtifactAbsentError.error_code,",
        new="    TemplateMissingError.error_code,",
        want=f"{U}.py::TestFailureKindsDistinctAndReachable::"
             "test_failure_kinds_are_reachable_and_mutually_distinct",
        why="失败 kind 登记清单里出现重复 code ⇒ 「实测集合与登记清单双向锁死」失效。"
            "这条专测「收集全部 kind 并断言互不相同」比「每类各测一遍」强",
    ),
    Mutation(
        id="M24", side="be", path=WR, kind="replace",
        anchor='    error_code = "word_canonical_artifact_absent"',
        new='    error_code = "template_missing"',
        want=f"{U}.py::TestFailureKindsDistinctAndReachable::"
             "test_failure_kinds_are_reachable_and_mutually_distinct",
        why="把「canonical 缺失」与「模板缺失」合并成同一 error_code ⇒ 前者永久被后者"
            "遮蔽，只断言类型/单条的守卫会判 GREEN",
    ),
    Mutation(
        id="M25", side="be", path=WR, kind="replace",
        anchor="    own_docx = own_template_carriers(code, document_type=WORD_DOCUMENT_TYPE)",
        new="    own_docx = list(collect_template_carriers(code))",
        want=f"{U}.py::TestProperty40MostSpecificSubCode::test_bridge_rejects_ancestor_only_docx",
        why="桥的第 1 条限制（只认 exact-own）被放开 ⇒ 祖先 DOCX 顶替自有载体，具体度倒转。"
            "🔴 首轮此条判 GREEN：真实模板库里「无自有工作簿 + 无自有 DOCX + 有祖先 "
            "DOCX」的 wp_code 实测为 0（1539 个全扫），该限制与前一道 own-xlsx 门在"
            "真实数据上冗余 ⇒ 补了合成模板根的用例让它可达",
    ),
    # ═══ 调用点（finder / router）══════════════════════════════════════
    Mutation(
        id="M26", side="be", path=FINDER, kind="replace",
        anchor="    most_specific_docx = _resolve_most_specific_docx(wp_code)",
        new="    most_specific_docx = None",
        want=f"{U}.py::TestProperty40MostSpecificSubCode::"
             "test_legacy_finder_now_returns_own_docx_for_affected_codes",
        wants=(f"{U}.py::TestGuardSelfCheck::test_resolver_is_not_dead_code",),
        why="🔴 存量入口不再委派统一 resolver ⇒ 9 个 B 子码回到抢父级 XLSX。"
            "这条专测「旧调用点真的改到了」——只测新 resolver 的守卫在此处会全绿"
            "（假绿第①源：additive 注入即死代码）",
    ),
    Mutation(
        id="M27", side="be", path=FINDER, kind="replace",
        anchor='_LEGACY_A_ONLY_SUB_CODE_RE = re.compile(r"^A\\d+-\\d+")',
        new='_LEGACY_A_ONLY_SUB_CODE_RE = re.compile(r"^[A-Z]+\\d+-\\d+")',
        want=f"{U}.py::TestGuardSelfCheck::test_a_only_regex_would_miss_b_sub_codes",
        why="把存量 A-only 正则改成字母类无关 ⇒ 「9 个受影响码确实不被 A-only 命中」"
            "这条缺陷证据失效；同时 D2-2 之类会落进 A 分支（正是不能这么改的原因）",
    ),
    Mutation(
        id="M28", side="be", path=FINDER, kind="replace",
        anchor="    return resolve_own_docx_or_none(wp_code)",
        new="    return None",
        want=f"{U}.py::TestGuardSelfCheck::test_resolver_is_not_dead_code",
        wants=(
            f"{U}.py::TestProperty40MostSpecificSubCode::"
            "test_legacy_finder_now_returns_own_docx_for_affected_codes",
        ),
        why="委派函数内部改成恒 None —— 与 M26 是两个不同位置（调用点 vs 委派体），"
            "两处都要各自可被抓到",
    ),
    Mutation(
        id="M29", side="be", path=ROUTER, kind="replace",
        anchor="    return onlyoffice_canonical_dir(project_id)",
        new='    return Path(settings.STORAGE_ROOT) / "projects" / str(project_id) / "workpapers" / "onlyoffice"',
        want=f"{U}.py::TestProperty39SingleWordResolver::"
             "test_router_read_side_delegates_to_canonical_paths",
        wants=(f"{U}.py::TestGuardSelfCheck::test_canonical_dir_segments_are_declared_once",),
        why="读侧回到自拼段名 ⇒ 与写侧再次形成两份路径拼装（Requirement 9.3 的分叉源）",
    ),
    Mutation(
        id="M30", side="be", path=ROUTER, kind="replace",
        anchor="            target = word_canonical_write_target(project_id, _save_wp_code or wp_code)",
        new='            target = Path(f"storage/{project_id}/workpapers/{wp_code}.docx")',
        want=f"{U}.py::TestProperty39SingleWordResolver::"
             "test_router_callback_no_longer_hardcodes_divergent_word_path",
        why="🔴 把存量分叉写法原样放回 ⇒ 159 份孤儿 docx 的成因复现。"
            "这是 Requirement 9.3 / Property 39 最直接的反例",
    ),
    # ═══ 清册（生成器 + JSON）══════════════════════════════════════════
    Mutation(
        id="M31", side="be", path=GEN, kind="replace",
        anchor="        if overrides[code] == WORD_COMPONENT_TYPE:",
        new="        if False:",
        want=f"{U}.py::TestAdjudicationLedger::"
             "test_denominator_comes_from_sources_not_a_hand_written_list",
        wants=(f"{U}.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources",),
        why="generic 分母整段消失 ⇒ 「18 个」无从计数。分母不可由生成器悄悄收缩",
    ),
    Mutation(
        id="M32", side="be", path=GEN, kind="replace",
        anchor="            if code.upper().startswith(prefix) and overrides[code] != WORD_COMPONENT_TYPE:",
        new="            if False:",
        want=f"{U}.py::TestAdjudicationLedger::"
             "test_denominator_comes_from_sources_not_a_hand_written_list",
        wants=(f"{U}.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources",),
        why="A16/A17 专用链整段不进清册 ⇒ Requirement 7.7 点名的第 4 类被漏掉。"
            "🔴 首轮此条判 WRONG-TEST：分母用例原先只比落盘 JSON（静态），生成器分支被"
            "短路后它仍全绿，只有 digest 用例红 ⇒ 已改成同时比对生成器现算的分母",
    ),
    Mutation(
        id="M33", side="be", path=GEN, kind="replace",
        anchor='    if unified == "template_missing":',
        new="    if False:",
        want=f"{U}.py::TestAdjudicationLedger::test_adjudication_derivation_is_a_total_function",
        why="「无载体」不再优先于 chain 分支 ⇒ 专用链上的缺失行会被记成「只有工作簿」，"
            "Task 63 / 64 的责任归属当场错位",
    ),
    Mutation(
        id="M34", side="be", path=GEN, kind="replace",
        anchor='    if ledger_class.startswith("dedicated_chain"):',
        new="    if False:",
        want=f"{U}.py::TestAdjudicationLedger::test_adjudication_derivation_is_a_total_function",
        wants=(f"{U}.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources",),
        why="专用链分支消失 ⇒ A16-1~7 等被当 generic 计入「18」，与 AC 7.7 对账崩",
    ),
    Mutation(
        id="M35", side="be", path=GEN, kind="replace",
        anchor='        if unified == "resolved_docx" and own_docx > 0:',
        new='        if unified == "resolved_docx":',
        want=f"{U}.py::TestAdjudicationLedger::test_adjudication_derivation_is_a_total_function",
        why="`own_docx > 0` 这个合取项被删 ⇒ 只解析到**祖先** DOCX 的链上行也被记成"
            "「子码有自有 DOCX」，裁决说谎",
    ),
    Mutation(
        id="M36", side="be", path=GEN, kind="replace",
        anchor='    if unified != "resolved_docx":',
        new="    if False:",
        want=f"{U}.py::TestAdjudicationLedger::test_adjudication_derivation_is_a_total_function",
        why="generic 入口「解析不到 DOCX」不再归 missing ⇒ 会被记成"
            "`generic_docx_direct`（把失败记成成功，最危险的一类裁决错）",
    ),
    Mutation(
        id="M37", side="be", path=GEN, kind="replace",
        anchor='    if affected_by_legacy_a_only_defect and legacy == "parent_workbook":',
        new='    if legacy == "parent_workbook":',
        want=f"{U}.py::TestAdjudicationLedger::test_adjudication_derivation_is_a_total_function",
        wants=(f"{U}.py::TestAdjudicationLedger::test_ledger_counts_match_requirement_7_7",),
        why="去掉「受 A-only 缺陷影响」这个前提 ⇒ A 子码（`A8-2` 等）也被算进"
            "「9 个误解析」，18/9 的对账崩",
    ),
    Mutation(
        id="M38", side="be", path=GEN, kind="replace",
        anchor='    return "generic_docx_direct"',
        new='    return "unadjudicated_placeholder"',
        want=f"{U}.py::TestAdjudicationLedger::"
             "test_every_row_has_a_registered_adjudication_and_owner",
        wants=(f"{U}.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources",),
        why="兜底裁决返回未登记取值 ⇒ 「逐行都有已登记裁决」这条判据必须打红，"
            "而不是默默进清册",
    ),
    Mutation(
        id="M39", side="be", path=GEN, kind="replace",
        anchor='    "subcode_docx_recovered",',
        new='    "subcode_docx_recovered_renamed",',
        want=f"{U}.py::TestAdjudicationLedger::"
             "test_every_row_has_a_registered_adjudication_and_owner",
        wants=(f"{U}.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources",),
        why="裁决取值域与派生结果脱钩 ⇒ 9 行变「未裁决」。取值域与派生必须双向锁死",
    ),
    Mutation(
        id="M40", side="be", path=GEN, kind="replace",
        anchor='    r"7\\.7\\.\\s*(?P<generic>\\d+)\\s*个可正确解析\\s*DOCX、(?P<subcode>\\d+)\\s*个误解析为父级"',
        new='    r"7\\.7\\.\\s*(?P<generic>\\d)\\s*个可正确解析\\s*DOCX、(?P<subcode>\\d+)\\s*个误解析为父级"',
        want=f"{U}.py::TestAdjudicationLedger::test_ledger_counts_match_requirement_7_7",
        why="AC 7.7 的对账正则只吃一位数 ⇒ `18` 被读成 `1`，与需求原文的双向锁死失效",
    ),
    Mutation(
        id="M41", side="be", path=GEN, kind="replace",
        anchor='        "declared_generic_docx": int(match.group("generic")),',
        new='        "declared_generic_docx": 17,',
        want=f"{U}.py::TestAdjudicationLedger::test_ledger_counts_match_requirement_7_7",
        why="把从需求原文抠出的数字改成硬编码常量 ⇒ 对账退化成自证同义反复"
            "（期望值绝不能由被测侧提供）",
    ),
    Mutation(
        id="M42", side="be", path=LEDGER, kind="replace",
        anchor='      "unified_verdict": "template_missing",',
        new='      "unified_verdict": "resolved_docx",',
        want=f"{U}.py::TestAdjudicationLedger::test_carrier_inventory_and_resolver_agree",
        wants=(
            f"{U}.py::TestAdjudicationLedger::test_ledger_is_in_sync_with_sources",
            f"{U}.py::TestProperty41NoCrossTypeFallback::"
            "test_s33_rev_has_no_carrier_and_fails_as_template_missing",
        ),
        why="手改清册 JSON 里 S33-REV 的 verdict ⇒ 验证守卫是按 wp_code **真跑一次**"
            "resolver 再比对，而不是读 JSON 字符串（假绿第②源在清册守卫上最危险）",
        scope_check=_ledger_row_field_is("S33-REV", "unified_verdict", "resolved_docx"),
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 58 统一 Word canonical resolver + 模板裁决清册守卫变异检验",
            backend_args=[
                f"backend/tests/workpaper_sync/{U}.py",
                "-q",
                "--tb=no",
                "-rfE",
            ],
            # 冻结基线：47 passed（2026-08-29 实测）。首轮 45 passed 时 M09/M25/M32
            # 三条非 RED，补了两条判据（类型过滤顺序、桥拒祖先-only DOCX）并把分母
            # 用例改成同时比对生成器现算值，故基线由 45 升到 47。
            baseline_backend_passed=47,
        )
    )
