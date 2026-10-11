"""Task 26 真库判据的 D1 部分：application 终态 ⇒ 绑在它上面的 request 同事务终结。

拆分自 `test_task26_oo_to_html_pg.py`（宿主在行数门禁 whitelist 上：基线 3493 +5% = 3667，
D1 判据放进去会顶过）。宿主的采集（`_collect` / `snap` fixture）**按路径加载复用**，不抄第二份；
S20 采集体住 `task26_d1_settlement_world.py`，由宿主 `_collect` 调用。

两个文件一起跑时 `_collect` 会各跑一次（module scope fixture 按模块实例化），代价约 25 s。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_HOST_PATH = Path(__file__).with_name("test_task26_oo_to_html_pg.py")
_spec = importlib.util.spec_from_file_location("_task26_pg_host", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

snap = _host.snap  # noqa: F811  fixture 需在本模块命名空间


# ═══════════════════════════════════════════════════════════════════════════
# D1：application 终态 ⇒ 绑在它上面的 request 同事务终结
# ═══════════════════════════════════════════════════════════════════════════

#: 每个场景末态 application 落什么、它的 request 该落什么（期望值由语义推出，不是抄实测）：
#: 终态 application ⇒ `REQUEST_STATE_FOR_TERMINAL_APPLICATION`；非终态（conflict / error）
#: ⇒ request 必须**仍是** `correlated` —— 裁决 / 重试还可能把内容应用上去。
_D1_FINAL_REQUEST_STATE: dict[str, tuple[str, str, str]] = {
    # 场景: (读哪一相, 期望 application 状态, 期望 request 状态)
    "applied": ("after", "applied", "terminal"),
    "refresh": ("after", "refresh_required", "terminal"),
    "close_capture_ok": ("after", "applied", "terminal"),
    "adjudication_applied": ("after", "applied", "terminal"),
    "fence_before_publish": ("after", "authorization_stale", "authorization_stale"),
    "fence_before_write": ("after", "authorization_stale", "authorization_stale"),
    "bundle_swap": ("after", "authorization_stale", "authorization_stale"),
    "initiator_revoked": ("after", "authorization_stale", "authorization_stale"),
    "contributor_revoked": ("after", "authorization_stale", "authorization_stale"),
    "close_capture_stale": ("after", "authorization_stale", "authorization_stale"),
    "conflict": ("after", "conflict", "correlated"),
    "row_conflict": ("after", "conflict", "correlated"),
    "unmanaged_drift": ("after", "error", "correlated"),
    "probe_broken": ("after", "error", "correlated"),
    "probe_incomplete": ("after", "error", "correlated"),
}


class TestD1RequestSettlementOnTerminalApplication:
    """修前：`correlated → terminal` 这条登记边全仓零生产写入方。

    三个消费方都以「request 已终结」为前提：participant 主动离开的 in-flight 门、close
    barrier 的 predecessor 计数、editor destroy 闸。于是保存成功后 initiator 永远离不开
    （真库：重药安徽 3 次 applied 全停 `correlated`，离开恒 409）。
    """

    def test_collection_did_not_crash(self, snap: dict[str, Any]) -> None:
        """本模块的 `snap` 是独立一次采集：它挂了，下面每条都会以 KeyError 形态出现。"""
        assert snap["harness_errors"] == {}, snap["harness_errors"]
        assert "settlement" in snap["scenarios"]

    @pytest.mark.parametrize("scenario", sorted(_D1_FINAL_REQUEST_STATE), ids=lambda v: v)
    def test_request_follows_the_application_outcome(
        self, snap: dict[str, Any], scenario: str
    ) -> None:
        phase, app_state, request_state = _D1_FINAL_REQUEST_STATE[scenario]
        st = snap["scenarios"][scenario][phase]
        assert st["app_state"] == app_state, (scenario, st["app_state"])
        assert st["request_states"] == [request_state], (
            f"{scenario}: application={app_state} 时 request 应为 {request_state}，"
            f"实得 {st['request_states']}"
        )
        terminal = request_state != "correlated"
        assert st["requests_finished"] == (1 if terminal else 0), (
            f"{scenario}: finished_at 只在 request 终结时写（实得 {st['requests_finished']}）"
        )

    @pytest.mark.parametrize(
        "scenario", ["applied", "refresh", "conflict", "fence_before_write"], ids=lambda v: v
    )
    def test_request_is_correlated_before_apply(
        self, snap: dict[str, Any], scenario: str
    ) -> None:
        """前置自证：apply 之前 request 是 `correlated`（否则「之后变 terminal」不证明任何事）。"""
        st = snap["scenarios"][scenario]["before"]
        assert st["request_states"] == ["correlated"], st["request_states"]
        assert st["requests_finished"] == 0

    def test_retry_keeps_the_request_open_until_the_content_lands(
        self, snap: dict[str, Any]
    ) -> None:
        """error 可重试 ⇒ 中间态仍 `correlated`；重试成功后才终结。"""
        sc = snap["scenarios"]["retry"]
        assert sc["mid"]["app_state"] == "error"
        assert sc["mid"]["request_states"] == ["correlated"]
        assert sc["after"]["app_state"] == "applied"
        assert sc["after"]["request_states"] == ["terminal"]

    def test_conflict_then_adjudication_settles_only_at_the_end(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["adjudication_applied"]
        assert sc["before"]["app_state"] == "conflict"
        assert sc["before"]["request_states"] == ["correlated"]
        assert sc["after"]["request_states"] == ["terminal"]

    def test_reapply_refusal_does_not_rewrite_a_settled_request(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["reapply"]
        assert sc["after_first"]["request_states"] == ["terminal"]
        assert sc["after_second"]["request_states"] == ["terminal"]
        assert sc["after_second"]["requests_finished"] == 1

    @pytest.mark.parametrize(
        "scenario,expected",
        [
            ("applied", ["applied"]),
            ("refresh", ["refresh_required"]),
            ("fence_before_publish", ["authorization_stale"]),
            ("conflict", []),
            ("unmanaged_drift", []),
        ],
        ids=lambda v: v if isinstance(v, str) else None,
    )
    def test_operation_finished_at_is_written_only_on_terminal(
        self, snap: dict[str, Any], scenario: str, expected: list[str]
    ) -> None:
        """触类旁通：OO→HTML 路径此前从不写 `operation.finished_at`（快照恒 null）。"""
        assert snap["scenarios"][scenario]["after"]["operations_finished"] == expected

    # ── S20：离开被拒 → apply → 离开放行；折叠 duplicate；supersede ──────────

    def test_settlement_scenario_applied(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["settlement"]["outcome"]["result"] == "applied"

    def test_leave_is_refused_while_the_content_is_not_yet_applied(
        self, snap: dict[str, Any]
    ) -> None:
        """修复不得放宽 in-flight 门：内容未应用时仍拒。"""
        got = snap["scenarios"]["settlement"]["leave_before"]
        assert got["left"] is False, got
        assert got["error_code"] == "participant_leave_refused_in_flight", got

    def test_leave_is_allowed_once_the_content_is_applied(
        self, snap: dict[str, Any]
    ) -> None:
        """D1 本体：保存成功后同一 participant 能离开（修前恒 409）。"""
        got = snap["scenarios"]["settlement"]["leave_after"]
        assert got == {"left": True, "already_left": False}, got

    def test_the_second_save_really_folded_into_the_same_application(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["settlement"]
        assert sc["fold"] == {"shape": "duplicate", "same_application": True}, sc["fold"]
        assert sorted(r["state"] for r in sc["requests_before"].values()) == [
            "correlated",
            "correlated",
        ]

    def test_origin_and_folded_request_both_settle(self, snap: dict[str, Any]) -> None:
        """只结 `origin_request_id` 时，后发保存的那条（duplicate shell）照样停 correlated。"""
        sc = snap["scenarios"]["settlement"]
        after = sc["requests_after"]
        for key in ("origin_request", "folded_request"):
            row = after[sc[key]]
            assert row == {**row, "state": "terminal", "finished": True}, (key, row)

    def test_settlement_is_idempotent(self, snap: dict[str, Any]) -> None:
        """已结算的 application 再结算 ⇒ 零改写、不抛。"""
        assert snap["scenarios"]["settlement"]["resettle"] == {"settled": []}

    def test_supersede_settles_the_old_request_only(self, snap: dict[str, Any]) -> None:
        sup = snap["scenarios"]["settlement"]["supersede"]
        rows = sup["requests"]
        assert rows[sup["old_request"]]["state"] == "superseded", rows
        assert rows[sup["old_request"]]["finished"] is True
        assert rows[sup["new_request"]]["state"] == "correlated", (
            "新 application 尚未应用 ⇒ 它的 request 必须仍 open"
        )
        assert rows[sup["new_request"]]["finished"] is False
