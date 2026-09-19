# -*- coding: utf-8 -*-
"""check_tb_publish_confirm_gate.py 单元测试。

spec: tb-writeback-explicit-publish-gate 复盘补强 6 / Req 1, 2（Property 1+2）。

验证守卫「真能拦、不误报」：
- 判据 A：无 confirm 直调 publish-to-tb 被检出；同文件有 confirm 放行（直接门）；
  同循环 Adjudication 有 confirm 放行（间接门，FormData 层只 post 的现实架构）。
- 判据 B：watch / watchEffect / onMounted / setTimeout / setInterval 回调内
  publishToTb( 或 publish-to-tb post 被检出；回调外的正常发布不误报。
- 收口注释里的字面量不误报（先剥注释）；测试文件被排除。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "check"))

import check_tb_publish_confirm_gate as guard  # noqa: E402


PUB = "await api.post('/api/workpapers/w1/audit-determination/publish-to-tb', {})"
CONFIRM = "await ElMessageBox.confirm('发布后将写入试算表，确认？', '发布确认')"


def _mk(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


class TestCycleOf:
    def test_form_data(self):
        assert guard.cycle_of(Path("useL2FormData.ts")) == "L2"

    def test_gt_host(self):
        assert guard.cycle_of(Path("GtK6HeldForSale.vue")) == "K6"

    def test_tab_adjudication(self):
        assert guard.cycle_of(Path("N5TabAdjudication.vue")) == "N5"

    def test_two_digit(self):
        assert guard.cycle_of(Path("useM10FormData.ts")) == "M10"

    def test_no_cycle(self):
        assert guard.cycle_of(Path("GtAuditSheet.vue")) is None


class TestJudgeA:
    """判据 A：确认门配对。"""

    def test_unconfirmed_publish_detected(self, tmp_path):
        p = _mk(tmp_path, "useX9FormData.ts", "export async function w() {" + PUB + "}")
        v = guard.scan([p])
        assert [x["kind"] for x in v] == ["unconfirmed_publish"]

    def test_same_file_confirm_passes(self, tmp_path):
        p = _mk(tmp_path, "useX9Adjudication.ts",
                "export async function w() {" + CONFIRM + PUB + "}")
        assert guard.scan([p]) == []

    def test_sibling_adjudication_confirm_passes(self, tmp_path):
        """间接门：FormData 只 post，同循环 Adjudication 承载 confirm（现实架构 29 例）。"""
        fd = _mk(tmp_path, "useL9FormData.ts", "export async function w() {" + PUB + "}")
        adj = _mk(tmp_path, "useL9Adjudication.ts",
                  "export async function p() {" + CONFIRM + " await fd.w()}")
        assert guard.scan([fd, adj]) == []

    def test_unrelated_confirm_does_not_pair(self, tmp_path):
        """AI/OCR 确认不算发布门：文件名不含 Adjudication 则不配对（防误放行）。"""
        fd = _mk(tmp_path, "useK9FormData.ts", "export async function w() {" + PUB + "}")
        ai = _mk(tmp_path, "useK9AiGenerate.ts", "export async function g() {" + CONFIRM + "}")
        v = guard.scan([fd, ai])
        assert [x["kind"] for x in v] == ["unconfirmed_publish"]

    def test_closure_comment_not_flagged(self, tmp_path):
        p = _mk(tmp_path, "useX8FormData.ts",
                "// 原直调已移除，TB 回写走 audit-determination/publish-to-tb" + chr(10)
                + "export function noop() { return 1 }")
        assert guard.scan([p]) == []


class TestJudgeB:
    """判据 B：禁自动调用（Req 1 数据变化/挂载绝不写 TB）。"""

    def test_watch_auto_publish_detected(self, tmp_path):
        body = CONFIRM + chr(10) + "watch(total, async () => { await publishToTb() })"
        p = _mk(tmp_path, "useX7Adjudication.ts", body)
        kinds = [x["kind"] for x in guard.scan([p])]
        assert "auto_publish" in kinds

    def test_onmounted_auto_publish_detected(self, tmp_path):
        body = CONFIRM + chr(10) + "onMounted(() => { void publishToTb() })"
        p = _mk(tmp_path, "useX6Adjudication.ts", body)
        assert "auto_publish" in [x["kind"] for x in guard.scan([p])]

    def test_settimeout_auto_post_detected(self, tmp_path):
        body = CONFIRM + chr(10) + "setTimeout(async () => {" + PUB + "})"
        p = _mk(tmp_path, "useX5Adjudication.ts", body)
        assert "auto_publish" in [x["kind"] for x in guard.scan([p])]

    def test_watcheffect_auto_publish_detected(self, tmp_path):
        body = CONFIRM + chr(10) + "watchEffect(() => { void publishToTb() })"
        p = _mk(tmp_path, "useX4Adjudication.ts", body)
        assert "auto_publish" in [x["kind"] for x in guard.scan([p])]

    def test_publish_outside_callback_not_flagged(self, tmp_path):
        lines = [CONFIRM, "watch(total, () => { emitAdjudicated() })",
                 "export async function publishToTb() {" + PUB + "}"]
        p = _mk(tmp_path, "useX3Adjudication.ts", chr(10).join(lines))
        assert guard.scan([p]) == []

    def test_commented_auto_publish_not_flagged(self, tmp_path):
        note = "// 原自动写已移除: watch(total, () => { void publishToTb() })"
        lines = [CONFIRM, note,
                 "export async function publishToTb() {" + PUB + "}"]
        p = _mk(tmp_path, "useX2Adjudication.ts", chr(10).join(lines))
        assert guard.scan([p]) == []


class TestMainIntegration:
    """main 集成：clean 仓库 exit 0；含违规 exit 1；测试文件被排除。"""

    def _patch_src(self, tmp_path, monkeypatch):
        src = tmp_path / "audit-platform" / "frontend" / "src"
        src.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(guard, "FRONTEND_SRC", src, raising=False)
        import check_tb_writeback_no_direct_call as sibling
        monkeypatch.setattr(sibling, "FRONTEND_SRC", src)
        monkeypatch.setattr(sibling, "_REPO", tmp_path)
        return src

    def test_clean_exits_0(self, tmp_path, monkeypatch):
        src = self._patch_src(tmp_path, monkeypatch)
        (src / "useZ1Adjudication.ts").write_text(CONFIRM + chr(10) + PUB, encoding="utf-8")
        assert guard.main([]) == 0

    def test_violation_exits_1(self, tmp_path, monkeypatch):
        src = self._patch_src(tmp_path, monkeypatch)
        (src / "useZ2FormData.ts").write_text(PUB, encoding="utf-8")
        assert guard.main([]) == 1

    def test_test_files_excluded(self, tmp_path, monkeypatch):
        src = self._patch_src(tmp_path, monkeypatch)
        d = src / "__tests__"
        d.mkdir()
        (d / "z.spec.ts").write_text(PUB, encoding="utf-8")
        assert guard.main([]) == 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
