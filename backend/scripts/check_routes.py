"""检查路由前缀冲突和前后端联动完整性"""
import re
import os
from collections import Counter

# 1. 分析已注册路由的前缀
main_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'main.py')
with open(main_path, 'r', encoding='utf-8') as f:
    mc = f.read()

imported = re.findall(r'from app\.routers\.(\w+) import router', mc)
print(f"=== 已注册路由模块: {len(imported)} ===")

router_dir = os.path.join(os.path.dirname(__file__), '..', 'app', 'routers')
prefixes = []
for mod in imported:
    fp = os.path.join(router_dir, mod + '.py')
    if not os.path.exists(fp):
        print(f"  WARNING: {mod}.py 不存在!")
        continue
    with open(fp, 'r', encoding='utf-8') as f:
        c = f.read()
    m = re.search(r'prefix\s*=\s*["\']([^"\']+)', c)
    p = m.group(1) if m else '(no prefix)'
    # Check if main.py overrides prefix
    m2 = re.search(rf'include_router\([^,]*{mod}[^,]*,\s*prefix\s*=\s*["\']([^"\']+)', mc)
    if m2:
        p = m2.group(1) + ' (main.py override)'
    prefixes.append((mod, p))

# Find duplicates
pfx_list = [p for _, p in prefixes]
dupes = {k: v for k, v in Counter(pfx_list).items() if v > 1}

if dupes:
    print(f"\n!!! 发现 {len(dupes)} 个前缀冲突:")
    for pfx, count in dupes.items():
        mods = [m for m, p in prefixes if p == pfx]
        print(f"  {pfx} -> {mods}")
else:
    print("\n无前缀冲突")

# 2. 未注册的路由文件（死代码）
all_files = set(f.replace('.py', '') for f in os.listdir(router_dir)
               if f.endswith('.py') and f != '__init__.py')
imported_set = set(imported)
dead = sorted(all_files - imported_set)
print(f"\n=== 未注册路由文件（死代码）: {len(dead)} ===")
for d in dead:
    print(f"  {d}.py")

# 3. 前端路由 vs Vue 文件
fe_router = os.path.join(os.path.dirname(__file__), '..', '..', 'audit-platform', 'frontend', 'src', 'router', 'index.ts')
fe_views = os.path.join(os.path.dirname(__file__), '..', '..', 'audit-platform', 'frontend', 'src', 'views')

if os.path.exists(fe_router):
    with open(fe_router, 'r', encoding='utf-8') as f:
        rc = f.read()
    vue_imports = re.findall(r"import\('@/views/([^']+)'\)", rc)
    print(f"\n=== 前端路由引用的 Vue 文件: {len(vue_imports)} ===")
    missing_vue = []
    for vi in vue_imports:
        vp = os.path.join(fe_views, vi)
        if not os.path.exists(vp):
            missing_vue.append(vi)
    if missing_vue:
        print(f"  缺失 Vue 文件: {missing_vue}")
    else:
        print("  所有引用的 Vue 文件都存在")

print("\n=== 完成 ===")
