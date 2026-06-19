"""按循环拆分 procedure_table_templates.json。

将巨型单文件拆为按循环的子文件：
  procedure_table_templates.json (保留 version/description/tables 老格式)
  procedure_table_templates_G.json
  procedure_table_templates_H.json
  ...

运行：python scripts/ops/split_procedure_templates.py
"""
from __future__ import annotations

import json
from pathlib import Path

SRC = Path("backend/data/procedure_table_templates.json")
OUT_DIR = SRC.parent


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))

    # 分离元数据 vs 各循环程序表
    meta = {}
    cycles: dict[str, dict] = {}

    for key, value in data.items():
        if key in ("version", "description", "tables"):
            meta[key] = value
        else:
            # 按首字母分组 (G0A→G, K13A→K, M10A→M, S1→S)
            cycle = key[0]
            cycles.setdefault(cycle, {})[key] = value

    # 写各循环子文件
    for cycle, templates in sorted(cycles.items()):
        out_path = OUT_DIR / f"procedure_table_templates_{cycle}.json"
        out_data = {
            "description": f"{cycle} 循环程序表模板（拆分自 procedure_table_templates.json）",
            "cycle": cycle,
            "count": len(templates),
            **templates,
        }
        out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ {out_path.name}: {len(templates)} 个程序表")

    # 主文件保留 meta + 引用说明
    meta["_split_note"] = "各循环程序表已拆分为 procedure_table_templates_{CYCLE}.json，运行时由 loader 合并"
    meta["_cycle_files"] = [f"procedure_table_templates_{c}.json" for c in sorted(cycles)]

    # 暂不删除主文件中的程序表（保持向后兼容），仅添加 _split_note
    # 如果要真正拆分，取消下面注释：
    # SRC.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✓ 拆分完成：{len(cycles)} 个循环，共 {sum(len(v) for v in cycles.values())} 个程序表")
    print("  注：主文件未修改（向后兼容），子文件已生成供将来切换")


if __name__ == "__main__":
    main()
