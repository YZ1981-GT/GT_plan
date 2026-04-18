"""找出 routers/ 中存在但未注册到 main.py 的死代码路由文件"""
import os
import re

main_path = "backend/app/main.py"
router_dir = "backend/app/routers"

# 从 main.py 提取所有导入的路由模块名
with open(main_path, encoding="utf-8") as f:
    main_content = f.read()

registered = set()
for m in re.finditer(r"from app\.routers\.(\w+) import", main_content):
    registered.add(m.group(1) + ".py")

# 列出 routers/ 中所有 .py 文件
all_files = sorted(f for f in os.listdir(router_dir) if f.endswith(".py") and f != "__init__.py")

dead = [f for f in all_files if f not in registered]
alive = [f for f in all_files if f in registered]

print(f"已注册: {len(alive)} 个路由文件")
print(f"未注册（死代码）: {len(dead)} 个\n")
for f in dead:
    # 检查文件内容判断是同步还是异步
    path = os.path.join(router_dir, f)
    content = open(path, encoding="utf-8").read()
    is_sync = "db.query(" in content or "from sqlalchemy.orm import Session" in content
    style = "同步ORM" if is_sync else "异步ORM"
    lines = content.count("\n")
    endpoints = len(re.findall(r"@router\.(get|post|put|delete|patch)\(", content))
    print(f"  {f:35s} {style:8s} {endpoints:2d}个端点 {lines:4d}行")
