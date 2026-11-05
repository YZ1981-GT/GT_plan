# -*- coding: utf-8 -*-
"""任务 70 门禁的「环境与路径解析」三件 —— 从门禁主文件拆出来的。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 6.3 修复

拆分理由：门禁主文件在白名单基线 3126 行，补完下面三处修复后 3317 行、超过 +5% 上限。
按仓库口径**拆模块而不是抬白名单**。这三件自成一体（都只回答「本环境/本仓库的事实是
什么」，不参与任何 scenario 判定），放一起不会把两类关注点搅在一起。

三处修复各自的根因：

1. :data:`PENDING_CAPABILITY_BUCKET` / :func:`capability_bucket`
   门禁用 `capability_of`（pending 一律抛）去统计**含未裁决 entry** 的能力分布 ⇒
   自 task 1.1 引入 pending 态起整门崩在第一条 pending entry 上，报告根本生成不出来。
   生产函数的文档写得很清楚：只问「是否已启用某能力」时用 `effective_capability`。

2. :func:`spec_doc`
   本 spec 目录换过代。任务 70 的正文在 `_archive/17-…/<spec>/tasks.md`，活跃目录里
   已重编号成 0.x~7.x、一条 `- [x] 70.` 都没有。路径写死活跃目录 ⇒ `task_body()` 抛
   「tasks.md 里找不到任务 70」。design.md 同理（活跃那份没有 `### Property 20`）。
   所以择路要按**内容**而不是存在性 —— 两代文件都存在。

3. :func:`artifact_environment`
   `storage/` 与 `backend/storage/` 都在 .gitignore 里，真实项目的 `.versions/**`
   **从不入库**。于是干净检出 / CI / 临时 worktree 里 provider 侧必然以
   `artifact_publish_failed` 整批失败、`registered` 被系统性压到 0 —— 那是**环境事实**，
   不是供给事实。实测同一份代码同一个库：无 storage 的 worktree registered **0** /
   artifact_publish_failed **59**；主工作树 registered **32** / 真实漂移 **27**
   （16 published_identity_observed_drift + 11 sync_contract_structure_drift）。
   不区分的话「registered=0」会被读成「没有一条 entry 具备供给」。

🔴 三件都**不放宽任何准入判据**：`resolve_published_artifact` 对「指针指向缺失文件」
继续可见地报错（生产上那是真的半成功态），`effective_capability` 对不带 pending 标记的
`capability=null` 继续抛。这里只负责把事实如实分型。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final, Mapping

#: 未裁决 entry 在能力分布里的桶名（不是 `Capability` 的成员 —— 封闭四态里没有它）。
PENDING_CAPABILITY_BUCKET: Final[str] = "pending"


class SpecDocNotFoundError(RuntimeError):
    """按内容择路也找不到 spec 文档 —— 候选路径逐条列出，便于定位是哪一代。"""


def capability_bucket(entry_profile: Any, entry: Mapping[str, Any]) -> str:
    """能力分布的桶名：已裁决取封闭四态的值，未裁决归 ``pending``。

    必须用 `effective_capability`（pending → ``None``）而不是 `capability_of`
    （pending 一律抛）。现算：197 条 entry 里 86 条 pending。
    """
    capability = entry_profile.effective_capability(entry)
    if capability is None:
        return PENDING_CAPABILITY_BUCKET
    return str(capability.value)


def spec_doc(
    repo: Path, spec: str, name: str, *, must_contain: str | None = None
) -> Path:
    """spec 文档路径：活跃目录优先，``_archive/*/<spec>/`` 兜底。

    ``must_contain`` 给定时按「要找的内容真的在这份文件里」择路（正则，`re.M`）。
    只看文件存在性会继续选中活跃目录那份 —— 两代 tasks.md 都存在。
    """
    specs = repo / ".kiro/specs"
    candidates = [specs / spec / name]
    candidates += sorted(specs.glob(f"_archive/*/{spec}/{name}"))
    for path in candidates:
        if not path.is_file():
            continue
        if must_contain is None:
            return path
        try:
            if re.search(must_contain, path.read_text(encoding="utf-8"), re.M):
                return path
        except OSError:
            continue
    raise SpecDocNotFoundError(
        f"找不到含 {must_contain!r} 的 {name}；候选："
        + " / ".join(str(p) for p in candidates)
    )


def artifact_environment(
    backend_root: Path, failures: Mapping[str, Any]
) -> dict[str, Any]:
    """本环境能否解析 published artifact —— 读注册数字之前必须先知道的事。

    只做可复算的三件事：storage 根在不在、本轮有多少条 entry 因
    ``artifact_publish_failed`` 而失败、点名前若干条。不改任何准入判据。
    """
    storage_root = backend_root / "storage"
    publish_failed = sorted(
        entry_id
        for entry_id, fail in failures.items()
        if str(getattr(fail, "error_code", "") or "") == "artifact_publish_failed"
    )
    info: dict[str, Any] = {
        "backend_root": str(backend_root),
        "storage_root": str(storage_root),
        "storage_root_exists": storage_root.is_dir(),
        "storage_is_gitignored": True,
        "project_dirs": 0,
        "artifact_publish_failed_count": len(publish_failed),
        "artifact_publish_failed_entries": publish_failed[:12],
        "why": (
            "storage 不入库 ⇒ 干净检出 / CI / 临时 worktree 里 published artifact 恒不可解析；"
            "此时 registered 数字只反映环境，不反映供给"
        ),
    }
    if storage_root.is_dir():
        info["project_dirs"] = sum(1 for child in storage_root.iterdir() if child.is_dir())
    return info


def measurement_is_environment_limited(artifact_env: Mapping[str, Any]) -> bool:
    """注册数字是否只反映环境。

    🔴 两个触发条件都要：storage 根**不存在**，或者根在但本轮真有
    ``artifact_publish_failed``。只看根是否存在会漏掉「目录在、里面是空的」——
    临时 worktree 实测就是这种（`storage_root_exists=True` 而 `project_dirs=0`，
    59 条 entry 全失败）。
    """
    return (
        not bool(artifact_env.get("storage_root_exists"))
        or int(artifact_env.get("artifact_publish_failed_count") or 0) > 0
    )
