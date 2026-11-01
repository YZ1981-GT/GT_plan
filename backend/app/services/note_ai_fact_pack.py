"""附注 AI 叙述使用的服务端权威事实包。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import DisclosureEngine


class NoteFactPackUnavailable(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class NoteFactPack:
    note_id: UUID
    note_section: str
    section_title: str
    account_name: str
    year: int
    current_data: Any
    prior_data: Any
    source_refs: tuple[dict[str, Any], ...]

    def prompt_text(self, *, max_chars_each: int = 4000) -> str:
        current = _compact_json(self.current_data, max_chars_each)
        prior = _compact_json(self.prior_data, max_chars_each)
        return (
            f"附注章节：{self.note_section} {self.section_title}\n"
            f"相关科目：{self.account_name or '未指定'}\n"
            f"本期（{self.year} 年）权威数据：{current}\n"
            f"上期权威数据：{prior}"
        )

    def derived_fact_tokens(self, *, limit: int = 60) -> tuple[str, ...]:
        """变动额与变动率：本期、上期各数值两两相减 / 相除。

        只交给验证器作为“可由权威事实推导”的数字（ADR-LLM-012），不进入 prompt；
        模型写出的变动额 / 变动率必须能由事实包里的某一对本期、上期数值算出。
        """
        current = _numbers(self.current_data)[:limit]
        prior = _numbers(self.prior_data)[:limit]
        steps = (Decimal("0.01"), Decimal("0.1"), Decimal(1))
        tokens: set[str] = set()
        for cur in current:
            for pre in prior:
                diff = cur - pre
                for value in (diff, abs(diff)):
                    tokens.add(str(value))
                    tokens.update(str(value.quantize(step, rounding=ROUND_HALF_UP)) for step in steps)
                if pre != 0:
                    ratio = diff / abs(pre) * 100
                    for value in (ratio, abs(ratio)):
                        tokens.update(
                            f"{value.quantize(step, rounding=ROUND_HALF_UP)}%" for step in steps
                        )
        return tuple(sorted(tokens))


async def build_note_fact_pack(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    note_section: str,
) -> NoteFactPack:
    """从附注实例和统一上年读取器构建事实包；缺数据时不让模型猜原因。"""
    row = (
        await db.execute(
            sa.select(
                DisclosureNote.id,
                DisclosureNote.note_section,
                DisclosureNote.section_title,
                DisclosureNote.account_name,
                DisclosureNote.table_data,
                DisclosureNote.is_stale,
            ).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == note_section,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
    ).first()
    if row is None:
        raise NoteFactPackUnavailable("note_not_found", "附注章节尚未生成")
    if row.is_stale:
        raise NoteFactPackUnavailable(
            "stale_source", "本章节数据已过期，请先刷新附注再生成变动分析"
        )
    if not _has_numeric_fact(row.table_data):
        raise NoteFactPackUnavailable(
            "current_data_missing", "本章节没有可核对的本期表格数据"
        )

    prior = await DisclosureEngine(db).get_prior_year_data(
        project_id, year, note_section
    )
    prior_payload = (
        (prior.get("table_data") or prior.get("amounts"))
        if isinstance(prior, dict)
        else prior
    )
    if not _has_numeric_fact(prior_payload):
        raise NoteFactPackUnavailable(
            "prior_data_missing", "未找到本章节的上期附注或试算表数据"
        )

    return NoteFactPack(
        note_id=row.id,
        note_section=row.note_section,
        section_title=row.section_title or row.note_section,
        account_name=row.account_name or "",
        year=year,
        current_data=row.table_data,
        prior_data=prior,
        source_refs=(
            {
                "source_type": "note",
                "source_id": str(row.id),
                "year": year,
                "is_stale": False,
            },
            {
                "source_type": "prior_note_or_tb",
                "source_id": str(row.id),
                "year": year - 1,
                "is_stale": False,
            },
        ),
    )


def _compact_json(value: Any, limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return text if len(text) <= limit else text[:limit] + "…[已截断]"


def _numbers(value: Any) -> list[Decimal]:
    """按出现顺序收集去重后的数值；布尔、空串、非数字文本不算。"""
    found: list[Decimal] = []
    seen: set[Decimal] = set()

    def _walk(node: Any) -> None:
        if node is None or isinstance(node, bool):
            return
        if isinstance(node, (int, float, Decimal)):
            number = Decimal(str(node))
        elif isinstance(node, str):
            raw = node.strip().replace(",", "").removesuffix("%").strip()
            if not raw:
                return
            try:
                number = Decimal(raw)
            except InvalidOperation:
                return
        elif isinstance(node, dict):
            for child in node.values():
                _walk(child)
            return
        elif isinstance(node, (list, tuple, set)):
            for child in node:
                _walk(child)
            return
        else:
            return
        if number.is_finite() and number not in seen:
            seen.add(number)
            found.append(number)

    _walk(value)
    return found


def _has_numeric_fact(value: Any) -> bool:
    """是否含至少一个可核对数字；0 也是有效事实，标题/年份元数据不算。"""
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float, Decimal)):
        return True
    if isinstance(value, str):
        raw = value.strip().replace(",", "").removesuffix("%").strip()
        if not raw:
            return False
        try:
            Decimal(raw)
            return True
        except InvalidOperation:
            return False
    if isinstance(value, dict):
        return any(_has_numeric_fact(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_numeric_fact(v) for v in value)
    return False
