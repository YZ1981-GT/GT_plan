"""生成 G/H/I/J/L/M/N/S 循环程序表 JSON 模板（对齐 D4A 折叠展开格式）。

背景：`procedure_table_templates.json` 仅覆盖 A/B/C1/D/E/F/K 循环的 *A 程序表；
G/H/I/J/L/M/N/S 循环缺失 → 底稿程序表 tab 只能靠 render 时 openpyxl 从源 xlsx 兜底
提取（有 openpyxl 冷启动开销，且非一等模板）。本脚本从各循环源 xlsx 的「*A 程序表」
sheet 抽取真实致同审计程序行，转成 D4A 同构 JSON（content 保留「（1）（2）」子步骤
供前端折叠展开），按 sheet 级编码（如 J1A/G1A）合并进模板库。

关键点：
- key = sheet 级编码（与 `_a_program.render` 的 `get_template(_sheet_code)` 一致）。
- content 由 extract_program_rows 的 program_desc + sub_steps 反向重建，保留折叠格式。
- 仅新增缺失编码，绝不覆盖已有 A/B/C/D/E/F/K 模板。
- 排除 -原版/-原/删除 等历史遗留 sheet。

用法：
  python scripts/generate_cycle_procedure_templates.py           # 预览（dry-run）
  python scripts/generate_cycle_procedure_templates.py --apply   # 写回 JSON
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 允许作为脚本直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.wp_program_extract import extract_program_rows  # noqa: E402

_BACKEND = Path(__file__).resolve().parent.parent
_TEMPLATES = _BACKEND / "data" / "procedure_table_templates.json"
_WP_TEMPLATES = _BACKEND / "wp_templates"

# S 专项底稿结构异质（会计估计 S34 有数十子表、利用专家 S12 有子表），非标准 *A
# 循环程序表模式，且未在前端 cycleProcedureSheets.ts 注册 → 需逐 sheet 人工甄别，
# 本批不纳入（避免把 S34-1..S34-40 等检查子表当程序表污染模板库）。
SCOPE_FOLDERS = ["G", "H", "I", "J", "L", "M", "N"]

# 与 _a_program.render 完全一致的 sheet 级编码提取正则
_SHEET_CODE_RE = re.compile(
    r"([A-Z]\d+(?:-\d+)?[A-Z](?:-\d+)*|[A-Z]\d+[A-Z](?:-\d+)*|[A-Z]\d+-\d+[A-Z]?)"
)
_BASE_RE = re.compile(r"^([A-Z]\d+)")

_EXCLUDE_MARKERS = ("原版", "-原", "删除", "修订前", "原底稿", "（原", "(原")


def _file_wp_code(filename: str) -> str | None:
    m = _BASE_RE.match(filename.strip())
    return m.group(1) if m else None


def _derive_sheet_code(sheet_name: str, file_wp_code: str) -> str | None:
    """镜像 _a_program.render 的 _sheet_code 推导：正则命中优先，否则回退 file wp_code。

    并要求 sheet 编码的 base（如 G1A→G1）与所属文件 wp_code 一致，
    过滤源工作簿里混入的其它科目遗留 sheet（如 J2 文件里的 L2A、Q/O 修订前底稿）。
    """
    m = _SHEET_CODE_RE.search(sheet_name or "")
    code = m.group(1) if m else file_wp_code
    base_m = _BASE_RE.match(code)
    base = base_m.group(1) if base_m else code
    if base != file_wp_code:
        return None
    return code


def _rebuild_content(row: dict) -> str:
    """由 program_desc + sub_steps 反向重建 D4A 折叠格式 content。"""
    parent = (row.get("program_desc") or "").strip()
    subs = row.get("sub_steps") or []
    if not subs:
        return parent
    lines = [parent] if parent else []
    for s in subs:
        no = s.get("no")
        text = (s.get("text") or "").strip()
        lines.append(f"（{no}）{text}")
    return "\n".join(lines)


def _clean_table_name(sheet_name: str, code: str) -> str:
    name = (sheet_name or "").strip()
    # 去掉尾部编码 + 空白
    name = re.sub(rf"\s*{re.escape(code)}\s*$", "", name).strip()
    return name or sheet_name.strip()


def build() -> dict:
    with open(_TEMPLATES, "r", encoding="utf-8") as f:
        data = json.load(f)
    tables: dict = data.setdefault("tables", {})
    existing = set(tables.keys())

    added: dict[str, int] = {}
    skipped_existing: list[str] = []

    import openpyxl

    for folder in SCOPE_FOLDERS:
        fdir = _WP_TEMPLATES / folder
        if not fdir.is_dir():
            continue
        for xlsx in sorted(fdir.glob("*.xlsx")):
            try:
                wb = openpyxl.load_workbook(str(xlsx), read_only=True, data_only=True)
                sheet_names = list(wb.sheetnames)
                wb.close()
            except Exception as e:  # noqa: BLE001
                print(f"  ! 打开失败 {xlsx.name}: {e}")
                continue

            file_code = _file_wp_code(xlsx.name)
            if not file_code:
                continue
            for sn in sheet_names:
                if any(mk in sn for mk in _EXCLUDE_MARKERS):
                    continue
                if "程序" not in sn:  # 只处理程序表 sheet
                    continue
                code = _derive_sheet_code(sn, file_code)
                if not code:
                    continue
                if code in existing or code in added:
                    if code in existing:
                        skipped_existing.append(code)
                    continue
                rows = extract_program_rows(str(xlsx), sn)
                if not rows:
                    continue
                items = []
                for r in rows:
                    content = _rebuild_content(r)
                    if not content.strip():
                        continue
                    items.append({
                        "seq": r.get("program_no"),
                        "content": content,
                        "ref_index": (r.get("linked_workpapers") or "").strip(),
                        "auto_data_source": None,
                        "applicable_default": "yes",
                    })
                if not items:
                    continue
                tables[code] = {"name": _clean_table_name(sn, code), "items": items}
                added[code] = len(items)
                print(f"  + {code:10s} ({len(items):2d} steps)  <- {xlsx.name} :: {sn}")

    print(f"\n新增 {len(added)} 个程序表模板: {sorted(added.keys())}")
    if skipped_existing:
        print(f"已存在跳过: {sorted(set(skipped_existing))}")
    return data


def main() -> None:
    apply = "--apply" in sys.argv
    data = build()
    if apply:
        backup = _TEMPLATES.with_suffix(".json.bak")
        if not backup.exists():
            backup.write_text(_TEMPLATES.read_text(encoding="utf-8"), encoding="utf-8")
        with open(_TEMPLATES, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n[APPLIED] 已写回 {_TEMPLATES}（备份 {backup.name}）")
    else:
        print("\n[DRY-RUN] 未写回。加 --apply 生效。")


if __name__ == "__main__":
    main()
