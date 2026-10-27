"""架构提案现状节登记制守卫的切分与判据库（供 test_acnr_status_doc_statements.py 使用，本模块不含测试）。

切分规则与登记口径见 test_acnr_status_doc_statements.py 的文档字符串。判据只读真实产物、源码 AST、tasks.md，
以及（核对引文时）节外原文与 design.md，不读现状节自身。拆成单独模块是因为测试文件受 800 行门禁约束。
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import warnings
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from app.services.acnr import catalog_contract as cc
from tests.acnr.test_acnr_architecture_status_doc import (
    _BACKEND, _DOC, _END_MARKER, _REPO, _RESOLVER, _STATUS_HEADING_RE, _TASK_RE,
    H_COMPONENTS, H_FACTS, H_PLANNED,
    _called_names, _catalog_data, _cells, _facts, _imports_module, _production_importers, _read,
    _resolver_doc_problems, _section, _strip_code, _task_states, _test_function_count, _top_level_names,
)

H_INTRO = "（节首导言）"
H_VERSION = "### 版本号格式"
H_PARALLEL = "### V1 / V2 / legacy 导航的并行关系（现状）"
H_ERRATA = "### 过时陈述勘误（原文保留，仅在此指出）"
#: 子节标题与顺序（新增、改名、调序即红）。
_SUBSECTIONS = (H_FACTS, H_COMPONENTS, H_PLANNED, H_VERSION, H_PARALLEL, H_ERRATA)
#: 三张表的表头（逐字）。其他子节不得出现表格。
_TABLE_HEADERS = {
    H_FACTS: ("事实", "值", "复算键"),
    H_COMPONENTS: ("组件", "类型", "模块", "符号", "测试"),
    H_PLANNED: ("事项", "任务"),
}
_SEPARATOR_CELL_RE = re.compile(r":?-{3,}:?")
#: 表格行须以未转义的竖线收尾：_cells 丢弃最后一个竖线之后的文字，不收尾的行会让尾部文字逃出切分。
_ROW_CLOSED_RE = re.compile(r"(?<!\\)\|$")
_LIST_PREFIX_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")
_OPEN_TO_CLOSE = {"「": "」", "（": "）", "(": ")"}
_SENTENCE_ENDS = frozenset("。；;")


# ─── 陈述单元切分（结构封闭） ────────────────────────────────────────────────


@dataclass(frozen=True)
class Unit:
    subsection: str
    kind: str  # prose / fact / component / planned
    text: str  # 登记键（逐字）
    cols: tuple[str, ...] = ()  # 表格行随单元登记的其余列（事实表只取复算键，不含值）


def _sentences(text: str) -> list[str]:
    """按「。」「；」「;」切句；「」、（）、() 与反引号内不切。返回去掉句末标点、去首尾空白的非空句。"""
    out: list[str] = []
    buf: list[str] = []
    stack: list[str] = []
    in_code = False
    for ch in text:
        if ch == "`":
            in_code = not in_code
        elif not in_code:
            if ch in _OPEN_TO_CLOSE:
                stack.append(_OPEN_TO_CLOSE[ch])
            elif stack and ch == stack[-1]:
                stack.pop()
            elif ch in _SENTENCE_ENDS and not stack:
                sent = "".join(buf).strip()
                if sent:
                    out.append(sent)
                buf = []
                continue
        buf.append(ch)
    sent = "".join(buf).strip()
    if sent:
        out.append(sent)
    return out


def _prose_body(line: str) -> str:
    body = line.strip()
    while body.startswith(">"):
        body = body[1:].lstrip()
    m = _LIST_PREFIX_RE.match(body)
    return body[m.end():] if m else body


def _units_and_structure_problems(section: list[str]) -> tuple[list[Unit], list[str]]:
    """section = 现状节标题行到结束行之前（_section()）。返回 (陈述单元, 结构问题)。"""
    units: list[Unit] = []
    problems: list[str] = []
    if not section or not _STATUS_HEADING_RE.match(section[0].strip()):
        return units, ["现状节首行不是「## 现状（2026-10-26）」"]
    current = H_INTRO
    headings: list[str] = []
    rows: dict[str, list[list[str]]] = {}
    for ln in section[1:]:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            headings.append(s)
            current = s
            if s not in _SUBSECTIONS:
                problems.append(f"未登记的标题：{s}")
            continue
        if s.startswith("|"):
            if not _ROW_CLOSED_RE.search(s):
                problems.append(f"表格行须以竖线收尾（最后一个竖线之后的文字不进任何单元）：{s[-60:]}")
            if current not in _TABLE_HEADERS:
                problems.append(f"子节「{current}」不应有表格：{s[:60]}")
            else:
                rows.setdefault(current, []).append(_cells(s))
            continue
        units += [Unit(current, "prose", sent) for sent in _sentences(_prose_body(s))]
    if headings != list(_SUBSECTIONS):
        problems.append(f"子节标题或顺序与登记不符：{headings}")
    for heading, header in _TABLE_HEADERS.items():
        table = rows.get(heading, [])
        if len(table) < 3:
            problems.append(f"「{heading}」缺表格或没有数据行")
            continue
        if tuple(table[0]) != header:
            problems.append(f"「{heading}」表头应为 {header}，得 {tuple(table[0])}")
        if len(table[1]) != len(header) or not all(_SEPARATOR_CELL_RE.fullmatch(c) for c in table[1]):
            problems.append(f"「{heading}」第二行不是分隔行：{table[1]}")
        for r in table[2:]:
            if len(r) != len(header):
                problems.append(f"「{heading}」行列数应为 {len(header)}：{r}")
                continue
            if heading == H_FACTS:
                units.append(Unit(heading, "fact", r[0], (r[2],)))
            elif heading == H_COMPONENTS:
                units.append(Unit(heading, "component", r[0], tuple(r[1:])))
            else:
                units.append(Unit(heading, "planned", r[0], (r[1],)))
    return units, problems


@lru_cache(maxsize=1)
def _parsed() -> tuple[tuple[Unit, ...], tuple[str, ...]]:
    units, problems = _units_and_structure_problems(_section())
    return tuple(units), tuple(problems)


def _units_of(kind: str) -> list[Unit]:
    return [u for u in _parsed()[0] if u.kind == kind]


def _task_ids(cell: str) -> list[str]:
    return [f"T{m}" for m in _TASK_RE.findall(cell)]


# ─── 判据（只读真实产物、源码 AST、tasks.md；引文核对读节外原文与 design.md） ────────

Check = tuple[str, Callable[[], bool]]

_RESOLVER_REL = "backend/app/services/acnr/resolver.py"
_GEN_REL = "backend/scripts/acnr/generate_catalog.py"
_LINKAGE_REL = "backend/app/routers/linkage_bus.py"
_V2_REL = "backend/app/routers/address_registry_v2.py"
_STALE_REL = "backend/app/services/stale_propagation_engine.py"
_SCHEMA_REL = "docs/acnr/schemas/global_catalog.schema.json"
_STATUS_GUARD_REL = "backend/tests/acnr/test_acnr_architecture_status_doc.py"
_THIS_REL = "backend/tests/acnr/test_acnr_status_doc_statements.py"
_FE_GUARD_REL = "audit-platform/frontend/src/services/acnr/tests/acnrArchitectureStatusDoc.spec.ts"
_TASKS_REL = ".kiro/specs/acnr-foundation-defect-closure/tasks.md"
_DESIGN = _REPO / ".kiro" / "specs" / "acnr-foundation-defect-closure" / "design.md"
#: 插入现状节之前（96fba2c49^）提案原文的 LF 内容 sha256。现算：节外文本（见 _outside_lines）与
#: `git show 96fba2c49^:docs/proposals/address-coordinate-name-registry-architecture.md` 逐字相同，
#: 两者 sha256 都是这个值（tmp_acnr_foundation/probes/fix4r3/p02_outside_text.py）。
_ORIGINAL_SHA256 = "441a0405ee26094b247691f5c1f22759b8caa675e90ab4fbbc4878fa8976cdf7"


@lru_cache(maxsize=None)
def _tree(rel: str) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse((_REPO / rel).read_text(encoding="utf-8"))


def _func(rel: str, name: str) -> ast.AST | None:
    return next((n for n in ast.walk(_tree(rel))
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), None)


def _ids(xs: tuple[str, ...]) -> str:
    return "、".join(xs)


def task_open(*ids: str) -> Check:
    return (f"tasks.md 里 {_ids(ids)} 仍为 [ ]", lambda: all(_task_states().get(t) is False for t in ids))


def task_done(*ids: str) -> Check:
    return (f"tasks.md 里 {_ids(ids)} 已勾选", lambda: all(_task_states().get(t) is True for t in ids))


@lru_cache(maxsize=None)
def _task_states_at(commit: str) -> dict[str, bool]:
    """历史提交里 tasks.md 顶层任务 → 是否勾选（`git show <commit>:<tasks.md>`；取不到即空表，判据随之不成立）。"""
    import subprocess

    rel = (_REPO / ".kiro" / "specs" / "acnr-foundation-defect-closure" / "tasks.md").relative_to(_REPO).as_posix()
    proc = subprocess.run(["git", "-C", str(_REPO), "show", f"{commit}:{rel}"], capture_output=True)
    if proc.returncode != 0:
        return {}
    states: dict[str, bool] = {}
    for ln in proc.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n"):
        m = re.match(r"^- \[([ xX])\]\*? (\d+)\. ", ln)
        if m:
            states[f"T{int(m.group(2)):02d}"] = m.group(1).lower() == "x"
    return states


def task_open_at(commit: str, *ids: str) -> Check:
    """历史陈述（「某提交时尚未实施」）的判据：该提交的 tasks.md 里这些任务为 [ ]，不随之后的勾选失效。"""
    return (f"提交 {commit} 的 tasks.md 里 {_ids(ids)} 为 [ ]",
            lambda: (st := _task_states_at(commit)) != {} and all(st.get(t) is False for t in ids))


def fact_eq(key: str, value: str) -> Check:
    return (f"现算 {key} = {value}", lambda: _facts()[key] == value)


def fact_ne(key: str, value: str) -> Check:
    return (f"现算 {key} ≠ {value}", lambda: _facts()[key] != value)


def exists(rel: str) -> Check:
    return (f"{rel} 存在", lambda: (_REPO / rel).exists())


def absent(rel: str) -> Check:
    return (f"{rel} 不存在", lambda: not (_REPO / rel).exists())


def defines(rel: str, *names: str) -> Check:
    return (f"{rel} 定义 {_ids(names)}（AST）",
            lambda: (_REPO / rel).is_file() and set(names) <= _top_level_names(_REPO / rel))


def has_tests(rel: str, *names: str) -> Check:
    def ok() -> bool:
        if not (_REPO / rel).is_file():
            return False
        got = {n.name for n in ast.walk(_tree(rel)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        return set(names) <= got
    return (f"{rel} 有测试 {_ids(names)}（AST）", ok)


def calls(rel: str, fn: str, *names: str) -> Check:
    return (f"{rel} 的 {fn} 调用 {_ids(names)}（AST）", lambda: set(names) <= _called_names(_REPO / rel, fn))


def not_calls(rel: str, *names: str) -> Check:
    return (f"{rel} 不调用 {_ids(names)}（AST）", lambda: not set(names) & _called_names(_REPO / rel))


def not_imports(rel: str, module_tail: str) -> Check:
    return (f"{rel} 不导入 {module_tail}（AST）", lambda: not _imports_module(_REPO / rel, module_tail))


def claim(label: str, fn: Callable[[], bool]) -> Check:
    return (label, fn)


# ─── 节外原文与引文核对 ──────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s")


@lru_cache(maxsize=1)
def _outside_lines() -> tuple[str, ...]:
    """节外原文：现状节标题行之前 + 结束行之后（结束行后紧跟的一个空行是插入本节带进来的分隔，去掉）。"""
    lines = _read(_DOC).split("\n")
    start = next(i for i, ln in enumerate(lines) if _STATUS_HEADING_RE.match(ln.strip()))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == _END_MARKER)
    after = lines[end + 1:]
    if after and not after[0].strip():
        after = after[1:]
    return tuple(lines[:start] + after)


@lru_cache(maxsize=1)
def _outside_with_headings() -> tuple[tuple[str, str], ...]:
    """节外原文逐行 (所在的最近标题, 行)；代码块内以 # 开头的行不算标题。"""
    out: list[tuple[str, str]] = []
    heading, fenced = "", False
    for ln in _outside_lines():
        if _FENCE_RE.match(ln):
            fenced = not fenced
        elif not fenced and _MD_HEADING_RE.match(ln):
            heading = ln.strip()
        out.append((heading, ln))
    return tuple(out)


def outside_unchanged() -> Check:
    return ("节外文本与 96fba2c49^ 提案原文逐字相同（LF 内容 sha256 钉住）",
            lambda: hashlib.sha256("\n".join(_outside_lines()).encode("utf-8")).hexdigest() == _ORIGINAL_SHA256)


def quote_at(quote: str, heading: str, line_has: str = "") -> Check:
    where = f"（同一行含「{line_has}」）" if line_has else ""
    return (f"节外原文「{heading}」下有一行逐字含「{quote}」{where}",
            lambda: any(h == heading and quote in ln and line_has in ln for h, ln in _outside_with_headings()))


def design_quote(quote: str, heading_prefix: str) -> Check:
    def ok() -> bool:
        lines = _read(_DESIGN).split("\n")
        start = next((i for i, ln in enumerate(lines) if ln.startswith(heading_prefix)), None)
        if start is None:
            return False
        body: list[str] = []
        for ln in lines[start + 1:]:
            if ln.startswith("## ") or ln.startswith("### "):
                break
            body.append(ln)
        return quote in "\n".join(body)
    return (f"design.md「{heading_prefix}」节逐字含「{quote}」", ok)


# ─── 领域判据（陈述里的具体说法） ────────────────────────────────────────────


def _schema_props(entry: str) -> dict:
    return cc.build_schema()["$defs"][entry]["properties"]


def _schema_file_is_generated() -> bool:
    raw = (_REPO / _SCHEMA_REL).read_bytes().decode("utf-8").replace("\r\n", "\n")
    return raw == cc.schema_json()


def _functional_types_follow_catalog() -> bool:
    actual = {s["functional_type"] for s in _catalog_data().get("sheets", []) if s.get("functional_type")}
    declared = set(_schema_props("SheetCatalogEntry")["functional_type"]["enum"])
    return bool(actual) and declared == actual == set(cc.FUNCTIONAL_TYPES)


def _item_id_allows_array() -> bool:
    one_of = _schema_props("SheetCatalogEntry")["import_export"]["properties"]["item_id"]["oneOf"]
    return any(o.get("type") == "array" for o in one_of)


SCHEMA_FOLLOWS_CONTRACT: tuple[Check, ...] = (
    claim("schema 文件与 catalog_contract.schema_json() 逐字相同（LF）", _schema_file_is_generated),
    claim("purpose 用受控模式而不是枚举", lambda: _schema_props("CellCatalogEntry")["purpose"].get("pattern")
          == cc.PURPOSE_PATTERN and "enum" not in _schema_props("CellCatalogEntry")["purpose"]),
    claim("functional_type 枚举 = 目录里实际出现的取值", _functional_types_follow_catalog),
    claim("registry_version 用时间戳模式 ^\\d{14}$", lambda: cc.build_schema()["properties"]["registry_version"]
          ["pattern"] == cc.REGISTRY_VERSION_PATTERN == r"^\d{14}$"),
    claim("import_export.item_id 允许数组", _item_id_allows_array),
)


def _orphan_ids() -> set[str]:
    data = _catalog_data()
    sheet_ids = {s.get("addr_id") for s in data.get("sheets", [])}
    return {c["addr_id"] for c in data.get("cells", []) if c.get("parent_addr_id") not in sheet_ids}


def _orphans_have_deprecate_verdicts() -> bool:
    sv = json.loads((_BACKEND / "data" / "acnr" / "sources" / "sheet_verdicts.json").read_text(encoding="utf-8"))
    deprecate = {c.get("addr_id") for c in sv.get("cell_verdicts", []) if c.get("verdict") == "deprecate"}
    return bool(_orphan_ids()) and _orphan_ids() == deprecate


_PURE_STDLIB = {"__future__", "re", "dataclasses", "typing", "functools", "itertools", "collections", "enum"}
_PURE_LOCAL = {"reasons", "catalog_contract", "catalog"}
_IO_CALLS = {"open", "read_text", "read_bytes", "write_text", "write_bytes", "execute"}


def _exact_identity_is_pure() -> bool:
    """只导入标准库与本包 reasons / catalog_contract / catalog，不调用文件或数据库读写（AST）。"""
    for n in ast.walk(_tree("backend/app/services/acnr/exact_identity.py")):
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] not in _PURE_STDLIB for a in n.names):
            return False
        if isinstance(n, ast.ImportFrom):
            mods = [n.module or ""] if n.level == 0 else ([n.module] if n.module else [a.name for a in n.names])
            allowed = _PURE_STDLIB if n.level == 0 else _PURE_LOCAL
            if any(m.split(".")[0] not in allowed for m in mods):
                return False
        if isinstance(n, ast.Call):
            f = n.func
            if (f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")) in _IO_CALLS:
                return False
    return True


def _exact_identity_only_release_imports() -> bool:
    """生产导入方恰为目录写法解析（catalog，T10）、发布门禁与生成器名称规则（T06）、单元格取值接线（T12）；
    V2 / stale（T21）、CCR 检查器（T22）尚未接入。"""
    return _production_importers_of("exact_identity") == [
        "backend/app/services/acnr/catalog.py", "backend/app/services/acnr/catalog_names.py",
        "backend/app/services/acnr/catalog_release.py", "backend/app/services/acnr/wp_cell_target.py"]


def _production_importers_of(module: str) -> list[str]:
    """backend/app 与 backend/scripts 里 import 了 ``module`` 的生产文件（排除同名模块自身；AST）。"""
    own = [p for p in (_BACKEND / "app").rglob(f"{module}.py")]
    exclude = own[0] if len(own) == 1 else _BACKEND / "__no_such_file__.py"
    return _production_importers(module, exclude)


def _full_resolve_step1_uses_exact_identity() -> bool:
    """full_resolve 第 1 步调 step1_identity，后者经 catalog 的结构化判定调 exact_identity.sheet_of（AST）；
    catalog 里已不存在按 sheet_code 子串取最长的旧启发式（`code in sheet_name` 形态）。"""
    def _calls(rel: str, func: str, name: str) -> bool:
        f = _func(rel, func)
        return f is not None and any(isinstance(n, ast.Call) and (getattr(n.func, "id", None) == name
                                     or getattr(n.func, "attr", None) == name) for n in ast.walk(f))
    cat_rel = "backend/app/services/acnr/catalog.py"
    rid_rel = "backend/app/services/acnr/resolve_identity.py"
    substring = any(isinstance(n, ast.Compare) and any(isinstance(op, ast.In) for op in n.ops)
                    and isinstance(n.left, ast.Name) and n.left.id == "code"
                    for n in ast.walk(_tree(cat_rel)))
    return (_calls(_RESOLVER_REL, "full_resolve", "step1_identity")
            and _calls(rid_rel, "step1_identity", "_formula_ref_to_sheet_match")
            and _calls(rid_rel, "step1_identity", "_uri_to_sheet_match")
            and _calls(cat_rel, "_sheet_match", "sheet_of") and not substring)


def _orphan_verdicts_released() -> bool:
    """sheet_verdicts 里 kind=orphan 的 cell 全部仍在目录、已停用、父 sheet 已补登（首个合规发布批次）。"""
    sv = json.loads((_BACKEND / "data" / "acnr" / "sources" / "sheet_verdicts.json").read_text(encoding="utf-8"))
    ids = {c.get("addr_id") for c in sv.get("cell_verdicts", []) if c.get("kind") == "orphan"}
    data = _catalog_data()
    sheets = {s.get("addr_id") for s in data.get("sheets", [])}
    cells = {c.get("addr_id"): c for c in data.get("cells", [])}
    return bool(ids) and all(i in cells and cells[i].get("deprecated") and cells[i].get("parent_addr_id") in sheets
                             for i in ids)


def _non_wp_delegated_to_v1() -> bool:
    domains: set[str] = set()
    for n in _tree(_RESOLVER_REL).body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_NON_WP_DOMAINS" for t in n.targets):
            domains = set(ast.literal_eval(n.value))
    delegate = _func(_RESOLVER_REL, "_delegate_v1")
    v1 = delegate is not None and any(
        isinstance(n, ast.ImportFrom) and n.module == "app.services.address_registry" for n in ast.walk(delegate))
    return {"tb", "report", "note", "aux"} <= domains and v1 and "_delegate_v1" in _called_names(_RESOLVER, "full_resolve")


def _v1_direct_importers() -> list[str]:
    """backend/app 里绕过 ACNR 直接导入 V1（app.services.address_registry）的文件（不含 acnr 包、V1 自身与 V1 路由）。"""
    acnr_dir = _BACKEND / "app" / "services" / "acnr"
    skip = {_BACKEND / "app" / "services" / "address_registry.py", _BACKEND / "app" / "routers" / "address_registry.py"}
    hits: list[str] = []
    for p in sorted((_BACKEND / "app").rglob("*.py")):
        if acnr_dir in p.parents or p in skip:
            continue
        raw = p.read_bytes()
        if b"address_registry" not in raw:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(raw.decode("utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue  # 只会少算，判据「至少 1 处」随之 fail-closed
        for n in ast.walk(tree):
            if (isinstance(n, ast.ImportFrom) and (n.module == "app.services.address_registry" or (
                    n.module == "app.services" and any(a.name == "address_registry" for a in n.names)))) or (
                    isinstance(n, ast.Import) and any(a.name == "app.services.address_registry" for a in n.names)):
                hits.append(p.relative_to(_REPO).as_posix())
                break
    return hits


def _generator_assigns_utc_timestamp() -> bool:
    fn = _func(_GEN_REL, "generate_catalog")
    for n in ast.walk(fn) if fn is not None else ():
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "strftime"
                and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "%Y%m%d%H%M%S"):
            inner = n.func.value
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr == "now"
                    and any(isinstance(a, ast.Attribute) and a.attr == "utc" for a in inner.args)):
                return True
    return False


def _versions_are_timestamps() -> bool:
    rx = re.compile(cc.REGISTRY_VERSION_PATTERN)
    names = [p.stem for p in (_BACKEND / "data" / "acnr" / "catalog_snapshots").glob("*.json")]
    return bool(names) and all(rx.match(n) for n in names) and bool(rx.match(_facts()["catalog.registry_version"]))


def _stale_impact_route() -> bool:
    tree = _tree(_LINKAGE_REL)
    prefix = any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "APIRouter" and any(
        k.arg == "prefix" and isinstance(k.value, ast.Constant) and k.value.value == "/api/linkage-bus"
        for k in n.keywords) for n in ast.walk(tree))
    fn = _func(_LINKAGE_REL, "stale_impact")
    route = fn is not None and any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "post"
        and d.args and isinstance(d.args[0], ast.Constant) and d.args[0].value == "/impact" for d in fn.decorator_list)
    return prefix and route


def _resolve_instance_binds_wp_code() -> bool:
    fn = _func(_RESOLVER_REL, "resolve_instance")
    return fn is not None and any(isinstance(n, ast.Attribute) and n.attr == "wp_code" and isinstance(n.value, ast.Name)
                                  and n.value.id == "WpIndex" for n in ast.walk(fn))


def _planned_rows_open() -> bool:
    rows = _units_of("planned")
    return bool(rows) and all(_task_ids(u.cols[0]) and all(_task_states().get(t) is False for t in _task_ids(u.cols[0]))
                              for u in rows)


def _component_tests_present() -> bool:
    rows = _units_of("component")
    for u in rows:
        p = _REPO / _strip_code(u.cols[3])
        if not p.is_file() or (u.cols[0] == "后端" and _test_function_count(p) == 0):
            return False
    return bool(rows)


def in_planned(*ids: str) -> Check:
    return (f"{_ids(ids)} 都出现在计划表的任务列",
            lambda: set(ids) <= {t for u in _units_of("planned") for t in _task_ids(u.cols[0])})


PLANNED_ROWS_OPEN = claim("计划表每行都带任务号，且这些任务在 tasks.md 里仍为 [ ]", _planned_rows_open)
RESOLVER_DOC_OK = claim("resolver 模块与函数文档定位为「canonical resolver + legacy 委托」、不称唯一入口（AST）",
                        lambda: not _resolver_doc_problems())
V1_BYPASS = claim("backend/app 里仍有绕过 ACNR 直接导入 V1 的文件（AST）", lambda: bool(_v1_direct_importers()))
NON_WP_TO_V1 = claim("resolver 的非底稿域（tb / report / note / aux）经 _delegate_v1 委托 V1（AST）", _non_wp_delegated_to_v1)
SPEC_TASKS = exists(_TASKS_REL)
