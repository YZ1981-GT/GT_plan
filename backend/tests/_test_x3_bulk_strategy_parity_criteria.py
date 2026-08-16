"""test_x3_bulk_strategy_parity —— 判据层（常量 / 登记表 / fixture / 纯函数 / 取证 helper）。

从 `backend/tests/test_x3_bulk_strategy_parity.py` 拆出：原文件 1168 行 > pre-commit 的 800 行门禁。
**不加 file_size_whitelist** —— 白名单表头写明「仅历史大文件」，新增文件
套用属滥用。

刻意与用例文件**同目录**：判据里的 `Path(__file__).parents[N]` 路径推算
移到子目录会整体错一层（实测过，会变成 fixture setup 全 ERROR）。

用例层的 import 清单由拆分脚本按其**实际引用**算出，不手写 —— 漏一个名字
就是 collection error，会让整份守卫的断言零执行而表面上「没有失败」。

原文件 docstring 原样保留在下方。
"""

"""GS7 —— bulk 通路与界面通路的**库态等价**（任务 17.1 的收口判据）

═══════════════════════════════════════════════════════════════════════════════
判的是什么
═══════════════════════════════════════════════════════════════════════════════

∀ 16 张 X-3 作业面 × ∀ ``ConflictStrategy`` 三取值：经 **bulk 通路**
（``import_tab`` → ``IE_ADAPTER_REGISTRY[短前缀].import_fn`` → ``_call_endpoint``）导入
与经 **界面通路**（形态 A 端点走真实 HTTP）导入同一份 xlsx 后，``checklist_responses``
的**整表库态逐行逐列相同**，且界面读路径（``load_rows``）读回逐行相同。

**Validates: Requirements 1.1, 1.5, 2.5, 6.6, 10.3**

🔴 **不判「kwargs 里有没有 `strategy` 这个键」**。那种判据在下面这三类形态下全绿：
① 传了个键但取值是硬编码的 ``"overwrite"``（用户选的 ``fill-empty`` 照样丢）
② 传了正确取值但被调侧不消费 ③ 两条通路解析到**不同的** endpoint 对象（split-brain）。
故本文件的每条判据都落在 ``checklist_responses`` 的整表快照上（含 ``created_at`` /
``updated_at`` 的「本轮是否被写过」这一维），并对 ``reject`` 追加「库态必须与导入前逐行
逐列相同」。

═══════════════════════════════════════════════════════════════════════════════
为什么这条判据在施加前必然红（缺陷实证，Checkpoint 7 已量化）
═══════════════════════════════════════════════════════════════════════════════

``_call_endpoint`` 施加前不传 ``strategy`` ⇒ 端点形参落到默认值 ``Query("overwrite")``
这个 ``FieldInfo`` **对象本身**（实测 ``isinstance(默认值, str) is False``、
``默认值 == "overwrite"`` 为 ``False``），后果两条且方向相反于直觉：

* ``resolve_conflict`` 对未知策略走**防御性 ``else``** ⇒ 合并语义**恰好**等同 overwrite
  ⇒ 用户在批量对话框选的 ``fill-empty`` / ``reject`` 被静默丢掉（``reject`` 本该整表拒绝）；
* ``_should_purge_residual`` 的 ``== "overwrite"`` 对 ``FieldInfo`` **不成立** ⇒ bulk
  **从不清**残留族键（幽灵行留存），而界面通路会清。

这两条不是推理，是本文件 ``test_witness_dropping_strategy_diverges_from_ui`` 用**真实
丢参调用**（走生产 ``_call_endpoint``，不传 ``strategy`` —— 与施加前逐字同形）在库态上
量化出来的：丢参态 vs 界面 ``fill-empty`` / ``reject`` 在 **16/16** 上分叉；vs 界面
``overwrite`` 在 **11 张非整表单键族**上分叉（残留没清）、在 **5 张整表单键族**上相同
（该族无残留概念 ⇒ 只剩「合并语义恰好等同 overwrite」这一条）。

🔴 该 witness 同时是本文件的**反空转锚点**：它证明「bulk 态 == 界面态」这句话有内容
（存在一个真实实现让它红），不是恒真命题。删掉它 = 拆掉唯一能证明判据有牙的那条。

═══════════════════════════════════════════════════════════════════════════════
库态比对口径（哪几列被归一，为什么归一不是放水）
═══════════════════════════════════════════════════════════════════════════════

快照取 ``checklist_responses`` **全部 10 列**。其中三列在两次运行间**按设计**不可能逐字
相同（``id`` 是 ``uuid4()``、两个时间戳来自 ``NOW()``），故归一成**类别**而非丢弃：

| 列 | 归一后取值 | 归一后仍能抓到的分叉 |
|---|---|---|
| ``id`` | ``"seed"`` / ``"run"`` | 「原地 upsert」vs「新插一行」（``ON CONFLICT`` 保留原 id） |
| ``created_at`` | ``"seed"`` / ``"run"`` | 该键是预置的还是本轮新建的 |
| ``updated_at`` | ``"seed"`` / ``"run"`` | 该行**本轮有没有被写过**（值相同的幂等 upsert 也算） |

预置行的 ``id`` 用**确定性**取值（不用 ``uuid4``）⇒ 两次运行的基线逐字节相同，归一只作用
在「本轮新产生的行」上。``NOW()`` 在夹具里是**单调递增**替身 ⇒ 「值没变只动时间戳」这种
写入照样落进快照差。归一是否放水由 ``test_reverse_selfcheck_normalization_is_not_lossy``
反向钉住（两个刻意不同的库态归一后必须不同）。

═══════════════════════════════════════════════════════════════════════════════
与既有判据的分工（本文件不抄第二份）
═══════════════════════════════════════════════════════════════════════════════

| 面 | 既有归属 | 本文件 |
|---|---|---|
| 两条通路解析到**同一模块** | GS6 ``test_x3_adapter_host_same_module`` | 只加一条**同一 callable 对象**的恒等锚点（模块相同不等于对象相同） |
| 委派点剥 ``Query`` 包装后是真 ``str`` | GS6 ``test_x3_legacy_sheet_param`` | 不重复（那是形态 B → 形态 A 的委派，不是 bulk） |
| ``_should_purge_residual`` 纯函数真值表 | GS1 ``test_x3_key_ledger`` | 不重复 |
| 端点自己把 ``strategy`` 透传到门控 | Property 2 ``test_anchor_import_endpoint_forwards_strategy`` | 不重复（那条只走界面通路） |
| **bulk 通路 vs 界面通路的库态等价** | 无 | **本文件全部判据** |
| **``reject`` 经 bulk 真的拒绝而不是覆盖** | 无 | **本文件** |
| **73 个非 X-3 键行为逐字不变** | 无 | **本文件**（签名探测面 + 全键 kwargs 双向锁死） |

零硬编码：作业面取自 ``backend/data/adjustment_ie_contract.json``（与实现
``_select_x3_entries`` 同口径）并与 ``X3_SHEET_SPECS`` 双向锁死；策略取值面取自
``ConflictStrategy`` 这个 ``Literal``；族键一律由生产函数拼；短前缀由 ``spec.api_prefix``
反查。本文件不写任何键 / 列头 / sheet 名 / 短前缀字面量。
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import io
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple, get_args

import pytest
import sqlalchemy as sa
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.routers.wp_render_strategies import _x3_adjustment_import_export as impl
from app.services.bulk_tab import _kfgh_cycle_adapters as ad
from app.services.bulk_tab.single_tab_adapter import (
    IE_ADAPTER_REGISTRY,
    ConflictStrategy,
    import_tab,
)

_REPO = Path(__file__).resolve().parents[2]
_CONTRACT = _REPO / "backend" / "data" / "adjustment_ie_contract.json"

#: 探针记号 —— 真实清单取值与真实 sheet 名里都不会出现（由反向自检钉住）。
_MARK = "‡通路等价探针"

#: 基线预置行号；上传 1 行 ⇒ 行 2/3 的族键成为「残留」（overwrite 该清、fill-empty 不清）。
_BASE_INDICES = (1, 2, 3)
_UPLOAD_ROWS = 1

_PROJECT_ID = "3f7c1a02-0000-4000-8000-000000000012"
#: 目标底稿 + 旁证底稿（旁证底稿也预置全部 16 张 ⇒ 越界写入会落进整表快照差）。
_WP_TARGET = "3f7c1a02-0000-4000-9001-00000000001a"
_WP_BYSTANDER = "3f7c1a02-0000-4000-9001-00000000001b"

_SEED_TS = "2026-01-01T00:00:00.000000000"
#: 预置行的 id 前缀 —— 确定性取值（不用 uuid4）⇒ 两条通路的基线逐字节相同。
_SEED_ID = "seed"
_RUN_ID = "run"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 真源装载
# ═══════════════════════════════════════════════════════════════════════════


@lru_cache(maxsize=1)
def _contract() -> Mapping[str, Any]:
    assert _CONTRACT.is_file(), f"契约清单缺失：{_CONTRACT}（守卫必须打红而非跳过）"
    doc = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    assert isinstance(doc.get("sheets"), Mapping), "契约清单缺 `sheets` 段"
    return doc


@lru_cache(maxsize=1)
def _codes() -> tuple[str, ...]:
    """作业面 —— 判据 = 条目登记了 ``key_family``（与实现 ``_select_x3_entries`` 同口径）。"""
    sheets = _contract()["sheets"]
    codes = tuple(
        sorted(
            code
            for code, entry in sheets.items()
            if isinstance(entry, Mapping) and entry.get("key_family")
        )
    )
    assert codes, "契约清单里没有任何登记 key_family 的条目 ⇒ 作业面塌陷"
    return codes


def _spec(code: str) -> Any:
    return impl.sheet_spec(code)


@lru_cache(maxsize=1)
def _strategies() -> tuple[str, ...]:
    """策略取值面 —— 取自 ``ConflictStrategy`` 这个 ``Literal`` 的类型参数（不写三元组）。"""
    values = tuple(str(v) for v in get_args(ConflictStrategy))
    assert values, "`ConflictStrategy` 的 Literal 取值面为空 ⇒ 策略维度塌陷"
    return values


@lru_cache(maxsize=1)
def _face() -> tuple[str, ...]:
    """列面（只作构造上传文件用）= 实现由清单 ``column_map`` 派生的列序。"""
    face = tuple(impl.COLUMN_ORDER)
    assert face, "实现派生的 COLUMN_ORDER 为空"
    return face


def _is_single(spec: Any) -> bool:
    return spec.key_family is impl.KeyFamily.SINGLE_JSON


def _family_prefixes(spec: Any) -> tuple[str, ...]:
    return tuple(p for p in (spec.per_field_prefix, spec.data_key_prefix) if p)


def _import_endpoint(code: str) -> Any:
    """bulk 通路解析到的 ``import-data`` 端点 —— 走**生产**解析式子，不复制第二份。"""
    prefix = _spec(code).api_prefix
    module_name = ad._PREFIX_TO_MODULE[prefix]
    module = importlib.import_module(ad._resolve_module_path(module_name))
    return ad._endpoint_for(module, prefix, ad._SUFFIX_IMPORT)


def _shape_a_routes(code: str) -> list[Any]:
    """生产模块 ``router`` 上该短前缀的形态 A 路由对象（三态）。"""
    prefix = _spec(code).api_prefix
    module = importlib.import_module(ad._resolve_module_path(ad._PREFIX_TO_MODULE[prefix]))
    want = f"/{prefix}/"
    return [
        route
        for route in getattr(module.router, "routes", [])
        if f"/api/workpapers/{{wp_id}}{want}" in str(getattr(route, "path", ""))
    ]


@lru_cache(maxsize=None)
def _upload_bytes(code: str, n_rows: int) -> bytes:
    """按标准列序造一份真实 xlsx 字节。

    表名取该 sheet 自己的 ``sheet_name`` ⇒ 不触发「异表名拒收」；单元格带探针记号 ⇒
    既非空（``fill-empty`` 的合并分支才有意义）也不等于清单示例行（不被示例行过滤吞掉）。
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
# 2. 库夹具（一个 loop + 一个 sqlite 引擎 + 生产路由对象搬进 ASGI app）
# ═══════════════════════════════════════════════════════════════════════════

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


class _Reply(NamedTuple):
    status: int
    body: Any


class _Harness:
    """一个事件循环 + 一个 sqlite 引擎 + 挂了**生产路由对象**的 ASGI 客户端。

    🔴 全程复用**同一个** loop：aiosqlite 连接绑定在创建它的 loop 上，每次迭代各起一个
    ``asyncio.run`` 会在第二次拿到已关闭 loop 上的连接（平台踩过的同族坑）。

    🔴 ``NOW()`` 在 sqlite 不存在（实现的 upsert SQL 用到它），此处注册**单调递增**替身：
    既让 sqlite 跑得通，又让「值相同的幂等 upsert」表现为 ``updated_at`` 前移。

    🔴 app 里挂的是**生产模块 router 上的那些路由对象**（不是重新 ``attach_shape_a_routes``
    生成一份新闭包）⇒ 界面通路命中的 endpoint 与 bulk 通路解析到的是**同一个对象**
    （由 ``test_anchor_two_paths_share_one_callable`` 恒等断言钉住）。否则「两条通路库态
    相同」可能只是「两份同源闭包各自正确」，而真实 split-brain 照样漏网。
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
            transport=ASGITransport(app=self.app), base_url="http://x3-bulk-parity"
        )
        self.loop.run_until_complete(self._setup())

    # ── 生命周期 ──────────────────────────────────────────────────────────
    def _next_now(self) -> str:
        self._tick += 1
        return f"2026-03-03T00:00:00.{self._tick:09d}"

    def _build_app(self) -> FastAPI:
        from app.core.database import get_db
        from app.deps import get_current_user

        host = APIRouter()
        seen: set[int] = set()
        for code in _codes():
            for route in _shape_a_routes(code):
                if id(route) in seen:
                    continue
                seen.add(id(route))
                host.routes.append(route)
        assert host.routes, "生产模块 router 上没找到任何形态 A 路由 ⇒ 夹具塌陷"
        app = FastAPI()
        app.include_router(host)

        async def _db_override() -> Any:
            async with self.maker() as session:
                yield session

        class _User:
            id = "3f7c1a02-0000-4000-a001-000000000011"
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

    # ── 预置（确定性 id / 固定时间戳 ⇒ 两条通路的基线逐字节相同）──────────
    def _seed_pairs(self, code: str, indices: Sequence[int]) -> list[tuple[str, Any]]:
        spec = _spec(code)
        pairs: list[tuple[str, Any]] = []
        if _is_single(spec):
            pairs.append(
                (
                    impl.single_json_item_id(spec),
                    json.dumps(
                        [self._seed_row_payload(code, i) for i in indices],
                        ensure_ascii=False,
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
                                f"{_MARK}预置{row_no}-{suffix}",
                            )
                        )
                if spec.data_key_prefix is not None:
                    pairs.append(
                        (
                            impl.data_item_id(spec, row_no),
                            json.dumps(
                                self._seed_row_payload(code, row_no), ensure_ascii=False
                            ),
                        )
                    )
        for item_id in spec.standalone_item_ids:
            pairs.append((item_id, f"{_MARK}表级独立键"))
        return pairs

    @staticmethod
    def _seed_row_payload(code: str, row_no: int) -> dict[str, Any]:
        """预置行载荷 —— 每个字段都带记号 ⇒ 非空（``is_row_empty`` 为假，冲突真存在）。"""
        spec = _spec(code)
        payload = {
            key: f"{_MARK}预置{row_no}-{key}" for key in spec.field_keys if key is not None
        }
        if spec.entry_type_field:
            payload[spec.entry_type_field] = f"{_MARK}预置类型"
        return payload

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
                            "id": f"{_SEED_ID}:{wp_id}:{iid}",
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
        """把两个底稿的 16 张恢复成 ``_BASE_INDICES`` —— 每次通路对照前必须调。

        没有它，两条通路的**起点**就不同（前一条已经清过残留）⇒ 「库态相同」这句话
        无法解读，属守卫缺陷。
        """
        self.loop.run_until_complete(self._reseed_all())

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

    def readback(self, code: str, *, wp_id: str = _WP_TARGET) -> list[dict[str, Any]]:
        """界面读路径（生产函数 ``load_rows``）。"""

        async def _run() -> list[dict[str, Any]]:
            async with self.maker() as db:
                rows, _warnings = await impl.load_rows(db, wp_id, code)
                return rows

        return self.loop.run_until_complete(_run())

    # ── 两条通路 ──────────────────────────────────────────────────────────
    def via_bulk(self, code: str, strategy: str) -> Any:
        """bulk 通路 —— 生产入口 ``import_tab``（含注册表查找 + `_call_endpoint`）。"""
        prefix = _spec(code).api_prefix
        payload = _upload_bytes(code, _UPLOAD_ROWS)

        async def _run() -> Any:
            async with self.maker() as db:
                return await import_tab(db, _WP_TARGET, prefix, code, payload, strategy)  # type: ignore[arg-type]

        return self.loop.run_until_complete(_run())

    def via_ui(self, code: str, strategy: str | None) -> _Reply:
        """界面通路 —— 真实 HTTP 打到生产形态 A 端点（``strategy`` 为 None 时不传该参）。"""
        prefix = _spec(code).api_prefix
        params: dict[str, Any] = {"sheet": code}
        if strategy is not None:
            params["strategy"] = strategy
        files = {
            "file": (
                f"{code}.xlsx",
                _upload_bytes(code, _UPLOAD_ROWS),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }

        async def _run() -> _Reply:
            resp = await self.client.post(
                f"/api/workpapers/{_WP_TARGET}/{prefix}/{ad._SUFFIX_IMPORT}",
                params=params,
                files=files,
            )
            ctype = resp.headers.get("content-type", "")
            body: Any = resp.json() if "json" in ctype else resp.content
            return _Reply(status=resp.status_code, body=body)

        return self.loop.run_until_complete(_run())

    def via_bulk_dropping_strategy(self, code: str) -> Any:
        """**施加前**的 bulk 形态 —— 走生产 ``_call_endpoint`` 但不传 ``strategy``。

        这不是「模拟」：``_call_endpoint`` 的 ``strategy`` 形参默认 ``None``、探测为假 ⇒
        构造出的 kwargs 与施加前逐字相同 ⇒ 它就是施加前那次调用。
        """
        endpoint = _import_endpoint(code)
        assert endpoint is not None, f"{code}: bulk 侧解析不到 import-data 端点"
        upload = ad._make_upload_file(_upload_bytes(code, _UPLOAD_ROWS), code)

        async def _run() -> Any:
            async with self.maker() as db:
                try:
                    return await ad._call_endpoint(
                        endpoint, db=db, wp_id=_WP_TARGET, sheet_code=code, upload_file=upload
                    )
                except Exception as exc:  # noqa: BLE001 - 与生产 import_fn 同款兜法
                    return {"ok": False, "errors": [f"{type(exc).__name__}: {exc}"]}

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


# ═══════════════════════════════════════════════════════════════════════════
# 3. 快照归一（只归一「按设计不可能相同」的三列，且归成类别不丢弃）
# ═══════════════════════════════════════════════════════════════════════════

_ID_COL = _SNAPSHOT_COLUMNS.index("id")
_CREATED_COL = _SNAPSHOT_COLUMNS.index("created_at")
_UPDATED_COL = _SNAPSHOT_COLUMNS.index("updated_at")
#: 可能承载业务载荷的列（只对它们做 UUID 掩码 —— ``wp_id`` / ``project_id`` 本身就是 UUID，
#: 掩掉它们会把「别的底稿被误写」这一维直接判瞎，那才是放水）。
_PAYLOAD_COLS = tuple(
    _SNAPSHOT_COLUMNS.index(c) for c in ("conclusion", "remark", "wp_ref", "updated_by")
)

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_UUID_MASK = "<uuid>"


def _mask_uuids(value: Any) -> Any:
    """载荷里的行级 ``id`` 是 ``parse_workbook`` 每次现生成的 ``uuid4`` —— 掩成定值。

    实测：整表单键 JSON 族的库值形如 ``[{"id": "<uuid4>", "description": …}]``，同一份
    xlsx 连跑两次这个 ``id`` 必不同 ⇒ 不掩的话「两条通路库态相同」在这 5 张上恒假，
    等价判据变成一条永远红的死判据（假红也是守卫缺陷）。
    掩码只作用在载荷列上，且只替换 UUID 形状的子串 ⇒ 载荷里任何**业务**取值差异照样暴露。
    """
    if isinstance(value, str):
        return _UUID_RE.sub(_UUID_MASK, value)
    return value


def _normalize(snapshot: Sequence[Sequence[Any]]) -> tuple[tuple[Any, ...], ...]:
    """整表快照 → 可跨运行比对的形态。

    四个「按设计不可能跨运行相同」的维度归一，其余 6 列逐字比对：
    ``id`` / ``created_at`` / ``updated_at`` 归成 ``seed`` | ``run`` 二值（仍能抓到
    「原地 upsert vs 新插行」「该行本轮有没有被写过」），载荷列里的 UUID 归成定值。
    """
    out: list[tuple[Any, ...]] = []
    for row in snapshot:
        cells = list(row)
        cells[_ID_COL] = (
            _SEED_ID if str(cells[_ID_COL]).startswith(f"{_SEED_ID}:") else _RUN_ID
        )
        for col in (_CREATED_COL, _UPDATED_COL):
            cells[col] = _SEED_ID if cells[col] == _SEED_TS else _RUN_ID
        for col in _PAYLOAD_COLS:
            cells[col] = _mask_uuids(cells[col])
        out.append(tuple(cells))
    return tuple(sorted(out, key=lambda r: (str(r[_WP_COL]), str(r[_ITEM_COL]))))


def _normalize_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """界面读回行的同款归一（行内 ``id`` 同样是每次现生成的 ``uuid4``）。"""
    return [{k: _mask_uuids(v) for k, v in sorted(row.items())} for row in rows]


def _delta(before: Sequence[Sequence[Any]], after: Sequence[Sequence[Any]]) -> str:
    """两次归一快照的差 → 「新增 / 删除 / 改值」三段（人可读，各最多 5 条）。"""

    def keyed(rows: Sequence[Sequence[Any]]) -> dict[tuple[Any, Any], Sequence[Any]]:
        return {(row[_WP_COL], row[_ITEM_COL]): row for row in rows}

    b, a = keyed(before), keyed(after)
    added = sorted(set(a) - set(b))
    removed = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if tuple(a[k]) != tuple(b[k]))
    parts: list[str] = []
    if added:
        parts.append(f"仅后者有 {len(added)} 条: {added[:5]}")
    if removed:
        parts.append(f"仅前者有 {len(removed)} 条: {removed[:5]}")
    if changed:
        detail = []
        for key in changed[:5]:
            diffs = [
                f"{_SNAPSHOT_COLUMNS[i]}: {b[key][i]!r} -> {a[key][i]!r}"
                for i in range(len(_SNAPSHOT_COLUMNS))
                if b[key][i] != a[key][i]
            ]
            detail.append(f"{key} [{'; '.join(diffs)}]")
        parts.append(f"取值不同 {len(changed)} 条: {detail}")
    return " | ".join(parts) or "<无差异>"


def _run_via(hz: _Harness, code: str, strategy: str, path: str) -> tuple[Any, tuple[Any, ...]]:
    """从同一基线跑一条通路 → (通路自报结果, 归一后的整表库态)。"""
    hz.reset()
    if path == "bulk":
        result: Any = hz.via_bulk(code, strategy)
    elif path == "ui":
        result = hz.via_ui(code, strategy)
    else:
        result = hz.via_bulk_dropping_strategy(code)
    return result, _normalize(hz.snapshot())


def _ok(result: Any) -> bool:
    """两条通路的「成功」归一：界面返 ``_Reply``、bulk 返 ``TabImportResult``、丢参态返 dict。

    🔴 ``_Reply`` 必须**先**判：它也是 NamedTuple 且同样有 ``.status`` 字段（取值是 HTTP
    状态码 200，不是 ``"success"``）—— 按 ``hasattr(result, "status")`` 先判会把界面通路
    的成功恒判成失败。
    """
    if isinstance(result, _Reply):
        return bool(
            result.status == 200
            and isinstance(result.body, dict)
            and result.body.get("ok")
        )
    if hasattr(result, "status"):
        return bool(result.status in {"success", "partial"})
    return bool(isinstance(result, dict) and result.get("ok"))


# ═══════════════════════════════════════════════════════════════════════════
# 4. 前置锚点（红 = 作业面或夹具塌了，下面的等价结论不可解读）
# ═══════════════════════════════════════════════════════════════════════════


