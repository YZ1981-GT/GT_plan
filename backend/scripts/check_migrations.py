"""检查迁移链并输出重编号方案"""
import re, os

d = os.path.join(os.path.dirname(__file__), '..', 'alembic', 'versions')
files = sorted(f for f in os.listdir(d) if f.endswith('.py') and f != '__init__.py')

print("=== 当前迁移链 ===")
for f in files:
    fp = os.path.join(d, f)
    with open(fp, 'r', encoding='utf-8') as fh:
        c = fh.read()
    rev = re.search(r'revision\s*=\s*["\']([^"\']+)', c)
    down = re.search(r'down_revision\s*=\s*["\']([^"\']*)', c)
    r = rev.group(1) if rev else '?'
    dr = down.group(1) if down else 'None'
    print(f'  {f:55s} rev={r:6s} down={dr}')

# Find duplicates
from collections import Counter
nums = [f.split('_')[0] for f in files]
dupes = {k: v for k, v in Counter(nums).items() if v > 1}
print(f"\n=== 重复编号: {dupes} ===")

# Propose renaming
print("\n=== 重编号方案 ===")
new_num = 1
rename_map = {}
for f in files:
    old_num = f.split('_')[0]
    new_name = f'{new_num:03d}' + f[len(old_num):]
    if new_name != f:
        rename_map[f] = new_name
        print(f'  {f} -> {new_name}')
    new_num += 1

print(f"\n需要重命名 {len(rename_map)} 个文件")
