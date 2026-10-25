"""全仓 `INSERT INTO checklist_responses` 列清单守卫（冻结基线，只许下降）。

背景（spec chain-closure-phase2-formula-push-engine 需求 6.2 / F9）：真库
`checklist_responses.project_id NOT NULL` 无默认值，且没有 `value` / `status` / `content` 列。
写入站点漏 `project_id` 或写不存在的列，在真 PG 上**必然失败**（新行与冲突行都失败），
而大量单测用可空建表的 SQLite 全绿 —— 本守卫把这一类缺陷的现存规模冻结下来。

扫描口径（纯 AST，不做文本匹配 —— 注释与 docstring 正反两向都会骗过文本扫描）：
- 只看 `backend/app/**/*.py` 里**非 docstring** 的字符串常量与 f-string；
- f-string 的插值段记为 `{…}`，列名为插值的站点单列为「动态列」，不计入两类缺陷；
- 列清单 = `INSERT INTO checklist_responses (` 之后第一个括号内的内容。

本 spec 只修了运行时适配器一处；其余站点跨 39 个文件、多数有他人未提交改动，另立 spec 逐个修。
修掉若干处后请同步下调基线（守卫同时拒绝「基线虚高」）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

#: 真库列（V085 + V089 + V098 + V161 叠加后，information_schema 现查）
REAL_COLUMNS = frozenset({
    "id", "project_id", "wp_id", "item_id", "conclusion", "remark", "wp_ref",
    "updated_by", "created_at", "updated_at", "content_version",
})

#: 2026-09-29 现算基线（修复 formula_runtime 底稿适配器之后）
BASELINE_MISSING_PROJECT_ID = 49
BASELINE_UNKNOWN_COLUMN = 7
#: 允许的「已修但未下调基线」松弛（超过即视为基线虚高）
_SLACK = 5

_PAT = re.compile(r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+checklist_responses\s*\(([^)]*)\)", re.IGNORECASE)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _string_texts(tree: ast.AST) -> list[tuple[int, str]]:
    skip = _docstring_nodes(tree)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                else:
                    parts.append("{…}")
            out.append((node.lineno, "".join(parts)))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            out.append((node.lineno, node.value))
    return out


def scan_source(source: str, path: str = "<mem>") -> list[dict]:
    """返回该源码里每个 INSERT 站点的列清单与缺陷分类。"""
    tree = ast.parse(source)
    sites: list[dict] = []
    seen_f_parts: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                seen_f_parts.add(id(v))
    for lineno, text in _string_texts(tree):
        for m in _PAT.finditer(text):
            cols = [c.strip().strip('"') for c in m.group(1).replace("\n", " ").split(",") if c.strip()]
            dynamic = any("{…}" in c for c in cols)
            unknown = [c for c in cols if "{…}" not in c and c not in REAL_COLUMNS]
            sites.append({
                "path": path, "line": lineno, "cols": cols, "dynamic": dynamic,
                "missing_project_id": "project_id" not in cols,
                "unknown": unknown,
            })
    return sites


def _all_sites() -> list[dict]:
    sites: list[dict] = []
    for p in sorted(APP.rglob("*.py")):
        # utf-8-sig：仓内有带 BOM 的源文件，按 utf-8 解码 ast.parse 会报 U+FEFF
        src = p.read_bytes().decode("utf-8-sig", errors="replace")
        if "checklist_responses" not in src:
            continue
        # f-string 内的常量片段会被 ast.walk 单独再遇到一次 ⇒ 去重（同行同文本只算一次）
        uniq: dict[tuple[int, str], dict] = {}
        for s in scan_source(src, str(p.relative_to(APP.parent)).replace("\\", "/")):
            uniq[(s["line"], ",".join(s["cols"]))] = s
        sites.extend(uniq.values())
    return sites


def test_scanner_self_check():
    """反向自检：扫描器能命中坏样本、放过好样本，且不被 docstring / 注释骗到。"""
    bad = scan_source('q = "INSERT INTO checklist_responses (wp_id, item_id, value) VALUES (1,2,3)"')
    assert len(bad) == 1 and bad[0]["missing_project_id"] and bad[0]["unknown"] == ["value"]
    good = scan_source('q = "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark)"')
    assert len(good) == 1 and not good[0]["missing_project_id"] and not good[0]["unknown"]
    doc = scan_source('def f():\n    """INSERT INTO checklist_responses (from snapshot rows)"""\n    return 1\n')
    assert doc == [], "docstring 被当成真实写入站点"
    comment = scan_source('# INSERT INTO checklist_responses (wp_id)\nx = 1\n')
    assert comment == [], "注释被当成真实写入站点"
    dyn = scan_source('f = "remark"\nq = f"INSERT INTO checklist_responses (id, project_id, {f})"')
    assert dyn and dyn[0]["dynamic"] and not dyn[0]["unknown"]


def test_real_scan_is_not_empty():
    """防空转：真实扫描必须命中站点（否则口径失效，两条基线断言会恒绿）。"""
    assert len(_all_sites()) >= 60


def test_missing_project_id_does_not_grow():
    offenders = [s for s in _all_sites() if s["missing_project_id"] and not s["dynamic"]]
    n = len(offenders)
    listing = "\n".join(f"  {s['path']}:{s['line']} cols={s['cols']}" for s in offenders)
    assert n <= BASELINE_MISSING_PROJECT_ID, (
        f"缺 project_id 的 INSERT 站点从基线 {BASELINE_MISSING_PROJECT_ID} 增至 {n}"
        f"（真库 NOT NULL，必失败）：\n{listing}"
    )
    assert BASELINE_MISSING_PROJECT_ID - n <= _SLACK, (
        f"已修到 {n}，请把 BASELINE_MISSING_PROJECT_ID 下调（当前 {BASELINE_MISSING_PROJECT_ID} 虚高）"
    )


def test_unknown_columns_do_not_grow():
    offenders = [s for s in _all_sites() if s["unknown"]]
    n = len(offenders)
    listing = "\n".join(f"  {s['path']}:{s['line']} 不存在列={s['unknown']}" for s in offenders)
    assert n <= BASELINE_UNKNOWN_COLUMN, (
        f"写不存在列的 INSERT 站点从基线 {BASELINE_UNKNOWN_COLUMN} 增至 {n}：\n{listing}"
    )
    assert BASELINE_UNKNOWN_COLUMN - n <= _SLACK, (
        f"已修到 {n}，请把 BASELINE_UNKNOWN_COLUMN 下调（当前 {BASELINE_UNKNOWN_COLUMN} 虚高）"
    )


def test_formula_runtime_adapter_is_clean():
    """本 spec 修过的站点钉死为干净（回退即红）。"""
    mine = [s for s in _all_sites() if s["path"].endswith("formula_runtime/adapters/workpaper.py")]
    assert mine, "适配器 INSERT 站点未被扫描到（口径失效）"
    assert all(not s["missing_project_id"] and not s["unknown"] for s in mine), mine
