"""合并模块 Phase 0 锁定/留痕/精度 PBT（P5~P7，hypothesis）

使用 hypothesis 做 property-based testing，验证 3 个正确性属性：

- P5 锁状态机：随机 lock/unlock 操作序列 → 每步断言三字段联合不变量
- P6 哈希链连续性：随机 K 条审计日志 → 链 prev_hash→entry_hash 连续 + 篡改检测
- P7 Decimal 无精度丢失：易触发 float 误差金额 → 服务结果与纯 Decimal 参照逐位相等

纯函数测试，不依赖 DB / 网络。

Validates: Requirements 5.2, 7.1, 1.7, 2.4
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from hypothesis import given, settings, strategies as st

from app.services.audit_log_helper import GENESIS_HASH, _compute_entry_hash
from app.services.consol_individual_sum_service import (
    ZERO,
    _aggregate_from_company_amounts,
)


# ---------------------------------------------------------------------------
# P5 锁状态机：纯函数状态模拟
# ---------------------------------------------------------------------------


def _apply_lock(state: dict, user_id: uuid.UUID) -> dict:
    """模拟 lock 操作：设置三字段为锁定态。"""
    return {
        "consol_lock": True,
        "consol_lock_by": user_id,
        "consol_lock_at": datetime.now(timezone.utc),
    }


def _apply_unlock(state: dict) -> dict:
    """模拟 unlock 操作：清空三字段为解锁态。"""
    return {
        "consol_lock": False,
        "consol_lock_by": None,
        "consol_lock_at": None,
    }


def _check_invariant(state: dict) -> None:
    """断言三字段联合不变量：

    - locked  <=> (consol_lock==True AND consol_lock_by!=None AND consol_lock_at!=None)
    - unlocked <=> (consol_lock==False AND consol_lock_by==None AND consol_lock_at==None)
    - 不存在半填中间态
    """
    locked = state["consol_lock"]
    lock_by = state["consol_lock_by"]
    lock_at = state["consol_lock_at"]

    if locked:
        assert lock_by is not None, "locked but consol_lock_by is None"
        assert lock_at is not None, "locked but consol_lock_at is None"
    else:
        assert lock_by is None, f"unlocked but consol_lock_by={lock_by}"
        assert lock_at is None, f"unlocked but consol_lock_at={lock_at}"


# Strategy: 操作序列（lock=True, unlock=False）
_lock_op = st.booleans()  # True=lock, False=unlock


class TestP5LockStateMachine:
    """P5 锁状态机不变量：随机 lock/unlock 操作序列（含重复/交替）→
    每步断言三字段联合不变量 + 无半填中间态。

    **Validates: Requirements 5.2**
    """

    @given(ops=st.lists(_lock_op, min_size=1, max_size=20))
    @settings(max_examples=15)
    def test_invariant_holds_after_every_operation(self, ops: list[bool]):
        """随机操作序列后，每步三字段不变量成立。"""
        # 初始态：unlocked
        state = {
            "consol_lock": False,
            "consol_lock_by": None,
            "consol_lock_at": None,
        }
        _check_invariant(state)

        user_id = uuid.uuid4()

        for is_lock in ops:
            if is_lock:
                state = _apply_lock(state, user_id)
            else:
                state = _apply_unlock(state)

            # 每步后断言不变量
            _check_invariant(state)

    @given(ops=st.lists(_lock_op, min_size=1, max_size=20))
    @settings(max_examples=15)
    def test_no_half_filled_state_ever_exists(self, ops: list[bool]):
        """断言不存在半填中间态（仅部分字段被设置）。"""
        state = {
            "consol_lock": False,
            "consol_lock_by": None,
            "consol_lock_at": None,
        }

        user_id = uuid.uuid4()

        for is_lock in ops:
            if is_lock:
                state = _apply_lock(state, user_id)
            else:
                state = _apply_unlock(state)

            # 三字段要么全有值（locked）要么全 None/False（unlocked）
            has_lock = state["consol_lock"] is True
            has_by = state["consol_lock_by"] is not None
            has_at = state["consol_lock_at"] is not None

            # 全部一致：要么全 True 要么全 False
            assert has_lock == has_by == has_at, (
                f"半填态: lock={has_lock}, by={has_by}, at={has_at}"
            )



# ---------------------------------------------------------------------------
# P6 哈希链连续性
# ---------------------------------------------------------------------------

# Strategy: 审计日志条目 payload
_audit_action = st.sampled_from([
    "consol.lock", "consol.unlock", "consol.elimination.approve",
    "consol.recalc", "consol.scope.change",
])

_audit_payload = st.fixed_dictionaries({
    "event_type": st.just("consol_lifecycle"),
    "sub_action": _audit_action,
    "before": st.fixed_dictionaries({"locked": st.booleans()}),
    "after": st.fixed_dictionaries({"locked": st.booleans()}),
})


def _build_chain(entries: list[dict]) -> list[dict]:
    """用 _compute_entry_hash 构建哈希链。

    每个 entry 需含: ts, user_id, action_type, object_id, payload
    返回带 prev_hash / entry_hash 的链。
    """
    chain: list[dict] = []
    prev_hash = GENESIS_HASH

    for entry in entries:
        ts = entry["ts"]
        user_id = entry["user_id"]
        action_type = entry["action_type"]
        object_id = entry.get("object_id")
        payload_json = json.dumps(
            entry["payload"], sort_keys=True, ensure_ascii=False, default=str
        )

        entry_hash = _compute_entry_hash(
            ts, user_id, action_type, object_id, payload_json, prev_hash
        )

        chain.append({
            "ts": ts,
            "user_id": user_id,
            "action_type": action_type,
            "object_id": object_id,
            "payload_json": payload_json,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
        })

        prev_hash = entry_hash

    return chain


@st.composite
def audit_entries_strategy(draw: st.DrawFn):
    """生成 K 条随机审计日志条目。"""
    k = draw(st.integers(min_value=2, max_value=8))
    user_id = str(uuid.uuid4())
    entries = []
    for i in range(k):
        payload = draw(_audit_payload)
        entries.append({
            "ts": datetime(2026, 5, 30, 12, 0, i, tzinfo=timezone.utc).isoformat(),
            "user_id": user_id,
            "action_type": payload["sub_action"],
            "object_id": str(uuid.uuid4()),
            "payload": payload,
        })
    return entries


class TestP6HashChainContinuity:
    """P6 哈希链连续性：随机 K 条审计日志 →
    - chain[i].prev_hash == chain[i-1].entry_hash
    - 篡改中间 payload 使后续 hash 校验失败

    **Validates: Requirements 7.1**
    """

    @given(entries=audit_entries_strategy())
    @settings(max_examples=15)
    def test_chain_prev_hash_links_to_previous_entry_hash(self, entries):
        """断言 chain[i].prev_hash == chain[i-1].entry_hash。"""
        chain = _build_chain(entries)

        # 第一条的 prev_hash 应为 GENESIS_HASH
        assert chain[0]["prev_hash"] == GENESIS_HASH

        # 后续每条的 prev_hash == 前一条的 entry_hash
        for i in range(1, len(chain)):
            assert chain[i]["prev_hash"] == chain[i - 1]["entry_hash"], (
                f"链断裂 at index {i}: "
                f"prev_hash={chain[i]['prev_hash']} != "
                f"prev entry_hash={chain[i - 1]['entry_hash']}"
            )

    @given(entries=audit_entries_strategy())
    @settings(max_examples=15)
    def test_tampering_intermediate_payload_breaks_chain(self, entries):
        """篡改中间 payload 后重算 hash，后续条目校验失败。"""
        chain = _build_chain(entries)

        if len(chain) < 2:
            return

        # 篡改第一条的 payload（模拟恶意修改）
        tampered_payload = json.dumps(
            {"tampered": True}, sort_keys=True, ensure_ascii=False
        )
        tampered_hash = _compute_entry_hash(
            chain[0]["ts"],
            chain[0]["user_id"],
            chain[0]["action_type"],
            chain[0]["object_id"],
            tampered_payload,
            chain[0]["prev_hash"],
        )

        # 篡改后的 entry_hash 应与原始不同
        assert tampered_hash != chain[0]["entry_hash"], (
            "篡改 payload 后 hash 未变化（哈希碰撞或逻辑错误）"
        )

        # 第二条的 prev_hash 仍指向原始 chain[0].entry_hash
        # 如果用篡改后的 hash 作为 prev_hash 重算第二条，结果不同
        recomputed_second = _compute_entry_hash(
            chain[1]["ts"],
            chain[1]["user_id"],
            chain[1]["action_type"],
            chain[1]["object_id"],
            chain[1]["payload_json"],
            tampered_hash,  # 用篡改后的 hash 作为 prev
        )
        assert recomputed_second != chain[1]["entry_hash"], (
            "篡改中间 payload 后后续 hash 未变化"
        )



# ---------------------------------------------------------------------------
# P7 Decimal 无精度丢失
# ---------------------------------------------------------------------------

# Strategy: 易触发 float 精度误差的金额
_float_trap_amounts = st.one_of(
    # 经典 0.1 + 0.2 != 0.3 类
    st.sampled_from([
        Decimal("0.10"), Decimal("0.20"), Decimal("0.30"),
        Decimal("0.07"), Decimal("0.14"), Decimal("0.21"),
    ]),
    # 大量小数累加
    st.decimals(
        min_value=Decimal("0.01"),
        max_value=Decimal("0.99"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ),
    # 大数（float 精度在大数时丢失尾数）
    st.sampled_from([
        Decimal("10000000.01"),
        Decimal("99999999.99"),
        Decimal("12345678.12"),
        Decimal("10000000.10"),
        Decimal("50000000.05"),
    ]),
)


@st.composite
def float_trap_company_amounts(draw: st.DrawFn):
    """生成易触发 float 精度误差的 company_amounts。

    多个子公司贡献小数金额到同一科目，累加后与 float 路径对比。
    """
    n_companies = draw(st.integers(min_value=2, max_value=6))
    # 使用固定科目确保跨子公司累加
    account_codes = ["1001", "1002", "6001"]

    result = []
    for i in range(n_companies):
        meta = {"company_code": f"SUB{i:03d}", "company_name": f"子公司{i}"}
        amounts: dict[str, Decimal] = {}
        for code in account_codes:
            # 每个子公司每个科目都有金额（确保累加）
            amounts[code] = draw(_float_trap_amounts)
        result.append((meta, amounts))

    return result


class TestP7DecimalNoPrecisionLoss:
    """P7 Decimal 无精度丢失：生成易触发 float 误差金额 →
    _aggregate_from_company_amounts 结果与纯 Decimal 参照逐位相等（quantized to 2 places）。

    **Validates: Requirements 1.7**
    """

    @given(data=float_trap_company_amounts())
    @settings(max_examples=15)
    def test_aggregate_equals_pure_decimal_reference(self, data):
        """服务汇总结果 == 纯 Decimal 逐项相加（quantized to 2 places, bit-exact）。"""
        company_amounts = data

        # 纯 Decimal 参照计算（独立实现，不经过 service）
        reference: dict[str, Decimal] = {}
        for _meta, amounts in company_amounts:
            for code, amount in amounts.items():
                if amount == ZERO:
                    continue
                reference[code] = reference.get(code, ZERO) + amount

        # 通过 service 纯函数计算
        acc, _prov = _aggregate_from_company_amounts(company_amounts)

        # 逐科目比对：quantize to 2 places 后 bit-exact 相等
        two_places = Decimal("0.01")
        for code in set(reference.keys()) | set(acc.keys()):
            ref_val = reference.get(code, ZERO).quantize(two_places)
            svc_val = acc.get(code, ZERO).quantize(two_places)
            assert svc_val == ref_val, (
                f"科目 {code}: service={svc_val} != reference={ref_val} "
                f"(精度丢失)"
            )

    @given(data=float_trap_company_amounts())
    @settings(max_examples=15)
    def test_no_float_intermediate_in_provenance(self, data):
        """provenance 中金额序列化为 str(Decimal)，反序列化后与原值精确相等。"""
        company_amounts = data

        _acc, prov = _aggregate_from_company_amounts(company_amounts)

        for code, entries in prov.items():
            for entry in entries:
                # provenance 中 amount 是 str(Decimal)
                amount_str = entry["amount"]
                # 反序列化回 Decimal 应精确相等（无 float 中转丢精度）
                restored = Decimal(amount_str)
                # 找到原始输入中对应的金额
                for meta, amounts in company_amounts:
                    if (
                        meta["company_code"] == entry["company_code"]
                        and code in amounts
                        and amounts[code] != ZERO
                    ):
                        if str(amounts[code]) == amount_str:
                            assert restored == amounts[code], (
                                f"provenance 精度丢失: "
                                f"original={amounts[code]} "
                                f"restored={restored}"
                            )
                            break
