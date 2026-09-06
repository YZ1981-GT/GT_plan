"""BP-26：projection lane 的目标底稿必须是**审计师真能打开**的那种。

═══ 这条判据为什么存在（2026-09-06 Playwright 实测）═════════════════════════════

`projection_target_resolution.resolve_projection_target` 的首版 `WHERE` 只有
`wp.is_deleted = false` —— 只看底稿自己删没删，不看它**所在项目**删没删。后果：

* H1 的全序第一名是 `f663b18c`（project `df5b8403`「首汽租车_2025」，
  `projects.is_deleted = true`），首版 published representation 已经发在它上面；
* 前端打开该底稿时 `GET /api/workpapers/{id}/render-config` 返回
  **404「项目已删除」** ⇒ 那条 representation 审计师永远看不到。

于是「DB 里 published representation 存在」与「双向回写在界面上可用」两个判据分别在
**两个异集**上为真。它比 BP-24 隐蔽：BP-24 是两个宿主选到**不同**底稿（一比就发现），
这一条是两个宿主选到**同一条**、只是那条对用户不可达，任何只查库的判据都恒绿。

为什么此前一路预演没撞上（这部分决定了判据必须怎么写）：

* `has_store_payload DESC` **偶然**替 D2 挡住了 —— D2 在活项目那条上有 490,291 B 载荷；
* H1 的 `H1-8-rows` 全库 0 行载荷 ⇒ 全序退化成 `wi.wp_code, wp.created_at, wp.id`，
  而**已删除的测试项目往往创建得最早** ⇒ 它稳定地排第一。

⇒ 行为判据必须构造成「不可见的那条按全序本该胜出」，否则用例对本机制不敏感
（可见的那条本来就会赢，删不删过滤都一样 —— 那是「在当前状态下与正确结果同值」
那类无效用例）。反向自检用旧口径复算，证明差异确实由新增过滤造成。

═══ 隔离 ═══════════════════════════════════════════════════════════════════════

真 PG + 独立 schema（`CREATE SCHEMA` / `DROP ... CASCADE`），只建本文件消费的四张
stub 表，不跑迁移。全部快照由**一次** `asyncio.run` 采集 —— 每个测试各自 async 会
污染共享连接池（第二个起报 `NoneType has no attribute send`）。

DB 非 PostgreSQL 时 `raise` 而不是 `skip`：skip 等于把「没验证」记成「通过」。
"""

from __future__ import annotations

import ast
import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

#: 生产真源。判据一律读它，不读宿主的转引（宿主只 re-export）。
RESOLUTION_PATH = _BACKEND / "app/services/workpaper_sync/projection_target_resolution.py"

#: 三个消费该解析的 Excel 侧宿主。可见性过滤只能有一份，宿主不得自留。
HOST_PATHS: tuple[Path, ...] = (
    _BACKEND / "scripts/fix/fix_projection_first_publication.py",
    _BACKEND / "scripts/fix/fix_task76_provision_projection_definitions.py",
    _BACKEND / "scripts/fix/fix_excel_instrumentation_upgrade_candidate.py",
)

_SCHEMA_PREFIX = "tmp_bp26_"

#: 只建被本文件消费的列。
_STUB_DDL = """
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    name VARCHAR(200) NOT NULL DEFAULT 'stub',
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE wp_index (
    id UUID PRIMARY KEY,
    wp_code VARCHAR(60) NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE working_paper (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_index_id UUID REFERENCES wp_index(id),
    content_revision BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE checklist_responses (
    id UUID PRIMARY KEY,
    wp_id UUID NOT NULL REFERENCES working_paper(id),
    item_id VARCHAR(120) NOT NULL,
    remark TEXT
);
"""

#: 旧口径 —— 反向自检用。只保留底稿自身那一层。
_OLD_VISIBILITY = "wp.is_deleted = false"

_CODE = "BP26"
_STORE_ITEM = "bp26-rows"


class _HarnessError(RuntimeError):
    """夹具自身失败。与「判据不成立」区分开，否则会把环境问题记成缺陷。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _strip_docstrings(source: str) -> str:
    """剥掉 docstring 后再做「某符号是否真被用到」的判断。

    本模块顶部那段长注释里逐字写着 `wp.is_deleted = false`（在讲首版为什么错），
    不剥的话「宿主不得自留可见性字面量」这类判据会在**说明文字**上恒红。
    """
    tree = ast.parse(source)
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
            and first.lineno is not None
            and first.end_lineno is not None
        ):
            spans.append((first.lineno, first.end_lineno))
    lines = source.splitlines()
    for start, end in spans:
        # 🔴 首行必须留一个**空串字面量**并保持原缩进，不能整段清空：类体 / 函数体
        #    只有 docstring 时，清空会让它变成空体 ⇒ `ast.parse` 报 IndentationError，
        #    于是所有依赖本函数的判据都在「解析失败」上打红（首版实测 5 条）。
        #    行数保持不变，报出的行号才与磁盘一致。
        raw = lines[start - 1]
        indent = raw[: len(raw) - len(raw.lstrip())]
        lines[start - 1] = f'{indent}""'
        for idx in range(start, min(end, len(lines))):
            lines[idx] = ""
    return "\n".join(lines)


def _function_node(source: str, name: str) -> ast.AST:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"源码里没有名为 {name} 的函数")


# ═══════════════════════════════════════════════════════════════════════════
# 真 PG 采集（一次 asyncio.run）
# ═══════════════════════════════════════════════════════════════════════════


async def _resolve_with(session: Any, *, visibility: str, order_sql: str) -> Any:
    """对照口径：与生产 SQL 同构，仅替换可见性子句。

    存在的理由是**反向自检**：只断言「新口径选中可见的那条」时，一个把可见性过滤
    整个删掉的实现也可能通过（若可见的那条本来就该赢）。必须同时证明旧口径会选中
    不可见的那条 —— 那才说明用例对本机制敏感。
    """
    import sqlalchemy as sa

    return (
        await session.execute(
            sa.text(
                "SELECT wp.id AS wp_id, wp.project_id, wi.wp_code, "
                "       COALESCE(wp.content_revision, 0) AS rev, "
                "       COALESCE(LENGTH(store.remark), 0) AS store_bytes "
                "FROM working_paper wp "
                "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                "JOIN projects p ON p.id = wp.project_id "
                "LEFT JOIN checklist_responses store "
                "       ON store.wp_id = wp.id AND store.item_id = :item_id "
                f"WHERE {visibility} AND wi.wp_code = ANY(:codes) "
                f"ORDER BY {order_sql} LIMIT 1"
            ),
            {"codes": [_CODE], "item_id": _STORE_ITEM},
        )
    ).first()


async def _seed(conn: Any, *, project_deleted: bool, wp_deleted: bool,
                index_deleted: bool, age_days: int) -> str:
    """种一条候选，返回 wp_id。`age_days` 越大 ⇒ `created_at` 越早 ⇒ 全序越靠前。"""
    import sqlalchemy as sa

    project = uuid.uuid4()
    wp_index = uuid.uuid4()
    wp = uuid.uuid4()
    await conn.execute(
        sa.text("INSERT INTO projects (id, is_deleted) VALUES (:p, :d)"),
        {"p": project, "d": project_deleted},
    )
    await conn.execute(
        sa.text("INSERT INTO wp_index (id, wp_code, is_deleted) VALUES (:i, :c, :d)"),
        {"i": wp_index, "c": _CODE, "d": index_deleted},
    )
    await conn.execute(
        sa.text(
            "INSERT INTO working_paper (id, project_id, wp_index_id, is_deleted, created_at)"
            " VALUES (:w, :p, :i, :d, :t)"
        ),
        {"w": wp, "p": project, "i": wp_index, "d": wp_deleted, "t": _now() - timedelta(days=age_days)},
    )
    return str(wp)


async def _collect() -> dict[str, Any]:  # noqa: PLR0915 - 一次采集覆盖全部阶段
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.workpaper_sync import projection_target_resolution as TR

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise _HarnessError(
            "BP-26 的判据是「真库上真的排除了不可见底稿」，必须真实 PostgreSQL；"
            f"当前 DATABASE_URL 为 {str(settings.DATABASE_URL).split('://')[0]}。"
            "此处**不 skip** —— skip 等于把「没验证」记成「通过」"
        )

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(
        str(settings.DATABASE_URL), poolclass=NullPool, connect_args=dict(ssl_off)
    )
    out: dict[str, Any] = {"schema": schema, "seeded": {}, "picks": {}}
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(
            str(settings.DATABASE_URL),
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            for stmt in [s.strip() for s in _STUB_DDL.strip().split(";") if s.strip()]:
                await conn.exec_driver_sql(stmt)

        # ── 构造：不可见的三条都比可见那条**更早**创建 ⇒ 按全序它们本该胜出 ──
        async with engine.begin() as conn:
            out["seeded"]["project_deleted"] = await _seed(
                conn, project_deleted=True, wp_deleted=False, index_deleted=False, age_days=30
            )
            out["seeded"]["index_deleted"] = await _seed(
                conn, project_deleted=False, wp_deleted=False, index_deleted=True, age_days=20
            )
            out["seeded"]["wp_deleted"] = await _seed(
                conn, project_deleted=False, wp_deleted=True, index_deleted=False, age_days=10
            )
            out["seeded"]["visible"] = await _seed(
                conn, project_deleted=False, wp_deleted=False, index_deleted=False, age_days=1
            )

        async with Session() as session:
            prod = await TR.resolve_projection_target(
                session, wp_codes=[_CODE], store_item_id=_STORE_ITEM
            )
            out["picks"]["production"] = str(prod.wp_id) if prod is not None else None
            new_ctl = await _resolve_with(
                session, visibility=TR.TARGET_VISIBILITY_SQL, order_sql=TR.TARGET_ORDER_SQL
            )
            out["picks"]["new_control"] = str(new_ctl.wp_id) if new_ctl is not None else None
            old_ctl = await _resolve_with(
                session, visibility=_OLD_VISIBILITY, order_sql=TR.TARGET_ORDER_SQL
            )
            out["picks"]["old_control"] = str(old_ctl.wp_id) if old_ctl is not None else None
            out["hidden_count"] = await TR.count_candidates_hidden_by_visibility(
                session, wp_codes=[_CODE]
            )

        # ── 只剩不可见候选时：必须无目标，且诊断文案要指向正确的解除动作 ──
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("DELETE FROM working_paper WHERE id = :w"),
                {"w": uuid.UUID(out["seeded"]["visible"])},
            )
        async with Session() as session:
            only_hidden = await TR.resolve_projection_target(
                session, wp_codes=[_CODE], store_item_id=_STORE_ITEM
            )
            out["picks"]["after_removing_visible"] = (
                str(only_hidden.wp_id) if only_hidden is not None else None
            )
            out["hidden_count_after"] = await TR.count_candidates_hidden_by_visibility(
                session, wp_codes=[_CODE]
            )
            host = _load_first_host()
            out["diagnosis_hidden"] = await host._no_target_diagnosis(
                session, wp_codes=[_CODE]
            )
            out["diagnosis_empty"] = await host._no_target_diagnosis(
                session, wp_codes=["BP26-NO-SUCH-CODE"]
            )
    finally:
        if engine is not None:
            await engine.dispose()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.dispose()
    return out


def _load_first_host() -> Any:
    import importlib.util

    path = HOST_PATHS[0]
    spec = importlib.util.spec_from_file_location("_bp26_first_host", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 🔴 含 @dataclass 的模块必须先进 sys.modules 再 exec，否则 dataclass 解析
    #    注解时找不到自己的模块。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# 结构判据（不需库）
# ═══════════════════════════════════════════════════════════════════════════


class TestVisibilityFilterIsOneDeclaredSource:
    """可见性过滤是**一处声明**，三层齐全，且真的被 SQL 消费。"""

    def test_the_constant_covers_all_three_layers(self) -> None:
        """三层各是一个**独立合取项**，按 ` AND ` 拆开精确比对。

        🔴 不能用子串判定：`"wp.is_deleted = false"` 本身就**包含**子串
        `"p.is_deleted = false"`（`wp` 里的那个 `p`）。首版写成
        `"p.is_deleted = false" in clause` 时，摘掉项目层的变异 M01 照样通过 ——
        变异检验当场把这条判据自己的缺陷打出来了。
        """
        from app.services.workpaper_sync import projection_target_resolution as TR

        clause = TR.TARGET_VISIBILITY_SQL
        parts = {part.strip() for part in clause.split(" AND ")}
        for layer in ("wp.is_deleted = false", "p.is_deleted = false", "wi.is_deleted = false"):
            assert layer in parts, (
                f"`TARGET_VISIBILITY_SQL` 缺合取项 {layer!r}；实测拆出 {sorted(parts)}\n"
                "三层缺一即有一类不可见底稿能被选中；漏 `p.is_deleted` 正是 BP-26 本身"
            )
        assert len(parts) == 3, (
            f"可见性子句拆出 {len(parts)} 个合取项（应恰 3）: {sorted(parts)} —— "
            "多出来的项会把过滤范围悄悄扩大到本判据没有覆盖的语义上"
        )

    def test_the_select_joins_projects_and_uses_the_constant(self) -> None:
        """SQL 必须 JOIN projects 并用常量拼 WHERE —— 写死字面量就等于抄第二份。"""
        stripped = _strip_docstrings(RESOLUTION_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "resolve_projection_target")
        text = ast.unparse(node)
        assert "JOIN projects p ON p.id = wp.project_id" in text, (
            "`resolve_projection_target` 没 JOIN projects —— `p.is_deleted` 无从求值"
        )
        assert "TARGET_VISIBILITY_SQL" in text, (
            "WHERE 没用 `TARGET_VISIBILITY_SQL` 常量 —— 可见性口径被写死了第二份"
        )

    def test_the_constant_is_interpolated_exactly_twice(self) -> None:
        """常量恰在**三处**被拼进 SQL，且三处各有确定用途：

        1. `resolve_projection_target` —— 发布期选目标底稿（BP-26）；
        2. `count_candidates_hidden_by_visibility` —— 诊断「有几条被排除」（同上，取反）；
        3. `resolve_visible_current_representation_id` —— **请求期**取 current
           representation（BP-27，生产请求路径 `wp_sync_router` 经 pilot 调它）。

        锁死条数的理由：多一处 = 又冒出第四条查询路径（BP-24 的形态，四份副本必漂移）；
        少一处 = 某条路径退回了自己的口径，于是「可见」的定义又变成两个。
        **加第四处用途时必须同时改这里的期望值并在上面补一行说明** —— 否则下一个人
        只会把数字改大，而不知道那一处是干什么的。
        """
        stripped = _strip_docstrings(RESOLUTION_PATH.read_text(encoding="utf-8"))
        hits: list[int] = []
        for node in ast.walk(ast.parse(stripped)):
            if not isinstance(node, ast.JoinedStr):
                continue
            for part in node.values:
                if (
                    isinstance(part, ast.FormattedValue)
                    and isinstance(part.value, ast.Name)
                    and part.value.id == "TARGET_VISIBILITY_SQL"
                ):
                    hits.append(node.lineno)
        assert len(hits) == 3, (
            f"`TARGET_VISIBILITY_SQL` 被拼进 SQL 的位置有 {len(hits)} 处（应恰 3 处："
            "发布期选目标 / 隐藏计数 / 请求期取 current representation）"
            f"，行号 {hits}"
        )

    def test_the_count_query_negates_the_same_clause(self) -> None:
        """隐藏计数必须是同一子句的**取反**，不得另写一套条件。"""
        stripped = _strip_docstrings(RESOLUTION_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "count_candidates_hidden_by_visibility")
        text = ast.unparse(node)
        assert "NOT (" in text and "TARGET_VISIBILITY_SQL" in text, (
            "隐藏计数没有对 `TARGET_VISIBILITY_SQL` 取反 —— 两个数字会各自为真"
        )

    def test_hosts_do_not_keep_a_second_visibility_filter(self) -> None:
        """三个宿主都不得自留可见性 SQL 字面量（剥 docstring 后判）。"""
        offenders: list[str] = []
        for path in HOST_PATHS:
            stripped = _strip_docstrings(path.read_text(encoding="utf-8"))
            for node in ast.walk(ast.parse(stripped)):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = node.value
                    if "is_deleted" in text and "wp_index" not in text and "FROM working_paper" in text:
                        offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, (
            f"宿主里有自留的可见性过滤 SQL: {offenders} —— 口径的真源只能是生产模块"
        )

    def test_the_hidden_counter_has_a_real_consumer(self) -> None:
        """🔴 防死代码（假绿第①源）：隐藏计数必须真的被宿主调用。

        additive 地加一个诊断函数而没有消费方时，「报告不说谎」这条承诺在生产上
        完全不成立，而任何单测都照样绿。
        """
        consumers: list[str] = []
        for path in HOST_PATHS:
            stripped = _strip_docstrings(path.read_text(encoding="utf-8"))
            for node in ast.walk(ast.parse(stripped)):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "count_candidates_hidden_by_visibility"
                ):
                    consumers.append(f"{path.name}:{node.lineno}")
        assert consumers, (
            "没有任何宿主调用 `count_candidates_hidden_by_visibility` —— 它是死代码，"
            "「无目标时区分『一条都没有』与『有但不可见』」这条承诺在生产上不成立"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 行为判据（真 PG）
# ═══════════════════════════════════════════════════════════════════════════


class TestInvisibleCandidatesAreNotSelected:
    """不可见候选即便按全序本该胜出，也不得被选中。"""

    def test_the_fixture_makes_hidden_rows_win_the_order(self, snap: dict[str, Any]) -> None:
        """🔴 分母：旧口径必须选中**不可见**的那条。

        这一条先立，后面两条才有意义 —— 若旧口径本来也选可见那条，
        则「新口径选可见那条」对任何实现恒真（在当前状态下与正确结果同值的无效用例）。
        """
        old_pick = snap["picks"]["old_control"]
        assert old_pick == snap["seeded"]["project_deleted"], (
            f"旧口径选中的是 {old_pick}，而构造期望它选中已删项目那条 "
            f"{snap['seeded']['project_deleted']} —— 用例对可见性过滤不敏感"
        )

    def test_production_picks_the_visible_row(self, snap: dict[str, Any]) -> None:
        assert snap["picks"]["production"] == snap["seeded"]["visible"], (
            f"生产解析选中 {snap['picks']['production']}，期望可见那条 "
            f"{snap['seeded']['visible']}。已删项目 / 已删索引 / 已删底稿三类候选都"
            "比它早创建，被选中说明可见性过滤没生效"
        )

    def test_the_control_query_agrees_with_production(self, snap: dict[str, Any]) -> None:
        """对照 SQL 与生产函数结论必须一致 —— 否则是本判据自己抄错了口径。"""
        assert snap["picks"]["new_control"] == snap["picks"]["production"], (
            f"对照 {snap['picks']['new_control']} 与生产 {snap['picks']['production']} 不一致"
        )

    def test_all_three_hidden_layers_are_counted(self, snap: dict[str, Any]) -> None:
        """三类不可见各种了一条 ⇒ 隐藏计数必须恰为 3。

        只断言 `> 0` 时，漏掉任一层（例如只过滤项目不过滤索引）也会通过。
        """
        assert snap["hidden_count"] == 3, (
            f"隐藏计数 {snap['hidden_count']}，期望 3（已删项目 / 已删索引 / 已删底稿各一条）"
            " —— 数不到 3 说明某一层没被计入，也就没被过滤"
        )

    def test_no_target_when_only_hidden_rows_remain(self, snap: dict[str, Any]) -> None:
        assert snap["picks"]["after_removing_visible"] is None, (
            f"删掉唯一可见候选后仍解析出 {snap['picks']['after_removing_visible']} —— "
            "不可见底稿被当成了合法目标"
        )
        assert snap["hidden_count_after"] == 3, (
            f"删掉可见候选后隐藏计数变成 {snap['hidden_count_after']}，期望仍是 3"
        )


class TestDiagnosisPointsAtTheRightRemedy:
    """无目标诊断必须区分两种成因 —— 它们的解除动作完全不同。"""

    def test_hidden_case_mentions_project_deletion(self, snap: dict[str, Any]) -> None:
        text = snap["diagnosis_hidden"]
        assert "不可见" in text and "项目已删除" in text, (
            f"隐藏候选存在时的诊断没点明成因: {text!r} —— "
            "读报告的人会去新建底稿，而真实解除动作是恢复项目或改裁决表"
        )
        assert "3" in text, f"诊断里没有隐藏条数: {text!r} —— 数字缺失则无法复算"

    def test_empty_case_does_not_claim_invisibility(self, snap: dict[str, Any]) -> None:
        """🔴 反向：码族下真的一条都没有时，**不得**报「有但不可见」。

        少了这一条，一个把两种情形都报成「不可见」的实现同样通过 ——
        那只是把误导换了个方向。
        """
        text = snap["diagnosis_empty"]
        assert "不可见" not in text and "没有存活底稿" in text, (
            f"码族为空时的诊断措辞错了: {text!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# BP-27：adapter 接线取 current representation 必须只认「可见」底稿
# ═══════════════════════════════════════════════════════════════════════════

#: 四个 pilot 模块 —— `attach_pilot_adapters()` 的所在处。
PILOT_PATHS: tuple[Path, ...] = (
    _BACKEND / "app/services/workpaper_sync/pilot_h1_grouped_dynamic.py",
    _BACKEND / "app/services/workpaper_sync/pilot_d2_large_json.py",
    _BACKEND / "app/services/workpaper_sync/pilot_g7_two_level_dynamic.py",
    _BACKEND / "app/services/workpaper_sync/pilot_simple_checklist.py",
)


class TestPilotsShareOneRepresentationLookup:
    """BP-27：4 个 pilot 不得各留一份 entry_state 查询。

    实测根因（2026-09-06）：四处逐字相同（md5 `2256d0b778f0`）的查询同时有三个问题
    —— 只按 `entry_id` 过滤（而主键是 `(wp_id, entry_id)`，同 entry 多实例合法）、
    无 `ORDER BY` 就取 `.first()`、不看项目软删除。H1 当时正好三条全中：BP-26 修好后
    在活项目发了新首版，而旧的已删项目那条 entry_state 仍在 ⇒ adapter 可能绑到前端
    404 的那份 representation。**这一条在生产请求路径上**（`wp_sync_router`），
    比宿主脚本更要紧。
    """

    def test_no_pilot_queries_entry_state_directly(self) -> None:
        offenders: list[str] = []
        for path in PILOT_PATHS:
            stripped = _strip_docstrings(path.read_text(encoding="utf-8"))
            for node in ast.walk(ast.parse(stripped)):
                if (
                    isinstance(node, ast.Attribute)
                    and node.attr == "current_representation_id"
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "WorkpaperSyncEntryState"
                ):
                    offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, (
            f"pilot 里仍有直查 `WorkpaperSyncEntryState.current_representation_id`: "
            f"{offenders} —— 可见性与确定性口径的真源只能是 "
            "`projection_target_resolution.resolve_visible_current_representation_id`"
        )

    def test_every_pilot_uses_the_shared_resolver(self) -> None:
        """🔴 反向：不能只证明「没有旧写法」，还要证明**新写法真的被调用**。

        少了这一条，把整段查询删掉（adapter 永不注册）也会让上一条判据通过。
        """
        missing: list[str] = []
        for path in PILOT_PATHS:
            stripped = _strip_docstrings(path.read_text(encoding="utf-8"))
            found = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "resolve_visible_current_representation_id"
                for node in ast.walk(ast.parse(stripped))
            )
            if not found:
                missing.append(path.name)
        assert not missing, (
            f"这些 pilot 没有调用共享解析器: {missing} —— adapter 取不到 representation"
        )

    def test_the_resolver_filters_and_orders(self) -> None:
        """共享解析器必须同时具备可见性过滤与确定性全序。"""
        stripped = _strip_docstrings(RESOLUTION_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "resolve_visible_current_representation_id")
        text = ast.unparse(node)
        assert "TARGET_VISIBILITY_SQL" in text, (
            "共享解析器没用可见性常量 —— 又会取到已删项目上的 representation"
        )
        assert "ORDER BY" in text and "LIMIT 1" in text, (
            "共享解析器缺确定性全序或 LIMIT 1 —— 多实例下取哪条不确定"
        )
        assert "JOIN projects p" in text, "没 JOIN projects，`p.is_deleted` 无从求值"


# ═══════════════════════════════════════════════════════════════════════════
# BP-29：artifact 根全平台必须同一个，否则读写两侧永远错层
# ═══════════════════════════════════════════════════════════════════════════

#: 全平台构造 `CanonicalArtifactRepository` 的地方（读写两侧都在内）。
_ARTIFACT_ROOT_SCAN_DIRS: tuple[Path, ...] = (
    _BACKEND / "app/services/workpaper_sync",
    _BACKEND / "app/routers",
    _BACKEND / "scripts/fix",
)


class TestArtifactRootIsOneChoice:
    """BP-29：`CanonicalArtifactRepository` 的根不得用 `storage_root()`。

    实测证据（决定性，2026-09-06）：artifact 的 `relative_path` **自带 `storage/`
    前缀** ⇒ 根必须是 `BACKEND_ROOT`（= `backend/`）。分布是 **142 : 4** ——
    `backend/storage/<proj>/…` 有 142 个 representations 目录（多数派用 `BACKEND_ROOT`
    写的，含生产请求路径 `wp_sync_router`），而两个首版发布宿主用 `storage_root()`
    写出的双层 `backend/storage/storage/…` 只有 4 个。

    错层的后果不是「少了点文件」：adapter 组装时 `ArtifactPublishError` /
    `ArtifactUnreadableError` 必抛 ⇒ `capability_counts.bidirectional` 在结构上
    永不可能 > 0。而此前 capability 门恒抛、门后代码从未执行 ⇒ 这个错根一直不可见
    （假绿第①源：门后代码等于死代码）。
    """

    def test_no_module_uses_storage_root_as_artifact_root(self) -> None:
        offenders: list[str] = []
        for directory in _ARTIFACT_ROOT_SCAN_DIRS:
            for path in sorted(directory.rglob("*.py")):
                stripped = _strip_docstrings(path.read_text(encoding="utf-8"))
                for node in ast.walk(ast.parse(stripped)):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "CanonicalArtifactRepository"
                        and node.args
                    ):
                        arg = node.args[0]
                        is_storage_root_call = (
                            isinstance(arg, ast.Call)
                            and isinstance(arg.func, ast.Name)
                            and arg.func.id == "storage_root"
                        )
                        if is_storage_root_call:
                            offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, (
            f"这些地方把 `storage_root()` 当 artifact 根: {offenders} —— "
            "artifact 的 relative_path 自带 `storage/` 前缀，会写出双层 "
            "`backend/storage/storage/…`，而全平台读取方都在 `backend/storage/…` 找"
        )

    def test_the_denominator_is_not_empty(self) -> None:
        """🔴 分母：扫描范围里必须真的有 `CanonicalArtifactRepository(...)` 调用。

        没有这一条，扫错目录（0 个调用）也会让上一条恒真 —— 本 spec 反复踩过的
        「在空集上恒真」。
        """
        total = 0
        for directory in _ARTIFACT_ROOT_SCAN_DIRS:
            for path in sorted(directory.rglob("*.py")):
                stripped = _strip_docstrings(path.read_text(encoding="utf-8"))
                for node in ast.walk(ast.parse(stripped)):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "CanonicalArtifactRepository"
                    ):
                        total += 1
        assert total >= 10, (
            f"扫描范围里只找到 {total} 处 `CanonicalArtifactRepository(...)`（应 >=10）"
            " —— 扫描面不对，上面那条判据会在空集上恒真"
        )
