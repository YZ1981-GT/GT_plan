"""自动生成 ER 图（基于 SQLAlchemy models）

使用方式：python scripts/gen_er_diagram.py
输出：docs/er_diagram.svg

依赖：pip install eralchemy2（按需安装）
还需要系统安装 graphviz: https://graphviz.org/download/
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    try:
        from eralchemy2 import render_er
    except ImportError:
        print("请先安装 eralchemy2: pip install eralchemy2")
        print("还需要 graphviz: https://graphviz.org/download/")
        sys.exit(1)

    output_path = Path(__file__).resolve().parent.parent.parent / "docs" / "er_diagram.svg"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 尝试方式 1：从 DATABASE_URL 直接渲染
    try:
        from app.core.config import settings

        # eralchemy 需要同步驱动，替换 asyncpg
        db_url = settings.DATABASE_URL.replace("+asyncpg", "")

        render_er(db_url, str(output_path))
        print(f"ER 图已生成: {output_path}")
        return
    except Exception as e:
        print(f"从数据库直接生成失败: {e}")
        print("尝试从 SQLAlchemy metadata 生成...")

    # 尝试方式 2：从 models metadata 渲染
    try:
        from app.models.base import Base  # noqa: F401
        # Import all models to populate metadata
        import app.models.core  # noqa: F401

        try:
            import app.models.workpaper_models  # noqa: F401
        except ImportError:
            pass
        try:
            import app.models.audit_platform_models  # noqa: F401
        except ImportError:
            pass

        render_er(Base.metadata, str(output_path))
        print(f"ER 图已生成（从 metadata）: {output_path}")
    except Exception as e:
        print(f"生成失败: {e}")
        print("请确保：")
        print("  1. eralchemy2 已安装: pip install eralchemy2")
        print("  2. graphviz 已安装并在 PATH 中")
        print("  3. 数据库可连接 或 SQLAlchemy models 可导入")
        sys.exit(1)


if __name__ == "__main__":
    main()
