# -*- coding: utf-8 -*-
"""M 循环明细表的 store 载荷要能被投影成契约里真实存在的受管键（spec oo-writeback-template-parity-closure 任务 9.2）。

═══ 要解决的事 ═══

前端明细表把**整表**写成一条 `checklist_responses`：

* `useM1Detail.ts`：`debouncedSave('M1-M1-2-full-data', { remark: JSON.stringify(detailRows) })`
* `useM2Detail.ts`：`M2-M2-2-listed-full-data` / `M2-M2-2-unlisted-full-data`，同形

而 M 的 provider `build_store_projection`（`phase5_m_cycle_common._build_store_projection`）
只认两种形态：`[{item_id, conclusion|remark}, …]` 与 `{item_id: value}`，逐键取标量。
喂前端真实载荷时它产出**一个** `M1-M1-2-full-data = '<整表 JSON 字符串>'` —— 而这个
stable_field_key **不在契约的受管字段里**（契约是 `flat_key_value`，键形如
`M1-m101-managed-company_code`）。

后果：首版发布 / 回写两条路径都拿不到任何一格受管字段的值，前端录的内容**一格都进不了 OO**。
这是「形态冲突」在运行时的真实表现，不是「前端少几个字段」。

═══ 判据 ═══

1. 前端真实载荷投影出的每个 key 都必须是契约里存在的 stable_field_key（否则就是死键）；
2. 明细行的每个字段要落到契约声明的那个 flat 键上（值等于前端行里的值）；
3. 未知键不得凭空出现在投影里（不得把 `full-data` 这种容器键当受管字段）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_m1_dividends_payable as M1  # noqa: E402
from app.services.workpaper_sync import phase5_m2_paid_in_capital as M2  # noqa: E402


def _managed_keys(provider) -> set[str]:
    """契约里全部 stable_field_key（受管字段的真源）。

    🔴 行表字段的 key 含 `{row_uuid}` 占位（`m1_detail_rows/{row_uuid}/company_code`），
    而展开后是 `m1_detail_rows/r1/company_code`。比对时把占位段替换成 `*` 再比。
    """
    payload = provider.build_contract_payload()
    keys: set[str] = set()
    for sheet in payload.get("sheets") or ():
        for table in sheet.get("tables") or ():
            for field in table.get("fields") or ():
                sfk = field.get("stable_field_key")
                if sfk:
                    keys.add(sfk)
    return keys


def _key_matches_managed(key: str, managed: set[str]) -> bool:
    """展开后的 key 是否对应某个受管字段（把 `{row_uuid}` 占位段当通配）。"""
    if key in managed:
        return True
    parts = key.split("/")
    for sfk in managed:
        tmpl = sfk.split("/")
        if len(tmpl) != len(parts):
            continue
        if all(t == p or t == "{row_uuid}" for t, p in zip(tmpl, parts)):
            return True
    return False


def _frontend_payload(item_id: str, rows: list[dict]) -> str:
    """前端真实写法的等价载荷：一个 item，remark 是整表 JSON。"""
    return json.dumps(
        [{"item_id": item_id, "remark": json.dumps(rows, ensure_ascii=False)}],
        ensure_ascii=False,
    )


M1_ROWS = [
    # 🔴 用契约的 column_key（snake_case）—— 前端行模型是驼峰（shareholderName / declaredAmount），
    #    两者不一致正是本 spec 登记的真实差异（`test_m_detail_keys_match_provider.py` 的 65 条基线），
    #    不在本测试的判据范围内。本测试只钉「容器键里的整表 JSON 能被展开成受管键」。
    {"rowId": "r1", "company_code": "C1", "prior_opening": 100, "increase_amount": 40},
    {"rowId": "r2", "company_code": "C2", "prior_opening": 200, "increase_amount": 80},
]


@pytest.fixture(scope="module")
def m1_keys() -> set[str]:
    return _managed_keys(M1)


@pytest.mark.parametrize("provider", [M1, M2], ids=["m1", "m2"])
def test_frontend_full_data_payload_yields_only_managed_keys(provider) -> None:
    """前端真实载荷不得投影出契约里不存在的键（死键 = 一格都写不进 OO）。"""
    keys = _managed_keys(provider)
    payload = _frontend_payload(f"{provider.CONFIG.item_prefix}M1-2-full-data", M1_ROWS)
    projection = provider.build_store_projection(payload, contract=provider.load_contract_from_disk())
    produced = set(projection.values)
    unknown = sorted(k for k in produced if not _key_matches_managed(k, keys))
    assert unknown == [], (
        f"{provider.ADAPTER_ID}: 投影出了契约里没有的键 {unknown} —— "
        "这些值物化时无处可写，前端录的内容会整批丢失"
    )


def test_m1_detail_rows_land_on_their_flat_keys(m1_keys: set[str]) -> None:
    """明细行要落到契约声明的行表键上，值等于行里的值。"""
    payload = _frontend_payload("M1-M1-2-full-data", M1_ROWS)
    projection = M1.build_store_projection(payload, contract=M1.load_contract_from_disk())
    values = {k: v.value for k, v in projection.values.items()}

    # 契约的行表指针形如 m1_detail_rows/{row_uuid}/{column_key}
    assert any(k.endswith("/company_code") for k in values), sorted(values)[:10]
    assert any(k.endswith("/prior_opening") for k in values), sorted(values)[:10]
    # 逐值核对：C1 / C2 都在，且金额按 amount 类型归一
    assert "C1" in values.values() and "C2" in values.values(), values
    assert 100 in [float(v) for v in values.values() if isinstance(v, (int, float))], values


def test_container_key_is_not_treated_as_a_managed_field(m1_keys: set[str]) -> None:
    """`*-full-data` 这类容器键不得出现在投影里。"""
    payload = _frontend_payload("M1-M1-2-full-data", M1_ROWS)
    projection = M1.build_store_projection(payload, contract=M1.load_contract_from_disk())
    containers = [k for k in projection.values if k.endswith("-full-data")]
    assert containers == [], f"容器键被当成受管字段：{containers}"


def test_flat_key_value_payload_still_works() -> None:
    """回归：flat_key_value 形态（后端自产）不得被本次改动弄坏。"""
    payload = json.dumps({"M1-m101-managed-company_code": "C9"}, ensure_ascii=False)
    projection = M1.build_store_projection(payload, contract=M1.load_contract_from_disk())
    assert projection.values["M1-m101-managed-company_code"].value == "C9"


def test_empty_payload_yields_empty_projection() -> None:
    for raw in ("[]", "null", "{}", ""):
        projection = M1.build_store_projection(raw, contract=M1.load_contract_from_disk())
        assert dict(projection.values) == {}, raw
