# -*- coding: utf-8 -*-
"""Task 44 gate：真实 OnlyOffice 9.4 Excel pilot 的 fail-closed 门禁。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 44
Requirements: 4.10, 4.11, 5.5, 6.8, 6.11, 6.16, 8.10, 10.2, 10.3, 10.4, 10.9, 10.10,
12.2, 12.10, 14.2, 14.3, 14.5, 14.6, 14.7, 14.8, 14.9, 14.16
Properties: **P18 / P25 / P26 / P29 / P43 / P44 / P49 / P55 / P56 / P58 / P62 / P63 /
P64 / P65 / P66 / P69**

═══ 这道门存在的唯一理由：让「四类 pilot 已验证」不可能被声明出来 ═══

Tasks 40–43 交付了四个 pilot 的契约与守卫，但四个都停在 Task 36 的 finalize 前。
🔴 卡点在 Task 75 之后**换了一环**（这行原先写的是
`UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER`，现已过时）：Task 75 建成了
`published_identity_observer` 并删掉四处欠账登记，于是缺的不再是观测器**实现**，而是
approved bundle → published representation 的**供给**（四张 definition/representation 表
PG 实测 0 行，属 Task 76）。两者都属**实现**缺口而非环境缺口，故 admission probe 仍是
`failed` + `upstream_gap`，见 `_supply_gap_debt` 与 `probe_finalize_signals` ③。
于是本任务能做的**唯一**诚实交付是：
把「哪一条没跑、为什么没跑、缺的是环境还是实现」变成逐条可追踪、可复算、非零退出的
事实，而不是写一句「真实 OO 未执行前保持 UNVERIFIABLE」。

四条不可协商的设计
------------------

1. **finalize 状态真实反读，不硬编码**
   :func:`probe_finalize_signals` 逐个调用生产符号：
   `assert_manifest_capability_enabled()`（manifest 真实读）、
   `adapters.registry.build_production_registry()`（registry 真实读）、
   `resolve_published_frozen_definitions()`（**真跑那个 coroutine**）、
   `attach_pilot_adapters()`（**真跑生产接线点**，只替换 DB session）。
   四个信号全部经 `getattr(module, name)` 在调用时刻取 ⇒ 观测器补上后本门自动感知。
   :func:`gate_probe_admission_is_state_sensitive` 用**替身**把四个信号全部翻成"已就绪"
   并复跑同一函数，断言判定确实改变 —— 「不是硬编码」是本门自己度量出来的事实。

2. **probe 行是分母，不是清单**
   :data:`PER_PILOT_PROBES` 的每条 `anchor` 必须逐字出现在 `tasks.md` 的 Task 44 正文里
   （:func:`assert_probes_anchored_in_task_text`）；scenario 侧再与生产 required set
   **双向**锁死（:func:`_scenario_denominator_facts`）—— 正文枚举项被删、或 evidence 侧
   新增场景而这里没跟上，两个方向都立刻打红。

3. **判定顺序不可交换**：schema 不可表达 → upstream-gap（`failed`）→ pilot 未准入 →
   真实黑盒未执行 → 执行记录缺失 → 真判据。upstream-gap 必须排在黑盒**之前**，
   否则接上真实 OO 会把「永远不会通过」的场景自动刷绿（本 spec 已三次实测）。
   :func:`ordering_facts` 把这条顺序同时按**源码位置**与**反事实行为**记下来。

4. **`passed` 只能由真实执行记录推导**
   任何执行记录里出现 `result` / `verdict` / `passed` / `aggregate_result` /
   `status` 键即被 :class:`DocumentaryClaimRejected` 拒绝（AC 14.9 / Property 49 /
   Property 69：不得以文档声明通过）。gate 自己在运行时真跑一次这条拒绝路径
   （:func:`gate_probe_no_documentary_pass`），拒绝没发生就不给这条 probe 判 passed。

用法（仓库根）::

    py -3 backend/scripts/check/check_task44_oo94_excel_pilot_gate.py
    py -3 backend/scripts/check/check_task44_oo94_excel_pilot_gate.py --json out.json
    py -3 backend/scripts/check/check_task44_oo94_excel_pilot_gate.py \
        --execution-records records.json

退出码：0 = 四类 pilot 全部 verified（今天不可能）；1 = 阻断 Wave 5（有 probe 未通过）；
2 = 门自身的结构性失效（锚点脱钩 / 分母脱钩 / 生产符号消失）—— 比 1 更严重，
因为那意味着这道门已经量不准了。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import inspect
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Final, Mapping, Sequence

_REPO: Final[Path] = Path(__file__).resolve().parents[3]
_BACKEND: Final[Path] = _REPO / "backend"
_SPEC_DIR: Final[Path] = (
    _REPO / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
_TASKS_MD: Final[Path] = _SPEC_DIR / "tasks.md"
_DESIGN_MD: Final[Path] = _SPEC_DIR / "design.md"
_EVIDENCE_DIR: Final[Path] = _SPEC_DIR / "evidence/task44-oo94-excel-pilot-gate"
#: 生成数据文件（probe 注册表投影 + digest）。生成器 = `backend/scripts/gen/`。
REGISTRY_JSON: Final[Path] = _BACKEND / "data/workpaper_task44_pilot_gate_probes.json"

#: gate 版本。改判据必须 +1（它进 evidence，旧 evidence 因此 stale）。
GATE_VERSION: Final[str] = "task44-gate/1"

#: Task 44 在 tasks.md 里的编号。用编号定位而**不是**用行号：行号会随上游任务增删漂移。
TASK_NUMBER: Final[int] = 44


class GateStructuralError(RuntimeError):
    """门自身失效（锚点/分母/生产符号脱钩）。比"有 probe 没通过"更严重。"""


class DocumentaryClaimRejected(GateStructuralError):
    """执行记录里出现了结果声明字段。

    🔴 单独一个异常类型而不是复用上面那个：`gate.no_documentary_pass` 这条 probe 要断言
    「拒绝确实发生过、且拒的正是这一条」。共享类型时"拒了别的东西"也能让它变绿。
    """


#: 执行记录里**禁止出现**的键 —— 它们全是"我宣布这条过了"的形态。
FORBIDDEN_RECORD_KEYS: Final[frozenset[str]] = frozenset(
    {"result", "verdict", "passed", "aggregate_result", "status", "outcome"}
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 四个 pilot（Tasks 40–43 的交付物，本门只读）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PilotRef:
    """一个 pilot 的定位信息。`owner_task` 让阻断原因能指名道姓。"""

    pilot_class: str
    module_path: str
    owner_task: int


PILOTS: Final[tuple[PilotRef, ...]] = (
    PilotRef("simple_checklist", "app.services.workpaper_sync.pilot_simple_checklist", 40),
    PilotRef("d2_large_json", "app.services.workpaper_sync.pilot_d2_large_json", 41),
    PilotRef("h1_grouped_dynamic", "app.services.workpaper_sync.pilot_h1_grouped_dynamic", 42),
    PilotRef(
        "g7_two_level_dynamic",
        "app.services.workpaper_sync.pilot_g7_two_level_dynamic",
        43,
    ),
)


def _ensure_backend_on_path() -> None:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    os.environ.setdefault("DB_DISABLE_SSL", "True")


def load_pilot_module(ref: PilotRef) -> Any:
    """import 一个 pilot 模块。**不吞异常** —— fail-open 会把"接线断了"伪装成"没数据"。"""
    _ensure_backend_on_path()
    try:
        return importlib.import_module(ref.module_path)
    except Exception as exc:  # noqa: BLE001 - 转成结构性失效，不降级
        raise GateStructuralError(
            f"pilot {ref.pilot_class}: 无法 import {ref.module_path} —— "
            f"{type(exc).__name__}: {exc}"
        ) from exc


# ═══════════════════════════════════════════════════════════════════════════
# 2. probe 声明（每条都锚定到 tasks.md 的 Task 44 正文）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProbeSpec:
    """一条 probe 声明。

    :param anchor: **逐字**出现在 Task 44 正文里的子串。它是本门与任务正文的锁：
        枚举项被改写/删除 ⇒ :func:`assert_probes_anchored_in_task_text` 抛。
    :param scenario_id: 非空即表示该 probe 的判定**委派**给生产
        :func:`~app.services.workpaper_sync.pilot_harness.run_scenario_oracle`，
        其 `evidence_inputs` 也从生产 oracle 现取（不在这里抄第二份）。
    :param evidence_inputs: 仅非 scenario probe 需要声明（生产侧没有对应 oracle）。
    :param production_refs: 该 probe 在生产上由哪些符号实现（`module:attr`）。
        plan 阶段逐个 import+getattr —— 符号改名/删除立刻抛，而不是等真实 OO 才发现
        被测对象早已不在。
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


_SYNC = "app.services.workpaper_sync"


def _p(
    probe_id: str,
    probe_class: str,
    anchor: str,
    why: str,
    *,
    reqs: Sequence[str] = (),
    props: Sequence[str] = (),
    scenario: str | None = None,
    inputs: Sequence[str] = (),
    refs: Sequence[str] = (),
    validator: Callable[..., tuple[bool, str]] | None = None,
) -> ProbeSpec:
    return ProbeSpec(
        probe_id=probe_id,
        probe_class=probe_class,
        anchor=anchor,
        why=why,
        requirements=tuple(reqs),
        properties=tuple(props),
        scenario_id=scenario,
        evidence_inputs=tuple(inputs),
        production_refs=tuple(refs),
        validator=validator,
    )


#: 正文第 2 条逐项 + 第 3 条 close 族 —— scenario 侧 probe。
#: 每条 `scenario` 都必须能在生产 `SCENARIO_ORACLES` 里找到（:func:`_assert_scenarios_known`）。
_SCENARIO_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _p(
        "scenario.html_to_oo", "scenario", "HTML→OO",
        "HTML 提交后 canonical artifact 在 OO 侧可见",
        reqs=("14.2",), props=("P29", "P55"), scenario="html_to_oo",
    ),
    _p(
        "scenario.oo_to_html", "scenario", "OO→HTML",
        "durable callback 后结构化内容在 HTML 侧可见且 revision 递增",
        reqs=("14.2",), props=("P29", "P55"), scenario="oo_to_html",
    ),
    _p(
        "scenario.identity_retention", "scenario", "、identity、",
        "identity 载体经真实 OO 打开/编辑/插删/排序/复制/forcesave/重开后仍保留",
        reqs=("6.16", "14.5"), props=("P66",), scenario="identity_retention",
    ),
    _p(
        "scenario.different_field_merge", "scenario", "different-field merge",
        "不同字段并行修改自动合并且 conflict_count=0",
        reqs=("6.8", "14.2"), props=("P25",), scenario="different_field_merge",
    ),
    _p(
        "scenario.same_field_conflict_resolve", "scenario", "same-field conflict/resolve",
        "同字段异值必冲突、三值完整、裁决后才落库",
        reqs=("6.8", "14.2"), props=("P26",), scenario="same_field_conflict_resolve",
    ),
    _p(
        "scenario.frozen_base_status_6_2_dedupe", "scenario", "frozen-base status 6/2 dedupe",
        "status 6/2 与网络重试命中同一 frozen identity 只应用一次",
        reqs=("14.3",), props=("P18", "P56", "P64"),
        scenario="frozen_base_status_6_2_dedupe",
    ),
    _p(
        "scenario.same_application_higher_sequence_fold", "scenario",
        "same-application higher-sequence fold不self-stale",
        "同 canonical application 的更高 sequence 只 fold、不 self-stale、origin 不改写",
        reqs=("5.5",), props=("P18", "P64"),
        scenario="same_application_higher_sequence_fold",
    ),
    _p(
        "scenario.cross_participant_idempotency_409", "scenario",
        "跨participant同Idempotency-Key及不同kind/payload均409且不泄露旧ID",
        "跨 participant 复用同 Idempotency-Key 及不同 kind/payload 均 409 且不返回旧 ID",
        reqs=("5.5",), props=("P18", "P64"), scenario="cross_participant_idempotency_409",
    ),
    _p(
        "scenario.quarantined_rejects_application_and_engine", "scenario",
        "quarantined拒绝application/engine",
        "quarantined incoming 在 application FK / coordinator / engine 三层各自被拒",
        reqs=("8.10",), props=("P65",),
        scenario="quarantined_rejects_application_and_engine",
    ),
    _p(
        "scenario.opaque_version_rollback_no_numeric_collision", "scenario",
        "opaque version UUID rollback与跨wp同numeric revision无碰撞",
        "rollback 只接受 opaque version UUID；跨 wp 相同 numeric revision 不碰撞",
        reqs=("14.6",), props=("P65",),
        scenario="opaque_version_rollback_no_numeric_collision",
    ),
    _p(
        "scenario.browser_crash_no_userdata_recovery_case", "scenario",
        "browser crash no-userdata recovery case",
        "无 userdata 的 crash close 建 recovery case，claim 前三实体为 0",
        reqs=("14.3", "14.8"), props=("P58",),
        scenario="browser_crash_no_userdata_recovery_case",
    ),
    _p(
        "scenario.authorization_first_recovery_claim", "scenario", "authorization-first claim",
        "authorization-first claim 在一个事务内建 request+shell 并创建/命中 application",
        reqs=("10.10",), props=("P43", "P58"),
        scenario="authorization_first_recovery_claim",
    ),
    _p(
        "scenario.wrong_prior_confirmation_bundle_fence_contributor_rejected", "scenario",
        "错误 prior confirmation/bundle/fence/contributor 拒绝",
        "错误 prior confirmation / bundle / fence / contributor 一律拒绝且不产生 operation",
        reqs=("10.10", "10.3"), props=("P43", "P44"),
        scenario="wrong_prior_confirmation_bundle_fence_contributor_rejected",
    ),
    _p(
        "scenario.download_only_zero_three_entities", "scenario", "download-only 三实体为 0",
        "download-only 只终结 case 并签下载，request/application/operation 恒为 0",
        reqs=("14.3",), props=("P58",), scenario="download_only_zero_three_entities",
    ),
    _p(
        "scenario.refresh_required_reopen", "scenario", "merged≠incoming refresh/reopen",
        "merged≠incoming ⇒ refresh_required，supersede/reopen 后才接受下一次 request",
        reqs=("4.11", "14.2"), props=("P62",), scenario="refresh_required_reopen",
    ),
    _p(
        "scenario.rollback", "scenario", "refresh/reopen与 rollback",
        "回滚到历史 content version 并重物化，比对 rematerialized representation hash",
        reqs=("14.2", "14.6"), props=("P65",), scenario="rollback",
    ),
    _p(
        "scenario.dynamic_row_add_delete_reorder_copy", "scenario",
        "动态能力再跑插删/排序/复制",
        "动态行增删重排复制按 row identity 合并 —— 「在 OO 里插一行」只能真实 OO 做",
        reqs=("14.5",), props=("P66",), scenario="dynamic_row_add_delete_reorder_copy",
    ),
    # ── 正文第 3 条：close 族八条 ────────────────────────────────────────
    _p(
        "scenario.single_participant_close", "scenario", "single close",
        "单用户 clean close 最终恰一个 close-capture",
        reqs=("4.10",), props=("P63", "P69"), scenario="single_participant_close",
    ),
    _p(
        "scenario.two_user_close_order_a_then_b", "scenario", "两个用户两种关闭顺序",
        "两用户 A→B 顺序关闭，最终恰一个 close-capture",
        reqs=("4.10",), props=("P63",), scenario="two_user_close_order_a_then_b",
    ),
    _p(
        "scenario.two_user_close_order_b_then_a", "scenario", "两个用户两种关闭顺序",
        "两用户 B→A 顺序关闭，最终恰一个 close-capture",
        reqs=("4.10",), props=("P63",), scenario="two_user_close_order_b_then_a",
    ),
    _p(
        "scenario.b_close_before_a_forcesave_terminal", "scenario", "A terminal 前/后 B close",
        "A 的普通 forcesave terminal 之前 B close：barrier 必须等前置 forcesave 安全终结",
        reqs=("4.10",), props=("P63",), scenario="b_close_before_a_forcesave_terminal",
    ),
    _p(
        "scenario.b_close_after_a_forcesave_terminal", "scenario", "A terminal 前/后 B close",
        "A 的普通 forcesave terminal 之后 B close",
        reqs=("4.10",), props=("P63",), scenario="b_close_after_a_forcesave_terminal",
    ),
    _p(
        "scenario.close_leader_revoked_successor_exactly_one", "scenario",
        "leader promotion前revoke/expire后的successor",
        "leader promotion 前被 revoke/expire、存在合法 successor ⇒ 仍恰一个 capture",
        reqs=("4.10", "10.4"), props=("P63",),
        scenario="close_leader_revoked_successor_exactly_one",
    ),
    _p(
        "scenario.close_leader_revoked_no_successor_recovery_required", "scenario",
        "无successor`recovery_required`",
        "无合法 successor ⇒ 零 capture + generation supersede + 显式 recovery_required",
        reqs=("4.10", "10.4"), props=("P63",),
        scenario="close_leader_revoked_no_successor_recovery_required",
    ),
    _p(
        "scenario.close_reconciler_reentrant_exactly_one_capture", "scenario",
        "`reconcile_close_intents()` 重入",
        "reconcile 重入（同 eligibility snapshot 重放）不换 leader、不产生第二 capture",
        reqs=("4.10",), props=("P63", "P69"),
        scenario="close_reconciler_reentrant_exactly_one_capture",
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 执行记录：接口 + 真判据（今天没有记录，但判据现在就必须可执行）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PilotFacts:
    """一个 pilot 今天的实测事实包。全部现算，没有一项来自文档。"""

    ref: PilotRef
    module: Any
    entry_id: str
    adapter_id: str
    entry: Mapping[str, Any]
    required_scenario_ids: tuple[str, ...]
    required_digest: str
    close_required: bool
    close_predicate_raw: bool
    capability: str
    editability: str
    room_model: str
    authority_model: str
    authority_model_definition_sha256: str
    template_definition_sha256: str
    instrumentation_definition_sha256: str
    contract_canonical_sha256: str
    bundle_sha256: str
    signals: "FinalizeSignals"
    registered_debts: Mapping[str, str]


def _iso_datetimes(raw: Mapping[str, Any]) -> dict[str, datetime]:
    """把记录里的 ISO 字符串解析成 tz-aware datetime；非法/naive 直接抛。

    naive 时间戳必须拒：AC 14.8 要求「数据库时间」参与证明，而 naive 值无法区分
    服务端时钟与客户端时钟 —— 那正是这条 AC 要防的东西。
    """
    out: dict[str, datetime] = {}
    for key, value in raw.items():
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            raise ValueError(f"{key}={value!r} 是 naive 时间戳，无法证明它来自服务端时钟")
        out[key] = parsed
    return out


def _need(record: Mapping[str, Any], *keys: str) -> tuple[bool, str]:
    missing = [k for k in keys if k not in record]
    if missing:
        return False, f"执行记录缺字段 {missing}"
    return True, ""


def validate_playwright_trace(facts: PilotFacts, record: Mapping[str, Any]) -> tuple[bool, str]:
    """Playwright network/console 通道（AC 14.8）。"""
    ok, why = _need(record, "network_requests", "console_messages", "har_sha256")
    if not ok:
        return False, why
    requests = record["network_requests"]
    if not isinstance(requests, list) or not requests:
        return False, "network_requests 为空 —— 没有网络证据等于没跑浏览器"
    errors = [
        m
        for m in record["console_messages"]
        if str((m or {}).get("level", "")).lower() in {"error", "severe"}
    ]
    if errors:
        return False, f"console 有 {len(errors)} 条 error 级消息：{errors[:2]}"
    if not str(record["har_sha256"]).strip():
        return False, "har_sha256 为空 —— trace bundle 必须内容寻址，截图不算证据"
    return True, f"network {len(requests)} 条、console 零 error、har {record['har_sha256'][:12]}"


def validate_timeline_triple(facts: PilotFacts, record: Mapping[str, Any]) -> tuple[bool, str]:
    """recovery + application + operation 三条 timeline（AC 14.8 / Property 58）。

    判据**委派生产** :func:`~app.services.workpaper_sync.pilot_harness.evaluate_timeline_order`
    与它冻结的两条顺序常量 —— 顺序在这里抄一份就等于第二真源。
    """
    from app.services.workpaper_sync import pilot_harness as ph

    ok, why = _need(record, "operation_timeline", "recovery_timeline")
    if not ok:
        return False, why
    for label, raw, order in (
        ("operation", record["operation_timeline"], ph.OO_TO_HTML_TIMELINE_ORDER),
        ("recovery", record["recovery_timeline"], ph.RECOVERY_TIMELINE_ORDER),
    ):
        verdict = ph.evaluate_timeline_order(_iso_datetimes(raw), expected_order=order)
        if not verdict.passed:
            return False, f"{label} timeline 不成立：{verdict.error_code} {verdict.notes[:1]}"
    return True, "两条 timeline 均由生产 oracle 判定顺序成立"


def validate_db_timestamps(facts: PilotFacts, record: Mapping[str, Any]) -> tuple[bool, str]:
    """DB 时间戳通道（AC 14.8）：服务端时钟 + 单调不倒退。"""
    from app.services.workpaper_sync import timeline as tl

    ok, why = _need(record, "db_timestamps", "clock_source")
    if not ok:
        return False, why
    if str(record["clock_source"]) != "server":
        return False, f"clock_source={record['clock_source']!r} —— 只接受服务端时钟"
    stamps = _iso_datetimes(record["db_timestamps"])
    if not stamps:
        return False, "db_timestamps 为空"
    # 🔴 排序依据的**列级**策略委派生产：`assert_server_clock_only` 的白名单是
    # `('sequence_no', 'occurred_at')`，喂它别的列（如客户端时间）它会抛。这里传记录声明的
    # order_keys（默认服务端列）—— 时钟政策不在本门抄第二份。
    tl.assert_server_clock_only(tuple(record.get("order_keys") or ("occurred_at",)))
    ordered = [stamps[k] for k in record["db_timestamps"]]
    if any(b < a for a, b in zip(ordered, ordered[1:])):
        return False, "db_timestamps 非单调 —— 时序倒挂即失败（AC 14.8 原文）"
    return True, f"{len(stamps)} 个服务端时间戳单调且 order key 经生产白名单校验"


def validate_published_result_representation(
    facts: PilotFacts, record: Mapping[str, Any]
) -> tuple[bool, str]:
    """published result representation（AC 6.11 / 8.10 / Property 29 / 65）。"""
    ok, why = _need(
        record,
        "representation_id",
        "representation_state",
        "representation_kind",
        "projection_sha256",
        "extracted_projection_sha256",
        "candidate_participated",
    )
    if not ok:
        return False, why
    if str(record["representation_state"]) != "published":
        return False, f"state={record['representation_state']!r} —— candidate 不得作为结果"
    if str(record["representation_kind"]) != "result":
        return False, f"kind={record['representation_kind']!r} —— 结果只能是 result"
    if bool(record["candidate_participated"]):
        return False, "candidate 参与了结果发布（AC 14.6 明禁）"
    if str(record["projection_sha256"]) != str(record["extracted_projection_sha256"]):
        return False, (
            "materialize 后 extract 反读的 projection hash 与 applied projection 不等 "
            "—— Property 29 不成立"
        )
    return True, f"published result representation {record['representation_id']} 往返等值"


def validate_authority_model(facts: PilotFacts, record: Mapping[str, Any]) -> tuple[bool, str]:
    """authority model 通道（AC 14.16）：记录里的 digest 必须等于**现算**值。"""
    ok, why = _need(record, "authority_model", "authority_model_definition_sha256")
    if not ok:
        return False, why
    if str(record["authority_model"]) != facts.authority_model:
        return False, (
            f"authority_model={record['authority_model']!r} 与本 entry 现算的 "
            f"{facts.authority_model!r} 不符"
        )
    if str(record["authority_model_definition_sha256"]) != facts.authority_model_definition_sha256:
        return False, (
            "authority model definition digest 与现算值不符 —— evidence 已 stale "
            f"（现算 {facts.authority_model_definition_sha256[:12]}）"
        )
    return True, f"authority model {facts.authority_model} / {facts.authority_model_definition_sha256[:12]} 对齐"


def validate_bundle_digest_typed_slots(
    facts: PilotFacts, record: Mapping[str, Any]
) -> tuple[bool, str]:
    """bundle digest + 三类 typed child（AC 12.10 / 14.16 / Property 64）。"""
    ok, why = _need(record, "bundle_sha256", "typed_slots")
    if not ok:
        return False, why
    if str(record["bundle_sha256"]) != facts.bundle_sha256:
        return False, (
            f"bundle digest {str(record['bundle_sha256'])[:12]} ≠ 现算 "
            f"{facts.bundle_sha256[:12]}"
        )
    expected = {
        "template": facts.template_definition_sha256,
        "instrumentation": facts.instrumentation_definition_sha256,
        "contract": facts.contract_canonical_sha256,
    }
    slots = record["typed_slots"]
    if set(slots) != set(expected):
        return False, f"typed_slots 键集 {sorted(slots)} ≠ {sorted(expected)}"
    for slot, digest in expected.items():
        got = slots[slot] or {}
        if str(got.get("type")) != "definition":
            return False, f"slot {slot} 的 type={got.get('type')!r} —— marker 不得冒充 definition"
        if str(got.get("digest")) != digest:
            return False, f"slot {slot} digest 与现算值不符（现算 {digest[:12]}）"
    return True, f"bundle {facts.bundle_sha256[:12]} 与三类 typed child 全部对齐"


def validate_artifact_identity_inventory(
    facts: PilotFacts, record: Mapping[str, Any]
) -> tuple[bool, str]:
    """artifact / identity inventory（AC 6.16 / Property 66）。"""
    from app.services.workpaper_sync import excel_instrumentation as ei

    ok, why = _need(record, "artifact_sha256", "identity_inventory")
    if not ok:
        return False, why
    inventory = record["identity_inventory"] or {}
    for key in ("metadata_sheet", "defined_names", "row_uuids"):
        if key not in inventory:
            return False, f"identity_inventory 缺 {key}"
    if str(inventory["metadata_sheet"]) != ei.GT_SYNC_SHEET_NAME:
        return False, (
            f"metadata sheet={inventory['metadata_sheet']!r} 与生产常量 "
            f"{ei.GT_SYNC_SHEET_NAME!r} 不符"
        )
    if not inventory["defined_names"] or not inventory["row_uuids"]:
        return False, "defined_names / row_uuids 至少一项为空 —— identity 载体缺失即阻断"
    return True, (
        f"artifact {str(record['artifact_sha256'])[:12]}，"
        f"{len(inventory['defined_names'])} 个 defined name / "
        f"{len(inventory['row_uuids'])} 个 row uuid"
    )


def validate_distinct_application_ids(
    facts: PilotFacts, record: Mapping[str, Any]
) -> tuple[bool, str]:
    """逐 scenario 独立 application IDs（Property 69/70 的写入侧不变量）。

    判据委派生产 :func:`~app.services.workpaper_sync.pilot_harness.assert_no_reuse_within_run`
    —— 复用规则在这里抄一份就会与 harness 的写入侧判据分叉。
    """
    from app.services.workpaper_sync import pilot_harness as ph

    ok, why = _need(record, "per_scenario_application_ids")
    if not ok:
        return False, why
    per_scenario: Mapping[str, Any] = record["per_scenario_application_ids"]
    if set(per_scenario) != set(facts.required_scenario_ids):
        missing = sorted(set(facts.required_scenario_ids) - set(per_scenario))
        extra = sorted(set(per_scenario) - set(facts.required_scenario_ids))
        return False, f"逐 scenario application id 覆盖不全：缺 {missing}、多 {extra}"
    recorded: list[tuple[str, frozenset[str]]] = []
    for scenario_id in facts.required_scenario_ids:
        ids = per_scenario[scenario_id] or []
        if not ids:
            return False, f"{scenario_id} 的 application_ids 为空"
        observation = ph.ScenarioObservation(
            scenario_id=scenario_id,
            application_ids=tuple(uuid.UUID(str(i)) for i in ids),
            supplied_inputs=frozenset(),
        )
        ph.assert_no_reuse_within_run(observation=observation, recorded=recorded)
        recorded.append((scenario_id, frozenset(str(i) for i in ids)))
    return True, f"{len(recorded)} 条 scenario 各自持有互不复用的 application id"


def validate_full_restoration(facts: PilotFacts, record: Mapping[str, Any]) -> tuple[bool, str]:
    """测试数据完整复原（AC 14.9）：前后实测计数必须逐键相等。"""
    ok, why = _need(record, "counts_before", "counts_after", "restored_at")
    if not ok:
        return False, why
    before, after = record["counts_before"], record["counts_after"]
    if not before:
        return False, "counts_before 为空 —— 空计数比对恒成立，等于没验证"
    if set(before) != set(after):
        return False, f"计数键集不同：{sorted(before)} vs {sorted(after)}"
    drift = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    if drift:
        return False, f"以下表未复原：{drift}"
    return True, f"{len(before)} 张表的行数在 pilot 前后逐键相等"


def validate_close_aggregate_artifact(
    facts: PilotFacts, record: Mapping[str, Any]
) -> tuple[bool, str]:
    """聚合 artifact（AC 10.9 / Property 63）：一个 artifact、多个 contributor。"""
    ok, why = _need(record, "artifact_sha256", "contributor_user_ids", "forcesave_initiator")
    if not ok:
        return False, why
    contributors = record["contributor_user_ids"] or []
    if len(contributors) < 2:
        return False, "聚合 artifact 必须有 ≥2 个 contributor，否则证不了「聚合」"
    if len(set(map(str, contributors))) != len(contributors):
        return False, "contributor 列表有重复 —— contributor rows 必须分表逐行记录"
    if str(record["forcesave_initiator"]) not in {str(c) for c in contributors}:
        return False, "forcesave initiator 不在 contributor 集合内"
    return True, f"1 个 artifact / {len(contributors)} 个 contributor / initiator 已定位"


def validate_close_identity_separation(
    facts: PilotFacts, record: Mapping[str, Any]
) -> tuple[bool, str]:
    """initiator / route / contributors 分离（AC 10.2 / 10.9 / Property 63）。"""
    ok, why = _need(
        record, "initiator_participant_id", "route_credential_id", "contributor_row_ids"
    )
    if not ok:
        return False, why
    initiator = str(record["initiator_participant_id"])
    route = str(record["route_credential_id"])
    rows = [str(r) for r in (record["contributor_row_ids"] or [])]
    if not initiator or not route or not rows:
        return False, "三者任一为空 —— 分表记录才能证明它们不是同一个主体"
    if initiator == route:
        return False, "initiator 与 route credential 同值 —— route 被当成授权主体（AC 10.2 明禁）"
    if route in rows:
        return False, "route credential 出现在 contributor rows 里 —— 身份未分离"
    return True, f"initiator/route/{len(rows)} 个 contributor row 三者互不相等且分表"


def validate_close_revoke_rotation(
    facts: PilotFacts, record: Mapping[str, Any]
) -> tuple[bool, str]:
    """revoke / OO drop / generation rotation（AC 10.3 / 10.4 / Property 44）。"""
    ok, why = _need(
        record,
        "revoked_participant_id",
        "oo_drop_observed",
        "write_fence_epoch_before",
        "write_fence_epoch_after",
        "generation_before",
        "generation_after",
        "cancelled_request_ids",
    )
    if not ok:
        return False, why
    drop = bool(record["oo_drop_observed"])
    fence_advanced = int(record["write_fence_epoch_after"]) > int(
        record["write_fence_epoch_before"]
    )
    rotated = str(record["generation_after"]) != str(record["generation_before"])
    if drop:
        if fence_advanced or rotated:
            return True, "OO drop 已取证；fence/generation 变化亦被记录"
        return False, "OO drop 已取证但既未提升 fence 也未旋转 generation —— 取证结果未落地"
    if not (fence_advanced and rotated):
        return False, (
            "无法证明 OO drop 时必须同时提升 write_fence_epoch 并 supersede generation"
            "（AC 10.4 原文），实测两者未同时发生"
        )
    if not record["cancelled_request_ids"]:
        return False, "无法证明 drop 时未取消 outstanding requests"
    return True, "drop 不可证 ⇒ fence 提升 + generation 旋转 + outstanding request 取消"


def validate_exactly_one_close_capture(
    facts: PilotFacts, record: Mapping[str, Any]
) -> tuple[bool, str]:
    """适用路径最终 exactly-one close-capture（AC 4.10 / Property 63）。

    分母来自生产 `CLOSE_SCENARIOS` 的 `expected_close_captures`，不在这里手写期望值。
    """
    from app.services.workpaper_sync import evidence as ev

    ok, why = _need(record, "close_captures_by_scenario")
    if not ok:
        return False, why
    observed: Mapping[str, Any] = record["close_captures_by_scenario"]
    expected = {
        s.scenario_id: s.expected_close_captures
        for s in ev.CLOSE_SCENARIOS
        if s.scenario_id in facts.required_scenario_ids
    }
    if set(observed) != set(expected):
        return False, (
            f"close-capture 观测覆盖不全：缺 {sorted(set(expected) - set(observed))}、"
            f"多 {sorted(set(observed) - set(expected))}"
        )
    bad = {k: (observed[k], expected[k]) for k in expected if int(observed[k]) != expected[k]}
    if bad:
        return False, f"以下 close 场景的 capture 数与生产期望不符：{bad}"
    return True, f"{len(expected)} 条 close 路径的 capture 数逐条等于生产声明"


#: 正文第 1 条：准入四条。**全部走生产路径反读**，见 :func:`probe_finalize_signals`。
_ADMISSION_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _p(
        "admission.task36_finalized", "admission", "已按 Task 36 finalize",
        "Task 36 finalize（candidate → published representation）之后方可注册 adapter / "
        "启用 capability；三个信号（capability / adapter 注册 / published identity 观测器）"
        "任一不成立即不得测试该 entry",
        reqs=("12.2",), props=("P49",),
        inputs=("db_entities",),
        refs=(
            f"{_SYNC}.excel_entry_gate:ExcelEntryDefinitionLoader",
            f"{_SYNC}.excel_entry_gate:FrozenEntryDefinitions",
        ),
    ),
    _p(
        "admission.resolver_published_representation", "admission",
        "resolver返回 published representation",
        "生产接线点 `attach_pilot_adapters()` 必须能从 entry_state 取到 published "
        "representation 才返回 adapter_id；返回空元组即「今天还没 finalize」",
        reqs=("12.2", "8.10"), props=("P49", "P65"),
        inputs=("db_entities",),
        refs=(f"{_SYNC}.resolution:CanonicalResolutionService",),
    ),
    _p(
        "admission.approved_per_entry_bundle", "admission", "approved per-entry bundle",
        "representation 必须绑定本 entry 自己的 approved non-null definition bundle "
        "（authority model + template + instrumentation + contract 四个 typed child）",
        reqs=("12.10", "14.16"), props=("P64",),
        inputs=("db_entities", "artifact_digests"),
        refs=(
            f"{_SYNC}.definitions:build_bundle_canonical_payload",
            f"{_SYNC}.representations:assert_bundle_snapshot_finalizable",
        ),
    ),
    _p(
        "admission.no_candidate_or_unapproved_substrate", "admission",
        "candidate、unapproved/missing-contract bundle",
        "candidate / unapproved / 缺契约的 bundle 不得进入 resolver/room/current/evidence；"
        "🔴 今天无 substrate 可查 ⇒ 判据**空转**，空转不算通过（零场景全过是本 spec 反复"
        "点名的假绿形态）",
        reqs=("8.10", "12.10"), props=("P65",),
        inputs=("db_entities",),
        refs=(f"{_SYNC}.resolution:CanonicalResolutionService",),
    ),
)

#: 正文第 3 条末句的三项"同时核对" + exactly-one 汇总。
_CLOSE_ASPECT_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _p(
        "close_aspect.exactly_one_capture_on_applicable_paths", "close_aspect",
        "验证适用路径最终 exactly-one close-capture",
        "逐条 close 路径的实测 capture 数必须等于生产 CLOSE_SCENARIOS 的声明值",
        reqs=("4.10",), props=("P63", "P69"),
        inputs=("close_barrier", "db_entities"),
        refs=(
            f"{_SYNC}.close_intent:CloseIntentService",
            f"{_SYNC}.close_intent:assert_at_most_one_open_capture",
        ),
        validator=validate_exactly_one_close_capture,
    ),
    _p(
        "close_aspect.aggregate_artifact", "close_aspect", "核对聚合 artifact",
        "同 room 两用户可贡献同一 artifact：一个 artifact / ≥2 contributor / initiator 可定位",
        reqs=("10.9", "10.2"), props=("P63",),
        inputs=("close_barrier", "db_entities", "artifact_digests"),
        refs=(
            f"{_SYNC}.rooms:ContributorSnapshot",
            f"{_SYNC}.rooms:ContributorRecord",
        ),
        validator=validate_close_aggregate_artifact,
    ),
    _p(
        "close_aspect.initiator_route_contributors_separated", "close_aspect",
        "initiator/route/contributors 分离",
        "initiator、callback route credential 与多 contributor 关系分表记录且互不相等",
        reqs=("10.2", "10.9"), props=("P63",),
        inputs=("close_barrier", "db_entities"),
        refs=(
            f"{_SYNC}.rooms:RouteCredential",
            f"{_SYNC}.rooms:mint_route_credential",
        ),
        validator=validate_close_identity_separation,
    ),
    _p(
        "close_aspect.revoke_drop_generation_rotation", "close_aspect",
        "revoke/drop/generation rotation",
        "撤销写 participant 时以 OO drop 取证；无法取证即提升 write_fence_epoch、"
        "取消 outstanding request 并 supersede generation",
        reqs=("10.3", "10.4"), props=("P44",),
        inputs=("close_barrier", "db_entities", "onlyoffice_forcesave"),
        refs=(
            f"{_SYNC}.rooms:RevokeOutcome",
            f"{_SYNC}.rooms:revocation_policy",
        ),
        validator=validate_close_revoke_rotation,
    ),
)

#: 正文第 4 条：证据通道。今天全部 UNVERIFIABLE，但判据现在就可执行 ——
#: 将来只需提供执行记录即可判定，**无需改判据**。
_CHANNEL_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _p(
        "channel.playwright_network_console", "evidence_channel",
        "联合 Playwright network/console",
        "前端 network + console 证据：network 非空、零 error 级 console、har 内容寻址",
        reqs=("14.8",), props=("P58",),
        inputs=("browser_trace",),
        refs=(f"{_SYNC}.pilot_harness:assert_trace_bundle_published",),
        validator=validate_playwright_trace,
    ),
    _p(
        "channel.recovery_application_operation_timeline", "evidence_channel",
        "recovery+application+operation timeline",
        "两条生产顺序常量逐条成立（委派生产 evaluate_timeline_order）",
        reqs=("14.8",), props=("P58",),
        inputs=("server_timeline", "recovery_lifecycle"),
        refs=(
            f"{_SYNC}.pilot_harness:evaluate_timeline_order",
            f"{_SYNC}.timeline:SyncTimelineService",
        ),
        validator=validate_timeline_triple,
    ),
    _p(
        "channel.db_timestamps", "evidence_channel", "DB timestamps",
        "数据库时间戳必须来自服务端时钟、tz-aware 且单调",
        reqs=("14.8",), props=("P58",),
        inputs=("server_timeline", "db_entities"),
        refs=(f"{_SYNC}.timeline:assert_server_clock_only",),
        validator=validate_db_timestamps,
    ),
    _p(
        "channel.published_result_representation", "evidence_channel",
        "published result representation",
        "结果只能是 published result representation，且 materialize→extract 往返等值",
        reqs=("6.11", "8.10", "14.6"), props=("P29", "P65"),
        inputs=("db_entities", "artifact_digests"),
        refs=(
            f"{_SYNC}.representations:RepresentationService",
            f"{_SYNC}.excel_extract:extract_projection",
        ),
        validator=validate_published_result_representation,
    ),
    _p(
        "channel.authority_model", "evidence_channel", "authority model",
        "authority model 枚举与其 definition digest 必须等于本 entry 现算值",
        reqs=("14.16", "14.6"), props=("P64",),
        inputs=("artifact_digests",),
        refs=(f"{_SYNC}.definitions:canonical_digest",),
        validator=validate_authority_model,
    ),
    _p(
        "channel.bundle_digest_typed_slots", "evidence_channel", "bundle digest/typed slots",
        "bundle canonical digest + template/instrumentation/contract 三类 typed child "
        "逐个等于现算值，且 slot type 全为 definition（marker 不得冒充）",
        reqs=("12.10", "14.16"), props=("P64",),
        inputs=("artifact_digests",),
        refs=(
            f"{_SYNC}.definitions:build_bundle_canonical_payload",
            f"{_SYNC}.evidence_freshness:recompute_bundle_canonical_digest",
        ),
        validator=validate_bundle_digest_typed_slots,
    ),
    _p(
        "channel.artifact_identity_inventory", "evidence_channel", "artifact/identity inventory",
        "artifact 的 identity inventory：metadata sheet 名取自生产常量，"
        "defined names / row uuids 非空",
        reqs=("6.16", "14.5"), props=("P66",),
        inputs=("artifact_digests", "onlyoffice_forcesave"),
        refs=(
            f"{_SYNC}.excel_instrumentation:read_back_identity",
            f"{_SYNC}.excel_instrumentation:GT_SYNC_SHEET_NAME",
        ),
        validator=validate_artifact_identity_inventory,
    ),
    _p(
        "channel.per_scenario_distinct_application_ids", "evidence_channel",
        "逐 scenario 记录独立 application IDs并入库",
        "每条 required scenario 各自持有非空且互不复用的 application id"
        "（委派生产 assert_no_reuse_within_run）",
        reqs=("12.10",), props=("P69",),
        inputs=("db_entities",),
        refs=(
            f"{_SYNC}.pilot_harness:assert_no_reuse_within_run",
            f"{_SYNC}.pilot_harness:assert_no_reuse_across_entry",
        ),
        validator=validate_distinct_application_ids,
    ),
    _p(
        "channel.full_data_restoration", "evidence_channel", "完整复原数据",
        "pilot 前后逐表行数相等 —— 「完整复原」是实测计数比对，不是一句声明",
        reqs=("14.9",), props=("P49",),
        inputs=("db_entities",),
        refs=(f"{_SYNC}.retention:RetentionPolicyService",),
        validator=validate_full_restoration,
    ),
)

#: 每个 pilot 都要跑的 probe 全集（42 条）。
PER_PILOT_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _ADMISSION_PROBES + _SCENARIO_PROBES + _CLOSE_ASPECT_PROBES + _CHANNEL_PROBES
)

#: 门自身的 probe（5 条，不按 pilot 展开）。它们**可以**今天就通过 ——
#: 但只能靠真跑，不能靠声明。
GATE_PROBES: Final[tuple[ProbeSpec, ...]] = (
    _p(
        "gate.no_documentary_pass", "gate", "不得以文档声明通过",
        "把一条带 result 字段的执行记录喂进真正的记录校验器，必须被 "
        "DocumentaryClaimRejected 拒绝；拒绝没发生就不给这条 probe 判 passed",
        reqs=("14.9", "12.2"), props=("P49", "P69"),
    ),
    _p(
        "gate.blocks_wave5", "gate", "阻断 Wave 5",
        "只要有一条 probe 未 passed，本门的退出码必须非零（阻断 Wave 5）",
        reqs=("12.2",), props=("P49",),
    ),
    _p(
        "gate.ordering_upstream_gap_before_black_box", "gate",
        "任一 probe 未真实执行时标 UNVERIFIABLE",
        "upstream-gap 判 failed 且排在黑盒判定之前 —— 源码位置 + 反事实行为双侧实测；"
        "顺序交换会让缺实现的场景在接上真实 OO 后自动刷绿",
        reqs=("14.9",), props=("P49",),
    ),
    _p(
        "gate.admission_is_state_sensitive", "gate", "已按 Task 36 finalize",
        "用替身把四个 finalize 信号全部翻成「已就绪」并复跑同一函数，准入判定必须改变 "
        "—— 证明本门真实反读状态而不是硬编码 false",
        reqs=("12.2",), props=("P49",),
    ),
    _p(
        "gate.mutation_four_state", "gate", "14.7",
        "变异检验四态：declared==executed 且全部 RED，否则本门不认为守卫成立",
        reqs=("14.7",), props=("P49",),
    ),
)

ALL_PROBE_SPECS: Final[tuple[ProbeSpec, ...]] = PER_PILOT_PROBES + GATE_PROBES

#: Task 44 正文要求「独立验证」的 16 条 Property。封闭元组 —— 少一条即结构性失效。
DECLARED_PROPERTIES: Final[tuple[str, ...]] = (
    "P18", "P25", "P26", "P29", "P43", "P44", "P49", "P55",
    "P56", "P58", "P62", "P63", "P64", "P65", "P66", "P69",
)


# ═══════════════════════════════════════════════════════════════════════════
# 4. finalize 状态：**真实反读生产路径**（本门最容易被写成硬编码的一段）
# ═══════════════════════════════════════════════════════════════════════════


class _StubResult:
    """`session.execute()` 的返回替身：只承载一个值，形态与 SQLAlchemy 一致。"""

    def __init__(self, value: Any) -> None:
        self._value = value

    def scalars(self) -> "_StubResult":
        return self

    def first(self) -> Any:
        return self._value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _StubSession:
    """只替换 DB 的 session 替身。

    🔴 被替换的**只有数据库**：`attach_pilot_adapters` 本体是真跑的生产函数。
    本门在没有真实库的环境里要回答的问题是「生产接线点在 entry_state 没有 published
    representation 时会不会注册 adapter」，而那条判断完全发生在 Python 侧。
    每次 `execute` 按序返回预置值，用完最后一个则一直返回它。
    """

    def __init__(self, values: Sequence[Any]) -> None:
        self._values = list(values) or [None]
        self.calls = 0

    async def execute(self, _statement: Any) -> _StubResult:
        value = self._values[min(self.calls, len(self._values) - 1)]
        self.calls += 1
        return _StubResult(value)


class _StubRepresentation:
    """entry_state 指向的 representation 行替身（只用到两个字段）。"""

    def __init__(self, bundle_id: Any) -> None:
        self.id = uuid.uuid4()
        self.definition_bundle_id = bundle_id


@dataclass(frozen=True)
class FinalizeSignals:
    """一个 pilot 的 finalize / 准入信号。每一项都由生产调用得出。"""

    capability_enabled: bool
    capability_reject: str
    adapter_registered: bool
    registered_adapter_ids: tuple[str, ...]
    published_identity_observer: str
    observer_detail: str
    attach_without_representation: tuple[str, ...]
    attach_with_representation_without_bundle: tuple[str, ...]
    #: 生产接线点在"无 published representation"那一跑里**读了几次库**。
    #:
    #: 🔴 这不是装饰：Tasks 41/42/43 的 `attach_pilot_adapters` 在 capability 门就
    #: `return ()` 且**一次库都不读**（Task 41 因 raise 导致整条 sync 路由 500 后改的），
    #: 而 Task 40 的版本先查 entry_state。把这个差异量出来，顺序被重排时守卫会打红。
    attach_session_reads: int = 0

    @property
    def admitted(self) -> bool:
        """🔴 四项**全部**成立才算准入。缺一项即该 entry 不进入测试范围。"""
        return (
            self.capability_enabled
            and self.adapter_registered
            and self.published_identity_observer == "available"
            and bool(self.attach_without_representation)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "capability_enabled": self.capability_enabled,
            "capability_reject": self.capability_reject,
            "adapter_registered": self.adapter_registered,
            "registered_adapter_ids": list(self.registered_adapter_ids),
            "published_identity_observer": self.published_identity_observer,
            "observer_detail": self.observer_detail,
            "attach_without_representation": list(self.attach_without_representation),
            "attach_with_representation_without_bundle": list(
                self.attach_with_representation_without_bundle
            ),
            "attach_session_reads": self.attach_session_reads,
        }


def probe_finalize_signals(module: Any) -> FinalizeSignals:
    """逐个调用生产符号反读 finalize 状态。

    🔴 四个信号全部经 `getattr(module, name)` **在调用时刻**取值 —— 这是"观测器补上后
    本门自动感知"的机制所在：任何一侧被实现/替身替换，本函数的返回值立即改变
    （:func:`gate_probe_admission_is_state_sensitive` 把这件事实测下来）。

    没有任何一处返回硬编码常量；没有 `except: pass`。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync.adapters import registry as registry_module

    adapter_id = str(getattr(module, "PILOT_ADAPTER_ID"))

    # ① manifest capability：生产断言，抛即未启用。
    capability_enabled, capability_reject = True, ""
    try:
        getattr(module, "assert_manifest_capability_enabled")()
    except Exception as exc:  # noqa: BLE001 - 记成信号，不降级
        capability_enabled, capability_reject = False, f"{type(exc).__name__}: {exc}"

    # ② 生产 registry 里到底有没有这个 adapter。
    production = registry_module.build_production_registry()
    registered = tuple(sorted(reg.adapter_id for reg in production.registrations()))

    # ③ published representation → FrozenEntryDefinitions 观测器是否可用（真跑 coroutine）。
    #
    # 🔴 三态而不是二态（Task 75 起）：探针只能拿 `None` 去问，而**已实现**的观测器面对
    #    `representation=None` 的正确行为就是抛 `RepresentationShapeError`（「无法确定
    #    project scope」）。把它记成 `unavailable` 会在 Task 75 之后变成一句假话。
    #    判据因此按**异常类型**分型：观测器自己的 shape 错误 ⇒ 已实现（available）；
    #    其它任何异常 ⇒ 仍未实现或接线坏了（unavailable，含原先那条欠账 fail closed）。
    observer = getattr(module, "resolve_published_frozen_definitions")
    try:
        from app.services.workpaper_sync.published_identity_observer import (
            RepresentationShapeError,
        )
    except ImportError:  # pragma: no cover - 观测器模块不存在即视为未实现
        RepresentationShapeError = None  # type: ignore[assignment]
    try:
        asyncio.run(observer(session=None, representation=None, contract=None))
        observer_state, observer_detail = "available", "观测器返回了 FrozenEntryDefinitions"
    except Exception as exc:  # noqa: BLE001 - 分型记录，不吞
        implemented = (
            RepresentationShapeError is not None
            and isinstance(exc, RepresentationShapeError)
        )
        observer_state = "available" if implemented else "unavailable"
        observer_detail = f"{type(exc).__name__}: {str(exc)[:220]}"

    # ④ 生产接线点：两种 DB 状态各跑一次（只替换 session，函数本体是生产的）。
    attach = getattr(module, "attach_pilot_adapters")

    def _fresh_registry() -> Any:
        from app.services.workpaper_sync.entry_profile import load_entry_manifest

        return registry_module.WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())

    empty_session = _StubSession([None])
    without = tuple(asyncio.run(attach(_fresh_registry(), session=empty_session)))
    without_bundle = tuple(
        asyncio.run(
            attach(
                _fresh_registry(),
                session=_StubSession([uuid.uuid4(), _StubRepresentation(None)]),
            )
        )
    )
    return FinalizeSignals(
        capability_enabled=capability_enabled,
        capability_reject=capability_reject,
        adapter_registered=adapter_id in registered,
        registered_adapter_ids=registered,
        published_identity_observer=observer_state,
        observer_detail=observer_detail,
        attach_without_representation=without,
        attach_with_representation_without_bundle=without_bundle,
        attach_session_reads=empty_session.calls,
    )


def collect_pilot_facts(ref: PilotRef) -> PilotFacts:
    """一个 pilot 的全部实测事实：required set、四个 digest、bundle、准入信号。"""
    _ensure_backend_on_path()
    from app.services.workpaper_sync import evidence as ev
    from app.services.workpaper_sync.definitions import (
        build_bundle_canonical_payload,
        canonical_digest,
    )
    from app.services.workpaper_sync.models import BundleSlot

    module = load_pilot_module(ref)
    entry_id = str(module.PILOT_ENTRY_ID)
    entries = ev.manifest_entries_by_id(ev.load_entry_manifest())
    if entry_id not in entries:
        raise GateStructuralError(
            f"pilot {ref.pilot_class}: entry {entry_id} 不在 source-backed manifest 里"
        )
    entry = entries[entry_id]
    required = ev.derive_for_manifest_entry(entry, authority_model=module.AUTHORITY_MODEL)

    authority = canonical_digest(module.authority_model_payload())
    template = canonical_digest(module.template_definition_payload())
    instrumentation = canonical_digest(module.instrumentation_definition_payload())
    contract = canonical_digest(dict(module.load_pilot_contract().canonical_payload))
    bundle = canonical_digest(
        build_bundle_canonical_payload(
            authority_model=module.AUTHORITY_MODEL,
            authority_model_definition_sha256=authority,
            slots={
                BundleSlot.template: {
                    "type": "definition",
                    "ref": f"definition:{uuid.uuid4()}",
                    "digest": template,
                },
                BundleSlot.instrumentation: {
                    "type": "definition",
                    "ref": f"definition:{uuid.uuid4()}",
                    "digest": instrumentation,
                },
                BundleSlot.contract: {
                    "type": "definition",
                    "ref": f"definition:{uuid.uuid4()}",
                    "digest": contract,
                },
            },
        )
    )
    # 🔴 close 谓词**双源**：一侧是生产推导的 `close_required`，另一侧是直接读 manifest
    # 的三个字段。两侧都读 evidence 会退化成自我比对（假绿第③源）。
    editability = str(entry.get("editability") or "")
    capability = str(entry.get("capability") or "")
    room_model = str(entry.get("room_model") or "")
    raw_predicate = editability == "editable" and (
        capability == "bidirectional" or room_model == "shared"
    )
    return PilotFacts(
        ref=ref,
        module=module,
        entry_id=entry_id,
        adapter_id=str(module.PILOT_ADAPTER_ID),
        entry=entry,
        required_scenario_ids=tuple(sorted(s.scenario_id for s in required.scenarios)),
        required_digest=required.digest,
        close_required=bool(required.close_required),
        close_predicate_raw=raw_predicate,
        capability=capability,
        editability=editability,
        room_model=room_model,
        authority_model=module.AUTHORITY_MODEL.value,
        authority_model_definition_sha256=authority,
        template_definition_sha256=template,
        instrumentation_definition_sha256=instrumentation,
        contract_canonical_sha256=contract,
        bundle_sha256=bundle,
        signals=probe_finalize_signals(module),
        registered_debts={
            name: getattr(module, name)
            for name in getattr(module, "__all__", ())
            if name.startswith("UPSTREAM_DEBT_")
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 与 tasks.md / design.md 的真源锁
# ═══════════════════════════════════════════════════════════════════════════

_TASK_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"^- \[[ x~\-]\] (\d+)\. ", flags=re.MULTILINE
)


def read_task_body(task_number: int = TASK_NUMBER, *, text: str | None = None) -> str:
    """从 tasks.md 抠出某个任务的正文（含标题行，不含下一任务）。

    🔴 按**任务编号**定位而不是行号：行号随上游任务增删漂移。checkbox 状态用 `[ x~-]`
    通配 —— 本门不因 Task 44 被勾选而失效（勾选是簿记，不是事实）。
    """
    body = text if text is not None else _TASKS_MD.read_bytes().decode("utf-8")
    starts: list[tuple[int, int, int]] = [
        (int(m.group(1)), m.start(), m.end()) for m in _TASK_HEADER_RE.finditer(body)
    ]
    for index, (number, start, _end) in enumerate(starts):
        if number != task_number:
            continue
        stop = starts[index + 1][1] if index + 1 < len(starts) else len(body)
        section = body.find("\n### ", start)
        if 0 <= section < stop:
            stop = section
        return body[start:stop]
    raise GateStructuralError(f"tasks.md 里找不到 Task {task_number} —— 本门与任务正文脱钩")


def assert_probes_anchored_in_task_text(
    specs: Sequence[ProbeSpec] = ALL_PROBE_SPECS, *, task_body: str | None = None
) -> dict[str, int]:
    """每条 probe 的 `anchor` 必须逐字出现在 Task 44 正文里。

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
            "以下 probe 的锚点在 Task 44 正文里找不到（本门已与任务正文脱钩）：\n  "
            + "\n  ".join(missing)
        )
    return counts


def task_requirement_ids(*, task_body: str | None = None) -> tuple[str, ...]:
    """Task 44 `_Requirements:` 行里逐字列出的 AC 编号。"""
    body = task_body if task_body is not None else read_task_body()
    match = re.search(r"_Requirements:\s*([^_]+)_", body)
    if match is None:
        raise GateStructuralError("Task 44 正文缺 `_Requirements:` 行")
    return tuple(sorted({part.strip() for part in match.group(1).split(",") if part.strip()}))


def design_property_titles(
    properties: Sequence[str] = DECLARED_PROPERTIES, *, text: str | None = None
) -> dict[str, str]:
    """design.md 里 16 条 Property 的标题。缺一条即结构性失效。"""
    body = text if text is not None else _DESIGN_MD.read_bytes().decode("utf-8")
    out: dict[str, str] = {}
    missing: list[str] = []
    for prop in properties:
        number = prop[1:]
        match = re.search(rf"(?m)^### Property {number}:\s*(.+)$", body)
        if match is None:
            missing.append(prop)
            continue
        out[prop] = match.group(1).strip()
    if missing:
        raise GateStructuralError(
            f"design.md 里找不到以下 Property 的定义：{missing} —— "
            "Task 44 要求独立验证它们，定义缺失即无从验证"
        )
    return out


def _assert_scenarios_known() -> None:
    """scenario probe 的 `scenario_id` 必须都在生产 oracle 表里。"""
    _ensure_backend_on_path()
    from app.services.workpaper_sync import pilot_harness as ph

    declared = {s.scenario_id for s in PER_PILOT_PROBES if s.scenario_id}
    unknown = sorted(declared - set(ph.SCENARIO_ORACLES))
    if unknown:
        raise GateStructuralError(
            f"以下 scenario probe 在生产 SCENARIO_ORACLES 里没有 oracle：{unknown}"
        )


def _resolve_production_refs(spec: ProbeSpec) -> tuple[str, ...]:
    """逐个 import + getattr。符号消失即抛 —— 不等真实 OO 才发现被测对象已不在。"""
    _ensure_backend_on_path()
    resolved: list[str] = []
    for ref in spec.production_refs:
        module_name, _, attr = ref.partition(":")
        if not module_name or not attr:
            raise GateStructuralError(f"{spec.probe_id}: production_ref {ref!r} 必须形如 module:attr")
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001
            raise GateStructuralError(
                f"{spec.probe_id}: 无法 import {module_name!r}: {type(exc).__name__}: {exc}"
            ) from exc
        if not hasattr(module, attr):
            raise GateStructuralError(
                f"{spec.probe_id}: {module_name} 里没有 {attr!r} —— "
                "probe 声明还在，被测的生产符号已经不在了"
            )
        resolved.append(ref)
    return tuple(resolved)


# ═══════════════════════════════════════════════════════════════════════════
# 6. probe 判定（顺序不可交换）
# ═══════════════════════════════════════════════════════════════════════════

#: probe 结果三态。与 V151 `ck_wpees_result` 同域。
RESULT_PASSED: Final[str] = "passed"
RESULT_FAILED: Final[str] = "failed"
RESULT_UNVERIFIABLE: Final[str] = "unverifiable"

#: 「本次没有真实 OO / 浏览器」的哨兵，与 harness 共用（不另造一个）。
def _not_executed() -> str:
    _ensure_backend_on_path()
    from app.services.workpaper_sync import pilot_harness as ph

    return str(ph.NOT_EXECUTED)


@dataclass(frozen=True)
class ProbeRow:
    """一条 probe 的判定结果。逐条可追踪 —— 这就是「任何一个缺场景都保持 UNVERIFIABLE」
    的度量形态。"""

    probe_id: str
    probe_class: str
    pilot_class: str | None
    entry_id: str | None
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
            "pilot_class": self.pilot_class,
            "entry_id": self.entry_id,
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
    sentinel = _not_executed()
    return Environment(onlyoffice_build=sentinel, browser_build=sentinel)


def assert_records_carry_no_claim(records: Any, *, where: str = "<root>") -> None:
    """🔴 执行记录里不得出现结果声明字段（AC 14.9 / Property 49 / Property 69）。

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
        return {"environment": {}, "supplied_inputs": {}, "probes": {}}
    payload = json.loads(path.read_bytes().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise GateStructuralError(f"{path}: 执行记录根必须是对象")
    assert_records_carry_no_claim(payload, where=str(path.name))
    return {
        "environment": dict(payload.get("environment") or {}),
        "supplied_inputs": dict(payload.get("supplied_inputs") or {}),
        "probes": dict(payload.get("probes") or {}),
    }


def _scenario_denominator_facts(facts: PilotFacts) -> dict[str, Any]:
    """scenario probe ↔ 生产 required set **双向**核对。

    * 正向：声明了 probe 但不在 required set 里 ⇒ 该 probe 只能 failed/unverifiable；
    * 反向：required set 里有场景却没人声明 probe ⇒ 分母悄悄缩小，**结构性失效**。
    """
    declared = {s.scenario_id for s in _SCENARIO_PROBES if s.scenario_id}
    required = set(facts.required_scenario_ids)
    unclaimed = sorted(required - declared)
    if unclaimed:
        raise GateStructuralError(
            f"pilot {facts.ref.pilot_class}: required set 里的 {unclaimed} 没有任何 probe "
            "声明 —— 分母会悄悄缩小（本 spec 反复点名的假绿第①源）"
        )
    return {
        "declared_scenario_probes": len(declared),
        "required_scenarios": len(required),
        "declared_not_required": sorted(declared - required),
    }


def _supply_gap_debt(facts: PilotFacts) -> str:
    """Task 75 之后「finalize 仍做不成」的那一环：approved bundle 的**生产侧供给**。

    文本取 `registry.DELIVERED_PER_ENTRY_CONTRACTS` 里本 entry 那一行的 `reason`（单一
    真源；Task 75 已把它改成指名「观测器已交付 / 供给是 Task 76 的交付」），本文件不另写
    一份说明 —— 另写一份就是第二真源，登记表一改这里就悄悄过期。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync.adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS

    for row in DELIVERED_PER_ENTRY_CONTRACTS:
        if str(row.get("entry_id")) == str(facts.entry_id):
            return f"supply_gap[{row['contract_id']}]: {row['reason']}"
    raise GateStructuralError(
        f"entry {facts.entry_id} 不在 per-entry 契约交付登记表里 —— pilot 的契约身份丢了，"
        "本门不得替它编一个阻断原因"
    )


def _debt_for_missing_scenario(facts: PilotFacts, scenario_id: str) -> str | None:
    """某条被正文枚举、却进不了 required set 的场景，是否已有登记的上游欠账。

    今天命中的是 `UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY`：
    动态族被门控在 `scenario_profile.mount_cardinality`（量的是前端宿主挂载基数），
    对任何 xlsx entry 结构性不可达。**不改那个门控去硬凑分母** —— 如实度量并登记。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync import evidence as ev

    dynamic_ids = {s.scenario_id for s in ev.DYNAMIC_SCENARIOS}
    if scenario_id not in dynamic_ids:
        return None
    for name, text in facts.registered_debts.items():
        if "DYNAMIC_FAMILY" in name:
            return f"{name}: {text}"
    # 🔴 本 pilot 自己没登记，就到**另外三个** pilot 上找同一条平台级欠账：这条缺口是
    # `evidence.derive_for_manifest_entry` 的门控问题，四个 entry 共有。找到即沿用已注册
    # 的名字（不重复发明），同时点名"本 pilot 未登记"这一实测缺陷。
    for other in PILOTS:
        if other.pilot_class == facts.ref.pilot_class:
            continue
        module = load_pilot_module(other)
        for name in getattr(module, "__all__", ()):
            if name.startswith("UPSTREAM_DEBT_") and "DYNAMIC_FAMILY" in name:
                return (
                    f"{name}（Task {other.owner_task} 登记；🔴 Task "
                    f"{facts.ref.owner_task} 的 pilot 模块**未**登记这条同源欠账）: "
                    f"{getattr(module, name)}"
                )
    return (
        "动态族场景进不了 required set，且四个 pilot 都没登记对应 upstream debt —— "
        "缺场景必须有 owner"
    )


def evaluate_probe(
    spec: ProbeSpec,
    facts: PilotFacts,
    *,
    environment: Environment,
    record: Mapping[str, Any] | None,
    supplied_inputs: frozenset[str],
) -> ProbeRow:
    """判定一条 per-pilot probe。**顺序不可交换**，理由见模块 docstring 第 3 条。

    1. schema 不可表达（V151 无法把它记成 passed）⇒ `unverifiable`
    2. **上游实现缺口** ⇒ `failed` + `upstream_gap`（缺的是实现不是环境）
    3. pilot 未准入 ⇒ `unverifiable` + `pilot_not_admitted`
    4. 真实黑盒未执行 ⇒ `unverifiable` + `real_onlyoffice_not_executed`
    5. 执行记录缺失 ⇒ `unverifiable` + `execution_record_missing`
    6. 真判据（validator / 生产 scenario oracle）

    2 必须在 4 之前：否则缺实现的场景在没有 OO 的环境里显示成 `unverifiable`，
    接上真实 OO 就会**自动刷绿**，而它们其实永远不会通过。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync import evidence as ev
    from app.services.workpaper_sync import pilot_harness as ph

    _resolve_production_refs(spec)
    scenario_id = spec.scenario_id
    in_required = bool(scenario_id) and scenario_id in facts.required_scenario_ids
    oracle = ph.SCENARIO_ORACLES.get(scenario_id) if scenario_id else None
    requires: frozenset[str] = (
        frozenset(i.value for i in oracle.requires) if oracle else frozenset(spec.evidence_inputs)
    )
    unreal_black_box: list[str] = []
    if "onlyoffice_forcesave" in requires and not environment.real_onlyoffice:
        unreal_black_box.append("onlyoffice_build")
    if "browser_trace" in requires and not environment.real_browser:
        unreal_black_box.append("browser_build")
    oracle_echo: dict[str, Any] | None = None
    if oracle is not None and in_required:
        scenario = next(
            s
            for s in ph.all_declared_scenarios()
            if s.scenario_id == scenario_id
        )
        echo = ph.run_scenario_oracle(
            scenario=scenario,
            oracle=oracle,
            observation=ph.ScenarioObservation(scenario_id=str(scenario_id)),
            onlyoffice_build=environment.onlyoffice_build,
            browser_build=environment.browser_build,
        )
        oracle_echo = {"result": echo.outcome.value, "error_code": echo.error_code}

    blocking: list[str] = []
    notes: list[str] = []

    # ── 收集**全部**未满足条件（error_code 只取第一条，但事实一条不丢）──────
    schema_note = ev.SCHEMA_UNREPRESENTABLE_SCENARIOS.get(str(scenario_id))
    if schema_note:
        blocking.append("schema_unrepresentable")
    debt: str | None = None
    if scenario_id and not in_required:
        debt = _debt_for_missing_scenario(facts, str(scenario_id))
        blocking.append("enumerated_scenario_not_in_required_set")
    if oracle is not None and oracle.upstream_debt:
        debt = debt or oracle.upstream_debt
        blocking.append("oracle_upstream_debt")
    if spec.probe_class == "admission" and not facts.signals.admitted:
        observer_debt = next(
            (
                f"{name}: {text}"
                for name, text in facts.registered_debts.items()
                if "PUBLISHED_IDENTITY_OBSERVER" in name
            ),
            None,
        )
        # 🔴 Task 75 起 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER` 已结清并删除 ⇒ 上面那条
        #    查找恒 None。但「finalize 仍做不成」这件事**没有**消失，只是换了一环：缺的
        #    是 approved bundle → published representation 的生产侧 provisioner（Task 76），
        #    仍属**实现**缺口而不是环境缺口 ⇒ 这些 admission probe 必须继续是
        #    `failed` + `upstream_gap`，不能悄悄降级成 `unverifiable`。
        #    debt 文本取交付登记表里那一行的 `reason`（单一真源，Task 75 已把它改成指名
        #    Task 75 已交付 / Task 76 供给），不在本文件另写一份说明。
        debt = debt or observer_debt or _supply_gap_debt(facts)
        blocking.append("finalize_blocked")
    if spec.probe_class != "admission" and not facts.signals.admitted:
        blocking.append("pilot_not_admitted")
    if spec.probe_class == "close_aspect" and not facts.close_required:
        blocking.append("close_predicate_not_matched")
    if unreal_black_box:
        blocking.append("real_black_box_not_executed")
        notes.append(f"仍是哨兵的黑盒环境项：{unreal_black_box}")
    if record is None:
        blocking.append("execution_record_missing")
    missing_inputs = sorted(requires - supplied_inputs)
    if missing_inputs:
        blocking.append("evidence_input_missing")
        notes.append(f"该 probe 需要 {sorted(requires)}，本次提供 {sorted(supplied_inputs)}")

    # ── 判定（顺序即上面 docstring 的 1..6）──────────────────────────────
    if schema_note:
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
            scenario_id, spec.anchor, RESULT_UNVERIFIABLE, "scenario_kind_unrepresentable",
            tuple(blocking), spec.requirements, spec.properties,
            tuple(notes + [schema_note]), oracle_echo,
        )
    if debt is not None:
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
            scenario_id, spec.anchor, RESULT_FAILED, "upstream_gap",
            tuple(blocking), spec.requirements, spec.properties,
            tuple(notes + [debt]), oracle_echo,
        )
    if "pilot_not_admitted" in blocking:
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
            scenario_id, spec.anchor, RESULT_UNVERIFIABLE, "pilot_not_admitted",
            tuple(blocking), spec.requirements, spec.properties,
            tuple(
                notes
                + [
                    f"Task {facts.ref.owner_task} 的 pilot 未按 Task 36 finalize："
                    f"capability_enabled={facts.signals.capability_enabled} / "
                    f"adapter_registered={facts.signals.adapter_registered} / "
                    f"observer={facts.signals.published_identity_observer}"
                ]
            ),
            oracle_echo,
        )
    if "close_predicate_not_matched" in blocking:
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
            scenario_id, spec.anchor, RESULT_UNVERIFIABLE, "close_predicate_not_matched",
            tuple(blocking), spec.requirements, spec.properties,
            tuple(
                notes
                + [
                    "本 entry 不满足 `editable=true AND (capability=bidirectional OR "
                    f"room_model=shared)`：editability={facts.editability} / "
                    f"capability={facts.capability} / room_model={facts.room_model}"
                ]
            ),
            oracle_echo,
        )
    if "real_black_box_not_executed" in blocking:
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
            scenario_id, spec.anchor, RESULT_UNVERIFIABLE, "real_onlyoffice_not_executed",
            tuple(blocking), spec.requirements, spec.properties,
            tuple(
                notes
                + [
                    f"onlyoffice_build={environment.onlyoffice_build} / "
                    f"browser_build={environment.browser_build} —— Property 49：probe/pilot "
                    "未实际通过时必须保持 UNVERIFIABLE，不得因文档声明计为通过"
                ]
            ),
            oracle_echo,
        )
    if record is None:
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
            scenario_id, spec.anchor, RESULT_UNVERIFIABLE, "execution_record_missing",
            tuple(blocking), spec.requirements, spec.properties,
            tuple(notes + ["本次运行没有为该 probe 提供真实执行记录"]), oracle_echo,
        )
    if missing_inputs:
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
            scenario_id, spec.anchor, RESULT_UNVERIFIABLE, "evidence_input_missing",
            tuple(blocking), spec.requirements, spec.properties, tuple(notes), oracle_echo,
        )

    # ── 6. 真判据 ────────────────────────────────────────────────────────
    if spec.validator is not None:
        try:
            ok, detail = spec.validator(facts, record)
        except Exception as exc:  # noqa: BLE001 - 判据自身出错必须记成 failed，不得吞成"没数据"
            return ProbeRow(
                spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
                scenario_id, spec.anchor, RESULT_FAILED, "validator_error",
                tuple(blocking), spec.requirements, spec.properties,
                tuple(notes + [f"{type(exc).__name__}: {exc}"]), oracle_echo,
            )
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
            scenario_id, spec.anchor,
            RESULT_PASSED if ok else RESULT_FAILED,
            None if ok else "validator_rejected",
            tuple(blocking), spec.requirements, spec.properties,
            tuple(notes + [detail]), oracle_echo,
        )
    if oracle is not None:
        scenario = next(
            s for s in ph.all_declared_scenarios() if s.scenario_id == scenario_id
        )
        observation = _observation_from_record(str(scenario_id), record, supplied_inputs)
        verdict = ph.run_scenario_oracle(
            scenario=scenario,
            oracle=oracle,
            observation=observation,
            onlyoffice_build=environment.onlyoffice_build,
            browser_build=environment.browser_build,
        )
        return ProbeRow(
            spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
            scenario_id, spec.anchor, verdict.outcome.value, verdict.error_code,
            tuple(blocking), spec.requirements, spec.properties,
            tuple(notes + list(verdict.notes)), oracle_echo,
        )
    return ProbeRow(
        spec.probe_id, spec.probe_class, facts.ref.pilot_class, facts.entry_id,
        scenario_id, spec.anchor, RESULT_UNVERIFIABLE, "no_oracle_declared",
        tuple(blocking + ["no_oracle_declared"]), spec.requirements, spec.properties,
        tuple(notes + ["该 probe 既没有 validator 也没有 scenario oracle —— 判据缺失"]),
        oracle_echo,
    )


def _observation_from_record(
    scenario_id: str, record: Mapping[str, Any], supplied: frozenset[str]
) -> Any:
    """把执行记录翻成生产 `ScenarioObservation`。

    只搬运**观测量**（实体 id / 时间戳 / close capture 数），一个结果字段都不搬 ——
    `record_scenario` 的签名里根本没有 `result`（Property 69）。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync import pilot_harness as ph

    def _ids(key: str) -> tuple[uuid.UUID, ...]:
        return tuple(uuid.UUID(str(v)) for v in (record.get(key) or ()))

    timeline_raw = record.get("server_timeline") or {}
    return ph.ScenarioObservation(
        scenario_id=scenario_id,
        operation_ids=_ids("operation_ids"),
        application_ids=_ids("application_ids"),
        recovery_case_ids=_ids("recovery_case_ids"),
        content_version_ids=_ids("content_version_ids"),
        representation_ids=_ids("representation_ids"),
        trace_bundle_sha256=str(record.get("trace_bundle_sha256") or ""),
        server_timeline=_iso_datetimes(timeline_raw),
        observed_close_captures=record.get("observed_close_captures"),
        recovery_precondition_zero_entities=record.get("recovery_precondition_zero_entities"),
        supplied_inputs=frozenset(
            getattr(ph.EvidenceInput, name) for name in sorted(supplied)
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. 门自身的 probe（可以今天就通过，但只能靠真跑）
# ═══════════════════════════════════════════════════════════════════════════


def ordering_facts() -> dict[str, Any]:
    """「upstream-gap 判 failed 且排在黑盒之前」—— 源码位置 + 反事实行为双侧实测。

    形态与 Task 43 evidence 的 `_ordering_facts` 保持一致（同一条不变量，不另造词汇），
    但这里**同时**核验本门 :func:`evaluate_probe` 的顺序，而不只是生产 oracle 的。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync import pilot_harness as ph

    def _line_of(source: str, needle: str) -> int:
        for index, line in enumerate(source.splitlines()):
            if needle in line:
                return index
        return -1

    production = inspect.getsource(ph.run_scenario_oracle)
    gate = inspect.getsource(evaluate_probe)
    prod_debt = _line_of(production, "if oracle.upstream_debt:")
    prod_black = _line_of(production, "if oracle.needs_black_box:")
    gate_debt = _line_of(gate, "if debt is not None:")
    gate_black = _line_of(gate, 'if "real_black_box_not_executed" in blocking:')
    return {
        "production_upstream_debt_branch_line": prod_debt,
        "production_black_box_branch_line": prod_black,
        "production_upstream_gap_decided_before_black_box": 0 <= prod_debt < prod_black,
        "gate_upstream_debt_branch_line": gate_debt,
        "gate_black_box_branch_line": gate_black,
        "gate_upstream_gap_decided_before_black_box": 0 <= gate_debt < gate_black,
        "upstream_gap_outcome": RESULT_FAILED,
        "upstream_gap_error_code": "upstream_gap",
        "black_box_outcome": RESULT_UNVERIFIABLE,
        "black_box_error_code": "real_onlyoffice_not_executed",
        "why": (
            "顺序不可交换：把 upstream_debt 放到 black-box 之后，缺实现的场景在没有 OO 的"
            "环境里会显示成 unverifiable ⇒ 将来接上真实 OO 会把它们**自动刷绿**，而它们"
            "其实永远不会通过"
        ),
    }


def upstream_gap_counterfactual(facts: PilotFacts, environment: Environment) -> dict[str, Any]:
    """反事实：把 `upstream_debt` 清空后同一条 probe 的判定必须**改变**。

    这是「upstream-gap 必须判 failed」的**行为侧**证据（源码位置只是形态侧）。
    """
    import dataclasses

    _ensure_backend_on_path()
    from app.services.workpaper_sync import pilot_harness as ph

    out: dict[str, Any] = {}
    for spec in _SCENARIO_PROBES:
        oracle = ph.SCENARIO_ORACLES.get(str(spec.scenario_id))
        if oracle is None or not oracle.upstream_debt:
            continue
        real = evaluate_probe(
            spec, facts, environment=environment, record=None, supplied_inputs=frozenset()
        )
        naked = dataclasses.replace(oracle, upstream_debt="")
        patched = dict(ph.SCENARIO_ORACLES)
        patched[str(spec.scenario_id)] = naked
        original = ph.SCENARIO_ORACLES
        try:
            ph.SCENARIO_ORACLES = patched  # type: ignore[misc]
            without = evaluate_probe(
                spec, facts, environment=environment, record=None, supplied_inputs=frozenset()
            )
        finally:
            ph.SCENARIO_ORACLES = original  # type: ignore[misc]
        out[spec.probe_id] = {
            "with_debt": {"result": real.result, "error_code": real.error_code},
            "without_debt": {"result": without.result, "error_code": without.error_code},
            "differs": (real.result, real.error_code) != (without.result, without.error_code),
        }
    return out


def gate_probe_ordering() -> tuple[bool, str, dict[str, Any]]:
    facts = ordering_facts()
    ok = bool(
        facts["production_upstream_gap_decided_before_black_box"]
        and facts["gate_upstream_gap_decided_before_black_box"]
    )
    detail = (
        f"生产 oracle: debt@{facts['production_upstream_debt_branch_line']} < "
        f"black-box@{facts['production_black_box_branch_line']}；"
        f"本门: debt@{facts['gate_upstream_debt_branch_line']} < "
        f"black-box@{facts['gate_black_box_branch_line']}"
    )
    return ok, detail, facts


def gate_probe_no_documentary_pass() -> tuple[bool, str, dict[str, Any]]:
    """真跑一次拒绝路径：带 result 的记录必须被 :class:`DocumentaryClaimRejected` 拒。

    🔴 三个样例覆盖三种埋法（顶层 / 嵌套 / 列表内），且必须**全部**被拒 ——
    只测顶层时"深埋一层就绕过"会照绿。
    """
    samples: tuple[tuple[str, Any], ...] = (
        ("top_level", {"result": "passed"}),
        ("nested", {"probes": {"xlsx/x": {"scenario.rollback": {"verdict": "passed"}}}}),
        ("in_list", {"probes": [{"aggregate_result": "verified"}]}),
    )
    observed: dict[str, str] = {}
    for label, payload in samples:
        try:
            assert_records_carry_no_claim(payload, where=label)
            observed[label] = "NOT-REJECTED"
        except DocumentaryClaimRejected as exc:
            observed[label] = f"rejected: {str(exc)[:60]}"
        except Exception as exc:  # noqa: BLE001 - 拒了但不是这一条，同样不算通过
            observed[label] = f"wrong-error: {type(exc).__name__}"
    ok = all(v.startswith("rejected") for v in observed.values())
    clean = {"environment": {}, "probes": {"xlsx/x": {"scenario.rollback": {"a": 1}}}}
    assert_records_carry_no_claim(clean)
    return ok, f"三种埋法逐一实测：{observed}", {"samples": observed, "clean_record_accepted": True}


def gate_probe_admission_is_state_sensitive() -> tuple[bool, str, dict[str, Any]]:
    """🔴 替身实测：把四个 finalize 信号全部翻成「已就绪」后，准入判定必须改变。

    这条 probe 存在的理由是本门最容易犯的错：把 `admitted` 写成 `return False` 并在注释里
    写「今天必然不通过」。那种实现在观测器补上后**不会**变绿，于是 Task 45 之后这道门会
    永久误红且没人知道。替身法证明本门读的是真状态。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync.adapters import registry as registry_module

    class _Definitions:
        identity_binding = object()

    async def _observer(**_kwargs: Any) -> Any:
        return _Definitions()

    observed: dict[str, Any] = {}
    all_flipped = True
    for ref in PILOTS:
        module = load_pilot_module(ref)
        real = probe_finalize_signals(module)
        saved = {
            name: getattr(module, name)
            for name in ("assert_manifest_capability_enabled", "resolve_published_frozen_definitions", "attach_pilot_adapters")
        }
        saved_registry = registry_module.build_production_registry

        async def _attach(_registry: Any, *, session: Any) -> tuple[str, ...]:
            return (str(module.PILOT_ADAPTER_ID),)

        class _Stand:
            def registrations(self) -> tuple[Any, ...]:
                return (type("R", (), {"adapter_id": str(module.PILOT_ADAPTER_ID)})(),)

        try:
            setattr(module, "assert_manifest_capability_enabled", lambda **_k: None)
            setattr(module, "resolve_published_frozen_definitions", _observer)
            setattr(module, "attach_pilot_adapters", _attach)
            registry_module.build_production_registry = lambda: _Stand()  # type: ignore[assignment]
            substituted = probe_finalize_signals(module)
        finally:
            for name, value in saved.items():
                setattr(module, name, value)
            registry_module.build_production_registry = saved_registry  # type: ignore[assignment]
        flipped = real.admitted != substituted.admitted
        all_flipped = all_flipped and flipped
        observed[ref.pilot_class] = {
            "real_admitted": real.admitted,
            "substituted_admitted": substituted.admitted,
            "flipped": flipped,
            "real_observer": real.published_identity_observer,
            "substituted_observer": substituted.published_identity_observer,
        }
    detail = (
        "四个 pilot 的准入判定在替身下全部由 False 翻成 True ⇒ 本门读的是真实状态"
        if all_flipped
        else f"有 pilot 的判定未随信号改变：{observed}"
    )
    return all_flipped, detail, observed


def mutation_coverage_facts() -> tuple[bool, str, dict[str, Any]]:
    """变异检验四态（AC 14.7）：declared==executed 且全部 RED。"""
    coverage_path = _EVIDENCE_DIR / "mutation_coverage.json"
    report_path = _EVIDENCE_DIR / "mutation_report.json"
    if not coverage_path.exists() or not report_path.exists():
        return False, "变异覆盖面/报告尚未落盘 —— 守卫成立性未闭合", {"present": False}
    coverage = json.loads(coverage_path.read_bytes().decode("utf-8"))
    report = json.loads(report_path.read_bytes().decode("utf-8"))
    verdicts: dict[str, int] = {}
    for row in report:
        verdicts[str(row.get("verdict"))] = verdicts.get(str(row.get("verdict")), 0) + 1
    declared = int(coverage.get("declared_count") or 0)
    executed = int(coverage.get("executed_count") or 0)
    all_red = bool(report) and verdicts.get("RED", 0) == len(report)
    ok = declared > 0 and declared == executed and all_red
    return (
        ok,
        f"declared={declared} executed={executed} verdicts={verdicts}",
        {"present": True, "declared_count": declared, "executed_count": executed, "verdicts": verdicts},
    )


def evaluate_gate_probes() -> tuple[list[ProbeRow], dict[str, Any]]:
    """五条门自身的 probe。每条都真跑，没有一条靠声明。"""
    checks: dict[str, Callable[[], tuple[bool, str, dict[str, Any]]]] = {
        "gate.no_documentary_pass": gate_probe_no_documentary_pass,
        "gate.ordering_upstream_gap_before_black_box": gate_probe_ordering,
        "gate.admission_is_state_sensitive": gate_probe_admission_is_state_sensitive,
        "gate.mutation_four_state": mutation_coverage_facts,
    }
    rows: list[ProbeRow] = []
    details: dict[str, Any] = {}
    for spec in GATE_PROBES:
        if spec.probe_id == "gate.blocks_wave5":
            continue  # 由 :func:`build_report` 在汇总后判定（它要看全部 probe）
        ok, detail, payload = checks[spec.probe_id]()
        details[spec.probe_id] = payload
        rows.append(
            ProbeRow(
                spec.probe_id, spec.probe_class, None, None, None, spec.anchor,
                RESULT_PASSED if ok else RESULT_FAILED,
                None if ok else "gate_selfcheck_failed",
                () if ok else ("gate_selfcheck_failed",),
                spec.requirements, spec.properties, (detail,), None,
            )
        )
    return rows, details


# ═══════════════════════════════════════════════════════════════════════════
# 8. 汇总报告 + CLI
# ═══════════════════════════════════════════════════════════════════════════


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def probe_registry_payload() -> dict[str, Any]:
    """probe 注册表的 canonical 投影（落 `backend/data/`，供生成器 --check 复算）。"""
    task_body = read_task_body()
    anchors = assert_probes_anchored_in_task_text(task_body=task_body)
    _assert_scenarios_known()
    properties = design_property_titles()
    requirements = task_requirement_ids(task_body=task_body)
    claimed_reqs = {r for spec in ALL_PROBE_SPECS for r in spec.requirements}
    claimed_props = {p for spec in ALL_PROBE_SPECS for p in spec.properties}
    probes = [
        {
            "probe_id": spec.probe_id,
            "probe_class": spec.probe_class,
            "anchor": spec.anchor,
            "anchor_occurrences_in_task_text": anchors[spec.anchor],
            "scenario_id": spec.scenario_id,
            "requirements": list(spec.requirements),
            "properties": list(spec.properties),
            "evidence_inputs": list(spec.evidence_inputs),
            "production_refs": list(spec.production_refs),
            "has_validator": spec.validator is not None,
            "why": spec.why,
        }
        for spec in ALL_PROBE_SPECS
    ]
    payload: dict[str, Any] = {
        "schema_version": "task44-probe-registry:v1",
        "gate_version": GATE_VERSION,
        "gate_script": "backend/scripts/check/check_task44_oo94_excel_pilot_gate.py",
        "task_number": TASK_NUMBER,
        "task_body_sha256": hashlib.sha256(task_body.encode("utf-8")).hexdigest(),
        "pilots": [
            {"pilot_class": p.pilot_class, "module": p.module_path, "owner_task": p.owner_task}
            for p in PILOTS
        ],
        "per_pilot_probe_count": len(PER_PILOT_PROBES),
        "gate_probe_count": len(GATE_PROBES),
        "total_probe_rows": len(PER_PILOT_PROBES) * len(PILOTS) + len(GATE_PROBES),
        "declared_properties": list(DECLARED_PROPERTIES),
        "property_titles": properties,
        "task_requirements": list(requirements),
        "requirements_without_probe": sorted(set(requirements) - claimed_reqs),
        "properties_without_probe": sorted(set(DECLARED_PROPERTIES) - claimed_props),
        "properties_claimed_but_not_declared": sorted(claimed_props - set(DECLARED_PROPERTIES)),
        "probes": probes,
    }
    payload["registry_digest"] = _digest(
        {k: v for k, v in payload.items() if k != "registry_digest"}
    )
    return payload


def assert_registry_coverage(payload: Mapping[str, Any]) -> None:
    """AC / Property 覆盖必须闭合：任务正文列出的每一条都要有 probe 认领。"""
    problems: list[str] = []
    if payload["requirements_without_probe"]:
        problems.append(
            f"Task 44 的 AC {payload['requirements_without_probe']} 没有任何 probe 认领"
        )
    if payload["properties_without_probe"]:
        problems.append(
            f"Property {payload['properties_without_probe']} 没有任何 probe 认领"
        )
    if payload["properties_claimed_but_not_declared"]:
        problems.append(
            f"probe 认领了未声明的 Property {payload['properties_claimed_but_not_declared']}"
        )
    if problems:
        raise GateStructuralError("probe 注册表覆盖不闭合：\n  " + "\n  ".join(problems))


def build_report(
    *, records: Mapping[str, Any] | None = None, environment: Environment | None = None
) -> dict[str, Any]:
    """跑完整道门并返回可落盘的报告。"""
    registry = probe_registry_payload()
    assert_registry_coverage(registry)
    payload = dict(records or {"environment": {}, "supplied_inputs": {}, "probes": {}})
    env = environment or default_environment()
    if payload.get("environment"):
        sentinel = _not_executed()
        env = Environment(
            onlyoffice_build=str(payload["environment"].get("onlyoffice_build") or sentinel),
            browser_build=str(payload["environment"].get("browser_build") or sentinel),
            source_commit=str(payload["environment"].get("source_commit") or ""),
            runner_version=str(payload["environment"].get("runner_version") or GATE_VERSION),
        )

    rows: list[ProbeRow] = []
    pilots: dict[str, Any] = {}
    for ref in PILOTS:
        facts = collect_pilot_facts(ref)
        denominator = _scenario_denominator_facts(facts)
        if facts.close_required != facts.close_predicate_raw:
            raise GateStructuralError(
                f"pilot {ref.pilot_class}: 生产推导的 close_required="
                f"{facts.close_required} 与直接读 manifest 的谓词="
                f"{facts.close_predicate_raw} 不符 —— 两侧必须同源同结论"
            )
        pilot_records = dict((payload.get("probes") or {}).get(facts.entry_id) or {})
        pilot_inputs = dict((payload.get("supplied_inputs") or {}).get(facts.entry_id) or {})
        pilot_rows: list[ProbeRow] = []
        for spec in PER_PILOT_PROBES:
            record = pilot_records.get(spec.probe_id)
            supplied = frozenset(str(v) for v in (pilot_inputs.get(spec.probe_id) or ()))
            pilot_rows.append(
                evaluate_probe(
                    spec,
                    facts,
                    environment=env,
                    record=record,
                    supplied_inputs=supplied,
                )
            )
        rows.extend(pilot_rows)
        distribution: dict[str, int] = {}
        errors: dict[str, int] = {}
        for row in pilot_rows:
            distribution[row.result] = distribution.get(row.result, 0) + 1
            errors[str(row.error_code)] = errors.get(str(row.error_code), 0) + 1
        oracle_echo: dict[str, int] = {}
        for row in pilot_rows:
            if row.oracle_echo:
                key = f"{row.oracle_echo['result']}/{row.oracle_echo['error_code']}"
                oracle_echo[key] = oracle_echo.get(key, 0) + 1
        pilots[facts.entry_id] = {
            "pilot_class": ref.pilot_class,
            "owner_task": ref.owner_task,
            "adapter_id": facts.adapter_id,
            "status": (
                "verified"
                if all(row.passed for row in pilot_rows)
                else "unverifiable"
            ),
            "finalize_signals": facts.signals.as_dict(),
            "required_scenario_set": {
                "digest": facts.required_digest,
                "size": len(facts.required_scenario_ids),
                "scenario_ids": list(facts.required_scenario_ids),
                **denominator,
            },
            "close_predicate": {
                "editability": facts.editability,
                "capability": facts.capability,
                "room_model": facts.room_model,
                "close_required_derived": facts.close_required,
                "close_predicate_raw": facts.close_predicate_raw,
            },
            "digests": {
                "authority_model_definition": facts.authority_model_definition_sha256,
                "template_definition": facts.template_definition_sha256,
                "instrumentation_definition": facts.instrumentation_definition_sha256,
                "contract_canonical": facts.contract_canonical_sha256,
                "bundle": facts.bundle_sha256,
                "authority_model": facts.authority_model,
            },
            "result_distribution": distribution,
            "error_code_distribution": errors,
            "production_oracle_echo_distribution": oracle_echo,
            "upstream_gap_counterfactual": upstream_gap_counterfactual(facts, env),
            "registered_upstream_debts": sorted(facts.registered_debts),
            "blocking_reasons": sorted(
                {
                    condition
                    for row in pilot_rows
                    for condition in row.blocking_conditions
                }
            ),
        }

    gate_rows, gate_details = evaluate_gate_probes()
    rows.extend(gate_rows)

    # `gate.blocks_wave5`：本门在有 probe 未通过时**必须**非零退出。它要看全部 probe，
    # 所以只能在这里判 —— 且判据是"退出码会不会非零"，不是一句声明。
    unpassed = [row for row in rows if not row.passed]
    blocks = bool(unpassed) and _exit_code_for(rows, structural_error=None) != 0
    spec = next(s for s in GATE_PROBES if s.probe_id == "gate.blocks_wave5")
    rows.append(
        ProbeRow(
            spec.probe_id, spec.probe_class, None, None, None, spec.anchor,
            RESULT_PASSED if blocks else RESULT_FAILED,
            None if blocks else "gate_selfcheck_failed",
            () if blocks else ("gate_selfcheck_failed",),
            spec.requirements, spec.properties,
            (
                f"{len(unpassed)} 条 probe 未通过 ⇒ 退出码 "
                f"{_exit_code_for(rows, structural_error=None)}（阻断 Wave 5）",
            ),
            None,
        )
    )

    distribution: dict[str, int] = {}
    errors: dict[str, int] = {}
    for row in rows:
        distribution[row.result] = distribution.get(row.result, 0) + 1
        errors[str(row.error_code)] = errors.get(str(row.error_code), 0) + 1
    conditions: dict[str, int] = {}
    for row in rows:
        for condition in row.blocking_conditions:
            conditions[condition] = conditions.get(condition, 0) + 1

    properties: dict[str, Any] = {}
    for prop in DECLARED_PROPERTIES:
        landing = [row for row in rows if prop in row.properties]
        results = {row.result for row in landing}
        properties[prop] = {
            "title": registry["property_titles"][prop],
            "probe_rows": len(landing),
            "distinct_probe_ids": sorted({row.probe_id for row in landing}),
            "verdict": (
                RESULT_PASSED
                if results == {RESULT_PASSED}
                else RESULT_FAILED
                if RESULT_FAILED in results
                else RESULT_UNVERIFIABLE
            ),
            "result_distribution": {r: sum(1 for x in landing if x.result == r) for r in sorted(results)},
        }

    return {
        "gate_version": GATE_VERSION,
        "environment": env.as_dict(),
        "registry": {
            "registry_digest": registry["registry_digest"],
            "task_body_sha256": registry["task_body_sha256"],
            "per_pilot_probe_count": registry["per_pilot_probe_count"],
            "gate_probe_count": registry["gate_probe_count"],
            "total_probe_rows": registry["total_probe_rows"],
            "task_requirements": registry["task_requirements"],
        },
        "ordering": ordering_facts(),
        "gate_selfcheck_details": gate_details,
        "pilots": pilots,
        "properties": properties,
        "probe_rows": [row.as_dict() for row in rows],
        "result_distribution": distribution,
        "error_code_distribution": errors,
        "blocking_condition_distribution": conditions,
        "verified_pilot_classes": sorted(
            data["pilot_class"] for data in pilots.values() if data["status"] == "verified"
        ),
        "all_pilots_verified": bool(pilots) and all(
            data["status"] == "verified" for data in pilots.values()
        ),
        "unpassed_probe_count": len(unpassed),
    }


def _exit_code_for(rows: Sequence[ProbeRow], *, structural_error: str | None) -> int:
    """退出码：2 = 门自身失效；1 = 阻断 Wave 5；0 = 四类全 verified。"""
    if structural_error:
        return 2
    return 0 if all(row.passed for row in rows) else 1


def _print_report(report: Mapping[str, Any]) -> None:
    print(f"Task 44 gate（{report['gate_version']}）")
    env = report["environment"]
    print(
        f"  环境：onlyoffice_build={env['onlyoffice_build']} "
        f"browser_build={env['browser_build']}"
    )
    reg = report["registry"]
    print(
        f"  probe 分母：{reg['per_pilot_probe_count']}/pilot × {len(PILOTS)} + "
        f"{reg['gate_probe_count']} gate = {reg['total_probe_rows']} 行"
        f"（registry_digest={reg['registry_digest'][:12]}）"
    )
    print(f"  判定分布：{report['result_distribution']}")
    print(f"  error_code：{report['error_code_distribution']}")
    print(f"  阻断条件计数：{report['blocking_condition_distribution']}")
    print()
    for entry_id, data in sorted(report["pilots"].items()):
        signals = data["finalize_signals"]
        print(
            f"  [{data['status'].upper():<13}] {data['pilot_class']:<21} {entry_id}"
            f"  (Task {data['owner_task']})"
        )
        print(
            f"       finalize：capability_enabled={signals['capability_enabled']} "
            f"adapter_registered={signals['adapter_registered']} "
            f"observer={signals['published_identity_observer']} "
            f"attach={signals['attach_without_representation'] or '()'}"
        )
        print(
            f"       required set：{data['required_scenario_set']['size']} 条 / "
            f"digest={data['required_scenario_set']['digest'][:12]} / "
            f"bundle={data['digests']['bundle'][:12]}"
        )
        print(f"       判定：{data['result_distribution']}  error：{data['error_code_distribution']}")
        print(f"       阻断：{data['blocking_reasons']}")
    print()
    print("  Property 验证结论：")
    for prop, data in report["properties"].items():
        print(
            f"    {prop:<4} {data['verdict']:<13} {data['probe_rows']:>3} 行  "
            f"{data['result_distribution']}"
        )
    print()
    for row in report["probe_rows"]:
        if row["probe_class"] == "gate":
            flag = "OK " if row["result"] == RESULT_PASSED else "!! "
            print(f"  {flag}{row['probe_id']:<48} {row['result']:<13} {row['notes'][0][:96]}")
    print()
    print(
        f"  未通过 probe：{report['unpassed_probe_count']} / {len(report['probe_rows'])}"
        f"；verified pilot 类：{report['verified_pilot_classes'] or '无'}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execution-records",
        metavar="PATH",
        help="真实 pilot 执行记录（JSON）。不给即视为未执行，全部 probe 保持 UNVERIFIABLE",
    )
    parser.add_argument("--json", metavar="PATH", help="报告落盘路径")
    parser.add_argument(
        "--print-registry", action="store_true", help="只打印 probe 注册表的 canonical 投影"
    )
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - 老 Python 无 reconfigure
            pass

    try:
        if args.print_registry:
            payload = probe_registry_payload()
            assert_registry_coverage(payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        records = load_execution_records(
            Path(args.execution_records) if args.execution_records else None
        )
        report = build_report(records=records)
    except GateStructuralError as exc:
        print(f"[FATAL] 门自身失效：{exc}")
        return 2
    except Exception as exc:  # noqa: BLE001 - 任何未预期错误都必须 fail closed
        print(f"[FATAL] {type(exc).__name__}: {exc}")
        return 2

    _print_report(report)
    if args.json:
        Path(args.json).write_bytes(
            (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )
        )
        print(f"  报告已落盘：{args.json}")

    if report["all_pilots_verified"]:
        print("[OK] 四类 Excel pilot 全部 verified")
        return 0
    print("[BLOCKED] 真实 OnlyOffice 9.4 Excel pilot gate 未通过 —— Wave 5 阻断。逐条原因：")
    for entry_id, data in sorted(report["pilots"].items()):
        print(
            f"  · {data['pilot_class']} ({entry_id}, Task {data['owner_task']})："
            f"{data['status']}；阻断条件 {data['blocking_reasons']}"
        )
        signals = data["finalize_signals"]
        if not signals["admitted"]:
            print(
                f"      finalize 未完成 ⇒ 该 entry 不进入测试范围："
                f"observer={signals['published_identity_observer']} "
                f"capability_enabled={signals['capability_enabled']} "
                f"adapter_registered={signals['adapter_registered']}"
            )
            # 🔴 Task 75 起「为什么 finalize 不成」不再是观测器缺失（已交付），而是**供给**：
            #    把那一条 upstream_gap 的 debt 文本直接打出来，否则阻断输出只剩「观测器拿
            #    None 去问当然抛」这种无用诊断（原实现打的正是 observer_detail）。
            gap = next(
                (
                    row["notes"][-1]
                    for row in report["probe_rows"]
                    if row["entry_id"] == entry_id
                    and row["error_code"] == "upstream_gap"
                    and "finalize_blocked" in row["blocking_conditions"]
                    and row["notes"]
                ),
                "",
            )
            if gap:
                print(f"      finalize 阻断原因：{gap[:220]}")
    for row in report["probe_rows"]:
        if row["probe_class"] == "gate" and row["result"] != RESULT_PASSED:
            print(f"  · 门自身的 {row['probe_id']} 未通过：{row['notes'][0][:200]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
