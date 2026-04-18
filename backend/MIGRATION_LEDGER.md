# 代码迁移台账

## 路径口径不统一

| 当前路径 | 权威路径 | 状态 | 说明 |
|---------|---------|------|------|
| `/api/projects/{id}/workpapers/...` | `/api/projects/{id}/working-papers/...` | 共存 | 新代码统一用 working-papers |
| `process_record.py` 中的 `/workpapers/` | 应改为 `/working-papers/` | 待迁移 | breaking change，需前端同步改 |

## 待淘汰路由文件（32个死代码）

以下路由文件未注册到 main.py，使用同步 ORM 风格，启用前需转异步：

- ai_admin.py / ai_chat.py / ai_confirmation.py / ai_contract.py
- ai_evidence_chain.py / ai_knowledge.py / ai_ocr.py / ai_pdf_export.py
- ai_report.py / ai_risk_assessment.py / ai_workpaper.py
- archive.py / audit_findings.py / audit_logs.py / audit_plan.py / audit_program.py
- auth.py（旧版，与 api/auth.py 冲突）
- companies.py / component_auditors.py（与 component_auditor.py 重复）
- confirmations.py / going_concern.py / management_letter.py
- nl_command.py / notifications.py / pbc.py / project_mgmt.py
- review.py / reviews.py（同前缀冲突）
- risk.py / sync.py / sync_conflict.py / users.py（与 api/users.py 重复）

## 两套前端

| 前端 | 定位 | 状态 |
|------|------|------|
| `audit-platform/frontend/` | 正式主前端 | 权威 |
| `frontend/` | AI 子前端原型 | 保留但不扩展 |
