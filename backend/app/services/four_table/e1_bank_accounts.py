"""E1 账户级取数共享件（`tb_aux_balance` 的 `银行账户` 维度）。

**为什么需要它**：客户的 `1002 银行存款` 在 `tb_balance` 里**不分户**（叶子恒 1 行），
而 E1-3「银行存款及其他货币资金明细表」要逐户列示、E1-10「已开立银行账户清单核对表」
要做账户完整性核对 —— 账户级明细的**唯一**来源是 `tb_aux_balance` 的
`aux_type='银行账户'` 维度，其 `aux_dimensions_raw` 一行即含全部维度组合：

    金融机构:YG0014,上海浦东发展银行;银行账户:58080155200000296

实测（2026-08-08，8 个项目）带 `get_active_filter` 后与 `tb_balance` 叶子**逐分勾稽成立**。

🔴 三条硬约束（每条都对应一次平台级 P0）：

1. `get_active_filter` 是 **`async def`** —— 漏 `await` 会让 `sa.and_(coroutine, ...)`
   抛异常，被本模块的 fail-open 吞成 warning ⇒ 账户清单恒空，且与「本项目无 aux 数据」
   **不可区分**（N5 与 D 循环各因此出过一次 P0）。禁裸写 `is_deleted == False`：
   实测 `0ec33ac9` 裸查 23 个账户 / active 22 个，多出的那个来自非 active dataset。
2. 归属不了的账户进 `unassigned` 而**不静默丢弃**（宁缺勿造）。
3. 勾稽不平时如实暴露差异，**不修正数据**。

spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/ (Task 4)
Requirements: 1.1~1.5, 1.8, 10.8, 10.9
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Mapping, Sequence
from uuid import UUID

import sqlalchemy as sa

logger = logging.getLogger(__name__)

#: aux 维度名 —— 银行账号
AUX_TYPE_BANK_ACCOUNT = "银行账户"
#: aux 维度名 —— 开户银行（同一行 `aux_dimensions_raw` 里并存）
AUX_DIM_INSTITUTION = "金融机构"

#: 勾稽容差（元）。与 `leaf_aggregation.resolve_leaf_totals` 同口径。
TOLERANCE = 0.005

#: 取数来源标签前缀（供溯源面板展示）
SOURCE_PREFIX = f"tb_aux_balance:{AUX_TYPE_BANK_ACCOUNT}"


# ─── 维度解析 ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AuxDimensions:
    """`aux_dimensions_raw` 的解析结果。

    `parsed_level` 三级降级，**任何一级都不臆造银行名**：

    - 1 = 账号 + 银行名都拿到（`金融机构:CODE,NAME;银行账户:NO`）
    - 2 = 只拿到账号（raw 里有 `银行账户:` 但无 `金融机构:`，或银行名为空）
    - 3 = raw 解析不出，账号退回 `aux_name`、银行名留空
    """

    account_no: str
    bank_name: str
    parsed_level: int

    @property
    def has_bank_name(self) -> bool:
        return bool(self.bank_name)


def _split_dimensions(raw: str) -> dict[str, str]:
    """`A:x;B:y` → `{'A': 'x', 'B': 'y'}`（分号分隔、首个冒号切分）。"""
    out: dict[str, str] = {}
    for seg in str(raw or "").split(";"):
        seg = seg.strip()
        if not seg or ":" not in seg:
            continue
        name, _, value = seg.partition(":")
        name = name.strip()
        if name:
            out[name] = value.strip()
    return out


def _institution_name(value: str) -> str:
    """`YG0014,上海浦东发展银行` → `上海浦东发展银行`（无逗号时整串即名称）。"""
    value = str(value or "").strip()
    if not value:
        return ""
    if "," in value:
        # 逗号后是名称；名称本身可能再含逗号，故只切第一个
        return value.split(",", 1)[1].strip()
    return value


def parse_aux_dimensions(raw: str | None, aux_name: str | None) -> AuxDimensions:
    """解析账户维度，三级降级。

    🔴 银行名拿不到时**留空**而不是拿 `aux_name` 顶替 —— `aux_name` 是账号，
    塞进「开户银行」列会让审计师看到一列账号当银行名（比留空更坏）。
    """
    dims = _split_dimensions(raw or "")
    account_no = dims.get(AUX_TYPE_BANK_ACCOUNT, "").strip()
    bank_name = _institution_name(dims.get(AUX_DIM_INSTITUTION, ""))

    if account_no and bank_name:
        return AuxDimensions(account_no=account_no, bank_name=bank_name, parsed_level=1)
    if account_no:
        return AuxDimensions(account_no=account_no, bank_name="", parsed_level=2)
    return AuxDimensions(
        account_no=str(aux_name or "").strip(), bank_name="", parsed_level=3
    )


# ─── 行模型 ───────────────────────────────────────────────────────────────────


@dataclass
class BankAccountRow:
    """一个银行账户（同一账号在 active dataset 内的多行已聚合）。"""

    account_code: str
    account_no: str
    bank_name: str
    currency: str
    opening: float
    debit: float
    credit: float
    closing: float
    slot: str | None = None
    source: str = ""
    parsed_level: int = 3
    #: 同一账号聚合了几行（>1 说明 active dataset 内该账号有多笔）
    row_count: int = 1

    def as_dict(self) -> dict:
        return {
            "account_code": self.account_code,
            "account_no": self.account_no,
            "bank_name": self.bank_name,
            "currency": self.currency,
            "opening": self.opening,
            "debit": self.debit,
            "credit": self.credit,
            "closing": self.closing,
            "slot": self.slot,
            "source": self.source,
            "parsed_level": self.parsed_level,
            "row_count": self.row_count,
        }


def _f(v: object) -> float:
    """`COALESCE(...,0)` 的 Python 侧对应 —— NULL 与缺失一律 0.0。"""
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ─── 取数 ─────────────────────────────────────────────────────────────────────


async def fetch_e1_bank_accounts(
    db,
    project_id: UUID | str,
    year: int,
    *,
    account_prefixes: Sequence[str],
) -> list[BankAccountRow]:
    """从 `tb_aux_balance` 取银行账户级明细。

    - 查询一律经 `await get_active_filter(...)`（**禁裸写 `is_deleted == False`**）
    - 按 `(account_code, 解析出的账号)` 聚合求和
    - 金额 `COALESCE(...,0)`
    - fail-open：异常返 `[]` + warning + rollback（不让取数失败打断整个 render）

    `account_prefixes` 为空时直接返 `[]`（不查库）—— 槽全 `found=False` 时的正常路径。
    """
    prefixes = [str(p).strip() for p in (account_prefixes or []) if str(p).strip()]
    if not prefixes:
        return []

    try:
        from app.models.audit_platform_models import TbAuxBalance
        from app.services.dataset_query import get_active_filter

        # 🔴 必须 await —— 见模块 docstring 约束 1
        active = await get_active_filter(
            db, TbAuxBalance.__table__, project_id, year
        )

        code_pred = sa.or_(
            *[TbAuxBalance.account_code.like(f"{p}%") for p in prefixes]
        )
        stmt = (
            sa.select(
                TbAuxBalance.account_code,
                TbAuxBalance.account_name,
                TbAuxBalance.aux_name,
                TbAuxBalance.aux_dimensions_raw,
                TbAuxBalance.currency_code,
                TbAuxBalance.opening_balance,
                TbAuxBalance.debit_amount,
                TbAuxBalance.credit_amount,
                TbAuxBalance.closing_balance,
            )
            .where(
                sa.and_(
                    active,
                    TbAuxBalance.aux_type == AUX_TYPE_BANK_ACCOUNT,
                    code_pred,
                )
            )
            .order_by(TbAuxBalance.account_code, TbAuxBalance.aux_name)
        )
        rows = (await db.execute(stmt)).all()
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.warning(
            "E1 账户级取数失败（project=%s year=%s prefixes=%s）：%s",
            project_id,
            year,
            prefixes,
            exc,
        )
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return []

    return aggregate_aux_rows(rows)


def aggregate_aux_rows(rows: Iterable) -> list[BankAccountRow]:
    """把 aux 原始行按 `(account_code, 账号)` 聚合成账户行（纯函数，供守卫直测）。

    实测 `a7fc75e5` 的 `1207014210004455` 在 active dataset 内有
    `+25,954,468.80` 与 `−25,874,468.80` 两笔 ⇒ 必须聚合，否则账户数虚高。
    """
    bucket: dict[tuple[str, str], BankAccountRow] = {}
    for r in rows:
        code = str(getattr(r, "account_code", "") or "").strip()
        dims = parse_aux_dimensions(
            getattr(r, "aux_dimensions_raw", None), getattr(r, "aux_name", None)
        )
        key = (code, dims.account_no)
        cur = str(getattr(r, "currency_code", "") or "").strip()
        existing = bucket.get(key)
        if existing is None:
            bucket[key] = BankAccountRow(
                account_code=code,
                account_no=dims.account_no,
                bank_name=dims.bank_name,
                currency=cur,
                opening=_f(getattr(r, "opening_balance", None)),
                debit=_f(getattr(r, "debit_amount", None)),
                credit=_f(getattr(r, "credit_amount", None)),
                closing=_f(getattr(r, "closing_balance", None)),
                source=f"{SOURCE_PREFIX}:{dims.account_no}",
                parsed_level=dims.parsed_level,
            )
            continue
        existing.opening += _f(getattr(r, "opening_balance", None))
        existing.debit += _f(getattr(r, "debit_amount", None))
        existing.credit += _f(getattr(r, "credit_amount", None))
        existing.closing += _f(getattr(r, "closing_balance", None))
        existing.row_count += 1
        # 解析质量取更好的那一级；银行名以先拿到的非空值为准
        if dims.parsed_level < existing.parsed_level:
            existing.parsed_level = dims.parsed_level
        if not existing.bank_name and dims.bank_name:
            existing.bank_name = dims.bank_name
    return list(bucket.values())


# ─── 归属与勾稽 ───────────────────────────────────────────────────────────────


@dataclass
class SlotAssignment:
    """账户按语义槽归属的结果。`unassigned` 显式保留，禁兜底。"""

    by_slot: dict[str, list[BankAccountRow]] = field(default_factory=dict)
    unassigned: list[BankAccountRow] = field(default_factory=list)


def _code_matches_prefix(code: str, prefix: str) -> bool:
    """科目码前缀匹配 —— **必须带点号边界**。

    🔴 裸 `code.startswith(prefix)` 会让 `10021` 被 `1002` 吞掉（平台已踩过：
    `_is_leaf` 缺点号边界让 `1002.1` 被 `1002.11` 误判）。口径与共享件
    `leaf_aggregation.filter_by_prefixes` 逐字一致：`code == p or code.startswith(p + '.')`。
    """
    return code == prefix or code.startswith(prefix + ".")


def assign_accounts_to_slots(
    rows: Sequence[BankAccountRow],
    slot_codes: Mapping[str, Sequence[str]],
) -> SlotAssignment:
    """按槽的**原始码前缀**归属账户。

    多个槽都能匹配时取**最长前缀**（避免父子码双算，同 `sumLongestPrefixOnly` 口径）。
    一个槽都不中的进 `unassigned` —— 语义是「aux 里有账户但科目定位未覆盖」，
    必须让审计师看见，不能静默丢弃也不能塞进某个槽。
    """
    out = SlotAssignment(by_slot={k: [] for k in slot_codes})
    for row in rows:
        best_slot: str | None = None
        best_len = -1
        for slot, codes in slot_codes.items():
            for code in codes or []:
                c = str(code).strip()
                if c and _code_matches_prefix(row.account_code, c) and len(c) > best_len:
                    best_slot, best_len = slot, len(c)
        if best_slot is None:
            row.slot = None
            out.unassigned.append(row)
        else:
            row.slot = best_slot
            out.by_slot[best_slot].append(row)
    return out


def check_accounts_vs_leaves(
    slot_accounts: Mapping[str, Sequence[BankAccountRow]],
    slot_leaves: Mapping[str, float],
) -> dict[str, dict[str, float | bool]]:
    """三口径勾稽：账户合计 / 叶子合计 / 差异。**不修正数据**。

    只对**两侧都有数据**的槽产出条目（缺一侧时「不平」没有意义）。
    """
    out: dict[str, dict[str, float | bool]] = {}
    for slot, accounts in slot_accounts.items():
        if not accounts:
            continue
        if slot not in slot_leaves:
            continue
        acc_sum = round(sum(a.closing for a in accounts), 2)
        leaf_sum = round(_f(slot_leaves.get(slot)), 2)
        diff = round(acc_sum - leaf_sum, 2)
        out[slot] = {
            "account_sum": acc_sum,
            "leaf_sum": leaf_sum,
            "diff": diff,
            "ok": abs(diff) <= TOLERANCE,
        }
    return out


def build_e1_account_prefill(
    assignment: SlotAssignment,
    slot_leaves: Mapping[str, float] | None = None,
) -> dict:
    """产出 render 下发的 `account_prefill` 载荷。

    形态（前端 `normalizeAccountPrefill` 的契约）：

        {
          "accounts": {"bank": [...], "other": [...], "finance_co": [...],
                       "unassigned": [...]},
          "reconcile": {"bank": {"account_sum","leaf_sum","diff","ok"}},
          "meta": {"source", "account_count", "parsed_level_dist"}
        }

    🔴 无数据时 `accounts` 各键为 `[]`（不是缺键）—— 前端据此退回叶子口径。
    """
    accounts = {slot: [r.as_dict() for r in rows] for slot, rows in assignment.by_slot.items()}
    accounts["unassigned"] = [r.as_dict() for r in assignment.unassigned]

    all_rows = [r for rows in assignment.by_slot.values() for r in rows]
    all_rows += list(assignment.unassigned)
    dist: dict[str, int] = {}
    for r in all_rows:
        dist[str(r.parsed_level)] = dist.get(str(r.parsed_level), 0) + 1

    return {
        "accounts": accounts,
        "reconcile": check_accounts_vs_leaves(assignment.by_slot, slot_leaves or {}),
        "meta": {
            "source": SOURCE_PREFIX,
            "account_count": len(all_rows),
            "parsed_level_dist": dist,
        },
    }
