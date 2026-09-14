"""Task 63 守卫变异检验 —— 9 个 B 子码错型 + `S33-REV` 的裁决、载体三值与假切换移除。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 63
Requirements: 7.7, 9.4, 9.5, 12.5, 12.8, 12.10, 12.11, 12.12
Properties: P40 / P41 / P69 / P70

## 变异分四组

* **载体三值（M01–M04）** —— `word_resolution.WordCarrierVerdict` /
  `word_carrier_verdict`：安全门顺序、三值封闭、`has_usable_docx_carrier` 的保守写法。
  M01 是**真实缺陷的回归锚**：本函数首版漏了 `assert_wp_code_segment`，`../B2-1` 被吞成
  `template_missing`，由守卫打红后才补上。
* **render 下发（M05–M06）** —— `_word_template.py`：两种「拿不到」必须可区分；三个
  失败分支都真的改到了。
* **假切换（M07–M12）** —— 宿主门控三要素、判据来源（不得按 wp_code 字面量）、popup
  配置条目与 templatePath 磁盘实存。fe 侧变异验证门控在**真实 DOM** 上生效。
* **裁决记录（M13–M17）** —— 可复算、不越 Task 61 的门、阻塞项 open、载体线索待确认，
  以及守卫自己的剥注释器。

## 已知坑（本脚本逐条规避）

* 锚点一律**单行**（工作树 CRLF，跨行锚点必 ANCHOR-MISS）；
* `    assert_wp_code_segment(wp_code)` 在 `word_resolution.py` 出现两次，靠**缩进**
  区分（模块级函数 4 空格 / 类方法 8 空格）—— 不靠行号；
* `        return _carrier_absence_payload(wp_code)` 出现 3 次，用 `scope`+`offset`
  相对定位到「路径为空」那一处；
* 替换体保持语法合法（`if False:` / `v-if="false"`），避免 collection error 被误判成
  WRONG-TEST；
* 改 JSON 的变异带 `scope_check`，自证改动落在目标结构内。

## 用法（仓库根）

    py backend/scripts/diagnose/mutate_task63_subcode_guards.py --list
    py backend/scripts/diagnose/mutate_task63_subcode_guards.py --check-anchors
    py backend/scripts/diagnose/mutate_task63_subcode_guards.py --run all
    py backend/scripts/diagnose/mutate_task63_subcode_guards.py --run M01,M07

只改本 Task 的生产/守卫/记录文件；**不触碰 `backend/wp_templates/`**（权威模板只读），
不写业务库、不发网络请求。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

WR = "backend/app/services/workpaper_sync/word_resolution.py"
RENDER = "backend/app/routers/wp_render_strategies/_word_template.py"
EDITOR = "audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue"
POPUP_S = "audit-platform/frontend/src/components/workpaper/wpPopupDocxConfigsS.ts"
RECORD = "backend/data/workpaper_sync_task63_subcode_adjudication.json"
GUARD_BE = "backend/tests/workpaper_sync/test_task63_subcode_adjudication.py"
GEN = "backend/scripts/gen/generate_workpaper_task63_subcode_adjudication.py"

U = "test_task63_subcode_adjudication"
FE_SPEC = "task63WordCarrierGate.spec.ts"

GUARD_FILES = {
    f"{U}.py": "Task 63 新建（载体三值 / render 下发 / 假切换移除 / 裁决记录）",
    FE_SPEC: "Task 63 新建（无载体底稿编辑入口门控的真实 DOM 判据）",
}

BE_ARGS = [
    "backend/tests/workpaper_sync/test_task63_subcode_adjudication.py",
    "-q",
    "-rfE",
    "--no-header",
]
FE_DIR = REPO / "audit-platform" / "frontend"
FE_FILTERS = [f"src/components/workpaper/__tests__/{FE_SPEC}"]
VITEST_JSON = REPO / "tmp_t63_mutation_vitest.json"


def _record_entry_field_is(wp_code: str, field: str, expected: object):
    """作用域自证：变异确实落在裁决记录**那个 entry** 的那个字段上。"""

    def _check(mutated: bytes) -> bool:
        try:
            payload = json.loads(mutated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        for e in payload.get("entries") or []:
            if e.get("wp_code") == wp_code:
                return e.get(field) == expected
        return False

    return _check


def _record_stat_is(field: str, expected: object):
    def _check(mutated: bytes) -> bool:
        try:
            payload = json.loads(mutated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return (payload.get("stats") or {}).get(field) == expected

    return _check


def _record_bp_measured_is(bp_id: str, field: str, expected: object):
    """作用域自证：变异落在**那条 BP** 的 `measured` 里的那个字段上。

    必需：`true` / `0` 这类值在整份记录里到处都是，只看「文件里出现了 false」
    无法证明改的是 BP-18 的判据而不是别处的同名布尔。
    """

    def _check(mutated: bytes) -> bool:
        try:
            payload = json.loads(mutated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        for bp in payload.get("blocking_preconditions") or []:
            if bp.get("id") == bp_id:
                return (bp.get("measured") or {}).get(field) == expected
        return False

    return _check


def _record_bp_what_contains(bp_id: str, needle: str):
    def _check(mutated: bytes) -> bool:
        try:
            payload = json.loads(mutated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        for bp in payload.get("blocking_preconditions") or []:
            if bp.get("id") == bp_id:
                return needle in (bp.get("what") or "")
        return False

    return _check


def _record_source_paths_exclude(path: str):
    """作用域自证：`sources` 块里已不再登记该路径（只看 sources，不看全文）。"""

    def _check(mutated: bytes) -> bool:
        try:
            payload = json.loads(mutated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        paths = {v.get("path") for v in (payload.get("sources") or {}).values()}
        return path not in paths

    return _check


def _record_reverification_verdict_is(bp_id: str, expected: object):
    def _check(mutated: bytes) -> bool:
        try:
            payload = json.loads(mutated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        verdicts = (payload.get("residency_reverification") or {}).get("verdicts") or {}
        return verdicts.get(bp_id) == expected

    return _check


MUTATIONS: list[Mutation] = [
    # ═══ 载体三值 ═══════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=WR, kind="replace",
        anchor="    assert_wp_code_segment(wp_code)",
        new="    pass  # boundary gate removed",
        want=f"{U}.py::TestWordCarrierVerdict::test_path_boundary_is_not_swallowed_into_a_verdict",
        wants=(
            f"{U}.py::TestCarrierAbsencePayload::test_boundary_violation_returns_none_and_logs_error",
        ),
        why="把 word_carrier_verdict 的安全门去掉 ⇒ `../B2-1` 先撞 TemplateMissingError，"
            "路径穿越被吞成 verdict `template_missing`，宿主当「本底稿没模板」正常显示。"
            "这正是本函数首版的真实缺陷（4 空格缩进那处唯一，类方法里是 8 空格）",
        tags=("carrier_verdict", "security"),
    ),
    Mutation(
        id="M02", side="be", path=WR, kind="replace",
        anchor="        return self is WordCarrierVerdict.resolved_docx",
        new="        return self is not WordCarrierVerdict.template_missing",
        want=f"{U}.py::TestWordCarrierVerdict::test_only_resolved_docx_is_usable",
        why="把 has_usable_docx_carrier 从白名单式改成黑名单式 ⇒ "
            "document_type_mismatch（只有 xlsx 载体）被当成可 Word 编辑，"
            "且未来新增第四个 verdict 会默认放行",
        tags=("carrier_verdict",),
    ),
    Mutation(
        id="M03", side="be", path=WR, kind="insert",
        anchor='    template_missing = "template_missing"',
        new='    resolved_by_alias = "resolved_by_alias"',
        want=f"{U}.py::TestWordCarrierVerdict::test_verdict_domain_is_closed_and_matches_ledger_domain",
        why="给 verdict 加第四个值而清册取值域未变 ⇒ 「同名同域」被破坏。"
            "若守卫写成「包含」而不是「相等」，这条会 GREEN",
        tags=("carrier_verdict",),
    ),
    Mutation(
        id="M04", side="be", path=WR, kind="replace",
        anchor="        return WordCarrierVerdict.template_missing",
        new="        return WordCarrierVerdict.document_type_mismatch",
        want=f"{U}.py::TestWordCarrierVerdict::test_verdict_matches_ledger_row_by_row",
        wants=(
            f"{U}.py::TestWordCarrierVerdict::test_s33rev_is_template_missing_and_b_subcodes_are_resolved",
        ),
        why="把「零载体」误报成「只有异类型载体」⇒ S33-REV 的 verdict 与清册登记不符。"
            "验证守卫是按 wp_code **逐行现算比对**而不是只测一个样本。"
            "首版这条写的是合并两个 except 分支，但 TemplateMissingError 已被前一分支捕获 ⇒ "
            "行为不变 ⇒ 判 GREEN，实为**无效变异**（变异声明缺陷，不是守卫缺陷）",
        tags=("carrier_verdict",),
    ),
    # ═══ render 下发 ════════════════════════════════════════════════════
    Mutation(
        id="M05", side="be", path=RENDER, kind="replace",
        anchor="    if verdict.has_usable_docx_carrier:",
        new="    if False:",
        want=f"{U}.py::TestCarrierAbsencePayload::test_usable_carrier_keeps_returning_none",
        why="去掉「有载体则让 None 冒泡」的早退 ⇒ 一次磁盘/权限故障被永久呈现为"
            "「此底稿无模板」，可修的故障变成不可修的裁决",
        tags=("render",),
    ),
    Mutation(
        id="M06", side="be", path=RENDER, kind="replace",
        scope='        logger.debug("word-template 模板文件路径为空, wp_code=%s, wp_id=%s", wp_code, wp_id)',
        offset=1,
        anchor="        return _carrier_absence_payload(wp_code)",
        new="        return None",
        want=f"{U}.py::TestCarrierAbsencePayload::test_render_strategy_routes_all_three_failure_points",
        why="把「模板路径为空」这一处改回裸 return None ⇒ 零载体底稿又拿不到裁决。"
            "该行文本在 render() 内出现 3 次，靠 scope+offset 相对定位",
        tags=("render",),
    ),
    # ═══ 假切换：宿主门控 ═══════════════════════════════════════════════
    Mutation(
        id="M07", side="be", path=EDITOR, kind="replace",
        anchor="  () => props.htmlData?.word_carrier?.has_usable_carrier === false,",
        new="  () => !props.htmlData?.word_carrier?.has_usable_carrier,",
        want=f"{U}.py::TestFakeSwitchRemoved::test_word_editor_gates_all_three_edit_entrypoints",
        why="把显式 `=== false` 改成取反 ⇒ 字段缺失（老 render 路径 / A16 bundle 内嵌）"
            "也被判无载体，28 个 word-template 底稿的编辑入口会被全部藏掉",
        tags=("fake_switch", "gate"),
    ),
    Mutation(
        id="M08", side="fe", path=EDITOR, kind="replace",
        anchor="  () => props.htmlData?.word_carrier?.has_usable_carrier === false,",
        new="  () => !props.htmlData?.word_carrier?.has_usable_carrier,",
        want="htmlData 未提供 word_carrier",
        wants=("word_carrier 存在但 has_usable_carrier 缺失",),
        why="同 M07，但在真实 DOM 上验证：字段缺失时切换器必须仍然渲染。"
            "只有 fe 侧能证明门控真的挂在 DOM 上而不只是源码里有那几个字符串",
        tags=("fake_switch", "gate"),
    ),
    Mutation(
        id="M09", side="be", path=EDITOR, kind="replace",
        anchor="  () => props.htmlData?.word_carrier?.has_usable_carrier === false,",
        new="  () => wpCode.value === 'S33-REV',",
        want=f"{U}.py::TestFakeSwitchRemoved::test_word_editor_has_no_wp_code_literal_gate",
        wants=(
            f"{U}.py::TestFakeSwitchRemoved::test_word_editor_gates_all_three_edit_entrypoints",
        ),
        why="把裁决权从后端搬进组件（按 wp_code 字面量判）⇒ 下一个零载体 wp_code 出现时"
            "静默失效，且「有没有载体」这个磁盘事实由无从得知的组件回答",
        tags=("fake_switch", "hardcode"),
    ),
    Mutation(
        id="M10", side="fe", path=EDITOR, kind="replace",
        anchor='        <div v-if="hasNoUsableCarrier" class="gt-wp-word-editor__no-carrier">',
        new='        <div v-if="false" class="gt-wp-word-editor__no-carrier">',
        want="不渲染双模式切换器",
        why="缺失说明块的 v-if 恒假 ⇒ 它的 v-else（双模式切换器）反而对零载体底稿渲染出来，"
            "假切换回归。这条只能由 DOM 判据抓到",
        tags=("fake_switch", "dom"),
    ),
    Mutation(
        id="M11", side="fe", path=EDITOR, kind="replace",
        anchor="  if (!isA16Mode.value && !hasNoUsableCarrier.value) {",
        new="  if (!isA16Mode.value) {",
        # 🔴 2026-09-04 修：本条曾判 WRONG-TEST，**不是守卫缺陷也不是行为回归** ——
        #    变异确实把该门的那条测试打红了（8/9 passed，红的正是它），但 `want` 里
        #    写的是一个**已不存在的测试标题**（旧名 "不发起 template-structure /
        #    onlyoffice-config 请求"）。前端 spec 在 2026-09-01 被改名成
        #    "不发起结构化取数与 onlyoffice-config 请求"，`want` 随之过期。
        #    教训：fe 侧 `want` 是**测试标题子串**，标题一改就悄悄失配，而四态里
        #    WRONG-TEST 长得很像「污染残留」，容易被误判成守卫问题去改生产代码。
        want="不发起结构化取数与 onlyoffice-config 请求",
        why="onMounted 的门控去掉 ⇒ 零载体底稿仍发两个注定失败的请求，"
            "失败又被降级成误导文案",
        tags=("fake_switch", "dom"),
    ),
    Mutation(
        id="M12", side="be", path=EDITOR, kind="replace",
        anchor="  if (hasNoUsableCarrier.value) return",
        new="  if (false) return",
        want=f"{U}.py::TestFakeSwitchRemoved::test_word_editor_gates_all_three_edit_entrypoints",
        why="去掉 initGenericEditor 的第二道结构门 ⇒ UI 外的调用路径（watch / 外部调用）"
            "仍能对零载体底稿拉起 OO",
        tags=("fake_switch",),
    ),
    # ═══ 假切换：popup 配置 ═════════════════════════════════════════════
    Mutation(
        id="M13", side="be", path=POPUP_S, kind="insert",
        anchor="export const S_DOCX_POPUP_CONFIGS: Record<string, DocxPopupConfig> = {",
        new=(
            "  'S33-REV': {\n"
            "    title: '综合核查程序修订说明',\n"
            "    guidance: [],\n"
            "    applicableNote: 'x',\n"
            "    templatePath: 'wp_templates/S/S33 程序修订说明.docx',\n"
            "    relatedLinks: [],\n"
            "  },"
        ),
        want=f"{U}.py::TestFakeSwitchRemoved::test_s33rev_has_no_popup_docx_config_entry",
        wants=(
            f"{U}.py::TestFakeSwitchRemoved::test_every_popup_template_path_exists_on_disk",
        ),
        why="把 S33-REV 的假切换加回来（含原来那个磁盘不存在的 templatePath）⇒ "
            "两个动作对零载体必然失败。同时验证「剥注释后判条目」的判据真的在工作 —— "
            "该文件注释里逐字写着 'S33-REV'，裸 grep 判据在变异前后都会说「还在」",
        tags=("fake_switch", "popup"),
    ),
    Mutation(
        id="M14", side="be", path=POPUP_S, kind="replace",
        anchor="    templatePath: 'wp_templates/S/S12A 评估专家工作报告（或评估专家工作总结）.docx',",
        new="    templatePath: 'wp_templates/S/S12A 评估专家报告.docx',",
        want=f"{U}.py::TestFakeSwitchRemoved::test_every_popup_template_path_exists_on_disk",
        why="把 S12A 的 templatePath 改回勘查前的错值 ⇒ 「下载模板」拿它取文件名，"
            "审计师下到的文件名与真实模板不符",
        tags=("popup",),
    ),
    # ═══ 裁决记录 ═══════════════════════════════════════════════════════
    Mutation(
        id="M15", side="be", path=RECORD, kind="replace",
        anchor='      "verification_state": "ADJUDICATED_MISSING",',
        new='      "verification_state": "UNVERIFIABLE",',
        want=f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_missing_entry_is_adjudicated_not_blocked",
        ),
        why="手改裁决记录，把「已裁决缺失」伪装成「待验证」⇒ S33-REV 会被当成还在等 "
            "Task 61 的 entry。验证记录不是可手改的字符串表（--check 必须打红）",
        scope_check=_record_entry_field_is("S33-REV", "verification_state", "UNVERIFIABLE"),
        tags=("record",),
    ),
    Mutation(
        id="M16", side="be", path=RECORD, kind="replace",
        anchor='    "published_artifacts": 0,',
        new='    "published_artifacts": 3,',
        want=f"{U}.py::TestAdjudicationRecord::test_no_publication_happened",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        ),
        why="宣称本轮发布了 3 个 artifact ⇒ 越过 Task 61 的门。"
            "这条是「不为满足数字伪造 contract/bundle/finalize」的机器判据",
        scope_check=_record_stat_is("published_artifacts", 3),
        tags=("record", "gate"),
    ),
    Mutation(
        id="M17", side="be", path=RECORD, kind="replace",
        anchor='      "id": "BP-18",',
        new='      "id": "BP-99",',
        want=f"{U}.py::TestAdjudicationRecord::test_blocking_preconditions_are_open",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
            f"{U}.py::TestAdjudicationRecord::test_pending_entries_are_unverifiable_and_blocked",
        ),
        why="把 adapter 禁令那条阻塞项改成不存在的编号 ⇒ 「为什么 9 个 entry 没启用」"
            "失去追溯锚点，且 entry 的 blocked_by 指向一个查不到的 id",
        tags=("record",),
    ),
    Mutation(
        id="M18", side="be", path=RECORD, kind="replace",
        anchor='    "resolution": "pending_business_confirmation",',
        new='    "resolution": "applied_renamed_template",',
        want=f"{U}.py::TestAdjudicationRecord::test_s33rev_hint_is_pending_not_silently_applied",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        ),
        why="宣称已自行落实改名方案 ⇒ 改了运行时权威模板库却无业务确认。"
            "载体线索必须停在「待确认」",
        tags=("record",),
    ),
    # ═══ 字段身份基础与二义裁决（BP-20 / BP-19）═════════════════════════
    Mutation(
        id="M20", side="be", path=GEN, kind="replace",
        anchor='        "field_identity_admissible": dollar_count > 0,',
        new='        "field_identity_admissible": dollar_count >= 0,',
        # 改生成器时磁盘 record 不动，故真正命中的是 `--check` 那条（现算 ≠ 磁盘）；
        # 下面那条要等有人重跑生成器才会红，作为二级说明保留。
        want=f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_no_b_subcode_has_admissible_field_identity",
        ),
        why="把字段身份放行判据改成恒真 ⇒ 9 个 B 子码立刻「够条件」发布 11 个名为 "
            "placeholder_generic_N 的字段：数字达标而审计师无从知道每个字段该填什么。"
            "这正是 Task 63 明禁的「为满足数字伪造 contract」",
        tags=("field_basis", "bp20"),
    ),
    Mutation(
        id="M21", side="be", path=GEN, kind="replace",
        anchor='            "id": "BP-20",',
        new='            "id": "BP-20-DRAFT",',
        want=f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_blocking_preconditions_are_open",
            f"{U}.py::TestAdjudicationRecord::test_bp20_gives_resolution_paths_not_a_workaround",
        ),
        why="把「字段身份基础不合法」这条阻塞项改成查不到的编号 ⇒ 9 个 entry 的 "
            "blocked_by 指向不存在的 id，「为什么没发契约」失去追溯锚点",
        tags=("bp20",),
    ),
    Mutation(
        id="M22", side="be", path=GEN, kind="replace",
        # 该行在 `_carrier_ambiguity_adjudication` 的 options 里出现两次（OPT-SPLIT /
        # OPT-PRIMARY），缩进 20 空格；用 OPT-SPLIT 的 id 行做 scope 相对定位。
        scope='                    "id": "OPT-SPLIT",',
        offset=7,
        anchor='                    "recommended": None,',
        new='                    "recommended": True,',
        want=f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        wants=(
            f"{U}.py::TestAdjudicationRecord::"
            "test_carrier_ambiguity_adjudication_covers_every_ambiguous_entry",
        ),
        why="替业务选定 B2-3 的处置方案 ⇒ 「哪一封是底稿正本」这个业务判断被脚本代劳。"
            "两个方案都会新增 wp_code 或让一封载体永久离线，不能自行拍定",
        tags=("bp19", "ambiguity"),
    ),
    Mutation(
        id="M23", side="be", path=RECORD, kind="replace",
        scope='    "zero_structured_field_entries": [',
        offset=2,
        anchor='      "B40-2"',
        new='      "B40-9"',
        want=f"{U}.py::TestAdjudicationRecord::test_zero_structured_field_entries_are_registered",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        ),
        why="把「结构化岛为空集」的 entry 清单改掉一个 ⇒ B40-2 的空字段事实被抹掉。"
            "空字段集的契约是空转（同 Task 77 拒绝的「空集上 equivalent=True」），"
            "这个清单是它的唯一登记处",
        scope_check=_record_stat_is("zero_structured_field_entries", ["B40-1", "B40-9"]),
        tags=("field_basis",),
    ),
    Mutation(
        id="M19", side="be", path=GUARD_BE, kind="replace",
        anchor='    text = re.sub(r"/\\*.*?\\*/", "", text, flags=re.DOTALL)',
        new='    text = re.sub(r"/\\*.*?\\*/", "", text)',
        want=f"{U}.py::TestGuardSelfCheck::test_comment_stripper_really_strips",
        wants=(
            f"{U}.py::TestGuardSelfCheck::test_s33rev_appears_in_comments_so_naive_grep_would_be_fooled",
            f"{U}.py::TestFakeSwitchRemoved::test_s33rev_has_no_popup_docx_config_entry",
        ),
        why="把守卫自己的剥注释器改坏（漏 DOTALL ⇒ 跨行块注释剥不掉）⇒ 依赖它的"
            "「S33-REV 不在配置里」判据会把注释里的字样当成配置条目。"
            "反向自检必须打红，否则这个剥注释器就是不可信的",
        tags=("guard_self_check",),
    ),
    # ═══ 驻留重验判据（M24–M29，2026-09-04 新增）════════════════════════
    #
    # 这一组钉住的是**本轮新加的 `measured` 判据本身**。没有它们，`measured` 就是
    # additive 死代码：下一轮读到 `b_subcodes_with_own_entry_count: 0` 无从判断那是
    # 刚算的还是几个月前烧进去的常量（假绿第①源）。
    Mutation(
        id="M24", side="be", path=RECORD, kind="replace",
        anchor='      "BP-20": "still_open"',
        new='      "BP-20": "cleared"',
        want=f"{U}.py::TestResidencyReverification::"
             "test_verdicts_cover_every_blocking_precondition_that_blocks_this_lane",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        ),
        why="只改重验结论那一行字宣称 BP-20 已解除，而 BP-20 的 status 仍是 open、"
            "9 个 entry 仍是 UNVERIFIABLE ⇒ 「阻塞解除」变成一句可以单独改的话。"
            "字段身份基础的解除是业务输入（引入 ${token} 或逐份裁定 ××），"
            "不可能只由记录里一行字达成",
        scope_check=_record_reverification_verdict_is("BP-20", "cleared"),
        tags=("reverification", "gate"),
    ),
    Mutation(
        id="M25", side="be", path=RECORD, kind="replace",
        anchor='        "b_subcodes_with_own_entry_count": 0,',
        new='        "b_subcodes_with_own_entry_count": 1,',
        want=f"{U}.py::TestResidencyReverification::"
             "test_bp16_manifest_criterion_is_recomputed_from_the_manifest",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        ),
        why="谎报「已有 1 个 B 子码拿到自己的 manifest entry」⇒ BP-16 看起来快解除了。"
            "守卫必须重新扫一遍 manifest 而不是采信这个数，否则这条判据只是个常量",
        scope_check=_record_bp_measured_is("BP-16", "b_subcodes_with_own_entry_count", 1),
        tags=("reverification", "bp16"),
    ),
    Mutation(
        id="M26", side="be", path=RECORD, kind="replace",
        anchor='        "real_target_is_listed": true,',
        new='        "real_target_is_listed": false,',
        want=f"{U}.py::TestResidencyReverification::"
             "test_bp18_forbiddance_names_the_real_target_not_just_a_nonempty_list",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        ),
        why="把「禁令清单逐字包含 adapters/word.py」这条事实改成 false ⇒ 记录不再声称"
            "真实目标在禁令里。这正是 Task 64 M13 的教训：只断言「清单非空 + 逐项不存在」"
            "会被改名绕过，必须断言包含那个真实路径",
        scope_check=_record_bp_measured_is("BP-18", "real_target_is_listed", False),
        tags=("reverification", "bp18", "gate"),
    ),
    Mutation(
        id="M27", side="be", path=RECORD, kind="replace",
        anchor='        "assert_may_publish_defined_in": '
               '"app/services/workpaper_sync/word_sdt_engine.py",',
        new='        "assert_may_publish_defined_in": '
            '"app/services/workpaper_sync/word_entry_gate.py",',
        want=f"{U}.py::TestResidencyReverification::"
             "test_bp17_publish_gate_symbol_is_where_the_source_refs_say_it_is",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        ),
        why="把发布门符号的定义处指到 `word_entry_gate.py`（那里只有**调用** "
            "`definitions.binding.assert_may_publish()`，没有 def）⇒ 复现首版 BP-17 的"
            "失准形态：source_refs 指的文件里找不到那个「恒抛」的方法。"
            "刻意选一个**在 source_refs 里**的文件，这样只靠「refs 里有没有它」的判据会漏",
        scope_check=_record_bp_measured_is(
            "BP-17",
            "assert_may_publish_defined_in",
            "app/services/workpaper_sync/word_entry_gate.py",
        ),
        tags=("reverification", "bp17"),
    ),
    Mutation(
        id="M28", side="be", path=RECORD, kind="replace",
        anchor='      "what": "`registry.PENDING_ENGINE_ADAPTERS` 仍禁止 '
               '`adapters/word.py`（禁令清单逐字包含该路径，磁盘上该文件仍不存在），'
               '放行门写明是 Task 61（真实 OO 9.4 F2 Word gate）；'
               'Task 61 复选框现扫仍是 `[-]`。"',
        new='      "what": "`registry.PENDING_ENGINE_ADAPTERS` 仍禁止 '
            '`adapters/word.py`，放行门写明是 Task 61；'
            'Task 61 当前 `[-]`，其 BP-10~BP-15 六条全部 open。"',
        want=f"{U}.py::TestResidencyReverification::"
             "test_bp18_no_longer_restates_upstream_blocking_ids",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        ),
        why="把 2026-08-31 那版**已被证伪**的措辞（转述 Task 61 的 BP-10~BP-15）放回去。"
            "上游重编号是常态：Task 61 早已改登记 BP-61-1/2/3，转述上游编号必然失准。"
            "反向判据必须拦住这种回退",
        scope_check=_record_bp_what_contains("BP-18", "BP-10~BP-15"),
        tags=("reverification", "bp18"),
    ),
    Mutation(
        id="M29", side="be", path=RECORD, kind="replace",
        # 🔴 刻意锚在 `path` 行而不是 `sha256` 行：digest 会随并发会话改动上游文件而变，
        #    拿它当字面锚点必然周期性 ANCHOR-MISS（脚本缺陷会被误读成守卫缺陷）。
        #    path 是稳定的，而把它改错同样能证明「digest 覆盖面」这条判据可失效。
        scope='    "word_sdt_engine": {',
        offset=1,
        anchor='      "path": "backend/app/services/workpaper_sync/word_sdt_engine.py",',
        new='      "path": "backend/app/services/workpaper_sync/word_resolution.py",',
        want=f"{U}.py::TestResidencyReverification::"
             "test_source_digests_cover_every_file_the_measured_criteria_read",
        wants=(
            f"{U}.py::TestAdjudicationRecord::test_record_is_reproducible",
        ),
        why="把 BP-17 判据所读源文件从 digest 覆盖面里换掉 ⇒ `word_sdt_engine.py` 不再被"
            "锁 digest，「措辞对得上的是**今天那份**源码」这句话失去凭据。"
            "锁 digest 不被校验时它只是装饰",
        # 作用域自证只看 `sources` 块：该路径在 BP-17 的 source_refs 与 measured 里
        # 仍会出现，用「全文不含」判会恒假 ⇒ ANCHOR-MISS（被误读成守卫缺陷）。
        scope_check=_record_source_paths_exclude(
            "backend/app/services/workpaper_sync/word_sdt_engine.py"
        ),
        tags=("reverification", "digest"),
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 63 守卫变异检验（B 子码错型 + S33-REV）",
            backend_args=BE_ARGS,
            frontend_dir=FE_DIR,
            frontend_filters=FE_FILTERS,
            vitest_json=VITEST_JSON,
        )
    )
