"""Property-based tests for AddressingService (Tasks 2.3–2.6, Properties P1–P4).

Spec: .kiro/specs/advanced-query-module (design.md Correctness Properties).

统一寻址层 `AddressingService` 封装 ACNR 的单一 `full_resolve` 出口（消费而非
重写 ACNR 核心）。这些属性测试在没有实时 catalog 的场景下 **mock/stub**
`full_resolve`（addressing_service 命名空间内），用受控的 `ResolveResult` 驱动
五域寻址、身份对齐、改名不变性与「全有或全无」归集逻辑。

每条属性用单个属性测试实现；按用户指令使用 `@settings(max_examples=5)` 让套件快速
运行（全局 conftest 亦有 fast profile，此处仍显式声明）。
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from hypothesis import assume, given, settings
from hypothesis import strategies as st

import app.services.custom_query.addressing_service as addr_mod
from app.services.custom_query.addressing_service import (
    AddressingService,
    ERR_CODE_TARGET_UNRESOLVABLE,
)
from app.services.acnr.resolver import ResolveResult


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _run(coro):
    """Run a coroutine to completion in a fresh event loop (per Hypothesis example)."""
    return asyncio.run(coro)


def _make_fake_resolve(registry: dict[str, str]):
    """Build a fake async `full_resolve` backed by a raw→canonical addr_id registry.

    The addressing layer classifies each input into exactly one full_resolve
    kwarg (uri / formula_ref / addr_id / index_ref); the value that reaches
    full_resolve is what we key the registry on. Registered inputs resolve to
    their canonical addr_id (found=True); anything else is a miss (found=False).
    """

    async def _fake_full_resolve(
        *,
        uri: str | None = None,
        formula_ref: str | None = None,
        addr_id: str | None = None,
        index_ref: str | None = None,
        project_id: str | None = None,
        db=None,
    ) -> ResolveResult:
        raw = uri or formula_ref or addr_id or index_ref
        canonical = registry.get(raw)
        if canonical is not None:
            return ResolveResult(
                found=True,
                addr_id=canonical,
                entry_type="cell",
                jump_route=f"/workpapers/x?sheet={canonical}",
            )
        return ResolveResult(found=False, error="miss", candidates=[])

    return _fake_full_resolve


# ─── Strategies ──────────────────────────────────────────────────────────────

# Safe source/label alphabet: letters, digits, Chinese, dash/underscore — no
# ':' '/' '#' '!' or quotes that would break URI / formula / addr_id syntax.
_safe_alphabet = st.characters(
    whitelist_categories=("Lu", "Ll", "Nd", "Lo"),
    whitelist_characters="-_",
)
_safe_text = (
    st.text(alphabet=_safe_alphabet, min_size=1, max_size=8)
    .map(lambda s: s.strip())
    .filter(lambda s: s != "")
)

_wp_code_st = st.from_regex(r"[A-N][0-9]{1,2}", fullmatch=True)
_sheet_code_st = st.from_regex(r"[A-N][0-9]{1,2}(-[0-9]{1,2})?", fullmatch=True)
_coord_st = st.from_regex(r"[A-Z]{1,2}[0-9]{1,3}", fullmatch=True)

_domain_st = st.sampled_from(["wp", "tb", "report", "note", "aux"])


@st.composite
def _five_domain_entry(draw):
    """Generate a single ACNR-registered content entry across the five domains.

    Returns (raw_input, canonical_addr_id) where raw_input is the exact string
    that reaches full_resolve after classification.
    """
    domain = draw(_domain_st)
    wp = draw(_wp_code_st)
    sheet = draw(_sheet_code_st)
    coord = draw(_coord_st)
    if domain == "wp":
        raw = f"{wp}/{sheet}/{coord}"  # bare addr_id → addr_id kwarg
        canonical = raw
    else:
        source = draw(_safe_text)
        raw = f"{domain}://{source}#{coord}"  # five-domain URI → uri kwarg
        canonical = f"{domain}://{source}/{coord}"
    return raw, canonical


# ─── Property 1: 通用寻址覆盖 (Task 2.3) ─────────────────────────────────────
# Feature: advanced-query-module, Property 1: 通用寻址覆盖 — For any ACNR catalog
# 已登记的五域 (tb/report/note/wp/aux) sheet/cell 条目，AddressingService.
# resolve_target 都应成功解析为非空 canonical addr_id 并纳入可查询字段集，不因内容
# 类型被任何固定白名单拒绝。


@settings(max_examples=5)
@given(entries=st.lists(_five_domain_entry(), min_size=1, max_size=8))
def test_p1_universal_addressing_coverage(entries):
    """Property 1: 通用寻址覆盖.

    **Validates: Requirements 1.1, 1.2**
    """
    # dedup by raw (later wins) so registry lookups are unambiguous
    registry = {raw: canonical for raw, canonical in entries}
    svc = AddressingService()

    async def _check():
        with patch.object(addr_mod, "full_resolve", _make_fake_resolve(registry)):
            for raw, canonical in registry.items():
                res = await svc.resolve_target(raw, project_id="proj-1")
                # 每个已登记内容都解析成功、addr_id 非空、不被固定白名单拒绝
                assert res.found is True, f"registered target rejected: {raw}"
                assert res.addr_id == canonical
                assert res.addr_id and res.addr_id.strip() != ""
                assert res.error is None

    _run(_check())


# ─── Property 2: addr_id 身份对齐与确定性 (Task 2.4) ─────────────────────────
# Feature: advanced-query-module, Property 2: addr_id 身份对齐与确定性 — For any
# 物理格，无论经选字段树 / 回写路径 / WP() 公式引用解析，得到的 addr_id 都逐字符相同；
# 且对同一格重复多次解析，结果恒定（确定性）。


@settings(max_examples=5)
@given(
    wp=_wp_code_st,
    sheet_code=_sheet_code_st,
    sheet_name=_safe_text,
    coord=_coord_st,
    repeats=st.integers(min_value=2, max_value=4),
)
def test_p2_addr_id_identity_alignment_and_determinism(
    wp, sheet_code, sheet_name, coord, repeats
):
    """Property 2: addr_id 身份对齐与确定性.

    **Validates: Requirements 2.5, 3.1, 3.2, 3.3**
    """
    canonical = f"{wp}/{sheet_code}/{coord}"
    field_tree_raw = canonical  # 选字段树选中 → 记录 addr_id
    writeback_raw = f"wp://{wp}/{sheet_name}#{coord}"  # 回写目标 → uri
    wp_formula_raw = f"WP('{wp}','{sheet_name}','{coord}')"  # WP() 公式引用

    # 三种物理格表示都归到同一 canonical addr_id（catalog 单源身份）
    registry = {
        field_tree_raw: canonical,
        writeback_raw: canonical,
        wp_formula_raw: canonical,
    }
    svc = AddressingService()

    async def _check():
        with patch.object(addr_mod, "full_resolve", _make_fake_resolve(registry)):
            seen: list[str] = []
            for raw in (field_tree_raw, writeback_raw, wp_formula_raw):
                for _ in range(repeats):
                    res = await svc.resolve_target(raw, project_id="proj-1")
                    assert res.found is True
                    seen.append(res.addr_id)
            # 三路径 + 多次重复：全部逐字符一致（身份对齐 + 确定性）
            assert len(set(seen)) == 1
            assert seen[0] == canonical

    _run(_check())


# ─── Property 3: addr_id 改名不变性 (Task 2.5) ───────────────────────────────
# Feature: advanced-query-module, Property 3: addr_id 改名不变性 — For any sheet
# 与任意 sheet 改名/别名变动，该 sheet 及其下单元格的 addr_id 保持不变，且仍能通过
# 稳定 addr_id 定位；已保存的查询字段 addr_id 不因改名失效或改变。


@settings(max_examples=5)
@given(
    wp=_wp_code_st,
    sheet_code=_sheet_code_st,
    coord=_coord_st,
    names=st.lists(_safe_text, min_size=2, max_size=5, unique=True),
)
def test_p3_addr_id_rename_invariance(wp, sheet_code, coord, names):
    """Property 3: addr_id 改名不变性.

    **Validates: Requirements 2.6**
    """
    canonical = f"{wp}/{sheet_code}/{coord}"
    # catalog 通过 sheet_name_aliases 吸收改名：任意 sheet 名（原名/别名）经 WP() 或
    # URI 解析都归到同一 canonical addr_id；已保存的裸 addr_id 更是恒定不变。
    registry: dict[str, str] = {canonical: canonical}
    formula_forms = []
    for nm in names:
        f_form = f"WP('{wp}','{nm}','{coord}')"
        u_form = f"wp://{wp}/{nm}#{coord}"
        registry[f_form] = canonical
        registry[u_form] = canonical
        formula_forms.extend([f_form, u_form])

    svc = AddressingService()

    async def _check():
        with patch.object(addr_mod, "full_resolve", _make_fake_resolve(registry)):
            # 已保存的查询字段（裸 addr_id）不因改名改变
            saved = await svc.resolve_target(canonical, project_id="proj-1")
            assert saved.found is True and saved.addr_id == canonical
            # 每个改名/别名扰动仍定位到相同 addr_id
            for raw in formula_forms:
                res = await svc.resolve_target(raw, project_id="proj-1")
                assert res.found is True
                assert res.addr_id == canonical

    _run(_check())


# ─── Property 4: 不可解析目标全有或全无 (Task 2.6) ───────────────────────────
# Feature: advanced-query-module, Property 4: 不可解析目标全有或全无 — For any
# 查询目标集合，只要其中存在至少一个无法被 Resolve_Service 解析为有效 addr_id 的目标，
# 系统就不执行查询、不返回任何部分结果，并逐项列出全部无法解析的目标标识。

_token_st = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=4,
    max_size=10,
).filter(lambda s: s != "")


@settings(max_examples=5)
@given(
    good=st.lists(_token_st, min_size=0, max_size=5, unique=True),
    bad=st.lists(_token_st, min_size=1, max_size=5, unique=True),
)
def test_p4_unresolvable_all_or_nothing(good, bad):
    """Property 4: 不可解析目标全有或全无.

    **Validates: Requirements 1.4**
    """
    assume(set(good).isdisjoint(set(bad)))
    # 只有 good 目标登记；bad 目标一律 miss
    registry = {g: f"ADDR/{g}" for g in good}
    svc = AddressingService()
    targets = good + bad  # 至少含一个不可解析目标

    async def _check():
        with patch.object(addr_mod, "full_resolve", _make_fake_resolve(registry)):
            outcome = await svc.resolve_all(targets, project_id="proj-1")
            # 存在不可解析目标 → 整体不执行、不返回部分结果
            assert outcome.ok is False
            assert outcome.resolved == []
            assert outcome.error_code == ERR_CODE_TARGET_UNRESOLVABLE
            # 逐项列出全部（且仅）无法解析的目标标识
            unresolved_raws = {u["raw"] for u in outcome.unresolved}
            assert unresolved_raws == set(bad)

    _run(_check())
