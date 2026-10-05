"""K1 + D4 canary 真 PG 事务内试跑：推送后值正确，回滚后指纹逐字恢复（需求 9.4）。

Task 24 · spec formula-push-all-subjects-rollout

与 Task 4 的 PG 测试（test_formula_push_engine_pg.py）同模式：
- 临时 schema ``tmp_formula_push_canary_{uuid}``
- 最小表集合：projects / wp_index / working_paper / checklist_responses + V169（run / state）
- K1 + D4 两个 binding 的取数 mock 为固定源（与 test_formula_push_d4_canary.py 同口径）
- 推送后验证：K1 审定合计 3 键 / D4 两条锚点值 / 运行状态 ok / 状态行数
- **指纹比对**：推送前快照全表 → 推送并验证 → 回滚连接 → 重新快照 → 前后逐字相同

不 mock _find_workpapers / _project_audit_year —— 它们走临时 schema 内的真表。
取数层 mock：K1Binding.load_sources / TierAAnchorBinding.load_sources 返回固定源。
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models.formula_push_models import FormulaPushState
from app.services.formula_push import engine as push
from app.services.formula_push.bindings.k1 import K1Binding, K1Sources
from app.services.formula_push.bindings.tier_a import TierAAnchorBinding, TierASources
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot

_BACKEND = Path(__file__).resolve().parents[1]
_V169 = _BACKEND / "migrations" / "V169__formula_push_engine.sql"

# ── 固定取数源 ────────────────────────────────────────────────────────────

# K1：1221 期末 500000 / 1231 期末 200000
_K1_TB = TbAuditedSnapshot(
    tb_data={
        "1221": {"期末余额": Decimal("500000"), "年初余额": Decimal("300000"),
                 "本期发生额": Decimal("500000") - Decimal("300000")},
        "1231": {"期末余额": Decimal("200000"), "年初余额": Decimal("150000"),
                 "本期发生额": Decimal("200000") - Decimal("150000")},
    },
    available=True,
    company_codes=("001",),
)
_K1_SOURCES = K1Sources(formula=FormulaSources(tb=_K1_TB))

# D4：6001 期末 2000000 / 6051 期末 300000
_D4_TB = TbAuditedSnapshot(
    tb_data={
        "6001": {"期末余额": Decimal("2000000"), "年初余额": Decimal("1500000"),
                 "本期发生额": Decimal("2000000") - Decimal("1500000")},
        "6051": {"期末余额": Decimal("300000"), "年初余额": Decimal("200000"),
                 "本期发生额": Decimal("300000") - Decimal("200000")},
    },
    available=True,
    company_codes=("001",),
)
_D4_SOURCES = TierASources(formula=FormulaSources(tb=_D4_TB))


# ── 辅助 ──────────────────────────────────────────────────────────────────

async def _run_sql_file(conn, path: Path) -> None:
    from app.core.migration_runner import MigrationRunner
    for statement in MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8")):
        await conn.exec_driver_sql(statement)


def _fingerprint(rows: list[tuple]) -> tuple[tuple[str, str, str | None], ...]:
    """排序后的 (wp_id, item_id, remark) 元组，用于前后逐字比对。"""
    return tuple(sorted((str(r[0]), str(r[1]), r[2]) for r in rows))


# ── K1 底稿条目种子（需要组合行 unadj/aje/rje 才能计算审定合计） ─────────

def _k1_seed_items() -> dict[str, str]:
    """K1 底稿的组合行条目：r0~r3 各行的 receivable + baddebt 的 unadj/aje/rje。
    
    receivable 审定合计 = Σ (unadj + aje + rje) for r0~r3
      r0: 100 + 10 + 5 = 115
      r1: 200 + 20 + 10 = 230
      r2: 50 + 0 + 0 = 50
      r3: 30 + 5 + 5 = 40
      合计 = 435
    
    baddebt 审定合计 = Σ (unadj + aje + rje) for r0~r3
      r0: 10 + 1 + 0 = 11
      r1: 20 + 2 + 1 = 23
      r2: 5 + 0 + 0 = 5
      r3: 3 + 0 + 1 = 4
      合计 = 43
    
    net = 435 - 43 = 392
    """
    return {
        # receivable
        "K1-1-receivable-r0-unadj": "100", "K1-1-receivable-r0-aje": "10", "K1-1-receivable-r0-rje": "5",
        "K1-1-receivable-r1-unadj": "200", "K1-1-receivable-r1-aje": "20", "K1-1-receivable-r1-rje": "10",
        "K1-1-receivable-r2-unadj": "50", "K1-1-receivable-r2-aje": "0", "K1-1-receivable-r2-rje": "0",
        "K1-1-receivable-r3-unadj": "30", "K1-1-receivable-r3-aje": "5", "K1-1-receivable-r3-rje": "5",
        # baddebt
        "K1-1-baddebt-r0-unadj": "10", "K1-1-baddebt-r0-aje": "1", "K1-1-baddebt-r0-rje": "0",
        "K1-1-baddebt-r1-unadj": "20", "K1-1-baddebt-r1-aje": "2", "K1-1-baddebt-r1-rje": "1",
        "K1-1-baddebt-r2-unadj": "5", "K1-1-baddebt-r2-aje": "0", "K1-1-baddebt-r2-rje": "0",
        "K1-1-baddebt-r3-unadj": "3", "K1-1-baddebt-r3-aje": "0", "K1-1-baddebt-r3-rje": "1",
    }


# ── 主场景 ────────────────────────────────────────────────────────────────

async def _scenario(monkeypatch) -> dict:
    """临时 schema 内创建 K1+D4 双底稿，推送后验证值，回滚后验证指纹恢复。"""
    assert engine.dialect.name == "postgresql", f"需要 PostgreSQL，实际 {engine.dialect.name}"

    schema = f"tmp_formula_push_canary_{uuid.uuid4().hex[:10]}"
    project_id = uuid.uuid4()
    k1_idx, k1_wp = uuid.uuid4(), uuid.uuid4()
    d4_idx, d4_wp = uuid.uuid4(), uuid.uuid4()

    # ── mock 取数 ──
    async def fake_k1_load(db, project_id, year, wp_id):
        return _K1_SOURCES

    async def fake_d4_load(self_or_db, *args, **kwargs):
        return _D4_SOURCES

    monkeypatch.setattr(K1Binding, "load_sources", staticmethod(fake_k1_load))
    monkeypatch.setattr(TierAAnchorBinding, "load_sources", fake_d4_load)

    # ── mock _project_audit_year（避免 ORM 映射到临时 schema 的 projects 表） ──
    async def fake_audit_year(db, pid):
        return True, 2025

    monkeypatch.setattr(push, "_project_audit_year", fake_audit_year)

    # ── mock broadcast（临时 schema 内不需要 SSE） ──
    monkeypatch.setattr(push, "_broadcast", lambda result: None)

    # ── 创建临时 schema ──
    async with engine.begin() as admin:
        await admin.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text(f'SET search_path TO "{schema}", public'))

            # ── 建表 ──
            await conn.exec_driver_sql(
                "CREATE TABLE projects (id UUID PRIMARY KEY)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE wp_index ("
                "id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id), "
                "wp_code VARCHAR(50) NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT false)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE working_paper ("
                "id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id), "
                "wp_index_id UUID NOT NULL REFERENCES wp_index(id), "
                "status VARCHAR(50) NOT NULL DEFAULT 'draft', "
                "is_deleted BOOLEAN NOT NULL DEFAULT false)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE checklist_responses ("
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                "project_id UUID NOT NULL, "
                "wp_id UUID NOT NULL REFERENCES working_paper(id), "
                "item_id VARCHAR(256) NOT NULL, "
                "remark TEXT, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "content_version INTEGER NOT NULL DEFAULT 1, "
                "UNIQUE (wp_id, item_id))"
            )
            await _run_sql_file(conn, _V169)

            # ── 种子数据 ──
            await conn.execute(sa.text(
                "INSERT INTO projects (id) VALUES (:p)"
            ), {"p": project_id})

            # K1 底稿
            await conn.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'K1')"
            ), {"i": k1_idx, "p": project_id})
            await conn.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": k1_wp, "p": project_id, "i": k1_idx})

            # D4 底稿
            await conn.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'D4')"
            ), {"i": d4_idx, "p": project_id})
            await conn.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": d4_wp, "p": project_id, "i": d4_idx})

            # K1 组合行条目（审定合计由推送引擎的 derived 规则计算）
            for item_id, remark in _k1_seed_items().items():
                await conn.execute(sa.text(
                    "INSERT INTO checklist_responses (project_id, wp_id, item_id, remark) "
                    "VALUES (:p, :w, :i, :r)"
                ), {"p": project_id, "w": k1_wp, "i": item_id, "r": remark})

            await conn.commit()

            # ── 指纹 BEFORE ──
            rows_before = (await conn.execute(sa.text(
                "SELECT wp_id, item_id, remark FROM checklist_responses ORDER BY wp_id, item_id"
            ))).all()
            fingerprint_before = _fingerprint(rows_before)

            # ── 推送（事务内） ──
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                result = await push.run_and_commit(
                    session, project_id=project_id, year=2025, trigger="manual",
                )

                # ── 读取推送后的条目 ──
                rows_after_push = (await conn.execute(sa.text(
                    "SELECT wp_id, item_id, remark FROM checklist_responses ORDER BY wp_id, item_id"
                ))).all()

                # ── 读取运行记录 ──
                run_row = (await conn.execute(sa.text(
                    "SELECT status, detail FROM formula_push_run ORDER BY started_at DESC LIMIT 1"
                ))).one()

                # ── 读取状态行 ──
                state_rows = (await conn.execute(sa.text(
                    "SELECT addr_id, rule_id FROM formula_push_state ORDER BY addr_id"
                ))).all()
            finally:
                await session.close()

            # ── 回滚连接（事务内试跑的核心：回滚后指纹必须恢复） ──
            await conn.rollback()

            # ── 指纹 AFTER ROLLBACK ──
            rows_after_rollback = (await conn.execute(sa.text(
                "SELECT wp_id, item_id, remark FROM checklist_responses ORDER BY wp_id, item_id"
            ))).all()
            fingerprint_after_rollback = _fingerprint(rows_after_rollback)

            return {
                "result": result,
                "fingerprint_before": fingerprint_before,
                "fingerprint_after_rollback": fingerprint_after_rollback,
                "rows_after_push": [
                    (str(r[0]), str(r[1]), r[2]) for r in rows_after_push
                ],
                "run_status": run_row[0],
                "run_detail": run_row[1],
                "state_addrs": [(str(r[0]), str(r[1])) for r in state_rows],
                "k1_wp": str(k1_wp),
                "d4_wp": str(d4_wp),
            }
    finally:
        async with engine.begin() as admin:
            await admin.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


# ══════════════════════════════════════════════════════════════════════════
#  测试
# ══════════════════════════════════════════════════════════════════════════


def test_k1_d4_canary_real_pg(monkeypatch):
    """K1 + D4 canary 真 PG 事务内试跑：推送后值正确，回滚后指纹逐字恢复。"""
    snap = asyncio.run(_scenario(monkeypatch))
    result = snap["result"]

    # ── 运行状态 ──
    # K1 + D4 都应成功（非 partial / failed）
    assert result.status in ("succeeded", "ok"), f"运行状态异常：{result.status}"
    wp_codes_in_run = [w["wp_code"] for w in result.workpapers]
    assert "K1" in wp_codes_in_run, "运行记录缺 K1"
    assert "D4" in wp_codes_in_run, "运行记录缺 D4"
    for wp in result.workpapers:
        if wp["wp_code"] in ("K1", "D4"):
            assert wp["status"] == "pushed", f"{wp['wp_code']} 状态异常：{wp['status']}"

    # ── D4 两条锚点值 ──
    d4_items = {
        r[1]: r[2] for r in snap["rows_after_push"]
        if r[0] == snap["d4_wp"]
    }
    assert d4_items.get("D4-1-adj-tb-6001") == "2000000", (
        f"D4 6001 期末余额推送值错误：{d4_items.get('D4-1-adj-tb-6001')!r}"
    )
    assert d4_items.get("D4-1-adj-tb-6051") == "300000", (
        f"D4 6051 期末余额推送值错误：{d4_items.get('D4-1-adj-tb-6051')!r}"
    )

    # ── K1 审定合计 3 键 ──
    # receivable = 115 + 230 + 50 + 40 = 435
    # baddebt = 11 + 23 + 5 + 4 = 43
    # net = 435 - 43 = 392
    k1_items = {
        r[1]: r[2] for r in snap["rows_after_push"]
        if r[0] == snap["k1_wp"]
    }
    assert k1_items.get("K1-1-audited-receivable") == "435", (
        f"K1 receivable 审定合计错误：{k1_items.get('K1-1-audited-receivable')!r}"
    )
    assert k1_items.get("K1-1-audited-baddebt") == "43", (
        f"K1 baddebt 审定合计错误：{k1_items.get('K1-1-audited-baddebt')!r}"
    )
    assert k1_items.get("K1-1-audited-net") == "392", (
        f"K1 net 审定合计错误：{k1_items.get('K1-1-audited-net')!r}"
    )

    # ── 运行记录（真 PG） ──
    assert snap["run_status"] == "succeeded"
    detail_wp = snap["run_detail"].get("wp", [])
    detail_wp_codes = [w["wp_code"] for w in detail_wp]
    assert "K1" in detail_wp_codes
    assert "D4" in detail_wp_codes

    # ── 状态行（K1 3 + D4 2 = 5） ──
    state_rule_prefixes = {addr[1].split(".")[0] for addr in snap["state_addrs"]}
    assert "K1" in state_rule_prefixes, "缺 K1 状态行"
    assert "D4" in state_rule_prefixes, "缺 D4 状态行"
    k1_states = [a for a in snap["state_addrs"] if a[1].startswith("K1.")]
    d4_states = [a for a in snap["state_addrs"] if a[1].startswith("D4.")]
    assert len(k1_states) == 3, f"K1 应有 3 条状态行，实际 {len(k1_states)}"
    assert len(d4_states) == 2, f"D4 应有 2 条状态行，实际 {len(d4_states)}"

    # ── 🔑 回滚后指纹逐字相同 ──
    assert snap["fingerprint_before"] == snap["fingerprint_after_rollback"], (
        "回滚后指纹与推送前不一致！\n"
        f"  推送前行数：{len(snap['fingerprint_before'])}\n"
        f"  回滚后行数：{len(snap['fingerprint_after_rollback'])}"
    )
