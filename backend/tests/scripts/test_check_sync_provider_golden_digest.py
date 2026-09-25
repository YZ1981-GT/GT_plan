# -*- coding: utf-8 -*-
"""`check_sync_provider_golden_digest.py` 基线门自测。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 1 · Requirements 4.1 / 4.2 / 4.5

覆盖：
  1. 8 家 provider 全部可 import 并产出三段（含 B60 无 projection 的诚实 null）。
  2. digest 总数 = 23（8 contract + 8 instrumentation + 7 projection；B60 无 projection）。
  3. 现状 digest ≡ 已入库基线（零回归门本身此时必绿）。
  4. 变异反证：篡改一家的 contract digest ⇒ _compare 必须报漂移（门不是永绿装饰）。
  5. 合成 payload 确实驱动了 build_store_projection（D3 真库 0 行仍被覆盖，Req 4.5）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_CHECK_PATH = _BACKEND / "scripts" / "check" / "check_sync_provider_golden_digest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_check_sync_provider_golden_digest", _CHECK_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_all_delivered_providers_produce_three_sections() -> None:
    mod = _load_module()
    report = mod.run()
    labels = {p["label"] for p in report["providers"]}
    # 🔴 2026-09-26：E1 纳入（spec e1-sync-coverage-and-first-canary 交付的第 9 个 contract，
    #    也是引擎落地后新建的第一个 entry ⇒ 它的 digest 能钉住「薄转发层」不被引擎改动破坏）
    assert labels == {"b60", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "e1"}
    for p in report["providers"]:
        assert p["contract_payload_sha256"], f"{p['label']} contract digest 空"
        assert p["instrumentation_sha256"], f"{p['label']} instrumentation digest 空"
        if p["label"] == "b60":
            assert p["store_projection_sha256"] is None, "B60 是 simple_checklist，projection 应为 null"
        else:
            assert p["store_projection_sha256"], f"{p['label']} projection digest 空"


def test_digest_count_matches_provider_capabilities() -> None:
    """digest 总数 = 每家 contract + instrumentation（必有）+ projection（B60 无该路径）。

    🔴 断言从 PROVIDERS 表**现算**而非手抄数字（首版写死 23，E1 纳入后变 26 ⇒ 手抄必过期）。
    B60 是 simple_checklist 形态、无 `build_store_projection` ⇒ 它的 projection 如实记 null，
    不假造 digest（需求 4.5 的诚实边界）。
    """
    mod = _load_module()
    report = mod.run()
    expected = sum(2 + (1 if has_proj else 0) for (_l, _m, _c, has_proj, _p) in mod.PROVIDERS)
    assert report["digest_count"] == expected
    # 当前实测：9 家 × 3 − B60 的 projection = 26
    assert report["digest_count"] == 26


def test_current_matches_committed_baseline() -> None:
    """现状 digest ≡ 已入库基线（零回归门此时必绿）。"""
    mod = _load_module()
    baseline = mod._load_baseline()
    assert baseline is not None, "基线文件缺失 —— 应先 --update 入库"
    drift = mod._compare(mod.run(), baseline)
    assert drift == [], f"现状与基线漂移：{drift}"


def test_mutation_sheet_digest_drift_is_detected() -> None:
    """变异反证（P1-4 sheet 粒度）：篡改一家某 sheet 的 digest ⇒ _compare 必须报出该 sheet 漂移。

    P1-4 复盘修复后，contract 整体 digest 不再进严格比较（扩容新 sheet 是 additive）；
    改动**已有 sheet** 才算回归，由 sheet 粒度 digest 精确定位。
    """
    mod = _load_module()
    current = mod.run()
    tampered = {
        "digest_count": current["digest_count"],
        "providers": [dict(p) for p in current["providers"]],
    }
    # 篡改 d1 的某个 sheet digest（模拟已有 sheet 被改动）
    d1 = next(dict(p) for p in tampered["providers"] if p["label"] == "d1")
    d1_sheets = dict(d1.get("sheet_digests") or {})
    assert d1_sheets, "d1 应有 sheet_digests"
    first_sk = sorted(d1_sheets)[0]
    d1_sheets[first_sk] = "0" * 64
    d1["sheet_digests"] = d1_sheets
    tampered["providers"] = [d1 if p["label"] == "d1" else dict(p) for p in tampered["providers"]]
    drift = mod._compare(current, tampered)
    assert drift, "变异后未检出漂移 —— 门是永绿装饰"
    assert any(d["field"] == f"sheet[{first_sk}]" and d["label"] == "d1" for d in drift), drift


def test_synthetic_payload_drives_projection_for_zero_row_provider() -> None:
    """D3 真库 0 行，但合成 payload 必须驱动出非空 projection（Requirement 4.5）。"""
    mod = _load_module()
    d3 = mod._import_provider("phase5_d3_prepaid_receipts")
    rows = mod._synthetic_rows(d3)
    assert len(rows) == 2
    # 合成两行须各带稳定 rowId 且账龄 nested 路径已建 dict
    assert all(r.get("rowId") for r in rows)
    assert isinstance(rows[0].get("agingPrior"), dict), "nested 账龄路径应被逐级建 dict"
