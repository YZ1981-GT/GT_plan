# -*- coding: utf-8 -*-
"""契约同一张表里，两个字段不得绑同一个 store 键（spec oo-writeback-template-parity-closure R3 批 B2b）。

D2-12 质押区 B「期末余额」与 C「质押金额」原同接 ``/rows/{row_uuid}/pledgeAmount``：HTML → OO 期末余额恒等于
质押金额；OO 侧两格改得不一样时回写互相覆盖、谁后写谁赢。字段名对拍守卫看不出（键名前端有），
表头守卫也看不出（两列表头都对）。全仓 458 张表现算只有这一处，本守卫钉死为 0。

判据：同一 sheet 内同一 table（或 sheet 级 fields）中，(store_item_id, json_pointer) 二元组不得重复。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

_CONTRACTS = Path(__file__).resolve().parents[2] / "data" / "workpaper_sync_contracts"


def duplicate_bindings(contract: dict) -> list[str]:
    """判据本体（变异自检也走它）：返回「表 · store 键 · 字段列表」。"""
    out: list[str] = []
    for sheet in contract.get("sheets", []):
        groups = [(t.get("table_key"), t.get("fields", []) or []) for t in sheet.get("tables", []) or []]
        groups.append(("<sheet>", sheet.get("fields", []) or []))
        for table_key, fields in groups:
            seen: dict[tuple[str, str], list[str]] = defaultdict(list)
            for f in fields:
                pointer = f.get("json_pointer") or ""
                if pointer:
                    seen[(f.get("store_item_id") or "", pointer)].append(f.get("stable_field_key", "?"))
            out.extend(
                f"{sheet.get('excel_name')} · {table_key} · {item}{pointer} ← {keys}"
                for (item, pointer), keys in sorted(seen.items()) if len(keys) > 1
            )
    return out


def _contracts() -> list[tuple[str, dict]]:
    paths = sorted(p for p in _CONTRACTS.glob("*.json") if ".candidate." not in p.name)
    assert len(paths) > 50, f"契约目录只扫到 {len(paths)} 份 —— 路径错了会让本守卫恒绿"
    return [(p.name, json.loads(p.read_text(encoding="utf-8"))) for p in paths]


def test_no_two_fields_share_one_store_key() -> None:
    found = {name: bad for name, c in _contracts() if (bad := duplicate_bindings(c))}
    assert found == {}, found


def test_d2_12_end_balance_binds_its_own_key() -> None:
    contract = json.loads((_CONTRACTS / "d2.inspection.json").read_text(encoding="utf-8"))
    pointers = {
        f["column_key"]: f["json_pointer"]
        for s in contract["sheets"] for t in s.get("tables", []) for f in t.get("fields", [])
        if t.get("table_key") == "pledge_rows"
    }
    assert pointers["end_balance"] == "/rows/{row_uuid}/endBalance"
    assert pointers["pledge_amount"] == "/rows/{row_uuid}/pledgeAmount"


def test_mutation_duplicate_binding_is_reported() -> None:
    """把 D2-12 期末余额改回接 pledgeAmount ⇒ 判据必报。"""
    contract = json.loads((_CONTRACTS / "d2.inspection.json").read_text(encoding="utf-8"))
    for s in contract["sheets"]:
        for t in s.get("tables", []):
            for f in t.get("fields", []):
                if t.get("table_key") == "pledge_rows" and f["column_key"] == "end_balance":
                    f["json_pointer"] = "/rows/{row_uuid}/pledgeAmount"
    bad = duplicate_bindings(contract)
    assert len(bad) == 1 and "pledgeAmount" in bad[0], bad
