# 底稿模块健康度二期 — 需求文档

## 变更记录

| 版本 | 日期 | 摘要 | 触发 |
|------|------|------|------|
| v1.0 | 2026-06-20 | 初始版本：P1×5 + P2×4 共 9 项 | 第一轮策略拆分完成后遗留待办 |

## 背景

第一轮代码健康度治理（spec: `workpaper-render-config-refactor`）完成策略模式拆分，`wp_render_config.py` 从 1474→1156 行，`get_render_config` 从 475→119 行。但仍有 9 项 P1/P2 待办遗留：循环依赖隐患、重复代码、缺失测试、大文件膨胀等。本轮一次性收口。

## 现状量化

| 指标 | 当前值 | 目标 |
|------|--------|------|
| wp_render_config.py 行数 | 1156 | ≤800 |
| `_build_preparation_info` 位置 | router 文件（被策略反向 import） | service 层 |
| 策略 render(ctx) 单元测试 | 0 | ≥7（每策略 ≥1） |
| `_WP_CODE_OVERRIDE` 契约测试 | 0 | 1 条断言 |
| `_count_adjustments` 重复份数 | 2 | 1（共享 helper） |
| `_WP_CODE_OVERRIDE` 存储形式 | 源码内嵌 910 条 | 外置 JSON + 热重载 |
| auto_data_resolvers 有 docstring 比例 | ~20% | 100% |
| router_registry 启动校验 | 无 | assert 完整性 |
| wp_template_files.py 行数 | ~1160 | 预防性拆分后 ≤800 |

## 术语表

- **Router**：FastAPI 路由文件，定义 HTTP 端点
- **Service**：业务逻辑层，不直接处理 HTTP 请求/响应
- **Strategy（策略）**：`wp_render_strategies/` 下按 componentType 分发的渲染函数
- **RenderContext**：策略函数的统一上下文 dataclass
- **Resolver**：`auto_data_resolvers.py` 中注册的数据解析函数，按 resolver_name 分发
- **Router_Registry**：`backend/app/router_registry.py` 中注册所有 router 的集中配置
- **_WP_CODE_OVERRIDE**：910 条 wp_code→componentType 硬编码覆盖映射
- **prep_info**：底稿渲染前置准备信息（项目名称、年度、客户等）

## 需求

### Requirement 1: `_build_preparation_info` 下沉到 Service 层

**User Story:** 作为开发者，我希望 `_build_preparation_info` 从 router 文件迁入独立 service，以消除策略文件反向 import router 的循环依赖隐患。

#### Acceptance Criteria

1. WHEN 策略函数需要 prep_info 时, THE WpPreparationInfoService SHALL 提供 `build_preparation_info(db, project_id, wp_code)` 异步方法返回准备信息字典
2. THE wp_render_config.py SHALL 不再包含 `_build_preparation_info` 函数定义
3. WHEN `_b_index.py` 或 `_c_note.py` 策略需要 prep_info 时, THE Strategy SHALL 从 `services.wp_preparation_info_service` 导入而非从 router 导入
4. IF 迁移后任何已有 import 路径不存在, THEN THE System SHALL 在模块加载时立即报 ImportError（零静默失败）
5. THE wp_render_config.py SHALL 在迁移后总行数 ≤ 1050 行

### Requirement 2: 旧 Helper 迁出 Router

**User Story:** 作为开发者，我希望 `wp_render_config.py` 中残留的 ~350 行 helper 函数迁入策略文件或 service 层，使 router 文件降到 ≤800 行。

#### Acceptance Criteria

1. THE wp_render_config.py SHALL 不再包含 `_generate_b_index_data` 函数定义
2. THE wp_render_config.py SHALL 不再包含 `_generate_a_program_data` 函数定义
3. THE wp_render_config.py SHALL 不再包含 `_generate_grid_data` 函数定义
4. THE wp_render_config.py SHALL 不再包含 `_fetch_audit_sheet_tb_values` 函数定义
5. WHEN 上述 helper 迁移完成后, THE wp_render_config.py SHALL 总行数 ≤ 800 行
6. THE 1096 render-config 冒烟测试 SHALL 全部通过（零回归）

### Requirement 3: 策略单元测试

**User Story:** 作为开发者，我希望每个策略的 `render(ctx)` 有独立单元测试，以便在修改策略时快速验证正确性。

#### Acceptance Criteria

1. THE test_workpaper_render_strategies.py SHALL 为每个策略文件提供至少 1 个单元测试（共 ≥7 个）
2. WHEN 测试执行时, THE TestSuite SHALL mock RenderContext 的 db 会话和外部依赖，不依赖真实数据库
3. WHEN 策略函数接收有效 RenderContext 时, THE Strategy SHALL 返回包含预期键的字典或 None
4. WHEN 策略函数接收缺少必要数据的 RenderContext 时, THE Strategy SHALL 优雅返回 None 或空字典而非抛异常
5. THE 全部策略单元测试 SHALL 在 pytest 执行中通过

### Requirement 4: `_WP_CODE_OVERRIDE` 契约测试

**User Story:** 作为开发者，我希望有一条契约断言确保 `_WP_CODE_OVERRIDE` 的 910 条值全部属于合法 componentType 集合，防止新增映射时引入拼写错误。

#### Acceptance Criteria

1. THE 契约测试 SHALL 断言 `_WP_CODE_OVERRIDE` 中每个 value 都存在于 `VALID_COMPONENT_TYPES` 集合中
2. IF 任何 value 不属于合法集合, THEN THE 契约测试 SHALL 失败并报告具体非法 wp_code 和对应 value
3. THE 契约测试 SHALL 在常规 pytest 执行中自动运行（无需手动触发）

### Requirement 5: `_count_adjustments` DRY

**User Story:** 作为开发者，我希望 `_count_adjustments` 逻辑只维护一份，消除 `auto_data_resolvers.py` 和 `procedure_table_auto_service.py` 之间的重复代码。

#### Acceptance Criteria

1. THE System SHALL 提供唯一一份 `_count_adjustments` 实现（共享 helper 模块或 service 方法）
2. WHEN `auto_data_resolvers.py` 需要调用计数逻辑时, THE Resolver SHALL 从共享位置导入
3. WHEN `procedure_table_auto_service.py` 需要调用计数逻辑时, THE Service SHALL 从同一共享位置导入
4. THE 28 个 auto_data_resolvers 测试 SHALL 全部通过
5. THE procedure_table_auto_service 相关测试 SHALL 全部通过

### Requirement 6: `_WP_CODE_OVERRIDE` 外置 JSON

**User Story:** 作为开发者，我希望 910 条 wp_code→componentType 映射从源码内嵌改为外置 JSON 文件，便于非开发人员审阅和热重载修改。

#### Acceptance Criteria

1. THE System SHALL 在 `backend/app/data/wp_code_overrides.json` 存储全部映射，格式为 `{"wp_code": "componentType"}` 扁平对象
2. WHEN 应用启动时, THE OverrideLoader SHALL 读取 JSON 文件并验证所有 value 属于 `VALID_COMPONENT_TYPES`
3. IF JSON 文件包含非法 componentType 值, THEN THE OverrideLoader SHALL 在启动时抛出异常并拒绝启动
4. WHEN JSON 文件在运行时被修改时, THE OverrideLoader SHALL 在下次请求前重新加载（热重载，基于文件 mtime 检测）
5. THE `_WP_CODE_OVERRIDE` 在源码中 SHALL 被替换为从 JSON 加载的引用
6. THE 1096 render-config 冒烟测试 SHALL 全部通过

### Requirement 7: auto_data_resolvers Docstring 补全

**User Story:** 作为新加入团队的开发者，我希望每个 resolver 函数都有清晰的 docstring，说明其输入参数、数据来源和返回结构，降低理解成本。

#### Acceptance Criteria

1. THE auto_data_resolvers.py 中每个注册到 `_REGISTRY` 的 resolver 函数 SHALL 包含 docstring
2. THE docstring SHALL 至少说明：(a) 该 resolver 的用途，(b) 返回数据的结构概要
3. WHEN 新增 resolver 时, THE 代码审查 SHALL 依据此规范要求 docstring（文档化约定）
4. THE 全部 51 个 resolver 函数 SHALL 有非空 docstring

### Requirement 8: Router_Registry 启动完整性断言

**User Story:** 作为开发者，我希望应用启动时自动检测是否有 router 文件遗漏注册，避免上线后才发现端点 404。

#### Acceptance Criteria

1. WHEN 应用启动时, THE Registry_Validator SHALL 扫描 `backend/app/routers/` 目录下所有包含 `router = APIRouter` 的 Python 模块
2. THE Registry_Validator SHALL 与已注册 router 列表比对，找出未注册模块
3. IF 存在未注册的 router 模块, THEN THE Registry_Validator SHALL 以 WARNING 级别日志输出遗漏列表（不阻断启动）
4. THE System SHALL 提供一个 pytest 测试断言所有 router 模块已注册（CI 阻断）
5. WHERE 某些 router 文件故意不注册（如废弃/实验性）, THE System SHALL 支持通过排除列表（`_EXCLUDED_ROUTERS`）显式豁免

### Requirement 9: wp_template_files.py 预防性策略拆分

**User Story:** 作为开发者，我希望预防 `wp_template_files.py`（~1160 行）继续膨胀，将其按端点职责拆分为子模块。

#### Acceptance Criteria

1. THE wp_template_files.py SHALL 在拆分后总行数 ≤ 800 行（仅保留路由注册和公共 helper）
2. THE System SHALL 将 xlsx 转换相关端点拆入独立模块（如 `wp_template_xlsx.py`）
3. THE System SHALL 将 docx 转换相关端点拆入独立模块（如 `wp_template_docx.py`）
4. THE 所有已有 API 端点路径和响应结构 SHALL 保持不变（零破坏性变更）
5. THE 相关测试 SHALL 全部通过（零回归）

## 非目标（不做）

- 不改 componentType 语义
- 不改前端组件
- 不改 API 响应结构
- 不加新底稿类型
