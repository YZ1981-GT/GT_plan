"""候选实例启动门禁的薄适配层。

候选模式与共享后端共用 PG/Redis，启动任务和 worker 必须由
`candidate_identity.CANDIDATE_MODE_POLICY` 统一裁决。
"""
from __future__ import annotations

from typing import Any, Callable

from app.core import candidate_identity

CandidateIdentityError = candidate_identity.CandidateIdentityError


def verify_tree_identity() -> None:
    """在任何迁移或 worker 之前核对候选树身份。"""
    candidate_identity.verify_candidate_identity()


def skip_reason(task_name: str) -> str | None:
    """返回候选模式任务的跳过原因；未登记任务直接抛出安全错误。"""
    return candidate_identity.candidate_skip_reason(task_name)


def apply_policy(
    spec: Any,
    results: list[Any],
    report: bool,
    set_report: Callable[[list[Any]], None],
    result_type: Callable[..., Any],
    redact: Callable[[str], str],
) -> bool:
    """应用候选策略并记录 skipped/未登记失败；返回是否跳过任务。"""
    try:
        reason = skip_reason(spec.name)
    except CandidateIdentityError:
        results.append(result_type(
            spec.name, spec.phase, "failed", 0,
            f"candidate_mode: unregistered task {spec.name!r}"))
        if report:
            set_report(results)
        raise
    if reason:
        results.append(result_type(
            spec.name, spec.phase, "skipped", 0, redact(reason)))
        if report:
            set_report(results)
        return True
    return False
