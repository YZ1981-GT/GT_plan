# Implementation Plan

## Overview

实现 `require_operation` 授权工厂 + CI lint 脚本 + 首批 10 个高风险端点接入权限矩阵�?

## Tasks

- [x] 1. Implement `require_operation` dependency factory in `deps.py`
  - Add `require_operation(operation: str)` factory returning FastAPI Depends
  - Internally call `permission_matrix_service.can(system_role, project_role, operation)`
  - Add `_resolve_project_role(db, user_id, project_id)` helper (query ProjectUser �?project_role)
  - Unauthorized �?HTTPException(403, {"error_code": "OPERATION_NOT_ALLOWED"})
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Unit tests for `require_operation`
  - test_admin_passes_any_operation
  - test_auditor_denied_report_sign
  - test_manager_passes_wp_edit
  - test_no_project_role_uses_system_role_only
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 3. Create CI lint script `scripts/check/check_endpoint_auth.py`
  - Scan `backend/app/routers/*.py` for `@router.post/put/patch/delete` decorated functions
  - Check each function has `require_operation` or `require_project_access` in Depends
  - Maintain `_EXEMPT_ENDPOINTS` set (health/login/register/events SSE)
  - Output WARNING for missing, exit 0 (non-blocking initially)
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 4. Add CI step to `governance-checks.yml`
  - Run `python scripts/check/check_endpoint_auth.py`
  - Non-blocking (allow-failure) for first Sprint, switch to blocking after coverage reaches 80%
  - _Requirements: 2.2_

- [x] 5. Wire `require_operation` to first batch of 10 high-risk endpoints
  - [x] 5.1 `wp_html_save.save_html_data` �?`require_operation("wp:edit")`
  - [x] 5.2 `wp_editor_router.save_univer_data` �?`require_operation("wp:edit")`
  - [x] 5.3 `disclosure_notes.update_note` �?`require_operation("note:edit")`
  - [x] 5.4 `reports.generate_reports` �?`require_operation("report:edit")`
  - [x] 5.5 `archive.orchestrate` �?`require_operation("archive:manage")`
  - [x] 5.6 `signatures.sign_report` �?`require_operation("report:sign")`
  - [x] 5.7 `adjustments.create_adjustment` �?`require_operation("wp:edit")`
  - [x] 5.8 Confirm custom-query endpoints (spec #1) already use project access �?no duplicate
  - _Requirements: 3.1, 3.2_

- [x] 6. Integration tests for first batch endpoints (authorized + unauthorized)
  - 10 pairs: admin pass / auditor denied for each operation
  - _Requirements: 3.1, 3.2_

- [x] 7. Checkpoint
  - CI lint passes with 0 warnings on first batch
  - All unit + integration tests green
  - Existing tests no regression

## Task Dependency Graph

```json
{"waves":[["1","3"],["2","4"],["5"],["6"],["7"]]}
```
