"""批量打包「未导出清单」守卫 —— Wave 1 Task 2（spec: workpaper-import-export-lifecycle-closure）

## 判据分层（先打红设计）

- **类 A（应全绿）**：`VERDICT_LABELS` 真源完整性、清单渲染器可导入、替身自检。
- **类 B（应全红，直到 Wave 2 Task 6）**：`template_fallback` 是否进清单。

## 🔴 本守卫要钉死的缺陷

改造前 `download_pack` 的跳过清单**只列 `empty` / `missing`**（真实库 54 + 11 = 65 份），
而 `verdict == 'template_fallback'` 的 **1670 份**底稿虽然进了 ZIP，却是**空白模板**，
清单里一个字都没提 ⇒ 用户拿到 ZIP 看到一堆空模板，误以为「底稿本来就没数据」。

清单渲染器 `_render_skipped_manifest` 的入参 `skipped` 只由 `download_pack` 里
`res.path is None or not res.path.is_file()` 这一个分支喂入 —— 而 `template_fallback`
的 `path` 是**有效文件**（模板库原件），永远进不了那个分支。所以这里不是「文案没写」，
而是**结构上进不去**：修法必须在 `download_pack` 的写入侧另开一路。

## 反向自检

`test_manifest_omitting_fallback_is_detectable` 用一个「只列 empty/missing」的替身
渲染器，断言本守卫的判据**能把它判红** —— 否则判据本身是空转。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.wp_export.wp_file_resolver import VERDICT_LABELS, WP_FILE_VERDICTS

_SVC_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "services" / "wp_download_service.py"
)


def _svc_source() -> str:
    return _SVC_PATH.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# 类 A —— 真源与基础设施自检（应全绿）
# ═══════════════════════════════════════════════════════════════════════════════


class TestManifestSourceOfTruth:
    """清单文案真源。"""

    def test_verdict_labels_cover_all_verdicts(self) -> None:
        """R1.5 前置：分组要按 verdict，故每档都必须有中文标签。"""
        missing = [v for v in WP_FILE_VERDICTS if v not in VERDICT_LABELS]
        assert not missing, f"VERDICT_LABELS 缺档: {missing}"

    def test_renderer_is_importable(self) -> None:
        from app.services.wp_download_service import _render_skipped_manifest

        assert callable(_render_skipped_manifest)

    def test_service_source_readable(self) -> None:
        """扫描面非空自检 —— 防「文件读不到导致断言空转」。"""
        src = _svc_source()
        assert len(src) > 2000, f"wp_download_service.py 疑似读取异常: {len(src)} 字符"
        assert "_render_skipped_manifest" in src


class TestManifestRendererBehaviour:
    """渲染器的既有行为（不依赖本 spec 改动，应全绿）。"""

    @staticmethod
    def _render(skipped: list[dict[str, str]]) -> str:
        from uuid import uuid4

        from app.services.wp_download_service import _render_skipped_manifest

        return _render_skipped_manifest(
            project_id=uuid4(),
            total=len(skipped) + 1,
            written=1,
            skipped=skipped,
        )

    def test_groups_by_verdict(self) -> None:
        """R1.5：按 verdict 分组。"""
        text = self._render(
            [
                {"wp_code": "A1", "wp_name": "甲", "verdict": "empty", "reason": "r1"},
                {"wp_code": "A2", "wp_name": "乙", "verdict": "missing", "reason": "r2"},
            ]
        )
        assert VERDICT_LABELS["empty"] in text
        assert VERDICT_LABELS["missing"] in text

    def test_uses_verdict_labels_not_raw_verdict(self) -> None:
        """文案取真源，不裸显英文 verdict（UI 全中文化铁律）。"""
        text = self._render(
            [{"wp_code": "A1", "wp_name": "甲", "verdict": "empty", "reason": "r"}]
        )
        assert VERDICT_LABELS["empty"] in text
        # 分组标题行不得是裸英文
        assert "【empty】" not in text

    def test_manifest_omitting_fallback_is_detectable(self) -> None:
        """🔴 反向自检：判据必须能把「只列 empty/missing」的替身判红。

        若这条通不过，说明下面类 B 的断言是空转（改回旧实现也不会红）。
        """

        def _stub_renderer(skipped: list[dict[str, str]]) -> str:
            kept = [s for s in skipped if s["verdict"] in ("empty", "missing")]
            return "\n".join(
                f"【{VERDICT_LABELS[s['verdict']]}】{s['wp_code']}" for s in kept
            )

        text = _stub_renderer(
            [
                {"wp_code": "A1", "verdict": "empty"},
                {"wp_code": "A2", "verdict": "template_fallback"},
            ]
        )
        # 替身漏掉了 fallback ⇒ 判据（下面类 B 用的同一条）必须能识别
        assert VERDICT_LABELS["template_fallback"] not in text, (
            "替身本应漏掉 fallback；若它反而出现了，说明判据字串选错了"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 类 B —— 被测实现（应全红，直到 Wave 2 Task 6）
# ═══════════════════════════════════════════════════════════════════════════════


class TestFallbackEntersManifest:
    """R1.4 / R1.5：`template_fallback` 必须进清单。"""

    def test_download_pack_collects_fallback_into_skipped(self) -> None:
        """🔴 结构性判据：`download_pack` 必须有一路专门把 fallback 收进清单。

        改造前唯一的收集分支是 `res.path is None or not res.path.is_file()`，
        而 fallback 的 path 是有效文件 ⇒ 结构上进不去。
        """
        src = _svc_source()
        # 判据：源码里必须出现「按 verdict 判 fallback 后 append 到 skipped」的形态
        has_fallback_branch = bool(
            re.search(r"is_fallback|verdict\s*==\s*[\"']template_fallback[\"']", src)
        )
        assert has_fallback_branch, (
            "尚未实现（Wave 2 Task 6）：download_pack 没有任何针对 "
            "template_fallback 的分支 ⇒ 真实库 1670 份回退底稿不会进 "
            "_未导出清单.txt（它们的 path 是有效模板文件，进不了现有的 "
            "`path is None or not is_file()` 分支）"
        )

    def test_manifest_advice_covers_fallback(self) -> None:
        """R1.5：每个出现的档位都要有处置建议。"""
        from uuid import uuid4

        from app.services.wp_download_service import _render_skipped_manifest

        text = _render_skipped_manifest(
            project_id=uuid4(),
            total=3,
            written=1,
            skipped=[
                {
                    "wp_code": "A1",
                    "wp_name": "甲",
                    "verdict": "template_fallback",
                    "reason": VERDICT_LABELS["template_fallback"],
                },
            ],
        )
        assert VERDICT_LABELS["template_fallback"] in text

        # 处置建议条数 ≥ 出现档位数
        advice_lines = [ln for ln in text.splitlines() if ln.strip().startswith("·")]
        assert len(advice_lines) >= 1, "处置建议缺失"

    def test_advice_count_ge_verdict_count(self) -> None:
        """R1.5：三档同时出现时，建议条数不得少于档位数。"""
        from uuid import uuid4

        from app.services.wp_download_service import _render_skipped_manifest

        text = _render_skipped_manifest(
            project_id=uuid4(),
            total=4,
            written=1,
            skipped=[
                {"wp_code": "A1", "verdict": "empty", "reason": "r"},
                {"wp_code": "A2", "verdict": "missing", "reason": "r"},
                {"wp_code": "A3", "verdict": "template_fallback", "reason": "r"},
            ],
        )
        groups = len(re.findall(r"^【", text, re.M))
        advice_lines = [ln for ln in text.splitlines() if ln.strip().startswith("·")]
        assert len(advice_lines) >= groups, (
            f"尚未实现（Wave 2 Task 6）：出现 {groups} 个档位但只有 "
            f"{len(advice_lines)} 条处置建议"
        )


class TestFallbackAlsoStampedInZip:
    """R1.1 与 R1.4 不互斥：fallback 底稿既进 ZIP（带自证）又进清单。"""

    def test_pack_stamps_self_evidence_on_fallback(self) -> None:
        src = _svc_source()
        assert "self_evidence" in src or "stamp_self_evidence" in src, (
            "尚未实现（Wave 2 Task 5/6）：download_pack 未接自证共享件 ⇒ "
            "ZIP 内的空白模板不会自证，用户仍会误认为底稿本来无数据"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


# ═══════════════════════════════════════════════════════════════════════════════
# `_VERDICT_ADVICE` 键集完整性 —— Wave 2 Task 6
#
# 🔴 为什么「建议条数 ≥ 档位数」还不够：清单按出现档位逐条取建议，缺键会退到
#    `_VERDICT_ADVICE_FALLBACK`。条数照样够，但内容是兜底话术（"请联系管理员"），
#    对用户等于没给指引。这正是 memory 记的「fail-open 掩盖接线错误」形态 ——
#    必须另有一条守卫扫键集，让"新增 verdict 档忘了补建议"直接打红。
# ═══════════════════════════════════════════════════════════════════════════════


class TestVerdictAdviceCompleteness:
    """R1.5：每个非 `file` 档位都要有**专属**处置建议，不得退兜底。"""

    def test_advice_covers_all_non_file_verdicts(self) -> None:
        from app.services.wp_download_service import _VERDICT_ADVICE

        expected = {v for v in WP_FILE_VERDICTS if v != "file"}
        missing = sorted(expected - set(_VERDICT_ADVICE))
        assert not missing, (
            f"以下 verdict 档缺专属处置建议（会退到兜底话术）: {missing}"
        )

    def test_advice_has_no_extra_keys(self) -> None:
        """反向：不得登记 `WP_FILE_VERDICTS` 之外的档位（stale 键）。"""
        from app.services.wp_download_service import _VERDICT_ADVICE

        extra = sorted(set(_VERDICT_ADVICE) - set(WP_FILE_VERDICTS))
        assert not extra, f"`_VERDICT_ADVICE` 含未知档位（已废弃？）: {extra}"

    def test_file_verdict_has_no_advice(self) -> None:
        """`file` 档是正常态，不该出现在建议表里（否则正常导出也会被加噪声）。"""
        from app.services.wp_download_service import _VERDICT_ADVICE

        assert "file" not in _VERDICT_ADVICE, (
            "`file` 是正常档位，登记建议会让正常导出也带处置话术"
        )

    def test_each_advice_is_actionable_chinese(self) -> None:
        """每条建议须是中文且含可操作动词（不能只陈述现象）。"""
        from app.services.wp_download_service import _VERDICT_ADVICE

        for verdict, advice in _VERDICT_ADVICE.items():
            assert re.search(r"[\u4e00-\u9fff]", advice), f"{verdict} 建议非中文"
            assert re.search(r"(请|改用|使用|联系|重新)", advice), (
                f"{verdict} 的建议缺可操作动词: {advice!r}"
            )

    def test_advice_lines_match_group_count_for_all_three(self) -> None:
        """三档同时出现时，建议条数恰等于档位数（不多不少）。"""
        from uuid import uuid4

        from app.services.wp_download_service import _render_skipped_manifest

        text = _render_skipped_manifest(
            project_id=uuid4(),
            total=4,
            written=2,
            skipped=[
                {"wp_code": "A1", "verdict": "empty", "reason": "r"},
                {"wp_code": "A2", "verdict": "missing", "reason": "r"},
                {"wp_code": "A3", "verdict": "template_fallback", "reason": "r"},
            ],
        )
        groups = len(re.findall(r"^【", text, re.M))
        advice = [ln for ln in text.splitlines() if ln.strip().startswith("·")]
        assert groups == 3, f"应有 3 个档位分组，实际 {groups}"
        assert len(advice) == 3, f"建议条数应恰为 3，实际 {len(advice)}"

    def test_fallback_counted_separately_from_missing(self) -> None:
        """🔴 `template_fallback` 进了 ZIP，不能与「未导出」混计。

        否则"未导出 N 份"会与 ZIP 内文件数矛盾，用户对不上账。
        """
        from uuid import uuid4

        from app.services.wp_download_service import _render_skipped_manifest

        text = _render_skipped_manifest(
            project_id=uuid4(),
            total=3,
            written=2,
            skipped=[
                {"wp_code": "A1", "verdict": "missing", "reason": "r"},
                {"wp_code": "A2", "verdict": "template_fallback", "reason": "r"},
            ],
        )
        assert "未导出（无文件）：1 份" in text, f"未分开计数: {text[:400]}"
        assert "已导出但为空白模板：1 份" in text, f"未分开计数: {text[:400]}"
