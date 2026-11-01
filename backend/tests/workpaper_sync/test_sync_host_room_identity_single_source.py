"""同步载体 room 身份判据：派生侧与 RG-17 实测侧必须共用同一个判据点。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure`

缺陷现场（2026-11-01 实测）：`derive_room_model` 早已认得「room/docKey 来自服务端签发
descriptor」这一形态（`WorkpaperSyncEditorHost` 刻意不请求 OO config），据此派生
`room_model=shared`；而 RG-17 的实测侧 `observe_room_facts` **没有**这一分支，只会去匹配
legacy `onlyoffice-config` 端点 ⇒ 对同步载体 entry 得 `shared_doc_key=False`。于是：

* 每条已迁到 `WorkpaperSyncEditorHost` 且终裁 bidirectional 的 entry 都被报成
  `registry_profile_drift`（实测 J2/J3 两条），迁移完成反而被判漂移；
* 漂移文案写的是「实测 room 事实为 per-client doc_key」，而这类 entry 的宿主与组件
  doc_key 客户端兜底实测均为 `None` —— 与事实相反，照它排查会走错方向。

判据四条：①两侧对**全部**同步载体 entry 结论一致；②真实 manifest 上 RG-17 对同步载体
零漂移；③descriptor 形态消失时实测侧必须 fail closed，不得继续宣称 shared；④带客户端
本地 doc_key 兜底的形态仍判非共享（本次放宽没有顺手放过真缺陷）。
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from app.services.workpaper_sync import entry_profile as EP
from app.services.workpaper_sync import entry_source_facts as F

SYNC_HOST_COMPONENT = "WorkpaperSyncEditorHost"
SYNC_HOST_FILE = (
    "audit-platform/frontend/src/components/workpaper/sync/WorkpaperSyncEditorHost.vue"
)


def _entries() -> list[dict[str, Any]]:
    return list(EP.load_entry_manifest()["entries"])


def _sync_host_entries() -> list[dict[str, Any]]:
    rows = []
    for entry in _entries():
        components = {
            str(mount.get("component") or "") for mount in (entry.get("mounts") or [])
        }
        if SYNC_HOST_COMPONENT in components and entry.get("host_path"):
            rows.append(entry)
    return rows


def _host_facts(entry: dict[str, Any]) -> Any:
    return F.host_source_facts(
        entry_id=str(entry.get("entry_id") or ""),
        host_path=str(entry.get("host_path") or ""),
        document_type=str(entry.get("document_type") or ""),
        mounts=list(entry.get("mounts") or []),
    )


# ════════════════════════════════════════════════════════════════════════════


def test_sync_host_denominator_is_not_empty() -> None:
    rows = _sync_host_entries()
    assert len(rows) >= 10, f"同步载体 entry 只有 {len(rows)} 条，判据分母过小"


def test_single_predicate_is_shared_by_both_sides() -> None:
    """结构判据：两侧都调用 `server_issued_descriptor_room_ref`，不各写一份正则。"""
    source = Path(F.__file__).read_text(encoding="utf-8")
    body = "\n".join(
        line for line in source.split("\n") if not line.lstrip().startswith("#")
    )
    for regex_name in ("_DESCRIPTOR_ROOM_RE", "_DESCRIPTOR_DOC_KEY_RE"):
        # 两个正则只许在唯一判据点里被 `search` —— 定义行不算。
        searches = body.count(f"{regex_name}.search")
        assert searches == 1, (
            f"{regex_name}.search 出现 {searches} 次 —— descriptor 形态必须只有一个判据点，"
            "否则派生侧与实测侧会再次分叉"
        )
    assert body.count("server_issued_descriptor_room_ref(") >= 3, (
        "唯一判据点应被定义 1 次 + 派生侧与实测侧各调用 1 次"
    )


def test_derive_and_observe_agree_for_every_sync_host_entry() -> None:
    disagreements: dict[str, str] = {}
    for entry in _sync_host_entries():
        facts = _host_facts(entry)
        if facts.endpoints:
            continue  # 走 legacy provider 匹配那条路，不属本判据
        room_model, _fact, _refs, _defects = F.derive_room_model(facts)
        observed = F.observe_room_facts(entry)
        derived_shared = room_model is EP.RoomModel.shared
        if derived_shared != observed.shared_doc_key:
            disagreements[str(entry["entry_id"])] = (
                f"derive={room_model.value} observe.shared_doc_key={observed.shared_doc_key}"
            )
    assert not disagreements, (
        f"派生侧与 RG-17 实测侧对同步载体结论不一致：{disagreements}"
    )


def test_rg17_is_clear_for_sync_host_entries_on_the_real_manifest() -> None:
    offenders: dict[str, str] = {}
    checked = 0
    for entry in _sync_host_entries():
        if not entry.get("scenario_profile"):
            continue
        profile = EP.extract_entry_profile(entry)
        checked += 1
        try:
            EP.assert_profile_consistent_with_room(profile, F.observe_room_facts(entry))
        except EP.EntryProfileDriftError as exc:
            offenders[str(entry["entry_id"])] = str(exc)
    assert checked >= 10, f"只核了 {checked} 条，分母过小"
    assert not offenders, f"同步载体 entry 仍报 RG-17 漂移：{offenders}"


def test_observer_fails_closed_when_the_descriptor_shape_disappears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """descriptor 形态消失 ⇒ 实测侧不得继续宣称 shared（放宽不等于放过）。"""
    entry = next(
        row
        for row in _sync_host_entries()
        if not _host_facts(row).endpoints
    )
    monkeypatch.setattr(F, "server_issued_descriptor_room_ref", lambda _file: None)
    observed = F.observe_room_facts(copy.deepcopy(entry))
    assert observed.shared_doc_key is False, (
        "descriptor 证据不在了，实测侧仍判 shared ⇒ 新分支变成了无条件放行"
    )


def test_client_local_doc_key_still_defeats_shared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """带客户端本地 doc_key 兜底的 legacy entry 仍判非共享 —— 新分支不覆盖真缺陷形态。

    写成**差分**判据：同一条 entry 打补丁前必须是 shared，打补丁后必须不是。只断言后者
    会在「这条 entry 本来就不 shared」时因错误的理由通过。
    """
    legacy = next(
        (
            row
            for row in _entries()
            if row.get("host_path")
            and _host_facts(row).endpoints
            and F.observe_room_facts(row).shared_doc_key
        ),
        None,
    )
    if legacy is None:
        pytest.skip("manifest 里没有「走 legacy config 端点且判 shared」的 entry")

    monkeypatch.setattr(F, "_client_local_doc_key", lambda relative: f"{relative}#L1")
    for name in ("host_source_facts", "component_source_facts"):
        cached = getattr(F, name, None)
        clear = getattr(cached, "cache_clear", None)
        if callable(clear):
            clear()
    observed = F.observe_room_facts(copy.deepcopy(legacy))
    assert observed.shared_doc_key is False, (
        f"{legacy['entry_id']}: doc_key 行上有客户端本地兜底却判 shared ⇒ 真缺陷形态被放过"
    )
