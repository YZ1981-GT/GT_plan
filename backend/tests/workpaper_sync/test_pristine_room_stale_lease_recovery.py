"""`room_never_took_custody` 纯判据守卫（治本分流的判据侧）。

背景（2026-09-22 真栈根因）：`materialize` 旧代码把**所有**僵死 participant lease 都当
「写会话被撤销 ⇒ 内容可能已污染 ⇒ 作废整代」处理。该安全论证（「OO 的 ``c=drop`` 只证明
会话被逐出，不证明已合入内容被移除」）预设 **OO 会话真实接管过文档**。

但存在另一类僵死 lease：用户点了在线编辑、room 建好、**descriptor 确认从未到达**
（OO 没加载完 / 用户切走 / L1 验收脚本只测挂载不测确认），lease 随后自然到期。此时 room
仍停在 ``opening``、``client_confirmed_*`` 全空、request/durable 序列为 0、无 application、
fence 仍是初值 —— 这一代**从未写入过任何字节**，污染在物理上不可能发生。

对它作废整代会把用户彻底锁死：`materialize` 无法旋转 generation（那是 `content_commit`
的职责），而「重新 flush」在内容未改时走 business-identity 复用路径、**同样不触发旋转**，
于是永远回到同一间死 room。真栈同一 entry 因此堆积了 6 个从未确认即被遗弃的代际
（g69/76/77/78/80/93），materialize 稳定 500（只改成 409 则变成 409 死循环）。

本文件锚定**判据侧**：干净代际判 True；任何「动过内容」的迹象判 False。
释放机制（lease → `expired` 腾出 `uq_wpoop_active_lease` 槽位 + 续租 room 窗口 + 可重新
join）由 `test_task21_room_service_pg.py` 的 `pristine_lease` 阶段在真库上守卫。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.workpaper_sync.models import RoomState
from app.services.workpaper_sync.rooms import room_never_took_custody


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pristine_room(**over: object) -> SimpleNamespace:
    """一间「刚 open、什么都没发生过」的 room 行（字段与 ORM 同名）。"""
    base: dict[str, object] = dict(
        state=RoomState.opening.value,
        refresh_required_at=None,
        client_confirmed_base_version_id=None,
        client_confirmed_representation_id=None,
        client_confirmed_definition_bundle_id=None,
        client_confirmed_projection_sha256=None,
        last_applied_version_id=None,
        latest_durable_application_id=None,
        close_leader_intent_id=None,
        latest_request_sequence=0,
        latest_durable_sequence=0,
        close_barrier_epoch=0,
        write_fence_epoch=1,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_a_freshly_opened_room_never_took_custody() -> None:
    """正向自检：干净代际必须判 True。

    没有这一条，把判据写成恒 False 也能让下面全部「必须 False」的用例全绿 —— 而那会让
    整条 pristine 轻量分支永不生效，真栈死锁原样复现。
    """
    assert room_never_took_custody(_pristine_room()) is True


@pytest.mark.parametrize(
    "field,value,why",
    [
        ("state", RoomState.active.value, "active 意味着 descriptor 确认到达过"),
        ("state", RoomState.close_barrier.value, "已进 close barrier"),
        ("state", RoomState.closing.value, "正在关闭"),
        ("state", RoomState.superseded.value, "已被取代"),
        ("state", RoomState.closed.value, "已关闭"),
        ("state", RoomState.recovery_required.value, "待恢复"),
        ("state", RoomState.refresh_required.value, "待刷新"),
        ("refresh_required_at", _now(), "被标过 refresh-required"),
        ("client_confirmed_base_version_id", uuid.uuid4(), "确认过基线版本"),
        ("client_confirmed_representation_id", uuid.uuid4(), "确认过 representation"),
        ("client_confirmed_definition_bundle_id", uuid.uuid4(), "确认过 bundle"),
        ("client_confirmed_projection_sha256", "a" * 64, "确认过 projection"),
        ("last_applied_version_id", uuid.uuid4(), "服务端已应用过内容"),
        ("latest_durable_application_id", uuid.uuid4(), "有 durable application"),
        ("close_leader_intent_id", uuid.uuid4(), "有 close leader intent"),
        ("latest_request_sequence", 1, "发起过 request"),
        ("latest_durable_sequence", 1, "有 durable 内容"),
        ("close_barrier_epoch", 1, "close barrier 推进过"),
        ("write_fence_epoch", 2, "fence 被提升过（此前发生撤销/旋转）"),
    ],
)
def test_any_sign_of_custody_flips_the_predicate_to_false(
    field: str, value: object, why: str
) -> None:
    """任何一项「动过内容」的迹象都必须判 False —— 判据只朝保守方向放行。

    逐字段参数化而不是合并成一条：合并后删掉其中任意一项检查仍会全绿，
    而那正是「静默放宽安全判据」。新增承载内容托管语义的列必须在此登记。
    """
    room = _pristine_room(**{field: value})
    assert room_never_took_custody(room) is False, f"{field}={value!r} ⇒ {why}"


# ═══════════════════════════════════════════════════════════════════════════
# C. coordinator 接线（AST 源码守卫）
#
# 🔴 为什么需要这一节：上面的判据单测与 `test_task21_room_service_pg.py` 的机制测试都
#    直连 `RoomService`，**都不会**因为 `MaterializeCoordinator` 那段接线被删而打红
#    （实测：把 `released = await ...release_stale_lease_on_pristine_room(...)` 改成
#    `released = False`，两处测试全绿）。而那段接线正是把治本能力接到用户路径上的唯一一环
#    —— 删掉它，真栈死锁立刻原样复现。本节用源码结构把它钉住（本仓库既有的 AST 守卫手法）。
# ═══════════════════════════════════════════════════════════════════════════

import ast
from pathlib import Path

_COORDINATOR = (
    Path(__file__).resolve().parents[2]
    / "app" / "services" / "workpaper_sync" / "materialize_coordinator.py"
)


def _stale_lease_branch_source() -> str:
    """取 `_join_or_reuse_participant` 里僵死 lease 分支的源码。"""
    tree = ast.parse(_COORDINATOR.read_text(encoding="utf-8"))
    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        and node.name == "_join_or_reuse_participant"
    )
    return ast.unparse(fn)


def test_the_stale_lease_branch_tries_the_pristine_release_before_superseding() -> None:
    """僵死 lease 分支必须先试轻量释放，且仅在失败后才走 revoke+supersede。"""
    src = _stale_lease_branch_source()
    assert "release_stale_lease_on_pristine_room" in src, (
        "僵死 lease 分支没有调用 release_stale_lease_on_pristine_room —— 治本能力未接线，"
        "所有僵死 lease 会重新退回「作废整代」，真栈死锁复现"
    )
    assert "join_participant" in src, (
        "释放成功后必须重新 join 一个干净 lease，否则用户拿不到 participant"
    )
    # 顺序判据：轻量释放必须出现在 revoke/supersede **之前**
    idx_release = src.index("release_stale_lease_on_pristine_room")
    idx_revoke = src.index("revoke_participant")
    idx_supersede = src.index("supersede_room")
    assert idx_release < idx_revoke < idx_supersede, (
        "顺序必须是「先试轻量释放 → 再 revoke → 再 supersede」；颠倒后 pristine room 会"
        "先被作废，轻量分支形同虚设"
    )


def test_the_conservative_path_is_still_reachable() -> None:
    """反向自检：重型路径必须仍然存在（不能为了修 pristine 而把安全反应整条删掉）。"""
    src = _stale_lease_branch_source()
    assert "revoke_participant" in src, "接管过内容的 room 仍必须能走 revoke"
    assert "supersede_room" in src, "接管过内容的 room 仍必须能被 supersede"
    assert "_ExpiredLeaseRoomSuperseded" in src, (
        "重型路径仍必须抛 _ExpiredLeaseRoomSuperseded，交由调用方转 409 stale"
    )
