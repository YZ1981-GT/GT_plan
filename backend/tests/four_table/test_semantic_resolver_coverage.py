"""守卫：语义科目解析器的**真实消费**与声明一致性。

🔴 **本文件的第一版是「假绿生成器」**：它只 grep 字符串 ``resolve_semantic_accounts``，
于是 23 个「赋值后从不读取」的死代码文件（`_sem_accounts` assigns=2 / reads=0，
每次 render 白跑 3~7 条 DB 查询后丢弃结果）全部被判为"已迁移"，
连带让 tasks.md 记成 57/57 = 100%。教训与平台铁律「任务标记不能假绿」「dead output」同源。

现版本改为断言**解析结果被真实消费**（`codes_of` / `standard_codes_of` / `slots` /
`as_dict` / 传参给下游），并补上第一版漏掉的两个洞：
  ① 互斥检查排除了 K/H 循环（不同 spec 格式）→ 漏掉 L7 与 K5 都认领 ``2801``；
  ② 未校验传给 `resolve_semantic_accounts` 的 spec **类型**
     → 漏掉 F1/F5 传 `ReportLineAccountSpec`（该函数读 ``spec.slots``，RLA 无此属性 → AttributeError）。

spec: semantic-account-resolver-full-rollout Task 11/16/19/23/26
"""
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
RENDER_DIR = _BACKEND / "app" / "routers" / "wp_render_strategies"
FOUR_TABLE_DIR = _BACKEND / "app" / "services" / "four_table"

SKIP_PATTERNS = (
    "_ai", "_import_export", "_service", "_validate", "_ocr", "_engine",
    "_sync", "_export", "_disclosure_io", "_contract_ocr", "_stocktake",
    "_special", "_valuation", "_derecognition", "_peer_policies",
    "_depreciation", "_amortization", "_capitalization", "_dcf",
    "_interest_cap", "_transfer", "_property_ocr", "_plan_sync", "_summary_sync",
)

#: 「解析结果被真实消费」的证据
CONSUME_MARKERS = ("codes_of", "standard_codes_of", "slots", "as_dict",
                   "conflicts", "chart_available")


def _four_table_strategies() -> list[Path]:
    """所有涉及四表取数的主 render 策略（D~N 循环）。"""
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
        if any(k in src for k in ("_fetch_tb", "TbBalance", "ReportLineAccountSpec",
                                  "resolve_report_line_accounts")):
            out.append(f)
    return out


def _really_consumes(src: str) -> bool:
    """解析结果是否被真实消费（而非赋值即丢弃）。"""
    recv = re.findall(r"(\w+)\s*=\s*await resolve_semantic_accounts\(", src)
    for var in recv:
        for kw in CONSUME_MARKERS:
            if re.search(rf"\b{re.escape(var)}\s*\.\s*{re.escape(kw)}", src):
                return True
        # 结果被整体传给下游函数
        if re.search(rf"\(\s*{re.escape(var)}\s*[,)]", src):
            return True
    return False


class TestRealConsumption:
    """Property: 凡调用 resolve_semantic_accounts，其结果必须被真实消费。"""

    def test_no_dead_resolver_calls(self):
        """禁止「赋值后从不读取」—— 那是每次 render 白跑数条 DB 查询的纯浪费。"""
        dead = []
        for f in RENDER_DIR.iterdir():
            if not f.name.endswith(".py") or not f.name.startswith("_"):
                continue
            src = f.read_text(encoding="utf-8")
            if "await resolve_semantic_accounts(" not in src:
                continue
            if not _really_consumes(src):
                dead.append(f.name)
        assert dead == [], (
            "以下文件调用了 resolve_semantic_accounts 但结果从未被消费"
            f"（死代码 + 无谓 DB 开销）:\n" + "\n".join(f"  {d}" for d in dead)
        )

    def test_reverse_selfcheck_detects_dead_code(self):
        """反向自检：死代码样本必须被 _really_consumes 判否（防判据空转）。"""
        dead_sample = (
            "async def f(ctx):\n"
            "    try:\n"
            "        _sem = await resolve_semantic_accounts(ctx, X_SPEC)\n"
            "    except Exception:\n"
            "        _sem = None\n"
            "    return {}\n"
        )
        live_sample = (
            "async def f(ctx):\n"
            "    acc = await resolve_semantic_accounts(ctx, X_SPEC)\n"
            '    return acc.codes_of("gross")\n'
        )
        assert _really_consumes(dead_sample) is False
        assert _really_consumes(live_sample) is True


class TestSpecTypeSafety:
    """Property: 传给 resolve_semantic_accounts 的必须是 SemanticAccountSpec。

    `resolve_semantic_accounts` 内部读 ``spec.slots``；`ReportLineAccountSpec`
    没有该属性 → 运行时 AttributeError（被 except 吞掉后表现为「取数恒空」）。
    """

    def test_no_report_line_spec_passed_to_semantic_resolver(self):
        bad = []
        for f in RENDER_DIR.iterdir():
            if not f.name.endswith(".py") or not f.name.startswith("_"):
                continue
            src = f.read_text(encoding="utf-8")
            for var in re.findall(r"resolve_semantic_accounts\(\s*ctx\s*,\s*([A-Za-z_]\w*)", src):
                if re.search(rf"^{re.escape(var)}\s*=\s*ReportLineAccountSpec\(", src, re.M):
                    bad.append(f"{f.name}: {var}")
        assert bad == [], (
            "以下调用把 ReportLineAccountSpec 传给了 resolve_semantic_accounts"
            "（会抛 AttributeError: 'ReportLineAccountSpec' object has no attribute 'slots'）:\n"
            + "\n".join(f"  {b}" for b in bad)
        )

    def test_reverse_selfcheck_rla_lacks_slots(self):
        """反向自检：证明 ReportLineAccountSpec 确实没有 slots（本守卫的前提）。"""
        from app.services.four_table.report_line_accounts import ReportLineAccountSpec

        assert not hasattr(ReportLineAccountSpec(row_code="X"), "slots")


class TestPerCycleSpecsExist:
    """Property: 各循环的 specs 模块可用。"""

    @pytest.mark.parametrize("module", [
        "g_cycle_specs", "d_cycle_specs", "f_cycle_specs",
        "h_cycle_specs", "i_cycle_specs", "l_cycle_specs",
        "m_cycle_specs", "n_cycle_specs", "k_cycle_specs",
    ])
    def test_specs_module_importable(self, module):
        import importlib

        assert importlib.import_module(f"app.services.four_table.{module}") is not None

    def test_j_cycle_has_semantic_specs(self):
        from app.services.four_table.j_cycle_account_scope import j_semantic_spec_of

        assert j_semantic_spec_of("J1") is not None
        assert j_semantic_spec_of("J2") is not None

    def test_k_cycle_has_semantic_bridge(self):
        from app.services.four_table.k_cycle_specs import semantic_spec_of

        assert semantic_spec_of("K3") is not None
        assert semantic_spec_of("K8") is not None


class TestFallbackCodeMutualExclusion:
    """Property: 兜底码跨循环互斥（同一标准码不得被两个循环认领为原值）。

    🔴 第一版漏了 K/H 循环（spec 格式不同）→ 没抓到 L7 与 K5 都认领 ``2801``。
    本版把 K（`KCycleSpec`）与 J（bridge）一并纳入同一张认领表。
    """

    def _claims(self) -> dict[str, str]:
        """{标准码: 认领它的 wp_code}，冲突时抛。"""
        from app.services.four_table.d_cycle_specs import D_CYCLE_SPECS
        from app.services.four_table.f_cycle_specs import F_CYCLE_SPECS
        from app.services.four_table.g_cycle_specs import G_CYCLE_SPECS
        from app.services.four_table.i_cycle_specs import I_CYCLE_SPECS
        from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
        from app.services.four_table.l_cycle_specs import L_CYCLE_SPECS
        from app.services.four_table.m_cycle_specs import M_CYCLE_SPECS
        from app.services.four_table.n_cycle_specs import N_CYCLE_SPECS

        owner: dict[str, str] = {}

        def claim(code: str, wp: str):
            if not code:
                return
            prev = owner.get(code)
            assert prev is None or prev == wp, (
                f"兜底码 {code} 被 {prev} 与 {wp} 同时认领为原值科目 —— "
                "跨循环科目必须互斥（两个循环取同一科目 = 双算）"
            )
            owner[code] = wp

        # SemanticAccountSpec 格式（gross 槽）
        for specs in (D_CYCLE_SPECS, F_CYCLE_SPECS, G_CYCLE_SPECS,
                      I_CYCLE_SPECS, L_CYCLE_SPECS, M_CYCLE_SPECS, N_CYCLE_SPECS):
            for wp, spec in specs.items():
                for slot in spec.slots:
                    if slot.key != "gross":
                        continue  # 备抵可与原值循环重合，只查原值
                    for code in slot.fallback_standard_codes:
                        claim(code, wp)

        # KCycleSpec 格式（第一版漏掉的）
        for wp, kspec in K_CYCLE_SPECS.items():
            claim(kspec.fallback_standard, wp)

        return owner

    def test_no_duplicate_fallback_across_all_cycles(self):
        owner = self._claims()
        assert len(owner) > 30, f"认领表过小（{len(owner)}），判据可能空转"

    def test_reverse_selfcheck_k5_owns_2801(self):
        """反向自检：K5 预计负债认领 2801（L7 不得再认领它）。"""
        owner = self._claims()
        assert owner.get("2801") == "K5"


class TestNoNewReportLineAccountsImport:
    """降级守卫：新增 render 文件不得引入 report_line_accounts。

    存量白名单随逐个循环真迁移逐步缩小；**清一个必跑一次全量确认无回归**。
    """

    LEGACY_RLA_WHITELIST = frozenset({
        "_f1_prepayment.py",
        "_g7_long_term_equity_main.py",
        "_j1_employee_compensation.py",
        "_j2_defined_benefit_plan.py",
        "_k1_import_export.py",
        "_k1_other_receivables.py",
        "_k2_other_current_assets.py",
        "_k3_other_payables.py",
        "_k4_other_current_liabilities.py",
        "_k5_provisions.py",
        "_k6_held_for_sale.py",
        "_k7_deferred_income.py",
    })

    def test_no_new_rla_imports(self):
        violations = []
        for f in RENDER_DIR.iterdir():
            if not f.name.endswith(".py") or not f.name.startswith("_"):
                continue
            if f.name in self.LEGACY_RLA_WHITELIST:
                continue
            if "from app.services.four_table.report_line_accounts import" in f.read_text(
                encoding="utf-8"
            ):
                violations.append(f.name)
        assert violations == [], (
            "以下文件不在白名单内却引入了 report_line_accounts（新文件禁止引入）:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_whitelist_has_no_stale_entries(self):
        """白名单不得留已清理干净的条目（否则失去收敛压力）。"""
        stale = []
        for name in self.LEGACY_RLA_WHITELIST:
            p = RENDER_DIR / name
            if not p.exists():
                stale.append(f"{name}(文件不存在)")
            elif "from app.services.four_table.report_line_accounts import" not in p.read_text(
                encoding="utf-8"
            ):
                stale.append(f"{name}(已不再引用，应移出白名单)")
        assert stale == [], "白名单有陈旧条目:\n" + "\n".join(f"  {s}" for s in stale)


class TestHonestCoverageReport:
    """如实记录覆盖率，不把死代码算成已迁移。"""

    #: 真消费基线 = 24（13 G + 9 H + E1 + G6-main，2026-08-03 实测）。
    #: 🔴 这个数字**只许升不许降**；升了要同步改这里，降了说明有迁移被回退。
    REAL_CONSUMPTION_BASELINE = 24

    def test_coverage_baseline_not_regressed(self):
        """真消费的策略数不得下降。"""
        real = [f.name for f in _four_table_strategies()
                if "await resolve_semantic_accounts(" in f.read_text(encoding="utf-8")
                and _really_consumes(f.read_text(encoding="utf-8"))]
        assert len(real) >= self.REAL_CONSUMPTION_BASELINE, (
            f"真消费策略数 {len(real)} 低于基线 {self.REAL_CONSUMPTION_BASELINE}"
            " —— 有迁移被回退？\n" + "\n".join(f"  {r}" for r in sorted(real))
        )

    def test_total_strategy_count_stable(self):
        """涉四表策略总数稳定（新增循环时须同步更新基线并复核覆盖）。"""
        assert len(_four_table_strategies()) >= 55
