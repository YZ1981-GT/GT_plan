"""凭证身份单一实现（spec voucher-identity-writeback-and-audit-phase 需求 1，ADR-VK-01~04）。

为什么需要它：平台此前有两套「一张凭证」口径——只按凭证号（抽样单位、排除、登记、幂等），
或按 (日期, 凭证号)（穿透、对方科目补全、挂凭）。真实账里两者都不唯一：医疗器械 723 个凭证号
对应 13,384 张凭证；四川物流、宜宾临港、辽宁卫生分别有 167 / 118 / 1,247 组同日同号混了
2~5 种凭证字（2025-01-07 的「0003」同时是 FY-0003 与 ZZ-0003）。

- 凭证键 = (年度, 主体编码, 凭证日期, 凭证字, 凭证号)；凭证字为空按空串参与。
- 借贷栏按栏位判定：只有借方栏非零为 D，只有贷方栏非零为 C，其余为 X（两栏都非零，如辽宁
  卫生借贷双填；或都为零）。不按正负号：红字分录占 3%~19.5%，红字借方仍记在借方栏。
- 分录指纹 = 凭证键 + 科目 + 借贷栏 + 金额（两位小数带符号）+ 同组序号。同组 = 凭证键、
  科目、借贷栏、金额都相同；组内按 (摘要, 行 id) 排序编号。摘要不进指纹：客户改摘要不改变
  分录身份。分录序号 entry_seq 在真实账里 100% 为空，行 id 每次导入都换，二者都不能做身份。

前端同口径实现：audit-platform/frontend/src/utils/voucherIdentity.ts；
跨语言样例：backend/tests/fixtures/voucher_identity_vectors.json。
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException

SIDE_DEBIT = "D"
SIDE_CREDIT = "C"
SIDE_UNKNOWN = "X"

_CENT = Decimal("0.01")
_RESOLVE_CHUNK = 400
#: 409 候选清单最多列这么多张（只给凭证号时可能对应全年几十张同号凭证）
AMBIGUOUS_CANDIDATE_LIMIT = 50


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _get(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def norm_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def norm_date(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()[:10]


def to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if text == "":
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"金额无法解析：{value!r}") from exc


def amount_str(value: Any) -> str:
    """两位小数、四舍五入（远离零）、带符号；零一律写 0.00（不出现 -0.00）。"""
    d = to_decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)
    if d == 0:
        return "0.00"
    return format(d, "f")


def side_of(debit: Any, credit: Any) -> str:
    d, c = to_decimal(debit), to_decimal(credit)
    if d != 0 and c == 0:
        return SIDE_DEBIT
    if c != 0 and d == 0:
        return SIDE_CREDIT
    return SIDE_UNKNOWN


def signed_amount(debit: Any, credit: Any, side: str | None = None) -> Decimal:
    """该分录在其借贷栏上的带符号金额；不明（X）时取非零那栏，都非零取借方。"""
    s = side or side_of(debit, credit)
    d, c = to_decimal(debit), to_decimal(credit)
    if s == SIDE_DEBIT:
        return d
    if s == SIDE_CREDIT:
        return c
    return d if d != 0 else c


@dataclass(frozen=True)
class VoucherKey:
    year: str
    company_code: str
    voucher_date: str
    voucher_type: str
    voucher_no: str

    @classmethod
    def of(
        cls,
        *,
        year: Any,
        company_code: Any,
        voucher_date: Any,
        voucher_type: Any,
        voucher_no: Any,
    ) -> VoucherKey:
        return cls(
            norm_text(year),
            norm_text(company_code),
            norm_date(voucher_date),
            norm_text(voucher_type),
            norm_text(voucher_no),
        )

    @classmethod
    def from_row(cls, row: Any, *, year: Any = None) -> VoucherKey:
        """从分录行（ORM 对象或 dict）取凭证键；行上没有 year 时用参数补。"""
        row_year = _get(row, "year")
        return cls.of(
            year=row_year if row_year not in (None, "") else year,
            company_code=_get(row, "company_code"),
            voucher_date=_get(row, "voucher_date"),
            voucher_type=_get(row, "voucher_type"),
            voucher_no=_get(row, "voucher_no"),
        )

    def parts(self) -> list[str]:
        return [self.year, self.company_code, self.voucher_date, self.voucher_type, self.voucher_no]

    def to_str(self) -> str:
        return _dumps(self.parts())

    @classmethod
    def from_str(cls, text: str) -> VoucherKey:
        try:
            parts = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"凭证键格式错误：{text!r}") from exc
        if not (isinstance(parts, list) and len(parts) == 5 and all(isinstance(p, str) for p in parts)):
            raise ValueError(f"凭证键格式错误：{text!r}")
        return cls(*parts)

    @property
    def date_value(self) -> date:
        return date.fromisoformat(self.voucher_date)

    def sql_values(self, *, with_company: bool = True) -> tuple:
        """与 :func:`voucher_key_tuple` 列顺序对应的取值（日期为 date 对象，asyncpg 不收字符串）。"""
        base = (self.date_value, self.voucher_type, self.voucher_no)
        return (self.company_code, *base) if with_company else base


def parse_voucher_keys(values: Iterable[Any]) -> list[VoucherKey]:
    """凭证键串列表（回填日志的 ``filled_voucher_keys`` 等）→ VoucherKey 列表，去重保序。

    格式错、日期不是 YYYY-MM-DD、凭证号为空的跳过 —— 调用方拿到的每个键都能直接
    ``date_value`` / ``sql_values()``。
    """
    out: dict[VoucherKey, None] = {}
    for value in values:
        try:
            vk = VoucherKey.from_str(str(value))
            vk.date_value  # noqa: B018 — 校验日期可解析
        except ValueError:
            continue
        if vk.voucher_no:
            out.setdefault(vk, None)
    return list(out)


def line_fingerprint(vk: VoucherKey, account_code: Any, side: str, amount: Any, occ: int) -> str:
    return _dumps([*vk.parts(), norm_text(account_code), side, amount_str(amount), int(occ)])


@dataclass(frozen=True)
class LineFingerprint:
    vk: VoucherKey
    account_code: str
    side: str
    amount: str
    occ: int

    @classmethod
    def parse(cls, text: str) -> LineFingerprint:
        try:
            parts = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"分录指纹格式错误：{text!r}") from exc
        if not (
            isinstance(parts, list)
            and len(parts) == 9
            and all(isinstance(p, str) for p in parts[:8])
            and isinstance(parts[8], int)
            and parts[6] in (SIDE_DEBIT, SIDE_CREDIT, SIDE_UNKNOWN)
        ):
            raise ValueError(f"分录指纹格式错误：{text!r}")
        return cls(VoucherKey(*parts[:5]), parts[5], parts[6], parts[7], parts[8])

    def to_str(self) -> str:
        return _dumps([*self.vk.parts(), self.account_code, self.side, self.amount, self.occ])


def describe_line(row: Any, *, year: Any = None) -> tuple[VoucherKey, str, str, str]:
    """分录行 → (凭证键, 科目, 借贷栏, 金额字符串)，即分录指纹去掉同组序号的部分。"""
    debit, credit = _get(row, "debit_amount"), _get(row, "credit_amount")
    side = side_of(debit, credit)
    return (
        VoucherKey.from_row(row, year=year),
        norm_text(_get(row, "account_code")),
        side,
        amount_str(signed_amount(debit, credit, side)),
    )


def fingerprint_lines(lines: Sequence[Any], *, year: Any = None) -> list[str]:
    """给一组分录行算分录指纹，结果与输入顺序一一对应。

    🔴 同组序号依赖「同凭证、同科目」的分录全部在输入里：只给一部分会编错号。
    调用方按凭证键 + 科目取齐分录（见 :func:`resolve_line_fps`）。
    """
    groups: dict[tuple[VoucherKey, str, str, str], list[int]] = defaultdict(list)
    for i, row in enumerate(lines):
        groups[describe_line(row, year=year)].append(i)
    out = [""] * len(lines)
    for (vk, acct, side, amt), idxs in groups.items():
        idxs.sort(key=lambda i: (norm_text(_get(lines[i], "summary")), str(_get(lines[i], "id") or "")))
        for occ, i in enumerate(idxs):
            out[i] = _dumps([*vk.parts(), acct, side, amt, occ])
    return out


class VoucherKeyAmbiguous(HTTPException):
    """穿透只给了凭证号（或日期 + 号）却命中多张凭证：409 + 候选清单，不合并分录（需求 2.1）。

    继承 HTTPException：平台全局处理器返回 ``{"code": 409, "message": {error_code, message,
    candidates, truncated}}``，前端 http 拦截器把 ``message`` 补成 ``detail``。
    """

    error_code = "VOUCHER_KEY_AMBIGUOUS"

    def __init__(self, candidates: list[dict], total: int):
        self.candidates = candidates
        super().__init__(status_code=409, detail={
            "error_code": self.error_code,
            "message": f"该凭证号对应 {total} 张凭证（日期、凭证字或主体不同），请选择一张查看",
            "candidates": candidates,
            "truncated": total > len(candidates),
        })


def group_by_voucher_key(rows: Iterable[Any], *, year: Any = None) -> dict[VoucherKey, list]:
    groups: dict[VoucherKey, list] = {}
    for row in rows:
        groups.setdefault(VoucherKey.from_row(row, year=year), []).append(row)
    return groups


def single_voucher_lines(rows: Sequence[Any], *, year: Any = None) -> list:
    """穿透结果必须恰好是一张凭证：跨多张凭证抛 :class:`VoucherKeyAmbiguous`（附候选），空则返回空。"""
    groups = group_by_voucher_key(rows, year=year)
    if len(groups) <= 1:
        return list(rows)
    candidates = []
    for vk in sorted(groups, key=VoucherKey.parts)[:AMBIGUOUS_CANDIDATE_LIMIT]:
        lines = groups[vk]
        summaries = (norm_text(_get(x, "summary")) for x in lines)
        candidates.append({
            "voucher_key": vk.to_str(),
            "company_code": vk.company_code,
            "voucher_date": vk.voucher_date,
            "voucher_type": vk.voucher_type,
            "voucher_no": vk.voucher_no,
            "line_count": len(lines),
            "debit_total": amount_str(sum((to_decimal(_get(x, "debit_amount")) for x in lines), Decimal("0"))),
            "summary": next((s for s in summaries if s), ""),
        })
    raise VoucherKeyAmbiguous(candidates, len(groups))


def annotate_lines(rows: list[dict], *, year: Any = None) -> list[dict]:
    """给一张凭证的分录行补 ``voucher_key`` / ``side`` / ``line_fp``（就地修改并返回）。"""
    for row, fp in zip(rows, fingerprint_lines(rows, year=year)):
        row["voucher_key"] = VoucherKey.from_row(row, year=year).to_str()
        row["side"] = side_of(_get(row, "debit_amount"), _get(row, "credit_amount"))
        row["line_fp"] = fp
    return rows


def voucher_type_condition(table: Any, voucher_type: Any) -> sa.ColumnElement:
    """凭证字条件；空串匹配凭证字为空（NULL 或 ''）的那张。"""
    c = table.c if hasattr(table, "c") else table.__table__.c
    return sa.func.coalesce(c.voucher_type, sa.literal_column("''")) == norm_text(voucher_type)


def company_code_condition(table: Any, company_code: Any) -> sa.ColumnElement | None:
    """主体条件；没给（None / 空串）返回 None = 不限主体。

    四表的 ``company_code`` 非空（导入没映射主体时记 ``default``），空串因此只表示「不知道」，不像凭证字那样
    表示「为空的那张」。一套账两个主体同日同号同凭证字时（真库现扫：3 个已软删的 B2Perf 性能测试项目各 92 组，
    在用项目 0 组），只给日期 + 凭证字 + 号会命中两张凭证（409 + 候选），选候选时必须带主体才能取到其中一张。
    """
    code = norm_text(company_code)
    if not code:
        return None
    c = table.c if hasattr(table, "c") else table.__table__.c
    return c.company_code == code


def voucher_key_sql(table: Any, *, with_company: bool = True) -> tuple:
    """凭证键在 SQL 里的列表达式：(主体, 日期, COALESCE(凭证字, ''), 凭证号)，供 group by / 行值 IN。

    年度不在其中：四表查询一律先经 get_active_filter 限定 (project_id, year)。主体必须在：真库有
    4 个 active 数据集一套账里有两个主体编码，只按 (日期, 凭证字, 号) 会把两家公司的凭证并成一张。

    🔴 空串必须是 SQL 字面量而不是绑定参数：SELECT 与 GROUP BY 各调一次本函数时，绑定参数会编成
    ``coalesce(voucher_type, $1)`` 与 ``coalesce(voucher_type, $5)``，PG 认为是两个表达式而报 GroupingError
    （SQLite 不报，只有真库测试抓得到）。
    """
    c = table.c if hasattr(table, "c") else table.__table__.c
    cols = (c.voucher_date, sa.func.coalesce(c.voucher_type, sa.literal_column("''")), c.voucher_no)
    return (c.company_code, *cols) if with_company else cols


def voucher_key_tuple(table: Any, *, with_company: bool = True) -> sa.Tuple:
    return sa.tuple_(*voucher_key_sql(table, with_company=with_company))


#: 一条语句里行值 IN / NOT IN 最多放这么多个凭证键：每键 4 个绑定参数，asyncpg 单语句上限 32,767 个，
#: 同一语句还有项目、日期、科目、行 id 等参数，留出余量。超过时抛 ValueError（抽凭路由转 400 并说明原因），
#: 不让驱动报「参数过多」变成 500。拆成多段 IN 仍在同一语句里，不解决上限，所以不拆。
MAX_KEYS_PER_STATEMENT = 7000


def _key_values(keys: Iterable[VoucherKey]) -> list[tuple]:
    vals = sorted({k.sql_values() for k in keys})
    if len(vals) > MAX_KEYS_PER_STATEMENT:
        raise ValueError(
            f"一次要匹配的凭证有 {len(vals)} 张，超过单条查询上限 {MAX_KEYS_PER_STATEMENT} 张；"
            "请缩小范围（如只排除本底稿已抽的凭证）"
        )
    return vals


def voucher_keys_in(table: Any, keys: Iterable[VoucherKey]) -> sa.ColumnElement:
    vals = _key_values(keys)
    return voucher_key_tuple(table).in_(vals) if vals else sa.false()


def voucher_keys_not_in(table: Any, keys: Iterable[VoucherKey]) -> sa.ColumnElement:
    vals = _key_values(keys)
    return voucher_key_tuple(table).not_in(vals) if vals else sa.true()


def legacy_voucher_nos_condition(column: Any, voucher_nos: Iterable[Any], *, exclude: bool) -> sa.ColumnElement:
    """旧格式数据（只有凭证号的回填日志 / 登记行）的唯一入口：按凭证号整张匹配或排除。

    🔴 会连带同号别日、同日同号别凭证字的凭证 —— 只用于兼容旧数据，调用方须把「按旧口径」
    告诉用户（legacy_exclusion）。守卫 test_voucher_identity_single_source.py 只允许登记过的
    调用点使用它，其余地方一律按凭证键。
    """
    nos = sorted({norm_text(v) for v in voucher_nos if norm_text(v)})
    if not nos:
        return sa.true() if exclude else sa.false()
    return column.notin_(nos) if exclude else column.in_(nos)


def voucher_label(vk: VoucherKey) -> str:
    """界面与留痕里的凭证称呼：「2025-01-07 FY-0003」（凭证字为空时只写号）。"""
    no = f"{vk.voucher_type}-{vk.voucher_no}" if vk.voucher_type else vk.voucher_no
    return f"{vk.voucher_date} {no}".strip()


async def resolve_line_fps(
    db: Any,
    *,
    project_id: UUID,
    year: int,
    fps: Iterable[str],
    force_dataset_id: UUID | None = None,
) -> dict[str, UUID]:
    """把分录指纹解析成「当前数据集」里的分录行 id。

    账套重导后行 id 全换（真库 26 个被替换版本里 16 个已清空行），排除、去重、存续核对一律
    存指纹、用时解析。只按指纹涉及的 (主体, 日期, 凭证字, 号, 科目) 小范围取行，在 Python
    端分组编号后匹配；解析不了的指纹（格式错或当前账套里没有）不出现在结果里。
    """
    from app.models.audit_platform_models import TbLedger
    from app.services.dataset_query import get_active_filter

    wanted: dict[str, LineFingerprint] = {}
    for fp in fps:
        try:
            wanted[fp] = LineFingerprint.parse(fp)
        except ValueError:
            continue
    if not wanted:
        return {}
    probes = sorted({(*p.vk.sql_values(), p.account_code) for p in wanted.values()})
    tbl = TbLedger.__table__
    active = await get_active_filter(db, tbl, project_id, year, force_dataset_id=force_dataset_id)
    probe_tuple = sa.tuple_(*voucher_key_sql(tbl), tbl.c.account_code)
    result: dict[str, UUID] = {}
    for start in range(0, len(probes), _RESOLVE_CHUNK):
        chunk = probes[start : start + _RESOLVE_CHUNK]
        stmt = sa.select(
            tbl.c.id, tbl.c.year, tbl.c.company_code, tbl.c.voucher_date, tbl.c.voucher_type,
            tbl.c.voucher_no, tbl.c.account_code, tbl.c.debit_amount, tbl.c.credit_amount, tbl.c.summary,
        ).where(active, probe_tuple.in_(chunk))
        rows = (await db.execute(stmt)).mappings().all()
        for fp, row in zip(fingerprint_lines(rows), rows):
            if fp in wanted:
                result[fp] = row["id"]
    return result
