# Implementation Plan

## Overview

**spec**：`g-cycle-adjudication-sheets-coverage`　**创建**：2026-09-27　**状态**：0/12（Task 0~11），Design-First 未实施
**上游**：**`g-cycle-sync-foundation-and-first-canary`（GC-1~GC-10，硬前置）** · 四份已建 G lane spec 交棒

`[ ]*` = 依赖外部供给（`AdjudicationSheetSpec` 泛化 / OO 真栈 / 模板覆盖层）。

🔴 **13 张审定表的几何基线（openpyxl 逐格实测 2026-09-27）**：

| 审定表 | 行×列 | 公式 | 裸IF | 密度 |
|--------|-------|------|------|------|
| G1-1 | 93×11 | 504 | 191 | 49% |
| G2-1 | 41×11 | 132 | 19 | 29% |
| G3-1 | 48×22 | 120 | 18 | 11% |
| G4-1 | 46×11 | 176 | 29 | 35% |
| G5-1 | 87×13 | 501 | 70 | 44% |
| G6-1 | 76×11 | 340 | 48 | 41% |
| G8-1 | 29×11 | 100 | 12 | 31% |
| G9-1 | 69×15 | 390 | 122 | 38% |
| G10-1 | 58×12 | 178 | 28 | 26% |
| G11-1 | 79×11 | 161 | 91 | 19% |
| G12-1 | 23×11 | 38 | 7 | 15% |
| G13-1 | 35×11 | 78 | 11 | 20% |
| G14-1 | 36×11 | 72 | 11 | 18% |

合计：**3357 公式格 / 686 裸 IF**（G 循环审定表层面）。

## Tasks

### 阶段 0：前置门 + 红判据

- [x] 0. 前置依赖核查
  - 🔴 **实测结论（2026-09-27）：`AdjudicationSheetSpec` 未落地**（`git cat-file HEAD` 不存在 + import ModuleNotFoundError）——
    它是 D1 spec `d1-sync-row-table-engine-and-d1-coverage` 的框架层产物，D1 spec 本身 0/35 未实施。
    ⇒ **Task 2~11 全部阻塞**（13 张审定表无类型可依），本 spec 只能停在几何基线（Task 1）+ 前置登记。
  - foundation 已确认 G2-1「本 spec 不交付其 AdjudicationSheetSpec」（`adjudication_spec()` 恒 None）——
    与本结论一致：审定表逐格 mask 引擎归 D1 spec，G 循环各 lane spec 只交棒不实施。
  - 13 张审定表几何基线已实测（见上表，合计 3357 公式格 / 686 裸 IF）。
  - 模板覆盖层：G5-1!B35 越界缺陷待 Task 10（同样阻塞于 AdjudicationSheetSpec）。
  - _Requirements: 1.1, 3.1_

- [ ]* 1. 13 张几何逐格实测 + 红判据（🔴 阻塞于 AdjudicationSheetSpec）
  - ✅ 几何基线已实测（上表）
  - P1 断言 13 张公式总数 ≥ 3300（不写死精确值，GC-10）—— 待引擎落地后写
  - P2 断言 13 张全命中裸 IF（7~191，不写死具体数）—— 待引擎落地后写
  - _Requirements: 1.2, 1.3, 2.1, 4.1_

### 阶段 1：批① 三张最简（G12-1 / G13-1 / G14-1）

- [ ]* 2. G12-1 逐格 spec（38f / 7 IF —— 全 G 最简审定表）
  - _Requirements: 1.1, 1.3_

- [ ]* 3. G13-1 逐格 spec（78f / 11 IF）
  - _Requirements: 1.1_

- [ ]* 4. G14-1 逐格 spec（72f / 11 IF）
  - _Requirements: 1.1_

- [ ]* 5. 批① 发布链 + 零回归
  - 三张契约 + 登记 + P3 零回归
  - _Requirements: 3.3_

### 阶段 2：批② 五张中等（G2-1 / G3-1 / G8-1 / G10-1 / G11-1）

- [ ]* 6. G2-1 / G8-1 逐格 spec（132f / 100f）
  - _Requirements: 1.1_

- [ ]* 7. G3-1 / G10-1 / G11-1 逐格 spec（120f / 178f / 161f）
  - _Requirements: 1.1_

- [ ]* 8. 批② 发布链 + 零回归
  - _Requirements: 3.3_

### 阶段 3：批③ 五张复杂 + G5-1 越界修 + 收口

- [ ]* 9. G4-1 / G6-1 逐格 spec（176f / 340f）
  - 🔴 G4-1 / G6-1 的 TB 发布门缺口（GC-9 裁决）须同步立门
  - _Requirements: 1.1, 3.1, 3.2_

- [ ]* 10. G1-1 / G5-1 / G9-1 逐格 spec（504f / 501f / 390f —— 全 G 最复杂三张）
  - 🔴 G5-1!B35 越界缺陷走模板覆盖层修
  - _Requirements: 1.1, 5.3_

- [ ]* 11. 批③ 发布链 + 收口
  - 全部 13 张零回归 + TB 红线 + materialize/verify
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
    "0": "AdjudicationSheetSpec 未泛化 ⇒ 全部 13 张无类型可依",
    "9": "GC-9 三家 TB 缺口未立门 ⇒ G1/G4/G6 审定表不得收口",
    "10": "模板覆盖层未交付 ⇒ G5-1!B35 只能登记不能修"
  }
}
```

## Notes

- 🔴 **本 spec 是 G 循环的收口 spec**：四份 lane spec 的审定表全部交棒到此。
- 🔴 **AdjudicationSheetSpec 是硬前置**：D1 spec 产出，当前不确定是否在 HEAD。若不在则 Task 2 起全部阻塞。
- 🔴 **G1-1 是全平台公式最密的审定表**（504 格 / 93×11 = 49% 密度），逐格声明量巨大。
- 🔴 **G5-1!B35 是唯一需要修的模板缺陷**（越界引用），其余审定表只声明不修。
