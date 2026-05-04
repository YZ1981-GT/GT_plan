---
inclusion: manual
---

# 项目架构参考

需要了解项目结构、文件清单、技术栈时用 `#architecture` 引用此文件。

## 技术栈

- 后端：FastAPI + SQLAlchemy 2.0 异步 + PostgreSQL 16 + Redis 7 + Alembic（已放弃迁移链，用 create_all + 手动 ALTER TABLE）
- 前端：Vue 3 + TypeScript + Element Plus + Vite，入口 `audit-platform/frontend/`（端口 3030）
- 在线编辑：ONLYOFFICE Document Server 8.2（Docker，WOPI 协议）
- LLM：本地 vLLM Qwen3.5-27B-NVFP4（端口 8100，OpenAI 兼容 API）
- OCR：Tesseract + MinerU（GPU 加速）+ PaddleOCR
- 文件存储：本地磁盘 storage/ + Paperless-ngx（OCR/检索）+ 云端归档（S3/SFTP/SMB）

## 系统规模

- 后端路由：115 个文件，按 11 个业务域分组（router_registry.py）
- 后端服务：~170 个文件
- 后端模型：38 个文件，~144 张数据库表
- 前端页面+组件：~200 个 Vue 文件
- 前端 API 服务层：17 个文件
- 前端全局组件库：7 个 composable + 6 个 store + 8 个 common 组件 + 7 个 utils
- 底稿精细化规则：347 个 JSON
- 测试：~1800 个用例（单元 + E2E + 集成）

## 前端全局组件库（2026-05-05 完成）

### Composables（composables/）
| 文件 | 功能 | 接入模块数 |
|------|------|-----------|
| useFullscreen | 全屏切换+ESC退出 | 17（13 worksheet + 4 views） |
| useCellSelection | 单击/Ctrl多选/Shift范围选/鼠标拖拽框选/右键保持选区/selectionStats | 5 核心模块 |
| useCellComments | 单元格批注/复核标记 CRUD | 6 模块 |
| useLazyEdit | 按需渲染编辑控件（大表格性能） | 3 模块 |
| useProjectSelector | 项目/年度选择器 | 6 页面 |
| useWorkflowGuide | 工作流引导提示 | 8 个预定义引导 |
| useTableSearch | 表格内搜索替换(Ctrl+F) | 3 模块 |
| useEditMode | 查看/编辑模式切换+未保存提示+路由拦截 | 全模块 |
| useExcelIO | 统一 Excel 导入导出 | 14 worksheet |
| useTableToolbar | 通用表格工具栏逻辑 | 多模块 |
| useCopyPaste | 表格复制粘贴 | TrialBalance + ReportView |
| useKnowledge | 全局知识库调用 | DisclosureEditor + AuditReportEditor |
| useAutoSave | 自动保存/草稿恢复 | 3 模块 |
| useLoading | withLoading 包装 + NProgress | 全局 |
| usePermission | 按钮级权限控制 | 全局 |
| useKeyboardNav | Tab 键盘导航+批量粘贴 | GtEditableTable |

### Stores（stores/）
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

### Common Components（components/common/）
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
| GtEditableTable | 高阶可编辑表格（内置选中/拖拽/右键/批注/增删行/全屏/懒加载/小计） |
| GtPrintPreview | 打印预览弹窗 |
| GtConsolWizard | 合并模块向导式步骤条 |
| SyncStatusIndicator | SSE 同步状态指示器 |
| ExcelImportPreviewDialog | 通用导入预览弹窗 |
| KnowledgePickerDialog | 知识库文档选择器 |
| SharedTemplatePicker | 共享模板选择器（8 configType） |

### Utils（utils/）
| 文件 | 功能 | 状态 |
|------|------|------|
| formatters.ts | 金额/日期/百分比格式化+单位换算 | 5核心+14worksheet |
| http.ts | HTTP客户端+401刷新+去重+重试+POST防重复 | 全局 |
| sse.ts | SSE封装+自动重连 | 全局接入（ThreeColumnLayout） |
| shortcuts.ts | 快捷键管理(13个) | 全模块接入 |
| operationHistory.ts | 撤销功能 | Adjustments + RecycleBin |
| eventBus.ts | mitt 类型安全事件总线 | 全局 |
| apiPaths.ts | API 路径集中管理（500+路径） | 全局 |
| statusMaps.ts | 状态标签映射 | 全局 |
| confirm.ts | 语义化确认弹窗 | 全局 |

### 后端基础设施
| 文件 | 功能 | 状态 |
|------|------|------|
| core/pagination.py | PaginationParams/SortParams 统一分页排序 | 5 高频 API |
| core/bulk_operations.py | BulkOperationMixin 批量操作 | RecycleBin/Adjustments/ReviewInbox |
| core/audit_decorator.py | @audit_log 审计日志装饰器 | 删除/审批/状态变更 |
| core/migration_runner.py | 数据库版本化迁移 | 启动时自动执行 |
| services/equity_method_service.py | 模拟权益法（6 项改进） | 合并模块 |

## 11 个业务域（router_registry.py）

1. 基础设施 — 认证/健康检查/WOPI
2. 项目与向导 — 建项/科目导入/映射/数据集版本
3. 查账与试算 — 四表穿透/试算表/调整分录/重要性/错报/事件总线
4. 报表与附注 — 6 张报表/附注生成校验/审计报告/Word 导出/国企上市转换
5. 底稿管理 — 模板/QC/复核/预填充/精细化规则/公式/四式联动/账龄/依赖（最大域，27 路由）
6. 合并报表 — 差额表/内部交易/商誉/外币/少数股东（11 路由，前端标记 developing）
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
- 中间件栈（从外到内）：RequestBodyLimit→GZip→Observability→ResponseWrapper→RequestID→LLMRateLimit→AuditLog

## 关键环境配置

- Git 远程：https://github.com/YZ1981-GT/GT_plan.git（master 分支）
- 后端端口：9980，前端端口：3030，vLLM：8100，ONLYOFFICE：8080，Paperless：8010，Redis：6379，PG：5432
- 初始化数据库：`python backend/scripts/_init_tables.py`（自动扫描 models + create_all + 种子数据）+ `python backend/scripts/_create_admin.py`（admin/admin123）
- 启动开发：`start-dev.bat` 或 `uvicorn app.main:app --host 0.0.0.0 --port 9980 --reload --reload-dir app`（从 backend/ 目录）
- vLLM 启动：`docker compose --profile gpu up vllm`
- 文件上传限制：MAX_UPLOAD_SIZE_MB=800 / MAX_REQUEST_BODY_MB=850

## 关键数据文件

- `backend/data/report_config_seed.json` — 报表行次种子（4 套 × 6 张报表，1191 行）
- `backend/data/note_template_soe.json` — 国企版附注模板（14 章 170 节）
- `backend/data/note_template_listed.json` — 上市版附注模板（17 章 185 节）
- `backend/data/wp_account_mapping.json` — 底稿科目映射（88 条）
- `backend/data/wp_fine_rules/` — 347 个底稿精细化规则 JSON
- `backend/data/wp_system_map.json` — 底稿体系全景图（四阶段递进+11个业务循环关联）
- `backend/data/gt_template_library.json` — 363 条底稿模板索引
- `backend/data/standard_account_chart.json` — 标准科目表（166 个）

## 17 个开发阶段状态

| 阶段 | 名称 | 状态 |
|------|------|------|
| Phase 0 | 基础设施 | ✅ 完成 |
| Phase 1a | MVP Core | ✅ 完成 |
| Phase 1b | MVP Report | ✅ 完成 |
| Phase 1c | MVP Workpaper | ✅ 完成 |
| Phase 2 | 合并报表 | ⚠️ 后端完成，前端 211 个 TS 错误（developing） |
| Phase 3 | 协作功能 | ✅ 死代码已清理 |
| Phase 4 | AI 服务 | ✅ 通过统一入口间接可达 |
| Phase 5 | 扩展功能 | ✅ 完成 |
| Phase 6 | 深度集成 | ✅ 完成 |
| Phase 7 | 增强功能 | ✅ 完成 |
| Phase 8 | 数据模型优化 | ✅ 完成（性能测试待真实环境） |
| Phase 11 | 系统加固 | ✅ 完成 |
| Phase 12 | 底稿深度开发 | ✅ 完成 |
| Phase 13 | Word 导出引擎 | ✅ 完成 |
| Phase 14 | 门禁引擎 | ✅ 完成 |
| Phase 15 | 任务树编排 | ✅ 完成 |
| Phase 16 | 取证版本链 | ✅ 完成 |
| Phase 17 | 数据集版本治理 | ✅ 完成 |

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
