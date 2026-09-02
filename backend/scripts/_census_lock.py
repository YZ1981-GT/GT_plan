# -*- coding: utf-8 -*-
"""普查量与逐字节锁的分离机制（四个门共用）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure
被 Tasks 67 / 68 / 70 / 71 的门共用。拆分原因：同一机制原先在四个门里各抄一份，
把 6 个已登记文件顶穿了 `check_file_size.py` 的「不得再膨胀 >5%」阈值；钩子自身推荐的
首选方案就是「抽伴生模块」。

═══ 要解决的缺陷（同型三处 + 一处传递）═══

* **BP-71-8（Task 70）** —— `radiation_surface()` 把 `backend/tests` **全树** `test_*.py`
  计数（登记 2340）写进逐字节比对；
* **BP-72-8（Task 67）** —— `collect_inbound_obligations()` 把 `backend/data/**` 与源码里对
  本任务的引用普查结果（登记 12 行）写进比对；
* **BP-74-1（Task 68）** —— 按引用关系派生的辐射面 `surface_size`（登记 94）进了锁；
* **传递** —— Task 71 把 Task 70 的全树计数 live 值写进自己的锁。

后果一致：仓库任意位置新增一个 `test_*.py` 或落一份产物，就让上游门打红，表象是「上游报告
过期」。换目录、不写模块路径字面量都躲不开 —— 唯一的「规避」是不写守卫，等于放弃判据。
所以这是**判据形状**的缺陷，不是代码回归。

═══ 分离的形状 ═══

1. 各门自己登记 `CENSUS_KEYS`（**按点号路径**，不按裸键名 —— 报告里另有十余处正当的
   `digest` / `sha256` 同名量，按裸键名剔会把真正的 stale 轴一起放过）；
2. `--check` 逐字节比对前用 :func:`strip_census` 剔除（或按 `projections` 做**投影**，保留
   稳定核）；
3. 被剔的字段**仍然现算**，由各门自己的 `census_semantics()` 逐条断言语义性质 ——
   **剔除 ≠ 不管**；语义性质不随仓库演进，因此它们继续进锁；
4. `report_digest` 改在 census 剔除**之后**的内容上算 ⇒ 继续锁死「非普查内容不可手改」，
   但不再被仓库演进顶红；
5. :func:`build_census_contract` 把「剔了什么 / 为什么 / 语义断言结果 / **什么仍然锁死**」
   写进报告，让「放水」与「修复」在产物里可区分。

🔴 **为什么不整块剔掉普查节点**：整块剔会把「普查器/辐射面选取逻辑被改坏」一起放过。因此
节点里的**选取契约**（subject 名单、逐单元覆盖布尔、扫描根声明、`how`）继续逐字节锁死，
只有计数 / 成员清单 / digest 走 census。各门的 `census_semantics()` 里都有一条专门抓
「普查器被改成只返回写死的稳定核」的判据（否则投影比对照样绿）。
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

__all__ = [
    "strip_census",
    "coverage_from_members",
    "artifact_status_semantics",
    "surface_core_checks",
    "finalize_checks",
    "build_census_contract",
]


def strip_census(
    node: Any,
    census_keys: Iterable[str],
    *,
    projections: Mapping[str, Callable[[Any], Any]] | None = None,
    path: str = "",
) -> Any:
    """按**点号路径**剔除 `census_keys`，或按 `projections` 做投影。

    :param census_keys: 点号路径集合。列表元素的路径带 `[]` 段，于是 `properties.rows[].xxx`
        这类形态也能精确命中。
    :param projections: 路径 → 投影函数。命中投影的节点**保留稳定核**而不是整块剔除
        （Task 67 的 `inbound_obligations` 就走这条：真实目标那几行继续进锁，随仓库增长的
        尾巴被剔）。投影优先于剔除。
    """
    keys = census_keys if isinstance(census_keys, (set, frozenset)) else frozenset(census_keys)
    projected = projections or {}
    if isinstance(node, Mapping):
        out: dict[Any, Any] = {}
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if child in projected:
                out[key] = projected[child](value)
                continue
            if child in keys:
                continue
            out[key] = strip_census(value, keys, projections=projected, path=child)
        return out
    if isinstance(node, list):
        return [
            strip_census(value, keys, projections=projected, path=f"{path}[]") for value in node
        ]
    return node


def finalize_checks(checks: Mapping[str, bool], **extra: Any) -> dict[str, Any]:
    """把逐条语义断言收敛成统一形状：`{**checks, **extra, failing_checks, all_hold}`。

    🔴 `failing_checks` 必须逐条给名，不能只给一个 bool —— 变异检验要能断言「打红的**正是**
    预期那条」，否则 WRONG-TEST 与 RED 分不开。
    """
    return {
        **checks,
        **extra,
        "failing_checks": sorted(name for name, ok in checks.items() if not ok),
        "all_hold": all(checks.values()),
    }


def artifact_status_semantics(status: Mapping[str, str]) -> dict[str, Any]:
    """产物跟踪状态的**语义性质**（不随「提交/未提交」变化，故继续进锁）。

    `artifact_git_status` 是仓库状态派生量：同一份产物提交前是 `??`、提交后变 tracked-clean。
    冻进逐字节锁 ⇒「把产物入库」这个正确动作本身就会打红门（与 BP-71-8 同型的第五个实例）。
    真信号只有一条：**每个产物都在盘上** —— 「产物根本不存在」才是让挂进 CI 的 job 在干净
    checkout 下必挂的那件事，而它不随 commit 翻转。
    """
    return {
        "products": sorted(status),
        "product_count": len(status),
        "every_product_is_on_disk": all(v != "missing-on-disk" for v in status.values()),
        "missing_products": sorted(k for k, v in status.items() if v == "missing-on-disk"),
    }


def coverage_from_members(
    members: Mapping[str, Any], names: Iterable[str]
) -> dict[str, bool]:
    """逐名字的覆盖布尔：`names` 里每个名字是否被 `members` 的任一命中理由提到。

    🔴 抽成**纯函数**的唯一理由是可被喂合成输入：今天每个 pattern/subject 都真有命中者，
    于是「把它写成 `{name: True}` 恒真」与「从成员清单重算」在真实数据上**结果相同** ——
    等价变异，数值判据天生测不出（实测 GREEN）。喂一个「某名字零命中」的合成清单，恒真实现
    立刻现形。
    """
    return {
        str(name): any(str(name) in (why or ()) for why in members.values())
        for name in names
    }


def surface_core_checks(
    *,
    scanned: int,
    present: int,
    coverage: Mapping[str, bool],
    expected_names: Iterable[str],
    complete_key: str,
    every_key: str,
) -> tuple[dict[str, bool], list[str]]:
    """辐射面/普查面的**通用退化判据**（Tasks 68 / 70 / 71 同构，键名各门自定）。

    返回 `(checks, missing_names)`。四条通用判据各对应一种真实退化形态，都比「计数相等」
    更能抓到问题：

    * `walk_really_traversed_the_tree` —— scanner 被短路成不遍历时计数掉到 0；
    * `surface_is_not_empty` —— 空集恒真（假绿第⑥源）；
    * `surface_is_not_the_whole_tree` —— 退化成「跑无边界全量」，各门正文均明令禁止；
    * `complete_key` / `every_key` —— **必须分成两条**：空的 coverage 字典让
      「一条都没缺」恒真，只有「名单与期望集合相等」那条能抓到「coverage 被清空」。

    :param present: 辐射面/普查面的规模（各门字段名不同：`surface_size` /
        `referencing_test_file_count`）。
    :param complete_key: 覆盖完整性判据的键名（各门不同，且被守卫与变异锚点逐字断言，
        故由调用方传入而不是在此拼装）。
    """
    missing = sorted(name for name, hit in coverage.items() if not hit)
    checks = {
        "walk_really_traversed_the_tree": scanned > 1000,
        "surface_is_not_empty": present > 0,
        "surface_is_not_the_whole_tree": 0 < present < scanned,
        complete_key: set(coverage) == set(expected_names),
        every_key: bool(coverage) and not missing,
    }
    return checks, missing


def build_census_contract(
    *,
    statement: str,
    census_keys: Iterable[str],
    why: str,
    excluded_is_not_unchecked: str,
    still_locked: Iterable[str],
    semantics: Mapping[str, Any],
    measured: Mapping[str, Any],
    projection: str | None = None,
) -> dict[str, Any]:
    """普查契约节点：哪些键走 census、为什么、语义断言结果、以及**没有**被削弱的轴。

    `measured` 是**快照**，本身也应登记进 `CENSUS_KEYS`（路径 `census_contract.measured`），
    否则契约节点自己又成了一个会被仓库演进顶红的锁。
    """
    contract: dict[str, Any] = {
        "statement": statement,
        "census_keys": sorted(census_keys),
        "why": why,
        "excluded_is_not_unchecked": excluded_is_not_unchecked,
        "still_locked": list(still_locked),
        "semantics": dict(semantics),
        "measured": {**dict(measured), "note": "本节点是**快照**，不参与逐字节比对（见 `census_keys`）。"},
    }
    if projection is not None:
        contract["projection"] = projection
    return contract
