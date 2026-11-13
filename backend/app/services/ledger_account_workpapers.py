"""余额表科目 → 该科目的底稿（审定表优先），供查账页右键「跳转到底稿」使用。

数据来源：``wp_account_mapping.json``（经 ``wp_mapping_service`` 读取，不各自拼路径读 json）。

- 科目匹配：取映射表里**最长的、等于该科目或是它前缀**的科目码（``1002.01`` → ``1002``，``1122.01.03`` → ``1122``）；
  不用短前缀兜底，避免 ``1`` 之类把所有科目都匹配上。
- 分类：名称含「审定表」的条目是审定表（``audit_determination``，如 ``E1-1 货币资金审定表``、``D2 应收账款审定表``）；
  ``is_primary`` 的是循环主底稿（``primary``）；其余是 ``other``。排序 审定表 → 主底稿 → 其他，同类按编码自然序。
- 落到哪本底稿：审定表常是主册里的一个 sheet（``E1-1`` 在底稿 ``E1`` 里），所以按「编码 → 去掉末段 → …」找本项目已生成的
  底稿；``wp_id`` 为空表示本项目还没生成（前端提示并回到底稿目录高亮）。``sheet`` 给原映射编码，编辑器按 ``?sheet=`` 定位，
  对不上时落默认页。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.wp_mapping_service import _load_mappings

MAX_ITEMS = 30
KIND_ORDER = {"audit_determination": 0, "primary": 1, "other": 2}


@dataclass(frozen=True)
class AccountWorkpaper:
    wp_code: str
    wp_name: str
    kind: str  # audit_determination | primary | other
    host_wp_code: str | None  # 本项目已生成的所在底稿编码；None = 未生成
    wp_id: str | None


def _natural_key(code: str) -> list:
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", code) if p]


def match_mapped_account(code: str, mapped_codes: set[str]) -> str | None:
    """最长的「等于或为前缀」的映射科目码；没有返回 None。"""
    code = (code or "").strip()
    if not code:
        return None
    best: str | None = None
    for mapped in mapped_codes:
        if code == mapped or code.startswith(mapped):
            # 前缀必须落在层级边界上（1002 匹配 1002.01，但不匹配 10021）
            if code != mapped and code[len(mapped)] not in ".-_ ":
                continue
            if best is None or len(mapped) > len(best):
                best = mapped
    return best


def classify(entry: dict) -> str:
    name = str(entry.get("wp_name") or "")
    if "审定表" in name:
        return "audit_determination"
    if entry.get("is_primary"):
        return "primary"
    return "other"


def candidate_entries(account_code: str) -> tuple[str | None, list[dict]]:
    """(命中的映射科目码, 排好序的映射条目)。"""
    mappings = _load_mappings()
    mapped_codes = {c for m in mappings for c in (m.get("account_codes") or [])}
    matched = match_mapped_account(account_code, mapped_codes)
    if matched is None:
        return None, []
    entries = [m for m in mappings if matched in (m.get("account_codes") or []) and m.get("wp_code")]
    def _key(m: dict):
        kind = classify(m)
        # 审定表里带明确 sheet 编码的（D2-1、E1-1）排前，深链能直接落到那个 sheet；单独的主册编码（D2）排后
        explicit_sheet_first = 0 if (kind == "audit_determination" and "-" in str(m["wp_code"])) else 1
        return (KIND_ORDER[kind], explicit_sheet_first, _natural_key(str(m["wp_code"])))

    entries.sort(key=_key)
    return matched, entries[:MAX_ITEMS]


def _host_candidates(wp_code: str) -> list[str]:
    """E1-1 → [E1-1, E1]；D2 → [D2]。"""
    parts = wp_code.split("-")
    return ["-".join(parts[:i]) for i in range(len(parts), 0, -1)]


async def resolve_account_workpapers(
    db: AsyncSession, project_id: UUID, account_code: str,
) -> tuple[str | None, list[AccountWorkpaper]]:
    matched, entries = candidate_entries(account_code)
    if not entries:
        return matched, []
    wanted = {h for m in entries for h in _host_candidates(str(m["wp_code"]))}
    rows = (await db.execute(
        sa.select(WorkingPaper.id, WpIndex.wp_code)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(),
               WpIndex.wp_code.in_(wanted))
        .order_by(WorkingPaper.created_at.desc())
    )).all()
    generated: dict[str, str] = {}
    for wp_id, code in rows:
        generated.setdefault(str(code), str(wp_id))  # 同编码多本取最新
    items: list[AccountWorkpaper] = []
    for m in entries:
        code = str(m["wp_code"])
        host = next((h for h in _host_candidates(code) if h in generated), None)
        items.append(AccountWorkpaper(
            wp_code=code, wp_name=str(m.get("wp_name") or ""), kind=classify(m),
            host_wp_code=host, wp_id=generated.get(host) if host else None,
        ))
    return matched, items
