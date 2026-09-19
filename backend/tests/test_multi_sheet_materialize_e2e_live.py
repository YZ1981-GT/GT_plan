# -*- coding: utf-8 -*-
"""多 sheet materialize 端到端实测（spec multi-sheet-materialize-defined-name-shift-normalization R6）。

打**真实运行的后端**（127.0.0.1:9980）+ **真实 PG**,验证:编辑 D4-29（转置客户表）触发的
combined projection 里 sibling D4-22/D4-23 各插行时,materialize 完整通过 —— 不再出现
`adapter_unmanaged_region_drift`。这条同时守护三个修复:
  1. sibling footer 合计公式扩张（oo-html-writeback-performance,_plan_row_shift 按 region.table_key
     取 GT_FOOTER_ROW_{TID}）;
  2. workbook.xml own-sheet defined-name 位移的合并归一化（MaterializeWorkbookChangeSet）;
  3. sibling worksheet part 的 per-sheet shift 归一化（MaterializeResult.per_table_shift）。

任一修复回退 ⇒ materialize 返回 500 ⇒ 本测试红（非空守卫）。

前置:后端已运行（start-dev.bat,9980）+ PG 在线,且存在真实 wp（首汽/D4 收入 entry）。
门控:后端不在线时 skip。
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

BASE = os.environ.get("D4_E2E_BASE", "http://127.0.0.1:9980")
PROJECT = os.environ.get("MS_E2E_PROJECT", "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")
WP = os.environ.get("MS_E2E_WP", "b3ab3c46-828f-4f48-950e-aee9bbdc923f")
ENTRY = "gt-d4-operating-revenue"
SHEET_KEY = "d4-29-managed"
PREFIX = f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entries/xlsx/{ENTRY}"


def _backend_up() -> bool:
    try:
        return httpx.get(f"{BASE}/api/health", timeout=3).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _backend_up(),
    reason="需真实后端(9980)在线 + 真实 D4 收入 entry（多 sheet 契约）",
)


def _login(c: httpx.Client) -> dict[str, str]:
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    r.raise_for_status()
    body = r.json()
    token = body.get("data", {}).get("access_token") or body.get("access_token")
    return {"Authorization": f"Bearer {token}"}


def test_multi_sheet_materialize_no_unmanaged_drift() -> None:
    """编辑 D4-29 → materialize 200,不再 adapter_unmanaged_region_drift。"""
    with httpx.Client(base_url=BASE, timeout=180.0) as c:
        h = _login(c)

        sp = c.get(PREFIX + "/store-projection", headers=h)
        assert sp.status_code == 200, sp.text[:500]
        data = sp.json().get("data", {})
        projection = data.get("projection") or {}
        expected_revision = data.get("expected_revision") or 0
        # 该 entry 是多 sheet 契约（D4-2/D4-22/D4-23/D4-29…）;combined projection 的行数
        # 远超单 sheet,是本守卫成立的前提。
        assert data.get("row_count", 0) > 0, "combined projection 为空,守卫会空转"

        idem = f"ms-e2e-{uuid.uuid4().hex[:8]}"
        body = {
            "projection": projection,
            "sheet_key": SHEET_KEY,
            "expected_revision": expected_revision,
            "client_edit_epoch": 0,
        }
        pm = c.post(
            PREFIX + "/pending-mutations",
            headers={**h, "Idempotency-Key": idem},
            json=body,
        )
        assert pm.status_code == 200, f"pending-mutations 失败: {pm.text[:500]}"
        pm_data = pm.json().get("data", pm.json())
        token = pm_data.get("pending_mutation_token") if isinstance(pm_data, dict) else None
        assert token, f"未拿到 pending_mutation_token: {pm_data}"

        mr = c.post(
            PREFIX + "/materialize",
            headers={**h, "Idempotency-Key": idem},
            json={**body, "pending_mutation_token": token},
        )
        # 🔴 核心断言:三修复任一回退 ⇒ 这里 500（footer_formula_range_stale 或
        #    adapter_unmanaged_region_drift）。
        assert mr.status_code == 200, (
            f"materialize 未通过（可能某个多 sheet 归一化修复回退了）: "
            f"{mr.status_code} {mr.text[:800]}"
        )
        body_out = mr.json().get("data", mr.json())
        assert isinstance(body_out, dict) and body_out.get("artifact_sha256"), (
            f"materialize 200 但产物 descriptor 不完整: {body_out}"
        )
