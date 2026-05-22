"""测试覆盖率报告生成

使用方式：python scripts/run_coverage.py
输出：htmlcov/index.html

依赖：pip install pytest-cov（已在 requirements.txt）

选项：
  --html    生成 HTML 报告（默认）
  --term    仅终端输出
  --xml     生成 XML 报告（CI 用）
"""
import subprocess
import sys
from pathlib import Path


def main():
    backend_dir = Path(__file__).resolve().parent.parent

    # 解析参数
    args = sys.argv[1:]
    report_formats = []

    if "--xml" in args:
        report_formats.append("--cov-report=xml")
    if "--term" in args or not args:
        report_formats.append("--cov-report=term-missing")
    if "--html" in args or not args:
        report_formats.append("--cov-report=html")

    print("=" * 60)
    print("  后端测试覆盖率报告")
    print("=" * 60)
    print()

    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=app",
        "--cov-config=.coveragerc",
        "-q", "--tb=short",
        *report_formats,
    ]

    print(f"执行: {' '.join(cmd)}")
    print(f"工作目录: {backend_dir}")
    print()

    result = subprocess.run(cmd, cwd=str(backend_dir))

    htmlcov = backend_dir / "htmlcov" / "index.html"
    if htmlcov.exists():
        print(f"\n覆盖率 HTML 报告: {htmlcov}")

    xmlcov = backend_dir / "coverage.xml"
    if xmlcov.exists():
        print(f"覆盖率 XML 报告: {xmlcov}")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
