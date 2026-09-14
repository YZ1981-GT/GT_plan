"""test_x3_keyfamily_property —— 判据层（常量 / 登记表 / fixture / 纯函数 / 取证 helper）。

从 `backend/tests/test_x3_keyfamily_property.py` 拆出：原文件 1586 行 > pre-commit 的 800 行门禁。
**不加 file_size_whitelist** —— 白名单表头写明「仅历史大文件」，新增文件
套用属滥用。

刻意与用例文件**同目录**：判据里的 `Path(__file__).parents[N]` 路径推算
移到子目录会整体错一层（实测过，会变成 fixture setup 全 ERROR）。

用例层的 import 清单由拆分脚本按其**实际引用**算出，不手写 —— 漏一个名字
就是 collection error，会让整份守卫的断言零执行而表面上「没有失败」。

原文件 docstring 原样保留在下方。

Feature: x3-adjustment-entry-import-export, Property 2: 族键爆炸与归约保行数、无幽灵残留

*For any* X-3 分录列表与任意目标行数 ``n``（含 ``n = 0`` 与 ``n <`` 库中现有行数），按该
sheet 的 ``key_family`` 执行「族键爆炸 → 落库 → 族键归约」后，界面读路径读回的行数恰为
``n``，且不存在索引大于 ``n`` 的残留键。

**Validates: Requirements 2.5, 6.5, 6.6, 11.7**

═══════════════════════════════════════════════════════════════════════════════
判据落在**库态**，不是返回值
═══════════════════════════════════════════════════════════════════════════════

``write_rows`` 自报 ``ImportOutcome(written_count, written_item_ids, removed_item_ids,
warnings)``。只断言这些字段等于复述实现自己的说法：一次「算出了要删哪些键、却把别的键
删了」的实现照样能让 ``removed_item_ids`` 好看。故本文件的每条属性都同时判两侧：

* **库态** —— ``checklist_responses`` 里该 sheet 的族键集合、别的 sheet / 别的底稿的行、
  以及整表快照（``SELECT`` 全部 10 列，含 ``created_at`` / ``updated_at``）。
* **界面读路径** —— 生产函数 ``load_rows``（按 ``spec.read_family``；``NONE`` 回落写入族）。
  「读回行数恰为 n」这句话的量化对象是它，不是「库里有多少键」—— 两者的差正是幽灵行。

``NOW()`` 在夹具里被换成**单调递增**的替身 ⇒ 一次「值相同的幂等 upsert」也会让
``updated_at`` 前移，同样落进快照差。作用域判据因此比「值有没有变」更严。

═══════════════════════════════════════════════════════════════════════════════
与既有判据的分工（本文件不抄第二份）
═══════════════════════════════════════════════════════════════════════════════

| 面 | 既有归属 | 本文件（Property 2） |
|---|---|---|
| ``_should_purge_residual`` 的**纯函数真值表**（∀ sheet × ∀ 策略） | GS1 ``test_x3_key_ledger.TestResidualPurgeScope.test_purge_only_under_overwrite`` | 不重复 |
| ``_residual_item_ids`` 的**纯函数**清理面（排除表级独立键 / 排除保留行 / 不越出库存键集） | GS1 同类 ``test_residual_scope_excludes_standalone_and_kept_rows`` | 不重复 |
| ``write_rows`` 体内**是否调用**了 ``_should_purge_residual``（AST 层） | GS1 ``test_write_rows_delegates_purge_decision`` | 不重复 |
| 委派点剥 ``Query`` 包装后 ``strategy`` 是真 ``str`` | GS6 ``test_x3_legacy_sheet_param`` | 不重复 |
| 列面 / sheet 名对齐源模板 | GS2 + Property 3 | 不用（本文件不产出 workbook，除一条端点锚点） |
| 列序无关解析 / 身份不符零写入 | Property 4 ``test_x3_parse_property`` | 不重复（那边判「有没有写」，这边判「写完库里剩什么」） |
| **∀ n 下界面读回行数 == n（含 n=0 / n<现有行数）** | 无 | **本文件 P2-1 / P2-5** |
| **落库族键集合恰等于「爆炸集」（无残留、无空洞、pfd 两族都写、``ociBlock`` 不丢）** | 无 | **本文件 P2-2** |
| **清理在库态上只发生于 ``overwrite``**（纯函数返对但结果被忽略 ⇒ 仍打红） | 无 | **本文件 P2-3** |
| **清理作用域由 ``(wp_id, 族前缀)`` 双重限定**（别的底稿 / 别的 sheet / 表级独立键零改动） | 无 | **本文件 P2-4** |

🔴 GS1 的三条是**纯函数 + AST**判据，抓不到三类形态，而这三类都是删用户数据：
① ``_delete_many`` 丢掉 ``wp_id`` 过滤（越界删别的底稿）② ``write_rows`` 把门控结果算了
但不用（``fill-empty`` 照样清）③ 归约通路整条断掉（``_delete_many`` 早退 ⇒ 幽灵行常驻）。
本轮变异检验对这三条各有 witness（见 tasks.md 实录）。

═══════════════════════════════════════════════════════════════════════════════
零硬编码：作业面 / 键面 / 策略取值面全部从真源装载
═══════════════════════════════════════════════════════════════════════════════

本文件不写任何 X-3 键 / 列头 / 后缀 / sheet 名 / 短前缀字面量：

* 作业面 = ``backend/data/adjustment_ie_contract.json`` 里登记了 ``key_family`` 的条目
  （与实现 ``_select_x3_entries`` 同一口径），并与 ``X3_SHEET_SPECS`` 键集双向锁死。
* **族键一律由生产函数拼**：``single_json_item_id`` / ``per_field_item_id`` /
  ``data_item_id``。测试侧不复制第二份拼接式子 —— 复制一份的话，「前缀写死成
  ``{X}-{X}-3-entry-`` 公式」这类分叉会在两侧同时错、判据反而恒绿。
* 后缀集 / 前缀 / 落库列 / 表级独立键 / entryType 字段与大小写：取 ``spec`` 字段与
  生产函数 ``_entry_type_literal``；「类别」→ entryType 的枚举面取
  ``CATEGORY_TO_ENTRY_TYPE``。
* **冲突策略取值面取自 ``ConflictStrategy`` 这个 ``Literal`` 的 ``get_args``**（GS1 那边
  写的是三元组字面量；此处改从类型真源取，一旦平台加第四种策略本文件立刻覆盖到它）。
* 列面（仅端点锚点构造上传文件时用）= 实现由清单 ``column_map`` 派生的 ``COLUMN_ORDER``。

═══════════════════════════════════════════════════════════════════════════════
🔴 四条施工期实测（写在这里免得下一轮再踩）
═══════════════════════════════════════════════════════════════════════════════

1. **「库中现有行数」对三族不是同一个量**。逐字段族与整行 JSON 族的读回是「从 1 连续取到
   断档为止」⇒ 库里存着行号 ``{1, 3, 5}`` 时读回只有 **1** 行；整表单键 JSON 族没有行号
   概念，读回 = 数组长度 = **3**。故「``n <`` 库中现有行数」这个边界必须以 ``load_rows``
   的实测返回值为基准（本文件 ``_expected_seed_readback`` 就按族分别推），
   而不是按「预置了几行」想当然。有空洞的种子由 ``seed_kind="sparse"`` 一维专门覆盖。

2. **整表单键 JSON 族的「无幽灵残留」不能判键集**：它永远只有一个键，
   ``_should_purge_residual`` 对它恒为 ``False``（实测 5 张全 ``removed_item_ids == ()``）。
   幽灵行在这一族的形态是**数组里多出的元素** ⇒ 判据改成「``json.loads(库值)`` 的长度
   恰为 ``n``」。若照抄逐字段族的「键集 == 爆炸集」，这 5 张会得到一条恒真判据。

3. **``reject`` + ``n = 0`` 在两族上分叉，但两边都是零写入**：逐字段族此时 ``incoming``
   为空 ⇒ ``_resolve_reject`` 找不到冲突键、**不抛**，``removed`` 也是空（门控挡住）⇒
   库态不变；整表单键族的 ``incoming`` 总含那唯一一个键、库里又非空 ⇒ **抛**
   ``ConflictRejected``。故 P2-3 的 ``reject`` 判据写成「**抛与不抛都要求库态逐行逐列
   不变**」，并把两个分支各自的命中数自证出来 —— 只断言「必抛」会在 11 张上直接假红。

4. **表级独立键不落在族前缀内**（实测 3 张有独立键：2 张 ``M`` 族 + 1 张 ``N`` 族，其键
   形如「…-adjustment-note」/「…-audit-conclusion」，与族前缀「…-entry-」分叉在前缀段）
   ⇒ ``_residual_item_ids`` 里那句 ``if item_id in standalone: continue`` 在真实清单下
   **是不可达的防御分支**。本文件如实把它记在这里，并仍在 P2-4 里断言独立键零改动
   （断言的价值在于「前缀一旦被改成更宽的形态就立刻打红」，不在于覆盖那句 ``continue``）。
   ⚠️ 不要据此删掉那句防御 —— 它的成本是零，而清单前缀是会被改的。
"""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple, get_args

import pytest
import sqlalchemy as sa
from fastapi import APIRouter, FastAPI
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.routers.wp_render_strategies import _x3_adjustment_import_export as impl

_REPO = Path(__file__).resolve().parents[2]
_CONTRACT = _REPO / "backend" / "data" / "adjustment_ie_contract.json"

#: 每条属性的迭代次数（任务要求 ≥100）。每次迭代内循环遍历 16 张 ⇒ 「∀ sheet × ∀ 行数」
#: 两维同迭代覆盖。实测单次迭代（16 张各一轮预置 + 写 + 两次读回 + 键查询）≈ 87 ms。
_RUNS = 100

#: 预置行号的上界。``ROW_LIMIT`` 是 500，取 6 足够跨越 ``n`` 的全部相对位置
#: （``n < k`` / ``n == k`` / ``n > k``）且让单次迭代成本留在毫秒级。
_MAX_SEED = 6
_MAX_ROWS = 6

#: 探针记号 —— 真实清单取值与真实 sheet 名里都不会出现（由反向自检钉住）。
_MARK = "‡族键探针"

_SETTINGS = settings(
    max_examples=_RUNS,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 真源装载（清单 → 作业面；实现 → 键面 / 列面；Literal → 策略面）
# ═══════════════════════════════════════════════════════════════════════════


@lru_cache(maxsize=1)
def _contract() -> Mapping[str, Any]:
    assert _CONTRACT.is_file(), f"契约清单缺失：{_CONTRACT}（守卫必须打红而非跳过）"
    doc = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    assert isinstance(doc, Mapping), f"清单顶层不是对象：{type(doc).__name__}"
    return doc


@lru_cache(maxsize=1)
def _codes() -> tuple[str, ...]:
    """作业面 —— 判据 = 条目登记了 ``key_family``（与实现 ``_select_x3_entries`` 同口径）。"""
    sheets = _contract()["sheets"]
    assert isinstance(sheets, Mapping), "清单 `sheets` 段不是对象"
    selected = tuple(
        sorted(
            code
            for code, entry in sheets.items()
            if isinstance(entry, Mapping) and entry.get("key_family")
        )
    )
    assert selected, "清单里没有任何登记了 `key_family` 的条目 ⇒ 作业面为空，属性会恒真"
    return selected


def _spec(code: str) -> Any:
    return impl.sheet_spec(code)


@lru_cache(maxsize=1)
def _face() -> tuple[str, ...]:
    """列面（只作端点锚点构造上传文件用）= 实现由清单 ``column_map`` 派生的列序。"""
    face = tuple(impl.COLUMN_ORDER)
    assert len(face) >= 2, f"列面塌陷成 {face}"
    return face


@lru_cache(maxsize=1)
def _strategies() -> tuple[str, ...]:
    """冲突策略取值面 —— 取自 ``ConflictStrategy`` 这个 ``Literal`` 的类型参数。"""
    from app.services.bulk_tab.single_tab_adapter import ConflictStrategy

    values = tuple(str(v) for v in get_args(ConflictStrategy))
    assert values, "`ConflictStrategy` 取不出取值面（类型形态变了？）"
    assert impl._STRATEGY_OVERWRITE in values, (
        f"实现的 `_STRATEGY_OVERWRITE`={impl._STRATEGY_OVERWRITE!r} 不在平台策略词表 "
        f"{values} 内 ⇒ 门控比对的那个字符串与 bulk 侧传的值分叉，清理永不生效或永远生效"
    )
    return values


@lru_cache(maxsize=1)
def _canonical_entry_types() -> tuple[str, ...]:
    """规范 entryType 取值面 —— 取自派生映射表 ``CATEGORY_TO_ENTRY_TYPE`` 的值域。"""
    values = tuple(sorted(set(impl.CATEGORY_TO_ENTRY_TYPE.values())))
    assert len(values) >= 2, f"entryType 取值面塌陷成 {values}"
    return values


@lru_cache(maxsize=1)
def _prefix_to_codes() -> dict[str, frozenset[str]]:
    """短前缀 → 该前缀的 X-3 码集合 —— 与生产同一式子（按 ``api_prefix`` 反查）。"""
    out: dict[str, set[str]] = {}
    for code in _codes():
        out.setdefault(_spec(code).api_prefix, set()).add(code)
    return {prefix: frozenset(codes) for prefix, codes in out.items()}


# ═══════════════════════════════════════════════════════════════════════════
# 2. 族键面（**一律由生产函数拼**，测试侧不复制第二份拼接式子）
# ═══════════════════════════════════════════════════════════════════════════


def _is_single(spec: Any) -> bool:
    return spec.key_family is impl.KeyFamily.SINGLE_JSON


def _family_prefixes(spec: Any) -> tuple[str, ...]:
    return tuple(p for p in (spec.per_field_prefix, spec.data_key_prefix) if p)


@lru_cache(maxsize=None)
def _keys_for_indices(code: str, indices: tuple[int, ...]) -> frozenset[str]:
    """给定行号集合的**全部**族键（= 族键爆炸的结果集）。

    整表单键族无行号概念 ⇒ 恒为那唯一一个键（行数体现在 JSON 数组长度里，见模块 docstring
    实测 2）。
    """
    spec = _spec(code)
    if _is_single(spec):
        return frozenset({impl.single_json_item_id(spec)})
    keys: set[str] = set()
    for row_no in indices:
        if spec.per_field_prefix is not None:
            for suffix in spec.per_field_suffixes:
                keys.add(impl.per_field_item_id(spec, row_no, suffix))
        if spec.data_key_prefix is not None:
            keys.add(impl.data_item_id(spec, row_no))
    return frozenset(keys)


def _exploded_keys(code: str, n: int) -> frozenset[str]:
    """写入 ``n`` 行后该 sheet **应当**存在的族键集合。"""
    return _keys_for_indices(code, tuple(range(1, n + 1)))


def _belongs(spec: Any, item_id: str) -> bool:
    """该 item_id 是否落在这张 sheet 的**族键空间**内（表级独立键不算 —— 实测 4）。"""
    if _is_single(spec):
        return item_id == impl.single_json_item_id(spec)
    return any(item_id.startswith(p) for p in _family_prefixes(spec))


def _leading_run(indices: Sequence[int]) -> int:
    """从 1 起连续存在的行号个数（= 逐字段族 / 整行 JSON 族的界面读回行数）。"""
    present = set(indices)
    n = 0
    while n + 1 in present:
        n += 1
    return n


def _expected_seed_readback(code: str, indices: Sequence[int]) -> int:
    """预置态下界面读路径**应当**读回的行数（三族分推 —— 见模块 docstring 实测 1）。"""
    return len(indices) if _is_single(_spec(code)) else _leading_run(indices)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 生成器（抽象行与具体 sheet 解耦 ⇒ 同一生成值 materialize 到 16 张各自的字段名）
# ═══════════════════════════════════════════════════════════════════════════

#: 取值 6 类：``None`` / 空串 / 数值（整、浮点、极小）/ 长中文 / 特殊字符 / 普通文本。
#: 全部可 JSON 序列化且为有限值（整表单键族要 ``json.dumps`` 整个数组）。
_arb_cell = st.one_of(
    st.none(),
    st.just(""),
    st.integers(min_value=-10**9, max_value=10**9),
    st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-1e-6, max_value=1e-6, allow_nan=False, allow_infinity=False),
    st.text(alphabet="调整分录科目附注借贷方金额索引备注说明重分类", min_size=1, max_size=80),
    st.text(alphabet="，。（）%&#@!?+-*/_|^$<>[]{}~`'\"\\ \t", min_size=1, max_size=24),
    st.text(alphabet="abcXYZ0189 -_", min_size=1, max_size=24),
)


class _AbstractRow(NamedTuple):
    """一行分录的抽象形态。``cells`` 与 ``COLUMN_ORDER`` 同长，按位 materialize。"""

    cells: tuple[Any, ...]
    entry_type: str


class _SeedPlan(NamedTuple):
    """预置态：``kind="prefix"`` 是连续行号 1..k；``kind="sparse"`` 可含空洞。"""

    kind: str
    indices: tuple[int, ...]


def _arb_row(width: int) -> st.SearchStrategy[_AbstractRow]:
    return st.builds(
        _AbstractRow,
        cells=st.tuples(*([_arb_cell] * width)),
        entry_type=st.sampled_from(_canonical_entry_types()),
    )


def _arb_rows(width: int) -> st.SearchStrategy[list[_AbstractRow]]:
    return st.lists(_arb_row(width), min_size=0, max_size=_MAX_ROWS)


def _arb_seed() -> st.SearchStrategy[_SeedPlan]:
    contiguous = st.integers(min_value=0, max_value=_MAX_SEED).map(
        lambda k: _SeedPlan("prefix", tuple(range(1, k + 1)))
    )
    sparse = st.lists(
        st.integers(min_value=1, max_value=_MAX_SEED),
        unique=True,
        min_size=1,
        max_size=_MAX_SEED,
    ).map(lambda xs: _SeedPlan("sparse", tuple(sorted(xs))))
    return st.one_of(contiguous, sparse)


def _materialize(code: str, row: _AbstractRow) -> dict[str, Any]:
    """抽象行 → 该 sheet 的行载荷（字段名取 ``field_keys``，占位位不给键）。"""
    spec = _spec(code)
    payload: dict[str, Any] = {}
    for key, cell in zip(spec.field_keys, row.cells, strict=True):
        if key is not None:
            payload[key] = cell
    literal = impl._entry_type_literal(spec, row.entry_type)
    payload[spec.entry_type_field] = row.entry_type if literal is None else literal
    return payload


def _materialize_all(code: str, rows: Sequence[_AbstractRow]) -> list[dict[str, Any]]:
    return [_materialize(code, row) for row in rows]


def _seed_row_payload(code: str, row_no: int) -> dict[str, Any]:
    """预置行的载荷 —— 每个字段都带 ``_MARK`` ⇒ 非空（``is_row_empty`` 为假）。

    非空是 ``fill-empty`` / ``reject`` 两条判据的**前置条件**：``fill-empty`` 只填空位、
    ``reject`` 只在有非空数据时拒收 ⇒ 若预置值是空的，这两条判据都会退化成恒真。
    """
    spec = _spec(code)
    payload = {
        key: f"{_MARK}{row_no}-{key}" for key in spec.field_keys if key is not None
    }
    literal = impl._entry_type_literal(spec, _canonical_entry_types()[0])
    payload[spec.entry_type_field] = literal or _canonical_entry_types()[0]
    return payload


# ═══════════════════════════════════════════════════════════════════════════
# 4. 库夹具（sqlite in-memory + 生产函数直调；不连真库、不 pg_only 跳过）
# ═══════════════════════════════════════════════════════════════════════════

#: ``checklist_responses`` 的全部列。快照取全部列：只比值列会漏掉「只动时间戳」的 upsert。
_SNAPSHOT_COLUMNS = (
    "id",
    "project_id",
    "wp_id",
    "item_id",
    "conclusion",
    "remark",
    "wp_ref",
    "updated_by",
    "created_at",
    "updated_at",
)
_WP_COL = _SNAPSHOT_COLUMNS.index("wp_id")
_ITEM_COL = _SNAPSHOT_COLUMNS.index("item_id")

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS working_paper (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS checklist_responses (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        wp_id TEXT NOT NULL,
        item_id VARCHAR(64) NOT NULL,
        conclusion TEXT,
        remark TEXT,
        wp_ref VARCHAR(100),
        updated_by TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        UNIQUE (wp_id, item_id)
    )
    """,
)

_PROJECT_ID = "3f7c1a02-0000-4000-8000-000000000002"
#: 目标底稿与旁证底稿。两者都预置**全部 16 张**的族键 ⇒ 「作用域双重限定」的两个维度
#: （别的底稿 / 同底稿的别的 sheet）都能在同一次快照差里判定。
_WP_TARGET = "3f7c1a02-0000-4000-9001-00000000000a"
_WP_BYSTANDER = "3f7c1a02-0000-4000-9001-00000000000b"
#: 基线预置行号（``reset()`` 把两个底稿的 16 张都恢复成这个形态）。
_BASE_INDICES = (1, 2, 3)

_SEED_TS = "2026-01-01T00:00:00.000000000"


class _Reply(NamedTuple):
    status: int
    body: Any


class _Harness:
    """一个事件循环 + 一个 sqlite 引擎 + 一个挂了 16 个前缀形态 A 三态的 ASGI 客户端。

    🔴 全程复用**同一个** loop：aiosqlite 的连接绑定在创建它的 loop 上，每次迭代各起一个
    ``asyncio.run`` 会在第二次就拿到一个已关闭 loop 上的连接（平台踩过的同族坑）。

    🔴 ``NOW()`` 在 sqlite 不存在（实现的 upsert SQL 用到它），此处注册一个**单调递增**的
    替身：既让 sqlite 跑得通，又让「值相同的幂等 upsert」表现为 ``updated_at`` 前移，
    从而被整表快照抓到。
    """

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._tick = 0
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine.sync_engine, "connect")
        def _register_now(dbapi_connection: Any, _record: Any) -> None:
            dbapi_connection.create_function("NOW", 0, self._next_now)

        self.maker = async_sessionmaker(self.engine, expire_on_commit=False)
        self.wp_ids = (_WP_TARGET, _WP_BYSTANDER)
        self.app = self._build_app()
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://x3-keyfamily-property"
        )
        self.loop.run_until_complete(self._setup())

    # ── 生命周期 ──────────────────────────────────────────────────────────
    def _next_now(self) -> str:
        self._tick += 1
        return f"2026-02-02T00:00:00.{self._tick:09d}"

    def _build_app(self) -> FastAPI:
        from app.core.database import get_db
        from app.deps import get_current_user

        host = APIRouter()
        for prefix, codes in _prefix_to_codes().items():
            # 与生产同一调用形态：sheets = 按 api_prefix 反查出的 X-3 码集合
            impl.attach_shape_a_routes(host, api_prefix=prefix, sheets=codes)
        app = FastAPI()
        app.include_router(host)

        async def _db_override() -> Any:
            async with self.maker() as session:
                yield session

        class _User:
            id = "3f7c1a02-0000-4000-a001-000000000001"
            role = "admin"

        app.dependency_overrides[get_db] = _db_override
        app.dependency_overrides[get_current_user] = lambda: _User()
        return app

    async def _setup(self) -> None:
        async with self.engine.begin() as conn:
            for ddl in _DDL:
                await conn.execute(sa.text(ddl))
        async with self.maker() as db:
            for wp_id in self.wp_ids:
                await db.execute(
                    sa.text(
                        "INSERT INTO working_paper (id, project_id, is_deleted) "
                        "VALUES (:id, :pid, 0)"
                    ),
                    {"id": wp_id, "pid": _PROJECT_ID},
                )
            await db.commit()
        await self._reseed_all()

    # ── 预置 ──────────────────────────────────────────────────────────────
    def _seed_pairs(self, code: str, indices: Sequence[int]) -> list[tuple[str, Any]]:
        """(item_id, 落库值) 清单 —— 键一律由生产函数拼，值一律非空。"""
        spec = _spec(code)
        pairs: list[tuple[str, Any]] = []
        if _is_single(spec):
            pairs.append(
                (
                    impl.single_json_item_id(spec),
                    json.dumps(
                        [_seed_row_payload(code, i) for i in indices], ensure_ascii=False
                    ),
                )
            )
        else:
            for row_no in indices:
                if spec.per_field_prefix is not None:
                    for suffix in spec.per_field_suffixes:
                        pairs.append(
                            (
                                impl.per_field_item_id(spec, row_no, suffix),
                                f"{_MARK}{row_no}-{suffix}",
                            )
                        )
                if spec.data_key_prefix is not None:
                    pairs.append(
                        (
                            impl.data_item_id(spec, row_no),
                            json.dumps(_seed_row_payload(code, row_no), ensure_ascii=False),
                        )
                    )
        for item_id in spec.standalone_item_ids:
            pairs.append((item_id, f"{_MARK}表级独立键"))
        return pairs

    async def _seed(self, code: str, wp_id: str, indices: Sequence[int]) -> None:
        spec = _spec(code)
        column = spec.storage_field
        async with self.maker() as db:
            prefixes = [
                {"w": wp_id, "p": impl._like_prefix(p)} for p in _family_prefixes(spec)
            ]
            if prefixes:
                await db.execute(
                    sa.text(
                        "DELETE FROM checklist_responses "
                        "WHERE wp_id = :w AND item_id LIKE :p ESCAPE '\\'"
                    ),
                    prefixes,
                )
            exact = [impl.single_json_item_id(spec)] if _is_single(spec) else []
            exact.extend(spec.standalone_item_ids)
            if exact:
                await db.execute(
                    sa.text(
                        "DELETE FROM checklist_responses WHERE wp_id = :w AND item_id = :i"
                    ),
                    [{"w": wp_id, "i": iid} for iid in exact],
                )
            pairs = self._seed_pairs(code, indices)
            if pairs:
                await db.execute(
                    sa.text(
                        f"INSERT INTO checklist_responses "  # noqa: S608 - 列名取自白名单
                        f"(id, project_id, wp_id, item_id, {column}, created_at, updated_at) "
                        "VALUES (:id, :pid, :wp, :iid, :val, :ts, :ts)"
                    ),
                    [
                        {
                            "id": str(uuid.uuid4()),
                            "pid": _PROJECT_ID,
                            "wp": wp_id,
                            "iid": iid,
                            "val": val,
                            "ts": _SEED_TS,
                        }
                        for iid, val in pairs
                    ],
                )
            await db.commit()

    async def _reseed_all(self) -> None:
        async with self.maker() as db:
            await db.execute(sa.text("DELETE FROM checklist_responses"))
            await db.commit()
        for wp_id in self.wp_ids:
            for code in _codes():
                await self._seed(code, wp_id, _BASE_INDICES)

    def reset(self) -> None:
        """把两个底稿的 16 张全部恢复成 ``_BASE_INDICES`` —— 每条库判据开头调一次。

        没有它，判据之间就**互相依赖执行顺序**（``overwrite`` 会清掉行号超出的族键）⇒
        单独跑 ``-k`` 时结论会变，属守卫缺陷。
        """
        self.loop.run_until_complete(self._reseed_all())

    def seed(self, code: str, indices: Sequence[int], *, wp_id: str = _WP_TARGET) -> None:
        self.loop.run_until_complete(self._seed(code, wp_id, indices))

    def close(self) -> None:
        try:
            self.loop.run_until_complete(self.client.aclose())
            self.loop.run_until_complete(self.engine.dispose())
        finally:
            self.loop.close()

    # ── 库态读取 ──────────────────────────────────────────────────────────
    def snapshot(self) -> tuple[tuple[Any, ...], ...]:
        async def _run() -> tuple[tuple[Any, ...], ...]:
            async with self.maker() as db:
                result = await db.execute(
                    sa.text(
                        f"SELECT {', '.join(_SNAPSHOT_COLUMNS)} "  # noqa: S608 - 列名白名单
                        "FROM checklist_responses ORDER BY wp_id, item_id"
                    )
                )
                return tuple(tuple(row) for row in result.fetchall())

        return self.loop.run_until_complete(_run())

    def family_keys(self, code: str, *, wp_id: str = _WP_TARGET) -> frozenset[str]:
        """该底稿里落在这张 sheet **族键空间**内的 item_id 集合。"""
        spec = _spec(code)

        async def _run() -> frozenset[str]:
            async with self.maker() as db:
                result = await db.execute(
                    sa.text(
                        "SELECT item_id FROM checklist_responses WHERE wp_id = :w"
                    ),
                    {"w": wp_id},
                )
                return frozenset(
                    row[0] for row in result.fetchall() if _belongs(spec, row[0])
                )

        return self.loop.run_until_complete(_run())

    def single_json_array(self, code: str, *, wp_id: str = _WP_TARGET) -> Any:
        """整表单键族的库值解析结果（幽灵行在这一族的形态是数组多出的元素）。"""
        spec = _spec(code)
        column = spec.storage_field

        async def _run() -> Any:
            async with self.maker() as db:
                result = await db.execute(
                    sa.text(
                        f"SELECT {column} AS value FROM checklist_responses "  # noqa: S608
                        "WHERE wp_id = :w AND item_id = :i LIMIT 1"
                    ),
                    {"w": wp_id, "i": impl.single_json_item_id(spec)},
                )
                row = result.fetchone()
                if row is None or row.value is None:
                    return None
                return json.loads(row.value)

        return self.loop.run_until_complete(_run())

    # ── 生产函数直调 ──────────────────────────────────────────────────────
    def readback(self, code: str, *, wp_id: str = _WP_TARGET) -> list[dict[str, Any]]:
        """界面读路径（生产函数 ``load_rows``）。"""

        async def _run() -> list[dict[str, Any]]:
            async with self.maker() as db:
                rows, _warnings = await impl.load_rows(db, wp_id, code)
                return rows

        return self.loop.run_until_complete(_run())

    def write(
        self,
        code: str,
        rows: Sequence[Mapping[str, Any]],
        strategy: str,
        *,
        wp_id: str = _WP_TARGET,
    ) -> Any:
        """族键爆炸 → 落库 → 归约（生产函数 ``write_rows``）。异常原样上抛。"""

        async def _run() -> Any:
            async with self.maker() as db:
                return await impl.write_rows(db, wp_id, code, rows, strategy)

        return self.loop.run_until_complete(_run())

    # ── 端点调用（只给「策略透传」那条行为锚点用）────────────────────────
    def post(
        self, code: str, action: str, *, params: Mapping[str, Any], content: bytes | None
    ) -> _Reply:
        prefix = _spec(code).api_prefix
        files = (
            None
            if content is None
            else {
                "file": (
                    "upload.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }
        )

        async def _run() -> _Reply:
            resp = await self.client.post(
                f"/api/workpapers/{_WP_TARGET}/{prefix}/{action}",
                params=dict(params),
                files=files,
            )
            ctype = resp.headers.get("content-type", "")
            body: Any = resp.json() if "json" in ctype else resp.content
            return _Reply(status=resp.status_code, body=body)

        return self.loop.run_until_complete(_run())


_HARNESS: _Harness | None = None


def _hz() -> _Harness:
    global _HARNESS
    if _HARNESS is None:
        _HARNESS = _Harness()
    return _HARNESS


@pytest.fixture(scope="session", autouse=True)
def _harness_lifecycle() -> Any:
    yield
    global _HARNESS
    if _HARNESS is not None:
        _HARNESS.close()
        _HARNESS = None


def _static_region(
    snapshot: Sequence[Sequence[Any]], code: str, wp_id: str
) -> tuple[tuple[Any, ...], ...]:
    """快照里**本次写入不该碰**的那部分：别的底稿全部 + 本底稿除目标族键空间以外全部。"""
    spec = _spec(code)
    return tuple(
        tuple(row)
        for row in snapshot
        if not (row[_WP_COL] == wp_id and _belongs(spec, row[_ITEM_COL]))
    )


def _delta(before: Sequence[Sequence[Any]], after: Sequence[Sequence[Any]]) -> str:
    """把两次快照差渲染成「新增 / 删除 / 改值」三段（人可读，各最多 5 条）。"""

    def keyed(rows: Sequence[Sequence[Any]]) -> dict[tuple[Any, Any], Sequence[Any]]:
        return {(row[_WP_COL], row[_ITEM_COL]): row for row in rows}

    b, a = keyed(before), keyed(after)
    added = sorted(set(a) - set(b))
    removed = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if tuple(a[k]) != tuple(b[k]))
    parts: list[str] = []
    if added:
        parts.append(f"新增 {len(added)} 条: {added[:5]}")
    if removed:
        parts.append(f"删除 {len(removed)} 条: {removed[:5]}")
    if changed:
        detail = []
        for key in changed[:5]:
            diffs = [
                f"{_SNAPSHOT_COLUMNS[i]}: {b[key][i]!r} -> {a[key][i]!r}"
                for i in range(len(_SNAPSHOT_COLUMNS))
                if b[key][i] != a[key][i]
            ]
            detail.append(f"{key} [{'; '.join(diffs)}]")
        parts.append(f"改值 {len(changed)} 条: {detail}")
    return " | ".join(parts) or "<无差异>"


def _upload_bytes(code: str, n_rows: int) -> bytes:
    """按标准列序造一份真实 xlsx 字节（只给端点锚点用）。

    表名取该 sheet 自己的 ``sheet_name`` ⇒ 不触发实现的「异表名拒收」通路
    （那条通路属 Property 4 的半径）。
    """
    spec = _spec(code)
    wb = Workbook()
    ws = wb.active
    ws.title = spec.sheet_name
    ws.append(list(_face()))
    for i in range(1, n_rows + 1):
        ws.append([f"{_MARK}{i}-{j}" for j in range(len(_face()))])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# 5. 前置锚点（反空转；红 = 作业面或夹具塌了，下面的属性结论不可解读）
# ═══════════════════════════════════════════════════════════════════════════


