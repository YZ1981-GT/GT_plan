# 显示格式化单一真源（金额/时间/百分比）— Requirements

## 背景

codegraph 实证（2026-06-23，80785 节点）：
- `displayPrefs.fmt()` 已存在（接单位/小数/零值偏好），但**未被普遍引用**。
- **43 个 .vue 各自手写 `function formatAmount`**，逻辑大同小异，且全部裸调 `toLocaleString('zh-CN', {...})`，**不跟随** displayPrefs 的单位（万元/元）、小数位、负数红。
- `toLocaleString('zh-CN', ...)` 在 .vue/.ts 中散落 **70+ 处**。
- 已存在两个工具文件 `utils/formatAmount.ts`、`utils/formatters.ts`，但它们**自身也是裸 toLocaleString，未接 displayPrefs**；`formatters.ts` 已有 `fmtDateTime` 但同样是裸实现。
- `qc/ClientQualityTrend.vue`、`components/workpaper/PriorYearCompareDrawer.vue` 用 `style:'currency', currency:'CNY'`（带 ¥ 符号），与平台"元/万元"规范冲突。

**用户实感**：用户在顶部把单位切成"万元"，主表跟着变，但点开"公式详情/汇总明细"弹窗、或大量计算弹窗里的金额仍是"元"，且小数位、负数红不统一。审计人员核对数字时极易看错量级——这是金额准确性的体验风险。

## 目标

建立**接 displayPrefs 的唯一格式化出口**，让金额/时间/百分比格式化全平台一致，且单位/小数/负数偏好实时跟随。存量散落格式化渐进迁移到统一出口，并加 CI 守卫防新增。

## 术语

- **统一出口**：`displayPrefs` store 暴露的 `fmt`（金额）/ `fmtDateTime`（时间）/ `fmtPercent`（百分比），内部消费用户显示偏好。
- **裸格式化**：业务代码直接调 `toLocaleString` / `toFixed` / `style:'currency'` 格式化金额或时间。

## 需求

### 需求 1：金额统一出口（已有 fmt，需补齐能力并成为唯一出口）

**用户故事**：作为审计助理，我切换显示单位后，平台所有金额（含弹窗、明细、计算对话框）都应同步换算，小数位与负数红一致。

#### 验收准则
1. WHEN 调用 `displayPrefs.fmt(v)` THEN 返回值 SHALL 按当前 `amountUnit`/`decimals`/`showZero` 偏好格式化。
2. WHEN 金额为 null/undefined/非数字 THEN `fmt` SHALL 返回统一占位符（`'—'`），不抛错。
3. THE store SHALL 额外暴露 `fmtAmount` 作为 `fmt` 的语义别名（便于 import 命名一致），二者行为完全相同。
4. WHERE 组件需要"原始元值不换算"的特殊场景 THE store SHALL 提供 `fmt(v, { rawUnit: true })` 选项显式绕过单位换算（避免开发者退回裸 toLocaleString）。

### 需求 2：时间统一出口（收编现有裸 fmtDateTime）

**用户故事**：作为任意角色，我在不同页面看到的时间格式应一致。

#### 验收准则
1. THE `utils/formatters.ts` 的 `fmtDateTime` SHALL 成为唯一时间格式化出口，并保持现有签名向后兼容。
2. WHEN 传入 null/空/非法日期 THEN `fmtDateTime` SHALL 返回 `'-'`，不抛错。
3. THE store SHALL 转发 `fmtDateTime`（`displayPrefs.fmtDateTime`），使模板可统一从 prefs 取所有格式化方法。
4. 散落的 `new Date(x).toLocaleString('zh-CN', {...})` 时间格式化 SHALL 迁移到 `fmtDateTime`（存量分批，见需求 5）。

### 需求 3：百分比统一出口（新增）

**用户故事**：作为现场经理，我看到的完成率/占比小数位应一致。

#### 验收准则
1. THE store SHALL 提供 `fmtPercent(v, decimals?)`，默认 1 位小数，返回带 `%` 字符串。
2. WHEN 传入 null/非数字 THEN SHALL 返回 `'—'`。

### 需求 4：废弃裸实现工具文件

#### 验收准则
1. THE `utils/formatAmount.ts` SHALL 改为转发到 displayPrefs 统一逻辑（保留导出名向后兼容，内部不再裸 toLocaleString）。
2. THE `utils/formatters.ts` 的金额相关函数 SHALL 同样转发；`fmtDateTime` 保留为时间唯一实现。
3. `style:'currency', currency:'CNY'` 的两处（ClientQualityTrend、PriorYearCompareDrawer）SHALL 改用统一出口，去掉 ¥ 符号，符合"元/万元"规范。

### 需求 5：存量迁移（渐进，分批可验证）

**用户故事**：作为维护者，我需要 43 处组件级 formatAmount 逐步消除，但每批可独立验证不破坏页面。

#### 验收准则
1. 43 处组件级 `function formatAmount` SHALL 分批删除并改 import 统一出口；每批迁移后该组件页面金额显示 SHALL 与迁移前一致（除单位现在会跟随偏好外）。
2. WHILE 迁移未完成 THE 已迁移组件与未迁移组件 SHALL 不冲突（统一出口与旧函数可共存）。
3. 迁移批次 SHALL 优先覆盖审计核对高频页面：TrialBalance、ReviewWorkbench、底稿计算弹窗群（折旧/减值/ECL/薪酬/所得税等）。

### 需求 6：CI 守卫防新增

#### 验收准则
1. THE 一个 CI grep 守卫脚本 SHALL 检测 `.vue`/`.ts`（排除 displayPrefs.ts / formatters.ts / formatAmount.ts 出口文件）中新增的 `toLocaleString('zh-CN'` 与 `style:\s*'currency'` 金额格式化，命中即告警。
2. THE 守卫 SHALL 支持"存量豁免清单"，已知存量行不告警，新增行告警；豁免清单随迁移逐步清空。
3. THE 守卫 SHALL 可在本地与 CI 运行（纯 Python/node 脚本，无新依赖）。

## 非目标
- 不改 displayPrefs 的持久化/UI 设置面板。
- 不引入新前端依赖（用 Intl 原生）。
- 不动后端格式化。
