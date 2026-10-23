"""真库判据：文档服务器已最终保存 ⇒ room closed；关闭之后的 apply 仍能落库。

spec: writeback-followup-issue-closure · R1.1 / R1.5（D1 / D2）

宿主采集（`test_task26_oo_to_html_pg.py` 的 `_collect` / `snap`）**按路径加载复用**；S21 采集体住
`task26_closed_room_world.py`。两个文件一起跑时 `_collect` 各跑一次（module scope fixture）。

判据的期望值由语义推出（不是抄实测）：

* 关闭只改 room 状态，apply 照常产生一个 business revision、推进 server last-applied；
* 已关闭 room 没有在线客户端 ⇒ client-confirmed 基线不推进、不进 refresh-required、不被
  supersede（这三步对 `closed` 都是非法边，修前 apply 在最后一步失败）；
* application 终态语义不变：merged == incoming ⇒ `applied`，否则 `refresh_required`。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_HOST_PATH = Path(__file__).with_name("test_task26_oo_to_html_pg.py")
_spec = importlib.util.spec_from_file_location("_task26_pg_host_closed_room", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

snap = _host.snap  # noqa: F811  fixture 需在本模块命名空间

#: 分支 → 期望的 application / 结果终态（merged == incoming 与否）
_BRANCH_RESULT = {"equal": "applied", "differs": "refresh_required"}


def _scenario(snap: dict[str, Any]) -> dict[str, Any]:
    assert "closed_room" in snap["scenarios"], snap["harness_errors"]
    return snap["scenarios"]["closed_room"]


@pytest.mark.parametrize("branch", sorted(_BRANCH_RESULT))
class TestApplyOnAClosedRoom:
    def test_close_lands_closed_and_is_idempotent(self, snap: dict[str, Any], branch: str) -> None:
        sc = _scenario(snap)[branch]
        assert sc["first_close"] == {"state": "closed"}, sc["first_close"]
        assert sc["second_close"] == {"state": "closed"}, "重发的 status 2 回调必须幂等"
        assert sc["room_after_close"]["closed_at_set"] is True, sc["room_after_close"]
        assert sc["before"]["room_state"] == "closed"

    def test_apply_still_lands_with_unchanged_result_semantics(
        self, snap: dict[str, Any], branch: str
    ) -> None:
        sc = _scenario(snap)[branch]
        assert "raised" not in sc["outcome"], sc["outcome"]
        assert sc["outcome"]["result"] == _BRANCH_RESULT[branch], sc["outcome"]
        assert sc["after"]["app_state"] == _BRANCH_RESULT[branch], sc["after"]
        assert sc["after"]["revision"] == sc["before"]["revision"] + 1
        assert sc["after"]["room_last_applied"] != sc["before"]["room_last_applied"], (
            "server last-applied 每次成功应用都推进（AC 2.9 前半句），与 room 是否关闭无关"
        )

    def test_closed_room_is_left_alone(self, snap: dict[str, Any], branch: str) -> None:
        """不推进 client 基线、不进 refresh-required、不被 supersede。"""
        sc = _scenario(snap)[branch]
        assert sc["after"]["room_state"] == "closed", sc["after"]
        assert sc["after"]["room_refresh_required_at"] is None, sc["after"]
        assert (
            sc["after"]["room_client_confirmed_version"]
            == sc["before"]["room_client_confirmed_version"]
        ), "已关闭 room 没有在线客户端，client-confirmed 基线不得被推进"


@pytest.mark.parametrize(
    ("start", "state"),
    [("superseded", "superseded"), ("recovery_required", "recovery_required")],
)
def test_close_leaves_terminal_and_recovery_rooms_untouched(
    snap: dict[str, Any], start: str, state: str
) -> None:
    """已终结的不重复关；待恢复的只能去 superseded，关闭不得抢掉恢复流程。"""
    sc = _scenario(snap)[start]
    assert sc["close"] == {"state": state}, sc["close"]
    assert sc["room"]["state"] == state, sc["room"]
    assert sc["room"]["closed_at_set"] is False, sc["room"]
