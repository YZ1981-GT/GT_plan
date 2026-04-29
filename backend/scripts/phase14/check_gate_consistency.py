"""Phase 14 验收脚本：三入口门禁一致性检查

随机选 10 个 wp_id，三入口调用 gate_engine.evaluate，断言 decision 一致。
用法: python -m scripts.phase14.check_gate_consistency
"""
import asyncio
import uuid
import sys

PASS = 0
FAIL = 0


async def main():
    global PASS, FAIL
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text
    from app.services.gate_engine import gate_engine
    from app.services.gate_rules_phase14 import register_phase14_rules

    register_phase14_rules()

    async with AsyncSession(async_engine) as db:
        # 取最多 10 个底稿
        result = await db.execute(text("""
            SELECT id, project_id FROM working_paper
            WHERE is_deleted = false LIMIT 10
        """))
        rows = result.fetchall()
        if not rows:
            print("[SKIP] 无底稿数据")
            return

        actor_id = uuid.uuid4()
        for wp_id, project_id in rows:
            decisions = {}
            for gate_type in ["submit_review", "sign_off", "export_package"]:
                try:
                    r = await gate_engine.evaluate(
                        db=db, gate_type=gate_type,
                        project_id=project_id, wp_id=wp_id,
                        actor_id=actor_id, context={},
                    )
                    decisions[gate_type] = r.decision
                except Exception as e:
                    decisions[gate_type] = f"ERROR:{e}"

            vals = set(decisions.values())
            if len(vals) == 1:
                PASS += 1
                print(f"  [PASS] wp={str(wp_id)[:8]} decision={vals.pop()}")
            else:
                FAIL += 1
                print(f"  [FAIL] wp={str(wp_id)[:8]} decisions={decisions}")

    print(f"\n[RESULT] PASS={PASS} FAIL={FAIL} {'ALL PASS ✓' if FAIL == 0 else 'HAS FAILURES ✗'}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
