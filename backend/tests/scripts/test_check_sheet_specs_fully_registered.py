# -*- coding: utf-8 -*-
"""`check_sheet_specs_fully_registered.py` 门禁自测（P10 / D1-P10）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 3（先打红）→ Task 21（转绿）
Requirements 7.2 / 7.4

═══ 红→绿的归因链 ═══

Task 3 落判据时注册表尚不存在 ⇒ `reason=registry_module_missing`（红，实测已记录）。
Task 12 落 `store_item_registry.STORE_MERGE_REGISTRY` 后 ⇒ 本判据转绿。本文件在转绿后
断言「绿」+「变异必红」两侧，使卡点不是永绿装饰（需求 7.4）。

覆盖：
  1. 现状通过（8 家已交付 adapter 全在注册表；实测含 g7/h1 共 10 家）。
  2. 变异反证：从注册表剔掉 d1 ⇒ 门禁必报漏项。
  3. per-item default 不得 blanket（rows→[] / dict→{} / fixed_text→''）。
  4. 未命中抛显式错误且含已注册清单（需求 3.4，不静默跳过）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_CHECK_PATH = _BACKEND / "scripts" / "check" / "check_sheet_specs_fully_registered.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_check_sheet_specs_fully_registered", _CHECK_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_all_delivered_adapters_are_registered() -> None:
    """Task 21 转绿：8 家已交付 adapter 全部在 STORE_MERGE_REGISTRY。"""
    report = _load_module().run()
    assert report["ok"], f"应通过，实得 reason={report['reason']} missing={report['missing']}"
    assert report["missing"] == []
    assert len(report["registered"]) >= 8


def test_mutation_missing_adapter_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    """变异反证：注册表漏掉 d1 ⇒ 门禁必报漏项（卡点非永绿装饰）。"""
    from app.services.workpaper_sync import store_item_registry as REG

    crippled = {k: v for k, v in REG.STORE_MERGE_REGISTRY.items() if k != "d1.notes_receivable_detail"}
    monkeypatch.setattr(REG, "STORE_MERGE_REGISTRY", crippled)
    report = _load_module().run()
    assert not report["ok"], "变异后门禁仍通过 —— 判据空转"
    assert "d1.notes_receivable_detail" in report["missing"]


def test_per_item_default_is_not_blanket() -> None:
    """需求 3.2：default 必须 per-kind（rows→[] / dict→{} / fixed_text→''），不得 blanket '[]'。"""
    from app.services.workpaper_sync.store_item_registry import (
        StoreItemSpec,
        StoreKind,
        default_payload_for,
    )

    assert default_payload_for(StoreKind.rows) == "[]"
    assert default_payload_for(StoreKind.dict) == "{}"
    assert default_payload_for(StoreKind.fixed_text) == ""
    # per-item 覆盖优先
    assert StoreItemSpec(item_id="x", kind=StoreKind.dict).effective_default == "{}"
    assert StoreItemSpec(item_id="x", kind=StoreKind.rows, default="{}").effective_default == "{}"


def test_unregistered_adapter_raises_with_registered_list() -> None:
    """需求 3.4：未命中抛显式错误且含已注册清单 —— 不得静默 return。"""
    from app.services.workpaper_sync.store_item_registry import (
        StoreMergePlanNotRegisteredError,
        resolve_store_merge_plan,
    )

    with pytest.raises(StoreMergePlanNotRegisteredError) as exc:
        resolve_store_merge_plan("zz.not_a_real_adapter")
    msg = str(exc.value)
    assert "zz.not_a_real_adapter" in msg
    assert "d1.notes_receivable_detail" in msg, "错误消息应含已注册清单，便于定位漏接"


def test_dedicated_kind_requires_merge_fn() -> None:
    """dedicated 形态必须指名 provider 侧 merge 门面（否则构造即抛）。"""
    from app.services.workpaper_sync.store_item_registry import StoreItemSpec, StoreKind

    with pytest.raises(ValueError, match="dedicated"):
        StoreItemSpec(item_id="x", kind=StoreKind.dedicated)
