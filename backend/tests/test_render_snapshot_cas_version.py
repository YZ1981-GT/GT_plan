"""render 快照条目带 CAS 版本（K1~K13 / D2 保存 428 的回归守卫）。

K1~K13 与 D2 的宿主只用 render 快照建编辑基线（快照非空就不再 GET），保存走严格 CAS：
``PUT /checklist-responses`` 带 ``require_if_match=true``，已有行缺 ``if_match`` 返回 428。快照条目原先
只有 conclusion / remark ⇒ 已有行改一次就 428（2026-11-04 浏览器实测：K9-8「是否异常」开关）。

- 快照构造点逐个覆盖：共享 ``load_responses_snapshot``（K3~K13）、K1 / K2 / D2 内联查询；
- fake 会话只在 SELECT 列表含 ``updated_at`` 时给行带该列 ⇒ 查询漏选这一列即红；
- K1 坏账 seed 换了显示内容也要保留库里这一行的版本；
- 版本写法与 GET 回执同口径（真 PG 往返见 ``test_render_snapshot_cas_version_pg.py``）。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.checklist_responses import _version_of
from app.routers.wp_render_strategies import _d2_accounts_receivable as d2
from app.routers.wp_render_strategies import _g1_trading_financial_assets as g1
from app.routers.wp_render_strategies import _k1_other_receivables as k1
from app.routers.wp_render_strategies import _k2_other_current_assets as k2
from app.services.checklist_response_cas import (
    checklist_response_version,
    checklist_snapshot_entry,
)
from app.services.four_table.k1_detail_seed import K1_BAD_DEBT_ITEM_ID, seed_k1_bad_debt
from app.services.four_table.tb_fetch import load_responses_snapshot

UPDATED_AT = datetime(2026, 11, 4, 1, 2, 3, 456789, tzinfo=timezone.utc)
VERSION = UPDATED_AT.isoformat()


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _SnapshotSession:
    """只回答 checklist_responses 查询：SELECT 列表选了 updated_at 才给行带该列；其余查询一律抛错（走 fail-open）。"""

    def __init__(self, item_ids):
        self.item_ids = list(item_ids)
        self.checklist_sql: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM checklist_responses" in sql:
            self.checklist_sql.append(sql)
            selects_version = "updated_at" in sql.split("FROM", 1)[0]
            rows = []
            for item_id in self.item_ids:
                cols = {"item_id": item_id, "conclusion": None, "remark": f"{item_id} 的值"}
                if selects_version:
                    cols["updated_at"] = UPDATED_AT
                rows.append(SimpleNamespace(**cols))
            return _Rows(rows)
        raise RuntimeError("本用例只测 checklist 快照")

    async def rollback(self):
        return None


def _ctx(db):
    return SimpleNamespace(
        db=db, project_id=uuid4(), wp_id=uuid4(), year=2025,
        business_category="", classification=None,
    )


# ── 条目写法 ────────────────────────────────────────────────────────────────


def test_entry_version_is_the_same_string_get_returns():
    row = SimpleNamespace(item_id="K9-8-row", conclusion=None, remark="说明", updated_at=UPDATED_AT)
    entry = checklist_snapshot_entry(row)
    assert entry == {"conclusion": "", "remark": "说明", "version": VERSION}
    # GET /checklist-responses 回执的 version 与 CAS 预检的服务端版本都是 updated_at.isoformat()
    assert entry["version"] == _version_of(UPDATED_AT)


def test_entry_without_updated_at_has_no_version():
    """没有这一行版本时不造版本（新行可不带 if_match 新建；既有 fake 行形态照旧可用）。"""
    entry = checklist_snapshot_entry(SimpleNamespace(item_id="K1-x", conclusion="Y", remark=None))
    assert entry == {"conclusion": "Y", "remark": ""}


@pytest.mark.parametrize(("value", "expected"), [(None, None), ("", None), ("2026-11-04 01:02:03", "2026-11-04 01:02:03")])
def test_version_of_non_datetime_values(value, expected):
    assert checklist_response_version(value) == expected


# ── 四个快照构造点 ────────────────────────────────────────────────────────


def test_shared_loader_used_by_k3_to_k13_carries_version():
    db = _SnapshotSession(["K9-8-a", "K9-8-b"])
    snapshot = asyncio.run(load_responses_snapshot(_ctx(db), "K9"))
    assert db.checklist_sql, "没有执行 checklist 查询"
    assert {item: entry.get("version") for item, entry in snapshot.items()} == {
        "K9-8-a": VERSION, "K9-8-b": VERSION,
    }


@pytest.mark.parametrize(("module", "item_id"), [(k1, "K1-1-note"), (k2, "K2-1-note")], ids=["K1", "K2"])
def test_k1_k2_inline_snapshot_carries_version(module, item_id):
    db = _SnapshotSession([item_id])
    out = asyncio.run(module.render(_ctx(db)))
    assert db.checklist_sql, "没有执行 checklist 查询"
    assert out["responses_snapshot"][item_id] == {
        "conclusion": "", "remark": f"{item_id} 的值", "version": VERSION,
    }


def test_d2_inline_snapshot_carries_version(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    db = _SnapshotSession(["D2-vc-current-rows"])  # D2-7 凭证检查「本期增减变动」区的持久化键
    out = asyncio.run(d2.render(_ctx(db)))
    assert db.checklist_sql, "没有执行 checklist 查询"
    assert out["responses_snapshot"]["D2-vc-current-rows"]["version"] == VERSION


def test_g1_inline_snapshot_carries_version():
    """G1 在 checklist GET 降级到 render 快照时也必须保留 strict CAS 基线。"""
    db = _SnapshotSession(["G1-1-adjudicated-amount"])
    out = asyncio.run(g1.render(_ctx(db)))
    assert db.checklist_sql, "没有执行 checklist 查询"
    assert out["responses_snapshot"]["G1-1-adjudicated-amount"]["version"] == VERSION


# ── seed 不丢编辑基线 ──────────────────────────────────────────────────────


def test_k1_bad_debt_seed_keeps_the_row_version():
    snapshot = {K1_BAD_DEBT_ITEM_ID: {"conclusion": "", "remark": "", "version": VERSION}}
    payload = {"mainRows": [{"category": "portfolio", "isSubRow": False, "priorBook": 10.0}]}
    assert seed_k1_bad_debt(snapshot, payload) is True
    entry = snapshot[K1_BAD_DEBT_ITEM_ID]
    assert entry["version"] == VERSION
    assert entry["remark"] != ""  # 显示内容确实换成了 seed


def test_k1_bad_debt_seed_on_a_new_row_adds_no_version():
    snapshot: dict = {}
    payload = {"mainRows": [{"category": "portfolio", "isSubRow": False, "priorBook": 10.0}]}
    assert seed_k1_bad_debt(snapshot, payload) is True
    assert "version" not in snapshot[K1_BAD_DEBT_ITEM_ID]
