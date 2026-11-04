"""render 快照版本 == CAS 预检的服务端版本（真 PG 往返，K1~K13 / D2 保存 428 的回归守卫）。

版本令牌是 ``updated_at.isoformat()``，asyncpg 把 ``timestamptz`` 解成带时区的 datetime；快照与 CAS 预检两处
各自取 ``updated_at``，字符串只要差一个字符（时区写法、微秒位数），``if_match`` 就恒判冲突。SQLite 存文本、
CAS 预检在 SQLite 上根本跑不通 ⇒ 真 PG。

- 会话：``tests.formula_hub._pg_harness.pg_tx_session``（独立连接 + 外层事务，退出一律回滚，不留数据）；
- 正向：快照带出的 version 原样当 ``if_match``，``require_if_match=True`` 的预检通过；
- 反向对照：同一行不带 ``if_match`` 时预检返回 428 —— 不红说明这一行没被当成「已有行」，正向断言就是空转。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi import HTTPException

from app.services.checklist_response_cas import lock_and_check_versions
from app.services.four_table.tb_fetch import load_responses_snapshot
from tests.formula_hub._pg_harness import pg_tx_session

pytestmark = [pytest.mark.asyncio, pytest.mark.pg_only]


async def _existing_row(db):
    """在任意一张现存底稿上插一行 checklist（外层事务回滚即消失），返回 (wp_id, item_id, 前缀)。"""
    wp = (await db.execute(sa.text("SELECT id, project_id FROM working_paper LIMIT 1"))).fetchone()
    if wp is None:
        pytest.skip("库里没有底稿行，无法挂 checklist_responses 外键")
    prefix = f"K9-ZZCAS{uuid.uuid4().hex[:8]}"
    item_id = f"{prefix}-1"
    await db.execute(
        sa.text(
            "INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark) "
            "VALUES (:pid, :wid, :iid, NULL, '原值')"
        ),
        {"pid": str(wp.project_id), "wid": str(wp.id), "iid": item_id},
    )
    return wp.id, item_id, prefix


async def test_snapshot_version_passes_strict_cas_precheck():
    async with pg_tx_session() as db:
        wp_id, item_id, prefix = await _existing_row(db)
        snapshot = await load_responses_snapshot(SimpleNamespace(db=db, wp_id=wp_id), prefix)
        version = snapshot[item_id].get("version")
        assert version, f"快照条目没有版本：{snapshot[item_id]!r}"

        server = await lock_and_check_versions(
            db, wp_id, [SimpleNamespace(item_id=item_id, if_match=version)], require_if_match=True,
        )
        assert server == {item_id: version}


async def test_negative_control_without_if_match_is_428():
    async with pg_tx_session() as db:
        wp_id, item_id, _ = await _existing_row(db)
        with pytest.raises(HTTPException) as caught:
            await lock_and_check_versions(
                db, wp_id, [SimpleNamespace(item_id=item_id, if_match=None)], require_if_match=True,
            )
        assert caught.value.status_code == 428
