"""性能测试选择器的共享库硬闸门（spec platform-heavy-jobs-and-capacity-closure 任务 0.3）。

R1.2 / R1.5：性能测试不得无意中对共享 PG 跑写负载。``perf`` 用例分两类：

* **纯内存 / 只读**（如 ``tests/perf/test_workpaper_html_renderer_perf.py``，不碰 DB）：随便跑。
* **写真库**（如 ``test_procedure_performance.py``，``pg_only`` + ``perf``，会往
  ``DATABASE_URL`` 指的库插 5000 行再清理）：只有当这个库被**显式声明为可销毁**时才放行。

判据（与 ``tests.load.load_guard`` 同口径）：选中了「``perf`` ∧ ``pg_only``」的用例，且
``DATABASE_URL`` 是 PG 时，必须：

1. 设 ``GT_PERF_DISPOSABLE_DB=YES``（确认这是可销毁库），且
2. ``DATABASE_URL`` 的库名不在共享 / 默认库黑名单里。

不满足即返回报错文字（conftest 据此抛 ``pytest.UsageError``，整次运行失败），绝不静默跑到
共享库上。只读 / 非 PG 环境下该闸门不触发（pg_only 用例本就会被跳过）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from tests._pg_url import is_pg_url

#: 明确不是「可销毁性能库」的名字片段：共享业务库与各默认库。
_SHARED_DB_MARKERS = ("audit_platform", "postgres", "gt_plan", "metabase")


def _db_name(url: str) -> str:
    return url.rsplit("/", 1)[-1].split("?", 1)[0].strip().lower()


def perf_write_gate_error(
    db_url: str | None,
    env: Mapping[str, str],
    write_perf_nodeids: Sequence[str],
) -> str | None:
    """选中写真库的 perf 用例却未声明可销毁库时，返回报错文字；否则 None。

    ``write_perf_nodeids``：本次将要运行的「perf ∧ pg_only」用例 id（空 ⇒ 无需闸门）。
    """
    if not write_perf_nodeids:
        return None
    # 不是 PG：这些 pg_only 用例会被 conftest 的 pg 跳过逻辑整批跳掉，不会真写库。
    if not is_pg_url(db_url):
        return None

    sample = "、".join(list(write_perf_nodeids)[:5])
    more = f" 等 {len(write_perf_nodeids)} 个" if len(write_perf_nodeids) > 5 else ""
    disposable = (env.get("GT_PERF_DISPOSABLE_DB") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not disposable:
        return (
            "选中了会往数据库写大规模数据的性能用例（perf ∧ pg_only），但未声明可销毁库："
            f"{sample}{more}。请设 GT_PERF_DISPOSABLE_DB=YES 并把 DATABASE_URL 指向独立的"
            "可销毁库；共享 PG 严禁跑写性能测试（-m perf 时用 -m 'perf and not pg_only' 只跑纯内存项）。"
        )

    name = _db_name(db_url or "")
    hit = next((marker for marker in _SHARED_DB_MARKERS if marker in name), None)
    if hit:
        return (
            f"GT_PERF_DISPOSABLE_DB 已声明，但 DATABASE_URL 指向疑似共享/默认库"
            f"（库名含“{hit}”：{name}）：{sample}{more}。请换独立的可销毁库再跑写性能测试。"
        )
    return None


__all__ = ["perf_write_gate_error"]
