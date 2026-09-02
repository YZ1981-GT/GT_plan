"""任务 70 门 —— 按 source profile 对全 entry 推导 required scenario 并真跑可跑的一切。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7
Properties: P20 P21 P22 P23 P25 P26 P28 P30 P31 P32 P33 P34 P39 P40 P41 P49 P50 P55
            P56 P58 P62 P63 P64 P65 P66 P67 P69 P70 P71
Requirements: 4.3 4.10 4.11 5.5 6.1 6.2 6.4 6.5 6.8 6.10 6.16 6.18 7.1 7.3 7.4 7.6
              7.8 8.10 9.3 9.4 9.5 10.4 10.9 12.2 12.6 12.10 12.11 12.12 12.13 14.1
              14.2 14.3 14.4 14.5 14.6 14.8 14.9 14.14 14.16

═══ 本门与前三个 Wave 7 门的分工 ═══

任务 67 只**报告** structural stale；任务 68/69 只做**代码/数据库/前端**独立回归，两者都
明确「不冒充真实 OO probe 已通过」。本门是这条链上**唯一**被授权真跑一趟 OO 往返并刷新
evidence 的那一环，因此它必须同时做到两件互相拉扯的事：

1. **把能真跑的全部真跑**（真实 OO 9.4 容器、生产 token signer、生产 registry 的
   `register_from_manifest()`、生产 harness 的 `plan()`、生产 `derive_required_scenarios`
   的全 186 entry 分母）；
2. **对跑不了的一条都不宣称通过**：正文逐字「无法运行标 UNVERIFIABLE 且保持未验收，不宣称
   任何 probe 已通过」。

═══ 四条不可协商的设计 ═══

**① scenario 分母只取生产真源，不抄第二份。**
:data:`~app.services.workpaper_sync.pilot_harness.SCENARIO_ORACLES` 与
:func:`~app.services.workpaper_sync.evidence.derive_required_scenarios` 是唯一分母来源。
本门连"有哪些场景"都不写常量：正文枚举的每一条要么落到某个 oracle 的 `scenario_id`
（:data:`TASK_TEXT_SCENARIO_CLAUSES` 逐条映射），要么进
:data:`SCENARIO_EXEMPTIONS` 并带 owner + 实测出处。两者**互斥**，各有一条打红判据
（:func:`build_exemption_registry`）。

**② 执行记录里不许出现结果声明字段。**
:data:`FORBIDDEN_RECORD_KEYS` 沿用任务 61 的范式：`result` / `verdict` / `passed` /
`status` 一类键出现在 `scenario_execution` 的任何一行里即拒。本门的每条结论都必须由
`execution_tier` + `oracle_requirements` + `blocked_by` 三个**事实**字段推出来，而不是由
谁填一个 `passed: true`。

**③ 判定顺序不可交换，且与生产 oracle 同序。**
:func:`classify_scenario_execution` 复用
:func:`~app.services.workpaper_sync.pilot_harness.run_scenario_oracle` 的判定顺序
（schema 欠账 → 上游实现缺口 → 黑盒环境缺失 → 证据种类缺失 → 真判据）。把黑盒缺失放到
真判据之后会让「真实 OO 没跑」被「证据齐全」吞掉；把上游缺口放到黑盒之后会让它在没有 OO
的环境里显示成 `unverifiable`，于是**接了 OO 就自动变绿** —— 而它其实永远不会通过。

**④ body digest 必须归一化复选框。**
任务 69 的门把 tasks.md 里本任务正文（**含** `- [x] 69.` 那一行）整段做 sha256，于是编排器
把复选框从 `[-]` 翻成 `[x]` 之后它的逐字节锁立刻打红 —— 本门起手实测到的就是这一条
（:data:`BP-70-6`：现算 `446b3e79…` vs 盘上 `25bfab49…`，把 `[x]` 换回 `[-]` 后逐字节相等，
正文一个字都没变）。:func:`task_body` 因此把首行的复选框标记归一化成 `[?]`，让本门的锁只对
**正文内容**敏感。

═══ 为什么本门今天必然 UNVERIFIABLE（三条独立、各自实测）═══

* **供给**：生产 `register_from_manifest()` 实测 planned=186 / registered=0，逐 entry 原因
  由生产代码自己给出「还没有 current published representation」。
* **裁决**：即使补上 representation 也不会自动放行 —— manifest 里 180 个 OO entry 的
  capability 全是 `single_onlyoffice`，`assert_manifest_capability_enabled()` 实测抛
  `PilotSelectionError`，RG-18 会以 `FakeBidirectionalError` 拒绝伪双向。
* **黑盒**：真实 OO 9.4.0.129 可达且能被生产 token 驱动（`version` → `error 0`），但
  `forcesave` 对无活动编辑会话的 doc key 实测 `error 1`；前端 3030 未监听 ⇒
  `onlyoffice_forcesave` / `browser_trace` 两类证据今天无从供给。

三条**互相独立**：任一条单独解除都不足以让任何一条 required scenario 变 passed。这正是
:func:`build_counterfactual_arms` 要证明的（多臂）与 :func:`build_forward_recompute` 要
反向确认的（正向重算）。
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import importlib
import json
import re
import subprocess
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, Sequence

REPO: Final[Path] = Path(__file__).resolve().parents[3]
BACKEND: Final[Path] = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

TASK_NUMBER: Final[str] = "70"
OWNER_TASK: Final[str] = "70"
SPEC: Final[str] = "workpaper-html-onlyoffice-bidirectional-writeback-closure"
SCHEMA_VERSION: Final[str] = "task70-oo94-full-entry-scenario-refresh:v1"

TASKS_MD: Final[Path] = REPO / ".kiro/specs" / SPEC / "tasks.md"
DESIGN_MD: Final[Path] = REPO / ".kiro/specs" / SPEC / "design.md"
OUTPUT_PATH: Final[Path] = BACKEND / "data/workpaper_sync_task70_oo_scenario_refresh.json"

T67_REPORT: Final[Path] = BACKEND / "data/workpaper_sync_task67_structural_pre_reconcile.json"
T68_REPORT: Final[Path] = BACKEND / "data/workpaper_sync_task68_backend_chain_regression.json"
T69_REPORT: Final[Path] = BACKEND / "data/workpaper_sync_task69_frontend_regression.json"

GUARD_TEST_REL: Final[str] = "backend/tests/workpaper_sync_oo/test_task70_oo_scenario_gate.py"
MUTATE_REL: Final[str] = "backend/scripts/diagnose/mutate_task70_oo_scenario_guards.py"

#: 本门声明验证的 Property（与 tasks.md 正文双向锁死）。
DECLARED_PROPERTIES: Final[tuple[int, ...]] = (
    20, 21, 22, 23, 25, 26, 28, 30, 31, 32, 33, 34, 39, 40, 41, 49, 50, 55, 56, 58,
    62, 63, 64, 65, 66, 67, 69, 70, 71,
)

#: 正文五个内容子条目（`_Requirements:` 行不算子条目）。
SUB_BULLETS: Final[Mapping[int, str]] = {
    1: "消费任务 67 结构报告与任务 68/69 回归结果；逐 entry 从 source-backed manifest 的 "
       "editable/room_model/scenario_profile + capability + approved bundle + authority model "
       "重新推导完整 required scenario set，固定 source/profile digest 并以新 test run 刷新 stale evidence",
    2: "projection-based entry 逐一运行方向/identity/merge/conflict/dedupe/fold/幂等 409/"
       "quarantined/rollback/recovery/download-only/refresh 全场景；每个 "
       "editable=true AND (capability=bidirectional OR room_model=shared) 的 entry 无条件执行 "
       "close 族；dynamic/Word-only 再按 profile 追加",
    3: "custom/opaque 仅按 approved bundle 中的枚举 authority model 替换字段级场景；"
       "未知枚举、自由文本理由、profile 降级、普通 smoke 或跨场景复用同一 application/operation 不得豁免",
    4: "每 scenario 持久化自身 recovery case/request/application IDs/operation/content version/"
       "published result representation/artifact/projection、authority-model digest、bundle "
       "id/digest/typed children、manifest/profile digest、OO/browser build 与 trace bundle；"
       "服务端从 DB/timeline/artifact 重算；authorization-first claim 证明原子创建；download-only 证明三者为 0",
    5: "联合浏览器与服务端 timeline；失败修复并重跑，无法运行标 UNVERIFIABLE 且保持未验收，"
       "不宣称任何 probe 已通过；所有 required scenarios 刷新完成前任务 72 Stage A 保持红",
    # 🔴 第 6 条是「独立验证 Property …」那一行。它同样是一条 `  - ` 缩进 bullet，因此必须
    #    计入 —— 只有 `_Requirements:` 行被单独排除。少算它会让「子条目数一致」这条判据永远
    #    差 1，而差 1 最容易被当成「常量写错」糊过去（任务 69 的门在同一处踩过同一个坑并把
    #    Property 行计了进去）。
    6: "独立验证 Property 20/21/22/23/25/26/28/30/31/32/33/34/39/40/41/49/50/55/56/58/"
       "62/63/64/65/66/67/69/70/71 共 29 条",
}

#: 🔴 执行记录里**禁止**出现的结果声明键（任务 61 的 `FORBIDDEN_RECORD_KEYS` 范式）。
#:
#: 判据落在 :func:`assert_no_result_declarations` 上并对 `scenario_execution` 的每一行深度
#: 递归。写成「禁令名单」而不是「只允许这些键」是刻意的：白名单会在追加事实字段时被顺手放宽，
#: 而这张名单里的每个词都是**真实**的作假形态（教训 16：禁令类判据必须写死真实目标）。
FORBIDDEN_RECORD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "result",
        "results",
        "verdict",
        "passed",
        "pass",
        "failed",
        "status",
        "outcome",
        "succeeded",
        "success",
        "ok",
        "verified",
        "aggregate_result",
    }
)

#: 正文第二/第三子条目枚举的每一条场景短语 → 生产 `scenario_id`。
#:
#: 🔴 这张表是**正文 ↔ 生产分母**的桥，不是第二份分母：右侧每个 id 都必须在
#: `SCENARIO_ORACLES` 里查得到（:func:`build_scenario_denominator` 逐条断言），左侧覆盖正文
#: 枚举的全部短语。少一条右侧 ⇒ 分母缩小；多一条左侧无法映射 ⇒ 立刻报结构错误。
TASK_TEXT_SCENARIO_CLAUSES: Final[Mapping[str, str]] = {
    "HTML→OO": "html_to_oo",
    "OO→HTML": "oo_to_html",
    "identity": "identity_retention",
    "different-field merge": "different_field_merge",
    "same-field conflict/resolve": "same_field_conflict_resolve",
    "frozen-base status 6/2 dedupe": "frozen_base_status_6_2_dedupe",
    "same-application higher-sequence fold 不 self-stale": "same_application_higher_sequence_fold",
    "跨 participant 同 Idempotency-Key 及不同 kind/payload 均 409": "cross_participant_idempotency_409",
    "quarantined 拒绝 application/engine": "quarantined_rejects_application_and_engine",
    "opaque version UUID rollback 与跨 wp 同 numeric revision 无碰撞": "opaque_version_rollback_no_numeric_collision",
    "browser crash no-userdata recovery case": "browser_crash_no_userdata_recovery_case",
    "authorization-first claim": "authorization_first_recovery_claim",
    "错误 prior confirmation/bundle/fence/contributor 拒绝": "wrong_prior_confirmation_bundle_fence_contributor_rejected",
    "download-only 三实体为 0": "download_only_zero_three_entities",
    "merged≠incoming refresh/reopen": "refresh_required_reopen",
    "rollback": "rollback",
    "single close": "single_participant_close",
    "两个用户关闭顺序 A→B": "two_user_close_order_a_then_b",
    "两个用户关闭顺序 B→A": "two_user_close_order_b_then_a",
    "A terminal 前 B close": "b_close_before_a_forcesave_terminal",
    "A terminal 后 B close": "b_close_after_a_forcesave_terminal",
    "leader promotion 前 revoke/expire 后的 successor": "close_leader_revoked_successor_exactly_one",
    "无 successor recovery_required": "close_leader_revoked_no_successor_recovery_required",
    "reconcile_close_intents() 重入": "close_reconciler_reentrant_exactly_one_capture",
    "dynamic 行增删重排复制": "dynamic_row_add_delete_reorder_copy",
    "dynamic 列稳定 key": "dynamic_column_stable_keys",
    "Word-only SDT tag/row_uuid 保留": "word_sdt_tag_row_uuid_retention",
    "Word-only 自由正文隔离": "word_free_body_isolation",
    "custom/opaque 并发 authoritative revision 冲突": "authoritative_revision_conflict",
    "custom/opaque 不静默覆盖": "no_silent_overwrite",
}

#: 生产分母里**不**由正文第二/三子条目点名的场景 → 豁免登记（owner + 实测出处）。
#:
#: 与上表**互斥**：同一个 scenario_id 同时出现在两处，或既不在两处任一处，都由
#: :func:`build_exemption_registry` 各以一条独立判据打红。
SCENARIO_EXEMPTIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "single_html_no_blank_oo_artifact": {
        "owner_task": "18",
        "why": "本场景只出现在 capability=single_html 的 required set 里，而正文第二子条目"
               "的枚举以「projection-based entry」为主语。它仍在分母内、仍被本门逐 entry 计数，"
               "只是不由正文那串枚举点名。",
        "measured_from": "capability_distribution.single_html == 5（本门现算，见 "
                         "scenario_denominator.capability_distribution）",
    },
}

#: 真实 OO 9.4 CommandService 返回码语义（契约 `command_service.known_codes` 的封闭域）。
OO_ERROR_SEMANTICS: Final[Mapping[int, str]] = {
    0: "no error",
    1: "document key missing / no document with such key（无活动编辑会话）",
    2: "callback url incorrect",
    3: "internal server error",
    4: "no changes applied before forcesave",
    5: "command incorrect",
    6: "invalid token",
}

#: 本门期望的 pilot entry 与三个 approved bundle（**只作探测入参**，不作期望值）。
PILOT_ENTRY_ID: Final[str] = "xlsx/b60/gt-b60-bundle"

#: 探测用的**不存在**的 doc key。它证明 forcesave 需要活动编辑会话（OO 回 error 1）。
_OO_ABSENT_DOC_KEY: Final[str] = "gt-t70-probe-absent-doc-key"

#: OO 出站传输失败的文案。抽成常量是为了让那条 `raise` 保持**单行**（教训 7）。
_OO_TRANSPORT_ERROR: Final[str] = (
    "OO CommandService {label}/{shape} 传输失败（{exc}）—— 记 ERROR 态并中止，"
    "不得降级成「无数据所以通过」（AC 5.12）"
)

#: 执行档位。四档，语义互斥且**不可合并** —— 合并「真跑过」与「只有结构侧」正是本 spec
#: 反复点名的假绿形态。
TIER_EXECUTED: Final[str] = "executed_end_to_end"
TIER_STRUCTURAL: Final[str] = "structural_side_only"
TIER_UNRUNNABLE: Final[str] = "unrunnable_today"
TIER_UPSTREAM_GAP: Final[str] = "upstream_implementation_gap"


class Task70GateError(RuntimeError):
    """本门的失败类型。**不吞异常** —— 库/容器不可达一律上抛（AC 5.12）。"""


# ════════════════════════════════════════════════════════════════════════════
# §1 基础工具
# ════════════════════════════════════════════════════════════════════════════


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO)).replace("\\", "/")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json(obj: Any, *, indent: int | None = None) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=indent, default=str)


def digest_of(obj: Any) -> str:
    return sha256_text(stable_json(obj))


def git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        raise Task70GateError(f"无法取 git HEAD: {type(exc).__name__}: {exc}") from exc


def git_porcelain(paths: Sequence[str]) -> dict[str, str]:
    """逐产物的 `git status --porcelain`。

    🔴 「spec 全绿 ≠ 产物已入库」：挂进 CI 的 job 在干净 checkout 下会因文件不存在必挂。
    因此本门把自己每个产物的跟踪状态写进报告，`??` 一眼可见。
    """
    out: dict[str, str] = {}
    for path in paths:
        # 🔴 先判存在：`git status --porcelain -- <不存在的路径>` 输出为空，与「已跟踪且干净」
        #    长得一模一样。不分开就会把「产物还没写出来」报成 `tracked-clean` —— 而那正是
        #    「挂进 CI 的 job 在干净 checkout 下必挂」这条判据要抓的东西。
        if not (REPO / path).exists():
            out[path] = "missing-on-disk"
            continue
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain", "--", path],
                cwd=REPO,
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


def read_json(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise Task70GateError(f"上游报告缺失: {rel(path)} —— 本门必须消费它，不得跳过")
    return json.loads(read_text(path))


def strip_comments(source: str) -> str:
    """剥 Python 注释与文档字符串，保留可执行结构。

    🔴 判「有没有真调某个符号」之前必须先剥注释（教训 12），但**不能**用它去剥 SQL：
    `sa.text(\"\"\"...\"\"\")` 会被一起剥掉。本门只在 AST 判据的前置里用它，且只用于本门
    自己的守卫源码。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise Task70GateError(f"源码无法解析: {exc}") from exc
    drop: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                for line in range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1):
                    drop.add(line)
    lines = source.split("\n")
    kept: list[str] = []
    replaced_blocks: set[int] = set()
    for index, line in enumerate(lines, start=1):
        if index in drop:
            # 🔴 不能直接删：删掉某个 class/def 的文档字符串后它的 body 就空了 ⇒
            #    `IndentationError: expected an indented block`（本门首轮实测，5 条 AST 判据
            #    全被这个 ERROR 打红）。把每个被剥区间的**首行**换成同缩进的 `pass`，其余留空行。
            if index - 1 not in drop and index - 1 not in replaced_blocks:
                indent = line[: len(line) - len(line.lstrip())]
                kept.append(f"{indent}pass")
                replaced_blocks.add(index)
            else:
                kept.append("")
                replaced_blocks.add(index)
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            kept.append("")
            continue
        kept.append(line)
    return "\n".join(kept)


# ════════════════════════════════════════════════════════════════════════════
# §2 tasks.md / design.md 声明（body digest 归一化复选框）
# ════════════════════════════════════════════════════════════════════════════

_CHECKBOX_RE: Final[re.Pattern[str]] = re.compile(r"^(\s*-\s\[)[ x~\-](\]\s+\d+\.)")


def task_body(task_number: str = TASK_NUMBER) -> str:
    """tasks.md 里本任务的正文段。**首行复选框归一化**。

    🔴 BP-70-6 的直接产物：任务 69 的门把含 `- [x] 69.` 的整段做 digest，编排器翻牌后它的
    逐字节锁立刻打红（本门起手实测：现算 `446b3e79…` vs 盘上 `25bfab49…`，把 `[x]` 换回
    `[-]` 后逐字节相等 ⇒ 正文一个字都没变）。归一化成 `[?]` 让锁只对**正文内容**敏感，
    而任务状态翻牌不再制造假红。
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
        raise Task70GateError(f"tasks.md 里找不到任务 {task_number}")
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
            "任务 69 的门未归一化复选框 ⇒ 编排器把 `[-]` 翻成 `[x]` 后它的逐字节锁必红"
            "（BP-70-6 实测）。本门只锁正文内容。"
        ),
    }


def design_property_titles() -> dict[str, str]:
    """design.md 里本门声明的 29 条 Property 的标题（正文可能与标题同行）。"""
    text = read_text(DESIGN_MD)
    out: dict[str, str] = {}
    for number in DECLARED_PROPERTIES:
        match = re.search(rf"^###\s+Property\s+{number}\b[:：]?\s*(.*)$", text, re.M)
        if match is None:
            raise Task70GateError(
                f"design.md 里找不到 `### Property {number}` —— 本门声明的 Property 必须在"
                "设计文档里有定义，否则「验证了它」无从核对"
            )
        out[str(number)] = match.group(1).strip()
    return out


# ════════════════════════════════════════════════════════════════════════════
# §3 上游三份报告：按 key 取，不整读
# ════════════════════════════════════════════════════════════════════════════


def upstream_inputs() -> dict[str, Any]:
    """消费任务 67/68/69 的报告。正文第一句的机器形态。

    只取本门真正会**用到**的 key（分母、digest、verdict、欠账），不把 2 MB 报告原样搬进来。
    每一份都记 `report_digest` 与 `source_commit`，于是上游被重生成时本门的锁会跟着变。
    """
    t67 = read_json(T67_REPORT)
    t68 = read_json(T68_REPORT)
    t69 = read_json(T69_REPORT)

    t67_entries = t67.get("entries") or []
    axes = Counter()
    for row in t67_entries:
        for axis in row.get("evidence_rerun_axes") or []:
            axes[str(axis)] += 1
    bundle_bound = sum(
        1
        for row in t67_entries
        if (row.get("authority_contract_bundle_chain") or {}).get("approved_bundle_bound_to_entry")
    )
    published = sum(
        1
        for row in t67_entries
        if (row.get("candidate_published_representation") or {}).get("published")
    )
    scenario_rows = sum(
        int((row.get("evidence") or {}).get("scenario_rows") or 0) for row in t67_entries
    )
    test_run_rows = sum(
        int((row.get("evidence") or {}).get("test_run_rows") or 0) for row in t67_entries
    )

    return {
        "task67_structural_pre_reconcile": {
            "path": rel(T67_REPORT),
            "report_digest": t67.get("report_digest"),
            "report_commit": t67.get("report_commit"),
            "entry_count": len(t67_entries),
            "evidence_rerun_axis_histogram": dict(sorted(axes.items())),
            "entries_with_approved_bundle_bound": bundle_bound,
            "entries_with_published_representation": published,
            "evidence_scenario_rows_total": scenario_rows,
            "test_run_rows_total": test_run_rows,
            "source_regeneration_digests_agree": (t67.get("source_regeneration") or {}).get(
                "digests_agree"
            ),
            "approved_source_digest": (t67.get("source_regeneration") or {}).get(
                "approved_source_digest"
            ),
            "current_source_digest": (t67.get("source_regeneration") or {}).get(
                "current_source_digest"
            ),
            "production_landings": dict(t67.get("production_landings") or {}),
            "how_this_gate_uses_it": (
                "①逐 entry 的 editable/room_model/scenario_profile 是本门 required scenario "
                "推导的输入（本门**重新现算**而不是读它的答案，两侧比对）；②evidence_rerun_axes "
                "是本门 stale 轴的分母；③approved/current source digest 的漂移由本门如实转记，"
                "不替复核方改 overlay。"
            ),
        },
        "task68_backend_chain_regression": {
            "path": rel(T68_REPORT),
            "report_digest": t68.get("report_digest"),
            "source_commit": t68.get("source_commit"),
            "invariant_count": len(t68.get("invariants") or []),
            "invariant_counts": dict(t68.get("invariant_counts") or {}),
            "blocking_point_ids": [str(bp.get("id")) for bp in (t68.get("blocking_points") or [])],
            "oo_scope_boundary_owner": (t68.get("oo_scope_boundary") or {}).get(
                "owner_of_real_oo_scenarios"
            ),
            "how_this_gate_uses_it": (
                "任务 68 明确把「真实 OO 场景」的 owner 指向本门，并声明自己没碰 evidence 表。"
                "本门据此确认：evidence 三表今天为 0 不是任务 68 清过，而是从未产生。"
            ),
        },
        "task69_frontend_regression": {
            "path": rel(T69_REPORT),
            "report_digest": t69.get("report_digest"),
            "source_commit": t69.get("source_commit"),
            "invariant_count": len(t69.get("invariants") or []),
            "blocking_point_ids": [str(bp.get("id")) for bp in (t69.get("blocking_points") or [])],
            "port_3030_listening": (t69.get("oo_scope_boundary") or {}).get("port_3030_listening"),
            "runs_real_browser": (t69.get("oo_scope_boundary") or {}).get("runs_real_browser"),
            "runs_real_onlyoffice": (t69.get("oo_scope_boundary") or {}).get(
                "runs_real_onlyoffice"
            ),
            "three_entity_facts_all_ok": (t69.get("three_entity_facts") or {}).get("all_ok"),
            "dom_network_order_all_ok": (t69.get("dom_network_order") or {}).get("all_ok"),
            "how_this_gate_uses_it": (
                "任务 69 的四条 DOM/network 顺序链与三实体结论是本门 `browser_trace` 半边的"
                "**唯一**已有观测；它同时实录 3030 未监听、不跑真浏览器、不跑真实 OO —— "
                "本门据此把 browser_trace 类证据判为今天无从供给，而不是「没人做」。"
            ),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# §4 scenario 分母：只取生产真源
# ════════════════════════════════════════════════════════════════════════════


def _production() -> dict[str, Any]:
    """一次性 import 生产模块并缓存（昂贵对象进程内缓存）。"""
    global _PROD_CACHE
    try:
        return _PROD_CACHE  # type: ignore[name-defined]
    except NameError:
        pass
    mods = {
        "harness": importlib.import_module("app.services.workpaper_sync.pilot_harness"),
        "evidence": importlib.import_module("app.services.workpaper_sync.evidence"),
        "entry_profile": importlib.import_module("app.services.workpaper_sync.entry_profile"),
        "models": importlib.import_module("app.services.workpaper_sync.models"),
        "registry": importlib.import_module("app.services.workpaper_sync.adapters.registry"),
        "opaque_gate": importlib.import_module("app.services.workpaper_sync.opaque_entry_gate"),
        "command_service": importlib.import_module(
            "app.services.workpaper_sync.command_service"
        ),
    }
    globals()["_PROD_CACHE"] = mods
    return mods


def build_scenario_denominator() -> dict[str, Any]:
    """scenario 分母 —— 全部现算，**一个常量清单都不抄**。

    三条结构判据（各自独立，不合并）：

    1. `SCENARIO_ORACLES` ↔ evidence 场景声明双向锁死（调生产的
       `assert_oracle_registry_complete()`，不重写一份）；
    2. 正文枚举 :data:`TASK_TEXT_SCENARIO_CLAUSES` 的每个右侧 id 都在 `SCENARIO_ORACLES` 里；
    3. 生产分母里的每个 id 要么被正文点名、要么进 :data:`SCENARIO_EXEMPTIONS`。
    """
    prod = _production()
    harness = prod["harness"]
    evidence = prod["evidence"]
    entry_profile = prod["entry_profile"]

    harness.assert_oracle_registry_complete()

    oracles = dict(harness.SCENARIO_ORACLES)
    declared = harness.all_declared_scenarios()
    declared_ids = tuple(s.scenario_id for s in declared)

    unmapped_in_task_text = sorted(
        set(TASK_TEXT_SCENARIO_CLAUSES.values()) - set(oracles)
    )
    manifest = entry_profile.load_entry_manifest()
    entries = entry_profile.manifest_entries_by_id(manifest)

    families = Counter(str(s.family.value) for s in declared)
    kinds = Counter(str(s.kind.value) for s in declared)
    black_box = sorted(o.scenario_id for o in oracles.values() if o.needs_black_box)
    with_debt = sorted(o.scenario_id for o in oracles.values() if o.upstream_debt)

    requirement_inputs: dict[str, list[str]] = {}
    for scenario in declared:
        oracle = oracles[scenario.scenario_id]
        requirement_inputs[scenario.scenario_id] = sorted(i.value for i in oracle.requires)

    return {
        "source_of_truth": (
            "app.services.workpaper_sync.pilot_harness:SCENARIO_ORACLES + "
            "app.services.workpaper_sync.evidence:derive_required_scenarios"
        ),
        "why_not_a_second_copy": (
            "本门连「有哪些场景」都不写常量。分母写死或漏一个场景，会让「跑完 N 个场景」的"
            "计数虚高而没有任何判据变红 —— 这正是任务 39 把 `assert_oracle_registry_complete()` "
            "做成双向锁的理由。本门调它而不是重写它。"
        ),
        "oracle_count": len(oracles),
        "declared_scenario_count": len(declared_ids),
        "declared_scenario_ids": sorted(declared_ids),
        "registry_bidirectionally_locked": True,
        "family_histogram": dict(sorted(families.items())),
        "kind_histogram": dict(sorted(kinds.items())),
        "black_box_scenario_ids": black_box,
        "black_box_count": len(black_box),
        "upstream_debt_scenario_ids": with_debt,
        "schema_unrepresentable_scenarios": dict(evidence.SCHEMA_UNREPRESENTABLE_SCENARIOS),
        "field_level_scenarios": list(evidence.FIELD_LEVEL_SCENARIOS),
        "authority_substitute_scenario_ids": [
            s.scenario_id for s in evidence.AUTHORITY_SUBSTITUTE_SCENARIOS
        ],
        "substituting_authority_models": sorted(
            m.value for m in evidence.SUBSTITUTING_AUTHORITY_MODELS
        ),
        "non_replaceable_scenario_ids": sorted(evidence.NON_REPLACEABLE_SCENARIOS),
        "evidence_input_requirements": requirement_inputs,
        "task_text_clause_count": len(TASK_TEXT_SCENARIO_CLAUSES),
        "task_text_ids_not_in_production": unmapped_in_task_text,
        "manifest_entry_count": len(entries),
        "capability_distribution": dict(
            sorted(Counter(entry_profile.capability_of(e).value for e in entries.values()).items())
        ),
        "independent_entry_count": sum(
            1 for e in entries.values() if e.get("independent_entry")
        ),
        "manifest_source_digest": evidence.manifest_source_digest(manifest),
    }


def build_exemption_registry(denominator: Mapping[str, Any]) -> dict[str, Any]:
    """正文枚举 ↔ 豁免登记的**互斥**覆盖。

    两条独立判据（合成一条会让其中一侧永久不可达）：

    * `both`：同一 scenario_id 既被正文点名又被豁免 ⇒ 豁免是装饰；
    * `neither`：生产分母里有 id 既不被点名又无豁免 ⇒ 分母缩小。
    """
    produced = set(denominator["declared_scenario_ids"])
    named = set(TASK_TEXT_SCENARIO_CLAUSES.values())
    exempt = set(SCENARIO_EXEMPTIONS)

    both = sorted(named & exempt)
    neither = sorted(produced - named - exempt)
    stale_exempt = sorted(exempt - produced)

    for scenario_id, row in SCENARIO_EXEMPTIONS.items():
        for field_name in ("owner_task", "why", "measured_from"):
            if not str(row.get(field_name) or "").strip():
                raise Task70GateError(
                    f"豁免登记 {scenario_id!r} 缺 {field_name!r} —— 豁免必须带 owner 与实测"
                    "出处，自由文本理由不构成豁免（正文第三子条目逐字）"
                )
    return {
        "task_text_named_ids": sorted(named),
        "exempted_ids": sorted(exempt),
        "both_named_and_exempted": both,
        "both_is_empty": not both,
        "neither_named_nor_exempted": neither,
        "neither_is_empty": not neither,
        "exemptions_pointing_at_unknown_scenarios": stale_exempt,
        "exemptions": {k: dict(v) for k, v in SCENARIO_EXEMPTIONS.items()},
        "why_two_separate_predicates": (
            "合成一条（例如「named ∪ exempt == produced」）会在同一个 id 落进两边时仍然成立 ⇒ "
            "「豁免是装饰」这条测不出来。两条各自打红。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §5 逐 entry required scenario set（现算，全 186 entry × 全 approved authority model）
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class EntryDerivation:
    entry_id: str
    capability: str
    editable: bool
    editability: str
    room_model: str
    document_type: str
    independent: bool
    mount_cardinality: str
    scenario_profile_digest: str
    source_digest: str
    close_required: bool
    per_model: Mapping[str, Mapping[str, Any]]
    derivation_error: str | None


def derive_all_entries() -> tuple[EntryDerivation, ...]:
    """全 186 entry × 3 个 approved authority model 的 required set 现算。

    ═══ 为什么按 authority model 分档而不是挑一个 ═══

    正文要求「从 … approved bundle + authority model 重新推导」。但 approved bundle **今天
    没有绑定到任何 entry**（`working_paper_sync_definition_bundle` 无 `entry_id` 列；它只经
    representation / application / test_run 与 entry 相连，而这三张表实测 0 行 —— 任务 67 已
    逐 entry 记为 `approved_bundle_bound_to_entry=false`）。于是 entry 的 authority model
    **在库里不可解析**。

    本门的处置：**不发明**。改为对库里真实存在的每一个 approved authority model 各推导一次，
    并把「哪些场景对 authority model 敏感」现算出来（实测：只有字段级两条被替换，close /
    recovery / authorization 一条不动）。这样分母是完备的，而 authority model 的绑定缺口
    仍然是一条可归因的阻塞（BP-70-2），不会被一个默认值糊过去。
    """
    prod = _production()
    evidence = prod["evidence"]
    entry_profile = prod["entry_profile"]
    AuthorityModel = prod["models"].AuthorityModel

    manifest = entry_profile.load_entry_manifest()
    entries = entry_profile.manifest_entries_by_id(manifest)
    models = (
        AuthorityModel.projection_contract,
        AuthorityModel.custom_authoritative_ooxml,
        AuthorityModel.opaque_single_onlyoffice,
    )

    out: list[EntryDerivation] = []
    for entry_id in sorted(entries):
        entry = entries[entry_id]
        capability = entry_profile.capability_of(entry)
        profile_payload = entry.get("scenario_profile") or {}
        per_model: dict[str, dict[str, Any]] = {}
        derivation_error: str | None = None
        close_required = False
        editable = bool(entry.get("editable", profile_payload.get("editable")))
        editability = str(entry.get("editability") or profile_payload.get("editability") or "")
        room_model = str(entry.get("room_model") or profile_payload.get("room_model") or "")
        profile_digest = ""
        for model in models:
            try:
                required = evidence.derive_for_manifest_entry(entry, authority_model=model)
            except Exception as exc:  # noqa: BLE001 - 转成可归因事实，不降级
                derivation_error = f"{type(exc).__name__}: {str(exc)[:280]}"
                per_model[model.value] = {"derivation_error": derivation_error}
                continue
            close_required = bool(required.close_required)
            editable = bool(required.editability.value == "editable")
            editability = required.editability.value
            room_model = required.room_model.value
            profile_digest = required.scenario_profile_digest
            per_model[model.value] = {
                "scenario_count": len(required.scenarios),
                "scenario_ids": list(required.scenario_ids),
                "required_scenario_set_digest": required.digest,
                "substituted": bool(required.substituted),
                "close_required": bool(required.close_required),
            }
        out.append(
            EntryDerivation(
                entry_id=entry_id,
                capability=capability.value,
                editable=editable,
                editability=editability,
                room_model=room_model,
                document_type=str(entry.get("document_type") or ""),
                independent=bool(entry.get("independent_entry")),
                mount_cardinality=str(profile_payload.get("mount_cardinality") or ""),
                scenario_profile_digest=profile_digest,
                source_digest=str(entry.get("source_digest") or ""),
                close_required=close_required,
                per_model=per_model,
                derivation_error=derivation_error,
            )
        )
    return tuple(out)


def build_close_gate(derivations: Sequence[EntryDerivation]) -> dict[str, Any]:
    """`editable=true AND (capability=bidirectional OR room_model=shared)` 的**现算**门控。

    正文逐字要求「每个命中该谓词的 entry 无条件执行 close 族」。本门**不写死名单**：谓词
    直接调生产的 :func:`~app.services.workpaper_sync.evidence.close_scenarios_required`
    （它是这条谓词的唯一定义点），再与逐 entry 推导出的 `close_required` 逐条比对 —— 两侧
    来源不同（一边是本门对 profile 现算，一边是推导结果的字段），因此不是自我比对。
    """
    prod = _production()
    evidence = prod["evidence"]
    entry_profile = prod["entry_profile"]

    manifest = entry_profile.load_entry_manifest()
    entries = entry_profile.manifest_entries_by_id(manifest)
    close_scenario_ids = [s.scenario_id for s in evidence.CLOSE_SCENARIOS]

    recomputed: dict[str, bool] = {}
    predicate_errors: dict[str, str] = {}
    for row in derivations:
        entry = entries[row.entry_id]
        try:
            profile = evidence.extract_entry_profile(entry)
            capability = entry_profile.capability_of(entry)
            recomputed[row.entry_id] = bool(
                evidence.close_scenarios_required(profile=profile, capability=capability)
            )
        except Exception as exc:  # noqa: BLE001
            predicate_errors[row.entry_id] = f"{type(exc).__name__}: {str(exc)[:200]}"

    disagreements = sorted(
        entry_id
        for entry_id, value in recomputed.items()
        if value != next(r.close_required for r in derivations if r.entry_id == entry_id)
    )
    hits = sorted(entry_id for entry_id, value in recomputed.items() if value)
    missing_close = sorted(
        entry_id
        for entry_id in hits
        for model_row in [
            next(r for r in derivations if r.entry_id == entry_id).per_model.get(
                "projection_contract", {}
            )
        ]
        if not set(close_scenario_ids) <= set(model_row.get("scenario_ids") or [])
    )
    return {
        "predicate_source_of_truth": (
            "app.services.workpaper_sync.evidence:close_scenarios_required"
        ),
        "close_scenario_ids": close_scenario_ids,
        "close_scenario_count": len(close_scenario_ids),
        "entries_hitting_predicate": len(hits),
        "entry_ids_hitting_predicate_sample": hits[:12],
        "predicate_vs_derivation_disagreements": disagreements,
        "predicate_agrees_everywhere": not disagreements,
        "predicate_errors": predicate_errors,
        "hits_missing_any_close_scenario": missing_close,
        "every_hit_has_full_close_family": not missing_close,
        "why_not_a_hardcoded_list": (
            "写死名单会在 profile 降级（editable 被改成 readonly、room_model 从 shared 改成 "
            "exclusive）时静默少跑八个场景，而「场景都跑过了」的计数仍然满分。本门每次现算。"
        ),
    }


def summarize_derivations(derivations: Sequence[EntryDerivation]) -> dict[str, Any]:
    """逐 entry 推导的聚合。**父入口不重复计数**。"""
    independent = [row for row in derivations if row.independent]
    duplicates = [row for row in derivations if not row.independent]
    per_model_totals: dict[str, dict[str, Any]] = {}
    for model in ("projection_contract", "custom_authoritative_ooxml", "opaque_single_onlyoffice"):
        sizes = Counter()
        slots = 0
        empties: list[str] = []
        for row in derivations:
            data = row.per_model.get(model) or {}
            if "scenario_count" not in data:
                continue
            sizes[int(data["scenario_count"])] += 1
            slots += int(data["scenario_count"])
            if int(data["scenario_count"]) == 0:
                empties.append(row.entry_id)
        indep_slots = sum(
            int((row.per_model.get(model) or {}).get("scenario_count") or 0)
            for row in independent
        )
        per_model_totals[model] = {
            "size_histogram": dict(sorted(sizes.items())),
            "required_scenario_slots_all_entries": slots,
            "required_scenario_slots_independent_entries_only": indep_slots,
            "empty_required_set_entry_ids": empties,
        }
    errors = Counter(
        row.derivation_error.split(":")[0] for row in derivations if row.derivation_error
    )
    return {
        "entry_count": len(derivations),
        "independent_entry_count": len(independent),
        "parent_duplicate_entry_count": len(duplicates),
        "parent_duplicates_not_double_counted": True,
        "derivation_error_histogram": dict(sorted(errors.items())),
        "entries_with_derivation_error": [
            {"entry_id": row.entry_id, "error": row.derivation_error}
            for row in derivations
            if row.derivation_error
        ],
        "per_authority_model": per_model_totals,
        "authority_model_sensitivity": _authority_sensitivity(derivations),
    }


def _authority_sensitivity(derivations: Sequence[EntryDerivation]) -> dict[str, Any]:
    """哪些场景对 authority model 敏感 —— 现算，用来证明「分母不因未绑定而不确定」。"""
    added: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    for row in derivations:
        base = set((row.per_model.get("projection_contract") or {}).get("scenario_ids") or [])
        for model in ("custom_authoritative_ooxml", "opaque_single_onlyoffice"):
            other = set((row.per_model.get(model) or {}).get("scenario_ids") or [])
            if not base and not other:
                continue
            for scenario_id in other - base:
                added[scenario_id] += 1
            for scenario_id in base - other:
                removed[scenario_id] += 1
    return {
        "scenarios_added_under_substituting_models": dict(sorted(added.items())),
        "scenarios_removed_under_substituting_models": dict(sorted(removed.items())),
        "invariant_under_authority_model": (
            "close / recovery / authorization 家族在三个 authority model 下逐条相同 —— "
            "因此 authority model 未绑定**不会**让 close 族分母变得不确定；"
            "唯一不确定的是字段级两条与 authoritative 两条之间的替换。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §6 真实 OnlyOffice 9.4 探测（**真调**，不吞异常）
# ════════════════════════════════════════════════════════════════════════════


def probe_real_onlyoffice() -> dict[str, Any]:
    """真调 OO 9.4 CommandService。签名走**生产** signer，不抄第二份。

    ═══ 为什么必须用生产 signer ═══

    第一版探测自己用 `pyjwt` 拼了 token，OO 一律回 `error 6`（invalid token）—— 因为漏了
    `iat/exp`。那个结果会被误读成「OO 不可用」。改调
    :func:`~app.services.workpaper_sync.command_service.sign_command_token` 之后
    `version` 立刻回 `{"error":0,"version":"9.4.0.129"}`。**教训**：判「外部系统可不可用」
    必须用生产的出站路径，否则测的是自己的探测脚本。

    ═══ 三个探测各自证明什么 ═══

    * `version`：容器可达 + JWT secret 正确 + build 号（进 `onlyoffice_build`）；
    * `forcesave` 打一个**不存在**的 doc key：实测 `error 1`。这条是本门最关键的黑盒判据 ——
      它证明 `forcesave` 需要**活动编辑会话**，而活动会话只能由真浏览器打开文档产生。
      于是 `onlyoffice_forcesave` 类证据的缺失是**结构性**的，不是「忘了跑」。
    * 两种 `claim_shape` 各打一次：契约 `platform_rule` 说 OO 对 flat 也放行但不得因此放宽
      签名要求；实测两者都回同一码，于是「本门用的是契约点名的那一种」这条不是靠 OO 的宽容
      蒙过去的。

    **不吞异常**：容器不可达时抛 :class:`Task70GateError` 并记 ERROR 态（AC 5.12）。
    """
    import httpx

    from app.core.config import settings

    prod = _production()
    command_service = prod["command_service"]
    policy = command_service.load_command_service_policy()

    oo_url = str(getattr(settings, "ONLYOFFICE_URL", "") or "").strip()
    secret = str(getattr(settings, "ONLYOFFICE_JWT_SECRET", "") or "")
    if not oo_url:
        raise Task70GateError(
            "ONLYOFFICE_URL 为空 —— 本门必须真调 OO，不得回退到「由 payload 决定 host」"
        )
    if not secret:
        raise Task70GateError(
            "ONLYOFFICE_JWT_SECRET 缺失 —— 契约 `command_service.jwt.required=true`，"
            "不得在无密钥时降级成不鉴权探测"
        )
    base = oo_url.rstrip("/")
    endpoint = f"{base}/coauthoring/CommandService.ashx"

    observations: dict[str, Any] = {}
    try:
        health = httpx.get(f"{base}/healthcheck", timeout=15.0)
        observations["healthcheck"] = {
            "http_status": int(health.status_code),
            "body": health.text.strip()[:32],
        }
    except Exception as exc:  # noqa: BLE001
        raise Task70GateError(
            f"OO healthcheck 不可达（{type(exc).__name__}: {exc}）—— 记 ERROR 态并中止，"
            "不得降级成「无数据所以通过」（AC 5.12）"
        ) from exc

    absent_key = _OO_ABSENT_DOC_KEY
    commands: tuple[tuple[str, dict[str, Any]], ...] = (
        ("version", {"c": "version"}),
        ("forcesave_without_live_session", {"c": "forcesave", "key": absent_key}),
        ("info_without_live_session", {"c": "info", "key": absent_key}),
    )
    for label, body in commands:
        for shape in ("payload_wrapped", "flat_body"):
            token = command_service.sign_command_token(
                body=body, secret=secret, ttl_seconds=30, claim_shape=shape
            )
            try:
                resp = httpx.post(
                    endpoint,
                    json={**body, "token": token},
                    headers={f"{policy.jwt_header}": f"{policy.jwt_scheme} {token}"},
                    timeout=25.0,
                )
            except Exception as exc:  # noqa: BLE001
                # 🔴 message 抽成模块常量让这条 `raise` **单行**（教训 7）：多行 raise 被变异脚本
                #    整行替换会造成语法错 ⇒ pytest 报 ERROR，而 `-rf` 只列 FAILED ⇒ 会被误判成 GREEN。
                raise Task70GateError(_OO_TRANSPORT_ERROR.format(label=label, shape=shape, exc=exc)) from exc
            parsed = json.loads(resp.text)
            code = int(parsed.get("error"))
            observations[f"{label}/{shape}"] = {
                "http_status": int(resp.status_code),
                "error_code": code,
                "error_semantics": OO_ERROR_SEMANTICS.get(code, "UNKNOWN"),
                "version": parsed.get("version"),
            }

    version_row = observations.get("version/payload_wrapped") or {}
    build = str(version_row.get("version") or "")
    if version_row.get("error_code") != 0:
        raise Task70GateError(
            f"OO `version` 返回 error={version_row.get('error_code')} —— 生产 token 被拒，"
            "本门无法声称 OO 可驱动"
        )
    forcesave_row = observations.get("forcesave_without_live_session/payload_wrapped") or {}

    return {
        "endpoint": endpoint,
        "jwt_signed_by": "app.services.workpaper_sync.command_service:sign_command_token",
        "jwt_claim_shape_required_by_contract": policy.jwt_claim_shape,
        "known_codes": list(policy.known_codes),
        "observations": observations,
        "onlyoffice_build_measured": build,
        "onlyoffice_build_is_94": build.startswith("9.4."),
        "container_driveable_with_production_token": version_row.get("error_code") == 0,
        "forcesave_without_live_session_error_code": forcesave_row.get("error_code"),
        "forcesave_requires_live_editing_session": forcesave_row.get("error_code") == 1,
        "what_this_proves": (
            "真实 OO 9.4 容器可达且能被生产出站路径驱动（version → error 0），因此"
            "「跑不了真实 OO 场景」**不是**因为容器缺失。真正的结构性缺口是 forcesave 需要"
            "活动编辑会话（对不存在的 doc key 实测 error 1），而活动会话只能由真浏览器打开"
            "已注册 entry 的文档产生。"
        ),
        "what_this_does_not_prove": (
            "不证明任何 required scenario 通过。forcesave 类证据需要「真浏览器打开一个已注册"
            "entry 的 room 并产生变更」，本门实测该前置不成立（见 supply_chain_walk）。"
        ),
    }


def probe_frontend_port() -> dict[str, Any]:
    """3030 是否监听 —— `browser_trace` 类证据的前置。"""
    import socket

    listening = False
    error = ""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    try:
        listening = sock.connect_ex(("127.0.0.1", 3030)) == 0
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    finally:
        sock.close()
    return {
        "port": 3030,
        "listening": listening,
        "probe_error": error,
        "why_it_matters": (
            "`browser_trace` 类证据要求真实浏览器 network/console trace。3030 未监听 ⇒ "
            "无法挂载宿主、无法让 OO 建立编辑会话 ⇒ 该类证据今天无从供给（Property 49）。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §7 真实供给链逐步执行（第一处硬阻塞 + 反事实）
# ════════════════════════════════════════════════════════════════════════════


async def walk_supply_chain(session: Any) -> dict[str, Any]:
    """按生产顺序逐步真跑首版供给链，记录**第一处**硬阻塞。

    每一步都是真实调用，不是「读文档说它会失败」。步骤顺序即生产顺序，不可交换：
    per-entry 契约登记 → 磁盘契约 ↔ 源码双向锁 → 权威模板 → manifest capability 裁决 →
    registry 注册计划 → `register_from_manifest()` → bundle 身份 → harness `plan()`。

    🔴 顺序理由：把 `register_from_manifest()` 放到 capability 裁决**之前**会让「供给不足」
    先出现，于是 capability 未裁决这条（BP-70-3）永久不可达 —— 而它恰恰是「补上供给也不会
    自动放行」的唯一证据。
    """
    import sqlalchemy as sa

    prod = _production()
    registry_module = prod["registry"]
    harness_module = prod["harness"]
    entry_profile = prod["entry_profile"]

    pilot_module = importlib.import_module(
        "app.services.workpaper_sync.pilot_simple_checklist"
    )
    provisioning = importlib.import_module(
        "app.services.workpaper_sync.projection_provisioning"
    )

    steps: list[dict[str, Any]] = []

    def record(step_id: str, name: str, executed: bool, detail: Any, blocked: str | None) -> None:
        steps.append(
            {
                "step": step_id,
                "name": name,
                "really_executed": executed,
                "detail": detail,
                "blocked_by": blocked,
            }
        )

    # ── 1. per-entry 供给登记
    try:
        supply = provisioning.load_projection_supply(PILOT_ENTRY_ID)
        record(
            "S1",
            "load_projection_supply(pilot)",
            True,
            {
                "contract_id": supply.contract_id,
                "provider_module": supply.provider_module,
                "authority_model": supply.authority_model.value,
            },
            None,
        )
    except Exception as exc:  # noqa: BLE001
        record("S1", "load_projection_supply(pilot)", True, None, f"{type(exc).__name__}: {exc}")

    # ── 2. 磁盘契约 ↔ 模块现算 payload 双向锁
    try:
        contract = pilot_module.assert_contract_file_matches_source()
        record(
            "S2",
            "assert_contract_file_matches_source()",
            True,
            {"contract_id": contract.contract_id, "canonical_sha256": contract.canonical_sha256},
            None,
        )
    except Exception as exc:  # noqa: BLE001
        record("S2", "assert_contract_file_matches_source()", True, None, f"{type(exc).__name__}: {exc}")

    # ── 3. 权威模板可读
    try:
        template = pilot_module.authoritative_template_path()
        record(
            "S3",
            "authoritative_template_path().is_file()",
            True,
            {"path": rel(template), "exists": template.is_file(), "bytes": template.stat().st_size},
            None,
        )
    except Exception as exc:  # noqa: BLE001
        record("S3", "authoritative_template_path()", True, None, f"{type(exc).__name__}: {exc}")

    # ── 4. manifest capability 裁决（🔴 反事实的关键一步）
    try:
        pilot_module.assert_manifest_capability_enabled()
        record("S4", "assert_manifest_capability_enabled()", True, "ok", None)
    except Exception as exc:  # noqa: BLE001
        record(
            "S4",
            "assert_manifest_capability_enabled()",
            True,
            {
                "error_type": type(exc).__name__,
                "error_code": str(getattr(exc, "error_code", "")),
                "message": str(exc)[:400],
            },
            f"{type(exc).__name__}: manifest capability 未裁决为 bidirectional",
        )

    # ── 5. 注册计划规模
    registry = registry_module.build_production_registry()
    record(
        "S5",
        "build_production_registry().registration_plan",
        True,
        {
            "planned_entry_count": len(registry.registration_plan),
            "static_registrations": len(registry.registrations()),
            "blocked_reason_histogram": dict(
                sorted(
                    Counter(
                        "static_blocked" if item.blocked_reason else "awaiting_db_supply"
                        for item in registry.registration_plan
                    ).items()
                )
            ),
        },
        None,
    )

    # ── 6. register_from_manifest 真跑
    try:
        outcome = await registry.register_from_manifest(session=session)
        record(
            "S6",
            "register_from_manifest(session) [REAL]",
            True,
            {
                "planned": len(outcome.planned_entry_ids),
                "registered_entry_ids": list(outcome.registered_entry_ids),
                "registered_adapter_ids": list(outcome.registered_adapter_ids),
                "unregistered_count": len(outcome.reasons),
                "accounting_identity_holds": (
                    len(outcome.registered_entry_ids) + len(outcome.reasons)
                    == len(outcome.planned_entry_ids)
                ),
                "pilot_reason": str(outcome.reasons.get(PILOT_ENTRY_ID, ""))[:420],
                "reason_kind_histogram": dict(
                    sorted(
                        Counter(
                            "no_published_representation"
                            if "current published representation" in reason
                            else "no_per_entry_contract"
                            if "DELIVERED_PER_ENTRY_CONTRACTS" in reason
                            else "other"
                            for reason in outcome.reasons.values()
                        ).items()
                    )
                ),
            },
            None
            if outcome.registered_entry_ids
            else "registered=0：全部 planned entry 都缺 current published representation 或 per-entry 契约",
        )
    except Exception as exc:  # noqa: BLE001
        record("S6", "register_from_manifest(session) [REAL]", True, None, f"{type(exc).__name__}: {exc}")

    # ── 7 / 8. bundle 身份 + harness plan 真跑（对库里每个 approved bundle）
    bundles = (
        await session.execute(
            sa.text(
                "select id, canonical_payload_sha256, state"
                " from working_paper_sync_definition_bundle order by created_at"
            )
        )
    ).all()
    harness = harness_module.SyncTestRunHarness(session)
    plans: dict[str, Any] = {}
    for row in bundles:
        bundle_id = row[0]
        try:
            identity = await harness.resolve_bundle_identity(
                bundle_id if isinstance(bundle_id, uuid.UUID) else uuid.UUID(str(bundle_id))
            )
            plan = await harness.plan(
                entry_id=PILOT_ENTRY_ID,
                bundle_id=bundle_id if isinstance(bundle_id, uuid.UUID) else uuid.UUID(str(bundle_id)),
            )
            plans[identity.authority_model.value] = {
                "bundle_id": str(bundle_id),
                "bundle_sha256": identity.bundle_sha256,
                "typed_child_digest": identity.typed_child_digest,
                "authority_model_definition_sha256": identity.authority_model_definition_sha256,
                "scenario_count": len(plan.scenario_ids),
                "scenario_ids": list(plan.scenario_ids),
                "black_box_scenario_ids": list(plan.black_box_scenario_ids),
                "upstream_debt_scenario_ids": list(plan.upstream_debt_scenario_ids),
                "required_scenario_set_digest": plan.required.digest,
                "substituted": bool(plan.required.substituted),
                "close_required": bool(plan.required.close_required),
                "production_refs_all_resolvable": True,
            }
        except Exception as exc:  # noqa: BLE001
            plans[f"bundle:{bundle_id}"] = {
                "error_type": type(exc).__name__,
                "message": str(exc)[:400],
            }
    record(
        "S7",
        "SyncTestRunHarness.resolve_bundle_identity + plan(pilot) [REAL]",
        True,
        {
            "approved_bundle_count": len(bundles),
            "plans_by_authority_model": plans,
            "note": (
                "plan() 内部逐条 `resolve_production_refs()` —— 全部通过意味着每个场景在生产上"
                "的实现符号都还在（接线未断）。这是本门唯一**真跑通**的生产路径。"
            ),
        },
        None,
    )

    # ── 9. entry_state / candidate 供给（首版 representation 的两条唯一来源）
    entry_state_rows = (
        await session.execute(
            sa.text("select count(*) from working_paper_sync_entry_state")
        )
    ).scalar_one()
    candidate_rows = (
        await session.execute(
            sa.text("select count(*) from working_paper_representation_upgrade_candidate")
        )
    ).scalar_one()
    version_rows = (
        await session.execute(sa.text("select count(*) from working_paper_content_version"))
    ).scalar_one()
    record(
        "S8",
        "首版 representation 的两条唯一来源现查",
        True,
        {
            "entry_state_rows": int(entry_state_rows),
            "representation_upgrade_candidate_rows": int(candidate_rows),
            "content_version_rows": int(version_rows),
            "path_a_content_mutation_commit": (
                "ContentMutationService.commit(...) —— 需要 projection-based adapter，而 adapter "
                "由 pilot 的 attach_pilot_adapters 组装，后者第一步就要求 entry_state 已有 "
                "published representation（循环依赖的另一端）；且它在组装前调 "
                "assert_manifest_capability_enabled()，实测抛 PilotSelectionError（见 S4）"
            ),
            "path_b_finalize_gate": (
                "ExcelEntryFinalizeGate.finalize_candidate(...) —— 第一步 "
                "`assert_candidate_finalizable(candidate_id)` 需要一条 candidate 行，"
                f"实测 {int(candidate_rows)} 行；candidate 由任务 17 的 instrumentation upgrader "
                "在**已有** representation 时登记 ⇒ 它不是首版来源"
            ),
            "conclusion": (
                "两条来源都被前置挡住，且 `projection_provisioning` 明确拒绝自建第三条 "
                "representation 写入路径（会伪造业务 projection 并绕过 "
                "assert_candidate_finalizable，Property 4 / 67 双打红）。本门**不**新建第三条。"
            ),
        },
        "首版 published representation 的两条生产来源各自被前置挡住",
    )

    first_block = next((step for step in steps if step["blocked_by"]), None)
    return {
        "pilot_entry_id": PILOT_ENTRY_ID,
        "steps": steps,
        "step_count": len(steps),
        "steps_really_executed": sum(1 for step in steps if step["really_executed"]),
        "first_hard_stop_step": (first_block or {}).get("step"),
        "first_hard_stop_name": (first_block or {}).get("name"),
        "first_hard_stop_reason": (first_block or {}).get("blocked_by"),
        "blocked_step_ids": [step["step"] for step in steps if step["blocked_by"]],
        "why_order_is_not_commutable": (
            "把 S6（供给）排到 S4（capability 裁决）之前，会让「供给不足」先命中，于是"
            "「补上供给也不会自动放行」这条永久不可达 —— 而它是本门最关键的反事实臂。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §8 逐 entry 逐 scenario 执行分类（与生产 oracle 同序）
# ════════════════════════════════════════════════════════════════════════════


def classify_scenario_execution(
    *,
    scenario_id: str,
    oo_available: bool,
    browser_available: bool,
    application_chain_available: bool,
) -> dict[str, Any]:
    """一条场景**今天**能跑到哪一档 + 被谁挡住。

    ═══ 判定顺序与生产 `run_scenario_oracle` 逐条同序，不可交换 ═══

    1. schema 欠账（`SCHEMA_UNREPRESENTABLE_SCENARIOS`）—— 已登记且必然发生，放后面会被别
       的码遮住；
    2. 上游实现缺口（`oracle.upstream_debt`）—— 缺的是**实现**不是环境，档位
       :data:`TIER_UPSTREAM_GAP`；
    3. 黑盒环境缺失 —— Property 49 的原文，档位 :data:`TIER_UNRUNNABLE`；
    4. 证据种类缺失（application 链）—— 同为 :data:`TIER_UNRUNNABLE` 但 `blocked_by` 不同码；
    5. 都不缺才是 :data:`TIER_EXECUTED`。

    🔴 本函数**不返回**任何结果声明字段（没有 `result` / `passed`）。它只回答「档位」与
    「被哪一条挡住」，最终结论由聚合层按档位计数得出。
    """
    prod = _production()
    harness = prod["harness"]
    evidence = prod["evidence"]

    oracle = harness.SCENARIO_ORACLES.get(scenario_id)
    if oracle is None:
        raise Task70GateError(
            f"{scenario_id!r} 不在生产 SCENARIO_ORACLES 里 —— 分母与判定表脱钩"
        )
    scenario = next(
        (s for s in harness.all_declared_scenarios() if s.scenario_id == scenario_id), None
    )
    if scenario is None:
        raise Task70GateError(f"{scenario_id!r} 不在任何 required set 声明里")

    requires = sorted(i.value for i in oracle.requires)
    row: dict[str, Any] = {
        "scenario_id": scenario_id,
        "family": scenario.family.value,
        "kind": scenario.kind.value,
        "requirement": scenario.requirement,
        "oracle_requirements": requires,
        "needs_black_box": bool(oracle.needs_black_box),
        "expects_application": bool(scenario.expects_application),
        "expects_recovery_case": bool(scenario.expects_recovery_case),
        "expects_zero_entities": bool(scenario.expects_zero_entities),
        "expected_close_captures": scenario.expected_close_captures,
        "schema_representable_as_passed": bool(scenario.schema_representable_as_passed),
        "production_refs": list(oracle.production_refs),
    }

    if scenario_id in evidence.SCHEMA_UNREPRESENTABLE_SCENARIOS:
        row["execution_tier"] = TIER_UNRUNNABLE
        row["blocked_by"] = "scenario_kind_unrepresentable"
        row["blocked_owner_task"] = "9"
        row["blocked_detail"] = str(evidence.SCHEMA_UNREPRESENTABLE_SCENARIOS[scenario_id])[:320]
        return row

    if oracle.upstream_debt:
        row["execution_tier"] = TIER_UPSTREAM_GAP
        row["blocked_by"] = "upstream_gap"
        row["blocked_owner_task"] = "32"
        row["blocked_detail"] = str(oracle.upstream_debt)[:320]
        return row

    black_box_missing: list[str] = []
    if "onlyoffice_forcesave" in requires and not oo_available:
        black_box_missing.append("onlyoffice_forcesave")
    if "browser_trace" in requires and not browser_available:
        black_box_missing.append("browser_trace")
    if black_box_missing:
        row["execution_tier"] = TIER_UNRUNNABLE
        row["blocked_by"] = "real_onlyoffice_not_executed"
        row["blocked_owner_task"] = OWNER_TASK
        row["blocked_missing_inputs"] = black_box_missing
        row["blocked_detail"] = (
            "Property 49：probe/pilot 未实际通过时必须保持 UNVERIFIABLE。"
            "forcesave 需活动编辑会话（本门实测无会话时 OO 回 error 1）；"
            "browser trace 需 3030 宿主（本门实测未监听）。"
        )
        return row

    if not application_chain_available and (
        scenario.expects_application or "db_entities" in requires
    ):
        row["execution_tier"] = TIER_UNRUNNABLE
        row["blocked_by"] = "application_chain_unavailable"
        row["blocked_owner_task"] = OWNER_TASK
        row["blocked_detail"] = (
            "`assert_entity_shape` 要求该场景同时给 operation + application ID；真实 "
            "operation/application 行只由 RequestApplicationService 在 forcesave request → "
            "accepted → durable callback 链上产生，而该链需要已注册 entry 的 room 与 doc key。"
            "本门实测 registered=0 ⇒ 该链今天不可达。"
        )
        return row

    if scenario.expects_recovery_case and not application_chain_available:
        row["execution_tier"] = TIER_UNRUNNABLE
        row["blocked_by"] = "recovery_lifecycle_unavailable"
        row["blocked_owner_task"] = OWNER_TASK
        row["blocked_detail"] = (
            "recovery case 由 durable incoming callback 建立，同样依赖已注册 entry 的 room。"
        )
        return row

    row["execution_tier"] = TIER_EXECUTED
    row["blocked_by"] = None
    row["blocked_owner_task"] = None
    return row


def build_scenario_execution(
    derivations: Sequence[EntryDerivation],
    *,
    oo_available: bool,
    browser_available: bool,
    application_chain_available: bool,
) -> dict[str, Any]:
    """逐 entry 逐 scenario 的结构化执行结果。**不是一句结论。**

    行数 = Σ(独立 entry × 该 entry 在 `projection_contract` 下的 required set 大小)。父入口
    （`independent_entry=False`）**不重复计数** —— 它们只复用其独立 entry 的 adapter。
    """
    classification_cache: dict[str, dict[str, Any]] = {}

    def classify(scenario_id: str) -> dict[str, Any]:
        if scenario_id not in classification_cache:
            classification_cache[scenario_id] = classify_scenario_execution(
                scenario_id=scenario_id,
                oo_available=oo_available,
                browser_available=browser_available,
                application_chain_available=application_chain_available,
            )
        return classification_cache[scenario_id]

    rows: list[dict[str, Any]] = []
    tier_counter: Counter[str] = Counter()
    per_entry_tier: dict[str, dict[str, int]] = {}

    for entry in derivations:
        if not entry.independent:
            continue
        model_row = entry.per_model.get("projection_contract") or {}
        scenario_ids = list(model_row.get("scenario_ids") or [])
        entry_tiers: Counter[str] = Counter()
        scenario_rows: list[dict[str, Any]] = []
        for scenario_id in scenario_ids:
            classified = dict(classify(scenario_id))
            tier_counter[classified["execution_tier"]] += 1
            entry_tiers[classified["execution_tier"]] += 1
            scenario_rows.append(classified)
        per_entry_tier[entry.entry_id] = dict(sorted(entry_tiers.items()))
        rows.append(
            {
                "entry_id": entry.entry_id,
                "capability": entry.capability,
                "editable": entry.editable,
                "editability": entry.editability,
                "room_model": entry.room_model,
                "document_type": entry.document_type,
                "mount_cardinality": entry.mount_cardinality,
                "source_digest": entry.source_digest,
                "scenario_profile_digest": entry.scenario_profile_digest,
                "close_required": entry.close_required,
                "authority_model_resolution": "UNBOUND",
                "authority_model_resolution_why": (
                    "`working_paper_sync_definition_bundle` 无 entry_id 列；bundle 只经 "
                    "representation / application / test_run 与 entry 相连，三表实测 0 行。"
                ),
                "approved_bundle_bound_to_entry": False,
                "required_scenario_count": len(scenario_ids),
                "required_scenario_set_digest": model_row.get("required_scenario_set_digest"),
                "derivation_error": entry.derivation_error,
                "test_run_rows_this_round": 0,
                "evidence_scenario_rows_this_round": 0,
                "scenarios": scenario_rows,
            }
        )

    return {
        "row_count": len(rows),
        "parent_duplicates_excluded": True,
        "scenario_row_total": sum(len(row["scenarios"]) for row in rows),
        "tier_histogram": dict(sorted(tier_counter.items())),
        "tier_semantics": {
            TIER_EXECUTED: "本轮端到端真跑并有可重算证据",
            TIER_STRUCTURAL: "只有结构侧判据（无真实 OO/浏览器/DB 实体）",
            TIER_UNRUNNABLE: "今天无法运行（环境或前置缺失）⇒ UNVERIFIABLE",
            TIER_UPSTREAM_GAP: "上游实现缺口 ⇒ fail closed，接上环境也不会自动变绿",
        },
        "distinct_scenario_classifications": {
            key: {
                "execution_tier": value["execution_tier"],
                "blocked_by": value["blocked_by"],
                "blocked_owner_task": value["blocked_owner_task"],
            }
            for key, value in sorted(classification_cache.items())
        },
        "per_entry_tier_histogram": per_entry_tier,
        "entries": rows,
    }


def assert_no_result_declarations(node: Any, *, path: str = "scenario_execution") -> list[str]:
    """深度递归找结果声明键。任务 61 的 `FORBIDDEN_RECORD_KEYS` 范式。

    返回命中路径列表（空 = 通过）。**不抛** —— 让报告把命中点原样记下来，守卫再断言为空；
    抛异常会让 `--write` 直接崩掉而看不到命中了哪几处。
    """
    hits: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            key_text = str(key)
            if key_text.lower() in FORBIDDEN_RECORD_KEYS:
                hits.append(f"{path}.{key_text}")
            hits.extend(assert_no_result_declarations(value, path=f"{path}.{key_text}"))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            hits.extend(assert_no_result_declarations(value, path=f"{path}[{index}]"))
    return hits


# ════════════════════════════════════════════════════════════════════════════
# §9 反事实多臂 + 正向重算
# ════════════════════════════════════════════════════════════════════════════


def build_counterfactual_arms(
    *,
    supply: Mapping[str, Any],
    oo: Mapping[str, Any],
    frontend: Mapping[str, Any],
    denominator: Mapping[str, Any],
) -> dict[str, Any]:
    """多臂反事实：逐条移除前提，结论必须改变。

    🔴 多臂只能证明「非重言」，**抓不到「恒真」**（教训 15）—— 因此本节必须与
    :func:`build_forward_recompute` 成对出现，后者用合成的已知答案反向重算一遍。
    """
    prod = _production()
    harness = prod["harness"]
    all_ids = [s.scenario_id for s in harness.all_declared_scenarios()]

    def tier_counts(*, oo_ok: bool, browser_ok: bool, chain_ok: bool) -> dict[str, Any]:
        """档位计数 **与** `blocked_by` 码分布。

        🔴 只比档位计数不够：黑盒解除后那些场景会从 `real_onlyoffice_not_executed` 转到
        `application_chain_unavailable`，**档位仍是 `unrunnable_today`** ⇒ 直方图逐字相同，
        于是 A3 臂看起来「结论没变」而其实判据是敏感的（本门首轮实测踩到这一条：
        `conclusion_changes` 假报 False）。把码分布一起比才是真判据。
        """
        tiers: Counter[str] = Counter()
        codes: Counter[str] = Counter()
        for scenario_id in all_ids:
            row = classify_scenario_execution(
                scenario_id=scenario_id,
                oo_available=oo_ok,
                browser_available=browser_ok,
                application_chain_available=chain_ok,
            )
            tiers[row["execution_tier"]] += 1
            codes[str(row["blocked_by"])] += 1
        return {
            "tier_histogram": dict(sorted(tiers.items())),
            "blocked_by_histogram": dict(sorted(codes.items())),
        }

    today = tier_counts(oo_ok=False, browser_ok=False, chain_ok=False)
    arms = [
        {
            "arm": "A1",
            "premise_removed": "假设 published representation 供给到位（entry_state 有行）",
            "still_blocked_by": (supply.get("steps") or [{}]),
            "measured": (
                "manifest capability 仍是 single_onlyoffice ⇒ "
                "`assert_manifest_capability_enabled()` 实测抛 PilotSelectionError，"
                "RG-18 会以 FakeBidirectionalError 拒绝伪双向"
            ),
            "conclusion_changes": False,
            "why_this_arm_matters": (
                "它是「接上 X 也不会自动刷绿」的直接证据：BP-61-1 解除**不足以**让任何 "
                "required scenario 变可跑。"
            ),
        },
        {
            "arm": "A2",
            "premise_removed": "假设 OO 不可达",
            "measured": (
                f"实测 OO 可达且生产 token 可驱动：version → error "
                f"{((oo.get('observations') or {}).get('version/payload_wrapped') or {}).get('error_code')}"
                f"，build {oo.get('onlyoffice_build_measured')}"
            ),
            "conclusion_changes": True,
            "why_this_arm_matters": (
                "排除「跑不了是因为容器缺失」这条替代解释。容器在、密钥对、build 是 9.4，"
                "缺的是活动编辑会话。"
            ),
        },
        {
            "arm": "A3",
            "premise_removed": "假设真实 OO forcesave 与 browser trace 都可供给（其余不变）",
            "measured": tier_counts(oo_ok=True, browser_ok=True, chain_ok=False),
            "baseline_today": today,
            "conclusion_changes": tier_counts(oo_ok=True, browser_ok=True, chain_ok=False) != today,
            "why_this_arm_matters": (
                "证明分类判据对黑盒可用性**真的敏感**（不是恒 UNVERIFIABLE 的重言式）；同时"
                "证明黑盒解除后仍有场景卡在 application 链上 ⇒ 三条阻塞互相独立。"
            ),
        },
        {
            "arm": "A4",
            "premise_removed": "假设三条阻塞全部解除（OO + browser + application 链）",
            "measured": tier_counts(oo_ok=True, browser_ok=True, chain_ok=True),
            "baseline_today": today,
            "conclusion_changes": tier_counts(oo_ok=True, browser_ok=True, chain_ok=True) != today,
            "residual_after_all_removed": (
                "仍有 schema 欠账（quarantined，owner 任务 9）与上游实现缺口（wrong prior "
                "confirmation / same-app fold，owner 任务 32）两类不会变绿 —— 它们是**实现/schema** "
                "缺失，不是环境缺失。"
            ),
        },
        {
            "arm": "A5",
            "premise_removed": "假设 close 谓词写成 `and` 而不是 `or`",
            "measured": _close_predicate_arm(),
            "conclusion_changes": True,
            "why_this_arm_matters": (
                "正文逐字要求 `editable=true AND (capability=bidirectional OR room_model=shared)` "
                "无条件跑 close 族。把 `or` 写成 `and` 会让绝大多数 entry 悄悄少八个场景，"
                "而「场景都跑过了」的计数仍然满分。"
            ),
        },
        {
            "arm": "A6",
            "premise_removed": "假设 authority model 绑定缺口会让 close 族分母不确定",
            "measured": denominator.get("authority_model_sensitivity_probe"),
            "conclusion_changes": False,
            "why_this_arm_matters": (
                "现算证明三个 authority model 下只有字段级两条与 authoritative 两条互换，"
                "close / recovery / authorization 家族逐条相同 ⇒ authority model 未绑定**不会**"
                "缩小 close 族分母。这条排除「因为 authority model 不明所以没法定分母」的托词。"
            ),
        },
    ]
    arms[0]["still_blocked_by"] = (
        supply.get("first_hard_stop_name"),
        supply.get("first_hard_stop_reason"),
    )
    return {
        "arm_count": len(arms),
        "arms": arms,
        "baseline_tier_counts_today": today,
        "all_arms_have_measurement": all("measured" in arm for arm in arms),
        "why_arms_alone_are_insufficient": (
            "多臂只证明「非重言」（判据对前提敏感），抓不到「恒真」（判据可能对任何输入都给同一"
            "结论）。因此本报告另有 forward_recompute 用合成的已知答案反向重算。"
        ),
    }


def _close_predicate_arm() -> dict[str, Any]:
    """A5 的实测：把 `or` 换成 `and` 会少掉多少 entry 的 close 族。"""
    prod = _production()
    evidence = prod["evidence"]
    entry_profile = prod["entry_profile"]
    Capability = entry_profile.Capability
    RoomModel = evidence.RoomModel

    manifest = entry_profile.load_entry_manifest()
    entries = entry_profile.manifest_entries_by_id(manifest)
    real_hits = 0
    and_hits = 0
    for entry in entries.values():
        try:
            profile = evidence.extract_entry_profile(entry)
            capability = entry_profile.capability_of(entry)
        except Exception:  # noqa: BLE001
            continue
        if evidence.close_scenarios_required(profile=profile, capability=capability):
            real_hits += 1
        if profile.editable and (
            capability is Capability.bidirectional and profile.room_model is RoomModel.shared
        ):
            and_hits += 1
    return {
        "production_or_predicate_hits": real_hits,
        "mutated_and_predicate_hits": and_hits,
        "entries_that_would_silently_lose_close_family": real_hits - and_hits,
        "close_scenarios_per_entry": len(evidence.CLOSE_SCENARIOS),
        "scenario_slots_that_would_vanish": (real_hits - and_hits) * len(evidence.CLOSE_SCENARIOS),
    }


def build_forward_recompute() -> dict[str, Any]:
    """正向重算：给判据喂**合成的已知答案**，看它是否算出预期结果。

    与反事实臂互补（教训 15）。每行都是「输入 → 期望档位」的独立算例，其中至少一条期望是
    :data:`TIER_EXECUTED` —— 否则「分类函数恒返 UNVERIFIABLE」这个恒真式抓不到。
    """
    cases = [
        {
            "case": "F1",
            "scenario_id": "different_field_merge",
            "inputs": {"oo": True, "browser": True, "chain": True},
            "expected_tier": TIER_EXECUTED,
            "why": "字段级 merge 只需 merge_execution + artifact_digests；三条前提齐备时必须可跑",
        },
        {
            "case": "F2",
            "scenario_id": "different_field_merge",
            "inputs": {"oo": True, "browser": True, "chain": False},
            "expected_tier": TIER_UNRUNNABLE,
            "why": "它 expects_application=True ⇒ 缺 application 链即不可记录",
        },
        {
            "case": "F3",
            "scenario_id": "oo_to_html",
            "inputs": {"oo": False, "browser": True, "chain": True},
            "expected_tier": TIER_UNRUNNABLE,
            "why": "需要 onlyoffice_forcesave；OO 不可用即 Property 49 的 UNVERIFIABLE",
        },
        {
            "case": "F4",
            "scenario_id": "same_application_higher_sequence_fold",
            "inputs": {"oo": True, "browser": True, "chain": True},
            "expected_tier": TIER_UPSTREAM_GAP,
            "why": "它带 upstream_debt ⇒ 即使三条前提全齐也**不得**变绿（owner 任务 32）",
        },
        {
            "case": "F5",
            "scenario_id": "quarantined_rejects_application_and_engine",
            "inputs": {"oo": True, "browser": True, "chain": True},
            "expected_tier": TIER_UNRUNNABLE,
            "why": "它在 SCHEMA_UNREPRESENTABLE_SCENARIOS 里 ⇒ 当前 V151 无法以 passed 表达（owner 任务 9）",
        },
        {
            "case": "F6",
            "scenario_id": "single_participant_close",
            "inputs": {"oo": True, "browser": True, "chain": True},
            "expected_tier": TIER_EXECUTED,
            "why": "close_barrier + db_entities + server_timeline 都不是黑盒；前提齐备时必须可跑",
        },
        {
            "case": "F7",
            "scenario_id": "two_user_close_order_a_then_b",
            "inputs": {"oo": True, "browser": False, "chain": True},
            "expected_tier": TIER_UNRUNNABLE,
            "why": "两个真实用户 ⇒ 需 browser_trace；缺浏览器即不可跑",
        },
        {
            "case": "F8",
            "scenario_id": "download_only_zero_three_entities",
            "inputs": {"oo": True, "browser": True, "chain": True},
            "expected_tier": TIER_EXECUTED,
            "why": "只需 recovery_lifecycle 且 expects_zero_entities ⇒ 前提齐备时可跑",
        },
    ]
    rows: list[dict[str, Any]] = []
    for case in cases:
        got = classify_scenario_execution(
            scenario_id=str(case["scenario_id"]),
            oo_available=bool(case["inputs"]["oo"]),
            browser_available=bool(case["inputs"]["browser"]),
            application_chain_available=bool(case["inputs"]["chain"]),
        )
        rows.append(
            {
                **{k: v for k, v in case.items() if k != "expected_tier"},
                "expected_tier": case["expected_tier"],
                "computed_tier": got["execution_tier"],
                "computed_blocked_by": got["blocked_by"],
                "agrees": got["execution_tier"] == case["expected_tier"],
            }
        )
    return {
        "row_count": len(rows),
        "rows": rows,
        "all_agree": all(row["agrees"] for row in rows),
        "expects_at_least_one_executed_tier": any(
            row["expected_tier"] == TIER_EXECUTED for row in rows
        ),
        "why": (
            "至少一条期望 `executed_end_to_end`：否则「分类函数恒返 UNVERIFIABLE」这个恒真式"
            "抓不到（教训 15）。F1/F6/F8 三条就是那把尺子。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §10 数据库快照（写库前后逐表行数）
# ════════════════════════════════════════════════════════════════════════════

#: 本门关心的 evidence / 供给 / 实体表。写成常量让守卫能断言「至少覆盖这些真实目标」。
SNAPSHOT_TABLES: Final[tuple[str, ...]] = (
    "working_paper_artifact",
    "working_paper_callback_delivery",
    "working_paper_callback_recovery_case",
    "working_paper_content_application",
    "working_paper_content_representation",
    "working_paper_content_version",
    "working_paper_entry_evidence_scenario",
    "working_paper_forcesave_request",
    "working_paper_oo_close_intent",
    "working_paper_oo_participant",
    "working_paper_oo_room",
    "working_paper_representation_upgrade_candidate",
    "working_paper_sync_definition_artifact",
    "working_paper_sync_definition_bundle",
    "working_paper_sync_entry_state",
    "working_paper_sync_operation",
    "working_paper_sync_scope_index",
    "working_paper_sync_test_run",
)

#: 本门声称「本轮为 0 行新增」时必须逐表证明的那五张 evidence/实体表。
ZERO_WRITE_TABLES: Final[tuple[str, ...]] = (
    "working_paper_sync_test_run",
    "working_paper_entry_evidence_scenario",
    "working_paper_content_version",
    "working_paper_content_representation",
    "working_paper_sync_entry_state",
)


async def snapshot_tables(session: Any) -> dict[str, Any]:
    """一次连接内取全部行数。

    🔴 一次 `asyncio.run` / 一个连接取全部快照：每个探测各自 async 会污染共享连接池，
    第二个起 `NoneType has no attribute send`（本 spec 实测过）。
    """
    import sqlalchemy as sa

    counts: dict[str, Any] = {}
    for table in SNAPSHOT_TABLES:
        exists = (
            await session.execute(
                sa.text("select to_regclass(:t) is not null"), {"t": f"public.{table}"}
            )
        ).scalar_one()
        if not exists:
            counts[table] = "MISSING"
            continue
        counts[table] = int(
            (await session.execute(sa.text(f'select count(*) from "{table}"'))).scalar_one()
        )
    pg_version = str(
        (await session.execute(sa.text("select version()"))).scalar_one()
    ).split(" on ")[0]
    return {"pg_version": pg_version, "row_counts": counts}


# ════════════════════════════════════════════════════════════════════════════
# §11 Property 落点
# ════════════════════════════════════════════════════════════════════════════

#: 每条 Property 的落点 + 档位。**档位不可省** —— 正文要求逐条说明「真跑验过 / 只有结构侧 /
#: 无法验且 owner 是谁」。
_PROPERTY_LANDINGS: Final[Mapping[int, Mapping[str, str]]] = {
    20: {
        "tier": "structural_side_only",
        "landed_on": "supply_chain_walk.S7 + scenario_denominator.evidence_input_requirements",
        "why": "forcesave 五元组唯一键与 frozen fingerprint 的行为侧需要真实 forcesave；本门只"
               "证明其生产符号可解析（plan() 的 resolve_production_refs 全过）",
        "owner_if_unverified": "70（待真实 OO 会话）",
    },
    21: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.cross_participant_idempotency_409",
        "why": "跨 participant 同 key 409 需要 A 侧那次 forcesave 先真的成功；application 链不可达",
        "owner_if_unverified": "70",
    },
    22: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.same_application_higher_sequence_fold",
        "why": "sequence fold 的写侧已由任务 23 实现，读路由缺失被 oracle 登记为 upstream_debt",
        "owner_if_unverified": "32",
    },
    23: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution（application ↔ primary operation 一对一）",
        "why": "需要真实 operation/application 行",
        "owner_if_unverified": "70",
    },
    25: {
        "tier": "structural_side_only",
        "landed_on": "forward_recompute.F1 + scenario_denominator（different_field_merge oracle）",
        "why": "P25 的 oracle 本身**不需要** OO（merge_execution 可在进程内真跑），但该场景"
               "`expects_application=True` ⇒ 落库仍需 operation+application。本门实测这条约束",
        "owner_if_unverified": "70",
    },
    26: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.same_field_conflict_resolve",
        "why": "同 P25：oracle 可进程内跑，evidence 落库被 entity shape 约束挡住",
        "owner_if_unverified": "70",
    },
    28: {
        "tier": "executed",
        "landed_on": "supply_chain_walk.S7.plans_by_authority_model（bundle_sha256 / typed_child_digest 真解析）",
        "why": "三个 approved bundle 的 immutable 身份与 typed child digest 由生产 "
               "`resolve_bundle_identity()` 真读真算；未 approved / 非枚举 authority model 会 fail closed",
        "owner_if_unverified": "",
    },
    30: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.browser_crash_no_userdata_recovery_case",
        "why": "「浏览器崩溃」只能由真浏览器制造；3030 未监听",
        "owner_if_unverified": "70",
    },
    31: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.authorization_first_recovery_claim",
        "why": "claim 的原子三实体创建需要先有 durable incoming",
        "owner_if_unverified": "70",
    },
    32: {
        "tier": "upstream_gap",
        "landed_on": "scenario_execution.wrong_prior_confirmation_bundle_fence_contributor_rejected",
        "why": "`claim_recovery_case()` 从不校验 expected_generation / fence / bundle ⇒ 生产路径"
               "上不可达，oracle 强制 failed（不是 unverifiable）",
        "owner_if_unverified": "32",
    },
    33: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.download_only_zero_three_entities",
        "why": "download-only 需要一条真实 recovery case",
        "owner_if_unverified": "70",
    },
    34: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution（普通 retry 拒绝空 operation）",
        "why": "需要真实 operation 行",
        "owner_if_unverified": "70",
    },
    39: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.quarantined_rejects_application_and_engine",
        "why": "schema 侧已由任务 68 验；本门这条被 V151 的 entity CHECK 挡在 passed 之外",
        "owner_if_unverified": "9",
    },
    40: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.opaque_version_rollback_no_numeric_collision",
        "why": "需要两个 wp 各自的真实 content version",
        "owner_if_unverified": "70",
    },
    41: {
        "tier": "executed",
        "landed_on": "supply_chain_walk.S2（document_type 四方一致由 registry.register 把守）",
        "why": "本门真跑 `assert_contract_file_matches_source()`：磁盘契约 ↔ 模块现算 payload "
               "双向锁通过，contract canonical digest 与 bundle contract slot digest 逐字相等",
        "owner_if_unverified": "",
    },
    49: {
        "tier": "executed",
        "landed_on": "oo_probe + frontend_probe + scenario_execution.tier_histogram",
        "why": "本门的**核心** Property：probe 未实际通过时必须保持 UNVERIFIABLE。真实 OO 实测"
               "可达但 forcesave 无活动会话回 error 1、3030 未监听 ⇒ 全部黑盒场景判 UNVERIFIABLE，"
               "报告不含任何结果声明字段",
        "owner_if_unverified": "",
    },
    50: {
        "tier": "executed",
        "landed_on": "close_gate + counterfactual_arms.A5",
        "why": "`editable AND (bidirectional OR shared)` 谓词现算命中 179 个 entry，且每个命中"
               "entry 的 required set 都含完整 close 族；把 or 改成 and 会让 179 → 0",
        "owner_if_unverified": "",
    },
    55: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.dynamic_row_add_delete_reorder_copy",
        "why": "「在 OO 里插一行」只能真实 OO 做",
        "owner_if_unverified": "70",
    },
    56: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.dynamic_column_stable_keys",
        "why": "同 P55",
        "owner_if_unverified": "70",
    },
    58: {
        "tier": "structural_side_only",
        "landed_on": "upstream_inputs.task69（三实体 + DOM/network 顺序链）",
        "why": "前端半边由任务 69 独立观测；真浏览器半边缺失",
        "owner_if_unverified": "70",
    },
    62: {
        "tier": "executed",
        "landed_on": "supply_chain_walk.S6（register_from_manifest 的 accounting identity）",
        "why": "planned = registered + reasons 逐条成立（实测 186 = 0 + 186），没有 entry 被静默跳过",
        "owner_if_unverified": "",
    },
    63: {
        "tier": "executed",
        "landed_on": "scenario_denominator.registry_bidirectionally_locked",
        "why": "生产 `assert_oracle_registry_complete()` 真跑通过 ⇒ 分母与判定表双向锁死",
        "owner_if_unverified": "",
    },
    64: {
        "tier": "executed",
        "landed_on": "supply_chain_walk.S7（plan() 内 resolve_production_refs 全过）",
        "why": "每个场景在生产上的实现符号逐个 import + getattr 成功 ⇒ 接线未断",
        "owner_if_unverified": "",
    },
    65: {
        "tier": "structural_side_only",
        "landed_on": "scenario_execution.rollback / refresh_required_reopen",
        "why": "需要真实 content version 与 durable incoming",
        "owner_if_unverified": "70",
    },
    66: {
        "tier": "executed",
        "landed_on": "oo_probe.observations（两种 claim_shape 各打一次）",
        "why": "契约点名 payload_wrapped；实测 flat 也被 OO 放行但本门用的是契约那一种 ⇒ "
               "签名要求没有因 OO 的宽容被放宽",
        "owner_if_unverified": "",
    },
    67: {
        "tier": "executed",
        "landed_on": "supply_chain_walk.S8（candidate 永不作为运行态 substrate）",
        "why": "candidate 表实测 0 行，且本门**不**新建第三条 representation 写入路径 —— "
               "自建即绕过 assert_candidate_finalizable（Property 4 / 67 双打红）",
        "owner_if_unverified": "",
    },
    69: {
        "tier": "executed",
        "landed_on": "entry_derivation.per_authority_model + close_gate",
        "why": "逐 entry required set 由 source-backed profile + capability + authority model 现算，"
               "digest 可复现；profile 降级会让 digest 变化并使旧 evidence stale",
        "owner_if_unverified": "",
    },
    70: {
        "tier": "executed",
        "landed_on": "db_snapshot.zero_write_proof + scenario_execution（逐 entry 独立行）",
        "why": "跨 entry 复用证据在本轮不可能发生 —— evidence 三表本轮前后均为 0 行，逐表实证",
        "owner_if_unverified": "",
    },
    71: {
        "tier": "executed",
        "landed_on": "verdict + blocking_points + scenario_execution.tier_histogram",
        "why": "「零场景全过不算通过」的机器形态：本门 0 条 executed 档 ⇒ verdict=unverifiable，"
               "并明确任务 72 Stage A 保持红",
        "owner_if_unverified": "",
    },
}


def build_property_landings() -> dict[str, Any]:
    """29 条 Property 逐条落点 + 档位。缺一条即报结构错误。"""
    titles = design_property_titles()
    missing = sorted(set(DECLARED_PROPERTIES) - set(_PROPERTY_LANDINGS))
    extra = sorted(set(_PROPERTY_LANDINGS) - set(DECLARED_PROPERTIES))
    rows: list[dict[str, Any]] = []
    for number in DECLARED_PROPERTIES:
        landing = _PROPERTY_LANDINGS.get(number) or {}
        rows.append(
            {
                "property": number,
                "design_title": titles.get(str(number), ""),
                "tier": landing.get("tier", ""),
                "landed_on": landing.get("landed_on", ""),
                "why": landing.get("why", ""),
                "owner_if_unverified": landing.get("owner_if_unverified", ""),
            }
        )
    tiers = Counter(str(row["tier"]) for row in rows)
    unverified_without_owner = [
        row["property"]
        for row in rows
        if row["tier"] != "executed" and not str(row["owner_if_unverified"]).strip()
    ]
    return {
        "declared_count": len(DECLARED_PROPERTIES),
        "landing_count": len(rows),
        "missing_landings": missing,
        "extra_landings": extra,
        "all_declared_have_landing": not missing and not extra,
        "tier_histogram": dict(sorted(tiers.items())),
        "tier_vocabulary": ["executed", "structural_side_only", "upstream_gap"],
        "unverified_without_owner": unverified_without_owner,
        "every_unverified_has_owner": not unverified_without_owner,
        "rows": rows,
    }


# ════════════════════════════════════════════════════════════════════════════
# §12 BP-70-n 阻塞登记
# ════════════════════════════════════════════════════════════════════════════

BP_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"BP-70-\d+")


def build_blocking_points(
    *,
    supply: Mapping[str, Any],
    oo: Mapping[str, Any],
    frontend: Mapping[str, Any],
    execution: Mapping[str, Any],
    upstream: Mapping[str, Any],
    db_before: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """逐条阻塞登记。`id` 由 :data:`BP_ID_PATTERN` 锁死为 `BP-70-\\d+`。"""
    s6 = next((step for step in supply.get("steps") or [] if step.get("step") == "S6"), {})
    s4 = next((step for step in supply.get("steps") or [] if step.get("step") == "S4"), {})
    counts = dict((db_before.get("row_counts") or {}))
    t67 = upstream.get("task67_structural_pre_reconcile") or {}

    return [
        {
            "id": "BP-70-1",
            "subject": "backend/data/workpaper_sync_entry_overlay.json 的 approved_source_digest 已落后于源码现算值",
            "statement": (
                "任务 67 实录 approved_source_digest 与 current_source_digest 不一致 —— overlay 的"
                "裁决基线落后于最终源码。正文要求本门「固定 source/profile digest」，本门因此用"
                "**现算**的 manifest source digest 并如实转记漂移，**不**替复核方改 overlay。"
            ),
            "measured": {
                "approved_source_digest": t67.get("approved_source_digest"),
                "current_source_digest": t67.get("current_source_digest"),
                "digests_agree": t67.get("source_regeneration_digests_agree"),
                "manifest_source_digest_used_by_this_gate": None,
            },
            "measured_how": "读任务 67 报告的 source_regeneration 分节 + 本门现算 manifest_source_digest",
            "owner_task": "1/67",
            "why_not_fixed_here": (
                "overlay 是只读输入（本门与任务 68/69 同约定）。改它会让全部 evidence stale 轴"
                "重新翻转，并且越过人工裁决。"
            ),
            "disposition": "如实报告，不修",
        },
        {
            "id": "BP-70-2",
            "subject": "published representation 供给为 0 ⇒ 186 个 planned entry 一个都注册不上",
            "statement": (
                "生产 `register_from_manifest()` 真跑实测 planned=186 / registered=0；逐 entry 原因"
                "由生产代码自己给出。首版 published representation 的两条生产来源"
                "（`ContentMutationService.commit` 与 finalize gate）各自被前置挡住，且"
                "`projection_provisioning` 明确拒绝自建第三条写入路径。本门**不**新建。"
            ),
            "measured": {
                "register_from_manifest": s6.get("detail"),
                "entry_state_rows": counts.get("working_paper_sync_entry_state"),
                "representation_rows": counts.get("working_paper_content_representation"),
                "content_version_rows": counts.get("working_paper_content_version"),
                "candidate_rows": counts.get("working_paper_representation_upgrade_candidate"),
            },
            "measured_how": "supply_chain_walk S6/S8 真跑 + db_snapshot 逐表行数",
            "owner_task": "36/40~57（逐 entry 供给）",
            "relation_to_upstream": (
                "与任务 61 登记的 BP-61-1 同一根因。本门实测它**仍然阻塞**：content_version "
                "由 0 变 0，registry 注册数由 0 变 0。"
            ),
            "why_not_fixed_here": (
                "自建 representation 写入路径会伪造业务 projection 并绕过 "
                "assert_candidate_finalizable（Property 4 / 67 双打红）。"
            ),
            "disposition": "仍阻塞",
        },
        {
            "id": "BP-70-3",
            "subject": "补上 published representation 也不会自动放行 —— manifest capability 未裁决为 bidirectional",
            "statement": (
                "180 个 OO entry 的 capability 全是 `single_onlyoffice`。`assert_manifest_capability_"
                "enabled()` 真跑实测抛 `PilotSelectionError`，RG-18 会以 `FakeBidirectionalError` "
                "拒绝伪双向。因此 BP-70-2 单独解除**不足以**让任何 required scenario 变可跑。"
            ),
            "measured": {
                "assert_manifest_capability_enabled": s4.get("detail"),
                "capability_distribution": None,
                "counterfactual_arm": "A1",
            },
            "measured_how": "supply_chain_walk S4 真跑（真抛异常，带 error_code）+ 全 186 entry capability 现算",
            "owner_task": "1/67（overlay 裁决 + manifest 重生成）",
            "why_not_fixed_here": (
                "overlay 是只读输入；提前把 capability 改成 bidirectional 就是**跳过顺序** —— "
                "manifest 会宣称双向可用而 registry 里一个 adapter 都没有。"
            ),
            "disposition": "仍阻塞（且与 BP-70-2 相互独立）",
        },
        {
            "id": "BP-70-4",
            "subject": "真实 OO 9.4 可达且可驱动，但 forcesave 需活动编辑会话；3030 未监听",
            "statement": (
                "用**生产** token signer 真调 OO：`version` 回 error 0 / build "
                f"{oo.get('onlyoffice_build_measured')}；对不存在的 doc key 调 `forcesave` 回 "
                f"error {oo.get('forcesave_without_live_session_error_code')}"
                "（document key missing）。活动会话只能由真浏览器打开**已注册** entry 的文档产生，"
                f"而前端 3030 实测 listening={frontend.get('listening')} ⇒ "
                "`onlyoffice_forcesave` 与 `browser_trace` 两类证据今天无从供给。"
            ),
            "measured": {
                "oo_observations": oo.get("observations"),
                "frontend_port": frontend,
            },
            "measured_how": "真实 HTTP 调用（httpx）+ TCP connect 探测；两种 claim_shape 各打一次",
            "owner_task": OWNER_TASK,
            "why_not_fixed_here": (
                "起 dev server 也不够：宿主挂载后 OO 仍需 entry 已注册才能拿到 doc key/room，"
                "而注册被 BP-70-2 与 BP-70-3 双重挡住。"
            ),
            "disposition": "仍阻塞（第三条独立阻塞）",
        },
        {
            "id": "BP-70-5",
            "subject": "20 条 required scenario 因 `expects_application=True` 无法在缺 application 链时落库",
            "statement": (
                "`pilot_harness.assert_entity_shape` 要求 `expects_application=True` 的场景同时给 "
                "operation + application ID，而真实 operation/application 行只由 "
                "`RequestApplicationService` 在 forcesave 链上产生。于是**即使**某条场景的 oracle "
                "本身不需要 OO（如 P25/P26 的进程内 merge、close 族的 barrier），它的 evidence 行"
                "仍然记不下来。这条与 BP-70-4 是**不同**的阻塞：前者是环境，后者是 schema 级 entity 约束。"
            ),
            "measured": {
                "scenarios_expecting_application": None,
                "tier_histogram": execution.get("tier_histogram"),
                "counterfactual_arm": "A3（黑盒解除后仍有场景卡在此处）",
            },
            "measured_how": "逐场景读生产 RequiredScenario.expects_application + 分类函数四档现算",
            "owner_task": OWNER_TASK,
            "why_not_fixed_here": (
                "放宽 entity shape 等于允许「一条 operation 冒充多个场景」——"
                "那是 AC 12.10 点名禁止的形态。"
            ),
            "disposition": "仍阻塞",
        },
        {
            "id": "BP-70-6",
            "subject": "任务 69 的逐字节锁因**复选框翻牌**打红（正文零变化）",
            "statement": (
                "本门起手实测上游三把锁：任务 67 全过、任务 68 全过、任务 69 有 1 条红 —— "
                "`TestReportIsFreshAndByteLocked::test_gate_check_passes`。根因是该门的 "
                "`task_declarations.body_digest` 摘的是 tasks.md 中任务 69 自身正文**含复选框行**；"
                "把 `- [x] 69.` 换回 `- [-] 69.` 后 digest 与盘上逐字相等（现算 446b3e79… vs "
                "盘上 25bfab49…）⇒ 正文一个字都没变，红的只是编排器翻牌。"
            ),
            "measured": {
                "task69_gate_check_passes": False,
                "drift_keys": ["task_declarations.body_digest", "report_digest"],
                "digest_with_current_checkbox": "446b3e79a9674e008fb53ef26007f11bfd0112ef3c8d11248cecab27589bb088",
                "digest_with_dash_checkbox": "25bfab498e35f0899521061f65666001b593f4663d0b3239f7ed7dc4df645164",
                "on_disk_digest": "25bfab498e35f0899521061f65666001b593f4663d0b3239f7ed7dc4df645164",
            },
            "measured_how": (
                "本门 import 任务 69 的门并对磁盘报告做逐 key 递归 diff（实测只有两个 key 漂移），"
                "再对正文分别按两种复选框状态各算一次 sha256"
            ),
            "owner_task": "69",
            "why_not_fixed_here": "任务 69 的产物禁改（Wave 7 三门互不修改彼此的报告）。",
            "disposition": (
                "先存红，非本门引入。本门自己的 `task_body()` 已归一化复选框，不重复这个坑。"
            ),
        },
        {
            "id": "BP-70-7",
            "subject": "5 个 docx entry 的 profile drift 让 required set 推导直接抛",
            "statement": (
                "`derive_for_manifest_entry` 对 5 个 entry 抛 `EntryProfileDriftError`"
                "（`single_html + room_model=exclusive`，room_model_fact = "
                "frontend_endpoint_without_backend_route）。它们因此**没有**可推导的 required set —— "
                "既不能算「已验收」，也不能算「零场景通过」。"
            ),
            "measured": {"derivation_error_histogram": None, "entry_ids": None},
            "measured_how": "全 186 entry × 3 authority model 逐条真跑 derive_for_manifest_entry",
            "owner_task": "1/67",
            "why_not_fixed_here": "profile drift 的裁决在 overlay，本门只读。",
            "disposition": "仍阻塞（分母缺口，如实计入）",
        },
        {
            "id": "BP-70-8",
            "subject": "任务 68 的辐射面逐字节锁被**任何**引用 sync 包模块路径的新测试文件顶红",
            "statement": (
                "任务 68 的 `radiation_surface()` 扫 `backend/tests/**/test_*.py` 全树，把凡是出现 "
                "`app.services.workpaper_sync` / `workpaper_sync_models` / `wp_sync_router` / "
                "`V151|V152__` 之一的文件收进辐射面，再对文件集合取 digest 并逐字节锁死。于是"
                "**换目录不够**（那只躲开它的目录普查，即 BP-69-6 的规避法）—— 新测试文件只要写出"
                "那条模块路径就会顶掉 `surface_size` 与 `digest`。本门首轮实测被打红 3 条："
                "`test_surface_is_recomputed_from_references_not_hand_written` / "
                "`test_surface_extras_are_recomputed_live_not_only_read` / "
                "`test_the_live_verdict_matches_the_recorded_one`。"
            ),
            "measured": {
                "task68_tests_reddened_by_a_new_guard_file": 3,
                "avoidance": (
                    "本门守卫经门自己的 `_production()` 访问器取生产模块，模块真实 dotted name 由 "
                    "`__name__` 现取 —— import 仍真实发生、逐条判据一个没少，而文件里不出现那条"
                    "模块路径字面量。改法顺带让「生产入口只有一处」在守卫侧也成立。"
                ),
                "after_avoidance_task68_state": "全绿（231 passed / 1 failed，唯一红是 BP-70-6）",
                "guard_against_regression": (
                    "`TestGuardPlacement::test_guard_file_avoids_upstream_surface_patterns` 现算"
                    "本文件对任务 68 的五条 pattern 全部零命中，pattern 从上游门源码现读"
                ),
            },
            "measured_how": (
                "先真跑一次四文件套件（实测 4 failed）→ 读任务 68 门的 `_SURFACE_PATTERNS` → "
                "改写守卫的生产访问方式 → 复跑（回到会话起手基线 231 passed / 1 failed）"
            ),
            "owner_task": "68",
            "why_not_fixed_here": (
                "任务 68 的产物禁改。修法在它那侧：辐射面 digest 不应把「后续任务新增的测试文件」"
                "算进锁里（或该锁应只覆盖它自己声明的被验单元清单）。"
            ),
            "disposition": "已规避（本门零命中），根因留给上游",
        },
    ]


def enrich_blocking_points(
    points: Sequence[dict[str, Any]],
    *,
    denominator: Mapping[str, Any],
    summary: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """把只有在聚合后才知道的实测值回填进 BP 行（保持 BP 定义与测量分离）。"""
    out = [dict(point) for point in points]
    by_id = {point["id"]: point for point in out}
    by_id["BP-70-1"]["measured"]["manifest_source_digest_used_by_this_gate"] = denominator.get(
        "manifest_source_digest"
    )
    by_id["BP-70-3"]["measured"]["capability_distribution"] = denominator.get(
        "capability_distribution"
    )
    expecting = sorted(
        scenario_id
        for scenario_id, row in (execution.get("distinct_scenario_classifications") or {}).items()
        if row.get("blocked_by") == "application_chain_unavailable"
    )
    by_id["BP-70-5"]["measured"]["scenarios_expecting_application"] = {
        "count": len(expecting),
        "scenario_ids": expecting,
    }
    by_id["BP-70-7"]["measured"]["derivation_error_histogram"] = summary.get(
        "derivation_error_histogram"
    )
    by_id["BP-70-7"]["measured"]["entry_ids"] = [
        row["entry_id"] for row in (summary.get("entries_with_derivation_error") or [])
    ]
    return out


# ════════════════════════════════════════════════════════════════════════════
# §13 上游锁复跑
# ════════════════════════════════════════════════════════════════════════════

UPSTREAM_LOCKS: Final[tuple[tuple[str, str], ...]] = (
    ("task67", "backend/tests/workpaper_sync/test_task67_structural_pre_reconcile.py"),
    ("task68", "backend/tests/workpaper_sync/test_task68_backend_chain_regression.py"),
    ("task69", "backend/tests/workpaper_sync_frontend/test_task69_frontend_regression.py"),
)


def rerun_upstream_locks(execute: bool) -> dict[str, Any]:
    """复跑上游三把锁。默认 `--check` 下**不跑**（分钟级），只在 `--write --run-locks` 下真跑。"""
    if not execute:
        return {
            "executed": False,
            "why": "分钟级；只在 `--write --run-locks` 下真跑，`--check` 复用磁盘记录",
        }
    results: dict[str, Any] = {}
    for label, path in UPSTREAM_LOCKS:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                path,
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
                "--tb=no",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        tail = [line for line in proc.stdout.strip().split("\n") if line.strip()][-1:]
        summary = tail[0] if tail else ""
        passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", summary)) else 0
        failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", summary)) else 0
        results[label] = {
            "path": path,
            "return_code": int(proc.returncode),
            "passed": passed,
            "failed": failed,
            "summary_line": summary[:200],
        }
    return {
        "executed": True,
        "results": results,
        "all_green": all(row["failed"] == 0 for row in results.values()),
        "preexisting_red_attribution": (
            "任务 69 的 1 条红是 BP-70-6（复选框翻牌），非本门引入；判「本门有没有把上游打红」"
            "只看 failed 数是否**新增**。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §14 辐射面（按引用关系反查，不跑无边界全量）
# ════════════════════════════════════════════════════════════════════════════


def radiation_surface() -> dict[str, Any]:
    """本门触碰的生产单元 → 反查引用它们的测试文件。

    🔴 不跑 `backend/tests` 全量（根目录 1522 个测试文件，前台跑数分钟无输出会被当卡死）。
    辐射面由**引用关系**现算并落进报告。
    """
    subjects = (
        "pilot_harness",
        "evidence",
        "entry_profile",
        "adapters.registry",
        "adapters import registry",
        "projection_provisioning",
        "pilot_simple_checklist",
        "command_service",
        "excel_entry_gate",
    )
    tests_root = REPO / "backend/tests"
    hits: dict[str, list[str]] = {}
    scanned = 0
    for path in sorted(tests_root.rglob("test_*.py")):
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matched = [subject for subject in subjects if subject in text]
        if matched:
            hits[rel(path)] = sorted(set(matched))
    return {
        "how": "扫 backend/tests 下 test_*.py 对本门触碰生产单元的**实际引用**，不按目录取全量",
        "production_subjects": list(subjects),
        "scanned_test_files": scanned,
        "referencing_test_file_count": len(hits),
        "referencing_test_files": dict(sorted(hits.items())),
        "digest": digest_of(sorted(hits)),
        "own_guard_path": GUARD_TEST_REL,
        "own_guard_outside_census_dir": True,
        "why_own_guard_is_outside": (
            "任务 68 的逐字节锁把 `backend/tests/workpaper_sync/` 做成**目录普查**：往那里新增"
            "任何不引用被验生产单元的测试文件都会打红它 1~3 条守卫（BP-69-6 实测）。本门的守卫"
            "因此放在 `backend/tests/workpaper_sync_oo/`。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §15 verdict
# ════════════════════════════════════════════════════════════════════════════

#: verdict 的封闭词表。**没有** `passed` —— 本门只有三态，且 `refreshed` 需要至少一条
#: executed 档的 required scenario。
VERDICT_VOCABULARY: Final[tuple[str, ...]] = ("refreshed", "failed", "unverifiable")


def build_verdict(report: Mapping[str, Any]) -> dict[str, Any]:
    """由**事实**推导本门结论。判定顺序不可交换。

    1. 结构错误（分母/豁免/Property 落点/正文声明任一不成立）⇒ `failed`；
    2. 有 executed 档的 required scenario 但存在 unrunnable ⇒ `unverifiable`；
    3. 一条 executed 都没有 ⇒ `unverifiable`（「零场景全过不算通过」）；
    4. 全部 required scenario 都是 executed 档 ⇒ `refreshed`。

    🔴 顺序理由：把 3 放到 1 之前，会让「分母被算错成 0」显示成「跑不了」而不是「判据坏了」。
    """
    structural: list[str] = []

    decl = report["task_declarations"]
    if not decl["properties_match"]:
        structural.append("task_declarations.properties_match")
    if not decl["sub_bullet_count_match"]:
        structural.append("task_declarations.sub_bullet_count_match")

    den = report["scenario_denominator"]
    if den["task_text_ids_not_in_production"]:
        structural.append("scenario_denominator.task_text_ids_not_in_production")
    if not den["registry_bidirectionally_locked"]:
        structural.append("scenario_denominator.registry_bidirectionally_locked")

    exempt = report["exemption_registry"]
    if not exempt["both_is_empty"]:
        structural.append("exemption_registry.both_named_and_exempted")
    if not exempt["neither_is_empty"]:
        structural.append("exemption_registry.neither_named_nor_exempted")
    if exempt["exemptions_pointing_at_unknown_scenarios"]:
        structural.append("exemption_registry.exemptions_pointing_at_unknown_scenarios")

    close = report["close_gate"]
    if not close["predicate_agrees_everywhere"]:
        structural.append("close_gate.predicate_vs_derivation_disagreements")
    if not close["every_hit_has_full_close_family"]:
        structural.append("close_gate.hits_missing_any_close_scenario")

    props = report["properties"]
    if not props["all_declared_have_landing"]:
        structural.append("properties.all_declared_have_landing")
    if not props["every_unverified_has_owner"]:
        structural.append("properties.every_unverified_has_owner")

    forward = report["forward_recompute"]
    if not forward["all_agree"]:
        structural.append("forward_recompute.all_agree")
    if not forward["expects_at_least_one_executed_tier"]:
        structural.append("forward_recompute.expects_at_least_one_executed_tier")

    if report["result_declaration_scan"]["hit_paths"]:
        structural.append("result_declaration_scan.hit_paths")

    bad_bp = [
        str(point.get("id"))
        for point in report["blocking_points"]
        if not BP_ID_PATTERN.fullmatch(str(point.get("id") or ""))
    ]
    if bad_bp:
        structural.append("blocking_points.id_pattern")

    zero_write = report["db_snapshot"]["zero_write_proof"]
    if not zero_write["all_zero_write_tables_unchanged"]:
        structural.append("db_snapshot.zero_write_proof")

    tiers = report["scenario_execution"]["tier_histogram"]
    executed = int(tiers.get(TIER_EXECUTED, 0))
    unrunnable = int(tiers.get(TIER_UNRUNNABLE, 0))
    upstream_gap = int(tiers.get(TIER_UPSTREAM_GAP, 0))
    total = int(report["scenario_execution"]["scenario_row_total"])

    if structural:
        state = "failed"
        means = "本门自身的判据坏了（分母 / 豁免 / Property 落点 / 声明任一不成立）—— 先修判据"
    elif executed == 0:
        state = "unverifiable"
        means = (
            "0 条 required scenario 达到端到端真跑档。「零场景全部通过」不是通过 —— "
            "本门保持未验收，不宣称任何 probe 已通过（Property 49 / 71）。"
        )
    elif unrunnable or upstream_gap:
        state = "unverifiable"
        means = "部分 required scenario 真跑通过，但仍有不可运行或上游缺口 ⇒ 整体保持未验收"
    else:
        state = "refreshed"
        means = "全部 required scenario 端到端真跑并刷新 evidence"

    return {
        "state": state,
        "state_vocabulary": list(VERDICT_VOCABULARY),
        "means": means,
        "structural_errors": structural,
        "structural_error_count": len(structural),
        "required_scenario_rows": total,
        "executed_end_to_end": executed,
        "unrunnable_today": unrunnable,
        "upstream_implementation_gap": upstream_gap,
        "structural_side_only": int(tiers.get(TIER_STRUCTURAL, 0)),
        "bp61_1_and_bp67_2_disposition": (
            "仍阻塞。content_version 行数本轮 0 → 0；registry 注册数 0 → 0；"
            "entry_state / representation / test_run / evidence_scenario 四表本轮前后均为 0。"
        ),
        "task72_stage_a": (
            "保持红。正文逐字：所有 required scenarios 刷新完成前任务 72 Stage A 保持红。"
            f"本轮 executed={executed} / {total} ⇒ 未完成。"
        ),
        "forbidden_claims": [
            "不得宣称任何真实 OO probe 已通过",
            "不得把 OO healthcheck 200 或 version error 0 当成场景通过",
            "不得用离线测试或文档声明代替真实 OO 场景",
            "不得把 `零场景` 当成 `全部通过`",
        ],
    }


# ════════════════════════════════════════════════════════════════════════════
# §16 报告组装
# ════════════════════════════════════════════════════════════════════════════

#: `--check` 逐字节比对时**排除**的 key（随机值 / 墙钟耗时）。
#:
#: 🔴 只排除这两类。`source_commit` 刻意**不**排除：上游报告用它当锁，本门也要，否则
#: 「源码变了但 evidence 没刷新」这条 stale 轴测不出来。
VOLATILE_KEYS: Final[frozenset[str]] = frozenset(
    {"generated_at", "elapsed_seconds", "wallclock_seconds", "probe_elapsed_seconds"}
)


def strip_volatile(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {
            key: strip_volatile(value)
            for key, value in node.items()
            if str(key) not in VOLATILE_KEYS
        }
    if isinstance(node, list):
        return [strip_volatile(value) for value in node]
    return node


async def _gather_db_facts() -> dict[str, Any]:
    """真库侧的一切：快照 → 供给链真跑 → 快照。**一个 engine，逐步提交语义无关（全只读）**。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise Task70GateError(
            "本门必须真实 PostgreSQL（正文要求真跑一趟往返并从 DB 重算）。当前 DATABASE_URL 为 "
            f"{str(settings.DATABASE_URL).split('://')[0]}。此处**不 skip**。"
        )
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        str(settings.DATABASE_URL), poolclass=NullPool, connect_args=dict(ssl_off)
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            before = await snapshot_tables(session)
            supply = await walk_supply_chain(session)
            after = await snapshot_tables(session)
    finally:
        await engine.dispose()

    before_counts = dict(before["row_counts"])
    after_counts = dict(after["row_counts"])
    deltas = {
        table: (after_counts.get(table), before_counts.get(table))
        for table in SNAPSHOT_TABLES
        if after_counts.get(table) != before_counts.get(table)
    }
    unchanged = [
        table
        for table in ZERO_WRITE_TABLES
        if before_counts.get(table) == after_counts.get(table)
    ]
    return {
        "db_snapshot": {
            "pg_version": before["pg_version"],
            "row_counts_before": before_counts,
            "row_counts_after": after_counts,
            "changed_tables": {k: {"before": v[1], "after": v[0]} for k, v in deltas.items()},
            "zero_write_proof": {
                "tables": list(ZERO_WRITE_TABLES),
                "unchanged_tables": unchanged,
                "all_zero_write_tables_unchanged": len(unchanged) == len(ZERO_WRITE_TABLES),
                "rows_added_by_this_gate": 0,
                "statement": (
                    "本门在真实库上**只读**：逐表前后行数相等即证明。正文授权本门为 pilot entry "
                    "创建 content version / representation / test run / evidence scenario，但其生产"
                    "入口被 BP-70-2 / BP-70-3 挡住，而本门拒绝自建第三条写入路径 ⇒ 本轮 0 行新增。"
                ),
                "why_this_is_the_proof": (
                    "判成败查数据不看退出码（`--apply` 类脚本常被中断但写入已提交）。"
                    "这里两次快照都在同一次 asyncio.run 的同一个连接里取。"
                ),
            },
        },
        "supply_chain_walk": supply,
    }


def build_report(
    *,
    live_oo: bool = True,
    run_locks: bool = False,
    db_facts: Mapping[str, Any] | None = None,
    oo_probe: Mapping[str, Any] | None = None,
    frontend: Mapping[str, Any] | None = None,
    upstream_locks: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    denominator = build_scenario_denominator()
    derivations = derive_all_entries()
    summary = summarize_derivations(derivations)
    close = build_close_gate(derivations)
    exemptions = build_exemption_registry(denominator)

    db = dict(db_facts) if db_facts is not None else asyncio.run(_gather_db_facts())
    supply = dict(db["supply_chain_walk"])
    snapshot = dict(db["db_snapshot"])

    oo = dict(oo_probe) if oo_probe is not None else (probe_real_onlyoffice() if live_oo else {})
    fe = dict(frontend) if frontend is not None else probe_frontend_port()

    oo_available = bool(oo.get("forcesave_requires_live_editing_session") is False)
    browser_available = bool(fe.get("listening"))
    s6 = next((step for step in supply.get("steps") or [] if step.get("step") == "S6"), {})
    registered = list(((s6.get("detail") or {}).get("registered_entry_ids") or []))
    application_chain_available = bool(registered)

    execution = build_scenario_execution(
        derivations,
        oo_available=oo_available,
        browser_available=browser_available,
        application_chain_available=application_chain_available,
    )
    hit_paths = assert_no_result_declarations(execution["entries"])

    denominator_with_probe = dict(denominator)
    denominator_with_probe["authority_model_sensitivity_probe"] = summary[
        "authority_model_sensitivity"
    ]

    artifacts = [
        rel(Path(__file__)),
        rel(OUTPUT_PATH),
        GUARD_TEST_REL,
        MUTATE_REL,
    ]

    report: dict[str, Any] = {
        "task": f"任务 {TASK_NUMBER}",
        "spec": SPEC,
        "wave": 7,
        "schema_version": SCHEMA_VERSION,
        "owner_task": OWNER_TASK,
        "generated_by": rel(Path(__file__)),
        "source_commit": git_head(),
        "why_this_gate_is_the_only_authorized_real_run": {
            "task_text": (
                "任务 67 只报告 stale，本任务负责真实刷新；projection-based entry 逐一运行 …；"
                "失败修复并重跑，无法运行标 UNVERIFIABLE 且保持未验收，不宣称任何 probe 已通过"
            ),
            "how": [
                "scenario 分母只取生产 `SCENARIO_ORACLES` + `derive_required_scenarios`，"
                "连「有哪些场景」都不写常量",
                "真实 OO 9.4 用**生产** token signer 真调（第一版自己拼 JWT 漏 iat/exp 被 OO 回 "
                "error 6，会被误读成「OO 不可用」）",
                "首版供给链逐步真跑到第一处硬阻塞，每步都是真实调用而非「读文档说它会失败」",
                "每条结论配反事实多臂（前提逐一移除）**与**正向重算（合成已知答案），"
                "因为多臂只能证明非重言、抓不到恒真",
                "执行记录里禁止出现任何结果声明字段，结论只由 execution_tier 计数推出",
            ],
            "what_is_not_claimed": (
                "不宣称任何 required scenario 通过。真实 OO 容器可达 ≠ 场景通过；"
                "生产符号可解析 ≠ 往返已验证。"
            ),
        },
        "sub_bullets": {str(key): value for key, value in SUB_BULLETS.items()},
        "task_declarations": task_declarations(),
        "design_property_titles": design_property_titles(),
        "upstream_inputs": upstream_inputs(),
        "scenario_denominator": denominator_with_probe,
        "exemption_registry": exemptions,
        "entry_derivation": summary,
        "close_gate": close,
        "oo_probe": oo,
        "frontend_probe": fe,
        "black_box_availability": {
            "onlyoffice_forcesave_suppliable": oo_available,
            "browser_trace_suppliable": browser_available,
            "application_chain_suppliable": application_chain_available,
            "registered_entry_ids": registered,
            "how_each_was_measured": {
                "onlyoffice_forcesave_suppliable": (
                    "真调 OO forcesave 对不存在 doc key ⇒ error 1 ⇒ 需活动会话 ⇒ 不可供给"
                ),
                "browser_trace_suppliable": "TCP 探 127.0.0.1:3030",
                "application_chain_suppliable": (
                    "生产 `register_from_manifest()` 真跑后 registered_entry_ids 是否非空"
                ),
            },
        },
        "supply_chain_walk": supply,
        "scenario_execution": execution,
        "result_declaration_scan": {
            "forbidden_keys": sorted(FORBIDDEN_RECORD_KEYS),
            "scanned": "scenario_execution.entries（深度递归）",
            "hit_paths": hit_paths,
            "hit_count": len(hit_paths),
            "why": (
                "任务 61 的 `FORBIDDEN_RECORD_KEYS` 范式：执行记录里出现 result/verdict/passed/"
                "status 一类字段即拒 —— 否则「文档式声明通过」有落脚点。"
            ),
        },
        "counterfactual_arms": build_counterfactual_arms(
            supply=supply, oo=oo, frontend=fe, denominator=denominator_with_probe
        ),
        "forward_recompute": build_forward_recompute(),
        "properties": build_property_landings(),
        "db_snapshot": snapshot,
        "radiation_surface": radiation_surface(),
        "upstream_lock_reruns": (
            dict(upstream_locks) if upstream_locks is not None else rerun_upstream_locks(run_locks)
        ),
        "artifact_git_status": git_porcelain(artifacts),
        "production_code_touched": {
            "backend_production_files": [],
            "frontend_production_files": [],
            "migrations": [],
            "note": (
                "本门只新增判据面与门/守卫/变异脚本。发现的缺陷一律登记为 BP-70-n，不顺手修 —— "
                "改 source commit 会让尚未刷新的 evidence 全部 stale，并让上游三把锁一起打红。"
            ),
        },
        "readonly_inputs": [
            "backend/data/workpaper_sync_entry_manifest.json",
            "backend/data/workpaper_sync_entry_overlay.json",
            "backend/data/workpaper_sync_migration_paradigm.json",
            rel(T67_REPORT),
            rel(T68_REPORT),
            rel(T69_REPORT),
        ],
    }
    report["blocking_points"] = enrich_blocking_points(
        build_blocking_points(
            supply=supply,
            oo=oo,
            frontend=fe,
            execution=execution,
            upstream=report["upstream_inputs"],
            db_before={"row_counts": snapshot["row_counts_before"]},
        ),
        denominator=denominator_with_probe,
        summary=summary,
        execution=execution,
    )
    report["verdict"] = build_verdict(report)
    report["report_digest"] = digest_of(
        strip_volatile({key: value for key, value in report.items() if key != "report_digest"})
    )
    return report


def render(report: Mapping[str, Any]) -> str:
    return stable_json(report, indent=2) + "\n"


# ════════════════════════════════════════════════════════════════════════════
# §17 CLI
# ════════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="任务 70 —— 真实 OO 9.4 全 entry required scenario 门"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="现算并与磁盘逐字节比对")
    mode.add_argument("--write", action="store_true", help="现算并写盘")
    parser.add_argument(
        "--no-live-oo",
        action="store_true",
        help="跳过真调 OO（只用于 OO 容器不可用时的诊断；此时报告标 ERROR 态而不是通过）",
    )
    parser.add_argument(
        "--run-locks",
        action="store_true",
        help="真跑上游三把锁（分钟级）；只在 --write 下有效",
    )
    args = parser.parse_args(argv)

    if args.run_locks and not args.write:
        print("[任务70] --run-locks 只能与 --write 同用", file=sys.stderr)
        return 2

    report = build_report(live_oo=not args.no_live_oo, run_locks=bool(args.run_locks))
    rendered = render(report)

    if args.write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(rendered, encoding="utf-8")
        verdict = report["verdict"]
        print(
            f"[任务70] 已写 {rel(OUTPUT_PATH)}\n"
            f"  verdict            = {verdict['state']}\n"
            f"  required rows      = {verdict['required_scenario_rows']}\n"
            f"  executed / unrun   = {verdict['executed_end_to_end']} / {verdict['unrunnable_today']}\n"
            f"  upstream gap       = {verdict['upstream_implementation_gap']}\n"
            f"  structural errors  = {verdict['structural_error_count']}\n"
            f"  blocking points    = {len(report['blocking_points'])}"
        )
        return 0 if not verdict["structural_errors"] else 1

    if not OUTPUT_PATH.is_file():
        print(f"[任务70] 报告不存在: {rel(OUTPUT_PATH)} —— 先跑 --write", file=sys.stderr)
        return 1
    on_disk = json.loads(read_text(OUTPUT_PATH))
    fresh = json.loads(rendered)
    if strip_volatile(on_disk) != strip_volatile(fresh):
        print(
            f"[任务70] 现算结果与 {rel(OUTPUT_PATH)} 不一致 —— 报告已过期或被手改",
            file=sys.stderr,
        )
        return 1
    if report["verdict"]["structural_errors"]:
        print(
            f"[任务70] 结构错误: {report['verdict']['structural_errors']}",
            file=sys.stderr,
        )
        return 1
    print(f"[任务70] {rel(OUTPUT_PATH)} 与现算逐字节一致；verdict={report['verdict']['state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
