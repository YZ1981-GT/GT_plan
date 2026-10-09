# -*- coding: utf-8 -*-
"""D1 各受管区 spec 的 `json_key` 必须与**前端真实持久化键**一致。

spec: d1-sync-row-table-engine-and-d1-coverage · 2026-09-28 新抓缺陷（Task 25~29 前置）

═══ 为什么这条判据必须存在 ═══

`RowTableSheetSpec.field_specs` 的第 5 元组位是 `json_key`，它进契约成为
`json_pointer = /rows/{row_uuid}/{json_key}`，是**寻址 HTML store 行对象的唯一依据**。

若它与前端实际写入的键不一致，两个方向都断：

* HTML → OO（materialize）：按 pointer 取不到值 ⇒ 写空进 Excel
  （连带**擦掉**审计师直接在 Excel 里填的内容）；
* OO → HTML（extract/merge）：把 Excel 值写进前端**从不读**的键 ⇒ 静默丢弃。

🔴🔴 **为什么既有判据全都抓不到**：本 entry 的 23 条往返判据（含 16 条逐区参数化）
都用 **spec 自己的 json_key** 造合成行，再断言「读回等值」——
键错了也自洽，**结构上恒绿**。这是本仓库反复出现的
「测试镜像同款错误 ⇒ 恒绿而生产恒死」（D1 四锚点 / D6-D7 聚合键）的又一例。
能抓住它的判据必须拿**前端源码**（写入方）或**真库载荷**当第二个独立口径。

═══ 判定口径 ═══

前端是**权威写入方**：值由 `serializeXxx()` 落库，spec 只是读它。
故以前端源码字面量为真、spec 为待校验方。真库载荷已独立复核与前端一致
（2026-09-28 现查 14 个有载荷 item），排除了「真库陈旧」这一替代解释。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FRONTEND = (
    Path(__file__).resolve().parents[3]
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "composables"
)

# ═══════════════════════════════════════════════════════════════════════════
# 🔴 首轮实测的 26 列错配，经逐列核对模板列头后**分成两类**（关键：它们不是一种缺陷）
# ═══════════════════════════════════════════════════════════════════════════
#
# 类 ①「真改名」13 列 —— Excel 列语义与前端字段**一一对应**，只是 spec 的 json_key
#      照模板列头语义命名而没读前端。**已按裁决 B1 修复**（2026-09-28）：
#        D1-bd-individual-rows / D1-bd-portfolio-rows 各 6 列
#          item→label · provision→currentProvision · otherIncrease→currentRecovery
#          reversal→currentReversal · writeOff→currentWriteOff · otherDecrease→currentOther
#        D1-bd-notetype-rows 1 列：item→noteType（该区前端用票据种类名，不是 label）
#      定位依据：Excel F/H/I 列头「计提/转回/核销」与前端 UI「本期计提/本期转回/本期核销」
#      逐字相同作三个锚，五列顺序一致 ⇒ G/J 的对应在位置上无歧义。
#
# 类 ②「HTML 无字段」13 列 —— **Excel 有这一列且列头语义明确，而前端根本没有对应字段**。
#      改 json_key 解决不了（改了只会把别的语义的值写进这一列）⇒ **不属 B1 范围**，
#      需要独立裁决（给前端补字段 / 把该列声明为不受 HTML 管）。下方 KNOWN_HTML_FIELD_GAPS。

#: 类 ②：Excel 有列但 HTML 无对应字段。
#:
#: 🔴🔴 **这不是惰性缺陷**：`split_store_row` 对每个声明列都 yield，缺键时值为 `None`，
#:    而 `excel_materialize._render_number(None)` 返回 **`"0"`**、`inline_text` 返回 `""`
#:    ⇒ 每次 materialize 都会把这些 Excel 单元格**写成 0 / 清空**，
#:    擦掉审计师直接在 OO 侧填的内容。
#:
#: 🔴 **棘轮基线：只许变短**。
#:
#: ✅ **2026-09-28 已清零**：用户裁决「补 8 个字段」⇒ D1-10 的 `payer` 与 D1-13 的 7 列
#:    已在前端补齐（interface + 持久化白名单 + 默认工厂 + UI 列），本表因此为空。
#:    另 5 列（D1-4 第三区 F~J）先前已按「分权拥有」从 field_specs 排除。
#:    ⇒ 首轮 26 列 = 类 ① 真改名 13（改 spec）+ 类 ② 13（5 排除 + 8 补前端），**全部处置完毕**。
KNOWN_HTML_FIELD_GAPS: dict[str, tuple[str, ...]] = {
    # ✅ D1-4 第三区原有 5 列（模板 F~J）**已处置**（2026-09-28）：
    #    前端 `serializeNoteTypeRows()` 对本区一个都不落 ⇒ 已从该区 field_specs 显式排除
    #    （`_HTML_UNOWNED_COLUMNS_D104_NOTETYPE`），语义改为**分权拥有**：F~J 由审计师直接
    #    在 Excel 填、HTML 不碰，模板 K23 的 `=B23+SUM(F23:G23)-SUM(H23:J23)` 因此能正确求值。
    #    已验证安全：`_plan_static_writes` 对投影里没有的键 `continue`（不写），
    #    `verify_unmanaged_regions` 比对 before/after 而未写的格前后相同 ⇒ 不判漂移。
    #
    # ✅ D1-10 `payer`(Excel K 付款人名称) 与 D1-13 的 7 列
    #    （voucherDate B / counterDetail F / creditAmount H / supportDoc I /
    #     check4 M / check5 N / isAbnormal P）**已补进前端**（2026-09-28）。
    #    下方 `FRONTEND_NEW_FIELD_ANCHORS` 逐个钉住「四处都改到了」。
}

#: 本轮补进前端的 8 个字段：(文件, 字段名, Excel 列)。
#:
#: 🔴 补一个字段要改**四处**，缺任何一处都等于没补：
#:   ① `d1InspectionFormulas.ts` 的行 interface（类型）
#:   ② 该 composable 的**持久化白名单**（`*_STRING_FIELDS` / `*_NUMERIC_FIELDS`）
#:      —— 不在白名单里 `serialize*` 不落库，落不了库同步层 `json_pointer` 就指空
#:   ③ 空行工厂（`emptyVouchingRow` / `emptyInventoryCountRow`）—— 否则新行该字段 undefined
#:   ④ 宿主 `.vue` 的表格列 —— 否则审计师看不见、填不了
FRONTEND_NEW_FIELD_ANCHORS: tuple[tuple[str, str, str], ...] = (
    ("useD1InventoryCount.ts", "payer", "K"),
    ("useD1SamplingVouching.ts", "voucherDate", "B"),
    ("useD1SamplingVouching.ts", "counterDetail", "F"),
    ("useD1SamplingVouching.ts", "creditAmount", "H"),
    ("useD1SamplingVouching.ts", "supportDoc", "I"),
    ("useD1SamplingVouching.ts", "check4", "M"),
    ("useD1SamplingVouching.ts", "check5", "N"),
    ("useD1SamplingVouching.ts", "isAbnormal", "P"),
)

#: 字段 → 宿主 `.vue`
_HOST_OF = {
    "useD1InventoryCount.ts": "D1TabInventoryCount.vue",
    "useD1SamplingVouching.ts": "D1TabSamplingVouching.vue",
}

#: 向后兼容别名（旧判据名），指向类 ② —— 类 ① 已修完故不再单列。
KNOWN_JSON_KEY_MISMATCHES = KNOWN_HTML_FIELD_GAPS

#: 真库无载荷 ⇒ 本轮无法用「真库」这一口径判定（前端口径仍可，留待修复批次）。
UNVERIFIABLE_EMPTY_STORE: tuple[str, ...] = (
    "D1-cat-rows",
    "D1-endorse-discount-rows",
    "D1-endorse-transfer-rows",
    "D1-sampling-specific-samples",
)

#: 前端持久化键的**源码字面量锚点**：(文件, 必须出现的键, ...)
#: 存在的意义 = 前端若改键名，本表对不上 ⇒ 立刻打红，而不是让基线悄悄过期。
FRONTEND_KEY_ANCHORS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "useD1BadDebt.ts",
        (
            "currentProvision", "currentRecovery", "currentReversal",
            "currentWriteOff", "currentOther", "label", "noteType",
        ),
    ),
    ("useD1InventoryCount.ts", ("endorseDate",)),
    ("useD1SamplingVouching.ts", ("maturityDate", "existenceCheck", "accuracyCheck")),
)


def _spec_json_keys() -> dict[str, dict[str, tuple[str, str]]]:
    """store_item_id -> {json_key: (列, mode)}（含不在 managed_row_table_specs 的静态区）。"""
    from app.services.workpaper_sync import phase5_d1_04_bad_debt as d104
    from app.services.workpaper_sync import phase5_d1_expansion as exp

    out: dict[str, dict[str, tuple[str, str]]] = {}
    for spec in list(exp.managed_row_table_specs()) + [d104.SPEC_D104_NOTETYPE]:
        d = out.setdefault(spec.store_item_id, {})
        for fs in spec.field_specs:
            d[fs[4]] = (fs[1], fs[2])
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 1. 前端源码锚点仍在 —— 基线不会悄悄过期
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("filename,keys", FRONTEND_KEY_ANCHORS)
def test_frontend_persisted_keys_still_present(filename: str, keys: tuple[str, ...]) -> None:
    """前端若改了持久化键名，本文件的基线即失效 ⇒ 必须立刻打红。"""
    path = _FRONTEND / filename
    assert path.exists(), f"前端文件已移动/改名：{path}"
    src = path.read_bytes().decode("utf-8")
    for key in keys:
        assert key in src, (
            f"{filename} 已不含前端持久化键 {key!r} —— "
            "KNOWN_JSON_KEY_MISMATCHES 的判定依据变了，需重新对账后更新基线"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 棘轮：错配集合只许变短
# ═══════════════════════════════════════════════════════════════════════════


def test_mismatch_baseline_entries_are_still_declared_in_spec() -> None:
    """🔴 反向检查：基线里的每个 (item, json_key) 必须**真的**还在 spec 里。

    修好某列后 spec 不再声明该 json_key ⇒ 本条打红，强制把它从基线删掉。
    没有这条，基线会变成「越修越对不上、但没人知道」的死清单。
    """
    spec_keys = _spec_json_keys()
    stale: list[str] = []
    for item, keys in KNOWN_JSON_KEY_MISMATCHES.items():
        declared = spec_keys.get(item)
        if declared is None:
            stale.append(f"{item}（整个 item 已不在 spec 中）")
            continue
        for k in keys:
            if k not in declared:
                stale.append(f"{item}/{k}")
    assert not stale, (
        "基线中的下列条目已失效（spec 不再声明它们）⇒ 说明已被修复，"
        f"请从 KNOWN_JSON_KEY_MISMATCHES 删除：{stale}"
    )


def test_gap_baseline_is_empty() -> None:
    """✅ 类 ②「Excel 有列、HTML 无字段」已清零（棘轮到底）。

    首轮实测 26 列错配 = 类 ① 真改名 **13**（改 spec 对齐前端）
    + 类 ② **13**（D1-4 第三区 5 列按「分权拥有」排除 + 其余 8 列补进前端）。
    """
    assert KNOWN_HTML_FIELD_GAPS == {}, (
        f"缺口又出现了：{KNOWN_HTML_FIELD_GAPS} —— 新接的区声明了 HTML 没有的列，"
        "materialize 会把这些 Excel 格写成 0/清空"
    )


@pytest.mark.parametrize("filename,field,column", FRONTEND_NEW_FIELD_ANCHORS)
def test_new_field_is_wired_in_all_four_places(filename: str, field: str, column: str) -> None:
    """🔴 补字段必须**四处齐全**，缺任何一处等于没补。

    这条判据存在的理由：只加 interface 字段最容易「看起来补了」——
    但不进持久化白名单就不落库，不进 UI 就填不了，两者都让同步层的
    `json_pointer` 继续指空。
    """
    composable = (_FRONTEND / filename).read_bytes().decode("utf-8")
    types_src = (_FRONTEND / "d1InspectionFormulas.ts").read_bytes().decode("utf-8")
    host = (_FRONTEND.parent / "d1" / _HOST_OF[filename]).read_bytes().decode("utf-8")

    # ① 类型
    assert f"{field}:" in types_src, f"{field} 未进行 interface（d1InspectionFormulas.ts）"
    # ② 持久化白名单：字段名必须以 `'field',` 形态出现在某个 *_FIELDS 数组里
    assert f"'{field}'" in composable, (
        f"{field} 未进 {filename} 的持久化白名单 ⇒ serialize 不落库、json_pointer 指空"
    )
    # ③ 空行工厂默认值
    assert f"{field}: " in composable, f"{field} 未进 {filename} 的空行工厂 ⇒ 新行该字段 undefined"
    # ④ UI 可填：宿主里必须有针对该字段的写入调用
    assert f"'{field}'" in host, f"{field} 在 {_HOST_OF[filename]} 里没有可编辑的表格列"
    assert f"row.{field}" in host, f"{_HOST_OF[filename]} 未把 {field} 绑到输入控件"


def test_spec_declares_every_new_field_at_its_excel_column() -> None:
    """反向：spec 侧的 `json_key` 与 Excel 列**必须**与前端新字段逐一对上。

    没有这条，前端补了字段但列字母对错了也发现不了（会把值写进别的列）。
    """
    spec_keys = _spec_json_keys()
    expect_item = {
        "useD1InventoryCount.ts": "D1-inventory-rows",
        "useD1SamplingVouching.ts": "D1-sampling-vouching-rows",
    }
    for filename, field, column in FRONTEND_NEW_FIELD_ANCHORS:
        declared = spec_keys[expect_item[filename]]
        assert field in declared, f"spec 未声明 {field}"
        got_col = declared[field][0]
        assert got_col == column, (
            f"{field} 的 Excel 列不符：spec={got_col} 期望={column} —— 值会被写进别的列"
        )


def test_notetype_region_excludes_html_unowned_columns() -> None:
    """🔴 第三区必须**显式排除** F~J（HTML 不持有），且只排除这五列。

    正面：9 列（A/B/C/D/E/K/L/M/N）齐；反面：F~J 一列都不许出现。
    没有这条，把它们加回去只会在 materialize 时静默把 F23:J24 写成 0。
    """
    from app.services.workpaper_sync import phase5_d1_04_bad_debt as d104

    cols = [fs[1] for fs in d104.SPEC_D104_NOTETYPE.field_specs]
    assert cols == ["A", "B", "C", "D", "E", "K", "L", "M", "N"], (
        f"第三区列集不对：{cols}（F~J 应被排除，其余九列应齐）"
    )
    assert d104._HTML_UNOWNED_COLUMNS_D104_NOTETYPE == frozenset({"F", "G", "H", "I", "J"})

    # 两个动态区**不受影响**：仍是全 14 列
    for spec in (d104.SPEC_D104_INDIVIDUAL, d104.SPEC_D104_PORTFOLIO):
        assert len(spec.field_specs) == 14, (
            f"{spec.store_item_id} 的列数被误伤：{len(spec.field_specs)}"
        )

    # 派生而非复制：改共用字段面的表头应同步反映到第三区
    shared = {fs[0]: fs[5] for fs in d104._FIELD_SPECS_D104}
    for fs in d104.SPEC_D104_NOTETYPE.field_specs:
        assert fs[5] == shared[fs[0]], f"{fs[0]} 表头与共用字段面漂移（说明被复制了一份）"


def test_class1_renames_are_really_fixed() -> None:
    """类 ① 的 13 列必须**真的**已改名 —— 防「改了一半」与回退。

    正面判据：spec 现在声明的是前端那组键；反面判据：旧键一个都不许再出现。
    """
    spec_keys = _spec_json_keys()
    dynamic_expected = {
        "label", "currentProvision", "currentRecovery",
        "currentReversal", "currentWriteOff", "currentOther",
    }
    old_keys = {"item", "provision", "otherIncrease", "reversal", "writeOff", "otherDecrease"}

    for item in ("D1-bd-individual-rows", "D1-bd-portfolio-rows"):
        declared = set(spec_keys[item])
        assert dynamic_expected <= declared, (
            f"{item} 缺少前端实际键：{sorted(dynamic_expected - declared)}"
        )
        assert not (old_keys & declared), (
            f"{item} 仍在声明旧键：{sorted(old_keys & declared)}"
        )

    # 第三区 A 列是 `noteType` 而非 `label`（三区内部就不同）
    nt = set(spec_keys["D1-bd-notetype-rows"])
    assert "noteType" in nt, "第三区 A 列未改成 noteType"
    assert "label" not in nt, "第三区误用了动态区的 label"
    assert "item" not in nt


def test_unverifiable_items_really_have_no_contract_conflict_claim() -> None:
    """空分母 item 必须显式登记，不得被当成「已对齐」。"""
    spec_keys = _spec_json_keys()
    for item in UNVERIFIABLE_EMPTY_STORE:
        assert item in spec_keys, f"{item} 已不在 spec 中，请更新空分母清单"
        assert item not in KNOWN_JSON_KEY_MISMATCHES, (
            f"{item} 同时出现在「空分母」与「已确认错配」两张表里，口径矛盾"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 原始诉求：json_key 应当与前端一致（钉住，修好后此条会 XPASS 逼迫摘 xfail）
# ═══════════════════════════════════════════════════════════════════════════


# ✅ 原 `xfail(strict=True)` 已摘除（2026-09-28）：类 ② 13 列全部处置完毕
#    （D1-4 第三区 5 列按「分权拥有」排除 + 其余 8 列补进前端）。
#    strict xfail 在缺陷修好后会 XPASS 并**报错**，正是它逼我来摘这个标记 —— 机制生效。
def test_no_html_field_gap_at_all() -> None:
    assert not KNOWN_HTML_FIELD_GAPS, (
        "仍有「Excel 有列但 HTML 无字段」的受管列："
        + json.dumps(KNOWN_HTML_FIELD_GAPS, ensure_ascii=False, sort_keys=True)
    )
