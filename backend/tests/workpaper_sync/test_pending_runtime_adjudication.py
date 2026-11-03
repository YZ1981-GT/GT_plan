from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend/scripts/fix/apply_pending_runtime_adjudications.py"
_spec = importlib.util.spec_from_file_location("pending_runtime_adjudication", SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


WITHHELD_HOSTS = {
    "audit-platform/frontend/src/components/workpaper/GtH9LeaseLiabilities.vue",
    "audit-platform/frontend/src/components/workpaper/GtI1IntangibleAssets.vue",
    "audit-platform/frontend/src/components/workpaper/GtI5OtherNoncurrentAssets.vue",
}
_MANAGED_RUNTIME_EVIDENCE_REFS = mod._MANAGED_RUNTIME_EVIDENCE_REFS


def _unsafe_row(host: str) -> dict:
    return {
        "file_glob": host,
        "component": "GtOnlyOfficeSheet",
        "adapter_id": "unsafe.adapter",
        "capability": "bidirectional",
        "evidence_patch": {
            "contract_test": mod.RUNTIME_EVIDENCE_REF,
        },
    }


def test_expected_rows_require_runtime_and_representation_intersection() -> None:
    rows = mod.expected_rows()
    assert len(rows) == 13
    assert not ({row["file_glob"] for row in rows} & WITHHELD_HOSTS)
    assert all(
        row["evidence_patch"]["representation_preflight"]
        == mod.PREFLIGHT_EVIDENCE_REF
        for row in rows
    )


def test_check_rejects_managed_runtime_row_outside_safe_intersection() -> None:
    expected = mod.expected_rows()
    unsafe = _unsafe_row(next(iter(WITHHELD_HOSTS)))
    errors = mod.check({"overrides": [*expected, unsafe]}, expected)
    assert errors == [
        f"unsafe stale runtime override {mod.row_key(unsafe)}"
    ]


def test_apply_withdraws_unsafe_rows_without_touching_unrelated_overrides() -> None:
    expected = mod.expected_rows()
    unsafe_rows = [_unsafe_row(host) for host in sorted(WITHHELD_HOSTS)]
    unrelated = {
        "file_glob": "some/other/host.vue",
        "component": "GtOnlyOfficeSheet",
        "capability": "single_onlyoffice",
    }
    overlay = {
        "review_basis": "existing audit trail",
        "overrides": [unrelated, *expected, *unsafe_rows],
    }

    updated = mod.apply(overlay, expected)

    assert unrelated in updated["overrides"]
    assert not any(row in updated["overrides"] for row in unsafe_rows)
    assert mod.check(updated, expected) == []
    assert "撤回 3 条" in updated["review_basis"]


# ════════════════════════════════════════════════════════════════════════════
# 生成物侧不变量：消费方真正读的是 manifest，不是脚本的 expected_rows
# ════════════════════════════════════════════════════════════════════════════


def _manifest_entries() -> list[dict]:
    return list(mod.load(mod.MANIFEST_PATH)["entries"])


def _preflight_state_by_entry() -> dict[str, str]:
    report = mod.load(mod.PREFLIGHT_EVIDENCE_PATH)
    return {
        str(row["entry_id"]): str(row["state"]) for row in report.get("entries") or []
    }


def test_manifest_runtime_adjudicated_entries_are_representation_consistent() -> None:
    """凭本 spec runtime 证据终裁 bidirectional 的 entry，冻结结构必须自洽。

    这正是首轮踩过的坑：只过 registry probe 就终裁，而 H9/I1/I5 的 `_GT_SYNC` 冻结坐标
    已随行位移错位（下游 materialize 计划期才 fail closed）。判据落在**生成后的
    manifest** 上，而不是脚本的 `expected_rows()` —— 后者是输入侧，手工改 overlay 绕过
    脚本时只有这一条会打红。
    """
    preflight = _preflight_state_by_entry()
    adjudicated = [
        entry
        for entry in _manifest_entries()
        if (entry.get("evidence") or {}).get("contract_test")
        in _MANAGED_RUNTIME_EVIDENCE_REFS
    ]
    assert adjudicated, "凭 runtime 证据终裁的分母为空 —— 判据会在空集上恒真"

    offenders = {
        str(entry["entry_id"]): preflight.get(str(entry["entry_id"]), "<无预检记录>")
        for entry in adjudicated
        if preflight.get(str(entry["entry_id"])) != "already_consistent"
    }
    assert not offenders, (
        "以下 entry 已终裁 bidirectional，但 representation 预检不是 already_consistent："
        f"{offenders} —— registry 可注册不等于冻结结构自洽，必须退回 pending"
    )
    assert all(
        entry.get("capability") == "bidirectional" for entry in adjudicated
    ), "带本 spec runtime 证据的 entry 必须已终裁 bidirectional"


def test_manifest_adjudicated_set_equals_the_script_intersection() -> None:
    """manifest 实际终裁集合 == 脚本按双判据算出的集合（两侧互为伪证）。"""
    expected_hosts = {row["file_glob"] for row in mod.expected_rows()}
    actual_hosts = {
        str(entry["host_path"])
        for entry in _manifest_entries()
        if (entry.get("evidence") or {}).get("contract_test")
        in _MANAGED_RUNTIME_EVIDENCE_REFS
    }
    assert actual_hosts == expected_hosts, (
        f"仅在 manifest {sorted(actual_hosts - expected_hosts)}；"
        f"仅在脚本 {sorted(expected_hosts - actual_hosts)}"
    )


def test_withheld_entries_stay_pending_in_the_manifest() -> None:
    """representation 预检判 stale_needs_reprojection 的 entry 不得在 manifest 里被终裁。"""
    preflight = _preflight_state_by_entry()
    stale = {
        entry_id
        for entry_id, state in preflight.items()
        if state == "stale_needs_reprojection"
    }
    assert stale, "预检里没有 stale_needs_reprojection —— 判据会在空集上恒真"
    by_id = {str(entry["entry_id"]): entry for entry in _manifest_entries()}
    wrongly_terminal = {
        entry_id: by_id[entry_id].get("capability")
        for entry_id in sorted(stale)
        if entry_id in by_id
        and (by_id[entry_id].get("evidence") or {}).get("contract_test")
        in _MANAGED_RUNTIME_EVIDENCE_REFS
    }
    assert not wrongly_terminal, (
        f"冻结坐标已漂移却带 runtime 终裁证据：{wrongly_terminal}"
    )
