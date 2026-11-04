"""test_workpaper_sync_program_milestones —— 判据层（路径常量、核心 spec 的独立现算口径、点名名单）。

从 `backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py` 拆出：HEAD 上该文件已
857 行（白名单基线 803 + 5% = 843 早已超出），2026-11-04 再把 BLOCKED / 诊断两条计数上限改成
逐条点名后到 1051 行。这里只放**不含断言**的解析层与 `source` 的构建函数；fixture 本身与
全部用例、断言留在原文件（从别的模块导入的 fixture 只被 pytest 按参数名注入，ruff 判 F811），
生成器 AST / 变异锚点仍在原文件可见（白名单那条注释要求的同文件可见性指的是这一层）。

刻意与用例文件**同目录**：`Path(__file__).parents[3]` 的路径推算移到子目录会整体错一层。
搬过来的定义逐行等于原文；用例层的 import 清单由拆分脚本按实际引用算出。
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


_REPO = Path(__file__).resolve().parents[3]


_GENERATOR_PATH = (
    _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_sync_program_milestones.py"
)


_DEFINITIONS_PATH = (
    _REPO / "backend" / "data" / "workpaper_sync_program_milestone_definitions.json"
)


_REGISTRY_PATH = _REPO / "backend" / "data" / "workpaper_sync_program_milestones.json"


_WRITER_GATE_PATH = (
    _REPO / "backend" / "scripts" / "check" / "check_workpaper_writer_revision_gate.py"
)


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_CORE = "workpaper-html-onlyoffice-bidirectional-writeback-closure"


_CORE_TASKS_REL = f".kiro/specs/{_CORE}/tasks.md"


_CORE_ACTIVE_TASKS = _REPO / _CORE_TASKS_REL


_INDEPENDENT_TASK_RE = re.compile(
    r"^\s*-\s*\[([ xX~\-])\]\*?\s+([0-9]+(?:\.[0-9]+)*)(?:\.\s+|\s+)\S"
)


_STATE_NAMES = {"x": "completed", "~": "partial", "-": "blocked", " ": "pending"}


def _independent_task_states(path: Path) -> dict[str, str]:
    states: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _INDEPENDENT_TASK_RE.match(line)
        if match:
            assert match.group(2) not in states, f"{path}: 任务号 {match.group(2)} 重复"
            states[match.group(2)] = match.group(1).lower()
    assert states, f"{path}: 一个任务行都没解析出来 ⇒ 口径失锚"
    return states


def _independent_state_counts(states: dict[str, str]) -> dict[str, int]:
    counts = {name: 0 for name in _STATE_NAMES.values()}
    for value in states.values():
        counts[_STATE_NAMES[value]] += 1
    return counts


def _independent_graph(path: Path) -> dict[str, Any]:
    after_heading = path.read_text(encoding="utf-8").split("## Task Dependency Graph", 1)[1]
    return json.loads(after_heading.split("```json", 1)[1].split("```", 1)[0])


def _task_order(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _program_evidence(rel: str) -> Path:
    """G0-x 执行卡在 Wave 6 程序的 evidence 目录里，按 evidence 文件本身定位。

    🔴 原写法硬拼 active 目录：spec 归档（2026-10-03）后又重建了 active 目录（2026-11-01），
       active 下没有这些 evidence ⇒ 两条判据恒 FileNotFoundError —— 报的是「文件不存在」，
       实际是「读错了地方」。active 有就用 active，否则取归档快照（与 0.6 重绑旧消费方同一实现）。
    """
    from app.core.spec_docs import resolve_spec_dir

    path = resolve_spec_dir(_CORE, require_files=(f"evidence/{rel}",)) / "evidence" / rel
    assert path.is_file(), f"evidence/{rel} 在 active 与归档快照里都不存在"
    return path


def build_source() -> dict[str, Any]:
    """用例文件 module 级 fixture `source` 的取值：生成器、定义、现算 registry、落盘 registry 与 spec 事实。"""
    generator = _load_module("workpaper_sync_program_milestone_generator_test", _GENERATOR_PATH)
    definitions = generator.load_definitions()
    registry = generator.build_program_registry()
    on_disk = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    spec_inputs: dict[str, str] = {}
    spec_facts = generator.collect_spec_facts(definitions, spec_inputs)
    return {
        "generator": generator,
        "definitions": definitions,
        "registry": registry,
        "on_disk": on_disk,
        "spec_facts": spec_facts,
    }


# ── 核心 spec 的独立现算口径 ────────────────────────────────────────────────
#
# 🔴 2026-11-03：核心 spec 在 2026-11-01 被**重写**成两级任务号（0.1 … 7.5，20 个 wave），
#    Wave 6 的 77 个整数任务已随 2026-10-03 归档成冻结快照。用例文件原先把 Wave 6 的形态
#    写成字面量（77 / 263 / 9 个 wave / 任务 72·74），重写后 6 条判据恒红，而生成器早已
#    改读新任务图 —— 判据守的是一份已不存在的文档。上面的 `_independent_*` 改成**独立现算**：
#    与生成器同语义、不同对象（不复用生成器的正则：生成器读错时两边一起错、守卫照绿）。


# ── BLOCKED / 诊断逐条点名 ──────────────────────────────────────────────────
#
# 🔴 阻塞原先是计数上限（2026-09-28 由 3 校准到 5）。计数上限挡不住「清掉一条、冒出另一条」
#    的互换，而且把对错交给了上限取值：2026-11-03 writer 清册补齐重生成后
#    `SYNC-MULTI-RESOLVER` 由 STALE 回到 BLOCKED（multi_resolver 4 条，属实 —— 先前的 STALE
#    是清册过期造成的假象），上限 5 立刻报「阻塞变多」，可这次「变多」是**更诚实**：要么照抄
#    实测值 6 让上限失去意义，要么误报。改成名单：每条 BLOCKED 写明是哪些 reason_code 在阻塞它。
#      · 新冒出的阻塞（名单外的 milestone，或名单内出现新原因）⇒ 红，先查来源再登记；
#      · 阻塞解除 ⇒ 红，提示把它从名单删掉（只许删：留着失效条目，它日后重新阻塞时
#        就不会被发现）。
KNOWN_BLOCKED: dict[str, frozenset[str]] = {
    "ROW-MUTATION-READY": frozenset({"producer_tasks_incomplete"}),
    "SYNC-DURABLE-APPLICATION": frozenset(
        {"producer_tasks_incomplete", "durable_callback_application_evidence_missing"}
    ),
    "SYNC-MULTI-RESOLVER": frozenset(
        {"producer_tasks_incomplete", "writer_gate_multi_resolver_nonzero"}
    ),
    "SYNC-UNIFIED-ROOM": frozenset(
        {"producer_tasks_incomplete", "real_room_forcesave_close_evidence_missing"}
    ),
    "TEMPLATE-OVERRIDE-CHANGED": frozenset(
        {"producer_tasks_missing", "producer_contract_missing"}
    ),
    "X-RUNTIME-EVIDENCE": frozenset(
        {"producer_tasks_incomplete", "evidence_partial_or_blocked"}
    ),
}


# 诊断同样逐条点名（原先先是 `== 5`、后改 `<= 5`：前者惩罚进展，后者挡不住互换）。
# 2026-11-03 现算 5 条 = 4 条 natural_language_producer_placeholder + 1 条
# producer_tasks_missing（重写后冒出的那条指向任务 72 的幻影 blocker 已随守卫改造消失）。
KNOWN_DIAGNOSTICS: frozenset[tuple[str, str]] = frozenset(
    {
        ("natural_language_producer_placeholder", "SYNC-DURABLE-APPLICATION"),
        ("natural_language_producer_placeholder", "SYNC-ENTRY-NAMESPACE"),
        ("natural_language_producer_placeholder", "SYNC-MULTI-RESOLVER"),
        ("natural_language_producer_placeholder", "SYNC-UNIFIED-ROOM"),
        ("producer_tasks_missing", "TEMPLATE-OVERRIDE-CHANGED"),
    }
)


def blocked_reason_codes(registry: dict[str, Any]) -> dict[str, frozenset[str]]:
    """registry 里每条 BLOCKED milestone → 阻塞它的 reason_code 集合。"""
    return {
        item["id"]: frozenset(blocker["reason_code"] for blocker in item["blockers"])
        for item in registry["milestones"]
        if item["state"] == "BLOCKED"
    }


def named_set_drift(
    actual: dict[str, frozenset[str]], known: dict[str, frozenset[str]]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """返回（名单外新冒出的原因，名单内已解除的原因），都按 milestone 分组、组内排序。"""
    unexplained = {
        milestone: sorted(reasons - known.get(milestone, frozenset()))
        for milestone, reasons in actual.items()
        if reasons - known.get(milestone, frozenset())
    }
    cleared = {
        milestone: sorted(reasons - actual.get(milestone, frozenset()))
        for milestone, reasons in known.items()
        if reasons - actual.get(milestone, frozenset())
    }
    return unexplained, cleared
