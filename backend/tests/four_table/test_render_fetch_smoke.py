"""取数路径冒烟测试 —— 补上「4 个 AttributeError regression 溜过 962 例」的安全网。

**为什么需要这一层（本文件的存在理由）**

各循环 render 的取数函数一律 **fail-open**::

    try:
        accounts = await resolve_semantic_accounts(ctx, SPEC)
        ...
    except Exception as e:            # noqa: BLE001
        logger.warning("G1 TB fetch failed: %s", e)
    return result                     # ← 返回键齐全，只是值变空

于是「取数彻底坏掉」的线上表现是**取数恒空**而不是报错：

- 返回结构完全正常（`tb_values` / `tb_source_codes` / `adjudication_prefill` 键都在）
  → 只断言返回结构的测试**抓不到**；
- 异常被 `except` 吞掉 → 只断言「不抛异常」的测试**也抓不到**。

实证（2026-08-03）：F1/F3/F4/F5 把解析器换成 `resolve_semantic_accounts` 却仍读
`accounts.gross`（`ReportLineAccounts` 独有字段）→ 运行时 AttributeError，
**`four_table` 962 例全绿一个没抓到**，因为 44/57 个策略的取数函数从无测试真实调用。
同族历史缺陷：G6 曾 `await select_leaves(...)`（同步纯函数）抛 TypeError 被吞成 warning，
导致「G6-1 审定表 TB seed 一直恒空」。

**故本文件的判据是「取数没走进 except 分支」** —— 用 logging handler 捕获 WARNING/ERROR，
捕获到即判红。反向自检 :class:`TestSelfCheck` 故意注入 F3 式属性错误，证明判据不空转。

**fake 科目表由各循环 spec 自动生成**（`_build_fake_chart`），新增循环只要在
`_cycle_specs.py` 里声明就自动被覆盖，无需手工维护本文件的 fixture。

spec: semantic-account-resolver-full-rollout（复盘补强）
"""
from __future__ import annotations

import importlib
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa

RENDER_PKG = "app.routers.wp_render_strategies"
RENDER_DIR = Path(__file__).resolve().parents[2] / "app" / "routers" / "wp_render_strategies"

SKIP_PATTERNS = (
    "_ai", "_import_export", "_service", "_validate", "_ocr", "_engine",
    "_sync", "_export", "_disclosure_io", "_contract_ocr", "_stocktake",
    "_special", "_valuation", "_derecognition", "_peer_policies",
    "_depreciation", "_amortization", "_capitalization", "_dcf",
    "_interest_cap", "_transfer", "_property_ocr", "_plan_sync", "_summary_sync",
)

#: 取数函数名（各循环命名不统一）
FETCH_FN_RE = re.compile(
    r"async def (_fetch_tb[\w]*|_load_[\w]*leaves[\w]*)\(([^)]*)\)"
)


# ─────────────────────────────────────────────────────────────────────────────
# fake DB
# ─────────────────────────────────────────────────────────────────────────────


class _Row:
    """宽容行对象：未声明的列返回 ``None``（`to_leaf_rows` 用 `getattr(r,k,None)`）。

    🔴 必须提供真实 `_mapping` —— 部分取数走 `dict(r._mapping)`
    （如 `i_cycle_extraction._fetch_tb_rows`），靠 `__getattr__` 返回 None
    会变成 `dict(None)` → `'NoneType' object is not iterable`，
    表现为「fake 不够」的噪声而不是真缺陷。
    """

    def __init__(self, **kw):
        self.__dict__.update(kw)

    @property
    def _mapping(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def __getattr__(self, k):  # noqa: D105
        if k.startswith("__"):
            raise AttributeError(k)
        return None


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


def _build_fake_chart() -> list[_Row]:
    """从各循环 spec 自动生成 fake `account_chart`（新增循环自动覆盖）。"""
    rows: dict[str, _Row] = {}

    def add(code: str, name: str):
        if code and name and code not in rows:
            rows[code] = _Row(
                account_code=code, account_name=name,
                direction="debit", source="client",
            )

    # SemanticAccountSpec 格式
    for mod_name in ("d_cycle_specs", "f_cycle_specs", "g_cycle_specs",
                     "h_cycle_specs", "i_cycle_specs", "l_cycle_specs",
                     "m_cycle_specs", "n_cycle_specs"):
        try:
            mod = importlib.import_module(f"app.services.four_table.{mod_name}")
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(mod):
            if not attr.endswith("_CYCLE_SPECS"):
                continue
            for spec in getattr(mod, attr).values():
                for slot in getattr(spec, "slots", ()):
                    codes = slot.fallback_standard_codes
                    if codes:
                        add(codes[0], slot.names[0] if slot.names else "")

    # KCycleSpec 格式
    try:
        from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS

        for kspec in K_CYCLE_SPECS.values():
            add(kspec.fallback_standard, kspec.account_name)
    except Exception:  # noqa: BLE001
        pass

    return list(rows.values())


_FAKE_CHART = _build_fake_chart()


class FakeSession:
    """按 SQL 关键字路由的 fake session（覆盖取数链路涉及的表）。

    🔴 不用 ``MagicMock`` —— memory 铁律：MagicMock 传给 ``sa.and_`` 会被拒，
    异常被 fail-open 吞成空结果，测试「通过」却什么都没测。
    """

    def __init__(self, chart=None):
        self.chart = _FAKE_CHART if chart is None else chart
        self.seen: list[str] = []

    async def execute(self, stmt, params=None):  # noqa: D102
        s = str(stmt)
        self.seen.append(s[:80])

        if "projects" in s:
            return _Rows([_Row(
                client_name="测试客户", audit_year=2025,
                applicable_standard_v2={"entity_type": "soe", "scope": "standalone"},
                entity_type="soe", scope="standalone", business_category="",
            )])
        if "report_config" in s:
            # 不返公式 → 逼取数走「按科目名定位 / 兜底码」路径（更严格）
            return _Rows([])
        if "account_chart" in s:
            return _Rows(self.chart)
        if "account_mapping" in s:
            codes = list((params or {}).get("codes") or [])
            return _Rows([
                _Row(original_account_code=c, standard_account_code=c) for c in codes
            ])
        if "checklist_responses" in s or "wp_index" in s or "working_paper" in s:
            return _Rows([])

        # tb_balance / trial_balance 的 sa.select()：给每个 fake 科目一行余额
        return _Rows([
            _Row(
                account_code=r.account_code, account_name=r.account_name,
                standard_account_code=r.account_code,
                opening_balance=1000.0, closing_balance=1500.0,
                debit_amount=800.0, credit_amount=300.0,
                closing_direction="debit", opening_direction="debit",
                dataset_id=None,
                unadjusted_amount=1500.0, audited_amount=1500.0,
                begin_balance=1000.0, end_balance=1500.0, amount=1500.0,
            )
            for r in self.chart
        ])


class _Capture(logging.Handler):
    """捕获 WARNING+ —— 取数走进 except 分支的唯一可观测信号。"""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records: list[str] = []

    def emit(self, record):  # noqa: D102
        self.records.append(f"{record.name}: {record.getMessage()}")


@pytest.fixture
def capture_warnings():
    """挂到所有 render 策略 logger 上。"""
    cap = _Capture()
    attached = []
    for name in list(logging.root.manager.loggerDict):
        if name.startswith(RENDER_PKG) or name.startswith("app.services.four_table"):
            lg = logging.getLogger(name)
            lg.addHandler(cap)
            attached.append(lg)
    root = logging.getLogger(RENDER_PKG)
    root.addHandler(cap)
    attached.append(root)
    yield cap
    for lg in attached:
        lg.removeHandler(cap)


def _fake_ctx(**kw):
    base = dict(
        db=FakeSession(), project_id=uuid4(), wp_id=uuid4(), year=2025,
        wp_code="XX", business_category="", sheet_html_data=None,
        sheet_schema=None, template_file_path=None, working_paper=None,
        classification=None, component_type="", cross_ref_items=[],
        prep_info=None, classifications=[], audit_cycle=None,
        source_files=[], user_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ─────────────────────────────────────────────────────────────────────────────
# 目标收集
# ─────────────────────────────────────────────────────────────────────────────


def _discover() -> list[tuple[str, str]]:
    """``[(模块名, 取数函数名), ...]``，只收单参 ``(ctx)`` 的（多参在专门用例里覆盖）。"""
    out = []
    for f in sorted(RENDER_DIR.iterdir()):
        if not f.name.startswith("_") or not f.name.endswith(".py"):
            continue
        if any(x in f.name for x in SKIP_PATTERNS):
            continue
        m = re.match(r"_([a-z]\d+)_", f.name)
        if not m or m.group(1).upper()[0] not in "DEFGHIJKLMN":
            continue
        src = f.read_text(encoding="utf-8")
        for fn, args in FETCH_FN_RE.findall(src):
            # 只保留单参（去掉类型注解后仅一个 ctx）
            parts = [a for a in args.split(",") if a.strip()]
            if len(parts) == 1:
                out.append((f.name[:-3], fn))
    return out


_TARGETS = _discover()


async def _true_filter(db, table, project_id, year):
    return sa.true()


#: 取数会下潜到的共享子模块（它们各自 `from ... import get_active_filter`，
#: 持的是直接引用 → 必须逐模块打补丁，patch 上游包无效）
_SHARED_FILTER_MODULES = (
    "app.services.four_table.i_cycle_extraction",
    "app.services.four_table.tb_query",
    "app.services.four_table.tb_fetch",
    "app.services.four_table.pl_render",
    "app.services.four_table.l_cycle_extraction.render_support",
)


def _patch_filter(mod):
    """把模块（及取数会下潜到的共享子模块）持有的 `get_active_filter` 换掉。

    🔴 必须返回 `sa.true()` 而非 MagicMock：取数里会写 `sa.and_(active_filter, ...)`，
    非 SA 表达式会被 `sa.and_` 拒绝 → fail-open 吞成空 → 假绿。
    """
    restore: list[tuple[object, object]] = []
    for target in (mod, *[_safe_import(m) for m in _SHARED_FILTER_MODULES]):
        if target is not None and hasattr(target, "get_active_filter"):
            restore.append((target, target.get_active_filter))
            target.get_active_filter = _true_filter
    return restore


def _safe_import(name):
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001
        return None


def _unpatch(restore):
    for target, orig in restore or []:
        target.get_active_filter = orig


class TestFetchPathDoesNotFailOpen:
    """Property: 取数函数在正常入参下不得走进 except 分支（fail-open = 取数恒空）。"""

    def test_targets_discovered(self):
        """自检：目标集合非空且规模合理（防 discovery 正则失效导致空跑）。"""
        assert len(_TARGETS) >= 30, f"只发现 {len(_TARGETS)} 个取数函数，discovery 可能失效"

    @pytest.mark.parametrize("mod_name,fn_name", _TARGETS, ids=lambda v: str(v))
    def test_no_failopen_warning(self, mod_name, fn_name, capture_warnings):
        mod = importlib.import_module(f"{RENDER_PKG}.{mod_name}")
        fn = getattr(mod, fn_name)
        restore = _patch_filter(mod)
        try:
            import asyncio

            asyncio.run(fn(_fake_ctx(wp_code=mod_name.split("_")[1].upper())))
        finally:
            _unpatch(restore)

        offending = [r for r in capture_warnings.records if mod_name in r or "four_table" in r]
        assert offending == [], (
            f"{mod_name}.{fn_name} 走进了 fail-open 分支（线上表现 = 取数恒空）:\n"
            + "\n".join(f"  {o}" for o in offending)
        )


#: 多参取数函数 —— `_discover()` 只收单参，这些必须**显式登记**。
#: 🔴 不登记就会静默漏掉（上一轮 57/57 假绿正是「漏掉的当成覆盖了」）。
#: 格式：``(模块名, 函数名, 额外位置参构造器)``
_MULTI_ARG_TARGETS = [
    ("_g5_long_term_receivable", "_load_leaves", lambda mod: (["1531"],)),
    ("_n3_deferred_tax_liabilities", "_fetch_tb_data", lambda mod: (["2901"],)),
    ("_n5_income_tax_expense", "_fetch_tb_data", lambda mod: (["6801"],)),
    ("_n4_taxes_and_surcharges", "_fetch_tb_period_amount", lambda mod: (["6403"],)),
    ("_n2_taxes_payable", "_fetch_tb_data", lambda mod: (2025,)),
    # N1 的取数函数有必需 kwargs
    ("_n1_deferred_tax_assets", "_fetch_tb_for_codes",
     lambda mod: (["1811"], {"account_name": "递延所得税资产", "direction": "debit"})),
    # J1/J2 仍走 RLA 解析器，用它们自己的 `_resolve_jN_accounts(ctx)` 拿真实入参
    ("_j1_employee_compensation", "_load_j1_leaves", "_resolve_j1_accounts"),
    ("_j2_defined_benefit_plan", "_load_j2_leaves", "_resolve_j2_accounts"),
]


class TestMultiArgFetchPaths:
    """多参取数函数同样不得走进 fail-open 分支。"""

    def test_all_multi_arg_functions_registered(self):
        """自检：源码里的多参取数函数必须全部登记在 `_MULTI_ARG_TARGETS`。

        🔴 这条防的正是「discovery 漏掉 → 当成已覆盖」的假绿路径。
        """
        found = set()
        for f in sorted(RENDER_DIR.iterdir()):
            if not f.name.startswith("_") or not f.name.endswith(".py"):
                continue
            if any(x in f.name for x in SKIP_PATTERNS):
                continue
            m = re.match(r"_([a-z]\d+)_", f.name)
            if not m or m.group(1).upper()[0] not in "DEFGHIJKLMN":
                continue
            for fn, args in FETCH_FN_RE.findall(f.read_text(encoding="utf-8")):
                parts = [a for a in args.split(",") if a.strip()]
                if len(parts) > 1:
                    found.add((f.name[:-3], fn))
        registered = {(m, f) for m, f, _ in _MULTI_ARG_TARGETS}
        missing = found - registered
        assert missing == set(), (
            "以下多参取数函数未登记（会被 discovery 静默漏掉）:\n"
            + "\n".join(f"  {m}.{f}" for m, f in sorted(missing))
        )

    @pytest.mark.parametrize(
        "mod_name,fn_name,extra", _MULTI_ARG_TARGETS,
        ids=[f"{m}-{f}" for m, f, _ in _MULTI_ARG_TARGETS],
    )
    def test_no_failopen_warning(self, mod_name, fn_name, extra, capture_warnings):
        import asyncio

        mod = importlib.import_module(f"{RENDER_PKG}.{mod_name}")
        fn = getattr(mod, fn_name)
        restore = _patch_filter(mod)
        ctx = _fake_ctx(wp_code=mod_name.split("_")[1].upper())
        try:
            kwargs: dict = {}
            if isinstance(extra, str):
                # 用该模块自己的解析 helper 拿真实入参（比自造替身更贴近运行态）
                accounts = asyncio.run(getattr(mod, extra)(ctx))
                args = (accounts,)
            else:
                built = extra(mod)
                if built and isinstance(built[-1], dict):
                    *pos, kwargs = built
                    args = tuple(pos)
                else:
                    args = built
            asyncio.run(fn(ctx, *args, **kwargs))
        finally:
            _unpatch(restore)

        offending = [r for r in capture_warnings.records
                     if mod_name in r or "four_table" in r]
        assert offending == [], (
            f"{mod_name}.{fn_name} 走进了 fail-open 分支（线上表现 = 取数恒空）:\n"
            + "\n".join(f"  {o}" for o in offending)
        )


class TestSelfCheck:
    """反向自检：证明上面的判据不空转。"""

    def test_injected_attribute_error_is_caught(self, capture_warnings):
        """注入 F3 式属性错误（读 SemanticAccountResult 上不存在的 .gross）必须判红。"""
        import asyncio

        mod = importlib.import_module(f"{RENDER_PKG}._g1_trading_financial_assets")
        restore = _patch_filter(mod)
        orig_resolve = mod.resolve_semantic_accounts

        async def buggy(ctx, spec):
            result = await orig_resolve(ctx, spec)
            _ = result.gross  # SemanticAccountResult 无此字段 → AttributeError
            return result

        mod.resolve_semantic_accounts = buggy
        try:
            out = asyncio.run(mod._fetch_tb_data(_fake_ctx(wp_code="G1")))
        finally:
            mod.resolve_semantic_accounts = orig_resolve
            _unpatch(restore)

        assert capture_warnings.records, "注入的 AttributeError 未被捕获 —— 判据空转"
        assert any("no attribute 'gross'" in r for r in capture_warnings.records)
        # 同时证明：为什么只看返回值抓不到
        assert set(out.keys()) >= {"tb_values", "tb_source_codes"}, "返回键仍齐全"
        assert out["tb_values"] == {}, "值变空 —— 正是线上「取数恒空」的表现"

    def test_fake_chart_is_generated_from_specs(self):
        """自检：fake 科目表确实由 spec 自动生成（非硬编码空表）。"""
        assert len(_FAKE_CHART) >= 25, f"fake chart 只有 {len(_FAKE_CHART)} 行"
        codes = {r.account_code for r in _FAKE_CHART}
        assert "1101" in codes, "G1 交易性金融资产兜底码缺失"
        assert "1511" in codes, "G7 长期股权投资兜底码缺失"

    def test_active_filter_patch_returns_real_sa_expression(self):
        """自检：过滤器替身返回真实 SA 表达式（MagicMock 会被 sa.and_ 拒绝）。"""
        import asyncio

        mod = importlib.import_module(f"{RENDER_PKG}._g1_trading_financial_assets")
        restore = _patch_filter(mod)
        try:
            f = asyncio.run(mod.get_active_filter(None, None, None, None))
            # 必须能进 sa.and_ 而不抛
            sa.and_(f, sa.true())
        finally:
            _unpatch(restore)
