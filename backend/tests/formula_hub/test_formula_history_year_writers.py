"""公式历史按年度可查：生产写入方都给 ``formula.changed`` 载荷带上年度（第 2 轮 D-1，需求 11.1）。

阶段 D 浏览器实测：历史页对公式设置类变更恒空 —— ``audit_project`` 的 8 处生产调用都不传 ``year``，
而 ``GET /api/formula-audit-log/{pid}/{year}`` 只返回 ``payload->>'year' = :yr`` 的条目。
``test_formula_audit_log_year.py`` 直接给 ``audit_project`` 传 ``year``，看不到调用方漏传。

本文件走生产调用方本身（SQLite 真 ORM，项目审计年度 2025），再经 HTTP（按生产注册挂 router，鉴权链真实运行，
只替换 ``get_current_user`` / ``get_db``）按年度查历史：2025 查得到该操作、载荷 ``year == "2025"``，2024 查不到。
另有 AST 守卫：``backend/app`` 里 ``audit_project(`` 的调用点集合 == 本文件逐个覆盖的 8 处（新增调用点必须补用例）。
同类写入方（不经 ``audit_project``，同样写 ``formula.changed``）各一例：⑨ 底稿公式 CRUD、⑩ 报表试算批量、
⑪ 合并报表生成、⑫ 底稿用户公式保存 / 恢复预设。
"""
from __future__ import annotations

import ast
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.models.workpaper_models import WorkingPaper, WpFormula, WpSourceType
from app.services.formula_settings import apply_ops, project_ops
from app.services.formula_settings import template_service as tsvc
from app.services.formula_settings import template_sync as tsync
from app.services.formula_settings.engine import Decisions
from app.services.formula_settings.publish import publish_global
from app.services.formula_settings.template_access import Viewer
from app.services.report_config_service import ReportConfigService
from tests.formula_hub._history_http import history, http_client, payload_of
from tests.formula_settings._env import (
    STD,
    add_global_row,
    add_project,
    add_project_row,
    add_user,
    make_db,
    pending_items,
)

OLD, MINE, NEW = "TB('1001','期末余额')", "ROW('BS-009')", "TB('1001','期末余额')*2"
SLOT = "balance_sheet:BS-001"
APP_ROOT = Path(__file__).resolve().parents[2] / "app"


async def _base(db) -> None:
    await add_global_row(db, "BS-001", OLD)
    await add_global_row(db, "BS-002", "TB('1002','期末余额')", row_number=2)


async def _publish_new(db) -> None:
    await publish_global(db, domain="report", scope=STD, user_id=None,
                         changes=[{"slot_key": SLOT, "definition": {"formula": NEW}, "expected_version": 1}])
    await db.commit()


async def _adapt(db, pid) -> None:
    await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None,
                                     items=[{"slot_key": SLOT, "definition": {"formula": MINE}}])
    await db.commit()


# ─── 8 处 audit_project 生产调用（计划 §1 表 D-1 的 1~8） ────────────────────


async def _s_publish(db, _admin):
    await _base(db)
    pid = await add_project(db, "跟随全局")
    await db.commit()
    await _publish_new(db)
    return pid


async def _s_adapt(db, _admin):
    await _base(db)
    pid = await add_project(db, "本项目适配")
    await db.commit()
    await _adapt(db, pid)
    return pid


async def _s_restore(db, _admin):
    pid = await _s_adapt(db, _admin)
    await project_ops.restore_global(db, domain="report", project_id=pid, slot_keys=[SLOT], user_id=None)
    await db.commit()
    return pid


async def _s_resolve(db, _admin):
    await _base(db)
    pid = await add_project(db, "处理待确认")
    await add_project_row(db, pid, "BS-001", MINE, base_formula=OLD)
    await db.commit()
    await _publish_new(db)
    [item] = await pending_items(db, pid)
    await project_ops.resolve_items(db, project_id=pid, user_id=None, resolutions=[
        {"item_id": str(item.id), "choice": "adopt", "revision": item.revision}])
    await db.commit()
    return pid


async def _s_push(db, _admin):
    await _base(db)
    src, target = await add_project(db, "推送来源"), await add_project(db, "推送目标")
    await add_project_row(db, src, "BS-001", MINE, base_formula=OLD)
    await db.commit()
    await apply_ops.apply_to_projects(db, domain="report", project_id=src, slot_keys=[SLOT], target_ids=[target],
                                      decisions=Decisions(), user_id=None)
    await db.commit()
    return target


async def _template(db, admin):
    await _base(db)
    src, follower = await add_project(db, "模板来源"), await add_project(db, "模板订阅方")
    await add_project_row(db, src, "BS-001", MINE, base_formula=OLD)
    await db.commit()
    viewer = await Viewer.load(db, admin)
    tpl = await tsvc.create_template(db, viewer=viewer, name="集团报表口径", description=None, share_scope="personal",
                                     owner_project_id=None, applicable_scope="", source="project", domains=["report"],
                                     source_project_id=src)
    await tsync.subscribe(db, project_id=follower, tpl=tpl, domain="report", decisions=None, user_id=admin.id)
    await db.commit()
    return follower


async def _s_unsubscribe_keep(db, admin):
    follower = await _template(db, admin)
    # keep 模式不经 _apply：只有 unsubscribe 自己的 audit_project（模板定义与全局不同 ⇒ 记 template_keep）
    await tsync.unsubscribe(db, project_id=follower, domain="report", mode="keep", decisions=None, user_id=admin.id)
    await db.commit()
    return follower


async def _s_materialize(db, _admin):
    await _base(db)
    pid = await add_project(db, "物化预设")
    await add_project_row(db, pid, "BS-001", MINE, base_formula=OLD)
    await db.commit()
    out = await ReportConfigService(db).materialize_project_presets(pid, applicable_standard=STD, overwrite=True)
    await db.commit()
    assert out["updated"] == 1, out
    return pid


@dataclass(frozen=True)
class Writer:
    key: str
    site: tuple[str, str]  # （相对 backend/app 的文件, 调 audit_project 的函数）
    run: Callable[..., Awaitable]
    operation: str
    source: str


WRITERS: tuple[Writer, ...] = (
    Writer("publish_global", ("services/formula_settings/publish.py", "publish_global"), _s_publish,
           "sync_global", "global_edit"),
    Writer("save_overrides", ("services/formula_settings/project_ops.py", "save_overrides"), _s_adapt,
           "adapt", "project_edit"),
    Writer("restore_global", ("services/formula_settings/project_ops.py", "restore_global"), _s_restore,
           "restore", "project_restore"),
    Writer("resolve_items", ("services/formula_settings/project_ops.py", "resolve_items"), _s_resolve,
           "resolve_pending", "project_resolve"),
    Writer("apply_to_projects", ("services/formula_settings/apply_ops.py", "apply_to_projects"), _s_push,
           "push", "apply_to_projects"),
    Writer("template_apply", ("services/formula_settings/template_sync.py", "_apply"), _template,
           "template_subscribe", "template_subscribe"),
    Writer("template_unsubscribe", ("services/formula_settings/template_sync.py", "unsubscribe"),
           _s_unsubscribe_keep, "template_unsubscribe", "template_unsubscribe"),
    Writer("materialize_presets", ("services/report_config_service.py", "materialize_project_presets"),
           _s_materialize, "adapt", "materialize_overwrite"),
)


@pytest.mark.parametrize("writer", WRITERS, ids=[w.key for w in WRITERS])
async def test_production_writer_entry_is_found_by_project_year(writer: Writer):
    async with make_db() as factory, factory() as db:
        admin = await add_user(db, "fhic_history_admin", "admin")
        pid = await writer.run(db, admin)
        async with http_client(db, admin) as http:
            items = await history(http, pid, 2025)
            hits = [i for i in items if (i["operation"], i["source"]) == (writer.operation, writer.source)]
            assert hits, (writer.key, "按项目审计年度 2025 查不到该操作",
                          [(i["operation"], i["source"]) for i in items])
            for hit in hits:
                assert (await payload_of(db, hit["id"]))["year"] == "2025", writer.key
            assert await history(http, pid, 2024) == [], writer.key


def _calls_in(path: Path, name: str) -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    sites: set[tuple[str, str]] = set()

    def visit(node: ast.AST, func: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            current = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
            if isinstance(child, ast.Call):
                callee = child.func
                called = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
                if called == name and func is not None:
                    sites.add((path.relative_to(APP_ROOT).as_posix(), func))
            visit(child, current)

    visit(tree, None)
    return sites


def test_audit_project_call_sites_equal_covered_writers():
    """``audit_project`` 的生产调用点集合 == 上面逐个覆盖的 8 处（新增调用点不补用例即红）。"""
    sites: set[tuple[str, str]] = set()
    for path in APP_ROOT.rglob("*.py"):
        if path.name == "audit.py" and path.parent.name == "formula_settings":
            continue  # 定义所在模块
        if "audit_project" in path.read_text(encoding="utf-8"):
            sites |= _calls_in(path, "audit_project")
    assert sites == {w.site for w in WRITERS}, sorted(sites ^ {w.site for w in WRITERS})


# ─── 同类写入方（不经 audit_project，计划 §1 的 ⑨~⑫） ───────────────────────


async def _entries(db, admin, pid, year, *, module: str, action: str) -> list[dict]:
    async with http_client(db, admin) as http:
        return [i for i in await history(http, pid, year) if (i["module"], i["action"]) == (module, action)]


async def test_wp_formula_crud_audit_fills_project_year():
    """⑨ ``write_wp_formula_audit``：``wp_formula.py`` 三处 CRUD 调用都不传 year ⇒ 按项目审计年度补齐。"""
    from app.routers.wp_formula_audit import write_wp_formula_audit

    async with make_db() as factory, factory() as db:
        admin = await add_user(db, "fhic_history_admin", "admin")
        pid = await add_project(db, "底稿公式")
        await db.commit()
        await write_wp_formula_audit(db, user=admin, project_id=pid, wp_code="E1-1", target_cell="审定表!B5",
                                     action="update", old_formula="", new_formula="=TB('1001','审定数')")
        await db.commit()
        [hit] = await _entries(db, admin, pid, 2025, module="workpaper", action="update")
        assert (await payload_of(db, hit["id"]))["year"] == "2025"
        assert await _entries(db, admin, pid, 2024, module="workpaper", action="update") == []


async def test_report_trial_run_batch_audit_records_request_year():
    """⑩ 报表试算批量（HTTP ``execute-formulas-batch``）：留痕记本次请求的年度（看上年数据时记上年，不按项目年度）。"""
    from app.routers import report_config

    async with make_db() as factory, factory() as db:
        admin = await add_user(db, "fhic_history_admin", "admin")
        pid = await add_project(db, "报表试算")
        await db.commit()
        async with http_client(db, admin, report_config.router) as http:
            resp = await http.post("/api/report-config/execute-formulas-batch", json={
                "project_id": str(pid), "year": 2024, "formulas": [{"row_code": "BS-001", "formula": "100"}]})
            assert resp.status_code == 200, resp.text
            assert resp.json()["results"][0]["value"] == 100, resp.text
        [hit] = await _entries(db, admin, pid, 2024, module="report", action="execute")
        assert hit["row_code"] == "BS-001"
        assert (await payload_of(db, hit["id"]))["year"] == "2024"
        assert await _entries(db, admin, pid, 2025, module="report", action="execute") == []


async def test_consol_report_formula_audit_records_generation_year():
    """⑪ 合并报表生成的公式留痕：调用方已带年度参数，载荷原先没写进去。"""
    from app.routers.consol_report import _write_consol_formula_audit

    async with make_db() as factory, factory() as db:
        admin = await add_user(db, "fhic_history_admin", "admin")
        pid = await add_project(db, "合并报表")
        await db.commit()
        await _write_consol_formula_audit(db, str(pid), 2025, {"balance_sheet": [
            {"row_code": "BS-001", "row_name": "货币资金", "formula_used": "ROW('BS-002')",
             "current_period_amount": 5}]}, user_id=admin.id)
        [hit] = await _entries(db, admin, pid, 2025, module="consol", action="execute")
        assert (await payload_of(db, hit["id"]))["year"] == "2025"
        assert await _entries(db, admin, pid, 2024, module="consol", action="execute") == []


async def _working_paper(db, pid, parsed_data: dict | None = None):
    import uuid

    wp_id = uuid.uuid4()
    db.add(WorkingPaper(id=wp_id, project_id=pid, wp_index_id=uuid.uuid4(), file_path="fhic.xlsx",
                        source_type=WpSourceType.template, parsed_data=parsed_data))
    await db.commit()
    return wp_id


async def test_wp_user_formula_save_and_restore_preset_record_project_year():
    """⑫ 底稿用户公式：保存（``update_user_formulas``）与恢复预设（``restore_preset_formula``）两处都按项目年度记。"""
    from app.routers.wp_user_formulas import BatchUserFormulasRequest, restore_preset_formula, update_user_formulas

    from app.models.audit_platform_models import TrialBalance

    cell = "审定表!B5"
    # trial_balance：保存时的取数校验要读（空表 ⇒ 校验按无数据处理）
    async with make_db(extra_models=(WorkingPaper, WpFormula, TrialBalance)) as factory, factory() as db:
        admin = await add_user(db, "fhic_history_admin", "admin")
        pid = await add_project(db, "底稿用户公式")
        wp_id = await _working_paper(db, pid)
        # 只关掉 ACNR 悬空引用校验（与本条年度断言正交，校验行为由 test_formula_save_validation.py 覆盖）
        with patch("app.services.wp_formula_service.validate_refs_via_acnr", new_callable=AsyncMock, return_value=[]):
            # 不引用试算表：保存前的取数校验（本年度试算表有无数据）与本条年度断言正交
            out = await update_user_formulas(wp_id, BatchUserFormulasRequest(formulas={cell: "=MAX(1,2)"}),
                                             db=db, user=admin)
        assert out["updated"] == 1, out
        restored = await restore_preset_formula(wp_id, cell, db=db, _user=admin)
        assert restored["status"] == "restored", restored
        saved = await _entries(db, admin, pid, 2025, module="workpaper", action="update")
        undone = await _entries(db, admin, pid, 2025, module="workpaper", action="restore_preset")
        assert len(saved) == 1 and len(undone) == 1, (saved, undone)
        for hit in saved + undone:
            assert (await payload_of(db, hit["id"]))["year"] == "2025"
        async with http_client(db, admin) as http:
            assert await history(http, pid, 2024) == []
