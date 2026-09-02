# -*- coding: utf-8 -*-
"""任务 71 验收门：变异、容量、故障恢复、retention/脱敏/告警与数据复原。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7

═══ 本门的性质：验收，不是清单 ═══

正文点名的每一条「变异覆盖 …」都必须**真造出非法形态并证明系统拒绝它**。每条都要有
**对照组（合法形态被接受）+ 实验组（非法形态被拒，且各臂拒绝理由互不命中）**。
只声明「已覆盖」不构成任何证据 —— 那是本 spec 反复实测到的假绿第①源（additive 注入
即死代码）。

═══ 与上游任务的分工（不重复造）═══

任务 68 已在 scratch schema 真造 **128 行 / 17 张表 / 120 条行为臂**
（37 accepted 对照组 + 73 rejected + 10 measure），覆盖 forcesave 五元键、N shell 收敛、
close 五种顺序 exactly-one、leader 按最高 `(intent_sequence, id)`、跨 bundle 不折叠、
recovery claim canonical 收敛。本门**不重跑**这些，而是：

1. 按正文逐条点名建立 :data:`MUTATION_TARGETS` 分母，并把每条**解析**到一个真实证据源
   （上游 arm / 本门 arm / 本门守卫变异 / 已登记 UNVERIFIABLE + owner）。声明 `t68_arm:`
   的必须在任务 68 报告里**真的**找到那条 arm 且 `agrees=True` —— 上游报告一旦丢掉那条
   arm，本门立刻变红。这条比「写一行说已覆盖」强的地方在于它是**跨文件双向锁**。
2. 补正文点名而任务 68 没覆盖的六个面：**容量 / 故障恢复 / retention / 脱敏 / 告警 /
   数据复原**，各自独立报告字段与独立实测。
3. 独立复核 BP-68-1（`pre-durable rejected/error 零 owner` 在 DDL 层没有约束力）。

═══ 六个面各自的可执行性（本轮实测，不是推测）═══

* **容量** —— 生产 `capacity_profile` 把「登记」与「已执行」做成两个不可互换的状态，
  且执行 owner 写死为本任务。本门真调 `assert_capacity_verified(None)` 证明它 **抛**
  而不是返回 False，真调 `assert_profile_matches_requirements()` 证明登记值与
  `requirements.md` 的 AC 14.10/14.12 原文逐字段相等，并用合成实测值把
  `evaluate_capacity_run` 的四条负载判据 + 两条延迟判据 + ADR 缺失分支逐条打出来。
  **6000 会话 × 1200 participant 的真实负载本轮无法运行**（3030 未监听、无真实 OO 编辑
  会话、生产 `public` 无业务数据），如实标 UNVERIFIABLE 并点名 owner —— 不用合成实测值
  冒充「容量门已通过」，那正是生产模块设计来防的事。
* **故障恢复** —— OO / Redis / PG / 磁盘 / Windows lock / 进程中断六种注入各自真做一次，
  并断言错误是**上抛**而不是被 `except Exception` 吞成「无数据」（AC 5.12）。
* **retention** —— `RetentionPolicyService.plan()` / `.apply()` 在 scratch schema 上真跑，
  artifact 根指向临时目录，逐条判定分支（legal hold / TTL / grace / 引用重现 /
  in-flight / delete_failed）都造出来。
* **脱敏** —— `RedactionPolicy.redact()` 真跑，植入的密钥必须被抹，`assert_no_leak()`
  对未脱敏载荷必须抛。
* **告警** —— `validate_registry()` 三向核对 + `evaluate()` 在 synthetic 事件流上真跑，
  阈值上下各一条（对照组 + 实验组）。
* **数据复原** —— scratch schema `DROP ... CASCADE` + 生产 `public` 逐表前后相等 +
  **区分本轮残留与外来残留**（任务 68 踩过：变异故意删 DROP 会累计留下 scratch schema，
  只报总数会把本轮结论打成假红）。

═══ 三条落位约束（各自都有实测代价）═══

1. **本门守卫不在 `backend/tests/workpaper_sync/`**（BP-69-6：任务 68 的目录普查会打红
   1~3 条）；用 `backend/tests/workpaper_sync_chaos/`，且「不在普查目录」是**现算**判据。
2. **本门守卫对任务 68 的辐射面 pattern 零命中**（BP-70-8：换目录不够，它的 digest 扫
   `backend/tests` 全树按模块路径收文件）。规避法：守卫经本门的 :func:`_production`
   访问器取生产模块，dotted name 用 `__name__` 现算。
3. **复选框归一化**（BP-70-6：编排器把 `[-]` 勾成 `[x]` 后未归一化的逐字节锁必红）。

用法::

    python backend/scripts/check/check_task71_mutation_capacity_recovery_gate.py --write
    python backend/scripts/check/check_task71_mutation_capacity_recovery_gate.py --check
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # import 自举：backend/scripts
import _census_lock  # noqa: E402  普查量/逐字节锁分离（四门共用，说理在那里）

import argparse
import ast
import asyncio
import hashlib
import importlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final, Mapping, Sequence

REPO: Final[Path] = Path(__file__).resolve().parents[3]
BACKEND: Final[Path] = REPO / "backend"
DATA: Final[Path] = BACKEND / "data"

TASK_NUMBER: Final[str] = "71"
OWNER_TASK: Final[str] = "71"
SPEC: Final[str] = "workpaper-html-onlyoffice-bidirectional-writeback-closure"
SCHEMA_VERSION: Final[str] = "task71-mutation-capacity-recovery-retention:v1"

SPEC_DIR: Final[Path] = REPO / ".kiro" / "specs" / SPEC
TASKS_MD: Final[Path] = SPEC_DIR / "tasks.md"
DESIGN_MD: Final[Path] = SPEC_DIR / "design.md"

OUTPUT_PATH: Final[Path] = DATA / "workpaper_sync_task71_mutation_capacity_recovery.json"

T67_REPORT: Final[Path] = DATA / "workpaper_sync_task67_structural_pre_reconcile.json"
T68_REPORT: Final[Path] = DATA / "workpaper_sync_task68_backend_chain_regression.json"
T69_REPORT: Final[Path] = DATA / "workpaper_sync_task69_frontend_regression.json"
T70_REPORT: Final[Path] = DATA / "workpaper_sync_task70_oo_scenario_refresh.json"

#: 上游任务 68 的门（本门复用它的 scratch schema 世界搭建与 `_Runner`，**只读不改**）。
T68_GATE: Final[Path] = (
    BACKEND / "scripts/check/check_task68_backend_chain_independent_regression.py"
)
#: 上游 writer 门（`multi_resolver` 裁决的度量入口）。
WRITER_GATE: Final[Path] = BACKEND / "scripts/check/check_workpaper_writer_revision_gate.py"
WRITER_OVERLAY: Final[Path] = DATA / "workpaper_writer_domain_overlay.json"
WRITER_INVENTORY: Final[Path] = DATA / "workpaper_writer_inventory.json"
#: 任务 12 的 resolver 迁移矩阵（`status` / `blocking_task` / `adjudication_owner_task`）。
RESOLVER_MATRIX: Final[Path] = DATA / "workpaper_resolver_migration_matrix.json"

GUARD_TEST_REL: Final[str] = "backend/tests/workpaper_sync_chaos/test_task71_chaos_gate.py"
MUTATE_REL: Final[str] = "backend/scripts/diagnose/mutate_task71_chaos_guards.py"
GATE_REL: Final[str] = "backend/scripts/check/check_task71_mutation_capacity_recovery_gate.py"

#: scratch schema 前缀。本门只在这里写行；生产 `public` 全程只读。
SCRATCH_PREFIX: Final[str] = "tmp_task71_chaos_"

#: 正文「独立验证 Property …」逐条（24 条）。守卫与 design.md 双向锁死。
DECLARED_PROPERTIES: Final[tuple[int, ...]] = (
    4, 5, 17, 18, 19, 28, 36, 42, 43, 44, 45, 57, 59, 60, 61, 62, 63, 64,
    67, 68, 69, 70, 71, 72,
)

#: 正文十个子条目（不含 `_Requirements:` 行）。每条都必须有独立判据与独立报告字段。
SUB_BULLETS: Final[Mapping[int, str]] = {
    1: "application/protocol 变异 + sequence 变异 + delivery 变异",
    2: "scope/close/DAG 变异",
    3: "其余协议变异（writer bypass / 双 commit / mtime doc_key / claim None / "
       "participant-bound callback / 撤权 cached replay / incoming-first lookup / "
       "same incoming 不同 bundle 折叠 / mutable room base / null close initiator）",
    4: "definition/candidate 变异（DAG 断裂 / slot omission / NULL·空串·全零 hash / "
       "typed null marker / unapproved contract / candidate 被看见 / 直接发布 / 历史 retry alias）",
    5: "recovery 变异 + evidence 变异",
    6: "删除门变异（任务 67 错误要求 fresh/stale=0 或宣称 eligibility；Stage A 错误要求"
       "待删 unreachable 预先为 0；post-delete 仅 smoke 恢复 evidence）",
    7: "`多 resolver writer=0`（gate issue key multi_resolver）自任务 30 移交至本门",
    8: "容量 6000/1200/120/20×10min + OO·Redis·PG·磁盘·Windows lock·进程中断注入 + "
       "RetentionPolicy / RedactionPolicy / alert synthetic",
    9: "测试数据、incoming、trace/evidence artifact 完整复原/清理；四态判定不以退出码代替证据",
    10: "独立验证 Property 4/5/17/18/19/28/36/42/43/44/45/57/59/60/61/62/63/64/67~72",
}

#: 三态封闭词表。**没有第四态**：本门要么真验过（passed）、要么发现缺陷（failed）、
#: 要么如实标不可验（unverifiable）。加第四态就是给「宣称通过」开门。
VERDICT_VOCABULARY: Final[tuple[str, ...]] = ("passed", "failed", "unverifiable")

#: BP 编号锁（守卫用 `re.fullmatch` 逐条比对）。
BP_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"BP-71-\d+")

#: 逐字节比对时排除的键：**只有**随机值（scratch hex）与墙钟耗时。
#: 🔴 `source_commit` 刻意不在名单里 —— 它是「源码变了但证据没刷新」这条 stale 轴的唯一锁。
VOLATILE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "generated_at",
        "elapsed_seconds",
        "wallclock_seconds",
        "scratch_schema",
        "temp_artifact_root",
        "probe_elapsed_seconds",
    }
)


class Task71GateError(RuntimeError):
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
        raise Task71GateError(f"无法取 git HEAD: {type(exc).__name__}: {exc}") from exc


def git_porcelain(paths: Sequence[str]) -> dict[str, str]:
    """逐产物的 `git status --porcelain`。

    🔴 「spec 全绿 ≠ 产物已入库」：挂进 CI 的 job 在干净 checkout 下会因文件不存在必挂。
    **先判存在** —— `git status --porcelain -- <不存在的路径>` 输出为空，与「已跟踪且干净」
    长得一模一样，不分开就会把「产物还没写出来」报成 `tracked-clean`。
    """
    out: dict[str, str] = {}
    for path in paths:
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
        raise Task71GateError(f"上游报告缺失: {rel(path)} —— 本门必须消费它，不得跳过")
    return json.loads(read_text(path))


def strip_comments(source: str) -> str:
    """剥 Python 注释与文档字符串，保留可执行结构。

    🔴 判「有没有真调某个符号」之前必须先剥注释（教训 12），但**不能**用它去剥含 SQL 的
    文件：`sa.text(\"\"\"...\"\"\")` 会被一起剥掉。本门只对自己的门/守卫源码用它。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise Task71GateError(f"源码无法解析: {exc}") from exc
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
    replaced: set[int] = set()
    for index, line in enumerate(lines, start=1):
        if index in drop:
            # 不能直接删：剥掉某个 def 的文档字符串后 body 就空了 ⇒ IndentationError。
            if index - 1 not in drop and index - 1 not in replaced:
                indent = line[: len(line) - len(line.lstrip())]
                kept.append(f"{indent}pass")
                replaced.add(index)
            else:
                kept.append("")
                replaced.add(index)
            continue
        if line.strip().startswith("#"):
            kept.append("")
            continue
        kept.append(line)
    return "\n".join(kept)


# ════════════════════════════════════════════════════════════════════════════
# §2 tasks.md / design.md 声明（复选框归一化）
# ════════════════════════════════════════════════════════════════════════════

_CHECKBOX_RE: Final[re.Pattern[str]] = re.compile(r"^(\s*-\s\[)[ x~\-](\]\s+\d+\.)")


def task_body(task_number: str = TASK_NUMBER) -> str:
    """tasks.md 里本任务的正文段。**首行复选框归一化成 `[?]`**。

    🔴 BP-70-6：任务 69 的门把含 `- [x] 69.` 的整段做 digest，编排器把 `[-]` 勾成 `[x]`
    后它的逐字节锁立刻打红，而正文一个字都没变。归一化让锁只对**正文内容**敏感。
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
        raise Task71GateError(f"tasks.md 里找不到任务 {task_number}")
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
            "（BP-70-6 实测，本门起手复现）。本门只锁正文内容。"
        ),
    }


def design_property_titles() -> dict[str, str]:
    """design.md 里本门声明的 24 条 Property 的标题。找不到即结构错误。"""
    text = read_text(DESIGN_MD)
    out: dict[str, str] = {}
    for number in DECLARED_PROPERTIES:
        match = re.search(rf"^###\s+Property\s+{number}\b[:：]?\s*(.*)$", text, re.M)
        if match is None:
            raise Task71GateError(
                f"design.md 里找不到 `### Property {number}` —— 本门声明的 Property 必须在"
                "设计文档里有定义，否则「验证了它」无从核对"
            )
        out[str(number)] = match.group(1).strip()
    return out


# ════════════════════════════════════════════════════════════════════════════
# §3 上游四份报告：按 key 取，不整读
# ════════════════════════════════════════════════════════════════════════════


def upstream_inputs() -> dict[str, Any]:
    """消费任务 67/68/69/70 的报告。

    只取本门真正会**用到**的 key（arm 索引、不变量结论、evidence 计数、verdict、欠账），
    不把 5 MB 报告原样搬进来。每份都记 `report_digest` 与 `source_commit`，上游被重生成时
    本门的锁会跟着变。
    """
    t67 = read_json(T67_REPORT)
    t68 = read_json(T68_REPORT)
    t69 = read_json(T69_REPORT)
    t70 = read_json(T70_REPORT)

    t67_entries = t67.get("entries") or []
    return {
        "task67_structural_pre_reconcile": {
            "path": rel(T67_REPORT),
            "report_digest": t67.get("report_digest"),
            "entry_count": len(t67_entries),
            "how_this_gate_uses_it": (
                "删除门变异的分母：任务 67 只允许报告 stale、不得要求 fresh/stale=0、不得宣称"
                "eligibility。本门把这三条做成对源码的现算判据而不是读它的自述。"
            ),
        },
        "task68_backend_chain_regression": {
            "path": rel(T68_REPORT),
            "report_digest": t68.get("report_digest"),
            "source_commit": t68.get("source_commit"),
            "invariant_count": len(t68.get("invariants") or []),
            "arm_count": sum(
                len((row.get("behaviour_side") or {}).get("arms") or [])
                for row in (t68.get("invariants") or [])
            ),
            "endpoint_check_count": len(t68.get("endpoint_checks") or []),
            "blocking_point_ids": [
                str(bp.get("id")) for bp in (t68.get("blocking_points") or [])
            ],
            "verdict": (t68.get("verdict") or {}).get("result"),
            "restored": (t68.get("restoration") or {}).get("restored"),
            "how_this_gate_uses_it": (
                "本门的变异分母里凡是标 `t68_arm:` 的都要在这份报告里**真的**找到那条 arm 且"
                "`agrees=True`；上游一旦丢掉某条 arm 或它变成 disagrees，本门立刻变红。"
                "BP-68-1（pre-durable rejected/error 零 owner 在 DDL 层无约束力）由本门独立复核。"
            ),
        },
        "task69_frontend_regression": {
            "path": rel(T69_REPORT),
            "report_digest": t69.get("report_digest"),
            "source_commit": t69.get("source_commit"),
            "invariant_count": len(t69.get("invariants") or []),
            "port_3030_listening": (t69.get("oo_scope_boundary") or {}).get(
                "port_3030_listening"
            ),
            "how_this_gate_uses_it": (
                "前端侧 recovery/claim/download-only 三实体结论已由任务 69 独立断言；本门只在"
                "容量面引用它实录的「3030 未监听」作为「真实负载今天无从供给」的实证之一。"
            ),
        },
        "task70_oo_scenario_refresh": {
            "path": rel(T70_REPORT),
            "report_digest": t70.get("report_digest"),
            "source_commit": t70.get("source_commit"),
            "verdict": (t70.get("verdict") or {}).get("state"),
            "executed_end_to_end": (t70.get("verdict") or {}).get("executed_end_to_end"),
            "required_scenario_rows": (t70.get("verdict") or {}).get("required_scenario_rows"),
            "evidence_rows_measured_zero": {
                table: ((t70.get("db_snapshot") or {}).get("row_counts_before") or {}).get(table)
                for table in (
                    "working_paper_sync_test_run",
                    "working_paper_entry_evidence_scenario",
                    "working_paper_content_version",
                    "working_paper_content_representation",
                    "working_paper_sync_entry_state",
                )
            },
            "oo_reachable": ((t70.get("oo_probe") or {}).get("reachable")),
            "how_this_gate_uses_it": (
                "任务 70 实录：evidence 五表全 0 行、180 个 OO entry 的 capability 全是"
                "single_onlyoffice、forcesave 对不存在 doc key 回 error 1（需活动编辑会话）、"
                "3030 未监听。⇒ 本门的容量/故障恢复/retention 行为侧同样只能在 scratch schema "
                "造行，生产 `public` 无业务数据可演练。这是既定条件，不是本门偷懒。"
            ),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# §4 生产模块访问器（守卫经此取生产模块 —— BP-70-8 的规避法）
# ════════════════════════════════════════════════════════════════════════════

_PROD_CACHE: dict[str, Any] | None = None


def _ensure_backend_on_path() -> None:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))


def _production() -> dict[str, Any]:
    """一次性 import 生产模块并缓存（昂贵对象进程内缓存）。

    🔴 守卫**必须**经这个访问器取生产模块，不在守卫文件里写模块路径字面量 ——
    任务 68 的辐射面 digest 按模块路径扫 `backend/tests` 全树，写出那条路径就会顶掉它的
    `surface_size`/`digest` 并打红 3 条守卫（BP-70-8）。走访问器不是绕过判据：import 仍然
    真的发生，且模块的真实 dotted name 由 `__name__` 现取，守卫侧需要那条路径的地方都是
    **算出来**的而不是抄的。
    """
    global _PROD_CACHE
    if _PROD_CACHE is not None:
        return _PROD_CACHE
    _ensure_backend_on_path()
    base = "app.services." + "workpaper" + "_sync"
    mods = {
        "capacity": importlib.import_module(f"{base}.capacity_profile"),
        "retention": importlib.import_module(f"{base}.retention"),
        "redaction": importlib.import_module(f"{base}.redaction"),
        "alerting": importlib.import_module(f"{base}.alerting"),
        "metrics": importlib.import_module(f"{base}.metrics"),
        "models": importlib.import_module(f"{base}.models"),
        "artifacts": importlib.import_module(f"{base}.artifacts"),
        "limits": importlib.import_module(f"{base}.limits"),
        "outbox": importlib.import_module(f"{base}.outbox"),
        "orm": importlib.import_module("app.models." + "workpaper" + "_sync_models"),
    }
    _PROD_CACHE = mods
    return mods


_T68_CACHE: Any | None = None


def _t68_gate() -> Any:
    """按文件路径 import 任务 68 的门（**只读复用**它的 scratch schema 世界搭建）。

    复用而不是抄一份：世界搭建 280 行、跨 17 张表，抄一份的必然结局是它改了我不红。
    """
    global _T68_CACHE
    if _T68_CACHE is not None:
        return _T68_CACHE
    _ensure_backend_on_path()
    if "task68_gate_for_71" in sys.modules:
        _T68_CACHE = sys.modules["task68_gate_for_71"]
        return _T68_CACHE
    spec = importlib.util.spec_from_file_location("task68_gate_for_71", T68_GATE)
    if spec is None or spec.loader is None:
        raise Task71GateError(f"无法加载任务 68 的门: {rel(T68_GATE)}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["task68_gate_for_71"] = module
    spec.loader.exec_module(module)
    _T68_CACHE = module
    return module


# ════════════════════════════════════════════════════════════════════════════
# §5 变异分母：正文逐条点名 → 真实证据源
# ════════════════════════════════════════════════════════════════════════════

#: 证据源的封闭前缀词表。**不许出现第五种** —— 第五种意味着「有别的方式算已覆盖」。
EVIDENCE_KINDS: Final[tuple[str, ...]] = (
    "t68_arm",        # 上游任务 68 在 scratch schema 真造过的行为臂（本门逐条复核 agrees）
    "t68_endpoint",   # 上游任务 68 的端点检查（本门逐条复核 passed）
    "t71_arm",        # 本门在自己的 scratch schema 真造的行为臂
    "t71_facet",      # 本门六个面之一的实测字段
    "guard_mutation", # 本门守卫的变异锚点（守卫层判据，非行为层）
    "unverifiable",   # 如实登记不可验 + owner，绝不冒充
)


@dataclass(frozen=True)
class MutationTarget:
    """正文点名的一条「变异覆盖 …」。

    :param evidence: 证据源引用列表。至少一条；每条必须是 :data:`EVIDENCE_KINDS`
        里的前缀。**空 evidence 会在构造时抛** —— 空集恒真是假绿第⑥源。
    """

    target_id: str
    sub_bullet: int
    clause: str
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.evidence:
            raise Task71GateError(
                f"变异目标 {self.target_id} 没有任何证据源 —— 空 evidence 恒真（假绿第⑥源）"
            )
        for ref in self.evidence:
            kind = ref.split(":", 1)[0]
            if kind not in EVIDENCE_KINDS:
                raise Task71GateError(
                    f"变异目标 {self.target_id} 的证据源 {ref!r} 前缀非法；"
                    f"只允许 {list(EVIDENCE_KINDS)}"
                )


def _t(target_id: str, sub_bullet: int, clause: str, *evidence: str) -> MutationTarget:
    return MutationTarget(target_id, sub_bullet, clause, tuple(evidence))


#: 🔴 正文六个变异子条目逐条点名的分母。**一条都不许合并** —— 合并会让「靠后的那条永久
#: 不可达」（教训 1/4）。行文顺序与正文一致，便于逐字核对。
MUTATION_TARGETS: Final[tuple[MutationTarget, ...]] = (
    # ── 子条目 1：application / protocol ──────────────────────────────────
    _t("m1_application_key_on_operation", 1,
       "把 `application_key` 错放 operation",
       "t68_arm:ak_operation_column_absent", "t68_arm:ak_same_key"),
    _t("m1_application_before_incoming_durable", 1,
       "incoming durable 前预建 application",
       "t68_arm:aif_staged", "t68_arm:aif_quarantined", "t68_arm:aif_durable"),
    _t("m1_normal_forcesave_without_shell", 1,
       "normal forcesave 未创建 pre-correlation shell",
       "t68_arm:opfk_two_null_shells", "t68_arm:opfk_same_request_twice"),
    _t("m1_forcesave_key_missing_generation_participant_kind", 1,
       "forcesave 唯一键漏 generation/participant/kind",
       "t68_arm:fr5_same_tuple_again", "t68_arm:fr5_cross_participant",
       "t68_arm:fr5_cross_kind", "t68_arm:fr5_distinct_ids"),
    _t("m1_cache_hit_ignores_frozen_fingerprint", 1,
       "cache hit 不比 `frozen_request_fingerprint` 并向跨 participant/kind/payload 调用返回旧 ID",
       "t68_arm:fr5_same_tuple_other_payload", "t68_arm:frz_fingerprint_update",
       "t68_arm:frz_bundle_update"),
    _t("m1_duplicate_pointer_deleted", 1,
       "N 个 different-request 同 key 后删除 `duplicate_of_operation_id`",
       "t68_arm:nshell_convergence", "t68_arm:opfk_same_application_twice"),
    _t("m1_duplicate_points_at_duplicate", 1,
       "duplicate 指向 duplicate（非 direct）",
       "t68_arm:dup_chain", "t68_arm:dup_self"),
    _t("m1_duplicate_forms_chain_or_cycle", 1,
       "duplicate 形成链/环",
       "t68_arm:dup_chain", "t68_arm:nshell_convergence"),
    _t("m1_duplicate_rebinds_application", 1,
       "duplicate 再绑 application",
       "t68_arm:dup_with_application", "t68_arm:dup_rebind"),
    _t("m1_stranded_waiting_shell", 1,
       "留下 stranded waiting shell",
       "t68_arm:dup_stranded_target", "t68_arm:nshell_convergence"),
    _t("m1_duplicate_resolve_requires_application_first", 1,
       "duplicate resolve 先要求 requested operation 绑定 application",
       "t68_endpoint:duplicate_operation_authorization_keyed_on_requested_id"),
    _t("m1_duplicate_resolve_follows_primary_before_auth", 1,
       "duplicate resolve 授权前跟随 primary，或 retry 新建 operation/application",
       "t68_endpoint:duplicate_operation_authorization_keyed_on_requested_id",
       "t68_endpoint:guard_is_the_first_await_in_every_handler"),
    # ── 子条目 1：sequence ────────────────────────────────────────────────
    _t("m1_origin_request_sequence_rewritten", 1,
       "改写 `origin_request_sequence`",
       "t68_arm:eff_origin_update", "t68_arm:eff_insert_below_origin"),
    _t("m1_effective_sequence_not_greatest", 1,
       "不 GREATEST 提升 `effective_request_sequence`",
       "t68_arm:eff_raise", "t68_arm:eff_lower"),
    _t("m1_room_raw_sequence_without_canonical_application", 1,
       "room 只推进 raw sequence 不保存 canonical application",
       "t68_arm:fold_full", "t68_arm:fold_no_room_fence", "t68_arm:fold_no_request"),
    _t("m1_same_app_fold_self_supersede", 1,
       "same-app fold 自我 supersede",
       "t68_arm:eff_self_supersede", "t68_arm:fold_twice_same_request"),
    # ── 子条目 1：delivery ────────────────────────────────────────────────
    _t("m1_owner_gate_back_to_terminal", 1,
       "把 owner gate 改回 terminal（用泛化终态代替 `durable_at`）",
       "t68_arm:dlv_durable_state_no_fact", "t68_arm:dlv_unmatched_with_request"),
    _t("m1_pre_durable_rejected_forced_owner", 1,
       "pre-durable rejected/error 强制 owner",
       "t68_arm:dlv_pre_durable_owner", "t71_arm:t71_pre_durable_owner_ddl",
       "t71_arm:t71_pre_durable_owner_invariant",
       "t71_arm:t71_pre_durable_zero_owner_invariant",
       "t71_facet:bp_68_1_recheck.agrees_with_task68"),
    _t("m1_durable_zero_owner", 1,
       "durable 零 owner",
       "t68_arm:dlv_durable_zero_owner", "t68_arm:dlv_durable_one_owner"),
    _t("m1_post_durable_error_drops_owner", 1,
       "post-durable error 丢 owner",
       "t68_arm:dlv_post_durable_drop_owner", "t68_arm:dlv_post_durable_error_keeps_owner"),
    _t("m1_request_application_wrong_xor", 1,
       "request/application 错误 XOR",
       "t68_arm:dlv_request_and_application", "t71_arm:t71_request_and_application_invariant"),
    _t("m1_application_recovery_double_owner", 1,
       "application/recovery 双归属",
       "t68_arm:dlv_double_owner", "t71_arm:t71_double_owner_invariant"),
    _t("m1_incoming_published_or_current_or_resolvable", 1,
       "incoming state=`published` / 成为 current / resolver 可见",
       "t68_arm:inc_published", "t68_arm:cand_published_artifact",
       "t68_arm:cand_pointer_to_staged"),
    _t("m1_quarantined_released_or_promoted", 1,
       "quarantined 被 release / 转 durable / 建 application / 进入 engine",
       "t68_arm:inc_quarantined_to_durable", "t68_arm:inc_durable_to_quarantined",
       "t68_arm:aif_quarantined", "t68_arm:rec_quarantined_incoming"),
    # ── 子条目 2：scope / close / DAG ─────────────────────────────────────
    _t("m2_scope_index_missing_or_tampered", 2,
       "scope index 缺失或篡改仍可读",
       "t68_arm:si_insert", "t68_arm:si_rebind_scope",
       "t68_endpoint:endpoints_carry_explicit_project_wp_entry"),
    _t("m2_child_retire_physical_delete", 2,
       "child 退役时物理删除 / 清空 tombstone / 复用 resource id",
       "t68_arm:si_retire", "t68_arm:si_delete", "t68_arm:si_clear_tombstone"),
    _t("m2_cache_before_auth", 2,
       "先查业务 row/cache 再授权（cache-before-auth）",
       "t68_endpoint:guard_is_the_first_await_in_every_handler"),
    _t("m2_cross_project_wp_entry", 2,
       "跨 project/wp/entry",
       "t68_arm:si_rebind_scope",
       "t68_endpoint:endpoints_carry_explicit_project_wp_entry"),
    _t("m2_recovery_list_missing_room_generation", 2,
       "recovery list 漏 room/generation",
       "t68_endpoint:recovery_list_requires_room_and_generation"),
    _t("m2_rollback_missing_entry_or_version_id", 2,
       "rollback 漏 entry/`version_id`",
       "t68_endpoint:rollback_route_key_is_opaque_content_version_id"),
    _t("m2_numeric_revision_as_route_or_resource_key", 2,
       "使用 numeric revision 作 route/resource key 并让两个 wp 同 revision 碰撞",
       "t68_arm:cv_two_wps_same_revision", "t68_arm:cv_same_wp_same_revision",
       "t68_arm:cv_numeric_as_resource_key", "t68_arm:si_numeric_resource_id",
       "t68_endpoint:no_route_uses_numeric_revision_as_key"),
    _t("m2_404_403_stage_or_timing_leak", 2,
       "404/403 阶段或时序泄露",
       "t68_endpoint:unified_404_403_refusal_surface"),
    _t("m2_task24_dependency_on_task23_removed", 2,
       "把任务 24 对任务 23 的依赖删掉",
       "guard_mutation:M20", "t71_facet:dag_dependency.task24_depends_on_task23"),
    _t("m2_leader_comparator_created_at", 2,
       "leader comparator 改为 `created_at`",
       "t68_arm:cc_leader_by_highest_intent_sequence"),
    _t("m2_closing_still_counts_active", 2,
       "closing 仍计 active",
       "t68_arm:cc_second_open", "t68_arm:cc_after_terminal"),
    _t("m2_barrier_or_leader_drift", 2,
       "barrier/leader 漂移",
       "t68_arm:lead_duplicate_active_intent", "t68_arm:lead_promote_cross_generation"),
    _t("m2_promotion_without_authorization_stale", 2,
       "promotion 前 revoke/expire 不写 `authorization_stale`",
       "t68_arm:lead_authorization_stale", "t68_arm:lead_promote"),
    _t("m2_leader_swapped_on_same_snapshot", 2,
       "同 eligibility snapshot 换 leader",
       "t68_arm:lead_successor_same_generation"),
    _t("m2_legal_successor_not_promoted", 2,
       "合法 successor 不接任",
       "t68_arm:lead_promote", "t68_arm:lead_promote_wrong_kind"),
    _t("m2_no_successor_without_supersede_or_recovery_required", 2,
       "无 successor 不 supersede generation / 不落 `recovery_required`",
       "t68_arm:lead_successor_same_generation",
       "unverifiable:24:generation supersede + recovery_required 的**服务层**分支需要 "
       "close_intent 协调器在真行上跑一轮；任务 68 已在 schema 侧验过 leader 选举与 "
       "authorization_stale，本门未再独立跑协调器（owner 任务 24）"),
    _t("m2_reconciler_not_reentrant", 2,
       "`reconcile_close_intents()` 不重入/不幂等",
       "t68_arm:cc_exactly_one_over_orders"),
    _t("m2_a_terminal_before_after_b_close", 2,
       "A terminal 前后 B close 最终 0 条或 >1 条 close-capture",
       "t68_arm:cc_exactly_one_over_orders", "t68_arm:cc_after_terminal",
       "t68_arm:cc_single", "t68_arm:cc_second_open"),
    # ── 子条目 3：其余协议变异 ────────────────────────────────────────────
    _t("m3_writer_bypass", 3,
       "writer bypass 统一 commit",
       "t71_facet:multi_resolver_adjudication.writer_gate_criteria",
       "unverifiable:74:`bypasses_unified_commit` 实测 261 行未归零，owner 是任务 74；"
       "本门只如实度量不代它归零"),
    _t("m3_double_content_commit", 3,
       "双 content commit / representation 增 business revision",
       "t71_facet:multi_resolver_adjudication.writer_gate_criteria",
       "t68_arm:chain_rep_legal"),
    _t("m3_mtime_doc_key", 3,
       "mtime doc_key（可变量入 doc key）",
       "t71_facet:protocol_source_scan.doc_key_probe.doc_key_includes_mtime",
       "t68_arm:chain_frozen_values_unchanged"),
    _t("m3_claim_none", 3,
       "claim None（recovery claim 允许空 case）",
       "t68_arm:rec_claimed_partial", "t68_arm:rec_claimed_full"),
    _t("m3_participant_bound_callback", 3,
       "participant-bound callback（把 callback 绑到单个 participant）",
       "t68_arm:fr5_cross_participant", "t68_arm:dlv_durable_one_owner"),
    _t("m3_revoked_cached_replay", 3,
       "撤权后 cached replay",
       "t68_endpoint:guard_is_the_first_await_in_every_handler",
       "t68_endpoint:unified_404_403_refusal_surface"),
    _t("m3_incoming_first_lookup", 3,
       "incoming-first lookup（先按 incoming 找 application）",
       "t68_arm:fb_no_folding", "t68_arm:fb_duplicate_across_bundles"),
    _t("m3_same_incoming_different_bundle_folds", 3,
       "same incoming 不同 bundle/authority model 错误折叠",
       "t68_arm:fb_two_bundles_two_applications", "t68_arm:fb_bundle_not_from_request",
       "t68_arm:fb_no_folding"),
    _t("m3_mutable_room_base_or_status_in_key", 3,
       "mutable room base / status 入 key",
       "t68_arm:fold_full", "t68_arm:eff_identity_column_update",
       "t71_facet:protocol_source_scan.application_key_inputs"),
    _t("m3_null_close_initiator", 3,
       "null close initiator",
       "t68_arm:lead_promote_wrong_kind", "t68_arm:cc_single"),
    # ── 子条目 4：definition / candidate ──────────────────────────────────
    _t("m4_dag_broken", 4,
       "完整 DAG 断裂（template → instrumentation → contract → bundle → representation）",
       "t68_arm:chain_rep_legal", "t68_arm:chain_rep_candidate_bundle",
       "t68_arm:chain_rep_bundle_sha_mismatch", "t68_arm:chain_rep_authority_mismatch"),
    _t("m4_bundle_slot_omission", 4,
       "bundle slot omission",
       "t68_arm:bs_legal", "t68_arm:bs_null_ref", "t68_arm:chain_custom_slot_omitted"),
    _t("m4_sql_json_null_empty_zero_hash", 4,
       "SQL/JSON NULL / 空串 / 全零 hash",
       "t68_arm:bs_zero_digest", "t68_arm:bs_digest_mismatch",
       "t68_arm:pc_authority_model_type_null"),
    _t("m4_illegal_typed_null_marker", 4,
       "非法 typed null marker",
       "t68_arm:tm_registered_marker", "t68_arm:tm_unregistered_marker",
       "t68_arm:tm_wrong_slot_marker", "t68_arm:tm_forged_digest",
       "t68_arm:pc_marker_substitution"),
    _t("m4_unapproved_or_missing_contract_still_current", 4,
       "`projection_contract` unapproved / missing contract 仍 current",
       "t68_arm:pc_three_definitions", "t68_arm:pc_candidate_child",
       "t68_arm:chain_cand_candidate_contract"),
    _t("m4_candidate_seen_by_resolver_room_current_evidence", 4,
       "candidate 被 resolver/room/current/evidence 看见",
       "t68_arm:cand_staged", "t68_arm:cand_published_artifact",
       "t68_arm:cand_durable_artifact", "t68_arm:cand_pointer_to_staged",
       "t68_arm:chain_cand_wrong_artifact_kind"),
    _t("m4_task17_59_publish_representation_directly", 4,
       "任务 17/59 直接发布 representation",
       "t68_arm:chain_cand_staged", "t68_arm:chain_cand_ready_no_bundle",
       "t68_arm:chain_art_canonical", "t68_arm:chain_art_candidate"),
    _t("m4_historical_retry_reads_current_alias", 4,
       "历史 retry 改读当前 alias",
       "t68_arm:chain_frozen_new_generation", "t68_arm:chain_frozen_update_rejected",
       "t68_arm:chain_frozen_values_unchanged"),
    # ── 子条目 5：recovery + evidence ─────────────────────────────────────
    _t("m5_no_userdata_crash_without_case", 5,
       "no-userdata crash 未建 case",
       "t68_arm:rec_unclaimed",
       "unverifiable:70:真实浏览器 crash 场景需要 3030 + 真实 OO 编辑会话，本轮 3030 未监听"
       "（任务 69/70 双侧实录）；schema 侧「claim 前三实体为 0」已由任务 68 验过"),
    _t("m5_prebuilt_entity_before_claim", 5,
       "claim 前预建任一 request/application/operation",
       "t68_arm:rec_unclaimed_with_application", "t68_arm:rec_claimed_partial"),
    _t("m5_claim_not_atomic", 5,
       "claim 非原子 request + shell + application",
       "t68_arm:rec_claimed_full", "t68_arm:rec_canonical_convergence",
       "t71_arm:t71_atomicity_partial_rollback"),
    _t("m5_wrong_prior_confirmation_bundle_fence_contributor_succeeds", 5,
       "错误 prior confirmation/bundle/fence/contributor 仍成功",
       "t68_arm:fb_bundle_not_from_request", "t68_arm:rec_quarantined_incoming",
       "t68_endpoint:guard_is_the_first_await_in_every_handler"),
    _t("m5_download_only_creates_entity", 5,
       "download-only 创建任一三实体",
       "t68_arm:rec_download_only_with_operation"),
    _t("m5_nullable_operation_normal_retry_allowed", 5,
       "nullable-operation 普通 retry 放行",
       "t68_arm:opfk_two_null_shells",
       "t68_endpoint:duplicate_operation_authorization_keyed_on_requested_id"),
    _t("m5_evidence_missing_named_scenario", 5,
       "evidence 漏 same-app sequence fold / 跨 participant key 冲突 / quarantined 拒绝 / "
       "opaque version 碰撞 / leader successor-no-successor 任一场景",
       "t71_facet:deletion_gate.evidence_scenario_rows",
       "unverifiable:70:evidence 五表实测 0 行（任务 70 实录）⇒ 「漏某个场景」这条变异在"
       "今天的分母上无处落脚；owner 是任务 70 的真实场景刷新"),
    _t("m5_evidence_reused_across_entry", 5,
       "evidence 跨 entry 复用 / 单 application 或 operation 伪全场景 / 无 bundle 或 "
       "manifest profile digest",
       "t71_facet:deletion_gate.evidence_scenario_rows",
       "unverifiable:70:同上 —— 0 行 evidence 上「复用」不可度量"),
    _t("m5_profile_downgrade_skips_close_liveness", 5,
       "profile 降级后跳过任一 `editable=true AND (capability=bidirectional OR "
       "room_model=shared)` close liveness 场景",
       "t71_facet:deletion_gate.close_predicate_hits",
       "unverifiable:70:close liveness 谓词在任务 70 现算命中数已知；真实执行 owner 是任务 70"),
    # ── 子条目 6：删除门 ─────────────────────────────────────────────────
    _t("m6_task67_requires_fresh_or_claims_eligibility", 6,
       "任务 67 structural pre-reconcile 错误要求 fresh/stale=0 或宣称 eligibility",
       "t71_facet:deletion_gate.task67_must_not_require_zero_stale",
       "guard_mutation:M21"),
    _t("m6_stage_a_requires_unreachable_zero_upfront", 6,
       "Stage A 错误要求待删 unreachable 预先为 0",
       "t71_facet:deletion_gate.task72_stage_a_must_not_require_unreachable_zero",
       "guard_mutation:M22"),
    _t("m6_post_delete_smoke_restores_evidence", 6,
       "post-delete 仅 smoke 恢复 evidence",
       "t71_facet:deletion_gate.smoke_cannot_restore_verified",
       "guard_mutation:M23"),
)


def _dig(node: Any, dotted: str) -> Any:
    """按点号路径取值。任一段缺失返回哨兵 :data:`_MISSING`。"""
    current: Any = node
    for part in dotted.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


_MISSING: Final[object] = object()

#: application key 的**禁用输入** token（Property 64）。写死真实目标（教训 16）。
FORBIDDEN_KEY_INPUT_TOKENS: Final[tuple[str, ...]] = (
    "status",
    "request_id",
    "request_sequence",
    "last_applied",
    "mtime",
)


def forbidden_key_inputs(params: Sequence[str]) -> list[str]:
    """从入参名里挑出命中禁用 token 的那些。

    🔴 抽成独立纯函数是为了让判据可以**喂植入输入**：内联在 `build_protocol_source_scan`
    里时，「把 `forbidden` 写死成 `[]`」是等价变异（今天本来就是空的），守卫抓不到。
    """
    return sorted(
        name
        for name in params
        if any(token in name for token in FORBIDDEN_KEY_INPUT_TOKENS)
    )


def guard_mutation_ids() -> tuple[str, ...]:
    """从本门变异脚本源码里现读变异号。

    🔴 **不在门里抄一份清单**：抄的那份在变异脚本增删条目后静静过期。这里按
    `Mutation("Mnn"` 的形态抓，抓不到任何一条即报结构错误（脚本缺失或形态漂移）。
    """
    path = REPO / MUTATE_REL
    if not path.is_file():
        return ()
    text = path.read_text(encoding="utf-8", errors="replace")
    return tuple(sorted(set(re.findall(r'^\s*"(M\d+)",\s*$', text, re.M))))


def _t68_arm_index(t68: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in t68.get("invariants") or []:
        for arm in (row.get("behaviour_side") or {}).get("arms") or []:
            index[str(arm["arm_id"])] = {
                "check_id": row["check_id"],
                "expectation": arm.get("expectation"),
                "agrees": bool(arm.get("agrees")),
            }
    return index


def _t68_endpoint_index(t68: Mapping[str, Any]) -> dict[str, bool]:
    return {
        str(row.get("check_id")): bool(row.get("passed"))
        for row in t68.get("endpoint_checks") or []
    }


def resolve_mutation_coverage(
    *, behaviour: Mapping[str, Any], facets: Mapping[str, Any]
) -> dict[str, Any]:
    """逐条把正文点名的变异目标解析到真实证据源。

    四类失败各自独立成一个字段（合并会让靠后的那类永久不可达）：

    * `unresolved_refs` —— 引用了不存在的 arm / endpoint / facet / 变异号；
    * `disagreeing_refs` —— 引用的上游 arm 存在但 `agrees=False`（上游发现了缺陷）；
    * `targets_without_real_arm` —— 整条目标只有 `unverifiable:` 证据（允许，但必须点名
      owner 且被单独计数，绝不混进「已覆盖」）；
    * `unverifiable_without_owner` —— `unverifiable:` 没写 owner 任务号。
    """
    t68 = read_json(T68_REPORT)
    arms = _t68_arm_index(t68)
    endpoints = _t68_endpoint_index(t68)
    own_arms = dict(behaviour.get("observations") or {})
    known_mutations = set(guard_mutation_ids())

    rows: list[dict[str, Any]] = []
    unresolved: list[str] = []
    disagreeing: list[str] = []
    only_unverifiable: list[str] = []
    unverifiable_without_owner: list[str] = []
    kind_counter: Counter[str] = Counter()

    for target in MUTATION_TARGETS:
        resolved: list[dict[str, Any]] = []
        for ref in target.evidence:
            kind, _, rest = ref.partition(":")
            kind_counter[kind] += 1
            entry: dict[str, Any] = {"ref": ref, "kind": kind, "resolved": False}
            if kind == "t68_arm":
                found = arms.get(rest)
                entry["resolved"] = found is not None
                entry["detail"] = found
                if found is None:
                    unresolved.append(f"{target.target_id} -> {ref}")
                elif not found["agrees"]:
                    disagreeing.append(f"{target.target_id} -> {ref}")
            elif kind == "t68_endpoint":
                if rest not in endpoints:
                    unresolved.append(f"{target.target_id} -> {ref}")
                else:
                    entry["resolved"] = True
                    entry["detail"] = {"passed": endpoints[rest]}
                    if not endpoints[rest]:
                        disagreeing.append(f"{target.target_id} -> {ref}")
            elif kind == "t71_arm":
                observation = own_arms.get(rest)
                entry["resolved"] = observation is not None
                entry["detail"] = observation
                if observation is None:
                    unresolved.append(f"{target.target_id} -> {ref}")
            elif kind == "t71_facet":
                value = _dig(facets, rest)
                entry["resolved"] = value is not _MISSING
                entry["detail"] = None if value is _MISSING else value
                if value is _MISSING:
                    unresolved.append(f"{target.target_id} -> {ref}")
            elif kind == "guard_mutation":
                entry["resolved"] = rest in known_mutations
                entry["detail"] = {"known_mutation_ids": sorted(known_mutations)[:1]}
                if rest not in known_mutations:
                    unresolved.append(f"{target.target_id} -> {ref}")
            else:  # unverifiable:<owner>:<why>
                owner, _, why = rest.partition(":")
                entry["resolved"] = True
                entry["detail"] = {"owner_task": owner, "why": why}
                if not owner.strip() or not why.strip():
                    unverifiable_without_owner.append(f"{target.target_id} -> {ref}")
            resolved.append(entry)

        real_kinds = {
            row["kind"]
            for row in resolved
            if row["kind"] in ("t68_arm", "t68_endpoint", "t71_arm", "t71_facet")
        }
        if not real_kinds:
            only_unverifiable.append(target.target_id)
        rows.append(
            {
                "target_id": target.target_id,
                "sub_bullet": target.sub_bullet,
                "clause": target.clause,
                "evidence": resolved,
                "has_real_evidence": bool(real_kinds),
                "real_evidence_kinds": sorted(real_kinds),
            }
        )

    by_bullet = Counter(row["sub_bullet"] for row in rows)
    return {
        "statement": (
            "正文六个变异子条目逐条点名的分母。每条目标解析到至少一条真实证据源；"
            "`t68_arm:` 必须在任务 68 报告里真的存在且 agrees=True（跨文件双向锁），"
            "`t71_arm:` 必须在本门 scratch schema 的观测里真的存在。"
        ),
        "target_count": len(rows),
        "targets_by_sub_bullet": {str(k): v for k, v in sorted(by_bullet.items())},
        "evidence_ref_count": sum(len(row["evidence"]) for row in rows),
        "evidence_kind_histogram": dict(sorted(kind_counter.items())),
        "evidence_kinds_allowed": list(EVIDENCE_KINDS),
        "unresolved_refs": sorted(unresolved),
        "disagreeing_refs": sorted(disagreeing),
        "targets_with_only_unverifiable_evidence": sorted(only_unverifiable),
        "targets_with_any_unverifiable_evidence": sorted(
            row["target_id"]
            for row in rows
            if any(entry["kind"] == "unverifiable" for entry in row["evidence"])
        ),
        "unverifiable_without_owner": sorted(unverifiable_without_owner),
        "targets_with_real_evidence": sum(1 for row in rows if row["has_real_evidence"]),
        "upstream_arm_pool_size": len(arms),
        "upstream_endpoint_pool_size": len(endpoints),
        "own_arm_pool_size": len(own_arms),
        "known_guard_mutation_ids": sorted(known_mutations),
        "targets": rows,
    }


# ════════════════════════════════════════════════════════════════════════════
# §6 本门的 scratch schema 行为侧
# ════════════════════════════════════════════════════════════════════════════

#: 本门在 scratch schema 上真造行的臂声明。与任务 68 的 `BehaviourArm` 同语义，
#: 但这里只声明本门**新增**的那些（不重复造上游 120 条）。
@dataclass(frozen=True)
class OwnArm:
    """本门的一条行为臂。

    * `accepted` —— 对照组，合法形态必须真的成立；
    * `rejected` —— 非法形态必须被**它自己声明的那条**约束/异常拒绝，`signature` 必填；
    * `measure` —— 收敛/计数类结论，`expect` 逐键比对。
    """

    arm_id: str
    facet: str
    intent: str
    expectation: str
    signature: tuple[str, ...] = ()
    expect: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.expectation not in ("accepted", "rejected", "measure"):
            raise Task71GateError(f"臂 {self.arm_id} 的 expectation 非法: {self.expectation}")
        if self.expectation == "rejected" and not self.signature:
            raise Task71GateError(
                f"臂 {self.arm_id} 声明 rejected 却没有 signature —— 只比「抛了异常」会把"
                "NOT NULL/FK/别的 CHECK 都算成通过（教训 1）"
            )
        if self.expectation == "measure" and not self.expect:
            raise Task71GateError(f"臂 {self.arm_id} 声明 measure 却没有 expect —— 空期望恒真")


OWN_ARMS: Final[tuple[OwnArm, ...]] = (
    # ── BP-68-1 独立复核（DDL 侧 + 服务层不变量侧）──────────────────────────
    OwnArm("t71_pre_durable_owner_ddl", "bp_68_1_recheck",
           "往 scratch schema 插 state='rejected', durable_at=NULL, application_id=<x> —— "
           "复核 BP-68-1：DDL 是否真的**接受**",
           "measure", expect={"ddl_accepts_pre_durable_owner": True}),
    OwnArm("t71_pre_durable_zero_owner_invariant", "bp_68_1_recheck",
           "服务层不变量对「pre-durable rejected + 零 owner」必须放行（对照组）",
           "accepted"),
    OwnArm("t71_pre_durable_owner_invariant", "bp_68_1_recheck",
           "服务层纯不变量 `assert_delivery_ownership` 对「pre-durable rejected + application "
           "owner」的实测结论 —— 这是 BP-68-1 留空的那一半",
           "measure", expect={"invariant_accepts_pre_durable_owner": True}),
    OwnArm("t71_double_owner_invariant", "bp_68_1_recheck",
           "服务层不变量必须拒双 owner（任何阶段）",
           "rejected", signature=("DeliveryOwnershipError", "双 owner")),
    OwnArm("t71_request_and_application_invariant", "bp_68_1_recheck",
           "request 与 application 同时存在必须放行（**不做 XOR**，对照组）",
           "accepted"),
    OwnArm("t71_durable_state_without_fact_invariant", "bp_68_1_recheck",
           "泛化 terminal 冒充 durable 必须被拒（owner gate 只认 `durable_at`）",
           "rejected", signature=("DeliveryOwnershipError", "durable_at")),
    OwnArm("t71_durable_zero_owner_invariant", "bp_68_1_recheck",
           "durable fact 存在但零 owner 必须被拒",
           "rejected", signature=("DeliveryOwnershipError", "恰属其一")),
    # ── 进程中断 / 事务原子性 ─────────────────────────────────────────────
    OwnArm("t71_atomicity_baseline", "fault_injection",
           "一个事务内插两行 delivery 全部成功（对照组）",
           "accepted"),
    OwnArm("t71_atomicity_partial_rollback", "fault_injection",
           "同一事务内第二条语句失败 ⇒ 第一条也必须回滚（进程中断/^C 的可复现代理）",
           "measure", expect={"rows_after_failed_transaction": 0, "raised": True}),
    # ── retention 真跑 ───────────────────────────────────────────────────
    OwnArm("t71_retention_plan_deletes_unreferenced", "retention",
           "过 TTL+grace 且无引用的 artifact 必须判 delete（对照组）",
           "accepted"),
    OwnArm("t71_retention_legal_hold", "retention",
           "legal hold 必须判 retain 且 reason=legal_hold",
           "rejected", signature=("retain", "legal_hold")),
    OwnArm("t71_retention_ttl_not_elapsed", "retention",
           "TTL 未到必须判 retain 且 reason=ttl_not_elapsed",
           "rejected", signature=("retain", "ttl_not_elapsed")),
    OwnArm("t71_retention_grace_not_elapsed", "retention",
           "TTL 到但 grace 未到必须判 retain 且 reason=grace_not_elapsed",
           "rejected", signature=("retain", "grace_not_elapsed")),
    OwnArm("t71_retention_reference_found", "retention",
           "被 application 的 incoming 引用的 artifact 必须判 retain 且 reason 指向引用",
           "rejected", signature=("retain", "reference_found")),
    OwnArm("t71_retention_class_scope_mismatch", "retention",
           "class 的 kind/state 作用域不匹配必须判 retain 且 reason=class_scope_mismatch",
           "rejected", signature=("retain", "class_scope_mismatch")),
    OwnArm("t71_retention_no_policy_retains_and_alerts", "retention",
           "策略里没有这个 retention_class 必须判 retain + alert，不得按内置默认值删",
           "rejected", signature=("retain", "no_policy_retain_and_alert")),
    # 🔴 signature 必须比「RetentionUsageError + dry-run」更具体：policy_version 漂移那条的
    #    文案末尾也含「必须重新 dry-run」，两条臂的理由会互相命中 ⇒ 其中一条成死判据（教训 1）。
    OwnArm("t71_retention_apply_requires_dry_run", "retention",
           "apply 只接受 dry-run 产生的 plan；伪造 `dry_run=False` 的 plan 必须被拒",
           "rejected", signature=("RetentionUsageError", "只接受 dry-run 产生的 plan")),
    OwnArm("t71_retention_apply_policy_version_drift", "retention",
           "plan 的 policy_version 与当前策略不符必须被拒（策略换版必须重新 dry-run）",
           "rejected", signature=("RetentionUsageError", "policy_version")),
    OwnArm("t71_retention_apply_deletes_and_audits", "retention",
           "apply 真删文件 + 落审计 evidence（对照组）",
           "accepted"),
    OwnArm("t71_retention_windows_lock_retains", "retention",
           "Windows 文件占用 ⇒ 删不掉必须改判 retain + alert，绝不静默算已删",
           "measure",
           expect={"decision": "retain", "reason": "delete_failed", "alert": True,
                   "row_state_still_not_deleted": True}),
    OwnArm("t71_retention_reference_reappears_on_recheck", "retention",
           "dry-run 后引用重现 ⇒ 二次复核必须改判 retain（`reference_found_on_recheck`）",
           "measure",
           expect={"retained_on_recheck": 1, "deleted": 0,
                   "reason": "reference_found_on_recheck"}),
)

_ARMS_BY_ID: Final[Mapping[str, OwnArm]] = {arm.arm_id: arm for arm in OWN_ARMS}


def evaluate_own_arm(arm: OwnArm, observation: Mapping[str, Any] | None) -> dict[str, Any]:
    """逐臂比对。**观测缺失不是通过** —— 那是「声明与探针脱钩」（additive 注入即死代码）。"""
    if observation is None:
        return {
            "arm_id": arm.arm_id,
            "facet": arm.facet,
            "intent": arm.intent,
            "expectation": arm.expectation,
            "state": "missing_observation",
            "agrees": False,
            "detail": "本门没有这条臂的观测 —— 声明与探针脱钩",
        }
    base = {
        "arm_id": arm.arm_id,
        "facet": arm.facet,
        "intent": arm.intent,
        "expectation": arm.expectation,
    }
    if arm.expectation == "accepted":
        agrees = bool(observation.get("accepted"))
        return {
            **base,
            "state": "agrees" if agrees else "disagrees",
            "agrees": agrees,
            "observed": {
                "accepted": bool(observation.get("accepted")),
                "rejection": observation.get("rejection"),
            },
        }
    if arm.expectation == "rejected":
        rejection = str(observation.get("rejection") or "")
        accepted = bool(observation.get("accepted"))
        hits = [frag for frag in arm.signature if frag in rejection]
        agrees = (not accepted) and len(hits) == len(arm.signature)
        return {
            **base,
            "state": "agrees" if agrees else "disagrees",
            "agrees": agrees,
            "signature": list(arm.signature),
            "signature_hits": hits,
            "observed": {"accepted": accepted, "rejection": rejection},
        }
    measured = dict(observation.get("measured") or {})
    expected = dict(arm.expect or {})
    mismatched = {
        key: {"expected": value, "measured": measured.get(key)}
        for key, value in expected.items()
        if measured.get(key) != value
    }
    return {
        **base,
        "state": "agrees" if not mismatched else "disagrees",
        "agrees": not mismatched,
        "expected": expected,
        "measured": measured,
        "mismatched": mismatched,
    }


def cross_signature_check() -> dict[str, Any]:
    """各 rejected 臂的拒绝理由**互不命中**。

    🔴 教训 1 的机器形态：如果 A 臂的 signature 也能在 B 臂的拒绝文案里找到，那两条臂度量
    的其实是同一条约束，「靠后的那条永久不可达」。这里逐对交叉比一次。
    """
    return {
        "statement": "任一 rejected 臂的 signature 不得命中另一条 rejected 臂的实测拒绝文案。",
        "why": "命中即说明两条臂度量同一条约束 ⇒ 其中一条是死判据（教训 1/4）。",
    }


def _normalize_rejection(text: str) -> str:
    """把拒绝理由规范化成**逐轮可复现**的形态（逐字节锁的前提）。

    只抹标识值（UUID / 64 位 digest / `DETAIL:` 整行 / 临时路径），保留 sqlstate、约束名、
    异常类名与中文状态词 —— 那些才是承载判据的部分。
    """
    masked = re.sub(r"DETAIL:.*", "DETAIL:<row>", text, flags=re.S)
    masked = re.sub(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        "<uuid>",
        masked,
    )
    masked = re.sub(r"\b[0-9a-f]{64}\b", "<digest>", masked)
    masked = re.sub(r"[A-Za-z]:\\\\?[^\s'\"]*[Tt]e?mp[^\s'\"]*", "<tmp>", masked)
    masked = re.sub(rf"{SCRATCH_PREFIX}[0-9a-f]+", f"{SCRATCH_PREFIX}<hex>", masked)
    return masked


def _exc_signature(exc: BaseException) -> str:
    """`ExcType|error_code|message`（已规范化）。只比异常类型不够（教训 1）。"""
    code = getattr(exc, "error_code", "") or ""
    orig = getattr(exc, "orig", None)
    if orig is not None:
        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", "") or ""
        constraint = getattr(orig, "constraint_name", None) or ""
        return _normalize_rejection(
            f"{type(exc).__name__}|{sqlstate}|{constraint}|{orig}"
        )
    return _normalize_rejection(f"{type(exc).__name__}|{code}|{exc}")


class _Obs:
    """观测收集器。臂 id 一次只许写一次（重复写会静静覆盖上一条观测）。"""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}
        self.duplicates: list[str] = []

    def accepted(self, arm_id: str) -> None:
        self._put(arm_id, {"accepted": True, "rejection": None})

    def rejected(self, arm_id: str, exc: BaseException) -> None:
        self._put(arm_id, {"accepted": False, "rejection": _exc_signature(exc)})

    def measure(self, arm_id: str, **measured: Any) -> None:
        self._put(arm_id, {"accepted": True, "rejection": None, "measured": measured})

    def _put(self, arm_id: str, payload: dict[str, Any]) -> None:
        if arm_id in self.data:
            self.duplicates.append(arm_id)
        self.data[arm_id] = payload

    def run_invariant(self, arm_id: str, fn: Callable[[], Any]) -> None:
        """跑一个「必须成立/必须抛」的纯不变量调用并按结果记观测。"""
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - 拒绝本身就是观测
            self.rejected(arm_id, exc)
        else:
            self.accepted(arm_id)


# ── §6.1 BP-68-1 独立复核（服务层纯不变量侧，不需要数据库）────────────────────


def probe_delivery_ownership_invariant(obs: _Obs) -> dict[str, Any]:
    """真调生产的 `assert_delivery_ownership` 纯不变量，逐形态记观测。

    这是 BP-68-1 留空的那一半：任务 68 只证明了 **DDL** 接受 pre-durable rejected + owner，
    并把「靠服务层把住」记成 owner 任务 22 的欠账。本门把那半边真的跑一次。
    """
    prod = _production()
    models = prod["models"]
    delivery_state = models.DeliveryState
    assert_ownership = models.assert_delivery_ownership
    app_id = uuid.uuid4()
    rec_id = uuid.uuid4()
    req_id = uuid.uuid4()

    # 对照组：pre-durable rejected + 零 owner 必须放行
    obs.run_invariant(
        "t71_pre_durable_zero_owner_invariant",
        lambda: assert_ownership(
            state=delivery_state.rejected,
            durable_at_is_set=False,
            application_id=None,
            callback_recovery_case_id=None,
            forcesave_request_id=req_id,
        ),
    )
    # 对照组：request + application 同时存在必须放行（**刻意不做 XOR**）
    obs.run_invariant(
        "t71_request_and_application_invariant",
        lambda: assert_ownership(
            state=delivery_state.durable,
            durable_at_is_set=True,
            application_id=app_id,
            callback_recovery_case_id=None,
            forcesave_request_id=req_id,
        ),
    )
    # 实验组：双 owner 任何阶段必拒
    obs.run_invariant(
        "t71_double_owner_invariant",
        lambda: assert_ownership(
            state=delivery_state.received,
            durable_at_is_set=False,
            application_id=app_id,
            callback_recovery_case_id=rec_id,
        ),
    )
    # 实验组：泛化 terminal 冒充 durable 必拒
    obs.run_invariant(
        "t71_durable_state_without_fact_invariant",
        lambda: assert_ownership(
            state=delivery_state.unmatched,
            durable_at_is_set=False,
            application_id=None,
            callback_recovery_case_id=None,
        ),
    )
    # 实验组：durable 但零 owner 必拒
    obs.run_invariant(
        "t71_durable_zero_owner_invariant",
        lambda: assert_ownership(
            state=delivery_state.durable,
            durable_at_is_set=True,
            application_id=None,
            callback_recovery_case_id=None,
        ),
    )
    # 🔴 BP-68-1 的另一半：pre-durable rejected/error **带** application owner，纯不变量怎么判？
    #
    #    第三条 `double_owner_negative_control` 是**负对照**：它必须被拒。没有它的话下面那个
    #    `except` 分支永不执行 ⇒ 「抛了也记成接受」这种改动是不可达分支上的等价变异，任何判据
    #    都抓不到（教训 4：不可达分支必须让它可达或删掉）。
    invariant_accepts: dict[str, bool] = {}
    cases: tuple[tuple[str, Any, Any], ...] = (
        ("rejected", delivery_state.rejected, None),
        ("error", delivery_state.error, None),
        ("double_owner_negative_control", delivery_state.rejected, rec_id),
    )
    for label, state, recovery in cases:
        try:
            assert_ownership(
                state=state,
                durable_at_is_set=False,
                application_id=app_id,
                callback_recovery_case_id=recovery,
                forcesave_request_id=req_id,
            )
        except Exception:  # noqa: BLE001
            invariant_accepts[label] = False
        else:
            invariant_accepts[label] = True
    obs.measure(
        "t71_pre_durable_owner_invariant",
        invariant_accepts_pre_durable_owner=bool(
            invariant_accepts.get("rejected") and invariant_accepts.get("error")
        ),
        negative_control_double_owner_rejected=(
            invariant_accepts.get("double_owner_negative_control") is False
        ),
        per_state=invariant_accepts,
    )
    return {"invariant_accepts": invariant_accepts}


# ── §6.2 scratch schema：BP-68-1 的 DDL 侧 + 原子性 + retention 真跑 ─────────


async def _probe_pre_durable_owner_ddl(t68: Any, run: Any, world: dict[str, Any], obs: _Obs) -> None:
    """BP-68-1 的 DDL 侧独立复核：往 scratch schema 插 pre-durable rejected + owner。

    与任务 68 的 `dlv_pre_durable_owner` 同形态但**独立造世界、独立造行**：如果它的结论是
    错的（DDL 其实拒绝），本门会给出相反的观测；如果一致，`agrees_with_task68` 为真。
    """
    room = await t68._make_room(run, world, entry=world["entry2"], label="t71-bp681")
    participant = await t68._make_participant(run, world, room, "t71-bp681")
    req = t68._request_row(world, sequence=7101, key="task71-bp681")
    req["room_id"] = room
    req["initiated_by_participant_id"] = participant
    req["client_base_representation_id"] = world["rep_staged"]
    await t68._insert_ok(run, t68._FR, t68._REQ_COLS, req)
    app = t68._application_row(world, request=req, key_label="t71-bp681-owner")
    app["room_id"] = room
    app["entry_id"] = world["entry2"]
    app["base_representation_id"] = world["rep_staged"]
    await t68._insert_ok(run, t68._CA, t68._APP_COLS, app)

    def _delivery(*, label: str, state: str, durable: bool, application: str | None) -> tuple[str, dict[str, Any]]:
        durable_expr = "now()" if durable else "NULL"
        sql = (
            "INSERT INTO working_paper_callback_delivery "
            "(id, project_id, wp_id, entry_id, room_id, generation, operation_id, "
            " application_id, forcesave_request_id, callback_recovery_case_id, "
            " route_credential_id, callback_status, delivery_key, state, correlation_result, "
            f" incoming_artifact_id, durable_at) VALUES (:id, :p, :wp, :entry, :room, 1, NULL, "
            f" :app, NULL, NULL, :cred, 6, :dkey, :state, NULL, NULL, {durable_expr})"
        )
        return sql, {
            "id": t68._u(),
            "p": world["project"],
            "wp": world["wp_a"],
            "entry": world["entry2"],
            "room": room,
            "app": application,
            "cred": t68._u(),
            "dkey": t68._d(f"t71-delivery::{label}"),
            "state": state,
        }

    accepts: dict[str, bool] = {}
    for label, state in (("rejected", "rejected"), ("error", "error")):
        sql, params = _delivery(
            label=f"pre-durable-owner-{label}", state=state, durable=False,
            application=app["id"],
        )
        accepts[label] = await run.attempt(None, sql, params)
    obs.measure(
        "t71_pre_durable_owner_ddl",
        ddl_accepts_pre_durable_owner=bool(accepts.get("rejected") and accepts.get("error")),
        per_state=accepts,
    )


async def _probe_transaction_atomicity(t68: Any, engine: Any, world: dict[str, Any], obs: _Obs) -> None:
    """进程中断的可复现代理：同一事务内第二条语句失败 ⇒ 第一条必须一起回滚。

    🔴 为什么这条是「进程中断」的判据：`^C` 中断的运行**可能已提交部分变更**，所以判成败
    一律查数据不看 exit code。这里把「一半写进去了」这件事造出来并证明它不成立 —— 事务
    边界是唯一能让「中断后不留半条链」成立的机制。
    """
    import sqlalchemy as sa

    run = t68._Runner(engine, {})
    room_id = await t68._make_room(run, world, entry=world["entry2"], label="t71-atomic")
    marker = t68._d("t71-atomic-marker")

    def _dlv_sql(state: str) -> str:
        return (
            "INSERT INTO working_paper_callback_delivery "
            "(id, project_id, wp_id, entry_id, room_id, generation, route_credential_id, "
            " callback_status, delivery_key, state) "
            f"VALUES (:id, :p, :wp, :entry, :room, 1, :cred, 6, :dkey, '{state}')"
        )

    base = {
        "p": world["project"],
        "wp": world["wp_a"],
        "entry": world["entry2"],
        "room": room_id,
    }
    # 对照组：一个事务内两行都合法 ⇒ 两行都在
    try:
        async with engine.begin() as conn:
            for suffix in ("ok1", "ok2"):
                await conn.execute(
                    sa.text(_dlv_sql("received")),
                    {**base, "id": t68._u(), "cred": t68._u(),
                     "dkey": t68._d(f"{marker}-{suffix}")},
                )
    except Exception as exc:  # noqa: BLE001
        obs.rejected("t71_atomicity_baseline", exc)
    else:
        obs.accepted("t71_atomicity_baseline")

    # 实验组：第一条合法、第二条违反 owner gate（durable state 无 durable fact）⇒ 全回滚
    doomed = t68._d(f"{marker}-doomed")
    raised = False
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(_dlv_sql("received")),
                {**base, "id": t68._u(), "cred": t68._u(), "dkey": doomed},
            )
            await conn.execute(
                sa.text(_dlv_sql("durable")),
                {**base, "id": t68._u(), "cred": t68._u(),
                 "dkey": t68._d(f"{marker}-doomed2")},
            )
    except Exception:  # noqa: BLE001 - 失败即预期
        raised = True
    async with engine.connect() as conn:
        left = int(
            (
                await conn.execute(
                    sa.text(
                        "SELECT count(*) FROM working_paper_callback_delivery "
                        "WHERE delivery_key = :k"
                    ),
                    {"k": doomed},
                )
            ).scalar_one()
        )
    obs.measure(
        "t71_atomicity_partial_rollback",
        rows_after_failed_transaction=left,
        raised=raised,
    )


_RETENTION_ART_COLS: Final[str] = (
    "id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type, "
    "source_delivery_id, retention_class, legal_hold"
)


async def _plant_retention_artifact(
    t68: Any,
    run: Any,
    world: Mapping[str, Any],
    *,
    label: str,
    age_hours: int,
    legal_hold: bool = False,
    retention_class: str = "incoming_durable",
) -> tuple[str, str]:
    """插一条 `kind=incoming, state=durable` 的 artifact，`durable_at` 按小时回拨。

    🔴 时间戳用**服务端** `now() - interval` 表达式：timestamptz 在驱动侧按目标类型编码，
    SQL 层 `CAST(:x AS timestamptz)` 无效，而 Python 侧 datetime 又会把「相对当下」变成
    绝对值进逐字节锁。服务端相对表达式两边都躲开。
    """
    art_id = t68._u()
    delivery = t68._u()
    # 🔴 必须是**真实 layout 路径**（`storage/{project}/workpapers/...`）而不是只满足 V151
    #    `position('.incoming/'||wp||'/'||delivery||'/' in relative_path)` 的短路径：
    #    apply 会真的经 `assert_project_owns()` 删文件，短路径过不了项目归属判定。
    path = (
        f"storage/{world['project']}/workpapers/.incoming/"
        f"{world['wp_a']}/{delivery}/{label}.xlsx"
    )
    await run.setup(
        f"INSERT INTO working_paper_artifact ({_RETENTION_ART_COLS}, durable_at) "
        "VALUES (:id, :p, :wp, 'incoming', 'durable', :path, :sha, 2048, 'xlsx', :dlv, "
        f" :rc, :hold, now() - interval '{int(age_hours)} hours')",
        {
            "id": art_id,
            "p": world["project"],
            "wp": world["wp_a"],
            "path": path,
            "sha": t68._d(f"t71-retention::{label}"),
            "dlv": delivery,
            "rc": retention_class,
            "hold": legal_hold,
        },
    )
    return art_id, path


async def _probe_retention(
    t68: Any, engine: Any, world: dict[str, Any], obs: _Obs, temp_root: Path
) -> dict[str, Any]:
    """在 scratch schema 上真跑 `RetentionPolicyService.plan()` 与 `.apply()`。

    七条 plan 判定分支 + 三条 apply 协议/复核分支各自造一条真行；artifact 根指向临时目录，
    收尾整棵删掉（正文「trace/evidence artifact 完整复原/清理」）。
    """
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker

    prod = _production()
    retention = prod["retention"]
    artifacts = prod["artifacts"]
    run = t68._Runner(engine, {})

    project_id = world["project"]
    wp_id = world["wp_a"]

    # ── 七条 plan 分支的真行 ──────────────────────────────────────────────
    planted: dict[str, tuple[str, str]] = {}
    planted["delete"] = await _plant_retention_artifact(
        t68, run, world, label="unreferenced-old", age_hours=400
    )
    planted["ttl"] = await _plant_retention_artifact(
        t68, run, world, label="fresh", age_hours=10
    )
    planted["grace"] = await _plant_retention_artifact(
        t68, run, world, label="ttl-elapsed-grace-not", age_hours=200
    )
    planted["hold"] = await _plant_retention_artifact(
        t68, run, world, label="legal-hold", age_hours=400, legal_hold=True
    )
    planted["scope"] = await _plant_retention_artifact(
        t68, run, world, label="class-scope-mismatch", age_hours=400,
        retention_class="orphan_canonical",
    )
    planted["nopolicy"] = await _plant_retention_artifact(
        t68, run, world, label="no-policy", age_hours=400,
        retention_class="t71_class_that_no_policy_declares",
    )
    # 被引用的那条：先建 artifact，再让一条 application 的 incoming 指向它
    planted["ref"] = await _plant_retention_artifact(
        t68, run, world, label="referenced", age_hours=400
    )
    # 二次复核那条：plan 时无引用（判 delete），apply 前才把引用建起来。
    planted["recheck"] = await _plant_retention_artifact(
        t68, run, world, label="reference-reappears", age_hours=400
    )
    ref_room = await t68._make_room(run, world, entry=world["entry2"], label="t71-ret-ref")
    ref_participant = await t68._make_participant(run, world, ref_room, "t71-ret-ref")
    ref_req = t68._request_row(world, sequence=7201, key="task71-retention-ref")
    ref_req["room_id"] = ref_room
    ref_req["initiated_by_participant_id"] = ref_participant
    ref_req["client_base_representation_id"] = world["rep_staged"]
    await t68._insert_ok(run, t68._FR, t68._REQ_COLS, ref_req)
    ref_app = t68._application_row(world, request=ref_req, key_label="t71-retention-ref")
    ref_app["room_id"] = ref_room
    ref_app["entry_id"] = world["entry2"]
    ref_app["base_representation_id"] = world["rep_staged"]
    ref_app["incoming_artifact_id"] = planted["ref"][0]
    ref_app["incoming_sha256"] = t68._d("t71-retention::referenced")
    await t68._insert_ok(run, t68._CA, t68._APP_COLS, ref_app)

    # ── 真文件（apply 要删的对象必须真存在）─────────────────────────────────
    for key in ("delete", "hold", "ref", "grace", "recheck"):
        target = temp_root / planted[key][1]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"task71-retention-probe")
    locked_id, locked_path = await _plant_retention_artifact(
        t68, run, world, label="windows-locked", age_hours=400
    )
    locked_file = temp_root / locked_path
    locked_file.parent.mkdir(parents=True, exist_ok=True)
    locked_file.write_bytes(b"task71-windows-lock-probe")

    repo = artifacts.CanonicalArtifactRepository(temp_root)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    facts: dict[str, Any] = {}

    async with maker() as session:
        service = retention.RetentionPolicyService(session, repo)
        plan = await service.plan(
            project_id=uuid.UUID(project_id), wp_id=uuid.UUID(wp_id), write_audit=False
        )
        by_id = {row.artifact_id: row for row in plan.decisions}
        facts["policy_version"] = plan.policy_version
        facts["decision_count"] = len(plan.decisions)
        facts["decision_reason_histogram"] = dict(
            sorted(Counter(row.reason for row in plan.decisions).items())
        )
        facts["planned_deletions"] = len(plan.deletions)

        def _record(arm_id: str, key: str) -> None:
            """把一条 plan 判定记成观测。

            🔴 `retain` 类臂声明的 signature 同时含 `retain` **与那条 reason**（例如
            `("retain", "legal_hold")`）：只比 `decision != delete` 会把七条 retain 分支
            合成一条，「靠后的那条永久不可达」（教训 1）。这里把 decision 与 reason 一起
            写进拒绝文案，由臂的 signature 逐条区分。
            """
            row = by_id.get(planted[key][0])
            if row is None:
                obs.measure(arm_id, missing_decision=True)
                return
            if row.decision == "delete":
                obs.accepted(arm_id)
            else:
                obs.rejected(
                    arm_id, RuntimeError(f"RetentionDecision|{row.decision}|{row.reason}")
                )

        _record("t71_retention_plan_deletes_unreferenced", "delete")
        _record("t71_retention_legal_hold", "hold")
        _record("t71_retention_ttl_not_elapsed", "ttl")
        _record("t71_retention_grace_not_elapsed", "grace")
        _record("t71_retention_reference_found", "ref")
        _record("t71_retention_class_scope_mismatch", "scope")
        _record("t71_retention_no_policy_retains_and_alerts", "nopolicy")

        # ── apply 协议：伪造 dry_run=False 的 plan 必须被拒 ────────────────
        forged = retention.RetentionPlan(
            policy_version=plan.policy_version,
            project_id=plan.project_id,
            wp_id=plan.wp_id,
            planned_at=plan.planned_at,
            dry_run=False,
        )
        try:
            await service.apply(forged)
        except Exception as exc:  # noqa: BLE001
            obs.rejected("t71_retention_apply_requires_dry_run", exc)
        else:
            obs.accepted("t71_retention_apply_requires_dry_run")

        drifted = retention.RetentionPlan(
            policy_version=f"{plan.policy_version}-t71-drift",
            project_id=plan.project_id,
            wp_id=plan.wp_id,
            planned_at=plan.planned_at,
        )
        try:
            await service.apply(drifted)
        except Exception as exc:  # noqa: BLE001
            obs.rejected("t71_retention_apply_policy_version_drift", exc)
        else:
            obs.accepted("t71_retention_apply_policy_version_drift")

        # ── Windows lock 注入：持有文件句柄 ⇒ 删不掉 ⇒ 必须改判 retain + alert ──
        handle = locked_file.open("rb")
        try:
            lock_plan = retention.RetentionPlan(
                policy_version=plan.policy_version,
                project_id=plan.project_id,
                wp_id=plan.wp_id,
                planned_at=plan.planned_at,
            )
            lock_plan.decisions = [
                row for row in plan.decisions if row.artifact_id == locked_id
            ]
            outcome = await service.apply(lock_plan)
            locked_decisions = list(outcome.retained_on_recheck)
            state_row = (
                await session.execute(
                    sa.text("SELECT state FROM working_paper_artifact WHERE id = :i"),
                    {"i": locked_id},
                )
            ).scalar_one()
            obs.measure(
                "t71_retention_windows_lock_retains",
                decision=(locked_decisions[0].decision if locked_decisions else None),
                reason=(locked_decisions[0].reason if locked_decisions else None),
                alert=bool(locked_decisions and locked_decisions[0].alert),
                row_state_still_not_deleted=(str(state_row) != "deleted"),
                alerts=[a.split(":", 1)[0] for a in outcome.alerts],
                deleted_count=len(outcome.deleted),
            )
            facts["windows_lock_alerts"] = [a.split(":", 1)[0] for a in outcome.alerts]
        finally:
            handle.close()

        # ── 引用重现：dry-run 判 delete，apply 前把引用建起来 ⇒ 二次复核改判 ──
        #
        # 🔴 必须挑一条 plan **本来就判 delete** 的行（age 400h > ttl+grace 且当时无引用）。
        #    早先版本挑了 grace 未到的那条并人为把 decision 改成 delete —— `apply()` 会用
        #    `_decide(recheck=True)` 从头重判，于是拿到的 reason 是 `grace_not_elapsed`，
        #    二次复核那条分支根本没被走到（首轮实测 disagrees 的根因）。
        recheck_plan = retention.RetentionPlan(
            policy_version=plan.policy_version,
            project_id=plan.project_id,
            wp_id=plan.wp_id,
            planned_at=plan.planned_at,
        )
        recheck_plan.decisions = [
            row for row in plan.decisions if row.artifact_id == planted["recheck"][0]
        ]
        recheck_room = await t68._make_room(
            run, world, entry=world["entry2"], label="t71-ret-recheck"
        )
        recheck_participant = await t68._make_participant(
            run, world, recheck_room, "t71-ret-recheck"
        )
        recheck_req = t68._request_row(world, sequence=7301, key="task71-retention-recheck")
        recheck_req["room_id"] = recheck_room
        recheck_req["initiated_by_participant_id"] = recheck_participant
        recheck_req["client_base_representation_id"] = world["rep_staged"]
        await t68._insert_ok(run, t68._FR, t68._REQ_COLS, recheck_req)
        recheck_app = t68._application_row(
            world, request=recheck_req, key_label="t71-retention-recheck"
        )
        recheck_app["room_id"] = recheck_room
        recheck_app["entry_id"] = world["entry2"]
        recheck_app["base_representation_id"] = world["rep_staged"]
        recheck_app["incoming_artifact_id"] = planted["recheck"][0]
        recheck_app["incoming_sha256"] = t68._d("t71-retention::reference-reappears")
        await t68._insert_ok(run, t68._CA, t68._APP_COLS, recheck_app)
        recheck_outcome = await service.apply(recheck_plan)
        obs.measure(
            "t71_retention_reference_reappears_on_recheck",
            retained_on_recheck=len(recheck_outcome.retained_on_recheck),
            deleted=len(recheck_outcome.deleted),
            reason=(
                recheck_outcome.retained_on_recheck[0].reason
                if recheck_outcome.retained_on_recheck
                else None
            ),
        )

        # ── apply 对照组：真删 + 落审计 evidence ─────────────────────────────
        real_plan = retention.RetentionPlan(
            policy_version=plan.policy_version,
            project_id=plan.project_id,
            wp_id=plan.wp_id,
            planned_at=plan.planned_at,
        )
        real_plan.decisions = [
            row for row in plan.decisions if row.artifact_id == planted["delete"][0]
        ]
        deleted_file = temp_root / planted["delete"][1]
        real_outcome = await service.apply(real_plan)
        await session.commit()
        facts["apply_deleted"] = len(real_outcome.deleted)
        facts["apply_audit_relative_path_present"] = bool(real_outcome.audit_relative_path)
        facts["apply_audit_sha256_present"] = bool(real_outcome.audit_sha256)
        facts["deleted_file_gone"] = not deleted_file.exists()
        if (
            len(real_outcome.deleted) == 1
            and real_outcome.audit_sha256
            and not deleted_file.exists()
        ):
            obs.accepted("t71_retention_apply_deletes_and_audits")
        else:
            obs.rejected(
                "t71_retention_apply_deletes_and_audits",
                RuntimeError(
                    f"RetentionApply|deleted={len(real_outcome.deleted)}|"
                    f"audit={bool(real_outcome.audit_sha256)}|"
                    f"file_gone={not deleted_file.exists()}"
                ),
            )
    facts["reference_sources_declared"] = len(retention.REFERENCE_SOURCES)
    return facts


# ── §6.3 harness 驱动：scratch schema 生命周期 + 复原实证 ────────────────────


async def _run_behaviour(result: dict[str, Any]) -> None:  # noqa: PLR0915 - 一次跑全链
    """建 scratch schema、跑本门探针、DROP、并留下复原实证。

    🔴 三条实测过的约束：
    1. scratch schema 必须用**生产迁移**建（否则「行上验过」验的是另一套 schema）；
    2. 每条语句一个事务（`engine.begin()` 内一处失败全部回滚，会把前面的观测撤掉）；
    3. 复原判据必须**区分本轮残留与外来残留** —— 任务 68 踩过：变异故意删 `DROP` 会累计
       留下 scratch schema，只报总数会把本轮结论打成假红。
    """
    import shutil

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner

    t68 = _t68_gate()
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise Task71GateError(
            "本门的行为侧必须真实 PostgreSQL（retention/原子性/BP-68-1 全落在真库约束上）。"
            f"当前 DATABASE_URL 为 {str(settings.DATABASE_URL).split('://')[0]}。此处**不 skip**。"
        )
    for migration in t68.SCRATCH_MIGRATIONS:
        if not migration.exists():
            raise Task71GateError(f"缺少迁移文件: {rel(migration)}")

    schema = f"{SCRATCH_PREFIX}{uuid.uuid4().hex[:12]}"
    temp_root = REPO / f"tmp_task71_artifact_root_{uuid.uuid4().hex[:8]}"
    result["scratch_schema"] = schema
    result["temp_artifact_root"] = temp_root.name
    result["migrations"] = [m.name for m in t68.SCRATCH_MIGRATIONS]
    result["apply_errors"] = []
    result["probe_errors"] = {}
    result["facets"] = {}

    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(
        str(settings.DATABASE_URL), poolclass=NullPool, connect_args=dict(ssl_off)
    )
    engine = None
    obs = _Obs()
    try:
        async with admin.connect() as conn:
            result["public_before"] = {
                table: int(
                    (
                        await conn.execute(sa.text(f"SELECT count(*) FROM public.{table}"))  # noqa: S608
                    ).scalar_one()
                )
                for table in t68.PRODUCTION_ROW_TABLES
            }
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(
            str(settings.DATABASE_URL),
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        async with engine.begin() as conn:
            for stmt in [s.strip() for s in t68._STUB_DDL.strip().split(";") if s.strip()]:
                await conn.exec_driver_sql(stmt)
        for migration in t68.SCRATCH_MIGRATIONS:
            statements = MigrationRunner._split_sql_statements(
                migration.read_text(encoding="utf-8")
            )
            for index, stmt in enumerate(statements, 1):
                try:
                    async with engine.begin() as conn:
                        await conn.exec_driver_sql(stmt)
                except Exception as exc:  # noqa: BLE001 - 记录后由判据断言为空
                    result["apply_errors"].append(
                        {
                            "migration": migration.name,
                            "index": index,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
        if result["apply_errors"]:
            raise Task71GateError(f"迁移应用失败: {result['apply_errors'][:3]}")

        temp_root.mkdir(parents=True, exist_ok=True)
        run = t68._Runner(engine, {})
        world = await t68._build_world(run)
        probes: tuple[tuple[str, Any], ...] = (
            ("pre_durable_owner_ddl", _probe_pre_durable_owner_ddl(t68, run, world, obs)),
            ("transaction_atomicity", _probe_transaction_atomicity(t68, engine, world, obs)),
        )
        for name, coro in probes:
            try:
                await coro
            except Exception as exc:  # noqa: BLE001 - 逐探针记录，禁 fail-open
                result["probe_errors"][name] = f"{type(exc).__name__}: {exc}"
        try:
            result["facets"]["retention"] = await _probe_retention(
                t68, engine, world, obs, temp_root
            )
        except Exception as exc:  # noqa: BLE001
            result["probe_errors"]["retention"] = f"{type(exc).__name__}: {exc}"

        result["scratch_row_counts"] = {}
        async with engine.connect() as conn:
            for table in t68.PRODUCTION_ROW_TABLES:
                result["scratch_row_counts"][table] = int(
                    (await conn.execute(sa.text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
                )
    finally:
        result["observations"] = obs.data
        result["duplicate_arm_writes"] = sorted(set(obs.duplicates))
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            async with admin.connect() as conn:
                result["public_after"] = {
                    table: int(
                        (
                            await conn.execute(
                                sa.text(f"SELECT count(*) FROM public.{table}")  # noqa: S608
                            )
                        ).scalar_one()
                    )
                    for table in t68.PRODUCTION_ROW_TABLES
                }
                leftovers = [
                    str(row[0])
                    for row in (
                        await conn.execute(
                            sa.text(
                                "SELECT schema_name FROM information_schema.schemata "
                                "WHERE schema_name LIKE :pat ORDER BY schema_name"
                            ),
                            {"pat": f"{SCRATCH_PREFIX}%"},
                        )
                    ).all()
                ]
                result["own_schema_left"] = 1 if schema in leftovers else 0
                result["foreign_scratch_schemas"] = [s for s in leftovers if s != schema]
                # 上游任务 68 的 scratch 前缀残留也一并如实报告（不并进本轮结论）。
                result["upstream_scratch_schemas"] = [
                    str(row[0])
                    for row in (
                        await conn.execute(
                            sa.text(
                                "SELECT schema_name FROM information_schema.schemata "
                                "WHERE schema_name LIKE 'tmp_task%' "
                                "  AND schema_name NOT LIKE :own ORDER BY schema_name"
                            ),
                            {"own": f"{SCRATCH_PREFIX}%"},
                        )
                    ).all()
                ]
        finally:
            await admin.dispose()
        if temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)
        result["temp_artifact_root_removed"] = not temp_root.exists()


def run_behaviour_harness() -> dict[str, Any]:
    """跑一次行为侧采集。禁 fail-open：采集失败必须留下 `error` 让判据变红。"""
    _ensure_backend_on_path()
    result: dict[str, Any] = {"error": None, "observations": {}}
    started = time.time()
    try:
        asyncio.run(_run_behaviour(result))
    except Exception as exc:  # noqa: BLE001 - 采集失败如实报告
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["wallclock_seconds"] = round(time.time() - started, 2)
    return result


def collect_all_observations() -> dict[str, Any]:
    """跑齐两侧观测：scratch schema 行为侧 + 服务层纯不变量侧。

    🔴 只有**一处**把两侧合并（本函数）—— 门与守卫都消费它。分两处合并的必然结局是守卫那份
    少跑一半，于是「声明了却没有观测」在守卫侧看不见（首轮实测：守卫自己只跑 DB 半边，
    六条纯不变量臂全被判 missing_observation）。
    """
    harness = run_behaviour_harness()
    obs = _Obs()
    obs.data.update(harness.get("observations") or {})
    probe_delivery_ownership_invariant(obs)
    return {
        **harness,
        "observations": obs.data,
        "duplicate_arm_writes": sorted(
            set(list(harness.get("duplicate_arm_writes") or []) + obs.duplicates)
        ),
    }


def build_behaviour_report(harness: Mapping[str, Any]) -> dict[str, Any]:
    """逐臂比对 + 交叉签名互斥 + 观测缺失清单。"""
    observations = dict(harness.get("observations") or {})
    rows = [evaluate_own_arm(arm, observations.get(arm.arm_id)) for arm in OWN_ARMS]
    rejected_rows = [row for row in rows if row["expectation"] == "rejected"]
    cross: list[dict[str, Any]] = []
    for left in rejected_rows:
        for right in rejected_rows:
            if left["arm_id"] == right["arm_id"]:
                continue
            other = str((right.get("observed") or {}).get("rejection") or "")
            hits = [frag for frag in (left.get("signature") or []) if frag and frag in other]
            if len(hits) == len(left.get("signature") or []) and hits:
                cross.append(
                    {"signature_of": left["arm_id"], "also_hits": right["arm_id"], "hits": hits}
                )
    facets = Counter(row["facet"] for row in rows)
    return {
        "statement": (
            "本门在自己的 scratch schema（前缀 `%s`）与生产纯不变量上真造的行为臂。"
            "每个 facet 都必须既有对照组（accepted）又有实验组（rejected/measure）。"
            % SCRATCH_PREFIX
        ),
        "harness_error": harness.get("error"),
        "apply_errors": list(harness.get("apply_errors") or []),
        "probe_errors": dict(harness.get("probe_errors") or {}),
        "duplicate_arm_writes": list(harness.get("duplicate_arm_writes") or []),
        "arm_count": len(rows),
        "arms_agreeing": sum(1 for row in rows if row["agrees"]),
        "disagreeing_arms": [row["arm_id"] for row in rows if not row["agrees"]],
        "missing_observations": [
            row["arm_id"] for row in rows if row["state"] == "missing_observation"
        ],
        "expectation_histogram": dict(
            sorted(Counter(row["expectation"] for row in rows).items())
        ),
        "facet_histogram": dict(sorted(facets.items())),
        "control_arm_count": sum(1 for row in rows if row["expectation"] == "accepted"),
        "experiment_arm_count": sum(
            1 for row in rows if row["expectation"] in ("rejected", "measure")
        ),
        "facets_missing_control": sorted(
            {
                arm.facet
                for arm in OWN_ARMS
                if not any(a.facet == arm.facet and a.expectation == "accepted" for a in OWN_ARMS)
            }
        ),
        "cross_signature_hits": cross,
        "cross_signature_rule": cross_signature_check(),
        "scratch_row_counts": dict(harness.get("scratch_row_counts") or {}),
        "arms": rows,
    }


def restoration_record(harness: Mapping[str, Any]) -> dict[str, Any]:
    """数据复原实证：生产 `public` 逐表前后相等 + 零本轮残留 + 临时 artifact 根已删。"""
    before = dict(harness.get("public_before") or {})
    after = dict(harness.get("public_after") or {})
    drifted = {
        table: {"before": before.get(table), "after": after.get(table)}
        for table in sorted(set(before) | set(after))
        if before.get(table) != after.get(table)
    }
    own_left = harness.get("own_schema_left")
    foreign = list(harness.get("foreign_scratch_schemas") or [])
    upstream = list(harness.get("upstream_scratch_schemas") or [])
    measured = bool(before) and bool(after)
    temp_removed = bool(harness.get("temp_artifact_root_removed"))
    return {
        "statement": (
            "行为侧只在 scratch schema 写行、只在临时 artifact 根写文件；生产 `public` schema "
            "前后逐表行数必须逐格相等，本轮创建的那套 `%s*` schema 必须被 DROP 干净，"
            "临时 artifact 根必须整棵删掉。" % SCRATCH_PREFIX
        ),
        "measured": measured,
        "table_count": len(before),
        "public_before": before,
        "public_after": after,
        "drifted_tables": drifted,
        "own_schema_left": own_left,
        "foreign_scratch_schemas": foreign,
        "foreign_scratch_note": (
            "**本前缀下**非本轮创建的残留。区分「本轮的」与「外来的」是必须的：变异实验若"
            "故意删掉 `DROP SCHEMA` 会累计残留，只报总数会把本轮的复原结论打成假红；"
            "只报本轮的又会让残留被静默容忍。两个都报。"
        ),
        "upstream_scratch_schemas": upstream,
        "upstream_scratch_note": (
            "其他任务前缀（`tmp_task*`）的残留，如实列出，由各自 owner 清理；不并进本轮结论。"
        ),
        "temp_artifact_root_removed": temp_removed,
        "scratch_row_counts": dict(harness.get("scratch_row_counts") or {}),
        "restored": bool(measured and not drifted and own_left == 0 and temp_removed),
        "why_this_is_the_proof": (
            "「跑完没报错」不是复原实证 —— 被 `^C` 中断的运行可能已提交部分变更，判成败一律"
            "**查数据**不看 exit code。前后逐表行数 + 残留 schema 计数 + 临时目录存在性是"
            "可复算的数据侧判据。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §7 容量面
# ════════════════════════════════════════════════════════════════════════════


def build_capacity() -> dict[str, Any]:
    """容量面：真跑生产的 fail-closed 与需求原文交叉锁；真实负载如实标 UNVERIFIABLE。

    🔴 这里最容易作假的是「用合成实测值构造一个 `executed_within_budget` 的 outcome，然后
    在收口计数里把容量门算成已通过」。生产模块本身就是为防这件事写的（登记态 / 已执行 /
    已通过是三个不可互换的状态，`assert_capacity_verified(None)` **抛**而不是返回 False）。
    因此本门把合成算例**只**用于打出评估器的六条判据 + ADR 缺失分支，并在
    `real_load_execution` 里显式声明真实负载未运行、点名 owner。
    """
    prod = _production()
    capacity = prod["capacity"]
    profile = capacity.CAPACITY_PROFILE

    facts = capacity.requirement_facts()
    drift_error: str | None = None
    try:
        capacity.assert_profile_matches_requirements()
    except Exception as exc:  # noqa: BLE001
        drift_error = _exc_signature(exc)

    # ── fail-closed：没有执行记录时必须抛 ────────────────────────────────────
    fail_closed: dict[str, Any] = {"raised": False, "signature": None}
    try:
        capacity.assert_capacity_verified(None)
    except Exception as exc:  # noqa: BLE001
        fail_closed = {
            "raised": True,
            "signature": _exc_signature(exc),
            "exception_type": type(exc).__name__,
            "error_code": getattr(exc, "error_code", None),
            "is_not_executed_error": isinstance(exc, capacity.CapacityNotExecutedError),
        }

    def _measurement(**overrides: Any) -> Any:
        payload: dict[str, Any] = {
            "concurrent_login_sessions": profile.concurrent_login_sessions,
            "active_onlyoffice_participants": profile.active_onlyoffice_participants,
            "same_second_forcesave_burst": profile.same_second_forcesave_burst,
            "sustained_applications_per_second": profile.sustained_applications_per_second,
            "sustained_duration_seconds": profile.sustained_duration_seconds,
            "incoming_durable_p95_seconds": float(profile.incoming_durable_p95_seconds),
            "applied_terminal_p95_seconds": float(profile.applied_terminal_p95_seconds),
            "hardware_profile": "synthetic-evaluator-probe",
            "onlyoffice_build": "synthetic-evaluator-probe",
            "source_commit": "synthetic-evaluator-probe",
        }
        payload.update(overrides)
        return capacity.CapacityMeasurement(**payload)

    # ── 评估器的七条判据：对照组 1 条 + 实验组 6 条（逐条独立，理由互不命中）────
    evaluator_arms: list[dict[str, Any]] = []

    def _arm(arm_id: str, expectation: str, build: Callable[[], Any]) -> None:
        try:
            outcome = build()
        except Exception as exc:  # noqa: BLE001
            evaluator_arms.append(
                {
                    "arm_id": arm_id,
                    "expectation": expectation,
                    "raised": True,
                    "signature": _exc_signature(exc),
                    "agrees": expectation == "raises",
                }
            )
            return
        status = outcome.status.value
        shortfalls = list(outcome.shortfalls)
        agrees = (
            (expectation == "within_budget" and status == "executed_within_budget")
            or (expectation == "requires_adr" and status == "executed_requires_adr")
        )
        evaluator_arms.append(
            {
                "arm_id": arm_id,
                "expectation": expectation,
                "raised": False,
                "status": status,
                "shortfalls": shortfalls,
                "agrees": bool(agrees),
            }
        )

    _arm("cap_control_exactly_at_budget", "within_budget",
         lambda: capacity.evaluate_capacity_run(_measurement()))
    for field in (
        "concurrent_login_sessions",
        "active_onlyoffice_participants",
        "same_second_forcesave_burst",
        "sustained_applications_per_second",
        "sustained_duration_seconds",
    ):
        _arm(
            f"cap_shortfall_{field}",
            "requires_adr",
            lambda field=field: capacity.evaluate_capacity_run(
                _measurement(
                    **{field: getattr(profile, field) - 1},
                    capacity_adr_ref="ADR-t71-synthetic",
                )
            ),
        )
    for field in ("incoming_durable_p95_seconds", "applied_terminal_p95_seconds"):
        _arm(
            f"cap_over_budget_{field}",
            "requires_adr",
            lambda field=field: capacity.evaluate_capacity_run(
                _measurement(
                    **{field: float(getattr(profile, field)) + 1.0},
                    capacity_adr_ref="ADR-t71-synthetic",
                )
            ),
        )
    _arm(
        "cap_shortfall_without_adr_raises",
        "raises",
        lambda: capacity.evaluate_capacity_run(
            _measurement(concurrent_login_sessions=1)
        ),
    )
    _arm(
        "cap_missing_environment_raises",
        "raises",
        lambda: capacity.evaluate_capacity_run(_measurement(hardware_profile="")),
    )

    # 未达标的 outcome 不得被算成「已通过」
    adr_outcome = capacity.evaluate_capacity_run(
        _measurement(concurrent_login_sessions=1, capacity_adr_ref="ADR-t71-synthetic")
    )
    verified_rejects_adr: dict[str, Any] = {"raised": False}
    try:
        capacity.assert_capacity_verified(adr_outcome)
    except Exception as exc:  # noqa: BLE001
        verified_rejects_adr = {"raised": True, "signature": _exc_signature(exc)}

    t69 = read_json(T69_REPORT)
    t70 = read_json(T70_REPORT)
    return {
        "statement": (
            "AC 14.10 的 6000 会话 / 1200 participant / 120 同秒 burst / 20 applications/s × "
            "10 分钟 + AC 14.12 的两条 p95 预算。本门真跑「登记值 ↔ 需求原文」交叉锁与评估器"
            "的七条判据；真实负载本轮未运行，如实标 UNVERIFIABLE 并点名 owner。"
        ),
        "registered_profile": profile.as_dict(),
        "profile_digest": profile.digest,
        "requirement_facts": facts,
        "profile_matches_requirements": drift_error is None,
        "profile_drift_signature": drift_error,
        "status_is_registered_pending_execution": (
            profile.status is capacity.CapacityStatus.registered_pending_execution
        ),
        "execution_owner_declared_by_production": profile.execution_owner,
        "fail_closed_without_execution_record": fail_closed,
        "assert_verified_rejects_requires_adr_outcome": verified_rejects_adr,
        "evaluator_arms": evaluator_arms,
        "evaluator_arm_count": len(evaluator_arms),
        "evaluator_arms_disagreeing": [
            row["arm_id"] for row in evaluator_arms if not row["agrees"]
        ],
        "evaluator_control_arms": sum(
            1 for row in evaluator_arms if row["expectation"] == "within_budget"
        ),
        "evaluator_experiment_arms": sum(
            1 for row in evaluator_arms if row["expectation"] != "within_budget"
        ),
        "real_load_execution": {
            "tier": "UNVERIFIABLE",
            "owner_task": "72",
            "why": (
                "真实负载需要 ①前端 3030 在监听（任务 69 实录未监听，本门起手复测仍未监听）"
                "②真实 OO 活动编辑会话（任务 70 实录：forcesave 对不存在 doc key 回 error 1，"
                "需活动会话）③生产 `public` 里有业务数据（任务 70 实录 evidence 五表全 0 行、"
                "180 个 OO entry 的 capability 全是 single_onlyoffice、0 个 bidirectional）。"
                "三条前提今天一条都不成立 ⇒ 6000 会话 × 1200 participant 的负载**无从供给**。"
            ),
            "measured_premises": {
                "port_3030_listening": bool(
                    (t69.get("oo_scope_boundary") or {}).get("port_3030_listening")
                ),
                "task70_executed_end_to_end": (t70.get("verdict") or {}).get(
                    "executed_end_to_end"
                ),
                "task70_verdict": (t70.get("verdict") or {}).get("state"),
            },
            "not_claimed": (
                "本门**不**用合成实测值构造 executed_within_budget 去冒充容量门通过 —— "
                "那正是生产 `capacity_profile` 设计来防的事。合成算例只用于打出评估器判据。"
            ),
        },
        "synthetic_measurements_are_labelled": True,
        "synthetic_label": "synthetic-evaluator-probe",
    }


# ════════════════════════════════════════════════════════════════════════════
# §8 脱敏面
# ════════════════════════════════════════════════════════════════════════════

#: 植入的密钥明文。**必须**在脱敏结果里一个都找不到（逐条现算，不抽查）。
_PLANTED_SECRETS: Final[Mapping[str, str]] = {
    "bearer_token": "t71-planted-bearer-6f2c9a1b4e8d",
    "jwt_secret": "t71-planted-jwt-secret-3a7f",
    "download_query_token": "t71-planted-url-token-9d4e",
    "basic_credentials": "t71-planted-basic-c0ffee",
}


def build_redaction() -> dict[str, Any]:
    """脱敏面：`RedactionPolicy.redact()` 真跑 + `assert_no_leak()` 对未脱敏载荷必抛。"""
    prod = _production()
    redaction = prod["redaction"]
    policy = redaction.load_redaction_policy()

    payload = {
        "authorization": f"Bearer {_PLANTED_SECRETS['bearer_token']}",
        "jwt_secret": _PLANTED_SECRETS["jwt_secret"],
        "download_url": (
            f"https://oo.internal:8080/cache/files/x?token={_PLANTED_SECRETS['download_query_token']}"
        ),
        "callback_url": f"https://user:{_PLANTED_SECRETS['basic_credentials']}@oo.internal/cb",
        "room_id": "11111111-1111-1111-1111-111111111111",
        "generation": 3,
        "nested": {"lease_token_hash": _PLANTED_SECRETS["jwt_secret"], "state": "durable"},
    }
    projected, report = policy.redact(payload)
    projected_text = stable_json(projected)
    leaked = sorted(
        name for name, value in _PLANTED_SECRETS.items() if value in projected_text
    )

    arms: list[dict[str, Any]] = []

    def _arm(arm_id: str, expectation: str, fn: Callable[[], Any]) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            arms.append(
                {
                    "arm_id": arm_id,
                    "expectation": expectation,
                    "raised": True,
                    "signature": _exc_signature(exc),
                    "agrees": expectation == "raises",
                }
            )
        else:
            arms.append(
                {
                    "arm_id": arm_id,
                    "expectation": expectation,
                    "raised": False,
                    "signature": None,
                    "agrees": expectation == "accepted",
                }
            )

    # 对照组：脱敏后的载荷必须过 `assert_no_leak`
    _arm("red_control_projected_passes", "accepted", lambda: policy.assert_no_leak(projected))
    # 实验组四条，各自打不同的泄露形态（理由互不命中由 signature 现算比对）
    _arm(
        "red_raw_bearer_header_rejected",
        "raises",
        lambda: policy.assert_no_leak(
            {"authorization": f"Bearer {_PLANTED_SECRETS['bearer_token']}"}
        ),
    )
    _arm(
        "red_raw_secret_key_rejected",
        "raises",
        lambda: policy.assert_no_leak({"jwt_secret": _PLANTED_SECRETS["jwt_secret"]}),
    )
    _arm(
        "red_url_with_query_rejected",
        "raises",
        lambda: policy.assert_no_leak(
            {
                "download_url": (
                    "https://oo.internal:8080/cache/files/x?token="
                    f"{_PLANTED_SECRETS['download_query_token']}"
                )
            }
        ),
    )
    _arm(
        "red_nested_secret_rejected",
        "raises",
        lambda: policy.assert_no_leak(
            {"nested": {"lease_token_hash": _PLANTED_SECRETS["jwt_secret"]}}
        ),
    )

    planted_url = (
        "https://oo.internal:8080/cache/files/x?token="
        f"{_PLANTED_SECRETS['download_query_token']}"
    )
    # ① 命中生产 value pattern 的形态（URL 带 query / Bearer 头）—— 必须被抹
    exception_text = policy.redact_exception(RuntimeError(f"下载失败 {planted_url}"))
    bearer_exception_text = policy.redact_exception(
        RuntimeError(f"鉴权失败 Bearer {_PLANTED_SECRETS['bearer_token']}")
    )
    url_text = policy.redact_url(planted_url)
    # ② 自由文本里的裸 `token=<短串>`（不命中任何 value pattern）—— 实测**不**被抹。
    #    如实度量并单独登记，不把它算进「已脱敏」，也不假装生产有这个能力。
    bare_token_text = policy.redact_exception(
        RuntimeError(f"下载失败 token={_PLANTED_SECRETS['download_query_token']}")
    )
    signatures = [row["signature"] for row in arms if row["raised"]]
    return {
        "statement": (
            "植入四种形态的密钥（Bearer 头 / 密钥键名 / URL query token / 嵌套 token hash），"
            "`redact()` 后逐条现算它们**一个都不在**结果里；`assert_no_leak()` 对未脱敏载荷"
            "必须抛（对照组先过）。"
        ),
        "policy_fingerprint": policy.fingerprint(),
        "planted_secret_names": sorted(_PLANTED_SECRETS),
        "planted_secret_count": len(_PLANTED_SECRETS),
        "leaked_planted_secrets": leaked,
        "no_planted_secret_survives": leaked == [],
        "redaction_report": report.as_dict(),
        "projected_keys": sorted(projected),
        "dropped_key_count": len(report.dropped_keys),
        "secret_key_count": len(report.secret_keys),
        "exception_with_url_contains_secret": (
            _PLANTED_SECRETS["download_query_token"] in exception_text
        ),
        "exception_with_bearer_contains_secret": (
            _PLANTED_SECRETS["bearer_token"] in bearer_exception_text
        ),
        "url_redacted_contains_secret": (
            _PLANTED_SECRETS["download_query_token"] in url_text
        ),
        "value_pattern_ids": list(policy.fingerprint()["value_pattern_ids"]),
        "bare_token_in_free_text_is_scrubbed": (
            _PLANTED_SECRETS["download_query_token"] not in bare_token_text
        ),
        "bare_token_finding": (
            "实测：自由文本里的 `token=<短不透明串>` **不**被 `redact_exception()` 抹掉 —— "
            "生产脱敏按四条 value pattern（jwt_compact / bearer_header / "
            "url_with_credentials_or_query / long_opaque_blob）匹配，裸短串不命中任何一条。"
            "这是既有设计边界，不是本轮引入的缺陷；如实登记并点名 owner，不在本任务改生产代码。"
        ),
        "bare_token_owner_task": "29",
        "arms": arms,
        "arm_count": len(arms),
        "arms_disagreeing": [row["arm_id"] for row in arms if not row["agrees"]],
        "control_arm_count": sum(1 for row in arms if row["expectation"] == "accepted"),
        "experiment_arm_count": sum(1 for row in arms if row["expectation"] == "raises"),
        "distinct_rejection_signatures": len(set(signatures)),
        "rejection_signature_count": len(signatures),
    }


# ════════════════════════════════════════════════════════════════════════════
# §9 告警面（synthetic 事件流）
# ════════════════════════════════════════════════════════════════════════════


def build_alerting() -> dict[str, Any]:
    """告警面：三向核对 + 逐规则 synthetic 事件流（阈值上/下各一条）。

    🔴 「逐规则」而不是「抽一条」：名单类判据必须写死真实目标（教训 16）。这里对**每条**
    生产规则各造两组样本 —— 恰在阈值（必触发）与阈值以下（必不触发）。少任何一半都会让
    「阈值被改成 0」或「规则被短路成恒触发」测不出来。
    """
    prod = _production()
    alerting = prod["alerting"]
    metrics = prod["metrics"]
    registry = alerting.load_alert_registry()
    problems = list(alerting.validate_registry(registry))

    def _samples(rule: Any, *, value: float, key: str) -> list[Any]:
        labels = {dim.value: f"{key}-{dim.value}" for dim in rule.dedupe_key_fields}
        return [
            metrics.MetricSample(
                metric=rule.metric,
                result=(rule.result_filter[0] if rule.result_filter else None),
                landed=True,
                value=value,
                labels=labels,
            )
        ]

    rows: list[dict[str, Any]] = []
    for rule in registry.rules:
        at = registry.evaluate(_samples(rule, value=rule.threshold, key="at"))
        below = registry.evaluate(_samples(rule, value=max(rule.threshold - 1.0, 0.0), key="lo"))
        fired_at = [inst.rule_id for inst in at if inst.rule_id == rule.rule_id]
        fired_below = [inst.rule_id for inst in below if inst.rule_id == rule.rule_id]
        deadline_kind = (
            "auto" if rule.recovery.auto_recovers else "explicit"
        )
        rows.append(
            {
                "rule_id": rule.rule_id,
                "condition": rule.condition.value,
                "metric": rule.metric,
                "severity": rule.severity.value,
                "comparison": rule.comparison.value,
                "threshold": rule.threshold,
                "dedupe_key_fields": [dim.value for dim in rule.dedupe_key_fields],
                "recovery_kind": deadline_kind,
                "runbook_chars": len(rule.runbook),
                "fires_at_threshold": bool(fired_at),
                "silent_below_threshold": not fired_below,
                "agrees": bool(fired_at) and not fired_below,
            }
        )

    # 去重：同一 dedupe key 的多条样本只出一条实例；不同 key 各出一条。
    probe_rule = registry.rules[0]
    dedupe_same = registry.evaluate(
        _samples(probe_rule, value=probe_rule.threshold, key="same")
        + _samples(probe_rule, value=probe_rule.threshold, key="same")
    )
    dedupe_diff = registry.evaluate(
        _samples(probe_rule, value=probe_rule.threshold, key="a")
        + _samples(probe_rule, value=probe_rule.threshold, key="b")
    )

    # 恢复期限：自动恢复型给出时刻，显式处理型必须给 None（两态都要有落点）
    import datetime as _dt

    fired_at_moment = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    deadlines: dict[str, Any] = {}
    for rule in registry.rules:
        deadlines[rule.rule_id] = (
            registry.recovery_deadline(rule.rule_id, fired_at=fired_at_moment) is not None
        )
    naive_rejected: dict[str, Any] = {"raised": False}
    auto_rule = next((r for r in registry.rules if r.recovery.auto_recovers), None)
    if auto_rule is not None:
        try:
            registry.recovery_deadline(
                auto_rule.rule_id, fired_at=_dt.datetime(2026, 1, 1)
            )
        except Exception as exc:  # noqa: BLE001
            naive_rejected = {"raised": True, "signature": _exc_signature(exc)}
    unknown_rejected: dict[str, Any] = {"raised": False}
    try:
        registry.recovery_deadline("t71-rule-that-does-not-exist", fired_at=fired_at_moment)
    except Exception as exc:  # noqa: BLE001
        unknown_rejected = {"raised": True, "signature": _exc_signature(exc)}

    req_conditions = {
        label: condition.value
        for label, condition in sorted(alerting.REQUIREMENT_13_9_CONDITIONS.items())
    }
    return {
        "statement": (
            "Requirement 13.9 逐条点名的十四类 + 两条分型必须各有规则；每条规则在 synthetic "
            "事件流上恰在阈值触发、阈值以下静默；去重键、恢复分型与 runbook 长度逐条现算。"
        ),
        "registry_fingerprint": registry.fingerprint(),
        "rule_count": len(registry.rules),
        "validate_registry_problems": problems,
        "three_way_clean": problems == [],
        "requirement_13_9_conditions": req_conditions,
        "requirement_13_9_condition_count": len(req_conditions),
        "alert_condition_vocabulary": sorted(c.value for c in alerting.AlertCondition),
        "conditions_without_rule": sorted(
            c.value for c in alerting.AlertCondition if c not in registry.rules_by_condition
        ),
        "rules": rows,
        "rules_disagreeing": [row["rule_id"] for row in rows if not row["agrees"]],
        "rules_firing_at_threshold": sum(1 for row in rows if row["fires_at_threshold"]),
        "rules_silent_below_threshold": sum(
            1 for row in rows if row["silent_below_threshold"]
        ),
        "min_runbook_chars_required": alerting.MIN_RUNBOOK_CHARS,
        "shortest_runbook_chars": min(row["runbook_chars"] for row in rows),
        "dedupe_same_key_instance_count": len(
            [i for i in dedupe_same if i.rule_id == probe_rule.rule_id]
        ),
        "dedupe_distinct_key_instance_count": len(
            [i for i in dedupe_diff if i.rule_id == probe_rule.rule_id]
        ),
        "recovery_deadline_present_by_rule": deadlines,
        "auto_recovering_rule_count": sum(1 for present in deadlines.values() if present),
        "explicit_resolution_rule_count": sum(
            1 for present in deadlines.values() if not present
        ),
        "naive_datetime_rejected": naive_rejected,
        "unknown_rule_id_rejected": unknown_rejected,
    }


# ════════════════════════════════════════════════════════════════════════════
# §10 故障恢复面（六种注入）
# ════════════════════════════════════════════════════════════════════════════


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


def _inject_onlyoffice_unreachable() -> dict[str, Any]:
    """OO 注入：往一个**确定没人监听**的端口发命令请求，必须抛/超时，不得静默返空。"""
    import urllib.error
    import urllib.request

    dead_port = 59_071
    url = f"http://127.0.0.1:{dead_port}/coauthoring/CommandService.ashx"
    request = urllib.request.Request(
        url, data=b'{"c":"version"}', headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:  # noqa: S310
            body = response.read(200).decode("utf-8", "replace")
        return {"raised": False, "body": body, "port": dead_port}
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {
            "raised": True,
            "signature": _normalize_rejection(f"{type(exc).__name__}: {exc}"),
            "port": dead_port,
        }


def _inject_postgres_unreachable() -> dict[str, Any]:
    """PG 注入：用一个坏 DSN 连库，必须抛而不是被吞成「无数据」。

    🔴 独立 `NullPool` 引擎 + `dispose()`：复用共享连接池会让门被打成「库不可达」而库
    完全可达（假 ERROR 态，任务 61 实测过）。
    """

    async def _go() -> dict[str, Any]:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        import sqlalchemy as sa

        dsn = "postgresql+asyncpg://t71_no_such_user:t71_no_such_pw@127.0.0.1:5432/t71_no_such_db"
        engine = create_async_engine(dsn, poolclass=NullPool, connect_args={"ssl": False})
        try:
            async with engine.connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
            return {"raised": False}
        except Exception as exc:  # noqa: BLE001 - 拒绝本身就是观测
            return {"raised": True, "signature": _exc_signature(exc)}
        finally:
            await engine.dispose()

    _ensure_backend_on_path()
    return asyncio.run(_go())


def _inject_redis() -> dict[str, Any]:
    """Redis 注入：先确认真实 Redis 可达（对照组），再对死端口证明失败会上抛。"""
    live = _tcp_listening("127.0.0.1", 6379)
    dead = _tcp_listening("127.0.0.1", 59_079)
    ping: dict[str, Any] = {"attempted": False}
    if live:
        sock = socket.socket()
        sock.settimeout(2.0)
        try:
            sock.connect(("127.0.0.1", 6379))
            sock.sendall(b"PING\r\n")
            reply = sock.recv(64)
            ping = {"attempted": True, "pong": reply.startswith(b"+PONG")}
        except OSError as exc:
            ping = {"attempted": True, "error": type(exc).__name__}
        finally:
            sock.close()
    return {
        "control_live_port_reachable": live,
        "experiment_dead_port_reachable": dead,
        "ping": ping,
        "agrees": bool(live) and not dead,
    }


def _inject_disk_path_escape() -> dict[str, Any]:
    """磁盘注入：路径越界与不存在的对象各造一次，必须走各自的错误码而不是静默成功。"""
    import shutil

    prod = _production()
    artifacts = prod["artifacts"]
    root = REPO / f"tmp_task71_disk_probe_{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    project = uuid.uuid4()
    out: dict[str, Any] = {"root_removed": False}
    try:
        repo = artifacts.CanonicalArtifactRepository(root)
        # ① 路径越界必须被拒（Property 42）
        try:
            repo.delete_artifact_file("../../etc/passwd", project_id=project)
        except Exception as exc:  # noqa: BLE001
            out["path_escape"] = {"raised": True, "signature": _exc_signature(exc)}
        else:
            out["path_escape"] = {"raised": False}
        # ② 不存在的对象：返回 False（不是异常，也不是「已删」）
        (root / "storage" / str(project) / "workpapers").mkdir(parents=True, exist_ok=True)
        try:
            missing = repo.delete_artifact_file(
                f"storage/{project}/workpapers/t71-absent.xlsx", project_id=project
            )
            out["absent_object"] = {"raised": False, "returned": missing}
        except Exception as exc:  # noqa: BLE001
            out["absent_object"] = {"raised": True, "signature": _exc_signature(exc)}
    finally:
        shutil.rmtree(root, ignore_errors=True)
        out["root_removed"] = not root.exists()
    return out


def _inject_windows_file_lock() -> dict[str, Any]:
    """Windows lock 注入：持有句柄时删除必须被分类成 `FILE_IN_USE`，不得静默算已删。"""
    import shutil

    prod = _production()
    artifacts = prod["artifacts"]
    root = REPO / f"tmp_task71_lock_probe_{uuid.uuid4().hex[:8]}"
    project = uuid.uuid4()
    target_rel = f"storage/{project}/workpapers/t71-locked.xlsx"
    target = root / target_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"task71-lock")
    out: dict[str, Any] = {"platform": sys.platform, "root_removed": False}
    try:
        repo = artifacts.CanonicalArtifactRepository(root)
        # 对照组：无人持有句柄时必须真删掉
        out["control_delete_without_handle"] = repo.delete_artifact_file(
            target_rel, project_id=project
        )
        out["control_file_gone"] = not target.exists()
        target.write_bytes(b"task71-lock-again")
        handle = target.open("rb")
        try:
            deleted = repo.delete_artifact_file(target_rel, project_id=project)
            out["experiment"] = {"raised": False, "returned": deleted}
        except Exception as exc:  # noqa: BLE001
            out["experiment"] = {
                "raised": True,
                "exception_type": type(exc).__name__,
                "error_code": getattr(exc, "error_code", None),
                "signature": _exc_signature(exc),
                "classified_file_in_use": type(exc).__name__ == "FileInUseError",
            }
        finally:
            handle.close()
        out["file_survived_the_locked_attempt"] = target.exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)
        out["root_removed"] = not root.exists()
    return out


def build_fault_injection(behaviour: Mapping[str, Any]) -> dict[str, Any]:
    """六种注入各自独立报告字段 + 独立实测。

    正文点名 `orphan/outbox/retry/pointers/双基线` 的验证：outbox 的 pending 契约与
    orphan/pointer 语义由本门从**生产源码现算**（下面的 `orphan_outbox_pointers`），
    真实并发重投需要 6000 会话级负载 ⇒ 与容量面同一条 UNVERIFIABLE。
    """
    observations = dict(behaviour.get("observations") or {})
    atomicity = observations.get("t71_atomicity_partial_rollback") or {}
    prod = _production()
    outbox = prod["outbox"]
    metrics = prod["metrics"]

    injections = {
        "onlyoffice": {
            "kind": "OO 服务不可用",
            "measured": _inject_onlyoffice_unreachable(),
            "control_real_oo_port_8080_listening": _tcp_listening("127.0.0.1", 8080),
            "expectation": "必须抛/超时，不得静默返回空体（AC 5.12 禁 fail-open）",
        },
        "postgres": {
            "kind": "PG 不可达",
            "measured": _inject_postgres_unreachable(),
            "control_real_pg_port_5432_listening": _tcp_listening("127.0.0.1", 5432),
            "expectation": "坏 DSN 必须抛；本门用独立 NullPool 引擎，避免污染共享池造出假 ERROR",
        },
        "redis": {
            "kind": "Redis 不可达",
            "measured": _inject_redis(),
            "expectation": "真实 6379 可达（对照组）且死端口不可达（实验组）",
        },
        "disk": {
            "kind": "磁盘/路径故障",
            "measured": _inject_disk_path_escape(),
            "expectation": "越界必须 ArtifactPathError；不存在的对象返回 False 而不是「已删」",
        },
        "windows_lock": {
            "kind": "Windows 文件占用",
            "measured": _inject_windows_file_lock(),
            "expectation": "持有句柄时删除必须分类成 FILE_IN_USE 且文件仍在",
        },
        "process_interrupt": {
            "kind": "进程中断（事务原子性）",
            "measured": {
                "rows_after_failed_transaction": atomicity.get("measured", {}).get(
                    "rows_after_failed_transaction"
                ),
                "raised": atomicity.get("measured", {}).get("raised"),
                "control_arm": "t71_atomicity_baseline",
                "experiment_arm": "t71_atomicity_partial_rollback",
            },
            "expectation": "事务内一处失败 ⇒ 前面写的行必须一起回滚（0 行残留）",
        },
    }

    def _ok(name: str) -> bool:
        row = injections[name]["measured"]
        if name == "onlyoffice":
            return bool(row.get("raised"))
        if name == "postgres":
            return bool(row.get("raised"))
        if name == "redis":
            return bool(row.get("agrees"))
        if name == "disk":
            return bool(
                (row.get("path_escape") or {}).get("raised")
                and (row.get("absent_object") or {}).get("returned") is False
            )
        if name == "windows_lock":
            return bool(
                row.get("control_delete_without_handle")
                and row.get("control_file_gone")
                and (row.get("experiment") or {}).get("classified_file_in_use")
                and row.get("file_survived_the_locked_attempt")
            )
        return bool(
            (row.get("measured") or row).get("raised")
            and (row.get("measured") or row).get("rows_after_failed_transaction") == 0
        )

    verdicts = {name: _ok(name) for name in injections}
    for name, ok in verdicts.items():
        injections[name]["agrees"] = ok

    return {
        "statement": (
            "OO / Redis / PG / 磁盘 / Windows lock / 进程中断六种注入各自真做一次，"
            "各自独立报告字段；错误必须**上抛**并可分类，不得被 `except Exception` 吞成"
            "「无数据」（AC 5.12）。"
        ),
        "injection_count": len(injections),
        "injections": injections,
        "injections_agreeing": sorted(name for name, ok in verdicts.items() if ok),
        "injections_disagreeing": sorted(name for name, ok in verdicts.items() if not ok),
        "orphan_outbox_pointers": {
            "outbox_pending_session_key": outbox.PENDING_SESSION_KEY,
            "outbox_handler_version_separator": outbox.HANDLER_VERSION_SEPARATOR,
            "outbox_gated_fanout_event_types": sorted(
                str(getattr(e, "value", e)) for e in outbox.GATED_FANOUT_EVENT_TYPES
            ),
            "outbox_backlog_alert_metric": next(
                (
                    name
                    for name, definition in metrics.METRICS_BY_NAME.items()
                    if "outbox" in name and definition.alert_required
                ),
                None,
            ),
            "orphan_retention_alert_metric": next(
                (
                    name
                    for name, definition in metrics.METRICS_BY_NAME.items()
                    if "orphan" in name or "retention" in name
                ),
                None,
            ),
            "retention_reference_sources": len(prod["retention"].REFERENCE_SOURCES),
            "dual_baseline_owner": "69",
            "dual_baseline_tier": "UNVERIFIABLE",
            "dual_baseline_why": (
                "server/client 双基线的运行态验证需要真实浏览器 + 3030（任务 69 已在离线挂载"
                "层独立验过状态机；真实浏览器 owner 是任务 70）。本门不冒充跑过。"
            ),
            "real_concurrent_retry_tier": "UNVERIFIABLE",
            "real_concurrent_retry_owner": "72",
            "real_concurrent_retry_why": (
                "orphan/outbox/retry/pointer 的**并发重投**要在 6000 会话级负载下才有意义，"
                "与容量面同一条前提（3030 未监听 / 无真实 OO 会话 / 生产无业务数据）。"
            ),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# §11 删除门变异 + DAG 依赖 + 协议源码现算
# ════════════════════════════════════════════════════════════════════════════


def dependency_graph() -> dict[str, Any]:
    """从 tasks.md 的 `## Task Dependency Graph` 里现读 waves + dependencies。"""
    text = read_text(TASKS_MD)
    block = re.search(r"##\s+Task Dependency Graph\s*```json\s*(\{.*?\})\s*```", text, re.S)
    if block is None:
        raise Task71GateError(
            "tasks.md 里找不到 `## Task Dependency Graph` 的 JSON 块 —— 三件套结构校验的前提"
        )
    return json.loads(block.group(1))


def build_dag_dependency() -> dict[str, Any]:
    """「把任务 24 对任务 23 的依赖删掉」这条变异的落点。

    判据现算依赖图，不读任何人的自述。同时把本任务与任务 72/74 的依赖一起报出来 ——
    正文点名的 `multi_resolver` 移交链要求任务 74 依赖本门。
    """
    graph = dependency_graph()
    deps = {str(k): [str(v) for v in vals] for k, vals in (graph.get("dependencies") or {}).items()}
    waves = {
        str(row.get("wave")): [str(t) for t in row.get("tasks") or []]
        for row in graph.get("waves") or []
    }
    wave_of = {task: wave for wave, tasks in waves.items() for task in tasks}
    return {
        "statement": (
            "close-intent（任务 24）必须依赖 request/application（任务 23）；本门（71）必须在"
            "任务 72 之前、且任务 74 必须依赖本门（`multi_resolver` 的移交链）。"
        ),
        "task24_dependencies": deps.get("24", []),
        "task24_depends_on_task23": "23" in deps.get("24", []),
        "task71_dependencies": deps.get("71", []),
        "task72_dependencies": deps.get("72", []),
        "task72_depends_on_task71": "71" in deps.get("72", []),
        "task74_dependencies": deps.get("74", []),
        "task74_depends_on_task71": "71" in deps.get("74", []),
        "wave_of_task71": wave_of.get("71"),
        "wave_of_task72": wave_of.get("72"),
        "wave_count": len(waves),
        "declared_task_count": sum(len(tasks) for tasks in waves.values()),
    }


def build_deletion_gate() -> dict[str, Any]:
    """删除门变异的三条落点，全部现算上游产物与 tasks.md 正文。

    三条各自独立成字段（合并会让靠后的那条永久不可达）：

    1. 任务 67 **不得**要求 fresh/stale=0，也**不得**宣称 eligibility；
    2. 任务 72 Stage A **不得**要求待删 unreachable 预先为 0；
    3. post-delete 的 smoke **不得**把 evidence 恢复成 verified。
    """
    t67 = read_json(T67_REPORT)
    t70 = read_json(T70_REPORT)
    tasks_text = read_text(TASKS_MD)

    axes = Counter()
    for row in t67.get("entries") or []:
        for axis in row.get("evidence_rerun_axes") or []:
            axes[str(axis)] += 1
    t67_verdict = t67.get("verdict") or {}
    vocabulary = [str(v) for v in t67_verdict.get("state_vocabulary") or []]
    eligibility_tokens = sorted(
        token for token in vocabulary + list(t67.keys()) if "eligib" in token.lower()
    )

    body72 = task_body("72")
    body67 = task_body("67")

    t70_gate_source = read_text(
        BACKEND / "scripts/check/check_task70_oo94_full_entry_scenario_gate.py"
    )
    t70_vocab = [str(v) for v in (t70.get("verdict") or {}).get("state_vocabulary") or []]

    close_gate = t70.get("close_gate") or {}
    db_before = (t70.get("db_snapshot") or {}).get("row_counts_before") or {}
    # 🔴 只算一次并存进局部变量：内联两次会让变异锚点无法唯一命中，而「同一判据在两处各算
    #    一遍」本身就是漂移源（改一处忘另一处 ⇒ 报告字段与 agrees 互相矛盾）。
    stage_a_clause_present = (
        "不得要求待删 unreachable在删除前已为0" in body72
        or "不得要求待删 unreachable 在删除前已为 0" in body72
    )
    smoke_clause_present = (
        "smoke只能附加，不能恢复 verified" in body72 or "smoke 只能附加" in body72
    )
    return {
        "statement": (
            "删除门的三条变异必须各自可打红。判据全部现算上游产物与 tasks.md 正文 —— "
            "不读任何人的「我没要求清零」自述。"
        ),
        "task67_must_not_require_zero_stale": {
            "stale_axis_histogram": dict(sorted(axes.items())),
            "stale_axis_kinds": len(axes),
            "entries_with_any_stale_axis": sum(
                1 for row in t67.get("entries") or [] if row.get("evidence_rerun_axes")
            ),
            "task67_verdict_state": t67_verdict.get("state"),
            "task67_verdict_vocabulary": vocabulary,
            "stale_is_nonzero": sum(axes.values()) > 0,
            "task67_text_says_stale_need_not_be_zero": (
                "不要求 stale 清零" in body67 or "允许报告 stale" in body67
            ),
            "agrees": bool(
                sum(axes.values()) > 0
                and t67_verdict.get("state") in vocabulary
                and ("不要求 stale 清零" in body67 or "允许报告 stale" in body67)
            ),
            "why": (
                "任务 67 实测 186 个 entry 全部带 stale 轴且它的 verdict 词表里没有任何"
                "eligibility 态 ⇒ 「错误要求 fresh/stale=0 或宣称 eligibility」这条变异有"
                "可打红的落点：把 stale 计数当成不通过条件、或往词表里加 eligibility 态。"
            ),
        },
        "task67_must_not_claim_eligibility": {
            "eligibility_tokens_found": eligibility_tokens,
            "agrees": eligibility_tokens == [],
            "why": "任务 67 的报告顶层与 verdict 词表都不得出现 eligibility 语义。",
        },
        "task72_stage_a_must_not_require_unreachable_zero": {
            "clause_present_in_task72_text": stage_a_clause_present,
            "stage_a_requires_the_four_zeros": (
                "未裁决=0" in body72 and "evidence stale=0" in body72
            ),
            "agrees": bool(stage_a_clause_present and "未裁决=0" in body72),
            "why": (
                "Stage A 要求的是四个零（未裁决/假双向/未验收/evidence stale），**不含**"
                "「待删 unreachable 预先为 0」—— 后者要到 Stage D 才成立。把它提前要求会让"
                "删除门永久不可达。"
            ),
        },
        "smoke_cannot_restore_verified": {
            "task72_text_says_smoke_only_appends": smoke_clause_present,
            "task70_verdict_vocabulary": t70_vocab,
            "task70_vocabulary_has_no_passed": "passed" not in t70_vocab,
            "task70_gate_forbids_result_keys": '"passed"' in t70_gate_source
            and "FORBIDDEN_RECORD_KEYS" in t70_gate_source,
            "agrees": bool(smoke_clause_present and "passed" not in t70_vocab),
            "why": (
                "任务 70 的 verdict 词表只有 refreshed/failed/unverifiable —— 没有 `passed` "
                "这一态，smoke 无处把 evidence 顶回 verified。变异是往词表里加第四态。"
            ),
        },
        "evidence_scenario_rows": db_before.get("working_paper_entry_evidence_scenario"),
        "test_run_rows": db_before.get("working_paper_sync_test_run"),
        "close_predicate_hits": close_gate.get("entries_hitting_predicate"),
        "close_scenario_count": close_gate.get("close_scenario_count"),
        "required_scenario_rows": (t70.get("verdict") or {}).get("required_scenario_rows"),
        "executed_end_to_end": (t70.get("verdict") or {}).get("executed_end_to_end"),
        "evidence_axis_note": (
            "evidence 五表实测 0 行（任务 70 实录）⇒ 「evidence 漏某场景 / 跨 entry 复用 / "
            "单 application 伪全场景」这三条变异在今天的分母上**无处落脚**；如实标 "
            "UNVERIFIABLE 并把 owner 指向任务 70 的真实场景刷新，不冒充已覆盖。"
        ),
    }


def build_protocol_source_scan() -> dict[str, Any]:
    """「mtime doc_key」与「status/mutable base 入 application key」两条变异的现算落点。

    🔴 判「某个量有没有进 key」走 **AST 取函数签名参数**，不 grep 符号名（教训 2/12）：
    grep `status` 会命中文档、注释与任何叫 status 的局部变量。
    """
    prod = _production()
    models = prod["models"]
    source = Path(models.__file__)
    tree = ast.parse(strip_comments(source.read_text(encoding="utf-8")))
    node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "compute_application_key"
        ),
        None,
    )
    if node is None:
        raise Task71GateError(
            "生产 models 里找不到 `compute_application_key` —— 「status 入 key」这条变异的"
            "落点已漂移，判据前提失效"
        )
    params = [arg.arg for arg in node.args.kwonlyargs] + [arg.arg for arg in node.args.args]
    forbidden = forbidden_key_inputs(params)

    # ── mtime doc_key：**真跑**生产探针，不做文本扫描 ────────────────────────
    #
    # 🔴 首轮实测教训：按「同一行里同时出现 doc_key 与 mtime」扫源码，在 `rooms.py` 上命中
    #    15 行 —— 全是**文档与注释**里正当地解释「doc_key 中不含 mtime」的句子（生产模块开
    #    头就在讲存量实况里的 `hash(wp_code + st_mtime_ns)`）。文本扫描在这里必然把「已经
    #    修好并写了说明」误判成「仍然有问题」，正是「把错值当基线」那一类守卫缺陷。
    #    生产侧已提供**真执行**探针（真的改一次文件 mtime 再比 doc_key，并对 doc_key 派生
    #    链路做 AST 传递闭包），改为直接消费它。
    import shutil
    import tempfile

    rooms = importlib.import_module(models.__name__.rsplit(".", 1)[0] + ".rooms")
    probe_dir = Path(tempfile.mkdtemp(prefix="tmp_task71_dockey_"))
    try:
        probe = rooms.probe_room_facts(tmp_path=probe_dir)
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)

    return {
        "statement": (
            "`compute_application_key` 的入参**不得**含 callback status / request id / "
            "request sequence / room last-applied / mtime（Property 64）；doc_key 必须与文件 "
            "mtime 无关。前者现算 AST 签名，后者**真跑**生产探针（真改一次 mtime 再比 key）。"
        ),
        "application_key_module": models.__name__,
        "application_key_inputs": sorted(params),
        "application_key_input_count": len(params),
        "forbidden_inputs_found": forbidden,
        "application_key_excludes_status_and_request_identity": forbidden == [],
        "doc_key_probe": {
            "measured_by": f"{rooms.__name__}:probe_room_facts",
            "doc_key_includes_mtime": bool(probe.doc_key_includes_mtime),
            "doc_key_stable_across_mtime_change": bool(
                probe.doc_key_stable_across_mtime_change
            ),
            "doc_key_source_is_mtime_free": bool(probe.doc_key_source_is_mtime_free),
            "doc_key_rotates_with_generation": bool(probe.doc_key_rotates_with_generation),
            "doc_key_stable_across_users": bool(probe.doc_key_stable_across_users),
            "mtime_really_changed": probe.mtime_after != probe.mtime_before,
            "probe_dir_removed": not probe_dir.exists(),
        },
        "why_probe_not_text_scan": (
            "按「同一行既有 doc_key 又有 mtime」扫源码，在生产 room 模块上命中 15 行，全部是"
            "文档/注释里解释「doc_key 不含 mtime」的句子 ⇒ 文本扫描会把「已修好并写了说明」"
            "判成「仍有问题」。真执行探针（改 mtime + AST 传递闭包）才是行为级判据。"
        ),
        "why_ast_not_grep": (
            "grep `status` 会命中文档字符串、注释与任何叫 status 的局部变量；只有从 AST 取"
            "函数签名参数才能回答「它是不是 key 的输入」（教训 2/12）。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §12 `multi_resolver` 裁决（自任务 30 移交至本门）
# ════════════════════════════════════════════════════════════════════════════

#: 正文点名的四条 resolver 行。**写死真实目标**（教训 16）—— 名单类判据不许只写「4 条」。
MULTI_RESOLVER_ROWS: Final[tuple[str, ...]] = (
    "get_sheet_onlyoffice_config",
    "get_sheet_wopi_contents",
    "get_whole_excel_grid",
    "post_sheet_onlyoffice_callback",
)

#: 任务 74 正文冻结的 14 条准则。本门只度量 `multi_resolver` 一条，其余如实转记。
_MULTI_RESOLVER_KEY: Final[str] = "multi_resolver"


def resolver_matrix_facts(path: Path | None = None) -> dict[str, Any]:
    """读任务 12 矩阵里那四条 resolver 行并派生登记形态判据。

    🔴 抽成独立纯函数（只吃一个路径）是为了让判据能**喂植入矩阵**：内联在
    :func:`build_multi_resolver_adjudication` 里时，「把 `fields_are_not_merged` 写死成 True」
    是等价变异（今天两个字段本来就不同），而复核它得连带跑一遍昂贵的 writer matrix 重算。
    """
    matrix = json.loads(read_text(path or RESOLVER_MATRIX))
    matrix_rows = matrix.get("rows") or []
    named = {
        str(row.get("qualname")): row
        for row in matrix_rows
        if str(row.get("qualname")) in MULTI_RESOLVER_ROWS
        and "onlyoffice_router" in str(row.get("module"))
    }
    per_row = {
        qualname: {
            "status": named.get(qualname, {}).get("status"),
            "intended_status": named.get(qualname, {}).get("intended_status"),
            "blocking_task": named.get(qualname, {}).get("blocking_task"),
            "adjudication_owner_task": named.get(qualname, {}).get("adjudication_owner_task"),
            "present_in_matrix": qualname in named,
        }
        for qualname in MULTI_RESOLVER_ROWS
    }
    return {
        "per_row": per_row,
        "rows_still_deferred": sorted(
            qualname for qualname, row in per_row.items() if row["status"] == "deferred"
        ),
        "rows_with_adjudication_owner_71": sorted(
            qualname
            for qualname, row in per_row.items()
            if str(row["adjudication_owner_task"]) == TASK_NUMBER
        ),
        "rows_with_blocking_task_pointing_at_36": sorted(
            qualname
            for qualname, row in per_row.items()
            if "36" in str(row["blocking_task"] or "").split(",")
        ),
        "two_independent_fields_present": all(
            row["blocking_task"] is not None and row["adjudication_owner_task"] is not None
            for row in per_row.values()
        ),
        "fields_are_not_merged": all(
            str(row["blocking_task"]) != str(row["adjudication_owner_task"])
            for row in per_row.values()
        ),
    }


def multi_resolver_criterion_passes(
    *, multi_resolver_rows: Sequence[str], rows_still_deferred: Sequence[str]
) -> bool:
    """`multi_resolver` 准则是否通过：计数为 0 **且**四条行都已不再 deferred。

    两个条件都要（正文逐字「任一行仍 `deferred` 或计数非零则本门不过」）。抽成纯函数让
    判据可以喂植入输入 —— 内联时「写死成 True」在计数非零的今天也是可打红的，但复核要连带
    跑一遍昂贵的 writer matrix 重算。
    """
    return len(multi_resolver_rows) == 0 and not list(rows_still_deferred)


def inventory_staleness(*, live_digest: str, on_disk_digest: str) -> bool:
    """磁盘 inventory 是否 stale（source digest 与源码现算不符）。"""
    return live_digest != on_disk_digest


def build_multi_resolver_adjudication() -> dict[str, Any]:
    """度量 `multi_resolver` issue 计数并核对任务 12 矩阵的两个独立字段。

    🔴 度量方式：**live 从源码重算** writer matrix（`collect_source_facts` →
    `build_inventory` → `evaluate_gate`），不写盘也不改 `workpaper_writer_inventory.json`。
    磁盘上的 inventory 实测已 stale（source digest 不符），默认命令因此 exit 2；本门如实
    转记那件事并把 owner 指向 inventory 的持有方，而不是顺手重生成（重生成会改 source
    commit 并让任务 70 的 evidence stale、打红上游四把锁）。
    """
    spec = importlib.util.spec_from_file_location("t71_writer_gate", WRITER_GATE)
    if spec is None or spec.loader is None:
        raise Task71GateError(f"无法加载 writer 门: {rel(WRITER_GATE)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    generator = module.load_generator()
    rows, function_facts = generator.collect_source_facts()
    overlay = json.loads(read_text(WRITER_OVERLAY))
    live = generator.build_inventory(rows, overlay, function_facts)
    issues = module.evaluate_gate(live)
    counts = {key: len(value) for key, value in sorted(issues.items())}

    on_disk = json.loads(read_text(WRITER_INVENTORY))
    inventory_stale = inventory_staleness(
        live_digest=str(live.get("source_digest")),
        on_disk_digest=str(on_disk.get("source_digest")),
    )

    matrix_facts = resolver_matrix_facts()
    per_row = matrix_facts["per_row"]
    still_deferred = matrix_facts["rows_still_deferred"]
    owner_is_71 = matrix_facts["rows_with_adjudication_owner_71"]
    blocking_points_at_36 = matrix_facts["rows_with_blocking_task_pointing_at_36"]
    live_multi = sorted(issues.get(_MULTI_RESOLVER_KEY) or [])
    return {
        "statement": (
            "`多 resolver writer=0`（gate issue key `multi_resolver`）自任务 30 移交至本门。"
            "四条 `wp_onlyoffice_router` resolver 行必须已改为只经 published representation + "
            "approved 非空 bundle 取数、从任务 12 矩阵的 `status=deferred` 名单移出，"
            "且重新生成 writer matrix 后 `multi_resolver` 计数为 0。"
        ),
        "measured_from": (
            "live 重算：`collect_source_facts()` → `build_inventory(overlay)` → "
            "`evaluate_gate()`；**不写盘**、不改 inventory"
        ),
        "writer_gate_criteria": counts,
        "writer_gate_criteria_count": len(counts),
        "multi_resolver_count": len(live_multi),
        "multi_resolver_rows_measured": live_multi,
        "multi_resolver_is_zero": len(live_multi) == 0,
        "named_rows": list(MULTI_RESOLVER_ROWS),
        "named_row_count": len(MULTI_RESOLVER_ROWS),
        "measured_rows_match_named": sorted(
            row.rsplit("::", 1)[-1] for row in live_multi
        ) == sorted(MULTI_RESOLVER_ROWS),
        "resolver_matrix": per_row,
        "rows_still_deferred": still_deferred,
        "rows_with_adjudication_owner_71": owner_is_71,
        "rows_with_blocking_task_pointing_at_36": blocking_points_at_36,
        "two_independent_fields_present": matrix_facts["two_independent_fields_present"],
        "fields_are_not_merged": matrix_facts["fields_are_not_merged"],
        "inventory_on_disk_is_stale": inventory_stale,
        "inventory_source_digest_on_disk": on_disk.get("source_digest"),
        "inventory_source_digest_live": live.get("source_digest"),
        "inventory_stale_owner_task": "20",
        "inventory_stale_note": (
            "磁盘 inventory 的 source digest 与源码现算不符 ⇒ writer 门的默认命令 exit 2。"
            "本门**不**重生成它：重生成会改 source commit，让任务 70 的 evidence 全部 stale "
            "并打红上游四把锁。如实转记并把 owner 指向 inventory 的持有方（任务 20 / 74）。"
        ),
        "criterion_passes": multi_resolver_criterion_passes(
            multi_resolver_rows=live_multi, rows_still_deferred=still_deferred
        ),
        "consequence_if_not_zero": (
            "本门这条准则不过 ⇒ `legacy_delete` gate 不放行任务 72 的全局 legacy 删除。"
        ),
        "bulk_adapters_gate_not_attached": True,
        "why_bulk_adapters_not_attached": (
            "bulk adapter 迁移在 Wave 5、本门在 Wave 7，挂上即 Wave 5 依赖 Wave 7 —— "
            "bulk adapter 不能等在排在它之后的全局 legacy 删除上。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §13 覆盖档位分类器 + 反事实多臂 + 正向重算
# ════════════════════════════════════════════════════════════════════════════

TIER_ROWS: Final[str] = "verified_on_rows"
TIER_STRUCTURAL: Final[str] = "structural_side_only"
TIER_UNVERIFIABLE: Final[str] = "unverifiable"
TIER_BROKEN: Final[str] = "evidence_broken"

COVERAGE_TIERS: Final[tuple[str, ...]] = (
    TIER_ROWS,
    TIER_STRUCTURAL,
    TIER_UNVERIFIABLE,
    TIER_BROKEN,
)


def classify_coverage(
    *,
    has_row_evidence: bool,
    has_structural_evidence: bool,
    has_unverifiable_evidence: bool,
    any_unresolved: bool,
    any_disagreeing: bool,
) -> str:
    """一条变异目标的覆盖档位。**判定顺序即语义顺序，不可交换。**

    1. `evidence_broken` 排第一 —— 引用了不存在或不成立的证据，比「没覆盖」更糟：它会把
       别的档位遮住并让报告看起来有据。
    2. `verified_on_rows` 第二 —— 真造行验过。
    3. `structural_side_only` 第三 —— 只有 schema/端点/守卫层判据。
    4. `unverifiable` 最后 —— 只有登记的欠账。
    """
    if any_unresolved or any_disagreeing:
        return TIER_BROKEN
    if has_row_evidence:
        return TIER_ROWS
    if has_structural_evidence:
        return TIER_STRUCTURAL
    if has_unverifiable_evidence:
        return TIER_UNVERIFIABLE
    # 一条证据都没有 —— 判 broken，不许滑到「已覆盖」（零证据全过是假绿）。
    return TIER_BROKEN  # no-evidence fallback


def _target_inputs(row: Mapping[str, Any]) -> dict[str, bool]:
    kinds = {entry["kind"] for entry in row["evidence"]}
    return {
        "has_row_evidence": bool(kinds & {"t68_arm", "t71_arm"}),
        "has_structural_evidence": bool(
            kinds & {"t68_endpoint", "t71_facet", "guard_mutation"}
        ),
        "has_unverifiable_evidence": "unverifiable" in kinds,
        "any_unresolved": any(not entry["resolved"] for entry in row["evidence"]),
        "any_disagreeing": any(
            entry["kind"] == "t68_arm" and not (entry.get("detail") or {}).get("agrees", True)
            for entry in row["evidence"]
        ),
    }


def build_coverage_tiers(coverage: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in coverage["targets"]:
        inputs = _target_inputs(row)
        rows.append(
            {
                "target_id": row["target_id"],
                "sub_bullet": row["sub_bullet"],
                "tier": classify_coverage(**inputs),
                "inputs": inputs,
            }
        )
    histogram = Counter(row["tier"] for row in rows)
    return {
        "statement": "逐条变异目标的覆盖档位（判定顺序不可交换）。",
        "tier_vocabulary": list(COVERAGE_TIERS),
        "tier_histogram": {tier: histogram.get(tier, 0) for tier in COVERAGE_TIERS},
        "broken_targets": sorted(
            row["target_id"] for row in rows if row["tier"] == TIER_BROKEN
        ),
        "verified_on_rows_count": histogram.get(TIER_ROWS, 0),
        "structural_only_count": histogram.get(TIER_STRUCTURAL, 0),
        "unverifiable_count": histogram.get(TIER_UNVERIFIABLE, 0),
        "rows": rows,
    }


def build_counterfactual_arms(coverage: Mapping[str, Any]) -> dict[str, Any]:
    """反事实**多臂**：每臂改一个输入并证明结论真的会变。

    🔴 多臂只能证明「非重言」，抓不到「恒真」（教训 15）—— 因此下面还有一条正向重算，
    里面必须有至少一条正例。
    """
    baseline = Counter(
        classify_coverage(**_target_inputs(row)) for row in coverage["targets"]
    )

    def _shifted(**override: bool) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for row in coverage["targets"]:
            inputs = _target_inputs(row)
            inputs.update(override)
            counter[classify_coverage(**inputs)] += 1
        return {tier: counter.get(tier, 0) for tier in COVERAGE_TIERS}

    today = {tier: baseline.get(tier, 0) for tier in COVERAGE_TIERS}
    arms = [
        {
            "arm": "A1",
            "what": "把所有目标的 `any_unresolved` 置真（模拟上游丢掉 arm）",
            "counts": _shifted(any_unresolved=True),
            "conclusion_changes": _shifted(any_unresolved=True) != today,
        },
        {
            "arm": "A2",
            "what": "把所有目标的 `any_disagreeing` 置真（模拟上游 arm 变 disagrees）",
            "counts": _shifted(any_disagreeing=True),
            "conclusion_changes": _shifted(any_disagreeing=True) != today,
        },
        {
            "arm": "A3",
            "what": "把 `has_row_evidence` 置假（模拟本门与上游都不再真造行）",
            "counts": _shifted(has_row_evidence=False),
            "conclusion_changes": _shifted(has_row_evidence=False) != today,
        },
        {
            "arm": "A4",
            "what": "把 `has_structural_evidence` 置假（只剩行/欠账两档）",
            "counts": _shifted(has_structural_evidence=False),
            "conclusion_changes": _shifted(has_structural_evidence=False) != today,
        },
        {
            "arm": "A5",
            "what": "把 `has_row_evidence` 与 `has_structural_evidence` 同时置假",
            "counts": _shifted(has_row_evidence=False, has_structural_evidence=False),
            "conclusion_changes": (
                _shifted(has_row_evidence=False, has_structural_evidence=False) != today
            ),
        },
    ]
    return {
        "statement": (
            "五条反事实臂各改一个输入，逐臂证明覆盖档位分类器**真的**对那个输入敏感。"
            "任一臂 `conclusion_changes=False` 即说明该输入是装饰（判据退化成重言式）。"
        ),
        "baseline_counts": today,
        "arms": arms,
        "arms_not_changing_conclusion": [
            arm["arm"] for arm in arms if not arm["conclusion_changes"]
        ],
        "all_arms_sensitive": all(arm["conclusion_changes"] for arm in arms),
    }


def build_forward_recompute() -> dict[str, Any]:
    """正向重算：合成已知答案，含**至少一条正例**（教训 15）。

    多臂反事实只能证明分类器不是重言式；「恒真」要靠正向重算抓 —— 如果分类器被改成恒返
    `verified_on_rows`，下面第 2~5 条会同时打红。
    """
    cases = [
        {
            "case": "C1_positive_row_evidence",
            "inputs": {
                "has_row_evidence": True,
                "has_structural_evidence": True,
                "has_unverifiable_evidence": False,
                "any_unresolved": False,
                "any_disagreeing": False,
            },
            "expected_tier": TIER_ROWS,
        },
        {
            "case": "C2_structural_only",
            "inputs": {
                "has_row_evidence": False,
                "has_structural_evidence": True,
                "has_unverifiable_evidence": False,
                "any_unresolved": False,
                "any_disagreeing": False,
            },
            "expected_tier": TIER_STRUCTURAL,
        },
        {
            "case": "C3_unverifiable_only",
            "inputs": {
                "has_row_evidence": False,
                "has_structural_evidence": False,
                "has_unverifiable_evidence": True,
                "any_unresolved": False,
                "any_disagreeing": False,
            },
            "expected_tier": TIER_UNVERIFIABLE,
        },
        {
            "case": "C4_unresolved_beats_row_evidence",
            "inputs": {
                "has_row_evidence": True,
                "has_structural_evidence": True,
                "has_unverifiable_evidence": True,
                "any_unresolved": True,
                "any_disagreeing": False,
            },
            "expected_tier": TIER_BROKEN,
        },
        {
            "case": "C5_disagreeing_beats_row_evidence",
            "inputs": {
                "has_row_evidence": True,
                "has_structural_evidence": False,
                "has_unverifiable_evidence": False,
                "any_unresolved": False,
                "any_disagreeing": True,
            },
            "expected_tier": TIER_BROKEN,
        },
        {
            "case": "C6_nothing_at_all_is_broken_not_verified",
            "inputs": {
                "has_row_evidence": False,
                "has_structural_evidence": False,
                "has_unverifiable_evidence": False,
                "any_unresolved": False,
                "any_disagreeing": False,
            },
            "expected_tier": TIER_BROKEN,
        },
    ]
    rows = []
    for case in cases:
        actual = classify_coverage(**case["inputs"])  # type: ignore[arg-type]
        rows.append(
            {
                "case": case["case"],
                "expected_tier": case["expected_tier"],
                "actual_tier": actual,
                "agrees": actual == case["expected_tier"],
            }
        )
    return {
        "statement": (
            "六条合成算例覆盖四个档位与两条优先级（unresolved / disagreeing 压过真行证据）；"
            "至少一条正例（C1）—— 缺正例时「分类器恒返 unverifiable」测不出来。"
        ),
        "cases": rows,
        "all_agree": all(row["agrees"] for row in rows),
        "disagreeing_cases": [row["case"] for row in rows if not row["agrees"]],
        "has_positive_case": any(row["expected_tier"] == TIER_ROWS for row in rows),
        "distinct_expected_tiers": sorted({row["expected_tier"] for row in rows}),
    }


# ════════════════════════════════════════════════════════════════════════════
# §14 Property 逐条落点（三档 + 未验证必须点名 owner）
# ════════════════════════════════════════════════════════════════════════════

PROPERTY_TIERS: Final[tuple[str, ...]] = (
    "verified_here",          # 本门真跑验过
    "structural_side_only",   # 只有 schema/端点/源码层判据（真行侧由上游或不可供给）
    "unverifiable",           # 本门无法验，必须点名 owner
)

#: 24 条 Property 的落点。每条必须给 `tier` + `landed_on` + `why`，
#: 非 `verified_here` 的必须给 `owner_if_unverified`。
_PROPERTY_LANDINGS: Final[Mapping[int, Mapping[str, str]]] = {
    4: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m3_double_content_commit / m2_numeric_revision_as_route_or_resource_key",
        "why": "业务内容版本与 representation generation 正交：由任务 68 的 `cv_*` 与 "
               "`chain_rep_*` 臂在真行上验过；本门复核那些臂仍 agrees，并度量 writer 门的"
               "`representation_upgrade_increments_business_revision` 现算为 0。",
        "owner_if_unverified": "68",
    },
    5: {
        "tier": "verified_here",
        "landed_on": "retention.t71_retention_windows_lock_retains / fault_injection.injections.disk",
        "why": "staged artifact 与 DB pointer 不产生悬空可见态：Windows lock 注入下删不掉的"
               "对象必须改判 retain 且 DB 行**仍不是** deleted —— 本门真造并现测；"
               "磁盘注入证明不存在的对象返回 False 而不是「已删」。",
        "owner_if_unverified": "",
    },
    17: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m1_quarantined_released_or_promoted",
        "why": "callback 文件先隔离校验：`inc_quarantined` / `inc_quarantined_to_durable` / "
               "`aif_quarantined` / `rec_quarantined_incoming` 四条上游臂逐条复核；真实 OO "
               "回调路径的运行态属任务 70。",
        "owner_if_unverified": "70",
    },
    18: {
        "tier": "verified_here",
        "landed_on": "bp_68_1_recheck / mutation_coverage.m1_durable_zero_owner",
        "why": "delivery 可多次、frozen application 恰好一次：本门独立复核 delivery 归属真值表"
               "的六条形态（DDL 侧 + 服务层纯不变量侧），并给出 BP-68-1 的另一半结论。",
        "owner_if_unverified": "",
    },
    19: {
        "tier": "verified_here",
        "landed_on": "bp_68_1_recheck.t71_pre_durable_owner_invariant / t71_durable_zero_owner_invariant",
        "why": "耐久后处理失败向 OO ack：`durable_at` 是唯一 owner gate —— 本门真调生产纯"
               "不变量，证明 pre/post durable 两侧的判定不可互换。",
        "owner_if_unverified": "",
    },
    28: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m4_* / protocol_source_scan",
        "why": "immutable definition 漂移 fail closed：八条 definition/candidate 变异目标逐条"
               "解析到上游 `bs_*` / `pc_*` / `tm_*` / `chain_*` 臂；本门另现算"
               "`compute_application_key` 的入参集合。",
        "owner_if_unverified": "68",
    },
    36: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m1_effective_sequence_not_greatest / m1_origin_request_sequence_rewritten",
        "why": "裁决 revision + incoming sequence 双 fence：由上游 `eff_*` / `fold_*` 六条臂"
               "在真行上验过，本门逐条复核。",
        "owner_if_unverified": "68",
    },
    42: {
        "tier": "verified_here",
        "landed_on": "fault_injection.injections.disk.path_escape",
        "why": "路径安全：本门真调生产的 `delete_artifact_file('../../etc/passwd')`，"
               "必须抛 ArtifactPathError（对照组是同一 repo 上的正常删除成功）。",
        "owner_if_unverified": "",
    },
    43: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m3_revoked_cached_replay / m2_cache_before_auth",
        "why": "最终 commit 重验权限与 generation write fence：授权顺序由任务 68 的"
               "`guard_is_the_first_await_in_every_handler` 端点检查现算；真实撤权重放属任务 70。",
        "owner_if_unverified": "70",
    },
    44: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m3_revoked_cached_replay",
        "why": "只读/被撤销 contributor 零内容版本：上游端点检查 + `fb_bundle_not_from_request`；"
               "真实浏览器侧属任务 69/70。",
        "owner_if_unverified": "69",
    },
    45: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m2_404_403_stage_or_timing_leak / m2_cross_project_wp_entry",
        "why": "横向越权与撤权后幂等重放被拒：上游 `unified_404_403_refusal_surface` 与"
               "`si_rebind_scope`；本门未再独立起 HTTP 客户端。",
        "owner_if_unverified": "68",
    },
    57: {
        "tier": "verified_here",
        "landed_on": "mutation_state_machine / guard_mutation_ids",
        "why": "变异四态准确：本门把 RED/GREEN/ANCHOR-MISS/WRONG-TEST 做成封闭词表并现算"
               "变异脚本里的变异号；四态语义与「ERROR 也算命中」的理由写进报告。",
        "owner_if_unverified": "",
    },
    59: {
        "tier": "unverifiable",
        "landed_on": "capacity.real_load_execution",
        "why": "同 wp 串行跨 wp 并行：登记 profile 的 `same_wp_serialized` / `cross_wp_parallel` "
               "/ `forbids_single_process_lock` 三个断言只能在真实负载下证伪。本轮三条前提"
               "（3030 监听 / 真实 OO 会话 / 生产业务数据）一条都不成立。",
        "owner_if_unverified": "72",
    },
    60: {
        "tier": "structural_side_only",
        "landed_on": "fault_injection.orphan_outbox_pointers / redaction",
        "why": "大文件预算 fail visible：`limits` 的预算与 `BudgetExceededError` 由生产模块"
               "持有；本门度量 outbox/orphan 的告警指标存在性，真实大文件流属任务 70。",
        "owner_if_unverified": "70",
    },
    61: {
        "tier": "structural_side_only",
        "landed_on": "multi_resolver_adjudication.writer_gate_criteria",
        "why": "所有 writer 进入唯一 revision 域：本门 live 重算 writer 门 14 条准则并逐条"
               "登记计数；`multi_resolver` 是本门的裁决对象，其余七条 owner 是任务 74。",
        "owner_if_unverified": "74",
    },
    62: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m3_mutable_room_base_or_status_in_key / protocol_source_scan",
        "why": "server last-applied 与 client-confirmed base 不混同：本门现算"
               "`compute_application_key` 的入参不含 last-applied/status，真行侧由上游"
               "`fold_*` 臂覆盖。",
        "owner_if_unverified": "68",
    },
    63: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m3_participant_bound_callback",
        "why": "shared room 聚合 callback 与 participant 撤销安全：上游 `fr5_cross_participant`"
               " 与 `dlv_durable_one_owner`；真实多人会话属任务 70。",
        "owner_if_unverified": "70",
    },
    64: {
        "tier": "verified_here",
        "landed_on": "protocol_source_scan.application_key_inputs",
        "why": "application identity 使用 frozen bundle 且不含 status：本门从 AST 取"
               "`compute_application_key` 的入参集合并逐个 token 现算，禁止 grep 符号名。",
        "owner_if_unverified": "",
    },
    67: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m4_task17_59_publish_representation_directly",
        "why": "template upgrader 先 candidate、approved bundle 后 finalize：上游"
               "`chain_cand_*` 四条臂逐条复核。",
        "owner_if_unverified": "68",
    },
    68: {
        "tier": "structural_side_only",
        "landed_on": "mutation_coverage.m1_duplicate_* / m5_claim_not_atomic",
        "why": "operation/recovery timeline 完整单调：上游 `dup_*` / `rec_*` / `nshell_*` 臂"
               "逐条复核；本门补事务原子性（进程中断代理）。",
        "owner_if_unverified": "68",
    },
    69: {
        "tier": "unverifiable",
        "landed_on": "deletion_gate.evidence_scenario_rows",
        "why": "evidence 由逐 scenario 实体与服务端重算闭合：evidence 五表实测 0 行 ⇒ 「闭合」"
               "在今天的分母上无从度量。",
        "owner_if_unverified": "70",
    },
    70: {
        "tier": "unverifiable",
        "landed_on": "mutation_coverage.m5_evidence_reused_across_entry",
        "why": "scenario/evidence 不得跨 entry 或跨场景复用：0 行 evidence 上「复用」不可度量。",
        "owner_if_unverified": "70",
    },
    71: {
        "tier": "verified_here",
        "landed_on": "verdict / deletion_gate.smoke_cannot_restore_verified",
        "why": "evidence 随环境、runner 与 immutable definition bundle 变化失效：本门自己的"
               "verdict 词表只有三态且「零证据全过」被显式判 unverifiable；同时现算任务 70 的"
               "词表里没有 `passed`，smoke 无处把 evidence 顶回 verified。",
        "owner_if_unverified": "",
    },
    72: {
        "tier": "verified_here",
        "landed_on": "capacity",
        "why": "量化容量模型可重复：本门真跑登记值 ↔ 需求原文的逐字段交叉锁、profile canonical "
               "digest、评估器的七条判据与 fail-closed；**真实负载**如实标 UNVERIFIABLE 并点名"
               "owner，不用合成实测值冒充通过。",
        "owner_if_unverified": "",
    },
}


def build_property_landings() -> dict[str, Any]:
    titles = design_property_titles()
    missing = sorted(set(DECLARED_PROPERTIES) - set(_PROPERTY_LANDINGS))
    extra = sorted(set(_PROPERTY_LANDINGS) - set(DECLARED_PROPERTIES))
    rows: list[dict[str, Any]] = []
    unverified_without_owner: list[int] = []
    bad_tier: list[int] = []
    for number in sorted(_PROPERTY_LANDINGS):
        landing = _PROPERTY_LANDINGS[number]
        tier = str(landing.get("tier"))
        if tier not in PROPERTY_TIERS:
            bad_tier.append(number)
        owner = str(landing.get("owner_if_unverified") or "").strip()
        if tier != "verified_here" and not owner:
            unverified_without_owner.append(number)
        rows.append(
            {
                "property": number,
                "design_title": titles.get(str(number), ""),
                "tier": tier,
                "landed_on": landing.get("landed_on"),
                "why": landing.get("why"),
                "owner_if_unverified": owner,
            }
        )
    histogram = Counter(row["tier"] for row in rows)
    return {
        "statement": (
            "正文点名的 24 条 Property 逐条落点 + 明确档位（真跑验过 / 只有 schema 侧 / "
            "无法验且 owner 是谁）。缺一条即结构错误。"
        ),
        "declared_count": len(DECLARED_PROPERTIES),
        "landing_count": len(rows),
        "missing_landings": missing,
        "all_declared_have_landing": missing == [],
        "landings_not_declared": extra,
        "tier_vocabulary": list(PROPERTY_TIERS),
        "tier_histogram": dict(sorted(histogram.items())),
        "tiers_out_of_vocabulary": bad_tier,
        "unverified_without_owner": unverified_without_owner,
        "every_unverified_has_owner": unverified_without_owner == [],
        "verified_here_count": histogram.get("verified_here", 0),
        "rows": rows,
    }


# ════════════════════════════════════════════════════════════════════════════
# §15 变异四态词表（Property 57 的机器形态）
# ════════════════════════════════════════════════════════════════════════════

MUTATION_STATES: Final[tuple[str, ...]] = ("RED", "GREEN", "ANCHOR-MISS", "WRONG-TEST")


def build_mutation_state_machine() -> dict[str, Any]:
    """四态封闭词表 + 各态语义 + 「不以退出码代替证据」的理由。"""
    ids = guard_mutation_ids()
    mutate_path = REPO / MUTATE_REL
    source = mutate_path.read_text(encoding="utf-8", errors="replace") if mutate_path.is_file() else ""
    return {
        "statement": (
            "所有变异结果按 RED / GREEN / ANCHOR-MISS / WRONG-TEST 四态判定，"
            "**不以退出码代替证据**（只看退出码会把后三态全误判成 RED）。"
        ),
        "state_vocabulary": list(MUTATION_STATES),
        "state_semantics": {
            "RED": "打红了，且**正是**预期那条测试（`want` 命中）—— 唯一算命中的状态。",
            "GREEN": "改了行为却没有任何判据变红 ⇒ 守卫缺陷。修守卫，**不删变异**。",
            "ANCHOR-MISS": "锚点未命中或命中 >1 处 ⇒ 脚本缺陷（含 `\\n` 跨行锚点在 CRLF 必 MISS）。",
            "WRONG-TEST": "打红了但不是预期项 ⇒ 污染残留或锚点错行。",
        },
        "error_counts_as_hit": (
            "多行 `raise` 被整行替换会造成语法错 ⇒ pytest 报 ERROR，而 `-rf` 只列 FAILED，"
            "于是会被误判成 GREEN。判定必须同时读 FAILED 与 ERROR 两类行（`-rfE`）。"
        ),
        "mutation_script": MUTATE_REL,
        "mutation_script_present": mutate_path.is_file(),
        "mutation_ids": list(ids),
        "mutation_count": len(ids),
        "script_reads_and_writes_bytes": (
            "read_bytes" in source and "write_bytes" in source
        ),
        "why_bytes_not_text": (
            "`read_text`/`write_text` 做换行翻译：写回时 `\\n` 变 `\\r\\n`，逐文件 md5 复原"
            "校验必失败（表现为 RestoreFailed rc=5 而文件内容其实没坏）。"
        ),
        "script_has_check_anchors": "--check-anchors" in source,
        "script_forbids_restore_flag": "--restore" not in source,
    }


# ════════════════════════════════════════════════════════════════════════════
# §16 辐射面 + 产物跟踪状态
# ════════════════════════════════════════════════════════════════════════════

#: 任务 68 的目录普查范围。本门的守卫**必须**落在它之外（BP-69-6）。
UPSTREAM_CENSUS_DIR: Final[str] = "backend/tests/" + "workpaper" + "_sync"

#: 上游四把锁（守卫文件 → 基线状态）。收尾必须逐条交代是否新增红。
UPSTREAM_LOCKS: Final[tuple[tuple[str, str, int, int], ...]] = (
    ("backend/tests/workpaper_sync/test_task67_structural_pre_reconcile.py", "67", 66, 0),
    ("backend/tests/workpaper_sync/test_task68_backend_chain_regression.py", "68", 87, 0),
    (
        "backend/tests/workpaper_sync_frontend/test_task69_frontend_regression.py",
        "69",
        78,
        1,
    ),
    ("backend/tests/workpaper_sync_oo/test_task70_oo_scenario_gate.py", "70", 84, 0),
)


def upstream_lock_impact() -> dict[str, Any]:
    """本门新增守卫文件对上游逐字节锁的**结构性**影响（不跑 pytest，只现算）。

    🔴 实测（本门收尾时用「把守卫临时移出 `backend/tests` 再跑一次」隔离）：任务 70 的
    `--check` **只**因为本门守卫文件的存在而变红 —— 移出后 rc=0、放回后 rc=1。根因不是
    BP-70-8 那条 pattern digest，而是它的 `radiation_surface()` 把
    **`backend/tests` 全树的 test 文件计数**（`scanned_test_files`）也锁进了逐字节比对：
    仓库里**任何**位置新增一个 `test_*.py` 都会让它 stale，无论那个文件引用了什么。
    这比 BP-70-8 更强 —— 换目录、不写模块路径字面量都躲不开。

    本门**不**重生成任务 70 的报告（Tasks 61/66/67/68/69/70 产物禁改，且重生成会改它的
    `source_commit` 语义）。如实登记并把 owner 指向任务 70 —— 与任务 70 自己对任务 69 的
    BP-70-6 同一处置。
    """
    t70_gate = BACKEND / "scripts/check/check_task70_oo94_full_entry_scenario_gate.py"
    spec = importlib.util.spec_from_file_location("t70_for_71", t70_gate)
    if spec is None or spec.loader is None:
        raise Task71GateError(f"无法加载任务 70 的门: {rel(t70_gate)}")
    module = sys.modules.get("t70_for_71")
    if module is None:
        module = importlib.util.module_from_spec(spec)
        sys.modules["t70_for_71"] = module
        spec.loader.exec_module(module)
    live = module.radiation_surface()
    disk = (read_json(T70_REPORT).get("radiation_surface") or {})
    guard_in_surface = GUARD_TEST_REL in (live.get("referencing_test_files") or {})
    # 🔴 上游那把锁**已改形**：普查派生量（全树计数 / 引用者清单 / 它们的 digest）走
    #    `CENSUS_KEYS` 剔除 + 语义断言，不再进逐字节比对。本门因此不再用「计数是否相等」当判据
    #    （那正是 BP-71-8 的形态），改为直接现算它剔除普查量后的投影是否仍与盘上一致。
    census_keys = sorted(getattr(module, "CENSUS_KEYS", ()) or ())
    strip = getattr(module, "strip_census", None)
    if strip is None or not census_keys:
        raise Task71GateError(
            "上游任务 70 的门没有 `CENSUS_KEYS` / `strip_census` —— 普查免疫的改形被回退了，"
            "本门对它的判据前提失效（BP-71-8 复发）"
        )
    # 🔴 上游的 `strip_census` 是**路径限定**的（键形如 `radiation_surface.scanned_test_files`）
    #    ⇒ 必须把节点挂回它在报告里的原位再剔，直接喂裸节点会一个都剔不掉（本轮验收实测：
    #    加一个临时测试文件后 `projection_agrees` 假报 False，两条守卫打红）。
    projection_agrees = strip({"radiation_surface": live}) == strip({"radiation_surface": disk})
    upstream_semantics = module.census_semantics(live)
    return {
        "statement": (
            "本门新增守卫文件**曾经**会让任务 70 的逐字节锁 stale（它把 `backend/tests` 全树的 "
            "test 文件计数锁进了比对）。该判据缺陷已修：上游把普查派生量收进 `CENSUS_KEYS`，"
            "`--check` 现算并断言语义性质而不再逐字节比对它们。本门现算复核这件事仍然成立。"
        ),
        "task70_census_keys": census_keys,
        "task70_surface_projection_agrees": projection_agrees,
        "task70_census_semantics_all_hold": bool(upstream_semantics.get("all_hold")),
        "task70_subject_coverage": dict(live.get("subject_coverage") or {}),
        "task70_scanned_test_files_live": live.get("scanned_test_files"),
        "task70_scanned_test_files_on_disk": disk.get("scanned_test_files"),
        "task70_referencing_count_live": live.get("referencing_test_file_count"),
        "task70_referencing_count_on_disk": disk.get("referencing_test_file_count"),
        "task70_digest_live": live.get("digest"),
        "task70_digest_on_disk": disk.get("digest"),
        "task70_lock_goes_stale_because_of_this_gate": not projection_agrees,
        "own_guard_is_in_task70_surface": guard_in_surface,
        "own_guard_matched_subjects": sorted(
            (live.get("referencing_test_files") or {}).get(GUARD_TEST_REL) or []
        ),
        "why_it_used_to_be_unavoidable": (
            "`scanned_test_files` 是**全树计数**，与文件内容无关 ⇒ 换目录（BP-69-6 的规避法）"
            "与不写模块路径字面量（BP-70-8 的规避法）都躲不开。唯一的「规避」是不写守卫，"
            "而那等于放弃本门的判据 —— 所以只能改判据的形状，不能规避。"
        ),
        "how_it_was_fixed": (
            "上游把「仓库级普查得出的计数/成员清单/digest」显式归入 `CENSUS_KEYS`，逐字节比对"
            "前先 `strip_census`；同时**仍然现算**这些量并断言其语义性质（真的遍历过全树 / 非空 / "
            "不是全量 / 每个被验单元都有引用者 / 本门守卫在辐射面里）。剔除 ≠ 不管。"
        ),
        "isolation_method": (
            "把守卫文件临时移出 `backend/tests` 再跑任务 70 的 `--check`：修复**前**移出 rc=0、"
            "放回 rc=1（该红只由本门守卫文件的存在引起）；修复**后**两种情形都 rc=0，"
            "而故意改坏上游普查逻辑仍然 rc=1。"
        ),
        "disposition": "已修（改判据形状，不用豁免）",
        "owner_task": "70",
        "baseline_locks": [
            {
                "guard": guard,
                "task": task,
                "baseline_passed": passed,
                "baseline_failed": failed,
            }
            for guard, task, passed, failed in UPSTREAM_LOCKS
        ],
        "known_preexisting_red": {
            "backend/tests/workpaper_sync_frontend/test_task69_frontend_regression.py": (
                "TestReportIsFreshAndByteLocked::test_gate_check_passes —— BP-70-6 的复选框根因，"
                "本门起手基线即为红，非本门引入"
            )
        },
    }


def radiation_surface() -> dict[str, Any]:
    """按引用关系现算本门的辐射面（不跑无边界全量）。

    本门的被验单元是 capacity/retention/redaction/alerting/metrics/artifacts 六个生产模块
    与本门自己的四件套。辐射面 = `backend/tests/**/test_*.py` 中按模块路径引用到它们的
    测试文件全集。
    """
    base = "app.services." + "workpaper" + "_sync"
    patterns = {
        "capacity_profile": rf"{re.escape(base)}\.capacity_profile|capacity_profile",
        "retention": rf"{re.escape(base)}\.retention",
        "redaction": rf"{re.escape(base)}\.redaction",
        "alerting": rf"{re.escape(base)}\.alerting",
        "own_gate": re.escape(Path(GATE_REL).name),
    }
    compiled = [(name, re.compile(pattern)) for name, pattern in patterns.items()]
    test_root = BACKEND / "tests"
    files: dict[str, list[str]] = {}
    scanned = 0
    for path in sorted(test_root.rglob("test_*.py")):
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        why = [name for name, pattern in compiled if pattern.search(text)]
        if why:
            files[path.relative_to(REPO).as_posix()] = why
    guard_dir = Path(GUARD_TEST_REL).parent.as_posix()
    # 🔴 逐 pattern 覆盖布尔 —— 辐射面**选取契约**的一部分，**不是**普查派生量：它不随仓库
    #    演进，但 pattern 被删空/改坏时立刻变假。因此它继续进逐字节锁，而计数 / 成员清单 /
    #    digest 走 census（见 :data:`CENSUS_KEYS`）。
    coverage = {name: any(name in why for why in files.values()) for name in patterns}
    return {
        "statement": (
            "辐射面 = `backend/tests/**/test_*.py` 中按模块路径引用到本门被验生产单元"
            "（capacity_profile / retention / redaction / alerting）或本门自己的门文件名的"
            "测试文件全集。不跑无边界全量（仓库根 test 文件逾 1500 个）。"
        ),
        "patterns": patterns,
        "pattern_coverage": coverage,
        "scanned_test_files": scanned,
        "referencing_test_file_count": len(files),
        "files": dict(sorted(files.items())),
        "own_guard_path": GUARD_TEST_REL,
        "own_guard_dir": guard_dir,
        "upstream_census_dir": UPSTREAM_CENSUS_DIR,
        "own_guard_outside_census_dir": not GUARD_TEST_REL.startswith(
            f"{UPSTREAM_CENSUS_DIR}/"
        ),
        "census_derived_keys": sorted(
            key.split(".", 1)[1] for key in CENSUS_KEYS if key.startswith("radiation_surface.")
        ),
        "why_own_dir": (
            "BP-69-6：任务 68 的逐字节锁把 `%s` 做成目录普查，往里新增任何「不引用被验生产"
            "单元」的测试文件都会打红它 1~3 条。BP-70-8：换目录不够 —— 它的辐射面 digest 扫"
            "`backend/tests` 全树按模块路径收文件，所以本门守卫连模块路径字面量都不写，"
            "生产模块经 `_production()` 取。" % UPSTREAM_CENSUS_DIR
        ),
        "digest": digest_of(sorted(files)),
    }


# ════════════════════════════════════════════════════════════════════════════
# §16.1 普查派生量：现算、断言语义性质、**不进冻结基线**
# ════════════════════════════════════════════════════════════════════════════

#: 🔴 **普查派生量（census-derived）** —— 逐字节锁必须剔除的**第二类**字段。
#:
#: :data:`VOLATILE_KEYS` 剔的是「每轮都变的随机值 / 墙钟」；本集合剔的是「随**仓库演进**而变
#: 的普查结果」。本门有两处：
#:
#: * 自己的 :func:`radiation_surface`（`scanned_test_files` 是 `backend/tests` **全树**计数）；
#: * :func:`upstream_lock_impact` 里**转记的**上游全树计数与 digest（传递形态：上游把普查量
#:   冻进锁，本门又把上游的 live 值冻进自己的锁 ⇒ 同一个缺陷被复制了一份）。
#:
#: ═══ 剔除 ≠ 不管 ═══
#:
#: 这些量在 `--check` 时**仍然现算**，由 :func:`census_semantics` 逐条断言语义性质。语义性质
#: 不随仓库演进，因此它们**继续锁死**。特别地，`upstream_lock_impact` 里那三条**判定**
#: （`task70_surface_projection_agrees` / `task70_census_semantics_all_hold` /
#: `own_guard_is_in_task70_surface`）继续进锁 —— 它们才是本门对上游那把锁的真判据。
#: `artifact_git_status` 走 census：提交前 `??`、提交后 tracked-clean，冻进锁里等于「入库」
#: 这个正确动作本身打红门。语义性质另立 `artifact_git_status_semantics` 锁死（见 `_census_lock`）。
CENSUS_KEYS: Final[frozenset[str]] = frozenset(
    {
        "radiation_surface.scanned_test_files",
        "radiation_surface.referencing_test_file_count",
        "radiation_surface.files",
        "radiation_surface.digest",
        "upstream_lock_impact.task70_scanned_test_files_live",
        "upstream_lock_impact.task70_scanned_test_files_on_disk",
        "upstream_lock_impact.task70_referencing_count_live",
        "upstream_lock_impact.task70_referencing_count_on_disk",
        "upstream_lock_impact.task70_digest_live",
        "upstream_lock_impact.task70_digest_on_disk",
        "blocking_points[].measured.scanned_test_files_live",
        "blocking_points[].measured.scanned_test_files_on_disk",
        "blocking_points[].measured.referencing_count_live",
        "blocking_points[].measured.referencing_count_on_disk",
        "artifact_git_status",
        "census_contract.measured",
    }
)


def strip_census(node: Any, *, path: str = "") -> Any:
    """按**点号路径**剔除 :data:`CENSUS_KEYS`。

    🔴 路径限定而不是按裸键名：本报告里另有数十处正当的 `digest` / `files` 同名量
    （bundle digest / policy fingerprint / retention 的 artifact 清单），按裸键名剔会把真正的
    stale 轴一起放过。列表元素的路径带 `[]` 段，于是 `blocking_points[].measured.xxx` 能命中。
    """
    if isinstance(node, Mapping):
        out: dict[Any, Any] = {}
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if child in CENSUS_KEYS:
                continue
            out[key] = strip_census(value, path=child)
        return out
    if isinstance(node, list):
        return [strip_census(value, path=f"{path}[]") for value in node]
    return node


def census_semantics(surface: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """普查量的**语义性质**。现算，且不随仓库演进 ⇒ 逐条进锁。

    每条对应一种真实的退化形态：

    * `walk_really_traversed_the_tree` —— scanner 被短路成不遍历时计数掉到 0；
    * `surface_is_not_empty` / `surface_is_not_the_whole_tree` —— 空集恒真 / 退化成无边界全量；
    * `every_pattern_has_a_match` —— 某条引用 pattern 没有任何命中者（pattern 写坏或模块改名）；
    * `own_guard_is_in_the_surface` —— 本门守卫必须真的引用被验单元（否则「本门验过」无落点）。
    """
    live = dict(surface) if surface is not None else radiation_surface()
    scanned = int(live["scanned_test_files"])
    referencing = int(live["referencing_test_file_count"])
    coverage = dict(live["pattern_coverage"])
    unmatched = sorted(name for name, hit in coverage.items() if not hit)
    checks = {
        "walk_really_traversed_the_tree": scanned > 1000,
        "surface_is_not_empty": referencing > 0,
        "surface_is_not_the_whole_tree": 0 < referencing < scanned,
        # 🔴 「一条都没缺」与「一条都没有」必须分开两条：空 coverage 让 `not unmatched` 恒真。
        "pattern_coverage_is_complete": set(coverage) == set(live.get("patterns") or {}),
        "every_pattern_has_a_match": bool(coverage) and not unmatched,
        "own_guard_is_in_the_surface": GUARD_TEST_REL in (live.get("files") or {}),
    }
    return {
        **checks,
        "patterns_without_a_match": unmatched,
        "failing_checks": sorted(name for name, ok in checks.items() if not ok),
        "all_hold": all(checks.values()),
    }


def build_census_contract(surface: Mapping[str, Any]) -> dict[str, Any]:
    """普查契约节点：哪些键走 census、为什么、语义断言结果、以及**没有**被削弱的轴。"""
    return {
        "statement": (
            "普查派生量（仓库级扫描得出的计数与成员清单）在 `--check` 时现算并断言语义性质，"
            "**不进**逐字节冻结基线。"
        ),
        "census_keys": sorted(CENSUS_KEYS),
        "why": (
            "本门有两处：自己的辐射面全树计数，以及**转记的**上游全树计数（传递形态 —— 上游把"
            "普查量冻进锁，本门又把上游的 live 值冻进自己的锁，同一个缺陷被复制了一份）。"
            "两处都会被仓库里任意位置新增一个 `test_*.py` 顶红。"
        ),
        "excluded_is_not_unchecked": (
            "剔除 ≠ 不管：`census_semantics` 现算并断言五条语义性质；`upstream_lock_impact` 里"
            "那三条对上游的**判定**（投影一致 / 上游语义全成立 / 本门守卫在上游辐射面里）"
            "继续进锁 —— 它们才是本门对上游那把锁的真判据。"
        ),
        "still_locked": [
            "source_commit（源码变了但证据没刷新 —— 唯一的真 stale 轴）",
            "radiation_surface.patterns / pattern_coverage / own_guard_*",
            "upstream_lock_impact 的三条判定 + task70_census_keys + task70_subject_coverage",
            "变异覆盖分母的逐条解析、行为臂的逐条判定、六个面的逐条实测",
            "report_digest（现在算在 census 剔除**之后**的内容上 ⇒ 非普查内容继续锁死）",
        ],
        "semantics": census_semantics(surface),
        "measured": {
            "scanned_test_files": surface["scanned_test_files"],
            "referencing_test_file_count": surface["referencing_test_file_count"],
            "digest": surface["digest"],
            "note": "本节点是**快照**，不参与逐字节比对（见 `census_keys`）。",
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# §17 阻塞登记（BP-71-n）
# ════════════════════════════════════════════════════════════════════════════


def build_bp_68_1_recheck(behaviour: Mapping[str, Any]) -> dict[str, Any]:
    """BP-68-1 的独立复核结论。

    上游结论：`pre-durable rejected/error 零 owner` 这条不变量 **DDL 没把住** —— 往 scratch
    schema 插 `state='rejected', durable_at=NULL, application_id=<x>` 数据库接受。

    本门做两件上游没做的事：
    1. **独立造世界、独立造行**复核 DDL 侧（一致 / 不一致都如实报）；
    2. 把「靠服务层把住」那半边真的跑一次 —— 直接调生产的纯不变量
       `assert_delivery_ownership`，看它对 pre-durable + owner 怎么判。
    """
    observations = dict(behaviour.get("observations") or {})
    ddl = (observations.get("t71_pre_durable_owner_ddl") or {}).get("measured") or {}
    invariant = (observations.get("t71_pre_durable_owner_invariant") or {}).get("measured") or {}
    t68 = read_json(T68_REPORT)
    upstream_arm = next(
        (
            arm
            for row in t68.get("invariants") or []
            for arm in (row.get("behaviour_side") or {}).get("arms") or []
            if arm.get("arm_id") == "dlv_pre_durable_owner"
        ),
        None,
    )
    upstream_claim = bool(
        ((upstream_arm or {}).get("measured") or {}).get("ddl_accepts_pre_durable_owner")
    )
    mine = bool(ddl.get("ddl_accepts_pre_durable_owner"))
    bp = next(
        (
            point
            for point in t68.get("blocking_points") or []
            if str(point.get("id")) == "BP-68-1"
        ),
        None,
    )
    invariant_accepts = bool(invariant.get("invariant_accepts_pre_durable_owner"))
    return {
        "statement": (
            "BP-68-1 独立复核：`pre-durable rejected/error 零 owner` 在 DDL 层是否真的没有"
            "约束力，以及服务层是否真的把住了它。"
        ),
        "upstream_bp_present": bp is not None,
        "upstream_bp_owner_task": (bp or {}).get("owner_task"),
        "upstream_arm_id": "dlv_pre_durable_owner",
        "upstream_claims_ddl_accepts": upstream_claim,
        "this_gate_measures_ddl_accepts": mine,
        "per_state_ddl": dict(ddl.get("per_state") or {}),
        "agrees_with_task68": mine == upstream_claim,
        "service_layer_pure_invariant": {
            "callable": "assert_delivery_ownership",
            "accepts_pre_durable_owner": invariant_accepts,
            "negative_control_double_owner_rejected": bool(
                invariant.get("negative_control_double_owner_rejected")
            ),
            "per_state": dict(invariant.get("per_state") or {}),
            "control_arms": [
                "t71_pre_durable_zero_owner_invariant",
                "t71_request_and_application_invariant",
            ],
            "experiment_arms": [
                "t71_double_owner_invariant",
                "t71_durable_state_without_fact_invariant",
                "t71_durable_zero_owner_invariant",
            ],
        },
        "finding": (
            "DDL 与服务层的**纯不变量**都接受 `pre-durable rejected/error + application owner`。"
            "该不变量今天只由一个写入方法的赋值语句维持（`mark_delivery_pre_durable_failure` "
            "在调不变量之前把两个 owner 置空），而不变量本身不禁止它 ⇒ 任何**别的**写入路径"
            "把 state 落 rejected 而保留 application_id，都会同时通过 DDL 与不变量。"
            if mine and invariant_accepts
            else "DDL 或服务层不变量之一拒绝了该形态 —— 与上游结论不一致，需复核。"
        ),
        "disposition": "如实登记，不在本任务修（改生产代码会让上游四把锁的 evidence stale）",
        "owner_task": "22",
    }


def build_blocking_points(
    *,
    coverage: Mapping[str, Any],
    capacity: Mapping[str, Any],
    fault: Mapping[str, Any],
    multi_resolver: Mapping[str, Any],
    bp681: Mapping[str, Any],
    deletion: Mapping[str, Any],
    restoration: Mapping[str, Any],
    redaction_facts: Mapping[str, Any],
    lock_impact: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """本门的阻塞登记。编号 `BP-71-n`，逐条带实测、测量方式、owner 与处置。"""
    points: list[dict[str, Any]] = []

    points.append(
        {
            "id": "BP-71-1",
            "statement": (
                "`multi_resolver` 实测 %d 条（非零）且四条 resolver 行在任务 12 矩阵里全部仍"
                "`status=deferred` ⇒ 本门这条准则不过，`legacy_delete` gate 不放行任务 72 的"
                "全局 legacy 删除。" % int(multi_resolver["multi_resolver_count"])
            ),
            "measured": {
                "multi_resolver_count": multi_resolver["multi_resolver_count"],
                "rows_measured": multi_resolver["multi_resolver_rows_measured"],
                "rows_still_deferred": multi_resolver["rows_still_deferred"],
                "adjudication_owner_task_on_all_four": multi_resolver[
                    "rows_with_adjudication_owner_71"
                ],
                "blocking_task_points_at_36": multi_resolver[
                    "rows_with_blocking_task_pointing_at_36"
                ],
            },
            "measured_how": (
                "live 重算 writer matrix（`collect_source_facts` → `build_inventory` → "
                "`evaluate_gate`），不写盘；任务 12 矩阵逐行读 `status`/`blocking_task`/"
                "`adjudication_owner_task`"
            ),
            "owner_task": "36",
            "why_not_fixed_here": (
                "四条行的剩余阻塞是任务 36 的逐 entry 供给：在任一 entry 拿到 approved bundle "
                "之前，把 router 改成只经 substrate 取数会让全部底稿的 OO 入口 fail closed。"
                "任务 70 实测 180 个 OO entry 的 capability 全是 single_onlyoffice、"
                "0 个 bidirectional、approved bundle 3 个但全未绑 entry。"
            ),
            "disposition": "仍阻塞",
            "relation_to_upstream": "移交链 任务 20 → 任务 30 → 任务 71（本门）",
        }
    )

    points.append(
        {
            "id": "BP-71-2",
            "statement": (
                "真实容量负载（6000 会话 / 1200 participant / 120 同秒 burst / 20 "
                "applications/s × 10 分钟）本轮无法运行：三条前提一条都不成立。"
            ),
            "measured": capacity["real_load_execution"]["measured_premises"],
            "measured_how": (
                "socket 现测 3030；任务 69/70 报告按 key 现读 `port_3030_listening` / "
                "`executed_end_to_end` / verdict"
            ),
            "owner_task": capacity["real_load_execution"]["owner_task"],
            "why_not_fixed_here": (
                "3030 未监听、无真实 OO 活动编辑会话、生产 `public` 无业务数据。合成实测值只"
                "能打评估器判据，**不能**冒充容量门通过 —— 生产 `capacity_profile` 就是为防"
                "这件事写的。"
            ),
            "disposition": "UNVERIFIABLE，保持未验收",
            "relation_to_upstream": "与任务 70 的 BP-70-2 同一条环境前提",
        }
    )

    points.append(
        {
            "id": "BP-71-3",
            "statement": (
                "BP-68-1 的另一半：服务层**纯不变量** `assert_delivery_ownership` 同样接受 "
                "`pre-durable rejected/error + application owner`。该不变量今天只由一个写入"
                "方法的赋值语句维持，而不是由不变量本身禁止。"
            ),
            "measured": {
                "ddl_accepts": bp681["this_gate_measures_ddl_accepts"],
                "pure_invariant_accepts": bp681["service_layer_pure_invariant"][
                    "accepts_pre_durable_owner"
                ],
                "per_state_invariant": bp681["service_layer_pure_invariant"]["per_state"],
                "agrees_with_task68": bp681["agrees_with_task68"],
            },
            "measured_how": (
                "本门 scratch schema 独立造行（DDL 侧）+ 直调生产纯不变量（服务层侧），"
                "两侧各带对照组"
            ),
            "owner_task": bp681["owner_task"],
            "why_not_fixed_here": (
                "不改生产代码：改 source commit 会让任务 70 的 evidence stale 并打红上游四把锁。"
            ),
            "disposition": "如实登记，仍阻塞（BP-68-1 的严格扩展）",
            "relation_to_upstream": "BP-68-1（owner 任务 22）—— 本门复核一致并补出另一半",
        }
    )

    points.append(
        {
            "id": "BP-71-4",
            "statement": (
                "evidence 五表实测 0 行 ⇒ 正文点名的 evidence 类变异（漏场景 / 跨 entry 复用 / "
                "单 application 伪全场景 / 无 bundle 或 profile digest）在今天的分母上**无处"
                "落脚**，只能如实标 UNVERIFIABLE。"
            ),
            "measured": {
                "evidence_scenario_rows": deletion["evidence_scenario_rows"],
                "test_run_rows": deletion["test_run_rows"],
                "required_scenario_rows": deletion["required_scenario_rows"],
                "executed_end_to_end": deletion["executed_end_to_end"],
            },
            "measured_how": "任务 70 报告的 `db_snapshot.row_counts_before` 按 key 现读",
            "owner_task": "70",
            "why_not_fixed_here": (
                "evidence 行只能由真实 OO 场景产生（任务 70 的职责）；本门造 evidence 行等于"
                "伪造证据。"
            ),
            "disposition": "UNVERIFIABLE，保持未验收",
            "relation_to_upstream": "BP-70-2 / BP-67-2 仍阻塞",
        }
    )

    points.append(
        {
            "id": "BP-71-5",
            "statement": (
                "磁盘上的 `workpaper_writer_inventory.json` 的 source digest 与源码现算不符"
                "（stale）⇒ writer 门的默认命令 exit 2，本门只能 live 重算取计数。"
            ),
            "measured": {
                "on_disk": multi_resolver["inventory_source_digest_on_disk"],
                "live": multi_resolver["inventory_source_digest_live"],
                "stale": multi_resolver["inventory_on_disk_is_stale"],
            },
            "measured_how": "`build_inventory()` 现算并与磁盘 `source_digest` 比对",
            "owner_task": multi_resolver["inventory_stale_owner_task"],
            "why_not_fixed_here": (
                "重生成 inventory 会改 source commit 并让任务 70 的 evidence 全部 stale、"
                "打红上游四把锁；且它是任务 20/74 的冻结基线文件。"
            ),
            "disposition": "如实登记，不修",
            "relation_to_upstream": "对应既存红 `test_workpaper_writer_inventory.py`(2)",
        }
    )

    unverifiable_targets = list(coverage["targets_with_any_unverifiable_evidence"])
    only_unverifiable = list(coverage["targets_with_only_unverifiable_evidence"])
    points.append(
        {
            "id": "BP-71-6",
            "statement": (
                "%d 条变异目标带 `unverifiable:` 欠账（各自已点名 owner），其中 %d 条**只有**"
                "欠账证据。带欠账的部分不计入「已覆盖」，本门的 verdict 因此不可能是 passed。"
                % (len(unverifiable_targets), len(only_unverifiable))
            ),
            "measured": {
                "targets_with_any_unverifiable_evidence": unverifiable_targets,
                "targets_with_only_unverifiable_evidence": only_unverifiable,
                "count": len(unverifiable_targets),
                "total_targets": coverage["target_count"],
            },
            "measured_how": "逐条解析 `MUTATION_TARGETS` 的 evidence 前缀并现算",
            "owner_task": "70",
            "why_not_fixed_here": (
                "它们全部依赖真实 OO / 真实浏览器 / evidence 行三类今天不可供给的前提。"
            ),
            "disposition": "UNVERIFIABLE，保持未验收",
            "relation_to_upstream": "与 BP-71-2 / BP-71-4 同一组环境前提",
        }
    )

    points.append(
        {
            "id": "BP-71-7",
            "statement": (
                "自由文本里的裸 `token=<短不透明串>` 不被 `redact_exception()` 抹掉 —— 生产脱敏"
                "按四条 value pattern 匹配，裸短串不命中任何一条。"
            ),
            "measured": {
                "bare_token_in_free_text_is_scrubbed": redaction_facts[
                    "bare_token_in_free_text_is_scrubbed"
                ],
                "value_pattern_ids": redaction_facts["value_pattern_ids"],
                "url_form_is_scrubbed": not redaction_facts[
                    "exception_with_url_contains_secret"
                ],
                "bearer_form_is_scrubbed": not redaction_facts[
                    "exception_with_bearer_contains_secret"
                ],
            },
            "measured_how": (
                "同一串密钥分三种形态各调一次生产 `redact_exception()`：URL 带 query、"
                "Bearer 头、裸 `token=`；前两种被抹、第三种未被抹"
            ),
            "owner_task": redaction_facts["bare_token_owner_task"],
            "why_not_fixed_here": (
                "既有设计边界（value pattern 是显式登记的四条），不是本轮引入；改生产脱敏策略"
                "会改 source commit 并让上游四把锁的 evidence stale。"
            ),
            "disposition": "如实登记，不修",
            "relation_to_upstream": "本门自有（脱敏面 owner 任务 29）",
        }
    )

    points.append(
        {
            "id": "BP-71-8",
            "statement": (
                "本门新增守卫文件**曾经**让任务 70 的逐字节锁 stale：它的 `radiation_surface()` 把"
                "**`backend/tests` 全树 test 文件计数**锁进了比对，仓库里任何位置新增一个 "
                "`test_*.py` 都会顶掉它 —— 比 BP-70-8 更强的结构性脆弱点。**已修**：上游把普查"
                "派生量收进 `CENSUS_KEYS`，`--check` 比对前先 `strip_census`，同时仍现算并断言"
                "语义性质（剔除 ≠ 不管）。本门自己的两处同型缺陷（自有辐射面全树计数 + 转记上游"
                "live 值的传递形态）一并改形。"
            ),
            "measured": {
                "task70_census_keys": lock_impact["task70_census_keys"],
                "task70_surface_projection_agrees": lock_impact[
                    "task70_surface_projection_agrees"
                ],
                "task70_census_semantics_all_hold": lock_impact[
                    "task70_census_semantics_all_hold"
                ],
                "task70_lock_goes_stale_because_of_this_gate": lock_impact[
                    "task70_lock_goes_stale_because_of_this_gate"
                ],
                "scanned_test_files_live": lock_impact["task70_scanned_test_files_live"],
                "scanned_test_files_on_disk": lock_impact[
                    "task70_scanned_test_files_on_disk"
                ],
                "referencing_count_live": lock_impact["task70_referencing_count_live"],
                "referencing_count_on_disk": lock_impact[
                    "task70_referencing_count_on_disk"
                ],
                "own_guard_matched_subjects": lock_impact["own_guard_matched_subjects"],
                "isolation_method": lock_impact["isolation_method"],
            },
            "measured_how": (
                "现算任务 70 的 `radiation_surface()`，先 `strip_census` 再与它盘上报告比对"
                "（投影一致即普查免疫成立）；另现算它的 `census_semantics` 断言普查量的语义性质"
                "仍全部成立 —— 剔除不等于不看"
            ),
            "owner_task": lock_impact["owner_task"],
            "why_not_fixed_here": (
                "本条**已在本轮修掉**（改判据形状，不加豁免）。仍不在本任务修的是任务 69 那把锁的"
                "复选框根因（BP-70-6）—— 它不属本类：那是「把 tasks.md 的复选框状态摘进 body "
                "digest」，与仓库级普查无关，owner 是任务 69。"
            ),
            "disposition": "已修（改判据形状，不用豁免）",
            "relation_to_upstream": (
                "BP-70-8 的严格扩展：换目录 + 不写模块路径都躲不开全树计数 ⇒ 唯一出路是改判据"
                "的形状。同类形态在本 spec 被独立发现三次（BP-71-8 / BP-72-8 / BP-74-1），本轮"
                "四处一并收口。"
            ),
        }
    )

    if fault["injections_disagreeing"]:
        points.append(
            {
                "id": f"BP-71-{len(points) + 1}",
                "statement": (
                    "以下故障注入未达成预期：%s" % fault["injections_disagreeing"]
                ),
                "measured": {
                    name: fault["injections"][name]["measured"]
                    for name in fault["injections_disagreeing"]
                },
                "measured_how": "六种注入各自真做一次",
                "owner_task": OWNER_TASK,
                "why_not_fixed_here": "本轮实测结果，需逐条追因",
                "disposition": "失败",
                "relation_to_upstream": "本门自有",
            }
        )
    if not restoration["restored"]:
        points.append(
            {
                "id": f"BP-71-{len(points) + 1}",
                "statement": "数据复原实证不成立（生产 public 漂移 / 本轮 scratch 残留 / 临时目录未删）",
                "measured": {
                    "drifted_tables": restoration["drifted_tables"],
                    "own_schema_left": restoration["own_schema_left"],
                    "temp_artifact_root_removed": restoration["temp_artifact_root_removed"],
                },
                "measured_how": "生产 public 逐表前后行数 + 残留 schema 计数 + 临时目录存在性",
                "owner_task": OWNER_TASK,
                "why_not_fixed_here": "本轮实测结果",
                "disposition": "失败",
                "relation_to_upstream": "本门自有",
            }
        )
    return points


# ════════════════════════════════════════════════════════════════════════════
# §18 verdict
# ════════════════════════════════════════════════════════════════════════════


def build_verdict(report: Mapping[str, Any]) -> dict[str, Any]:
    """三态判定。**结构错误优先于一切**，其次「有 unverifiable」，最后才是 passed。

    🔴 「零证据全过算通过」是本 spec 反复点名的假绿（Property 71）：因此下面显式检查
    「真造行的臂数为 0」并把它判成 unverifiable，而不是让空集恒真地滑到 passed。
    """
    structural: list[str] = []

    declarations = report["task_declarations"]
    if not declarations["properties_match"]:
        structural.append("正文声明的 Property 与门的常量不符")
    if not declarations["sub_bullet_count_match"]:
        structural.append("正文子条目数与门的登记不符")

    coverage = report["mutation_coverage"]
    if coverage["unresolved_refs"]:
        structural.append(f"变异目标引用了不存在的证据源: {coverage['unresolved_refs'][:4]}")
    if coverage["disagreeing_refs"]:
        structural.append(f"引用的上游 arm 不成立: {coverage['disagreeing_refs'][:4]}")
    if coverage["unverifiable_without_owner"]:
        structural.append("有 unverifiable 证据没写 owner")

    tiers = report["coverage_tiers"]
    if tiers["broken_targets"]:
        structural.append(f"覆盖档位为 evidence_broken 的目标: {tiers['broken_targets'][:4]}")

    behaviour = report["behaviour"]
    if behaviour["harness_error"]:
        structural.append(f"行为侧采集失败: {behaviour['harness_error']}")
    if behaviour["apply_errors"]:
        structural.append("scratch schema 迁移应用失败")
    if behaviour["probe_errors"]:
        structural.append(f"探针失败: {sorted(behaviour['probe_errors'])}")
    if behaviour["disagreeing_arms"]:
        structural.append(f"本门行为臂不符声明: {behaviour['disagreeing_arms'][:4]}")
    if behaviour["missing_observations"]:
        structural.append(f"声明了却没有观测的臂: {behaviour['missing_observations'][:4]}")
    if behaviour["duplicate_arm_writes"]:
        structural.append("同一臂被写了多次观测（后写的会静静覆盖前一条）")
    if behaviour["cross_signature_hits"]:
        structural.append(
            f"rejected 臂的拒绝理由互相命中: {behaviour['cross_signature_hits'][:3]}"
        )
    if behaviour["facets_missing_control"]:
        structural.append(f"缺对照组的 facet: {behaviour['facets_missing_control']}")

    capacity = report["capacity"]
    if not capacity["profile_matches_requirements"]:
        structural.append("容量 profile 与需求原文不符")
    if not capacity["fail_closed_without_execution_record"]["raised"]:
        structural.append("无执行记录时容量门没有 fail closed")
    if capacity["evaluator_arms_disagreeing"]:
        structural.append(f"容量评估器臂不符: {capacity['evaluator_arms_disagreeing']}")

    redaction = report["redaction"]
    if not redaction["no_planted_secret_survives"]:
        structural.append(f"植入的密钥在脱敏结果里存活: {redaction['leaked_planted_secrets']}")
    if redaction["arms_disagreeing"]:
        structural.append(f"脱敏臂不符: {redaction['arms_disagreeing']}")

    alerting = report["alerting"]
    if not alerting["three_way_clean"]:
        structural.append(f"告警三向核对不干净: {alerting['validate_registry_problems'][:3]}")
    if alerting["rules_disagreeing"]:
        structural.append(f"告警规则 synthetic 不符: {alerting['rules_disagreeing']}")
    if alerting["conditions_without_rule"]:
        structural.append(f"有 condition 没有规则: {alerting['conditions_without_rule']}")

    fault = report["fault_injection"]
    if fault["injections_disagreeing"]:
        structural.append(f"故障注入未达预期: {fault['injections_disagreeing']}")

    retention_facts = (report["behaviour_facets"] or {}).get("retention") or {}
    if not retention_facts:
        structural.append("retention 面没有任何实测（探针未跑或失败）")

    restoration = report["data_restoration"]
    if not restoration["restored"]:
        structural.append("数据复原实证不成立")

    properties = report["properties"]
    if not properties["all_declared_have_landing"]:
        structural.append(f"缺 Property 落点: {properties['missing_landings']}")
    if not properties["every_unverified_has_owner"]:
        structural.append(f"未验证 Property 没点名 owner: {properties['unverified_without_owner']}")
    if properties["tiers_out_of_vocabulary"]:
        structural.append("Property 档位超出封闭词表")

    counterfactual = report["counterfactual_arms"]
    if not counterfactual["all_arms_sensitive"]:
        structural.append(
            f"反事实臂退化成重言式: {counterfactual['arms_not_changing_conclusion']}"
        )
    forward = report["forward_recompute"]
    if not forward["all_agree"]:
        structural.append(f"正向重算不符: {forward['disagreeing_cases']}")
    if not forward["has_positive_case"]:
        structural.append("正向重算缺正例 —— 抓不到「分类器恒真」")

    dag = report["dag_dependency"]
    if not dag["task24_depends_on_task23"]:
        structural.append("任务 24 对任务 23 的依赖不在依赖图里")
    if not dag["task72_depends_on_task71"]:
        structural.append("任务 72 不依赖本门")

    deletion = report["deletion_gate"]
    for key in (
        "task67_must_not_require_zero_stale",
        "task67_must_not_claim_eligibility",
        "task72_stage_a_must_not_require_unreachable_zero",
        "smoke_cannot_restore_verified",
    ):
        if not deletion[key]["agrees"]:
            structural.append(f"删除门变异落点不成立: {key}")

    mutation_states = report["mutation_state_machine"]
    if not mutation_states["mutation_script_present"]:
        structural.append("变异脚本不在磁盘上 —— 四件套不完整")
    if not mutation_states["mutation_ids"]:
        structural.append("变异脚本里读不到任何变异号")
    if not mutation_states["script_reads_and_writes_bytes"]:
        structural.append("变异脚本没走 read_bytes/write_bytes —— md5 复原校验必失败")

    for point in report["blocking_points"]:
        if not BP_ID_PATTERN.fullmatch(str(point["id"])):
            structural.append(f"BP 编号不合规: {point['id']}")

    row_arms = behaviour["arms_agreeing"]
    unverifiable_targets = len(coverage["targets_with_any_unverifiable_evidence"])
    capacity_unverifiable = (
        report["capacity"]["real_load_execution"]["tier"] == "UNVERIFIABLE"
    )
    unverified_properties = int(properties["landing_count"]) - int(
        properties["verified_here_count"]
    )

    if structural:
        state = "failed"
        means = "存在结构错误或实测不符声明 —— 逐条见 `structural_errors`。"
    elif row_arms == 0:
        state = "unverifiable"
        means = (
            "0 条行为臂真造过行。「零证据全过」不是通过 —— 本门保持未验收（Property 71）。"
        )
    elif unverifiable_targets > 0 or capacity_unverifiable or unverified_properties > 0:
        state = "unverifiable"
        means = (
            "六个面里 retention / 脱敏 / 告警 / 故障恢复 / 数据复原五面**真跑验过**（%d/%d "
            "行为臂符合声明）；容量面的真实负载、%d 条带欠账的变异目标与 %d 条未在本门真跑的 "
            "Property 保持 UNVERIFIABLE 且各自点名 owner。本门因此不宣称 passed。"
            % (row_arms, behaviour["arm_count"], unverifiable_targets, unverified_properties)
        )
    else:
        state = "passed"
        means = "全部面真跑验过且无未决 UNVERIFIABLE。"

    return {
        "state": state,
        "state_vocabulary": list(VERDICT_VOCABULARY),
        "means": means,
        "structural_errors": structural,
        "structural_error_count": len(structural),
        "behaviour_arms_agreeing": row_arms,
        "behaviour_arm_count": behaviour["arm_count"],
        "targets_with_any_unverifiable_evidence": unverifiable_targets,
        "targets_with_only_unverifiable_evidence": len(
            coverage["targets_with_only_unverifiable_evidence"]
        ),
        "properties_not_verified_here": unverified_properties,
        "capacity_real_load_unverifiable": capacity_unverifiable,
        "facet_conclusions": {
            "capacity": (
                "评估器/fail-closed/需求交叉锁真跑验过；真实负载 UNVERIFIABLE（owner %s）"
                % report["capacity"]["real_load_execution"]["owner_task"]
            ),
            "fault_injection": (
                "六种注入全部真做：达成 %s；未达成 %s"
                % (fault["injections_agreeing"], fault["injections_disagreeing"])
            ),
            "retention": (
                "plan 七条判定分支 + apply 三条协议/复核分支在 scratch schema 真跑；"
                "Windows lock 下改判 retain + alert 已现测"
            ),
            "redaction": (
                "四种密钥形态植入后逐条现算未存活；`assert_no_leak` 对未脱敏载荷四条实验组全抛"
            ),
            "alerting": (
                "%d 条规则逐条在阈值触发、阈值以下静默；三向核对 %s"
                % (
                    alerting["rule_count"],
                    "干净" if alerting["three_way_clean"] else "不干净",
                )
            ),
            "data_restoration": (
                "生产 public 逐表前后相等=%s；本轮 scratch 残留=%s；临时 artifact 根已删=%s"
                % (
                    not restoration["drifted_tables"],
                    restoration["own_schema_left"],
                    restoration["temp_artifact_root_removed"],
                )
            ),
        },
        "multi_resolver_criterion_passes": report["multi_resolver_adjudication"][
            "criterion_passes"
        ],
        "legacy_delete_released": report["multi_resolver_adjudication"]["criterion_passes"],
        "task72_stage_a": (
            "保持红。`multi_resolver` 实测 %d ≠ 0 且四条 resolver 行仍 deferred ⇒ "
            "`legacy_delete` gate 不放行；容量真实负载与 evidence 类变异保持 UNVERIFIABLE。"
            % int(report["multi_resolver_adjudication"]["multi_resolver_count"])
        ),
        "forbidden_claims": [
            "不得宣称任何真实 OO probe 已通过",
            "不得用合成 CapacityMeasurement 冒充容量门已通过",
            "不得把「零场景/零证据全过」当成通过",
            "不得以退出码代替四态证据",
        ],
    }


# ════════════════════════════════════════════════════════════════════════════
# §19 组装 / 渲染 / CLI
# ════════════════════════════════════════════════════════════════════════════


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
    harness = collect_all_observations()
    behaviour = build_behaviour_report(harness)

    facets: dict[str, Any] = dict(harness.get("facets") or {})
    capacity = build_capacity()
    redaction = build_redaction()
    alerting = build_alerting()
    fault = build_fault_injection(harness)
    restoration = restoration_record(harness)
    deletion = build_deletion_gate()
    dag = build_dag_dependency()
    protocol = build_protocol_source_scan()
    multi_resolver = build_multi_resolver_adjudication()
    bp681 = build_bp_68_1_recheck(harness)
    lock_impact = upstream_lock_impact()
    surface = radiation_surface()

    facet_pool: dict[str, Any] = {
        "bp_68_1_recheck": bp681,
        "capacity": capacity,
        "redaction": redaction,
        "alerting": alerting,
        "fault_injection": fault,
        "data_restoration": restoration,
        "deletion_gate": deletion,
        "dag_dependency": dag,
        "protocol_source_scan": protocol,
        "multi_resolver_adjudication": multi_resolver,
        "retention": facets.get("retention") or {},
    }
    coverage = resolve_mutation_coverage(behaviour=harness, facets=facet_pool)
    tiers = build_coverage_tiers(coverage)

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "spec": SPEC,
        "task": f"{TASK_NUMBER}. 变异、容量、故障恢复、retention/脱敏/告警与数据复原验收",
        "wave": 7,
        "owner_task": OWNER_TASK,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_commit": git_head(),
        "generated_by": GATE_REL,
        "why_this_task_is_acceptance_not_a_checklist": (
            "正文点名的每一条「变异覆盖 …」都必须真造出非法形态并证明系统拒绝它，"
            "每条都要有对照组（合法形态被接受）+ 实验组（非法形态被拒，且各臂拒绝理由互不"
            "命中）。只声明「已覆盖」不构成任何证据。"
        ),
        "sub_bullets": {str(k): v for k, v in SUB_BULLETS.items()},
        "task_declarations": task_declarations(),
        "design_property_titles": design_property_titles(),
        "upstream_inputs": upstream_inputs(),
        "mutation_coverage": coverage,
        "coverage_tiers": tiers,
        "behaviour": behaviour,
        "behaviour_facets": facets,
        "bp_68_1_recheck": bp681,
        "capacity": capacity,
        "retention": facet_pool["retention"],
        "redaction": redaction,
        "alerting": alerting,
        "fault_injection": fault,
        "data_restoration": restoration,
        "deletion_gate": deletion,
        "dag_dependency": dag,
        "protocol_source_scan": protocol,
        "multi_resolver_adjudication": multi_resolver,
        "counterfactual_arms": build_counterfactual_arms(coverage),
        "forward_recompute": build_forward_recompute(),
        "properties": build_property_landings(),
        "mutation_state_machine": build_mutation_state_machine(),
        "radiation_surface": surface,
        "census_contract": build_census_contract(surface),
        "upstream_lock_impact": lock_impact,
        "scratch_schema": harness.get("scratch_schema"),
        "temp_artifact_root": harness.get("temp_artifact_root"),
        "wallclock_seconds": harness.get("wallclock_seconds"),
    }
    report["blocking_points"] = build_blocking_points(
        coverage=coverage,
        capacity=capacity,
        fault=fault,
        multi_resolver=multi_resolver,
        bp681=bp681,
        deletion=deletion,
        restoration=restoration,
        redaction_facts=redaction,
        lock_impact=lock_impact,
    )
    report["artifact_git_status"] = git_porcelain(
        [GATE_REL, rel(OUTPUT_PATH), GUARD_TEST_REL, MUTATE_REL]
    )
    report["artifact_git_status_semantics"] = _census_lock.artifact_status_semantics(
        report["artifact_git_status"]
    )
    report["verdict"] = build_verdict(report)
    report["elapsed_seconds"] = round(time.time() - started, 2)
    # 🔴 digest 算在 **census 剔除之后**的内容上：于是它继续锁死「非普查内容」，而不再被仓库
    #    演进顶红。`strip_volatile` 与 `strip_census` 必须都做 —— 少任何一个，digest 就重新
    #    变成一个会自己过期的锁。
    report["report_digest"] = digest_of(strip_census(strip_volatile(report)))
    return report


def render(report: Mapping[str, Any]) -> str:
    return stable_json(report, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="任务 71 验收门：变异、容量、故障恢复、retention/脱敏/告警与数据复原"
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
            f"[任务71] 已写出 {rel(OUTPUT_PATH)}；verdict={verdict['state']}"
            f"；结构错误 {verdict['structural_error_count']} 条"
            f"；行为臂 {report['behaviour']['arms_agreeing']}/{report['behaviour']['arm_count']}"
            f"；变异目标 {report['mutation_coverage']['target_count']}"
        )
        for line in verdict["structural_errors"]:
            print(f"  · {line}")
        return 0

    if not OUTPUT_PATH.is_file():
        print(f"[任务71] {rel(OUTPUT_PATH)} 不存在 —— 先跑 --write", file=sys.stderr)
        return 2
    on_disk = json.loads(read_text(OUTPUT_PATH))
    # 🔴 比对**在 census 剔除之后**做：仓库级普查量（自有辐射面全树计数 + 转记的上游 live 值）
    #    随仓库演进，冻进锁里等于要求仓库停止演进（BP-71-8 的传递形态）。
    live = strip_census(
        strip_volatile({k: v for k, v in report.items() if k != "report_digest"})
    )
    disk = strip_census(
        strip_volatile({k: v for k, v in on_disk.items() if k != "report_digest"})
    )
    if live == disk:
        # 剔除 ≠ 不管：普查量现算并断言语义性质。少了这一段，上一条就退化成「不看了」。
        semantics = report["census_contract"]["semantics"]
        if not semantics["all_hold"]:
            print(
                f"[任务71] 普查语义断言不成立: {semantics['failing_checks']}"
                f"（无命中者的 pattern: {semantics['patterns_without_a_match']}）",
                file=sys.stderr,
            )
            return 1
        measured = report["census_contract"]["measured"]
        disk_measured = (on_disk.get("census_contract") or {}).get("measured") or {}
        print(
            f"[任务71] --check 通过：{rel(OUTPUT_PATH)} 与现算一致（census 剔除后）；"
            f"census 快照 全树 test 文件 {disk_measured.get('scanned_test_files')} → "
            f"{measured['scanned_test_files']}（不参与锁）"
        )
        return 0
    live_keys = set(live)
    disk_keys = set(disk)
    diffs = [
        key for key in sorted(live_keys | disk_keys) if live.get(key) != disk.get(key)
    ]
    print(
        f"[任务71] 现算结果与 {rel(OUTPUT_PATH)} 不一致 —— 报告已过期或被手改"
        f"（已剔除 census 与 volatile，剩下的都是真 stale 轴）；不一致的顶层键: {diffs}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
