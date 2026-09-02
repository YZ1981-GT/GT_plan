"""Task 6 guard：Word tagged SDT 载体真值表 ↔ 真实 OO 9.4 实证互锁。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure Task 6
Requirements 7.2 / 7.5 / 7.6 / 14.4 / 14.16 · Property 33（Word pilot tag 往返保留）

为什么必须双向互锁（而不是只做 JSON schema 校验）：
    单验 schema 属于「守卫把字符串存在当判据」的假绿第②源 —— 手填
    `probe_verdict: passed` 也能过。本文件的每条裁决都从 evidence 目录的
    `operation_matrix.json` / `instrumentation_report.json` **重新计算**，
    契约值与实证值不一致即红：
      - 改契约（把 row_sdt 的 failed 改 passed、把 not_covered 改 passed、
        改 artifact 计数、放开 downstream gate）→ 红
      - 改实证（重跑探针得到不同 OO 行为）→ 红，必须重新裁决契约

evidence 由 `backend/scripts/diagnose/probe_oo94_word_sdt.py` 在真实
OnlyOffice 9.4.0-129 容器上采集（平台自有真实模板的隔离副本 F2-22 / F2-23 /
B30-11-2，Playwright 驱动真实编辑器；权威模板 `backend/wp_templates/` 只读）。

本 guard **不**校验生产 extractor、fail-closed 或 operation 回写是否存在 ——
那三件由 Tasks 59/61/68 承接，在这里断言等于替它们提前自证。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
_CONTRACT_PATH = _REPO / "backend" / "data" / "onlyoffice_word_sdt_carrier_contract.json"
_EVIDENCE_DIR = (
    _REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence"
    / "task6-oo94-word-tagged-sdt"
)

_VERDICTS = {"passed", "partial", "failed", "not_covered"}

#: design §Identity probe 决策门 Word 行拆出的四个可独立成败的载体。
_REQUIRED_CARRIERS = {
    "field_sdt_inline",
    "field_sdt_block",
    "row_sdt",
    "sdt_external_body",
}

#: 与载体分开裁决的候选锚点（后四个专门用来**证伪**）。
_REQUIRED_ANCHORS = {
    "w_tag",
    "alias_display_name",
    "sdt_id",
    "paragraph_index",
    "run_index",
}

#: Requirement 7.5 明列的三种硬场景必须在注入清单里各有至少一条。
_REQUIRED_75_SCENARIOS = {
    "cross_run",
    "same_paragraph_multi",
    "duplicate_instance",
}


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    assert _CONTRACT_PATH.exists(), f"缺少载体真值表: {_CONTRACT_PATH}"
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
def instrumentation() -> dict[str, Any]:
    path = _EVIDENCE_DIR / "instrumentation_report.json"
    assert path.exists(), f"缺少注入 evidence: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def carriers(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["carrier"]: c for c in contract["carriers"]}


@pytest.fixture(scope="module")
def anchors(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {a["anchor"]: a for a in contract["anchors"]}


def _missing_tags(row: dict[str, Any], prefix: str) -> list[str]:
    return [t for t in (row["carriers"]["w_tag"]["missing_tags"] or []) if t.startswith(prefix)]


# ---------------------------------------------------------------------------
# 结构完整性（这些只是前置条件，不能单独当判据）
# ---------------------------------------------------------------------------


def test_every_carrier_and_anchor_has_machine_readable_verdict(
    carriers: dict[str, Any], anchors: dict[str, Any]
) -> None:
    assert set(carriers) == _REQUIRED_CARRIERS, (
        f"载体清单与 design 决策门不一致：契约 {sorted(carriers)} vs 要求 {sorted(_REQUIRED_CARRIERS)}"
    )
    assert set(anchors) == _REQUIRED_ANCHORS, (
        f"锚点清单不一致：契约 {sorted(anchors)} vs 要求 {sorted(_REQUIRED_ANCHORS)}"
    )
    for name, item in {**carriers, **anchors}.items():
        assert item.get("probe_verdict") in _VERDICTS, f"{name} 的 probe_verdict 非法/缺失"
    for name, item in carriers.items():
        assert isinstance(item.get("may_enter_word_engine"), bool), f"{name} 缺 may_enter_word_engine"
    for name, item in anchors.items():
        assert isinstance(item.get("admissible_as_identity_anchor"), bool), (
            f"{name} 缺 admissible_as_identity_anchor"
        )


def test_evidence_has_no_collection_errors(rows: list[dict[str, Any]]) -> None:
    """采集异常必须是 ERROR 态而不是「无 tag」—— 有 error 的行不能参与裁决。"""
    broken = [
        {"doc": r.get("doc"), "op": r.get("op"), "error": r.get("error"),
         "collection_errors": r.get("collection_errors")}
        for r in rows
        if r.get("error") or r.get("collection_errors")
    ]
    assert not broken, f"evidence 含采集错误，裁决不可信：{broken}"


def test_evidence_derived_verdict_flags_agree_with_their_own_raw_measurements(
    rows: list[dict[str, Any]]
) -> None:
    """evidence 里的每个派生布尔必须能由同一行的原始测量重算出来。

    本 guard 的所有裁决都绕开这些布尔、直接从 `tags_present`/`missing_tags` 重数 ——
    这是对的，但也留下一个缺口：布尔本身没人校验，evidence 可以自相矛盾地躺在库里，
    而下游（Task 59/61 的工具、人工复核）很可能就读那个布尔。变异 M29 把 b30112
    baseline 格的 `tag_set_not_reduced` 从 false 翻成 true、原始字段一字未动，
    首轮实测无人打红。这条把派生值与原始值锁死。
    """
    bad: list[dict[str, Any]] = []
    for r in rows:
        c = r["carriers"]
        wt = c["w_tag"]
        deltas = wt.get("instance_count_deltas") or {}
        expect_tag_ok = not wt["missing_tags"] and not any(
            d["got"] < d["expected"] for d in deltas.values()
        )
        expect_count_ok = not any(d["got"] < d["expected"] for d in deltas.values())
        h = c["hierarchy"]
        expect_hier_ok = not h["regressions"] and not h["level_regressions"]
        ru = c["row_uuid"]
        expect_uuid_ok = not ru["missing"]
        eb = c["sdt_external_body"]
        expect_body_ok = eb["digest"] == eb["baseline_digest"]
        for name, got, want in (
            ("w_tag.tag_set_not_reduced", wt["tag_set_not_reduced"], expect_tag_ok),
            ("w_tag.instance_count_not_reduced", wt["instance_count_not_reduced"], expect_count_ok),
            ("hierarchy.hierarchy_preserved", h["hierarchy_preserved"], expect_hier_ok),
            ("row_uuid.row_uuid_set_not_reduced", ru["row_uuid_set_not_reduced"], expect_uuid_ok),
            ("sdt_external_body.matches_baseline", eb["matches_baseline"], expect_body_ok),
        ):
            if bool(got) is not bool(want):
                bad.append(
                    {
                        "artifact": r.get("artifact_file"),
                        "field": name,
                        "recorded": got,
                        "recomputed": want,
                    }
                )
        # 行内自证：missing/present 与 tags_present 必须互不重叠、且与基线期望同源
        overlap = set(wt["tags_present"]) & set(wt["missing_tags"])
        if overlap:
            bad.append(
                {"artifact": r.get("artifact_file"), "field": "tags_present∩missing_tags",
                 "recorded": sorted(overlap), "recomputed": []}
            )
    assert not bad, f"evidence 派生布尔与原始测量不一致（evidence 自相矛盾）：{bad}"


def test_baseline_integrity_ties_matrix_to_instrumentation(matrix: dict[str, Any]) -> None:
    """analyze 用的基线必须与注入报告是同一份 document.xml。"""
    integrity = matrix["baseline_integrity"]
    assert integrity, "operation_matrix 缺 baseline_integrity"
    bad = {k: v for k, v in integrity.items() if not v.get("matches")}
    assert not bad, f"基线漂移：staging 与 instrumentation_report 的 document.xml 不一致 {bad}"


def test_op_label_policy_statement_matches_observed_label_sources(
    matrix: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """矩阵自述的标签政策必须与它自己每一行的 `op_label_source` 一致。

    只按行校验、不校验政策自述，会留下缺口：政策被改成「以 probe mark 为准」而 17 行
    仍标 `callback_userdata`，两者直接矛盾却无人打红（变异 M31 实测因此 GREEN）。
    """
    policy = matrix.get("op_label_policy") or ""
    assert policy, "矩阵缺 op_label_policy —— 标签权威来源无自述"
    sources = {r.get("op_label_source") for r in rows}
    if "callback_userdata" in sources:
        assert "userdata" in policy, (
            f"有 {sum(1 for r in rows if r.get('op_label_source') == 'callback_userdata')} 行以 "
            f"callback userdata 为标签来源，政策自述却没把 userdata 写成权威：{policy!r}"
        )
        assert "mark 为准" not in policy, (
            f"政策自述称以 probe mark 为准，与逐行 op_label_source=callback_userdata 矛盾：{policy!r}"
        )
    if "probe_mark_fallback" in sources:
        assert "mark" in policy, (
            f"存在 probe_mark_fallback 行，政策自述却未提及 mark 兜底：{policy!r}"
        )


def test_op_labels_come_from_callback_userdata_where_available(
    rows: list[dict[str, Any]]
) -> None:
    """op 标签必须以 callback userdata 为权威，且不一致处如实留痕。

    实测 b30112 有 3 格因为「同一行命令里 command 后紧跟 mark」而被 mark 贴错标签；
    如果矩阵只留 mark 的值，evidence 就会把 baseline 的结果写成 edit_in_sdt 的结果。
    """
    assert "userdata" in matrix_policy(rows), "矩阵行缺 userdata 字段，无法自证标签来源"
    for r in rows:
        assert r.get("op_label_source") in {"callback_userdata", "probe_mark_fallback"}, r
        if r.get("op_label_source") == "callback_userdata":
            assert r.get("userdata"), f"声称用 userdata 却没有 userdata：{r.get('artifact_file')}"
        else:
            assert not r.get("userdata"), (
                f"有 userdata 却回落到 mark：{r.get('artifact_file')} userdata={r.get('userdata')}"
            )
    disagreed = [r for r in rows if r.get("op_label_disagreed_with_mark")]
    assert disagreed, (
        "没有任何一行记录 mark 与 userdata 的分歧 —— 实测存在 3 处竞态，"
        "分歧字段消失说明矩阵不再如实留痕"
    )


def matrix_policy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[0]


# ---------------------------------------------------------------------------
# 载体裁决 ↔ 实证（正向）
# ---------------------------------------------------------------------------


def test_inline_field_sdt_verdict_is_backed_by_every_artifact(
    carriers: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    item = carriers["field_sdt_inline"]
    retained = [r for r in rows if not _missing_tags(r, "gt:field:")]
    assert len(rows) == item["expected_artifacts_examined"], (
        f"契约声明检查 {item['expected_artifacts_examined']} 个 artifact，实证矩阵有 {len(rows)} 行"
    )
    assert len(retained) == item["expected_artifacts_retaining_all_inline_tags"], (
        f"inline field tag 保留数不符：契约 {item['expected_artifacts_retaining_all_inline_tags']}，"
        f"实证 {len(retained)}；缺失明细 "
        f"{[(r['doc'], r['op'], _missing_tags(r, 'gt:field:')) for r in rows if _missing_tags(r, 'gt:field:')]}"
    )
    if item["probe_verdict"] == "passed":
        assert len(retained) == len(rows), "裁决 passed 但存在 inline tag 缺失的 artifact"


def test_block_field_sdt_verdict_and_hierarchy_are_backed_by_evidence(
    carriers: dict[str, Any], rows: list[dict[str, Any]], instrumentation: dict[str, Any]
) -> None:
    item = carriers["field_sdt_block"]
    block_docs = sorted(
        d
        for d, info in instrumentation["docs"].items()
        if any(rec.get("block_tag") for rec in info["manifest"]["fields"])
    )
    assert block_docs == sorted(item["expected_block_injection_docs"]), (
        f"block 注入文档集合不符：契约 {item['expected_block_injection_docs']}，实证 {block_docs}"
    )
    subject = [r for r in rows if r["doc"] in block_docs]
    assert len(subject) == item["expected_artifacts_examined"], (
        f"block 载体 artifact 数不符：契约 {item['expected_artifacts_examined']}，实证 {len(subject)}"
    )
    retained = [r for r in subject if not _missing_tags(r, "gt:block:")]
    assert len(retained) == item["expected_artifacts_retaining_all_block_tags"]
    regressions = sum(len(r["carriers"]["hierarchy"]["regressions"]) for r in subject)
    assert regressions == item["expected_hierarchy_regressions"], (
        f"层级回归数不符：契约 {item['expected_hierarchy_regressions']}，实证 {regressions}"
    )
    if item["probe_verdict"] == "passed":
        assert regressions == 0, "裁决 passed 但存在层级回归"
        assert len(retained) == len(subject), "裁决 passed 但存在 block tag 缺失"


def test_nested_hierarchy_actually_exists_in_instrumentation(
    instrumentation: dict[str, Any], carriers: dict[str, Any]
) -> None:
    """层级判据的前提：注入时真的建了 depth=2 的嵌套，否则「层级保留」是空话。"""
    nested = {
        tag: chain
        for info in instrumentation["docs"].values()
        for tag, chain in info["manifest"]["expected_hierarchy"].items()
        if chain
    }
    assert nested, "注入清单里没有任何嵌套 SDT ⇒ 层级保留无从取证"
    item = carriers["field_sdt_block"]
    for child in item["evidence"]["nested_child_tags"]:
        assert child in nested, f"契约声明的嵌套子 tag 不在注入清单里：{child}"
        assert nested[child], f"{child} 的祖先链为空，不构成层级"
    for parent in item["evidence"]["block_tags"]:
        assert any(parent in chain for chain in nested.values()), (
            f"契约声明的 block tag 从未作为祖先出现：{parent}"
        )


def test_sdt_external_body_verdict_is_backed_by_digest_evidence(
    carriers: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    item = carriers["sdt_external_body"]
    unchanged = [r for r in rows if r["carriers"]["sdt_external_body"]["matches_baseline"]]
    assert len(rows) == item["expected_artifacts_examined"]
    assert len(unchanged) == item["expected_artifacts_with_digest_unchanged"], (
        f"自由正文未变的 artifact 数不符：契约 "
        f"{item['expected_artifacts_with_digest_unchanged']}，实证 {len(unchanged)}"
    )
    observed_ops = sorted({f"{r['doc']}/{r['op']}" for r in unchanged})
    assert observed_ops == sorted(item["expected_ops_with_digest_unchanged"]), (
        f"自由正文未变的操作集合不符：契约 {sorted(item['expected_ops_with_digest_unchanged'])}，"
        f"实证 {observed_ops}"
    )


def test_sdt_internal_edit_does_not_touch_free_text(rows: list[dict[str, Any]]) -> None:
    """Requirement 7.3 的核心：只改结构化岛时 SDT 外正文 digest 逐字不变。

    这条独立于契约数字 —— 每个文档的 `edit_in_sdt` 格必须 digest 未变。
    """
    edit_rows = [r for r in rows if r["op"] == "edit_in_sdt"]
    assert len(edit_rows) >= 3, f"edit_in_sdt 格不足 3 个文档：{[r['doc'] for r in edit_rows]}"
    changed = [
        (r["doc"], r["carriers"]["sdt_external_body"]["lines_lost"],
         r["carriers"]["sdt_external_body"]["lines_added"])
        for r in edit_rows
        if not r["carriers"]["sdt_external_body"]["matches_baseline"]
    ]
    assert not changed, f"仅改 SDT 内容却动了自由正文：{changed}"


# ---------------------------------------------------------------------------
# 载体裁决 ↔ 实证（反向锁：失败必须保持失败）
# ---------------------------------------------------------------------------


def test_row_sdt_carrier_is_disproven_by_evidence(
    carriers: dict[str, Any], rows: list[dict[str, Any]], instrumentation: dict[str, Any]
) -> None:
    """本任务最贵的一条反向锁。

    row 级 SDT 被 OO 9.4 剥离已由 9/9 artifact 证伪；若守卫放过手填 passed，
    Task 59/61 就会按 Requirement 7.2 的现设计去建 row-level 回写，全部返工。
    """
    item = carriers["row_sdt"]
    doc = item["expected_probe_doc"]
    injected = len(instrumentation["docs"][doc]["manifest"]["rows"])
    assert injected == item["expected_row_sdt_injected_at_instrumentation"], (
        f"注入的 row SDT 数不符：契约 {item['expected_row_sdt_injected_at_instrumentation']}，实证 {injected}"
    )
    assert injected > 0, "没有注入任何 row SDT ⇒ 「行载体失败」这个结论没有实证基础"

    subject = [r for r in rows if r["doc"] == doc]
    assert len(subject) == item["expected_artifacts_examined"], (
        f"行载体 artifact 数不符：契约 {item['expected_artifacts_examined']}，实证 {len(subject)}"
    )
    retaining = [
        r for r in subject
        if any(t.startswith("gt:row:") for t in r["carriers"]["w_tag"]["tags_present"])
    ]
    assert len(retaining) == item["expected_artifacts_retaining_any_row_tag"], (
        f"保留 row tag 的 artifact 数不符：契约 {item['expected_artifacts_retaining_any_row_tag']}，"
        f"实证 {len(retaining)}"
    )
    wrapped = sorted({n for r in subject for n in r["carriers"]["row_uuid"]["row_sdt_wrapped_rows"]})
    assert wrapped == [item["expected_rows_wrapped_in_sdt_after_oo"]], (
        f"OO 返回件里被 SDT 包住的行数不符：契约 {item['expected_rows_wrapped_in_sdt_after_oo']}，实证 {wrapped}"
    )
    assert item["probe_verdict"] == "failed", (
        f"row_sdt 实测 0/{len(subject)} 保留，契约却裁 {item['probe_verdict']}"
    )
    assert item["may_enter_word_engine"] is False, "row_sdt 已证伪却仍被放进 Word engine 准入名单"


def test_row_sdt_stripping_happens_at_baseline_not_by_row_edits(
    carriers: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """区分「加载/保存路径固有剥离」与「某个行操作触发」—— 结论不同，改法也不同。"""
    item = carriers["row_sdt"]
    doc = item["expected_probe_doc"]
    baseline = [r for r in rows if r["doc"] == doc and r["op"] == "baseline"]
    assert baseline, f"{doc} 缺 baseline 格，无法区分剥离时机"
    for r in baseline:
        present = [t for t in r["carriers"]["w_tag"]["tags_present"] if t.startswith("gt:row:")]
        assert not present, (
            "baseline 格仍有 row tag ⇒ 剥离不是加载/保存路径固有的，"
            f"契约的 stripped_at_baseline 断言不成立：{present}"
        )
    assert item["failure"]["stripped_at_baseline"] is True


def test_row_sdt_stripping_did_not_destroy_table_rows(
    carriers: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """「SDT 包装丢了」与「行数据丢了」是两件事，契约不得把前者写成后者。"""
    item = carriers["row_sdt"]
    doc = item["expected_probe_doc"]
    baseline = [r for r in rows if r["doc"] == doc and r["op"] == "baseline"]
    counts = [t["row_count"] for r in baseline for t in r["carriers"]["row_uuid"]["tables"]]
    assert counts and min(counts) >= 4, f"baseline 表行数异常（应仍为 4 行）：{counts}"
    assert item["failure"]["table_rows_survived"] is True


def test_paragraph_index_anchor_is_disproven_by_evidence(
    anchors: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """Requirement 7.1 禁用段落序号；这里给出实证反例而不是引用条文。"""
    item = anchors["paragraph_index"]
    unstable = [r for r in rows if not r["anchors"]["paragraph_index"]["stable"]]
    assert len(rows) == item["expected_artifacts_examined"]
    assert len(unstable) == item["expected_artifacts_unstable"], (
        f"段落序号不稳定的 artifact 数不符：契约 {item['expected_artifacts_unstable']}，"
        f"实证 {len(unstable)} -> {[(r['doc'], r['op']) for r in unstable]}"
    )
    assert unstable, "段落序号在全部 artifact 上都稳定 ⇒ 契约的 failed 裁决无实证支撑"
    ce = item["counterexample"]
    hit = [r for r in unstable if r["doc"] == ce["doc"] and r["op"] == ce["op"]]
    assert hit, f"契约声明的反例 {ce['doc']}/{ce['op']} 在实证里并不是不稳定的那一格"
    assert item["probe_verdict"] == "failed"
    assert item["admissible_as_identity_anchor"] is False


def test_run_index_anchor_is_disproven_by_evidence(
    anchors: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """跨 run 值被 OO 重排 run 切分 ⇒ run 序号不可作锚点。"""
    item = anchors["run_index"]
    ce = item["counterexample"]
    tag = ce["tag"]
    at_injection = [
        r for r in rows
        if r["doc"] == ce["doc"] and r["op"] == "baseline"
        for c in r["run_counts_per_tag"].get(tag, [])
        if c == ce["run_count_at_injection"]
    ]
    after = [
        r for r in rows
        if r["doc"] == ce["doc"] and r["op"] != "baseline"
        for c in r["run_counts_per_tag"].get(tag, [])
        if c == ce["run_count_after_oo"]
    ]
    assert at_injection, (
        f"baseline 里 {tag} 的 run 数不是契约声明的 {ce['run_count_at_injection']}"
    )
    assert after, f"后续 artifact 里 {tag} 的 run 数不是契约声明的 {ce['run_count_after_oo']}"
    assert ce["run_count_at_injection"] != ce["run_count_after_oo"], (
        "契约的反例前后 run 数相同 ⇒ 没有证伪任何东西"
    )
    assert item["probe_verdict"] == "failed"
    assert item["admissible_as_identity_anchor"] is False


def test_retained_but_inadmissible_anchors_state_both_facts(
    anchors: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """alias / sdt_id 确实保留，但都不许当定位键 —— 两个事实都要写、都要有实证。"""
    for name, key in (("alias_display_name", "alias_display_name"), ("sdt_id", "sdt_id")):
        item = anchors[name]
        stable = [r for r in rows if r["anchors"][key]["stable"]]
        assert len(stable) == item["expected_artifacts_stable"], (
            f"{name} 稳定 artifact 数不符：契约 {item['expected_artifacts_stable']}，实证 {len(stable)}"
        )
        assert item["retention_measured"] is True
        assert item["admissible_as_identity_anchor"] is False, (
            f"{name} 只是被保留，不足以当身份锚点（Requirement 7.1 只认 w:tag）"
        )
        assert len(item.get("why") or "") >= 20, f"{name} 缺少不可采纳的理由"


def test_sdt_id_duplicate_claim_is_backed_by_instrumentation(
    anchors: dict[str, Any], instrumentation: dict[str, Any]
) -> None:
    """`sdt_id` 不可采纳的硬理由：同 stable key 的多实例共享同一个 w:id。"""
    item = anchors["sdt_id"]
    assert item["duplicate_ids_observed"] is True
    tag = item["duplicate_id_tag"]
    ids: list[int] = []
    for info in instrumentation["docs"].values():
        for rec in info["manifest"]["fields"]:
            if rec["tag"] == tag:
                ids.append(rec["sdt_id"])
    assert len(ids) >= 2, f"{tag} 在注入清单里不足 2 个实例，无法支撑 duplicate 断言"
    assert len(set(ids)) == 1, f"{tag} 的多实例 w:id 并不重复：{ids}"


def test_w_tag_anchor_scope_matches_carrier_verdicts(
    anchors: dict[str, Any], carriers: dict[str, Any]
) -> None:
    """`w_tag` 的可用范围必须与载体裁决一致，不能一处放行一处拦住。"""
    item = anchors["w_tag"]
    for carrier in item["admissible_scope"]:
        assert carriers[carrier]["probe_verdict"] == "passed", (
            f"w_tag 声称在 {carrier} 上可用，但该载体裁决是 {carriers[carrier]['probe_verdict']}"
        )
    for carrier in item["inadmissible_scope"]:
        assert carriers[carrier]["probe_verdict"] == "failed", (
            f"w_tag 声称在 {carrier} 上不可用，但该载体裁决是 {carriers[carrier]['probe_verdict']}"
        )
    assert item["admissible_as_identity_anchor"] is True


# ---------------------------------------------------------------------------
# 行身份替代方案（取证到了，但不许被写成「已采纳」）
# ---------------------------------------------------------------------------


def test_row_identity_fallback_is_backed_by_evidence(
    contract: dict[str, Any], rows: list[dict[str, Any]], carriers: dict[str, Any]
) -> None:
    fb = contract["row_identity_fallback_measured"]
    doc = carriers["row_sdt"]["expected_probe_doc"]
    subject = [r for r in rows if r["doc"] == doc]
    assert len(subject) == fb["expected_artifacts_examined"]
    before_ops = set(fb["expected_ops_before_user_delete"])
    after_ops = set(fb["expected_ops_after_user_delete"])
    for r in subject:
        got = len(r["carriers"]["row_uuid"]["from_field_tags"])
        if r["op"] in before_ops:
            assert got == fb["expected_row_uuids_from_field_tags_before_user_delete"], (
                f"{r['op']} 的 field-tag row_uuid 数不符：契约 "
                f"{fb['expected_row_uuids_from_field_tags_before_user_delete']}，实证 {got}"
            )
        elif r["op"] in after_ops:
            assert got == fb["expected_row_uuids_from_field_tags_after_user_delete"], (
                f"{r['op']} 的 field-tag row_uuid 数不符：契约 "
                f"{fb['expected_row_uuids_from_field_tags_after_user_delete']}，实证 {got}"
            )
        else:
            pytest.fail(f"{r['op']} 未被契约的前/后删除分组覆盖")
    # 替代方案必须在 row 载体已死的同一批 artifact 上成立，否则不构成替代
    assert all(not r["carriers"]["row_uuid"]["from_row_sdt"] for r in subject)
    assert fb["evidence"]["survives_row_sdt_stripping"] is True


def test_user_row_delete_is_not_counted_as_carrier_loss(
    matrix: dict[str, Any], contract: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """删行是审计师意图，必须显式声明并从期望集合里累积裁掉，不能混进载体失效。"""
    declared = matrix["intentional_deletions"]
    assert declared, "矩阵未声明任何有意删除 ⇒ 删行会被误算成载体失效"
    # 🔴 声明键必须解析到真实存在的 doc/op 格，且它声明的注入必须真的从那一格起消失。
    #    只断言「字典非空」会漏掉键改名（变异 M30 实测因此 GREEN）：键错了等于没声明，
    #    期望集合就不会被裁剪，删行会被重新算成载体失效。
    cells = {f"{r['doc']}/{r['op']}" for r in rows}
    unresolvable = sorted(k for k in declared if k not in cells)
    assert not unresolvable, (
        f"intentional_deletions 的键定位不到任何 doc/op 格：{unresolvable}（矩阵实有 {sorted(cells)}）"
    )
    for key, inj_ids in declared.items():
        assert inj_ids, f"{key} 声明了有意删除但注入清单为空"
        doc, _, op = key.partition("/")
        cell = [r for r in rows if r["doc"] == doc and r["op"] == op]
        assert cell, f"{key} 没有对应的 artifact 行"
        for r in cell:
            assert sorted(r.get("intentionally_removed_injections") or []) == sorted(inj_ids), (
                f"{key} 的有意删除声明未落到该行：行内 "
                f"{r.get('intentionally_removed_injections')} vs 声明 {inj_ids}"
            )
    fb = contract["row_identity_fallback_measured"]["evidence"]["user_row_delete_removes_exactly_that_rows_uuid"]
    deleted_uuid = fb["deleted_row_uuid"]
    surviving = set(fb["surviving_row_uuids"])
    after = [r for r in rows if r["doc"] == "b30112" and r["op"] in {"delete_row", "forcesave", "reopen", "download"}]
    assert after, "找不到删除之后的 artifact"
    for r in after:
        got = set(r["carriers"]["row_uuid"]["from_field_tags"])
        assert deleted_uuid not in got, f"{r['op']}：被删行的 row_uuid 复活了"
        assert surviving <= got, f"{r['op']}：未被删的行 uuid 丢了 {surviving - got}"
        assert not r["carriers"]["row_uuid"]["missing"], (
            f"{r['op']}：期望集合未按有意删除裁剪，missing={r['carriers']['row_uuid']['missing']}"
        )


def test_oo_created_row_has_no_identity(
    contract: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """OO 内新增行不带 identity —— Requirement 6.15 的 Word 侧同类问题，必须显式记录。"""
    claim = contract["row_identity_fallback_measured"]["evidence"]["oo_created_row_has_no_uuid"]
    ins = [r for r in rows if r["doc"] == "b30112" and r["op"] == "insert_row"]
    assert ins, "缺 insert_row 格"
    for r in ins:
        counts = [t["row_count"] for t in r["carriers"]["row_uuid"]["tables"]]
        assert counts == [claim["table_row_count_after"]], (
            f"insert_row 后表行数不符：契约 {claim['table_row_count_after']}，实证 {counts}"
        )
        assert (
            len(r["carriers"]["row_uuid"]["from_field_tags"])
            == claim["row_uuids_from_field_tags_unchanged"]
        ), "新增行不该带来新的 row_uuid"
        assert not r["carriers"]["row_uuid"]["added"], (
            f"新增行带来了 uuid：{r['carriers']['row_uuid']['added']}"
        )
    assert claim["observed"] is True


def test_row_identity_fallback_is_not_declared_adopted(contract: dict[str, Any]) -> None:
    """探针可以取证替代方案可行，但不得把它写成已采纳的正式协议（越权自证）。"""
    status = contract["row_identity_fallback_measured"]["status"]
    assert "不代替裁决" in status or "not adopted" in status.lower(), (
        f"替代载体的 status 读起来像已采纳：{status}"
    )
    assert contract["carriers"] and all(
        c["carrier"] != "cell_level_field_sdt_tag_carrying_row_uuid" for c in contract["carriers"]
    ), "替代载体被塞进正式 carriers 列表 ⇒ 等于绕过 design 直接采纳"


# ---------------------------------------------------------------------------
# 下游门与覆盖面
# ---------------------------------------------------------------------------


def test_downstream_gate_lists_exactly_the_passed_items(
    contract: dict[str, Any], carriers: dict[str, Any], anchors: dict[str, Any]
) -> None:
    gate = contract["downstream_gate"]
    allowed = sorted(gate["carriers_allowed_into_word_engine"])
    blocked = sorted(gate["carriers_blocked"])
    expected_allowed = sorted(n for n, c in carriers.items() if c["probe_verdict"] == "passed")
    expected_blocked = sorted(n for n, c in carriers.items() if c["probe_verdict"] != "passed")
    assert allowed == expected_allowed, (
        f"准入名单与裁决不一致：gate {allowed} vs 裁决 passed {expected_allowed}"
    )
    assert blocked == expected_blocked, (
        f"阻断名单与裁决不一致：gate {blocked} vs 裁决非 passed {expected_blocked}"
    )
    for name in allowed:
        assert carriers[name]["may_enter_word_engine"] is True
    for name in blocked:
        assert carriers[name]["may_enter_word_engine"] is False

    a_allowed = sorted(gate["anchors_allowed"])
    a_blocked = sorted(gate["anchors_blocked"])
    assert a_allowed == sorted(
        n for n, a in anchors.items() if a["admissible_as_identity_anchor"]
    )
    assert a_blocked == sorted(
        n for n, a in anchors.items() if not a["admissible_as_identity_anchor"]
    )


def test_declared_operations_are_fully_covered(
    matrix: dict[str, Any], contract: dict[str, Any]
) -> None:
    coverage = matrix["coverage"]
    contract_docs = {d["doc"]: d for d in contract["probe_docs"]}
    assert set(coverage) == set(contract_docs), (
        f"契约探针文档与 evidence 覆盖不一致：{sorted(contract_docs)} vs {sorted(coverage)}"
    )
    for doc, info in coverage.items():
        assert not info["uncovered_operations"], (
            f"{doc} 声明了但没跑的操作：{info['uncovered_operations']}"
        )
        assert info["has_tables"] == contract_docs[doc]["has_tables"], (
            f"{doc} 的 has_tables 与实证不一致"
        )
        assert info["row_carrier_probeable"] == contract_docs[doc]["row_carrier_probeable"], (
            f"{doc} 的 row_carrier_probeable 与实证不一致"
        )


def test_pilot_row_carrier_gap_is_backed_by_template_facts(
    contract: dict[str, Any], instrumentation: dict[str, Any]
) -> None:
    """「pilot 模板零表格所以行载体不可取证」必须由模板事实支撑，不能是一句说明。"""
    gap = contract["pilot_template_row_carrier_gap"]
    pilots = [d["doc"] for d in contract["probe_docs"] if d["wp_code"].startswith("F2-2")]
    assert len(pilots) == 2, f"Requirement 7.6 指定两个 pilot，契约里有 {pilots}"
    for doc in pilots:
        tables = instrumentation["docs"][doc]["pre_injection_inventory"]["tables"]
        assert tables == [], f"{doc} 实测有表格 {tables}，与 gap 声明矛盾"
        assert instrumentation["docs"][doc]["manifest"]["rows"] == []
    row_doc = contract["carriers"][2]["expected_probe_doc"] if False else None
    row_carrier = next(c for c in contract["carriers"] if c["carrier"] == "row_sdt")
    alt = row_carrier["expected_probe_doc"]
    assert alt not in pilots, "行载体取证文档不能还是那两个零表格 pilot"
    assert instrumentation["docs"][alt]["pre_injection_inventory"]["tables"], (
        f"替代取证文档 {alt} 实测也没有表格"
    )
    assert alt in gap["action_taken"] or "B30-11-2" in gap["action_taken"]


def test_template_shas_match_readonly_authority_source(contract: dict[str, Any]) -> None:
    """契约记录的模板 sha 必须等于当前 `backend/wp_templates/` 权威源。"""
    import hashlib

    for doc in contract["probe_docs"]:
        path = _REPO / doc["template_rel"]
        assert path.exists(), f"权威模板缺失：{doc['template_rel']}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == doc["template_sha256"], (
            f"{doc['template_rel']} 的 sha 与契约不一致（模板被改过或契约过期）："
            f"契约 {doc['template_sha256']} vs 实际 {actual}"
        )


def test_authority_templates_were_not_modified_by_the_probe() -> None:
    """探针只读权威模板：before/after 两次 sha 快照必须逐项相等。"""
    before = json.loads((_EVIDENCE_DIR / "source_template_sha_before.json").read_text(encoding="utf-8"))
    after_path = _EVIDENCE_DIR / "source_template_sha_after.json"
    assert after_path.exists(), "缺少收工时的 source_template_sha_after.json"
    after = json.loads(after_path.read_text(encoding="utf-8"))
    assert set(before["templates"]) == set(after["templates"])
    drift = {
        rel: (info.get("sha256"), after["templates"][rel].get("sha256"))
        for rel, info in before["templates"].items()
        if info.get("sha256") != after["templates"][rel].get("sha256")
    }
    assert not drift, f"权威模板在探针期间被改动：{drift}"
    assert not after["lock_files"], f"wp_templates 下存在锁文件，快照不可信：{after['lock_files']}"


def test_requirement_7_5_hard_scenarios_are_all_instrumented(
    instrumentation: dict[str, Any]
) -> None:
    """Requirement 7.5 的三种硬场景必须真的被注入过，否则「7.5 通过」是空话。"""
    scenarios = {
        part
        for info in instrumentation["docs"].values()
        for rec in info["manifest"]["fields"]
        for part in str(rec["scenario"]).split("+")
    }
    missing = sorted(_REQUIRED_75_SCENARIOS - scenarios)
    assert not missing, f"Requirement 7.5 的场景没被注入：{missing}（已注入 {sorted(scenarios)}）"


def test_requirement_7_5_scenarios_are_pinned_to_named_injections(
    contract: dict[str, Any], instrumentation: dict[str, Any]
) -> None:
    """7.5 场景必须逐条钉到具体注入记录。

    只比全局集合会留缺口：某文档的 `scenario` 被改名时，另一份文档仍贡献同名场景，
    集合判据照样通过（变异 M34 实测因此 GREEN）。这里按 (doc, inj_id, run_split)
    逐条对齐契约声明与 instrumentation 实测，任一条漂移即红。
    """
    declared = contract["requirement_7_5_scenarios"]["instrumented"]
    assert set(declared) == _REQUIRED_75_SCENARIOS, (
        f"契约声明的 7.5 场景集合不对：{sorted(declared)} vs 要求 {sorted(_REQUIRED_75_SCENARIOS)}"
    )
    observed: dict[str, list[tuple[str, str, int]]] = {s: [] for s in _REQUIRED_75_SCENARIOS}
    for doc, info in instrumentation["docs"].items():
        for rec in info["manifest"]["fields"]:
            for part in str(rec["scenario"]).split("+"):
                if part in observed:
                    observed[part].append((doc, rec["inj_id"], int(rec["run_split"])))
    for scenario in sorted(_REQUIRED_75_SCENARIOS):
        want = sorted(
            (d["doc"], d["inj_id"], int(d["run_split"])) for d in declared[scenario]
        )
        got = sorted(observed[scenario])
        assert want == got, (
            f"7.5 场景 {scenario} 的注入记录漂移：契约 {want}，实证 {got}"
        )
        assert got, f"7.5 场景 {scenario} 没有任何注入记录"


def test_cross_run_injection_really_spans_multiple_runs(
    instrumentation: dict[str, Any]
) -> None:
    """`cross_run` 场景必须 run_split>1，否则名字叫跨 run 而实际是单 run。"""
    cross = [
        rec
        for info in instrumentation["docs"].values()
        for rec in info["manifest"]["fields"]
        if "cross_run" in str(rec["scenario"])
    ]
    assert cross, "没有任何 cross_run 注入"
    for rec in cross:
        assert rec["run_split"] > 1, f"{rec['inj_id']} 声称 cross_run 但 run_split={rec['run_split']}"


def test_not_covered_items_are_never_marked_passed(contract: dict[str, Any]) -> None:
    """未取证的方面一律 not_covered —— 「推理冒充实证」是本任务明令禁止的。"""
    assert contract["not_covered"], "not_covered 为空 ⇒ 探针声称覆盖了一切，不可信"
    for item in contract["not_covered"]:
        assert item["probe_verdict"] == "not_covered", (
            f"{item['aspect']} 在 not_covered 段里却裁 {item['probe_verdict']}"
        )
        assert len(item.get("why") or "") >= 8, f"{item['aspect']} 缺少 not_covered 理由"


def test_contract_does_not_claim_downstream_task_deliverables(contract: dict[str, Any]) -> None:
    """本 probe 不得提前宣称 extractor / fail-closed / operation 回写已实现。"""
    non_claims = contract["scope_and_non_claims"]["explicitly_not_claimed"]
    joined = "\n".join(non_claims)
    for keyword in ("extractor", "fail-closed", "operation 回写"):
        assert keyword in joined, f"非声明清单里缺少 {keyword}"
    covered_aspects = {i["aspect"] for i in contract["not_covered"]}
    for aspect in (
        "tag_missing_fail_closed_in_production",
        "extract_merge_rematerialize_roundtrip",
    ):
        assert aspect in covered_aspects, f"{aspect} 必须显式登记为 not_covered"


def test_environment_records_stale_policy_inputs(contract: dict[str, Any]) -> None:
    """Requirement 14.16：build / 浏览器 / runner / commit / 时间 + stale policy 必须齐。"""
    env = contract["environment"]
    for key in (
        "oo_build",
        "browser",
        "runner",
        "source_commit",
        "captured_at",
        "evidence_dir",
        "stale_policy",
    ):
        assert env.get(key), f"environment 缺 {key}（Requirement 14.16）"
    assert env["oo_build"] == "9.4.0-129", "契约里的 OO build 必须与 oo_build.json 一致"
    build = json.loads((_EVIDENCE_DIR / "oo_build.json").read_text(encoding="utf-8"))
    assert env["oo_build"] in build["dpkg_onlyoffice_documentserver"], (
        "契约 build 号在 oo_build.json 的 dpkg 输出里找不到"
    )
    runner = _REPO / env["runner"]
    assert runner.exists(), f"runner 脚本不存在：{env['runner']}"


def test_lock_policy_is_no_lock_and_matches_instrumentation(
    contract: dict[str, Any], instrumentation: dict[str, Any]
) -> None:
    """注入刻意不加锁 —— 若实际加了锁，「OO 自发保留 tag」这个结论就不成立。"""
    assert contract["scope_and_non_claims"]["lock_policy"] == "no_w_lock_injected"
    for doc, info in instrumentation["docs"].items():
        assert info["manifest"]["lock_policy"] == "no_w_lock_injected", doc
    staging = _EVIDENCE_DIR / "staging"
    import zipfile

    for path in sorted(staging.glob("*_instrumented.docx")):
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        assert "<w:lock" not in xml, f"{path.name} 实际写入了 w:lock，与 lock_policy 矛盾"


def test_negative_control_is_field_specific(contract: dict[str, Any]) -> None:
    """反向自检：往契约副本塞一个**未知键**，判据必须保持通过。

    没有这条，「35 条变异全 RED」就无法区分「守卫有效」与「守卫一改就红」。
    放在守卫里而不是当 GREEN 对照变异，因为共享 kit 把 GREEN 一律判成守卫缺陷。
    """
    import copy

    clone = copy.deepcopy(contract)
    clone["__unknown_probe_key__"] = {"probe_verdict": "passed", "everything": "fine"}
    clone["carriers"][0]["__unrelated_note__"] = "无关字段"
    assert {c["carrier"] for c in clone["carriers"]} == _REQUIRED_CARRIERS
    assert all(c["probe_verdict"] in _VERDICTS for c in clone["carriers"])
    row = next(c for c in clone["carriers"] if c["carrier"] == "row_sdt")
    assert row["probe_verdict"] == "failed"
    assert row["may_enter_word_engine"] is False
