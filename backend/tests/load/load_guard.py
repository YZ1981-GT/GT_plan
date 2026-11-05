"""容量压测的专用库硬闸门（spec platform-heavy-jobs-and-capacity-closure 任务 0.3）。

R1.2：共享 PG 不运行写压测；容量测试的写操作必须指向**显式声明的可销毁数据库**。

`load_config.load_config()` 已经把「写压测必须 ``GT_LOAD_ALLOW_WRITES=1`` 且
``GT_LOAD_DISPOSABLE_ENV=YES``」做成配置层闸门。但真正发起 locust 的三个 runner
（run_baseline / run_final / run_post_implementation）此前对**目标库**零校验：只要环境里
那两个开关一开，写请求就会打到后端连的任何库——包括共享 PG。本模块补上发起前的闸门：

1. 只读压测：直接放行（locustfile 不会发任何写请求）。
2. 写压测：除两个开关外，还必须：
   - 显式声明 ``GT_LOAD_DISPOSABLE_DB_URL``（被压后端连的那个库），且
   - 它**不等于**当前进程的 ``DATABASE_URL``（共享/开发库），且
   - 它不在内置的「已知共享库名」黑名单里（audit_platform / 默认库）。

闸门只读环境、不连库、不发请求，纯校验，便于 runner 在起 locust **之前**调用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

#: 明确不是可销毁库的名字片段：共享业务库与各默认库。写压测指向它们一律拒绝。
_SHARED_DB_MARKERS = ("audit_platform", "postgres", "gt_plan", "metabase")


class LoadGuardError(RuntimeError):
    """发起压测前的硬闸门未通过（目标库不可销毁 / 声明缺失 / 指向共享库）。"""


@dataclass(frozen=True)
class LoadGuardDecision:
    allow_writes: bool
    disposable_db_url: str | None
    reason: str


def _flag(env: Mapping[str, str], key: str) -> bool:
    return (env.get(key) or "").strip().lower() in ("1", "true", "yes", "on")


def _db_name(url: str) -> str:
    """取 URL 末段库名（去掉查询串），用于黑名单与同一库判定。"""
    tail = url.rsplit("/", 1)[-1]
    return tail.split("?", 1)[0].strip().lower()


def evaluate_load_target(env: Mapping[str, str] | None = None) -> LoadGuardDecision:
    """校验本次压测是否可以安全发起；写压测指向共享/默认库时抛 ``LoadGuardError``。"""
    source = os.environ if env is None else env
    allow_writes = _flag(source, "GT_LOAD_ALLOW_WRITES")
    disposable_env = _flag(source, "GT_LOAD_DISPOSABLE_ENV")
    disposable_url = (source.get("GT_LOAD_DISPOSABLE_DB_URL") or "").strip()

    if not allow_writes:
        # 只读压测：确保没有「只开了 disposable 却忘了声明读写」的误配造成的假安全感；
        # 直接放行，locustfile 不会发写请求。
        return LoadGuardDecision(False, None, "只读压测：不发写请求，放行")

    if not disposable_env:
        raise LoadGuardError(
            "写压测必须设置 GT_LOAD_DISPOSABLE_ENV=YES（确认这是可销毁环境）"
        )
    if not disposable_url:
        raise LoadGuardError(
            "写压测必须显式声明 GT_LOAD_DISPOSABLE_DB_URL（被压后端连接的可销毁库）；"
            "共享 PG 严禁跑写压测"
        )

    name = _db_name(disposable_url)
    if not name:
        raise LoadGuardError("GT_LOAD_DISPOSABLE_DB_URL 解析不出库名，拒绝发起写压测")

    hit = next((marker for marker in _SHARED_DB_MARKERS if marker in name), None)
    if hit:
        raise LoadGuardError(
            f"GT_LOAD_DISPOSABLE_DB_URL 指向疑似共享/默认库（库名含“{hit}”：{name}），"
            "拒绝发起写压测；请用独立的可销毁库"
        )

    current = (source.get("DATABASE_URL") or "").strip()
    if current and _db_name(current) == name:
        raise LoadGuardError(
            "GT_LOAD_DISPOSABLE_DB_URL 与当前进程 DATABASE_URL 是同一个库，"
            "拒绝对运行库跑写压测"
        )

    return LoadGuardDecision(True, disposable_url, f"写压测指向可销毁库：{name}")


def require_safe_load_target(env: Mapping[str, str] | None = None) -> LoadGuardDecision:
    """runner 在起 locust 之前调用；不通过即抛 ``LoadGuardError``（调用方退出码 2）。"""
    return evaluate_load_target(env)


__all__ = [
    "LoadGuardDecision",
    "LoadGuardError",
    "evaluate_load_target",
    "require_safe_load_target",
]
