"""Task 6 守卫变异检验：Word tagged SDT 载体真值表 ↔ 真实 OO 9.4 实证互锁。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure Task 6
Requirements 7.2 / 7.5 / 7.6 / 14.4 / 14.16 · Property 33

走 `backend/scripts/_mutation_kit` 共享件（`guard_files` 覆盖面分母、声明期锚点校验、
四态判定 RED/GREEN/WRONG-TEST/ANCHOR-MISS、备份还原 md5 自证均由共享件提供）。

## 变异分两半（互锁的两个方向）

- **契约侧（M01–M28、M37–M38）**：改 `onlyoffice_word_sdt_carrier_contract.json` 的裁决/
  期望值 —— 验证「手填 `probe_verdict: passed`、把 row_sdt 的 failed 改成 passed、放开
  downstream gate、把 not_covered 改成 passed、改 artifact 计数」这类假绿必须被 evidence
  反算打红。
- **evidence 侧（M29–M36）**：改 `operation_matrix.json` / `instrumentation_report.json` /
  `source_template_sha_after.json` —— 验证「实证变了但契约没重新裁决」同样打红。

## 本任务最贵的一条反向锁

M01：把 `row_sdt` 的 `probe_verdict` 从 `failed` 改成 `passed`。实测 9/9 artifact
里 row 级 SDT 全被 OO 9.4 剥离；若守卫放过这一改，Task 59/61 就会按 Requirement 7.2
的现设计去建 row-level 回写，整条 Word lane 返工。

## 「不是一改就红」的反向证据

两条：

1. **爆炸半径** —— 每条变异只打红 1–4 例（守卫共 36 例），且命中的正是声明的 `want`。
   守卫若过敏，一条变异会连带打红大片。
2. **守卫内自检** —— `test_negative_control_is_field_specific` 往契约副本塞未知键并断言
   判据**保持通过**。放在守卫里而不是当 GREEN 对照变异，因为共享件把 GREEN 一律判成
   守卫缺陷（`verdict.py` 的四态定义），有意的 GREEN 会让 rc 恒为 1。

## 首轮 3 条 GREEN + 1 条 ERROR 的处置（2026-08-25）

首轮 36 条跑出 RED 32 / GREEN 3 / ERROR 1，**没有**直接采信。逐条归因后收口：

- **M30 GREEN** → 守卫只断言 `intentional_deletions` 字典非空，键改名照样过。补
  「键必须解析到真实 doc/op 格」+「逐行 `intentionally_removed_injections` 对齐」两道判据。
- **M31 GREEN** → 守卫只按行校验 `op_label_source`，不校验矩阵自述的 `op_label_policy`。
  新增 `test_op_label_policy_statement_matches_observed_label_sources`，把自述与逐行事实锁死。
- **M34 GREEN** → 7.5 场景只比全局集合，f222/F02 被改名后 f223/G02 仍贡献同名场景。
  契约新增 `requirement_7_5_scenarios.instrumented`（逐条 doc/inj_id/run_split），
  守卫按条比对；同时补 M37/M38 给这段新声明本身上反向锁。
- **M29 ERROR → 二轮 GREEN → 收口** → 首轮 `FileNotFoundError: operation_matrix.json.mutbak`：
  备份文件在本条变异运行期间被**别的进程**移走。留痕不足以唯一定位是谁（同一 harness 的
  重叠调用、并发 `--restore`、或并发跑 probe `analyze` 重写 evidence 都能造成同一形态），
  但三种可能指向同一条教训：**变异期间 evidence 目录必须独占**，且 `stale_backups()` 是
  全仓 `rglob` ⇒ 别的 spec 在跑变异时本 harness 会直接 ABORT，必须等对方跑完再开。
  独占后重跑露出真实缺口 —— 所有裁决都绕开
  `tag_set_not_reduced` 直接重数，**布尔本身没人校验**，evidence 可以自相矛盾地躺着而
  下游会读它。补 `test_evidence_derived_verdict_flags_agree_with_their_own_raw_measurements`
  把 5 个派生布尔与各自原始测量锁死。

## 用法（仓库根）

    python backend/scripts/diagnose/mutate_task6_word_sdt_guards.py --list
    python backend/scripts/diagnose/mutate_task6_word_sdt_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task6_word_sdt_guards.py --run all --out <evidence>/mutation_report.json
    python backend/scripts/diagnose/mutate_task6_word_sdt_guards.py --run M01,M23

只碰契约 JSON 与 evidence JSON；不动生产代码、不写业务库、不发网络请求、不触碰
`backend/wp_templates/` 权威模板。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

CONTRACT = "backend/data/onlyoffice_word_sdt_carrier_contract.json"
_EV = (
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/"
    "evidence/task6-oo94-word-tagged-sdt"
)
MATRIX = f"{_EV}/operation_matrix.json"
INSTRUMENTATION = f"{_EV}/instrumentation_report.json"
SOURCE_SHA_AFTER = f"{_EV}/source_template_sha_after.json"

#: 覆盖面分母：本 spec Task 6 新建的守卫文件。
GUARD_FILES = {
    "test_workpaper_word_sdt_carrier_contract.py": "Task 6 新建（Word SDT 载体真值表 ↔ 实证互锁）",
}


# ---------------------------------------------------------------------------
# 作用域自证：确认变异确实落在被测结构里，而不是同名注释/说明字段
# ---------------------------------------------------------------------------


def _carrier_field_is(carrier: str, field: str, expected: object):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        item = next((c for c in payload["carriers"] if c["carrier"] == carrier), None)
        return item is not None and item.get(field) == expected

    return check


def _anchor_field_is(anchor: str, field: str, expected: object):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        item = next((a for a in payload["anchors"] if a["anchor"] == anchor), None)
        return item is not None and item.get(field) == expected

    return check


def _nested_field_is(path: tuple[str, ...], expected: object):
    def check(data: bytes) -> bool:
        node: object = json.loads(data.decode("utf-8"))
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return False
            node = node[key]
        return node == expected

    return check


def _matrix_row_field(artifact: str, path: tuple[str, ...], expected: object):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        row = next(
            (r for r in payload["matrix"] if (r.get("artifact_file") or "").endswith(artifact)),
            None,
        )
        if row is None:
            return False
        node: object = row
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return False
            node = node[key]
        return node == expected

    return check


MUTATIONS: list[Mutation] = [
    # ================= 契约侧：把失败裁决手填成通过 =================
    Mutation(
        id="M01",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='      "carrier": "row_sdt",',
        offset=2,
        anchor='      "probe_verdict": "failed",',
        new='      "probe_verdict": "passed",',
        want="test_row_sdt_carrier_is_disproven_by_evidence",
        wants=("test_downstream_gate_lists_exactly_the_passed_items",
               "test_w_tag_anchor_scope_matches_carrier_verdicts"),
        why="把已被 9/9 artifact 证伪的 row 级 SDT 改成 passed —— 本任务最贵的一条反向锁；"
            "若守卫放过，Task 59/61 会按 Requirement 7.2 现设计去建 row-level 回写，整条 Word lane 返工",
        scope_check=_carrier_field_is("row_sdt", "probe_verdict", "passed"),
    ),
    Mutation(
        id="M02",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='      "carrier": "row_sdt",',
        offset=3,
        anchor='      "may_enter_word_engine": false,',
        new='      "may_enter_word_engine": true,',
        want="test_row_sdt_carrier_is_disproven_by_evidence",
        wants=("test_downstream_gate_lists_exactly_the_passed_items",),
        why="让准入布尔与 probe_verdict 脱钩（failed 却许进 engine）—— 两处各写一份就会出现"
            "「读 verdict 的代码拦住、读布尔的代码放行」的分叉",
        scope_check=_carrier_field_is("row_sdt", "may_enter_word_engine", True),
    ),
    Mutation(
        id="M03",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "expected_artifacts_retaining_any_row_tag": 0,',
        new='      "expected_artifacts_retaining_any_row_tag": 9,',
        want="test_row_sdt_carrier_is_disproven_by_evidence",
        why="把「0 个 artifact 保留 row tag」谎报成 9；守卫必须从 operation_matrix 重新数 "
            "tags_present 而不是采信契约数字",
        scope_check=_carrier_field_is("row_sdt", "expected_artifacts_retaining_any_row_tag", 9),
    ),
    Mutation(
        id="M04",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "expected_rows_wrapped_in_sdt_after_oo": 0,',
        new='      "expected_rows_wrapped_in_sdt_after_oo": 3,',
        want="test_row_sdt_carrier_is_disproven_by_evidence",
        why="谎称 OO 返回件里还有 3 行被 SDT 包着；实证 rows_wrapped_in_sdt 恒为 0",
        scope_check=_carrier_field_is("row_sdt", "expected_rows_wrapped_in_sdt_after_oo", 3),
    ),
    Mutation(
        id="M05",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "expected_row_sdt_injected_at_instrumentation": 3,',
        new='      "expected_row_sdt_injected_at_instrumentation": 0,',
        want="test_row_sdt_carrier_is_disproven_by_evidence",
        why="把注入的 row SDT 数改成 0 —— 那样「行载体失败」就变成「根本没测」，"
            "守卫必须回到 instrumentation manifest 数 rows 长度",
        scope_check=_carrier_field_is("row_sdt", "expected_row_sdt_injected_at_instrumentation", 0),
    ),
    Mutation(
        id="M06",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        "stripped_at_baseline": true,',
        new='        "stripped_at_baseline": false,',
        want="test_row_sdt_stripping_happens_at_baseline_not_by_row_edits",
        why="把「加载/保存路径固有剥离」改成「某个行操作触发」—— 两个结论对应完全不同的改法，"
            "守卫必须从 baseline 格的 tags_present 反算",
        scope_check=_nested_field_is(("carriers",), None) if False else None,
    ),
    Mutation(
        id="M07",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        "table_rows_survived": true,',
        new='        "table_rows_survived": false,',
        want="test_row_sdt_stripping_did_not_destroy_table_rows",
        why="把「只丢 SDT 包装」写成「行数据也丢了」—— 会把一个载体不支持问题夸大成数据损坏，"
            "守卫必须核 baseline 表行数仍为 4",
    ),
    Mutation(
        id="M08",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='      "anchor": "paragraph_index",',
        offset=2,
        anchor='      "probe_verdict": "failed",',
        new='      "probe_verdict": "passed",',
        want="test_paragraph_index_anchor_is_disproven_by_evidence",
        wants=("test_downstream_gate_lists_exactly_the_passed_items",),
        why="把 Requirement 7.1 明令禁止且已有实测反例的段落序号锚点改成 passed；"
            "放过就意味着允许写段落索引提取器",
        scope_check=_anchor_field_is("paragraph_index", "probe_verdict", "passed"),
    ),
    Mutation(
        id="M09",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='      "anchor": "paragraph_index",',
        offset=3,
        anchor='      "admissible_as_identity_anchor": false,',
        new='      "admissible_as_identity_anchor": true,',
        want="test_paragraph_index_anchor_is_disproven_by_evidence",
        wants=("test_downstream_gate_lists_exactly_the_passed_items",),
        why="裁决仍写 failed 但把可采纳布尔翻成 true —— 典型的「两处各写一份」分叉",
        scope_check=_anchor_field_is("paragraph_index", "admissible_as_identity_anchor", True),
    ),
    Mutation(
        id="M10",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "expected_artifacts_unstable": 1,',
        new='      "expected_artifacts_unstable": 0,',
        want="test_paragraph_index_anchor_is_disproven_by_evidence",
        why="把段落序号不稳定的 artifact 数改成 0 —— 那样 failed 裁决就没有反例支撑，"
            "守卫必须从 anchors.paragraph_index.stable 重新数",
        scope_check=_anchor_field_is("paragraph_index", "expected_artifacts_unstable", 0),
    ),
    Mutation(
        id="M11",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='        "op": "insert_paragraph",',
        offset=-1,
        anchor='        "doc": "f222",',
        new='        "doc": "b30112",',
        want="test_paragraph_index_anchor_is_disproven_by_evidence",
        why="把反例指到 b30112（那份文档段落序号实测是稳定的）—— 反例必须真的落在不稳定那一格",
        scope_check=_nested_field_is(("anchors",), None) if False else None,
    ),
    Mutation(
        id="M12",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        "run_count_after_oo": 2',
        new='        "run_count_after_oo": 3',
        want="test_run_index_anchor_is_disproven_by_evidence",
        why="把 OO 往返后的 run 数改回 3（= 与注入时相同）⇒ 反例前后相等，什么都没证伪；"
            "守卫必须核 run_counts_per_tag 实测值且要求前后不等",
    ),
    Mutation(
        id="M13",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='      "anchor": "sdt_id",',
        offset=3,
        anchor='      "admissible_as_identity_anchor": false,',
        new='      "admissible_as_identity_anchor": true,',
        want="test_retained_but_inadmissible_anchors_state_both_facts",
        wants=("test_downstream_gate_lists_exactly_the_passed_items",),
        why="`w:id` 在 OO 里确实没被重编号，很容易被误当成可用锚点；但同 stable key 的两实例"
            "共享同一个 w:id，实测不唯一 ⇒ 这条锁的是「保留 ≠ 可作身份」",
        scope_check=_anchor_field_is("sdt_id", "admissible_as_identity_anchor", True),
    ),
    Mutation(
        id="M14",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "duplicate_ids_observed": true,',
        new='      "duplicate_ids_observed": false,',
        want="test_sdt_id_duplicate_claim_is_backed_by_instrumentation",
        why="抹掉「w:id 重复」这条硬理由；守卫必须从 instrumentation manifest 里同 tag 的多实例"
            "sdt_id 反算，确认它们真的相等",
        scope_check=_anchor_field_is("sdt_id", "duplicate_ids_observed", False),
    ),
    Mutation(
        id="M15",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "duplicate_id_tag": "gt:field:f2.stocktake.plan:plan/entity_name"',
        new='      "duplicate_id_tag": "gt:field:f2.stocktake.plan:plan/purpose"',
        want="test_sdt_id_duplicate_claim_is_backed_by_instrumentation",
        why="把重复 id 的 tag 指到只有单实例的 purpose ⇒ 断言失去支撑；"
            "守卫必须要求该 tag 在注入清单里 >=2 个实例",
        scope_check=_anchor_field_is(
            "sdt_id", "duplicate_id_tag", "gt:field:f2.stocktake.plan:plan/purpose"
        ),
    ),
    Mutation(
        id="M16",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "expected_artifacts_retaining_all_inline_tags": 26,',
        new='      "expected_artifacts_retaining_all_inline_tags": 20,',
        want="test_inline_field_sdt_verdict_is_backed_by_every_artifact",
        why="把 inline 保留数从 26 改成 20，同时 verdict 仍是 passed ⇒ 自相矛盾；"
            "守卫必须重新数并要求 passed 时保留数 == 总数",
        scope_check=_carrier_field_is(
            "field_sdt_inline", "expected_artifacts_retaining_all_inline_tags", 20
        ),
    ),
    Mutation(
        id="M17",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "expected_hierarchy_regressions": 0,',
        new='      "expected_hierarchy_regressions": 4,',
        want="test_block_field_sdt_verdict_and_hierarchy_are_backed_by_evidence",
        why="谎称有 4 处层级回归；守卫必须从 hierarchy.regressions 重新数，并在 passed 时要求为 0",
        scope_check=_carrier_field_is("field_sdt_block", "expected_hierarchy_regressions", 4),
    ),
    Mutation(
        id="M18",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "expected_block_injection_docs": ["f222", "f223"],',
        new='      "expected_block_injection_docs": ["f222", "f223", "b30112"],',
        want="test_block_field_sdt_verdict_and_hierarchy_are_backed_by_evidence",
        why="把没有 block 注入的 b30112 也算进 block 载体的分母 ⇒ 分母被稀释；"
            "守卫必须从 manifest 的 block_tag 存在性反算文档集合",
        scope_check=_carrier_field_is(
            "field_sdt_block", "expected_block_injection_docs", ["f222", "f223", "b30112"]
        ),
    ),
    Mutation(
        id="M19",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "expected_artifacts_with_digest_unchanged": 11,',
        new='      "expected_artifacts_with_digest_unchanged": 26,',
        want="test_sdt_external_body_verdict_is_backed_by_digest_evidence",
        why="谎称 26 个 artifact 的自由正文都没变（实测只有 11 个）—— 那会把「显式改过自由正文」"
            "的格子也说成没变，等于掩盖了自己的操作",
        scope_check=_carrier_field_is(
            "sdt_external_body", "expected_artifacts_with_digest_unchanged", 26
        ),
    ),
    Mutation(
        id="M20",
        side="be",
        path=CONTRACT,
        kind="delete",
        anchor='        "f222/edit_in_sdt",',
        want="test_sdt_external_body_verdict_is_backed_by_digest_evidence",
        why="从「自由正文未变」的操作集合里删掉 f222/edit_in_sdt —— Requirement 7.3 的核心格；"
            "守卫比的是集合而不只是计数，删一项必须打红",
    ),
    Mutation(
        id="M21",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='      "aspect": "tag_missing_fail_closed_in_production",',
        offset=1,
        anchor='      "probe_verdict": "not_covered",',
        new='      "probe_verdict": "passed",',
        want="test_not_covered_items_are_never_marked_passed",
        why="把「生产 fail-closed」从 not_covered 改成 passed —— 这正是 Task 6 明令禁止的"
            "提前自证（该项由 Tasks 59/68 承接）",
    ),
    Mutation(
        id="M22",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "field_sdt_block",',
        new='      "row_sdt",',
        want="test_downstream_gate_lists_exactly_the_passed_items",
        why="把 downstream gate 的准入名单里塞进已证伪的 row_sdt（并挤掉 field_sdt_block）；"
            "gate 必须由裁决反算而不是手写",
        scope_check=_nested_field_is(
            ("downstream_gate", "carriers_allowed_into_word_engine"),
            ["field_sdt_inline", "row_sdt", "sdt_external_body"],
        ),
    ),
    Mutation(
        id="M23",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='    "status": "probe 级已取证可行；是否采纳为正式行身份协议属 design 修订，本 contract 不代替裁决"',
        new='    "status": "已采纳为正式行身份协议，Task 59 可直接实现"',
        want="test_row_identity_fallback_is_not_declared_adopted",
        why="把「取证可行」偷偷升级成「已采纳」—— 本 probe 无权替 design 选载体；"
            "这条锁的是探针不越权",
        scope_check=_nested_field_is(
            ("row_identity_fallback_measured", "status"),
            "已采纳为正式行身份协议，Task 59 可直接实现",
        ),
    ),
    Mutation(
        id="M24",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='    "lock_policy": "no_w_lock_injected",',
        new='    "lock_policy": "w_lock_sdtLocked_injected",',
        want="test_lock_policy_is_no_lock_and_matches_instrumentation",
        why="把 lock 策略改成「加锁」—— 若真加了锁，「OO 自发保留 tag」这个结论不成立；"
            "守卫必须回 staging docx 里核 <w:lock 是否真的不存在",
        scope_check=_nested_field_is(
            ("scope_and_non_claims", "lock_policy"), "w_lock_sdtLocked_injected"
        ),
    ),
    Mutation(
        id="M25",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "template_sha256": "b4facd6b7d31b1419eb102ede582e7e77b1a5c685a3f9513bb546b9de0bbb247",',
        new='      "template_sha256": "0000000000000000000000000000000000000000000000000000000000000000",',
        want="test_template_shas_match_readonly_authority_source",
        why="把权威模板 sha 改成全零 —— 全零 hash 是本平台反复出现的假绿形态；"
            "守卫必须真去读 backend/wp_templates 下的文件重算",
    ),
    Mutation(
        id="M26",
        side="be",
        path=CONTRACT,
        kind="delete",
        anchor='      "未宣称 operation 回写 / merge / rematerialize 已实现（Task 61/68 承接）",',
        want="test_contract_does_not_claim_downstream_task_deliverables",
        why="删掉「未宣称 operation 回写已实现」这条非声明 —— Task 6 正文明确要求不得提前自证，"
            "非声明清单被删就等于默许越权",
    ),
    Mutation(
        id="M27",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='    "oo_build": "9.4.0-129",',
        new='    "oo_build": "8.1.0-1",',
        want="test_environment_records_stale_policy_inputs",
        why="把 OO build 号改成另一个版本 —— Requirement 14.16 要求 build 可核；"
            "守卫必须回 oo_build.json 的 dpkg 输出里找这个串",
        scope_check=_nested_field_is(("environment", "oo_build"), "8.1.0-1"),
    ),
    Mutation(
        id="M28",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "has_tables": true,',
        new='      "has_tables": false,',
        want="test_declared_operations_are_fully_covered",
        wants=("test_pilot_row_carrier_gap_is_backed_by_template_facts",),
        why="把唯一有表格的取证文档标成无表格 ⇒ 行载体取证的前提消失；"
            "守卫必须与 evidence coverage 及 instrumentation 的 tables 事实交叉核对",
    ),
    # ================= evidence 侧：实证变了但契约没重新裁决 =================
    Mutation(
        id="M29",
        side="be",
        path=MATRIX,
        kind="replace",
        scope='      "artifact_file": "artifacts/b30112_edit_in_sdt_cb02_status6.docx",',
        offset=17,
        anchor='          "tag_set_not_reduced": false,',
        new='          "tag_set_not_reduced": true,',
        want="test_evidence_derived_verdict_flags_agree_with_their_own_raw_measurements",
        why="伪造 evidence：把 b30112 baseline 格（文件名带 mark 标签 edit_in_sdt，effective op "
            "是 baseline）的 tag_set_not_reduced 翻成 true，同时保留 tags_present 不变。"
            "首轮这条是 ERROR（并发自撞），二轮是 GREEN —— 因为所有裁决都绕开这个布尔直接重数，"
            "布尔本身反而没人校验，evidence 可以自相矛盾地躺着而下游会读它。"
            "已补 test_evidence_derived_verdict_flags_agree_with_their_own_raw_measurements 收口",
        scope_check=_matrix_row_field(
            "b30112_edit_in_sdt_cb02_status6.docx",
            ("carriers", "w_tag", "tag_set_not_reduced"),
            True,
        ),
    ),
    Mutation(
        id="M30",
        side="be",
        path=MATRIX,
        kind="replace",
        anchor='    "b30112/delete_row": [',
        new='    "b30112/delete_row_TYPO": [',
        want="test_user_row_delete_is_not_counted_as_carrier_loss",
        why="把有意删除的声明键改名 ⇒ 键定位不到任何 doc/op 格，等于没声明，删行会被重新算成"
            "载体失效。首轮实测这条是 GREEN（守卫只断言字典非空），已补键可解析 + 逐行 "
            "intentionally_removed_injections 对齐两道判据收口",
        scope_check=lambda data: "b30112/delete_row_TYPO" in json.loads(data.decode("utf-8"))["intentional_deletions"],
    ),
    Mutation(
        id="M31",
        side="be",
        path=MATRIX,
        kind="replace",
        anchor='  "op_label_policy": "op 以 callback 的 userdata 为权威（发 forcesave 时写死），probe mark 只作兜底；两者不一致时保留 marked_op 与 op_label_disagreed_with_mark 供审计",',
        new='  "op_label_policy": "op 以 probe mark 为准",',
        want="test_op_label_policy_statement_matches_observed_label_sources",
        why="把标签政策自述改成「以 probe mark 为准」，而 17 行仍标 op_label_source="
            "callback_userdata ⇒ 自述与逐行事实直接矛盾。首轮实测这条是 GREEN（守卫只按行校验、"
            "不校验自述），已补 test_op_label_policy_statement_matches_observed_label_sources 收口",
        scope_check=_nested_field_is(("op_label_policy",), "op 以 probe mark 为准"),
    ),
    Mutation(
        id="M32",
        side="be",
        path=MATRIX,
        kind="replace",
        scope='      "artifact_file": "artifacts/f222_insert_paragraph_cb05_status6.docx",',
        offset=-10,
        anchor='      "op": "insert_paragraph",',
        new='      "op": "insert_paragraph_renamed",',
        want="test_declared_operations_are_fully_covered",
        wants=("test_paragraph_index_anchor_is_disproven_by_evidence",),
        why="把段落序号反例那一格的 op 改名 ⇒ 契约声明的反例定位不到；"
            "同时该文档声明的 insert_paragraph 变成未覆盖",
    ),
    Mutation(
        id="M33",
        side="be",
        path=INSTRUMENTATION,
        kind="replace",
        anchor='            "run_split": 3,',
        new='            "run_split": 1,',
        want="test_cross_run_injection_really_spans_multiple_runs",
        wants=("test_run_index_anchor_is_disproven_by_evidence",
               "test_requirement_7_5_scenarios_are_pinned_to_named_injections"),
        why="把 cross_run 注入的 run_split 改成 1 ⇒ 名字叫跨 run 实际是单 run，"
            "Requirement 7.5 的跨 run 场景就没被真正取证",
    ),
    Mutation(
        id="M34",
        side="be",
        path=INSTRUMENTATION,
        kind="replace",
        scope='            "run_split": 3,',
        offset=-2,
        anchor='            "scenario": "cross_run",',
        new='            "scenario": "single_run",',
        want="test_requirement_7_5_scenarios_are_pinned_to_named_injections",
        why="抹掉 f222/F02 的 cross_run 场景标记。首轮实测这条是 GREEN —— 因为 f223/G02 也贡献"
            "同名场景，全局集合判据照样通过；已补按 (doc, inj_id, run_split) 逐条钉住的判据收口",
    ),
    Mutation(
        id="M35",
        side="be",
        path=INSTRUMENTATION,
        kind="replace",
        scope='        "doc": "b30112",',
        offset=5,
        anchor='        "lock_policy": "no_w_lock_injected",',
        new='        "lock_policy": "w_lock_sdtLocked_injected",',
        want="test_lock_policy_is_no_lock_and_matches_instrumentation",
        why="evidence 侧改 lock 策略（只改 b30112 那份 manifest）⇒ 与契约声明不一致；"
            "守卫两侧都比，且最终落到 staging docx 里 <w:lock 的真实存在性",
    ),
    Mutation(
        id="M37",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        {"doc": "f222", "inj_id": "F02", "run_split": 3},',
        new='        {"doc": "f222", "inj_id": "F08", "run_split": 3},',
        want="test_requirement_7_5_scenarios_are_pinned_to_named_injections",
        why="新增声明块本身也要有反向锁：把 cross_run 的注入 id 指到 F08（实测是 single_run "
            "且 run_split=1）⇒ 契约声明与 instrumentation 逐条对不上，必须打红。"
            "没有这条，新加的 requirement_7_5_scenarios 就是一段没人锁的自由文本",
        scope_check=_nested_field_is(
            ("requirement_7_5_scenarios", "instrumented", "cross_run"),
            [
                {"doc": "f222", "inj_id": "F08", "run_split": 3},
                {"doc": "f223", "inj_id": "G02", "run_split": 2},
            ],
        ),
    ),
    Mutation(
        id="M38",
        side="be",
        path=CONTRACT,
        kind="delete",
        # F03 那行在 same_paragraph_multi 与 duplicate_instance 里字面完全相同 ⇒ 必须给 scope，
        # 否则锚点命中 2 次直接 ANCHOR-MISS。删带尾逗号的首元素才能保持 JSON 合法（删末元素
        # 会留下悬空逗号，守卫会以 json 解析异常变成 ERROR 而不是 RED）。
        scope='      "same_paragraph_multi": [',
        offset=1,
        anchor='        {"doc": "f222", "inj_id": "F03", "run_split": 1},',
        want="test_requirement_7_5_scenarios_are_pinned_to_named_injections",
        why="从 same_paragraph_multi 的声明里删掉一条注入 ⇒ 声明比实证少一条。"
            "锁的是「逐条相等」而不是「至少一条」——后者会让同段多 token 只证一半",
        scope_check=lambda data: [
            d["inj_id"]
            for d in json.loads(data.decode("utf-8"))["requirement_7_5_scenarios"][
                "instrumented"
            ]["same_paragraph_multi"]
        ]
        == ["F04"],
    ),
    Mutation(
        id="M36",
        side="be",
        path=SOURCE_SHA_AFTER,
        kind="replace",
        anchor='      "sha256": "f19aa64a9daa01022231d91f43d342a4ae973088dbd42b58459ad65c206662ba",',
        new='      "sha256": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",',
        want="test_authority_templates_were_not_modified_by_the_probe",
        wants=("test_template_shas_match_readonly_authority_source",),
        why="伪造收工快照，制造「权威模板被探针改过」的形态 ⇒ 必须打红。"
            "这条同时证明 before/after 自证不是摆设",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 6 Word tagged SDT 载体守卫变异检验",
            backend_args=[
                "backend/tests/test_workpaper_word_sdt_carrier_contract.py",
                "-q",
                "--tb=no",
                "-rf",
            ],
            baseline_backend_passed=36,
        )
    )
