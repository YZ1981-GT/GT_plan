"""映射表读取方：按科目找底稿、调整到达通知、底稿一键刷新取数科目。

两个读取方原先自己读 json 且都静默失效（异常被吞，界面上看不出来）：
- 调整到达通知 ``adjustments._notify_affected_wp_assignees``：拼的两个路径落在 ``app/data/`` 下（文件在 ``backend/data/``），
  且把 ``{"mappings": [...]}`` 按列表取 ⇒ 映射恒空，从未通知过任何人；
- 底稿一键刷新 ``audit-sheet-refresh``：把 ``{"mappings": [...]}`` 当列表遍历（遍历到的是键名字符串）⇒ 恒「未找到科目映射」，
  只有写死的 D1 → 1121 能用。
现在两者都经 ``wp_mapping_service``（与其余读取方同一份缓存）。期望值为字面量，来自修正后的映射表与单一来源。

spec: .kiro/specs/formula-fetch-followup-defect-closure/ R1.6
"""
from __future__ import annotations

import ast
import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.base import Base
from app.models.core import Notification, Project, User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.routers.adjustments import _notify_affected_wp_assignees
from app.routers.wp_render_config import audit_sheet_account_codes
from app.services.wp_mapping_service import workpapers_for_account_codes

_BACKEND = Path(__file__).resolve().parents[1]


# ─── 按科目找底稿 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("codes", "include_parent", "expected"),
    [
        (["1506"], False, ["G6", "G6-1", "G6-2", "G6-3", "G6-4", "G6-5", "G6-6"]),
        (["1507"], False, ["G8", "G8-1", "G8-2", "G8-3", "G8-4", "G8-5", "G8-6"]),
        (["1503"], False, []),  # 旧准则可供出售金融资产：不再归入 G6 / G8
        (["1901"], False, ["K2", "K2-1", "K2-2", "K2-3", "K2-4"]),
        (["2201"], False, ["E0-5", "F3", "F3-1", "F3-2", "F3-3", "F3-4", "F3-5", "F3-6", "F3-7"]),
        (["1122.01"], False, []),
        (["1122.01"], True, ["D0", "D0-1", "D0-2", "D0-3", "D0-4", "D0-5", "D2", "D2-1", "D2-2", "D2-3", "D2-4", "D2-5", "D2-6"]),
        (["", "  "], True, []),
    ],
)
def test_workpapers_for_account_codes(codes, include_parent, expected):
    assert workpapers_for_account_codes(codes, include_parent=include_parent) == expected


# ─── 一键刷新取数科目 ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("wp_code", "expected"),
    [
        ("D1", ["1121"]),
        ("D2-1", ["1122"]),
        ("E1", ["1001", "1002", "1012"]),
        ("F2-4", ["1403"]),  # 原材料明细（原先写的 1401 是材料采购）
        ("F2-5", []),  # 在产品没有存货类独立科目
        ("G8", ["1507"]),
        ("M5", ["4101"]),
        ("ZZ", []),
    ],
)
def test_audit_sheet_account_codes(wp_code, expected):
    assert audit_sheet_account_codes(wp_code) == expected


def test_audit_sheet_refresh_does_not_read_the_json_itself():
    """端点取科目只经 audit_sheet_account_codes；函数体里不得再出现映射文件名或写死的科目码兜底。"""
    src = (_BACKEND / "app" / "routers" / "wp_render_config.py").read_text(encoding="utf-8")
    fn = next(
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "refresh_audit_sheet_from_ledger"
    )
    called = {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    consts = [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "audit_sheet_account_codes" in called
    assert not [c for c in consts if "wp_account_mapping" in c or c == "1121"], consts


# ─── 调整到达通知（真 SQLite + 真 ORM） ───────────────────────────────

_TABLES = [User.__table__, Project.__table__, WpIndex.__table__, WorkingPaper.__table__, Notification.__table__]


def _run(scenario):
    async def _main():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                return await scenario(session)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


async def _seed(s: AsyncSession, assignees: dict[str, uuid.UUID]) -> uuid.UUID:
    pid = uuid.uuid4()
    for wp_code, user_id in assignees.items():
        idx = WpIndex(project_id=pid, wp_code=wp_code, wp_name=wp_code, assigned_to=user_id)
        s.add(idx)
        await s.flush()
        source_type = WorkingPaper.__table__.c["source_type"].type.enum_class("template")
        s.add(WorkingPaper(project_id=pid, wp_index_id=idx.id, file_path=f"{wp_code}.xlsx",
                           source_type=source_type, assigned_to=user_id))
    await s.flush()
    return pid


async def _notified(s: AsyncSession) -> dict[uuid.UUID, list[str]]:
    rows = (await s.execute(sa.select(Notification))).scalars().all()
    return {n.recipient_id: sorted((n.notification_metadata or {}).get("affected_wp_codes") or []) for n in rows}


def _request(source: str, *codes: str):
    return SimpleNamespace(source_wp_code=source, line_items=[SimpleNamespace(standard_account_code=c) for c in codes])


def test_adjustment_arrival_notifies_assignee_of_the_mapped_workpaper():
    g6_owner, k9_owner, sender = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async def _s(s):
        pid = await _seed(s, {"G6": g6_owner, "K9": k9_owner})
        # K9 同步一笔分录：管理费用 6602（K9 自己那一族，不通知）+ 其他债权投资 1506（G6）
        await _notify_affected_wp_assignees(s, pid, _request("K9", "6602", "1506"), "AJE-001", sender)
        return await _notified(s)

    assert _run(_s) == {g6_owner: ["G6"]}


def test_old_code_and_own_family_notify_nobody():
    g8_owner, sender = uuid.uuid4(), uuid.uuid4()

    async def _s(s):
        pid = await _seed(s, {"G8": g8_owner})
        await _notify_affected_wp_assignees(s, pid, _request("G8", "1507"), "AJE-002", sender)  # 自己那一族
        await _notify_affected_wp_assignees(s, pid, _request("K9", "1503"), "AJE-003", sender)  # 旧准则码不归任何底稿
        return await _notified(s)

    assert _run(_s) == {}


def test_sub_account_code_falls_back_to_parent():
    d2_owner, sender = uuid.uuid4(), uuid.uuid4()

    async def _s(s):
        pid = await _seed(s, {"D2": d2_owner})
        await _notify_affected_wp_assignees(s, pid, _request("K9", "1122.01"), "AJE-004", sender)
        return await _notified(s)

    assert _run(_s) == {d2_owner: ["D2"]}


# ─── 真库只读：一键刷新端点按映射取到科目（连库才跑） ───────────────────

#: 重药控股安徽有限公司_2025 的 E1 底稿（试算表有 1001 / 1002 / 1012）
_ANHUI_E1_WP = uuid.UUID("2a482c69-f468-47d6-ac6d-6e634cc8abaa")


def _pg_available() -> bool:
    try:
        import psycopg2

        psycopg2.connect(dbname="audit_platform", user="postgres", password="postgres",
                         host="localhost", port=5432, connect_timeout=3).close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _pg_available(), reason="本地 PostgreSQL 不可用")
def test_audit_sheet_refresh_reads_mapped_accounts_on_real_db():
    from app.core.database import async_session
    from app.routers.wp_render_config import refresh_audit_sheet_from_ledger
    from tests._pg_shared_engine import run_and_dispose

    async def _main():
        async with async_session() as db:
            exists = (await db.execute(sa.text("SELECT 1 FROM working_paper WHERE id = :i AND is_deleted = false"),
                                       {"i": str(_ANHUI_E1_WP)})).first()
            if not exists:
                return None
            try:
                return await refresh_audit_sheet_from_ledger(wp_id=_ANHUI_E1_WP, db=db, _user=None)
            finally:
                await db.rollback()

    result = asyncio.run(run_and_dispose(_main()))
    if result is None:
        pytest.skip("安徽 E1 底稿已不在真库")
    assert "科目映射" not in result["message"], result["message"]
    assert result["rows"], result
