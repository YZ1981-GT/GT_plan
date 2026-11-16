"""
test_display_preferences_doc_guard.py

屏幕显示与正式导出单位两份开发文档与代码对拍
（spec platform-global-display-settings-closure 12A / 12C、AC-26 的 A / C 部分）。

判据（与 12B 同一模式，design §8.1 / AC-26）：
1. 文档里点名的**每个符号 / 常量**都必须在代码里真实存在。
2. 文档里写的**现算数量**必须能被代码重算（不能写死一个不再成立的值）。
3. 文档声明的**枚举值集合**必须与代码逐值一致。
4. 反向：文档不能漏掉关键章节（核心页面矩阵 / 数据集三态 / 四类 export surface）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_DOCS = Path(__file__).resolve().parents[2] / "docs"
_DISPLAY_DOC = _DOCS / "frontend" / "display-preferences.md"
_EXPORT_DOC = _DOCS / "reference" / "formal-export-unit-policy.md"
_BACKEND = Path(__file__).resolve().parents[1]


def _text(path: Path) -> str:
    assert path.exists(), f"文档不存在：{path}"
    return path.read_text(encoding="utf-8")


# ── 12A：屏幕显示文档 ──────────────────────────────────────


class TestDisplayPreferencesDoc:
    def test_doc_exists_and_is_substantial(self) -> None:
        text = _text(_DISPLAY_DOC)
        assert len(text.split("\n")) >= 300, "文档过薄（< 300 行），不足以覆盖 12A 要求"

    @pytest.mark.parametrize("anchor", [
        "reached_by",           # render schema 核心清单
        "matched",              # 附注 matched/unmatched/invalid 分布
        "legacy_unknown",       # 数据集三态
        "render_schema_core",   # 核心清单文件名
    ])
    def test_doc_mentions_key_anchor(self, anchor: str) -> None:
        assert anchor in _text(_DISPLAY_DOC), f"文档未提及 {anchor}"

    def test_dataset_unit_states_match_code(self) -> None:
        """数据集三态必须与 `dataset_unit_contract.classify_dataset_unit` 逐值一致。

        🔴 夹具按**真实口径**现读构造（本用例首版按命名习惯猜，写成
        `unit_normalization={version,source_unit,factor}` 就期望 `normalized_v1`，
        实测返回 `legacy_unknown` —— 真实判据是 `unit_normalization.contract`
        必须是**有效合同**，而 `legacy_declared` 看的是顶层 `amount_unit`）。
        """
        from app.services.dataset_unit_contract import classify_dataset_unit

        cases = {
            # normalized_v1 的真实判据：unit_normalization.contract.contract_digest
            # 是 64 位小写十六进制（不是「有 contract 就行」，也不是 version/source_unit）
            "normalized_v1": {
                "unit_normalization": {
                    "contract": {"contract_digest": "a" * 64},
                },
            },
            # legacy_declared 看顶层 amount_unit（非 unit_normalization 内）
            "legacy_declared": {"amount_unit": "wan"},
            "legacy_unknown": {},
        }
        text = _text(_DISPLAY_DOC)
        for expected, summary in cases.items():
            actual = classify_dataset_unit(summary)
            assert actual == expected, (
                f"分类器口径变了：{summary} → {actual}（期望 {expected}）；"
                "夹具必须按真实口径构造，不能按命名习惯猜"
            )
            assert expected in text, f"文档未提及数据集状态 {expected}"

    def test_invalid_contract_fails_closed(self) -> None:
        """`unit_normalization` 存在但合同无效 ⇒ fail-closed 为 legacy_unknown。"""
        from app.services.dataset_unit_contract import classify_dataset_unit

        assert classify_dataset_unit(
            {"unit_normalization": {"version": 1, "source_unit": "wan"}}
        ) == "legacy_unknown"

    def test_measure_kinds_match_code(self) -> None:
        """七类 measure kind 必须与 `MeasureKind` 枚举逐值一致。

        前端枚举无法在 Python 侧 import，改为读 TS 源文本（AST 太重，
        这里只需要 `NAME = 'value'` 的字面形态）。
        """
        ts = (_BACKEND.parent / "audit-platform" / "frontend" / "src" / "types" / "measureKind.ts")
        assert ts.exists()
        source = ts.read_text(encoding="utf-8")
        kinds = re.findall(r"^\s+([A-Z_]+)\s*=\s*'([a-z_]+)'", source, re.M)
        assert len(kinds) >= 7, f"解析到的 measure kind 少于 7 类：{kinds}"
        doc = _text(_DISPLAY_DOC)
        missing = [
            f"{name}={value}" for name, value in kinds
            if value not in doc and name not in doc
        ]
        assert not missing, f"文档未覆盖以下 measure kind：{missing}"

    def test_doc_states_formal_export_boundary(self) -> None:
        """AC-20 / 12A：文档必须写明「个人偏好不进入正式导出」。"""
        text = _text(_DISPLAY_DOC)
        assert "正式导出" in text, "文档未提及正式导出边界"
        assert any(kw in text for kw in ("不进入", "不参与", "不读", "不得")), (
            "文档未写明个人偏好与正式导出的隔离"
        )


# ── 12C：正式导出单位策略文档 ──────────────────────────────


class TestFormalExportDoc:
    def test_doc_exists(self) -> None:
        assert _EXPORT_DOC.exists()

    def test_doc_is_not_too_thin(self) -> None:
        """12C 现状记录：文档只有 78 行，明显薄于 12A（459）/12B（396）。

        本轮补齐后必须 ≥ 150 行，否则「四类 export surface + 两阶段 authority +
        审计报告 placeholder + 普通底稿证据」这些内容装不下。
        """
        lines = len(_text(_EXPORT_DOC).split("\n"))
        assert lines >= 150, f"文档仍过薄（{lines} 行 < 150）"

    @pytest.mark.parametrize("anchor", [
        "ExportUnitRegion",
        "formal",
        "data_exchange",
        "template",
        "non_amount",
    ])
    def test_doc_mentions_export_surface_concept(self, anchor: str) -> None:
        assert anchor in _text(_EXPORT_DOC), f"文档未提及 {anchor}"

    def test_four_classifications_match_code(self) -> None:
        """四类出口必须与 `EXPORT_SURFACE_REGISTRY` 的实际分类逐值一致。"""
        from app.services.export_surface_registry import EXPORT_SURFACE_REGISTRY

        actual = {e.classification for e in EXPORT_SURFACE_REGISTRY.values()}
        assert actual == {"formal", "data_exchange", "template", "non_amount"}
        doc = _text(_EXPORT_DOC)
        for cls in actual:
            assert cls in doc, f"文档未提及出口分类 {cls}"

    def test_doc_warns_against_free_text_unit_inference(self) -> None:
        """design §6.3：示例不得靠自由文本猜模板单位。"""
        text = _text(_EXPORT_DOC)
        assert any(kw in text for kw in ("不得", "禁止", "不猜", "不推断")), (
            "文档未写明「不得靠自由文本猜单位」"
        )
