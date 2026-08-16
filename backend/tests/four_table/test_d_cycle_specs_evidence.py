"""D 循环科目规格证据守卫 —— Property 7 / 34 / 35（含跨模块交叉锁死）。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 2.1, 2.2, 2.5, 2.6, 2.7, 2.8

不连库（冻结证据 + 源码级断言），可进 CI。

为什么本文件必须存在（平台既有守卫的覆盖缺口）
----------------------------------------------
`tests/four_table/test_cycle_specs_row_code_evidence.py` 的 ``_all_specs()`` 只导入
``d_cycle_specs.D_CYCLE_SPECS``，而 D 类 render **真正消费的是**
``d_cycle_extraction.d_account_resolver.D_ACCOUNT_SPECS``（前者当前不接线，见其文件头）
⇒ ``D_ACCOUNT_SPECS`` 的 ``row_code`` **完全没有守卫**。

这正是 memory 已登记的「同名导出 + 守卫导入错模块 = 整类错误永久逃逸」范式
（L 循环那次：`four_table/l_cycle_specs.py` 与 `l_cycle_extraction/account_scope.py`
都导出 ``L_CYCLE_SPECS``，守卫导入了 row_code 全对的那份，被真实消费的那份 4 处错行
全部逃逸）。本文件把**被消费的那份**与平台证据表交叉锁死。
"""
from __future__ import annotations

import inspect
import re

import pytest


def _code_only(src: str) -> str:
    """剥掉 docstring 与 ``#`` 注释，只留可执行代码。

    🔴 只剥 ``#`` 是不够的 —— 本 spec 的模块普遍在 docstring 里**如实写出**
    「``d_cycle_specs`` 保留但不接线」这类交叉说明，裸 ``in`` / ``\\b`` 判定会把
    说明散文数成真实引用（本守卫首版即因此假红）。
    同族坑见 memory「读源码型守卫必先 stripComments()」。
    """
    out: list[str] = []
    in_doc = False
    quote = ""
    for line in src.split("\n"):
        s = line.strip()
        if in_doc:
            if quote in s:
                in_doc = False
            continue
        if s.startswith(('"""', "'''", 'r"""', "r'''")):
            quote = '"""' if '"""' in s[:4] else "'''"
            body = s.split(quote, 1)[1]
            if quote not in body:
                in_doc = True
            continue
        if s.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)

from app.services.d_cycle_extraction.d_account_resolver import (
    D_ACCOUNT_SPECS,
    D_SUBJECT_KEYWORDS,
    NOT_IN_SCOPE,
)
from app.services.four_table.d_cycle_specs import (
    D_CYCLE_SPECS,
    D_PL_CYCLES,
    D_PL_POSITIVE_SIDE,
)

# ──────────────────────────────────────────────────────────────────────────────
# 冻结证据：D 类 row_code → report_config 行名
#
# 取自 2026-08-05 对 `report_config` 的只读查询（四准则逐条），与平台
# `test_cycle_specs_row_code_evidence._ROW_CODE_EVIDENCE` 中的 D 类条目逐字一致 ——
# 下方 `test_evidence_agrees_with_platform_table` 会做交叉比对，防两处漂移。
# ──────────────────────────────────────────────────────────────────────────────
_D_ROW_NAMES: dict[str, str] = {
    "BS-005": "应收票据",
    "BS-006": "应收账款",
    "BS-046": "预收款项",
    "BS-007": "应收款项融资",
    "BS-011": "合同资产",
    "BS-047": "合同负债",
    "IS-001": "一、营业收入",
}

#: 备抵报表行 —— **不在**平台证据表里（因其 formula 为 NULL 或用点号恒空），
#: 故单独冻结并附实证理由，防被当成「漏登记」而误加。
_D_PROVISION_ROWS: dict[str, str] = {
    # `IMP-004 三、合同资产减值准备` 四准则 formula **全 NULL** ⇒ 解析必失败走兜底码。
    # 仍声明它，是为了该行将来被补上公式时自动生效。
    "IMP-004": "四准则 formula 全 NULL，解析必失败 → 走 fallback_provision",
}

#: 每循环 row_code 的期望值（被消费的那份 = `D_ACCOUNT_SPECS`；D1/D4 另有去处）
_EXPECTED_ROW_CODE: dict[str, str] = {
    "D2": "BS-006",
    "D3": "BS-046",
    "D5": "BS-007",
    "D6": "BS-011",
    "D7": "BS-047",
}

#: 一级科目通名 —— 备抵槽的 `names` 里出现任何一个即打红（Property 7）
_BARE_PROVISION_WORDS = (
    "坏账准备",
    "减值准备",
    "跌价准备",
    "累计折旧",
    "累计摊销",
)


def _src(mod) -> str:
    """源码去 `#` 注释（docstring 保留 —— 本文件有断言要读 docstring）。"""
    return "\n".join(
        l for l in inspect.getsource(mod).split("\n") if not l.strip().startswith("#")
    )


# ─────────────── Property 7 前置：被消费的规格与证据表交叉锁死 ───────────────


class TestConsumedSpecsRowCodes:
    """🔴 断言对象是 `D_ACCOUNT_SPECS`（render 真正消费的那份），不是 `D_CYCLE_SPECS`。"""

    def test_registry_shape(self):
        assert set(D_ACCOUNT_SPECS) == set(_EXPECTED_ROW_CODE), (
            "D_ACCOUNT_SPECS 的循环集合变了，先确认是有意扩缩还是漏改"
        )

    @pytest.mark.parametrize("wp", sorted(_EXPECTED_ROW_CODE))
    def test_row_code_matches_evidence(self, wp):
        spec = D_ACCOUNT_SPECS[wp]
        expected = _EXPECTED_ROW_CODE[wp]
        assert spec.row_code == expected, (
            "%s 的 row_code=%s 与实证不符（应为 %s = %s）"
            % (wp, spec.row_code, expected, _D_ROW_NAMES[expected])
        )
        assert expected in _D_ROW_NAMES, "%s 未登记行名证据" % expected

    def test_provision_row_code_registered(self):
        """声明了备抵报表行的循环，该行必须在冻结证据里带理由。"""
        for wp, spec in D_ACCOUNT_SPECS.items():
            prc = spec.provision_row_code
            if prc:
                assert prc in _D_PROVISION_ROWS, (
                    "%s 声明备抵报表行 %s 但未登记实证理由" % (wp, prc)
                )
                assert len(_D_PROVISION_ROWS[prc]) >= 10

    def test_no_two_cycles_claim_same_row_code(self):
        """跨循环互斥 —— 这条断言正是当年抓出 G6/G8/G9 错位链的判据。"""
        seen: dict[str, str] = {}
        for wp, spec in D_ACCOUNT_SPECS.items():
            rc = spec.row_code
            assert rc not in seen, (
                "row_code %s 被 %s 与 %s 同时认领（跨循环双算风险）" % (rc, seen[rc], wp)
            )
            seen[rc] = wp

    def test_evidence_agrees_with_platform_table(self):
        """与平台证据表的 D 类条目逐字比对（防两处各自漂移成双真源）。"""
        from backend.tests.four_table import test_cycle_specs_row_code_evidence as plat  # noqa: E501

        table = getattr(plat, "_ROW_CODE_EVIDENCE", None)
        assert isinstance(table, dict) and len(table) >= 50, (
            "平台证据表结构变了（常量名或规模），本交叉断言已失效 —— 先修判据"
        )
        checked = 0
        for rc, name in _D_ROW_NAMES.items():
            if rc in table:
                assert table[rc][0] == name, (
                    "row_code %s 行名两处不一致：本文件=%r 平台=%r"
                    % (rc, name, table[rc][0])
                )
                checked += 1
        assert checked >= 6, "只比对到 %d 条，疑似平台表键名变了" % checked

    def test_平台守卫确实没覆盖被消费的那份(self):
        """反向锁死本文件存在的理由。

        平台 `_all_specs()` 只导入 `D_CYCLE_SPECS`。哪天它把 `D_ACCOUNT_SPECS`
        也纳入了，本断言打红 —— 那时应删掉本文件的 row_code 组，避免双真源。
        """
        from backend.tests.four_table import test_cycle_specs_row_code_evidence as plat  # noqa: E501

        src = _src(plat)
        assert "D_ACCOUNT_SPECS" not in src, (
            "平台守卫已开始覆盖 D_ACCOUNT_SPECS —— 请删除本文件的 row_code 断言组，"
            "改由平台单一真源维护"
        )
        assert "D_CYCLE_SPECS" in src, "平台守卫的 D 类导入变了，交叉判据需重校"


# ─────────────────── Property 7：备抵槽不含一级科目通名 ───────────────────


class TestProvisionSlotNaming:
    """裸通名会让 D1/D2 双双命中整个 `1231`（真实库虚增，与 K1 那次 31.6 倍同源）。"""

    @staticmethod
    def _provision_slots():
        for wp, spec in D_CYCLE_SPECS.items():
            for slot in spec.slots:
                if getattr(slot, "is_provision", False):
                    yield wp, slot

    def test_有备抵槽的循环不为空(self):
        got = {wp for wp, _ in self._provision_slots()}
        assert got == {"D1", "D2", "D6"}, (
            "备抵槽所在循环变了，实得 %s（实证 D1/D2/D6 有备抵，D3/D5/D7 无）" % sorted(got)
        )

    def test_names_不含裸通名(self):
        for wp, slot in self._provision_slots():
            for name in slot.names:
                assert name not in _BARE_PROVISION_WORDS, (
                    "%s 备抵槽含裸通名 %r —— 会命中一级科目 1231 整族" % (wp, name)
                )

    def test_names_覆盖横杠与下划线两种写法(self):
        """standard 表用横杠、client 表用下划线，两者都要认。"""
        for wp, slot in self._provision_slots():
            names = list(slot.names)
            assert any("-" in n for n in names), "%s 缺横杠写法：%s" % (wp, names)
            assert any("_" in n for n in names), "%s 缺下划线写法：%s" % (wp, names)

    def test_每个备抵槽都声明了主体关键词(self):
        for wp, slot in self._provision_slots():
            kws = tuple(getattr(slot, "subject_keywords", ()) or ())
            assert kws, "%s 备抵槽未声明 subject_keywords" % wp
            for kw in kws:
                assert kw.strip(), "%s 的关键词含空白项" % wp


# ────────────── Property 35：主体关键词粒度足以区分同族科目 ──────────────


class TestKeywordGranularityInSpecs:
    """`d_cycle_specs` 与 `d_account_resolver` 两处关键词必须一致（防单侧改动）。"""

    def test_两处关键词一致(self):
        for wp, kws in D_SUBJECT_KEYWORDS.items():
            spec = D_CYCLE_SPECS.get(wp)
            assert spec is not None, "%s 不在 D_CYCLE_SPECS" % wp
            slot_kws: tuple[str, ...] = ()
            for slot in spec.slots:
                if getattr(slot, "is_provision", False):
                    slot_kws = tuple(getattr(slot, "subject_keywords", ()) or ())
            assert set(kws) <= set(slot_kws), (
                "%s 的关键词两处不一致：resolver=%s spec=%s" % (wp, kws, slot_kws)
            )

    def test_d2_关键词能区分长期应收款(self):
        """🔴 「应收」放行错映射、「应收账款」拦住它 —— 差别只在这一格。"""
        kws = D_SUBJECT_KEYWORDS["D2"]
        assert kws == ("应收账款",)
        wrong = "坏账准备_长期应收款"
        right = "坏账准备_应收账款"
        assert not any(k in wrong for k in kws), "关键词放过了 %s" % wrong
        assert any(k in right for k in kws), "关键词拦住了正确的 %s" % right

    def test_反向_关键词写宽则两者都放行(self):
        """复现粒度不足 —— 证明上一条断言不是空话。"""
        loose = ("应收",)
        assert any(k in "坏账准备_长期应收款" for k in loose)
        assert any(k in "坏账准备_应收账款" for k in loose)


# ────────── Property 34：语义规格保留但不接线，且理由与去处在册 ──────────


class TestSpecNotWiredAndScopeRegistered:
    def test_docstring_写明不接线(self):
        from app.services.four_table import d_cycle_specs

        doc = d_cycle_specs.__doc__ or ""
        assert "不接线" in doc
        assert "d_account_resolver" in doc, "须写明 D2~D7 的真实去处"
        assert "d1_account_resolver" in doc, "须写明 D1 的真实去处"

    def test_无生产消费方(self):
        """全库 `backend/app/**` 除自身外不得 **import** `d_cycle_specs`。

        哪天真接线了本断言打红 —— 提醒同步更新 docstring 与 Property 34。

        🔴 判据必须是「真 import」而不是「全文出现模块名」：
        ``d_account_resolver`` 的 docstring 里**如实写着**「``d_cycle_specs`` 的
        语义规格保留但当前不接线」这句交叉说明，裸 ``\\bd_cycle_specs\\b`` 会把
        这句散文数成消费方而假红（本守卫首版即中招）。而 Python 跨模块消费**必须
        先 import**（无隐式全局），故 import 语句是充分必要判据。
        同族坑见 memory「只认 import 路径比符号级匹配更准」。
        """
        import os

        root = os.path.join("backend", "app")
        hits: list[str] = []
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".py") or fn == "d_cycle_specs.py":
                    continue
                p = os.path.join(dirpath, fn)
                with open(p, encoding="utf-8") as f:
                    src = f.read()
                body = _code_only(src)
                if re.search(
                    r"^\s*(?:from\s+[\w.]*\bd_cycle_specs\b|"
                    r"from\s+[\w.]+\s+import\s+[^\n]*\bd_cycle_specs\b|"
                    r"import\s+[\w.]*\bd_cycle_specs\b)",
                    body,
                    re.M,
                ):
                    hits.append(p.replace("\\", "/"))
        assert not hits, (
            "🔴 `d_cycle_specs` 出现生产消费方 %s —— 若确已接线，请更新其 docstring "
            "与 Property 34；若是误引用，请改指 d_account_resolver" % hits
        )

    def test_反向_扫描面非空(self):
        """证明上一条不是因为扫不到文件而恒绿。"""
        import os

        n = sum(
            1
            for dp, _d, fs in os.walk(os.path.join("backend", "app"))
            for f in fs
            if f.endswith(".py")
        )
        assert n > 500, "只扫到 %d 个 py 文件，路径判据失效" % n

    def test_不在范围内的循环已登记去处(self):
        assert set(NOT_IN_SCOPE) == {"D1", "D4"}
        assert not (set(D_ACCOUNT_SPECS) & set(NOT_IN_SCOPE))
        assert set(D_ACCOUNT_SPECS) | set(NOT_IN_SCOPE) == {
            "D%d" % i for i in range(1, 8)
        }
        for wp, reason in NOT_IN_SCOPE.items():
            assert len(reason) >= 10, "%s 的不纳入理由太短" % wp


# ───────────────────────── 损益类方向声明（D4） ─────────────────────────


class TestPlSideDeclaration:
    def test_d4_是唯一损益类且贷方为正(self):
        assert D_PL_CYCLES == frozenset({"D4"})
        assert D_PL_POSITIVE_SIDE["D4"] == "credit", (
            "收入类正方向在贷方 —— 差额法 Σ借−Σ贷 在含结转损益的全年账上恒为 0"
        )

    def test_非损益循环不得声明方向(self):
        assert set(D_PL_POSITIVE_SIDE) == set(D_PL_CYCLES)


# ───────────────── 负债类声明（D3 / D7 为贷方，必须显式）─────────────────


class TestLiabilityDeclaration:
    @pytest.mark.parametrize("wp", ["D3", "D7"])
    def test_预收与合同负债声明为负债类(self, wp):
        assert D_ACCOUNT_SPECS[wp].is_liability is True, (
            "%s 是贷方科目，未声明 is_liability 会让 split_gross_provision "
            "按「direction=credit 即备抵」把原值整体误判成备抵" % wp
        )

    @pytest.mark.parametrize("wp", ["D2", "D5", "D6"])
    def test_资产类不得声明为负债(self, wp):
        assert not D_ACCOUNT_SPECS[wp].is_liability

    def test_负债类不得有备抵兜底码(self):
        """声明 is_liability 会整体跳过备抵拆分 ⇒ 同时给备抵码是自相矛盾。"""
        for wp, spec in D_ACCOUNT_SPECS.items():
            if spec.is_liability:
                assert not spec.fallback_provision, "%s 既声明负债又给备抵码" % wp


# ──────────────────────────── 兜底码实证锁死 ────────────────────────────


_EXPECTED_FALLBACK: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # wp: (gross, provision)
    "D2": (("1122",), ("1231-02",)),
    "D3": (("2203",), ()),
    # `1124` 是 CAS 正确码（财会[2019]6 号），全库零命中属业务事实不是错码
    "D5": (("1124",), ()),
    # 双候选：`1142`（standard 6 项目）与 `1231-05`（standard 10 项目）
    "D6": (("1141",), ("1142", "1231-05")),
    "D7": (("2205",), ()),
}


@pytest.mark.parametrize("wp", sorted(_EXPECTED_FALLBACK))
def test_兜底码与实证一致(wp):
    spec = D_ACCOUNT_SPECS[wp]
    g, p = _EXPECTED_FALLBACK[wp]
    assert tuple(spec.fallback_gross) == g, "%s 原值兜底码变了" % wp
    assert tuple(spec.fallback_provision) == p, "%s 备抵兜底码变了" % wp


def test_d5_兜底码非空的理由在册():
    """🔴 D5 曾一度刻意留空，复核后改回给兜底码 —— 理由必须在源码里，防再次反复。"""
    from app.services.d_cycle_extraction import d_account_resolver

    src = inspect.getsource(d_account_resolver)
    assert "1124" in src
    assert "业务事实" in src, "须写明「零命中是业务事实而非错码」"
    assert "四态" in src or "found" in src, "须写明「无此科目由四态表达而非靠空兜底」"
