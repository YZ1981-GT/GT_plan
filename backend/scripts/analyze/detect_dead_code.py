"""死代码检测脚本

Python: 使用 vulture 扫描未使用的代码
TypeScript: 使用 ts-prune 扫描未使用的导出

使用方式：python scripts/detect_dead_code.py
"""
import subprocess
import sys
from pathlib import Path


def run_vulture():
    """Python 死代码检测"""
    print("=" * 60)
    print("  Python 死代码检测 (vulture)")
    print("=" * 60)

    backend_dir = Path(__file__).resolve().parent.parent
    app_dir = backend_dir / "app"

    if not app_dir.exists():
        print(f"错误: {app_dir} 不存在")
        return

    try:
        result = subprocess.run(
            [sys.executable, "-m", "vulture", "app/",
             "--min-confidence", "80",
             "--exclude", "tests/,alembic/,scripts/"],
            capture_output=True, text=True, cwd=str(backend_dir)
        )
        if result.returncode == 0 and not result.stdout.strip():
            print("✓ 无死代码检测到（confidence ≥ 80%）")
        elif result.stdout:
            lines = result.stdout.strip().split("\n")
            print(f"发现 {len(lines)} 处可能的死代码：\n")
            # 限制输出前 50 行
            for line in lines[:50]:
                print(f"  {line}")
            if len(lines) > 50:
                print(f"\n  ... 还有 {len(lines) - 50} 处（完整输出请直接运行 vulture）")
        if result.stderr:
            print(f"\n警告: {result.stderr[:500]}")
    except FileNotFoundError:
        print("vulture 未安装，请运行: pip install vulture")


def run_ts_prune():
    """TypeScript 未使用导出检测"""
    print("\n" + "=" * 60)
    print("  TypeScript 未使用导出检测 (ts-prune)")
    print("=" * 60)

    frontend_dir = Path(__file__).resolve().parent.parent.parent / "audit-platform" / "frontend"

    if not frontend_dir.exists():
        print(f"错误: {frontend_dir} 不存在")
        return

    try:
        result = subprocess.run(
            ["npx", "ts-prune", "--error"],
            capture_output=True, text=True, cwd=str(frontend_dir),
            shell=True  # Windows 需要 shell=True for npx
        )
        if result.returncode == 0 and not result.stdout.strip():
            print("✓ 无未使用的导出")
        elif result.stdout:
            lines = result.stdout.strip().split("\n")
            # 过滤掉 index.ts 的 re-export（通常是有意的）
            meaningful = [l for l in lines if "index.ts" not in l]
            print(f"发现 {len(meaningful)} 处未使用的导出：\n")
            for line in meaningful[:30]:
                print(f"  {line}")
            if len(meaningful) > 30:
                print(f"\n  ... 还有 {len(meaningful) - 30} 处")
        if result.stderr and "ERR" in result.stderr:
            print(f"\n提示: ts-prune 可能未安装，运行: npm install -g ts-prune")
    except FileNotFoundError:
        print("npx 未找到，请确保 Node.js 已安装")


def main():
    print("死代码检测工具")
    print("=" * 60)
    print()

    run_vulture()
    run_ts_prune()

    print("\n" + "=" * 60)
    print("检测完成。建议：")
    print("  - confidence ≥ 90% 的项可直接删除")
    print("  - confidence 80-90% 的项需人工确认")
    print("  - 定期运行此脚本保持代码库整洁")
    print("=" * 60)


if __name__ == "__main__":
    main()
