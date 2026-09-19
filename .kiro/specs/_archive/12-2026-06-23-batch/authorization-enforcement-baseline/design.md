# Design Document

## Overview

在 `deps.py` 中新增 `require_operation(op_code)` 工厂函数，封装 `permission_matrix_service.can(system_role, project_role, operation)` 判断。敏感端点通过 `Depends(require_operation("wp:edit"))` 接入。CI 脚本扫描 router 文件检测遗漏。

## Architecture

### 新增 `require_operation` 依赖工厂

```python
# deps.py
def require_operation(operation: str):
    async def dependency(
        current_user: User = Depends(get_current_user),
        project_id: UUID | None = None,  # 从 path/query/body 获取
        db: AsyncSession = Depends(get_db),
    ):
        from app.services.permission_matrix_service import can
        project_role = await _resolve_project_role(db, current_user.id, project_id)
        if not can(current_user.role, project_role, operation):
            raise HTTPException(403, {"error_code": "OPERATION_NOT_ALLOWED", "operation": operation})
        return current_user
    return dependency
```

### CI 脚本 `scripts/check/check_endpoint_auth.py`

扫描 `backend/app/routers/*.py`，对每个 `@router.post/put/patch/delete` 修饰函数检查是否包含 `require_operation`/`require_project_access`/`get_current_user` + 手动操作检查的 Depends。未声明的输出 WARNING + 端点路径。豁免列表 `_EXEMPT_ENDPOINTS`。

### 端点接入顺序

首批 10 个高风险端点（Req 3）→ 后续逐批覆盖（每个 Sprint 收敛 10~20 个）。

## Components and Interfaces

- **`require_operation(operation: str)`** — `deps.py` 中的 FastAPI Depends 工厂函数，内部调用 `permission_matrix_service.can()`
- **`scripts/check/check_endpoint_auth.py`** — CI lint 脚本，扫描 router 文件检测缺少授权声明的写端点

## Data Models

N/A — 无新数据模型。复用现有 `permission_matrix_service.OPERATION_CODES` 和 `ProjectUser` 表。

## Correctness Properties

Property 1: `require_operation("X")` 等价于 `permission_matrix_service.can(role, project_role, "X")` — 不引入任何额外逻辑

Property 2: admin/partner 对所有 operation 返回 True（全集）

Property 3: CI 脚本不误报豁免端点、不漏报无声明的写端点

## Testing Strategy

- Unit：mock user roles + operation → verify 403/pass
- Integration：首批 10 端点各一条（authorized pass / unauthorized 403）
- CI：在 governance-checks.yml 中加 step
