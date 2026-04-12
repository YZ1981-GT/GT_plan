# 技术设计文档：第零阶段 — 技术基础设施

## 概述

本设计文档描述审计作业平台第零阶段的技术架构与实现方案。第零阶段为整个审计作业平台奠定技术地基，涵盖6个核心模块：

1. **Docker Compose 开发环境** — 一键启动 PostgreSQL 16 + Redis + FastAPI + ONLYOFFICE Document Server
2. **数据库 Schema 与迁移框架** — 5张核心表 + Alembic 版本化迁移
3. **用户认证与权限框架** — JWT 认证 + 6角色 RBAC + 项目级权限
4. **统一 API 规范与中间件** — 标准化响应格式 + 全局错误处理 + 操作日志自动记录
5. **前端项目骨架** — Vue 3 + TypeScript + Pinia + Element Plus + GT 品牌视觉 Token
6. **ONLYOFFICE 集成 POC** — WOPI 协议对接 + 自定义函数 + 插件开发验证

技术栈：Python FastAPI + PostgreSQL 16 + Redis + Vue 3 + TypeScript + Element Plus + ONLYOFFICE Document Server

## 架构

### 系统架构总览

```mermaid
graph TB
    subgraph Docker Compose
        subgraph Frontend["前端容器（开发时独立运行）"]
            VUE[Vue 3 + Vite Dev Server<br/>:5173]
        end

        subgraph Backend["后端容器"]
            FASTAPI[FastAPI<br/>:8000]
            subgraph Middleware["中间件层"]
                AUTH_MW[JWT 认证中间件]
                CORS_MW[CORS 中间件]
                LOG_MW[操作日志中间件]
                ERR_MW[全局错误处理]
                RESP_MW[统一响应包装]
            end
            subgraph Services["服务层"]
                AUTH_SVC[认证服务]
                PERM_SVC[权限服务]
                WOPI_SVC[WOPI Host]
                HEALTH_SVC[健康检查]
            end
        end

        subgraph DataLayer["数据层"]
            PG[(PostgreSQL 16<br/>:5432)]
            REDIS[(Redis<br/>:6379)]
        end

        subgraph DocServer["文档服务"]
            ONLYOFFICE[ONLYOFFICE<br/>Document Server<br/>:8080]
        end
    end

    VUE -->|REST API /api/*| FASTAPI
    VUE -->|iframe WOPI| ONLYOFFICE
    ONLYOFFICE -->|WOPI Protocol /wopi/*| FASTAPI
    FASTAPI --> PG
    FASTAPI --> REDIS
    AUTH_SVC --> REDIS
```

### 服务编排与依赖关系

```mermaid
graph LR
    PG[PostgreSQL 16] -->|healthcheck| REDIS[Redis]
    REDIS -->|healthcheck| BACKEND[FastAPI Backend]
    BACKEND -->|healthcheck| ONLYOFFICE[ONLYOFFICE DS]

    style PG fill:#336791,color:#fff
    style REDIS fill:#DC382D,color:#fff
    style BACKEND fill:#009688,color:#fff
    style ONLYOFFICE fill:#FF6F00,color:#fff
```

启动顺序：PostgreSQL → Redis → FastAPI Backend → ONLYOFFICE Document Server

### 请求处理流程

```mermaid
sequenceDiagram
    participant C as 前端
    participant M as 中间件链
    participant R as 路由处理器
    participant DB as PostgreSQL
    participant RD as Redis

    C->>M: HTTP Request
    M->>M: CORS 检查
    M->>M: JWT 令牌验证
    M->>RD: 检查令牌黑名单
    M->>M: 角色/权限校验
    M->>R: 转发请求
    R->>DB: 业务操作
    R-->>M: 返回结果
    M->>M: 统一响应包装
    M->>DB: 写操作日志（异步）
    M-->>C: {"code": 200, "message": "success", "data": ...}
```


## 组件与接口

### 1. Docker Compose 服务编排

**文件结构：**
```
project-root/
├── docker-compose.yml
├── .env
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── core/
│   │   │   ├── config.py        # Settings (pydantic-settings)
│   │   │   ├── database.py      # SQLAlchemy async engine + session
│   │   │   ├── redis.py         # Redis 连接池
│   │   │   └── security.py      # JWT 编解码、密码哈希
│   │   ├── middleware/
│   │   │   ├── response.py      # 统一响应包装
│   │   │   ├── error_handler.py # 全局异常处理
│   │   │   └── audit_log.py     # 操作日志中间件
│   │   ├── models/
│   │   │   └── base.py          # SQLAlchemy 声明式基类 + 5张核心表
│   │   ├── schemas/
│   │   │   ├── auth.py          # 认证相关 Pydantic 模型
│   │   │   ├── user.py          # 用户 CRUD 模型
│   │   │   └── common.py        # 统一响应模型
│   │   ├── api/
│   │   │   ├── auth.py          # /api/auth/* 路由
│   │   │   ├── users.py         # /api/users/* 路由
│   │   │   ├── health.py        # /api/health 路由
│   │   │   └── wopi.py          # /wopi/files/* 路由
│   │   ├── services/
│   │   │   ├── auth_service.py  # 认证业务逻辑
│   │   │   └── wopi_service.py  # WOPI 文件操作
│   │   └── deps.py              # 依赖注入（get_current_user, require_role, require_project_access）
│   ├── alembic/
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_init_core_tables.py
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/index.ts
│   │   ├── stores/auth.ts       # useAuthStore
│   │   ├── utils/http.ts        # Axios 封装
│   │   ├── styles/
│   │   │   ├── gt-tokens.css    # GT 品牌 CSS 变量
│   │   │   └── global.css       # 全局样式
│   │   ├── layouts/
│   │   │   └── DefaultLayout.vue
│   │   └── views/
│   │       ├── Login.vue
│   │       ├── Dashboard.vue
│   │       ├── Projects.vue
│   │       └── NotFound.vue
│   └── index.html
├── onlyoffice/                   # POC 相关
│   ├── plugins/
│   │   └── audit-sidebar/       # 示例插件
│   └── custom-functions/
│       └── tb-function.js       # TB() 自定义函数
└── storage/                      # 文件存储根目录
    └── poc/                      # POC 测试文件
```

**docker-compose.yml 服务定义：**

| 服务名 | 镜像 | 端口 | 依赖 | 数据卷 | 健康检查 |
|--------|------|------|------|--------|----------|
| `postgres` | `postgres:16-alpine` | `${PG_PORT:-5432}:5432` | 无 | `pg_data:/var/lib/postgresql/data` | `pg_isready -U ${PG_USER}` |
| `redis` | `redis:7-alpine` | `${REDIS_PORT:-6379}:6379` | 无 | `redis_data:/data` | `redis-cli ping` |
| `backend` | 本地构建 `./backend` | `${API_PORT:-8000}:8000` | postgres, redis | `./storage:/app/storage` | `curl -f http://localhost:8000/api/health` |
| `onlyoffice` | `onlyoffice/documentserver:8.2` | `${OFFICE_PORT:-8080}:80` | backend | `office_data:/var/lib/onlyoffice` | `curl -f http://localhost/healthcheck` |

### 2. 后端核心模块

#### 2.1 配置管理 (`core/config.py`)

使用 `pydantic-settings` 从环境变量加载配置：

```python
class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform"
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    # JWT
    JWT_SECRET_KEY: str  # 必填，无默认值
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    # 登录安全
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCK_MINUTES: int = 30
    # ONLYOFFICE
    ONLYOFFICE_URL: str = "http://onlyoffice:80"
    WOPI_BASE_URL: str = "http://backend:8000/wopi"
    # 文件存储
    STORAGE_ROOT: str = "./storage"

    model_config = SettingsConfigDict(env_file=".env")
```

#### 2.2 数据库连接 (`core/database.py`)

```python
# 异步引擎 + 会话工厂
engine = create_async_engine(settings.DATABASE_URL, pool_size=10, max_overflow=20)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
```

#### 2.3 认证服务接口

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/api/auth/login` | POST | 用户登录，返回 access_token + refresh_token | 无 |
| `/api/auth/refresh` | POST | 刷新 access_token | refresh_token |
| `/api/auth/logout` | POST | 登出，使 refresh_token 失效 | access_token |
| `/api/users` | POST | 创建用户（仅管理员） | admin |
| `/api/users/me` | GET | 获取当前用户信息 | 任意已认证 |
| `/api/health` | GET | 健康检查 | 无 |

#### 2.4 权限依赖注入

```python
# 角色校验
def require_role(allowed_roles: list[str]) -> Callable:
    async def dependency(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return current_user
    return Depends(dependency)

# 项目级权限校验
def require_project_access(min_permission: str = "readonly") -> Callable:
    async def dependency(
        project_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ):
        # admin 角色跳过项目权限检查
        if current_user.role == "admin":
            return current_user
        # 查询 project_users 表
        perm = await db.execute(
            select(ProjectUser).where(
                ProjectUser.project_id == project_id,
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False
            )
        )
        # 校验 permission_level 层级: edit > review > readonly
        ...
    return Depends(dependency)
```

#### 2.5 WOPI Host 接口（POC）

| 端点 | 方法 | WOPI 操作 | 描述 |
|------|------|-----------|------|
| `/wopi/files/{file_id}` | GET | CheckFileInfo | 返回文件元信息（名称、大小、权限等） |
| `/wopi/files/{file_id}/contents` | GET | GetFile | 返回文件二进制内容 |
| `/wopi/files/{file_id}/contents` | POST | PutFile | 保存文件内容 |

#### 2.6 中间件链

执行顺序（从外到内）：
1. **CORS 中间件** — 处理跨域请求
2. **全局异常处理** — 捕获未处理异常，返回 500
3. **统一响应包装** — 将路由返回值包装为标准格式
4. **操作日志中间件** — 对写操作（POST/PUT/PATCH/DELETE）自动记录日志

### 3. 前端核心模块

#### 3.1 路由配置

| 路径 | 组件 | 守卫 | 描述 |
|------|------|------|------|
| `/login` | `Login.vue` | 无（已登录则跳转 `/`） | 登录页 |
| `/` | `Dashboard.vue` | `requireAuth` | 首页仪表盘 |
| `/projects` | `Projects.vue` | `requireAuth` | 项目列表 |
| `/:pathMatch(.*)*` | `NotFound.vue` | 无 | 404 页面 |

#### 3.2 状态管理 (`useAuthStore`)

```typescript
interface AuthState {
  token: string | null
  refreshToken: string | null
  user: UserProfile | null
}

// Actions: login(), logout(), refreshToken(), fetchUserProfile()
```

#### 3.3 HTTP 客户端 (`utils/http.ts`)

- 请求拦截器：自动附加 `Authorization: Bearer <token>`
- 响应拦截器：
  - 401 → 尝试 refresh token，失败则跳转 `/login`
  - 其他错误 → 提取 `message` 字段展示 ElMessage

#### 3.4 GT 品牌视觉 Token 系统

```css
:root {
  /* 品牌色 */
  --gt-color-primary: #4b2d77;
  --gt-color-primary-light: #A06DFF;
  --gt-color-primary-dark: #2B1D4D;
  --gt-color-teal: #0094B3;
  --gt-color-coral: #FF5149;
  --gt-color-wheat: #FFC23D;
  --gt-color-success: #28A745;

  /* 间距（4px 网格） */
  --gt-space-1: 4px;
  --gt-space-2: 8px;
  --gt-space-3: 12px;
  --gt-space-4: 16px;
  --gt-space-6: 24px;
  --gt-space-8: 32px;

  /* 圆角 */
  --gt-radius-sm: 4px;
  --gt-radius-md: 8px;
  --gt-radius-lg: 12px;

  /* 字体 */
  --gt-font-family-zh: 'FZYueHei', 'Microsoft YaHei', 'PingFang SC', sans-serif;
  --gt-font-family-en: 'GT Walsheim', 'Helvetica Neue', Arial, sans-serif;
  --gt-font-size-base: 16px;
  --gt-line-height-base: 1.6;

  /* 阴影（GT 紫色调） */
  --gt-shadow-sm: 0 1px 3px rgba(75, 45, 119, 0.075);
  --gt-shadow-md: 0 4px 12px rgba(75, 45, 119, 0.15);
  --gt-shadow-lg: 0 8px 24px rgba(75, 45, 119, 0.175);
}
```


## 数据模型

### ER 图

```mermaid
erDiagram
    users ||--o{ projects : "manages (manager_id)"
    users ||--o{ projects : "partners (partner_id)"
    users ||--o{ project_users : "assigned to"
    projects ||--o{ project_users : "has members"
    users ||--o{ logs : "performs"
    users ||--o{ notifications : "receives"

    users {
        uuid id PK
        varchar username UK "NOT NULL"
        varchar email UK "NOT NULL"
        varchar hashed_password "NOT NULL"
        enum role "admin/partner/manager/auditor/qc/readonly"
        varchar office_code
        boolean is_active "DEFAULT true"
        boolean is_deleted "DEFAULT false"
        timestamp deleted_at
        timestamp created_at
        timestamp updated_at
        uuid created_by FK
        uuid updated_by FK
    }

    projects {
        uuid id PK
        varchar name "NOT NULL"
        varchar client_name "NOT NULL"
        date audit_period_start
        date audit_period_end
        enum project_type "annual/special/ipo/internal_control"
        numeric materiality_level
        enum status "created/planning/execution/completion/reporting/archived"
        uuid manager_id FK
        uuid partner_id FK
        boolean is_deleted "DEFAULT false"
        timestamp deleted_at
        timestamp created_at
        timestamp updated_at
        uuid created_by FK
        uuid updated_by FK
        integer version "DEFAULT 1"
    }

    project_users {
        uuid id PK
        uuid project_id FK "NOT NULL"
        uuid user_id FK "NOT NULL"
        enum role "partner/manager/auditor/qc/readonly"
        enum permission_level "edit/review/readonly"
        text scope_cycles
        text scope_accounts
        date valid_from
        date valid_to
        boolean is_deleted "DEFAULT false"
        timestamp created_at
        timestamp updated_at
    }

    logs {
        uuid id PK
        uuid user_id FK
        varchar action_type "NOT NULL"
        varchar object_type "NOT NULL"
        uuid object_id
        jsonb old_value
        jsonb new_value
        varchar ip_address
        timestamp created_at "NOT NULL"
    }

    notifications {
        uuid id PK
        uuid recipient_id FK "NOT NULL"
        varchar message_type "NOT NULL"
        varchar title "NOT NULL"
        text content
        varchar related_object_type
        uuid related_object_id
        boolean is_read "DEFAULT false"
        timestamp created_at "NOT NULL"
    }
```

### DDL 设计要点

**枚举类型定义：**
```sql
CREATE TYPE user_role AS ENUM ('admin', 'partner', 'manager', 'auditor', 'qc', 'readonly');
CREATE TYPE project_type AS ENUM ('annual', 'special', 'ipo', 'internal_control');
CREATE TYPE project_status AS ENUM ('created', 'planning', 'execution', 'completion', 'reporting', 'archived');
CREATE TYPE project_user_role AS ENUM ('partner', 'manager', 'auditor', 'qc', 'readonly');
CREATE TYPE permission_level AS ENUM ('edit', 'review', 'readonly');
```

**索引策略：**
```sql
-- 复合索引
CREATE UNIQUE INDEX idx_project_users_project_user ON project_users(project_id, user_id) WHERE is_deleted = false;
CREATE INDEX idx_logs_object ON logs(object_type, object_id);
CREATE INDEX idx_logs_user_time ON logs(user_id, created_at DESC);
CREATE INDEX idx_notifications_recipient_read ON notifications(recipient_id, is_read);

-- 软删除过滤索引
CREATE INDEX idx_users_active ON users(is_active) WHERE is_deleted = false;
CREATE INDEX idx_projects_status ON projects(status) WHERE is_deleted = false;
```

**软删除约定：**
- 所有业务表包含 `is_deleted` (boolean, default false) 和 `deleted_at` (timestamp, nullable)
- 查询时默认过滤 `WHERE is_deleted = false`
- SQLAlchemy 基类中通过 mixin 统一实现

**SQLAlchemy 模型基类：**
```python
class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

class AuditMixin:
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
```

### JWT 认证流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant F as 前端
    participant B as 后端
    participant R as Redis

    U->>F: 输入用户名/密码
    F->>B: POST /api/auth/login
    B->>B: 验证密码 (bcrypt)
    B->>R: 检查登录失败次数
    alt 失败次数 >= 5
        B-->>F: 423 账号已锁定
    else 密码错误
        B->>R: INCR 失败次数 (TTL 30min)
        B-->>F: 401 用户名或密码错误
    else 密码正确
        B->>R: DEL 失败次数
        B->>B: 生成 access_token (2h) + refresh_token (7d)
        B->>R: 存储 refresh_token
        B-->>F: {access_token, refresh_token, user}
    end
    F->>F: 存储 token 到 localStorage

    Note over F,B: 后续请求
    F->>B: 请求 + Authorization: Bearer <access_token>
    B->>B: 验证 JWT 签名和过期时间
    alt token 过期
        F->>B: POST /api/auth/refresh + refresh_token
        B->>R: 验证 refresh_token 有效性
        B-->>F: 新 access_token
    end
```

### 角色权限矩阵

| 功能 | admin | partner | manager | auditor | qc | readonly |
|------|:-----:|:-------:|:-------:|:-------:|:--:|:--------:|
| 用户管理（CRUD） | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 创建项目 | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| 查看项目列表 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 编辑项目信息 | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| 分配项目成员 | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| 编辑底稿 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| 复核底稿 | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| 查看底稿 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 系统配置 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

**项目级权限层级：** `edit` > `review` > `readonly`
- `edit`：可编辑项目内所有可写资源
- `review`：可查看 + 添加复核意见
- `readonly`：仅查看

### 操作日志中间件设计

```mermaid
flowchart TD
    A[收到写请求 POST/PUT/PATCH/DELETE] --> B{是否需要记录?}
    B -->|跳过: /api/auth/login, /api/health| Z[直接执行]
    B -->|需要记录| C[提取请求信息]
    C --> D[读取对象当前状态 → old_value]
    D --> E[执行业务逻辑]
    E --> F[读取操作结果 → new_value]
    F --> G[异步写入 logs 表]
    G --> H[返回响应]

    style G fill:#FFC23D,color:#000
```

**日志记录字段映射：**
- `user_id` — 从 JWT 令牌中提取
- `action_type` — HTTP 方法映射：POST→create, PUT/PATCH→update, DELETE→delete
- `object_type` — 从路由路径提取（如 `/api/users` → `user`）
- `object_id` — 从路径参数或响应体提取
- `ip_address` — 优先 `X-Forwarded-For`，回退 `request.client.host`
- `old_value` / `new_value` — JSON 序列化的对象快照


## 正确性属性

*属性（Property）是指在系统所有合法执行路径中都应成立的特征或行为——本质上是对系统应做什么的形式化陈述。属性是人类可读规格说明与机器可验证正确性保证之间的桥梁。*

### Property 1: 数据库迁移升降级往返

*For any* Alembic 迁移版本，执行 `upgrade` 后再执行 `downgrade`，数据库 Schema 应回退到升级前的状态（表结构、索引、约束一致）。

**Validates: Requirements 2.8, 2.9**

### Property 2: 软删除字段强制存在

*For any* 继承自业务基类的 SQLAlchemy 模型，该模型对应的数据库表必须包含 `is_deleted` (boolean, default false) 和 `deleted_at` (timestamp, nullable) 两个列。

**Validates: Requirements 2.10**

### Property 3: 有效凭据登录返回令牌

*For any* 已存在的活跃用户，使用正确的用户名和密码调用 `POST /api/auth/login`，响应中应同时包含 `access_token`（非空字符串）和 `refresh_token`（非空字符串），且 `access_token` 可被成功解码为包含该用户 ID 的 JWT。

**Validates: Requirements 3.1**

### Property 4: 令牌刷新生命周期

*For any* 已认证用户，当 access_token 过期后，使用有效的 refresh_token 调用 `POST /api/auth/refresh` 应返回一个新的有效 access_token，且新 token 中的用户 ID 与原 token 一致。

**Validates: Requirements 3.2**

### Property 5: 密码 bcrypt 安全存储

*For any* 通过系统创建的用户，其 `hashed_password` 字段的值必须是 bcrypt 格式（以 `$2b$` 开头），且 cost factor 不低于 12。

**Validates: Requirements 3.5**

### Property 6: 角色访问控制正确性

*For any* 用户角色和 API 端点的 `allowed_roles` 配置组合，当用户角色在 `allowed_roles` 列表中时请求应被允许（返回 2xx），当用户角色不在列表中时请求应被拒绝（返回 403），当请求未携带有效令牌时应返回 401。

**Validates: Requirements 3.7, 3.9, 3.10**

### Property 7: 项目级权限层级正确性

*For any* 用户、项目和最低权限要求的组合，`require_project_access` 应遵循 `edit > review > readonly` 的层级关系：当用户的实际权限级别大于等于要求的最低权限时允许访问，否则拒绝。admin 角色应跳过项目权限检查。

**Validates: Requirements 3.8**

### Property 8: 登出令牌失效

*For any* 已认证用户，调用 `POST /api/auth/logout` 后，使用同一 refresh_token 调用 `POST /api/auth/refresh` 应返回失败（401），证明 refresh_token 已被失效。

**Validates: Requirements 3.11**

### Property 9: 用户创建响应排除密码

*For any* 通过 `POST /api/users` 创建的用户，API 响应体中不应包含 `password`、`hashed_password` 或任何密码相关字段。

**Validates: Requirements 3.12**

### Property 10: 当前用户信息一致性

*For any* 已认证用户，调用 `GET /api/users/me` 返回的用户信息（id、username、email、role）应与该用户在数据库中的记录完全一致。

**Validates: Requirements 3.13**

### Property 11: API 响应格式一致性

*For any* API 请求，成功响应必须符合 `{"code": 200, "message": "success", "data": <payload>}` 格式，错误响应必须符合 `{"code": <http_status>, "message": <string>, "detail": <optional>}` 格式。

**Validates: Requirements 4.1, 4.2**

### Property 12: 异常处理隐藏内部信息

*For any* 导致服务端未捕获异常的请求，API 响应应返回 HTTP 500，响应体中的 `message` 为 "服务器内部错误"，且响应体中不包含 Python traceback、文件路径或内部变量名等敏感信息。

**Validates: Requirements 4.3**

### Property 13: Pydantic 校验返回 422

*For any* 不符合 Pydantic 模型约束的请求体，API 应返回 HTTP 422，且响应中包含具体的字段级错误信息（字段名和错误描述）。

**Validates: Requirements 4.4**

### Property 14: 写操作审计日志完整性

*For any* 写操作（POST/PUT/PATCH/DELETE）请求，`logs` 表中应新增一条记录，包含正确的 `user_id`、`action_type`、`object_type`、`object_id`、`ip_address` 和 `created_at`。对于更新和删除操作，`old_value` 应反映操作前的对象状态；对于创建和更新操作，`new_value` 应反映操作后的对象状态。IP 地址应优先从 `X-Forwarded-For` 头提取。

**Validates: Requirements 4.5, 4.6, 4.12**

### Property 15: 健康检查服务状态准确性

*For any* PostgreSQL 和 Redis 的可用性组合（均可用、仅 PG 不可用、仅 Redis 不可用、均不可用），`GET /api/health` 应在所有服务可用时返回 200，在任一服务不可用时返回 503，且响应体中准确标识哪个服务不可用。

**Validates: Requirements 4.8, 4.9**

### Property 16: 前端 HTTP 客户端令牌自动附加

*For any* 通过 Axios 封装发出的请求，当 authStore 中存在有效 token 时，请求头中应包含 `Authorization: Bearer <token>`；当收到 401 响应时，应自动尝试使用 refresh_token 刷新，刷新失败则跳转到 `/login`。

**Validates: Requirements 5.4**

### Property 17: 前端路由守卫认证检查

*For any* 需要认证的路由（`/`、`/projects` 等），当用户未登录（authStore 中无有效 token）时，导航应被拦截并重定向到 `/login`。

**Validates: Requirements 5.5**

### Property 18: CSS 类名 gt- 前缀规范

*For any* 项目自定义的 CSS 类名（排除第三方库），应使用 `gt-` 前缀命名。

**Validates: Requirements 5.8**

### Property 19: WOPI 文件读写往返

*For any* 有效的文件，通过 `POST /wopi/files/{file_id}/contents`（PutFile）写入内容后，通过 `GET /wopi/files/{file_id}/contents`（GetFile）读取的内容应与写入的内容完全一致（字节级相同）。

**Validates: Requirements 6.2**


## 错误处理

### 错误分类与处理策略

| 错误类型 | HTTP 状态码 | 处理方式 | 示例 |
|----------|:-----------:|----------|------|
| 认证失败 | 401 | 返回标准错误响应，前端跳转登录页 | 无效/过期 JWT、错误密码 |
| 权限不足 | 403 | 返回 "权限不足"，前端提示 | 审计员尝试创建用户 |
| 账号锁定 | 423 | 返回锁定信息和剩余时间 | 连续5次登录失败 |
| 请求校验失败 | 422 | 返回字段级错误详情 | Pydantic 模型校验不通过 |
| 资源不存在 | 404 | 返回 "资源不存在" | 查询不存在的用户/项目 |
| 服务不可用 | 503 | 健康检查返回不可用服务详情 | PostgreSQL/Redis 连接断开 |
| 服务器内部错误 | 500 | 记录完整堆栈到日志文件，返回通用错误消息 | 未捕获异常 |

### 全局异常处理器

```python
# 异常处理优先级（从高到低）
1. HTTPException          → 直接返回对应状态码和消息
2. RequestValidationError → 422 + 字段级错误详情
3. PermissionError        → 403 "权限不足"
4. Exception              → 500 "服务器内部错误" + 日志记录
```

### 前端错误处理

| 场景 | 处理方式 |
|------|----------|
| 401 响应 | 尝试 refresh token → 失败则清除 authStore 并跳转 `/login` |
| 403 响应 | ElMessage.error("权限不足") |
| 422 响应 | 表单字段级错误提示 |
| 500 响应 | ElMessage.error("服务器内部错误，请稍后重试") |
| 网络断开 | ElMessage.error("网络连接失败，请检查网络") |

### 操作日志错误隔离

操作日志中间件的写入操作采用异步执行，日志写入失败不应影响业务请求的正常返回。日志写入异常应记录到系统运行日志（文件日志），不向客户端暴露。

## 测试策略

### 测试分层

```
┌─────────────────────────────────────┐
│        E2E 测试（手动/Playwright）     │  ONLYOFFICE 集成、完整登录流程
├─────────────────────────────────────┤
│        集成测试（pytest + httpx）      │  API 端点、中间件链、数据库交互
├─────────────────────────────────────┤
│        属性测试（pytest + Hypothesis） │  正确性属性验证（100+ 迭代）
├─────────────────────────────────────┤
│        单元测试（pytest）              │  纯函数、工具函数、边界条件
└─────────────────────────────────────┘
```

### 属性测试（Property-Based Testing）

**测试库：** [Hypothesis](https://hypothesis.readthedocs.io/) (Python) + [fast-check](https://fast-check.dev/) (TypeScript/前端)

**配置要求：**
- 每个属性测试最少运行 100 次迭代（`@settings(max_examples=100)`）
- 每个属性测试必须通过注释引用设计文档中的属性编号
- 注释格式：`# Feature: phase0-infrastructure, Property {N}: {property_text}`

**后端属性测试清单：**

| 属性 | 测试文件 | 生成器策略 |
|------|----------|-----------|
| P1: 迁移往返 | `tests/test_migration_props.py` | 不适用（使用固定迁移脚本） |
| P2: 软删除字段 | `tests/test_model_props.py` | 遍历所有 SQLAlchemy 模型类 |
| P3: 登录返回令牌 | `tests/test_auth_props.py` | `st.text()` 生成用户名/密码 |
| P4: 令牌刷新 | `tests/test_auth_props.py` | 复用 P3 生成器 |
| P5: bcrypt 安全 | `tests/test_auth_props.py` | `st.text(min_size=1)` 生成密码 |
| P6: 角色访问控制 | `tests/test_permission_props.py` | `st.sampled_from(roles)` × `st.lists(st.sampled_from(roles))` |
| P7: 项目权限层级 | `tests/test_permission_props.py` | `st.sampled_from(permission_levels)` 组合 |
| P8: 登出令牌失效 | `tests/test_auth_props.py` | 复用 P3 生成器 |
| P9: 创建用户排除密码 | `tests/test_auth_props.py` | `st.fixed_dictionaries()` 生成用户数据 |
| P10: 用户信息一致性 | `tests/test_auth_props.py` | 复用 P3 生成器 |
| P11: 响应格式一致性 | `tests/test_middleware_props.py` | `st.sampled_from(endpoints)` |
| P12: 异常隐藏内部信息 | `tests/test_middleware_props.py` | `st.sampled_from(exception_types)` |
| P13: Pydantic 422 | `tests/test_middleware_props.py` | `st.dictionaries()` 生成随机请求体 |
| P14: 审计日志完整性 | `tests/test_audit_log_props.py` | `st.sampled_from(write_endpoints)` × `st.text()` 生成 IP |
| P15: 健康检查状态 | `tests/test_health_props.py` | `st.booleans()` × 2（PG/Redis 可用性） |
| P19: WOPI 文件往返 | `tests/test_wopi_props.py` | `st.binary(min_size=1)` 生成文件内容 |

**前端属性测试清单：**

| 属性 | 测试文件 | 生成器策略 |
|------|----------|-----------|
| P16: HTTP 令牌附加 | `tests/http.spec.ts` | `fc.string()` 生成 token |
| P17: 路由守卫 | `tests/router.spec.ts` | `fc.constantFrom(routes)` |
| P18: CSS gt- 前缀 | `tests/css.spec.ts` | 静态分析 CSS 文件 |

### 单元测试

单元测试聚焦于具体示例和边界条件：

| 测试范围 | 关键用例 |
|----------|----------|
| JWT 编解码 | 正常编解码、过期令牌、篡改令牌、空 payload |
| 密码哈希 | 正确验证、错误密码、空密码 |
| 登录锁定 | 第4次失败（未锁定）、第5次失败（锁定）、锁定后30分钟解锁 |
| 统一响应 | 各种数据类型的包装（dict、list、None、嵌套对象） |
| IP 提取 | 单个 IP、多级代理链、无 X-Forwarded-For |
| 健康检查 | 全部正常、PG 断开、Redis 断开、全部断开 |
| WOPI CheckFileInfo | 文件存在、文件不存在、权限校验 |
| 前端路由 | 已登录访问 /login 跳转首页、未登录访问 / 跳转登录 |
| Pinia Store | login/logout action、token 持久化到 localStorage |

### 集成测试

使用 `pytest` + `httpx.AsyncClient` + 测试数据库（独立 PostgreSQL schema 或 SQLite）：

| 测试场景 | 描述 |
|----------|------|
| 完整登录流程 | 创建用户 → 登录 → 获取 token → 访问受保护端点 → 刷新 token → 登出 |
| 权限矩阵验证 | 6种角色 × 关键端点的访问控制矩阵 |
| 操作日志链路 | 创建用户 → 验证 logs 表记录 → 检查 old_value/new_value |
| 数据库迁移 | upgrade head → 验证表结构 → downgrade → 验证回退 |
| WOPI 文件操作 | PutFile → GetFile → 验证内容一致 |

### 测试环境配置

- 后端测试使用 `pytest-asyncio` 支持异步测试
- 数据库测试使用事务回滚隔离（每个测试用例在独立事务中运行，测试结束后回滚）
- Redis 测试使用 `fakeredis` 或独立 Redis 实例（database 15）
- 前端测试使用 `Vitest` + `@vue/test-utils` + `fast-check`
- CI 中属性测试配置 `max_examples=200`，本地开发 `max_examples=100`

