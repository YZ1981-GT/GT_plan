"""公式推送端到端：四表入库 / 调整分录审批 → 试算表重算 → 事件 → 引擎（真实取数）→ 底稿 → 附注。

spec: chain-closure-phase2-formula-push-engine · 任务 15 · 需求 4.1~4.6 / 7.1

与 ``test_formula_push_engine.py`` 分工：那边把 ``E1Binding.load_sources`` 换成固定源，只测判定与写入；
本文件**恢复真实取数** ``load_e1_sources``（→ ``_build_four_table_extraction(strict=True)`` → tb_balance /
tb_aux_balance / ledger_datasets；``load_tb_audited`` → trial_balance；``adj_net_batch`` → adjustments），
试算表用真 ``TrialBalanceService.full_recalc`` 重算，从事件 handler（``on_trial_balance_updated`` /
``on_workpaper_saved``）进入。这段真实取数链路此前只被 mock 过，本文件是它第一次被真实执行。

SQLite 与生产（PG）的已知差异，如实断言而非回避：
- 本文件不造 ``account_chart``：语义科目定位对它走裸 SQL（uuid 传带横线形态、ORM 存 32 位 hex，互不命中；
  反解映射还用 ``ANY`` / ``unnest`` 等 PG 语法），SQLite 下造了也取不到 ⇒ 定位落在「科目表不可用」兜底层
  （标准码 1001 / 1002 / 1012），运行记录带该告警。按客户科目表名称定位的真实路径由任务 16 真库试跑覆盖；
- ``ledger_datasets`` 查询失败时 strict 取数上抛 = 推送失败（``test_dataset_lookup_failure_fails_the_push``）。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.core import database
from app.models.audit_platform_models import (
    AccountCategory, AccountChart, AccountMapping, Adjustment, AdjustmentEntry, AdjustmentType, MappingType,
    ReviewStatus, TbAuxBalance, TbBalance, TrialBalance,
)
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.core import Project
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.models.formula_push_models import FormulaPushState
from app.services.event_bus import event_bus
from app.services.formula_push import panel, triggers
from app.services.formula_push.bindings import e1_calc
from app.services.formula_push.bindings.e1 import E1_ACCOUNT_CODES, E1Binding, load_e1_sources
from app.services.formula_push.sources import load_hall_adjustments, load_tb_audited
from app.services.report_engine import ReportFormulaParser
from app.services.trial_balance_service import TrialBalanceService
from tests._formula_push_env import YEAR, by_addr, make_env

LEDGER = (LedgerDataset, TbBalance, TbAuxBalance, AccountChart, AccountMapping)
ADJUSTMENTS = (TrialBalance, Adjustment, AdjustmentEntry)
NAMES = {"1001": "库存现金", "1001.01": "人民币", "1002": "银行存款", "1002.01": "银行存款-本部",
         "1012": "其他货币资金", "1012.02": "其他货币资金_银行承兑汇票保证金", "101202": "银行本票存款",
         "1003": "存放中央银行款项"}
CHART_FALLBACK = "本项目科目表不可用，货币资金科目按标准科目编码兜底定位"
ICBC, CCB = "6222000001", "6217000002"

NOTE_COLS = [
    {"key": "label", "flat": True, "label": "项目", "is_label": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "上年年末余额", "format": "amount"},
]


def generated_note(cash_label: str = "库存现金") -> dict:
    """附注模块生成、尚未同步过的货币资金主表（底稿来源 F2，全 0）。"""
    labels = [cash_label, "银行存款", "存放财务公司款项", "其他货币资金"]
    rows = [{"label": label, "end_amount": 0, "prior_amount": 0} for label in labels]
    rows += [{"label": "合计", "is_total": True, "end_amount": 0, "prior_amount": 0},
             {"label": "其中：存放在境外的款项总额", "end_amount": 0, "prior_amount": 0}]
    return {"_source": "workpaper", "_sub_table_columns": {"货币资金": NOTE_COLS}, "sub_table_data": {"货币资金": rows}}


def note_rows(note) -> dict[str, dict]:
    return {r["label"]: r for r in note.table_data["sub_table_data"]["货币资金"]}


def cash_default_row() -> str:
    """composable ``createDefaultRmbRow`` 的占位行（先打开底稿、后导入四表的项目都有）。"""
    return json.dumps([{"id": "fixed-rmb", "currency": "人民币", "opening": 0, "increase": 0, "decrease": 0,
                        "fxRate": 1, "adjustment": 0, "note": ""}], ensure_ascii=False)


def account_row(no: str, opening, increase, decrease) -> dict:
    """E1-3 账户级种子行（前端 ``buildBankSeedRowsFromAccounts`` 的 id 口径）。"""
    return {"id": f"bank-principal-institution-acct-{no}", "section": "principal", "group": "institution",
            "opening": opening, "increase": increase, "decrease": decrease, "fxCurrency": "人民币", "fxRate": 1}


def rows_by_id(raw: str) -> dict[str, dict]:
    return {r["id"]: r for r in json.loads(raw)}


def num(raw) -> float:
    return float(raw)


# ── 造数：四表入库 / 调整分录 / 试算表重算 / 事件 ──────────────────────────────


def _balance(env, ds_id, code: str, opening, debit, credit) -> TbBalance:
    return TbBalance(
        project_id=env.pid, year=YEAR, company_code="001", account_code=code, account_name=NAMES[code],
        level=code.count(".") + 1, opening_balance=opening, debit_amount=debit, credit_amount=credit,
        closing_balance=opening + debit - credit, currency_code="CNY", dataset_id=ds_id,
        opening_direction="debit", closing_direction="debit",
    )


async def import_ledger(env, leaves, *, accounts=(), status=DatasetStatus.active, register=True) -> uuid.UUID:
    """一次四表入库：新数据集（激活时旧 active → superseded）+ 余额表父子行 + 辅助余额表银行账户行。

    ``leaves``：``{叶子码: (期初, 借方, 贷方)}``，父行 = 其叶子之和；``accounts``：``[(科目, 账号, 期初, 借, 贷)]``。
    ``register=False``：只写余额行、不登记数据集（``ledger_datasets`` 缺表的场景）。
    """
    ds_id = uuid.uuid4()
    async with env.factory() as db:
        if register and status == DatasetStatus.active:
            await db.execute(sa.update(LedgerDataset).where(
                LedgerDataset.project_id == env.pid, LedgerDataset.status == DatasetStatus.active,
            ).values(status=DatasetStatus.superseded))
        if register:
            db.add(LedgerDataset(id=ds_id, project_id=env.pid, year=YEAR, status=status, source_type="import",
                                 activated_at=datetime.now(timezone.utc) if status == DatasetStatus.active else None))
        parents: dict[str, list] = {}
        for code, amounts in leaves.items():
            amounts = [Decimal(str(a)) for a in amounts]
            db.add(_balance(env, ds_id, code, *amounts))
            acc = parents.setdefault(code.split(".")[0], [Decimal("0")] * 3)
            parents[code.split(".")[0]] = [a + b for a, b in zip(acc, amounts)]
        for code, amounts in parents.items():
            db.add(_balance(env, ds_id, code, *amounts))
        for code, no, *amounts in accounts:
            o, d, c = (Decimal(str(a)) for a in amounts)
            db.add(TbAuxBalance(
                project_id=env.pid, year=YEAR, company_code="001", account_code=code, account_name=NAMES[code],
                aux_type="银行账户", aux_code=no, aux_name=no, aux_dimensions_raw=f"金融机构:B{no[-2:]},开户行{no[-2:]};银行账户:{no}",
                opening_balance=o, debit_amount=d, credit_amount=c, closing_balance=o + d - c,
                currency_code="CNY", dataset_id=ds_id,
            ))
        await db.commit()
    return ds_id


async def map_accounts(env) -> None:
    """科目映射（四表入库后 auto_match 的产物）：一级客户科目 → 标准科目，叶子按最长前缀继承。"""
    async with env.factory() as db:
        for code in ("1001", "1002"):
            db.add(AccountMapping(project_id=env.pid, original_account_code=code, original_account_name=NAMES[code],
                                  standard_account_code=code, mapping_type=MappingType.auto_exact))
        await db.commit()


async def add_aje(env, code: str, amount, *, status=ReviewStatus.approved, origin: str = "manual") -> uuid.UUID:
    """一笔 AJE：借 ``code`` / 贷 6603（两条明细行，与大厅录入同形）。"""
    adj_id, group = uuid.uuid4(), uuid.uuid4()
    amount = Decimal(str(amount))
    async with env.factory() as db:
        db.add(Adjustment(
            id=adj_id, project_id=env.pid, year=YEAR, company_code="001", adjustment_no=f"AJE-{adj_id.hex[:6]}",
            adjustment_type=AdjustmentType.aje, account_code=code, account_name=NAMES[code], entry_group_id=group,
            review_status=status, origin=origin, created_by=uuid.uuid4(),
            source_ref=f"{env.wp_id}:E1-adjustment-entries" if origin == "workpaper" else None,
        ))
        for line_no, (line_code, name, debit, credit) in enumerate(
            [(code, NAMES[code], amount, Decimal("0")), ("6603", "财务费用", Decimal("0"), amount)], start=1,
        ):
            db.add(AdjustmentEntry(adjustment_id=adj_id, entry_group_id=group, line_no=line_no,
                                   standard_account_code=line_code, account_name=name,
                                   debit_amount=debit, credit_amount=credit))
        await db.commit()
    return adj_id


async def approve(env, adj_id: uuid.UUID) -> None:
    async with env.factory() as db:
        await db.execute(sa.update(Adjustment).where(Adjustment.id == adj_id)
                         .values(review_status=ReviewStatus.approved))
        await db.commit()


async def recalc_tb(env) -> dict[str, TrialBalance]:
    """真 ``TrialBalanceService.full_recalc``（未审数 → 调整列 → 审定数），返回重算后的试算表行。"""
    async with env.factory() as db:
        await TrialBalanceService(db).full_recalc(env.pid, YEAR)
        await db.commit()
        rows = (await db.execute(sa.select(TrialBalance).where(TrialBalance.project_id == env.pid))).scalars()
        return {r.standard_account_code: r for r in rows}


def _no_new_failure(env, before: int) -> None:
    """handler 吞异常（事件副作用不冒泡）⇒ 必须显式核对没有新增失败通知，否则断言会指向错误的地方。"""
    new = env.failures[before:]
    assert not new, f"推送失败：{new[0].extra.get('error')}"


async def tb_updated(env, *codes: str, expect_failure: bool = False) -> None:
    """试算表重算后发布方发出的事件（四表入库重算 / 调整分录审批重算 / 审定表发布门同一事件）。"""
    before = len(env.failures)
    await triggers.on_trial_balance_updated(EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED, project_id=env.pid, year=YEAR, account_codes=list(codes) or None,
    ))
    if not expect_failure:
        _no_new_failure(env, before)


async def wp_saved(env, *item_ids: str) -> None:
    """``checklist_responses`` 批量保存成功后发布的 WORKPAPER_SAVED（与路由 ``_publish_checklist_saved`` 同载荷）。"""
    before = len(env.failures)
    await triggers.on_workpaper_saved(EventPayload(
        event_type=EventType.WORKPAPER_SAVED, project_id=env.pid, year=YEAR,
        extra={"wp_id": str(env.wp_id), "wp_code": "E1", "trigger": "checklist_response_save",
               "item_ids": list(item_ids), "atomic": True},
    ))
    _no_new_failure(env, before)


_SAVES = iter(range(1, 10_000))


async def user_saves(env, item: str, remark: str) -> None:
    """用户保存一个条目（checklist 路由同效果：写 remark、推进版本与 updated_at）。"""
    stamp = (datetime(2026, 9, 30, 9) + timedelta(seconds=next(_SAVES))).strftime("%Y-%m-%d %H:%M:%S.%f+00:00")
    async with env.factory() as db:
        hit = (await db.execute(sa.text(
            "UPDATE checklist_responses SET remark = :r, updated_at = :t, content_version = content_version + 1 "
            "WHERE wp_id = :w AND item_id = :i"
        ), {"r": remark, "t": stamp, "w": str(env.wp_id), "i": item})).rowcount
        if not hit:
            await db.execute(sa.text(
                "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at) "
                "VALUES (:id, :p, :w, :i, :r, :t)"
            ), {"id": str(uuid.uuid4()), "p": str(env.pid), "w": str(env.wp_id), "i": item, "r": remark, "t": stamp})
        await db.commit()


async def set_template(env, template_type: str | None) -> None:
    """附注模块的模板类型权威（``wizard_state.basic_info.data.template_type``；缺省 = 国企版）。"""
    async with env.factory() as db:
        project = await db.get(Project, env.pid)
        project.wizard_state = (
            None if template_type is None else {"basic_info": {"data": {"template_type": template_type}}}
        )
        await db.commit()


async def _wire(env, monkeypatch, template_type: str | None = "listed") -> None:
    """恢复真实取数；事件 handler 的独立会话指向本测试库；失败通知（sync.failed）捕获进 ``env.failures``。"""
    monkeypatch.setattr(E1Binding, "load_sources", staticmethod(load_e1_sources))
    monkeypatch.setattr(database, "async_session", env.factory)
    env.failures = []

    async def capture(payload):
        env.failures.append(payload)

    monkeypatch.setattr(event_bus, "_notify_sse", capture)
    await set_template(env, template_type)


@pytest_asyncio.fixture
async def chain(monkeypatch):
    async with make_env(monkeypatch, extra_tables=[m.__table__ for m in LEDGER + ADJUSTMENTS]) as env:
        await _wire(env, monkeypatch)
        yield env


FIRST_IMPORT = {"1001.01": (286.73, 90, 0), "1002.01": (100, 60, 30)}
FIRST_ACCOUNTS = [("1002.01", ICBC, 60, 40, 10), ("1002.01", CCB, 40, 20, 20)]
CASH_DECREASE = "E1/E1-2/E1-cash-detail-rows[fixed-rmb].decrease"


def bank_addr(no: str, field: str) -> str:
    return f"E1/E1-3/E1-bank-detail-rows[bank-principal-institution-acct-{no}].{field}"


# ── 主链：四表入库 → 试算表重算 → 推送 → 底稿 → 附注；调整分录审批 → 再推送 ──────────


@pytest.mark.asyncio
async def test_ledger_import_and_adjustment_approval_flow_through_to_workpaper_and_note(chain):
    env = chain
    # 先打开过底稿（composable 占位行 + 人民币版）、附注模块已生成上市版货币资金章节
    await env.seed_entries({e1_calc.CASH_ROWS_KEY: cash_default_row(), e1_calc.BANK_VARIANT_KEY: "rmb"})
    await env.add_note("五、1", generated_note())
    # 四表：被替代的旧版本（999）与导入中未激活的版本（5555）都不得被取到
    await import_ledger(env, {"1001.01": (999, 0, 0)})
    await import_ledger(env, FIRST_IMPORT, accounts=FIRST_ACCOUNTS)
    await import_ledger(env, {"1001.01": (5555, 0, 0)}, status=DatasetStatus.staged)
    await map_accounts(env)
    # 大厅：已批准手工 AJE 计入；底稿来源（已在 E1-5 本地调整）与草稿都不计入
    await add_aje(env, "1001", 100)
    await add_aje(env, "1001", 50, origin="workpaper")
    await add_aje(env, "1001", 7, status=ReviewStatus.draft)
    tb = await recalc_tb(env)
    assert (tb["1001"].unadjusted_amount, tb["1001"].aje_adjustment, tb["1001"].audited_amount) == (
        Decimal("376.73"), Decimal("100.00"), Decimal("476.73"))
    assert (tb["1002"].audited_amount, tb["1002"].opening_balance) == (Decimal("130.00"), Decimal("100.00"))

    await tb_updated(env)  # 全量重算（account_codes 为空）

    saved = await env.entries()
    cash = rows_by_id(saved[e1_calc.CASH_ROWS_KEY])["fixed-rmb"]
    assert (cash["opening"], cash["increase"], cash["decrease"]) == (286.73, 90, 0), "占位行按 active 数据集写入"
    assert (saved["E1-cash-detail-opening-unaudited"], saved["E1-cash-detail-total-unaudited"]) == ("286.73", "376.73")
    # 银行明细尚未建立 ⇒ 汇总取四表叶子合计（与前端种子兜底同式）；行不由后端新建
    assert e1_calc.BANK_ROWS_KEY not in saved
    assert (saved["E1-bank-detail-principal-opening-unaudited"], saved["E1-bank-detail-principal-total-unaudited"]) == (
        "100", "130")
    # 试算平衡表数 = 试算表审定数合计；大厅已确认调整只含已批准、非底稿来源
    assert (saved["E1-adj-tb-amount-ending"], saved["E1-adj-tb-amount-opening"]) == ("606.73", "386.73")
    assert saved["E1-hall-adj-cash-ending"] == "100"
    # 审定合计 = 未审 + 本地调整 + 大厅已确认调整 —— 与试算表审定数逐科目相等
    assert (saved["E1-adj-total-1001"], saved["E1-adj-total-1001-opening"]) == ("476.73", "286.73")
    assert (saved["E1-adj-total-1002"], saved["E1-adj-total-1002-opening"]) == ("130", "100")

    rows = note_rows(await env.note("五、1"))
    assert (rows["库存现金"]["end_amount"], rows["库存现金"]["prior_amount"]) == (476.73, 286.73)
    assert (rows["银行存款"]["end_amount"], rows["银行存款"]["prior_amount"]) == (130, 100)
    assert rows["合计"]["end_amount"] == pytest.approx(606.73) and rows["合计"]["prior_amount"] == pytest.approx(386.73)
    [run] = await env.runs()
    items = {i["addr_id"]: i for i in run.detail["items"] if i.get("addr_id")}
    finance = items["note://五、1/货币资金/存放财务公司款项.end"]
    assert finance["action"] == "skipped" and "本项目无此科目" in finance["reason"], "取不到值 ⇒ 附注保持原值，不写 0"
    assert (run.trigger_source, run.status) == ("TRIAL_BALANCE_UPDATED", "succeeded")
    assert CHART_FALLBACK in run.detail["warnings"]
    bank_skips = [i for i in run.detail["items"] if i["rule_id"] == "E1.bank_rows.four_table"]
    assert bank_skips and all(i["action"] == "skipped" and "尚未建立" in i["reason"] for i in bank_skips)
    [(event, payload)] = env.broadcasts
    assert event == "formula.pushed" and payload["note_sections"] == ["五、1"]
    assert e1_calc.CASH_ROWS_KEY in payload["changed_items"] and "source" in payload["stages"]

    # 调整分录审批：草稿 → 已批准 ⇒ 审批 handler 重算试算表后发 TRIAL_BALANCE_UPDATED(受影响科目)
    bank_aje = await add_aje(env, "1002", 20, status=ReviewStatus.draft)
    await approve(env, bank_aje)
    assert (await recalc_tb(env))["1002"].audited_amount == Decimal("150.00")
    await tb_updated(env, "1002", "6603")

    saved = await env.entries()
    assert (saved["E1-hall-adj-bank_principal-ending"], saved["E1-hall-adj-cash-ending"]) == ("20", "100")
    assert (saved["E1-adj-total-1002"], saved["E1-adj-tb-amount-ending"]) == ("150", "626.73")
    rows = note_rows(await env.note("五、1"))
    assert rows["银行存款"]["end_amount"] == 150 and rows["合计"]["end_amount"] == pytest.approx(626.73)
    assert [r.status for r in await env.runs()] == ["succeeded", "succeeded"]


# ── 重新导入：自动值跟随；人工改值 / 锁定值保留；派生与附注按底稿实际行 ──────────────


@pytest.mark.asyncio
async def test_reimport_follows_auto_values_and_keeps_manual_and_locked_ones(chain):
    env = chain
    await map_accounts(env)
    await import_ledger(env, FIRST_IMPORT, accounts=FIRST_ACCOUNTS)
    await recalc_tb(env)
    # 导入后打开底稿：明细行由四表带入（账户级口径）并保存
    await env.seed_entries({
        e1_calc.CASH_ROWS_KEY: json.dumps([{"id": "fixed-rmb", "currency": "人民币", "opening": 286.73,
                                            "increase": 90, "decrease": 0, "fxRate": 1, "adjustment": 0,
                                            "note": "四表取数 1001.01"}], ensure_ascii=False),
        e1_calc.BANK_VARIANT_KEY: "rmb",
        e1_calc.BANK_ROWS_KEY: json.dumps([account_row(ICBC, 60, 40, 10), account_row(CCB, 40, 20, 20)],
                                          ensure_ascii=False),
    })
    await env.add_note("五、1", generated_note())
    await tb_updated(env)
    # 与四表相同的带入值：静默采纳为自动（需求 3.3），此后随四表刷新
    states = await env.states()
    assert all(states[a].state == "auto" for a in (CASH_DECREASE, bank_addr(ICBC, "increase"), bank_addr(CCB, "increase")))

    # 用户改建行本期增加（人工）；在公式管理面板锁定现金本期减少
    bank = json.loads((await env.entries())[e1_calc.BANK_ROWS_KEY])
    bank[1]["increase"] = 25
    await user_saves(env, e1_calc.BANK_ROWS_KEY, json.dumps(bank, ensure_ascii=False))
    async with env.factory() as db:
        await panel.set_locked(db, project_id=env.pid, year=YEAR, addr_ids=[CASH_DECREASE], locked=True, user_id=None)
        await db.commit()

    # 四表重新导入（新 active 数据集）→ 试算表重算 → 推送
    await import_ledger(env, {"1001.01": (286.73, 150, 20), "1002.01": (100, 100, 30)},
                        accounts=[("1002.01", ICBC, 60, 70, 10), ("1002.01", CCB, 40, 30, 20)])
    tb = await recalc_tb(env)
    assert (tb["1001"].audited_amount, tb["1002"].audited_amount) == (Decimal("416.73"), Decimal("170.00"))
    await tb_updated(env, "1001", "1002")

    saved = await env.entries()
    cash = rows_by_id(saved[e1_calc.CASH_ROWS_KEY])["fixed-rmb"]
    assert (cash["opening"], cash["increase"], cash["decrease"]) == (286.73, 150, 0), "自动值跟随；锁定值保留"
    assert cash["note"] == "四表取数 1001.01", "用户字段不动"
    bank = rows_by_id(saved[e1_calc.BANK_ROWS_KEY])
    assert bank[f"bank-principal-institution-acct-{ICBC}"]["increase"] == 70
    assert bank[f"bank-principal-institution-acct-{CCB}"]["increase"] == 25, "人工改值保留"
    items = {i["addr_id"]: i for i in (await env.runs())[-1].detail["items"] if i.get("addr_id")}
    assert (items[bank_addr(CCB, "increase")]["action"], items[bank_addr(CCB, "increase")]["formula"]) == ("keep_manual", 30)
    assert (items[CASH_DECREASE]["action"], items[CASH_DECREASE]["formula"]) == ("keep_locked", 20)
    states = await env.states()
    assert (states[bank_addr(CCB, "increase")].state, states[CASH_DECREASE].state) == ("manual", "locked")

    # 派生值按底稿实际行（含保留的人工 / 锁定值）重算，附注跟随底稿
    assert (saved["E1-cash-detail-total-unaudited"], saved["E1-bank-detail-principal-total-unaudited"]) == (
        "436.73", "165")
    assert (saved["E1-adj-total-1001"], saved["E1-adj-total-1002"]) == ("436.73", "165")
    rows = note_rows(await env.note("五、1"))
    assert (rows["库存现金"]["end_amount"], rows["银行存款"]["end_amount"]) == (436.73, 165)
    # 试算平衡表数是系统值（取试算表 586.73）⇒ 保留的人工 / 锁定差异在审定表核对中如实暴露（底稿 601.73）
    assert saved["E1-adj-tb-amount-ending"] == "586.73"


# ── 底稿保存：审定合计 → 附注；冻结底稿不动 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_workpaper_save_recomputes_audited_totals_and_note_only(chain):
    env = chain
    await map_accounts(env)
    await import_ledger(env, FIRST_IMPORT)
    await add_aje(env, "1001", 100)
    await recalc_tb(env)
    await env.seed_entries({e1_calc.CASH_ROWS_KEY: cash_default_row(), e1_calc.BANK_VARIANT_KEY: "rmb"})
    await env.add_note("五、1", generated_note())
    await tb_updated(env)

    # E1-5 录入本地账项调整（现金期末 +10）并保存
    await user_saves(env, "E1-adjustment-by-item-cash-ending", "10")
    await wp_saved(env, "E1-adjustment-by-item-cash-ending")

    saved = await env.entries()
    assert saved["E1-adj-total-1001"] == "486.73", "审定 = 未审 376.73 + 本地 10 + 大厅已确认 100"
    rows = note_rows(await env.note("五、1"))
    assert rows["库存现金"]["end_amount"] == 486.73 and rows["合计"]["end_amount"] == pytest.approx(616.73)
    run = (await env.runs())[-1]
    assert run.trigger_source == "WORKPAPER_SAVED" and run.status == "succeeded"
    # 保存不改四表 / 试算表 / 大厅 ⇒ 源值规则不在该触发下运行
    assert run.detail["items"] and all(i["stage"] != "source" for i in run.detail["items"])
    assert saved["E1-adj-tb-amount-ending"] == "606.73", "系统值保持上次推送结果"


@pytest.mark.asyncio
async def test_frozen_workpaper_and_its_note_are_left_alone(chain):
    env = chain
    await map_accounts(env)
    await import_ledger(env, FIRST_IMPORT)
    await recalc_tb(env)
    await env.seed_entries({e1_calc.CASH_ROWS_KEY: cash_default_row()})
    await env.add_note("五、1", generated_note())
    await env.set_wp_status("review_passed")
    before = await env.entries()

    await tb_updated(env)

    assert await env.entries() == before
    assert (await env.note("五、1")).table_data == generated_note(), "冻结底稿不推，附注也不跟着动"
    [run] = await env.runs()
    assert run.written_count == 0 and run.detail["wp"][0]["status"] == "frozen"
    assert await env.states() == {}


# ── 附注章节按附注模块同一模板类型权威选取（上市 五、1 / 国企 八、1 / 缺省国企）─────────


@pytest.mark.asyncio
@pytest.mark.parametrize("template_type, section, other", [
    ("listed", "五、1", "八、1"),
    ("soe", "八、1", "五、1"),
    (None, "八、1", "五、1"),  # DisclosureEngine._get_active_template_type 缺省国企版
])
async def test_note_section_follows_note_module_template_type(chain, template_type, section, other):
    env = chain
    await set_template(env, template_type)
    await map_accounts(env)
    await import_ledger(env, FIRST_IMPORT)
    await recalc_tb(env)
    await env.seed_entries({e1_calc.CASH_ROWS_KEY: cash_default_row(), e1_calc.BANK_VARIANT_KEY: "rmb"})
    await env.add_note("五、1", generated_note())
    await env.add_note("八、1", generated_note())

    await tb_updated(env)

    assert note_rows(await env.note(section))["库存现金"]["end_amount"] == 376.73
    assert (await env.note(other)).table_data == generated_note(), "另一版附注不动"
    assert (await env.runs())[-1].detail["note_sections"] == [section]


# ── 取数失败即推送失败（strict）：不 rollback、不退化成「不按数据集过滤」────────────


@pytest.mark.asyncio
async def test_dataset_lookup_failure_fails_the_push(monkeypatch):
    """``ledger_datasets`` 查不了（缺表 / 连接断开）⇒ 本次推送失败、零写入、留失败记录并推 sync.failed。

    fail-open 口径（去掉 ``get_active_filter`` 的 strict 分支）实测：``rollback`` 撤销了已 flush 的运行记录，
    过滤退化为不按数据集 ⇒ 两个数据集的 1001.01 叶子同时进种子，``fixed-rmb`` 拿到**被替代版本**的 999；
    随后照常提交 —— 写入 18 个条目、26 条推送状态，运行记录 0 条，不推 sync.failed，却仍广播
    ``formula.pushed``（其 run_id 在库中不存在）。即：错数落库且面板与顶栏都看不到失败。
    """
    tables = [m.__table__ for m in LEDGER + ADJUSTMENTS if m is not LedgerDataset]
    async with make_env(monkeypatch, extra_tables=tables) as env:
        await _wire(env, monkeypatch)
        await import_ledger(env, {"1001.01": (999, 0, 0)}, register=False)
        await import_ledger(env, FIRST_IMPORT, register=False)
        await env.seed_entries({e1_calc.CASH_ROWS_KEY: cash_default_row()})
        before = await env.entries()

        await tb_updated(env, expect_failure=True)  # handler 不冒泡

        assert await env.entries() == before
        assert await env.states() == {}
        [run] = await env.runs()
        assert run.status == "failed" and "ledger_datasets" in run.detail["error"]
        [evt] = env.failures
        assert evt.event_type == EventType.SYNC_FAILED and evt.extra["handler"] == "公式推送"
        assert evt.extra["retry_endpoint"] == f"/api/projects/{env.pid}/formula-push/run"
        assert env.broadcasts == [], "失败不广播 formula.pushed"


# ── 试算表口径与报表引擎同源：科目及其子级标准码（前缀汇总）─────────────────────────


async def _tb_row(db, env, code: str, audited, opening) -> None:
    db.add(TrialBalance(
        project_id=env.pid, year=YEAR, company_code="001", standard_account_code=code, account_name=NAMES[code],
        account_category=AccountCategory.asset, unadjusted_amount=Decimal(str(audited)),
        audited_amount=Decimal(str(audited)), opening_balance=Decimal(str(opening)),
    ))


@pytest.mark.asyncio
async def test_tb_context_matches_report_engine_including_sub_level_codes(chain):
    """「试算平衡表数」核对的是报表货币资金行 ⇒ 取数口径必须与报表引擎 ``TB()`` 逐值相等。

    真库形态（和平药房_2024）：客户 ``1012.02`` / ``1012.03`` 映射到子级标准码 ``101202`` / ``101203``，
    试算表 ``1012`` 本行为 0、子级合计 52,475,713.77。报表按前缀汇总计入；只取本码会让审定表凭空差出这笔数。
    ``1003`` 是独立科目（存放中央银行款项），前缀 ``1001`` 不得吞掉它（``100`` 不是任何 E1 科目码的前缀）。
    """
    env = chain
    async with env.factory() as db:
        await _tb_row(db, env, "1001", 376.73, 286.73)
        await _tb_row(db, env, "1002", 130, 100)
        await _tb_row(db, env, "1012", 0, 0)
        await _tb_row(db, env, "101202", 21225713.77, 36418371.85)
        await _tb_row(db, env, "1003", 999, 999)
        await db.commit()
    await add_aje(env, "101202", 5)  # 记到子级标准码的大厅调整
    await add_aje(env, "1003", 7)

    async with env.factory() as db:
        snapshot = await load_tb_audited(db, env.pid, YEAR, E1_ACCOUNT_CODES)
        hall = await load_hall_adjustments(db, env.pid, YEAR, E1_ACCOUNT_CODES)
        report = ReportFormulaParser(db, env.pid, YEAR)  # 报表引擎审定模式的 TB() / ADJ() 取数器
        for code in E1_ACCOUNT_CODES:
            for column in ("期末余额", "年初余额"):
                assert snapshot.tb_data[code][column] == await report.resolve_tb(code, column), (code, column)
        adj = await report._get_adj_data()
    assert snapshot.tb_data["1012"]["期末余额"] == Decimal("21225713.77")
    assert hall["1012"]["aje_net"] == Decimal("5") and adj["101202"]["aje_net"] == Decimal("5")
    assert "1003" not in hall and hall.get("1001", {}).get("aje_net", Decimal("0")) == 0

    # 端到端：试算平衡表数 = 报表货币资金，E1 审定合计计入子级调整
    await env.seed_entries({e1_calc.BANK_VARIANT_KEY: "rmb"})
    await tb_updated(env)
    saved = await env.entries()
    assert num(saved["E1-adj-tb-amount-ending"]) == pytest.approx(376.73 + 130 + 21225713.77)
    assert saved["E1-hall-adj-other_mf-ending"] == "5"
