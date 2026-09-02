# -*- coding: utf-8 -*-
"""Task 59 守卫变异检验 —— Word tagged-SDT engine + candidate upgrader。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 59
Requirements: 2.3, 6.10, 6.18, 7.1, 7.2, 7.3, 7.4, 7.5, 7.8, 7.9, 7.10, 8.10, 8.11,
9.1, 9.8, 9.9, 9.10, 14.16
Properties: P28 / P30 / P31 / P32 / P34 / P65 / P67 / P71

## 变异分四组

* **engine 准入与顺序（M01–M07）** —— substrate 门顺序、安全门、离线发布门、
  tag 形态真源。验证「quarantined/candidate/缺 bundle 各自可达且互不遮蔽」。
* **engine tag 语义（M08–M17）** —— 缺 tag / 未登记 / 实例计数 / 层级 / 行身份 /
  多实例异值 / 容器识别 / `w:br` 往返 / 采集口径一致性。验证 P30/P32/P34/P65。
* **instrumentation（M20–M32）** —— stale 门四项、token 命中数、`w:t` 严格匹配、
  可见文本流不变量、SDT 外正文逐块解释、只改 document.xml、`w:lock` 禁令、
  candidate 两个 target 恒 None。验证 P67/P71 与「注入只加结构」。
* **数据文件（M33–M35）** —— gate 基线 JSON 本体（带 `scope_check` 作用域自证）。
* **merge 域登记（M36–M37）** —— 本 Task 在 Task 14 那张跨任务共享登记表里退役了
  Word 侧那条延后，两条变异分别证明「登记指向的模块」与「空表的前提」都可被 falsify。

## 已知坑（本脚本逐条规避）

* `want` 用**短 nodeid**（`file.py::Class::test`，不带目录前缀）；
* pytest 参数传 `-rfE`（`-rf` 收不进 error 态用例名）；
* 锚点一律**单行**（工作树 CRLF，跨行锚点必 ANCHOR-MISS）；
* 替换体保持**语法合法** —— 整行替换让后续行悬空会 collection error，被误判成
  WRONG-TEST。故条件语句一律用短路式 `if False and <原式>:` 或 `if False:`；
* 同形态锚点用 `scope` + `offset` **相对定位**，不用绝对 `line`。

## 用法（仓库根）

    py -3 backend/scripts/diagnose/mutate_task59_word_sdt_engine_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task59_word_sdt_engine_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task59_word_sdt_engine_guards.py --run all
    py -3 backend/scripts/diagnose/mutate_task59_word_sdt_engine_guards.py --run M01,M08

只改本 Task 的生产文件与自有数据文件；不写业务库、不发网络请求、**不触碰
`backend/wp_templates/`**（权威模板只读）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

WE = "backend/app/services/workpaper_sync/word_sdt_engine.py"
WI = "backend/app/services/workpaper_sync/word_instrumentation.py"
GATE = "backend/data/onlyoffice_word_instrumentation_gate.json"
#: 跨任务共享的 merge 域登记表（Task 14 拥有判据，本 Task 只在其中加/退役自己那条）。
MERGE = "backend/app/services/workpaper_sync/merge.py"

U = "test_task59_word_sdt_engine"
T14 = "test_task14_merge_conflicts.py"

#: 覆盖面分母：本 Task 新建的守卫文件 + 被本 Task 登记改动波及的 Task 14 判据。
GUARD_FILES = {
    f"{U}.py": "Task 59 新建（Word tagged-SDT engine 离线守卫，89 例）",
    "test_task59_word_candidate_pg.py": (
        "Task 59 新建（candidate 不入运行态的四条边界，真实 PostgreSQL，19 例）"
    ),
    T14: (
        "Task 14（merge 域消费方 ↔ 退役登记双向等值）—— 本 Task 退役了 Word 侧那条延后，"
        "M36/M37 证明该退役登记两侧都可被 falsify"
    ),
}

REACHABILITY = (
    f"{U}.py::TestFailureKindsDistinctAndReachable::"
    "test_every_engine_failure_kind_is_reachable"
)


def _gate_field_is(section: str, field: str, expected: object):
    """作用域自证：变异确实落在 gate 基线**那个字段**上。

    没有它时，锚点若命中了别处同形态的行，四态判定会报 GREEN（守卫缺陷），
    而真实原因是脚本缺陷 —— 本平台已实测过这个误判。
    """

    def _check(mutated: bytes) -> bool:
        try:
            payload = json.loads(mutated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return payload.get(section, {}).get(field) == expected

    return _check


def _gate_file_digest_is(role: str, expected: str):
    def _check(mutated: bytes) -> bool:
        try:
            payload = json.loads(mutated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        for tier in ("tier_a_runtime", "tier_b_evidence"):
            for item in payload.get(tier, {}).get("files") or []:
                if item.get("role") == role:
                    return item.get("sha256") == expected
        return False

    return _check


MUTATIONS: list[Mutation] = [
    # ═══ engine 准入与顺序 ═════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=WE, kind="replace",
        anchor="            assert_substrate_usable(",
        new="            _ = dict(",
        want=f"{U}.py::TestProperty65ProjectionEquivalence::"
             "test_quarantined_and_non_durable_incoming_are_rejected_at_the_entry",
        wants=(
            f"{U}.py::TestProperty65ProjectionEquivalence::"
            "test_upgrade_candidate_is_never_an_engine_substrate",
            REACHABILITY,
        ),
        why="把 substrate 准入门整条摘掉 ⇒ quarantined / candidate / 未 durable incoming "
            "全部放行。替换成 `_ = dict(` 保持括号与后续参数行语法合法（整行删除会让"
            "参数行悬空 → IndentationError → collection error → 被误判成 WRONG-TEST）",
    ),
    Mutation(
        id="M02", side="be", path=WE, kind="replace",
        anchor='    "substrate_admission",',
        new='    "ooxml_security",  # order swapped',
        want=f"{U}.py::TestNoParagraphOrRegexFallback::"
             "test_read_gate_order_puts_admission_before_any_parsing",
        wants=(
            f"{U}.py::TestProperty65ProjectionEquivalence::"
            "test_quarantined_and_non_durable_incoming_are_rejected_at_the_entry",
            f"{U}.py::TestProperty65ProjectionEquivalence::"
            "test_upgrade_candidate_is_never_an_engine_substrate",
        ),
        why="🔴 判定顺序不可交换：把准入门挪到 OOXML 安全门**之后** ⇒ 非 DOCX 字节先撞 "
            "`ooxml_structure_invalid`，「quarantined 永不进 engine」落在永久不可达分支"
            "（本 spec 已实测同形态 3 次）。守卫刻意用一份**不是 zip** 的 artifact，"
            "所以顺序一换就打红。\n"
            "🔴 首轮用 `kind=move` 判 ANCHOR-MISS（两个锚点落在同一块内，因为 "
            "`block_open` 与 `anchor` 同一行），已把门顺序改成显式声明元组 "
            "`READ_GATE_ORDER`，于是「换顺序」成为一条可单行变异的真实改动",
    ),
    Mutation(
        id="M03", side="be", path=WE, kind="replace",
        anchor="                binding.assert_may_publish()",
        new="                pass  # publish gate removed",
        want=f"{U}.py::TestProperty28FrozenDefinitionDrift::"
             "test_published_representation_substrate_needs_an_approved_bundle",
        wants=(REACHABILITY,),
        why="离线模式也能读 published representation ⇒ 「缺 approved bundle 时只能离线"
            "验证 candidate」这条边界失守，`word_approved_bundle_required` 变不可达",
    ),
    Mutation(
        id="M04", side="be", path=WE, kind="replace",
        anchor="        if self.mode is not WordEngineMode.bundle_bound or self.bundle is None:",
        new="        if False:",
        want=f"{U}.py::TestProperty28FrozenDefinitionDrift::"
             "test_offline_binding_can_never_publish",
        wants=(
            f"{U}.py::TestProperty28FrozenDefinitionDrift::"
            "test_published_representation_substrate_needs_an_approved_bundle",
            REACHABILITY,
        ),
        why="`assert_may_publish` 恒通过 ⇒ 离线态可以走发布路径。与 M03 是两个不同位置"
            "（调用点 vs 判据体），两处都要各自可被抓到",
    ),
    Mutation(
        id="M05", side="be", path=WE, kind="replace",
        anchor="        elif self.bundle is not None:",
        new="        elif False:",
        want=f"{U}.py::TestProperty28FrozenDefinitionDrift::"
             "test_offline_mode_must_not_carry_a_bundle",
        why="离线模式允许携带 bundle ⇒ 两个模式不再互斥，「离线」会变成「有时候也能发布」",
    ),
    Mutation(
        id="M06", side="be", path=WE, kind="replace",
        anchor="from app.services.workpaper_sync.contracts import _SDT_TAG_RE as SDT_TAG_PATTERN",
        new='import re as _re; SDT_TAG_PATTERN = _re.compile(r"^gt:(?P<kind>field|block):(?P<contract>[a-z0-9][a-z0-9_.\\-]*):(?P<key>[A-Za-z0-9_.\\-/{}]+)$")',
        want=f"{U}.py::TestNoParagraphOrRegexFallback::"
             "test_tag_pattern_has_no_second_source_in_the_engine",
        why="🔴 复制一份**字符完全相同**的正则 ⇒ tag 形态出现第二真源。\n"
            "首轮此条判 GREEN：守卫原先用 `WE.SDT_TAG_PATTERN is C._SDT_TAG_RE`，而 "
            "`re` 模块对 `(pattern, flags)` 有编译缓存 ⇒ `re.compile(<同串>)` 返回的就是"
            "**同一个对象**，`is` 照样成立。已改成 AST 结构判据（必须 import 那一份 + "
            "engine 内零 `*.compile(...)` 调用）",
    ),
    Mutation(
        id="M07", side="be", path=WE, kind="replace",
        anchor="    UnmanagedRegionDriftError.error_code,",
        new='    "word_only_region_drift",',
        want=REACHABILITY,
        why="🔴 登记一个**从未被抛出**的 error_code ⇒ 「实测集合与登记清单双向锁死」必须"
            "打红。这正是本任务首轮实测到的假绿形态（曾声明过一个死类型 "
            "`WordOnlyRegionDriftError`），已按判据删掉",
    ),
    # ═══ engine tag 语义 ═══════════════════════════════════════════════
    Mutation(
        id="M08", side="be", path=WE, kind="replace",
        anchor="    if missing:",
        new="    if False:",
        want=f"{U}.py::TestProperty30TagOnly::test_removing_the_tag_fails_closed",
        wants=(
            f"{U}.py::TestProperty30TagOnly::"
            "test_placeholder_text_alone_is_not_a_protocol",
            f"{U}.py::TestProperty34NoDegradation::"
            "test_incoming_bytes_survive_a_failed_extract",
            REACHABILITY,
        ),
        why="🔴 Property 30 的核心：缺 tag 不再 fail closed ⇒ 只剩 placeholder 文本的"
            "原始模板会被当成「读到 0 个字段」静默通过，而 Requirement 7.8 要求 operation "
            "error + 保留 Word 文件版本",
    ),
    Mutation(
        id="M09", side="be", path=WE, kind="replace",
        anchor="        raise WordTagUnregisteredError(",
        new="        _ = (  # no longer raises",
        want=f"{U}.py::TestProperty30TagOnly::test_unregistered_tag_fails_closed",
        wants=(REACHABILITY,),
        why="未登记 tag 不再 fail closed ⇒ 正是 Requirement 6.20 / 7.1 禁止的"
            "「降级到位置/标题猜测」。\n"
            "🔴 替换体用 `_ = (` 而不是 `return ...`：后者会让紧跟的 f-string 参数行"
            "悬空 → IndentationError → collection error → 被误判成 WRONG-TEST"
            "（首轮实测 2 errors）。`_ = (` 保持括号配对与后续行语法合法",
        scope="        for spec in self.contract.all_fields():",
        offset=5,
    ),
    Mutation(
        id="M10", side="be", path=WE, kind="replace",
        anchor='        if group[0].spec.instances == "one" and len(group) > 1:',
        new="        if False:",
        want=f"{U}.py::TestProperty30TagOnly::test_instance_count_drift_fails_closed",
        wants=(REACHABILITY,),
        why="`instances='one'` 却出现两个实例时不再拒 ⇒ Requirement 7.10 的「字段实例"
            "计数」检测失效，模板漂移/SDT 被复制静默通过",
    ),
    Mutation(
        id="M11", side="be", path=WE, kind="replace",
        anchor="            if block_tag not in inst.ancestor_tags:",
        new="            if False:",
        want=f"{U}.py::TestProperty30TagOnly::test_hierarchy_flattening_fails_closed",
        wants=(REACHABILITY,),
        why="block 容器被删后内层 field 的层级漂移不再打红 ⇒ 「区块内字段」的归属靠位置"
            "猜（Requirement 7.5 / Property 30）",
    ),
    Mutation(
        id="M12", side="be", path=WE, kind="replace",
        anchor='        if inst.tag.row_scoped and "/tc" not in inst.container_path:',
        new="        if False:",
        want=f"{U}.py::TestProperty30TagOnly::"
             "test_row_scoped_tag_outside_a_table_is_hierarchy_drift",
        wants=(REACHABILITY,),
        why="行域 tag 跑到表格外也放行 ⇒ 读到的值不再属于任何行，而行身份正是靠单元格内"
            "field SDT 承载的（Requirement 7.2）",
    ),
    Mutation(
        id="M13", side="be", path=WE, kind="replace",
        anchor="    if orphan_rows:",
        new="    if False:",
        want=f"{U}.py::TestProperty34NoDegradation::"
             "test_materialize_writes_nothing_when_row_identity_is_absent",
        wants=(REACHABILITY,),
        why="要写的行 UUID 不存在时不再拒 ⇒ 会按位置落到某一行上（Requirement 7.2 明令"
            "禁止用表格行号识别）。守卫同时断言**一个字节都没落盘**",
    ),
    Mutation(
        id="M14", side="be", path=WE, kind="replace",
        anchor="        if duplicate is not None:",
        new="        if False:",
        want=f"{U}.py::TestProperty32DuplicateWordInstances::"
             "test_divergent_values_produce_a_conflict_listing_every_xpath",
        why="🔴 Property 32：同 stable tag 多实例异值时不再产生 duplicate conflict ⇒ "
            "engine 自行选了第一个实例的值（`incoming_envelope` 取的就是首个 XPath 序"
            "的快照），审计师看不到另一处的不同值。\n"
            "🔴 收口时重新定位：原锚点 `if len(texts) > 1:` 是**内联**判定，而 AC 7.4 的"
            "归约规则已按「单一真源」收敛到 Task 14 的 `reduce_word_instances`，engine "
            "只保留「拿到 duplicate 就记冲突」这一句 ⇒ 旧锚点随之消失（ANCHOR-MISS）。"
            "改打这一句，并用 `scope`+`offset` 相对定位（绝对行号一改文件就失效）",
        scope="        incoming_envelope, duplicate = reduce_word_instances(observation, locator)",
        offset=1,
    ),
    Mutation(
        id="M15", side="be", path=WE, kind="replace",
        anchor="        if nested:",
        new="        if False:",
        want=f"{U}.py::TestProperty65ProjectionEquivalence::"
             "test_materialize_extract_roundtrip_is_type_equal",
        wants=(
            f"{U}.py::TestProperty31WordOnlyPreserved::"
            "test_two_materialize_passes_keep_every_non_sdt_node",
        ),
        why="🔴 block 容器不再被识别为容器 ⇒ 整块覆盖 `w:sdtContent`，内层 inline SDT "
            "连 tag 一起被抹掉。首轮实测正是这个形态（`written_tags` 里同时出现容器 tag "
            "与内层 tag），因为容器分类与反向替换的 span 重叠",
    ),
    Mutation(
        id="M16", side="be", path=WE, kind="replace",
        anchor='            pieces.append("\\n")',
        new="            pass  # drop w:br",
        want=f"{U}.py::TestProperty65ProjectionEquivalence::test_multiline_values_round_trip",
        wants=(
            f"{U}.py::TestProperty65ProjectionEquivalence::"
            "test_materialize_extract_roundtrip_is_type_equal",
        ),
        why="🔴 `w:br` 不再读成 `\\n` ⇒ 「A\\nB」写进去读回来是「AB」，多行值的反读等值门"
            "在真实数据上必红。首轮实测就是它（design §Word extract 明写要保留换行）",
    ),
    Mutation(
        id="M17", side="be", path=WE, kind="replace",
        anchor="        if ordinal >= len(texts):",
        new="        if False and ordinal >= len(texts):",
        want=f"{U}.py::TestProperty30TagOnly::"
             "test_two_collector_disagreement_fails_closed",
        why="两个采集口径（ElementTree 遍历 vs 字节 span 扫描）实例数不一致时不再 fail "
            "closed ⇒ 会 IndexError 或读到错位的值。\n"
            "🔴 首轮此条判 GREEN：真实数据上两个口径一直一致 ⇒ 分支不可达（假绿第④源）。"
            "所有能造出分歧的畸形 XML 都被更早的 `_fingerprint_or_fail` 拦掉，故改用"
            "**故障注入**（monkeypatch `_sdt_texts_by_tag` 截短一个实例）让它可达",
    ),
    Mutation(
        id="M18", side="be", path=WE, kind="replace",
        anchor='    verdicts["managed_row_identity"] = not lost_rows',
        new='    verdicts["managed_row_identity"] = True',
        want=f"{U}.py::TestProperty31WordOnlyPreserved::"
             "test_row_identity_loss_is_detected_on_the_gt_scheme",
        why="🔴 行身份保留判据恒真 ⇒ 回到「借用 `word_sdt_fingerprint.row_uuid_set`」的"
            "空集恒等价形态（那一格认旧 `gtsdt/v1` 方案，在 `gt:` 方案下两侧恒空）",
    ),
    Mutation(
        id="M19", side="be", path=WE, kind="replace",
        anchor="    return (value.value_type.value, str(value.value))",
        new="    return (value.value_type.value, \"\")",
        want=f"{U}.py::TestProperty65ProjectionEquivalence::"
             "test_managed_projection_mismatch_blocks_publication",
        wants=(REACHABILITY,),
        why="**非 text** 字段的类型化等值口径退化成「一律相等」⇒ AC 8.11 的反读等值门"
            "对金额/日期恒通过。\n"
            "🔴 首轮此条判 GREEN：守卫的 fixture 五个字段全是 text，这条 `return` 落在"
            "从未被执行的分支上。已给 F2-22 契约补了真实的 `${bsDate}` 占位作 "
            "`value_type=date` 字段，并让不等值用例对**日期**说谎",
    ),
    # ═══ instrumentation ═══════════════════════════════════════════════
    Mutation(
        id="M20", side="be", path=WI, kind="replace",
        anchor='            if observed != item["sha256"]:',
        new="            if False:",
        want=f"{U}.py::TestProperty71ProbeGateFreshness::"
             "test_carrier_contract_digest_drift_is_stale",
        why="Tier A 的文件 digest 比对被短路 ⇒ 载体裁决契约或 fingerprint 模块改了也照旧"
            "放行（Requirement 14.16 / Property 71）",
    ),
    Mutation(
        id="M21", side="be", path=WI, kind="replace",
        anchor="            if not want or want != got:",
        new="            if False:",
        want=f"{U}.py::TestProperty71ProbeGateFreshness::test_environment_drift_is_stale",
        why="OO build / source_commit / runner 三项漂移不再 stale ⇒ 旧证据被无限保鲜",
    ),
    Mutation(
        id="M22", side="be", path=WI, kind="replace",
        anchor='            if declared[wp_code]["sha256"] != want_sha:',
        new="            if False:",
        want=f"{U}.py::TestProperty71ProbeGateFreshness::"
             "test_probe_template_digest_drift_is_stale",
        why="probe 文档模板 digest 在契约与基线之间不一致时不再 stale ⇒ 换了模板还沿用"
            "旧裁决",
    ),
    Mutation(
        id="M23", side="be", path=WI, kind="replace",
        anchor="        if len(hits) != expected:",
        new="        if False:",
        want=f"{U}.py::TestZipLevelInstrumentation::"
             "test_token_occurrence_drift_fails_closed",
        wants=(
            f"{U}.py::TestZipLevelInstrumentation::test_missing_token_fails_closed",
        ),
        why="🔴 一次性 token 的命中数不再与声明值锁死 ⇒ 缺失/重复/漂移全部静默通过，"
            "「按段落序号挑一个」这条禁令失守（Requirement 7.1）",
    ),
    Mutation(
        id="M24", side="be", path=WI, kind="replace",
        anchor='        if after not in (">", " ", "\\t", "\\r", "\\n", "/"):',
        new="        if False:",
        want=f"{U}.py::TestZipLevelInstrumentation::"
             "test_visible_text_stream_is_byte_identical",
        why="🔴 `\"<w:t\"` 退回裸前缀匹配 ⇒ `w:sdtPr` 里的 `<w:tag w:val=…/>` 被当成文本"
            "节点开头，一路吞到下一个 `</w:t>`，把整段 XML 算成「可见文本」。首轮实测："
            "注入 `${purpose}` 后可见文本从 546 涨到 632 字符",
    ),
    Mutation(
        id="M25", side="be", path=WI, kind="replace",
        anchor="    if text_before != text_after:",
        new="    if False:",
        want=f"{U}.py::TestZipLevelInstrumentation::"
             "test_visible_text_change_inside_an_sdt_is_still_rejected",
        why="可见文本流不变量被撤 ⇒ 注入可以顺手改掉可见字符。它是三层判据里最强的一条，"
            "撤掉后只剩逐 aspect 比对 —— 而 SDT **内部**的文本改动在逐 aspect 口径下"
            "完全看不见（`outside_sdt_text` 不含它、`sdt_tag_set` 也不含它）",
    ),
    Mutation(
        id="M26", side="be", path=WI, kind="replace",
        anchor='    if not outside["explained"]:',
        new="    if False:",
        want=f"{U}.py::TestZipLevelInstrumentation::"
             "test_swallowing_a_free_text_paragraph_is_rejected",
        why="SDT 外正文的增删不再逐块用声明 token 解释 ⇒ 「注入顺手吞掉一整段自由正文」"
            "会照样绿。真实缺陷形态是 31 块掉到 26 块（整个 run 被包进 SDT）。\n"
            "🔴 首轮此条判 GREEN：没有任何用例构造**未被 token 解释**的 outside 差异。"
            "补的反例刻意让可见文本流不变，否则会被更前面那条不变量顺手挡掉、本判据仍不可达",
    ),
    Mutation(
        id="M27", side="be", path=WI, kind="replace",
        anchor="    if leaked:",
        new="    if False:",
        want=f"{U}.py::TestZipLevelInstrumentation::"
             "test_only_document_part_changed_is_enforced_not_just_observed",
        why="`word/document.xml` 之外的部件被改动时不再拒 ⇒ 批注/修订/图片/页眉页脚/"
            "styles/customXml 可以静默丢失（Requirement 7.3 / 9.9）。\n"
            "🔴 首轮此条判 GREEN：`instrument_docx_bytes` 结构上只写一个部件 ⇒ 这条防御"
            "判据在公开 API 上不可达。已抽成公开 `assert_only_document_part_changed`，"
            "守卫直接喂反例",
    ),
    Mutation(
        id="M28", side="be", path=WI, kind="replace",
        anchor="    if _FORBIDDEN_SDT_CHILD in document_xml:",
        new="    if False:",
        want=f"{U}.py::TestZipLevelInstrumentation::test_no_w_lock_is_injected",
        why="允许注入 `w:lock` ⇒ OO 无法删除 SDT，等于替载体作弊，Task 6 的"
            "`no_w_lock_injected` 前提不再成立、载体保留结论失效。\n"
            "🔴 首轮此条判 GREEN：守卫只断言产物里没有 `w:lock`（观察），而 `_sdt_wrapper` "
            "本来就不写锁 ⇒ 判据不可达。已抽成公开 `assert_no_sdt_lock` 并补反面用例",
    ),
    Mutation(
        id="M29", side="be", path=WI, kind="replace",
        anchor="    if observed_counts != want_counts:",
        new="    if False:",
        want=f"{U}.py::TestZipLevelInstrumentation::"
             "test_readback_detects_a_lost_instance_not_just_a_lost_tag",
        why="🔴 反读只比 tag **集合**不比实例计数 ⇒ 同 tag 少一个实例时集合完全相同、"
            "判绿（Requirement 7.10）",
    ),
    Mutation(
        id="M30", side="be", path=WI, kind="replace",
        anchor="            target_contract_definition_id=None,",
        new="            target_contract_definition_id=template_definition.definition_id,",
        want="test_task59_word_candidate_pg.py::TestBoundary3NoPublishedRepresentation::"
             "test_candidate_is_not_finalizable_without_approved_children",
        why="🔴 candidate 带上伪造的 target contract ⇒ 本任务「不得为任何 entry 伪造 "
            "contract/bundle」的否定式承诺失守，`ck_wpruc_ready_requires_bundle` 之后"
            "就能被 finalize。两处同形态锚点用 scope 相对定位到**写库那一处**",
        scope="        candidate = await self._repo.create_upgrade_candidate(",
        offset=13,
    ),
    Mutation(
        id="M31", side="be", path=WI, kind="replace",
        anchor="    if lock_policy != REQUIRED_PROBE_LOCK_POLICY:",
        new="    if False:",
        want=f"{U}.py::TestProperty71ProbeGateFreshness::"
             "test_tier_a_and_tier_b_are_enforced_against_real_files",
        why="Task 6 的 `lock_policy` 变化不再打红 ⇒ 本模块的注入判据建立在「无 w:lock」"
            "前提上，policy 改了必须重新取证。\n"
            "🔴 首轮此条判 GREEN：磁盘契约里这个值恒为 `no_w_lock_injected` ⇒ 判据在 "
            "`load()` 内部结构不可达。已抽成公开 `assert_probe_lock_policy` 并补三个"
            "错误取值的反面用例",
    ),
    Mutation(
        id="M32", side="be", path=WI, kind="replace",
        anchor="            if not target.is_file():",
        new="            if False:",
        # 三处同形态锚点（Tier A 文件 / probe 模板 / Tier B evidence），用 scope 相对
        # 定位到 `assert_evidence_fresh` 里那一处 —— 绝对行号一改文件就失效。
        scope="        for item in (baseline.get(\"tier_b_evidence\") or {}).get(\"files\") or []:",
        offset=2,
        want=f"{U}.py::TestProperty71ProbeGateFreshness::"
             "test_missing_evidence_is_stale_not_skipped",
        why="evidence 文件缺失时不再 stale ⇒ 「缺失即 stale，不得跳过」失守。"
            "本条同时验证守卫没有把它写成 skip（skip 等于删掉判据）",
    ),
    # ═══ 数据文件（带作用域自证）═══════════════════════════════════════
    Mutation(
        id="M33", side="be", path=GATE, kind="replace",
        anchor='    "onlyoffice_build": "9.4.0-129",',
        new='    "onlyoffice_build": "9.5.0-001",',
        want=f"{U}.py::TestProperty71ProbeGateFreshness::"
             "test_tier_a_and_tier_b_are_enforced_against_real_files",
        why="手改基线里的 OO build ⇒ 与 Task 6 契约的 `environment.oo_build` 不再一致，"
            "gate 必须 fail closed。验证守卫是**真跑一次** loader 再比对，而不是读 JSON "
            "字符串（假绿第②源在清册守卫上最危险）",
        scope_check=_gate_field_is("tier_a_runtime", "onlyoffice_build", "9.5.0-001"),
    ),
    Mutation(
        id="M34", side="be", path=GATE, kind="replace",
        anchor='        "sha256": "b494a3e0c8f89525ea8225a0a74a2077ed080d838b7a1518337a9845f76dc857"',
        new='        "sha256": "0000000000000000000000000000000000000000000000000000000000000001"',
        want=f"{U}.py::TestProperty71ProbeGateFreshness::"
             "test_tier_a_and_tier_b_are_enforced_against_real_files",
        why="手改 `word_sdt_fingerprint` 模块的基线 digest ⇒ Tier A 必须打红。"
            "该模块是全部载体事实的采集器，它变了裁决就得重取证",
        scope_check=_gate_file_digest_is(
            "fingerprint_module",
            "0000000000000000000000000000000000000000000000000000000000000001",
        ),
    ),
    Mutation(
        id="M35", side="be", path=GATE, kind="replace",
        anchor='    "source_commit": "d330d7cea6bb112709edce5bf287877df0a5f60c",',
        new='    "source_commit": "0000000000000000000000000000000000000000",',
        want=f"{U}.py::TestProperty71ProbeGateFreshness::"
             "test_tier_a_and_tier_b_are_enforced_against_real_files",
        why="手改 source_commit ⇒ 与契约不一致必须 stale。Requirement 14.16 明列"
            "「runner/source commit 变化后按 stale policy 失效」",
        scope_check=_gate_field_is(
            "tier_a_runtime", "source_commit", "0" * 40
        ),
    ),
    # ═══ merge 域登记（跨任务共享表，归因型判据）═════════════════════
    Mutation(
        id="M36", side="be", path=MERGE, kind="replace",
        anchor='        "expected_consumer_module": "app/services/workpaper_sync/word_sdt_engine.py",',
        new='        "expected_consumer_module": "app/services/workpaper_sync/not_there.py",',
        want=f"{T14}::TestTask14ScopeBoundary::test_retired_deferral_records_who_wired_it",
        wants=(
            f"{T14}::TestTask14ScopeBoundary::"
            "test_merge_domain_consumers_match_the_retirement_registry_exactly",
        ),
        why="🔴 本 Task 的退役登记指向不存在的模块 ⇒ 「谁在哪个任务把 Word 侧输入形态"
            "接上了」的记录与事实脱钩。Task 14 的双向等值必须两侧都抓到："
            "登记方（目标文件不存在）与实测方（word_sdt_engine 成了未登记消费方 ⇒ "
            "看起来像绕过唯一 commit 入口）。范式取自 Task 37 的 M39",
        tags=("registry",),
    ),
    Mutation(
        id="M37", side="be", path=MERGE, kind="replace",
        anchor="RETIRED_DEFERRALS: Final[tuple[Mapping[str, Any], ...]] = (",
        new="RETIRED_DEFERRALS: Final[tuple[Mapping[str, Any], ...]] = (); _RETIRED_SHADOW = (",
        want=f"{T14}::TestTask14ScopeBoundary::"
             "test_deferred_consumers_registration_is_complete",
        wants=(
            f"{T14}::TestTask14ScopeBoundary::test_retired_deferral_records_who_wired_it",
            f"{T14}::TestTask14ScopeBoundary::"
            "test_merge_domain_consumers_match_the_retirement_registry_exactly",
        ),
        why="🔴 本 Task 退役最后一条延后后 `DEFERRED_CONSUMERS` 成了空元组，Task 14 那条"
            "无条件 `assert M.DEFERRED_CONSUMERS` 因此把「过渡事实」锁成了永久不变量"
            "（真源改对反而打红）。收口裁决把它改成**前提式**：空表合法的前提是"
            "「退役登记非空 + merge 域真有生产消费方」。本条把 `RETIRED_DEFERRALS` 也清空"
            "（`= (); _RETIRED_SHADOW = (` 让后续条目仍是合法元组、不产生 collection "
            "error），于是「两张表同时为空＝登记表被整段删掉」必须打红 —— 证明放宽的那一"
            "步没有留下「清空登记以躲判据」的缺口",
        tags=("registry",),
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 59 Word tagged-SDT engine + candidate upgrader 守卫变异检验",
            backend_args=[
                f"backend/tests/workpaper_sync/{U}.py",
                "backend/tests/workpaper_sync/test_task59_word_candidate_pg.py",
                f"backend/tests/workpaper_sync/{T14}",
                "-q",
                "--tb=no",
                "-rfE",
            ],
            # 冻结基线：89（离线）+ 19（真库）+ 178（Task 14 判据）= 286 passed
            # （2026-08-29 收口实测）。
            # 首轮 84+19=103 时 M25/M17/M19 三条无有效判据，逐条补齐后升到 106：
            # M25→可见文本流反例 / M17→采集口径分歧故障注入 / M19→非 text（date）字段 /
            # M26→吞掉自由正文反例 / M27,M28→两条防御判据抽成公开函数后补反面用例。
            # 🔴 收口时把 Task 14 的守卫纳入基线：本 Task 退役了 merge 域最后一条延后，
            #    M36/M37 的判据只存在于那个文件里，不纳入 backend_args 则两条恒 GREEN。
            baseline_backend_passed=286,
        )
    )
