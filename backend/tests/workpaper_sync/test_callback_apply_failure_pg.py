"""真库判据：回调后 apply 在协调器接手前失败 ⇒ 可见、可重试；已应用过的不能再应用一次。

spec: writeback-followup-issue-closure · R3.3 / R3.4

宿主采集（`test_task26_oo_to_html_pg.py` 的 `_collect` / `snap`）**按路径加载复用**；S22 采集体住
`task26_pre_apply_failure_world.py`。期望值由状态机语义推出（不是抄实测）：

* `queued → error`、`application_bound → error` 是登记过的边；错误码与阶段既进事件流也进 operation 行
  （`GET operation` 直接读 operation 行，前端据此显示原因）；
* `error` 是可重试态：同一协调器入口 attempt=2 落 `applied`，业务 revision +1；
* `applied` 没有出边 ⇒ 再记录失败什么也不改；同一 incoming 再申请应用 ⇒ 协调器拒绝重放
  （`application_already_applied`），路由据此回 0（R3.3，单测见 `test_callback_apply_resend.py`）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_HOST_PATH = Path(__file__).with_name("test_task26_oo_to_html_pg.py")
_spec = importlib.util.spec_from_file_location("_task26_pg_host_pre_apply_failure", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

snap = _host.snap  # noqa: F811  fixture 需在本模块命名空间


@pytest.fixture(scope="module")
def sc(snap: dict[str, Any]) -> dict[str, Any]:
    assert "pre_apply_failure" in snap["scenarios"], snap["harness_errors"]
    return snap["scenarios"]["pre_apply_failure"]


def test_world_starts_before_the_coordinator(sc: dict[str, Any]) -> None:
    assert sc["before"]["app_state"] == "queued", sc["before"]
    assert sc["before"]["revision"] == 0


def test_failure_lands_on_application_and_operation(sc: dict[str, Any]) -> None:
    assert sc["recorded"] is True, sc["recorded"]
    assert sc["mid"]["app_state"] == "error", sc["mid"]
    assert sc["app_event_after_record"] == {"to_state": "error", "error_code": "adapter_unavailable"}
    op = sc["op_after_record"]
    assert (op["state"], op["error_code"], op["error_stage"]) == ("error", "adapter_unavailable", "registry")
    assert "RegistryError" in (op["error_detail"] or "")
    assert op["last_event"] == {"to_state": "error", "error_code": "adapter_unavailable", "stage": "registry#1"}
    assert sc["mid"]["revision"] == sc["before"]["revision"], "失败不得产生业务 revision"


def test_error_is_retryable_through_the_same_coordinator_entry(sc: dict[str, Any]) -> None:
    assert "raised" not in sc["retried"], sc["retried"]
    assert sc["retried"]["result"] == "applied", sc["retried"]
    assert sc["retried"]["attempt"] == 2
    assert sc["after"]["app_state"] == "applied"
    assert sc["after"]["revision"] == sc["before"]["revision"] + 1


def test_terminal_application_is_left_alone_and_replay_is_refused(sc: dict[str, Any]) -> None:
    assert sc["recorded_again"] is False, "applied 没有到 error 的边，不得改动"
    assert sc["final"]["app_state"] == "applied"
    assert sc["final"]["revision"] == sc["after"]["revision"]
    assert sc["replay"].get("raised", "").startswith("ReapplyForbiddenError"), sc["replay"]
