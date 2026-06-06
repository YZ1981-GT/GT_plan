# 实施计划：审计报告交付件管理中心

## 概述

将设计转化为可增量交付的编码任务序列。任务严格按交付优先级分三批组织：**先 P0 核心闭环 → 再 P1 质量合规 → 后 P2 增强**。每批可独立执行交付，P0 完成即构成可用的最小闭环。

- 后端 Python（FastAPI + SQLAlchemy + Hypothesis PBT，`max_examples=5` 项目铁律）。
- 前端 TypeScript（Vue3 + Element Plus + fast-check + Vitest）。
- 三层一致铁律：迁移 DDL + ORM 模型 + service 三处必须同步增列。
- 标 `*` 的子任务为可选（测试/部署依赖项），核心实现任务不带 `*`。
- 每个主区域含「实现任务 + 对应 PBT/单元测试子任务」，PBT 子任务标注 Property 编号与所验证需求。

---

# 第一批：P0 核心闭环

> 范围：需求 1/2/3/4/5/21/22/23/24。Properties 1-15、37-50。
> 目标：选择性导出 → 双路径存储 → 中心页面 → 版本管理 → 预览 → 报告正文 JSON 主源 + 占位符映射 + 意见矩阵 + KAM。

- [x] 0. 环境准备：依赖安装
  - 在 `backend/requirements.txt` 增加 `docxtpl`（JSON→docx 渲染）；`pip install` 进 backend venv 并验证 `python -c "import docxtpl"` 可导入
  - 确认前端 `@vue-office/docx` / `@vue-office/pdf` 已装（预览复用），未装则补
  - _Requirements: 24.7, 5.2, 5.3_

- [x] 1. 数据库迁移 V059 与三层一致基线
  - [x] 1.1 编写 `V059__deliverable_center.sql` 与 `R059__deliverable_center_rollback.sql`
    - **先扫描 `backend/migrations/` 确认当前最高版本号**（已知 V057=editing_locks / V058=confirmations），确认 V059 未被占用再定版本号（铁律：撞号字母序靠后者静默丢失）
    - 在 `backend/migrations/`（MigrationRunner 扫描目录）创建 V059：对 `word_export_task`、`word_export_task_versions`、`audit_report` 全部 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`，含索引 `idx_wet_doc_subtype` / `idx_wetv_file_hash`
    - R059 对应 `DROP COLUMN IF EXISTS` / `DROP INDEX IF EXISTS`
    - 遵守铁律：CREATE/ALTER 必 IF NOT EXISTS，TimestampMixin 风格列显式 TIMESTAMPTZ，不使用 ALTER TYPE ADD VALUE
    - _Requirements: 2.2, 3.2, 13.1, 22.1, 24.2_
  - [x] 1.2 同步 ORM 模型增列（三层一致）
    - `phase13_models.py` 的 `WordExportTask` / `WordExportTaskVersion` 增列；`report_models.py` 的 `AuditReport` 增 `report_body_json` / `is_pie` / `prior_period_info`
    - **`word_export_task.opinion_type` / `company_type` 新列用 `VARCHAR` 不用 PG enum**，与 `audit_report` 既有 PG 枚举列脱钩（规避 ALTER TYPE 即用限制；5 类意见/soe 走应用层建模）；契约测试按 VARCHAR 校验
    - 列定义与 V059 DDL 严格对齐（类型、可空性、默认值）
    - _Requirements: 2.2, 13.1, 22.1, 23.1, 24.2, 26.1_
  - [x]* 1.3 编写迁移三层一致契约测试
    - 复用/扩展 `test_raw_sql_column_contract.py`，断言 DDL 列集合 == ORM 列集合
    - _Requirements: 2.2, 24.2_

- [x] 2. DeliverableService 列表/分组/筛选/搜索（中心页面后端）
  - [x] 2.1 创建 `DeliverableService(ExportTaskService)` 与 `DeliverableDTO`
    - 在 `backend/app/services/` 新建 `deliverable_service.py`，继承 `ExportTaskService`，保持原状态机方法不变
    - 实现 `list_deliverables(project_id, doc_type, status, date_from, date_to, keyword)`，组装含七字段的 `DeliverableDTO`（文件名/版本号/文档类型/导出者/导出时间/状态/文件大小）
    - service 只 flush 不 commit（铁律）
    - _Requirements: 3.1, 3.2, 3.4, 3.5_
  - [x]* 2.2 PBT：交付物分组分区性
    - **Property 6: 交付物分组分区性**
    - **Validates: Requirements 3.1**
  - [x]* 2.3 PBT：列表 DTO 字段完整性
    - **Property 7: 列表 DTO 字段完整性**
    - **Validates: Requirements 3.2**
  - [x]* 2.4 PBT：筛选结果子集且满足条件
    - **Property 9: 筛选结果子集且满足条件**
    - **Validates: Requirements 3.4, 9.2**
  - [x]* 2.5 PBT：关键字搜索相关性
    - **Property 10: 关键字搜索相关性**
    - **Validates: Requirements 3.5**

- [x] 3. 版本链与双路径存储（需求 4 / 需求 2）
  - [x] 3.1 实现版本链与版本创建
    - `get_version_chain(task_id)` 按创建时间倒序；`create_version(task_id, file_path, html_path, user_id, source_snapshot_refs)`，版本号 = max(version_no)+1 单调递增
    - `export_or_new_deliverable`：状态属于 {confirmed,signed,archived} 时新建独立交付物，否则追加版本
    - _Requirements: 4.1, 4.2, 4.4_
  - [x] 3.2 实现版本元信息对比
    - `compare_versions(task_id, a, b)`：返回导出时间/章节选择/文件大小差异，对称且 compare(a,a) 为空
    - _Requirements: 4.3_
  - [x] 3.3 实现 `render_and_store` 双路径存储与降级
    - 写平台存储 `storage/deliverables` + 记录元信息（含 selected_sections）；平台写入失败返回 `platform_persist_failed` 降级标志
    - _Requirements: 2.1, 2.2, 2.3_
  - [x]* 3.4 PBT：版本号单调递增
    - **Property 11: 版本号单调递增**
    - **Validates: Requirements 4.1, 6.4**
  - [x]* 3.5 PBT：历史版本不删除不变式
    - **Property 12: 历史版本不删除不变式**
    - **Validates: Requirements 4.2**
  - [x]* 3.6 PBT：版本对比对称性
    - **Property 13: 版本对比对称性**
    - **Validates: Requirements 4.3**
  - [x]* 3.7 PBT：终态再导出新建交付物
    - **Property 14: 终态再导出新建交付物**
    - **Validates: Requirements 4.4**
  - [x]* 3.8 PBT：状态机转换合法性
    - **Property 5: 状态机转换合法性**（扩展 VALID_STATUS_TRANSITIONS 后验证）
    - **Validates: Requirements 2.5, 7.1, 7.2, 7.3**
  - [x]* 3.9 单元测试：双路径降级边界
    - 平台写失败仍返回 blob（2.3）、下载被阻止仍留存（2.4）
    - _Requirements: 2.3, 2.4_
  - [x]* 3.10 PBT：双路径存储原子记录
    - **Property 4: 双路径存储原子记录**（成功导出后平台存在文件且版本记录含完整元信息）
    - **Validates: Requirements 2.1, 2.2**
  - [x]* 3.11 PBT：版本链时间倒序
    - **Property 8: 版本链时间倒序**
    - **Validates: Requirements 3.3**

- [x] 4. ReportBodyService 与占位符映射注册表（报告正文 JSON 主源核心）
  - [x] 4.1 新建占位符映射注册表种子
    - 创建 `backend/data/placeholder_mapping_registry.json`（auto/financial/manual 三类），运行时加载为字典，新增占位符无需改渲染逻辑
    - _Requirements: 24.3, 24.4, 24.8_
  - [x] 4.2 补充审计意见模板矩阵种子
    - 扩充 `backend/data/audit_report_templates_seed.json`：各非无保留意见补「形成X意见的基础」段、`emphasis` 强调事项段、`other_matter` 其他事项段；由 `AuditReportService.load_seed_templates` 幂等加载
    - _Requirements: 22.3, 22.4, 26.2_
  - [x] 4.3 实现 `ReportBodyService` 模板加载与占位符填充
    - 新建 `backend/app/services/report_body_service.py`：`load_body_template(opinion_type, company_type)` 组装 Report_Body_JSON；`fill_placeholders` 填充 auto + financial 类，manual 类保留提示文本；`unqualified_with_emphasis` 在 unqualified 基础上附加可删 emphasis 段
    - _Requirements: 22.1, 22.2, 22.3, 22.5, 24.1, 24.3, 24.4, 24.5_
  - [x] 4.4 实现 KAM 处理与校验
    - KAM 段多条目数组（matter + response）；`validate_kam`：listed 或 is_pie 且非 disclaimer → 必填非空；disclaimer → 不含 KAM 段
    - _Requirements: 23.1, 23.2, 23.3, 23.5_
  - [x] 4.5 实现 HTML/docx 渲染
    - `render_html` 供预览；`render_docx`（docxtpl，新增依赖写入 `backend/requirements.txt`）供交付；渲染-解析往返保段落结构
    - _Requirements: 24.7_
  - [x]* 4.6 PBT：意见×公司类型模板加载矩阵
    - **Property 38: 意见×公司类型模板加载矩阵**
    - **Validates: Requirements 22.1, 22.2, 22.5, 24.1**
  - [x]* 4.7 PBT：强调意见模板结构
    - **Property 39: 强调意见模板结构**
    - **Validates: Requirements 22.3**
  - [x]* 4.8 PBT：非无保留意见含形成基础段
    - **Property 40: 非无保留意见含形成基础段**
    - **Validates: Requirements 22.4**
  - [x]* 4.9 PBT：可选段落增删往返
    - **Property 41: 可选段落增删往返**
    - **Validates: Requirements 22.6**
  - [x]* 4.10 PBT：KAM 必填判定
    - **Property 42: KAM 必填判定**
    - **Validates: Requirements 23.1, 23.2, 23.3**
  - [x]* 4.11 PBT：KAM 必填定稿守卫
    - **Property 43: KAM 必填定稿守卫**（沿用 `AuditReportService._validate_finalize`）
    - **Validates: Requirements 23.4**
  - [x]* 4.12 PBT：KAM 多条目结构
    - **Property 44: KAM 多条目结构**
    - **Validates: Requirements 23.5**
  - [x]* 4.13 PBT：自动映射占位符填充
    - **Property 45: 自动映射占位符填充**
    - **Validates: Requirements 24.3**
  - [x]* 4.14 PBT：财务占位符映射正确
    - **Property 46: 财务占位符映射正确**
    - **Validates: Requirements 24.4**
  - [x]* 4.15 PBT：手工占位符保留
    - **Property 47: 手工占位符保留**
    - **Validates: Requirements 24.5**
  - [x]* 4.16 PBT：正文生成渲染往返
    - **Property 49: 正文生成渲染往返**（结构等价：往返后段落数量与 section_id 集合一致，不要求样式无损）
    - **Validates: Requirements 24.7**
  - [x]* 4.17 PBT：占位符注册表可扩展
    - **Property 50: 占位符注册表可扩展**
    - **Validates: Requirements 24.8**

- [x] 5. 财务占位符随源刷新（Event_Linkage 接入）
  - [x] 5.1 接入 REPORTS_UPDATED 事件刷新
    - `ReportBodyService.refresh_financial_placeholders`，在 `event_handlers.py` 的 REPORTS_UPDATED → AuditReportService.on_reports_updated 链路中调用，仅刷新财务数据类占位符
    - _Requirements: 24.6_
  - [x]* 5.2 PBT：财务占位符随源刷新
    - **Property 48: 财务占位符随源刷新**
    - **Validates: Requirements 24.6**

- [x] 6. deliverable.py 路由（P0 端点）与注册
  - [x] 6.1 创建路由并注册
    - 新建 `backend/app/routers/deliverable.py`，`prefix="/api/projects/{project_id}/deliverables"`；在 `router_registry/report.py` 的 `register_report_routers` 注册（铁律：不注册即 404）
    - P0 端点：`GET /`、`GET /{task_id}/versions`、`POST /{task_id}/versions/compare`、`GET /{task_id}/versions/{version_no}/download`、`GET /{task_id}/versions/{version_no}/preview-url`、`POST /report-body/load-template`、`POST /report-body/render`、`GET /report-body/preview-html`
    - 校验 `task.project_id == path project_id` 防越权；router 统一 commit/rollback
    - _Requirements: 2.1, 3.1, 3.6, 4.1, 4.3, 5.1, 24.1, 24.7_
  - [x] 6.2 实现预览 URL 与不支持格式降级
    - docx 直读 / pdf 复用 `office_preview` 转换降级；后缀非 {.docx,.pdf} 返回降级提示 + 下载链接
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [x]* 6.3 PBT：不支持格式降级提示
    - **Property 15: 不支持格式降级提示**
    - **Validates: Requirements 5.4**
  - [x]* 6.4 单元测试：docx/pdf 预览端点
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 7. 前端交付中心页面与导出弹窗（P0）
  - [x] 7.1 新增路由、视图与 API 命名空间
    - `DeliverableCenter.vue`（路由 `/projects/:projectId/deliverable-center`）；`apiPaths/report.ts` 新增 `deliverables` 命名空间，走 `apiProxy`（自动解信封）
    - _Requirements: 3.1_
  - [x] 7.2 实现分组列表、筛选、搜索、版本链组件
    - `DeliverableGroupList.vue` / `DeliverableRow.vue` / `DeliverableVersionList.vue` / `DeliverableActions.vue` / `DeliverableToolbar.vue`；版本链按时间倒序展开、下载按钮
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - [x] 7.3 实现选择性导出弹窗与文档结构树
    - `DeliverableExportDialog.vue`（复用 ExportDialog 骨架）+ `DocStructureTree.vue`：默认全选、父子联动、空选禁用确认、按文档类型展示不同结构（含附注层级）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 18.3_
  - [x] 7.4 实现在线预览组件
    - `DeliverablePreview.vue` 复用 `@vue-office/docx` + `@vue-office/pdf`，加载指示器，不支持格式显示提示 + 下载链接
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [x] 7.5 实现三处一致生成入口
    - `GenerateEntryGroup.vue`：报表（复用 generateReports）/附注/报告正文三处入口，统一前置检查、进度反馈、结果提示
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7_
  - [x]* 7.6 前端 PBT（fast-check）：导出弹窗默认全选
    - **Property 2: 导出弹窗默认全选**
    - **Validates: Requirements 1.2**
  - [x]* 7.7 前端 PBT（fast-check）：附注层级选择联动
    - **Property 3: 附注层级选择联动**
    - **Validates: Requirements 1.6**
  - [x]* 7.8 前端 PBT（fast-check）：选择性导出投影一致性
    - **Property 1: 选择性导出投影一致性**
    - **Validates: Requirements 1.3, 18.3**
  - [x]* 7.9 单元测试：空选禁用确认、生成入口存在
    - _Requirements: 1.4, 21.1, 21.2, 21.3_
  - [x]* 7.10 PBT：生成前置数据就绪守卫
    - **Property 37: 生成前置数据就绪守卫**（底层数据未就绪时生成被阻止并给出前置检查提示）
    - **Validates: Requirements 21.4**

- [x] 8. P0 检查点
  - 确保 P0 全部测试通过（迁移契约 + 后端 service PBT + 前端 fast-check）；如有疑问询问用户。此时核心闭环（选择性导出→双路径存储→中心页面→版本→预览→报告正文生成）应可端到端运行。

---

# 第二批：P1 质量与合规

> 范围：需求 8/13/19/14/17/25/28/29。Properties 18-19、27-30、34、51、54-55。
> 目标：完整性 + 一致性、快照溯源、签章 EQCR、权限矩阵、报告日期合规、OnlyOffice 降级与回调鉴权。

- [ ] 9. DeliverableSnapshotService 统一快照封装（需求 13/19）
  - [ ] 9.1 实现统一快照引用与三件套一致性校验
    - 新建 `backend/app/services/deliverable_snapshot_service.py`：`capture_snapshot_ref(project_id, year, doc_type)` 复用 `report_snapshot_service`，三类统一回退到 trial_balance MD5 哈希；`check_trio_consistency` 校验同一 tb_hash
    - **前置验证**：确认 `disclosure_note` 表能取到对齐用的 tb_hash（附注无 `bound_dataset_id` 字段，那是 audit_report 的字段）；若附注无直接快照字段，则统一以 trial_balance MD5 为三类对齐基准（设计已论证可行，此处编码时落实）
    - 在 `render_and_store` 时写入版本 `source_snapshot_refs`
    - _Requirements: 13.1, 13.2, 13.3, 19.1, 19.2_
  - [ ] 9.2 实现数据过时（stale）检测端点
    - `GET /{task_id}/snapshot-stale`：对比绑定快照哈希与当前底层数据哈希
    - _Requirements: 13.4, 13.5, 16.2_
  - [ ]* 9.3 PBT：快照绑定完整性
    - **Property 27: 快照绑定完整性**
    - **Validates: Requirements 13.1, 13.2, 19.1**
  - [ ]* 9.4 PBT：数据过时检测正确性
    - **Property 28: 数据过时检测正确性**
    - **Validates: Requirements 13.4, 13.5, 16.2**

- [ ] 10. CompletenessService 完整性 + 一致性（需求 8/19）
  - [ ] 10.1 实现齐全性 + 一致性合并校验
    - 新建 `backend/app/services/completeness_service.py`：`check(project_id, year)` = 齐全性（三件套，至少含 BS+IS）AND 至少一类 confirmed AND 三件套一致性；`required_doc_types(project_type)` 可配置必需件清单
    - `GET /completeness` 端点
    - _Requirements: 8.1, 8.2, 8.3, 19.2, 19.3, 19.4_
  - [ ]* 10.2 PBT：三件套齐全性判定
    - **Property 18: 三件套齐全性判定**
    - **Validates: Requirements 8.1, 8.2, 18.4**
  - [ ]* 10.3 PBT：完整性通过判定
    - **Property 19: 完整性通过判定**
    - **Validates: Requirements 8.3, 19.4**
  - [ ]* 10.4 前端：CompletenessBanner 顶部状态条
    - `CompletenessBanner.vue` 显示齐全性/一致性状态与缺失/不一致警告
    - _Requirements: 3.7, 8.2, 19.3_

- [ ] 11. 签章与 EQCR 守卫（需求 14）
  - [ ] 11.1 实现 EQCR 前置校验与签章字段记录
    - `DeliverableService.sign(task_id, signer_id, sign_type)`：confirmed→signed，转 confirmed 前校验项目 EQCR 已通过，记录 signed_by/signed_at/sign_type；`POST /{task_id}/sign` 端点
    - EQCR 复核角色对交付物仅只读
    - _Requirements: 14.1, 14.2, 14.3, 14.4_
  - [ ]* 11.2 PBT：EQCR 守卫
    - **Property 29: EQCR 守卫**
    - **Validates: Requirements 14.1, 14.2**
  - [ ]* 11.3 PBT：签章字段完整性
    - **Property 30: 签章字段完整性**
    - **Validates: Requirements 14.3**

- [ ] 12. 权限矩阵（需求 17）
  - [ ] 12.1 实现权限矩阵授权判定
    - 新建权限判定模块（如 `deliverable_permissions.py`）：按 (角色, 操作, 状态) 判定导出/预览/编辑/审批/归档/解除归档；EQCR 复核角色对写操作全拒、仅读；在路由依赖中接入
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7_
  - [ ]* 12.2 PBT：权限矩阵授权一致性
    - **Property 34: 权限矩阵授权一致性**
    - **Validates: Requirements 14.4, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7**

- [ ] 13. 报告日期合规校验（需求 25）
  - [ ] 13.1 实现报告日期下界校验
    - 在 `ReportBodyService` 或独立校验器实现 `Report_Date_Compliance`：报告日期不早于 max(审计证据完成日, 财表/治理层批准日, EQCR 通过日)，不合规返回告警要求确认（非硬阻断）
    - _Requirements: 25.1, 25.2, 25.3, 25.4_
  - [ ]* 13.2 PBT：报告日期下界合规
    - **Property 51: 报告日期下界合规**
    - **Validates: Requirements 25.1, 25.2, 25.3**

- [ ] 14. OnlyOffice 降级与 callback 鉴权（需求 28/29，P1 安全刚需）
  - [ ] 14.1 实现 OnlyOfficeCallbackService 健康检查与 JWT 校验
    - 新建 `backend/app/services/onlyoffice_callback_service.py`：`health_check()` 探测 OnlyOffice `/healthcheck`；`verify_callback_jwt(token, body)` 校验签名，失败写安全日志并拒绝（401）
    - **在 `backend/app/config.py` 的 Settings 类注册 `ONLYOFFICE_SERVER_URL` / `ONLYOFFICE_JWT_SECRET` / `ONLYOFFICE_CALLBACK_BASE` 三项**，`.env` 同步；密钥缺失时 OnlyOffice 集成整体禁用并降级只读
    - `GET /onlyoffice/health`、`POST /onlyoffice/callback/{task_id}`（仅 JWT 通过且 status==2 时创建新版本）端点
    - _Requirements: 28.1, 28.2, 28.3, 29.1, 29.2, 29.3_
  - [ ]* 14.2 PBT：OnlyOffice 不可用降级
    - **Property 54: OnlyOffice 不可用降级**
    - **Validates: Requirements 28.1**
  - [ ]* 14.3 PBT：callback JWT 鉴权
    - **Property 55: callback JWT 鉴权**
    - **Validates: Requirements 29.1, 29.2, 29.3**
  - [ ]* 14.4 单元测试：OnlyOffice 不可用核心功能可用
    - 健康检查失败时预览/下载/版本端点仍正常响应
    - _Requirements: 28.2, 28.3_

- [ ] 15. P1 检查点
  - 确保 P1 全部测试通过（快照/完整性/EQCR/权限/日期/callback 鉴权）；如有疑问询问用户。安全要点：callback JWT 校验必须先于 P2 在线编辑落地。

---

# 第三批：P2 增强

> 范围：需求 6/7/10/30/11/12/15/16/9/18/20/26/27。Properties 16-17、20-26、31-33、35-36、39-44(已属 P0)、52-53、56。
> 说明：OnlyOffice 在线编辑（需求 6）依赖 Docker 部署 OnlyOffice Document Server，相关任务标 `*` 为部署依赖可选。

- [ ] 16. 审批流（需求 7）
  - [ ] 16.1 实现审批状态流转与端点
    - `DeliverableService.submit_for_approval/approve/reject`：editing→pending_approval→confirmed/退回 editing，记录 approval_by/approval_at/reject_reason；`POST /{task_id}/submit-approval` `/approve` `/reject` 端点；扩展 VALID_STATUS_TRANSITIONS 含 pending_approval
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 16.2 前端审批面板
    - `ApprovalPanel.vue`：状态栏显示审批进度与审批人；站内消息通知（复用现有通知机制）
    - _Requirements: 7.4, 7.5_
  - [ ]* 16.3 单元测试：审批流转与驳回留痕
    - _Requirements: 7.1, 7.2, 7.3_

- [ ] 17. 归档锁定与项目生命周期联动（需求 11/27）
  - [ ] 17.1 实现项目级归档与解除归档
    - `archive_project_deliverables`：confirmed/signed → archived，归档前执行完整性检查（不通过阻止/确认）；`unarchive` 仅 admin，写 archive_unarchive 审计日志；项目归档级联、全归档反映项目阶段完结
    - `POST /archive`、`POST /{task_id}/unarchive` 端点
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 27.1, 27.2, 27.3_
  - [ ]* 17.2 PBT：不齐全则归档被阻止
    - **Property 20: 不齐全则归档被阻止**
    - **Validates: Requirements 8.4, 11.3**
  - [ ]* 17.3 PBT：项目归档级联状态一致性
    - **Property 23: 项目归档级联状态一致性**
    - **Validates: Requirements 11.1, 27.1, 27.3**
  - [ ]* 17.4 PBT：归档锁定不变式
    - **Property 24: 归档锁定不变式**
    - **Validates: Requirements 11.2**
  - [ ]* 17.5 PBT：解除归档权限与留痕
    - **Property 25: 解除归档权限与留痕**
    - **Validates: Requirements 11.4**
  - [ ]* 17.6 PBT：项目阶段聚合完结
    - **Property 53: 项目阶段聚合完结**
    - **Validates: Requirements 27.2**

- [ ] 18. 哈希链防篡改与在线编辑回写边界（需求 15/16）
  - [ ] 18.1 实现版本哈希链写入与完整性校验
    - 复用 `audit_log_helper` 哈希链：版本创建时计算文件 SHA256 写入 `file_hash` + `hash_chain_entry_id`，prev_hash 链接；`GET /{task_id}/integrity-verify` 端点返回校验结果与被篡改版本号
    - _Requirements: 15.1, 15.2, 15.3, 15.4_
  - [ ] 18.2 保证在线编辑源数据隔离
    - 编辑回写仅修改交付物副本，源附注/报表/audit_report 数据不变
    - _Requirements: 16.1, 16.2, 16.3_
  - [ ]* 18.3 PBT：哈希链绑定与连续性
    - **Property 31: 哈希链绑定与连续性**
    - **Validates: Requirements 15.1, 15.4**
  - [ ]* 18.4 PBT：篡改检测正确性
    - **Property 32: 篡改检测正确性**
    - **Validates: Requirements 15.2, 15.3**
  - [ ]* 18.5 PBT：在线编辑源数据隔离
    - **Property 33: 在线编辑源数据隔离**
    - **Validates: Requirements 16.1**

- [ ] 19. 交付物水印（需求 12）
  - [ ] 19.1 实现草稿水印
    - 预览叠加 `DraftWatermark.vue`（draft/editing）；下载文件 python-docx 后处理嵌入水印；confirmed/signed 生成无水印
    - _Requirements: 12.1, 12.2, 12.3_
  - [ ]* 19.2 PBT：水印当且仅当草稿态
    - **Property 26: 水印当且仅当草稿态**
    - **Validates: Requirements 12.1, 12.2, 12.3**

- [ ] 20. 打包下载异步化与进度（需求 10/30）
  - [ ] 20.1 实现异步打包
    - 复用 `ExportJobService` 异步打包各类最新 confirmed 版本为 ZIP，按 doc_type 建子目录 + `deliverable_manifest.txt` 清单；不完整警告允许继续；SSE（复用 `event_bus.broadcast_raw`）推送进度
    - `POST /package` 端点返回 job + 下载链接
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 30.1, 30.2, 30.3_
  - [ ]* 20.2 PBT：打包内容为各类最新 confirmed 版本
    - **Property 21: 打包内容为各类最新 confirmed 版本**
    - **Validates: Requirements 10.1**
  - [ ]* 20.3 PBT：打包结构与清单完整
    - **Property 22: 打包结构与清单完整**
    - **Validates: Requirements 10.3, 10.4**
  - [ ]* 20.4 PBT：打包进度单调递增
    - **Property 56: 打包进度单调递增**
    - **Validates: Requirements 30.2**

- [ ]* 21. OnlyOffice 在线编辑（需求 6，依赖 Docker 部署 OnlyOffice Document Server）
  - [ ]* 21.1 实现编辑配置与 callback 回写新版本
    - `OnlyOfficeCallbackService.build_editor_config`（document/editorConfig + 签发 JWT）；`handle_callback` status==2 下载编辑后文件创建新版本 + 哈希链；docx→Document Editor / xlsx→Spreadsheet Editor；confirmed/signed/archived 只读
    - `GET /onlyoffice/config/{task_id}/{version_no}` 端点
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  - [ ]* 21.2 前端 OnlyOfficeEditor 组件与降级
    - `OnlyOfficeEditor.vue` 嵌入编辑器，OnlyOffice 不可用时降级 `DeliverablePreview`
    - _Requirements: 6.1, 6.5, 6.6, 28.1_
  - [ ]* 21.3 PBT：编辑器模式由状态决定
    - **Property 16: 编辑器模式由状态决定**
    - **Validates: Requirements 6.5, 6.6**
  - [ ]* 21.4 PBT：编辑器类型由扩展名决定
    - **Property 17: 编辑器类型由扩展名决定**
    - **Validates: Requirements 6.2**

- [ ] 22. doc_type 可扩展与专项报告 + A 循环关联 + 上期比较（需求 20/9/18/26）
  - [ ] 22.1 实现 doc_type 可扩展通用管理与专项必需件清单
    - doc_type 以可扩展枚举/配置定义（不硬编码）；`required_doc_types` 按项目类型返回清单（标准三件套 / 专项）；新增专项类型无需改核心逻辑
    - _Requirements: 18.1, 18.2, 18.4, 20.1, 20.2, 20.3, 20.4_
  - [ ] 22.2 实现 A 循环关联入口
    - A 循环底稿侧边导航交付物快捷入口，自动筛选当前项目交付物，阶段概览显示完整性摘要，状态变更同步阶段进度
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - [ ] 22.3 实现上期比较其他事项段
    - 上期比较三情形（本所前期/前任注师/上期未审）措辞，首次委托情形含「其他事项段」
    - _Requirements: 26.1, 26.2, 26.3_
  - [ ]* 22.4 PBT：doc_type 可扩展通用管理
    - **Property 35: doc_type 可扩展通用管理**
    - **Validates: Requirements 20.1, 20.2**
  - [ ]* 22.5 PBT：必需件清单由项目类型决定
    - **Property 36: 必需件清单由项目类型决定**
    - **Validates: Requirements 20.3, 20.4**
  - [ ]* 22.6 PBT：首次委托其他事项段
    - **Property 52: 首次委托其他事项段**
    - **Validates: Requirements 26.2**

---

# 收尾：迁移一致性验证与端到端

- [ ] 23. 迁移 + 三层一致性最终验证
  - 应用 V059 迁移后运行 `test_raw_sql_column_contract.py` 与 `test_raw_sql_schema_contract.py`，校验迁移 DDL + ORM 模型 + service 三层完全一致；运行后端全量 `python -m pytest backend/tests/ -v --tb=short`（用 `;` 连接、`rtk` 前缀）
  - _Requirements: 2.2, 22.1, 24.2_

- [ ]* 24. Playwright 端到端实测（needs-env：需运行中后端 9980 + 前端 3030）
  - 实测交付中心页面、选择性导出弹窗、预览、报告正文生成、版本链、审批面板关键交互（getDiagnostics 过 ≠ 运行时无错）；中文全链路不崩
  - _Requirements: 1.1, 3.1, 5.1, 21.1, 24.7_

- [ ] 25. 最终检查点
  - 确保所有批次测试通过；如有疑问询问用户。

## 说明

- 标 `*` 的子任务为可选（测试 / 部署依赖项），可为加速 MVP 跳过；顶层任务不带 `*`。
- 任务 21（OnlyOffice 在线编辑）整体可选，依赖 Docker 部署 OnlyOffice Document Server；其安全前置（callback JWT 鉴权，任务 14）已在 P1 先行落地。
- 每个任务引用具体需求条款与 Property 编号以保证可追溯。
- 后端 PBT 用 Hypothesis（`max_examples=5` 铁律），前端用 fast-check + Vitest。
- 三层一致铁律贯穿任务 1（迁移）→ 任务 23（最终验证）。
- 人工验收项（不纳入自动化）：5.5、6.7、7.4、9.4、16.3、21.5/21.6/21.7、13.3、18.1/18.2、24.2、25.4、26.3。
