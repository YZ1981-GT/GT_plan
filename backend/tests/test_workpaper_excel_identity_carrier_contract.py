"""Task 5 guard：Excel identity 载体真值表 ↔ 真实 OO 9.4 实证互锁。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure Task 5
Requirements 6.13 / 6.14 / 6.15 / 6.16 / 6.17 / 14.5 / 14.16
Property 66（Excel identity 经真实 OO 往返保留）的判据。

为什么必须双向互锁（而不是只做 JSON schema 校验）：
  单验 schema 属于「守卫把字符串存在当判据」的假绿第②源 —— 手填
  `probe_verdict: passed` 也能过。故本文件的每一条裁决都从 evidence 目录的
  `operation_matrix.json` / `instrumentation_report.json` / `oo_normalization_attribution.json`
  **重新计算**，契约值与实证值不一致即红：
    - 改契约（把 failed 改 passed、把 not_covered 改 passed、改 per-op UUID 期望）→ 红
    - 改实证（重跑探针得到不同 OO 行为）→ 红，必须重新裁决契约

evidence 由 `backend/scripts/diagnose/probe_oo94_excel_identity.py` 在真实
OnlyOffice 9.4.0-129 容器上采集（平台自有真实模板 K11 / C24，Playwright 驱动真实编辑器）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
_CONTRACT_PATH = _REPO / "backend" / "data" / "onlyoffice_excel_identity_carrier_contract.json"
_EVIDENCE_DIR = (
    _REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence"
    / "task5-oo94-excel-identity"
)

_VERDICTS = {"passed", "partial", "failed", "not_covered"}
_DECLARED_OPS = {
    "edit",
    "insert_row",
    "delete_row",
    "sort",
    "copy",
    "paste",
    "rename_sheet",
    "forcesave",
    "download",
    "reopen",
}
#: design §Identity probe 决策门列出的三类 Excel 候选载体（`hidden_uuid_column` 在本任务
#: 被拆成 `excel_table` + `hidden_uuid_column` 两条，因为二者是可独立成败的不同部件）。
_REQUIRED_CARRIERS = {"hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column"}
_REQUIRED_ANCHORS = {
    "sheet_id",
    "sheet_display_name",
    "defined_name_ref",
    "excel_table_sheet_association",
}
_EQUIVALENCE_ASPECTS = (
    "visible_sheets",
    "business_values",
    "formulas",
    "styles",
    "merges",
    "protected_parts",
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix() -> dict[str, Any]:
    path = _EVIDENCE_DIR / "operation_matrix.json"
    assert path.exists(), f"缺少真实 OO 操作矩阵 evidence: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["matrix"], "operation_matrix.json 为空：契约的 probe_verdict 无实证支撑"
    return data


@pytest.fixture(scope="module")
def rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    return matrix["matrix"]


@pytest.fixture(scope="module")
def k11_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("doc") == "k11"]


@pytest.fixture(scope="module")
def instrumentation() -> dict[str, Any]:
    path = _EVIDENCE_DIR / "instrumentation_report.json"
    assert path.exists(), f"缺少 instrumentation evidence: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def attribution() -> dict[str, Any]:
    path = _EVIDENCE_DIR / "oo_normalization_attribution.json"
    assert path.exists(), f"缺少归因控制组 evidence: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def carriers(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["carrier"]: c for c in contract["carriers"]}


@pytest.fixture(scope="module")
def anchors(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {a["anchor"]: a for a in contract["anchors"]}


def _rows_in_ref(ref: str | None) -> int:
    """`A7:N26` → 20（Table ref 覆盖的行数）。"""
    if not ref:
        return 0
    start, end = ref.split(":")
    first = int(re.search(r"(\d+)$", start).group(1))
    last = int(re.search(r"(\d+)$", end).group(1))
    return last - first + 1


# ---------------------------------------------------------------------------
# A. 契约自身结构（Requirement 14.16 版本化 + 可复核）
# ---------------------------------------------------------------------------


def test_contract_is_versioned_and_complete(contract: dict[str, Any]) -> None:
    assert contract["contract_id"] == "onlyoffice_excel_identity_carrier_contract"
    assert contract["schema_version"] == 1, "真值表必须版本化；schema_version 变化需同步 guard"
    for section in (
        "verdict_enum",
        "evidence",
        "templates_probed",
        "template_population_scan",
        "carriers",
        "anchors",
        "operation_matrix_declared",
        "operation_notes",
        "visible_equivalence",
        "gate_for_downstream_tasks",
        "properties_gated",
    ):
        assert section in contract, f"真值表缺少必需小节: {section}"
    assert set(contract["verdict_enum"]) == _VERDICTS
    assert set(contract["operation_matrix_declared"]) == _DECLARED_OPS, (
        "声明的操作矩阵必须与 Task 5 要求的 10 个操作一致"
    )


def test_every_carrier_and_anchor_has_machine_readable_verdict(
    carriers: dict[str, dict[str, Any]], anchors: dict[str, dict[str, Any]]
) -> None:
    """Task 5 硬要求：失败载体必须机器可读，让 Task 17 loader fail-closed 读它。"""
    assert set(carriers) == _REQUIRED_CARRIERS, f"载体覆盖不全: {sorted(carriers)}"
    assert set(anchors) == _REQUIRED_ANCHORS, f"锚点覆盖不全: {sorted(anchors)}"
    for name, item in list(carriers.items()) + list(anchors.items()):
        assert item["probe_verdict"] in _VERDICTS, f"{name}: 非法 probe_verdict"
        assert isinstance(item["may_enter_task_17_36_37"], bool), f"{name}: 缺少准入布尔"
        # 准入布尔必须由 verdict 推出，不能各自为政。
        assert item["may_enter_task_17_36_37"] is (item["probe_verdict"] == "passed"), (
            f"{name}: probe_verdict={item['probe_verdict']} 与准入布尔"
            f" {item['may_enter_task_17_36_37']} 矛盾"
        )
        if item["probe_verdict"] == "failed":
            assert item.get("disproof"), f"{name}: failed 必须给出证伪实证"
            assert item.get("forbidden"), f"{name}: failed 必须列出禁止做法"


def test_downstream_gate_lists_exactly_the_passed_items(
    contract: dict[str, Any], carriers: dict[str, dict[str, Any]], anchors: dict[str, dict[str, Any]]
) -> None:
    """Task 17/36/37 的准入名单必须由 verdict 推导，不得手写第二份。"""
    gate = contract["gate_for_downstream_tasks"]["task_17_instrumentation_definition"]
    passed_carriers = {k for k, v in carriers.items() if v["probe_verdict"] == "passed"}
    passed_anchors = {k for k, v in anchors.items() if v["probe_verdict"] == "passed"}
    failed_anchors = {k for k, v in anchors.items() if v["probe_verdict"] != "passed"}
    assert set(gate["allowed_carriers"]) == passed_carriers
    assert set(gate["allowed_anchors"]) == passed_anchors
    assert set(gate["forbidden_anchors"]) == failed_anchors
    assert "fail closed" in gate["loader_rule"], "loader 规则必须写明 fail closed"
    assert contract["gate_for_downstream_tasks"]["stale_policy"]["invalidate_on"]


def test_evidence_pointers_resolve(contract: dict[str, Any]) -> None:
    evidence = contract["evidence"]
    base = _REPO / evidence["dir"]
    assert base.is_dir(), f"evidence 目录不存在: {base}"
    for key in (
        "findings",
        "instrumentation_report",
        "operation_matrix",
        "raw_callbacks",
        "raw_commands",
        "build",
        "source_sha_before",
        "source_sha_after",
        "attribution_report",
    ):
        assert (base / evidence[key]).exists(), f"evidence.{key} 指向的文件不存在"
    shots = base / evidence["screenshots"]
    assert shots.is_dir() and list(shots.glob("*.png")), (
        "截图目录缺失或为空 —— UI 侧结论（`_GT_SYNC` 不出现在标签栏、名称框显示 Table 名、"
        "改名后标签生效）失去可复核依据"
    )
    for key in ("probe_script", "reusable_module", "mutation_script"):
        assert (_REPO / evidence[key]).exists(), f"evidence.{key} 缺失，evidence 不可复现"
    assert evidence["onlyoffice_build"].startswith("9.4."), "实证必须来自 OO 9.4"
    build = json.loads((base / evidence["build"]).read_text(encoding="utf-8"))
    assert evidence["onlyoffice_build"] in build["dpkg_onlyoffice_documentserver"], (
        "契约记录的 build 与容器实测 dpkg 输出不一致"
    )


def test_probed_templates_are_platform_authoritative_and_unmodified(contract: dict[str, Any]) -> None:
    """Requirement 6.13：只能用 `backend/wp_templates/` 的平台自有模板，且权威源不得被改。"""
    before = json.loads((_EVIDENCE_DIR / "source_template_sha_before.json").read_text(encoding="utf-8"))
    after = json.loads((_EVIDENCE_DIR / "source_template_sha_after.json").read_text(encoding="utf-8"))
    assert not before["lock_files"] and not after["lock_files"], "wp_templates 存在 ~$ 锁文件，模板可能有未保存改动"
    for tpl in contract["templates_probed"]:
        rel = tpl["template_rel"]
        assert rel.startswith("backend/wp_templates/"), f"{rel} 不在运行时权威源目录"
        path = _REPO / rel
        assert path.exists(), f"模板不存在: {rel}"
        assert before["templates"][rel]["sha256"] == tpl["template_sha256"], (
            f"{rel}: 契约记录的 sha256 与开工时实测不一致"
        )
        assert after["templates"][rel]["sha256"] == tpl["template_sha256"], (
            f"{rel}: 收工时源文件 sha256 已漂移 —— 运行时权威模板被修改过"
        )


def test_population_scan_backs_the_not_covered_claims(contract: dict[str, Any]) -> None:
    """`pivot/vba = not_covered` 的理由是「总体里 0 个」，这个数字必须在契约里可核。"""
    scan = contract["template_population_scan"]
    assert scan["xlsx_total"] > 0 and scan["fingerprint_failures"] == 0
    assert scan["with_pivot_parts"] == 0
    assert scan["with_vba"] == 0
    assert scan["with_chart_parts"] >= 1, "含 chart 的模板数为 0 时，chart 结论也应改 not_covered"
    not_covered = {
        item["aspect"]: item
        for item in contract["visible_equivalence"]["not_covered"]
    }
    assert not_covered["pivot_table"]["probe_verdict"] == "not_covered"
    assert not_covered["vba_macro"]["probe_verdict"] == "not_covered"
    assert "0 个" in not_covered["pivot_table"]["reason"], "not_covered 理由必须引用总体扫描事实"


# ---------------------------------------------------------------------------
# B. 契约 ↔ 真实 OO 实证互锁（核心防假绿边）
# ---------------------------------------------------------------------------


def test_declared_operations_all_have_real_oo_evidence(
    contract: dict[str, Any], k11_rows: list[dict[str, Any]]
) -> None:
    """10 个操作里除显式声明无 artifact 者，每个都必须有真实 OO artifact。"""
    observed = {r["op"] for r in k11_rows}
    notes = contract["operation_notes"]
    for op in contract["operation_matrix_declared"]:
        if op in observed:
            continue
        note = notes.get(op)
        assert note is not None, f"操作 {op} 既无 artifact 也无 operation_notes 说明"
        assert note["artifact_produced"] is False, (
            f"操作 {op} 声明会产出 artifact，但 evidence 里没有 —— 覆盖缺口不得默认通过"
        )
        assert note.get("reason"), f"操作 {op} 无 artifact 必须给出原因"


def test_copy_has_no_artifact_because_oo_refused_forcesave(
    contract: dict[str, Any]
) -> None:
    """`copy` 那一格的「无 artifact」必须由 Command Service 真实返回码支撑。"""
    note = contract["operation_notes"]["copy"]
    expected_error = note["command_service_error"]
    commands = [
        json.loads(line)
        for line in (_EVIDENCE_DIR / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    copy_cmds = [c for c in commands if c.get("op") == "copy"]
    assert copy_cmds, "evidence 中没有 copy 操作的 Command Service 调用记录"
    bodies = [(c.get("result") or {}).get("body") for c in copy_cmds]
    errors = {b.get("error") for b in bodies if isinstance(b, dict)}
    assert errors == {expected_error}, (
        f"copy 的实测返回码 {errors} 与契约声明 {expected_error} 不一致"
    )


def test_consecutive_forcesave_without_changes_matches_contract(contract: dict[str, Any]) -> None:
    note = contract["operation_notes"]["forcesave"]
    commands = [
        json.loads(line)
        for line in (_EVIDENCE_DIR / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    repeats = [
        c
        for c in commands
        if str(c["request"].get("userdata") or "").endswith("repeat")
    ]
    assert repeats, "缺少「连续 forcesave 无新变更」实证"
    body = (repeats[0].get("result") or {}).get("body")
    assert isinstance(body, dict)
    assert body["error"] == note["consecutive_forcesave_without_changes"]


def test_hidden_sheet_carrier_verdict_matches_evidence(
    carriers: dict[str, dict[str, Any]], rows: list[dict[str, Any]]
) -> None:
    """hidden `_GT_SYNC` 载体：契约 passed 必须由每个 artifact 的实测反算支撑。"""
    carrier = carriers["hidden_sheet"]
    observed = carrier["observed"]
    present_all = all(r["carriers"]["hidden_sheet"]["present"] for r in rows)
    missing_total = sum(len(r["carriers"]["hidden_sheet"]["missing_keys"]) for r in rows)
    excluded_all = all(
        r["carriers"]["hidden_sheet"]["excluded_from_business_enumeration"] for r in rows
    )
    hidden_all = all("_GT_SYNC" in r["hidden_sheet_names"] for r in rows)
    assert observed["present_in_all_oo_artifacts"] is present_all
    assert observed["required_keys_missing_anywhere"] == missing_total
    assert observed["excluded_from_business_sheet_enumeration"] is excluded_all
    assert observed["state_stays_hidden"] is hidden_all
    expected_verdict = "passed" if (present_all and missing_total == 0 and excluded_all and hidden_all) else "failed"
    assert carrier["probe_verdict"] == expected_verdict, (
        f"hidden_sheet 契约裁决 {carrier['probe_verdict']} 与实证推出的 {expected_verdict} 不一致"
    )


def test_defined_name_carrier_verdict_matches_evidence(
    carriers: dict[str, dict[str, Any]], rows: list[dict[str, Any]]
) -> None:
    carrier = carriers["defined_name"]
    observed = carrier["observed"]
    missing_total = sum(len(r["carriers"]["defined_name"]["missing_names"]) for r in rows)
    assert observed["gt_names_missing_anywhere"] == missing_total
    counts = {r["carriers"]["defined_name"]["count"] for r in rows}
    assert counts == {observed["gt_name_count"]}, (
        f"GT defined name 个数实测 {sorted(counts)}，契约声明 {observed['gt_name_count']}"
    )
    assert carrier["probe_verdict"] == ("passed" if missing_total == 0 else "failed")
    # workbook 级与 sheet-local 两种 scope 都要真的出现过。
    scopes = {
        scope
        for r in rows
        for scope in r["carriers"]["defined_name"]["scopes"].values()
    }
    assert None in scopes, "实证中没有 workbook 级 defined name"
    assert any(s is not None for s in scopes), "实证中没有 sheet-local defined name"
    assert observed["workbook_scope_survives"] is True
    assert observed["sheet_local_scope_survives"] is True


def test_defined_name_ref_auto_tracks_sheet_rename(
    carriers: dict[str, dict[str, Any]], anchors: dict[str, dict[str, Any]], k11_rows: list[dict[str, Any]]
) -> None:
    """Requirement 6.14 的关键格：改名后 defined name 的 ref 是否仍指向正确 sheet。"""
    renamed = [r for r in k11_rows if r["op"] == "rename_sheet"]
    assert renamed, "缺少 sheet 改名 artifact —— 这一格是 Task 5 的关键项"
    refs = renamed[0]["carriers"]["defined_name"]["refs"]
    example = anchors["defined_name_ref"]["proof"]["example_after_rename"]
    new_sheet = example.split("!")[0].strip("'")
    business_refs = [ref for name, ref in refs.items() if not ref.startswith("_GT_SYNC")]
    assert business_refs, "改名后没有任何指向业务 sheet 的 GT defined name"
    assert all(new_sheet in ref for ref in business_refs), (
        f"改名后 ref 未同步到新 sheet 名 {new_sheet!r}: {business_refs}"
    )
    assert carriers["defined_name"]["observed"]["ref_auto_rewritten_on_sheet_rename"] is True
    assert anchors["defined_name_ref"]["probe_verdict"] == "passed"


def test_sheet_id_anchor_is_disproven_by_evidence(
    anchors: dict[str, dict[str, Any]], rows: list[dict[str, Any]]
) -> None:
    """🔴 sheetId 锚点必须被实证钉成 failed：OO 每次保存都重编号。

    这是本任务最重要的一条反向锁：如果有人把 `sheet_id` 改回 passed，本测试立刻打红。
    """
    anchor = anchors["sheet_id"]
    holds = [r["carriers"]["hidden_uuid_column"]["sheet_id_anchor_holds"] for r in rows]
    assert anchor["disproof"]["oo_artifacts_checked"] == len(rows), (
        f"契约声明核了 {anchor['disproof']['oo_artifacts_checked']} 个 artifact，实测 {len(rows)} 个"
    )
    assert anchor["disproof"]["sheet_id_anchor_holds_in_oo_artifacts"] == sum(1 for h in holds if h)
    assert not any(holds), (
        "存在 sheetId 锚点仍成立的 artifact —— 若 OO 行为已变，必须重新裁决 sheet_id"
    )
    assert anchor["probe_verdict"] == "failed"
    assert anchor["may_enter_task_17_36_37"] is False
    # 证伪表里的 sheetId 映射必须与实测 artifact 一致（防手填一份好看的映射）。
    declared_after = anchor["disproof"]["after_any_oo_save_sheet_ids"]
    sample = next(r for r in rows if r["doc"] == "k11")
    actual = {s: str(i + 1) for i, s in enumerate(sample["sheet_names"])}
    assert declared_after == actual, (
        f"契约声明的 OO 重编号结果与实测不符：{declared_after} vs {actual}"
    )
    first_op = anchor["disproof"]["first_failing_operation"]
    first_row = next(r for r in rows if r["op"] == first_op)
    assert first_row["carriers"]["hidden_uuid_column"]["sheet_id_anchor_holds"] is False


def test_sheet_display_name_anchor_is_disproven_by_evidence(
    anchors: dict[str, dict[str, Any]], k11_rows: list[dict[str, Any]]
) -> None:
    anchor = anchors["sheet_display_name"]
    renamed = next(r for r in k11_rows if r["op"] == "rename_sheet")
    candidates = renamed["carriers"]["hidden_uuid_column"]["sheet_resolution_candidates"]
    assert candidates["sheet_name"]["resolvable"] is anchor["disproof"]["resolvable_after_rename"]
    assert candidates["sheet_name"]["resolvable"] is False
    assert anchor["probe_verdict"] == "failed"
    assert anchor["disproof"]["renamed_to"] == candidates["table_sheet"]["resolved_sheet"], (
        "契约记录的新 sheet 名与实测 Table 归属 sheet 不一致"
    )


def test_excel_table_is_the_surviving_anchor_after_rename(
    carriers: dict[str, dict[str, Any]], anchors: dict[str, dict[str, Any]], k11_rows: list[dict[str, Any]]
) -> None:
    """改名后只有 Table 路径还能定位到 UUID 列 —— 这是 Table 载体的存在理由。"""
    renamed = next(r for r in k11_rows if r["op"] == "rename_sheet")
    candidates = renamed["carriers"]["hidden_uuid_column"]["sheet_resolution_candidates"]
    assert candidates["sheet_id"]["row_uuid_count"] == 0
    assert candidates["sheet_name"]["row_uuid_count"] == 0
    assert candidates["table_sheet"]["row_uuid_count"] > 0, (
        "改名后连 Table 路径都定位不到 UUID ⇒ 没有任何可用锚点，Table 裁决必须改 failed"
    )
    assert anchors["excel_table_sheet_association"]["probe_verdict"] == "passed"
    assert carriers["excel_table"]["observed"]["survives_sheet_rename"] is True


def test_excel_table_carrier_verdict_matches_evidence(
    carriers: dict[str, dict[str, Any]], k11_rows: list[dict[str, Any]], instrumentation: dict[str, Any]
) -> None:
    carrier = carriers["excel_table"]
    observed = carrier["observed"]
    expected_name = instrumentation["docs"]["k11"]["manifest"]["managed_table"]
    assert observed["table_display_name_stable"] == expected_name
    present = [r["carriers"]["excel_table"]["present"] for r in k11_rows]
    names = {r["carriers"]["excel_table"]["table_name"] for r in k11_rows}
    assert observed["table_present_in_all_k11_artifacts"] is all(present)
    assert names == {expected_name}, f"Table displayName 在往返中漂移: {names}"
    # headerRowCount=0 被 OO 接受：每个 artifact 都仍报告 header_row_count_zero。
    zero_header = [r["carriers"]["excel_table"]["header_row_count_zero"] for r in k11_rows]
    assert observed["header_row_count_zero_accepted_by_oo"] is all(zero_header)
    # ref 随插行扩张：契约声明的 "A7:N25 -> A7:N26" 必须与实测 insert_row 一致。
    declared = observed["ref_expands_on_row_insert"]
    before_ref, after_ref = [s.strip() for s in declared.split("->")]
    insert_row = next(r for r in k11_rows if r["op"] == "insert_row")
    edit_row = next(r for r in k11_rows if r["op"] == "edit")
    assert edit_row["carriers"]["excel_table"]["table_ref"] == before_ref
    assert insert_row["carriers"]["excel_table"]["table_ref"] == after_ref
    assert carrier["probe_verdict"] == ("passed" if all(present) else "failed")


def test_per_operation_uuid_expectations_match_evidence(
    carriers: dict[str, dict[str, Any]], k11_rows: list[dict[str, Any]]
) -> None:
    """Property 66 的核心：逐操作的 identity inventory 期望 ↔ 实测逐项相等。"""
    expectations = {e["op"]: e for e in carriers["hidden_uuid_column"]["per_operation_expectations"]}
    by_op: dict[str, list[dict[str, Any]]] = {}
    for row in k11_rows:
        by_op.setdefault(row["op"], []).append(row)
    assert set(expectations) <= set(by_op), (
        f"契约给了实证不存在的操作期望: {sorted(set(expectations) - set(by_op))}"
    )
    for op, expected in expectations.items():
        for row in by_op[op]:
            u = row["carriers"]["hidden_uuid_column"]
            label = f"{op}/{row['artifact_file']}"
            assert u["row_uuid_count"] == expected["row_uuid_count"], f"{label}: UUID 个数不符"
            assert u["distinct_row_uuid_count"] == expected["distinct"], f"{label}: 去重数不符"
            assert u["duplicate_row_uuids"] == expected["duplicates"], f"{label}: 重复 UUID 不符"
            assert u["missing_row_uuids"] == expected["missing"], f"{label}: 丢失 UUID 不符"
            # rows_without_uuid = Table ref 覆盖行数 − 非空 UUID 数（Requirement 6.15 新行判据）
            rows_without = _rows_in_ref(row["carriers"]["excel_table"]["table_ref"]) - u["row_uuid_count"]
            assert rows_without == expected["rows_without_uuid"], (
                f"{label}: 无 UUID 的受管行数实测 {rows_without}，契约 {expected['rows_without_uuid']}"
            )
            assert u["uuid_column_hidden"] is True, f"{label}: UUID 列不再隐藏"
            assert not u["errors"], f"{label}: 采集有 ERROR，不得当成通过 {u['errors']}"


def test_sort_moves_uuids_with_their_rows(
    carriers: dict[str, dict[str, Any]], k11_rows: list[dict[str, Any]]
) -> None:
    """排序判据必须是「行号→UUID 映射改变且集合不变」，不是「个数没少」。"""
    evidence = carriers["hidden_uuid_column"]["sort_reorder_evidence"]
    before = next(r for r in k11_rows if r["op"] == "delete_row")["carriers"]["hidden_uuid_column"]
    after = next(r for r in k11_rows if r["op"] == "sort")["carriers"]["hidden_uuid_column"]
    assert set(before["row_uuids"].values()) == set(after["row_uuids"].values()), (
        "排序改变了 UUID 集合 —— 说明有 UUID 丢失或被重写"
    )
    assert before["row_uuids"] != after["row_uuids"], (
        "排序后行号→UUID 映射没变 ⇒ UUID 留在原行号上、没跟着业务行走"
    )
    for row_no, uuid_value in evidence["after"].items():
        assert after["row_uuids"].get(row_no) == uuid_value, (
            f"契约记录的排序结果第 {row_no} 行={uuid_value}，实测 {after['row_uuids'].get(row_no)}"
        )
    for row_no, uuid_value in evidence["before"].items():
        assert before["row_uuids"].get(row_no) == uuid_value
    assert carriers["hidden_uuid_column"]["observed"]["uuid_travels_with_row_under_sort"] is True


def test_requirement_6_15_classifications_are_backed_by_evidence(
    carriers: dict[str, dict[str, Any]], k11_rows: list[dict[str, Any]]
) -> None:
    """空 UUID / 重复 UUID / 复用已删 UUID 三种形态各自的实证。"""
    cls = carriers["hidden_uuid_column"]["requirement_6_15_classification"]
    insert_row = next(r for r in k11_rows if r["op"] == "insert_row")
    paste = next(r for r in k11_rows if r["op"] == "paste")
    delete = next(r for r in k11_rows if r["op"] == "delete_row")

    # 1) 新增行 → 无 UUID，且判据（ref 行数 − UUID 数）确实 > 0
    gap = (
        _rows_in_ref(insert_row["carriers"]["excel_table"]["table_ref"])
        - insert_row["carriers"]["hidden_uuid_column"]["row_uuid_count"]
    )
    assert cls["empty_uuid_on_new_row"]["detectable"] is (gap > 0)
    assert gap > 0, "插行后没有出现「无 UUID 的受管行」，新行判据失去实证"

    # 2) 粘贴 → 可检出重复 UUID
    dups = paste["carriers"]["hidden_uuid_column"]["duplicate_row_uuids"]
    assert cls["duplicate_uuid_from_copy"]["detectable"] is bool(dups)
    assert dups, "粘贴后没有重复 UUID，重复判据失去实证"
    assert cls["duplicate_uuid_from_copy"]["contract_action"].startswith("结构冲突")

    # 3) 被删 UUID 未被复用（在删除之后的所有 artifact 里都不再出现）
    deleted = set(delete["carriers"]["hidden_uuid_column"]["missing_row_uuids"])
    assert deleted, "delete_row 未产生任何缺失 UUID，删除语义失去实证"
    later_ops = ("sort", "paste", "rename_sheet", "forcesave", "download", "reopen")
    for row in [r for r in k11_rows if r["op"] in later_ops]:
        seen = set(row["carriers"]["hidden_uuid_column"]["row_uuids"].values())
        assert not (deleted & seen), (
            f"{row['artifact_file']}: 已删除 UUID {sorted(deleted & seen)} 又出现了"
        )
    assert cls["reuse_of_deleted_uuid"]["observed"] is False
    # 「用户删掉 identity 列」这一形态未实测 ⇒ 必须标 not_covered，不许写 passed。
    assert cls["user_deleted_identity_column"]["probe_verdict"] == "not_covered"


def test_download_covers_both_serialisation_paths(
    contract: dict[str, Any], k11_rows: list[dict[str, Any]]
) -> None:
    """`download` 必须同时覆盖 callback status 2 与编辑器下载两条独立序列化路径。"""
    note = contract["operation_notes"]["download"]
    downloads = [r for r in k11_rows if r["op"] == "download"]
    deliveries = {r["delivery"] for r in downloads}
    assert deliveries == {"oo_callback", "editor_download_not_callback"}, (
        f"download 只覆盖了 {sorted(deliveries)}，契约声明两条路径"
    )
    assert len(note["paths_covered"]) == 2
    for row in downloads:
        u = row["carriers"]["hidden_uuid_column"]
        assert row["carriers"]["hidden_sheet"]["present"]
        assert not row["carriers"]["defined_name"]["missing_names"]
        assert row["carriers"]["excel_table"]["present"]
        assert u["row_uuid_count"] > 0
    assert note["both_paths_preserve_all_carriers"] is True


def test_reopen_preserves_all_carriers(
    contract: dict[str, Any], k11_rows: list[dict[str, Any]]
) -> None:
    reopens = [r for r in k11_rows if r["op"] == "reopen"]
    assert reopens, "缺少 reopen artifact"
    for row in reopens:
        assert row["carriers"]["hidden_sheet"]["present"]
        assert not row["carriers"]["hidden_sheet"]["missing_keys"]
        assert not row["carriers"]["defined_name"]["missing_names"]
        assert row["carriers"]["excel_table"]["present"]
        assert row["carriers"]["hidden_uuid_column"]["row_uuid_count"] > 0
    assert "全部保留" in contract["operation_notes"]["reopen"]["carriers_after_reopen"]


def test_no_collection_errors_anywhere(rows: list[dict[str, Any]]) -> None:
    """🔴 禁止 fail-open：采集异常必须让守卫打红，不能被当成「无 identity」。"""
    for row in rows:
        assert not row.get("error"), f"{row.get('artifact_file')}: 采集失败 {row.get('error')}"
        assert not row["collection_errors"], (
            f"{row['artifact_file']}: 结构采集有 ERROR {row['collection_errors']}"
        )


# ---------------------------------------------------------------------------
# C. Requirement 6.17 等价性（instrumentation 严格等价 + OO 归一化归因）
# ---------------------------------------------------------------------------


def test_instrumentation_is_strictly_visible_equivalent(
    contract: dict[str, Any], instrumentation: dict[str, Any]
) -> None:
    """Requirement 6.17：instrumentation 前后可见 sheet/值/公式/样式/merge/受保护部件等价。"""
    claim = contract["visible_equivalence"]["instrumentation_time"]
    assert claim["verdict"] == "equivalent"
    for doc_key, expected in (("k11", claim["k11_diff_counts"]), ("c24", claim["c24_diff_counts"])):
        report = instrumentation["docs"][doc_key]["visible_equivalence"]
        assert report["equivalent"] is True, f"{doc_key}: instrumentation 破坏了可见等价"
        for aspect in _EQUIVALENCE_ASPECTS:
            assert report["aspect_verdicts"][aspect] is True, f"{doc_key}: {aspect} 不等价"
        for aspect, count in expected.items():
            actual = report["aspects"][aspect].get("diff_count")
            assert actual == count, f"{doc_key}.{aspect}: 契约 {count}，实证 {actual}"
        assert not report["collection_errors"][report["label_before"]]
        assert not report["collection_errors"][report["label_after"]]
        # 隐藏 metadata sheet 必须被业务 sheet 枚举排除。
        assert report["metadata_sheet_excluded_from_business"] is True
        assert not report["unexpected_table_columns"]


def _negative_control_problems(before: dict[str, Any]) -> list[str]:
    """注入前必须**没有**任何 GT 载体（负对照：证明测的是新增，而不是模板自带）。

    抽成函数是为了让 `test_negative_control_is_field_specific` 能用一个「多了未知键」的
    副本验证判据是**按字段**判定而不是按整体形状 —— 否则 evidence 结构一微调就假红。
    """
    problems: list[str] = []
    if before["hidden_sheet"]["present"] is not False:
        problems.append("注入前已存在 hidden_sheet")
    if before["defined_name"]["count"] != 0:
        problems.append(f"注入前已有 {before['defined_name']['count']} 个 GT defined name")
    if before["hidden_uuid_column"]["row_uuid_count"] != 0:
        problems.append("注入前已有 row UUID")
    return problems


def test_instrumentation_adds_nothing_beyond_the_declared_whitelist(
    contract: dict[str, Any], instrumentation: dict[str, Any]
) -> None:
    """instrumentation 只能加白名单里那几样；多加一样即红（防「顺手改业务内容」）。"""
    allowed = contract["visible_equivalence"]["instrumentation_time"]["allowed_additions"]
    assert len(allowed) == 4
    for doc_key in ("k11", "c24"):
        doc = instrumentation["docs"][doc_key]
        before = doc["identity_inventory_before_instrumentation"]
        after = doc["actual_identity_inventory_after_instrumentation"]
        assert not _negative_control_problems(before), (
            f"{doc_key}: 负对照不成立 —— {_negative_control_problems(before)}"
        )
        # 注入后必须有。
        assert after["hidden_sheet"]["present"] is True
        assert after["defined_name"]["count"] == 4
        assert after["hidden_uuid_column"]["row_uuid_count"] > 0
        # 只增加了一张隐藏 sheet。
        assert doc["visible_equivalence"]["hidden_sheets_added"] == ["_GT_SYNC"]


def test_negative_control_is_field_specific(instrumentation: dict[str, Any]) -> None:
    """守卫精度自检：负对照判据只看具体载体字段，不因 evidence 多一个未知键而变色。

    存在理由：本文件 34 条变异全部 RED，需要一条反向证据说明「不是一改就红」。
    变异脚本的爆炸半径（每条变异只打红 1–3/30 例）是一条；这条是另一条 ——
    往 evidence 里塞一个无关键，判据必须**保持通过**。
    """
    before = dict(instrumentation["docs"]["k11"]["identity_inventory_before_instrumentation"])
    assert not _negative_control_problems(before), "基线负对照本身不成立，后续对比无意义"
    augmented = {**before, "_unrelated_future_key": {"anything": 1}}
    assert not _negative_control_problems(augmented), (
        "多一个未知键就让负对照判据失败 —— 说明判据按形状而非按字段，evidence 结构演进会假红"
    )
    # 反向：真正该管的字段一改就必须失败（否则判据是空操作）。
    broken = {**before, "hidden_sheet": {**before["hidden_sheet"], "present": True}}
    assert _negative_control_problems(broken), "负对照判据对 hidden_sheet.present 不敏感"


def test_oo_normalization_is_attributed_to_oo_not_instrumentation(
    contract: dict[str, Any], attribution: dict[str, Any]
) -> None:
    """控制组：B(源模板过OO) 与 C(instrumented过OO) 逐项相等、A(仅instrumentation) 全零。"""
    claim = contract["visible_equivalence"]["oo_roundtrip"]["attribution_control"]
    cases = attribution["cases"]
    for name in ("case_A_instrumentation_only", "case_B_pristine_through_oo", "case_C_instrumented_through_oo"):
        declared = claim[name]
        actual = cases[name]["diff_counts"]
        for aspect, count in declared.items():
            assert actual[aspect] == count, f"{name}.{aspect}: 契约 {count}，实证 {actual[aspect]}"
    assert attribution["conclusion"]["instrumentation_contributes_zero_diffs"] is True
    assert attribution["conclusion"]["oo_normalization_identical_with_and_without_instrumentation"] is True
    assert cases["case_B_pristine_through_oo"]["diff_counts"] == cases["case_C_instrumented_through_oo"]["diff_counts"]


def test_oo_roundtrip_is_not_claimed_byte_equivalent(contract: dict[str, Any]) -> None:
    """必须显式承认 OO 往返非字节等价，并给下游改成语义口径的指令。"""
    rt = contract["visible_equivalence"]["oo_roundtrip"]
    assert rt["verdict"] == "not_byte_equivalent_by_design"
    kinds = {n["kind"] for n in rt["oo_normalizations_observed"]}
    assert {
        "fill_color_palette_remap",
        "font_substitution",
        "formula_whitespace_normalization",
        "protected_part_reserialization",
        "defined_name_addition",
    } <= kinds
    for note in rt["oo_normalizations_observed"]:
        if "occurs_without_instrumentation" in note:
            assert note["occurs_without_instrumentation"] is True, (
                f"{note['kind']} 声明只在 instrumentation 后出现 —— 与控制组结论矛盾"
            )
    assert any("语义" in item for item in rt["consequence_for_task_17_36_37"])
    assert any("GT_" in item for item in rt["consequence_for_task_17_36_37"])


def test_protected_parts_count_never_decreases_through_oo(
    contract: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """受保护部件的通过判据是「名集合/计数不减少」，不是字节等价。"""
    baseline = {"drawing": 3, "chart": 8, "media": 1}
    c24_rows = [r for r in rows if r["doc"] == "c24"]
    assert c24_rows, "缺少含 chart 文档的 artifact"
    for row in c24_rows:
        parts = row["protected_parts"]
        for category, count in baseline.items():
            assert parts.get(category, 0) >= count, (
                f"{row['artifact_file']}: {category} 部件从 {count} 降到 {parts.get(category, 0)}"
            )
    declared = next(
        n for n in contract["visible_equivalence"]["oo_roundtrip"]["oo_normalizations_observed"]
        if n["kind"] == "protected_part_reserialization"
    )
    assert "数量" in declared["detail"] or "计数" in declared["detail"]


def test_not_covered_items_are_never_marked_passed(contract: dict[str, Any]) -> None:
    """未覆盖项必须保持 not_covered，且给出阻塞点，不得以推理冒充实证。"""
    items = contract["visible_equivalence"]["not_covered"]
    assert len(items) >= 6, "未覆盖清单不得被削减为空壳"
    for item in items:
        assert item["probe_verdict"] == "not_covered"
        assert item.get("reason"), f"{item['aspect']}: not_covered 必须给原因"
    aspects = {i["aspect"] for i in items}
    assert {
        "pivot_table",
        "vba_macro",
        "external_link_workbooks",
        "user_deletes_hidden_identity_column_in_oo",
        "concurrent_multi_user_structural_edits",
    } <= aspects
    pivot = next(i for i in items if i["aspect"] == "pivot_table")
    assert pivot.get("blocking"), "pivot 未覆盖必须写明它阻塞什么"


def test_c24_partial_operation_coverage_is_declared(contract: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """C24 只跑了 5 个操作 —— 必须在契约里显式声明未覆盖，不能让读者以为全覆盖。"""
    c24 = next(t for t in contract["templates_probed"] if t["template_id"] == "C24")
    assert c24["operations_not_covered"], "C24 未声明未覆盖操作"
    assert c24["operations_not_covered_reason"]
    observed = {r["op"] for r in rows if r["doc"] == "c24"}
    assert observed <= set(c24["operations_covered"]), (
        f"C24 实测出现了未声明的操作: {sorted(observed - set(c24['operations_covered']))}"
    )
    assert not (observed & set(c24["operations_not_covered"])), (
        "C24 声明未覆盖的操作却有 artifact —— 契约与实证矛盾"
    )
    # K11 才是承担全 10 操作的文档。
    k11 = next(t for t in contract["templates_probed"] if t["template_id"] == "K11")
    assert set(k11["operations_covered"]) == _DECLARED_OPS


def test_property_66_gate_is_registered(contract: dict[str, Any]) -> None:
    """Property 66 必须在契约里登记，并写明它阻断什么。"""
    gated = contract["properties_gated"]
    assert set(gated) == {"66"}
    text = gated["66"]
    assert "sheet_id" in text and "证伪" in text, "Property 66 登记必须写明 sheetId 被证伪"
    assert set(contract["requirements_covered"]) >= {"6.13", "6.14", "6.15", "6.16", "6.17"}
    assert "6.20" in contract["requirements_partially_covered"]
