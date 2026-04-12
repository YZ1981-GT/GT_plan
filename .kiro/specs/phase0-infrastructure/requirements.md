# 需求文档：第零阶段 — 技术基础设施

## 简介

本文档定义审计作业平台第零阶段（技术基础设施）的需求。第零阶段为后续所有业务功能提供技术地基，涵盖开发环境搭建、数据库初始化、用户认证与权限框架、统一API规范与中间件、前端项目骨架，以及ONLYOFFICE集成技术验证（POC）。预计工期2-3周。

## 术语表

- **Platform（审计作业平台）**：面向会计师事务所的本地私有化审计全流程作业系统，本文档中所有需求的目标系统
- **Developer（开发者）**：使用本系统进行开发和部署的技术人员
- **Administrator（管理员）**：拥有系统最高权限的用户角色，负责用户管理和系统配置
- **User（用户）**：使用审计作业平台的所有角色的统称，包括管理员、合伙人、项目经理、审计员、质控部、只读用户
- **Auth_Service（认证服务）**：负责用户身份验证和JWT令牌管理的后端服务模块
- **Permission_Framework（权限框架）**：基于角色的访问控制系统，管理6种角色（管理员/合伙人/项目经理/审计员/质控部/只读）的功能权限
- **API_Gateway（API网关层）**：统一处理请求路由、认证校验、错误处理和操作日志记录的中间件层
- **Audit_Log_Middleware（操作日志中间件）**：自动记录所有写操作的中间件，记录操作人、时间、类型、对象、改前值、改后值、IP地址
- **Migration_Framework（迁移框架）**：基于Alembic的数据库Schema版本管理和迁移工具
- **Frontend_Shell（前端骨架）**：基于Vue 3 + TypeScript + Element Plus的前端项目基础框架，包含路由、状态管理和GT品牌视觉基础
- **ONLYOFFICE_POC（ONLYOFFICE概念验证）**：验证ONLYOFFICE Document Server与后端WOPI协议对接、自定义函数和插件开发可行性的技术验证项目
- **WOPI_Host（WOPI宿主服务）**：后端实现的Web Application Open Platform Interface协议接口，管理ONLYOFFICE与后端的文件交互
- **Health_Check_Endpoint（健康检查端点）**：`/api/health` 接口，用于监控后端服务、数据库连接和Redis连接的可用状态
- **JWT（JSON Web Token）**：用于用户身份认证的令牌机制，有效期2小时，支持刷新
- **Docker_Compose_Environment（Docker Compose开发环境）**：通过docker-compose.yml一键启动PostgreSQL、Redis、FastAPI、ONLYOFFICE Document Server的本地开发环境

## 需求

### 需求 1：Docker Compose 一键开发环境

**用户故事：** 作为开发者，我希望通过一条命令启动完整的本地开发环境，以便快速开始开发工作而无需手动配置各个服务。

#### 验收标准

1. WHEN Developer executes `docker-compose up`, THE Docker_Compose_Environment SHALL start PostgreSQL 16, Redis, FastAPI backend, and ONLYOFFICE Document Server containers within 120 seconds
2. THE Docker_Compose_Environment SHALL expose PostgreSQL on port 5432, Redis on port 6379, FastAPI on port 8000, and ONLYOFFICE Document Server on port 8080 via configurable port mappings
3. THE Docker_Compose_Environment SHALL persist PostgreSQL data and Redis data through named Docker volumes so that data survives container restarts
4. THE Docker_Compose_Environment SHALL use environment variables defined in a `.env` file for all configurable parameters including database credentials, Redis URL, JWT secret key, and service ports
5. THE Docker_Compose_Environment SHALL define health checks for PostgreSQL, Redis, and FastAPI containers so that dependent services start only after their dependencies are healthy
6. WHEN Developer executes `docker-compose down`, THE Docker_Compose_Environment SHALL stop all containers gracefully within 30 seconds
7. THE Docker_Compose_Environment SHALL include a `.env.example` file documenting all required and optional environment variables with default values and descriptions

### 需求 2：数据库Schema初始化与Alembic迁移框架

**用户故事：** 作为开发者，我希望数据库Schema通过版本化迁移脚本管理，以便团队协作时数据库变更可追踪、可回滚。

#### 验收标准

1. THE Migration_Framework SHALL initialize the following core tables on first migration: `users`, `projects`, `project_users`, `logs`, `notifications`
2. THE `users` table SHALL contain columns: `id` (UUID primary key), `username` (unique, not null), `email` (unique, not null), `hashed_password` (not null), `role` (enum: admin/partner/manager/auditor/qc/readonly), `office_code` (varchar), `is_active` (boolean, default true), `is_deleted` (boolean, default false), `deleted_at` (timestamp, nullable), `created_at` (timestamp), `updated_at` (timestamp), `created_by` (UUID, nullable), `updated_by` (UUID, nullable)
3. THE `projects` table SHALL contain columns: `id` (UUID primary key), `name` (not null), `client_name` (not null), `audit_period_start` (date), `audit_period_end` (date), `project_type` (enum: annual/special/ipo/internal_control), `materiality_level` (numeric, nullable), `status` (enum: created/planning/execution/completion/reporting/archived), `manager_id` (UUID, foreign key to users), `partner_id` (UUID, foreign key to users), `is_deleted` (boolean, default false), `deleted_at` (timestamp, nullable), `created_at`, `updated_at`, `created_by`, `updated_by`, `version` (integer, default 1)
4. THE `project_users` table SHALL contain columns: `id` (UUID primary key), `project_id` (UUID, foreign key to projects, not null), `user_id` (UUID, foreign key to users, not null), `role` (enum: partner/manager/auditor/qc/readonly), `permission_level` (enum: edit/review/readonly), `scope_cycles` (text, nullable, for audit cycle assignment), `scope_accounts` (text, nullable, for account assignment), `valid_from` (date), `valid_to` (date, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`
5. THE `logs` table SHALL contain columns: `id` (UUID primary key), `user_id` (UUID, foreign key to users), `action_type` (varchar, not null), `object_type` (varchar, not null), `object_id` (UUID), `old_value` (jsonb, nullable), `new_value` (jsonb, nullable), `ip_address` (varchar), `created_at` (timestamp, not null)
6. THE `notifications` table SHALL contain columns: `id` (UUID primary key), `recipient_id` (UUID, foreign key to users, not null), `message_type` (varchar, not null), `title` (varchar, not null), `content` (text), `related_object_type` (varchar, nullable), `related_object_id` (UUID, nullable), `is_read` (boolean, default false), `created_at` (timestamp, not null)
7. THE Migration_Framework SHALL create composite indexes on `project_users(project_id, user_id)`, `logs(object_type, object_id)`, `logs(user_id, created_at)`, and `notifications(recipient_id, is_read)`
8. WHEN Developer runs `alembic upgrade head`, THE Migration_Framework SHALL apply all pending migrations in order
9. WHEN Developer runs `alembic downgrade -1`, THE Migration_Framework SHALL revert the most recent migration
10. THE Migration_Framework SHALL enforce that all tables with business data include `is_deleted` (boolean) and `deleted_at` (timestamp) columns for soft delete support

### 需求 3：用户认证（JWT）与基础权限框架

**用户故事：** 作为管理员，我希望系统提供安全的用户认证和基于角色的权限控制，以便不同角色的用户只能访问其被授权的功能。

#### 验收标准

1. WHEN User submits valid username and password to `POST /api/auth/login`, THE Auth_Service SHALL return a JWT access token (valid for 2 hours) and a refresh token
2. WHEN User submits an expired access token with a valid refresh token to `POST /api/auth/refresh`, THE Auth_Service SHALL return a new access token
3. WHEN User submits invalid credentials to `POST /api/auth/login`, THE Auth_Service SHALL return HTTP 401 with error message "用户名或密码错误"
4. WHEN User fails login 5 consecutive times for the same username, THE Auth_Service SHALL lock the account for 30 minutes and return HTTP 423 with error message "账号已锁定，请30分钟后重试"
5. THE Auth_Service SHALL store passwords using bcrypt hashing with a cost factor of at least 12
6. THE Permission_Framework SHALL support 6 roles: admin, partner, manager, auditor, qc, readonly
7. THE Permission_Framework SHALL provide a dependency injection function `require_role(allowed_roles)` that can be applied to any API endpoint to restrict access by role
8. THE Permission_Framework SHALL provide a dependency injection function `require_project_access(project_id, min_permission)` that verifies the current user has access to the specified project with at least the specified permission level (edit/review/readonly)
9. WHEN an unauthenticated request accesses a protected endpoint, THE API_Gateway SHALL return HTTP 401 with a standardized error response
10. WHEN an authenticated user without sufficient role accesses a restricted endpoint, THE API_Gateway SHALL return HTTP 403 with error message "权限不足"
11. THE Auth_Service SHALL provide `POST /api/auth/logout` endpoint that invalidates the current refresh token
12. WHEN Administrator calls `POST /api/users` with valid user data, THE Auth_Service SHALL create a new user account and return the user profile (excluding password)
13. THE Auth_Service SHALL provide `GET /api/users/me` endpoint that returns the current authenticated user's profile information

### 需求 4：统一API规范、错误处理与操作日志中间件

**用户故事：** 作为开发者，我希望所有API遵循统一的请求/响应规范并自动记录操作日志，以便前后端协作高效且所有写操作可追溯。

#### 验收标准

1. THE API_Gateway SHALL return all successful responses in the format `{"code": 200, "message": "success", "data": <payload>}`
2. THE API_Gateway SHALL return all error responses in the format `{"code": <http_status>, "message": <error_description>, "detail": <optional_detail>}`
3. THE API_Gateway SHALL handle uncaught exceptions and return HTTP 500 with error message "服务器内部错误" without exposing stack traces to the client
4. THE API_Gateway SHALL validate all request bodies using Pydantic models and return HTTP 422 with field-level error details for validation failures
5. WHEN any API endpoint performs a write operation (POST, PUT, PATCH, DELETE), THE Audit_Log_Middleware SHALL automatically record an entry in the `logs` table containing: user_id, action_type, object_type, object_id, old_value (for updates and deletes), new_value (for creates and updates), ip_address, and timestamp
6. THE Audit_Log_Middleware SHALL extract the client IP address from the `X-Forwarded-For` header or the direct connection address
7. THE API_Gateway SHALL add CORS headers allowing requests from the configured frontend origin
8. THE API_Gateway SHALL provide a `GET /api/health` endpoint that returns the health status of the backend service, PostgreSQL connection, and Redis connection without requiring authentication
9. WHEN PostgreSQL or Redis is unreachable, THE Health_Check_Endpoint SHALL return HTTP 503 with details indicating which service is unavailable
10. THE API_Gateway SHALL use a consistent API path prefix `/api` for all business endpoints and `/wopi` for WOPI protocol endpoints
11. THE API_Gateway SHALL generate OpenAPI documentation accessible at `/docs` (Swagger UI) and `/redoc` (ReDoc)
12. THE Audit_Log_Middleware SHALL capture the old_value by reading the current state of the object before the write operation executes, and capture the new_value from the result of the write operation

### 需求 5：前端项目骨架

**用户故事：** 作为开发者，我希望前端项目具备完整的基础框架和致同GT品牌视觉规范，以便后续业务页面开发可以直接在此骨架上迭代。

#### 验收标准

1. THE Frontend_Shell SHALL be initialized as a Vue 3 project with TypeScript, Vite build tool, and Element Plus component library
2. THE Frontend_Shell SHALL configure Vue Router with the following base routes: `/login` (login page), `/` (dashboard/home), `/projects` (project list), and a catch-all 404 page
3. THE Frontend_Shell SHALL configure Pinia as the state management library with a `useAuthStore` store managing user authentication state (token, user profile, login/logout actions)
4. THE Frontend_Shell SHALL include an Axios HTTP client wrapper that automatically attaches the JWT token to request headers, handles 401 responses by redirecting to login, and handles token refresh
5. THE Frontend_Shell SHALL implement route guards that redirect unauthenticated users to the login page
6. THE Frontend_Shell SHALL include a base layout component with a sidebar navigation, top header bar (displaying current user and logout button), and main content area
7. THE Frontend_Shell SHALL define CSS custom properties (variables) following the GT brand specification: core purple `#4b2d77`, bright purple `#A06DFF`, deep purple `#2B1D4D`, teal `#0094B3`, coral `#FF5149`, wheat yellow `#FFC23D`, success green `#28A745`
8. THE Frontend_Shell SHALL use the CSS class naming convention with `gt-` prefix (e.g., `gt-button`, `gt-card`, `gt-table`)
9. THE Frontend_Shell SHALL configure the font stack: Chinese fonts (FZYueHei → Microsoft YaHei → PingFang SC), English fonts (GT Walsheim → Helvetica Neue → Arial), with base font size 16px and line height 1.6
10. THE Frontend_Shell SHALL use a 4px grid spacing system with 8px as the primary rhythm unit
11. THE Frontend_Shell SHALL implement a functional login page that calls `POST /api/auth/login` and stores the returned JWT token
12. WHEN the page first loads, THE Frontend_Shell SHALL render the initial view within 2 seconds on a local network

### 需求 6：ONLYOFFICE集成技术POC

**用户故事：** 作为开发者，我希望在正式开发前验证ONLYOFFICE Document Server的WOPI协议对接、自定义函数和插件开发的可行性，以便确认技术方案可行并识别潜在风险。

#### 验收标准

1. THE ONLYOFFICE_POC SHALL deploy ONLYOFFICE Document Server as a Docker container within the Docker_Compose_Environment
2. THE ONLYOFFICE_POC SHALL implement a minimal WOPI_Host with the following endpoints: `GET /wopi/files/{file_id}` (CheckFileInfo), `GET /wopi/files/{file_id}/contents` (GetFile), `POST /wopi/files/{file_id}/contents` (PutFile)
3. WHEN a user opens a .xlsx file through the POC frontend page, THE ONLYOFFICE_POC SHALL load the file in the ONLYOFFICE editor embedded via iframe using the WOPI protocol
4. WHEN a user edits and saves a .xlsx file in the ONLYOFFICE editor, THE ONLYOFFICE_POC SHALL persist the changes back to the server through the WOPI PutFile endpoint
5. THE ONLYOFFICE_POC SHALL register at least one custom function (e.g., `TB(account_code, column_name)`) using the ONLYOFFICE `AddCustomFunction` API that makes an asynchronous HTTP request to a backend API endpoint and returns the result to the spreadsheet cell
6. THE ONLYOFFICE_POC SHALL develop a minimal ONLYOFFICE plugin that adds a sidebar panel displaying static content, verifying the plugin development and loading mechanism
7. THE ONLYOFFICE_POC SHALL produce a technical findings document recording: WOPI protocol compatibility results, custom function async API call latency, plugin loading mechanism, and any identified limitations or risks
8. IF ONLYOFFICE Document Server fails to start or the WOPI protocol integration encounters blocking issues, THEN THE ONLYOFFICE_POC SHALL document the failure details and propose alternative approaches
