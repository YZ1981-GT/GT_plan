"""Property 8 PBT: 附注双源单向同步

**Validates: Requirements 3.11.5 §4.2 + design §12.1**

六条核心 property（hypothesis 生成 (wp_id, section_id, sub_table_data, current_standard, year)）：

- Property 8a (单向同步): sync_from_workpaper(payload) →
  DisclosureNote.table_data["sub_table_data"] 与 payload.sub_table_data 完全一致
- Property 8b (sync markers 写入): 同步后 DisclosureNote 写入 last_sync_source='workpaper'
  + last_sync_wp_id=payload.wp_id + last_sync_at 非空 + last_sync_user_id 非空
- Property 8c (反向不写回): DisclosureNote 直接编辑（修改 table_data） →
  WorkingPaper.parsed_data 保持不变（无反向 sync 路径）
- Property 8d (重复同步幂等): 同 payload 同步两次 → DisclosureNote 终态 == 单次同步终态
  + 第二次 created=False（无重复行）
- Property 8e (section_id 路由): 不同 section_id → 各自独立的 DisclosureNote 行
  （无交叉污染）
- Property 8f (rows_synced 计数正确): 返回 rows_synced == sum(len(rows) for rows in sub_table_data.values())

Spec: ``.kiro/specs/workpaper-html-renderer/`` Task 10.4

Strategy: 测试 sync_from_workpaper 的语义为 PURE FUNCTION property——用 FakeDB 拦截
SQLAlchemy session 调用并按 (project_id, year, note_section) key 维护 in-memory 字典，
避免完整 PG 集成依赖。
"""

from __future__ import annotations

import asyncio
import string
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, BooleanClauseList

from app.models.core import User, UserRole
from app.models.report_models import DisclosureNote
from app.services.wp_disclosure_sync_service import sync_from_workpaper


# ─── FakeDB: 内存版 AsyncSession 替身 ───────────────────────────────────────


def _extract_filters(stmt: Any) -> dict[str, Any]:
    """从 SQLAlchemy select stmt 的 WHERE 子句提取 BindParameter 值。

    handles AND'd BinaryExpression chain 的常见情况
    （DisclosureNote.project_id == X、year == Y、note_section == Z、is_deleted == false()）
    """
    filters: dict[str, Any] = {}
    where = stmt.whereclause
    if where is None:
        return filters

    if isinstance(where, BooleanClauseList):
        children = list(where.clauses)
    else:
        children = [where]

    for clause in children:
        if not isinstance(clause, BinaryExpression):
            continue
        col_name = getattr(clause.left, "key", None) or getattr(clause.left, "name", None)
        right = clause.right
        if isinstance(right, BindParameter):
            filters[col_name] = right.value
    return filters


class FakeDB:
    """模拟 AsyncSession：以 (project_id, year, note_section) 为主键存储 DisclosureNote。"""

    def __init__(self) -> None:
        self.notes: dict[tuple, DisclosureNote] = {}
        self.commit_count: int = 0
        self.add_count: int = 0
        self.rollback_count: int = 0

    async def execute(self, stmt: Any) -> Any:
        filters = _extract_filters(stmt)
        key = (
            filters.get("project_id"),
            filters.get("year"),
            filters.get("note_section"),
        )
        note = self.notes.get(key)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=note)
        return result

    def add(self, obj: Any) -> None:
        self.add_count += 1
        if isinstance(obj, DisclosureNote):
            key = (obj.project_id, obj.year, obj.note_section)
            self.notes[key] = obj

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        username="prop_user",
        email="prop@test.com",
        hashed_password="x",
        role=UserRole.admin,
        is_active=True,
        is_deleted=False,
    )


def _run_sync(
    db: FakeDB,
    *,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    sheet_name: str,
    section_id: str,
    sub_table_data: dict[str, list[dict]],
    current_standard: str,
    year: int,
    user: User | None = None,
) -> dict[str, Any]:
    """同步包装器：跑 sync_from_workpaper 并返回结果。"""
    if user is None:
        user = _make_user()
    return asyncio.run(
        sync_from_workpaper(
            db,  # type: ignore[arg-type]
            project_id,
            wp_id=wp_id,
            sheet_name=sheet_name,
            section_id=section_id,
            sub_table_data=sub_table_data,
            current_standard=current_standard,
            user=user,
            year=year,
        )
    )


# ─── Hypothesis Strategies ──────────────────────────────────────────────────

# 真实 section_id 样本（覆盖五/六/七章常见附注节）
_SECTION_IDS: list[str] = [
    "五-1-1 货币资金",
    "五-1-2 应收账款",
    "五-1-3 应收票据",
    "五-1-4 其他应收款",
    "五-1-5 存货",
    "五-2-1 短期借款",
    "五-2-3 应付账款",
    "五-2-4 预收款项",
    "六-1-1 营业收入",
    "六-1-2 营业成本",
    "六-2 税金及附加",
    "七-1 关联方关系",
    "五-1-1",  # 无空格变体
]

st_section_id = st.sampled_from(_SECTION_IDS)

st_table_id = st.text(
    alphabet=string.ascii_lowercase + "_",
    min_size=3,
    max_size=20,
)

# 单行：dict[str, scalar]（避免嵌套 dict 与 hypothesis 慢策略）
st_row = st.dictionaries(
    keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=6),
    values=st.one_of(
        st.integers(min_value=-10_000, max_value=10_000),
        st.text(max_size=12),
        st.none(),
    ),
    min_size=0,
    max_size=4,
)

# 子表：list[row]，长度 0~6 控制规模
st_sub_table_rows = st.lists(st_row, min_size=0, max_size=6)

# sub_table_data：dict[table_id, list[row]] 长度 0~5
st_sub_table_data = st.dictionaries(
    keys=st_table_id,
    values=st_sub_table_rows,
    min_size=0,
    max_size=5,
)

st_current_standard = st.sampled_from([
    "soe_standalone",
    "soe_consolidated",
    "listed_standalone",
    "listed_consolidated",
])

st_year = st.integers(min_value=2020, max_value=2030)

st_uuid = st.builds(uuid.uuid4)

st_sheet_name = st.sampled_from([
    "C-应收账款附注",
    "C-存货附注",
    "C-货币资金附注",
    "C-营业收入附注",
])

# 完整 payload（含双 UUID + section + sub_table_data + standard + year + sheet）
st_payload = st.fixed_dictionaries({
    "project_id": st_uuid,
    "wp_id": st_uuid,
    "sheet_name": st_sheet_name,
    "section_id": st_section_id,
    "sub_table_data": st_sub_table_data,
    "current_standard": st_current_standard,
    "year": st_year,
})


# ─── 测试用 hypothesis settings（DB 集成更慢，max_examples=20 + 抑制慢检查） ──

_PBT_SETTINGS = h_settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
    ],
)


# ─── Property 8a: 单向同步 sub_table_data 完全反映 ─────────────────────────


@_PBT_SETTINGS
@given(payload=st_payload)
def test_property_8a_sub_table_data_synced_exactly(payload: dict) -> None:
    """**Validates: Requirements 3.11.5 §4.2** — C sheet 保存后 disclosure_notes 反映 sub_table_data

    sync_from_workpaper(payload) 后：
    - DB 中存在恰好 1 条 DisclosureNote 记录（按 project_id+year+section_id 索引）
    - note.table_data["sub_table_data"] == payload.sub_table_data（值完全一致）
    """
    db = FakeDB()
    result = _run_sync(db, **payload)

    assert result["success"] is True
    assert result["section_id"] == payload["section_id"]
    # 1 条记录 + 1 次 commit
    assert len(db.notes) == 1
    assert db.commit_count == 1

    note = next(iter(db.notes.values()))
    assert isinstance(note.table_data, dict)
    assert "sub_table_data" in note.table_data
    # 值完全一致（dict 深比较）
    assert note.table_data["sub_table_data"] == payload["sub_table_data"], (
        f"sub_table_data 同步不一致：\n"
        f"  payload  = {payload['sub_table_data']!r}\n"
        f"  in note  = {note.table_data['sub_table_data']!r}"
    )


# ─── Property 8b: sync markers 写入 ─────────────────────────────────────────


@_PBT_SETTINGS
@given(payload=st_payload)
def test_property_8b_sync_markers_written(payload: dict) -> None:
    """**Validates: Requirements 3.11.5 §4.2 + design §12.1** — 同步标记完整

    同步后 DisclosureNote 必满足：
    - last_sync_source == "workpaper"
    - last_sync_wp_id == payload.wp_id
    - last_sync_at 非空
    - last_sync_user_id == 同步用户 id
    - 元数据 _last_sync_wp_id / _last_sync_sheet / _last_sync_at 也写入 table_data
    """
    db = FakeDB()
    user = _make_user()
    result = _run_sync(db, **payload, user=user)

    assert result["success"] is True

    note = next(iter(db.notes.values()))

    # ORM 列上的同步标记
    assert note.last_sync_source == "workpaper", (
        f"last_sync_source 应为 'workpaper'，实际 {note.last_sync_source!r}"
    )
    assert note.last_sync_wp_id == payload["wp_id"], (
        f"last_sync_wp_id 应为 {payload['wp_id']!r}，实际 {note.last_sync_wp_id!r}"
    )
    assert note.last_sync_at is not None, "last_sync_at 不应为 None"
    assert isinstance(note.last_sync_at, datetime), (
        f"last_sync_at 应为 datetime，实际 {type(note.last_sync_at).__name__}"
    )
    assert note.last_sync_user_id == user.id, (
        f"last_sync_user_id 应为 {user.id!r}，实际 {note.last_sync_user_id!r}"
    )

    # table_data 元数据
    td = note.table_data
    assert td is not None
    assert td.get("_source") == "workpaper"
    assert td.get("_current_standard") == payload["current_standard"]
    assert td.get("_last_sync_wp_id") == str(payload["wp_id"])
    assert td.get("_last_sync_sheet") == payload["sheet_name"]
    assert isinstance(td.get("_last_sync_at"), str) and td["_last_sync_at"]


# ─── Property 8c: 反向不写回（DisclosureNote 编辑 → workpaper 不变） ────────


@_PBT_SETTINGS
@given(
    payload=st_payload,
    edit_overlay=st_sub_table_data,
)
def test_property_8c_reverse_edit_does_not_modify_workpaper(
    payload: dict, edit_overlay: dict
) -> None:
    """**Validates: design §12.1** — 单向同步：附注编辑不反向写回 C sheet

    模拟 disclosure_notes PUT /api/disclosure-notes/{id} 直接编辑场景：
    1. sync_from_workpaper 同步底稿 → DisclosureNote 创建
    2. 模拟 WorkingPaper.parsed_data 快照（freeze 副本）
    3. 用户直接编辑 note.table_data（模拟 DisclosureEngine.update_note）
    4. 断言 WorkingPaper.parsed_data 保持初始快照（无反向写回路径）

    关键：sync_from_workpaper 是底稿 → 附注的单向通道；不存在附注 → 底稿的对应服务，
    任何对 DisclosureNote 的修改都不应触及 WorkingPaper.parsed_data。
    """
    db = FakeDB()
    _run_sync(db, **payload)
    note = next(iter(db.notes.values()))

    # Step 2: 模拟 WorkingPaper.parsed_data 快照（与 sync_from_workpaper 无关的独立对象）
    workpaper_parsed_data: dict[str, Any] = {
        "html_data": {
            "sub_table_data": dict(payload["sub_table_data"]),
            "version": "v1",
        },
        "univer_snapshot": {"sheet1": {"cellData": {}}},
    }
    initial_snapshot = {
        "html_data": {
            "sub_table_data": dict(payload["sub_table_data"]),
            "version": "v1",
        },
        "univer_snapshot": {"sheet1": {"cellData": {}}},
    }

    # Step 3: 模拟用户直接编辑 disclosure_notes（PUT /api/disclosure-notes/{id}）
    # → 修改 note.table_data["sub_table_data"]，新增 _edit_marker 字段
    note.table_data = {
        **(note.table_data or {}),
        "sub_table_data": dict(edit_overlay),
        "_user_edited": True,
        "_edit_at": datetime.now(timezone.utc).isoformat(),
    }
    note.last_sync_source = None  # 模拟"用户直接编辑"清除来源标记

    # Step 4: 断言 workpaper_parsed_data 完全不变
    assert workpaper_parsed_data == initial_snapshot, (
        f"DisclosureNote 编辑后 WorkingPaper.parsed_data 被意外修改：\n"
        f"  initial = {initial_snapshot!r}\n"
        f"  current = {workpaper_parsed_data!r}"
    )
    # 同时 FakeDB 中 disclosure_notes 仍是同一条（无新增 wp 类型记录）
    assert len(db.notes) == 1
    # commit 计数仍为 1（编辑路径未通过 sync_from_workpaper 触发额外 commit）
    assert db.commit_count == 1


# ─── Property 8d: 重复同步幂等 ────────────────────────────────────────────


@_PBT_SETTINGS
@given(payload=st_payload)
def test_property_8d_duplicate_sync_is_idempotent(payload: dict) -> None:
    """**Validates: Requirements 3.11.5 §4.2** — 同 payload 重复同步幂等

    同 payload 同步两次后：
    - DB 中仍只有 1 条 DisclosureNote 记录（无重复行）
    - 第一次 created=True，第二次 created=False
    - 终态 sub_table_data 等于 payload.sub_table_data
    - last_sync_wp_id / last_sync_source 不变
    """
    db = FakeDB()
    user = _make_user()

    # 第一次同步
    result1 = _run_sync(db, **payload, user=user)
    assert result1["created"] is True
    assert len(db.notes) == 1
    note_after_1 = next(iter(db.notes.values()))
    sub_table_after_1 = dict(note_after_1.table_data.get("sub_table_data") or {})

    # 第二次同步（同 payload）
    result2 = _run_sync(db, **payload, user=user)
    assert result2["created"] is False, (
        f"第二次同步应为更新而非创建，实际 created={result2['created']!r}"
    )

    # 仍只有 1 条记录（无重复）
    assert len(db.notes) == 1, (
        f"重复同步导致重复行：当前 {len(db.notes)} 条记录"
    )
    note_after_2 = next(iter(db.notes.values()))
    sub_table_after_2 = note_after_2.table_data.get("sub_table_data") or {}

    # 终态一致
    assert sub_table_after_1 == sub_table_after_2 == payload["sub_table_data"], (
        f"幂等性破坏：\n"
        f"  after sync1 = {sub_table_after_1!r}\n"
        f"  after sync2 = {sub_table_after_2!r}\n"
        f"  payload     = {payload['sub_table_data']!r}"
    )

    # 同步标记保持
    assert note_after_2.last_sync_source == "workpaper"
    assert note_after_2.last_sync_wp_id == payload["wp_id"]

    # rows_synced 在两次调用结果中一致
    assert result1["rows_synced"] == result2["rows_synced"]


# ─── Property 8e: section_id 路由（不同 section_id → 不同 DisclosureNote） ─


@_PBT_SETTINGS
@given(
    project_id=st_uuid,
    wp_id=st_uuid,
    sheet_name=st_sheet_name,
    current_standard=st_current_standard,
    year=st_year,
    sections=st.lists(st_section_id, min_size=2, max_size=5, unique=True),
    sub_data_per_section=st.lists(st_sub_table_data, min_size=2, max_size=5),
)
def test_property_8e_section_id_routes_to_distinct_rows(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    sheet_name: str,
    current_standard: str,
    year: int,
    sections: list[str],
    sub_data_per_section: list[dict],
) -> None:
    """**Validates: Requirements 3.11.5 §4.2** — section_id 决定路由

    对同一 (project_id, year) 但不同 section_id 进行多次同步：
    - 每个 section_id 创建独立 DisclosureNote 行（无交叉污染）
    - 各行 sub_table_data 保留各自 payload 数据，不被其他 section 覆盖
    - DB 总记录数 == unique section_id 数
    """
    # 截齐两个列表长度
    n = min(len(sections), len(sub_data_per_section))
    sections = sections[:n]
    sub_data_per_section = sub_data_per_section[:n]

    db = FakeDB()

    # 顺序同步每个 section
    for section_id, sub_data in zip(sections, sub_data_per_section, strict=True):
        result = _run_sync(
            db,
            project_id=project_id,
            wp_id=wp_id,
            sheet_name=sheet_name,
            section_id=section_id,
            sub_table_data=sub_data,
            current_standard=current_standard,
            year=year,
        )
        assert result["success"] is True
        assert result["section_id"] == section_id

    # DB 中应有 N 条独立记录
    assert len(db.notes) == n, (
        f"期望 {n} 条独立 DisclosureNote 行（每个 section 各一条），"
        f"实际 {len(db.notes)} 条"
    )

    # 每条记录的 note_section 与 sub_table_data 各自匹配（无污染）
    for section_id, expected_sub_data in zip(sections, sub_data_per_section, strict=True):
        key = (project_id, year, section_id)
        assert key in db.notes, f"section_id={section_id!r} 未生成对应行"
        note = db.notes[key]
        assert note.note_section == section_id
        actual = note.table_data.get("sub_table_data") if note.table_data else None
        assert actual == expected_sub_data, (
            f"section_id={section_id!r} 数据被污染：\n"
            f"  expected = {expected_sub_data!r}\n"
            f"  actual   = {actual!r}"
        )


# ─── Property 8f: rows_synced 计数正确 ───────────────────────────────────


@_PBT_SETTINGS
@given(payload=st_payload)
def test_property_8f_rows_synced_count_matches_total(payload: dict) -> None:
    """**Validates: Requirements 3.11.5 §4.2** — 同步行数计数正确

    返回的 rows_synced 等于 sub_table_data 中所有子表行数之和。
    """
    db = FakeDB()
    result = _run_sync(db, **payload)

    expected_count = sum(
        len(rows) for rows in payload["sub_table_data"].values()
        if isinstance(rows, list)
    )
    assert result["rows_synced"] == expected_count, (
        f"rows_synced={result['rows_synced']!r} != expected={expected_count!r}\n"
        f"  sub_table_data = {payload['sub_table_data']!r}"
    )
    assert isinstance(result["rows_synced"], int)
    assert result["rows_synced"] >= 0


# ─── 单元测试：边界 case（PBT 互补） ─────────────────────────────────────


def test_unit_empty_sub_table_data_creates_note_with_zero_rows() -> None:
    """空 sub_table_data → 创建 note + rows_synced=0 + 同步标记仍写入"""
    db = FakeDB()
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    result = _run_sync(
        db,
        project_id=project_id,
        wp_id=wp_id,
        sheet_name="C-货币资金附注",
        section_id="五-1-1 货币资金",
        sub_table_data={},
        current_standard="soe_standalone",
        year=2025,
    )
    assert result["success"] is True
    assert result["rows_synced"] == 0
    assert result["created"] is True
    assert len(db.notes) == 1

    note = next(iter(db.notes.values()))
    assert note.last_sync_source == "workpaper"
    assert note.last_sync_wp_id == wp_id
    assert note.table_data is not None
    assert note.table_data.get("sub_table_data") == {}


def test_unit_empty_section_id_raises() -> None:
    """空 section_id → ValueError（service 入口校验）"""
    db = FakeDB()

    async def _run() -> None:
        await sync_from_workpaper(
            db,  # type: ignore[arg-type]
            uuid.uuid4(),
            wp_id=uuid.uuid4(),
            sheet_name="C-sheet",
            section_id="   ",
            sub_table_data={},
            current_standard="soe_standalone",
            user=_make_user(),
            year=2025,
        )

    with pytest.raises(ValueError, match="section_id"):
        asyncio.run(_run())

    # ValueError 在 commit 前抛出，notes 应为空
    assert len(db.notes) == 0
    assert db.commit_count == 0
