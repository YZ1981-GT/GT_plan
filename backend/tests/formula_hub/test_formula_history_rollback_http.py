"""公式历史一键回滚带当前修订号（第 2 轮 D-2，需求 13.1 / 13.3），全部经 HTTP。

阶段 D 浏览器实测：界面回滚请求体不带 ``expected_version``、历史条目也没有当前版本可带 ⇒ 后端恒 428。
本文件按界面的真实顺序走：``GET`` 历史列表 → 取条目的 ``current_version`` → ``POST …/rollback``；
按生产注册挂 router，鉴权链（``require_role`` + 函数体内本项目 review 级成员校验）真实运行，
只替换 ``get_current_user`` / ``get_db``；下游只把提交后的「定义已变化」事件换成计数桩。
"""
from __future__ import annotations

import pytest

from app.services.formula_settings import project_ops
from app.services.formula_settings.publish import publish_global
from tests.formula_hub._history_http import history, http_client
from tests.formula_settings._env import STD, add_global_row, add_project, add_user, make_db, project_rows

OLD, MINE, NEW = "TB('1001','期末余额')", "ROW('BS-009')", "TB('1001','期末余额')*2"
SLOT = "balance_sheet:BS-001"


@pytest.fixture
def events(monkeypatch):
    """提交后的变更事件（只记次数，不出进程）。"""
    sent: list[dict] = []

    async def _publish(evts, *, domain, source, token=None):
        sent.append({"events": list(evts), "domain": domain, "source": source})
        return len(sent[-1]["events"])

    monkeypatch.setattr("app.services.formula_settings.propagation.publish_events", _publish)
    return sent


async def _rollback(http, pid, entry: dict, **extra):
    body = {"row_code": entry["row_code"], "module": entry["module"], "source_log_id": entry["id"], **extra}
    return await http.post(f"/api/formula-audit-log/{pid}/2025/rollback", json=body)


async def _seed_adapted(db):
    admin = await add_user(db, "fhic_rollback_admin", "admin")
    await add_global_row(db, "BS-001", OLD)
    pid = await add_project(db, "回滚本项目")
    await db.commit()
    out = await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None,
                                           items=[{"slot_key": SLOT, "definition": {"formula": MINE}}])
    await db.commit()
    return admin, pid, out["saved"][0]["version"]


async def test_list_version_drives_rollback_and_stale_or_missing_version_is_rejected(events):
    async with make_db() as factory, factory() as db:
        admin, pid, version = await _seed_adapted(db)
        async with http_client(db, admin) as http:
            [entry] = [i for i in await history(http, pid, 2025) if i["operation"] == "adapt"]
            assert (entry["rollbackable"], entry["current_version"]) == (True, version)

            stale = await _rollback(http, pid, entry, expected_version=version + 1)
            assert stale.status_code == 409, stale.text
            missing = await _rollback(http, pid, entry)
            assert missing.status_code == 428, missing.text
            assert (await project_rows(db, pid))["BS-001"].formula == MINE, "拒绝的回滚不得改本项目定义"
            assert events == []

            ok = await _rollback(http, pid, entry, expected_version=entry["current_version"])
            assert ok.status_code == 200, ok.text
            assert ok.json()["restored_formula"] == OLD
            assert events and events[0]["source"] == "history_rollback"

            db.expire_all()
            row = (await project_rows(db, pid))["BS-001"]
            assert (row.formula, row.formula_version) == (OLD, version + 1), "回滚写回条目的变更前定义（本项目新版本）"
            [after] = [i for i in await history(http, pid, 2025) if i["operation"] == "rollback"]
            assert after["current_version"] == version + 1
            # 回滚后原条目的版本号已过期：再用它回滚得 409
            again = await _rollback(http, pid, entry, expected_version=version)
            assert again.status_code == 409, again.text


async def test_entry_without_local_adaptation_rolls_back_with_version_zero(events):
    """同步全局写入的条目在本项目没有适配 ⇒ 当前版本 0；带 0 回滚 ⇒ 新建本项目适配（版本 1）= 变更前定义。"""
    async with make_db() as factory, factory() as db:
        admin = await add_user(db, "fhic_rollback_admin", "admin")
        await add_global_row(db, "BS-001", OLD)
        pid = await add_project(db, "回滚跟随全局")
        await db.commit()
        await publish_global(db, domain="report", scope=STD, user_id=None,
                             changes=[{"slot_key": SLOT, "definition": {"formula": NEW}, "expected_version": 1}])
        await db.commit()
        assert await project_rows(db, pid) == {}
        async with http_client(db, admin) as http:
            [entry] = [i for i in await history(http, pid, 2025) if i["operation"] == "sync_global"]
            assert (entry["rollbackable"], entry["current_version"]) == (True, 0)
            ok = await _rollback(http, pid, entry, expected_version=entry["current_version"])
            assert ok.status_code == 200, ok.text
            db.expire_all()
            row = (await project_rows(db, pid))["BS-001"]
            assert (row.formula, row.formula_version) == (OLD, 1)


async def test_unlocatable_legacy_entry_is_not_rollbackable_and_has_no_version(events):
    """旧格式条目（只有行次、无公式位）且行次在本项目定位不到：列表判不可回滚并给原因、不给版本号
    （界面据此不显示回滚按钮）；强行回滚 404，不改任何定义。"""
    from app.services.audit_log_helper import append_audit_log

    async with make_db() as factory, factory() as db:
        admin, pid, _ = await _seed_adapted(db)
        await append_audit_log(db, {
            "user_id": admin.id, "project_id": pid, "action": "formula.changed", "resource_type": "report_config",
            "resource_id": "BS-404", "details": {
                "event_type": "formula_changed", "module": "report", "row_code": "BS-404", "action": "update",
                "old_formula": OLD, "new_formula": "1", "result_value": "", "year": "2025"}})
        await db.commit()
        async with http_client(db, admin) as http:
            [entry] = [i for i in await history(http, pid, 2025) if i["row_code"] == "BS-404"]
            assert entry["rollbackable"] is False and entry["current_version"] is None, entry
            assert "无法定位" in (entry["rollback_blocked_reason"] or ""), entry
            forced = await _rollback(http, pid, entry, expected_version=0)
            assert forced.status_code == 404, forced.text
            assert events == []
