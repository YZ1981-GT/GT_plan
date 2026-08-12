"""E1 账户级取数共享件守卫（`e1_bank_accounts.py` 纯函数层）。

**Validates: Requirements 1.1~1.5, 1.8, 10.8, 10.9**

Property 1（active 过滤）/ Property 2（同账号聚合）/ Property 3（三级降级不臆造）
Property 4（归属三态不兜底）/ Property 5（勾稽如实不修正）/ Property 39（await 源码级）

🔴 本文件只测**纯函数**（不连库）；连库判据在 `test_e1_bank_accounts_live.py`。
两者分工：源码级断言防「漏 await」这类静默缺陷，连库断言证明取数真的产出真值。

spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/ (Task 4)
"""

from __future__ import annotations

import inspect
import asyncio
import inspect
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.four_table.e1_bank_accounts import (
    AUX_DIM_INSTITUTION,
    AUX_TYPE_BANK_ACCOUNT,
    SOURCE_PREFIX,
    TOLERANCE,
    AuxDimensions,
    BankAccountRow,
    aggregate_aux_rows,
    assign_accounts_to_slots,
    build_e1_account_prefill,
    check_accounts_vs_leaves,
    fetch_e1_bank_accounts,
    parse_aux_dimensions,
)

MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "services"
    / "four_table"
    / "e1_bank_accounts.py"
)


def _fn_body(name: str) -> str:
    """截取模块级函数体。

    🔴 必须先用**圆括号配对**跳过参数列表 —— 多行签名的 `) -> list[X]:` 那行
    缩进为 0，按「首个缩进 <= def 缩进的行即结束」会在签名处提前中断，
    截出来的"函数体"只有签名，`assert 'xxx' in body` 恒假红（memory 已记同族坑）。
    """
    src = _src()
    m = re.search(rf"(?m)^(async\s+)?def\s+{re.escape(name)}\s*\(", src)
    assert m, f"未找到函数 {name}（锚点漂移，断言会空转）"
    i = src.index("(", m.end() - 1)
    depth = 0
    while i < len(src):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    j = src.index(":", i)
    lines = src[j + 1 :].splitlines()
    out: list[str] = []
    for ln in lines:
        if ln.strip() and not ln.startswith((" ", "\t")):
            break
        out.append(ln)
    body = "\n".join(out)
    assert len(body) > 50, f"{name} 函数体截取过短（配对失效？）"
    return body


def _src() -> str:
    return MODULE_PATH.read_text(encoding="utf-8")


def _strip_comments(src: str) -> str:
    """剥 docstring 与 `#` 注释。

    🔴 本模块的 docstring 里**故意**写着 `is_deleted == False` 与「漏 await」等反例
    （给下个会话看的），不剥会被数成真实代码（memory 已记同族教训）。
    """
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    return re.sub(r"(?m)#.*$", "", out)


def _aux(
    *,
    account_code: str = "1002",
    raw: str | None = "金融机构:YG0001,工商银行;银行账户:1234567890",
    aux_name: str | None = "1234567890",
    currency: str = "CNY",
    opening: float = 0.0,
    debit: float = 0.0,
    credit: float = 0.0,
    closing: float = 100.0,
) -> SimpleNamespace:
    """构造 **aux 原始行替身**（`aggregate_aux_rows` 的真实入参形态）。

    🔴 入参不是 `BankAccountRow` 而是 ORM 行 —— 字段名必须与
    `fetch_e1_bank_accounts` 的 `sa.select(...)` 列清单逐字一致，
    否则替身与生产路径不同构、测了也不算。
    """
    return SimpleNamespace(
        account_code=account_code,
        account_name="银行存款",
        aux_name=aux_name,
        aux_dimensions_raw=raw,
        currency_code=currency,
        opening_balance=opening,
        debit_amount=debit,
        credit_amount=credit,
        closing_balance=closing,
    )


def _row(
    *,
    account_code: str = "1002",
    account_no: str = "1234567890",
    bank_name: str = "工商银行",
    closing: float = 100.0,
    opening: float = 0.0,
    parsed_level: int = 1,
) -> BankAccountRow:
    """构造已聚合的账户行（`assign_accounts_to_slots` / 勾稽的入参形态）。"""
    return BankAccountRow(
        account_code=account_code,
        account_no=account_no,
        bank_name=bank_name,
        currency="CNY",
        opening=opening,
        debit=0.0,
        credit=0.0,
        closing=closing,
        source=f"{SOURCE_PREFIX}:{account_no}",
        parsed_level=parsed_level,
    )


# ─── 反向自检：判据基础设施 ───────────────────────────────────────────────────


class TestJudgementInfrastructure:
    def test_module_source_readable(self):
        src = _src()
        assert len(src) > 2000, "模块源码过短（路径漂移？源码级断言会空转）"
        assert "def fetch_e1_bank_accounts" in src

    def test_strip_comments_is_not_a_noop(self):
        """剥注释必须真的剥掉东西，否则 Property 39 的判据形同虚设。"""
        raw = _src()
        stripped = _strip_comments(raw)
        assert len(stripped) < len(raw)
        # 模块 docstring 里确实写了反例文字（证明剥的是说明不是代码）
        assert "is_deleted" in raw
        assert "is_deleted" not in stripped, "反例文字未被剥掉 → 会被数成真实代码"

    def test_source_prefix_is_traceable(self):
        """前缀不带尾冒号；逐行 source 由 `f"{SOURCE_PREFIX}:{账号}"` 拼出（R1.8）。"""
        assert SOURCE_PREFIX == f"tb_aux_balance:{AUX_TYPE_BANK_ACCOUNT}"
        assert AUX_TYPE_BANK_ACCOUNT == "银行账户"
        assert AUX_DIM_INSTITUTION == "金融机构"

    def test_tolerance_matches_platform(self):
        """与 `leaf_aggregation.resolve_leaf_totals` 同口径（0.005 元）。"""
        assert TOLERANCE == 0.005


# ─── Property 39：`get_active_filter` 必须 await（源码级）─────────────────────


class TestProperty39ActiveFilterIsAwaited:
    def test_get_active_filter_is_awaited(self):
        """🔴 `get_active_filter` 是 async —— 漏 await 会被 fail-open 吞成空清单。

        该缺陷在 N5 与 D 循环各发生过一次 P0，且**四层验证全绿**：
        `get_diagnostics` 不报、单测用替身测不到、连库测试因 fail-open 只看到空结果。
        """
        body = _strip_comments(_src())
        hits = list(re.finditer(r"get_active_filter\s*\(", body))
        assert hits, "源码里找不到 get_active_filter 调用（判据空转）"
        for m in hits:
            head = body[max(0, m.start() - 40) : m.start()]
            assert re.search(r"await\s+$", head), (
                f"get_active_filter 调用前未紧邻 await（位置 {m.start()}）：{head!r}"
            )

    def test_missing_await_would_be_caught(self):
        """反向自检：去掉 await 的替身源码必须被同一判据判红。"""
        mutated = "active = get_active_filter(db, T, pid, year)\n"
        hits = list(re.finditer(r"get_active_filter\s*\(", mutated))
        assert hits
        head = mutated[: hits[0].start()]
        assert not re.search(r"await\s+$", head), "判据对无 await 的形态不敏感"

    def test_no_naive_is_deleted_filter(self):
        """禁裸写 `is_deleted == False`（实测裸查会多算非 active dataset 的账户）。"""
        body = _strip_comments(_src())
        assert "is_deleted" not in body, (
            "出现裸 is_deleted 过滤 —— 必须一律经 get_active_filter"
        )


# ─── Property 3：维度解析三级降级，任何一级都不臆造银行名 ─────────────────────


class TestProperty3ParseAuxDimensions:
    def test_level1_full(self):
        """真实样本：账号 + 银行名都拿到。"""
        d = parse_aux_dimensions(
            "金融机构:YG0014,上海浦东发展银行;银行账户:58080155200000296",
            "58080155200000296",
        )
        assert d == AuxDimensions(
            account_no="58080155200000296",
            bank_name="上海浦东发展银行",
            parsed_level=1,
        )
        assert d.has_bank_name is True

    def test_level2_account_only(self):
        """raw 里只有账号维度 → level 2，银行名**留空**不臆造。"""
        d = parse_aux_dimensions("银行账户:12189001040040959", "12189001040040959")
        assert d.account_no == "12189001040040959"
        assert d.bank_name == ""
        assert d.parsed_level == 2
        assert d.has_bank_name is False

    def test_level3_falls_back_to_aux_name(self):
        """raw 解析不出 → 账号退回 `aux_name`、银行名仍留空。"""
        d = parse_aux_dimensions("乱七八糟没有冒号", "6222001234567890")
        assert d.account_no == "6222001234567890"
        assert d.bank_name == ""
        assert d.parsed_level == 3

    def test_level3_on_empty_raw(self):
        d = parse_aux_dimensions(None, "ACC-1")
        assert (d.account_no, d.bank_name, d.parsed_level) == ("ACC-1", "", 3)

    def test_bank_name_is_never_the_account_no(self):
        """🔴 银行名拿不到时禁用 `aux_name` 顶替（一列账号当银行名比留空更坏）。"""
        for raw in (None, "", "银行账户:ACC-9", "垃圾"):
            d = parse_aux_dimensions(raw, "ACC-9")
            assert d.bank_name != "ACC-9"
            assert d.bank_name == ""

    def test_institution_code_is_stripped_from_name(self):
        """`YG0001,工商银行` → 只取名称部分（编码不进展示列）。"""
        d = parse_aux_dimensions("金融机构:YG0001,工商银行;银行账户:X", "X")
        assert d.bank_name == "工商银行"

    def test_institution_without_code_keeps_whole_value(self):
        """无逗号时整串即名称（不同客户格式可能不带编码）。"""
        d = parse_aux_dimensions("金融机构:招商银行;银行账户:X", "X")
        assert d.bank_name == "招商银行"

    def test_bank_name_containing_comma_keeps_tail(self):
        """名称本身含逗号时只切第一个逗号。"""
        d = parse_aux_dimensions("金融机构:YG1,某银行,某支行;银行账户:X", "X")
        assert d.bank_name == "某银行,某支行"

    def test_extra_dimensions_are_ignored(self):
        """raw 里可能并存别的维度，不得干扰账号解析。"""
        d = parse_aux_dimensions(
            "成本中心:CC01;金融机构:YG0001,工商银行;银行账户:ACC-7;业态:X",
            "ACC-7",
        )
        assert (d.account_no, d.bank_name, d.parsed_level) == ("ACC-7", "工商银行", 1)


# ─── Property 2：同账号聚合（active dataset 内多行必须求和）───────────────────


class TestProperty2AggregateByAccount:
    def test_same_account_two_rows_are_summed(self):
        """实测样本：`a7fc75e5` 的同一账号有 +25,954,468.80 / −25,874,468.80 两笔。"""
        rows = aggregate_aux_rows(
            [
                _aux(raw="银行账户:ACC-1", aux_name="ACC-1", closing=25954468.80),
                _aux(raw="银行账户:ACC-1", aux_name="ACC-1", closing=-25874468.80),
            ]
        )
        assert len(rows) == 1, "同账号未聚合 → 账户数虚高"
        assert rows[0].closing == pytest.approx(80000.00, abs=0.005)
        assert rows[0].row_count == 2

    def test_different_accounts_stay_separate(self):
        rows = aggregate_aux_rows(
            [
                _aux(raw="银行账户:A", aux_name="A"),
                _aux(raw="银行账户:B", aux_name="B"),
            ]
        )
        assert {r.account_no for r in rows} == {"A", "B"}

    def test_same_account_different_subject_stays_separate(self):
        """同账号但挂在不同科目下 → 不同账户行（键是 `(科目码, 账号)`）。"""
        rows = aggregate_aux_rows(
            [
                _aux(account_code="1002", raw="银行账户:A", aux_name="A"),
                _aux(account_code="1012.02", raw="银行账户:A", aux_name="A"),
            ]
        )
        assert len(rows) == 2
        assert {r.account_code for r in rows} == {"1002", "1012.02"}

    def test_all_amount_columns_are_summed(self):
        rows = aggregate_aux_rows(
            [
                _aux(
                    raw="银行账户:A",
                    aux_name="A",
                    opening=1.0,
                    debit=10.0,
                    credit=2.0,
                    closing=9.0,
                ),
                _aux(
                    raw="银行账户:A",
                    aux_name="A",
                    opening=2.0,
                    debit=20.0,
                    credit=3.0,
                    closing=19.0,
                ),
            ]
        )
        r = rows[0]
        assert (r.opening, r.debit, r.credit, r.closing) == (3.0, 30.0, 5.0, 28.0)

    def test_null_amounts_are_coalesced_to_zero(self):
        """🔴 `closing_balance` 可以是 NULL 而不是 0（memory 已记）→ 必须 COALESCE。"""
        rows = aggregate_aux_rows(
            [_aux(raw="银行账户:A", aux_name="A", closing=None, opening=None)]
        )
        assert rows[0].closing == 0.0
        assert rows[0].opening == 0.0

    def test_bank_name_from_richest_row_wins(self):
        """一行有银行名一行没有 → 取有的那个（不因行序丢信息）。"""
        rows = aggregate_aux_rows(
            [
                _aux(raw="银行账户:A", aux_name="A"),  # level 2，无银行名
                _aux(raw="金融机构:YG4,建设银行;银行账户:A", aux_name="A"),
            ]
        )
        assert len(rows) == 1
        assert rows[0].bank_name == "建设银行"
        assert rows[0].parsed_level == 1, "解析质量应取更好的那一级"

    def test_source_is_stamped_per_account(self):
        rows = aggregate_aux_rows([_aux(raw="银行账户:ACC-X", aux_name="ACC-X")])
        assert rows[0].source == f"{SOURCE_PREFIX}:ACC-X"

    def test_empty_input(self):
        assert aggregate_aux_rows([]) == []


# ─── Property 4：归属三态，不兜底 ─────────────────────────────────────────────


class TestProperty4SlotAssignment:
    def test_prefix_match_assigns_to_slot(self):
        a = assign_accounts_to_slots(
            [_row(account_code="1002")], {"bank": ["1002"], "other": ["1012"]}
        )
        assert [r.account_no for r in a.by_slot["bank"]] == ["1234567890"]
        assert a.by_slot["other"] == []
        assert a.unassigned == []
        assert a.by_slot["bank"][0].slot == "bank"

    def test_subaccount_prefix_matches(self):
        a = assign_accounts_to_slots(
            [_row(account_code="1012.02")], {"other": ["1012"]}
        )
        assert len(a.by_slot["other"]) == 1

    def test_prefix_match_has_dot_boundary(self):
        """🔴 `10021` 不得被 `1002` 槽吞掉（平台已踩过缺点号边界的坑）。

        变异检验 M6 首轮 GREEN 就是抓到了这个真实现缺陷（当时用的是裸
        `startswith`）—— 口径必须与共享件 `filter_by_prefixes` 一致：
        `code == p or code.startswith(p + '.')`。
        """
        rows = [
            _row(account_code="1002", account_no="A"),
            _row(account_code="1002.01", account_no="B"),
            _row(account_code="10021", account_no="C"),
        ]
        a = assign_accounts_to_slots(rows, {"bank": ["1002"]})
        assert [r.account_no for r in a.by_slot["bank"]] == ["A", "B"]
        assert [r.account_no for r in a.unassigned] == ["C"], (
            "`10021` 是另一个科目（如 100210），不得归入 `1002` 槽"
        )

    def test_source_module_uses_shared_dot_boundary_idiom(self):
        """源码级交叉锁死：本模块的前缀判据必须与共享件同款写法。"""
        body = _strip_comments(_src())
        assert 'startswith(prefix + ".")' in body or "startswith(prefix + '.')" in body, (
            "前缀匹配缺点号边界 —— 会把 `10021` 当成 `1002` 的子科目"
        )

    def test_unrelated_code_goes_to_unassigned_not_dropped(self):
        """🔴 归属不了的账户必须进 `unassigned`（宁缺勿造，禁静默丢弃）。"""
        a = assign_accounts_to_slots(
            [_row(account_code="1001")], {"bank": ["1002"], "other": ["1012"]}
        )
        assert a.by_slot["bank"] == []
        assert a.by_slot["other"] == []
        assert len(a.unassigned) == 1
        assert a.unassigned[0].slot is None

    def test_empty_slot_never_absorbs(self):
        """槽的兜底码为空（`digital`/`finance_co` 无兜底码）时不得吸走任何账户。"""
        a = assign_accounts_to_slots(
            [_row(account_code="1002")], {"bank": ["1002"], "digital": []}
        )
        assert a.by_slot["digital"] == []
        assert len(a.by_slot["bank"]) == 1

    def test_longest_prefix_wins(self):
        """多槽都能匹配时取最长前缀（避免父子码双算）。"""
        a = assign_accounts_to_slots(
            [_row(account_code="1012.02")],
            {"broad": ["1012"], "narrow": ["1012.02"]},
        )
        assert len(a.by_slot["narrow"]) == 1
        assert a.by_slot["broad"] == []

    def test_no_slot_declared_means_all_unassigned(self):
        a = assign_accounts_to_slots([_row()], {})
        assert len(a.unassigned) == 1

    def test_partition_is_complete(self):
        """归属结果必须是全集划分：各槽 ∪ unassigned == 输入，且互不重叠。"""
        rows = [
            _row(account_code="1002", account_no="A"),
            _row(account_code="1012", account_no="B"),
            _row(account_code="9999", account_no="C"),
        ]
        a = assign_accounts_to_slots(rows, {"bank": ["1002"], "other": ["1012"]})
        got = [r.account_no for rs in a.by_slot.values() for r in rs]
        got += [r.account_no for r in a.unassigned]
        assert sorted(got) == ["A", "B", "C"]
        assert len(got) == len(set(got)), "同一账户被归进多个槽"

    def test_prefix_match_respects_dot_boundary(self):
        """🔴 平台既有口径是 `code == p or code.startswith(p + '.')`。

        裸 `startswith` 会让 `10021`（另一个一级科目）被 `1002` 槽吞掉。
        变异检验 M6 首轮 GREEN 就是抓到了这个真实现缺陷
        （`leaf_aggregation.filter_by_prefixes` / `resolve_leaf_totals` 都是点号边界）。
        """
        a = assign_accounts_to_slots(
            [
                _row(account_code="1002", account_no="EXACT"),
                _row(account_code="1002.01", account_no="CHILD"),
                _row(account_code="10021", account_no="SIBLING"),
            ],
            {"bank": ["1002"]},
        )
        got = sorted(r.account_no for r in a.by_slot["bank"])
        assert got == ["CHILD", "EXACT"], f"点号边界失效：{got}"
        assert [r.account_no for r in a.unassigned] == ["SIBLING"], (
            "`10021` 与 `1002` 是两个不同的一级科目，不得被吞进 bank 槽"
        )

    def test_dot_boundary_criterion_mirrors_platform_helper(self):
        """交叉锁死：本模块的边界口径必须与 `leaf_aggregation` 同语义。

        平台真源 `filter_by_prefixes` 写的是 `code == p or code.startswith(p + ".")`；
        本模块把它抽成 `_code_matches_prefix`，两侧行为必须一致（下方逐样本比对）。
        """
        from app.services.four_table import leaf_aggregation as la
        from app.services.four_table.e1_bank_accounts import _code_matches_prefix

        helper_src = inspect.getsource(la.filter_by_prefixes)
        assert 'startswith(p + ".")' in helper_src, "平台口径漂移（helper 已改？）"

        # 行为等价：拿平台 helper 当裁决者，逐样本比对
        samples = ["1002", "1002.01", "1002.01.03", "10021", "100", "2002", ""]
        for code in samples:
            mine = _code_matches_prefix(code, "1002")
            theirs = bool(
                la.filter_by_prefixes(
                    [SimpleNamespace(account_code=code)], ["1002"]
                )
            )
            assert mine == theirs, (
                f"边界口径与平台不一致：code={code!r} 本模块={mine} 平台={theirs}"
            )

    def test_boundary_helper_is_used_not_bare_startswith(self):
        """源码级：归属判定必须走 helper，不得裸 `startswith`（M6 变异要打红）。"""
        body = _fn_body("assign_accounts_to_slots")
        assert "_code_matches_prefix" in body, "归属未走点号边界 helper"
        assert "account_code.startswith(" not in body, (
            "出现裸 startswith —— `10021` 会被 `1002` 吞掉"
        )


class TestEmptyPrefixesShortCircuits:
    """空前缀必须**直接返 []**、不查库（槽全 found=False 时的正常路径）。

    变异检验 M9（去掉早退）首轮 GREEN —— 因为 `sa.or_()` 空参产出恒假谓词、
    查库也返空 ⇒ 行为等价。但「不查库」本身是契约（省一次无谓 DB 往返，
    且 fail-open 不该被无意义的查询触发），故用替身钉住。
    """

    def test_no_db_call_when_prefixes_empty(self):
        """🔴 替身异常必须是 `BaseException` 子类才能穿透 fail-open。

        第三轮变异 M9 仍 GREEN 的根因就在这里：替身原先抛 `AssertionError`
        （`Exception` 子类）→ 被 `fetch_e1_bank_accounts` 的
        `except Exception` 吞成 warning → 返 `[]` → 断言照样通过 ⇒ 守卫空转。
        这与本 spec 要防的「fail-open 把接线错误伪装成本项目无数据」是同一个坑，
        只不过这次踩在守卫自己身上。
        """
        import asyncio

        class _DbTouched(BaseException):
            """有意继承 BaseException —— 不被被测代码的 except Exception 捕获。"""

        class _Boom:
            async def execute(self, *a, **kw):  # noqa: ANN002, ANN003
                raise _DbTouched("空前缀不得查库")

            async def rollback(self):
                raise _DbTouched("空前缀不得触发 rollback")

        for prefixes in ([], None, ["", "  "]):
            try:
                got = asyncio.run(
                    fetch_e1_bank_accounts(
                        _Boom(), "00000000-0000-0000-0000-000000000000", 2025,
                        account_prefixes=prefixes,
                    )
                )
            except _DbTouched as exc:  # noqa: PERF203
                raise AssertionError(
                    f"prefixes={prefixes!r} 时仍访问了数据库：{exc}"
                ) from exc
            assert got == [], f"prefixes={prefixes!r} 应返空"

    def test_boom_stub_actually_penetrates_fail_open(self):
        """反向自检：证明替身确实能穿透 fail-open（否则上一条是空转）。

        用非空前缀触发查库路径 —— 此时替身必须把异常抛出来，
        而不是被 `except Exception` 吞掉。
        """
        import asyncio

        class _DbTouched(BaseException):
            pass

        class _Boom:
            async def execute(self, *a, **kw):  # noqa: ANN002, ANN003
                raise _DbTouched("touched")

            async def rollback(self):
                pass

        with pytest.raises(_DbTouched):
            asyncio.run(
                fetch_e1_bank_accounts(
                    _Boom(), "00000000-0000-0000-0000-000000000000", 2025,
                    account_prefixes=["1002"],
                )
            )

    def test_early_return_is_in_source(self):
        """源码级：早退分支必须在 `try` 之前（否则异常路径会掩盖它）。"""
        body = _fn_body("fetch_e1_bank_accounts")
        i_ret = body.find("return []")
        i_try = body.find("try:")
        assert 0 <= i_ret < i_try, "空前缀早退必须在 try 之前"


class TestFailOpenRollsBack:
    """fail-open 必须 `rollback()`，否则污染同一 session 的后续查询。

    PG 在一条语句失败后会把事务置为 aborted，后续任何查询都报
    `current transaction is aborted` —— 表现为「别的取数也全空」，
    极易被误判成「本项目无数据」（memory 已记该级联假失败）。
    """

    def test_rollback_is_called_on_failure(self):
        import asyncio

        calls: list[str] = []

        class _Failing:
            async def execute(self, *a, **kw):  # noqa: ANN002, ANN003
                calls.append("execute")
                raise RuntimeError("boom")

            async def rollback(self):
                calls.append("rollback")

        got = asyncio.run(
            fetch_e1_bank_accounts(
                _Failing(),
                "00000000-0000-0000-0000-000000000000",
                2025,
                account_prefixes=["1002"],
            )
        )
        assert got == [], "取数失败必须 fail-open 返空"
        # 🔴 序列里会出现**两对** execute/rollback —— `get_active_filter` 自己也查库
        # 且自带一层 fail-open（实测调用序列 ['execute','rollback','execute','rollback']）。
        # 故判据只能是「最后一次 execute 之后紧跟 rollback」，不能写成整体相等。
        assert "rollback" in calls, (
            f"取数失败后未 rollback（实际调用序列 {calls}）—— "
            "aborted 事务会让后续查询全部失败并伪装成「本项目无数据」"
        )
        assert calls[-1] == "rollback", (
            f"最后一次失败后没有 rollback（序列 {calls}）"
        )

    def test_rollback_is_in_except_branch(self):
        """源码级：`rollback` 必须在 `except` 分支内（不是主流程末尾）。"""
        body = _fn_body("fetch_e1_bank_accounts")
        i_exc = body.find("except Exception")
        i_rb = body.find("await db.rollback()")
        assert 0 <= i_exc < i_rb, "rollback 必须在 except 分支内"


# ─── Property 5：勾稽如实暴露，不修正数据 ─────────────────────────────────────


class TestProperty5ReconcileIsHonest:
    def test_tie_reports_zero_diff(self):
        a = assign_accounts_to_slots([_row(closing=1000.0)], {"bank": ["1002"]})
        r = check_accounts_vs_leaves(a.by_slot, {"bank": 1000.0})
        assert r["bank"]["diff"] == 0.0
        assert r["bank"]["ok"] is True

    def test_mismatch_is_exposed_not_corrected(self):
        """🔴 不平时如实暴露差异，**不修正数据**（R1.5）。"""
        a = assign_accounts_to_slots([_row(closing=900.0)], {"bank": ["1002"]})
        r = check_accounts_vs_leaves(a.by_slot, {"bank": 1000.0})
        assert r["bank"]["account_sum"] == 900.0
        assert r["bank"]["leaf_sum"] == 1000.0
        assert r["bank"]["diff"] == -100.0
        assert r["bank"]["ok"] is False

    def test_negative_balance_is_not_absolutized(self):
        """银行存款期末可为负（实测 `a7fc75e5` = −297,771,168.89）→ 不得取绝对值。"""
        a = assign_accounts_to_slots(
            [_row(closing=-297771168.89)], {"bank": ["1002"]}
        )
        r = check_accounts_vs_leaves(a.by_slot, {"bank": -297771168.89})
        assert r["bank"]["account_sum"] == pytest.approx(-297771168.89, abs=0.005)
        assert r["bank"]["ok"] is True

    def test_slot_without_accounts_is_skipped(self):
        """两侧缺一侧时不产出条目（「不平」没有意义）。"""
        a = assign_accounts_to_slots([], {"bank": ["1002"]})
        assert check_accounts_vs_leaves(a.by_slot, {"bank": 1000.0}) == {}

    def test_slot_without_leaf_amount_is_skipped(self):
        a = assign_accounts_to_slots([_row()], {"bank": ["1002"]})
        assert check_accounts_vs_leaves(a.by_slot, {}) == {}

    def test_no_abs_on_reported_amounts(self):
        """🔴 判据收窄到「上报金额」—— `abs(diff) <= TOLERANCE` 是容差判定，合法。

        要禁的是 `abs(a.closing)` / `abs(acc_sum)` 这类**把上报金额翻正**的写法
        （会掩盖资金池/内部结算的负余额）。首版判据写成裸 `abs(` 会误伤容差判定
        —— 那正是「守卫判据必须是形态而非字符」这条铁律的又一实例。
        """
        body = _strip_comments(_src())
        for m in re.finditer(r"abs\s*\(([^)]*)\)", body):
            arg = m.group(1).strip()
            assert arg == "diff", (
                f"abs() 只允许作用于 diff（容差判定），实为 abs({arg}) —— "
                "上报金额被翻正会掩盖负余额异常"
            )


# ─── 载荷形态 ─────────────────────────────────────────────────────────────────


class TestAccountPrefillPayload:
    def test_payload_shape(self):
        a = assign_accounts_to_slots(
            [_row(closing=1000.0)], {"bank": ["1002"], "other": ["1012"]}
        )
        p = build_e1_account_prefill(a, {"bank": 1000.0})
        assert set(p) == {"accounts", "reconcile", "meta"}
        # 🔴 无数据的槽是 `[]` 而不是缺键（前端据此退回叶子口径）
        assert p["accounts"]["other"] == []
        assert p["accounts"]["unassigned"] == []
        assert p["meta"]["account_count"] == 1
        assert p["meta"]["source"] == SOURCE_PREFIX

    def test_empty_assignment_still_has_all_keys(self):
        """🔴 aux 无数据时载荷形态仍合法（不是缺键）—— R2.5 恒空形态合法。"""
        a = assign_accounts_to_slots([], {"bank": ["1002"], "digital": []})
        p = build_e1_account_prefill(a, {})
        assert p["accounts"] == {"bank": [], "digital": [], "unassigned": []}
        assert p["reconcile"] == {}
        assert p["meta"]["account_count"] == 0

    def test_row_carries_source_and_parsed_level(self):
        a = assign_accounts_to_slots([_row(parsed_level=2)], {"bank": ["1002"]})
        row = build_e1_account_prefill(a)["accounts"]["bank"][0]
        assert row["source"].startswith(SOURCE_PREFIX)
        assert row["parsed_level"] == 2
        assert set(row) >= {
            "account_code",
            "account_no",
            "bank_name",
            "currency",
            "opening",
            "closing",
            "slot",
            "source",
            "parsed_level",
        }

    def test_zero_balance_accounts_are_kept(self):
        """🔴 E1-10 完整性核对需要零余额账户（体外账户是舞弊主入口）→ 不过滤。"""
        a = assign_accounts_to_slots(
            [_row(account_no="ZERO", closing=0.0, opening=0.0)], {"bank": ["1002"]}
        )
        p = build_e1_account_prefill(a, {})
        assert [r["account_no"] for r in p["accounts"]["bank"]] == ["ZERO"]

    def test_parsed_level_distribution_is_reported(self):
        """`parsed_level` 分布是数据质量指标（level 3 占比高 → 该客户格式异常）。"""
        a = assign_accounts_to_slots(
            [
                _row(account_no="A", parsed_level=1),
                _row(account_no="B", parsed_level=3),
                _row(account_no="C", parsed_level=3),
            ],
            {"bank": ["1002"]},
        )
        assert build_e1_account_prefill(a)["meta"]["parsed_level_dist"] == {
            "1": 1,
            "3": 2,
        }

    def test_unassigned_is_surfaced_in_payload(self):
        """未归属账户必须出现在载荷里（供溯源面板告警）。"""
        a = assign_accounts_to_slots(
            [_row(account_code="9999", account_no="ORPHAN")], {"bank": ["1002"]}
        )
        p = build_e1_account_prefill(a)
        assert [r["account_no"] for r in p["accounts"]["unassigned"]] == ["ORPHAN"]
        assert p["meta"]["account_count"] == 1, "unassigned 也要计入总数"
