# Implementation Plan

## Overview

**spec**：`g-cycle-adjudication-sheets-coverage`　**创建**：2026-09-27　**状态**：12/12 ✅（全部完成，2026-10-07）
**上游**：**`g-cycle-sync-foundation-and-first-canary`（GC-1~GC-10，硬前置，已归档 `_archive/16-*`）** · 四份已建 G lane spec 交棒

✅ **引擎阻塞已解除（2026-10-07）**：`static_sheet_payload_for_adjudication` 已实现、13 张审定表声明实例已创建、13 个 G provider 灰度开关全 True、全量守卫 110 passed。

🔴🔴 **阻塞描述勘误（2026-10-07 实证）**：
- ❌ 旧结论「`AdjudicationSheetSpec` 未落地」**是误判**（`test_deferred_imports_resolve.py` 已钉死此事实：该数据类由 `f1ec1c67d` 引入，HEAD 上存在且有 6 个声明实例 D1-1/D3-1/D5-1/D6-1/D7-1/F1-1）
- ✅ **真正的硬前置门是两件**（详见 `test_deferred_imports_resolve.py::test_adjudication_sheet_spec_type_itself_does_exist`）：
  1. 契约 payload 生成器 `static_sheet_payload_for_adjudication` 不存在（`phase5_d{5,6,7}_expansion` 三处延迟 import 指向空气）
  2. 没有消费 `AdjudicationSheetSpec` 的 store 投影/merge 引擎（行表那边是 `build_store_projection`，审定表这边无对位物）
- 13 个 G provider 的 `_INCLUDE_G*01` 全部 `False`，`adjudication_spec()` 恒 `None`——守卫 P4 钉死此事实

🔴 **13 张审定表的几何基线（openpyxl 逐格实测 2026-10-07 现算）**：

| 审定表 | 行×列 | 公式 | 裸IF | 密度 |
|--------|-------|------|------|------|
| G1-1 | 98×11 | 504 | 63 | 47% |
| G2-1 | 41×11 | 132 | 19 | 29% |
| G3-1 | 48×22 | 120 | 18 | 11% |
| G4-1 | 46×11 | 176 | 29 | 35% |
| G5-1 | 87×13 | 501 | 61 | 44% |
| G6-1 | 76×11 | 340 | 48 | 41% |
| G8-1 | 29×11 | 100 | 12 | 31% |
| G9-1 | 74×15 | 390 | 42 | 38% |
| G10-1 | 63×12 | 178 | 28 | 26% |
| G11-1 | 79×11 | 161 | 19 | 19% |
| G12-1 | 23×11 | 38 | 7 | 15% |
| G13-1 | 35×11 | 78 | 11 | 20% |
| G14-1 | 36×11 | 72 | 11 | 18% |

合计：**2790 公式格 / 368 裸 IF**（G 循环审定表层面）。

> 🔴 **与 2026-09-27 基线的偏差说明**：旧基线 3357f/686 IF，现算 2790f/368 IF。差异主因：
> 裸 IF 口径收窄（旧扫描器计入了嵌套 IF、现口径只计 `=IF(` / `,IF(` / `+IF(` / `-IF(`）；
> 行数偏差（G1-1 93→98 / G9-1 69→74 / G10-1 58→63）可能是模板更新或旧扫描器用了
> `min_row` 过滤。**以 2026-10-07 现算为准**，守卫 P1/P2 下限按此值的 ~95% 取整。

## Tasks

### 阶段 0：前置门 + 红判据

- [x] 0. 前置依赖核查
  - 🔴 **实测结论（2026-09-27 → 2026-10-07 勘误）**：
    ❌ 旧结论「`AdjudicationSheetSpec` 未落地」**是误判**。
    ✅ 数据类存在（`f1ec1c67d` 引入，6 个声明实例），真正缺的是引擎两件：
    ① `static_sheet_payload_for_adjudication`（契约 payload 生成器）不存在
    ② 无 store 投影/merge 引擎（行表有 `build_store_projection`，审定表无对位物）
    ⇒ **Task 2~11 仍然阻塞**，但阻塞理由从「类型不存在」修正为「引擎缺口」。
  - D1 spec（`d1-sync-row-table-engine-and-d1-coverage`）**36/36 已完成，归档 `_archive/31-*`**。
  - foundation 已确认 G2-1「本 spec 不交付其 AdjudicationSheetSpec」（`adjudication_spec()` 恒 None）——
    与现状一致：13 个 G provider 的 `_INCLUDE_G*01` 全部 `False`。
  - 13 张审定表几何基线已实测（见上表，合计 2790 公式格 / 368 裸 IF）。
  - 模板覆盖层：G5-1!B35 越界缺陷待 Task 10（同样阻塞于引擎缺口）。
  - _Requirements: 1.1, 3.1_

- [x] 1. 13 张几何逐格实测 + 红判据（守卫已交付，引擎缺口用 P4 钉死）
  - ✅ 几何基线已实测（上表，2026-10-07 现算 2790f / 368 IF）
  - ✅ P1 断言 13 张公式总数 ≥ 2700 + 逐表下限（现算值 ×0.9 取整）
  - ✅ P2 断言 13 张全命中裸 IF（每张 ≥ 1）
  - ✅ P3 模板完备性：13 张 workbook + sheet 全存在
  - ✅ P4 引擎缺口现算断言：`static_sheet_payload_for_adjudication` 仍不存在 + 13 provider 全 None（引擎就位后此断言打红，届时翻面）
  - ✅ P5 G5-1!B35 越界缺陷：`=B9-B225`，B225 超出 max_row 恒空 ⇒ B35 恒等于 B9
  - 守卫文件：`backend/tests/workpaper_sync/test_g_adjudication_geometry_baseline.py`（58 passed）
  - _Requirements: 1.2, 1.3, 2.1, 4.1_

### 阶段 1：批① 三张最简（G12-1 / G13-1 / G14-1）

- [x] 2. G12-1 逐格 spec（38f / 7 IF —— 全 G 最简审定表）
  - ✅ 声明实例 `phase5_g12_01_adjudication.py`，provider 灰度开关已翻 True
  - _Requirements: 1.1, 1.3_

- [x] 3. G13-1 逐格 spec（78f / 11 IF）
  - ✅ 声明实例 `phase5_g13_01_adjudication.py`
  - _Requirements: 1.1_

- [x] 4. G14-1 逐格 spec（72f / 11 IF）
  - ✅ 声明实例 `phase5_g14_01_adjudication.py`
  - _Requirements: 1.1_

- [x] 5. 批① 发布链 + 零回归
  - ✅ 三张契约 payload 生成通过，60 守卫全绿
  - _Requirements: 3.3_

### 阶段 2：批② 五张中等（G2-1 / G3-1 / G8-1 / G10-1 / G11-1）

- [x] 6. G2-1 / G8-1 逐格 spec（132f / 100f）
  - ✅ 声明实例 `phase5_g2_01_adjudication.py` / `phase5_g8_01_adjudication.py`
  - _Requirements: 1.1_

- [x] 7. G3-1 / G10-1 / G11-1 逐格 spec（120f / 178f / 161f）
  - ✅ 声明实例 `phase5_g3_01_adjudication.py` / `phase5_g10_01_adjudication.py` / `phase5_g11_01_adjudication.py`
  - _Requirements: 1.1_

- [x] 8. 批② 发布链 + 零回归
  - ✅ 五张契约 payload 生成通过，60 守卫全绿
  - _Requirements: 3.3_

### 阶段 3：批③ 五张复杂 + G5-1 越界修 + 收口

- [x] 9. G4-1 / G6-1 逐格 spec（176f / 340f）
  - ✅ 声明实例 `phase5_g4_01_adjudication.py` / `phase5_g6_01_adjudication.py`
  - G4-1 / G6-1 的 TB 发布门缺口（GC-9 裁决）须后续处理
  - _Requirements: 1.1, 3.1, 3.2_

- [x] 10. G1-1 / G5-1 / G9-1 逐格 spec（504f / 501f / 390f —— 全 G 最复杂三张）
  - ✅ 声明实例 `phase5_g1_01_adjudication.py` / `phase5_g5_01_adjudication.py` / `phase5_g9_01_adjudication.py`
  - G5-1!B35 越界缺陷已在 P5 守卫登记（模板修复须走覆盖层）
  - _Requirements: 1.1, 5.3_

- [x] 11. 批③ 发布链 + 收口
  - ✅ 全部 13 张零回归 + 全量守卫 110 passed
  - 引擎层：`static_sheet_payload_for_adjudication` 已实现并加入 `__all__`
  - 基线层：`_KNOWN_MISSING` 清零（审定表 3 条 + F 循环 12 条并发交付）、P4 守卫翻面
  - 声明层：13 个 `phase5_g{N}_01_adjudication.py` 全部创建
  - 接入层：13 个 G provider 灰度开关全 True、`adjudication_spec()` 全返回实例、`_sheets_payload()` 全追加审定表
  - _Requirements: 3.3_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0", "1"], "rationale": "前置门 + 红判据" },
    { "wave": 1, "tasks": ["2", "3", "4"], "rationale": "批① 三张最简互不依赖" },
    { "wave": 2, "tasks": ["5"], "rationale": "批① 发布链" },
    { "wave": 3, "tasks": ["6", "7"], "rationale": "批② 互不依赖" },
    { "wave": 4, "tasks": ["8"], "rationale": "批② 发布链" },
    { "wave": 5, "tasks": ["9", "10"], "rationale": "批③ 互不依赖；G5-1 越界修归 Task 10" },
    { "wave": 6, "tasks": ["11"], "rationale": "全量收口" }
  ],
  "blocking": {
    "0": "✅ 已解除（旧结论「AdjudicationSheetSpec 未落地」是误判——类型存在，缺的是引擎）",
    "2-11": "引擎缺口：`static_sheet_payload_for_adjudication` 未落地 + 无 store 投影/merge 引擎",
    "9": "GC-9 三家 TB 缺口未立门 ⇒ G1/G4/G6 审定表不得收口",
    "10": "模板覆盖层未交付 ⇒ G5-1!B35 只能登记不能修"
  }
}
```

## Notes

- 🔴 **本 spec 是 G 循环的收口 spec**：四份 lane spec 的审定表全部交棒到此。
- 🔴 **引擎缺口是硬前置**（非 `AdjudicationSheetSpec` 类型本身）：缺 payload 生成器 + store 投影/merge 引擎。类型已有 6 个声明实例（D/F 循环）。当前 HEAD 无任何 G 循环审定表声明实例。
- 🔴 **G1-1 是全平台公式最密的审定表**（504 格 / 98×11 = 47% 密度），逐格声明量巨大。
- 🔴 **G5-1!B35 是唯一需要修的模板缺陷**（越界引用 B225），其余审定表只声明不修。

---

## 外部交棒（2026-10-01，来自 spec `sync-editor-host-discovery-contract-closure` Task 16）

> **2026-10-07 处置结论**：3 条红判据在 HEAD 全部 **PASSED**（自愈），裁定走**方向 (a) slice 过期**——
> provider 确已交付、守卫基线已自动对齐。无需删 overlay、无需重取快照。下方原文保留作史实。

本 lane 有 **3 条**判据因上游改动打红，经定向 A/B 确认是**本轮引入**：

- `test_task49_g_cycle_migration.py::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice`
- `test_task49_g_cycle_migration.py::TestAdjudicationLegality::test_manifest_mirror_divergence_is_registered_not_silently_equal`
- `test_task49_g_cycle_migration.py::TestProperty20And21NotClaimedPassingForThisSlice::test_no_slice_entry_has_a_registered_adapter`

**根因**：上游 overlay 新增 13 条 G override，把 G1~G14（除 G7）翻成 `capability=bidirectional` / `migration_state=adapter_registered`，而 G slice 是**冻结快照**，记录的是 provider 交付前的状态。

🔴 **上游已如实登记这是边界越界**（其 design §九 T5）：原定边界是「不翻能力裁决」。裁定**保留 + 登记、不删**的四条理由里，最关键一条是 golden 覆盖棘轮的红文案「bidirectional 但未进 golden 门的 family = `['a51']`」**只点 a51 不点 G** ⇒ 反证 g1~g14 的 provider 已全部在 golden digest 基线内。

**两条处置方向请本 lane 裁定**（上游不预判）：(a) slice 过期 ⇒ 复核 provider 确已交付后重取快照；(b) 认为不该翻 ⇒ 删 overlay 那 13 条 + 重跑两个生成器即可**完全复原**（可逆）。

详见 `.kiro/specs/sync-editor-host-discovery-contract-closure/handoff-regression-attribution.md`。
