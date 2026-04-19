# -*- coding: utf-8 -*-
"""重新导入余额表（带 aux_dimensions_raw）"""
import sys, asyncio
from pathlib import Path
from uuid import UUID
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def main():
    from app.services.smart_import_engine import smart_parse_files, write_four_tables
    from app.core.database import async_session

    base = Path(__file__).resolve().parent.parent.parent / "数据"
    files = []
    with open(base / "科目余额表-重庆和平药房连锁有限责任公司2025.xlsx", "rb") as f:
        files.append(("余额表.xlsx", f.read()))

    print("解析余额表...", flush=True)
    result = smart_parse_files(files)
    print(f"balance={len(result['balance_rows'])}, aux_bal={len(result['aux_balance_rows'])}", flush=True)

    # 检查 aux_dimensions_raw
    for r in result["aux_balance_rows"][:3]:
        raw = r.get("aux_dimensions_raw", "MISSING")
        print(f"  {r['aux_type']}:{r['aux_code']}: raw={raw[:80] if raw else 'None'}", flush=True)

    pid = UUID("6687b8ce-7a83-4816-bd4a-c2d173d4b683")
    async with async_session() as db:
        print("写入数据库...", flush=True)
        imported = await write_four_tables(
            pid, 2025,
            result["balance_rows"], result["aux_balance_rows"],
            [], [],  # 不重新导入序时账
            db,
        )
        print(f"完成: {imported}", flush=True)

asyncio.run(main())
