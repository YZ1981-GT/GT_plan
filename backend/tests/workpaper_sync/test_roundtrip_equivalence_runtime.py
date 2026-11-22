"""roundtrip_equivalence 的真实执行路径守卫。

spec: onlyoffice-sheet-open-via-published-artifact · task 3.3
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.workpaper_sync.adapters.base import Projection
from app.services.workpaper_sync.roundtrip_equivalence import (
    assert_roundtrip_equivalent,
)


def test_template_skeleton_extra_uses_shared_identity_predicate() -> None:
    """模板骨架 extra 应被共享判定豁免，且运行时不得出现 NameError。"""
    intended = Projection(
        contract_id="test",
        semantic_version="1",
        document_type="xlsx",
        values={},
        row_keys={},
    )
    extracted = Projection(
        contract_id="test",
        semantic_version="1",
        document_type="xlsx",
        values={"rows/GTROW-D410-0013/label": object()},
        row_keys={},
    )
    contract = SimpleNamespace(all_fields=lambda: [])

    assert_roundtrip_equivalent(
        intended=intended,
        extracted=extracted,
        contract=contract,
    )
