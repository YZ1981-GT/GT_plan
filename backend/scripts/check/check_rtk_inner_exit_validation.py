# -*- coding: utf-8 -*-
"""RTK 包装命令内层退出码校验门禁 —— 防「只看 returncode」的 RTK 吞失败假绿。

Task 8.5 · spec `formula-manager-closure`（需求 20.4、design §5 步骤 8 · 20.4、§7.4③）。

═══ 守的是什么 ═══

RTK（CLI token 压缩代理）外层包装子命令时，审计报告（第八/九节）观察到它在**子命令
失败时仍可能返回 exit 0**。任何门禁子进程若 ``rtk <cmd>`` 包装后**只看 returncode**，
就会被外层的 0 骗过 → 假绿。本门禁拦住这一整类反模式：

  **规则**：凡门禁/CI 脚本里用 ``subprocess`` 跑一条以 ``rtk`` 包装的命令，调用处必须
  对**内层**成败显式校验——要么断言 stdout/stderr 含预期标记（§7.4③），要么经
  ``rtk_exit_validation.run_gate_subprocess`` / ``assert_gate_passed`` 做内层判定——
  **不得仅凭 ``.returncode == 0`` / ``r.status === 0`` 判通过**。

═══ 为什么用 AST 而非文本 in 匹配（memory 铁律㉖）═══

「代码是否真的只看 returncode」是语义判断。注释里写「这里校验 returncode」/ docstring
示例 / 字符串里出现 `rtk` 都会骗过文本匹配（㉖：注释正反两向都会骗扫描器）。故 Python
侧一律走 **AST**：
  * 识别 ``subprocess.run(...)`` / ``subprocess.Popen(...)`` / ``subprocess.check_*`` 调用；
  * 看其第一个 argv 实参的字面量首元素是否为 ``rtk``（或 ``shell=True`` 下命令串以 rtk 开头）；
  * 看调用所在函数体内是否存在对该结果的 stdout/stderr 访问或内层校验调用；
  * docstring 是 ``Expr(Constant)`` 不产生 ``Name`` 引用、``#`` 注释不进 AST ⇒ 天然排除。

TS 侧（门禁 spec 的 ``spawnSync``）无 Python AST 可用，退而求其次：**先剥注释再做结构匹配**
（复用 check_tb_writeback_no_direct_call 的 strip_comments 同款状态机），匹配 ``spawnSync``/
``execSync`` 的 argv 首元素是否 rtk 包装 + 是否仅比对 ``.status``。

═══ 范围（如实）═══

现状：CI（governance-checks.yml / ci.yml）与 pre-push 全部直调 ``python ...`` 不经 rtk；
formula-manager 门禁 spec 的 ``runProbeCheck`` 直调 ``python`` 且已断言 stdout 标记（§7.4③
合规）。故**当前命中数预期为 0**——本门禁是**棘轮式防回归**：日后任何人把门禁命令包成
``rtk ...`` 又只看退出码，立即打红。配可伪证豁免登记（仅压缩输出、不参与成败判定的纯日志
型 rtk 调用可登记，但须附理由字段）。

命中即 exit 1，逐条打印 `文件:行`。产出 JSON 报告。stdlib-only，秒级。
自测：`backend/tests/formula_management/test_rtk_inner_exit_validation.py`。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
FRONTEND_SRC = _REPO / "audit-platform" / "frontend" / "src"

#: 扫描的门禁/CI Python 脚本根目录（check / acnr / fix 等治理脚本）。
_PY_SCAN_DIRS = [
    _BACKEND / "scripts" / "check",
    _BACKEND / "scripts" / "acnr",
    _REPO / "scripts" / "check",
]

#: subprocess 的运行类调用名。
_SUBPROCESS_RUNNERS = {"run", "Popen", "call", "check_call", "check_output"}

#: 识别「内层校验」的方法/函数名——出现在调用处所在函数体即视为已做内层校验。
_INNER_VALIDATION_NAMES = {
    "run_gate_subprocess",
    "assert_gate_passed",
    "inner_passed",
    "markers_hit",
    "failure_markers_hit",
}


# ───────────────────────── Python AST 扫描 ─────────────────────────


def _argv_head_is_rtk(node: ast.Call) -> bool:
    """判断一个 subprocess 调用的 argv 首元素字面量是否为 ``rtk``。

    覆盖两形态：
      * ``subprocess.run(["rtk", ...], ...)`` —— 列表首字面量 == "rtk"。
      * ``subprocess.run("rtk ...", shell=True)`` —— 命令串以 "rtk " 开头。
    只认**字面量**（动态构造的 argv 无法静态判定，交由调用处内层校验兜，不在此误报）。
    """
    if not node.args:
        return False
    first = node.args[0]
    # 列表/元组形态
    if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
        head = first.elts[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return _is_rtk_token(head.value)
    # 命令串形态（shell=True）
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        parts = first.value.strip().split()
        return bool(parts) and _is_rtk_token(parts[0])
    return False


def _is_rtk_token(tok: str) -> bool:
    base = tok.strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
    return base in ("rtk", "rtk.exe")


def _is_subprocess_call(node: ast.Call) -> bool:
    """是否 ``subprocess.<runner>(...)`` 或 ``from subprocess import run`` 后的 ``run(...)``。"""
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return (
            fn.attr in _SUBPROCESS_RUNNERS
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "subprocess"
        )
    if isinstance(fn, ast.Name):
        return fn.id in _SUBPROCESS_RUNNERS
    return False


class _RtkSubprocessVisitor(ast.NodeVisitor):
    """收集「rtk 包装的 subprocess 调用」及其所在函数体是否做了内层校验。"""

    def __init__(self) -> None:
        self.findings: list[dict[str, Any]] = []
        self._func_stack: list[ast.AST] = []

    def _enter(self, node: ast.AST) -> None:
        self._func_stack.append(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._enter(node)
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._enter(node)
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if _is_subprocess_call(node) and _argv_head_is_rtk(node):
            scope = self._func_stack[-1] if self._func_stack else None
            self.findings.append(
                {
                    "lineno": node.lineno,
                    "scope": scope,
                    "has_inner_validation": self._scope_has_inner_validation(scope),
                }
            )
        self.generic_visit(node)

    def _scope_has_inner_validation(self, scope: ast.AST | None) -> bool:
        """所在函数体内是否访问了 stdout/stderr 或调用了内层校验工具。

        判据（任一成立即视为已做内层校验，非仅看 returncode）：
          * 访问 ``.stdout`` / ``.stderr`` 属性；
          * 调用 / 引用 run_gate_subprocess / assert_gate_passed / inner_passed /
            markers_hit / failure_markers_hit；
          * 出现 check_output（check_output 本身就返回 stdout，天然非「只看码」）。
        """
        if scope is None:
            return False
        for sub in ast.walk(scope):
            if isinstance(sub, ast.Attribute) and sub.attr in ("stdout", "stderr"):
                return True
            if isinstance(sub, ast.Name) and sub.id in _INNER_VALIDATION_NAMES:
                return True
            if isinstance(sub, ast.Attribute) and sub.attr in _INNER_VALIDATION_NAMES:
                return True
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "check_output"
            ):
                return True
        return False


def scan_python_file(path: Path) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return []
    v = _RtkSubprocessVisitor()
    v.visit(tree)
    out: list[dict[str, Any]] = []
    for f in v.findings:
        if not f["has_inner_validation"]:
            out.append(
                {
                    "lang": "python",
                    "file": _rel(path),
                    "line": f["lineno"],
                    "detail": "rtk 包装的 subprocess 调用，所在函数体未访问 stdout/stderr "
                    "也未经内层校验工具 ⇒ 仅看 returncode（RTK 吞失败假绿风险）",
                }
            )
    return out


# ───────────────────────── TS 门禁 spec 扫描（剥注释 + 结构匹配）─────────────────────────


def strip_comments_ts(text: str) -> str:
    """剥 JS 行/块注释（保留字符串字面量原样），复用 tb-writeback 门禁同款状态机。"""
    out: list[str] = []
    i, n = 0, len(text)
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append("  ")
                i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


#: spawnSync/execSync 的 argv 列表字面量首元素是 'rtk' / "rtk"（或变量 rtk 显式），
#: 形如 `spawnSync('rtk', [...])` 或 `spawnSync(rtkBin, ['rtk', ...])`。
_TS_SPAWN_RTK_RE = re.compile(
    r"\b(?:spawnSync|execSync|execFileSync|spawn)\s*\(\s*[`'\"]rtk[`'\"]"
)
#: argv 列表里首元素是 rtk：`spawnSync(py, ['rtk', ...])` —— 第二参数数组首元素。
_TS_SPAWN_RTK_INARGS_RE = re.compile(
    r"\b(?:spawnSync|execFileSync)\s*\([^,]+,\s*\[\s*[`'\"]rtk[`'\"]"
)
#: 「只看 .status / .code」的比对（无 stdout/stderr 访问时才构成违规，见 scan_ts_file）。
_TS_STATUS_ONLY_RE = re.compile(r"\.\s*(?:status|code)\b")
_TS_STDOUT_RE = re.compile(r"\.\s*(?:stdout|stderr)\b")


def scan_ts_file(path: Path) -> list[dict[str, Any]]:
    """TS 门禁 spec：rtk 包装的 spawnSync + 未访问 stdout/stderr ⇒ 违规。"""
    raw = path.read_text(encoding="utf-8", errors="replace")
    stripped = strip_comments_ts(raw)
    hits: list[dict[str, Any]] = []
    for rx in (_TS_SPAWN_RTK_RE, _TS_SPAWN_RTK_INARGS_RE):
        for m in rx.finditer(stripped):
            # 取该 spawn 调用点往后 800 字符窗口，判是否访问了 stdout/stderr。
            window = stripped[m.start() : m.start() + 800]
            accesses_stdout = bool(_TS_STDOUT_RE.search(window))
            if not accesses_stdout:
                line = stripped[: m.start()].count("\n") + 1
                hits.append(
                    {
                        "lang": "ts",
                        "file": _rel(path),
                        "line": line,
                        "detail": "rtk 包装的 spawnSync 后未访问 stdout/stderr（仅看 .status "
                        "⇒ RTK 吞失败假绿风险）",
                    }
                )
    return hits


# ───────────────────────── 文件枚举 + 工具 ─────────────────────────


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(_REPO)).replace("\\", "/")
    except ValueError:
        return path.name


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for d in _PY_SCAN_DIRS:
        if d.is_dir():
            files.extend(p for p in d.rglob("*.py") if p.is_file())
    return files


def iter_ts_gate_files() -> list[Path]:
    """门禁 spec（__tests__ 下 *.spec.ts）——它们才会 spawnSync 跑 Python 门禁子进程。"""
    if not FRONTEND_SRC.is_dir():
        return []
    return [
        p
        for p in FRONTEND_SRC.rglob("*.spec.ts")
        if p.is_file()
    ]


def scan_all() -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for path in iter_python_files():
        violations.extend(scan_python_file(path))
    for path in iter_ts_gate_files():
        violations.extend(scan_ts_file(path))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="RTK 包装命令内层退出码校验门禁（防只看 returncode 的 RTK 吞失败假绿）"
    )
    parser.add_argument("--json", dest="json_path", default=None, help="把 JSON 报告写到此路径")
    args = parser.parse_args(argv)

    violations = scan_all()

    report = {
        "gate": "rtk-inner-exit-validation/1",
        "spec": "formula-manager-closure Task 8.5 / 需求 20.4 / design §7.4③",
        "python_files_scanned": len(iter_python_files()),
        "ts_gate_files_scanned": len(iter_ts_gate_files()),
        "violations": violations,
        "verdict": "passed" if not violations else "failed",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_path:
        Path(args.json_path).write_text(text, encoding="utf-8")
    print(text)

    if violations:
        print("\n❌ 检测到 rtk 包装命令仅看 returncode（RTK 吞失败退出码 → 假绿）：")
        for v in violations:
            print(f"  [{v['lang']}] {v['file']}:{v['line']}  {v['detail']}")
        print(
            "\n修复（§7.4③ 口径）：门禁子进程断言 stdout/stderr 含预期标记，或改用 "
            "`app.services.formula_management.rtk_exit_validation.run_gate_subprocess` + "
            "`assert_gate_passed` 做内层退出码/标记校验，不得仅凭外层 returncode 判通过。"
        )
        return 1

    print("\n✅ 无 rtk 包装命令仅看 returncode（全部门禁子进程均做内层 stdout/标记校验）")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
