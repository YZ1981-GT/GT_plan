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


async def recorded_evidence(session: Any) -> dict[str, Any]:
    """库里**真实存在**的 (entry_id, scenario_id) 通过证据 —— `TIER_EXECUTED` 的前置。

    只认 `result='passed'` 的 `working_paper_entry_evidence_scenario` 行，并经 `run_id`
    回到 `working_paper_sync_test_run` 取 `entry_id`（证据表自己没有 entry 列）。
    现算为 0 行时 `passed_pairs` 是空集 ⇒ 没有任何场景可以被记成「已执行」。

    🔴 为什么需要这一项：`classify_scenario_execution` 只按 schema / 上游 / 黑盒 /
    application 链 / recovery 五层逐层排除，排不掉就落 `executed_end_to_end` ——
    **全程不查证据**。而该档位自己声明的语义是「本轮端到端真跑并有可重算证据」。
    2026-11-05 实测：给工作树补上 storage 副本、注入 OO 密钥、3030 又在监听之后，
    黑盒与链路两层同时解除，**1206/1608 行瞬间变「已执行」**，而证据两表都是 0 行 ——
    正是门禁文件头点名要防的「接了 OO 就自动变绿」。
    """
    import sqlalchemy as sa

    runs = (
        await session.execute(sa.text("select count(*) from working_paper_sync_test_run"))
    ).scalar_one()
    scenarios = (
        await session.execute(
            sa.text("select count(*) from working_paper_entry_evidence_scenario")
        )
    ).scalar_one()
    pairs = (
        await session.execute(
            sa.text(
                "select r.entry_id, s.scenario_id"
                " from working_paper_entry_evidence_scenario s"
                " join working_paper_sync_test_run r on r.id = s.run_id"
                " where s.result = 'passed'"
            )
        )
    ).all()
    return {
        "test_run_rows": int(runs or 0),
        "evidence_scenario_rows": int(scenarios or 0),
        "passed_pairs": [(str(row[0]), str(row[1])) for row in pairs],
    }


def close_predicate_arm(prod: Mapping[str, Any]) -> dict[str, Any]:
    """A5 的实测：把 `or` 换成 `and` 会少掉多少 entry 的 close 族。

    从门禁主文件搬来（行数门）。`prod` 由调用方传入门自己的 `_production()`，
    本模块不自己去 import 生产模块 —— 生产真源只能有一个访问器。
    """
    evidence = prod["evidence"]
    entry_profile = prod["entry_profile"]
    Capability = entry_profile.Capability
    RoomModel = evidence.RoomModel

    manifest = entry_profile.load_entry_manifest()
    entries = entry_profile.manifest_entries_by_id(manifest)
    real_hits = 0
    and_hits = 0
    pending = 0
    # 🔴 区分力全靠「editable ∧ shared ∧ ¬bidirectional」这一类 entry：该类为空时两个
    #    谓词在现有数据上不可区分 ⇒ 本臂**不可观测**（不是「谓词等价」）。
    distinguishing = 0
    for entry in entries.values():
        try:
            profile = evidence.extract_entry_profile(entry)
            capability = entry_profile.effective_capability(entry)
        except Exception:  # noqa: BLE001
            continue
        if capability is None:
            pending += 1
            continue
        if evidence.close_scenarios_required(profile=profile, capability=capability):
            real_hits += 1
        if profile.editable and (
            capability is Capability.bidirectional and profile.room_model is RoomModel.shared
        ):
            and_hits += 1
        if (
            profile.editable
            and profile.room_model is RoomModel.shared
            and capability is not Capability.bidirectional
        ):
            distinguishing += 1
    return {
        "production_or_predicate_hits": real_hits,
        "mutated_and_predicate_hits": and_hits,
        "pending_entries_excluded": pending,
        "distinguishing_entries": distinguishing,
        "difference_observable_today": real_hits > and_hits,
        "why_not_observable": (
            f"区分类（editable ∧ shared ∧ ¬bidirectional）现算 {distinguishing} 条，"
            f"排除的未裁决 entry {pending} 条；该类为空时两谓词命中数相同 ⇒ 本臂**不可观测**"
        ),
        "entries_that_would_silently_lose_close_family": real_hits - and_hits,
        "close_scenarios_per_entry": len(evidence.CLOSE_SCENARIOS),
        "scenario_slots_that_would_vanish": (real_hits - and_hits) * len(evidence.CLOSE_SCENARIOS),
    }


def oo_probe_prerequisites_of(settings: Any) -> dict[str, Any]:
    """真调 OO 的前置条件 —— **单一来源**，守卫可查询，谁都不替谁降级。

    为什么要单独一个函数：`ci.yml` 的 `backend-tests` job 跑全量
    ``pytest backend/tests/ -x`` 且**没有 OnlyOffice 容器**，于是
    `probe_real_onlyoffice()` 一抛，三条守卫在 CI 里恒红并把整个 job 截断。恒红的门禁
    没人看 ⇒ 等于没有门禁（与 `--write` + ``git diff`` 那类永假门禁同形）。

    处置**不是**放宽探测：无密钥仍然拒绝探测（契约 ``command_service.jwt.required=true``，
    降级成不鉴权探测会把「OO 不可用」和「我们没带密钥」混成同一个结论）。处置是把「前置
    条件满足与否」变成**可查询的事实**，让守卫走两条臂：具备条件时断言真实观测，不具备时
    断言「门真的拒绝了且点名缺哪一项」。两条臂都真跑、都不 skip —— skip 会让它静静地永不运行。

    `jwt_secret` 原样带出供调用方使用；它是 dev 容器密钥，**不进报告**（报告里只有
    `jwt_signed_by` 这类不含密钥的事实）。
    """
    oo_url = str(getattr(settings, "ONLYOFFICE_URL", "") or "").strip()
    secret = str(getattr(settings, "ONLYOFFICE_JWT_SECRET", "") or "")
    missing: list[str] = []
    if not oo_url:
        missing.append("ONLYOFFICE_URL")
    if not secret:
        missing.append("ONLYOFFICE_JWT_SECRET")
    why = ""
    if "ONLYOFFICE_URL" in missing:
        why = "ONLYOFFICE_URL 为空 —— 本门必须真调 OO，不得回退到「由 payload 决定 host」"
    elif "ONLYOFFICE_JWT_SECRET" in missing:
        why = (
            "ONLYOFFICE_JWT_SECRET 缺失 —— 契约 `command_service.jwt.required=true`，"
            "不得在无密钥时降级成不鉴权探测"
        )
    return {
        "satisfied": not missing,
        "missing": missing,
        "onlyoffice_url": oo_url,
        "jwt_secret": secret,
        "why_not": why,
    }


def source_digests(repo: Path, paths: Any) -> dict[str, str]:
    """逐产物的**内容** sha256 —— 「源码变了但报告没刷新」这条 stale 轴的正确锁。

    🔴 原来这条轴靠顶层 `source_commit`（`git rev-parse HEAD`）锁住，而**提交这份报告本身
    就会改变 HEAD** ⇒ 报告在它自己的提交里必然 stale、`test_gate_check_passes` 一落地就红。
    这与「`--write` + `git diff --exit-code`」那类永假门禁同形：恒红的门禁没人看，等于没有
    门禁。内容 digest 没有这个毛病 —— 提交前后文件内容一致 ⇒ digest 一致；源码真改了
    ⇒ digest 变、报告必须重新 `--write`。

    🔴 调用方**不要**把报告自己传进来：报告内容包含本 digest，自指算不出不动点。

    🔴 **先按 LF 归一再哈希**。本仓 `core.autocrlf=true`：一次 rebase / checkout 就把工作树
    重新物化成 CRLF，而入库内容是 LF ⇒ 对原始字节哈希时，同一份已提交内容在 Windows 工作树
    与干净 Linux 检出上得出**两个不同的 digest**，报告在其中一边必然 stale。实测（2026-11-05
    变基后）：门禁与宿主守卫两项 digest 同时漂移，而 `git show HEAD:<path>` 的内容逐字节未变。
    这与「拿 HEAD sha 当源码轴」是同一类缺陷 —— 锁住了表示形式而不是内容。
    """
    import hashlib

    out: dict[str, str] = {}
    for path in sorted(str(item) for item in paths):
        target = repo / path
        if not target.is_file():
            out[path] = "missing-on-disk"
            continue
        normalized = target.read_bytes().replace(b"\r\n", b"\n")
        out[path] = hashlib.sha256(normalized).hexdigest()
    return out


def git_porcelain_of(repo: Path, paths: Any) -> dict[str, str]:
    """逐产物的 `git status --porcelain`。

    🔴 「spec 全绿 ≠ 产物已入库」：挂进 CI 的 job 在干净 checkout 下会因文件不存在必挂。
    因此门把自己每个产物的跟踪状态写进报告，`??` 一眼可见。

    🔴 先判存在：`git status --porcelain -- <不存在的路径>` 输出为空，与「已跟踪且干净」
    长得一模一样。不分开就会把「产物还没写出来」报成 `tracked-clean` —— 而那正是
    「挂进 CI 的 job 在干净 checkout 下必挂」这条判据要抓的东西。
    """
    import subprocess

    out: dict[str, str] = {}
    for path in paths:
        if not (repo / path).exists():
            out[path] = "missing-on-disk"
            continue
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain", "--", path],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            line = proc.stdout.strip().split("\n")[0] if proc.stdout.strip() else ""
            out[path] = line[:2].strip() if line else "tracked-clean"
        except Exception as exc:  # noqa: BLE001
            out[path] = f"error:{type(exc).__name__}"
    return out
