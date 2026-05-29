#!/usr/bin/env python3
"""通用附注模板重建脚本 — 从md精确提取文字和表格到JSON模板

用法：
  python backend/scripts/rebuild_note_from_md.py

功能：
  1. 解析md文件的标题层级树（#/##/###）
  2. 每个章节精确分离：纯文字段落 vs 表格
  3. 表格解析为 {headers, rows} 结构
  4. 文字按段落分割为数组
  5. 写入JSON模板的 text_sections 和 tables 字段
"""
import json, re, io, sys
from pathlib import Path
from typing import Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# ═══════════════════════════════════════════
# MD 解析器
# ═══════════════════════════════════════════

def parse_md_tree(md_path: str) -> list[dict]:
    """解析md为标题树，每个节点含 title/level/text_paragraphs/tables/children"""
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    root_sections: list[dict] = []
    stack: list[dict] = []  # 当前层级栈

    current_text_lines: list[str] = []
    current_tables: list[dict] = []
    _in_table = False
    _table_lines: list[str] = []

    def _flush_content(node: Optional[dict]):
        """将累积的文字和表格写入节点"""
        nonlocal current_text_lines, current_tables, _in_table, _table_lines

        # 结束未关闭的表格
        if _in_table and _table_lines:
            tbl = _parse_table(_table_lines)
            if tbl:
                current_tables.append(tbl)
            _table_lines = []
            _in_table = False

        if node is None:
            current_text_lines = []
            current_tables = []
            return

        # 文字按双换行分段
        text = '\n'.join(current_text_lines).strip()
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()] if text else []

        node['text_paragraphs'] = paragraphs
        node['tables'] = current_tables

        current_text_lines = []
        current_tables = []

    for line in lines:
        stripped = line.strip()

        # 检测标题
        if stripped.startswith('#') and not stripped.startswith('#[['):
            level = len(stripped) - len(stripped.lstrip('#'))
            title = stripped.lstrip('#').strip()

            if level < 1 or level > 4:
                continue
            if not title:
                continue
            # 跳过使用说明等非正文标题
            if '使用说明' in title or '财务报表附注' == title:
                continue

            # 先把之前的内容写入上一个节点
            if stack:
                _flush_content(stack[-1])
            elif root_sections:
                _flush_content(root_sections[-1])
            else:
                _flush_content(None)

            node = {
                'title': title,
                'level': level,
                'text_paragraphs': [],
                'tables': [],
                'children': [],
            }

            # 找到正确的父节点
            while stack and stack[-1]['level'] >= level:
                stack.pop()

            if stack:
                stack[-1]['children'].append(node)
            else:
                root_sections.append(node)

            stack.append(node)
            continue

        # 检测表格
        if stripped.startswith('|') and '|' in stripped[1:]:
            if not _in_table:
                _in_table = True
                _table_lines = []
            _table_lines.append(stripped)
            continue
        elif _in_table:
            # 表格结束
            tbl = _parse_table(_table_lines)
            if tbl:
                current_tables.append(tbl)
            _table_lines = []
            _in_table = False

        # 普通文字行
        if stripped:
            current_text_lines.append(stripped)
        elif current_text_lines:
            current_text_lines.append('')  # 保留空行作为段落分隔

    # 最后一个节点
    if stack:
        _flush_content(stack[-1])

    return root_sections


def _parse_table(lines: list[str]) -> Optional[dict]:
    """解析md表格为 {name, headers, rows}"""
    if len(lines) < 2:
        return None

    # 第一行是表头
    header_line = lines[0]
    headers = [c.strip() for c in header_line.split('|') if c.strip()]
    if not headers:
        return None

    # 第二行是分隔线（跳过）
    data_start = 1
    if len(lines) > 1 and re.match(r'^[\|\-\s:]+$', lines[1]):
        data_start = 2

    rows = []
    for line in lines[data_start:]:
        if re.match(r'^[\|\-\s:]+$', line):
            continue
        cells = [c.strip() for c in line.split('|') if c.strip() or line.count('|') > 2]
        # 重新解析：按|分割但保留空单元格
        raw_cells = line.split('|')
        if raw_cells and not raw_cells[0].strip():
            raw_cells = raw_cells[1:]
        if raw_cells and not raw_cells[-1].strip():
            raw_cells = raw_cells[:-1]
        cells = [c.strip() for c in raw_cells]

        if not cells:
            continue

        label = cells[0] if cells else ''
        is_total = any(kw in label for kw in ['合计', '合  计', '小计', '小  计', '总计'])
        values = [None] * (len(headers) - 1)  # 数据列为空

        rows.append({
            'label': label,
            'values': values,
            'is_total': is_total,
        })

    name = headers[0] if headers else ''
    return {
        'name': name,
        'headers': headers,
        'rows': rows,
    }


# ═══════════════════════════════════════════
# JSON 模板更新
# ═══════════════════════════════════════════

def update_template(tpl_path: str, md_tree: list[dict], chapter_mapping: dict):
    """用md树更新JSON模板"""
    with open(tpl_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    sections = data['sections']

    # 建立md标题索引（扁平化）
    md_index: dict[str, dict] = {}

    def _flatten(nodes, parent_title=''):
        for node in nodes:
            title = node['title']
            # 清理标题（去掉括号提示）
            clean = title.split('（')[0].split('【')[0].strip()
            md_index[clean] = node
            md_index[title] = node
            _flatten(node.get('children', []), title)

    _flatten(md_tree)

    updated = 0
    for s in sections:
        title = s.get('section_title', '')
        account = s.get('account_name', '')

        # 在md索引中查找
        md_node = None
        for key in [title, account, title.split('（')[0].strip(), account.split('（')[0].strip()]:
            if key and key in md_index:
                md_node = md_index[key]
                break

        if not md_node:
            continue

        # 更新文字段落
        paragraphs = md_node.get('text_paragraphs', [])
        if paragraphs:
            # 过滤空段落
            clean_paragraphs = [p for p in paragraphs if p.strip()]
            if clean_paragraphs:
                existing_len = sum(len(t) for t in s.get('text_sections', []))
                new_len = sum(len(p) for p in clean_paragraphs)
                if new_len > existing_len:
                    s['text_sections'] = clean_paragraphs
                    ct = s.get('content_type', '')
                    if not ct or ct == 'table':
                        s['content_type'] = 'mixed' if s.get('tables') else 'text'

        # 更新表格（只对没有tables的章节补充）
        md_tables = md_node.get('tables', [])
        if md_tables and not s.get('tables'):
            s['tables'] = md_tables
            ct = s.get('content_type', '')
            if ct == 'text':
                s['content_type'] = 'mixed'

        updated += 1

    data['sections'] = sections
    with open(tpl_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return updated


# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════

def main():
    configs = [
        {
            'name': '国企版',
            'md': '附注模版/国企报表附注.md',
            'tpl': 'backend/data/note_template_soe.json',
        },
        {
            'name': '上市版',
            'md': '附注模版/上市报表附注.md',
            'tpl': 'backend/data/note_template_listed.json',
        },
    ]

    for cfg in configs:
        print(f"\n{'='*60}")
        print(f"  {cfg['name']}")
        print(f"{'='*60}")

        if not Path(cfg['md']).exists():
            print(f"  ⚠️ md文件不存在: {cfg['md']}")
            continue

        # 解析md
        tree = parse_md_tree(cfg['md'])
        print(f"  md解析: {len(tree)} 个一级章节")

        # 统计
        total_nodes = 0
        total_tables = 0
        total_text = 0

        def _count(nodes):
            nonlocal total_nodes, total_tables, total_text
            for n in nodes:
                total_nodes += 1
                total_tables += len(n.get('tables', []))
                total_text += len(n.get('text_paragraphs', []))
                _count(n.get('children', []))

        _count(tree)
        print(f"  总节点: {total_nodes}, 表格: {total_tables}, 文字段落: {total_text}")

        # 打印树形结构（前3级）
        def _print_tree(nodes, indent=0):
            for n in nodes[:20]:
                tables = len(n.get('tables', []))
                text = len(n.get('text_paragraphs', []))
                marker = f"[{tables}表 {text}段]" if tables or text else ""
                print(f"  {'  '*indent}{'H'+str(n['level'])} {n['title'][:35]} {marker}")
                if indent < 2:
                    _print_tree(n.get('children', [])[:10], indent + 1)

        _print_tree(tree)

        # 更新模板
        updated = update_template(cfg['tpl'], tree, {})
        print(f"\n  更新了 {updated} 个章节")

        # 验证
        d = json.load(open(cfg['tpl'], 'r', encoding='utf-8'))
        no_text = sum(1 for s in d['sections'] if not s.get('text_sections'))
        no_tables = sum(1 for s in d['sections']
                        if s.get('content_type') in ('table', 'mixed') and not s.get('tables'))
        print(f"  验证: {len(d['sections'])} 章节, {no_text} 无正文, {no_tables} 无表格(table/mixed类型)")


if __name__ == '__main__':
    main()
