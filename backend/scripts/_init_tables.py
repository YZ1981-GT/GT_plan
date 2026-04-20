"""一次性建表脚本"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text
from app.models.base import Base

# 导入所有模型
from app.models import core, audit_platform_models, report_models, workpaper_models
try: from app.models import consolidation_models
except Exception as e: print(f"skip consolidation_models: {e}")
try: from app.models import collaboration_models
except Exception as e: print(f"skip collaboration_models: {e}")
try: from app.models import ai_models
except Exception as e: print(f"skip ai_models: {e}")
try: from app.models import staff_models
except Exception as e: print(f"skip staff_models: {e}")
try: from app.models import phase10_models
except Exception as e: print(f"skip phase10_models: {e}")
try: from app.models import procedure_models
except Exception as e: print(f"skip procedure_models: {e}")
try: from app.models import note_trim_models
except Exception as e: print(f"skip note_trim_models: {e}")
try: from app.models import extension_models
except Exception as e: print(f"skip extension_models: {e}")

DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/audit_platform"
engine = create_engine(DB_URL)
Base.metadata.create_all(engine)
tables = sorted(Base.metadata.tables.keys())
print(f"\nCreated {len(tables)} tables:")
for t in tables:
    print(f"  {t}")
engine.dispose()
