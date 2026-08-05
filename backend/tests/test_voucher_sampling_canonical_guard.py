"""canonical 抽样端点契约守卫（voucher-sampling-hardening Task 16
+ sampling-compliance-closure Wave 2 Task 11 扩面）

防止回退到多轨状态：canonical 抽凭路径（voucher-extract）必须使用单一算法真源
`voucher_sampling_algorithms.execute_sampling`，且**全仓**不得残留 legacy
`WpSamplingEngine`（该引擎已于 sampling-compliance-closure Wave 2 整体下线）。

Validates: Requirements 7.1, 12.3（voucher-sampling-hardening）
          / 4.3, 4.4, 4.5（sampling-compliance-closure）
Properties: Property 14（hardening） / Property 10（closure）
"""

from __future__ import annotations

import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_ROUTERS = _BACKEND / "app" / "routers"
_APP = _BACKEND / "app"

# legacy 引擎的标识符：类名 + 模块名
_LEGACY_TOKENS = ("WpSamplingEngine", "wp_sampling_engine")
# legacy 引擎独有的底稿写入方法（写 parsed_data.action_data，前端零消费 = dead write）
_LEGACY_WRITE_TOKENS = ("fill_sampling_to_workpaper", "associate_ocr_evidence")


def _strip_comments(src: str) -> str:
    """剥掉 Python 注释与文档字符串。

    🔴 必须先剥：本守卫要求的说明性注释里会**如实写出**被禁的标识符
    （如「已下线的 WpSamplingEngine」），不剥会把说明文字数成真实引用 → 假红。
    """
    # 三引号文档字符串/块注释
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    # 行注释（行首或非字符串上下文的 #；此处简化处理，够用且偏保守）
    src = re.sub(r"(?m)#.*$", "", src)
    return src


def _violating_files(tokens: tuple[str, ...]) -> list[str]:
    """返回 backend/app 下（剥注释后）仍引用 tokens 的文件相对路径。"""
    out: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        code = _strip_comments(path.read_text(encoding="utf-8"))
        if any(tok in code for tok in tokens):
            out.append(str(path.relative_to(_BACKEND)).replace("\\", "/"))
    return out


class TestCanonicalSamplingGuard:
    def test_voucher_extract_uses_canonical_algorithm(self):
        src = (_ROUTERS / "voucher_sampling.py").read_text(encoding="utf-8")
        # 使用 canonical 算法真源
        assert "from app.services.voucher_sampling_algorithms import" in src
        assert "execute_sampling" in src

    def test_voucher_extract_does_not_use_legacy_engine(self):
        src = _strip_comments((_ROUTERS / "voucher_sampling.py").read_text(encoding="utf-8"))
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


# ─── Wave 2 Task 11：全仓扩面（R4.3 / R4.4 / R4.5，Property 10）──────────────


class TestLegacyEngineFullyRemoved:
    """legacy `WpSamplingEngine` 在 backend/app 全仓零引用。

    此前守卫只查 `voucher_sampling.py` 一个文件 → 而 legacy 引擎当时仍挂在
    `sampling_enhanced.py` 与 `wp_functional_actions.py` 两个活端点上（前端零调用，
    但口径与 canonical 不同：金额 debit+credit vs GREATEST、分层写死 0.33/0.66 +
    权重 0.2/0.3/0.5、MUS 固定 interval、不落日志/不入批次/不可撤销），守卫全绿放过。
    """

    def test_service_module_deleted(self):
        assert not (_APP / "services" / "wp_sampling_engine.py").exists(), (
            "legacy 引擎模块应已删除"
        )

    def test_no_legacy_reference_anywhere_in_app(self):
        violations = _violating_files(_LEGACY_TOKENS)
        assert violations == [], f"backend/app 仍引用 legacy 引擎: {violations}"

    def test_no_legacy_writeback_helpers_anywhere_in_app(self):
        """legacy 的底稿写入点（写 parsed_data.action_data，前端零消费）零残留。

        注：`wp_functional_actions._fill_parsed_data` 也写 action_data，但那是
        functional-actions（截止测试/账龄/月度明细）自身的填充路径，与本次下线的
        legacy 抽样引擎无关，不在本断言范围内。其是否也是 dead write 属独立议题，
        已登记在 sampling-compliance-closure 的 Notes。
        """
        violations = _violating_files(_LEGACY_WRITE_TOKENS)
        assert violations == [], f"legacy 底稿写入点仍残留: {violations}"

    def test_sampling_execute_endpoint_gone(self):
        for name in ("sampling_enhanced.py", "wp_functional_actions.py"):
            code = _strip_comments((_ROUTERS / name).read_text(encoding="utf-8"))
            assert "sampling/execute" not in code, f"{name} 仍暴露 /sampling/execute"

    # ── 反向自检（R4.5）：证明守卫非空转 ──────────────────────────────────

    def test_reverse_selfcheck_detects_legacy_reference(self):
        """给定含 legacy 引用的替身源码，判定必须为「违规」。"""
        stub = (
            "from app.services.wp_sampling_engine import WpSamplingEngine\n"
            "engine = WpSamplingEngine()\n"
        )
        code = _strip_comments(stub)
        assert any(tok in code for tok in _LEGACY_TOKENS), "反向自检失败：判定逻辑空转"

    def test_reverse_selfcheck_strip_comments_actually_strips(self):
        """`_strip_comments` 真的剥掉注释/文档串 —— 否则本文件自己的说明注释
        （里面如实写了 `WpSamplingEngine`）会让全仓断言假红。"""
        raw = (
            '"""模块说明：已下线的 WpSamplingEngine 不得再引用。"""\n'
            "x = 1  # 历史上这里 import 过 wp_sampling_engine\n"
        )
        stripped = _strip_comments(raw)
        assert "WpSamplingEngine" in raw and "wp_sampling_engine" in raw
        assert "WpSamplingEngine" not in stripped
        assert "wp_sampling_engine" not in stripped
        assert "x = 1" in stripped

    def test_guard_scans_a_nonempty_file_set(self):
        """扫描集合非空 —— 否则「零引用」是因为一个文件都没扫到（假绿）。"""
        files = list(_APP.rglob("*.py"))
        assert len(files) > 100, f"backend/app 扫描到的 .py 过少（{len(files)}），疑似路径错"
