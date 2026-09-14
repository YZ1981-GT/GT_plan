# -*- coding: utf-8 -*-
"""容量 profile：**只登记，不宣称通过**。执行归 Task 71。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 39
Requirements: 14.10, 14.12
Properties: **P72**

═══ 本模块存在的唯一理由 ═══

Task 39 正文最后一句：「容量 profile **仅登记**待 Task 71 执行，**不宣称真实 OO
probe/pilot 已通过**」。于是这里要解决的是一个很具体的作假风险：把 AC 14.10 的四个
数字写进某份文档，然后在收口计数里把容量门算成"已定义"甚至"已满足"。

对策是把「登记」与「已执行」做成**两个不可互换的状态**，并让后者**只能**由一份带环境
指纹的执行记录构造：

* :data:`CAPACITY_PROFILE` 是登记态，`status` 恒为
  :attr:`CapacityStatus.registered_pending_execution`；
* 想得到"通过"必须调用 :func:`evaluate_capacity_run` 并交出真实测得的四个数与预算；
* 直接问「过了吗」而没有执行记录时，:func:`assert_capacity_verified` 抛
  :class:`CapacityNotExecutedError` —— 不是返回 False。抛异常与返回 False 的差别在于：
  后者会被 `if not verified: pass` 静静吞掉。

═══ Property 72 的可重复性 ═══

「结果记录环境并满足预算或产生显式 capacity ADR」。可重复 = 同样的输入必须得到同样的
digest，因此 :meth:`CapacityProfile.digest` 是 canonical digest，且**四个负载数字与两条
延迟预算全部参与**。守卫把这些数字与 `requirements.md` 的 AC 14.10 / 14.12 原文交叉锁死
（:func:`requirement_facts`），因此"把数字改成一个更容易达到的值"必然打红 ——
这一条正是本 spec 反复强调的「绝不用被测函数算期望值」的反面：期望值来自需求原文。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.models import SyncDomainError

#: `requirements.md` 的位置（AC 14.10 / 14.12 的真源）。
REQUIREMENTS_PATH: Final[Path] = (
    Path(__file__).resolve().parents[4]
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "requirements.md"
)


class CapacityError(SyncDomainError):
    error_code = "sync_capacity_profile_invalid"


class CapacityNotExecutedError(CapacityError):
    """有人问"容量门过了吗"但没有执行记录。

    🔴 抛而不是返回 False：返回值会被 `if not ok: pass` 静静吞掉，异常不会。
    """

    error_code = "sync_capacity_not_executed"


class CapacityStatus(str, Enum):
    """容量门的三态。**登记 ≠ 已执行 ≠ 已通过**。"""

    #: 已登记负载与预算，等待 Task 71 在真实环境执行。**当前状态**。
    registered_pending_execution = "registered_pending_execution"
    #: 已执行且满足预算。
    executed_within_budget = "executed_within_budget"
    #: 已执行但未达标 —— 必须有显式 capacity ADR，不得静默放宽（AC 14.12）。
    executed_requires_adr = "executed_requires_adr"


@dataclass(frozen=True)
class CapacityProfile:
    """AC 14.10 的并发容量门 + AC 14.12 的延迟预算。"""

    concurrent_login_sessions: int
    active_onlyoffice_participants: int
    same_second_forcesave_burst: int
    sustained_applications_per_second: int
    sustained_duration_seconds: int
    incoming_durable_p95_seconds: int
    applied_terminal_p95_seconds: int
    #: 同 wp 串行、跨 wp 并行，且不得依赖单进程锁（AC 14.10 末句）。
    same_wp_serialized: bool
    cross_wp_parallel: bool
    forbids_single_process_lock: bool
    execution_owner: str
    status: CapacityStatus

    @property
    def digest(self) -> str:
        """canonical digest —— Property 72 的「可重复」判据。"""
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "concurrent_login_sessions": self.concurrent_login_sessions,
            "active_onlyoffice_participants": self.active_onlyoffice_participants,
            "same_second_forcesave_burst": self.same_second_forcesave_burst,
            "sustained_applications_per_second": self.sustained_applications_per_second,
            "sustained_duration_seconds": self.sustained_duration_seconds,
            "incoming_durable_p95_seconds": self.incoming_durable_p95_seconds,
            "applied_terminal_p95_seconds": self.applied_terminal_p95_seconds,
            "same_wp_serialized": self.same_wp_serialized,
            "cross_wp_parallel": self.cross_wp_parallel,
            "forbids_single_process_lock": self.forbids_single_process_lock,
            "execution_owner": self.execution_owner,
            "status": self.status.value,
        }


#: 🔴 **登记态**。`status` 写死为 `registered_pending_execution`，`execution_owner` 指名
#: Task 71 —— Task 39 建的是 harness，容量执行不在本任务范围内（正文原话）。
CAPACITY_PROFILE: Final[CapacityProfile] = CapacityProfile(
    concurrent_login_sessions=6000,
    active_onlyoffice_participants=1200,
    same_second_forcesave_burst=120,
    sustained_applications_per_second=20,
    sustained_duration_seconds=600,
    incoming_durable_p95_seconds=10,
    applied_terminal_p95_seconds=30,
    same_wp_serialized=True,
    cross_wp_parallel=True,
    forbids_single_process_lock=True,
    execution_owner="Task 71",
    status=CapacityStatus.registered_pending_execution,
)


@dataclass(frozen=True)
class CapacityMeasurement:
    """一次**真实**容量执行的实测值 + 环境指纹。

    每个字段都必填：AC 14.12 要求"记录硬件/OO build/载荷"，缺环境的实测数在
    Property 72 的"可重复"意义下等于没测。
    """

    concurrent_login_sessions: int
    active_onlyoffice_participants: int
    same_second_forcesave_burst: int
    sustained_applications_per_second: int
    sustained_duration_seconds: int
    incoming_durable_p95_seconds: float
    applied_terminal_p95_seconds: float
    hardware_profile: str
    onlyoffice_build: str
    source_commit: str
    #: 未达标时必须给出的显式 ADR 引用（AC 14.12「不得静默放宽」）。
    capacity_adr_ref: str | None = None

    def assert_environment_recorded(self) -> None:
        missing = [
            name
            for name in ("hardware_profile", "onlyoffice_build", "source_commit")
            if not str(getattr(self, name) or "").strip()
        ]
        if missing:
            raise CapacityError(
                f"容量实测缺环境记录 {missing} —— AC 14.12 要求记录硬件/OO build/载荷，"
                "否则结果不可重复（Property 72）"
            )


@dataclass(frozen=True)
class CapacityOutcome:
    """一次容量评估的结论。`status` 由实测与预算**推导**。"""

    profile: CapacityProfile
    measurement: CapacityMeasurement
    shortfalls: tuple[str, ...]

    @property
    def status(self) -> CapacityStatus:
        if not self.shortfalls:
            return CapacityStatus.executed_within_budget
        return CapacityStatus.executed_requires_adr

    @property
    def within_budget(self) -> bool:
        return self.status is CapacityStatus.executed_within_budget

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_digest": self.profile.digest,
            "status": self.status.value,
            "shortfalls": list(self.shortfalls),
            "measurement": {
                "concurrent_login_sessions": self.measurement.concurrent_login_sessions,
                "active_onlyoffice_participants": (
                    self.measurement.active_onlyoffice_participants
                ),
                "same_second_forcesave_burst": self.measurement.same_second_forcesave_burst,
                "sustained_applications_per_second": (
                    self.measurement.sustained_applications_per_second
                ),
                "sustained_duration_seconds": self.measurement.sustained_duration_seconds,
                "incoming_durable_p95_seconds": (
                    self.measurement.incoming_durable_p95_seconds
                ),
                "applied_terminal_p95_seconds": (
                    self.measurement.applied_terminal_p95_seconds
                ),
                "hardware_profile": self.measurement.hardware_profile,
                "onlyoffice_build": self.measurement.onlyoffice_build,
                "source_commit": self.measurement.source_commit,
                "capacity_adr_ref": self.measurement.capacity_adr_ref,
            },
        }


def evaluate_capacity_run(
    measurement: CapacityMeasurement, *, profile: CapacityProfile = CAPACITY_PROFILE
) -> CapacityOutcome:
    """把实测值与登记预算比对，推导 status。

    四条负载判据（实测**不得低于**登记目标）与两条延迟判据（实测**不得高于**预算）逐条
    独立成一条 shortfall 文案 —— 合成一条会让"到底哪一项没达标"消失，那正是 capacity
    ADR 需要写清楚的东西。
    """
    measurement.assert_environment_recorded()
    shortfalls: list[str] = []
    for name, target in (
        ("concurrent_login_sessions", profile.concurrent_login_sessions),
        ("active_onlyoffice_participants", profile.active_onlyoffice_participants),
        ("same_second_forcesave_burst", profile.same_second_forcesave_burst),
        ("sustained_applications_per_second", profile.sustained_applications_per_second),
        ("sustained_duration_seconds", profile.sustained_duration_seconds),
    ):
        got = getattr(measurement, name)
        if got < target:
            shortfalls.append(f"{name}: 实测 {got} < 目标 {target}")
    for name, budget in (
        ("incoming_durable_p95_seconds", profile.incoming_durable_p95_seconds),
        ("applied_terminal_p95_seconds", profile.applied_terminal_p95_seconds),
    ):
        got = getattr(measurement, name)
        if got > budget:
            shortfalls.append(f"{name}: 实测 p95 {got}s > 预算 {budget}s")
    if shortfalls and not (measurement.capacity_adr_ref or "").strip():
        raise CapacityError(
            f"容量未达标（{shortfalls}）但没有显式 capacity ADR —— AC 14.12 明令"
            "「不得静默放宽」；先写 ADR 记录硬件/OO build/载荷再调整预算"
        )
    return CapacityOutcome(
        profile=profile, measurement=measurement, shortfalls=tuple(shortfalls)
    )


def assert_capacity_verified(outcome: CapacityOutcome | None) -> CapacityOutcome:
    """容量门是否可以计入"已通过"。没有执行记录时**抛**。"""
    if outcome is None:
        raise CapacityNotExecutedError(
            f"容量 profile 当前状态 {CAPACITY_PROFILE.status.value}，"
            f"执行 owner 是 {CAPACITY_PROFILE.execution_owner} —— "
            "Task 39 只登记负载与预算，不得宣称容量门或真实 OO pilot 已通过"
        )
    if not outcome.within_budget:
        raise CapacityError(
            f"容量已执行但未达标：{list(outcome.shortfalls)}（ADR "
            f"{outcome.measurement.capacity_adr_ref}）—— 不计入已通过"
        )
    return outcome


# ═══════════════════════════════════════════════════════════════════════════
# 需求原文交叉锁
# ═══════════════════════════════════════════════════════════════════════════

#: AC 14.10 / 14.12 的抠数正则。**期望值来自需求原文**，不是从被测常量抄一遍。
_AC_PATTERNS: Final[Mapping[str, tuple[str, str]]] = {
    "concurrent_login_sessions": ("14.10", r"(\d+)\s*个并发登录会话"),
    "active_onlyoffice_participants": ("14.10", r"(\d+)\s*个\s*active\s*OO\s*participant"),
    "same_second_forcesave_burst": ("14.10", r"(\d+)\s*个同秒\s*forcesave\s*burst"),
    "sustained_applications_per_second": ("14.10", r"持续\s*(\d+)\s*callback\s*applications/s"),
    "sustained_duration_seconds": ("14.10", r"（(\d+)\s*分钟）"),
    "incoming_durable_p95_seconds": ("14.12", r"incoming\s*durable\s*p95\s*≤\s*(\d+)s"),
    "applied_terminal_p95_seconds": ("14.12", r"applied\s*terminal\s*p95\s*≤\s*(\d+)s"),
}


def _ac_text(body: str, ac: str) -> str:
    match = re.search(rf"^{re.escape(ac)}\.\s(.+?)(?=^\d+\.\d+\.\s|\Z)", body, re.M | re.S)
    if match is None:
        raise CapacityError(
            f"requirements.md 里找不到 AC {ac} —— 容量 profile 的真源不可读，fail closed"
        )
    return match.group(1)


def requirement_facts(path: Path | None = None) -> dict[str, int]:
    """从 `requirements.md` 的 AC 14.10 / 14.12 原文抠出容量数字。

    `sustained_duration_seconds` 在原文里是"10 分钟"，这里换算成秒 —— 换算是本函数
    **唯一**的加工，其余全部逐字取。
    """
    target = path or REQUIREMENTS_PATH
    try:
        body = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise CapacityError(f"读不到需求原文 {target}: {exc}") from exc
    facts: dict[str, int] = {}
    for name, (ac, pattern) in _AC_PATTERNS.items():
        text = _ac_text(body, ac)
        match = re.search(pattern, text)
        if match is None:
            raise CapacityError(
                f"AC {ac} 原文里抠不到 {name}（正则 {pattern!r}）—— "
                "需求措辞变了就必须同步改这里，而不是让锁默默失效"
            )
        value = int(match.group(1))
        facts[name] = value * 60 if name == "sustained_duration_seconds" else value
    return facts


def assert_profile_matches_requirements(
    *, profile: CapacityProfile = CAPACITY_PROFILE, path: Path | None = None
) -> None:
    """登记的 profile 必须与需求原文逐字段相等。"""
    facts = requirement_facts(path)
    drift = {
        name: (getattr(profile, name), want)
        for name, want in facts.items()
        if getattr(profile, name) != want
    }
    if drift:
        raise CapacityError(
            f"容量 profile 与需求原文不符：{drift}（左=登记值，右=AC 原文）—— "
            "把目标改小或把预算放宽必须先改需求并写 ADR"
        )


__all__ = [
    "CAPACITY_PROFILE",
    "REQUIREMENTS_PATH",
    "CapacityError",
    "CapacityMeasurement",
    "CapacityNotExecutedError",
    "CapacityOutcome",
    "CapacityProfile",
    "CapacityStatus",
    "assert_capacity_verified",
    "assert_profile_matches_requirements",
    "evaluate_capacity_run",
    "requirement_facts",
]
