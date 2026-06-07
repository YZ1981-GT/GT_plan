# API 契约账

> 登记所有 API 路由的权限、错误码、对应前端路径。新增路由必须在此登记。

## 使用说明

- 新增 API 路由的 PR 必须同步更新本账本
- 权限列参考 `backend/app/services/allowed_actions_service.py`
- 错误码以 HTTP status + 业务 code 形式记录
- 前端路径指触发该 API 的主要页面

## 契约登记表

| # | 路由 | 方法 | Router 文件 | 权限 | 主要错误码 | 前端路径 |
|---|------|------|-------------|------|-----------|---------|
| 1 | `/api/projects` | GET | `backend/app/routers/project_wizard.py` | 登录用户 | 401 未认证 | `/projects` |
| 2 | `/api/projects/{id}/trial-balance` | GET | `backend/app/routers/trial_balance.py` | 项目成员 | 404 项目不存在 | `/projects/{id}/trial-balance` |
| 3 | `/api/projects/{id}/reports` | GET | `backend/app/routers/reports.py` | 项目成员 | 404 项目不存在 | `/projects/{id}/reports` |
| 4 | `/api/projects/{id}/adjustments` | GET/POST | `backend/app/routers/adjustments.py` | 项目成员（POST 需编辑权限） | 400 校验失败, 404 项目不存在 | `/projects/{id}/adjustments` |
| 5 | `/api/projects/{id}/workpapers` | GET | `backend/app/routers/working_paper.py` | 项目成员 | 404 项目不存在 | `/projects/{id}/workpapers` |
| 6 | `/api/projects/{id}/disclosure-notes` | GET | `backend/app/routers/disclosure_notes.py` | 项目成员 | 404 项目不存在 | `/projects/{id}/notes` |
| 7 | `/api/projects/{id}/ledger/penetration` | GET | `backend/app/routers/ledger_penetration.py` | 项目成员 | 404 科目不存在 | `/projects/{id}/ledger` |
| 8 | `/api/projects/{id}/drilldown` | GET | `backend/app/routers/drilldown.py` | 项目成员 | 404 行项不存在 | `/projects/{id}/reports`（穿透弹窗） |
| 9 | `/api/auth/login` | POST | `backend/app/routers/security.py` | 公开 | 401 密码错误, 429 限流 | `/login` |
| 10 | `/api/projects/{id}/deliverables` | GET/POST | `backend/app/routers/deliverable.py` | 项目经理+ | 403 权限不足 | `/projects/{id}/deliverables` |

## 待补登路由（存量债务）

> 当前 router 文件 307 个，仅登记 10 条高频路由。后续按模块逐步补全。

- [ ] 合并报表相关（consol_*）
- [ ] 质控相关（qc_*）
- [ ] 知识库相关（knowledge_*）
- [ ] 导入导出相关（import_*、export_*）
- [ ] AI 相关（ai_*、doc_ai_chat、wp_ai）

## 变更记录

| 日期 | 变更人 | 内容 |
|------|--------|------|
| 2026-06-06 | 初始化 | 创建账本骨架，登记 10 条高频 API |
