"""进程内导出闸（advanced-query-linkage-closure R8.6，ADR-AQL-14，design §3.5）。

单次导出最多 100 万行、最长 120 秒，行写入（openpyxl write_only）在事件循环里执行；平台目标并发 6000，不设上限时几个
大导出就能占满事件循环与连接池。闸按服务进程计（多进程部署时总上限 = 4 × 进程数，跨进程闸归运维，requirements §3）：

- 同一用户同时只能有 1 个导出，全进程同时不超过 :data:`MAX_EXPORTS_PER_PROCESS` 个；超出 → 429 ``EXPORT_BUSY``
  「已有导出在进行，请稍后再试」，不排队、不产生文件；
- :func:`acquire_export_slot` 非阻塞；:meth:`ExportSlot.release` 幂等（导出发完、出错或客户端断开都会调到，重复调用不会
  多放行一个名额）。

全进程计数 = 在途用户集合的大小（每个用户至多 1 个导出，二者等价）；不用 ``asyncio.Semaphore``：它在首次等待时绑定事件
循环，非阻塞获取还要读私有字段。判断与登记之间没有 ``await``，在单个事件循环里是原子的。业务视图导出
（``POST /api/custom-query/export``）与构建器导出（``POST /api/query/export-excel``）共用这一处计数（design §7）。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

#: 全进程同时进行的导出上限（R8.6）
MAX_EXPORTS_PER_PROCESS = 4
EXPORT_BUSY_MESSAGE = "已有导出在进行，请稍后再试"

#: 在途导出的用户（每人至多 1 个）
_IN_FLIGHT: set[str] = set()


class ExportSlot:
    """一个导出名额；``release`` 幂等。"""

    __slots__ = ("user_key", "_released")

    def __init__(self, user_key: str) -> None:
        self.user_key = user_key
        self._released = False

    @property
    def released(self) -> bool:
        return self._released

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        _IN_FLIGHT.discard(self.user_key)


def export_busy() -> HTTPException:
    return HTTPException(status_code=429, detail={"error_code": "EXPORT_BUSY", "message": EXPORT_BUSY_MESSAGE})


def acquire_export_slot(user_id: Any) -> ExportSlot:
    """取一个导出名额；本人已有在途导出或全进程已满 → 429 ``EXPORT_BUSY``（非阻塞）。"""
    key = str(user_id)
    if key in _IN_FLIGHT or len(_IN_FLIGHT) >= MAX_EXPORTS_PER_PROCESS:
        raise export_busy()
    _IN_FLIGHT.add(key)
    return ExportSlot(key)


def in_flight_count() -> int:
    """当前在途导出数（测试与运维观测用）。"""
    return len(_IN_FLIGHT)
