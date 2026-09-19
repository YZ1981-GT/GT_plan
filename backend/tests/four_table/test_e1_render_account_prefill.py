"""E1 render 接账户级取数 + 扩明细槽 的守卫（Task 5）。

**Validates: Requirements 1.6, 1.7, 2.1, 2.2, 2.5, 11.6**

Property 9（characterization 零回归）、Property 10（found=False 返空不占位）。

🔴 本文件的核心是**零回归支点**：扩槽 + 新增 `account_prefill` 键都是**加法式**改动，
既有三槽（cash/bank/other）的明细行字段与顺序必须逐字节不变 —— 前端 24 个子 Tab
经宿主种子化消费这些键，字段一改就静默丢数据（`html_data` 在 TS 里是 `any`，
`get_diagnostics` / vitest / Vite transform 四层全绿）。

spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/ (Task 5)
"""

from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routers.wp_render_strategies import _e1_monetary_fund as mod
from app.routers.wp_render_strategies._e1_monetary_fund import (
    _ACCOUNT_SLOT_KEYS,
    _DETAIL_SLOT_KEYS,
    _empty_account_prefill,
    build_e1_account_list,
    build_e1_adjudication_prefill,
    build_e1_detail_rows,
    build_e1_tb_values,
)
from app.services.four_table import LeafRow
from app.services.four_table.e_cycle_specs import (
    E1_SLOT_BANK,
    E1_SLOT_CASH,
    E1_SLOT_DIGITAL,
    E1_SLOT_FINANCE_CO,
    E1_SLOT_OTHER,
)

MODULE_PATH = Path(inspect.getsourcefile(mod))  # type: ignore[arg-type]


def _src() -> str:
    return MODULE_PATH.read_text(encoding="utf-8")


def _strip(src: str) -> str:
    """剥 docstring 与 `#` 注释（本模块注释里会写反例，不剥会被数成真实调用）。"""
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    return re.sub(r"(?m)#.*$", "", out)


def _fn_body(name: str) -> str:
    """截某个顶层函数体。

    🔴 必须先用**圆括号配对**跳过参数列表再按缩进截 —— 多行签名的 `) -> dict:`
    那行缩进为 0，按「首个缩进 ≤ def 缩进的行即结束」会在签名处提前中断，
    截出来只有签名，`assert 'xxx' in body` 恒假红（memory 已记该坑）。
    """
    src = _src()
    m = re.search(rf"(?m)^(async\s+)?def\s+{re.escape(name)}\s*\(", src)
    assert m, f"未找到 def {name}（锚点漂移）"
    i = src.index("(", m.start())
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
    lines = src[j:].splitlines()
    out: list[str] = []
    for ln in lines[1:]:
        if ln.strip() and not ln.startswith((" ", "\t")):
            break
        out.append(ln)
    return "\n".join(out)


def _leaf(code: str, name: str, *, o=0.0, d=0.0, c=0.0, e=0.0) -> LeafRow:
    return LeafRow(
        account_code=code,
        account_name=name,
        opening=o,
        debit=d,
        credit=c,
        closing=e,
    )


class _Slot:
    def __init__(self, codes, found=True):
        self.codes = list(codes)
        self.found = found


class _Accounts:
    def __init__(self, slots):
        self.slots = slots


# ─── 反向自检 ─────────────────────────────────────────────────────────────────


class TestJudgementInfrastructure:
    def test_module_source_readable(self):
        src = _src()
        assert len(src) > 5000, "模块源码过短（路径漂移？后续源码级断言会空转）"
        assert "async def render" in src

    def test_strip_comments_is_not_a_noop(self):
        raw = _src()
        assert len(_strip(raw)) < len(raw), "剥注释无效果（判据会把说明文字数成调用）"

    def test_fn_body_skips_multiline_signature(self):
        """反向自检：多行签名的函数体必须真截到语句，不能只有签名。"""
        body = _fn_body("_build_account_prefill")
        assert "return" in body, "截函数体失效（命中了参数列表或类型注解）"
        assert len(body.splitlines()) > 5


# ─── Property 11.6 / 2.1：扩槽是加法式 ────────────────────────────────────────


class TestSlotKeysExtendedAdditively:
    def test_detail_slot_keys_declaration_lists_all_five_in_source(self):
        """🔴 源码级：`_DETAIL_SLOT_KEYS` 声明块必须列出五个槽常量。

        变异检验 M1 首轮 GREEN —— 因为其余断言读的是 import 进来的运行时值，
        而变异改的是源码文本；两者在同一进程内不同步。故这里直接钉源码形态。
        """
        src = _strip(_src())
        m = re.search(
            r"_DETAIL_SLOT_KEYS\s*:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\((.*?)\)",
            src,
            re.S,
        )
        assert m, "未找到 _DETAIL_SLOT_KEYS 声明（锚点漂移）"
        body = m.group(1)
        for name in (
            "E1_SLOT_CASH",
            "E1_SLOT_BANK",
            "E1_SLOT_OTHER",
            "E1_SLOT_FINANCE_CO",
            "E1_SLOT_DIGITAL",
        ):
            assert name in body, (
                f"_DETAIL_SLOT_KEYS 声明缺 {name} —— "
                "该槽的明细表刷新取数会恒空（R2.1）"
            )

    def test_detail_slot_keys_has_five_slots(self):
        """R2.1：`_DETAIL_SLOT_KEYS` 扩至含 digital 与 finance_co。"""
        assert _DETAIL_SLOT_KEYS == (
            E1_SLOT_CASH,
            E1_SLOT_BANK,
            E1_SLOT_OTHER,
            E1_SLOT_FINANCE_CO,
            E1_SLOT_DIGITAL,
        )

    def test_existing_three_slots_keep_leading_order(self):
        """🔴 R11.6 零回归支点：既有三槽必须仍在**最前**且顺序不变。

        前端既有种子键按这三个键读，插到中间会让 `meta.*_count` 与行序漂移。
        """
        assert _DETAIL_SLOT_KEYS[:3] == (E1_SLOT_CASH, E1_SLOT_BANK, E1_SLOT_OTHER)

    def test_account_slot_keys_excludes_cash_and_digital(self):
        """账户级取数只对「有银行账户维度」的槽有意义。

        `cash`（库存现金）与 `digital`（数字货币）在 `tb_aux_balance` 的
        `银行账户` 维度下**不该有账户** —— 把它们纳入会让 unassigned 出现
        本不该存在的噪声。
        """
        assert _ACCOUNT_SLOT_KEYS == (E1_SLOT_BANK, E1_SLOT_OTHER, E1_SLOT_FINANCE_CO)
        assert E1_SLOT_CASH not in _ACCOUNT_SLOT_KEYS
        assert E1_SLOT_DIGITAL not in _ACCOUNT_SLOT_KEYS


# ─── Property 9：characterization 零回归 ──────────────────────────────────────


class TestProperty9DetailRowsCharacterization:
    """既有三槽的明细行**字段名与顺序**逐字冻结。

    这是「扩槽不影响既有槽」的结构性证明 —— 不是靠回归测试碰运气。
    """

    #: 前端契约字段序列（改造前实测值，只许因前端契约变更而改）
    FIELDS = (
        "code",
        "name",
        "currency",
        "opening",
        "increase",
        "decrease",
        "ending",
        "source",
        "formula",
        "formulaOpening",
    )

    def test_field_names_and_order_frozen(self):
        rows = build_e1_detail_rows(
            {E1_SLOT_BANK: [_leaf("1002.01", "招行基本户", o=1.0, d=2.0, c=3.0, e=4.0)]},
            {"1002.01": "CNY"},
        )
        assert tuple(rows[E1_SLOT_BANK][0].keys()) == self.FIELDS

    def test_field_values_are_mapped_as_before(self):
        rows = build_e1_detail_rows(
            {E1_SLOT_BANK: [_leaf("1002.01", "招行", o=10.0, d=20.0, c=30.0, e=40.0)]},
            {"1002.01": "USD"},
        )
        r = rows[E1_SLOT_BANK][0]
        assert r["code"] == "1002.01"
        assert r["name"] == "招行"
        assert r["currency"] == "USD"
        assert r["opening"] == 10.0
        assert r["increase"] == 20.0, "本期增加 = 借方发生额（资产/借方科目）"
        assert r["decrease"] == 30.0, "本期减少 = 贷方发生额"
        assert r["ending"] == 40.0
        assert r["source"] == "tb_balance:1002.01 招行"
        assert r["formula"] == "TB('1002.01','期末余额')"
        assert r["formulaOpening"] == "TB('1002.01','期初余额')"

    def test_all_zero_rows_are_still_filtered(self):
        """全零过滤行为不变（既有语义）。"""
        rows = build_e1_detail_rows(
            {E1_SLOT_BANK: [_leaf("1002.01", "空壳户")]}, {}
        )
        assert rows[E1_SLOT_BANK] == []

    def test_new_slots_use_identical_field_set(self):
        """R2.1：两个新槽的明细行字段与既有三槽**逐字同构**。"""
        rows = build_e1_detail_rows(
            {
                E1_SLOT_FINANCE_CO: [_leaf("1012.05", "存放财务公司", e=100.0)],
                E1_SLOT_DIGITAL: [_leaf("1002.99", "数字人民币", e=50.0)],
            },
            {},
        )
        for slot in (E1_SLOT_FINANCE_CO, E1_SLOT_DIGITAL):
            assert tuple(rows[slot][0].keys()) == self.FIELDS

    def test_all_five_slots_always_present_as_keys(self):
        """空输入时五槽都要有键（前端按键读，缺键与空数组语义不同）。"""
        rows = build_e1_detail_rows({}, {})
        assert set(rows) == set(_DETAIL_SLOT_KEYS)
        assert all(v == [] for v in rows.values())

    def test_account_list_still_only_from_bank_slot(self):
        """R1.7 / 零回归：E1-10 账户清单仍只取 bank 槽，且**保留零余额账户**。"""
        lst = build_e1_account_list(
            {
                E1_SLOT_BANK: [
                    _leaf("1002.01", "有余额", e=100.0),
                    _leaf("1002.02", "零余额户"),
                ],
                E1_SLOT_FINANCE_CO: [_leaf("1012.05", "财务公司", e=9.0)],
            },
            {},
        )
        assert [r["code"] for r in lst] == ["1002.01", "1002.02"], (
            "账户清单不得纳入 finance_co 槽（那是另一张明细表），"
            "且零余额账户必须保留（完整性核对红线）"
        )
        assert lst[1]["isZeroBalance"] is True


# ─── Property 10：found=False 返空不占位 ──────────────────────────────────────


class TestProperty10NotFoundReturnsEmpty:
    def test_detail_rows_empty_for_missing_slot(self):
        """槽无科目 → 明细返 `[]`，**不产生零值占位行**（R2.2）。"""
        rows = build_e1_detail_rows({E1_SLOT_DIGITAL: []}, {})
        assert rows[E1_SLOT_DIGITAL] == []

    def test_adjudication_prefill_marks_found_false(self):
        """R2.2：`found=False` 让前端显示「本项目无此科目」而非 0。"""
        acc = _Accounts(
            {
                E1_SLOT_BANK: _Slot(["1002"], found=True),
                E1_SLOT_DIGITAL: _Slot([], found=False),
            }
        )
        out = build_e1_adjudication_prefill(
            {E1_SLOT_BANK: [_leaf("1002.01", "招行", e=100.0)], E1_SLOT_DIGITAL: []},
            acc,
        )
        assert out[E1_SLOT_BANK]["found"] is True
        assert out[E1_SLOT_DIGITAL]["found"] is False
        assert out[E1_SLOT_DIGITAL]["opening"] == 0
        assert out[E1_SLOT_DIGITAL]["accountCodes"] == []

    def test_new_slots_zero_is_legal_payload_shape(self):
        """R2.5：全库 8 项目这两槽 found=False 是数据事实 —— 载荷形态仍合法。"""
        acc = _Accounts(
            {
                E1_SLOT_FINANCE_CO: _Slot([], found=False),
                E1_SLOT_DIGITAL: _Slot([], found=False),
            }
        )
        out = build_e1_adjudication_prefill({}, acc)
        for slot in (E1_SLOT_FINANCE_CO, E1_SLOT_DIGITAL):
            assert set(out[slot]) == {
                "opening",
                "closing",
                "accountCode",
                "accountCodes",
                "found",
            }
            assert out[slot]["found"] is False

    def test_tb_values_include_new_slots(self):
        """新槽也要产出 `{slot}_opening` / `{slot}_closing`（供披露主表预填）。"""
        out = build_e1_tb_values(
            {
                E1_SLOT_FINANCE_CO: [_leaf("1012.05", "财务公司", o=1.0, e=2.0)],
                E1_SLOT_DIGITAL: [],
            }
        )
        assert out["finance_co_opening"] == 1.0
        assert out["finance_co_closing"] == 2.0
        assert out["digital_opening"] == 0.0
        assert out["digital_closing"] == 0.0


# ─── R1.6：account_prefill 空态形态合法 ───────────────────────────────────────


class TestEmptyAccountPrefillShape:
    def test_empty_payload_has_all_keys(self):
        """🔴 aux 无数据时各槽为 `[]`（**不是缺键**）—— 前端据此退回叶子口径。"""
        p = _empty_account_prefill()
        assert set(p) == {"accounts", "reconcile", "meta"}
        assert set(p["accounts"]) == set(_ACCOUNT_SLOT_KEYS) | {"unassigned"}
        assert all(v == [] for v in p["accounts"].values())
        assert p["reconcile"] == {}
        assert p["meta"]["account_count"] == 0

    def test_empty_payload_is_not_shared_mutable(self):
        """两次调用必须返回**独立**对象（返回模块级常量会被调用方就地改坏）。"""
        a = _empty_account_prefill()
        b = _empty_account_prefill()
        a["accounts"]["bank"].append({"x": 1})
        assert b["accounts"]["bank"] == [], "空载荷被共享 —— 一处改动污染全局"


# ─── 接线：render 输出键 + await 正确性 ───────────────────────────────────────


class TestRenderWiring:
    def test_render_returns_account_prefill_key(self):
        """🔴 render 返回 dict 必须含 `account_prefill` —— 否则前端拿不到 = dead output。

        「后端算了但没下发」是本平台反复出现的缺陷形态（H1 曾因两个同名键静默丢失
        导致溯源面板永不渲染）。

        判据落在**整份源码的 return 语句**上而不是 `_fn_body("render")` —— 后者按缩进
        截函数体，而 `render` 的 return dict 是多行字面量，变异检验 M2 首轮 GREEN
        就是因为截取范围没覆盖到它。
        """
        src = _strip(_src())
        # render 的返回字面量必须显式带该键（`extraction.get(...)` 那一处）
        assert re.search(
            r'"account_prefill"\s*:\s*extraction\.get\(\s*"account_prefill"\s*\)', src
        ), "render 返回 dict 缺 account_prefill 键 —— 账户级取数成了 dead output"

    def test_render_return_dict_key_set_is_frozen(self):
        """render 返回键集冻结（新增/删键都要显式改这里，防静默漂移）。"""
        src = _strip(_src())
        i = src.rfind("return {")
        assert i > 0, "未找到 render 的返回字面量（锚点漂移）"
        tail = src[i : src.find("\n    }", i) + 6]
        got = set(re.findall(r'"([a-z_]+)"\s*:', tail))
        assert got == {
            "sheet_name",
            "project_context",
            "responses_snapshot",
            "four_table_prefill",
            "account_prefill",
            "adjudication_prefill",
            "restricted_prefill",
            "tb_values",
        }, f"render 返回键集漂移：{sorted(got)}"

    def test_render_fallback_skeleton_has_account_prefill(self):
        """fail-open 骨架也要有该键（取数失败时前端仍拿到合法形态）。"""
        body = _fn_body("render")
        i_skel = body.find("extraction: dict = {")
        assert i_skel >= 0, "未找到 extraction 骨架（锚点漂移）"
        i_try = body.find("_build_four_table_extraction")
        skel = body[i_skel:i_try if i_try > i_skel else len(body)]
        assert "_empty_account_prefill()" in skel, (
            "fail-open 骨架缺 account_prefill —— 取数失败时前端读到 undefined"
        )

    def test_extraction_returns_account_prefill(self):
        body = _fn_body("_build_four_table_extraction")
        assert '"account_prefill"' in body
        assert "_build_account_prefill(" in body

    def test_get_active_filter_is_awaited_everywhere(self):
        """🔴 Property 39：`get_active_filter` 是 async，漏 await 会被 fail-open 吞掉。"""
        body = _strip(_src())
        calls = len(re.findall(r"get_active_filter\s*\(", body))
        awaited = len(re.findall(r"await\s+get_active_filter\s*\(", body))
        assert calls > 0, "扫不到调用（正则失效）"
        assert calls == awaited, f"{calls - awaited} 处漏 await"

    def test_fetch_e1_bank_accounts_is_awaited(self):
        body = _strip(_src())
        calls = len(re.findall(r"fetch_e1_bank_accounts\s*\(", body))
        awaited = len(re.findall(r"await\s+fetch_e1_bank_accounts\s*\(", body))
        assert calls > 0, "扫不到调用（正则失效）"
        assert calls == awaited, "漏 await 会让账户清单恒空且与「无数据」不可区分"

    def test_account_prefill_is_fail_open(self):
        """账户级取数失败不得阻断 render（既有 fail-open 语义）。"""
        body = _fn_body("_build_account_prefill")
        assert "except Exception" in body
        assert "_empty_account_prefill()" in body, "异常路径必须返回合法空态"

    def test_no_slot_codes_returns_legal_empty_shape_not_bare_dict(self):
        """🔴 真调 `_build_account_prefill`：槽全无码时必须返**形态合法**的空载荷。

        变异检验 M5 首轮 GREEN —— 既有断言只验 `_empty_account_prefill()` 本身，
        没验「早退路径返的就是它」。返 `{}` 会让前端 `normalizeAccountPrefill`
        拿不到 `accounts` 键 → 各槽渲染成「无此科目」的误导态（而真相是「未取数」）。
        """
        import asyncio

        from app.routers.wp_render_strategies._e1_monetary_fund import (
            _ACCOUNT_SLOT_KEYS,
            _build_account_prefill,
        )

        class _NoDb:
            async def execute(self, *a, **kw):  # noqa: ANN002, ANN003
                raise AssertionError("槽无码时不应查库")

            async def rollback(self):
                pass

        ctx = SimpleNamespace(
            db=_NoDb(), project_id="00000000-0000-0000-0000-000000000000"
        )
        # 全部槽都没有码（本项目科目表无货币资金科目）
        accounts = SimpleNamespace(
            slots={k: SimpleNamespace(codes=[], found=False) for k in _ACCOUNT_SLOT_KEYS}
        )
        got = asyncio.run(_build_account_prefill(ctx, 2025, accounts, {}))

        assert isinstance(got, dict), "必须返 dict"
        assert set(got) >= {"accounts", "reconcile", "meta"}, (
            f"空态载荷形态不合法：{sorted(got)} —— 前端会退化成误导态"
        )
        for slot_key in _ACCOUNT_SLOT_KEYS:
            assert got["accounts"].get(slot_key) == [], (
                f"空态下 accounts[{slot_key}] 应为 []（不是缺键）"
            )
        assert got["accounts"].get("unassigned") == []

    def test_reconcile_baseline_is_leaf_closing_not_parent(self):
        """🔴 勾稽基准必须是**叶子期末合计**，与 `build_e1_tb_values` 同口径。

        变异检验 M8 首轮 GREEN = 该口径零覆盖。改用父额会让「叶子和 == 父额」
        本就成立的项目看不出差异，而父子双算的项目反被判成「平」（掩盖数据问题）。
        """
        body = _fn_body("_build_account_prefill")
        assert "r.closing for r in slot_leaves" in body, (
            "勾稽基准未取叶子期末合计（口径漂移）"
        )
        assert "parent" not in body.lower(), (
            "出现 parent —— 勾稽基准不得用父科目额（见 build_e1_tb_values 口径）"
        )
        # 行为级：叶子合计 1000 vs 账户合计 900 必须报 diff=-100 且 ok=False
        import asyncio

        from app.routers.wp_render_strategies._e1_monetary_fund import (
            _build_account_prefill,
        )
        from app.services.four_table.e1_bank_accounts import BankAccountRow

        rows = [
            BankAccountRow(
                account_code="1002",
                account_no="A",
                bank_name="工商银行",
                currency="CNY",
                opening=0.0,
                debit=0.0,
                credit=0.0,
                closing=900.0,
            )
        ]

        class _Db:
            async def execute(self, *a, **kw):  # noqa: ANN002, ANN003
                raise RuntimeError("unused")

            async def rollback(self):
                pass

        ctx = SimpleNamespace(
            db=_Db(), project_id="00000000-0000-0000-0000-000000000000"
        )
        accounts = SimpleNamespace(
            slots={"bank": SimpleNamespace(codes=["1002"], found=True)}
        )
        leaf = SimpleNamespace(closing=1000.0)

        import app.routers.wp_render_strategies._e1_monetary_fund as mod

        orig = mod.fetch_e1_bank_accounts

        async def _fake(*a, **kw):  # noqa: ANN002, ANN003
            return rows

        mod.fetch_e1_bank_accounts = _fake
        try:
            got = asyncio.run(
                _build_account_prefill(ctx, 2025, accounts, {"bank": [leaf]})
            )
        finally:
            mod.fetch_e1_bank_accounts = orig

        rec = got.get("reconcile", {}).get("bank")
        assert rec, f"未产出 bank 槽勾稽：{got.get('reconcile')}"
        assert rec["leaf_sum"] == pytest.approx(1000.0, abs=0.005), (
            f"叶子基准取错：{rec}"
        )
        assert rec["account_sum"] == pytest.approx(900.0, abs=0.005)
        assert rec["diff"] == pytest.approx(-100.0, abs=0.005)
        assert rec["ok"] is False

    def test_account_prefill_only_uses_account_slots(self):
        """账户级取数只按 `_ACCOUNT_SLOT_KEYS` 的槽取前缀（不把 cash 也拉进来）。"""
        body = _fn_body("_build_account_prefill")
        assert "_ACCOUNT_SLOT_KEYS" in body


# ─── 前端消费方交叉锁死 ───────────────────────────────────────────────────────


class TestFrontendContractCrossLock:
    """render 新增的键必须与前端归一层的键名逐字一致。

    Task 7 建 `e1BankAccountPrefill.ts` 后本断言转为强校验；当前只做「键名已声明」
    的存在性检查，避免 Wave 2/3 之间出现「后端发 A、前端读 B」的静默断链。
    """

    FRONTEND = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "audit-platform"
        / "frontend"
        / "src"
        / "components"
        / "workpaper"
        / "composables"
    )

    def test_payload_key_names_are_snake_case_as_backend_convention(self):
        """载荷键沿用后端 snake_case（前端 `props.htmlData?.account_prefill`）。"""
        p = _empty_account_prefill()
        for k in ("accounts", "reconcile", "meta"):
            assert k in p
        for k in p["meta"]:
            assert k == k.lower(), f"meta 键 {k!r} 应为 snake_case"

    @pytest.mark.skipif(
        not (
            Path(__file__).resolve().parent.parent.parent.parent
            / "audit-platform"
            / "frontend"
            / "src"
            / "components"
            / "workpaper"
            / "composables"
            / "e1BankAccountPrefill.ts"
        ).exists(),
        reason="Task 7 的前端归一层尚未创建（Wave 3）",
    )
    def test_frontend_normalizer_reads_same_keys(self):
        src = (self.FRONTEND / "e1BankAccountPrefill.ts").read_text(encoding="utf-8")
        for key in ("accounts", "reconcile", "meta", "unassigned"):
            assert key in src, f"前端归一层未读 {key!r} 键"
        for slot in _ACCOUNT_SLOT_KEYS:
            assert slot in src, f"前端归一层未处理 {slot!r} 槽"
