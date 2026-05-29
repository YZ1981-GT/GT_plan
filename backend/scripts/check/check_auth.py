"""检查所有路由文件的认证覆盖率"""
import os

d = "backend/app/routers"
files = [f for f in sorted(os.listdir(d)) if f.endswith(".py") and not f.startswith("__")]
no_auth = []
for f in files:
    content = open(os.path.join(d, f), encoding="utf-8").read()
    has = any(kw in content for kw in ["get_current_user", "require_project_access", "require_role"])
    if not has:
        no_auth.append(f)

print(f"Total router files: {len(files)}")
print(f"With auth: {len(files) - len(no_auth)}")
print(f"Without auth: {len(no_auth)}")
for f in no_auth:
    print(f"  {f}")
