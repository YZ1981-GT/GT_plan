"""公式目录：全平台公式位的单一可查询目录（spec unified-formula-registry Phase 2）。

``build_catalog`` 对每个域调 ``effective_slots()``，返回扁平列表，每项是一个
``CatalogEntry``（含 addr_id / domain / 可读公式文本 / 层级 / 引用函数列表）。

目录是只读视图，不引入新存储——所有数据来自既有的 ``effective_slots`` + 当前 ``_REGISTRY``。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings.definitions import DOMAINS
from app.services.formula_settings.dependencies import FORMULA_FIELDS, formula_text
from app.services.formula_settings.effective import effective_slots

# 从 formula_engine 取已注册函数名，构建提取正则（延迟编译）
_FUNC_RE: re.Pattern | None = None


def _get_func_re() -> re.Pattern:
    global _FUNC_RE
    if _FUNC_RE is None:
        from app.services.formula_engine import _REGISTRY
        names = sorted(_REGISTRY.known_function_names(), key=len, reverse=True)
        _FUNC_RE = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\s*\(")
    return _FUNC_RE


def extract_function_names(text: str) -> list[str]:
    """从公式文本提取引用的函数名（去重、按出现顺序）。"""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _get_func_re().finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


@dataclass
class CatalogEntry:
    addr_id: str
    domain: str
    slot_key: str
    formula_text: str
    layer: str
    function_refs: list[str] = field(default_factory=list)
    target_label: str = ""


def _slot_to_addr(domain: str, slot_key: str) -> str:
    """slot_key → ACNR 风格 addr_id。"""
    if domain == "report":
        # slot_key = "balance_sheet:BS-002" → addr_id = "report:balance_sheet:BS-002"
        return f"report:{slot_key}"
    if domain == "wp":
        # slot_key = "D2|审定表D2-1|E100" → addr_id = "wp:D2/审定表D2-1/E100"
        return f"wp:{slot_key.replace('|', '/')}"
    if domain == "note":
        # slot_key = "五、1|应收账款:value" → addr_id = "note:五、1" (章节级)
        section = slot_key.partition("|")[0]
        return f"note:{section}"
    # cross_check / tb_detail / consol_note 直接加前缀
    return f"{domain}:{slot_key}"


async def build_catalog(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    domains: Iterable[str] | None = None,
) -> list[CatalogEntry]:
    """本项目有效公式的扁平目录（跨域一次返回）。"""
    target_domains = list(domains) if domains else list(DOMAINS.keys())
    entries: list[CatalogEntry] = []
    for domain in target_domains:
        if domain not in DOMAINS:
            continue
        try:
            async with db.begin_nested():
                slots = await effective_slots(db, domain, project_id)
        except Exception:  # noqa: BLE001 — 单域失败不拖垮整个目录
            continue
        for key, slot in slots.items():
            text = formula_text(domain, slot.definition)
            if not text:
                continue  # 无公式文本的位不进目录
            entries.append(CatalogEntry(
                addr_id=_slot_to_addr(domain, key),
                domain=domain,
                slot_key=key,
                formula_text=text,
                layer=slot.layer,
                function_refs=extract_function_names(text),
                target_label=slot.label,
            ))
    return entries


async def catalog_stats(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> dict[str, Any]:
    """按域和按层级的公式计数摘要。"""
    entries = await build_catalog(db, project_id)
    by_domain: dict[str, int] = {}
    by_layer: dict[str, int] = {}
    by_function: dict[str, int] = {}
    for e in entries:
        by_domain[e.domain] = by_domain.get(e.domain, 0) + 1
        by_layer[e.layer] = by_layer.get(e.layer, 0) + 1
        for fn in e.function_refs:
            by_function[fn] = by_function.get(fn, 0) + 1
    return {
        "total": len(entries),
        "by_domain": by_domain,
        "by_layer": by_layer,
        "by_function": by_function,
        "domain_labels": {d: DOMAINS[d].label for d in DOMAINS},
    }
