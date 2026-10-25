# B 类孤儿载体与宿主内联门控通道 — 需求

## 背景

本 spec 承担 B 循环 10 条 entry 中的 **5** 条，分两个子组：

- **孤儿载体组**（3 条）：挂在 `useWpDualMode.ts` 上。🔴 该载体是**全 slice 唯一** `becomes_orphan_after_rewire = True` 的共享载体 —— 改线后整个文件成孤儿，须连带删除。
- **宿主内联组**（2 条）：门控写在宿主内（`host_inline_segmented`），无共享载体牵连。

两组合并为一份 spec 的理由：缺陷集合 Jaccard 重合度 **0.25**，且改线动作都不涉及「保共享基类兼容」（与 lane 2 的根本差异）。

共同判据由 `b-cycle-sync-foundation-and-first-canary` 一次性裁定为 **BC-1 ~ BC-60**，本 spec **只引用编号，不重复裁决**。

## 范围

### 子组 A：孤儿载体 `useWpDualMode.ts`（3 条）

| # | entry_id | pattern | 真实 wp_code | 宿主 | 行数 | 挂点 |
|---|---|---|---|---|---|---|
| 1 | `xlsx/gt-b1-evaluation` | `B1E` | `B1-3` / `业务评价表B1-3` | `GtB1Evaluation.vue` | 432 | `#L223` |
| 2 | `xlsx/gt-b1-kaa-check` | `B1K` | `' B1-5 KAA检查表-业务承接'` / `B1-5` | `GtB1KaaCheck.vue` | 311 | `#L166` |
| 3 | `xlsx/gt-b1-risk-assessment` | `B1R` | `B1-1` / `B1-2` / `风险评估表-保持` / `风险评估表-承接` | `GtB1RiskAssessment.vue` | 538 | `#L301` |

### 子组 B：宿主内联门控（2 条）

| # | entry_id | pattern | 真实 wp_code | 宿主 | 行数 |
|---|---|---|---|---|---|
| 4 | `xlsx/gt-b14-due-diligence-report` | `B14D` | `B1-4` | `GtB14DueDiligenceReport.vue` | 636 |
| 5 | `xlsx/gt-b23-process-control` | `B23P` | `B23` | `GtB23ProcessControl.vue` | 963 |

### 本组独有缺陷

- 子组 A 独有 **2** 项：`.reduce(` 派生合计 · 解析抛 `FileNotFoundError`
- 子组 B 独有 **4** 项：`rowIndex` 形参 · Property 22 写死对标公司 · 双 segmented · xlsm 宏丢失

### 不在本 spec

- 共享基类 `useWorkpaperEntryDualMode.ts` 上的 5 条（canary 在 foundation，其余 4 条在 `b-class-shared-base-carrier-lanes`）

## 需求

### 需求 1：孤儿载体改线后必须连带删除

**用户故事**：作为维护者，我不希望改线后仓库里留下一个没人用的 composable 文件持续误导后人。

#### 验收标准

1. WHEN 3 条 entry 全部改线完成 THEN `useWpDualMode.ts` 的生产引用 SHALL 归零
2. WHEN 引用归零 THEN 该文件 SHALL 被删除，且删除前后测试全绿
3. WHEN 删除该文件 THEN 变更 SHALL 独立成 commit 以便回滚
4. IF 3 条 entry 未全部改线完成 THEN 该文件 SHALL 保留（不可提前删除）

### 需求 2：解析失败三模式在本组全部出现

**用户故事**：作为改线工程师，我需要解析层的兜底能同时处理返回空、抛异常、多册歧义三种情况。

#### 验收标准

1. WHEN 解析 `' B1-5 KAA检查表-业务承接'`（带前导空格）THEN 系统 SHALL 处理 `FileNotFoundError` 而非仅处理返回 `None`
2. WHEN 解析中文名 wp_code THEN 系统 SHALL 处理返回 `None` 的情况并给出可诊断信息
3. WHEN `B1-4` 对应标准版与简化版**两本**册 THEN 系统 SHALL 显式指定册而非依赖 finder 排序
4. WHEN sheet 名含前导空格 THEN 系统 SHALL 禁止归一化（前导空格来自真实 sheet 名）

### 需求 3：一个 componentType 覆盖四个 wp_code 的归属消歧

**用户故事**：作为审计助理，风险评估表的「承接」版与「保持」版填写内容不应互相覆盖。

#### 验收标准

1. WHEN `xlsx/gt-b1-risk-assessment` 的 componentType 覆盖 **4** 个 wp_code（`B1-1` / `B1-2` / `风险评估表-保持` / `风险评估表-承接`）THEN 系统 SHALL 按 wp_code 区分持久化命名空间
2. WHEN 其中 2 个是中文 sheet 名而非真实码 THEN 系统 SHALL 登记该 override 表缺陷而非静默接受
3. WHEN 「承接」与「保持」对应不同模板册 THEN 解析 SHALL 能区分（`B1-1` → 承接 / `B1-2` → 保持）
4. WHEN 断言真库分母 THEN 该 entry 的载荷 SHALL 被显式登记（实测为 0 条业务数据）

### 需求 4：宿主内联门控与写死列结构

**用户故事**：作为审计助理，我需要在行业对标表里填写第 3 家及更多对标公司。

#### 验收标准

1. WHEN 行业对标表列结构写死 `peer1` / `peer2` 两家 THEN 系统 SHALL 改为动态列以支持任意家数
2. WHEN `xlsx/gt-b14-due-diligence-report` 有 **2** 个 segmented 控件 THEN 门控扫描 SHALL 正确归属而非计重
3. WHEN 章节表行用 `rowIndex` 形参索引 JSON 数组 THEN 行身份 SHALL 改为稳定 id（同宿主 `sections` 已有 `sec.id` 可参照）
4. WHEN `xlsx/gt-b23-process-control` 的权威册是 xlsm THEN 回写 SHALL 保留 VBA 宏，且数据验证丢失 SHALL 被登记为已知限制
