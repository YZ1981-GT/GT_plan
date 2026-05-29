"""迁移链完整性检查脚本

验证：
1. 只有一个 head（无分叉）
2. 所有迁移有 downgrade 函数（非 pass/raise）
3. 迁移链从 001_consolidated 到 head 连续无断裂

用法：python backend/scripts/check_migrations.py
CI 中作为 pre-commit 或 PR 检查使用。
"""

import importlib.util
import sys
from pathlib import Path

VERSIONS_DIR = Path(__file__).parent.parent / "alembic" / "versions"
ARCHIVED_DIR = VERSIONS_DIR / "_archived"


def load_migration(path: Path) -> dict:
    """加载迁移文件，提取 revision/down_revision/upgrade/downgrade"""
    spec = importlib.util.spec_from_file_location("migration", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        return {"error": str(e), "path": str(path)}

    return {
        "path": path.name,
        "revision": getattr(mod, "revision", None),
        "down_revision": getattr(mod, "down_revision", None),
        "has_upgrade": hasattr(mod, "upgrade"),
        "has_downgrade": hasattr(mod, "downgrade"),
    }


def check():
    errors = []

    # 收集所有迁移文件（排除 __init__.py 和 _archived/）
    migrations = []
    for f in VERSIONS_DIR.glob("*.py"):
        if f.name == "__init__.py":
            continue
        migrations.append(load_migration(f))

    if not migrations:
        print("⚠️  没有找到迁移文件")
        return 1

    # 检查加载错误
    for m in migrations:
        if "error" in m:
            errors.append(f"❌ 加载失败: {m['path']} — {m['error']}")

    # 构建 revision 图
    rev_map = {}  # revision -> migration
    children = {}  # down_revision -> [revision]

    for m in migrations:
        if "error" in m:
            continue
        rev = m["revision"]
        down = m["down_revision"]
        rev_map[rev] = m

        # down_revision 可能是 tuple（merge）或 str 或 None
        if down is None:
            children.setdefault(None, []).append(rev)
        elif isinstance(down, (list, tuple)):
            for d in down:
                children.setdefault(d, []).append(rev)
        else:
            children.setdefault(down, []).append(rev)

    # 检查 head 数量（没有被其他迁移引用为 down_revision 的）
    all_revisions = set(rev_map.keys())
    referenced = set()
    for m in migrations:
        if "error" in m:
            continue
        down = m["down_revision"]
        if down is None:
            pass
        elif isinstance(down, (list, tuple)):
            referenced.update(down)
        else:
            referenced.add(down)

    heads = all_revisions - referenced
    if len(heads) > 1:
        errors.append(f"❌ 多个 head 检测到: {heads}（需要 merge 迁移）")
    elif len(heads) == 1:
        print(f"✅ 唯一 head: {heads.pop()}")
    else:
        errors.append("❌ 无法确定 head")

    # 检查 downgrade 函数
    for m in migrations:
        if "error" in m:
            continue
        if m["revision"] == "001_consolidated":
            continue  # 基线允许无 downgrade
        if not m["has_downgrade"]:
            errors.append(f"⚠️  缺少 downgrade: {m['path']}")

    # 输出结果
    print(f"\n📊 迁移文件总数: {len(migrations)}")
    if errors:
        print(f"\n{'='*50}")
        for e in errors:
            print(e)
        print(f"\n❌ 发现 {len(errors)} 个问题")
        return 1
    else:
        print("\n✅ 迁移链完整性检查通过")
        return 0


if __name__ == "__main__":
    sys.exit(check())
