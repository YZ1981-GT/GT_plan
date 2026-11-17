"""`unit_policy_snapshot` 生产写入方守卫
（spec platform-global-display-settings-closure 任务 10 / AC-21）。

覆盖四类判据：

1. **快照必含 digest**：`_digest` 是 64 位 hex 且等于 policy 自己的
   `canonical_digest` —— 只存 unit 不存 digest 就无法证明「当时算的就是这份」。
2. **幂等**：同 input 两次构造逐字节相同（否则每次导出都产生新证据，
   归档里「同一 policy」无法比对）。
3. **fallback 必须标**：读不到项目单位回落 yuan 时快照必须带 `_fallback: true`
   —— 静默回落会让「元」看起来像用户正常选择。
4. **非法 unit 要抛**：静默接受未知单位会让 divisor 落成 1（金额放大 1 万倍）。

🔴 判据不许只测纯函数：`build_policy_snapshot` 与 `resolve_policy_snapshot_for_project`
两条路径都要测（前者是内核、后者是生产入口；只测内核会漏「生产入口没标 fallback」）。
"""

from __future__ import annotations

import json
import re
import uuid

import pytest

from app.services.export_policy_snapshot import (
    _UNIT_DIVISORS,
    build_policy_snapshot,
    resolve_policy_snapshot_for_project,
)


class _FakeDb:
    """最小 AsyncSession 替身：`execute()` 返回带 `.first()` 的对象。"""

    def __init__(self, row):
        self._row = row
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):  # noqa: ANN001
        self.calls.append((str(stmt), dict(params or {})))
        row = self._row

        class _Result:
            def first(self_inner):  # noqa: N805
                return row

        return _Result()


class _BoomDb:
    async def execute(self, stmt, params=None):  # noqa: ANN001
        raise RuntimeError("connection lost")


# ---------------------------------------------------------------------------
# 1. 快照结构与 digest
# ---------------------------------------------------------------------------


def test_snapshot_contains_64_hex_digest():
    snapshot = build_policy_snapshot(project_id=uuid.uuid4(), unit="wan")
    payload = json.loads(snapshot)
    assert re.fullmatch(r"[0-9a-f]{64}", payload["_digest"]), payload


def test_snapshot_digest_equals_policy_canonical_digest():
    """`_digest` 必须等于 `ExportUnitPolicy.compute_digest()` 的 canonical_digest。

    这两处若各自算一遍，任何一侧改口径都会让「同一份 policy 两条记录不同 digest」。
    """
    from app.schemas.export_unit_policy import ExportUnitPolicy

    pid = uuid.uuid4()
    payload = json.loads(build_policy_snapshot(project_id=pid, unit="qian"))
    expected = ExportUnitPolicy(
        project_id=pid, unit="qian", divisor=1000, regions=[]
    ).compute_digest()
    assert payload["_digest"] == expected.canonical_digest


def test_snapshot_carries_divisor_from_single_source():
    """divisor 必须取自 `_UNIT_DIVISORS`，不得各处各写一份。"""
    for unit, divisor in _UNIT_DIVISORS.items():
        payload = json.loads(build_policy_snapshot(project_id=uuid.uuid4(), unit=unit))
        assert payload["divisor"] == divisor, unit


def test_snapshot_divisor_mapping_values():
    """三个单位档位现读钉住（改档位会让历史快照的 divisor 语义漂移）。"""
    assert _UNIT_DIVISORS == {"yuan": 1, "qian": 1000, "wan": 10000}


def test_snapshot_records_project_id():
    pid = uuid.uuid4()
    payload = json.loads(build_policy_snapshot(project_id=pid, unit="yuan"))
    assert payload["_project_id"] == str(pid)


# ---------------------------------------------------------------------------
# 2. 幂等
# ---------------------------------------------------------------------------


def test_snapshot_is_idempotent():
    pid = uuid.uuid4()
    first = build_policy_snapshot(project_id=pid, unit="wan")
    second = build_policy_snapshot(project_id=pid, unit="wan")
    assert first == second


def test_snapshot_is_canonical_json():
    """键排序 + 无空格：换 Python 版本 / dict 插入顺序都不改变字节。"""
    snapshot = build_policy_snapshot(project_id=uuid.uuid4(), unit="wan")
    assert " " not in snapshot.replace('"yuan"', '"yuan"'), snapshot
    payload = json.loads(snapshot)
    assert list(payload) == sorted(payload)


# ---------------------------------------------------------------------------
# 3. fallback 标记
# ---------------------------------------------------------------------------


def test_fallback_snapshot_is_marked():
    payload = json.loads(
        build_policy_snapshot(project_id=uuid.uuid4(), unit="yuan", fallback=True)
    )
    assert payload["_fallback"] is True
    assert payload["divisor"] == 1


def test_non_fallback_snapshot_has_no_fallback_key():
    """正常路径不得出现 `_fallback` 键（出现即「消费方无法区分降级」）。"""
    payload = json.loads(build_policy_snapshot(project_id=uuid.uuid4(), unit="wan"))
    assert "_fallback" not in payload


def test_fallback_and_normal_differ_in_bytes():
    """降级快照必须与正常 yuan 快照逐字节不同，否则标记等于没写。"""
    pid = uuid.uuid4()
    normal = build_policy_snapshot(project_id=pid, unit="yuan", fallback=False)
    degraded = build_policy_snapshot(project_id=pid, unit="yuan", fallback=True)
    assert normal != degraded


# ---------------------------------------------------------------------------
# 4. 非法输入
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_unit", ["", "WAN", "万元", "yi", None])
def test_build_rejects_unknown_unit(bad_unit):
    """非法 unit 必须抛 —— 静默回落会让 divisor 变 1、金额放大 1 万倍。"""
    with pytest.raises((ValueError, TypeError)):
        build_policy_snapshot(project_id=uuid.uuid4(), unit=bad_unit)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. `resolve_policy_snapshot_for_project`（生产入口）
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_resolver_uses_project_unit():
    pid = uuid.uuid4()
    db = _FakeDb(("wan",))
    snapshot = await resolve_policy_snapshot_for_project(db, project_id=pid)
    payload = json.loads(snapshot)
    assert payload["unit"] == "wan"
    assert payload["divisor"] == 10000
    assert "_fallback" not in payload


@pytest.mark.anyio
async def test_resolver_marks_fallback_when_row_missing():
    """项目不存在 / 无 amount_unit ⇒ 必须标 fallback，不得静默当正常 yuan。"""
    db = _FakeDb(None)
    snapshot = await resolve_policy_snapshot_for_project(db, project_id=uuid.uuid4())
    payload = json.loads(snapshot)
    assert payload["unit"] == "yuan"
    assert payload["_fallback"] is True


@pytest.mark.anyio
async def test_resolver_marks_fallback_on_db_error():
    """DB 异常必须降级 + 标 fallback，不得抛出把导出整个打断。"""
    snapshot = await resolve_policy_snapshot_for_project(
        _BoomDb(), project_id=uuid.uuid4()
    )
    payload = json.loads(snapshot)
    assert payload["_fallback"] is True


@pytest.mark.anyio
async def test_resolver_marks_fallback_for_unknown_stored_unit():
    """库里存了非法值（历史脏数据）也必须标 fallback，不得静默当合法。"""
    db = _FakeDb(("万元",))
    snapshot = await resolve_policy_snapshot_for_project(db, project_id=uuid.uuid4())
    payload = json.loads(snapshot)
    assert payload["unit"] == "yuan"
    assert payload["_fallback"] is True


@pytest.mark.anyio
async def test_resolver_queries_by_project_id_param():
    """绑定参数必须是 project_id（写成常量会让所有项目拿到同一单位）。"""
    pid = uuid.uuid4()
    db = _FakeDb(("wan",))
    await resolve_policy_snapshot_for_project(db, project_id=pid)
    assert db.calls, "resolver 未发起任何查询"
    _, params = db.calls[0]
    assert params.get("pid") == str(pid)


@pytest.mark.anyio
async def test_resolver_is_idempotent():
    pid = uuid.uuid4()
    first = await resolve_policy_snapshot_for_project(_FakeDb(("qian",)), project_id=pid)
    second = await resolve_policy_snapshot_for_project(
        _FakeDb(("qian",)), project_id=pid
    )
    assert first == second


# ---------------------------------------------------------------------------
# 6. 端到端：`create_export_task` 真的把快照写进 ORM
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_export_task_persists_snapshot():
    """生产写入方守卫：`create_export_task` 必须把快照落进 ORM 字段。

    🔴 只测 `build_policy_snapshot` 会漏掉「构造了但没传进去」——
    这正是本轮变异 B5 的形态（只折算不标注）。
    """
    import sqlalchemy as sa

    from app.models.report_models import ExportTask, ExportTaskType
    from app.services.pdf_export_engine import PDFExportEngine

    class _Db:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            return None

        async def execute(self, stmt):  # pragma: no cover - 本用例不查
            return None

    pid = uuid.uuid4()
    snapshot = build_policy_snapshot(project_id=pid, unit="wan")
    db = _Db()
    task = await PDFExportEngine(db).create_export_task(  # type: ignore[arg-type]
        project_id=pid,
        task_type=ExportTaskType.single_document,
        document_type="audit_report",
        unit_policy_snapshot=snapshot,
        export_year=2025,
        document_types=["audit_report", "financial_report"],
    )
    assert isinstance(task, ExportTask)
    assert task.unit_policy_snapshot == json.loads(snapshot)
    assert task.export_year == 2025
    assert task.document_types == ["audit_report", "financial_report"]


@pytest.mark.anyio
async def test_create_export_task_defaults_new_fields_to_safe_json_values():
    """旧调用方也必须满足 V265：数组字段不能写 JSON null。"""
    from app.models.report_models import ExportTaskType
    from app.services.pdf_export_engine import PDFExportEngine

    class _Db:
        def add(self, obj):
            return None

        async def flush(self):
            return None

    task = await PDFExportEngine(_Db()).create_export_task(  # type: ignore[arg-type]
        project_id=uuid.uuid4(), task_type=ExportTaskType.single_document
    )
    assert task.export_year is None
    assert task.document_types == []
    assert task.unit_policy_snapshot is None


@pytest.mark.anyio
async def test_create_export_task_legacy_single_type_is_normalized():
    """旧单数调用必须落成单元素 document_types 数组。"""
    from app.models.report_models import ExportTaskType
    from app.services.pdf_export_engine import PDFExportEngine

    class _Db:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            return None

    task = await PDFExportEngine(_Db()).create_export_task(  # type: ignore[arg-type]
        project_id=uuid.uuid4(),
        task_type=ExportTaskType.single_document,
        document_type="financial_report",
        unit_policy_snapshot=json.dumps({"_digest": "a" * 64, "unit": "yuan", "divisor": 1}),
    )
    assert task.document_types == ["financial_report"]
    assert task.unit_policy_snapshot == {
        "_digest": "a" * 64,
        "unit": "yuan",
        "divisor": 1,
    }


@pytest.mark.anyio
async def test_create_export_task_rejects_conflicting_single_and_plural_types():
    """单数与复数不一致时拒绝，不能静默选择错误的文档类型。"""
    from app.models.report_models import ExportTaskType
    from app.services.pdf_export_engine import PDFExportEngine

    class _Db:
        def add(self, obj):
            raise AssertionError("冲突输入不应写库")

        async def flush(self):
            raise AssertionError("冲突输入不应 flush")

    with pytest.raises(ValueError, match="document_type"):
        await PDFExportEngine(_Db()).create_export_task(  # type: ignore[arg-type]
            project_id=uuid.uuid4(),
            task_type=ExportTaskType.single_document,
            document_type="financial_report",
            document_types=["audit_report"],
        )


def test_router_passes_snapshot_to_engine():
    """路由必须真的把快照传下去（AST 级，禁靠运行时才暴露）。

    🔴 路径必须基于 `__file__` 而不是 cwd 相对路径：原先写
    `Path("app/routers/export.py")` 只有 cwd == `backend/` 时才成立，
    在仓库根（CI、`pytest backend/tests/...`）跑就 `FileNotFoundError` ——
    属「测试依赖执行目录」的脆弱写法，不是产品缺陷。
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "app/routers/export.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "create_export_task":
                kwargs = {kw.arg for kw in node.keywords}
                if {"unit_policy_snapshot", "document_types", "export_year"} <= kwargs:
                    found = True
    assert found, "router 的 create_export_task 调用未传 policy/document_types/export_year"
