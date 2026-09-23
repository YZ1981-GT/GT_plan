# -*- coding: utf-8 -*-
"""P9 红判据：D4-35 / D4-13 的 store item 未被出方向端点装配（缺陷 C）。

spec: d4-html-to-oo-store-contract-alignment · Task 2
Requirements 3.2 · Property 9

═══ 这条判据钉的是什么 ═══

`store_projection_response.py` 装配 payloads 时只遍历两个来源：`provider.STORE_ITEM_IDS`
与 `provider.STORE_ITEM_IDS_D45_FIXED`。而 provider 另外声明了：

  * `D4-35-data`（`STORE_ITEM_ID_D435_DICT`，注释明写"不进 STORE_ITEM_IDS"）
  * `STORE_ITEM_IDS_D413_FIXED`（`D4-13-process` / `-conclusion`）

两者都**不在**那两个来源里 ⇒ 出方向永远拿不到它们的 payload：D4-35 切 OO 恒空、
D4-13 两段正文恒写不进 OO。反方向 `oo_to_html` 三批清单都消费了 ⇒ 两侧真源不一致。

本文件**不启后端**、不连库：直接复刻端点的装配规则（「只喂 STORE_ITEM_IDS +
STORE_ITEM_IDS_D45_FIXED」），把一份非空 payload 按该规则喂 `build_combined_store_projection`，
与「手动塞入」对照。

🔴 现状**必红**：
  * D4-35：端点装配 → `other_revenue_check_rows/*` 0 字段；对照组 > 0。
  * D4-13：固定键恒存在，**必须比值不能比键数** —— 端点装配下值为 `''`，对照组为正文。

判据以字段数 / 字段值为准，不断言键的内部形状（后者随 getRequestKey 类实现漂移）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d4_revenue_detail as P  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.phase5_d4_other_check_sheet import (  # noqa: E402
    ROWS_TABLE_KEY_D435,
    STORE_ITEM_ID_D435,
)
from app.services.workpaper_sync.phase5_d4_erp_check_sheet import (  # noqa: E402
    STORE_ITEM_ID_D413_CONCLUSION,
    STORE_ITEM_ID_D413_PROCESS,
    STORE_ITEM_IDS_D413_FIXED,
)


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(P.build_contract_payload(), adapter_id=P.ADAPTER_ID)


def _endpoint_payload_loader_rule() -> tuple[str, ...]:
    """端点 `store_projection_response.py` 真实的 payload 装配来源。

    Task 5 后：端点若 provider 暴露 `all_store_item_ids()` 就用它作单一来源，否则回退旧并集
    `STORE_ITEM_IDS + STORE_ITEM_IDS_D45_FIXED`。本函数如实复刻端点那段选择逻辑 —— 修好后
    provider 有 `all_store_item_ids`，本函数返回它，D4-35/D4-13 进入来源集，红判据随之转绿。
    """
    all_ids_fn = getattr(P, "all_store_item_ids", None)
    if callable(all_ids_fn):
        return tuple(all_ids_fn())
    ids = list(getattr(P, "STORE_ITEM_IDS", ()) or ())
    ids += list(getattr(P, "STORE_ITEM_IDS_D45_FIXED", ()) or ())
    return tuple(ids)


def _d435_nonempty_payload() -> str:
    return json.dumps(
        {
            "rows": [
                {"id": "GTROW-D435-0015", "bizName": "探针-其他业务A", "periodAmount": 123456.78},
                {"id": "GTROW-D435-0016", "bizName": "探针-其他业务B", "periodAmount": 999.01},
            ],
            "sampling": {"note": "HTML-only"},
            "periodAmount": 124455.79,
        },
        ensure_ascii=False,
    )


def _build_via_endpoint_rule(item_payloads: dict[str, str], contract: Any) -> Any:
    """按端点装配规则：只把命中 loader 来源的 item 喂进 combined projection。"""
    loader_ids = set(_endpoint_payload_loader_rule())
    payloads = {k: v for k, v in item_payloads.items() if k in loader_ids}
    return P.build_combined_store_projection(payloads, contract=contract)


def _build_manual(item_payloads: dict[str, str], contract: Any) -> Any:
    """对照组：手动把 payload 全塞进去（证明 provider 本身能投影）。"""
    return P.build_combined_store_projection(dict(item_payloads), contract=contract)


# ═══════════════════════════════════════════════════════════════════════════
# D4-35：比字段数（0 vs > 0）
# ═══════════════════════════════════════════════════════════════════════════


def test_d435_reaches_endpoint_projection(contract: Any) -> None:
    """P9-a：D4-35 的 store 数据经端点装配后必须产出 `other_revenue_check_rows/*` 字段。

    🔴 现状必红：`D4-35-data` 不在 STORE_ITEM_IDS，也不在 D45_FIXED ⇒ 端点拿不到它。
    """
    payloads = {STORE_ITEM_ID_D435: _d435_nonempty_payload()}
    proj_endpoint = _build_via_endpoint_rule(payloads, contract)
    proj_manual = _build_manual(payloads, contract)

    hit_endpoint = [
        k for k in proj_endpoint.values if str(k).startswith(ROWS_TABLE_KEY_D435 + "/")
    ]
    hit_manual = [
        k for k in proj_manual.values if str(k).startswith(ROWS_TABLE_KEY_D435 + "/")
    ]
    assert len(hit_manual) > 0, "对照组也没投影出 D4-35 —— 前提被破坏（provider 应能投影它）"
    assert len(hit_endpoint) > 0, (
        f"缺陷 C：D4-35 出方向拿不到 payload。端点装配下 `{ROWS_TABLE_KEY_D435}/*` 字段数="
        f"{len(hit_endpoint)}，对照组={len(hit_manual)}。"
        f"根因：`{STORE_ITEM_ID_D435}` 不在 STORE_ITEM_IDS 也不在 STORE_ITEM_IDS_D45_FIXED，"
        "而端点只遍历这两个来源。"
    )


# ═══════════════════════════════════════════════════════════════════════════
# D4-13：固定键恒存在 ⇒ 必须比**值**（'' vs 正文）
# ═══════════════════════════════════════════════════════════════════════════


def _d413_field_value(proj: Any, needle: str):
    for k, fv in proj.values.items():
        if "d413" in str(k) and str(k).endswith(needle):
            return getattr(fv, "value", None)
    return "MISSING"


def test_d413_process_conclusion_reach_endpoint_with_value(contract: Any) -> None:
    """P9-b：D4-13 核对过程/结论正文经端点装配后必须**有值**（比值不比键数）。

    🔴 现状必红：`STORE_ITEM_IDS_D413_FIXED` 不被端点消费 ⇒ 两键值恒 ''（对照组为正文）。
    固定键恒存在，只断言键存在会恒绿——本判据只认 value。
    """
    text_process = "探针-D4-13-核对过程正文"
    text_conclusion = "探针-D4-13-核对结论正文"
    payloads = {
        STORE_ITEM_ID_D413_PROCESS: text_process,
        STORE_ITEM_ID_D413_CONCLUSION: text_conclusion,
    }
    proj_endpoint = _build_via_endpoint_rule(payloads, contract)
    proj_manual = _build_manual(payloads, contract)

    manual_process = _d413_field_value(proj_manual, "/process")
    manual_conclusion = _d413_field_value(proj_manual, "/conclusion")
    assert manual_process == text_process and manual_conclusion == text_conclusion, (
        f"对照组未取到 D4-13 正文（process={manual_process!r} conclusion={manual_conclusion!r}）"
        " —— 前提被破坏"
    )

    endpoint_process = _d413_field_value(proj_endpoint, "/process")
    endpoint_conclusion = _d413_field_value(proj_endpoint, "/conclusion")
    assert endpoint_process == text_process and endpoint_conclusion == text_conclusion, (
        f"缺陷 C：D4-13 出方向拿不到正文。端点装配下 process={endpoint_process!r} / "
        f"conclusion={endpoint_conclusion!r}（对照组分别是 {text_process!r} / {text_conclusion!r}）。"
        f"根因：STORE_ITEM_IDS_D413_FIXED={tuple(STORE_ITEM_IDS_D413_FIXED)} 不被端点的 payload "
        "装配循环遍历（它只遍历 STORE_ITEM_IDS + STORE_ITEM_IDS_D45_FIXED）。"
    )


def test_endpoint_rule_covers_d435_and_d413_after_fix() -> None:
    """Task 5 后端点装配来源必须**包含** D4-35 与 D4-13 两条 fixed item。

    这条与修复前的红判据互为镜像：修复前它们被漏在来源之外（缺陷 C），修复后
    `all_store_item_ids()` 把它们纳入单一口径。若哪天有人把端点改回只遍历
    STORE_ITEM_IDS + D45_FIXED（或删掉 all_store_item_ids），本断言立即打红。
    """
    loader_ids = set(_endpoint_payload_loader_rule())
    for item in STORE_ITEM_IDS_D413_FIXED:
        assert item in loader_ids, (
            f"{item} 未进端点装配来源 —— 缺陷 C 复发：D4-13 正文将写不进 OO"
        )
    assert STORE_ITEM_ID_D435 in loader_ids, (
        "D4-35-data 未进端点装配来源 —— 缺陷 C 复发：D4-35 切 OO 恒空"
    )
