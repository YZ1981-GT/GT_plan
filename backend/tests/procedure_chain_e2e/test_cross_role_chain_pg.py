"""程序链跨角色端到端（spec procedure-chain-hardening-and-java-contracts R21）。

真实 PostgreSQL + 真实 FastAPI 应用（全部中间件、注册表、底稿门）。一个外层事务（``create_savepoint``：路由里的
commit / rollback 只动保存点），结束整体回滚、不落库；底稿文件生成到临时目录。

三种角色：系统管理员；项目经理（唯一人员档案 + 团队分配 manager + 项目成员 edit：可裁剪、委派、生成）；
审计员（团队分配勾选 D 循环 + 项目成员 edit）。按界面上的真实顺序走一遍：

1. 经理按编码生成 D1 / D2 / H3；
2. 经理粗裁 H3：已生成的 H3 移入回收站（生命周期事件记移入人；回收站「删除人」= 经理）；
3. 再生成 H3 / H3-1：两个都按「已裁」跳过，不建；
4. 审计员不能裁剪、不能委派（403）；
5. 经理把 D2 委派给审计员；
6. 可见：审计员列表只有 D2，打开 D1 / H3 都是 404（不暴露存在性）；经理、管理员看到 D1 / D2；
7. 编辑锁：审计员取 D2 → 经理取同一把 409（带持有人）、放不掉别人的锁 → 审计员释放 → 经理取到；审计员取 D1 404；
8. 经理恢复执行 H3：H3 从回收站恢复（事件记恢复），审计员仍打不开（不在其循环）；
9. 再生成 H3 / H3-1：H3 已存在、H3-1 新建。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models.procedure_models import ProcedureRowTask
from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL
from app.services.wp_visibility.epoch_cache import reset_epoch_cache
from tests.procedure_chain_e2e import _chain_world as cw

pytestmark = [pytest.mark.pg_only, pytest.mark.asyncio]


async def test_trim_generate_delegate_visibility_lock_restore_chain(db, tmp_path):
    s = db
    await cw.ensure_lifecycle_table(s)
    w = await cw.world(s)
    pid = w.pid

    # 1. 经理按编码生成：文件落在临时存储目录（不写真实存储）
    async with cw.client(s, w.manager) as c:
        first = await cw.generate(c, pid, ["D1", "D2", "H3"])
    assert first["created_codes"] == ["D1", "D2", "H3"], first
    assert (first["failures"], first["skipped_trimmed_codes"], first["in_recycle_codes"]) == ([], [], [])
    papers = await cw.papers(s, pid)
    storage = (tmp_path / "wp_storage").resolve()
    for code in ("D1", "D2", "H3"):
        path = Path(papers[code].file_path).resolve()
        assert path.is_file() and storage in path.parents, (code, path)
    wp = {code: papers[code].id for code in papers}

    # 2. 经理粗裁 H3：已生成的 H3 移入回收站
    async with cw.client(s, w.manager) as c:
        preview, trimmed, trim_request = await cw.trim(c, pid, cw.h3_entry("not_applicable", "本期无投资性房地产"))
        assert preview["recycle_preview"]["to_recycle"] == ["H3"], preview["recycle_preview"]
        assert preview["recycle_preview"]["substantive"] == [], "刚生成、没编制过的底稿不需要二次确认"
        assert (trimmed["recycled_codes"], trimmed["restored_codes"]) == (["H3"], [])
        rb = await c.get("/api/recycle-bin", params={"item_type": "working_paper"})
    assert rb.status_code == 200, rb.text
    index = await cw.index_rows(s, pid)
    assert index["H3"].is_deleted is True and index["D2"].is_deleted is False
    assert await cw.events(s, pid) == [("H3", "recycled", "trim", str(w.manager.id), trim_request)]
    [h3_item] = [i for i in cw.data(rb)["items"] if i["id"] == str(index["H3"].id)]
    assert h3_item["deleted_by"] == str(w.manager.id) and h3_item["deleted_by_name"], h3_item

    # 3. 再生成 H3 / H3-1：已裁优先于「在回收站」，两个都跳过、不建
    async with cw.client(s, w.manager) as c:
        again = await cw.generate(c, pid, ["H3", "H3-1"])
    assert (again["created_codes"], again["skipped_trimmed_codes"]) == ([], ["H3", "H3-1"]), again
    assert (again["in_recycle_codes"], again["existing_codes"]) == ([], [])
    assert "H3-1" not in await cw.index_rows(s, pid)

    # 4. 审计员不能裁剪、不能委派
    delegation = {"selector": {"kind": "workpaper", "wp_index_ids": [str(index["D2"].id)]},
                  "assignee_staff_id": str(w.a_staff.id)}
    async with cw.client(s, w.auditor) as c:
        r = await c.post(f"/api/projects/{pid}/procedure-trim/preview", json={"entries": [cw.h3_entry("execute")]})
        assert r.status_code == 403, r.text
        r = await c.post(f"/api/projects/{pid}/procedure-delegations/preview", json=delegation)
        assert r.status_code == 403, r.text

    # 5. 经理把 D2 委派给审计员
    async with cw.client(s, w.manager) as c:
        pv = await c.post(f"/api/projects/{pid}/procedure-delegations/preview", json=delegation)
        assert pv.status_code == 200, pv.text
        dpv = cw.data(pv)
        assert dpv["preparation_ready"] is True and dpv["summary"]["would_assign"] > 0, dpv["summary"]
        ap = await c.post(f"/api/projects/{pid}/procedure-delegations/apply", json={
            **delegation, "preview_id": dpv["preview_id"], "request_id": f"r21-del-{uuid.uuid4().hex[:8]}"})
        assert ap.status_code == 200, ap.text
    applied = cw.data(ap)["applied"]
    assert applied == dpv["summary"]["would_assign"]
    assigned = (await s.execute(sa.select(sa.func.count()).select_from(ProcedureRowTask).where(
        ProcedureRowTask.project_id == pid, ProcedureRowTask.wp_index_id == index["D2"].id,
        ProcedureRowTask.assignee_staff_id == w.a_staff.id, ProcedureRowTask.is_deleted == sa.false(),
    ))).scalar_one()
    assert assigned == applied


    # 6. 可见：审计员只看到被委派的 D2；打开别的底稿 404 且不暴露存在性
    reset_epoch_cache()
    detail = f"/api/projects/{pid}/working-papers/{{}}"
    listing = f"/api/projects/{pid}/working-papers"
    async with cw.client(s, w.auditor) as c:
        r = await c.get(listing, params={"page_size": 100})
        assert r.status_code == 200, r.text
        assert [i["wp_code"] for i in cw.data(r)["items"]] == ["D2"]
        assert (await c.get(detail.format(wp["D2"]))).status_code == 200
        for code in ("D1", "H3"):
            r = await c.get(detail.format(wp[code]))
            assert r.status_code == 404 and cw.wire_detail(r) == EXTERNAL_NOT_FOUND_DETAIL, (code, r.text)
        rc = await c.get(f"/api/workpapers/{wp['D2']}/render-config")
        assert not (rc.status_code == 404 and cw.wire_detail(rc) == EXTERNAL_NOT_FOUND_DETAIL), rc.text
    for who in ("manager", "admin"):
        async with cw.client(s, getattr(w, who)) as c:
            r = await c.get(listing, params={"page_size": 100})
            assert r.status_code == 200, (who, r.text)
            assert [i["wp_code"] for i in cw.data(r)["items"]] == ["D1", "D2"], who
            assert (await c.get(detail.format(wp["D1"]))).status_code == 200, who
            assert (await c.get(detail.format(wp["H3"]))).status_code == 404, f"{who}：回收站里的底稿打不开"

    # 7. 编辑锁
    lock = "/api/editing-locks/workpaper/{}"
    async with cw.client(s, w.auditor) as c:
        assert (await c.post(lock.format(wp["D2"]))).status_code == 200
        r = await c.post(lock.format(wp["D1"]))
        assert r.status_code == 404 and cw.wire_detail(r) == EXTERNAL_NOT_FOUND_DETAIL, r.text
    async with cw.client(s, w.manager) as c:
        r = await c.post(lock.format(wp["D2"]))
        assert r.status_code == 409, r.text
        held = cw.wire_detail(r)
        assert held["error_code"] == "LOCK_HELD" and held["locked_by"] == str(w.auditor.id), held
        assert (await c.delete(lock.format(wp["D2"]))).status_code == 404, "只有持有人能释放"
    async with cw.client(s, w.auditor) as c:
        assert (await c.delete(lock.format(wp["D2"]))).status_code == 200
    async with cw.client(s, w.manager) as c:
        assert (await c.post(lock.format(wp["D2"]))).status_code == 200
        assert (await c.delete(lock.format(wp["D2"]))).status_code == 200
    async with cw.client(s, w.admin) as c:
        assert (await c.post(lock.format(wp["D1"]))).status_code == 200
        assert (await c.delete(lock.format(wp["D1"]))).status_code == 200

    # 8. 经理恢复执行 H3：从回收站恢复
    async with cw.client(s, w.manager) as c:
        preview, restored, restore_request = await cw.trim(c, pid, cw.h3_entry("execute"))
    assert preview["recycle_preview"]["to_restore"] == ["H3"], preview["recycle_preview"]
    assert (restored["restored_codes"], restored["recycled_codes"]) == (["H3"], [])
    assert (await cw.index_rows(s, pid))["H3"].is_deleted is False
    assert await cw.events(s, pid) == [("H3", "recycled", "trim", str(w.manager.id), trim_request),
                                     ("H3", "restored", "trim", str(w.manager.id), restore_request)]
    reset_epoch_cache()
    async with cw.client(s, w.manager) as c:
        assert (await c.get(detail.format(wp["H3"]))).status_code == 200
    async with cw.client(s, w.auditor) as c:
        r = await c.get(detail.format(wp["H3"]))
        assert r.status_code == 404 and cw.wire_detail(r) == EXTERNAL_NOT_FOUND_DETAIL, "H3 不在审计员的循环范围"

    # 9. 再生成 H3 / H3-1：H3 已存在、H3-1 新建
    async with cw.client(s, w.manager) as c:
        final = await cw.generate(c, pid, ["H3", "H3-1"])
    assert (final["existing_codes"], final["created_codes"]) == (["H3"], ["H3-1"]), final
    assert (final["skipped_trimmed_codes"], final["in_recycle_codes"], final["failures"]) == ([], [], [])
