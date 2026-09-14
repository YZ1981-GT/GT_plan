"""Property-based test for P27 — Legacy-Consumer Drift Guard.

spec acnr-consumer-wiring · Task 34.5 (Property 27, generative).

**Property 27: Legacy-Consumer Drift Guard**
    *For any* new backend module introducing a direct ``address_registry.``
    consumer outside the documented exemption list, the CI drift-guard test
    SHALL fail unless a corresponding Coverage Ledger entry is added.

**Validates: Requirements 22.2**

Rationale
---------
The real drift guard (task 34.4) is a *codebase-scan* invariant — it walks the
source tree looking for direct ``address_registry.`` consumers and fails CI when
a consumer appears that is neither in the Coverage Ledger (design.md
"Coverage Ledger — 全库 ACNR 消费点清单") nor in the documented exemption
whitelist. That scan is not easily randomized over *inputs*.

P27 therefore expresses the guard as a property over a GENERATED set of
hypothetical consumer records. Given:

  * the fixed Coverage-Ledger allowlist (``LEDGER_COVERED``),
  * the fixed exemption whitelist (``EXEMPTIONS`` / ``EXEMPT_PREFIXES``), and
  * a random set of ``(module_path, references_address_registry: bool)`` records,

the drift-guard predicate ``is_allowed(module)`` holds **iff** the module is in
``ledger ∪ exemptions``. The property asserts:

  * a module referencing ``address_registry`` that is NOT in the allowlist is
    *flagged* (the guard would fail CI), and
  * a module in the allowlist (or one that does not reference address_registry)
    *passes*.

This tests the guard LOGIC generatively, independent of the physical scan.

Coordination with task 34.4
---------------------------
Task 34.4 (example-based drift guard, ``[-]`` at time of writing) is expected to
expose the same allowlist + predicate. This module defines them at module level
(``LEDGER_COVERED``, ``EXEMPTIONS``, ``EXEMPT_PREFIXES``, ``is_ledger_covered``,
``is_allowed``, ``drift_guard_flags``) so that 34.4 can import and converge on a
single source of truth. Until then they are replicated here per the task brief.
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ═══════════════════════════════════════════════════════════════════════════════
# Coverage Ledger allowlist + exemption whitelist (design.md · Req 22.1)
# ═══════════════════════════════════════════════════════════════════════════════

# Backend ACNR/address_registry consumers WITH a documented Coverage Ledger entry
# (each maps to a P-priority in design.md). These are ALLOWED to consume
# address_registry because their migration/coverage is tracked.
LEDGER_COVERED: frozenset[str] = frozenset(
    {
        "app/services/wp_parsed_data_service.py",  # touch_wp_registry — P6 / Req 10.1
        "app/services/wp_structure.py",  # invalidate — P6 / Req 2.6
        "app/services/event_handlers.py",  # _invalidate_addr_* — P6 / Req 11
        "app/services/wp_formula_service.py",  # save validate — P5 / Req 9.1
        "app/routers/report_config.py",  # validate — P5 / Req 9.2
        "app/routers/wp_user_formulas.py",  # validate — P5 / Req 9.2
        "app/services/address_registry.py",  # _build_custom_wp_cell_entries — P7 / Req 12
        "app/services/formula_engine.py",  # extract_custom_cells — P15 / Req 21.1
        "app/services/wp_structure_bridge.py",  # build_uri/AddressEntry — P15 / Req 21.2
        "app/services/custom_query/query_builder.py",  # TB() ref 语法 — P15 / Req 21.3
        "app/services/stale_propagation_engine.py",  # WP:* URI — P2 / Req 4
        "app/services/linkage_graph_builder.py",  # 10 数据源 URI — P2 / Req 3
        "app/services/acnr/events.py",  # reverse_index — P1 / Req 2
        "app/services/custom_query/cross_sheet_resolver.py",  # full_resolve — P1 / Req 1
    }
)

# Explicitly EXEMPT consumers (documented in design.md Coverage Ledger as 豁免):
#   - V1 router API (strangler fallback, intentionally kept)  — Req 21.4
#   - ACNR core seams (grammar/resolver/catalog delegation)   — Req 21.5
EXEMPTIONS: frozenset[str] = frozenset(
    {
        "app/routers/address_registry.py",  # V1 API strangler fallback — Req 21.4
        "app/services/acnr/grammar.py",  # ACNR core delegation — Req 21.5
        "app/services/acnr/resolver.py",  # ACNR core delegation — Req 21.5
        "app/services/acnr/catalog.py",  # ACNR core delegation — Req 21.5
    }
)

# Prefix-based exemptions: data resolvers are NOT address consumers (they query
# the DB; ref_index chips route through GtIndexChip which is already on ACNR).
EXEMPT_PREFIXES: tuple[str, ...] = ("app/services/auto_data_resolvers/",)

# The full allowlist the drift guard consults.
ALLOWLIST: frozenset[str] = LEDGER_COVERED | EXEMPTIONS


def is_exempt(module_path: str) -> bool:
    """True if ``module_path`` is on the documented exemption whitelist."""
    if module_path in EXEMPTIONS:
        return True
    return any(module_path.startswith(p) for p in EXEMPT_PREFIXES)


def is_ledger_covered(module_path: str) -> bool:
    """True if ``module_path`` has a Coverage Ledger entry."""
    return module_path in LEDGER_COVERED


def is_allowed(module_path: str) -> bool:
    """Drift-guard predicate: a consumer is allowed iff it is Ledger-covered or exempt.

    ``is_allowed(m) <=> m ∈ (LEDGER_COVERED ∪ EXEMPTIONS ∪ EXEMPT_PREFIXES*)``
    """
    return is_ledger_covered(module_path) or is_exempt(module_path)


def drift_guard_flags(consumers: dict[str, bool]) -> set[str]:
    """Return the set of modules the drift guard would FLAG (CI failure).

    A module is flagged iff it directly references ``address_registry`` AND is
    not on the allowlist.

    :param consumers: mapping ``module_path -> references_address_registry``.
    """
    return {
        module
        for module, references in consumers.items()
        if references and not is_allowed(module)
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Hypothesis strategies
# ═══════════════════════════════════════════════════════════════════════════════

# Known modules from the allowlist (both Ledger-covered and exempt).
_known_module_st = st.sampled_from(sorted(ALLOWLIST))

# A brand-new module path NOT in the allowlist (simulates a newly-introduced
# consumer that a developer forgot to add to the Coverage Ledger).
_new_module_st = st.builds(
    lambda seg: f"app/services/new_feature_{seg}.py",
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_", min_size=1, max_size=12),
).filter(lambda p: p not in ALLOWLIST and not is_exempt(p))

# A path under an exempt prefix (should always be allowed regardless of name).
_exempt_prefix_module_st = st.builds(
    lambda seg: f"app/services/auto_data_resolvers/{seg}.py",
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_", min_size=1, max_size=12),
)

# Any module (mix of known / new / exempt-prefix).
_any_module_st = st.one_of(_known_module_st, _new_module_st, _exempt_prefix_module_st)

# A consumer record set: module_path -> references_address_registry.
_consumer_set_st = st.dictionaries(
    keys=_any_module_st,
    values=st.booleans(),
    min_size=0,
    max_size=12,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 27 — Legacy-Consumer Drift Guard
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty27LegacyConsumerDriftGuard:
    """P27: drift guard flags un-Ledgered new consumers, passes allowlisted ones."""

    @settings(max_examples=50)
    @given(consumers=_consumer_set_st)
    def test_guard_flags_exactly_unallowed_referencing_modules(
        self, consumers: dict[str, bool]
    ) -> None:
        """Guard flags a module iff it references address_registry AND is not allowed.

        ``flagged = { m | consumers[m] ∧ ¬is_allowed(m) }``
        """
        flagged = drift_guard_flags(consumers)

        expected = {
            m for m, refs in consumers.items() if refs and not is_allowed(m)
        }
        assert flagged == expected

        # No flagged module is on the allowlist, and every flagged module
        # actually references address_registry.
        for m in flagged:
            assert not is_allowed(m), f"allowlisted module wrongly flagged: {m}"
            assert consumers[m] is True

    @settings(max_examples=50)
    @given(new_module=_new_module_st)
    def test_new_unledgered_consumer_is_flagged(self, new_module: str) -> None:
        """A NEW module referencing address_registry with no Ledger entry → flagged (CI fails)."""
        assert not is_allowed(new_module)
        flagged = drift_guard_flags({new_module: True})
        assert new_module in flagged, (
            f"新 legacy 消费者 {new_module} 无 Ledger 条目却未被 drift guard 标记"
        )

    @settings(max_examples=50)
    @given(known_module=_known_module_st)
    def test_ledgered_or_exempt_consumer_passes(self, known_module: str) -> None:
        """A module on the allowlist (Ledger-covered or exempt) referencing address_registry → passes."""
        assert is_allowed(known_module)
        flagged = drift_guard_flags({known_module: True})
        assert known_module not in flagged, (
            f"已登记/豁免消费者 {known_module} 被 drift guard 误标记"
        )

    @settings(max_examples=50)
    @given(module=_any_module_st)
    def test_non_referencing_module_never_flagged(self, module: str) -> None:
        """A module that does NOT reference address_registry is never flagged, regardless of Ledger status."""
        flagged = drift_guard_flags({module: False})
        assert flagged == set()

    @settings(max_examples=50)
    @given(module=_exempt_prefix_module_st)
    def test_exempt_prefix_always_allowed(self, module: str) -> None:
        """Any module under an exempt prefix (data resolvers) is always allowed."""
        assert is_exempt(module)
        assert is_allowed(module)
        assert drift_guard_flags({module: True}) == set()


class TestDriftGuardPredicateInvariants:
    """Static invariants of the allowlist/predicate (non-generative sanity checks)."""

    def test_ledger_and_exemptions_are_allowed(self) -> None:
        for m in LEDGER_COVERED:
            assert is_allowed(m)
        for m in EXEMPTIONS:
            assert is_allowed(m)

    def test_ledger_covered_are_not_treated_as_exempt(self) -> None:
        # Ledger-covered consumers must be covered because they are Ledgered,
        # not because they are exempt (except events.py which is not in EXEMPTIONS).
        assert "app/services/acnr/events.py" in LEDGER_COVERED
        assert "app/services/acnr/events.py" not in EXEMPTIONS

    def test_unknown_referencing_module_not_allowed(self) -> None:
        assert not is_allowed("app/services/some_brand_new_consumer.py")


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
