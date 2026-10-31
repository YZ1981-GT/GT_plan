#!/usr/bin/env python
"""利润表归属行存量升级：默认只读逐行列出旧值 / 目标 / 动作，``--apply`` 经同步内核发布。

spec formula-hub-integrity-closure（需求 6.6，ADR-FHIC-23，决策项 X2）。四套准则利润表的归属行（国企两套 IS-074 / IS-075、
上市两套 IS-051 / IS-052，共 8 行）在已有库里是首版 ``_generate_sum_formula`` 直写的 ``SUM_ROW`` 区间（区间含其他合计行，
原文见 :data:`KNOWN_BAD`）。种子已按需求 6.1 写成显式公式，但种子加载不覆盖已有行 ⇒ 已有库只能经本工具发布。

目标（需求 6.1）：国企两套 IS-074 = IS-048 + IS-054；合并 IS-075 = IS-049 + IS-072；单体 IS-075 无公式；上市两套
IS-051 = IS-029 + IS-032；合并 IS-052 = IS-030 + IS-049；单体 IS-052 无公式。本文件按行名写成 :data:`ATTRIBUTION`；
运行时在本准则利润表（未删的准则行）里按行名定位合计行与组成行，目标公式 = 组成行 ``ROW('行次')`` 按需求顺序相加。
行名找不到或不唯一、合计行定位到的行次与 :data:`KNOWN_BAD` 不符 ⇒ 退出码 2，不写。

逐行动作（:func:`classify`）：
- 已是目标：公式去首尾空白后 = 目标（单体两条：无公式或空白）⇒ 不动；
- 待升级：公式逐字等于 :data:`KNOWN_BAD` 的对应文本 ⇒ ``--apply`` 时发布；
- 旧值不符跳过：两者都不是 ⇒ 不动，在报告里列出（其余照常）。

``--apply``（一个事务）：取报表域发布锁（与 ``publish_global`` 同一把，先取以免与并发发布互等）→ ``SELECT … FOR UPDATE``
锁住 8 行 → 按锁定后的值重判动作 → 每个有待升级行的准则调一次 ``publish_global(domain="report", scope=<准则>,
source="seed", request_id="seed-upgrade-is-attribution-<准则>")``（定义只给 ``formula``，其余字段按补丁语义沿用现值；
``expected_version`` = 锁定时的版本）→ 复读核对 → 提交。受影响报表行标过期由 ``publish_global`` 在同一事务内完成
（ADR-FHIC-04：跟随全局的项目，这些行及经 ``ROW`` / ``SUM_ROW`` 引用它们的行，全部年度）；工具不发公式变更事件、不调报表
重算（决策项 X3）。可重复执行：第二次全部「已是目标」、不调 ``publish_global``、0 写入。同 request_id 的发布记录已存在而行
又是已知坏式（发布之后被改回）时，``publish_global`` 按幂等重放返回、不写入 ⇒ 工具报错退出 1（不另起 request_id）。

用法（目标库 = ``settings.DATABASE_URL``，与应用同一来源，输出第一行打印库名）::

    python backend/scripts/fix/republish_report_seed_rows.py                    # 只读（只读事务），逐行列出
    python backend/scripts/fix/republish_report_seed_rows.py --json out.json    # 另存完整报告
    python backend/scripts/fix/republish_report_seed_rows.py --apply            # 发布（决策项 X2）

退出码：0 完成（只读列出，或 ``--apply`` 已提交；全部已是目标 = 0 变更也是 0）；1 升级失败（连不上库、数据库错误、版本冲突、
同 request_id 幂等重放、发布后复读不是目标；已回滚）；2 参数缺失或非法、库不是 PostgreSQL、按行名定位不到（都在写入之前，
未做任何修改）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, NoReturn, Sequence

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.models.formula_setting_models import FormulaPublish  # noqa: E402
from app.models.report_models import FinancialReportType, ReportConfig  # noqa: E402
from app.services.formula_settings.engine import lock_domain  # noqa: E402
from app.services.formula_settings.publish import publish_global  # noqa: E402

TOOL = "republish_report_seed_rows"
DOMAIN = "report"
REPORT_TYPE = FinancialReportType.income_statement
REQUEST_ID_PREFIX = "seed-upgrade-is-attribution-"
PUBLISH_NOTE = "存量升级：利润表归属行按需求 6.1 改写（republish_report_seed_rows.py，决策项 X2）"
STANDARDS = ("soe_consolidated", "soe_standalone", "listed_consolidated", "listed_standalone")
ACTION_PENDING = "待升级"
ACTION_ALREADY = "已是目标"
ACTION_MISMATCH = "旧值不符跳过"
ACTIONS = (ACTION_PENDING, ACTION_ALREADY, ACTION_MISMATCH)
NO_FORMULA = "（无公式）"

#: 每套准则 × 行次的精确旧公式。取自快照库 fh_snap_202610270028（共享库 audit_platform 2026-10-27 00:28 的副本）的只读查询
#: （2026-10-28，spec 任务 18 第一段 A ``probes/task18a_snap_rows.py``，SQL 包在 BEGIN TRANSACTION READ ONLY … ROLLBACK）：
#:   SELECT applicable_standard, row_code, formula FROM report_config
#:    WHERE is_deleted = false AND report_type = 'income_statement'
#:      AND ((applicable_standard IN ('soe_consolidated', 'soe_standalone') AND row_code IN ('IS-074', 'IS-075'))
#:        OR (applicable_standard IN ('listed_consolidated', 'listed_standalone') AND row_code IN ('IS-051', 'IS-052')))
#: 8 行都是 formula_source = 'auto_total'、formula_version = 1（首版生成器直写）。2026-10-28 任务 19 对共享库 audit_platform
#: 以同一条件只读核对一次（BEGIN TRANSACTION READ ONLY … ROLLBACK）：8 行公式与下列文本逐字相同，版本仍为 1。
KNOWN_BAD: dict[tuple[str, str], str] = {
    ("soe_consolidated", "IS-074"): "SUM_ROW('IS-001','IS-073')",
    ("soe_consolidated", "IS-075"): "SUM_ROW('IS-001','IS-074')",
    ("soe_standalone", "IS-074"): "SUM_ROW('IS-001','IS-073')",
    ("soe_standalone", "IS-075"): "SUM_ROW('IS-001','IS-074')",
    ("listed_consolidated", "IS-051"): "SUM_ROW('IS-031','IS-050')",
    ("listed_consolidated", "IS-052"): "SUM_ROW('IS-031','IS-051')",
    ("listed_standalone", "IS-051"): "SUM_ROW('IS-031','IS-050')",
    ("listed_standalone", "IS-052"): "SUM_ROW('IS-031','IS-051')",
}

_SOE_PARENT = ("IS-074", "归属于母公司所有者的综合收益总额",
               ("1.归属于母公司所有者的净利润", "归属于母公司所有者的其他综合收益的税后净额"))
_SOE_MINOR = ("IS-075", "*归属于少数股东的综合收益总额",
              ("*2.少数股东损益", "*归属于少数股东的其他综合收益的税后净额"))
_LISTED_PARENT = ("IS-051", "归属于母公司股东的综合收益总额",
                  ("其中：归属于母公司股东的净利润（净亏损以“-”号填列）", "归属于母公司股东的其他综合收益的税后净额"))
_LISTED_MINOR = ("IS-052", "归属于少数股东的综合收益总额",
                 ("少数股东损益（净亏损以“-”号填列）", "归属于少数股东的其他综合收益的税后净额"))
#: 需求 6.1（唯一权威文本）按行名：准则 → ((合计行次, 合计行名, (组成行名, …) 或 None = 无公式), …)
ATTRIBUTION: dict[str, tuple[tuple[str, str, tuple[str, ...] | None], ...]] = {
    "soe_consolidated": (_SOE_PARENT, _SOE_MINOR),
    "soe_standalone": (_SOE_PARENT, (*_SOE_MINOR[:2], None)),
    "listed_consolidated": (_LISTED_PARENT, _LISTED_MINOR),
    "listed_standalone": (_LISTED_PARENT, (*_LISTED_MINOR[:2], None)),
}


class TargetUnresolved(RuntimeError):
    """按行名定位不到（找不到 / 不唯一 / 合计行行次与 KNOWN_BAD 不符）：退出码 2，不写。"""


class UpgradeReplayed(RuntimeError):
    """同 request_id 的发布记录已存在而行仍是已知坏式：``publish_global`` 幂等重放、未写入（调用方回滚）。"""


class UpgradeMismatch(RuntimeError):
    """锁定时缺行，或发布后复读不是目标（调用方回滚）。"""


class ArgumentProblem(ValueError):
    """命令行参数缺失或非法：退出码 2，未连接数据库。"""


@dataclass(frozen=True)
class Target:
    standard: str
    row_code: str
    row_name: str
    formula: str | None  # None = 无公式
    parts: tuple[str, ...]
    known_bad: str


@dataclass(frozen=True)
class CurrentRow:
    row_id: uuid.UUID
    standard: str
    row_code: str
    row_name: str
    formula: str | None
    version: int


@dataclass(frozen=True)
class RowPlan:
    standard: str
    row_code: str
    row_name: str
    old: str | None
    target: str | None
    action: str
    version: int

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


def request_id_for(standard: str) -> str:
    return f"{REQUEST_ID_PREFIX}{standard}"


def slot_key(row_code: str) -> str:
    return f"{REPORT_TYPE.value}:{row_code}"


def resolve_targets(name_rows: Iterable[tuple[str, str, str]]) -> dict[tuple[str, str], Target]:
    """``name_rows`` =（准则, 行次, 行名），只含利润表未删的准则行；按 :data:`ATTRIBUTION` 的行名定位 → 8 行目标。

    任何一处找不到 / 不唯一 / 合计行行次与 :data:`KNOWN_BAD` 不符都收集起来，一次抛 :class:`TargetUnresolved`。
    """
    codes_by_name: dict[str, dict[str, list[str]]] = {}
    for standard, code, name in name_rows:
        codes_by_name.setdefault(standard, {}).setdefault(name or "", []).append(code)
    problems: list[str] = []

    def locate(standard: str, name: str) -> str | None:
        codes = sorted(codes_by_name.get(standard, {}).get(name, []))
        if len(codes) == 1:
            return codes[0]
        problems.append(f"{standard} 利润表找不到行名「{name}」" if not codes
                        else f"{standard} 利润表行名「{name}」不唯一（{'、'.join(codes)}）")
        return None

    out: dict[tuple[str, str], Target] = {}
    for standard, totals in ATTRIBUTION.items():
        for code, name, parts in totals:
            located = locate(standard, name)
            if located is not None and located != code:
                problems.append(f"{standard}「{name}」按行名定位到 {located}，与 KNOWN_BAD 的行次 {code} 不符")
            part_codes = tuple(locate(standard, part) for part in parts) if parts else ()
            if located == code and None not in part_codes:
                formula = "+".join(f"ROW('{c}')" for c in part_codes) or None
                out[(standard, code)] = Target(standard, code, name, formula, part_codes, KNOWN_BAD[(standard, code)])
    if problems:
        raise TargetUnresolved("；".join(problems))
    return out


def is_target(formula: str | None, target: str | None) -> bool:
    """已是目标：去首尾空白后 = 目标；目标为无公式时，无公式或空白都算（与写入方 ``_apply_report_definition`` 同口径）。"""
    return (formula or "").strip() == (target or "")


def classify(old: str | None, target: Target) -> str:
    if is_target(old, target.formula):
        return ACTION_ALREADY
    if old == target.known_bad:  # 旧值精确比对：逐字相等才升级（不去空白、不规范化）
        return ACTION_PENDING
    return ACTION_MISMATCH


def _report_rows(*columns: Any) -> sa.Select:
    return sa.select(*columns).where(ReportConfig.is_deleted == sa.false(), ReportConfig.report_type == REPORT_TYPE)


async def load_name_rows(db: Any) -> list[tuple[str, str, str]]:
    """四套准则利润表未删准则行的（准则, 行次, 行名）。"""
    q = _report_rows(ReportConfig.applicable_standard, ReportConfig.row_code, ReportConfig.row_name).where(
        ReportConfig.applicable_standard.in_(STANDARDS))
    return [(r[0], r[1], r[2] or "") for r in (await db.execute(q)).all()]


async def load_rows(db: Any, *, lock: bool = False) -> dict[tuple[str, str], CurrentRow]:
    """:data:`KNOWN_BAD` 的 8 个（准则, 行次）现值；``lock`` ⇒ ``SELECT … FOR UPDATE``。"""
    q = _report_rows(ReportConfig.id, ReportConfig.applicable_standard, ReportConfig.row_code, ReportConfig.row_name,
                     ReportConfig.formula, ReportConfig.formula_version).where(
        sa.or_(*(sa.and_(ReportConfig.applicable_standard == std, ReportConfig.row_code == code)
                 for std, code in KNOWN_BAD))).order_by(ReportConfig.applicable_standard, ReportConfig.row_code)
    if lock:
        q = q.with_for_update()
    return {(r[1], r[2]): CurrentRow(r[0], r[1], r[2], r[3] or "", r[4], int(r[5] or 1))
            for r in (await db.execute(q)).all()}


def plan(rows: Mapping[tuple[str, str], CurrentRow], targets: Mapping[tuple[str, str], Target]) -> list[RowPlan]:
    missing = [key for key in targets if key not in rows]
    if missing:
        raise UpgradeMismatch(f"报表定义里没有这些行（已删或不存在）：{missing}")
    order = {std: i for i, std in enumerate(STANDARDS)}
    out = []
    for key in sorted(targets, key=lambda k: (order[k[0]], k[1])):
        target, row = targets[key], rows[key]
        out.append(RowPlan(target.standard, target.row_code, row.row_name, row.formula, target.formula,
                           classify(row.formula, target), row.version))
    return out


async def existing_publishes(db: Any) -> dict[str, str | None]:
    """各准则升级用 request_id 已有的发布记录 id（没有为 None）。"""
    ids = {request_id_for(std): std for std in STANDARDS}
    found = (await db.execute(sa.select(FormulaPublish.request_id, FormulaPublish.id).where(
        FormulaPublish.request_id.in_(list(ids))))).all()
    out: dict[str, str | None] = dict.fromkeys(STANDARDS)
    for request_id, publish_id in found:
        out[ids[request_id]] = str(publish_id)
    return out


def _report(mode: str, database: str, plans: list[RowPlan], *, publish_records: Mapping[str, str | None] | None = None,
            publishes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "tool": TOOL,
        "mode": mode,
        "database": database,
        "rows": [p.as_row() for p in plans],
        "counts": {action: sum(p.action == action for p in plans) for action in ACTIONS},
        "skipped": [p.as_row() for p in plans if p.action == ACTION_MISMATCH],
        "publish_records": dict(publish_records or {}),
        "publishes": list(publishes or []),
    }


async def dry_run(db: Any, *, database: str) -> dict[str, Any]:
    """只读：按行名解析目标、读 8 行现值并判定动作；不加锁、不写入。"""
    targets = resolve_targets(await load_name_rows(db))
    plans = plan(await load_rows(db), targets)
    return _report("dry-run", database, plans, publish_records=await existing_publishes(db))


async def apply_upgrade(db: Any, *, database: str) -> dict[str, Any]:
    """锁定 → 重判 → 按准则发布 → 复读核对（在调用方的事务里执行，提交 / 回滚由调用方负责）。"""
    targets = resolve_targets(await load_name_rows(db))
    await lock_domain(db, DOMAIN)
    plans = plan(await load_rows(db, lock=True), targets)
    publishes: list[dict[str, Any]] = []
    for standard in STANDARDS:
        pending = [p for p in plans if p.standard == standard and p.action == ACTION_PENDING]
        if not pending:
            continue
        request_id = request_id_for(standard)
        result = await publish_global(
            db, domain=DOMAIN, scope=standard, user_id=None, source="seed", request_id=request_id, note=PUBLISH_NOTE,
            changes=[{"slot_key": slot_key(p.row_code), "label": p.row_name, "expected_version": p.version,
                      "definition": {"formula": p.target}} for p in pending])
        if result.get("idempotent"):
            raise UpgradeReplayed(
                f"{standard}：request_id {request_id} 的发布记录 {result.get('publish_id')} 已存在，publish_global 按幂等"
                f"重放返回、未写入，而 {'、'.join(p.row_code for p in pending)} 仍是已知坏式（发布之后被改回？）"
                "—— 不另起 request_id 重发，请人工核对")
        publishes.append({"standard": standard, "request_id": request_id, "publish_id": result.get("publish_id"),
                          "slots": [slot_key(p.row_code) for p in pending],
                          "versions": dict(result.get("versions") or {}),
                          "changed_projects": len(result.get("events") or [])})
    await db.flush()
    after = await load_rows(db)
    wrong = [f"{p.standard} {p.row_code} 复读为 {after[(p.standard, p.row_code)].formula!r}、目标 {p.target!r}"
             for p in plans if p.action == ACTION_PENDING and not is_target(after[(p.standard, p.row_code)].formula,
                                                                            p.target)]
    if wrong:
        raise UpgradeMismatch("发布后复读不是目标：" + "；".join(wrong))
    return _report("apply", database, plans, publishes=publishes)


async def run_session(session: Any, *, apply: bool, database: str) -> tuple[int, dict[str, Any]]:
    """在给定会话里执行并收尾：成功 ⇒ ``--apply`` 提交、只读回滚；失败一律回滚。返回（退出码, 报告）。"""
    mode = "apply" if apply else "dry-run"
    try:
        if apply:
            report = await apply_upgrade(session, database=database)
            await session.commit()
        else:
            report = await dry_run(session, database=database)
            await session.rollback()
    except TargetUnresolved as exc:
        await session.rollback()
        return 2, {"tool": TOOL, "mode": mode, "database": database, "error": f"按行名定位不到：{exc}"}
    except Exception as exc:  # noqa: BLE001 —— 升级失败整次回滚，原因进报告
        await session.rollback()
        return 1, {"tool": TOOL, "mode": mode, "database": database, "error": f"{type(exc).__name__}: {exc}"}
    return 0, report


def _database_label(url: str) -> str:
    parsed = make_url(url)
    return f"{parsed.database}（{parsed.host}:{parsed.port or 5432}）"


async def _run(*, apply: bool) -> tuple[int, dict[str, Any]]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    url = str(settings.DATABASE_URL)
    backend = make_url(url).get_backend_name()
    if backend != "postgresql":
        return 2, {"tool": TOOL, "error": f"只支持 PostgreSQL：{backend}"}
    database = _database_label(url)
    engine = create_async_engine(
        url, poolclass=NullPool, connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {}
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            if not apply:
                try:  # 只读模式由库强制：本事务里任何写语句都会报错
                    await session.execute(sa.text("SET TRANSACTION READ ONLY"))
                except Exception as exc:  # noqa: BLE001 —— 连不上库等，原因进报告
                    return 1, {"tool": TOOL, "mode": "dry-run", "database": database,
                               "error": f"连接数据库失败：{type(exc).__name__}: {exc}"}
            return await run_session(session, apply=apply, database=database)
    finally:
        await engine.dispose()


def _fmt(formula: str | None) -> str:
    return NO_FORMULA if formula is None else json.dumps(formula, ensure_ascii=False)


def _print(code: int, report: dict[str, Any]) -> None:
    if "error" in report:
        print(f"[{TOOL}] 库 {report.get('database', '?')}：{report['error']}（退出码 {code}，未做任何修改）")
        return
    apply = report["mode"] == "apply"
    print(f"[{TOOL}] 库 {report['database']}；模式 {'--apply（已提交）' if apply else '只读（只读事务，不写入）'}")
    counts = report["counts"]
    print(f"[{TOOL}] {len(report['rows'])} 行{'（动作按锁定后的值判定）' if apply else ''}："
          + "、".join(f"{action} {counts[action]}" for action in ACTIONS))
    for row in report["rows"]:
        print(f"[{TOOL}]   {row['standard']} {row['row_code']}「{row['row_name']}」v{row['version']} 旧值 {_fmt(row['old'])}"
              f" → 目标 {_fmt(row['target'])}：{row['action']}")
    if report["skipped"]:
        print(f"[{TOOL}] 旧值不符跳过 {len(report['skipped'])} 行（未改动，需人工核对）："
              + "；".join(f"{r['standard']} {r['row_code']}" for r in report["skipped"]))
    if not apply:
        pending: dict[str, int] = {}
        for row in report["rows"]:
            if row["action"] == ACTION_PENDING:
                pending[row["standard"]] = pending.get(row["standard"], 0) + 1
        records = report["publish_records"]
        plan_text = "；".join(f"{std} {n} 行 request_id={request_id_for(std)}（已有发布记录：{records.get(std) or '无'}）"
                              for std, n in pending.items()) or "无（没有待升级行）"
        print(f"[{TOOL}] --apply 时发布（每个有待升级行的准则一次，source=seed）：{plan_text}")
        for std in pending:
            if records.get(std):
                print(f"[{TOOL}]   注意：{std} 的升级发布记录已存在而仍有待升级行 ⇒ --apply 会幂等重放、不写入并报错")
        return
    for pub in report["publishes"]:
        slots = "、".join(f"{slot} → v{pub['versions'].get(slot)}" for slot in pub["slots"])
        print(f"[{TOOL}] 已发布 {pub['standard']}：publish_id={pub['publish_id']} request_id={pub['request_id']} "
              f"公式位 {slots}；有效定义变化的项目 {pub['changed_projects']} 个"
              "（报表行已在同一事务内标过期；未发公式变更事件、未重算报表）")
    if not report["publishes"]:
        print(f"[{TOOL}] 没有待升级行：未调用 publish_global，0 变更")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:  # argparse 的英文报错换成中文原因；退出码 2 由 main 给出
        raise ArgumentProblem(_argparse_reason(message))


def _argparse_reason(message: str) -> str:
    if message.startswith("unrecognized arguments:"):
        return f"无法识别的参数：{message.split(':', 1)[1].strip()}"
    if message.endswith("expected one argument"):
        return f"参数 {message.split(':', 1)[0].replace('argument', '').strip()} 缺少取值"
    return f"参数不合法：{message}"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _Parser(prog=TOOL, allow_abbrev=False,
                     description="利润表归属行存量升级：默认只读列出旧值 / 目标 / 动作，--apply 经同步内核发布")
    parser.add_argument("--apply", action="store_true",
                        help="锁定 8 行 → 逐字等于已知坏式的行按准则经 publish_global 发布 → 提交（决策项 X2）")
    parser.add_argument("--json", type=Path, default=None, help="完整报告另存路径（所在目录须已存在）")
    args = parser.parse_args(argv)
    if args.json is not None:
        if args.json.is_dir():
            raise ArgumentProblem(f"参数 --json 应为文件路径，{args.json} 是目录")
        if not args.json.parent.is_dir():
            raise ArgumentProblem(f"参数 --json 的目录不存在：{args.json.parent}")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows 控制台默认 gbk，中文会抛
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    try:
        args = parse_args(argv)
    except ArgumentProblem as exc:
        print(f"[{TOOL}] 参数错误：{exc}（退出码 2，未连接数据库、未做任何修改）")
        return 2
    code, report = asyncio.run(_run(apply=bool(args.apply)))
    if args.json is not None:
        args.json.write_text(json.dumps({**report, "exit_code": code}, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    _print(code, report)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
