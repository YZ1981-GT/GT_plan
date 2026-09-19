"""公式列名别名覆盖守卫（平台级）。

**要防的缺陷**

``formula_engine.COLUMN_ALIASES`` 只登记了 8 个列名，而
``prefill_formula_mapping.json`` 里大量使用 ``本期借方`` / ``本期贷方`` /
``借方发生额`` / ``贷方发生额``。这四个列名**未注册**，而两条求值路径都写着::

    val = account_data.get(resolved_col, account_data.get("期末余额", Decimal("0")))

即取不到该列时**静默回退期末余额** → 公式算出来的是「期末余额」而不是「本期发生额」。
这是「数字错」不是「取不到」，比恒空更隐蔽：界面有值、无任何报错、
`get_diagnostics` 与既有单测全绿。

**实证基线（2026-08-06）**

- 未注册列名 4 个，涉及 **48 个预设格**：
  ``本期借方`` 19 / ``本期贷方`` 17 / ``贷方发生额`` 7 / ``借方发生额`` 5
- 其中 H 类 **16 格**：H1 明细表 4 / H2 明细表 2 / H3 明细表(公允价值) 2 /
  H8 明细表 2 / H9 两张明细表 4 / H10 明细表 2
- ``tb_data`` 的两个构造点都不产出发生额键：
  ``wp_template_files._get_tb_data_for_prefill`` 注释明写「发生额明细在
  tb_balance，此处不取」；``adjudication_writeback._build_context`` 只有 6 键
- 静默回退形态在 ``formula_engine.py`` 出现 **2 处**（``_handle_tb`` = AST 路径 /
  ``_execute_regex`` = 降级路径）→ Task 4 必须同时改，只改一处另一条路径仍错

**Wave 1 期望：本文件现在必须打红**（Task 4 修完转绿）。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 2.1~2.5 / Property 5~7
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_ENGINE = _BACKEND / "app" / "services" / "formula_engine.py"
_PRESETS = _BACKEND / "data" / "prefill_formula_mapping.json"

#: 未注册列名 → 语义（Task 4 应把它们加进 COLUMN_ALIASES）
EXPECTED_MISSING_BEFORE_FIX: dict[str, str] = {
    "本期借方": "借方发生额",
    "本期贷方": "贷方发生额",
    "借方发生额": "借方发生额",
    "贷方发生额": "贷方发生额",
}

#: 静默回退形态（Task 4 应改成三态：注册但无数据 → WARNING + 0，不回退期末余额）
_SILENT_FALLBACK = 'account_data.get(resolved_col, account_data.get("期末余额"'

#: 该形态当前出现的路径数（两条求值路径各一处）
_SILENT_FALLBACK_PATHS = 2


# ─────────────────────────── 读取真源 ───────────────────────────


def _strip_comments(src: str) -> str:
    """剥掉 # 注释与三引号串（防守卫注释里的反例被数成真实代码）。"""
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    return re.sub(r"(?m)#.*$", "", src)


def _column_aliases() -> dict[str, str]:
    """从源码 AST 抽 COLUMN_ALIASES（不 import，避免副作用）。"""
    tree = ast.parse(_ENGINE.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = (
            [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        )
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "COLUMN_ALIASES":
                return ast.literal_eval(node.value)
    raise AssertionError("未在 formula_engine.py 找到 COLUMN_ALIASES")


def _preset_columns() -> dict[str, list[tuple[str, str, str, str]]]:
    """列名 → [(wp_code, sheet, cell_ref, formula)]。

    只扫 ``TB(...)`` / ``SUM_TB(...)`` 的**第二实参**（列名位）。
    """
    raw = json.loads(_PRESETS.read_text(encoding="utf-8"))
    out: dict[str, list[tuple[str, str, str, str]]] = {}
    pat = re.compile(r"\b(?:SUM_)?TB\(\s*'[^']*'\s*,\s*'([^']*)'")
    for block in raw.get("mappings", []):
        wp = block.get("wp_code") or ""
        sheet = block.get("sheet") or ""
        for cell in block.get("cells", []) or []:
            formula = cell.get("formula") or ""
            ref = cell.get("cell_ref") or ""
            for col in pat.findall(formula):
                out.setdefault(col, []).append((wp, sheet, ref, formula))
    return out


ALIASES = _column_aliases()
PRESET_COLS = _preset_columns()


# ─────────────────────────── Property 5：解析器自检 ───────────────────────────


class TestExtractionSelfCheck:
    """抽取器失效时必须打红，而不是断言空转。"""

    def test_aliases_nonempty(self):
        assert len(ALIASES) >= 8, f"COLUMN_ALIASES 只抽到 {len(ALIASES)} 条，抽取器可能失效"
        # 锚点：这几个是既有 8 键里的，抽不到说明解析坏了
        for k in ("期末余额", "审定数", "本期发生额", "AJE调整"):
            assert k in ALIASES, f"锚点键 {k} 缺失，抽取器失效"

    def test_preset_columns_nonempty(self):
        assert len(PRESET_COLS) >= 3, f"只抽到 {len(PRESET_COLS)} 个列名，正则可能失效"
        assert "期末余额" in PRESET_COLS, "锚点列名『期末余额』未命中，正则失效"
        total = sum(len(v) for v in PRESET_COLS.values())
        assert total >= 400, f"预设列名引用只抽到 {total} 处，抽取器可能失效"

    def test_sum_tb_is_also_scanned(self):
        """`SUM_TB` 与 `TB` 都要扫到 —— 只扫 `\\bTB` 会漏 `SUM_TB`（下划线是词字符）。"""
        pat = re.compile(r"\b(?:SUM_)?TB\(\s*'[^']*'\s*,\s*'([^']*)'")
        assert pat.findall("=SUM_TB('1601~1604','期末余额')") == ["期末余额"]
        assert pat.findall("=TB('1601','期初余额')") == ["期初余额"]
        # 反向自检：只写 \bTB 会漏 SUM_TB
        naive = re.compile(r"\bTB\(\s*'[^']*'\s*,\s*'([^']*)'")
        assert naive.findall("=SUM_TB('1601~1604','期末余额')") == [], (
            "若此断言失败说明 \\bTB 也能命中 SUM_TB，本文件的解释注释需更正"
        )


# ─────────────────────── Property 6：列名必须全部注册 ───────────────────────


class TestEveryPresetColumnIsRegistered:
    def test_all_columns_registered(self):
        """预设里出现的每个列名都必须在 COLUMN_ALIASES 里。

        🔴 Wave 1 预期红：4 个发生额列名未注册，48 个预设格取到的是期末余额。
        """
        missing: dict[str, int] = {
            col: len(refs) for col, refs in PRESET_COLS.items() if col not in ALIASES
        }
        if missing:
            detail = "; ".join(f"{c}×{n}" for c, n in sorted(missing.items(), key=lambda x: -x[1]))
            total = sum(missing.values())
            pytest.fail(
                f"【Wave 1 预期红】{len(missing)} 个列名未注册、共 {total} 个预设格"
                f"会静默回退期末余额：{detail}"
            )

    @pytest.mark.parametrize("col", sorted(EXPECTED_MISSING_BEFORE_FIX))
    def test_expected_missing_columns_are_really_used(self, col: str):
        """登记的 4 个缺口列名必须真的被预设使用 —— 否则这份清单已过期。"""
        assert col in PRESET_COLS, (
            f"{col} 已不再被任何预设使用，请从 EXPECTED_MISSING_BEFORE_FIX 移除"
        )

    def test_h_cycle_affected_cells_are_all_fixed(self):
        """H 类曾受影响的 16 个格现在必须全部有注册列名。

        改造前基线（2026-08-06）：H1 明细 4 / H2 明细 2 / H3 明细(公允价值) 2 /
        H8 明细 2 / H9 两张明细 4 / H10 明细 2 = **16 格**，六个循环全中招。
        Task 4 注册四个发生额列名后，这 16 格必须一个不剩。
        """
        h_cells = [
            (wp, sheet, ref, col)
            for col, refs in PRESET_COLS.items()
            if col not in ALIASES
            for (wp, sheet, ref, _f) in refs
            if re.fullmatch(r"H\d+", wp or "")
        ]
        assert h_cells == [], (
            f"H 类仍有 {len(h_cells)} 个格用未注册列名：{sorted(h_cells)}"
        )

    def test_occurrence_columns_still_used_by_h_cycle(self):
        """反向自检：那 16 格确实在用发生额列名（防上一条变成空转）。

        若哪天预设改写掉了这些列名，本断言会打红提醒把上一条断言的
        基线数字一起更新 —— 否则上一条会因「扫描面为空」而永久假绿。
        """
        h_occurrence = [
            (wp, sheet, ref, col)
            for col, refs in PRESET_COLS.items()
            if col in EXPECTED_MISSING_BEFORE_FIX
            for (wp, sheet, ref, _f) in refs
            if re.fullmatch(r"H\d+", wp or "")
        ]
        # 🔴 按**格**去重后计数，不按引用次数 —— 双族加和（`TB('1641','本期借方')
        # +TB('1651','本期借方')`）让同一格出现两次同列引用，按次数会从 16 变 20
        # 而实际受影响的格数不变。
        h_cells = {(wp, sheet, ref) for (wp, sheet, ref, _col) in h_occurrence}
        assert len(h_cells) == 16, (
            f"H 类发生额受影响格数由 16 变为 {len(h_cells)}，"
            f"请同步复核上一条断言的基线：{sorted(h_cells)}"
        )
        got_wp = {wp for (wp, _s, _r, _c) in h_occurrence}
        assert got_wp == {"H1", "H2", "H3", "H8", "H9", "H10"}, got_wp


# ─────────────────── Property 7：禁静默回退期末余额 ───────────────────


class TestNoSilentFallbackToClosingBalance:
    def test_no_silent_fallback(self):
        """两条求值路径都不得把「列取不到」静默回退成期末余额。

        🔴 Wave 1 预期红。Task 4 改三态后转绿。
        """
        src = _strip_comments(_ENGINE.read_text(encoding="utf-8"))
        hits = src.count(_SILENT_FALLBACK)
        if hits:
            pytest.fail(
                f"【Wave 1 预期红】formula_engine 仍有 {hits} 处静默回退期末余额"
                f"（AST 路径 _handle_tb + 降级路径 _execute_regex），"
                f"取不到列名时会返回期末余额而不是报警"
            )

    def test_both_eval_paths_use_the_shared_resolver(self):
        """两条求值路径都必须走三态 helper `_resolve_tb_column`。

        只改一条路径另一条仍会静默回退 —— 这条断言把「两处都要改」钉死。
        改造前该形态在 `_handle_tb`（AST 路径）与 `_execute_regex`（降级路径）
        各有一处，共 2 处。
        """
        src = _strip_comments(_ENGINE.read_text(encoding="utf-8"))
        calls = src.count("_resolve_tb_column(")
        # 1 处定义 + 2 处调用（两条路径各一次）
        assert calls >= _SILENT_FALLBACK_PATHS + 1, (
            f"`_resolve_tb_column` 只出现 {calls} 次（期望 ≥ "
            f"{_SILENT_FALLBACK_PATHS + 1} = 1 定义 + {_SILENT_FALLBACK_PATHS} 调用）"
            f"→ 可能只有一条求值路径接了三态 helper"
        )
        assert "_execute_regex" in src and "_handle_tb" in src, (
            "两条求值路径的函数名之一不存在 → 抽取失效或引擎结构已变"
        )

    def test_resolver_distinguishes_unregistered_from_missing_data(self):
        """三态语义：未注册列名 → WARNING；已注册但无数据 → 返 0；命中 → 返值。

        关键是**未注册**与**无数据**必须走不同分支（改造前两者都回退期末余额，
        让「配置错」与「数据缺」共用一个错误处置并产出看起来合法的错数字）。
        """
        from decimal import Decimal

        from app.services.formula_engine import _resolve_tb_column

        data = {"期末余额": Decimal("1000"), "本期借方": Decimal("300")}

        trace: list[str] = []
        assert _resolve_tb_column(data, "本期借方", code="1601", trace=trace) == Decimal("300")

        trace.clear()
        # 已注册但该科目无此列 → 0 且 trace 标「列无数据」，**不得**返 1000
        assert _resolve_tb_column(data, "本期贷方", code="1601", trace=trace) == Decimal("0")
        assert any("列无数据" in t for t in trace), trace

        trace.clear()
        # 未注册 → 0 且 trace 标「列名未注册」，**不得**返 1000
        assert _resolve_tb_column(data, "不存在的列", code="1601", trace=trace) == Decimal("0")
        assert any("列名未注册" in t for t in trace), trace

    def test_tb_data_builders_produce_occurrence_keys(self):
        """两个 `tb_data` 构造点必须产出发生额键。

        列名注册了但构造点不产出该键 = 落到「列无数据」分支恒返 0 ——
        对使用方而言仍是取不到数（只是不再是错数字）。故两侧必须同时改。
        """
        targets = {
            "wp_template_files": _BACKEND / "app" / "routers" / "wp_template_files.py",
            "adjudication_writeback": (
                _BACKEND / "app" / "services" / "formula_management"
                / "adjudication_writeback.py"
            ),
        }
        for name, path in targets.items():
            src = _strip_comments(path.read_text(encoding="utf-8"))
            # 🔴 必须断言**调用点**而不是「符号出现」：把调用行改成 `pass` 后，
            # import 行与说明文字里仍留着该符号名 → 裸 `in src` 判定通过 =
            # 假绿（2026-08-06 变异检验 M3 实测抓出）。
            for fn in ("fetch_occurrence_by_standard_code", "merge_occurrence_into_tb_data"):
                calls = len(re.findall(rf"(?<![\w.]){fn}\s*\(", src))
                assert calls >= 1, (
                    f"{name} 里 `{fn}` 没有真实调用点（只出现在 import/文字中）"
                    f" → 发生额键不会被产出，`TB(code,'本期借方')` 恒返 0"
                )
            # 合并结果必须落回 tb_data（而不是算完丢弃 = 又一个 dead output）
            assert re.search(
                r"merge_occurrence_into_tb_data\(\s*tb_data\b", src
            ), f"{name} 的合并未作用在 tb_data 上"

    def test_occurrence_keys_match_engine_standard_fields(self):
        """交叉锁死：共享件的键名必须等于 `COLUMN_ALIASES` 的**标准字段名**。

        键名写错（如 `借方发生额` 而非 `本期借方`）会让合并进去的数据
        永远被 `_resolve_tb_column` 判为「列无数据」—— 两侧各自都「有代码」
        但链路是断的。
        """
        from app.services.four_table.occurrence_by_standard_code import (
            CREDIT_KEY,
            DEBIT_KEY,
        )

        standard_fields = set(ALIASES.values())
        assert DEBIT_KEY in standard_fields, (
            f"DEBIT_KEY={DEBIT_KEY!r} 不是 COLUMN_ALIASES 的标准字段名"
        )
        assert CREDIT_KEY in standard_fields, (
            f"CREDIT_KEY={CREDIT_KEY!r} 不是 COLUMN_ALIASES 的标准字段名"
        )
        # 且必须是「借方发生额」/「贷方发生额」两个别名解析到的那个字段
        assert ALIASES["借方发生额"] == DEBIT_KEY
        assert ALIASES["贷方发生额"] == CREDIT_KEY


# ─── Property 25：地址目录的 tb 域列名必须覆盖 COLUMN_ALIASES（否则存不进去）───
#
# spec: formula-management-runtime-closure Task 18（Requirements 3.1, 10.5）
#
# 🔴 **2026-08-07 真实库实测发现的第 12 处缺陷**：Wave 2 把四个发生额列名注册进
# `COLUMN_ALIASES` 让 48 格公式**能求值**了，但 `address_registry.
# build_trial_balance_entries` 的列名清单是**另一份硬编码 5 项**
# （`未审数/审定数/AJE调整/RJE调整/期初余额`）⇒ 14 键里 **9 个在地址目录中不存在**。
#
# 而 `PUT /formulas`（Tier A 编辑）与 `PUT /user-formulas`（用户公式）都在写库前跑
# `validate_refs_via_acnr` → TB 域落回 legacy `validate_formula_refs`，
# 后者按「ref 转 URI 后是否在 uri_set 里」判定 ⇒ **任何用这 9 个列名写的公式
# 保存时必被 422 `FORMULA_REF_NOT_FOUND` 拒绝**，报错文案还是
# 「引用地址在当前项目中不存在」（指向数据缺失，实为目录缺列 = 误导排查方向）。
#
# 影响面（逐条实测，项目 0ec33ac9 / year 2025）：
#   - 改造前 tb 域 980 条目 / 196 科目 / **5** 个列名；改造后 2744 条目 / **14** 个列名
#   - `期末余额` 是预设里用得最多的列（实测 280 格），而 D1 的 Tier A 预设本体就是
#     `TB('1121','期末余额') - TB('1231-01','期末余额')`
#     ⇒ 审计师在公式管理面板里**改任何一条 Tier A 公式都存不进去**
#   - 14 列逐个 `validate_refs_via_acnr` 实测：改造前 5 PASS / 9 fail，改造后 14 PASS
#
# 该修复是**纯 additive**（只往 uri_set 加条目 ⇒ 校验只会更宽松），
# 零回归有结构性保证，不依赖回归测试碰运气。


class TestAddressRegistryTbColumnsCoverAliases:
    """tb 域地址目录列名 ⊇ `COLUMN_ALIASES` 键集（交叉锁死，不连库）。"""

    def test_tb_columns_cover_all_registered_aliases(self):
        from app.services.address_registry import trial_balance_address_columns

        cols = set(trial_balance_address_columns())
        missing = sorted(set(ALIASES) - cols)
        assert not missing, (
            f"tb 域地址目录缺 {len(missing)} 个已注册列名：{missing}\n"
            "⇒ 用这些列名写的公式保存时会被 422 FORMULA_REF_NOT_FOUND 拒绝，"
            "而报错文案指向「数据不存在」= 误导排查方向。"
        )

    def test_legacy_five_columns_still_registered(self):
        """零回归：历史 5 项一个不许少（它们是既有可保存公式的地址来源）。"""
        from app.services.address_registry import (
            _TB_LEGACY_COLUMNS,
            trial_balance_address_columns,
        )

        cols = set(trial_balance_address_columns())
        dropped = sorted(set(_TB_LEGACY_COLUMNS) - cols)
        assert not dropped, f"历史列名被丢弃：{dropped}"

    def test_columns_are_derived_not_hardcoded(self):
        """源码级：`build_trial_balance_entries` 必须走派生函数，禁再硬编码清单。

        判据落在**赋值形态**上（而不是「文件里出现过某个符号」）——
        memory 已记同族坑：`toContain(标识符)` 抓不住「把条件改成 if False」。
        """
        src = _strip_comments(
            (_BACKEND / "app" / "services" / "address_registry.py").read_text(
                encoding="utf-8"
            )
        )
        assert re.search(r"columns\s*=\s*trial_balance_address_columns\(\s*\)", src), (
            "build_trial_balance_entries 的 columns 不再由 "
            "trial_balance_address_columns() 派生 → 又回到硬编码清单"
        )
        # 反向自检：改造前的硬编码清单形态必须已经消失
        assert not re.search(
            r"columns\s*=\s*\[\s*'未审数'\s*,\s*'审定数'", src
        ), "硬编码 5 项清单复活了"

    def test_selfcheck_derivation_reflects_alias_changes(self):
        """反向自检：派生函数确实读 `COLUMN_ALIASES`（不是另抄一份 14 项字面量）。

        判据 = 往别名表里临时塞一个键，派生结果必须跟着变；
        若它是写死的字面量，塞了也不会变（断言即打红）。
        """
        from app.services import formula_engine as fe
        from app.services.address_registry import trial_balance_address_columns

        probe = "__ADDR_REGISTRY_PROBE_COL__"
        fe.COLUMN_ALIASES[probe] = "期末余额"
        try:
            assert probe in trial_balance_address_columns(), (
                "派生函数没有真读 COLUMN_ALIASES —— 它可能另抄了一份字面量清单"
            )
        finally:
            fe.COLUMN_ALIASES.pop(probe, None)
        # 还原后不得残留
        assert probe not in trial_balance_address_columns()
