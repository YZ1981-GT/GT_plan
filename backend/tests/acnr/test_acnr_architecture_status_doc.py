r"""T32 守卫：架构提案「现状（2026-10-26）」节逐项复算（design §15.1 / 需求 14.1、14.4；段四审计 F4-01 / F4-02 返工）。

现状节只允许写当前 HEAD 可验证的事实，守卫逐项复算，不信文字：

1. 「已落地：目录与代码现算事实」表：每行的「复算键」必须是本守卫认识的键，「值」与从真实产物
   （global_catalog.json / catalog_report.json / 快照 / 生成器源码 AST）现算的结果逐字相等；
   本守卫认识的键必须全部出现在表里（删行也红）。
2. 「已落地：组件」表：后端行用 AST 确认模块里定义了所列符号、测试文件里有 test_ 函数；
   前端行确认文件存在（TS 符号由 vitest 守卫 acnrArchitectureStatusDoc.spec.ts 用编译器 API 核对）。
3. 「计划中（未落地）」表：每行至少一个任务号，且这些任务在 tasks.md 里仍是 `[ ]`。
4. 节内（表格之外）提到登记的「计划中符号」（如 lock_project_registry、v2_canonical、`--check`）时，
   若该符号在代码里还不存在，同一行必须带一个仍未勾选的任务号——把未落地写成现状即红。
5. 版本格式与 catalog_contract.REGISTRY_VERSION_PATTERN 逐字一致；旧 YYYY.N.N 只能以勘误出现。
6. resolver 模块文档定位为「canonical resolver + legacy 委托」，不得再称「唯一解析入口」（design §15.2 第 2 条）。

节范围 = 「## 现状（2026-10-26）」标题行到下一个顶层「## 」标题行（按标题定位，不写死行号）。
变异证明见 tmp_acnr_foundation/out/段四_修复记录.md（每条判据各一条磁盘变异，在 verify_wt 做）。
"""
from __future__ import annotations

import ast
import json
import re
from functools import lru_cache
from pathlib import Path

import pytest

from app.services.acnr import catalog as cat_mod
from app.services.acnr import catalog_contract as cc

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_ACNR_DATA = _BACKEND / "data" / "acnr"
_DOC = _REPO / "docs" / "proposals" / "address-coordinate-name-registry-architecture.md"
_TASKS = _REPO / ".kiro" / "specs" / "acnr-foundation-defect-closure" / "tasks.md"
_RESOLVER = _BACKEND / "app" / "services" / "acnr" / "resolver.py"
_GENERATOR = _BACKEND / "scripts" / "acnr" / "generate_catalog.py"

_STATUS_HEADING_RE = re.compile(r"^##\s*现状（2026-10-26）\s*$")
_NEXT_H2_RE = re.compile(r"^##\s+")
#: 现状节的显式结束行（标题之后到这一行之前是现状节；之后的「文档体系地图」等是提案原文）。
_END_MARKER = "> —— 现状节到此结束；以下为提案原文（未改动）——"
_TASK_RE = re.compile(r"\bT(\d{2})\b")
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")

H_FACTS = "### 已落地：目录与代码现算事实"
H_COMPONENTS = "### 已落地：组件"
H_PLANNED = "### 计划中（未落地）"

#: 计划中符号 → (任务号, 落地探测方式)。节内提到它而代码里还没有时，同一行必须带仍未勾选的任务号。
_PLANNED_SYMBOLS: dict[str, tuple[str, tuple[str, str]]] = {
    "lock_project_registry": ("T17", ("py_ident", "lock_project_registry")),
    "effective_catalog": ("T12", ("py_ident", "effective_catalog")),
    "project_registry_lock": ("T17", ("file", "backend/app/services/acnr/project_registry_lock.py")),
    "v2_canonical": ("T21", ("file", "backend/app/services/acnr/v2_canonical.py")),
    "acnr_results": ("T15", ("py_ident", "acnr_results")),
    "ACNR_TARGETS_REJECTED": ("T14", ("py_ident", "ACNR_TARGETS_REJECTED")),
    "acnr_target_values": ("T14", ("file", "backend/app/services/custom_query/acnr_target_values.py")),
    "display.py": ("T29", ("file", "backend/app/services/acnr/display.py")),
    "AcnrTargetResults": ("T16", ("file", "audit-platform/frontend/src/components/custom-query/AcnrTargetResults.vue")),
    "AcnrCandidatesHint": ("T31", ("file", "audit-platform/frontend/src/components/acnr/AcnrCandidatesHint.vue")),
    "--check": ("T07", ("cli_flag", "--check")),
    "release_exceptions": ("T07", ("file", "backend/data/acnr/release_exceptions.json")),
    "reconcile_v2_canonical": ("T22", ("file", "backend/scripts/acnr/reconcile_v2_canonical.py")),
    "acnr_bypass_scan": ("T24", ("file", "backend/scripts/check/acnr_bypass_scan.py")),
    "test_only_generator_writes_catalog": ("T07", ("file", "backend/tests/acnr/test_only_generator_writes_catalog.py")),
}

#: py_ident 探测扫描的目录（AST：def / class / 赋值目标 / 注解字段 / 字符串常量）。
_IDENT_SCAN_DIRS = ("backend/app/services/acnr", "backend/app/services/custom_query",
                    "backend/app/routers", "backend/app/models", "backend/scripts/acnr")


# ─── 文档解析 ────────────────────────────────────────────────────────────────


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _status_section(text: str) -> list[str]:
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if _STATUS_HEADING_RE.match(ln.strip())), None)
    assert start is not None, "架构提案缺少「## 现状（2026-10-26）」节（D12 守卫）"
    end = None
    for j in range(start + 1, len(lines)):
        if lines[j].strip() == _END_MARKER:
            end = j
            break
        if _NEXT_H2_RE.match(lines[j]):
            break
    assert end is not None, f"现状节缺少结束行「{_END_MARKER}」（须在下一个顶层标题之前）"
    return lines[start:end]


def _subsection(section: list[str], heading: str) -> list[str]:
    idx = next((i for i, ln in enumerate(section) if ln.strip() == heading), None)
    assert idx is not None, f"现状节缺少子节「{heading}」"
    out: list[str] = []
    for ln in section[idx + 1:]:
        if ln.startswith("### ") or ln.startswith("## "):
            break
        out.append(ln)
    return out


def _cells(row: str) -> list[str]:
    parts = _UNESCAPED_PIPE_RE.split(row.strip())
    return [p.strip() for p in parts[1:-1]]


def _table(lines: list[str]) -> list[list[str]]:
    """子节里第一张 markdown 表的数据行（去掉表头与分隔行）。"""
    rows = [ln for ln in lines if ln.strip().startswith("|")]
    assert len(rows) >= 3, "子节里没有带数据行的表"
    return [_cells(r) for r in rows[2:]]


def _strip_code(s: str) -> str:
    return s.strip().strip("`").strip()


def _section() -> list[str]:
    return _status_section(_read(_DOC))


# ─── 现算事实 ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _catalog_data() -> dict:
    return json.loads((_ACNR_DATA / "global_catalog.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _report_data() -> dict:
    return json.loads((_ACNR_DATA / "catalog_report.json").read_text(encoding="utf-8"))


def _generator_cli_flags() -> list[str]:
    tree = ast.parse(_GENERATOR.read_text(encoding="utf-8"))
    flags: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument":
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("--"):
                    flags.append(a.value)
    return flags


def _imports_module(path: Path, module_tail: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith(module_tail) or any(a.name == module_tail for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(a.name.endswith(module_tail) for a in node.names):
                return True
    return False


def _production_importers(module_tail: str, exclude: Path) -> list[str]:
    """backend/app 与 backend/scripts 中 import 了该模块的生产文件（文本预筛 + AST 判定）。"""
    hits: list[str] = []
    for root in (_BACKEND / "app", _BACKEND / "scripts"):
        for p in root.rglob("*.py"):
            if p.resolve() == exclude.resolve():
                continue
            raw = p.read_bytes()
            if module_tail.encode() not in raw:
                continue
            if _imports_module(p, module_tail):
                hits.append(p.relative_to(_REPO).as_posix())
    return sorted(hits)


@lru_cache(maxsize=1)
def _facts() -> dict[str, str]:
    data = _catalog_data()
    sheets = data.get("sheets", [])
    cells = data.get("cells", [])
    sheet_ids = {s.get("addr_id") for s in sheets}
    orphans = [c for c in cells if c.get("parent_addr_id") not in sheet_ids]
    orphan_codes = sorted({c["parent_addr_id"].rsplit("/", 1)[-1] for c in orphans})
    cycles = sorted({(s.get("parent_wp_code") or "?")[0] for s in sheets})
    domains = sorted({e.get("domain", "") for e in sheets + cells})
    deprecated = sum(1 for e in sheets + cells if e.get("deprecated"))
    roundtrip_ok = sum(
        1 for c in cells
        if c.get("formula_ref") and cat_mod._formula_ref_to_addr_id(c["formula_ref"]) == c.get("addr_id")
    )
    import jsonschema

    schema_errors = sum(1 for _ in jsonschema.Draft7Validator(cc.build_schema()).iter_errors(data))
    flags = _generator_cli_flags()
    gen_uses_gates = _imports_module(_GENERATOR, "catalog_release")
    release_importers = _production_importers(
        "catalog_release", _BACKEND / "app" / "services" / "acnr" / "catalog_release.py")
    shards = sorted(p.name for p in (_ACNR_DATA / "shards").glob("*.json"))
    snapshots = sorted((_ACNR_DATA / "catalog_snapshots").glob("*.json"))
    return {
        "catalog.registry_version": str(data.get("registry_version")),
        "catalog.sheets": str(len(sheets)),
        "catalog.cells": str(len(cells)),
        "catalog.cells_with_parent": str(len(cells) - len(orphans)),
        "catalog.orphan_cells": str(len(orphans)),
        "catalog.orphan_parent_sheet_codes": "、".join(orphan_codes),
        "catalog.deprecated_entries": str(deprecated),
        "catalog.domains": "、".join(domains),
        "catalog.parent_cycles": "、".join(cycles),
        "catalog.formula_ref_roundtrip_ok": str(roundtrip_ok),
        "catalog.schema_errors": str(schema_errors),
        "report.has_release": "是" if "release" in _report_data() else "否",
        "snapshots.count": str(len(snapshots)),
        "shards.files": "、".join(shards) if shards else "无",
        "generator.cli_flags": "、".join(flags),
        "generator.runs_release_gates": "是" if gen_uses_gates else "否",
        "catalog_release.production_importers": str(len(release_importers)),
    }


# ─── 代码存在性（AST） ──────────────────────────────────────────────────────


def _top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _test_function_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1 for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
    )


@lru_cache(maxsize=1)
def _known_idents() -> frozenset[str]:
    idents: set[str] = set()
    for rel in _IDENT_SCAN_DIRS:
        for p in (_REPO / rel).rglob("*.py"):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    idents.add(n.name)
                elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    idents.add(n.id)
                elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                    idents.add(n.target.id)
                elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.isidentifier():
                    idents.add(n.value)
    return frozenset(idents)


def _symbol_landed(probe: tuple[str, str]) -> bool:
    kind, target = probe
    if kind == "file":
        return (_REPO / target).exists()
    if kind == "py_ident":
        return target in _known_idents()
    if kind == "cli_flag":
        return target in _generator_cli_flags()
    raise AssertionError(f"未知探测方式 {kind}")


@lru_cache(maxsize=1)
def _task_states() -> dict[str, bool]:
    """tasks.md 顶层任务 → 是否勾选（`- [x] N.` / `- [ ] N.` / `- [ ]* N.`）。"""
    states: dict[str, bool] = {}
    for ln in _read(_TASKS).split("\n"):
        m = re.match(r"^- \[([ xX])\]\*? (\d+)\. ", ln)
        if m:
            states[f"T{int(m.group(2)):02d}"] = m.group(1).lower() == "x"
    return states


# ─── 1. 节存在 ───────────────────────────────────────────────────────────────


def test_status_section_present_and_has_three_tables():
    section = _section()
    for h in (H_FACTS, H_COMPONENTS, H_PLANNED):
        assert _table(_subsection(section, h)), f"子节「{h}」没有数据行"


# ─── 2. 事实表逐项复算 ───────────────────────────────────────────────────────


def test_fact_table_values_recomputed_from_artifacts():
    rows = _table(_subsection(_section(), H_FACTS))
    facts = _facts()
    seen: set[str] = set()
    problems: list[str] = []
    for row in rows:
        assert len(row) == 3, f"事实表每行须 3 列（事实 | 值 | 复算键）：{row}"
        _label, value, key = row
        key = _strip_code(key)
        value = _strip_code(value)
        if key not in facts:
            problems.append(f"未知复算键 {key!r}（守卫不认识的数字不能写进已落地）")
            continue
        seen.add(key)
        if value != facts[key]:
            problems.append(f"{key}: 文档写 {value!r}，产物现算 {facts[key]!r}")
    missing = sorted(set(facts) - seen)
    if missing:
        problems.append(f"事实表缺少复算键 {missing}")
    assert not problems, "现状节事实与真实产物不符：\n" + "\n".join(problems)


# ─── 3. 组件表 AST 核对 ──────────────────────────────────────────────────────


def test_component_rows_exist_by_ast():
    rows = _table(_subsection(_section(), H_COMPONENTS))
    problems: list[str] = []
    for row in rows:
        assert len(row) == 5, f"组件表每行须 5 列（组件 | 类型 | 模块 | 符号 | 测试）：{row}"
        name, kind, module, symbols, test = row
        module, test = _strip_code(module), _strip_code(test)
        mod_path, test_path = _REPO / module, _REPO / test
        if not mod_path.is_file():
            problems.append(f"{name}: 模块 {module} 不存在")
            continue
        if not test_path.is_file():
            problems.append(f"{name}: 测试 {test} 不存在")
            continue
        syms = [_strip_code(s) for s in re.split(r"[、,，]", symbols) if _strip_code(s)]
        if kind == "后端":
            defined = _top_level_names(mod_path)
            absent = [s for s in syms if s not in defined]
            if absent:
                problems.append(f"{name}: {module} 未定义 {absent}（AST）")
            if _test_function_count(test_path) == 0:
                problems.append(f"{name}: {test} 没有 test_ 函数（AST）")
        elif kind != "前端":
            problems.append(f"{name}: 类型须为 后端 / 前端，得 {kind!r}")
    assert not problems, "现状节组件表与代码不符：\n" + "\n".join(problems)


# ─── 4. 计划中任务仍未勾选 ───────────────────────────────────────────────────


def test_planned_rows_reference_unchecked_tasks():
    rows = _table(_subsection(_section(), H_PLANNED))
    states = _task_states()
    assert len(states) == 33, f"tasks.md 顶层任务应为 33 个，解析到 {len(states)}"
    problems: list[str] = []
    for row in rows:
        assert len(row) == 2, f"计划表每行须 2 列（事项 | 任务）：{row}"
        item, tasks = row
        ids = [f"T{m}" for m in _TASK_RE.findall(tasks)]
        if not ids:
            problems.append(f"计划项缺任务号：{item[:40]}")
        for t in ids:
            if t not in states:
                problems.append(f"{item[:30]}…: 任务 {t} 不在 tasks.md")
            elif states[t]:
                problems.append(f"{item[:30]}…: 任务 {t} 已勾选，不能再写成「计划中」——请移到已落地并补现算")
    assert not problems, "\n".join(problems)


# ─── 5. 计划中符号不得写成现状 ───────────────────────────────────────────────


def test_planned_symbols_outside_tables_carry_unchecked_task():
    states = _task_states()
    problems: list[str] = []
    for ln in _section():
        if ln.strip().startswith("|"):
            continue  # 表格行由上面三条判据核对
        for sym, (task, probe) in _PLANNED_SYMBOLS.items():
            if sym not in ln or _symbol_landed(probe):
                continue
            ids = {f"T{m}" for m in _TASK_RE.findall(ln)}
            if not any(not states.get(t, True) for t in ids):
                problems.append(f"「{sym}」尚未落地（{task}），所在行须带仍未勾选的任务号：{ln.strip()[:80]}")
    assert not problems, "\n".join(problems)


# ─── 6. 版本格式 ─────────────────────────────────────────────────────────────


def test_status_section_version_format_matches_contract():
    section = "\n".join(_section())
    pattern = cc.REGISTRY_VERSION_PATTERN  # '^\\d{14}$'
    assert pattern in section, (
        f"现状节未声明与契约一致的版本格式 {pattern!r}（须与 catalog_contract.REGISTRY_VERSION_PATTERN 单一来源）"
    )
    assert "14 位" in section and "UTC" in section, "现状节须说明 14 位 UTC 时间戳"


def test_status_section_marks_old_format_as_deprecated():
    section = "\n".join(_section())
    if "2026.07.10" in section or "YYYY.N.N" in section:
        assert any(k in section for k in ("过时", "作废", "勘误", "不再使用")), (
            "现状节提到旧版本格式但未标注为过时/勘误"
        )


# ─── 7. resolver 定位措辞 ────────────────────────────────────────────────────


def test_resolver_docstring_positioning():
    """design §15.2 第 2 条：定位为「canonical resolver + legacy 委托」，不得再称唯一解析入口。"""
    doc = ast.get_docstring(ast.parse(_RESOLVER.read_text(encoding="utf-8"))) or ""
    assert "canonical resolver" in doc and "legacy 委托" in doc, (
        "resolver 模块文档须写明「canonical resolver + legacy 委托」定位"
    )
    assert "唯一解析入口" not in doc, "resolver 模块文档仍称「唯一解析入口」（design §15.2 第 2 条要求更正）"


# ─── 判据自检：守卫认识的计划中符号此刻确实都未落地（防登记失效） ───────────


@pytest.mark.parametrize("sym", sorted(_PLANNED_SYMBOLS))
def test_planned_symbol_registry_has_no_stale_entry(sym):
    """登记的计划中符号此刻都未落地（落地了就是失效条目，须删除并把现状节内容移到已落地），
    且其任务仍未勾选（任务已勾而符号不存在 = tasks.md 与代码不符）。"""
    task, probe = _PLANNED_SYMBOLS[sym]
    assert not _symbol_landed(probe), (
        f"「{sym}」已在代码里出现：从 _PLANNED_SYMBOLS 删除本条（失效条目），并更新现状节"
    )
    assert _task_states().get(task) is False, f"「{sym}」未落地但 {task} 已勾选：任务状态与代码不符"
