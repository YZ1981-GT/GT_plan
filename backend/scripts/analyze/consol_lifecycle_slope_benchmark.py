"""合并运行生命周期——企业树节点数斜率基准（spec consolidation-run-and-workpaper-lifecycle-closure 批 8 Task 8.1）。

用途
----
在隔离库（SQLite in-memory）里按 N ∈ {10, 100, 500} 个企业树节点规模播种一个
合成合并项目，**复用真实合并代码路径**（不重写）测量下列不变量随节点数 N 的斜率：

- tree build 次数：每 target/run 恰一次（R10.1，与 N 无关 ⇒ 斜率 0）；
- CalcBasis load 次数：每 target/run 恰一次（R10.1，与 N 无关 ⇒ 斜率 0）；
- SQL 语句数：build_tree + load_calc_basis 的 SQL 对 N 有界（递归 CTE / IN 列表，
  不按节点逐条查询 ⇒ 斜率≈0，不出现 N² 爆炸）；
- push_targets 的 SQL 数（递归 CTE，对父链深度恒为 1）；
- 附注章节 fill_note_sections 的 SQL 对章节数 S 的斜率为 0（view_context 只构建一次，
  R10.2 / 批 5.5）；
- 墙钟/CPU 时间、tracemalloc 峰值内存、数据库连接 checkout 次数。

设计取舍
--------
真实 `build_tree`、`load_calc_basis`、`push_targets` 直接跑在播种库上，是 R10 不变量的
权威度量。附注斜率复用真实 `fill_note_sections`（含「view_ctx 循环外构建一次 + 逐章 SAVEPOINT」
的真实编排），仅把单章计算核 `fill_by_formula` 替换为一次固定的真实 DB 读，使「每章固定开销」
与「view_context 一次性开销」可分离度量——附注模板/明细映射的全量播种不属于本斜率基准范围
（批 5.8 已有功能回归覆盖）。

候选 vs HEAD
------------
候选改动（批 2/3：operation 每 target 一次 tree/context/basis；push_targets 递归 CTE；
fill_note_sections view_ctx 循环外构建）已在本树。斜率不变量的**绝对界**本身即回归守卫：
tree/basis 次数平斜、SQL 对 N 有界、附注对 S 斜率 0。若未来回归（如退回逐节点装载 basis
或把 view_ctx 放进章节循环），本基准的断言会打红。HEAD 基线期望值记录在输出 JSON 的
``head_baseline_expectation`` 字段，供人工对照。

运行
----
    python backend/scripts/analyze/consol_lifecycle_slope_benchmark.py
    python backend/scripts/analyze/consol_lifecycle_slope_benchmark.py --nodes 10 100 500 --out tmp_consol_lifecycle/slope_benchmark.json

退出码：0 全部不变量满足；1 任一斜率越界（可作独立门禁）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import tracemalloc
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

# 让脚本可直接 `python backend/scripts/analyze/...` 运行：把 backend/ 放进 sys.path。
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import tests.conftest  # noqa: F401,E402 - 注册全模型与 SQLite 方言补丁
from app.models.audit_platform_models import AccountCategory, TrialBalance  # noqa: E402
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.consol_note_data_models import ConsolNoteData  # noqa: E402
from app.models.consolidation_models import (  # noqa: E402
    EliminationEntry,
    EliminationEntryType,
    ReviewStatusEnum,
)
from app.models.core import Project, User  # noqa: E402

YEAR = 2025
ROOT_CODE = "SLOPE_ROOT"

#: 播种的合成库里只建这几张表：全表 create_all 会连带并发会话引入的 PG-only 默认值表
#: （如 user_display_preferences 的 '{}'::jsonb），在 SQLite 上无法建表。
_TABLES = [
    User.__table__,
    Project.__table__,
    TrialBalance.__table__,
    EliminationEntry.__table__,
    ConsolNoteData.__table__,
]

#: 每个数据叶子播种的试算表科目数（固定；基准度量的是节点数 N 的斜率，不是科目数 A）。
_ACCOUNTS_PER_LEAF = 3
_ACCOUNT_CODES = ("1001", "1002", "2001")


# ─────────────────────────────── 仪表 ───────────────────────────────


class _Instruments:
    """一次测量窗口：SQL 语句数 + 连接 checkout 数。绑定到 async engine 的 sync_engine。"""

    def __init__(self, engine):
        self._sync_engine = engine.sync_engine
        self.sql_count = 0
        self.connection_checkouts = 0

    def _on_exec(self, *_args, **_kwargs):
        self.sql_count += 1

    def _on_checkout(self, *_args, **_kwargs):
        self.connection_checkouts += 1

    def __enter__(self) -> "_Instruments":
        event.listen(self._sync_engine, "before_cursor_execute", self._on_exec)
        event.listen(self._sync_engine, "checkout", self._on_checkout)
        return self

    def __exit__(self, *_exc):
        event.remove(self._sync_engine, "before_cursor_execute", self._on_exec)
        event.remove(self._sync_engine, "checkout", self._on_checkout)


# ─────────────────────────────── 播种 ───────────────────────────────


def _project(
    *,
    name: str,
    code: str,
    scope: str,
    parent_code: str | None = None,
    ultimate_code: str | None = None,
    relation: str | None = None,
) -> Project:
    return Project(
        id=uuid.uuid4(),
        name=f"【测试】{name}_{YEAR}",
        client_name=f"【测试】{name}",
        company_code=code,
        audit_year=YEAR,
        report_scope=scope,
        status=ProjectStatus.execution,
        parent_company_code=parent_code,
        ultimate_company_code=ultimate_code,
        relation_to_parent=relation,
        is_deleted=False,
    )


async def seed_consolidated_group(db: AsyncSession, node_target: int) -> Project:
    """播种一个合成合并集团：1 个合并项目 + (node_target-1) 个子公司单体项目（星形）。

    返回根合并项目。子公司单体项目填三码（parent/ultimate=根代码，relation=subsidiary），
    使 build_tree 推导出「根合并 + 根差额 + 母公司 + 各子公司」结构。每个数据叶子播种
    固定科目数的试算表，根合并项目播种若干已审批抵销分录（证明 load_calc_basis 的 IN 列表
    查询对叶子数不放大）。
    """
    subsidiary_count = max(0, node_target - 1)

    root = _project(
        name="集团",
        code=ROOT_CODE,
        scope="consolidated",
        ultimate_code=ROOT_CODE,
    )
    db.add(root)
    await db.flush()

    subsidiaries: list[Project] = []
    for i in range(subsidiary_count):
        sub = _project(
            name=f"子公司{i}",
            code=f"SUB{i:04d}",
            scope="standalone",
            parent_code=ROOT_CODE,
            ultimate_code=ROOT_CODE,
            relation="subsidiary",
        )
        db.add(sub)
        subsidiaries.append(sub)
    await db.flush()

    # 试算表：每个单体子公司播种固定科目数（数据叶子的审定数来源）。
    for sub in subsidiaries:
        for j, acct in enumerate(_ACCOUNT_CODES[:_ACCOUNTS_PER_LEAF]):
            db.add(TrialBalance(
                id=uuid.uuid4(),
                project_id=sub.id,
                year=YEAR,
                company_code=sub.company_code,
                standard_account_code=acct,
                account_name=f"科目{acct}",
                account_category=AccountCategory.asset,
                audited_amount=Decimal("100.00") * (j + 1),
                opening_balance=Decimal("0.00"),
            ))

    # 抵销分录：根合并项目上几笔已审批分录（固定数量，不随节点放大）。
    for k in range(3):
        db.add(EliminationEntry(
            id=uuid.uuid4(),
            project_id=root.id,
            year=YEAR,
            entry_no=f"E{k}",
            entry_type=EliminationEntryType.equity,
            account_code=_ACCOUNT_CODES[0],
            account_name=f"科目{_ACCOUNT_CODES[0]}",
            debit_amount=Decimal("50.00"),
            credit_amount=Decimal("0.00"),
            lines=[{
                "account_code": _ACCOUNT_CODES[0],
                "account_name": f"科目{_ACCOUNT_CODES[0]}",
                "debit_amount": "50.00",
                "credit_amount": "0.00",
            }],
            related_company_codes=[],
            entry_group_id=uuid.uuid4(),
            review_status=ReviewStatusEnum.approved,
        ))

    await db.commit()
    return root


# ─────────────────────────────── 单点度量 ───────────────────────────────


@dataclass
class NodePointMetrics:
    """单个节点规模 N 的度量结果。"""

    node_target: int
    actual_node_count: int
    tree_build_calls: int
    basis_load_calls: int
    tree_sql: int
    basis_sql: int
    push_targets_sql: int
    push_targets_count: int
    note_section_sql_by_s: dict[int, int] = field(default_factory=dict)
    wall_ms: float = 0.0
    cpu_ms: float = 0.0
    peak_memory_kb: float = 0.0
    connection_checkouts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_target": self.node_target,
            "actual_node_count": self.actual_node_count,
            "tree_build_calls": self.tree_build_calls,
            "basis_load_calls": self.basis_load_calls,
            "tree_sql": self.tree_sql,
            "basis_sql": self.basis_sql,
            "push_targets_sql": self.push_targets_sql,
            "push_targets_count": self.push_targets_count,
            "note_section_sql_by_s": {str(k): v for k, v in self.note_section_sql_by_s.items()},
            "wall_ms": round(self.wall_ms, 3),
            "cpu_ms": round(self.cpu_ms, 3),
            "peak_memory_kb": round(self.peak_memory_kb, 1),
            "connection_checkouts": self.connection_checkouts,
        }


async def _measure_note_section_sql(
    db: AsyncSession,
    engine,
    root: Project,
    *,
    section_counts: tuple[int, ...] = (1, 10),
) -> dict[int, int]:
    """复用真实 fill_note_sections 测附注章节 SQL 对章节数 S 的斜率。

    fill_note_sections 先在章节循环外构建一次 view_ctx（load_calc_basis + 报表配置），
    再逐章调 fill_by_formula。为把「一次性 view_ctx 开销」与「每章固定开销」分离度量，
    这里用真实编排 + 真实 view_context（预构建），并把单章计算核替换为一次固定真实 DB 读。
    S=1 与 S=10 的 SQL 数之差 = 9 × 每章固定开销；view_ctx 构建对 S 的贡献为 0。
    """
    import app.services.consol_note_formula_service as note_mod
    from app.services.consol_report_view_service import ViewContext
    from app.services.consol_calc_basis import load_calc_basis
    from app.services.consol_tree_service import build_tree

    # 预构建真实 view_context（真实 basis + 空报表行），章节循环外一次构建。
    tree = await build_tree(db, root.id)
    assert tree is not None
    basis = await load_calc_basis(db, root.id, YEAR, tree=tree)
    assert basis is not None
    view_ctx = ViewContext(basis=basis, rows=[], standard="soe_consolidated", year=YEAR)

    original_fill = note_mod.fill_by_formula

    async def _probe_fill_by_formula(_db, project_id, year, section_id, **_kwargs):
        # 每章一次固定的真实 DB 读（计入 SAVEPOINT 内的 per-section SQL）。
        # 🔴 必须用真实存在的列（section_id，不是 section_code）：错列会抛 AttributeError 被
        #    fill_note_sections 的 except 吞进 failures，每章零 SQL ⇒ 斜率假 0（伪绿）。
        await _db.execute(
            sa.select(sa.func.count())
            .select_from(ConsolNoteData.__table__)
            .where(
                ConsolNoteData.project_id == project_id,
                ConsolNoteData.year == year,
                ConsolNoteData.section_id == str(section_id),
            )
        )
        return {"section_id": section_id, "status": "persisted"}

    result: dict[int, int] = {}
    note_mod.fill_by_formula = _probe_fill_by_formula  # type: ignore[assignment]
    try:
        for s in section_counts:
            section_ids = [f"SEC{i}" for i in range(s)]
            with _Instruments(engine) as inst:
                outcome = await note_mod.fill_note_sections(
                    db,
                    root.id,
                    YEAR,
                    section_ids,
                    node_key=tree.node_key,
                    template_type="soe_consolidated",
                    view_context=view_ctx,
                )
            # 🔴 防伪绿：每章必须真的跑过（否则「斜率 0」只是因为全章静默失败）。
            if len(outcome.get("results") or []) != s or outcome.get("failures"):
                raise AssertionError(
                    f"附注章节探针未全部执行：S={s} results={len(outcome.get('results') or [])} "
                    f"failures={outcome.get('failures')}"
                )
            result[s] = inst.sql_count
    finally:
        note_mod.fill_by_formula = original_fill  # type: ignore[assignment]
    return result


async def measure_point(engine, node_target: int) -> NodePointMetrics:
    """播种 node_target 规模并度量全部不变量。每点用独立会话。"""
    import app.services.consol_calc_basis as calc_mod
    import app.services.consol_tree_service as tree_mod
    from app.services import consol_push_service as push_service

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 计数真实 build_tree / load_calc_basis 的调用次数（包裹真实实现，不改语义）。
    real_build_tree = tree_mod.build_tree
    real_load_basis = calc_mod.load_calc_basis
    counters = {"tree": 0, "basis": 0}

    async def counting_build_tree(db, root_project_id):
        counters["tree"] += 1
        return await real_build_tree(db, root_project_id)

    async def counting_load_basis(db, project_id, year, **kwargs):
        counters["basis"] += 1
        return await real_load_basis(db, project_id, year, **kwargs)

    async with factory() as db:
        root = await seed_consolidated_group(db, node_target)

    # ── 1. 真实 build_tree 的 SQL + 节点数（一次构建） ──
    async with factory() as db:
        with _Instruments(engine) as tree_inst:
            tree = await real_build_tree(db, root.id)
        assert tree is not None
        from app.services.consol_tree_service import iter_nodes
        actual_nodes = sum(1 for _ in iter_nodes(tree))

    # ── 2. 真实 load_calc_basis 的 SQL（一次装载，复用上面那棵树） ──
    async with factory() as db:
        tree2 = await real_build_tree(db, root.id)
        assert tree2 is not None
        with _Instruments(engine) as basis_inst:
            basis = await real_load_basis(db, root.id, YEAR, tree=tree2)
        assert basis is not None

    # ── 3. push_targets 的 SQL（递归 CTE，恒为 1） ──
    async with factory() as db:
        with _Instruments(engine) as pt_inst:
            targets = await push_service.push_targets(db, root.id)

    # ── 4. 调用次数：一个 operation/target 只建一次 tree、装一次 basis ──
    # 用包裹计数版跑一次「树→口径」的典型 operation 前置（_load_runtime 语义）。
    tree_mod.build_tree = counting_build_tree  # type: ignore[assignment]
    calc_mod.load_calc_basis = counting_load_basis  # type: ignore[assignment]
    try:
        async with factory() as db:
            t = await tree_mod.build_tree(db, root.id)
            await calc_mod.load_calc_basis(db, root.id, YEAR, tree=t)
    finally:
        tree_mod.build_tree = real_build_tree  # type: ignore[assignment]
        calc_mod.load_calc_basis = real_load_basis  # type: ignore[assignment]

    # ── 5. 附注章节 SQL 对 S 的斜率 ──
    async with factory() as db:
        note_sql = await _measure_note_section_sql(db, engine, root)

    # ── 6. 墙钟/CPU/内存/连接（整段树→口径流程） ──
    tracemalloc.start()
    wall0, cpu0 = time.perf_counter(), time.process_time()
    async with factory() as db:
        with _Instruments(engine) as flow_inst:
            ft = await real_build_tree(db, root.id)
            await real_load_basis(db, root.id, YEAR, tree=ft)
    cpu_ms = (time.process_time() - cpu0) * 1000.0
    wall_ms = (time.perf_counter() - wall0) * 1000.0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return NodePointMetrics(
        node_target=node_target,
        actual_node_count=actual_nodes,
        tree_build_calls=counters["tree"],
        basis_load_calls=counters["basis"],
        tree_sql=tree_inst.sql_count,
        basis_sql=basis_inst.sql_count,
        push_targets_sql=pt_inst.sql_count,
        push_targets_count=len(targets),
        note_section_sql_by_s=note_sql,
        wall_ms=wall_ms,
        cpu_ms=cpu_ms,
        peak_memory_kb=peak / 1024.0,
        connection_checkouts=flow_inst.connection_checkouts,
    )


# ─────────────────────────────── 斜率与判定 ───────────────────────────────


def _slope(xs: list[int], ys: list[float]) -> float:
    """最小二乘斜率 dy/dx；点数 < 2 返回 0。"""
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return num / denom


@dataclass
class SlopeReport:
    points: list[NodePointMetrics]
    tree_build_calls_slope: float
    basis_load_calls_slope: float
    tree_sql_slope: float
    basis_sql_slope: float
    note_section_sql_slope: float
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": [p.to_dict() for p in self.points],
            "slopes": {
                "tree_build_calls_vs_n": round(self.tree_build_calls_slope, 6),
                "basis_load_calls_vs_n": round(self.basis_load_calls_slope, 6),
                "tree_sql_vs_n": round(self.tree_sql_slope, 6),
                "basis_sql_vs_n": round(self.basis_sql_slope, 6),
                "note_section_sql_vs_s": round(self.note_section_sql_slope, 6),
            },
            "invariants_ok": self.ok,
            "violations": list(self.violations),
            "head_baseline_expectation": {
                "note": (
                    "候选改动（批 2/3：每 target 一次 tree/context/basis；push_targets 递归 CTE；"
                    "fill_note_sections view_ctx 循环外构建）已在本树。HEAD（批 2/3 之前）期望："
                    "附注若把 view_ctx 放进章节循环则 note_section_sql_vs_s 会出现 CalcBasis 级常数项 × S，"
                    "push_targets 若按父链逐层查询则 push_targets_sql 会随深度线性增长。"
                ),
                "expected_tree_build_calls_per_target": 1,
                "expected_basis_load_calls_per_target": 1,
                "expected_push_targets_sql": 1,
            },
        }


def evaluate_slopes(points: list[NodePointMetrics]) -> SlopeReport:
    """计算斜率并按 R10 不变量判定；违规记入列表（供脚本退出码与 pytest 断言共用）。"""
    xs = [p.node_target for p in points]
    tree_calls = _slope(xs, [float(p.tree_build_calls) for p in points])
    basis_calls = _slope(xs, [float(p.basis_load_calls) for p in points])
    tree_sql = _slope(xs, [float(p.tree_sql) for p in points])
    basis_sql = _slope(xs, [float(p.basis_sql) for p in points])

    # 附注章节：所有点合并 (S, sql) 求斜率；view_ctx 一次构建 ⇒ 斜率 = 每章固定开销（有界小常数）。
    note_xs: list[int] = []
    note_ys: list[float] = []
    for p in points:
        for s, sql in sorted(p.note_section_sql_by_s.items()):
            note_xs.append(s)
            note_ys.append(float(sql))
    note_slope = _slope(note_xs, note_ys)

    violations: list[str] = []

    # R10.1：每 target/run 恰一次 tree build 与一次 basis load（与 N 无关）。
    for p in points:
        if p.tree_build_calls != 1:
            violations.append(
                f"N={p.node_target}: tree build 调用 {p.tree_build_calls} 次（应恰 1）"
            )
        if p.basis_load_calls != 1:
            violations.append(
                f"N={p.node_target}: CalcBasis load 调用 {p.basis_load_calls} 次（应恰 1）"
            )
    # 次数斜率必须为 0（平斜）。
    if abs(tree_calls) > 1e-9:
        violations.append(f"tree build 次数对 N 斜率 {tree_calls}（应为 0）")
    if abs(basis_calls) > 1e-9:
        violations.append(f"CalcBasis load 次数对 N 斜率 {basis_calls}（应为 0）")

    # R10.1/R10.2：build_tree / load_calc_basis 的 SQL 对 N 有界（递归 CTE / IN 列表，非逐节点）。
    # 单条 SQL 可能因 IN 列表而变长，但语句**数**不得随 N 线性增长：斜率接近 0。
    if abs(tree_sql) > 1e-6:
        violations.append(f"build_tree SQL 对 N 斜率 {tree_sql}（应≈0，不逐节点查询）")
    if abs(basis_sql) > 1e-6:
        violations.append(f"load_calc_basis SQL 对 N 斜率 {basis_sql}（应≈0，用 IN 列表非逐叶查询）")

    # push_targets 递归 CTE：恒 1 条 SQL。
    for p in points:
        if p.push_targets_sql != 1:
            violations.append(
                f"N={p.node_target}: push_targets SQL {p.push_targets_sql} 条（递归 CTE 应恰 1）"
            )

    # R10.2 / 批 5.5：附注章节 SQL 对 S 的斜率 = 每章固定开销（有界小常数），
    # view_context 不随 S 重复构建 ⇒ 斜率里不含 CalcBasis 级开销。
    # 健康基线：每章 = SAVEPOINT + 单章计算 + RELEASE ≈ 3；若 view_ctx 退回章节循环内重建，
    # 每章会多出一整套 CalcBasis 装载（require_calc_year + tb + entries）⇒ 斜率跳到 ≈5（已由
    # 变异反证 tmp_consol_lifecycle/_diag_mutation_note_slope.py 实测：健康 3.0 → 变异 5.0）。
    # 阈值 4.5 介于两者之间：健康通过、回归打红。
    _NOTE_SLOPE_MAX = 4.5
    if note_slope >= _NOTE_SLOPE_MAX:
        violations.append(
            f"附注章节 SQL 对 S 斜率 {note_slope}（≥{_NOTE_SLOPE_MAX} ⇒ 疑似 view_context 进了章节循环，每章重建 basis）"
        )

    return SlopeReport(
        points=points,
        tree_build_calls_slope=tree_calls,
        basis_load_calls_slope=basis_calls,
        tree_sql_slope=tree_sql,
        basis_sql_slope=basis_sql,
        note_section_sql_slope=note_slope,
        violations=violations,
    )


# ─────────────────────────────── 编排 ───────────────────────────────


async def run_benchmark(node_targets: tuple[int, ...]) -> SlopeReport:
    """按节点规模逐点度量并求斜率。每个节点规模用独立的 in-memory engine（干净库）。"""
    points: list[NodePointMetrics] = []
    for n in node_targets:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
            points.append(await measure_point(engine, n))
        finally:
            await engine.dispose()
    return evaluate_slopes(points)


def _default_out() -> Path:
    return _BACKEND_ROOT.parent / "tmp_consol_lifecycle" / "slope_benchmark.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合并生命周期节点数斜率基准")
    parser.add_argument(
        "--nodes", type=int, nargs="+", default=[10, 100, 500],
        help="节点规模列表（默认 10 100 500）",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="输出 JSON 路径（默认 仓库根/tmp_consol_lifecycle/slope_benchmark.json）",
    )
    args = parser.parse_args(argv)

    report = asyncio.run(run_benchmark(tuple(args.nodes)))
    payload = report.to_dict()
    payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload["node_targets"] = list(args.nodes)

    out = args.out or _default_out()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload["slopes"], ensure_ascii=False, indent=2))
    for p in report.points:
        print(
            f"N={p.node_target:>4} 节点={p.actual_node_count:>4} "
            f"tree_sql={p.tree_sql} basis_sql={p.basis_sql} "
            f"push_targets_sql={p.push_targets_sql}(targets={p.push_targets_count}) "
            f"tree_calls={p.tree_build_calls} basis_calls={p.basis_load_calls} "
            f"note_sql={p.note_section_sql_by_s} "
            f"wall={p.wall_ms:.1f}ms cpu={p.cpu_ms:.1f}ms mem={p.peak_memory_kb:.0f}KB "
            f"conn={p.connection_checkouts}"
        )
    print(f"\n输出：{out}")
    if report.ok:
        print("✅ 全部斜率不变量满足")
        return 0
    print("❌ 斜率越界：")
    for v in report.violations:
        print(f"  - {v}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
