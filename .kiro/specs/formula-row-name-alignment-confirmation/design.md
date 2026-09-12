# Design Document

## Overview

本设计在**名称维度**补一层「可确认映射」，夹在既有"报表行 → 科目码"定位与"账套明细"之间。核心思路：不改科目定位真源，只把「行名 ↔ 账套明细名」的多对多关系显式化、可裁决、可持久化、可追溯。

```
底稿行（模板固定行名，如「预收销售固定资产款」）
        │
        │  ① 既有：ReportLineAccountSpec 定位科目码（不动）
        ▼
四表库科目叶子（select_leaves / aggregate_leaves）（不动）
        │
        │  ② 本 spec 新增：名称对齐层（行名 ↔ aux_name / account_name 的 N:M 映射）
        │     状态机 auto_matched / ambiguous / unmatched / user_confirmed
        ▼
账套明细（tb_aux_balance.aux_name / tb_balance.account_name 等）
```

## Architecture

### 分层与归属（谁拥有什么）

| 关注点 | owner | 本 spec 的关系 |
|---|---|---|
| toolbar outlet / 页面级 FormulaManager | `workpaper-page-formula-toolbar-closure`（F-SHELL） | **只消费**，不得新建按钮 owner（红基线：`GtWpToolbar.vue` 无 Vue slot） |
| 全局一键刷新范围选择 | `GtRefreshScopeDialog.vue`（formula-runtime-convergence） | 不同关注点，不合并、不复制其 scope 树 |
| 报表行 → 科目码定位 | `four_table/report_line_accounts.py` | 不改，只在其下游加名称层 |
| 叶子聚合 | `four_table/leaf_aggregation.py` | 不改 |
| 用户覆盖存储 | `workpaper_field_overrides`（V076） | 先评估复用，形态不足才新表（见 DEC-2） |

### 匹配状态机

```
account 侧候选集 = 该行科目码定位出的叶子 → 其账套明细名集合
  精确同名（归一后）唯一命中           → auto_matched
  归一后多命中 / 相似度命中             → ambiguous（必须人工确认）
  零命中                               → unmatched
  命中来自已落库的用户映射且映射未失效  → user_confirmed
  已落库映射的目标名在当前 active dataset 中消失 → 回落 unmatched（stale）
```

名称归一（仅用于**候选生成**，不用于直接出数）：去空白 / 全半角 / 常见后缀（有限公司等）。🔴 归一命中若非唯一，一律 `ambiguous`，不得当精确命中直接出数（Requirement 5.2）。

## Components and Interfaces

### 后端

1. `backend/app/services/four_table/row_name_alignment.py`（新）
   - `build_candidates(spec, dataset) -> list[Candidate]`：从已定位科目叶子取账套明细名候选（复用 `select_leaves`，不重写定位）
   - `classify(row_label, candidates, saved_mapping) -> MatchState`：纯函数，产出四态
   - `resolve_amounts(mapping, leaves) -> dict[row_label, Decimal]`：按映射聚合；多对一时按 DEC-3 口径处理
2. 映射存储（DEC-2 决定形态）+ 读写服务
3. 刷新端点：**扩展既有取数/刷新链**返回每行 `match_state` 与候选，而非新建平行端点

### 前端

1. `components/formula/GtRowNameAlignmentDialog.vue`（新，domain-owned dialog）
   - 两栏：左=底稿行名（带状态 tag）、右=候选账套明细名（带金额与相似度提示）
   - 支持连线式建立 1:N / N:1 / N:M；多对一必须弹出口径确认（Requirement 2.4）
2. 刷新入口：**通过 F-SHELL outlet 注入**（Requirement 4.1）；outlet 不可用时任务 BLOCKED，不临时加按钮
3. 行内标识：`unmatched`/`ambiguous` 行给可见 tag + 点击直达弹窗对应行

## Data Models

```
RowNameMapping
  project_id, year, wp_code, sheet_code, row_key        -- 作用域（Requirement 3.2）
  target_names: [str]                                   -- N（一对多）
  match_state: user_confirmed
  confirmed_by, confirmed_at, superseded_from           -- 留痕（Requirement 3.5）
  dataset_fingerprint                                   -- 用于判 stale（Requirement 1.4）
```

多对一由「不同 row_key 的 target_names 交集非空」自然表达，无需额外结构。

## Correctness Properties

### Property 1

对任意 (行名, 候选集)，`classify` 的返回值必属四态之一，且「归一后多命中」必映射到 `ambiguous`（不得为 `auto_matched`）。

**Validates: Requirements 5.2**

### Property 2

对任意已落库映射，若其 `target_names` 中任一名在当前 active dataset 不存在，则该行状态必为 stale/`unmatched`，`resolve_amounts` 不得为其产出金额。

**Validates: Requirements 1.4**

### Property 3

对任意映射集合，若两个不同 row_key 的 `target_names` 交集非空（多对一），则重算结果必须携带「重复引用」告警标记。

**Validates: Requirements 2.4**

### Property 4

用户取消弹窗后，映射存储的内容与取消前逐字节一致（零写入）。

**Validates: Requirements 2.6**

### Property 5

同一作用域第二次刷新时，已确认且未失效的映射不触发弹窗，且出数与第一次确认后一致。

**Validates: Requirements 3.3**

### Property 6

`unmatched` 行的输出必须是「无值」语义，不得是 0 或上期值。

**Validates: Requirements 5.1**

## Testing Strategy

1. **纯函数 PBT**：`classify` / `resolve_amounts` 覆盖 Property 1/2/3/6（hypothesis，max_examples=5 按仓库约定）
2. **变异检验**：删掉映射查询 / 改错作用域键（漏 year 或漏 wp_code）/ 把 `ambiguous` 当 `auto_matched` —— 每条必须打红对应守卫（Requirement 5.3）
3. **零写入守卫**：取消路径断言存储 digest 不变（Property 4）
4. **真栈实测**（Requirement 5.4）：Playwright 跑一张真实名称不一致的审定表，确认前该行 0 → 弹窗确认 → 该行变账套真实值；证据 JSON 落 spec evidence
5. **入口清册**：从 renderer registry / render-config / 已挂载宿主推导缺刷新入口的底稿（禁 grep 按钮文字）

## Open Decisions

- **DEC-1（待用户确认）**：样板底稿。用户提到「图片红框位置＝工具栏「导入」右侧」，但图未获取到。设计已按「导入右侧 + 走 F-SHELL outlet」落定位置；**样板底稿**建议取 D3-1 审定表或 F1 附注（两者都有固定行名 + 已有四表库取数），待确认后写进 tasks 的实测目标。
- **DEC-2**：映射存储形态。倾向**新建 `workpaper_row_name_mapping` 表 + 新迁移**，理由：`workpaper_field_overrides` 是「单 scope 单字段值」形态，承载 N:M 的 `target_names` 数组与 stale 指纹会退化成塞 JSON 字符串（丧失可查询性）。⚠️ 但必须在 Task 1 先出书面评估结论（Requirement 3.1），不得跳过。
- **DEC-3**：多对一口径。默认**不自动去重**（各行按映射各自聚合），但必须显式告警重复引用；是否要提供「按比例分摊」模式留作后续增强，本 spec 不做。
- **DEC-4**：与 `GtRefreshScopeDialog` 的触发关系。本 spec 的弹窗挂在**底稿级刷新**链上；全局一键刷新（合伙人）遇到 unmatched 时**不弹窗**（合伙人不逐行确认），而是产出「N 行待确认」的汇总告警，导向底稿级处理。
