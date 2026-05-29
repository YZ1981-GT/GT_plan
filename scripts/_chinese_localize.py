"""全平台中文化批量扫描 + 术语表替换 + dry-run diff。

工作流:
  1. python scripts/_chinese_localize.py --scan       # 输出未中文化的英文 UI 文本
  2. python scripts/_chinese_localize.py --dry-run    # 预览替换 diff（不修改文件）
  3. python scripts/_chinese_localize.py --apply      # 实际替换（谨慎使用）

扫描范围:
  - audit-platform/frontend/src/**/*.vue

检测位置:
  - label="..." (el-table-column / el-form-item / el-tab-pane)
  - title="..." (el-dialog / el-drawer / el-tooltip)
  - placeholder="..."
  - <el-button>...</el-button> 内文本

豁免条件:
  - 值含中文字符（混合中英视为已中文化）
  - 值为动态绑定（:label / v-bind:label）
  - 值在技术术语白名单中
  - 值为纯数字/符号
  - 行末含 // allow-en-text 注释

用完即删（_ 前缀一次性脚本）。
"""

import re
import sys
import pathlib
import argparse
from collections import defaultdict, Counter

# ─── 术语表（英文→中文映射）───────────────────────────────────────────
GLOSSARY = {
    # 审计核心术语
    "Source": "来源",
    "Target": "目标",
    "Severity": "严重程度",
    "Status": "状态",
    "Type": "类型",
    "Name": "名称",
    "Description": "描述",
    "Action": "操作",
    "Date": "日期",
    "Amount": "金额",
    "Total": "合计",
    "Blocking": "阻断",
    "Warning": "警告",
    "Info": "提示",
    "Token": "令牌",
    "ADJUSTING": "调整事项",
    "NON-ADJUSTING": "非调整事项",
    "English": "英文",
    "Save": "保存",
    "Submit": "提交",
    "Cancel": "取消",
    "Edit": "编辑",
    "Delete": "删除",
    "Export": "导出",
    "Import": "导入",
    "Filter": "筛选",
    "Search": "搜索",
    "Sort": "排序",
    "Add": "新增",
    "Create": "创建",
    "Confirm": "确认",
    "Reject": "拒绝",
    "Close": "关闭",
    "Reset": "重置",
    "Refresh": "刷新",
    "Download": "下载",
    "Upload": "上传",
    "Copy": "复制",
    "Remove": "移除",
    "Back": "返回",
    "Next": "下一步",
    "Previous": "上一步",
    "Apply": "应用",
    "Clear": "清空",
    "Update": "更新",
    "View": "查看",
    "Preview": "预览",
    "Generate": "生成",
    "Batch": "批量",
    "Select": "选择",
    "Workpaper": "底稿",
    "Adjustment": "调整分录",
    "Misstatement": "错报",
    "Trial Balance": "试算平衡表",
    "Disclosure": "附注披露",
    "Report": "报表",
    "Ledger": "序时账",
    "Account": "科目",
    "Voucher": "凭证",
    "Confirmation": "函证",
    "Materiality": "重要性",
    "Risk Assessment": "风险评估",
    "Sign Off": "签字",
    "Review": "复核",
    "Archive": "归档",
    "Sampling": "抽样",
    "Penetration": "穿透",
    "Reconciliation": "调节",
    "Variance": "差异",
    "Quality Control": "质量控制",
    "Consolidation": "合并",
    "Impairment": "减值",
    "Depreciation": "折旧",
    "Amortization": "摊销",
    "Revenue": "收入",
    "Expense": "费用",
    "Inventory": "存货",
}

# ─── 技术术语白名单（保留英文）───────────────────────────────────────
TECH_WHITELIST = {
    # 编程/技术
    'SQL', 'PDF', 'OCR', 'LLM', 'AI', 'API', 'URL', 'UUID', 'CSV', 'JSON', 'YAML',
    'HTTP', 'HTTPS', 'UTF', 'RFC', 'ISO', 'XML', 'HTML', 'CSS', 'JWT', 'OAuth',
    'RBAC', 'RLS', 'ORM', 'CRUD', 'REST', 'GraphQL', 'WebSocket', 'SSE',
    'Docker', 'Redis', 'PostgreSQL', 'FastAPI', 'Vue', 'Pinia', 'TypeScript',
    'ESLint', 'Playwright', 'vitest', 'Decimal', 'PyYAML',
    # AI/模型
    'Qwen', 'GPT', 'Claude', 'DeepSeek', 'Ollama', 'vLLM', 'PaddleOCR', 'OpenAI',
    # 审计标准
    'CAS', 'PCAOB', 'WCAG', 'EQCR', 'PBC', 'AJE', 'RJE',
    # 公式/函数
    'TB', 'ROW', 'NOTE', 'WP', 'REPORT', 'AUX', 'PREV', 'IF', 'ABS', 'ROUND',
    'MAX', 'MIN', 'SUM', 'AVG', 'COUNT', 'DISTINCT',
    # 格式
    'OL', 'UL', 'AND', 'OR', 'INNER', 'LEFT', 'RIGHT', 'ID',
    'Excel', 'Word', 'Ref', 'SAP', 'Sheet',
    # 日志级别
    'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL',
    # 数据格式
    'ACT', 'SHA', 'SHA-256', 'Token',
    # 其他
    'LLM Stub', 'API Key', 'YYYY-MM-DD',
}

# ─── 正则 ─────────────────────────────────────────────────────────────
HAS_CHINESE = re.compile(r'[\u4e00-\u9fff]')
ENGLISH_ONLY = re.compile(r'^[A-Za-z][A-Za-z0-9 \-_./\\]*$')


def is_whitelisted(value: str) -> bool:
    """Check if value is in technical whitelist."""
    if value in TECH_WHITELIST:
        return True
    words = value.split()
    return all(
        w in TECH_WHITELIST or w.upper() in TECH_WHITELIST or re.match(r'^[0-9.]+$', w)
        for w in words
    )


def scan_file(filepath: pathlib.Path, src_root: pathlib.Path):
    """Scan a single .vue file for English UI text."""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return []

    hits = []
    lines = content.split('\n')

    # Pattern: static label/title/placeholder attributes (not dynamic :label)
    for m in re.finditer(r'(?<!:)(?:label|title|placeholder)="([^"]+)"', content):
        # Verify not preceded by : (dynamic binding)
        start = m.start()
        if start > 0 and content[start - 1] == ':':
            continue

        val = m.group(1)

        # Skip if contains Chinese
        if HAS_CHINESE.search(val):
            continue

        # Skip if not English-like
        if not ENGLISH_ONLY.match(val):
            continue

        # Skip very short values (likely variable names)
        if len(val) <= 2:
            continue

        # Skip camelCase / dot notation (dynamic variable references)
        if '.' in val or (val[0].islower() and any(c.isupper() for c in val[1:])):
            continue

        # Skip whitelisted terms
        if is_whitelisted(val):
            continue

        # Get line number and check for allow-en-text comment
        line_num = content[:start].count('\n') + 1
        line_content = lines[line_num - 1] if line_num <= len(lines) else ''
        if 'allow-en-text' in line_content:
            continue

        # Check if it's actually a dynamic binding on the line
        if re.search(r'(?::|v-bind:)(?:label|title|placeholder)\s*=\s*"' + re.escape(val) + '"', line_content):
            continue

        # Skip el-radio / el-radio-button / el-option label values (programmatic values)
        if re.search(r'<el-(?:radio|radio-button|option)\b[^>]*\blabel="' + re.escape(val) + '"', line_content):
            continue

        attr_type = m.group(0).split('=')[0]
        rel_path = str(filepath.relative_to(src_root))
        suggestion = GLOSSARY.get(val, '???')
        hits.append({
            'file': rel_path,
            'line': line_num,
            'attr': attr_type,
            'value': val,
            'suggestion': suggestion,
        })

    return hits


def main():
    parser = argparse.ArgumentParser(description='全平台中文化扫描工具')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--scan', action='store_true', help='扫描并输出未中文化的英文 UI 文本')
    group.add_argument('--dry-run', action='store_true', help='预览替换 diff（不修改文件）')
    group.add_argument('--apply', action='store_true', help='实际执行替换')
    args = parser.parse_args()

    src_root = pathlib.Path('audit-platform/frontend/src')
    if not src_root.exists():
        print(f'ERROR: {src_root} not found. Run from project root.')
        sys.exit(1)

    vue_files = sorted(src_root.rglob('*.vue'))
    print(f'Scanning {len(vue_files)} .vue files...\n')

    all_hits = []
    for f in vue_files:
        all_hits.extend(scan_file(f, src_root))

    if args.scan:
        # Group by file
        by_file = defaultdict(list)
        for h in all_hits:
            by_file[h['file']].append(h)

        print(f'Total English UI text hits: {len(all_hits)}')
        print(f'Files affected: {len(by_file)}')
        print()

        # Show by frequency
        val_counter = Counter(h['value'] for h in all_hits)
        print('=== Top values by frequency ===')
        for val, count in val_counter.most_common(30):
            suggestion = GLOSSARY.get(val, '???')
            marker = '  ' if suggestion != '???' else ' [NO MAPPING]'
            print(f'  [{count:2d}x] "{val}" -> "{suggestion}"{marker}')

        print()
        print('=== All hits by file ===')
        for filepath, hits in sorted(by_file.items()):
            print(f'\n  {filepath}:')
            for h in hits:
                marker = '' if h['suggestion'] != '???' else ' [NO MAPPING]'
                print(f'    L{h["line"]:4d} {h["attr"]}="{h["value"]}" -> "{h["suggestion"]}"{marker}')

        # Summary
        mapped = sum(1 for h in all_hits if h['suggestion'] != '???')
        unmapped = len(all_hits) - mapped
        print(f'\n=== Summary ===')
        print(f'  Total hits: {len(all_hits)}')
        print(f'  With mapping: {mapped}')
        print(f'  Without mapping (need manual): {unmapped}')

    elif args.dry_run or args.apply:
        # Only process hits that have a mapping
        replaceable = [h for h in all_hits if h['suggestion'] != '???']
        print(f'Replaceable hits: {len(replaceable)} / {len(all_hits)} total')
        print()

        # Group by file for replacement
        by_file = defaultdict(list)
        for h in replaceable:
            by_file[h['file']].append(h)

        modified_files = 0
        for filepath, hits in sorted(by_file.items()):
            full_path = src_root / filepath
            content = full_path.read_text(encoding='utf-8', errors='ignore')
            new_content = content

            for h in hits:
                old_str = f'{h["attr"]}="{h["value"]}"'
                new_str = f'{h["attr"]}="{h["suggestion"]}"'
                if old_str in new_content:
                    new_content = new_content.replace(old_str, new_str, 1)

            if new_content != content:
                modified_files += 1
                if args.dry_run:
                    print(f'--- {filepath}')
                    for h in hits:
                        print(f'  L{h["line"]:4d}: {h["attr"]}="{h["value"]}" -> "{h["suggestion"]}"')
                elif args.apply:
                    full_path.write_text(new_content, encoding='utf-8')
                    print(f'  [MODIFIED] {filepath} ({len(hits)} replacements)')

        print(f'\n{"Would modify" if args.dry_run else "Modified"}: {modified_files} files')


if __name__ == '__main__':
    main()
