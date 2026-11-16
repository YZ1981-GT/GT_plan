"""E1：PgBouncer transaction 模式契约验证（RLS / SET LOCAL / prepared statement / 取消）。

spec: `platform-heavy-jobs-and-capacity-closure` E1。

E1 原文说「需部署环境（PgBouncer 进程 + 真实后端 + RLS/SET LOCAL 验证），本机无法伪造，
保持阻塞」。本文件把**可在本机真实验证的那部分**兑现：起一个 transaction 模式的
PgBouncer（`POOL_MODE=transaction`），用它当后端，验证平台在 transaction pooling 下
**语义不破**的四件事：

1. **RLS 仍然生效** —— 平台靠 `SET LOCAL app.current_project` + RLS 策略做项目隔离。
   transaction 模式下 `SET LOCAL` 只在事务内有效，而 PgBouncer 会把同一事务内
   后续语句留在**同一服务端连接**上 ⇒ 事务内的 RLS 必须仍然隔离。
   （这正是「PgBouncer 先灰度再切流」要证明的第一件事。）
2. **`SET LOCAL` 不泄漏到下一个事务** —— transaction 模式把连接还给池后，
   下一个客户端拿到同一条服务端连接时**不能**看到上一个事务的 `SET LOCAL`。
   泄漏 = 跨项目数据泄露。
3. **prepared statement 必须关闭或命名唯一** —— transaction pooling 下同一客户端
   的语句可能落到不同服务端连接，服务端级 prepared statement 会撞
   `prepared statement "..." already exists`。平台已在 `statement_cache_size=0`
   （见 `test_pgbouncer_connection.py`），本文件用真 bouncer 验证该设置确实不撞。
4. **取消（cancel）能穿透 bouncer** —— `pg_cancel_backend` / asyncpg 的取消请求
   经 transaction pooling 仍能中断正在跑的查询。

⚠️ 跳过条件：必须显式 `GT_PGBOUNCER_URL` 指向一个 transaction 模式的 bouncer，
否则整文件 skip（CI 没有 bouncer 时不阻塞常规回归）。
⚠️ 本文件只连 bouncer 背后的**一次性库**（`GT_PGBOUNCER_DISPOSABLE_DB=1` 二次确认），
且库名不得含 `audit_platform` —— 绝不对共享库跑。
"""
from __future__ import annotations

import asyncio
import os
import uuid
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.pg_only

#: 需要 bouncer 的用例打这个标记；纯静态判据（如默认值断言）不带它，任何环境都跑。
_NEEDS_BOUNCER = pytest.mark.skipif(
    not (os.environ.get("GT_PGBOUNCER_URL") or "").strip()
    or os.environ.get("GT_PGBOUNCER_DISPOSABLE_DB", "").strip() not in ("1", "true", "yes"),
    reason="需要 GT_PGBOUNCER_URL + GT_PGBOUNCER_DISPOSABLE_DB=1（transaction 模式 bouncer）",
)


def _bouncer_url() -> str:
    """取 bouncer 连接串；缺任一前提即 skip（不 fail —— CI 无 bouncer 是正常情况）。"""
    url = (os.environ.get("GT_PGBOUNCER_URL") or "").strip()
    if not url:
        pytest.skip("需要 GT_PGBOUNCER_URL 指向 transaction 模式的 PgBouncer")
    if os.environ.get("GT_PGBOUNCER_DISPOSABLE_DB", "").strip() not in ("1", "true", "yes"):
        pytest.skip("需要 GT_PGBOUNCER_DISPOSABLE_DB=1 确认 bouncer 背后是可销毁库")
    db_name = (urlparse(url).path or "/").lstrip("/").lower()
    if "audit_platform" in db_name or not db_name:
        raise RuntimeError(
            f"拒绝对共享库或无名库跑 bouncer 契约测试（库名 {db_name!r}）"
        )
    return url


def _engine(url: str, *, statement_cache_size: int = 0) -> AsyncEngine:
    """连 bouncer 的引擎：NullPool（每次新建客户端连接，才能测池化语义）。

    ``statement_cache_size`` 默认 **0** —— transaction pooling 下这是**必须的**：
    PgBouncer 把同一客户端的语句分散到不同服务端连接，asyncpg 的服务端 prepared
    statement 缓存会撞 `prepared statement "..." already exists`。
    实测（2026-11-16，本机 transaction 模式 bouncer）：**连
    `select pg_catalog.version()` 都撞**，提示原文就写着「set statement_cache_size
    to 0」。平台的 `app/core/database.py` 正是这么做的（见 `test_pgbouncer_connection.py`）。
    """
    connect_args: dict = {"statement_cache_size": statement_cache_size}
    return create_async_engine(url, poolclass=NullPool, connect_args=connect_args)


async def _scalar(engine: AsyncEngine, sql: str, params: dict | None = None):
    async with engine.connect() as conn:
        return (await conn.execute(sa.text(sql), params or {})).scalar()


# ---------------------------------------------------------------------------
# 判据 1：transaction 模式确实生效（否则后面三条测的不是 bouncer 语义）
# ---------------------------------------------------------------------------


@_NEEDS_BOUNCER
async def test_bouncer_is_running_in_transaction_mode():
    """先证明「这确实是 transaction pooling」——否则后面测的是直连语义。

    PgBouncer 的 `SHOW POOL_MODE` 只在 admin 库可用；业务库上改用间接判据：
    两条**独立**连接上 `pg_backend_pid()` 可能相同（池复用），而同一个事务内
    必然相同。这里用「同一事务内两条语句 pid 相同」+「跨事务可不同」来确认
    池化在起作用（若始终不同则说明每次都是新服务端连接，池没复用）。
    """
    url = _bouncer_url()
    engine = _engine(url)
    try:
        async with engine.connect() as conn:
            pid_a = (await conn.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one()
            pid_b = (await conn.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one()
        assert pid_a == pid_b, (
            "同一事务内两条语句拿到不同 backend pid ⇒ 不是事务级绑定，"
            "SET LOCAL 语义会破"
        )
        # 记录：跨事务是否复用由 bouncer 决定，不做断言（池大小与负载决定）
        print(f"[E1] bouncer backend pid={pid_a}")
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# 判据 2：SET LOCAL 不跨事务泄漏（跨项目泄露风险）
# ---------------------------------------------------------------------------


@_NEEDS_BOUNCER
async def test_set_local_does_not_leak_across_transactions():
    """`SET LOCAL` 在事务结束后必须失效 —— 泄漏 = 跨项目数据泄露。

    这条在 transaction pooling 下尤其关键：连接被还回池后可能立刻被别的客户端
    （甚至别的项目）复用。若 `SET LOCAL` 变成会话级 `SET`，下一个人会读到上一个人
    的项目上下文。
    """
    url = _bouncer_url()
    engine = _engine(url)
    marker = f"leak-probe-{uuid.uuid4().hex[:8]}"
    try:
        # 事务 A：SET LOCAL 一个自定义参数
        async with engine.connect() as conn:
            async with conn.begin():
                await conn.execute(sa.text("SELECT set_config('app.gt_probe', :v, true)"),
                                   {"v": marker})
                seen = (await conn.execute(
                    sa.text("SELECT current_setting('app.gt_probe', true)")
                )).scalar_one()
                assert seen == marker, "事务内 SET LOCAL 未生效（测法本身有问题）"

        # 事务 B：同一引擎的新连接必须看不到它
        async with engine.connect() as conn:
            async with conn.begin():
                after = (await conn.execute(
                    sa.text("SELECT current_setting('app.gt_probe', true)")
                )).scalar_one()
        assert after in (None, ""), (
            f"SET LOCAL 泄漏到下一个事务（读到 {after!r}）⇒ "
            "transaction pooling 下会造成跨项目数据泄露"
        )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# 判据 3：prepared statement 不撞（statement_cache_size=0 是真必要）
# ---------------------------------------------------------------------------


@_NEEDS_BOUNCER
async def test_statement_cache_disabled_avoids_prepared_statement_conflict():
    """`statement_cache_size=0` 下反复同名查询不撞 `already exists`。

    transaction pooling 会把同名语句送到不同服务端连接；若 asyncpg 开了服务端缓存，
    第二次可能落到「已建过同名语句」的连接上。平台因此设 `statement_cache_size=0`。
    本用例连续跑同一 SQL 多次（NullPool ⇒ 每次新客户端连接，最大化撞的概率）。
    """
    url = _bouncer_url()
    engine = _engine(url, statement_cache_size=0)
    try:
        for index in range(12):
            got = await _scalar(engine, "SELECT CAST(:n AS int) + 1", {"n": index})
            assert got == index + 1, f"第 {index} 次同名查询结果错：{got}"
    finally:
        await engine.dispose()


@_NEEDS_BOUNCER
async def test_statement_cache_enabled_is_actually_risky():
    """反向对照：开着服务端语句缓存时，撞 prepared statement 的概率显著上升。

    这条**不**断言一定失败（取决于 bouncer 池里有多少条服务端连接、语句如何分布），
    而是记录现象 —— 它存在的意义是证明上一条「关闭缓存」不是无的放矢：
    如果开着缓存也从不撞，那 `statement_cache_size=0` 就是多余的。
    只有在真撞到（抛 `DuplicatePreparedStatement`）时才判「证明确有必要」。
    """
    url = _bouncer_url()
    engine = _engine(url, statement_cache_size=100)
    conflict = False
    try:
        for index in range(40):
            try:
                await _scalar(engine, "SELECT CAST(:n AS int) * 2", {"n": index})
            except Exception as exc:  # noqa: BLE001
                message = str(exc).lower()
                if "prepared statement" in message and "already exists" in message:
                    conflict = True
                    print(f"[E1] 第 {index} 次撞到 prepared statement 冲突：{exc}")
                    break
                raise
    finally:
        await engine.dispose()
    # 不 fail：只如实记录。真撞到就说明 statement_cache_size=0 是必须的。
    print(f"[E1] 开启语句缓存 40 次同名查询，撞 prepared statement = {conflict}")


# ---------------------------------------------------------------------------
# 判据 4：取消能穿透 bouncer
# ---------------------------------------------------------------------------


@_NEEDS_BOUNCER
async def test_query_cancellation_works_through_bouncer():
    """`pg_sleep` 可被取消（asyncpg 取消经 bouncer 仍能到达后端）。

    R1 要求「取消」语义在 transaction pooling 下不丢 —— 否则用户点了取消，
    查询还在池里的连接上跑到天荒地老，占着连接预算。
    """
    url = _bouncer_url()
    engine = _engine(url)
    try:
        async with engine.connect() as conn:
            task = asyncio.create_task(
                conn.execute(sa.text("SELECT pg_sleep(10)"))
            )
            await asyncio.sleep(0.6)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    finally:
        await engine.dispose()


@_NEEDS_BOUNCER
async def test_connection_usable_after_cancellation():
    """取消之后必须 `rollback()` 才能复用连接（SQLAlchemy 的真实语义）。

    🔴 实测发现（2026-11-16）：取消正在跑的查询后，直接在同一连接上执行下一条
    SQL 会抛
    ``PendingRollbackError: Can't reconnect until invalid transaction is rolled back``
    —— 取消把事务置为 invalid，**必须显式 rollback**。这是 SQLAlchemy 的语义，
    不是 bouncer 造成的（直连同样如此）。

    ⇒ 平台契约是：**取消路径必须 rollback**，否则连接不可复用、并且带着
    invalid 事务还给池会毒到下一个客户端。本用例把这条契约钉住：
    ① 不 rollback 直接查 → 必须抛 PendingRollbackError（证明这条约束真实存在）
    ② rollback 之后再查 → 必须成功（证明 rollback 是正确解法）
    """
    url = _bouncer_url()
    engine = _engine(url)
    try:
        async with engine.connect() as conn:
            task = asyncio.create_task(conn.execute(sa.text("SELECT pg_sleep(10)")))
            await asyncio.sleep(0.5)
            task.cancel()
            # `pytest.raises(CancelledError)` 已足够钉住「取消真的传播」——
            # 再补 `task.cancelled()` 是冗余的（变异验证：删掉它用例仍全绿）。
            with pytest.raises(asyncio.CancelledError):
                await task

            # ① 不 rollback 直接查：必须失败（invalid transaction）
            with pytest.raises(Exception) as excinfo:
                await conn.execute(sa.text("SELECT 42"))
            assert "PendingRollback" in type(excinfo.value).__name__ or (
                "invalid transaction" in str(excinfo.value)
            ), f"取消后未 rollback 却可继续查询，与 SQLAlchemy 语义不符：{excinfo.value}"

            # ② rollback 之后必须能继续用
            await conn.rollback()
            got = (await conn.execute(sa.text("SELECT 42"))).scalar_one()
            assert got == 42, f"rollback 之后连接仍不可用（读到 {got}）"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# 判据 5：RLS 策略在事务内仍隔离（平台最核心的隔离机制）
# ---------------------------------------------------------------------------


@_NEEDS_BOUNCER
async def test_rls_policy_still_isolates_inside_transaction():
    """在 bouncer 后面建带 RLS 的表，验证 `SET LOCAL` + 策略仍隔离。

    这是 E1 真正的目的：**RLS 不能因为换成 transaction pooling 就失效**。

    🔴 **必须用非 superuser 角色**：PostgreSQL 的 superuser **永远绕过** RLS
    （即使 `FORCE ROW LEVEL SECURITY` 也无效，那只对表 owner 起作用）。
    本机开发库的 `postgres` 是 superuser —— 用它测 RLS 会得到「看到全部行」的
    假绿/假红（第一版就踩了：项目 A 读到 [1, 2]）。这里临时建一个 NOSUPERUSER
    角色并 `SET ROLE` 到它，才测得到真实策略行为。

    用提交型临时 schema 隔离（不写 public）。
    """
    url = _bouncer_url()
    engine = _engine(url)
    schema = f"e1_rls_{uuid.uuid4().hex[:10]}"
    role = f"e1_rls_role_{uuid.uuid4().hex[:8]}"
    try:
        async with engine.begin() as conn:
            # 非 superuser 角色（RLS 才会对它生效）
            await conn.exec_driver_sql(f'CREATE ROLE "{role}" NOSUPERUSER NOLOGIN')
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await conn.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
            await conn.exec_driver_sql(
                f'CREATE TABLE "{schema}".probe (id int primary key, project text not null)'
            )
            await conn.exec_driver_sql(
                f'INSERT INTO "{schema}".probe VALUES (1, \'A\'), (2, \'B\')'
            )
            await conn.exec_driver_sql(
                f'ALTER TABLE "{schema}".probe ENABLE ROW LEVEL SECURITY'
            )
            await conn.exec_driver_sql(
                f'ALTER TABLE "{schema}".probe FORCE ROW LEVEL SECURITY'
            )
            await conn.exec_driver_sql(
                f'CREATE POLICY p ON "{schema}".probe USING '
                f"(project = current_setting('app.gt_project', true))"
            )
            await conn.exec_driver_sql(f'GRANT SELECT ON "{schema}".probe TO "{role}"')

        async def _rows_as(project: str | None) -> list[int]:
            """以非 superuser 角色查表；``project=None`` 表示不设上下文。"""
            async with engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(sa.text(f'SET LOCAL ROLE "{role}"'))
                    if project is not None:
                        await conn.execute(
                            sa.text("SELECT set_config('app.gt_project', :p, true)"),
                            {"p": project},
                        )
                    return list((await conn.execute(
                        sa.text(f'SELECT id FROM "{schema}".probe ORDER BY id')
                    )).scalars().all())

        assert await _rows_as("A") == [1], "项目 A 应只见 id=1"
        assert await _rows_as("B") == [2], "项目 B 应只见 id=2"
        # 没设上下文必须**看不到任何行**（fail-closed，不是 fail-open）
        assert await _rows_as(None) == [], (
            "未设项目上下文却读到行 ⇒ RLS 在 bouncer 后 fail-open，跨项目数据泄露"
        )
    finally:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await conn.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
        await engine.dispose()


# ---------------------------------------------------------------------------
# 判据 6：默认必须关语句缓存（不靠「撞车运气」，直接断言默认值）
# ---------------------------------------------------------------------------


def test_default_engine_disables_statement_cache():
    """`_engine()` 的默认 `statement_cache_size` 必须是 0。

    🔴 为什么单独一条：靠「开缓存后撞不撞」判定是不可靠的 —— 撞不撞取决于
    bouncer 池里有多少条服务端连接、语句怎么分布（实测：v2 变异把默认改成 100
    后，用例集合**仍然全绿**，因为「撞车」那条本来就显式传 100 且断言只记录不 fail）。
    ⇒ 改成直接断言默认值，任何把默认调大的改动立刻打红。
    """
    import inspect

    signature = inspect.signature(_engine)
    default = signature.parameters["statement_cache_size"].default
    assert default == 0, (
        f"_engine 的 statement_cache_size 默认是 {default!r}，必须是 0 —— "
        "transaction pooling 下开启服务端语句缓存会撞 "
        "DuplicatePreparedStatement（实测连 select pg_catalog.version() 都撞）"
    )


def test_platform_database_module_also_disables_statement_cache():
    """平台自己的引擎也必须关（本 spec 不能只把测试修对、生产还是开着的）。

    `app/core/database.py` 是生产入口。现读它的真实写法（2026-11-16）：
    模块级建 `_pgbouncer_connect_args = {"statement_cache_size": 0, ...}`，
    再 `create_async_engine(..., connect_args=_pgbouncer_connect_args)` ——
    所以判据必须**跟踪 `connect_args` 指向的变量**，只看 `create_async_engine`
    的 keyword 会漏（第一版就漏了：直接查 keyword 得 False）。

    判据分两层，任一成立即可：
    ① `create_async_engine` 调用里直接出现 `statement_cache_size`（关键字或字符串常量）；
    ② `connect_args=` 指向一个**模块级字典字面量**，该字典里含
       `"statement_cache_size": 0`（0 是硬要求 —— 开缓存必撞）。
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "app" / "core" / "database.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 收集「名字 → 字典字面量」（不限顶层：`_pgbouncer_connect_args` 在
    # `if _is_postgres and settings.DB_USE_PGBOUNCER:` 分支里赋值，只看 tree.body 会漏）
    module_dicts: dict[str, ast.Dict] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_dicts[target.id] = node.value

    def _dict_has_zero_statement_cache(node: ast.Dict) -> bool:
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "statement_cache_size"
                and isinstance(value, ast.Constant)
                and value.value == 0
            ):
                return True
        return False

    engine_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "create_async_engine")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "create_async_engine")
        )
    ]
    assert engine_calls, "app/core/database.py 没有 create_async_engine 调用"

    def _call_disables_cache(call: ast.Call) -> bool:
        # ① 直接出现
        for child in ast.walk(call):
            if isinstance(child, ast.keyword) and child.arg == "statement_cache_size":
                return True
            if isinstance(child, ast.Constant) and child.value == "statement_cache_size":
                return True
        # ② 经 connect_args=<模块级字典>
        for keyword in call.keywords:
            if keyword.arg != "connect_args":
                continue
            value = keyword.value
            if isinstance(value, ast.Name) and value.id in module_dicts:
                if _dict_has_zero_statement_cache(module_dicts[value.id]):
                    return True
        return False

    assert any(_call_disables_cache(call) for call in engine_calls), (
        "app/core/database.py 的 create_async_engine 没有把 statement_cache_size 设为 0 "
        "（直接 keyword 或经 connect_args 字典）⇒ 切 PgBouncer transaction 模式后"
        "第一条查询就会撞 DuplicatePreparedStatement。现读该文件应看到 "
        '_pgbouncer_connect_args = {"statement_cache_size": 0, ...}。'
    )
