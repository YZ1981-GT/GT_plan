"""`/d2-sync/*` legacy 旁路退役的 pre/post-delete eligibility 现算门（G4-2）。

═══ 为什么需要本门 ═══

总控 DEC-08 把 `/d2-sync/*` 的删除时机绑在「宿主统一路径 + `HOST-CONSUMES-UNIFIED-PATH`
达 `ONLYOFFICE_VERIFIED`」上。该门 2026-09-11 已达标，但**达标不等于可删** ——
删除还要同时满足「无生产调用方」「替换面在位且真有覆盖」「必须保留的判据已迁走」
「防复活负向断言齐备」。本门把这四件事变成机器判据。

═══ 判据形态的三条纪律 ═══

1. **不读文档声明**：里程碑态取自 `workpaper_sync_program_milestones.json` 的
   `state` / `machine_predicates` / `entry_state_counts`，不读任何 README 的自述。
2. **按「是否作为代码使用」判，不按字符串存在判**：Python 侧用 AST 只看
   ``ast.Constant`` 字符串（注释天然不进 AST）；TS/Vue 侧先做真正的注释剥离
   （带字符串/模板串状态机），再看剩下的代码。否则「注释里提了一句 legacy」
   会被误判成「还有调用方」。
3. **一门两相**：legacy 文件在盘 ⇒ pre-delete 相，允许它们自己出现；文件已删
   ⇒ post-delete 相，允许集合收紧为空。post-delete 严格强于 pre-delete。

`--self-check` 对每条判据做反向自检：把输入改成「应当失败」的形态，判据必须真的
翻成 fail。任何一条翻不动即本门自身有缺陷（假绿第②源）。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_FRONTEND = _REPO / "audit-platform" / "frontend"

MILESTONES_PATH = _BACKEND / "data" / "workpaper_sync_program_milestones.json"
CALLBACK_CONTRACT_PATH = _BACKEND / "data" / "onlyoffice_callback_state_contract.json"

#: 被退役的两个 legacy 生产文件。它们在盘 ⇒ pre-delete 相。
LEGACY_BACKEND_ROUTER = _BACKEND / "app" / "routers" / "d2_sync_router.py"
LEGACY_FRONTEND_BRIDGE = (
    _FRONTEND / "src" / "components" / "workpaper" / "sync" / "useD2SyncBridge.ts"
)

#: 必须**保留**的模块：统一 `oo_to_html` 复用它做 store 合并（总控 §2.4.6 可复用资产）。
RETAINED_BRIDGE = (
    _BACKEND / "app" / "services" / "workpaper_sync" / "d2_bidirectional_bridge.py"
)

MILESTONE_ID = "HOST-CONSUMES-UNIFIED-PATH"
NEEDLE = "d2-sync"


class EligibilityStructuralError(RuntimeError):
    """本门赖以度量的输入缺失/形态非法。**不吞** —— 缺输入不得静默判 pass。"""


@dataclass(frozen=True)
class Verdict:
    """一条判据的结论。`result` 只有三态，`unverifiable` 必须带原因。"""

    id: str
    result: str  # pass | fail | unverifiable
    detail: str
    facts: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.result not in {"pass", "fail", "unverifiable"}:
            raise EligibilityStructuralError(f"非法 result: {self.result!r}")
        if self.result != "pass" and not self.detail.strip():
            raise EligibilityStructuralError(f"{self.id}: 非 pass 必须带原因")


def _read(path: Path) -> str:
    if not path.is_file():
        raise EligibilityStructuralError(f"输入文件不存在: {path}")
    return path.read_bytes().decode("utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(_read(path))


# ═══════════════════════════════════════════════════════════════════════════
# TS / Vue 注释剥离：带字符串与模板串状态机
# ═══════════════════════════════════════════════════════════════════════════


def strip_js_comments(text: str) -> str:
    """剥掉 `//` 与 `/* */`，但**不碰**字符串/模板串里的同形字符。

    🔴 用朴素正则剥注释会把 ``'https://x'`` 里的 `//` 当注释起点，把后面整行吞掉
    —— 那会让「还有调用方」被误判成「已无调用方」，正是本门最不能犯的错。
    剥掉的内容一律用等长空格顶替，保持偏移不变（便于报行号）。
    """
    out: list[str] = []
    i = 0
    n = len(text)
    quote: str | None = None
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if quote is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(nxt)
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and nxt == "*":
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            out.append("  ")
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def python_string_literal_hits(source: str, needle: str) -> tuple[str, ...]:
    """AST 里含 `needle` 的字符串常量。注释/docstring 之外的真实字面量才算。

    docstring 也是 ``ast.Constant``，故额外剔除 module/class/function 的首条
    Expression-Constant —— 它是文档，不是端点。
    """
    tree = ast.parse(source)
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstring_nodes.add(id(body[0].value))
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstring_nodes:
            continue
        if needle in node.value:
            hits.append(f"L{getattr(node, 'lineno', 0)}:{node.value[:80]}")
    return tuple(hits)


def _iter_files(root: Path, suffixes: Iterable[str], skip: Callable[[Path], bool]) -> list[Path]:
    found: list[Path] = []
    for suffix in suffixes:
        for path in root.rglob(f"*{suffix}"):
            if skip(path):
                continue
            found.append(path)
    return sorted(found)


def _rel(path: Path) -> str:
    return path.relative_to(_REPO).as_posix()


# ═══════════════════════════════════════════════════════════════════════════
# 相位
# ═══════════════════════════════════════════════════════════════════════════


def detect_phase() -> str:
    """`pre_delete`（两个 legacy 文件仍在盘）/ `post_delete`（都已删）/ `partial`。"""
    backend_alive = LEGACY_BACKEND_ROUTER.is_file()
    frontend_alive = LEGACY_FRONTEND_BRIDGE.is_file()
    if backend_alive and frontend_alive:
        return "pre_delete"
    if not backend_alive and not frontend_alive:
        return "post_delete"
    return "partial"


# ═══════════════════════════════════════════════════════════════════════════
# E1：里程碑态（DEC-08 的解除条件）
# ═══════════════════════════════════════════════════════════════════════════

_ENTRY_BUCKETS_MUST_BE_ZERO = ("REQUEST_PATH_LEGACY", "REQUEST_PATH_VERIFIED", "STALE", "BLOCKED")


def verdict_milestone(
    registry: Mapping[str, Any] | None = None, *, phase: str = "pre_delete"
) -> Verdict:
    """里程碑判据 —— **相位不同，问的问题就不同**。

    `pre_delete` 问的是「能不能删」：DEC-08 要求 `ONLYOFFICE_VERIFIED` + 谓词全 pass。

    `post_delete` 问的是「删完有没有回退」，**刻意不再断言 freshness**：删除本身会让
    删除前采的浏览器观测 stale（总控 §2.3 与 Task 45 预定行为），此时若继续要求
    `ONLYOFFICE_VERIFIED`，本门会为一个与「删得干不干净」无关的原因永久打红，而
    freshness 已经由 `workpaper-sync-program-milestones` 那道门负责 —— 在这里重复断言
    等于给同一个事实造第二个真源。故本相位只守**回退**：不得出现 `REQUEST_PATH_LEGACY`
    的 entry，顶层不得掉回 `BLOCKED`。
    """
    payload = registry if registry is not None else _load_json(MILESTONES_PATH)
    milestones = payload.get("milestones") or []
    row = next((m for m in milestones if m.get("id") == MILESTONE_ID), None)
    if row is None:
        raise EligibilityStructuralError(
            f"milestone registry 里没有 {MILESTONE_ID} —— DEC-08 的解除条件无从度量"
        )
    state = str(row.get("state") or "")
    preds = row.get("machine_predicates") or []
    failing = tuple(str(p.get("id")) for p in preds if p.get("result") != "pass")
    blockers = row.get("blockers") or []
    counts = dict(row.get("entry_state_counts") or {})
    verified = int(counts.get("ONLYOFFICE_VERIFIED") or 0)
    nonzero_bad = {k: int(counts.get(k) or 0) for k in _ENTRY_BUCKETS_MUST_BE_ZERO if int(counts.get(k) or 0)}
    facts = {
        "state": state,
        "predicate_count": len(preds),
        "failing_predicates": failing,
        "blocker_count": len(blockers),
        "entry_state_counts": counts,
    }
    facts["phase"] = phase
    legacy = int(counts.get("REQUEST_PATH_LEGACY") or 0)

    if phase == "post_delete":
        vid = "E1.milestone-no-legacy-regression"
        problems: list[str] = []
        if legacy:
            problems.append(f"仍有 {legacy} 个 entry 处于 REQUEST_PATH_LEGACY —— 宿主退回了旁路")
        if state == "BLOCKED":
            problems.append("milestone 顶层掉回 BLOCKED")
        if problems:
            return Verdict(vid, "fail", "；".join(problems), facts)
        note = (
            "（删除导致删除前采的浏览器观测 stale 属预定行为；freshness 由 "
            "workpaper-sync-program-milestones 那道门负责，本门不重复断言）"
            if state == "STALE"
            else ""
        )
        return Verdict(
            vid,
            "pass",
            f"{MILESTONE_ID}={state}，REQUEST_PATH_LEGACY=0、未掉回 BLOCKED{note}",
            facts,
        )

    vid = "E1.milestone-onlyoffice-verified"
    problems = []
    if state != "ONLYOFFICE_VERIFIED":
        problems.append(f"milestone.state={state!r} != ONLYOFFICE_VERIFIED")
    if failing:
        problems.append(f"未通过谓词 {list(failing)}")
    if blockers:
        problems.append(f"blockers 非空（{len(blockers)} 条）")
    if verified <= 0:
        problems.append("entry_state_counts.ONLYOFFICE_VERIFIED == 0（分母为空不算达标）")
    if nonzero_bad:
        problems.append(f"仍有非终态 entry {nonzero_bad}")
    if problems:
        return Verdict(vid, "fail", "；".join(problems), facts)
    return Verdict(
        vid,
        "pass",
        f"{MILESTONE_ID}={state}，{len(preds)} 条谓词全 pass，ONLYOFFICE_VERIFIED entry={verified}",
        facts,
    )


# ═══════════════════════════════════════════════════════════════════════════
# E2：生产源码零调用（按「是否作为代码使用」判）
# ═══════════════════════════════════════════════════════════════════════════


def _backend_app_files() -> list[Path]:
    return _iter_files(
        _BACKEND / "app",
        (".py",),
        skip=lambda p: "__pycache__" in p.parts,
    )


def verdict_backend_no_caller(phase: str, *, sources: Mapping[str, str] | None = None) -> Verdict:
    """`backend/app/**` 里除被删文件自身外，不得有含 `d2-sync` 的字符串字面量。"""
    if sources is None:
        sources = {_rel(p): _read(p) for p in _backend_app_files()}
    allowed = {_rel(LEGACY_BACKEND_ROUTER)} if phase == "pre_delete" else set()
    offenders: dict[str, tuple[str, ...]] = {}
    for rel, text in sorted(sources.items()):
        if NEEDLE not in text:
            continue
        try:
            hits = python_string_literal_hits(text, NEEDLE)
        except SyntaxError as exc:  # 语法坏了不得静默跳过
            raise EligibilityStructuralError(f"{rel}: 无法解析（{exc}）") from exc
        if not hits:
            continue  # 只出现在注释/docstring ⇒ 不是调用方
        if rel in allowed:
            continue
        offenders[rel] = hits
    facts = {"scanned": len(sources), "allowed": sorted(allowed), "offenders": {k: list(v) for k, v in offenders.items()}}
    if offenders:
        return Verdict(
            "E2a.backend-no-production-caller",
            "fail",
            f"后端仍有 {len(offenders)} 个模块把 `{NEEDLE}` 当字符串字面量用：{sorted(offenders)}",
            facts,
        )
    return Verdict(
        "E2a.backend-no-production-caller",
        "pass",
        f"扫 {len(sources)} 个 backend/app 模块，允许集 {sorted(allowed) or '空'} 之外零字面量",
        facts,
    )


def _frontend_production_files() -> list[Path]:
    """`src/**` 的 ts/vue，排除测试目录 —— 测试里的 `/d2-sync/` 是**负向断言**。"""
    return _iter_files(
        _FRONTEND / "src",
        (".ts", ".vue"),
        skip=lambda p: "__tests__" in p.parts or p.name.endswith((".spec.ts", ".test.ts")),
    )


def verdict_frontend_no_caller(phase: str, *, sources: Mapping[str, str] | None = None) -> Verdict:
    """`frontend/src` 非测试代码里，注释剥离后不得再出现 `d2-sync`。"""
    if sources is None:
        sources = {_rel(p): _read(p) for p in _frontend_production_files()}
    allowed = {_rel(LEGACY_FRONTEND_BRIDGE)} if phase == "pre_delete" else set()
    offenders: dict[str, list[str]] = {}
    for rel, text in sorted(sources.items()):
        if NEEDLE not in text:
            continue
        code = strip_js_comments(text)
        lines = [
            f"L{no}:{line.strip()[:80]}"
            for no, line in enumerate(code.splitlines(), 1)
            if NEEDLE in line
        ]
        if not lines:
            continue  # 只在注释里 ⇒ 不是调用方
        if rel in allowed:
            continue
        offenders[rel] = lines
    facts = {"scanned": len(sources), "allowed": sorted(allowed), "offenders": offenders}
    if offenders:
        return Verdict(
            "E2b.frontend-no-production-caller",
            "fail",
            f"前端非测试代码仍有 {len(offenders)} 个文件在代码里用 `{NEEDLE}`：{sorted(offenders)}",
            facts,
        )
    return Verdict(
        "E2b.frontend-no-production-caller",
        "pass",
        f"扫 {len(sources)} 个 src 生产文件（剥注释后），允许集 {sorted(allowed) or '空'} 之外零命中",
        facts,
    )


_ROUTER_REGISTRY = _BACKEND / "app" / "router_registry" / "workpaper.py"
_REGISTRY_TOKEN = "d2_sync"


def route_decorator_paths(source: str, needle: str) -> tuple[str, ...]:
    """AST 里 `@router.<verb>("<path>")` 的 path 含 `needle` 的那些。

    只看装饰器第一个位置实参 —— 这是「真的挂成了 HTTP 路由」的判据；模块里别处出现
    同样的字符串（日志、文案）不算路由。
    """
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                continue
            if deco.func.attr not in {"get", "post", "put", "patch", "delete", "api_route"}:
                continue
            if not deco.args:
                continue
            first = deco.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and needle in first.value:
                found.append(f"{node.name} -> {first.value}")
    return tuple(found)


def registry_binding_names(source: str, token: str) -> tuple[str, ...]:
    """registry 模块里对 `token` 这个名字的**代码级**引用（import 别名 + Name 引用）。"""
    tree = ast.parse(source)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if (alias.asname or alias.name) == token:
                    hits.append(f"L{node.lineno}:import {node.module}.{alias.name} as {token}")
        elif isinstance(node, ast.Name) and node.id == token:
            hits.append(f"L{node.lineno}:Name {token}")
    return tuple(hits)


def verdict_no_route_registration(
    phase: str,
    *,
    router_sources: Mapping[str, str] | None = None,
    registry_source: str | None = None,
) -> Verdict:
    """post-delete 相：全仓 router 无 `d2-sync` 路由，且 registry 不再绑定该名字。"""
    if router_sources is None:
        router_sources = {
            _rel(p): _read(p)
            for p in _iter_files(_BACKEND / "app" / "routers", (".py",), skip=lambda p: "__pycache__" in p.parts)
        }
    if registry_source is None:
        registry_source = _read(_ROUTER_REGISTRY)
    routes: dict[str, list[str]] = {}
    for rel, text in sorted(router_sources.items()):
        if NEEDLE not in text:
            continue
        paths = route_decorator_paths(text, NEEDLE)
        if paths:
            routes[rel] = list(paths)
    bindings = registry_binding_names(registry_source, _REGISTRY_TOKEN)
    facts = {"routes": routes, "registry_bindings": list(bindings), "phase": phase}
    if phase == "pre_delete":
        # pre-delete 相只要求「路由只由被删文件提供」——它自己当然还挂着。
        stray = {k: v for k, v in routes.items() if k != _rel(LEGACY_BACKEND_ROUTER)}
        if stray:
            return Verdict(
                "E2c.no-route-registration",
                "fail",
                f"除被删 router 外还有别的模块挂了 `{NEEDLE}` 路由：{sorted(stray)}",
                facts,
            )
        return Verdict(
            "E2c.no-route-registration",
            "pass",
            f"pre-delete：`{NEEDLE}` 路由只由 {_rel(LEGACY_BACKEND_ROUTER)} 提供"
            f"（{len(routes.get(_rel(LEGACY_BACKEND_ROUTER)) or [])} 条），registry 绑定 {len(bindings)} 处待摘",
            facts,
        )
    problems: list[str] = []
    if routes:
        problems.append(f"仍有模块挂着 `{NEEDLE}` 路由：{sorted(routes)}")
    if bindings:
        problems.append(f"registry 仍绑定 `{_REGISTRY_TOKEN}`：{list(bindings)}")
    if problems:
        return Verdict("E2c.no-route-registration", "fail", "；".join(problems), facts)
    return Verdict(
        "E2c.no-route-registration",
        "pass",
        f"post-delete：全仓 router 零 `{NEEDLE}` 路由，registry 零 `{_REGISTRY_TOKEN}` 绑定",
        facts,
    )


# ═══════════════════════════════════════════════════════════════════════════
# E3：替换面在位且真有覆盖
# ═══════════════════════════════════════════════════════════════════════════


def js_block_containing(code: str, needle: str, *, openers: Sequence[str] = ("it(", "test(")) -> str:
    """抠出包含 `needle` 的那个 `it(...)` / `test(...)` 块（花括号配对）。

    🔴 判「某条断言还在不在」必须落在**同一个块**里：只在整文件里找 `toBeGreaterThan`
    会被别的用例顶替，删掉目标断言仍绿（假绿第②源）。
    """
    at = code.find(needle)
    if at < 0:
        return ""
    start = -1
    for opener in openers:
        pos = code.rfind(opener, 0, at)
        start = max(start, pos)
    if start < 0:
        return ""
    brace = code.find("{", start)
    if brace < 0:
        return ""
    depth = 0
    for i in range(brace, len(code)):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return code[start : i + 1]
    return code[start:]


def _block_requires(path: Path, anchor: str, required: Sequence[str], verdict_id: str, what: str) -> Verdict:
    code = strip_js_comments(_read(path))
    block = js_block_containing(code, anchor)
    facts = {"path": _rel(path), "anchor": anchor, "block_chars": len(block)}
    if not block:
        return Verdict(verdict_id, "fail", f"{_rel(path)} 里找不到含 `{anchor}` 的用例块 —— {what} 已消失", facts)
    missing = [token for token in required if token not in block]
    facts["missing"] = missing
    if missing:
        return Verdict(verdict_id, "fail", f"{_rel(path)} 的用例块缺 {missing} —— {what} 被削弱", facts)
    return Verdict(verdict_id, "pass", f"{what} 在位（{_rel(path)}，块 {len(block)} 字符）", facts)


#: legacy `_issue_forcesave` 的三态 → 统一 command_service 的封闭 outcome 域。
_LEGACY_OUTCOME_MAP = {
    "accepted": "accepted",
    "nothing_to_save": "no_changes",
    "rejected": "doc_not_online",
}
_REQUIRED_ERROR_CODES = frozenset({0, 1, 2, 3, 4, 5, 6})


def verdict_command_service_superset(contract: Mapping[str, Any] | None = None) -> Verdict:
    """统一 command_service 的返回码真值表必须**严格覆盖** legacy 三态。"""
    payload = contract if contract is not None else _load_json(CALLBACK_CONTRACT_PATH)
    rows = ((payload.get("command_service") or {}).get("return_codes")) or []
    if not rows:
        raise EligibilityStructuralError(
            f"{_rel(CALLBACK_CONTRACT_PATH)} 缺 command_service.return_codes —— 替换面无从度量"
        )
    errors = {int(r["error"]) for r in rows if "error" in r}
    outcomes = {str(r.get("platform_outcome") or "") for r in rows}
    missing_errors = sorted(_REQUIRED_ERROR_CODES - errors)
    missing_outcomes = sorted(v for v in _LEGACY_OUTCOME_MAP.values() if v not in outcomes)
    facts = {
        "error_codes": sorted(errors),
        "outcomes": sorted(outcomes),
        "legacy_state_map": _LEGACY_OUTCOME_MAP,
        "missing_errors": missing_errors,
        "missing_outcomes": missing_outcomes,
    }
    problems: list[str] = []
    if missing_errors:
        problems.append(f"返回码真值表缺 error {missing_errors}")
    if missing_outcomes:
        problems.append(f"outcome 域缺 {missing_outcomes}（legacy 三态无处落）")
    if len(outcomes) < 3:
        problems.append(f"outcome 域只有 {len(outcomes)} 个值，压不住 legacy 三态")
    if problems:
        return Verdict("E3a.command-service-superset", "fail", "；".join(problems), facts)
    return Verdict(
        "E3a.command-service-superset",
        "pass",
        f"统一返回码真值表覆盖 error {sorted(errors)} / {len(outcomes)} 个 outcome，"
        f"legacy 三态映射 {_LEGACY_OUTCOME_MAP}",
        facts,
    )


_OO_TO_HTML = _BACKEND / "app" / "services" / "workpaper_sync" / "oo_to_html.py"
_BRIDGE_MODULE_NAME = "d2_bidirectional_bridge"


def verdict_bridge_retained(*, oo_to_html_source: str | None = None, bridge_exists: bool | None = None) -> Verdict:
    """`d2_bidirectional_bridge` **必须保留** —— 统一 `oo_to_html` 在用它做 store 合并。

    这条是「别删多了」的反向门：它 fail 表示删过头，而不是没删干净。
    """
    text = oo_to_html_source if oo_to_html_source is not None else _read(_OO_TO_HTML)
    exists = RETAINED_BRIDGE.is_file() if bridge_exists is None else bridge_exists
    referenced = bool(re.search(rf"\b{_BRIDGE_MODULE_NAME}\b", strip_js_comments(text)))
    facts = {"bridge_exists": exists, "referenced_by_oo_to_html": referenced, "path": _rel(RETAINED_BRIDGE)}
    if referenced and not exists:
        return Verdict(
            "E3b.bridge-module-retained",
            "fail",
            f"统一 oo_to_html 仍引用 `{_BRIDGE_MODULE_NAME}` 但模块已不在盘 —— 删过头了",
            facts,
        )
    if not referenced:
        return Verdict(
            "E3b.bridge-module-retained",
            "fail",
            f"统一 oo_to_html 不再引用 `{_BRIDGE_MODULE_NAME}` —— "
            "store 合并的复用关系断了，保留该模块的理由随之消失，须重新裁决",
            facts,
        )
    return Verdict(
        "E3b.bridge-module-retained",
        "pass",
        f"`{_BRIDGE_MODULE_NAME}` 在盘且被统一 oo_to_html 引用（总控 §2.4.6 可复用资产，不删）",
        facts,
    )


_HOST_WIRING_SPEC = (
    _FRONTEND / "src" / "components" / "workpaper" / "__tests__" / "d2SyncHostWiring.spec.ts"
)
_BRIDGE_MACHINE_SPEC = (
    _FRONTEND
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "__tests__"
    / "workpaperSyncBridgeMachine.spec.ts"
)
_OO_SHEET_HOST = _FRONTEND / "src" / "components" / "workpaper" / "GtOnlyOfficeSheet.vue"


_INDEX_OF_RE = r"""(\w+)\s*=\s*[^\n]*?\.indexOf\(\s*['"]{name}['"]\s*\)"""


def verdict_defect_a_reverse_lock(*, source: str | None = None) -> Verdict:
    """缺陷 A（切 OO 前不 flush）的反向锁必须在**统一宿主**上，不得随 legacy 一起删。

    🔴 判据形态踩过一次坑（M06 变异实测 GREEN）：原判据要求块里含子串
    ``toBeGreaterThan``，而同一个块里还有 ``expect(flushAt).toBeGreaterThanOrEqual(0)``
    —— 它**包含**那个子串。于是把真正的顺序断言
    ``expect(readAt).toBeGreaterThan(flushAt)`` 改成 ``expect(readAt).not.toBe(-1)``
    之后判据照样绿。这正是「grep 式守卫只查字符串存在」的假绿第②源。

    改成结构判据：先解析出两个下标变量各自绑定的是哪个符号，再要求
    ``expect(<读下标>).toBeGreaterThan(<flush 下标>)`` —— 两个变量名由源码现读，
    改名不影响，削弱断言必打红。
    """
    code = strip_js_comments(source if source is not None else _read(_HOST_WIRING_SPEC))
    block = js_block_containing(code, "flushPendingSave")
    facts: dict[str, Any] = {"path": _rel(_HOST_WIRING_SPEC), "block_chars": len(block)}
    vid = "E3c.defect-a-reverse-lock"
    what = "缺陷 A 反向锁（flush 严格早于读 store projection）"
    if not block:
        return Verdict(vid, "fail", f"{_rel(_HOST_WIRING_SPEC)} 里找不到含 flushPendingSave 的用例块 —— {what} 已消失", facts)
    flush_match = re.search(_INDEX_OF_RE.format(name="flushPendingSave"), block)
    read_match = re.search(_INDEX_OF_RE.format(name="readStoreProjection"), block)
    facts["flush_var"] = flush_match.group(1) if flush_match else None
    facts["read_var"] = read_match.group(1) if read_match else None
    if not flush_match or not read_match:
        return Verdict(
            vid,
            "fail",
            f"用例块里取不到两个下标变量（flush={facts['flush_var']} read={facts['read_var']}）—— {what} 已被拆掉",
            facts,
        )
    flush_var, read_var = flush_match.group(1), read_match.group(1)
    ordering = re.search(
        rf"expect\(\s*{re.escape(read_var)}\s*\)\s*\.toBeGreaterThan\(\s*{re.escape(flush_var)}\s*\)",
        block,
    )
    facts["ordering_assertion"] = bool(ordering)
    if not ordering:
        return Verdict(
            vid,
            "fail",
            f"用例块里没有 `expect({read_var}).toBeGreaterThan({flush_var})` —— "
            f"{what} 被削弱成「只要出现过」，flush 可以晚于读 store",
            facts,
        )
    return Verdict(vid, "pass", f"{what} 在位（{read_var} > {flush_var}，{_rel(_HOST_WIRING_SPEC)}）", facts)


def verdict_four_state_text_guard() -> Verdict:
    """缺陷 B 的语义继任者：四类结果文案两两不同，且没有一条是「同步成功」。"""
    return _block_requires(
        _BRIDGE_MACHINE_SPEC,
        "WP_BRIDGE_STATE_TEXT.forcesave_accepted",
        (
            "WP_BRIDGE_STATE_TEXT.forcesave_accepted",
            "WP_BRIDGE_STATE_TEXT.incoming_durable",
            "WP_BRIDGE_STATE_TEXT.applied",
            "WP_BRIDGE_STATE_TEXT.conflict",
            "toBe(4)",
        ),
        "E3d.four-state-text-guard",
        "四态结果文案互不相同门（取代 legacy durable 三态文案判据）",
    )


def verdict_forcesave_fail_closed(*, source: str | None = None) -> Verdict:
    """G4-0a：未注入 `forcesaveEndpoint` 时共享 OO 组件必须 fail-closed，不发 HTTP。"""
    code = strip_js_comments(source if source is not None else _read(_OO_SHEET_HOST))
    needed = ("forcesaveEndpoint", "if (!endpoint)", "accepted: false")
    missing = [token for token in needed if token not in code]
    facts = {"path": _rel(_OO_SHEET_HOST), "missing": missing}
    if missing:
        return Verdict(
            "E3e.forcesave-fail-closed",
            "fail",
            f"{_rel(_OO_SHEET_HOST)} 的 fail-closed 形态缺 {missing} —— "
            "179 个共用该组件的 entry 会重新把 forcesave 泄漏到 D2-2（总控 gap 14）",
            facts,
        )
    return Verdict(
        "E3e.forcesave-fail-closed",
        "pass",
        f"G4-0a fail-closed 在位（{_rel(_OO_SHEET_HOST)}）",
        facts,
    )


# ═══════════════════════════════════════════════════════════════════════════
# E4：必须保留的判据已迁到新宿主
# ═══════════════════════════════════════════════════════════════════════════

_REHOMED_SPEC = _BACKEND / "tests" / "workpaper_sync" / "test_d2_store_value_equivalence.py"

#: 迁移后必须仍被覆盖的三个符号。前两个是 legacy 守卫 Half A 的判据对象，
#: 第三个是「统一路径真的在用它们」的反向锁 —— 缺它就退化成孤立单测。
_REHOMED_SYMBOLS = ("same_store_value", "_assign_store_value", "merge_projection_into_store_rows")


def verdict_store_value_rehomed(*, source: str | None = None) -> Verdict:
    if source is None:
        if not _REHOMED_SPEC.is_file():
            return Verdict(
                "E4.store-value-equivalence-rehomed",
                "fail",
                f"{_rel(_REHOMED_SPEC)} 不存在 —— legacy 守卫 Half A 的三条 store 值等价判据"
                "还没有新宿主；直接删 legacy 守卫会让统一 oo_to_html 依赖的 "
                "`d2_store_value_equivalence` 失去**全部**覆盖",
                {"path": _rel(_REHOMED_SPEC), "exists": False},
            )
        source = _read(_REHOMED_SPEC)
    hits = python_string_literal_hits(source, "never-matches-anything")  # 触发语法校验
    del hits
    missing = [name for name in _REHOMED_SYMBOLS if name not in source]
    facts = {"path": _rel(_REHOMED_SPEC), "missing": missing, "required": list(_REHOMED_SYMBOLS)}
    if missing:
        return Verdict(
            "E4.store-value-equivalence-rehomed",
            "fail",
            f"{_rel(_REHOMED_SPEC)} 缺 {missing} —— 迁移不完整",
            facts,
        )
    return Verdict(
        "E4.store-value-equivalence-rehomed",
        "pass",
        f"store 值等价判据已迁到 {_rel(_REHOMED_SPEC)}，覆盖 {list(_REHOMED_SYMBOLS)}",
        facts,
    )


# ═══════════════════════════════════════════════════════════════════════════
# E5：防复活负向断言清册
# ═══════════════════════════════════════════════════════════════════════════

_FE_WP = _FRONTEND / "src" / "components" / "workpaper"
_E2E = _FRONTEND / "e2e"

#: (相对路径, 该文件里必须仍在的负向断言片段)。删 legacy 后这些是唯一防复活手段。
NEGATIVE_ASSERTION_INVENTORY: tuple[tuple[Path, tuple[str, ...]], ...] = (
    (_FE_WP / "__tests__" / "d2SyncHostWiring.spec.ts", ("not.toMatch", "useD2SyncBridge")),
    (_FE_WP / "__tests__" / "GtOnlyOfficeSheet.spec.ts", ("not.toMatch", "d2-sync")),
    (_E2E / "g4-0d-d2-unified-path.spec.ts", ("d2_sync", "toEqual([])")),
    (_E2E / "g4-1-h1-unified-path.spec.ts", ("d2_sync", "toEqual([])")),
    (_E2E / "g4-1-g7-unified-path.spec.ts", ("d2_sync", "toEqual([])")),
    (_E2E / "g4-1-b60-unified-path.spec.ts", ("d2_sync", "toEqual([])")),
    (
        _BACKEND / "scripts" / "gen" / "generate_workpaper_sync_program_milestones.py",
        ('"/d2-sync/" in path',),
    ),
)


def verdict_negative_assertions() -> Verdict:
    broken: dict[str, Any] = {}
    for path, tokens in NEGATIVE_ASSERTION_INVENTORY:
        rel = _rel(path)
        if not path.is_file():
            broken[rel] = "文件不存在"
            continue
        code = _read(path)
        if path.suffix in {".ts", ".vue"}:
            code = strip_js_comments(code)
        missing = [token for token in tokens if token not in code]
        if missing:
            broken[rel] = f"缺 {missing}"
    facts = {"inventory_size": len(NEGATIVE_ASSERTION_INVENTORY), "broken": broken}
    if broken:
        return Verdict(
            "E5.negative-assertion-inventory",
            "fail",
            f"{len(broken)}/{len(NEGATIVE_ASSERTION_INVENTORY)} 处防复活负向断言失效：{broken}",
            facts,
        )
    return Verdict(
        "E5.negative-assertion-inventory",
        "pass",
        f"{len(NEGATIVE_ASSERTION_INVENTORY)} 处防复活负向断言全部在位",
        facts,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════════════════


def evaluate(phase: str | None = None) -> dict[str, Any]:
    resolved = phase or detect_phase()
    verdicts: list[Verdict] = []
    if resolved == "partial":
        verdicts.append(
            Verdict(
                "E0.phase-is-consistent",
                "fail",
                f"半删状态：router 在盘={LEGACY_BACKEND_ROUTER.is_file()} / "
                f"bridge 在盘={LEGACY_FRONTEND_BRIDGE.is_file()} —— "
                "两侧必须同批删除，否则前端调用面还在而后端已 404",
                {"phase": resolved},
            )
        )
    else:
        verdicts.append(
            Verdict("E0.phase-is-consistent", "pass", f"相位一致：{resolved}", {"phase": resolved})
        )
    verdicts.append(verdict_milestone(phase=resolved))
    verdicts.append(verdict_backend_no_caller(resolved))
    verdicts.append(verdict_frontend_no_caller(resolved))
    verdicts.append(verdict_no_route_registration(resolved))
    verdicts.append(verdict_command_service_superset())
    verdicts.append(verdict_bridge_retained())
    verdicts.append(verdict_defect_a_reverse_lock())
    verdicts.append(verdict_four_state_text_guard())
    verdicts.append(verdict_forcesave_fail_closed())
    verdicts.append(verdict_store_value_rehomed())
    verdicts.append(verdict_negative_assertions())
    counts = {"pass": 0, "fail": 0, "unverifiable": 0}
    for v in verdicts:
        counts[v.result] += 1
    eligible = counts["fail"] == 0 and counts["unverifiable"] == 0
    return {
        "work_package": "G4-2",
        "phase": resolved,
        "eligible_to_delete": eligible if resolved == "pre_delete" else None,
        "post_delete_clean": eligible if resolved == "post_delete" else None,
        "counts": counts,
        "verdicts": [
            {"id": v.id, "result": v.result, "detail": v.detail, "facts": v.facts} for v in verdicts
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 反向自检：每条判据必须能被打红
# ═══════════════════════════════════════════════════════════════════════════


def self_check() -> list[dict[str, Any]]:
    """把输入换成「应当失败」的形态，逐条确认判据真的翻成 fail。

    翻不动即本门自身有缺陷 —— 那正是「grep 式守卫只查字符串存在」的假绿第②源。
    """
    rows: list[dict[str, Any]] = []

    def record(check_id: str, verdict: Verdict, note: str) -> None:
        rows.append(
            {
                "check": check_id,
                "flipped": verdict.result == "fail",
                "observed": verdict.result,
                "note": note,
            }
        )

    def record_stays_green(check_id: str, verdict: Verdict, note: str) -> None:
        """反向的反向：本该放行的形态若被打红，本门就会逼人去删注释/删负向断言。"""
        rows.append(
            {
                "check": check_id,
                "flipped": verdict.result == "pass",
                "observed": verdict.result,
                "note": note,
            }
        )

    record(
        "E1",
        verdict_milestone({"milestones": [{"id": MILESTONE_ID, "state": "REQUEST_PATH_LEGACY"}]}),
        "里程碑退回 REQUEST_PATH_LEGACY",
    )
    record(
        "E1.post-delete-legacy-regression",
        verdict_milestone(
            {
                "milestones": [
                    {
                        "id": MILESTONE_ID,
                        "state": "STALE",
                        "machine_predicates": [],
                        "blockers": [],
                        "entry_state_counts": {"ONLYOFFICE_VERIFIED": 3, "REQUEST_PATH_LEGACY": 1},
                    }
                ]
            },
            phase="post_delete",
        ),
        "post-delete 相：有 entry 退回 REQUEST_PATH_LEGACY 必打红",
    )
    record_stays_green(
        "E1.post-delete-stale-is-not-a-regression",
        verdict_milestone(
            {
                "milestones": [
                    {
                        "id": MILESTONE_ID,
                        "state": "STALE",
                        "machine_predicates": [],
                        "blockers": [{"x": 1}],
                        "entry_state_counts": {"ONLYOFFICE_VERIFIED": 0, "STALE": 4},
                    }
                ]
            },
            phase="post_delete",
        ),
        "post-delete 相：删除导致的 STALE **不得**被当成回退（freshness 归 milestone 门）",
    )
    record(
        "E1.entry-bucket",
        verdict_milestone(
            {
                "milestones": [
                    {
                        "id": MILESTONE_ID,
                        "state": "ONLYOFFICE_VERIFIED",
                        "machine_predicates": [{"id": "x", "result": "pass"}],
                        "blockers": [],
                        "entry_state_counts": {"ONLYOFFICE_VERIFIED": 3, "REQUEST_PATH_LEGACY": 1},
                    }
                ]
            }
        ),
        "顶层已 verified 但仍有 1 个 entry 处于 REQUEST_PATH_LEGACY",
    )
    record(
        "E2a",
        verdict_backend_no_caller(
            "post_delete",
            sources={"backend/app/routers/fake.py": 'X = "/api/workpapers/{x}/d2-sync/status"\n'},
        ),
        "注入一个后端调用方",
    )
    record_stays_green(
        "E2a.comment-only-is-not-a-caller",
        verdict_backend_no_caller(
            "post_delete", sources={"backend/app/x.py": "# 提到 d2-sync 但不是调用\nY = 1\n"}
        ),
        "只在注释里提到 d2-sync **不得**判成调用方（AST 天然不收注释）",
    )
    record(
        "E2b",
        verdict_frontend_no_caller(
            "post_delete",
            sources={"src/x.ts": "await http.get(`/api/workpapers/${id}/d2-sync/status`)\n"},
        ),
        "注入一个前端调用方",
    )
    record_stays_green(
        "E2b.comment-only-is-not-a-caller",
        verdict_frontend_no_caller("post_delete", sources={"src/x.ts": "// legacy d2-sync 已退役\n"}),
        "前端注释提到 d2-sync **不得**判成调用方（注释剥离生效）",
    )
    record_stays_green(
        "E2b.url-with-double-slash-not-eaten",
        verdict_frontend_no_caller(
            "post_delete", sources={"src/x.ts": "const u = 'https://x/ok'\n// d2-sync\n"}
        ),
        "`https://` 里的 `//` **不得**被当注释起点吞掉后续（剥离状态机的核心回归）",
    )
    record(
        "E2c",
        verdict_no_route_registration(
            "post_delete",
            router_sources={"backend/app/routers/fake.py": '@router.get("/{x}/d2-sync/status")\nasync def f(): ...\n'},
            registry_source="def r():\n    pass\n",
        ),
        "注入一条 d2-sync 路由",
    )
    record(
        "E2c.registry-binding",
        verdict_no_route_registration(
            "post_delete",
            router_sources={},
            registry_source="from app.routers.d2_sync_router import router as d2_sync\n",
        ),
        "registry 仍绑定 d2_sync",
    )
    record(
        "E3a",
        verdict_command_service_superset({"command_service": {"return_codes": [{"error": 0, "platform_outcome": "accepted"}]}}),
        "返回码真值表退化成只有 error 0",
    )
    record(
        "E3b",
        verdict_bridge_retained(oo_to_html_source="# 不再引用桥\n", bridge_exists=True),
        "统一 oo_to_html 不再引用桥（保留理由消失）",
    )
    record(
        "E3b.deleted-too-much",
        verdict_bridge_retained(oo_to_html_source="import d2_bidirectional_bridge\n", bridge_exists=False),
        "桥被删掉但统一路径还在用它 —— 删过头",
    )
    record(
        "E3c.substring-trap",
        verdict_defect_a_reverse_lock(
            source=(
                "it('x', () => {\n"
                "  const flushAt = args.indexOf('flushPendingSave')\n"
                "  const readAt = args.indexOf('readStoreProjection')\n"
                "  expect(flushAt).toBeGreaterThanOrEqual(0)\n"
                "  expect(readAt).not.toBe(-1)\n"
                "})\n"
            )
        ),
        "顺序断言被削弱成 not.toBe(-1)，而同块仍有 toBeGreaterThanOrEqual（M06 的子串陷阱）",
    )
    record_stays_green(
        "E3c.renaming-is-allowed",
        verdict_defect_a_reverse_lock(
            source=(
                "it('x', () => {\n"
                "  const a = args.indexOf('flushPendingSave')\n"
                "  const b = args.indexOf('readStoreProjection')\n"
                "  expect(b).toBeGreaterThan(a)\n"
                "})\n"
            )
        ),
        "变量改名 **不得**打红（判据现读变量名而非写死 flushAt/readAt）",
    )
    record(
        "E3e",
        verdict_forcesave_fail_closed(source="function forceSave() { post(url) }\n"),
        "forcesave fail-closed 被去掉",
    )
    record(
        "E4",
        verdict_store_value_rehomed(source="import pytest\n"),
        "迁移宿主里没有任何被要求的符号",
    )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G4-2 `/d2-sync/*` 退役 eligibility 门")
    parser.add_argument("--json", type=Path, default=None, help="把结果写到该路径（UTF-8）")
    parser.add_argument("--self-check", action="store_true", help="只跑反向自检")
    parser.add_argument(
        "--phase", choices=("pre_delete", "post_delete"), default=None, help="覆盖相位（默认按磁盘现测）"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_check:
        rows = self_check()
        bad = [r for r in rows if not r["flipped"]]
        for row in rows:
            mark = "OK " if row["flipped"] else "BAD"
            print(f"[{mark}] {row['check']:38s} observed={row['observed']:12s} {row['note']}")
        print(f"\n[SELF-CHECK] {len(rows) - len(bad)}/{len(rows)} 条判据可被翻动")
        return 0 if not bad else 1

    report = evaluate(args.phase)
    for row in report["verdicts"]:
        mark = {"pass": "PASS", "fail": "FAIL", "unverifiable": "UNVR"}[row["result"]]
        print(f"[{mark}] {row['id']:40s} {row['detail']}")
    print(
        f"\n[G4-2] phase={report['phase']} counts={report['counts']} "
        f"eligible_to_delete={report['eligible_to_delete']} "
        f"post_delete_clean={report['post_delete_clean']}"
    )
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[G4-2] 结果已写入 {args.json}")
    return 0 if report["counts"]["fail"] == 0 and report["counts"]["unverifiable"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
