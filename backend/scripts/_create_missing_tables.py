"""补建所有缺失的表（不影响已有表和数据）"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, inspect

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/audit_platform"
engine = create_engine(DATABASE_URL)

# 导入所有模型，确保 Base.metadata 包含全部表定义
from app.models.base import Base
from app.models import core  # noqa
from app.models import audit_platform_models  # noqa
from app.models import report_models  # noqa
from app.models import workpaper_models  # noqa

# Phase 6/7 模型
try:
    from app.models import staff_models  # noqa
    print("  staff_models loaded")
except Exception as e:
    print(f"  staff_models FAILED: {e}")

try:
    from app.models import collaboration_models  # noqa
    print("  collaboration_models loaded")
except Exception as e:
    print(f"  collaboration_models FAILED: {e}")

try:
    from app.models import consolidation_models  # noqa
    print("  consolidation_models loaded")
except Exception as e:
    print(f"  consolidation_models FAILED: {e}")

try:
    from app.models import ai_models  # noqa
    print("  ai_models loaded")
except Exception as e:
    print(f"  ai_models FAILED: {e}")

try:
    from app.models import phase10_models  # noqa
    print("  phase10_models loaded")
except Exception as e:
    print(f"  phase10_models FAILED: {e}")

try:
    from app.models import procedure_models  # noqa
    print("  procedure_models loaded")
except Exception as e:
    print(f"  procedure_models FAILED: {e}")

try:
    from app.models import note_trim_models  # noqa
    print("  note_trim_models loaded")
except Exception as e:
    print(f"  note_trim_models FAILED: {e}")

# 检查已有表
inspector = inspect(engine)
existing = set(inspector.get_table_names())
all_tables = set(Base.metadata.tables.keys())
missing = all_tables - existing

print(f"\n已有表: {len(existing)}")
print(f"模型定义表: {len(all_tables)}")
print(f"缺失表: {len(missing)}")
if missing:
    for t in sorted(missing):
        print(f"  + {t}")

# 只创建缺失的表（checkfirst=True 不会影响已有表）
Base.metadata.create_all(engine, checkfirst=True)
print(f"\n补建完成！")

# 验证
inspector2 = inspect(engine)
existing2 = set(inspector2.get_table_names())
still_missing = all_tables - existing2
if still_missing:
    print(f"仍然缺失: {still_missing}")
else:
    print(f"所有 {len(all_tables)} 张表已就绪")

engine.dispose()
