"""Task 69 前端状态机 / recovery / descriptor / 宿主与 DOM **独立回归门**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7 Task 69

═══ 本任务为什么必须是独立的 ═══

正文逐字：「不得由实现任务自证」，且「判据不以 import/字符串存在」。所以：

* **行为判据全在浏览器语义里跑** —— `audit-platform/frontend/src/components/workpaper/
  sync/__tests__/task69IndependentRegression.spec.ts` 是本门自己写的独立文件，真实
  `mount()` 宿主、真实 DocEditor 构造、真实 network 调用序列。它不 import 任何实现任务的
  `__tests__` 夹具。
* **本门自己再算一遍** —— 上面那份 spec 把真实观测带（network / DocEditor / emit / DOM
  的统一时间轴）导出成 JSON，本门用 Python **重新实现同一套顺序判据**在它上面现算。
  两次独立计算得出同一结论才算过（教训 17：只读磁盘产物的判据对实现侧改动天生不敏感）。
* **反事实多臂 + 正向重算都做** —— 每条结论的前提逐一在内存里移除（结论不变 ⇒ 该判据
  度量的是别的东西），再对**合成的已知答案**正向重算一次（教训 15：反事实只能证非重言，
  抓不到恒真）。

═══ 三个内容子条目的落点 ═══

| 子条目 | 报告字段 |
|---|---|
| 1 状态机 / 挂载 / 状态条 / 面板 / localStorage / 事件 / 双基线 / shell 收敛 / requested-canonical / refresh-required / close 仲裁 | `invariants[sub_bullet=1]` |
| 2 显式 scope / recovery list room+generation / opaque versionId / 不泄露 / 三实体 | `invariants[sub_bullet=2]` |
| 3 DOM/network 顺序 + 五条立即失败 | `invariants[sub_bullet=3]` + `immediate_failures` + `dom_network_order` |

═══ 本门不做什么 ═══

* **不改任何生产代码**。发现缺陷如实登记成 `BP-69-n`，不顺手修（会改 source commit 让
  Task 70 的 evidence stale）。
* **不运行真实 OnlyOffice / 真浏览器**。前端侧只跑 vitest + jsdom；真浏览器联合时序归
  Task 70。`oo_scope_boundary` 显式记录这条边界。
* **不宣称生产宿主链路已验**。替代面 19/22 从生产文件不可达（本门独立复算），因此
  「组件级独立挂载已验」与「生产宿主链路已验」在报告里是两个不同档位。

═══ 用法（仓库根；PATH 上的 `python` 指向坏掉的解释器）═══

    .\\.venv\\Scripts\\python.exe backend/scripts/check/check_task69_frontend_independent_regression.py --check
    .\\.venv\\Scripts\\python.exe backend/scripts/check/check_task69_frontend_independent_regression.py --write
    ... --write --run-vitest      # 真跑辐射面 vitest（分钟级）并把真实执行结果写进报告

`--check` / `--write` 互斥且必选。`--check` 现算全部结论并与磁盘逐字节比对；
`vitest_run` 块是**昂贵的真实执行记录**，`--check` 从磁盘复用，但辐射面清单、legacy 键
分母、可达性、顺序判据、反事实臂与正向重算每次都现算，改 scanner 蒙不过去。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Final, Mapping, Sequence

# ════════════════════════════════════════════════════════════════════════════
# §0 常量与路径
# ════════════════════════════════════════════════════════════════════════════

SCHEMA_VERSION: Final[str] = "task69-frontend-independent-regression:v1"
OWNER_TASK: Final[str] = "69"
TASK_NUMBER: Final[int] = 69
SPEC: Final[str] = "workpaper-html-onlyoffice-bidirectional-writeback-closure"

REPO: Final[Path] = Path(__file__).resolve().parents[3]
BACKEND: Final[Path] = REPO / "backend"
DATA: Final[Path] = BACKEND / "data"
FRONTEND: Final[Path] = REPO / "audit-platform" / "frontend"
FE_SRC: Final[Path] = FRONTEND / "src"
SYNC_DIR: Final[Path] = FE_SRC / "components" / "workpaper" / "sync"
SYNC_TESTS: Final[Path] = SYNC_DIR / "__tests__"

OUTPUT_PATH: Final[Path] = DATA / "workpaper_sync_task69_frontend_regression.json"
UPSTREAM_STRUCTURAL_PATH: Final[Path] = DATA / "workpaper_sync_task67_structural_pre_reconcile.json"
UPSTREAM_DELETION_PLAN_PATH: Final[Path] = DATA / "workpaper_sync_task66_legacy_deletion_plan.json"
UPSTREAM_BACKEND_REGRESSION_PATH: Final[Path] = DATA / "workpaper_sync_task68_backend_chain_regression.json"

SPEC_DIR: Final[Path] = REPO / ".kiro" / "specs" / SPEC
TASKS_MD: Final[Path] = SPEC_DIR / "tasks.md"
DESIGN_MD: Final[Path] = SPEC_DIR / "design.md"

#: 本门自己的独立回归判据面（相对仓库根）。
GUARD_SPEC_REL: Final[str] = (
    "audit-platform/frontend/src/components/workpaper/sync/__tests__/"
    "task69IndependentRegression.spec.ts"
)

#: 本门的后端守卫。
#:
#: 🔴 **刻意不放在** `backend/tests/workpaper_sync/`：上游后端独立回归把「该目录内不引用被验
#: 生产单元的测试文件」这份**目录普查**（`in_dir_but_out_of_surface`）冻结进了自己的逐字节锁，
#: 往那个目录新增任何一个这类文件都会让它变长并打红 1~3 条上游守卫。本轮实测过完整因果链：
#: 放在该目录且带包路径字面量 ⇒ 上游 3 红；去掉字面量 ⇒ 2 条转绿、剩 1 条（纯目录成员）；
#: 移出该目录 ⇒ 全绿。见 BP-69-6（owner 68/72：Tasks 70/71/72 还要往那儿加测试文件）。
GUARD_TEST_REL: Final[str] = (
    "backend/tests/workpaper_sync_frontend/test_task69_frontend_regression.py"
)

#: 上游把普查冻结进逐字节锁的那个目录。本门守卫必须**不在**它下面（现算判据，不是注释）。
UPSTREAM_CENSUS_DIR: Final[str] = "backend/tests/workpaper_sync/"

#: 模式键真源（迁移正则从这里现读，不在本门抄第二份）。
MODE_STORAGE_REL: Final[str] = (
    "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncModeStorage.ts"
)
BRIDGE_MACHINE_REL: Final[str] = (
    "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncBridgeMachine.ts"
)

RESULT_PASSED: Final[str] = "passed"
RESULT_FAILED: Final[str] = "failed"
RESULT_UNVERIFIABLE: Final[str] = "unverifiable"

#: 正文声明的 11 条 Property。守卫与它双向锁死（多一条少一条都报结构错误）。
DECLARED_PROPERTIES: Final[tuple[int, ...]] = (8, 11, 12, 13, 14, 15, 35, 46, 47, 48, 58)

#: 正文四个子条目（第 4 条是 Property 行本身）。
SUB_BULLETS: Final[dict[int, str]] = {
    1: "bridge PBT、editor mounted、状态条、冲突/recovery panel、localStorage、event refresh、"
       "server/client 双基线、normal accepted pre-correlation shell→primary bound 或 terminal "
       "duplicate、requested/canonical operation 授权跟随、refresh-required reopen 与真实宿主 API "
       "顺序；另独立挂载验证 leader promotion 前 revoke/expire 先显示 close_authorization_stale、"
       "合法 successor 接任后继续同一 generation、无 successor 时进入 close_recovery_required 并"
       "停止 loading/禁止成功文案",
    2: "独立断言所有请求显式携带 project/wp/entry，recovery list 另带 room/generation、rollback "
       "API/DTO 使用 opaque versionId 并保留 entry scope、numeric revision 不得拼 route；"
       "scope/404/403 失败不泄露对象；browser crash 进入 recovery_pending 且 claim 前三实体均空；"
       "claim 仅成功后同时关联三者；错误 prior confirmation/bundle/fence/contributor 仍保持三者为 0；"
       "download-only 三者为 0 且不显示回写成功；普通 retry 拒绝空 operation",
    3: "DOM/network 顺序覆盖 descriptor mount→ready→confirm 与 recovery list/claim/download-only；"
       "判据不以 import/字符串存在，不存在 prop/expose、editor 自行取 config、normal shell 提前伪 "
       "application、claim 前伪三实体或 fail-open 文案立即失败",
    4: "独立验证 Property 8/11/12/13/14/15/35/46/47/48/58",
}

#: 正文第 3 子条目逐字列出的五条「立即失败」。每条各有独立打红判据。
IMMEDIATE_FAILURE_IDS: Final[tuple[str, ...]] = (
    "nonexistent_prop_or_expose",
    "editor_fetches_its_own_config",
    "normal_shell_fakes_application_early",
    "three_entities_faked_before_claim",
    "fail_open_success_text",
)

#: 既存红的归因。**不修**（不属本任务；改生产代码会让 Task 70 尚未刷新的 evidence stale）。
#:
#: 前端侧逐条 nodeid 由 `frontend_baseline.failures` **现算记录**（数百条，不手抄）；这里只登记
#: 归因与 owner，以及「本门没有把它们弄红」的证据。后端侧本门未改任何生产代码，按引用关系反查
#: 的辐射面只有上游两份报告的逐字节锁 + 本门自己的守卫，故 spec 基线里那批既存红都在辐射面外。
PREEXISTING_RED_ATTRIBUTION: Final[dict[str, Any]] = {
    "frontend": {
        "where": "frontend_baseline.failures（逐条 suite + 测试名，现算记录）",
        "attribution": "并发多会话在途的存量红：本门只新增一个判据面文件，未改任何前端生产代码。",
        "evidence_that_this_gate_did_not_cause_them": [
            "本门判据面自身在全套里 0 红（门的判定对此有独立 blocker）",
            "按引用关系现算的辐射面 18 个 spec 文件全绿",
            "production_code_touched.frontend_production_files 为空",
        ],
        "owner_task": "各自功能方 / 最终由 Task 72 Stage D 的五个零门收口",
        "why_not_fixed_here": "正文未授权改生产代码；且 `components/workpaper/` 下的宿主面是并发"
                              "在途禁碰面。",
    },
    "backend": {
        "where": "本门辐射面之外",
        "attribution": "本门未改任何后端生产代码/迁移，按引用关系反查的后端辐射面只有"
                       "上游两份报告的逐字节锁与本门自己的守卫，三者本轮全绿。",
        "owner_task": "20 / 70 / 28 / 30（见上游后端独立回归的既存红登记）",
        "why_not_fixed_here": "同上；另外那批红大多要等真实 OO evidence 刷新（Task 70）。",
    },
}

#: 本门不做真实 OO / 真浏览器的边界（Task 70 的地盘）。
OO_SCOPE_BOUNDARY: Final[dict[str, Any]] = {
    "runs_real_onlyoffice": False,
    "runs_real_browser": False,
    "test_environment": "vitest 3 + jsdom（vitest.config.ts 的 environment=jsdom）",
    "why": "正文第 3 子条目要求 DOM/network 顺序判据，不要求真浏览器；真实 OO 9.4 全 entry "
           "required scenario 刷新由 Task 70 负责。本门不刷新任何 evidence、不宣称任何 probe 通过。",
    "port_3030_listening": False,
}


class Task69GateError(RuntimeError):
    """本门自己的结构错误（与被判据对象的失败区分开）。"""


# ════════════════════════════════════════════════════════════════════════════
# §1 基础工具
# ════════════════════════════════════════════════════════════════════════════


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json(payload: Any, indent: int | None = None) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=indent)


def digest_of(payload: Any) -> str:
    return sha256_text(stable_json(payload))


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return (out.stdout or "").strip() or "unknown"
    except Exception:  # noqa: BLE001 - 无 git 时不该让门崩
        return "unknown"


def git_porcelain(paths: Sequence[str]) -> dict[str, str]:
    """逐个产物的 `git status --porcelain`（不加 rtk —— 压缩会漏整目录 `??`）。"""
    out: dict[str, str] = {}
    for path in paths:
        if not (REPO / path).exists():
            # 🔴 `git status --porcelain -- <不存在的路径>` 输出为空，与「已跟踪且干净」
            # 逐字节相同。不先查存在性，缺产物会被登记成「已入库」——最贵的一种假绿。
            out[path] = "missing"
            continue
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain", "--", path],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                timeout=30,
            )
            lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
            out[path] = lines[0][:2].strip() if lines else "tracked_clean"
        except Exception as exc:  # noqa: BLE001
            out[path] = f"unknown:{type(exc).__name__}"
    return out


# ════════════════════════════════════════════════════════════════════════════
# §2 正文声明（tasks.md 现读，双向锁死）
# ════════════════════════════════════════════════════════════════════════════


def task_body(task_number: int = TASK_NUMBER) -> str:
    """现读 tasks.md 里本任务的正文（含任意复选框状态）。"""
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
        raise Task69GateError(f"tasks.md 里找不到任务 {task_number}")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.match(r"^\s*-\s\[[ x~\-]\]\s+\d+\.", lines[index])
            or lines[index].startswith("### ")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def task_declarations() -> dict[str, Any]:
    body = task_body()
    properties = sorted({int(m) for m in re.findall(r"Property (\d+)", body)})
    req_line = next((line for line in body.split("\n") if "_Requirements:" in line), "")
    requirements = re.findall(r"\d+\.\d+", req_line)
    # `_Requirements:` 行也是一条 `  - ` 缩进 bullet，但它不是子条目 —— 单独排除，
    # 否则「子条目数」这条判据会永远差 1（而差 1 是最容易被当成「写错常量」糊过去的形态）。
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
    }


def design_property_titles() -> dict[str, str]:
    """design.md 里本任务 11 条 Property 的标题（正文可能与标题同行）。"""
    text = read_text(DESIGN_MD)
    titles: dict[str, str] = {}
    for match in re.finditer(r"### Property (\d+)[ \t:.、]*([^\n]*)\n([^\n]*)", text):
        number = int(match.group(1))
        if number not in DECLARED_PROPERTIES:
            continue
        inline = match.group(2).strip()
        following = match.group(3).strip()
        titles[str(number)] = (inline or following)[:220]
    return titles


# ════════════════════════════════════════════════════════════════════════════
# §3 现算 ①：替代面可达性（独立复算，不读上游的答案）
# ════════════════════════════════════════════════════════════════════════════

_IMPORT_RE = re.compile(r"""(?:from|import)\s+['"]([^'"]+)['"]""")


def _resolve_import(spec: str, origin: Path) -> Path | None:
    if spec.startswith("@/"):
        base = FE_SRC / spec[2:]
    elif spec.startswith("."):
        base = (origin.parent / spec).resolve()
    else:
        return None
    for candidate in (base, base.with_suffix(".ts"), base.with_suffix(".vue"), base / "index.ts"):
        if candidate.is_file():
            return candidate
    return None


def _frontend_sources() -> list[Path]:
    return [
        path
        for path in sorted(FE_SRC.rglob("*"))
        if path.is_file() and path.suffix in {".ts", ".vue"}
    ]


@dataclass
class ImportGraph:
    """`importer -> 被 import 的替代面模块` 的现算结果。"""

    surface: list[str]
    edges: dict[str, list[str]] = field(default_factory=dict)
    scanned_files: int = 0

    def importers_of(self, module_rel: str) -> list[str]:
        return sorted(
            importer for importer, targets in self.edges.items() if module_rel in targets
        )


def build_import_graph() -> ImportGraph:
    surface = [
        rel(path)
        for path in sorted(SYNC_DIR.iterdir())
        if path.is_file() and path.suffix in {".ts", ".vue"}
    ]
    surface_set = set(surface)
    edges: dict[str, list[str]] = {}
    sources = _frontend_sources()
    for path in sources:
        text = path.read_text(encoding="utf-8", errors="replace")
        hits: set[str] = set()
        for spec in _IMPORT_RE.findall(text):
            target = _resolve_import(spec, path)
            if target is None:
                continue
            target_rel = rel(target)
            if target_rel in surface_set:
                hits.add(target_rel)
        if hits:
            edges[rel(path)] = sorted(hits)
    return ImportGraph(surface=surface, edges=edges, scanned_files=len(sources))


def _is_test_file(path_rel: str) -> bool:
    return "__tests__" in path_rel or path_rel.endswith((".spec.ts", ".test.ts"))


def _is_inside_surface(path_rel: str) -> bool:
    return path_rel.startswith(rel(SYNC_DIR) + "/") and "/__tests__/" not in path_rel


def replacement_reachability(graph: ImportGraph) -> dict[str, Any]:
    """逐个替代面模块算「从替代面目录之外的生产文件是否可达」。

    🔴 **两个口径都要算，并且分开报**：

    * `direct` —— 被替代面目录之外的生产文件**直接** import；
    * `transitive` —— 从那些生产文件出发，允许经过替代面内部的边到达。

    首版只算 direct，结果与上游 deletion plan 在 `workpaperEntrySyncNotice.ts` 上对不上：
    它没有任何外部直接 importer，但被 `GtEntrySyncCapabilityNotice.vue`（41 个生产宿主在用）
    import。那不是数据分歧而是**口径差异** —— 压成一个口径就必然有一方看起来错了。
    上游登记的是 transitive，故交叉核对以 transitive 为准，direct 另报。
    """
    surface_set = set(graph.surface)
    # 生产文件（替代面之外、非测试）直接 import 到的替代面模块 = 传递可达的起点
    seeds: set[str] = set()
    for importer, targets in graph.edges.items():
        if _is_test_file(importer) or _is_inside_surface(importer):
            continue
        seeds.update(targets)
    # 替代面内部的边：module -> 它 import 的替代面模块
    internal: dict[str, list[str]] = {
        importer: targets
        for importer, targets in graph.edges.items()
        if _is_inside_surface(importer) and importer in surface_set
    }
    reachable: set[str] = set()
    frontier = list(seeds)
    while frontier:
        current = frontier.pop()
        if current in reachable:
            continue
        reachable.add(current)
        frontier.extend(internal.get(current, []))

    rows: list[dict[str, Any]] = []
    for module_rel in graph.surface:
        importers = graph.importers_of(module_rel)
        production_outside = [
            importer
            for importer in importers
            if not _is_test_file(importer) and not _is_inside_surface(importer)
        ]
        inside = [
            importer
            for importer in importers
            if not _is_test_file(importer) and _is_inside_surface(importer)
        ]
        tests = [importer for importer in importers if _is_test_file(importer)]
        rows.append(
            {
                "module": module_rel,
                "production_importers_outside_surface": production_outside,
                "production_importer_outside_count": len(production_outside),
                "surface_internal_importer_count": len(inside),
                "test_importer_count": len(tests),
                "reachable_directly_from_production_host": bool(production_outside),
                "reachable_from_production_host": module_rel in reachable,
            }
        )
    unreachable = [row["module"] for row in rows if not row["reachable_from_production_host"]]
    direct_unreachable = [
        row["module"] for row in rows if not row["reachable_directly_from_production_host"]
    ]
    return {
        "scanned_frontend_files": graph.scanned_files,
        "surface_module_count": len(graph.surface),
        "modules": rows,
        "reachability_semantics": "transitive（起点 = 替代面之外的生产文件直接 import 到的模块，"
                                 "再沿替代面内部的 import 边闭包）",
        "unreachable_from_production_host": unreachable,
        "unreachable_count": len(unreachable),
        "reachable_count": len(graph.surface) - len(unreachable),
        "direct_unreachable_count": len(direct_unreachable),
        "direct_only_gap": sorted(set(direct_unreachable) - set(unreachable)),
        "direct_only_gap_note": "只被替代面内部引用、但那个引用方本身有生产宿主 —— 两个口径的"
                                "差集必须显式列出，否则「19/22 不可达」这个数字说不清是哪个口径。",
    }


def cross_check_reachability(recomputed: Mapping[str, Any]) -> dict[str, Any]:
    """与上游 deletion plan 的 `replacement_registry` 逐模块比对（只报告，不采信）。"""
    if not UPSTREAM_DELETION_PLAN_PATH.exists():
        return {"available": False}
    plan = read_json(UPSTREAM_DELETION_PLAN_PATH)
    registry = {
        str(row.get("path")): bool(row.get("reachable_from_production_host"))
        for row in (plan.get("replacement_registry") or [])
        if isinstance(row, dict)
    }
    mine = {
        str(row["module"]): bool(row["reachable_from_production_host"])
        for row in recomputed["modules"]
    }
    shared = sorted(set(registry) & set(mine))
    disagree = [key for key in shared if registry[key] != mine[key]]
    return {
        "available": True,
        "upstream_module_count": len(registry),
        "compared_module_count": len(shared),
        "only_upstream": sorted(set(registry) - set(mine)),
        "only_recomputed": sorted(set(mine) - set(registry)),
        "disagreeing_modules": disagree,
        "agrees": not disagree,
        "upstream_unreachable_count": sum(1 for value in registry.values() if not value),
        "recomputed_unreachable_count": recomputed["unreachable_count"],
    }


# ════════════════════════════════════════════════════════════════════════════
# §4 现算 ②：legacy 模式键分母与迁移正则覆盖（纯逻辑，可反事实/正向重算）
# ════════════════════════════════════════════════════════════════════════════

_DECL_RE = re.compile(
    r"""(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*(?:STORAGE|KEY|PREFIX)[A-Za-z0-9_]*)"""
    r"""\s*(?::\s*string\s*)?=\s*['"]([^'"]+)['"]""",
)
_TEMPLATE_RE = re.compile(r"`([^`]*)`")
_INTERP_RE = re.compile(r"\$\{[^}]*\}")
_MODE_HINT_RE = re.compile(r"(?:^|[-_:])(?:dual-)?mode(?:[-_:]|$)")
_PLACEHOLDER: Final[str] = "wpXYZ"


def legacy_migration_regex() -> str:
    """从模式键真源现读 `LEGACY_KEY_RE`（本门不抄第二份，改了必须一起动）。"""
    text = read_text(REPO / MODE_STORAGE_REL)
    match = re.search(r"^const LEGACY_KEY_RE = /(.+?)/\s*$", text, re.M)
    if match is None:
        raise Task69GateError(f"{MODE_STORAGE_REL} 里取不到 LEGACY_KEY_RE")
    return match.group(1)


def reconstruct_key_forms(text: str, const_name: str, literal: str) -> list[str]:
    """按源码里的真实拼接式重建这个常量会产出的 localStorage 键形态。

    三种拼接都要认（否则分母会漏）：模板字符串 `${PREFIX}${wpId}`、`PREFIX + wpId`、
    以及常量直接当键用。插值一律替换成占位 wpId —— 判据关心的是**键的结构**。
    """
    forms: set[str] = set()
    for template in _TEMPLATE_RE.findall(text):
        if f"${{{const_name}}}" in template:
            forms.add(_INTERP_RE.sub(_PLACEHOLDER, template.replace(f"${{{const_name}}}", literal)))
    if re.search(rf"\b{re.escape(const_name)}\s*\+", text):
        forms.add(literal + _PLACEHOLDER)
    if re.search(
        rf"localStorage\.(?:get|set|remove)Item\(\s*{re.escape(const_name)}\s*[,)]", text
    ):
        forms.add(literal)
    return sorted(forms) or [literal]


def legacy_mode_key_coverage() -> dict[str, Any]:
    """现算「旧模式键 → 统一键」迁移正则的覆盖面。

    分母是**源码里真实存在的键形态**，不是一张会漂移的前缀名单（AC 11.8 的迁移面）。
    """
    pattern_source = legacy_migration_regex()
    pattern = re.compile(pattern_source)
    rows: list[dict[str, Any]] = []
    for path in _frontend_sources():
        path_rel = rel(path)
        if _is_test_file(path_rel) or path.parent == SYNC_DIR:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "localStorage" not in text:
            continue
        for const_name, literal in _DECL_RE.findall(text):
            if not _MODE_HINT_RE.search(literal):
                continue
            forms = reconstruct_key_forms(text, const_name, literal)
            covered = all(pattern.match(form) is not None for form in forms)
            rows.append(
                {
                    "file": path_rel,
                    "const": const_name,
                    "literal": literal,
                    "key_forms": forms,
                    "covered_by_migration_regex": covered,
                    # dual-mode 判据 = 该文件真的声明了 onlyoffice 侧模式（view-mode 类不算）
                    "is_dual_mode_surface": "'onlyoffice'" in text,
                }
            )
    rows.sort(key=lambda row: (row["file"], row["const"]))
    dual = [row for row in rows if row["is_dual_mode_surface"]]
    gaps = [row for row in dual if not row["covered_by_migration_regex"]]
    return {
        "migration_regex_source": pattern_source,
        "migration_regex_read_from": MODE_STORAGE_REL,
        "mode_key_constant_total": len(rows),
        "dual_mode_constant_total": len(dual),
        "non_dual_mode_constants": [
            {"file": row["file"], "literal": row["literal"], "key_forms": row["key_forms"]}
            for row in rows
            if not row["is_dual_mode_surface"]
        ],
        "covered_count": len(dual) - len(gaps),
        "uncovered_count": len(gaps),
        "uncovered": [
            {
                "file": row["file"],
                "const": row["const"],
                "literal": row["literal"],
                "key_forms": row["key_forms"],
                "why_uncovered": (
                    "键形态里没有 `-dual-mode:` 字面段（分隔符或命名漂移）"
                    if any("-dual-mode:" not in form for form in row["key_forms"])
                    else "未知"
                ),
                "also_missing_wp_segment": all(
                    _PLACEHOLDER not in form for form in row["key_forms"]
                ),
            }
            for row in gaps
        ],
        "rows": rows,
    }


# ════════════════════════════════════════════════════════════════════════════
# §5 现算 ③：桥状态域 / 文案（AC 11.2 / 11.3 的逻辑级复算）
# ════════════════════════════════════════════════════════════════════════════


def _extract_string_array(text: str, const_name: str) -> list[str]:
    """从 TS 源里取一个字符串数组常量的成员（括号配对，禁固定字符窗口）。"""
    anchor = re.search(rf"\b{re.escape(const_name)}\s*(?::[^=]*)?=\s*\[", text)
    if anchor is None:
        raise Task69GateError(f"取不到数组常量 {const_name}")
    start = text.index("[", anchor.start())
    depth = 0
    end = -1
    for index in range(start, len(text)):
        char = text[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end < 0:
        raise Task69GateError(f"{const_name} 的数组括号不配对")
    return re.findall(r"'([^']+)'", text[start : end + 1])


def _extract_record_literal(text: str, const_name: str) -> dict[str, str]:
    """从 TS 源里取一个 `key: '中文'` 映射常量（花括号配对）。"""
    anchor = re.search(rf"\b{re.escape(const_name)}\s*(?::[^=]*)?=\s*Object\.freeze\(\{{", text)
    if anchor is None:
        anchor = re.search(rf"\b{re.escape(const_name)}\s*(?::[^=]*)?=\s*\{{", text)
    if anchor is None:
        raise Task69GateError(f"取不到映射常量 {const_name}")
    start = text.index("{", anchor.start())
    depth = 0
    end = -1
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end < 0:
        raise Task69GateError(f"{const_name} 的花括号不配对")
    body = text[start : end + 1]
    return dict(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*'([^']*)'", body, re.M))


def bridge_state_surface() -> dict[str, Any]:
    """独立复算桥状态域与文案的三条结构事实（AC 11.2 / 11.3）。

    这是**逻辑级现算**：不依赖 vitest 是否跑过，改一个状态名/文案立刻变。
    """
    text = read_text(REPO / BRIDGE_MACHINE_REL)
    states = _extract_string_array(text, "WP_BRIDGE_STATES")
    required = _extract_string_array(text, "WP_BRIDGE_AC_11_2_REQUIRED_STATES")
    terminals = _extract_string_array(text, "WP_BRIDGE_TERMINAL_STATES")
    events = _extract_string_array(text, "WP_BRIDGE_EVENTS")
    texts = _extract_record_literal(text, "WP_BRIDGE_STATE_TEXT")
    missing_required = [state for state in required if state not in states]
    missing_text = [state for state in states if state not in texts]
    duplicate_text = sorted(
        {value for value in texts.values() if list(texts.values()).count(value) > 1}
    )
    forbidden = sorted(state for state, value in texts.items() if "同步成功" in value)
    return {
        "state_count": len(states),
        "states": states,
        "ac_11_2_required_states": required,
        "ac_11_2_required_count": len(required),
        "ac_11_2_missing_from_domain": missing_required,
        "terminal_states": terminals,
        "event_count": len(events),
        "state_text_entries": len(texts),
        "states_without_text": missing_text,
        "duplicate_state_texts": duplicate_text,
        "states_with_forbidden_success_text": forbidden,
        "four_ac_11_3_texts_distinct": len(
            {
                texts.get("forcesave_accepted", ""),
                texts.get("incoming_durable", ""),
                texts.get("applied", ""),
                texts.get("conflict", ""),
            }
        )
        == 4,
    }


# ════════════════════════════════════════════════════════════════════════════
# §6 现算 ④：DOM/network 顺序判据（对 vitest 导出的真实观测带重新表达一遍）
# ════════════════════════════════════════════════════════════════════════════

TraceRow = dict[str, Any]

#: 每条被判据的顺序链。`marker` 形态 `kind:name`，与 vitest 侧观测带逐字同域。
ORDER_CHAINS: Final[dict[str, tuple[str, ...]]] = {
    "descriptor_open": (
        "net:create_pending_mutation",
        "net:materialize",
        "editor:doc-editor-constructed",
        "emit:ready",
        "net:confirm_descriptor",
        "dom:after-confirm",
    ),
    "recovery_claim": (
        "net:list_recovery_cases",
        "net:claim_recovery_case",
        "net:get_operation",
    ),
    "recovery_download_only": (
        "net:list_recovery_cases",
        "net:terminate_recovery_download_only",
    ),
    "crash_recovery": (
        "net:confirm_descriptor",
        "net:list_recovery_cases",
        "emit:recovery-case",
    ),
}


def index_of(rows: Sequence[TraceRow], marker: str) -> int:
    kind, name = marker.split(":", 1)
    for index, row in enumerate(rows):
        if row.get("kind") == kind and row.get("name") == name:
            return index
    return -1


def judge_order(rows: Sequence[TraceRow], chain: Sequence[str]) -> dict[str, Any]:
    """顺序判据的**唯一**实现。返回结构化结论而不是抛 —— 反事实臂要复用它。

    🔴 判「三件事都发生过」是不够的：那种判据对顺序被交换全绿。这里逐对比下标，
    并把缺项单独列出来（缺项也不能被读成「顺序对」）。
    """
    positions = [(marker, index_of(rows, marker)) for marker in chain]
    missing = [marker for marker, index in positions if index < 0]
    violations = []
    if not missing:
        for previous, current in zip(positions, positions[1:]):
            if previous[1] >= current[1]:
                violations.append(f"{previous[0]}(#{previous[1]}) 不早于 {current[0]}(#{current[1]})")
    return {
        "chain": list(chain),
        "positions": {marker: index for marker, index in positions},
        "missing_markers": missing,
        "order_violations": violations,
        "ok": not missing and not violations,
    }


def swap_rows(rows: Sequence[TraceRow], first: str, second: str) -> list[TraceRow]:
    copy = [dict(row) for row in rows]
    i = index_of(copy, first)
    j = index_of(copy, second)
    if i < 0 or j < 0:
        raise Task69GateError(f"合成坏观测带失败：缺 {first} 或 {second}")
    copy[i], copy[j] = copy[j], copy[i]
    return copy


def evaluate_order_chains(traces: Mapping[str, Any]) -> dict[str, Any]:
    """对每条链现算结论，并逐链做「交换相邻两项 ⇒ 判据必须翻红」的反事实臂。"""
    rows_out: list[dict[str, Any]] = []
    for name, chain in ORDER_CHAINS.items():
        rows = traces.get(name)
        if not isinstance(rows, list) or not rows:
            rows_out.append(
                {
                    "scenario": name,
                    "trace_present": False,
                    "ok": False,
                    "why": "vitest 未导出该场景的观测带 —— 无观测就不能宣称顺序成立",
                }
            )
            continue
        verdict = judge_order(rows, chain)
        arms: list[dict[str, Any]] = []
        for previous, current in zip(chain, chain[1:]):
            swapped_rows = swap_rows(rows, previous, current)
            swapped_verdict = judge_order(swapped_rows, chain)
            arms.append(
                {
                    "swapped": [previous, current],
                    "flips_to_red": not swapped_verdict["ok"],
                    "violations": swapped_verdict["order_violations"],
                }
            )
        # 正向重算：合成一条**已知顺序正确**的最小观测带，判据必须判过
        synthetic_ok = judge_order(
            [
                {"seq": index + 1, "kind": marker.split(":", 1)[0], "name": marker.split(":", 1)[1]}
                for index, marker in enumerate(chain)
            ],
            chain,
        )
        # 正向重算 ②：合成一条**缺一项**的观测带，判据必须判不过
        synthetic_missing = judge_order(
            [
                {"seq": index + 1, "kind": marker.split(":", 1)[0], "name": marker.split(":", 1)[1]}
                for index, marker in enumerate(chain[:-1])
            ],
            chain,
        )
        rows_out.append(
            {
                "scenario": name,
                "trace_present": True,
                "trace_row_count": len(rows),
                "verdict": verdict,
                "ok": verdict["ok"],
                "counterfactual_arms": arms,
                "all_arms_flip_to_red": all(arm["flips_to_red"] for arm in arms),
                "forward_recompute_accepts_correct_order": synthetic_ok["ok"],
                "forward_recompute_rejects_missing_marker": not synthetic_missing["ok"],
            }
        )
    return {
        "chains": rows_out,
        "chain_count": len(rows_out),
        "all_ok": all(row.get("ok") for row in rows_out),
        "all_arms_flip": all(row.get("all_arms_flip_to_red", False) for row in rows_out),
        "forward_recompute_ok": all(
            row.get("forward_recompute_accepts_correct_order", False)
            and row.get("forward_recompute_rejects_missing_marker", False)
            for row in rows_out
        ),
    }


def three_entity_facts(traces: Mapping[str, Any]) -> dict[str, Any]:
    """从真实观测带里现算「claim 前三实体为 0」「download-only 三者为 0」两条结论。

    判据落在**前端观测到的 network 序列**上（不读后端库）：claim 之前不得出现任何创建
    request/application/operation 的端点调用；download-only 整趟只允许那一个端点。
    """
    creating_endpoints = {
        "request_forcesave",
        "claim_recovery_case",
        "create_close_intent",
        "materialize",
        "create_pending_mutation",
    }
    out: dict[str, Any] = {}

    claim_rows = traces.get("recovery_claim") or []
    claim_index = index_of(claim_rows, "net:claim_recovery_case")
    before_claim = [
        row.get("name")
        for row in claim_rows[: max(claim_index, 0)]
        if row.get("kind") == "net" and row.get("name") in creating_endpoints
    ]
    # descriptor 打开阶段的 materialize / pending-mutation 属于 HTML→OO 链路，不是
    # recovery 三实体；此处只看 forcesave / claim / close-intent 三类真正会建实体的端点
    entity_creating_before_claim = [
        name for name in before_claim if name in {"request_forcesave", "claim_recovery_case", "create_close_intent"}
    ]
    out["claim"] = {
        "trace_present": bool(claim_rows),
        "claim_call_index": claim_index,
        "entity_creating_calls_before_claim": entity_creating_before_claim,
        "three_entities_zero_before_claim": claim_index >= 0 and not entity_creating_before_claim,
        "operation_probe_after_claim": index_of(claim_rows, "net:get_operation") > claim_index >= 0,
    }

    dl_rows = traces.get("recovery_download_only") or []
    dl_index = index_of(dl_rows, "net:terminate_recovery_download_only")
    after_dl = [
        row.get("name")
        for row in dl_rows[dl_index + 1 :]
        if row.get("kind") == "net" and row.get("name") in creating_endpoints
    ]
    dl_creating = [
        row.get("name")
        for row in dl_rows
        if row.get("kind") == "net"
        and row.get("name") in {"request_forcesave", "claim_recovery_case", "create_close_intent"}
    ]
    out["download_only"] = {
        "trace_present": bool(dl_rows),
        "terminate_call_index": dl_index,
        "entity_creating_calls_anywhere": dl_creating,
        "calls_after_terminate": after_dl,
        "three_entities_zero": dl_index >= 0 and not dl_creating and not after_dl,
    }

    crash_rows = traces.get("crash_recovery") or []
    crash_creating = [
        row.get("name")
        for row in crash_rows
        if row.get("kind") == "net"
        and row.get("name") in {"request_forcesave", "claim_recovery_case", "create_close_intent"}
    ]
    out["crash"] = {
        "trace_present": bool(crash_rows),
        "recovery_case_emitted": index_of(crash_rows, "emit:recovery-case") >= 0,
        "entity_creating_calls": crash_creating,
        "three_entities_zero": bool(crash_rows) and not crash_creating,
    }

    # 反事实臂：往每条真实观测带里注入一次 forcesave 调用 ⇒ 三条结论都必须翻红
    arms: list[dict[str, Any]] = []
    for scenario, rows in (
        ("claim", claim_rows),
        ("download_only", dl_rows),
        ("crash", crash_rows),
    ):
        if not rows:
            arms.append({"scenario": scenario, "injected": False, "flips_to_red": False})
            continue
        poisoned = [dict(row) for row in rows]
        poisoned.insert(0, {"seq": 0, "kind": "net", "name": "request_forcesave", "detail": {}})
        poisoned_facts = _three_entity_verdict(scenario, poisoned)
        arms.append({"scenario": scenario, "injected": True, "flips_to_red": not poisoned_facts})
    out["counterfactual_arms"] = arms
    out["all_arms_flip_to_red"] = all(arm["flips_to_red"] for arm in arms)
    out["all_ok"] = (
        out["claim"]["three_entities_zero_before_claim"]
        and out["claim"]["operation_probe_after_claim"]
        and out["download_only"]["three_entities_zero"]
        and out["crash"]["three_entities_zero"]
    )
    return out


def _three_entity_verdict(scenario: str, rows: Sequence[TraceRow]) -> bool:
    """把「三实体为 0」的结论抽成一个可对任意观测带复用的纯判据（反事实臂用）。"""
    entity_endpoints = {"request_forcesave", "claim_recovery_case", "create_close_intent"}
    if scenario == "claim":
        claim_index = index_of(rows, "net:claim_recovery_case")
        if claim_index < 0:
            return False
        return not [
            row
            for row in rows[:claim_index]
            if row.get("kind") == "net" and row.get("name") in entity_endpoints
        ]
    return not [
        row for row in rows if row.get("kind") == "net" and row.get("name") in entity_endpoints
    ]


# ════════════════════════════════════════════════════════════════════════════
# §7 辐射面（按引用关系反查，不跑无边界全量）
# ════════════════════════════════════════════════════════════════════════════


def radiation_surface(graph: ImportGraph) -> dict[str, Any]:
    """现算「哪些前端 spec 文件与本门碰的模块有引用关系」。

    本门**不改任何生产文件**，只新增一个 spec。所以辐射面 = 引用了同一批替代面模块的
    全部 spec 文件（证明新文件不破坏它们）+ 本门自己的判据面。名单现算，不手抄。
    """
    spec_files: dict[str, list[str]] = {}
    for importer, targets in graph.edges.items():
        if not _is_test_file(importer):
            continue
        if not importer.endswith(".spec.ts"):
            continue
        spec_files[importer] = targets
    guard = GUARD_SPEC_REL
    if guard not in spec_files:
        spec_files[guard] = graph.edges.get(guard, [])
    files = dict(sorted(spec_files.items()))
    return {
        "how": "扫全部前端 ts/vue 的 import，解析到替代面目录下的模块即计入；再取其中的 "
               "*.spec.ts 作为需要复跑的辐射面。不手抄名单，不跑无边界全量。",
        "frontend_files_scanned": graph.scanned_files,
        "spec_file_count": len(files),
        "spec_files": files,
        "own_guard_included": guard in files,
        "own_guard_path": guard,
        "digest": digest_of(files),
        "backend_touched_production_files": [],
        "backend_touched_note": "本门未改任何后端生产代码/迁移，故后端辐射面只有上游报告的"
                                "逐字节锁（`test_task67_structural_pre_reconcile.py` 与 "
                                "`test_task68_backend_chain_regression.py`），单独在 "
                                "`upstream_lock_reruns` 里登记。",
    }


UPSTREAM_LOCK_TESTS: Final[tuple[str, ...]] = (
    "backend/tests/workpaper_sync/test_task67_structural_pre_reconcile.py",
    "backend/tests/workpaper_sync/test_task68_backend_chain_regression.py",
)


# ════════════════════════════════════════════════════════════════════════════
# §8 不变量声明
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Invariant:
    """一条独立不变量。

    :param want_test: 本门判据面里那条测试的稳定标识（`[T69-Inn]`）。门要求它**存在且通过**
        —— 改名/删掉都会让本条立刻红（比「文件里有这个字符串」强，因为它读的是真实执行结果）。
    :param logic_key: 逻辑级现算判据的键（教训 17）。为 None 表示这条只由真实执行承载，
        报告里如实标 `logic_side.state = "behaviour_only"`。
    """

    id: str
    sub_bullet: int
    statement: str
    want_test: str
    properties: tuple[int, ...]
    requirements: tuple[str, ...]
    logic_key: str | None = None
    immediate_failure: str | None = None


ALL_INVARIANTS: Final[tuple[Invariant, ...]] = (
    # ── 子条目 1
    Invariant(
        id="bridge_state_domain_closed_under_random_events",
        sub_bullet=1,
        statement="随机事件序列只能进入声明状态；非法转换抛显式互不相同的码且不产出新状态；"
                  "AC 11.2 的 19 个状态逐字在域内；表自证无孤岛/死端/漏边。",
        want_test="[T69-I01]",
        properties=(46,),
        requirements=("11.2",),
        logic_key="bridge_state_domain",
    ),
    Invariant(
        id="editor_mounts_only_with_descriptor",
        sub_bullet=1,
        statement="无 descriptor 时 DocEditor 构造次数为 0；descriptor 到位且 mode=oo 才构造恰一次。",
        want_test="[T69-I02]",
        properties=(11, 47),
        requirements=("3.7", "11.4"),
    ),
    Invariant(
        id="status_text_is_derived_not_constant",
        sub_bullet=1,
        statement="状态条文案是逐状态派生值（≥4 个状态两两不同），全域没有一条「同步成功」，"
                  "AC 11.3 的四类文案互不相同。",
        want_test="[T69-I03]",
        properties=(48,),
        requirements=("11.2",),
        logic_key="bridge_state_text",
    ),
    Invariant(
        id="recovery_panel_and_plain_retry_are_state_gated",
        sub_bullet=1,
        statement="oo_editing 时 recovery 区不渲染；进入 recovery_pending 后 recovery 区渲染而"
                  "普通重试按钮结构性不渲染（AC 5.8 末句）。",
        want_test="[T69-I04]",
        properties=(47,),
        requirements=("11.6",),
    ),
    Invariant(
        id="legacy_mode_key_migration_is_idempotent_and_capability_bounded",
        sub_bullet=1,
        statement="旧模式键首次迁移写统一键并删旧键；第二次不覆盖用户手动切换；capability "
                  "不支持的存量值回落真实可用模式；unreachable 不写统一键（AC 11.8）。",
        want_test="[T69-I05]",
        properties=(46,),
        requirements=("11.2",),
        logic_key="legacy_mode_key_coverage",
    ),
    Invariant(
        id="content_event_dedupes_by_wp_and_revision",
        sub_bullet=1,
        statement="内容事件按 wp_id + revision 去重；重复投递不重复 reload；跨 wp 事件不触发本 wp "
                  "reload；纯表示升级不重载（AC 11.9）。",
        want_test="[T69-I06]",
        properties=(46,),
        requirements=("11.9",),
    ),
    Invariant(
        id="server_and_client_baselines_stay_two_fields",
        sub_bullet=1,
        statement="descriptor 的 server_applied_revision 与 client_confirmed_base_revision 是两个"
                  "不同字段；confirm 回传 content_revision（服务端已应用），不回传 client 基线。",
        want_test="[T69-I07]",
        properties=(11, 58),
        requirements=("3.7", "4.11"),
    ),
    Invariant(
        id="normal_shell_converges_to_primary_or_terminal_duplicate",
        sub_bullet=1,
        statement="202 之后 shell 落 waiting_application 且 application 尚不存在；按快照分别收敛为"
                  "primary（application_bound）或 terminal duplicate，duplicate 之后不再推进。",
        want_test="[T69-I08]",
        properties=(12,),
        requirements=("4.1", "5.8"),
    ),
    Invariant(
        id="followups_use_requested_operation_id",
        sub_bullet=1,
        statement="duplicate 之后 GET/conflicts/timeline/retry 的真实 URL 仍是 requested id，"
                  "canonical id 不出现在任何 URL 里，但保留在投影中供显示。",
        want_test="[T69-I09]",
        properties=(12,),
        requirements=("4.1", "5.8"),
    ),
    Invariant(
        id="refresh_required_reopen_path_is_table_only",
        sub_bullet=1,
        statement="转换表声明了 refresh_required → rematerializing → oo_loading，但桥没有任何公开"
                  "动作能 apply `descriptor_received`；此时推新 descriptor 会被桥拒绝并落成可见"
                  "宿主失败（如实登记为缺口，不假绿）。",
        want_test="[T69-I10]",
        properties=(11, 46),
        requirements=("4.11", "11.2"),
    ),
    Invariant(
        id="close_leader_stale_successor_and_recovery_required",
        sub_bullet=1,
        statement="close leader 失权先显示 close_authorization_stale；缺 successor intent id 时拒绝"
                  "渲染成功；合法 successor 接任后 generation 不变；无 successor 进入 "
                  "close_recovery_required、停止 loading（可离开）且不显示 applied 文案。",
        want_test="[T69-I11]",
        properties=(15,),
        requirements=("4.7", "11.2"),
    ),
    Invariant(
        id="flush_failure_blocks_materialize_and_mount",
        sub_bullet=1,
        statement="flush 抛错时 materialize 与 pending-mutation 的真实调用次数为 0、DocEditor 构造"
                  "次数为 0、mode 停在 html、状态条为 error（Property 8 / AC 3.2）。",
        want_test="[T69-I12]",
        properties=(8,),
        requirements=("3.2",),
    ),
    Invariant(
        id="callback_timeout_keeps_oo_and_allows_retry",
        sub_bullet=1,
        statement="超时（无响应体无 error_code）时 mode 仍 oo、错误可见、裁决为可重试、reloadHtml "
                  "调用次数为 0、重试按钮渲染（Property 13 / AC 4.4）。",
        want_test="[T69-I13]",
        properties=(13,),
        requirements=("4.4",),
    ),
    Invariant(
        id="applied_reload_uses_result_revision",
        sub_bullet=1,
        statement="applied 之后 reloadHtml 收到的最小 revision 不低于 operation 的 result_revision；"
                  "pre-bind shell 带 result_revision 时投影显式拒绝（Property 14）。",
        want_test="[T69-I14]",
        properties=(14,),
        requirements=("4.5",),
    ),
    Invariant(
        id="conflict_records_are_traceable_on_both_sides",
        sub_bullet=1,
        statement="冲突面板逐项渲染 JSON Pointer 与 OO 位置（两者不同）、base/current/incoming 三方值"
                  "（两两不同）与业务标签，四者均非空；关闭面板不得自动应用任何一侧（AC 11.7）。",
        want_test="[T69-I33]",
        properties=(35,),
        requirements=("8.1",),
    ),
    Invariant(
        id="unconfirmed_descriptor_cannot_enter_editing",
        sub_bullet=1,
        statement="confirm 返回 forcesave_unlocked=false 时不得进入 oo_editing、不得解锁保存、"
                  "宿主必须收回编辑器，程序化 forceSave 仍 fail visible。",
        want_test="[T69-I15]",
        properties=(11, 15),
        requirements=("3.7", "4.7"),
    ),
    # ── 子条目 2
    Invariant(
        id="every_request_carries_explicit_project_wp_entry",
        sub_bullet=2,
        statement="真实发出的每个请求 URL 都以 project/wp/entry 三段前缀开头、entry_id 的 `/` 未被"
                  "percent-encode；三段各缺一次都在发出前被拒且零新增调用。",
        want_test="[T69-I16]",
        properties=(11, 47),
        requirements=("11.4", "11.11"),
    ),
    Invariant(
        id="recovery_list_carries_room_and_generation",
        sub_bullet=2,
        statement="recovery list 的真实 query 恰为 {room_id, generation}；缺 room_id 或 generation "
                  "非整数时在发出前被拒且零新增调用。",
        want_test="[T69-I17]",
        properties=(47,),
        requirements=("11.6",),
    ),
    Invariant(
        id="rollback_uses_opaque_version_id_under_entry_scope",
        sub_bullet=2,
        statement="rollback 的真实 URL 是 entry scope 前缀 + /versions/{opaque uuid}/rollback；"
                  "numeric revision / 全零 UUID / 缺二次确认三条各自在发出前被拒。",
        want_test="[T69-I18]",
        properties=(47,),
        requirements=("11.11",),
    ),
    Invariant(
        id="unified_404_403_does_not_disclose_the_object",
        sub_bullet=2,
        statement="统一 404 与 403 归一成同一个不泄露码与同一文案（两者不可区分），文案不含"
                  "operation/room/wp 标识；与「本地/传输失败」的码不同（后者可重试）。",
        want_test="[T69-I19]",
        properties=(47,),
        requirements=("11.6", "11.11"),
    ),
    Invariant(
        id="crash_enters_recovery_pending_with_three_entities_zero",
        sub_bullet=2,
        statement="编辑器异常中断后进入 recovery_pending；列出的 case 三实体全空；桥的 requested "
                  "operation 与 canonical application 均为 null；recoveryCase emit 载荷键集恰为 "
                  "{caseId, reason}；服务端若返回带三实体的 unclaimed case，DTO 必须 fail visible。",
        want_test="[T69-I20]",
        properties=(12, 47, 58),
        requirements=("5.8", "11.5"),
        logic_key="three_entities_crash",
    ),
    Invariant(
        id="claim_associates_three_entities_only_on_success",
        sub_bullet=2,
        statement="claim 成功后同时关联三实体并按服务端形态落 primary/duplicate；claim 请求体是"
                  "白名单键集；prior confirmation / bundle / fence / contributor 四类错误各自失败"
                  "且拒绝理由互不命中，三实体仍为 0、零 operation 探针。",
        want_test="[T69-I21]",
        properties=(12, 58),
        requirements=("5.8", "11.6"),
        logic_key="three_entities_claim",
    ),
    Invariant(
        id="download_only_keeps_three_entities_zero",
        sub_bullet=2,
        statement="download-only 之后端点多重集恰为它自己、三实体为 0、状态条不是 success 且不等于"
                  "applied 文案；服务端若在回执里塞三实体，DTO 必须 fail visible。",
        want_test="[T69-I22]",
        properties=(46, 48, 58),
        requirements=("5.8", "11.10"),
        logic_key="three_entities_download_only",
    ),
    Invariant(
        id="plain_retry_refuses_null_operation",
        sub_bullet=2,
        statement="普通 retry 在桥层与 API 层各有互不相同的拒绝码，且零网络调用（AC 5.8 末句）。",
        want_test="[T69-I23]",
        properties=(47,),
        requirements=("5.8",),
    ),
    # ── 子条目 3
    Invariant(
        id="descriptor_order_mount_ready_confirm",
        sub_bullet=3,
        statement="真实观测带上 pending → materialize → DocEditor 构造 → ready → confirm → DOM "
                  "逐项递增；交换相邻两项、缺任一项时同一判据必须翻红。",
        want_test="[T69-I24]",
        properties=(11, 58),
        requirements=("3.7", "14.8"),
        logic_key="order_descriptor_open",
    ),
    Invariant(
        id="mounted_but_unconfirmed_is_masked_and_locked",
        sub_bullet=3,
        statement="已挂载而 ready 未触发时遮罩在位、保存按钮 disabled、程序化 forceSave 可见失败且"
                  "零 forcesave 调用、且不把正在飞行的确认推成 error；confirm 成功后才解锁。",
        want_test="[T69-I25]",
        properties=(11, 47),
        requirements=("3.7", "11.5"),
    ),
    Invariant(
        id="nonexistent_prop_or_expose_fails_immediately",
        sub_bullet=3,
        statement="传不存在的 prop 名时 DocEditor 构造次数为 0（对照组正确 prop 名必须真挂载）；"
                  "expose 的 forceSave/getSyncState 必须是真函数且真能跑出派生值；不存在的 expose "
                  "读到 undefined。",
        want_test="[T69-I26]",
        properties=(47,),
        requirements=("11.5", "11.12"),
        immediate_failure="nonexistent_prop_or_expose",
    ),
    Invariant(
        id="editor_never_fetches_its_own_config",
        sub_bullet=3,
        statement="整趟 descriptor 链路的端点多重集**等于** {pending, materialize, confirm}（合成一次"
                  "多余调用即翻红）；交给 DocEditor 的 config 相对 descriptor 只多出 width/height/"
                  "events，且每段同一引用；编辑器侧 forcesave=true 时拒绝挂载。",
        want_test="[T69-I27]",
        properties=(11, 47),
        requirements=("3.7", "11.4"),
        immediate_failure="editor_fetches_its_own_config",
    ),
    Invariant(
        id="normal_shell_never_fakes_application_early",
        sub_bullet=3,
        statement="forcesave_accepted 阶段不接受 operation 观测（跳过 shell 阶段结构性不可达）；"
                  "202 之后快照 shape 仍 pre_correlation 且两 link 均空；shell_tracking_started 缺"
                  "requested id 时以专属码拒绝。",
        want_test="[T69-I28]",
        properties=(12, 14),
        requirements=("4.1", "5.8"),
        immediate_failure="normal_shell_fakes_application_early",
    ),
    Invariant(
        id="three_entities_never_faked_before_claim",
        sub_bullet=3,
        statement="三个 recovery 状态各自对三个实体逐个非空的进入都以 "
                  "`bridge_recovery_premature_entities` 拒绝（九种组合逐一）；claim 成功缺任一实体"
                  "以专属码拒绝；download-only 终态没有通往 applied 的边。",
        want_test="[T69-I29]",
        properties=(46, 47),
        requirements=("5.8", "11.5"),
        immediate_failure="three_entities_faked_before_claim",
    ),
    Invariant(
        id="fail_open_success_text_is_forbidden",
        sub_bullet=3,
        statement="一次真失败之后 destroy/DOM 重渲染/dirty 复位/unmount 都不得把状态条转成功；"
                  "只有用户显式发起的新尝试（reset）才清 —— 反事实臂证明它真会清，于是「粘住」"
                  "与「永远不清」可区分。",
        want_test="[T69-I30]",
        properties=(48,),
        requirements=("11.10",),
        immediate_failure="fail_open_success_text",
    ),
    Invariant(
        id="host_failure_becomes_visible_sticky_error",
        sub_bullet=3,
        statement="DocsAPI 载不到时零 DocEditor 构造、状态条 error、宿主错误块渲染、桥进入 error "
                  "且可离开（永久 loading 的可观测反面），error 事件带真实 stage。",
        want_test="[T69-I31]",
        properties=(48,),
        requirements=("11.10", "11.6"),
    ),
    Invariant(
        id="all_ac_11_5_events_have_real_trigger_paths",
        sub_bullet=3,
        statement="ready/dirty/save-requested/incoming-durable/terminal/recovery-case/error 七个事件"
                  "逐个被真实路径触发；terminal 的 state/revision 可辨；incoming-durable 的"
                  " artifactSha256 只能为 null（已登记上游缺口，不得拿另一份摘要顶替）。",
        want_test="[T69-I32]",
        properties=(47,),
        requirements=("11.5",),
    ),
)


# ════════════════════════════════════════════════════════════════════════════
# §9 真实执行：vitest（辐射面 + 本门判据面）与观测带导出
# ════════════════════════════════════════════════════════════════════════════


def run_vitest(surface: Mapping[str, Any]) -> dict[str, Any]:
    """真跑辐射面 vitest，并让判据面把观测带导出到临时文件。

    🔴 **不经 shell 字符串拼接**之外还有一条：Windows 上 `npm exec` 必须走
    `cmd /c "<单串>"` —— `subprocess.run([...], shell=True)` 形态下 npm 把
    `--reporter/--outputFile` 当自己的参数吞掉，退出码 0 而 JSON 从不产出。
    """
    targets = sorted(surface["spec_files"])
    # 🔴 vitest 的过滤参数按**项目根**（= `audit-platform/frontend`）解析，不是仓库根。
    # 传仓库相对路径会静默匹配到 0 个 suite（退出码非零但报告里 `suite_total=0`），
    # 于是「行为侧全红」看起来像被判据的代码坏了，实际是过滤器写错了。
    frontend_prefix = rel(FRONTEND) + "/"
    filter_targets = [
        target[len(frontend_prefix) :] if target.startswith(frontend_prefix) else target
        for target in targets
    ]
    with tempfile.TemporaryDirectory(prefix="task69_vitest_") as tmpdir:
        report_path = Path(tmpdir) / "report.json"
        trace_path = Path(tmpdir) / "traces.json"
        filters = " ".join(filter_targets)
        command = (
            f"npm exec -- vitest run {filters} --reporter=json "
            f'--outputFile="{report_path}"'
        )
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["T69_TRACE_OUT"] = str(trace_path)
        proc = subprocess.run(
            ["cmd", "/c", command] if os.name == "nt" else ["sh", "-c", command],
            cwd=str(FRONTEND),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
        )
        if not report_path.exists():
            tail = ((proc.stdout or "") + (proc.stderr or ""))[-1200:]
            return {
                "executed": False,
                "return_code": proc.returncode,
                "error": "vitest 未产出 JSON 报告",
                "tail": tail,
                "targets": targets,
            }
        report = json.loads(report_path.read_text(encoding="utf-8"))
        traces: dict[str, Any] = {}
        if trace_path.exists():
            traces = json.loads(trace_path.read_text(encoding="utf-8")).get("traces") or {}

    tests: dict[str, str] = {}
    failures: list[dict[str, str]] = []
    for suite in report.get("testResults") or []:
        suite_name = str(suite.get("name") or "").replace("\\", "/")
        for assertion in suite.get("assertionResults") or []:
            full = str(assertion.get("fullName") or assertion.get("title") or "")
            status = str(assertion.get("status") or "")
            tests[full] = status
            if status not in {"passed", "skipped", "todo"}:
                failures.append(
                    {
                        "suite": suite_name.rsplit("/", 1)[-1],
                        "test": full,
                        "status": status,
                        "message": ((assertion.get("failureMessages") or [""])[0] or "")[:400],
                    }
                )
    suite_total = int(report.get("numTotalTestSuites") or 0)
    return {
        "executed": True,
        # 0 个 suite 是过滤器写错的特征形态（不是「全过了」）。显式登记，让判定能打红。
        "matched_zero_suites": suite_total == 0,
        "return_code": proc.returncode,
        "targets": targets,
        "filter_targets": filter_targets,
        "target_count": len(targets),
        "suite_total": report.get("numTotalTestSuites"),
        "suite_failed": report.get("numFailedTestSuites"),
        "test_total": report.get("numTotalTests"),
        "test_passed": report.get("numPassedTests"),
        "test_failed": report.get("numFailedTests"),
        "test_statuses": dict(sorted(tests.items())),
        "failures": failures,
        "traces": traces,
        "trace_scenarios": sorted(traces),
        # 墙钟耗时刻意**不入报告**：`--check` 的逐字节锁会因为它永远对不上（Task 68 已踩过）
        "wallclock_excluded": True,
    }


def find_test_status(run: Mapping[str, Any], want: str) -> dict[str, Any]:
    """在真实执行结果里按稳定标识定位一条测试。命中必须唯一。"""
    statuses = run.get("test_statuses") or {}
    hits = {name: status for name, status in statuses.items() if want in name}
    if len(hits) == 1:
        name, status = next(iter(hits.items()))
        return {"want": want, "found": True, "unique": True, "test": name, "status": status,
                "passed": status == "passed"}
    return {
        "want": want,
        "found": bool(hits),
        "unique": False,
        "hit_count": len(hits),
        "hits": sorted(hits),
        "status": None,
        "passed": False,
    }


# ════════════════════════════════════════════════════════════════════════════
# §10 逻辑级现算判据（每条结论配一条，教训 17）
# ════════════════════════════════════════════════════════════════════════════


def build_logic_checks(
    *,
    bridge: Mapping[str, Any],
    keys: Mapping[str, Any],
    orders: Mapping[str, Any],
    entities: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """把四组现算结果切成逐不变量可引用的判据。"""
    order_by_scenario = {row["scenario"]: row for row in orders["chains"]}
    checks: dict[str, dict[str, Any]] = {
        "bridge_state_domain": {
            "recomputed_from": BRIDGE_MACHINE_REL,
            "state_count": bridge["state_count"],
            "ac_11_2_required_count": bridge["ac_11_2_required_count"],
            "ac_11_2_missing_from_domain": bridge["ac_11_2_missing_from_domain"],
            "terminal_states": bridge["terminal_states"],
            "passed": not bridge["ac_11_2_missing_from_domain"]
            and bridge["ac_11_2_required_count"] == 19
            and bridge["state_count"] >= 19,
        },
        "bridge_state_text": {
            "recomputed_from": BRIDGE_MACHINE_REL,
            "state_text_entries": bridge["state_text_entries"],
            "states_without_text": bridge["states_without_text"],
            "duplicate_state_texts": bridge["duplicate_state_texts"],
            "states_with_forbidden_success_text": bridge["states_with_forbidden_success_text"],
            "four_ac_11_3_texts_distinct": bridge["four_ac_11_3_texts_distinct"],
            "passed": not bridge["states_without_text"]
            and not bridge["duplicate_state_texts"]
            and not bridge["states_with_forbidden_success_text"]
            and bridge["four_ac_11_3_texts_distinct"],
        },
        "legacy_mode_key_coverage": {
            "recomputed_from": "audit-platform/frontend/src/**（现扫 localStorage 键字面量并按真实"
                               "拼接式重建键形态）",
            "migration_regex_source": keys["migration_regex_source"],
            "dual_mode_constant_total": keys["dual_mode_constant_total"],
            "covered_count": keys["covered_count"],
            "uncovered_count": keys["uncovered_count"],
            "uncovered_literals": [row["literal"] for row in keys["uncovered"]],
            # 🔴 本条**不要求 uncovered=0**：那是存量缺口（登记为 BP），本条要求的是
            # 「分母非空 + 覆盖判定真的会区分」。分母为空会让覆盖率恒 100%（假绿第⑥源）。
            "passed": keys["dual_mode_constant_total"] > 0 and keys["covered_count"] > 0,
        },
        "three_entities_crash": {
            "recomputed_from": "vitest 导出的真实观测带 crash_recovery",
            **entities["crash"],
            "passed": bool(entities["crash"]["three_entities_zero"]),
        },
        "three_entities_claim": {
            "recomputed_from": "vitest 导出的真实观测带 recovery_claim",
            **entities["claim"],
            "passed": bool(entities["claim"]["three_entities_zero_before_claim"])
            and bool(entities["claim"]["operation_probe_after_claim"]),
        },
        "three_entities_download_only": {
            "recomputed_from": "vitest 导出的真实观测带 recovery_download_only",
            **entities["download_only"],
            "passed": bool(entities["download_only"]["three_entities_zero"]),
        },
    }
    for scenario, row in order_by_scenario.items():
        checks[f"order_{scenario}"] = {
            "recomputed_from": f"vitest 导出的真实观测带 {scenario}",
            "trace_present": row.get("trace_present"),
            "verdict": row.get("verdict"),
            "all_arms_flip_to_red": row.get("all_arms_flip_to_red"),
            "forward_recompute_accepts_correct_order": row.get(
                "forward_recompute_accepts_correct_order"
            ),
            "forward_recompute_rejects_missing_marker": row.get(
                "forward_recompute_rejects_missing_marker"
            ),
            "passed": bool(row.get("ok"))
            and bool(row.get("all_arms_flip_to_red"))
            and bool(row.get("forward_recompute_accepts_correct_order"))
            and bool(row.get("forward_recompute_rejects_missing_marker")),
        }
    return checks


# ════════════════════════════════════════════════════════════════════════════
# §11 反事实多臂 + 正向重算（对本门自己的纯判据）
# ════════════════════════════════════════════════════════════════════════════


def counterfactual_arms(
    *,
    graph: ImportGraph,
    keys: Mapping[str, Any],
    bridge: Mapping[str, Any],
) -> dict[str, Any]:
    """逐条把前提在**内存里**移除：结论不变 ⇒ 该判据度量的是别的东西（教训 13）。"""
    arms: list[dict[str, Any]] = []

    # ① 可达性判据：往内存图里注入一个「生产文件 import 了 editor host」的边 ⇒ 可达性必须翻
    host_rel = rel(SYNC_DIR / "WorkpaperSyncEditorHost.vue")
    baseline = replacement_reachability(graph)
    baseline_unreachable = set(baseline["unreachable_from_production_host"])
    poisoned = ImportGraph(
        surface=list(graph.surface),
        edges={
            **graph.edges,
            "audit-platform/frontend/src/components/workpaper/GtSyntheticHost.vue": [host_rel],
        },
        scanned_files=graph.scanned_files,
    )
    poisoned_unreachable = set(replacement_reachability(poisoned)["unreachable_from_production_host"])
    arms.append(
        {
            "id": "reachability_flips_when_a_production_importer_appears",
            "premise_removed": f"内存里给 {host_rel} 加一个生产 importer",
            "baseline_unreachable_count": len(baseline_unreachable),
            "poisoned_unreachable_count": len(poisoned_unreachable),
            "conclusion_changed": host_rel in baseline_unreachable
            and host_rel not in poisoned_unreachable,
        }
    )

    # ② 迁移正则判据：把 `-dual-mode:` 换成一个不可能命中的片段 ⇒ 覆盖数必须塌到 0
    pattern = re.compile(keys["migration_regex_source"])
    forms = [form for row in keys["rows"] if row["is_dual_mode_surface"] for form in row["key_forms"]]
    real_hits = sum(1 for form in forms if pattern.match(form))
    broken = re.compile(keys["migration_regex_source"].replace("-dual-mode:", "-NEVER-MATCH:"))
    broken_hits = sum(1 for form in forms if broken.match(form))
    arms.append(
        {
            "id": "migration_coverage_collapses_when_the_regex_body_changes",
            "premise_removed": "把迁移正则里的 `-dual-mode:` 改成不可能命中的片段",
            "baseline_hits": real_hits,
            "poisoned_hits": broken_hits,
            "conclusion_changed": real_hits > 0 and broken_hits == 0,
        }
    )

    # ③ 键形态重建判据：把「`PREFIX + wpId`」这条拼接规则去掉 ⇒ 分母必须缩小
    sample_path = REPO / "audit-platform/frontend/src/components/workpaper/composables/useF1DualMode.ts"
    if sample_path.exists():
        sample_text = read_text(sample_path)
        with_concat = reconstruct_key_forms(sample_text, "STORAGE_PREFIX", "f1-dual-mode:")
        without_concat = reconstruct_key_forms(
            sample_text.replace("STORAGE_PREFIX + wpId.value", "someOtherThing"),
            "STORAGE_PREFIX",
            "f1-dual-mode:",
        )
        arms.append(
            {
                "id": "key_form_reconstruction_depends_on_the_concat_rule",
                "premise_removed": "把源码里的 `PREFIX + wpId` 拼接改掉",
                "baseline_forms": with_concat,
                "poisoned_forms": without_concat,
                "conclusion_changed": with_concat != without_concat,
            }
        )
    else:
        arms.append(
            {
                "id": "key_form_reconstruction_depends_on_the_concat_rule",
                "premise_removed": "样本文件缺失",
                "conclusion_changed": False,
            }
        )

    # ④ AC 11.2 判据：内存里从状态域里删掉一个必需状态 ⇒ 缺项判据必须翻红
    reduced = [state for state in bridge["states"] if state != "recovery_download_only"]
    missing_after = [state for state in bridge["ac_11_2_required_states"] if state not in reduced]
    arms.append(
        {
            "id": "ac_11_2_check_flips_when_a_required_state_disappears",
            "premise_removed": "内存里从状态域删掉 recovery_download_only",
            "baseline_missing": bridge["ac_11_2_missing_from_domain"],
            "poisoned_missing": missing_after,
            "conclusion_changed": not bridge["ac_11_2_missing_from_domain"] and bool(missing_after),
        }
    )

    # ⑤ 文案判据：内存里把两个状态的文案改成同一句 ⇒ 重复判据必须翻红
    text_values = {"applied": "同一句", "conflict": "同一句"}
    duplicates = sorted(
        {value for value in text_values.values() if list(text_values.values()).count(value) > 1}
    )
    arms.append(
        {
            "id": "duplicate_text_check_flips_when_two_states_share_one_sentence",
            "premise_removed": "内存里把 applied 与 conflict 的文案改成同一句",
            "baseline_duplicates": bridge["duplicate_state_texts"],
            "poisoned_duplicates": duplicates,
            "conclusion_changed": not bridge["duplicate_state_texts"] and bool(duplicates),
        }
    )

    return {
        "arms": arms,
        "arm_count": len(arms),
        "all_arms_change_conclusion": all(arm["conclusion_changed"] for arm in arms),
        "why": "反事实多臂只能证明「判据非重言」；它抓不到「结论恒真」——那由 forward_recompute "
               "另外证（教训 15）。",
    }


def forward_recompute() -> dict[str, Any]:
    """对**合成的已知答案**正向跑一遍每个纯判据（教训 15：只有反事实不够）。"""
    rows: list[dict[str, Any]] = []

    # ① 顺序判据：正序必过、逆序必不过、缺项必不过
    chain = ("net:a", "net:b", "net:c")
    good = [{"seq": i, "kind": "net", "name": n.split(":")[1]} for i, n in enumerate(chain)]
    bad = list(reversed(good))
    short = good[:2]
    rows.append(
        {
            "id": "judge_order_on_synthetic_inputs",
            "accepts_correct": judge_order(good, chain)["ok"],
            "rejects_reversed": not judge_order(bad, chain)["ok"],
            "rejects_missing": not judge_order(short, chain)["ok"],
            "passed": judge_order(good, chain)["ok"]
            and not judge_order(bad, chain)["ok"]
            and not judge_order(short, chain)["ok"],
        }
    )

    # ② 三实体判据：干净观测带必过、注入 forcesave 必不过
    clean = [
        {"seq": 1, "kind": "net", "name": "list_recovery_cases"},
        {"seq": 2, "kind": "net", "name": "claim_recovery_case"},
    ]
    dirty = [{"seq": 0, "kind": "net", "name": "request_forcesave"}, *clean]
    rows.append(
        {
            "id": "three_entity_verdict_on_synthetic_inputs",
            "accepts_clean": _three_entity_verdict("claim", clean),
            "rejects_injected": not _three_entity_verdict("claim", dirty),
            "passed": _three_entity_verdict("claim", clean)
            and not _three_entity_verdict("claim", dirty),
        }
    )

    # ③ 迁移正则：三个已知答案的键形态
    pattern = re.compile(legacy_migration_regex())
    cases = {
        "f1-dual-mode:wp123": True,
        "l1-dual-mode-wp123": False,
        "f4-ap-mode:wp123": False,
        "n3-dual-mode": False,
        "g14-dual-mode:wp123:sheetA": True,
    }
    observed = {key: bool(pattern.match(key)) for key in cases}
    rows.append(
        {
            "id": "migration_regex_on_synthetic_keys",
            "expected": cases,
            "observed": observed,
            "passed": observed == cases,
        }
    )

    # ④ 数组/映射提取器：对合成 TS 片段必须给出已知答案
    snippet = (
        "export const SAMPLE_STATES = [\n  'a',\n  'b',\n] as const\n"
        "export const SAMPLE_TEXT: Readonly<Record<string, string>> = Object.freeze({\n"
        "  a: '甲',\n  b: '乙',\n})\n"
    )
    rows.append(
        {
            "id": "ts_literal_extractors_on_synthetic_source",
            "array": _extract_string_array(snippet, "SAMPLE_STATES"),
            "record": _extract_record_literal(snippet, "SAMPLE_TEXT"),
            "passed": _extract_string_array(snippet, "SAMPLE_STATES") == ["a", "b"]
            and _extract_record_literal(snippet, "SAMPLE_TEXT") == {"a": "甲", "b": "乙"},
        }
    )

    # ⑤ 键形态重建器：对合成源必须重建出三种形态
    synthetic = (
        "const STORAGE_PREFIX = 'x-dual-mode:'\n"
        "localStorage.getItem(STORAGE_PREFIX + wpId.value)\n"
    )
    rows.append(
        {
            "id": "key_form_reconstruction_on_synthetic_source",
            "forms": reconstruct_key_forms(synthetic, "STORAGE_PREFIX", "x-dual-mode:"),
            "passed": reconstruct_key_forms(synthetic, "STORAGE_PREFIX", "x-dual-mode:")
            == [f"x-dual-mode:{_PLACEHOLDER}"],
        }
    )

    return {
        "rows": rows,
        "row_count": len(rows),
        "all_passed": all(row["passed"] for row in rows),
        "why": "反事实臂证明判据不是重言；本节证明判据也不是恒真 —— 对已知答案的合成输入，"
               "它必须给出那个答案（含必须拒绝的那几个）。",
    }


# ════════════════════════════════════════════════════════════════════════════
# §12 Property 落点与档位
# ════════════════════════════════════════════════════════════════════════════

#: 每条 Property 的档位裁决。
#:
#: * ``independently_expressed`` —— 本门在自己的独立文件里**重新表达**了这条不变量。
#: * ``partially_expressed`` —— 客户端半边重新表达了，另半边（真浏览器 / 服务端 timeline）
#:   结构上不在本门范围内，owner 另有其人。
#:
#: 🔴 一条都不许标成「跑了实现任务的测试所以算验过」—— 那是第二档，本门不用它冒充第一档。
PROPERTY_TIERS: Final[dict[int, dict[str, Any]]] = {
    8: {"tier": "independently_expressed"},
    11: {
        "tier": "partially_expressed",
        "verified_here": "唯一 descriptor 才挂载、组件不再请求 config、ready 后才 confirm、"
                         "confirm 未解锁不得 editing、篡改的编辑器侧 forcesave 拒绝挂载",
        "not_verified_here": "「candidate descriptor 必须拒绝」在前端侧没有可观测面 —— 前端 DTO "
                             "不解析 representation 的 candidate 状态，服务端根本不下发 candidate "
                             "descriptor（`resolver/room/current` 不读 candidate 由后端把守）。",
        "owner_of_remainder": "70",
    },
    12: {"tier": "independently_expressed"},
    13: {"tier": "independently_expressed"},
    14: {"tier": "independently_expressed"},
    15: {
        "tier": "partially_expressed",
        "verified_here": "撤权/未解锁时不得 forcesave；leader promotion 前失权先显示 "
                         "authorization-stale、合法 successor 接任后 generation 不变、无 successor "
                         "进入 recovery-required 且停止 loading/禁止成功文案（正文点名的独立挂载验证）",
        "not_verified_here": "服务端侧 room-lock reconciler 的 eligibility snapshot / generation "
                             "supersede 由上游后端独立回归（任务 68）在真实 PostgreSQL 上验；"
                             "前端观测不到 room row lock。",
        "owner_of_remainder": "68",
    },
    35: {
        "tier": "partially_expressed",
        "verified_here": "冲突面板的 DOM 侧可追溯字段（JSON Pointer / OO 位置 / base-current-"
                         "incoming / kind）在本门的冲突预览判据里逐项断言非空。",
        "not_verified_here": "「OO cell/XPath 真的指到那个单元格」需要真实 OO 文档打开后比对，"
                             "属真实 OO 场景。",
        "owner_of_remainder": "70",
    },
    46: {"tier": "independently_expressed"},
    47: {"tier": "independently_expressed"},
    48: {"tier": "independently_expressed"},
    58: {
        "tier": "partially_expressed",
        "verified_here": "客户端半边的联合时序：flush→commit→descriptor mounted→ready→confirm，"
                         "以及 recovery 的 incoming durable 之后 list→claim（三实体在 claim 前为 0）"
                         "或 download-only（三者为 0）。判据落在**真实观测带的下标**上。",
        "not_verified_here": "服务端 timestamp / application-bound / sequence-fold event 的联合"
                             "timeline 需要真实后端与真实 OO；前端观测不到服务端时间。",
        "owner_of_remainder": "70",
    },
}


def build_property_landings(
    invariant_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    structural_errors: list[str] = []
    for number in DECLARED_PROPERTIES:
        landing = [row for row in invariant_rows if number in row["properties"]]
        tier = PROPERTY_TIERS.get(number)
        if tier is None:
            structural_errors.append(f"Property {number} 未裁决档位")
            continue
        if not landing:
            structural_errors.append(f"Property {number} 没有任何不变量落点")
        rows.append(
            {
                "property": f"Property {number}",
                "number": number,
                "owner_task": OWNER_TASK,
                "invariants": [row["id"] for row in landing],
                "invariant_count": len(landing),
                "all_landings_passed": bool(landing) and all(row["passed"] for row in landing),
                **tier,
            }
        )
    declared = {row["number"] for row in rows}
    if declared != set(DECLARED_PROPERTIES):
        structural_errors.append(
            f"落点表覆盖 {sorted(declared)} ≠ 正文声明 {sorted(DECLARED_PROPERTIES)}"
        )
    return {
        "declared_count": len(DECLARED_PROPERTIES),
        "rows": rows,
        "tier_counts": {
            tier: sum(1 for row in rows if row["tier"] == tier)
            for tier in sorted({row["tier"] for row in rows})
        },
        "structural_errors": structural_errors,
    }


# ════════════════════════════════════════════════════════════════════════════
# §13 立即失败清单 / 档位切分 / BP
# ════════════════════════════════════════════════════════════════════════════


def build_immediate_failures(invariant_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for failure_id in IMMEDIATE_FAILURE_IDS:
        landing = [row for row in invariant_rows if row.get("immediate_failure") == failure_id]
        rows.append(
            {
                "id": failure_id,
                "invariants": [row["id"] for row in landing],
                "invariant_count": len(landing),
                "judged_by": "真实挂载后的 DOM/行为 + 真实 network 序列",
                "not_judged_by": "import / 字符串存在（正文逐字禁止）",
                "passed": bool(landing) and all(row["passed"] for row in landing),
            }
        )
    missing = [row["id"] for row in rows if row["invariant_count"] == 0]
    return {
        "declared_count": len(IMMEDIATE_FAILURE_IDS),
        "rows": rows,
        "without_judgement": missing,
        "all_passed": all(row["passed"] for row in rows) and not missing,
    }


def build_verification_tiers(reachability: Mapping[str, Any]) -> dict[str, Any]:
    """把「组件级独立挂载已验」与「生产宿主链路已验」明确切成两档。"""
    host_rel = rel(SYNC_DIR / "WorkpaperSyncEditorHost.vue")
    bridge_rel = rel(SYNC_DIR / "useWorkpaperSyncBridge.ts")
    host_row = next(
        (row for row in reachability["modules"] if row["module"] == host_rel), None
    )
    bridge_row = next(
        (row for row in reachability["modules"] if row["module"] == bridge_rel), None
    )
    return {
        "component_level_mount": {
            "state": "verified",
            "how": "本门的独立 spec 真实 `mount(WorkpaperSyncEditorHost)` + 真桥 + 真 API 层 + "
                   "真 DocEditor 构造观测；正文第 1 子条目逐字授权「另独立挂载验证」。",
            "editor_host_production_importers": (host_row or {}).get(
                "production_importers_outside_surface", []
            ),
        },
        "production_host_chain": {
            "state": "not_verified_here",
            "why": "替代面 19/22 从生产文件不可达 —— `WorkpaperSyncEditorHost.vue` 与 "
                   "`useWorkpaperSyncBridge.ts` 的生产 importer 实测为 0，生产 `Gt*.vue` 宿主"
                   "根本没有 import 它们。AC 11.12「在真实渲染宿主做 DOM 与 API 顺序测试」的"
                   "「生产宿主」那一档因此**不成立**，且正文未授权本门改宿主（那 ~51 个文件"
                   "是并发在途禁碰面）。",
            "editor_host_reachable": bool((host_row or {}).get("reachable_from_production_host")),
            "bridge_reachable": bool((bridge_row or {}).get("reachable_from_production_host")),
            "owner_of_remainder": "72",
            "blocking_point": "BP-69-1",
        },
        "why_two_tiers": "把两者压成一句「宿主与 DOM 已回归」是本任务最容易翻车的一处：组件级"
                        "全绿不代表审计师在生产界面上走的是这条链路。",
    }


def build_blocking_points(
    *,
    reachability: Mapping[str, Any],
    cross_check: Mapping[str, Any],
    keys: Mapping[str, Any],
    invariant_rows: Sequence[Mapping[str, Any]],
    upstream_reruns: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """本门发现/转报的阻塞点。id 用 task-scoped 前缀 `BP-69-n`（守卫用 fullmatch 锁死）。"""
    host_rel = rel(SYNC_DIR / "WorkpaperSyncEditorHost.vue")
    bridge_rel = rel(SYNC_DIR / "useWorkpaperSyncBridge.ts")
    rows: list[dict[str, Any]] = [
        {
            "id": "BP-69-1",
            "subject": "replacement_surface_unreachable_from_production_hosts",
            "statement": f"替代面 {reachability['unreachable_count']}/{reachability['surface_module_count']} "
                         "个模块从替代面目录之外的生产文件不可达（含 editor host 与 bridge）"
                         "⇒ AC 11.12 的「生产宿主」档不成立。",
            "measured": True,
            "measured_how": "本门独立复算前端 import 图（扫 "
                            f"{reachability['scanned_frontend_files']} 个 ts/vue），"
                            f"{host_rel} 与 {bridge_rel} 的生产 importer 实测为 0。",
            "independently_confirmed_by": [
                f"{GUARD_SPEC_REL}::[T69-I02]（组件级独立挂载真的能跑起来 ⇒ 零 importer 不是"
                "「模块坏了」而是「没人接」）",
            ],
            "cross_check_with_upstream_deletion_plan": {
                "agrees": cross_check.get("agrees"),
                "upstream_unreachable_count": cross_check.get("upstream_unreachable_count"),
                "recomputed_unreachable_count": cross_check.get("recomputed_unreachable_count"),
                "disagreeing_modules": cross_check.get("disagreeing_modules"),
            },
            "disposition": "reported_forward_unchanged",
            "relation_to_upstream": "上游 legacy 删前清册（任务 66）与 structural pre-reconcile"
                                    "（任务 67）已各自登记过同一事实并判「如实报告、未解除」；"
                                    "本门独立复算得到同一数字，**转报、未解除**。",
            "owner_task": "72",
            "why_not_fixed_here": "接宿主要改 `components/workpaper/` 下 ~51 个并发在途文件，"
                                  "正文未授权，且会改 source commit 让 Task 70 的 evidence stale。",
        },
        {
            "id": "BP-69-2",
            "subject": "legacy_mode_key_forms_outside_migration_regex",
            "statement": f"dual-mode 侧 {keys['dual_mode_constant_total']} 个模式键常量里，"
                         f"{keys['uncovered_count']} 个的真实键形态不被统一迁移正则 "
                         f"`{keys['migration_regex_source']}` 覆盖 ⇒ 这些底稿的存量偏好永远迁不过来。",
            "measured": True,
            "measured_how": "现扫前端全部 ts/vue 的 localStorage 键字面量，按源码真实拼接式"
                            "（模板串 / `+` 拼接 / 裸常量）重建键形态，再逐条问迁移正则。",
            "uncovered": keys["uncovered"],
            "two_distinct_gap_kinds": {
                "separator_or_naming_drift": [
                    row["literal"]
                    for row in keys["uncovered"]
                    if not row["also_missing_wp_segment"]
                ],
                "bare_global_key_without_wp_segment": [
                    row["literal"] for row in keys["uncovered"] if row["also_missing_wp_segment"]
                ],
            },
            "why_the_second_kind_is_worse": "裸全局键（如 `n3-dual-mode`）连 wp 段都没有 —— 同一"
                                            "浏览器里所有底稿共用一个偏好，迁移正则不可能命中，"
                                            "而 AC 11.8 要求按 entry/wp/sheet 分键。",
            "independently_confirmed_by": [
                f"{GUARD_SPEC_REL}::[T69-I05]（统一键三段齐备 + capability 回落真的生效）",
            ],
            "disposition": "reported_not_fixed",
            "owner_task": "72",
            "why_not_fixed_here": "改这 10 处旧 composable 属 Stage B 精确删除的范围；本门是"
                                  "回归验证，不改生产代码。",
        },
        {
            "id": "BP-69-3",
            "subject": "refresh_required_reopen_has_no_runtime_producer",
            "statement": "转换表声明了 `refresh_required --descriptor_received--> rematerializing "
                         "--descriptor_accepted--> oo_loading`，但桥里唯一会 apply "
                         "`descriptor_received` 的公开动作是 `switchToOnlyOffice()`，而它第一步 "
                         "`flush_started` 在 `refresh_required` 上没有出边 ⇒ `rematerializing` "
                         "在运行时不可达，正文点名的「refresh-required reopen」目前只能靠整页重挂。",
            "measured": True,
            "measured_how": "真实执行：在 refresh_required 上调 `switchToOnlyOffice()` 必抛且零"
                            "新增网络调用；此时推新 descriptor 会让桥拒绝 `editor_mounted`，"
                            "宿主落成可见失败（stage=notify_editor_mounted）。",
            "independently_confirmed_by": [f"{GUARD_SPEC_REL}::[T69-I10]"],
            "disposition": "reported_not_fixed",
            "owner_task": "72",
            "why_not_fixed_here": "补 reopen 入口要改 `useWorkpaperSyncBridge.ts` 生产代码；"
                                  "本门只做独立回归。",
        },
        {
            "id": "BP-69-4",
            "subject": "incoming_durable_event_cannot_carry_incoming_artifact_digest",
            "statement": "`incomingDurable` 事件的 `artifactSha256` 只能为 null —— "
                         "`GET .../operations/{id}` 的投影里没有 incoming artifact digest（只有 "
                         "application 的 bundle/authority digest）。拿 descriptor 的 "
                         "`artifactSha256` 顶替会让「回传文件与我发出去的是同一份」凭空成立。",
            "measured": True,
            "measured_how": "真实执行：观测到的 incoming-durable 载荷 artifactSha256 恒为 null，"
                            "operationId 为 requested id。",
            "independently_confirmed_by": [f"{GUARD_SPEC_REL}::[T69-I32]"],
            "disposition": "reported_not_fixed",
            "owner_task": "70",
            "why_not_fixed_here": "补投影要改后端 operation DTO；且「同一份」这个结论本身要靠"
                                  "真实 OO 回传才能验。",
        },
        {
            "id": "BP-69-5",
            "subject": "no_real_browser_in_this_gate",
            "statement": "本门在 vitest + jsdom 里跑，不是真浏览器；AC 14.8 要求的「浏览器 "
                         "network/console 与后端 timeline、数据库时间联合」只完成了客户端半边。",
            "measured": True,
            "measured_how": "环境实测：3030 端口未监听；本门刻意不起 dev server，也不跑 Playwright。",
            "disposition": "reported_scope_boundary",
            "owner_task": "70",
            "why_not_fixed_here": "正文第 3 子条目要求的是 DOM/network 顺序判据，未要求真浏览器；"
                                  "真实 OO 9.4 全 entry 场景刷新是 Task 70 的准则。",
        },
        {
            "id": "BP-69-6",
            "subject": "upstream_byte_lock_freezes_a_test_directory_census",
            "statement": "上游后端独立回归把 `" + UPSTREAM_CENSUS_DIR + "` 的**目录普查**"
                         "（`in_dir_but_out_of_surface` = 目录内不引用被验生产单元的测试文件清单）"
                         "冻结进了自己的逐字节锁 ⇒ 任何人往那个目录新增一个这类测试文件，"
                         "上游就打红 1~3 条守卫，而表象是「上游报告过期」，看上去像别人的问题。"
                         "Tasks 70/71/72 都还要往那儿加测试文件，会各自再撞一次。",
            "measured": True,
            "measured_how": "本轮实测三段因果：①守卫放在该目录且含上游 `sync_package_path` 模式的"
                            "包路径字面量 ⇒ 上游 3 红（辐射面 digest 不可复算 / surface_size 等 6 个"
                            "字段不可复算 / 现算判定与磁盘不一致）；②改写引用形式去掉字面量 ⇒ 2 条"
                            "转绿，剩 1 条（`in_dir_but_out_of_surface` 多了本文件）；"
                            "③把守卫移出该目录 ⇒ 上游全绿。每段都真跑上游守卫取证。",
            "independently_confirmed_by": [
                "guard_placement（本门现算：守卫路径不在普查目录内 + 守卫里零触发字面量，"
                "两条都从上游门源码现读模式字面量后判定）",
            ],
            "disposition": "reported_not_fixed",
            "owner_task": "68/72",
            "why_not_fixed_here": "上游产物（门 + 报告 + 守卫）在本 spec 里明令禁改；本门只能靠"
                                  "**放置位置**规避，并把规避本身做成现算判据，避免后人无声挪回去。",
        },
        {
            "id": "BP-69-7",
            "subject": "frontend_full_suite_baseline_is_not_reproducible",
            "statement": "整套前端 vitest 的既存红**逐轮不同**：本会话两次全套真跑分别得 534 与 "
                         "532 条失败（同一 source commit、同一命令）⇒ 存量红里有一批是 flaky。"
                         "任何「全套失败数」型的门槛都会随机红/绿，Task 72 Stage D 的五个零门若"
                         "把它当判据会不可靠。",
            "measured": True,
            "measured_how": "本会话对同一 commit 跑了两次 `npm exec -- vitest run`（无过滤器）："
                            "第一次 32705 tests / 534 failed，第二次 32706 tests / 532 failed"
                            "（第二次多 1 条 = 本门自己新增的 I34）。逐条清单见报告 "
                            "`frontend_baseline.failures`（记录的是第二次那轮）。",
            "why_it_does_not_affect_this_gate": "本门的判定只要求「本门判据面在全套里 0 红」与"
                                                "「按引用关系现算的辐射面 0 红」，不要求全套清零；"
                                                "两条都不受 flaky 存量红影响。",
            "disposition": "reported_not_fixed",
            "owner_task": "72",
            "why_not_fixed_here": "定位 flaky 需要逐 suite 复跑并改生产/测试代码，正文未授权，"
                                  "且会改 source commit 让 Task 70 的 evidence stale。",
        },
    ]
    failed = [row["id"] for row in invariant_rows if not row["passed"]]
    if failed:
        rows.append(
            {
                "id": f"BP-69-{len(rows) + 1}",
                "subject": "failed_invariants_in_this_gate",
                "statement": f"本门有 {len(failed)} 条不变量未通过：{failed}",
                "measured": True,
                "disposition": "open",
                "owner_task": OWNER_TASK,
            }
        )
    stale = [
        name
        for name, row in (upstream_reruns.get("results") or {}).items()
        if not row.get("passed")
    ]
    if stale:
        rows.append(
            {
                "id": f"BP-69-{len(rows) + 1}",
                "subject": "upstream_byte_locks_broken_by_this_gate",
                "statement": f"上游逐字节锁复跑不过：{stale} —— 本门往 backend/data 写产物时"
                             "触发了上游报告的入向扫描。",
                "measured": True,
                "disposition": "open",
                "owner_task": OWNER_TASK,
            }
        )
    return rows


# ════════════════════════════════════════════════════════════════════════════
# §14 上游逐字节锁复跑（本门往 backend/data 写产物，必须证明没打红上游）
# ════════════════════════════════════════════════════════════════════════════


def outside_census_dir(path_rel: str) -> bool:
    """某个仓库相对路径是否落在上游冻结的那份目录普查**之外**。

    🔴 抽成纯函数是为了能用**合成输入**正向重算：直接把 `outside_census_dir = True` 写死时，
    当前世界的取值本来就是 True ⇒ 报告一字不变 ⇒ 只读磁盘的判据全绿（教训 17，本轮变异
    实测过这条 GREEN）。有了纯函数，判据可以喂一个「就在普查目录里」的合成路径要求它返回
    False，写死常量立刻打红。
    """
    return not path_rel.startswith(UPSTREAM_CENSUS_DIR)


def guard_placement() -> dict[str, Any]:
    """现算判据：本门守卫必须真的落在上游普查目录**之外**，且它自己不带触发字面量。

    🔴 为什么这是判据而不是注释：上游那份逐字节锁把「普查目录内不引用被验生产单元的测试
    文件清单」冻结了。本门只要往那个目录放一个守卫，上游就打红 —— 而打红的表现是「上游报告
    过期」，看上去像别人的问题。把「不在那个目录」与「不含触发字面量」做成**现算**结论，
    未来任何人把文件挪回去、或在守卫里写回那个包路径字面量，本门自己先红。
    """
    guard_path = REPO / GUARD_TEST_REL
    text = read_text(guard_path) if guard_path.exists() else ""
    # 上游 `sync_package_path` 模式**现读上游门源码**取得（不在本门抄死第二份）。
    #
    # 🔴 走 AST 不走子串（教训 12）：首版用正则 `r"([^"]+)"` 取字面量，而上游那条模式里本身
    # 就有转义引号 `\"workpaper_sync\"` ⇒ 字符类提前收尾、整条取不到 ⇒ 判据静默失去输入
    # （本轮真跑时就是这个 blocker）。AST 拿到的是**求值后的字符串**，转义与拼接都不影响。
    upstream_gate = REPO / "backend/scripts/check/check_task68_backend_chain_independent_regression.py"
    pattern_literal = ""
    if upstream_gate.exists():
        for node in ast.walk(ast.parse(read_text(upstream_gate))):
            if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
                continue
            head, tail = node.elts
            if (
                isinstance(head, ast.Constant)
                and head.value == "sync_package_path"
                and isinstance(tail, ast.Constant)
                and isinstance(tail.value, str)
            ):
                pattern_literal = tail.value
                break
    hits: list[int] = []
    if pattern_literal:
        compiled = re.compile(pattern_literal)
        hits = [
            index
            for index, line in enumerate(text.split("\n"), 1)
            if compiled.search(line)
        ]
    outside = outside_census_dir(GUARD_TEST_REL)
    return {
        "guard_test": GUARD_TEST_REL,
        "guard_test_exists": guard_path.exists(),
        "upstream_census_dir": UPSTREAM_CENSUS_DIR,
        "outside_census_dir": outside,
        "upstream_pattern_read_from": rel(upstream_gate),
        "upstream_pattern_literal": pattern_literal,
        "upstream_pattern_found": bool(pattern_literal),
        "trigger_literal_hit_lines": hits,
        "passed": guard_path.exists() and outside and not hits and bool(pattern_literal),
        "why": "本轮实测的完整因果链：①放在普查目录且守卫里写着上游那个包路径字面量 ⇒ 上游 3 红"
               "（辐射面不可复算 / surface_size 不可复算 / 现算判定与磁盘不一致）；②去掉字面量 ⇒ "
               "2 条转绿、剩 1 条纯目录成员红；③移出普查目录 ⇒ 上游全绿。见 BP-69-6。",
    }


def run_frontend_baseline() -> dict[str, Any]:
    """真跑一次**整套**前端 vitest 作为基线（旧数不可直接引用，必须自己实测）。

    与 `run_vitest` 的分工：那个只跑按引用关系现算出的辐射面；本函数跑全套，用来回答
    「本门的新文件有没有把别处打红」。既存红**如实登记不修**（它们不属本任务）。
    """
    with tempfile.TemporaryDirectory(prefix="task69_baseline_") as tmpdir:
        report_path = Path(tmpdir) / "baseline.json"
        command = f'npm exec -- vitest run --reporter=json --outputFile="{report_path}"'
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            ["cmd", "/c", command] if os.name == "nt" else ["sh", "-c", command],
            cwd=str(FRONTEND),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5400,
        )
        if not report_path.exists():
            tail = ((proc.stdout or "") + (proc.stderr or ""))[-1200:]
            return {"executed": False, "return_code": proc.returncode, "tail": tail}
        payload = json.loads(report_path.read_text(encoding="utf-8"))

    failures: list[dict[str, str]] = []
    for suite in payload.get("testResults") or []:
        suite_rel = str(suite.get("name") or "").replace("\\", "/")
        if str(REPO).replace("\\", "/") in suite_rel:
            suite_rel = suite_rel.split(str(REPO).replace("\\", "/") + "/", 1)[-1]
        for assertion in suite.get("assertionResults") or []:
            if str(assertion.get("status")) not in {"passed", "skipped", "todo", "pending"}:
                failures.append(
                    {
                        "suite": suite_rel,
                        "test": str(assertion.get("fullName") or assertion.get("title") or ""),
                        "status": str(assertion.get("status")),
                    }
                )
    return {
        "executed": True,
        "measured_by_this_gate": True,
        "how": "`npm exec -- vitest run`（全套，无过滤器），项目根 = audit-platform/frontend",
        "return_code": proc.returncode,
        "suite_total": payload.get("numTotalTestSuites"),
        "suite_failed": payload.get("numFailedTestSuites"),
        "test_total": payload.get("numTotalTests"),
        "test_passed": payload.get("numPassedTests"),
        "test_failed": payload.get("numFailedTests"),
        "test_skipped": payload.get("numPendingTests"),
        "failures": sorted(failures, key=lambda row: (row["suite"], row["test"])),
        "failed_suites": sorted({row["suite"] for row in failures}),
        "note": "既存红如实登记、**不修**（不属本任务；改生产代码会让 Task 70 的 evidence stale）。"
                "本门只要求「本门自己的判据面 0 红」与「既存红有归因」，不要求全套清零。",
        "wallclock_excluded": True,
    }


def rerun_upstream_locks(enabled: bool) -> dict[str, Any]:
    """复跑上游两份报告的逐字节锁守卫。

    🔴 为什么必须做：上游 structural pre-reconcile 的入向扫描会遍历 `backend/data`，
    产物里出现某些字面标记就会让它的清册变长、逐字节锁打红。本门的报告因此**刻意避开**
    那些字面形态（正文引用一律用中文「任务 NN」），并用真跑证明这条避让确实有效。
    """
    if not enabled:
        return {
            "executed": False,
            "why": "只在 --write --run-vitest 下真跑（数分钟）；--check 复用磁盘记录",
            "tests": list(UPSTREAM_LOCK_TESTS),
        }
    results: dict[str, Any] = {}
    for test in UPSTREAM_LOCK_TESTS:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", test, "-q", "--no-header", "--tb=line", "-p", "no:randomly"],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        summary = next(
            (line.strip() for line in reversed(out.splitlines()) if " passed" in line or " failed" in line),
            f"rc={proc.returncode}",
        )
        passed_match = re.search(r"(\d+) passed", summary)
        failed_match = re.search(r"(\d+) failed", summary)
        results[test] = {
            "summary": summary,
            "passed_count": int(passed_match.group(1)) if passed_match else -1,
            "failed_count": int(failed_match.group(1)) if failed_match else 0,
            "passed": proc.returncode == 0,
        }
    return {
        "executed": True,
        "results": results,
        "all_passed": all(row["passed"] for row in results.values()),
        "why": "本门往 backend/data 写报告；上游 structural pre-reconcile 的入向扫描遍历该目录，"
               "故收尾必须证明它的逐字节锁仍然过。",
    }


# ════════════════════════════════════════════════════════════════════════════
# §15 上游只读输入
# ════════════════════════════════════════════════════════════════════════════


def upstream_inputs() -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for label, path in (
        ("structural_pre_reconcile_report", UPSTREAM_STRUCTURAL_PATH),
        ("legacy_deletion_plan", UPSTREAM_DELETION_PLAN_PATH),
        ("backend_chain_regression_report", UPSTREAM_BACKEND_REGRESSION_PATH),
    ):
        if not path.exists():
            rows[label] = {"path": rel(path), "present": False}
            continue
        raw = path.read_bytes()
        rows[label] = {
            "path": rel(path),
            "present": True,
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "disposition": "read_only_input",
        }
    return rows


def upstream_dom_descriptor_denominators() -> dict[str, Any]:
    """从上游 structural 报告按 key 取 DOM/descriptor 两面的分母（不整读）。"""
    if not UPSTREAM_STRUCTURAL_PATH.exists():
        return {"available": False}
    record = read_json(UPSTREAM_STRUCTURAL_PATH)
    entries = record.get("entries") or []
    host_reachable = 0
    descriptor_observed = 0
    descriptor_consistency: dict[str, int] = {}
    room_consistency: dict[str, int] = {}
    mount_total = 0
    exposes_mode_switch = 0
    for entry in entries:
        landing = entry.get("host_dom_landing") or {}
        config = entry.get("descriptor_room_config") or {}
        descriptor = config.get("descriptor") or {}
        room = config.get("room") or {}
        if landing.get("host_reachable"):
            host_reachable += 1
        mount_total += int(landing.get("mount_count") or 0)
        if descriptor.get("observed"):
            descriptor_observed += 1
        if descriptor.get("exposes_mode_switch"):
            exposes_mode_switch += 1
        key = str(descriptor.get("consistency"))
        descriptor_consistency[key] = descriptor_consistency.get(key, 0) + 1
        rkey = str(room.get("consistency"))
        room_consistency[rkey] = room_consistency.get(rkey, 0) + 1
    return {
        "available": True,
        "consumed_keys": ["entries[].host_dom_landing", "entries[].descriptor_room_config"],
        "entry_total": len(entries),
        "host_reachable": host_reachable,
        "host_unreachable": len(entries) - host_reachable,
        "mount_total": mount_total,
        "descriptor_observed": descriptor_observed,
        "descriptor_exposes_mode_switch": exposes_mode_switch,
        "descriptor_consistency_counts": dict(sorted(descriptor_consistency.items())),
        "room_consistency_counts": dict(sorted(room_consistency.items())),
        "how_this_gate_uses_it": "作为「宿主与 DOM」面的**分母**：上游数的是 186 条 manifest entry "
                                "的挂载点与 descriptor 一致性；本门验的是那些挂载点最终要消费的"
                                "统一 descriptor/bridge 链路本身。两者不是同一个计数口径，"
                                "故本门不把上游的 186 当自己的分母，只引用它说明规模。",
    }


# ════════════════════════════════════════════════════════════════════════════
# §16 不变量求值 / 判定 / 报告组装
# ════════════════════════════════════════════════════════════════════════════


def evaluate_invariants(
    *,
    run: Mapping[str, Any],
    logic_checks: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for invariant in ALL_INVARIANTS:
        behaviour = find_test_status(run, invariant.want_test)
        if invariant.logic_key is None:
            logic: dict[str, Any] = {
                "state": "behaviour_only",
                "why": "这条不变量的判据形态就是真实挂载/真实调用序列本身，另造一个逻辑级复算"
                       "只会得到同一份观测的第二次抄写（additive 死代码）。",
                "passed": True,
            }
        else:
            check = logic_checks.get(invariant.logic_key)
            if check is None:
                logic = {
                    "state": "missing",
                    "logic_key": invariant.logic_key,
                    "passed": False,
                }
            else:
                logic = {"state": "recomputed", "logic_key": invariant.logic_key, **check}
        rows.append(
            {
                "id": invariant.id,
                "sub_bullet": invariant.sub_bullet,
                "statement": invariant.statement,
                "properties": list(invariant.properties),
                "requirements": list(invariant.requirements),
                "immediate_failure": invariant.immediate_failure,
                "behaviour_side": behaviour,
                "logic_side": logic,
                "passed": bool(behaviour["passed"]) and bool(logic.get("passed")),
            }
        )
    return rows


def build_verdict(report: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    declarations = report["task_declarations"]
    if not declarations["properties_match"]:
        blockers.append("正文 Property 声明与本门锁定的 11 条不一致")
    if not declarations["sub_bullet_count_match"]:
        blockers.append("正文子条目数与本门声明不一致")

    properties = report["properties"]
    if properties["structural_errors"]:
        blockers.extend(properties["structural_errors"])

    failed = [row["id"] for row in report["invariants"] if not row["passed"]]
    if failed:
        blockers.append(f"未通过的不变量：{failed}")

    immediate = report["immediate_failures"]
    if immediate["without_judgement"]:
        blockers.append(f"没有独立判据的立即失败项：{immediate['without_judgement']}")
    if not immediate["all_passed"]:
        blockers.append("立即失败清单里有未通过项")

    run = report["vitest_run"]
    if not run or not run.get("executed"):
        blockers.append("vitest 未真跑 —— 行为侧结论无来源")
    else:
        if run.get("matched_zero_suites"):
            blockers.append("vitest 匹配到 0 个 suite —— 过滤器写错，行为侧结论无来源")
        if run.get("test_failed"):
            blockers.append(f"vitest 有 {run['test_failed']} 条失败")
        if int(run.get("test_total") or 0) < len(ALL_INVARIANTS):
            blockers.append(
                f"vitest 实跑 {run.get('test_total')} 条 < 不变量数 {len(ALL_INVARIANTS)}"
            )

    orders = report["dom_network_order"]
    if not orders["all_ok"]:
        blockers.append("DOM/network 顺序判据未全部成立")
    if not orders["all_arms_flip"]:
        blockers.append("顺序判据的反事实臂没有全部翻红 ⇒ 判据可能是重言")
    if not orders["forward_recompute_ok"]:
        blockers.append("顺序判据的正向重算不成立 ⇒ 判据可能恒真")

    arms = report["counterfactual_arms"]
    if not arms["all_arms_change_conclusion"]:
        blockers.append("反事实多臂里有臂不改变结论 ⇒ 对应判据度量的是别的东西")
    forward = report["forward_recompute"]
    if not forward["all_passed"]:
        blockers.append("正向重算有未通过项")

    entities = report["three_entity_facts"]
    if not entities["all_ok"]:
        blockers.append("三实体结论（crash / claim / download-only）未全部成立")
    if not entities["all_arms_flip_to_red"]:
        blockers.append("三实体判据的反事实臂没有全部翻红")

    reachability_cross = report["reachability_cross_check"]
    if reachability_cross.get("available") and not reachability_cross.get("agrees"):
        blockers.append(
            f"与上游 deletion plan 的可达性登记不一致：{reachability_cross.get('disagreeing_modules')}"
        )

    locks = report["upstream_lock_reruns"]
    if locks.get("executed") and not locks.get("all_passed"):
        blockers.append("上游逐字节锁复跑不过 —— 本门产物打红了上游报告")

    placement = report["guard_placement"]
    if not placement["guard_test_exists"]:
        blockers.append(f"本门守卫不在声明位置：{placement['guard_test']}")
    if not placement["upstream_pattern_found"]:
        blockers.append("取不到上游辐射面模式字面量 ⇒ 「守卫不带触发字面量」这条无法现算")
    if not placement["outside_census_dir"]:
        blockers.append(
            f"本门守卫落在上游普查目录 {placement['upstream_census_dir']} 内 ⇒ 必打红上游逐字节锁"
        )
    if placement["trigger_literal_hit_lines"]:
        blockers.append(
            f"本门守卫里出现上游辐射面触发字面量（行 {placement['trigger_literal_hit_lines']}）"
        )

    baseline = report["frontend_baseline"]
    if baseline.get("executed"):
        own_spec_reds = [
            row for row in baseline.get("failures") or [] if GUARD_SPEC_REL.endswith(row["suite"])
            or row["suite"].endswith(GUARD_SPEC_REL.rsplit("/", 1)[-1])
        ]
        if own_spec_reds:
            blockers.append(f"全套基线里本门判据面自己有 {len(own_spec_reds)} 条红")
        if int(baseline.get("test_total") or 0) < int(report["vitest_run"].get("test_total") or 0):
            blockers.append("全套基线的测试数小于辐射面 ⇒ 基线跑的不是全套")

    bad_bp = [
        row["id"]
        for row in report["blocking_points"]
        if not re.fullmatch(r"BP-69-\d+", str(row.get("id")))
    ]
    if bad_bp:
        blockers.append(f"BP id 不符 task-scoped 前缀：{bad_bp}")

    result = RESULT_PASSED if not blockers else RESULT_FAILED
    return {
        "result": result,
        "blockers": blockers,
        "invariant_count": len(report["invariants"]),
        "invariants_passed": sum(1 for row in report["invariants"] if row["passed"]),
        "failed_invariants": failed,
        "property_tier_counts": properties["tier_counts"],
        "immediate_failure_count": immediate["declared_count"],
        "honest_scope": {
            "component_level_mount_verified": True,
            "production_host_chain_verified": False,
            "real_browser": False,
            "real_onlyoffice": False,
            "note": "本门的结论是「组件级独立挂载链路（真桥 + 真 API 层 + 真 DocEditor 构造 + 真 "
                    "DOM）在 vitest/jsdom 下逐条成立」。它**不等于**生产 Gt*.vue 宿主链路已验"
                    "（BP-69-1），也**不等于**真浏览器/真 OO 联合时序已验（BP-69-5，owner 70）。",
        },
    }


def build_report(
    *,
    run: Mapping[str, Any] | None = None,
    upstream_reruns: Mapping[str, Any] | None = None,
    frontend_baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    graph = build_import_graph()
    reachability = replacement_reachability(graph)
    cross_check = cross_check_reachability(reachability)
    keys = legacy_mode_key_coverage()
    bridge = bridge_state_surface()
    surface = radiation_surface(graph)
    vitest_run = dict(run) if run else {"executed": False}
    traces = vitest_run.get("traces") or {}
    orders = evaluate_order_chains(traces)
    entities = three_entity_facts(traces)
    logic_checks = build_logic_checks(bridge=bridge, keys=keys, orders=orders, entities=entities)
    invariant_rows = evaluate_invariants(run=vitest_run, logic_checks=logic_checks)
    properties = build_property_landings(invariant_rows)
    immediate = build_immediate_failures(invariant_rows)
    tiers = build_verification_tiers(reachability)
    locks = dict(upstream_reruns) if upstream_reruns else rerun_upstream_locks(False)
    placement = guard_placement()
    baseline = (
        dict(frontend_baseline)
        if frontend_baseline
        else {"executed": False, "why": "只在 --write --run-vitest 下真跑全套；--check 复用磁盘记录"}
    )

    artifacts = [
        rel(Path(__file__)),
        rel(OUTPUT_PATH),
        GUARD_SPEC_REL,
        GUARD_TEST_REL,
        "backend/scripts/diagnose/mutate_task69_frontend_regression_guards.py",
    ]

    report: dict[str, Any] = {
        "task": f"Task {TASK_NUMBER}",
        "spec": SPEC,
        "wave": 7,
        "schema_version": SCHEMA_VERSION,
        "owner_task": OWNER_TASK,
        "generated_by": rel(Path(__file__)),
        "source_commit": git_head(),
        "why_this_task_is_independent": {
            "task_text": "不得由实现任务自证；判据不以 import/字符串存在",
            "how": [
                "行为判据全在本门自己写的独立 spec 里跑：真实 `mount()` 宿主 + 真桥 + 真 API 层 + "
                "真 DocEditor 构造 + 真 DOM，唯一被替换的是平台 HTTP 面",
                "不 import 任何实现任务的 `__tests__` 夹具，自带 wire 级夹具工厂",
                "该 spec 把 network/editor/emit/DOM 的统一观测带导出，本门用 Python 重新实现同一套"
                "顺序与三实体判据在它上面现算一遍（两次独立计算）",
                "替代面可达性、legacy 键分母、辐射面、桥状态域与文案全部现算，不读上游的答案",
                "每条结论配反事实多臂（前提逐一移除）与正向重算（合成已知答案）",
            ],
            "what_is_not_claimed": "对无法在前端侧重新表达的半边（真浏览器/服务端 timeline/真实 OO "
                                   "位置比对），报告标 `partially_expressed` 并点名 owner，不把"
                                   "「跑了别人的测试」说成「我独立验过」。",
        },
        "sub_bullets": {str(key): value for key, value in SUB_BULLETS.items()},
        "task_declarations": task_declarations(),
        "design_property_titles": design_property_titles(),
        "upstream_inputs": upstream_inputs(),
        "upstream_dom_descriptor_denominators": upstream_dom_descriptor_denominators(),
        "replacement_reachability": reachability,
        "reachability_cross_check": cross_check,
        "legacy_mode_key_coverage": keys,
        "bridge_state_surface": bridge,
        "radiation_surface": surface,
        "vitest_run": vitest_run,
        "frontend_baseline": baseline,
        "guard_placement": placement,
        "dom_network_order": orders,
        "three_entity_facts": entities,
        "logic_checks": logic_checks,
        "counterfactual_arms": counterfactual_arms(graph=graph, keys=keys, bridge=bridge),
        "forward_recompute": forward_recompute(),
        "invariants": invariant_rows,
        "invariant_counts": {
            "total": len(invariant_rows),
            "passed": sum(1 for row in invariant_rows if row["passed"]),
            "by_sub_bullet": {
                str(bullet): sum(1 for row in invariant_rows if row["sub_bullet"] == bullet)
                for bullet in sorted({row["sub_bullet"] for row in invariant_rows})
            },
            "with_logic_recompute": sum(
                1 for row in invariant_rows if row["logic_side"]["state"] == "recomputed"
            ),
            "behaviour_only": sum(
                1 for row in invariant_rows if row["logic_side"]["state"] == "behaviour_only"
            ),
        },
        "immediate_failures": immediate,
        "properties": properties,
        "verification_tiers": tiers,
        "oo_scope_boundary": dict(OO_SCOPE_BOUNDARY),
        "preexisting_reds": {
            **PREEXISTING_RED_ATTRIBUTION,
            "frontend_failed_count_in_record": int(baseline.get("test_failed") or 0)
            if baseline.get("executed")
            else None,
            "frontend_failed_suite_count_in_record": len(baseline.get("failed_suites") or []),
        },
        "upstream_lock_reruns": locks,
        "artifact_git_status": git_porcelain(artifacts),
        "production_code_touched": {
            "frontend_production_files": [],
            "backend_production_files": [],
            "migrations": [],
            "note": "本门只新增判据面与门/守卫/变异脚本；发现的缺陷一律登记为 BP-69-n，不顺手修"
                    "（改 source commit 会让 Task 70 尚未刷新的 evidence 全部 stale）。",
        },
    }
    report["blocking_points"] = build_blocking_points(
        reachability=reachability,
        cross_check=cross_check,
        keys=keys,
        invariant_rows=invariant_rows,
        upstream_reruns=locks,
    )
    report["guard_placement"]["registered_as"] = "BP-69-6"
    report["verdict"] = build_verdict(report)
    report["report_digest"] = digest_of(
        {key: value for key, value in report.items() if key != "report_digest"}
    )
    return report


def render(report: Mapping[str, Any]) -> str:
    return stable_json(report, indent=2) + "\n"


# ════════════════════════════════════════════════════════════════════════════
# §17 CLI
# ════════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 69 前端独立回归门")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="现算并与磁盘逐字节比对")
    mode.add_argument("--write", action="store_true", help="现算并写盘")
    parser.add_argument(
        "--run-vitest",
        action="store_true",
        help="真跑辐射面 vitest（分钟级）并把真实执行结果与观测带写进报告；只在 --write 下有效",
    )
    args = parser.parse_args(argv)

    run: Mapping[str, Any] | None = None
    locks: Mapping[str, Any] | None = None
    baseline: Mapping[str, Any] | None = None
    if args.run_vitest:
        if not args.write:
            print("[Task69] --run-vitest 只能与 --write 同用", file=sys.stderr)
            return 2
        run = run_vitest(radiation_surface(build_import_graph()))
        # 旧的「887 passed」不可直接引用 —— 全套基线必须自己实测一次。
        baseline = run_frontend_baseline()
        # 本门往 backend/data 写报告 ⇒ 收尾必须证明上游两份报告的逐字节锁没被打红。
        locks = rerun_upstream_locks(True)
    elif OUTPUT_PATH.exists():
        existing = read_json(OUTPUT_PATH)
        run = existing.get("vitest_run")
        locks = existing.get("upstream_lock_reruns")
        baseline = existing.get("frontend_baseline")

    report = build_report(run=run, upstream_reruns=locks, frontend_baseline=baseline)
    rendered = render(report)
    verdict = report["verdict"]["result"]

    if args.write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUTPUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(rendered, encoding="utf-8")
        os.replace(tmp, OUTPUT_PATH)
        print(f"[Task69] 已写入 {rel(OUTPUT_PATH)} · verdict={verdict}")
    else:
        if not OUTPUT_PATH.exists():
            print(f"[Task69] 缺少 {rel(OUTPUT_PATH)}，先跑 --write", file=sys.stderr)
            return 2
        on_disk = read_text(OUTPUT_PATH)
        if on_disk != rendered:
            print(
                f"[Task69] 现算结果与 {rel(OUTPUT_PATH)} 不一致 —— 报告已过期或被手改",
                file=sys.stderr,
            )
            return 1
        print(f"[Task69] --check 通过 · verdict={verdict}")

    if verdict == RESULT_PASSED:
        return 0
    print(
        f"[Task69] verdict={verdict} · blockers={report['verdict']['blockers'][:4]}",
        file=sys.stderr,
    )
    return 1 if verdict == RESULT_FAILED else 3


if __name__ == "__main__":
    raise SystemExit(main())
