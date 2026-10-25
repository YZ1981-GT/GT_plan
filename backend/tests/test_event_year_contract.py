"""事件年度契约守卫（断点 3：year 缺失静默跳过 / 猜错年份）。

🔴 缺陷（2026-09-29 现扫）：
1. 数据链事件有 11 个发布点不传 ``year``（OnlyOffice 在线保存、底稿上传/导入、函证 ×3 的
   WORKPAPER_SAVED；科目表编辑的 ACCOUNT_MAPPING_CHANGED；报表公式、预填种子 …），而
   订阅者要么 ``if not year: return``（静默跳过：OnlyOffice 保存后 stale 传播、C/D/F 循环
   联动一律不跑），要么 ``payload.year or 2025``（2024 项目写到 2025 = 错年份）。
2. 委派保存复用 ``DATA_IMPORTED``（year=None）冒充数据导入，命中 7 个订阅者，其中 5 个
   不看 year 按项目全量执行（全项目底稿 prefill_stale、地址库/报表/程序表缓存全清）。
3. 报表公式编辑 / 预填种子把 ``current_user.id`` 当 project_id 发事件 ⇒ stale 标到一个用户 id 上。

修法：EventBus 唯一派发口 ``_dispatch`` 按项目审计年度补齐 year；订阅者缺 year 时显式可见降级
（stale-degraded），不猜年份。

本文件守三件事：
- 行为：缺 year 的事件派发给订阅者时已补齐为项目审计年度；查不到则保持 None 且不抛
- 覆盖面：「全仓读 year 的订阅者所属事件类型」⊆ ``YEAR_SCOPED_EVENT_TYPES``（现算，不写死）
- 防回归：不再存在 ``payload.year or 20xx`` 猜年份；委派不再发 DATA_IMPORTED；
  报表公式 / 预填种子不再把用户 id 当 project_id
"""
from __future__ import annotations

import ast
import re
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.event_bus import YEAR_SCOPED_EVENT_TYPES, EventBus

_APP = Path(__file__).resolve().parents[1] / "app"


# ─────────────────────────────────────────────────────────────────────────────
# 行为：派发口年度补齐
# ─────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def project_factory():
    """真 SQLite 库 + 真 Project 行，补齐走真实 SQL（PROJECT_AUDIT_YEAR_SQL）。"""
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
    from app.models.base import Base
    import app.models.core  # noqa: F401
    from app.models.core import Project, ProjectStatus, ProjectType

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _make(**fields) -> uuid.UUID:
        pid = uuid.uuid4()
        async with factory() as db:
            db.add(Project(
                id=pid, name=fields.pop("name", f"测试项目_{pid.hex[:6]}"),
                client_name="测试客户",
                project_type=ProjectType.annual, status=ProjectStatus.created,
                **fields,
            ))
            await db.commit()
        return pid

    with patch("app.core.database.async_session", factory):
        yield _make
    await engine.dispose()


async def _dispatch_and_capture(event_type: EventType, project_id: uuid.UUID, **kw) -> EventPayload:
    bus = EventBus(debounce_ms=0)
    seen: list[EventPayload] = []

    async def _h(p: EventPayload) -> None:
        seen.append(p)

    bus.subscribe(event_type, _h)
    await bus.publish_immediate(EventPayload(event_type=event_type, project_id=project_id, **kw))
    assert len(seen) == 1
    return seen[0]


@pytest.mark.asyncio
async def test_missing_year_backfilled_from_audit_year(project_factory):
    """发布方漏传 year → 订阅者拿到项目 audit_year（2024 项目不得被猜成 2025）。"""
    pid = await project_factory(audit_year=2024)
    got = await _dispatch_and_capture(EventType.WORKPAPER_SAVED, pid, extra={"wp_id": "x"})
    assert got.year == 2024


@pytest.mark.asyncio
async def test_backfill_falls_back_to_period_end(project_factory):
    """audit_year 为空时按 audit_period_end 年份（与 fetch_project_audit_year 同口径）。"""
    pid = await project_factory(audit_year=None, audit_period_end=date(2023, 12, 31))
    got = await _dispatch_and_capture(EventType.ACCOUNT_MAPPING_CHANGED, pid)
    assert got.year == 2023


@pytest.mark.asyncio
async def test_explicit_year_never_overridden(project_factory):
    """显式传的 year 优先（发布方比项目元数据更清楚本次操作的年度，如跨年导入）。"""
    pid = await project_factory(audit_year=2025)
    got = await _dispatch_and_capture(EventType.TRIAL_BALANCE_UPDATED, pid, year=2024)
    assert got.year == 2024


@pytest.mark.asyncio
async def test_unknown_project_keeps_none_and_does_not_raise(project_factory):
    """项目不存在 / 无年度 → year 保持 None（订阅者可见降级），派发本身不抛。"""
    got = await _dispatch_and_capture(EventType.WORKPAPER_SAVED, uuid.uuid4())
    assert got.year is None


@pytest.mark.asyncio
async def test_non_year_scoped_event_not_backfilled(project_factory):
    """不在 YEAR_SCOPED_EVENT_TYPES 的事件不补（其 project_id 可能只是占位，不能当项目查）。"""
    assert EventType.REPORT_CONFIG_MASTER_UPDATED not in YEAR_SCOPED_EVENT_TYPES
    pid = await project_factory(audit_year=2025)
    got = await _dispatch_and_capture(EventType.REPORT_CONFIG_MASTER_UPDATED, pid)
    assert got.year is None


# ─────────────────────────────────────────────────────────────────────────────
# 覆盖面：读 year 的订阅者 ⊆ YEAR_SCOPED_EVENT_TYPES（现算，不写死）
# ─────────────────────────────────────────────────────────────────────────────

_SUB_RE = re.compile(r"subscribe\(\s*EventType\.(\w+)\s*,\s*([\w\.]+)")
_READS_YEAR_RE = re.compile(
    r"payload\.year|event\.year|getattr\(\s*(?:payload|event)\s*,\s*['\"]year['\"]"
)
#: _make_handler/_make_tb_handler 包装的 service 方法：闭包本身读 payload.year
#: （after_commit 级联判断），且被包装的方法全部读 year —— 按包装器名整体认定。
_WRAPPER_PREFIXES = ("_make_tb_handler", "_make_handler")


def _function_sources() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in _APP.rglob("*.py"):
        src = p.read_bytes().decode("utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(node.name, ast.get_source_segment(src, node) or "")
    return out


def _event_types_with_year_readers() -> dict[str, set[str]]:
    funcs = _function_sources()
    readers: dict[str, set[str]] = {}
    for p in _APP.rglob("*.py"):
        src = p.read_bytes().decode("utf-8", errors="replace")
        for m in _SUB_RE.finditer(src):
            et, handler = m.group(1), m.group(2).split(".")[-1]
            body = funcs.get(handler, "")
            if handler.startswith(_WRAPPER_PREFIXES) or _READS_YEAR_RE.search(body):
                readers.setdefault(et, set()).add(handler)
    return readers


def test_every_year_reading_subscription_is_backfilled():
    """新增读 year 的订阅者而没登记进 YEAR_SCOPED_EVENT_TYPES → 打红（补齐覆盖面不得静默缩水）。"""
    readers = _event_types_with_year_readers()
    assert readers, "扫描器一个订阅都没抽到 —— 正则失效会让本守卫恒绿"
    scoped = {e.name for e in YEAR_SCOPED_EVENT_TYPES}
    uncovered = {et: sorted(hs) for et, hs in readers.items() if et not in scoped}
    assert not uncovered, (
        "以下事件类型有订阅者读 payload.year，但未登记进 event_bus.YEAR_SCOPED_EVENT_TYPES"
        f"（发布方漏传 year 时不会被补齐）：{uncovered}"
    )


def test_scanner_detects_known_year_readers():
    """反向断言：扫描器必须能抽到已知读 year 的订阅（证明守卫不是空转）。"""
    readers = _event_types_with_year_readers()
    assert "TrialBalanceService" not in str(readers)  # 包装器按名认定，不依赖类名
    assert "WORKPAPER_SAVED" in readers
    assert "LEDGER_DATASET_ACTIVATED" in readers
    assert "ADJUSTMENT_APPROVED" in readers


def test_adjustment_review_revoked_is_year_scoped():
    """撤回复核与审批一样读取年度，必须纳入年度补齐集合。"""
    assert EventType.ADJUSTMENT_REVIEW_REVOKED in YEAR_SCOPED_EVENT_TYPES


    """YEAR_SCOPED_EVENT_TYPES 里每一项都必须仍有读 year 的订阅者（清单不得虚高）。"""
    readers = _event_types_with_year_readers()
    stale = sorted(e.name for e in YEAR_SCOPED_EVENT_TYPES if e.name not in readers)
    assert not stale, f"以下事件类型已无读 year 的订阅者，应从 YEAR_SCOPED_EVENT_TYPES 移除：{stale}"


# ─────────────────────────────────────────────────────────────────────────────
# 防回归：猜年份 / 冒充事件 / 用户 id 当 project_id
# ─────────────────────────────────────────────────────────────────────────────


def _guessed_year_sites(src: str) -> list[int]:
    """AST 找 ``payload.year or <20xx 常量>`` / ``event.year or <20xx>``。

    用 AST 而不是文本匹配：docstring / 注释里描述这个反模式（本修复自己的说明文字就有）
    不产生 ``BoolOp`` 节点，天然排除；文本匹配会把说明误报成违规（首版即踩）。
    """
    lines = []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)):
            continue
        head, *rest = node.values
        if not (
            isinstance(head, ast.Attribute) and head.attr == "year"
            and isinstance(head.value, ast.Name) and head.value.id in {"payload", "event"}
        ):
            continue
        if any(isinstance(v, ast.Constant) and isinstance(v.value, int) and v.value >= 2000
               for v in rest):
            lines.append(node.lineno)
    return lines


def test_no_handler_guesses_year_with_hardcoded_default():
    """事件 handler 里不得 ``payload.year or 20xx`` —— 对非该年项目是错年份。"""
    hits = []
    for p in _APP.rglob("*.py"):
        src = p.read_bytes().decode("utf-8", errors="replace")
        try:
            sites = _guessed_year_sites(src)
        except SyntaxError:
            continue
        hits += [f"{p.relative_to(_APP.parent)}:{ln}" for ln in sites]
    assert not hits, "handler 猜年份（应依赖派发口补齐 + 缺失时可见降级）：\n" + "\n".join(hits)


def test_guessed_year_detector_is_not_blind():
    """反向断言：探测器对真实反模式必须命中，对 docstring/注释里的同名文字必须不命中。"""
    assert _guessed_year_sites("y = payload.year or 2025\n") == [1]
    assert _guessed_year_sites("def f(event):\n    return event.year or 2024\n") == [2]
    assert _guessed_year_sites('"""替代 ``payload.year or 2025`` 猜年份"""\n# payload.year or 2025\n') == []
    assert _guessed_year_sites("y = payload.year or fallback\n") == []


def _event_payload_calls(path: Path) -> list[tuple[str | None, dict[str, str]]]:
    tree = ast.parse(path.read_bytes().decode("utf-8"))
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
        if name != "EventPayload":
            continue
        kw = {k.arg: ast.unparse(k.value) for k in node.keywords if k.arg}
        et = kw.get("event_type", "")
        calls.append((et.split(".")[-1] if et else None, kw))
    return calls


def test_assignment_no_longer_masquerades_as_data_imported():
    """委派只改人员权限，不得发 DATA_IMPORTED（会全项目标底稿 stale + 清缓存）。"""
    calls = _event_payload_calls(_APP / "services" / "assignment_service.py")
    assert not [c for c in calls if c[0] == "DATA_IMPORTED"]


@pytest.mark.parametrize("rel", [
    "routers/report_config.py",
    "routers/template_library_mgmt.py",
])
def test_no_user_id_as_project_id(rel):
    """不得把 current_user.id 当 project_id 发数据链事件（stale 会标到一个用户 id 上）。"""
    bad = [
        (et, kw["project_id"]) for et, kw in _event_payload_calls(_APP / rel)
        if "current_user" in kw.get("project_id", "")
    ]
    assert not bad, f"{rel} 把用户 id 当 project_id: {bad}"
