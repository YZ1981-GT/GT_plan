#!/bin/bash
# V199 重放（每条独立事务 + SAVEPOINT 语义 = autocommit 单条）
set -a; source /opt/gt-new-plan/backend/.env; set +a
cd /opt/gt-new-plan/backend
../.venv/bin/python - <<'EOF'
import asyncio, os
from pathlib import Path

async def main():
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(os.environ["DATABASE_URL"])
    raw = (Path("migrations") / "V199__formula_global_settings_and_templates.sql").read_text(encoding="utf-8")
    ok = fail = 0
    for i, stmt in enumerate([s.strip() for s in raw.split(";") if s.strip()]):
        lines = [l for l in stmt.split("\n") if not l.strip().startswith("--")]
        clean = "\n".join(lines).strip()
        if not clean:
            continue
        # 每条一个独立连接事务（失败不污染后续）
        try:
            async with engine.connect() as conn:
                await conn.execute(clean.replace("\x00", ""))
                await conn.commit()
            ok += 1
        except Exception as exc:
            fail += 1
            first = str(exc).split("\n")[0][:120]
            head = clean.replace("\n", " ")[:80]
            print(f"  [{fail}] {head} => {first}")
    print(f"ok={ok} fail={fail}")
    await engine.dispose()

asyncio.run(main())
EOF
echo "--- 核对 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT to_regclass('formula_template')"
sudo -u postgres psql -d audit_platform -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='knowledge_documents' AND column_name='ocr_status'"
