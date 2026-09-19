"""OO 编辑留痕正确性 — deliverable-lineage-wiring-and-writeback-closure Wave 2

覆盖 Property 13/14/15：
- Property 13：OO 编辑新版本的 `source_snapshot_refs` 与上一版逐字相等；
  且 `task.source_snapshot_refs` 不被覆盖 ⇒ tb_hash 变化后仍判 stale
- Property 14：编辑人如实记录（可识别 / 不可识别 / 非本项目三态），
  **任何情况下不得等于 task.created_by**
- Property 15：doc_key 确定性派生（不含时间戳）且与席位 key 同源

反向自检：
- 复现旧行为（回调重新 capture_snapshot_refs）则 stale 被洗白 → 必须打红
- 复现旧行为（doc_key 带时间戳）则两次调用不等 → 必须打红
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.services.deliverable_doc_key import (
    deliverable_doc_key,
    parse_deliverable_doc_key,
)
from app.services.deliverable_service import DeliverableService
from app.services.onlyoffice_editor_identity import (
    extract_editor_ids,
    resolve_editor_id,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


# ─── Property 15: doc_key 确定性且与席位同源 ────────────────────────────────


@given(
    task_id=st.uuids(),
    version_no=st.integers(min_value=1, max_value=999),
)
@hyp_settings(max_examples=5, deadline=None)
def test_property_15_doc_key_is_deterministic(task_id, version_no):
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 15
    a = deliverable_doc_key(task_id, version_no)
    b = deliverable_doc_key(task_id, version_no)
    assert a == b, "doc_key 必须确定性派生"
    # round-trip：解析回 (UUID, int)。返回 UUID 而非 str 是有意的 ——
    # 调用方拿它直接查库，返回 str 会让每个调用方各自 UUID(...) 一次。
    assert parse_deliverable_doc_key(a) == (task_id, version_no)


def test_doc_key_has_no_timestamp():
    """反向自检：doc_key 不得含时间戳。

    历史实现 `f"{task.id}_{version_no}_{int(time.time())}"` 使每次请求 config 都成为
    「新文档」→ 两人同开进入两个独立 OO 会话，后 forcesave 者静默覆盖前者。
    """
    tid = uuid.uuid4()
    k1 = deliverable_doc_key(tid, 1)
    import time as _t

    _t.sleep(0.01)
    k2 = deliverable_doc_key(tid, 1)
    assert k1 == k2

    legacy = f"{tid}_1_{int(_t.time())}"
    assert k1 != legacy, "doc_key 退化为含时间戳形态"


def _strip_py_comments(src: str) -> str:
    """剥掉 `#` 行注释与三引号 docstring。

    🔴 memory 铁律：读源码型守卫必须先 stripComments —— 否则「说明注释里写出的反例」
    会被数成真实代码。本守卫首版即因此假红：`build_editor_config` 的注释里写了
    「历史实现带 int(time.time())」，扫描把它当成"仍含时间戳"。
    """
    out: list[str] = []
    i, n = 0, len(src)
    in_str: str | None = None
    while i < n:
        if in_str:
            if src.startswith(in_str, i):
                i += len(in_str)
                in_str = None
            else:
                i += 1
            continue
        if src.startswith('"""', i) or src.startswith("'''", i):
            in_str = src[i : i + 3]
            i += 3
            continue
        ch = src[i]
        if ch == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def test_strip_comments_selfcheck():
    """反向自检：剥注释函数确实生效（否则上面的断言全是空转）。"""
    sample = 'a = 1  # int(time.time())\n"""doc int(time.time())"""\nb = 2\n'
    stripped = _strip_py_comments(sample)
    assert "int(time.time())" not in stripped
    assert "a = 1" in stripped and "b = 2" in stripped
    # 原文里确实有该字样 ⇒ 证明剥离不是因为样本本来就没有
    assert sample.count("int(time.time())") == 2


def test_doc_key_source_is_single_and_used_by_all_three_sites():
    """三处（config 生成 / 席位占用 / 席位释放）必须走同一函数（需求 7.5）。

    判据：源码级（**剥注释后**）—— 三处均引用 `deliverable_doc_key`，且不再出现
    字面量拼接 `f"deliverable-{task_id}-{version_no}"` / `int(time.time())`。
    """
    root = Path(__file__).resolve().parents[1] / "app"
    oo_src = _strip_py_comments(
        (root / "services" / "onlyoffice_callback_service.py").read_text(
            encoding="utf-8"
        )
    )
    router_src = _strip_py_comments(
        (root / "routers" / "deliverable.py").read_text(encoding="utf-8")
    )

    assert "deliverable_doc_key" in oo_src, "build_editor_config 未走 doc_key 真源"
    assert "int(time.time())" not in oo_src, "doc_key 仍含时间戳"

    assert "deliverable_doc_key" in router_src, "席位占用未走 doc_key 真源"
    assert 'f"deliverable-{task_id}-{version_no}"' not in router_src, (
        "路由仍在字面量拼接 doc_key（与真源分叉，改一处另一处不红）"
    )
    # 释放侧改走按 doc_key 释放（回调无鉴权用户上下文）
    assert "release_sessions_by_doc_key" in router_src


def test_release_by_doc_key_exists_and_legacy_creator_approx_removed():
    """反向自检：释放侧不得再用 `task.created_by` 近似占位人。

    历史实现 `release_session(creator_id, doc_key)` 与占用侧 `current_user.id`
    两把 key 不匹配 ⇒ 席位从未真正释放（靠 1h TTL 自愈，期间虚占名额）。
    """
    root = Path(__file__).resolve().parents[1] / "app"
    limiter_src = (root / "services" / "onlyoffice_session_limiter.py").read_text(
        encoding="utf-8"
    )
    router_src = (root / "routers" / "deliverable.py").read_text(encoding="utf-8")

    assert "async def release_sessions_by_doc_key" in limiter_src
    assert "release_session(creator_id" not in router_src, (
        "释放仍用 creator 近似 ⇒ 与占用 key 不匹配"
    )


# ─── Property 14: 编辑人如实记录 ────────────────────────────────────────────


def test_property_14_identifiable_editor_is_extracted():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 14
    uid = uuid.uuid4()
    assert resolve_editor_id({"users": [str(uid)]}) == uid
    assert resolve_editor_id({"actions": [{"type": 2, "userid": str(uid)}]}) == uid
    assert (
        resolve_editor_id({"history": {"changes": [{"user": {"id": str(uid)}}]}}) == uid
    )


def test_property_14_unidentifiable_editor_is_none_not_creator():
    """不可识别 ⇒ None（未知），**绝不**回退 created_by。"""
    creator = uuid.uuid4()
    for body in (
        {},
        {"users": []},
        {"users": ["anonymous"]},
        {"actions": [{"type": 1}]},
        {"history": {"changes": [{}]}},
        {"users": [None]},
    ):
        got = resolve_editor_id(body)
        assert got is None, f"{body} 应解析为未知，实得 {got}"
        assert got != creator


def test_extract_editor_ids_dedupes_and_keeps_order():
    a, b = uuid.uuid4(), uuid.uuid4()
    body = {
        "users": [str(a), str(a)],
        "actions": [{"userid": str(b)}, {"userid": str(a)}],
    }
    assert extract_editor_ids(body) == [a, b]


def test_extract_editor_ids_tolerates_malformed_body():
    for bad in (None, [], "x", 42, {"users": "notalist"}):
        try:
            out = extract_editor_ids(bad)  # type: ignore[arg-type]
        except TypeError:
            # users 为字符串时逐字符迭代亦不得抛，若抛说明健壮性不足
            pytest.fail(f"extract_editor_ids 对 {bad!r} 抛异常")
        assert out == [] or all(isinstance(x, uuid.UUID) for x in out)


def test_callback_never_falls_back_to_created_by_source_level():
    """源码级反向自检：`_resolve_verified_editor` 不得返回 created_by。

    「伪装成创建人」比留空更坏 —— 留空能看出留痕缺失，伪装让错误信息
    看起来是可信的审计证据。
    """
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "onlyoffice_callback_service.py"
    ).read_text(encoding="utf-8")
    i = src.index("async def _resolve_verified_editor")
    j = src.index("\n    def ", i) if "\n    def " in src[i:] else len(src)
    body = src[i:j]
    # 允许注释中提到 created_by（解释为什么不用），但不得作为返回值
    code_lines = [
        ln for ln in body.splitlines() if not ln.strip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "return task.created_by" not in code
    assert "or task.created_by" not in code


# ─── Property 13: OO 编辑不改变快照绑定 ─────────────────────────────────────


async def _mk_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            WordExportTask.metadata.create_all,
            tables=[WordExportTask.__table__, WordExportTaskVersion.__table__],
        )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _run(factory_coro):
    async def _main():
        engine, factory = await _mk_engine()
        try:
            async with factory() as session:
                return await factory_coro(session)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


async def _seed_task_with_v1(session, refs: dict, tmp: Path):
    # 🔴 word_export_task **无 year 列**（年度在请求参数/版本快照里），传了会 TypeError
    task = WordExportTask(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        doc_type="disclosure_notes",
        status=WordExportStatus.generated.value,
        created_by=uuid.uuid4(),
        source_snapshot_refs=refs,
    )
    session.add(task)
    await session.flush()
    v1 = WordExportTaskVersion(
        id=uuid.uuid4(),
        word_export_task_id=task.id,
        version_no=1,
        file_path=str(tmp / "v1.docx"),
        created_by=task.created_by,
        source_snapshot_refs=refs,
        created_via="generate",
    )
    session.add(v1)
    await session.flush()
    return task


@pytest.mark.parametrize("editor_known", [True, False])
def test_property_13_oo_edit_inherits_snapshot_refs(tmp_path, editor_known):
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 13
    """OO 编辑版本继承上一版 refs，且不覆盖 task 级 refs。"""
    bound = {"tb_hash": "a" * 64, "captured_at": "2026-01-01T00:00:00Z"}
    editor = uuid.uuid4() if editor_known else None

    async def _scenario(session):
        task = await _seed_task_with_v1(session, bound, tmp_path)
        svc = DeliverableService(session)
        res = await svc.render_and_store(
            task.id,
            docx_bytes=b"PK-edited",
            user_id=task.created_by,
            created_via="onlyoffice_edit",
            inherit_snapshot_refs=True,
            edited_by=editor,
            edited_at=datetime.now(timezone.utc),
        )
        await session.refresh(task)
        return task, res.version

    import unittest.mock as mock

    from app.services.deliverable_hash_service import DeliverableHashService

    with mock.patch.object(
        DeliverableHashService, "bind_version_hash", new=_noop_async
    ):
        task, v2 = _run(_scenario)

    assert v2.created_via == "onlyoffice_edit"
    assert v2.source_snapshot_refs == bound, "OO 编辑版本未继承上一版快照引用"
    assert task.source_snapshot_refs == bound, (
        "task 级快照被 OO 编辑覆盖 ⇒ stale 被洗白（正是需求 7.1 要修的缺陷）"
    )
    assert v2.edited_by == editor
    if editor is None:
        assert v2.edited_by is None
    else:
        assert v2.edited_by != task.created_by or editor == task.created_by


async def _noop_async(self, *a, **kw):  # noqa: ANN001
    return None


def test_reverse_selfcheck_recapture_would_wash_out_stale(tmp_path):
    """反向自检：不传 inherit_snapshot_refs 且传入**当前**快照 ⇒ 绑定被改写。

    这正是历史实现的行为（`handle_callback` 重新 `capture_snapshot_refs`）：
    试算表改过、本该 stale 的交付件，只要在 OO 里改个错别字保存就重新绑到新
    tb_hash ⇒ `check_stale` / `check_trio_consistency` 双双转绿而内容其实过期。
    """
    old = {"tb_hash": "a" * 64}
    new = {"tb_hash": "b" * 64}

    async def _scenario(session):
        task = await _seed_task_with_v1(session, old, tmp_path)
        svc = DeliverableService(session)
        res = await svc.render_and_store(
            task.id,
            docx_bytes=b"PK-edited",
            user_id=task.created_by,
            source_snapshot_refs=new,  # 旧行为：重新捕获当前快照
            created_via="onlyoffice_edit",
        )
        await session.refresh(task)
        return task, res.version

    import unittest.mock as mock

    from app.services.deliverable_hash_service import DeliverableHashService

    with mock.patch.object(
        DeliverableHashService, "bind_version_hash", new=_noop_async
    ):
        task, v2 = _run(_scenario)

    assert v2.source_snapshot_refs == new
    assert task.source_snapshot_refs == new, (
        "旧行为本应改写绑定；若此处不成立说明反向自检失效（空转）"
    )


def test_callback_wires_inherit_and_editor(tmp_path):
    """源码级：`handle_callback` 必须传 inherit_snapshot_refs 且不再 capture。"""
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "onlyoffice_callback_service.py"
    ).read_text(encoding="utf-8")
    i = src.index("async def handle_callback")
    j = src.index("async def _resolve_verified_editor")
    body = src[i:j]
    assert "inherit_snapshot_refs=True" in body
    assert "edited_by=" in body
    assert "capture_snapshot_refs" not in body, (
        "回调仍在重新捕获当前快照 ⇒ stale 会被洗白"
    )


def test_version_orm_has_editor_columns():
    """V142 三层一致：ORM 侧两列存在且可空。"""
    cols = WordExportTaskVersion.__table__.columns
    assert "edited_by" in cols and cols["edited_by"].nullable is True
    assert "edited_at" in cols and cols["edited_at"].nullable is True


def test_v142_migration_is_idempotent_and_has_rollback():
    mig = Path(__file__).resolve().parents[1] / "migrations"
    v = mig / "V142__deliverable_version_editor_identity.sql"
    r = mig / "R142__deliverable_version_editor_identity.sql"
    assert v.exists() and r.exists()
    vs = v.read_text(encoding="utf-8")
    # 🔴 只数**非注释行** —— 迁移头部的说明注释里会写出「用 ADD COLUMN IF NOT EXISTS
    # 保证幂等」这句话，直接 count 整文件会把说明文字数成真实 DDL（本守卫首版即因此
    # 得到 3 而非 2）。与「读源码型守卫必须先 stripComments」是同一个坑。
    ddl = "\n".join(
        ln for ln in vs.splitlines() if not ln.lstrip().startswith("--")
    )
    assert "ADD COLUMN IF NOT EXISTS" in vs, "反向自检：文件里确实提到该写法"
    assert ddl.count("ADD COLUMN IF NOT EXISTS") == 2, (
        f"迁移必须对两列都用 ADD COLUMN IF NOT EXISTS（实际 {ddl.count('ADD COLUMN IF NOT EXISTS')} 处）"
    )
    assert "edited_by" in ddl and "edited_at" in ddl
    rs = r.read_text(encoding="utf-8")
    assert "DROP COLUMN IF EXISTS edited_by" in rs
    assert "DROP COLUMN IF EXISTS edited_at" in rs


def test_v142_number_not_reused():
    """迁移版本号永不复用：V142 只能有一个文件。"""
    mig = Path(__file__).resolve().parents[1] / "migrations"
    hits = sorted(p.name for p in mig.glob("V142__*.sql"))
    assert hits == ["V142__deliverable_version_editor_identity.sql"], hits
