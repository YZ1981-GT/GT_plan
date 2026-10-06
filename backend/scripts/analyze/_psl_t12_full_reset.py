"""完全重置 A5-1 的 sync 状态（entry_state + representation + content_version + pending mutations）然后重新首次发布。"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8")
    except: pass

ENTRY_ID = "xlsx/gt-a51-cashflow-audit"
WP_ID = "2246b5c0-19c3-4d66-bfb2-72d9afdc2996"
PROJECT_ID = "c8621493-70aa-46a9-8285-e0674e4e1418"

async def main():
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
    from app.core.config import settings

    engine = create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        # 1. 查现状
        es = (await session.execute(sa.text(
            "SELECT * FROM working_paper_sync_entry_state WHERE entry_id = :e AND wp_id = :w"
        ), {"e": ENTRY_ID, "w": WP_ID})).mappings().first()
        rep_id = es["current_representation_id"] if es else None
        print(f"entry_state: rep_id={rep_id}")

        # 2. 删 content_version（按 wp_id）
        r = await session.execute(sa.text(
            "DELETE FROM working_paper_content_version WHERE wp_id = :w"
        ), {"w": WP_ID})
        print(f"Deleted {r.rowcount} content_versions")

        # 4. 删 entry_state（引用 representation）
        r = await session.execute(sa.text(
            "DELETE FROM working_paper_sync_entry_state WHERE entry_id = :e AND wp_id = :w"
        ), {"e": ENTRY_ID, "w": WP_ID})
        print(f"Deleted {r.rowcount} entry_states")

        # 5. 删 representation（引用 bundle）
        reps = (await session.execute(sa.text(
            "SELECT id, definition_bundle_id FROM working_paper_content_representation WHERE entry_id = :e AND wp_id = :w"
        ), {"e": ENTRY_ID, "w": WP_ID})).fetchall()
        for rep in reps:
            await session.execute(sa.text(
                "DELETE FROM working_paper_content_representation WHERE id = :id"
            ), {"id": str(rep.id)})
        print(f"Deleted {len(reps)} representations")

        # 6. 删 bundles
        for rep in reps:
            if rep.definition_bundle_id:
                try:
                    await session.execute(sa.text(
                        "DELETE FROM working_paper_sync_definition_bundle WHERE id = :id"
                    ), {"id": str(rep.definition_bundle_id)})
                except Exception as e:
                    print(f"  bundle {rep.definition_bundle_id}: {e}")
        
        await session.commit()
        print("\nAll A5-1 sync state cleaned")

    # 7. 重新首次发布
    print("\nRe-running first publish...")
    from scripts.analyze._psl_t12_first_publish import run
    report = await run(apply=True)
    print(f"\nResult: {report.get('status')}")
    if report.get("receipt"):
        print(f"  revision: {report['receipt'].get('revision')}")
        print(f"  generation: {report['receipt'].get('generation')}")

    await engine.dispose()
    return report.get("status") == "published"

ok = asyncio.run(main())
sys.exit(0 if ok else 1)
