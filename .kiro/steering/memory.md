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
- 公式体系完整（三分类 + 跨表引用 + 拓扑排序 + 审计留痕）
- 公式管理（FormulaManagerDialog）已提升到全局顶部导航栏（ThreeColumnLayout），所有模块共享
- 公式管理树形导航已增加"合并报表"分类（7张表 CI/CC/CE/CN/CS/CX/CK 编码）+ 表间审核"合并↔报表"规则
- 各表的"ƒx 公式"按钮与全局公式管理中心必须双向联动同步：任一处修改公式后另一处自动更新，所有模块统一
- 公式联动机制：CustomEvent('gt-open-formula-manager') 打开 + CustomEvent('gt-formula-changed') 广播变更，各模块监听刷新
- 企业级治理完整（门禁/留痕/SoD/版本链/一致性复算）
- 合并工作底稿前端 9 个组件已创建（worksheets/），集成到 ConsolidationIndex 第一个 Tab
- 合并工作底稿已扩展到 16 个组件（7基础表+3汇总表+3内部抵消表+股比变动表+入口Tab），左侧导航含动态股比变动项

## 活跃待办

- ~~附注校验公式从 md 导入~~ ✅ 已完成：国企 757 条 + 上市 804 条（继承国企版+差异+特有）
- ~~上市版校验公式仅 179 条需补全~~ ✅ 已完成：上市版继承国企版全部公式，差异公式替换/排除，特有公式追加
- ~~上市版五章 29 个无表格章节排查~~ ✅ 已排查：实际仅 3 个第五章空表格（F19/F22/F26 各 1-2 个子表），其余为政策描述型表格无需数据行
- 合并报表前端 211 个 TS 错误专项修复（2-3 周）
- 合并工作底稿表样逐表完善（基本信息表→投资明细→净资产表→模拟权益法→抵消分录→资本公积变动）
- ~~合并工作底稿7张表功能对齐~~ ✅ 已完成：全屏/公式管理/导出模板/导入Excel/多选删除（固定行表除外）
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
- 合并工作底稿所有表的保存按钮需接后端API持久化（当前仅前端提示），模块间数据提取联动需后端接口配合
- 用真实审计项目端到端验证（最高优先级）
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
- Alembic 已放弃，用 create_all + 手动 ALTER TABLE
- 底稿明细行：不硬编码行名，用 detail_discovery 动态发现（企业实际数据决定），key_rows 只定义结构性行
- 附注表格填充：结构/样式来自模板，明细行数据从底稿 fine_summary 动态提取，降级从试算表取数，合计行自动求和
- 统一导入架构：import_template_service（模板生成+校验+解析）+ import_templates 路由（4 API）+ UnifiedImportDialog 前端三步弹窗
- 合并工作底稿：参照致同 Excel 模板（合并模板有关表样.xlsx，10 sheet），前端 7 张表 + 1 弹窗 + 1 入口 Tab 组件，路径 components/consolidation/worksheets/
- 合并工作底稿用 Element Plus 表格（非 Univer），因为是结构化表单（下拉/日期/联动），不是自由格式 Excel；需要时加"从 Excel 导入"按钮
- 合并工作底稿小计行要求默认自动合计但支持用户编辑覆盖，用 reactive 数据行实现（非 show-summary）
- el-table 内嵌 el-select 必须用 `v-model` + `<div @click.stop @mousedown.stop>` 包裹 + watch 防循环（internalUpdate 标志位，prop→rows 用直接赋值不要浅拷贝）
- el-table 多级表头的 getSummary 中 `col.property` 对嵌套子列可能为 undefined，计算列需用 `col.label` + `col.parent?.label` 匹配后手动计算
- 合并工作底稿五步流程：基本信息→投资明细→净资产归集→权益法模拟→抵消分录+资本公积核查
- 合并股比变动：从弹窗改为内联表（ShareChangeSheet），左侧导航根据基本信息表动态生成（1/2/3次），每家企业独立展示左右两栏
- 合并净资产表：动态列根据合并范围树形结构生成（当前层级直接下级），列头显示企业名称+期末持股比例
- 合并净资产表预设公式：表内公式（SUM/期初+增加-减少）+ 提取公式 TB({company_code},'科目','期初余额') 从子企业试算表按企业代码提取 + 3条校验公式
- 合并资本公积变动（差额表）：从抵消分录按科目自动提取，与合并报表期末数比对差异
- 当期处置出表企业不单独建表，在模拟权益法中体现（期初模拟→出表日前变动→处置分录→期末长投归零）

## 底稿编码体系（致同 2025 修订版）

- D 循环：D0 函证/D1 应收票据/D2 应收账款/D3 预收账款/D4 营业收入/D5-D7 合同资产等
- F 循环：F1 预付账款/F2 存货/F3 应付票据/F4 应付账款/F5 营业成本
- K 循环：K1 其他应收款/K2-K5 费用/K6 持有待售/K7-K8 其他/K9 管理费用
- N 循环：N1 递延所得税资产/N2 应交税费/N3 所得税费用
- 映射文件：backend/data/wp_account_mapping.json（88 条，v2025-R4）
