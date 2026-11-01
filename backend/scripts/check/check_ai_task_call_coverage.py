"""AI 任务统一入口与专业边界债务棘轮。

默认与 ``backend/data/ai_task_legacy_debt_baseline.json`` 对比：既有债务可逐步删除，
不允许新增。``--emit`` 输出当前清册供评审，不修改文件。
"""

from __future__ import annotations

import argparse
import ast
import base64
import json
import re
import zlib
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
BASELINE = BACKEND / "data" / "ai_task_legacy_debt_baseline.json"
_EXCLUDED_DIRECT = {
    "app/services/ai_task_executor.py",
    "app/services/llm_client.py",
    "app/services/ai_chat/native_model_client.py",
}
_DIRECT_NAMES = {"chat_completion", "chat_completion_result"}
_PROHIBITED = {
    "formal_audit_conclusion": re.compile(r"正式审计结论"),
    "overall_audit_conclusion": re.compile(r"总体审计结论"),
    "generate_overall_opinion": re.compile(r"请生成[^\n]{0,80}(?:整体|总体)[^\n]{0,20}审计意见"),
    "audit_opinion_impact": re.compile(r"对审计意见的影响"),
}


def _relative(path: Path) -> str:
    return path.relative_to(BACKEND).as_posix()


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


class _Calls(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[str] = []
        self.rows: list[tuple[str, str, int]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name in _DIRECT_NAMES:
            self.rows.append((".".join(self.scope) or "<module>", name, node.lineno))
        self.generic_visit(node)


def scan_direct_calls() -> list[str]:
    raw: list[tuple[str, str, str, int]] = []
    for path in sorted(APP.rglob("*.py")):
        rel = _relative(path)
        if rel in _EXCLUDED_DIRECT or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        visitor = _Calls()
        visitor.visit(tree)
        raw.extend((rel, scope, name, line) for scope, name, line in visitor.rows)
    grouped: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for rel, scope, name, line in raw:
        grouped[(rel, scope, name)].append(line)
    result: list[str] = []
    for (rel, scope, name), lines in sorted(grouped.items()):
        for ordinal, _line in enumerate(sorted(lines), 1):
            result.append(f"{rel}::{scope}::{name}#{ordinal}")
    return result


def _dict_key_for_constant(tree: ast.AST, target: ast.Constant) -> str | None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if value is target and isinstance(key, ast.Constant) and isinstance(key.value, str):
                return key.value
    return None


def scan_prompt_debts() -> list[str]:
    result: set[str] = set()
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            matched = [name for name, pattern in _PROHIBITED.items() if pattern.search(node.value)]
            if not matched:
                continue
            owner = _dict_key_for_constant(tree, node)
            if owner is None:
                current = parents.get(node)
                while current is not None and not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    current = parents.get(current)
                owner = current.name if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)) else f"line-{node.lineno}"
            rel = _relative(path)
            result.update(f"{rel}::{owner}::{name}" for name in matched)
    return sorted(result)


def snapshot() -> dict[str, object]:
    direct = scan_direct_calls()
    prompts = scan_prompt_debts()
    return {
        "schema_version": 1,
        "direct_calls": direct,
        "prompt_debts": prompts,
        "summary": {
            "direct_calls": len(direct),
            "prompt_debts": len(prompts),
            "direct_by_callee": dict(sorted(Counter(row.split("::")[-1].split("#")[0] for row in direct).items())),
        },
    }


def _baseline_rows(baseline: dict[str, object], field: str) -> list[str]:
    plain = baseline.get(field)
    if isinstance(plain, list):
        return [str(value) for value in plain]
    encoded = baseline.get(f"{field}_zlib_b64")
    if not isinstance(encoded, str) or not encoded:
        return []
    raw = zlib.decompress(base64.b64decode(encoded)).decode("utf-8")
    return [row for row in raw.split("\n") if row]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()
    current = snapshot()
    if args.emit:
        print(json.dumps(current, ensure_ascii=False, indent=2))
        return 0
    if not BASELINE.exists():
        print(f"[FAIL] 基线不存在：{BASELINE}")
        return 2
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    failures: list[str] = []
    for field in ("direct_calls", "prompt_debts"):
        prior = _baseline_rows(baseline, field)
        added = sorted(set(current[field]) - set(prior))
        if added:
            failures.append(f"{field} 新增 {len(added)} 项：\n  " + "\n  ".join(added))
    if failures:
        print("[FAIL] AI 任务统一入口棘轮回退\n" + "\n".join(failures))
        return 1
    prior_direct = _baseline_rows(baseline, "direct_calls")
    prior_prompts = _baseline_rows(baseline, "prompt_debts")
    print(
        "[PASS] AI 任务债务未增加："
        f"direct={len(current['direct_calls'])}/{len(prior_direct)}, "
        f"prompt={len(current['prompt_debts'])}/{len(prior_prompts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
