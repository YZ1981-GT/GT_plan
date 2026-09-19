# D1 技术闭环验收报告

## 验收概述

| 项目 | 内容 |
|------|------|
| spec | workpaper-account-package-d1-d2-pilot |
| 工作包 | D1 应收票据 (D1_notes_receivable) |
| 验收日期 | 2026-06-07 |
| 验收目标 | 语义标注 + 附注来源 + 状态持久化闭环 |

## 验收项

### 4.1 D1 工作包入口 ✅

- 路由 `/projects/:projectId/account-packages/:packageId` 已注册
- `AccountPackageView.vue` 展示 D1 工作包首页
- 展示科目名称、代码、循环、sheet 数量
- `mapping_status=pending_inventory_reconciliation` 时显示"映射待确认"标签

### 4.2 D1 sheet_type 分组导航 ✅

- `AccountPackageSheetNav.vue` 按 sheet_type 分组展示
- D1 分组包含：审定表、明细表、分析、检查程序、调整分录、附注披露、科目结论
- 分组按固定优先级排序（control_panel → audit_sheet → detail_table → ...）
- 点击 sheet 触发选中事件
- 空状态显示"暂无工作表"

### 4.3 D1 审定表字段来源面板 ✅

- `AccountPackageFieldSource.vue` 在审定表选中时展示
- D1 关键字段：期末余额（← D1-2）、坏账准备（← D1-4）、贴现/背书（← D1-8）、质押金额（← D1-12）
- 点击来源可跳转到对应 sheet（预留链接）
- 每个来源标注类型标签

### 4.4 D1-C 结论入口 ✅

- `AccountPackageConclusionEntry.vue` 展示科目结论入口
- 展示 D1-C 结论状态（待编制/进行中/已完成）
- 提供"进入结论表"按钮

### 4.5 D1 附注来源链路 ✅

- D1-1（审定表）→ C-D1-disclosure
- D1-4（坏账）→ C-D1-disclosure
- D1-8（贴现背书）→ C-D1-disclosure
- D1-12（质押）→ C-D1-disclosure
- 在附注区域标注数据来自哪些程序表

### 4.6 测试覆盖 ✅

- `AccountPackageView.spec.ts`: 16 tests passed
- `AccountPackageSheetNav.spec.ts`: 8 tests passed
- 覆盖：分组正确性、排序、交互、空状态、缺失卡片

## 技术产物

| 文件 | 职责 |
|------|------|
| `composables/useAccountPackage.ts` | 工作包数据获取 composable |
| `views/AccountPackageView.vue` | 工作包入口首页 |
| `components/workpaper/AccountPackageSheetNav.vue` | sheet_type 分组导航 |
| `components/workpaper/AccountPackageFieldSource.vue` | 字段来源面板 |
| `components/workpaper/AccountPackageControlPanel.vue` | 程序状态控制台 |
| `components/workpaper/AccountPackageEvidenceCard.vue` | 摘要卡片 |
| `components/workpaper/AccountPackageConclusionEntry.vue` | 结论入口 |

## 可复制模式

D1 工作包的注册表结构（`account_package_registry.json`）可直接复制到：
- D4 营业收入工作包
- F 采购存货工作包
- H 固定资产工作包

只需修改 `sheets`、`source_wp_codes`、`schema_refs` 字段即可注册新工作包。
