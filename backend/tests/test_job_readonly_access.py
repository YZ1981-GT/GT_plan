"""F24 / Sprint 5.17: GET /jobs/{id}* 应放宽至项目组 readonly 成员。

需求（requirements F24）：
- 项目组成员（含 readonly 角色）都可以查看导入作业的实时状态
  （不只是 holder/PM），方便"只读旁观"
- POST /jobs/{id}/* 写操作（cancel/retry/resume/takeover）仍需 edit
  或更高权限

实现策略：
采用静态扫描而非运行时测试 —— 运行时 FastAPI 权限测试需要完整 app +
auth override，复杂度高；静态扫描 router 文件里的 `require_project_access`
参数更稳定、覆盖面更广。

扫描规则：
1. 所有 GET 路径含 `/jobs/` 的端点必须使用 `require_project_access("readonly")`
2. 所有 POST 路径含 `/jobs/` 的端点必须使用 `require_project_access("edit")`
   或更高级别（在本次 spec 范围内）

豁免：
- `get_current_user` 无项目级权限判断 —— 非本次 spec 范围，不强制迁移
  （archive.py / word_export.py 属其他业务域，另行评估）
"""
from __future__ import annotations

import re
from pathlib import Path


ROUTERS_DIR = Path(__file__).resolve().parent.parent / "app" / "routers"

# 只扫描本 spec 范围内的 ledger-import 相关 router
LEDGER_IMPORT_ROUTERS = {
    "ledger_import_v2.py",
    "ledger_datasets.py",
}


def _scan_file(path: Path) -> list[dict]:
    """扫描一个 router 文件，返回 `[{method, path, access_level}, ...]`。

    策略：分两步
    1. 找所有 `@router.{method}("path"...)` 位置
    2. 对每个装饰器，向后查找下一个 `require_project_access("xxx")`，
       但不能跨过下一个 `@router.` 装饰器（否则配对会错位）
    """
    text = path.read_text(encoding="utf-8")

    deco_pattern = re.compile(
        r'@router\.(get|post|put|patch|delete)\("([^"]+)"'
    )
    require_pattern = re.compile(r'require_project_access\("(\w+)"\)')

    decorators = [
        (m.start(), m.group(1), m.group(2))
        for m in deco_pattern.finditer(text)
    ]

    results: list[dict] = []
    for idx, (pos, method, route_path) in enumerate(decorators):
        # 下一个装饰器的位置（限定搜索窗口）
        next_pos = (
            decorators[idx + 1][0] if idx + 1 < len(decorators) else len(text)
        )
        window = text[pos:next_pos]
        m = require_pattern.search(window)
        if m is None:
            # 该端点未用 require_project_access（可能用 get_current_user 或其他）
            continue
        results.append(
            {
                "method": method,
                "path": route_path,
                "access_level": m.group(1),
                "file": path.name,
            }
        )
    return results


def _collect_ledger_import_routes() -> list[dict]:
    """收集本 spec 范围内 router 文件的所有 route 信息。"""
    routes: list[dict] = []
    for pyfile in ROUTERS_DIR.rglob("*.py"):
        if pyfile.name in LEDGER_IMPORT_ROUTERS:
            routes.extend(_scan_file(pyfile))
    return routes


def test_ledger_import_jobs_get_uses_readonly() -> None:
    """F24: 所有 GET 路径含 `/jobs/` 的端点应使用 `readonly` 权限。"""
    routes = _collect_ledger_import_routes()
    get_jobs = [
        r for r in routes
        if r["method"] == "get" and "/jobs/" in r["path"]
    ]

    # 至少扫到 1 个（否则正则没匹配上，测试失去意义）
    assert len(get_jobs) >= 1, (
        "未扫描到任何 GET /jobs/* 端点，请检查 router 文件或正则表达式"
    )

    violations = [r for r in get_jobs if r["access_level"] != "readonly"]
    assert not violations, (
        f"GET /jobs/* 端点应使用 readonly 权限，以下端点违规：\n"
        + "\n".join(
            f"  - {v['file']}: {v['method'].upper()} {v['path']}"
            f" (当前 access_level={v['access_level']!r})"
            for v in violations
        )
    )


def test_ledger_import_jobs_write_uses_edit_or_higher() -> None:
    """F24: POST /jobs/* 写操作（cancel/retry/resume）应保持 edit 或更高。"""
    routes = _collect_ledger_import_routes()
    write_jobs = [
        r for r in routes
        if r["method"] in ("post", "put", "patch", "delete")
        and "/jobs/" in r["path"]
    ]

    # 允许的写权限级别（从 PERMISSION_HIERARCHY 对齐：readonly < edit < owner < admin）
    allowed_write = {"edit", "owner", "admin"}

    violations = [
        r for r in write_jobs
        if r["access_level"] not in allowed_write
    ]
    assert not violations, (
        f"POST/PUT/PATCH /jobs/* 写端点应使用 edit 及以上权限，以下端点违规：\n"
        + "\n".join(
            f"  - {v['file']}: {v['method'].upper()} {v['path']}"
            f" (当前 access_level={v['access_level']!r})"
            for v in violations
        )
    )


def test_ledger_import_routers_exist() -> None:
    """Sanity check: LEDGER_IMPORT_ROUTERS 里列的文件都要真实存在。"""
    for name in LEDGER_IMPORT_ROUTERS:
        assert (ROUTERS_DIR / name).is_file(), f"Router 文件不存在: {name}"
