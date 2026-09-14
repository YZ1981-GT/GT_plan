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

#: 🔴 `SKIP_PATTERNS` 是**子串**匹配，有两处误伤真实主策略，必须强制纳入域内：
#:   - ``_h4_engineering_materials.py`` —— ``_engineering`` 内含 ``_engine``
#:   - ``_m7_special_reserve.py``       —— ``_special_reserve`` 内含 ``_special``
#: 不强制纳入会让 M7 这个**确实未迁移**的四表策略逃出裁决名单（假绿）。
DOMAIN_FORCE_INCLUDE = frozenset({
    "_h4_engineering_materials.py",
    "_m7_special_reserve.py",
})

FOUR_TABLE_KEYWORDS = ("_fetch_tb", "TbBalance", "ReportLineAccountSpec",
                       "resolve_report_line_accounts")


def _four_table_strategies() -> list[Path]:
    """所有涉及四表取数的主 render 策略（D~N 循环）。"""
    out = []
    for f in sorted(RENDER_DIR.iterdir()):
        if not f.name.startswith("_") or not f.name.endswith(".py"):
            continue
        if f.name not in DOMAIN_FORCE_INCLUDE and any(x in f.name for x in SKIP_PATTERNS):
            continue
        m = re.match(r"_([a-z]\d+)_", f.name)
        if not m or m.group(1).upper()[0] not in "DEFGHIJKLMN":
            continue
        src = f.read_text(encoding="utf-8")
        if any(k in src for k in FOUR_TABLE_KEYWORDS):
            out.append(f)
    return out


def _all_render_strategy_files() -> list[Path]:
    """全部 render 策略文件（不过滤 SKIP_PATTERNS）—— 真消费基线的度量域。"""
    return [f for f in sorted(RENDER_DIR.iterdir())
            if f.name.endswith(".py") and f.name.startswith("_")]


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

    def test_k_cycle_semantic_bridge_is_withdrawn(self):
        """🔴 K 循环的语义桥接已**撤回**（Requirement 5.1 / Property 16）。

        撤回而非接线的实证依据（2026-08-09 `account_chart` 按 source 分域对账）：
        K 循环主科目在项目间**同码同名**（`2241` standard 10 / client 8 项目、
        `2801` 8/5、`2401` 9/6、`6601` 10/8、`6602` 10/8 …），语义解析买不到东西；
        而旧桥接 `to_semantic_spec` 硬编码 ``row_code_soe`` + 单槽规格 ⇒
        接过去对**上市**项目即 regression。且它**生产零消费方**（只有本测试引用）。

        本测试从「断言桥接存在」反转为「断言桥接不得重新引入」——
        防下个会话看见 J 循环有 bridge 就给 K 也补一个（平台已因此返工过一轮）。
        """
        from app.services.four_table import k_cycle_specs

        for name in ("to_semantic_spec", "semantic_spec_of"):
            assert not hasattr(k_cycle_specs, name), (
                f"k_cycle_specs.{name} 已于 K 循环收口 spec 撤回，不得重新引入。"
                f"理由见 SEMANTIC_BRIDGE_WITHDRAWAL_REASON；"
                f"要接语义定位须先修「硬编码 row_code_soe」与「多槽关闭报表兜底层」"
            )

        # 撤回理由必须留在生产代码里（不能只写在测试里，否则读源码的人看不到）
        reason = getattr(k_cycle_specs, "SEMANTIC_BRIDGE_WITHDRAWAL_REASON", "")
        assert len(reason) >= 40, f"撤回理由过短或缺失：{reason!r}"
        assert "零消费方" in reason or "生产零" in reason
        assert "row_code_soe" in reason, "撤回理由须写明旧桥接的具体缺陷"


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

    #: 真消费基线 = **28**，度量域 = 全部 render 策略文件（`_all_render_strategy_files`）。
    #:
    #: 依据（2026-08-03 变量名无关实证，先抓 ``(\\w+) = await resolve_semantic_accounts``
    #: 再数该变量被 ``.`` / ``[`` 读取的次数）：**G 16 / H 10 / E1 1 / M8 1**。
    #: 上一轮记的 24 偏低 —— 漏了 G6/G7 的 ``_service`` 子策略（它们赋值给 ``result``
    #: 而不是 ``accounts``，按 ``accounts.`` grep 会假阴性）与 ``_h4_engineering_materials``。
    #: 🔴 这个数字**只许升不许降**；升了要同步改这里，降了说明有迁移被回退。
    REAL_CONSUMPTION_BASELINE = 28

    #: 各循环真消费的**下限**（只许升）。防「一个循环回退、另一个循环新增」互相掩盖。
    REAL_CONSUMPTION_BY_CYCLE = {"G": 16, "H": 10, "E": 1, "M": 1}

    @staticmethod
    def _real_consumers() -> list[str]:
        out = []
        for f in _all_render_strategy_files():
            src = f.read_text(encoding="utf-8")
            if "await resolve_semantic_accounts(" in src and _really_consumes(src):
                out.append(f.name)
        return sorted(out)

    def test_coverage_baseline_not_regressed(self):
        """真消费的策略数不得下降。"""
        real = self._real_consumers()
        assert len(real) >= self.REAL_CONSUMPTION_BASELINE, (
            f"真消费策略数 {len(real)} 低于基线 {self.REAL_CONSUMPTION_BASELINE}"
            " —— 有迁移被回退？\n" + "\n".join(f"  {r}" for r in real)
        )

    def test_coverage_composition_not_regressed(self):
        """按循环的真消费数不得下降（防跨循环互相掩盖）。"""
        counts: dict[str, int] = {}
        for name in self._real_consumers():
            m = re.match(r"_([a-z])\d+_", name)
            if m:
                counts[m.group(1).upper()] = counts.get(m.group(1).upper(), 0) + 1
        regressed = {c: (counts.get(c, 0), floor_)
                     for c, floor_ in self.REAL_CONSUMPTION_BY_CYCLE.items()
                     if counts.get(c, 0) < floor_}
        assert regressed == {}, (
            "以下循环的真消费数低于实证下限（实际, 下限）: " f"{regressed}\n实测分布: {counts}"
        )

    def test_total_strategy_count_stable(self):
        """涉四表策略总数稳定（新增循环时须同步更新基线并复核覆盖）。"""
        assert len(_four_table_strategies()) >= 55


# ---------------------------------------------------------------------------
# Task 31：`REAL_CONSUMPTION_BASELINE` 与「定向迁移名单」交叉锁死
# ---------------------------------------------------------------------------

#: 「已裁决不迁移」名单 = {render 策略文件名: 裁决理由}。
#:
#: 真源 = spec `semantic-account-resolver-full-rollout` 的 tasks.md
#: 「🔴 定向迁移名单（2026-08-03 实证）」表 + 各迁移任务的 ⚪ 标注。
#: 判据四档（每档都有反例被排除，详见 tasks.md）：
#:   ⚪ 已按名定位 / ⚪ client 表内一码一名且覆盖完整 /
#:   🟡 旧制码存在但金额恒 0（潜伏风险交 Task 30 数据触发守卫）/
#:   ⚪ 科目全库不存在＝业务事实 / ⚪ 无生产代码硬编码
#:
#: 🔴 **理由不得为空**。新增四表策略若既未迁移又未在此登记，`TestAdjudicationCrossLock`
#: 直接打红 —— 这条就是为了防「下个会话看到 26/59 又发起一轮批量 additive 注入」。
#: 🔴 某策略真迁移后**必须从本表移出**（否则孤儿条目检查打红），同时上调
#: `REAL_CONSUMPTION_BASELINE`。
ADJUDICATED_NOT_MIGRATED: dict[str, str] = {
    # ── F 循环 ────────────────────────────────────────────────────────────
    "_f2_inventory_main.py":
        "⚪ 已按名定位：取数真源是 classify_f2_leaf（按科目名归类），"
        "_F2_CATEGORIES[].account 源码明写「兜底/展示用」；存货域是 client 表内"
        "唯一存在一名多码的域（库存商品 1405/1406 等 6 组），故只有它必须按名归类。"
        "两处展示元数据错码已由 Task 29 改正（1410→1472 / 1412→1408）。",
    "_f1_prepayment.py":
        "⚪ client 表内一码一名：1123 预付款项；1231-04 坏账准备在 account_mapping 无映射，"
        "已由「宽前缀 1231 + 预付名称过滤」兜住（Task 10 裁决），语义解析零收益。",
    "_f3_notes_payable.py":
        "⚪ client 表内一码一名：2201 应付票据（负债类，走 report_line_accounts + "
        "gross_direction='credit'）；标准码在项目间完全一致（Task 10 裁决）。",
    "_f4_accounts_payable.py":
        "⚪ client 表内一码一名：2202 应付账款（负债类，同 F3 判据）（Task 10 裁决）。",
    "_f5_cost_of_sales.py":
        "🟡 旧制/CAS2006 双码并存：6402/6404 在活体两张余额表恒 0（旧制骨架行），"
        "6401 主营业务成本为 CAS2006 侧真码且有真余额 → 当前不少算；"
        "潜伏风险由 Task 30 数据触发守卫接管（旧制码一带非零余额即打红），不做迁移。",
    # ── I 循环 ────────────────────────────────────────────────────────────
    "_i1_intangible_assets.py":
        "⚪ client 表内一码一名：1701 无形资产 / 1702 累计摊销 / 1703 无形资产减值准备"
        "（Task 15 裁决）。",
    "_i2_development_expenditure.py":
        "⚪ 无生产代码硬编码：源码零科目码字面量，科目定位已委托 i_cycle_specs"
        "（其兜底码 1704 已按 postgres 双向对账改正）（Task 15 裁决）。",
    "_i3_goodwill.py":
        "⚪ 无生产代码硬编码：源码零科目码字面量（i_cycle_specs 兜底码 1711 已 DB 对账）"
        "（Task 15 裁决）。",
    "_i4_long_term_prepaid.py":
        "⚪ 无生产代码硬编码：源码零科目码字面量（Task 15 裁决）。",
    "_i5_other_noncurrent_assets.py":
        "⚪ 无生产代码硬编码：源码零科目码字面量；i_cycle_specs 的 I5 已撤兜底码"
        "（原 BS-039 实为资产总计，row_code 已改正 BS-037）（Task 15 裁决）。",
    "_i6_research_development_expense.py":
        "⚪ client 表内一码一名：6604 研发费用（损益类）；i_cycle_specs 的 I6 row_code"
        "原误指 IS-007（财务费用）已改正 IS-006 并关闭 report_config 兜底层（Task 15 裁决）。",
    # ── J 循环 ────────────────────────────────────────────────────────────
    "_j1_employee_compensation.py":
        "⚪ client 表内一码一名：2211 应付职工薪酬（负债类 is_liability=True）"
        "（Task 25 裁决）。",
    "_j2_defined_benefit_plan.py":
        "⚪ 已委托 spec 且换解析器会丢变体行号：J2_SPEC_BY_ENTITY 按 listed/soe 选 row_code"
        "（BS-023/BS-067 vs BS-093），2705 长期应付职工薪酬为 DB 实证真码。"
        "源码残留的 2221 只在 docstring（记录「曾取错应交税费整族」的历史），非取数路径。",
    # ── K 循环 ────────────────────────────────────────────────────────────
    "_k1_other_receivables.py":
        "⚪ client 表内一码一名：1221/1231-03/1131/1132；且 k1_account_scope 的 row_code"
        "常量被前端多处 .ts 引用，re-export 不能断（Task 18 裁决）。",
    "_k2_other_current_assets.py":
        "⚪ 科目码已收敛到单一真源：1901 为 BS-014 的 DB 实证真码，前端 k2AccountScope.ts"
        "与后端交叉锁死，12 处消费点读扁平契约 tb_source_codes（Task 18 裁决）。",
    "_k3_other_payables.py":
        "⚪ 判据 1+3：2241 在 10 个标准表 + 8 个 client 表完全一致（语义解析买不到东西）；"
        "且有 4 个纯函数读 accounts.gross / .gross_standard（ReportLineAccounts 独有字段），"
        "与已回退的 F1/F3/F4/F5 regression 完全同形（Task 18 裁决）。",
    "_k4_other_current_liabilities.py":
        "⚪ 判据 2：走 KCycleSpec.spec_for(standards) 按 listed/soe 选 row_code，"
        "semantic_spec_of() 桥接硬编码 soe → 换过去对上市项目即 regression；"
        "2301 一码一名（Task 18 裁决）。",
    "_k5_provisions.py":
        "⚪ 判据 2（同 K4）：2801 预计负债由 K5 独占认领（L7 已撤同码兜底），"
        "变体行号 BS-065 vs BS-094 由 KCycleSpec 选（Task 18 裁决；listed 侧原写 "
        "BS-068 实为其他非流动负债，已于 2026-08-05 按 report_config 对账改正）。",
    "_k6_held_for_sale.py":
        "⚪ 无科目码字面量 + 判据 2：走 K6_SPEC + report_line_accounts，"
        "listed/soe 章节结构不对称（五、11 一节 vs 八、12+八、43 两节）（Task 18 裁决）。",
    "_k7_deferred_income.py":
        "⚪ 判据 2（同 K4）：2401 递延收益一码一名，变体行号由 KCycleSpec 选（Task 18 裁决）。",
    "_k8_selling_expenses.py":
        "⚪ 损益类已走共享件：pl_occurrence + K8_SPEC（trial_balance 本期发生额权威口径）；"
        "6601 销售费用一码一名（Task 18 裁决）。",
    # ── M 循环（权益类，查 TbBalance 客户原始码）──────────────────────────
    "_m3_treasury_stock.py":
        "⚪ client 表内权益类一码一名：4201 库存股 / 4002 资本公积（client 侧实证 4201×5、"
        "4002×7 项目全部唯一命名）；查 TbBalance 用客户原始码，语义解析零收益。"
        "row_code 已由 BS-076 改正 BS-084 并关闭 report_config 兜底层（Task 22 裁决）。",
    "_m4_capital_reserve.py":
        "⚪ client 表内权益类一码一名：4002 资本公积（Task 22 裁决）。",
    "_m5_surplus_reserve.py":
        "⚪ client 表内权益类一码一名：4101 盈余公积（client 侧 8 项目全部唯一命名）"
        "（Task 22 裁决）。",
    "_m6_retained_earnings.py":
        "⚪ client 表内权益类一码一名：4104 利润分配（client 侧 8 项目；"
        "「未分配利润」只在 standard 的 320104）（Task 22 裁决）。",
    "_m7_special_reserve.py":
        "⚪ client 表内权益类一码一名：4301 专项储备（client 侧 4 项目）；"
        "row_code 已由 BS-075 改正 BS-086 并关闭 report_config 兜底层"
        "（report_config 的 BS-086 写 4103＝本年利润，是错码）（Task 22 裁决）。",
    "_m9_other_comprehensive_income.py":
        "⚪ client 表内权益类一码一名：4003 其他综合收益（client 侧 8 项目）；"
        "row_code 已由 BS-085 校正并关闭 report_config 兜底层（BS-085 写的 4102 全库零命中）"
        "（Task 22 裁决）。",
    "_m10_other_equity_instruments.py":
        "⚪ client 表内权益类一码一名：4401 其他权益工具（client 侧 5 项目）；"
        "row_code 已改正 BS-082 并关闭 report_config 兜底层（BS-082 写 4003＝其他综合收益）"
        "（Task 22 裁决）。",
    # ── N 循环 ────────────────────────────────────────────────────────────
    "_n1_deferred_tax_assets.py":
        "⚪ client 表内一码一名：1811 递延所得税资产 / 2901 递延所得税负债"
        "（两码兜底均已 DB 对账通过，Task 24）（Task 25 裁决）。",
    "_n2_taxes_payable.py":
        "⚪ client 表内一码一名：2221 应交税费；其子科目（税种）编码语义在客户间冲突，"
        "已按科目名归类（_classify_n4_subaccount 同族铁律），非语义解析能解"
        "（Task 25 裁决）。",
    "_n3_deferred_tax_liabilities.py":
        "⚪ 同 N1 域：2901 递延所得税负债，兜底码已 DB 对账通过（Task 24/25 裁决）。",
    "_n4_taxes_and_surcharges.py":
        "🟡 旧制码金额恒 0：6403 税金及附加为 CAS2006 侧真码；旧制 5xxx 段在活体"
        "trial_balance/tb_balance 实测恒 0（170 行仅 1 行非零且为白名单 3201 套期工具），"
        "故当前不少算。潜伏风险由 Task 30 数据触发守卫接管，不做迁移。",
    "_n5_income_tax_expense.py":
        "🟡 旧制码金额恒 0：6801 所得税费用为 CAS2006 侧真码，旧制对照码 5801 实测恒 0；"
        "同 N4，潜伏风险由 Task 30 数据触发守卫接管，不做迁移。",
}


def _migrated_names(files: list[Path]) -> set[str]:
    return {f.name for f in files
            if "await resolve_semantic_accounts(" in f.read_text(encoding="utf-8")
            and _really_consumes(f.read_text(encoding="utf-8"))}


def _unmigrated_names(files: list[Path]) -> set[str]:
    return {f.name for f in files} - _migrated_names(files)


#: 可核对实证的标记符（四档判据 + 「无硬编码 / 已委托 spec / 下游属性不兼容」三条附加依据）。
#: 🔴 只许因**新出现的实证形态**而扩充，不许为了让某条占位理由过关而放宽。
REASON_BASIS_MARKERS = (
    "一码一名",        # 判据②
    "按名定位",        # 判据①
    "恒 0",            # 判据③（旧制码金额恒 0）
    "全库不存在",      # 判据④（科目全库不存在＝业务事实）
    "全库零命中",
    "硬编码",          # 无生产代码硬编码
    "无科目码字面量",
    "单一真源",        # 科目码已收敛 + 前后端交叉锁死
    "变体行号",        # 换解析器会丢 listed/soe 变体
    "accounts.gross",  # 下游属性不兼容（与已回退的 F1/F3/F4/F5 同形）
    "已委托",
    "DB 对账",
)


def _reason_lacks_basis(reason: str) -> bool:
    """理由是否**未**引用任何可核对实证（True = 疑似占位）。"""
    return not any(m in (reason or "") for m in REASON_BASIS_MARKERS)


def adjudication_gaps(unmigrated: set[str], adjudicated: dict[str, str]) -> list[str]:
    """未迁移却未登记裁决理由（或理由为空白）的策略 —— 纯函数，供反向自检注入替身。"""
    gaps = []
    for name in sorted(unmigrated):
        reason = adjudicated.get(name)
        if reason is None or not reason.strip():
            gaps.append(name)
    return gaps


def adjudication_orphans(
    adjudicated: dict[str, str],
    *,
    exists,
    migrated,
) -> list[str]:
    """名单里的孤儿条目 —— 文件已不存在，或该策略其实已迁移。防名单腐烂。"""
    orphans = []
    for name in sorted(adjudicated):
        if not exists(name):
            orphans.append(f"{name}(文件不存在)")
        elif migrated(name):
            orphans.append(f"{name}(已真迁移，应移出名单并上调 REAL_CONSUMPTION_BASELINE)")
    return orphans


class TestAdjudicationCrossLock:
    """Property: 未迁移策略清单 ⊆ 定向名单里「已裁决不迁移」的集合。

    spec: semantic-account-resolver-full-rollout Task 31（_Requirements: 4.7, 5.4_）
    """

    def test_every_unmigrated_strategy_is_adjudicated(self):
        files = _four_table_strategies()
        gaps = adjudication_gaps(_unmigrated_names(files), ADJUDICATED_NOT_MIGRATED)
        assert gaps == [], (
            "以下四表策略既未真消费 semantic_account_resolver，又未在 "
            "ADJUDICATED_NOT_MIGRATED 登记裁决理由：\n"
            + "\n".join(f"  {g}" for g in gaps)
            + "\n\n二选一（不许第三条路）：\n"
            "  (a) 真迁移它（读 spec Wave 1 的执行检查清单，禁 additive 注入死代码）；\n"
            "  (b) 按 tasks.md 的四档判据做实证裁决，把**带理由**的条目加进名单。\n"
            "🔴 禁止只加空理由或「暂不迁移」这类无实证的占位。"
        )

    def test_no_orphan_adjudication_entries(self):
        """反向自检 ②：名单不得有孤儿条目（已迁移 / 文件不存在）—— 防名单腐烂。"""
        files = _four_table_strategies()
        migrated = _migrated_names(files)
        orphans = adjudication_orphans(
            ADJUDICATED_NOT_MIGRATED,
            exists=lambda n: (RENDER_DIR / n).exists(),
            migrated=lambda n: n in migrated,
        )
        assert orphans == [], (
            "ADJUDICATED_NOT_MIGRATED 有孤儿条目（登记了裁决理由但已失效）:\n"
            + "\n".join(f"  {o}" for o in orphans)
        )

    def test_every_reason_is_substantive(self):
        """理由不得为空/空白，且须给出可核对的实证（不许「暂不迁移」式占位）。"""
        thin = [f"{n}: {(r or '').strip()!r}" for n, r in ADJUDICATED_NOT_MIGRATED.items()
                if len((r or "").strip()) < 20]
        no_basis = [f"{n}: {r.strip()[:40]}..." for n, r in ADJUDICATED_NOT_MIGRATED.items()
                    if len(r.strip()) >= 20 and _reason_lacks_basis(r)]
        assert thin == [], "以下裁决理由过短/为空:\n" + "\n".join(f"  {t}" for t in thin)
        assert no_basis == [], (
            "以下裁决理由未引用任何实证判据（疑似占位）:\n"
            + "\n".join(f"  {n}" for n in no_basis)
        )

    def test_reverse_selfcheck_placeholder_reason_turns_red(self):
        """反向自检：占位式理由必须被 `_reason_lacks_basis` 判否（防判据空转）。"""
        assert _reason_lacks_basis("暂不迁移，等下个 spec 再说，本轮先放过去不做处理。") is True
        assert _reason_lacks_basis("这个循环比较复杂，风险大，先不动，以后有空再看。") is True
        assert _reason_lacks_basis(
            "⚪ client 表内一码一名：2201 应付票据，标准码在项目间完全一致。"
        ) is False

    def test_reverse_selfcheck_unadjudicated_entry_turns_red(self):
        """反向自检 ①：伪造「未迁移且未登记裁决理由」的策略必须被点名。"""
        fake_unmigrated = {"_x9_brand_new_cycle.py", "_f1_prepayment.py"}
        # 未登记 → 点名
        assert adjudication_gaps(fake_unmigrated, ADJUDICATED_NOT_MIGRATED) == [
            "_x9_brand_new_cycle.py"
        ]
        # 登记了但理由为空白 → 仍点名（空理由不算裁决）
        blank = dict(ADJUDICATED_NOT_MIGRATED, **{"_x9_brand_new_cycle.py": "   "})
        assert adjudication_gaps(fake_unmigrated, blank) == ["_x9_brand_new_cycle.py"]
        # 登记了实质理由 → 放行
        ok = dict(ADJUDICATED_NOT_MIGRATED,
                  **{"_x9_brand_new_cycle.py": "⚪ client 表内一码一名：9999 替身科目（实证）。"})
        assert adjudication_gaps(fake_unmigrated, ok) == []

    def test_reverse_selfcheck_orphan_detection_works(self):
        """反向自检 ②的判据不空转：已迁移条目与不存在文件都必须被点名。"""
        probe = {
            "_g1_trading_financial_assets.py": "（替身）假装它还没迁移",
            "_zz_never_existed.py": "（替身）文件不存在",
            "_f1_prepayment.py": "（替身）确实未迁移，应放行",
        }
        orphans = adjudication_orphans(
            probe,
            exists=lambda n: (RENDER_DIR / n).exists(),
            migrated=lambda n: n in _migrated_names(_four_table_strategies()),
        )
        assert any(o.startswith("_g1_trading_financial_assets.py") for o in orphans)
        assert any(o.startswith("_zz_never_existed.py") for o in orphans)
        assert not any(o.startswith("_f1_prepayment.py") for o in orphans)

    def test_domain_force_include_is_not_a_noop(self):
        """反向自检 ③：强制纳入的两个文件确实会被 SKIP_PATTERNS 误伤（否则该常量是死代码）。"""
        for name in DOMAIN_FORCE_INCLUDE:
            assert (RENDER_DIR / name).exists(), f"{name} 不存在，应从 FORCE_INCLUDE 移出"
            assert any(x in name for x in SKIP_PATTERNS), (
                f"{name} 已不再被 SKIP_PATTERNS 误伤，应从 DOMAIN_FORCE_INCLUDE 移出"
            )
        assert DOMAIN_FORCE_INCLUDE <= {f.name for f in _four_table_strategies()}, (
            "强制纳入的文件未出现在四表策略域内（关键词判定或文件已变）"
        )

    def test_adjudication_list_partitions_the_domain(self):
        """名单 + 真迁移 = 域全集（不留第三类，防「既不在名单也不算未迁移」的灰区）。"""
        files = _four_table_strategies()
        domain = {f.name for f in files}
        migrated = _migrated_names(files)
        assert migrated | set(ADJUDICATED_NOT_MIGRATED) == domain, (
            "域未被完整划分。\n未覆盖: "
            f"{sorted(domain - migrated - set(ADJUDICATED_NOT_MIGRATED))}\n"
            f"名单越界（不在域内）: {sorted(set(ADJUDICATED_NOT_MIGRATED) - domain)}"
        )
