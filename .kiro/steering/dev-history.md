---
inclusion: manual
---

# 开发历史记录

各 Phase 的开发日志、已完成修复、已解决问题的详细记录。需要查阅历史决策或排查回归问题时用 `#dev-history` 引用。

> 此文件内容从原 memory.md 迁移，保留完整历史供溯源。
> 由于内容量大（1000+ 行），建议按需搜索关键词而非通读。

---

注意：此文件的详细内容保留在 Git 历史中（原 memory.md 的 "技术决策(2026-04-12)" 至文件末尾的全部内容）。

## 关键里程碑索引

### 2026-04-12 ~ 04-14：Phase 0-1 基础建设
- 数据库迁移 10 张表 + ORM 模型 + 项目向导 + 科目管理 + 映射引擎
- 四表穿透查询 + 试算表计算引擎 + 调整分录管理

### 2026-04-14 ~ 04-15：查账链路优化
- 百万行数据优化（批量化 + COPY 命令 + 流式导入）
- 四表字段扩展（20 列）+ 穿透查询性能基准（442ms→4ms）
- 科目映射 7 级优先匹配 + 标准科目表 120→166 个

### 2026-04-15 ~ 04-16：Phase 6 深度集成
- 人员库 + 团队委派 + 工时管理 + 管理看板（ECharts）
- 底稿落地 4 阶段（模板→预填充→在线编辑→工作台）
- 审计程序裁剪与委派 + 四种角色看板体系

### 2026-04-17 ~ 04-18：Phase 7 增强 + 系统复盘
- 21 个需求 193 个子任务全部完成
- 外部评审报告 → 16 项修复 → 五根主梁认证硬化（28%→100%）
- WOPI 企业级重写 + 复核状态拆分 + 在线优先+离线兜底

### 2026-04-18 ~ 04-19：Phase 8 + 企业级加固
- 数据模型优化 + EventBus debounce + 公式超时控制
- JWT refresh rotation + LLM 限流熔断 + 事件总线 Redis 持久化
- 合并差额表批量计算重构（N×M→6 次查询）

### 2026-04-19 ~ 04-23：大数据导入改造
- smart_import_engine 通用智能导入 + calamine 加速（百万行 66s）
- 数据集版本治理（LedgerDataset staged→active→superseded）
- 三层校验模型（Technical + Business + Activation Gate）

### 2026-04-25 ~ 04-26：Phase 11 系统加固
- 死代码清理（31 服务 + 16 测试删除）+ 前端 API 统一化
- Alembic 迁移链合并 + main.py 路由分组重构
- 合并报表同步→异步改造 + E2E 测试 3 条链路

### 2026-04-26 ~ 04-27：Phase 12-13 底稿深度 + Word 导出
- 审计说明 LLM 生成 + QC-15~18 内容级规则 + 复核工作台
- GTWordEngine 致同排版 + 报表快照 + 模板填充 + ZIP 打包

### 2026-04-29：Phase 14-16 企业级治理
- 门禁引擎 + 操作留痕 + SoD 职责分离 + QC-19~26
- 四级任务树 + 事件总线 + 问题单 SLA
- 版本链 + 离线冲突 + 一致性复算 + 取证校验

### 2026-04-29：公式体系 + 四式联动
- 统一公式语法（Excel/坐标/跨表）+ 拓扑排序 + 审计留痕
- Excel↔HTML↔Word↔structure.json 四式联动
- 模板三层体系 + 知识库升级 + RAG 辅助生成

### 2026-04-30 ~ 05-02：报表/附注/底稿精细化
- 报表行次从模板 Excel 提取 1191 行（4 套 × 6 张）
- 附注模板从 md 全量提取（国企 170 节 / 上市 185 节）
- 底稿精细化规则 347 个 JSON（12 个手工精修 + 335 个通用增强）
- ONLYOFFICE 容器恢复 + WOPI 全链路验证

## 已知遗留问题

- ai_plugin_service 8 个外部 API 为 stub（设计如此，需外部服务）
- sign_service level3 CA 证书 / regulatory_service 监管格式转换（需外部对接）
- Phase 8 性能测试待真实 PG + 大数据量环境执行
- WorkpaperEditor.vue 有 1 个预存的 Univer locale 类型声明问题（@univerjs 包问题，非本项目代码）
- Element Plus 按需导入后 bundle 仍有大文件（WorkpaperEditor 5.7MB，AttachmentManagement 4.8MB），主要是 Univer 和 xlsx 库

### 2026-05-02：附注校验公式导入 + 底稿精细化规则打磨

**附注校验公式：**
- 修复 `_parse_check_presets_md.py` 解析脚本：支持上市版 🔸 标记、FS/FK/FO 编号、继承国企版公式
- 国企版 757 条 + 上市版 804 条（继承全部国企版 + 差异替换 + 特有追加）
- `NoteValidationEngine.validate_all` 增强：加载预设公式按科目分发，支持 template_type 参数
- 上市版空表格排查：仅 3 个第五章子表格为空，其余为政策描述型无需数据行

**底稿精细化规则打磨（31→36→77）：**
- 手动精修：L8 财务费用、N4 税金及附加、N5 所得税费用、D5 应收款项融资、K8 销售费用
- 批量精修 44 个科目：G2-G14（投资循环）、H4-H10（固定资产循环）、I2/I5/I6（无形资产）、J2（薪酬）、K2-K13（管理循环）、L4-L7（债务循环）、M1/M3/M7-M10（权益循环）、N3（递延所得税负债）、D6/D7（合同资产/负债）
- 精修内容：补充 key_rows、report_row 映射、精确 cross_references、增强 audit_checks、版本升级 R1→R2
- 剩余 270 个为函证程序/子底稿/控制测试等通用增强版（无需 key_rows 精修）

### 2026-05-02：底稿体系全景图 + API 增强

- 新增 `wp_system_map.json`：四阶段递进（准备→控制测试→实质性→完成）+ 11 个业务循环 B→C→实质性关联 + 特定项目分组 + 跨阶段关联
- 新增 API `/api/wp-fine-rules/system-map`：返回体系全景数据供前端可视化
- 增强 `list_fine_rules`：新增 cycle/quality/version/account_codes 字段，支持过滤
- 新增 API `/api/wp-fine-rules/summary`：按循环分组统计
- 22 个精修科目版本号统一升级 R1→R2

### 2026-05-02：底稿精细化规则深度增强（第二轮）

深度审计发现三大问题并修复：
- 通用占位符 key_rows（47个）→ 全部替换为真实科目行名（如"应收账款坏账损失""公司债券"等）
- 模糊 cross_references（63个）→ 精确化为行列坐标（如 `.total` → `.R14.C5`）
- 缺失报表引用（51个）→ 全部补充 `REPORT('BS-xxx','期末')` 交叉引用和 report_row 映射
- 77 个实质性程序科目全部增强，347 个 JSON 格式验证通过

### 2026-05-02：底稿 key_rows 架构重构（第三轮）

- 问题：之前硬编码了具体明细行名（如"公司债券""中期票据"），但实际审计中每个企业明细行完全不同
- 方案：key_rows 只保留结构性行（合计/小计/减：/试算/差异/段标题），明细行改为 detail_discovery 动态发现
- detail_discovery 规则：mode=auto, start_row=N, end_rule=before_first_total, skip_empty=true
- 引擎 _extract_summary_rows 增强：支持 detail_discovery 自动扫描 start_row 到合计行之间的所有非空行
- 59 个科目完成重构，347 个 JSON 格式验证通过

### 2026-05-02：附注表格动态填充架构

统一设计原则：数据动态提取 + 结构参照模板 + 校验基于结构
- disclosure_engine._build_table_data 重构：支持 is_dynamic_detail 标记，明细行从底稿 fine_summary 动态提取
- _preload_data_for_notes 增强：新增 _wp_fine_cache 缓存底稿精细化明细行
- 取数优先级：底稿 fine_summary 明细行 > 底稿 audited_amount > 试算表 > 模板预设行
- 合计行回填逻辑改进：支持多段合计（每个合计行只汇总上一个合计行到当前行之间的明细）

### 2026-05-02：项目向导 bug 修复（3 处）

- `ProjectCreateResponse` schema 缺少 `template_type` 字段 → 已补充
- `_to_project_response()` 手动构造响应时漏传 `template_type` → 已补充（注意：手动构造模式新增字段时需同步更新此函数）
- `update_step` 状态检查过严：已确认项目（planning）无法编辑基本信息 → basic_info 步骤放宽为 created/planning 均可编辑
- `MiddleProjectList.loadProjects` 加载后自动恢复上次选中项目（从 localStorage），修复向导跳回后旧数据残留

### 2026-05-02：统一 Excel 导入框架

- 新增 `import_template_service.py`：7 种导入类型（adjustments/report/disclosure_note/workpaper/formula/staff/trial_balance），每种含列定义+模板生成+格式校验+数据解析
- 新增 `routers/import_templates.py`：4 个 API（类型列表/模板下载/格式校验/导入入库），_dispatch_import 按类型分发到各业务服务
- 新增 `UnifiedImportDialog.vue`：三步式导入弹窗（上传→校验预览→导入结果），支持模板下载、错误提示、数据预览
- 已集成 7 个页面：调整分录、报表、人员库、附注编辑器、底稿列表、试算表、公式管理
- 人员库旧导入逻辑（triggerImport/handleImportFile）已替换为统一组件
- Bug 修复：ProjectCreateResponse 缺 template_type 字段 + _to_project_response 漏传 + update_step 状态检查过严 + DisclosureEditor 重复代码块 + MiddleProjectList 自动恢复选中

### 2026-05-02：Univer 替换 ONLYOFFICE + 统一导入框架 + 多项 Bug 修复

**Univer 替换 ONLYOFFICE：**
- WorkpaperEditor.vue 完全重写为 Univer 纯前端方案
- 新增 xlsx_to_univer.py（xlsx→IWorkbookData）+ univer_to_xlsx.py（IWorkbookData→xlsx 回写）
- 新增 /univer-data API（加载）+ /univer-save API（完整保存链路：xlsx回写+structure.json+版本快照+审计留痕+事件发布）
- 新增前端依赖：@univerjs/presets + @univerjs/preset-sheets-core + opentype.js
- Vite alias: opentype.js/dist/opentype.module.js → opentype.js/dist/opentype.mjs
- 全面清理 ONLYOFFICE 引用：WopiPoc/UniverTest/test-oo.html 删除，_trace_oo.py 删除
- WOPI 端点/配置保留向后兼容，所有前端引用标注 @deprecated
- docker-compose.yml ONLYOFFICE 服务加向后兼容注释
- .env/.env.example 删除 VITE_ONLYOFFICE_URL

**统一 Excel 导入框架：**
- import_template_service.py：7 种模板（adjustments/report/disclosure_note/workpaper/formula/staff/trial_balance）
- import_templates.py：4 API（类型列表/模板下载/格式校验/导入入库），事务保护+失败行反馈
- UnifiedImportDialog.vue：三步弹窗（上传→校验预览→导入结果），追加/覆盖模式
- 已集成 7 个页面：调整分录/报表/人员库/附注编辑器/底稿列表/试算表/公式管理
- 14 项加固：数值校验/事务保护/RFC5987文件名/示例行宽松跳过/失败行反馈/覆盖追加模式/重试按钮

**Bug 修复：**
- ProjectCreateResponse 缺 template_type + _to_project_response 漏传
- update_step 状态检查过严（planning 状态无法编辑 basic_info）
- MiddleProjectList 自动恢复上次选中项目
- DisclosureEditor 重复代码块（projectOptions/loadProjectOptions）
- FourColumnCatalog 项目树始终显示（去掉 >1 限制）

### 2026-05-04：全局组件库建设（feature/global-component-library 分支）

**新建全局工具（7 个文件）：**
- `utils/formatters.ts`：fmtAmount/fmtAmountUnit/fmtDate/fmtDateTime/fmtPercent/toNum + 金额单位换算(yuan/wan/qian) + FontSize 预设(xs/sm/md/lg)
- `composables/useFullscreen.ts`：全屏切换+ESC退出，替代17个组件各自实现
- `composables/useTableSearch.ts`：表格内搜索替换(Ctrl+F)，keyword/search/next/prev/replace/cellMatchClass
- `composables/useCellSelection.ts`：增强拖拽框选(setupTableDrag DOM事件委托)+Shift范围选+selectionStats+isCellSelected+右键保持选区+_skipNextCellClick防重复
- `stores/displayPrefs.ts`：金额单位/字号/小数位/零值/负数红色/变动高亮，localStorage持久化
- `components/common/SelectionBar.vue`：选中区域求和状态栏(count/sum/avg/max/min)+操作提示
- `components/common/TableSearchBar.vue`：搜索栏UI(致同品牌紫色风格)+Ctrl+F拦截浏览器默认搜索
- `components/common/CommentTooltip.vue`：批注hover气泡(el-tooltip包裹，300ms显示)

**全局集成（24 个文件修改）：**
- ThreeColumnLayout 顶栏：Aa 显示设置面板（单位/字号/小数位/零值/负数红色/变动高亮 6项）
- 5 核心模块全部接入：TrialBalance/ReportView/DisclosureEditor/ConsolidationIndex/ConsolNoteTab
  - displayPrefs（fmt+字号+单位标注+条件格式）
  - useCellSelection setupTableDrag（鼠标拖拽框选+Shift范围选+右键保持选区）
  - SelectionBar（选中区域求和状态栏）
  - TableSearchBar + Ctrl+F（TrialBalance/ReportView/DisclosureEditor）
  - CommentTooltip（ReportView 本期/上期金额列）
  - 项目列 fixed + 金额列 sortable（ReportView）
- 14 个 worksheet 组件：useFullscreen + fmtAmount 迁移
- CellContextMenu：选中样式升级（Excel风格连续区域淡紫色半透明+边缘边框+单选填充柄）+ 复制选中区域/复制整表区分
- global.css：.gt-fullscreen/.gt-amount--negative/.gt-amount--highlight/.gt-selection-bar/.gt-search-match/.gt-dragging
- 5 模块 scoped 选中样式（tb/rv/de/gt-cell--selected）全部删除，统一使用全局 gt-ucell--selected

**踩坑记录：**
- Vue 3 子组件 prop 不能 v-model 绑定（Vite 生产构建报错），需 :model-value + @update:model-value
- el-table setupTableDrag mousedown 和 cell-click 重复触发，需 _skipNextCellClick 标志位
- Shift+点击必须在 setupTableDrag(mousedown) 和 onXxxCellClick(cell-click) 两处传递 range=true
- Ctrl+F 不能用 shortcuts.ts CustomEvent（浏览器默认搜索抢先），需各组件内 addEventListener + preventDefault
- 搜索栏必须在表格上方（用户看不到下方的）

**构建验证：** vue-tsc 零错误，Vite 构建通过（31文件 +1997/-583行），git 推送 feature/global-component-library 分支

### 2026-05-05：全局化增强项目完成（4 Sprint，46 Task）

**Sprint 1（10 Task）— 全局化收尾+快速见效：**
- formatters.ts 替换 22 个组件的本地格式化函数
- displayPrefs 接入 13 个 worksheet 组件（单位/字号跟随全局设置）
- CommentTooltip 接入 4 个核心模块（DisclosureEditor/ConsolidationIndex/ConsolNoteTab/TrialBalance）
- confirm.ts 语义化确认弹窗（confirmDelete/confirmBatch/confirmDangerous）
- statusMaps.ts + GtStatusTag 状态标签集中管理
- useEditMode composable（查看/编辑切换+未保存提示+路由拦截）
- ExcelImportPreviewDialog 通用导入预览弹窗
- operationHistory 接入 Adjustments + RecycleBin
- GtAmountCell 金额单元格组件（displayPrefs+可点击+hover高亮）

**Sprint 2（9 Task）— 核心基础设施：**
- mitt 事件总线替代 CustomEvent（类型安全，删除 _redispatched 补丁）
- useProjectStore Pinia（路由自动同步 projectId/year/standard）
- apiPaths.ts 集中管理 500+ API 路径（40+ 业务域）
- 后端响应格式统一（修复 5 个双重包装路由，清理前端 30+ 处 data?.data 兼容代码）
- usePermission + v-permission 指令（角色权限体系）
- 路由守卫统一（认证+权限+项目上下文+developing 拦截）
- API 调用统一收口（21 个 view/component 文件迁移到 apiProxy）
- 批量操作场景优化（batch_mode + batch-commit 端点）
- shortcuts.ts 接入各模块（Ctrl+S/Ctrl+Z 全模块生效）

**Sprint 3（14 Task）— 组件层+后端统一：**
- GtToolbar/GtPageHeader/GtInfoBar 标准化页面头部（替换 3 个模块的重复横幅 CSS）
- useExcelIO composable（14 个 worksheet 统一导入导出）
- useTableToolbar composable（增删行/多选/导入导出/复制）
- useDictStore + 后端 /api/system/dicts（枚举字典 sessionStorage 缓存）
- 后端 PaginationParams/SortParams 统一（5 个高频列表 API）
- 后端 BulkOperationMixin（批量删除/审批）
- 后端 @audit_log 装饰器（before/after diff，接入删除/审批/状态变更）
- SharedTemplatePicker 扩展到 4 个 configType
- useCopyPaste composable（HTML+纯文本双格式，TrialBalance+ReportView）
- useKnowledge + KnowledgePickerDialog（AI 续写知识库上下文）
- useAutoSave 草稿恢复（30s 定时 localStorage，3 个模块）
- useLoading + NProgress（全局进度条，路由+HTTP 拦截器）
- useAddressRegistry Store（CellSelector/FormulaRefPicker 数据源统一）

**Sprint 4（10 Task）— 高阶组件+验证+优化：**
- GtEditableTable 高阶可编辑表格（360行，内置 useCellSelection/useLazyEdit/useEditMode/useFullscreen/useTableToolbar/useCopyPaste/SelectionBar/CellContextMenu/CommentTooltip，列配置声明式，支持 hidden/validator/locked/groupBy/filterable）
- 端到端验证脚本（test_e2e_audit_flow.py，11 步全流程 API 测试）
- 数据库 migration 机制（migration_runner.py，V*.sql 版本化脚本，启动时自动执行）
- 合并模块集成测试（test_consolidation_chain.py，合并范围→试算→抵消→差额→报表）
- 事件链路失败通知 + SSE 全局接入（SYNC_FAILED 事件，SyncStatusIndicator 顶栏指示器，失败详情抽屉）
- 架构优化：Element Plus unplugin 按需导入、ResponseWrapperMiddleware 大响应跳过、POST 防重复提交、Locust 压力测试脚本
- 用户体验：GtConsolWizard 合并向导步骤条、500 重试 loading 提示、423 锁定详情、useKeyboardNav 键盘导航
- 表格交互增强：GtPrintPreview 打印预览、CommentThread 批注线程（回复链）
- 功能完善：equity_method_service.py 模拟权益法（6 项改进）、elimination_service 汇总中心（5 区域）、内部抵消表自动汇总

**构建验证：** vue-tsc 零错误，Vite 构建通过（32.77s），git 推送 feature/global-component-library 分支

**已知遗留问题（Sprint 4 后）：**
- WorkpaperEditor.vue 有 1 个预存的 Univer locale 类型声明问题（@univerjs 包问题，非本项目代码）
- Element Plus 按需导入后 bundle 仍有大文件（WorkpaperEditor 5.7MB，AttachmentManagement 4.8MB），主要是 Univer 和 xlsx 库
