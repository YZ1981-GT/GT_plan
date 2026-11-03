"""科目自动匹配：一级科目名校验与明细跟随（spec mapping-code-collision-and-fetch-by-mapping R1 / R2）。

``mapping_service._match_single`` 按编码命中标准科目后用这里核对客户一级科目名，防同码不同义（《企业会计制度》
1501 固定资产 ≠ 标准表 1501 持有至到期投资）；``find_code_collisions`` 给存量修复工具列出已有自动映射里的撞号。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.models.audit_platform_models import AccountChart, AccountMapping, AccountSource, MappingType
from app.models.audit_platform_schemas import MappingSuggestion
from app.services.account_name_compat import (
    level1_name_from_detail,
    name_key,
    reliable_level1_name,
    same_account,
    synonyms_of,
)

#: 父级科目靠名称模糊匹配认出来时，明细不跟随（模糊结果不可靠，各明细按自己的名称 / 编码匹配）
UNRELIABLE_PARENT_METHODS = frozenset({"fuzzy_name"})

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def strip_dot_zero(code: str | None) -> str:
    """剥掉表格读出的 ``.0`` 尾巴（``"1133.0"`` → ``"1133"``），与试算表 ``tb_mapping_sql.normalized_code`` 同口径。"""
    s = str(code or "").strip()
    return s[:-2] if s.endswith(".0") and s[:-2].isdigit() else s


def level1_code(code: str | None) -> str:
    """一级码：分隔符前一段，纯数字取前 4 位（先剥「.0」）。"""
    s = strip_dot_zero(code)
    for sep in (".", "-", "/", "_", "\\", " "):
        if sep in s:
            return s.split(sep)[0]
    return s[:4] if len(s) >= 4 else s


def is_level1(code: str | None) -> bool:
    return level1_code(code) == strip_dot_zero(code)


def std_level1_name(std_code: str, std_by_code: dict[str, AccountChart]) -> str | None:
    head = std_by_code.get(level1_code(std_code))
    return head.account_name if head is not None else std_by_code[std_code].account_name


def mapping_type_for(confidence: float) -> MappingType:
    """自动匹配落库的映射方式：置信度 ≥ 0.92 记「自动（精确）」，否则「自动（模糊）」。"""
    return MappingType.auto_exact if confidence >= 0.92 else MappingType.auto_fuzzy


def suggest(client: AccountChart, std: AccountChart, confidence: float, method: str) -> MappingSuggestion:
    return MappingSuggestion(
        original_account_code=client.account_code,
        original_account_name=client.account_name,
        suggested_standard_code=std.account_code,
        suggested_standard_name=std.account_name,
        confidence=confidence,
        match_method=method,
    )


def inherit(client: AccountChart, parent: MappingSuggestion, std_by_code: dict[str, AccountChart]) -> MappingSuggestion:
    """明细跟随所属一级科目的匹配结果。"""
    std = std_by_code.get(parent.suggested_standard_code)
    return MappingSuggestion(
        original_account_code=client.account_code,
        original_account_name=client.account_name,
        suggested_standard_code=parent.suggested_standard_code,
        suggested_standard_name=std.account_name if std is not None else parent.suggested_standard_name,
        confidence=min(parent.confidence, 0.97),
        match_method="inherit_parent",
    )


#: ``code_and_level1_step`` 的「确定不自动映射」（与 None =「本步没结论，交给后面的名称匹配」区分）
NO_MATCH = object()


def code_and_level1_step(
    client: AccountChart,
    std_by_code: dict[str, AccountChart],
    index: dict[str, AccountChart],
    *,
    normalized: str,
    prefix: str,
    level1_name: str | None,
    is_level1: bool,
    parent_suggestion: MappingSuggestion | None,
    has_level1_row: bool,
) -> MappingSuggestion | object | None:
    """自动匹配的编码段 + 一级科目段（``mapping_service._match_single`` 调用）。

    - 按编码命中（完整码 → 前 4 位 → 分隔符前一级码）后核对客户一级科目名 ``level1_name`` 与标准一级科目名：
      兼容 ⇒ 按编码认；不兼容（编码撞号，《企业会计制度》1501 固定资产 ≠ 1501 持有至到期投资）⇒ 不按编码认。
    - 明细：编码认不出 / 撞号时跟随所属一级科目（``parent_suggestion``）。
    - 撞号：按一级科目名找（全等 / 同义表）；找不到 ⇒ ``NO_MATCH``（留给人工）。
    - 一级科目行存在但没配上（``has_level1_row``）⇒ 明细 ``NO_MATCH``（不按明细自己的名称猜）。
    - 一级科目名全等 / 同义表命中（应付工资 → 应付职工薪酬）先于名称模糊匹配；一级科目本身只在同义表命中时在此返回。
    返回 None ⇒ 交给调用方后续的名称全等 / 去后缀 / 模糊匹配。
    """
    level1 = level1_code(client.account_code)
    tiers = [(normalized, 1.0, "exact_code"), (prefix, 0.98, "prefix")]
    if level1 != prefix:
        tiers.append((level1, 0.96, "level1_prefix"))
    collided = False
    for candidate, confidence, method in tiers:
        if candidate not in std_by_code:
            continue
        if level1_name and not same_account(level1_name, std_level1_name(candidate, std_by_code)):
            collided = True
            break
        return suggest(client, std_by_code[candidate], confidence, method)
    if not is_level1 and parent_suggestion is not None:
        return inherit(client, parent_suggestion, std_by_code)
    if collided:
        hit = match_by_level1_name(level1_name, index)
        return suggest(client, hit[0], 0.95 if is_level1 else 0.94, hit[1]) if hit else NO_MATCH
    if not is_level1 and has_level1_row:
        return NO_MATCH
    if level1_name:
        hit = match_by_level1_name(level1_name, index)
        if hit is not None and (not is_level1 or hit[1] == "level1_synonym"):
            return suggest(client, hit[0], 0.95 if is_level1 else 0.94, hit[1])
    return None


def std_name_index(standard_accounts: list[AccountChart]) -> dict[str, AccountChart]:
    """归一名称 → 标准一级科目；同名多码（5001 / 6001 主营业务收入）取 6xxx 新码，否则取编码最小的。"""
    index: dict[str, AccountChart] = {}
    for a in sorted(standard_accounts, key=lambda a: (not a.account_code.startswith("6"), a.account_code)):
        if is_level1(a.account_code):  # 只认一级科目（1231-01 坏账准备-应收票据 这类二级不参与）
            index.setdefault(name_key(a.account_name), a)
    return index


def match_by_level1_name(name: str, index: dict[str, AccountChart]) -> tuple[AccountChart, str] | None:
    """一级科目名 → 标准一级科目：全等，再同义表（不做模糊）。"""
    hit = index.get(name_key(name))
    if hit is not None:
        return hit, "level1_name"
    for alias in synonyms_of(name):
        hit = index.get(name_key(alias))
        if hit is not None:
            return hit, "level1_synonym"
    return None


def normalize_code(code: str | None) -> str:
    """剥「.0」后去掉全部分隔符（``"4001.01"`` → ``"400101"``），与 ``mapping_service`` 按完整码查标准科目同口径。"""
    s = strip_dot_zero(code)
    for sep in (".", "-", "/", "_", "\\", " "):
        s = s.replace(sep, "")
    return s


def _derived_level1(details: list[AccountChart], index: dict[str, AccountChart]) -> str | None:
    """没有一级科目行时推一级科目名：每个明细取「分隔符前一段」（没有分隔符取全名），只认能全等 / 同义对上
    标准一级科目的；全部对上的指向同一个标准一级科目才用（取该标准科目名），否则不推（不做名称校验，按编码认）。

    北京那份账没有一级科目行、明细叫「人工费用-工资」（第二级名）：「人工费用」对不上标准一级科目 ⇒ 不推，照常按 6601 认；
    辽宁「实收资本_国有资本」「实收资本_民营资本」都对上 3001 ⇒ 推出「实收资本」，4001 生产成本按撞号处理。
    """
    hits: set[str] = set()
    for c in details:
        candidate = level1_name_from_detail(c.account_name) or reliable_level1_name(c.account_name)
        hit = match_by_level1_name(candidate, index) if candidate else None
        if hit is not None:
            hits.add(hit[0].account_code)
    if len(hits) != 1:
        return None
    code = hits.pop()
    return next(a.account_name for a in index.values() if a.account_code == code)


def client_level1_context(
    client_accounts: list[AccountChart], index: dict[str, AccountChart],
) -> tuple[dict[str, AccountChart], dict[int, tuple[str | None, bool]]]:
    """``(一级科目行, {id(客户科目): (一级科目名, 有没有一级科目行)})``。

    一级科目名：有一级科目行用该行名称（以「\\」开头的旧导入名称不可信 ⇒ None）；没有时由同一一级码下的明细推（``_derived_level1``）。
    """
    heads: dict[str, AccountChart] = {}
    groups: dict[str, list[AccountChart]] = {}
    for c in client_accounts:
        if is_level1(c.account_code):
            heads.setdefault(strip_dot_zero(c.account_code), c)
        groups.setdefault(level1_code(c.account_code), []).append(c)
    derived = {l1: _derived_level1(items, index) for l1, items in groups.items() if l1 not in heads}
    ctx: dict[int, tuple[str | None, bool]] = {}
    for c in client_accounts:
        l1 = level1_code(c.account_code)
        head = heads.get(l1)
        ctx[id(c)] = (reliable_level1_name(head.account_name) if head is not None else derived.get(l1), head is not None)
    return heads, ctx


async def find_code_collisions(project_id: UUID, db: AsyncSession, year: int | None = None) -> list[dict]:
    """已有自动映射里「按编码认、但一级科目名对不上」的（编码撞号），附新规则的建议。

    只看标准科目码 = 客户科目本码 / 一级码的自动映射（按编码认出来的）；按名称 / 模糊匹配出来的不在此列。
    """
    import sqlalchemy as sa

    from app.services import mapping_service

    std_by_code = {a.account_code: a for a in (await db.execute(sa.select(AccountChart).where(
        AccountChart.project_id == project_id, AccountChart.source == AccountSource.standard,
        AccountChart.is_deleted == sa.false()))).scalars().all()}
    clients = (await db.execute(sa.select(AccountChart).where(
        *await mapping_service._client_account_filters(project_id, db, year)))).scalars().all()
    _, ctx = client_level1_context(list(clients), std_name_index(list(std_by_code.values())))
    names = {strip_dot_zero(c.account_code): ctx[id(c)][0] for c in clients}
    suggestions = {strip_dot_zero(s.original_account_code): s
                   for s in await mapping_service.auto_suggest(project_id, db, year=year)}
    rows = (await db.execute(sa.select(AccountMapping).where(
        AccountMapping.project_id == project_id, AccountMapping.is_deleted == sa.false(),
        AccountMapping.mapping_type.in_([MappingType.auto_exact, MappingType.auto_fuzzy])))).scalars().all()
    out = []
    for m in rows:
        code = strip_dot_zero(m.original_account_code)
        std = m.standard_account_code
        # 按编码认出来的：本码 / 去分隔符的完整码（4001.01 → 400101）/ 前 4 位 / 一级码
        if std not in std_by_code or std not in (code, normalize_code(code), normalize_code(code)[:4], level1_code(code)):
            continue
        name = names.get(code)
        if not name or same_account(name, std_level1_name(std, std_by_code)):
            continue
        new = suggestions.get(code)
        out.append({
            "mapping_id": m.id, "code": m.original_account_code, "level1_name": name,
            "old_code": std, "old_name": std_by_code[std].account_name,
            "new_code": new.suggested_standard_code if new else None,
            "new_name": new.suggested_standard_name if new else None,
            "method": new.match_method if new else None,
        })
    return out
