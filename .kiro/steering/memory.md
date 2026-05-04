---
inclusion: always
---

# 持久记忆

每次对话自动加载。详细架构见 `#architecture`，编码规范见 `#conventions`，开发历史见 `#dev-history`。

## 用户偏好（核心）

- 语言：中文
- 部署：本地优先、轻量方案
- 启动：`start-dev.bat` 一键启动后端 9980 + 前端 3030
- 打包：build_exe.py（PyInstaller），不要 .bat
- 功能收敛：停止加新功能，核心 6-8 个页面做到极致，空壳标记 developing
- 前后端联动：不能只开发后端不管前端
- 删除必须二次确认，所有删除先进回收站
- 一次性脚本用完即删
- 文档同步：功能变更后同步更新需求文档
- 记忆拆分：memory.md 只放精简状态+待办，技术决策→architecture.md，规范→conventions.md，修复记录→dev-history.md，每次对话自动拆分
- 底稿精细化：每个科目需要单独规则配套，利用 LLM 辅助
- 底稿体系展示：要体现 B→C→实质性的循环递进关系，可视化、逻辑感强，包括准备和完成阶段
- 目标并发规模 6000 人，在线编辑考虑混合方案：日常用纯前端表格组件（Luckysheet/Univer）无并发限制 + 少数完整 Excel 场景走 ONLYOFFICE
- 合并报表等子页面布局要参照项目的三栏布局（左侧导航+右侧内容+可拖拽分隔线），不要用纯 Tab 平铺
- 每个表都要有详细的操作指引（步骤编号引导），让用户知道要干什么、怎么干、数据从哪来到哪去
- 数据提取填充优先用本地化脚本（按科目名匹配），辅以 LLM 模型（智能填充按钮）
- 表格列宽要足够大让内容完整显示，不折行不省略号截断，宁可加宽列也不要 ellipsis
- 企业代码字段统一使用统一社会信用代码（18位），placeholder 示例用真实格式如 91500000MA5UQXXX0X
- 表格编辑需支持查看/编辑模式切换：查看模式纯文本可选中复制，编辑模式 el-input 逐单元格编辑

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，Ollama 0.11.10
- PG 141 张表，Redis 6379，后端 9980，前端 3030
- vLLM Qwen3.5-27B-NVFP4 端口 8100（enable_thinking: false）
- ONLYOFFICE 端口 8080（JWT_ENABLED=false，WOPI 协议）
- Paperless-ngx 端口 8010（admin/admin）
- 测试用户：admin/admin123（role=admin）
- WOPI_BASE_URL 必须用 http://host.docker.internal:9980/wopi（Docker 容器内）
- uvicorn --reload-dir app（限制监控范围，避免 347 个 JSON 拖慢）
- MAX_UPLOAD_SIZE_MB=800 / MAX_REQUEST_BODY_MB=850

## 当前系统状态（2026-05-04）

- 17 个开发阶段中 16 个完成，前端 vue-tsc 零错误（tsconfig 关闭 noUnusedLocals/noUnusedParameters，从 366 降到 0）
- 旧版合并模块已清除：删除 11 个 views/consolidation/ + 14 个旧组件 + 1 个旧 store（共 26 个文件），当前合并模块统一由 ConsolidationIndex.vue 承载
- Vite 构建验证通过（44.97s），vue-tsc 零错误
- git 已推送 feature/global-component-library 分支（31文件 +1997/-583行）：7个新建全局工具 + 24个组件修改
- 全局组件库已接入：useFullscreen(17组件) + formatters/displayPrefs(5核心+14worksheet) + useCellSelection拖拽框选(5核心) + useTableSearch(3模块) + SelectionBar(5模块) + TableSearchBar(3模块) + CommentTooltip(ReportView) + 条件格式(3模块) + 右键保持选区(5模块) + 选中样式统一(5模块)
- 后端约700路由正常加载，0 个 stub 残留
- PG 144 张表（consol_cell_comments + account_note_mapping + formula_audit_log），formula_audit_log 路由 2 个 API（GET 查询+POST 记录）
- 汇总穿透已接真实数据：POST /api/report-config/drill-down 从各子企业 consol_worksheet_data 按 row_code 提取实际金额，降级保留持股比例估算
- 附注 refresh API 三级匹配：精确科目名 → account_note_mapping 映射表 → 模糊包含匹配（len>=2）
- 审计员 8 步全流程理论可走通（导入-查账-调整-试算表-底稿-附注-报告-Word导出）
- 测试：公式解析器单元测试 28 个全部通过（test_formula_parser.py），端到端冒烟测试 14 个 API（test_smoke_e2e.py，需后端在线）
- 附注 8 种校验器全部做实，预设公式国企 757 条 + 上市 804 条已集成到引擎，QC 28 条规则全部做实
- 底稿精细化规则 347 个 JSON（77 个 A 级精修 + 270 个 C 级程序表），明细行动态发现（detail_discovery），全部 v2025-R2
- 报表 4 套 x 6 张，1191 行种子数据
- 附注模板国企 14 章 170 节 / 上市 17 章 185 节
- 合并附注种子数据：seed_consol_note_sections.py 解析附注模板 md 生成 JSON（国企 91 父章节 221 表格节点，上市 80 父章节 282 表格节点），每个表格独立节点，标题取表格上方最近的 md 标题
- 合并附注 API：/api/consol-note-sections/{standard} 返回按父章节分组的树形，叶子节点是单个表格；用户数据存 consol_note_data 表（project_id+year+section_id+JSONB）
- 合并附注前端：左侧树按父章节折叠，每个叶子点击后右侧只显示一个表格（不分页），支持全屏/导出模板/导出数据/导入Excel/保存/增删行/多选删除
- 合并附注公式刷新：POST /api/consol-note-sections/refresh/{project_id}/{year}/{section_id}，从试算表按科目名匹配+按表头（期末/期初/借方/贷方）自动填充对应列
- 合并附注公式管理：工具栏 ƒx 按钮打开全局公式管理器定位到当前章节，批量弹窗支持导出公式模板/导入公式/一键取数计算（apply-formulas API）
- 合并附注全审和单表审核按钮保留在工具栏（✅），批量弹窗中不重复放审核按钮
- 合并附注全审：POST /api/consol-note-sections/audit-all/{project_id}/{year}，规则含合计行校验+试算表交叉校验，结果弹窗显示+导出Excel
- 合并附注单表审核：POST /api/consol-note-sections/audit/{project_id}/{year}/{section_id}，对当前表格执行公式审核，弹窗同全审格式
- 合并附注多行表头：md 中分隔行后首列为空的行识别为子表头，forward-fill 合并单元格后用 '/' 连接层级（如 期末数/账面余额/金额），multi_header 字段保留原始多行结构
- 合并附注树形导航移到第3栏 ConsolCatalog（附注 tab），右侧内容区占满宽度；批量操作弹窗支持一键导出全部数据/模板、一键导入（按 Sheet 名匹配章节）
- 四栏视图切换：子页面可通过 CustomEvent('gt-switch-four-col') 通知 ThreeColumnLayout 激活四栏模式并展开 catalog 栏
- ThreeColumnLayout catalog 栏去掉 gt-catalog-header 和 gt-catalog-body 包裹层，slot 直接作为 flex 子元素，避免多层 overflow 冲突导致 el-tabs 点击和收起按钮失效
- ThreeColumnLayout resizer 的 ::after 伪元素（±3px 透明扩展区）会遮挡相邻栏的点击事件，已移除；catalog z-index:1 高于 resizer z-index:5 的默认层
- ThreeColumnLayout 切换四栏模式时必须强制 catalogCollapsed=false，否则 localStorage 持久化的折叠状态会导致 catalog 不显示
- gt-switch-four-col 事件重新派发必须加 _redispatched 标记防止 ThreeColumnLayout↔ConsolCatalog 无限循环（曾导致 UI 冻结）
- 事件通信仍使用 CustomEvent（Pinia store 迁移已回退：deep watch + 自动解包导致渲染崩溃，需要更完善的测试环境配合后再尝试）
- 全屏功能用 Teleport to="body" 实现（非 position:fixed），避免被祖先 overflow/transform 裁剪导致全屏失效
- 公式体系完整（三分类 + 跨表引用 + 拓扑排序 + 审计留痕）
- 公式执行引擎 Phase1-3 全部完成：Phase1 解析器+求值器，Phase2 前端对接，Phase3 跨模块引用(REPORT/NOTE/CONSOL)+审计日志(formula_audit_log)+并行执行(asyncio.gather)
- 公式解析器踩坑：NUMBER 正则禁止含负号前缀（`-?\d+` 会把 `100-50` 解析为 `100` 和 `-50`），负号由 MINUS token + UnaryNode 处理
- 公式跨模块查询：REPORT 必须带 project_id 过滤；NOTE 列匹配用精确优先+组合降级；CONSOL 支持 2 参数汇总和 3 参数单行取值
- 公式 API：execute-formula + execute-formulas-batch + formula-audit-log(GET/POST)，共 8 种函数（TB/WP/AUX/PREV/SUM_TB/REPORT/NOTE/CONSOL）
- 公式管理（FormulaManagerDialog）已提升到全局顶部导航栏（ThreeColumnLayout），所有模块共享
- 公式管理树形导航已增加"合并报表"分类（7张表 CI/CC/CE/CN/CS/CX/CK 编码）+ 表间审核"合并↔报表"规则
- 各表的"ƒx 公式"按钮与全局公式管理中心必须双向联动同步：任一处修改公式后另一处自动更新，所有模块统一
- 公式联动机制：CustomEvent('gt-open-formula-manager') 打开 + CustomEvent('gt-formula-changed') 广播变更，各模块监听刷新
- 企业级治理完整（门禁/留痕/SoD/版本链/一致性复算）
- 合并工作底稿前端 9 个组件已创建（worksheets/），集成到 ConsolidationIndex 第一个 Tab
- 合并工作底稿 16 个组件全部就绪（0编译错误），前后端联动持久化完成，7条跨表数据流正常，三栏股比变动+拖拽+折叠

## 活跃待办

### 最高优先级
- 用真实审计项目端到端验证（导入→查账→调整→试算表→底稿→附注→报告→Word导出 全流程）
- 引入数据库 migration 机制（create_all + 手动 ALTER TABLE 上线后不可持续，需版本化 SQL 脚本管理）
- 事件链路失败通知机制（五环联动中任一环失败后续全断，用户无感知，需前端可见的同步状态面板）
- API 调用方式统一收口到 apiProxy.ts（当前 authHttp/http/api 三套并存，新人易踩坑）
- 合并模块集成测试（最复杂模块测试最薄弱，至少覆盖：合并范围→试算表→抵消分录→差额表→合并报表主线）
- 批量操作场景优化：批量调整分录应支持"批量提交"模式，一次性提交后统一触发一次重算，避免逐笔触发全链路

### 功能完善（中期）
- 模拟权益法改进：❶净资产联动取期末值 ❷当期变动按比例自动提取 ❸按企业展开独立模拟 ❹期初从上年底稿带入 ❺底部按科目汇总分录传给抵消分录表 ❻基本信息表保存后同步consol_scope
- 合并抵消分录表汇总中心：权益抵消+损益抵消+交叉持股+内部抵消自动导入+用户自定义分录，5个区域
- 3张内部抵消表生成的抵消分录自动汇总到合并抵消分录表（往来→BS科目，交易→IS科目，现金流→CF项目）
- 公式管理中心左侧数据源树待统一补充完善（各模块开发完毕后更新）
- 地址坐标库（CellSelector/FormulaRefPicker）需全局联动：新增表样后引用下拉同步更新 → 由全局化❾ useAddressRegistry 承接
- 模板管理（SharedTemplatePicker）需全局联动：任一模块保存模板后其他模块可见 → 由全局化⑪ 扩展承接

### 全局化改造
#### 已完成
- ✅ useFullscreen composable：16个组件迁移完成（13 worksheet + TrialBalance + ReportView + DisclosureEditor），ConsolNoteTab 待补
- ✅ formatters.ts 基础函数：fmtAmount/fmtAmountUnit/fmtDate/fmtDateTime/fmtPercent/toNum/unitLabel + AmountUnit/FontSize 类型
- ✅ displayPrefs Store：金额单位(yuan/wan/qian)+字号(xs/sm/md/lg)+小数位+零值显示，localStorage 持久化
- ✅ ThreeColumnLayout 顶栏"Aa"显示设置面板：单位/字号/小数位/零值 四项切换
- ✅ useCellSelection 增强：Shift 范围选+鼠标拖拽框选(startDrag/updateDrag/endDrag)+registerCellValueGetter+矩形复制
- ✅ TrialBalance 完整接入 displayPrefs：18处 fmt 替换+字号绑定+单位标注（示范模块）
- ✅ global.css .gt-fullscreen 统一全屏类

#### 进行中
- formatters.ts 剩余替换：Drilldown/CFSWorksheet/Adjustments/Misstatements/Materiality/LedgerPenetration 等20+组件的 formatAmount/fmtDate/fmtTime 替换为全局函数
- useCellSelection 拖拽框选接入：✅ setupTableDrag 已接入全部 5 个核心模块（TrialBalance/ReportView/DisclosureEditor/ConsolidationIndex/ConsolNoteTab）
- displayPrefs 已接入 5 个核心模块（TrialBalance/ReportView/DisclosureEditor/ConsolidationIndex/ConsolNoteTab），13 worksheet 组件待接入
- SelectionBar 已接入 5 个核心模块
- TableSearchBar 已接入 TrialBalance/ReportView/DisclosureEditor（ConsolidationIndex/ConsolNoteTab 用 placeholder）
- ConsolNoteTab useFullscreen 已补上（本轮完成）

#### 待开始
- ❷ mitt 事件总线替代 CustomEvent：类型安全 Events 映射，200字节零依赖，解决 _redispatched 补丁问题（1天）
- ❸ useProjectStore（Pinia）：统一 projectId/year/standard/clientName，从路由自动同步，替代各组件自行解析（1天）
- ❹ useTableToolbar composable：增删行/多选/导入导出Excel/复制表格，覆盖20+表格组件（1天）
- ❺ useEditMode composable：查看/编辑切换+isDirty+离开提示+onBeforeRouteLeave 拦截，统一推广到所有模块（半天）
- ❻ API 路径集中管理（apiPaths.ts）：所有路径常量集中定义，18个service文件引用，路径变更只改一处（1天）
- ❼ 枚举字典 Store（useDictStore）：后端 /api/system/dicts 一次性返回所有枚举{key,label,color}，前端 sessionStorage 缓存，替代各模块硬编码中文标签（2天含后端）
- ❽ 后端响应格式彻底统一：路由只返回业务数据+中间件统一包装+前端统一解包，删除所有 data?.data ?? data 兼容代码（1天）
- ❾ 地址坐标前端 Store（useAddressRegistry）：对接后端 address_registry，CellSelector/FormulaRefPicker 统一数据源，新增表样后自动刷新（1天）
- ⑩ useExcelIO composable：15+组件重复 import('xlsx')+book_new+writeFile，统一 exportTemplate/exportData/parseFile/onFileSelected+导入预览弹窗+说明sheet（1天）
- ⑪ SharedTemplatePicker 扩展到全模块：当前仅3处使用，需覆盖公式配置/附注模板/合并范围/抵消分录模板/QC规则/科目映射共8个configType（1天）
- ⑫ useKnowledge composable + KnowledgePickerDialog：全局知识库调用（search/getDocContent/pickDocuments/buildContext），供附注编辑/AI续写/底稿编制/审计报告等模块引用上下文（1.5天）
- ⑬ GtToolbar 标准工具栏组件：组合导出模板/导出数据/导入Excel/全屏/公式/SharedTemplatePicker/查看编辑切换/显示设置，20+页面统一工具栏布局（1天）
- ⑭ GtEditableTable 高阶组件（中期）：内置查看/编辑切换+选中+拖拽框选+右键+批注+增删行+全屏+懒加载+小计+ExcelIO+displayPrefs，20+表格逐步迁移（3-5天）
- ⑮ ExcelImportPreviewDialog 通用导入预览弹窗：隐藏file input + 解析xlsx + 预览表格 + 统计(total/valid/skipped) + 确认追加，替代15+组件各自的导入弹窗（半天）
- ⑯ useCopyPaste composable：表格复制（选中区域→制表符分隔文本）+粘贴（从Excel粘贴多单元格解析写入），配合 useCellSelection 使用（1天）
- ⑰ 模板市场全局入口：TemplateMarket 当前仅扩展页面可达，需在各模块工具栏加"从市场引用"快捷入口（半天）
- ⑲ usePermission + v-permission 指令：前端按钮级权限控制，对接 roleContextStore，当前仅1个组件做了 canEdit 判断（1天）
- ⑳ useLoading composable + NProgress 全局进度条：解决50+处 loading.value 手动管理、并发请求提前关闭、路由切换无过渡问题（1天）
- ㉑ 表格列配置声明式管理：列定义从模板抽到数据对象（prop/label/width/formatter），配合⑭ GtEditableTable 数据驱动渲染（中期）
- ㉒ 后端 PaginationParams/SortParams 统一：当前 page/page_size、offset/limit、skip/take 混用，统一为 FastAPI 依赖注入（1天）
- ㉓ 后端批量操作 BulkOperationMixin：批量删除/更新统一 ID 校验+事务管理+部分失败处理（1天）
- ㉔ 后端审计日志装饰器（服务层）：关键业务操作（删除/审批/状态变更）记录 before/after diff，比中间件粒度更细（1.5天）
- ㉕ 路由守卫统一（router beforeEach）：权限守卫（角色限制路由）+项目上下文自动加载+未保存变更拦截，配合❸useProjectStore+❺useEditMode（1天）
- ㉖ statusMaps.ts + GtStatusTag 组件：10+组件各自定义 statusTagType/statusLabel，统一为 {label,tag} 映射表 + `<GtStatusTag type="wp" :status="row.status" />` 组件（半天）
- ㉗ shortcuts.ts 接入各模块：已有 ShortcutManager + 13 个默认快捷键（Ctrl+S/Z/F/G/E 等），但通过 CustomEvent 分发后各组件未监听，需逐模块接入（1天）
- ㉘ useAutoSave 自动保存/草稿恢复：当前仅 StructureEditor 有5秒debounce自动保存，编辑量大的页面需 localStorage 草稿+恢复提示（1天）
- ㉙ TanStack Query 接入高频 API：已引入但几乎未使用 useQuery/useMutation，高频读取API应接入（2天）
- ㉚ confirm.ts 语义化确认弹窗：30+处 ElMessageBox.confirm 模式一致，封装 confirmDelete/confirmBatch/confirmDangerous（半天）
- ㉛ sse.ts 全局连接接入：已有完整 SSE 封装（createSSE+fetchSSE+自动重连+token），但无组件使用，需在 ThreeColumnLayout 创建全局连接+分发到 mitt 事件总线（1天）
- ㉜ ErrorBoundary 细粒度错误隔离：当前仅 DefaultLayout 一层，需在 Tab/弹窗/功能区块加错误边界（半天）
- ㉝ useExport 统一导出服务：PDF/Word/Excel/打包导出统一入口（1.5天）
- ㉞ GtPageHeader 通用页面横幅：紫色渐变横幅（返回+标题+GtInfoBar+操作按钮 slot），替代 gt-tb-banner/gt-rv-banner/gt-de-banner 等5+套重复实现（1天）
- ㉟ GtInfoBar 信息栏组件：单位选择+年度选择+模板选择+徽章+分隔线，每个页面横幅内重复写的 el-select+info-sep+info-badge 统一封装（半天）
- ㊱ GtAmountCell 金额单元格组件：跟随 displayPrefs 格式化+可点击穿透+hover 高亮，替代模板中重复的 `{{ fmt(row.xxx) }}` + class 绑定（半天）
- ㊲ operationHistory.ts 接入：已有撤销功能（execute+undo+ElNotification 带撤销按钮），需接入删除/调整分录等关键操作（半天）
- ㊳ VirtualScrollTable 接入 formatters：formatCell 需改用全局 fmtAmount 替代内联 toLocaleString（10分钟）

### 架构优化（低优先级）
- consol_note_sections.py 暂不拆分（1003行但内部分隔清晰，拆分风险大于收益）
- 前端主 bundle 优化（Element Plus 按需导入+图标按需引入，当前 index.js 1.3MB）
- ResponseWrapperMiddleware 性能：每个响应读取完整 body 再重新包装，大响应（导出 Excel）是瓶颈，考虑跳过大文件响应
- POST 请求防重复提交机制（当前 pendingMap 去重仅对 GET 生效）
- 上线前压力测试：重点关注批量导入、合并重算、报表导出三个重 IO 场景

### 用户体验（持续）
- 合并模块用户引导优化：信息密度过高（5 Tab+顶部5按钮+左侧树+第三栏目录），考虑向导式步骤条引导
- 表格工具栏提示：不要完全依赖右键菜单，上方加简洁工具栏显示选中状态和可用操作
- 500 错误自动重试时加 loading 状态提示"正在重试..."
- 423 锁定错误应显示锁定人、锁定时间、解锁方式
- 查看/编辑模式切换推广到报表、底稿等更多模块
- 合并报表抵消分录变更接入 EventBus 五环联动
- 键盘导航（Tab切换单元格）、批量粘贴（从Excel复制多单元格）

### 表格交互增强（WPS 借鉴，按优先级）
#### P1（已完成）
- ✅ 负数红色+条件格式：displayPrefs 新增 negativeRed/highlightThreshold，amountClass() 返回 CSS 类，顶栏面板新增开关，TrialBalance 已接入
- ✅ 批注 hover 气泡：CommentTooltip.vue 通用组件（el-tooltip 包裹，hover 300ms 显示批注内容+时间+复核状态），各模块待接入
- ✅ useTableSearch 表格内搜索替换：composable + TableSearchBar.vue 通用组件（keyword/search/next/prev/replace/cellMatchClass），TrialBalance 已接入
- ✅ 选中区域自动求和状态栏：useCellSelection 新增 selectionStats() + SelectionBar.vue 通用组件（count/sum/avg/max/min），TrialBalance 已接入
#### P2（提升效率）
- 列显示/隐藏：GtToolbar 加"列显示"下拉多选框，勾选要显示的列（半天）
- 数值范围校验：GtEditableTable 列配置支持 validator 函数+实时错误提示（半天）
- 单元格锁定：公式计算行+已复核行+合计行不可编辑，行数据 _locked 标记（半天）
- 分组折叠（大纲）：试算表按科目类别折叠、附注按章节折叠，el-table tree-props 配合 groupBy 配置（1天）
- 排序筛选默认开启：GtEditableTable 数值列默认 sortable，文本列默认 filters（半天）
#### P3（锦上添花）
- 打印预览弹窗：A4 纸张比例预览+页边距+方向+表头每页重复，配合 gt-print.css（1天）
- 批注线程（回复链）：useCellComments 扩展 replies 数组，支持复核人提意见→编制人回复→确认的讨论链（1天）

### 已完成归档（本轮对话）
- ✅ useCellSelection + CellContextMenu 5模块统一迁移
- ✅ 单元格选中样式升级（GT品牌紫色系）
- ✅ 批注与复核标记持久化（consol_cell_comments表+API+composable+6模块集成）
- ✅ 试算平衡表期初提取上年数（prior-year API）
- ✅ 汇总穿透接真实数据（drill-down API）
- ✅ 科目→附注行映射表（account_note_mapping+refresh三级匹配）
- ✅ 公式执行引擎Phase1-3（解析器+求值器+前端对接+跨模块引用+审计日志+并行执行）
- ✅ 大表格按需渲染（useLazyEdit，3个模块）
- ✅ 内部往来抵消细化（逐笔核对+坏账分别冲回+差异提示）
- ✅ 自定义查询全局功能（6种数据源+树形指标+转置+导出）
- ✅ 旧版合并模块清除（26个文件）+ TS错误366→0
- ✅ ConsolidationIndex拆分（试算表Tab抽取为独立组件，1678→1350行）
- ✅ 合并模块4个Tab布局风格统一
- ✅ 14张工作底稿表功能完整性确认
- ✅ 端到端冒烟测试+公式解析器单元测试（28+14个）
- ✅ 15+个bug修复

## 关键技术决策（速查）

- 事件驱动：EventBus debounce 500ms，调整-试算表-报表-附注-底稿五环联动
- 四式联动：Excel + HTML + Word + structure.json（权威数据源）
- 三层模板：事务所默认-集团定制-项目级应用
- 数据集版本：LedgerDataset staged-active-superseded
- 在线编辑：Univer 纯前端方案（2026-05-02），完整保存链路：前端 snapshot → POST /univer-save → xlsx 回写（univer_to_xlsx.py）+ structure.json + 版本快照 + 审计留痕 + 事件发布（五环联动）
- 新增后端服务：xlsx_to_univer.py（xlsx→IWorkbookData）+ univer_to_xlsx.py（IWorkbookData→xlsx 回写）
- 新增前端依赖：@univerjs/presets + @univerjs/preset-sheets-core + opentype.js
- 新增前端依赖：xlsx@0.18.5（合并工作底稿导出模板/导入Excel）
- Vite 配置：需要 alias `opentype.js/dist/opentype.module.js` → `opentype.js/dist/opentype.mjs`
- ONLYOFFICE 全面替换完成：WOPI/wopi_service 保留向后兼容，所有前端 ONLYOFFICE 引用已清除，WopiPoc/UniverTest 已删除
- 文件存储三阶段：本地磁盘（进行中）- Paperless（OCR/检索）- 云端（归档）
- 附注正文三级填充：上年附注-LLM 生成-模板默认文字
- RAG：llm_client.chat_completion 支持 context_documents 参数，截断 8000 字符
- asyncpg 时区：datetime.utcnow()（naive），不能用 timezone.utc（aware）
- asyncpg 不支持 `::jsonb` 类型转换语法（与命名参数 `:data` 冲突），必须用 `CAST(:data AS jsonb)`
- Alembic 已放弃，用 create_all + 手动 ALTER TABLE
- 底稿明细行：不硬编码行名，用 detail_discovery 动态发现（企业实际数据决定），key_rows 只定义结构性行
- 附注表格填充：结构/样式来自模板，明细行数据从底稿 fine_summary 动态提取，降级从试算表取数，合计行自动求和
- 统一导入架构：import_template_service（模板生成+校验+解析）+ import_templates 路由（4 API）+ UnifiedImportDialog 前端三步弹窗
- 合并工作底稿：参照致同 Excel 模板（合并模板有关表样.xlsx，10 sheet），前端 7 张表 + 1 弹窗 + 1 入口 Tab 组件，路径 components/consolidation/worksheets/
- 合并工作底稿用 Element Plus 表格（非 Univer），因为是结构化表单（下拉/日期/联动），不是自由格式 Excel；需要时加"从 Excel 导入"按钮
- 合并工作底稿小计行要求默认自动合计但支持用户编辑覆盖，用 reactive 数据行实现（非 show-summary）
- 持股比例字段统一支持最多6位小数（precision=6），输入框宽度≥90px 以完整显示
- el-table 内嵌 el-select 必须用 `v-model` + `<div @click.stop @mousedown.stop>` 包裹 + watch 防循环（internalUpdate 标志位，prop→rows 用直接赋值不要浅拷贝）
- el-table 多级表头的 getSummary 中 `col.property` 对嵌套子列可能为 undefined，计算列需用 `col.label` + `col.parent?.label` 匹配后手动计算
- 模板渲染函数中禁止修改 reactive 数据（如 `row.total = sum`），会触发无限渲染循环崩溃，合计同步放 watch 中
- 跨表数据提取用 computed 而非 watch 修改源数据，watch 修改 reactive 数组会触发 indexOf 崩溃（已踩坑两次）
- Vue 3 reactive 不追踪运行时新增属性：对 computed 返回的对象设置 `row._newProp = val` 不触发模板更新，需用独立 ref Map 存储动态数据
- `<script setup>` 中 reactive 数组初始化必须在 setup 阶段同步完成（不能依赖 watch immediate），否则模板首次渲染时数组为空导致 undefined 崩溃
- 同一组件不同 props 切换时（如股比变动1/2/3次），必须加 `:key` 强制重建实例，否则 reactive 数据的数组长度不匹配
- Vue 模板 HTML 属性值中禁止使用中文引号 `""`，会被解析为属性结束符导致编译失败
- 禁止用 PowerShell `-replace` 修改含中文的 Vue 文件，会破坏 UTF-8 编码导致中文乱码，必须用 strReplace 工具逐个替换
- tsconfig.json 关闭 noUnusedLocals/noUnusedParameters（大型项目噪音过多，unused 检查交给 ESLint）
- 大表格编辑性能：useLazyEdit composable 按需渲染，只有点击的单元格渲染 el-input（其他纯文本），已集成到 ConsolNoteTab + ConsolidationIndex 合并试算表 + TrialBalance 单体试算表（3 个模块）
- 合并工作底稿五步流程：基本信息→投资明细→净资产归集→权益法模拟→抵消分录+资本公积核查
- 合并股比变动：内联表三栏布局（净资产变动+直接持股模拟+间接持股模拟），左侧导航根据基本信息表动态生成（1/2/3次），:key 强制重建，setup 同步初始化
- 全局化改造方向（2026-05-04 评审确定）：composable 提取（useFullscreen/useTableToolbar/useEditMode）→ Pinia store 统一（project/dict/addressRegistry）→ mitt 事件总线 → API 路径集中 → GtEditableTable 高阶组件
- 全屏重复代码现状：17个组件各自 `const isFullscreen = ref(false)` + ESC 监听 + 独立 CSS 类，需统一为 useFullscreen + `.gt-fullscreen`
- 前端 Pinia store 现状：仅 5 个 store（auth/drilldown/roleContext/wizard/collaboration），缺少 project/dict/addressRegistry 等全局 store
- 前端无 provide/inject 使用，模块间数据传递全靠 props/route/CustomEvent，需 Pinia store 补位
- API 路径散落在 18 个 service 文件中，需集中到 apiPaths.ts 统一管理
- 枚举字典前端硬编码中文标签，需后端 /api/system/dicts 接口 + 前端 useDictStore 统一管理
- 金额格式化重复现状：35+处各自定义 fmt/formatAmount/formatNumber（toLocaleString zh-CN minimumFractionDigits:2），需统一到 formatters.ts
- 金额单位换算架构：数据库始终以"元"存储，前端 displayPrefs Store 控制显示单位（yuan/wan/qian），fmtAmountUnit 按 divisor 换算，导出时用 unitDivisor 还原
- 显示偏好持久化：displayPrefs Store → localStorage('gt_display_prefs')，包含 amountUnit/fontSize/showZero/decimals，全局顶栏"Aa"面板切换
- 表格字号绑定：el-table 通过 `:style="{ fontSize: displayPrefs.fontConfig.tableFont }"` 动态响应，4档预设（11/12/13/14px）
- useCellSelection 拖拽框选：startDrag(mousedown) → updateDrag(mousemove) → endDrag(mouseup 全局监听)，selectRange 矩形区域选中，registerCellValueGetter 注册取值函数
- useCellSelection Shift 范围选：锚点(anchorRow/anchorCol) + Shift+点击 → selectRange(anchor, target)，复制改为多行矩形格式
- el-table 拖拽框选实现：setupTableDrag(tableRef, getCellVal) 通过 DOM 事件委托（mousedown+mouseover 在 table 容器上），从 td.el-table__cell→tr→tbody 解析行列索引，拖拽期间 body 加 .gt-dragging 禁止文本选中+光标变 cell，忽略 input/button 等交互元素
- 已有但未使用的基础设施：sse.ts（完整 SSE 封装+自动重连）、shortcuts.ts（ShortcutManager+13 个默认快捷键）、operationHistory.ts（撤销功能+ElNotification），均需接入而非重建
- 页面横幅重复现状：TrialBalance(.gt-tb-banner)/ReportView(.gt-rv-banner)/DisclosureEditor(.gt-de-banner)/ConsolidationIndex(.gt-consol-bar) 等5+套同构横幅各自实现，需抽 GtPageHeader+GtInfoBar
- VirtualScrollTable.vue 的 formatCell 未使用全局 formatters.ts，仍用内联 toLocaleString
- Vue 3 子组件 prop 不能直接 v-model 绑定：TableSearchBar 踩坑，v-model="keyword"（keyword 是 prop）Vite 生产构建报错，需改为 :model-value="keyword" + @update:model-value="$emit(...)"
- Ctrl+F 搜索栏实现：不依赖 shortcuts.ts 的 CustomEvent（浏览器默认 Ctrl+F 会抢先触发），改为各组件内直接 document.addEventListener('keydown') + e.preventDefault() 拦截，触发 useTableSearch.toggle()
- TableSearchBar 位置：必须在表格上方（横幅/提示区下方），不能在表格下方（用户看不到）
- TableSearchBar 样式：致同品牌紫色渐变背景（#f5f0ff→#ece6f5），紫色边框+聚焦环+匹配计数徽章，cubic-bezier 丝滑动画
- 日期格式化重复现状：15+处各自定义 formatDate/fmtDate/fmtTime（toLocaleString/toLocaleDateString zh-CN），需统一到 formatters.ts
- 前端权限控制现状：后端有完整 RBAC（Permission 枚举+require_permission），前端仅 SEChecklistPanel 1处做了 canEdit，其余全靠后端 403 拦截
- 后端分页参数不统一：page/page_size、offset/limit、skip/take 混用，需统一为 PaginationParams 依赖注入
- 状态标签映射重复现状：statusTagType/statusLabel 在10+组件各自定义（WP 6种状态+6种复核状态、调整4种、报告3种、模板3种），需集中到 statusMaps.ts
- TanStack Query 现状：已引入 @tanstack/vue-query + queryClient（5分钟 staleTime），但实际代码几乎未使用 useQuery/useMutation，全是手动 http.get+ref+loading
- 后端 SSE 现状：EventBus 已实现 create_sse_queue/_notify_sse，前端未接入 EventSource，导入完成/复核提交/五环联动完成等场景靠轮询或手动刷新
- 自动保存现状：仅 StructureEditor 1处有5秒debounce自动保存，其余编辑页面无草稿恢复机制
- 确认弹窗现状：30+处 ElMessageBox.confirm 模式一致（确定删除xxx？+删除确认+type:warning），可封装语义函数
- ErrorBoundary 现状：仅 DefaultLayout 1层，子组件崩溃导致整页白屏，需细粒度隔离
- 基本信息表 holding_type（直接/间接）+ indirect_holder（间接持股方）字段，同一企业可出现两行（直接51%+间接49%通过公司B），模拟权益法按持股路径分别模拟
- EquitySimSheet 间接持股 sections 通过 computedIndirectSections computed 从基本信息表动态生成（优先已保存数据，否则自动创建）
- 合并净资产表：动态列根据合并范围树形结构生成（当前层级直接下级），列头显示企业名称+期末持股比例
- 合并净资产表预设公式：表内公式（SUM/期初+增加-减少）+ 提取公式 TB({company_code},'科目','期初余额') 从子企业试算表按企业代码提取 + 3条校验公式
- 合并资本公积变动（差额表）：从抵消分录按科目自动提取，与合并报表期末数比对差异
- 合并报表左侧导航改为集团架构树+差额表节点，每个合并节点自动生成差额表子节点，合并数=汇总直接下级-差额表，底部6种报表类型切换
- 合并模块独立中间栏树形导航（ConsolMiddleNav），通过 DefaultLayout slot 条件渲染（非命名视图），hideMiddle 排除合并路由，CustomEvent 联动
- 合并工作底稿持久化：consol_worksheet_data 表（project_id+year+sheet_key+JSONB），自动建表无需 migration，upsert 保存，onMounted 批量加载回填
- 基本信息表新增字段：parent_code（上级单位代码）、ultimate_controller（最终控制方）、ultimate_controller_code（控制方代码），用于构建树形层级
- ConsolMiddleNav syncFromProject 按 parent_code 构建层级树（非扁平列表），selectedYear 改为从 route.query 取值
- ConsolCatalog 监听 consol-standard-change 事件，顶部栏切换准则后自动刷新附注树
- 合并报表/附注 Tab 内不重复放置准则选择器和转换规则按钮，统一由顶部紫色栏控制，避免 UI 冗余
- 报表转换映射 API 路径：`/api/projects/{projectId}/report-mapping/preset`（非 `/api/report-mapping/preset`），scope 合并报表用 `consolidated`，返回字段 soe_row_code/soe_row_name 需映射为 source_code/source_name
- 合并报表按类型分视图：权益变动表/减值准备表用矩阵 table（多行表头+横向滚动+sticky），其余4张用普通 el-table 四列结构
- 合并汇总明细查看：顶部栏"📊 查看"按钮，选中单元格后穿透显示该数值的汇总过程（直接下级贡献+末级明细），支持占比、数据来源、导出 Excel
- 表格单元格选中：查看模式下支持单击选中、Ctrl+多选、右键菜单（汇总穿透/复制值/查看公式/添加批注/标记已复核/汇总/求和/对比差异），通过 el-table 的 cell-click + cell-contextmenu 事件实现
- 单元格选中样式统一：5模块各自的 scoped CSS（tb/rv/de/gt-cell--selected）已全部删除，统一使用 CellContextMenu.vue 全局 gt-ucell--selected 样式
- 选中区域样式设计：连续区域统一淡紫色半透明背景(rgba(75,45,119,0.08))，只在边缘显示边框，相邻单元格无内部边框（Excel 风格）；单选时加 outline + 右下角填充柄小方块
- 复制按钮命名规范：工具栏"复制整表"（复制整个表格）vs 右键菜单"复制选中区域(N格)"/"复制值"（复制选中单元格），两者明确区分
- 右键汇总功能：直接下级汇总（自动获取下级企业同位置数据合计）+ 自定义汇总（树形多选企业+选择数据来源：同表/报表/附注），POST /api/consol-note-sections/aggregate
- ConsolMiddleNav 树形节点右键菜单：直接下级汇总/自定义汇总/刷新数据/查看报表/查看附注，通过 consol-tree-aggregate 事件联动 ConsolidationIndex 的汇总弹窗
- 合并报表按合并主体隔离：树形每个企业节点是独立合并主体（currentConsolEntity），点击后 loadConsolReport 带 company_code 加载该主体的报表/附注数据
- 数据刷新策略：保存只入库不触发刷新，前端维持当前状态；用户主动点刷新才从后端拉数据；树形节点支持按单位+按表类型选择性刷新（弹窗勾选）
- 前端缓存：合并报表/附注数据按 company_code+report_type 缓存，切换单位/报表时优先读缓存，刷新时清除对应缓存重新请求
- ConsolidationIndex onUnmounted 清理事件监听器，onStandardChange 广播准则变更事件
- 当期处置出表企业不单独建表，在模拟权益法中体现（期初模拟→出表日前变动→处置分录→期末长投归零）

## 底稿编码体系（致同 2025 修订版）

- D 循环：D0 函证/D1 应收票据/D2 应收账款/D3 预收账款/D4 营业收入/D5-D7 合同资产等
- F 循环：F1 预付账款/F2 存货/F3 应付票据/F4 应付账款/F5 营业成本
- K 循环：K1 其他应收款/K2-K5 费用/K6 持有待售/K7-K8 其他/K9 管理费用
- N 循环：N1 递延所得税资产/N2 应交税费/N3 所得税费用
- 映射文件：backend/data/wp_account_mapping.json（88 条，v2025-R4）
