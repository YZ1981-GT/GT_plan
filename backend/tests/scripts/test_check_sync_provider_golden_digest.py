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


def test_all_eight_providers_produce_three_sections() -> None:
    mod = _load_module()
    report = mod.run()
    labels = {p["label"] for p in report["providers"]}
    assert labels == {"b60", "d1", "d2", "d3", "d4", "d5", "d6", "d7"}
    for p in report["providers"]:
        assert p["contract_payload_sha256"], f"{p['label']} contract digest 空"
        assert p["instrumentation_sha256"], f"{p['label']} instrumentation digest 空"
        if p["label"] == "b60":
            assert p["store_projection_sha256"] is None, "B60 是 simple_checklist，projection 应为 null"
        else:
            assert p["store_projection_sha256"], f"{p['label']} projection digest 空"


def test_digest_count_is_23() -> None:
    """8 contract + 8 instrumentation + 7 projection（B60 无）= 23。"""
    report = _load_module().run()
    assert report["digest_count"] == 23


def test_current_matches_committed_baseline() -> None:
    """现状 digest ≡ 已入库基线（零回归门此时必绿）。"""
    mod = _load_module()
    baseline = mod._load_baseline()
    assert baseline is not None, "基线文件缺失 —— 应先 --update 入库"
    drift = mod._compare(mod.run(), baseline)
    assert drift == [], f"现状与基线漂移：{drift}"


def test_mutation_contract_digest_drift_is_detected() -> None:
    """变异反证：篡改一家 contract digest ⇒ _compare 必须报出漂移。"""
    mod = _load_module()
    current = mod.run()
    tampered = {
        "digest_count": current["digest_count"],
        "providers": [dict(p) for p in current["providers"]],
    }
    tampered["providers"][1]["contract_payload_sha256"] = "0" * 64  # d1
    drift = mod._compare(current, tampered)
    assert drift, "变异后未检出漂移 —— 门是永绿装饰"
    assert any(d["field"] == "contract_payload_sha256" and d["label"] == "d1" for d in drift)


def test_synthetic_payload_drives_projection_for_zero_row_provider() -> None:
    """D3 真库 0 行，但合成 payload 必须驱动出非空 projection（Requirement 4.5）。"""
    mod = _load_module()
    d3 = mod._import_provider("phase5_d3_prepaid_receipts")
    rows = mod._synthetic_rows(d3)
    assert len(rows) == 2
    # 合成两行须各带稳定 rowId 且账龄 nested 路径已建 dict
    assert all(r.get("rowId") for r in rows)
    assert isinstance(rows[0].get("agingPrior"), dict), "nested 账龄路径应被逐级建 dict"
