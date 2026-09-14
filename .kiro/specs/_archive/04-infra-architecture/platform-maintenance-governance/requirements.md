# 需求文档：平台治理、维护账本与工程卡点

## 需求

### 需求 1：平台治理四本账
1. THE system SHALL 维护 API 契约账，记录路由、请求响应、权限、错误码。
2. THE system SHALL 维护组件账，记录全局组件、适用场景、禁用组件、迁移计划。
3. THE system SHALL 维护数据口径账，记录金额、年度、准则、状态、stale、来源规则。
4. THE system SHALL 维护质量账，记录测试、PBT、压测、线上缺陷和回归范围。

### 需求 2：自动规模快照
1. THE system SHALL 提供脚本自动统计 routers、services、models、views、components、composables、migrations、tests。
2. WHEN 规模快照生成，THE system SHALL 写入架构文档的标记区块。
3. WHEN 手工文档规模数字与脚本输出不一致，THE CI SHALL fail 或提示更新。

### 需求 3：新增代码治理卡点
1. WHEN 新增页面，THE PR SHALL 说明使用哪些全局组件。
2. WHEN 新增金额字段，THE PR SHALL 说明 Decimal 序列化方式。
3. WHEN 新增状态，THE PR SHALL 说明是否进入枚举字典。
4. WHEN 新增路由，THE PR SHALL 配权限、错误码、前端路径。
5. WHEN 新增 AI 功能，THE PR SHALL 配人工确认机制。
6. WHEN 新增穿透，THE PR SHALL 使用 LinkageContract。

### 需求 4：超大文件与重复模块治理
1. THE system SHALL 对超大 Vue/Python 文件设置 baseline 和收敛计划。
2. THE system SHALL 对 composable、service、formula engine 等同族模块建立注册表。
3. WHEN 新增 composable/service 与现有能力重叠，THE CI SHALL 提示评审。

### 需求 5：数据库与 SQL 契约
1. THE system SHALL 检查 DDL、ORM、service 三层一致。
2. THE system SHALL 检查 ORM 和裸 SQL 引用不存在列。
3. WHEN 发现字段漂移或不存在列引用，THE CI SHALL fail。

### 需求 6：上线运维检查
1. THE system SHALL 提供上线 smoke checklist，覆盖健康检查、OnlyOffice/WOPI、Redis、Postgres、迁移、Worker、SSE。
2. THE system SHALL 提供容量与备份演练记录。
3. THE system SHALL 提供 degraded 状态总览。

## 范围边界
- 不替代现有 CI，只新增检查项。
- 不一次性修复所有历史债务，先建立账本和卡点。
- 不改变现有 Git 工作流。

## 实施批次

- **P0 核心闭环**：四本账骨架、规模快照、SQL 列契约、PR checklist、smoke checklist。
- **P1 试点增强**：超大文件 baseline、composable/service 注册表、CI 提示。
- **P2 规模化治理**：自动更新账本、重复模块检测、生产容量与备份演练。

## Properties / 验收不变量

1. **Property 1：规模快照可复现**  
   同一提交上重复运行规模快照脚本，输出 SHALL 一致。
2. **Property 2：不存在列引用零容忍**  
   ORM 或裸 SQL 引用不存在列时，CI SHALL fail。
3. **Property 3：新增路由必须有契约**  
   新增 API 路由必须在 API 契约账中登记权限、错误码和前端路径。
4. **Property 4：新增全局能力不重复**  
   新增 composable/service 时必须说明是否复用或替代现有能力。
5. **Property 5：smoke checklist 环境分层**  
   本地、试点、生产 SHALL 有各自检查项，不得混用。

## 依赖关系

- 本 spec 是其他 5 个 spec 的工程治理前置。
- 与现有 `.github/workflows/ci.yml`、`backend/scripts/check/*`、`.git-hooks/pre-commit` 对齐。

## UAT / 运维场景

1. 新人根据四本账找到某 API、组件、金额口径和测试范围。
2. 开发新增不存在列引用，CI 能失败。
3. 试点上线前按 smoke checklist 检查 OnlyOffice/WOPI、Redis、Postgres、Worker、SSE。
4. 架构规模数字由脚本生成而非人工维护。
