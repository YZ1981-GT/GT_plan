"""Task 25 真库判据的 R5 / R6 / R13 部分：当前代际 room 不可复用 / 已确认代际不接新内容。

spec: d2-online-edit-platform-closure · R5 / R6 / R13

拆分自 `test_task25_materialize_coordinator_pg.py`（宿主在行数门禁 whitelist 上：基线 2682 +5% = 2816）。
宿主的采集（`_collect` / `snap` fixture）**按路径加载复用**，不抄第二份；阶段 13 采集体住
`task25_room_generation_world.py`，由宿主 `_collect` 调用。场景清册（`snap["retired"]` 三个键）
仍由宿主的 `test_every_scenario_produced_a_measurement` 锁死。

两个文件一起跑时 `_collect` 会各跑一次（module scope fixture 按模块实例化）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_HOST_PATH = Path(__file__).with_name("test_task25_materialize_coordinator_pg.py")
_spec = importlib.util.spec_from_file_location("_task25_pg_host", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

snap = _host.snap  # noqa: F811  fixture 需在本模块命名空间


# ─────────────────────────────────────────────────────────────────────────
# 当前代际 room 不可复用（spec d2-online-edit-platform-closure R5 / R6）
# ─────────────────────────────────────────────────────────────────────────


def test_retired_room_with_unchanged_content_rotates_the_generation(
    snap: dict[str, Any],
) -> None:
    """终态 room + 内容未改 ⇒ materialize 换代后照发 descriptor，revision 不动。

    修复前：`open_or_reuse_room` 抛 `RoomNotWritableError` ⇒ 500；内容未改时「重新 flush」
    走业务身份复用、不产生新 commit ⇒ 永远撞同一间死 room。
    """
    row = snap["retired"]["same_content"]
    assert row["refusal"] is None, row
    assert row["business_identity_reused"] is True, row
    assert row["revision_delta"] == 0, row
    assert row["descriptors_issued"] == 1, row
    assert row["descriptor_generation"] == row["max_generation_before"] + 1, row
    assert row["pointer_generation_after"] == row["descriptor_generation"], row
    assert row["pointer_moved"] is True, row
    assert row["rooms_delta"] == 1, "换代后必须在新代际开一间新 room"
    assert row["representations_delta"] == 1, "换代 = 同 content version 新增恰一代"


def test_new_content_on_a_retired_generation_commits_onto_a_fresh_one(
    snap: dict[str, Any],
) -> None:
    """终态 room + 内容已改 ⇒ commit 直接取 `max(rep, room)+1`，不先落死代再换代。

    `representations_delta == 1` 是区分「commit 选对代际」与「commit 落进死代、靠
    materialize 换代兜底」的判据：后者会多出一行 representation。
    """
    row = snap["retired"]["new_content"]
    assert row["refusal"] is None, row
    assert row["business_identity_reused"] is False, row
    assert row["revision_delta"] == 1, row
    assert row["descriptor_generation"] == row["max_generation_before"] + 1, row
    assert row["pointer_generation_after"] == row["descriptor_generation"], row
    assert row["representations_delta"] == 1, row
    assert row["rooms_delta"] == 1, row


def test_room_closed_after_docserver_saved_rotates_to_a_fresh_doc_key(
    snap: dict[str, Any],
) -> None:
    """status 2 回 0 后 room closed ⇒ 再进入换代、doc key 必须变（spec writeback-followup-issue-closure R1.4）。

    修复前：没有任何代码关闭 room ⇒ 同代 key 被复用，而文档服务器已认定该 key 保存过 ⇒
    编辑器「版本已更改」并载入 room 物化时的旧字节。内容未改 ⇒ revision 不动、同 artifact 换代。
    """
    row = snap["retired"]["docserver_saved"]
    assert row["refusal"] is None, row
    assert row["business_identity_reused"] is True, row
    assert row["revision_delta"] == 0, row
    assert row["descriptor_generation"] == row["max_generation_before"] + 1, row
    assert row["rooms_delta"] == 1, row
    assert row["representations_delta"] == 1, row
    assert row["descriptor_doc_key"] and row["descriptor_doc_key"] != row["retired_doc_key"], row


def test_non_terminal_refusal_is_409_and_does_not_rotate(snap: dict[str, Any]) -> None:
    """refresh-required 不是终态（可能仍有待恢复的 incoming）⇒ 不换代，409 透出。

    修复前未登记 ⇒ 500，前端拦截器还会对 5xx 自动重试 3 次。
    """
    row = snap["retired"]["refresh_required"]
    assert row["refusal"] == "RoomNotWritableError", row
    assert row["status"] == 409, row
    assert "refresh_required" in (row["refusal_detail"] or ""), row
    assert row["descriptors_issued"] == 0, row
    assert row["pointer_moved"] is False, row
    assert row["rooms_delta"] == 0, row
    assert row["representations_delta"] == 0, "非终态拒绝不得换代"


# ─────────────────────────────────────────────────────────────────────────
# R13：已被编辑器确认打开过的代际不再接新内容
# ─────────────────────────────────────────────────────────────────────────


def test_new_content_after_a_confirmed_editor_session_lands_on_a_fresh_generation(
    snap: dict[str, Any],
) -> None:
    """R13（spec d2-online-edit-platform-closure）：新内容不得沿用编辑器确认过的代际。

    阶段 6 在阶段 5 的 room 上 confirm 了 descriptor（OnlyOffice 自此按这一代的
    ``doc_key`` 缓存文档）；阶段 8c 用新业务内容再物化一次 —— 沿用同一代，下一位进来的
    编辑器会拿到缓存里的旧文档，而 descriptor 记的基线是新内容（真栈形态：和平药房 D2
    第二次进在线编辑 ⇒ confirm-descriptor 422）。
    """
    confirmed_generation = int((snap["descriptor"] or {})["generation"])
    row = snap["idempotency"]["new_content"]
    assert row["revision_delta"] == 1, row
    assert row["representation_generation"] > confirmed_generation, row
