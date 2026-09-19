"""H 类公式预设科目自洽守卫（Task 3，Wave 1 必须先打红）。

四条判据，全部由 `backend/data/prefill_formula_mapping.json` 实证（2026-08-06）：

**A. 公式里的科目码 ⊆ 该块 `accounts` 声明 ∪ 双族 alternate**

    VIOL  H3 | 审定表（成本模式）H3-1
          declared = 1521 / 1525 / 1526 / 1527   （投资性房地产族）
          formula  = TB_SUM('1641~1643', …) + ADJ('1641', …)   （使用权资产族！）

    整块 5 条公式全是**使用权资产**口径，与自己声明的 `accounts` 完全不搭。
    且 `1641` 族在 9 个项目里余额为 0（详见 `dual_family_codes`）⇒ H3 审定表
    公式取数**恒空**，而 UI 上看不出任何异常。

**B. 损益类审定表的「期初余额」不得与「未审数」逐字相同**

    审定表H10-1：两者都是 ``=TB('6115','本期发生额')`` —— 损益类无期初余额，
    上年数只能走 ``PREV()``。当前形态让「期初」列显示本期数，是数字错。

**C. 明细表不得含项目号/客户号字面量**

    明细表H2-2 有 4 条 ``AUX('1604','项目名称','B510003'|'B510006', …)`` ——
    这是某个真实项目的工程编号被写进平台预设（同 G7-2 已修范式的污染），
    换项目即恒空。

**D. 审定表必须有 `WP()` 底稿间联动**

    H 类 25 个块 ``WP()`` 总数 = **0**。H1-1 未从 H1-2/H1-12 带入、H2-1 未从
    H2-2 带入、H8-1 未从 H8-2 带入、H9-1 未从 H9-2/H9-3 带入 ⇒ 审计师在明细表
    录完数据，审定表不会自动跟随。

🔴 **区间函数的抽取**：``TB_SUM('1641~1643','期初余额')`` 抽出的是区间端点
``1641``/``1643``，不是三个离散码。判据按「区间端点也要在声明集合里」处理 ——
H3 那块正是靠这条被抓到（`1641` 不在 `1521/1525/1526/1527` 里）。

🔴 **`PLACEHOLDER` 与 `PREV`/`WP` 不参与 A 组判定**：前者是「无法用单一科目码
表达」的一等取值类型；后两者的实参是 wp_code/sheet 名不是科目码。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 3.1~3.7 / Property 7~10
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.four_table.dual_family_codes import (  # noqa: E402
    ALTERNATE_CODES,
)

_PRESET = _BACKEND / "data" / "prefill_formula_mapping.json"

# ── 双哨兵：防 REPO_ROOT 解析漂移变成空转 ──
_SENTINELS = (
    _BACKEND / "app" / "services" / "formula_engine.py",
    _BACKEND / "data" / "prefill_formula_mapping.json",
)


def _load_h_blocks() -> list[dict]:
    data = json.loads(_PRESET.read_text(encoding="utf-8"))
    return [
        m for m in data["mappings"]
        if str(m.get("wp_code", "")).upper().startswith("H")
    ]


_H_BLOCKS = _load_h_blocks()

#: 科目码形态：4 位数字，可带 `.xx` / `-xx` 子级
_CODE_RE = re.compile(r"^\d{4}(?:[.\-]\d+)*$")

#: 只从这些函数的**第一个**实参抽科目码（`PREV`/`WP`/`PLACEHOLDER` 的首参不是科目码）
_ACCOUNT_FUNCS = ("TB", "SUM_TB", "TB_SUM", "ADJ", "AUX", "LEDGER", "LEDGER_DETAIL")


def _extract_codes(formula: str) -> set[str]:
    """抽公式里出现的科目码（含区间端点）。"""
    out: set[str] = set()
    for m in re.finditer(r"\b([A-Z_]+)\s*\(\s*'([^']*)'", formula or ""):
        func, first = m.group(1), m.group(2)
        if func not in _ACCOUNT_FUNCS:
            continue
        for part in first.split("~"):
            part = part.strip()
            if _CODE_RE.match(part):
                out.add(part)
    return out


def _cells(block: dict) -> list[dict]:
    cells = block.get("cells")
    return cells if isinstance(cells, list) else []


class TestSelfConsistency:
    """守卫自身可用性（防解析失效变成空转）。"""

    def test_sentinels_exist(self):
        for p in _SENTINELS:
            assert p.exists(), f"REPO_ROOT 解析漂移，哨兵不存在: {p}"

    def test_h_blocks_nonempty(self):
        assert len(_H_BLOCKS) >= 20, f"H 块数异常（实测应 25）: {len(_H_BLOCKS)}"

    def test_code_extraction_works(self):
        """抽取器自检 —— 含区间、含 ADJ、排除 PREV/WP。"""
        assert _extract_codes("=TB('1601','期末余额')") == {"1601"}
        assert _extract_codes("=TB_SUM('1641~1643','期初余额')") == {"1641", "1643"}
        assert _extract_codes("=ADJ('1521','aje_net')") == {"1521"}
        assert _extract_codes("=PREV('H1','审定表H1-1','审定数')") == set()
        assert _extract_codes("=WP('H1','明细表H1-2','合计')") == set()
        assert _extract_codes("=PLACEHOLDER('九品种账面金额')") == set()
        # 子级码
        assert _extract_codes("=TB('1231-01','期末余额')") == {"1231-01"}
        assert _extract_codes("=TB('1521.02','期末余额')") == {"1521.02"}


class TestAccountCoherence:
    """A 组：公式码 ⊆ accounts 声明 ∪ 双族 alternate。"""

    def test_formula_codes_subset_of_declared(self):
        allow_extra = set(ALTERNATE_CODES)
        violations: list[str] = []
        for b in _H_BLOCKS:
            declared = {str(c) for c in (b.get("account_codes") or [])}
            if not declared:
                continue  # 未声明 accounts 的块不在本判据范围
            used: set[str] = set()
            for c in _cells(b):
                used |= _extract_codes(c.get("formula", ""))
            extra = sorted(used - declared - allow_extra)
            if extra:
                violations.append(
                    f"{b.get('wp_code')} | {b.get('sheet')}: "
                    f"公式用了 {extra} 但 accounts 只声明 {sorted(declared)}"
                )
        if violations:
            pytest.fail(
                "【Wave 1 预期红】公式科目与 accounts 声明不自洽（H3 审定表整块"
                "贴的是使用权资产口径）：\n  " + "\n  ".join(violations)
            )

    def test_h3_block_is_the_known_violation(self):
        """把当前唯一违规钉死 —— 修好后此断言转为「H3 已用 1521 族」。"""
        h3 = [
            b for b in _H_BLOCKS
            if b.get("wp_code") == "H3" and "审定表" in str(b.get("sheet", ""))
        ]
        assert h3, "未找到 H3 审定表块（解析漂移？）"
        block = h3[0]
        declared = {str(c) for c in (block.get("account_codes") or [])}
        assert declared == {"1521", "1525", "1526", "1527"}, (
            f"H3 声明的 accounts 变了: {sorted(declared)}"
        )
        used: set[str] = set()
        for c in _cells(block):
            used |= _extract_codes(c.get("formula", ""))
        # 修好后：used ⊆ declared
        #
        # 🔴 消息必须以 `\n` 开头：pytest 对**单行** fail 消息会走 repr 转义，
        # 中文会显示成 `\u3010Wave 1...` 完全不可读（本轮实测踩到）。
        # 带换行的多行消息才按原文输出。
        if used - declared:
            pytest.fail(
                f"\n【Wave 1 预期红】H3 审定表公式用的是 {sorted(used)}，"
                f"应为投资性房地产族 {sorted(declared)}；"
                f"\n且 1641 族在 9 个项目余额为 0，取数恒空"
            )


    def test_h1_analysis_range_does_not_cross_into_cip(self):
        """H1 分析程序的区间上界越界到在建工程（第二处真违规，Task 7 修）。

        ``分析程序H1-3`` 写 ``TB_SUM('1601~1604','期末余额')``，而
        ``1604`` 是**在建工程**（`report_config` BS-029，属 H2 循环），
        ``1605`` 工程物资、``1606`` 固定资产清理同在区间内。

        固定资产合计的正确区间是 ``1601~1603``（原值/累计折旧/减值准备）；
        soe 侧若要含清理则应显式 ``+TB('1606')``（BS-028 soe_standalone
        公式就是这么写的），不能靠区间"顺带"扫进来。

        修好后此断言转为「区间上界 <= 1603」。
        """
        blocks = [
            b for b in _H_BLOCKS
            if b.get("wp_code") == "H1" and "分析程序" in str(b.get("sheet", ""))
        ]
        assert blocks, "未找到 H1 分析程序块（解析漂移？）"
        declared = {str(c) for c in (blocks[0].get("account_codes") or [])}
        crossed: list[str] = []
        for c in _cells(blocks[0]):
            used = _extract_codes(c.get("formula", ""))
            for code in sorted(used - declared):
                crossed.append(
                    f"{c.get('cell_ref')} | {c.get('formula')} | 越界码 {code}"
                )
        if crossed:
            lines = "\n  ".join(crossed)
            pytest.fail(
                "【Wave 1 预期红】H1 分析程序区间上界越界到别的循环科目"
                "（1604 在建工程 / 1605 工程物资 / 1606 固定资产清理）：\n  "
                + lines
            )


class TestOccurrenceOpeningColumn:
    """B 组：损益类审定表「期初余额」不得与「未审数」逐字相同。"""

    @staticmethod
    def _find(block: dict, ref: str) -> str | None:
        for c in _cells(block):
            if c.get("cell_ref") == ref:
                return c.get("formula")
        return None

    def test_h10_opening_differs_from_unadjusted(self):
        h10 = [
            b for b in _H_BLOCKS
            if b.get("wp_code") == "H10" and "审定表" in str(b.get("sheet", ""))
        ]
        assert h10, "未找到 H10 审定表块"
        block = h10[0]
        opening = self._find(block, "期初余额")
        unadj = self._find(block, "未审数")
        assert opening and unadj, f"H10 审定表缺格: opening={opening} unadj={unadj}"
        if opening == unadj:
            pytest.fail(
                f"【Wave 1 预期红】H10 审定表「期初余额」与「未审数」公式逐字相同"
                f"（{opening}）—— 损益类无期初余额，上年数应走 PREV()"
            )

    def test_opening_of_occurrence_sheet_uses_prev(self):
        """修好后：损益类审定表的期初列必须用 PREV()。"""
        h10 = [
            b for b in _H_BLOCKS
            if b.get("wp_code") == "H10" and "审定表" in str(b.get("sheet", ""))
        ]
        block = h10[0]
        opening = self._find(block, "期初余额") or ""
        unadj = self._find(block, "未审数") or ""
        if opening != unadj:  # 已修
            assert "PREV(" in opening, (
                f"H10 期初列已与未审数不同，但没走 PREV(): {opening}"
            )


class TestNoHardcodedProjectIds:
    """C 组：明细表不得含项目号/客户号字面量。"""

    #: 项目号形态：字母开头 + 数字（`B510003`）；纯数字科目码不算
    _ID_RE = re.compile(r"^[A-Za-z]+\d{3,}$")

    def test_no_project_code_literals(self):
        hits: list[str] = []
        for b in _H_BLOCKS:
            for c in _cells(b):
                f = c.get("formula", "") or ""
                for m in re.finditer(r"'([^']*)'", f):
                    v = m.group(1)
                    if self._ID_RE.match(v):
                        hits.append(
                            f"{b.get('wp_code')} | {b.get('sheet')} | "
                            f"{c.get('cell_ref')} | {v}"
                        )
        if hits:
            pytest.fail(
                "【Wave 1 预期红】预设含项目号字面量（换项目即恒空，"
                "同 G7-2 已修范式的污染）：\n  " + "\n  ".join(hits)
            )

    def test_detection_actually_works(self):
        """反向自检 —— 抓得住 B510003，且不误伤科目码。"""
        assert self._ID_RE.match("B510003")
        assert not self._ID_RE.match("1601")
        assert not self._ID_RE.match("1231-01")


class TestWorkpaperLinkage:
    """D 组：审定表必须有 WP() 底稿间联动，明细表禁写 WP() 防成环。"""

    #: 应有 WP() 的审定表（依据：各自有明细表可带入）
    _EXPECT_WP = ("H1", "H2", "H8", "H9")

    def test_adjudication_sheets_have_wp(self):
        missing: list[str] = []
        for wp in self._EXPECT_WP:
            blocks = [
                b for b in _H_BLOCKS
                if b.get("wp_code") == wp and "审定表" in str(b.get("sheet", ""))
            ]
            if not blocks:
                missing.append(f"{wp}: 未找到审定表块")
                continue
            n = sum(
                1 for b in blocks for c in _cells(b)
                if "WP(" in (c.get("formula") or "")
            )
            if n == 0:
                missing.append(f"{wp} | {blocks[0].get('sheet')}: WP()=0")
        if missing:
            pytest.fail(
                "【Wave 1 预期红】审定表无底稿间联动（明细表录完数据审定表不跟随）："
                "\n  " + "\n  ".join(missing)
            )

    def test_detail_sheets_have_no_wp(self):
        """明细表禁写 WP() —— 审定表←明细表已成链，反向引用即成环。"""
        offenders: list[str] = []
        for b in _H_BLOCKS:
            sheet = str(b.get("sheet", ""))
            if "明细表" not in sheet:
                continue
            for c in _cells(b):
                if "WP(" in (c.get("formula") or ""):
                    offenders.append(
                        f"{b.get('wp_code')} | {sheet} | {c.get('cell_ref')}"
                    )
        assert not offenders, (
            "明细表出现 WP() 会与「审定表←明细表」形成环：\n  "
            + "\n  ".join(offenders)
        )
