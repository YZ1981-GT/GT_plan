"""需求 2.7：「委派角色 → 项目角色与级别」映射只有角色映射一份（partner-manager-edit-permission 任务 2.5）。

扫描范围（均不含测试文件）：

- 后端：``backend/app`` 下全部 ``.py``（递归），纯 AST（``ast.parse``）。``backend/tests`` 整个目录不在范围内，
  包括期望表 ``role_map_expected.py``；级别回填迁移的 SQL 不是 Python，由需求 12.7 的对账测试钉住。
- 前端：``audit-platform/frontend/src`` 下的脚本源码（``.ts`` ``.tsx`` ``.mts`` ``.cts`` ``.js`` ``.jsx`` ``.mjs``
  ``.cjs``，以及 ``.vue`` 的 ``<script>`` / ``<script setup>`` 块；模板不在范围内），排除 ``__tests__`` 目录、
  ``*.spec.*`` / ``*.test.*`` 与 vitest 的 setupFiles 目录 ``src/test/``。经 node 子进程用前端依赖里的 ``typescript``
  解析，``.vue`` 先用 ``@vue/compiler-sfc`` 取出脚本块。TS 解析器带错误恢复，有语法诊断的文件照样产出语法树、
  照样被扫描，所以语法诊断只登记不计作空转；读不出、不是 UTF-8、脚本块没取全才算没扫到。

计数口径（需求 2.7）：一个映射字面量计一份，当且仅当其中有 2 个及以上条目的键是四个别名集合里的委派角色、
且该条目的取值给出项目级别。

- 映射字面量：Python 的字典显示 ``{...}`` 与 ``dict(k=v, ...)`` / ``dict([(k, v), ...])``；前端的对象字面量与
  ``new Map([[k, v], ...])`` / ``Object.fromEntries([[k, v], ...])``。
- 键：字符串字面量（前端另含标识符键与 ``['…']`` 计算键；``dict()`` 取关键字参数名），按字符串精确比对四个别名
  集合（取自需求 2.5 的期望表，不读生产代码）。以枚举成员为键（如 ``ProjectUserRole.partner``）的不是委派角色
  字符串，不计；委派角色只作记录里的字段取值（如 ``{"value": "manager", "level": "edit"}`` 的列表）也不是以它为键。
- 取值给出项目级别：取值本身是级别（字符串 ``edit`` / ``review`` / ``readonly``，或 ``PermissionLevel.<级别>``、
  可带 ``.value``，或 ``PermissionLevel("<级别>")`` / ``PermissionLevel["<级别>"]``）；或取值是元组 / 列表 / 集合 /
  字典 / 对象字面量、其直接元素（字典取直接的值）里有级别，即项目角色与级别的组合，如
  ``(ProjectUserRole.partner, PermissionLevel.edit)``、``("partner", "review")``、``{"role": ..., "level": "edit"}``。
- 不计：取值是中文显示名（委派通知、页面显示名）、只给项目角色、数字（资历 / 优先级）、操作权限集合（级别字样
  嵌在更深一层，或包在 ``Set(...)`` / ``frozenset(...)`` 里）。注释、docstring 与字符串里的映射文本不进语法树。
  只数字面量：先把级别赋给变量、再在映射里引用变量的写法不在本扫描口径内（同任务 2.8）。

位置写成「相对路径::类.函数.赋值目标」（后端相对 ``backend/``，前端相对 ``audit-platform/``），不用行号。
任务 19.4 ⑤ 的变异（在角色上下文服务里写回一份等价映射）应红在「映射不唯一」上。
"""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.role_map_expected import EXPECTED_ROLE_MAP

_BACKEND = Path(__file__).resolve().parents[1]
_APP = _BACKEND / "app"
_FRONTEND = _BACKEND.parent / "audit-platform" / "frontend"
_FRONTEND_SRC = _FRONTEND / "src"

# 四个别名集合 = 期望表中取值不是 (readonly, readonly) 的键（需求 2.5 允许另登记的 readonly 键不属于四个集合）。
_ROLE_ALIASES: frozenset[str] = frozenset(
    role for role, value in EXPECTED_ROLE_MAP.items() if value != ("readonly", "readonly"))
_LEVELS = frozenset({"edit", "review", "readonly"})
_ROLE_MAP_LOCATION = "app/services/assignment_service.py::ROLE_MAP"
_NOT_UNIQUE = "映射不唯一"
_FRONTEND_SUFFIXES = frozenset({".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".vue"})

# node 子进程脚本：运行时写到临时目录（仓库外）执行。读 config 列出的文件，输出候选映射（≥2 个别名键）的 JSON；
# 取值规整成与 _py_norm 同形的结构，「是否给出级别」统一由 Python 侧的 _gives_level 判定。非 ASCII 字符转义成
# \uXXXX，输出是纯 ASCII；读取端仍按 UTF-8 解码并断言无替换字符，传输出错不会被静默吞掉。
_EXTRACTOR_JS = r"""'use strict';
const fs = require('fs');
const path = require('path');
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const ts = require(cfg.typescript);
const sfc = require(cfg.compilerSfc);
const ALIASES = new Set(cfg.aliases);
const K = ts.SyntaxKind;
const decoder = new TextDecoder('utf-8', { fatal: true });
const WRAPPERS = new Set([K.ParenthesizedExpression, K.AsExpression, K.SatisfiesExpression,
  K.TypeAssertionExpression, K.NonNullExpression]);
const SCOPES = new Set([K.FunctionDeclaration, K.FunctionExpression, K.ArrowFunction, K.MethodDeclaration,
  K.GetAccessor, K.SetAccessor, K.Constructor, K.ClassDeclaration, K.ClassExpression]);
const TARGETS = new Set([K.VariableDeclaration, K.PropertyDeclaration, K.PropertyAssignment]);
const isStr = (n) => !!n && (n.kind === K.StringLiteral || n.kind === K.NoSubstitutionTemplateLiteral);
const unwrap = (n) => { while (n && WRAPPERS.has(n.kind)) n = n.expression; return n; };
function dotted(n) {
  n = unwrap(n);
  if (!n) return null;
  if (n.kind === K.Identifier) return n.text;
  if (n.kind === K.PropertyAccessExpression) {
    const base = dotted(n.expression);
    return base === null ? null : `${base}.${n.name.text}`;
  }
  if (n.kind === K.ElementAccessExpression && isStr(unwrap(n.argumentExpression))) {
    const base = dotted(n.expression);
    return base === null ? null : `${base}.${unwrap(n.argumentExpression).text}`;
  }
  return null;
}
function norm(n, depth) {
  n = unwrap(n);
  if (!n || depth > 3) return { t: 'other' };
  if (isStr(n)) return { t: 'str', v: n.text };
  const ref = dotted(n);
  if (ref !== null) return { t: 'ref', v: ref };
  if (n.kind === K.CallExpression) {
    return { t: 'call', f: dotted(n.expression) || '', args: n.arguments.map((a) => norm(a, depth + 1)) };
  }
  if (n.kind === K.ArrayLiteralExpression) return { t: 'seq', items: n.elements.map((e) => norm(e, depth + 1)) };
  if (n.kind === K.ObjectLiteralExpression) {
    return { t: 'map', values: n.properties.map((p) => (p.kind === K.PropertyAssignment
      ? norm(p.initializer, depth + 1) : { t: 'other' })) };
  }
  return { t: 'other' };
}
function keyOf(name) {
  if (!name) return null;
  if (name.kind === K.Identifier || isStr(name)) return name.text;
  if (name.kind === K.ComputedPropertyName && isStr(unwrap(name.expression))) return unwrap(name.expression).text;
  return null;
}
function pairEntries(arg) {
  arg = unwrap(arg);
  if (!arg || arg.kind !== K.ArrayLiteralExpression) return null;
  return arg.elements.map(unwrap).filter((p) => p && p.kind === K.ArrayLiteralExpression && p.elements.length === 2)
    .map((p) => [isStr(unwrap(p.elements[0])) ? unwrap(p.elements[0]).text : null, norm(p.elements[1], 1)]);
}
function entriesOf(n) {
  if (n.kind === K.ObjectLiteralExpression) {
    return n.properties.map((p) => [p.kind === K.SpreadAssignment ? null : keyOf(p.name),
      p.kind === K.PropertyAssignment ? norm(p.initializer, 1) : { t: 'other' }]);
  }
  const callee = (n.kind === K.NewExpression || n.kind === K.CallExpression) ? dotted(n.expression) : null;
  const ctor = (n.kind === K.NewExpression && callee === 'Map')
    || (n.kind === K.CallExpression && callee === 'Object.fromEntries');
  return ctor && n.arguments && n.arguments.length ? pairEntries(n.arguments[0]) : null;
}
function scopeName(n) {
  if (n.kind === K.Constructor) return 'constructor';
  if (n.name) return n.name.getText();
  let p = n.parent;
  while (p && (p.kind === K.CallExpression || WRAPPERS.has(p.kind))) p = p.parent;
  return p && TARGETS.has(p.kind) && p.name ? p.name.getText() : '<匿名函数>';
}
function locator(node) {
  const scopes = [];
  let target = null;
  for (let cur = node.parent; cur; cur = cur.parent) {
    if (SCOPES.has(cur.kind)) scopes.push(scopeName(cur));
    else if (!scopes.length && target === null) {
      if (TARGETS.has(cur.kind) && cur.name) target = cur.name.getText();
      else if (cur.kind === K.BinaryExpression && cur.operatorToken.kind === K.EqualsToken) target = cur.left.getText();
      else if (cur.kind === K.ExportAssignment) target = 'export default';
    }
  }
  return [...scopes.reverse(), ...(target === null ? [] : [target])].join('.') || '<module>';
}
const out = { files: 0, blocks: 0, problems: [], diagnostics: [], candidates: [] };
function scanSource(rel, text, kind) {
  out.blocks += 1;
  const sf = ts.createSourceFile(rel, text, ts.ScriptTarget.Latest, true, kind);
  for (const d of sf.parseDiagnostics || []) {
    out.diagnostics.push(`${rel}：${ts.flattenDiagnosticMessageText(d.messageText, ' ')}`);
  }
  const visit = (n) => {
    const entries = entriesOf(n);
    if (entries) {
      const own = entries.filter(([k]) => k !== null && ALIASES.has(k));
      if (new Set(own.map(([k]) => k)).size >= 2) out.candidates.push({ file: rel, locator: locator(n), entries: own });
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
}
const LANG = { ts: ts.ScriptKind.TS, tsx: ts.ScriptKind.TSX, js: ts.ScriptKind.JS, jsx: ts.ScriptKind.JSX };
const EXT = { ts: 'ts', mts: 'ts', cts: 'ts', tsx: 'tsx', js: 'js', mjs: 'js', cjs: 'js', jsx: 'jsx' };
for (const rel of cfg.files) {
  let text;
  try {
    text = decoder.decode(fs.readFileSync(path.join(cfg.root, rel)));
  } catch (e) {
    out.problems.push(`${rel}：读取或 UTF-8 解码失败（${e.message}）`);
    continue;
  }
  out.files += 1;
  if (!rel.endsWith('.vue')) {
    scanSource(rel, text, LANG[EXT[rel.split('.').pop()]]);
    continue;
  }
  // ignoreEmpty: false —— 默认会丢掉只有空白的脚本块，下面按 <script> 标签数核对时会被误判成没取全
  const { descriptor, errors } = sfc.parse(text, { filename: rel, ignoreEmpty: false });
  for (const e of errors) out.diagnostics.push(`${rel}：${e.message || e}`);
  const blocks = [descriptor.script, descriptor.scriptSetup].filter(Boolean);
  const tags = (text.match(/^<script\b/gm) || []).length;
  if (blocks.length < tags) out.problems.push(`${rel}：有 ${tags} 个 <script> 块，只取出 ${blocks.length} 个`);
  for (const b of blocks) if (!b.src) scanSource(rel, b.content, LANG[b.lang || 'js'] ?? ts.ScriptKind.TS);
}
process.stdout.write(JSON.stringify(out).replace(/[\u007f-\uffff]/g,
  (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`));
"""


@dataclass(frozen=True)
class Hit:
    location: str  # 「相对路径::类.函数.赋值目标」
    keys: tuple[str, ...]  # 取值给出项目级别的委派别名键（排序）

    def __str__(self) -> str:
        return f"{self.location}（键 {'、'.join(self.keys)}）"


@dataclass
class BackendScan:
    root: Path
    files: int = 0
    parse_errors: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)


@dataclass
class FrontendScan:
    src: Path
    listed: int = 0  # 按范围列出的文件数
    files: int = 0  # 子进程实际读到的文件数
    blocks: int = 0  # 解析的脚本块数（.vue 每个 <script> 块计一个）
    problems: list[str] = field(default_factory=list)  # 读不出 / 非 UTF-8 / 脚本块没取全
    diagnostics: list[str] = field(default_factory=list)  # 语法诊断与 SFC 解析告警：只登记
    candidates: int = 0  # 以 ≥2 个委派别名为键的映射字面量数（不论取值）
    hits: list[Hit] = field(default_factory=list)


def _is_level(value: dict) -> bool:
    """取值本身是级别：字符串、PermissionLevel 成员（可带 .value）、PermissionLevel("…") / PermissionLevel["…"]。"""
    kind = value["t"]
    if kind == "str":
        return value["v"] in _LEVELS
    if kind == "ref":
        parts = value["v"].split(".")
        if parts[-1] == "value":
            parts = parts[:-1]
        return len(parts) >= 2 and parts[-2] == "PermissionLevel" and parts[-1] in _LEVELS
    if kind == "call":
        args = value["args"]
        return value["f"].split(".")[-1] == "PermissionLevel" and len(args) == 1 and _is_level(args[0])
    return False


def _gives_level(value: dict) -> bool:
    """取值给出项目级别：本身是级别，或容器的直接元素 / 直接的值里有级别（项目角色与级别的组合）。"""
    if _is_level(value):
        return True
    if value["t"] == "seq":
        return any(_is_level(item) for item in value["items"])
    if value["t"] == "map":
        return any(_is_level(item) for item in value["values"])
    return False


def _level_keys(entries: list) -> tuple[str, ...]:
    return tuple(sorted({key for key, value in entries if key in _ROLE_ALIASES and _gives_level(value)}))


def _py_str(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _py_dotted(node: ast.expr) -> str | None:
    """a / a.b / a["b"] → "a.b"；其余 None。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _py_dotted(node.value)
        return None if base is None else f"{base}.{node.attr}"
    if isinstance(node, ast.Subscript) and _py_str(node.slice) is not None:
        base = _py_dotted(node.value)
        return None if base is None else f"{base}.{_py_str(node.slice)}"
    return None


def _py_norm(node: ast.expr | None, depth: int = 1) -> dict:
    """把取值规整成与前端脚本同形的结构（只需看到第 3 层：容器 → 元素 → PermissionLevel("…") 的实参）。"""
    if node is None or depth > 3:
        return {"t": "other"}
    if _py_str(node) is not None:
        return {"t": "str", "v": _py_str(node)}
    ref = _py_dotted(node)
    if ref is not None:
        return {"t": "ref", "v": ref}
    if isinstance(node, ast.Call):
        return {"t": "call", "f": _py_dotted(node.func) or "", "args": [_py_norm(a, depth + 1) for a in node.args]}
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return {"t": "seq", "items": [_py_norm(e, depth + 1) for e in node.elts]}
    if isinstance(node, ast.Dict):
        return {"t": "map", "values": [_py_norm(v, depth + 1) for v in node.values]}
    return {"t": "other"}


def _py_entries(node: ast.AST) -> list[tuple[str | None, ast.expr]] | None:
    """映射字面量的（键，取值）；不是映射字面量返回 None。"""
    if isinstance(node, ast.Dict):
        return [(_py_str(key), value) for key, value in zip(node.keys, node.values)]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
        entries: list[tuple[str | None, ast.expr]] = [(kw.arg, kw.value) for kw in node.keywords]
        if node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
            entries += [(_py_str(pair.elts[0]), pair.elts[1]) for pair in node.args[0].elts
                        if isinstance(pair, (ast.Tuple, ast.List)) and len(pair.elts) == 2]
        return entries
    return None


def _locator(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    """所在的类 / 函数（由外到内）加同一作用域内最近的赋值目标；两者都没有时为 <module>（同任务 2.8）。"""
    scopes: list[str] = []
    target: str | None = None
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scopes.append(cur.name)
        elif not scopes and target is None and isinstance(cur, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = cur.targets if isinstance(cur, ast.Assign) else [cur.target]
            target = " = ".join(ast.unparse(t) for t in targets)
        cur = parents.get(cur)
    return ".".join([*reversed(scopes), *([target] if target else [])]) or "<module>"


def scan_backend(root: Path) -> BackendScan:
    """扫描 root 下全部 .py（递归）；位置相对 root 的上一级给出（root 为 backend/app 时形如 app/...）。"""
    scan = BackendScan(root)
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root.parent).as_posix()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)  # 无效转义等告警与本扫描无关
                tree = ast.parse(path.read_bytes(), filename=str(path))
        except (SyntaxError, ValueError) as exc:  # 如实登记，由「扫描器不空转」打红，不静默跳过
            scan.parse_errors.append(f"{rel}：{exc}")
            continue
        scan.files += 1
        found: list[tuple[ast.AST, tuple[str, ...]]] = []
        for node in ast.walk(tree):
            entries = _py_entries(node)
            if entries:
                keys = _level_keys([(key, _py_norm(value)) for key, value in entries if key in _ROLE_ALIASES])
                if len(keys) >= 2:
                    found.append((node, keys))
        if not found:
            continue  # 本文件没有命中，不必建父节点表
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node, keys in sorted(found, key=lambda item: (item[0].lineno, item[0].col_offset)):
            scan.hits.append(Hit(f"{rel}::{_locator(node, parents)}", keys))
    return scan


def _frontend_files(src: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path.suffix not in _FRONTEND_SUFFIXES:
            continue
        rel = path.relative_to(src)
        if "__tests__" in rel.parts or rel.parts[0] == "test" or ".spec." in path.name or ".test." in path.name:
            continue
        files.append(rel.as_posix())
    return files


def scan_frontend(src: Path, node_modules: Path = _FRONTEND / "node_modules") -> FrontendScan:
    """扫描 src 下的前端脚本源码；解析器取自 node_modules（可指向另一棵树的依赖，用于在只读基线树上对照）。

    位置相对 src 的上两级给出（src 为 audit-platform/frontend/src 时形如 frontend/src/...）。
    """
    files = _frontend_files(src)
    node = shutil.which("node")
    tools = {"typescript": node_modules / "typescript", "compilerSfc": node_modules / "@vue" / "compiler-sfc"}
    missing = sorted(str(p) for p in tools.values() if not (p / "package.json").is_file())
    assert node is not None and not missing, (
        f"前端扫描跑不起来：node 可执行文件 {node!r}，缺解析依赖 {missing}（先在 audit-platform/frontend 跑 npm ci）")
    with tempfile.TemporaryDirectory(prefix="role_map_scan_") as tmp:
        script, config = Path(tmp) / "extract.cjs", Path(tmp) / "config.json"
        script.write_text(_EXTRACTOR_JS, encoding="utf-8")
        config.write_text(json.dumps({"root": str(src), "files": files, "aliases": sorted(_ROLE_ALIASES),
                                      **{name: str(p) for name, p in tools.items()}}, ensure_ascii=False),
                          encoding="utf-8")
        proc = subprocess.run([node, str(script), str(config)], capture_output=True, timeout=600, check=False)
    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 0, f"前端解析子进程失败（退出码 {proc.returncode}）：{stderr[-2000:]}"
    assert stdout.strip(), f"前端解析子进程没有输出：{stderr[-2000:]}"
    assert "\ufffd" not in stdout, f"前端解析子进程的输出含解码替换字符：{stdout[:200]}"
    data = json.loads(stdout)
    scan = FrontendScan(src, listed=len(files), files=data["files"], blocks=data["blocks"],
                        problems=data["problems"], diagnostics=data["diagnostics"], candidates=len(data["candidates"]))
    prefix = src.relative_to(src.parent.parent).as_posix()
    for candidate in data["candidates"]:
        keys = _level_keys(candidate["entries"])
        if len(keys) >= 2:
            scan.hits.append(Hit(f"{prefix}/{candidate['file']}::{candidate['locator']}", keys))
    return scan


@pytest.fixture(scope="module")
def backend_scan() -> BackendScan:
    return scan_backend(_APP)


@pytest.fixture(scope="module")
def frontend_scan() -> FrontendScan:
    return scan_frontend(_FRONTEND_SRC)


def _not_unique(hits: list[Hit]) -> str:
    others = [h for h in hits if h.location != _ROLE_MAP_LOCATION]
    listing = "\n".join(f"  - {h}" for h in others) or "  （无）"
    return (
        f"{_NOT_UNIQUE}：以 2 个及以上委派别名为键、取值给出项目级别的映射应只有 {_ROLE_MAP_LOCATION} 一份；"
        f"现算 {len(hits)} 份（ROLE_MAP 处 {len(hits) - len(others)} 份），其他位置 {len(others)} 处：\n{listing}\n"
        "委派角色的项目角色与级别请经 assignment_service.map_assignment_role / resolve_member_mapping（读 ROLE_MAP）"
        "取用，不另存映射副本；委派通知与页面显示名映射不计。"
    )


def test_scanner_is_not_idle(backend_scan: BackendScan, frontend_scan: FrontendScan) -> None:
    """扫描器不空转：两端都读到了文件且没有漏读，后端在 ROLE_MAP 处恰命中 1 次，前端认出了以别名为键的映射。"""
    assert len(_ROLE_ALIASES) >= 2, f"期望表里的委派别名不足 2 个，计数口径无从命中：{sorted(_ROLE_ALIASES)}"
    assert backend_scan.files > 0, f"扫描器空转：{backend_scan.root} 下没有扫到 .py 文件"
    assert backend_scan.parse_errors == [], "扫描器空转：以下文件读不出 AST：\n" + "\n".join(backend_scan.parse_errors)
    at_role_map = [h for h in backend_scan.hits if h.location == _ROLE_MAP_LOCATION]
    assert len(at_role_map) == 1, (
        f"扫描器空转：应在 ROLE_MAP 处恰命中 1 次，现算 {[str(h) for h in at_role_map]}")
    assert frontend_scan.files > 0, f"扫描器空转：{frontend_scan.src} 下没有扫到前端源码"
    assert frontend_scan.problems == [], "扫描器空转：以下前端文件没有扫全：\n" + "\n".join(frontend_scan.problems)
    assert frontend_scan.files == frontend_scan.listed, (
        f"扫描器空转：列出 {frontend_scan.listed} 个前端文件，子进程只读到 {frontend_scan.files} 个")
    assert frontend_scan.candidates > 0, "扫描器空转：前端源码里没认出任何以 2 个及以上委派别名为键的映射（解析器没在工作）"


def test_role_map_is_the_only_role_level_mapping(backend_scan: BackendScan, frontend_scan: FrontendScan) -> None:
    """需求 2.7：以 2 个及以上委派别名为键、取值给出项目级别的映射，后端与前端合计只有 ROLE_MAP 一份。"""
    assert frontend_scan.problems == [], "前端源码没有扫全，不能判定映射唯一：\n" + "\n".join(frontend_scan.problems)
    hits = [*backend_scan.hits, *frontend_scan.hits]
    assert [h.location for h in hits] == [_ROLE_MAP_LOCATION], _not_unique(hits)
