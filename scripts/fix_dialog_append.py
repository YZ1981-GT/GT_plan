"""批量给 el-dialog 添加 append-to-body 属性（幂等）。

Phase 11 Task 4.1: 解决三栏布局 overflow:hidden 截断弹窗问题。
使用 Python 而非 PowerShell，避免编码损坏。

幂等性保证：
  - 单行 <el-dialog ... append-to-body ...> 不会重复添加
  - 多行 <el-dialog\n  ...\n  append-to-body\n  ...> 也不会重复添加
  - 已有 append-to-body 的弹窗完全不受影响

用法：
  python scripts/fix_dialog_append.py          # 执行修复
  python scripts/fix_dialog_append.py --dry-run # 仅预览，不写文件
"""
import pathlib
import re
import sys


def has_append_to_body(tag_text: str) -> bool:
    """检查一个 <el-dialog ...> 标签（可能跨多行）是否已包含 append-to-body。"""
    return bool(re.search(r'\bappend-to-body\b', tag_text))


def fix_file(filepath: pathlib.Path, dry_run: bool = False) -> bool:
    """修复单个 Vue 文件中缺少 append-to-body 的 el-dialog 标签。
    返回 True 表示文件有修改。
    """
    text = filepath.read_text(encoding='utf-8')

    # 匹配完整的 <el-dialog ... > 标签（可能跨多行）
    # 使用 re.DOTALL 让 . 匹配换行符
    pattern = re.compile(r'<el-dialog\b(.*?)(?=/?>)', re.DOTALL)

    modified = False

    def replacer(match: re.Match) -> str:
        nonlocal modified
        full_match = match.group(0)  # e.g. '<el-dialog v-model="x" width="500px"'
        attrs = match.group(1)       # e.g. ' v-model="x" width="500px"'

        if has_append_to_body(attrs):
            return full_match  # 已有，不动

        modified = True
        # 在 <el-dialog 后面紧跟插入 append-to-body
        return '<el-dialog append-to-body' + attrs

    new_text = pattern.sub(replacer, text)

    if modified and not dry_run:
        filepath.write_text(new_text, encoding='utf-8')

    return modified


def main():
    dry_run = '--dry-run' in sys.argv

    vue_dir = pathlib.Path('audit-platform/frontend/src')
    if not vue_dir.exists():
        print(f'Error: directory not found: {vue_dir}')
        sys.exit(1)

    fixed_count = 0
    for f in sorted(vue_dir.rglob('*.vue')):
        if fix_file(f, dry_run=dry_run):
            prefix = '[DRY-RUN] Would fix' if dry_run else 'Fixed'
            print(f'{prefix}: {f}')
            fixed_count += 1

    mode = ' (dry-run)' if dry_run else ''
    print(f'\nTotal fixed: {fixed_count} files{mode}')


if __name__ == '__main__':
    main()
