"""sheet_name override 优先级 + 非兜底 契约测试

confirmation-hub-workbench-tabs Task 7.3 / 2.5：
- 复刻 wp_render_config 的 _sheet_ovr 解析顺序（不 refactor 生产代码）：
    1) 编码尾码：_SHEET_CODE_RE.search(sheet_name) → override[code]
    2) 回退：override[整个 sheet_name]（精确）
    3) 回退：override[f"{wp_code}-{sheet_name}"]
  → 断言四组冲突场景解析正确（Property 4）
- 非兜底守卫（Property 21/23/24）：已登记的 confirmation-* sheet_name override
  解析结果 ∉ {confirmation-hub, skip}

实测约束（不猜，读 wp_code_overrides.json 定案）：
- 编码在尾部的 sheet 走「编码尾码」分支（如 跟函函证过程控制G0-3 → override['G0-3']）
- 编码不在尾部（后接括号）走「精确 sheet_name」分支
  （如 函证差异核对表G0-3（证券投资） → override 整名，因 _SHEET_CODE_RE 锚定 $）
"""
import re

import pytest

from app.routers.wp_render_config import _SHEET_CODE_RE
from app.services.wp_classification_service import refresh_wp_code_overrides


@pytest.fixture(scope="module")
def overrides() -> dict[str, str]:
    """加载真实 wp_code_overrides.json（含本 spec 新增的 sheet_name 精确 override）。"""
    return refresh_wp_code_overrides()


def resolve_sheet_ovr(sheet_name: str, wp_code: str, ovr: dict[str, str]) -> str | None:
    """复刻 wp_render_config.py 第 734-744 行的 _sheet_ovr 解析顺序（多 sheet 底稿）。

    与生产逻辑逐字对齐：编码尾码 → 精确 sheet_name → {wp_code}-{sheet_name}。
    """
    _sheet_ovr = None
    m = _SHEET_CODE_RE.search(sheet_name)
    if m:
        _sheet_ovr = ovr.get(m.group(1))
    if not _sheet_ovr:
        _sheet_ovr = ovr.get(sheet_name)
    if not _sheet_ovr and wp_code:
        _sheet_ovr = ovr.get(f"{wp_code}-{sheet_name}")
    return _sheet_ovr


class TestSheetCodeRegexAnchoring:
    """_SHEET_CODE_RE 锚定 $ 的行为（解析分支的分岔点）。"""

    def test_code_at_end_matches(self):
        assert _SHEET_CODE_RE.search("跟函函证过程控制G0-3").group(1) == "G0-3"

    def test_code_followed_by_paren_no_match(self):
        # 尾部是「）」而非编码 → 无匹配 → 走精确 sheet_name 分支
        assert _SHEET_CODE_RE.search("函证差异核对表G0-3（证券投资）") is None

    def test_program_code_a_suffix_matches(self):
        assert _SHEET_CODE_RE.search("函证程序表F0A").group(1) == "F0A"

    def test_e0_5_code_at_end_matches(self):
        assert _SHEET_CODE_RE.search("银行函证其他信息核对表E0-5").group(1) == "E0-5"


class TestG03Conflict:
    """G0-3 双 sheet：同尾码但一张后接括号 → 各归其位（Property 4）。"""

    def test_followup_via_code_tail(self, overrides):
        # 尾部 G0-3 → 编码尾码分支 → override['G0-3']
        assert resolve_sheet_ovr("跟函函证过程控制G0-3", "G0", overrides) == "confirmation-followup"

    def test_diff_securities_via_exact_sheet_name(self, overrides):
        # 后接括号 → 编码尾码不匹配 → 精确 sheet_name 分支
        assert (
            resolve_sheet_ovr("函证差异核对表G0-3（证券投资）", "G0", overrides)
            == "confirmation-diff-securities"
        )

    def test_two_g03_sheets_resolve_differently(self, overrides):
        a = resolve_sheet_ovr("跟函函证过程控制G0-3", "G0", overrides)
        b = resolve_sheet_ovr("函证差异核对表G0-3（证券投资）", "G0", overrides)
        assert a != b
        assert a == "confirmation-followup"
        assert b == "confirmation-diff-securities"


class TestG0PollutionF08:
    """G0 内污染 sheet 函证程序舞弊风险评价表F0-8 → fraud-risk。"""

    def test_f08_resolves_fraud_risk(self, overrides):
        # 尾部 F0-8 → 编码尾码 override['F0-8'] = fraud-risk（与精确 sheet_name 同值）
        assert (
            resolve_sheet_ovr("函证程序舞弊风险评价表F0-8", "G0", overrides)
            == "confirmation-fraud-risk"
        )


class TestL0PollutionF0A:
    """L0 内污染 sheet 函证程序表F0A → a-program-console。"""

    def test_f0a_resolves_program_console(self, overrides):
        # 尾部 F0A → 编码尾码 override['F0A'] = a-program-console
        assert (
            resolve_sheet_ovr("函证程序表F0A", "L0", overrides) == "a-program-console"
        )


class TestE05Conflict:
    """E0-5 一码两表：`银行函证其他信息核对表E0-5` 在源 xlsx 里是 **hidden** sheet
    （不在 `底稿目录` 的 9 项索引里）→ 按**完整 sheet_name** 精确 skip；
    `应付银行承兑汇票发函记录表E0-5` 是真实底稿 → 仍走编码尾码 `override['E0-5']`。

    见 `test_e0_hidden_sheets_skipped.py`（以 openpyxl `sheet_state` 为裁决者）。
    """

    def test_bank_info_check_e05_skipped_by_full_name(self, overrides):
        # 隐藏 sheet：render-config 在 componentType 解析**之前**按完整 sheet_name skip
        assert overrides.get("银行函证其他信息核对表E0-5") == "skip"

    def test_bank_accept_send_record_e05(self, overrides):
        assert (
            resolve_sheet_ovr("应付银行承兑汇票发函记录表E0-5", "E0", overrides) == "d-form-table"
        )

    def test_code_tail_e05_must_not_be_skip(self, overrides):
        """反向自检：**禁止**按编码 `E0-5` skip —— 那会连真实的
        `应付银行承兑汇票发函记录表E0-5` 一起误伤（wp_render_config L722 按尾码判 skip）。
        """
        assert overrides.get("E0-5") == "d-form-table"


class TestE0Rebuild:
    """E0 重建（B 方案）核心 sheet 解析（Task 3.1）。"""

    @pytest.mark.parametrize(
        "sheet_name,wp_code,expected",
        [
            ("函证结果汇总表E0-1", "E0", "confirmation-summary"),
            ("核实被函证单位信息E0-2", "E0", "confirmation-entity-verify"),
            ("跟函函证过程控制E0-7", "E0", "confirmation-followup"),
            ("函证程序表E0A", "E0", "a-program-console"),
            # E0-6 由通用 d-form-table 升级为专属组件（用户裁决 2026-08-02：通用表格
            # 无法承载看板/受限告警/汇总键完整性校验）。sheet_name 与编码尾码两处
            # override 必须同时指向专属类型 —— sheet_name override 优先级更高，
            # 只改编码那一处会被它静默遮蔽。
            ("理财产品发函记录表E0-6", "E0", "confirmation-wealth-list"),
        ],
    )
    def test_e0_sheet_resolution(self, overrides, sheet_name, wp_code, expected):
        assert resolve_sheet_ovr(sheet_name, wp_code, overrides) == expected

    def test_e06_both_override_paths_point_to_dedicated(self, overrides):
        """E0-6 的两条 override 路径（sheet_name 精确 / 编码尾码）必须一致。

        反向自检意义：sheet_name override 优先于编码尾码（同 D0-7 范式），
        若只改编码那一处，本断言会因 sheet_name 仍是 d-form-table 而失败。
        """
        assert overrides.get("理财产品发函记录表E0-6") == "confirmation-wealth-list"
        assert overrides.get("E0-6") == "confirmation-wealth-list"
        assert resolve_sheet_ovr("理财产品发函记录表E0-6", "E0", overrides) == (
            "confirmation-wealth-list"
        )


class TestNonFallbackGuard:
    """Property 21/23/24：已登记的 confirmation-* sheet_name 精确 override 解析结果
    ∉ {confirmation-hub, skip}（漏配/兜底即失败）。"""

    # 本 spec 新增/纠正的 confirmation 相关 sheet_name 精确 override（Wave 1/2 + E0 重建）
    KNOWN_CONFIRMATION_SHEETS = [
        # G0 差异 / 污染纠正
        ("函证差异核对表G0-3（证券投资）", "G0"),
        ("函证程序舞弊风险评价表F0-8", "G0"),
        # L0 污染纠正
        ("函证程序表F0A", "L0"),
        # E0 重建
        ("函证结果汇总表E0-1", "E0"),
        ("核实被函证单位信息E0-2", "E0"),
        ("跟函函证过程控制E0-7", "E0"),
        ("函证程序表E0A", "E0"),
    ]

    @pytest.mark.parametrize("sheet_name,wp_code", KNOWN_CONFIRMATION_SHEETS)
    def test_not_fallback(self, overrides, sheet_name, wp_code):
        resolved = resolve_sheet_ovr(sheet_name, wp_code, overrides)
        assert resolved is not None, f"{sheet_name} 未命中任何 override（会落 class_code 派生兜底）"
        assert resolved not in ("confirmation-hub", "skip"), (
            f"{sheet_name} 解析为兜底值 {resolved}（Property 21/23/24 违反）"
        )


class TestSkipOverrides:
    """Task 2.1：遗留 / 占位 sheet skip 生效（精确 sheet_name key）。"""

    @pytest.mark.parametrize(
        "sheet_name",
        [
            "函证程序表-原版本备份",
            "函证结果汇总表E0-1（原）",
            # 源 xlsx 里同为 hidden、且不在「底稿目录」9 项索引内 → 不属于 E0 底稿集合
            "回函情况汇编",
            "银行函证其他信息核对表E0-5",
            "邮件传真回函核对记录F1-12",
        ],
    )
    def test_legacy_sheets_skipped(self, overrides, sheet_name):
        assert overrides.get(sheet_name) == "skip"


class TestDeadConfigDocumented:
    """G0-3S 为死配置（sheet 名中不存在该编码），保留/移除都不改变解析结果。"""

    def test_g0_3s_is_dead(self, overrides):
        # G0-3S 在 override 存在（历史），但没有任何 sheet_name 以 G0-3S 结尾
        # （_SHEET_CODE_RE 从 「...G0-3」提取的是 G0-3 不是 G0-3S）
        assert _SHEET_CODE_RE.search("函证差异核对表G0-3（证券投资）") is None
        # 即便存在也不影响两张 G0-3 sheet 的解析
        assert resolve_sheet_ovr("跟函函证过程控制G0-3", "G0", overrides) == "confirmation-followup"
