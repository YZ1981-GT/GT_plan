"""预览与回滚守卫 — Property 31 / 32 / 33.

spec: soe-listed-note-conversion-correctness / Task 17
（Requirements 9.1, 9.2, 9.3, 9.4）

🔴 **Property 编号按 design.md 现行表**（31 预览无写入且与实际一致 / 32 回滚往返一致 /
33 自动触发留快照）。tasks.md 原写「29~31」是 2026-08-07 全量重映射前的错位编号，
照旧编号写守卫会覆盖错的 Property（29 是「真 null 附理由」、30 是「章号映射核查结论
落地」，都归别的任务）。

🔴 **本文件由两个并发会话对同一任务的产出合并而成（2026-08-08）**，取各自更强的一半：

* **行为面**（真跑 handler 并抓日志、真跑往返并逐字段比对）—— 会话 A；
* **源码面用 AST 形态判据而非字符串包含**（``_log_call_carries`` / ``_assigns_from`` /
  ``_expr``）—— 会话 B。「源码里出现 snapshot_id 字样」会被 docstring 与日志文案骗过，
  AST 才能判「哪条 ``logger.info`` 的第几个实参是 ``result.get('snapshot_id')``」。

同一不变式**只保留一处实现**：Property 33 的源码判据统一走 AST（会话 A 的正则谓词已
撤下），行为判据统一走事件总线驱动（会话 B 曾判定「成本远超收益」，实测用
``patch(event_bus.subscribe)`` 只收集不注册即可，故保留）。

------------------------------------------------------------------------------
本文件与相邻守卫的分工（不得互相重复断言）
------------------------------------------------------------------------------

==========================================================  ==================================
文件                                                        定位
==========================================================  ==================================
``tests/services/test_note_conversion_section_mapping_production.py``  Task 10：单章节被正确处理
                                                            （**替身真源**：``FakeSession`` /
                                                            ``make_note`` / ``_Savepoint``）
``tests/test_note_conversion_v2_removal.py``                Task 10：v2 符号归零 + 迁移表锁死
                                                            （**源码剥离工具真源**：
                                                            ``_code_level_source``）
``tests/test_note_conversion_section_mapping.py``           Task 11：正向映射的 Property 级
                                                            不变式（**判据数据真源**：``_Fx``）
``tests/test_note_conversion_preview_rollback.py``（本文件） Task 17：**预览零写入 / 往返一致 /
                                                            自动触发留痕**
==========================================================  ==================================

故本文件刻意**不重复**正向映射的任何断言（改写落在目标侧 / 归档留痕 / 新建空章节形态
…… 全部归 Task 10/11）。本文件只问三件事：**预览有没有写库**、**往返之后回不回得去**、
**自动触发有没有留下可回滚的线索**。

替身与判据数据一律 **import 复用**，不在本文件重造 —— 同一替身两份实现即双真源
（改一处另一处不红），平台已多次踩过。本文件只做**加法式扩展**：
:class:`ConversionSession` 继承 ``FakeSession`` 补出预览/回滚链路额外需要的四类能力
（``Project`` / ``ChainExecution`` 查询、``scalar_one_or_none``、``delete``、
savepoint 的显式 ``rollback``），而 ``_RollbackAwareSavepoint`` 的「还原到进入时快照」
逻辑**复用基类实现**（传哨兵异常走同一段代码），不抄第二份。

------------------------------------------------------------------------------
为什么用内存替身而不是真实库
------------------------------------------------------------------------------

Requirement 10.6 明令禁止为凑验收改动真实项目的 ``template_type``（会触发
``execute_full_chain(force=True)`` 全链重算）；真实库验收归 Task 19 且需用户显式授权
专用项目。本文件走内存替身，但**判据数据全部取自真实 diff + 真实两份模板 JSON**
（章节 sid / 章节号 / 标题现取，不自造），故仍是对生产逻辑的有效验证。

🔴 替身的 savepoint 语义必须与生产一致，否则 Property 31 是空转：

* **异常** → 还原到进入时快照（基类已实现，且 ``__aexit__`` 返回 ``False`` 不吞异常）；
* **显式 ``await sp.rollback()``** → 同样还原（本文件扩展）；
* **干净退出且未显式 rollback** → **保留写入**（真实 SQLAlchemy 会 RELEASE savepoint）。

第三条是关键：正是它让「预览里漏了 ``await sp.rollback()``」这个变异能被打红。
:meth:`TestGuardSanity.test_savepoint_without_explicit_rollback_keeps_writes` 反向钉死它。
"""
from __future__ import annotations

import ast
import copy
import inspect
import logging
import pathlib
import re
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa

from app.models.chain_execution import ChainExecution
from app.models.core import Project
from app.models.report_models import DisclosureNote
from app.services.note_conversion_service import (
    ROLLBACK_REASON_LEGACY_SNAPSHOT,
    ROLLBACK_SKIP_CREATED_HAS_CONTENT,
    ROLLBACK_UNRESTORED_FIELDS,
    SNAPSHOT_FORMAT_VERSION,
    NoteConversionService,
    snapshot_note_state,
)

# --- 复用 Task 10 的内存替身（禁止在本文件再造一份）------------------------------
from tests.services.test_note_conversion_section_mapping_production import (  # noqa: E402
    PROJECT,
    YEAR,
    FakeSession,
    _Result,
    _Savepoint,
    make_note,
)

# --- 复用 Task 11 的判据数据派生 + binding 前缀收集器 ----------------------------
from tests.test_note_conversion_section_mapping import (  # noqa: E402
    _Fx,
    _pair_note,
    collect_binding_prefixes,
)

# --- 复用 Task 10 的源码剥离工具（剥 # 注释 + docstring，保留普通字符串）----------
from tests.test_note_conversion_v2_removal import (  # noqa: E402
    CONVERSION_SERVICE,
    _code_level_source,
)

#: ``STANDARD_CHANGED`` handler 所在文件（Property 33 的源码判据面）
EVENT_IMPL = (
    pathlib.Path(inspect.getsourcefile(NoteConversionService)).resolve()  # type: ignore[arg-type]
    .parents[1]
    / "services"
    / "event_handlers"
    / "_impl.py"
)


# ===========================================================================
# 替身扩展 —— 只补预览/回滚链路额外需要的能力
# ===========================================================================


class _SavepointRolledBack(Exception):
    """哨兵异常：仅用于驱动基类 ``__aexit__`` 的「还原到进入时快照」分支。

    显式 ``rollback()`` 与「异常回滚」在语义上是同一件事（都要还原到 savepoint
    进入时的状态），故复用基类那段实现而不在本文件抄第二份。
    """


class _ScalarResult:
    """``Project`` / ``ChainExecution`` 查询的最小结果对象。

    这两类查询走 ``scalar_one_or_none()``，而 Task 10 替身的 ``_Result`` 只服务
    ``disclosure_notes``（``scalars().all()`` / ``all()``）⇒ 这里是**新查询种类的新
    能力**，不是既有替身的复制。
    """

    def __init__(self, obj: Any) -> None:
        self._obj = obj

    def scalar_one_or_none(self) -> Any:
        return self._obj


class _RollbackAwareSavepoint(_Savepoint):
    """给 Task 10 的 savepoint 替身补一个显式 ``rollback()``。

    生产 :meth:`NoteConversionService.preview_note_conversion` 写的是::

        async with self.db.begin_nested() as sp:
            detail = await self._map_disclosure_notes(...)
            await sp.rollback()          # ← 不可省

    真实 SQLAlchemy 在 ``__aexit__`` 时若 savepoint 仍活跃会 **RELEASE**（写入生效）
    ⇒ 替身必须复刻这一点：**干净退出且未显式 rollback ⇒ 保留写入**。否则「漏写
    rollback」这个最核心的变异会静默变绿。
    """

    def __init__(self, session: "ConversionSession") -> None:
        super().__init__(session)
        self.rolled_back = False

    async def rollback(self) -> None:
        await super().__aexit__(_SavepointRolledBack, _SavepointRolledBack(), None)
        self.session._resync_flushed_state()
        self.rolled_back = True

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is None:
            # 已显式回滚 ⇒ 无事可做；未回滚 ⇒ RELEASE（保留写入），同基类。
            return False
        result = await super().__aexit__(exc_type, exc, tb)
        self.session._resync_flushed_state()
        return result


def make_project(template_type: str = "soe") -> Project:
    """替身用的 ``Project`` 实例（不入库，只被 ``_get_project`` 读）。"""
    p = Project()
    p.id = PROJECT
    p.name = "替身项目"
    p.template_type = template_type
    return p


class ConversionSession(FakeSession):
    """在 Task 10 替身之上补出**预览与回滚**链路要用的能力。

    加法式扩展四类：

    1. ``Project`` 的 SELECT/UPDATE（``_get_project`` / Step 2 切 ``template_type``）；
    2. ``ChainExecution`` 的 INSERT/SELECT/UPDATE（快照落盘 / 回滚取快照 /
       ``_record_forward_summary`` 写正向摘要）；
    3. ``disclosure_notes`` 的**不过滤 ``is_deleted``** 全列查询 —— 回滚要复原归档章节，
       而基类的全列查询只返回未删除行（正向映射的口径）。判据取编译文本里有无
       ``is_deleted = false``（实测 ``sa.false()`` 就渲染成 ``false``）；
    4. ``delete()`` / ``rollback()`` / ``new`` / ``dirty`` / ``deleted``
       —— 回滚要物理删除新建空章节，预览的第 3 层零写入核验要读那三个集合。

    另**模拟 Python 侧 ``default=uuid4`` 在 flush 时赋 id** —— 裸
    ``DisclosureNote()`` / ``ChainExecution()`` 的 ``id`` 实测为 ``None``，而
    ``_create_snapshot`` 会拿 ``execution.id`` 当 ``snapshot_id`` 回传、回滚又按
    ``note_id`` 反查快照。不模拟就会得到字面量 ``"None"`` 当主键。
    """

    def __init__(
        self,
        notes: list[Any],
        *,
        project: Project | None = None,
        flush_fail_on: set[UUID] | None = None,
    ) -> None:
        super().__init__(notes, flush_fail_on=flush_fail_on)
        self.project = project if project is not None else make_project()
        self.chain_rows: list[ChainExecution] = []
        self.session_rollbacks = 0
        self.update_statements: list[str] = []
        self._pending_new: list[Any] = []
        self._pending_deleted: list[Any] = []
        self._flushed: dict[int, tuple] = {}
        self._resync_flushed_state()

    # -- 状态可见性（preview 第 3 层核验读它们）----------------------------

    @staticmethod
    def _note_state(note: Any) -> tuple:
        return (
            note.section_id,
            note.note_section,
            bool(note.is_deleted),
            copy.deepcopy(note.table_data),
            copy.deepcopy(note.template_lineage),
        )

    def _resync_flushed_state(self) -> None:
        """把「已落盘状态」重置为当前内存状态。

        真实 SQLAlchemy 在 flush / savepoint 回滚后会让对象不再是 ``dirty``
        （回滚路径靠 expire 实现）⇒ 替身用「重新快照」表达同一效果。
        """
        self._flushed = {id(n): self._note_state(n) for n in self.notes}

    @property
    def new(self) -> tuple[Any, ...]:
        return tuple(self._pending_new)

    @property
    def deleted(self) -> tuple[Any, ...]:
        return tuple(self._pending_deleted)

    @property
    def dirty(self) -> tuple[Any, ...]:
        out = []
        for n in self.notes:
            before = self._flushed.get(id(n))
            if before is None or before != self._note_state(n):
                out.append(n)
        return tuple(out)

    # -- 会话操作 ----------------------------------------------------------

    def add(self, obj: Any) -> None:
        if isinstance(obj, ChainExecution):
            if obj.id is None:
                obj.id = uuid4()
            self.chain_rows.append(obj)
            self._pending_new.append(obj)
            return
        super().add(obj)
        self._pending_new.append(obj)

    async def delete(self, obj: Any) -> None:
        self.notes = [n for n in self.notes if n is not obj]
        self.added = [n for n in self.added if n is not obj]
        self._pending_deleted.append(obj)

    async def flush(self) -> None:
        # 模拟 Python 侧 default=uuid4 在 INSERT 时生效
        for n in self.notes:
            if getattr(n, "id", None) is None:
                n.id = uuid4()
        for row in self.chain_rows:
            if row.id is None:
                row.id = uuid4()
        await super().flush()
        self._pending_new.clear()
        self._pending_deleted.clear()
        self._resync_flushed_state()

    async def rollback(self) -> None:
        self.session_rollbacks += 1
        self._pending_new.clear()
        self._pending_deleted.clear()

    def begin_nested(self) -> _RollbackAwareSavepoint:
        return _RollbackAwareSavepoint(self)

    # -- 查询分发 ----------------------------------------------------------

    async def execute(self, stmt: Any) -> Any:
        text = str(stmt)
        is_update = text.lstrip().upper().startswith("UPDATE")
        if is_update:
            self.update_statements.append(text)

        if "chain_executions" in text:
            if is_update:
                params = stmt.compile().params
                target = str(params.get("id_1"))
                for row in self.chain_rows:
                    if str(row.id) == target:
                        row.steps = params.get("steps")
                return _ScalarResult(None)
            # SELECT ... ORDER BY created_at DESC LIMIT 1 ⇒ 取最后插入的一条
            return _ScalarResult(self.chain_rows[-1] if self.chain_rows else None)

        if "projects" in text:
            if is_update:
                params = stmt.compile().params
                if "template_type" in params:
                    self.project.template_type = params["template_type"]
                return _ScalarResult(None)
            return _ScalarResult(self.project)

        head = text.split("FROM")[0]
        if "disclosure_notes.table_data" in head and "is_deleted = false" not in text:
            # 回滚路径：**含软删记录**（归档章节要复原、新建空章节要识别）
            return _Result(list(self.notes))
        return await super().execute(stmt)


# ===========================================================================
# 判据数据与场景构造
# ===========================================================================


@pytest.fixture(scope="module")
def fx() -> _Fx:
    """真实 diff + 真实两份模板派生的候选章节（复用 Task 11 的派生逻辑）。"""
    return _Fx()


def binding_table_data(number: str) -> dict[str, Any]:
    """带 ``binding_id``（章节号前缀）与 manual 单元格的 ``table_data``。

    binding 刻意分布在三处容器（``rows`` / ``_tables[].rows`` / ``sub_table_data``）——
    生产的前缀改写是**递归**处理的，只放一处测不出「只扫了固定路径」。
    """
    return {
        "rows": [
            {
                "label": "行A",
                "binding_id": f"{number}.行A.closing_balance",
                "values": ["1,000.00", "2,000.00"],
                "_cell_modes": {"0": "manual", "1": "formula"},
            }
        ],
        "_tables": [
            {
                "name": "表一",
                "rows": [
                    {"label": "行B", "binding_id": f"{number}.行B.opening_balance"}
                ],
            }
        ],
        "sub_table_data": {
            "明细表一": [{"label": "行C", "binding_id": f"{number}.行C.prior_value"}]
        },
    }


def build_notes(fx: _Fx) -> list[Any]:
    """造一组覆盖三条正向路径的章节记录（改写 / 改写+lineage 已有值 / 归档）。

    ``pair0`` 带 binding + manual 单元格（Property 32 的 binding 往返判据）；
    ``pair1`` 的 ``template_lineage`` 预置非空 dict（验证「整体还原」而非「删掉我们
    加的键」—— 后者无法还原 ``conversions`` 这类 list 的原有元素）；
    ``archived`` 落在源侧独有清单里，正向会被软删归档。
    """
    pair0 = _pair_note(fx, fx.c0, table_data=binding_table_data(fx.c0["src_num"]))
    pair1 = _pair_note(
        fx, fx.c1, lineage={"conversions": [{"seq": 1, "note": "预置历史记录"}]}
    )
    archived = make_note(
        section_id=fx.archive_sid,
        note_section=fx.archive_num,
        section_title="源侧独有章节",
        table_data={"rows": [{"label": "行X", "values": ["9"]}]},
    )
    return [pair0, pair1, archived]


def note_state(note: Any) -> dict[str, Any]:
    """Property 32 的五项判据投影（``binding_id`` 以「全部前缀集合」表达）。

    🔴 **有意不复用** :func:`snapshot_note_state` —— 那是**被测**的快照投影；拿它当
    期望值就是自证（快照少存一个字段，两侧同时少，断言照样绿）。
    """
    return {
        "section_id": note.section_id,
        "note_section": note.note_section,
        "is_deleted": bool(note.is_deleted),
        "template_lineage": copy.deepcopy(note.template_lineage),
        "binding_prefixes": collect_binding_prefixes(note.table_data),
        "table_data": copy.deepcopy(note.table_data),
    }


def states_by_id(notes: list[Any]) -> dict[str, dict[str, Any]]:
    return {str(n.id): note_state(n) for n in notes}


def patch_chain_refresh():
    """把全链重算打桩 —— 它对真实 orchestrator 有依赖，与本文件判据无关。

    生产里它是 fail-open 的（失败只 warning），打桩只为让日志干净、结果确定。
    """
    return patch.object(
        NoteConversionService,
        "_trigger_chain_refresh",
        new=AsyncMock(return_value=True),
    )


# ===========================================================================
# AST 形态判据工具（Property 33 的源码面；不用字符串包含）
# ===========================================================================

_IMPL_TREE = ast.parse(EVENT_IMPL.read_text(encoding="utf-8"))
_SERVICE_TREE = ast.parse(CONVERSION_SERVICE.read_text(encoding="utf-8"))


def _expr(src: str) -> str:
    """由 ``ast.unparse`` **派生**期望形态。

    🔴 不能手写字符串形态去比 —— ``ast.unparse`` 会把字符串下标统一规范化成单引号，
    手写双引号形态恒不相等（判据会在正确实现上静默返回 False）。
    """
    return ast.unparse(ast.parse(src, mode="eval").body)


def _find_func(tree: ast.AST, name: str, where: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{where} 里找不到函数 {name}")


def _handler_node() -> ast.AST:
    return _find_func(_IMPL_TREE, "_on_standard_changed_notes", EVENT_IMPL.name)


def _service_method_node(name: str) -> ast.AST:
    return _find_func(_SERVICE_TREE, name, CONVERSION_SERVICE.name)


def _log_call_carries(node: ast.AST, level: str, marker: str, arg_form: str) -> bool:
    """节点内是否有一条 ``logger.<level>`` 调用：格式串含 ``marker`` 且实参含 ``arg_form``。

    纯函数 —— 便于用「好/坏」两个替身证明判据非恒真（见
    :meth:`TestProperty33_AutoTriggerRecordsSnapshotId.test_ast_judgement_is_not_vacuous`）。
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        try:
            if ast.unparse(sub.func) != f"logger.{level}":
                continue
        except Exception:  # noqa: BLE001
            continue
        if not sub.args or not isinstance(sub.args[0], ast.Constant):
            continue
        if marker not in str(sub.args[0].value):
            continue
        for arg in sub.args[1:]:
            try:
                if ast.unparse(arg) == arg_form:
                    return True
            except Exception:  # noqa: BLE001
                continue
    return False


def _assigns_from(node: ast.AST, target: str, value_form: str) -> bool:
    """节点内是否有 ``target = <value_form>`` 的赋值（按 AST 形态精确比对）。"""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Assign):
            continue
        if target not in {ast.unparse(t) for t in sub.targets}:
            continue
        try:
            if ast.unparse(sub.value) == value_form:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _assigns_call_containing(node: ast.AST, target: str, needle: str) -> bool:
    """节点内是否有 ``target = ...<needle>...`` 的赋值（值形态含子串即可）。"""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Assign):
            continue
        if target not in {ast.unparse(t) for t in sub.targets}:
            continue
        try:
            if needle in ast.unparse(sub.value):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


# ===========================================================================
# 判据自检 —— 缺了这层，判据失效会表现为「全绿」
# ===========================================================================


class TestGuardSanity:
    """替身语义、判据数据与判据工具的自检。"""

    def test_candidate_data_is_non_empty(self, fx: _Fx) -> None:
        assert fx.diff.get("is_mock") is False, "落盘 diff 仍是 mock -- 判据数据不可信"
        assert fx.plan["pairs"], "pairs 为空 -- 预览/回滚判据失效"
        assert fx.plan["source_only"], "source_only 为空 -- 归档往返判据失效"
        assert fx.plan["target_only"], "target_only 为空 -- 新建撤销判据失效"
        assert fx.c0["src_num"] != fx.c0["tgt_num"], (
            "候选 pair 两侧章节号相同 -- binding 前缀改写与往返判据失效"
        )

    def test_event_impl_path_resolves(self) -> None:
        assert EVENT_IMPL.exists(), f"事件 handler 文件定位失败：{EVENT_IMPL}"
        assert "_on_standard_changed_notes" in EVENT_IMPL.read_text(encoding="utf-8")

    def test_savepoint_replica_is_the_shared_double(self) -> None:
        """扩展替身必须继承 Task 10 的 ``_Savepoint``（不是另造一份 savepoint 语义）。"""
        sp = ConversionSession([]).begin_nested()
        assert isinstance(sp, _Savepoint)
        assert hasattr(sp, "rollback"), "替身缺 rollback()，生产的显式回滚无从复刻"

    @pytest.mark.asyncio
    async def test_savepoint_explicit_rollback_restores_state(self, fx: _Fx) -> None:
        """显式 ``rollback()`` 必须还原到进入时快照（本文件扩展的语义）。"""
        note = _pair_note(fx, fx.c0)
        sess = ConversionSession([note])
        before = note_state(note)
        async with sess.begin_nested() as sp:
            note.section_id = "mutated-sid"
            note.note_section = "零、被改过"
            await sp.rollback()
        assert note_state(note) == before, "显式 rollback 未还原 -- 替身语义与生产不符"

    @pytest.mark.asyncio
    async def test_savepoint_without_explicit_rollback_keeps_writes(
        self, fx: _Fx
    ) -> None:
        """🔴 反向自检：干净退出且未显式 rollback ⇒ **保留写入**（真实 SQLAlchemy 会 RELEASE）。

        这条是 Property 31 不空转的前提 —— 若替身在干净退出时也还原，则「预览无写入」
        的断言对「生产漏写 ``await sp.rollback()``」完全不敏感。
        """
        note = _pair_note(fx, fx.c0)
        sess = ConversionSession([note])
        async with sess.begin_nested():
            note.section_id = "mutated-sid"
        assert note.section_id == "mutated-sid", (
            "替身在干净退出时还原了 savepoint -- 「预览漏 rollback」将无法被打红"
        )

    @pytest.mark.asyncio
    async def test_savepoint_replica_still_propagates_exceptions(self) -> None:
        """子类不得把基类「不吞异常」的纪律改坏（否则失败隔离断言静默变绿）。"""
        sess = ConversionSession([])
        with pytest.raises(RuntimeError):
            async with sess.begin_nested():
                raise RuntimeError("must propagate")

    @pytest.mark.asyncio
    async def test_rollback_path_query_returns_soft_deleted_rows(self, fx: _Fx) -> None:
        """回滚用的全列查询必须**含软删记录**，否则归档章节根本进不了回退范围。"""
        live = _pair_note(fx, fx.c0)
        gone = _pair_note(fx, fx.c1)
        gone.is_deleted = True
        sess = ConversionSession([live, gone])

        all_rows = await sess.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == PROJECT, DisclosureNote.year == YEAR
            )
        )
        live_rows = await sess.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == PROJECT,
                DisclosureNote.year == YEAR,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        assert len(list(all_rows.scalars().all())) == 2, "回滚口径查询漏掉了软删记录"
        assert len(list(live_rows.scalars().all())) == 1, "正向口径查询不该返回软删记录"

    def test_state_projection_covers_the_five_required_fields(self, fx: _Fx) -> None:
        """Property 32 点名的五项必须都在判据投影里（少一项即判据不完整）。"""
        note = _pair_note(fx, fx.c0, table_data=binding_table_data(fx.c0["src_num"]))
        keys = set(note_state(note))
        for field in (
            "section_id",
            "note_section",
            "is_deleted",
            "template_lineage",
            "binding_prefixes",
        ):
            assert field in keys, f"判据投影缺 {field} -- Property 32 不完整"
        assert note_state(note)["binding_prefixes"] == {fx.c0["src_num"]}, (
            "binding 前缀收集器没抓到三处容器里的绑定 -- 往返判据空转"
        )

    def test_state_projection_does_not_reuse_the_production_snapshot(self) -> None:
        """``note_state`` 必须独立实现 —— 复用被测的 ``snapshot_note_state`` 就是自证。"""
        body = _code_level_source(inspect.getsource(note_state))
        assert "snapshot_note_state" not in body, (
            "note_state 复用了被测的快照投影函数 -- 快照少存字段将不可见"
        )


# ===========================================================================
# Property 31 —— 预览无写入，且预览计数 == 随后真实执行的计数
# Validates: Requirements 9.1, 9.2
# ===========================================================================


class TestProperty31_PreviewHasNoWrites:
    """预览端点执行后 DB 无变化；预览返回的计数与真实执行的计数相等。

    ``preview_note_conversion`` 走 savepoint + 显式 rollback 真跑一遍映射，故
    「计数相等」由**构造**保证 —— 但只有在**回滚真的干净**时才成立。下面两组断言
    正是从这两个方向夹住它：状态逐字段不变 + 紧随其后的真实执行得到同一组计数。
    """

    @pytest.mark.asyncio
    async def test_preview_leaves_every_note_byte_identical(self, fx: _Fx) -> None:
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        svc = NoteConversionService(sess)

        before = states_by_id(notes)
        before_count = len(sess.notes)

        payload = await svc.preview_note_conversion(PROJECT, YEAR, "listed")

        assert payload["status"] == "preview"
        assert states_by_id(notes) == before, (
            "预览改动了既有章节的五项字段 -- 违反 Requirement 9.2（预览不得产生写入）"
        )
        assert len(sess.notes) == before_count, (
            f"预览留下了 {len(sess.notes) - before_count} 条新建章节 -- savepoint 未回滚干净"
        )
        assert sess.added == [], "预览留下了待写入对象（session.added 非空）"
        assert sess.committed is False, "预览调用了 commit -- 违反 Requirement 9.2"
        assert sess.chain_rows == [], "预览创建了转换快照行 -- 预览不该落任何行"

    @pytest.mark.asyncio
    async def test_preview_leaves_no_pending_write_objects(self, fx: _Fx) -> None:
        """生产第 3 层核验读的 ``new`` / ``dirty`` / ``deleted`` 必须全空。

        非空时生产会记 ERROR 并整体 ``db.rollback()`` —— 那条兜底路径不该被触发。
        """
        sess = ConversionSession(build_notes(fx))
        svc = NoteConversionService(sess)
        await svc.preview_note_conversion(PROJECT, YEAR, "listed")
        leftover = len(sess.new) + len(sess.dirty) + len(sess.deleted)
        assert leftover == 0, (
            f"预览后仍有 {leftover} 个待写对象（new={len(sess.new)} "
            f"dirty={len(sess.dirty)} deleted={len(sess.deleted)}）"
        )
        assert sess.session_rollbacks == 0, (
            "生产触发了整体 db.rollback() 兜底 -- 说明 savepoint 没兜住写入"
        )

    @pytest.mark.asyncio
    async def test_preview_counts_are_non_zero(self, fx: _Fx) -> None:
        """判据自检：四类计数必须都非零，否则「相等」断言等于空转。"""
        sess = ConversionSession(build_notes(fx))
        svc = NoteConversionService(sess)
        payload = await svc.preview_note_conversion(PROJECT, YEAR, "listed")
        assert payload["mapped"] > 0, "预览 mapped 为 0 -- 相等判据空转"
        assert payload["archived"] > 0, "预览 archived 为 0 -- 相等判据空转"
        assert payload["created"] > 0, "预览 created 为 0 -- 相等判据空转"
        assert payload["user_edits_preserved"] > 0, (
            "预览 user_edits_preserved 为 0 -- manual 单元格判据空转"
        )

    @pytest.mark.asyncio
    async def test_preview_counts_equal_subsequent_real_mapping(self, fx: _Fx) -> None:
        """**同一 session** 先预览、再真跑映射 ⇒ 计数逐项相等。

        这一条同时验两件事：预览没留下写入（否则第二次跑会因「已是目标侧」大批进
        ``skipped``，计数必然变）与「预览用的就是真实执行那条路径」。
        """
        sess = ConversionSession(build_notes(fx))
        svc = NoteConversionService(sess)

        preview = await svc.preview_note_conversion(PROJECT, YEAR, "listed")
        real = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")

        assert preview["mapped"] == real["mapped"]
        assert preview["archived"] == real["archived"]
        assert preview["created"] == real["created"]
        assert preview["user_edits_preserved"] == real["user_edits_preserved"]
        assert preview["details"]["skipped_count"] == len(real["skipped"]), (
            "预览与真实执行的 skipped 条数不等 -- 预览没回滚干净或走了另一条路径"
        )
        assert preview["details"]["failed_count"] == len(real["failed"])
        assert (
            preview["details"]["binding_ids_rewritten"] == real["binding_ids_rewritten"]
        )

    @pytest.mark.asyncio
    async def test_preview_counts_equal_execute_conversion_end_to_end(
        self, fx: _Fx
    ) -> None:
        """预览（session A）与 ``execute_conversion``（session B，同构初始状态）计数相等。

        与上一条的分工：上一条盯「同一 session 里预览有没有留痕」，这一条盯「预览的
        六个键与真实**端到端**执行上报的数是不是同一批」—— 若哪天 ``execute_conversion``
        改用了别的映射实现，只有这一条会红。
        """
        sess_preview = ConversionSession(build_notes(fx))
        preview = await NoteConversionService(sess_preview).preview_note_conversion(
            PROJECT, YEAR, "listed"
        )

        sess_real = ConversionSession(build_notes(fx))
        with patch_chain_refresh():
            real = await NoteConversionService(sess_real).execute_conversion(
                PROJECT, YEAR, "listed"
            )

        assert real["status"] == "completed"
        assert preview["mapped"] == real["mapped_notes"]
        assert preview["archived"] == real["archived_notes"]
        assert preview["created"] == real["created_notes"]
        assert (
            preview["user_edits_preserved"]
            == real["notes_detail"]["user_edits_preserved"]
        )
        assert preview["details"]["skipped_count"] == real["notes_skipped"]
        assert preview["details"]["failed_count"] == real["notes_failed"]

    @pytest.mark.asyncio
    async def test_preview_does_not_touch_project_template_type(self, fx: _Fx) -> None:
        """Requirement 10.6：预览不得改 ``template_type``（会触发全链重算）。"""
        sess = ConversionSession(build_notes(fx))
        svc = NoteConversionService(sess)
        await svc.preview_note_conversion(PROJECT, YEAR, "listed")
        assert sess.project.template_type == "soe", "预览改了 project.template_type"
        assert sess.update_statements == [], (
            f"预览发出了 UPDATE 语句：{sess.update_statements}"
        )

    def test_preview_source_forbids_writing_project_standard_columns(self) -> None:
        """源码级：预览方法体内不得出现对三个准则口径列的写入（Requirement 10.6）。"""
        src = _code_level_source(
            inspect.getsource(NoteConversionService.preview_note_conversion)
        )
        for banned in ("template_type=", "report_scope=", "applicable_standard_v2="):
            assert banned not in src, (
                f"preview_note_conversion 里出现 {banned!r} -- 预览不得改项目准则口径"
            )
        assert "sa.update(" not in src, "预览方法体内出现 sa.update( -- 预览不得写库"

    def test_preview_explicitly_rolls_back_the_savepoint(self) -> None:
        """源码级：``await sp.rollback()`` 必须在场。

        savepoint 干净退出会 RELEASE（写入生效）⇒ 漏掉这一行就是「预览真写库」。
        行为层由 :meth:`test_preview_leaves_every_note_byte_identical` 覆盖，本条
        额外钉住写法，让「把 rollback 挪进条件分支」这类改动也能被看见。
        """
        src = _code_level_source(
            inspect.getsource(NoteConversionService.preview_note_conversion)
        )
        assert re.search(r"async with\s+self\.db\.begin_nested\(\)\s+as\s+sp", src), (
            "预览未使用 `async with self.db.begin_nested() as sp` -- 无法显式回滚"
        )
        assert re.search(r"await\s+sp\.rollback\(\)", src), (
            "预览缺少 `await sp.rollback()` -- savepoint 会被 RELEASE，预览将真实写库"
        )

    @pytest.mark.asyncio
    async def test_preview_is_sensitive_to_a_missing_rollback(self, fx: _Fx) -> None:
        """🔴 反向自检：把 ``rollback()`` 打成空操作后，「无写入」必须变得不成立。

        证明零写入断言不是空转（不改磁盘文件，只在本测试内替换替身方法）。
        """
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        svc = NoteConversionService(sess)
        before = states_by_id(notes)

        async def _noop(self: _RollbackAwareSavepoint) -> None:
            self.rolled_back = True

        with patch.object(_RollbackAwareSavepoint, "rollback", _noop):
            await svc.preview_note_conversion(PROJECT, YEAR, "listed")

        assert states_by_id(notes) != before or len(sess.notes) != len(notes), (
            "漏掉 rollback 后状态竟然没变 -- 「预览无写入」的断言对该缺陷不敏感"
        )

    @pytest.mark.asyncio
    async def test_same_type_preview_is_no_change_and_writes_nothing(
        self, fx: _Fx
    ) -> None:
        """同类型预览走零值早退，不发 UPDATE、不落快照。"""
        sess = ConversionSession(build_notes(fx))
        svc = NoteConversionService(sess)
        payload = await svc.preview_note_conversion(PROJECT, YEAR, "soe")
        assert payload["status"] == "no_change"
        assert payload["mapped"] == payload["archived"] == payload["created"] == 0
        assert sess.update_statements == []
        assert sess.chain_rows == []

    @pytest.mark.asyncio
    async def test_invalid_target_type_raises(self) -> None:
        sess = ConversionSession([])
        with pytest.raises(ValueError):
            await NoteConversionService(sess).preview_note_conversion(
                PROJECT, YEAR, "private"
            )

    def test_preview_payload_keys_match_the_endpoint_schema(self) -> None:
        """交叉锁死：服务返回的顶层键集 ≡ 路由 ``NoteSectionPreviewResponse`` 字段集。

        Requirement 9.1 的端点契约在两处表达（服务投影 + pydantic 模型），任一侧加/删
        键而另一侧不跟 ⇒ 预览响应静默丢字段。
        """
        from app.routers.note_conversion import NoteSectionPreviewResponse

        payload = NoteConversionService._build_note_preview_payload(
            "soe",
            "listed",
            {
                "mapped": 1,
                "archived": 2,
                "created": 3,
                "user_edits_preserved": 4,
                "forbidden_hits": [],
                "skipped": [],
                "failed": [],
            },
        )
        assert set(payload) == set(NoteSectionPreviewResponse.model_fields), (
            "预览投影的键集与端点响应模型不一致 -- 端点契约漂移"
        )
        for key in (
            "mapped",
            "archived",
            "created",
            "user_edits_preserved",
            "forbidden_hits",
            "details",
        ):
            assert key in payload, f"design 端点契约要求的 {key} 缺失"

    def test_preview_and_rollback_endpoints_are_registered(self) -> None:
        """Requirement 9.1 / 9.3：两个端点必须真的挂在 router 上（否则前端不可达）。"""
        from app.routers.note_conversion import router

        routes = [
            (getattr(r, "path", ""), set(getattr(r, "methods", set())))
            for r in router.routes
        ]
        preview = [p for p, m in routes if p.endswith("/{year}/preview") and "GET" in m]
        rollback = [p for p, m in routes if p.endswith("/rollback") and "POST" in m]
        assert preview, f"未找到 GET .../{{year}}/preview：{routes}"
        assert rollback, f"未找到 POST .../rollback：{routes}"
        assert preview[0].startswith("/api/projects/{project_id}/notes/conversion")


# ===========================================================================
# Property 32 —— soe→listed→rollback 往返一致
# Validates: Requirements 9.3
# ===========================================================================


async def _forward(sess: ConversionSession, target: str = "listed") -> dict[str, Any]:
    with patch_chain_refresh():
        return await NoteConversionService(sess).execute_conversion(
            PROJECT, YEAR, target
        )


async def _rollback(sess: ConversionSession) -> dict[str, Any]:
    with patch_chain_refresh():
        return await NoteConversionService(sess).rollback_conversion(PROJECT, YEAR)


class TestProperty32_RollbackRoundtrip:
    """往返后 ``section_id`` / ``note_section`` / ``is_deleted`` /
    ``template_lineage`` / ``binding_id`` 回到初始。

    🔴 第一条测试是**判据自检**：正向必须真的改动了这五项，否则「回到初始」在
    「正向什么都没做」时同样成立（最典型的假绿形态）。
    """

    @pytest.mark.asyncio
    async def test_forward_really_mutates_all_five_fields(self, fx: _Fx) -> None:
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        before = states_by_id(notes)

        result = await _forward(sess)

        after = states_by_id(notes)
        changed: set[str] = set()
        for nid, state in after.items():
            for key, value in state.items():
                if before[nid][key] != value:
                    changed.add(key)
        for field in (
            "section_id",
            "note_section",
            "is_deleted",
            "template_lineage",
            "binding_prefixes",
        ):
            assert field in changed, (
                f"正向转换没有改动 {field} -- Property 32 对该字段的往返断言空转"
            )
        assert result["created_notes"] > 0, "正向没有新建章节 -- 撤销新建的断言空转"
        assert len(sess.notes) > len(notes), "新建章节没有进 session"

    @pytest.mark.asyncio
    async def test_roundtrip_restores_five_fields(self, fx: _Fx) -> None:
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        before = states_by_id(notes)
        forward = await _forward(sess)

        rolled = await _rollback(sess)

        assert rolled["status"] == "rolled_back", (
            f"回滚未报完全成功：status={rolled['status']} sections={rolled.get('sections')}"
        )
        assert rolled["sections"]["complete"] is True
        after = states_by_id(notes)
        for nid, initial in before.items():
            got = after[nid]
            for field in (
                "section_id",
                "note_section",
                "is_deleted",
                "template_lineage",
                "binding_prefixes",
            ):
                assert got[field] == initial[field], (
                    f"note {nid} 的 {field} 未回到初始：{got[field]!r} != {initial[field]!r}"
                )
        # table_data 整体逐字节相等 —— 仅当正向没做过不可逆的格式适配时成立
        if int(forward["notes_detail"].get("format_adapted") or 0) == 0:
            for nid, initial in before.items():
                assert after[nid]["table_data"] == initial["table_data"], (
                    f"note {nid} 的 table_data 未逐字节回到初始"
                )
        else:  # pragma: no cover - field_mapping 实测 39/39 全 null，当前不可达
            assert rolled["status"] == "partial", (
                "正向做过格式适配（不可逆）而回滚仍报完全成功 -- 必须降级为 partial"
            )

    @pytest.mark.asyncio
    async def test_roundtrip_removes_created_sections(self, fx: _Fx) -> None:
        """新建的空章节必须被撤销（否则往返后残留一批空骨架章节）。"""
        notes = build_notes(fx)
        original_ids = {str(n.id) for n in notes}
        sess = ConversionSession(notes)
        forward = await _forward(sess)
        assert forward["created_notes"] > 0

        rolled = await _rollback(sess)

        assert rolled["sections"]["created_removed"] == forward["created_notes"], (
            f"新建 {forward['created_notes']} 个、撤销 "
            f"{rolled['sections']['created_removed']} 个 -- 数量不等"
        )
        leftover = {str(n.id) for n in sess.notes} - original_ids
        assert leftover == set(), f"往返后残留 {len(leftover)} 个新建章节"

    @pytest.mark.asyncio
    async def test_roundtrip_unarchives_the_archived_section(self, fx: _Fx) -> None:
        """归档（软删）必须被撤销，且计数如实上报。"""
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        forward = await _forward(sess)
        assert forward["archived_notes"] > 0

        rolled = await _rollback(sess)

        assert rolled["sections"]["unarchived"] == forward["archived_notes"]
        assert all(not n.is_deleted for n in notes), "仍有章节停在软删（归档）状态"

    @pytest.mark.asyncio
    async def test_roundtrip_restores_template_type(self, fx: _Fx) -> None:
        sess = ConversionSession(build_notes(fx))
        await _forward(sess)
        assert sess.project.template_type == "listed"
        rolled = await _rollback(sess)
        assert rolled["restored_type"] == "soe"
        assert sess.project.template_type == "soe"

    @pytest.mark.asyncio
    async def test_reverse_direction_roundtrip(self, fx: _Fx) -> None:
        """listed→soe→rollback 同样要回到初始（方向对称，不只单向可逆）。"""
        notes = [
            make_note(
                section_id=fx.c0["tgt_sid"],
                note_section=fx.c0["tgt_num"],
                section_title=fx.c0["title"],
                table_data=binding_table_data(fx.c0["tgt_num"]),
            ),
            make_note(
                section_id=fx.create_sid,
                note_section=fx.create_num,
                section_title="目标侧独有（反向即源侧独有）",
            ),
        ]
        before = states_by_id(notes)
        sess = ConversionSession(notes, project=make_project("listed"))

        forward = await _forward(sess, target="soe")
        assert forward["mapped_notes"] > 0, "反向转换零改写 -- 反向往返判据空转"

        rolled = await _rollback(sess)

        assert rolled["status"] == "rolled_back"
        assert states_by_id(notes) == before, "反向往返后状态未回到初始"
        assert sess.project.template_type == "listed"

    @pytest.mark.asyncio
    async def test_roundtrip_is_stable_over_two_cycles(self, fx: _Fx) -> None:
        """连做两次「正向 + 回滚」，终态仍等于初始（回滚不该越做越脏）。"""
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        before = states_by_id(notes)
        for _ in range(2):
            await _forward(sess)
            rolled = await _rollback(sess)
            assert rolled["status"] == "rolled_back"
        assert states_by_id(notes) == before, "两轮往返后状态漂移"

    @pytest.mark.asyncio
    async def test_legacy_snapshot_is_fail_closed(self, fx: _Fx) -> None:
        """旧格式快照（无 ``notes``）⇒ 如实报 ``partial`` + 原因码，禁静默假成功。"""
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        await _forward(sess)
        # 把快照降级成旧格式（改造前只存三个键）
        sess.chain_rows[-1].snapshot_before = {
            "template_type": "soe",
            "year": YEAR,
            "converted_at": "2026-01-01T00:00:00+00:00",
        }

        rolled = await _rollback(sess)

        assert rolled["status"] == "partial", "旧格式快照下回滚竟报完全成功（假成功）"
        assert rolled["sections"]["complete"] is False
        assert rolled["sections"]["reason"] == ROLLBACK_REASON_LEGACY_SNAPSHOT
        assert rolled["sections"]["warnings"], "旧格式快照未给出说明"
        # template_type 仍应回退（它不依赖章节快照）
        assert sess.project.template_type == "soe"
        # 章节字段结构上无从回退 ⇒ 必须一行都没改
        assert rolled["sections"]["restored"] == 0

    @pytest.mark.asyncio
    async def test_created_section_with_content_is_kept_and_status_degrades(
        self, fx: _Fx
    ) -> None:
        """转换新建的空章节若已被录入内容 ⇒ 保留不删 + 计入 skipped + 降级 partial。

        判据取**内容**而非来源：删它就是删审计师的数据（平台红线）。
        """
        notes = build_notes(fx)
        original_ids = {str(n.id) for n in notes}
        sess = ConversionSession(notes)
        await _forward(sess)

        created = [n for n in sess.notes if str(n.id) not in original_ids]
        assert created, "正向没有新建章节 -- 本条判据空转"
        touched = created[0]
        touched.text_content = "审计师在转换后录入的内容"

        rolled = await _rollback(sess)

        assert rolled["status"] == "partial", "有内容的新建章节被保留后仍报完全成功"
        reasons = {i["reason"] for i in rolled["sections"]["skipped"]}
        assert ROLLBACK_SKIP_CREATED_HAS_CONTENT in reasons, (
            f"未登记「新建章节已有内容」原因码：{reasons}"
        )
        assert touched in sess.notes, "已有内容的新建章节被物理删除 -- 删了审计师的数据"

    @pytest.mark.asyncio
    async def test_rollback_reports_unrestored_fields_honestly(self, fx: _Fx) -> None:
        """``unrestored_fields`` 必须如实上报「哪些字段不尝试还原」。"""
        sess = ConversionSession(build_notes(fx))
        await _forward(sess)
        rolled = await _rollback(sess)
        assert rolled["unrestored_fields"] == list(ROLLBACK_UNRESTORED_FIELDS)
        assert rolled["unrestored_fields"], "未声明任何不可还原字段 -- 该清单不该为空"
        assert any("table_data" in item for item in rolled["unrestored_fields"]), (
            "unrestored_fields 未提到 table_data（只回退 binding_id 前缀）"
        )

    @pytest.mark.asyncio
    async def test_rollback_without_snapshot_reports_error(self) -> None:
        sess = ConversionSession([])
        rolled = await _rollback(sess)
        assert rolled["status"] == "error"
        assert "snapshot" in rolled["message"].lower()

    def test_snapshot_projection_only_carries_reversible_fields(self, fx: _Fx) -> None:
        """``snapshot_note_state`` 只投影可回退的四项 + note_id，**不含 ``table_data``**。

        把 ``table_data`` 存进快照会让 30 天前的旧值有机会覆盖这期间的正常录入
        （数据销毁风险），而 ``binding_id`` 前缀改写本身是可逆变换、无需快照。
        """
        note = _pair_note(fx, fx.c0, table_data=binding_table_data(fx.c0["src_num"]))
        state = snapshot_note_state(note)
        assert set(state) == {
            "note_id",
            "section_id",
            "note_section",
            "is_deleted",
            "template_lineage",
        }, f"快照投影字段集漂移：{sorted(state)}"
        assert "table_data" not in state
        assert isinstance(state["note_id"], str), "note_id 必须是 str（JSONB 可序列化）"

    def test_snapshot_lineage_is_deep_copied(self, fx: _Fx) -> None:
        """快照里的 lineage 必须是深拷贝，否则后续就地改会污染快照（回滚拿到新值）。"""
        lineage = {"conversions": [{"seq": 1}]}
        note = _pair_note(fx, fx.c1, lineage=lineage)
        state = snapshot_note_state(note)
        lineage["conversions"].append({"seq": 2})
        assert state["template_lineage"] == {"conversions": [{"seq": 1}]}, (
            "快照与活对象共享了 lineage 引用 -- 回滚会拿到被污染的值"
        )

    @pytest.mark.asyncio
    async def test_forward_snapshot_is_current_format_and_covers_soft_deleted(
        self, fx: _Fx
    ) -> None:
        """快照必须是 v2 格式且**含软删记录**（否则归档章节根本进不了回退范围）。"""
        notes = build_notes(fx)
        notes[-1].is_deleted = True  # 转换前就已软删的章节也要能回退
        sess = ConversionSession(notes)
        await _forward(sess)

        snap = sess.chain_rows[-1].snapshot_before
        assert snap["snapshot_version"] == SNAPSHOT_FORMAT_VERSION
        assert snap["direction"] == "soe_to_listed"
        assert snap["notes_count"] == len(notes)
        ids = {s["note_id"] for s in snap["notes"]}
        assert str(notes[-1].id) in ids, "快照漏掉了软删记录 -- 归档章节无从回退"


# ===========================================================================
# Property 33 —— STANDARD_CHANGED 自动触发路径记录 snapshot_id 到日志
# Validates: Requirements 9.4
# ===========================================================================


def _standard_changed_notes_handler():
    """取出 ``_on_standard_changed_notes`` 闭包，**不污染全局 EventBus**。

    ``register_event_handlers()`` 会把全部 handler 注册到模块级 ``event_bus``；测试里
    直接调用会造成重复注册并影响同批其它测试。故把 ``event_bus.subscribe`` 打桩成
    「只收集不注册」，跑一遍注册函数后从收集结果里挑出目标 handler。
    """
    from app.models.audit_platform_schemas import EventType
    from app.services.event_bus import event_bus
    from app.services.event_handlers._impl import register_event_handlers

    captured: dict[Any, list[Any]] = {}

    def _fake_subscribe(event_type: Any, handler: Any) -> None:
        captured.setdefault(event_type, []).append(handler)

    with patch.object(event_bus, "subscribe", _fake_subscribe):
        register_event_handlers()

    handlers = [
        h
        for h in captured.get(EventType.STANDARD_CHANGED, [])
        if getattr(h, "__name__", "") == "_on_standard_changed_notes"
    ]
    assert handlers, (
        "STANDARD_CHANGED 上找不到 _on_standard_changed_notes -- "
        "附注层自动跟随未注册（Requirement 9.4 的载体不存在）"
    )
    return handlers[0]


class _DummySession:
    """handler 只用到 ``commit`` / ``rollback``（服务被打桩，不发查询）。"""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "_DummySession":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _payload(project_id: UUID, year: int | None, entity_type: str) -> Any:
    from app.models.audit_platform_schemas import EventType

    return SimpleNamespace(
        event_type=EventType.STANDARD_CHANGED,
        project_id=project_id,
        year=year,
        extra={"new_standard": {"entity_type": entity_type}},
    )


def _patch_service(svc: Any):
    """handler 内部是 ``from app.services.note_conversion_service import ...`` 局部导入
    ⇒ 必须打桩**源模块**上的类名。"""
    return patch(
        "app.services.note_conversion_service.NoteConversionService", return_value=svc
    )


def _patch_session(session: Any):
    return patch(
        "app.services.event_handlers._impl.async_session_factory",
        return_value=session,
    )


class TestProperty33_AutoTriggerRecordsSnapshotId:
    """自动触发路径（``STANDARD_CHANGED``）必须把 snapshot_id 记进日志。

    转换会在准则切换时**静默生效**（不经审计师点按钮）⇒ 没有 snapshot_id 就无从定位
    可回滚的快照，Requirement 9.4 因此存在。

    判据分两层：**行为层**（真跑 handler、抓真实日志）+ **源码层**（AST 形态，判「哪条
    ``logger.info`` 的第几个实参是 ``result.get('snapshot_id')``」）。源码层刻意不用
    「源码里出现 snapshot_id 字样」—— 那会被 docstring 与日志文案骗过。
    """

    # -- 行为层 ------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_success_path_logs_snapshot_id(self, caplog: Any) -> None:
        snapshot_id = str(uuid4())
        handler = _standard_changed_notes_handler()
        svc = SimpleNamespace(
            execute_conversion=AsyncMock(
                return_value={
                    "status": "completed",
                    "from_type": "soe",
                    "to_type": "listed",
                    "snapshot_id": snapshot_id,
                    "mapped_notes": 3,
                    "archived_notes": 1,
                    "created_notes": 2,
                    "warnings": [],
                }
            )
        )
        session = _DummySession()
        with _patch_service(svc), _patch_session(session), caplog.at_level(logging.INFO):
            await handler(_payload(PROJECT, YEAR, "listed"))

        text = caplog.text
        assert snapshot_id in text, (
            f"自动触发路径未把 snapshot_id 记入日志 -- 违反 Requirement 9.4。日志：{text[:600]}"
        )
        assert "snapshot_id=" in text, "日志未用 `snapshot_id=` 形态，事后检索困难"
        assert "rollback" in text.lower(), (
            "日志未给出回退入口提示 -- 「使事后可回滚」只做了一半"
        )
        assert session.committed is True

    @pytest.mark.asyncio
    async def test_warnings_are_logged_with_snapshot_id(self, caplog: Any) -> None:
        """告警（failed / manual 丢失）也必须带 snapshot_id，否则看到告警不知回滚谁。"""
        snapshot_id = str(uuid4())
        handler = _standard_changed_notes_handler()
        svc = SimpleNamespace(
            execute_conversion=AsyncMock(
                return_value={
                    "status": "completed",
                    "from_type": "soe",
                    "to_type": "listed",
                    "snapshot_id": snapshot_id,
                    "mapped_notes": 1,
                    "archived_notes": 0,
                    "created_notes": 0,
                    "warnings": ["2 个附注章节映射失败"],
                }
            )
        )
        with _patch_service(svc), _patch_session(_DummySession()), caplog.at_level(
            logging.WARNING
        ):
            await handler(_payload(PROJECT, YEAR, "listed"))

        warn = "\n".join(
            r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "2 个附注章节映射失败" in warn, "告警未落日志"
        assert snapshot_id in warn, "告警日志缺 snapshot_id"

    @pytest.mark.asyncio
    async def test_failure_path_logs_snapshot_id_and_commit_state(
        self, caplog: Any
    ) -> None:
        """失败面：snapshot_id 由异常属性携带，并如实说明「未提交 ⇒ DB 未改动」。"""
        snapshot_id = str(uuid4())
        handler = _standard_changed_notes_handler()
        exc = RuntimeError("boom")
        setattr(exc, "conversion_snapshot_id", snapshot_id)
        setattr(exc, "conversion_committed", False)
        svc = SimpleNamespace(execute_conversion=AsyncMock(side_effect=exc))
        session = _DummySession()

        with _patch_service(svc), _patch_session(session), caplog.at_level(
            logging.ERROR
        ):
            await handler(_payload(PROJECT, YEAR, "listed"))

        text = caplog.text
        assert snapshot_id in text, "失败路径未留下 snapshot_id 线索"
        assert "committed=False" in text, "未说明提交状态（无法判断 DB 是否已改动）"
        assert session.rolled_back is True, "失败后未回滚会话"

    @pytest.mark.asyncio
    async def test_missing_year_is_skipped_with_warning(self, caplog: Any) -> None:
        """缺 year 时跳过并 warning —— 不得静默什么都不做。"""
        handler = _standard_changed_notes_handler()
        svc = SimpleNamespace(execute_conversion=AsyncMock())
        with _patch_service(svc), caplog.at_level(logging.WARNING):
            await handler(_payload(PROJECT, None, "listed"))
        assert svc.execute_conversion.await_count == 0
        assert "year" in caplog.text

    @pytest.mark.asyncio
    async def test_non_soe_listed_entity_type_is_skipped(self) -> None:
        handler = _standard_changed_notes_handler()
        svc = SimpleNamespace(execute_conversion=AsyncMock())
        with _patch_service(svc):
            await handler(_payload(PROJECT, YEAR, "private"))
        assert svc.execute_conversion.await_count == 0

    # -- 源码层（AST 形态判据）-------------------------------------------

    def test_scan_surface_is_non_empty(self) -> None:
        node = _handler_node()
        assert len(node.body) > 5, "handler 体过短，判据可能指错了函数"  # type: ignore[attr-defined]

    def test_handler_keeps_execute_conversion_result(self) -> None:
        """改造前这里丢弃了返回值 ⇒ snapshot_id 从未落日志。"""
        assert _assigns_call_containing(
            _handler_node(), "result", "execute_conversion"
        ), (
            "handler 没有把 execute_conversion 的返回值接住 -- "
            "snapshot_id 无从落日志（Requirement 9.4）"
        )

    def test_success_branch_logs_snapshot_id(self) -> None:
        assert _log_call_carries(
            _handler_node(),
            "info",
            "snapshot_id=%s",
            _expr("result.get('snapshot_id')"),
        ), "成功分支的 logger.info 未带 result.get('snapshot_id')"

    def test_failure_branch_logs_snapshot_id_from_exception(self) -> None:
        handlers = [
            h for h in ast.walk(_handler_node()) if isinstance(h, ast.ExceptHandler)
        ]
        assert handlers, "handler 无 except 分支"
        assert any(
            _assigns_from(
                h, "snapshot_id", _expr("getattr(e, 'conversion_snapshot_id', None)")
            )
            for h in handlers
        ), "失败分支未从异常上取 conversion_snapshot_id"
        assert any(
            _log_call_carries(h, "error", "snapshot_id=%s", "snapshot_id")
            for h in handlers
        ), "失败分支的 logger.error 未带 snapshot_id"

    def test_execute_conversion_attaches_snapshot_id_to_exception(self) -> None:
        """异常路径的线索由 ``execute_conversion`` 挂在异常上（handler 才读得到）。"""
        node = _service_method_node("execute_conversion")
        marked = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and ast.unparse(sub.func) == "setattr":
                if len(sub.args) >= 2 and isinstance(sub.args[1], ast.Constant):
                    marked.add(str(sub.args[1].value))
        assert "conversion_snapshot_id" in marked
        assert "conversion_committed" in marked

    def test_ast_judgement_is_not_vacuous(self) -> None:
        """🔴 反向自检：用「好/坏」两个替身证明 AST 判据不是恒真。

        ``bad`` 复现改造前的写法（丢弃返回值 + 日志不带 snapshot_id）。
        """
        good = ast.parse(
            "async def h():\n"
            "    result = await svc.execute_conversion(p, y, t)\n"
            "    logger.info('done snapshot_id=%s', result.get('snapshot_id'))\n"
        )
        bad = ast.parse(
            "async def h():\n"
            "    await svc.execute_conversion(p, y, t)\n"
            "    logger.info('done')\n"
        )
        marker, form = "snapshot_id=%s", _expr("result.get('snapshot_id')")
        assert _log_call_carries(good, "info", marker, form) is True
        assert _log_call_carries(bad, "info", marker, form) is False
        assert _assigns_call_containing(good, "result", "execute_conversion") is True
        assert _assigns_call_containing(bad, "result", "execute_conversion") is False

    def test_expr_helper_is_derived_not_hand_written(self) -> None:
        """``_expr`` 必须由 ``ast.unparse`` 派生 —— 手写双引号形态恒不相等。"""
        assert _expr('result.get("snapshot_id")') == "result.get('snapshot_id')"
        assert _expr('result.get("snapshot_id")') != 'result.get("snapshot_id")', (
            "ast.unparse 未做引号规范化 -- 手写形态比对的风险说明已过期，请复核判据"
        )

    def test_execute_conversion_returns_snapshot_id_key(self) -> None:
        """契约：``execute_conversion`` 的成功返回必须带 ``snapshot_id``。

        handler 记的就是这个键；键名一改（或不再返回）日志里就只剩 ``None``。
        """
        src = _code_level_source(
            inspect.getsource(NoteConversionService.execute_conversion)
        )
        assert '"snapshot_id"' in src, "execute_conversion 不再返回 snapshot_id 键"

    # -- 端到端：正向回传的 snapshot_id 就是回滚用的那一行 ------------------

    @pytest.mark.asyncio
    async def test_snapshot_id_from_execute_is_usable_for_rollback(
        self, fx: _Fx
    ) -> None:
        sess = ConversionSession(build_notes(fx))
        forward = await _forward(sess)
        rolled = await _rollback(sess)

        assert forward["snapshot_id"], "正向未回传 snapshot_id"
        UUID(str(forward["snapshot_id"]))  # 必须是可解析 uuid，不是字面量 'None'
        assert str(sess.chain_rows[-1].id) == forward["snapshot_id"]
        assert rolled["snapshot_id"] == forward["snapshot_id"], (
            f"回滚用的快照 {rolled['snapshot_id']} 与正向回传的 "
            f"{forward['snapshot_id']} 不是同一行"
        )
        assert rolled["snapshot_version"] == SNAPSHOT_FORMAT_VERSION
        # Requirement 4.1 的连带：mapped_notes 是实际改写数（不是存量 count(*)）
        assert forward["mapped_notes"] == forward["notes_detail"]["mapped"]

    @pytest.mark.asyncio
    async def test_failed_conversion_exception_carries_snapshot_id(
        self, fx: _Fx
    ) -> None:
        """行为面：失败路径把 snapshot_id 挂到异常上，并标明未提交。"""
        sess = ConversionSession(build_notes(fx))
        svc = NoteConversionService(sess)
        with patch.object(
            svc, "_map_disclosure_notes", AsyncMock(side_effect=RuntimeError("boom"))
        ), patch_chain_refresh(), pytest.raises(RuntimeError) as exc_info:
            await svc.execute_conversion(PROJECT, YEAR, "listed")

        exc = exc_info.value
        assert getattr(exc, "conversion_snapshot_id", None), "异常未带 snapshot_id"
        UUID(str(getattr(exc, "conversion_snapshot_id")))
        assert getattr(exc, "conversion_committed", None) is False
        assert sess.committed is False, "失败路径不该 commit"


# ===========================================================================
# 补齐段（2026-08-08）—— 两个并发会话产出合并后的**语义缺口**
# ===========================================================================
#
# 上方 51 例已覆盖 Property 31/32/33 的主干（预览零写入 / 往返五项回到初始 /
# 自动触发留快照）。本段只补「另一版有、这一版没有」的判据，逐条对应生产里
# **已实现但无人断言**的分支 —— 它们全是 fail-closed 路径，一旦静默失效就变成
# 「回滚报成功而实际没回退干净」，正是 Requirement 9.3 要消除的假成功形态。
#
# 缺口来源 = code-level 命中数比对（剥注释/docstring 后，生产有该符号而守卫 0 命中）：
#
# ============================================  =======  =====  ==============
# 符号 / 分支                                   service  guard  本段补齐
# ============================================  =======  =====  ==============
# ``ROLLBACK_SKIP_NOTE_MISSING``                      2      0  ✅
# ``ROLLBACK_FAIL_NUMBER_BLOCKED``                    2      0  ✅
# ``format_adapted_not_reversible``                   1      0  ✅
# ``count_manual_cells``（往返不减少）                 5      0  ✅
# ``user_edits_dropped``（恒 0 的平台红线）            8      0  ✅
# 快照过期 / ``snapshot_before`` 为空两条 error        2      0  ✅
# 回填出来的 sid 退回 ``None``                        14      0  ✅
# 预览第 3 层 leftover 核验**真会触发**                 1      0  ✅
# ``details`` 可追溯键 + ``forbidden_hits`` 可读       —      —  ✅
# ============================================  =======  =====  ==============
#
# 一律**加法式**：不改上方任何断言、不重造替身与判据数据（同一替身两份实现即双真源）。
# 本段的 import 刻意就近放置而不并入文件顶部 —— 保持与并发会话的改动零重叠。
from datetime import datetime, timedelta, timezone  # noqa: E402

from app.services.note_conversion_service import (  # noqa: E402
    ROLLBACK_FAIL_NUMBER_BLOCKED,
    ROLLBACK_SKIP_NOTE_MISSING,
    count_manual_cells,
)


class TestProperty31_PreviewTraceabilityAndLeftoverGuard:
    """预览响应的**可追溯性**与第 3 层零写入核验的**可触发性**。

    Validates: Requirements 9.1, 9.2

    上方 :class:`TestProperty31_PreviewHasNoWrites` 断言的是「预览没写库」与
    「计数等于真实执行」；本类补两件它没问的事：

    1. 预览除了给四个数，还得让审计师能逐条核对**为什么这一章没被改写**
       （``details`` 的 skipped / failed / 别名桥接 / 禁止对 / 回填冲突）——
       否则预览只是一句「将改写 112 个」，审计师无从判断该不该切换；
    2. 生产的第 3 层 leftover 核验（``db.new`` / ``dirty`` / ``deleted`` 非空即
       记 ERROR 并整体 ``db.rollback()``）**是否真的会触发**。上方只断言了它
       「不该被触发」，而「永远不触发」与「压根不工作」在那条判据下**不可区分**。
    """

    @pytest.mark.asyncio
    async def test_preview_details_carry_traceability(self, fx: _Fx) -> None:
        """``details`` 必须带齐可追溯键，且计数与明细自洽。"""
        sess = ConversionSession(build_notes(fx))
        payload = await NoteConversionService(sess).preview_note_conversion(
            PROJECT, YEAR, "listed"
        )
        details = payload["details"]

        required = {
            "format_adapted",
            "binding_ids_rewritten",
            "sid_backfilled",
            "sid_backfill_conflicts",
            "user_edits_dropped",
            "skipped_count",
            "skipped_reasons",
            "skipped",
            "failed_count",
            "failed",
            "bridged_by_alias",
            "forbidden_pairs",
            "pending_keys",
        }
        missing = required - set(details)
        assert not missing, f"预览 details 缺可追溯键：{sorted(missing)}"

        # 计数与明细自洽（只给数不给明细 = 审计师无从核对）
        # 🔴 本场景实测 skipped/failed 均为空（章节全部可处理，实测
        # mapped=2 / archived=1 / created=65 / skipped=0）⇒ 这两条在此数据下是
        # **恒真**的，不能作为「计数由明细派生」的判据。真判据在
        # :meth:`test_details_counts_are_derived_from_the_lists`（用非空明细直调
        # 投影纯函数）—— 变异「把 skipped_count 写死 0」正是被那条打红的。
        assert details["skipped_count"] == len(details["skipped"])
        assert details["failed_count"] == len(details["failed"])
        for item in details["skipped"]:
            assert item.get("reason"), f"skipped 条目缺 reason：{item}"

        # 🔴 平台红线：人工编辑不得在章节改写中丢失
        assert details["user_edits_dropped"] == 0, (
            f"预览显示会丢失 {details['user_edits_dropped']} 个人工编辑单元格 "
            "-- 违反 Requirement 2.5"
        )

        # 判据自检（真实数据锚点）：本场景确实走过 binding_id 前缀改写、别名桥接与
        # 禁止对，否则上面几条等于空转。实测 binding 3 / 别名 5 / 禁止对 1。
        assert details["binding_ids_rewritten"] > 0, (
            "本场景 binding_id 一条都没改写 -- details 判据空转"
            "（build_notes 的 pair0 应带 binding 且两侧章节号不同）"
        )
        assert details["bridged_by_alias"], (
            "别名桥接明细为空 -- 真实 diff 的 bridged 应有 5 条，可追溯性判据空转"
        )
        assert details["forbidden_pairs"], (
            "禁止匹配对明细为空 -- 真实 diff 应含合并章↔母公司章那一对"
        )
        assert payload["forbidden_hits"], "顶层 forbidden_hits 为空但 details 里有条目"

    def test_details_counts_are_derived_from_the_lists(self) -> None:
        """``skipped_count`` / ``failed_count`` 必须由明细**派生**，不得写死。

        🔴 本条是上一条的**非空转补强**：真实预览场景下 ``skipped`` / ``failed``
        实测均为空（章节全部可处理），此时 ``0 == len([])`` 恒成立 ⇒ 上一条对
        「计数写死」这类改动**不敏感**（变异检验实测 GREEN，属守卫缺陷）。
        故这里改用非空明细直接调投影**纯函数**，让计数与明细脱钩即打红。
        """
        payload = NoteConversionService._build_note_preview_payload(
            "soe",
            "listed",
            {
                "skipped": [
                    {"reason": "target_sid_occupied", "note_id": "n1"},
                    {"reason": "sid_unresolved", "note_id": "n2"},
                ],
                "failed": [{"phase": "restore_note", "note_id": "n3"}],
                "skipped_reasons": {"target_sid_occupied": 1, "sid_unresolved": 1},
                "forbidden_hits": [],
            },
        )
        details = payload["details"]
        assert details["skipped_count"] == 2, (
            f"skipped_count 未由明细派生：{details['skipped_count']} != 2"
        )
        assert details["failed_count"] == 1, (
            f"failed_count 未由明细派生：{details['failed_count']} != 1"
        )
        assert len(details["skipped"]) == 2, "skipped 明细未原样透传"
        assert len(details["failed"]) == 1, "failed 明细未原样透传"
        assert sum(details["skipped_reasons"].values()) == details["skipped_count"], (
            "skipped_reasons 分布与 skipped_count 不等 -- 分布统计漏项"
        )

    def test_forbidden_hits_are_human_readable(self, fx: _Fx) -> None:
        """``forbidden_hits`` 面向审计师必须是可读句子，结构化条目留在 ``details``。

        「故意不配对」是需要人来复核的判断（典型为合并章 ↔ 母公司章），把原始
        dict 丢给前端等于不可读；而结构化条目仍需保留在 ``details.forbidden_pairs``
        以便机器核对。两处形态不同是有意的，故双向断言。
        """
        hit = {
            "source_side": "soe",
            "source_title": "财务报表主要项目注释",
            "source_section_id": "sid-soe-x",
            "target_side": "listed",
            "target_title": "母公司财务报表主要项目注释",
            "target_section_id": "sid-listed-y",
        }
        line = NoteConversionService._format_forbidden_hit(hit)
        assert isinstance(line, str)
        for token in (
            "财务报表主要项目注释",
            "母公司财务报表主要项目注释",
            "sid-soe-x",
            "sid-listed-y",
        ):
            assert token in line, f"禁止对展示串缺少 {token} -- 无从追溯是哪两章"

        payload = NoteConversionService._build_note_preview_payload(
            "soe",
            "listed",
            {"forbidden_hits": [hit], "skipped": [], "failed": []},
        )
        assert payload["forbidden_hits"] == [line], "顶层 forbidden_hits 不是可读串"
        assert payload["details"]["forbidden_pairs"] == [hit], (
            "details 未保留结构化禁止对条目 -- 机器无从核对"
        )

    @pytest.mark.asyncio
    async def test_leftover_guard_fires_and_rolls_back_whole_session(
        self, fx: _Fx, caplog: pytest.LogCaptureFixture
    ) -> None:
        """🔴 反向自检：真留下待写对象时，第 3 层核验必须记 ERROR 并整体回滚。

        构造「映射函数绕过 savepoint 留下待写对象」—— 这正是该核验存在的理由
        （防将来有人在映射里直接写库）。上方
        :meth:`TestProperty31_PreviewHasNoWrites.test_preview_leaves_no_pending_write_objects`
        只断言它**不该**被触发，那条判据在「核验压根不工作」时同样通过。
        """
        sess = ConversionSession(build_notes(fx))
        svc = NoteConversionService(sess)

        async def _leaky(
            project_id: Any, year: int, current_type: str, target_type: str
        ) -> dict[str, Any]:
            # 只 add 不 flush ⇒ savepoint 回滚后 session 仍持有待写对象
            sess.add(
                make_note(
                    section_id="leak-sid",
                    note_section="漏写章节",
                    section_title="绕过 savepoint 的写入",
                )
            )
            return {
                "mapped": 0,
                "archived": 0,
                "created": 0,
                "user_edits_preserved": 0,
                "forbidden_hits": [],
                "skipped": [],
                "failed": [],
            }

        with patch.object(svc, "_map_disclosure_notes", _leaky), caplog.at_level(
            logging.ERROR
        ):
            payload = await svc.preview_note_conversion(PROJECT, YEAR, "listed")

        assert sess.session_rollbacks == 1, (
            "留下待写对象后生产没有整体 db.rollback() -- 第 3 层核验形同虚设"
        )
        assert any(
            record.levelno >= logging.ERROR and "待写对象" in record.getMessage()
            for record in caplog.records
        ), f"未记 ERROR 说明残留待写对象：{[r.getMessage() for r in caplog.records]}"
        assert payload["status"] == "preview", "兜底回滚后仍应返回预览响应"


class TestProperty32_RollbackFailClosedPaths:
    """回滚的 fail-closed 分支 —— 「回不去」必须如实上报，禁半成品与假成功。

    Validates: Requirements 9.3

    上方 :class:`TestProperty32_RollbackRoundtrip` 走的是**顺利路径**（往返回到
    初始）。生产另有五条「回不去」的分支，它们的共同纪律是
    **complete=False + status='partial'（或 error）+ 逐条说明**：

    ==================================  =========================================
    ``ROLLBACK_SKIP_NOTE_MISSING``      快照里有、库里已被别的流程物理删除
    ``ROLLBACK_FAIL_NUMBER_BLOCKED``    目标章节号被本次回滚无权移动的记录占着
                                        => **整章不动**（禁「sid 退了、章节号没退」）
    ``format_adapted_not_reversible``   正向做过格式适配（改列结构，不可逆）
    快照过期（> 保留期）                 error，且一行都不改
    ``snapshot_before`` 为空             error，且一行都不改
    ==================================  =========================================

    这些分支只要静默失效，回滚就会报「成功」而数据仍停在目标变体的章节位置上 ——
    比不回滚更坏（审计师以为已经退回去了）。
    """

    @pytest.mark.asyncio
    async def test_missing_snapshot_note_is_reported_not_ignored(
        self, fx: _Fx
    ) -> None:
        """快照里的章节在库中已不存在 ⇒ 进 ``skipped`` + 降级，而非静默忽略。"""
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        await _forward(sess)

        victim = notes[1]
        sess.notes = [n for n in sess.notes if n is not victim]

        rolled = await _rollback(sess)

        assert rolled["status"] == "partial", (
            "快照章节已不存在而回滚仍报完全成功 -- 假成功"
        )
        sections = rolled["sections"]
        assert sections["complete"] is False
        entries = [
            i for i in sections["skipped"] if i["reason"] == ROLLBACK_SKIP_NOTE_MISSING
        ]
        assert entries, (
            f"未登记「快照章节已不存在」原因码："
            f"{ {i['reason'] for i in sections['skipped']} }"
        )
        assert str(victim.id) in {i["note_id"] for i in entries}, (
            "skipped 条目未带 note_id -- 无从追溯是哪一章丢了"
        )
        # 一条缺失不该让其余章节放弃回退（与正向的逐章隔离同一纪律）
        assert sections["restored"] > 0, "因一条缺失而整体放弃回退 -- 隔离失效"

    @pytest.mark.asyncio
    async def test_blocked_note_section_is_not_half_rolled_back(
        self, fx: _Fx
    ) -> None:
        """目标章节号被外来记录占着 ⇒ 该章**整体不动** + 进 ``failed``。

        🔴 判据的关键是「整章不动」而不只是「进了 failed」：若实现先改
        ``section_id`` 再撞章节号唯一约束，就会留下「sid 退了、章节号没退」的半
        成品状态 —— 那比不回退更难修（两个列指向不同变体）。
        """
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        await _forward(sess)

        blocked = notes[0]
        state_after_forward = note_state(blocked)
        # 外来记录（不在快照里、无 created_by_conversion lineage）占住它要退回的章节号
        squatter = make_note(
            section_id="foreign-sid",
            note_section=fx.c0["src_num"],
            section_title="别的流程建的章节",
        )
        sess.notes.append(squatter)

        rolled = await _rollback(sess)

        sections = rolled["sections"]
        assert rolled["status"] == "partial"
        assert sections["complete"] is False
        blocked_fails = [
            f for f in sections["failed"] if f.get("error") == ROLLBACK_FAIL_NUMBER_BLOCKED
        ]
        assert blocked_fails, (
            f"章节号被占却未登记 {ROLLBACK_FAIL_NUMBER_BLOCKED}："
            f"{[f.get('error') for f in sections['failed']]}"
        )
        assert str(blocked.id) in {f["note_id"] for f in blocked_fails}

        assert note_state(blocked) == state_after_forward, (
            "被阻塞的章节被部分回退了（半成品状态）-- section_id 与 note_section 必须同进同退"
        )
        assert squatter in sess.notes, "外来记录被本次回滚动了 -- 越权"
        assert sections["foreign_notes"] >= 1, "未把外来记录计入 foreign_notes"

    @pytest.mark.asyncio
    async def test_format_adapted_is_declared_irreversible(self, fx: _Fx) -> None:
        """正向做过格式适配 ⇒ 回滚如实声明不可逆并降级，但其余字段仍照退。

        真实数据里 ``field_mapping`` 实测 39/39 全 null ⇒ ``format_adapted`` 恒 0，
        该分支在真实数据上不可达。故直接改写快照行的正向摘要（生产回滚正是从
        ``chain_executions.steps.conversion_forward.format_adapted`` 读它）。
        """
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        before = states_by_id(notes)
        await _forward(sess)

        row = sess.chain_rows[-1]
        forward_summary = dict((row.steps or {}).get("conversion_forward") or {})
        assert forward_summary, "正向摘要没写进快照 steps -- 本条判据的前提不成立"
        assert int(forward_summary.get("format_adapted") or 0) == 0, (
            "真实数据下 format_adapted 竟非 0 -- 请复核 field_mapping 是否已非 null"
        )
        forward_summary["format_adapted"] = 3
        row.steps = {**(row.steps or {}), "conversion_forward": forward_summary}

        rolled = await _rollback(sess)

        sections = rolled["sections"]
        assert sections["format_adapted_not_reversible"] == 3
        assert sections["complete"] is False
        assert rolled["status"] == "partial", (
            "做过不可逆格式适配却报完全成功 -- 假成功"
        )
        assert any("不可逆" in w for w in sections["warnings"]), (
            f"未说明哪一项不可逆：{sections['warnings']}"
        )
        # 不可逆项只降级 status，不该阻断其余字段回退
        assert sections["restored"] > 0
        for nid, initial in before.items():
            assert states_by_id(notes)[nid]["section_id"] == initial["section_id"], (
                f"note {nid} 的 section_id 因不可逆项而未回退 -- 降级不等于放弃"
            )

    @pytest.mark.asyncio
    async def test_manual_cells_never_decrease_across_roundtrip(
        self, fx: _Fx
    ) -> None:
        """人工编辑单元格数在「正向」与「往返」后都不得减少（平台红线）。

        判据用生产的 :func:`count_manual_cells`（按 ``manual`` **值**计数，两种建键
        形态都成立）；它同时是生产上报 ``user_edits_preserved`` /
        ``user_edits_dropped`` 的依据 ⇒ 这里既验数据、又验上报口径一致。
        """
        notes = build_notes(fx)
        baseline = {str(n.id): count_manual_cells(n.table_data) for n in notes}
        total = sum(baseline.values())
        assert total > 0, "本场景没有 manual 单元格 -- 该判据空转"

        sess = ConversionSession(notes)
        forward = await _forward(sess)

        detail = forward["notes_detail"]
        assert detail["user_edits_dropped"] == 0, (
            f"正向改写丢失了 {detail['user_edits_dropped']} 个人工编辑单元格 "
            "-- 违反 Requirement 2.5"
        )
        assert detail["user_edits_preserved"] > 0, (
            "user_edits_preserved 为 0 -- 上报口径失效（本场景确有 manual 单元格）"
        )
        after_forward = {str(n.id): count_manual_cells(n.table_data) for n in notes}
        for nid, count in baseline.items():
            assert after_forward[nid] >= count, (
                f"note {nid} 正向后 manual 单元格由 {count} 减少到 {after_forward[nid]}"
            )

        await _rollback(sess)

        after_rollback = {str(n.id): count_manual_cells(n.table_data) for n in notes}
        assert after_rollback == baseline, (
            f"往返后 manual 单元格数漂移：{after_rollback} != {baseline}"
        )

    @pytest.mark.asyncio
    async def test_expired_snapshot_reports_error_and_changes_nothing(
        self, fx: _Fx
    ) -> None:
        """快照超出保留期 ⇒ 报 error 且**一行都不改**（含 ``template_type``）。"""
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        await _forward(sess)
        after_forward = states_by_id(notes)

        row = sess.chain_rows[-1]
        row.started_at = datetime.now(timezone.utc) - timedelta(
            days=NoteConversionService.SNAPSHOT_RETENTION_DAYS + 1
        )

        rolled = await _rollback(sess)

        assert rolled["status"] == "error", "过期快照下回滚竟未报 error"
        assert "expired" in rolled["message"].lower(), rolled["message"]
        assert "sections" not in rolled, "过期快照下竟给出章节回退结果"
        assert states_by_id(notes) == after_forward, "过期快照下仍改动了章节状态"
        assert sess.project.template_type == "listed", (
            "过期快照下仍改了 template_type -- 会触发全链重算"
        )

    @pytest.mark.asyncio
    async def test_empty_snapshot_reports_error_and_changes_nothing(
        self, fx: _Fx
    ) -> None:
        """``snapshot_before`` 为空 ⇒ 报 error 且一行都不改。

        与「旧格式快照」（有 ``template_type`` 但无 ``notes``，走 partial）是**两条
        不同分支**：这里连 ``template_type`` 都无从得知，故只能整体拒绝。
        """
        notes = build_notes(fx)
        sess = ConversionSession(notes)
        await _forward(sess)
        after_forward = states_by_id(notes)

        sess.chain_rows[-1].snapshot_before = None

        rolled = await _rollback(sess)

        assert rolled["status"] == "error"
        assert "empty" in rolled["message"].lower(), rolled["message"]
        assert states_by_id(notes) == after_forward
        assert sess.project.template_type == "listed"

    @pytest.mark.asyncio
    async def test_backfilled_sid_returns_to_null_after_rollback(
        self, fx: _Fx
    ) -> None:
        """回填出来的 ``section_id`` 必须退回 ``None``（Requirement 2.8 的往返侧）。

        存量 note 的 ``section_id`` 大面积为 NULL，正向会按
        ``note_section`` + ``section_title`` 回填后参与映射 ⇒ 回滚必须把它退回
        ``None``，否则往返之后凭空多出一个 sid（而它并非审计师录入的数据）。
        朴素实现（「只把 sid 改回源侧取值」）在这里会留下回填值。
        """
        note = make_note(
            section_id=None,
            note_section=fx.c2["src_num"],
            section_title=fx.c2["title"],
            table_data=binding_table_data(fx.c2["src_num"]),
        )
        sess = ConversionSession([note])

        forward = await _forward(sess)

        assert forward["notes_detail"]["sid_backfilled"] >= 1, (
            "NULL sid 未被回填 -- 本条判据的前提不成立（请复核 fx.c2 的回填键唯一性）"
        )
        assert note.section_id == fx.c2["tgt_sid"], (
            f"回填后未改写到目标 sid：{note.section_id!r}"
        )
        assert note.note_section == fx.c2["tgt_num"]

        rolled = await _rollback(sess)

        assert rolled["status"] == "rolled_back", (
            f"回滚未报完全成功：{rolled.get('sections')}"
        )
        assert note.section_id is None, (
            f"回填出来的 sid 未退回 None：{note.section_id!r} "
            "-- 往返后凭空多出一个 sid"
        )
        assert note.note_section == fx.c2["src_num"]
        assert note.template_lineage is None, (
            f"lineage 未整体退回 None：{note.template_lineage!r}"
        )
        assert collect_binding_prefixes(note.table_data) == {fx.c2["src_num"]}, (
            "binding_id 前缀未退回源侧章节号"
        )
