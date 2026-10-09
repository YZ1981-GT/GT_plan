# Requirements

## Overview

G 循环 13 张审定表（`审定表G{N}-1`，N=1~14 无 G7）的双向回写覆盖。

裁决 GF-H5：审定表的三条共性（全部命中裸 IF / 公式密度极高 G1-1 504f / TB 发布门含 GC-9
三家缺口）大于其所属科目的差异 ⇒ 统一后置，不散入各循环 lane spec。

## Requirements

### 1. 审定表逐格 mask 声明

1.1 每张审定表声明 `AdjudicationSheetSpec`（或等价的逐格 mask spec），公式格全部判 `formula`/`auto_source`。
1.2 13 张审定表的 `header_rows` / `first_data_row` / `footer_row` 逐张实测，不按模式推演。
1.3 `formula_mask` 逐张从模板逐格现算（不手写 range）。

### 2. 裸 IF 中性化

2.1 13 张审定表全命中裸 IF（7~191 格），中性化由 per-file `oo_crash_neutralization_fn` 覆盖（GC-2 已挂）。
2.2 🔴 G9-1 裸 IF **122 格**（仅次于 G1-1 的 191）—— 按 GC-2 保守策略不能因为数量少就不挂。

### 3. TB 发布门

3.1 G1/G4/G6 三家审定表的 `publishToTb` 路径是 TB 的唯一写入点（GC-9 裁决）。
3.2 其余 10 家的 `publishToTb` 已就位（foundation Task 8 确认）。
3.3 sync 路径对 trial_balance 写次数必须为 0（FC-9 红线）。

### 4. 13 张审定表几何基线

4.1 G1-1：93r×11c / 504f / IF=191（**全平台公式最密**）
4.2 G5-1：87r×13c / 501f / IF=70
4.3 G9-1：69r×15c / 390f / IF=122
4.4 G6-1：76r×11c / 340f / IF=48
4.5 G12-1：23r×11c / 38f / IF=7（最简）

### 5. 交棒来源

5.1 本 spec 由 `g-cycle-sync-foundation-and-first-canary` Task 18 裁决（GF-H5）。
5.2 四份已建 G lane spec 均在正文引用本 spec 作交棒目标。
5.3 `g5-nested-sections-and-template-defects` Task 7 的 G5-1!B35 越界缺陷在本 spec 处置。
