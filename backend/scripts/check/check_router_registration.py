"""路由注册完整性检查（pre-commit hook）。

扫描 backend/app/routers/*.py 中定义了 APIRouter 的文件，
验证每个 router 文件都在 backend/app/router_registry/ 中被 import。
未注册的 router 会导致端点 404，属于高频遗漏 bug。

策略：
- 扫描 routers/ 目录下所有 .py 文件，检测含 `router = APIRouter` 或 `APIRouter(`
- 扫描 router_registry/ 目录下所有 .py 文件，收集 `from app.routers.XXX import` 语句
- 对比：router 文件未被任何 registry 文件引用 → 违规
- 已知例外：__init__.py（包初始化，不含路由）

用法：
    python backend/scripts/check/check_router_registration.py [--init]

    --init  仅打印当前状态，不以非零退出码失败
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTERS_DIR = ROOT / "backend" / "app" / "routers"
REGISTRY_DIR = ROOT / "backend" / "app" / "router_registry"

# 匹配 router 定义
ROUTER_DEF_RE = re.compile(r"(?:router\s*=\s*APIRouter|APIRouter\s*\()")

# 匹配 registry 中的 import 语句：from app.routers.XXX import ...
REGISTRY_IMPORT_RE = re.compile(r"from\s+app\.routers\.(\w+)\s+import")

# 已知例外（不需要注册的文件）
EXCEPTIONS = {
    "__init__.py",
}


def find_router_files() -> list[Path]:
    """找到所有定义了 APIRouter 的 router 文件。"""
    if not ROUTERS_DIR.exists():
        return []

    results: list[Path] = []
    for f in sorted(ROUTERS_DIR.iterdir()):
        if not f.is_file() or f.suffix != ".py":
            continue
        if f.name in EXCEPTIONS:
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        if ROUTER_DEF_RE.search(content):
            results.append(f)

    return results


def find_registered_modules() -> set[str]:
    """从 router_registry/ 收集所有被 import 的 router 模块名。"""
    if not REGISTRY_DIR.exists():
        return set()

    registered: set[str] = set()
    for f in sorted(REGISTRY_DIR.iterdir()):
        if not f.is_file() or f.suffix != ".py":
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for match in REGISTRY_IMPORT_RE.finditer(content):
            registered.add(match.group(1))

    return registered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="路由注册完整性检查")
    parser.add_argument("--init", action="store_true",
                        help="仅打印当前状态，不以非零退出码失败")
    args = parser.parse_args(argv)

    router_files = find_router_files()
    if not router_files:
        print("未找到 router 文件", file=sys.stderr)
        return 0

    registered = find_registered_modules()

    # 对比：router 文件的模块名（去 .py 后缀）是否在 registered 中
    violations: list[str] = []
    for f in router_files:
        module_name = f.stem  # e.g. "wp_template"
        if module_name not in registered:
            rel_path = str(f.relative_to(ROOT)).replace("\\", "/")
            violations.append(rel_path)

    if args.init:
        print(f"扫描 {len(router_files)} 个 router 文件，已注册 {len(registered)} 个模块")
        print(f"未注册: {len(violations)} 个")
        if violations:
            print("\n未注册的 router 文件：")
            for v in violations:
                print(f"  {v}")
        else:
            print("\n✅ 所有 router 均已注册")
        return 0

    if violations:
        print(f"❌ 发现 {len(violations)} 个未注册的 router（端点将 404）：", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print("\n请在 backend/app/router_registry/ 对应文件中添加 import 并注册。", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
