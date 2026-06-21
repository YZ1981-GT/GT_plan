# Requirements Document

## Introduction

底稿模块已上线 OnlyOffice WOPI 集成（spec `d0-onlyoffice-migration`），以纯 iframe DocEditor 嵌入渲染非白名单多 sheet 底稿，降级到只读网格。本 spec 在不改变"白名单 HTML / 非白名单 OnlyOffice / 降级只读网格"三层架构的前提下，修复 7 个经代码复核确认的缺陷（4 个 P0 + 3 个复核新增）、落地 4 项工程优化、并新增 OnlyOffice Plugin SDK 方向（审计标识标注插件 + 取数联动插件）。

核心目标是在 6000 人并发场景下消除并发崩溃风险（席位限制器当前为死代码、per-sheet 整本复制、容器无约束拉起）与越权下载底稿文件的安全风险（WOPI 端点零鉴权），同时不影响共享同一容器的交付模块。

本需求文档从已批准的设计文档派生，覆盖设计中的全部缺陷修复、工程优化、插件方向与 8 条正确性性质。

## Glossary

- **Config_Endpoint**: 后端 `GET .../onlyoffice-config` 端点，负责席位获取、doc_key 生成、JWT 签发与配置返回。
- **WOPI_Endpoint**: 后端 `GET .../wopi/contents` 端点，OnlyOffice 容器据此下载 xlsx 文件内容。
- **Callback_Endpoint**: 后端 `POST .../onlyoffice-callback` 端点，接收 OnlyOffice 状态回调，执行写回与席位释放。
- **Health_Endpoint**: 后端 `GET .../onlyoffice/health` 端点，提供 OnlyOffice 健康预检。
- **Session_Limiter**: `onlyoffice_session_limiter` 服务，基于 Redis 原子操作管理编辑席位（`acquire_session` / `release_session` / `get_active_count`）。
- **Session_Seat**: 一次编辑会话占用的席位资源，键为 `user_id + doc_key`。
- **MAX_SESSIONS**: 活跃编辑席位上限，由环境变量 `ONLYOFFICE_MAX_SESSIONS` 配置。
- **Doc_Key**: OnlyOffice 协议要求的文档版本唯一标识，由 `hash(wp_code + file_mtime_ns)` 生成。
- **WP_File**: 按 `wp_code` 命名的单一共享 xlsx 文件（`{wp_code}.xlsx`）。
- **Soft_Delete_Guard**: 三端点统一的软删守卫，校验 `WorkingPaper.is_deleted` 与 `projects.is_deleted`。
- **Frontend_Editor**: 前端 `GtOnlyOfficeSheet.vue` 组件，承载 DocEditor iframe 与降级逻辑。
- **Grid_Fallback**: 降级目标 `GtGridSheet` 只读网格组件。
- **DocEditor**: OnlyOffice 前端 JS API 实例（`DocsAPI.DocEditor`）。
- **JWT_Secret**: OnlyOffice JWT 签名密钥，取值 `onlyoffice-dev-2026`，须在 `config.py`、`docker-compose`、`local.json` 三处一致。
- **Audit_Legend_Plugin**: 审计标识/勾稽标注插件（`audit-legend`），在单元格叠加审计符号。
- **TB_Fetch_Plugin**: 取数联动插件（`tb-fetch`），从 TB 取数回填单元格。
- **Delivery_Module**: 与底稿共享同一 OnlyOffice 容器的交付模块（`onlyoffice_callback_service.py` 等）。

## Requirements

### Requirement 1: 编辑席位接入（P0-1）

**User Story:** As a 系统管理员, I want OnlyOffice 编辑会话在创建前占用席位, so that 在 6000 人并发目标下容器不会被无约束拉起而崩溃。

#### Acceptance Criteria

1. WHEN Frontend_Editor 以编辑模式请求 Config_Endpoint, THE Config_Endpoint SHALL 调用 Session_Limiter 的 `acquire_session(user_id, doc_key)` 获取 Session_Seat。
2. IF `acquire_session` 返回成功, THEN THE Config_Endpoint SHALL 返回 200 响应及包含配置与 JWT 的内容。
3. WHERE 请求模式为只读（view）, THE Config_Endpoint SHALL 不占用 Session_Seat。
4. WHEN 同一 `user_id + doc_key` 的会话再次请求 Config_Endpoint, THE Session_Limiter SHALL 以幂等续期方式刷新 Session_Seat 的 TTL 而不新增席位。

### Requirement 2: 编辑席位上限与拒绝（P0-1）

**User Story:** As a 系统管理员, I want 活跃席位达到上限时新会话被拒绝, so that 容器内存占用受控且系统不崩溃。

#### Acceptance Criteria

1. THE Session_Limiter SHALL 维持活跃 Session_Seat 数量不超过 MAX_SESSIONS。
2. IF 活跃 Session_Seat 数量已达到 MAX_SESSIONS 且新编辑会话请求 Config_Endpoint, THEN THE Config_Endpoint SHALL 返回 429 状态码及"当前编辑人数已满"提示。
3. WHEN Config_Endpoint 返回 429, THE Frontend_Editor SHALL 降级到 Grid_Fallback 并提示编辑人数已满。
4. THE MAX_SESSIONS SHALL 从环境变量 `ONLYOFFICE_MAX_SESSIONS` 读取，不写死在代码中。

### Requirement 3: 编辑席位释放（P0-2）

**User Story:** As a 系统管理员, I want 编辑会话结束时释放席位, so that 不产生占座的僵尸会话耗尽席位池。

#### Acceptance Criteria

1. WHEN Callback_Endpoint 收到 status=2 或 status=6（保存）回调且写回成功, THE Callback_Endpoint SHALL 调用 `release_session(user_id, doc_key)` 释放 Session_Seat。
2. WHEN Callback_Endpoint 收到 status=4（关闭无修改）回调, THE Callback_Endpoint SHALL 调用 `release_session(user_id, doc_key)` 释放 Session_Seat。
3. WHEN Callback_Endpoint 收到 status=3 或 status=7（保存出错关闭）回调, THE Callback_Endpoint SHALL 调用 `release_session(user_id, doc_key)` 释放 Session_Seat。
4. WHEN Callback_Endpoint 处理回调, THE Callback_Endpoint SHALL 从回调 body 的 `actions[].userid` 提取 user_id，并在缺失时回退到 `users[0]`。
5. WHEN Callback_Endpoint 处理回调, THE Callback_Endpoint SHALL 从回调 body 的 `key` 字段提取 doc_key。
6. IF Callback_Endpoint 无法从回调 body 提取有效 user_id 或 doc_key, THEN THE Callback_Endpoint SHALL 跳过席位释放并依赖 TTL 兜底，返回 `{"error": 0}`。

### Requirement 4: 单文件共享模型（P0-3）

**User Story:** As a 项目经理, I want 同一 wp_code 的多个 sheet 共享单一物理文件, so that 不再为每个 sheet 复制整本工作簿、节省存储并避免显示全部 tab。

#### Acceptance Criteria

1. WHEN 解析 wp_code 对应的 WP_File, THE Config_Endpoint SHALL 使用 `{wp_code}.xlsx` 命名而非 per-sheet 命名。
2. THE 项目存储目录 SHALL 对每个 wp_code 至多保留一个 `{wp_code}.xlsx` 文件。
3. WHEN WP_File 不存在且存在模板文件, THE Config_Endpoint SHALL 从模板整本复制一次生成 WP_File。
4. IF WP_File 不存在且无可用模板, THEN THE Config_Endpoint SHALL 返回 404 错误。
5. WHEN 构建 OnlyOffice 配置, THE Config_Endpoint SHALL 通过 `editorConfig.actionLink` 携带目标 sheet_name 以定位目标 sheet。

### Requirement 5: doc_key 一致性（P0-4）

**User Story:** As a 系统管理员, I want 同一文件的所有 sheet 共享同一 doc_key, so that OnlyOffice 协调编辑会话语义正确且文件变更可被感知。

#### Acceptance Criteria

1. WHEN 生成 Doc_Key, THE Config_Endpoint SHALL 计算 `hash(wp_code + file_mtime_ns)`，不包含 sheet_name。
2. WHEN 同一 wp_code 的不同 sheet 请求 Config_Endpoint 且文件未变更, THE Config_Endpoint SHALL 返回相同的 Doc_Key。
3. WHEN WP_File 的修改时间（mtime）变化, THE Config_Endpoint SHALL 生成不同的 Doc_Key。

### Requirement 6: WOPI 端点 JWT 鉴权（P-5）

**User Story:** As a 审计员, I want 底稿文件下载请求经过鉴权, so that 他人无法仅凭 wp_id 与 sheet_name 越权下载底稿文件。

#### Acceptance Criteria

1. WHEN WOPI_Endpoint 收到 GetFile 请求, THE WOPI_Endpoint SHALL 从 `Authorization` header 或 `token` 查询参数提取 JWT。
2. WHERE JWT_Secret 已配置, IF WOPI_Endpoint 请求缺少有效 JWT, THEN THE WOPI_Endpoint SHALL 返回 403 状态码且不返回文件内容。
3. WHERE JWT_Secret 已配置, IF WOPI_Endpoint 请求携带的 JWT 校验失败, THEN THE WOPI_Endpoint SHALL 返回 403 状态码且不返回文件内容。
4. WHERE JWT_Secret 未配置（测试环境）, THE WOPI_Endpoint SHALL 直通校验。
5. WHEN WOPI_Endpoint 通过 JWT 鉴权与软删守卫, THE WOPI_Endpoint SHALL 返回对应 WP_File 的 xlsx 内容。

### Requirement 7: 项目软删守卫（P-6）

**User Story:** As a 审计员, I want 已删除项目的底稿无法被打开或下载, so that 软删除的项目数据不会通过 OnlyOffice 端点泄露或被编辑。

#### Acceptance Criteria

1. WHEN Config_Endpoint、WOPI_Endpoint 或 Callback_Endpoint 查询底稿, THE 对应端点 SHALL 通过统一的 Soft_Delete_Guard 校验。
2. IF 底稿的 `WorkingPaper.is_deleted` 为真, THEN THE 对应端点 SHALL 返回 404 状态码及"底稿不存在"提示。
3. IF 底稿所属项目的 `projects.is_deleted` 为真, THEN THE 对应端点 SHALL 返回 404 状态码及"项目已删除"提示。

### Requirement 8: 前端 DocEditor 内部错误降级（P-7）

**User Story:** As a 审计员, I want OnlyOffice iframe 内部加载失败时自动降级到只读网格, so that 我永远看不到 OnlyOffice 的原始报错页。

#### Acceptance Criteria

1. WHEN 创建 DocEditor 实例, THE Frontend_Editor SHALL 注册 `events.onError` 回调。
2. WHEN DocEditor 触发 `onError` 事件（如 JWT 不匹配或文档加载失败）, THE Frontend_Editor SHALL 降级到 Grid_Fallback。
3. WHEN 创建 DocEditor 实例, THE Frontend_Editor SHALL 注册 `events.onWarning` 回调并记录告警。
4. WHEN DocEditor 触发 `onDocumentReady` 事件, THE Frontend_Editor SHALL 关闭加载状态。
5. WHILE 文档仍在 iframe 内加载, THE Frontend_Editor SHALL 保持加载状态直至 `onDocumentReady` 触发。

### Requirement 9: 健康预检降级链（工程优化 + R6 语义修正）

**User Story:** As a 审计员, I want 打开底稿前先主动检测 OnlyOffice 健康状态, so that 服务不可用时直接降级而不浪费时间加载 api.js。

#### Acceptance Criteria

1. THE Health_Endpoint SHALL 复用交付模块的 `health_check` 返回健康状态、活跃席位数与席位上限。
2. WHEN Frontend_Editor 挂载, THE Frontend_Editor SHALL 在加载 api.js 之前调用 Health_Endpoint 进行主动预检。
3. IF Health_Endpoint 返回不健康或超时, THEN THE Frontend_Editor SHALL 直接降级到 Grid_Fallback 且不加载 api.js。
4. WHEN api.js 脚本加载失败（onerror）, THE Frontend_Editor SHALL 降级到 Grid_Fallback。
5. THE Health_Endpoint SHALL 注册在 `/{wp_id}` 动态通配路由之前作为静态路径。

### Requirement 10: 只读模式 type:embedded（工程优化）

**User Story:** As a 审计员, I want 只读查看底稿时使用更轻量的嵌入式编辑器, so that 加载更快且无多余工具栏。

#### Acceptance Criteria

1. WHERE 请求为只读模式, THE Frontend_Editor SHALL 将 DocEditor 配置的 `type` 设为 `embedded` 且 `mode` 设为 `view`。
2. WHERE 请求为编辑模式, THE Frontend_Editor SHALL 将 DocEditor 配置的 `type` 设为 `desktop` 并保留公式与数据 Tab。

### Requirement 11: api.js preload（工程优化）

**User Story:** As a 审计员, I want 进入底稿列表时预热 OnlyOffice 脚本, so that 打开非白名单 sheet 时减少首次约 3 秒的加载等待。

#### Acceptance Criteria

1. WHEN 用户进入底稿列表页, THE 底稿列表页 SHALL 通过 `<link rel="preload" as="script">` 预热 api.js。
2. THE 底稿列表页 SHALL 仅执行 preload 而不初始化 DocsAPI 或创建 DocEditor。

### Requirement 12: 审计标识标注插件（增强亮点）

**User Story:** As a 审计员, I want 在 OnlyOffice 单元格叠加审计符号, so that 我能标注已核对（√）、已计算（ⓒ）、索引跳转（➜）等审计痕迹。

#### Acceptance Criteria

1. THE Audit_Legend_Plugin SHALL 提供符合 OnlyOffice Plugin SDK 规范的 `config.json` 清单。
2. THE Audit_Legend_Plugin SHALL 在 `config.json` 中通过 `EditorsSupport: ["cell"]` 限定仅电子表格编辑器可见。
3. WHEN 用户在选中单元格触发标注操作, THE Audit_Legend_Plugin SHALL 在单元格叠加对应审计符号（√ 已核对 / ⓒ 已计算 / ➜ 索引跳转）。

### Requirement 13: 取数联动插件（增强亮点）

**User Story:** As a 审计员, I want 在 OnlyOffice 中右键从 TB 取数, so that 底稿的联动取数能力延伸到 OnlyOffice 编辑场景。

#### Acceptance Criteria

1. THE TB_Fetch_Plugin SHALL 提供符合 OnlyOffice Plugin SDK 规范的 `config.json` 清单并注册 `onContextMenuClick` 事件。
2. WHEN 用户在选中单元格触发"从 TB 取数", THE TB_Fetch_Plugin SHALL 调用后端 `auto_data_resolvers` 取数并回填单元格。
3. WHEN TB_Fetch_Plugin 调用后端取数 API, THE TB_Fetch_Plugin SHALL 复用平台既有鉴权（携带 session/token）且不硬编码任何密钥。
4. WHEN TB_Fetch_Plugin 调用后端取数 API, THE 后端 SHALL 经现有项目权限校验。

### Requirement 14: 容器侧插件加载（增强亮点）

**User Story:** As a 系统管理员, I want 自定义插件以非侵入方式加载进共享容器, so that 插件可用且不影响交付模块的 Word 编辑器。

#### Acceptance Criteria

1. THE 容器配置 SHALL 将 `backend/onlyoffice_plugins/{plugin}` 挂载或复制到容器 `sdkjs-plugins/{plugin}` 目录。
2. THE 插件 `config.json` SHALL 通过 `EditorsSupport: ["cell"]` 限定可见范围，使 Delivery_Module 的 Word 编辑器不显示该插件。
3. THE 容器配置 SHALL 保持 JWT_Secret 三处一致（取值 `onlyoffice-dev-2026`）。

### Requirement 15: JWT secret 三处一致（铁律）

**User Story:** As a 系统管理员, I want config、callback、WOPI 三端点使用一致的 JWT 密钥, so that 签发与校验不会因密钥不一致而失败。

#### Acceptance Criteria

1. THE Config_Endpoint、Callback_Endpoint 与 WOPI_Endpoint SHALL 使用 `settings.ONLYOFFICE_JWT_SECRET` 作为 JWT 密钥。
2. THE `settings.ONLYOFFICE_JWT_SECRET` SHALL 与 `docker-compose` 及 `local.json` 中配置的密钥取值一致。

### Requirement 16: 交付模块零回归（铁律）

**User Story:** As a 系统管理员, I want 底稿模块的改动不影响共享容器的交付模块, so that 交付模块保持原有行为不被破坏。

#### Acceptance Criteria

1. THE 底稿模块改动 SHALL 不修改 `onlyoffice_callback_service.py` 的现有行为。
2. WHERE 插件已加载到共享容器, THE 插件 SHALL 仅对电子表格编辑会话可见，不影响 Delivery_Module 的 Word 编辑器。
3. WHEN 底稿改动完成, THE 系统 SHALL 通过 1101+ render-config 冒烟测试零回归。
4. WHEN 底稿改动完成, THE 改动 SHALL 经 Playwright 端到端实测验证。
