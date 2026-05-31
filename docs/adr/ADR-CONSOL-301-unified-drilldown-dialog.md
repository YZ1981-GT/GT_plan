# ADR-CONSOL-301: 统一穿透组件 ConsolBreakdownDialog（report+note 一个组件）

## 状态
已接受 (2026-05-31)

## 背景

报表级穿透（Phase 2 后端就位）+ 附注级穿透（Phase 3 新建）都需要"列 N 家子公司金额 + 占比 + 抵销 + 跳转链接"的弹窗。分别造两个组件 = 重复 + 渲染分叉风险。

## 决策

新建单一 `ConsolBreakdownDialog.vue`，`props.source = 'report' | 'note'` **仅决定调哪个端点，渲染契约统一**：

- `source='report'` → `GET /api/consolidation/report/{pid}/{year}/{account_code}/consol-breakdown`（Phase 2，未就绪时友好降级）
- `source='note'` → `GET /api/consolidation/notes/{pid}/{year}/{section_id}/consol-breakdown`（Phase 3 新建）
- 两 source 归一化为统一行结构 `{company_code, company_name, amount, elimination_amount?, source_project_id?}`，渲染同一 el-table（子公司名称 / 金额 GtAmountCell / 占比 / 抵销额 + 底部合并数）。
- 点子公司行 → 跳该单体报表/附注 + 纳入 Backspace 返回栈（T3）；跳转前项目级权限预检（EH2）。

## 后果

- 正向：一个组件服务两场景，渲染一致；由 T1 vitest（7 测试）守门渲染契约不分叉。
- 代价：props 分支（source 决定端点）；report 端点依赖 Phase 2，未就绪时降级为友好空态而非报错。
- 注：附注 by_company 行的 `source_project_id` 由 Phase 3 V2 provenance 写入（`_build_section_consolidation_breakdown` 已带），缺失时降级为不跳转（ElMessage.info）。
