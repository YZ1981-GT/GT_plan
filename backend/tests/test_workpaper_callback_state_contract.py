"""Task 4 guard：OnlyOffice callback / Command Service 版本化真值表 ↔ 真实 OO 9.4 实证互锁。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure Task 4
Requirements 4.3 / 4.9 / 4.10 / 5.1 / 5.2 / 5.4 / 10.2 / 10.4 / 10.9
Property 16 / 17 / 63 的**真实行为前置判据**（本任务只验前置，不验实现）。

为什么必须双向互锁（而不是只做 JSON schema 校验）：
  单验 schema 属于「守卫把字符串存在当判据」的假绿第②源 —— 手填 `oo94_observed: true`
  也能过。故本文件的每一条 `oo94_*` 断言都从 evidence 目录的**原始 callback payload /
  Command Service 返回 / artifact 单元格**重新计算，契约值与实证值不一致即红：
    - 改契约（把 observed 改成 false、把 status 6 的 userdata 改成 always 等）→ 红
    - 改实证（重跑探针得到不同 OO 行为）→ 红，必须重新裁决契约

evidence 由 `backend/scripts/diagnose/probe_oo94_multiuser_callback.py` 在真实
OnlyOffice 9.4.0-129 容器上采集（两个独立用户、同一 doc_key）。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
_CONTRACT_PATH = _REPO / "backend" / "data" / "onlyoffice_callback_state_contract.json"
_EVIDENCE_DIR = (
    _REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence"
    / "task4-oo94-multiuser-callback"
)

_REQUIRED_STATUSES = {1, 2, 3, 4, 6, 7}
_ROW_REQUIRED_KEYS = {
    "status",
    "oo_name",
    "meaning",
    "url_present",
    "userdata_present",
    "download_required",
    "oo_response_error",
    "room_transition",
    "delivery_terminal_state",
    "request_correlation",
    "recovery_outcome",
    "application_allowed",
    "oo94_observed",
    "observed_count",
    "observed_body_fields_always",
    "observed_body_fields_sometimes",
    "handling",
}
_PRESENCE_ENUM = {"always", "never", "optional"}


# ---------------------------------------------------------------------------
# fixtures：契约 + 原始 evidence
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows(contract: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(row["status"]): row for row in contract["callback_statuses"]}


@pytest.fixture(scope="module")
def callbacks() -> list[dict[str, Any]]:
    path = _EVIDENCE_DIR / "callbacks.jsonl"
    assert path.exists(), f"缺少真实 OO 实证 evidence: {path}"
    entries = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert entries, "callbacks.jsonl 为空：真值表的 oo94_* 字段无实证支撑"
    return entries


@pytest.fixture(scope="module")
def commands() -> list[dict[str, Any]]:
    path = _EVIDENCE_DIR / "commands.jsonl"
    assert path.exists(), f"缺少 Command Service 实证 evidence: {path}"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _command_body(record: dict[str, Any]) -> Any:
    """commands.jsonl 的 OO 返回体在 `result.body`（HTTP 层信息与业务 error 分开记录）。"""
    return (record.get("result") or {}).get("body")


@pytest.fixture(scope="module")
def artifact_analysis() -> dict[str, Any]:
    return json.loads((_EVIDENCE_DIR / "artifact_analysis.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def marker_cells() -> dict[str, str]:
    meta = json.loads((_EVIDENCE_DIR / "run_meta_phase1.json").read_text(encoding="utf-8"))
    cells = meta["marker_cells"]
    assert set(cells) == {"alice", "bob"}, "两用户 marker 单元格缺失，无法判定聚合/撤销语义"
    return cells


# ---------------------------------------------------------------------------
# A. 契约自身的结构与语义（Requirement 4.9 版本化真值表）
# ---------------------------------------------------------------------------


def test_contract_is_versioned_and_complete(contract: dict[str, Any], rows: dict[int, dict[str, Any]]) -> None:
    assert contract["contract_id"] == "onlyoffice_callback_state_contract"
    assert contract["schema_version"] == 1, "真值表必须版本化；schema_version 变化需同步 guard"
    for section in (
        "callback_statuses",
        "unknown_status_policy",
        "userdata_rules",
        "oo_redelivery_semantics",
        "command_service",
        "clean_close",
        "timers",
        "correlation_determinism",
        "multi_user_semantics",
        "jwt_claim_schema",
        "download_security",
        "evidence",
    ):
        assert section in contract, f"真值表缺少必需小节: {section}"
    assert set(rows) == _REQUIRED_STATUSES, (
        f"status 覆盖不全或有多余项: {sorted(rows)} != {sorted(_REQUIRED_STATUSES)}"
    )
    assert len(contract["callback_statuses"]) == len(_REQUIRED_STATUSES), "status 行重复"


def test_every_status_row_has_full_decision_columns(rows: dict[int, dict[str, Any]]) -> None:
    for status, row in rows.items():
        missing = _ROW_REQUIRED_KEYS - set(row)
        assert not missing, f"status {status} 缺少判定列: {sorted(missing)}"
        assert row["url_present"] in _PRESENCE_ENUM
        assert row["userdata_present"] in _PRESENCE_ENUM
        assert isinstance(row["download_required"], bool)
        assert isinstance(row["application_allowed"], bool)
        # durable/ack 语义：只有需要下载的状态才可能形成 application。
        if row["application_allowed"]:
            assert row["download_required"], f"status {status}: 不下载却允许 application"
        if row["url_present"] == "never":
            assert not row["download_required"], f"status {status}: 无 url 却要求下载"


def test_unknown_status_is_fail_visible(contract: dict[str, Any]) -> None:
    policy = contract["unknown_status_policy"]
    assert policy["mode"] == "fail_visible"
    assert policy["application_allowed"] is False
    assert policy["must_alert"] is True
    assert policy["must_persist_raw_payload"] is True
    assert policy["forbidden"], "未知状态必须显式列出禁止做法（防 fail-open 复活）"


def test_application_key_excludes_status_and_arrival_pointer(contract: dict[str, Any]) -> None:
    """design「明确拒绝的方案」12/19：key 不含 status，也不含到达时可变 room 指针。"""
    det = contract["correlation_determinism"]
    components = set(det["application_key_components"])
    forbidden = set(det["application_key_forbidden_components"])
    for required in (
        "incoming_sha256",
        "immutable_definition_bundle_sha256",
        "authority_model_definition_sha256",
        "frozen_client_base_version_id",
        "frozen_client_base_representation_id",
    ):
        assert required in components, f"application key 缺少 frozen 组件: {required}"
    assert "callback_status" in forbidden and "callback_status" not in components
    assert "request_id" in forbidden and "request_id" not in components
    assert "room.last_applied_at_arrival" in forbidden
    delivery = set(det["delivery_key_components"])
    assert {"room_id", "generation", "callback_status"} <= delivery, (
        "delivery key 必须含 status（Requirement 5.4），与 application key 相反"
    )


def test_participant_bound_authorization_is_refused(contract: dict[str, Any]) -> None:
    """design 拒绝方案 18 + Task 4：不得设计 participant-bound callback authorization。"""
    semantics = contract["multi_user_semantics"]
    assert semantics["callback_scope"] == "room_generation_route_event"
    assert semantics["participant_bound_callback_authorization"]["allowed"] is False
    assert semantics["users_field_semantics"] == "last_editor_only_not_contributors"
    revocation = semantics["revocation"]
    assert revocation["decision"] == "write_fence_plus_generation_rotation"
    assert "已合入内容被移除" in " ".join(revocation["oo_drop_does_not_prove"])


def test_jwt_claim_schema_is_versioned_and_url_bound(contract: dict[str, Any]) -> None:
    """Requirement 5.1/5.2 + Property 16 前置判据。"""
    schema = contract["jwt_claim_schema"]
    assert schema["claim_schema_version"] == 1
    assert schema["unknown_or_missing_version"] == "reject_before_download"
    required = schema["required_claims"]
    for claim in (
        "cbv",
        "iss",
        "aud",
        "act",
        "room_id",
        "generation",
        "doc_key",
        "route_credential_id",
        "callback_token_id",
        "exp",
        "iat",
    ):
        assert claim in required, f"claim schema 缺少必需 claim: {claim}"
    assert required["cbv"]["must_equal"] == schema["claim_schema_version"]
    assert schema["required_claims"]["iss"]["must_equal"]
    assert schema["required_claims"]["aud"]["must_equal"]
    assert set(schema["required_claims"]["act"]["enum"]) >= {"callback_write"}
    binding = schema["url_binding"]
    for token in ("room_id", "generation", "doc_key", "route_credential_id"):
        assert token in binding["rule"], f"URL binding 未绑定 {token}"
    order = schema["verification_order"]
    assert order.index("校验签名与 alg") < order.index("以上全部通过后才允许下载")
    assert any("cbv" in step for step in order), "校验顺序未包含 claim version 检查"
    # participant 只能是审计线索，不能当授权主体。
    optional = schema["optional_claims"]["participant_id"]
    assert optional["must_not_be_used_for"], "participant_id 必须显式声明不可用于授权"
    assert any("claim_version=None" in item for item in schema["forbidden"]), (
        "Requirement 5.2 要求显式禁止 claim_version=None 绕过"
    )


def test_download_security_policy_is_versioned_and_strict(contract: dict[str, Any]) -> None:
    """Requirement 5.3/5.6 + Property 17 前置判据。"""
    sec = contract["download_security"]
    assert sec["policy_version"] == 1
    controls = sec["required_controls"]
    assert controls["redirect_policy"]["follow_redirects"] is False
    assert controls["redirect_policy"]["max_redirects"] == 0
    assert controls["streaming_size_cap_bytes"] > 0
    assert controls["connect_timeout_seconds"] > 0
    assert controls["read_timeout_seconds"] > 0
    assert controls["dns_recheck_after_resolve"]["rule"]
    assert controls["url_allowlist"]["mode"] == "host_allowlist"
    assert {"zip magic", "外部关系"} <= set(controls["ooxml_checks"])
    current = sec["characterized_current_production_behavior"]
    assert current["call_site"].endswith("post_sheet_onlyoffice_callback")
    assert (_REPO / current["characterization_test"]).exists(), (
        "characterization 测试路径必须真实存在，否则安全 gap 无可执行判据"
    )
    assert len(current["gaps"]) >= 5, "现状 gap 清单不得被削减为空壳"


def test_timers_cover_timeout_grace_and_ttl(contract: dict[str, Any]) -> None:
    timers = contract["timers"]
    for key in (
        "command_service_http_timeout_seconds",
        "forcesave_callback_wait_timeout_seconds",
        "in_flight_grace_seconds",
        "download_connect_timeout_seconds",
        "download_read_timeout_seconds",
        "recovery_case_claim_ttl_hours",
    ):
        assert isinstance(timers[key], (int, float)) and timers[key] > 0, f"timers.{key} 非法"
    assert timers["in_flight_grace_seconds"] < timers["forcesave_callback_wait_timeout_seconds"], (
        "in-flight grace 必须短于 callback 等待超时，否则 grace 永不结束"
    )
    ttl = timers["delivery_ttl"]
    assert ttl["pending_mutation_token_seconds"] > 0
    assert ttl["callback_download_url_validity_seconds"] > 0


def test_userdata_rules_cover_present_absent_duplicate(contract: dict[str, Any]) -> None:
    rules = contract["userdata_rules"]
    assert set(rules) >= {"present", "absent", "duplicate"}
    assert "request-first" in rules["present"]["handling"]
    assert rules["absent"]["status_2"] and rules["absent"]["status_6"]
    dup = rules["duplicate"]
    assert any("幂等键" in item for item in dup["forbidden"]), (
        "必须显式禁止把 userdata 当幂等键（实证 OO 不去重）"
    )


# ---------------------------------------------------------------------------
# B. 契约 ↔ 真实 OO 9.4 实证互锁（核心防假绿边）
# ---------------------------------------------------------------------------


def test_observed_statuses_match_real_probe(
    rows: dict[int, dict[str, Any]], callbacks: list[dict[str, Any]]
) -> None:
    claimed = {status for status, row in rows.items() if row["oo94_observed"]}
    actual = {int(entry["status"]) for entry in callbacks if entry.get("status") is not None}
    assert claimed == actual, (
        f"契约声明已实证的 status {sorted(claimed)} 与 evidence 实际出现的 {sorted(actual)} 不一致"
    )


def test_observed_counts_and_body_fields_match_real_payloads(
    rows: dict[int, dict[str, Any]], callbacks: list[dict[str, Any]]
) -> None:
    counts = Counter(int(entry["status"]) for entry in callbacks)
    for status, row in rows.items():
        if not row["oo94_observed"]:
            assert row["observed_count"] == 0
            assert row["observed_body_fields_always"] == []
            assert row["observed_body_fields_sometimes"] == []
            continue
        assert row["observed_count"] == counts[status], (
            f"status {status}: 契约 observed_count={row['observed_count']}，evidence={counts[status]}"
        )
        key_sets = [
            set(entry["body_keys"]) for entry in callbacks if int(entry["status"]) == status
        ]
        always = set.intersection(*key_sets)
        sometimes = set.union(*key_sets) - always
        assert sorted(always) == row["observed_body_fields_always"], (
            f"status {status}: always 字段与真实 payload 不符（真实 {sorted(always)}）"
        )
        assert sorted(sometimes) == row["observed_body_fields_sometimes"], (
            f"status {status}: sometimes 字段与真实 payload 不符（真实 {sorted(sometimes)}）"
        )


def test_url_and_userdata_presence_match_real_payloads(
    rows: dict[int, dict[str, Any]], callbacks: list[dict[str, Any]]
) -> None:
    for status, row in rows.items():
        if not row["oo94_observed"]:
            continue
        entries = [e for e in callbacks if int(e["status"]) == status]
        with_url = [e for e in entries if (e.get("body") or {}).get("url")]
        with_userdata = [e for e in entries if e.get("has_userdata")]
        expected_url = {
            "always": len(entries),
            "never": 0,
        }.get(row["url_present"])
        if expected_url is not None:
            assert len(with_url) == expected_url, (
                f"status {status}: url_present={row['url_present']} 与实证 {len(with_url)}/{len(entries)} 不符"
            )
        else:  # optional
            assert 0 < len(with_url) < len(entries), f"status {status}: 声明 optional 但实证并非有无并存"
        if row["userdata_present"] == "never":
            assert not with_userdata, f"status {status}: 声明恒无 userdata，实证却有"
        elif row["userdata_present"] == "always":
            assert len(with_userdata) == len(entries), f"status {status}: 声明恒有 userdata，实证却缺"
        else:  # optional —— 必须真的出现过"有"和"无"两种，否则不许写 optional
            assert 0 < len(with_userdata) < len(entries), (
                f"status {status}: 声明 userdata optional，但实证只见一种形态"
            )


def test_download_required_matches_artifacts_actually_produced(
    rows: dict[int, dict[str, Any]], callbacks: list[dict[str, Any]]
) -> None:
    produced = {
        int(entry["status"]) for entry in callbacks if entry.get("artifact_sha256")
    }
    for status, row in rows.items():
        if not row["oo94_observed"]:
            continue
        assert row["download_required"] == (status in produced), (
            f"status {status}: download_required={row['download_required']}，"
            f"实证是否产出 artifact={status in produced}"
        )


def test_oo_does_not_redeliver_rejected_callbacks(
    contract: dict[str, Any], callbacks: list[dict[str, Any]]
) -> None:
    """实证 OO 9.4 对 host 返回非零 error 的 callback **不重发**。"""
    semantics = contract["oo_redelivery_semantics"]
    assert semantics["redelivers_on_nonzero_response"] is False
    rejected = [e for e in callbacks if e.get("response_error_returned")]
    assert rejected, "evidence 中没有任何被拒绝的 delivery，无法支撑 redelivery 结论"
    for entry in rejected:
        phase, status = entry["phase"], int(entry["status"])
        same = [
            e
            for e in callbacks
            if e["phase"] == phase and int(e["status"]) == status
        ]
        assert len(same) == 1, (
            f"{phase} status {status}: 返回非零后出现 {len(same)} 次投递 —— "
            "若 OO 确会重发，契约的 redelivers_on_nonzero_response 必须改为 true"
        )
    assert semantics["client_ui_still_shows_saved"] is True


def test_command_service_return_codes_match_real_calls(
    contract: dict[str, Any], commands: list[dict[str, Any]]
) -> None:
    claimed = {
        int(item["error"]): item
        for item in contract["command_service"]["return_codes"]
    }
    actual: set[int] = set()
    for record in commands:
        body = _command_body(record)
        if isinstance(body, dict) and "error" in body:
            actual.add(int(body["error"]))
    observed_claimed = {code for code, item in claimed.items() if item["oo94_observed"]}
    assert observed_claimed == actual, (
        f"契约声明已实证的 Command Service 返回码 {sorted(observed_claimed)} 与实际 {sorted(actual)} 不符"
    )
    assert claimed[0]["callback_expected"] is True
    for code in (1, 4, 6):
        assert claimed[code]["callback_expected"] is False, (
            f"error {code} 声明会有 callback —— 实证表明不会，前端会无限等待"
        )
    assert contract["command_service"]["http_semantics"][
        "http_status_always_200_even_on_error"
    ] is True


def test_no_callback_follows_non_accepted_commands(
    commands: list[dict[str, Any]], callbacks: list[dict[str, Any]]
) -> None:
    """行为判据：error∈{1,4,6} 的命令之后、下一条命令之前，不得出现新的 status 6 callback。"""
    timeline = sorted(commands, key=lambda r: r["ts"])
    save_ts = sorted(e["ts"] for e in callbacks if int(e["status"]) == 6)
    checked = 0
    for index, record in enumerate(timeline):
        body = _command_body(record)
        if not isinstance(body, dict) or int(body.get("error", 0)) not in (1, 4, 6):
            continue
        start = record["ts"]
        end = timeline[index + 1]["ts"] if index + 1 < len(timeline) else "9999"
        assert not [ts for ts in save_ts if start < ts < end], (
            f"命令 {record['request']} 返回 error={body['error']} 却随后产生了 status 6 callback"
        )
        checked += 1
    assert checked >= 3, f"只核到 {checked} 条非接受命令，实证覆盖不足"


def test_forcesave_artifact_aggregates_other_participant_edits(
    contract: dict[str, Any],
    callbacks: list[dict[str, Any]],
    marker_cells: dict[str, str],
) -> None:
    """Property 63 前置判据：A 发起的 forcesave artifact 含 B 的并发修改，且 users≠contributors。"""
    alice_cell, bob_cell = marker_cells["alice"], marker_cells["bob"]
    aggregated = []
    for entry in callbacks:
        if int(entry.get("status") or 0) != 6:
            continue
        cells = ((entry.get("artifact_probe") or {}).get("cells")) or {}
        if cells.get(alice_cell) and cells.get(bob_cell):
            aggregated.append(entry)
    assert aggregated, (
        "没有任何 status 6 artifact 同时含两个用户的单元格 —— "
        "callback 的 room 级聚合语义失去实证支撑"
    )
    sample = aggregated[0]
    contributors = {
        change["user"]["id"]
        for change in ((sample["body"].get("history") or {}).get("changes") or [])
    }
    users = set(sample.get("users") or [])
    assert len(contributors) >= 2, "history.changes 未记录多贡献者"
    assert users < contributors, (
        f"users={sorted(users)} 未真子集于 contributors={sorted(contributors)}；"
        "契约的 users_field_semantics=last_editor_only 需重新裁决"
    )
    assert contract["multi_user_semantics"]["contributor_snapshot_source"] == "history.changes[].user"


def test_revoked_user_contribution_is_not_dropped_from_aggregate(
    contract: dict[str, Any],
    commands: list[dict[str, Any]],
    callbacks: list[dict[str, Any]],
    marker_cells: dict[str, str],
) -> None:
    """Task 4 判据：若无法证明撤销用户已被安全 drop，则固定 write-fence + generation rotation。"""
    drops = [r for r in commands if r["request"]["c"] == "drop"]
    assert drops, "没有 c=drop 实证，撤销语义结论无支撑"
    drop = drops[0]
    drop_body = _command_body(drop)
    assert isinstance(drop_body, dict) and drop_body["error"] == 0, "drop 命令未被 OO 接受"
    dropped_user = drop["request"]["users"][0]
    bob_cell = marker_cells["bob"]
    assert dropped_user == "bob", f"marker 映射与被撤销用户不一致: {dropped_user}"

    # 1) OO 确实给出会话级 drop 取证（status 1 + actions type 0）。
    drop_evidence = [
        entry
        for entry in callbacks
        if int(entry.get("status") or 0) == 1
        and entry["ts"] > drop["ts"]
        and any(
            action.get("type") == 0 and action.get("userid") == dropped_user
            for action in (entry.get("actions") or [])
        )
    ]
    assert drop_evidence, "未捕获 OO 的 drop 断开取证（status 1 + actions type 0）"

    # 2) 但被撤销用户此前的贡献仍留在后续 artifact 中 —— 这才是决定设计的判据。
    after = [
        entry
        for entry in callbacks
        if entry["ts"] > drop["ts"]
        and ((entry.get("artifact_probe") or {}).get("cells") or {}).get(bob_cell)
    ]
    assert after, (
        "drop 之后的 artifact 已不含被撤销用户的内容 —— "
        "若 OO 真能安全 drop 内容，则 revocation.decision 必须重新裁决"
    )
    revocation = contract["multi_user_semantics"]["revocation"]
    assert revocation["decision"] == "write_fence_plus_generation_rotation"
    assert set(revocation["requirements"]) >= {"4.7", "10.4"}


def test_status6_and_status2_cannot_be_deduped_by_incoming_sha(
    contract: dict[str, Any], artifact_analysis: dict[str, Any]
) -> None:
    """实证：同内容的 status 6 / status 2 字节不同 ⇒ 不会因 incoming sha 相同而折叠。"""
    groups = artifact_analysis["same_content_different_bytes"]
    assert groups, "缺少「同内容异字节」实证，application key 的 incoming sha 语义无判据"
    pairs = [tuple(sorted(group["statuses"])) for group in groups]
    assert (2, 6) in pairs, f"未覆盖 status 6/2 组合: {pairs}"
    for group in groups:
        assert len(set(group["byte_sha256"])) > 1, "分组内字节 sha 相同，与结论矛盾"
    claim = contract["correlation_determinism"]["oo94_evidence"]
    assert claim["same_content_different_bytes"] is True
    assert any("网络重试" in item for item in claim["consequence"])


def test_evidence_pointers_in_contract_resolve(contract: dict[str, Any]) -> None:
    evidence = contract["evidence"]
    base = _REPO / evidence["dir"]
    assert base.is_dir(), f"evidence 目录不存在: {base}"
    for key in ("findings", "raw_callbacks", "raw_commands", "artifact_analysis", "machine_projection", "build"):
        assert (base / evidence[key]).exists(), f"evidence.{key} 指向的文件不存在"
    assert (_REPO / evidence["probe_script"]).exists(), "探针脚本缺失，evidence 不可复现"
    assert evidence["onlyoffice_build"].startswith("9.4."), "实证必须来自 OO 9.4"
    build = json.loads((base / evidence["build"]).read_text(encoding="utf-8"))
    assert evidence["onlyoffice_build"] in build["dpkg_onlyoffice_documentserver"], (
        "契约记录的 build 与容器实测 dpkg 输出不一致"
    )


#: Property → 本任务提供的「真实行为前置判据」测试（Task 4 只验前置，实现由 Wave 2 承接）。
#: 该映射被 `test_property_prerequisite_map_is_complete` 反向核对，防止前置判据被悄悄删掉。
_PROPERTY_PREREQUISITES: dict[int, tuple[tuple[str, str], ...]] = {
    16: (
        ("test_workpaper_callback_state_contract.py", "test_jwt_claim_schema_is_versioned_and_url_bound"),
        ("test_workpaper_callback_download_security.py", "test_production_passes_claim_version_none"),
        ("test_workpaper_callback_download_security.py", "test_claim_version_none_bypasses_version_check_today"),
    ),
    17: (
        ("test_workpaper_callback_state_contract.py", "test_download_security_policy_is_versioned_and_strict"),
        ("test_workpaper_callback_download_security.py", "test_production_writes_downloaded_bytes_without_staging"),
        ("test_workpaper_callback_download_security.py", "test_no_streaming_size_cap"),
        ("test_workpaper_callback_download_security.py", "test_dns_rebinding_is_not_rechecked"),
        ("test_workpaper_callback_download_security.py", "test_no_content_type_or_ooxml_validation_at_download"),
    ),
    63: (
        ("test_workpaper_callback_state_contract.py", "test_forcesave_artifact_aggregates_other_participant_edits"),
        ("test_workpaper_callback_state_contract.py", "test_revoked_user_contribution_is_not_dropped_from_aggregate"),
        ("test_workpaper_callback_state_contract.py", "test_participant_bound_authorization_is_refused"),
    ),
}


def test_property_prerequisite_map_is_complete(contract: dict[str, Any]) -> None:
    """Property 16 / 17 / 63 的前置判据必须真实存在且被契约登记。"""
    import ast

    assert set(_PROPERTY_PREREQUISITES) == {16, 17, 63}
    gated = {int(key) for key in contract["properties_gated"]}
    assert gated == set(_PROPERTY_PREREQUISITES), (
        f"契约 properties_gated={sorted(gated)} 与前置判据映射不一致"
    )
    tests_dir = Path(__file__).resolve().parent
    for prop, entries in _PROPERTY_PREREQUISITES.items():
        for filename, test_name in entries:
            path = tests_dir / filename
            assert path.exists(), f"Property {prop} 前置判据文件缺失: {filename}"
            names = {
                node.name
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            assert test_name in names, f"Property {prop} 前置判据测试缺失: {filename}::{test_name}"


def test_evidence_is_redacted(callbacks: list[dict[str, Any]]) -> None:
    """入库 evidence 不得含 OO 签名值/token 原文（Requirement 10.7）。"""
    raw = (_EVIDENCE_DIR / "callbacks.jsonl").read_text(encoding="utf-8")
    import re

    leaked_md5 = [v for v in re.findall(r"md5=([^&\"\\]+)", raw) if not v.startswith("sha256:")]
    assert not leaked_md5, f"evidence 泄露 OO 下载签名: {leaked_md5[:2]}"
    for entry in callbacks:
        token = (entry.get("body") or {}).get("token")
        if token is not None:
            assert str(token).startswith("sha256:"), "callback body 的 token 未脱敏"
