#!/usr/bin/env python
"""
规模快照脚本：统计平台后端/前端模块数量，输出 JSON 或 Markdown 表。

用法：
    python backend/scripts/analyze/snapshot_scale.py          # JSON 输出
    python backend/scripts/analyze/snapshot_scale.py --markdown  # Markdown 表输出
    python backend/scripts/analyze/snapshot_scale.py --write     # （预留）写入文档

从仓库根目录运行。
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _count_py_files(directory: Path, *, exclude_init: bool = True) -> int:
    """统计目录下 .py 文件数量（不递归），可排除 __init__.py。"""
    if not directory.exists():
        return 0
    count = 0
    for f in directory.iterdir():
        if f.is_file() and f.suffix == ".py":
            if exclude_init and f.name == "__init__.py":
                continue
            count += 1
    return count


def _count_files_recursive(directory: Path, pattern: str) -> int:
    """递归统计匹配 pattern 的文件数量。"""
    if not directory.exists():
        return 0
    return len(list(directory.rglob(pattern)))


def _count_ts_files(directory: Path, *, exclude_tests: bool = True) -> int:
    """统计目录下 .ts 文件数量（不递归），可排除 __tests__ 子目录。"""
    if not directory.exists():
        return 0
    count = 0
    for f in directory.iterdir():
        if exclude_tests and f.is_dir() and f.name == "__tests__":
            continue
        if f.is_file() and f.suffix == ".ts":
            count += 1
    return count


def collect_metrics(repo_root: Path) -> dict:
    """收集所有模块计数指标。"""
    backend = repo_root / "backend"
    frontend = repo_root / "audit-platform" / "frontend" / "src"

    routers = _count_py_files(backend / "app" / "routers")
    services = _count_py_files(backend / "app" / "services")
    models = _count_py_files(backend / "app" / "models")

    # migrations: V*.sql files
    migrations_dir = backend / "migrations"
    migrations = 0
    if migrations_dir.exists():
        migrations = len([f for f in migrations_dir.iterdir()
                         if f.is_file() and f.name.startswith("V") and f.suffix == ".sql"])

    # tests: test_*.py recursively
    tests = _count_files_recursive(backend / "tests", "test_*.py")

    # frontend counts
    views = _count_files_recursive(frontend / "views", "*.vue")
    components = _count_files_recursive(frontend / "components", "*.vue")
    composables = _count_ts_files(frontend / "composables")

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "backend": {
            "routers": routers,
            "services": services,
            "models": models,
            "migrations": migrations,
            "tests": tests,
        },
        "frontend": {
            "views": views,
            "components": components,
            "composables": composables,
        },
    }


def format_markdown(metrics: dict) -> str:
    """将指标格式化为 Markdown 表格。"""
    lines = [
        f"# 平台规模快照",
        f"",
        f"> 生成时间：{metrics['timestamp']}",
        f"",
        f"## 后端",
        f"",
        f"| 模块 | 数量 |",
        f"|------|------|",
        f"| Routers | {metrics['backend']['routers']} |",
        f"| Services | {metrics['backend']['services']} |",
        f"| Models | {metrics['backend']['models']} |",
        f"| Migrations | {metrics['backend']['migrations']} |",
        f"| Tests | {metrics['backend']['tests']} |",
        f"",
        f"## 前端",
        f"",
        f"| 模块 | 数量 |",
        f"|------|------|",
        f"| Views | {metrics['frontend']['views']} |",
        f"| Components | {metrics['frontend']['components']} |",
        f"| Composables | {metrics['frontend']['composables']} |",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="平台规模快照统计")
    parser.add_argument("--markdown", action="store_true", help="输出 Markdown 表格")
    parser.add_argument("--write", action="store_true",
                        help="（预留）写入 docs/architecture/scale-snapshot.md")
    args = parser.parse_args()

    # 确定仓库根目录：脚本在 backend/scripts/analyze/ 下，根目录上溯 3 层
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent.parent

    metrics = collect_metrics(repo_root)

    if args.write:
        output_path = repo_root / "docs" / "architecture" / "scale-snapshot.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(format_markdown(metrics), encoding="utf-8")
        print(f"已写入 {output_path.relative_to(repo_root)}")
        return

    if args.markdown:
        print(format_markdown(metrics))
    else:
        print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
