"""一次性脚本：全量 schema 同步（create_all + 逐列 ALTER TABLE）"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import app.models  # noqa: E402,F401
import app.models.extension_models  # noqa: E402,F401
import app.models.ai_models  # noqa: E402,F401
import app.models.phase10_models  # noqa: E402,F401
import app.models.phase12_models  # noqa: E402,F401
import app.models.phase15_models  # noqa: E402,F401
import app.models.report_models  # noqa: E402,F401
import app.models.workpaper_models  # noqa: E402,F401
import app.models.dataset_models  # noqa: E402,F401
import app.models.collaboration_models  # noqa: E402,F401
import app.models.staff_models  # noqa: E402,F401

try:
    import app.models.workhour_entry_models  # noqa: F401
except ImportError:
    pass
try:
    import app.models.attachment_lineage_model  # noqa: F401
except ImportError:
    pass


async def main():
    from app.models.base import Base
    from app.core.database import engine
    from sqlalchemy import inspect, text
    from sqlalchemy.dialects.postgresql import dialect as pg_dialect_cls

    pg_dialect = pg_dialect_cls()

    # Step 1: create_all for missing tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Step 1: create_all done")

    # Step 2: Add missing columns
    added = 0
    skipped = 0
    errors = 0

    async with engine.connect() as conn:
        def get_info(sync_conn):
            insp = inspect(sync_conn)
            result = {}
            for tname in insp.get_table_names():
                cols = {c["name"] for c in insp.get_columns(tname)}
                result[tname] = cols
            return result

        existing_info = await conn.run_sync(get_info)

        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing_info:
                continue

            existing_cols = existing_info[table_name]

            for col in table.columns:
                if col.name in existing_cols:
                    skipped += 1
                    continue

                # Build type string
                try:
                    col_type = col.type.compile(dialect=pg_dialect)
                except Exception:
                    col_type = "TEXT"

                # Build default
                default = ""
                if col.server_default is not None:
                    try:
                        sd = col.server_default
                        if hasattr(sd, "arg"):
                            arg = sd.arg
                            if hasattr(arg, "text"):
                                default = f" DEFAULT {arg.text}"
                            else:
                                default = f" DEFAULT {arg}"
                    except Exception:
                        pass

                # Nullable
                nullable_str = ""
                if not col.nullable and not default:
                    # NOT NULL without default - use safe defaults
                    upper_type = col_type.upper()
                    if "INT" in upper_type:
                        default = " DEFAULT 0"
                    elif "BOOL" in upper_type:
                        default = " DEFAULT false"
                    elif "JSON" in upper_type:
                        default = " DEFAULT '{}'"
                    elif "UUID" in upper_type:
                        default = " DEFAULT gen_random_uuid()"
                    elif "TIMESTAMP" in upper_type:
                        default = " DEFAULT now()"
                    elif "NUMERIC" in upper_type or "DECIMAL" in upper_type:
                        default = " DEFAULT 0"
                    else:
                        # Can't add NOT NULL without default, make nullable
                        pass

                stmt = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS \"{col.name}\" {col_type}{nullable_str}{default}"

                try:
                    await conn.execute(text(stmt))
                    await conn.commit()
                    added += 1
                except Exception as e:
                    await conn.rollback()
                    err = str(e)[:100]
                    if "already exists" in err:
                        skipped += 1
                    else:
                        errors += 1
                        if errors <= 10:
                            print(f"  ERR [{table_name}.{col.name}]: {err}")

    print(f"Step 2: added={added}, skipped={skipped}, errors={errors}")
    print(f"Total: {added + skipped + errors} columns processed")


if __name__ == "__main__":
    asyncio.run(main())
