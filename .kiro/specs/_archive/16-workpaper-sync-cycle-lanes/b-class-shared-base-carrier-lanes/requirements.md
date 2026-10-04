# B 类共享基类载体通道 — 需求

## 背景

本 spec 承担 B 循环 10 条 entry 中，挂在共享基类 `useWorkpaperEntryDualMode.ts` 上的 **4** 条（第 5 条 `xlsx/gt-b22-a-control-matrix` 作为首张 canary 在 foundation spec 落地）。

共同判据由 `b-cycle-sync-foundation-and-first-canary` 一次性裁定为 **BC-1 ~ BC-60**，本 spec **只引用编号，不重复裁决**。

## 范围

| # | entry_id | wp_code pattern | 真实 wp_code | 宿主 | 行数 |
|---|---|---|---|---|---|
| 1 | `xlsx/gt-b22-b-control-matrix` | `B22B` | `B22B` | `GtB22BControlMatrix.vue` | 531 |
| 2 | `xlsx/gt-b22-b-deficiency-evaluation` | `B22B`（与 #1 共用） | （空，override 零命中） | `GtB22BDeficiencyEvaluation.vue` | 1148 |
| 3 | `xlsx/gt-b22-c-design-effectiveness` | `B22C` | `B22C` | `GtB22CDesignEffectiveness.vue` | 685 |
| 4 | `xlsx/gt-b50-risk-assessment` | `B50R` | `B50` | `GtB50RiskAssessment.vue` | 2772 |

全部 4 条的共享载体挂点行号（现算自 slice `dual_mode_carrier_inventory.shared_carriers`）：`#L29` / `#L32` / `#L24` / `#L30`。

### 本组独有缺陷（8 项，foundation §1.4 现算）

`GRP-05` 通道差异 · Property 22 label 作 key · `checklist-responses` 在宿主内直调（D0） · override 表零命中 · `row-{n}` 位置化 item_id · 一码多册 11 本 · 公式裸 IF · 熵键

### 不在本 spec

- `xlsx/gt-b22-a-control-matrix`（canary，foundation 承担）
- `useWpDualMode` 3 条与 host_inline 2 条（`b-class-orphan-carrier-and-host-inline-lanes` 承担）

## 需求

### 需求 1：共享基类改线保持向后兼容

**用户故事**：作为维护其他循环底稿的工程师，我不希望 B 域改线把共享基类改坏，导致其他循环的底稿一起坏掉。

#### 验收标准

1. WHEN 改线 4 条 entry THEN `useWorkpaperEntryDualMode.ts` 的其余 **21** 条生产边（26 − 5）SHALL 保持行为不变
2. WHEN 共享基类新增参数 THEN 该参数 SHALL 有默认值，未传时退回改线前行为
3. WHEN 改线完成 THEN `becomes_orphan_after_rewire` SHALL 仍为假（本组载体不成孤儿，与 `useWpDualMode` 相反）
4. IF 改线导致其他循环回归 THEN 变更 SHALL 可按 entry 粒度回滚，而非整体回退

### 需求 2：`B22B` 一码双 entry 的归属消歧

**用户故事**：作为审计助理，我在「控制矩阵」和「缺陷评价」两张底稿上填的内容不应互相串台。

#### 验收标准

1. WHEN 两条 entry 共用 `B22B` pattern THEN 系统 SHALL 以 componentType 而非 wp_code 区分归属
2. WHEN `xlsx/gt-b22-b-deficiency-evaluation` 的 override 表命中为 **0** THEN 其 sheet 名解析 SHALL 有显式兜底而非依赖 override
3. WHEN 两条 entry 的载荷写入 `checklist_responses` THEN `item_id` 命名空间 SHALL 不重叠
4. WHEN 断言真库分母 THEN `B22B` 的 13 行 SHALL 可按 entry 归属拆分或显式登记为「无法拆分」

### 需求 3：位置化行键与 `count` 键一致

**用户故事**：作为审计助理，我删掉中间一行后，后面几行的内容不应整体错位。

#### 验收标准

1. WHEN 持久化行数据 THEN 行键 SHALL 不使用数组下标（`B22B-row-{n}` / `B22C-env-def-{n}` 属违规形态）
2. WHEN 独立 `count` 键存在 THEN 其值 SHALL 等于实际行键数量
3. WHEN 两种编号基准并存（`row-0` 0-based vs `env-def-1` 1-based）THEN 迁移脚本 SHALL 分别处理而非统一假设
4. WHEN 渲染 key 绑定到可编辑文本 THEN 守卫 SHALL 报缺陷（本组 4 处全在 `GtB50RiskAssessment.vue`）

### 需求 4：`GRP-05` 的额外通道被显式登记

**用户故事**：作为改线工程师，我需要知道 `xlsx/gt-b50-risk-assessment` 比其余 3 条多了什么通道。

#### 验收标准

1. WHEN 断言 group 归属 THEN `xlsx/gt-b50-risk-assessment` SHALL 为 `GRP-05`，其余 3 条为 `GRP-04`
2. WHEN `GRP-05` 声明含 `field_overrides` 通道 THEN 该通道在前端 import 闭包深度 3 内的命中 SHALL 被显式登记为 **0**
3. IF `field_overrides` 通道实际走后端 THEN 该路径 SHALL 被实测确认而非推演
4. WHEN `xlsx/gt-b50-risk-assessment` 真库载荷为 **0** 行 THEN 其改线验证 SHALL 依赖人造数据并声明该前提
