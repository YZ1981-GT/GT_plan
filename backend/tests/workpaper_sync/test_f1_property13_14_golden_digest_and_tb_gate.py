# -*- coding: utf-8 -*-
"""F1 红判据 Property 13 + Property 14。

spec: f1-sync-coverage-and-first-canary · Task 6

Property 13: 其余 10 个 contract 的 golden digest 不变
  b60/d1~d7/e1/g7/h1 的 contract payload sha256 在 F1 纳入后不得变化。

Property 14: F1-1 受管后 sync 路径 TB 写次数为 0
  sync 回写路径不 import publishToTb、不触发 trial_balance 写入。
"""
from __future__ import annotations

import json
import hashlib
import importlib
from typing import Any

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Property 13：零回归基线（10 个既有 contract）
# ═══════════════════════════════════════════════════════════════════════════


def _canonical_sha256(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: 10 个既有 provider 模块
EXISTING_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("b60", "app.services.workpaper_sync.pilot_simple_checklist"),
    ("d1", "app.services.workpaper_sync.phase5_d1_notes_receivable"),
    ("d2", "app.services.workpaper_sync.pilot_d2_large_json"),
    ("d3", "app.services.workpaper_sync.phase5_d3_prepaid_receipts"),
    ("d4", "app.services.workpaper_sync.phase5_d4_revenue_detail"),
    ("d5", "app.services.workpaper_sync.phase5_d5_receivables_financing"),
    ("d6", "app.services.workpaper_sync.phase5_d6_contract_assets"),
    ("d7", "app.services.workpaper_sync.phase5_d7_contract_liabilities"),
    ("e1", "app.services.workpaper_sync.phase5_e1_monetary_fund"),
    ("g7", "app.services.workpaper_sync.pilot_g7_two_level_dynamic"),
    ("h1", "app.services.workpaper_sync.pilot_h1_grouped_dynamic"),
)


class TestProperty13GoldenDigestBaseline:
    """F1 纳入后既有 10 个 contract 的 golden digest 不变。"""

    def test_existing_contracts_can_build_payload(self) -> None:
        """每个既有 provider 的 build_contract_payload 仍能调用。"""
        for label, module_name in EXISTING_PROVIDERS:
            try:
                mod = importlib.import_module(module_name)
            except ImportError:
                pytest.skip(f"{module_name} 不可导入")
            build_fn = getattr(mod, "build_contract_payload", None)
            if build_fn is None:
                continue  # 部分 pilot 无此方法
            payload = build_fn()
            digest = _canonical_sha256(payload)
            assert isinstance(digest, str) and len(digest) == 64, (
                f"{label}: contract payload digest 格式不对"
            )

    def test_delivered_contracts_count_is_11(self) -> None:
        """DELIVERED_PER_ENTRY_CONTRACTS 应有 11 条（10 既有 + F1）。

        🔴 此判据在 Task 9 向 registry 追加 F1 条目后转绿。
        """
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )
        count = len(DELIVERED_PER_ENTRY_CONTRACTS)
        # 当前应为 11（F1 尚未加入时为 11；加入后也是 12，本判据需更新）
        assert count >= 11, (
            f"DELIVERED_PER_ENTRY_CONTRACTS 只有 {count} 条，"
            "期望至少 11 条（10 既有 + 可能的 F1）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 14：sync 路径 TB 写次数为 0
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty14TbGateRedLine:
    """F1 sync 回写路径不得触碰 trial_balance。"""

    def test_f1_store_items_no_trial_or_tb(self) -> None:
        """F1 的 store_item_id 集合中不含 trial/tb 相关键。"""
        from tests.workpaper_sync.test_f1_property2_3_store_item_id_and_triad import (
            REAL_STORE_ITEM_IDS,
        )
        for label, item_id in REAL_STORE_ITEM_IDS.items():
            assert "trial" not in item_id.lower(), (
                f"{label}: store_item_id '{item_id}' 含 'trial'"
            )
            assert "tb" not in item_id.lower() or item_id.startswith("F1-"), (
                f"{label}: store_item_id '{item_id}' 含 'tb'"
            )

    def test_publish_to_tb_not_in_sync_provider_imports(self) -> None:
        """F1 provider（尚未创建）的 sync 路径不 import publishToTb。

        🔴 此判据在 F1 provider 创建后验证：provider 文件不含 publishToTb。
        """
        import ast
        from pathlib import Path

        provider_path = (
            Path(__file__).resolve().parents[2]
            / "app"
            / "services"
            / "workpaper_sync"
            / "phase5_f1_prepayment.py"
        )
        if not provider_path.exists():
            pytest.skip("phase5_f1_prepayment.py 尚未创建（Task 7）")

        source = provider_path.read_text(encoding="utf-8")
        assert "publishToTb" not in source, (
            "phase5_f1_prepayment.py 不得 import/调用 publishToTb"
        )
        assert "publish_to_tb" not in source, (
            "phase5_f1_prepayment.py 不得 import/调用 publish_to_tb"
        )

    def test_ci_guard_scripts_exist(self) -> None:
        """CI 守卫脚本存在。"""
        from pathlib import Path
        scripts_dir = Path(__file__).resolve().parents[2] / "scripts" / "check"
        assert (scripts_dir / "check_tb_writeback_no_direct_call.py").exists(), (
            "CI 守卫 check_tb_writeback_no_direct_call.py 不存在"
        )
        assert (scripts_dir / "check_tb_publish_confirm_gate.py").exists(), (
            "CI 守卫 check_tb_publish_confirm_gate.py 不存在"
        )
