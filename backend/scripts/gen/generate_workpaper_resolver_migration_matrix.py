# -*- coding: utf-8 -*-
"""生成 canonical resolver 迁移矩阵 —— 每个 resolver 分叉的状态由**源码事实**推导。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 12
Requirements: 2.10, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.11, 9.12
Properties: P7 / P39 / P40 / P41 / P42

═══ 为什么状态必须「派生」而不是「手写」═══

任务书要求「旧调用点已真的指向统一 resolver」而不是「新函数存在」。手写
`"status": "migrated"` 是一句**声明**，改回自写路径解析后它照样是绿的 —— 正是
memory 里「假绿第②源：grep 式守卫只查字符串存在」的形态。

因此本生成器对每一行做三件事：

1. 从 Task 3 清册（`workpaper_writer_inventory.json`）取**分母**：全部
   `kind ∈ {resolver, writer_resolver}` 且 `non_canonical_resolver_only or
   multi_resolver` 的行。分母不由本文件决定，故不能靠「少登记一行」蒙过去。
2. 按 `POLICY` 里的模块级裁决（人工判断，很小的一张表）给出**意图**状态。
3. 用 AST 对目标函数体做**证据**判定：
   * `calls_unified_entry` —— 函数体内真有 `resolve_wp_file(...)` /
     `CanonicalResolutionService(...).resolve(...)` / `resolve_within_root(...)`
     等统一入口的**调用**（不是 import 行、不是同名字符串）；
   * `self_written_markers` —— 函数体内是否残留自写路径解析特征
     （`.exists()` 判可达、`parent.parent.parent`、`Path(<x>.file_path)`）。
   最终 `status` = 意图 ∧ 证据：意图为 `migrated` 但证据不成立 ⇒ 输出
   `status="regressed"`，守卫直接红。

用法（仓库根）::

    python backend/scripts/gen/generate_workpaper_resolver_migration_matrix.py --check
    python backend/scripts/gen/generate_workpaper_resolver_migration_matrix.py --apply
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import sys
import tokenize
from pathlib import Path
from typing import Any, Final

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - 老 Python / 非 tty
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_INVENTORY = _BACKEND / "data" / "workpaper_writer_inventory.json"
_MATRIX = _BACKEND / "data" / "workpaper_resolver_migration_matrix.json"

SCHEMA_VERSION: Final[str] = "resolver-migration-matrix:v1"

# ═══════════════════════════════════════════════════════════════════════════
# 1. 统一入口标识（唯一真源；守卫按它断言，禁止在别处硬写字面量）
# ═══════════════════════════════════════════════════════════════════════════

#: 统一 canonical resolver 的入口调用名。任一出现即算「已指向统一入口」。
UNIFIED_ENTRY_CALLS: Final[tuple[str, ...]] = (
    "resolve_wp_file",                 # legacy 路径域唯一入口
    "resolve_template_docx",           # legacy 模板域（docx 类型门）
    "resolve_published_artifact",      # 同步域：published artifact
    "resolve_within_root",             # 路径边界唯一实现
    "join_within_root",                # 同上，返回未 realpath 展开的形态
    "assert_within_root",
    "is_within_any_legacy_root",
    "pick_most_specific",              # 子码最具体匹配唯一实现
    # ── Task 58：Word 域统一入口（`workpaper_sync.word_resolution`）────────
    # 这四个与上面同性质：它们是「往哪读/往哪写」的唯一回答处。登记在这里而不是在
    # 守卫里另写一份，理由与本常量的存在理由相同 —— 判据必须只有一份名单。
    "resolve_word_template",           # wp_code → 最具体 DOCX 模板（类型门 fail closed）
    "resolve_own_docx_or_none",        # 存量 `find_template_file_any` 的委派桥
    "word_canonical_write_target",     # callback 落盘唯一入口
    "onlyoffice_canonical_dir",        # OO 运行态 canonical 目录（读写共用）
    "onlyoffice_canonical_path",
)

#: 自写路径解析的残留特征（正则在**剥注释/docstring 后**匹配）。
#:
#: 🔴 每条都刻意窄化到「真正的分叉形态」，而不是「出现过某个词」：
#: * `bare_exists_reachability` 只认 `if not <x>.exists()` —— 目录存在性检查
#:   （`if not version_dir.exists()`）不是路径解析分叉，误判会逼守卫降标；
#: * `raw_file_path_construction` 只认**赋值**形态 `x = Path(wp.file_path)` ——
#:   把 DB 列绑成 Path 变量供后续文件操作才是分叉；内联取 `.name` 当显示名不是；
#: * `ad_hoc_storage_join` 只认 `"storage" / "projects"` 连拼 —— 单独出现
#:   `"storage"` 字面量（如日志文案）不算。
SELF_WRITTEN_PATTERNS: Final[dict[str, str]] = {
    "bare_exists_reachability": r"if\s+not\s+[\w\.]+\.exists\(\)",
    "manual_backend_root": r"parent\.parent\.parent",
    "raw_file_path_construction": r"=\s*Path\(\s*(?:str\()?\s*\w+\.file_path",
    "ad_hoc_storage_join": r"[\"']storage[\"']\s*/\s*[\"']projects[\"']",
}

# ═══════════════════════════════════════════════════════════════════════════
# 2. 模块级裁决（人工判断；很小，且每条 deferred 都必须写阻塞任务与原因）
# ═══════════════════════════════════════════════════════════════════════════

#: `intended_status`: migrated | deferred
#: `blocking_task` / `reason` 对 deferred 必填。
POLICY: Final[dict[str, dict[str, Any]]] = {
    # ── Task 12 本轮迁移 ────────────────────────────────────────────────
    "app.services.wp_export.wp_file_resolver": {
        "intended_status": "migrated",
        "group": "legacy_file_path",
        "note": "legacy 路径域唯一入口；边界/类型/子码判据委托 canonical_paths",
    },
    "app.services.wp_export.export_engine": {
        "intended_status": "migrated",
        "group": "legacy_file_path",
        "note": "_resolve_docx_template 声明 expected_document_type='docx'（P41 真实消费方）",
    },
    "app.services.wopi_service": {
        "intended_status": "migrated",
        "group": "wopi",
        "note": "check_file_info / get_file / put_file 三处统一走 resolve_wp_file",
    },
    "app.services.wp_storage_service": {
        "intended_status": "migrated",
        "group": "storage_version",
        "note": "save_version / list_versions 统一走 resolve_wp_file",
    },
    # ── 本轮不迁移（每条都写明阻塞任务）────────────────────────────────
    "app.routers.wp_onlyoffice_router": {
        "intended_status": "deferred",
        "group": "oo_room",
        # 21,25,26 是 Task 12 当时登记的阻塞；36 由 Task 30 独立门实测补入（见 reason 末段）。
        "blocking_task": "21,25,26,36",
        # 🔴 `blocking_task` 与 `adjudication_owner_task` 是**两件不同的事**，禁止合并：
        # 前者 = 「什么东西不落地这几行就迁不了」（真实供给阻塞，Task 36 的逐 entry
        # finalizeCandidate），守卫据此要求登记的阻塞任务**真的**把守 approved per-entry
        # contract + candidate finalize 那道发布门；后者 = 「哪一道门的验收卡在这条
        # criterion 上」（裁决归属）。合并成一个字段后，把归属改成 71 会同时把「阻塞必须
        # 真的把守发布门」那条判据指向 Task 71，而 Task 71 不是发布门 —— 判据当场失去意义。
        # 归属两次移交：Task 20 → Task 30 → Task 71（成环理由见 tasks.md 三处正文）。
        "adjudication_owner_task": "71",
        "reason": (
            "OO config/callback 的 substrate 必须是 room/staged representation，"
            "依赖 Task 21 room_service 与 Task 25/26 coordinator；Task 12 只提供 "
            "CanonicalResolutionService.assert_sheet_visibility_target 作为 "
            "Requirement 9.12 的可执行判据，未改 router 调用点。"
            "【Task 30 独立门补记：21/25/26 已落地后仍不可迁移】"
            "统一 resolver 只接受 published representation + approved non-null bundle"
            "（design「现有 wp_onlyoffice_router.py 保留 URL 兼容，但逻辑下沉」一节；"
            "repository.create_representation 走 assert_bundle_usable，"
            "materialize_coordinator 对无 published substrate 抛 SubstrateNotPublishedError）。"
            "而 published representation 只能由 Task 36 finalizeCandidate 在**逐 entry**"
            "人工审核并发布 approved per-entry contract + authority model + non-null bundle "
            "之后产生（Task 36/40–57，Wave 3/4）。故这 4 行的剩余阻塞不是 Task 25/26 而是 "
            "Task 36：在任一 entry 拿到 approved bundle 之前，把 router 改成只经 substrate "
            "取数会让全部底稿的 OO 入口 fail closed；保留 legacy 回退则 multi_resolver 归不了零。"
            "【裁决归属再移交：Task 30 → Task 71】Task 36 依赖 Task 30，故 criterion 留在 "
            "Task 30 即第二次成环；它真正能归零的时点是「每个 entry 都已有 published "
            "representation」，恰是 legacy 回退可删的时点，故归属落到 legacy_delete gate "
            "成员 Task 71（见 adjudication_owner_task；本 criterion 自此不挂 bulk_adapters "
            "gate，否则 Wave 5 的 bulk adapter 迁移会依赖 Wave 7）。Task 30 的门在该 "
            "criterion 移出后判**过**，判据仍锁在 "
            "backend/tests/workpaper_sync/test_task30_closure_gate.py"
        ),
    },
    "app.services.wp_template_finder": {
        # 模块级仍是 deferred：本模块**一半迁移一半没迁移**，逐 writer 覆盖见
        # `POLICY_BY_WRITER`（`find_template_file_any` 已迁移，`find_all_template_files`
        # 仍自己 glob 索引）。用模块级把两者混成同一状态会让矩阵失去逐项可核对性。
        "intended_status": "deferred",
        "group": "template_finder",
        # 🔴 Task 58 已落地，故 blocking 从 58 移交：剩余未迁移的是 **xlsx 多文件底稿**
        # 的模板 glob，它替换成统一 resolver 的时点与 `wp_onlyoffice_router` 同一条 ——
        # 每个 entry 都有 published representation（Task 36 供给），归属落 legacy_delete
        # gate 成员 Task 71（与该行同一先例）。
        "blocking_task": "36",
        "adjudication_owner_task": "71",
        "reason": (
            "【Task 58 已收口的部分】find_template_file_any 的子码判据原先写死 "
            "^A\\d+-\\d+ ⇒ B/S 子码落进主码分支并被「终极回退：用主表」抢到父级 XLSX；"
            "2026-08-29 逐条实测 28 个 word-template wp_code 里 9 个（B18-3-1/B18-3-2/"
            "B2-1/B2-11/B2-3/B2-6/B2-8/B40-1/B40-2）都有自己的 DOCX 却全部解析到父级 "
            "XLSX。现在该函数把自有-DOCX 探测**提到 A-only 分支之前**并委派 "
            "workpaper_sync.word_resolution.resolve_own_docx_or_none（内部走 "
            "canonical_paths.pick_most_specific，类型门 fail closed），"
            "见 POLICY_BY_WRITER 里该 writer 的 migrated 裁决与 "
            "backend/data/workpaper_word_template_adjudication.json 的 50 行裁决清册。"
            "【仍未迁移的部分】find_all_template_files 与 find_template_file 的 xlsx "
            "多文件 glob（范围式命名 `D2-1至D2-4 …xlsx` 等）不在 Word lane 内，"
            "换成统一 resolver 需要该 entry 已有 published representation（Task 36 供给），"
            "与 wp_onlyoffice_router 同一条阻塞，故归属 Task 71"
        ),
    },
    "app.routers.wp_render_strategies._f2_stocktake_plan_sync": {
        "intended_status": "deferred",
        "group": "f2_word",
        "blocking_task": "59,60",
        "reason": "F2 Word lane 的 resolver 由 Task 58/59/60 统一改造，删除第二流程",
    },
    "app.routers.wp_render_strategies._f2_stocktake_summary_sync": {
        "intended_status": "deferred",
        "group": "f2_word",
        "blocking_task": "59,60",
        "reason": "同上（F2 汇总表）",
    },
    "app.routers.excel_html": {
        "intended_status": "deferred",
        "group": "legacy_excel_html",
        "blocking_task": "19",
        "reason": "上传/导入/rollback writer 由 Task 19 迁入 ContentMutationService 时一并换 resolver",
    },
    "app.services.wp_download_service": {
        "intended_status": "deferred",
        "group": "upload_import",
        "blocking_task": "19",
        "reason": (
            "WpUploadService.upload_file 的 ad-hoc storage 拼接属 upload writer，"
            "Task 19 迁入统一 commit 时一并换；download 侧已在用 resolve_wp_file"
        ),
    },
}

#: 逐 writer 覆盖（比模块级更细）。模块内一半迁移一半不迁移时必须用这张表 ——
#: 用模块级裁决会把 `download_pack`（已走统一入口）与 `upload_file`（未迁移）
#: 混成同一状态，矩阵就失去逐项可核对性。
POLICY_BY_WRITER: Final[dict[str, dict[str, Any]]] = {
    "app.services.wp_download_service::WpDownloadService.download_pack": {
        "intended_status": "migrated",
        "group": "legacy_file_path",
        "note": "打包下载已走 resolve_wp_file（wp-export-file-path-resolution），Task 12 继承其边界/类型门",
    },
    "app.services.wp_download_service::WpDownloadService.download_single": {
        "intended_status": "migrated",
        "group": "legacy_file_path",
        "note": "单份下载已走 resolve_wp_file，同上",
    },
    "app.services.wp_export.export_engine::WpExportEngine._export_docx": {
        "intended_status": "migrated",
        "group": "legacy_file_path",
        "note": "经 _resolve_docx_template 走统一入口并声明 docx 类型门",
    },
    # ── Task 58：Word lane 已迁移，Excel 多文件 glob 未迁移 ──────────────────
    "app.services.wp_template_finder::find_template_file_any": {
        "intended_status": "migrated",
        "group": "template_finder",
        "note": (
            "Task 58：自有-DOCX 探测提到 A-only 分支之前并委派 "
            "word_resolution.resolve_own_docx_or_none（→ canonical_paths.pick_most_specific）。"
            "9 个 B 子码由抢父级 XLSX 改为解析自己的 DOCX；1539 个 wp_code 全量比对差异 14 条"
            "（9 个目标 + B2-12/B30-3/B30-4/B30-5/B60 五个同族旁及项），零 None、"
            "find_all_template_files 差异 0"
        ),
    },
    "app.services.wp_template_finder::find_all_template_files": {
        "intended_status": "deferred",
        "group": "template_finder",
        "blocking_task": "36",
        "adjudication_owner_task": "71",
        "reason": (
            "本函数只服务 xlsx 多文件底稿（范围式命名 `D2-1至D2-4 …xlsx`），"
            "不在 Task 58 的 Word lane 内；Task 58 只把它的 A-only 正则提成命名常量"
            "（`_LEGACY_A_ONLY_SUB_CODE_RE`），行为逐字节不变（全量比对差异 0）。"
            "换成统一 resolver 需要该 entry 已有 published representation（Task 36 供给），"
            "与 wp_onlyoffice_router 同一条阻塞，归属 Task 71"
        ),
    },
}

#: 追加的模块级裁决（与上方 `POLICY` 同一张表，分两段只为可读性）。
POLICY.update({
    "app.routers.wp_template": {
        "intended_status": "deferred",
        "group": "custom",
        "blocking_task": "65",
        "reason": "custom 底稿以 xlsx 本体为唯一权威，resolver 收敛由 Task 65 承接",
    },
    "app.services.wp_template_init_service": {
        "intended_status": "deferred",
        "group": "template_provisioning",
        "blocking_task": "17,58",
        "reason": "模板初始化属 provisioning，不是内容解析；instrumentation 发布后由 Task 17/58 一并处理",
    },
    "app.services.wp_xlsx_export_service": {
        "intended_status": "deferred",
        "group": "export_storage",
        "blocking_task": "19,20",
        "reason": "_resolve_template_path 是第 4 份模板路径副本，随 Task 19/20 writer 矩阵归零一并收敛",
    },
    "app.routers.wp_render_config_helpers": {
        "intended_status": "deferred",
        "group": "export_storage",
        "blocking_task": "19,20",
        "reason": "同上（render-config 侧的 _resolve_template_path 副本）",
    },
})

#: 未在 `POLICY` 登记的模块归入此默认裁决。**不是豁免**：它们仍进矩阵、仍是
#: `deferred`，且 `blocking_task` 指向本 spec 的对应 Wave 任务，守卫会数它们。
DEFAULT_POLICY: Final[dict[str, Any]] = {
    "intended_status": "deferred",
    "group": "out_of_task12_scope",
    "blocking_task": "19,20,66,67",
    "reason": (
        "非 Task 12 第 4 条点名的三类分叉（wp_file_resolver / WOPI / storage-version）；"
        "属附件、预览、模板下载、A17x docx sync 等旁路 resolver，"
        "由 Task 19/20 的 writer 矩阵归零与 Task 66/67 删前清册统一裁决"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# 3. 源码事实提取
# ═══════════════════════════════════════════════════════════════════════════


def strip_comments_and_docstrings(src: str) -> str:
    """剥 `#` 注释与 docstring，保留普通字符串字面量。

    🔴 必须剥：本 spec 的改造说明注释里必然写出「反例」（`if not x.exists()`），
    不剥会把说明文字数成真实代码（memory 已记多次踩中）。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    lines = src.splitlines(keepends=True)
    blank: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                blank.add(ln)
    lines = ["\n" if (i + 1) in blank else ln for i, ln in enumerate(lines)]
    joined = "".join(lines)
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(joined).readline))
    except (tokenize.TokenError, IndentationError):
        return joined
    out = joined.splitlines(keepends=True)
    for tok in reversed([t for t in toks if t.type == tokenize.COMMENT]):
        row, col = tok.start[0] - 1, tok.start[1]
        if 0 <= row < len(out):
            line = out[row]
            tail = "\n" if line.endswith("\n") else ""
            out[row] = line[:col].rstrip() + tail
    return "".join(out)


def _qual_name(node: ast.AST, stack: list[str]) -> str:
    return ".".join(stack)


def function_source(src: str, qualname: str) -> str:
    """按 `Class.method` / `func` / `func.<inner>` 取函数源码（AST 精确切片）。

    🔴 不用「声明后第一个 `{`/固定字符窗口」：多行签名与返回类型注解会截错
    （memory 已记）。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ""
    target = qualname.split("::")[-1]
    parts = target.split(".")
    found: list[str] = []

    def walk(node: ast.AST, stack: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            name = getattr(child, "name", None)
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                new_stack = [*stack, str(name)]
                if new_stack[-len(parts):] == parts and isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    seg = ast.get_source_segment(src, child)
                    if seg:
                        found.append(seg)
                walk(child, new_stack)

    walk(tree, [])
    return "\n".join(found)


def called_names(body_src: str) -> set[str]:
    """函数体内**被调用**的名字集合（`f(...)` / `obj.f(...)`）。

    🔴 只收 `ast.Call` 的 func 名，故 import 行、字符串字面量、类型注解里的同名
    标识符不算 —— 「把委托改回自写、只留 import」这类变异必须被抓到
    （既有 `test_wp_file_resolver.py` 的 M7 实测过 GREEN）。
    """
    out: set[str] = set()
    try:
        tree = ast.parse("\n".join(
            line[4:] if line.startswith("    ") else line
            for line in body_src.splitlines()
        ))
    except SyntaxError:
        try:
            tree = ast.parse(body_src)
        except SyntaxError:
            return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name):
            out.add(fn.id)
        elif isinstance(fn, ast.Attribute):
            out.add(fn.attr)
    return out


def module_level_evidence(module_path: Path) -> dict[str, Any]:
    """模块级证据：统一入口调用 + 自写残留特征（剥注释后）。"""
    if not module_path.is_file():
        return {"exists": False, "unified_entry_calls": [], "self_written_markers": []}
    raw = module_path.read_text(encoding="utf-8", errors="replace")
    stripped = strip_comments_and_docstrings(raw)
    calls = called_names(stripped)
    return {
        "exists": True,
        "unified_entry_calls": sorted(c for c in UNIFIED_ENTRY_CALLS if c in calls),
        "self_written_markers": sorted(
            name for name, pattern in SELF_WRITTEN_PATTERNS.items()
            if re.search(pattern, stripped)
        ),
    }


def function_evidence(module_path: Path, qualname: str) -> dict[str, Any]:
    """函数级证据。函数找不到时返回 `found=False`（守卫按它判脚本缺陷）。"""
    if not module_path.is_file():
        return {"found": False, "unified_entry_calls": [], "self_written_markers": []}
    raw = module_path.read_text(encoding="utf-8", errors="replace")
    stripped = strip_comments_and_docstrings(raw)
    body = function_source(stripped, qualname)
    if not body:
        return {"found": False, "unified_entry_calls": [], "self_written_markers": []}
    calls = called_names(body)
    return {
        "found": True,
        "unified_entry_calls": sorted(c for c in UNIFIED_ENTRY_CALLS if c in calls),
        "self_written_markers": sorted(
            name for name, pattern in SELF_WRITTEN_PATTERNS.items()
            if re.search(pattern, body)
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. 矩阵构建
# ═══════════════════════════════════════════════════════════════════════════


def load_inventory() -> dict[str, Any]:
    if not _INVENTORY.is_file():
        raise SystemExit(f"缺少 Task 3 清册: {_INVENTORY}")
    return json.loads(_INVENTORY.read_text(encoding="utf-8"))


def is_resolver_fork(entry: dict[str, Any]) -> bool:
    """是否属「resolver 分叉」分母：resolver/writer_resolver 且非 canonical 或多 resolver。"""
    if entry["kind"] not in ("resolver", "writer_resolver"):
        return False
    verdicts = entry["verdicts"]
    return bool(verdicts["non_canonical_resolver_only"] or verdicts["multi_resolver"])


def resolver_forks(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """矩阵分母 = resolver 分叉 ∪ POLICY 点名模块的全部行。

    🔴 并上「POLICY 点名模块的全部行」是必需的：`WpStorageService.save_version`
    在 Task 3 清册里 `kind=writer`（它自己不解析模板，只用 `file_path`），故不在
    resolver 分叉集合内。但 Task 12 第 4 条明确要求处理 `storage/version` 分叉 ——
    只用 resolver 分母会让这条迁移**根本不出现在矩阵里**，等于没有可核对的判据。
    """
    named_modules = set(POLICY)
    named_writers = set(POLICY_BY_WRITER)
    out = [
        entry for entry in inventory["entries"]
        if is_resolver_fork(entry)
        or entry["module"] in named_modules
        or entry["writer_id"] in named_writers
    ]
    return sorted(out, key=lambda e: e["writer_id"])


def derive_status(*, intended: str, evidence_ok: bool, residue: list[str]) -> str:
    """由「意图 ∧ 证据」派生最终状态 —— **纯函数**，可被真值表守卫锁死。

    🔴 提成纯函数的理由（2026-08-25 变异检验实测）：这段判断原本内联在
    :func:`build_matrix` 里，而当前矩阵没有任何 regressed 行 ⇒ 把判断整段短路成
    `if False:` 之后输出**完全不变**、digest 不变、守卫全绿。也就是说
    「migrated 必须有源码证据」这条判据在那个状态下**不可达**，属无效变异。

    抽成纯函数后，守卫可以对四种输入组合直接断言真值表，判据不再依赖「矩阵里恰好
    存在一个反例行」这个偶然条件。
    """
    if intended != "migrated":
        return intended
    if not evidence_ok or residue:
        return "regressed"
    return "migrated"


def policy_for(module: str, writer_id: str) -> dict[str, Any]:
    """逐 writer 覆盖优先，其次模块级，最后默认。"""
    if writer_id in POLICY_BY_WRITER:
        return POLICY_BY_WRITER[writer_id]
    return POLICY.get(module, DEFAULT_POLICY)


def build_matrix() -> dict[str, Any]:
    inventory = load_inventory()
    rows: list[dict[str, Any]] = []
    module_cache: dict[str, dict[str, Any]] = {}

    for entry in resolver_forks(inventory):
        module = entry["module"]
        qualname = entry["qualname"]
        source_path = _REPO / entry["source_path"]
        pol = policy_for(module, entry["writer_id"])
        if module not in module_cache:
            module_cache[module] = module_level_evidence(source_path)
        mod_ev = module_cache[module]
        fn_ev = function_evidence(source_path, qualname)

        intended = pol["intended_status"]
        # 证据判定分两侧，缺一侧都会假绿：
        #
        # ① **调用侧用模块级**：WOPI 的 `_resolve_put_target` 是模块级 helper，
        #    `check_file_info` / `get_file` / `put_file` 各自调它；只看函数体会把
        #    这类合法委托误判为 regressed。
        # ② **残留侧用函数级**：模块里合法存在的目录检查（`if not version_dir.exists()`）
        #    与显示名取值（`Path(wp.file_path).name`）不是分叉；用模块级会把它们算成
        #    残留，逼守卫降标 —— 而降标之后真正的回退（在 `get_file` 里重写
        #    `fp = Path(wp.file_path)`）也抓不到了。
        evidence_ok = bool(mod_ev["unified_entry_calls"])
        residue = list(fn_ev["self_written_markers"])
        status = derive_status(
            intended=intended, evidence_ok=evidence_ok, residue=residue
        )

        rows.append({
            "writer_id": entry["writer_id"],
            "module": module,
            "qualname": qualname,
            "source_path": entry["source_path"],
            "kind": entry["kind"],
            "domain": entry["adjudication"].get("domain"),
            "is_resolver_fork": is_resolver_fork(entry),
            "group": pol["group"],
            "intended_status": intended,
            "status": status,
            "blocking_task": pol.get("blocking_task"),
            # 裁决归属（哪一道门的验收卡在这一行上），与 `blocking_task`（真实供给阻塞）
            # 分列两个字段。多数行两者同一，故此字段只在 POLICY 显式登记时非空。
            "adjudication_owner_task": pol.get("adjudication_owner_task"),
            "reason": pol.get("reason"),
            "note": pol.get("note"),
            "resolver_identities": entry["resolver_identities"],
            "evidence": {
                "module_unified_entry_calls": mod_ev["unified_entry_calls"],
                "module_self_written_markers": mod_ev["self_written_markers"],
                "function_found": fn_ev["found"],
                "function_unified_entry_calls": fn_ev["unified_entry_calls"],
                "function_self_written_markers": fn_ev["self_written_markers"],
            },
        })

    stats = {
        "row_count": len(rows),
        "resolver_fork_count": sum(1 for r in rows if r["is_resolver_fork"]),
        "migrated": sum(1 for r in rows if r["status"] == "migrated"),
        "deferred": sum(1 for r in rows if r["status"] == "deferred"),
        "regressed": sum(1 for r in rows if r["status"] == "regressed"),
        "by_group": {},
        "by_status": {},
    }
    for r in rows:
        stats["by_group"][r["group"]] = stats["by_group"].get(r["group"], 0) + 1
        stats["by_status"][r["status"]] = stats["by_status"].get(r["status"], 0) + 1

    payload = {
        "schema_version": SCHEMA_VERSION,
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "task": "Wave 1 Task 12",
        "generated_from": "backend/data/workpaper_writer_inventory.json",
        "inventory_digest": inventory.get("inventory_digest"),
        "inventory_source_digest": inventory.get("source_digest"),
        "unified_entry_calls": list(UNIFIED_ENTRY_CALLS),
        "self_written_patterns": dict(SELF_WRITTEN_PATTERNS),
        "policy_modules": sorted(POLICY),
        "policy_writers": sorted(POLICY_BY_WRITER),
        "stats": stats,
        "rows": rows,
    }
    payload["matrix_digest"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in payload.items() if k != "matrix_digest"},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="写入矩阵 JSON")
    ap.add_argument("--check", action="store_true", help="只校验磁盘与源码一致")
    args = ap.parse_args()

    payload = build_matrix()
    text = _dump(payload)

    if args.apply:
        _MATRIX.parent.mkdir(parents=True, exist_ok=True)
        _MATRIX.write_text(text, encoding="utf-8")
        print(f"[apply] {_MATRIX.relative_to(_REPO).as_posix()}")
        print(json.dumps(payload["stats"], ensure_ascii=False, indent=1))
        return 0

    if not _MATRIX.is_file():
        print(f"[check] 矩阵不存在: {_MATRIX}")
        return 1
    on_disk = json.loads(_MATRIX.read_text(encoding="utf-8"))
    if on_disk.get("matrix_digest") != payload["matrix_digest"]:
        print("[check] 矩阵与源码不一致，请重跑 --apply")
        print(f"  on_disk={on_disk.get('matrix_digest')}")
        print(f"  from_source={payload['matrix_digest']}")
        return 1
    if payload["stats"]["regressed"]:
        bad = [r["writer_id"] for r in payload["rows"] if r["status"] == "regressed"]
        print(f"[check] 有 {len(bad)} 行声明 migrated 但源码证据不成立: {bad}")
        return 2
    print(f"[check] OK: {json.dumps(payload['stats'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
