"""C4：Ledger 导入分阶段 profiler — rows/s、WAL 增量、staging / COPY / index / activation 耗时。

**本模块只记账，不替换任何现有 pipeline 阶段**；真实 COPY/set-based 合并是独立的
性能优化工作，放在 `platform-heavy-jobs-and-capacity-closure` C4 验收项下，必须在
专用可销毁 PG + 真实大项目数据上跑。

用法::

    profiler = StagedProfiler()
    async with profiler.stage("staging_write", db, rows=42):
        await db.execute(...)
    report = profiler.to_dict()
    # {
    #   "stages": {
    #     "staging_write": {"duration_s": 1.23, "rows": 42,
    #                       "rows_per_sec": 34.1, "wal_bytes": 12345, "error": None},
    #     ...
    #   },
    #   "total_duration_s": 1.23,
    #   "total_rows": 42,
    # }

设计边界：
- **PG 环境**：stage 结束时取 `pg_wal_lsn_diff(pg_current_wal_lsn(), $start)`，
  得到该 stage 内的 WAL 增量字节；失败降级为 None，不打断主流程。
- **SQLite / 无 db**：`wal_bytes` 返回 None，`rows`/`duration_s`/`rows_per_sec`
  仍可用。
- 不访问 ImportJob ORM、不入全局 registry；每次 import 一个独立实例。
- `to_dict()` 返回纯 JSON 可序列化字典，pipeline 可塞进 progress / metadata。
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from typing import Any, AsyncIterator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


__all__ = [
    "StageRecord",
    "StagedProfiler",
]


@dataclass
class StageRecord:
    """单个 stage 的执行记录；所有字段都 JSON 可序列化。"""

    duration_s: float
    rows: int
    rows_per_sec: Optional[float]
    wal_bytes: Optional[int]
    error: Optional[str] = None


class StagedProfiler:
    """按阶段记录 duration + rows + WAL 增量；单例，非线程安全。

    PG / SQLite 共用同一份代码：WAL 探针在非 PG 环境自动降级为 None。
    """

    def __init__(self) -> None:
        self._stages: dict[str, StageRecord] = {}
        self._total_rows = 0

    @asynccontextmanager
    async def stage(
        self,
        name: str,
        db: AsyncSession | None = None,
        *,
        rows: int = 0,
    ) -> AsyncIterator["StagedProfiler"]:
        """包一段代码做为 stage；失败记 error 后原样向上抛。"""
        start_lsn = await _get_wal_lsn(db)
        started = time.perf_counter()
        error: Optional[str] = None
        try:
            yield self
        except Exception as exc:  # noqa: BLE001 — 保留原异常后向上抛
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            duration = time.perf_counter() - started
            end_lsn = await _get_wal_lsn(db)
            wal_bytes = await _wal_diff(db, start_lsn, end_lsn)
            rps = (rows / duration) if (rows > 0 and duration > 0) else None
            self._stages[name] = StageRecord(
                duration_s=duration,
                rows=rows,
                rows_per_sec=rps,
                wal_bytes=wal_bytes,
                error=error,
            )
            if rows > 0:
                self._total_rows += rows

    def record_rows(self, stage: str, rows: int) -> None:
        """stage 结束后追记行数（例如 COPY 返回真实行数）；rate 按累计重算。"""
        if stage not in self._stages:
            return
        current = self._stages[stage]
        new_rows = current.rows + rows
        rps = (new_rows / current.duration_s) if current.duration_s > 0 else None
        self._stages[stage] = StageRecord(
            duration_s=current.duration_s,
            rows=new_rows,
            rows_per_sec=rps,
            wal_bytes=current.wal_bytes,
            error=current.error,
        )
        self._total_rows += rows

    def record_stage_manual(
        self,
        name: str,
        *,
        duration_s: float,
        rows: int = 0,
        wal_bytes: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """不走 ``stage()`` context manager 的旁路登记：适合**事后**把 pipeline
        已经测好的 per-phase 时长折算进 profiler。``rows/sec`` 由 ``rows`` 与
        ``duration_s`` 推导；``wal_bytes`` / ``error`` 原样记录。

        用于：legacy pipeline 里 ``_mark("phase_done")`` + ``_perf`` 字典已经测
        好所有阶段耗时，调用方只需把这些已有数据平移进 profiler 做统一报告。
        """
        rps = (rows / duration_s) if (rows > 0 and duration_s > 0) else None
        self._stages[name] = StageRecord(
            duration_s=duration_s,
            rows=rows,
            rows_per_sec=rps,
            wal_bytes=wal_bytes,
            error=error,
        )
        if rows > 0:
            self._total_rows += rows

    def to_dict(self) -> dict[str, Any]:
        """返回可塞进 ImportJob metadata / API response 的纯 dict。"""
        return {
            "stages": {name: asdict(rec) for name, rec in self._stages.items()},
            "total_duration_s": sum(rec.duration_s for rec in self._stages.values()),
            "total_rows": self._total_rows,
        }

    @property
    def total_rows(self) -> int:
        return self._total_rows

    @property
    def stages(self) -> dict[str, StageRecord]:
        """只读视图；修改应走 stage() 或 record_rows()。"""
        return dict(self._stages)


async def _get_wal_lsn(db: AsyncSession | None) -> Optional[str]:
    """PG 返回当前 WAL LSN；其他环境返回 None。"""
    if db is None or db.bind is None:
        return None
    if db.bind.dialect.name != "postgresql":
        return None
    try:
        row = (await db.execute(text("SELECT pg_current_wal_lsn()::text"))).first()
        return row[0] if row else None
    except Exception:  # noqa: BLE001 — 权限不足 / replica 等情形降级
        return None


async def _wal_diff(
    db: AsyncSession | None,
    start_lsn: Optional[str],
    end_lsn: Optional[str],
) -> Optional[int]:
    """返回 start → end 的 WAL 字节差；缺一端或非 PG 返回 None。"""
    if db is None or db.bind is None:
        return None
    if db.bind.dialect.name != "postgresql":
        return None
    if not start_lsn or not end_lsn:
        return None
    try:
        row = (
            await db.execute(
                text("SELECT pg_wal_lsn_diff(:end, :start)::bigint"),
                {"end": end_lsn, "start": start_lsn},
            )
        ).first()
        return int(row[0]) if row else None
    except Exception:  # noqa: BLE001 — pg_wal_lsn_diff 不可用时降级
        return None
