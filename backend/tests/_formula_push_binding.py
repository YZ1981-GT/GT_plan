"""Minimal valid bindings shared by formula-push registry tests."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class DummyPushBinding:
    """Small protocol-complete binding for registration-only tests.

    ``paper_codes`` is intentionally omitted: registry validation should keep
    the production default of a binding's primary paper code.
    """

    wp_code = "Z9"
    account_prefixes = ("9901",)
    derivations = frozenset()
    four_table_slots = frozenset()
    tb_columns = frozenset({"期末余额"})

    async def load_sources(self, db: Any, project_id: Any, year: int, wp_id: Any) -> Any:
        return SimpleNamespace(warnings=[], template_type=None)

    def workpaper_targets(self, rule: Any, overlay: dict[str, Any], sources: Any) -> tuple[list, list]:
        return [], []

    def apply(self, overlay: dict[str, Any], target: Any, value: Any) -> bool:
        return False

    def note_rows(self, overlay: dict[str, Any], template_type: str, rule: Any) -> list[dict]:
        return []

    def entry_warnings(self, overlay: dict[str, Any]) -> list[str]:
        return []


def make_dummy_binding(wp_code: str, account_prefix: str = "9901") -> DummyPushBinding:
    """Factory used to exercise ``module:factory(literal, ...)`` parsing."""
    binding = DummyPushBinding()
    binding.wp_code = wp_code
    binding.account_prefixes = (account_prefix,)
    return binding
