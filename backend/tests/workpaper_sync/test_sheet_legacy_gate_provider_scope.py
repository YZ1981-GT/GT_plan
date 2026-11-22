"""provider binding 的 legacy gate 候选码回归守卫。

spec: onlyoffice-sheet-open-via-published-artifact · task 3.3
"""
from __future__ import annotations

from uuid import UUID

from app.routers import _wp_onlyoffice_legacy_url_gate as GATE
from app.services.workpaper_sync.sheet_open_bindings import (
    SheetOpenBindingResolution,
    SheetOpenBindingResolver,
)


PROJECT = UUID("e8c40d30-de96-440d-a880-fafcf41f32f3")


def test_provider_legacy_gate_passes_parent_and_runtime_wp_codes(monkeypatch) -> None:
    """D4-2 的运行时码是 D4-2，但 migrated binding 的码族是父码 D4。"""
    captured: dict[str, object] = {}

    def fake_resolve(self, **kwargs):
        captured.update(kwargs)
        return SheetOpenBindingResolution(
            "migrated",
            None,
            {
                "entry_id": "xlsx/gt-d4-operating-revenue",
                "effective_entry_id": "xlsx/gt-d4-operating-revenue",
                "status": "migrated",
            },
        )

    monkeypatch.setattr(SheetOpenBindingResolver, "resolve", fake_resolve)
    verdict, binding = GATE._binding_verdict(
        source_wp_code="D4-2",
        source_wp_codes=("D4-2", "D4"),
        sheet_name="主营业务收入明细表D4-2",
        whole_workbook=False,
        project_id=PROJECT,
    )

    assert verdict == "refuse_migrated"
    assert binding is not None
    assert captured["source_wp_codes"] == ("D4-2", "D4")
    assert captured["source_wp_code"] == "D4-2"
