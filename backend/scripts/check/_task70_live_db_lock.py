# -*- coding: utf-8 -*-
"""任务 70 门禁的**第三类**逐字节锁剔除：共享真库的现状量。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 6.3

═══ 为什么需要第三类 ═══

本门已有两类剔除，各自的理由都写在门禁主文件里：

* :data:`VOLATILE_KEYS` —— 每轮都变的随机值与墙钟耗时；
* :data:`CENSUS_KEYS` —— 随**仓库演进**而变的普查量（全树 test 计数 / 引用者清单 /
  产物的 git 状态）。冻进锁里等于要求仓库停止演进（BP-71-8，同形缺陷在本 spec 被独立
  发现过三次）。

2026-11-05 实测出第三类：**随共享真库被别的会话写入而变的量**。
把报告在具备观测条件的环境里刷新、`--check` 当场 rc=0 之后约 40 分钟再跑，就有 **47 条
叶子路径**漂移 —— 因为另一个会话给 `xlsx/gt-d4-operating-revenue` 发布了一条新的
content representation：

====================================  =========  =========
路径                                    刷新时     40 分钟后
====================================  =========  =========
``working_paper_content_representation``   455        456
``working_paper_content_version``          435        436
``working_paper_sync_entry_state``          83         84
S6 ``failure_count``                        27         28
S6 ``unregistered_count``                  138        137
``measurement_is_environment_limited``   False       True
====================================  =========  =========

（`registered_entry_ids` 仍是 32，三集合恒等式仍成立 —— 那一条 entry 只是从
「没有 representation」的 reason 挪到了「artifact 文件不在本工作树」的 failure。）

⇒ 冻进锁里等于**要求共享库停止写入**。这与前两类是同一笔账：锁必须锁住「我们的判断与
派生逻辑」，而不是锁住「环境此刻长什么样」。第四批已经点名过这件事该怎么修
（「照本门已有的 CENSUS_KEYS / VOLATILE_KEYS 范式『剔除 ≠ 不管』，改为现算 + 语义断言」），
本模块就是那一步。

═══ 剔除 ≠ 不管 ═══

这些量在 `--check` 时**仍然现算**，并由 :func:`live_db_semantics` 逐条断言其**语义性质**：
快照前后覆盖同一批表 / 行数都是非负整数 / 注册分母非空 / 三集合之和 == planned /
两个直方图各自加总等于对应计数 / 环境分型可按同一函数重算。
语义性质不随别人写库而变，因此它们**继续锁死**。

🔴 :data:`LIVE_DB_KEYS` 自己也必须进锁（门禁把它写进 `live_db_contract.live_db_keys`）——
否则这个剔除集合就成了一个静默逃生口：往里加一条路径就能让任意漂移「合法」地绕过锁。
往里加路径会改变报告内容 ⇒ 必须显式 `--write` ⇒ 在 review 里看得见。

🔴 本模块**不放宽任何准入判据**：被剔的值照旧写进报告文件（剔除只作用于*比对*与
*digest*），守卫读 `report[...]` 看到的还是真实值。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Final, Mapping

if str(Path(__file__).resolve().parents[1]) not in sys.path:  # backend/scripts
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _census_lock  # noqa: E402  通用机制（点号路径剔除 / finalize_checks）

from scripts.check._task70_gate_env import (  # noqa: E402
    measurement_is_environment_limited,
)

#: 共享真库现状量的点号路径。列表元素段写 `[]`（机制见 `_census_lock.strip_census`）。
#:
#: 逐条都来自 2026-11-05 的实测漂移清单，**不是**预防性地把一整棵子树剔掉：
#: `register_from_manifest` 下的 `planned` / `accounting_identity_holds` /
#: `accounting_identity_formula` 三项**继续锁死** —— 它们分别来自 manifest、恒等式本身和
#: 公式字符串，不随别人写库而变，而它们正是本门最关键的三项结论。
LIVE_DB_KEYS: Final[frozenset[str]] = frozenset(
    {
        # ── 纯 DB 普查：前后两次快照的逐表行数
        "db_snapshot.row_counts_before",
        "db_snapshot.row_counts_after",
        # ── S6 registry 的实测结果（真跑侧）
        "supply_chain_walk.steps[].detail.registered_entry_ids",
        "supply_chain_walk.steps[].detail.registered_adapter_ids",
        "supply_chain_walk.steps[].detail.unregistered_count",
        "supply_chain_walk.steps[].detail.failure_count",
        "supply_chain_walk.steps[].detail.reason_kind_histogram",
        "supply_chain_walk.steps[].detail.failure_code_histogram",
        "supply_chain_walk.steps[].detail.artifact_environment",
        "supply_chain_walk.steps[].detail.measurement_is_environment_limited",
        "supply_chain_walk.steps[].detail.pilot_reason",
        # ── S8 的三项行数（第四批已从「冻结成 0」改成现算，这里把它们从锁里也放开）
        "supply_chain_walk.steps[].detail.entry_state_rows",
        "supply_chain_walk.steps[].detail.representation_upgrade_candidate_rows",
        "supply_chain_walk.steps[].detail.content_version_rows",
        # ── BP-70-2 / BP-70-3 对同一批事实的镜像
        "blocking_points[].measured.content_version_rows",
        "blocking_points[].measured.entry_state_rows",
        "blocking_points[].measured.representation_rows",
        "blocking_points[].measured.candidate_rows",
        "blocking_points[].measured.register_from_manifest.registered_entry_ids",
        "blocking_points[].measured.register_from_manifest.registered_adapter_ids",
        "blocking_points[].measured.register_from_manifest.unregistered_count",
        "blocking_points[].measured.register_from_manifest.failure_count",
        "blocking_points[].measured.register_from_manifest.reason_kind_histogram",
        "blocking_points[].measured.register_from_manifest.failure_code_histogram",
        "blocking_points[].measured.register_from_manifest.artifact_environment",
        "blocking_points[].measured.register_from_manifest.measurement_is_environment_limited",
        "blocking_points[].measured.register_from_manifest.pilot_reason",
        # ── 本契约节点自己的快照（同 `census_contract.measured` 的道理）
        "live_db_contract.measured",
    }
)

#: 被剔之后**仍然**逐字节锁死的轴 —— 写进报告，便于一眼看出锁没有被整体放弃。
STILL_LOCKED: Final[tuple[str, ...]] = (
    "register_from_manifest.planned（manifest 侧分母）",
    "register_from_manifest.accounting_identity_holds / accounting_identity_formula",
    "verdict.*（executed / unrunnable / state —— 本门的结论，变了就该重新刷新并复核）",
    "scenario_execution.tier_histogram 与 recorded_evidence（证据档位的结论）",
    "supply_chain_walk.first_hard_stop_step / blocked_step_ids（顺序不可交换）",
    "entry_derivation.* 与 scenario_denominator.*（manifest 派生，与库无关）",
)


def strip_live_db(node: Any, *, path: str = "") -> Any:
    """按点号路径剔除 :data:`LIVE_DB_KEYS`。"""
    return _census_lock.strip_census(node, LIVE_DB_KEYS, path=path)


def _s6_detail(db_facts: Mapping[str, Any]) -> dict[str, Any]:
    walk = db_facts.get("supply_chain_walk") or {}
    for step in walk.get("steps") or []:
        if step.get("step") == "S6":
            return dict(step.get("detail") or {})
    return {}


def live_db_semantics(db_facts: Mapping[str, Any]) -> dict[str, Any]:
    """共享库现状量的**语义性质**。现算，且不随别人写库而变 ⇒ 逐条进锁。

    🔴 `failing_checks` 逐条给名（`_census_lock.finalize_checks` 的约定）：变异检验要能
    断言「打红的**正是**预期那条」，否则 WRONG-TEST 与 RED 分不开。
    """
    snapshot = db_facts.get("db_snapshot") or {}
    before = dict(snapshot.get("row_counts_before") or {})
    after = dict(snapshot.get("row_counts_after") or {})
    detail = _s6_detail(db_facts)

    registered = len(detail.get("registered_entry_ids") or [])
    reasons = int(detail.get("unregistered_count") or 0)
    failures = int(detail.get("failure_count") or 0)
    planned = int(detail.get("planned") or 0)
    reason_histogram = dict(detail.get("reason_kind_histogram") or {})
    failure_histogram = dict(detail.get("failure_code_histogram") or {})
    artifact_env = dict(detail.get("artifact_environment") or {})

    counts = list(before.values()) + list(after.values())
    checks = {
        "snapshot_is_not_empty": bool(before) and bool(after),
        "snapshot_covers_the_same_tables_before_and_after": set(before) == set(after),
        "every_row_count_is_a_non_negative_int": all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in counts
        ),
        "registry_denominator_is_non_empty": planned > 0,
        "three_sets_sum_to_planned": registered + reasons + failures == planned,
        "reason_histogram_sums_to_its_count": sum(reason_histogram.values()) == reasons,
        "failure_histogram_sums_to_its_count": sum(failure_histogram.values()) == failures,
        "artifact_environment_verdict_is_recomputable": bool(
            detail.get("measurement_is_environment_limited")
        )
        == measurement_is_environment_limited(artifact_env),
    }
    return _census_lock.finalize_checks(
        checks,
        measured_registered=registered,
        measured_reasons=reasons,
        measured_failures=failures,
        measured_planned=planned,
    )


def build_live_db_contract(db_facts: Mapping[str, Any]) -> dict[str, Any]:
    """活库契约节点。组装复用 `_census_lock.build_census_contract`（同一形状）。"""
    detail = _s6_detail(db_facts)
    snapshot = db_facts.get("db_snapshot") or {}
    return _census_lock.build_census_contract(
        statement=(
            "共享真库的现状量（逐表行数、S6 registry 的实测结果）在 `--check` 时现算并断言"
            "语义性质，但**不进**逐字节比对 —— 冻进锁里等于要求共享库停止写入"
        ),
        census_keys=LIVE_DB_KEYS,
        why=(
            "2026-11-05 实测：报告在具备观测条件的环境里刷新、`--check` 当场 rc=0，约 40 分钟后"
            "再跑有 47 条叶子路径漂移 —— 另一个会话给 xlsx/gt-d4-operating-revenue 发布了一条新的"
            " content representation（representation 455→456 / content_version 435→436 /"
            " entry_state 83→84 / S6 failure 27→28 / reason 138→137）。与 BP-71-8（仓库演进）"
            "是同一笔账：锁必须锁住判断与派生逻辑，不是锁住环境此刻长什么样"
        ),
        excluded_is_not_unchecked=(
            "逐条仍现算并断言语义性质：快照前后覆盖同一批表 / 行数都是非负整数 / 注册分母非空 /"
            " 三集合之和 == planned / 两个直方图各自加总等于对应计数 / 环境分型可按同一函数重算。"
            "被剔的值照旧写进报告文件（剔除只作用于比对与 digest），守卫读到的还是真实值"
        ),
        still_locked=STILL_LOCKED,
        semantics=live_db_semantics(db_facts),
        measured={
            "row_counts_after": dict(snapshot.get("row_counts_after") or {}),
            "registered_entry_count": len(detail.get("registered_entry_ids") or []),
            "unregistered_count": detail.get("unregistered_count"),
            "failure_count": detail.get("failure_count"),
            "failure_code_histogram": dict(detail.get("failure_code_histogram") or {}),
            "reason_kind_histogram": dict(detail.get("reason_kind_histogram") or {}),
            "measurement_is_environment_limited": detail.get(
                "measurement_is_environment_limited"
            ),
        },
    )
