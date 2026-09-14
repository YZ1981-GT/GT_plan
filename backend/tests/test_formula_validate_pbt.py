# Feature: custom-workpaper-formula-binding, Property 6: 公式引用校验完备
"""validate_formula_refs：悬空引用 ⟺ issues 含 not_found。"""
from __future__ import annotations

import asyncio
import re
import uuid
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings, strategies as st

from app.services.address_registry import (
    AddressEntry,
    AddressRegistryService,
    formula_ref_to_uri,
)

_FORMULA_PATTERNS = re.compile(
    r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)|"
    r"TB\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _extract_refs(formula: str) -> set[str]:
    refs: set[str] = set()
    for m in _FORMULA_PATTERNS.finditer(formula):
        refs.add(m.group(0))
    return refs


wp_refs_st = st.lists(
    st.from_regex(r"WP\('[\w\-]+','[A-Z]+\d+'\)", fullmatch=True),
    min_size=0,
    max_size=4,
    unique=True,
)
tb_refs_st = st.lists(
    st.from_regex(r"TB\('\d{4}','[^']+'\)", fullmatch=True),
    min_size=0,
    max_size=2,
    unique=True,
)


@settings(max_examples=5)
@given(wp_refs=wp_refs_st, tb_refs=tb_refs_st)
def test_p6_validate_refs_matches_dangling(wp_refs: list[str], tb_refs: list[str]):
    formula = " + ".join(wp_refs + tb_refs) or "1"
    known_wp = {r for r in wp_refs[: max(0, len(wp_refs) - 1)]}
    known_tb = {r for r in tb_refs[: max(0, len(tb_refs) - 1)]}

    wp_entries = []
    for ref in known_wp:
        uri = formula_ref_to_uri(ref)
        if uri:
            m = re.match(r"WP\('([^']+)','([^']+)'\)", ref)
            wp_entries.append(
                AddressEntry(
                    uri=uri,
                    domain="wp",
                    source=m.group(1) if m else "",
                    path="",
                    cell=m.group(2) if m else "",
                    label=ref,
                    formula_ref=ref,
                    wp_code=m.group(1) if m else "",
                )
            )
    tb_entries = []
    for ref in known_tb:
        uri = formula_ref_to_uri(ref)
        if uri:
            tb_entries.append(
                AddressEntry(
                    uri=uri,
                    domain="tb",
                    source="1001",
                    path="",
                    cell="期末",
                    label=ref,
                    formula_ref=ref,
                )
            )

    svc = AddressRegistryService()
    pid = str(uuid.uuid4())

    async def _mock_domain(db, project_id, year, template_type, domain):
        if domain == "wp":
            return wp_entries
        if domain == "tb":
            return tb_entries
        return []

    async def _inner():
        with patch.object(svc, "_get_domain", side_effect=_mock_domain):
            with patch.object(svc, "_redis_get", new_callable=AsyncMock, return_value=None):
                with patch.object(svc, "_redis_set", new_callable=AsyncMock):
                    return await svc.validate_formula_refs(db=None, project_id=pid, year=2025, formula=formula)

    issues = _run(_inner())
    issue_refs = {i["ref"] for i in issues if i.get("status") == "not_found"}
    all_refs = _extract_refs(formula)
    known = known_wp | known_tb
    expected_bad = {r for r in all_refs if r not in known}
    assert issue_refs == expected_bad
