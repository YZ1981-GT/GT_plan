# Requirements Document

## Introduction

权限矩阵（`permission_matrix_service.py`）作为操作权限单一真源已存在，但多个关键端点（如 §5.12/§5.13 custom-query、以及潜在的其他端点）绕过它直接操作。本 spec 建立**授权强制接入基线**：确保所有写/敏感读端点系统性地经过「权限矩阵操作校验 + 项目成员校验」两层授权，并引入 CI 检查防止未来端点遗漏授权声明。

覆盖条目：docs/architecture-improvement-proposals.md §17.1。

## Glossary

- **operation code**：`permission_matrix_service.OPERATION_CODES` 中定义的操作标识（如 `wp:edit`/`report:sign`）
- **require_project_access**：`deps.py` 中的项目级编辑/查看权限校验工厂函数
- **敏感端点**：涉及数据写入、导出、归档、签发的 router endpoint

## Requirements

### Requirement 1: 敏感端点授权声明 decorator/dependency

**User Story:** As a 安全工程师, I want 每个写/敏感读端点声明所需 operation code, so that 权限矩阵统一管控。

#### Acceptance Criteria

1. WHEN 新建一个写操作端点 THEN 必须通过 `Depends(require_operation("wp:edit"))` 或等价方式声明所需操作权限
2. WHEN 已登录用户的 (system_role, project_role) 组合不满足该 operation THEN 返回 403
3. WHEN admin/partner 角色访问任意端点 THEN 权限检查放行（OPERATION_CODES 全集）

### Requirement 2: CI lint 检查 — 敏感 router 无授权声明时告警

**User Story:** As a 开发团队, I want CI 自动检测新增的写端点是否声明了 operation code, so that 授权遗漏在 PR 阶段被发现。

#### Acceptance Criteria

1. WHEN `@router.post`/`@router.put`/`@router.patch`/`@router.delete` 修饰的函数不含 `require_operation`/`require_project_access` 相关 Depends THEN CI 脚本输出 WARNING（不阻断，逐步收紧）
2. WHEN 端点被加入豁免列表（如 `/health`/`/login`/`/register`） THEN 不告警
3. WHEN CI 检查通过 THEN 输出 "✅ 所有敏感端点已声明授权"

### Requirement 3: 既有高风险端点补齐授权（首批 10 个）

**User Story:** As a 平台用户, I want 首批高风险端点立即受权限矩阵管控, so that 授权体系有实际覆盖。

#### Acceptance Criteria

1. WHEN 以下端点被调用 THEN 必须经过 operation code 校验：
   - `custom_query.execute` / `batch-execute` / `cell-writeback`（已由 spec #1 修复，本 spec 确认接入 matrix）
   - `wp_html_save.save_html_data`（wp:edit）
   - `wp_editor_router.save_univer_data`（wp:edit）
   - `disclosure_notes.update_note`（note:edit）
   - `reports.generate_reports`（report:edit）
   - `archive.orchestrate`（archive:manage）
   - `signatures.sign_report`（report:sign）
   - `adjustments.create_adjustment`（wp:edit）
2. WHEN 未授权用户调用上述端点 THEN 返回 403 `{"error_code": "OPERATION_NOT_ALLOWED"}`
