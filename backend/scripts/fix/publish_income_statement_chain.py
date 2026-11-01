#!/usr/bin/env python
"""利润链存量发布：默认只读逐行列出旧值 / 目标 / 动作，``--apply`` 经同步内核发布。

spec income-statement-lower-section-formulas（R1~R4，ADR-ISL-03）。四套准则利润表的利润链公式行在已有库里多数为空，
另有 7 条「已知坏式」（design §1 第 4、5 行）；手工输入行的 ``formula_source`` 在已有库里全部未登记。
种子已按 design §2 写好，但种子加载不覆盖已有行 ⇒ 已有库只能经本工具发布。

目标 = 种子（``backend/data/report_config_seed.json``）里该准则该行次的公式与 ``formula_source``，
**本工具不自带第二份目标文本 / 输入行清单**：唯一权威是种子，避免两处口径漂移（ADR-ISL-04 同源）。
归属行 8 行归母 spec 的 ``republish_report_seed_rows.py``（决策项 X2），本工具不碰。

逐行动作（:func:`classify`）：
- 已是目标：公式 + 来源都等于种子 ⇒ 不动；
- 待发布（空公式）：库里公式为空 / 空白且来源是安全旧值 ⇒ 发布公式与来源；
- 待修正（已知坏式）：公式逐字等于 :data:`KNOWN_BAD` 且来源是安全旧值 ⇒ 发布目标；
- 待更新来源：公式已经正确、来源为空或为既有生成器来源 ⇒ 只补来源；
- 待登记（输入行）：公式为空且来源为空 ⇒ 写 ``formula_source='input'``，不造公式；
- 第三种定义：公式或来源存在未登记值（有人改过）⇒ **不改、列出、退出码 2**（design §4 D4：不替用户决定）。

``--apply``（一个事务）：取报表域发布锁 → ``SELECT … FOR UPDATE`` → 按锁定后的值重判 → 每个有待发布行的准则
调一次 ``publish_global(domain="report", scope=<准则>, source="seed")`` → 复读核对 → 提交。受影响报表行标过期由
``publish_global`` 在同一事务内完成（ADR-FHIC-04）；工具不发公式变更事件、不重算报表（决策项 X3、D4）。
可重复执行：第二次全部「已是目标」、不调 ``publish_global``、0 写入。

用法（目标库 = ``settings.DATABASE_URL``，输出第一行打印库名）::

    python backend/scripts/fix/publish_income_statement_chain.py                 # 只读（只读事务）
    python backend/scripts/fix/publish_income_statement_chain.py --json out.json # 另存完整报告
    python backend/scripts/fix/publish_income_statement_chain.py --apply         # 发布（决策项 D4）

退出码：0 完成；1 发布失败（连不上库、数据库错误、版本冲突、幂等重放、复读不是目标；已回滚）；
2 参数非法、库不是 PostgreSQL、种子缺行、或检出第三种定义（都不写入）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.models.formula_setting_models import FormulaPublish  # noqa: E402
from app.models.report_models import FinancialReportType, ReportConfig  # noqa: E402
from app.services.formula_settings.engine import lock_domain  # noqa: E402
from app.services.formula_settings.publish import publish_global  # noqa: E402

TOOL = "publish_income_statement_chain"
DOMAIN = "report"
REPORT_TYPE = FinancialReportType.income_statement
REQUEST_ID_PREFIX = "seed-publish-is-chain-"
PUBLISH_NOTE = "存量发布：利润链按 design §2 补齐（publish_income_statement_chain.py，决策项 D4）"
STANDARDS = ("soe_consolidated", "soe_standalone", "listed_consolidated", "listed_standalone")
SEED = _BACKEND_ROOT / "data" / "report_config_seed.json"

ACTION_EMPTY = "待发布（空公式）"
ACTION_BAD = "待修正（已知坏式）"
ACTION_SOURCE = "待更新来源"
ACTION_INPUT = "待登记（输入行）"
ACTION_ALREADY = "已是目标"
ACTION_THIRD = "第三种定义"
ACTIONS = (ACTION_EMPTY, ACTION_BAD, ACTION_SOURCE, ACTION_INPUT, ACTION_ALREADY, ACTION_THIRD)
PENDING_ACTIONS = (ACTION_EMPTY, ACTION_BAD, ACTION_SOURCE, ACTION_INPUT)
NO_FORMULA = "（无公式）"

#: 母 spec 的归属行（ADR-FHIC-23，决策项 X2 由 republish_report_seed_rows.py 处理）：本工具跳过
ATTRIBUTION_CODES: dict[str, frozenset[str]] = {
    "soe_consolidated": frozenset({"IS-074", "IS-075"}),
    "soe_standalone": frozenset({"IS-074", "IS-075"}),
    "listed_consolidated": frozenset({"IS-051", "IS-052"}),
    "listed_standalone": frozenset({"IS-051", "IS-052"}),
}

#: 已知坏式（design §1 第 4、5 行现算）：
#: - 第 4 行：综合收益总额只加其他综合收益一段、不含净利润，且区间同时含小计行与其明细行；
#: - 第 5 行：利润总额把营业外收入与营业外支出直接相加（国企合并还把「其中：政府补助」重复加了一次）。
#: 只有逐字等于这些文本的行才允许被 ``--apply`` 改写。
KNOWN_BAD: dict[tuple[str, str], str] = {
    ("soe_consolidated", "IS-044"): "SUM_ROW('IS-041','IS-043')",
    ("soe_consolidated", "IS-073"): "SUM_ROW('IS-054','IS-072')",
    ("soe_standalone", "IS-073"): "SUM_ROW('IS-054','IS-072')",
    ("listed_consolidated", "IS-022"): "SUM_ROW('IS-020','IS-021')",
    ("listed_consolidated", "IS-050"): "SUM_ROW('IS-032','IS-049')",
    ("listed_standalone", "IS-022"): "SUM_ROW('IS-020','IS-021')",
    ("listed_standalone", "IS-050"): "SUM_ROW('IS-032','IS-049')",
}


class SeedProblem(RuntimeError):
    """种子里缺本准则利润表、或目标行次在种子里查不到：退出码 2，不写。"""


class ThirdFormulaFound(RuntimeError):
    """检出第三种定义（公式或来源有人改过）：退出码 2，不写。"""


class PublishReplayed(RuntimeError):
    """同 request_id 的发布记录已存在而行仍待发布：``publish_global`` 幂等重放、未写入。"""


class PublishMismatch(RuntimeError):
    """锁定时缺行，或发布后复读不是目标（调用方回滚）。"""


class ArgumentProblem(ValueError):
    """命令行参数缺失或非法：退出码 2，未连接数据库。"""


@dataclass(frozen=True)
class Target:
    standard: str
    row_code: str
    row_name: str
    formula: str | None
    formula_source: str
    known_bad: str | None


@dataclass(frozen=True)
class CurrentRow:
    row_id: uuid.UUID
    standard: str
    row_code: str
    row_name: str
    formula: str | None
    formula_source: str | None
    version: int


@dataclass(frozen=True)
class RowPlan:
    standard: str
    row_code: str
    row_name: str
    old: str | None
    target: str | None
    old_source: str | None
    target_source: str
    action: str
    version: int

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


def request_id_for(standard: str) -> str:
    return f"{REQUEST_ID_PREFIX}{standard}"


def slot_key(row_code: str) -> str:
    return f"{REPORT_TYPE.value}:{row_code}"


def seed_targets(path: Path = SEED) -> dict[tuple[str, str], Target]:
    """种子四套利润表里有公式或 ``formula_source='input'``、且不属归属行的行 → 目标。

    公式文本与输入行登记都以种子为唯一权威；工具不自带第二份目标清单。
    """
    try:
        blocks = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise SeedProblem(f"读不到种子 {path}：{exc}") from exc
    out: dict[tuple[str, str], Target] = {}
    seen: set[str] = set()
    for block in blocks:
        standard = block.get("applicable_standard")
        if block.get("report_type") != REPORT_TYPE.value or standard not in STANDARDS:
            continue
        seen.add(standard)
        for row in block.get("rows", []):
            code = row.get("row_code")
            formula = (row.get("formula") or "").strip() or None
            source = (row.get("formula_source") or "").strip()
            if code in ATTRIBUTION_CODES[standard] or (formula is None and source != "input"):
                continue
            if formula is not None and source not in {"identity", "special"}:
                raise SeedProblem(f"种子 {standard} {code} 有公式但 formula_source={source!r}，应为 identity/special")
            out[(standard, code)] = Target(
                standard, code, row.get("row_name") or "", formula, source,
                KNOWN_BAD.get((standard, code)),
            )
    missing = sorted(set(STANDARDS) - seen)
    if missing:
        raise SeedProblem(f"种子缺这些准则的利润表：{missing}")
    if not out:
        raise SeedProblem("种子四套利润表没有任何公式或输入行登记（本工具无事可做，疑似种子未更新）")
    unused = sorted(key for key in KNOWN_BAD if key not in out)
    if unused:
        raise SeedProblem(f"已知坏式登记的行在种子里没有目标公式：{unused}")
    return out


def is_target(formula: str | None, source: str | None, target: Target) -> bool:
    return (formula or "").strip() == (target.formula or "") and (source or "").strip() == target.formula_source


_SAFE_OLD_SOURCES = frozenset({"", "special", "identity", "auto_total", "auto_total_flag", "fallback_prefix", "cas"})


def classify(old: str | None, old_source: str | None, target: Target) -> str:
    """定义级安全分类：输入行只允许从「空公式 + 空来源」登记，其他已有定义一律交人工决定。"""
    formula = (old or "").strip()
    source = (old_source or "").strip()
    if is_target(old, old_source, target):
        return ACTION_ALREADY
    if target.formula is None:  # 手工输入行：绝不自动清掉已有公式或未知来源
        if formula or source not in {"", "input"}:
            return ACTION_THIRD
        return ACTION_INPUT
    if formula == target.formula:
        return ACTION_SOURCE if source in _SAFE_OLD_SOURCES else ACTION_THIRD
    if not formula and source in _SAFE_OLD_SOURCES:
        return ACTION_EMPTY
    if target.known_bad is not None and old == target.known_bad and source in _SAFE_OLD_SOURCES:
        return ACTION_BAD
    return ACTION_THIRD


async def load_rows(db: Any, targets: Mapping[tuple[str, str], Target], *, lock: bool = False,
                    ) -> dict[tuple[str, str], CurrentRow]:
    q = sa.select(
        ReportConfig.id, ReportConfig.applicable_standard, ReportConfig.row_code, ReportConfig.row_name,
        ReportConfig.formula, ReportConfig.formula_source, ReportConfig.formula_version,
    ).where(
        ReportConfig.is_deleted == sa.false(), ReportConfig.report_type == REPORT_TYPE,
        sa.or_(*(sa.and_(ReportConfig.applicable_standard == std, ReportConfig.row_code == code)
                 for std, code in targets)),
    ).order_by(ReportConfig.applicable_standard, ReportConfig.row_code)
    if lock:
        q = q.with_for_update()
    return {(r[1], r[2]): CurrentRow(r[0], r[1], r[2], r[3] or "", r[4], r[5], int(r[6] or 1))
            for r in (await db.execute(q)).all()}


def plan(rows: Mapping[tuple[str, str], CurrentRow], targets: Mapping[tuple[str, str], Target]) -> list[RowPlan]:
    order = {std: i for i, std in enumerate(STANDARDS)}
    out: list[RowPlan] = []
    for key in sorted(targets, key=lambda k: (order[k[0]], k[1])):
        target = targets[key]
        row = rows.get(key)
        if row is None:  # 库里没有这一行（已删或行次不同）：不新增行，列出来
            out.append(RowPlan(target.standard, target.row_code, target.row_name, None, target.formula,
                               None, target.formula_source, "库里缺此行", 0))
            continue
        out.append(RowPlan(
            target.standard, target.row_code, row.row_name, row.formula, target.formula,
            row.formula_source, target.formula_source,
            classify(row.formula, row.formula_source, target), row.version,
        ))
    return out


async def existing_publishes(db: Any) -> dict[str, str | None]:
    ids = {request_id_for(std): std for std in STANDARDS}
    found = (await db.execute(sa.select(FormulaPublish.request_id, FormulaPublish.id).where(
        FormulaPublish.request_id.in_(list(ids))))).all()
    out: dict[str, str | None] = dict.fromkeys(STANDARDS)
    for request_id, publish_id in found:
        out[ids[request_id]] = str(publish_id)
    return out


def _report(mode: str, database: str, plans: list[RowPlan], *,
            publish_records: Mapping[str, str | None] | None = None,
            publishes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "tool": TOOL,
        "mode": mode,
        "database": database,
        "rows": [p.as_row() for p in plans],
        "counts": {action: sum(p.action == action for p in plans) for action in ACTIONS},
        "third_formula": [p.as_row() for p in plans if p.action == ACTION_THIRD],
        "missing_rows": [p.as_row() for p in plans if p.action == "库里缺此行"],
        "publish_records": dict(publish_records or {}),
        "publishes": list(publishes or []),
    }


async def dry_run(db: Any, *, database: str) -> dict[str, Any]:
    targets = seed_targets()
    plans = plan(await load_rows(db, targets), targets)
    return _report("dry-run", database, plans, publish_records=await existing_publishes(db))


async def apply_publish(db: Any, *, database: str) -> dict[str, Any]:
    targets = seed_targets()
    await lock_domain(db, DOMAIN)
    plans = plan(await load_rows(db, targets, lock=True), targets)
    third = [p for p in plans if p.action == ACTION_THIRD]
    if third:
        raise ThirdFormulaFound(
            "检出第三种定义（既不是目标 / 安全旧值，也不是已知坏式），不替用户决定："
            + "；".join(
                f"{p.standard} {p.row_code} 现公式 {p.old!r}、来源 {p.old_source!r}"
                for p in third
            ))
    publishes: list[dict[str, Any]] = []
    for standard in STANDARDS:
        pending = [p for p in plans if p.standard == standard and p.action in PENDING_ACTIONS]
        if not pending:
            continue
        request_id = request_id_for(standard)
        result = await publish_global(
            db, domain=DOMAIN, scope=standard, user_id=None, source="seed", request_id=request_id, note=PUBLISH_NOTE,
            changes=[{
                "slot_key": slot_key(p.row_code), "label": p.row_name, "expected_version": p.version,
                "definition": {"formula": p.target, "formula_source": p.target_source},
            } for p in pending])
        if result.get("idempotent"):
            raise PublishReplayed(
                f"{standard}：request_id {request_id} 的发布记录 {result.get('publish_id')} 已存在，publish_global 按"
                f"幂等重放返回、未写入，而 {'、'.join(p.row_code for p in pending)} 仍待发布（发布之后被改回？）"
                "—— 不另起 request_id 重发，请人工核对")
        publishes.append({"standard": standard, "request_id": request_id, "publish_id": result.get("publish_id"),
                          "slots": [slot_key(p.row_code) for p in pending],
                          "versions": dict(result.get("versions") or {}),
                          "changed_projects": len(result.get("events") or [])})
    await db.flush()
    after = await load_rows(db, targets)
    wrong = [
        f"{p.standard} {p.row_code} 复读为公式 {after[(p.standard, p.row_code)].formula!r}、"
        f"来源 {after[(p.standard, p.row_code)].formula_source!r}；目标公式 {p.target!r}、来源 {p.target_source!r}"
        for p in plans if p.action in PENDING_ACTIONS
        and not is_target(
            after[(p.standard, p.row_code)].formula,
            after[(p.standard, p.row_code)].formula_source,
            targets[(p.standard, p.row_code)],
        )
    ]
    if wrong:
        raise PublishMismatch("发布后复读不是目标：" + "；".join(wrong))
    return _report("apply", database, plans, publishes=publishes)


async def run_session(session: Any, *, apply: bool, database: str) -> tuple[int, dict[str, Any]]:
    """在给定会话里执行并收尾：成功 ⇒ ``--apply`` 提交、只读回滚；失败一律回滚。返回（退出码, 报告）。"""
    mode = "apply" if apply else "dry-run"
    try:
        if apply:
            report = await apply_publish(session, database=database)
            await session.commit()
        else:
            report = await dry_run(session, database=database)
            await session.rollback()
    except (SeedProblem, ThirdFormulaFound) as exc:
        await session.rollback()
        return 2, {"tool": TOOL, "mode": mode, "database": database, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 —— 发布失败整次回滚，原因进报告
        await session.rollback()
        return 1, {"tool": TOOL, "mode": mode, "database": database, "error": f"{type(exc).__name__}: {exc}"}
    if not apply and report["counts"][ACTION_THIRD]:
        return 2, report  # 只读模式也把第三种定义报成非 0（CI / 运维一眼看出需要人工决定）
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
        url, poolclass=NullPool, connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {})
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            if not apply:
                try:  # 只读模式由库强制：本事务里任何写语句都会报错
                    await session.execute(sa.text("SET TRANSACTION READ ONLY"))
                except Exception as exc:  # noqa: BLE001
                    return 1, {"tool": TOOL, "mode": "dry-run", "database": database,
                               "error": f"连接数据库失败：{type(exc).__name__}: {exc}"}
            return await run_session(session, apply=apply, database=database)
    finally:
        await engine.dispose()


def _fmt(formula: str | None) -> str:
    return NO_FORMULA if not (formula or "").strip() else json.dumps(formula, ensure_ascii=False)


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
        print(f"[{TOOL}]   {row['standard']} {row['row_code']}「{row['row_name']}」v{row['version']} "
              f"旧值 {_fmt(row['old'])} / 来源 {row['old_source'] or '（空）'} → "
              f"目标 {_fmt(row['target'])} / 来源 {row['target_source']}：{row['action']}")
    if report["third_formula"]:  # JSON 字段名保留 third_formula，兼容首版只读报告
        print(f"[{TOOL}] 第三种定义 {len(report['third_formula'])} 行（未改动，需人工核对后决定）："
              + "；".join(f"{r['standard']} {r['row_code']}" for r in report["third_formula"]))
    if report["missing_rows"]:
        print(f"[{TOOL}] 库里缺 {len(report['missing_rows'])} 行（不新增行）："
              + "；".join(f"{r['standard']} {r['row_code']}" for r in report["missing_rows"]))
    if not apply:
        pending: dict[str, int] = {}
        for row in report["rows"]:
            if row["action"] in PENDING_ACTIONS:
                pending[row["standard"]] = pending.get(row["standard"], 0) + 1
        records = report["publish_records"]
        plan_text = "；".join(f"{std} {n} 行 request_id={request_id_for(std)}（已有发布记录：{records.get(std) or '无'}）"
                              for std, n in pending.items()) or "无（没有待发布行）"
        print(f"[{TOOL}] --apply 时发布（每个有待发布行的准则一次，source=seed）：{plan_text}")
        for std in pending:
            if records.get(std):
                print(f"[{TOOL}]   注意：{std} 的发布记录已存在而仍有待发布行 ⇒ --apply 会幂等重放、不写入并报错")
        return
    for pub in report["publishes"]:
        slots = "、".join(f"{slot} → v{pub['versions'].get(slot)}" for slot in pub["slots"])
        print(f"[{TOOL}] 已发布 {pub['standard']}：publish_id={pub['publish_id']} request_id={pub['request_id']} "
              f"公式位 {slots}；有效定义变化的项目 {pub['changed_projects']} 个"
              "（报表行已在同一事务内标过期；未发公式变更事件、未重算报表）")
    if not report["publishes"]:
        print(f"[{TOOL}] 没有待发布行：未调用 publish_global，0 变更")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ArgumentProblem(_argparse_reason(message))


def _argparse_reason(message: str) -> str:
    if message.startswith("unrecognized arguments:"):
        return f"无法识别的参数：{message.split(':', 1)[1].strip()}"
    if message.endswith("expected one argument"):
        return f"参数 {message.split(':', 1)[0].replace('argument', '').strip()} 缺少取值"
    return f"参数不合法：{message}"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _Parser(prog=TOOL, allow_abbrev=False,
                     description="利润链存量发布：默认只读列出旧值 / 目标 / 动作，--apply 经同步内核发布")
    parser.add_argument("--apply", action="store_true",
                        help="锁定目标行 → 安全旧定义按准则经 publish_global 发布公式 / 来源 → 提交（决策项 D4）")
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
