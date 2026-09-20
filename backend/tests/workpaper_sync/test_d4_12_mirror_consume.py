# -*- coding: utf-8 -*-
"""D4-12 OO→HTML 消费侧（第四维）守卫。

spec: d4-12-transposed-writeback · Task 13 · Requirement 6.2 · Property 5

第四维判据（清册「OO→HTML 消费侧接线」）：转置 store item ``D4-12-contracts-v2``（list base
``[{id, ...21字段, indexNo, label, ...}]``）必须被 ``merge_projection_into_all_d4_stores`` 以
**4-tuple** 正确消费（同 D4-29，走 rows 循环非专用 dict 块）；applied>0 时**不抹 HTML-only 元字段**
（indexNo/label/attachment* 等前端受管之外的键）；空 projection 不静默把 base 投空。

与通用不变量 test_d4_mirror_shape_invariants 互补：那里验「每 value 是 4-tuple / 在 STORE_ITEM_IDS」
的形态面；这里验 D4-12 具体消费语义（list base 保留 + 不覆写元字段 + 不静默投空）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import app.services.workpaper_sync.phase5_d4_12_contract as D12  # noqa: E402
import app.services.workpaper_sync.phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402

STORE = "D4-12-contracts-v2"


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(D4.build_contract_payload())


def _contract_rows(count=2):
    out = []
    for i in range(count):
        item = {"id": f"c-{i}", "indexNo": f"D4-12-{i + 1}", "label": f"备注{i}",
                "attachmentId": f"att-{i}", "ocrStatus": "done"}
        for k in D12.FIELD_KEYS:
            item[k] = 100 + i if k == "contractAmount" else f"{k}-{i}"
        out.append(item)
    return out


def test_d412_is_consumed_as_four_tuple(contract):
    """D4-12 在 merge_projection_into_all_d4_stores 输出里是 4-tuple（可被 oo_to_html 硬解包）。"""
    payload = {STORE: json.dumps(_contract_rows(2), ensure_ascii=False)}
    proj = D4.build_combined_store_projection(payload, contract=contract)
    updates = D4.merge_projection_into_all_d4_stores(projection=proj, base_by_item=payload)
    assert STORE in updates, "D4-12 未进入 merge 输出（mirror 无路径消费）"
    v = updates[STORE]
    assert isinstance(v, tuple) and len(v) == 4, f"D4-12 merge 输出非 4-tuple: {type(v)}"
    rows, applied, _visited, _removed = v
    assert isinstance(rows, list) and len(rows) == 2


def test_d412_preserves_html_only_metafields(contract):
    """applied>0 时保留 HTML-only 元字段（indexNo/label/attachmentId/ocrStatus 不被抹）。"""
    base_rows = _contract_rows(2)
    payload = {STORE: json.dumps(base_rows, ensure_ascii=False)}
    proj = D4.build_combined_store_projection(payload, contract=contract)
    updates = D4.merge_projection_into_all_d4_stores(projection=proj, base_by_item=payload)
    rows, _applied, _visited, _removed = updates[STORE]
    by = {r["id"]: r for r in rows}
    for src in base_rows:
        got = by[src["id"]]
        # 21 受管字段回写正确
        assert got["contractNo"] == src["contractNo"]
        # HTML-only 元字段保留（转置受管区不含它们，merge 不得抹掉）
        assert got["indexNo"] == src["indexNo"], "indexNo 被抹（HTML-only 元字段丢失）"
        assert got["label"] == src["label"], "label 被抹"
        assert got["attachmentId"] == src["attachmentId"], "attachmentId 被抹"
        assert got["ocrStatus"] == src["ocrStatus"], "ocrStatus 被抹"


def test_d412_empty_projection_does_not_silently_blank_base(contract):
    """空 projection（无合同）+ 空 base：merge 返回空 list, 不抛、不静默投错。"""
    proj = D4.build_combined_store_projection({}, contract=contract)
    updates = D4.merge_projection_into_all_d4_stores(projection=proj, base_by_item={})
    rows, _applied, _visited, _removed = updates[STORE]
    assert rows == [], "空 projection 空 base 应返回空 list"


def test_d412_amount_numeric_roundtrip_through_merge(contract):
    """合同金额经 merge 保数值（Requirement 3.4a），不被投成空/字符串。"""
    base_rows = _contract_rows(1)
    base_rows[0]["contractAmount"] = 88888
    payload = {STORE: json.dumps(base_rows, ensure_ascii=False)}
    proj = D4.build_combined_store_projection(payload, contract=contract)
    updates = D4.merge_projection_into_all_d4_stores(projection=proj, base_by_item=payload)
    rows, _applied, _visited, _removed = updates[STORE]
    assert rows[0]["contractAmount"] == 88888


# ─── Task 9 途中修复的 pre-existing bug 守卫（_read_store_map dict-store 默认值）──────


def test_dict_store_missing_key_uses_provider_default_not_empty_list(contract):
    """🔴 回归守卫（Task 9 发布链修复）：dict-store item（D4-31 singleton / D4-9 / D4-35）
    缺失时**不能**统一塞 EMPTY_STORE_PAYLOAD('[]')。

    rematerialize 的 _read_store_map 曾对所有缺失 item 塞 '[]'，dict-store 拿 '[]' 被
    build_store_projection 判「必须是单对象/字典」抛 ValueError 打挂整册。修复 = 缺失时
    不塞 key，让 build_combined_store_projection 的 payloads.get(item, <per-item默认>) 用
    provider 自己声明的正确空默认。

    本守卫钉住 build_combined_store_projection 的行为契约：
    - 缺失 dict-store key（不塞）→ 用 provider 默认（{} for D4-31）→ 不抛；
    - 显式塞 '[]' 给 D4-31 → 抛（证明「不塞 key」是正解，不是「塞 []」）。
    """
    # (a) 完全空 payloads（所有 item 缺失）→ 各 provider 用自己的默认, 不抛。
    proj = D4.build_combined_store_projection({}, contract=contract)
    assert proj is not None

    # (b) 显式给 D4-31 塞 '[]'（模拟旧 _read_store_map 的错误默认）→ 应抛（证明危害真实存在）。
    from app.services.workpaper_sync import phase5_d4_ipo_interview_sheets as IV

    raised = False
    try:
        IV.build_store_projection("D4-31", "[]", contract=contract)
    except ValueError:
        raised = True
    assert raised, "D4-31 拿 '[]' 竟未抛 —— 旧 _read_store_map 默认危害的前提已不存在, 守卫需更新"

    # (c) D4-31 拿 provider 默认 '{}'（空 dict）→ 不抛, 返空 singleton。
    IV.build_store_projection("D4-31", "{}", contract=contract)
