# Design

## Overview

13 张 G 循环审定表（`审定表G{N}-1`，N=1~14 无 G7）的逐格 mask 双向回写。

## Architecture

### 逐格 mask 而非行表

审定表与明细表不同：不是「行数组 + 公式列」，而是「固定布局 + 逐格公式 / 手填混合」。
用 `AdjudicationSheetSpec` 声明逐格 mask（每格一条 `formula`/`editable`/`auto_source` 判定），
而非 `RowTableSheetSpec`。

### 13 张按复杂度分三批

**批①（3 张最简）**：G12-1(38f) / G13-1(78f) / G14-1(72f) —— 三张结构近同：
单页少行、公式列清晰、TB 发布门已就位。

**批②（5 张中等）**：G2-1(132f) / G3-1(120f) / G8-1(100f) / G10-1(178f) / G11-1(161f)。

**批③（5 张复杂）**：G1-1(**504f**) / G4-1(176f) / G5-1(**501f**) / G6-1(340f) / G9-1(390f) ——
G1-1 和 G5-1 是全平台公式最密的两张，逐格声明 500+ 条。

### TB 发布门三家缺口处置

G1/G4/G6 三家审定表的 TB 发布门缺口由 GC-9 裁决，本 spec 不独立裁决。
接入时须确认 `useG1Adjudication` / `useG4MainAdjudication` / `useG6MainAdjudication`
的 `publishToTb` 是活路径（foundation Task 8 已按值核）。

### G5-1!B35 越界缺陷

`=B9-B225`（sheet 仅 87 行）⇒ B225 空白越界，求值恒 0 ⇒ B35 恒等于 B9。
走模板覆盖层修（改为 `=B9-B34`），不改 `backend/wp_templates/` 字节。

## Decisions

| ID | 裁决 | 理由 |
|----|------|------|
| GA-H1 | 13 张审定表统一后置 | 三条共性 > 科目差异 |
| GA-H2 | 用 `AdjudicationSheetSpec` 不用 `RowTableSheetSpec` | 审定表是固定布局非行数组 |
| GA-H3 | 按复杂度分三批 | 风险收敛：最简的先验通 |
| GA-H4 | G5-1!B35 在本 spec 修 | g5 spec 登记不修，交棒给本 spec |
