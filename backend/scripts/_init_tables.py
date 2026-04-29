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
try: from app.models import dataset_models
except Exception as e: print(f"skip dataset_models: {e}")
try: from app.models import phase12_models
except Exception as e: print(f"skip phase12_models: {e}")
try: from app.models import phase13_models
except Exception as e: print(f"skip phase13_models: {e}")
try: from app.models import phase14_enums; from app.models import phase14_models
except Exception as e: print(f"skip phase14_models: {e}")
try: from app.models import phase15_models
except Exception as e: print(f"skip phase15_models: {e}")
try: from app.models import phase16_models
except Exception as e: print(f"skip phase16_models: {e}")

DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/audit_platform"
engine = create_engine(DB_URL)
Base.metadata.create_all(engine)
tables = sorted(Base.metadata.tables.keys())
print(f"\nCreated {len(tables)} tables:")
for t in tables:
    print(f"  {t}")

# 自动加载报表种子数据
try:
    import json
    from pathlib import Path
    from sqlalchemy.orm import Session

    seed_path = Path(__file__).parent.parent / "data" / "report_config_seed.json"
    if seed_path.exists():
        seed_data = json.loads(seed_path.read_text(encoding="utf-8"))
        with Session(engine) as session:
            from app.models.report_models import ReportConfig, FinancialReportType
            existing_count = session.query(ReportConfig).count()
            if existing_count == 0:
                count = 0
                for block in seed_data:
                    report_type = block["report_type"]
                    standard = block["applicable_standard"]
                    for row in block["rows"]:
                        rc = ReportConfig(
                            report_type=FinancialReportType(report_type) if report_type in [e.value for e in FinancialReportType] else None,
                            row_number=row["row_number"],
                            row_code=row["row_code"],
                            row_name=row["row_name"],
                            indent_level=row.get("indent_level", 0),
                            formula=row.get("formula"),
                            formula_category=row.get("formula_category"),
                            formula_description=row.get("formula_description"),
                            formula_source=row.get("formula_source"),
                            applicable_standard=standard,
                            is_total_row=row.get("is_total_row", False),
                            parent_row_code=row.get("parent_row_code"),
                        )
                        if rc.report_type:
                            session.add(rc)
                            count += 1
                session.commit()
                print(f"\nLoaded {count} report config rows from seed data")
            else:
                print(f"\nReport config already has {existing_count} rows, skipping seed")
except Exception as e:
    print(f"\nWarning: Failed to load report seed data: {e}")

engine.dispose()
