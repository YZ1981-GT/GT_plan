# API 契约账

> 登记平台所有对外 API 路由的权限、错误码、前端调用路径。新增路由必须在此登记，CI 将校验。

## 登记规则

- 新增 API 路由的 PR 必须同步更新本表
- 权限列使用 `require_project_access("level")` 标记
- 错误码仅记录该端点特有的业务码（通用 401/403/500 不重复登记）

## 契约登记表

| 路由 | 方法 | 权限 | 错误码 | 前端路径 | 备注 |
|------|------|------|--------|----------|------|
| `/api/projects/{id}/trial-balance` | GET | readonly | 404 项目不存在 | `/projects/:id/trial-balance` | 试算平衡表 |
| `/api/projects/{id}/reports` | GET | readonly | 404 | `/projects/:id/reports` | 报表列表 |
| `/api/projects/{id}/adjustments` | GET/POST | edit | 400 分录不平 | `/projects/:id/adjustments` | 审计调整 |
| `/api/projects/{id}/disclosures` | GET | readonly | 404 | `/projects/:id/disclosures` | 附注列表 |
| `/api/projects/{id}/workpapers` | GET | readonly | 404 | `/projects/:id/workpapers` | 底稿列表 |
| `/api/projects/{id}/aging/calculate` | POST | edit | 422 配置无效 | `/projects/:id/aging` | 账龄计算 |
| `/api/projects/{id}/account-chart/import-async` | POST | edit | 400 文件格式 | `/projects/:id/account-chart` | 科目表导入 |
| `/api/projects/{id}/ai-content/pending` | GET | readonly | — | `/projects/:id/ai-review` | AI 待确认内容 |
| `/api/accounting-standards` | GET | 无（公开） | — | `/settings/standards` | 准则列表 |
| `/api/health` | GET | 无 | — | — | 健康检查 |

## 变更历史

| 日期 | 变更 | PR |
|------|------|----|
| 2025-01-01 | 初始骨架创建 | — |
