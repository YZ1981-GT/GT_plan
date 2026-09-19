# -*- coding: utf-8 -*-
"""任务 72 Stage A 门：真正 pre-delete eligibility（Stage B/C/D 的可执行性如实登记）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7

═══ 本门只做 Stage A，且刻意做成「可以变绿」的判据 ═══

Stage A 的四个零 + unreachable 唯一命中 deletion plan 全部由**纯谓词函数**算出，谓词吃的是
现算出来的事实而不是上游报告的自述。这样做有两个不可替代的作用：

1. **今天为红**是被实测的事实撑起来的，不是写死的结论；
2. **明天世界变了它会变绿** —— :func:`stage_a_state` 是纯函数，守卫喂合成输入即可证明它翻
   转。一个恒红的门与一个恒绿的门一样没有信息量（假绿第③源的镜像：把错值当基线锁死）。

═══ Stage A 的判据来自 AC 12.13 / Property 51 / Property 71 的逐字口径 ═══

* **四个零**：未裁决 = 0、假双向 = 0、bidirectional 未验收 = 0、evidence stale = 0；
* **加一条**：每个仍存在的 `unreachable`/legacy 待删项**唯一命中** Task 66 的
  path/digest/owner/rollback plan；
* **不得**要求「待删 unreachable 在删除前已为 0」—— 那是 Stage D 的条件，提前要求会让删除门
  永久不可达（Task 71 的删除门变异专门守这条）。本门把它做成**封闭谓词词表**：
  :data:`STAGE_A_PREDICATE_IDS` 里不允许出现 unreachable-zero 语义的 id。

🔴 **`evidence stale = 0` 今天是空分母下的 vacuous zero**：`working_paper_sync_test_run`
实测 0 行 ⇒ 没有任何 evidence 可以「过期」。把它当成「已刷新」正是本 spec 反复实测的假绿
第⑥源（空集恒真）。:func:`count_admissibility` 因此把「零 + 空分母」判成 **不可采纳**，与
「零 + 非空分母」严格区分开。

═══ 三条今天实测的红（各自独立、互不派生）═══

1. **真实 OO required scenario 一条都没真跑**（owner 70）：本门从 Task 70 报告的
   `scenario_execution.entries[].scenarios[]` **逐行现算**（不读它的 `verdict
   .executed_end_to_end` 自述），3290 行里 0 行落在已执行档。正文点名的五类（same-app
   fold / 跨 participant 幂等冲突 / quarantined 拒绝 / opaque version UUID / leader
   successor 与 no-successor）逐类现算同样为 0 ⇒ 正文逐字「任一 required scenario 未真实
   执行即保持 UNVERIFIABLE 并使 Stage A 为红」。
2. **`multi_resolver` ≠ 0**（gate 归属 71、实际阻塞 36）：live 重算 writer matrix 得 4 条，
   且 Task 12 矩阵那四行仍全部 `status=deferred` ⇒ `legacy_delete` gate 不放行。
3. **Task 66 的 rollback 隔离门 verdict = `blocked`**（本门独立复算同意）：2 个待删项
   `recoverable_from_git=false`、22/22 替代面模块 git 未跟踪、19/22 替代面不可从生产宿主到
   达 ⇒「唯一命中 path/digest/owner/rollback plan」这条在 **rollback plan** 维度上不成立。

═══ 本门不做什么（逐条都有代价，不是偷懒）═══

* **不删一个字节**：Stage A 红 ⇒ Stage B 禁止执行。本门反过来**证明**没删：125 条待删路径
  逐条现算 sha256 与 plan 登记值比对（全等 ⇒ 磁盘未动），并用 **AST** 自证本门源码里没有
  任何删除原语、`write_text` 只打在 :data:`OUTPUT_PATH` 上。
* **不重生成任何上游产物**：Tasks 66/67/68/69/70/71 的报告只读。重生成会改 source commit ⇒
  Task 70 的 evidence 全部 stale 并打红上游四把锁（Task 71 的 BP-71-5 已踩过）。
* **不跑 Stage D 的最终门**：正文「仅在五类计数全为 0 后运行」。**「因 Stage A 红而未运行」
  与「静默 skip」是两件事**，本门把二者分成两个字段如实记录。

用法::

    python backend/scripts/check/check_task72_pre_delete_eligibility_gate.py --write
    python backend/scripts/check/check_task72_pre_delete_eligibility_gate.py --check
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import socket
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, Sequence

REPO: Final[Path] = Path(__file__).resolve().parents[3]
BACKEND: Final[Path] = REPO / "backend"
DATA: Final[Path] = BACKEND / "data"

TASK_NUMBER: Final[str] = "72"
OWNER_TASK: Final[str] = "72"
SPEC: Final[str] = "workpaper-html-onlyoffice-bidirectional-writeback-closure"
SCHEMA_VERSION: Final[str] = "task72-pre-delete-eligibility:v1"

SPEC_DIR: Final[Path] = REPO / ".kiro" / "specs" / SPEC
TASKS_MD: Final[Path] = SPEC_DIR / "tasks.md"
DESIGN_MD: Final[Path] = SPEC_DIR / "design.md"
REQUIREMENTS_MD: Final[Path] = SPEC_DIR / "requirements.md"

OUTPUT_PATH: Final[Path] = DATA / "workpaper_sync_task72_pre_delete_eligibility.json"

T66_REPORT: Final[Path] = DATA / "workpaper_sync_task66_legacy_deletion_plan.json"
T67_REPORT: Final[Path] = DATA / "workpaper_sync_task67_structural_pre_reconcile.json"
T68_REPORT: Final[Path] = DATA / "workpaper_sync_task68_backend_chain_regression.json"
T69_REPORT: Final[Path] = DATA / "workpaper_sync_task69_frontend_regression.json"
T70_REPORT: Final[Path] = DATA / "workpaper_sync_task70_oo_scenario_refresh.json"
T71_REPORT: Final[Path] = DATA / "workpaper_sync_task71_mutation_capacity_recovery.json"

UPSTREAM_REPORTS: Final[tuple[Path, ...]] = (
    T66_REPORT,
    T67_REPORT,
    T68_REPORT,
    T69_REPORT,
    T70_REPORT,
    T71_REPORT,
)

WRITER_GATE: Final[Path] = BACKEND / "scripts/check/check_workpaper_writer_revision_gate.py"
WRITER_OVERLAY: Final[Path] = DATA / "workpaper_writer_domain_overlay.json"
WRITER_INVENTORY: Final[Path] = DATA / "workpaper_writer_inventory.json"
RESOLVER_MATRIX: Final[Path] = DATA / "workpaper_resolver_migration_matrix.json"

GATE_REL: Final[str] = "backend/scripts/check/check_task72_pre_delete_eligibility_gate.py"
GUARD_TEST_REL: Final[str] = (
    "backend/tests/workpaper_sync_predelete/test_task72_pre_delete_eligibility.py"
)
MUTATE_REL: Final[str] = "backend/scripts/diagnose/mutate_task72_pre_delete_eligibility_guards.py"

#: 正文「独立验证 Property …」逐条（12 条）。守卫与 design.md 双向锁死。
DECLARED_PROPERTIES: Final[tuple[int, ...]] = (1, 2, 3, 46, 47, 48, 51, 57, 69, 70, 71, 72)

#: 报告里不允许出现的键名 —— 防「smoke 把 evidence 顶回 verified」这类语义偷渡。
FORBIDDEN_RECORD_KEYS: Final[frozenset[str]] = frozenset(
    {"oo_probe_passed", "scenarios_passed", "stage_a_passed", "eligibility_granted", "verified"}
)

#: 逐次运行会变的键（`--check` 前剔除）。**`source_commit` 刻意不在名单里** —— 它是
#: 「源码变了但结论没刷新」这条 stale 轴的唯一锁。
VOLATILE_KEYS: Final[frozenset[str]] = frozenset({"generated_at", "elapsed_seconds"})

#: Stage A 的封闭谓词词表。**不含任何 unreachable-zero 语义** —— AC 12.13 逐字禁止把
#: 「待删 unreachable 已为 0」当成 Stage A 前置条件。
STAGE_A_PREDICATE_IDS: Final[tuple[str, ...]] = (
    "unadjudicated_is_admissibly_zero",
    "fake_bidirectional_is_admissibly_zero",
    "bidirectional_unaccepted_is_admissibly_zero",
    "evidence_stale_is_admissibly_zero",
    "every_pending_delete_uniquely_lands_in_plan",
    "named_required_scenarios_really_executed",
    "multi_resolver_criterion_passes",
    "deletion_plan_is_current_with_head",
)

#: Task 72 正文点名的 required scenario 家族（「任一未真实执行即 UNVERIFIABLE」）。
#: leader successor / no-successor 是两条独立 scenario，故六个 id 对应正文的五类点名。
NAMED_REQUIRED_SCENARIOS: Final[tuple[str, ...]] = (
    "same_application_higher_sequence_fold",
    "cross_participant_idempotency_409",
    "quarantined_rejects_application_and_engine",
    "opaque_version_rollback_no_numeric_collision",
    "close_leader_revoked_successor_exactly_one",
    "close_leader_revoked_no_successor_recovery_required",
)

#: Task 70 的执行档词表里**算已执行**的档位。今天两个实测档（`unrunnable_today` /
#: `upstream_implementation_gap`）都不在其中。
EXECUTED_TIERS: Final[frozenset[str]] = frozenset({"executed_end_to_end"})

#: `multi_resolver` 那四条 resolver 行（Task 71 移交过来的裁决，本门独立复算）。
MULTI_RESOLVER_ROWS: Final[tuple[str, ...]] = (
    "get_sheet_onlyoffice_config",
    "get_sheet_wopi_contents",
    "get_whole_excel_grid",
    "post_sheet_onlyoffice_callback",
)
_MULTI_RESOLVER_KEY: Final[str] = "multi_resolver"

#: Task 66 逐项必须齐备的五个绑定。
REQUIRED_BINDINGS: Final[tuple[str, ...]] = (
    "replacement",
    "owner",
    "last_call_site_binding",
    "rollback_target",
    "required_scenario_evidence",
)

#: Stage D 正文点名的最终门。逐条记录「是否运行」与「为什么没运行」，禁止静默 skip。
STAGE_D_FINAL_GATES: Final[tuple[str, ...]] = (
    "ci",
    "capacity",
    "retention",
    "redaction",
    "alerts",
    "tracked_files",
)

STAGE_D_NOT_RUN: Final[str] = "not_run_because_stage_a_red"
STAGE_D_RUN: Final[str] = "run"

SUB_BULLETS: Final[dict[str, str]] = {
    "1": "Stage A —— 真正 pre-delete eligibility（本门唯一执行的阶段）",
    "2": "Stage B —— 精确删除（Stage A 红 ⇒ 禁止执行，本门反证磁盘未动）",
    "3": "Stage C —— source commit 变化后完整重跑（无前置条件 ⇒ UNVERIFIABLE）",
    "4": "Stage D —— 最终五个零与归档（Stage A 红 ⇒ 未运行，非静默 skip）",
}


class Task72GateError(RuntimeError):
    """本门自己的失败态 —— 绝不 `except Exception` 吞成「无数据」（AC 5.12 同款教训）。"""


# ════════════════════════════════════════════════════════════════════════════
# §1 通用工具
# ════════════════════════════════════════════════════════════════════════════


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO)).replace("\\", "/")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_json(obj: Any, *, indent: int | None = None) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=indent, default=str)


def digest_of(obj: Any) -> str:
    return sha256_text(stable_json(obj))


def _git(args: Sequence[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def git_head() -> str:
    proc = _git(["rev-parse", "HEAD"])
    if proc.returncode != 0:
        raise Task72GateError(f"无法取 git HEAD: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_porcelain(paths: Sequence[str]) -> dict[str, str]:
    """逐产物的 `git status --porcelain`。

    🔴 **先判存在**：`git status --porcelain -- <不存在的路径>` 输出为空，与「已跟踪且干净」
    长得一模一样。不分开就会把「产物还没写出来」报成 `tracked-clean` —— 挂进 CI 的 job 在干净
    checkout 下必挂而报告里看不出来。
    """
    out: dict[str, str] = {}
    for path in paths:
        if not (REPO / path).exists():
            out[path] = "missing-on-disk"
            continue
        proc = _git(["status", "--porcelain", "--", path])
        line = proc.stdout.strip().split("\n")[0] if proc.stdout.strip() else ""
        out[path] = line[:2].strip() if line else "tracked-clean"
    return out


def git_tracked_at(commit: str, paths: Sequence[str]) -> dict[str, bool]:
    """逐路径现算「在 `commit` 上是否 tracked」。

    一次 `git ls-tree -r` 取全集再求交，不逐路径起进程（125 条路径 × 一个进程会把本门拖到
    分钟级，而且失败时无法区分「路径不存在」与「git 调用失败」）。
    """
    proc = _git(["ls-tree", "-r", "--name-only", commit], timeout=180)
    if proc.returncode != 0:
        raise Task72GateError(f"git ls-tree {commit[:12]} 失败: {proc.stderr.strip()}")
    tracked = set(proc.stdout.split("\n"))
    return {path: path in tracked for path in paths}


def read_json(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise Task72GateError(f"上游报告缺失: {rel(path)} —— 本门必须消费它，不得跳过")
    return json.loads(read_text(path))


def _tcp_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


# ════════════════════════════════════════════════════════════════════════════
# §2 tasks.md / design.md 声明（复选框归一化）
# ════════════════════════════════════════════════════════════════════════════

_CHECKBOX_RE: Final[re.Pattern[str]] = re.compile(r"^(\s*-\s\[)[ x~\-](\]\s+\d+\.)")


def task_body(task_number: str = TASK_NUMBER) -> str:
    """tasks.md 里指定任务的正文段。**首行复选框归一化成 `[?]`**。

    🔴 BP-70-6：不归一化时，编排器把 `[-]` 勾成 `[x]` 会让逐字节锁立刻打红而正文一个字都没
    变。本门的锁只对**正文内容**敏感。
    """
    lines = read_text(TASKS_MD).split("\n")
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(rf"^\s*-\s\[[ x~\-]\]\s+{task_number}\.", line)
        ),
        None,
    )
    if start is None:
        raise Task72GateError(f"tasks.md 里找不到任务 {task_number}")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.match(r"^\s*-\s\[[ x~\-]\]\s+\d+\.", lines[index])
            or lines[index].startswith("### ")
        ),
        len(lines),
    )
    body = lines[start:end]
    body[0] = _CHECKBOX_RE.sub(r"\1?\2", body[0])
    return "\n".join(body)


def task_declarations() -> dict[str, Any]:
    body = task_body()
    properties = sorted({int(m) for m in re.findall(r"Property (\d+)", body)})
    req_line = next((line for line in body.split("\n") if "_Requirements:" in line), "")
    requirements = re.findall(r"\d+\.\d+", req_line)
    bullets = [
        line
        for line in body.split("\n")
        if re.match(r"^\s{2}-\s", line) and "_Requirements:" not in line
    ]
    return {
        "properties_in_task_text": properties,
        "declared_properties": list(DECLARED_PROPERTIES),
        "properties_match": properties == sorted(DECLARED_PROPERTIES),
        "requirements_in_task_text": requirements,
        "requirement_count": len(requirements),
        "sub_bullet_count_in_task_text": len(bullets),
        "sub_bullet_count_declared": len(SUB_BULLETS),
        "sub_bullet_count_match": len(bullets) == len(SUB_BULLETS),
        "body_digest": sha256_text(body),
        "body_digest_checkbox_normalized": True,
        "why_normalized": (
            "BP-70-6：不归一化时编排器把 `[-]` 翻成 `[x]` 会让逐字节锁必红而正文零变化。"
        ),
    }


def design_property_titles() -> dict[str, str]:
    """design.md 里本门声明的 12 条 Property 的标题。找不到即结构错误。"""
    text = read_text(DESIGN_MD)
    out: dict[str, str] = {}
    for number in DECLARED_PROPERTIES:
        match = re.search(rf"^###\s+Property\s+{number}\b[:：]?\s*(.*)$", text, re.M)
        if match is None:
            raise Task72GateError(
                f"design.md 里找不到 `### Property {number}` —— 声明的 Property 必须在设计"
                "文档里有定义，否则「验证了它」无从核对"
            )
        out[str(number)] = match.group(1).strip()
    return out


def requirement_clauses() -> dict[str, Any]:
    """AC 12.13 / 14.16 的逐字口径 —— Stage A 判据的法源，现读不背诵。"""
    text = read_text(REQUIREMENTS_MD)
    clauses: dict[str, Any] = {}
    for ac in ("12.13", "14.16", "1.7", "14.7"):
        escaped = ac.replace(".", r"\.")
        match = re.search(rf"^\s*{escaped}\.\s+(.*)$", text, re.M)
        if match is None:
            raise Task72GateError(f"requirements.md 里找不到 AC {ac}")
        clauses[ac] = match.group(1).strip()
    body = clauses["12.13"]
    return {
        "ac_text": clauses,
        "ac_12_13_names_four_zeros": all(
            token in body for token in ("未裁决", "假双向", "bidirectional 未验收", "evidence stale")
        ),
        "ac_12_13_requires_unique_plan_landing": "唯一命中" in body,
        "ac_12_13_forbids_requiring_unreachable_zero_upfront": (
            "不得把" in body and "unreachable 已为 0" in body
        ),
        "ac_1_7_forbids_deprecated_tombstone": "DEPRECATED" in clauses["1.7"],
        "ac_14_7_requires_four_state_mutation": "ANCHOR-MISS" in clauses["14.7"],
    }


# ════════════════════════════════════════════════════════════════════════════
# §3 纯谓词（可喂合成输入 ⇒ 守卫能证明本门会变绿，不是恒红）
# ════════════════════════════════════════════════════════════════════════════


def count_admissibility(*, value: int, denominator: int) -> dict[str, Any]:
    """一个「必须为 0」的计数是否**可采纳地**为零。

    🔴 三态而不是两态：

    * `value > 0` ⇒ 不为零，不可采纳；
    * `value == 0 and denominator == 0` ⇒ **vacuous zero**，不可采纳。空集恒真是本 spec 反复
      实测的假绿源：`evidence stale = 0` 今天成立**只因为** `working_paper_sync_test_run`
      一行都没有，没有任何 evidence 可以「过期」；
    * `value == 0 and denominator > 0` ⇒ 可采纳。

    分成三态而不是「zero and denominator>0」一行的理由：报告要能区分「真清零」与「分母为空」，
    否则读者看到 `evidence_stale: 0` 会以为已经刷新过了。
    """
    zero = value == 0
    denominator_empty = denominator == 0
    if not zero:
        reason = "nonzero"
    elif denominator_empty:
        reason = "vacuous_zero_empty_denominator"
    else:
        reason = "admissible_zero"
    return {
        "value": value,
        "denominator": denominator,
        "zero": zero,
        "denominator_empty": denominator_empty,
        "admissible": bool(zero and not denominator_empty),
        "reason": reason,
    }


def family_execution_state(tier_histogram: Mapping[str, int]) -> dict[str, Any]:
    """一个 required scenario 家族是否**真的**跑过。

    判据 = 落在 :data:`EXECUTED_TIERS` 里的行数 > 0，且没有任何行留在未执行档。
    「零场景全部通过」不是通过（Task 70 的 forbidden claim 同款），故家族行数为 0 时判未执行。
    """
    total = sum(int(v) for v in tier_histogram.values())
    executed = sum(int(v) for tier, v in tier_histogram.items() if tier in EXECUTED_TIERS)
    return {
        "rows": total,
        "executed_rows": executed,
        "unexecuted_rows": total - executed,
        "tier_histogram": dict(sorted((str(k), int(v)) for k, v in tier_histogram.items())),
        "really_executed": bool(total > 0 and executed == total),
    }


def pending_delete_landing_verdict(
    *,
    plan_item_count_for_subject: int,
    bindings_present: Mapping[str, bool],
    digest_matches_disk: bool,
    rollback_recoverable: bool,
) -> dict[str, Any]:
    """一个待删 subject 是否**唯一命中** Task 66 的 path/digest/owner/rollback plan。

    四个维度全要（正文逐字「唯一命中 Task 66 path/digest/owner/rollback plan」）：

    1. 计划里**恰一条** item 认领这个 subject（>1 ⇒ Stage B 不知道该删哪一份，0 ⇒ 计划外路径）；
    2. 五个绑定齐备（含 owner 与 rollback_target）；
    3. 登记 digest 与磁盘现算相等（不等 ⇒ 计划已 stale，按它删就是删了没审过的内容）；
    4. rollback 可回滚（不可回滚 ⇒ 删除不可逆，正文「计划外路径变化立即中止并回滚」无从执行）。
    """
    missing = sorted(name for name, present in bindings_present.items() if not present)
    reasons: list[str] = []
    if plan_item_count_for_subject != 1:
        reasons.append(f"plan_item_count={plan_item_count_for_subject}")
    if missing:
        reasons.append("missing_bindings=" + ",".join(missing))
    if not digest_matches_disk:
        reasons.append("digest_drift")
    if not rollback_recoverable:
        reasons.append("rollback_not_recoverable")
    return {
        "uniquely_landed": not reasons,
        "failure_reasons": reasons,
        "missing_bindings": missing,
    }


def multi_resolver_criterion_passes(
    *, multi_resolver_rows: Sequence[str], rows_still_deferred: Sequence[str]
) -> bool:
    """`multi_resolver` 准则：计数为 0 **且**四条行都已不再 `deferred`（两个条件都要）。"""
    return len(multi_resolver_rows) == 0 and not list(rows_still_deferred)


def stage_a_state(predicates: Mapping[str, bool]) -> str:
    """Stage A 的红/绿。

    🔴 纯函数 + 封闭词表校验：谓词集合必须**恰等于** :data:`STAGE_A_PREDICATE_IDS`。多一条
    （比如偷偷加「待删 unreachable 已为 0」）或少一条（比如把 evidence stale 那条摘掉让门变
    绿）都直接抛，而不是静静算出一个结论。
    """
    got = set(predicates)
    want = set(STAGE_A_PREDICATE_IDS)
    if got != want:
        raise Task72GateError(
            f"Stage A 谓词集合与封闭词表不符：多 {sorted(got - want)}、缺 {sorted(want - got)}"
        )
    return "green" if all(bool(v) for v in predicates.values()) else "red"


def stage_d_run_decision(stage_a: str) -> str:
    """Stage D 是否运行最终门。

    只有两个返回值，**没有 `skipped`** —— 正文「禁止静默 skip」。「因 Stage A 红而未运行」是
    一个有理由的、可复核的状态；`skip` 是没有理由的状态，本门的类型里就不存在它。
    """
    if stage_a == "green":
        return STAGE_D_RUN
    return STAGE_D_NOT_RUN


def stage_a_vocabulary_excludes_unreachable_zero(
    predicate_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """AC 12.13 逐字：Stage A 不得要求「待删 unreachable 在删除前已为 0」。

    做成对**本门自己的词表**的现算判据而不是一句注释：谓词 id 里凡出现 unreachable 且带 zero
    语义的即违约。Task 71 的删除门变异专门守这条，本门在自己这一侧独立成立。

    🔴 **吃 `predicate_ids` 参数**：不带参时检自己的词表；守卫喂一个**含违规 id 的合成词表**
    即可证明检出器真的会命中。首版写成零参函数，实测被「把检出条件改成 `if False`」这条变异
    绕过（GREEN）—— 真词表本来就干净，检出器坏掉与词表合规长得一模一样。
    """
    ids = list(STAGE_A_PREDICATE_IDS if predicate_ids is None else predicate_ids)
    offenders = [
        pid for pid in ids if "unreachable" in pid and ("zero" in pid or "cleared" in pid)
    ]
    return {
        "predicate_ids": ids,
        "offending_predicate_ids": offenders,
        "excludes_unreachable_zero": offenders == [],
        "why": (
            "AC 12.13 逐字「不得把『待本次删除的 unreachable 已为 0』作为」Stage A 前置条件；"
            "提前要求会让删除门永久不可达（要删的东西必须先不存在）。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §4 上游六份报告（只读，逐份记 digest）
# ════════════════════════════════════════════════════════════════════════════


def upstream_inputs() -> dict[str, Any]:
    """消费 Tasks 66/67/68/69/70/71 的报告。

    只取本门真正用到的 key，并逐份记 `report_digest` + `source_commit`：上游一旦被重生成，本门
    的锁会跟着变，「我消费的是哪一版」永远可复核。
    """
    t66 = read_json(T66_REPORT)
    t67 = read_json(T67_REPORT)
    t68 = read_json(T68_REPORT)
    t69 = read_json(T69_REPORT)
    t70 = read_json(T70_REPORT)
    t71 = read_json(T71_REPORT)
    return {
        "task66_legacy_deletion_plan": {
            "path": rel(T66_REPORT),
            "plan_commit": t66.get("plan_commit"),
            "item_total": len(t66.get("items") or []),
            "rollback_isolation_verdict": (t66.get("rollback_isolation_gate") or {}).get("verdict"),
            "blocking_precondition_ids": [
                str(bp.get("id")) for bp in (t66.get("blocking_preconditions") or [])
            ],
            "how_this_gate_uses_it": (
                "Stage A 的「唯一命中 path/digest/owner/rollback plan」逐 subject 现算它的 items；"
                "Stage B 的「磁盘未动」反证也拿它的登记 digest 做基线。"
            ),
        },
        "task67_structural_pre_reconcile": {
            "path": rel(T67_REPORT),
            "report_digest": t67.get("report_digest"),
            "source_commit": t67.get("report_commit"),
            "entry_count": len(t67.get("entries") or []),
            "verdict": (t67.get("verdict") or {}).get("state"),
            "how_this_gate_uses_it": (
                "五类计数的分子分母全部从它的 `entries[].verdicts` **逐行现算**，不读它的"
                "`counters` 自述 —— 自述与逐行现算是两个来源，只有两侧一致才算复核过。"
            ),
        },
        "task68_backend_chain_regression": {
            "path": rel(T68_REPORT),
            "report_digest": t68.get("report_digest"),
            "source_commit": t68.get("source_commit"),
            "verdict": (t68.get("verdict") or {}).get("result"),
            "blocking_point_ids": [str(bp.get("id")) for bp in (t68.get("blocking_points") or [])],
            "how_this_gate_uses_it": (
                "Stage A 正文要求「先消费 Tasks 68/69 独立回归」：本门核对它的 verdict 与既存 BP "
                "清单，并把 BP-68-1 的 owner（Task 22）原样转记，不在本门顺手修。"
            ),
        },
        "task69_frontend_regression": {
            "path": rel(T69_REPORT),
            "report_digest": t69.get("report_digest"),
            "source_commit": t69.get("source_commit"),
            "verdict": (t69.get("verdict") or {}).get("result"),
            "port_3030_listening": (t69.get("oo_scope_boundary") or {}).get("port_3030_listening"),
            "blocking_point_ids": [str(bp.get("id")) for bp in (t69.get("blocking_points") or [])],
            "how_this_gate_uses_it": (
                "Stage C 的前置条件清单引用它实录的「3030 未监听」；本门另做一次独立 socket 现测，"
                "两侧一致才写进报告。"
            ),
        },
        "task70_oo_scenario_refresh": {
            "path": rel(T70_REPORT),
            "report_digest": t70.get("report_digest"),
            "source_commit": t70.get("source_commit"),
            "verdict": (t70.get("verdict") or {}).get("state"),
            "self_reported_executed_end_to_end": (t70.get("verdict") or {}).get(
                "executed_end_to_end"
            ),
            "self_reported_required_scenario_rows": (t70.get("verdict") or {}).get(
                "required_scenario_rows"
            ),
            "how_this_gate_uses_it": (
                "Stage A 最重的一条判据。本门**不读**它的 `executed_end_to_end` 自述来下结论，"
                "而是逐 `scenario_execution.entries[].scenarios[]` 现算执行档，再与自述比对："
                "两侧不一致本身就是结构错误。"
            ),
        },
        "task71_mutation_capacity_recovery": {
            "path": rel(T71_REPORT),
            "report_digest": t71.get("report_digest"),
            "source_commit": t71.get("source_commit"),
            "verdict": (t71.get("verdict") or {}).get("state"),
            "legacy_delete_released": (t71.get("verdict") or {}).get("legacy_delete_released"),
            "self_reported_multi_resolver_count": (
                t71.get("multi_resolver_adjudication") or {}
            ).get("multi_resolver_count"),
            "blocking_point_ids": [str(bp.get("id")) for bp in (t71.get("blocking_points") or [])],
            "how_this_gate_uses_it": (
                "`legacy_delete` gate 的放行位。本门独立 live 重算 writer matrix 与 Task 12 矩阵，"
                "再与它的自述比对；同时原样转记 BP-71-3 / BP-71-8 两条既存缺陷的 owner。"
            ),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# §5 五类计数（从 Task 67 逐 entry 现算，不读它的 counters）
# ════════════════════════════════════════════════════════════════════════════

#: Task 67 逐 entry `verdicts` 里的五类判定键 → Stage A 的口径名。
_VERDICT_KEYS: Final[dict[str, str]] = {
    "unadjudicated": "未裁决",
    "fake_bidirectional": "假双向",
    "unaccepted": "bidirectional 未验收",
    "evidence_stale": "evidence stale",
    "unreachable": "unreachable（Stage D 条件，非 Stage A 前置）",
}


def build_five_counts() -> dict[str, Any]:
    """五类计数逐 entry 现算 + 与 Task 67 自述比对 + evidence stale 的分母可采纳性。

    分母口径两套都给（正文「父入口不重复计数」⇒ 主口径只取独立 entry），差集显式写出，确保没有
    任何真实 entry 因为不进主分母而从报告里消失。
    """
    t67 = read_json(T67_REPORT)
    entries = list(t67.get("entries") or [])
    if not entries:
        raise Task72GateError("Task 67 报告里 entries 为空 —— 五类计数无分母可算")

    independent = [row for row in entries if row.get("independent_entry")]
    recomputed_primary = {
        key: sum(1 for row in independent if (row.get("verdicts") or {}).get(key) is True)
        for key in _VERDICT_KEYS
    }
    recomputed_all = {
        key: sum(1 for row in entries if (row.get("verdicts") or {}).get(key) is True)
        for key in _VERDICT_KEYS
    }
    self_reported = dict((t67.get("counters") or {}).get("reported_by_task_text") or {})
    self_reported_all = dict(
        (t67.get("counters") or {}).get("reported_by_task_text_over_all_entries") or {}
    )

    # evidence stale 的分母 = 有多少 entry 的 stale 「可度量」（Task 67 逐 entry 现算的
    # `evidence_stale_is_measurable`）。分母为 0 ⇒ 计数 0 是 vacuous。
    stale_measurable = sum(
        1
        for row in independent
        if (row.get("verdicts") or {}).get("evidence_stale_is_measurable") is True
    )
    test_run_rows = int(
        ((read_json(T70_REPORT).get("db_snapshot") or {}).get("row_counts_before") or {}).get(
            "working_paper_sync_test_run", 0
        )
        or 0
    )

    admissibility = {
        "unadjudicated": count_admissibility(
            value=recomputed_primary["unadjudicated"], denominator=len(independent)
        ),
        "fake_bidirectional": count_admissibility(
            value=recomputed_primary["fake_bidirectional"], denominator=len(independent)
        ),
        "unaccepted": count_admissibility(
            value=recomputed_primary["unaccepted"], denominator=len(independent)
        ),
        "evidence_stale": count_admissibility(
            value=recomputed_primary["evidence_stale"], denominator=stale_measurable
        ),
    }
    return {
        "denominators": {
            "manifest_entry_total": len(entries),
            "independent_entry_total": len(independent),
            "parent_duplicate_total": len(entries) - len(independent),
            "primary_denominator": "independent_entry_total",
            "primary_denominator_why": "正文「父入口不重复计数」",
            "evidence_stale_denominator": stale_measurable,
            "evidence_stale_denominator_why": (
                "逐 entry 现算 `verdicts.evidence_stale_is_measurable`；今天为 0，与 Task 70 实录的"
                f"`working_paper_sync_test_run` = {test_run_rows} 行同源 —— 没有 evidence 可以过期。"
            ),
            "sync_test_run_rows_measured_by_task70": test_run_rows,
        },
        "recomputed_primary": recomputed_primary,
        "recomputed_over_all_entries": recomputed_all,
        "task67_self_reported_primary": self_reported,
        "task67_self_reported_over_all_entries": self_reported_all,
        "recompute_agrees_with_task67_primary": {
            key: recomputed_primary[key] == self_reported.get(key) for key in _VERDICT_KEYS
        },
        "recompute_agrees_with_task67_all": {
            key: recomputed_all[key] == self_reported_all.get(key) for key in _VERDICT_KEYS
        },
        "all_recomputes_agree": all(
            recomputed_primary[key] == self_reported.get(key) for key in _VERDICT_KEYS
        )
        and all(recomputed_all[key] == self_reported_all.get(key) for key in _VERDICT_KEYS),
        "admissibility": admissibility,
        "four_zeros_all_admissible": all(row["admissible"] for row in admissibility.values()),
        "labels": dict(_VERDICT_KEYS),
        "unreachable_is_not_a_stage_a_precondition": (
            "AC 12.13 逐字禁止把「待删 unreachable 已为 0」当 Stage A 前置；此处只报计数"
            f"（主口径 {recomputed_primary['unreachable']} / 全口径 {recomputed_all['unreachable']}）。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §6 真实 OO required scenario 执行档（从 Task 70 逐 row 现算）
# ════════════════════════════════════════════════════════════════════════════


def scenario_counts_agree(
    *,
    recomputed_rows: int,
    recomputed_executed: int,
    self_reported_rows: Any,
    self_reported_executed: Any,
) -> bool:
    """逐行现算的两个计数与 Task 70 自述是否一致（跨文件双向锁）。

    🔴 抽成纯函数是为了让「不一致时真的会报」可被喂输入证明：内联在报告里时，把该字段写死成
    True 在今天两侧本来就一致的情况下是**等价变异**（实测 GREEN），复核它还得连带跑一遍整份
    Task 70 报告的重算。
    """
    return (
        recomputed_rows == self_reported_rows and recomputed_executed == self_reported_executed
    )


def build_required_scenario_execution() -> dict[str, Any]:
    """逐 scenario row 现算执行档，并对正文点名的六个 scenario id 逐一判「是否真跑过」。

    🔴 现算而不是读 `verdict.executed_end_to_end`：那是自述。两侧都算出来再比对，任何一侧漂移
    都会被 `agrees_with_task70_self_report` 抓到 —— 这是跨文件双向锁，比读一个数字强。
    """
    t70 = read_json(T70_REPORT)
    entries = list((t70.get("scenario_execution") or {}).get("entries") or [])
    if not entries:
        raise Task72GateError("Task 70 报告里 scenario_execution.entries 为空 —— 无法现算执行档")

    tier_total: Counter[str] = Counter()
    family_tiers: dict[str, Counter[str]] = {}
    rows_total = 0
    for row in entries:
        for scenario in row.get("scenarios") or []:
            rows_total += 1
            tier = str(scenario.get("execution_tier"))
            tier_total[tier] += 1
            scenario_id = str(scenario.get("scenario_id"))
            family_tiers.setdefault(scenario_id, Counter())[tier] += 1

    executed_rows = sum(count for tier, count in tier_total.items() if tier in EXECUTED_TIERS)
    named = {
        scenario_id: family_execution_state(family_tiers.get(scenario_id, Counter()))
        for scenario_id in NAMED_REQUIRED_SCENARIOS
    }
    unnamed_in_report = sorted(set(family_tiers) - set(NAMED_REQUIRED_SCENARIOS))
    missing_named = [sid for sid in NAMED_REQUIRED_SCENARIOS if sid not in family_tiers]

    self_executed = (t70.get("verdict") or {}).get("executed_end_to_end")
    self_required = (t70.get("verdict") or {}).get("required_scenario_rows")
    return {
        "measured_from": (
            "Task 70 报告 `scenario_execution.entries[].scenarios[].execution_tier` 逐行现算"
        ),
        "entry_rows_scanned": len(entries),
        "required_scenario_rows_recomputed": rows_total,
        "executed_rows_recomputed": executed_rows,
        "tier_histogram_recomputed": dict(sorted(tier_total.items())),
        "executed_tier_vocabulary": sorted(EXECUTED_TIERS),
        "task70_self_reported_executed_end_to_end": self_executed,
        "task70_self_reported_required_scenario_rows": self_required,
        "agrees_with_task70_self_report": scenario_counts_agree(
            recomputed_rows=rows_total,
            recomputed_executed=executed_rows,
            self_reported_rows=self_required,
            self_reported_executed=self_executed,
        ),
        # 🔴 `list(...)` 不是多余：tuple 序列化成 JSON 后回读是 list，`--check` 的逐字节比对
        #    会把「元组 vs 列表」当成漂移而恒红（首轮实测就是它）。
        "named_required_scenarios": list(NAMED_REQUIRED_SCENARIOS),
        "named_required_scenario_count": len(NAMED_REQUIRED_SCENARIOS),
        "named_scenarios_missing_from_task70": missing_named,
        "per_named_scenario": named,
        "named_scenarios_really_executed": sorted(
            sid for sid, facts in named.items() if facts["really_executed"]
        ),
        "named_scenarios_not_executed": sorted(
            sid for sid, facts in named.items() if not facts["really_executed"]
        ),
        "all_named_really_executed": bool(
            not missing_named and all(facts["really_executed"] for facts in named.values())
        ),
        "other_scenario_ids_in_task70": unnamed_in_report,
        "other_scenario_id_count": len(unnamed_in_report),
        "why_named_scenarios_gate_stage_a": (
            "Task 72 正文逐字：「same-app fold、跨 participant 幂等冲突、quarantined 拒绝、"
            "opaque version UUID、leader successor/no-successor 任一 required scenario 未真实执行"
            "即保持 UNVERIFIABLE 并使 Stage A 为红」。"
        ),
        "zero_scenarios_is_not_all_passed": (
            "家族行数为 0 时判未执行 —— 「零场景全部通过」不是通过（与 Task 70 的 forbidden "
            "claim 同款）。"
        ),
    }


def build_environment_preconditions() -> dict[str, Any]:
    """真实 OO 场景的三条环境前提，本门独立现测（不引用别人的自述作结论）。"""
    frontend = _tcp_listening("127.0.0.1", 3030)
    backend_api = _tcp_listening("127.0.0.1", 9980)
    onlyoffice = _tcp_listening("127.0.0.1", 8080)
    t69 = read_json(T69_REPORT)
    t70 = read_json(T70_REPORT)
    db_before = (t70.get("db_snapshot") or {}).get("row_counts_before") or {}
    business_rows = {
        table: db_before.get(table)
        for table in (
            "working_paper_sync_test_run",
            "working_paper_entry_evidence_scenario",
            "working_paper_content_version",
            "working_paper_content_representation",
            "working_paper_sync_entry_state",
        )
    }
    return {
        "measured_by": "本门 socket 现测 + Task 70 报告的 DB 行数现读",
        "frontend_3030_listening": frontend,
        "backend_9980_listening": backend_api,
        "onlyoffice_8080_listening": onlyoffice,
        "task69_recorded_3030_listening": (t69.get("oo_scope_boundary") or {}).get(
            "port_3030_listening"
        ),
        "agrees_with_task69_on_3030": frontend
        == bool((t69.get("oo_scope_boundary") or {}).get("port_3030_listening")),
        "evidence_table_rows": business_rows,
        "all_evidence_tables_empty": all((value or 0) == 0 for value in business_rows.values()),
        "oo_forcesave_requires_live_session": (t70.get("oo_probe") or {}).get(
            "forcesave_requires_live_editing_session"
        ),
        "missing_preconditions": sorted(
            name
            for name, ok in {
                "frontend_3030_listening": frontend,
                "onlyoffice_live_editing_session": False,
                "business_data_in_evidence_tables": not all(
                    (value or 0) == 0 for value in business_rows.values()
                ),
            }.items()
            if not ok
        ),
        "why_it_matters": (
            "OO 8080 healthcheck 通与「有活动编辑会话」是两件事：forcesave 对不存在的 doc key 回"
            " error 1（Task 70 实测）。8080 在听**不能**当成场景可跑。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §7 待删项唯一命中 deletion plan（逐 subject 现算 + 磁盘 digest + plan commit tracked）
# ════════════════════════════════════════════════════════════════════════════


def build_pending_delete_landing() -> dict[str, Any]:
    """逐 pending_delete subject 判「唯一命中 path/digest/owner/rollback plan」。

    subject 的粒度 = `item_id`（不是 path）：实测 80 条路径承载 >1 个 item（典型 = 一个
    composable 文件同时是 `legacy_composable` 与 `legacy_local_storage_key` 两个 subject，最多
    4 个）。按 path 判唯一性会把这 80 条全打成「重复命中」——那是判据错，不是计划错；按
    `item_id` 判才对得上「Stage B 删的是站点/符号而不总是整文件」这件事。
    """
    t66 = read_json(T66_REPORT)
    items = list(t66.get("items") or [])
    plan_commit = str(t66.get("plan_commit") or "")
    if not plan_commit:
        raise Task72GateError("Task 66 计划里没有 plan_commit —— rollback 基线无从核对")

    pending = [item for item in items if item.get("disposition") == "pending_delete"]
    subject_counts = Counter(str(item.get("item_id")) for item in pending)
    paths = sorted({str(item.get("path")) for item in pending})
    tracked_at_plan = git_tracked_at(plan_commit, paths)

    disk_digest: dict[str, str | None] = {}
    for path in paths:
        target = REPO / path
        disk_digest[path] = sha256_file(target) if target.is_file() else None

    rows: list[dict[str, Any]] = []
    for item in pending:
        item_id = str(item.get("item_id"))
        path = str(item.get("path"))
        rollback = item.get("rollback_target") or {}
        bindings_present = {
            name: bool(item.get(name)) for name in REQUIRED_BINDINGS
        }
        digest_matches = disk_digest.get(path) == item.get("sha256")
        verdict = pending_delete_landing_verdict(
            plan_item_count_for_subject=subject_counts[item_id],
            bindings_present=bindings_present,
            digest_matches_disk=digest_matches,
            rollback_recoverable=bool(rollback.get("recoverable_from_git")),
        )
        rows.append(
            {
                "item_id": item_id,
                "category": item.get("category"),
                "path": path,
                "plan_item_count_for_subject": subject_counts[item_id],
                "bindings_present": bindings_present,
                "digest_matches_disk": digest_matches,
                "rollback_mode": rollback.get("mode"),
                "rollback_recoverable": bool(rollback.get("recoverable_from_git")),
                "tracked_at_plan_commit": tracked_at_plan.get(path),
                "owner_deletion_task": (item.get("owner") or {}).get("deletion_owner_task"),
                **verdict,
            }
        )

    failing = [row for row in rows if not row["uniquely_landed"]]
    reason_histogram: Counter[str] = Counter()
    for row in failing:
        for reason in row["failure_reasons"]:
            reason_histogram[reason.split("=")[0]] += 1

    replacement = list(t66.get("replacement_registry") or [])
    replacement_untracked_live = sorted(
        str(row.get("path"))
        for row in replacement
        if _git(["ls-files", "--error-unmatch", str(row.get("path"))]).returncode != 0
    )
    replacement_unreachable = sorted(
        str(row.get("path"))
        for row in replacement
        if row.get("reachable_from_production_host") is False
    )
    isolation = t66.get("rollback_isolation_gate") or {}
    checks = isolation.get("checks") or {}
    return {
        "subject_granularity": "item_id",
        "why_not_path": (
            "80 条路径承载 >1 个 item（最多 4）—— 按 path 判唯一性会把它们全打成重复命中，"
            "那是判据错不是计划错。"
        ),
        "plan_commit": plan_commit,
        "pending_delete_subject_total": len(pending),
        "pending_delete_distinct_path_total": len(paths),
        "subjects_uniquely_landed": len(rows) - len(failing),
        "subjects_failing": len(failing),
        "failure_reason_histogram": dict(sorted(reason_histogram.items())),
        "failing_subjects": [
            {
                "item_id": row["item_id"],
                "path": row["path"],
                "failure_reasons": row["failure_reasons"],
                "rollback_mode": row["rollback_mode"],
                "tracked_at_plan_commit": row["tracked_at_plan_commit"],
            }
            for row in failing
        ],
        "all_subjects_uniquely_landed": not failing,
        "paths_missing_from_disk": sorted(
            path for path, digest in disk_digest.items() if digest is None
        ),
        "paths_untracked_at_plan_commit": sorted(
            path for path, ok in tracked_at_plan.items() if not ok
        ),
        "digest_drift_paths": sorted(
            {
                str(item.get("path"))
                for item in pending
                if disk_digest.get(str(item.get("path"))) != item.get("sha256")
            }
        ),
        "replacement_surface_total": len(replacement),
        "replacement_surface_untracked_live": replacement_untracked_live,
        "replacement_surface_untracked_live_count": len(replacement_untracked_live),
        "replacement_surface_unreachable_from_production_host": replacement_unreachable,
        "replacement_surface_unreachable_count": len(replacement_unreachable),
        "task66_rollback_isolation_verdict": isolation.get("verdict"),
        "task66_rollback_isolation_failing_checks": sorted(
            name for name, row in checks.items() if row.get("passed") is False
        ),
        "recompute_agrees_with_task66_isolation": bool(
            (isolation.get("verdict") == "blocked")
            == bool(replacement_untracked_live or failing)
        ),
        "why_replacement_surface_matters": (
            "「删 legacy 保 replacement」是一笔事务：替代面自身未入库（实测 22/22 `??`）时，删完"
            "无法回到可用状态 ⇒ rollback plan 维度不成立。另有 19/22 不可从生产宿主到达（BP-66-1），"
            "删掉 legacy 后没有活的替代路径。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §8 multi_resolver（live 重算 writer matrix + Task 12 矩阵四行）
# ════════════════════════════════════════════════════════════════════════════


def resolver_matrix_facts(path: Path | None = None) -> dict[str, Any]:
    """读 Task 12 矩阵里那四条 resolver 行。抽成吃路径的纯函数 ⇒ 判据可喂植入矩阵。"""
    matrix = json.loads(read_text(path or RESOLVER_MATRIX))
    named = {
        str(row.get("qualname")): row
        for row in (matrix.get("rows") or [])
        if str(row.get("qualname")) in MULTI_RESOLVER_ROWS
        and "onlyoffice_router" in str(row.get("module"))
    }
    per_row = {
        qualname: {
            "present_in_matrix": qualname in named,
            "status": named.get(qualname, {}).get("status"),
            "intended_status": named.get(qualname, {}).get("intended_status"),
            "blocking_task": named.get(qualname, {}).get("blocking_task"),
            "adjudication_owner_task": named.get(qualname, {}).get("adjudication_owner_task"),
        }
        for qualname in MULTI_RESOLVER_ROWS
    }
    return {
        "per_row": per_row,
        "rows_still_deferred": sorted(
            qualname for qualname, row in per_row.items() if row["status"] == "deferred"
        ),
        "rows_absent_from_matrix": sorted(
            qualname for qualname, row in per_row.items() if not row["present_in_matrix"]
        ),
        "adjudication_owner_tasks": sorted(
            {str(row["adjudication_owner_task"]) for row in per_row.values()}
        ),
        "blocking_tasks": sorted({str(row["blocking_task"]) for row in per_row.values()}),
    }


def build_multi_resolver_live() -> dict[str, Any]:
    """live 重算 writer matrix 取 `multi_resolver` 计数，并与 Task 71 的自述比对。

    **不写盘、不重生成 inventory**：磁盘 inventory 实测已 stale（BP-71-5，owner 20/74），重生成
    会改 source commit 并让 Task 70 的 evidence 全部 stale、打红上游四把锁。
    """
    spec = importlib.util.spec_from_file_location("t72_writer_gate", WRITER_GATE)
    if spec is None or spec.loader is None:
        raise Task72GateError(f"无法加载 writer 门: {rel(WRITER_GATE)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    generator = module.load_generator()
    rows, function_facts = generator.collect_source_facts()
    overlay = json.loads(read_text(WRITER_OVERLAY))
    live = generator.build_inventory(rows, overlay, function_facts)
    issues = module.evaluate_gate(live)
    counts = {key: len(value) for key, value in sorted(issues.items())}
    live_multi = sorted(issues.get(_MULTI_RESOLVER_KEY) or [])

    on_disk = json.loads(read_text(WRITER_INVENTORY))
    matrix = resolver_matrix_facts()
    still_deferred = matrix["rows_still_deferred"]
    t71 = read_json(T71_REPORT)
    t71_self = (t71.get("multi_resolver_adjudication") or {}).get("multi_resolver_count")
    return {
        "measured_from": (
            "live 重算：`load_generator()` → `collect_source_facts()` → `build_inventory(overlay)`"
            " → `evaluate_gate()`；**不写盘**、不改 inventory"
        ),
        "writer_gate_criteria": counts,
        "writer_gate_criteria_count": len(counts),
        "multi_resolver_count": len(live_multi),
        "multi_resolver_rows_measured": live_multi,
        "multi_resolver_is_zero": len(live_multi) == 0,
        "named_rows": list(MULTI_RESOLVER_ROWS),
        "measured_rows_match_named": sorted(row.rsplit("::", 1)[-1] for row in live_multi)
        == sorted(MULTI_RESOLVER_ROWS),
        "resolver_matrix": matrix["per_row"],
        "rows_still_deferred": still_deferred,
        "adjudication_owner_tasks": matrix["adjudication_owner_tasks"],
        "blocking_tasks": matrix["blocking_tasks"],
        "criterion_passes": multi_resolver_criterion_passes(
            multi_resolver_rows=live_multi, rows_still_deferred=still_deferred
        ),
        "task71_self_reported_count": t71_self,
        "agrees_with_task71": len(live_multi) == t71_self,
        "inventory_on_disk_is_stale": str(live.get("source_digest"))
        != str(on_disk.get("source_digest")),
        "inventory_source_digest_live": live.get("source_digest"),
        "inventory_source_digest_on_disk": on_disk.get("source_digest"),
        "inventory_stale_owner_task": "20",
        "consequence_if_not_zero": (
            "`legacy_delete` gate 不放行 Task 72 的全局 legacy 删除（Task 71 正文逐字）。"
        ),
        "real_blocking_task": "36",
        "real_blocking_reason": (
            "四条行的剩余阻塞是 Task 36 的逐 entry 供给：任一 entry 拿到 approved bundle 之前，把"
            " router 改成只经 substrate 取数会让全部底稿的 OO 入口 fail closed。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §9 Stage A 组装
# ════════════════════════════════════════════════════════════════════════════


def build_stage_a(
    *,
    counts: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    landing: Mapping[str, Any],
    multi_resolver: Mapping[str, Any],
    head_commit: str,
) -> dict[str, Any]:
    """Stage A 的八条谓词 + 红/绿 + 逐条 owner。"""
    admissibility = counts["admissibility"]
    plan_is_current = landing["plan_commit"] == head_commit

    predicates: dict[str, bool] = {
        "unadjudicated_is_admissibly_zero": bool(admissibility["unadjudicated"]["admissible"]),
        "fake_bidirectional_is_admissibly_zero": bool(
            admissibility["fake_bidirectional"]["admissible"]
        ),
        "bidirectional_unaccepted_is_admissibly_zero": bool(
            admissibility["unaccepted"]["admissible"]
        ),
        "evidence_stale_is_admissibly_zero": bool(admissibility["evidence_stale"]["admissible"]),
        "every_pending_delete_uniquely_lands_in_plan": bool(
            landing["all_subjects_uniquely_landed"]
            and not landing["replacement_surface_untracked_live"]
        ),
        "named_required_scenarios_really_executed": bool(scenarios["all_named_really_executed"]),
        "multi_resolver_criterion_passes": bool(multi_resolver["criterion_passes"]),
        "deletion_plan_is_current_with_head": bool(plan_is_current),
    }
    state = stage_a_state(predicates)

    detail: dict[str, Any] = {
        "unadjudicated_is_admissibly_zero": {
            "measured": admissibility["unadjudicated"],
            "owner_task": "67",
            "statement": (
                f"未裁决实测 {admissibility['unadjudicated']['value']} / "
                f"{admissibility['unadjudicated']['denominator']} 个独立 entry"
            ),
        },
        "fake_bidirectional_is_admissibly_zero": {
            "measured": admissibility["fake_bidirectional"],
            "owner_task": "36",
            "statement": (
                f"假双向实测 {admissibility['fake_bidirectional']['value']} 个 entry —— "
                "capability 全是 single_onlyoffice / 0 个 bidirectional，adapter 注册数 0"
            ),
        },
        "bidirectional_unaccepted_is_admissibly_zero": {
            "measured": admissibility["unaccepted"],
            "owner_task": "70",
            "statement": (
                f"bidirectional 未验收实测 {admissibility['unaccepted']['value']} 个 entry —— "
                "evidence 五表 0 行，没有任何 entry 通过验收"
            ),
        },
        "evidence_stale_is_admissibly_zero": {
            "measured": admissibility["evidence_stale"],
            "owner_task": "70",
            "statement": (
                "evidence stale 计数为 0，但**分母为空**（`evidence_stale_is_measurable` 逐 entry "
                f"现算 = {admissibility['evidence_stale']['denominator']}，`working_paper_sync_"
                f"test_run` = {counts['denominators']['sync_test_run_rows_measured_by_task70']} 行）"
                " ⇒ vacuous zero，不可采纳"
            ),
            "why_not_green": (
                "「零 + 空分母」是空集恒真（假绿第⑥源）：没有 evidence 可以过期不等于 evidence 已"
                "刷新。honest 读法是 142 个 entry 全在未验收里。"
            ),
        },
        "every_pending_delete_uniquely_lands_in_plan": {
            "measured": {
                "subjects_total": landing["pending_delete_subject_total"],
                "subjects_uniquely_landed": landing["subjects_uniquely_landed"],
                "subjects_failing": landing["subjects_failing"],
                "failure_reason_histogram": landing["failure_reason_histogram"],
                "replacement_surface_untracked_live_count": landing[
                    "replacement_surface_untracked_live_count"
                ],
                "task66_rollback_isolation_verdict": landing["task66_rollback_isolation_verdict"],
            },
            "owner_task": "72",
            "statement": (
                f"{landing['subjects_failing']} / {landing['pending_delete_subject_total']} 个待删"
                " subject 未唯一命中（rollback 不可回滚）；另有 "
                f"{landing['replacement_surface_untracked_live_count']} / "
                f"{landing['replacement_surface_total']} 个替代面模块 git 未跟踪 ⇒ Task 66 的"
                " rollback 隔离门 verdict = blocked"
            ),
        },
        "named_required_scenarios_really_executed": {
            "measured": {
                "required_scenario_rows_recomputed": scenarios["required_scenario_rows_recomputed"],
                "executed_rows_recomputed": scenarios["executed_rows_recomputed"],
                "tier_histogram_recomputed": scenarios["tier_histogram_recomputed"],
                "named_scenarios_not_executed": scenarios["named_scenarios_not_executed"],
                "agrees_with_task70_self_report": scenarios["agrees_with_task70_self_report"],
            },
            "owner_task": "70",
            "statement": (
                f"逐行现算 {scenarios['executed_rows_recomputed']} / "
                f"{scenarios['required_scenario_rows_recomputed']} 行落在已执行档；正文点名的 "
                f"{len(scenarios['named_scenarios_not_executed'])} / "
                f"{scenarios['named_required_scenario_count']} 个 scenario 一条都没真跑"
            ),
        },
        "multi_resolver_criterion_passes": {
            "measured": {
                "multi_resolver_count": multi_resolver["multi_resolver_count"],
                "multi_resolver_rows_measured": multi_resolver["multi_resolver_rows_measured"],
                "rows_still_deferred": multi_resolver["rows_still_deferred"],
                "agrees_with_task71": multi_resolver["agrees_with_task71"],
            },
            "owner_task": "36",
            "statement": (
                f"live 重算 `multi_resolver` = {multi_resolver['multi_resolver_count']}（≠0）且"
                f" {len(multi_resolver['rows_still_deferred'])} 条行仍 `deferred` ⇒ `legacy_delete`"
                " gate 不放行"
            ),
        },
        "deletion_plan_is_current_with_head": {
            "measured": {
                "plan_commit": landing["plan_commit"],
                "head_commit": head_commit,
                "equal": plan_is_current,
            },
            "owner_task": "66",
            "statement": (
                "deletion plan 的 plan_commit 与当前 HEAD 相等 ⇒ 计划里的 digest/rollback 基线仍"
                "对得上磁盘"
            ),
        },
    }
    failing = sorted(pid for pid, ok in predicates.items() if not ok)
    return {
        "state": state,
        "state_vocabulary": ["red", "green"],
        "predicate_ids": list(STAGE_A_PREDICATE_IDS),
        "predicates": predicates,
        "predicate_detail": detail,
        "failing_predicates": failing,
        "failing_predicate_count": len(failing),
        "passing_predicates": sorted(pid for pid, ok in predicates.items() if ok),
        "vocabulary_check": stage_a_vocabulary_excludes_unreachable_zero(),
        "owner_tasks_of_failing": sorted(
            {str(detail[pid]["owner_task"]) for pid in failing}
        ),
        "means": (
            "Stage A 为红 ⇒ Stage B 一个字节都不许删；Stage C 无前置条件；Stage D 的最终门不运行。"
            "本门把每条红的实测数字、计算来源与 owner 逐条固化，供 orchestrator 登记阻塞。"
        ),
        "forbidden_claims": [
            "不得宣称任何真实 OO probe 已通过",
            "不得把 vacuous zero（空分母）当成已清零",
            "不得用文档/离线测试/smoke 代替真实 OO 场景",
            "不得要求待删 unreachable 在删除前已为 0",
        ],
    }


# ════════════════════════════════════════════════════════════════════════════
# §10 Stage B —— BLOCKED，并反证「磁盘一个字节都没动」
# ════════════════════════════════════════════════════════════════════════════

#: 无歧义的删除原语（任何接收者上出现即越权）。
#:
#: 🔴 **`remove` / `replace` / `rename` 刻意不在这里**：首版把它们放进来后本门自己打红了
#: —— `rel()` 里的 `str.replace("\\", "/")` 是同名方法调用。这不是「代码有问题」而是判据
#: 太粗：AST 只看方法名时与内建字符串方法撞名，属假红。它们改由
#: :data:`_QUALIFIED_DELETE_CALLS` 按 `模块.方法` 二元组判，零歧义。
_DELETE_CALLS: Final[frozenset[str]] = frozenset({"unlink", "rmdir", "rmtree", "removedirs"})

#: 需要模块限定才算删除原语的形态（`os.remove` 是删，`str.remove` 不存在，`str.replace` 不是删）。
_QUALIFIED_DELETE_CALLS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("os", "remove"),
        ("os", "rename"),
        ("os", "replace"),
        ("os", "unlink"),
        ("shutil", "rmtree"),
        ("shutil", "move"),
    }
)


def scan_source_boundary(source: str) -> dict[str, Any]:
    """扫一段源码的写盘目标与删除原语。

    🔴 用 AST 而不是子串：子串判据会被**说明文字**里的 `unlink` 三个字打成假红（Task 62 实测
    过同型缺陷），也会被 `# noqa: 这里没有 rmtree` 这类注释骗过。

    🔴 但 AST 也不能只看方法名 —— 见 :data:`_DELETE_CALLS` 的注释：首版把 `replace` 放进无歧义
    名单，被 `str.replace` 撞出一条假红。判据的粒度要跟得上语言的重名事实。

    🔴 **吃 source 字符串而不是自己去读文件**：这样守卫可以喂一段**真含删除原语**的合成源码，
    证明检测器会命中。不这么分层的话「本门无删除原语」这条测试可能只是检测器坏了（永远返回
    空集）—— 那是假绿第②源的 AST 版本，而且是自我比对（判据与被判对象同一个实现）。
    """
    tree = ast.parse(source)
    write_targets: list[str] = []
    delete_calls: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        receiver = node.func.value
        receiver_name = receiver.id if isinstance(receiver, ast.Name) else None
        if attr in {"write_text", "write_bytes"}:
            write_targets.append(receiver_name or ast.dump(receiver)[:60])
        if attr in _DELETE_CALLS:
            delete_calls.append(f"{receiver_name or '<expr>'}.{attr}")
        if receiver_name is not None and (receiver_name, attr) in _QUALIFIED_DELETE_CALLS:
            delete_calls.append(f"{receiver_name}.{attr}")
    return {
        "write_call_targets": sorted(set(write_targets)),
        "write_calls_only_output_path": sorted(set(write_targets)) in ([], ["OUTPUT_PATH"]),
        "delete_primitives_found": sorted(set(delete_calls)),
        "no_delete_primitive": not delete_calls,
        "delete_primitive_vocabulary": sorted(_DELETE_CALLS),
        "qualified_delete_primitive_vocabulary": sorted(
            f"{module}.{attr}" for module, attr in _QUALIFIED_DELETE_CALLS
        ),
        "judged_by": (
            "AST + 接收者限定 —— 只看方法名会被 `str.replace` 撞成假红（本门首版实测），"
            "只看子串会被说明文字撞成假红（Task 62 实测）"
        ),
    }


def _self_ast_write_targets() -> dict[str, Any]:
    """AST 自证：本门源码里写盘只打 `OUTPUT_PATH`，且无删除原语。"""
    return {
        "scanned": GATE_REL,
        **scan_source_boundary(read_text(REPO / GATE_REL)),
    }


#: **有归属的 out-of-band 移除登记**（不是豁免列）。
#:
#: 语义严格限定为：**用户点名、在 Stage B 之外**发生的单文件移除。登记一条不等于放过一条 ——
#: `validate_out_of_band_removals()` 会逐条现场核验三件事（在 Task 66 计划的待删集合里、磁盘上
#: 确实已不在、计划登记的 disposition/category 与登记声明一致）。任何一条不成立即进
#: `verdict.structural_errors`，所以：
#:
#: * 把一条**还在盘上**的路径塞进来 ⇒ `registered_but_still_on_disk` ⇒ 红（它没被移除，登记是假的）；
#: * 把一条**计划外**路径塞进来 ⇒ `registered_but_not_in_plan` ⇒ 红；
#: * 内容被**改动**（digest 变了但文件仍在）**永远不在**本登记的语义内 —— 只覆盖「整文件不在了」。
#:
#: Stage B 的 `executed` / `files_deleted` 不因本登记改变：Stage B 没有跑，这一条是它之外的动作。
OUT_OF_BAND_REMOVALS: tuple[dict[str, str], ...] = (
    {
        "path": (
            "audit-platform/frontend/src/components/workpaper/composables/"
            "useG7LonTerDualMode.ts"
        ),
        "directive": "用户点名清理（2026-09-02，Task 74 会话内的 out-of-band 请求）",
        "expected_disposition": "pending_delete",
        "expected_category": "legacy_composable",
        "why": (
            "整个文件只有一条 `@deprecated` 别名 re-export，且它 re-export 的 `./useG7DualMode` "
            "已由 Task 45 删除 ⇒ 指向已删模块的死墓碑（实测 `tsc --noEmit` 报 TS2307 "
            "`Cannot find module './useG7DualMode'`），全仓库对 `useG7LonTerDualMode` 零 importer"
            "（只有它自己与 Task 66 计划 JSON 提到这个名字）。AC 1.7 逐字禁止以 `DEPRECATED` 注释"
            "长期保留不可达旧桩。"
        ),
        "counts_as_stage_b_execution": "false",
    },
)


def validate_out_of_band_removals(
    *,
    pending_paths: Iterable[str],
    plan_items: Iterable[Mapping[str, Any]],
    registry: Iterable[Mapping[str, str]] = OUT_OF_BAND_REMOVALS,
) -> dict[str, Any]:
    """逐条现场核验 out-of-band 登记。登记 ≠ 豁免，核验不过即结构错误。"""
    pending = set(pending_paths)
    by_path: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in plan_items:
        by_path[str(item.get("path"))].append(item)

    rows: list[dict[str, Any]] = []
    for record in registry:
        path = record["path"]
        items = by_path.get(path) or []
        problems: list[str] = []
        if path not in pending:
            problems.append("registered_but_not_in_plan")
        if (REPO / path).exists():
            problems.append("registered_but_still_on_disk")
        for item in items:
            if str(item.get("disposition")) != record["expected_disposition"]:
                problems.append(
                    f"plan_disposition_mismatch={item.get('disposition')}"
                )
            if str(item.get("category")) != record["expected_category"]:
                problems.append(f"plan_category_mismatch={item.get('category')}")
        rows.append(
            {
                **record,
                "plan_item_ids": sorted(str(item.get("item_id")) for item in items),
                "plan_disposition": sorted({str(item.get("disposition")) for item in items}),
                "plan_category": sorted({str(item.get("category")) for item in items}),
                "problems": sorted(set(problems)),
                "valid": not problems,
            }
        )
    return {
        "why_this_is_not_an_exemption": (
            "登记只解释「这一条计划内路径为什么已经不在盘上」，不解释「磁盘可以随便动」：三条现场"
            "核验（在计划待删集合里 / 磁盘上确实已不在 / 计划登记的 disposition·category 与声明"
            "一致）任一不成立即进 structural_errors。塞一条还在盘上的路径进来会被 "
            "`registered_but_still_on_disk` 打红。"
        ),
        "records": rows,
        "registered_paths": sorted(record["path"] for record in registry),
        "valid_paths": sorted(row["path"] for row in rows if row["valid"]),
        "invalid_records": [row for row in rows if not row["valid"]],
        "all_valid": all(row["valid"] for row in rows),
    }


def build_stage_b(
    *,
    stage_a_state_value: str,
    landing: Mapping[str, Any],
    out_of_band: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stage B：Stage A 红 ⇒ BLOCKED，且必须**反证**没有偷偷删。

    「我没删」是自述；「125 条待删路径逐条 sha256 与 plan 登记值全等 + 本门 AST 无删除原语」是
    证据。两条都给，读者不必相信任何人的克制。

    🔴 **out-of-band 移除**：本 spec 之外（用户点名）移除了某条计划内路径时，反证不能靠「把它从
    分母里拿掉」来维持绿 —— 那正是缩小分母。做法是：**只有经 `validate_out_of_band_removals()`
    现场核验通过的路径**才允许出现在 `paths_missing_from_disk` 里而不算「磁盘被动过」，未登记的
    缺失一条都不放过，且 digest 漂移（文件仍在、内容变了）**从不**被登记覆盖。
    """
    blocked = stage_a_state_value != "green"
    self_ast = _self_ast_write_targets()
    excused = set((out_of_band or {}).get("valid_paths") or ())
    missing = list(landing["paths_missing_from_disk"])
    unexplained_missing = sorted(path for path in missing if path not in excused)
    # digest 漂移里，「文件已不在」那部分与 missing 同源；仍在盘上却改了内容的绝不豁免。
    drift = list(landing["digest_drift_paths"])
    unexplained_drift = sorted(
        path
        for path in drift
        if not (path in excused and path in set(missing))
    )
    disk_untouched = not unexplained_drift and not unexplained_missing
    return {
        "state": "blocked" if blocked else "eligible",
        "state_vocabulary": ["blocked", "eligible", "executed", "rolled_back"],
        "executed": False,
        "bytes_deleted": 0,
        "files_deleted": 0,
        "blocked_by": ["stage_a_red"] if blocked else [],
        "non_execution_proof": {
            "pending_delete_paths_checked": landing["pending_delete_distinct_path_total"],
            "digest_drift_paths": drift,
            "paths_missing_from_disk": missing,
            "out_of_band_removed_paths": sorted(excused & set(missing)),
            "unexplained_digest_drift_paths": unexplained_drift,
            "unexplained_paths_missing_from_disk": unexplained_missing,
            "disk_matches_plan_digest_everywhere": disk_untouched,
            "why_this_is_the_proof": (
                "计划登记的 sha256 是 plan commit 时的内容指纹。除已具名登记的 out-of-band 移除"
                "外，逐条现算全等 ⇒ 没有任何待删对象被改或被删；未登记的缺失文件数为 0 ⇒ 没有"
                "整文件删除。登记本身要过三条现场核验，见 `out_of_band_removals`。"
            ),
        },
        "out_of_band_removals": dict(out_of_band or {}),
        "self_ast_boundary": self_ast,
        "no_deprecated_tombstone_left": {
            "statement": (
                "本门没有执行删除，因此不存在「删了但留 DEPRECATED 墓碑」的形态；该判据的真正落点"
                "在 Stage B 真执行那一轮。"
            ),
            "ac": "1.7",
            "measurable_today": False,
        },
        "what_stage_b_needs": [
            "Stage A 八条谓词全绿（当前 red）",
            "Task 66 rollback 隔离门 verdict 从 blocked 变 open（替代面入库 + 可回滚）",
            "替代面 22 个模块入库且至少被生产宿主真消费（BP-66-1，owner 67）",
        ],
    }


# ════════════════════════════════════════════════════════════════════════════
# §11 Stage C —— UNVERIFIABLE（source commit 未变 ⇒ 没有「删除后重跑」这件事）
# ════════════════════════════════════════════════════════════════════════════


def build_stage_c(
    *,
    stage_b: Mapping[str, Any],
    head_commit: str,
    environment: Mapping[str, Any],
    scenarios: Mapping[str, Any],
) -> dict[str, Any]:
    """Stage C：删除改变 source commit 后的完整重跑。今天连「删除」都没发生。"""
    upstream_commits = {
        rel(path): str(read_json(path).get("source_commit") or read_json(path).get("report_commit"))
        for path in (T67_REPORT, T68_REPORT, T69_REPORT, T70_REPORT, T71_REPORT)
    }
    unchanged = sorted({commit for commit in upstream_commits.values()}) == [head_commit]
    return {
        "state": "unverifiable",
        "state_vocabulary": ["unverifiable", "refreshed", "failed"],
        "executed": False,
        "reason": "stage_b_not_executed",
        "not_a_silent_skip": True,
        "source_commit_head": head_commit,
        "upstream_report_source_commits": upstream_commits,
        "source_commit_unchanged_since_upstream_runs": unchanged,
        "why_unchanged_matters": (
            "Stage C 的触发条件逐字是「source commit 变化后」。HEAD 与上游五份报告的 source commit"
            "全等 ⇒ 既没删也没改，没有任何 entry 需要新 test run。这不是跳过，是触发条件不成立。"
        ),
        "new_test_runs_created": 0,
        "scenarios_rerun": 0,
        "required_scenario_rows_that_would_need_rerun": scenarios[
            "required_scenario_rows_recomputed"
        ],
        "missing_preconditions": environment["missing_preconditions"],
        "what_stage_c_needs": [
            "Stage B 真执行过并因此改变 source commit（当前未执行）",
            "3030 前端在听（当前未监听）",
            "真实 OnlyOffice 活动编辑会话（forcesave 对不存在 doc key 回 error 1）",
            "生产库有业务数据（evidence 五表实测全 0 行）",
        ],
        "forbidden_substitutes": [
            "离线测试",
            "smoke",
            "文档声明",
            "合成 measurement",
        ],
        "smoke_cannot_restore_verified": (
            "正文逐字「smoke 只能附加，不能恢复 verified」。本门的 verdict 词表里没有 `passed`/"
            "`verified` 态，smoke 无处把结论顶回去。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §12 Stage D —— 未运行（不是静默 skip）
# ════════════════════════════════════════════════════════════════════════════


def build_stage_d(
    *, stage_a: Mapping[str, Any], counts: Mapping[str, Any], landing: Mapping[str, Any]
) -> dict[str, Any]:
    """Stage D：五个零 + 最终门 + 归档。

    🔴 **「因 Stage A 红而未运行」与「静默 skip」分成两个字段**：正文「禁止静默 skip」。前者有
    理由、可复核、会随 Stage A 变绿自动运行；后者是没有理由的缺席。:func:`stage_d_run_decision`
    的返回值域里根本没有 `skipped`。
    """
    decision = stage_d_run_decision(str(stage_a["state"]))
    admissibility = counts["admissibility"]
    five_zeros = {
        "unadjudicated": admissibility["unadjudicated"],
        "fake_bidirectional": admissibility["fake_bidirectional"],
        "bidirectional_unaccepted": admissibility["unaccepted"],
        "unreachable": count_admissibility(
            value=int(counts["recomputed_over_all_entries"]["unreachable"]),
            denominator=int(counts["denominators"]["manifest_entry_total"]),
        ),
        "evidence_stale": admissibility["evidence_stale"],
    }
    gates = {
        name: {
            # `run` 恒 False —— 本门从不执行 Stage D 的最终门（那要等 Stage B/C 先做完）。
            # 真正随世界变化的字段是 `stage_a_precondition_met`：Stage A 变绿后它翻 True，
            # 于是「未运行」不是一句写死的话，而是一个有前置条件、可被观测到解除的状态。
            "run": False,
            "reason": decision,
            "stage_a_precondition_met": decision == STAGE_D_RUN,
            "not_a_silent_skip": True,
            "measurable_today": name == "tracked_files",
            "why_not_run": (
                "正文逐字「仅在 post-delete 五类计数全为 0 后运行最终 CI/容量/retention/redaction/"
                "alerts/tracked-files 门」；Stage A 红 ⇒ 前置条件不成立。"
            ),
        }
        for name in STAGE_D_FINAL_GATES
    }
    return {
        "state": decision,
        "state_vocabulary": [STAGE_D_RUN, STAGE_D_NOT_RUN],
        "run_decision_has_no_skip_state": "skipped" not in (STAGE_D_RUN, STAGE_D_NOT_RUN),
        "post_delete_five_zeros": five_zeros,
        "post_delete_five_zeros_all_admissible": all(
            row["admissible"] for row in five_zeros.values()
        ),
        "post_delete_is_pre_delete_today": (
            "Stage B 未执行 ⇒ post-delete 计数 == pre-delete 计数。此处如实标明二者今天同源，"
            "不假装做过一轮 post-delete 度量。"
        ),
        "final_gates": gates,
        "final_gates_run_count": 0,
        "final_gates_silently_skipped_count": 0,
        "archive": {
            "index_updated": False,
            "archived": False,
            "reason": decision,
            "what_archive_needs": [
                "Stage A 八条谓词全绿",
                "Stage B 按计划精确删除并逐项核对 rollback",
                "Stage C 为全部受影响 entry 建新 test run 并跑完 required scenarios",
                "Stage D 五个零全部**可采纳**为零（非空分母）",
                "机器核对全部 AC/Properties/DAG/gate/禁止文件边界（AC 14.15）",
            ],
        },
        "unreachable_note": (
            "unreachable 在 Stage D 才要求为 0（全口径实测 "
            f"{counts['recomputed_over_all_entries']['unreachable']}）；Stage A 不得提前要求它。"
        ),
        "landing_reference": {
            "pending_delete_subject_total": landing["pending_delete_subject_total"],
            "task66_rollback_isolation_verdict": landing["task66_rollback_isolation_verdict"],
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# §13 反事实多臂 —— 证明本门**会变绿**（恒红门与恒绿门一样没有信息量）
# ════════════════════════════════════════════════════════════════════════════


def build_counterfactual_arms(
    stage_a: Mapping[str, Any], *, state_fn: Any = stage_a_state
) -> dict[str, Any]:
    """逐谓词造一条「若该谓词成立」的臂，要求 Stage A 结论真的翻转。

    🔴 这是本门最重要的自检：一个恒红的门跟一个恒绿的门一样没有信息量（假绿第③源的镜像 ——
    把错值当基线锁死）。臂全部喂给纯函数 :func:`stage_a_state`，不碰任何磁盘。

    🔴 **`state_fn` 可注入**：守卫塞一个「全绿也返回 red」的假实现，本函数就必须报
    `gate_can_go_green=False`。首版把全绿探针的结果内联写死是等价变异（实测 GREEN）——
    今天探针本来就返回 green，写死与真跑长得一样。
    """
    today = dict(stage_a["predicates"])
    baseline = state_fn(today)
    arms: list[dict[str, Any]] = []
    for pid in STAGE_A_PREDICATE_IDS:
        flipped = dict(today)
        flipped[pid] = not today[pid]
        state = state_fn(flipped)
        arms.append(
            {
                "arm_id": f"flip::{pid}",
                "flipped_predicate": pid,
                "from_value": today[pid],
                "to_value": flipped[pid],
                "state": state,
                "conclusion_changes": state != baseline,
                "why": (
                    "该谓词是今天为红的原因之一 ⇒ 翻成 True 后若仍红说明还有别的红（正常）；"
                    "本臂只要求它**参与**结论，即在全绿基线上翻成 False 必须让结论变红。"
                ),
            }
        )
    all_green = {pid: True for pid in STAGE_A_PREDICATE_IDS}
    green_state = state_fn(all_green)
    single_red_arms = []
    for pid in STAGE_A_PREDICATE_IDS:
        probe = dict(all_green)
        probe[pid] = False
        probe_state = state_fn(probe)
        single_red_arms.append(
            {
                "arm_id": f"only_red::{pid}",
                "state": probe_state,
                "flips_green_to_red": probe_state == "red",
            }
        )
    return {
        "statement": (
                "Stage A 的红是被实测撑起来的，不是写死的：全绿输入下本门返回 green，任一谓词单独"
                "为假即返回 red。"
        ),
        "baseline_state": baseline,
        "all_green_probe_state": green_state,
        "gate_can_go_green": green_state == "green",
        "arm_count": len(arms),
        "arms": arms,
        "single_red_arms": single_red_arms,
        "every_predicate_alone_can_turn_it_red": all(
            row["flips_green_to_red"] for row in single_red_arms
        ),
        "vocabulary_is_enforced": {
            "extra_predicate_raises": True,
            "missing_predicate_raises": True,
            "why": (
                "`stage_a_state` 对谓词集合做封闭词表校验：偷偷加一条（如 unreachable=0）或摘掉一条"
                "（如 evidence stale）都直接抛，而不是静静算出一个更好看的结论。"
            ),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# §14 正向重算 —— 判据在合成输入上给出预期结论
# ════════════════════════════════════════════════════════════════════════════


def build_forward_recompute() -> dict[str, Any]:
    """把每个纯谓词喂一组合成输入，逐条核对结论。

    教训 15：没有正例的判据抓不到「分类器恒真」。因此每个谓词至少一条正例 + 一条负例。
    """
    rows: list[dict[str, Any]] = [
        {
            "case": "count_admissibility::real_zero",
            "input": {"value": 0, "denominator": 142},
            "expected": {"admissible": True, "reason": "admissible_zero"},
            "actual": count_admissibility(value=0, denominator=142),
        },
        {
            "case": "count_admissibility::vacuous_zero",
            "input": {"value": 0, "denominator": 0},
            "expected": {"admissible": False, "reason": "vacuous_zero_empty_denominator"},
            "actual": count_admissibility(value=0, denominator=0),
        },
        {
            "case": "count_admissibility::nonzero",
            "input": {"value": 136, "denominator": 142},
            "expected": {"admissible": False, "reason": "nonzero"},
            "actual": count_admissibility(value=136, denominator=142),
        },
        {
            "case": "family_execution_state::fully_executed",
            "input": {"executed_end_to_end": 137},
            "expected": {"really_executed": True},
            "actual": family_execution_state({"executed_end_to_end": 137}),
        },
        {
            "case": "family_execution_state::partially_executed",
            "input": {"executed_end_to_end": 100, "unrunnable_today": 37},
            "expected": {"really_executed": False},
            "actual": family_execution_state(
                {"executed_end_to_end": 100, "unrunnable_today": 37}
            ),
        },
        {
            "case": "family_execution_state::empty_family_is_not_a_pass",
            "input": {},
            "expected": {"really_executed": False},
            "actual": family_execution_state({}),
        },
        {
            "case": "pending_delete_landing_verdict::clean",
            "input": {"count": 1, "bindings": "all", "digest": True, "rollback": True},
            "expected": {"uniquely_landed": True},
            "actual": pending_delete_landing_verdict(
                plan_item_count_for_subject=1,
                bindings_present={name: True for name in REQUIRED_BINDINGS},
                digest_matches_disk=True,
                rollback_recoverable=True,
            ),
        },
        {
            "case": "pending_delete_landing_verdict::rollback_not_recoverable",
            "input": {"count": 1, "bindings": "all", "digest": True, "rollback": False},
            "expected": {"uniquely_landed": False},
            "actual": pending_delete_landing_verdict(
                plan_item_count_for_subject=1,
                bindings_present={name: True for name in REQUIRED_BINDINGS},
                digest_matches_disk=True,
                rollback_recoverable=False,
            ),
        },
        {
            "case": "pending_delete_landing_verdict::digest_drift",
            "input": {"count": 1, "bindings": "all", "digest": False, "rollback": True},
            "expected": {"uniquely_landed": False},
            "actual": pending_delete_landing_verdict(
                plan_item_count_for_subject=1,
                bindings_present={name: True for name in REQUIRED_BINDINGS},
                digest_matches_disk=False,
                rollback_recoverable=True,
            ),
        },
        {
            "case": "pending_delete_landing_verdict::two_plan_items_for_one_subject",
            "input": {"count": 2, "bindings": "all", "digest": True, "rollback": True},
            "expected": {"uniquely_landed": False},
            "actual": pending_delete_landing_verdict(
                plan_item_count_for_subject=2,
                bindings_present={name: True for name in REQUIRED_BINDINGS},
                digest_matches_disk=True,
                rollback_recoverable=True,
            ),
        },
        {
            "case": "multi_resolver_criterion_passes::cleared",
            "input": {"rows": [], "deferred": []},
            "expected": {"passes": True},
            "actual": {
                "passes": multi_resolver_criterion_passes(
                    multi_resolver_rows=[], rows_still_deferred=[]
                )
            },
        },
        {
            "case": "multi_resolver_criterion_passes::zero_count_but_still_deferred",
            "input": {"rows": [], "deferred": ["get_whole_excel_grid"]},
            "expected": {"passes": False},
            "actual": {
                "passes": multi_resolver_criterion_passes(
                    multi_resolver_rows=[], rows_still_deferred=["get_whole_excel_grid"]
                )
            },
        },
        {
            "case": "stage_d_run_decision::green_runs",
            "input": {"stage_a": "green"},
            "expected": {"decision": STAGE_D_RUN},
            "actual": {"decision": stage_d_run_decision("green")},
        },
        {
            "case": "stage_d_run_decision::red_is_not_skip",
            "input": {"stage_a": "red"},
            "expected": {"decision": STAGE_D_NOT_RUN},
            "actual": {"decision": stage_d_run_decision("red")},
        },
    ]
    for row in rows:
        expected = row["expected"]
        actual = row["actual"]
        row["agrees"] = all(actual.get(key) == value for key, value in expected.items())
    return {
        "row_count": len(rows),
        "rows": rows,
        "all_agree": all(row["agrees"] for row in rows),
        "disagreeing_cases": [row["case"] for row in rows if not row["agrees"]],
        "has_positive_case": any(
            row["agrees"] and row["expected"].get(key) is True
            for row in rows
            for key in row["expected"]
        ),
        "why": (
            "只有负例的判据可能恒假（永远说红），只有正例的可能恒真。每个谓词两侧都给，正负都能"
            "复现才算判据。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §15 Property 落位
# ════════════════════════════════════════════════════════════════════════════

TIER_STRUCTURAL: Final[str] = "structural_side_only"
TIER_PURE_LOGIC: Final[str] = "verified_on_pure_predicates"
TIER_UNVERIFIABLE: Final[str] = "unverifiable"

PROPERTY_TIERS: Final[tuple[str, ...]] = (TIER_PURE_LOGIC, TIER_STRUCTURAL, TIER_UNVERIFIABLE)


def assert_property_tier(tier: str) -> str:
    """档位必须落在封闭词表里，否则抛。

    🔴 抽成吃一个字符串的函数：内联在 `build_property_landings` 的循环里时，「把校验改成
    `if False`」是等价变异（今天全部档位本来就合规，实测 GREEN）。守卫喂一个自由文本档位
    （如「已覆盖」）即可证明词表真的在把关 —— 自由文本充当验证结论是本 spec 反复实测的形态。
    """
    if tier not in PROPERTY_TIERS:
        raise Task72GateError(
            f"Property 档位 {tier!r} 不在词表 {list(PROPERTY_TIERS)} 里 —— 自由文本不得充当验证结论"
        )
    return tier


def build_property_landings(
    *,
    stage_a: Mapping[str, Any],
    counts: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    landing: Mapping[str, Any],
    arms: Mapping[str, Any],
) -> dict[str, Any]:
    """12 条声明 Property 逐条落位 + 档位 + 未验证的 owner。"""
    titles = design_property_titles()
    rows: dict[str, Any] = {
        "1": {
            "tier": TIER_STRUCTURAL,
            "landing": "counts.denominators.manifest_entry_total",
            "how": "Task 67 逐 entry 现算 186 个挂载点入口，与它自述的分母比对",
        },
        "2": {
            "tier": TIER_STRUCTURAL,
            "landing": "counts.recomputed_primary",
            "how": "capability 取值只出现在四值封闭词表里（Task 67 现读）",
        },
        "3": {
            "tier": TIER_STRUCTURAL,
            "landing": "stage_a.predicate_detail.fake_bidirectional_is_admissibly_zero",
            "how": f"假双向实测 {counts['recomputed_primary']['fake_bidirectional']} ≠ 0",
        },
        "46": {
            "tier": TIER_UNVERIFIABLE,
            "landing": "upstream_inputs.task69_frontend_regression",
            "how": "bridge 状态封闭由 Task 69 独立断言；本门不重复造",
            "owner_task": "69",
        },
        "47": {
            "tier": TIER_UNVERIFIABLE,
            "landing": "pending_delete_landing.replacement_surface_unreachable_from_production_host",
            "how": (
                "19/22 替代面模块不可从生产宿主到达 ⇒ 「编辑器只消费 descriptor」在生产链上今天"
                "无处观测（BP-66-1，owner 67）"
            ),
            "owner_task": "67",
        },
        "48": {
            "tier": TIER_UNVERIFIABLE,
            "landing": "upstream_inputs.task69_frontend_regression",
            "how": "fail-open 文案禁令由 Task 69 独立断言；本门只引用其 verdict",
            "owner_task": "69",
        },
        "51": {
            "tier": TIER_PURE_LOGIC,
            "landing": "stage_a + stage_d.post_delete_five_zeros",
            "how": (
                "五个零的口径、vacuous zero 的不可采纳性、以及「Stage A 不得要求 unreachable=0」"
                "三件事全部由纯谓词现算并有正负例"
            ),
        },
        "57": {
            "tier": TIER_STRUCTURAL,
            "landing": "mutation_state_machine",
            "how": "变异脚本存在、四态词表齐备、`--check-anchors` 只读体检口存在",
        },
        "69": {
            "tier": TIER_UNVERIFIABLE,
            "landing": "required_scenario_execution",
            "how": f"3290 行 required scenario 中 {scenarios['executed_rows_recomputed']} 行执行过",
            "owner_task": "70",
        },
        "70": {
            "tier": TIER_UNVERIFIABLE,
            "landing": "required_scenario_execution.per_named_scenario",
            "how": "evidence 五表 0 行 ⇒ 「跨 entry 复用」在今天的分母上无处落脚",
            "owner_task": "70",
        },
        "71": {
            "tier": TIER_PURE_LOGIC,
            "landing": "stage_c.source_commit_unchanged_since_upstream_runs",
            "how": (
                "source commit 是 stale 轴的锁：本门把它排除在 VOLATILE_KEYS 之外，并现算 HEAD 与"
                "上游五份报告的 source commit 全等"
            ),
        },
        "72": {
            "tier": TIER_UNVERIFIABLE,
            "landing": "stage_d.final_gates.capacity",
            "how": "容量真实负载三条前提一条都不成立（BP-71-2，owner 72 → 环境）",
            "owner_task": "72",
        },
    }
    for number, row in rows.items():
        row["title"] = titles[number]
        row["tier"] = assert_property_tier(str(row["tier"]))
    missing = [str(n) for n in DECLARED_PROPERTIES if str(n) not in rows]
    extra = sorted(set(rows) - {str(n) for n in DECLARED_PROPERTIES})
    unverified_without_owner = sorted(
        number
        for number, row in rows.items()
        if row["tier"] == TIER_UNVERIFIABLE and not row.get("owner_task")
    )
    return {
        "declared_count": len(DECLARED_PROPERTIES),
        "landing_count": len(rows),
        "missing_landings": missing,
        "extra_landings": extra,
        "all_declared_have_landing": not missing and not extra,
        "tier_vocabulary": list(PROPERTY_TIERS),
        "tier_histogram": dict(Counter(row["tier"] for row in rows.values())),
        "rows": rows,
        "unverified_without_owner": unverified_without_owner,
        "every_unverified_has_owner": not unverified_without_owner,
        "verified_here_count": sum(
            1 for row in rows.values() if row["tier"] in (TIER_PURE_LOGIC, TIER_STRUCTURAL)
        ),
        "gate_can_go_green": arms["gate_can_go_green"],
    }


def build_mutation_state_machine() -> dict[str, Any]:
    """变异脚本的四态词表与只读体检口（AC 14.7）。"""
    script = REPO / MUTATE_REL
    present = script.is_file()
    source = read_text(script) if present else ""
    return {
        "mutation_script": MUTATE_REL,
        "mutation_script_present": present,
        "state_vocabulary": ["RED", "GREEN", "ANCHOR-MISS", "WRONG-TEST"],
        "state_semantics": {
            "RED": "打红且正是预期那条测试",
            "GREEN": "守卫缺陷 —— 改了行为却无判据变红；修守卫不删变异",
            "ANCHOR-MISS": "脚本缺陷 —— 锚点未命中或命中 >1（含 CRLF 下的跨行锚点）",
            "WRONG-TEST": "打红了但不是预期项 —— 污染残留或锚点错行",
        },
        "script_has_check_anchors": "--check-anchors" in source,
        "script_reads_and_writes_bytes": "read_bytes" in source and "write_bytes" in source,
        "script_collects_errors_too": "-rfE" in source,
        "error_counts_as_hit": True,
        "why_bytes_not_text": (
            "`read_text` 做换行翻译 ⇒ 写回时 `\\n` 变 `\\r\\n`，逐文件 md5 复原校验必失败（表现为"
            " RestoreFailed 而文件其实没坏）。"
        ),
        "exit_code_is_not_evidence": (
            "只看退出码会把 GREEN / ANCHOR-MISS / WRONG-TEST 三态全误判成 RED。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §16 上游锁影响 + 辐射面
# ════════════════════════════════════════════════════════════════════════════


def upstream_lock_impact() -> dict[str, Any]:
    """本门产物对上游四把锁的影响（两条既存/新发现的锁脆弱性，如实转记）。

    两条各自独立、由**不同的产物**触发，因此分成两个字段：

    * **BP-71-8（既存，owner 70）** —— Task 70 的锁含 `backend/tests` **全树** test 文件计数；
      本门新增守卫文件必然再顶它一次（该锁在本门动手前已是红的）。
    * **BP-72-8（本门新发现，owner 67）** —— Task 67 的锁含 `inbound_obligations` 普查，扫
      `backend/data/**` 与源码里对「Task 67」的引用；本门的**报告 JSON** 一落盘就被算进去
      （12 → 13 行）。已用移出/放回法隔离：移出 rc=0、放回 rc=1。
    """
    t70 = read_json(T70_REPORT)
    t70_surface = t70.get("radiation_surface") or {}
    scanned_live = sum(1 for _ in (BACKEND / "tests").rglob("test_*.py"))
    t71 = read_json(T71_REPORT)
    t71_impact = t71.get("upstream_lock_impact") or {}
    t67 = read_json(T67_REPORT)
    t67_inbound = [str(row.get("path")) for row in (t67.get("inbound_obligations") or [])]
    return {
        "statement": (
            "Task 70 的逐字节锁把 `backend/tests` **全树**的 test 文件计数锁进比对 ⇒ 仓库任意位置"
            "新增一个 `test_*.py` 都让它 stale。本门新增守卫必然再顶它一次。"
        ),
        "known_defect_id": "BP-71-8",
        "known_defect_owner_task": "70",
        "disposition": "如实登记，不改上游产物、不为让它变绿而绕过它",
        "task67_inbound_census": {
            "new_defect_id": "BP-72-8",
            "owner_task": "67",
            "statement": (
                "Task 67 的 `collect_inbound_obligations` 普查 `backend/data/**` 与源码里对自己的"
                "引用并把结果锁进逐字节比对 ⇒ 任何新落盘的、正文提到 Task 67 的产物都会顶掉它。"
                "本门的报告 JSON 就是这样的产物。"
            ),
            "rows_on_disk": len(t67_inbound),
            "this_gate_report_is_in_the_census": rel(OUTPUT_PATH) not in t67_inbound,
            "isolation_method": (
                "把本门报告 JSON 临时移出 `backend/data/` 再跑 Task 67 那两条测试：移出 rc=0、"
                "放回 rc=1 ⇒ 该红只由本门产物的存在引起，与 Task 67 自身漂移无关。"
            ),
            "affected_tests": [
                "test_task67_structural_pre_reconcile.py::TestInboundObligationsAndBlockingPreconditions::test_inbound_scan_recomputes_and_contains_the_real_targets",
                "test_task67_structural_pre_reconcile.py::TestGeneratorIsIdempotentAndCheckIsStrict::test_check_matches_the_file_on_disk",
            ],
            "why_not_fixed_here": (
                "重跑 Task 67 的 `--write` 就是重生成上游产物（Task 66/70 正文明令禁止，且会让"
                "Task 70 的 evidence 全部 stale）。改本门报告的落盘位置只是把普查躲开一次，"
                "下一个产物还会踩 —— 该修的是那条普查判据本身。"
            ),
            "same_class_as": "BP-71-8（全树普查进逐字节锁），但是**另一把锁、另一个 owner**",
        },
        "task71_own_lock": {
            "statement": (
                "Task 71 自有的那把锁也被顶红 2 条：它把 Task 70 的全树 test 计数 live 值"
                "（`upstream_lock_impact.task70_scanned_test_files_live`）写进了自己的逐字节锁 ⇒ "
                "本门新增守卫让那个 live 值 +1，它随之 stale。"
            ),
            "owner_task": "71",
            "affected_tests": [
                "test_task71_chaos_gate.py::TestReportIsFreshAndByteLocked::test_gate_check_passes",
                "test_task71_chaos_gate.py::TestGuardPlacement::test_upstream_lock_impact_is_measured_and_owned",
            ],
            "isolation_method": (
                "把本门守卫 + 报告一起临时移出再跑那两条：移出 rc=0、放回 rc=1 ⇒ 只由本门产物的"
                "存在引起。"
            ),
            "disposition": "如实登记，不改上游产物",
            "same_class_as": "BP-71-8（传递到 Task 71 自己的锁上）",
        },
        "task70_scanned_test_files_on_disk": t70_surface.get("scanned_test_files"),
        "task70_scanned_test_files_live": scanned_live,
        "task70_lock_already_red_before_this_gate": t71_impact.get(
            "task70_lock_goes_stale_because_of_this_gate"
        ),
        "task71_recorded_live_count": t71_impact.get("task70_scanned_test_files_live"),
        "baseline_locks": t71_impact.get("baseline_locks"),
        "known_preexisting_red": t71_impact.get("known_preexisting_red"),
        "why_unavoidable": (
            "`scanned_test_files` 是全树计数，与文件内容无关 ⇒ 换目录、不写模块路径字面量都躲不"
            "开。唯一的「规避」是不写守卫，那等于放弃本门的判据。"
        ),
        "guard_dir_is_outside_upstream_census_dirs": {
            "guard_dir": "backend/tests/workpaper_sync_predelete",
            "upstream_census_dir": "backend/tests/workpaper_sync",
            "outside": "workpaper_sync_predelete" != "workpaper_sync",
            "why": (
                "BP-69-6：Task 68 的逐字节锁把 `backend/tests/workpaper_sync/` 做成目录普查，往里"
                "新增文件会额外打红它 1~3 条。本门与 Tasks 69/70/71 一样自开目录。"
            ),
        },
    }


def radiation_surface() -> dict[str, Any]:
    """按引用关系反查本门的辐射面（不跑无边界全量）。"""
    subjects = (
        "check_task72_pre_delete_eligibility_gate",
        "workpaper_sync_task72_pre_delete_eligibility",
        "mutate_task72_pre_delete_eligibility_guards",
    )
    hits: dict[str, list[str]] = {}
    for path in (BACKEND / "tests").rglob("test_*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        matched = [subject for subject in subjects if subject in text]
        if matched:
            hits[rel(path)] = matched
    return {
        "how": "扫 `backend/tests` 全树里对本门三个产物名的实际引用（不是猜辐射面）",
        "subjects": list(subjects),
        "referencing_test_files": dict(sorted(hits.items())),
        "referencing_test_file_count": len(hits),
        "own_guard_included": GUARD_TEST_REL in hits,
        "digest": digest_of(sorted(hits.items())),
        "why_not_full_suite": (
            "`backend/tests` 根下 1500+ 测试文件，前台跑数分钟无输出会被当卡死；按引用关系反查是"
            "本 spec 的既定做法。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §17 阻塞清册
# ════════════════════════════════════════════════════════════════════════════


def build_blocking_points(
    *,
    stage_a: Mapping[str, Any],
    counts: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    landing: Mapping[str, Any],
    multi_resolver: Mapping[str, Any],
    environment: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """本门新发现 / 独立复核的阻塞点。

    🔴 id 用 **task-scoped 前缀** `BP-72-N`：实测 Tasks 63/64 的裁决记录各自登记过 `BP-16`~
    `BP-22`、同号不同义，全局单调编号在多会话并发下已被双重占用（Task 62 的教训）。
    """
    t71 = read_json(T71_REPORT)
    t71_bp = {str(bp.get("id")): bp for bp in (t71.get("blocking_points") or [])}
    t68 = read_json(T68_REPORT)
    t68_bp = {str(bp.get("id")): bp for bp in (t68.get("blocking_points") or [])}
    t66_bp = {
        str(bp.get("id")): bp for bp in (read_json(T66_REPORT).get("blocking_preconditions") or [])
    }

    return [
        {
            "id": "BP-72-1",
            "statement": (
                "真实 OO required scenario 一条都没真跑：逐行现算 "
                f"{scenarios['executed_rows_recomputed']} / "
                f"{scenarios['required_scenario_rows_recomputed']} 行落在已执行档；正文点名的 "
                f"{len(scenarios['named_scenarios_not_executed'])} / "
                f"{scenarios['named_required_scenario_count']} 个 scenario 全部未执行 ⇒ Stage A 红。"
            ),
            "measured": {
                "tier_histogram_recomputed": scenarios["tier_histogram_recomputed"],
                "named_scenarios_not_executed": scenarios["named_scenarios_not_executed"],
                "agrees_with_task70_self_report": scenarios["agrees_with_task70_self_report"],
            },
            "measured_how": (
                "Task 70 报告 `scenario_execution.entries[].scenarios[].execution_tier` 逐行现算，"
                "再与它的 `verdict.executed_end_to_end` 自述比对"
            ),
            "owner_task": "70",
            "disposition": "UNVERIFIABLE，保持未验收",
            "why_not_fixed_here": (
                "三条环境前提一条都不成立：3030 未监听、无 OO 活动编辑会话、evidence 五表 0 行。"
                "本门造 evidence 行等于伪造证据。"
            ),
            "relation_to_upstream": "与 BP-70-2 / BP-71-4 同一组环境前提",
        },
        {
            "id": "BP-72-2",
            "statement": (
                f"`multi_resolver` live 重算 = {multi_resolver['multi_resolver_count']}（≠0），"
                f"且 Task 12 矩阵那 {len(multi_resolver['rows_still_deferred'])} 条 resolver 行仍全部"
                " `status=deferred` ⇒ `legacy_delete` gate 不放行 Stage B 的全局 legacy 删除。"
            ),
            "measured": {
                "multi_resolver_rows_measured": multi_resolver["multi_resolver_rows_measured"],
                "rows_still_deferred": multi_resolver["rows_still_deferred"],
                "writer_gate_criteria": multi_resolver["writer_gate_criteria"],
            },
            "measured_how": "live 重算 writer matrix（不写盘）+ Task 12 矩阵逐行现读",
            "owner_task": "36",
            "adjudication_owner_task": "71",
            "disposition": "仍阻塞",
            "why_not_fixed_here": (
                "四条行的剩余阻塞是 Task 36 的逐 entry 供给；在任一 entry 拿到 approved bundle 之前"
                "改 router 会让全部底稿的 OO 入口 fail closed。"
            ),
            "relation_to_upstream": "BP-71-1 的独立复核（移交链 Task 20 → 30 → 71）",
        },
        {
            "id": "BP-72-3",
            "statement": (
                "「唯一命中 path/digest/owner/rollback plan」在 **rollback plan** 维度不成立："
                f"{landing['subjects_failing']} 个待删 subject `recoverable_from_git=false`（路径 "
                f"{landing['paths_untracked_at_plan_commit']} 在 plan commit 上未跟踪），且 "
                f"{landing['replacement_surface_untracked_live_count']} /"
                f" {landing['replacement_surface_total']} 个替代面模块 git 未跟踪 ⇒ Task 66 的"
                " rollback 隔离门 verdict = "
                f"{landing['task66_rollback_isolation_verdict']}。"
            ),
            "measured": {
                "failing_subjects": landing["failing_subjects"],
                "paths_untracked_at_plan_commit": landing["paths_untracked_at_plan_commit"],
                "replacement_surface_untracked_live_count": landing[
                    "replacement_surface_untracked_live_count"
                ],
                "task66_rollback_isolation_failing_checks": landing[
                    "task66_rollback_isolation_failing_checks"
                ],
            },
            "measured_how": (
                "逐 subject 现算五个绑定 + 磁盘 sha256 + `git ls-tree <plan_commit>`；替代面逐模块"
                " `git ls-files --error-unmatch` 现测"
            ),
            "owner_task": "72",
            "disposition": "仍阻塞（解除动作 = 把替代面与 usePilotBridgeAdapter.ts 入库）",
            "why_not_fixed_here": (
                "替代面入库属各推进方的产物归属，不该由本门替别人 commit；且入库会改 source commit，"
                "让 Task 70 的 evidence 全部 stale。"
            ),
            "relation_to_upstream": f"BP-66-2（owner 72）+ BP-66-1（owner 67）的独立复核",
            "upstream_bp_present": sorted(t66_bp),
        },
        {
            "id": "BP-72-4",
            "statement": (
                "`evidence stale = 0` 是空分母下的 vacuous zero，不能当成「已刷新」："
                "`evidence_stale_is_measurable` 逐 entry 现算 = "
                f"{counts['denominators']['evidence_stale_denominator']}，"
                "`working_paper_sync_test_run` = "
                f"{counts['denominators']['sync_test_run_rows_measured_by_task70']} 行。"
            ),
            "measured": counts["admissibility"]["evidence_stale"],
            "measured_how": "Task 67 逐 entry 现算分母 + Task 70 的 DB 行数现读，喂 `count_admissibility`",
            "owner_task": "70",
            "disposition": "如实登记 —— 判据已把它算成不可采纳，不是遗漏",
            "why_not_fixed_here": (
                "分母要靠真实 OO 场景产生 test run 行才会非空；这是 Task 70 的职责。"
            ),
            "relation_to_upstream": (
                "Task 67 已把该分母为空显式写出并交给 Task 70；本门只是把它变成**不可采纳**而不是"
                "一个看起来已达标的 0。"
            ),
        },
        {
            "id": "BP-72-5",
            "statement": (
                "本门新增守卫文件让 Task 70 的全树 test 文件计数锁再次 stale（既存脆弱性，不是本门"
                "引入的缺陷）。Task 71 已把它登记为 BP-71-8 并实测过隔离法。"
            ),
            "measured": {
                "task70_scanned_test_files_on_disk": (read_json(T70_REPORT).get(
                    "radiation_surface"
                ) or {}).get("scanned_test_files"),
                "upstream_bp_present": "BP-71-8" in t71_bp,
            },
            "measured_how": "现数 `backend/tests` 全树 `test_*.py` 并与 Task 70 报告登记值比对",
            "owner_task": "70",
            "disposition": "如实登记，不改上游产物",
            "why_not_fixed_here": (
                "改 Task 70 的产物即重生成上游 evidence（禁止）；把守卫挪出 `backend/tests` 会让它"
                "不进 CI。两害相权取如实登记。"
            ),
            "relation_to_upstream": "BP-71-8",
        },
        {
            "id": "BP-72-6",
            "statement": (
                "既存缺陷原样转记，不在本门顺手修：BP-71-3 / BP-68-1（`pre-durable rejected + "
                "application_id` 同时通过 DDL 与 `assert_delivery_ownership` 不变量，owner 22）、"
                "BP-70-6（Task 69 四把锁里的 1 红）、BP-71-5（磁盘 writer inventory stale，owner 20）。"
            ),
            "measured": {
                "task71_bp_ids": sorted(t71_bp),
                "task68_bp_ids": sorted(t68_bp),
                "inventory_on_disk_is_stale": multi_resolver["inventory_on_disk_is_stale"],
            },
            "measured_how": "上游报告的 blocking_points 逐条现读 + inventory digest 现算比对",
            "owner_task": "22",
            "disposition": "引用既存登记，本门零改动",
            "why_not_fixed_here": (
                "修它们要改生产代码或重生成上游基线文件 ⇒ 改 source commit ⇒ Task 70 的 evidence "
                "全部 stale 并打红上游四把锁。"
            ),
            "relation_to_upstream": "BP-68-1 / BP-71-3 / BP-71-5 / BP-70-6",
        },
        {
            "id": "BP-72-7",
            "statement": (
                "Stage C / Stage D 的最终门与容量真实负载今天无从供给：3030 未监听"
                f"（现测 {environment['frontend_3030_listening']}）、无 OO 活动编辑会话、"
                "evidence 五表全 0 行。"
            ),
            "measured": {
                "frontend_3030_listening": environment["frontend_3030_listening"],
                "onlyoffice_8080_listening": environment["onlyoffice_8080_listening"],
                "all_evidence_tables_empty": environment["all_evidence_tables_empty"],
                "missing_preconditions": environment["missing_preconditions"],
            },
            "measured_how": "socket 现测三个端口 + Task 70 的 DB 行数现读",
            "owner_task": "72",
            "disposition": "UNVERIFIABLE / BLOCKED，如实登记",
            "why_not_fixed_here": (
                "8080 healthcheck 通不等于有活动编辑会话（forcesave 对不存在 doc key 回 error 1）。"
                "合成 measurement 不能冒充容量门通过 —— 生产 `capacity_profile` 就是为防这件事写的。"
            ),
            "relation_to_upstream": "BP-71-2 / BP-70-2",
        },
        {
            "id": "BP-72-8",
            "statement": (
                "**本门新发现**：Task 67 的逐字节锁把 `inbound_obligations` 普查（扫 "
                "`backend/data/**` 与源码里对「Task 67」的引用）锁了进去 ⇒ 任何新落盘且正文提到"
                " Task 67 的产物都会顶掉它。本门报告 JSON 一落盘，该普查 12 → 13 行，Task 67 的锁"
                "多出 2 条红。与 BP-71-8 同类（全树普查进逐字节锁），但是**另一把锁、另一个 owner**。"
            ),
            "measured": {
                "task67_inbound_rows_on_disk": len(
                    (read_json(T67_REPORT).get("inbound_obligations") or [])
                ),
                "task67_affected_tests": 2,
                "task71_affected_tests": 2,
                "isolation": "两把锁各自「移出 rc=0 / 放回 rc=1」",
            },
            "measured_how": (
                "现跑 Task 67 生成器的 `collect_inbound_obligations()` 与磁盘清单求差集，"
                "再用移出/放回法隔离那两条测试"
            ),
            "owner_task": "67",
            "disposition": "如实登记，不改上游产物",
            "why_not_fixed_here": (
                "重跑 Task 67 的 `--write` 即重生成上游产物（明令禁止，且会让 Task 70 的 evidence "
                "全部 stale）；把报告挪到别的目录只是躲开一次普查，下一个产物还会踩 —— 该修的是那"
                "条普查判据本身。"
            ),
            "relation_to_upstream": "BP-71-8 的同类（不同锁）",
        },
    ]


# ════════════════════════════════════════════════════════════════════════════
# §18 verdict / 报告 / CLI
# ════════════════════════════════════════════════════════════════════════════


def _scan_forbidden_keys(node: Any, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if str(key) in FORBIDDEN_RECORD_KEYS:
                hits.append(here)
            hits.extend(_scan_forbidden_keys(value, here))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            hits.extend(_scan_forbidden_keys(item, f"{path}[{index}]"))
    return hits


def build_verdict(report: Mapping[str, Any]) -> dict[str, Any]:
    stage_a = report["stage_a"]
    stage_b = report["stage_b"]
    stage_c = report["stage_c"]
    stage_d = report["stage_d"]
    arms = report["counterfactual_arms"]
    forward = report["forward_recompute"]
    properties = report["properties"]
    counts = report["five_counts"]
    scenarios = report["required_scenario_execution"]

    structural_errors: list[str] = []
    if not report["task_declarations"]["properties_match"]:
        structural_errors.append("声明的 Property 与 tasks.md 正文不符")
    if not counts["all_recomputes_agree"]:
        structural_errors.append("五类计数的逐 entry 现算与 Task 67 自述不符")
    if not scenarios["agrees_with_task70_self_report"]:
        structural_errors.append("required scenario 逐行现算与 Task 70 自述不符")
    if not forward["all_agree"]:
        structural_errors.append(f"正向重算不一致: {forward['disagreeing_cases']}")
    if not arms["gate_can_go_green"]:
        structural_errors.append("全绿输入下本门仍不返回 green —— 门恒红，无信息量")
    if not arms["every_predicate_alone_can_turn_it_red"]:
        structural_errors.append("存在不参与结论的谓词 —— additive 死判据")
    if not properties["all_declared_have_landing"]:
        structural_errors.append("有声明 Property 没有落位")
    if not properties["every_unverified_has_owner"]:
        structural_errors.append("有 UNVERIFIABLE Property 没点名 owner")
    if not stage_a["vocabulary_check"]["excludes_unreachable_zero"]:
        structural_errors.append("Stage A 词表里出现了 unreachable-zero 语义（AC 12.13 禁止）")
    if not stage_b["self_ast_boundary"]["no_delete_primitive"]:
        structural_errors.append("本门源码里出现删除原语")
    if not stage_b["self_ast_boundary"]["write_calls_only_output_path"]:
        structural_errors.append("本门写盘目标不止 OUTPUT_PATH")
    if not stage_b["non_execution_proof"]["disk_matches_plan_digest_everywhere"]:
        structural_errors.append("待删对象的磁盘内容与 plan 登记 digest 不符（可能已被改动）")
    # out-of-band 登记本身必须站得住：登记一条还在盘上的路径、或一条计划外路径，都是给假绿开后门。
    out_of_band = stage_b.get("out_of_band_removals") or {}
    for row in out_of_band.get("invalid_records") or []:
        structural_errors.append(
            f"out-of-band 移除登记核验失败：{row.get('path')} {row.get('problems')}"
        )
    forbidden = _scan_forbidden_keys(
        {key: value for key, value in report.items() if key != "verdict"}
    )
    if forbidden:
        structural_errors.append(f"报告里出现禁止键: {forbidden}")

    return {
        "state": "stage_a_red",
        "state_vocabulary": ["stage_a_red", "stage_a_green_stage_b_pending", "archived"],
        "stage_a": stage_a["state"],
        "stage_b": stage_b["state"],
        "stage_c": stage_c["state"],
        "stage_d": stage_d["state"],
        "stage_a_failing_predicates": stage_a["failing_predicates"],
        "stage_a_owner_tasks": stage_a["owner_tasks_of_failing"],
        "task_72_completable": False,
        "structural_error_count": len(structural_errors),
        "structural_errors": structural_errors,
        "forbidden_record_keys_found": forbidden,
        "gate_can_go_green": arms["gate_can_go_green"],
        "legacy_delete_gate_released": False,
        "means": (
            "Stage A 八条谓词里 "
            f"{stage_a['failing_predicate_count']} 条为假 ⇒ 红。Stage B 未执行且有磁盘反证；"
            "Stage C 触发条件不成立（source commit 未变）；Stage D 的六个最终门"
            "**因 Stage A 红而未运行**，静默 skip 计数为 0。Task 72 不可完成。"
        ),
        "forbidden_claims": stage_a["forbidden_claims"],
        "what_is_not_claimed": [
            "不宣称任何真实 OO probe 已通过",
            "不宣称已删除任何 legacy",
            "不宣称五个零已达成",
            "不宣称已归档",
        ],
    }


def strip_volatile(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {
            key: strip_volatile(value)
            for key, value in node.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(node, list):
        return [strip_volatile(item) for item in node]
    return node


def build_report() -> dict[str, Any]:
    started = time.time()
    head = git_head()

    counts = build_five_counts()
    scenarios = build_required_scenario_execution()
    environment = build_environment_preconditions()
    landing = build_pending_delete_landing()
    multi_resolver = build_multi_resolver_live()

    stage_a = build_stage_a(
        counts=counts,
        scenarios=scenarios,
        landing=landing,
        multi_resolver=multi_resolver,
        head_commit=head,
    )
    plan_items = [
        item
        for item in (read_json(T66_REPORT).get("items") or [])
        if str(item.get("disposition")) == "pending_delete"
    ]
    out_of_band = validate_out_of_band_removals(
        pending_paths=[str(item.get("path")) for item in plan_items],
        plan_items=plan_items,
    )
    stage_b = build_stage_b(
        stage_a_state_value=str(stage_a["state"]),
        landing=landing,
        out_of_band=out_of_band,
    )
    stage_c = build_stage_c(
        stage_b=stage_b, head_commit=head, environment=environment, scenarios=scenarios
    )
    stage_d = build_stage_d(stage_a=stage_a, counts=counts, landing=landing)
    arms = build_counterfactual_arms(stage_a)

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "spec": SPEC,
        "task": f"{TASK_NUMBER}. 执行真正 pre-delete eligibility、删除全局 legacy、post-delete 全场景重验与归档",
        "wave": 7,
        "owner_task": OWNER_TASK,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_commit": head,
        "generated_by": GATE_REL,
        "why_this_gate_only_runs_stage_a": (
            "Stage A 为红 ⇒ Stage B 一个字节都不许删，Stage C 的触发条件（source commit 变化）不"
            "成立，Stage D 的最终门不运行。本门把 Stage A 的每条判据做成可复跑的纯谓词 + 现算事实，"
            "并对 Stage B/C/D 如实登记 BLOCKED / UNVERIFIABLE，而不是留空。"
        ),
        "sub_bullets": dict(SUB_BULLETS),
        "task_declarations": task_declarations(),
        "design_property_titles": design_property_titles(),
        "requirement_clauses": requirement_clauses(),
        "upstream_inputs": upstream_inputs(),
        "five_counts": counts,
        "required_scenario_execution": scenarios,
        "environment_preconditions": environment,
        "pending_delete_landing": landing,
        "multi_resolver_live": multi_resolver,
        "stage_a": stage_a,
        "stage_b": stage_b,
        "stage_c": stage_c,
        "stage_d": stage_d,
        "counterfactual_arms": arms,
        "forward_recompute": build_forward_recompute(),
        "mutation_state_machine": build_mutation_state_machine(),
        "upstream_lock_impact": upstream_lock_impact(),
        "radiation_surface": radiation_surface(),
        "upstream_artifacts_untouched": {
            "statement": "上游六份报告只读消费，本门零改动。",
            "digests": {rel(path): sha256_file(path) for path in UPSTREAM_REPORTS},
            "why": (
                "重生成上游产物会改 source commit ⇒ Task 70 的 evidence 全部 stale 并打红上游四把"
                "锁（BP-71-5 已踩过）。发现上游缺陷只登记 BP，不改文件。"
            ),
        },
    }
    report["properties"] = build_property_landings(
        stage_a=stage_a, counts=counts, scenarios=scenarios, landing=landing, arms=arms
    )
    report["blocking_points"] = build_blocking_points(
        stage_a=stage_a,
        counts=counts,
        scenarios=scenarios,
        landing=landing,
        multi_resolver=multi_resolver,
        environment=environment,
    )
    report["artifact_git_status"] = git_porcelain(
        [GATE_REL, rel(OUTPUT_PATH), GUARD_TEST_REL, MUTATE_REL]
    )
    report["verdict"] = build_verdict(report)
    report["elapsed_seconds"] = round(time.time() - started, 2)
    report["report_digest"] = digest_of(strip_volatile(report))
    return report


def render(report: Mapping[str, Any]) -> str:
    return stable_json(report, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="任务 72 Stage A 门：真正 pre-delete eligibility"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="重新采集并写出报告")
    mode.add_argument("--check", action="store_true", help="逐字节比对现算与盘上报告")
    args = parser.parse_args(argv)

    report = build_report()
    if args.write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(render(report), encoding="utf-8")
        verdict = report["verdict"]
        print(
            f"[任务72] 已写出 {rel(OUTPUT_PATH)}；Stage A={verdict['stage_a']}"
            f"（失败谓词 {len(verdict['stage_a_failing_predicates'])} 条）"
            f"；Stage B={verdict['stage_b']}；Stage C={verdict['stage_c']}"
            f"；Stage D={verdict['stage_d']}"
            f"；结构错误 {verdict['structural_error_count']} 条"
        )
        for pid in verdict["stage_a_failing_predicates"]:
            owner = report["stage_a"]["predicate_detail"][pid]["owner_task"]
            print(f"  · {pid}  owner=Task {owner}")
        for line in verdict["structural_errors"]:
            print(f"  🔴 {line}")
        return 0

    if not OUTPUT_PATH.is_file():
        print(f"[任务72] {rel(OUTPUT_PATH)} 不存在 —— 先跑 --write", file=sys.stderr)
        return 2
    on_disk = json.loads(read_text(OUTPUT_PATH))
    live = strip_volatile({k: v for k, v in report.items() if k != "report_digest"})
    disk = strip_volatile({k: v for k, v in on_disk.items() if k != "report_digest"})
    if live == disk:
        print(f"[任务72] --check 通过：{rel(OUTPUT_PATH)} 与现算逐字节一致")
        return 0
    diffs = [
        key for key in sorted(set(live) | set(disk)) if live.get(key) != disk.get(key)
    ]
    print(
        f"[任务72] 现算结果与 {rel(OUTPUT_PATH)} 不一致 —— 报告已过期或被手改；"
        f"不一致的顶层键: {diffs}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
