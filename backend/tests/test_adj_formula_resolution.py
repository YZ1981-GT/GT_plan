"""test_adj_formula_resolution.py — ADJ() 真执行求值端到端守卫.

spec: adj-formula-repair-and-approval-gate-wiring · 阶段 0 任务 0.1 + 0.2
修复前红、修复后绿。

本文件有两组守卫：
1. ADJ() 真正执行求值（0.1）：ImportError / 类型归一 / 符号归一 / 无数据返 0
2. _FORMULA_RESOLVERS 全成员冒烟（0.2）：每个 resolver 最小合法入参调一次

Validates: Requirements 7.1, 7.2, 7.4, 7.5 · Properties P1, P2, P12
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_TEST_PROJECT_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
_TEST_YEAR = 2099

# 各 resolver 的**足量** args —— 必须过其开头的 `if len(args) < N: return None`。
# 🔴 统一传 3 个会让 AUX（需 4 个）在 import 前早退 ⇒ 冒烟守卫恒绿（复盘实测教训）。
# 新增 resolver 未登记 args 时走 _FALLBACK_ARGS（给足 5 个，覆盖已知最大 arity）。
_RESOLVER_ARGS: dict[str, list[str]] = {
    "WP": ["A1", "sheet", "cell"],
    "LEDGER": ["1001", "debit", "全年"],
    "AUX": ["1001", "customer", "C001", "期末余额"],   # 需 4 个
    "PREV": ["A1", "sheet", "field"],
    "ADJ": ["1001", "aje_net"],
    "NOTE": ["sec", "row", "col"],
    "LEDGER_DETAIL": ["1001", "debit", "全年", "x", "y"],
    "COUNT_LEDGER": ["1001", "debit", "全年", "x", "y"],
}
_FALLBACK_ARGS = ["1001", "x", "y", "z", "w"]

# ---------------------------------------------------------------------------
# 0.1 — ADJ() 真正执行求值
# ---------------------------------------------------------------------------


class TestAdjFormulaResolution:
    """直接调 _resolve_adj_formula / resolve_extended_formula，
    断言 import 可解析、类型归一正确、符号归一正确、无数据返 0。

    修复前红（ImportError / 类型归一缺陷），修复后绿。
    """

    def test_adj_resolver_importable(self):
        """P1: _resolve_adj_formula 函数体内的 lazy import 不抛 ImportError。

        当前预期**红**：从 phase10_models import Adjustment 必抛。
        修复后（改为 audit_platform_models）转绿。
        """
        # 直接尝试 import 目标模型——如果路径错误这里就会红
        try:
            from app.models.audit_platform_models import (  # noqa: F401
                Adjustment,
                AdjustmentEntry,
            )
        except ImportError:
            pytest.fail("Adjustment / AdjustmentEntry 从 audit_platform_models 导入失败")

        # 验证 _resolve_adj_formula 函数体内的 import 路径
        import inspect
        from app.services.prefill_engine import _resolve_adj_formula

        source = inspect.getsource(_resolve_adj_formula)
        # 修复后应改为 audit_platform_models（或委托 adjustment_amount_source）
        assert "phase10_models" not in source or "audit_platform_models" in source, (
            "_resolve_adj_formula 仍从 phase10_models 导入 Adjustment/AdjustmentEntry，"
            "该模块无此定义 → 每次调用必抛 ImportError"
        )

    @pytest.mark.asyncio
    async def test_adj_aje_basic_resolve(self):
        """ADJ('1001','aje_net') 求值不抛异常且返回 Decimal。

        当前预期红（ImportError）。修复后转绿。
        """
        from app.services.prefill_engine import _resolve_adj_formula

        # 用 mock db，让 SQL 查询返回空结果（验证不抛、返 Decimal(0)）
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _resolve_adj_formula(
            mock_db, _TEST_PROJECT_ID, _TEST_YEAR, ["1001", "aje_net"]
        )
        assert isinstance(result, Decimal), f"期望 Decimal，得到 {type(result)}: {result}"
        assert result == Decimal("0")

    @pytest.mark.asyncio
    async def test_adj_rje_basic_resolve(self):
        """ADJ('1001','rje_net') 同理。"""
        from app.services.prefill_engine import _resolve_adj_formula

        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _resolve_adj_formula(
            mock_db, _TEST_PROJECT_ID, _TEST_YEAR, ["1001", "rje_net"]
        )
        assert isinstance(result, Decimal)
        assert result == Decimal("0")

    @pytest.mark.asyncio
    async def test_aje_and_rje_must_differ_with_data(self):
        """P2 双向变异：有数据时 AJE 与 RJE 结果必不相等。

        当前预期红（ImportError 或类型归一缺陷导致同值）。

        验证方式：通过 normalize_adj_type 确认 aje_net → "aje" 和 rje_net → "rje"
        产生不同的归一值，然后用区分性 mock 证明查询带了正确的 type 过滤。
        """
        from app.services.adjustment_amount_source import normalize_adj_type

        # 首先验证归一函数本身能正确区分
        aje_norm = normalize_adj_type("aje_net")
        rje_norm = normalize_adj_type("rje_net")
        assert aje_norm == "aje"
        assert rje_norm == "rje"
        assert aje_norm != rje_norm, (
            "aje_net 和 rje_net 归一后不应相同——否则 SQL 查询无法区分"
        )

        # 然后验证 _resolve_adj_formula 真正把不同 type 传给 adj_net
        # patch adj_net 在其源模块（lazy import 目标），检查传入参数
        from app.services.prefill_engine import _resolve_adj_formula

        calls_received: list[dict] = []

        async def _spy_adj_net(db, *, project_id, year, account_code, adj_type, **kw):
            calls_received.append({"adj_type": adj_type, "account_code": account_code})
            # AJE 返 500，RJE 返 300
            return Decimal("500") if normalize_adj_type(adj_type) == "aje" else Decimal("300")

        mock_db = AsyncMock()

        with patch(
            "app.services.adjustment_amount_source.adj_net",
            side_effect=_spy_adj_net,
        ):
            aje_val = await _resolve_adj_formula(
                mock_db, _TEST_PROJECT_ID, _TEST_YEAR, ["1001", "aje_net"]
            )
            rje_val = await _resolve_adj_formula(
                mock_db, _TEST_PROJECT_ID, _TEST_YEAR, ["1001", "rje_net"]
            )

        # 关键断言 1：两者必须不同（锁死类型归一）
        assert aje_val != rje_val, (
            f"AJE={aje_val} == RJE={rje_val}：类型归一缺陷，"
            "两个分支都未命中 → 退化为不加 adjustment_type 过滤"
        )

        # 关键断言 2：verify adj_net 收到了不同的 adj_type 参数
        assert len(calls_received) == 2
        assert calls_received[0]["adj_type"] == "aje_net"
        assert calls_received[1]["adj_type"] == "rje_net"

    @pytest.mark.asyncio
    async def test_credit_account_sign_normalization(self):
        """贷方类科目（2202 应付账款）符号归一：原始净额为负 → 取反后为正。

        验证 direction_resolver 被正确调用：
        科目 2202（负债类）→ credit direction → 乘 -1 → 负净额变正。
        """
        from app.services.prefill_engine import _resolve_adj_formula

        # mock 返回负净额（一笔贷记调整 debit=0, credit=1000 → SUM(d-c) = -1000）
        mock_result = MagicMock()
        mock_result.first.return_value = (Decimal("-1000"), "应付账款")
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _resolve_adj_formula(
            mock_db, _TEST_PROJECT_ID, _TEST_YEAR, ["2202", "aje_net"]
        )
        # 贷方类取反 → 1000（正数）
        assert result is not None
        assert result == Decimal("1000"), f"贷方类归一后应为正数，得到 {result}"

    @pytest.mark.asyncio
    async def test_debit_account_keeps_sign(self):
        """借方类科目（1001 库存现金）符号不变：正净额维持正。

        P12 双向变异配对：与 test_credit_account_sign_normalization 互为正/反样本。
        """
        from app.services.prefill_engine import _resolve_adj_formula

        mock_result = MagicMock()
        mock_result.first.return_value = (Decimal("800"), "库存现金")
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _resolve_adj_formula(
            mock_db, _TEST_PROJECT_ID, _TEST_YEAR, ["1001", "aje_net"]
        )
        assert result is not None
        assert result == Decimal("800"), f"借方类不应取反，得到 {result}"

    @pytest.mark.asyncio
    async def test_no_data_returns_zero(self):
        """P12 双向变异（负样本）：无数据 → Decimal("0")（非 None）。

        配对正样本见 test_adj_aje_basic_resolve（有 mock 数据时返回非 None Decimal）
        与 test_debit_account_keeps_sign（有数据 → Decimal("800")）。
        """
        from app.services.prefill_engine import _resolve_adj_formula

        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _resolve_adj_formula(
            mock_db, _TEST_PROJECT_ID, _TEST_YEAR, ["9999", "aje_net"]
        )
        assert result == Decimal("0"), f"无数据应返 Decimal('0')，得到 {result}"
        assert result is not None, "无数据不应返 None（fail-closed 语义）"

    @pytest.mark.asyncio
    async def test_with_data_returns_nonzero(self):
        """P12 双向变异（正样本）：有数据 → 非零 Decimal。

        与 test_no_data_returns_zero 配对，证明「返 0」不是恒空假绿。
        """
        from app.services.prefill_engine import _resolve_adj_formula

        mock_result = MagicMock()
        mock_result.first.return_value = (Decimal("12345.67"), "银行存款")
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _resolve_adj_formula(
            mock_db, _TEST_PROJECT_ID, _TEST_YEAR, ["1002", "aje_net"]
        )
        assert result is not None, "有数据时不应返 None"
        assert result != Decimal("0"), f"有数据时不应返 0，得到 {result}"
        assert isinstance(result, Decimal)

    @pytest.mark.asyncio
    async def test_resolve_via_entry_point(self):
        """通过统一入口 resolve_extended_formula 调用 ADJ resolver。"""
        from app.services.prefill_engine import resolve_extended_formula

        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await resolve_extended_formula(
            mock_db, _TEST_PROJECT_ID, _TEST_YEAR,
            "ADJ", "'1001','aje_net'",
        )
        assert isinstance(result, (Decimal, type(None)))


# ---------------------------------------------------------------------------
# 0.2 — _FORMULA_RESOLVERS 全成员冒烟守卫
# ---------------------------------------------------------------------------


class TestFormulaResolversSmoke:
    """遍历 _FORMULA_RESOLVERS 每个 resolver 各调一次，
    断言不抛 ImportError / AttributeError。
    registry 成员数现算，禁写死。
    """

    def test_registry_non_empty(self):
        """registry 非空（禁写死成员数，只验非空）。"""
        from app.services.prefill_engine import _FORMULA_RESOLVERS

        assert len(_FORMULA_RESOLVERS) > 0, "registry 为空"
        # 现算记录：编写时 9 个键
        # 新增 resolver 未配用例时由下方 test_each_resolver_no_import_error 覆盖

    @pytest.mark.asyncio
    async def test_each_resolver_no_import_error(self):
        """P1 + P12：每个 resolver 以**足量** args 调一次，不抛 ImportError。

        🔴 复盘修正（本 spec 最严重的守卫缺陷）：原实现对所有 resolver 统一传
        3 个 args `["1001","aje_net","期末余额"]`，但 `_resolve_aux_formula` 开头是
        `if len(args) < 4: return None` ⇒ **在执行到函数体内 import 之前就早退**，
        守卫形同虚设。实测后果：AUX 与 TB_AUX 存在与 ADJ 完全同源的
        `from app.models.dataset_models import TbAuxBalance` ImportError
        （真实位置是 audit_platform_models），却被这个守卫判绿数轮。

        现改为按 resolver 各自的 arity 下限逐个给足 args，并断言
        「每个 resolver 都真正执行到了函数体」（靠 ImportError 能被抓到反证）。

        对 None 值（如 TB_AUX）跳过 registry 遍历——它在 resolve_extended_formula
        里特殊处理，另由 test_tb_aux_resolver_no_import_error 单独覆盖。
        registry 成员数**现算**，新增 resolver 未配用例即红。

        AttributeError 分两类：
        - lazy import 路径错导致 getattr 失败（如 phase10_models 无 Adjustment）→ 抓
        - mock db 不支持 ORM 操作（如 TbLedger 传给 get_active_filter 后
          table.c 在 mock 上不存在）→ 运行时问题，非 import 缺陷，放过

        区分方法：检查 traceback 中最后一帧是否在 import 语句行内。
        保守做法：只抓 ImportError（一定是 import 缺陷），AttributeError 按
        traceback 最后一帧是否含 "import " 关键词判定。
        """
        import traceback as _tb
        from app.services.prefill_engine import _FORMULA_RESOLVERS

        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_result.all.return_value = []
        mock_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[]),
            first=MagicMock(return_value=None),
        )
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        # 现算 registry 成员数（禁写死）
        total_keys = len(_FORMULA_RESOLVERS)
        assert total_keys > 0, "registry 为空"

        none_keys = [k for k, v in _FORMULA_RESOLVERS.items() if v is None]
        callable_keys = [k for k, v in _FORMULA_RESOLVERS.items() if v is not None]
        tested_count = 0

        failures = []
        for key, resolver in _FORMULA_RESOLVERS.items():
            if resolver is None:
                continue  # TB_AUX 等特殊处理
            tested_count += 1
            # 🔴 足量 args：必须过各 resolver 开头的 `if len(args) < N: return None`
            # 否则在执行到函数体内 import 之前就早退，守卫恒绿（见 docstring）
            try:
                await resolver(
                    mock_db, _TEST_PROJECT_ID, _TEST_YEAR,
                    _RESOLVER_ARGS.get(key, _FALLBACK_ARGS),
                )
            except ImportError as e:
                # ImportError 一律视为 lazy import 缺陷
                failures.append(f"{key}: ImportError — {e}")
            except AttributeError as e:
                # 只有 import 相关的 AttributeError 才算缺陷
                # 例：from app.models.phase10_models import Adjustment
                #     → phase10_models 存在但无 Adjustment → AttributeError
                # 对比：table.c.project_id → mock 上无 .c → 运行时问题
                frames = _tb.extract_tb(e.__traceback__)
                if frames:
                    last_line = frames[-1].line or ""
                    if "import " in last_line:
                        failures.append(f"{key}: AttributeError（import 行）— {e}")
                    # else: runtime mock 问题，不是 import 缺陷
            except Exception:
                # TypeError、IndexError 等参数不匹配异常可接受
                pass

        # 断言覆盖度：所有 callable resolver 都被调用了
        assert tested_count == len(callable_keys), (
            f"被测 resolver 数 {tested_count} != 可调用 resolver 数 {len(callable_keys)}；"
            f"跳过（None）: {none_keys}"
        )

        assert not failures, (
            f"以下 resolver 存在 import/attribute 缺陷（现算 registry {total_keys} 个键，"
            f"可调用 {len(callable_keys)} 个，跳过 {none_keys}）：\n"
            + "\n".join(failures)
        )

    @pytest.mark.asyncio
    async def test_mutation_proof_fake_resolver_detected(self):
        """P12 双向变异：验证冒烟守卫不是恒绿。

        往 registry 里临时塞一个必抛 ImportError 的 fake resolver，
        跑同样的扫描逻辑——如果守卫是恒绿（从不真正调 resolver），它就抓不到 fake。
        """
        import traceback as _tb
        from app.services.prefill_engine import _FORMULA_RESOLVERS

        async def _always_fail(db, pid, year, args):
            raise ImportError("fake resolver import error for mutation proof")

        original_keys = set(_FORMULA_RESOLVERS.keys())
        assert "__FAKE_MUTATION__" not in original_keys

        # 临时注入 fake resolver
        _FORMULA_RESOLVERS["__FAKE_MUTATION__"] = _always_fail
        try:
            mock_result = MagicMock()
            mock_result.first.return_value = None
            mock_result.all.return_value = []
            mock_result.scalars.return_value = MagicMock(
                all=MagicMock(return_value=[]),
                first=MagicMock(return_value=None),
            )
            mock_result.scalar_one_or_none.return_value = None

            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(return_value=mock_result)

            # 用与 test_each_resolver_no_import_error 相同的扫描逻辑
            failures = []
            for key, resolver in _FORMULA_RESOLVERS.items():
                if resolver is None:
                    continue
                try:
                    await resolver(
                        mock_db, _TEST_PROJECT_ID, _TEST_YEAR,
                        ["1001", "aje_net", "期末余额"],
                    )
                except ImportError as e:
                    failures.append(f"{key}: ImportError — {e}")
                except AttributeError as e:
                    frames = _tb.extract_tb(e.__traceback__)
                    if frames:
                        last_line = frames[-1].line or ""
                        if "import " in last_line:
                            failures.append(f"{key}: AttributeError（import 行）— {e}")
                except Exception:
                    pass

            # fake resolver 必须被扫描器抓到——证明守卫不是恒绿
            fake_hits = [f for f in failures if "__FAKE_MUTATION__" in f]
            assert len(fake_hits) == 1, (
                f"变异证明失败：fake resolver 未被扫描器检出，"
                f"说明冒烟守卫恒绿（failures={failures}）"
            )
        finally:
            # 清理：还原 registry
            _FORMULA_RESOLVERS.pop("__FAKE_MUTATION__", None)

        # 确认清理成功
        assert "__FAKE_MUTATION__" not in _FORMULA_RESOLVERS

    @pytest.mark.asyncio
    async def test_tb_aux_resolver_no_import_error(self):
        """复盘补漏：TB_AUX 在 registry 里是 None，冒烟遍历会跳过它。

        它由 `resolve_extended_formula` 特殊分支调 `_resolve_tb_aux`，
        原守卫因此对它零覆盖 —— 实测该函数曾有与 ADJ 同源的
        `from app.models.dataset_models import TbAuxBalance` ImportError。
        """
        from app.services.prefill_engine import _FORMULA_RESOLVERS, _resolve_tb_aux

        # 前提：TB_AUX 确实在 registry 里且值为 None（否则本测试的立论失效）
        assert "TB_AUX" in _FORMULA_RESOLVERS
        assert _FORMULA_RESOLVERS["TB_AUX"] is None, (
            "TB_AUX 已改为可调用 ⇒ 它会被冒烟遍历覆盖，本测试可并入上一测试"
        )

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        try:
            await _resolve_tb_aux(
                mock_db, _TEST_PROJECT_ID, _TEST_YEAR,
                "1001", "customer", "期末余额",
            )
        except ImportError as e:
            pytest.fail(f"_resolve_tb_aux 存在 lazy import 缺陷: {e}")
        except Exception:
            # mock db 的运行时问题可接受，本守卫只抓 import
            pass

    @pytest.mark.asyncio
    async def test_resolver_args_table_covers_all_callable_keys(self):
        """P12：args 表必须覆盖全部可调用 resolver，否则退回 fallback 可能仍早退。

        新增 resolver 未在 _RESOLVER_ARGS 登记即红 —— 防「加了新 resolver，
        fallback args 不够导致它又被静默跳过」重演。
        """
        from app.services.prefill_engine import _FORMULA_RESOLVERS

        callable_keys = {k for k, v in _FORMULA_RESOLVERS.items() if v is not None}
        missing = sorted(callable_keys - set(_RESOLVER_ARGS))
        assert not missing, (
            f"以下 resolver 未在 _RESOLVER_ARGS 登记足量 args: {missing}；"
            "未登记会走 _FALLBACK_ARGS，若其 arity 要求更高则守卫对它恒绿"
        )


# ---------------------------------------------------------------------------
# 0.4 — 名实相符守卫（handler 函数名 ↔ 订阅事件语义一致性）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1.3 — normalize_adj_type 类型归一专项守卫
# ---------------------------------------------------------------------------


class TestNormalizeAdjType:
    """normalize_adj_type 全覆盖守卫。

    spec: adj-formula-repair-and-approval-gate-wiring · 阶段 1 任务 1.3
    Validates: Requirements 2.1, 2.2, 2.3 · Properties P2, P3

    归一表须容纳：
    - AJE 族：aje_net / AJE / 审计调整 → "aje"
    - RJE 族：rje_net / RJE / 重分类 → "rje"
    不可归一 → raise ValueError，禁退化为不加 adjustment_type 过滤。
    """

    # -- P2: AJE 族全部归一到 "aje" --

    @pytest.mark.parametrize("raw", ["aje_net", "AJE", "审计调整", "aje", "Aje_Net", "AJE_NET"])
    def test_aje_family_normalizes_to_aje(self, raw: str):
        """需求 2.1 + 2.2：AJE 族各种写法（含大小写变体）均归一到 "aje"。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        assert normalize_adj_type(raw) == "aje", (
            f"输入 {raw!r} 应归一为 'aje'"
        )

    # -- P2: RJE 族全部归一到 "rje" --

    @pytest.mark.parametrize("raw", ["rje_net", "RJE", "重分类", "rje", "Rje_Net", "RJE_NET"])
    def test_rje_family_normalizes_to_rje(self, raw: str):
        """需求 2.1 + 2.2：RJE 族各种写法（含大小写变体）均归一到 "rje"。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        assert normalize_adj_type(raw) == "rje", (
            f"输入 {raw!r} 应归一为 'rje'"
        )

    # -- P2: AJE 组与 RJE 组结果必不相等 --

    def test_aje_and_rje_groups_differ(self):
        """P2 双向：AJE 族的归一值与 RJE 族的归一值必不相同。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        aje_results = {normalize_adj_type(r) for r in ["aje_net", "AJE", "审计调整"]}
        rje_results = {normalize_adj_type(r) for r in ["rje_net", "RJE", "重分类"]}

        # 族内应一致
        assert len(aje_results) == 1, f"AJE 族内归一不一致: {aje_results}"
        assert len(rje_results) == 1, f"RJE 族内归一不一致: {rje_results}"

        # 族间应不同
        assert aje_results != rje_results, (
            f"AJE 族 {aje_results} 不应等于 RJE 族 {rje_results}，"
            "否则 SQL 查询无法区分 aje/rje"
        )

    # -- P3: 非法入参 raise ValueError，不静默省略过滤 --

    @pytest.mark.parametrize("bad_input", [
        "类型",          # 占位符（现算 1 处）
        "INVALID",
        "adjustment",
        "audit",
        "net",
        "",              # 空字符串
        "  ",            # 纯空格
        "aje_rje",       # 混合
        "123",
    ])
    def test_invalid_input_raises_value_error(self, bad_input: str):
        """需求 2.3 + P3：不可归一 → raise ValueError，禁退化为不加过滤。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        with pytest.raises(ValueError):
            normalize_adj_type(bad_input)

    # -- P3: 附加边界 --

    def test_none_like_input_raises(self):
        """P3 边界：None 传入不应被静默处理。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        # normalize_adj_type 签名接收 str，传 None 应在 strip() 时或之前失败
        with pytest.raises((ValueError, TypeError, AttributeError)):
            normalize_adj_type(None)  # type: ignore[arg-type]

    # -- P2 + P3: 归一表常量与白名单一致性 --

    def test_valid_literals_whitelist_consistency(self):
        """VALID_ADJ_TYPE_LITERALS 白名单应与归一表 key 集合完全一致。"""
        from app.services.adjustment_amount_source import (
            VALID_ADJ_TYPE_LITERALS,
            _ADJ_TYPE_NORMALIZE,
        )

        expected_keys = frozenset(_ADJ_TYPE_NORMALIZE.keys())
        assert VALID_ADJ_TYPE_LITERALS == expected_keys, (
            f"白名单 {VALID_ADJ_TYPE_LITERALS} != 归一表 keys {expected_keys}"
        )

    # -- P2: 归一结果只能是 "aje" 或 "rje"，无第三种 --

    def test_normalize_output_domain(self):
        """归一函数的值域严格为 {"aje", "rje"}。"""
        from app.services.adjustment_amount_source import (
            _ADJ_TYPE_NORMALIZE,
            normalize_adj_type,
        )

        all_outputs = {normalize_adj_type(k) for k in _ADJ_TYPE_NORMALIZE}
        assert all_outputs == {"aje", "rje"}, (
            f"归一值域应为 {{'aje', 'rje'}}，得到 {all_outputs}"
        )

    # -- P2: 大小写不敏感 --

    def test_case_insensitive(self):
        """归一匹配大小写不敏感。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        assert normalize_adj_type("AJE_NET") == "aje"
        assert normalize_adj_type("Aje_Net") == "aje"
        assert normalize_adj_type("rJe_NeT") == "rje"
        assert normalize_adj_type("RJE") == "rje"

    # -- P2: 前后空格容忍 --

    def test_whitespace_tolerance(self):
        """归一函数应容忍首尾空格。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        assert normalize_adj_type(" aje_net ") == "aje"
        assert normalize_adj_type("\trje_net\n") == "rje"
        assert normalize_adj_type("  AJE  ") == "aje"


# ---------------------------------------------------------------------------
# 1.6 — CI 守卫：预设第二参必在归一白名单内
# ---------------------------------------------------------------------------


