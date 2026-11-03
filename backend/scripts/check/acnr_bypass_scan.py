#!/usr/bin/env python3
"""acnr_bypass_scan.py — ACNR 消费方绕过点扫描与台账核对（acnr-foundation-defect-closure T24 / 需求 13 / design §14）

只依赖标准库（CI 作业不装依赖）。识别一律用 Python ``ast``：注释不进语法树，文档字符串单独剔除。

绕过点定义（design §14.1，后端两类；前端 BP-3 / BP-4 由
``audit-platform/frontend/src/acnrBypassRatchet.spec.ts`` 用 TS 编译器 API 扫描，读同一份基线）：

- BP-1：``backend/app`` 里从 V1 地址服务 / 路由（``app.services.address_registry``、
  ``app.routers.address_registry``）导入寻址符号。排除 V1 自身、``services/acnr/``（非底稿域委托层）、
  ``router_registry/system.py``（路由注册）与纯取值工具 ``extract_custom_cells`` / ``CellRecord``。
- BP-2（R2-F12 窄定义）：``backend/app``、``backend/scripts`` 里以字符串常量（含路径拼接的文件名常量）
  加载三个 V2 身份 JSON 的模块；以及读取 CCR（``cross_wp_references.json``）后自行推导 sheet 身份的模块。
  CCR 读取方由扫描器自动找出，但「是否推导 sheet 身份」须逐个裁决：推导身份的进基线（kind=ccr_identity），
  只做跨底稿业务规则的进台账（任一条目的 files），两边都没有即报「未裁决的 CCR 读取方」。
  排除 V2 路由与两个经 ``v2_canonical`` 取身份的对账 / 夹具脚本（排除项须仍命中且导入 v2_canonical）。

基线 ``backend/data/acnr/bypass_baseline.json`` 存「文件 + 作用域 + 符号 + 次数」，不含行号：
现算超出基线（新增绕过）或基线条目现算找不到（失效条目）都是违规。
台账 ``backend/data/acnr/consumer_ledger.json``：文件须存在、Python 符号须由 AST 定义、
migrated 条目的文件不得在基线里、基线里的每个文件都须被某个非 migrated 条目登记。

用法：
    python backend/scripts/check/acnr_bypass_scan.py             # 报告模式，退出 0
    python backend/scripts/check/acnr_bypass_scan.py --strict    # 有违规退出 1
    python backend/scripts/check/acnr_bypass_scan.py --json      # 输出结构化结果
基线 / 台账缺失或无法解析、被扫描文件无法解析，一律退出 2（不放行）。
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import warnings
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

REPO_ROOT = Path(__file__).resolve().parents[3]
SELF_REL = "backend/scripts/check/acnr_bypass_scan.py"  # 本扫描器自身的文件名常量不算加载
BASELINE_REL = "backend/data/acnr/bypass_baseline.json"
LEDGER_REL = "backend/data/acnr/consumer_ledger.json"

V1_MODULES = ("app.services.address_registry", "app.routers.address_registry")
BP1_SCAN_DIRS = ("backend/app",)
BP1_EXCLUDED_FILES = {
    "backend/app/services/address_registry.py": "V1 地址服务自身",
    "backend/app/routers/address_registry.py": "V1 地址路由自身",
    "backend/app/router_registry/system.py": "路由注册（基础设施，V1 路由退役前无法迁移）",
}
BP1_EXCLUDED_DIRS = {"backend/app/services/acnr/": "ACNR 包：非底稿域委托 V1 的唯一合法位置"}
BP1_VALUE_TOOLS = frozenset({"extract_custom_cells", "CellRecord"})

BP2_SCAN_DIRS = ("backend/app", "backend/scripts")
IDENTITY_JSONS = (
    "address_registry_l2_semantic.json",
    "address_registry_resolved_refs.json",
    "address_registry_l3_dependencies.json",
)
CCR_JSON = "cross_wp_references.json"
BP2_EXCLUDED_FILES = {
    "backend/app/routers/address_registry_v2.py": "V2 路由自身：读端点的节点经 v2_canonical 取规范身份（T21）",
    "backend/scripts/acnr/reconcile_v2_canonical.py": "V2 静态数据双读对账脚本：身份经 v2_canonical（T22）",
    "backend/scripts/acnr/gen_editor_save_inputs.py": "编辑器保存输入夹具生成器：身份经 v2_canonical（T21）",
}
LEDGER_STATUSES = ("migrated", "legacy_fallback", "not_wired")
BP_KEYS = ("bp1", "bp2", "bp3", "bp4")


class ScanError(Exception):
    """基线 / 台账 / 被扫描文件无法读取或解析：不放行（退出 2）。"""


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _parse(path: Path, root: Path) -> ast.Module:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            return ast.parse(path.read_bytes().decode("utf-8-sig"), filename=_rel(path, root))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
        raise ScanError(f"无法解析 {_rel(path, root)}：{exc}") from exc


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _module_package(rel: str) -> list[str]:
    """``backend/app/services/x.py`` → ``['app', 'services']``（相对导入的基准包）。"""
    parts = rel.split("/")[1:-1]
    return parts


def _absolute_module(node: ast.ImportFrom, rel: str) -> str:
    if not node.level:
        return node.module or ""
    base = _module_package(rel)
    if node.level > 1:
        base = base[: len(base) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


class _ScopedVisitor(ast.NodeVisitor):
    """记录当前作用域限定名（类 / 函数嵌套用点连接，模块级为 ``<module>``）。"""

    def __init__(self) -> None:
        self.stack: list[str] = []

    @property
    def scope(self) -> str:
        return ".".join(self.stack) or "<module>"

    def _enter(self, node: ast.AST) -> None:
        self.stack.append(node.name)  # type: ignore[attr-defined]
        self.generic_visit(node)
        self.stack.pop()

    visit_ClassDef = _enter
    visit_FunctionDef = _enter
    visit_AsyncFunctionDef = _enter


class _Bp1Visitor(_ScopedVisitor):
    def __init__(self, rel: str) -> None:
        super().__init__()
        self.rel = rel
        self.hits: Counter = Counter()
        self.statements = 0

    def _record(self, names: list[str]) -> None:
        if names:
            self.statements += 1
            for name in names:
                self.hits[(self.rel, self.scope, name)] += 1

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = _absolute_module(node, self.rel)
        if module in V1_MODULES:
            self._record([a.name for a in node.names if a.name not in BP1_VALUE_TOOLS])
        elif module in ("app.services", "app.routers"):
            self._record([a.name for a in node.names if a.name == "address_registry"])

    def visit_Import(self, node: ast.Import) -> None:
        self._record([a.name for a in node.names if a.name in V1_MODULES])

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in ("import_module", "__import__") and node.args \
                and isinstance(node.args[0], ast.Constant) and node.args[0].value in V1_MODULES:
            self._record([str(node.args[0].value)])
        self.generic_visit(node)


def _names_file(value: str, filename: str) -> bool:
    """字符串常量是否指向该文件：以文件名结尾，且前面是开头或路径分隔符（正文里提到文件名不算）。"""
    text = value.strip()
    if not text.endswith(filename):
        return False
    head = text[: len(text) - len(filename)]
    return head == "" or head[-1] in "/\\"


class _Bp2Visitor(_ScopedVisitor):
    def __init__(self, rel: str, docstrings: set[int]) -> None:
        super().__init__()
        self.rel = rel
        self.docstrings = docstrings
        self.identity: Counter = Counter()
        self.ccr: Counter = Counter()

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and id(node) not in self.docstrings:
            for name in IDENTITY_JSONS:
                if _names_file(node.value, name):
                    self.identity[(self.rel, self.scope, "identity_json", name)] += 1
            if _names_file(node.value, CCR_JSON):
                self.ccr[(self.rel, self.scope, "ccr_identity", CCR_JSON)] += 1


def _iter_py(root: Path, dirs: tuple[str, ...]):
    for d in dirs:
        base = root / d
        if base.is_dir():
            yield from sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _imports_v2_canonical(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and not node.level:
            if node.module == "app.services.acnr.v2_canonical":
                return True
            if node.module == "app.services.acnr" and any(a.name == "v2_canonical" for a in node.names):
                return True
    return False


def scan_backend(root: Path = REPO_ROOT) -> dict:
    """现算后端 BP-1 / BP-2 与 CCR 读取方。"""
    bp1: Counter = Counter()
    bp1_statements = 0
    for path in _iter_py(root, BP1_SCAN_DIRS):
        rel = _rel(path, root)
        if rel in BP1_EXCLUDED_FILES or any(rel.startswith(d) for d in BP1_EXCLUDED_DIRS):
            continue
        visitor = _Bp1Visitor(rel)
        visitor.visit(_parse(path, root))
        bp1 += visitor.hits
        bp1_statements += visitor.statements
    identity: Counter = Counter()
    ccr: Counter = Counter()
    excluded_hits: dict[str, bool] = {}
    excluded_problems: list[str] = []
    for path in _iter_py(root, BP2_SCAN_DIRS):
        rel = _rel(path, root)
        if rel == SELF_REL:
            continue
        tree = _parse(path, root)
        visitor = _Bp2Visitor(rel, _docstring_nodes(tree))
        visitor.visit(tree)
        if rel in BP2_EXCLUDED_FILES:
            excluded_hits[rel] = bool(visitor.identity or visitor.ccr)
            if not _imports_v2_canonical(tree):
                excluded_problems.append(f"{rel}：排除理由是身份经 v2_canonical，但该文件不导入 v2_canonical")
            continue
        identity += visitor.identity
        ccr += visitor.ccr
    for rel in BP2_EXCLUDED_FILES:
        if not excluded_hits.get(rel):
            excluded_problems.append(f"{rel}：排除项已不加载 V2 身份 JSON / CCR（失效排除，应删去）")
    return {
        "bp1": bp1,
        "bp1_statements": bp1_statements,
        "bp2_identity": identity,
        "ccr_readers": ccr,
        "exclusion_problems": excluded_problems,
    }


def _baseline_counter(entries: list[dict], fields: tuple[str, ...]) -> Counter:
    counter: Counter = Counter()
    for entry in entries:
        counter[tuple(entry[f] for f in fields)] += int(entry["count"])
    return counter


def _diff(current: Counter, baseline: Counter) -> tuple[list[tuple], list[tuple]]:
    extra = sorted((k, current[k] - baseline.get(k, 0)) for k in current if current[k] > baseline.get(k, 0))
    stale = sorted((k, baseline[k] - current.get(k, 0)) for k in baseline if baseline[k] > current.get(k, 0))
    return extra, stale


def load_json(path: Path, label: str) -> dict:
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ScanError(f"{label}缺失或无法解析（{path}）：{exc}") from exc
    if not isinstance(data, dict):
        raise ScanError(f"{label}顶层须为对象（{path}）")
    return data


def baseline_files(baseline: dict) -> set[str]:
    return {e["file"] for key in BP_KEYS for e in baseline.get(key, [])}


def python_defined_names(tree: ast.Module) -> set[str]:
    """模块里定义的名字：函数 / 类按限定名（``A.b``），模块级赋值目标按名字。"""
    names: set[str] = set()

    def walk(body: list, prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f"{prefix}{node.name}"
                names.add(qual)
                walk(node.body, qual + ".")
            elif not prefix and isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
            elif isinstance(node, (ast.If, ast.Try)):
                walk(node.body, prefix)

    walk(tree.body, "")
    return names


def ledger_problems(ledger: dict, baseline: dict, ccr_readers: Counter, root: Path) -> list[str]:
    problems: list[str] = []
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        return ["台账 entries 须为非空列表"]
    seen: set[str] = set()
    covered_non_migrated: set[str] = set()
    all_files: set[str] = set()
    bfiles = baseline_files(baseline)
    for entry in entries:
        eid = entry.get("id")
        if not isinstance(eid, str) or not eid or eid in seen:
            problems.append(f"台账条目 id 缺失或重复：{eid!r}")
            continue
        seen.add(eid)
        for field in ("consumer", "target", "notes"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                problems.append(f"{eid}：字段 {field} 须为非空文字")
        status = entry.get("status")
        if status not in LEDGER_STATUSES:
            problems.append(f"{eid}：status {status!r} 不在 {LEDGER_STATUSES}")
        files = entry.get("files")
        if not isinstance(files, list) or not files:
            problems.append(f"{eid}：files 须为非空列表")
            continue
        for f in files:
            all_files.add(f)
            if not (root / f).is_file():
                problems.append(f"{eid}：文件不存在 {f}")
        if status == "migrated":
            for f in sorted(set(files) & bfiles):
                problems.append(f"{eid}：标为 migrated，但 {f} 仍在绕过基线里")
        else:
            covered_non_migrated.update(files)
        for sym in entry.get("symbols") or []:
            sf, name = sym.get("file"), sym.get("name")
            if sf not in files or not isinstance(name, str) or not name:
                problems.append(f"{eid}：符号 {sym!r} 须指明本条目 files 里的文件与名字")
                continue
            if sf.endswith(".py") and (root / sf).is_file():
                if name not in python_defined_names(_parse(root / sf, root)):
                    problems.append(f"{eid}：{sf} 里没有定义 {name}")
    for f in sorted(bfiles - covered_non_migrated):
        problems.append(f"基线文件未被任何非 migrated 台账条目登记：{f}")
    ccr_identity_files = {e["file"] for e in baseline.get("bp2", []) if e.get("kind") == "ccr_identity"}
    for f in sorted({k[0] for k in ccr_readers} - ccr_identity_files - all_files):
        problems.append(f"未裁决的 CCR 读取方（须进基线 ccr_identity 或台账）：{f}")
    return problems


def run(root: Path = REPO_ROOT) -> dict:
    baseline = load_json(root / BASELINE_REL, "绕过基线")
    ledger = load_json(root / LEDGER_REL, "消费方台账")
    current = scan_backend(root)
    bp1_extra, bp1_stale = _diff(current["bp1"], _baseline_counter(baseline.get("bp1", []), ("file", "scope", "name")))
    ccr_baseline_files = {e["file"] for e in baseline.get("bp2", []) if e.get("kind") == "ccr_identity"}
    bp2_current = current["bp2_identity"] + Counter(
        {k: v for k, v in current["ccr_readers"].items() if k[0] in ccr_baseline_files})
    bp2_extra, bp2_stale = _diff(bp2_current, _baseline_counter(baseline.get("bp2", []), ("file", "scope", "kind", "name")))
    return {
        "bp1_statements": current["bp1_statements"],
        "bp1_files": sorted({k[0] for k in current["bp1"]}),
        "bp2_files": sorted({k[0] for k in bp2_current}),
        "ccr_readers": sorted({k[0] for k in current["ccr_readers"]}),
        "extra": [("BP-1", k, n) for k, n in bp1_extra] + [("BP-2", k, n) for k, n in bp2_extra],
        "stale": [("BP-1", k, n) for k, n in bp1_stale] + [("BP-2", k, n) for k, n in bp2_stale],
        "exclusion_problems": current["exclusion_problems"],
        "ledger_problems": ledger_problems(ledger, baseline, current["ccr_readers"], root),
    }


def violations(result: dict) -> int:
    return len(result["extra"]) + len(result["stale"]) + len(result["exclusion_problems"]) \
        + len(result["ledger_problems"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ACNR 消费方绕过点扫描与台账核对（T24）")
    parser.add_argument("--strict", action="store_true", help="有违规退出 1（CI 用）")
    parser.add_argument("--json", action="store_true", help="输出结构化结果")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="仓库根（测试用临时副本）")
    args = parser.parse_args(argv)
    try:
        result = run(args.repo_root.resolve())
    except ScanError as exc:
        print(f"[错误] {exc}；不放行")
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1, default=list))
    for bp, key, n in result["extra"]:
        print(f"[新增绕过] {bp} {key[0]}（{key[1]}）：{key[-1]} 超出基线 {n} 处")
    for bp, key, n in result["stale"]:
        print(f"[失效条目] {bp} {key[0]}（{key[1]}）：{key[-1]} 基线所指的 {n} 处现已不存在，须从基线删去")
    for text in result["exclusion_problems"]:
        print(f"[排除项] {text}")
    for text in result["ledger_problems"]:
        print(f"[台账] {text}")
    total = violations(result)
    print(f"BP-1 {result['bp1_statements']} 处 / {len(result['bp1_files'])} 个文件；"
          f"BP-2 {len(result['bp2_files'])} 个文件；CCR 读取方 {len(result['ccr_readers'])} 个；"
          f"新增 {len(result['extra'])} 条、失效 {len(result['stale'])} 条、排除项问题 "
          f"{len(result['exclusion_problems'])} 条、台账问题 {len(result['ledger_problems'])} 条"
          f"（前端 BP-3 / BP-4 由 src/acnrBypassRatchet.spec.ts 核对）")
    if total and args.strict:
        print(f"共 {total} 条违规，strict 模式退出 1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
