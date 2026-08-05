"""抽样评价持久化守卫（sampling-compliance-closure Wave 1 Task 4）

背景：CAS 1314 的样本评价输出（推断错报 / 高值层已知错报 / 基本准备 / 增量准备 /
错报上限 / 偏差笔数 / 总体结论）此前只存在于前端裸 ref，抽凭 dialog 一律
destroy-on-close → 关弹窗即丢。本文件锁定评价落库的归一化与合并语义。

Validates: Requirements 2.1, 2.3, 2.4, 7.2
Properties: Property 3, Property 4
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.routers.voucher_sampling import (
    _EVAL_AMOUNT_KEYS,
    _EVAL_CONCLUSION_CODES,
    _EVAL_COUNT_KEYS,
    _EVAL_PRESERVE_KEYS,
    _normalize_evaluation,
    merge_evaluation_into_criteria,
)

_ROUTER_PATH = (
    Path(__file__).resolve().parent.parent / "app" / "routers" / "voucher_sampling.py"
)
_ROUTER_SRC = _ROUTER_PATH.read_text(encoding="utf-8")

_ACTOR = uuid4()

_FULL_PAYLOAD = {
    "projected": "12345.678",
    "known_high_value": "5000",
    "basic_precision": "8000.00",
    "incremental_allowance": "1200.5",
    "upper_limit": "21546.18",
    "tolerable_misstatement": "500000",
    "checked_sample_count": 23,
    "unchecked_sample_count": 2,
    "deviation_count": 3,
    "conclusion_code": "acceptable",
    "conclusion_message": "错报上限低于可容忍错报，总体可接受",
    "conclusion_confirmed": True,
    "algo_version": "cas1314-poisson-v1",
}


# ─── 归一化：金额 / 计数 / 结论代码 / 白名单 ──────────────────────────────────


class TestNormalizeEvaluation:
    def test_amounts_become_two_decimal_strings(self):
        out = _normalize_evaluation(_FULL_PAYLOAD, actor_id=_ACTOR)
        assert out["projected"] == "12345.68"          # 四舍五入到分
        assert out["known_high_value"] == "5000.00"    # 整数补两位
        assert out["incremental_allowance"] == "1200.50"
        for key in _EVAL_AMOUNT_KEYS:
            assert isinstance(out[key], str)
            assert "." in out[key] and len(out[key].split(".")[1]) == 2

    def test_invalid_amount_falls_back_to_zero_not_raise(self):
        """评价是审计师成果：单字段格式问题不得让整条评价丢弃。"""
        out = _normalize_evaluation(
            {"projected": "abc", "upper_limit": None, "basic_precision": {}},
            actor_id=_ACTOR,
        )
        assert out["projected"] == "0.00"
        assert out["upper_limit"] == "0.00"
        assert out["basic_precision"] == "0.00"

    def test_counts_are_non_negative_ints(self):
        out = _normalize_evaluation(
            {"checked_sample_count": "7", "deviation_count": -5, "unchecked_sample_count": "x"},
            actor_id=_ACTOR,
        )
        assert out["checked_sample_count"] == 7
        assert out["deviation_count"] == 0    # 负数归零
        assert out["unchecked_sample_count"] == 0
        for key in _EVAL_COUNT_KEYS:
            assert isinstance(out[key], int) and out[key] >= 0

    def test_conclusion_code_domain(self):
        for code in _EVAL_CONCLUSION_CODES:
            out = _normalize_evaluation({"conclusion_code": code}, actor_id=_ACTOR)
            assert out["conclusion_code"] == code
        for bad in ("", "OK", "acceptable ", None, 123):
            out = _normalize_evaluation({"conclusion_code": bad}, actor_id=_ACTOR)
            assert out["conclusion_code"] == "undetermined"

    def test_unknown_keys_dropped(self):
        out = _normalize_evaluation(
            {**_FULL_PAYLOAD, "hacked": "x", "__proto__": "y", "sample_rows": [1, 2]},
            actor_id=_ACTOR,
        )
        assert "hacked" not in out
        assert "__proto__" not in out
        assert "sample_rows" not in out

    def test_server_overrides_actor_and_time(self):
        """客户端传的 evaluated_by / evaluated_at 不可信，一律服务端覆盖。"""
        fake_actor = uuid4()
        out = _normalize_evaluation(
            {**_FULL_PAYLOAD, "evaluated_by": str(fake_actor), "evaluated_at": "1999-01-01"},
            actor_id=_ACTOR,
        )
        assert out["evaluated_by"] == str(_ACTOR)
        assert out["evaluated_by"] != str(fake_actor)
        assert out["evaluated_at"].startswith("20")

    def test_non_dict_payload_yields_full_shape(self):
        for bad in (None, "x", 5, [1]):
            out = _normalize_evaluation(bad, actor_id=_ACTOR)
            for key in (*_EVAL_AMOUNT_KEYS, *_EVAL_COUNT_KEYS):
                assert key in out


class TestA13MarkerPreservation:
    """a13_pushed_at / a13_misstatement_id 未提供时必须保留既有值。

    persistEvaluation() 在每次推断变化时都会调用且不带这两个键；若按"未提供即清空"
    处理，已推送标记会被抹掉 → 同一批次可被反复推入错报汇总（重复计入）。
    """

    def test_preserved_when_absent(self):
        prev = {"a13_pushed_at": "2026-08-04T10:00:00Z", "a13_misstatement_id": "abc"}
        out = _normalize_evaluation(_FULL_PAYLOAD, actor_id=_ACTOR, existing=prev)
        assert out["a13_pushed_at"] == "2026-08-04T10:00:00Z"
        assert out["a13_misstatement_id"] == "abc"

    def test_explicit_value_wins(self):
        prev = {"a13_pushed_at": "2026-08-04T10:00:00Z"}
        out = _normalize_evaluation(
            {**_FULL_PAYLOAD, "a13_pushed_at": "2026-08-05T11:00:00Z"},
            actor_id=_ACTOR,
            existing=prev,
        )
        assert out["a13_pushed_at"] == "2026-08-05T11:00:00Z"

    def test_none_when_no_history(self):
        out = _normalize_evaluation(_FULL_PAYLOAD, actor_id=_ACTOR)
        for key in _EVAL_PRESERVE_KEYS:
            assert out[key] is None

    def test_reverse_selfcheck_naive_impl_would_wipe_marker(self):
        """反向自检：朴素实现（只读 src）会把既有标记清成 None。"""
        prev = {"a13_pushed_at": "2026-08-04T10:00:00Z"}
        naive = {k: _FULL_PAYLOAD.get(k) for k in _EVAL_PRESERVE_KEYS}
        assert naive["a13_pushed_at"] is None       # 朴素实现丢标记
        out = _normalize_evaluation(_FULL_PAYLOAD, actor_id=_ACTOR, existing=prev)
        assert out["a13_pushed_at"] is not None     # 现实现保留


# ─── Property 3：幂等 + 只影响 evaluation 一个 key ───────────────────────────


class TestMergeSemantics:
    def _criteria(self) -> dict:
        return {
            "sampling_method": "mus",
            "random_seed": 424242,
            "dataset_id": "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49",
            "filled_voucher_nos": ["V001", "V002"],
            "filled_unit_ids": ["11", "22"],
            "filters": {"account_codes": ["1122"], "period_range": [1, 12]},
            "conclusion": "总体可接受",
        }

    def test_other_keys_byte_for_byte_preserved(self):
        before = self._criteria()
        out = merge_evaluation_into_criteria(
            before, _normalize_evaluation(_FULL_PAYLOAD, actor_id=_ACTOR)
        )
        for key, val in before.items():
            assert out[key] == val, f"{key} 被评价写入破坏"

    def test_returns_new_dict_not_mutating_input(self):
        """JSONB 原地 mutate 不触发 SQLAlchemy 脏检测 → 必须返回新 dict。"""
        before = self._criteria()
        snapshot = dict(before)
        out = merge_evaluation_into_criteria(before, {"projected": "1.00"})
        assert out is not before
        assert before == snapshot          # 入参未被修改
        assert "evaluation" not in before

    def test_idempotent_except_evaluated_at(self):
        """Property 3：同一载荷连续两次归一，除 evaluated_at 外逐字节相同。"""
        first = _normalize_evaluation(_FULL_PAYLOAD, actor_id=_ACTOR)
        second = _normalize_evaluation(_FULL_PAYLOAD, actor_id=_ACTOR, existing=first)
        a = {k: v for k, v in first.items() if k != "evaluated_at"}
        b = {k: v for k, v in second.items() if k != "evaluated_at"}
        assert a == b

    def test_non_dict_existing_tolerated(self):
        assert merge_evaluation_into_criteria(None, {"x": 1}) == {"evaluation": {"x": 1}}
        assert merge_evaluation_into_criteria("junk", {"x": 1}) == {"evaluation": {"x": 1}}


# ─── Property 4：授权先于任何写入 ───────────────────────────────────────────


def _slice_func(src: str, name: str) -> str:
    lines = src.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"async def {name}(") or line.startswith(f"def {name}("):
            start = i
            break
    assert start is not None, f"未找到函数 {name}（切片失效 → 断言会空转）"
    out = [lines[start]]
    for line in lines[start + 1 :]:
        if line and not line[0].isspace() and not line.startswith(")"):
            break
        out.append(line)
    return "\n".join(out)


class TestAuthorizationOrdering:
    def test_endpoint_body_found(self):
        body = _slice_func(_ROUTER_SRC, "voucher_evaluation")
        assert "extraction_criteria" in body, "切片没拿到端点体 → 下面断言会空转"

    def test_authorize_before_any_write(self):
        body = _slice_func(_ROUTER_SRC, "voucher_evaluation")
        auth_at = body.index("_authorize_and_validate_evaluation")
        write_at = body.index("log.extraction_criteria =")
        assert auth_at < write_at, "授权必须先于 ORM 赋值"
        resolve_at = body.index("_resolve_target_log")
        assert auth_at < resolve_at, "授权必须先于目标批次查询"

    def test_authorize_not_wrapped_in_try(self):
        """授权置于 try 之外：否则 403/404 会被 except 吞成 500（平台已有同类踩坑）。"""
        body = _slice_func(_ROUTER_SRC, "voucher_evaluation")
        auth_at = body.index("_authorize_and_validate_evaluation")
        assert "try:" not in body[:auth_at]

    def test_authorize_checks_cross_project(self):
        body = _slice_func(_ROUTER_SRC, "_authorize_and_validate_evaluation")
        assert "authorize_wp_edit" in body
        assert "status_code=403" in body

    def test_target_log_scoped_to_workpaper(self):
        """显式 log_id 也必须校验归属该底稿，否则可跨底稿改别人的评价。"""
        body = _slice_func(_ROUTER_SRC, "_resolve_target_log")
        assert "WorkpaperExtractionLog.workpaper_id == workpaper_id" in body
        assert "status_code=404" in body
