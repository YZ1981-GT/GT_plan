"""多借多贷精确配对（spec voucher-identity-writeback-and-audit-phase 需求 3，ADR-VK-05，design §3）。

一张凭证的分录 → 每条分录的对方科目与金额。只接受唯一解；配不上的标「多科目」并附整张
凭证分录与对方科目汇总，不按比例分摊、不推算金额（用户 2026-10-27 拍板）。纯函数、不查库：
抽凭结果（ledger_sampling_service.enrich_voucher_context）、凭证穿透
（ledger_penetration_service / drilldown_service）与挂凭回拉都经这里，前端只消费结果。

每条分录的结果（按分录指纹 line_fp 索引）：

- ``status``：paired 配上 / multi 无解或多解 / large 分录超过上限不做配对 / unknown_side 借贷栏不明
- ``basis``（paired 时）：single_side 本侧或对侧只有一条分录 · one_to_one 等额一对一 ·
  one_to_many 本行对对侧若干行 · many_to_one 本行是对侧某一行的若干分之一 ·
  single_account 对侧只有一个科目（科目级，对方金额 = 本行金额）
- ``counterparts``（paired 时）：``[{account_code, account_name, amount, line_fp}]``，金额合计
  等于本行金额；科目级配对的 line_fp 为 None
- ``counterpart_summary``（multi / large 时）：对侧分录按科目汇总，是「非配对」信息，只供查看

借贷栏、金额口径与分录指纹同源（voucher_identity）：红字按借贷栏 + 带符号金额参与，
多对多时红字只与红字凑、蓝字只与蓝字凑（需求 3.5）。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.services.voucher_identity import (
    SIDE_CREDIT,
    SIDE_DEBIT,
    SIDE_UNKNOWN,
    amount_str,
    fingerprint_lines,
    norm_text,
    side_of,
    signed_amount,
)

#: 分录超过这么多行的凭证不做配对（需求 3.6）
LINE_LIMIT = 200
#: 子集等额配对时子集最多几行（design §3 的 K）
MAX_SUBSET = 6
#: 一张凭证累计试探的组合数上限，超过即停止搜索、余下标 multi（design §3 第 4c 步）
COMBINATION_BUDGET = 50_000

PAIRED, MULTI, LARGE, UNKNOWN_SIDE = "paired", "multi", "large", "unknown_side"
MULTI_ACCOUNT_LABEL = "多科目"


@dataclass(frozen=True)
class _Line:
    fp: str
    side: str
    account_code: str
    account_name: str
    amount: Decimal  # 本行借贷栏上的带符号金额，已按分录指纹口径取两位小数

    @property
    def order(self) -> tuple:
        """规范顺序：输出与输入顺序无关（指纹含同组序号，是全序）。"""
        return (self.side, self.account_code, self.amount, self.fp)


class _Budget:
    def __init__(self, total: int):
        self.left = total

    def spend(self) -> None:
        self.left -= 1
        if self.left < 0:
            raise _BudgetExhausted


class _BudgetExhausted(Exception):
    pass


def _get(row: Any, name: str) -> Any:
    return row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)


def _normalize(lines: Sequence[Any]) -> list[_Line]:
    fps = [norm_text(_get(r, "line_fp")) for r in lines]
    if not all(fps):
        fps = fingerprint_lines(lines)
    if len(set(fps)) != len(fps):
        raise ValueError("分录指纹重复：配对的输入必须是同一张凭证的全部分录")
    out = []
    for row, fp in zip(lines, fps):
        debit, credit = _get(row, "debit_amount"), _get(row, "credit_amount")
        side = side_of(debit, credit)
        out.append(_Line(
            fp=fp,
            side=side,
            account_code=norm_text(_get(row, "account_code")),
            account_name=norm_text(_get(row, "account_name")),
            amount=Decimal(amount_str(signed_amount(debit, credit, side))),
        ))
    return sorted(out, key=lambda ln: ln.order)


def _opposite(side: str) -> str:
    return SIDE_CREDIT if side == SIDE_DEBIT else SIDE_DEBIT


def _summary(lines: Sequence[_Line]) -> list[dict]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    names: dict[str, str] = {}
    for ln in lines:
        totals[ln.account_code] += ln.amount
        if not names.get(ln.account_code):
            names[ln.account_code] = ln.account_name
    return [
        {"account_code": code, "account_name": names[code], "amount": amount_str(totals[code])}
        for code in sorted(totals)
    ]


def _result(status: str, *, basis: str | None = None, counterparts: Sequence[dict] = (),
            summary: Sequence[dict] = ()) -> dict:
    return {"status": status, "basis": basis, "counterparts": list(counterparts),
            "counterpart_summary": list(summary)}


def _counterpart(line: _Line, amount: Decimal) -> dict:
    return {"account_code": line.account_code, "account_name": line.account_name,
            "amount": amount_str(amount), "line_fp": line.fp}


class _Side:
    """一侧分录的科目汇总，整张凭证只算一次（华氏一张凭证 19,546 行，逐行重算是平方级）。"""

    def __init__(self, lines: Sequence[_Line]):
        self.lines = list(lines)
        self.summary = _summary(self.lines)

    def unpaired_result(self, own: _Line) -> dict:
        """本行没配上：对侧只有一个科目时给科目级结果（需求 3.1 后半，对方金额 = 本行金额，
        不指认对侧哪一行）；否则 multi / large 由调用方定，这里给 multi。"""
        if len(self.summary) == 1:
            only = self.summary[0]
            return _result(PAIRED, basis="single_account", counterparts=[{
                "account_code": only["account_code"], "account_name": only["account_name"],
                "amount": amount_str(own.amount), "line_fp": None,
            }])
        return _result(MULTI, summary=self.summary)


# ── 多对多 ────────────────────────────────────────────────────────────────


def _equal_candidates(free: dict[str, _Line]) -> dict[str, list[_Line]]:
    """每行在对侧未配对行里的等额候选（不论科目），按规范顺序。"""
    by_amount: dict[tuple[str, Decimal], list[_Line]] = defaultdict(list)
    for ln in sorted(free.values(), key=lambda x: x.order):
        by_amount[(ln.side, ln.amount)].append(ln)
    return {fp: by_amount.get((_opposite(ln.side), ln.amount), []) for fp, ln in free.items()}


def _one_to_one(free: dict[str, _Line], links: dict, basis: dict) -> bool:
    """第 4a 步：等额一对一。先只看不同科目，为空再看同科目；双方互为唯一候选才配。"""
    equal = _equal_candidates(free)
    preferred: dict[str, list[_Line]] = {}
    for fp, cands in equal.items():
        other_account = [c for c in cands if c.account_code != free[fp].account_code]
        preferred[fp] = other_account or cands
    pairs = []
    for fp, cands in preferred.items():
        x = free[fp]
        if x.side != SIDE_DEBIT or len(cands) != 1:
            continue
        y = cands[0]
        back = preferred[y.fp]
        if len(back) == 1 and back[0].fp == x.fp:
            pairs.append((x, y))
    for x, y in pairs:
        links[x.fp], links[y.fp] = [(y, y.amount)], [(x, x.amount)]
        basis[x.fp] = basis[y.fp] = "one_to_one"
        del free[x.fp], free[y.fp]
    return bool(pairs)


def _subsets_summing(pool: list[_Line], target: Decimal, budget: _Budget) -> list[tuple[_Line, ...]]:
    """pool 与 target 同号；返回金额和等于 target 的 2..MAX_SUBSET 行子集（按绝对值升序剪枝）。"""
    goal = abs(target)
    items = sorted(pool, key=lambda ln: (abs(ln.amount), ln.order))
    found: list[tuple[_Line, ...]] = []
    chosen: list[_Line] = []

    def dfs(start: int, acc: Decimal) -> None:
        for i in range(start, len(items)):
            budget.spend()
            total = acc + abs(items[i].amount)
            if total > goal:
                break  # 升序：后面的只会更大
            chosen.append(items[i])
            if total == goal:
                if len(chosen) >= 2:
                    found.append(tuple(chosen))
            elif len(chosen) < MAX_SUBSET:
                dfs(i + 1, total)
            chosen.pop()

    dfs(0, Decimal("0"))
    return found


def _subset_groups(free: dict[str, _Line], links: dict, basis: dict, budget: _Budget) -> bool:
    """第 4b 步：一对多 / 多对一的子集等额。

    组 = 一行 y + 对侧若干行 T（2..MAX_SUBSET 行，与 y 同号，金额和 = y）。一行的「解」=
    含它的组 + 它剩余的等额一对一可能（不论科目）。组里每一行的解都恰好是这一个组才接受
    —— 只看发起行唯一不够：E 只有 {E,F}→A 一个解，但 A 还有 {F,G} 这个解时，答案并不唯一。
    预算在本轮中途耗尽时本轮一个都不接受（没枚举完的解集数不出唯一性）。
    """
    lines = sorted(free.values(), key=lambda x: x.order)
    groups: list[tuple[_Line, tuple[_Line, ...]]] = []
    for y in lines:
        pool = [t for t in lines
                if t.side != y.side and (t.amount > 0) == (y.amount > 0) and abs(t.amount) < abs(y.amount)]
        if len(pool) >= 2:
            groups.extend((y, combo) for combo in _subsets_summing(pool, y.amount, budget))
    solutions: dict[str, int] = defaultdict(int)
    for y, combo in groups:
        for ln in (y, *combo):
            solutions[ln.fp] += 1
    for fp, cands in _equal_candidates(free).items():
        solutions[fp] += len(cands)
    accepted = [(y, combo) for y, combo in groups
                if all(solutions[ln.fp] == 1 for ln in (y, *combo))]
    for y, combo in accepted:
        links[y.fp] = [(t, t.amount) for t in combo]
        basis[y.fp] = "one_to_many"
        for t in combo:
            links[t.fp] = [(y, t.amount)]
            basis[t.fp] = "many_to_one"
            del free[t.fp]
        del free[y.fp]
    return bool(accepted)


def _many_to_many(debit: list[_Line], credit: list[_Line], links: dict, basis: dict) -> None:
    free = {ln.fp: ln for ln in (*debit, *credit)}
    budget = _Budget(COMBINATION_BUDGET)
    progress = True
    while progress and free:
        progress = _one_to_one(free, links, basis)
        try:
            progress = _subset_groups(free, links, basis, budget) or progress
        except _BudgetExhausted:
            return  # 第 4c 步：停止搜索，余下标 multi


def _validate(links: dict, basis: dict, lines: Sequence[_Line]) -> None:
    """第 6 步：每行的对方金额合计 = 本行金额，且对方行也把本行列为对方；违反的连同对方降为 multi。"""
    amount = {ln.fp: ln.amount for ln in lines}
    while True:
        bad: set[str] = set()
        for fp, cps in links.items():
            if sum((a for _, a in cps), Decimal("0")) != amount[fp]:
                bad.add(fp)
                bad.update(c.fp for c, _ in cps)
            for c, _ in cps:
                if fp not in {b.fp for b, _ in links.get(c.fp, ())}:
                    bad.update((fp, c.fp))
        bad &= set(links)
        if not bad:
            return
        for fp in bad:
            links.pop(fp, None)
            basis.pop(fp, None)


# ── 入口 ─────────────────────────────────────────────────────────────────


def pair_voucher(lines: Sequence[Any], *, limit: int = LINE_LIMIT) -> dict[str, dict]:
    """一张凭证的全部分录 → {line_fp: 配对结果}。

    lines 是 dict 或 ORM 行，需有 account_code / account_name / debit_amount / credit_amount，
    最好带 line_fp（没有则按分录指纹口径现算，此时还需凭证键各列）。
    """
    norm = _normalize(lines)
    out: dict[str, dict] = {ln.fp: _result(UNKNOWN_SIDE) for ln in norm if ln.side == SIDE_UNKNOWN}
    known = [ln for ln in norm if ln.side != SIDE_UNKNOWN]
    sides = {s: _Side([ln for ln in known if ln.side == s]) for s in (SIDE_DEBIT, SIDE_CREDIT)}

    if len(known) > limit:
        # 第 2 步：不做配对、不把整张凭证写进底稿行；对侧只有一个科目时科目是确定的，照给
        for ln in known:
            res = sides[_opposite(ln.side)].unpaired_result(ln)
            out[ln.fp] = res if res["status"] == PAIRED else _result(LARGE, summary=res["counterpart_summary"])
        return out

    links: dict[str, list[tuple[_Line, Decimal]]] = {}
    basis: dict[str, str] = {}
    debit, credit = sides[SIDE_DEBIT].lines, sides[SIDE_CREDIT].lines
    if debit and credit:
        if len(debit) == 1 or len(credit) == 1:
            # 第 3 步：一侧只有一条，对侧每条按各自金额列出（红蓝不限，需求 3.5 括注）
            one, many = (debit[0], credit) if len(debit) == 1 else (credit[0], debit)
            links[one.fp] = [(m, m.amount) for m in many]
            basis[one.fp] = "single_side"
            for m in many:
                links[m.fp] = [(one, m.amount)]
                basis[m.fp] = "single_side"
        else:
            _many_to_many(debit, credit, links, basis)
    _validate(links, basis, known)

    for ln in known:
        if ln.fp in links:
            out[ln.fp] = _result(PAIRED, basis=basis[ln.fp],
                                 counterparts=[_counterpart(c, a) for c, a in links[ln.fp]])
        else:
            out[ln.fp] = sides[_opposite(ln.side)].unpaired_result(ln)
    return out


def annotate_pairing(rows: list[dict]) -> list[dict]:
    """给一张凭证的分录行（已有 line_fp，见 voucher_identity.annotate_lines）补 ``pairing``，就地修改并返回。

    用于凭证穿透 / 下钻（响应里本就是整张凭证）：超过上限的凭证每行的对侧汇总相同，逐行重复
    会让响应成倍膨胀（华氏一张凭证 19,546 行、对侧 9~11 个科目，约多出 20 MB），这里不带，
    标 ``summary_omitted``；要汇总的看同一响应里的整张凭证。抽凭样本（enrich_voucher_context）
    行数少，照带汇总。
    """
    if rows:
        result = pair_voucher(rows)
        for row in rows:
            pairing = result.get(norm_text(row.get("line_fp")))
            if pairing and pairing["status"] == LARGE:
                pairing = {**pairing, "counterpart_summary": [], "summary_omitted": True}
            row["pairing"] = pairing
    return rows


def counterpart_label(pairing: Mapping[str, Any] | None) -> tuple[str, str] | None:
    """配对结果 → 旧字段 ``counterpart_account`` / ``counterpart_account_name`` 的取值。

    对方只有一个科目时填该科目，否则填「多科目」（详情看 ``pairing``）；借贷栏不明时不填。
    """
    if not pairing or pairing.get("status") == UNKNOWN_SIDE:
        return None
    rows = pairing.get("counterparts") or pairing.get("counterpart_summary") or []
    accounts = {(r.get("account_code") or "", r.get("account_name") or "") for r in rows}
    codes = {code for code, _ in accounts}
    if len(codes) == 1:
        code = next(iter(codes))
        name = next((n for c, n in sorted(accounts) if c == code and n), "")
        return code, name
    if codes:
        return MULTI_ACCOUNT_LABEL, MULTI_ACCOUNT_LABEL
    return None
