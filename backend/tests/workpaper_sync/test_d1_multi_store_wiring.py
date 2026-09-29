# -*- coding: utf-8 -*-
"""D1 多 store item 装配面 —— **真跑**出/回两方向，不只验接线。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 14（需求 3.1 / 3.3）
配套卡点：`backend/scripts/check/check_store_item_two_way_parity.py`（Gate 6）

═══ 为什么必须真跑 ═══

2026-09-28 实测：D1 扩容面（12 张受管 sheet / 18 个 store item）声明在伴生模块
`phase5_d1_expansion` 里，而**两个方向都只读 entry 模块** ⇒ 出方向只投影单数
`STORE_ITEM_ID` 那 1 个、回方向只镜像那 1 个，伴生模块的 `all_store_item_ids()`
**没有任何生产代码调用**。per-sheet 声明判据、instrumentation 判据、golden digest
当时**全绿** —— 它们只验声明层内部自洽，覆盖不到「声明 ↔ 装配链」这条边。

⇒ 本文件的判据必须**真的调用** `build_combined_store_projection` 与
`merge_projection_into_all_d1_stores`，并断言产出覆盖到每一个受管区。
只断言「函数存在 / 注册表字段非空」会重犯同一类假绿（需求 9.4 的纪律）。

🔴 本 spec 有直接教训：D4 曾有 13 条纯函数判据全绿而生产坏掉。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d1_07_memo as D107  # noqa: E402
from app.services.workpaper_sync import phase5_d1_expansion as EXP  # noqa: E402
from app.services.workpaper_sync import phase5_d1_notes_receivable as ENTRY  # noqa: E402
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    StoreKind,
    managed_field_specs,
)


def _synthetic_row(spec, seq: int) -> dict:
    """按 spec 的 field_specs 造一行占位数据（json_key 逐个填值，不手抄字段名）。"""
    row: dict = {spec.row_identity_key: f"synthetic-{spec.table_key}-{seq}"}
    for col_key, _col, _mode, value_type, json_key, _label, _gh in managed_field_specs(spec):
        row[json_key] = (
            round(100.0 + seq, 2) if value_type == "amount" else f"{col_key}-{seq}"
        )
    if spec.row_section_field:
        row[spec.row_section_field] = spec.row_section_value
    return row


@pytest.fixture(scope="module")
def contract():
    from app.services.workpaper_sync.contracts import parse_contract

    return parse_contract(ENTRY.build_contract_payload(), adapter_id=ENTRY.ADAPTER_ID)


@pytest.fixture(scope="module")
def synthetic_payloads() -> dict[str, str]:
    """每个受管 item 两行合成数据（dict 形态按 `{bankRows, commercialRows}` 造）。"""
    payloads: dict[str, str] = {}
    memo: dict[str, list] = {"bankRows": [], "commercialRows": []}
    for spec in EXP.managed_row_table_specs():
        rows = [_synthetic_row(spec, 1), _synthetic_row(spec, 2)]
        if spec.store_kind is StoreKind.dict:
            key = "bankRows" if spec.table_key == D107.ROWS_TABLE_KEY_BANK else "commercialRows"
            memo[key] = rows
            continue
        payloads[spec.store_item_id] = json.dumps(rows, ensure_ascii=False)
    payloads[D107.STORE_ITEM_ID_D107] = json.dumps(memo, ensure_ascii=False)

    # 🔴 2026-09-28 补静态受管区的合成载荷。
    #    它不在 `managed_row_table_specs()` 里（那只翻动态 spec），漏掉会让
    #    `merge_all` 拿到空载荷 ⇒ `applied=0` ⇒ 本文件的「空基线必须有写入」断言打红。
    #    🔴 行身份必须用**前端真实 rowId**（`fixed-bank`/`fixed-commercial`），
    #       随手编 slug 会让投影一条都命中不了（静态区按 rowId 定位，不用数组下标）。
    from app.services.workpaper_sync import phase5_d1_04_bad_debt as _D104

    notetype_rows = []
    for i, (row_id, _row_no, label) in enumerate(_D104.NOTETYPE_FIXED_ROWS, start=1):
        notetype_rows.append(
            {
                "rowId": row_id,
                "noteType": label,
                "isFixed": True,
                "priorUnadjusted": 100.0 * i,
                "priorAje": 1.0 * i,
                "priorRje": 2.0 * i,
                "currentUnadjusted": 200.0 * i,
                "currentAje": 3.0 * i,
                "currentRje": 4.0 * i,
            }
        )
    payloads[_D104.SPEC_D104_NOTETYPE.store_item_id] = json.dumps(
        notetype_rows, ensure_ascii=False
    )
    return payloads


def _rows_form_specs() -> tuple:
    """rows 形态且有契约 table 的 spec（combined/merge 都该覆盖的那批）。"""
    skip = set(ENTRY.STORE_ITEM_IDS_WITHOUT_CONTRACT_TABLE)
    return tuple(
        s
        for s in EXP.managed_row_table_specs()
        if s.store_kind is not StoreKind.dict and s.store_item_id not in skip
    )


# ═══════════════════════════════════════════════════════════════════════════
# 出方向：真跑 build_combined_store_projection
# ═══════════════════════════════════════════════════════════════════════════


def test_combined_projection_covers_every_managed_region(contract, synthetic_payloads) -> None:
    """🔴 核心判据：combined 投影必须覆盖**每一个**受管区（含 dict 形态的两区）。

    接通前它只覆盖 D1-3 那一个区 —— 这条判据当时会红。
    """
    proj = ENTRY.build_combined_store_projection(synthetic_payloads, contract=contract)
    keys = [str(k) for k in proj.stable_keys()]
    assert keys, "combined 投影为空 —— 装配链没跑通"

    expected_tables = {s.table_key for s in _rows_form_specs()}
    expected_tables |= {D107.ROWS_TABLE_KEY_BANK, D107.ROWS_TABLE_KEY_COMMERCIAL}
    covered = {k.split("/", 1)[0] for k in keys}
    assert expected_tables <= covered, (
        f"未被投影覆盖的受管区：{sorted(expected_tables - covered)}"
    )
    # row_keys 也必须逐区给出（materialize 的插行/位移依赖它）
    assert expected_tables <= set(proj.row_keys), (
        f"row_keys 缺区：{sorted(expected_tables - set(proj.row_keys))}"
    )
    for table_key in expected_tables:
        assert len(proj.row_keys[table_key]) == 2, (
            f"{table_key} 的 row_keys 应为 2 行合成数据，实得 {proj.row_keys[table_key]}"
        )


def test_combined_projection_covers_static_region(contract, synthetic_payloads) -> None:
    """静态受管区（D1-4 第三区）必须被 combined 投影覆盖。

    🔴 **本条是从「必须被跳过」翻转过来的**（2026-09-28）。原判据写的是
    「无契约 table 的 static_region item 必须被跳过，否则 `field_by_stable_key` 会抛」，
    并附了一句反向提示「第三区已被投影 ⇒ 它应当已进契约，请同步删除
    `STORE_ITEM_IDS_WITHOUT_CONTRACT_TABLE` 里的登记」。
    契约层 `static_tables` 建成、白名单清空后，**正是这句提示把我引到这里翻转它** ——
    失效条目反向检查生效的实例，留档不删。

    现在的正面语义：契约里有 static table ⇒ 投影必须覆盖它，否则该区在 OO 侧恒空
    （与 D4-35「声明了但装配链看不见」同型断口）。

    🔴 **2026-09-28 二次处置**：T7 裁决 A 撤回了静态第三区（`_INCLUDE_D104_NOTETYPE_STATIC`
    翻 False），本条随之整体 skip —— 与 O/P/T 三节 41 条静态区判据同款门控，
    **不删**，开关翻回 True 时自动复活。撤回态下的正面判据（combined 投影不得泄漏
    静态区键）由 `test_d104_static_region_excluded.py` 承接，两边不重叠。
    """
    if not EXP._INCLUDE_D104_NOTETYPE_STATIC:
        pytest.skip(
            "静态第三区按 T7 裁决 A 处于撤回态；撤回态判据见 "
            "test_d104_static_region_excluded.py"
        )
    proj = ENTRY.build_combined_store_projection(synthetic_payloads, contract=contract)
    covered = {str(k).split("/", 1)[0] for k in proj.stable_keys()}
    assert "bad_debt_notetype_rows" in covered, (
        "静态受管区没进 combined 投影 ⇒ 它在 OO 侧会恒空"
    )
    # 且 `STORE_ITEM_IDS_WITHOUT_CONTRACT_TABLE` 必须已清空（两者是同一件事的两面）
    assert ENTRY.STORE_ITEM_IDS_WITHOUT_CONTRACT_TABLE == ()


def test_combined_projection_bad_payload_stays_domain_error(contract, synthetic_payloads) -> None:
    """畸形载荷必须是 domain 错误（4xx），且错误消息点明是哪个 item。

    收敛成薄转发时漏做错误转译，正是 D3/D5/D6/D7 在 Task 16/17 从 4xx 退化成 opaque 500
    的根因（2026-09-26 实测）。本函数一开始就带转译，这条钉住它。
    """
    victim = _rows_form_specs()[1]
    broken = dict(synthetic_payloads)
    broken[victim.store_item_id] = '{"not": "an array"}'
    with pytest.raises(ENTRY.StorePayloadError) as ei:
        ENTRY.build_combined_store_projection(broken, contract=contract)
    assert victim.store_item_id in str(ei.value), (
        f"错误消息未点明出问题的 item：{ei.value}"
    )
    assert getattr(ei.value, "error_code", None), "StorePayloadError 必须带 error_code 才能映射 4xx"


# ═══════════════════════════════════════════════════════════════════════════
# 回方向：真跑 merge_projection_into_all_d1_stores + 往返等值
# ═══════════════════════════════════════════════════════════════════════════


def test_merge_all_covers_every_rows_form_item(contract, synthetic_payloads) -> None:
    """回方向整体镜像必须为**每个** rows 形态 item 返回结果（dict 形态走 dedicated 通路）。

    🔴 2026-09-28 更新期望集：静态受管区（D1-4 第三区 `D1-bd-notetype-rows`）接通后
    **也由 merge_all 返回**。它不在 `_rows_form_specs()` 里 —— 那个 helper 遍历
    `managed_row_table_specs()`，而后者只翻**动态**（`excel_table`）spec：静态 spec 的
    `row_identity_key` 为空，行表引擎会拒它（`store_row_identity()` 抛错）。
    ⇒ 期望集 = 动态 rows 形态 ∪ 静态受管区。
    """
    proj = ENTRY.build_combined_store_projection(synthetic_payloads, contract=contract)
    updates = ENTRY.merge_projection_into_all_d1_stores(projection=proj, base_by_item={})
    expected = {s.store_item_id for s in _rows_form_specs()} | {
        item_id for item_id, _fn in ENTRY._static_region_merge_handlers()
    }
    assert set(updates) == expected, (
        f"缺={sorted(expected - set(updates))} 多={sorted(set(updates) - expected)}"
    )
    assert D107.STORE_ITEM_ID_D107 not in updates, (
        "dict 形态不得由 merge_all 返回 —— 它走 dedicated_items 的 merge_d17_from_projection，"
        "两条路都返会重复写库"
    )
    for item_id, (rows, applied, _visited, _touched) in updates.items():
        assert applied > 0, f"{item_id} applied=0 ⇒ 投影没合进去（空基线时必须有写入）"
        assert len(rows) == 2, f"{item_id} 应合出 2 行，实得 {len(rows)}"


@pytest.mark.parametrize("spec", _rows_form_specs(), ids=lambda s: s.table_key)
def test_roundtrip_values_survive_per_region(spec, contract, synthetic_payloads) -> None:
    """逐区往返等值：合成行 → combined 投影 → merge 回行数组，可编辑字段逐值不变。

    只比 `editable` 字段：`formula` 字段在投影里被标 protected、merge 时按设计跳过
    （公式由 OO 重算，不该被 store 值覆盖）。
    """
    proj = ENTRY.build_combined_store_projection(synthetic_payloads, contract=contract)
    updates = ENTRY.merge_projection_into_all_d1_stores(projection=proj, base_by_item={})
    merged_rows, _applied, _visited, _touched = updates[spec.store_item_id]

    original = json.loads(synthetic_payloads[spec.store_item_id])
    by_id = {r[spec.row_identity_key]: r for r in merged_rows}
    editable_keys = [
        row[4]
        for row in managed_field_specs(spec)
        if row[2] == "editable"
    ]
    assert editable_keys, f"{spec.table_key} 无 editable 字段 —— 本判据对它没有覆盖面"
    for src in original:
        rid = src[spec.row_identity_key]
        assert rid in by_id, f"{spec.table_key} 行 {rid} 往返后丢失"
        got = by_id[rid]
        for json_key in editable_keys:
            assert got.get(json_key) == src.get(json_key), (
                f"{spec.table_key} 行 {rid} 字段 {json_key} 往返不等："
                f"{src.get(json_key)!r} → {got.get(json_key)!r}"
            )


def test_merge_all_preserves_unrelated_base_rows(contract, synthetic_payloads) -> None:
    """基线里已有的、投影没碰到的行必须原样保留（不能被整表覆盖）。"""
    spec = _rows_form_specs()[0]
    keeper = {spec.row_identity_key: "pre-existing-keeper", "__marker__": "keep-me"}
    # 给 keeper 填上首列业务名称，避免被幽灵行防护当成空壳行剔除。
    name_key = managed_field_specs(spec)[spec.ghost_row_anchor_index][4]
    keeper[name_key] = "既有行"

    proj = ENTRY.build_combined_store_projection(synthetic_payloads, contract=contract)
    updates = ENTRY.merge_projection_into_all_d1_stores(
        projection=proj, base_by_item={spec.store_item_id: [keeper]}
    )
    rows, _applied, _visited, _touched = updates[spec.store_item_id]
    ids = [r.get(spec.row_identity_key) for r in rows]
    assert "pre-existing-keeper" in ids, f"既有行被丢掉了：{ids}"
    kept = next(r for r in rows if r.get(spec.row_identity_key) == "pre-existing-keeper")
    assert kept.get("__marker__") == "keep-me", "既有行的非受管字段被抹掉"


def test_dict_form_item_is_wired_through_dedicated_path(contract, synthetic_payloads) -> None:
    """dict 形态（D1-7 备查簿）走注册表 `dedicated_items`，且其 merge 门面真能合出两区。"""
    from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

    plan = STORE_MERGE_REGISTRY["d1.notes_receivable_detail"]
    ded = [d for d in plan.dedicated_items if d.provider_module == "phase5_d1_07_memo"]
    assert len(ded) == 1, f"D1-7 的 dedicated 登记应恰 1 条，实得 {ded}"
    assert ded[0].base_kind == "dict"

    proj = ENTRY.build_combined_store_projection(synthetic_payloads, contract=contract)
    merged, applied, _visited = D107.merge_d17_from_projection(
        projection=proj, base_state=None
    )
    assert applied > 0, "D1-7 dict store 的 merge 没有任何字段落地"
    assert len(merged.get("bankRows") or []) == 2
    assert len(merged.get("commercialRows") or []) == 2


def test_mutation_without_projection_slice_rows_bleed_across_regions(
    contract, synthetic_payloads, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 变异反证：去掉 `_projection_slice_for` 的切片 ⇒ 别区的行必须串进本区。

    这条钉住的是 2026-09-28 真跑时抓到的缺陷：框架层
    `merge_projection_into_store_rows` 遍历整份 projection、只按 `field_id` 过滤，
    而不同区列名重名（`note_type`/`bill_amount` 等）⇒ 不切片就会把别区行全吞进来。
    实测不切片时 `D1-cat-rows` 合出 16 行（应为 2）。

    没有这条，将来有人"简化"掉切片时不会有任何判据变红（往返等值判据只查
    原始行是否还在，不查是否多出别人的行）。
    """
    monkeypatch.setattr(ENTRY, "_projection_slice_for", lambda proj, _table_key: proj)
    proj = ENTRY.build_combined_store_projection(synthetic_payloads, contract=contract)
    updates = ENTRY.merge_projection_into_all_d1_stores(projection=proj, base_by_item={})
    bloated = {
        item_id: len(rows)
        for item_id, (rows, *_rest) in updates.items()
        if len(rows) > 2
    }
    assert bloated, (
        "去掉切片后行数竟然没膨胀 —— 要么框架层已自带前缀过滤（那切片可删，"
        "但要先改本判据），要么合成数据的列名恰好不重名（那本判据失去覆盖面）"
    )
