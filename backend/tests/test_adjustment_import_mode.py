"""中央调整分录导入 —— Import_Mode（append / overwrite）属性测试。

spec: adjustment-import-export-contract / Task 1.2

覆盖：
  Property 1 — Overwrite 幂等：同一文件以 mode=overwrite 连续导入 N 次 ≡ 1 次。
  Property 3 — Overwrite 覆盖范围安全：`approved` / 活跃协作 / `origin='workpaper'`
               的分录组不被覆盖，且在 `skipped` + `skipped_rows` 中可见。
  （Property 2 —— append 逐字节不变 —— 由 test_adjustment_ie_characterization.py 保障。）

测试替身说明：
  - `_StoreDB` 是最小 AsyncSession 替身，按**语句涉及的表**分派：
      account_chart / account_mapping → 项目科目库
      adjustments (SELECT)            → 内存 store 中该编号的未软删行
      adjustments (UPDATE)            → 把新建组的编号钉为文件编号
      adjustment_collaboration        → 活跃协作计数
    因此 `has_active_collaboration` 走的是**真实实现**（非 mock）。
  - `AdjustmentService` 用记录式替身（避免 audit_log 装饰器 / event_bus 触真实 DB），
    但 create/delete 都落到同一 store，使"覆盖后再导入"能真实观察幂等性。
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.audit_platform_models import AccountSource, ReviewStatus

# ═══════════════════════════════════════════════════════════════════════════
# 内存 store + fake DB
# ═══════════════════════════════════════════════════════════════════════════

_CHART_ROWS = [
    ("1122", "应收账款", AccountSource.standard),
    ("1231", "坏账准备", AccountSource.standard),
    ("6602", "管理费用", AccountSource.standard),
]
_MAPPING_ROWS: list[tuple[str, str]] = []


class _Group:
    """store 内的一个分录组（对应 adjustments 表同 entry_group_id 的多行）。"""

    def __init__(
        self,
        *,
        adjustment_no: str,
        adj_type: str,
        description: str,
        lines: list[tuple[str, Decimal, Decimal]],
        review_status: ReviewStatus = ReviewStatus.draft,
        origin: str = "manual",
        collab: bool = False,
        entry_group_id: UUID | None = None,
    ):
        self.entry_group_id = entry_group_id or uuid4()
        self.adjustment_no = adjustment_no
        self.adj_type = adj_type
        self.description = description
        self.lines = lines
        self.review_status = review_status
        self.origin = origin
        self.collab = collab
        self.is_deleted = False

    # 供 fake DB 当作 Adjustment ORM 行返回（只用到这几个属性）
    def as_row(self):
        return SimpleNamespace(
            entry_group_id=self.entry_group_id,
            adjustment_no=self.adjustment_no,
            review_status=self.review_status,
            origin=self.origin,
        )

    def snapshot(self) -> tuple:
        return (
            self.adjustment_no,
            self.adj_type,
            self.description,
            tuple(self.lines),
            self.review_status,
            self.origin,
        )


class _Store:
    def __init__(self, groups: list[_Group] | None = None):
        self.groups: list[_Group] = list(groups or [])

    # ── 查询 ──
    def active_by_no(self, adjustment_no: str) -> list[_Group]:
        return [
            g for g in self.groups
            if not g.is_deleted and g.adjustment_no == adjustment_no
        ]

    def active(self) -> list[_Group]:
        return [g for g in self.groups if not g.is_deleted]

    def collab_count(self, entry_group_id: UUID) -> int:
        return sum(
            1 for g in self.groups
            if g.entry_group_id == entry_group_id and g.collab and not g.is_deleted
        )

    # ── 变更 ──
    def next_no(self, adj_type: str) -> str:
        """复现真实 _next_adjustment_no：同类型组计数 +1（**含已软删组**）。"""
        prefix = "AJE" if adj_type == "aje" else "RJE"
        count = sum(1 for g in self.groups if g.adj_type == adj_type)
        return f"{prefix}-{count + 1:03d}"

    def soft_delete(self, entry_group_id: UUID) -> None:
        for g in self.groups:
            if g.entry_group_id == entry_group_id:
                g.is_deleted = True

    def pin_no(self, entry_group_id: UUID, adjustment_no: str) -> None:
        for g in self.groups:
            if g.entry_group_id == entry_group_id and not g.is_deleted:
                g.adjustment_no = adjustment_no


class _FakeResult:
    def __init__(self, rows: list, scalar_value=None):
        self._rows = list(rows)
        self._scalar = scalar_value

    def all(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


def _stmt_params(stmt) -> dict:
    try:
        return dict(stmt.compile().params)
    except Exception:  # pragma: no cover - 防御
        return {}


def _pick_named(params: dict, name: str):
    """按参数名取绑定值（`entry_group_id_1` / `adjustment_no` 等）。

    不能按"第一个 UUID"取值：where 子句里 project_id 通常排在 entry_group_id 之前。
    """
    for key, val in params.items():
        if key == name or key.startswith(f"{name}_"):
            return val
    return None


class _StoreDB:
    """按语句涉及的表分派的最小 AsyncSession 替身（不触库）。"""

    def __init__(self, store: _Store):
        self.store = store
        self.updates: list[tuple[UUID, str]] = []

    async def execute(self, stmt, *_a, **_kw):
        sql = str(stmt).lower()
        params = _stmt_params(stmt)

        if "update adjustments" in sql:
            gid = _pick_named(params, "entry_group_id")
            new_no = _pick_named(params, "adjustment_no")
            assert isinstance(gid, UUID) and isinstance(new_no, str), params
            self.store.pin_no(gid, new_no)
            self.updates.append((gid, new_no))
            return _FakeResult([])

        if "from account_chart" in sql:
            return _FakeResult(_CHART_ROWS)
        if "from account_mapping" in sql:
            return _FakeResult(_MAPPING_ROWS)
        if "from adjustment_collaboration" in sql:
            gid = _pick_named(params, "entry_group_id")
            assert isinstance(gid, UUID), params
            return _FakeResult([], scalar_value=self.store.collab_count(gid))
        if "from adjustments" in sql:
            no = _pick_named(params, "adjustment_no")
            assert isinstance(no, str), params
            return _FakeResult([g.as_row() for g in self.store.active_by_no(no)])

        return _FakeResult([])

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None

    def add(self, _obj):
        return None


class _StoreSvc:
    """AdjustmentService 替身：create/delete 落到同一 store。"""

    db_ref: _StoreDB | None = None

    def __init__(self, db):
        self._db = db

    async def create_entry(self, project_id, data, user_id):
        adj_type = data.adjustment_type.value
        store = self._db.store
        group = _Group(
            adjustment_no=store.next_no(adj_type),
            adj_type=adj_type,
            description=data.description or "",
            lines=[
                (li.standard_account_code, li.debit_amount, li.credit_amount)
                for li in data.line_items
            ],
        )
        store.groups.append(group)
        return SimpleNamespace(entry_group_id=group.entry_group_id)

    async def delete_entry(self, project_id, entry_group_id):
        self._db.store.soft_delete(entry_group_id)


def _patch_service(monkeypatch):
    import app.services.adjustment_service as adj_mod

    monkeypatch.setattr(adj_mod, "AdjustmentService", _StoreSvc)


async def _run_import(store: _Store, rows: list[dict], mode: str) -> tuple[dict, _StoreDB]:
    from app.routers.import_templates import _import_adjustments

    db = _StoreDB(store)
    result = await _import_adjustments(
        rows, uuid4(), 2025, SimpleNamespace(id=uuid4()), db, mode=mode,
    )
    return result, db


def _file_rows(amount: int) -> list[dict]:
    """两笔分录、各两行（借贷各一行）的典型文件内容。"""
    return [
        {"编号": "AJE-001", "类型": "AJE", "摘要": "补提坏账",
         "科目名称": "应收账款", "科目编码": "1122", "借方金额": str(amount)},
        {"编号": "AJE-001", "类型": "AJE", "摘要": "补提坏账",
         "科目名称": "坏账准备", "科目编码": "1231", "贷方金额": str(amount)},
        {"编号": "AJE-002", "类型": "AJE", "摘要": "费用重分类",
         "科目名称": "管理费用", "科目编码": "6602", "借方金额": str(amount * 2)},
        {"编号": "AJE-002", "类型": "AJE", "摘要": "费用重分类",
         "科目名称": "应收账款", "科目编码": "1122", "贷方金额": str(amount * 2)},
    ]


def _active_snapshots(store: _Store) -> set[tuple]:
    return {g.snapshot() for g in store.active()}


# ═══════════════════════════════════════════════════════════════════════════
# Property 1 — Overwrite 幂等
# ═══════════════════════════════════════════════════════════════════════════


@settings(max_examples=5, deadline=None)
@given(times=st.integers(min_value=2, max_value=4), amount=st.integers(min_value=1, max_value=99999))
def test_property1_overwrite_is_idempotent(monkeypatch, times: int, amount: int):
    """同一文件以 overwrite 导入 N 次（N≥2）与导入 1 次业务等价，不产生重复分录组。"""
    _patch_service(monkeypatch)
    rows = _file_rows(amount)

    async def _scenario(n: int) -> _Store:
        store = _Store()
        for _ in range(n):
            result, _db = await _run_import(store, rows, "overwrite")
            assert result["failed"] == 0, result
        return store

    once = asyncio.run(_scenario(1))
    many = asyncio.run(_scenario(times))

    # 编号集合与内容等价
    assert _active_snapshots(many) == _active_snapshots(once)
    # 未成倍追加：两个编号 → 两个活跃分录组
    assert len(many.active()) == 2
    assert sorted(g.adjustment_no for g in many.active()) == ["AJE-001", "AJE-002"]


def test_overwrite_pins_file_adjustment_no(monkeypatch):
    """覆盖模式把新建组的编号钉为文件编号（否则自动编号漂移 → 下次匹配不上不幂等）。"""
    _patch_service(monkeypatch)
    store = _Store()

    result, db = asyncio.run(_run_import(store, _file_rows(100), "overwrite"))

    assert result["imported"] == 2
    assert len(db.updates) == 2, "每个带编号的新建组都应发一条编号钉住 UPDATE"
    assert sorted(no for _gid, no in db.updates) == ["AJE-001", "AJE-002"]


def test_append_mode_duplicates_and_does_not_pin(monkeypatch):
    """append 模式保持既有行为：重复导入成倍追加，且不改编号（Property 2 对照）。"""
    _patch_service(monkeypatch)
    store = _Store()
    rows = _file_rows(100)

    asyncio.run(_run_import(store, rows, "append"))
    result, db = asyncio.run(_run_import(store, rows, "append"))

    assert result["skipped"] == 0
    assert "skipped_rows" not in result
    assert len(store.active()) == 4, "append 不做 by-key 覆盖 → 第二次导入追加为新组"
    assert db.updates == [], "append 不钉编号"


def test_illegal_mode_degrades_to_append(monkeypatch):
    """非法 mode 值降级为 append（不抛 500），行为与 append 一致。"""
    _patch_service(monkeypatch)
    store = _Store()
    rows = _file_rows(100)

    asyncio.run(_run_import(store, rows, "OVERWRITE_TYPO"))
    result, db = asyncio.run(_run_import(store, rows, ""))

    assert result["failed"] == 0 and result["skipped"] == 0
    assert len(store.active()) == 4
    assert db.updates == []


def test_overwrite_keeps_numbers_absent_from_file(monkeypatch):
    """文件里没有的编号保留（绝不清空全年 manual 分录）。"""
    _patch_service(monkeypatch)
    keep = _Group(
        adjustment_no="AJE-900", adj_type="aje", description="中央页手工新建",
        lines=[("1122", Decimal("7"), Decimal("0"))],
    )
    store = _Store([keep])

    result, _db = asyncio.run(_run_import(store, _file_rows(100), "overwrite"))

    assert result["imported"] == 2 and result["skipped"] == 0
    assert keep in store.active(), "文件未涉及的编号必须原样保留"


def test_overwrite_rows_without_no_are_appended(monkeypatch):
    """未填编号的行无 by-key 键 → 两种模式均为追加（不误覆盖任何既有组）。"""
    _patch_service(monkeypatch)
    store = _Store()
    rows = [
        {"类型": "AJE", "摘要": "无编号借", "科目名称": "应收账款", "借方金额": "5"},
        {"类型": "AJE", "摘要": "无编号贷", "科目名称": "坏账准备", "贷方金额": "5"},
    ]

    asyncio.run(_run_import(store, rows, "overwrite"))
    result, db = asyncio.run(_run_import(store, rows, "overwrite"))

    assert result["imported"] == 2 and result["skipped"] == 0
    assert len(store.active()) == 4
    assert db.updates == [], "无编号组不钉编号"


# ═══════════════════════════════════════════════════════════════════════════
# Property 3 — Overwrite 覆盖范围安全
# ═══════════════════════════════════════════════════════════════════════════


def _protected_store() -> tuple[_Store, dict[str, _Group]]:
    approved = _Group(
        adjustment_no="AJE-001", adj_type="aje", description="已审批",
        lines=[("1122", Decimal("11"), Decimal("0"))],
        review_status=ReviewStatus.approved,
    )
    workpaper = _Group(
        adjustment_no="AJE-002", adj_type="aje", description="底稿同步",
        lines=[("6602", Decimal("22"), Decimal("0"))],
        origin="workpaper",
    )
    collab = _Group(
        adjustment_no="AJE-003", adj_type="aje", description="协作中",
        lines=[("1231", Decimal("33"), Decimal("0"))],
        collab=True,
    )
    plain = _Group(
        adjustment_no="AJE-004", adj_type="aje", description="普通手工",
        lines=[("1122", Decimal("44"), Decimal("0"))],
    )
    store = _Store([approved, workpaper, collab, plain])
    return store, {
        "approved": approved, "workpaper": workpaper,
        "collab": collab, "plain": plain,
    }


def _rows_for(no: str, desc: str) -> list[dict]:
    return [
        {"编号": no, "类型": "AJE", "摘要": desc,
         "科目名称": "应收账款", "科目编码": "1122", "借方金额": "1000"},
        {"编号": no, "类型": "AJE", "摘要": desc,
         "科目名称": "坏账准备", "科目编码": "1231", "贷方金额": "1000"},
    ]


def test_property3_protected_groups_are_skipped_with_reasons(monkeypatch):
    """approved / 活跃协作 / origin=workpaper 不被覆盖，且在 skipped + skipped_rows 可见。"""
    _patch_service(monkeypatch)
    store, g = _protected_store()
    before = {k: v.snapshot() for k, v in g.items()}

    rows: list[dict] = []
    for no in ("AJE-001", "AJE-002", "AJE-003", "AJE-004"):
        rows.extend(_rows_for(no, f"文件覆盖 {no}"))

    result, _db = asyncio.run(_run_import(store, rows, "overwrite"))

    # 三个受保护组被跳过，仅普通手工组被覆盖
    assert result["skipped"] == 3, result
    assert result["imported"] == 1, result
    assert result["failed"] == 0, result

    reasons = {r["adj_no"]: r["reason"] for r in result["skipped_rows"]}
    assert set(reasons) == {"AJE-001", "AJE-002", "AJE-003"}
    assert "复核通过" in reasons["AJE-001"]
    assert "底稿同步" in reasons["AJE-002"]
    assert "协作" in reasons["AJE-003"]
    for r in result["skipped_rows"]:
        assert r["rows_in_group"], "跳过项须给出行号便于定位"

    # 受保护组仍存在且字段未变
    for key in ("approved", "workpaper", "collab"):
        assert not g[key].is_deleted, f"{key} 组不应被软删"
        assert g[key].snapshot() == before[key], f"{key} 组字段不应被改动"

    # 普通手工组被替换：旧组软删 + 新组接管同编号
    assert g["plain"].is_deleted is True
    replaced = store.active_by_no("AJE-004")
    assert len(replaced) == 1 and replaced[0].description == "文件覆盖 AJE-004"


def test_protected_groups_untouched_in_append_mode(monkeypatch):
    """append 模式不做覆盖判定：受保护组既不跳过也不改动（追加新组）。"""
    _patch_service(monkeypatch)
    store, g = _protected_store()

    result, _db = asyncio.run(_run_import(store, _rows_for("AJE-001", "追加"), "append"))

    assert result["imported"] == 1 and result["skipped"] == 0
    assert not g["approved"].is_deleted
    assert g["approved"].description == "已审批"


def test_overwrite_failure_does_not_abort_other_numbers(monkeypatch):
    """单编号覆盖失败计入 failed_rows 并继续处理其余编号（不整批回滚）。"""
    import app.services.adjustment_service as adj_mod

    class _FlakySvc(_StoreSvc):
        async def delete_entry(self, project_id, entry_group_id):
            raise ValueError("当前状态 pending_review 不允许删除")

    monkeypatch.setattr(adj_mod, "AdjustmentService", _FlakySvc)

    existing = _Group(
        adjustment_no="AJE-001", adj_type="aje", description="待复核",
        lines=[("1122", Decimal("1"), Decimal("0"))],
        review_status=ReviewStatus.pending_review,
    )
    store = _Store([existing])
    rows = _rows_for("AJE-001", "覆盖失败") + _rows_for("AJE-777", "其余编号照常")

    result, _db = asyncio.run(_run_import(store, rows, "overwrite"))

    assert result["failed"] == 1
    assert result["failed_rows"][0]["adj_no"] == "AJE-001"
    assert "不允许删除" in result["failed_rows"][0]["error"]
    assert result["imported"] == 1, "其余编号仍应正常导入"
    assert [g.adjustment_no for g in store.active_by_no("AJE-777")] == ["AJE-777"]
    assert not existing.is_deleted, "覆盖失败不得留下半删状态"


def test_overwrite_replace_goes_through_service_delete_entry(monkeypatch):
    """覆盖时的失效必须走 `AdjustmentService.delete_entry`（R1.6 试算表重算链路）。

    `delete_entry` 内部软删分录行 + 发 `ADJUSTMENT_DELETED` 事件 → 触发与手工删除
    同一条试算表重算链路。若实现改成裸 SQL `UPDATE adjustments SET is_deleted`
    直接软删，落库结果看似相同但**不会触发重算**，`trial_balance` 会残留被覆盖分录
    的影响（R1.6 失守）——本用例以"delete_entry 被调用 + 无裸软删 UPDATE"锁定该路径。
    """
    import app.services.adjustment_service as adj_mod

    deleted: list[UUID] = []

    class _SpySvc(_StoreSvc):
        async def delete_entry(self, project_id, entry_group_id):
            deleted.append(entry_group_id)
            await super().delete_entry(project_id, entry_group_id)

    monkeypatch.setattr(adj_mod, "AdjustmentService", _SpySvc)

    old = _Group(
        adjustment_no="AJE-001", adj_type="aje", description="旧内容",
        lines=[("1122", Decimal("1"), Decimal("0"))],
    )
    store = _Store([old])

    result, db = asyncio.run(_run_import(store, _rows_for("AJE-001", "新内容"), "overwrite"))

    assert result["imported"] == 1 and result["skipped"] == 0
    assert deleted == [old.entry_group_id], (
        "覆盖必须调 delete_entry(被覆盖组)，不得用裸 SQL 软删绕过重算链路"
    )
    assert old.is_deleted is True
    # db.updates 只应有「编号钉住」这一类 UPDATE（adjustment_no），没有裸软删 UPDATE
    assert [no for _gid, no in db.updates] == ["AJE-001"]


def test_overwrite_skip_does_not_delete_anything(monkeypatch):
    """跳过路径不得触发任何删除（受保护组不进重算链路）。"""
    import app.services.adjustment_service as adj_mod

    deleted: list[UUID] = []

    class _SpySvc(_StoreSvc):
        async def delete_entry(self, project_id, entry_group_id):
            deleted.append(entry_group_id)
            await super().delete_entry(project_id, entry_group_id)

    monkeypatch.setattr(adj_mod, "AdjustmentService", _SpySvc)
    store, g = _protected_store()

    result, _db = asyncio.run(
        _run_import(store, _rows_for("AJE-001", "覆盖已审批"), "overwrite")
    )

    assert result["skipped"] == 1 and result["imported"] == 0
    assert deleted == [], "受保护组被跳过时不得调 delete_entry"
    assert not g["approved"].is_deleted


@pytest.mark.parametrize("status", [ReviewStatus.draft, ReviewStatus.rejected])
def test_overwrite_replaces_draft_and_rejected(monkeypatch, status):
    """draft / rejected 的 manual 分录组可被覆盖（不在受保护集合内）。"""
    _patch_service(monkeypatch)
    old = _Group(
        adjustment_no="AJE-001", adj_type="aje", description="旧内容",
        lines=[("1122", Decimal("1"), Decimal("0"))], review_status=status,
    )
    store = _Store([old])

    result, _db = asyncio.run(_run_import(store, _rows_for("AJE-001", "新内容"), "overwrite"))

    assert result["imported"] == 1 and result["skipped"] == 0
    assert old.is_deleted is True
    assert store.active_by_no("AJE-001")[0].description == "新内容"
