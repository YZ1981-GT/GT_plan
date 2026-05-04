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
- Vite 构建验证通过（35s），git 已推送 feature/cell-selection-comments-cleanup 分支（2 commits）
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

### 功能完善（中期）
- 模拟权益法改进：❶净资产联动取期末值 ❷当期变动按比例自动提取 ❸按企业展开独立模拟 ❹期初从上年底稿带入 ❺底部按科目汇总分录传给抵消分录表 ❻基本信息表保存后同步consol_scope
- 合并抵消分录表汇总中心：权益抵消+损益抵消+交叉持股+内部抵消自动导入+用户自定义分录，5个区域
- 3张内部抵消表生成的抵消分录自动汇总到合并抵消分录表（往来→BS科目，交易→IS科目，现金流→CF项目）
- 公式管理中心左侧数据源树待统一补充完善（各模块开发完毕后更新）
- 地址坐标库（CellSelector/FormulaRefPicker）需全局联动：新增表样后引用下拉同步更新
- 模板管理（SharedTemplatePicker）需全局联动：任一模块保存模板后其他模块可见

### 架构优化（低优先级）
- 事件通信改 Pinia store（已回退，需更完善测试环境配合后再尝试）
- consol_note_sections.py 暂不拆分（1003行但内部分隔清晰，拆分风险大于收益）
- 后端 API 响应格式统一（当前前端用 data?.data ?? data 兼容，需后端配合）
- 前端主 bundle 优化（Element Plus 按需导入，当前 index.js 1.3MB）

### 用户体验（持续）
- 查看/编辑模式切换推广到报表、底稿等更多模块
- 合并报表抵消分录变更接入 EventBus 五环联动
- 键盘导航（Tab切换单元格）、批量粘贴（从Excel复制多单元格）

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
- 单元格选中样式统一：outline 1.5px solid + 左侧渐变强调条 + 右下角三角标记 + 缓慢 glow 动画，全部使用 CSS 变量（--gt-color-primary-bg 等），CellContextMenu.vue 统一渲染右键菜单
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
