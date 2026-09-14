"""Task 7 guard：Windows staged artifact / DB rollback / orphan GC 边界契约 ↔ 真实实证互锁。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure Task 7
Requirements 2.4 / 3.4 / 5.9 / 9.6 / 9.7 / 14.6
Property 5（staged artifact 与 DB pointer 不产生悬空可见态）
Property 9（materialize 使用临时校验与原子发布）
Property 42（路径安全）

为什么必须双向互锁（而不是只校验契约 JSON 的字段存在）：
  只查字段存在属于「守卫把字符串存在当判据」的假绿第②源 —— 手填
  `observed_target_winerrors: [5]` 也能过。故本文件的每条 `observed_*` 断言都从
  `evidence/task7-staged-artifact-db-rollback/` 的**原始探针观测**重新计算：
    - 改契约（把跨卷 winerror 改成别的、把 share_delete_does_not_help 改成 true 等）→ 红
    - 改实证（重跑探针得到不同平台行为）→ 红，必须重新裁决契约
  另外三类结构性守卫：
    - 禁 fail-open：probe_status 与逐 case status 必须全 ok，任何采集 ERROR 态直接红
    - 禁「文件系统与 PostgreSQL 同一事务」表述漂移：spec 文档里该表述必须存在且必须被否定
    - 禁写业务表：db_sql_log 的每条 DDL/DML 必须落在 scratch schema 内

evidence 由 `backend/scripts/diagnose/probe_task7_staged_artifact_boundaries.py all`
在本机真实 Windows 文件系统 + 真实 PostgreSQL 16 上采集。本任务属 Wave 0 探针：
Task 9 的迁移与 Task 11 的 CanonicalArtifactRepository 均未实现，故此处不断言任何生产代码。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
_CONTRACT_PATH = _REPO / "backend" / "data" / "workpaper_staged_artifact_boundary_contract.json"
_SPEC_DIR = (
    _REPO / ".kiro" / "specs" / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
_EVIDENCE_DIR = _SPEC_DIR / "evidence" / "task7-staged-artifact-db-rollback"

_REQUIRED_CASES = ("fs1", "fs2", "fs3", "fs4", "fs5", "fs6", "fs7", "fs8", "db1", "db2", "db3", "db4", "db5", "db6")


# ---------------------------------------------------------------------------
# fixtures：契约 + 原始 evidence
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    assert _CONTRACT_PATH.exists(), f"缺少边界契约: {_CONTRACT_PATH}"
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def run_meta() -> dict[str, Any]:
    path = _EVIDENCE_DIR / "run_meta.json"
    assert path.exists(), f"缺少探针 run_meta: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fs() -> dict[str, Any]:
    path = _EVIDENCE_DIR / "fs_observations.json"
    assert path.exists(), f"缺少 Windows 文件系统实证: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def db() -> dict[str, Any]:
    path = _EVIDENCE_DIR / "db_observations.json"
    assert path.exists(), f"缺少 PostgreSQL 实证: {path}"
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


@pytest.fixture(scope="module")
def sql_log() -> dict[str, Any]:
    path = _EVIDENCE_DIR / "db_sql_log.json"
    assert path.exists(), f"缺少 SQL 语句台账: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# A. 契约自身结构 + 禁 fail-open
# ---------------------------------------------------------------------------


def test_contract_is_versioned_and_complete(contract: dict[str, Any]) -> None:
    assert contract["contract_id"] == "workpaper_staged_artifact_boundary_contract"
    assert contract["schema_version"] == 1, "边界契约必须版本化；schema_version 变化需同步 guard"
    assert contract["task"] == 7
    assert set(contract["requirements"]) == {"2.4", "3.4", "5.9", "9.6", "9.7", "14.6"}
    assert set(contract["properties"]) == {"Property 5", "Property 9", "Property 42"}
    for section in (
        "cross_medium_transaction",
        "staging",
        "publish",
        "process_interruption",
        "path_safety",
        "validation_gates",
        "db_boundary",
        "property_oracles",
        "not_covered",
        "evidence",
    ):
        assert section in contract, f"边界契约缺少必需小节: {section}"


def test_probe_reported_no_fail_open_errors(run_meta: dict[str, Any], fs: dict[str, Any], db: dict[str, Any]) -> None:
    """禁止 fail-open：采集异常必须让守卫红，而不是被吞成『不支持/无数据』。"""
    assert run_meta["probe_status"] == "ok", f"探针存在 ERROR 态: {run_meta['harness_errors']}"
    assert run_meta["harness_errors"] == []
    statuses = {**{k: v["status"] for k, v in fs.items()}, **{k: v["status"] for k, v in db.items()}}
    bad = {cid: st for cid, st in statuses.items() if st != "ok"}
    assert not bad, f"存在非 ok 用例: {bad}"


def test_all_required_cases_present(contract: dict[str, Any], fs: dict[str, Any], db: dict[str, Any]) -> None:
    collected = set(fs) | set(db)
    missing = [cid for cid in _REQUIRED_CASES if cid not in collected]
    assert not missing, f"evidence 缺少用例: {missing}"
    assert set(contract["evidence"]["required_case_ids"]) == set(_REQUIRED_CASES)


def test_probe_ran_on_windows_with_two_volumes(run_meta: dict[str, Any]) -> None:
    host = run_meta["host"]
    assert "Windows" in host["platform"], f"Task 7 的 Windows 结论必须在 Windows 上采集，实得 {host['platform']}"
    assert host["repo_drive"] != host["temp_drive"], "跨卷用例要求项目卷与临时卷不同"


# ---------------------------------------------------------------------------
# B. 禁止「文件系统与 PostgreSQL 同一事务」（Requirement 5.9）
# ---------------------------------------------------------------------------

_FS_TOKENS = ("文件系统", "文件", "artifact", "filesystem", "staged")
_DB_TOKENS = ("PostgreSQL", "数据库", "postgres", "PG ")
_SAME_TX_TOKENS = (
    "同一事务",
    "同事务",
    "同一个事务",
    "同一 ACID",
    "同一ACID",
    "ACID 事务",
    "ACID事务",
    "跨介质 ACID",
    "same transaction",
    "single transaction",
)
_NEGATION_TOKENS = (
    "不宣称",
    "不得宣称",
    "禁止宣称",
    "不是同一",
    "不是同事务",
    "非同一",
    "不在同一",
    "不属于同一",
    "不使用同一",
    "不构成",
    "不能形成",
    "旧措辞",
    "不 宣称",
)


def _segments(text: str) -> list[str]:
    return [seg.strip() for seg in re.split(r"[。；\n|]", text) if seg.strip()]


def _same_transaction_segments(text: str) -> list[str]:
    hits = []
    for seg in _segments(text):
        if not any(tok in seg for tok in _SAME_TX_TOKENS):
            continue
        if not any(tok in seg for tok in _FS_TOKENS):
            continue
        if not any(tok in seg for tok in _DB_TOKENS):
            continue
        hits.append(seg)
    return hits


_SCANNED_DOCS = {
    "design.md": _SPEC_DIR / "design.md",
    "requirements.md": _SPEC_DIR / "requirements.md",
    "tasks.md": _SPEC_DIR / "tasks.md",
    "evidence/findings.md": _EVIDENCE_DIR / "findings.md",
}


@pytest.mark.parametrize("doc", sorted(_SCANNED_DOCS))
def test_spec_docs_never_claim_filesystem_and_postgres_share_a_transaction(doc: str) -> None:
    """任何把文件系统与 PostgreSQL 说成同一事务的表述都必须带显式否定。"""
    path = _SCANNED_DOCS[doc]
    assert path.exists(), f"缺少 spec 文档: {path}"
    text = path.read_text(encoding="utf-8")
    offenders = [
        seg for seg in _same_transaction_segments(text) if not any(neg in seg for neg in _NEGATION_TOKENS)
    ]
    assert not offenders, f"{doc} 存在未否定的『文件系统与 PostgreSQL 同一事务』表述: {offenders}"


def test_spec_docs_keep_the_explicit_disclaimer() -> None:
    """删掉免责表述本身也算漂移：design 与 requirements 必须各留至少一条否定式声明。"""
    for doc in ("design.md", "requirements.md"):
        text = (_SPEC_DIR / doc).read_text(encoding="utf-8")
        negated = [
            seg for seg in _same_transaction_segments(text) if any(neg in seg for neg in _NEGATION_TOKENS)
        ]
        assert negated, f"{doc} 未保留『不宣称文件系统与 PostgreSQL 同事务』的显式声明"


def test_contract_declares_no_cross_medium_transaction(contract: dict[str, Any], db: dict[str, Any]) -> None:
    section = contract["cross_medium_transaction"]
    assert section["filesystem_and_postgres_share_one_transaction"] is False
    assert section["acid_across_media_claim_allowed"] is False
    assert section["forbidden_phrasings"], "必须显式列出被禁的表述"

    # 反向互锁：契约的 false 必须由 db2/db6 的原始观测支撑
    proof = section["empirical_proof"]
    db2 = db["db2"]
    assert proof["case_id"] == "db2"
    assert proof["observed_file_survived_db_rollback"] is True
    assert all(case["file_survived_db_rollback"] is True for case in db2["cases"].values()), (
        "db2 原始观测显示文件被 DB rollback 一起回滚了 —— 若真如此，『不是同一事务』的结论需重新裁决"
    )
    assert db2["filesystem_participates_in_db_transaction"] is False
    db6 = db["db6"]
    assert proof["reverse_proof_case_id"] == "db6"
    assert db6["file_exists_on_disk"] is False, "db6 应证明 DB commit 不会创造文件"
    assert db6["resolver_row_path_missing_on_disk"] is True
    assert proof["observed_pointer_to_missing_artifact_is_physically_possible"] is True


# ---------------------------------------------------------------------------
# C. staging（Requirement 2.4 / 9.7）
# ---------------------------------------------------------------------------


def test_staging_streaming_and_fsync_match_evidence(contract: dict[str, Any], fs: dict[str, Any]) -> None:
    staging = contract["staging"]
    fs1 = fs["fs1"]
    assert staging["must_be_same_volume_as_publish_target"] is True
    assert fs1["same_volume_as_project"] is True
    stream = staging["streaming_write"]
    assert stream["observed_streaming_hash_equals_reread_hash"] == fs1["streaming_hash_matches_reread"] is True
    assert fs1["streaming_sha256"] == fs1["reread_sha256"] == fs1["seed_sha256"]
    assert stream["observed_file_fsync_supported"] == fs1["file_fsync_ok"] is True


def test_directory_fsync_unsupported_claim_matches_evidence(contract: dict[str, Any], fs: dict[str, Any]) -> None:
    """Windows 无法 fsync 目录：这条不能推理，必须与实测的异常类型/错误号一致。"""
    declared = contract["staging"]["directory_fsync"]
    observed = fs["fs1"]["directory_fsync"]
    assert declared["supported_on_windows"] == observed["supported"] is False
    assert declared["observed_failure_stage"] == observed["stage"]
    assert declared["observed_exc_type"] == observed["exc_type"]
    assert declared["observed_errno"] == observed["errno"]


# ---------------------------------------------------------------------------
# D. content-addressed publish 幂等（Requirement 2.4）
# ---------------------------------------------------------------------------


def test_content_addressed_publish_idempotency_matches_evidence(
    contract: dict[str, Any], fs: dict[str, Any]
) -> None:
    declared = contract["publish"]["content_addressed"]
    fs2 = fs["fs2"]
    first, second = fs2["publishes"]
    assert declared["observed_same_content_yields_same_target_name"] == (
        first["target_name"] == second["target_name"]
    ) is True
    assert declared["observed_same_content_yields_same_target_sha256"] == (
        first["target_sha256"] == second["target_sha256"]
    ) is True
    assert declared["observed_divergent_content_yields_different_target_name"] == (
        fs2["divergent_content_target_name"] != first["target_name"]
    ) is True
    assert (
        declared["observed_divergent_publish_does_not_clobber_existing_target"]
        == fs2["first_target_survives_divergent_publish"]
        is True
    )
    assert declared["idempotency_scope"] == "path_and_sha256"
    assert declared["observed_file_index_changes_on_republish"] == (
        first["file_index"] != second["file_index"]
    ), "文件身份是否变化必须与实测一致：实现不得用 st_ino 判幂等"
    # 目标名确实由内容 hash 决定
    assert first["target_name"].endswith(".xlsx")
    assert first["target_sha256"][:12] in first["target_name"]
    assert all(p["staging_removed"] is True for p in fs2["publishes"]), "publish 后 staging 必须消失"


# ---------------------------------------------------------------------------
# E. os.replace 原子性与跨卷（Requirement 9.7）
# ---------------------------------------------------------------------------


def test_same_volume_replace_atomicity_is_backed_by_enough_observations(
    contract: dict[str, Any], fs: dict[str, Any]
) -> None:
    """partial=0 只有在观测量足够时才是结论；否则是『没看』。"""
    declared = contract["publish"]["same_volume_atomicity"]
    fs3 = fs["fs3"]
    size = fs3["size_sampling"]
    content = fs3["content_sampling"]

    assert size["observations"] >= declared["size_sampling_min_observations"], (
        f"size 采样观测数 {size['observations']} 低于契约下限 {declared['size_sampling_min_observations']}"
    )
    assert content["observations"] >= declared["content_sampling_min_observations"], (
        f"content 采样观测数 {content['observations']} 低于契约下限"
        f" {declared['content_sampling_min_observations']}"
    )
    assert declared["observed_intermediate_sizes"] == size["intermediate_sizes_observed"]
    assert declared["observed_torn_content_reads"] == content["torn_reads"]
    assert declared["observed_missing_observations"] == size["stat_missing"] == content["missing_reads"]
    assert declared["verdict"] == "atomic_no_partial_or_missing"
    assert fs3["atomic_no_partial_or_missing"] is True
    assert set(size["distinct_sizes_observed"]) == set(size["expected_sizes"]), (
        "只允许观测到旧/新两种完整大小"
    )
    assert content["full_reads"] == content["observations"] - content["read_denied"] - content["missing_reads"]


def test_cross_volume_replace_facts_match_evidence(contract: dict[str, Any], fs: dict[str, Any]) -> None:
    declared = contract["publish"]["cross_volume"]
    fs4 = fs["fs4"]
    assert fs4["cross_volume_confirmed"] is True, "跨卷前置条件未成立，本用例无效"
    observed = fs4["os_replace"]
    assert declared["os_replace_supported"] is False
    assert observed["raised"] is True
    assert declared["observed_exc_type"] == observed["exc_type"]
    assert declared["observed_errno"] == observed["errno"]
    assert declared["observed_winerror"] == observed["winerror"]
    assert declared["observed_source_survives_failure"] == fs4["source_survived_after_failure"] is True
    assert declared["observed_target_absent_after_failure"] == fs4["target_absent_after_failure"] is True

    fallback = declared["fallback_shutil_move"]
    assert fallback["atomic"] is False
    assert (
        fallback["observed_destination_visible_while_incomplete"]
        == fs4["shutil_move_destination_visible_while_incomplete"]
        is True
    )
    # 🔴 未完成大小依赖采样时机：判据用「契约声明的每个值都被实测到」而不是集合相等，
    #    这样重跑观测到更多中间大小时不会假红，但手填未观测到的值仍必红。
    observed_incomplete = {
        size for attempt in fs4["shutil_move_attempts"] for size in attempt["incomplete_sizes_sample"]
    }
    declared_incomplete = set(fallback["observed_incomplete_sizes"])
    assert declared_incomplete, "必须至少声明一个实测到的未完成大小，否则非原子结论无支撑"
    assert declared_incomplete <= observed_incomplete, (
        f"契约声明的未完成大小 {sorted(declared_incomplete)} 未被实测覆盖（实测 {sorted(observed_incomplete)}）"
    )
    assert all(size < fs4["shutil_move_size_bytes"] for size in declared_incomplete)
    assert all(a["observations"] > 0 for a in fs4["shutil_move_attempts"]), "采样为 0 时不能下非原子结论"


def test_staging_must_be_same_volume_conclusion_follows_from_evidence(
    contract: dict[str, Any], fs: dict[str, Any]
) -> None:
    """『staging 必须同卷』的判据 = 跨卷没有原子原语 + 唯一 fallback 会暴露未完成目标。"""
    assert contract["staging"]["must_be_same_volume_as_publish_target"] is True
    assert contract["publish"]["cross_volume"]["os_replace_supported"] is False
    assert fs["fs4"]["os_replace"]["raised"] is True
    assert fs["fs4"]["shutil_move_destination_visible_while_incomplete"] is True


# ---------------------------------------------------------------------------
# F. 文件占用（Requirement 9.7 可诊断）
# ---------------------------------------------------------------------------


def test_file_occupancy_matrix_matches_evidence(contract: dict[str, Any], fs: dict[str, Any]) -> None:
    declared = contract["publish"]["file_occupancy"]
    fs5 = fs["fs5"]
    target_cases = {k: v for k, v in fs5["cases"].items() if k.startswith("target_held_")}
    assert target_cases, "缺少目标被占用的实测用例"

    observed_modes = sorted(k.removeprefix("target_held_") for k in target_cases)
    assert sorted(declared["observed_share_modes_tested"]) == observed_modes, (
        "契约声明的 share 模式集合必须与实测一致 —— 只测一种模式不能得出『任何模式都不行』"
    )
    assert "read_write_delete" in observed_modes, "必须包含 FILE_SHARE_DELETE 组合，否则结论不成立"

    observed_raised = {k: v["os_replace"]["raised"] for k, v in target_cases.items()}
    assert declared["occupied_target_blocks_replace"] == all(observed_raised.values()) is True, (
        f"实测各 share 模式的 os.replace 结果: {observed_raised}"
    )
    observed_winerrors = sorted({v["os_replace"].get("winerror") for v in target_cases.values()})
    assert declared["observed_target_winerrors"] == observed_winerrors
    assert declared["share_delete_makes_replace_succeed"] == (
        not target_cases["target_held_read_write_delete"]["os_replace"]["raised"]
    ) is False
    assert declared["observed_source_winerror"] == fs5["cases"]["source_held_read_write"]["os_replace"]["winerror"]
    assert declared["observed_old_content_preserved_on_failure"] == all(
        v["target_is_old_content"] for v in target_cases.values()
    ) is True
    assert not any(v["target_is_new_content"] for v in target_cases.values()), "失败却写入了新内容"


def test_occupancy_mitigation_is_immutable_content_addressed_target(
    contract: dict[str, Any], fs: dict[str, Any]
) -> None:
    """唯一可行缓解 = 目标名从不预先存在；实测『目标不存在时占用旧 current 也能发布』。"""
    declared = contract["publish"]["file_occupancy"]
    fresh = fs["fs5"]["cases"]["fresh_target_while_old_current_held"]
    assert declared["mitigation"] == "immutable_content_addressed_target_never_preexists"
    assert fresh["target_preexisting"] is False
    assert fresh["os_replace"]["raised"] is False, "目标不预先存在时 publish 仍失败，缓解结论不成立"
    assert fresh["target_exists_after"] is True
    assert fresh["old_current_intact"] is True
    assert (
        declared["observed_fresh_target_publish_succeeds_while_old_current_held"]
        == (not fresh["os_replace"]["raised"])
        is True
    )


def test_occupancy_is_diagnosable_with_stable_codes(contract: dict[str, Any], fs: dict[str, Any]) -> None:
    """Requirement 9.7『Windows 文件占用/rename 冲突 SHALL 可诊断』：错误码必须与实测一一对应。"""
    mapping = contract["publish"]["file_occupancy"]["diagnostic_mapping"]
    fs5, fs4 = fs["fs5"], fs["fs4"]
    target = fs5["cases"]["target_held_read_write"]["os_replace"]
    source = fs5["cases"]["source_held_read_write"]["os_replace"]
    cross = fs4["os_replace"]
    assert (mapping["target_occupied"]["exc_type"], mapping["target_occupied"]["winerror"]) == (
        target["exc_type"],
        target["winerror"],
    )
    assert (mapping["source_occupied"]["exc_type"], mapping["source_occupied"]["winerror"]) == (
        source["exc_type"],
        source["winerror"],
    )
    assert (mapping["cross_volume"]["exc_type"], mapping["cross_volume"]["winerror"]) == (
        cross["exc_type"],
        cross["winerror"],
    )
    assert mapping["target_occupied"]["winerror"] != mapping["source_occupied"]["winerror"], (
        "目标占用与源占用必须能分开诊断"
    )


# ---------------------------------------------------------------------------
# G. 进程中断（Requirement 2.4）
# ---------------------------------------------------------------------------


def test_interrupted_staging_residue_cannot_be_mistaken_for_published(
    contract: dict[str, Any], fs: dict[str, Any]
) -> None:
    declared = contract["process_interruption"]
    mid = fs["fs6"]["mid_write_kill"]
    post = fs["fs6"]["post_stage_pre_publish_kill"]

    assert declared["half_product_can_be_mistaken_for_published"] is False
    assert declared["mid_staging_kill"]["observed_residue_exists"] == mid["staging_exists"] is True
    assert declared["mid_staging_kill"]["observed_residue_is_partial"] == mid["is_partial"] is True
    assert 0 < mid["staging_size_bytes"] < mid["expected_total_bytes"]
    assert (
        declared["mid_staging_kill"]["observed_residue_hash_differs_from_full"]
        == (mid["residue_sha256"] != mid["expected_full_sha256"])
        is True
    )
    assert declared["mid_staging_kill"]["observed_residue_in_staging_namespace"] == mid[
        "residue_in_staging_namespace"
    ] is True
    assert (
        declared["mid_staging_kill"]["observed_resolver_namespace_contains_residue"]
        == any(".staging" in name for name in mid["resolver_namespace_files"])
        is False
    )
    assert declared["mid_staging_kill"]["observed_publish_gate_refuses_residue"] == mid[
        "publish_gate_refuses_residue"
    ] is True

    assert declared["post_stage_pre_publish_kill"]["observed_staging_hash_valid"] == post[
        "staging_hash_valid"
    ] is True
    assert declared["post_stage_pre_publish_kill"]["observed_published_anything"] == post[
        "published_anything"
    ] is False
    assert declared["post_stage_pre_publish_kill"]["classification"] == post["classification"]


def test_kill_verdict_comes_from_disk_state_not_exit_code(contract: dict[str, Any], fs: dict[str, Any]) -> None:
    declared = contract["process_interruption"]
    mid = fs["fs6"]["mid_write_kill"]
    assert declared["verdict_source"] == mid["verdict_source"] == "disk_state_not_exit_code"
    assert declared["observed_child_returncode_after_kill"] == mid["child_returncode"]
    assert mid["child_returncode"] != 0, "被 kill 的子进程退出码非 0，正说明不能按退出码判成败"


def test_os_replace_interruption_is_declared_as_not_independently_injected(
    contract: dict[str, Any], fs: dict[str, Any]
) -> None:
    """未实证的项必须明确标出，不许含混成『已覆盖』。"""
    declared = contract["process_interruption"]["os_replace_interruption"]
    observed = fs["fs6"]["os_replace_interruption_note"]
    assert declared["independently_injected"] is observed["independently_injected"] is False
    assert declared["derived_from"] == observed["derived_from"] == "fs3"
    not_covered_items = {entry["item"] for entry in contract["not_covered"]}
    assert "os.replace 自身被中断的半成品" in not_covered_items


# ---------------------------------------------------------------------------
# H. Property 42 路径安全（Requirement 9.6）
# ---------------------------------------------------------------------------


def test_path_safety_rejections_match_evidence(contract: dict[str, Any], fs: dict[str, Any]) -> None:
    declared = contract["path_safety"]
    fs7 = fs["fs7"]
    observed_rejected = sorted(
        label for label, case in fs7["cases"].items() if case.get("accepted") is False
    )
    assert sorted(declared["must_reject"]) == observed_rejected, (
        f"契约要求拒绝 {sorted(declared['must_reject'])}，实测拒绝 {observed_rejected}"
    )
    for label in declared["must_accept"]:
        assert fs7["cases"][label]["accepted"] is True, f"{label} 应被接受"
    for label in declared["must_reject"]:
        case = fs7["cases"][label]
        assert case["reject_reason"] == "outside_project_root"
        assert not case["path_resolved"].startswith(case["root_resolved"]), (
            f"{label} 的解析结果仍在根内，判据无效"
        )


def test_symlink_escape_is_really_covered(contract: dict[str, Any], fs: dict[str, Any]) -> None:
    """软链接越界必须真建过链接；建不出来时契约必须标 not covered，而不是默认通过。"""
    declared = contract["path_safety"]
    case = fs["fs7"]["cases"]["symlink_escape"]
    assert declared["symlink_escape_covered"] == case["covered"] is True, (
        f"软链接越界未实证: {case.get('blocker')}"
    )
    assert declared["observed_symlink_mechanism"] == case["mechanism"]
    assert case["mechanism"] in ("os.symlink", "mklink /J (junction)")
    assert case["accepted"] is False


def test_cross_project_reuse_and_extension_masquerade_match_evidence(
    contract: dict[str, Any], fs: dict[str, Any]
) -> None:
    declared = contract["path_safety"]
    fs7 = fs["fs7"]
    assert (
        declared["cross_project_reuse"]["same_relative_path_resolves_to_different_absolute_paths"]
        == fs7["cross_project_same_relative_resolves_differently"]
        is True
    )
    assert fs7["cross_project_resolved_a"] != fs7["cross_project_resolved_b"]

    masq_declared = declared["extension_masquerade"]
    masq = fs7["masquerade"]
    assert masq_declared["observed_non_zip_with_xlsx_ext_rejected"] == masq["non_zip_rejected"] is True
    assert masq["non_zip_with_xlsx_ext"]["magic_ok"] is False
    assert masq_declared["observed_ext_type_mismatch_detected"] == masq["ext_type_mismatch_detected"] is True
    assert masq["xlsx_bytes_with_docx_ext"]["detected"] == "xlsx", "扩展名为 docx 的 xlsx 必须被识别成 xlsx"


# ---------------------------------------------------------------------------
# I. Property 9 校验门（Requirement 3.4）
# ---------------------------------------------------------------------------


def test_validation_gate_injections_leave_current_untouched(contract: dict[str, Any], fs: dict[str, Any]) -> None:
    declared = contract["validation_gates"]
    fs8 = fs["fs8"]
    assert declared["fail_closed"] is True
    assert sorted(declared["observed_injections"]) == sorted(fs8["injections"])
    assert sorted(declared["order"]) == sorted(fs8["injections"]), "注入点必须覆盖每个 gate"

    for label, injection in fs8["injections"].items():
        assert injection["published"] is False, f"{label} 注入后仍发布了 artifact"
        assert injection["current_sha_unchanged"] is True, f"{label} 注入后 current hash 变了"
        assert injection["pointer_unchanged"] is True, f"{label} 注入后 pointer/revision 变了"
        assert injection["versions_namespace_unchanged"] is True, f"{label} 注入后 .versions 命名空间变了"
        assert injection["first_failed_gate"] is not None, f"{label} 未触发任何 gate 失败，注入无效"
        assert injection["staging_residue_exists"] is True, f"{label} 应只在 staging 留下 residue"

    assert declared["observed_all_injections_blocked_publish"] == fs8["all_injections_blocked_publish"] is True
    assert (
        declared["observed_all_injections_left_current_unchanged"]
        == fs8["all_injections_left_current_unchanged"]
        is True
    )
    assert (
        declared["observed_all_injections_left_pointer_unchanged"]
        == fs8["all_injections_left_pointer_unchanged"]
        is True
    )
    assert fs8["injections"]["zip_structure"]["first_failed_gate"] == "zip_structure"
    assert fs8["injections"]["ooxml_parts"]["first_failed_gate"] == "ooxml_parts"
    assert fs8["injections"]["roundtrip_equivalence"]["first_failed_gate"] == "roundtrip_equivalence"


# ---------------------------------------------------------------------------
# J. DB rollback / orphan / GC（Requirement 2.4 / 5.9 / 14.6，Property 5）
# ---------------------------------------------------------------------------


#: 写目标提取规则。🔴 不能用「语句里出现 scratch schema 名」当判据 —— `INSERT INTO
#: public.working_paper ... -- tmp_task7_probe_x` 也能过（变异 21 实测把该弱判据打成 GREEN）。
#: 必须结构化取出写目标并逐个要求 scratch schema 限定。
_WRITE_TARGET_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bCREATE\s+SCHEMA\s+([A-Za-z0-9_.\"]+)", "schema"),
    (r"\bDROP\s+SCHEMA\s+(?:IF\s+EXISTS\s+)?([A-Za-z0-9_.\"]+)", "schema"),
    (r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.\"]+)", "relation"),
    (r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+\S+\s+ON\s+([A-Za-z0-9_.\"]+)", "relation"),
    (r"\bCREATE\s+FUNCTION\s+([A-Za-z0-9_.\"]+)\s*\(", "relation"),
    (r"\bCREATE\s+TRIGGER\s+\S+\s+(?:BEFORE|AFTER|INSTEAD)\b.*?\bON\s+([A-Za-z0-9_.\"]+)", "relation"),
    (r"\bINSERT\s+INTO\s+([A-Za-z0-9_.\"]+)", "relation"),
    (r"\bUPDATE\s+([A-Za-z0-9_.\"]+)\s+SET\b", "relation"),
    (r"\bDELETE\s+FROM\s+([A-Za-z0-9_.\"]+)", "relation"),
    (r"\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([A-Za-z0-9_.\"]+)", "relation"),
    (r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([A-Za-z0-9_.\"]+)", "relation"),
)
_READ_TARGET_PATTERNS = (r"\bFROM\s+([A-Za-z0-9_.\"]+)", r"\bJOIN\s+([A-Za-z0-9_.\"]+)")
_CATALOG_ALLOWLIST = ("information_schema.", "pg_catalog.", "pg_")


def _extract_targets(sql: str, patterns) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for pattern, kind in patterns:
        for match in re.finditer(pattern, sql, flags=re.IGNORECASE | re.DOTALL):
            found.append((kind, match.group(1)))
    return found


def test_db_probe_did_not_touch_business_tables(contract: dict[str, Any], sql_log: dict[str, Any]) -> None:
    """禁写业务表：逐条 DDL/DML 结构化取出写目标，必须 scratch schema 限定（可复算证据）。"""
    declared = contract["db_boundary"]
    schema = sql_log["schema"]
    assert schema and schema.startswith(declared["scratch_schema_prefix"]), f"非 scratch schema: {schema}"
    statements = sql_log["statements"]
    assert statements, "SQL 台账为空，无法证明未写业务表"

    write_offenders: list[dict[str, Any]] = []
    write_targets: set[str] = set()
    for stmt in statements:
        if stmt["kind"] not in ("DDL", "DML"):
            continue
        targets = _extract_targets(stmt["sql"], _WRITE_TARGET_PATTERNS)
        assert targets, f"写语句未能解析出目标（守卫无法判定）: {stmt['sql'][:160]}"
        for kind, target in targets:
            write_targets.add(target)
            ok = target == schema if kind == "schema" else target.startswith(f"{schema}.")
            if not ok:
                write_offenders.append({"seq": stmt["seq"], "target": target, "sql": stmt["sql"][:160]})
    assert not write_offenders, f"存在未落在 scratch schema 的写目标: {write_offenders[:3]}"

    read_offenders: list[dict[str, Any]] = []
    for stmt in statements:
        if stmt["kind"] == "TX":
            continue
        for target in [m for pattern in _READ_TARGET_PATTERNS for m in re.findall(pattern, stmt["sql"], re.IGNORECASE)]:
            if target.startswith(f"{schema}.") or target.startswith(_CATALOG_ALLOWLIST):
                continue
            read_offenders.append({"seq": stmt["seq"], "target": target})
    assert not read_offenders, f"存在读取 scratch schema 之外关系的语句: {read_offenders[:3]}"

    assert any(s["kind"] == "DML" for s in statements), "台账里没有任何写语句，说明未真正验证写入行为"
    assert f"{schema}.working_paper_artifact" in write_targets
    assert f"{schema}.working_paper_content_representation" in write_targets
    assert f"{schema}.working_paper_sync_entry_state" in write_targets
    assert any("DROP SCHEMA" in s["sql"] for s in statements), "scratch schema 未清理"


def test_db_rollback_leaves_pointer_and_revision_untouched(contract: dict[str, Any], db: dict[str, Any]) -> None:
    declared = contract["db_boundary"]["rollback_invariants"]
    db2 = db["db2"]
    observed_kinds = sorted({case["failure"]["failure_kind"] for case in db2["cases"].values()})
    assert sorted(declared["observed_failure_kinds"]) == observed_kinds, (
        "必须同时覆盖 Python 异常与真实约束冲突两种失败注入"
    )
    assert "none" not in observed_kinds, "存在注入未生效的用例，rollback 结论无效"
    for label, case in db2["cases"].items():
        assert case["pointer_generation"] == declared["observed_pointer_generation_after_rollback"], label
        assert case["pointer_representation_is_old"] is True, label
        assert case["artifact_rows_for_new_sha"] == declared["observed_new_artifact_rows_after_rollback"] == 0
        assert case["counts_equal_baseline"] is True, label
        assert case["resolver_returns_old_artifact_only"] is True, label
        assert case["file_survived_db_rollback"] is True, label
        assert case["file_sha_on_disk_after_rollback"] == case["published_file_sha256"], label


def test_resolver_never_returns_candidate_incoming_or_orphan(contract: dict[str, Any], db: dict[str, Any]) -> None:
    declared = contract["db_boundary"]["resolver_exclusion"]
    db3 = db["db3"]
    for label in ("upgrade_candidate", "incoming_durable", "canonical_orphan"):
        assert db3["cases"][label]["rejected"] is True, f"{label} 竟被允许成为 representation 的 artifact"
    observed_codes = sorted({case["pgcode"] for case in db3["cases"].values()})
    assert observed_codes == [declared["observed_reject_pgcode"]], (
        f"契约声明 pgcode {declared['observed_reject_pgcode']}，实测 {observed_codes}"
    )
    assert declared["observed_representation_referencing_candidate_rejected"] is True
    assert declared["observed_representation_referencing_incoming_durable_rejected"] is True
    assert declared["observed_representation_referencing_orphan_rejected"] is True
    assert declared["enforcement"] == "database_trigger_plus_service_validator"


def test_orphan_reconciliation_covers_both_shapes(contract: dict[str, Any], db: dict[str, Any]) -> None:
    declared = contract["db_boundary"]["orphan_reconciliation"]
    db4 = db["db4"]
    recon = db4["reconciliation"]
    assert declared["detects_disk_file_without_db_row"] == bool(recon["registered_new_orphans"]) is True
    assert declared["detects_db_row_without_reference"] == bool(recon["marked_existing_as_orphan"]) is True
    assert declared["observed_precommitted_row_marked_orphan"] == db4["precommitted_row_marked_orphan"] is True
    assert declared["observed_resolver_unaffected"] == db4["resolver_still_only_old_artifact"] is True
    assert db4["orphan_count"] >= 2, "orphan 用例过少，两种形态未同时覆盖"
    assert all(row["orphaned_at_present"] for row in db4["orphan_rows"]), "orphan 必须记录 orphaned_at"
    assert all(row["state"] == "orphan" for row in db4["orphan_rows"])
    assert recon["referenced_sha_count"] >= 1, "无任何被引用 artifact 时无法验证『只标未引用的』"


def test_retention_gc_respects_grace_recheck_and_legal_hold(contract: dict[str, Any], db: dict[str, Any]) -> None:
    declared = contract["db_boundary"]["retention_gc"]
    db5 = db["db5"]
    assert declared["policy_version"] == db5["policy"]["policy_version"]

    # grace 未到：全部 retain，且文件都还在
    observed_before = sorted({d["decision"] for d in db5["dry_run_before_grace"]})
    assert declared["observed_dry_run_before_grace_decisions"] == observed_before == ["retain"]
    observed_reasons = sorted({d["reason"] for d in db5["dry_run_before_grace"]})
    assert declared["observed_dry_run_before_grace_reasons"] == observed_reasons == ["grace_not_elapsed"]
    assert all(db5["files_present_after_dry_run_before_grace"].values()), "grace 未到却删了文件"

    # dry-run 永不删文件（即便判定为 delete）
    assert any(d["decision"] == "delete" for d in db5["dry_run_after_grace"]), "grace 后没有任何 delete 判定"
    assert declared["observed_dry_run_never_deletes"] == db5["dry_run_never_deletes"] is True
    assert all(db5["files_present_after_dry_run_after_grace"].values())

    applied = {d["sha256"]: d for d in db5["applied"]}
    legal = applied[db5["legal_hold_sha256"]]
    assert legal["decision"] == "retain" and legal["reason"] == "legal_hold"
    assert db5["files_present_after_apply"][db5["legal_hold_sha256"]] is True

    reappearing = applied[db5["reappearing_sha256"]]
    assert reappearing["decision"] == "retain"
    assert reappearing["reason"] == declared["observed_reference_reappears_reason"] == "reference_found_on_recheck"
    assert db5["files_present_after_apply"][db5["reappearing_sha256"]] is True, "二次确认发现引用却仍删了文件"

    deleted = [d for d in db5["applied"] if d["decision"] == "delete"]
    assert deleted, "没有任何 orphan 被真正删除，GC 路径未验证"
    for entry in deleted:
        assert entry["reason"] == declared["observed_delete_reason"] == "grace_elapsed_and_unreferenced"
        assert entry["file_removed"] is True
        assert db5["files_present_after_apply"][entry["sha256"]] is False

    assert set(declared["retain_reasons"]) >= {d["reason"] for d in db5["applied"] if d["decision"] == "retain"}
    assert declared["observed_resolver_unaffected_by_gc"] == db5["resolver_unaffected_by_gc"] is True

    audit_pairs = {(row["dry_run"], row["decision"]) for row in db5["audit_rows"]}
    assert (True, "retain") in audit_pairs and (False, "delete") in audit_pairs, (
        "dry-run 与实删都必须留审计行"
    )


def test_target_tables_are_declared_as_not_yet_migrated(contract: dict[str, Any], db: dict[str, Any]) -> None:
    """Wave 0 边界：不得声称 Task 9 的表已存在。"""
    declared = contract["db_boundary"]
    assert declared["target_tables_not_yet_migrated"] is True
    assert db["db1"]["schema_is_scratch"] is True
    assert db["db1"]["business_tables_touched"] == []


# ---------------------------------------------------------------------------
# K. Property oracle 覆盖闭环
# ---------------------------------------------------------------------------


def test_property_oracles_reference_real_cases(contract: dict[str, Any], fs: dict[str, Any], db: dict[str, Any]) -> None:
    collected = set(fs) | set(db)
    oracles = contract["property_oracles"]
    assert set(oracles) == {"Property 5", "Property 9", "Property 42"}
    for name, oracle in oracles.items():
        assert oracle["oracle"].strip(), f"{name} 缺 oracle 判据"
        assert oracle["statement_ref"].startswith("design.md"), f"{name} 必须指向 design.md 的定义"
        assert oracle["covered_by_cases"], f"{name} 无覆盖用例"
        missing = [cid for cid in oracle["covered_by_cases"] if cid not in collected]
        assert not missing, f"{name} 引用了不存在的用例: {missing}"

    assert set(oracles["Property 9"]["covered_by_cases"]) == {"fs8"}
    assert set(oracles["Property 42"]["covered_by_cases"]) == {"fs7"}
    assert {"db2", "db4", "db5"} <= set(oracles["Property 5"]["covered_by_cases"]), (
        "Property 5 必须同时覆盖 rollback、orphan 标记与 GC"
    )


def test_not_covered_items_are_explicit(contract: dict[str, Any]) -> None:
    """无法实证的项必须写明阻塞点，不许标成成功。"""
    entries = contract["not_covered"]
    assert entries, "not_covered 为空：任何未覆盖项都必须显式登记"
    for entry in entries:
        assert entry["item"].strip()
        assert entry["status"].strip()
        assert entry.get("blocker", "").strip(), f"{entry['item']} 缺阻塞点说明"
