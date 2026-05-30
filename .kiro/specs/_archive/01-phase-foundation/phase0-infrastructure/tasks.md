# 实施计划：第零阶段 — 技术基础设施

## 概述

按照设计文档的6个核心模块，将实现拆分为10个递进式任务组。每个任务构建在前序任务之上，最终完成完整的技术基础设施。后端使用 Python (FastAPI)，前端使用 TypeScript (Vue 3)。

## 任务

- [x] 1. Docker Compose 环境搭建
  - [x] 1.1 创建 `.env.example` 和 `.env` 文件
    - 定义所有环境变量：PG_USER, PG_PASSWORD, PG_DB, PG_PORT, REDIS_URL, REDIS_PORT, JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_REFRESH_TOKEN_EXPIRE_DAYS, API_PORT, OFFICE_PORT, CORS_ORIGINS, ONLYOFFICE_URL, WOPI_BASE_URL, STORAGE_ROOT
    - 每个变量附带注释说明用途和默认值
    - _需求: 1.4, 1.7_

  - [x] 1.2 创建 `docker-compose.yml`
    - 定义4个服务：postgres (postgres:16-alpine), redis (redis:7-alpine), backend (本地构建), onlyoffice (onlyoffice/documentserver:8.2)
    - 配置端口映射使用环境变量：`${PG_PORT:-5432}:5432`, `${REDIS_PORT:-6379}:6379`, `${API_PORT:-8000}:8000`, `${OFFICE_PORT:-8080}:80`
    - 配置命名卷：pg_data, redis_data, office_data
    - 配置健康检查：pg_isready, redis-cli ping, curl /api/health, curl /healthcheck
    - 配置 depends_on 使用 condition: service_healthy 确保启动顺序
    - _需求: 1.1, 1.2, 1.3, 1.5, 1.6_

  - [x] 1.3 创建 `backend/Dockerfile`
    - 基于 python:3.12-slim，安装依赖，复制代码，uvicorn 启动
    - _需求: 1.1_

- [x] 2. 后端项目骨架
  - [x] 2.1 创建 FastAPI 入口 (`backend/app/main.py`)
    - 初始化 FastAPI 应用，配置 title/description/version
    - 注册 CORS 中间件，允许 CORS_ORIGINS 配置的前端源
    - 挂载路由前缀 `/api` 和 `/wopi`
    - 配置 OpenAPI 文档 `/docs` (Swagger UI) 和 `/redoc`
    - _需求: 4.7, 4.10, 4.11_

  - [x] 2.2 创建配置管理 (`backend/app/core/config.py`)
    - 使用 pydantic-settings 的 BaseSettings 定义 Settings 类
    - 包含所有配置项：DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_REFRESH_TOKEN_EXPIRE_DAYS, CORS_ORIGINS, LOGIN_MAX_ATTEMPTS, LOGIN_LOCK_MINUTES, ONLYOFFICE_URL, WOPI_BASE_URL, STORAGE_ROOT
    - 从 .env 文件加载配置
    - _需求: 1.4_

  - [x] 2.3 创建数据库连接 (`backend/app/core/database.py`)
    - 使用 SQLAlchemy 2.0 异步引擎 (create_async_engine + asyncpg)
    - 配置连接池 pool_size=10, max_overflow=20
    - 创建 async_sessionmaker 工厂
    - 实现 get_db 依赖注入生成器
    - _需求: 2.1_

  - [x] 2.4 创建 Redis 连接 (`backend/app/core/redis.py`)
    - 使用 redis.asyncio 创建连接池
    - 实现 get_redis 依赖注入
    - _需求: 1.1_

  - [x] 2.5 创建 `backend/requirements.txt`
    - 列出所有依赖：fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, redis, python-jose[cryptography], passlib[bcrypt], httpx, python-multipart
    - _需求: 1.1_

- [x] 3. 数据库 Schema 与 Alembic 迁移
  - [x] 3.1 创建 SQLAlchemy 模型基类 (`backend/app/models/base.py`)
    - 实现 SoftDeleteMixin (is_deleted, deleted_at)
    - 实现 TimestampMixin (created_at, updated_at)
    - 实现 AuditMixin (created_by, updated_by)
    - 定义 PostgreSQL 枚举类型：user_role, project_type, project_status, project_user_role, permission_level
    - _需求: 2.10_

  - [x] 3.2 创建5张核心表模型
    - User 模型：id(UUID PK), username(unique), email(unique), hashed_password, role(user_role enum), office_code, is_active + SoftDeleteMixin + TimestampMixin + AuditMixin
    - Project 模型：id(UUID PK), name, client_name, audit_period_start/end, project_type, materiality_level, status, manager_id(FK), partner_id(FK), version + SoftDeleteMixin + TimestampMixin + AuditMixin
    - ProjectUser 模型：id(UUID PK), project_id(FK), user_id(FK), role, permission_level, scope_cycles, scope_accounts, valid_from, valid_to + SoftDeleteMixin + TimestampMixin
    - Log 模型：id(UUID PK), user_id(FK), action_type, object_type, object_id, old_value(JSONB), new_value(JSONB), ip_address, created_at
    - Notification 模型：id(UUID PK), recipient_id(FK), message_type, title, content, related_object_type, related_object_id, is_read, created_at
    - _需求: 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.3 初始化 Alembic 配置
    - 创建 `backend/alembic.ini` 和 `backend/alembic/env.py`
    - 配置异步迁移支持 (使用 run_async_migrations)
    - 从 Settings 读取 DATABASE_URL
    - _需求: 2.8_

  - [x] 3.4 创建初始迁移脚本 (`001_init_core_tables.py`)
    - 创建5张表及所有枚举类型
    - 创建复合索引：project_users(project_id, user_id) WHERE is_deleted=false, logs(object_type, object_id), logs(user_id, created_at DESC), notifications(recipient_id, is_read)
    - 创建过滤索引：users(is_active) WHERE is_deleted=false, projects(status) WHERE is_deleted=false
    - 实现 downgrade 函数支持回滚
    - _需求: 2.1, 2.7, 2.8, 2.9_

  - [x]* 3.5 编写属性测试：软删除字段强制存在
    - **Property 2: 软删除字段强制存在**
    - 遍历所有继承业务基类的 SQLAlchemy 模型，验证均包含 is_deleted 和 deleted_at 列
    - **验证: 需求 2.10**

- [x] 4. 检查点 — 确保数据库迁移正常
  - 运行 `alembic upgrade head` 验证表创建成功
  - 运行 `alembic downgrade -1` 验证回滚正常
  - 确保所有测试通过，如有问题请向用户确认

- [x] 5. 认证模块
  - [x] 5.1 创建安全工具 (`backend/app/core/security.py`)
    - 实现 JWT 编解码：create_access_token (2h过期), create_refresh_token (7d过期), decode_token
    - 实现密码哈希：hash_password (bcrypt, cost factor ≥ 12), verify_password
    - _需求: 3.1, 3.5_

  - [x] 5.2 创建认证 Pydantic 模型 (`backend/app/schemas/auth.py`)
    - LoginRequest (username, password)
    - TokenResponse (access_token, refresh_token, token_type, user)
    - RefreshRequest (refresh_token)
    - UserCreate (username, email, password, role, office_code)
    - UserResponse (id, username, email, role, office_code, is_active, created_at — 排除密码字段)
    - _需求: 3.1, 3.12_

  - [x] 5.3 创建统一响应模型 (`backend/app/schemas/common.py`)
    - ApiResponse (code, message, data) — 成功响应格式
    - ErrorResponse (code, message, detail) — 错误响应格式
    - _需求: 4.1, 4.2_

  - [x] 5.4 创建认证服务 (`backend/app/services/auth_service.py`)
    - login: 验证用户名密码，检查账号锁定状态(Redis INCR + TTL 30min)，5次失败锁定，成功后清除失败计数，生成 token 对
    - refresh: 验证 refresh_token 有效性(Redis)，生成新 access_token
    - logout: 将 refresh_token 加入 Redis 黑名单
    - create_user: 创建用户，密码 bcrypt 哈希存储
    - get_current_user_profile: 查询当前用户信息
    - _需求: 3.1, 3.2, 3.3, 3.4, 3.5, 3.11, 3.12, 3.13_

  - [x] 5.5 创建认证路由 (`backend/app/api/auth.py`)
    - POST /api/auth/login — 登录，返回 token 对
    - POST /api/auth/refresh — 刷新 access_token
    - POST /api/auth/logout — 登出，失效 refresh_token
    - _需求: 3.1, 3.2, 3.11_

  - [x] 5.6 创建用户路由 (`backend/app/api/users.py`)
    - POST /api/users — 创建用户（仅 admin 角色）
    - GET /api/users/me — 获取当前用户信息
    - _需求: 3.12, 3.13_

  - [x]* 5.7 编写属性测试：有效凭据登录返回令牌
    - **Property 3: 有效凭据登录返回令牌**
    - 使用 Hypothesis st.text() 生成用户名/密码，创建用户后登录，验证返回 access_token 和 refresh_token 非空，且 access_token 可解码出正确 user_id
    - **验证: 需求 3.1**

  - [x]* 5.8 编写属性测试：密码 bcrypt 安全存储
    - **Property 5: 密码 bcrypt 安全存储**
    - 使用 Hypothesis st.text(min_size=1) 生成密码，验证哈希后以 $2b$ 开头且 cost factor ≥ 12
    - **验证: 需求 3.5**

  - [x]* 5.9 编写属性测试：令牌刷新生命周期
    - **Property 4: 令牌刷新生命周期**
    - 验证 access_token 过期后使用有效 refresh_token 可获取新 access_token，且新 token 中 user_id 一致
    - **验证: 需求 3.2**

  - [x]* 5.10 编写属性测试：登出令牌失效
    - **Property 8: 登出令牌失效**
    - 验证登出后使用同一 refresh_token 刷新应返回 401
    - **验证: 需求 3.11**

  - [x]* 5.11 编写属性测试：用户创建响应排除密码
    - **Property 9: 用户创建响应排除密码**
    - 验证 POST /api/users 响应体中不包含 password、hashed_password 字段
    - **验证: 需求 3.12**

  - [x]* 5.12 编写属性测试：当前用户信息一致性
    - **Property 10: 当前用户信息一致性**
    - 验证 GET /api/users/me 返回的 id/username/email/role 与数据库记录一致
    - **验证: 需求 3.13**

- [x] 6. 权限框架
  - [x] 6.1 创建依赖注入 (`backend/app/deps.py`)
    - get_current_user: 从 Authorization header 解析 JWT，查询用户，验证 is_active 和 is_deleted
    - require_role(allowed_roles): 角色校验依赖，不在列表中返回 403 "权限不足"
    - require_project_access(min_permission): 项目级权限校验，admin 跳过检查，其他角色查询 project_users 表，按 edit > review > readonly 层级比较
    - 未认证请求返回 401 标准错误响应
    - _需求: 3.7, 3.8, 3.9, 3.10_

  - [x]* 6.2 编写属性测试：角色访问控制正确性
    - **Property 6: 角色访问控制正确性**
    - 使用 Hypothesis st.sampled_from(roles) × st.lists(st.sampled_from(roles)) 生成角色和 allowed_roles 组合
    - 角色在列表中 → 2xx，不在列表中 → 403，无 token → 401
    - **验证: 需求 3.3, 3.7, 3.9, 3.10**

  - [x]* 6.3 编写属性测试：项目级权限层级正确性
    - **Property 7: 项目级权限层级正确性**
    - 使用 Hypothesis st.sampled_from(permission_levels) 生成实际权限和最低要求组合
    - 验证 edit > review > readonly 层级关系，admin 跳过检查
    - **验证: 需求 3.8**

- [x] 7. API 中间件
  - [x] 7.1 创建统一响应包装中间件 (`backend/app/middleware/response.py`)
    - 成功响应包装为 {"code": 200, "message": "success", "data": <payload>}
    - _需求: 4.1_

  - [x] 7.2 创建全局异常处理 (`backend/app/middleware/error_handler.py`)
    - HTTPException → 对应状态码和消息
    - RequestValidationError → 422 + 字段级错误详情
    - Exception → 500 "服务器内部错误"，记录堆栈到日志文件，不暴露给客户端
    - _需求: 4.2, 4.3, 4.4_

  - [x] 7.3 创建操作日志中间件 (`backend/app/middleware/audit_log.py`)
    - 拦截 POST/PUT/PATCH/DELETE 请求
    - 跳过 /api/auth/login, /api/health 等无需记录的端点
    - 执行前读取对象当前状态 → old_value
    - 执行后读取操作结果 → new_value
    - 异步写入 logs 表，写入失败不影响业务响应
    - 提取 IP：优先 X-Forwarded-For，回退 request.client.host
    - action_type 映射：POST→create, PUT/PATCH→update, DELETE→delete
    - object_type 从路由路径提取
    - _需求: 4.5, 4.6, 4.12_

  - [x] 7.4 创建健康检查路由 (`backend/app/api/health.py`)
    - GET /api/health 无需认证
    - 检查 PostgreSQL 连接 (SELECT 1)
    - 检查 Redis 连接 (PING)
    - 全部可用 → 200，任一不可用 → 503 + 详情
    - _需求: 4.8, 4.9_

  - [x] 7.5 在 main.py 中注册所有中间件
    - 按顺序注册：CORS → 全局异常处理 → 统一响应包装 → 操作日志
    - 注册所有路由：auth, users, health, wopi
    - _需求: 4.7, 4.10_

  - [x]* 7.6 编写属性测试：API 响应格式一致性
    - **Property 11: API 响应格式一致性**
    - 使用 Hypothesis st.sampled_from(endpoints) 遍历端点，验证成功响应和错误响应格式
    - **验证: 需求 4.1, 4.2**

  - [x]* 7.7 编写属性测试：异常处理隐藏内部信息
    - **Property 12: 异常处理隐藏内部信息**
    - 使用 Hypothesis st.sampled_from(exception_types) 模拟异常，验证 500 响应不含 traceback/文件路径/变量名
    - **验证: 需求 4.3**

  - [x]* 7.8 编写属性测试：Pydantic 校验返回 422
    - **Property 13: Pydantic 校验返回 422**
    - 使用 Hypothesis st.dictionaries() 生成随机请求体，验证不合法数据返回 422 + 字段级错误
    - **验证: 需求 4.4**

  - [x]* 7.9 编写属性测试：写操作审计日志完整性
    - **Property 14: 写操作审计日志完整性**
    - 使用 Hypothesis st.sampled_from(write_endpoints) × st.text() 生成 IP，验证 logs 表记录完整
    - **验证: 需求 4.5, 4.6, 4.12**

  - [x]* 7.10 编写属性测试：健康检查服务状态准确性
    - **Property 15: 健康检查服务状态准确性**
    - 使用 Hypothesis st.booleans() × 2 模拟 PG/Redis 可用性组合，验证返回码和详情
    - **验证: 需求 4.8, 4.9**

- [x] 8. 检查点 — 后端核心功能验证
  - 运行全部后端测试 `pytest backend/tests/`
  - 使用 httpx 测试完整登录流程：创建用户 → 登录 → 访问受保护端点 → 刷新 token → 登出
  - 验证操作日志记录正确
  - 确保所有测试通过，如有问题请向用户确认

- [x] 9. 前端项目骨架
  - [x] 9.1 初始化 Vue 3 项目
    - 使用 Vite 创建 Vue 3 + TypeScript 项目
    - 安装依赖：vue-router, pinia, element-plus, axios
    - 配置 vite.config.ts（代理 /api → backend:8000）
    - 创建 `frontend/index.html`, `frontend/src/main.ts`, `frontend/src/App.vue`
    - _需求: 5.1_

  - [x] 9.2 创建 GT 品牌视觉 Token (`frontend/src/styles/gt-tokens.css`)
    - 定义 CSS 自定义属性：--gt-color-primary (#4b2d77), --gt-color-primary-light (#A06DFF), --gt-color-primary-dark (#2B1D4D), --gt-color-teal (#0094B3), --gt-color-coral (#FF5149), --gt-color-wheat (#FFC23D), --gt-color-success (#28A745)
    - 定义间距系统：4px 网格，8px 主节奏
    - 定义字体栈：中文 (FZYueHei → Microsoft YaHei → PingFang SC)，英文 (GT Walsheim → Helvetica Neue → Arial)，base 16px, line-height 1.6
    - 定义圆角、阴影变量
    - _需求: 5.7, 5.9, 5.10_

  - [x] 9.3 创建全局样式 (`frontend/src/styles/global.css`)
    - 引入 gt-tokens.css
    - 使用 gt- 前缀命名自定义 CSS 类
    - 配置 Element Plus 主题覆盖（primary color 使用 GT 紫色）
    - _需求: 5.8_

  - [x] 9.4 配置路由 (`frontend/src/router/index.ts`)
    - /login → Login.vue（已登录跳转 /）
    - / → Dashboard.vue（requireAuth 守卫）
    - /projects → Projects.vue（requireAuth 守卫）
    - /:pathMatch(.*)* → NotFound.vue
    - 实现 beforeEach 路由守卫：未登录重定向到 /login
    - _需求: 5.2, 5.5_

  - [x] 9.5 创建 Pinia 认证 Store (`frontend/src/stores/auth.ts`)
    - 定义 AuthState: token, refreshToken, user
    - 实现 actions: login(), logout(), refreshToken(), fetchUserProfile()
    - token 持久化到 localStorage
    - _需求: 5.3_

  - [x] 9.6 创建 Axios HTTP 客户端 (`frontend/src/utils/http.ts`)
    - 请求拦截器：自动附加 Authorization: Bearer <token>
    - 响应拦截器：401 → 尝试 refresh → 失败跳转 /login
    - 错误处理：提取 message 字段展示 ElMessage
    - _需求: 5.4_

  - [x] 9.7 创建基础布局 (`frontend/src/layouts/DefaultLayout.vue`)
    - 侧边栏导航（项目列表等菜单项）
    - 顶部 header（显示当前用户名 + 登出按钮）
    - 主内容区域 (router-view)
    - 使用 gt- 前缀 CSS 类和 GT 品牌色
    - _需求: 5.6_

  - [x] 9.8 创建页面组件
    - Login.vue：登录表单（用户名/密码），调用 POST /api/auth/login，存储 JWT token
    - Dashboard.vue：首页仪表盘占位页
    - Projects.vue：项目列表占位页
    - NotFound.vue：404 页面
    - 验证首次加载在本地网络环境下 2 秒内渲染初始视图
    - _需求: 5.2, 5.11, 5.12_

  - [x]* 9.9 编写属性测试：HTTP 客户端令牌自动附加
    - **Property 16: 前端 HTTP 客户端令牌自动附加**
    - 使用 fast-check fc.string() 生成 token，验证请求头包含 Authorization: Bearer <token>
    - **验证: 需求 5.4**

  - [x]* 9.10 编写属性测试：路由守卫认证检查
    - **Property 17: 前端路由守卫认证检查**
    - 使用 fast-check fc.constantFrom(routes) 遍历需认证路由，验证未登录时重定向到 /login
    - **验证: 需求 5.5**

  - [x]* 9.11 编写属性测试：CSS 类名 gt- 前缀规范
    - **Property 18: CSS 类名 gt- 前缀规范**
    - 静态分析项目自定义 CSS 文件，验证所有自定义类名使用 gt- 前缀
    - **验证: 需求 5.8**

- [x] 10. ONLYOFFICE 集成 POC
  - [x] 10.1 创建 WOPI Host 服务 (`backend/app/services/wopi_service.py`)
    - check_file_info(file_id): 返回文件元信息（BaseFileName, Size, UserCanWrite 等）
    - get_file(file_id): 读取文件二进制内容并返回
    - put_file(file_id, content): 保存文件内容到 storage 目录
    - 文件存储路径：{STORAGE_ROOT}/poc/
    - _需求: 6.2_

  - [x] 10.2 创建 WOPI 路由 (`backend/app/api/wopi.py`)
    - GET /wopi/files/{file_id} — CheckFileInfo
    - GET /wopi/files/{file_id}/contents — GetFile
    - POST /wopi/files/{file_id}/contents — PutFile
    - _需求: 6.2_

  - [x] 10.3 创建 ONLYOFFICE 自定义函数 (`onlyoffice/custom-functions/tb-function.js`)
    - 注册 TB(account_code, column_name) 自定义函数
    - 使用 AddCustomFunction API
    - 函数内部发起异步 HTTP 请求到后端 API 获取数据
    - _需求: 6.5_

  - [x] 10.4 创建 ONLYOFFICE 示例插件 (`onlyoffice/plugins/audit-sidebar/`)
    - 创建 config.json 插件配置
    - 创建 index.html 侧边栏面板（显示静态审计信息内容）
    - 创建 index.js 插件逻辑
    - 验证插件加载机制
    - _需求: 6.6_

  - [x] 10.5 创建 POC 前端页面
    - 在前端添加 POC 测试页面，嵌入 ONLYOFFICE 编辑器 iframe
    - 配置 WOPI 协议连接参数
    - 准备测试用 .xlsx 文件放入 storage/poc/
    - _需求: 6.3, 6.4_

  - [x]* 10.6 编写属性测试：WOPI 文件读写往返
    - **Property 19: WOPI 文件读写往返**
    - 使用 Hypothesis st.binary(min_size=1) 生成文件内容，PutFile 后 GetFile 验证字节级一致
    - **验证: 需求 6.2**

- [x] 11. 检查点 — ONLYOFFICE POC 验证
  - 启动 Docker Compose 环境，验证 ONLYOFFICE Document Server 正常启动
  - 通过 POC 页面打开 .xlsx 文件，验证 WOPI 协议对接
  - 测试自定义函数 TB() 的异步 API 调用
  - 测试侧边栏插件加载
  - 记录技术发现到 POC 文档
  - 确保所有测试通过，如有问题请向用户确认
  - _需求: 6.7, 6.8_

- [x] 12. 测试与集成验证
  - [x] 12.1 配置后端测试环境
    - 创建 `backend/tests/conftest.py`：pytest-asyncio 配置、测试数据库 session（事务回滚隔离）、fakeredis 或独立 Redis 实例、httpx.AsyncClient fixture
    - 创建 `backend/pytest.ini`：asyncio_mode=auto
    - _需求: 2.8_

  - [x]* 12.2 编写迁移往返属性测试
    - **Property 1: 数据库迁移升降级往返**
    - 验证 upgrade 后 downgrade 数据库 Schema 回退到升级前状态
    - **验证: 需求 2.8, 2.9**

  - [x]* 12.3 编写单元测试：JWT 编解码
    - 正常编解码、过期令牌、篡改令牌、空 payload
    - _需求: 3.1_

  - [x]* 12.4 编写单元测试：登录锁定机制
    - 第4次失败（未锁定）、第5次失败（锁定）、锁定后30分钟解锁
    - _需求: 3.4_

  - [x]* 12.5 编写单元测试：统一响应包装
    - 各种数据类型的包装：dict、list、None、嵌套对象
    - _需求: 4.1_

  - [x]* 12.6 编写单元测试：IP 地址提取
    - 单个 IP、多级代理链、无 X-Forwarded-For
    - _需求: 4.6_

  - [x]* 12.7 编写集成测试：完整登录流程
    - 创建用户 → 登录 → 获取 token → 访问受保护端点 → 刷新 token → 登出 → 验证 token 失效
    - _需求: 3.1, 3.2, 3.11, 3.12, 3.13_

  - [x]* 12.8 编写集成测试：权限矩阵验证
    - 6种角色 × 关键端点的访问控制矩阵
    - _需求: 3.7, 3.8, 3.9, 3.10_

  - [x]* 12.9 编写集成测试：操作日志链路
    - 创建用户 → 验证 logs 表记录 → 检查 old_value/new_value
    - _需求: 4.5, 4.12_

  - [x]* 12.10 配置前端测试环境
    - 安装 vitest, @vue/test-utils, fast-check
    - 配置 vitest.config.ts
    - _需求: 5.1_

- [x] 13. 最终检查点 — 全量验证
  - 运行全部后端测试 `pytest backend/tests/ -v`
  - 运行全部前端测试 `cd frontend && npx vitest --run`
  - 启动 Docker Compose 验证所有服务正常启动和通信
  - 确保所有测试通过，如有问题请向用户确认

## 备注

- 标记 `*` 的子任务为可选测试任务，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求编号，确保需求可追溯
- 检查点任务用于阶段性验证，确保增量开发的正确性
- 属性测试验证设计文档中的正确性属性（Property 1-19）
- 单元测试和集成测试覆盖具体示例和边界条件
- ONLYOFFICE POC 的技术发现文档（需求 6.7, 6.8）在检查点 11 中完成
