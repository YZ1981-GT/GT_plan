# D2 业务闭环验收报告

## 验收概述

| 项目 | 内容 |
|------|------|
| spec | workpaper-account-package-d1-d2-pilot |
| 工作包 | D2 应收账款 (D2_accounts_receivable) |
| 验收日期 | 2026-06-07 |
| 验收目标 | 多文件工作包 + 函证 + 坏账/ECL + 附注/报表联动闭环 |

## 验收项

### 5.1 D2 工作包入口 ✅

- 复用 `AccountPackageView.vue`，packageId=D2_accounts_receivable
- 展示 D2 应收账款工作包（14 sheets）
- 显示 mapping_status 标签
- 展示 external_cards（confirmation_summary、adjustment_impact）

### 5.2 聚合审定表 D2-1 ~ D2-C ✅

- D2 sheets 按 sheet_type 分组完整展示：
  - control_panel: D2A
  - audit_sheet: D2-1
  - detail_table: D2-2
  - analysis: D2-3, D2-5, D2-9, D2-10, D2-13
  - procedure: D2-6, D2-7, D2-8
  - adjustment: D2-4
  - disclosure: C-D2-disclosure
  - conclusion: D2-C
- groupSheetsByType 测试验证 D2 所有分组正确

### 5.3 D2 函证摘要卡片 ✅

- `AccountPackageEvidenceCard.vue` type=confirmation_summary
- 展示覆盖率、差异金额、未解决事项（placeholder '--'）
- 提供"跳转函证中心"链接
- 点击链接跳转 ConfirmationHub 路由

### 5.4 D2 调整保存后下游 stale 提示 ✅

- 工作包视图检查 `summary.stale_summary.has_stale`
- stale 时显示警告："调整保存后，报表/附注数据需要刷新"
- stale 数据由 `AccountPackageSummaryService` 后端计算提供

### 5.5 D2 坏账与 ECL 分组 ✅

- `getBadDebtEclGroup` 函数识别：
  - D2-3 坏账准备明细
  - D2-8 坏账政策检查
  - D2-9 坏账准备测算
  - D2-10 预期信用损失计量测试
  - C-D2-disclosure 坏账披露
- 在工作包视图中独立展示"坏账与 ECL"分组区域
- 点击可跳转到对应 sheet

### 5.6 D2 分析结果统一进入 analysis_summary ✅

- D2-5 分析程序归类为 `analysis` sheet_type
- 不将账龄作为未确认独立 sheet 口径
- 所有分析类 sheet 统一在 analysis 分组展示
- 后端 summary 聚合分析结果

### 5.7 D2 多 sheet 不完整时，工作包仍可打开并明确显示缺失卡片 ✅

- `hasMissingSources` 计算属性检测缺失
- 缺失时显示 el-alert 警告：
  - "部分数据源缺失（工作包仍可打开）"
  - 列出每个缺失项的 sheet_name 和原因
- 工作包不因缺失而报错或阻塞

### 5.8 测试覆盖 ✅

- `AccountPackageView.spec.ts`: D2 分组正确性、ECL 分组、缺失卡片
- `AccountPackageSheetNav.spec.ts`: D2 控制台优先展示、分析分组内容
- 共 24 tests passed

## 技术产物

| 文件 | 职责 |
|------|------|
| `composables/useAccountPackage.ts` | 含 D2 坏账/ECL 分组逻辑 |
| `views/AccountPackageView.vue` | D2 入口（含 stale 提示、ECL 分组、函证卡片） |
| `components/workpaper/AccountPackageEvidenceCard.vue` | 函证摘要卡片 |

## D2 业务闭环验证清单

| 场景 | 状态 |
|------|------|
| 多 sheet 聚合（14 sheets） | ✅ 按 sheet_type 分组 |
| 函证摘要联动 | ✅ placeholder + 跳转链接 |
| 坏账/ECL 分组展示 | ✅ 5 相关 sheet 聚合 |
| 调整 stale 提示 | ✅ 基于 stale_summary |
| 缺失卡片降级 | ✅ 不阻塞打开 |
| 结论入口 | ✅ D2-C 结论按钮 |

## 可推广说明

D2 业务闭环模式可推广到：
- F2 应付账款（类似多 sheet 结构）
- G 投资循环（含公允价值测试卡片）
- H 固定资产（含折旧测算卡片）

推广步骤：
1. 在 `account_package_registry.json` 新增工作包定义
2. 配置 sheets、external_cards、downstream
3. 复用 AccountPackageView + AccountPackageSheetNav 组件
4. 根据需要新增特定 EvidenceCard 类型
