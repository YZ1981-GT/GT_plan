"""修复 Alembic 迁移编号冲突 — 重编号为线性链 001-032"""
import re, os, shutil

d = os.path.join(os.path.dirname(__file__), '..', 'alembic', 'versions')
files = sorted(f for f in os.listdir(d) if f.endswith('.py') and f != '__init__.py')

# Build rename map and new revision chain
rename_ops = []
for i, f in enumerate(files):
    new_num = f'{i+1:03d}'
    old_num = f.split('_')[0]
    new_name = new_num + f[len(old_num):]
    
    fp = os.path.join(d, f)
    with open(fp, 'r', encoding='utf-8') as fh:
        content = fh.read()
    
    # Extract current revision
    rev_match = re.search(r'(revision\s*=\s*["\'])([^"\']+)(["\'])', content)
    down_match = re.search(r'(down_revision\s*=\s*["\'])([^"\']*?)(["\'])', content)
    
    old_rev = rev_match.group(2) if rev_match else None
    new_rev = new_num
    new_down = f'{i:03d}' if i > 0 else None
    
    rename_ops.append({
        'old_file': f,
        'new_file': new_name,
        'old_rev': old_rev,
        'new_rev': new_rev,
        'new_down': new_down,
    })

# Execute: update content then rename
for op in rename_ops:
    fp = os.path.join(d, op['old_file'])
    with open(fp, 'r', encoding='utf-8') as fh:
        content = fh.read()
    
    # Update revision
    if op['old_rev']:
        content = re.sub(
            r'(revision\s*=\s*["\'])[^"\']+(["\'])',
            f'\\g<1>{op["new_rev"]}\\2',
            content, count=1
        )
    
    # Update down_revision
    if op['new_down'] is None:
        content = re.sub(
            r'down_revision\s*=\s*["\'][^"\']*["\']',
            'down_revision = None',
            content, count=1
        )
    else:
        content = re.sub(
            r'(down_revision\s*=\s*["\'])[^"\']*(["\'])',
            f'\\g<1>{op["new_down"]}\\2',
            content, count=1
        )
    
    with open(fp, 'w', encoding='utf-8') as fh:
        fh.write(content)
    
    # Rename file
    if op['old_file'] != op['new_file']:
        new_fp = os.path.join(d, op['new_file'])
        os.rename(fp, new_fp)
        print(f'  {op["old_file"]:55s} -> {op["new_file"]}  (rev={op["new_rev"]}, down={op["new_down"]})')
    else:
        print(f'  {op["old_file"]:55s}    (rev={op["new_rev"]}, down={op["new_down"]}) [no rename]')

print(f'\n完成: {len(rename_ops)} 个迁移文件已线性化')
