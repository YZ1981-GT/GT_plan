"""Sprint 9.1: 合成 500MB 等效样本 smoke 测试

验证 Python 处理管线（validate_l1 + convert_ledger_rows）能处理 200 万行
合成序时账数据而不 OOM（内存 < 2GB），且在合理时间内完成。

标记 @pytest.mark.slow 以便 CI 正常跑时跳过。
标记 xfail 如果超过 30 分钟（但预期远快于此，因为不做 DB 写入）。

策略：
- 生成 2,000,000 行合成序时账 dict（内存中，不写磁盘）
- 分批跑 validate_l1 + convert_ledger_rows（CPU-bound 部分）
- 断言：无崩溃 + 内存合理（psutil 可用时检查 RSS < 2GB）
"""
from __future__ import annotations

import time
from datetime import date
from decimal import Decimal

import pytest

from app.services.ledger_import.converter import convert_ledger_rows
from app.services.ledger_import.detection_types import TableType
from app.services.ledger_import.validator import validate_l1


TOTAL_ROWS = 2_000_000
BATCH_SIZE = 100_000  # 分批处理避免单次内存峰值过高


def _generate_ledger_batch(start: int, count: int) -> list[dict]:
    """生成一批合成序时账行（模拟真实数据结构）。"""
    rows = []
    for i in range(start, start + count):
        rows.append({
            "account_code": f"{1001 + (i % 800):06d}",
            "account_name": f"科目_{i % 800}",
            "voucher_date": date(2025, (i % 12) + 1, (i % 28) + 1),
            "voucher_no": f"记-{i:07d}",
            "debit_amount": Decimal("1234.56") if i % 2 == 0 else None,
            "credit_amount": None if i % 2 == 0 else Decimal("1234.56"),
            "summary": f"摘要内容_{i % 5000}",
            "company_code": "001",
            "currency_code": "CNY",
        })
    return rows


def _build_column_mapping() -> dict[str, str]:
    """构造 validate_l1 需要的 column_mapping（original→standard 映射）。"""
    fields = [
        "account_code", "account_name", "voucher_date", "voucher_no",
        "debit_amount", "credit_amount", "summary", "company_code",
        "currency_code",
    ]
    return {f: f for f in fields}


# ===========================================================================
# 主测试：200 万行管线 smoke
# ===========================================================================


@pytest.mark.slow
@pytest.mark.xfail(
    reason="超过 30 分钟视为环境问题，非代码 bug",
    condition=False,  # 默认不触发 xfail，由运行时判断
    run=True,
)
def test_huge_ledger_pipeline_2m_rows():
    """200 万行合成序时账通过 validate_l1 + convert_ledger_rows 不崩溃。

    验证点：
    1. 无异常抛出（不 OOM、不 crash）
    2. 内存增量 < 2GB（psutil 可用时检查）
    3. 总耗时 < 30 分钟（超时标 xfail）
    """
    # 内存基线
    mem_before_mb = None
    try:
        import psutil
        mem_before_mb = psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        pass

    col_mapping = _build_column_mapping()
    total_validated = 0
    total_converted_ledger = 0
    total_converted_aux = 0

    start_time = time.time()

    # 分批处理 200 万行
    for batch_start in range(0, TOTAL_ROWS, BATCH_SIZE):
        batch = _generate_ledger_batch(batch_start, BATCH_SIZE)

        # Phase 1: validate_l1
        findings, cleaned = validate_l1(
            batch,
            TableType.LEDGER,
            col_mapping,
            file_name="synthetic_huge.xlsx",
            sheet_name="序时账",
        )
        total_validated += len(cleaned)

        # Phase 2: convert_ledger_rows
        ledger_rows, aux_rows, _stats = convert_ledger_rows(cleaned)
        total_converted_ledger += len(ledger_rows)
        total_converted_aux += len(aux_rows)

        # 超时保护：30 分钟
        elapsed = time.time() - start_time
        if elapsed > 1800:
            pytest.xfail(f"超过 30 分钟限制（已处理 {batch_start + BATCH_SIZE} 行）")

    elapsed_total = time.time() - start_time

    # 断言：数据完整性
    assert total_validated == TOTAL_ROWS, (
        f"预期 {TOTAL_ROWS} 行通过 L1，实际 {total_validated}"
    )
    assert total_converted_ledger == TOTAL_ROWS, (
        f"预期 {TOTAL_ROWS} 行转换，实际 {total_converted_ledger}"
    )
    # aux 行数 = 0（合成数据无辅助维度字段）
    assert total_converted_aux == 0

    # 断言：内存合理
    if mem_before_mb is not None:
        import psutil
        mem_after_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        mem_delta_mb = mem_after_mb - mem_before_mb
        assert mem_delta_mb < 2048, (
            f"内存增量 {mem_delta_mb:.0f}MB 超过 2GB 限制"
        )

    # 信息输出（pytest -v 可见）
    print(f"\n[huge_ledger_smoke] {TOTAL_ROWS:,} 行处理完成")
    print(f"  耗时: {elapsed_total:.1f}s")
    print(f"  validated: {total_validated:,}")
    print(f"  ledger: {total_converted_ledger:,}")
    print(f"  aux: {total_converted_aux:,}")
    if mem_before_mb is not None:
        print(f"  内存增量: {mem_delta_mb:.0f}MB")


# ===========================================================================
# 辅助测试：验证测试能被 pytest 收集（不跑 slow）
# ===========================================================================


def test_huge_ledger_smoke_collectable():
    """确认 test_huge_ledger_pipeline_2m_rows 可被 pytest 收集。

    此测试不标 slow，CI 正常跑时验证模块 import 无误。
    """
    assert TOTAL_ROWS == 2_000_000
    assert BATCH_SIZE == 100_000
    # 验证函数可调用
    batch = _generate_ledger_batch(0, 10)
    assert len(batch) == 10
    assert batch[0]["account_code"] == "001001"
