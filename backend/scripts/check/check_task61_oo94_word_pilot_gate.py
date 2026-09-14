"""Task 61 gate：真实 OnlyOffice 9.4 **F2 Word** pilot 的 fail-closed 门禁。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 61
Requirements: 4.11, 7.1, 7.3, 7.4, 7.6, 7.8, 8.10, 12.3, 12.10, 14.2, 14.3, 14.4,
14.6, 14.7, 14.8, 14.9, 14.16
Properties: **P30 / P31 / P32 / P33 / P34 / P55 / P56 / P58 / P62 / P65 / P69 / P71**

═══ 这道门存在的唯一理由：让「F2 Word pilot 已验证」不可能被声明出来 ═══

Task 60 为 F2-22 / F2-23 发布了 approved authority model 与 reviewed per-entry
contract，但 AC 12.1 六件前置里余下四件（non-null approved bundle / Task 15 finalize
的 published representation / 注册 adapter / 逐 scenario evidence）仍被 BP-10 ~ BP-15
阻断。Task 61 正文第一句因此写死了准入条件：

    只允许测试 Task 60 已 finalize、resolver 返回 published representation +
    approved F2 per-entry bundle 的 F2-22/F2-23；candidate、unapproved/
    missing-contract bundle 或 Task 6 probe 未真实通过时保持 UNVERIFIABLE，
    **不得借离线 engine 宣称通过**。

于是本任务能做的**唯一**诚实交付是：把「哪一条没跑、为什么没跑、缺的是环境还是实现」
变成逐条可追踪、可复算、非零退出的事实。结构照 Task 44 的 Excel 侧同款门
（`check_task44_oo94_excel_pilot_gate.py`），并按 Word 域补两条它没有的判据。

五条不可协商的设计
------------------

1. **准入状态真实反读，不硬编码**
   :func:`probe_admission_signals` 逐个调用生产符号：`contracts.available_contract_ids()`
   （生产契约清册真读）、`registry.build_production_registry()`（registry 真读）、
   `evidence.load_entry_manifest()`（source-backed manifest 真读）、
   真实 PG 的四张 definition/representation/candidate 表（**真查库**）。
   :func:`gate_probe_admission_is_state_sensitive` 用替身把全部信号翻成「已就绪」
   并复跑同一函数，断言判定确实改变 —— 「不是硬编码」由本门自己度量。

2. **Task 6 载体裁决的新鲜度是可执行判据，不是一句「已通过」**
   Task 6 的 contract 自带 `stale_policy`：environment / source_commit / runner /
   probe 模板 sha256 任一变化即裁决失效。:func:`probe_carrier_gate` 逐项现算
   （三份模板真算 sha256、HEAD 真读 git、OO build 真问容器），
   :func:`gate_probe_carrier_freshness_is_measured` 用替身翻一位再复跑，判定必须改变。
   🔴 这是 Task 44 没有的一格：Excel 侧的载体门（Task 5）没有把 stale 判据写进产物。

3. **probe 行是分母，不是清单**
   :data:`ALL_PROBE_SPECS` 的每条 `anchor` 必须逐字出现在 `tasks.md` 的 Task 61 正文里
   （:func:`assert_probes_anchored_in_task_text`）；scenario 侧再与
   **Task 44 已声明的 scenario 集合**双向锁死（:func:`scenario_denominator_facts`）——
   正文枚举项被删、或平台侧新增场景而这里没跟上，两个方向都立刻打红。
   🔴 反向锁**不能**用生产 required set：F2 Word lane 在 source-backed manifest 里
   0 条 entry（BP-10），`derive_for_manifest_entry` 无从调用，required set 恒空 ——
   拿空集做反向锁是重言式（假绿第③源）。Task 44 的 declared 集合是**已落地的**
   同族分母，用它做反向锁既非空也非自我比对。

4. **判定顺序不可交换**：schema 不可表达 → **载体在本 entry 上不可表达** →
   upstream-gap（`failed`）→ 未准入 → 真实黑盒未执行 → 执行记录缺失 → 真判据。
   upstream-gap 必须排在黑盒**之前**，否则接上真实 OO 会把「永远不会通过」的场景
   自动刷绿（本 spec 已四次实测）。:func:`ordering_facts` 把这条顺序同时按
   **源码位置**与**反事实行为**记下来。

5. **`passed` 只能由真实执行记录推导**
   任何执行记录里出现 `result` / `verdict` / `passed` / `status` 等键即被
   :class:`DocumentaryClaimRejected` 拒绝（AC 14.9 / Property 69）。gate 自己在运行时
   真跑一次这条拒绝路径（:func:`gate_probe_no_documentary_pass`）。

用法（仓库根，Windows PowerShell）::

    .\\.venv\\Scripts\\python.exe backend/scripts/check/check_task61_oo94_word_pilot_gate.py
    .\\.venv\\Scripts\\python.exe backend/scripts/check/check_task61_oo94_word_pilot_gate.py --json out.json
    .\\.venv\\Scripts\\python.exe backend/scripts/check/check_task61_oo94_word_pilot_gate.py \\
        --execution-records records.json

退出码：0 = 两个 F2 entry 全部 verified（今天不可能）；1 = 阻断 Tasks 62–64；
2 = 门自身的结构性失效（锚点脱钩 / 分母脱钩 / 生产符号消失 / 库读不到）——
比 1 更严重，因为那意味着这道门已经量不准了。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Final, Mapping, Sequence

_REPO: Final[Path] = Path(__file__).resolve().parents[3]
_BACKEND: Final[Path] = _REPO / "backend"
_SPEC_DIR: Final[Path] = (
    _REPO / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
_TASKS_MD: Final[Path] = _SPEC_DIR / "tasks.md"
_DESIGN_MD: Final[Path] = _SPEC_DIR / "design.md"

#: Task 60 的 Word lane 发布记录 —— 本门的 **entry 与阻断原因唯一真源**。
PUBLICATION_PATH: Final[Path] = (
    _BACKEND / "data/workpaper_sync_f2_word_lane_publication.json"
)
#: Task 6 的真实 OO 9.4 载体裁决 —— 本门的 **载体/锚点/环境唯一真源**。
CARRIER_CONTRACT_PATH: Final[Path] = (
    _BACKEND / "data/onlyoffice_word_sdt_carrier_contract.json"
)
#: Task 44 的 Excel 侧同款门 —— scenario 反向锁的对照分母。
TASK44_GATE_PATH: Final[Path] = (
    _BACKEND / "scripts/check/check_task44_oo94_excel_pilot_gate.py"
)
#: 生成数据文件（probe 注册表投影 + digest）。生成器 = `backend/scripts/gen/`。
REGISTRY_JSON: Final[Path] = (
    _BACKEND / "data/workpaper_task61_word_pilot_gate_probes.json"
)

#: gate 版本。改判据必须 +1（它进 evidence，旧 evidence 因此 stale）。
#:
#: `/2` 追加第七条 gate 自检 `gate.binding_constraint_is_measured`：用三臂反事实实测
#: **哪一条阻塞才是绑定约束**。首版把 BP-10（manifest 无 docx F2 entry）当成 adapter
#: 注册的绑定约束，2026-09-01 实测证伪 —— 见 :data:`BINDING_CONSTRAINTS`。
GATE_VERSION: Final[str] = "task61-gate/2"

#: Task 61 在 tasks.md 里的编号。用编号定位而**不是**行号：行号随上游任务增删漂移。
TASK_NUMBER: Final[int] = 61

#: 本门的下游：任一 probe 未通过即这两个 Wave 6 任务保持阻塞（正文第 4 条）。
DOWNSTREAM_BLOCKED_TASKS: Final[tuple[str, ...]] = ("62", "63", "64")


class GateStructuralError(RuntimeError):
    """门自身失效（锚点/分母/生产符号/库读脱钩）。比"有 probe 没通过"更严重。"""


class DocumentaryClaimRejected(GateStructuralError):
    """执行记录里出现了结果声明字段。

    🔴 单独一个异常类型而不是复用上面那个：`gate.no_documentary_pass` 这条 probe 要断言
    「拒绝确实发生过、且拒的正是这一条」。共享类型时"拒了别的东西"也能让它变绿
    （本 spec 前三轮点名的第①条教训：判「拒绝」不能只比异常类型）。
    """


class DatabaseUnreadable(GateStructuralError):
    """真实库读不到。

    🔴 **不降级成「本项目无此数据」**（AC 5.12 / fail-open 是本 spec 最贵的一类缺陷）：
    读不到库时本门无法判断 published representation 是否存在，因此它是结构性失效
    （退出码 2），而不是"所有场景 unverifiable"（退出码 1）。两者的区别是：
    后者会让人误以为"门跑过了、只是环境不足"。
    """


#: 执行记录里**禁止出现**的键 —— 它们全是"我宣布这条过了"的形态。
FORBIDDEN_RECORD_KEYS: Final[frozenset[str]] = frozenset(
    {"result", "verdict", "passed", "aggregate_result", "status", "outcome"}
)

#: probe 结果三态。与 V151 `ck_wpees_result` 同域。
RESULT_PASSED: Final[str] = "passed"
RESULT_FAILED: Final[str] = "failed"
RESULT_UNVERIFIABLE: Final[str] = "unverifiable"


def _ensure_backend_on_path() -> None:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    os.environ.setdefault("DB_DISABLE_SSL", "True")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 1. 两个 F2 lane entry（Task 60 的交付物，本门只读）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LaneRef:
    """一个 F2 Word lane entry 的定位信息。全部字段从 Task 60 发布记录现读。"""

    lane_entry_key: str
    entry_id: str
    contract_id: str
    wp_code: str
    template_ref: str
    #: `adapter_blocked_by` / `published_representation_blocked_by` 的并集（BP 编号）。
    blocked_by: tuple[str, ...]
    capability_target: str
    capability_verdict_stage: str
    second_pipeline_endpoints: tuple[str, ...]


def load_publication() -> Mapping[str, Any]:
    """读 Task 60 的 Word lane 发布记录。**不吞异常**。"""
    if not PUBLICATION_PATH.is_file():
        raise GateStructuralError(
            f"Task 60 的 Word lane 发布记录不存在: {PUBLICATION_PATH} —— "
            "本门的 entry 与阻断原因都取自它，缺它即本门无从度量"
        )
    payload = json.loads(PUBLICATION_PATH.read_bytes().decode("utf-8"))
    if not isinstance(payload, Mapping) or "entries" not in payload:
        raise GateStructuralError(f"{PUBLICATION_PATH.name}: 结构非法（缺 entries）")
    return payload


def lane_refs(publication: Mapping[str, Any] | None = None) -> tuple[LaneRef, ...]:
    """从 Task 60 发布记录现算两个 lane entry。

    🔴 不在本文件写第二份清单：写死 `("F2-22", "F2-23")` 之后，发布记录一改这里就
    悄悄过期，而"过期"在集合判据下看不出来（本 spec 反复点名的第二真源形态）。
    """
    pub = publication if publication is not None else load_publication()
    refs: list[LaneRef] = []
    for entry in pub["entries"]:
        contract = entry.get("contract") or {}
        blocked = tuple(
            sorted(
                set(entry.get("adapter_blocked_by") or ())
                | set(entry.get("published_representation_blocked_by") or ())
            )
        )
        refs.append(
            LaneRef(
                lane_entry_key=str(entry["lane_entry_key"]),
                entry_id=str(contract.get("contract_id") or ""),
                contract_id=str(contract.get("contract_id") or ""),
                wp_code=str(entry["wp_code"]),
                template_ref=str(entry["template_ref"]),
                blocked_by=blocked,
                capability_target=str(entry.get("capability_target") or ""),
                capability_verdict_stage=str(entry.get("capability_verdict_stage") or ""),
                second_pipeline_endpoints=tuple(entry.get("second_pipeline_endpoints") or ()),
            )
        )
    if not refs:
        raise GateStructuralError(
            f"{PUBLICATION_PATH.name}: entries 为空 —— 空分母会让本门恒成功（假绿）"
        )
    for ref in refs:
        if not ref.entry_id:
            raise GateStructuralError(
                f"{ref.lane_entry_key}: 发布记录里 contract.contract_id 为空 —— "
                "entry identity 丢了，本门不得替它编一个"
            )
    return tuple(refs)


# ═══════════════════════════════════════════════════════════════════════════
# 2. probe 声明（每条都锚定到 tasks.md 的 Task 61 正文）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProbeSpec:
    """一条 probe 声明。

    :param anchor: **逐字**出现在 Task 61 正文里的子串。它是本门与任务正文的锁。
    :param scenario_id: 非空即表示该 probe 的判定**委派**给生产
        :func:`~app.services.workpaper_sync.pilot_harness.run_scenario_oracle`，
        其 `evidence_inputs` 也从生产 oracle 现取（不在这里抄第二份）。
    :param evidence_inputs: 仅非 scenario probe 需要声明（生产侧没有对应 oracle）。
    :param production_refs: 该 probe 在生产上由哪些符号实现（`module:attr`）。
        plan 阶段逐个 import+getattr —— 符号改名/删除立刻抛。
    :param validator: 有执行记录时**真跑**的判据。None = 该 probe 由 scenario oracle 判。
    """

    probe_id: str
    probe_class: str
    anchor: str
    why: str
    requirements: tuple[str, ...] = ()
    properties: tuple[str, ...] = ()
    scenario_id: str | None = None
    evidence_inputs: tuple[str, ...] = ()
    production_refs: tuple[str, ...] = ()
    validator: Callable[..., tuple[bool, str]] | None = None


_SYNC: Final[str] = "app.services.workpaper_sync"


def _s(
    scenario_id: str,
    anchor: str,
    why: str,
    *,
    probe_class: str = "scenario",
    reqs: tuple[str, ...] = (),
    props: tuple[str, ...] = (),
    refs: tuple[str, ...] = (),
) -> ProbeSpec:
    """声明一条 scenario probe（判定委派生产 oracle）。"""
    return ProbeSpec(
        probe_id=f"scenario.{scenario_id}",
        probe_class=probe_class,
        anchor=anchor,
        why=why,
        requirements=reqs,
        properties=props,
        scenario_id=scenario_id,
        production_refs=refs or (f"{_SYNC}.pilot_harness:run_scenario_oracle",),
    )


# ── 2.1 scenario probe：Task 61 正文第 2 条（每个 F2 entry 运行）─────────────
#
# 🔴 anchor 逐字取自正文。中文与 ASCII 之间**没有空格**的地方（`quarantined拒绝
#    application/engine`）必须原样抄 —— 补一个空格就 MISS。

_DIRECTION_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _s(
        "html_to_oo", "HTML→OO",
        "HTML 侧 pending mutation → materialize 出以 current published canonical Word 为底的"
        "artifact；不得用模板重生成（AC 7.9）",
        reqs=("7.1", "7.3", "14.2"), props=("P30", "P65"),
    ),
    _s(
        "oo_to_html", "OO→HTML",
        "durable incoming → 只认 w:tag 的 extract → HTML projection；SDT 外内容永不回填",
        reqs=("7.1", "7.8", "14.2"), props=("P30", "P34"),
    ),
    _s(
        "identity_retention", "tag/row UUID retention",
        "平台通用 identity 保留族：往返后 identity inventory 不丢不重",
        reqs=("7.6", "14.4"), props=("P33",),
    ),
    _s(
        "word_sdt_tag_row_uuid_retention", "tag/row UUID retention",
        "Word 域专属：tagged SDT 的 tag 集合 / 层级 / 逐 tag 实例计数在真实 OO 9.4 往返后"
        "逐条保留（design §OO 9.4 pilot 门 第 5 步）",
        reqs=("7.6", "14.4"), props=("P33", "P34"),
    ),
    _s(
        "word_free_body_isolation", "Word-only保留",
        "design §OO 9.4 pilot 门 第 7 步：再次 materialize 后 SDT 外自由正文逐字保留",
        reqs=("7.3", "14.4"), props=("P31",),
    ),
)

_MERGE_CONFLICT_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _s(
        "different_field_merge", "different-field merge",
        "两个 participant 改不同字段：merge 只重写结构化岛，Word-only 区域不变",
        reqs=("7.3", "8.10"), props=("P31",),
    ),
    _s(
        "same_field_conflict_resolve", "same-field conflict/resolve",
        "同字段异值必须成 conflict 并可 resolve；不得静默取一边。AC 7.4 的 Word 形态在此："
        "同一 stable field key 的**多实例**值不一致时必须产生 duplicate_word_instance "
        "冲突并列出全部 OO 位置（Task 60 已在两份文档的 `${entityName}` 两实例上实测）",
        reqs=("7.4", "8.10", "14.6"), props=("P32", "P62"),
    ),
    _s(
        "refresh_required_reopen", "refresh/reopen",
        "refresh_required 后重开：client-confirmed base 与 server last-applied 不混同",
        reqs=("14.6",), props=("P62",),
    ),
)

_DEDUPE_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _s(
        "frozen_base_status_6_2_dedupe", "frozen-base status 6/2 dedupe",
        "同一 frozen base 上 status=6 与 status=2 的重复 callback 零多版本",
        reqs=("8.10", "14.3"), props=("P56",),
    ),
    _s(
        "same_application_higher_sequence_fold", "same-application higher-sequence fold不self-stale",
        "同 application 更高 sequence 折叠时不得把自己判成 stale",
        reqs=("8.10", "14.3"), props=("P56", "P62"),
    ),
)

_AUTHORIZATION_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _s(
        "cross_participant_idempotency_409", "同Idempotency-Key及不同kind/payload均409且不泄露旧ID",
        "跨 participant 复用同 Idempotency-Key、以及同 key 不同 kind/payload，两种都 409 "
        "且响应体不泄露旧 application/operation id",
        reqs=("4.11", "12.10"), props=("P58",),
    ),
    _s(
        "quarantined_rejects_application_and_engine", "quarantined拒绝application/engine",
        "quarantined incoming 在 application FK 与 engine 入口两侧都被拒；只可 "
        "download-only/expire/retention",
        reqs=("4.11", "7.8"), props=("P34",),
    ),
    _s(
        "wrong_prior_confirmation_bundle_fence_contributor_rejected",
        "prior confirmation/bundle/fence/contributor拒绝",
        "错误的 prior confirmation / bundle / write fence / contributor 四类各自被拒，"
        "且四条原因互不命中（前三轮教训①：判拒绝要比 error_code + 原因文案）",
        reqs=("4.11", "8.10"), props=("P58",),
    ),
)

_ROLLBACK_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _s(
        "opaque_version_rollback_no_numeric_collision",
        "opaque version UUID rollback与跨wp同numeric revision无碰撞",
        "content version scope 只用 opaque UUID；跨 wp 同 numeric revision 不构成碰撞",
        reqs=("12.10", "14.8"), props=("P71",),
    ),
    _s(
        "rollback", "rollback与 Word-only保留",
        "rollback 到旧 representation 后 Word-only 自由正文仍逐字保留",
        reqs=("7.3", "14.8"), props=("P31", "P71"),
    ),
)

_RECOVERY_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _s(
        "browser_crash_no_userdata_recovery_case", "browser crash no-userdata recovery case",
        "浏览器崩溃且无 userdata 时生成 recovery case；🔴 claim 前不得伪造 operation id",
        reqs=("14.7", "14.9"), props=("P55", "P69"),
    ),
    _s(
        "authorization_first_recovery_claim", "authorization-first claim",
        "recovery claim 走 authorization-first 顺序：scope-index 只读 → 交叉比对 → "
        "action/lease/fence → 业务读 → 副作用",
        reqs=("4.11",), props=("P58",),
    ),
    _s(
        "download_only_zero_three_entities", "download-only 三实体为 0",
        "download-only 路径的 application / operation / representation 三实体恒为 0",
        reqs=("12.10", "14.9"), props=("P69",),
    ),
)

#: Task 61 正文第 3 条：**无条件运行**的 close 族（9 条）。
_CLOSE_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _s(
        "single_participant_close", "single close",
        "单人关闭：exactly-one close-capture",
        probe_class="close_aspect", reqs=("14.7",), props=("P55",),
    ),
    _s(
        "two_user_close_order_a_then_b", "两个用户两种关闭顺序",
        "两人关闭顺序 A→B",
        probe_class="close_aspect", reqs=("14.7",), props=("P55",),
    ),
    _s(
        "two_user_close_order_b_then_a", "两个用户两种关闭顺序",
        "两人关闭顺序 B→A（与上一条**分开断言**：写成集合成员会被另一个顶住，"
        "前三轮教训③）",
        probe_class="close_aspect", reqs=("14.7",), props=("P55",),
    ),
    _s(
        "b_close_before_a_forcesave_terminal", "A terminal 前/后 B close",
        "A 的 forcesave 进入 terminal **之前** B 关闭",
        probe_class="close_aspect", reqs=("14.7",), props=("P55", "P56"),
    ),
    _s(
        "b_close_after_a_forcesave_terminal", "A terminal 前/后 B close",
        "A 的 forcesave 进入 terminal **之后** B 关闭",
        probe_class="close_aspect", reqs=("14.7",), props=("P55", "P56"),
    ),
    _s(
        "close_leader_revoked_successor_exactly_one",
        "leader promotion前revoke/expire后的successor",
        "leader 在 promotion 前被 revoke/expire，successor 仍只产生一次 close-capture",
        probe_class="close_aspect", reqs=("4.11", "14.7"), props=("P58",),
    ),
    _s(
        "close_leader_revoked_no_successor_recovery_required",
        "无successor`recovery_required`",
        "无 successor 时结算为 recovery_required，不是静默丢弃",
        probe_class="close_aspect", reqs=("14.7", "14.9"), props=("P69",),
    ),
    _s(
        "close_reconciler_reentrant_exactly_one_capture",
        "`reconcile_close_intents()` 重入与适用路径最终 exactly-one close-capture",
        "reconciler 重入安全；适用路径最终 exactly-one close-capture",
        probe_class="close_aspect", reqs=("14.7",), props=("P55",),
    ),
)

SCENARIO_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _DIRECTION_PROBES
    + _MERGE_CONFLICT_PROBES
    + _DEDUPE_PROBES
    + _AUTHORIZATION_PROBES
    + _ROLLBACK_PROBES
    + _RECOVERY_PROBES
    + _CLOSE_PROBES
)


# ── 2.2 非 scenario probe：准入 / 载体门 / 证据联合 / 复原 ────────────────────


def _need(record: Mapping[str, Any], *keys: str) -> tuple[bool, str]:
    """执行记录里必须同时有这些键且非空。返回 `(ok, 诊断)`。"""
    missing = [k for k in keys if not record.get(k)]
    if missing:
        return False, f"执行记录缺 {missing}"
    return True, ""


def validate_evidence_union(
    facts: "LaneFacts", record: Mapping[str, Any]
) -> tuple[bool, str]:
    """正文第 3 条要求的**证据联合**：六路证据必须同时到位（AC 14.2/14.3/14.16）。

    🔴 交叉复用的判据落在**三个 typed slot digest 逐项**与 Task 60 冻结的
    `bundle_slot_plan` 相等 —— 而**不是**比一个 `definition_bundle_sha256` 常量：
    BP-11 未解除前 `slot_ref` 恒为 null ⇒ 真 bundle sha256 在库里根本不存在，
    拿一个不存在的值做等值判据会永远打红（假红与假绿一样有害）。
    """
    ok, why = _need(
        record,
        "browser_trace_path",
        "recovery_application_operation_timeline_path",
        "db_timestamps",
        "published_result_representation",
        "definition_bundle_sha256",
        "docx_unzip_tag_inventory",
    )
    if not ok:
        return False, why
    inventory = record.get("docx_unzip_tag_inventory")
    if not isinstance(inventory, Mapping) or not inventory:
        return False, "docx_unzip_tag_inventory 必须是非空对象（空集恒等价 = 假绿第⑥源）"
    slots = (record.get("published_result_representation") or {}).get(
        "definition_bundle_slots"
    )
    if not isinstance(slots, Mapping) or set(slots) != {
        "template",
        "instrumentation",
        "contract",
    }:
        return False, f"typed slots 必须恰是 template/instrumentation/contract，实得 {slots!r}"
    if not facts.frozen_slot_digests:
        return False, "本 entry 的 bundle_slot_plan 为空 —— 空计划恒等价，不得判过"
    drift = sorted(
        name
        for name, frozen in facts.frozen_slot_digests.items()
        if str((slots.get(name) or {}).get("sha256")) != str(frozen)
    )
    if drift:
        return (
            False,
            f"以下 typed slot digest 与本 entry 冻结的不符：{drift} —— 每个 F2 entry 保存"
            "自身 bundle digest，不交叉复用（Task 60 正文 / Property 70）",
        )
    return (
        True,
        f"六路证据齐备；{len(facts.frozen_slot_digests)} 个 typed slot digest 与本 entry "
        "冻结值逐项相等",
    )


def validate_distinct_application_ids(
    facts: "LaneFacts", record: Mapping[str, Any]
) -> tuple[bool, str]:
    """逐 scenario **独立** application ID：不交叉复用（正文第 3 条）。"""
    per_scenario = record.get("application_ids_by_scenario")
    if not isinstance(per_scenario, Mapping) or not per_scenario:
        return False, "缺 application_ids_by_scenario（空集恒等价，不得判过）"
    declared = {s.scenario_id for s in SCENARIO_PROBES if s.scenario_id}
    unknown = sorted(set(per_scenario) - declared)
    if unknown:
        return False, f"出现未声明的 scenario：{unknown}"
    seen: dict[str, str] = {}
    for scenario_id, app_id in sorted(per_scenario.items()):
        text = str(app_id)
        if not text:
            return False, f"{scenario_id} 的 application id 为空"
        if text in seen:
            return (
                False,
                f"{scenario_id} 与 {seen[text]} 复用了同一 application id {text} —— "
                "逐 scenario 必须独立",
            )
        seen[text] = scenario_id
    if len(per_scenario) != len(declared):
        return (
            False,
            f"application id 覆盖 {len(per_scenario)}/{len(declared)} 条 scenario —— "
            "覆盖计数不足即分母缩小",
        )
    return True, f"{len(seen)} 条 scenario 各有独立 application id"


def validate_full_restoration(
    facts: "LaneFacts", record: Mapping[str, Any]
) -> tuple[bool, str]:
    """正文第 3 条末句：**完整复原数据**。前后快照 digest 必须相等且非空。"""
    before = record.get("restoration_snapshot_before")
    after = record.get("restoration_snapshot_after")
    if not before or not after:
        return False, "缺 restoration_snapshot_before / after"
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return False, "复原快照必须是对象"
    if not before or set(before) != set(after):
        return False, f"两侧快照键集不同：{sorted(before)} vs {sorted(after)}"
    drift = sorted(k for k in before if before[k] != after[k])
    if drift:
        return False, f"以下条目未复原：{drift}"
    return True, f"{len(before)} 项快照逐项相等（复原完整）"


NON_SCENARIO_PROBES: Final[tuple[ProbeSpec, ...]] = (
    ProbeSpec(
        probe_id="admission.published_representation_and_approved_bundle",
        probe_class="admission",
        anchor="只允许测试 Task 60 已 finalize",
        why=(
            "准入条件：resolver 必须返回 published representation + approved F2 per-entry "
            "bundle。四个信号（生产契约清册 / source-backed manifest / adapter registry / "
            "真实库四张表）全部真读，任一缺失即该 entry 不进入测试范围"
        ),
        requirements=("12.3", "12.10"),
        properties=("P69",),
        production_refs=(
            f"{_SYNC}.contracts:available_contract_ids",
            f"{_SYNC}.adapters.registry:build_production_registry",
            f"{_SYNC}.evidence:load_entry_manifest",
        ),
    ),
    ProbeSpec(
        probe_id="admission.carrier_gate_probe_really_passed",
        probe_class="admission",
        anchor="Task 6 probe未真实通过时保持 UNVERIFIABLE",
        why=(
            "Task 6 的 contract 自带 stale_policy：environment / source_commit / runner / "
            "probe 模板 sha256 任一变化即裁决失效。本 probe 逐项现算而不是读一句"
            "「probe_verdict: passed」"
        ),
        requirements=("7.6", "14.4", "14.16"),
        properties=("P33", "P71"),
        production_refs=(f"{_SYNC}.word_instrumentation:WordSdtCarrierGate",),
    ),
    ProbeSpec(
        probe_id="admission.no_offline_engine_claim",
        probe_class="admission",
        anchor="不得借离线 engine宣称通过",
        why=(
            "离线 engine（`validate_candidate_offline`）在缺 approved bundle 时是**唯一**"
            "允许的动作，但它的通过**不得**被计入本门任何 scenario。判据落在："
            "`WordEngineBinding.assert_may_publish()` 在 offline 模式下必须抛"
        ),
        requirements=("7.8", "12.3"),
        properties=("P30", "P34"),
        production_refs=(f"{_SYNC}.word_sdt_engine:WordEngineBinding",),
    ),
    ProbeSpec(
        probe_id="evidence.union_of_six_sources",
        probe_class="evidence",
        anchor="联合浏览器、recovery+application+operation timeline、DB",
        why="六路证据必须同时到位；缺一路即不得判过（AC 14.2 / 14.3 / 14.16）",
        requirements=("14.2", "14.3", "14.16"),
        properties=("P55", "P58", "P69"),
        evidence_inputs=("browser_trace", "onlyoffice_forcesave", "db_snapshot"),
        production_refs=(f"{_SYNC}.evidence:load_entry_manifest",),
        validator=validate_evidence_union,
    ),
    ProbeSpec(
        probe_id="evidence.distinct_application_ids_per_scenario",
        probe_class="evidence",
        anchor="逐 scenario 记录独立 application IDs/evidence",
        why="逐 scenario 独立 application ID，不交叉复用；覆盖计数必须等于声明数",
        requirements=("12.10", "14.9"),
        properties=("P69",),
        evidence_inputs=("db_snapshot",),
        production_refs=(f"{_SYNC}.pilot_harness:run_scenario_oracle",),
        validator=validate_distinct_application_ids,
    ),
    ProbeSpec(
        probe_id="evidence.full_restoration",
        probe_class="evidence",
        anchor="完整复原数据",
        why="真实库跑过之后必须完整复原；快照键集与逐项值都要相等",
        requirements=("14.9",),
        properties=("P69",),
        evidence_inputs=("db_snapshot",),
        production_refs=(f"{_SYNC}.evidence:load_entry_manifest",),
        validator=validate_full_restoration,
    ),
    ProbeSpec(
        probe_id="boundary.word_adapter_has_not_landed",
        probe_class="boundary",
        anchor="禁止 paragraph fallback",
        why=(
            "PHASE D 的反向判据：本门未全绿之前 `adapters/word.py` 与 `adapters/word` "
            "都不得存在，且 `PENDING_ENGINE_ADAPTERS` 的 docx 行必须仍点名 Task 61。"
            "🔴 这条 probe 在 gate 未通过时**必须 passed** —— 它度量的是"
            "「adapter 没有提前落地」，不是「adapter 已落地」"
        ),
        requirements=("7.8", "12.3"),
        properties=("P34",),
        production_refs=(f"{_SYNC}.adapters.registry:PENDING_ENGINE_ADAPTERS",),
    ),
    ProbeSpec(
        probe_id="boundary.downstream_tasks_stay_blocked",
        probe_class="boundary",
        anchor="Tasks 62–64 阻塞",
        why=(
            "正文第 4 条：失败/UNVERIFIABLE 时 Tasks 62–64 阻塞。本 probe 把"
            "「阻塞结论」变成从 probe 行现算的事实而不是一句结论"
        ),
        requirements=("12.3",),
        properties=("P69",),
        production_refs=(f"{_SYNC}.adapters.registry:DELIVERED_PER_ENTRY_CONTRACTS",),
    ),
)


PER_ENTRY_PROBES: Final[tuple[ProbeSpec, ...]] = SCENARIO_PROBES + NON_SCENARIO_PROBES

#: gate 自检 probe（不按 entry 展开）。
GATE_PROBES: Final[tuple[ProbeSpec, ...]] = (
    ProbeSpec(
        probe_id="gate.ordering_upstream_gap_before_black_box",
        probe_class="gate",
        anchor="保持 UNVERIFIABLE",
        why=(
            "upstream-gap 判 failed 且排在黑盒判定之前 —— 源码位置 + 反事实行为双侧实测；"
            "顺序交换会让缺实现的场景在接上真实 OO 后自动刷绿（本 spec 已四次实测）"
        ),
        requirements=("14.9",),
        properties=("P69",),
    ),
    ProbeSpec(
        probe_id="gate.no_documentary_pass",
        probe_class="gate",
        anchor="14.9",
        why=(
            "执行记录里出现结果声明字段即拒；gate 自己在运行时真跑一次这条拒绝路径，"
            "拒绝没发生就不给这条 probe 判 passed"
        ),
        requirements=("14.9",),
        properties=("P69",),
    ),
    ProbeSpec(
        probe_id="gate.admission_is_state_sensitive",
        probe_class="gate",
        anchor="只允许测试 Task 60 已 finalize",
        why=(
            "用替身把全部准入信号翻成「已就绪」并复跑同一函数，准入判定必须改变 —— "
            "证明本门真实反读状态而不是硬编码 false"
        ),
        requirements=("12.3",),
        properties=("P69",),
    ),
    ProbeSpec(
        probe_id="gate.carrier_freshness_is_measured",
        probe_class="gate",
        anchor="Task 6 probe未真实通过时保持 UNVERIFIABLE",
        why=(
            "把载体门的任一新鲜度输入翻一位（模板 digest / source_commit / OO build）"
            "并复跑，裁决必须变 stale —— 证明这不是读一句 `probe_verdict: passed`"
        ),
        requirements=("14.16",),
        properties=("P71",),
    ),
    ProbeSpec(
        probe_id="gate.denominator_locked_against_task44",
        probe_class="gate",
        anchor="均无条件运行",
        why=(
            "scenario 分母与 Task 44 已声明集合双向锁死。🔴 反向锁不能用生产 required "
            "set：F2 Word lane 在 manifest 里 0 条 entry（BP-10）⇒ required set 恒空，"
            "空集反向锁是重言式"
        ),
        requirements=("12.10",),
        properties=("P69",),
    ),
    ProbeSpec(
        probe_id="gate.mutation_four_state",
        probe_class="gate",
        anchor="14.7",
        why="变异检验四态：declared==executed 且全部 RED，否则本门不认为守卫成立",
        requirements=("14.7",),
        properties=("P69",),
    ),
    ProbeSpec(
        probe_id="gate.binding_constraint_is_measured",
        probe_class="gate",
        anchor="resolver返回 published representation",
        why=(
            "三臂反事实实测「哪一条阻塞才是绑定约束」。🔴 首版把 BP-10（manifest 无 docx "
            "F2 entry）当绑定约束，2026-09-01 实测证伪：内存翻掉 manifest 后 F2 的拒绝"
            "原因与 Task 76 已完整 provision 的 b60 Excel pilot **逐字相等** ⇒ 真正的"
            "绑定约束是 published representation 供给（平台级 0 行），不是 F2 专属欠账。"
            "没有这条 probe，「registry 无 docx adapter」会被当成 word_bulk 门的证据，"
            "而它实际上在门被跨越后仍恒为 0 ⇒ 重言式（假绿第③源）"
        ),
        requirements=("7.3", "12.3"),
        properties=("P65", "P69"),
        production_refs=(
            f"{_SYNC}.adapters.registry:build_production_registry",
            f"{_SYNC}.adapters.registry:_describe_entry_supply",
        ),
    ),
)

ALL_PROBE_SPECS: Final[tuple[ProbeSpec, ...]] = PER_ENTRY_PROBES + GATE_PROBES

#: Task 61 正文要求「独立验证」的 12 条 Property。封闭元组 —— 少一条即结构性失效。
DECLARED_PROPERTIES: Final[tuple[str, ...]] = (
    "P30", "P31", "P32", "P33", "P34", "P55",
    "P56", "P58", "P62", "P65", "P69", "P71",
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. scenario 分母：与 Task 44 已声明集合**双向**锁死
# ═══════════════════════════════════════════════════════════════════════════

#: 平台 oracle 里**本 lane 结构性不适用**的场景。每条的 `reason` 必须是**实测事实**
#: （不是"感觉不相关"），`measured_from` 指出这条事实由哪个真源现算。
#:
#: 🔴 出现在这张表里的场景**不是 probe** —— 它们是"分母之外"的登记，不参与 passed 计数。
OUT_OF_LANE_SCENARIOS: Final[Mapping[str, Mapping[str, str]]] = {
    "dynamic_row_add_delete_reorder_copy": {
        "reason": (
            "本 lane 无行域字段：Task 60 发布记录现算 row_scoped_fields_total=0（两份契约"
            "都没有 repeaters），且 Task 6 把 row_sdt 载体判 failed / blocked ⇒ 行动态族"
            "在 F2-22/F2-23 上没有载体可承载"
        ),
        "measured_from": "workpaper_sync_f2_word_lane_publication.json:counters.row_scoped_fields_total",
        "owner_task": "67",
    },
    "dynamic_column_stable_keys": {
        "reason": (
            "同上：Word tagged-SDT 契约没有列维度（stable key 是 `段/字段` 而不是"
            "`行/列`），F2-22/F2-23 的 word/document.xml 里 w:tbl 计数为 0"
        ),
        "measured_from": "onlyoffice_word_sdt_carrier_contract.json:pilot_template_row_carrier_gap.fact",
        "owner_task": "67",
    },
    "single_html_no_blank_oo_artifact": {
        "reason": (
            "single-mode 族只适用于被裁决为 single_html 的 entry；两个 F2 entry 的"
            "capability_target 现算均为 bidirectional 且 html_counterpart_verdict=exists"
        ),
        "measured_from": "workpaper_sync_f2_word_lane_publication.json:entries[].capability_target",
        "owner_task": "63",
    },
    "authoritative_revision_conflict": {
        "reason": (
            "🔴 BP-23（本门实测）：Task 61 正文的场景枚举**没有**列这一条，Task 44 的"
            "Excel 侧门也没有声明它 ⇒ 它是**平台级未归属**场景，不是本 lane 的豁免。"
            "本门如实登记而不替它编一个 anchor（编 anchor 会破坏正文分母锁）"
        ),
        "measured_from": "check_task44_oo94_excel_pilot_gate.py:_SCENARIO_PROBES",
        "owner_task": "67",
    },
    "no_silent_overwrite": {
        "reason": (
            "🔴 BP-23（本门实测）：同上 —— Task 61 正文与 Task 44 的门都没有声明它。"
            "登记为平台级未归属，由 Task 67 的 structural pre-reconcile 统一裁决"
        ),
        "measured_from": "check_task44_oo94_excel_pilot_gate.py:_SCENARIO_PROBES",
        "owner_task": "67",
    },
}


def load_task44_declared_scenarios() -> frozenset[str]:
    """现读 Task 44 门的 declared scenario 集合（反向锁的对照分母）。

    🔴 用 import 而不是正则扫源码：正则会把注释里出现的 scenario 名也算进来，
    而"注释里提到"不等于"声明了 probe"（本 spec 教训②：判单一真源不能 grep 符号名）。
    """
    _ensure_backend_on_path()
    if not TASK44_GATE_PATH.is_file():
        raise GateStructuralError(
            f"Task 44 的 Excel 侧门不存在: {TASK44_GATE_PATH} —— 本门的反向分母锁失去对照"
        )
    spec = importlib.util.spec_from_file_location(
        "_task61_task44_gate", TASK44_GATE_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - 结构性
        raise GateStructuralError(f"无法加载 {TASK44_GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 需要模块在 sys.modules 里
    spec.loader.exec_module(module)
    declared = {
        str(p.scenario_id) for p in module._SCENARIO_PROBES if p.scenario_id
    }
    if not declared:
        raise GateStructuralError(
            "Task 44 的 declared scenario 集合为空 —— 空集做反向锁是重言式"
        )
    return frozenset(declared)


def scenario_denominator_facts() -> dict[str, Any]:
    """scenario probe ↔ 生产 oracle ↔ Task 44 declared 集合，**三向**核对。

    * 正向：声明了 probe 但生产 oracle 表里没有 ⇒ 结构性失效（被测对象不存在）；
    * 反向：Task 44 已声明的场景这里既没 probe 也没登记豁免 ⇒ 分母悄悄缩小；
    * Word 族：`pilot_harness` 里 family 为 word 的场景**必须**全部有 probe
      （本 lane 是 Word 域，漏掉 Word 族等于漏掉本任务的核心）。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync import pilot_harness as ph

    declared = {str(s.scenario_id) for s in SCENARIO_PROBES if s.scenario_id}
    oracles = set(ph.SCENARIO_ORACLES)
    unknown = sorted(declared - oracles)
    if unknown:
        raise GateStructuralError(
            f"以下 scenario probe 在生产 SCENARIO_ORACLES 里没有 oracle：{unknown}"
        )

    task44 = load_task44_declared_scenarios()
    excused = set(OUT_OF_LANE_SCENARIOS)
    shrunk = sorted(task44 - declared - excused)
    if shrunk:
        raise GateStructuralError(
            f"Task 44 已声明的 {shrunk} 在本门既无 probe 也无 OUT_OF_LANE 登记 —— "
            "分母会悄悄缩小（本 spec 反复点名的假绿第①源）"
        )

    word_family = {
        str(s.scenario_id)
        for s in ph.all_declared_scenarios()
        if str(getattr(getattr(s, "family", None), "value", getattr(s, "family", ""))) == "word"
    }
    missing_word = sorted(word_family - declared)
    if missing_word:
        raise GateStructuralError(
            f"Word 族场景 {missing_word} 没有 probe —— 本 lane 是 Word 域，"
            "漏掉 Word 族等于漏掉本任务的核心"
        )

    overlap = sorted(excused & declared)
    if overlap:
        raise GateStructuralError(
            f"{overlap} 同时出现在 probe 与 OUT_OF_LANE 登记里 —— 两者必须互斥，"
            "否则「豁免」会顶住「未通过」"
        )
    for scenario_id, row in OUT_OF_LANE_SCENARIOS.items():
        if scenario_id not in oracles:
            raise GateStructuralError(
                f"OUT_OF_LANE 登记的 {scenario_id} 不在生产 oracle 表里 —— 登记表已过期"
            )
        for field_name in ("reason", "measured_from", "owner_task"):
            if not str(row.get(field_name) or "").strip():
                raise GateStructuralError(
                    f"OUT_OF_LANE[{scenario_id}] 缺 {field_name} —— 缺场景必须有 owner "
                    "与实测出处"
                )
    return {
        "declared_scenario_probes": len(declared),
        "production_oracles": len(oracles),
        "task44_declared": len(task44),
        "out_of_lane_registered": len(excused),
        "word_family_scenarios": sorted(word_family),
        "not_declared_anywhere": sorted(oracles - declared - excused),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. 与 tasks.md / design.md 的真源锁
# ═══════════════════════════════════════════════════════════════════════════

_TASK_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"^- \[[ x~\-]\] (\d+)\. ", flags=re.MULTILINE
)


def read_task_body(task_number: int = TASK_NUMBER, *, text: str | None = None) -> str:
    """从 tasks.md 抠出某个任务的正文（含标题行，不含下一任务）。

    🔴 按**任务编号**定位而不是行号：行号随上游任务增删漂移。checkbox 状态用 `[ x~-]`
    通配 —— 本门不因 Task 61 被勾选而失效（勾选是簿记，不是事实）。
    """
    body = text if text is not None else _TASKS_MD.read_bytes().decode("utf-8")
    starts: list[tuple[int, int]] = [
        (int(m.group(1)), m.start()) for m in _TASK_HEADER_RE.finditer(body)
    ]
    for index, (number, start) in enumerate(starts):
        if number != task_number:
            continue
        stop = starts[index + 1][1] if index + 1 < len(starts) else len(body)
        section = body.find("\n### ", start)
        if 0 <= section < stop:
            stop = section
        return body[start:stop]
    raise GateStructuralError(
        f"tasks.md 里找不到 Task {task_number} —— 本门与任务正文脱钩"
    )


def assert_probes_anchored_in_task_text(
    specs: Sequence[ProbeSpec] = ALL_PROBE_SPECS, *, task_body: str | None = None
) -> dict[str, int]:
    """每条 probe 的 `anchor` 必须逐字出现在 Task 61 正文里。

    这是本门的**分母锁**：正文枚举项被改写/删除时立刻抛，而不是静默少跑一条。
    返回 anchor → 出现次数（共享 anchor 是允许的：正文用一句话覆盖两条场景时
    「两个用户两种关闭顺序」本身就只有一处）。
    """
    body = task_body if task_body is not None else read_task_body()
    counts: dict[str, int] = {}
    missing: list[str] = []
    for spec in specs:
        hits = body.count(spec.anchor)
        counts[spec.anchor] = hits
        if hits == 0:
            missing.append(f"{spec.probe_id} -> {spec.anchor!r}")
    if missing:
        raise GateStructuralError(
            "以下 probe 的锚点在 Task 61 正文里找不到（本门已与任务正文脱钩）：\n  "
            + "\n  ".join(missing)
        )
    return counts


def task_requirement_ids(*, task_body: str | None = None) -> tuple[str, ...]:
    """Task 61 `_Requirements:` 行里逐字列出的 AC 编号。"""
    body = task_body if task_body is not None else read_task_body()
    match = re.search(r"_Requirements:\s*([^_]+)_", body)
    if match is None:
        raise GateStructuralError("Task 61 正文缺 `_Requirements:` 行")
    return tuple(
        sorted({part.strip() for part in match.group(1).split(",") if part.strip()})
    )


def task_declared_properties(*, task_body: str | None = None) -> tuple[str, ...]:
    """Task 61 正文「独立验证 Property …」里逐字列出的 Property 编号。

    🔴 与 :data:`DECLARED_PROPERTIES` **双向**核对（见 :func:`probe_registry_payload`）：
    只从正文取会让本文件的封闭元组成为装饰，只用封闭元组则正文改了这里不知道。
    """
    body = task_body if task_body is not None else read_task_body()
    return tuple(sorted({f"P{n}" for n in re.findall(r"Property (\d+)", body)}))


def design_property_titles(
    properties: Sequence[str] = DECLARED_PROPERTIES, *, text: str | None = None
) -> dict[str, str]:
    """design.md 里 12 条 Property 的标题。缺一条即结构性失效。"""
    body = text if text is not None else _DESIGN_MD.read_bytes().decode("utf-8")
    out: dict[str, str] = {}
    missing: list[str] = []
    for prop in properties:
        match = re.search(rf"(?m)^### Property {prop[1:]}:\s*(.+)$", body)
        if match is None:
            missing.append(prop)
            continue
        out[prop] = match.group(1).strip()
    if missing:
        raise GateStructuralError(
            f"design.md 里找不到以下 Property 的定义：{missing} —— "
            "Task 61 要求独立验证它们，定义缺失即无从验证"
        )
    return out


def _resolve_production_refs(spec: ProbeSpec) -> tuple[str, ...]:
    """逐个 import + getattr。符号消失即抛 —— 不等真实 OO 才发现被测对象已不在。"""
    _ensure_backend_on_path()
    resolved: list[str] = []
    for ref in spec.production_refs:
        module_name, _, attr = ref.partition(":")
        if not module_name or not attr:
            raise GateStructuralError(
                f"{spec.probe_id}: production_ref {ref!r} 必须形如 module:attr"
            )
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - 转成结构性失效，不降级
            raise GateStructuralError(
                f"{spec.probe_id}: 无法 import {module_name!r}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if not hasattr(module, attr):
            raise GateStructuralError(
                f"{spec.probe_id}: {module_name} 里没有 {attr!r} —— "
                "probe 声明还在，被测的生产符号已经不在了"
            )
        resolved.append(ref)
    return tuple(resolved)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Task 6 载体门：新鲜度**现算**（Task 44 没有的一格）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CarrierGateVerdict:
    """Task 6 载体裁决的现算结论。"""

    #: 三份 probe 模板的 `(相对路径, 记录 digest, 现算 digest)`
    template_digests: tuple[tuple[str, str, str], ...]
    recorded_source_commit: str
    observed_source_commit: str
    recorded_oo_build: str
    observed_oo_build: str
    carriers_allowed: tuple[str, ...]
    carriers_blocked: tuple[str, ...]
    anchors_allowed: tuple[str, ...]
    anchors_blocked: tuple[str, ...]
    #: F2 pilot 文档上**行载体不可取证**这条实测缺口（Task 6 显式登记）。
    row_carrier_gap: str
    stale_reasons: tuple[str, ...]

    @property
    def fresh(self) -> bool:
        return not self.stale_reasons

    @property
    def really_passed(self) -> bool:
        """裁决新鲜 **且** 三类载体与 w:tag 锚点确实判 passed。"""
        return (
            self.fresh
            and "field_sdt_inline" in self.carriers_allowed
            and "field_sdt_block" in self.carriers_allowed
            and "sdt_external_body" in self.carriers_allowed
            and self.anchors_allowed == ("w_tag",)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "fresh": self.fresh,
            "really_passed": self.really_passed,
            "template_digests": [
                {"path": p, "recorded": r, "observed": o}
                for p, r, o in self.template_digests
            ],
            "recorded_source_commit": self.recorded_source_commit,
            "observed_source_commit": self.observed_source_commit,
            "recorded_oo_build": self.recorded_oo_build,
            "observed_oo_build": self.observed_oo_build,
            "carriers_allowed": list(self.carriers_allowed),
            "carriers_blocked": list(self.carriers_blocked),
            "anchors_allowed": list(self.anchors_allowed),
            "anchors_blocked": list(self.anchors_blocked),
            "row_carrier_gap": self.row_carrier_gap,
            "stale_reasons": list(self.stale_reasons),
        }


def observed_source_commit() -> str:
    """现读 git HEAD。读不到即返回哨兵（**不**假装等于记录值）。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_REPO),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError as exc:
        return f"<git-unavailable: {type(exc).__name__}>"
    if out.returncode != 0:
        return f"<git-failed: {out.stderr.strip()[:80]}>"
    return out.stdout.strip()


def observed_onlyoffice_build(*, container: str = "audit-onlyoffice") -> str:
    """现问容器里的 documentserver 版本。读不到即返回哨兵。"""
    try:
        out = subprocess.run(
            [
                "docker", "exec", container, "sh", "-c",
                "dpkg-query -W -f='${Version}' onlyoffice-documentserver",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except OSError as exc:
        return f"<docker-unavailable: {type(exc).__name__}>"
    if out.returncode != 0:
        return f"<docker-failed: {out.stderr.strip()[:80]}>"
    return out.stdout.strip()


def probe_carrier_gate(
    *,
    contract: Mapping[str, Any] | None = None,
    source_commit: str | None = None,
    oo_build: str | None = None,
) -> CarrierGateVerdict:
    """逐项现算 Task 6 载体裁决的新鲜度与结论。

    三个可注入参数只为 :func:`gate_probe_carrier_freshness_is_measured` 与守卫服务：
    生产路径全部现算（模板真算 sha256、HEAD 真读 git、OO build 真问容器）。
    """
    payload = (
        contract
        if contract is not None
        else json.loads(CARRIER_CONTRACT_PATH.read_bytes().decode("utf-8"))
    )
    env = payload.get("environment") or {}
    recorded_commit = str(env.get("source_commit") or "")
    recorded_build = str(env.get("oo_build") or "")
    seen_commit = source_commit if source_commit is not None else observed_source_commit()
    seen_build = oo_build if oo_build is not None else observed_onlyoffice_build()

    digests: list[tuple[str, str, str]] = []
    stale: list[str] = []
    for doc in payload.get("probe_docs") or ():
        rel = str(doc.get("template_rel") or "")
        recorded = str(doc.get("template_sha256") or "")
        path = _REPO / rel
        if not path.is_file():
            observed = "<missing>"
            stale.append(f"probe 模板不存在: {rel}")
        else:
            observed = _sha256_file(path)
            if observed != recorded:
                stale.append(
                    f"probe 模板 digest 漂移: {rel} 记录 {recorded[:12]} 现算 {observed[:12]}"
                )
        digests.append((rel, recorded, observed))
    if not digests:
        raise GateStructuralError(
            f"{CARRIER_CONTRACT_PATH.name}: probe_docs 为空 —— 空集恒新鲜（假绿第⑥源）"
        )
    if recorded_commit != seen_commit:
        stale.append(
            f"source_commit 变化: 记录 {recorded_commit[:12]} 现读 {seen_commit[:12]}"
        )
    if recorded_build != seen_build:
        stale.append(f"OO build 变化: 记录 {recorded_build!r} 现问 {seen_build!r}")

    gate = payload.get("downstream_gate") or {}
    return CarrierGateVerdict(
        template_digests=tuple(digests),
        recorded_source_commit=recorded_commit,
        observed_source_commit=seen_commit,
        recorded_oo_build=recorded_build,
        observed_oo_build=seen_build,
        carriers_allowed=tuple(gate.get("carriers_allowed_into_word_engine") or ()),
        carriers_blocked=tuple(gate.get("carriers_blocked") or ()),
        anchors_allowed=tuple(gate.get("anchors_allowed") or ()),
        anchors_blocked=tuple(gate.get("anchors_blocked") or ()),
        row_carrier_gap=str(
            (payload.get("pilot_template_row_carrier_gap") or {}).get("consequence") or ""
        ),
        stale_reasons=tuple(stale),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 准入信号：**真实反读生产路径 + 真实库**
# ═══════════════════════════════════════════════════════════════════════════

#: 真实库快照的封闭键集。缺一个键即结构性失效（防"少查一张表就当没问题"）。
DB_SNAPSHOT_KEYS: Final[tuple[str, ...]] = (
    "approved_bundles",
    "published_representations",
    "upgrade_candidates",
    "content_versions",
    "word_definition_artifacts",
    "v153_candidate_event_table",
    "max_applied_migration",
)


async def _read_db_snapshot(refs: Sequence[LaneRef]) -> dict[str, dict[str, Any]]:
    """一次 `asyncio.run` 取全部快照。

    🔴 一次而不是每个 entry 各自 async：每测试/每 entry 各开 async 会污染共享连接池，
    第二个起报 `NoneType has no attribute send`（本 spec 已实测）。
    """
    import sqlalchemy as sa

    from app.core.database import async_session

    snapshot: dict[str, dict[str, Any]] = {}
    async with async_session() as session:
        shared_v153 = await session.execute(
            sa.text(
                "SELECT to_regclass('public.working_paper_representation_candidate_event')"
            )
        )
        v153 = shared_v153.scalar_one()
        shared_max = await session.execute(
            sa.text("SELECT max(version::int) FROM schema_version")
        )
        max_migration = shared_max.scalar_one()
        word_defs = await session.execute(
            sa.text(
                "SELECT count(*) FROM working_paper_sync_definition_artifact "
                "WHERE logical_id LIKE 'word-%' OR logical_id LIKE 'f2.%'"
            )
        )
        word_definition_artifacts = int(word_defs.scalar_one())
        for ref in refs:
            row: dict[str, Any] = {
                "v153_candidate_event_table": None if v153 is None else str(v153),
                "max_applied_migration": None if max_migration is None else int(max_migration),
                "word_definition_artifacts": word_definition_artifacts,
            }
            reps = await session.execute(
                sa.text(
                    "SELECT count(*) FROM working_paper_content_representation "
                    "WHERE entry_id = :e"
                ),
                {"e": ref.entry_id},
            )
            row["published_representations"] = int(reps.scalar_one())
            cands = await session.execute(
                sa.text(
                    "SELECT count(*) FROM working_paper_representation_upgrade_candidate "
                    "WHERE entry_id = :e"
                ),
                {"e": ref.entry_id},
            )
            row["upgrade_candidates"] = int(cands.scalar_one())
            versions = await session.execute(
                sa.text(
                    "SELECT count(*) FROM working_paper_content_version cv "
                    "WHERE EXISTS (SELECT 1 FROM working_paper_content_representation r "
                    "              WHERE r.content_version_id = cv.id AND r.entry_id = :e)"
                ),
                {"e": ref.entry_id},
            )
            row["content_versions"] = int(versions.scalar_one())
            # `contract_slot_ref` 是 text（形如 `definition:<uuid>`），没有 uuid 列可 JOIN，
            # 因此按 digest 关联：approved bundle 的 contract slot digest 必须命中本 entry
            # 已 approved 的 contract definition。
            bundles = await session.execute(
                sa.text(
                    "SELECT count(*) FROM working_paper_sync_definition_bundle b "
                    "WHERE b.state = 'approved' AND EXISTS ("
                    "  SELECT 1 FROM working_paper_sync_definition_artifact c "
                    "  WHERE c.kind = 'contract' AND c.state = 'approved' "
                    "    AND c.logical_id = :e AND c.sha256 = b.contract_slot_digest)"
                ),
                {"e": ref.entry_id},
            )
            row["approved_bundles"] = int(bundles.scalar_one())
            snapshot[ref.entry_id] = row
    return snapshot


#: 库读不到时的 ERROR 态文本。抽成常量是为了让 `raise` 保持**单行** ——
#: 变异检验要能把这一行整行换成 fail-open（`return {}`）且仍是合法 Python；
#: 多行 `raise(` 被整行替换后会留下悬空字符串 ⇒ 整 module SyntaxError ⇒
#: pytest 报 ERROR 而 `-rf` 只列 FAILED ⇒ 四态判定误判 GREEN（2026 本轮 M19 实测）。
_DB_UNREADABLE_MESSAGE: Final[str] = (
    "真实库读不到 —— 本门无法判断 published representation 是否存在，"
    "故判结构性失效而不是「全部 unverifiable」：{detail}"
)


def read_db_snapshot(refs: Sequence[LaneRef]) -> dict[str, dict[str, Any]]:
    """真实库快照。读不到即抛 :class:`DatabaseUnreadable` —— **禁 fail-open**。"""
    _ensure_backend_on_path()
    try:
        snapshot = asyncio.run(_read_db_snapshot(refs))
    except Exception as exc:  # noqa: BLE001 - 记 ERROR 态并抛，不降级成"无数据"
        raise DatabaseUnreadable(_DB_UNREADABLE_MESSAGE.format(detail=f"{type(exc).__name__}: {exc}")) from exc
    for entry_id, row in snapshot.items():
        missing = [k for k in DB_SNAPSHOT_KEYS if k not in row]
        if missing:
            raise GateStructuralError(
                f"{entry_id} 的库快照缺键 {missing} —— 少查一张表就会把缺口当成没问题"
            )
    return snapshot


@dataclass(frozen=True)
class AdmissionSignals:
    """一个 F2 entry 的准入信号。每一项都由生产调用 / 真实库得出。"""

    contract_installed: bool
    installed_contract_ids: tuple[str, ...]
    manifest_entry_present: bool
    manifest_docx_entry_ids: tuple[str, ...]
    adapter_registered: bool
    registered_adapter_ids: tuple[str, ...]
    adapter_block_in_force: bool
    adapter_block_detail: str
    carrier: CarrierGateVerdict
    db: Mapping[str, Any]

    @property
    def approved_bundle_present(self) -> bool:
        return int(self.db.get("approved_bundles") or 0) > 0

    @property
    def published_representation_present(self) -> bool:
        return int(self.db.get("published_representations") or 0) > 0

    @property
    def admitted(self) -> bool:
        """🔴 五项**全部**成立才算准入。缺一项即该 entry 不进入测试范围。

        顺序即 Task 61 正文第一句：published representation + approved bundle +
        （契约装载 / manifest entry / adapter 注册这三件是它们的前置），
        再叠上 Task 6 probe 真实通过。
        """
        return (
            self.contract_installed
            and self.manifest_entry_present
            and self.adapter_registered
            and self.published_representation_present
            and self.approved_bundle_present
            and self.carrier.really_passed
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "contract_installed": self.contract_installed,
            "installed_contract_ids": list(self.installed_contract_ids),
            "manifest_entry_present": self.manifest_entry_present,
            "manifest_docx_entry_ids": list(self.manifest_docx_entry_ids),
            "adapter_registered": self.adapter_registered,
            "registered_adapter_ids": list(self.registered_adapter_ids),
            "adapter_block_in_force": self.adapter_block_in_force,
            "adapter_block_detail": self.adapter_block_detail,
            "approved_bundle_present": self.approved_bundle_present,
            "published_representation_present": self.published_representation_present,
            "carrier": self.carrier.as_dict(),
            "db": dict(self.db),
        }


def probe_adapter_block() -> tuple[bool, str, Mapping[str, Any]]:
    """`PENDING_ENGINE_ADAPTERS` 的 docx 行是否仍在force，且 forbidden path 未出现。

    返回 `(in_force, 诊断, 那一行)`。🔴 三条**分开断言**（前三轮教训③：判据写成
    集合成员会被另一个顶住）：①恰一行 docx 登记 ②`blocking_task` 点名 Task 61
    ③每条 forbidden path 在磁盘上都不存在。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync.adapters import registry as registry_module

    rows = [
        dict(r) for r in registry_module.PENDING_ENGINE_ADAPTERS
        if str(r.get("document_type")) == "docx"
    ]
    if len(rows) != 1:
        return False, f"docx engine adapter 的 pending 登记必须恰 1 行，实得 {len(rows)}", {}
    row = rows[0]
    if str(TASK_NUMBER) not in str(row.get("blocking_task") or ""):
        return (
            False,
            f"pending 行的 blocking_task={row.get('blocking_task')!r} 没有点名 Task "
            f"{TASK_NUMBER} —— 放行门的 owner 丢了",
            row,
        )
    landed = [p for p in row.get("forbidden_paths") or () if (_REPO / "backend" / p).exists()]
    if landed:
        return (
            False,
            f"以下路径已落地却未过本门：{landed} —— Word adapter 提前落地"
            "（design §OO 9.4 pilot 门七步未通过）",
            row,
        )
    return (
        True,
        f"docx adapter 仍被 pending 登记拦住（blocking_task={row.get('blocking_task')}），"
        f"{len(row.get('forbidden_paths') or ())} 条 forbidden path 全部不存在",
        row,
    )


def probe_admission_signals(
    ref: LaneRef,
    *,
    db_snapshot: Mapping[str, Any],
    carrier: CarrierGateVerdict | None = None,
) -> AdmissionSignals:
    """逐个调用生产符号 + 真实库快照，反读一个 F2 entry 的准入状态。

    🔴 三个信号全部经**真调用**取值（不是读常量）：这是"上游补上后本门自动感知"的
    机制所在。:func:`gate_probe_admission_is_state_sensitive` 把这件事实测下来。
    没有任何一处返回硬编码常量；没有 `except: pass`。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync import contracts as contracts_module
    from app.services.workpaper_sync import evidence as ev
    from app.services.workpaper_sync.adapters import registry as registry_module

    installed = tuple(sorted(contracts_module.available_contract_ids()))
    entries = ev.manifest_entries_by_id(ev.load_entry_manifest())
    docx_ids = tuple(
        sorted(k for k, v in entries.items() if str(v.get("document_type")) == "docx")
    )
    production = registry_module.build_production_registry()
    registered = tuple(sorted(reg.adapter_id for reg in production.registrations()))
    block_in_force, block_detail, _row = probe_adapter_block()
    return AdmissionSignals(
        contract_installed=ref.contract_id in installed,
        installed_contract_ids=installed,
        manifest_entry_present=ref.entry_id in entries,
        manifest_docx_entry_ids=docx_ids,
        # 🔴 docx adapter 的注册与否按 **registry 现读** 判断，不按"文件是否存在"：
        #    文件存在 ≠ 注册（additive 死代码就是这个形态）。
        adapter_registered=any(
            str(reg.adapter_id) == ref.contract_id for reg in production.registrations()
        ),
        registered_adapter_ids=registered,
        adapter_block_in_force=block_in_force,
        adapter_block_detail=block_detail,
        carrier=carrier if carrier is not None else probe_carrier_gate(),
        db=dict(db_snapshot),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. 一个 entry 的全部实测事实
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LaneFacts:
    """一个 F2 Word lane entry 的全部实测事实。"""

    ref: LaneRef
    signals: AdmissionSignals
    #: Task 60 冻结的三个 typed slot digest（本 entry 自己的，不交叉复用）。
    frozen_slot_digests: Mapping[str, str]
    #: 本 entry 的 authority model definition digest（两个 entry 各不相同）。
    authority_model_definition_sha256: str
    #: 上面四项的 canonical digest —— 本 entry 的 **frozen bundle identity**。
    #: 🔴 它**不是** `working_paper_sync_definition_bundle.canonical_payload_sha256`：
    #: BP-11 未解除前库里没有那一行（`slot_ref` 恒 null），本门不得替它编一个。
    frozen_bundle_identity_sha256: str
    contract_canonical_sha256: str
    managed_field_count: int
    #: 本 entry 是否有行域字段（决定 row_uuid 半边是否可表达）。
    row_scoped_field_count: int
    #: 从 Task 60 发布记录现读的 BP 阻断项（`{id: what}`）。
    blocking_preconditions: Mapping[str, str]

    @property
    def entry_id(self) -> str:
        return self.ref.entry_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane_entry_key": self.ref.lane_entry_key,
            "entry_id": self.entry_id,
            "wp_code": self.ref.wp_code,
            "template_ref": self.ref.template_ref,
            "capability_target": self.ref.capability_target,
            "capability_verdict_stage": self.ref.capability_verdict_stage,
            "blocked_by": list(self.ref.blocked_by),
            "second_pipeline_endpoints": list(self.ref.second_pipeline_endpoints),
            "frozen_slot_digests": dict(self.frozen_slot_digests),
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "frozen_bundle_identity_sha256": self.frozen_bundle_identity_sha256,
            "contract_canonical_sha256": self.contract_canonical_sha256,
            "managed_field_count": self.managed_field_count,
            "row_scoped_field_count": self.row_scoped_field_count,
            "signals": self.signals.as_dict(),
        }


def collect_lane_facts(
    refs: Sequence[LaneRef] | None = None,
    *,
    publication: Mapping[str, Any] | None = None,
    db_snapshot: Mapping[str, Mapping[str, Any]] | None = None,
    carrier: CarrierGateVerdict | None = None,
) -> tuple[LaneFacts, ...]:
    """两个 entry 的全部实测事实。`db_snapshot=None` ⇒ **真读库**。"""
    pub = publication if publication is not None else load_publication()
    lane = tuple(refs) if refs is not None else lane_refs(pub)
    snapshot = db_snapshot if db_snapshot is not None else read_db_snapshot(lane)
    verdict = carrier if carrier is not None else probe_carrier_gate()
    blocking = {
        str(bp["id"]): str(bp.get("what") or "")
        for bp in pub.get("blocking_preconditions") or ()
        if str(bp.get("status") or "") == "open"
    }
    by_key = {str(e["lane_entry_key"]): e for e in pub["entries"]}
    facts: list[LaneFacts] = []
    for ref in lane:
        entry = by_key[ref.lane_entry_key]
        plan = entry.get("bundle_slot_plan") or {}
        contract = entry.get("contract") or {}
        field_evidence = entry.get("field_evidence") or ()
        if ref.entry_id not in snapshot:
            raise GateStructuralError(
                f"{ref.entry_id} 没有库快照 —— 本门不得替它假设一个"
            )
        slot_digests = {
            name: str((slot or {}).get("slot_digest") or "")
            for name, slot in (plan.get("slots") or {}).items()
        }
        if sorted(slot_digests) != ["contract", "instrumentation", "template"]:
            raise GateStructuralError(
                f"{ref.entry_id} 的 bundle_slot_plan.slots 必须恰含 template/"
                f"instrumentation/contract，实得 {sorted(slot_digests)}"
            )
        if any(not d for d in slot_digests.values()):
            raise GateStructuralError(
                f"{ref.entry_id} 的 bundle_slot_plan 有空 slot_digest —— 空 digest 会让"
                "交叉复用判据恒成立"
            )
        authority = str(plan.get("authority_model_definition_sha256") or "")
        facts.append(
            LaneFacts(
                ref=ref,
                signals=probe_admission_signals(
                    ref, db_snapshot=snapshot[ref.entry_id], carrier=verdict
                ),
                frozen_slot_digests=dict(sorted(slot_digests.items())),
                authority_model_definition_sha256=authority,
                frozen_bundle_identity_sha256=_digest(
                    {
                        "authority_model": str(plan.get("authority_model") or ""),
                        "authority_model_definition_sha256": authority,
                        "slots": dict(sorted(slot_digests.items())),
                    }
                ),
                contract_canonical_sha256=str(contract.get("canonical_sha256") or ""),
                managed_field_count=len(field_evidence),
                row_scoped_field_count=sum(
                    len(f.get("repeaters") or ()) for f in field_evidence
                ),
                blocking_preconditions=blocking,
            )
        )
    return tuple(facts)


# ═══════════════════════════════════════════════════════════════════════════
# 8. probe 判定（顺序不可交换）
# ═══════════════════════════════════════════════════════════════════════════


def _not_executed() -> str:
    """「本次没有真实 OO / 浏览器」的哨兵，与 harness 共用（不另造一个）。"""
    _ensure_backend_on_path()
    from app.services.workpaper_sync import pilot_harness as ph

    return str(ph.NOT_EXECUTED)


@dataclass(frozen=True)
class Environment:
    """本次运行的环境指纹。默认全是 `NOT-EXECUTED` 哨兵。"""

    onlyoffice_build: str
    browser_build: str
    source_commit: str = ""
    runner_version: str = GATE_VERSION

    @property
    def real_onlyoffice(self) -> bool:
        return self.onlyoffice_build != _not_executed()

    @property
    def real_browser(self) -> bool:
        return self.browser_build != _not_executed()

    def as_dict(self) -> dict[str, Any]:
        return {
            "onlyoffice_build": self.onlyoffice_build,
            "browser_build": self.browser_build,
            "source_commit": self.source_commit,
            "runner_version": self.runner_version,
            "real_onlyoffice": self.real_onlyoffice,
            "real_browser": self.real_browser,
        }


def default_environment() -> Environment:
    """默认环境 = 两个哨兵。

    🔴 **刻意不**用 :func:`observed_onlyoffice_build` 填 `onlyoffice_build`：
    「容器在跑」不等于「本次真跑了 OO 往返」。把容器版本填进来会让黑盒判定
    自动变绿 —— 那正是本 spec 反复点名的假绿形态。容器版本只用于
    :func:`probe_carrier_gate` 的**新鲜度**核对。
    """
    sentinel = _not_executed()
    return Environment(onlyoffice_build=sentinel, browser_build=sentinel)


@dataclass(frozen=True)
class ProbeRow:
    """一条 probe 的判定结果。逐条可追踪 —— 这就是「任何一个缺场景都保持 UNVERIFIABLE」
    的度量形态。"""

    probe_id: str
    probe_class: str
    entry_id: str | None
    wp_code: str | None
    scenario_id: str | None
    anchor: str
    result: str
    error_code: str | None
    blocking_conditions: tuple[str, ...]
    requirements: tuple[str, ...]
    properties: tuple[str, ...]
    notes: tuple[str, ...]
    oracle_echo: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return self.result == RESULT_PASSED

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "probe_id": self.probe_id,
            "probe_class": self.probe_class,
            "entry_id": self.entry_id,
            "wp_code": self.wp_code,
            "scenario_id": self.scenario_id,
            "anchor": self.anchor,
            "result": self.result,
            "error_code": self.error_code,
            "blocking_conditions": list(self.blocking_conditions),
            "requirements": list(self.requirements),
            "properties": list(self.properties),
            "notes": list(self.notes),
        }
        if self.oracle_echo is not None:
            payload["oracle_echo"] = self.oracle_echo
        return payload


def assert_records_carry_no_claim(records: Any, *, where: str = "<root>") -> None:
    """🔴 执行记录里不得出现结果声明字段（AC 14.9 / Property 69）。

    递归检查：`{"probes": {...: {"result": "passed"}}}` 这种深埋的声明也必须被拒。
    """
    if isinstance(records, Mapping):
        for key, value in records.items():
            if str(key).lower() in FORBIDDEN_RECORD_KEYS:
                raise DocumentaryClaimRejected(
                    f"{where}.{key}: 执行记录不得携带结果声明字段 —— "
                    "probe 结果只能由真实执行推导（不得以文档声明通过）"
                )
            assert_records_carry_no_claim(value, where=f"{where}.{key}")
    elif isinstance(records, (list, tuple)):
        for index, value in enumerate(records):
            assert_records_carry_no_claim(value, where=f"{where}[{index}]")


def load_execution_records(path: Path | None) -> dict[str, Any]:
    """读执行记录（可选）。结构非法或带结果声明即拒。"""
    if path is None:
        return {"environment": {}, "supplied_inputs": {}, "entries": {}}
    payload = json.loads(path.read_bytes().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise GateStructuralError(f"{path}: 执行记录根必须是对象")
    assert_records_carry_no_claim(payload, where=str(path.name))
    return {
        "environment": dict(payload.get("environment") or {}),
        "supplied_inputs": dict(payload.get("supplied_inputs") or {}),
        "entries": dict(payload.get("entries") or {}),
    }


def supply_gap_debt(facts: LaneFacts) -> str:
    """「finalize 仍做不成」的那一环，文本取 **Task 60 发布记录**里的 BP 原文。

    🔴 单一真源：本文件不另写一份说明 —— 另写一份就是第二真源，发布记录一改这里就
    悄悄过期。取的是本 entry `blocked_by` 命中的、且 `status=open` 的 BP。
    """
    hits = [
        f"{bp_id}: {facts.blocking_preconditions[bp_id]}"
        for bp_id in facts.ref.blocked_by
        if bp_id in facts.blocking_preconditions
    ]
    if not hits:
        raise GateStructuralError(
            f"{facts.entry_id} 的 blocked_by={list(facts.ref.blocked_by)} 在发布记录的 "
            "open blocking_preconditions 里一条都没命中 —— 阻断原因与登记表脱钩，"
            "本门不得替它编一个"
        )
    return "upstream_gap[" + ",".join(facts.ref.blocked_by) + "]: " + " | ".join(hits)


def carrier_unrepresentable_note(facts: LaneFacts, scenario_id: str | None) -> str | None:
    """本 entry 上**载体层面**不可表达的场景（Task 44 没有的一格）。

    今天命中的只有 `word_sdt_tag_row_uuid_retention` 的 **row_uuid 半边**：
    Task 6 把 `row_sdt` 判 failed 并列入 `carriers_blocked`，而 F2-22/F2-23 的
    `word/document.xml` 里 `w:tbl` 计数为 0、契约 `repeaters` 为空 ⇒ 这半边
    **不是"没跑"，而是在这两个 entry 上没有载体可承载**。

    🔴 两者必须分开：把结构性不可表达混进"未执行"，接上真实 OO 后它会自动刷绿。
    """
    if scenario_id != "word_sdt_tag_row_uuid_retention":
        return None
    if "row_sdt" not in facts.signals.carrier.carriers_blocked:
        return None
    if facts.row_scoped_field_count > 0:
        return None
    return (
        "row_uuid 半边在本 entry 上结构性不可表达："
        f"Task 6 把 row_sdt 列入 carriers_blocked，且本 entry 的 row_scoped_field_count="
        f"{facts.row_scoped_field_count}（契约无 repeaters）。"
        f"{facts.signals.carrier.row_carrier_gap} —— tag 半边仍在分母内，"
        "row_uuid 半边须先经 design 换载体（Task 6 downstream_gate 的 row_carrier_consequence）"
    )


#: 「既无 validator 也无 oracle」的 ERROR 态文本。同 :data:`_DB_UNREADABLE_MESSAGE`：
#: 抽成常量让 `raise` 保持单行，变异检验才能把它整行换成 fail-open 且仍是合法 Python。
_NO_CRITERION_MESSAGE: Final[str] = (
    "{probe_id}: 既没有 validator 也没有 scenario oracle —— 这条 probe 无从判定"
    "（不得默认判过）"
)


def evaluate_probe(
    spec: ProbeSpec,
    facts: LaneFacts,
    *,
    environment: Environment,
    record: Mapping[str, Any] | None,
    supplied_inputs: frozenset[str],
) -> ProbeRow:
    """判定一条 per-entry probe。**顺序不可交换**，理由见模块 docstring 第 4 条。

    1. schema 不可表达（V151 无法把它记成 passed）⇒ `unverifiable`
    2. **载体在本 entry 上不可表达** ⇒ `unverifiable`
    3. **上游供给缺口** ⇒ `failed` + `upstream_gap`（缺的是实现不是环境）
    4. 未准入 ⇒ `unverifiable` + `entry_not_admitted`
    5. 真实黑盒未执行 ⇒ `unverifiable` + `real_black_box_not_executed`
    6. 执行记录缺失 ⇒ `unverifiable` + `execution_record_missing`
    7. 真判据（validator / 生产 scenario oracle）

    3 必须在 5 之前：否则缺实现的场景在没有真实 OO 的环境里显示成 `unverifiable`，
    接上真实 OO 就会**自动刷绿**，而它们其实永远不会通过。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync import evidence as ev
    from app.services.workpaper_sync import pilot_harness as ph

    _resolve_production_refs(spec)
    scenario_id = spec.scenario_id
    oracle = ph.SCENARIO_ORACLES.get(scenario_id) if scenario_id else None
    requires: frozenset[str] = (
        frozenset(i.value for i in oracle.requires)
        if oracle
        else frozenset(spec.evidence_inputs)
    )
    unreal_black_box: list[str] = []
    if "onlyoffice_forcesave" in requires and not environment.real_onlyoffice:
        unreal_black_box.append("onlyoffice_build")
    if "browser_trace" in requires and not environment.real_browser:
        unreal_black_box.append("browser_build")

    oracle_echo: dict[str, Any] | None = None
    if oracle is not None:
        scenario = next(
            (s for s in ph.all_declared_scenarios() if s.scenario_id == scenario_id), None
        )
        if scenario is None:
            raise GateStructuralError(
                f"{spec.probe_id}: {scenario_id} 有 oracle 但不在 all_declared_scenarios() "
                "里 —— 生产两侧已脱钩"
            )
        echo = ph.run_scenario_oracle(
            scenario=scenario,
            oracle=oracle,
            observation=ph.ScenarioObservation(scenario_id=str(scenario_id)),
            onlyoffice_build=environment.onlyoffice_build,
            browser_build=environment.browser_build,
        )
        oracle_echo = {"outcome": echo.outcome.value, "error_code": echo.error_code}

    blocking: list[str] = []
    notes: list[str] = []

    # ── 收集**全部**未满足条件（error_code 只取第一条，但事实一条不丢）──────
    schema_note = ev.SCHEMA_UNREPRESENTABLE_SCENARIOS.get(str(scenario_id))
    if schema_note:
        blocking.append("schema_unrepresentable")
    carrier_note = carrier_unrepresentable_note(facts, scenario_id)
    if carrier_note:
        blocking.append("carrier_unrepresentable_on_this_entry")

    debt: str | None = None
    if oracle is not None and getattr(oracle, "upstream_debt", None):
        debt = str(oracle.upstream_debt)
        blocking.append("oracle_upstream_debt")
    if not facts.signals.admitted:
        # 🔴 「未准入」在本 lane 上不是环境问题：Task 60 发布记录里 BP-10 ~ BP-15 全为
        #    open，缺的是 approved bundle / published representation / adapter 的**供给**。
        #    因此 boundary 类 probe 之外的每一条都必须是 `failed` + `upstream_gap`，
        #    不能悄悄降级成 `unverifiable`（那会让接上真实 OO 后自动刷绿）。
        debt = debt or supply_gap_debt(facts)
        blocking.append("entry_not_admitted")
    if not facts.signals.carrier.really_passed:
        blocking.append("carrier_gate_not_really_passed")
        notes.append(
            "Task 6 载体裁决未真实通过/已 stale："
            f"{list(facts.signals.carrier.stale_reasons)}"
        )
    if spec.probe_class == "close_aspect":
        # 正文第 3 条：close 族**无条件运行** ⇒ 不设 close 谓词门（Task 44 有那道门是因为
        # 它的 xlsx entry 里存在 close_required=False 的形态；这里正文写死了"均无条件"）。
        notes.append("正文第 3 条要求本族无条件运行，故不设 close 谓词门")
    if unreal_black_box:
        blocking.append("real_black_box_not_executed")
        notes.append(f"仍是哨兵的黑盒环境项：{unreal_black_box}")
    if record is None:
        blocking.append("execution_record_missing")
    missing_inputs = sorted(requires - supplied_inputs)
    if missing_inputs:
        blocking.append("evidence_input_missing")
        notes.append(f"该 probe 需要 {sorted(requires)}，本次提供 {sorted(supplied_inputs)}")

    def _row(result: str, error_code: str | None, extra: Sequence[str] = ()) -> ProbeRow:
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.entry_id, facts.ref.wp_code,
            scenario_id, spec.anchor, result, error_code, tuple(blocking),
            spec.requirements, spec.properties, tuple([*notes, *extra]), oracle_echo,
        )

    # ── 判定（顺序即上面 docstring 的 1..7）──────────────────────────────
    # boundary 类 probe 度量的是「没有提前落地 / 下游确实阻塞」，它在未准入时**应当**
    # 通过 —— 把它塞进下面的 upstream_gap 分支会让"adapter 没提前落地"这件事被记成
    # failed，从而无法区分"守住了"与"没守住"。
    if spec.probe_class == "boundary":
        return _evaluate_boundary_probe(spec, facts, blocking=blocking, notes=notes)
    if schema_note:
        return _row(RESULT_UNVERIFIABLE, "scenario_kind_unrepresentable", [schema_note])
    if carrier_note:
        return _row(RESULT_UNVERIFIABLE, "carrier_unrepresentable_on_this_entry", [carrier_note])
    if debt is not None:
        return _row(RESULT_FAILED, "upstream_gap", [debt])
    if "real_black_box_not_executed" in blocking:
        return _row(RESULT_UNVERIFIABLE, "real_onlyoffice_not_executed")
    if record is None:
        return _row(RESULT_UNVERIFIABLE, "execution_record_missing")
    if missing_inputs:
        return _row(RESULT_UNVERIFIABLE, "evidence_input_missing")

    if spec.validator is not None:
        ok, why = spec.validator(facts, record)
        return _row(
            RESULT_PASSED if ok else RESULT_FAILED,
            None if ok else "validator_rejected",
            [why],
        )
    if oracle_echo is None:
        raise GateStructuralError(_NO_CRITERION_MESSAGE.format(probe_id=spec.probe_id))
    outcome = str(oracle_echo["outcome"])
    return _row(
        RESULT_PASSED if outcome == RESULT_PASSED else outcome,
        oracle_echo.get("error_code"),
        [f"生产 oracle 判定：{outcome}"],
    )


def _evaluate_boundary_probe(
    spec: ProbeSpec,
    facts: LaneFacts,
    *,
    blocking: Sequence[str],
    notes: Sequence[str],
) -> ProbeRow:
    """boundary probe 的真判据：**不依赖执行记录**，只看当前源码/registry 事实。

    两条各自独立：

    * `word_adapter_has_not_landed` —— `PENDING_ENGINE_ADAPTERS` 的 docx 行仍在 force
      且 forbidden path 未出现（:func:`probe_adapter_block` 三条分开断言）；
    * `downstream_tasks_stay_blocked` —— 本门有任一 per-entry probe 未通过时，
      Tasks 62–64 必须仍是未勾选状态（从 tasks.md 现读，不读结论）。
    """
    if spec.probe_id == "boundary.word_adapter_has_not_landed":
        in_force, detail, _row = probe_adapter_block()
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.entry_id, facts.ref.wp_code, None,
            spec.anchor, RESULT_PASSED if in_force else RESULT_FAILED,
            None if in_force else "adapter_landed_before_gate",
            tuple(blocking), spec.requirements, spec.properties,
            tuple([*notes, detail]), None,
        )
    if spec.probe_id == "boundary.downstream_tasks_stay_blocked":
        crossed, detail, payload = probe_word_bulk_gate_not_crossed()
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.entry_id, facts.ref.wp_code, None,
            spec.anchor, RESULT_PASSED if crossed else RESULT_FAILED,
            None if crossed else "word_bulk_gate_crossed_before_verification",
            tuple(blocking), spec.requirements, spec.properties,
            tuple([*notes, detail, json.dumps(payload, ensure_ascii=False)]), None,
        )
    raise GateStructuralError(
        f"{spec.probe_id}: boundary probe 没有对应判据 —— 声明存在而判据缺失即假绿"
    )


def probe_word_bulk_gate_not_crossed() -> tuple[bool, str, dict[str, Any]]:
    """Tasks 62–64 是否**真的**还被 `word_bulk` 门拦着（AC 12.3 / 正文第 4 条）。

    🔴 判据**不是** checkbox：平台已确立 `[x]` 的"部分交付簿记"语义（Tasks 1/2/20/60/64
    的正文都写明 `[x]` 只表示已交付部分完成、不代表 adapter 已注册），Task 64 于本轮被
    并发会话勾成 `[x]` 且其脚注逐条声明"未越 Task 61 的 `word_bulk` 门"。用 checkbox 判
    会立刻产生假红 —— 而假红与假绿一样会让人不再看这条判据。

    真判据是 **Task 64 脚注自己列出的四件结构事实**，逐条独立断言（教训③：写成集合
    成员会被另一个顶住）：

    1. `adapters/word.py` 与 `adapters/word` 都不存在；
    2. `DELIVERED_PER_ENTRY_CONTRACTS` 里没有 docx entry（批量迁移会往这里加行）；
    3. 生产契约清册里没有 Word lane 契约；
    4. 生产 registry 里没有注册任何 docx adapter。

    checkbox 状态仍**记录**在返回值里（供人核对簿记），但不参与判定。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync import contracts as contracts_module
    from app.services.workpaper_sync.adapters import registry as registry_module

    block_in_force, block_detail, _row = probe_adapter_block()
    docx_delivered = sorted(
        str(r.get("contract_id"))
        for r in registry_module.DELIVERED_PER_ENTRY_CONTRACTS
        if str(r.get("entry_id") or "").startswith("docx/")
        or str(r.get("document_type") or "") == "docx"
    )
    lane_contract_ids = {ref.contract_id for ref in lane_refs()}
    installed = set(contracts_module.available_contract_ids())
    installed_lane = sorted(lane_contract_ids & installed)
    registry_docx = sorted(
        str(reg.adapter_id)
        for reg in registry_module.build_production_registry().registrations()
        if str(getattr(reg, "document_type", "")) == "docx"
    )
    facts = {
        "forbidden_paths_still_absent": block_in_force,
        "forbidden_paths_detail": block_detail,
        "docx_entries_in_delivered_registry": docx_delivered,
        "lane_contracts_installed_into_production_inventory": installed_lane,
        "docx_adapters_registered": registry_docx,
        "downstream_task_checkbox_states": downstream_task_states(),
        "checkbox_is_not_the_criterion": (
            "平台 `[x]` 语义 = 部分交付簿记（Tasks 1/2/20/60/64 正文均写明）；"
            "本 probe 只按上面四条结构事实判定"
        ),
    }
    ok = (
        block_in_force
        and not docx_delivered
        and not installed_lane
        and not registry_docx
    )
    return (
        ok,
        (
            "word_bulk 门未被跨越：forbidden path 未出现 / 交付登记表无 docx entry / "
            "Word lane 契约未装入生产清册 / registry 无 docx adapter"
            if ok
            else f"word_bulk 门已被跨越而本门未全绿：{facts}"
        ),
        facts,
    )


def downstream_task_states(*, text: str | None = None) -> dict[str, str]:
    """现读 tasks.md 里 Tasks 62/63/64 的 checkbox 状态（**只作观测，不作判据**）。"""
    body = text if text is not None else _TASKS_MD.read_bytes().decode("utf-8")
    states: dict[str, str] = {}
    for number in DOWNSTREAM_BLOCKED_TASKS:
        match = re.search(rf"(?m)^- \[([ x~\-])\] {number}\. ", body)
        if match is None:
            raise GateStructuralError(
                f"tasks.md 里找不到 Task {number} —— 本门的下游阻塞判据与任务清单脱钩"
            )
        states[number] = match.group(1)
    return states


# ═══════════════════════════════════════════════════════════════════════════
# 9. gate 自检 probe（每条都**真跑**一次被检验的行为）
# ═══════════════════════════════════════════════════════════════════════════


def ordering_facts() -> dict[str, Any]:
    """把判定顺序同时按**源码位置**与**反事实行为**记下来。

    源码位置：`evaluate_probe` 里 upstream-gap 的 return 必须出现在
    real-black-box 的 return **之前**。行为侧见 :func:`upstream_gap_counterfactual`。
    """
    source = inspect.getsource(evaluate_probe)
    # 🔴 定位 **return 语句**而不是 error_code 字符串的首次出现：同一个字符串在
    #    `blocking.append(...)` 收集段里也出现，用首次出现算顺序会把收集段的位置当成
    #    判定顺序（首轮实测正是这个形态：record_missing 的收集在 3905、返回在 5300+，
    #    顺序判据因此假红）。
    returns = {
        "schema": '_row(RESULT_UNVERIFIABLE, "scenario_kind_unrepresentable"',
        "carrier": '_row(RESULT_UNVERIFIABLE, "carrier_unrepresentable_on_this_entry"',
        "upstream_gap": '_row(RESULT_FAILED, "upstream_gap"',
        "black_box": '_row(RESULT_UNVERIFIABLE, "real_onlyoffice_not_executed"',
        "record_missing": '_row(RESULT_UNVERIFIABLE, "execution_record_missing"',
    }
    markers: dict[str, int] = {}
    for name, needle in returns.items():
        hits = [m.start() for m in re.finditer(re.escape(needle), source)]
        if len(hits) != 1:
            raise GateStructuralError(
                f"`evaluate_probe` 里 {name} 的 return 语句命中 {len(hits)} 次（应恰 1 次）"
                " —— 顺序判据无法定位（同 ANCHOR-MISS：命中 0 或 >1 都是脚本缺陷）"
            )
        markers[name] = hits[0]
    missing = sorted(k for k, v in markers.items() if v < 0)
    if missing:
        raise GateStructuralError(
            f"`evaluate_probe` 里找不到判定标记 {missing} —— 顺序判据与实现脱钩"
        )
    return {
        "source_positions": markers,
        "upstream_gap_before_black_box": markers["upstream_gap"] < markers["black_box"],
        "carrier_before_upstream_gap": markers["carrier"] < markers["upstream_gap"],
        "black_box_before_record_missing": markers["black_box"] < markers["record_missing"],
    }


def upstream_gap_counterfactual(
    facts: LaneFacts, *, environment: Environment | None = None
) -> dict[str, Any]:
    """反事实：把黑盒环境**全部接上**，upstream-gap 的场景仍必须是 `failed`。

    这条是本门最关键的自检 —— 顺序被交换时它立刻打红：交换后同一条 probe 在
    「有真实 OO」的环境里会变成 `unverifiable` 甚至 `passed`。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync import pilot_harness as ph

    spec = next(s for s in SCENARIO_PROBES if s.scenario_id == "html_to_oo")
    real = Environment(onlyoffice_build="9.4.0-129", browser_build="Chrome/151.0.0.0")
    baseline = evaluate_probe(
        spec,
        facts,
        environment=environment or default_environment(),
        record=None,
        supplied_inputs=frozenset(),
    )
    with_black_box = evaluate_probe(
        spec,
        facts,
        environment=real,
        record={"anything": "provided"},
        supplied_inputs=frozenset(i.value for i in ph.EvidenceInput),
    )
    return {
        "sentinel_env_result": baseline.result,
        "sentinel_env_error_code": baseline.error_code,
        "real_env_result": with_black_box.result,
        "real_env_error_code": with_black_box.error_code,
        "still_failed_with_real_black_box": with_black_box.result == RESULT_FAILED
        and with_black_box.error_code == "upstream_gap",
    }


def gate_probe_ordering(facts: Sequence[LaneFacts]) -> tuple[bool, str, dict[str, Any]]:
    order = ordering_facts()
    counter = upstream_gap_counterfactual(facts[0])
    ok = (
        order["upstream_gap_before_black_box"]
        and order["carrier_before_upstream_gap"]
        and order["black_box_before_record_missing"]
        and counter["still_failed_with_real_black_box"]
    )
    return (
        ok,
        (
            "upstream-gap 排在黑盒之前，且接上真实黑盒后仍判 failed+upstream_gap"
            if ok
            else f"顺序判据不成立：{order} / {counter}"
        ),
        {"source": order, "counterfactual": counter},
    )


def gate_probe_no_documentary_pass() -> tuple[bool, str, dict[str, Any]]:
    """**真跑**一次拒绝路径，并断言拒的正是这一条。

    🔴 对照组必须先过（前三轮教训⑤）：先喂一份不带声明字段的记录，它**不得**被拒；
    否则「什么都拒」也算通过。
    """
    clean = {"entries": {"f2.stocktake.plan": {"browser_trace_path": "x"}}}
    control_ok = True
    control_detail = "对照组（无声明字段）未被拒"
    try:
        assert_records_carry_no_claim(clean)
    except DocumentaryClaimRejected as exc:
        control_ok = False
        control_detail = f"对照组被误拒：{exc}"

    rejected = False
    detail = "拒绝没有发生"
    try:
        assert_records_carry_no_claim(
            {"entries": {"f2.stocktake.plan": {"probes": [{"result": "passed"}]}}}
        )
    except DocumentaryClaimRejected as exc:
        rejected = True
        detail = str(exc)
    return (
        control_ok and rejected,
        detail if control_ok else control_detail,
        {
            "control_not_rejected": control_ok,
            "claim_rejected": rejected,
            "forbidden_keys": sorted(FORBIDDEN_RECORD_KEYS),
        },
    )


def _all_signals_ready(signals: AdmissionSignals) -> AdmissionSignals:
    """替身：把全部准入信号翻成「已就绪」（只用于 state-sensitivity 自检）。"""
    return replace(
        signals,
        contract_installed=True,
        manifest_entry_present=True,
        adapter_registered=True,
        carrier=replace(
            signals.carrier,
            stale_reasons=(),
            carriers_allowed=("field_sdt_inline", "field_sdt_block", "sdt_external_body"),
            anchors_allowed=("w_tag",),
        ),
        db={**dict(signals.db), "approved_bundles": 1, "published_representations": 1},
    )


def gate_probe_admission_is_state_sensitive(
    facts: Sequence[LaneFacts],
) -> tuple[bool, str, dict[str, Any]]:
    """用替身把全部信号翻成「已就绪」并复跑同一函数，准入判定必须改变。"""
    rows: list[dict[str, Any]] = []
    ok = True
    for entry in facts:
        before = entry.signals.admitted
        after = _all_signals_ready(entry.signals).admitted
        rows.append(
            {"entry_id": entry.entry_id, "admitted_now": before, "admitted_if_ready": after}
        )
        if before or not after:
            ok = False
    return (
        ok,
        (
            "全部信号翻成就绪后准入判定确实改变 ⇒ 本门真实反读状态，不是硬编码 false"
            if ok
            else f"准入判定对状态不敏感：{rows}"
        ),
        {"entries": rows},
    )


def gate_probe_carrier_freshness_is_measured() -> tuple[bool, str, dict[str, Any]]:
    """把载体门的三个新鲜度输入各翻一位，裁决必须每次都变 stale。

    🔴 三项**分开断言**（前三轮教训③）：写成"任一项变化即 stale"时，只要有一项生效
    另两项被短路也能过。
    """
    contract = json.loads(CARRIER_CONTRACT_PATH.read_bytes().decode("utf-8"))
    real = probe_carrier_gate()
    outcomes: dict[str, Any] = {"baseline_fresh": real.fresh}

    drifted_commit = probe_carrier_gate(
        contract=contract,
        source_commit="0" * 40,
        oo_build=real.observed_oo_build,
    )
    outcomes["commit_drift_detected"] = not drifted_commit.fresh

    drifted_build = probe_carrier_gate(
        contract=contract,
        source_commit=real.observed_source_commit,
        oo_build="0.0.0-0",
    )
    outcomes["build_drift_detected"] = not drifted_build.fresh

    mutated = json.loads(json.dumps(contract))
    mutated["probe_docs"][0]["template_sha256"] = "f" * 64
    drifted_template = probe_carrier_gate(
        contract=mutated,
        source_commit=real.observed_source_commit,
        oo_build=real.observed_oo_build,
    )
    outcomes["template_digest_drift_detected"] = not drifted_template.fresh

    ok = (
        outcomes["commit_drift_detected"]
        and outcomes["build_drift_detected"]
        and outcomes["template_digest_drift_detected"]
    )
    return (
        ok,
        (
            "三个新鲜度输入各自翻一位都能被检出 ⇒ 载体门是现算的，不是读一句 "
            "`probe_verdict: passed`"
            if ok
            else f"载体门新鲜度不是现算：{outcomes}"
        ),
        outcomes,
    )


def gate_probe_denominator_locked() -> tuple[bool, str, dict[str, Any]]:
    """分母三向锁 + **覆盖计数非空**（前三轮教训⑥：等值判据必须断言计数非空）。"""
    denominator = scenario_denominator_facts()
    ok = (
        denominator["declared_scenario_probes"] > 0
        and denominator["task44_declared"] > 0
        and len(denominator["word_family_scenarios"]) > 0
    )
    return (
        ok,
        (
            f"declared={denominator['declared_scenario_probes']} / "
            f"task44={denominator['task44_declared']} / "
            f"word_family={denominator['word_family_scenarios']}"
            if ok
            else f"分母出现空集（恒等价 = 假绿）：{denominator}"
        ),
        denominator,
    )


#: 变异检验产物（由 `mutate_task61_oo94_word_pilot_gate_guards.py --run` 写入）。
MUTATION_LEDGER: Final[Path] = (
    _SPEC_DIR / "evidence/task61-oo94-word-pilot-gate/mutation_four_state.json"
)


def mutation_coverage_facts() -> tuple[bool, str, dict[str, Any]]:
    """变异四态：declared == executed 且全部 RED。

    🔴 只看退出码会把 GREEN / ANCHOR-MISS / WRONG-TEST 误判成 RED，因此这里要求台账
    逐条给出四态判定，而不是一个总数。
    """
    _ensure_backend_on_path()
    script = _BACKEND / "scripts/diagnose/mutate_task61_oo94_word_pilot_gate_guards.py"
    if not script.is_file():
        return False, f"变异脚本不存在: {script.name}", {"declared": 0, "executed": 0}
    spec = importlib.util.spec_from_file_location("_task61_mutations", script)
    if spec is None or spec.loader is None:  # pragma: no cover - 结构性
        raise GateStructuralError(f"无法加载 {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    declared = [m.id for m in module.MUTATIONS]
    if not declared:
        return False, "变异清单为空 —— 空清单会让本 probe 恒成功", {"declared": 0}
    if not MUTATION_LEDGER.is_file():
        return (
            False,
            f"变异台账未生成: {MUTATION_LEDGER.name} —— declared={len(declared)} 条，"
            "executed=0（本门不认为守卫已成立）",
            {"declared": len(declared), "executed": 0, "declared_ids": declared},
        )
    ledger = json.loads(MUTATION_LEDGER.read_bytes().decode("utf-8"))
    # 🔴 直接读 `_mutation_kit` 的**原生** `--out` 输出（记录数组），不引入手写中间格式：
    #    手抄一份 `{"verdicts": {...}}` 就是第二真源，抄错/抄漏都看不出来。
    if not isinstance(ledger, list):
        raise GateStructuralError(
            f"{MUTATION_LEDGER.name}: 必须是 `_mutation_kit --out` 的原生记录数组，"
            f"实得 {type(ledger).__name__} —— 手写中间格式即第二真源"
        )
    verdicts = {str(row["id"]): str(row["verdict"]) for row in ledger}
    reds = sorted(k for k, v in verdicts.items() if v == "RED")
    non_red = sorted((k, v) for k, v in verdicts.items() if v != "RED")
    ok = set(verdicts) == set(declared) and not non_red
    return (
        ok,
        (
            f"declared==executed=={len(declared)} 且全部 RED"
            if ok
            else f"declared={sorted(declared)} executed={sorted(verdicts)} 非 RED={non_red}"
        ),
        {
            "declared": len(declared),
            "executed": len(verdicts),
            "red": len(reds),
            "non_red": non_red,
            "declared_ids": declared,
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9b. 绑定约束的三臂反事实测量（gate/2 新增）
# ═══════════════════════════════════════════════════════════════════════════
#
# 首版这道门把「四条结构事实全部成立」当作「word_bulk 门未被跨越」的证据，其中第四条是
# 「生产 registry 里没有注册任何 docx adapter」。2026-09-01 的三臂实测证明这条是**重言
# 式**：把前三条的前提逐一移除（manifest 里放进 docx F2 entry、往交付登记表加行、provider
# 走白名单内的模块）之后，第四条**仍然**成立 —— 因为它被一条完全不同的、平台级的约束顶着。
#
# 于是「registry 无 docx adapter」度量的根本不是 Word 批量迁移的门，而是那条平台级约束。
# 把它当门禁证据 = 假绿第③源（守卫把恒真值当基线锁死）。
#
# 🔴 2026-09-04 更正那条平台级约束的表述。原文写的是「`working_paper_sync_entry_state`
# 全表 0 行 ⇒ 186 个 planned entry 一个都注册不上」，实测该表已有 **2 行**，且其中 1 行是
# **manifest entry**（非 `opaque-` 命名空间），供给门对它**放行**。行数判据因此已失效 ——
# 详见 `BINDING_CONSTRAINTS` 里 BP-61-1 的 `what` 与 `measured_2026_09_04`。约束本身**未
# 解除**（`registered_adapter_ids` 仍为空），但根因已从「没有 published representation」
# 移到「capability 未翻成 `bidirectional`」。
#
# 本节把这件事变成**可执行**判据：三臂各自真跑一次，并要求三臂结果互不相同。
# 三臂度量逻辑本身不因上述更正而改动 —— 先后关系继续由实测得出，不由写死字面量得出。

#: 本任务实测出的阻塞前置。🔴 id 用 task-scoped 前缀 `BP-61-n` 而不是全局 `BP-NN`：
#: 实测 Tasks 60 / 63 / 64 各自登记了 `BP-16`~`BP-22`、同号不同义，全局单调编号在多会话
#: 并发下已被重复占用（Task 62 同款处置，其守卫用 `re.fullmatch(r"BP-62-\d+")` 锁死）。
BINDING_CONSTRAINTS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "id": "BP-61-1",
        "kind": "binding",
        "what": (
            "**185 / 186** planned entry 没有 current published representation ⇒ "
            "`registry._describe_entry_supply` 对它们全部给出拒绝原因，"
            "`registered_adapter_ids` 仍为空。"
        ),
        "scope": "platform_wide_not_f2_specific",
        "owner_task": (
            "供给侧 = published-representation-production-path-and-lane-adjudication "
            "spec（首版发布宿主）；capability 翻转侧 = manifest 重生成 + "
            "`approved_source_digest` 人工复核（Task 67 登记的复核方）—— 均不属 Task 61"
        ),
        "measured_by": "gate.binding_constraint_is_measured / arm_a + arm_b",
        "unblocks": "Task 61 正文第一句的准入条件（resolver 返回 published representation）",
        #: 🔴 2026-09-04 更正。原 `what` 写的是「`working_paper_sync_entry_state` 全表
        #: 0 行 ⇒ 没有任何 entry 有 current published representation ⇒ 对 **186 个**
        #: planned entry 全部给出拒绝原因」。三句里有两句已成假话：
        #:
        #:   * 「全表 0 行」  → 实测 **2 行**
        #:   * 「186 个全部被拒」→ 实测 **185 个**（G7 已放行）
        #:
        #: ⇒ **行数判据必须换成按 manifest entry_id 集合过滤**：全表行数里混着
        #: `opaque-` 命名空间的行（它们不是 manifest entry，对 registry 注册没有贡献），
        #: 数全表会让「有了 opaque representation」被误读成「供给已经出现」。
        #:
        #: 约束本身**未解除**，但根因移位了：`registered_adapter_ids` 为空**不再是**因为
        #: 「没有 published representation」，而是因为那个已有 representation 的 entry 的
        #: manifest capability 仍是 `single_onlyoffice`。这两件事的解除方不同（见
        #: `owner_task`），混在一句话里会把工作派给错的人。
        "measured_2026_09_04": {
            "working_paper_sync_entry_state_rows_total": 2,
            "of_which_opaque_namespace": 1,
            "of_which_manifest_entry": 1,
            "manifest_entry_with_current_representation": (
                "xlsx/gt-g7-long-term-equity-main",
            ),
            "supply_gate_verdict_for_that_entry": "None（放行）",
            "supply_gate_rejects_remaining": 185,
            "manifest_entry_count": 186,
            "registered_adapter_ids": (),
            "capability_of_that_entry": "single_onlyoffice",
            "manifest_capability_counts": {
                "single_html": 5,
                "single_onlyoffice": 180,
                "unreachable": 1,
                "bidirectional": 0,
            },
            "why_still_binding": (
                "供给门已放行 1 个 entry，但 `registered_adapter_ids` 仍为空 —— 注册还要求"
                "该 entry 的 manifest capability 为 `bidirectional`，实测仍是 "
                "`single_onlyoffice`。⇒ 约束未解除，根因由「无 representation」移到"
                "「capability 未翻转」"
            ),
            "measured_by_probe": (
                "registry._describe_entry_supply 逐 entry 真跑 + "
                "build_manifest_registration_plan + build_production_registry"
                "（该 entry 的 plan item 的 `blocked_reason` 实测已变 None）"
            ),
        },
    },
    {
        "id": "BP-61-2",
        "kind": "non_binding_but_open",
        "what": (
            "source-backed manifest 里 document_type=='docx' 的 entry 现算 7 条、F2 lane "
            "0 条；唯一的 F2 entry `xlsx/gt-f2-stocktake-bundle` 是 xlsx（宿主挂的是 "
            "`GtOnlyOfficeSheet`）。拿它注册 docx adapter 会被 RG-6 "
            "`assert_document_types_agree` 以 error_code=`adapter_document_type_mismatch` "
            "拒绝（四方实测 adapter/matcher/contract=docx、manifest=xlsx）。"
        ),
        "scope": "f2_lane",
        "owner_task": "60（接 descriptor/bridge）+ 前端 docx 挂载点 —— 不属 Task 61",
        "measured_by": "gate.binding_constraint_is_measured / arm_b（移除它后原因不变）",
        "why_not_binding": (
            "内存翻掉它之后 F2 的拒绝原因与 b60 Excel pilot **逐字相等** ⇒ 它排在 BP-61-1 "
            "之后，不是当前的绑定约束。"
        ),
    },
    {
        "id": "BP-61-3",
        "kind": "must_not_fix_yet",
        "what": (
            "`adapters/word.py` 若现在落地即**死代码 + 拆守卫**：`build_excel_adapter` 的"
            "唯一构造点在四个 `pilot_*.attach_pilot_adapters` 里（实测），没有 F2 docx "
            "manifest entry + provider 模块时 Word adapter 零构造点；而建这个文件同时会"
            "让 `PENDING_ENGINE_ADAPTERS` 的 forbidden-path 判据失守。"
        ),
        "scope": "f2_lane",
        "owner_task": "61（本任务）—— 但解除条件是 BP-61-1 与 BP-61-2 先解",
        "measured_by": "boundary.word_adapter_has_not_landed（forbidden path 三条分开断言）",
        "lesson_refs": ("additive 注入即死代码", "禁令清单必须包含真实目标（Task 64 M13）"),
    },
)

#: 三臂的封闭名。少一臂即结构性失效 —— 两臂比不出「同类」与「不同类」两件事。
BINDING_ARMS: Final[tuple[str, ...]] = ("arm_a_control", "arm_b_manifest_flipped", "arm_c_supply_stubbed")

#: 反事实里合成的 docx F2 entry_id。刻意与真实 xlsx entry 同名不同前缀，
#: 以便「只改 document_type 这一件事」在 arm_b 里是唯一变量。
_SYNTH_DOCX_ENTRY_ID: Final[str] = "docx/gt-f2-stocktake-bundle"
_SYNTH_SOURCE_ENTRY_ID: Final[str] = "xlsx/gt-f2-stocktake-bundle"
#: arm_b/arm_c 的对照 entry —— Task 76 已把它的 template/instrumentation/contract/
#: authority_model 四条 definition 全部 approved 并发布 bundle，是「供给最完整」的那个。
_CONTROL_ENTRY_ID: Final[str] = "xlsx/b60/gt-b60-bundle"


def _synthetic_docx_manifest() -> dict[str, Any]:
    """把磁盘 manifest 读进内存并**只**追加一条 docx F2 entry。磁盘不动一个字节。

    唯一变量是 `document_type` / `capability` / `editability` 与 mounts 的
    `documentType` —— 其余字段逐字复制真实 xlsx entry，因此 arm_b 与 arm_a 的差集
    就是 BP-61-2 本身。
    """
    raw = json.loads(_BACKEND.joinpath("data/workpaper_sync_entry_manifest.json").read_bytes().decode("utf-8"))
    entries = raw.get("entries") or []
    source = next((e for e in entries if e.get("entry_id") == _SYNTH_SOURCE_ENTRY_ID), None)
    if source is None:
        raise GateStructuralError(
            f"manifest 里找不到 {_SYNTH_SOURCE_ENTRY_ID} —— 反事实的基准 entry 已消失，"
            "本 probe 的差集无从计算"
        )
    synth = json.loads(json.dumps(source))
    synth["entry_id"] = _SYNTH_DOCX_ENTRY_ID
    synth["document_type"] = "docx"
    synth["capability"] = "bidirectional"
    synth["editability"] = "editable"
    synth["adapter_id"] = None
    for mount in synth.get("mounts") or ():
        mount["documentType"] = "docx"
    entries.append(synth)
    return raw


def _synthetic_contract_row() -> dict[str, Any]:
    """arm_b/arm_c 注入交付登记表的那一行。`provider_module` 刻意用**白名单内**的模块。

    用白名单内模块而不是 `adapters.word` 是刻意的：白名单本身（
    `_ALLOWED_PROVIDER_MODULES`）是另一格阻塞（实测 `ProviderModuleNotAllowedError`），
    把它一并留在实验里就分不清「原因不变」是因为供给还是因为白名单。
    """
    return {
        "contract_id": "f2.stocktake.plan",
        "provider_module": "app.services.workpaper_sync.pilot_simple_checklist",
        "delivered_by_task": "61-counterfactual-probe",
        "pilot_class": "f2_word_tagged_sdt",
        "entry_id": _SYNTH_DOCX_ENTRY_ID,
        "document_type": "docx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F2-22 存货监盘计划.docx",
        "adapter_registered": False,
        "reason": "gate.binding_constraint_is_measured 的进程内反事实注入；不写盘、不写库。",
    }


def _isolated_session_factory() -> tuple[Any, Any]:
    """给三臂专用的 `NullPool` 引擎 + session 工厂（用完即 dispose）。

    🔴 不能复用 `app.core.database.async_session`：本门在 :func:`read_db_snapshot`
    里已经跑过一次 `asyncio.run`，那次的连接留在**共享池**里且绑定在已关闭的 event
    loop 上；第二次 `asyncio.run` 取到它就报 `'NoneType' object has no attribute
    'send'`（本 spec 早已实测，本轮把 gate/2 首跑直接打成 exit 2 —— 现象是
    `DatabaseUnreadable` 而不是真的库不可达，属**假 ERROR 态**）。

    🔴 也不能改成「一次 asyncio.run 里连快照带三臂一起取」：那会把 `read_db_snapshot`
    的失败与三臂的失败绑在一根 `raise` 上，两类原因不可分辨（AC 5.12 明禁的形态）。
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {},
    )
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _run_binding_arms() -> dict[str, Any]:
    """一次 `asyncio.run` 跑完三臂。**只读库**（`register_from_manifest` 不写任何表）。

    🔴 一次而不是三次：每臂各自 `asyncio.run` 会污染共享连接池，第二臂起报
    `NoneType has no attribute send`（本 spec 已实测，本轮探针上再次复现）。
    """
    from app.services.workpaper_sync.adapters import registry as registry_module

    arms: dict[str, Any] = {}
    original_rows = registry_module.DELIVERED_PER_ENTRY_CONTRACTS
    original_supply = registry_module._describe_entry_supply
    arms_engine, arms_session = _isolated_session_factory()
    async with arms_session() as session:
        try:
            # ── arm_a：真实 manifest、真实登记表、真实供给
            control = registry_module.build_production_registry()
            outcome_a = await control.register_from_manifest(session=session)
            control_reason = await registry_module._describe_entry_supply(
                session=session, entry_id=_CONTROL_ENTRY_ID
            )
            arms["arm_a_control"] = {
                "planned": len(outcome_a.planned_entry_ids),
                "registered_adapter_ids": list(outcome_a.registered_adapter_ids),
                "registered_entry_ids": list(outcome_a.registered_entry_ids),
                "unregistered": len(outcome_a.reasons),
                "distinct_reason_count": len(set(outcome_a.reasons.values())),
                "control_entry_reason": control_reason,
                "synth_entry_planned": _SYNTH_DOCX_ENTRY_ID in outcome_a.planned_entry_ids,
            }

            # ── arm_b：只解除 BP-61-2（manifest 有 docx F2 entry + 交付登记行）
            registry_module.DELIVERED_PER_ENTRY_CONTRACTS = original_rows + (
                _synthetic_contract_row(),
            )
            flipped = _synthetic_docx_manifest()
            experiment = registry_module.build_production_registry(manifest=flipped)
            outcome_b = await experiment.register_from_manifest(session=session)
            arms["arm_b_manifest_flipped"] = {
                "planned": len(outcome_b.planned_entry_ids),
                "registered_adapter_ids": list(outcome_b.registered_adapter_ids),
                "registered_entry_ids": list(outcome_b.registered_entry_ids),
                "unregistered": len(outcome_b.reasons),
                "synth_entry_planned": _SYNTH_DOCX_ENTRY_ID in outcome_b.planned_entry_ids,
                "synth_reason": outcome_b.reasons.get(_SYNTH_DOCX_ENTRY_ID),
            }

            # ── arm_c：再解除 BP-61-1（供给门用替身满足）⇒ 必须落到**另一格**
            async def _supply_satisfied(*, session: Any, entry_id: str) -> str | None:
                return None

            registry_module._describe_entry_supply = _supply_satisfied  # type: ignore[assignment]
            stubbed = registry_module.build_production_registry(manifest=flipped)
            outcome_c = await stubbed.register_from_manifest(session=session)
            arms["arm_c_supply_stubbed"] = {
                "planned": len(outcome_c.planned_entry_ids),
                "registered_adapter_ids": list(outcome_c.registered_adapter_ids),
                "registered_entry_ids": list(outcome_c.registered_entry_ids),
                "unregistered": len(outcome_c.reasons),
                "synth_reason": outcome_c.reasons.get(_SYNTH_DOCX_ENTRY_ID),
            }
        finally:
            registry_module.DELIVERED_PER_ENTRY_CONTRACTS = original_rows
            registry_module._describe_entry_supply = original_supply  # type: ignore[assignment]
    await arms_engine.dispose()
    # 复原自检：替身与注入必须都撤干净，否则本进程后续的判据全部不可信。
    if registry_module.DELIVERED_PER_ENTRY_CONTRACTS is not original_rows:
        raise GateStructuralError("反事实注入未复原：DELIVERED_PER_ENTRY_CONTRACTS 仍是替身")
    if registry_module._describe_entry_supply is not original_supply:
        raise GateStructuralError("反事实替身未复原：_describe_entry_supply 仍是替身")
    return arms


#: 三臂读不到库时的 ERROR 态文本。抽成常量让 `raise` 保持单行（教训⑦）。
_ARMS_UNREADABLE_MESSAGE: Final[str] = (
    "三臂反事实读不到真实库 —— 无法判定绑定约束是哪一条，故判结构性失效"
    "而不是「BP-10 就是绑定约束」：{detail}"
)


def binding_constraint_facts(arms: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """三臂实测 + 由结果**现算**的绑定约束裁决。

    `arms` 只给守卫用（与 :func:`read_db_snapshot` 的 `db_snapshot=` 注入口同款）：
    注入的三臂数据仍要走下面全部五条判据，因此注入**不能**换来一个 passed ——
    喂进「arm_b 原因与对照不等」或「arm_c 原因未变」的替身照样打红
    （守卫正面断言这两条）。
    """
    _ensure_backend_on_path()
    if arms is None:
        try:
            arms = asyncio.run(_run_binding_arms())
        except GateStructuralError:
            raise
        except Exception as exc:  # noqa: BLE001 - 记 ERROR 态并抛，禁 fail-open
            raise DatabaseUnreadable(
                _ARMS_UNREADABLE_MESSAGE.format(detail=f"{type(exc).__name__}: {exc}")
            ) from exc
    missing = [name for name in BINDING_ARMS if name not in arms]
    if missing:
        raise GateStructuralError(
            f"三臂缺 {missing} —— 两臂比不出「同类」与「不同类」两件事，判据不成立"
        )
    control_reason = arms["arm_a_control"]["control_entry_reason"]
    arm_b_reason = arms["arm_b_manifest_flipped"]["synth_reason"]
    arm_c_reason = arms["arm_c_supply_stubbed"]["synth_reason"]
    # 🔴 判「同类」用**逐字相等**而不是子串/关键词：原因文案的真源在
    #    `registry._describe_entry_supply` 里，抄一份关键词进来就是第二真源（抄错看不出）。
    same_class_as_control = arm_b_reason is not None and arm_b_reason == control_reason
    arm_c_moved = arm_c_reason is not None and arm_c_reason != arm_b_reason
    return {
        "arms": arms,
        "constraints": [dict(row) for row in BINDING_CONSTRAINTS],
        "arm_b_reason_equals_control_reason": same_class_as_control,
        "arm_c_reason_differs_from_arm_b": arm_c_moved,
        "binding_constraint_id": "BP-61-1" if same_class_as_control else None,
        "non_binding_constraint_ids": ["BP-61-2"] if same_class_as_control else [],
        "fact4_is_not_word_bulk_gate_evidence": (
            "arm_b 已解除 BP-61-2 而 `registered_adapter_ids` 仍为空 ⇒ "
            "「registry 无 docx adapter」在 word_bulk 门被跨越后仍恒真 ⇒ 它不是门的证据"
        ),
        "reason_source_of_truth": (
            f"{_SYNC}.adapters.registry:_describe_entry_supply（本 probe 逐字相等比对，"
            "不复制关键词）"
        ),
    }


def gate_probe_binding_constraint_is_measured(
    arms: Mapping[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """绑定约束由三臂**实测**得出，不由 BP 编号顺序假定。

    五条分开断言（教训③：写成集合成员会被另一个顶住）：

    1. `BINDING_CONSTRAINTS` 非空且每条 id 都匹配 ``BP-61-\\d+``（task-scoped 前缀）；
    2. 恰有一条 `kind == "binding"`；
    3. arm_a 的 `registered_adapter_ids` 为空且 planned 非空（分母非空，教训⑥）；
    4. arm_b（只解除 BP-61-2）后 F2 的拒绝原因与对照 entry **逐字相等** ⇒
       BP-61-2 不是绑定约束；
    5. arm_c（再解除 BP-61-1）后原因**改变** ⇒ 本 probe 度量的是真实顺序而不是硬编码。
    """
    facts = binding_constraint_facts(arms)
    ids = [str(row.get("id") or "") for row in BINDING_CONSTRAINTS]
    bad_ids = [i for i in ids if not re.fullmatch(r"BP-61-\d+", i)]
    binding = [row for row in BINDING_CONSTRAINTS if row.get("kind") == "binding"]
    arm_a = facts["arms"]["arm_a_control"]
    problems: list[str] = []
    if not ids:
        problems.append("BINDING_CONSTRAINTS 为空 —— 空清单让本 probe 恒成功")
    if bad_ids:
        problems.append(f"id 不是 task-scoped 前缀: {bad_ids}")
    if len(binding) != 1:
        problems.append(f"kind=='binding' 的行数 {len(binding)} ≠ 1")
    if not arm_a["planned"]:
        problems.append("arm_a 的 planned 为空 —— 分母为空时「零注册」是重言式")
    if arm_a["registered_adapter_ids"]:
        problems.append(
            f"arm_a 已有注册 adapter {arm_a['registered_adapter_ids']} —— "
            "本门的前提（Word lane 未注册）已变，判据须重新推导"
        )
    if not facts["arm_b_reason_equals_control_reason"]:
        problems.append(
            "arm_b 的拒绝原因与对照 entry 不再逐字相等 —— BP-61-2 与 BP-61-1 的先后"
            "关系已变（可能是好事：published representation 供给出现了），本 probe 拒绝"
            "沿用旧裁决"
        )
    if not facts["arm_c_reason_differs_from_arm_b"]:
        problems.append(
            "arm_c 解除供给门后原因未改变 —— 说明本 probe 没有真的度量顺序（硬编码）"
        )
    ok = not problems
    return (
        ok,
        (
            f"绑定约束实测为 {facts['binding_constraint_id']}（arm_a planned="
            f"{arm_a['planned']} / registered=0；arm_b 原因与对照 entry 逐字相等；"
            "arm_c 原因已改变）"
            if ok
            else "；".join(problems)
        ),
        facts,
    )


def evaluate_gate_probes(
    facts: Sequence[LaneFacts], *, binding_arms: Mapping[str, Any] | None = None
) -> tuple[list[ProbeRow], dict[str, Any]]:
    """跑七条 gate 自检 probe。"""
    runners: dict[str, Callable[[], tuple[bool, str, dict[str, Any]]]] = {
        "gate.ordering_upstream_gap_before_black_box": lambda: gate_probe_ordering(facts),
        "gate.no_documentary_pass": gate_probe_no_documentary_pass,
        "gate.admission_is_state_sensitive": lambda: gate_probe_admission_is_state_sensitive(
            facts
        ),
        "gate.carrier_freshness_is_measured": gate_probe_carrier_freshness_is_measured,
        "gate.denominator_locked_against_task44": gate_probe_denominator_locked,
        "gate.mutation_four_state": mutation_coverage_facts,
        "gate.binding_constraint_is_measured": (
            lambda: gate_probe_binding_constraint_is_measured(binding_arms)
        ),
    }
    if sorted(runners) != sorted(s.probe_id for s in GATE_PROBES):
        raise GateStructuralError(
            "gate probe 声明与 runner 不是一一对应 —— 声明存在而判据缺失即假绿：\n"
            f"  declared={sorted(s.probe_id for s in GATE_PROBES)}\n"
            f"  runners  ={sorted(runners)}"
        )
    rows: list[ProbeRow] = []
    detail: dict[str, Any] = {}
    for spec in GATE_PROBES:
        ok, why, payload = runners[spec.probe_id]()
        detail[spec.probe_id] = payload
        rows.append(
            ProbeRow(
                spec.probe_id, spec.probe_class, None, None, None, spec.anchor,
                RESULT_PASSED if ok else RESULT_FAILED,
                None if ok else "gate_self_check_failed",
                () if ok else ("gate_self_check_failed",),
                spec.requirements, spec.properties, (why,), None,
            )
        )
    return rows, detail


# ═══════════════════════════════════════════════════════════════════════════
# 10. probe 注册表投影（进 `backend/data/`，由生成器写盘）
# ═══════════════════════════════════════════════════════════════════════════


def probe_registry_payload() -> dict[str, Any]:
    """probe 注册表的可复算投影（不含任何 per-run 结果）。"""
    body = read_task_body()
    anchors = assert_probes_anchored_in_task_text(task_body=body)
    requirements = task_requirement_ids(task_body=body)
    text_properties = task_declared_properties(task_body=body)
    titles = design_property_titles()
    claimed_reqs = {r for spec in ALL_PROBE_SPECS for r in spec.requirements}
    claimed_props = {p for spec in ALL_PROBE_SPECS for p in spec.properties}
    payload: dict[str, Any] = {
        "schema_version": "task61-word-pilot-gate-probes:v1",
        "gate_version": GATE_VERSION,
        "task": TASK_NUMBER,
        "lane_entry_keys": [ref.lane_entry_key for ref in lane_refs()],
        "per_entry_probe_count": len(PER_ENTRY_PROBES),
        "scenario_probe_count": len(SCENARIO_PROBES),
        "gate_probe_count": len(GATE_PROBES),
        "total_probe_rows": len(PER_ENTRY_PROBES) * len(lane_refs()) + len(GATE_PROBES),
        "anchors": dict(sorted(anchors.items())),
        "task_requirements": list(requirements),
        "requirements_without_probe": sorted(set(requirements) - claimed_reqs),
        "requirements_claimed_but_not_declared": sorted(claimed_reqs - set(requirements)),
        "declared_properties": list(DECLARED_PROPERTIES),
        "task_text_properties": list(text_properties),
        "properties_without_probe": sorted(set(DECLARED_PROPERTIES) - claimed_props),
        "properties_claimed_but_not_declared": sorted(
            claimed_props - set(DECLARED_PROPERTIES)
        ),
        "property_titles": dict(sorted(titles.items())),
        "out_of_lane_scenarios": {
            k: dict(v) for k, v in sorted(OUT_OF_LANE_SCENARIOS.items())
        },
        # gate/2：把三臂实测出的阻塞前置写进数据文件，使「哪一条是绑定约束」可离线复核。
        # 只写**声明**不写 per-run 结果（结果在 report 的 gate_self_checks 里）。
        "binding_constraints": [dict(row) for row in BINDING_CONSTRAINTS],
        "scenario_denominator": scenario_denominator_facts(),
        "probes": [
            {
                "probe_id": spec.probe_id,
                "probe_class": spec.probe_class,
                "scenario_id": spec.scenario_id,
                "anchor": spec.anchor,
                "requirements": list(spec.requirements),
                "properties": list(spec.properties),
                "production_refs": list(spec.production_refs),
                "has_validator": spec.validator is not None,
            }
            for spec in ALL_PROBE_SPECS
        ],
    }
    payload["registry_digest"] = _digest(
        {k: v for k, v in payload.items() if k != "registry_digest"}
    )
    return payload


def assert_registry_coverage(payload: Mapping[str, Any]) -> None:
    """AC / Property 覆盖必须**双向**闭合，且分母非空。"""
    if not payload.get("task_requirements"):
        raise GateStructuralError("Task 61 的 `_Requirements:` 解析为空 —— 分母为空即恒等价")
    for key in (
        "requirements_without_probe",
        "requirements_claimed_but_not_declared",
        "properties_without_probe",
        "properties_claimed_but_not_declared",
    ):
        offenders = list(payload.get(key) or ())
        if offenders:
            raise GateStructuralError(
                f"{key} 非空：{offenders} —— Task 61 声明的 AC/Property 必须逐条落在 probe 上，"
                "probe 也不得声明正文之外的 AC/Property"
            )
    declared = set(payload.get("declared_properties") or ())
    from_text = set(payload.get("task_text_properties") or ())
    if declared != from_text:
        raise GateStructuralError(
            "本文件的 DECLARED_PROPERTIES 与 Task 61 正文「独立验证 Property …」不一致：\n"
            f"  file={sorted(declared)}\n  text={sorted(from_text)}"
        )
    if not payload.get("probes"):
        raise GateStructuralError("probe 清单为空 —— 空清单会让本门恒成功（假绿）")
    # gate/2：阻塞前置清单是「哪一条是绑定约束」的唯一登记处。三条判据**分开**断言。
    constraints = list(payload.get("binding_constraints") or ())
    if not constraints:
        raise GateStructuralError(
            "binding_constraints 为空 —— 没有登记的阻塞前置时，「绑定约束是哪一条」"
            "无从复核，本门会退化成一句结论"
        )
    offenders = [
        str(row.get("id"))
        for row in constraints
        if not re.fullmatch(r"BP-61-\d+", str(row.get("id") or ""))
    ]
    if offenders:
        raise GateStructuralError(
            f"binding_constraints 里的 id 不是 task-scoped 前缀 `BP-61-n`: {offenders} —— "
            "全局单调编号已被 Tasks 60/63/64 各自重复占用（同号不同义）"
        )
    binding = [row for row in constraints if row.get("kind") == "binding"]
    if len(binding) != 1:
        raise GateStructuralError(
            f"binding_constraints 里 kind=='binding' 的行数为 {len(binding)}，必须恰 1 —— "
            "零条等于没裁决，多条等于没收敛"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 11. 报告
# ═══════════════════════════════════════════════════════════════════════════


def build_report(
    *,
    environment: Environment | None = None,
    records: Mapping[str, Any] | None = None,
    db_snapshot: Mapping[str, Mapping[str, Any]] | None = None,
    carrier: CarrierGateVerdict | None = None,
    binding_arms: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """跑完整门禁并产出报告。任何结构性失效都以异常形式冒出（不吞）。"""
    _ensure_backend_on_path()
    payload = probe_registry_payload()
    assert_registry_coverage(payload)

    exec_records = dict(records or load_execution_records(None))
    env = environment or default_environment()
    env_overrides = exec_records.get("environment") or {}
    if env_overrides:
        env = Environment(
            onlyoffice_build=str(env_overrides.get("onlyoffice_build") or env.onlyoffice_build),
            browser_build=str(env_overrides.get("browser_build") or env.browser_build),
            source_commit=str(env_overrides.get("source_commit") or env.source_commit),
        )
    supplied = frozenset(
        str(k) for k, v in (exec_records.get("supplied_inputs") or {}).items() if v
    )

    facts = collect_lane_facts(db_snapshot=db_snapshot, carrier=carrier)
    rows: list[ProbeRow] = []
    for entry in facts:
        entry_records = (exec_records.get("entries") or {}).get(entry.entry_id) or {}
        for spec in PER_ENTRY_PROBES:
            record = entry_records.get(spec.probe_id)
            rows.append(
                evaluate_probe(
                    spec,
                    entry,
                    environment=env,
                    record=record,
                    supplied_inputs=supplied,
                )
            )
    gate_rows, gate_detail = evaluate_gate_probes(facts, binding_arms=binding_arms)
    rows.extend(gate_rows)

    if len(rows) != payload["total_probe_rows"]:
        raise GateStructuralError(
            f"probe 行数 {len(rows)} 与声明的 {payload['total_probe_rows']} 不符 —— "
            "分母与执行脱钩"
        )

    by_result: dict[str, int] = {}
    for row in rows:
        by_result[row.result] = by_result.get(row.result, 0) + 1
    per_entry_rows = [r for r in rows if r.entry_id is not None]
    entries_verified = sorted(
        {
            entry.entry_id
            for entry in facts
            if all(
                r.passed
                for r in per_entry_rows
                if r.entry_id == entry.entry_id
            )
        }
    )
    downstream_states = downstream_task_states()
    return {
        "schema_version": "task61-word-pilot-gate-report:v1",
        "gate_version": GATE_VERSION,
        "task": TASK_NUMBER,
        "environment": env.as_dict(),
        "observed_environment": {
            "source_commit": observed_source_commit(),
            "onlyoffice_container_build": facts[0].signals.carrier.observed_oo_build,
            "note": (
                "🔴 `observed_environment` 只用于载体门新鲜度核对；它**不**参与黑盒判定 —— "
                "「容器在跑」不等于「本次真跑了 OO 往返」"
            ),
        },
        "registry": payload,
        "entries": [entry.as_dict() for entry in facts],
        "probe_rows": [row.as_dict() for row in rows],
        "gate_self_checks": gate_detail,
        "summary": {
            "probe_rows": len(rows),
            "by_result": dict(sorted(by_result.items())),
            "entries_total": len(facts),
            "entries_verified": entries_verified,
            "entries_left_unverifiable": sorted(
                entry.entry_id for entry in facts if entry.entry_id not in entries_verified
            ),
            "downstream_task_states": downstream_states,
            "downstream_tasks_blocked": len(entries_verified) < len(facts),
        },
    }


def _exit_code_for(report: Mapping[str, Any]) -> int:
    rows = report["probe_rows"]
    return 0 if all(r["result"] == RESULT_PASSED for r in rows) else 1


def _print_report(report: Mapping[str, Any]) -> None:
    summary = report["summary"]
    print(f"Task {report['task']} gate ({report['gate_version']})")
    print(
        f"  probe 行 {summary['probe_rows']}  结果分布 {summary['by_result']}"
    )
    for entry in report["entries"]:
        signals = entry["signals"]
        print(
            f"  · {entry['wp_code']} [{entry['entry_id']}] admitted={signals['admitted']}"
            f" contract_installed={signals['contract_installed']}"
            f" manifest_entry={signals['manifest_entry_present']}"
            f" adapter={signals['adapter_registered']}"
            f" approved_bundle={signals['approved_bundle_present']}"
            f" published_repr={signals['published_representation_present']}"
            f" carrier_fresh={signals['carrier']['fresh']}"
        )
    print(f"  entries_verified            = {summary['entries_verified']}")
    print(f"  entries_left_unverifiable   = {summary['entries_left_unverifiable']}")
    print(f"  Tasks 62-64 checkbox        = {summary['downstream_task_states']}")
    print(f"  Tasks 62-64 仍阻塞          = {summary['downstream_tasks_blocked']}")
    failed = [r for r in report["probe_rows"] if r["result"] == RESULT_FAILED]
    unver = [r for r in report["probe_rows"] if r["result"] == RESULT_UNVERIFIABLE]
    if failed:
        print(f"  failed ({len(failed)})：")
        for row in failed[:6]:
            print(f"    - {row['probe_id']} [{row['entry_id']}] {row['error_code']}")
        if len(failed) > 6:
            print(f"    … 另有 {len(failed) - 6} 条，详见 --json")
    if unver:
        print(f"  unverifiable ({len(unver)})：")
        for row in unver[:6]:
            print(f"    - {row['probe_id']} [{row['entry_id']}] {row['error_code']}")
        if len(unver) > 6:
            print(f"    … 另有 {len(unver) - 6} 条，详见 --json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", dest="json_path", default=None, help="报告写盘路径")
    parser.add_argument(
        "--execution-records",
        dest="records_path",
        default=None,
        help="真实执行记录（不得携带结果声明字段）",
    )
    args = parser.parse_args(argv)
    try:
        records = load_execution_records(
            Path(args.records_path) if args.records_path else None
        )
        report = build_report(records=records)
    except GateStructuralError as exc:
        print(f"[结构性失效] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    _print_report(report)
    return _exit_code_for(report)


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
