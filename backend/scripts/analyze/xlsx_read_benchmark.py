"""xlsx 读路径性能微基准：calamine vs openpyxl

用法:
    python scripts/analyze/xlsx_read_benchmark.py [模板目录]

默认扫描 backend/wp_templates/ 下的 xlsx 文件，对比 read_sheet_values 在
calamine 与 openpyxl 两种后端下的读取耗时。

输出示例:
    File: D1.xlsx (3 sheets)
      calamine:  0.012s (avg of 5 runs)
      openpyxl:  0.048s (avg of 5 runs)
      speedup:   4.0x

Spec: xlsx-read-acceleration
Requirements: 5.1, 5.2
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# 确保 backend 在 path 上
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _time_read(path: Path, sheet_name: str | None, prefer_calamine: bool, n: int = 5) -> float:
    """返回 n 次 read_sheet_values 调用的平均耗时（秒）。"""
    from app.services.xlsx_read_adapter import read_sheet_values

    # warmup
    read_sheet_values(path, sheet_name, prefer_calamine=prefer_calamine)

    elapsed_list = []
    for _ in range(n):
        t0 = time.perf_counter()
        read_sheet_values(path, sheet_name, prefer_calamine=prefer_calamine)
        elapsed_list.append(time.perf_counter() - t0)

    return sum(elapsed_list) / len(elapsed_list)


def benchmark_file(path: Path, n_runs: int = 5) -> dict | None:
    """对单个 xlsx 文件跑 calamine vs openpyxl 基准。"""
    from app.services.xlsx_read_adapter import list_sheet_names

    try:
        sheets = list_sheet_names(path)
    except Exception as e:
        print(f"  SKIP (无法读取): {e}")
        return None

    if not sheets:
        return None

    # 取第一个 sheet 做基准
    sheet = sheets[0]

    try:
        cal_time = _time_read(path, sheet, prefer_calamine=True, n=n_runs)
    except Exception as e:
        print(f"  calamine 失败: {e}")
        cal_time = None

    try:
        opy_time = _time_read(path, sheet, prefer_calamine=False, n=n_runs)
    except Exception:
        opy_time = None

    return {
        "file": path.name,
        "sheets": len(sheets),
        "sheet_tested": sheet,
        "calamine_avg_s": cal_time,
        "openpyxl_avg_s": opy_time,
    }


def main():
    template_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND_DIR / "wp_templates"

    if not template_dir.exists():
        print(f"模板目录不存在: {template_dir}")
        sys.exit(1)

    xlsx_files = sorted(template_dir.rglob("*.xlsx"))
    if not xlsx_files:
        print(f"未找到 xlsx 文件: {template_dir}")
        sys.exit(1)

    # 检查 calamine 可用性
    try:
        import python_calamine  # noqa: F401
        calamine_ok = True
    except ImportError:
        calamine_ok = False
        print("⚠️  python_calamine 未安装，仅测 openpyxl 路径\n")

    print(f"═══ xlsx 读路径性能基准 ═══")
    print(f"模板目录: {template_dir}")
    print(f"文件数: {len(xlsx_files)}")
    print(f"calamine 可用: {'是' if calamine_ok else '否'}")
    print(f"每文件运行次数: 5")
    print()

    results = []
    for fp in xlsx_files[:20]:  # 最多测 20 个文件
        print(f"File: {fp.relative_to(template_dir)} ", end="")
        r = benchmark_file(fp)
        if r is None:
            print("(跳过)")
            continue

        cal = r["calamine_avg_s"]
        opy = r["openpyxl_avg_s"]
        print(f"({r['sheets']} sheets)")

        if cal is not None:
            print(f"  calamine: {cal:.4f}s")
        if opy is not None:
            print(f"  openpyxl: {opy:.4f}s")
        if cal and opy and cal > 0:
            speedup = opy / cal
            print(f"  加速比:   {speedup:.1f}x")
            r["speedup"] = speedup
        print()
        results.append(r)

    # 汇总
    if results:
        speedups = [r["speedup"] for r in results if r.get("speedup")]
        if speedups:
            avg_speedup = sum(speedups) / len(speedups)
            print(f"═══ 汇总 ═══")
            print(f"有效测试文件: {len(speedups)}")
            print(f"平均加速比: {avg_speedup:.1f}x")
            print(f"最大加速比: {max(speedups):.1f}x")
            print(f"最小加速比: {min(speedups):.1f}x")


if __name__ == "__main__":
    main()
