---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤ 200 行**。完成事项明细 → `#dev-history`；技术决策 → `#architecture`；规范铁律 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；启动 `start-dev.bat`（后端 9980 + 前端 3030）
- **输出分步但连续做完**；**任务标记不能假绿**；**彻底解决不绕开**；**optional(*)任务也要做完**
- **🔴 codegraph 优先于 grep**：79k 节点/160k 边/4449 文件；grep 仅用于非符号文本
- **触类旁通**；**改动前先 spec 三件套**（>500行/3+组件/跨前后端）；**改动后必 Playwright 实测**
- **UI 全中文化**；**报表金额默认"元"**；**中文场景全链路不能崩**
- **底稿表格UI统一规范**：表格字体13px；AI+复核按钮右对齐在section标题同行；公式列虚线下划线+cursor:help+tooltip来源；列宽min-width自适应；审计说明/结论el-card包裹；编制提示details折叠底部
- **🔴 底稿导入导出统一规范**：el-dropdown"导入导出▾"(导出模板/导出数据/导入数据)，复用`useXImportExport`composable(后端三端点)。多区块分sheet导出。动态行表格才需要导入导出
- **不要考虑轻量**：要考虑针对性、联动性、美观性、实操性、易懂性；审计UI要有逻辑追溯能力
- **动态行新增交互**：需命名的动态行必须先弹ElMessageBox.prompt输入名称确认后再创建
- **复杂底稿填报说明**：多步骤底稿顶部增加蓝色渐变引导区(序号步骤,2列grid)
- **源模板红字内容融入**：嵌入对应功能区域上方作为"方法论上下文"(琥珀色左边线+浅黄背景)
- **多section底稿每个文本区都要AI辅助**：section标题行右侧放AI按钮，不只底部有
- **叙述式底稿UI规范**：仅核对+结论的底稿不加独立审计意见区；textarea用autosize
- **抽凭表行级OCR**：📎附件列上传后复用`/d4/contract-ocr`端点OCR识别→确认弹窗填入
- 功能收敛；git 单 commit；**push 前必先 fetch**；**协作走 PR 不直推 main**
- **spec 归档按功能分类**（05-business-features / 04-infra 等），不按日期批次建目录
- 目标并发 6000 人；底稿编码致同 2025 修订版
- 5 角色轮转：审计助理/现场经理/业务合伙人/质量控制复核合伙人/EQCR技术复核人
- **v3.0 愿景方向**：项目级知识自动提取+跨年度续审继承（当前不做）

## 底稿开发铁律

- **风险导向审计**：B50风险→D~N程序表→A13评价错报，全链可追溯
- **componentType 选型**：结构化=d-form-table / 复杂Excel=OnlyOffice / 文档=word-template / 程序表=a-program-console / 函证=confirmation-*（9类）
- **三表HTML渲染**：底稿目录+审定表+附注全走HTML，仅复杂公式/DCF/图表留OnlyOffice
- **联动是核心价值**：ref_index chip+auto_data_source实时取数；孤立底稿=无价值
- **🔴 函证模块跨循环共享**：D0的9个confirmation-*组件跨循环复用(E0/F0/G0/H0/K0/L0)，不为每循环独立开发
- **开发前必先逐sheet读源模板**；**导入导出三级**；**适用性自动判断**
- **模板预填优先于AI生成**：有固定骨架的章节用CHAPTER_TEMPLATE+变量替换做预填，AI仅用于复杂章节
- **🔴 D~N专属组件开发标准模板**：Phase0双源输入(openpyxl脚本读xlsx+底稿模板库md交叉验证)→Phase1三件套→Phase2开发8步(①registry+yaml ②composable分层useXFormulaEngine纯函数 ③主入口sheetName v-if分发defineAsyncComponent lazy ④后端3-4py ⑤注册四件套 ⑥联动TB回写+EventBus+GtIndexChip ⑦UI铁律 ⑧功能方向:联动/美观/溯源/易操作/导入导出/AI/双三模式)
- **通用schema复用**：`{wp_code}-generic.yaml` + pattern matching
- **OO sheet-name必须与源xlsx tab名完全一致**；**多sheet workbook OO隐藏非目标tab**
- **D~N循环全sheet HTML组件化**：OnlyOffice仅为降级/偏好切换

## 环境配置

- Python 3.12 / Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`
- vLLM：Qwen3.5-27B-NVFP4，APC+fp8 kv-cache
- Docker：postgres(5432)/redis(6379)/metabase(3000)/pgbouncer(6432)/OCR(8200)
- DB_DISABLE_SSL=True；连接池 150 / PG max_connections=200
- 前端唯一路径：`audit-platform/frontend/`
- **codegraph v0.9.8**；**rtk 0.42.1**；**OnlyOffice 9.4.0**
- 部署v2.0：瘦客户端(Electron)+内网全栈

## PG schema

- MigrationRunner（非 alembic）；V+R 配对；`IF NOT EXISTS`；**最高 V094**
- trial_balance=standard_account_code/unadjusted_amount/aje_adjustment/audited_amount
- working_paper 无 wp_code（在 wp_index，JOIN）
- recalc 铁律：`tb_balance` v1 口径（借正贷负），`trial_balance` v2 正数；只汇总叶子；损益取发生额
- 契约测试：schema_contract(表级)+column_contract(列级)+componentType 契约 vitest

## 任务状态

### 完成度概览
- **222+ spec archived**（05-business-features 为主）
- **D循环全量完成**：D1(6spec拆分)+D2(refactor)+D3+D4(含D4-12/D4-14独立spec)+D5+D6+D7(三件套齐全待开发)
- **A/B/C类全量完成**：82+ componentType注册；A1~A27/B1~B60/C1~C26所有专属+bundle+聚合
- **E1货币资金全量完成**；F循环registry校准完成(99 override条目)

### git 状态
- 分支 `work/2026-05-30-wp-specs`，最高迁移 V094(V093部署+V094待执行)
- 远程默认分支隐患：`origin/HEAD→origin/master` 落后 main 298 commit

### 活跃/待办
- **🔵 D7合同负债**：三件套齐全待开发(25需求+31任务)
- **🔵 voucher-sampling-engine**：三件套齐全,P0(5种抽样算法+版本链+CAS1314)
- **🔵 cutoff-test-auto-sampling**：三件套齐全,P0(3模式截止+LedgerSampling)
- **🔵 workpaper-version-trail**：三件套齐全,P1(field-level快照+diff+回滚)
- **🔵 全局一致性治理 3 spec**：display-format-single-source/cycle-palette-single-source/stale-propagation-cleanup-doc
- **🟡 B40项目组讨论**：需重建spec(实际是CAS1211不是审计抽样)
- **🟡 B60 LLM辅助策略**：待vLLM Phase3
- **🟡 AI对话模式**：章节AI追问用户而非报错，对话流待做
- **🟡 存货监盘P2**：照片+GPS+OCR+差异预警
- **🟡 voucher-attachment-intelligence**：P2凭证附件智能化(依赖voucher-sampling-engine)
- **🟡 audit-review-dialog**：通用复核对话(三件套齐全,13需求)
- **架构优化**：①拆 event_handlers.py ②前端 Top-5 巨型 Vue 拆分 ③services/ 按域建子包
- 外部依赖：LLM embedding / 合并 UAT / GitHub 默认分支改 main / MinerU+OCR

## 踩坑铁律（高频）

### 后端
- **大文件导入期间禁改后端代码**→ uvicorn reload 杀 worker
- **event_bus publish 只传 EventPayload**；轻量通知用 broadcast_raw
- **asyncpg不支持IN tuple参数**：必须用`= ANY(:codes)` + `list(...)`
- **router_registry 必查**；**service 只 flush 不 commit**
- **新增 componentType 必须同步更新 VALID_COMPONENT_TYPES**
- **Bundle wpIdMap必须用item.wp_id不能用item.id**
- **D~N专属组件必须有RENDERER_DISPATCH注册**（否则被onlyoffice-sheet吞掉）
- **D~N专属组件不能有内部el-tabs**：接sheetName prop用v-if分发
- **account_package_registry sheets顺序=目录行顺序**
- **导入导出composable必须用http(axios)不能用原生fetch**（无Authorization header→401）
- **StreamingResponse中文文件名必须RFC5987编码**
- **GtOnlyOfficeSheet健康检查响应解析**：`health.data?.data?.healthy`双层兼容
- **聚合包内独立sheet三端点wp_code必须一致**（config/WOPI/callback统一用sheet级解析）
- **project_assignments列名是staff_id不是user_id**
- **结构化章节数据不能存到textarea content**（用独立item_id分别存checklist_responses）

### 前端
- **底稿编码→实际内容必须查源模板**：不能凭编码猜内容
- **render-config返回结构是`{sheets:[{html_data:{...}}]}`**
- **新专属组件必须有selfLoad逻辑**（bundle内嵌场景htmlData为null）
- **A1 Dashboard子Tab组件必须自加载**
- **GtIndexChip的prop名是`value`不是`wp`**
- **API调用可能触发全局404弹窗**：预期404请求加`{_silent:true}`
- **naive UTC时间戳前端少8小时**：补`Z`标记再交fmtDateTime
- **GtAProgramConsole需selfLoad**（bundle内嵌场景）

### OnlyOffice
1. JWT：开发环境 `JWT_ENABLED=false`
2. URL：`ONLYOFFICE_CALLBACK_BASE=http://host.docker.internal:9980`
3. callback 返回裸 `{"error":0}`
4. 改 URL 后需 `docker restart` 清 session
5. 统一用 GtOnlyOfficeSheet；健康端点=`/api/workpapers/onlyoffice/health`
6. fileType 动态检测（从file_path后缀推断）
7. 聚合包内sheet三端点统一用sheet级wp_code解析

## 关键引用

- spec 状态 → `.kiro/specs/INDEX.md`
- 领域术语 → glossary.md（inclusion:always）
- 底稿内容结构权威来源 → `基础数据/致同通用审计程序及底稿模板（2025年修订）/BCD类底稿md/`
