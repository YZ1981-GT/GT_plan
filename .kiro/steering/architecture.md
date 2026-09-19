---
inclusion: manual
---

# 项目架构参考

需要了解项目结构、文件清单、技术栈时用 `#architecture` 引用此文件。

## 技术栈

- 后端：FastAPI + SQLAlchemy 2.0 异步 + PostgreSQL 16 + Redis 7 + migration_runner.py（V*.sql 版本化迁移，替代 Alembic）
- 前端：Vue 3 + TypeScript + Element Plus + Vite，入口 `audit-platform/frontend/`（端口 3030）
- 在线编辑：Univer（纯前端，@univerjs/presets）替代 ONLYOFFICE，WOPI 端点保留向后兼容
- LLM：本地 vLLM Qwen3.5-27B-NVFP4（端口 8100，OpenAI 兼容 API）
- OCR：Tesseract + MinerU（GPU 加速）+ PaddleOCR
- 文件存储：本地磁盘 storage/ + Paperless-ngx（OCR/检索）+ 云端归档（S3/SFTP/SMB）

## 系统规模（2026-05-18 实测）

- 后端路由文件：**202** 个（router_registry.py 11 个业务域分组）
- 后端服务文件：**325** 个（含子目录 import_engine/、wp_scripts/、ledger_import/ 等）
- 后端模型文件：**56** 个，PG ~**188** 张表
- 后端 Alembic 迁移：**59** 个版本文件
- 后端 Worker：**10** 个（audit_log_writer / budget_alert / dataset_purge / import_recover / import / outbox_replay / qc_rating / reviewer_metrics / sla / staged_orphan_cleaner）
- 后端测试：**282** 个测试文件
- 后端中间件：9 个（audit_log/audit_log_middleware/auth_middleware/body_limit/error_handler/observability/rate_limiter/request_id/response）
- 后端核心模块：11 个（core/）
- V*.sql 迁移脚本：3 个（V001__init / V002__add_schema_version / V003__example_add_comment）
- 前端页面：**96** 个 Vue 视图（views/ 含子目录）
- 前端组件：**280** 个（components/ 含所有子目录）
- 前端 common 组件：**28** 个
- 前端 composables：**51** 个
- 前端 stores：**9** 个（auth/project/collaboration/roleContext/wizard/dict/displayPrefs/drilldown/addressRegistry）
- 前端 services：**30** 个文件（含 apiPaths.ts 1558 行）
- 前端 utils：**23** 个文件
- 底稿模板：**473** 个（xlsx + docx）
- 底稿精细化规则：**347** 个 JSON
- 底稿模板索引：**363** 条（gt_template_library.json）
- 底稿科目映射：**206** 条（wp_account_mapping.json v2025-R5）

## 前端全局组件库（2026-05-18 更新）

### Composables（composables/）— 51 个
| 文件 | 功能 | 接入模块数 |
|------|------|-----------|
| useFullscreen | 全屏切换+ESC退出 | 17（13 worksheet + 4 views） |
| useCellSelection | 单击/Ctrl多选/Shift范围选/鼠标拖拽框选/右键保持选区/selectionStats | 5 核心模块 |
| useCellComments | 单元格批注/复核标记 CRUD | 6 模块 |
| useLazyEdit | 按需渲染编辑控件（大表格性能） | 3 模块 |
| useProjectSelector | 项目/年度选择器（旧版，新版用 useProjectStore） | 保留兼容 |
| useWorkflowGuide | 工作流引导提示 | 8 个预定义引导 |
| useTableSearch | 表格内搜索替换(Ctrl+F) | 3 模块 |
| useEditMode | 查看/编辑模式切换+未保存提示+路由拦截 | 全模块 |
| useExcelIO | 统一 Excel 导入导出 | 14 worksheet |
| useTableToolbar | 通用表格工具栏逻辑 | 多模块 |
| useCopyPaste | 表格复制粘贴 | TrialBalance + ReportView + GtEditableTable |
| useKnowledge | 全局知识库调用 | DisclosureEditor + AuditReportEditor |
| useAutoSave | 自动保存/草稿恢复 | 3 模块 |
| useLoading | withLoading 包装 + NProgress | 全局 |
| usePermission | 按钮级权限控制 | 全局 |
| useKeyboardNav | Tab 键盘导航+批量粘贴 | GtEditableTable |

### Stores（stores/）— 9 个
| 文件 | 功能 | 状态 |
|------|------|------|
| auth | JWT认证+刷新 | 全局 |
| displayPrefs | 金额单位/字号/小数位/零值/负数红色/变动高亮 | 5 核心模块接入 |
| roleContext | 角色上下文 | 全局 |
| drilldown | 穿透导航 | 穿透页面 |
| wizard | 项目向导 | 向导页面 |
| collaboration | 协作 | 协作模块 |
| project | 项目上下文（projectId/year/standard） | 全局（路由自动同步） |
| dict | 枚举字典（后端 /api/system/dicts） | 全局（sessionStorage 缓存） |
| addressRegistry | 地址坐标全局注册表 | CellSelector/FormulaRefPicker |

### Common Components（components/common/）— 28 个
| 文件 | 功能 |
|------|------|
| CellContextMenu | 右键菜单+全局选中样式 |
| SelectionBar | 选中区域求和状态栏 |
| TableSearchBar | 搜索栏UI(致同品牌紫色) |
| CommentTooltip | 批注hover气泡 |
| CommentThread | 批注线程（回复链） |
| LoadingState | 骨架屏+空状态+错误 |
| VirtualScrollTable | 虚拟滚动表格 |
| ValidationList | 校验结果展示 |
| OperationFeedback | 进度+通知 |
| GtToolbar | 标准工具栏（导出/导入/全屏/公式/模板/编辑切换） |
| GtPageHeader | 通用页面横幅（紫色渐变） |
| GtInfoBar | 信息栏（单位/年度/模板选择+徽章） |
| GtAmountCell | 金额单元格（displayPrefs+可点击+hover高亮） |
| GtStatusTag | 状态标签（配合statusMaps.ts） |
| GtEditableTable | 高阶可编辑表格（内置选中/拖拽/右键/批注/增删行/全屏/懒加载/小计/键盘导航/分组折叠/打印） |
| GtPrintPreview | 打印预览弹窗 |
| GtConsolWizard | 合并模块向导式步骤条 |
| SyncStatusIndicator | SSE 同步状态指示器 |
| ExcelImportPreviewDialog | 通用导入预览弹窗 |
| KnowledgePickerDialog | 知识库文档选择器 |
| SharedTemplatePicker | 共享模板选择器（8 configType） |

### Utils（utils/）— 23 个文件
| 文件 | 功能 | 状态 |
|------|------|------|
| formatters.ts | 金额/日期/百分比格式化+单位换算 | 5核心+14worksheet |
| http.ts | HTTP客户端+401刷新+去重+重试+POST防重复 | 全局 |
| sse.ts | SSE封装+自动重连 | 全局接入（ThreeColumnLayout） |
| shortcuts.ts | 快捷键管理(13个) | 全模块接入 |
| operationHistory.ts | 撤销功能 | Adjustments + RecycleBin |
| eventBus.ts | mitt 类型安全事件总线 | 全局 |
| confirm.ts | 语义化确认弹窗 | 全局 |
| statusMaps.ts | 状态标签映射 | 全局 |
| monitor.ts | 性能监控（Web Vitals + 请求日志） | 全局 |
| queryClient.ts | TanStack Query 客户端配置 | 全局 |
| importValidation.ts + 相关 | 统一导入流程工具（5个文件） | 导入模块 |
| webVitals.ts | Web Vitals 上报 | 全局 |

### Services（services/）— 30 个文件
- apiPaths.ts — API 路径集中管理（1558 行，40+ 业务域）
- apiProxy.ts — 统一 API 代理（所有 view/component 通过此访问）
- auditPlatformApi.ts、consolidationApi.ts、workpaperApi.ts 等 28 个业务 API 文件

### 后端基础设施（core/）— 12 个模块
| 文件 | 功能 | 状态 |
|------|------|------|
| core/pagination.py | PaginationParams/SortParams 统一分页排序 | 5 高频 API |
| core/bulk_operations.py | BulkOperationMixin 批量操作 | RecycleBin/Adjustments/ReviewInbox |
| core/audit_decorator.py | @audit_log 审计日志装饰器 | 删除/审批/状态变更 |
| core/migration_runner.py | 数据库版本化迁移（V*.sql 脚本） | 启动时自动执行，3 个迁移文件 |
| core/database.py | 异步 SQLAlchemy 配置 + 连接池 | 全局 |
| core/security.py | JWT 认证 + 权限 | 全局 |
| core/redis.py | Redis 连接管理 | 全局 |
| core/container.py | 依赖注入容器 | 全局 |

### 后端 Worker（workers/）— 10 个
| 文件 | 功能 |
|------|------|
| sla_worker | SLA 超时检测 |
| import_worker | 账表导入主 Worker |
| import_recover_worker | 导入中断恢复 |
| outbox_replay_worker | 事件 outbox 重放 |
| dataset_purge_worker | superseded 数据集清理 |
| staged_orphan_cleaner | 孤立 staged 数据清理 |
| audit_log_writer_worker | 审计日志异步写入 |
| budget_alert_worker | 预算预警 |
| qc_rating_worker | QC 评分计算 |
| reviewer_metrics_worker | 复核人指标统计 |

## 11 个业务域（router_registry.py）

1. 基础设施 — 认证/健康检查/WOPI
2. 项目与向导 — 建项/科目导入/映射/数据集版本
3. 查账与试算 — 四表穿透/试算表/调整分录/重要性/错报/事件总线
4. 报表与附注 — 6 张报表/附注生成校验/审计报告/Word 导出/国企上市转换
5. 底稿管理 — 模板/QC/复核/预填充/精细化规则/公式/四式联动/账龄/依赖（最大域，27 路由）
6. 合并报表 — 差额表/内部交易/商誉/外币/少数股东（11 路由，前端全部完成）
7. 团队与看板 — 人员库/委派/工时/四种角色看板/程序裁剪
8. 系统管理 — 知识库/模板库/回收站/AI 插件/监管/签名/性能监控（24 路由）
9. 门禁与治理（Phase 14）— 统一门禁引擎/操作留痕/职责分离
10. 任务树与编排（Phase 15）— 四级任务树/事件总线/问题单
11. 取证与版本链（Phase 16）— 版本戳/离线冲突/一致性复算/导出完整性

## 核心架构模式

- 事件驱动联动：EventBus（debounce 500ms）串联 调整→试算表→报表→附注→底稿
- 四式联动：Excel + HTML + Word + structure.json（权威数据源）
- 三层模板体系：事务所默认→集团定制→项目级应用
- 数据集版本治理：LedgerDataset staged→active→superseded，支持回滚
- 企业级门禁：gate_engine 统一评估 + QC 28 条规则 + SoD 职责分离
- 附注校验公式继承：上市版默认继承国企版全部公式，差异公式按 id 替换，标记"—"的排除，特有科目（FS/FK/FO）追加
- 权限三级：readonly/edit/review + Redis 缓存 + 降级策略
- 中间件栈（从外到内，LIFO 注册顺序）：CORSMiddleware→RequestBodyLimitMiddleware→GZipMiddleware→ObservabilityMiddleware→ResponseWrapperMiddleware→RequestIDMiddleware→LLMRateLimitMiddleware→AuditLogMiddleware

## 关键环境配置

- Git 远程：https://github.com/YZ1981-GT/GT_plan.git（master 分支）
- 后端端口：9980，前端端口：3030，vLLM：8100，Paperless：8010，Redis：6379，PG：5432
- 初始化数据库：`python backend/scripts/init_tables.py`（自动扫描 models + create_all + 种子数据）+ `python backend/scripts/create_admin.py`（admin/admin123）
- 数据库迁移：启动时 migration_runner.py 自动扫描 backend/migrations/V*.sql 执行未应用版本
- 启动开发：`start-dev.bat` 或 `uvicorn app.main:app --host 0.0.0.0 --port 9980 --reload --reload-dir app`（从 backend/ 目录）
- vLLM 启动：`docker compose --profile gpu up vllm`
- 文件上传限制：MAX_UPLOAD_SIZE_MB=800 / MAX_REQUEST_BODY_MB=850

## 关键数据文件

- `backend/data/report_config_seed.json` — 报表行次种子（4 套 × 6 张报表，1191 行）
- `backend/data/note_template_soe.json` — 国企版附注模板（14 章 170 节）
- `backend/data/note_template_listed.json` — 上市版附注模板（17 章 185 节）
- `backend/data/wp_account_mapping.json` — 底稿科目映射（206 条 v2025-R5）
- `backend/data/wp_fine_rules/` — 347 个底稿精细化规则 JSON
- `backend/data/wp_system_map.json` — 底稿体系全景图（四阶段递进+11个业务循环关联）
- `backend/data/gt_template_library.json` — 363 条底稿模板索引
- `backend/data/standard_account_chart.json` — 标准科目表（166 个）

## 开发阶段状态（全部 ✅ 完成）

| 阶段 | 名称 | 状态 |
|------|------|------|
| Phase 0 | 基础设施 | ✅ |
| Phase 1a/1b/1c | MVP Core/Report/Workpaper | ✅ |
| Phase 2 | 合并报表 | ✅ |
| Phase 3 | 协作功能 | ✅ |
| Phase 4 | AI 服务 | ✅ |
| Phase 5-7 | 扩展/深度集成/增强 | ✅ |
| Phase 8 | 数据模型优化 | ✅ |
| Phase 11-17 | 系统加固~数据集版本治理 | ✅ |

当前处于**系统打磨+底稿深度优化**阶段，通过 spec 三件套驱动迭代。47 个 spec 目录见 `.kiro/specs/INDEX.md`。

## 底稿精细化规则分级体系

- A 级（77个）：有 layout + key_rows（结构性行）+ detail_discovery（明细行动态发现）+ cross_references + audit_checks
- C 级（270个）：有 audit_checks 但无精细 layout，为 A/B/C/S 系列程序表/检查表/核查清单
- key_rows 只定义结构性行（合计/小计/减：/试算平衡表数/差异数/段标题），明细行由 detail_discovery 根据企业实际数据动态识别
- detail_discovery 规则：mode=auto, start_row→before_first_total，自动扫描非空行
- API：`/api/wp-fine-rules` 支持 cycle/quality 过滤，`/api/wp-fine-rules/summary` 按循环分组统计，`/api/wp-fine-rules/system-map` 体系全景图

## 底稿→附注数据流

- 统一原则：结构来自模板，数据从底稿动态提取，校验基于结构不依赖行名
- 取数优先级：底稿 fine_summary 明细行 > 底稿 audited_amount > 试算表 > 模板预设行
- 缓存链路：extract_with_fine_rule → parsed_data.fine_summary → _wp_fine_cache → _build_table_data


## 辅助维度冗余存储模型（2026-05-10 定型）

**核心设计**：`tb_aux_balance` / `tb_aux_ledger` 采用"按维度冗余存储"模式，非"按坐标点单条存储"。

**举例**（真实 YG36）：
```
原始行：金融机构:YG0001,工商银行;银行账户:3100035219100042014  closing=3948.93
       金融机构:YG0018,邮储;银行账户:951004010002007700         closing=100.00

入库成 4 条 tb_aux_balance：
  type=金融机构  code=YG0001  name=工行           closing=3948.93
  type=金融机构  code=YG0018  name=邮储           closing=100.00
  type=银行账户  code=NULL    name=3100...42014   closing=3948.93   ← 同金额冗余
  type=银行账户  code=NULL    name=951...07700    closing=100.00    ← 同金额冗余
```

**校验铁律**：对 tb_aux_balance 做一致性校验时，**必须按 aux_type GROUP BY 求和后再和 tb_balance 比对**。
- 正确：`金融机构 sum = 3948.93+100 = 4048.93 = tb_balance.closing` ✓
- 正确：`银行账户 sum = 3948.93+100 = 4048.93 = tb_balance.closing` ✓
- **禁止**：所有 aux 行求和 `8097.86 = 父×2` → 会产生误报 mismatch

**受此模式影响的代码路径**（未来新增聚合逻辑必须遵守）：
- `/api/projects/{pid}/ledger/balance-tree` 端点 mismatches 算法（Layer 2 v2）
- `validate_four_tables` 校验函数（smart_import_engine.py:1210）
- `consistency_check_service._check_tb_vs_balance`
- `consistency_replay_engine`
- `import_intelligence` DQ-05
- 未来的合并工作底稿校验

## balance-tree 端点两层嵌套结构（2026-05-10）

`GET /api/projects/{pid}/ledger/balance-tree?year=&company_code=` 返回三层树形：

```
父科目节点 (account_code)
├── 维度组节点 (aux_type)  ← 第 2 层聚合求和
│   ├── 具体 aux 明细 1   ← 第 3 层 tb_aux_balance 原始行
│   └── 具体 aux 明细 2
└── 另一个维度组节点
    ├── 明细 1（与上组同金额冗余）
    └── 明细 2
```

**节点字段**：
- 父：`aux_types: []`（该科目涉及的维度类型列表）、`aux_rows_total: N`（所有明细总数）
- 维度组：`_is_dimension_group: true`、`aux_type`、`closing_balance`（组内求和）、`record_count`
- 明细：tb_aux_balance 原始字段

**mismatch 判定**：每个维度组 sum ≠ 主表 closing 才算 mismatch，返回 `{account_code, aux_type, parent_closing, dim_sum, record_count, diff}`。

**前端对应渲染**：`LedgerBalanceTreeView.vue` el-table tree-props 三层渲染，用 `_nodeType: 'account'|'group'|'aux'` 区分，`_rowKey` 三段式（`acc:...` / `acc:...:grp:...` / `acc:...:grp:...:aux:...`）。

## 流式分块 + 分组聚合矛盾（2026-05-10）

**问题**：pipeline.py `_execute_v2` 对所有 sheet 流式分块解析，converter 的"按 (company, account_code) 分组去重"只能在 chunk 范围内生效。YG36 真实数据 1823 行 balance sheet 分 2 chunk，导致 account_code 跨 chunk 重复（1002 被拆 3 条主表行）。

**决策**：按表特性差异化策略，非一刀切。
- **balance / aux_balance**：sheet 全量累积 cleaned 到内存，sheet 结束时统一 `convert_balance_rows` + `_insert`，跨 chunk 去重生效；真实数据 <5k 行内存安全
- **ledger / aux_ledger**：保持流式（百万级行数内存不可控），序时账本身不存在"同 account_code 重复"语义问题
- 未来若 balance 超 50000 行需要内存阈值 warning

**代码位置**：`backend/app/services/ledger_import/pipeline.py _execute_v2` 内的 `balance_cleaned_accumulated` 列表 + sheet 结束处的统一 insert。


## /balance-tree 分页查询参数（2026-05-10 Sprint 8 P3）

端点支持服务端分页 + 过滤：

| 参数 | 类型 | 约束 | 默认 | 说明 |
|------|------|------|------|------|
| `year` | int | required | — | 年度 |
| `company_code` | str | optional | None | 公司代码（合并账套用） |
| `page` | int | ≥1 | 1 | 页码（1-based） |
| `page_size` | int | 1-200 | 100 | 每页科目数，**硬上限 200** |
| `keyword` | str | optional | None | account_code/account_name 模糊过滤（ilike） |
| `only_with_children` | bool | optional | false | 仅返回含辅助维度的科目 |

**响应新增 `pagination` 字段**：`{page, page_size, total, total_pages}`

**设计要点**：
- `only_with_children=true` 时先查 aux_balance 的 account_code 集合再过滤主表（避免 LEFT JOIN 膨胀）
- aux 查询通过 `account_code IN (本页主表)` 收窄，避免全量 aux 拉回
- 前端 keyword/only_with_children 走服务端过滤，aggregated/mismatch 走本地过滤（服务端无需知道 mismatch 细节）

**ADR**：见 `docs/adr/ADR-001-auxiliary-dimension-redundant-storage.md`


## 损益类 vs 资产负债类科目过滤差异（2026-05-10 Sprint 8 P3f）

**会计准则事实**：损益类科目（5/6 开头）期末结转到本年利润，`opening_balance` 和 `closing_balance` 天然为 NULL；资产负债权益类（1/2/3/4 开头）则保留期初期末余额。

**影响所有涉及"是否有金额活动"判定的代码**：不能一刀切要求四字段都有值，必须按科目类型差异化：

- **1/2/3/4 开头**：`opening_balance OR closing_balance OR debit_amount OR credit_amount` 任一非零
- **5/6 开头**：`debit_amount OR credit_amount` 任一非零（opening/closing 不参与）

**实现模式**（SQLAlchemy，SQLite/PG 双兼容）：

```python
first_char = sa.func.substr(bal_tbl.c.account_code, 1, 1)
loss_gain_active = sa.and_(first_char.in_(("5", "6")), ...debit/credit 任一非零)
other_active = sa.and_(sa.not_(first_char.in_(("5", "6"))), ...四字段任一非零)
where.append(sa.or_(loss_gain_active, other_active))
```

用 OR 拼场景（非 CASE）便于查询优化器走索引；用 `substr` 而非 `left`（SQLite 不支持 `left`）。

**首次实现**：`/balance-tree` 端点 `only_with_activity` 参数。未来所有"余额状态/活跃度"判定（试算表筛选、报表生成预筛、账表健康度指标等）都应遵循此差异化规则。

**真实数据验证**（YG36）：全部 813 → 有活动 208；其中 6xxx 损益类 356 个 → 97 个有活动（opening/closing 全 NULL 但 debit/credit 有值被正确包含）。


## 账表导入可见性架构（B' 视图重构，2026-05-10）

**参考**：ADR-002 (`docs/adr/ADR-002-ledger-view-refactor.md`)、spec `.kiro/specs/ledger-import-view-refactor/`

### 核心原则
可见性状态从**行级 `is_deleted` 字段**升级到**`ledger_datasets.status` 元数据**。物理行 `is_deleted` 恒为 `false`（除回收站/归档场景），可见性完全由 `ledger_datasets.status = 'active'` 控制。

### 查询层
- **单一入口**：`app.services.dataset_query.get_active_filter(db, table, project_id, year)`
- **返回**：`project_id + year + dataset_id(active) + is_deleted=false（兜底）` 组合条件
- **优化版本**：`get_filter_with_dataset_id(table, pid, year, dataset_id)` 同步版，caller 先查一次 active_id 后批量复用（避免 N+1）
- **year=None 兜底**：`LedgerDataset` 子查询 + `dataset_id.in_(active_ids)` + `is_deleted=false` 双保险（Template B 模式）

### 写入层
- pipeline `_insert` 写入直接 `is_deleted=False`
- staged 隔离靠 `dataset.status = 'staged'`（不依赖 is_deleted）
- 回收站 / archive / restore 仍用 `is_deleted=true`（软删语义保留）

### activate/rollback 路径
- 只 UPDATE `ledger_datasets` 2 行元数据（superseded ↔ active）
- 不再 UPDATE Tb* 物理行（旧逻辑 127s → 新逻辑 <1s）
- `DatasetService._set_dataset_visibility` 改为 no-op + `logger.warning`（保留签名兼容）

### 禁止模式
- 业务查询禁用 `TbX.is_deleted == False`（Tb* = TbBalance/TbLedger/TbAuxBalance/TbAuxLedger）
- CI 卡点：`backend-lint` job 扫 `Tb(Balance|Ledger|AuxBalance|AuxLedger)\.is_deleted\s*==` 命中 > baseline(6) 即 fail
- 6 处允许清单均为 year=None 兜底分支（wp_chat_service/sampling_enhanced_service/report_trace_service/ocr_service_v2/routers/report_trace×2）

### 集成测试锚定
`backend/tests/integration/test_dataset_rollback_view_refactor.py` 4 用例覆盖：
- rollback 切换 metadata 不 UPDATE 物理行
- 首版无 previous 返回 None 不改状态
- 跨项目 A staged + B active 互不污染（按 project_id 隔离）
- 两项目同时 active 查询严格隔离

## 账表导入可见性架构（B' 视图重构，2026-05-11 落地）

- 业务查询统一走 `get_active_filter(db, table, pid, year)` 过滤可见数据
- pipeline 写入 `is_deleted=False`，staged 隔离靠 `dataset.status=staged`
- `DatasetService.activate/rollback` 只改 metadata（不 UPDATE 200 万行），activate <1s
- 4 张 Tb* 表 + partial index `WHERE is_deleted=false` 覆盖 active 查询
- CI guard：`Tb*.is_deleted==` baseline=6（year=None 兜底分支），新增查询必须走 get_active_filter

## 底稿模块架构（2026-05-17 落地）

- 模板文件：473 个致同 2025 修订版（xlsx + docx），存储 `backend/wp_templates/`
- 元数据：`wp_template_metadata` 表 179 主编码 + 24 子表继承 = 203 条
- 映射：`wp_account_mapping.json` 206 条（D-N 科目驱动 + A/B/C/S 阶段驱动，v2025-R5）
- 组件选型：Univer（xlsx 公式类）/ el-form（问答类）/ el-table（清单类）/ 富文本（docx 类）/ 混合视图
- 预填充双路径：生成时用 `prefill_formula_mapping.json`（119 条语义映射）；编辑时扫 xlsx 内嵌 `=TB()/=WP()` 公式执行
- 公式引擎类型 10 种：TB / SUM_TB / WP / AUX / PREV / ADJ / LEDGER / NOTE / TB_AUX / LEDGER_DETAIL
- 地址坐标 URI 格式：`{wp_code}:{sheet_name}:{label}`（语义描述稳定标识，物理坐标运行时动态解析）
- **自定义底稿公式（2026-06-03，`custom-workpaper-formula-binding`）**：持久化表 `wp_formula`（V052，`wp_formula_service`+`wp_formula` router）；`extract_custom_cells` 从 `parsed_data`（html_data[sheet].cells + 扁平）注册 address_registry **WP 域**；公式引用 URI **`wp://{wp_code}/{cell}`**（`wp_formula_service` 往返，legacy `#` 仍解析）；`WPExecutor` 对自定义 sheet 用 Excel 坐标 `^[A-Z]+\d+$` 直读 cell；`WorkpaperGenerationService.ensure_working_paper` 在程序指派/手动 generate-from-index 触发；`componentType=custom`→`GtCustomWpEditor`（classification/render-config 双路径，`sheet_name=wp_code`）；编制信息 `GET /api/workpapers/{wp_id}/preparation-info` + `GtWpPreparationHeader`（无 accounting_period）；registry 失效 `touch_wp_registry` 已接部分写路径（公式/精细化规则/程序状态等），非全量
- 全局联动：Unified Linkage Bus + 统一依赖图 46K 节点 / 36K 边 + Stale Propagation Engine BFS（spec 三件套已完成）

## 关键 PG 事实

- `working_paper` 表名单数（不是 working_papers）
- WorkingPaper 模型无 year/wp_code 字段（year 从 Project 取，wp_code 从 wp_index JOIN 取）
- `check_consol_lock` 必须用 SAVEPOINT（否则 rollback 让 ORM 对象 expired → MissingGreenlet）
- PG enum 值：`report_type` 7 个 / `job_status_enum` 13 个（含 interrupted/retrying/cancelled）
- SQLAlchemy `session.refresh(obj)` 会覆盖未 flush 修改；`db.add(obj)` 不立即生成 PK 需先 flush
- 任何 `try: db.execute(...) except: pass` 必须在 except 中 `await db.rollback()`（否则 session 进 aborted 状态）
- `async with db.begin_nested()` SAVEPOINT 模式：探测性查询失败只回滚子事务不破坏外层

## 关键前端事实

- apiProxy：`api.get/post` 返回 unwrapped data；HTTPException.detail 走 `body.message` 字段
- token 存 sessionStorage（不是 localStorage）；fetch 用 `sessionStorage.getItem('token') || localStorage.getItem('token')`
- DefaultLayout `FULLWIDTH_PATHS` 数组：新建一级路由必须登记，否则被三栏布局吞掉
- Univer JSON `cellData[r][c].s` 可以是 inline dict 或 styleId 字符串引用（必须 isinstance 校验）
- openpyxl `Color.rgb` 对 theme/indexed 色返回降级字符串，必须用 `_safe_hex_rgb()` 二次校验
- el-dialog 必须 `append-to-body`（三栏布局 overflow:hidden 截断）
- eventBus 新事件必须先在 Events type map 添加键（mitt 运行时通过但 TS 报错）


## §高级查询模块架构（2026-05-24 advanced-query-enhancements-p1p2）

### wp_template_registry 表

```
wp_template_registry (184 主底稿)
├── wp_code VARCHAR(32) PK
├── wp_name VARCHAR(255)
├── cycle VARCHAR(2) CHECK (A~N+S)
├── account_codes JSONB (GIN 索引)
├── sheets JSONB [{name, is_aux, sort_order}]
├── applicable_standard JSONB
├── version INTEGER (递增触发 X-Indicators-Schema-Version)
├── source_origin VARCHAR(64) (wp_account_mapping / step_sheet_mapping / merged)
└── 3 索引: cycle B-tree / updated_at DESC / account_codes GIN
```

### parsed_data GIN 索引

- `idx_wp_parsed_data_gin` ON working_papers USING GIN (parsed_data jsonb_path_ops)
- CREATE INDEX CONCURRENTLY（不锁表）+ _ccnew 残骸清理
- 启动时 `pg_stat_progress_create_index` 检查 → `INDEX_BUILDING` 全局 flag
- flag=True 时查询降级顺序扫描 + `X-Index-Status=building` 响应头
- 体积 > 500MB 触发 `pg_index_size` 告警

### LibreOffice 池化

- 模块级 `asyncio.Semaphore(2)` 限制并发
- Windows: `-env:UserInstallation=file:///tmp/soffice_{pid}_{tid}` 隔离
- 4 路径 fallback: libreoffice / soffice / C:\Program Files\... / /usr/bin/...
- 60s 超时 kill + HTTP 504 + semaphore 释放
- `X-Recompute-Queue-Depth` 响应头（队列 ≥ 10 时）+ Prometheus metric

### 4 模块 cell 提取器

```
SheetCellRangePicker → Module_Cell_Resolver (路由器)
  ├── workpaper:wp_code|sheet|range → _query_workpaper_cell_range (parsed_data)
  ├── report:type|range → _query_report_cells (report_snapshot.data JSONB)
  ├── note:section_id|range → _query_note_cells (consol_note_data.data JSONB)
  ├── adj:type|range → _query_adj_cells (adjustments 表 → 虚拟 sheet)
  └── tb:aux_dim|range → _query_tb_cells (trial_balance → 虚拟 sheet)
  
统一输出: {cell_ref, value, formula, sheet_name, module}
```

### SnapshotWriter 写回路由

- workpaper → `parsed_data['univer_snapshot']` JSONB + xlsx cache
- report → `report_snapshot.data` JSONB
- note → `consol_note_data.data` JSONB
- adj → `adjustments` 表 UPDATE (按列名)
- tb → `trial_balance.audited_amount` UPDATE (仅 G 列可写)
- 乐观锁: X-File-Opened-At vs updated_at → 409 WritebackConflict


## 底稿 Runtime Boundary 架构（2026-07-14 落地）

### 设计
`GtWpRenderer` 作为所有专属底稿的统一运行时边界。在 setup 中基于响应式 `wpId/projectId/wpCode/year` 调用一次 `useWorkpaperScaffold`，通过 Vue provide 向所有子组件提供平台横切能力。

### 提供的能力（8 项）
| 能力 | 来源 | 说明 |
|------|------|------|
| displayPrefs | useDisplayPrefsStore | 全局单位/字号/密度 |
| agingConfig | useAgingConfig | 账龄段配置 |
| version | useWorkpaperVersionToolbar | 版本链+自动快照 |
| review | useWorkpaperReviewProvide | 复核对话 |
| ai | generateAiText | AI 文本生成 |
| jumpToSection | Runtime Boundary | sheet 跳转 |
| reload | Runtime Boundary | 页面重载 |
| persistence | useChecklistPersistence | 统一持久化适配器 |

### 组件接入模式
```ts
// 子组件 inject Runtime Context（不再本地 provide）
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())
provide('openReviewDialog', (opts) => runtime?.review.openReviewDialog(opts))
```

### Host 挂载
- `GtWpReviewDialogHost`：复核对话宿主
- `GtWpVersionTrail`：版本历史抽屉
- `GtWorkpaperRuntimeHosts`：统一挂载组件

### 防回归
- Coverage Ledger v2 按 `wp_code × capability` 记录实际接入
- Legacy Provider 已全部登记到 Ledger，有限期内允许保留
- CI guard `check_coverage_ledger.py --strict` 阻断明确缺失

---

## D~N循环专属组件架构模式（2026-07-02 D4定稿）

### 标准目录结构
```
frontend/src/components/workpaper/
├── GtXOperatingRevenue.vue           # 主入口 sheetName v-if分发
├── x/                                # 循环代码小写
│   ├── core/                         # 审定表+明细+调整+附注+目录
│   ├── policy/                       # 政策检查
│   ├── analysis/                     # 分析程序
│   ├── inspection/                   # 检查程序(含子组件Card/Matrix)
│   ├── related/                      # 关联方
│   ├── ipo/                          # IPO/舞弊(条件可见)
│   └── other/                        # 其他类(按需)
├── composables/
│   ├── useXFormulaEngine.ts          # 纯函数(可PBT)
│   ├── useXFormData.ts               # 数据加载/保存/selfLoad/writebackTB
│   ├── useXCrossSheet.ts             # 跨sheet联动computed
│   ├── useXAdjudication.ts           # 审定表
│   ├── useXImportExport.ts           # 导入导出(axios三端点)
│   ├── useXDualMode.ts               # 双模式OO健康检查
│   └── useX{Sheet}.ts               # 每sheet一个composable

backend/app/routers/wp_render_strategies/
├── _x_operating_revenue.py           # render策略+RENDERER_DISPATCH
├── _x_import_export.py               # 3端点(export-template/data+import-data)
├── _x_ai_generate.py                 # AI多section
└── _x_resolvers.py                   # auto_data resolver(TB取数)

backend/app/services/auto_data_resolvers/
└── _x_revenue.py                     # resolver注册
```

### 注册四件套（每个新循环必做）
1. `VALID_COMPONENT_TYPES`（wp_classification_service.py）
2. `htmlRendererRegistry`（前端componentType→Vue组件映射）
3. `RENDERER_DISPATCH`（后端componentType→render策略函数）
4. `account_package_registry.json`（sheet清单+顺序=目录行顺序）

### 数据流模式
```
TB(科目余额) ─────────→ useXFormData.loadAll()
                              ↓
allResponses Map ←── checklist_responses API
         ↓ (computed链，不走API)
useXCrossSheet ──→ 各子composable ──→ 各Vue子组件
         ↓
EventBus(substantive:adjudicated) ──→ TB回写
```

### 已完成的专属组件（10个循环）
| componentType | 科目 | sheet数 | composable数 | 测试数 |
|---|---|---|---|---|
| d1-notes-receivable | 1131应收票据 | 21 | 18+shared | 200+ |
| d2-accounts-receivable | 1122应收账款 | 20 | 18+shared | 200+ |
| d4-operating-revenue | 6001+6051收入 | 42 | 18 | 288+ |
| d5-receivables-financing | 1124应收款项融资 | 7 | 8 | 43 |
| d6-contract-assets | 1402合同资产 | 12 | 11 | 42 |
| e1-monetary-fund | 1001+1002+1012货币资金 | 27 | 15 | 52 |
| c-control-test | C2~C15控制测试 | 共用 | 3 | 25+ |
| b50-risk-assessment | 风险矩阵 | - | 3 | 32 |
| b22a-control-matrix | 内控五要素 | - | 3 | 48 |
| b22b-deficiency-evaluation | 内控缺陷 | - | 3 | 57 |

### 开发方法论（双源输入）
新循环开发前必须完成Phase0：
1. openpyxl脚本实读源xlsx → sheet结构/列头/公式（权威列名来源）
2. 读`BCD类底稿md/X循环底稿模板库.md` → 业务逻辑/联动/认定（权威语义来源）
3. 两源交叉验证 → 产出spec三件套


---

## 平台级数值格式全局机制（2026-07-25 定型）

金额显示的**唯一真源** = `stores/displayPrefs.ts`，三层机制：

### 1. 全局格式化（覆盖只读金额）

- `fmtAmount()`：`toLocaleString` 千分符 + `decimals`（默认 2 位）+ `amountUnit`（**默认 `yuan`「元」**）
- localStorage 键 `gt_display_prefs` + `PREFS_VERSION=2`（`_v<2` 且遗留 `amountUnit==='wan'` 时一次性迁移到 `yuan`）
- 切换单位/小数位实时响应全平台
- 只读金额只要用 `displayPrefs.fmtAmount()` 就已全局生效

### 2. 防折行全局（覆盖全平台 el-table）

`styles/global.css`（`main.ts` 全局导入）：

```css
.el-table td.is-right .cell { white-space: nowrap; font-variant-numeric: tabular-nums; }
```

一处覆盖全平台所有 el-table 右对齐数值列，防长金额（含千分符）折两行 + 等宽对齐。**金额列必须 `align="right"` 才命中**。

### 3. 无法全局的两类（须逐模块）

- **可编辑金额**：EP 无全局 formatter → 用共享 `composables/wpAmountInput.ts` 的 `amountFormatter`/`amountParser`
  - **🔴 EP `el-input-number` 忽略 `:formatter`**（只 `:precision` 生效）→ 要千分符必须换 `el-input` + formatter/parser
  - **绝不套用**利率/汇率/比例/笔数/count/年度/月份 及 `precision=4|6` 字段（`isAmountColumn(col)` 按 label/key 判定）
- **显示原始数字** `{{ row.x }}` 未走 fmtAmount 的表格（无法全局拦截）须改用 fmtAmount

### 字号缩放

`global.css` 不强制字号（避免误伤正文）；个别超宽列按表微调 13→12→11px（14 位数在 130px 列 12px 单行可容），参照 E1-1。

### 主入口一处穿透覆盖（推荐范式）

多 tab 循环模块在主入口一次穿透覆盖全部子 tab 表格，不逐组件重复：

```css
:deep(.e1-monetary-fund :deep(.el-table td.is-right .cell)) { ... }
```

---

## 附注联动三链架构（J / R / S）

附注模块与底稿披露表的联动由三条独立链路组成，缺一即"改了披露表附注不动"：

| 链 | 名称 | 实现位置 | 机制 |
|----|------|----------|------|
| **J** | 跳转（附注→披露表） | `views/composables/noteDisclosureJump.ts` | `resolveNoteDisclosureJumpTarget` 按 note_section 章节号推 listed/soe sheet |
| **R** | 定向刷新 | `views/composables/useNoteRefresh.ts` | `onDisclosureNoteTextUpdated` 按 accountCode / sectionIds 匹配当前节 |
| **S** | 结构化同步 | 后端 `wp_disclosure_sync_service.sync_from_workpaper` + `note_sub_table_projector` | 按 section_id 驱动（**后端科目无关**），缺口全在前端注册 |

**反向跳转（披露表→附注）**：`views/composables/noteDisclosureReverseJump.ts` 的 `DISCLOSURE_NOTE_SECTION_MAP` + `buildNoteJumpRoute`。

### 权威数据源

- **章节号权威** = `backend/data/note_template_variant_matrix.json`（`account_key` → `variants{listed_standalone, soe_standalone}`）
  - 损益类：listed = `三、{section_title}`（matrix listed_* 为 null）+ soe = `八、N`
  - 资产负债类：listed = `五、N` + soe = `八、N`
- **section↔wp 映射真源** = `backend/data/note_workpaper_sync_registry.json`（由 `scripts/gen_note_wp_sync_registry.py` 从前端 `*NoteSectionMap.ts` 生成，禁手工维护第二份）

### 关键约束

- **纯编号章节判定必须精确 `===`**（`五、7 ≠ 八、70`、`五、8 ≠ 五、80`）；损益类关键词标题才前缀双向模糊
- **披露 sheet 名必须 = `workpaper_sheet_classification` 真实 tab 名**（各循环命名不统一：`附注披露信息（上市公司）` 全角 vs `附注披露信息(上市公司)` 半角），禁用 OnlyOffice sheet-name 映射（如 `附注上市`）
- **emit 载荷必带** `accountCode` + `projectId` + `sectionIds`（对齐 G10 范式），否则 R 链命不中只靠全量刷新兜底
- **piggyback 科目**（应收利息 G2 / 应收股利 G3 / 工程物资 H4 / 固定资产清理 H6 无独立章节）跳节主不单列入口
- **写入年度必须以 `projects.audit_year` 为权威**（前端普遍不传 year，fallback 到服务器自然年 = 跨年审计必写错年度）

### 结构化同步（S 链）payload 契约

前端 `buildXSyncPayload` → `POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper`：

- `sub_table_data` 各子表键 ↔ `columns` 键**必须同名**（投影器按名匹配）
- `_note_texts`（`list[{section,title,text}]`）混在 `sub_table_data` 里，服务端自动 pop 成 `text_content`
- 空载荷 = no-op 保留既有子表（**不清空**）；`{key:[]}` 才是该表空行有效状态
- 软删章节需"先查软删行复活"（唯一索引不含 `is_deleted`，否则删后重建撞键 500）

---

## 四表取数架构（Tier A / Tier B）

四表库（`trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance`）→ 底稿自动取数的两层模型：

| 层 | 适用 | 载体 | 可编辑 |
|----|------|------|--------|
| **Tier A** | 固定类别审定表（每类恰好=一个科目：F2 存货 13 类 / H/I/L/M/N 分段） | 预设 `TB('code','列名')` 公式（`{cycle}_extraction_presets.json`） | ✅ 公式管理可查可编 |
| **Tier B** | 明细/分段预填（复用 `_build_adjudication_prefill` 范式） | render 策略 SQL 直查 + `_is_leaf` 叶子过滤 | ❌ 只读溯源 |

### 铁律

- **宁缺勿造**：分类/账龄/客户维度（D 循环信用风险组合、账龄分类）**无法用单条公式表达**且 TB 无对应维度 → **不 seed**，只登记 Tier B provenance 声明
- **叶子过滤防双算**：`_is_leaf` = 该 code 不是任何其它 code 的前缀；父子同时累加会翻倍
- **方向口径**：资产借方 → 增加=`debit_amount` / 减少=`credit_amount` / 期末=`closing_balance`；负债/权益贷方相反；备抵科目（1471/1602/1512）反转 + `abs()`
- **手工优先（Persist_First）**：已有非空用户值不覆盖；仅锚点完全空时 seed
- **灰度默认关**：`{X}_FOUR_TABLE_EXTRACTION_ENABLED` 默认 False，开关 on/off 须逐字节等价（无干净映射时不 seed）
- **口径统一**：render 预填 / 公式求值 / 刷新三处必须同 `get_active_filter`（数据集版本一致）
- **锚点必从真实 composable 反查**（`{cycle}_anchor_registry.json`），禁臆造 item_id
- **明细项目/卡片级不取数**：`tb_aux_balance` 多数科目无项目/规格维度（实测 H1 固定资产 aux 只有 FFLEX10 三个 name）；`counterpart_account` 填充率仅 ~9% → 费用归属不做自动归集

### 报表科目映射（避免硬编码前缀）

审定表 TB 核对科目走 `services/report_account_mapping.py`：

- `resolve_report_line_account_codes(db, pid, row_code, fallback)`：项目级 → 标准级解析 `report_config.formula` 提取 `TB()`/`SUM_TB()` 码
- `build_trial_balance_code_filter`：单码 LIKE / 区间 BETWEEN 参数化
- 无配置回退 fallback（保零回归）；`project_context.tb_source_codes` 供追溯
- **报表取数真源 = `report_config` DB 表**（非 `formula_presets_seed.json`，后者是公式管理 UI 预设库）

---

## 双模式架构（结构化视图 / OnlyOffice 在线编辑）

统一封装 `composables/useWpDualMode.ts`（或各循环 `useXEntryDualMode`），核心 = **"拉取成功才切"**：

```
switchMode('onlyoffice')
  → GET /api/workpapers/{wp}/sheets/{sheet}/onlyoffice-config?project_id=  ← 必带 project_id 否则 422
  → config 非空才置 currentMode='onlyoffice'
  → 失败回退 html + warning
```

### 关键约束

- **`el-segmented` 必须 `:model-value` + `@change`**，禁 `v-model`（v-model 抢先改值使 `switchMode` 首行 `if(target===current) return` 短路 → config 预拉与健康门控全失效）
- **健康检查双层兼容** `res?.data?.healthy ?? res?.healthy`（`api.get` 只 return response.data）
- **`@fallback` 必须接线**（文档渲染/45s 超时失败要回退 html + 标记不可用），否则"拉取成功"tag 撒谎
- **入口级 mode 是共享状态**：目录/程序表等无切换栏的 sheet 必须从 OO 分支排除（`isSwitchableSheet`），否则切 OO 后被顶掉无法切回
- **单 sheet config 失败不应全局禁用 OO**（合成"底稿目录"无 xlsx 对应必 422）
- **OO sheet-name 必须与源 xlsx tab 名完全一致**；render 要输出 `source_sheet` 供前端定位

### 机对机端点必须公开（V113 回归教训）

`dedicated_wp_gate`（含 `get_current_user` 硬依赖）按"router 含 `{wp_id}` 路由"**整体挂载** → 同 router 内的机对机端点会被连坐要求用户 Bearer：

- `/onlyoffice/health`（前端裸 fetch 无 Bearer）
- `/{wp_id}/sheets/{sheet}/wopi/contents`（DocServer 拉文档，只带 `?token=` 签名 JWT）
- `/{wp_id}/sheets/{sheet}/onlyoffice-callback`（DocServer 保存回调）

**解法**：这三个迁到 `public_router` 且**显式在自动加 gate 的循环外注册**（放进 groups 列表会因含 wp_id 被重新加 gate）。

---

## 附件↔底稿关联权威真源（V133 收敛）

平台曾有**多套并行**"附件↔底稿"关联写不同存储，导致"本底稿关联哪些附件"无单一答案：

| 机制 | 写入 | 可被反查看见 |
|------|------|-------------|
| evidence-governance `associate` | `attachment_working_paper` 链表（M:N + association_type） | ✅ |
| process-record `linkAttachment` | `UPDATE attachments SET reference_type/reference_id`（1:1 覆盖） | ❌（收敛前） |
| 函证 | `confirmation_attachment_link(confirmation_id, attachment_id, role)` | 独立 |
| 检查项级 | `attachment_type` 过滤 | 视图级 |

**收敛后（V133）**：

- **权威真源** = `attachment_working_paper` M:N 链表 + `uq_awp_attachment_wp` 唯一约束
- `ensure_wp_link`（先查再 INSERT，幂等）；`associate` 委托它，`linkAttachment` 追加它（fail-open）
- 反查 `GET /working-papers/{wp}/attachments` = 链表(associated) ∪ reference(referenced) ∪ 函证(best-effort) **去重**，additive `source`/`sources`/`association_type` 标注来源
- 解除关联 `DELETE /working-papers/{wp}/attachments/{aid}/link`（清 reference + 幂等 no-op）
- **C3 opaque-locator** 单一真源 `services/attachment_locator.py::project_attachment_locator`（paperless:// 原样 / 其它 → `/api/attachments/{id}/download`），禁泄露绝对 file_path

---

## 委派 / 可见性隔离架构（V113）

两层委派**分层但联动**（非合并）：

| 层 | 存储 | 语义 |
|----|------|------|
| 底稿主编 | `WorkingPaper.assigned_to` + `ProcedureInstance.assigned_to` | 底稿层负责人 |
| 程序行执行/复核 | `ProcedureRowTask`（V105） | 具体程序步骤 |

两层互不覆盖，共同贡献可见性。

### 服务端 fail-closed 可见性隔离

- `services/wp_visibility/`：`visible_wp_index_ids` = lead/assignee/reviewer grants ∩ scope_cycles
- **列表/render-config/checklist/download/attachment/OnlyOffice 全部服务端强制**（不能靠前端隐藏）
- 未委派资源统一 **404**（不可见原因不区分，防信息泄露）
- Admin/Supervisor 产生显式 `admin`/`supervisor_scope` AccessGrant
- 撤权一致性：权限/委派/history/scope/角色变化必须与持久 policy epoch + invalidation outbox **同一事务**提交；Redis 只做提交后 fan-out
- 历史授权真源 = append-only `workpaper_delegation_history`（禁通过当前 StaffMember/ProcedureRowTask 反推）

### 粗裁

`ProcedureService.init_from_templates()` 按 wp_code 一张底稿一条 `ProcedureInstance` = **科目/底稿范围实例**（非程序行）；真实程序行在 `GtAProgramConsole.ProgramRow` + `WorkingPaper.parsed_data.procedure_status[sheet_key][row_id]`。

**智能裁剪判据 = 数据驱动**：`GET /api/b50/scope-accounts`（试算表非零余额科目 + `cycle_for_account` 循环映射）→ 只裁"该循环/科目在试算表无数据"的 D~N 程序；取数失败/试算表未导入 → **fail-safe 不裁**（防"拿不到=全无数据=全裁光"）。子科目级精度走 `procedure_trim_scope.py`（`account_package_registry` + `procedure_trim_account_map.json` 隔离文件，registry 优先不覆盖）。

---

## 调整分录集中登记架构（V124/V125/V127）

底稿级调整（`checklist_responses` JSON）→ 集中式 `adjustments` 表的汇聚：

- **前端显式** `useAdjustmentCentralSync.syncToCentral()`（前端知自身 row schema + 科目上下文，避免后端维护 N 种键 schema）
- **幂等** `source_ref = {wp_id}:{item_id}`；`origin='workpaper'` 隔离
- **🔴 recalc 加 `origin != 'workpaper'` 过滤消除双计**（workpaper origin 已由审定表 writeback 写 audited_amount，不再进 aje_adjustment；manual/NULL 零回归）
- **协作接力**（V125）：`adjustment_collaboration` 状态机 pending→acknowledged→contributed→confirmed + append-only `adjustment_collaboration_event`；锚点 = central `entry_group_id`；**协作锁**（活跃协作时 `sync_from_workpaper` 返 `COLLABORATION_LOCKED` 409 防底稿 re-sync 覆盖）
- **明细科目码**（V127）：`adjustment_entries.detail_account_code` 可空列承载二级/明细码（`standard_account_code` 一级码保校验/recalc/报表口径不变）；前端匹配 `effectiveCode = detail_account_code || standard_account_code`
- **错报 ≠ 调整**：`a13:push-misstatement` → `unadjusted_misstatements` 表（全局唯一消费者 `useA13MisstatementBridge` 挂 `WorkpaperEditor`，纯函数归一 4 种 payload 形态 + 5s 去重窗口 + `source_wp_code` 溯源）

---

## 前端 SSE 单连接总线（2026-07-23 收敛）

`services/sse/projectEventStream.ts`：

- 每 projectId **一条** `createSSE` Shared_Connection（fetch-based，Authorization header，**token 不入 URL**）
- `subscribeProjectEvent(pid, eventName, handler, {onReconnect, onDegraded})` 按 Event_Name fan-out + Ref_Count_Lifecycle
- `WILDCARD_EVENT='*'` 通配（ThreeColumnLayout 全局 catch-all 转发 `data.event_type` → mitt `sse:*`）
- 断线重连/退避委托 `createSSE` 单一真源；总线只做 fan-out（异常隔离）
- 守卫 `sseConsolidationGuard.spec.ts`：除总线/`utils/sse.ts` 外禁直连 `/events/stream`

**native `EventSource` 无法设 Authorization header** → 只能 `?token=` 入 URL（安全隐患）；要 token 出 URL 必须用 fetch-based SSE。

---

## 公式管理架构（surfacing / 预设 / 自定义）

### 底稿节点公式来源三层

1. **`wp_formula` 表**（用户自建/编辑的 `items`）
2. **surfaced 只读条目**（专属组件的取数/计算/勾稽公式，`wp_surfaced_{family}.py` 家族目录 + `wp_surfaced_formulas.py` try/except merge 聚合）
3. **extraction**（Tier A 可编辑预设 + Tier B 只读溯源）

**surfacing 铁律**：

- 公式必从真实 composable 反查（`useXFormulaEngine` 函数名/`useXAdjudication` 取数键），**禁臆造**
- 分类严格三种：`取数`（跨 sheet / 四表库）/ `计算`（表间）/ `logic_check`（核对）
- 每条打 `sheet_codes` 归属（前端按选中 sheet 过滤），否则工作簿级全量在每 sheet 重复
- `sheet_codes` 必须是 ACNR 真实编码节点（`X-1`/`X-2`）；非编码语义名（附注上市/程序表）在 ACNR 无独立节点 → 归到审定表 `{base}-1`
- 只读行必给**非 null 稳定 id**（`editingId===row.id` 对 null 恒真 → 渲染空编辑框）

### 预设库（通用 vs 自定义）

- **通用基线** = `backend/data/formula_presets/formula_presets_seed.json`（876+ 条，致同标准）
- **自定义** = `formula_custom_presets.json`（隔离文件）；`preset_library.build_preset_library` 把 custom **置于 seed 之前** → 去重首个赢使同键覆盖
- `upsert_custom_presets` 只写 custom 文件绝不碰 seed；写端点 `require_role`(admin/partner)
- 读时收敛（seed ∪ prefill ∪ check_presets ∪ wide_table，无 DB 表）

---

## 账套导入年度/月度列语义（2026-07-25 定型）

余额表导入的三层修正（识别 / 分类 / 转换）：

### 识别层

- `年初余额.借方` → `year_opening_debit`（**非** `opening_debit`）
- `本年累计.借方` / `累计发生额` → `year_debit`（原完全不被识别）
- 三处表头映射真源：`identifier._MERGED_HEADER_MAPPING`（双行合并点号，最先命中）/ `ledger_recognition_rules.json` 的 `column_aliases` / `smart_import_engine._MERGED_HEADER_MAP`（legacy 参照）

### 分类层

- `KEY_COLUMNS["balance"]` = `{account_code, year_opening_debit, year_opening_credit, year_debit, year_credit, closing_balance}`
- 月度列（`opening_balance` / `debit_amount` / `credit_amount`）→ RECOMMENDED（不硬阻断）
- `_alt_to_key` 加 `if "+" not in alt_group: continue`（单字段替代只识别打分不提升 tier，仅组合型 `closing_debit+closing_credit` 提升）
- `_NEGATIVE_SIGNALS["balance"]` 含 `aux_type`/`aux_code`（防含 aux 维度的净额表被误判 balance）

### 转换层

- `_first_decimal(*vals)`：**显式 `is None`** 判缺失（禁 `or`，`Decimal(0)` falsy 会误判）
- 期初优先 `year_opening_*`，发生额优先 `year_debit`/`year_credit`，月度兜底
- v2 `converter.py` 与 legacy `smart_import_engine.py` **必须同步改**

### 符号口径

`tb_balance.closing_balance` 可能是**无符号绝对值**（方向在 `closing_direction`）→ `recalc_unadjusted` 必按方向 `case` 带符号求和，否则混合方向科目（含借方性质挂账的其他应付款）同号累加不冲减 → 报表资产负债不平。

---

## 报表不平诊断链（2026-07-25 沉淀）

「资产负债不平」按以下顺序逐层排查：

1. **报表层**：总计行（BS-039/BS-099）→ 分段合计（资产/负债/**权益** BS-091）→ 定位为 0 的段
2. **公式层**：该段行的 `formula_used`（`TB('科目')`）→ 是否漏减备抵（累计折旧/减值/未确认融资费用）
3. **试算表层**：`trial_balance` 该科目 `audited_amount`
4. **源数据层**：`tb_balance` 四列（opening/debit/credit/closing_balance + direction）是否 NULL / 是否无符号绝对值
5. **映射层**：`account_mapping` 是否有未映射叶子（`original_account_code` 无匹配）

### 三层根治（已实施）

- **recalc 按方向带符号求和**（消除混合方向科目虚增）
- **未映射叶子按最长前缀继承祖先映射**（`ORDER BY LENGTH(original_account_code) DESC LIMIT 1`，防 auto_match 覆盖不全的静默丢弃）
- **`TB('父码')` 前缀聚合含子科目**（`LIKE 'code%'`，客户映射到合法子级标准码时不漏计；已验证 4 套标准 report_config 无前缀重叠不双算）

### 四表入库 → 可用的三段独立链路

`ledger_import/pipeline.py` 只做 detect → convert → activate_dataset → rebuild_aux_summary，**不建科目表/不做映射/不生成试算表**。后三步靠：

- 标准科目表：访问「科目表」页懒加载（`GET /account-chart/standard`）
- 科目映射：`mapping_service.auto_match`（幂等自愈：client 空→从 tb_balance 生成 / standard 不足→从 client 补 / 匹配 / 触发 recalc）
- **已接自动化**：`_auto_map_on_dataset_activated` 订阅 `LEDGER_DATASET_ACTIVATED` 自动跑 auto_match（best-effort 不阻断导入）

**🔴 dataset-stranding**：`account_chart` 唯一约束不含 `dataset_id` → client 科目项目全局唯一，**任何按 dataset 过滤 client 科目的地方都会造成 re-import 后滞留 superseded**（去过滤而非加过滤）。
