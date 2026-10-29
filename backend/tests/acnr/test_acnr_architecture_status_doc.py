r"""T32 守卫：架构提案「现状（2026-10-26）」节逐项复算（design §15.1 / 需求 14.1、14.4；段四审计 F4-01 / F4-02 返工）。

现状节只允许写当前 HEAD 可验证的事实，守卫逐项复算，不信文字：

1. 「已落地：目录与代码现算事实」表：每行的「复算键」必须是本守卫认识的键，「值」与从真实产物
   （global_catalog.json / catalog_report.json / 快照 / 生成器源码 AST）现算的结果逐字相等；
   本守卫认识的键必须全部出现在表里（删行也红）。
2. 「已落地：组件」表：后端行用 AST 确认模块里定义了所列符号、测试文件里有 test_ 函数；
   前端行确认文件存在（TS 符号由 vitest 守卫 acnrArchitectureStatusDoc.spec.ts 用编译器 API 核对）。
3. 「计划中（未落地）」表：每行至少一个任务号，且这些任务在 tasks.md 里仍是 `[ ]`。
4. 节内任何一行（含表格单元格与组件描述）提到登记的「计划中符号」（如 lock_project_registry、reconcile_v2_canonical、
   `--check`）时，若该符号在代码里还不存在，同一行必须带一个仍未勾选的任务号——把未落地写成现状即红。
5. 版本格式与 catalog_contract.REGISTRY_VERSION_PATTERN 逐字一致；旧 YYYY.N.N 只能以勘误出现。
6. resolver 的模块与函数文档定位为「canonical resolver + legacy 委托」，不得再称「唯一解析入口 / 方法」
   （design §15.2 第 2 条）。
7. 「已落地」两子节里，事实表「值」列以外出现的阿拉伯数字必须绑定复算键：同一句里写出 `复算键`，且数字等于
   该键的现算值；没有绑定的数字即红（数字一律进事实表或带键）。
8. 完成态措辞（「已…接入 / 清零 / 停用 / 持久化 / 生效 / 删除 / 更正 / 转发…」「现已」「清零」「退出 1/2」
   「写出前运行 / 跑」）必须被 _COMPLETION_CLAIMS 里登记的复算判据证实；「已落地」两子节不接受任务号豁免，
   其余子节同一句带仍未勾选的任务号时视为计划表述。「计划中（未落地）」子节不在此列；「…」引文（勘误引用的旧说法）不计。

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
    "project_registry_lock": ("T17", ("file", "backend/app/services/acnr/project_registry_lock.py")),
    "AcnrCandidatesHint": ("T31", ("file", "audit-platform/frontend/src/components/acnr/AcnrCandidatesHint.vue")),
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
        "catalog.orphan_parent_sheet_codes": "、".join(orphan_codes) if orphan_codes else "无",
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


def test_planned_symbols_carry_unchecked_task():
    """节内每一行（含「已落地」两张表的单元格与组件描述）提到尚未落地的计划中符号，同一行须带未勾选任务号。"""
    states = _task_states()
    problems: list[str] = []
    for ln in _section():
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


#: design §15.2 第 2 条要求更正的过时定位措辞（模块与函数文档都不得出现）。
_RESOLVER_FORBIDDEN = ("唯一解析入口", "唯一解析方法", "四库唯一", "四大消费库的唯一")


def _resolver_doc_problems() -> list[str]:
    tree = ast.parse(_RESOLVER.read_text(encoding="utf-8"))
    problems: list[str] = []
    module_doc = ast.get_docstring(tree) or ""
    if not ("canonical resolver" in module_doc and "legacy 委托" in module_doc):
        problems.append("resolver 模块文档须写明「canonical resolver + legacy 委托」定位")
    owners = [("模块", tree)] + [
        (n.name, n) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    for name, node in owners:
        doc = ast.get_docstring(node) or ""
        hits = [p for p in _RESOLVER_FORBIDDEN if p in doc]
        if hits:
            problems.append(f"resolver {name} 的文档仍称 {hits}（design §15.2 第 2 条要求更正）")
    return problems


def test_resolver_docstring_positioning():
    """design §15.2 第 2 条：模块与每个函数 / 类的文档都按「canonical resolver + legacy 委托」定位，不称唯一入口。"""
    problems = _resolver_doc_problems()
    assert not problems, "\n".join(problems)


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


# ─── 8. 「已落地」两子节：数字必须绑定复算键（段四复审 F4-02 残留） ─────────────

#: 阿拉伯数字（左右不贴英文字母 / 数字 / 下划线 / 点 / 连字符 / §、/、{}：排除 T07、b5fc200e0、§15.2、2026-10-27、\d{14}）
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.\-§/{])\d+(?:\.\d+)?(?![A-Za-z0-9_\-/}])")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_CLAUSE_RE = re.compile(r"[^。；;]+")
_QUOTE_RE = re.compile(r"「[^」]*」")


def _landed_text_units() -> list[tuple[str, str]]:
    """「已落地」两子节里须核数字的文本单元 (位置, 文本)：事实表只取「事实」列（值列由判据 2 复算），其余表格取全部单元格，表外取整行。"""
    section = _section()
    units: list[tuple[str, str]] = []
    for heading in (H_FACTS, H_COMPONENTS):
        lines = _subsection(section, heading)
        rows = [ln for ln in lines if ln.strip().startswith("|")]
        for ln in lines:
            s = ln.strip()
            if not s or ln in rows[:2]:
                continue  # 空行、表头与分隔行
            if s.startswith("|"):
                cells = _cells(ln)
                for c in (cells[:1] if heading == H_FACTS else cells):
                    units.append((f"{heading} 表格「{c[:16]}」", c))
            else:
                units.append((f"{heading} 正文", s))
    return units


def _number_problems(units: list[tuple[str, str]]) -> list[str]:
    facts = _facts()
    problems: list[str] = []
    for where, text in units:
        for clause in _CLAUSE_RE.findall(text):
            nums = _NUMBER_RE.findall(clause)
            if not nums:
                continue
            keys = [k for k in (_strip_code(x) for x in _BACKTICK_RE.findall(clause)) if k in facts]
            if not keys:
                problems.append(f"{where}：数字 {nums} 没有绑定复算键（写进事实表，或同一句写出 `复算键`）：{clause.strip()[:60]}")
                continue
            values = {facts[k] for k in keys}
            bad = [n for n in nums if n not in values]
            if bad:
                problems.append(f"{where}：数字 {bad} 与所绑复算键 {keys} 的现算值 {sorted(values)} 不符：{clause.strip()[:60]}")
    return problems


def test_landed_numbers_bound_to_fact_keys():
    units = _landed_text_units()
    assert len(units) >= 10, f"「已落地」两子节可核文本过少（防空转）：{len(units)}"
    problems = _number_problems(units)
    assert not problems, "已落地子节有未经复算的数字：\n" + "\n".join(problems)


@pytest.mark.parametrize("text,expect_red", [
    # T07 首个合规发布批次后现算 orphan_cells 为 0（此前为 25，两条自检随之对调）
    ("孤儿 cell 已停用（`catalog.orphan_cells` 为 0）", False),
    ("25 个孤儿 cell 已全部停用、孤儿计数已清零", True),            # 复审 R-G3e：数字没有绑定复算键
    ("孤儿 cell 仍在目录里（`catalog.orphan_cells` 为 25）", True),  # 绑定了键但数字与现算不符
    ("生成器（写出前跑门禁；--check 结构化比对，漂移退出 2）", True),  # 复审 R-G3d：退出码数字没有复算键
])
def test_number_rule_self_check(text, expect_red):
    assert bool(_number_problems([("自检", text)])) is expect_red


# ─── 9. 完成态措辞必须被复算判据证实（段四复审 F4-02 残留） ─────────────────────

_COMPLETION_RE = re.compile(
    r"已[^，。；、（）()]{0,8}?(?:接入|接线|启用|上线|落地|发布|支持|打通|修复|补齐|迁移|清零|停用|持久化|落库|生效|删除|下线"
    r"|迁回|重新生成|重生成|统一|实现|完成|更正|转发|创建|改为|加)"
    r"|现已|清零|退出\s*[12]|写出前(?:运行|跑)"
)
_LINKAGE_BUS = _BACKEND / "app" / "routers" / "linkage_bus.py"
_WP_INDEX_RESOLVE = _BACKEND / "app" / "routers" / "wp_index_resolve.py"


def _called_names(path: Path, fn: str | None = None) -> set[str]:
    """path 里（或其中名为 fn 的函数里，含参数默认值）被调用的函数名（AST）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = [tree] if fn is None else [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn
    ]
    names: set[str] = set()
    for root in roots:
        for n in ast.walk(root):
            if isinstance(n, ast.Call):
                names.add(n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", ""))
    return names


def _claim_stale_authz() -> bool:
    return ("assert_project_permission" in _called_names(_LINKAGE_BUS, "stale_impact")
            and "require_project_access" in _called_names(_LINKAGE_BUS, "stale_impact_by_addr"))


def _claim_legacy_forwarding() -> bool:
    tree = ast.parse(_WP_INDEX_RESOLVE.read_text(encoding="utf-8"))
    imported = any(
        isinstance(n, ast.ImportFrom) and n.module == "app.services.acnr.resolver"
        and any(a.name == "full_resolve" for a in n.names) for n in ast.walk(tree)
    )
    return imported and "full_resolve" in _called_names(_WP_INDEX_RESOLVE)


def _claim_version_format() -> bool:
    return cc.REGISTRY_VERSION_PATTERN == r"^\d{14}$" and bool(
        re.match(cc.REGISTRY_VERSION_PATTERN, _facts()["catalog.registry_version"]))


#: 完成态说法 → 复算判据（判据为真才证实该说法）。现在为假的判据只起拦截作用；新增完成态说法须先在这里登记。
_COMPLETION_CLAIMS: list[tuple[str, re.Pattern, object]] = [
    ("写 stale 端点项目鉴权", re.compile(r"已加项目鉴权"), _claim_stale_authz),
    ("legacy 导航门面转发 ACNR", re.compile(r"已转发\s*ACNR"), _claim_legacy_forwarding),
    ("resolver 注释更正", re.compile(r"注释已[^，。；]{0,4}更正"), lambda: not _resolver_doc_problems()),
    ("实施 spec 已创建", re.compile(r"`acnr-foundation-defect-closure`\s*已创建"), lambda: _TASKS.is_file()),
    ("版本号改为 14 位 UTC 时间戳", re.compile(r"版本号已改为\s*14\s*位\s*UTC\s*时间戳"), _claim_version_format),
    ("L1 按 classification 骨架覆盖各循环", re.compile(r"现已按\s*classification\s*骨架覆盖"),
     lambda: bool(_facts()["catalog.parent_cycles"]) and _facts()["catalog.domains"] == "wp"),
    ("发布门禁接入生成器", re.compile(r"已[^，。；、（）()]{0,8}?接入生成器|写出前(?:运行|跑)"),
     lambda: _facts()["generator.runs_release_gates"] == "是"),
    ("孤儿 cell 清零 / 停用", re.compile(r"孤儿[^。；]*?(?:已[^，。；、（）()]{0,8}?停用|清零)"),
     lambda: _facts()["catalog.orphan_cells"] == "0"),
    ("目录条目已停用", re.compile(r"已[^，。；、（）()]{0,8}?停用"), lambda: _facts()["catalog.deprecated_entries"] != "0"),
    ("版本锁持久化", re.compile(r"已[^，。；、（）()]{0,8}?(?:持久化|落库)"),
     lambda: (_REPO / "backend" / "app" / "services" / "acnr" / "project_registry_lock.py").is_file()),
    ("加载期 release 互校生效", re.compile(r"已[^，。；、（）()]{0,8}?生效"), lambda: _facts()["report.has_release"] == "是"),
]


def _completion_scope() -> list[tuple[str, str, bool]]:
    """(子节, 行, 是否「已落地」子节)：现状节除标题行与「计划中（未落地）」子节以外的全部行。"""
    out: list[tuple[str, str, bool]] = []
    current = "导言"
    for ln in _section()[1:]:
        s = ln.strip()
        if s.startswith("### "):
            current = s
            continue
        if s and current != H_PLANNED:
            out.append((current, s, current in (H_FACTS, H_COMPONENTS)))
    return out


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _completion_problems(scope: list[tuple[str, str, bool]]) -> list[str]:
    states = _task_states()
    problems: list[str] = []
    for where, line, landed in scope:
        for clause in _CLAUSE_RE.findall(_QUOTE_RE.sub("", line)):
            phrases = list(_COMPLETION_RE.finditer(clause))
            if not phrases:
                continue
            if not landed and any(states.get(f"T{t}") is False for t in _TASK_RE.findall(clause)):
                continue  # 非「已落地」子节：同一句带仍未勾选的任务号 = 计划表述
            for m in phrases:
                hits = [(name, check) for name, rx, check in _COMPLETION_CLAIMS
                        if any(_overlap(m.span(), x.span()) for x in rx.finditer(clause))]
                if not hits:
                    problems.append(f"{where}：完成态说法「{m.group(0)}」未登记复算判据：{clause.strip()[:70]}")
                problems += [f"{where}：「{m.group(0)}」与现算不符（{name}）：{clause.strip()[:70]}"
                             for name, check in hits if not check()]
    return problems


def test_completion_claims_certified_by_recompute():
    scope = _completion_scope()
    assert len(scope) >= 20, f"现状节可核文本过少（防空转）：{len(scope)}"
    problems = _completion_problems(scope)
    assert not problems, "现状节的完成态说法未被复算证实：\n" + "\n".join(problems)


def test_true_completion_claims_are_in_use():
    """现在为真的判据会证实匹配到的说法，须至少证实现状节里的一句（否则是失效登记，删掉）。"""
    text = "\n".join(_QUOTE_RE.sub("", line) for _w, line, _l in _completion_scope())
    stale = [name for name, rx, check in _COMPLETION_CLAIMS if check() and not rx.search(text)]
    assert not stale, f"这些完成态判据现在为真却没有证实任何一句（失效登记）：{stale}"


@pytest.mark.parametrize("line,landed,expect_red", [
    # T07 首个合规发布批次后「写出前跑门禁」「孤儿已停用」为真；退出码说法的判据已删（现状节不写退出码），写了即未登记
    ("| 目录生成器（写出前跑 catalog_release 门禁；`--check` 结构化比对，漂移退出 2） | 后端 |", True, True),  # R-G3d
    ("| 发布门禁模块（已接入生成器，目录写出前运行） | 后端 |", True, False),                             # R-G3f 现为真
    ("25 个孤儿 cell 已全部停用、孤儿计数已清零。", True, False),                                         # R-G3e 现为真（数字另由数字规则拦）
    ("| 版本锁（已持久化到项目表） | 后端 |", True, True),                                               # T17 未落地
    ("| 发布门禁模块（尚未接入生成器） | 后端 |", True, False),
    ("版本锁已持久化（T17）。", False, False),
    ("版本锁已持久化（T17）。", True, True),  # 「已落地」子节不接受任务号豁免
    ("| 发布门禁模块（已在生成器中启用） | 后端 |", True, True),  # 未登记的完成态动词也红
    ("门禁清单：已经在跑的守卫见上表「测试」列。", True, False),  # 「已经在跑」不是完成态动词
])
def test_completion_rule_self_check(line, landed, expect_red):
    assert bool(_completion_problems([("自检", line, landed)])) is expect_red
