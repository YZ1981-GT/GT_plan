"""canonical 抽样端点契约守卫（voucher-sampling-hardening Task 16）

防止回退到多轨状态：canonical 抽凭路径（voucher-extract）必须使用单一算法真源
`voucher_sampling_algorithms.execute_sampling`，且不得混用 legacy `WpSamplingEngine`。

Validates: Requirements 7.1, 12.3
Properties: Property 14
"""

from __future__ import annotations

from pathlib import Path

_ROUTERS = Path(__file__).resolve().parent.parent / "app" / "routers"


class TestCanonicalSamplingGuard:
    def test_voucher_extract_uses_canonical_algorithm(self):
        src = (_ROUTERS / "voucher_sampling.py").read_text(encoding="utf-8")
        # 使用 canonical 算法真源
        assert "from app.services.voucher_sampling_algorithms import" in src
        assert "execute_sampling" in src

    def test_voucher_extract_does_not_use_legacy_engine(self):
        src = (_ROUTERS / "voucher_sampling.py").read_text(encoding="utf-8")
        # canonical 路径不得混用 legacy WpSamplingEngine（防多轨漂移）
        assert "WpSamplingEngine" not in src
        assert "wp_sampling_engine" not in src

    def test_voucher_extract_uses_methodology_single_source(self):
        src = (_ROUTERS / "voucher_sampling.py").read_text(encoding="utf-8")
        # 方法学单一真源
        assert "build_methodology_snapshot" in src
        assert "from app.services.sampling_methodology import" in src

    def test_full_frame_two_phase_wired(self):
        src = (_ROUTERS / "voucher_sampling.py").read_text(encoding="utf-8")
        assert "locate_sampling_units" in src
        assert "fetch_by_unit_ids" in src
        assert "_SAMPLING_FRAME_LIMIT" in src

    def test_authorization_before_try(self):
        src = (_ROUTERS / "voucher_sampling.py").read_text(encoding="utf-8")
        assert "_authorize_and_validate_extract" in src
