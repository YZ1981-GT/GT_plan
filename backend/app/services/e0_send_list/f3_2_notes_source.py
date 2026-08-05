"""F3-2 → E0-5 上游取数：从应付票据明细表取银承待函证行。

纯函数。render 期由 E0-5 策略调用，结果挂 `_prefill`。

选取条件：isConfirmed=='是' AND noteType 含「银行」。
供应链票据不进结果，只进 hints（承兑人可能非银行 = 会计判断）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


BANK_ACCEPTANCE_KEYWORD = "银行"
SUPPLY_CHAIN_KEYWORD = "供应链"

E05AmountCaliber = Literal["face", "audited"]
DEFAULT_E05_AMOUNT_CALIBER: E05AmountCaliber = "face"


@dataclass(frozen=True)
class F3NoteRow:
    """F3-2 一行（字段名对齐 composables/useF3Detail.ts）"""
    ticket_no: str
    note_type: str
    acceptor: str
    issue_date: str
    due_date: str
    face_value: float | None
    audited_amount: float | None
    deposit_amount: float | None
    deposit_ratio: float | None
    is_confirmed: str


def select_bank_acceptance_to_confirm(
    rows: list[dict],
) -> tuple[list[F3NoteRow], list[str]]:
    """返回 (待函证银承行, hints)。

    只取 is_confirmed=='是' and BANK_ACCEPTANCE_KEYWORD in note_type。
    供应链票据不进结果、只进 hints。
    """
    results: list[F3NoteRow] = []
    hints: list[str] = []
    supply_chain_count = 0

    for row in rows:
        note_type = str(row.get("noteType") or row.get("note_type") or "")
        is_confirmed = str(row.get("isConfirmed") or row.get("is_confirmed") or "")

        # 供应链票据单独计数
        if SUPPLY_CHAIN_KEYWORD in note_type:
            supply_chain_count += 1
            continue

        # 只取银承 + 已决定函证
        if BANK_ACCEPTANCE_KEYWORD not in note_type:
            continue
        if is_confirmed != "是":
            continue

        results.append(F3NoteRow(
            ticket_no=str(row.get("ticketNo") or row.get("ticket_no") or ""),
            note_type=note_type,
            acceptor=str(row.get("acceptor") or ""),
            issue_date=str(row.get("issueDate") or row.get("issue_date") or ""),
            due_date=str(row.get("dueDate") or row.get("due_date") or ""),
            face_value=_to_float(row.get("faceValue") or row.get("face_value")),
            audited_amount=_to_float(row.get("auditedAmount") or row.get("audited_amount")),
            deposit_amount=_to_float(row.get("depositAmount") or row.get("deposit_amount")),
            deposit_ratio=_to_float(row.get("depositRatio") or row.get("deposit_ratio")),
            is_confirmed=is_confirmed,
        ))

    if supply_chain_count:
        hints.append(
            f"F3-2 含 {supply_chain_count} 张供应链票据未自动带入，"
            "承兑人是否为银行需人工判断"
        )

    return results, hints


def build_e05_prefill(
    rows: list[dict],
    caliber: E05AmountCaliber = DEFAULT_E05_AMOUNT_CALIBER,
    tb_2201: float | None = None,
) -> dict | None:
    """构建 E0-5 的 transient prefill。无命中行 → None（宁缺勿造）。"""
    selected, hints = select_bank_acceptance_to_confirm(rows)
    if not selected:
        return None

    # 计算 bank_unconfirmed_count（银承中 isConfirmed != '是' 的数量）
    bank_unconfirmed = 0
    for row in rows:
        note_type = str(row.get("noteType") or row.get("note_type") or "")
        is_confirmed = str(row.get("isConfirmed") or row.get("is_confirmed") or "")
        if BANK_ACCEPTANCE_KEYWORD in note_type and is_confirmed != "是":
            bank_unconfirmed += 1

    prefill_rows = []
    for f3row in selected:
        amount = f3row.face_value if caliber == "face" else f3row.audited_amount
        prefill_rows.append({
            "bill_no": f3row.ticket_no,
            "bank_name": f3row.acceptor,
            "face_amount": amount,
            "audited_amount": f3row.audited_amount,
            "issue_date": f3row.issue_date,
            "due_date": f3row.due_date,
            "settle_account": None,  # F3-2 无此列
            "currency": None,  # F3-2 无此列
            "deposit_amount": f3row.deposit_amount,
            "deposit_ratio": f3row.deposit_ratio,
            "note_type": f3row.note_type,
        })

    return {
        "source": "明细表F3-2",
        "caliber": caliber,
        "caliber_note": "默认取 F3-2「票面金额」（与 E0-5 表头同名同义）；可切「期末审定数」",
        "tb_2201": tb_2201,
        "bank_unconfirmed_count": bank_unconfirmed,
        "hints": hints,
        "rows": prefill_rows,
    }


def _to_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None
