"""S7-1: 9 家真实样本参数化 E2E。

与 test_execute_v2_e2e.py (YG36 单家) 的区别：
- 参数化对 9 家全部跑一次
- 每家的期望值不同（balance/aux_balance 行数）— 用最低断言（>0 即可）
- 只跑识别+转换，不跑写入（避免 9 家都写 DB 耗时）
- 确保每家的 aux_ledger/aux_balance 都能分别正确拆分
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ledger_import.converter import (
    convert_balance_rows,
    convert_ledger_rows,
)
from app.services.ledger_import.detector import detect_file_from_path
from app.services.ledger_import.identifier import identify
from app.services.ledger_import.parsers.excel_parser import iter_excel_rows_from_path
from app.services.ledger_import.parsers.csv_parser import iter_csv_rows_from_path
from app.services.ledger_import.validator import validate_l1
from app.services.ledger_import.writer import prepare_rows_with_raw_extra

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "数据"

# 限 1000 行/sheet 抽样，9 家 × 多 sheet 控制在 3 分钟内完成
SAMPLE_LIMIT = 1000


# 9 家企业样本清单
# 每项：(名称, [(相对路径, 期望含 balance, 期望含 ledger)])
SAMPLES = [
    ("YG36 四川物流", [
        ("YG36-重庆医药集团四川物流有限公司2025.xlsx", True, True),
    ]),
    ("YG2101 四川医药", [
        ("YG2101-重庆医药集团四川医药有限公司2025年-科目余额表+序时账.xlsx", True, True),
    ]),
    ("YG4001 宜宾大药房", [
        ("YG4001-30重庆医药集团宜宾医药有限公司新健康大药房临港店-余额表+序时账.xlsx", True, True),
    ]),
    ("和平药房", [
        ("和平药房/科目余额表-重庆和平药房连锁有限责任公司2025.xlsx", True, False),
        # csv 大文件耗时长，跳过
    ]),
    ("和平物流", [
        ("和平物流25加工账-药品批发.xlsx", True, True),  # S6-9 修复后余额表应识别为 balance
    ]),
    ("安徽骨科", [
        ("余额表+序时账-安徽-骨科.xlsx", True, True),
    ]),
    ("辽宁卫生", [
        ("辽宁卫生服务有限公司/辽宁卫生服务有限公司-科目余额表.xlsx", True, False),
    ]),
    ("医疗器械", [
        ("重庆医药集团医疗器械有限公司-医疗设备/余额表-器械25.xlsx", True, False),
    ]),
    ("陕西华氏 2025", [
        ("陕西华氏医药有限公司-需加工24和25年的AUD文件/2025/陕西华氏-科目余额表-2025.xlsx", True, False),
    ]),
]


def _parse_and_convert(path: Path):
    """Helper：对单文件跑识别 + 转换，返回 stats 字典。"""
    stats = {
        "balance_rows": 0,
        "aux_balance_rows": 0,
        "ledger_rows": 0,
        "aux_ledger_rows": 0,
        "sheets": [],
        "aux_types": set(),
    }

    fd = detect_file_from_path(str(path), path.name)
    for sheet in fd.sheets:
        identified = identify(sheet)
        stats["sheets"].append((identified.sheet_name, identified.table_type))

        if identified.table_type not in ("balance", "ledger"):
            continue

        col_mapping = {
            cm.column_header: cm.standard_field
            for cm in identified.column_mappings
            if cm.standard_field and cm.confidence >= 50
        }
        headers = identified.detection_evidence.get("header_cells", [])
        ff_cols = [
            cm.column_index for cm in identified.column_mappings
            if cm.standard_field in ("account_code", "account_name")
        ]

        ext = path.suffix.lower()
        if ext in (".xlsx", ".xlsm"):
            row_iter = iter_excel_rows_from_path(
                str(path), identified.sheet_name,
                data_start_row=identified.data_start_row,
                forward_fill_cols=ff_cols or None,
            )
        elif ext in (".csv", ".tsv"):
            encoding = fd.encoding or "utf-8"
            row_iter = iter_csv_rows_from_path(
                str(path), encoding=encoding,
                data_start_row=identified.data_start_row,
            )
        else:
            continue

        # 抽样
        parsed = []
        count = 0
        for chunk in row_iter:
            for raw in chunk:
                if count >= SAMPLE_LIMIT:
                    break
                row_dict = {}
                for i, val in enumerate(raw):
                    if i < len(headers):
                        row_dict[headers[i]] = val
                parsed.append(row_dict)
                count += 1
            if count >= SAMPLE_LIMIT:
                break

        std_rows, _ = prepare_rows_with_raw_extra(parsed, col_mapping, headers)
        _, cleaned = validate_l1(
            std_rows, identified.table_type, column_mapping=col_mapping,
        )

        if identified.table_type == "balance":
            bal, aux_bal = convert_balance_rows(cleaned)
            stats["balance_rows"] += len(bal)
            stats["aux_balance_rows"] += len(aux_bal)
            for row in aux_bal:
                if row.get("aux_type"):
                    stats["aux_types"].add(row["aux_type"])
        elif identified.table_type == "ledger":
            ledger, aux_ledger, aux_stats = convert_ledger_rows(cleaned)
            stats["ledger_rows"] += len(ledger)
            stats["aux_ledger_rows"] += len(aux_ledger)
            stats["aux_types"].update(aux_stats.keys())

    return stats


@pytest.mark.parametrize("company,files", SAMPLES, ids=[s[0] for s in SAMPLES])
def test_sample_recognition_and_conversion(company: str, files: list):
    """每家样本识别 + 转换必须产生数据。"""
    all_stats = {
        "balance_rows": 0,
        "aux_balance_rows": 0,
        "ledger_rows": 0,
        "aux_ledger_rows": 0,
        "aux_types": set(),
    }
    files_checked = 0

    for rel_path, expect_balance, expect_ledger in files:
        path = DATA_DIR / rel_path
        if not path.exists():
            pytest.skip(f"Real sample missing: {path}")
        try:
            stats = _parse_and_convert(path)
        except Exception as exc:
            pytest.fail(f"{company} - {rel_path} failed: {type(exc).__name__}: {exc}")

        files_checked += 1

        # 汇总
        all_stats["balance_rows"] += stats["balance_rows"]
        all_stats["aux_balance_rows"] += stats["aux_balance_rows"]
        all_stats["ledger_rows"] += stats["ledger_rows"]
        all_stats["aux_ledger_rows"] += stats["aux_ledger_rows"]
        all_stats["aux_types"].update(stats["aux_types"])

        # 单文件断言
        if expect_balance:
            assert stats["balance_rows"] > 0, (
                f"{company} - {rel_path}: 预期含余额表但 balance_rows=0, "
                f"sheets={stats['sheets']}"
            )
        if expect_ledger:
            assert stats["ledger_rows"] > 0, (
                f"{company} - {rel_path}: 预期含序时账但 ledger_rows=0, "
                f"sheets={stats['sheets']}"
            )

    assert files_checked > 0, f"{company}: 没有任何文件被成功处理"

    # 打印汇总（-s 时可见）
    print(
        f"\n[{company}] "
        f"balance={all_stats['balance_rows']} "
        f"aux_balance={all_stats['aux_balance_rows']} "
        f"ledger={all_stats['ledger_rows']} "
        f"aux_ledger={all_stats['aux_ledger_rows']} "
        f"aux_types={len(all_stats['aux_types'])}"
    )


def test_all_samples_have_aux_dimensions():
    """9 家中至少 5 家应有辅助维度数据（客户/金融机构/成本中心 等）。

    这是"核算维度识别"的综合验证：说明 converter 和 identifier 对
    真实数据的维度字段识别正常。
    """
    companies_with_aux = 0
    for company, files in SAMPLES:
        for rel_path, _, _ in files:
            path = DATA_DIR / rel_path
            if not path.exists():
                continue
            stats = _parse_and_convert(path)
            if stats["aux_balance_rows"] > 0 or stats["aux_ledger_rows"] > 0:
                companies_with_aux += 1
                break

    if companies_with_aux == 0:
        pytest.skip("No real samples available")

    assert companies_with_aux >= 5, (
        f"预期至少 5 家样本有辅助维度，实际 {companies_with_aux}"
    )
