"""只在回滚事务中测 500 行批量建项预校验与 apply；不会保留业务数据。"""
from __future__ import annotations

import asyncio
import argparse
import json
import sys
import time
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import sqlalchemy as sa
from openpyxl import Workbook

import app.models  # noqa: F401 — 注册 Project 外键依赖模型
import app.models.extension_models  # noqa: F401 — accounting_standards 外键
from app.core.database import async_session
from app.models.core import User
from app.services.batch_project_execution import apply_validation_plan, create_validation_plan
from app.services.batch_project_workbook import EXTENDED_COLUMNS
from app.services.uscc_validator import USCC_CHARSET, _CHAR_TO_VALUE, _WEIGHTS


def valid_uscc(number: int) -> str:
    prefix = f"91{number:015d}"
    total = sum(_CHAR_TO_VALUE[prefix[index]] * _WEIGHTS[index] for index in range(17))
    check = 31 - total % 31
    return prefix + USCC_CHARSET[0 if check == 31 else check]


def workbook_bytes(count: int = 500) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("数据")
    sheet.append(EXTENDED_COLUMNS)
    for index in range(count):
        sheet.append([
            f"【测试】批量性能企业{index:03d}", valid_uscc(8_000_000 + index),
            f"批量性能{index:03d}", 2096, "年报审计", "企业会计准则", "单户",
            "", "", "", "新建", "", "",
        ])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


async def main(*, as_manager: bool = False) -> None:
    payload = workbook_bytes()
    async with async_session() as db:
        stored_actor = (await db.execute(sa.select(User).where(User.username == "admin"))).scalar_one()
        actor = (
            SimpleNamespace(id=stored_actor.id, role=SimpleNamespace(value="manager"))
            if as_manager else stored_actor
        )
        started = time.perf_counter()
        plan, response, _ = await create_validation_plan(
            payload, db, actor=actor, file_name="500行性能.xlsx", mode="project",
            idempotency_key=f"batch-performance-rollback-500-{'manager' if as_manager else 'admin'}",
        )
        planned_ms = (time.perf_counter() - started) * 1000
        if not response.valid:
            raise RuntimeError(response.model_dump_json())
        started = time.perf_counter()
        result = await apply_validation_plan(
            db, plan_id=plan.id, actor=actor, idempotency_key=plan.idempotency_key,
        )
        applied_ms = (time.perf_counter() - started) * 1000
        await db.rollback()
    print(json.dumps({
        "rows": 500, "actor_mode": "manager" if as_manager else "admin",
        "bytes": len(payload), "plan_ms": round(planned_ms, 1),
        "apply_ms": round(applied_ms, 1), "created": result.created_count,
        "rolled_back": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-manager", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(as_manager=args.as_manager))
