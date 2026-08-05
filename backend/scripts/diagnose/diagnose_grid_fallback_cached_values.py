"""diagnose_grid_fallback_cached_values.py — 只读诊断：grid 兜底示例值污染面盘查

扫描 workpaper_sheet_classification × backend/wp_templates/，统计有多少 sheet 会走
extract_grid 兜底且其模板对应 sheet 的数据区含公式缓存值。

用法：
    python backend/scripts/diagnose/diagnose_grid_fallback_cached_values.py --out results.txt

输出：wp_code / sheet_name / 命中缓存值格数 清单（供独立 spec 决策）。

🔴 只读 + 只报告不改。不触碰数据库、不修改任何文件。
🔴 禁止用 PS 重定向（> file）存输出，用 --out 自己写盘。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ─── 加载平台常量（不 import app 模块避免依赖链）─────────────────────────────

_BACKEND = Path(__file__).resolve().parents[2]
_WP_TEMPLATES = _BACKEND / "wp_templates"
_OVERRIDES_PATH = _BACKEND / "app" / "data" / "wp_code_overrides.json"

# 仅 d-form-table 在白名单且不在 RENDERER_DISPATCH 时走 grid 兜底
# 这里不 import 后端模块，硬编码已知的白名单 componentType 列表
_GRID_FALLBACK_TYPES = {"d-form-table"}


def _load_overrides() -> dict[str, str]:
    if _OVERRIDES_PATH.exists():
        return json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {}


def _find_template(wp_code: str) -> Path | None:
    """按 wp_code 首字母定位 wp_templates/{letter}/{wp_code}*.xlsx"""
    prefix = wp_code[0].upper()
    tpl_dir = _WP_TEMPLATES / prefix
    if not tpl_dir.exists():
        return None
    for f in tpl_dir.iterdir():
        if f.suffix == ".xlsx" and not f.name.startswith("~$"):
            # 文件名含 wp_code
            if wp_code in f.name:
                return f
    return None


def _count_cached_formulas(ws) -> int:
    """数据区（行 5+ 排除表头）里含公式缓存值的单元格数。
    openpyxl data_only=True 时，有值但在 data_only=False 时是公式 → 就是缓存值。
    这里简单看 data_only=False 下是公式（以 = 开头），说明 data_only=True 会读到缓存。"""
    count = 0
    for row in ws.iter_rows(min_row=5, max_row=ws.max_row):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Grid 兜底示例值污染面盘查")
    parser.add_argument("--out", type=str, help="输出文件路径（UTF-8）")
    parser.add_argument("--limit", type=int, default=0, help="限制扫描模板数（0=全部）")
    args = parser.parse_args()

    overrides = _load_overrides()
    results: list[tuple[str, str, int]] = []

    # 找所有可能走 grid 兜底的 (sheet_name, componentType) 对
    # 从 overrides 里找 componentType in _GRID_FALLBACK_TYPES 的条目
    grid_sheets: list[tuple[str, str]] = []  # (override_key, componentType)
    for key, ct in overrides.items():
        if ct in _GRID_FALLBACK_TYPES:
            grid_sheets.append((key, ct))

    print(f"[诊断] 共 {len(grid_sheets)} 个 override 条目走 grid 兜底")

    # 按 wp_code 聚合去重
    scanned_templates: set[str] = set()
    scanned_count = 0

    try:
        import openpyxl
    except ImportError:
        print("ERROR: 需要 openpyxl", file=sys.stderr)
        sys.exit(1)

    for key, ct in grid_sheets:
        # 从 key 推 wp_code（尾码或全名里找）
        # 简单取前2~4字符作 wp_code 前缀用于找模板
        # 实际 key 可能是全名如 "货币资金发函记录表E0-3" 或短键如 "E0-3"
        # 先尝试全名→wp_code，再尝试短键
        parts = key.split("-")
        if len(parts) >= 2 and len(parts[0]) <= 3:
            wp_code = parts[0]  # E0, D0 等
        else:
            # 全名，尝试从尾部提取
            import re
            m = re.search(r"([A-Z]\d+(?:-\d+)?[A-Z]?)$", key)
            wp_code = m.group(1).split("-")[0] if m else key[:2]

        tpl = _find_template(wp_code)
        if tpl is None or str(tpl) in scanned_templates:
            continue

        if args.limit and scanned_count >= args.limit:
            break

        scanned_templates.add(str(tpl))
        scanned_count += 1

        try:
            wb = openpyxl.load_workbook(str(tpl), data_only=False)
            for sn in wb.sheetnames:
                ws = wb[sn]
                cached = _count_cached_formulas(ws)
                if cached > 0:
                    results.append((wp_code, sn, cached))
            wb.close()
        except Exception as e:
            print(f"  WARN: {tpl.name} 打开失败: {e}")

    # 输出
    lines = [
        f"# Grid 兜底示例值污染面盘查",
        f"# 扫描模板数: {scanned_count}",
        f"# 含缓存值的 sheet 数: {len(results)}",
        f"# 格式: wp_code | sheet_name | 命中缓存值格数",
        "",
    ]
    for wp_code, sn, count in sorted(results, key=lambda x: -x[2]):
        lines.append(f"{wp_code:6s} | {sn:50s} | {count}")

    output = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"[诊断] 结果已写入 {args.out}（{len(results)} 条）")
    else:
        print(output)


if __name__ == "__main__":
    main()
