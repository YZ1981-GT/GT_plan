"""Task 66 —— legacy 删前清册 / 逐 entry replacement map / rollback 隔离门（`--check` / `--write`）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 66
Requirements: 1.4, 1.5, 1.7, 11.1, 11.2, 11.5, 11.8, 11.10, 12.7, 12.8, 12.9, 12.13, 12.14
Properties: **P3 / P46 / P47 / P48 / P51**

═══ 本任务为什么**只生成计划**、一个字节生产代码都不改 ═══

Task 66 正文逐字写着「不 feature-disable、不删除、不改调用点，避免在 Task 70 前改变
source commit 使 evidence stale」。evidence 的新鲜度由 source digest 锁定
（`evidence_freshness` / `manifest_source_digest`），本任务只要动一个生产文件，
Tasks 44/45/70 的全部 run 立刻 stale ⇒ Stage A 无从判定。

所以本脚本的产物是**清册**：七类 legacy 对象逐项现算，每项绑定
`replacement / owner / last_call_site / rollback_target / required_scenario_evidence`
五个字段，外加五个「必须唯一归属」形态的归属结论与 rollback 隔离门判定。
真正的删除动作归 Task 72 Stage B。

═══ 三边锁 ═══

1. **源码边（磁盘真读）** —— `audit-platform/frontend/src/**`（`.ts`/`.vue`）与
   `backend/app/routers/**` 现读：**先剥注释**再建 import 图（按 specifier 解析到
   真实文件），legacy 形态逐个现算。🔴 不剥注释会把
   `GtG7LongTermEquityMain.vue` 里那句注释「The actual bridge integration is provided
   by GtWpRenderer / WorkpaperSyncEditorHost.」算成一个消费方 ⇒
   `WorkpaperSyncEditorHost.vue` 的「零生产消费方」这条真结论会被这句**说明文字**
   打成假绿（教训 12 的原样复现）。
2. **替代面边（impl 现读）** —— `workpaperSyncModeStorage.LEGACY_KEY_RE`（旧键迁移
   覆盖面的真源，从 TS 源码里把正则字面量读出来再在 Python 侧编译）、
   `workpaper_sync.evidence.derive_for_manifest_entry`（required scenario 现算）、
   `entry_profile.load_entry_manifest`、`word_entry_gate` 的 `anchors_blocked`
   （`paragraph_index` 是否真的被门拒掉）、`wp_sync_router` 的统一端点清单（AST）。
3. **清册边（既有裁决现读）** —— `workpaper_sync_entry_manifest.json`（186 entry 的
   capability/resolver/host）、`workpaper_sync_legacy_baseline.json`（Task 2 的
   `single_mode_switch_visible` 等 flag）、`workpaper_sync_pilot_deletion_plan.json`
   （Task 45 已删的四个 pilot composable —— 已删的不再列一遍）、13 份
   `workpaper_sync_*_cycle_deletion_plan.json`（`deletion_execution_owner` 现读，
   不手抄「Task 72」）、`workpaper_resolver_migration_matrix.json`
   （`adjudication_owner_task` 现读 + 25 行点名 Task 66 的入向义务）、
   `.kiro/specs/**/tasks.md`（cycle→owner task 从任务标题现算；owner 编号必须真存在）。

任一边改动而另两边没跟上，`--check` 立刻打红。记录里的每个计数都现算，没有手抄常量。

用法（Windows PowerShell，仓库根）::

    .\\.venv\\Scripts\\python.exe backend/scripts/gen/generate_task66_legacy_deletion_plan.py --check
    .\\.venv\\Scripts\\python.exe backend/scripts/gen/generate_task66_legacy_deletion_plan.py --write
"""
from __future__ import annotations

import argparse
import ast
import collections
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import contracts as SYNC_CONTRACTS  # noqa: E402
from app.services.workpaper_sync import evidence as EV  # noqa: E402
from app.services.workpaper_sync.definitions import AuthorityModel  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
# 0. 路径 / 封闭词表（只有真源路径与词表，无任何实测数字）
# ═══════════════════════════════════════════════════════════════════════════

FRONTEND_SRC: pathlib.Path = _REPO / "audit-platform" / "frontend" / "src"
SYNC_DIR: pathlib.Path = FRONTEND_SRC / "components" / "workpaper" / "sync"
DATA_DIR: pathlib.Path = _BACKEND / "data"

OUTPUT_PATH: pathlib.Path = DATA_DIR / "workpaper_sync_task66_legacy_deletion_plan.json"

ENTRY_MANIFEST_PATH: pathlib.Path = DATA_DIR / "workpaper_sync_entry_manifest.json"
LEGACY_BASELINE_PATH: pathlib.Path = DATA_DIR / "workpaper_sync_legacy_baseline.json"
PILOT_DELETION_PLAN_PATH: pathlib.Path = DATA_DIR / "workpaper_sync_pilot_deletion_plan.json"
RESOLVER_MATRIX_PATH: pathlib.Path = DATA_DIR / "workpaper_resolver_migration_matrix.json"
MIGRATION_PARADIGM_PATH: pathlib.Path = DATA_DIR / "workpaper_sync_migration_paradigm.json"

SPEC_DIR: pathlib.Path = (
    _REPO / ".kiro" / "specs" / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
TASKS_MD_PATH: pathlib.Path = SPEC_DIR / "tasks.md"
REQUIREMENTS_PATH: pathlib.Path = SPEC_DIR / "requirements.md"

#: 替代面（统一 bridge / 统一 coordinator）—— 这些路径是 replacement map 的**靶**。
MODE_STORAGE_TS: pathlib.Path = SYNC_DIR / "workpaperSyncModeStorage.ts"
BRIDGE_TS: pathlib.Path = SYNC_DIR / "useWorkpaperSyncBridge.ts"
BRIDGE_MACHINE_TS: pathlib.Path = SYNC_DIR / "workpaperSyncBridgeMachine.ts"
EDITOR_HOST_VUE: pathlib.Path = SYNC_DIR / "WorkpaperSyncEditorHost.vue"
SYNC_ROUTER_PY: pathlib.Path = _BACKEND / "app" / "routers" / "wp_sync_router.py"

#: legacy 后端路由模块（清点 endpoint 的磁盘边）。
LEGACY_ROUTER_PATHS: tuple[pathlib.Path, ...] = (
    _BACKEND / "app" / "routers" / "wp_onlyoffice_router.py",
    _BACKEND / "app" / "routers" / "wp_render_strategies" / "_f2_stocktake_plan_sync.py",
    _BACKEND / "app" / "routers" / "wp_render_strategies" / "_f2_stocktake_summary_sync.py",
)

#: paragraph fallback 的生产/消费面（Requirement 7.1 逐字禁止中文正则/段落绝对索引作回写协议）。
PARAGRAPH_FALLBACK_PATHS: tuple[pathlib.Path, ...] = (
    _BACKEND / "app" / "services" / "wp_docx_template_parser.py",
    _BACKEND / "app" / "routers" / "wp_onlyoffice_router.py",
)

SCHEMA_VERSION: str = "task66-legacy-deletion-plan:v1"
OWNER_TASK: str = "66"

#: 七类清点对象的**封闭**词表（与 Task 66 正文第 1 条逐字对应）。
CATEGORIES: tuple[str, ...] = (
    "legacy_composable",
    "legacy_factory",
    "legacy_endpoint",
    "legacy_local_storage_key",
    "legacy_state_machine",
    "paragraph_index_fallback",
    "fail_open_success_message",
)

#: 处置的**封闭**词表。
#: * `replacement` —— 该路径本身就是替代面（保留；它是 map 的靶）。
#: * `pending_delete` —— 进入 Task 72 Stage B 的待删清单（**现在不得改动**）。
#: * `preserved_until_replacement_lands` —— 未过 Task 70 的全局共用路径 / 兼容 endpoint /
#:   fallback：既不删也不改，且**不进**删除清单（Task 72 删它即为计划外变更）。
DISPOSITIONS: tuple[str, ...] = (
    "replacement",
    "pending_delete",
    "preserved_until_replacement_lands",
)

#: Task 66 正文第 3 条点名的五个「必须被唯一归入 replacement 或 pending-delete」形态。
FORMS: tuple[str, ...] = (
    "unconsumed_bridge",
    "legacy_config_second_request",
    "single_fake_switch",
    "fail_open_success_message",
    "unreachable_stub",
)

#: 五个形态**只允许**落在这两个 disposition 上（正文逐字）。
FORM_ADMISSIBLE_DISPOSITIONS: tuple[str, ...] = ("replacement", "pending_delete")

#: 删除单位的封闭词表。Stage B 有的项删整个文件，有的项只删文件内的调用点 ——
#: 两者混用会让「共用路径不得进待删清单」这条判据把「删 A 文件里的 3 行」误判成
#: 「删掉整个 A 文件」（`wp_onlyoffice_router.py` 就是这种双重身份：7 个共用端点必须留，
#: 但它里面的 `paragraph_index` 回写降级必须删）。
DELETION_UNITS: tuple[str, ...] = (
    "whole_file",
    "route_within_file",
    "call_sites_within_file",
    "none",
)

#: category → 删除单位（派生，不逐项声明）。
_CATEGORY_DELETION_UNIT: dict[str, str] = {
    "legacy_composable": "whole_file",
    "legacy_factory": "whole_file",
    "legacy_state_machine": "whole_file",
    "legacy_endpoint": "route_within_file",
    "legacy_local_storage_key": "call_sites_within_file",
    "paragraph_index_fallback": "call_sites_within_file",
    "fail_open_success_message": "call_sites_within_file",
}

#: rollback 形态的封闭词表。
ROLLBACK_MODES: tuple[str, ...] = (
    # 文件已被 git 跟踪 ⇒ Task 72 删除后可 `git checkout <commit> -- <path>` 复原。
    "git_blob_at_plan_commit",
    # 文件在 git 里是 `??` 未跟踪 ⇒ 删掉即蒸发，删除前必须先入库或落快照。
    "pre_delete_snapshot_required",
    # 不删除的项（replacement / preserved）没有 rollback 动作，但必须显式说明。
    "no_deletion_planned",
)

#: legacy OnlyOffice 端点字面量（前端「旧 config 二次请求」的判据来源；
#: 端点集合本身由 AST 从 legacy router 现算，这里只是前端调用点的搜索面）。
LEGACY_ENDPOINT_LITERALS: tuple[str, ...] = (
    "onlyoffice-config",
    "onlyoffice/health",
    "whole-excel-grid",
    "wopi/contents",
    "template-structure",
    "import-structured",
    "plan-sync-to-oo",
    "plan-sync-from-oo",
    "summary-sync-to-oo",
    "summary-sync-from-oo",
)

#: 「真同步落库」的符号面 —— 成功文案的真值条件必须落在这里面某一个上，
#: 否则该成功文案就是 fail-open（AC 11.10 / Property 48）。
DURABLE_ACK_SYMBOLS: tuple[str, ...] = (
    "incomingDurable",
    "incoming_durable",
    "durableAck",
    "durable_at",
    "forceSave(",
    "forcesave",
)

#: mode 值域字面量（判定某个 localStorage 键是不是「模式枚举键」用；
#: 判据是**读回时与 mode 字面量比较**，不是键名里带没带 `mode`）。
MODE_VALUE_LITERALS: tuple[str, ...] = ("html", "onlyoffice", "oo")

#: 各类对象的 replacement 靶（路径 + 语义）。这不是「实测数字」而是**替代关系声明**，
#: 每一条都要求靶文件真实存在（缺文件即抛），且靶必须落在替代面目录内。
REPLACEMENT_TARGETS: dict[str, dict[str, str]] = {
    "legacy_composable": {
        "kind": "unified_bridge_composable",
        "path": "audit-platform/frontend/src/components/workpaper/sync/useWorkpaperSyncBridge.ts",
        "why": "AC 11.1：legacy dual-mode 实现收敛到统一 bridge，业务组件只提供 entry_id + flush/reload 钩子",
    },
    "legacy_factory": {
        "kind": "unified_bridge_state_machine",
        "path": "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncBridgeMachine.ts",
        "why": "AC 11.2：状态机是唯一的；参数化工厂再生产一批同构 mode 机即第二条路径",
    },
    "legacy_endpoint": {
        "kind": "unified_sync_coordinator_router",
        "path": "backend/app/routers/wp_sync_router.py",
        "why": "AC 12.7：专用 to/from 端点迁到统一协议并删除第二套半闭环",
    },
    "legacy_local_storage_key": {
        "kind": "unified_mode_storage",
        "path": "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncModeStorage.ts",
        "why": "AC 11.8：旧键幂等迁移到按 entry_id/wp_id/sheet 的统一键",
    },
    "legacy_state_machine": {
        "kind": "unified_bridge_state_machine",
        "path": "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncBridgeMachine.ts",
        "why": "AC 11.2 / Property 46：状态转换封闭，非法转换抛错且不改 mode",
    },
    "paragraph_index_fallback": {
        "kind": "tagged_sdt_anchor_lane",
        "path": "backend/app/services/workpaper_sync/word_entry_gate.py",
        "why": "AC 7.1 + Task 6 裁决：paragraph_index/run_index 为 failed 锚点，只认 tagged SDT",
    },
    "fail_open_success_message": {
        "kind": "bridge_feedback_presentation",
        "path": "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncPresentation.ts",
        "why": "AC 11.10 / Property 48：文案由 bridge 的失败态决定，成功不得覆盖 error",
    },
}


class Task66GeneratorError(RuntimeError):
    """生成器自身失败（禁 fail-open：让退出码非零，不降级成「无数据」）。"""


# ═══════════════════════════════════════════════════════════════════════════
# 1. 源码读取工具：剥注释 / import 图 / 括号配对截取
# ═══════════════════════════════════════════════════════════════════════════

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def strip_comments(text: str) -> str:
    """剥掉 HTML/块/行注释，**保留行数**（行内注释只清尾巴，不删整行）。

    行注释扫描必须带引号状态机：`'https://x'` 里的 `//` 不是注释。
    """
    stripped = _HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    stripped = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), stripped)
    out: list[str] = []
    for line in stripped.split("\n"):
        cut = -1
        quote: str | None = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote is not None:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'`":
                quote = ch
            elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                cut = i
                break
            i += 1
        out.append(line if cut < 0 else line[:cut])
    return "\n".join(out)


def _is_test_path(rel: str) -> bool:
    return "__tests__" in rel or rel.endswith(".spec.ts") or rel.endswith(".test.ts")


def rel(path: pathlib.Path) -> str:
    return str(path.relative_to(_REPO)).replace("\\", "/")


class FrontendSources:
    """前端源码快照：原文 / 剥注释后的码面 / import 图（真 specifier 解析）。"""

    _IMPORT_SPEC = re.compile(r"""(?:from\s*|import\s*\(\s*)['"]([^'"]+)['"]""")
    _RESOLVE_EXTS = ("", ".ts", ".vue", ".js", "/index.ts", "/index.vue")

    def __init__(self) -> None:
        files = [
            p
            for p in FRONTEND_SRC.rglob("*")
            if p.is_file() and p.suffix in {".ts", ".vue"}
        ]
        if not files:
            raise Task66GeneratorError(f"前端源码目录为空：{FRONTEND_SRC}")
        self.files: tuple[pathlib.Path, ...] = tuple(sorted(files))
        self.raw: dict[pathlib.Path, str] = {
            p: p.read_text(encoding="utf-8", errors="replace") for p in self.files
        }
        self.code: dict[pathlib.Path, str] = {
            p: strip_comments(t) for p, t in self.raw.items()
        }
        self.importers: dict[pathlib.Path, set[pathlib.Path]] = {p: set() for p in self.files}
        self.imports: dict[pathlib.Path, set[pathlib.Path]] = {p: set() for p in self.files}
        for src, code in self.code.items():
            for match in self._IMPORT_SPEC.finditer(code):
                target = self._resolve(match.group(1), src)
                if target is not None and target in self.importers:
                    self.importers[target].add(src)
                    self.imports[src].add(target)

    def _resolve(self, spec: str, src: pathlib.Path) -> pathlib.Path | None:
        if spec.startswith("@/"):
            base = FRONTEND_SRC / spec[2:]
        elif spec.startswith("."):
            base = (src.parent / spec).resolve()
        else:
            return None
        for ext in self._RESOLVE_EXTS:
            candidate = pathlib.Path(str(base) + ext)
            if candidate.is_file():
                return candidate
        return None

    # ── 消费方 ──────────────────────────────────────────────────────────
    def production_importers(self, path: pathlib.Path) -> list[str]:
        return sorted(
            rel(q) for q in self.importers.get(path, ()) if not _is_test_path(rel(q))
        )

    def test_importers(self, path: pathlib.Path) -> list[str]:
        return sorted(
            rel(q) for q in self.importers.get(path, ()) if _is_test_path(rel(q))
        )

    def transitive_production_importers(self, path: pathlib.Path) -> list[str]:
        seen: set[pathlib.Path] = set()
        frontier = [path]
        while frontier:
            cur = frontier.pop()
            for q in self.importers.get(cur, ()):
                if q in seen or _is_test_path(rel(q)):
                    continue
                seen.add(q)
                frontier.append(q)
        return sorted(rel(q) for q in seen)

    def reference_sites(
        self, path: pathlib.Path, symbols: list[str]
    ) -> list[dict[str, Any]]:
        """生产消费方里对该模块导出符号的全部引用点（剥注释后；含 re-export barrel）。"""
        needles = [s for s in symbols if s]
        sites: list[dict[str, Any]] = []
        for consumer in sorted(self.importers.get(path, ())):
            if _is_test_path(rel(consumer)):
                continue
            for idx, line in enumerate(self.code[consumer].split("\n"), 1):
                if any(re.search(rf"\b{re.escape(n)}\b", line) for n in needles):
                    sites.append(
                        {
                            "file": rel(consumer),
                            "line": idx,
                            "snippet": line.strip()[:160],
                        }
                    )
        return sites

    def last_call_site(
        self, path: pathlib.Path, symbols: list[str]
    ) -> dict[str, Any] | None:
        """最后一处引用点 = 全部引用点里 `(文件, 行)` 字典序最大的那处。

        刻意**不**只认 `foo(` 形态的调用：Stage B 删文件时 re-export barrel
        （`export type { … } from './createDualMode'`）同样必须改，漏掉它就会留下
        指向已删文件的 import 而编译失败。
        """
        sites = self.reference_sites(path, symbols)
        if not sites:
            return None
        best = max(sites, key=lambda s: (s["file"], s["line"]))
        return {**best, "reference_site_count": len(sites)}


_EXPORT_FN = re.compile(r"^export\s+(?:async\s+)?function\s+([A-Za-z0-9_]+)", re.M)
_EXPORT_CONST = re.compile(r"^export\s+const\s+([A-Za-z0-9_]+)", re.M)


def exported_symbols(code: str, path: pathlib.Path) -> list[str]:
    syms = set(_EXPORT_FN.findall(code)) | set(_EXPORT_CONST.findall(code))
    if path.suffix == ".vue":
        syms.add(path.stem)
    return sorted(syms)


def sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 2. git 事实（rollback 隔离门的唯一依据）
# ═══════════════════════════════════════════════════════════════════════════


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=_REPO, capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise Task66GeneratorError(
            f"git {' '.join(args)} 失败 rc={proc.returncode}: "
            f"{proc.stderr.decode('utf-8', 'replace')[:300]}"
        )
    return proc.stdout.decode("utf-8", "replace")


class GitFacts:
    """HEAD commit + tracked 文件集合。rollback target 只能从这里推。"""

    def __init__(self) -> None:
        self.head_commit = _git("rev-parse", "HEAD").strip()
        self.tracked: frozenset[str] = frozenset(
            line for line in _git("ls-files", "-z").split("\0") if line
        )
        if not self.tracked:
            raise Task66GeneratorError("`git ls-files` 返回空集 —— tracked 判据会恒 False")

    def is_tracked(self, rel_path: str) -> bool:
        return rel_path in self.tracked


# ═══════════════════════════════════════════════════════════════════════════
# 3. 清册边：manifest / legacy baseline / pilot plan / cycle plans / matrix / tasks.md
# ═══════════════════════════════════════════════════════════════════════════


def load_json(path: pathlib.Path) -> Any:
    if not path.is_file():
        raise Task66GeneratorError(f"清册边缺文件：{rel(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


def cycle_owner_tasks() -> dict[str, str]:
    """从 tasks.md 的任务标题现算 `cycle letter -> owner task id`。

    两种标题形态都认：`逐一迁移 D 循环 …` 与 `逐一迁移 A/B/C/S 与跨循环共享 …`。
    禁手抄 46..57 —— 任务号漂移时必须打红。
    """
    text = TASKS_MD_PATH.read_text(encoding="utf-8")
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*-\s\[[ x~\-]\]\s+(\d+)\.\s+(.*)$", line)
        if not match:
            continue
        task_id, title = match.group(1), match.group(2)
        for group in re.findall(r"([A-Z](?:/[A-Z])*)\s*循环", title):
            for letter in group.split("/"):
                mapping.setdefault(letter, task_id)
        for group in re.findall(r"([A-Z](?:/[A-Z])+)\s*与跨循环共享", title):
            for letter in group.split("/"):
                mapping.setdefault(letter, task_id)
    if len(mapping) < 10:
        raise Task66GeneratorError(
            f"从 tasks.md 只解析出 {len(mapping)} 个 cycle→task 映射 —— 标题形态变了"
        )
    return mapping


def tasks_md_task_ids() -> frozenset[str]:
    text = TASKS_MD_PATH.read_text(encoding="utf-8")
    ids = frozenset(re.findall(r"^\s*-\s\[[ x~\-]\]\s+(\d+)\.", text, re.M))
    if not ids:
        raise Task66GeneratorError("tasks.md 里一个任务复选框都没解析到")
    return ids


def deletion_execution_owner() -> str:
    """从 per-cycle 删除计划现读 `deletion_execution_owner` 里的**执行方**任务号。

    不手抄「Task 72」：并发方改了执行方，本清册必须跟着变或者打红。各计划的文案不同
    （`Task 66（plan）/ Task 72（execute）` vs `Task 66 / Task 72（全局 legacy 删除两阶段门）`），
    所以规范化取「最后一个 Task 号」= 执行方，并要求各计划规范化后**一致**。
    """
    owners: dict[str, list[str]] = collections.defaultdict(list)
    for path in sorted(DATA_DIR.glob("workpaper_sync_*_cycle_deletion_plan.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("deletion_execution_owner")
        if not raw:
            continue
        task_ids = re.findall(r"Task\s*(\d+)", str(raw))
        if not task_ids:
            raise Task66GeneratorError(
                f"{rel(path)} 的 deletion_execution_owner 里抓不到任务号：{raw!r}"
            )
        if OWNER_TASK not in task_ids:
            raise Task66GeneratorError(
                f"{rel(path)} 的 deletion_execution_owner 不含 Task {OWNER_TASK}（计划方）：{raw!r}"
            )
        owners[task_ids[-1]].append(rel(path))
    if len(owners) != 1:
        raise Task66GeneratorError(
            "per-cycle 计划的删除执行方不唯一："
            f"{ {k: len(v) for k, v in owners.items()} }"
        )
    executor = next(iter(owners))
    if executor == OWNER_TASK:
        raise Task66GeneratorError(
            "per-cycle 计划把删除执行方也算成 Task 66 —— 本任务只生成计划，不执行删除"
        )
    return executor


def ac_11_5_required_events() -> list[str]:
    """从 requirements.md 的 AC 11.5 现读「必须发出的事件」清单。

    AC 原文：`… SHALL 暴露可 await 的 forceSave()/状态 API，发出 ready、dirty、
    save-requested、incoming-durable、applied/conflict、recovery-case、error 事件；
    不得只 emit fallback …`
    """
    text = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    line = next(
        (ln for ln in text.splitlines() if ln.strip().startswith("11.5.")), None
    )
    if line is None:
        raise Task66GeneratorError("requirements.md 里找不到 AC 11.5")
    match = re.search(r"发出\s*(.+?)\s*事件", line)
    if not match:
        raise Task66GeneratorError(f"AC 11.5 的事件清单抓取失败：{line[:160]!r}")
    events: list[str] = []
    for token in re.split(r"[、/]", match.group(1)):
        name = token.strip().strip("`")
        if name:
            events.append(name)
    if len(events) < 5:
        raise Task66GeneratorError(f"AC 11.5 只解析出 {len(events)} 个事件名")
    return events


# ═══════════════════════════════════════════════════════════════════════════
# 4. entry 绑定与 required scenario 现算
# ═══════════════════════════════════════════════════════════════════════════

#: authority model 探针 —— 全平台 approved bundle 实测为 0，required scenario 只能
#: 拿枚举里的一个值当**探针**跑出来；它不是最终 required set（Task 70 负责重推）。
PROBE_AUTHORITY_MODEL: AuthorityModel = AuthorityModel.projection_contract


class ManifestFacts:
    """manifest + legacy baseline 的联合视图（entry ↔ host 文件 ↔ required scenario）。"""

    def __init__(self) -> None:
        self.manifest = load_json(ENTRY_MANIFEST_PATH)
        self.entries: list[dict[str, Any]] = list(self.manifest["entries"])
        if not self.entries:
            raise Task66GeneratorError("manifest entries 为空 —— entry 绑定会恒空")
        self.baseline = load_json(LEGACY_BASELINE_PATH)
        self.baseline_by_id: dict[str, dict[str, Any]] = {
            str(e["entry_id"]): e for e in self.baseline["entries"]
        }
        # host 文件 → entry_id 集合（host_path + mounts 的 file / canonicalComponentFile）
        self.by_file: dict[str, set[str]] = collections.defaultdict(set)
        for entry in self.entries:
            entry_id = str(entry["entry_id"])
            host = entry.get("host_path")
            if host:
                self.by_file[str(host)].add(entry_id)
            for mount in entry.get("mounts") or ():
                for key in ("file", "canonicalComponentFile"):
                    value = mount.get(key)
                    if value:
                        self.by_file[str(value)].add(entry_id)
        # required scenario 现算（fail closed：drift 如实记 error，不吞）
        self.scenarios: dict[str, dict[str, Any]] = {}
        for entry in self.entries:
            entry_id = str(entry["entry_id"])
            try:
                derived = EV.derive_for_manifest_entry(
                    entry, authority_model=PROBE_AUTHORITY_MODEL
                )
            except Exception as exc:  # noqa: BLE001 - 逐 entry 如实记 error 码
                self.scenarios[entry_id] = {
                    "status": "underivable",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:220],
                    "scenario_ids": [],
                    "required_scenario_set_digest": None,
                }
                continue
            self.scenarios[entry_id] = {
                "status": "derived",
                "error_type": None,
                "error_message": None,
                "scenario_ids": list(derived.scenario_ids),
                "required_scenario_set_digest": derived.digest,
            }
        self.probe_sensitivity = self._probe_sensitivity()

    def _probe_sensitivity(self) -> dict[str, Any]:
        """证明「探针 authority model ≠ 最终 required set」：换枚举值后 scenario 集合会变。"""
        changed: list[str] = []
        for entry in self.entries:
            entry_id = str(entry["entry_id"])
            base = self.scenarios[entry_id]
            if base["status"] != "derived":
                continue
            for model in AuthorityModel:
                if model is PROBE_AUTHORITY_MODEL:
                    continue
                try:
                    other = EV.derive_for_manifest_entry(entry, authority_model=model)
                except Exception:  # noqa: BLE001 - 敏感性探测本身不决定裁决
                    continue
                if list(other.scenario_ids) != base["scenario_ids"]:
                    changed.append(entry_id)
                    break
        return {
            "probe_authority_model": PROBE_AUTHORITY_MODEL.value,
            "alternatives_probed": [
                m.value for m in AuthorityModel if m is not PROBE_AUTHORITY_MODEL
            ],
            "entries_whose_scenario_set_changes": len(changed),
            "sample": sorted(changed)[:3],
            "why_it_matters": (
                "approved bundle 实测为 0 ⇒ authority model 未定；换一个枚举值 scenario "
                "集合就变 ⇒ 本清册记的 required set 是**探针**，Task 70 必须按 approved "
                "bundle 重推，不能拿这里的 digest 当已验收"
            ),
        }

    def entries_for_files(self, files: list[str]) -> list[str]:
        found: set[str] = set()
        for f in files:
            found |= self.by_file.get(f, set())
        return sorted(found)

    def is_manifest_surface_file(self, rel_path: str) -> bool:
        """该文件是否出现在 source-backed manifest 的宿主/挂载面上。

        清点范围必须由 manifest 划定，否则会把 `components/deliverable/` 下的
        交付物编辑器也算进底稿 HTML↔OO 回写面（实测假阳性）。
        """
        return rel_path in self.by_file

    def scenario_evidence(self, entry_ids: list[str]) -> dict[str, Any]:
        """某一项的「所需 scenario evidence」。

        逐 entry 的 digest 只在记录顶层放一份（`manifest_required_scenario_sets`），
        item 里放**捆绑 digest** = 对 `(entry_id, digest)` 排序序列的 sha256 —— 任一
        绑定 entry 的 required set 变了，这个 digest 就变，Task 70 据此判重跑范围。
        """
        union: set[str] = set()
        pairs: list[tuple[str, str]] = []
        underivable: list[str] = []
        for entry_id in entry_ids:
            row = self.scenarios.get(entry_id)
            if row is None or row["status"] != "derived":
                underivable.append(entry_id)
                continue
            union |= set(row["scenario_ids"])
            pairs.append((entry_id, row["required_scenario_set_digest"]))
        bundle_digest = hashlib.sha256(
            json.dumps(sorted(pairs), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return {
            "bound_entry_ids": sorted(entry_ids),
            "bound_entry_count": len(entry_ids),
            "scenario_id_union": sorted(union),
            "scenario_id_union_count": len(union),
            "required_scenario_set_bundle_digest": bundle_digest,
            "derived_entry_count": len(pairs),
            "underivable_entry_ids": sorted(underivable),
            "refresh_owner_task": "70",
            "status": "UNVERIFIABLE",
            "status_reason": (
                "本任务不运行真实 OO 场景；approved bundle 与 published representation "
                "供给实测为 0，evidence 只能保持 UNVERIFIABLE（AC 12.10）"
            ),
        }

    def single_switch_entries(self) -> list[str]:
        """capability 非 bidirectional 却仍显示模式切换的 entry（single 假切换分母）。"""
        out: list[str] = []
        for entry in self.entries:
            entry_id = str(entry["entry_id"])
            if str(entry.get("capability")) == "bidirectional":
                continue
            base = self.baseline_by_id.get(entry_id) or {}
            flags = base.get("flags") or {}
            if flags.get("single_mode_switch_visible"):
                out.append(entry_id)
        return sorted(out)


# ═══════════════════════════════════════════════════════════════════════════
# 5. 七类对象的现算
# ═══════════════════════════════════════════════════════════════════════════

_LEGACY_COMPOSABLE_NAME = re.compile(r"^use[A-Za-z0-9]*DualMode\.ts$")
#: legacy 模式状态机的字段面（三元：当前模式 / OO 可用 / 探测中）。
_LEGACY_STATE_FIELDS: tuple[str, ...] = (
    "currentMode",
    "isOoAvailable",
    "ooAvailable",
    "ooConfigReady",
    "checking",
    "ooChecking",
    "switching",
)


def _cycle_letter_of(path: pathlib.Path, owners: dict[str, str]) -> str | None:
    """从 composable 文件名取循环字母（`useD1DualMode.ts` → `D`）。取不到即返回 None。"""
    match = re.match(r"^use([A-Z])\d*[A-Za-z0-9]*DualMode\.ts$", path.name)
    if match and match.group(1) in owners:
        return match.group(1)
    return None


def _legacy_endpoint_hits(code: str) -> list[str]:
    return sorted({lit for lit in LEGACY_ENDPOINT_LITERALS if lit in code})


def _mode_state_fields(code: str) -> list[str]:
    """真正**创建**了模式响应式状态的字段。

    🔴 判据必须是 `field = ref(...)`：只查 `field:` 会把 165 KB 的
    `workpaperSyncLegacyBaseline.generated.ts` 里当**数据键**出现的 `currentMode:`
    算成一个状态机（实测假阳性）。
    """
    return sorted(
        {
            field
            for field in _LEGACY_STATE_FIELDS
            if re.search(rf"\b{field}\b\s*(?::[^=\n]+)?=\s*ref\s*[<(]", code)
        }
    )


_SUCCESS_CALL = re.compile(
    r"ElMessage\.success\(|type:\s*'success'|type=\"success\"|type='success'"
)
_OO_SEMANTICS = re.compile(
    r"OnlyOffice|onlyoffice|在线编辑|拉取成功|回退|结构化视图|双模式|就绪"
)


def _success_sites(code: str) -> list[dict[str, Any]]:
    sites: list[dict[str, Any]] = []
    for idx, line in enumerate(code.split("\n"), 1):
        if _SUCCESS_CALL.search(line) and _OO_SEMANTICS.search(line):
            sites.append({"line": idx, "snippet": line.strip()[:180]})
    return sites


def _durable_symbols(code: str) -> list[str]:
    return sorted({sym for sym in DURABLE_ACK_SYMBOLS if sym in code})


def legacy_key_migration_regex() -> tuple[str, re.Pattern[str]]:
    """从替代面 TS 源码里把 `LEGACY_KEY_RE` 的正则字面量读出来（不手抄）。"""
    text = MODE_STORAGE_TS.read_text(encoding="utf-8")
    match = re.search(r"const\s+LEGACY_KEY_RE\s*=\s*/(.+?)/\s*$", text, re.M)
    if not match:
        raise Task66GeneratorError(
            f"{rel(MODE_STORAGE_TS)} 里抓不到 LEGACY_KEY_RE —— 旧键覆盖面判据失去真源"
        )
    pattern = match.group(1)
    return pattern, re.compile(pattern)


def unified_key_prefix() -> str:
    text = MODE_STORAGE_TS.read_text(encoding="utf-8")
    match = re.search(
        r"export\s+const\s+WP_SYNC_MODE_KEY_PREFIX\s*=\s*['\"]([^'\"]+)['\"]", text
    )
    if not match:
        raise Task66GeneratorError("抓不到 WP_SYNC_MODE_KEY_PREFIX")
    return match.group(1)


_LOCALSTORAGE_CALL = re.compile(
    r"localStorage\.(getItem|setItem|removeItem)\(\s*([^,)]+)"
)
_CONST_LITERAL = re.compile(
    r"""(?:const|let)\s+([A-Za-z0-9_]+)\s*(?::[^=\n]+)?=\s*['"]([^'"]+)['"]"""
)
#: 函数声明头（两种形态：`function name(` 与 `const name = (`/`const name = async (`）。
_FN_HEAD = re.compile(
    r"(?:function\s+(?P<fn>[A-Za-z0-9_]+)\s*\()"
    r"|(?:(?:const|let)\s+(?P<arrow>[A-Za-z0-9_]+)\s*(?::[^=\n]+)?=\s*(?:async\s*)?\()"
)


def _match_pair(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """从 `text[start] == open_ch` 起做**括号配对**，返回闭合符下标；配不上返回 -1。

    🔴 教训 14：截函数体禁固定字符窗口，一律配对；且必须**先跳参数列表**再找 `{`
    —— TS 的返回类型注解 `): Promise<{...}>` 会骗到「第一个 `{`」。
    """
    depth = 0
    i = start
    quote: str | None = None
    while i < len(text):
        ch = text[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _body_brace_after_params(code: str, paren_close: int) -> int:
    """参数列表闭合括号之后，函数体 `{` 的下标；找不到返回 -1。

    🔴 教训 14：TS 的返回类型注解会骗到「第一个 `{`」——
    `function f(a): Promise<{y: string}> {` 里第一个 `{` 落在 `Promise<…>` 内部。
    所以扫描时要记 `<>` 深度，只认 angle-depth 0 上的那个 `{`（`=>` 的 `>` 单独跳过）。
    """
    angle = 0
    i = paren_close + 1
    while i < len(code):
        ch = code[i]
        if ch == "=" and i + 1 < len(code) and code[i + 1] == ">":
            i += 2
            continue
        if ch == "<":
            angle += 1
        elif ch == ">":
            angle = max(0, angle - 1)
        elif ch == "{" and angle == 0:
            return i
        elif ch in ";)" and angle == 0:
            return -1
        i += 1
    return -1


def _function_bodies(code: str) -> dict[str, str]:
    """`函数名 -> 函数体源码`（括号配对；先跳参数列表再取花括号块）。"""
    bodies: dict[str, str] = {}
    for match in _FN_HEAD.finditer(code):
        name = match.group("fn") or match.group("arrow")
        if not name:
            continue
        paren_open = code.index("(", match.start())
        paren_close = _match_pair(code, paren_open, "(", ")")
        if paren_close < 0:
            continue
        brace_open = _body_brace_after_params(code, paren_close)
        if brace_open < 0:
            continue
        # 参数列表之后到 `{` 之间只允许返回类型注解/箭头/空白 —— 否则不是同一个函数。
        between = code[paren_close + 1: brace_open]
        if "\n\n" in between or ";" in between:
            continue
        brace_close = _match_pair(code, brace_open, "{", "}")
        if brace_close < 0:
            continue
        bodies.setdefault(name, code[brace_open: brace_close + 1])
    return bodies


_TEMPLATE_LITERAL = re.compile(r"`([^`]*)`", re.S)
_MODE_COMPARISON = re.compile(
    r"===?\s*'(?:" + "|".join(MODE_VALUE_LITERALS) + r")'"
    r"|'(?:" + "|".join(MODE_VALUE_LITERALS) + r")'\s*===?"
)


def _resolve_key_prefix(expr: str, code: str) -> str | None:
    r"""把 `localStorage` 的 key 表达式解析成静态前缀。

    支持三种形态（都在存量里真实出现）：
      1. `STORAGE_PREFIX + wpId.value` —— 常量字面量；
      2. `_getStorageKey()` —— 函数体里 `return \`${STORAGE_KEY_PREFIX}${wpId.value}\``；
      3. 直接模板字面量 `` `${PREFIX}${id}` `` 或纯字符串。
    解析不出来返回 None（**不猜**）。
    """
    expr = expr.strip()
    consts = dict(_CONST_LITERAL.findall(code))

    def _prefix_of_template(inner: str) -> str | None:
        head = re.match(r"^\$\{\s*([A-Za-z0-9_]+)\s*\}", inner)
        if head and head.group(1) in consts:
            return consts[head.group(1)]
        static = re.match(r"^([^$`]+)", inner)
        return static.group(1) if static else None

    call = re.match(r"^([A-Za-z0-9_]+)\s*\(", expr)
    if call:
        body = _function_bodies(code).get(call.group(1))
        if body is not None:
            for template in _TEMPLATE_LITERAL.finditer(body):
                prefix = _prefix_of_template(template.group(1))
                if prefix:
                    return prefix
            for name, value in consts.items():
                if re.search(rf"\b{re.escape(name)}\b", body):
                    return value
        return None

    if expr.startswith("`"):
        return _prefix_of_template(expr[1:])

    for name, value in consts.items():
        if re.search(rf"\b{re.escape(name)}\b", expr):
            return value
    literal = re.match(r"^['\"]([^'\"]+)['\"]", expr)
    if literal:
        return literal.group(1)
    return None


_PORT_STORAGE_CALL = re.compile(r"\bstorage\.(getItem|setItem|removeItem)\(\s*([^,)]+)")


def canonical_mode_storage_sites() -> list[dict[str, Any]]:
    """替代面 mode storage 模块的写入点。

    🔴 它**不**直接调全局 `localStorage`，而是走一个可注入的 storage port
    （`getItem/setItem/removeItem` 三方法接口）——这正是它与 100 余处 legacy 调用点的
    结构差别：legacy 全部直接摸全局对象、无法在测试里替换、也无法统一迁移。
    所以「直接全局 localStorage」那个检测器在这里命中 0 次是**事实**而不是漏检，
    本函数用第二个检测器把 canonical 写入点单独算出来。
    """
    code = strip_comments(MODE_STORAGE_TS.read_text(encoding="utf-8"))
    rel_path = rel(MODE_STORAGE_TS)
    direct_global = [
        idx
        for idx, line in enumerate(code.split("\n"), 1)
        if _LOCALSTORAGE_CALL.search(line)
    ]
    if direct_global:
        raise Task66GeneratorError(
            f"{rel_path} 出现了直接调用全局 localStorage 的调用点（行 {direct_global}）—— "
            "替代面的 storage port 被绕开，本记录关于「canonical 走注入端口」的结论失效"
        )
    sites: list[dict[str, Any]] = []
    for idx, line in enumerate(code.split("\n"), 1):
        match = _PORT_STORAGE_CALL.search(line)
        if not match:
            continue
        sites.append(
            {
                "file": rel_path,
                "line": idx,
                "op": match.group(1),
                "key_expression": match.group(2).strip()[:60],
                "snippet": line.strip()[:160],
            }
        )
    if not sites:
        raise Task66GeneratorError(
            f"{rel_path} 里一个 storage port 写入点都没算出来 —— canonical 分母恒空"
        )
    return sites


def mode_storage_sites(sources: FrontendSources) -> list[dict[str, Any]]:
    """模式枚举 localStorage 调用点：判据是**读回值与 mode 字面量比较**，不是键名。"""
    sites: list[dict[str, Any]] = []
    for path in sources.files:
        rel_path = rel(path)
        if _is_test_path(rel_path):
            continue
        code = sources.code[path]
        if "localStorage" not in code:
            continue
        lines = code.split("\n")
        for idx, line in enumerate(lines):
            match = _LOCALSTORAGE_CALL.search(line)
            if not match:
                continue
            window = "\n".join(lines[max(0, idx - 4): idx + 6])
            if not _MODE_COMPARISON.search(window):
                continue
            prefix = _resolve_key_prefix(match.group(2), code)
            if prefix is None:
                continue
            sites.append(
                {
                    "file": rel_path,
                    "line": idx + 1,
                    "op": match.group(1),
                    "key_prefix": prefix,
                    "snippet": line.strip()[:160],
                }
            )
    if not sites:
        raise Task66GeneratorError("一个模式 localStorage 调用点都没算出来 —— 判据退化成恒空")
    return sites


def router_routes(path: pathlib.Path) -> list[dict[str, Any]]:
    """AST 现算某个 router 模块的路由（方法 / 路径 / 函数名 / 行号）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    routes: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            if dec.func.attr not in {"get", "post", "put", "delete", "patch"}:
                continue
            receiver = dec.func.value
            receiver_name = receiver.id if isinstance(receiver, ast.Name) else "<expr>"
            route_path: str | None = None
            if dec.args:
                arg = dec.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    route_path = arg.value
                elif isinstance(arg, ast.BinOp):
                    parts: list[str] = []
                    for side in (arg.left, arg.right):
                        if isinstance(side, ast.Constant) and isinstance(side.value, str):
                            parts.append(side.value)
                        elif isinstance(side, ast.Name):
                            parts.append(f"<{side.id}>")
                    route_path = "".join(parts) or None
            routes.append(
                {
                    "router_object": receiver_name,
                    "method": dec.func.attr.upper(),
                    "path": route_path,
                    "function": node.name,
                    "line": node.lineno,
                }
            )
    if not routes:
        raise Task66GeneratorError(f"{rel(path)} 里 AST 没抓到任何路由")
    return sorted(routes, key=lambda r: r["line"])


def paragraph_fallback_sites() -> list[dict[str, Any]]:
    """`paragraph_index` 的生产/消费点（真源码现读，行号带上）。"""
    sites: list[dict[str, Any]] = []
    for path in PARAGRAPH_FALLBACK_PATHS:
        text = path.read_text(encoding="utf-8")
        for idx, line in enumerate(text.split("\n"), 1):
            if "paragraph_index" not in line:
                continue
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("*"):
                continue
            role = "producer" if re.search(r"position\s*=\s*\{", line) else "consumer"
            sites.append(
                {
                    "file": rel(path),
                    "line": idx,
                    "role": role,
                    "snippet": stripped[:160],
                }
            )
    if not sites:
        raise Task66GeneratorError("`paragraph_index` 一处都没找到 —— 该族判据恒空")
    return sites


def word_anchor_gate() -> dict[str, Any]:
    """从 Word 载体门现读锚点白/黑名单，并**真喂一次**证明 `paragraph_index` 会被拒。

    只读 `blocked_anchors` 列表是「清单非空 + 逐项成立」型判据，会被改名绕过
    （Task 64 的 M13 教训）；所以这里额外要求：
      * 黑名单**必须包含** `paragraph_index` 这个真实目标；
      * 把它真喂进 `assert_anchor` 必须抛，白名单 `w_tag` 必须不抛。
    """
    gate = SYNC_CONTRACTS.load_word_carrier_gate()
    blocked = sorted(gate.blocked_anchors)
    allowed = sorted(gate.allowed_anchors)
    if "paragraph_index" not in blocked:
        raise Task66GeneratorError(
            "Word 门的 blocked_anchors 里没有 `paragraph_index` —— "
            "paragraph fallback 的替代关系失去真源（AC 7.1）"
        )
    if not allowed:
        raise Task66GeneratorError("allowed_anchors 为空 —— 对照组缺失，「什么都拒」也算通过")
    control = allowed[0]
    # 对照组必须先过（否则「什么都拒」也算通过 —— 教训 5）。
    gate.assert_anchor(control, location="task66.control")
    refusal: dict[str, Any]
    try:
        gate.assert_anchor("paragraph_index", location="task66.paragraph_index")
    except Exception as exc:  # noqa: BLE001 - 这里要的就是它抛
        message = str(exc)
        # 教训 1：不能只比异常类型；拒绝原因必须点名被拒的那个锚点，且**不**点名对照组。
        if "paragraph_index" not in message or control in message:
            raise Task66GeneratorError(
                f"paragraph_index 的拒绝理由不互不命中：{message[:200]!r}"
            ) from exc
        refusal = {
            "raised": True,
            "error_type": type(exc).__name__,
            "message": message[:220],
            "names_the_refused_anchor": True,
            "does_not_name_the_control_anchor": True,
        }
    else:
        raise Task66GeneratorError(
            "`assert_anchor('paragraph_index')` 没抛 —— 门只是清单没有强制力"
        )
    return {
        "source_path": rel(pathlib.Path(gate.source_path)),
        "source_digest": gate.source_digest,
        "blocked_anchors": blocked,
        "allowed_anchors": allowed,
        "paragraph_index_refusal": refusal,
        "control_anchor_accepted": allowed[0],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. 逐项装配：五个必绑字段 + 形态 + disposition
# ═══════════════════════════════════════════════════════════════════════════

#: 每个 item 必须齐备的五个绑定字段（正文第 1 条逐字）。任一为空即结构性失效。
REQUIRED_BINDINGS: tuple[str, ...] = (
    "replacement",
    "owner",
    "last_call_site_binding",
    "rollback_target",
    "required_scenario_evidence",
)


def _replacement_for(category: str, manifest_entry_ids: list[str]) -> dict[str, Any]:
    target = REPLACEMENT_TARGETS[category]
    path = _REPO / target["path"]
    if not path.is_file():
        raise Task66GeneratorError(
            f"category={category} 的 replacement 靶不存在：{target['path']}"
        )
    return {
        "kind": target["kind"],
        "path": target["path"],
        "why": target["why"],
        "target_sha256": sha256_of(path),
        "manifest_entry_ids": manifest_entry_ids,
    }


def _rollback_target(
    rel_path: str, *, disposition: str, git: GitFacts
) -> dict[str, Any]:
    tracked = git.is_tracked(rel_path)
    if disposition != "pending_delete":
        return {
            "mode": "no_deletion_planned",
            "path": rel_path,
            "plan_commit": git.head_commit,
            "tracked_at_plan_time": tracked,
            "recoverable_from_git": tracked,
            "note": "本项不进 Stage B 删除清单；rollback 动作为空但必须显式登记",
        }
    return {
        "mode": "git_blob_at_plan_commit" if tracked else "pre_delete_snapshot_required",
        "path": rel_path,
        "plan_commit": git.head_commit,
        "tracked_at_plan_time": tracked,
        "recoverable_from_git": tracked,
        "restore_command": (
            f"git checkout {git.head_commit} -- {rel_path}"
            if tracked
            else "（未跟踪：Stage B 前必须先入库或落文件快照，否则删除不可逆）"
        ),
    }


def _last_call_site_binding(
    site: dict[str, Any] | None,
    absent_reason: str | None,
    *,
    needles: list[str],
) -> dict[str, Any]:
    """最后调用点绑定：`site` 与 `absent_reason` **恰有一个**非空。

    `needles` = 定位该调用点用的字符串（守卫据此反查「登记的行上真有它」）。
    endpoint 项用端点路径片段定位、composable 项用导出符号定位 —— 两者不同，
    所以必须随绑定一起登记，不能让守卫拿 `symbols` 去猜。
    """
    if (site is None) == (absent_reason is None):
        raise Task66GeneratorError(
            "last_call_site 与 absent_reason 必须恰有一个非空 —— "
            f"site={site!r} reason={absent_reason!r}"
        )
    if not needles:
        raise Task66GeneratorError("last_call_site 绑定缺 needles —— 反向守卫无从定位")
    return {
        "site": site,
        "absent_reason": absent_reason,
        "needles": sorted(set(needles)),
        "semantics": (
            "最后一处**引用**点（按 (文件, 行) 字典序最大；含 re-export barrel 与"
            "类型再导出，不只是 `foo(` 形态的调用）"
        ),
    }


def _owner(
    *,
    replacement_owner_task: str,
    replacement_owner_reason: str,
    deletion_owner_task: str,
    known_task_ids: frozenset[str],
) -> dict[str, Any]:
    for task_id in (replacement_owner_task, deletion_owner_task):
        if task_id not in known_task_ids:
            raise Task66GeneratorError(
                f"owner task {task_id!r} 在 tasks.md 里不存在 —— owner 是编的"
            )
    return {
        "replacement_owner_task": replacement_owner_task,
        "replacement_owner_reason": replacement_owner_reason,
        "deletion_owner_task": deletion_owner_task,
        "deletion_owner_source": "per-cycle deletion plan 的 `deletion_execution_owner` 现读",
    }


def _forms_of(
    *,
    disposition: str,
    endpoint_hits: list[str],
    single_switch_entry_ids: list[str],
    fail_open_sites: list[dict[str, Any]],
    production_importer_count: int | None,
    is_replacement_surface: bool,
    unreachable_entry_ids: list[str],
) -> list[str]:
    """五个形态的**派生**（不是声明）。每条都对应一个可现算的事实。"""
    forms: list[str] = []
    if is_replacement_surface and production_importer_count == 0:
        forms.append("unconsumed_bridge")
    if endpoint_hits:
        forms.append("legacy_config_second_request")
    if single_switch_entry_ids:
        forms.append("single_fake_switch")
    if fail_open_sites:
        forms.append("fail_open_success_message")
    if (production_importer_count == 0 and not is_replacement_surface) or unreachable_entry_ids:
        forms.append("unreachable_stub")
    del disposition  # 形态只由事实决定，不许被 disposition 反向影响
    return sorted(set(forms))


def build_items(
    sources: FrontendSources,
    manifest: ManifestFacts,
    git: GitFacts,
    *,
    cycle_owners: dict[str, str],
    known_task_ids: frozenset[str],
    deletion_owner: str,
    pilot_deleted_paths: frozenset[str],
    resolver_rows: list[dict[str, Any]],
    unified_prefix: str,
    legacy_key_pattern: str,
    legacy_key_re: re.Pattern[str],
    ac_11_5_events: list[str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    single_switch_all = set(manifest.single_switch_entries())
    unreachable_all = {
        str(e["entry_id"])
        for e in manifest.entries
        if str(e.get("capability")) == "unreachable"
        or str(e.get("migration_state")) == "unreachable_pending_delete"
    }

    # ── C1/C2：legacy composable 与 legacy factory ─────────────────────────
    legacy_modules = [
        p
        for p in sources.files
        if _LEGACY_COMPOSABLE_NAME.match(p.name) and not _is_test_path(rel(p))
    ]
    if not legacy_modules:
        raise Task66GeneratorError("一个 legacy dual-mode composable 都没找到 —— 分母恒空")
    factory_dir_modules = [
        p
        for p in sources.files
        if p.parent.name == "factories"
        and p.name != "index.ts"
        and not _is_test_path(rel(p))
        and _mode_state_fields(sources.code[p])
    ]
    for path in sorted(set(legacy_modules) | set(factory_dir_modules)):
        rel_path = rel(path)
        if rel_path in pilot_deleted_paths:  # Task 45 已删，不再列一遍
            continue
        code = sources.code[path]
        symbols = exported_symbols(code, path)
        importers = sources.production_importers(path)
        cycle = _cycle_letter_of(path, cycle_owners)
        # 派生 category：无循环字母且被 >=2 个生产模块 import ⇒ 共享工厂/基座
        is_factory = cycle is None and len(importers) >= 2
        category = "legacy_factory" if is_factory else "legacy_composable"
        host_files = importers + [rel_path]
        entry_ids = manifest.entries_for_files(host_files)
        endpoint_hits = _legacy_endpoint_hits(code)
        fail_open = [
            site for site in _success_sites(code) if not _durable_symbols(code)
        ]
        forms = _forms_of(
            disposition="pending_delete",
            endpoint_hits=endpoint_hits,
            single_switch_entry_ids=sorted(set(entry_ids) & single_switch_all),
            fail_open_sites=fail_open,
            production_importer_count=len(importers),
            is_replacement_surface=False,
            unreachable_entry_ids=sorted(set(entry_ids) & unreachable_all),
        )
        site = sources.last_call_site(path, symbols)
        owner_task, owner_reason, owner_letters = cycle_owner_for_paths(
            [rel_path], cycle_owners
        )
        items.append(
            {
                "item_id": f"{category}:{rel_path}",
                "category": category,
                "path": rel_path,
                "symbols": symbols,
                "sha256": sha256_of(path),
                "size_bytes": path.stat().st_size,
                "disposition": "pending_delete",
                "disposition_reason": (
                    "AC 11.1：legacy dual-mode 实现必须收敛到统一 bridge；本模块自带 mode "
                    "状态 + 旧端点/旧键，属第二条路径"
                ),
                "forms": forms,
                "replacement": _replacement_for(category, entry_ids),
                "owner": _owner(
                    replacement_owner_task=str(owner_task),
                    replacement_owner_reason=owner_reason,
                    deletion_owner_task=deletion_owner,
                    known_task_ids=known_task_ids,
                ),
                "last_call_site_binding": _last_call_site_binding(
                    site,
                    None if site else "no_production_importer_at_plan_commit",
                    needles=symbols or [path.stem],
                ),
                "rollback_target": _rollback_target(
                    rel_path, disposition="pending_delete", git=git
                ),
                "required_scenario_evidence": manifest.scenario_evidence(entry_ids),
                "facts": {
                    "cycle_letter": cycle,
                    "owner_cycle_letters": owner_letters,
                    "production_importer_count": len(importers),
                    "production_importers": importers,
                    "test_importer_count": len(sources.test_importers(path)),
                    "legacy_endpoint_literals": endpoint_hits,
                    "mode_state_fields": _mode_state_fields(code),
                    "fail_open_success_sites": fail_open,
                    "durable_ack_symbols": _durable_symbols(code),
                },
            }
        )

    # ── C3：legacy endpoint ────────────────────────────────────────────────
    resolver_owner_by_qualname = {
        str(row["qualname"]): row for row in resolver_rows
    }
    unified_routes = router_routes(SYNC_ROUTER_PY)
    for router_path in LEGACY_ROUTER_PATHS:
        router_rel = rel(router_path)
        for route in router_routes(router_path):
            literal = route["path"] or f"<{route['function']}>"
            call_site_files = [
                rel(p)
                for p in sources.files
                if not _is_test_path(rel(p))
                and any(
                    token and token in sources.code[p]
                    for token in _endpoint_search_tokens(literal)
                )
            ]
            reachable_hosts: set[str] = set()
            for f in call_site_files:
                reachable_hosts.add(f)
                reachable_hosts.update(
                    sources.transitive_production_importers(_REPO / f)
                )
            entry_ids = manifest.entries_for_files(sorted(reachable_hosts))
            matrix_row = resolver_owner_by_qualname.get(route["function"])
            owner_task = str(
                (matrix_row or {}).get("adjudication_owner_task") or deletion_owner
            )
            item_id = f"legacy_endpoint:{route['method']} {router_rel}::{route['function']}"
            first_site = min(
                (
                    {"file": f, "line": _first_line_with(sources.code[_REPO / f], _endpoint_search_tokens(literal)), "snippet": literal}
                    for f in call_site_files
                ),
                key=lambda s: (s["file"], s["line"]),
                default=None,
            )
            items.append(
                {
                    "item_id": item_id,
                    "category": "legacy_endpoint",
                    "path": router_rel,
                    "symbols": [route["function"]],
                    "sha256": sha256_of(router_path),
                    "size_bytes": router_path.stat().st_size,
                    "disposition": (
                        "pending_delete"
                        if _endpoint_is_dedicated_f2_half_loop(router_rel)
                        else "preserved_until_replacement_lands"
                    ),
                    "disposition_reason": (
                        "AC 12.7：F2 专用 to/from 端点属第二套半闭环，迁到统一协议后删除"
                        if _endpoint_is_dedicated_f2_half_loop(router_rel)
                        else "manifest 里 185/186 个 entry 的 canonical_resolver 仍指向本模块 ⇒ "
                        "它是**全局共用路径**，Task 70 之前不得变更、也不进 Stage B 删除清单"
                    ),
                    "forms": [],
                    "replacement": _replacement_for("legacy_endpoint", entry_ids),
                    "owner": _owner(
                        replacement_owner_task=owner_task,
                        replacement_owner_reason=(
                            "Task 12 resolver 矩阵的 `adjudication_owner_task` 现读"
                            if matrix_row
                            else "resolver 矩阵未登记该函数 ⇒ 退回删除执行方"
                        ),
                        deletion_owner_task=deletion_owner,
                        known_task_ids=known_task_ids,
                    ),
                    "last_call_site_binding": _last_call_site_binding(
                        first_site,
                        None if first_site else "no_frontend_call_site_at_plan_commit",
                        needles=list(_endpoint_search_tokens(literal)) or [literal],
                    ),
                    "rollback_target": _rollback_target(
                        router_rel,
                        disposition=(
                            "pending_delete"
                            if _endpoint_is_dedicated_f2_half_loop(router_rel)
                            else "preserved_until_replacement_lands"
                        ),
                        git=git,
                    ),
                    "required_scenario_evidence": manifest.scenario_evidence(entry_ids),
                    "facts": {
                        "route": route,
                        "frontend_call_site_files": sorted(call_site_files),
                        "reachable_host_count": len(reachable_hosts),
                        "resolver_matrix_status": (matrix_row or {}).get("status"),
                        "resolver_matrix_group": (matrix_row or {}).get("group"),
                        "resolver_matrix_blocking_task": (matrix_row or {}).get(
                            "blocking_task"
                        ),
                        "unified_route_count": len(unified_routes),
                    },
                }
            )

    # ── C4：legacy localStorage 键 ─────────────────────────────────────────
    sites = mode_storage_sites(sources)
    by_prefix: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for site in sites:
        by_prefix[site["key_prefix"]].append(site)
    mode_storage_rel = rel(MODE_STORAGE_TS)
    for prefix in sorted(by_prefix):
        prefix_sites = sorted(by_prefix[prefix], key=lambda s: (s["file"], s["line"]))
        probe = f"{prefix}{'' if prefix.endswith((':', '-')) else ':'}wp-uuid"
        covered = bool(legacy_key_re.match(probe))
        is_unified = prefix == unified_prefix
        # 统一键的**唯一**合法写入方是替代面的 mode storage 模块。同一个键被别的文件
        # 自行拼出来就是第二份真源（绕过 `migrateWorkpaperSyncMode` 的幂等迁移）⇒
        # 那些调用点仍属待删，而键本身属替代面。两种身份必须拆成两个 item，
        # 否则「唯一归属」这条判据就得在同一个 item 上二选一。
        groups: list[tuple[str, list[dict[str, Any]], str]] = []
        if is_unified:
            groups.append(("@canonical", canonical_mode_storage_sites(), "replacement"))
            for file_rel in sorted({s["file"] for s in prefix_sites} - {mode_storage_rel}):
                groups.append(
                    (
                        f"@duplicate_writer:{file_rel}",
                        [s for s in prefix_sites if s["file"] == file_rel],
                        "pending_delete",
                    )
                )
        else:
            groups.append(("", prefix_sites, "pending_delete"))

        for suffix, group_sites, disposition in groups:
            files = sorted({s["file"] for s in group_sites})
            entry_ids = manifest.entries_for_files(
                files
                + [
                    h
                    for f in files
                    for h in sources.transitive_production_importers(_REPO / f)
                ]
            )
            last = group_sites[-1]
            key_letter = _cycle_letter_from_prefix(prefix, cycle_owners)
            if key_letter is not None:
                key_owner_task = cycle_owners[key_letter]
                key_owner_reason = (
                    f"键前缀首段循环字母 {key_letter} → tasks.md 该循环的迁移任务"
                )
            else:
                key_owner_task, key_owner_reason, _ = cycle_owner_for_paths(
                    files, cycle_owners
                )
            if disposition == "replacement":
                reason = (
                    "统一键本体（AC 11.8 的迁移目标），由替代面 mode storage 模块独占写入 ⇒ 保留"
                )
            elif is_unified:
                reason = (
                    "该文件自行拼出统一键、绕过 `migrateWorkpaperSyncMode` 的幂等迁移 ⇒ "
                    "第二份真源，调用点待删（键本身保留）"
                )
            else:
                reason = "AC 11.8：按 wpId 的旧键必须幂等迁移到统一键"
            items.append(
                {
                    "item_id": f"legacy_local_storage_key:{prefix}{suffix}",
                    "category": "legacy_local_storage_key",
                    "path": last["file"],
                    "symbols": [prefix],
                    "sha256": sha256_of(_REPO / last["file"]),
                    "size_bytes": (_REPO / last["file"]).stat().st_size,
                    "disposition": disposition,
                    "disposition_reason": reason,
                    "forms": _forms_of(
                        disposition=disposition,
                        endpoint_hits=[],
                        single_switch_entry_ids=sorted(
                            set(entry_ids) & single_switch_all
                        ),
                        fail_open_sites=[],
                        production_importer_count=None,
                        is_replacement_surface=disposition == "replacement",
                        unreachable_entry_ids=[],
                    ),
                    "replacement": _replacement_for(
                        "legacy_local_storage_key", entry_ids
                    ),
                    "owner": _owner(
                        replacement_owner_task=key_owner_task,
                        replacement_owner_reason=key_owner_reason,
                        deletion_owner_task=deletion_owner,
                        known_task_ids=known_task_ids,
                    ),
                    "last_call_site_binding": _last_call_site_binding(
                        {
                            "file": last["file"],
                            "line": last["line"],
                            "snippet": last["snippet"],
                        },
                        None,
                        needles=["getItem", "setItem", "removeItem"],
                    ),
                    "rollback_target": _rollback_target(
                        last["file"], disposition=disposition, git=git
                    ),
                    "required_scenario_evidence": manifest.scenario_evidence(entry_ids),
                    "facts": {
                        "call_sites": group_sites,
                        "call_site_count": len(group_sites),
                        "is_unified_key": is_unified,
                        "key_role": (
                            "canonical_writer"
                            if disposition == "replacement"
                            else "duplicate_writer"
                            if is_unified
                            else "legacy_per_wp_key"
                        ),
                        "covered_by_migration_regex": covered,
                        "migration_regex": legacy_key_pattern,
                        "probe_key": probe,
                        "direct_global_localstorage_call": disposition != "replacement",
                        "storage_access_style": (
                            "injected_storage_port"
                            if disposition == "replacement"
                            else "direct_global_localStorage"
                        ),
                        "unified_key_direct_global_writer_files": sorted(
                            {s["file"] for s in prefix_sites}
                        )
                        if is_unified
                        else None,
                    },
                }
            )

    # ── C5：legacy 状态机（替代面目录内的影子状态机 + fallback-only 编辑器宿主）──
    for path in sorted(sources.files):
        rel_path = rel(path)
        if _is_test_path(rel_path):
            continue
        code = sources.code[path]
        machine_kind = _state_machine_kind(path, code, sources, ac_11_5_events)
        if machine_kind is None:
            continue
        # 清点范围由 source-backed manifest 划定：替代面目录内的影子机始终在范围内；
        # 编辑器宿主必须真的出现在 manifest 的宿主/挂载面上（或被这样的文件 import）。
        in_surface = (
            SYNC_DIR in path.parents
            or manifest.is_manifest_surface_file(rel_path)
            or any(
                manifest.is_manifest_surface_file(f)
                for f in sources.transitive_production_importers(path)
            )
        )
        if not in_surface:
            continue
        symbols = exported_symbols(code, path)
        importers = sources.production_importers(path)
        entry_ids = manifest.entries_for_files(
            importers
            + [rel_path]
            + [h for f in importers for h in sources.transitive_production_importers(_REPO / f)]
        )
        endpoint_hits = _legacy_endpoint_hits(code)
        fail_open = [
            site for site in _success_sites(code) if not _durable_symbols(code)
        ]
        site = sources.last_call_site(path, symbols)
        sm_owner_task, sm_owner_reason, sm_letters = cycle_owner_for_paths(
            [rel_path, *importers], cycle_owners
        )
        items.append(
            {
                "item_id": f"legacy_state_machine:{rel_path}",
                "category": "legacy_state_machine",
                "path": rel_path,
                "symbols": symbols,
                "sha256": sha256_of(path),
                "size_bytes": path.stat().st_size,
                "disposition": "pending_delete",
                "disposition_reason": machine_kind["reason"],
                "forms": _forms_of(
                    disposition="pending_delete",
                    endpoint_hits=endpoint_hits,
                    single_switch_entry_ids=sorted(set(entry_ids) & single_switch_all),
                    fail_open_sites=fail_open,
                    production_importer_count=len(importers),
                    is_replacement_surface=False,
                    unreachable_entry_ids=sorted(set(entry_ids) & unreachable_all),
                ),
                "replacement": _replacement_for("legacy_state_machine", entry_ids),
                "owner": _owner(
                    replacement_owner_task=sm_owner_task,
                    replacement_owner_reason=(
                        f"{sm_owner_reason}；本项的替代动作 = {machine_kind['owner_reason']}"
                    ),
                    deletion_owner_task=deletion_owner,
                    known_task_ids=known_task_ids,
                ),
                "last_call_site_binding": _last_call_site_binding(
                    site,
                    None if site else "no_production_importer_at_plan_commit",
                    needles=symbols or [path.stem],
                ),
                "rollback_target": _rollback_target(
                    rel_path, disposition="pending_delete", git=git
                ),
                "required_scenario_evidence": manifest.scenario_evidence(entry_ids),
                "facts": {
                    "machine_kind": machine_kind["kind"],
                    "owner_cycle_letters": sm_letters,
                    "mode_state_fields": _mode_state_fields(code),
                    "declared_emits": machine_kind["declared_emits"],
                    "ac_11_5_required_events": ac_11_5_events,
                    "missing_ac_11_5_events": machine_kind["missing_events"],
                    "imports_canonical_machine": machine_kind["imports_canonical"],
                    "production_importer_count": len(importers),
                    "production_importers": importers,
                    "legacy_endpoint_literals": endpoint_hits,
                    "fail_open_success_sites": fail_open,
                },
            }
        )

    # ── C6：paragraph_index fallback ───────────────────────────────────────
    gate = word_anchor_gate()
    para_sites = paragraph_fallback_sites()
    by_file: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for site in para_sites:
        by_file[site["file"]].append(site)
    word_entry_ids = sorted(
        str(e["entry_id"])
        for e in manifest.entries
        if str(e.get("document_type")) == "docx"
    )
    for file_rel in sorted(by_file):
        file_sites = sorted(by_file[file_rel], key=lambda s: s["line"])
        last = file_sites[-1]
        items.append(
            {
                "item_id": f"paragraph_index_fallback:{file_rel}",
                "category": "paragraph_index_fallback",
                "path": file_rel,
                "symbols": ["paragraph_index"],
                "sha256": sha256_of(_REPO / file_rel),
                "size_bytes": (_REPO / file_rel).stat().st_size,
                "disposition": "pending_delete",
                "disposition_reason": (
                    "AC 7.1 逐字禁止中文正则/段落绝对索引作回写协议；Task 6 已裁 "
                    "`paragraph_index` 为 failed 锚点，Word 门现读的 blocked_anchors 也含它"
                ),
                "forms": _forms_of(
                    disposition="pending_delete",
                    endpoint_hits=_legacy_endpoint_hits(
                        (_REPO / file_rel).read_text(encoding="utf-8")
                    ),
                    single_switch_entry_ids=[],
                    fail_open_sites=[],
                    production_importer_count=None,
                    is_replacement_surface=False,
                    unreachable_entry_ids=[],
                ),
                "replacement": _replacement_for(
                    "paragraph_index_fallback", word_entry_ids
                ),
                "owner": _owner(
                    replacement_owner_task=_word_lane_owner_task(known_task_ids),
                    replacement_owner_reason=(
                        "Word lane 的锚点协议归 Word entry 门（tasks.md 里的 Word entry gate 任务）"
                    ),
                    deletion_owner_task=deletion_owner,
                    known_task_ids=known_task_ids,
                ),
                "last_call_site_binding": _last_call_site_binding(
                    {"file": file_rel, "line": last["line"], "snippet": last["snippet"]},
                    None,
                    needles=["paragraph_index"],
                ),
                "rollback_target": _rollback_target(
                    file_rel, disposition="pending_delete", git=git
                ),
                "required_scenario_evidence": manifest.scenario_evidence(word_entry_ids),
                "facts": {
                    "sites": file_sites,
                    "producer_site_count": sum(
                        1 for s in file_sites if s["role"] == "producer"
                    ),
                    "consumer_site_count": sum(
                        1 for s in file_sites if s["role"] == "consumer"
                    ),
                    "word_anchor_gate": gate,
                },
            }
        )

    # ── C7：fail-open 成功文案 ─────────────────────────────────────────────
    for path in sorted(sources.files):
        rel_path = rel(path)
        if _is_test_path(rel_path):
            continue
        code = sources.code[path]
        if not _legacy_endpoint_hits(code) and not _LEGACY_COMPOSABLE_NAME.match(path.name):
            continue
        durable = _durable_symbols(code)
        if durable:
            continue
        if not (
            manifest.is_manifest_surface_file(rel_path)
            or _LEGACY_COMPOSABLE_NAME.match(path.name)
            or any(
                manifest.is_manifest_surface_file(f)
                for f in sources.transitive_production_importers(path)
            )
        ):
            continue
        for site in _success_sites(code):
            importers = sources.production_importers(path)
            entry_ids = manifest.entries_for_files([rel_path] + importers)
            msg_owner_task, msg_owner_reason, _ = cycle_owner_for_paths(
                [rel_path], cycle_owners
            )
            items.append(
                {
                    "item_id": f"fail_open_success_message:{rel_path}#L{site['line']}",
                    "category": "fail_open_success_message",
                    "path": rel_path,
                    "symbols": [],
                    "sha256": sha256_of(path),
                    "size_bytes": path.stat().st_size,
                    "disposition": "pending_delete",
                    "disposition_reason": (
                        "AC 11.10 / Property 48：文案真值条件是本地 mode/health 标志，"
                        "文件内没有任何 durable ack 符号 ⇒ 真同步失败也会显示成功"
                    ),
                    "forms": _forms_of(
                        disposition="pending_delete",
                        endpoint_hits=_legacy_endpoint_hits(code),
                        single_switch_entry_ids=sorted(
                            set(entry_ids) & single_switch_all
                        ),
                        fail_open_sites=[site],
                        production_importer_count=len(importers),
                        is_replacement_surface=False,
                        unreachable_entry_ids=sorted(set(entry_ids) & unreachable_all),
                    ),
                    "replacement": _replacement_for(
                        "fail_open_success_message", entry_ids
                    ),
                    "owner": _owner(
                        replacement_owner_task=msg_owner_task,
                        replacement_owner_reason=msg_owner_reason,
                        deletion_owner_task=deletion_owner,
                        known_task_ids=known_task_ids,
                    ),
                    "last_call_site_binding": _last_call_site_binding(
                        {
                            "file": rel_path,
                            "line": site["line"],
                            "snippet": site["snippet"],
                        },
                        None,
                        needles=["success"],
                    ),
                    "rollback_target": _rollback_target(
                        rel_path, disposition="pending_delete", git=git
                    ),
                    "required_scenario_evidence": manifest.scenario_evidence(entry_ids),
                    "facts": {
                        "site": site,
                        "durable_ack_symbols": durable,
                        "truth_condition_is_local_flag": True,
                        "legacy_endpoint_literals": _legacy_endpoint_hits(code),
                    },
                }
            )

    # ── 后处理：删除单位 + 「站点级删除落在共用文件里」的显式登记 ────────────
    preserved_paths = {
        i["path"]
        for i in items
        if i["disposition"] == "preserved_until_replacement_lands"
    }
    for item in items:
        unit = (
            _CATEGORY_DELETION_UNIT[item["category"]]
            if item["disposition"] == "pending_delete"
            else "none"
        )
        item["deletion_unit"] = unit
        item["inside_preserved_file"] = (
            unit in {"call_sites_within_file", "route_within_file"}
            and item["path"] in preserved_paths
        )
    return items


def _endpoint_search_tokens(literal: str) -> tuple[str, ...]:
    """路由路径 → 前端可搜的稳定片段（去掉 `{param}` 占位）。"""
    parts = [seg for seg in re.split(r"\{[^}]*\}|/", literal) if seg and not seg.startswith("<")]
    return tuple(p for p in parts if len(p) >= 5)


def _first_line_with(code: str, tokens: tuple[str, ...]) -> int:
    for idx, line in enumerate(code.split("\n"), 1):
        if any(t in line for t in tokens):
            return idx
    return 0


def _endpoint_is_dedicated_f2_half_loop(router_rel: str) -> bool:
    """AC 12.7 点名的「F2-22/F2-23 专用 to/from 端点」= F2 盘点两个 sync 模块。"""
    return "_f2_stocktake_" in router_rel and router_rel.endswith("_sync.py")


def _cycle_letter_from_prefix(prefix: str, owners: dict[str, str]) -> str | None:
    match = re.match(r"^([a-zA-Z])\d*[-:]", prefix)
    if match:
        letter = match.group(1).upper()
        if letter in owners:
            return letter
    return None


_HOST_CYCLE = re.compile(r"/(?:Gt|use)([A-Z])\d")


def cycle_owner_for_paths(
    paths: list[str], owners: dict[str, str]
) -> tuple[str, str, list[str]]:
    """统一 owner 推导规则（全部七类共用一条规则，不给某一类开小灶）。

    从路径里取循环字母（`…/GtD1NotesReceivable.vue` / `…/useH2DualMode.ts` → `D` / `H`）：
      * 恰好 1 个字母 ⇒ owner = tasks.md 里该循环的迁移任务；
      * 0 个或 ≥2 个字母 ⇒ 跨循环共享路径 ⇒ owner = tasks.md 里
        「A/B/C/S 与跨循环共享」那个任务。
    """
    letters = sorted(
        {
            m.group(1)
            for p in paths
            for m in _HOST_CYCLE.finditer("/" + p)
            if m.group(1) in owners
        }
    )
    shared_letter = "S"
    if shared_letter not in owners:
        raise Task66GeneratorError(
            "tasks.md 里没有「A/B/C/S 与跨循环共享」任务 —— 跨循环 owner 无从派生"
        )
    if len(letters) == 1:
        return (
            owners[letters[0]],
            f"路径里唯一循环字母 {letters[0]} → tasks.md 该循环的迁移任务",
            letters,
        )
    return (
        owners[shared_letter],
        (
            f"路径里取到 {len(letters)} 个循环字母（{letters}）⇒ 跨循环共享路径 → "
            "tasks.md 的 A/B/C/S 与跨循环共享任务"
        ),
        letters,
    )


def _word_lane_owner_task(known_task_ids: frozenset[str]) -> str:
    """从 tasks.md 现算 Word entry 门任务号（标题含 `Word` 且含 `门`/`gate`）。"""
    text = TASKS_MD_PATH.read_text(encoding="utf-8")
    hits: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*-\s\[[ x~\-]\]\s+(\d+)\.\s+(.*)$", line)
        if not match:
            continue
        task_id, title = match.group(1), match.group(2)
        if "Word" in title and ("gate" in title.lower() or "门" in title):
            hits.append(task_id)
    if not hits:
        raise Task66GeneratorError("tasks.md 里找不到 Word 门任务 —— owner 无从派生")
    chosen = sorted(hits, key=int)[0]
    if chosen not in known_task_ids:  # pragma: no cover - 结构上不可能
        raise Task66GeneratorError(f"Word 门任务号 {chosen} 不在 tasks.md 任务集合里")
    return chosen


_DEFINE_EMITS = re.compile(r"defineEmits<\{(.*?)\}>", re.S)
_EMIT_NAME = re.compile(r"['\"]?([a-zA-Z][a-zA-Z\-]*)['\"]?\s*:")


def _state_machine_kind(
    path: pathlib.Path,
    code: str,
    sources: FrontendSources,
    ac_events: list[str],
) -> dict[str, Any] | None:
    """判定某个文件是否是「与替代面并行的第二个模式状态机」。

    两种形态，各有独立判据：
      A. **影子状态机** —— 文件位于替代面目录 `sync/` 内、自带 mode 状态字段，
         却**不 import** canonical 状态机/bridge ⇒ 它在替代面里另开一条路径。
      B. **fallback-only 编辑器宿主** —— 真的挂载 OO DocEditor（`DocsAPI.DocEditor`），
         但 `defineEmits` 缺 AC 11.5 点名的事件（实测只有 `fallback`）。
    """
    imports_canonical = any(
        target in (BRIDGE_TS, BRIDGE_MACHINE_TS) for target in sources.imports.get(path, ())
    )
    fields = _mode_state_fields(code)
    declared: list[str] = []
    match = _DEFINE_EMITS.search(code)
    if match:
        declared = sorted(set(_EMIT_NAME.findall(match.group(1))))
    missing = [e for e in ac_events if e not in declared]

    in_replacement_dir = SYNC_DIR in path.parents
    if in_replacement_dir and fields and not imports_canonical and path.suffix == ".ts":
        return {
            "kind": "shadow_mode_machine_inside_replacement_dir",
            "reason": (
                "位于替代面目录内、自带 mode 状态字段却不 import canonical bridge/状态机 ⇒ "
                "AC 11.1 的「收敛到统一 bridge」在这里被绕开，模式真值来自本地 ref"
            ),
            "owner_reason": "宿主改为直接消费 canonical bridge 后本模块删除",
            "declared_emits": declared,
            "missing_events": missing,
            "imports_canonical": imports_canonical,
        }
    if "DocsAPI.DocEditor" in code and declared and missing:
        return {
            "kind": "fallback_only_editor_host",
            "reason": (
                "真挂载 OO DocEditor 却只声明 "
                f"{declared} 事件，缺 AC 11.5 现读的 {missing} ⇒ 没有 durable API、"
                "只会降级（Property 47）"
            ),
            "owner_reason": "宿主改为渲染 WorkpaperSyncEditorHost 后本组件删除",
            "declared_emits": declared,
            "missing_events": missing,
            "imports_canonical": imports_canonical,
        }
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 7. 替代面清册（`unconsumed_bridge` 形态的分母）
# ═══════════════════════════════════════════════════════════════════════════


def _backend_router_registered(module_stem: str) -> dict[str, Any]:
    """AST 现算某个 router 模块是否真的被 `router_registry` import（后端可达性）。"""
    registry_dir = _BACKEND / "app" / "router_registry"
    hits: list[str] = []
    for path in sorted(registry_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.endswith(module_stem):
                    hits.append(f"{rel(path)}::L{node.lineno}")
    return {"registered": bool(hits), "registration_sites": hits}


def build_replacement_registry(
    sources: FrontendSources, git: GitFacts, legacy_item_paths: frozenset[str]
) -> list[dict[str, Any]]:
    """替代面逐模块事实。**排除**已被列为 legacy item 的路径（唯一归属）。"""
    rows: list[dict[str, Any]] = []
    for path in sorted(SYNC_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".vue"}:
            continue
        rel_path = rel(path)
        if _is_test_path(rel_path) or rel_path in legacy_item_paths:
            continue
        importers = sources.production_importers(path)
        transitive = sources.transitive_production_importers(path)
        outside = [p for p in transitive if not p.startswith(rel(SYNC_DIR) + "/")]
        rows.append(
            {
                "surface_id": f"replacement:{rel_path}",
                "path": rel_path,
                "side": "frontend",
                "disposition": "replacement",
                "sha256": sha256_of(path),
                "tracked_in_git": git.is_tracked(rel_path),
                "direct_production_importers": importers,
                "direct_production_importer_count": len(importers),
                "transitive_production_importer_count": len(transitive),
                "reachable_from_production_host": bool(outside),
                "production_hosts_outside_replacement_dir": outside[:8],
                "test_importer_count": len(sources.test_importers(path)),
            }
        )
    backend_reach = _backend_router_registered("wp_sync_router")
    rows.append(
        {
            "surface_id": f"replacement:{rel(SYNC_ROUTER_PY)}",
            "path": rel(SYNC_ROUTER_PY),
            "side": "backend",
            "disposition": "replacement",
            "sha256": sha256_of(SYNC_ROUTER_PY),
            "tracked_in_git": git.is_tracked(rel(SYNC_ROUTER_PY)),
            "direct_production_importers": backend_reach["registration_sites"],
            "direct_production_importer_count": len(backend_reach["registration_sites"]),
            "transitive_production_importer_count": len(
                backend_reach["registration_sites"]
            ),
            "reachable_from_production_host": backend_reach["registered"],
            "production_hosts_outside_replacement_dir": backend_reach[
                "registration_sites"
            ],
            "test_importer_count": 0,
        }
    )
    if not rows:
        raise Task66GeneratorError("替代面清册为空 —— `unconsumed_bridge` 分母恒空")
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# 8. 五个形态的归属（每条独立断言，不合成集合判据）
# ═══════════════════════════════════════════════════════════════════════════


def build_form_findings(
    items: list[dict[str, Any]], replacement_rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    findings: dict[str, dict[str, Any]] = {}

    unconsumed = [
        row for row in replacement_rows if not row["reachable_from_production_host"]
    ]
    findings["unconsumed_bridge"] = {
        "denominator": len(replacement_rows),
        "denominator_meaning": "替代面模块总数（前端 sync/ 非测试模块 + 统一 coordinator router）",
        "subjects": [
            {
                "subject_id": row["surface_id"],
                "path": row["path"],
                "disposition": "replacement",
                "why": (
                    "该模块（含其 import 链）没有任何替代面目录之外的生产消费方 ⇒ "
                    "additive 注入即死代码（假绿第①源）。它是替代**靶**，不得删除，"
                    "解除动作是让宿主真去消费它"
                ),
                "direct_production_importer_count": row[
                    "direct_production_importer_count"
                ],
                "transitive_production_importer_count": row[
                    "transitive_production_importer_count"
                ],
            }
            for row in unconsumed
        ],
        "count": len(unconsumed),
    }

    for form in (
        "legacy_config_second_request",
        "single_fake_switch",
        "fail_open_success_message",
        "unreachable_stub",
    ):
        subjects = [
            {
                "subject_id": item["item_id"],
                "path": item["path"],
                "disposition": item["disposition"],
                "category": item["category"],
            }
            for item in items
            if form in item["forms"]
        ]
        findings[form] = {
            "denominator": len(items),
            "denominator_meaning": "七类清点对象的 item 总数",
            "subjects": subjects,
            "count": len(subjects),
        }
    return findings


# ═══════════════════════════════════════════════════════════════════════════
# 9. rollback 隔离门
# ═══════════════════════════════════════════════════════════════════════════

#: 门的**约束**（每条都必须被真正度量，不是重言式）。
BINDING_CONSTRAINTS: tuple[dict[str, str], ...] = (
    {
        "constraint_id": "every_pending_delete_has_a_recoverable_rollback_target",
        "statement": "每个 pending_delete 项在 plan commit 上必须是 git tracked，否则删除不可逆",
        "measured_by": "git ls-files 现算的 tracked 集合 ∩ 待删路径",
    },
    {
        "constraint_id": "replacement_surface_is_itself_recoverable",
        "statement": "替代面必须已入库；替代面未入库时「删 legacy 保 replacement」这笔事务整体不可逆",
        "measured_by": "replacement_registry 里 tracked_in_git 为 false 的模块数",
    },
    {
        "constraint_id": "no_path_is_both_replacement_and_pending_delete",
        "statement": "同一路径不得同时出现在替代面清册与待删清单里",
        "measured_by": "两个路径集合求交",
    },
    {
        "constraint_id": "every_form_subject_has_exactly_one_admissible_disposition",
        "statement": "五个形态的每个 subject 的 disposition ∈ {replacement, pending_delete} 且恰有一个",
        "measured_by": "逐 subject 取 disposition 后与封闭词表求交",
    },
    {
        "constraint_id": "shared_paths_are_not_whole_file_deletions",
        "statement": "未过 Task 70 的全局共用路径 / 兼容 endpoint / fallback 不得被整文件删除",
        "measured_by": "preserved 项路径与 `deletion_unit=whole_file` 的待删路径求交",
    },
    {
        "constraint_id": "site_level_deletions_inside_shared_files_are_declared",
        "statement": (
            "落在共用文件内部的站点级删除必须显式标 `inside_preserved_file=true`，"
            "让 Stage B 知道只能删那几行、不能删文件"
        ),
        "measured_by": "逐项重算 `path ∈ preserved_paths` 并与登记值比对",
    },
)


def build_rollback_gate(
    items: list[dict[str, Any]],
    replacement_rows: list[dict[str, Any]],
    form_findings: dict[str, dict[str, Any]],
    git: GitFacts,
) -> dict[str, Any]:
    pending = [i for i in items if i["disposition"] == "pending_delete"]
    preserved = [
        i for i in items if i["disposition"] == "preserved_until_replacement_lands"
    ]
    whole_file_paths = {
        i["path"] for i in pending if i["deletion_unit"] == "whole_file"
    }
    preserved_paths = {i["path"] for i in preserved}
    replacement_paths = {r["path"] for r in replacement_rows}
    unrecoverable = sorted(
        {
            i["path"]
            for i in pending
            if not i["rollback_target"]["recoverable_from_git"]
        }
    )
    untracked_replacement = sorted(
        r["path"] for r in replacement_rows if not r["tracked_in_git"]
    )
    both = sorted(whole_file_paths & replacement_paths)
    bad_form_dispositions: list[dict[str, str]] = []
    for form, finding in form_findings.items():
        for subject in finding["subjects"]:
            if subject["disposition"] not in FORM_ADMISSIBLE_DISPOSITIONS:
                bad_form_dispositions.append(
                    {
                        "form": form,
                        "subject_id": subject["subject_id"],
                        "disposition": subject["disposition"],
                    }
                )
    preserved_whole_file = sorted(preserved_paths & whole_file_paths)
    misdeclared = sorted(
        i["item_id"]
        for i in pending
        if i["deletion_unit"] in {"call_sites_within_file", "route_within_file"}
        and i["inside_preserved_file"] != (i["path"] in preserved_paths)
    )
    checks = {
        "every_pending_delete_has_a_recoverable_rollback_target": {
            "passed": not unrecoverable,
            "violations": unrecoverable,
            "violation_count": len(unrecoverable),
        },
        "replacement_surface_is_itself_recoverable": {
            "passed": not untracked_replacement,
            "violations": untracked_replacement,
            "violation_count": len(untracked_replacement),
        },
        "no_path_is_both_replacement_and_pending_delete": {
            "passed": not both,
            "violations": both,
            "violation_count": len(both),
        },
        "every_form_subject_has_exactly_one_admissible_disposition": {
            "passed": not bad_form_dispositions,
            "violations": bad_form_dispositions,
            "violation_count": len(bad_form_dispositions),
        },
        "shared_paths_are_not_whole_file_deletions": {
            "passed": not preserved_whole_file,
            "violations": preserved_whole_file,
            "violation_count": len(preserved_whole_file),
        },
        "site_level_deletions_inside_shared_files_are_declared": {
            "passed": not misdeclared,
            "violations": misdeclared,
            "violation_count": len(misdeclared),
        },
    }
    declared = {c["constraint_id"] for c in BINDING_CONSTRAINTS}
    if declared != set(checks):
        raise Task66GeneratorError(
            f"BINDING_CONSTRAINTS 与实测 checks 不同集：只声明 {sorted(declared - set(checks))}，"
            f"只实测 {sorted(set(checks) - declared)}"
        )
    return {
        "plan_commit": git.head_commit,
        "binding_constraints": list(BINDING_CONSTRAINTS),
        "checks": checks,
        "verdict": "open" if all(c["passed"] for c in checks.values()) else "blocked",
        "verdict_meaning": (
            "`open` = Task 72 Stage B 在 rollback 维度上可执行（其余门由 Stage A 把守）；"
            "`blocked` = 至少一条约束被违反，Stage B 若照删则该项不可逆"
        ),
        "what_this_gate_does_not_certify": [
            "不认证未裁决/假双向/未验收/stale 五个零（Task 67 报告 + Task 72 Stage A）",
            "不认证任何真实 OO probe 已通过（Task 70）",
            "不授权删除：本任务只生成计划",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 10. Task 12 resolver 矩阵的入向义务（25 行点名 Task 66）
# ═══════════════════════════════════════════════════════════════════════════

#: 入向义务的裁决词表（**派生**自「该模块是否真的碰 OO 回写面」）。
INBOUND_VERDICTS: tuple[str, ...] = (
    "inside_html_oo_writeback_surface",
    "outside_html_oo_writeback_surface",
)


def build_inbound_obligations(
    resolver_rows: list[dict[str, Any]], item_paths: frozenset[str]
) -> dict[str, Any]:
    named: list[dict[str, Any]] = []
    for row in resolver_rows:
        blocking = str(row.get("blocking_task") or "")
        if OWNER_TASK not in re.split(r"[,\s]+", blocking):
            continue
        source_path = str(row["source_path"])
        module = _REPO / source_path
        code = module.read_text(encoding="utf-8", errors="replace") if module.is_file() else ""
        touches = _legacy_endpoint_hits(code)
        verdict = (
            "inside_html_oo_writeback_surface"
            if touches
            else "outside_html_oo_writeback_surface"
        )
        named.append(
            {
                "writer_id": row["writer_id"],
                "source_path": source_path,
                "group": row.get("group"),
                "status": row.get("status"),
                "blocking_task": row.get("blocking_task"),
                "verdict": verdict,
                "legacy_endpoint_literals": touches,
                "listed_as_task66_item": source_path in item_paths,
                "reason": (
                    "模块里现读到 legacy OO 端点字面量 ⇒ 属本清册七类范围"
                    if touches
                    else "模块里零 legacy OO 端点字面量（附件/预览/模板下载等旁路 resolver）⇒ "
                    "不属 HTML↔OO 回写面，Task 66 的七类清点不覆盖它，"
                    "归属仍在 Task 19/20 的 writer 矩阵与 Task 67 的结构复核"
                ),
            }
        )
    if not named:
        raise Task66GeneratorError(
            "resolver 矩阵里没有一行点名 Task 66 —— 入向义务分母恒空，交叉锁失效"
        )
    return {
        "source": rel(RESOLVER_MATRIX_PATH),
        "verdict_vocabulary": list(INBOUND_VERDICTS),
        "rows_naming_task66": len(named),
        "rows": named,
        "counters": {
            "inside_html_oo_writeback_surface": sum(
                1 for r in named if r["verdict"] == "inside_html_oo_writeback_surface"
            ),
            "outside_html_oo_writeback_surface": sum(
                1 for r in named if r["verdict"] == "outside_html_oo_writeback_surface"
            ),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 11. 阻塞前置（BP-66-n；🔴 task-scoped 前缀，不接全局 `BP-NN`）
# ═══════════════════════════════════════════════════════════════════════════


def build_blocking_preconditions(
    replacement_rows: list[dict[str, Any]],
    form_findings: dict[str, dict[str, Any]],
    manifest: ManifestFacts,
    rollback_gate: dict[str, Any],
) -> list[dict[str, Any]]:
    untracked = [r["path"] for r in replacement_rows if not r["tracked_in_git"]]
    unconsumed = [s["path"] for s in form_findings["unconsumed_bridge"]["subjects"]]
    underivable = sorted(
        entry_id
        for entry_id, row in manifest.scenarios.items()
        if row["status"] != "derived"
    )
    adapters = sum(1 for e in manifest.entries if e.get("adapter_id"))
    return [
        {
            "id": "BP-66-1",
            "title": "替代面未被任何生产宿主消费（无消费 bridge）",
            "statement": (
                f"{len(unconsumed)}/{len(replacement_rows)} 个替代面模块在 import 图上"
                "不可从替代面目录之外的生产文件到达 ⇒ 统一 bridge 链目前是死代码；"
                "Stage B 删掉 legacy 后没有可用的替代路径"
            ),
            "owner_task": "67",
            "blocked_paths": unconsumed,
            "release_condition": (
                "宿主真去 import/渲染 `WorkpaperSyncEditorHost` 并由 DOM/network 顺序守卫把关"
            ),
            "evidence": [
                "剥注释后按 specifier 解析的 import 图（本记录 replacement_registry）",
                "🔴 不剥注释时 `GtG7LongTermEquityMain.vue` 的一句说明注释会让 "
                "`WorkpaperSyncEditorHost.vue` 看起来有一个消费方（教训 12）",
            ],
        },
        {
            "id": "BP-66-2",
            "title": "替代面自身未入库 ⇒ rollback 隔离门 blocked",
            "statement": (
                f"{len(untracked)} 个替代面模块在 plan commit 上是 git `??` 未跟踪；"
                "「删 legacy 保 replacement」这笔事务整体不可逆"
            ),
            "owner_task": "72",
            "blocked_paths": sorted(untracked),
            "release_condition": "替代面全部入库后重跑本生成器，门自动转 open",
            "evidence": [
                "`git ls-files` 现算 tracked 集合",
                f"rollback 门 verdict = {rollback_gate['verdict']}",
            ],
        },
        {
            "id": "BP-66-3",
            "title": "required scenario 只能给出探针集合（authority model 未定）",
            "statement": (
                f"manifest 186 个 entry 里 adapter_id 非空 {adapters} 个、approved bundle 供给为 0，"
                "authority model 无从解析；本清册的 scenario 集合是拿枚举值当探针跑出来的，"
                f"另有 {len(underivable)} 个 entry 连 profile 都推不出来（capability/room_model 漂移）"
            ),
            "owner_task": "70",
            "blocked_entry_ids": underivable,
            "release_condition": (
                "approved bundle + published representation 落地后由 Task 70 按真 authority model 重推并刷新 evidence"
            ),
            "evidence": [
                "`evidence.derive_for_manifest_entry` 逐 entry 现算（drift 如实记 error 码）",
                "authority model 敏感性探测：换枚举值 scenario 集合会变",
            ],
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 12. counters（全部现算）
# ═══════════════════════════════════════════════════════════════════════════


def build_counters(
    items: list[dict[str, Any]],
    replacement_rows: list[dict[str, Any]],
    form_findings: dict[str, dict[str, Any]],
    manifest: ManifestFacts,
) -> dict[str, int]:
    by_category = collections.Counter(i["category"] for i in items)
    by_disposition = collections.Counter(i["disposition"] for i in items)
    counters: dict[str, int] = {
        "items_total": len(items),
        "replacement_surface_modules": len(replacement_rows),
        "replacement_surface_untracked": sum(
            1 for r in replacement_rows if not r["tracked_in_git"]
        ),
        "replacement_surface_unreachable_from_production_host": sum(
            1 for r in replacement_rows if not r["reachable_from_production_host"]
        ),
        "manifest_entry_total": len(manifest.entries),
        "manifest_entry_with_adapter": sum(
            1 for e in manifest.entries if e.get("adapter_id")
        ),
        "manifest_entry_scenario_underivable": sum(
            1 for row in manifest.scenarios.values() if row["status"] != "derived"
        ),
        "single_switch_entries": len(manifest.single_switch_entries()),
        "pending_delete_paths_distinct": len(
            {i["path"] for i in items if i["disposition"] == "pending_delete"}
        ),
        "pending_delete_unrecoverable": sum(
            1
            for i in items
            if i["disposition"] == "pending_delete"
            and not i["rollback_target"]["recoverable_from_git"]
        ),
    }
    for category in CATEGORIES:
        counters[f"items_category_{category}"] = by_category.get(category, 0)
    for disposition in DISPOSITIONS:
        counters[f"items_disposition_{disposition}"] = by_disposition.get(disposition, 0)
    for form in FORMS:
        counters[f"form_{form}_subjects"] = form_findings[form]["count"]
    return counters


# ═══════════════════════════════════════════════════════════════════════════
# 13. 装配
# ═══════════════════════════════════════════════════════════════════════════


def build_record() -> dict[str, Any]:
    sources = FrontendSources()
    git = GitFacts()
    manifest = ManifestFacts()
    cycle_owners = cycle_owner_tasks()
    known_task_ids = tasks_md_task_ids()
    deletion_owner = deletion_execution_owner()
    ac_events = ac_11_5_required_events()
    legacy_key_pattern, legacy_key_re = legacy_key_migration_regex()
    unified_prefix = unified_key_prefix()
    resolver_rows = list(load_json(RESOLVER_MATRIX_PATH)["rows"])

    pilot_plan = load_json(PILOT_DELETION_PLAN_PATH)
    pilot_deleted_paths = frozenset(
        str(p["legacy_composable"]["file"]) for p in pilot_plan["pilots"]
    )
    pilot_still_on_disk = sorted(
        path for path in pilot_deleted_paths if (_REPO / path).is_file()
    )
    if pilot_still_on_disk:
        raise Task66GeneratorError(
            "Task 45 计划里已删的 pilot composable 仍在磁盘上："
            f"{pilot_still_on_disk} —— 「以 post-delete 新 evidence 为准」的前提不成立"
        )

    items = build_items(
        sources,
        manifest,
        git,
        cycle_owners=cycle_owners,
        known_task_ids=known_task_ids,
        deletion_owner=deletion_owner,
        pilot_deleted_paths=pilot_deleted_paths,
        resolver_rows=resolver_rows,
        unified_prefix=unified_prefix,
        legacy_key_pattern=legacy_key_pattern,
        legacy_key_re=legacy_key_re,
        ac_11_5_events=ac_events,
    )
    ids = [i["item_id"] for i in items]
    if len(set(ids)) != len(ids):
        dupes = [k for k, v in collections.Counter(ids).items() if v > 1]
        raise Task66GeneratorError(f"item_id 重复：{dupes[:5]}")
    for item in items:
        for field in REQUIRED_BINDINGS:
            if not item.get(field):
                raise Task66GeneratorError(
                    f"{item['item_id']}: 必绑字段 {field} 为空 —— 五个绑定缺一即结构性失效"
                )
        if item["category"] not in CATEGORIES:
            raise Task66GeneratorError(f"{item['item_id']}: category 越出封闭词表")
        if item["disposition"] not in DISPOSITIONS:
            raise Task66GeneratorError(f"{item['item_id']}: disposition 越出封闭词表")
        for form in item["forms"]:
            if form not in FORMS:
                raise Task66GeneratorError(f"{item['item_id']}: form {form!r} 越出封闭词表")
        if item["rollback_target"]["mode"] not in ROLLBACK_MODES:
            raise Task66GeneratorError(f"{item['item_id']}: rollback mode 越出封闭词表")

    legacy_item_paths = frozenset(i["path"] for i in items)
    # 只把**待删**路径从替代面清册里排掉：唯一归属的约束是 replacement ⊥ pending_delete，
    # 已被判为 `replacement` 的路径（如统一键的 canonical 写入方）仍应进替代面清册，
    # 否则它的 tracked 状态就不参与 rollback 隔离门。
    pending_delete_paths = frozenset(
        i["path"] for i in items if i["disposition"] == "pending_delete"
    )
    replacement_rows = build_replacement_registry(sources, git, pending_delete_paths)
    form_findings = build_form_findings(items, replacement_rows)
    rollback_gate = build_rollback_gate(items, replacement_rows, form_findings, git)
    inbound = build_inbound_obligations(resolver_rows, legacy_item_paths)
    blocking = build_blocking_preconditions(
        replacement_rows, form_findings, manifest, rollback_gate
    )
    for bp in blocking:
        if not re.fullmatch(r"BP-66-\d+", bp["id"]):
            raise Task66GeneratorError(f"BP id 必须是 task-scoped 的 BP-66-n：{bp['id']!r}")
    counters = build_counters(items, replacement_rows, form_findings, manifest)

    return {
        "schema_version": SCHEMA_VERSION,
        "task": OWNER_TASK,
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "description": (
            "Task 66 —— 七类 legacy 对象的删前清册、逐项 replacement map（replacement / owner / "
            "最后调用点 / rollback target / 所需 scenario evidence 五绑定）与 rollback 隔离门。"
            "本任务**只生成计划**：不 feature-disable、不删除、不改调用点。"
        ),
        "generator": rel(pathlib.Path(__file__)),
        "why_this_task_only_plans": {
            "statement": (
                "evidence 新鲜度由 source digest 锁定；本任务改任何一个生产文件都会让 "
                "Tasks 44/45/70 的 run 立刻 stale ⇒ Task 72 Stage A 无从判定"
            ),
            "task_body_quote": "不 feature-disable、不删除、不改调用点，避免在 Task 70 前改变 source commit 使 evidence stale",
            "machine_predicate": (
                "守卫用 AST 断言本生成器不 import DB 层、不调用发布链、`write_text` 只对 "
                "OUTPUT_PATH —— 这是「只生成计划不改源码」的机器判据"
            ),
        },
        "plan_commit": git.head_commit,
        "three_way_lock": {
            "source_side": [
                rel(FRONTEND_SRC),
                *[rel(p) for p in LEGACY_ROUTER_PATHS],
                *[rel(p) for p in PARAGRAPH_FALLBACK_PATHS],
            ],
            "replacement_side": [
                f"{rel(MODE_STORAGE_TS)}::LEGACY_KEY_RE",
                f"{rel(MODE_STORAGE_TS)}::WP_SYNC_MODE_KEY_PREFIX",
                "app/services/workpaper_sync/evidence.py::derive_for_manifest_entry",
                "app/services/workpaper_sync/contracts.py::load_word_carrier_gate",
                rel(SYNC_ROUTER_PY),
            ],
            "ledger_side": [
                rel(ENTRY_MANIFEST_PATH),
                rel(LEGACY_BASELINE_PATH),
                rel(PILOT_DELETION_PLAN_PATH),
                rel(RESOLVER_MATRIX_PATH),
                rel(MIGRATION_PARADIGM_PATH),
                rel(TASKS_MD_PATH),
                rel(REQUIREMENTS_PATH),
            ],
            "comment_stripping_is_mandatory": (
                "import 图必须在剥注释后建：`GtG7LongTermEquityMain.vue` 里有一句注释提到 "
                "`WorkpaperSyncEditorHost`，不剥就会把这句**说明文字**算成一个消费方，"
                "「替代面零生产消费方」这条真结论会被打成假绿"
            ),
        },
        "category_vocabulary": list(CATEGORIES),
        "disposition_vocabulary": list(DISPOSITIONS),
        "form_vocabulary": list(FORMS),
        "form_admissible_dispositions": list(FORM_ADMISSIBLE_DISPOSITIONS),
        "rollback_mode_vocabulary": list(ROLLBACK_MODES),
        "required_bindings": list(REQUIRED_BINDINGS),
        "owner_derivation": {
            "rule": (
                "统一一条规则：从路径里取循环字母，恰 1 个 ⇒ 该循环迁移任务；0 或 ≥2 个 ⇒ "
                "A/B/C/S 与跨循环共享任务。endpoint 另用 Task 12 resolver 矩阵的 "
                "`adjudication_owner_task`，paragraph fallback 用 tasks.md 的 Word 门任务"
            ),
            "cycle_owner_tasks": cycle_owners,
            "deletion_execution_owner_task": deletion_owner,
            "deletion_execution_owner_source": (
                "13 份 per-cycle 删除计划的 `deletion_execution_owner` 现读并要求一致"
            ),
        },
        "ac_11_5_required_events": ac_events,
        "unified_mode_key_prefix": unified_prefix,
        "legacy_mode_key_migration_regex": legacy_key_pattern,
        "task45_pilot_post_delete_state": {
            "planned_deletions": sorted(pilot_deleted_paths),
            "still_on_disk": pilot_still_on_disk,
            "note": (
                "Task 45 的四个 pilot composable 已从磁盘消失 ⇒ 本清册不再列它们一遍，"
                "「以其 post-delete 新 evidence 为准」（Task 66 正文第 2 条）"
            ),
        },
        "required_scenario_probe": manifest.probe_sensitivity,
        "manifest_required_scenario_sets": manifest.scenarios,
        "replacement_registry": replacement_rows,
        "form_findings": form_findings,
        "rollback_isolation_gate": rollback_gate,
        "inbound_obligations_from_task12_matrix": inbound,
        "blocking_preconditions": blocking,
        "counters": counters,
        "items": items,
        "requirements_covered": [
            "1.4", "1.5", "1.7",
            "11.1", "11.2", "11.5", "11.8", "11.10",
            "12.7", "12.8", "12.9", "12.13", "12.14",
        ],
        "properties_verified": [
            "Property 3", "Property 46", "Property 47", "Property 48", "Property 51",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 14. CLI
# ═══════════════════════════════════════════════════════════════════════════


def _canonical_text(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="只读：现算并与磁盘记录逐字节比对")
    mode.add_argument("--write", action="store_true", help="现算并落盘")
    args = parser.parse_args(argv)

    record = build_record()
    text = _canonical_text(record)
    if args.write:
        OUTPUT_PATH.write_text(text, encoding="utf-8")
        print(f"[write] {OUTPUT_PATH.name} counters=")
        print(json.dumps(record["counters"], ensure_ascii=False, indent=2))
        return 0
    if not OUTPUT_PATH.is_file():
        raise Task66GeneratorError(
            f"{OUTPUT_PATH.name} 不存在 —— 先跑 `--write`。`--check` 不得因缺文件而报成功"
        )
    on_disk = OUTPUT_PATH.read_text(encoding="utf-8")
    if on_disk != text:
        raise Task66GeneratorError(
            f"{OUTPUT_PATH.name} 与现算结果不一致 —— 三边锁其中一边变了，"
            "请重跑 `--write` 后复核 diff（磁盘 "
            f"{hashlib.sha256(on_disk.encode('utf-8')).hexdigest()[:12]} vs 现算 "
            f"{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}）"
        )
    print(f"[check] {OUTPUT_PATH.name} 与现算逐字节一致")
    print(json.dumps(record["counters"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
