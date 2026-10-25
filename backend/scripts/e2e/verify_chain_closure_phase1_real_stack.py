# -*- coding: utf-8 -*-
"""阶段一四个根因 · 真库端到端全链验证（spec chain-closure-phase1-root-cause-fixes · task 7）。

需求 5.4：端到端验证**必须用专用测试数据**，不得污染真实项目。本脚本自建一个
临时项目、跑完全链、然后把该项目名下所有行删净（逐表核验残留为 0）。

═══ 为什么需要这一刀（变异测试之外的增量）═══

`tests/test_chain_closure_phase1.py` 的 10 个变异测试跑在 SQLite 上，且每组
**只驱动单个断点**（直接调 handler / orchestrator / 端点）。它测不到的三件事：

1. **真库的科目/准则/预设分布**：SQLite fixture 自己造 `report_config`，两边自洽；
   真库是 `listed_standalone` 258 行 + **零 enterprise**，R3 的分母只在真库成立。
2. **四个根因串起来跑**：R1 放开门禁 → R2 派生出真实预设键 → 审批 → R3 重算 → R4 标 stale，
   是一条链。单点绿不等于链通（合并模块四阶段的教训：各阶段 mock 掉相邻阶段，merge 两次咬人）。
3. **真实事件派发**：`event_bus.publish` 带 debounce，handler 各开独立 session 并 commit。
   SQLite 测试用 `StaticPool` + 直调 handler 绕过了这一层。

用法（仓库根，需 `audit-postgres` 可连，**不需要**后端进程）::

    python backend/scripts/e2e/verify_chain_closure_phase1_real_stack.py
    python backend/scripts/e2e/verify_chain_closure_phase1_real_stack.py --keep          # 保留测试数据（排障用）
    python backend/scripts/e2e/verify_chain_closure_phase1_real_stack.py --cleanup-only  # 只清上次残留

变异证明（证明上面 19 个判据不是恒真）::

    python backend/scripts/e2e/verify_chain_closure_phase1_mutation.py

退出码：0 = 全链通过；1 = 任一判据失败（失败也会清理，除 --keep）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

YEAR = 2025
STANDARD = "listed_standalone"          # 由 template_type='listed' + report_scope='standalone' 解析得出
MARK = "_CHAIN_P1_E2E_临时测试项目"      # 便于人工辨认/兜底清理
#: 运行期产物一律落系统临时目录，**不在仓库里留文件**（避免又多一个要记得删的 `_` 文件）
_TMP = Path(tempfile.gettempdir())
#: 造出的测试项目 id（异常中断后供 `--cleanup-only` 兜底）
IDS_FILE = _TMP / "chain_p1_e2e_ids.json"
#: 机器可读判据结果（变异驱动读它，不解析 stdout —— stdout 在 Windows 下是 gbk 解码雷区）
RESULT_FILE = _TMP / "chain_p1_e2e_result.json"

#: 造数口径：两个**资产**科目（都从 tb_balance 派生，不依赖 tb_ledger），
#: 一借一贷构成平衡分录 ⇒ 同时验证 aje 正负两个方向都正确落到审定数与报表。
AR_CODE, AR_NAME, AR_CLOSING = "1122", "应收账款", Decimal("1000000.00")
BANK_CODE, BANK_NAME, BANK_CLOSING = "1002", "银行存款", Decimal("3000000.00")
AJE_AMOUNT = Decimal("100000.00")
#: listed_standalone 里引用这两个码的报表行（现算自 report_config，非猜）：
#:   BS-006 应收账款 = TB('1122','期末余额') - TB('1231','期末余额')
#:   BS-002 货币资金 = TB('1001',..) + TB('1002',..) + TB('1012',..)
ROW_AR, ROW_BANK = "BS-006", "BS-002"

_FAILURES: list[str] = []
_CHECKS: list[tuple[bool, str, str]] = []


def import_all_models() -> int:
    """walk-import 全部 model 子模块（照抄 schema_drift_detector 的做法）。

    🔴 只 import 用到的那几个模型不够：``Project.accounting_standard_id`` 的
    ``ForeignKey("accounting_standards.id")`` 在 flush 时才解析，目标表所在模块
    （``extension_models``）没进 metadata 就抛 ``NoReferencedTableError``。
    按需逐个补 import 是打地鼠，直接全量 walk。
    """
    import importlib
    import pkgutil

    import app.models as _m

    n = 0
    for mi in pkgutil.walk_packages(_m.__path__, prefix="app.models."):
        try:
            importlib.import_module(mi.name)
            n += 1
        except Exception:  # noqa: BLE001 — 个别模块可选依赖缺失不阻断
            pass
    return n


def check(ok: bool, name: str, detail: str) -> bool:
    _CHECKS.append((ok, name, detail))
    print(f"  {'✅' if ok else '🔴'} {name}: {detail}")
    if not ok:
        _FAILURES.append(f"{name}: {detail}")
    return ok


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


# ═══════════════════════════════════════════════════════════════════════════════
# 0. 前置：真库分母（这些事实是四个根因判据的基础，必须现算而不是引用 spec 里的旧值）
# ═══════════════════════════════════════════════════════════════════════════════
async def preflight(factory) -> uuid.UUID:
    from app.models.core import User, UserRole
    from app.models.report_models import ReportConfig

    print("\n[0] 前置：真库分母现算")
    async with factory() as db:
        dist = (await db.execute(
            sa.select(ReportConfig.applicable_standard, sa.func.count())
            .group_by(ReportConfig.applicable_standard)
        )).all()
        table = {k: n for k, n in dist}
        check(
            table.get(STANDARD, 0) > 0 and table.get("enterprise", 0) == 0,
            "R3 分母",
            f"report_config: {STANDARD}={table.get(STANDARD, 0)} 行 / "
            f"enterprise={table.get('enterprise', 0)} 行（默认参数零命中才是根因）",
        )

        roles = dict((await db.execute(
            sa.select(User.role, sa.func.count())
            .where(User.is_active == sa.true()).group_by(User.role)
        )).all())
        rolemap = {(r.value if hasattr(r, "value") else str(r)): n for r, n in roles.items()}
        check(
            rolemap.get("partner", 0) == 0 and rolemap.get("admin", 0) > 0,
            "R1 分母",
            f"活跃用户按角色 {rolemap} —— 零 partner ⇒ 原白名单无人可达",
        )
        admin_id = (await db.execute(
            sa.select(User.id).where(
                User.role == UserRole.admin, User.is_active == sa.true(),
                User.username == "admin",
            ).limit(1)
        )).scalar_one_or_none()
        if admin_id is None:
            admin_id = (await db.execute(
                sa.select(User.id).where(
                    User.role == UserRole.admin, User.is_active == sa.true()
                ).limit(1)
            )).scalar_one()

        from app.services.formula_management.preset_library import build_preset_index
        idx = build_preset_index()
        rk = sorted(k for k in idx if k.startswith("report:"))
        check(
            "report:*" not in idx and len(rk) > 0,
            "R2 分母",
            f"预设库 report: 键 {len(rk)} 个，字面量 'report:*' 不在其中 ⇒ 写死即恒不命中",
        )
    return admin_id


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 造数：项目 + active 数据集 + 余额表 + 科目映射 → 真 full_recalc 出试算表
# ═══════════════════════════════════════════════════════════════════════════════
async def seed(factory, admin_id: uuid.UUID) -> uuid.UUID:
    from app.models.audit_platform_models import (
        AccountMapping, MappingType, TbBalance, TrialBalance,
    )
    from app.models.core import Project, ProjectStatus, ProjectType
    from app.models.dataset_models import DatasetStatus, LedgerDataset
    from app.services.trial_balance_service import TrialBalanceService

    pid, ds_id = uuid.uuid4(), uuid.uuid4()
    print(f"\n[1] 造测试项目 {pid}")
    async with factory() as db:
        db.add(Project(
            id=pid, name=f"{MARK}_{YEAR}", client_name=MARK,
            project_type=ProjectType.annual, status=ProjectStatus.planning,
            created_by=admin_id,
            # 准则由这两列组合解析：listed + standalone → listed_standalone
            template_type="listed", report_scope="standalone",
            audit_period_end=date(YEAR, 12, 31),
        ))
        # 🔴 必须先 flush 出 projects 行：`AccountMapping.project_id` 在 ORM 层**没有声明
        # ForeignKey**（DB 层有 account_mapping_project_id_fkey），SQLAlchemy 的 unit of work
        # 因此不知道它依赖 projects，会把 account_mapping 的 INSERT 排在 projects 之前
        # ⇒ ForeignKeyViolationError。同一个 session 里只要显式 flush 就能定序。
        await db.flush()
        db.add(LedgerDataset(
            id=ds_id, project_id=pid, year=YEAR, status=DatasetStatus.active,
            source_type="import", activated_at=datetime.now(timezone.utc),
        ))
        for code, name, closing in (
            (AR_CODE, AR_NAME, AR_CLOSING), (BANK_CODE, BANK_NAME, BANK_CLOSING)
        ):
            db.add(TbBalance(
                project_id=pid, year=YEAR, company_code="001",
                account_code=code, account_name=name, level=1,
                opening_balance=Decimal("0"), debit_amount=closing,
                credit_amount=Decimal("0"), closing_balance=closing,
                opening_direction="debit", closing_direction="debit",
                currency_code="CNY", dataset_id=ds_id,
            ))
            db.add(AccountMapping(
                project_id=pid, original_account_code=code, original_account_name=name,
                standard_account_code=code, mapping_type=MappingType.auto_exact,
            ))
        await db.commit()

    # 链条①：四表 → 试算表未审数（真 service，不手造 trial_balance 行）
    async with factory() as db:
        await TrialBalanceService(db).full_recalc(pid, YEAR)
        await db.commit()
    async with factory() as db:
        tb = {r.standard_account_code: r for r in (await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == pid, TrialBalance.year == YEAR
            )
        )).scalars()}
        check(
            money(tb[AR_CODE].unadjusted_amount) == AR_CLOSING
            and money(tb[BANK_CODE].unadjusted_amount) == BANK_CLOSING,
            "链条① 四表→试算表未审数",
            f"{AR_CODE}={money(tb[AR_CODE].unadjusted_amount)} / "
            f"{BANK_CODE}={money(tb[BANK_CODE].unadjusted_amount)}",
        )
    return pid


async def seed_reports(factory, pid: uuid.UUID) -> dict[str, Decimal]:
    """生成报表初稿（旧快照）并显式清 is_stale —— R4 的分母。"""
    from app.models.report_models import FinancialReport
    from app.services.report_engine import ReportEngine

    print("\n[2] 生成报表初稿 + 清 is_stale（R4 分母）")
    async with factory() as db:
        await ReportEngine(db).generate_all_reports(pid, YEAR, STANDARD)
        await db.commit()
    async with factory() as db:
        await db.execute(sa.update(FinancialReport).where(
            FinancialReport.project_id == pid
        ).values(is_stale=False))
        await db.commit()
        rows = (await db.execute(sa.select(FinancialReport).where(
            FinancialReport.project_id == pid, FinancialReport.year == YEAR
        ))).scalars().all()
        before = {r.row_code: money(r.current_period_amount) for r in rows}
        check(
            len(rows) > 0 and all(not r.is_stale for r in rows),
            "R4 分母",
            f"financial_report {len(rows)} 行，is_stale 全 False",
        )
        check(
            before.get(ROW_AR) == AR_CLOSING and before.get(ROW_BANK) == BANK_CLOSING,
            "报表初稿对齐审定数",
            f"{ROW_AR}={before.get(ROW_AR)} / {ROW_BANK}={before.get(ROW_BANK)}",
        )
    return before


# ═══════════════════════════════════════════════════════════════════════════════
# 2. R1 + R2：全局一键刷新入口（真发 HTTP，走真实 require_role 与预设治理层）
# ═══════════════════════════════════════════════════════════════════════════════
async def probe_draft_refresh(pid: uuid.UUID, admin_id: uuid.UUID) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.deps import get_current_user
    from app.main import app
    from app.models.core import User, UserRole

    print("\n[3] R1+R2：POST /api/workpapers/draft-refresh（scope=report）")
    body = {
        "project_id": str(pid), "year": YEAR,
        "scopes": ["report"], "transaction_mode": "partial_success",
    }

    async def _post(role: UserRole, uid: uuid.UUID | None = None):
        user = User(id=uid or uuid.uuid4(), username=f"probe_{role.value}",
                    role=role, is_active=True)
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app),
                                   base_url="http://t", timeout=180.0) as c:
                r = await c.post("/api/workpapers/draft-refresh", json=body)
                try:
                    return r.status_code, r.json()
                except Exception:
                    return r.status_code, {}
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    code_auditor, _ = await _post(UserRole.auditor)
    check(code_auditor == 403, "R1 反向断言", f"auditor → HTTP {code_auditor}（应 403，防修过头）")

    code_admin, payload = await _post(UserRole.admin, admin_id)
    check(code_admin != 403, "R1 核心", f"admin → HTTP {code_admin}（修复前实测 403）")

    # ResponseWrapperMiddleware 把 2xx JSON 包成 {code,message,data}
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    pa = (data or {}).get("preset_application") or {}
    presetted = pa.get("presetted_pages") or []
    check(
        int(pa.get("preset_count") or 0) > 0,
        "R2 核心",
        f"preset_count={pa.get('preset_count')}，presetted_pages={len(presetted)} 个"
        f"（修复前 'report:*' 恒不命中 ⇒ 恒 0）",
    )
    if presetted:
        bad = [k for k in presetted if not str(k).startswith("report:") or k == "report:*"]
        check(not bad, "R2 派生键形态", f"命中键全为具体 report: 键，异常项 {bad}")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 调整分录 → HTTP 审批 → 等链条 → R3 + R4
# ═══════════════════════════════════════════════════════════════════════════════
async def make_aje(factory, pid: uuid.UUID, admin_id: uuid.UUID) -> uuid.UUID:
    from app.models.audit_platform_models import (
        Adjustment, AdjustmentEntry, AdjustmentType, ReviewStatus,
    )

    group = uuid.uuid4()
    print(f"\n[4] 造 AJE（draft）：借 {AR_CODE} / 贷 {BANK_CODE} 各 {AJE_AMOUNT}")
    async with factory() as db:
        for code, name, dr, cr in (
            (AR_CODE, AR_NAME, AJE_AMOUNT, Decimal("0")),
            (BANK_CODE, BANK_NAME, Decimal("0"), AJE_AMOUNT),
        ):
            adj_id = uuid.uuid4()
            db.add(Adjustment(
                id=adj_id, project_id=pid, year=YEAR, company_code="001",
                adjustment_no="AJE-E2E-P1", adjustment_type=AdjustmentType.aje,
                description="chain-closure-phase1 task7 端到端验证分录",
                account_code=code, account_name=name,
                debit_amount=dr, credit_amount=cr,
                entry_group_id=group, review_status=ReviewStatus.draft,
                origin="manual", created_by=admin_id,
            ))
            db.add(AdjustmentEntry(
                adjustment_id=adj_id, entry_group_id=group, line_no=1,
                standard_account_code=code, account_name=name,
                debit_amount=dr, credit_amount=cr,
            ))
        await db.commit()
    return group


async def approve(pid: uuid.UUID, group: uuid.UUID, admin_id: uuid.UUID) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.deps import get_current_user
    from app.main import app
    from app.models.core import User, UserRole

    print("\n[5] HTTP 审批：draft → pending_review → approved")
    user = User(id=admin_id, username="admin", role=UserRole.admin, is_active=True)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://t", timeout=180.0) as c:
            for status in ("pending_review", "approved"):
                r = await c.post(
                    f"/api/projects/{pid}/adjustments/{group}/review",
                    json={"status": status},
                )
                check(r.status_code == 200, f"审批 → {status}",
                      f"HTTP {r.status_code} {r.text[:120]}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def wait_chain(factory, pid: uuid.UUID, before: dict[str, Decimal],
                     timeout_s: float = 60.0) -> dict:
    """轮询等 debounce + 各 handler 独立 session commit 落地。"""
    from app.models.audit_platform_models import TrialBalance
    from app.models.report_models import FinancialReport

    print(f"\n[6] 等事件链落地（最长 {timeout_s:.0f}s，publish 带 debounce）")
    want_ar = AR_CLOSING + AJE_AMOUNT
    want_bank = BANK_CLOSING - AJE_AMOUNT
    deadline = asyncio.get_running_loop().time() + timeout_s
    snap: dict = {}
    while True:
        async with factory() as db:
            tb = {r.standard_account_code: r for r in (await db.execute(
                sa.select(TrialBalance).where(
                    TrialBalance.project_id == pid, TrialBalance.year == YEAR
                )
            )).scalars()}
            fr = (await db.execute(sa.select(FinancialReport).where(
                FinancialReport.project_id == pid, FinancialReport.year == YEAR
            ))).scalars().all()
        snap = {
            "tb": {c: (money(r.unadjusted_amount), money(r.aje_adjustment),
                       money(r.rje_adjustment), money(r.audited_amount))
                   for c, r in tb.items()},
            "reports": {r.row_code: money(r.current_period_amount) for r in fr},
            "stale": sum(1 for r in fr if r.is_stale),
            "report_n": len(fr),
        }
        done = (
            snap["tb"].get(AR_CODE, (0, 0, 0, 0))[3] == want_ar
            and snap["reports"].get(ROW_AR) == want_ar
            and snap["reports"].get(ROW_BANK) == want_bank
            and snap["stale"] == snap["report_n"]
        )
        if done or asyncio.get_running_loop().time() > deadline:
            break
        await asyncio.sleep(1.5)
    return snap


def assert_chain(before: dict[str, Decimal], snap: dict) -> None:
    want_ar = AR_CLOSING + AJE_AMOUNT
    want_bank = BANK_CLOSING - AJE_AMOUNT

    print("\n[7] 判据")
    tb_ar = snap["tb"].get(AR_CODE)
    tb_bank = snap["tb"].get(BANK_CODE)
    check(
        tb_ar is not None and tb_ar[1] == AJE_AMOUNT and tb_bank[1] == -AJE_AMOUNT,
        "链条⑧ 审批→TB 调整列",
        f"{AR_CODE}.aje={tb_ar[1]} / {BANK_CODE}.aje={tb_bank[1]}"
        f"（借方类 +，贷记同为借方类 − ⇒ 方向归一正确）",
    )
    check(
        tb_ar[3] == tb_ar[0] + tb_ar[1] + tb_ar[2]
        and tb_bank[3] == tb_bank[0] + tb_bank[1] + tb_bank[2],
        "不变式 audited=未审+aje+rje",
        f"{AR_CODE}: {tb_ar[3]} / {BANK_CODE}: {tb_bank[3]}",
    )
    check(
        snap["reports"].get(ROW_AR) == want_ar
        and snap["reports"].get(ROW_BANK) == want_bank,
        "R3 核心 链条⑦ →报表审定数",
        f"{ROW_AR}: {before.get(ROW_AR)} → {snap['reports'].get(ROW_AR)}（期望 {want_ar}）; "
        f"{ROW_BANK}: {before.get(ROW_BANK)} → {snap['reports'].get(ROW_BANK)}（期望 {want_bank}）"
        f" —— 修复前 handler 走默认 'enterprise' 零命中 ⇒ 两值均不动",
    )
    # 🔴 判据必须是「该项目该年度**全部**行被标」而不是「stale > 0」：变异实测（把 R4 那段
    #    切掉后重跑）得 **2/258** —— 另有一条 REPORT_ROW_CHANGED 侧的传播路径会零星标到
    #    2 行。若判据写成 `stale > 0`，缺陷态也会绿。
    check(
        snap["report_n"] > 0 and snap["stale"] == snap["report_n"],
        "R4 核心 stale 落到 financial_report",
        f"{snap['stale']}/{snap['report_n']} 行 is_stale=True"
        f"（切掉 R4 那段重跑实测只有 2/{snap['report_n']}，其余 256 行静默陈旧）",
    )
    untouched = [c for c, v in snap["reports"].items()
                 if c not in (ROW_AR, ROW_BANK) and v != before.get(c)]
    check(
        not untouched,
        "增量重算不波及无关行",
        f"未引用变更科目的报表行零改动（异常 {len(untouched)} 行：{untouched[:5]}）",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 清理：该项目名下所有行删净，逐表核验残留 0
# ═══════════════════════════════════════════════════════════════════════════════
async def cleanup(factory, pid: uuid.UUID) -> bool:
    print(f"\n[8] 清理测试数据 project={pid}")
    async with factory() as db:
        tables = [r[0] for r in (await db.execute(sa.text("""
            SELECT c.table_name FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public' AND c.column_name = 'project_id'
              AND t.table_type = 'BASE TABLE'
            ORDER BY c.table_name
        """))).all()]

    # adjustment_entries 无 project_id，经 adjustment_id 关联
    async with factory() as db:
        await db.execute(sa.text(
            "DELETE FROM adjustment_entries WHERE adjustment_id IN "
            "(SELECT id FROM adjustments WHERE project_id = :p)"
        ), {"p": str(pid)})
        await db.commit()

    pending = list(tables)
    for _pass in range(6):
        stuck: list[str] = []
        for t in pending:
            async with factory() as db:
                try:
                    await db.execute(
                        sa.text(f'DELETE FROM "{t}" WHERE project_id = :p'), {"p": str(pid)}
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    stuck.append(t)
        pending = stuck
        if not pending:
            break

    async with factory() as db:
        residual: dict[str, int] = {}
        for t in tables:
            try:
                n = (await db.execute(
                    sa.text(f'SELECT count(*) FROM "{t}" WHERE project_id = :p'),
                    {"p": str(pid)},
                )).scalar_one()
            except Exception:
                await db.rollback()
                continue
            if n:
                residual[t] = n
        ae = (await db.execute(sa.text(
            "SELECT count(*) FROM adjustment_entries ae JOIN adjustments a "
            "ON a.id = ae.adjustment_id WHERE a.project_id = :p"
        ), {"p": str(pid)})).scalar_one()
        if ae:
            residual["adjustment_entries"] = ae

    async with factory() as db:
        try:
            await db.execute(sa.text("DELETE FROM projects WHERE id = :p"), {"p": str(pid)})
            await db.commit()
        except Exception as e:
            await db.rollback()
            residual["projects"] = -1
            print(f"  🔴 删 projects 失败: {type(e).__name__}: {e}")

    async with factory() as db:
        left = (await db.execute(
            sa.text("SELECT count(*) FROM projects WHERE id = :p"), {"p": str(pid)}
        )).scalar_one()
    ok = not residual and left == 0
    check(ok, "测试数据删净",
          "零残留" if ok else f"残留 {residual}，projects 行 {left}（须人工清理）")
    if ok and IDS_FILE.exists():
        IDS_FILE.unlink()
    return ok


async def cleanup_only(factory) -> int:
    """只清上次残留（--cleanup-only）：先读 ids 文件，再按项目名兜底。"""
    from app.models.core import Project

    pids: list[uuid.UUID] = []
    if IDS_FILE.exists():
        try:
            pids.append(uuid.UUID(json.loads(IDS_FILE.read_text("utf-8"))["project_id"]))
        except Exception:
            pass
    async with factory() as db:
        for r in (await db.execute(
            sa.select(Project.id).where(Project.name.like(f"{MARK}%"))
        )).scalars():
            if r not in pids:
                pids.append(r)
    if not pids:
        print("无残留测试项目")
        return 0
    allok = True
    for p in pids:
        allok = await cleanup(factory, p) and allok
    return 0 if allok else 1


# ═══════════════════════════════════════════════════════════════════════════════
async def amain(args) -> int:
    from app.core.database import async_session as factory
    from app.services.event_bus import event_bus
    from app.services.event_handlers import register_event_handlers

    print(f"[init] 已 import {import_all_models()} 个 model 子模块")

    if args.cleanup_only:
        return await cleanup_only(factory)

    # 真实启动期做的 handler 注册（脚本不跑 lifespan，须显式注册）
    register_event_handlers()
    from app.services.adjustment_approved_recalc_handler import (
        register_adjustment_approved_recalc_handler,
    )
    register_adjustment_approved_recalc_handler(event_bus)
    from app.models.audit_platform_schemas import EventType
    names = {getattr(h, "__name__", "?")
             for h in event_bus._handlers.get(EventType.ADJUSTMENT_APPROVED, [])}
    check(
        "_mark_reports_stale_on_adjustment" in names
        and "handle_adjustment_approved" in names,
        "handler 已注册",
        f"ADJUSTMENT_APPROVED 订阅者 {sorted(names)}",
    )

    admin_id = await preflight(factory)
    pid = await seed(factory, admin_id)
    IDS_FILE.write_text(json.dumps({"project_id": str(pid)}, ensure_ascii=False), "utf-8")
    try:
        before = await seed_reports(factory, pid)
        await probe_draft_refresh(pid, admin_id)
        group = await make_aje(factory, pid, admin_id)
        await approve(pid, group, admin_id)
        snap = await wait_chain(factory, pid, before)
        assert_chain(before, snap)
    finally:
        if args.keep:
            print(f"\n[8] --keep：保留测试项目 {pid}（记于 {IDS_FILE}）")
        else:
            await cleanup(factory, pid)

    ok_n = sum(1 for ok, _, _ in _CHECKS if ok)
    print(f"\n{'=' * 72}\n判据 {ok_n}/{len(_CHECKS)} 通过")
    for f in _FAILURES:
        print(f"  🔴 {f}")
    RESULT_FILE.write_text(json.dumps(
        {"passed": ok_n, "total": len(_CHECKS),
         "checks": [{"ok": ok, "name": n, "detail": d} for ok, n, d in _CHECKS]},
        ensure_ascii=False, indent=1,
    ), "utf-8")
    return 0 if not _FAILURES else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留测试数据（排障用）")
    ap.add_argument("--cleanup-only", action="store_true", help="只清上次残留")
    return asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
