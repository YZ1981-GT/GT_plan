# -*- coding: utf-8 -*-
"""首版从 instrumented 模板发布时，未管理区域比较必须先规范化模板字节。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.workpaper_sync.content_mutation import ContentMutationService
from tests.workpaper_sync.d4_materialize_harness import build_world


class _CpuStageHarness:
    _assert_roundtrip_equivalent = ContentMutationService._assert_roundtrip_equivalent

    @staticmethod
    def _projection_structure_hash(**_kwargs: object) -> str:
        return "test-structure-hash"


def test_first_publication_normalizes_template_before_unmanaged_verification(tmp_path):
    """D4 首代模板重序列化不再伪装成未管理区域样式漂移。"""
    world = build_world(tmp_path)
    plan = SimpleNamespace(
        substrate_path=world.base,
        contract=world.contract,
        normalize_unmanaged_baseline=True,
    )
    output = tmp_path / "first-publication.xlsx"

    _, _, unmanaged, structure_hash = ContentMutationService._stage_cpu_segment_scoped(
        _CpuStageHarness(),
        plan=plan,
        projection=world.projection,
        adapter=world.adapter,
        output=output,
    )

    assert output.is_file()
    assert unmanaged.equivalent is True, unmanaged.details
    assert structure_hash == "test-structure-hash"
    assert not list(tmp_path.glob("*.unmanaged-baseline.xlsx"))
