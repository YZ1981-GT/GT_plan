# -*- coding: utf-8 -*-
"""OO→HTML store 镜像与 content/application/operation/outbox 的真实 PG 原子性。"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_HOST_PATH = Path(__file__).with_name("test_task26_oo_to_html_pg.py")
_spec = importlib.util.spec_from_file_location("_task26_store_atomic_host", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

snap = _host.snap  # noqa: F811


class TestStoreMirrorRollbackAndRetry:
    def test_collection_completed(self, snap: dict[str, Any]) -> None:
        assert snap["harness_errors"] == {}, snap["harness_errors"]
        assert "store_atomic" in snap["scenarios"]

    def test_second_item_failure_is_visible_and_retryable(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["store_atomic"]
        assert sc["store_insert_attempts_before_failure"] == 2
        assert sc["failed_outcome"]["result"] == "error"
        assert sc["mid"]["app_state"] == "error"
        assert "error" in sc["mid"]["operation_states"]
        assert sc["mid"]["incoming_kind"] == "incoming"
        assert sc["mid"]["incoming_state"] == "durable"

    def test_failed_mirror_rolls_back_every_business_surface(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["store_atomic"]
        for key in (
            "revision",
            "current_content_version_id",
            "entry_pointer_representation_id",
            "content_version_count",
            "room_last_applied",
            "room_latest_durable_application",
            "outbox_rows",
            "store_rows",
        ):
            assert sc["mid"][key] == sc["before"][key], f"失败后 {key} 留下半提交"
        assert sc["mid"]["app_result_revision"] is None
        assert sc["mid"]["app_result_representation"] is None

    def test_same_operation_retry_commits_exactly_once(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["store_atomic"]
        assert sc["same_operation"] is True
        assert sc["same_application"] is True
        assert sc["same_substrate"] is True
        assert sc["retried_outcome"]["result"] == "applied"
        assert sc["retried_outcome"]["attempt"] == 2
        assert sc["after"]["revision"] == sc["before"]["revision"] + 1
        assert sc["after"]["content_version_count"] == sc["before"]["content_version_count"] + 1
        assert sc["after"]["outbox_rows"] == sc["before"]["outbox_rows"] + 1

    def test_both_store_items_contain_the_retried_projection(self, snap: dict[str, Any]) -> None:
        rows = snap["scenarios"]["store_atomic"]["after"]["store_rows"]
        assert [row["item_id"] for row in rows] == list(_host.ATOMIC_STORE_ITEMS)
        payloads = {row["item_id"]: json.loads(row["remark"]) for row in rows}
        assert payloads[_host.ATOMIC_STORE_ITEMS[0]]["marker"] == "a"
        assert payloads[_host.ATOMIC_STORE_ITEMS[1]]["marker"] == "b"
        assert {payload["field_count"] for payload in payloads.values()} == {2}

    def test_all_committed_rows_share_one_postgresql_transaction(self, snap: dict[str, Any]) -> None:
        xids = snap["scenarios"]["store_atomic"]["after"]["committed_xids"]
        expected = {
            "revision",
            "content_version",
            "representation",
            "entry_pointer",
            "application",
            "operation",
            "outbox",
            *{f"store:{item}" for item in _host.ATOMIC_STORE_ITEMS},
        }
        assert set(xids) == expected, xids
        assert len(set(xids.values())) == 1, xids
