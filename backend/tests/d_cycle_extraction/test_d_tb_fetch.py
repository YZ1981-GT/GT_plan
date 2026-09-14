"""D 循环取数编排件守卫 —— Property 4 / 5 / 10 / 33。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.3, 1.4, 3.1, 3.2, 3.3, 3.6

不连库（纯函数 + 替身 session），可进 CI。

**每条断言都配反向自检** —— 复现「改造前的做法」必须打红，否则守卫是空转。
（memory 铁律：变异没打红说明守卫有缺陷，而不是代码没问题。）
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from app.services.d_cycle_extraction import d_tb_fetch
from app.services.d_cycle_extraction.d_account_resolver import DCycleAccountCodes
from app.services.d_cycle_extraction.d_tb_fetch import (
    SLOT_GROSS,
    SLOT_PROVISION,
    DCycleTbData,
    SlotAmounts,
    build_d_tb_source_codes,
    fetch_d_cycle_tb,
)
from app.services.four_table.leaf_aggregation import LeafRow, to_leaf_rows


def _strip_py_docstrings_and_comments(obj) -> str:
    """剥掉 docstring 与 `#` 注释，只留可执行代码。

    🔴 只剥 `#` 是不够的 —— 被测函数的 docstring 里会**如实写出**「不得先
    select_leaves」这类禁用符号名作为说明，裸 `in` 判定会命中说明文字
    （本守卫首版即因此假红）。同族坑见 memory「读源码型守卫必先 stripComments()」。
    """
    src = obj if isinstance(obj, str) else inspect.getsource(obj)
    out, in_doc, quote = [], False, ""
    for line in src.split("\n"):
        s = line.strip()
        if in_doc:
            if quote in s:
                in_doc = False
            continue
        if s.startswith(('"""', "'''", 'r"""', "r'''")):
            quote = '"""' if '"""' in s[:4] else "'''"
            # 单行 docstring（起止同行）
            body = s.split(quote, 1)[1]
            if quote not in body:
                in_doc = True
            continue
        if s.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


# ────────────────────────────────── 测试替身 ──────────────────────────────────


def _raw(code, name, closing, *, direction="debit", opening=None, debit=0, credit=0):
    """构造 `tb_balance` 原始行形态（含 None 余额与方向列）。"""
    return {
        "account_code": code,
        "account_name": name,
        "opening_balance": opening,
        "closing_balance": closing,
        "debit_amount": debit,
        "credit_amount": credit,
        "closing_direction": direction,
    }


class _Ctx:
    """`RenderContext` 的最小替身（编排件只用 db / project_id / year）。"""

    def __init__(self, rows=None, trial_rows=None, raise_at=None):
        self.db = object()
        self.project_id = "00000000-0000-0000-0000-000000000001"
        self.year = 2025
        self._rows = rows or []
        self._trial = trial_rows or []
        self._raise_at = raise_at


def _patch_queries(monkeypatch, ctx: _Ctx):
    """把编排件依赖的两个 async 查询替换成替身（不碰聚合与过滤，那是被测逻辑）。"""

    async def _subtree(db, pid, year, prefixes):
        if ctx._raise_at == "subtree":
            raise RuntimeError("boom-subtree")
        return to_leaf_rows(ctx._rows)

    async def _trial(db, pid, year, codes):
        if ctx._raise_at == "trial":
            raise RuntimeError("boom-trial")
        return list(ctx._trial)

    monkeypatch.setattr(d_tb_fetch, "fetch_tb_subtree", _subtree)
    monkeypatch.setattr(d_tb_fetch, "fetch_trial_balance_rows", _trial)


def _codes(**kw) -> DCycleAccountCodes:
    base = dict(wp_code="D2", gross=["1122"], gross_standard=["1122"])
    base.update(kw)
    return DCycleAccountCodes(**base)


def _run(monkeypatch, ctx, codes, **kw) -> DCycleTbData:
    _patch_queries(monkeypatch, ctx)
    return asyncio.run(fetch_d_cycle_tb(ctx, codes, **kw))


# ───────────────── Property 4：NULL 余额不污染聚合 + 行数如实 ─────────────────


class TestNullBalanceAndRowCount:
    def test_null_closing_不让聚合变None(self, monkeypatch):
        """`closing_balance=None` 经 `to_leaf_rows` 归一后聚合必须是数值。

        真实库实证 5 处 NULL（`1121.03 信用证` / `1122.02 暂估应收款` /
        `1122.12 暂扣质保金` / `1231.05` / `2203.02`）。
        """
        ctx = _Ctx([
            _raw("1122", "应收账款", 100.0),
            _raw("1122.01", "应收账款_甲", 100.0),
            _raw("1122.02", "应收账款_暂估", None),
        ])
        data = _run(monkeypatch, ctx, _codes())
        slot = data.slots[SLOT_GROSS]
        assert slot.closing is not None
        assert isinstance(slot.closing, float)
        assert slot.closing == pytest.approx(100.0)

    def test_tb_rows_count_等于命中行数含父行(self, monkeypatch):
        ctx = _Ctx([
            _raw("1122", "应收账款", 300.0),
            _raw("1122.01", "应收账款_甲", 100.0),
            _raw("1122.02", "应收账款_乙", 200.0),
            _raw("2203", "预收账款", 999.0),  # 不同前缀，不该计入
        ])
        data = _run(monkeypatch, ctx, _codes())
        assert data.slots[SLOT_GROSS].tb_rows_count == 3

    def test_反向_裸求和含None会炸或得None(self):
        """复现「不经 `to_leaf_rows` 直接求和」—— 证明归一层不是可省的。"""
        raws = [100.0, None, 50.0]
        with pytest.raises(TypeError):
            sum(raws)  # type: ignore[arg-type]

        # 而经归一后同一批数据是干净数值
        rows = to_leaf_rows([
            _raw("1122.01", "甲", 100.0),
            _raw("1122.02", "乙", None),
            _raw("1122.03", "丙", 50.0),
        ])
        assert all(isinstance(r.closing, float) for r in rows)


# ───────────────── Property 5：方向不一致的族按符号求和 ─────────────────


class TestMixedDirection:
    #: 真实库同族混合方向实证（`c8621493` 的 2651 家族）：
    #: 2651.01 租赁付款额 98,176.48(credit) + 2651.02 未确认融资费用 3,956.64(debit)
    #: 父额 94,219.84 —— 裸求和得 102,133.12（偏 7,913.28）
    _PARENT = 94219.84
    _NAIVE_SUM = 102133.12

    def _rows(self):
        return [
            _raw("2651", "租赁负债", self._PARENT, direction="credit"),
            _raw("2651.01", "租赁负债_租赁付款额", 98176.48, direction="credit"),
            _raw("2651.02", "租赁负债_未确认融资费用", 3956.64, direction="debit"),
        ]

    def test_混合方向按符号求和与父额勾稽(self, monkeypatch):
        ctx = _Ctx(self._rows())
        codes = _codes(wp_code="D3", gross=["2651"], gross_standard=["2651"])
        data = _run(monkeypatch, ctx, codes)
        slot = data.slots[SLOT_GROSS]
        assert slot.closing == pytest.approx(self._PARENT, abs=0.01), (
            "应取与父额勾稽成立的符号约定，实得 %s" % slot.closing
        )
        assert slot.parent_diff == pytest.approx(0.0, abs=0.01)

    def test_反向_逐行abs之和与带符号和不等(self):
        """复现「逐行 abs」—— 结果偏离父额，证明符号约定判定不可省。"""
        naive = 98176.48 + 3956.64
        assert naive == pytest.approx(self._NAIVE_SUM, abs=0.01)
        assert abs(naive - self._PARENT) > 0.01

    def test_不得先select_leaves(self):
        """🔴 父行是符号约定的判定依据，预先筛叶子会让该判定永久失效。

        🔴 判据必须先剥 **docstring**，不只是剥 `#` 注释 —— `_sum_slot` 自己的
        docstring 里就写着「不得先 select_leaves」这句说明，裸 `in` 断言会命中
        说明文字而恒红（本守卫首版即中招；平台已登记的同族坑）。
        """
        src = _strip_py_docstrings_and_comments(inspect.getsource(d_tb_fetch._sum_slot))
        assert "select_leaves" not in src, (
            "🔴 `_sum_slot` 内不得 select_leaves —— 父行是 resolve_leaf_totals "
            "判定符号约定的依据"
        )
        # 反向自检：剥离函数不能把整段代码吃掉，否则断言退化成空转
        assert "resolve_leaf_totals" in src, "剥离过度 —— 真实代码被吃掉了"

    def test_反向_剥离前的裸断言会被docstring骗过(self):
        """证明上一条为何必须剥 docstring（复现首版的假红）。"""
        raw = inspect.getsource(d_tb_fetch._sum_slot)
        assert "select_leaves" in raw, (
            "docstring 里本该有那句说明 —— 若已删除，请同步简化上一条断言"
        )


# ──────────────────────── Property 10：四态互不混淆 ────────────────────────


class TestFourStates:
    def test_态1_无科目(self, monkeypatch):
        """found=False ⇒ amount is None 且 codes == []。

        🔴 四个金额字段**逐个**断言 None —— 只查 `closing` 会放过「无科目却返回
        0.0」这个变异（变异检验实测漏过）。「本项目无此科目」与「余额为 0」必须
        可区分，否则审定表会把未开展的业务显示成 0.00。
        """
        ctx = _Ctx([])
        codes = _codes(wp_code="D5", gross=[], gross_standard=[])
        data = _run(monkeypatch, ctx, codes)
        slot = data.slots[SLOT_GROSS]
        assert slot.found is False
        assert slot.state == "no_account"
        assert (slot.opening, slot.closing, slot.debit, slot.credit) == (
            None, None, None, None,
        ), "无科目槽的四个金额字段必须全为 None，不得出现 0.0"
        assert slot.query_codes == ()
        assert data.amount_of(SLOT_GROSS) is None
        # 载荷侧同样不得把 None 兑换成 0
        payload = build_d_tb_source_codes(codes, data)
        assert payload["slots"][SLOT_GROSS]["closing"] is None

    def test_态2b_科目表有但四表无数据(self, monkeypatch):
        """found=True + rows=0（点号码）⇒ amount is None，且不是 prefix_mismatch。"""
        ctx = _Ctx([_raw("9999", "别的科目", 1.0)])
        codes = _codes(wp_code="D6", gross=["1141"], gross_standard=["1141"])
        data = _run(monkeypatch, ctx, codes)
        slot = data.slots[SLOT_GROSS]
        assert slot.found is True
        assert slot.tb_rows_count == 0
        assert slot.closing is None, "🔴 无数据必须是 None，不能是 0.0"
        assert slot.prefix_mismatch is False
        assert slot.state == "no_data"

    def test_态3_余额确实为0(self, monkeypatch):
        """found=True + rows>0 + 聚合为 0 ⇒ amount == 0.0（**不是** None）。"""
        ctx = _Ctx([
            _raw("1122", "应收账款", 0.0),
            _raw("1122.01", "应收账款_甲", 0.0),
        ])
        data = _run(monkeypatch, ctx, _codes())
        slot = data.slots[SLOT_GROSS]
        assert slot.found is True
        assert slot.tb_rows_count == 2
        assert slot.closing == 0.0
        assert slot.closing is not None, "🔴 「余额为 0」与「无数据」必须可区分"
        assert slot.state == "ok"

    def test_四态两两互斥(self, monkeypatch):
        """同一批场景跑下来，state 取值互不重复地覆盖三态（态 4 是键不存在）。"""
        cases = {
            "no_account": (_codes(wp_code="D5", gross=[], gross_standard=[]), []),
            "no_data": (
                _codes(wp_code="D6", gross=["1141"], gross_standard=["1141"]),
                [_raw("9999", "别的", 1.0)],
            ),
            "ok": (_codes(), [_raw("1122", "应收账款", 5.0)]),
        }
        seen = {}
        for expect, (codes, rows) in cases.items():
            data = _run(monkeypatch, _Ctx(rows), codes)
            seen[expect] = data.slots[SLOT_GROSS].state
        assert seen == {k: k for k in cases}

    def test_态4_未取数则载荷无该槽键(self):
        """render 未执行 ⇒ 载荷里压根没有 slots 键（不是空 dict）。"""
        pc: dict = {}
        assert "tb_source_codes" not in pc
        # 反向：取过数就必然有 slots 键
        out = build_d_tb_source_codes(
            _codes(),
            DCycleTbData(wp_code="D2", slots={SLOT_GROSS: SlotAmounts(key=SLOT_GROSS)}),
        )
        assert "slots" in out

    def test_amount_of_无数据返None(self):
        data = DCycleTbData(
            wp_code="D6", slots={SLOT_GROSS: SlotAmounts(key=SLOT_GROSS, found=False)}
        )
        assert data.amount_of(SLOT_GROSS) is None
        assert data.amount_of("不存在的槽") is None


# ───────────── Property 33：前缀体系不匹配被检出而非静默取空 ─────────────


class TestPrefixMismatch:
    def test_横杠码且零命中判prefix_mismatch(self, monkeypatch):
        """`1231-05` 在 `account_mapping` 零反解 ⇒ 保留标准码 ⇒ 点号体系必零命中。"""
        ctx = _Ctx([_raw("1141", "合同资产", 100.0)])
        codes = _codes(
            wp_code="D6",
            gross=["1141"],
            gross_standard=["1141"],
            provision=["1231-05"],
            provision_standard=["1231-05"],
            subject_keywords=("合同资产",),
        )
        data = _run(monkeypatch, ctx, codes)
        slot = data.slots[SLOT_PROVISION]
        assert slot.tb_rows_count == 0
        assert slot.prefix_mismatch is True, (
            "🔴 含横杠且零命中必须标 prefix_mismatch —— 否则「反解失败」被显示成「无数据」"
        )
        assert slot.state == "prefix_mismatch"
        assert slot.closing is None

    def test_反向_点号码零命中不标prefix_mismatch(self, monkeypatch):
        """构造 `1231.04`（点号）零命中 ⇒ 标志必须为假，否则该标志无鉴别力。"""
        ctx = _Ctx([_raw("1141", "合同资产", 100.0)])
        codes = _codes(
            wp_code="D6",
            gross=["1141"],
            gross_standard=["1141"],
            provision=["1231.04"],
            provision_standard=["1231-04"],
            subject_keywords=(),
        )
        data = _run(monkeypatch, ctx, codes)
        slot = data.slots[SLOT_PROVISION]
        assert slot.tb_rows_count == 0
        assert slot.prefix_mismatch is False

    def test_有数据时不标mismatch(self, monkeypatch):
        """即便码里有横杠，只要命中了行就不是 mismatch。"""
        ctx = _Ctx([_raw("1231-05", "坏账准备-合同资产", 10.0, direction="credit")])
        codes = _codes(
            wp_code="D6",
            gross=[],
            gross_standard=[],
            provision=["1231-05"],
            provision_standard=["1231-05"],
            subject_keywords=("合同资产",),
        )
        data = _run(monkeypatch, ctx, codes)
        slot = data.slots[SLOT_PROVISION]
        assert slot.tb_rows_count == 1
        assert slot.prefix_mismatch is False

    def test_has_prefix_mismatch_汇总标志(self, monkeypatch):
        ctx = _Ctx([_raw("1141", "合同资产", 1.0)])
        codes = _codes(
            wp_code="D6",
            gross=["1141"],
            gross_standard=["1141"],
            provision=["1231-05"],
            provision_standard=["1231-05"],
            subject_keywords=("合同资产",),
        )
        data = _run(monkeypatch, ctx, codes)
        out = build_d_tb_source_codes(codes, data)
        assert out["has_prefix_mismatch"] is True


# ───────────────────── fail-open：取数失败不阻断 render ─────────────────────


class TestFailOpen:
    def test_subtree失败返回ok_false不抛(self, monkeypatch):
        ctx = _Ctx([], raise_at="subtree")
        data = _run(monkeypatch, ctx, _codes())
        assert data.ok is False
        assert data.error and "boom-subtree" in data.error

    def test_trial失败不影响槽取数(self, monkeypatch):
        ctx = _Ctx([_raw("1122", "应收账款", 7.0)], raise_at="trial")
        data = _run(monkeypatch, ctx, _codes())
        assert data.ok is True
        assert data.slots[SLOT_GROSS].closing == pytest.approx(7.0)

    def test_无前缀直接返双槽not_found(self, monkeypatch):
        ctx = _Ctx([])
        codes = _codes(gross=[], gross_standard=[], provision=[], provision_standard=[])
        data = _run(monkeypatch, ctx, codes)
        assert data.slots[SLOT_GROSS].found is False
        assert data.slots[SLOT_PROVISION].found is False


# ────────────────── 载荷：向后兼容扁平键不得丢（Property 32 的一部分）──────────────────


class TestPayloadBackwardCompat:
    _FLAT_KEYS = (
        "gross",
        "provision",
        "gross_standard",
        "provision_standard",
        "resolved_from",
    )

    def test_扁平键保留(self, monkeypatch):
        """前端 `html_data` 在 TS 里是 any —— 改键名不会编译报错，只会静默读到 undefined。"""
        ctx = _Ctx([_raw("1122", "应收账款", 1.0)])
        codes = _codes()
        data = _run(monkeypatch, ctx, codes)
        out = build_d_tb_source_codes(codes, data)
        for k in self._FLAT_KEYS:
            assert k in out, "🔴 既有消费方在读的扁平键 %s 丢失" % k

    def test_新增四态字段齐备(self, monkeypatch):
        ctx = _Ctx([_raw("1122", "应收账款", 1.0)])
        codes = _codes()
        data = _run(monkeypatch, ctx, codes)
        out = build_d_tb_source_codes(codes, data)
        slot = out["slots"][SLOT_GROSS]
        for k in ("found", "state", "query_codes", "tb_rows_count", "prefix_mismatch",
                  "dropped", "warnings"):
            assert k in slot, "槽载荷缺 %s" % k
        assert "parent_check" in out
        assert "fetch_ok" in out


# ───────── 溯源口径：query_codes 必须是**过滤后**的码（变异检验补充） ─────────


class TestQueryCodesReflectFilter:
    """`query_codes` 是「实际用于查 tb_balance 的前缀」，必须已过名称过滤。

    🔴 若它记的是未过滤的原始码，溯源面板展示的口径与真实取数口径不一致 ——
    审计师会看到「查了 1231.05」而实际没查，且 `_ParentCheckView.codes` 也用它，
    会让三口径比对把被剔掉的码重新算进去（`diff_parent` 与实际取数对不上）。

    本类由变异检验补出：把 `query_codes=tuple(kept)` 改成 `tuple(codes)` 时，
    改造前的守卫**全绿**（22 例一条没红）。
    """

    _NAMES = {
        "1231.02": "坏账准备_应收账款",
        "1231.05": "坏账准备_长期应收款",  # account_mapping 的 auto_fuzzy 错映射
    }

    def _rows(self):
        return [
            _raw("1231.02", "坏账准备_应收账款", 100.0, direction="credit"),
            _raw("1231.05", "坏账准备_长期应收款", 900.0, direction="credit"),
        ]

    def _slot(self, monkeypatch):
        ctx = _Ctx(self._rows())
        codes = _codes(
            wp_code="D2",
            gross=[],
            gross_standard=[],
            provision=["1231.02", "1231.05"],
            provision_standard=["1231-02"],
            subject_keywords=("应收账款",),
        )
        return _run(monkeypatch, ctx, codes).slots[SLOT_PROVISION]

    def test_query_codes_不含被剔除的码(self, monkeypatch):
        slot = self._slot(monkeypatch)
        assert "1231.05" not in slot.query_codes, (
            "🔴 query_codes 记了被名称过滤剔除的码 —— 溯源口径与实际取数不一致"
        )
        assert slot.query_codes == ("1231.02",)

    def test_query_codes_与dropped无交集(self, monkeypatch):
        slot = self._slot(monkeypatch)
        assert not (set(slot.query_codes) & {d["code"] for d in slot.dropped})

    def test_金额不含被剔除码的余额(self, monkeypatch):
        """最硬的判据：被剔掉的 900 不得进入聚合结果。"""
        slot = self._slot(monkeypatch)
        assert slot.closing == pytest.approx(100.0, abs=0.01), (
            "备抵金额 %s 说明错映射的长期应收款坏账被算进来了" % slot.closing
        )

    def test_tb_rows_count_只数保留码的行(self, monkeypatch):
        slot = self._slot(monkeypatch)
        assert slot.tb_rows_count == 1, (
            "行数 %s —— 应只数保留码命中的行" % slot.tb_rows_count
        )


class TestEmptySlotEarlyReturn:
    """槽级早退路径（`_build_slot` 内 codes 为空）必须与函数级早退同口径。

    🔴 变异检验暴露的守卫盲区：`fetch_d_cycle_tb` 有**两条**「无科目」早退 ——
    ① 函数开头（两槽都空 ⇒ 整体早退）② :func:`_build_slot` 内（该槽空）。
    只测 ``gross=[]`` 走的是 ①，把 ② 改成 ``closing=0.0`` 时守卫仍全绿。

    走到 ② 的真实场景 = **无备抵科目的循环**（D3 预收款项 / D5 应收款项融资 /
    D7 合同负债，其 spec 压根没声明 ``fallback_provision``）—— 它们的 provision 槽
    必须是「无此科目」而不是「余额 0」，否则审定表会凭空多出一行 0.00 的坏账准备。
    """

    def test_无备抵循环的备抵槽走槽级早退且金额为None(self, monkeypatch):
        ctx = _Ctx([_raw("2203", "预收账款", 500.0, direction="credit")])
        codes = _codes(
            wp_code="D3", gross=["2203"], gross_standard=["2203"],
            provision=[], provision_standard=[],
        )
        data = _run(monkeypatch, ctx, codes)
        gross, prov = data.slots[SLOT_GROSS], data.slots[SLOT_PROVISION]
        # 原值槽正常取到数 —— 证明确实走了 `_build_slot`（不是函数级早退）
        assert gross.found is True and gross.closing is not None
        # 备抵槽：无此科目
        assert prov.found is False, "无备抵声明的循环，备抵槽必须 found=False"
        assert prov.state == "no_account"
        assert prov.closing is None, (
            "🔴 备抵槽金额必须是 None（无此科目）而非 0.0 —— 后者会让审定表"
            "凭空多出一行 0.00 的坏账准备，与「余额确实为 0」不可区分"
        )
        assert prov.opening is None and prov.debit is None and prov.credit is None
        assert prov.query_codes == ()
        assert data.amount_of(SLOT_PROVISION) is None


# ───────────── Property 5（备抵侧）：贷方两种符号约定归一为「计提」口径 ─────────────


class TestProvisionSignNormalization:
    """备抵必须取绝对值归一，否则「贷方存负」的项目审定表会显示负数计提。

    真实库实证两种约定并存（memory 已登记）：`tb_balance` 的备抵科目既有存正的
    也有存负的。审定表「减：坏账准备」一栏是正数口径 ⇒ 取数侧必须归一。

    🔴 本组是变异检验补出来的盲区 —— 首版守卫把 `absolute=True` 改成 `False`
    时 27 例**全绿**（M4 变异未打红），说明备抵符号约定完全没被约束。
    """

    def _rows(self, closing):
        """🔴 必须构造**带子科目**的族，否则本组断言恒真、变异检验测不出东西。

        `resolve_leaf_totals` 对「父科目本身就是叶子」（无子科目）走捷径分支，
        该分支用的 `parent_abs` **已经 abs 过** ⇒ `absolute=True/False` 结果
        完全相同。首版 fixture 只给一行 `1231.02`，故把 `absolute=True` 改成
        `False` 时 30 例全绿（M4 变异未打红）—— 是 fixture 的缺陷不是实现的。
        """
        half = closing / 2
        return [
            _raw("1231.02", "坏账准备_应收账款", closing, direction="credit"),
            _raw("1231.02.01", "坏账准备_应收账款_甲", half, direction="credit"),
            _raw("1231.02.02", "坏账准备_应收账款_乙", half, direction="credit"),
        ]

    @pytest.mark.parametrize("stored", [-406014.85, 406014.85])
    def test_两种约定都归一为正(self, monkeypatch, stored):
        ctx = _Ctx(self._rows(stored))
        codes = _codes(
            wp_code="D2",
            gross=["1122"], gross_standard=["1122"],
            provision=["1231.02"], provision_standard=["1231-02"],
            subject_keywords=("应收账款",),
        )
        data = _run(monkeypatch, ctx, codes)
        p = data.slots[SLOT_PROVISION]
        assert p.closing == pytest.approx(abs(stored), abs=0.01), (
            "备抵须归一为正数计提口径，存 %s 得 %s" % (stored, p.closing)
        )

    def test_原值侧不做绝对值归一(self, monkeypatch):
        """反向边界：原值侧必须保留符号 —— `1122.11` 实测期末 −114,209,110.16，
        套 abs 会让 D2 合计偏 2.28 亿（memory 已登记的真实数字）。
        """
        # 同上：必须有真实子科目层，否则走「父即叶子」捷径分支测不出 absolute 的差别
        ctx = _Ctx([
            _raw("1122", "应收账款", -100.0, direction="credit"),
            _raw("1122.11", "应收账款_收款通", -60.0, direction="credit"),
            _raw("1122.12", "应收账款_暂扣质保金", -40.0, direction="credit"),
        ])
        data = _run(monkeypatch, ctx, _codes())
        g = data.slots[SLOT_GROSS]
        assert g.closing is not None
        assert g.closing < 0, "原值侧被 abs 归一了，负余额叶子会让合计偏离父额"
