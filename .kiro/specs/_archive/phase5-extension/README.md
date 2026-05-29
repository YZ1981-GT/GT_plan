# Phase 8 - 扩展能力与远期规划

## 概述

本阶段实现系统的扩展性能力、多准则适配、监管对接、用户自定义模板等高级功能，并为未来的AI能力扩展预留接口。同时引入外部系统集成（Metabase、Paperless-ngx）和大数据处理优化，提升系统的数据可视化和附件管理能力。

本阶段的目标是将系统从一个"企业会计准则下的年审工具"升级为"全场景审计作业平台"，支持多种审计类型、多种会计准则、多语言环境，并具备与监管系统对接的能力。

## 阶段目标

1. **多准则适配**：支持企业会计准则、小企业准则、政府会计准则、金融企业准则、国际准则IFRS
2. **多语言支持**：支持中英双语界面和报表输出
3. **审计类型扩展**：支持年度审计、专项审计、IPO审计、内控审计、验资、税审
4. **用户自定义模板**：允许用户创建自定义底稿模板、行业专用模板，扩展取数公式DSL
5. **电子签名方案**：实现三级电子签名（用户名+密码、手写签名、CA证书）
6. **监管对接**：对接中注协审计报告备案接口、电子底稿归档标准接口
7. **致同底稿编码体系**：内置致同标准的底稿编码体系（B/C/D-N/A/S/Q/Z类）
8. **品牌视觉规范**：详细实现致同GT品牌视觉规范
9. **附注模版完善**：完善国企版和上市版附注模版体系
10. **T型账户法**：实现现金流量表编制的T型账户分析工具
11. **AI能力预留接口**：为未来AI能力扩展预留插件架构
12. **Metabase数据可视化集成**：集成Metabase提供项目级数据可视化看板
13. **Paperless-ngx附件文档管理**：集成Paperless-ngx管理附件文档，支持OCR识别和全文搜索
14. **大数据处理优化**：优化账套数据联动查询，支持分区表、虚拟滚动、缓存策略

## 文档结构

- `requirements.md` - 需求文档，定义18个核心需求（含冲突说明）
- `tasks.md` - 任务清单，包含32个主要任务组（含冲突说明，Task 30三栏布局已完成初版）
- `design.md` - 设计文档，包含架构设计、数据库设计、API设计、冲突与解决方案

## 核心需求

### 需求 1：多准则适配
支持多种会计准则，每个准则对应不同的科目表、报表格式和附注模版。

### 需求 2：多语言支持
实现i18n框架，支持中英双语界面和报表输出。

### 需求 3：审计类型扩展
扩展审计类型，支持年度审计、专项审计、IPO审计、内控审计、验资、税审。

### 需求 4：用户自定义底稿模板
允许用户创建自定义模板、行业专用模板，扩展取数公式DSL，支持模板市场/共享。

### 需求 5：电子签名方案
实现三级电子签名（Level 1: 用户名+密码、Level 2: 手写签名图片、Level 3: CA数字证书）。

### 需求 6：监管对接
对接中注协审计报告备案接口和电子底稿归档标准接口。

### 需求 7：致同底稿编码体系
内置致同标准的底稿编码体系（B/C/D-N/A/S/Q/Z类），支持三测联动结构，关联6个内置模板集（附录G.6）。

### 需求 8：致同品牌视觉规范详细实现
详细实现致同GT品牌视觉规范，包括色系、字体、间距、圆角、阴影、可访问性等。

### 需求 9：附注模版体系完善
完善国企版和上市版附注模版，包含科目对照、校验公式、宽表公式、正文模版四个配置。

### 需求 10：T型账户法（现金流量表编制）
实现T型账户分析工具，处理固定资产处置、债务重组等复杂现金流量表编制场景。

### 需求 11：AI能力预留接口
为未来AI能力扩展预留插件架构，支持电子发票真伪验证、工商信息查询、银行对账等场景。

### 需求 12：数据表Schema定义
定义第八阶段扩展表的数据表结构（分区表和索引定义见需求15，避免冗余）。

### 需求 13：Metabase数据可视化集成
集成Metabase作为独立服务，提供项目级数据可视化看板。Metabase侧重管理层全局视角（跨项目汇总、趋势分析），与三栏布局右侧栏的单项目操作视角互补。

### 需求 14：Paperless-ngx附件文档管理集成
集成Paperless-ngx作为独立服务，管理附件文档，支持OCR识别和全文搜索。

### 需求 15：大数据处理优化（账套数据联动查询）
优化账套数据联动查询，支持分区表、虚拟滚动、缓存策略。

### 需求 16：前端三栏布局（已完成初版）
实现三栏式工作台布局（左侧功能导航+中间内容列表+右侧详情预览），支持拖拽调整、折叠、全屏、响应式。

### 需求 17：vue-office轻量级文档预览
集成vue-office组件用于附件快速只读预览，与ONLYOFFICE编辑模式明确区分。

### 需求 18：Teable/Grist评估
评估Teable或Grist作为PBC清单/函证/底稿索引管理的辅助工具可行性。

## 数据库变更

### 新增表（10个）
1. `accounting_standards` - 会计准则表
2. `signature_records` - 签名记录表
3. `wp_template_custom` - 自定义底稿模板表
4. `regulatory_filing` - 监管备案表
5. `gt_wp_coding` - 致同底稿编码表
6. `t_accounts` - T型账户表
7. `t_account_entries` - T型账户分录表
8. `ai_plugins` - AI插件表
9. `attachments` - 附件管理表（Paperless-ngx集成）
10. `attachment_working_paper` - 附件底稿关联表

### 扩展现有表（2个）
1. `users` - 添加`language`字段
2. `projects` - 扩展`audit_type`枚举，添加`accounting_standard`字段

### 分区表（1个）
1. `journal_entries` - 按年度分区（journal_entries_2024、journal_entries_2025等）

### 新增索引（5个）
1. `idx_attachments_project` - 附件表项目索引
2. `idx_attachments_ocr_status` - 附件表OCR状态索引
3. `idx_attachments_paperless` - 附件表Paperless文档ID索引
4. `idx_journal_entries_project_year_company_account` - 分录表复合索引
5. `idx_journal_entries_project_year_company_date` - 分录表日期索引

## API变更

### 新增API路由（11个）
1. `/api/accounting-standards` - 多准则适配API
2. `/api/i18n` - 多语言支持API
3. `/api/custom-templates` - 自定义模板API
4. `/api/signatures` - 电子签名API
5. `/api/regulatory` - 监管对接API
6. `/api/gt-coding` - 致同编码体系API
7. `/api/t-accounts` - T型账户API
8. `/api/ai-plugins` - AI插件API
9. `/api/projects/{id}/attachments` - 附件管理API
10. `/api/attachments` - 附件搜索API
11. `/api/projects/{id}/ledger/penetrate` - 穿透查询API

## 前端组件

### 新增组件（约40个）
- 多语言组件：LanguageSwitcher
- 自定义模板组件：CustomTemplateList、CustomTemplateEditor、TemplateMarket、TemplateUpload、TemplateValidator
- 电子签名组件：SignatureLevel1、SignatureLevel2、SignatureLevel3、SignatureHistory
- 监管对接组件：RegulatoryFiling、FilingStatus、FilingError、CICPAReportForm、ArchivalStandardForm
- 致同编码组件：GTCodingSystem、GTWPCodingTree、WPIndexGenerator、CustomCodingEditor
- T型账户组件：TAccountEditor、TAccountEntryForm、TAccountResult、TAccountManagement
- AI插件组件：AIPluginManagement、PluginList、PluginConfig、ExternalAPIConfig、ModelSwitcher
- 外部系统集成组件：MetabaseDashboard、DrillDownNavigator、AttachmentManagement、AttachmentPreview、VirtualScrollTable、LedgerPenetration

## 依赖项变更

### Python依赖
```txt
babel>=2.13.0  # i18n支持
python-cryptography>=41.0.0  # CA证书支持（远期）
httpx>=0.24.0  # 异步HTTP客户端
tenacity>=8.2.0  # 重试机制
importlib-metadata>=6.0.0  # 插件系统
```

### 前端依赖
```json
{
  "vue-i18n": "^9.3.0",
  "signature_pad": "^4.1.0",
  "@vue-office/docx": "^1.6.0",
  "@vue-office/excel": "^1.6.0",
  "@vue-office/pdf": "^1.6.0"
}
```

### 外部服务依赖
- Metabase（Docker部署）
- Paperless-ngx（Docker部署）

## 优先级建议

本阶段任务较多，建议按以下优先级分批实施：

### P0（必须实现）
- 多准则适配（需求1）
- 多语言支持（需求2）
- 电子签名Level 1和Level 2（需求5）
- 致同底稿编码体系（需求7）
- 致同品牌视觉规范（需求8）
- Metabase数据可视化集成（需求13）
- Paperless-ngx附件文档管理（需求14）

### P1（重要）
- 审计类型扩展（需求3）
- 用户自定义模板（需求4）
- 监管对接（需求6）
- 附注模版完善（需求9）
- 大数据处理优化（需求15）

### P2（可选）
- T型账户法（需求10）
- 电子签名Level 3（需求5，远期）
- AI能力预留接口（需求11，远期）

## 与前阶段的关系

本阶段建立在Phase 0-7的基础上，不修改现有功能，只进行扩展：

- Phase 0（基础设施）：无需修改
- Phase 1a（核心）：扩展科目体系以支持多准则
- Phase 1b（底稿）：扩展底稿模板引擎以支持自定义模板
- Phase 1c（报表）：扩展报表生成以支持多准则和多语言
- Phase 2（合并）：无需修改
- Phase 3（协作）：扩展签名记录以支持电子签名，新增附件管理表（attachments）
- Phase 4（AI）：扩展AI服务层以支持插件架构，保留PaddleOCR用于AI场景，新增Tesseract用于附件OCR
- 外部系统集成：新增Metabase和Paperless-ngx作为独立服务，通过API集成

## 预估工期

- P0任务：6-8周（包含Metabase和Paperless-ngx集成）
- P1任务：6-8周（包含大数据处理优化）
- P2任务：4-6周

总计：16-22周（约4-5.5个月）

## 风险与注意事项

1. **多准则适配复杂度**：不同准则的科目表和报表格式差异较大，需要充分的测试和验证
2. **监管对接不确定性**：中注协备案接口可能尚未发布，需要预留接口但暂不实现具体对接逻辑
3. **电子签名法律效力**：Level 3 CA证书签名需要对接第三方CA机构，涉及法律合规问题，需要法务确认
4. **自定义模板安全性**：用户自定义模板可能存在安全风险，需要严格的验证和审核机制
5. **AI插件架构复杂度**：插件架构设计需要充分考虑隔离性、安全性和性能
6. **外部服务依赖风险**：Metabase和Paperless-ngx作为外部服务，增加了系统依赖和部署复杂度
7. **数据库分区迁移风险**：journal_entries表分区迁移需要平滑过渡，避免影响现有功能
8. **功能重叠冲突**：Metabase与Phase 4 AI功能、Paperless-ngx与Phase 3附件管理存在潜在重叠，需明确功能边界

## 成功标准

1. 系统能够支持至少3种会计准则（企业会计准则、小企业准则、IFRS）
2. 系统能够支持中英双语界面和报表输出
3. 系统能够支持至少3种审计类型（年度审计、IPO审计、专项审计）
4. 用户能够创建和使用自定义底稿模板
5. 系统能够支持Level 1和Level 2电子签名
6. 系统能够对接中注协备案接口（如接口可用）
7. 系统能够生成致同编码体系的底稿索引
8. 前端界面严格遵循致同GT品牌视觉规范
9. 附注模版包含完整的国企版和上市版配置
10. 系统能够使用T型账户法编制现金流量表
11. 系统具备AI插件架构，能够快速集成新的AI能力
12. 系统能够集成Metabase提供数据可视化看板
13. 系统能够集成Paperless-ngx管理附件文档，支持OCR识别和全文搜索
14. 系统能够优化账套数据联动查询，支持分区表、虚拟滚动、缓存策略
