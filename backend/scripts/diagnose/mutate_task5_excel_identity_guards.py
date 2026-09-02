"""Task 5 守卫变异检验：Excel identity 载体真值表 ↔ 真实 OO 9.4 实证互锁。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure Task 5
Requirements 6.13 / 6.14 / 6.15 / 6.16 / 6.17 / 14.7 · Property 66

走 `backend/scripts/_mutation_kit` 共享件（`guard_files` 覆盖面分母、声明期锚点校验、
四态判定 RED/GREEN/WRONG-TEST/ANCHOR-MISS、备份还原 md5 自证均由共享件提供）。

## 变异分两半（互锁的两个方向）

- **契约侧（M01–M24）**：改 `onlyoffice_excel_identity_carrier_contract.json` 的裁决 /
  期望值 —— 验证「手填 `probe_verdict: passed`、抹掉重复 UUID 期望、把 not_covered 改成
  passed」这类假绿必须被 evidence 反算打红。
- **evidence 侧（M25–M35）**：改 `operation_matrix.json` / `instrumentation_report.json` /
  `oo_normalization_attribution.json` / `source_template_sha_after.json` —— 验证「实证变了
  但契约没重新裁决」同样打红。

## 「不是一改就红」的反向证据

35 条全 RED 时需要独立证据说明守卫不是过敏。两条：

1. **爆炸半径** —— 每条变异只打红 1–3 例（守卫共 31 例，均值 1.06），且命中的正是
   声明的 `want`。若守卫过敏，一条变异会连带打红大片。
2. **守卫内自检** —— `test_negative_control_is_field_specific` 往 evidence 副本塞一个
   未知键并断言判据**保持通过**。这条放在守卫里而不是当 GREEN 对照变异，因为共享件
   把 GREEN 一律判成守卫缺陷（`verdict.py` 的四态定义），有意的 GREEN 会让 rc 恒为 1。

## 用法（仓库根）

    python backend/scripts/diagnose/mutate_task5_excel_identity_guards.py --list
    python backend/scripts/diagnose/mutate_task5_excel_identity_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task5_excel_identity_guards.py --run all --out <evidence>/mutation_report.json
    python backend/scripts/diagnose/mutate_task5_excel_identity_guards.py --run M01,M25

只碰契约 JSON 与 evidence JSON；不动生产代码、不写业务库、不发网络请求。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

CONTRACT = "backend/data/onlyoffice_excel_identity_carrier_contract.json"
_EV = ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task5-oo94-excel-identity"
MATRIX = f"{_EV}/operation_matrix.json"
INSTRUMENTATION = f"{_EV}/instrumentation_report.json"
ATTRIBUTION = f"{_EV}/oo_normalization_attribution.json"
SOURCE_SHA_AFTER = f"{_EV}/source_template_sha_after.json"

#: 覆盖面分母：本 spec Task 5 新建的守卫文件。
GUARD_FILES = {
    "test_workpaper_excel_identity_carrier_contract.py": "Task 5 新建（载体真值表 ↔ 实证互锁）",
}


# ---------------------------------------------------------------------------
# 作用域自证（Property 24 口径）：确认变异确实落在被测结构里，而不是同名注释/说明
# ---------------------------------------------------------------------------


def _anchor_verdict_is(anchor_name: str, expected: str):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        item = next((a for a in payload["anchors"] if a["anchor"] == anchor_name), None)
        return item is not None and item["probe_verdict"] == expected

    return check


def _carrier_field_is(carrier: str, field: str, expected: object):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        item = next((c for c in payload["carriers"] if c["carrier"] == carrier), None)
        return item is not None and item.get(field) == expected

    return check


def _per_op_field_is(op: str, field: str, expected: object):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        carrier = next(c for c in payload["carriers"] if c["carrier"] == "hidden_uuid_column")
        row = next((e for e in carrier["per_operation_expectations"] if e["op"] == op), None)
        return row is not None and row.get(field) == expected

    return check


def _matrix_row_field(artifact: str, path: tuple[str, ...], expected: object):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        row = next(
            (r for r in payload["matrix"] if r.get("artifact_file", "").endswith(artifact)), None
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
    # ================= 契约侧：裁决被手填成通过 =================
    Mutation(
        id="M01",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='      "anchor": "sheet_id",',
        offset=2,
        anchor='      "probe_verdict": "failed",',
        new='      "probe_verdict": "passed",',
        want="test_sheet_id_anchor_is_disproven_by_evidence",
        wants=("test_every_carrier_and_anchor_has_machine_readable_verdict",
               "test_downstream_gate_lists_exactly_the_passed_items"),
        why="把已被 15/15 artifact 证伪的 sheetId 锚点改成 passed —— 这是本任务最贵的一条"
            "反向锁；若守卫放过，Task 17 就会拿一个每次保存都被 OO 重编号的值当 identity 锚点",
        scope_check=_anchor_verdict_is("sheet_id", "passed"),
    ),
    Mutation(
        id="M02",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        "sheet_id_anchor_holds_in_oo_artifacts": 0,',
        new='        "sheet_id_anchor_holds_in_oo_artifacts": 15,',
        want="test_sheet_id_anchor_is_disproven_by_evidence",
        why="证伪计数从实测 0 谎报成 15；守卫必须从 operation_matrix 重新数而不是采信契约数字",
    ),
    Mutation(
        id="M03",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        "resolvable_after_rename": false,',
        new='        "resolvable_after_rename": true,',
        want="test_sheet_display_name_anchor_is_disproven_by_evidence",
        why="谎称 sheet 展示名在改名后仍可解析；实测 rename_sheet artifact 的 sheet_name "
            "候选是 resolvable=false，改名后按名定位必然失败",
    ),
    Mutation(
        id="M04",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='          "底稿目录": "1",',
        new='          "底稿目录": "3",',
        want="test_sheet_id_anchor_is_disproven_by_evidence",
        why="手改「OO 重编号后的 sheetId 映射」表；守卫按 artifact 的 sheet 顺序反算 1..N，"
            "手填一份好看的映射必须被拦",
    ),
    Mutation(
        id="M05",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='      "carrier": "excel_table",',
        offset=3,
        anchor='      "may_enter_task_17_36_37": true,',
        new='      "may_enter_task_17_36_37": false,',
        want="test_every_carrier_and_anchor_has_machine_readable_verdict",
        wants=("test_downstream_gate_lists_exactly_the_passed_items",),
        why="让准入布尔与 probe_verdict 脱钩（passed 却不许进 Task 17）—— 两处各写一份"
            "就会出现「读 verdict 的代码放行、读布尔的代码拦住」的分叉",
        scope_check=_carrier_field_is("excel_table", "may_enter_task_17_36_37", False),
    ),
    Mutation(
        id="M06",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='        "aspect": "pivot_table",',
        offset=1,
        anchor='        "probe_verdict": "not_covered",',
        new='        "probe_verdict": "passed",',
        want="test_not_covered_items_are_never_marked_passed",
        wants=("test_population_scan_backs_the_not_covered_claims",),
        why="把 pivot 的 not_covered 改成 passed —— 351 个真实模板里 0 个含 pivot 部件，"
            "没有任何实证；「推理冒充实证」正是 Task 5 明令禁止的",
    ),
    Mutation(
        id="M07",
        side="be",
        path=CONTRACT,
        kind="replace",
        scope='          "contract_action": "拒绝",',
        offset=1,
        anchor='          "probe_verdict": "not_covered",',
        new='          "probe_verdict": "passed",',
        want="test_requirement_6_15_classifications_are_backed_by_evidence",
        why="「用户在 OO 内手工删除 identity 列」未实操，只有结构投影判据；标 passed 会让"
            "Requirement 6.15 的拒绝分支缺实测却被当成已验证",
    ),
    # ================= 契约侧：逐操作 identity 期望被改错 =================
    Mutation(
        id="M08",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        {"op": "paste", "row_uuid_count": 18, "distinct": 17, "duplicates": ["GTROW-K11-0018"], "missing": ["GTROW-K11-0012", "GTROW-K11-0016"], "rows_without_uuid": 1},',
        new='        {"op": "paste", "row_uuid_count": 18, "distinct": 18, "duplicates": [], "missing": ["GTROW-K11-0012", "GTROW-K11-0016"], "rows_without_uuid": 1},',
        want="test_per_operation_uuid_expectations_match_evidence",
        wants=("test_requirement_6_15_classifications_are_backed_by_evidence",),
        why="抹掉 paste 造出的重复 UUID 期望 —— 这是 Requirement 6.15「复制行产生重复 UUID"
            "→ 结构冲突」唯一的实证，抹掉后该分支就没有判据了",
        scope_check=_per_op_field_is("paste", "duplicates", []),
    ),
    Mutation(
        id="M09",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        {"op": "insert_row", "row_uuid_count": 19, "distinct": 19, "duplicates": [], "missing": [], "rows_without_uuid": 1},',
        new='        {"op": "insert_row", "row_uuid_count": 19, "distinct": 19, "duplicates": [], "missing": [], "rows_without_uuid": 0},',
        want="test_per_operation_uuid_expectations_match_evidence",
        why="把「新增行无 UUID」的判据改成 0 —— 该判据 = Table ref 覆盖行数 − 非空 UUID 数，"
            "守卫必须自己从 ref 算，不能采信契约数字",
        scope_check=_per_op_field_is("insert_row", "rows_without_uuid", 0),
    ),
    Mutation(
        id="M10",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        {"op": "delete_row", "row_uuid_count": 18, "distinct": 18, "duplicates": [], "missing": ["GTROW-K11-0012"], "rows_without_uuid": 1},',
        new='        {"op": "delete_row", "row_uuid_count": 18, "distinct": 18, "duplicates": [], "missing": [], "rows_without_uuid": 1},',
        want="test_per_operation_uuid_expectations_match_evidence",
        why="抹掉删除行导致的缺失 UUID —— 若守卫只看个数（18）就会放过，必须逐 UUID 值比对",
        scope_check=_per_op_field_is("delete_row", "missing", []),
    ),
    Mutation(
        id="M11",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        "ref_expands_on_row_insert": "A7:N25 -> A7:N26",',
        new='        "ref_expands_on_row_insert": "A7:N25 -> A7:N27",',
        want="test_excel_table_carrier_verdict_matches_evidence",
        why="改 Table ref 随插行扩张的声明；守卫按 edit/insert_row 两个 artifact 的实测 ref "
            "反算，手填的箭头两端必须都能对上",
    ),
    Mutation(
        id="M12",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        "after": {"7": "GTROW-K11-0014", "8": "GTROW-K11-0018", "9": "GTROW-K11-0020"},',
        new='        "after": {"7": "GTROW-K11-0007", "8": "GTROW-K11-0008", "9": "GTROW-K11-0009"},',
        want="test_sort_moves_uuids_with_their_rows",
        why="把排序取证的行号→UUID 映射改回未排序形态 —— 排序判据是「映射改变且集合不变」，"
            "手填一份「没变」的映射必须被 artifact 实测打红",
    ),
    Mutation(
        id="M13",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        "gt_name_count": 4,',
        new='        "gt_name_count": 5,',
        want="test_defined_name_carrier_verdict_matches_evidence",
        why="GT defined name 个数谎报成 5（实测 4）；守卫必须从每个 artifact 的实测 count 反算",
    ),
    Mutation(
        id="M14",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "k11_diff_counts": {"business_values": 0, "formulas": 0, "styles": 0, "merges": 0, "protected_parts": 0},',
        new='      "k11_diff_counts": {"business_values": 1, "formulas": 0, "styles": 0, "merges": 0, "protected_parts": 0},',
        want="test_instrumentation_is_strictly_visible_equivalent",
        why="谎称 instrumentation 造成了 1 处业务值差异 —— Requirement 6.17 的严格等价必须"
            "由 instrumentation_report 的 diff_count 逐项支撑，不接受契约自述",
    ),
    Mutation(
        id="M15",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        "case_B_pristine_through_oo": {"business_values": 1, "formulas": 0, "styles": 487, "merges": 0, "protected_parts": 1},',
        new='        "case_B_pristine_through_oo": {"business_values": 1, "formulas": 0, "styles": 0, "merges": 0, "protected_parts": 1},',
        want="test_oo_normalization_is_attributed_to_oo_not_instrumentation",
        why="把控制组 B 的 styles 规模抹成 0，会让「OO 归一化与 instrumentation 无关」的"
            "归因结论失去数量支撑（B==C 是该结论的全部依据）",
    ),
    Mutation(
        id="M16",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='          "occurs_without_instrumentation": true,',
        new='          "occurs_without_instrumentation": false,',
        want="test_oo_roundtrip_is_not_claimed_byte_equivalent",
        why="谎称字体替换（宋体→Calibri）只在 instrumentation 后出现 —— 与控制组 B 的实测"
            "直接矛盾，会把一个部署层问题错记成 instrumentation 的副作用",
    ),
    Mutation(
        id="M17",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "verdict": "not_byte_equivalent_by_design",',
        new='      "verdict": "equivalent",',
        want="test_oo_roundtrip_is_not_claimed_byte_equivalent",
        why="把 OO 往返宣称成字节等价 —— 下游若按字节口径判等值，每次 OO 保存都会误判成"
            "结构漂移（chart/drawing 部件字节必被重写）",
    ),
    Mutation(
        id="M18",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "command_service_error": 4',
        new='      "command_service_error": 0',
        want="test_copy_has_no_artifact_because_oo_refused_forcesave",
        why="copy 那一格「无 artifact」的唯一支撑是 Command Service 实测返回 error 4；"
            "改成 0 就等于把覆盖缺口说成正常结果",
    ),
    Mutation(
        id="M19",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "artifact_produced": false,',
        new='      "artifact_produced": true,',
        want="test_declared_operations_all_have_real_oo_evidence",
        why="谎称 copy 产出了 artifact，而 evidence 里没有 —— 声明有 artifact 却查不到，"
            "正是「某操作其实没测」的伪装形态",
    ),
    Mutation(
        id="M20",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "both_paths_preserve_all_carriers": true',
        new='      "both_paths_preserve_all_carriers": false',
        want="test_download_covers_both_serialisation_paths",
        why="download 覆盖 callback status 2 与编辑器下载两条独立序列化路径，结论翻成 false "
            "却仍标 passed，会让下游以为下载路径有载体丢失风险而绕开",
    ),
    Mutation(
        id="M21",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "operations_not_covered": ["insert_row", "delete_row", "sort", "copy", "paste", "rename_sheet"],',
        new='      "operations_not_covered": [],',
        want="test_c24_partial_operation_coverage_is_declared",
        why="清空 C24 的未覆盖操作声明 = 把「只跑了 4 个操作」伪装成全覆盖；"
            "Task 5 要求未覆盖必须如实记录",
    ),
    Mutation(
        id="M22",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='      "template_sha256": "dc0e5434b7c8e345913864ce524ad30a0a3729b5655627f3c30bce52294a9190",',
        new='      "template_sha256": "dc0e5434b7c8e345913864ce524ad30a0a3729b5655627f3c30bce52294a9191",',
        want="test_probed_templates_are_platform_authoritative_and_unmodified",
        why="改契约记录的源模板 sha256 —— 它必须与开工/收工两次实测都一致，否则「探针用的"
            "就是权威模板且没改过它」这条无法复核",
    ),
    Mutation(
        id="M23",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='    "with_pivot_parts": 0,',
        new='    "with_pivot_parts": 7,',
        want="test_population_scan_backs_the_not_covered_claims",
        why="谎称总体里有 7 个含 pivot 的模板 —— pivot 判 not_covered 的理由就是「0 个」，"
            "数字一改理由就不成立，必须同时重新裁决",
    ),
    Mutation(
        id="M24",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='    "66": "Excel identity 经真实 OO 往返保留 —— 三类载体在 10 个操作上的 identity inventory 期望由 carriers[].per_operation_expectations 与 operation_matrix.json 双向互锁；sheet_id 锚点被证伪并固定为 failed，阻断以它为前提的 engine 建设。"',
        new='    "66": "Excel identity 经真实 OO 往返保留 —— 三类载体在 10 个操作上的 identity inventory 期望由 carriers[].per_operation_expectations 与 operation_matrix.json 双向互锁。"',
        want="test_property_66_gate_is_registered",
        why="从 Property 66 登记里删掉「sheetId 被证伪」——「任一缺失阻断 engine gate」的"
            "阻断对象正是它，删掉就等于 Property 66 少了一半结论",
    ),
    # ================= evidence 侧：实证被篡改 =================
    Mutation(
        id="M25",
        side="be",
        path=MATRIX,
        kind="replace",
        scope='      "artifact_sha256": "45844defd27e179a1dfd86add9e7746633335923ef095953374bd07385a8124f",',
        offset=106,
        anchor='          "sheet_id_anchor_holds": false,',
        new='          "sheet_id_anchor_holds": true,',
        want="test_sheet_id_anchor_is_disproven_by_evidence",
        why="让 k11/edit 那条实证的 sheetId 锚点变成成立 —— 若 OO 行为真的变了，契约的 "
            "failed 裁决必须重新做；守卫不能只信契约一侧",
        scope_check=_matrix_row_field(
            "k11_edit_cb02_status6.xlsx", ("carriers", "hidden_uuid_column", "sheet_id_anchor_holds"), True
        ),
    ),
    Mutation(
        id="M26",
        side="be",
        path=MATRIX,
        kind="replace",
        scope='      "artifact_sha256": "45844defd27e179a1dfd86add9e7746633335923ef095953374bd07385a8124f",',
        offset=17,
        anchor='          "present": true,',
        new='          "present": false,',
        want="test_hidden_sheet_carrier_verdict_matches_evidence",
        why="抹掉 k11/edit 实证里 `_GT_SYNC` 的存在 —— hidden_sheet 的 passed 裁决必须由"
            "每个 artifact 的 present 反算，一处为假即不能维持 passed",
        scope_check=_matrix_row_field(
            "k11_edit_cb02_status6.xlsx", ("carriers", "hidden_sheet", "present"), False
        ),
    ),
    Mutation(
        id="M27",
        side="be",
        path=MATRIX,
        kind="replace",
        scope='      "artifact_sha256": "45844defd27e179a1dfd86add9e7746633335923ef095953374bd07385a8124f",',
        offset=146,
        anchor='      "collection_errors": [],',
        new='      "collection_errors": ["ERROR FingerprintError: 注入的采集失败"],',
        want="test_no_collection_errors_anywhere",
        why="🔴 禁止 fail-open 的判据：采集异常必须打红。若守卫只看 carriers 字段而不看"
            "collection_errors，「采集器坏了」就会和「载体确实在」得到同一个绿色结论",
        scope_check=_matrix_row_field(
            "k11_edit_cb02_status6.xlsx",
            ("collection_errors",),
            ["ERROR FingerprintError: 注入的采集失败"],
        ),
    ),
    Mutation(
        id="M28",
        side="be",
        path=INSTRUMENTATION,
        kind="replace",
        scope='      "template_sha256": "dc0e5434b7c8e345913864ce524ad30a0a3729b5655627f3c30bce52294a9190",',
        offset=413,
        anchor='          "business_values": true,',
        new='          "business_values": false,',
        want="test_instrumentation_is_strictly_visible_equivalent",
        why="让 K11 的 instrumentation 等价报告出现一个 false aspect —— Requirement 6.17 的"
            "严格等价必须逐 aspect 校验，只看顶层 `equivalent` 会漏",
    ),
    Mutation(
        id="M29",
        side="be",
        path=ATTRIBUTION,
        kind="replace",
        anchor='    "instrumentation_contributes_zero_diffs": true,',
        new='    "instrumentation_contributes_zero_diffs": false,',
        want="test_oo_normalization_is_attributed_to_oo_not_instrumentation",
        why="翻转归因结论 —— 若 instrumentation 真有贡献，「OO 往返差异与 instrumentation "
            "无关」这条就不成立，契约的 oo_roundtrip 小节必须重写",
    ),
    Mutation(
        id="M30",
        side="be",
        path=SOURCE_SHA_AFTER,
        kind="replace",
        anchor='      "sha256": "dc0e5434b7c8e345913864ce524ad30a0a3729b5655627f3c30bce52294a9190",',
        new='      "sha256": "0000000000000000000000000000000000000000000000000000000000000000",',
        want="test_probed_templates_are_platform_authoritative_and_unmodified",
        why="模拟收工时发现权威模板 sha256 已漂移 —— `backend/wp_templates/` 被改动是本任务"
            "的红线，守卫必须把 before/after 两次快照都比一遍",
    ),
    Mutation(
        id="M31",
        side="be",
        path=MATRIX,
        kind="replace",
        scope='      "artifact_sha256": "4ac224e250c34cba122a6fed7605e12b7790064885247382a65f8d8502b6c519",',
        offset=35,
        anchor="            \"GT_MANAGED_REGION_K11\": \"'审定表K11-1改名后'!$A$7:$L$25\",",
        new="            \"GT_MANAGED_REGION_K11\": \"'审定表K11-1'!$A$7:$L$25\",",
        want="test_defined_name_ref_auto_tracks_sheet_rename",
        why="让改名后的 defined name ref 停留在旧 sheet 名 —— defined name 能当锚点的全部"
            "理由就是 OO 会自动改写 ref；不改写它就和 sheet 展示名一样不可用",
        scope_check=_matrix_row_field(
            "k11_rename_sheet_cb07_status6.xlsx",
            ("carriers", "defined_name", "refs", "GT_MANAGED_REGION_K11"),
            "'审定表K11-1'!$A$7:$L$25",
        ),
    ),
    Mutation(
        id="M32",
        side="be",
        path=MATRIX,
        kind="replace",
        scope='      "artifact_sha256": "4ac224e250c34cba122a6fed7605e12b7790064885247382a65f8d8502b6c519",',
        offset=102,
        anchor='              "row_uuid_count": 18,',
        new='              "row_uuid_count": 0,',
        want="test_excel_table_is_the_surviving_anchor_after_rename",
        why="让改名后 Table 路径也定位不到 UUID —— 那就意味着三条锚点全废、没有任何可用"
            "定位方式，Table 载体的 passed 裁决必须改 failed",
    ),
    Mutation(
        id="M33",
        side="be",
        path=MATRIX,
        kind="replace",
        scope='      "artifact_sha256": "7b3061f91e963b126a351c4bff6b5c909fdeb0801eb0acb6e770dfe7acff3a58",',
        offset=123,
        anchor='        "chart": 8,',
        new='        "chart": 0,',
        want="test_protected_parts_count_never_decreases_through_oo",
        why="让 C24 的 chart 部件数掉到 0 —— Requirement 6.17 的受保护部件判据是「计数不减少」，"
            "chart 归零必须打红（C24 是全平台唯一含 chart 的模板，丢了就无从取证）",
        scope_check=_matrix_row_field(
            "c24_edit_cb02_status6.xlsx", ("protected_parts", "chart"), 0
        ),
    ),
    Mutation(
        id="M34",
        side="be",
        path=MATRIX,
        kind="replace",
        scope='      "artifact_sha256": "64820f83a361c17df69f23b2a05f2c12ae63a0ea95550e7725c9daecf2668a8f",',
        offset=114,
        anchor='            "7": "GTROW-K11-0014",',
        new='            "7": "GTROW-K11-0007",',
        want="test_sort_moves_uuids_with_their_rows",
        wants=("test_per_operation_uuid_expectations_match_evidence",),
        why="把排序后第 7 行的 UUID 改成排序前的值 —— 制造重复 UUID 并让契约声明的排序"
            "映射对不上；验证「UUID 随行迁移」不是靠个数、而是靠逐行映射判定",
        scope_check=_matrix_row_field(
            "k11_sort_cb05_status6.xlsx",
            ("carriers", "hidden_uuid_column", "row_uuids", "7"),
            "GTROW-K11-0007",
        ),
    ),
    Mutation(
        id="M35",
        side="be",
        path=INSTRUMENTATION,
        kind="replace",
        scope='      "template_sha256": "dc0e5434b7c8e345913864ce524ad30a0a3729b5655627f3c30bce52294a9190",',
        offset=139,
        anchor='          "present": false,',
        new='          "present": true,',
        want="test_instrumentation_adds_nothing_beyond_the_declared_whitelist",
        why="毁掉负对照：谎称 instrumentation **之前**模板就自带 `_GT_SYNC`。若守卫不看"
            "注入前快照，就无法区分「载体是我注入的」与「模板本来就有」，"
            "整个 instrumentation 等价结论都失去意义",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 5 Excel identity 载体真值表 ↔ 真实 OO 实证互锁 变异检验",
            backend_args=[
                "backend/tests/test_workpaper_excel_identity_carrier_contract.py",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:cacheprovider",
            ],
            baseline_backend_passed=31,
        )
    )
