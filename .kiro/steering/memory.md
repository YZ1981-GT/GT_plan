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

## 当前系统状态（2026-05-02）

- 17 个开发阶段中 16 个完成，仅合并报表前端存在 211 个 TS 错误（developing）
- 后端约700路由正常加载，0 个 stub 残留
- 审计员 8 步全流程理论可走通（导入-查账-调整-试算表-底稿-附注-报告-Word导出）
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
- 全屏功能用 Teleport to="body" 实现（非 position:fixed），避免被祖先 overflow/transform 裁剪导致全屏失效
- 公式体系完整（三分类 + 跨表引用 + 拓扑排序 + 审计留痕）
- 公式管理（FormulaManagerDialog）已提升到全局顶部导航栏（ThreeColumnLayout），所有模块共享
- 公式管理树形导航已增加"合并报表"分类（7张表 CI/CC/CE/CN/CS/CX/CK 编码）+ 表间审核"合并↔报表"规则
- 各表的"ƒx 公式"按钮与全局公式管理中心必须双向联动同步：任一处修改公式后另一处自动更新，所有模块统一
- 公式联动机制：CustomEvent('gt-open-formula-manager') 打开 + CustomEvent('gt-formula-changed') 广播变更，各模块监听刷新
- 企业级治理完整（门禁/留痕/SoD/版本链/一致性复算）
- 合并工作底稿前端 9 个组件已创建（worksheets/），集成到 ConsolidationIndex 第一个 Tab
- 合并工作底稿 16 个组件全部就绪（0编译错误），前后端联动持久化完成，7条跨表数据流正常，三栏股比变动+拖拽+折叠

## 活跃待办

- ~~附注校验公式从 md 导入~~ ✅ 已完成：国企 757 条 + 上市 804 条（继承国企版+差异+特有）
- ~~上市版校验公式仅 179 条需补全~~ ✅ 已完成：上市版继承国企版全部公式，差异公式替换/排除，特有公式追加
- ~~上市版五章 29 个无表格章节排查~~ ✅ 已排查：实际仅 3 个第五章空表格（F19/F22/F26 各 1-2 个子表），其余为政策描述型表格无需数据行
- 合并报表前端 211 个 TS 错误专项修复（2-3 周）
- 合并工作底稿表样逐表完善（基本信息表→投资明细→净资产表→模拟权益法→抵消分录→资本公积变动）
- ~~合并工作底稿7张表功能对齐~~ ✅ 已完成：全屏/公式管理/导出模板/导出数据/导入Excel/多选删除/增删行/还原（大部分表已统一，部分汇总表仍缺项见下）
- ~~合并工作底稿复盘缺陷（P0）：EquitySimSheet.rowTotal() + NetAssetSheet.calcRowTotal() 在渲染中修改 reactive 数据，需改为纯计算函数~~ ✅ 已修复
- ~~合并工作底稿复盘缺陷（P1）：PostElimIncomeSheet/MinorityInterestSheet 缺公式管理按钮；InternalTradeSheet/InternalCashFlowSheet 缺公式管理按钮~~ ✅ 已修复
- ~~合并工作底稿复盘缺陷（P2）：大部分表 ws-tip 只有一行，需升级为步骤引导面板；智能填充可扩展到净资产表/模拟权益法等~~ ✅ P2 操作指引已升级（8个表），智能填充待扩展
- ~~合并工作底稿新增3张汇总计算表（待前面表样稳定后实现）：❶抵消后长投明细表 ❷抵消后投资收益明细表 ❸少数股东权益/损益明细表，数据全部从前面表样自动提取计算~~ ✅ 已完成：PostElimInvestSheet/PostElimIncomeSheet/MinorityInterestSheet，纯计算无需用户输入
- ~~合并工作底稿新增3张内部抵消表（待实现）：❶内部往来抵消表（债务方×债权方矩阵，余额类）❷内部交易抵消表（卖方×买方，发生额类+未实现利润）❸内部现金流抵消表（按现金流量表项目配对），数据从各子企业底稿/附注关联方章节提取~~ ✅ 已完成：InternalArApSheet/InternalTradeSheet/InternalCashFlowSheet，各表自动生成抵消分录预览
- 内部往来抵消需支持：按科目细分+账龄分布+下级明细逐笔核对+坏账准备抵消还原
- 内部往来结构：本方（单位/科目/明细/坏账账龄）↔ 对方（单位/科目/明细/坏账账龄），双方独立记录
- 账龄段做全局枚举（项目级设置）：预设3年段/5年段+自定义，每段含段名/起止月数/默认坏账比例，所有账龄相关底稿统一引用
- 3张内部抵消表生成的抵消分录需自动汇总到合并抵消分录表中（往来→资产负债表科目，交易→利润表科目，现金流→现金流量表项目）
- 合并抵消分录表是汇总中心：权益抵消+损益抵消+交叉持股+内部抵消自动导入+用户自定义分录，5个区域
- 报表/试算表/附注的公式管理需改为走全局 CustomEvent 联动（当前各自独立实例，未联动）
- 地址坐标库（CellSelector/FormulaRefPicker）需全局联动：合并报表新增表样后，各模块公式编辑器的引用下拉要同步更新
- 模板管理（SharedTemplatePicker）需全局联动：任一模块保存模板后，其他模块引用时要看到最新版本
- 合并报表抵消分录变更需接入 EventBus 五环联动，触发合并试算表和合并报表重算
- 模拟权益法比对区的"期末净资产×持股比例"需从净资产表联动取值（当前占位为0）
- 模拟权益法改进待办：❶净资产联动取期末值 ❷当期变动从净资产表按比例自动提取 ❸按企业展开独立模拟 ❹期初从上年底稿带入 ❺底部按科目汇总分录传给抵消分录表 ❻基本信息表保存后同步consol_scope统一数据源
- ~~合并工作底稿跨表联动P0缺陷：❶净资产表期末值未联动到模拟权益法比对区 ❷模拟权益法分录未转换为合并抵消分录 ❸少数股东权益的期末净资产未从净资产表提取~~ ✅ 全部修复
- ~~合并工作底稿所有表的保存按钮需接后端API持久化（当前仅前端提示），模块间数据提取联动需后端接口配合~~ ✅ 已完成：consol_worksheet_data 表（JSONB）+ 3个API + 前端 onSave/onMounted 联动
- 用真实审计项目端到端验证（最高优先级）
- 合并模块 Tab 精简为4个：合并工作底稿、集团架构、合并报表、合并附注（差额表和自定义查询已删除）
- 自定义查询改为全局功能（待开发）：支持按底稿/报表/附注/调整分录/单位/年度多维度查询，树形地址坐标库选择指标，查询指标库，结果支持导出/转置/复制
- 公式管理中心左侧数据源树（报表/附注/流动资产/长期资产/负债/损益类/合并报表/表间审核）待统一补充完善，各模块开发完毕后更新
- ~~D2 应收账款 / H1 固定资产等更多科目精细化规则打磨~~ ✅ 已完成：77 个核心科目精修（全循环 D-N 覆盖），剩余 270 个为函证/控制测试/风险评估等无需 key_rows 精修
- ~~统一 Excel 导入框架~~ ✅ 已完成：7 种模板 + 7 页面集成 + 14 项加固（数值校验/事务保护/RFC5987文件名/示例行宽松跳过/失败行反馈/覆盖追加模式/重试按钮）

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
- `<script setup>` 中 reactive 数组初始化必须在 setup 阶段同步完成（不能依赖 watch immediate），否则模板首次渲染时数组为空导致 undefined 崩溃
- 同一组件不同 props 切换时（如股比变动1/2/3次），必须加 `:key` 强制重建实例，否则 reactive 数据的数组长度不匹配
- Vue 模板 HTML 属性值中禁止使用中文引号 `""`，会被解析为属性结束符导致编译失败
- 禁止用 PowerShell `-replace` 修改含中文的 Vue 文件，会破坏 UTF-8 编码导致中文乱码，必须用 strReplace 工具逐个替换
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
