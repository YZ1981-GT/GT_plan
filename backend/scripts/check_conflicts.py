"""检查跨阶段冲突：重复表名、重复服务类"""
import os
import re

models_dir = os.path.join(os.path.dirname(__file__), '..', 'app', 'models')
services_dir = os.path.join(os.path.dirname(__file__), '..', 'app', 'services')

# 1. 检查重复 __tablename__
print("=== 检查重复表名 ===")
tablenames = {}
for root, dirs, files in os.walk(models_dir):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if not f.endswith('.py') or f == '__init__.py':
            continue
        fp = os.path.join(root, f)
        with open(fp, 'r', encoding='utf-8') as fh:
            content = fh.read()
        for m in re.finditer(r'__tablename__\s*=\s*["\'](\w+)["\']', content):
            tn = m.group(1)
            if tn not in tablenames:
                tablenames[tn] = []
            tablenames[tn].append(f)

dupes = {k: v for k, v in tablenames.items() if len(v) > 1}
if dupes:
    print(f"  发现 {len(dupes)} 个重复表名:")
    for tn, files in sorted(dupes.items()):
        print(f"    {tn}: {files}")
else:
    print("  无重复表名")

# 2. 检查重复服务类名
print("\n=== 检查重复服务类名 ===")
classnames = {}
for root, dirs, files in os.walk(services_dir):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if not f.endswith('.py') or f == '__init__.py':
            continue
        fp = os.path.join(root, f)
        with open(fp, 'r', encoding='utf-8') as fh:
            content = fh.read()
        for m in re.finditer(r'^class\s+(\w+Service)\b', content, re.MULTILINE):
            cn = m.group(1)
            if cn not in classnames:
                classnames[cn] = []
            classnames[cn].append(f)

svc_dupes = {k: v for k, v in classnames.items() if len(v) > 1}
if svc_dupes:
    print(f"  发现 {len(svc_dupes)} 个重复服务类名:")
    for cn, files in sorted(svc_dupes.items()):
        print(f"    {cn}: {files}")
else:
    print("  无重复服务类名")

# 3. 统计
print(f"\n=== 统计 ===")
print(f"  表名总数: {len(tablenames)}")
print(f"  服务类总数: {len(classnames)}")
print(f"  重复表名: {len(dupes)}")
print(f"  重复服务类: {len(svc_dupes)}")
