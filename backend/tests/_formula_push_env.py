"""公式推送测试共享环境（引擎 / 端点测试共用；非测试模块）。

SQLite 真 ORM（projects / disclosure_notes / 推送状态）+ 裸 SQL 表（wp_index / working_paper /
checklist_responses，与生产写入适配器同一 uuid 传参口径）。取数层 ``E1Binding.load_sources`` 换成固定源。
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models.core  # noqa: E402, F401
import app.models.formula_push_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
from app.models.base import Base  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType  # noqa: E402
from app.models.formula_push_models import FormulaPushRun, FormulaPushState  # noqa: E402
from app.models.report_models import ContentType, DisclosureNote, NoteStatus  # noqa: E402
from app.services.formula_push import engine as push  # noqa: E402
from app.services.formula_push.bindings import e1_calc  # noqa: E402
from app.services.formula_push.bindings.e1 import E1Binding, E1Sources  # noqa: E402
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot  # noqa: E402

YEAR = 2025
CHECKLIST_DDL = """
CREATE TABLE checklist_responses (
    id TEXT PRIMARY KEY NOT NULL,
    project_id TEXT NOT NULL,
    wp_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    conclusion TEXT, remark TEXT, wp_ref TEXT, updated_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (wp_id, item_id)
)
"""


def cash_rows(opening=200, increase=90, decrease=0, note="四表取数 1001.01") -> str:
    return json.dumps([
        {"id": "fixed-rmb", "currency": "人民币", "opening": opening, "increase": increase,
         "decrease": decrease, "fxRate": 1, "adjustment": 0, "note": note},
        {"id": "cash-u1", "currency": "欧元", "opening": 3, "increase": 0, "decrease": 0, "fxRate": 0},
    ], ensure_ascii=False, separators=(",", ":"))


def bank_rows(opening=100, increase=50, decrease=30) -> str:
    return json.dumps([{
        "id": "bank-principal-institution-ft-1002.01", "section": "principal", "group": "institution",
        "opening": opening, "increase": increase, "decrease": decrease, "fxCurrency": "人民币", "fxRate": 1,
    }], ensure_ascii=False, separators=(",", ":"))


def base_entries() -> dict[str, str]:
    """已保存的 E1 条目：两张明细 + 已落库（但陈旧）的现金未审合计。"""
    return {
        e1_calc.CASH_ROWS_KEY: cash_rows(),
        e1_calc.BANK_VARIANT_KEY: "rmb",
        e1_calc.BANK_ROWS_KEY: bank_rows(),
        "E1-cash-detail-total-unaudited": "290",
    }


def make_sources(*, cash_opening=286.73, tb_available=True, hall_1001="100", template_type="listed") -> E1Sources:
    """四表：现金叶子 1001.01（期初 cash_opening、增 90）、银行叶子 1002.01（100 / 增 60 / 减 30）。"""
    prefill = {
        "cash": [{"code": "1001.01", "currency": "CNY", "opening": cash_opening, "increase": 90, "decrease": 0,
                  "ending": cash_opening + 90}],
        "bank": [{"code": "1002.01", "currency": "", "opening": 100, "increase": 60, "decrease": 30, "ending": 130}],
        "other": [], "finance_co": [], "digital": [],
    }
    tb = TbAuditedSnapshot(
        tb_data={"1001": {"期末余额": Decimal("476.73"), "年初余额": Decimal("286.73")},
                 "1002": {"期末余额": Decimal("130"), "年初余额": Decimal("100")},
                 "1012": {"期末余额": Decimal("0"), "年初余额": Decimal("0")}},
        available=tb_available, company_codes=("001",),
    )
    zero = {"aje_net": Decimal("0"), "rje_net": Decimal("0")}
    hall = {"1001": {"aje_net": Decimal(hall_1001), "rje_net": Decimal("0")}, "1002": dict(zero), "1012": dict(zero)}
    return E1Sources(
        four_table_prefill=prefill,
        account_prefill={"accounts": {"bank": [], "other": [], "finance_co": [], "unassigned": []}},
        formula=FormulaSources(tb=tb, hall_adj=hall),
        template_type=template_type,
    )


class Env:
    def __init__(self, factory, pid: uuid.UUID, wp_id: uuid.UUID):
        self.factory, self.pid, self.wp_id = factory, pid, wp_id
        self.sources = make_sources()

    async def seed_entries(self, entries: dict[str, str]) -> None:
        async with self.factory() as db:
            for item, remark in entries.items():
                await db.execute(sa.text(
                    "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at) "
                    "VALUES (:id, :p, :w, :i, :r, :t)"
                ), {"id": str(uuid.uuid4()), "p": str(self.pid), "w": str(self.wp_id), "i": item,
                    "r": remark, "t": "2026-09-01 08:00:00.000000+00:00"})
            await db.commit()

    async def entries(self) -> dict[str, str]:
        async with self.factory() as db:
            rows = (await db.execute(sa.text(
                "SELECT item_id, remark FROM checklist_responses WHERE wp_id = :w"
            ), {"w": str(self.wp_id)})).all()
        return {r[0]: r[1] for r in rows}

    async def set_wp_status(self, status: str) -> None:
        async with self.factory() as db:
            await db.execute(sa.text("UPDATE working_paper SET status = :s WHERE id = :w"),
                             {"s": status, "w": str(self.wp_id)})
            await db.commit()

    async def add_note(self, section: str, table_data: dict | None, *, title="货币资金",
                       status=NoteStatus.draft) -> None:
        async with self.factory() as db:
            db.add(DisclosureNote(project_id=self.pid, year=YEAR, note_section=section, section_title=title,
                                  content_type=ContentType.table, table_data=table_data, status=status))
            await db.commit()

    async def note(self, section: str) -> DisclosureNote:
        async with self.factory() as db:
            return (await db.execute(sa.select(DisclosureNote).where(
                DisclosureNote.project_id == self.pid, DisclosureNote.note_section == section,
            ))).scalar_one()

    async def states(self) -> dict[str, FormulaPushState]:
        async with self.factory() as db:
            rows = (await db.execute(sa.select(FormulaPushState))).scalars().all()
        return {r.addr_id: r for r in rows}

    async def runs(self) -> list[FormulaPushRun]:
        async with self.factory() as db:
            return list((await db.execute(sa.select(FormulaPushRun).order_by(FormulaPushRun.started_at))).scalars())

    async def push(self, trigger: str = "manual", **kw) -> push.RunResult:
        async with self.factory() as db:
            return await push.run_and_commit(db, project_id=self.pid, year=YEAR, trigger=trigger, **kw)


@asynccontextmanager
async def make_env(monkeypatch, extra_tables=()):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    tables = [Project.__table__, DisclosureNote.__table__, FormulaPushRun.__table__, FormulaPushState.__table__,
              *extra_tables]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.execute(sa.text(
            "CREATE TABLE wp_index (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, wp_code TEXT NOT NULL, "
            "is_deleted BOOLEAN NOT NULL DEFAULT 0)"
        ))
        await conn.execute(sa.text(
            "CREATE TABLE working_paper (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, wp_index_id TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'draft', is_deleted BOOLEAN NOT NULL DEFAULT 0)"
        ))
        await conn.execute(sa.text(CHECKLIST_DDL))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    pid, wp_id, idx = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with factory() as db:
        db.add(Project(id=pid, name=f"推送项目_{YEAR}", client_name="测试客户", project_type=ProjectType.annual,
                       status=ProjectStatus.created, audit_year=YEAR, template_type="listed"))
        await db.flush()
        await db.execute(sa.text("INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'E1')"),
                         {"i": str(idx), "p": str(pid)})
        await db.execute(sa.text("INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"),
                         {"w": str(wp_id), "p": str(pid), "i": str(idx)})
        await db.commit()
    e = Env(factory, pid, wp_id)

    async def fake_load(db, project_id, year, wp):
        assert (project_id, year, wp) == (pid, YEAR, wp_id), "取数上下文必须是本项目本年度本底稿"
        return e.sources

    monkeypatch.setattr(E1Binding, "load_sources", staticmethod(fake_load))
    broadcasts: list[tuple[str, dict]] = []
    from app.services.event_bus import event_bus

    monkeypatch.setattr(event_bus, "broadcast_raw", lambda t, extra=None: broadcasts.append((t, extra)))
    e.broadcasts = broadcasts
    yield e
    await engine.dispose()


def by_addr(result: push.RunResult) -> dict[str, push.PushItem]:
    return {i.addr_id: i for i in result.items if i.addr_id}


CASH_OPENING = "E1/E1-2/E1-cash-detail-rows[fixed-rmb].opening"
CASH_TOTAL = "E1/E1-2/E1-cash-detail-total-unaudited"
TB_ENDING = "E1/E1-1/E1-adj-tb-amount-ending"
HALL_CASH = "E1/E1-1/E1-hall-adj-cash-ending"
ADJ_1001 = "E1/E1-1/E1-adj-total-1001"
