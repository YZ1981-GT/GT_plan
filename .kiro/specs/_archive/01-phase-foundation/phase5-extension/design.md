# Phase 8 - 扩展能力与远期规划 设计文档

## 简介

本文档定义第八阶段"扩展能力与远期规划"的技术设计方案。本阶段在完成前七个阶段的基础上，实现系统的扩展性能力、多准则适配、监管对接、用户自定义模板等高级功能，并为未来的AI能力扩展预留接口。

## 与以往需求的冲突及解决方案

### 1. Metabase数据可视化集成

**冲突点：**

- **与Phase 4 AI功能的潜在重叠**：Phase 4实现了AI辅助分析（收入、采购、银行对账等），Metabase也提供数据可视化分析能力，可能存在功能重复。
- **与前端布局的冲突**：Metabase需要通过iframe嵌入前端，可能与现有的三栏布局产生样式冲突或交互冲突。
- **与ONLYOFFICE的潜在混淆**：用户可能不清楚何时使用Metabase看板，何时使用ONLYOFFICE编辑底稿。

**解决方案：**

- **明确功能边界**：
  - Metabase：用于项目级数据可视化看板（项目进度、账套总览、科目穿透、辅助账分析、凭证趋势），侧重于管理和监控视角
  - Phase 4 AI：用于具体的审计程序辅助（收入循环分析、采购循环分析、银行对账等），侧重于执行视角
  - ONLYOFFICE：用于底稿编辑和报表生成，侧重于文档编辑视角
- **统一嵌入规范**：
  - Metabase仪表板嵌入使用统一的iframe容器，遵循GT品牌视觉规范（紫色边框、阴影、圆角）
  - 嵌入位置明确：左侧栏"仪表盘"功能、右侧栏"关键指标"Tab
  - 提供全屏模式切换，避免iframe样式冲突
- **用户引导**：
  - 在前端提供明确的功能入口说明（图标+文字提示）
  - 在用户手册中明确各工具的使用场景
  - 提供工具切换的快捷键（如Ctrl+D切换到仪表板，Ctrl+E切换到底稿编辑）

### 2. Paperless-ngx附件文档管理集成

**冲突点：**

- **与Phase 3协作功能的附件管理重叠**：Phase 3已实现附件管理（confirmation_attachment等表），Paperless-ngx引入可能导致两套附件管理系统并存。
- **与Phase 4 PaddleOCR的冲突**：Phase 4使用PaddleOCR进行OCR识别，Paperless-ngx内置Tesseract OCR，可能产生OCR引擎选择的困惑。
- **与现有文件存储的冲突**：现有附件存储在审计系统统一文件存储，Paperless-ngx有自己的文件存储机制。

**解决方案：**

- **统一附件管理架构**：
  - 保留Phase 3的附件管理表结构（confirmation_attachment等），用于特定场景（如函证附件）
  - 新增Paperless-ngx专用的attachments表，用于通用附件管理（合同、发票、证照等）
  - 通过attachment_working_paper关联表实现附件与底稿的关联
  - 两套系统通过统一的AttachmentService对外提供服务，内部根据场景路由到不同的存储
- **OCR引擎分工**：
  - PaddleOCR：保留用于Phase 4的AI场景（发票识别、合同分析等），侧重于结构化数据提取
  - Tesseract（Paperless-ngx）：用于附件文档的全文OCR识别，侧重于可搜索性
  - 在配置中明确OCR引擎的使用场景，避免混淆
- **统一文件存储**：
  - Paperless-ngx配置使用审计系统的统一文件存储（NAS/本地文件系统）
  - 通过环境变量配置PAPERLESS_MEDIA_ROOT指向审计系统存储路径
  - 保持文件组织结构的一致性（按项目/年度/公司目录组织）

### 3. 大数据处理优化（账套数据联动查询）

**冲突点：**

- **与现有数据库结构的冲突**：现有journal_entries表未分区，新增分区策略需要数据迁移，可能影响现有功能。
- **与现有查询API的冲突**：现有账表查询API（/api/projects/{id}/accounts）与新增的穿透查询API（/api/projects/{id}/ledger/penetrate）可能功能重叠。
- **与前端现有组件的冲突**：现有账表展示组件未使用虚拟滚动，新增虚拟滚动组件可能导致组件不一致。

**解决方案：**

- **平滑数据迁移**：
  - 提供数据迁移脚本（Alembic migration），将现有journal_entries表转换为分区表
  - 迁移过程分为两个阶段：
    - 阶段1：创建分区表结构，保留原表作为历史数据
    - 阶段2：逐步将历史数据迁移到对应分区，保持服务在线
  - 提供回滚机制，迁移失败可恢复到原表结构
- **API兼容性设计**：
  - 保留现有账表查询API（/api/projects/{id}/accounts），保持向后兼容
  - 新增穿透查询API（/api/projects/{id}/ledger/penetrate）作为高级功能，可选使用
  - 在API文档中明确两个API的使用场景：
    - /api/projects/{id}/accounts：基础账表查询，适用于简单场景
    - /api/projects/{id}/ledger/penetrate：穿透查询，适用于复杂分析场景
- **前端组件渐进式升级**：
  - 保留现有账表展示组件，用于简单场景（数据量小）
  - 新增虚拟滚动组件，用于大数据量场景
  - 根据数据量自动选择组件（如数据量<1000行使用原组件，>=1000行使用虚拟滚动组件）
  - 统一组件接口，确保切换时用户体验一致

### 4. vue-office轻量级文档预览

**冲突点：**

- **与ONLYOFFICE的冲突**：vue-office和ONLYOFFICE都支持文档预览，可能导致用户困惑何时使用哪个工具。
- **与前端组件体系的冲突**：vue-office是第三方组件，可能与现有的Element Plus组件体系产生样式冲突。

**解决方案：**

- **明确使用场景**：
  - vue-office：仅用于附件快速预览（合同、发票、回函等），不支持编辑
  - ONLYOFFICE：用于底稿编辑和报表生成，支持完整编辑功能
  - 在附件列表中使用vue-office预览，点击"编辑"按钮才打开ONLYOFFICE
- **样式隔离**：
  - vue-office组件包裹在独立的容器中，使用scoped样式避免样式污染
  - 遵循GT品牌视觉规范，统一组件外观（边框、阴影、圆角）
  - 提供统一的预览组件封装（AttachmentPreview.vue），隐藏vue-office的实现细节

### 5. 数据库分区表策略

**冲突点：**

- **与现有ORM层的冲突**：SQLAlchemy 2.0对分区表的支持有限，可能需要特殊处理。
- **与现有Alembic迁移的冲突**：分区表的创建和迁移需要特殊的SQL语句，标准的Alembic迁移可能无法直接支持。

**解决方案：**

- **ORM层适配**：
  - 使用SQLAlchemy的DDL扩展（op.execute）执行分区表创建SQL
  - 在模型层使用装饰器标记分区表，自动生成正确的DDL
  - 提供分区表查询的辅助方法，自动路由到正确的分区
- **Alembic迁移适配**：
  - 编写自定义迁移脚本，使用op.execute执行分区表相关SQL
  - 在迁移脚本中添加错误处理和回滚逻辑
  - 提供迁移验证脚本，检查分区表创建是否正确
  - 在文档中明确分区表迁移的注意事项和操作步骤

### 6. Redis缓存策略

**冲突点：**

- **与现有缓存策略的冲突**：Phase 0-7已使用Redis缓存（如会话管理、计算结果缓存），新增缓存策略可能导致缓存键冲突或缓存失效策略不一致。
- **与数据一致性的冲突**：穿透查询结果缓存可能导致数据不一致（如底稿修改后缓存未失效）。

**解决方案：**

- **缓存键命名规范**：
  - 建立统一的缓存键命名规范：`{service}:{resource}:{identifier}`
  - Metabase缓存键：`metabase:dashboard:{dashboard_id}:{params_hash}`
  - 穿透查询缓存键：`penetrate:{project_id}:{year}:{company_code}:{account_code}:{date_range}`
  - 避免与现有缓存键冲突
- **缓存失效策略**：
  - 主动失效：在底稿修改、调整分录变更等操作后，主动清除相关缓存
  - TTL失效：设置合理的TTL（5分钟），即使主动失效失败也能保证数据最终一致性
  - 版本控制：在缓存键中加入数据版本号，数据变更时版本号递增，自动使旧缓存失效
  - 提供缓存管理API，支持手动清除指定项目的缓存

### 7. 外部服务依赖

**冲突点：**

- **与系统独立性的冲突**：引入Metabase和Paperless-ngx作为外部服务，增加了系统依赖，可能影响系统部署和运维复杂度。
- **与性能的冲突**：外部服务调用可能增加响应延迟，影响用户体验。

**解决方案：**

- **部署策略**：
  - Metabase和Paperless-ngx与审计系统一起部署在Docker Compose中，保持部署一致性
  - 提供单机部署和分布式部署两种方案，根据团队规模选择
  - 编写详细的部署文档和运维手册
- **性能优化**：
  - 外部服务调用使用异步httpx客户端，避免阻塞
  - 提供降级方案：外部服务不可用时，提供基础功能替代（如Metabase不可用时使用简单的表格展示）
  - 实现服务健康检查，及时发现和故障转移
  - 提供服务调用超时配置，避免长时间等待

## 架构设计

### 1. 整体架构

第八阶段的架构在前七个阶段的基础上，增加以下扩展层：

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端扩展层                                │
│  多语言组件 │ 自定义模板管理 │ 电子签名 │ 监管对接 │ AI插件管理  │
├───────────────────┼─────────────────────────────────────────────┤
│              API 扩展路由层（扩展API模块）                         │
│  /api/accounting-standards │ /api/i18n │ /api/custom-templates  │
│  /api/signatures │ /api/regulatory │ /api/ai-plugins           │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│  扩展服务层   │  插件架构层   │  外部集成层   │  多准则引擎层       │
│              │              │              │                    │
│ 标准服务      │ AI插件管理    │ 监管API集成   │ 准则适配引擎       │
│ 签名服务      │ 插件加载器    │ 第三方API    │ 多语言引擎         │
│ 自定义模板    │ 插件注册表    │ 限流/重试    │ 审计类型引擎       │
│ 监管服务      │              │              │                    │
├──────────────┴──────────────┴──────────────┴────────────────────┤
│                      数据访问层（ORM / Repository）              │
│  扩展模型：AccountingStandard、SignatureRecord、CustomTemplate  │
│  RegulatoryFiling、GTWPCoding、TAccount、AIPlugin             │
├─────────────────────────────────────────────────────────────────┤
│                      数据存储层                                  │
│  PostgreSQL │ 扩展表（accounting_standards、signature_records等）│
└─────────────────────────────────────────────────────────────────┘
```

### 2. 多准则适配架构

```python
# 准则适配引擎
class AccountingStandardEngine:
    def __init__(self, standard_code: str):
        self.standard_code = standard_code
        self.chart_of_accounts = self.load_standard_chart()
        self.report_formats = self.load_report_formats()
        self.disclosure_templates = self.load_disclosure_templates()
    
    def load_standard_chart(self) -> List[Account]:
        """加载准则对应的标准科目表"""
        
    def load_report_formats(self) -> Dict[str, ReportFormat]:
        """加载准则对应的报表格式"""
        
    def get_applicable_template_set(self, audit_type: str) -> TemplateSet:
        """根据准则和审计类型获取适用的模板集"""
```

### 3. 多语言支持架构

```python
# i18n框架
class I18nService:
    def __init__(self):
        self.translations = self.load_translations()
    
    def load_translations(self) -> Dict[str, Dict[str, str]]:
        """加载所有语言文件"""
        
    def get_text(self, key: str, lang: str = 'zh-CN') -> str:
        """获取指定语言的文本"""
        
    def translate_audit_term(self, term: str, lang: str) -> str:
        """翻译审计术语（AJE/RJE/TB/PBC等）"""
```

### 4. 电子签名架构

```python
# 签名服务接口
class SignService(ABC):
    @abstractmethod
    async def sign_document(self, object_type: str, object_id: UUID, 
                           signer_id: UUID, level: str) -> SignatureRecord:
        """签核文档"""
        
    @abstractmethod
    async def verify_signature(self, signature_id: UUID) -> bool:
        """验证签名"""

# Level 1实现：用户名+密码确认
class Level1SignService(SignService):
    async def sign_document(self, ...):
        # 记录操作人、时间、IP地址

# Level 2实现：手写签名图片+时间戳
class Level2SignService(SignService):
    async def sign_document(self, ...):
        # 保存手写签名图片，绑定时间戳

# Level 3实现：CA数字证书
class Level3SignService(SignService):
    async def sign_document(self, ...):
        # 对接第三方CA机构，具备法律效力
```

### 5. AI插件架构

```python
# 插件接口
class AIPlugin(ABC):
    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """插件ID"""
        
    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """插件名称"""
        
    @abstractmethod
    async def initialize(self, config: Dict):
        """初始化插件"""
        
    @abstractmethod
    async def execute(self, input_data: Any) -> Any:
        """执行插件功能"""
        
    @abstractmethod
    async def cleanup(self):
        """清理插件资源"""

# 插件管理器
class AIPluginManager:
    def __init__(self):
        self.plugins: Dict[str, AIPlugin] = {}
        self.plugin_configs: Dict[str, Dict] = {}
    
    def register_plugin(self, plugin: AIPlugin):
        """注册插件"""
        
    def load_plugin(self, plugin_id: str):
        """加载插件"""
        
    def enable_plugin(self, plugin_id: str):
        """启用插件"""
        
    def disable_plugin(self, plugin_id: str):
        """禁用插件"""
```

### 6. 外部API集成架构

```python
# 外部API客户端
class ExternalAPIClient:
    def __init__(self, base_url: str, rate_limit: int, retry_config: Dict):
        self.base_url = base_url
        self.rate_limit = rate_limit
        self.retry_config = retry_config
        self.rate_limiter = RateLimiter(rate_limit)
    
    async def call(self, endpoint: str, method: str, data: Dict) -> Response:
        """调用外部API，包含限流和重试逻辑"""
        await self.rate_limiter.acquire()
        return await self._call_with_retry(endpoint, method, data)
    
    async def _call_with_retry(self, endpoint: str, method: str, 
                               data: Dict) -> Response:
        """带重试的API调用"""
```

## 数据库设计

### 扩展表结构

#### accounting_standards（会计准则表）

```sql
CREATE TABLE accounting_standards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    standard_code VARCHAR(20) UNIQUE NOT NULL,
    standard_name VARCHAR(100) NOT NULL,
    standard_description TEXT,
    effective_date DATE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX idx_accounting_standards_code ON accounting_standards(standard_code);
CREATE INDEX idx_accounting_standards_active ON accounting_standards(is_active);
```

#### signature_records（签名记录表）

```sql
CREATE TABLE signature_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_type VARCHAR(50) NOT NULL,
    object_id UUID NOT NULL,
    signer_id UUID NOT NULL REFERENCES users(id),
    signature_level VARCHAR(20) NOT NULL,
    signature_data JSONB,
    signature_timestamp TIMESTAMP NOT NULL,
    ip_address VARCHAR(50),
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX idx_signature_records_object ON signature_records(object_type, object_id);
CREATE INDEX idx_signature_records_signer ON signature_records(signer_id);
```

#### wp_template_custom（自定义底稿模板表）

```sql
CREATE TABLE wp_template_custom (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    template_name VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    template_file_path VARCHAR(500) NOT NULL,
    is_published BOOLEAN DEFAULT false,
    version VARCHAR(20) NOT NULL,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX idx_wp_template_custom_user ON wp_template_custom(user_id);
CREATE INDEX idx_wp_template_custom_category ON wp_template_custom(category);
CREATE INDEX idx_wp_template_custom_published ON wp_template_custom(is_published);
```

#### regulatory_filing（监管备案表）

```sql
CREATE TABLE regulatory_filing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    filing_type VARCHAR(50) NOT NULL,
    filing_status VARCHAR(50) NOT NULL,
    submission_data JSONB,
    response_data JSONB,
    submitted_at TIMESTAMP,
    responded_at TIMESTAMP,
    error_message TEXT,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX idx_regulatory_filing_project ON regulatory_filing(project_id);
CREATE INDEX idx_regulatory_filing_type ON regulatory_filing(filing_type);
CREATE INDEX idx_regulatory_filing_status ON regulatory_filing(filing_status);
```

#### gt_wp_coding（致同底稿编码表）

```sql
CREATE TABLE gt_wp_coding (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code_prefix VARCHAR(10) NOT NULL,
    code_range VARCHAR(50) NOT NULL,
    cycle_name VARCHAR(100) NOT NULL,
    wp_type VARCHAR(50) NOT NULL,
    description TEXT,
    sort_order INTEGER,
    is_active BOOLEAN DEFAULT true,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX idx_gt_wp_coding_prefix ON gt_wp_coding(code_prefix);
CREATE INDEX idx_gt_wp_coding_type ON gt_wp_coding(wp_type);
CREATE INDEX idx_gt_wp_coding_active ON gt_wp_coding(is_active);
```

#### t_accounts（T型账户表）

```sql
CREATE TABLE t_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    account_code VARCHAR(50) NOT NULL,
    account_name VARCHAR(200) NOT NULL,
    account_type VARCHAR(50) NOT NULL,
    description TEXT,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX idx_t_accounts_project ON t_accounts(project_id);
CREATE INDEX idx_t_accounts_account ON t_accounts(account_code);
```

#### t_account_entries（T型账户分录表）

```sql
CREATE TABLE t_account_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    t_account_id UUID NOT NULL REFERENCES t_accounts(id),
    entry_type VARCHAR(10) NOT NULL,
    amount NUMERIC(20,2) NOT NULL,
    description TEXT,
    reference_id UUID,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX idx_t_account_entries_account ON t_account_entries(t_account_id);
```

#### ai_plugins（AI插件表）

```sql
CREATE TABLE ai_plugins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id VARCHAR(100) UNIQUE NOT NULL,
    plugin_name VARCHAR(200) NOT NULL,
    plugin_version VARCHAR(20) NOT NULL,
    plugin_description TEXT,
    is_enabled BOOLEAN DEFAULT false,
    config JSONB,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX idx_ai_plugins_id ON ai_plugins(plugin_id);
CREATE INDEX idx_ai_plugins_enabled ON ai_plugins(is_enabled);
```

## API设计

### 多准则适配API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/accounting-standards` | 获取所有准则列表 |
| GET | `/api/accounting-standards/{id}` | 获取准则详情 |
| GET | `/api/accounting-standards/{id}/chart` | 获取准则对应科目表 |
| GET | `/api/accounting-standards/{id}/report-formats` | 获取准则对应报表格式 |
| PUT | `/api/projects/{id}/accounting-standard` | 切换项目准则 |

### 多语言支持API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/i18n/languages` | 获取支持的语言列表 |
| GET | `/api/i18n/translations/{lang}` | 获取语言文件 |
| PUT | `/api/users/{id}/language` | 设置用户语言 |
| GET | `/api/i18n/audit-terms/{lang}` | 获取审计术语翻译 |

### 自定义模板API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/custom-templates` | 创建自定义模板 |
| PUT | `/api/custom-templates/{id}` | 更新模板 |
| POST | `/api/custom-templates/{id}/publish` | 发布模板 |
| GET | `/api/custom-templates` | 模板列表 |
| GET | `/api/custom-templates/{id}` | 模板详情 |
| POST | `/api/custom-templates/{id}/validate` | 验证模板 |
| GET | `/api/custom-templates/market` | 模板市场 |

### 电子签名API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/signatures/sign` | 签核文档 |
| GET | `/api/signatures/{object_type}/{object_id}` | 获取签名记录 |
| POST | `/api/signatures/{id}/verify` | 验证签名 |
| POST | `/api/signatures/{id}/revoke` | 撤销签名 |

### 监管对接API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/regulatory/cicpa-report` | 提交审计报告备案 |
| POST | `/api/regulatory/archival-standard` | 提交归档标准 |
| GET | `/api/regulatory/filings/{id}/status` | 查询备案状态 |
| POST | `/api/regulatory/filings/{id}/retry` | 重试备案 |
| GET | `/api/regulatory/filings` | 备案列表 |

### 致同编码体系API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/gt-coding` | 编码体系列表 |
| GET | `/api/gt-coding/{id}` | 编码详情 |
| GET | `/api/gt-coding/tree` | 编码树形结构 |
| POST | `/api/projects/{id}/generate-index` | 生成底稿索引 |

### T型账户API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects/{id}/t-accounts` | 创建T型账户 |
| POST | `/api/projects/{id}/t-accounts/{id}/entries` | 添加分录 |
| GET | `/api/projects/{id}/t-accounts/{id}` | 获取T型账户 |
| POST | `/api/projects/{id}/t-accounts/{id}/calculate` | 计算净变动 |
| POST | `/api/projects/{id}/t-accounts/{id}/integrate` | 集成到现金流量表 |

### AI插件API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ai-plugins` | 插件列表 |
| GET | `/api/ai-plugins/{id}` | 插件详情 |
| POST | `/api/ai-plugins/{id}/enable` | 启用插件 |
| POST | `/api/ai-plugins/{id}/disable` | 禁用插件 |
| PUT | `/api/ai-plugins/{id}/config` | 配置插件 |
| POST | `/api/ai-plugins/{id}/execute` | 执行插件 |

## 前端组件设计

### 多语言支持组件

```vue
<!-- LanguageSwitcher.vue -->
<template>
  <el-dropdown @command="handleLanguageChange">
    <span class="language-switcher">
      {{ currentLanguageLabel }}
      <el-icon><arrow-down /></el-icon>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="zh-CN">简体中文</el-dropdown-item>
        <el-dropdown-item command="en-US">English</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>
```

### 电子签名组件

```vue
<!-- SignatureLevel2.vue -->
<template>
  <el-dialog v-model="visible" title="手写签名">
    <canvas ref="signatureCanvas" @mousedown="startDrawing" 
            @mousemove="draw" @mouseup="stopDrawing" />
    <div class="signature-actions">
      <el-button @click="clearCanvas">清除</el-button>
      <el-button type="primary" @click="confirmSignature">确认签名</el-button>
    </div>
  </el-dialog>
</template>
```

### T型账户编辑器

```vue
<!-- TAccountEditor.vue -->
<template>
  <div class="t-account-editor">
    <div class="t-account-header">
      <h3>{{ accountName }}</h3>
      <el-button @click="addEntry">添加分录</el-button>
    </div>
    <div class="t-account-body">
      <div class="debit-side">
        <h4>借方</h4>
        <div v-for="entry in debitEntries" :key="entry.id">
          {{ entry.amount }} - {{ entry.description }}
        </div>
        <div class="total">借方合计: {{ debitTotal }}</div>
      </div>
      <div class="credit-side">
        <h4>贷方</h4>
        <div v-for="entry in creditEntries" :key="entry.id">
          {{ entry.amount }} - {{ entry.description }}
        </div>
        <div class="total">贷方合计: {{ creditTotal }}</div>
      </div>
    </div>
    <div class="t-account-footer">
      <div>净变动: {{ netChange }}</div>
      <el-button @click="integrateToCFS">集成到现金流量表</el-button>
    </div>
  </div>
</template>
```

## 属性测试

### Property 1: 多准则数据隔离

*对于任意*项目，其关联的会计准则必须存在于`accounting_standards`表中，且该准则的`is_active`字段必须为true。

**Validates: Requirements 1.1, 1.2**

### Property 2: 准则切换数据完整性

*对于任意*项目切换会计准则，系统必须验证新准则的科目表和报表格式是否完整，如果缺失则拒绝切换并提示用户。

**Validates: Requirements 1.3, 1.6**

### Property 3: 签名记录不可篡改

*对于任意*签名记录，一旦创建，其`signature_data`、`signature_timestamp`、`signer_id`字段不得修改，只能通过撤销并重新签名的方式更新。

**Validates: Requirements 5.2, 5.6**

### Property 4: 监管备案幂等性

*对于任意*监管备案请求，重复提交相同的数据不得产生重复的备案记录，系统应返回已存在的备案ID。

**Validates: Requirements 6.1, 6.2**

### Property 5: AI插件隔离

*对于任意*AI插件，其执行必须在独立的上下文中进行，插件的错误不得影响主系统运行，插件的配置不得与其他插件冲突。

**Validates: Requirements 11.1, 11.2**

### Property 6: T型账户勾稽一致性

*对于任意*T型账户，其计算的净变动必须与资产负债表中对应科目的期初期末变动一致，不一致时必须标注差异。

**Validates: Requirements 10.4**

### Property 7: 自定义模板版本唯一性

*对于任意*用户自定义模板，同一用户、同一模板名称、同一版本号只能存在一条记录，重复上传必须提升版本号。

**Validates: Requirements 4.4**

## 部署考虑

### 1. 数据库迁移

第八阶段需要执行以下数据库迁移：
- 创建7个新表（accounting_standards、signature_records、wp_template_custom、regulatory_filing、gt_wp_coding、t_accounts、t_account_entries、ai_plugins）
- 扩展2个现有表（users添加language字段、projects扩展audit_type枚举并添加accounting_standard字段）
- 插入种子数据（会计准则数据、致同底稿编码数据）

### 2. 配置管理

需要新增以下配置项：
```yaml
# 多语言配置
i18n:
  default_language: zh-CN
  supported_languages:
    - zh-CN
    - en-US
  translation_path: ./translations

# 电子签名配置
signature:
  default_level: level1
  level2_storage_path: ./signatures
  level3_ca_provider: null  # 远期配置

# 监管对接配置
regulatory:
  cicpa_api_url: null  # 远期配置
  cicpa_api_key: null
  archival_standard_api_url: null

# AI插件配置
ai_plugins:
  plugin_path: ./plugins
  external_api_rate_limit: 100  # 每分钟请求数
  external_api_retry_count: 3
  external_api_retry_delay: 1000  # 毫秒
```

### 3. 依赖项

需要新增以下Python依赖：
```txt
# i18n支持
babel>=2.13.0

# CA证书支持（远期）
python-cryptography>=41.0.0  # Level 3签名

# 外部API客户端
httpx>=0.24.0  # 异步HTTP客户端
tenacity>=8.2.0  # 重试机制

# 插件系统
importlib-metadata>=6.0.0
```

### 4. 前端依赖

需要新增以下npm依赖：
```json
{
  "dependencies": {
    "vue-i18n": "^9.3.0",
    "signature_pad": "^4.1.0"
  }
}
```

## 性能考虑

### 1. 多语言性能

- 语言文件应在前端构建时打包，避免运行时加载
- 翻译缓存使用浏览器localStorage，减少重复请求
- 审计术语翻译使用内存缓存，TTL设置为1小时

### 2. 监管备案性能

- 备案数据转换使用异步任务队列，不阻塞主流程
- 备案状态查询使用Redis缓存，TTL设置为5分钟
- 大量项目批量备案使用分批处理，避免超时

### 3. AI插件性能

- 插件加载使用懒加载，只在首次使用时加载
- 插件执行使用线程池，避免阻塞主线程
- 外部API调用使用连接池，复用HTTP连接

## 安全考虑

### 1. 电子签名安全

- Level 1签名必须验证用户密码，使用bcrypt加密存储
- Level 2签名图片必须加密存储，使用AES-256
- Level 3签名证书必须使用HSM（硬件安全模块）存储，私钥不可导出

### 2. 监管对接安全

- 备案API调用必须使用HTTPS
- 备案数据必须使用数字签名，防止篡改
- 备案响应必须验证CA证书，防止中间人攻击

### 3. 自定义模板安全

- 自定义模板上传必须验证文件类型，防止恶意文件
- 自定义公式必须沙箱执行，防止代码注入
- 模板发布必须经过审核，防止传播恶意模板

### 4. AI插件安全

- 插件必须签名验证，防止恶意插件
- 插件执行必须资源限制（CPU、内存、网络），防止资源耗尽
- 外部API调用必须限流，防止滥用

## 外部系统集成与数据处理优化设计

### 1. Metabase集成架构

```python
# Metabase集成服务
class MetabaseIntegrationService:
    def __init__(self, metabase_url: str, metabase_token: str):
        self.metabase_url = metabase_url
        self.metabase_token = metabase_token

    async def create_dashboard(self, project_id: UUID, dashboard_config: dict):
        """创建项目专属仪表板"""
        # 调用Metabase API创建仪表板
        # 预置SQL查询模板
        # 配置数据源连接

    async def get_embed_url(self, dashboard_id: int, params: dict):
        """获取仪表板嵌入URL"""
        # 使用Metabase Embedding API
        # 传递参数（project_id, year, company_code等）
        # 返回嵌入URL

    async def refresh_dashboard(self, dashboard_id: int):
        """刷新仪表板数据"""
        # 触发Metabase数据刷新
        # 清除Redis缓存
```

**预置仪表板模板：**

```sql
-- 项目进度看板
SELECT
    COUNT(*) as total_wps,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_wps,
    SUM(CASE WHEN status = 'reviewed' THEN 1 ELSE 0 END) as reviewed_wps,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_wps
FROM wp_index
WHERE project_id = :project_id AND is_deleted = false;

-- 账套总览
SELECT
    account_code,
    account_name,
    SUM(debit_amount) as debit_total,
    SUM(credit_amount) as credit_total
FROM journal_entries
WHERE project_id = :project_id AND year = :year AND company_code = :company_code
GROUP BY account_code, account_name
ORDER BY account_code;
```

### 2. Paperless-ngx集成架构

```python
# 附件管理服务
class AttachmentService:
    def __init__(self, paperless_url: str, paperless_token: str):
        self.paperless_url = paperless_url
        self.paperless_token = paperless_token
        self.client = httpx.AsyncClient()

    async def upload_to_paperless(self, file_path: str, metadata: dict):
        """上传文档到Paperless-ngx"""
        files = {'document': open(file_path, 'rb')}
        data = {
            'title': metadata.get('title'),
            'correspondent': metadata.get('customer_name'),
            'document_type': metadata.get('document_type'),
            'tags': metadata.get('tags', [])
        }
        response = await self.client.post(
            f'{self.paperless_url}/api/documents/post_document/',
            files=files,
            data=data,
            headers={'Authorization': f'Token {self.paperless_token}'}
        )
        return response.json()

    async def get_ocr_result(self, document_id: int):
        """获取OCR识别结果"""
        response = await self.client.get(
            f'{self.paperless_url}/api/documents/{document_id}/',
            headers={'Authorization': f'Token {self.paperless_token}'}
        )
        return response.json().get('content', '')

    async def search_attachments(self, query: str):
        """全文搜索附件"""
        response = await self.client.get(
            f'{self.paperless_url}/api/documents/',
            params={'query': query},
            headers={'Authorization': f'Token {self.paperless_token}'}
        )
        return response.json()

    async def associate_with_working_paper(self, attachment_id: UUID, wp_id: UUID):
        """关联附件到底稿"""
        # 在attachment_working_paper表中创建关联记录
        # 记录关联时间、关联人
```

**附件表结构：**

```sql
CREATE TABLE attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size BIGINT NOT NULL,
    paperless_document_id INTEGER,
    ocr_status VARCHAR(20) DEFAULT 'pending',
    ocr_text TEXT,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX idx_attachments_project ON attachments(project_id);
CREATE INDEX idx_attachments_ocr_status ON attachments(project_id, ocr_status);
CREATE INDEX idx_attachments_paperless ON attachments(paperless_document_id);

CREATE TABLE attachment_working_paper (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attachment_id UUID NOT NULL REFERENCES attachments(id),
    wp_id UUID NOT NULL REFERENCES working_paper(id),
    association_type VARCHAR(50) NOT NULL,
    notes TEXT,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT current_timestamp
);
```

### 3. 大数据处理优化架构

**穿透查询服务：**

```python
class LedgerPenetrationService:
    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis

    async def get_penetrate_data(
        self,
        project_id: UUID,
        year: int,
        company_code: str,
        account_code: Optional[str] = None,
        date_range: Optional[str] = None
    ) -> dict:
        """获取穿透查询数据（使用CTE一次性查询）"""
        query = """
        WITH total AS (
            SELECT
                account_code,
                account_name,
                SUM(debit_amount) as debit_total,
                SUM(credit_amount) as credit_total,
                SUM(debit_amount) - SUM(credit_amount) as balance
            FROM journal_entries
            WHERE project_id = :project_id
              AND year = :year
              AND company_code = :company_code
              AND (:account_code IS NULL OR account_code = :account_code)
              AND (:date_range IS NULL OR date BETWEEN :start_date AND :end_date)
              AND is_deleted = false
            GROUP BY account_code, account_name
        ),
        ledger AS (
            SELECT
                date,
                voucher_id,
                account_code,
                account_name,
                debit_amount,
                credit_amount,
                balance,
                description
            FROM journal_entries
            WHERE project_id = :project_id
              AND year = :year
              AND company_code = :company_code
              AND (:account_code IS NULL OR account_code = :account_code)
              AND (:date_range IS NULL OR date BETWEEN :start_date AND :end_date)
              AND is_deleted = false
            ORDER BY date, voucher_id
        ),
        voucher AS (
            SELECT DISTINCT
                voucher_id,
                date
            FROM journal_entries
            WHERE project_id = :project_id
              AND year = :year
              AND company_code = :company_code
              AND (:account_code IS NULL OR account_code = :account_code)
              AND (:date_range IS NULL OR date BETWEEN :start_date AND :end_date)
              AND is_deleted = false
            ORDER BY date, voucher_id
        )
        SELECT * FROM total;
        SELECT * FROM ledger;
        SELECT * FROM voucher;
        """

        # 解析日期范围
        start_date, end_date = None, None
        if date_range:
            start_date, end_date = date_range.split(',')

        # 执行查询
        results = await self.db.execute(
            text(query),
            {
                "project_id": project_id,
                "year": year,
                "company_code": company_code,
                "account_code": account_code,
                "start_date": start_date,
                "end_date": end_date
            }
        )

        return {
            "total": results[0],
            "ledger": results[1],
            "voucher": results[2]
        }

    async def get_penetrate_data_cached(
        self,
        project_id: UUID,
        year: int,
        company_code: str,
        account_code: Optional[str] = None,
        date_range: Optional[str] = None
    ) -> dict:
        """获取穿透查询数据（带缓存）"""
        cache_key = f"penetrate:{project_id}:{year}:{company_code}:{account_code}:{date_range}"

        # 尝试从缓存获取
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # 缓存未命中，查询数据库
        result = await self.get_penetrate_data(
            project_id, year, company_code, account_code, date_range
        )

        # 写入缓存，TTL=5分钟
        await self.redis.setex(cache_key, 300, json.dumps(result))

        return result
```

**数据库分区策略：**

```sql
-- 按年度分区journal_entries表
CREATE TABLE journal_entries (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    year INTEGER NOT NULL,
    company_code VARCHAR(50) NOT NULL,
    account_code VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    voucher_id VARCHAR(50),
    debit_amount NUMERIC(20,2),
    credit_amount NUMERIC(20,2),
    balance NUMERIC(20,2),
    description TEXT,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT current_timestamp
) PARTITION BY RANGE (year);

-- 创建2024年分区
CREATE TABLE journal_entries_2024 PARTITION OF journal_entries
    FOR VALUES FROM (2024) TO (2025);

-- 创建2025年分区
CREATE TABLE journal_entries_2025 PARTITION OF journal_entries
    FOR VALUES FROM (2025) TO (2026);

-- 创建索引（在每个分区上自动继承）
CREATE INDEX idx_journal_entries_2024_project_year_company_account
    ON journal_entries_2024(project_id, year, company_code, account_code);

CREATE INDEX idx_journal_entries_2024_project_year_company_date
    ON journal_entries_2024(project_id, year, company_code, date);
```

**前端虚拟滚动组件：**

```vue
<template>
  <div class="virtual-scroll-container" @scroll="handleScroll" ref="container">
    <div class="virtual-scroll-content" :style="{ height: totalHeight + 'px' }">
      <div
        class="virtual-scroll-item"
        v-for="item in visibleItems"
        :key="item.id"
        :style="{ transform: `translateY(${item.offset}px)` }"
      >
        <slot :item="item" />
      </div>
    </div>
  </div>
</template>

<script>
export default {
  props: {
    items: Array, // 所有数据
    itemHeight: { type: Number, default: 40 }, // 每项高度
    bufferSize: { type: Number, default: 5 } // 缓冲区大小
  },
  data() {
    return {
      scrollTop: 0,
      visibleStart: 0,
      visibleEnd: 0
    }
  },
  computed: {
    totalHeight() {
      return this.items.length * this.itemHeight
    },
    visibleItems() {
      return this.items.slice(this.visibleStart, this.visibleEnd).map((item, index) => ({
        ...item,
        offset: (this.visibleStart + index) * this.itemHeight
      }))
    }
  },
  methods: {
    handleScroll(event) {
      this.scrollTop = event.target.scrollTop
      const startIndex = Math.floor(this.scrollTop / this.itemHeight)
      this.visibleStart = Math.max(0, startIndex - this.bufferSize)
      this.visibleEnd = Math.min(
        this.items.length,
        startIndex + Math.ceil(event.target.clientHeight / this.itemHeight) + this.bufferSize
      )
    }
  }
}
</script>
```

### 4. 综合架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端（Vue 3）                            │
│  三栏布局 │ vue-office预览 │ Metabase嵌入 │ ONLYOFFICE编辑器      │
│  虚拟滚动组件 │ 附件预览组件 │ 仪表板嵌入组件                       │
├─────────────────────────────────────────────────────────────────┤
│                      API网关（FastAPI）                          │
│  底稿API │ 账套穿透API │ 附件API │ Metabase Embedding API       │
├──────────────────┬──────────────────┬───────────────────────────┤
│  业务服务层       │  外部集成层       │  数据可视化层              │
│                  │                  │                           │
│ 底稿服务          │ Paperless-ngx    │ Metabase（独立部署）       │
│ 账套服务          │ OCR识别          │ - 数据库连接              │
│ 附件服务          │ 文档分类          │ - 仪表板预置              │
│ 穿透查询服务      │ 全文搜索          │ - SQL查询模板             │
├──────────────────┴──────────────────┴───────────────────────────┤
│                      数据存储层                                  │
│  PostgreSQL（分区表+索引）│ Redis（缓存）│ 文件存储（附件+底稿）   │
└─────────────────────────────────────────────────────────────────┘
```

### 5. 性能优化策略

**缓存策略：**

- Metabase仪表板查询结果：Redis缓存，TTL=5分钟
- 穿透查询结果：Redis缓存，TTL=5分钟
- 附件OCR结果：存储在数据库，全文搜索使用PostgreSQL全文索引
- 用户布局偏好：localStorage永久缓存

**查询优化：**

- 使用CTE一次性查询多层级数据，减少数据库往返
- 按年度分区journal_entries表，查询只扫描特定年份分区
- 核心查询路径建立联合索引
- 大数据量查询使用LIMIT + OFFSET分页

**前端优化：**

- 虚拟滚动处理大量数据（只渲染可见行）
- 懒加载（点击项目后才加载详情）
- 防抖/节流（滚动、搜索等高频操作）
- Web Worker处理复杂计算

## 测试策略

### 1. 单元测试

- 所有新增服务必须有单元测试覆盖
- 测试覆盖率要求：核心逻辑>=80%，整体>=60%

### 2. 集成测试

- 多准则适配端到端测试
- 多语言支持端到端测试
- 电子签名流程端到端测试
- 监管对接端到端测试

### 3. 性能测试

- 多准则切换性能测试（目标：<1秒）
- 多语言切换性能测试（目标：<500ms）
- 监管备案性能测试（目标：单个项目<10秒）
- AI插件执行性能测试（目标：单个插件<5秒）

### 4. 安全测试

- 电子签名安全测试
- 监管对接安全测试
- 自定义模板安全测试
- AI插件安全测试
