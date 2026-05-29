"""
解析附注模板 md 文件，提取 '财务报表主要项目注释' 下的所有表格，
每个表格作为独立节点（用表格上方最近的标题作为名称），生成 JSON 种子数据。

用法: python -m scripts.seed_consol_note_sections [--standard soe|listed] [--dry-run]
"""
import argparse
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def merge_multi_headers(header_rows: list[list[str]]) -> list[str]:
    """将多行表头合并为单行，用 '/' 连接非空的层级标题。
    
    例如：
      Row 0: ['类别', '期末数', '', '', '', '', '期初数', '', '', '', '']
      Row 1: ['', '账面余额', '', '坏账准备', '', '账面价值', '账面余额', '', '坏账准备', '', '账面价值']
      Row 2: ['', '金额', '比例(%)', '金额', '预期信用损失率(%)', '', '金额', '比例(%)', '金额', '预期信用损失率(%)', '']
    
    合并后: ['类别', '期末数/账面余额/金额', '期末数/账面余额/比例(%)', ...]
    """
    if not header_rows:
        return []
    
    col_count = max(len(r) for r in header_rows)
    # 补齐每行到相同列数
    for r in header_rows:
        while len(r) < col_count:
            r.append("")
    
    # 对每列，从上到下收集非空标题，用 forward-fill 处理合并单元格
    filled: list[list[str]] = []
    for row in header_rows:
        filled_row = []
        last_val = ""
        for cell in row:
            if cell:
                last_val = cell
                filled_row.append(cell)
            else:
                filled_row.append(last_val)
        filled.append(filled_row)
    
    # 合并：每列取各行的值，去重后用 '/' 连接
    merged = []
    for ci in range(col_count):
        parts = []
        seen = set()
        for ri in range(len(filled)):
            val = filled[ri][ci]
            if val and val not in seen:
                parts.append(val)
                seen.add(val)
        merged.append("/".join(parts) if parts else f"列{ci + 1}")
    
    return merged


def parse_note_template(md_path: Path) -> list[dict]:
    """解析 md 文件，每个表格作为独立节点"""
    content = md_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    # 找到主要项目注释起始行
    start_idx = None
    for i, line in enumerate(lines):
        if line.startswith("#") and (
            "财务报表主要项目注释" in line
            or "合并财务报表项目附注" in line
            or "财务报表项目附注" in line
        ):
            start_idx = i + 1
            break

    if start_idx is None:
        print(f"未找到主要项目注释章节: {md_path}")
        return []

    # 找到结束位置
    end_idx = len(lines)
    for i in range(start_idx, len(lines)):
        line = lines[i]
        if line.startswith("# ") and not line.startswith("## "):
            end_idx = i
            break

    # 逐行扫描，收集每个表格及其上方最近的标题
    tables: list[dict] = []
    current_h2 = ""       # 当前 ## 标题（父章节）
    current_h3 = ""       # 当前 ### 标题（子章节）
    current_h4 = ""       # 当前 #### 标题
    last_heading = ""     # 最近的任意级别标题
    current_table_headers: list[str] | None = None
    current_table_rows: list[list[str]] = []
    current_table_raw_header_rows: list[list[str]] = []  # 多行表头原始行
    in_header_phase = False  # 是否还在表头阶段（连续的空首列行）
    h2_seq = 0

    def flush_table():
        nonlocal current_table_headers, current_table_rows, current_table_raw_header_rows, in_header_phase
        if current_table_headers:
            # 处理多行表头：合并为单行
            if len(current_table_raw_header_rows) > 1:
                merged = merge_multi_headers(current_table_raw_header_rows)
                current_table_headers = merged

            table_name = last_heading or current_h3 or current_h2 or "未命名"
            parent = current_h2
            tables.append({
                "parent_section": parent,
                "parent_seq": h2_seq,
                "title": table_name,
                "headers": current_table_headers,
                "rows": current_table_rows,
                "multi_header": current_table_raw_header_rows if len(current_table_raw_header_rows) > 1 else None,
            })
        current_table_headers = None
        current_table_rows = []
        current_table_raw_header_rows = []
        in_header_phase = False

    for i in range(start_idx, end_idx):
        line = lines[i]

        if line.startswith("## "):
            flush_table()
            h2_seq += 1
            current_h2 = line[3:].strip()
            current_h3 = ""
            current_h4 = ""
            last_heading = current_h2

        elif line.startswith("### "):
            flush_table()
            current_h3 = line[4:].strip()
            current_h4 = ""
            last_heading = current_h3

        elif line.startswith("#### "):
            flush_table()
            title = line[5:].strip()
            if title != "使用说明：":
                current_h4 = title
                last_heading = current_h4

        elif line.strip().startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if not cells:
                continue
            if current_table_headers is None:
                # 第一行表头
                current_table_headers = cells
                current_table_raw_header_rows = [cells]
                in_header_phase = True
            elif in_header_phase and cells[0] == "" and any(c != "" for c in cells[1:]):
                # 后续表头行：首列为空但其他列有内容 = 子表头行
                current_table_raw_header_rows.append(cells)
            else:
                in_header_phase = False
                current_table_rows.append(cells)

        elif line.strip().startswith("|") and "---" in line:
            pass  # 分隔行，不改变 in_header_phase（子表头可能在分隔行之后）

        elif line.strip() == "" and current_table_headers is not None:
            # 空行结束当前表格
            flush_table()

    flush_table()  # 最后一个表格

    return tables


def build_tree_json(tables: list[dict], standard: str) -> list[dict]:
    """构建树形 JSON：按父章节分组，每个表格一个节点"""
    # 按父章节分组
    groups: dict[str, list[dict]] = {}
    for t in tables:
        parent = t["parent_section"]
        if parent not in groups:
            groups[parent] = []
        groups[parent].append(t)

    result = []
    global_seq = 0
    for parent_name, group_tables in groups.items():
        parent_seq = group_tables[0]["parent_seq"]
        for ti, t in enumerate(group_tables):
            global_seq += 1
            section_id = f"五-{parent_seq}-{ti + 1}"
            result.append({
                "id": str(uuid.uuid4()),
                "standard": standard,
                "section_id": section_id,
                "parent_section": parent_name,
                "parent_seq": parent_seq,
                "title": t["title"],
                "seq": global_seq,
                "headers": t["headers"],
                "rows": t["rows"],
                "multi_header": t.get("multi_header"),
            })

    return result


def main():
    parser = argparse.ArgumentParser(description="解析附注模板并生成种子数据")
    parser.add_argument("--standard", choices=["soe", "listed", "both"], default="both")
    parser.add_argument("--dry-run", action="store_true", help="只生成 JSON 不入库")
    args = parser.parse_args()

    standards = ["soe", "listed"] if args.standard == "both" else [args.standard]
    md_files = {
        "soe": ROOT / "附注模版" / "国企报表附注.md",
        "listed": ROOT / "附注模版" / "上市报表附注.md",
    }

    for std in standards:
        md_path = md_files[std]
        if not md_path.exists():
            print(f"文件不存在: {md_path}")
            continue

        print(f"\n解析 {std} 模板: {md_path.name}")
        tables = parse_note_template(md_path)
        print(f"  提取到 {len(tables)} 个表格")

        seed_data = build_tree_json(tables, std)

        # 统计父章节数
        parents = set(t["parent_section"] for t in seed_data)
        print(f"  {len(parents)} 个父章节，{len(seed_data)} 个表格节点")

        out_path = ROOT / "backend" / "data" / f"consol_note_sections_{std}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(seed_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  已导出到 {out_path}")


if __name__ == "__main__":
    main()
