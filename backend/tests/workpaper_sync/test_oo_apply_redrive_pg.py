"""真库判据：中断的 OO→HTML apply 由重驱候选查询选中，且只选该选的。

spec: writeback-followup-issue-closure · R3.2

宿主采集（`test_task26_oo_to_html_pg.py` 的 `_collect` / `snap`）**按路径加载复用**；S23 采集体住
`task26_redrive_world.py`。期望值由语义推出：停在 apply 中途且一小时没有推进 ⇒ 是候选（连同它的
primary operation），多条时先选建得早的；最近一次事件在 5 分钟内 / 落 `error` / 落 `conflict` ⇒ 不是；
协调器同一入口 attempt=2 能从中途那一站续跑到 `applied`，之后不再是候选。worker 的循环与选主见
`test_oo_apply_redrive_worker.py`。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_HOST_PATH = Path(__file__).with_name("test_task26_oo_to_html_pg.py")
_spec = importlib.util.spec_from_file_location("_task26_pg_host_redrive", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

snap = _host.snap  # noqa: F811  fixture 需在本模块命名空间


@pytest.fixture(scope="module")
def sc(snap: dict[str, Any]) -> dict[str, Any]:
    assert "redrive" in snap["scenarios"], snap["harness_errors"]
    return snap["scenarios"]["redrive"]


def test_recent_activity_is_not_a_candidate(sc: dict[str, Any]) -> None:
    assert sc["fresh"] is None, "刚归组、5 分钟内有推进的 apply 不得被重驱"
    assert sc["touched_again"] is None, "一小时前建行但刚写过事件 ⇒ 仍在推进（判据看事件，不看建行时间）"


def test_stale_queued_application_is_picked_with_its_operation(sc: dict[str, Any]) -> None:
    assert sc["aged"] == [sc["ids"]["app"], sc["ids"]["op"]]


def test_oldest_stuck_application_goes_first(sc: dict[str, Any]) -> None:
    assert sc["oldest_first"] == [sc["ids"]["other_app"], sc["ids"]["other_op"]]


@pytest.mark.parametrize(
    "station", ["queued", "validating", "extracting", "merging", "rematerializing", "applying"]
)
def test_every_mid_apply_station_is_a_candidate(sc: dict[str, Any], station: str) -> None:
    assert sc["stations"][station] == [sc["ids"]["app"], sc["ids"]["op"]], f"停在 {station} 的中断 apply 没被选中"


@pytest.mark.parametrize("state", ["error", "conflict"])
def test_error_and_conflict_wait_for_the_user(sc: dict[str, Any], state: str) -> None:
    assert sc["excluded"][state] is None, f"{state} 不是中断，不得被重驱"


def test_same_entry_resumes_from_the_interrupted_station(sc: dict[str, Any]) -> None:
    assert sc["before_redrive"]["app_state"] == "validating", sc["before_redrive"]
    assert "raised" not in sc["redriven"], sc["redriven"]
    assert sc["redriven"]["result"] == "applied", sc["redriven"]
    assert sc["after"]["app_state"] == "applied"
    assert sc["after"]["revision"] == sc["before_redrive"]["revision"] + 1, "续跑只产出一个业务 revision"
    assert sc["after_redrive_find"] is None, "applied 之后不再是候选"
