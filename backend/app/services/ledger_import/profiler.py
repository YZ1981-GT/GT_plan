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
    "WalStageProbe",
    "read_wal_lsn",
    "wal_bytes_between",
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

    def record_wal_bytes(self, stage: str, wal_bytes: Optional[int]) -> None:
        """给已登记的 stage 补记 WAL 增量字节。

        用于 pipeline：阶段耗时由 ``_mark()`` 事后平移进 profiler，而 WAL 增量
        必须在**阶段自己的** ``async_session()`` 边界内读 LSN 才准确（那时连接
        还在、事务未提交）。读不到时传 ``None``，保持「读不到 ≠ 0」口径。
        """
        if stage not in self._stages:
            return
        current = self._stages[stage]
        self._stages[stage] = StageRecord(
            duration_s=current.duration_s,
            rows=current.rows,
            rows_per_sec=current.rows_per_sec,
            wal_bytes=wal_bytes,
            error=current.error,
        )

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


async def read_wal_lsn(db: AsyncSession | None) -> Optional[str]:
    """公开的 WAL 位置探针：PG 返回当前 LSN 文本，其他环境返回 None。

    供 pipeline 在**自己的** ``async_session()`` 边界内读取阶段起止位置——
    不能把 LSN 读取留给 ``to_dict()``（那时事务早已提交、连接可能已归还，
    读到的位置与阶段实际写入无关）。非 PG / 无权限 / replica 一律降级 None。
    """
    return await _get_wal_lsn(db)


async def wal_bytes_between(
    db: AsyncSession | None,
    start_lsn: Optional[str],
    end_lsn: Optional[str],
) -> Optional[int]:
    """公开的 WAL 增量计算：``start`` → ``end`` 之间产生的字节数。

    缺任一端（非 PG / 探针失败）返回 None —— 与 ``StageRecord.wal_bytes``
    的「读不到 ≠ 0」口径一致，绝不把读不到写成 0。
    """
    return await _wal_diff(db, start_lsn, end_lsn)


class WalStageProbe:
    """写阶段的 WAL 探针：在**阶段自己的** session 边界内取起止 LSN。

    用法（pipeline）::

        probe = WalStageProbe(session_factory=async_session)
        await probe.start()
        ... 写阶段 ...
        await probe.stop()
        wal_bytes = probe.wal_bytes   # None = 读不到（非 PG / 无权限）

    为什么要单独一个类：LSN 必须在阶段进行中读（事务未提交、连接还在），
    而「怎么读、读失败怎么办、两次读怎么配」这三件事与 pipeline 编排无关。
    把它们放在这里，pipeline 只留 `start()` / `stop()` 两行，避免主文件膨胀
    （`pipeline.py` 在行数白名单上，见 `backend/scripts/file_size_whitelist.txt`）。

    非 PG / 连接失败：两次读都返回 None，`wal_bytes` 恒 None（读不到 ≠ 0 字节）。
    """

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory
        self._start_lsn: Optional[str] = None
        self._end_lsn: Optional[str] = None
        self._started = False
        self._stopped = False

    async def start(self) -> None:
        """取起点 LSN（新开一个短 session，读完即还）。"""
        try:
            async with self._session_factory() as db:
                self._start_lsn = await _get_wal_lsn(db)
        except Exception:  # noqa: BLE001 — 探针失败绝不阻断导入
            self._start_lsn = None
        self._started = True

    async def stop(self) -> None:
        """取终点 LSN 并算增量（同一口径：新开短 session）。"""
        if not self._started:
            return
        try:
            async with self._session_factory() as db:
                self._end_lsn = await _get_wal_lsn(db)
                self._wal_bytes = await _wal_diff(db, self._start_lsn, self._end_lsn)
        except Exception:  # noqa: BLE001 — 探针失败绝不阻断导入
            self._wal_bytes = None
        self._stopped = True

    @property
    def wal_bytes(self) -> Optional[int]:
        """起止之间的 WAL 增量；未 stop 或读不到时为 None。"""
        if not self._stopped:
            return None
        return getattr(self, "_wal_bytes", None)
