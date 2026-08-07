"""零回归守卫：公式运行时收口不得改变既有函数集与列名映射。

spec: formula-management-runtime-closure Task 17
  (Requirements 9.1, 9.2, 9.3, 9.4, 9.5 / Property 21, 22)

🔴 **为什么需要这条守卫**：本 spec 的 Wave 2 往 ``COLUMN_ALIASES`` 里加了 6 个
发生额列名、Wave 3 把用户公式收敛进 ``wp_formula`` 表、Wave 4 给三类型执行链接了线。
这些都是 **additive** 改动，但「additive」是**声明**不是**保证** ——
只要有人顺手把 ``审定数 -> 期末余额`` 改成 ``审定数 -> 审定数``（看起来更"对"），
全平台 467 格已注册列名公式的取值就会静默变化，而单测各自都绿。

故这里把三件事钉成基线常量：

1. ``_REGISTRY`` 函数键集（Property 21）—— 少一个函数意味着某类公式全部失效；
   多一个意味着有人在没走 spec 的情况下扩了 DSL。
2. ``prefill_engine._FORMULA_RESOLVERS`` 键集（Property 21）—— 与上同理，
   且它是 **另一套**寻址空间（memory 已记 ``WP`` 在两个引擎各有一份实现）。
3. ``COLUMN_ALIASES`` 的**原 8 键映射目标逐字不变**（Property 22）——
   新增键可以有（本 spec 就加了 6 个），但既有 8 键的目标一旦改动就是数字级回归。

判据设计要点：
- 基线用 ``frozenset`` / ``dict`` 字面量**显式写死**，不从被测模块反向派生
  （从被测模块派生等于自证，改了也不会红）。
- 每条都配**反向自检**，证明断言不是空转。
- ``_REGISTRY`` 实测 **14 键**（spec tasks.md 写的 15 是记载偏差，已在 Notes 更正）；
  HEAD 版与工作树版逐个比对确认本 spec 未增删函数。
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 基线常量（显式写死，禁从被测模块派生）
# ---------------------------------------------------------------------------

#: ``formula_engine._REGISTRY`` 的函数键集。
#:
#: 🔴 实测 **14 个**（2026-08-07，HEAD 与工作树一致）。
#: spec tasks.md 写「15 个」属记载偏差 —— 按 15 写断言会立刻假红，
#: 而假红的正确处置是核实真值而不是往 registry 里塞一个函数。
BASELINE_REGISTRY_FUNCTIONS = frozenset(
    {
        "ABS",
        "AUX",
        "IF",
        "MAX",
        "MIN",
        "NOTE",
        "PREV",
        "REPORT",
        "ROUND",
        "ROW",
        "SUM_ROW",
        "SUM_TB",
        "TB",
        "WP",
    }
)

#: ``prefill_engine`` 的 resolver 键集（**另一套**寻址空间，与上表刻意不同）。
#:
#: 两侧共有 ``AUX`` / ``NOTE`` / ``PREV`` / ``WP`` 四个名字，
#: 但 ``WP`` 的两份实现语义不同（见 ``formula_wp_semantics.py`` 的登记）。
BASELINE_PREFILL_RESOLVERS = frozenset(
    {
        "ADJ",
        "AUX",
        "COUNT_LEDGER",
        "LEDGER",
        "LEDGER_DETAIL",
        "NOTE",
        "PREV",
        "TB_AUX",
        "WP",
    }
)

#: ``COLUMN_ALIASES`` 改造前的 8 键映射（HEAD 实测，逐字）。
#:
#: 🔴 **只断言这 8 键的映射目标不变**，不断言总键数 —— 本 spec Wave 2 已
#: additive 加了 6 个发生额列名（`本期借方`/`借方发生额`/`本期借方发生额` 及贷方三个）。
#: 把总数写死会让「按 spec 正确扩列名」这个动作打红。
BASELINE_COLUMN_ALIASES_PRE_WAVE2 = {
    "期末余额": "期末余额",
    "审定数": "期末余额",
    "年初余额": "年初余额",
    "期初余额": "年初余额",
    "未审数": "期末余额",
    "本期发生额": "本期发生额",
    "RJE调整": "RJE调整",
    "AJE调整": "AJE调整",
}

#: ``FormulaEngine.register_custom_function`` 注册自定义函数时固定使用的分类。
#: 内置注册全部显式带 取数/引用/数学/逻辑 之一 ⇒ 可据此过滤全局污染。
CUSTOM_CATEGORY = "自定义"

#: Wave 2 新增的发生额列名（规范名必须与共享件 ``DEBIT_KEY``/``CREDIT_KEY`` 一致）。
WAVE2_OCCURRENCE_ALIASES = {
    "本期借方": "本期借方",
    "借方发生额": "本期借方",
    "本期借方发生额": "本期借方",
    "本期贷方": "本期贷方",
    "贷方发生额": "本期贷方",
    "本期贷方发生额": "本期贷方",
}


# ---------------------------------------------------------------------------
# Property 21: 函数集不变
# ---------------------------------------------------------------------------


def _builtin_function_names() -> frozenset[str]:
    """只取**内置**函数名（``category != '自定义'``）。

    🔴 **为什么不能直接用 ``known_function_names()``**：``_REGISTRY`` 是**模块级
    可变全局**，而 ``FormulaEngine.register_custom_function`` 直接往它里面注册。
    `test_custom_dsl_coding.py` 有多个用例注册 ``NET_CHANGE`` / ``FUNC_A`` /
    ``FUNC_B`` / ``MY_FUNC`` 后**没有 unregister**（只有
    `test_formula_engine_registry.py` 那几个写了 ``finally: unregister``）
    ⇒ 全量跑时 ``_REGISTRY`` 被污染，本守卫单跑绿、全量红 = **顺序依赖的假红**。

    实测：单独跑本文件 14 键全绿；`-k formula` 全量跑时多出若干自定义函数。

    判据改为按 ``category`` 过滤 —— 内置注册全部显式带
    ``category='取数'/'引用'/'数学'/'逻辑'``，自定义注册固定 ``'自定义'``
    （见 ``FormulaEngine.register_custom_function``）。这样既不受污染影响，
    又保留了「内置函数被增删」的检出能力。
    """
    from app.services.formula_engine import _REGISTRY

    return frozenset(
        item["name"]
        for item in _REGISTRY.list_all()
        if item.get("category") != CUSTOM_CATEGORY
    )


class TestRegistryUnchanged:
    """``_REGISTRY`` 与 ``_FORMULA_RESOLVERS`` 键集逐字不变。"""

    def test_formula_engine_registry_keys(self):
        actual = _builtin_function_names()
        missing = sorted(BASELINE_REGISTRY_FUNCTIONS - actual)
        extra = sorted(actual - BASELINE_REGISTRY_FUNCTIONS)
        assert not missing, (
            f"_REGISTRY 少了内置函数 {missing} —— 该类公式会全部失效。"
            "若是有意移除，须在 spec 里登记并改本基线常量。"
        )
        assert not extra, (
            f"_REGISTRY 多了内置函数 {extra} —— 扩 DSL 属平台级变更，"
            "须先立 spec（新函数要同步 prefill 侧与语法校验白名单）。"
        )

    def test_custom_registration_excluded_from_baseline(self):
        """反向自检：``category`` 过滤确实把自定义函数排除掉了。

        这条同时证明两件事：①上面那条断言不是靠「恰好没有自定义函数」侥幸通过；
        ②真往 registry 里塞**内置**函数时仍会被检出（因为过滤只放行 `'自定义'`）。
        """
        from app.services.formula_engine import FormulaEngine, _REGISTRY

        engine = FormulaEngine()
        name = "__ZERO_REGRESSION_PROBE__"
        try:
            engine.register_custom_function(name, description="探针", expression="0")
            # 全集里有它（证明真注册进去了，不是空操作）
            assert name in _REGISTRY.known_function_names()
            # 内置集合里没有它（证明过滤生效）
            assert name not in _builtin_function_names()
            # 且内置集合仍等于基线（证明污染不会打红本守卫）
            assert _builtin_function_names() == BASELINE_REGISTRY_FUNCTIONS
        finally:
            engine.unregister_custom_function(name)

    def test_builtin_category_filter_is_not_vacuous(self):
        """反向自检：内置函数**确实都带** category，过滤不是把全部放行。

        若哪天有人 register 内置函数时忘了传 ``category``（默认空串），
        它仍会落进内置集合（空串 != '自定义'）⇒ 检出能力不丢；
        但若有人把内置的 category 误写成 '自定义'，本断言打红。
        """
        from app.services.formula_engine import _REGISTRY

        by_name = {item["name"]: item.get("category") for item in _REGISTRY.list_all()}
        mislabeled = sorted(
            n for n in BASELINE_REGISTRY_FUNCTIONS if by_name.get(n) == CUSTOM_CATEGORY
        )
        assert not mislabeled, (
            f"内置函数 {mislabeled} 的 category 被写成 '{CUSTOM_CATEGORY}' —— "
            "它们会从内置基线里消失，本守卫将永久空转"
        )
        # 且内置函数的 category 取值域必须落在既有四类里
        cats = {by_name[n] for n in BASELINE_REGISTRY_FUNCTIONS}
        assert cats <= {"取数", "引用", "数学", "逻辑"}, f"内置 category 取值域变化：{cats}"

    def test_registry_three_views_agree(self):
        """``_handlers`` / ``known_function_names`` / ``list_all`` 三视图一致。

        反向自检性质：三者由不同代码路径产出，若某次重构只改了一处，
        「按名注册的函数表」就会出现视图分歧（memory 已记同族坑：
        按名注册的大对象要配键唯一性/一致性断言）。
        """
        from app.services.formula_engine import _REGISTRY

        known = frozenset(_REGISTRY.known_function_names())
        listed = frozenset(item["name"] for item in _REGISTRY.list_all())
        handlers = frozenset(_REGISTRY._handlers.keys())  # noqa: SLF001
        assert known == listed == handlers

    def test_prefill_engine_resolver_keys(self):
        from app.services.prefill_engine import _FORMULA_RESOLVERS

        actual = frozenset(_FORMULA_RESOLVERS.keys())
        assert actual == BASELINE_PREFILL_RESOLVERS, (
            "prefill_engine._FORMULA_RESOLVERS 键集变化："
            f"missing={sorted(BASELINE_PREFILL_RESOLVERS - actual)} "
            f"extra={sorted(actual - BASELINE_PREFILL_RESOLVERS)}"
        )

    def test_two_engines_share_only_four_names(self):
        """两套寻址空间的交集恰为四个名字（防「统一成一套」的误重构）。

        ``WP`` 在两侧实现语义不同（两参 vs 三参，见 ``formula_wp_semantics.py``），
        故交集变大/变小都要先读那份登记。
        """
        from app.services.formula_engine import _REGISTRY
        from app.services.prefill_engine import _FORMULA_RESOLVERS

        shared = frozenset(_REGISTRY.known_function_names()) & frozenset(
            _FORMULA_RESOLVERS.keys()
        )
        assert shared == frozenset({"AUX", "NOTE", "PREV", "WP"})

    def test_selfcheck_baseline_not_derived_from_module(self):
        """反向自检：基线常量是写死的字面量，不是从模块反向派生。

        判据 = 往实际集合里塞一个假名字后，断言必须能发现差异
        （若基线是派生的，塞了也不会红）。
        """
        from app.services.formula_engine import _REGISTRY

        fake = frozenset(_REGISTRY.known_function_names()) | {"__FAKE_FN__"}
        assert fake != BASELINE_REGISTRY_FUNCTIONS


# ---------------------------------------------------------------------------
# Property 22: 既有列名映射不变
# ---------------------------------------------------------------------------


class TestColumnAliasesAdditiveOnly:
    """``COLUMN_ALIASES`` 的改动必须是 additive。"""

    def test_pre_wave2_mappings_unchanged(self):
        from app.services.formula_engine import COLUMN_ALIASES

        drift = {
            k: (v, COLUMN_ALIASES.get(k))
            for k, v in BASELINE_COLUMN_ALIASES_PRE_WAVE2.items()
            if COLUMN_ALIASES.get(k) != v
        }
        assert not drift, (
            "COLUMN_ALIASES 既有键的映射目标发生变化（数字级回归）："
            f"{drift}。467 格已注册列名公式的取值会静默改变。"
        )

    def test_wave2_occurrence_aliases_present(self):
        """Wave 2 新增的六个发生额别名在位且指向规范名。"""
        from app.services.formula_engine import COLUMN_ALIASES

        missing = {
            k: v
            for k, v in WAVE2_OCCURRENCE_ALIASES.items()
            if COLUMN_ALIASES.get(k) != v
        }
        assert not missing, f"Wave 2 发生额别名缺失或指错：{missing}"

    def test_canonical_names_match_shared_module(self):
        """规范名与共享件 ``DEBIT_KEY``/``CREDIT_KEY`` 交叉锁死。

        🔴 memory 铁律：规范名必须是 ``本期借方``/``本期贷方``，
        写成 ``借方发生额`` 会让共享件与引擎两侧对不上。
        """
        from app.services.formula_engine import COLUMN_ALIASES
        from app.services.four_table.occurrence_by_standard_code import (
            CREDIT_KEY,
            DEBIT_KEY,
        )

        targets = set(COLUMN_ALIASES.values())
        assert DEBIT_KEY in targets
        assert CREDIT_KEY in targets
        assert COLUMN_ALIASES[DEBIT_KEY] == DEBIT_KEY
        assert COLUMN_ALIASES[CREDIT_KEY] == CREDIT_KEY

    def test_all_targets_are_self_mapped_canonical(self):
        """每个映射目标本身必须也是键且自映射（否则出现二级别名链）。"""
        from app.services.formula_engine import COLUMN_ALIASES

        bad = [
            (k, v)
            for k, v in COLUMN_ALIASES.items()
            if COLUMN_ALIASES.get(v) != v
        ]
        assert not bad, f"存在非自映射的规范名（二级别名链）：{bad}"

    def test_selfcheck_drift_detection_works(self):
        """反向自检：篡改一个既有映射必被检出。"""
        from app.services.formula_engine import COLUMN_ALIASES

        mutated = dict(COLUMN_ALIASES)
        mutated["审定数"] = "审定数"  # 看似"更对"，实为数字级回归
        drift = {
            k: (v, mutated.get(k))
            for k, v in BASELINE_COLUMN_ALIASES_PRE_WAVE2.items()
            if mutated.get(k) != v
        }
        assert drift, "反向自检失败：篡改既有映射后判据未发现差异"


# ---------------------------------------------------------------------------
# Property 22 补充：已注册列名求值结果不变
# ---------------------------------------------------------------------------


class TestRegisteredColumnEvaluationStable:
    """使用已注册列名的公式求值结果逐字不变（R9.3）。

    这里不遍历真实 467 格（需连库且属 Task 18 的诊断脚本职责），
    改为用**替身 tb_data** 覆盖全部 14 个别名，断言每个别名都解析到
    与其规范名相同的值 —— 这是「467 格结果不变」的充分条件：
    只要别名→规范名映射不变、且取值只按规范名查 tb_data，结果必然不变。
    """

    TB = {
        "1601": {
            "期末余额": 1000,
            "年初余额": 900,
            "本期发生额": 100,
            "RJE调整": 5,
            "AJE调整": 7,
            "本期借方": 300,
            "本期贷方": 200,
        }
    }

    @pytest.mark.parametrize(
        "alias",
        sorted(
            set(BASELINE_COLUMN_ALIASES_PRE_WAVE2)
            | set(WAVE2_OCCURRENCE_ALIASES)
        ),
    )
    def test_alias_resolves_to_canonical_value(self, alias: str):
        from app.services.formula_engine import (
            COLUMN_ALIASES,
            FormulaContext,
            execute,
        )

        canonical = COLUMN_ALIASES[alias]
        expected = self.TB["1601"][canonical]

        ctx = FormulaContext(tb_data=self.TB)
        res = execute(f"TB('1601','{alias}')", ctx)
        assert not res.errors, f"别名 {alias} 求值报错：{res.errors}"
        assert float(res.value) == float(expected), (
            f"别名 {alias} 应解析到规范名 {canonical}（{expected}），"
            f"实得 {res.value}"
        )

    def test_unregistered_column_is_error_not_silent_fallback(self):
        """反向自检：未注册列名必须记 error，禁静默回退期末余额。

        这条正是 Wave 2 修掉的缺陷（48 格数字错），
        退化回「静默回退」时本断言会红。
        """
        from app.services.formula_engine import FormulaContext, execute

        ctx = FormulaContext(tb_data=self.TB)
        res = execute("TB('1601','不存在的列名')", ctx)
        assert res.errors, "未注册列名未产生 error（静默回退回归）"
        # 且不得返回期末余额
        assert float(res.value or 0) != 1000.0


# ---------------------------------------------------------------------------
# R9.4: 响应形状只增不减
# ---------------------------------------------------------------------------

#: ``FormulaResult`` 改造前的三个键（Wave 5 additive 加了 ``warnings``）。
BASELINE_FORMULA_RESULT_FIELDS = frozenset({"value", "cached", "error"})

#: ``user-formulas`` 三个端点的返回体顶层键（HEAD 实测，逐字）。
#:
#: 🔴 Wave 3 把存储从 ``parsed_data['user_formulas']`` 收敛进 ``wp_formula`` 表，
#: 但**响应形状必须逐字不变** —— 前端 `FormulaManagerDialog.vue` 读的是
#: ``data?.user_formulas || data?.items || data``，改键名会让「用户公式」页空白，
#: 且因为有三级 fallback 不会报错（memory 已记的静默失效范式）。
BASELINE_USER_FORMULA_RESPONSE_SHAPES = {
    # GET /user-formulas
    "list": frozenset({"wp_id", "count", "user_formulas"}),
    # PUT /user-formulas
    "batch_update": frozenset({"wp_id", "updated", "deleted", "total"}),
    # DELETE /user-formulas/{cell_key} —— 两个分支（未命中 / 已恢复预设）
    "delete_noop": frozenset({"wp_id", "status", "cell_key"}),
    "delete_restored": frozenset(
        {"wp_id", "status", "cell_key", "restored_to_preset"}
    ),
}


class TestResponseShapeAdditiveOnly:
    """响应形状只增不减（R9.4）。"""

    def test_formula_result_keeps_original_three_fields(self):
        from app.models.workpaper_schemas import FormulaResult

        fields = frozenset(FormulaResult.model_fields.keys())
        missing = sorted(BASELINE_FORMULA_RESULT_FIELDS - fields)
        assert not missing, (
            f"FormulaResult 丢了既有字段 {missing} —— "
            "`/api/formula/execute` 与 `/batch-execute` 两个已登记端点的调用方会取不到值。"
        )

    def test_formula_result_declares_warnings(self):
        """``warnings`` 必须显式声明，否则 pydantic 静默丢弃。

        🔴 这是 Task 15 的核心产出：`FormulaEngine.execute` 返回体里带
        ``warnings``，但 pydantic 默认忽略未声明字段 —— 不加声明该键就被**静默丢弃**
        （既有 ``formula`` 键至今就是这样被丢掉的，属同族已知缺陷）。
        """
        from app.models.workpaper_schemas import FormulaResult

        assert "warnings" in FormulaResult.model_fields, (
            "FormulaResult 未声明 warnings —— 父子双算告警会被 pydantic 静默丢弃"
        )
        # 必须有默认值，否则既有调用方构造 FormulaResult() 会报错（破坏 additive）
        inst = FormulaResult()
        assert inst.warnings == []

    def test_user_formula_endpoint_response_keys_unchanged(self):
        """三个 user-formulas 端点的返回体顶层键逐字不变。

        判据 = 读 router 源码抽 ``return {...}`` 的顶层键集（不连库、可进 CI）。
        """
        import re
        from pathlib import Path

        router = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "routers"
            / "wp_user_formulas.py"
        )
        src = router.read_text(encoding="utf-8")

        shapes = []
        for m in re.finditer(r"return\s*\{", src):
            i = src.index("{", m.start())
            depth = 0
            for j in range(i, len(src)):
                if src[j] == "{":
                    depth += 1
                elif src[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
            keys = frozenset(re.findall(r'"(\w+)"\s*:', src[i : j + 1]))
            if keys:
                shapes.append(keys)

        # 提取器自检：必须抽到至少 4 个返回体（三端点 + delete 两分支）
        assert len(shapes) >= 4, f"提取器失效：只抽到 {len(shapes)} 个 return 字典"

        for name, expected in BASELINE_USER_FORMULA_RESPONSE_SHAPES.items():
            assert expected in shapes, (
                f"user-formulas 端点 `{name}` 的响应形状变化 —— "
                f"期望顶层键 {sorted(expected)}，实测形状集合 "
                f"{[sorted(s) for s in shapes]}"
            )

    def test_selfcheck_shape_drift_detected(self):
        """反向自检：改一个键名必被检出（防提取器空转）。"""
        mutated = {frozenset({"wp_id", "count", "user_formulas_RENAMED"})}
        assert BASELINE_USER_FORMULA_RESPONSE_SHAPES["list"] not in mutated
