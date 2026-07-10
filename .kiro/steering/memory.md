---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤ 200 行**。完成事项明细 → `#dev-history`；技术决策 → `#architecture`；规范铁律 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；启动 `start-dev.bat`（后端 9980 + 前端 3030）
- **输出分步但连续做完**；**任务标记不能假绿**；**彻底解决不绕开**；**optional(*)任务也要做完**
- **🔴 codegraph 优先于 grep**：146k 节点/312k 边/8673 文件；grep 仅用于非符号文本
- **触类旁通**；**改动前先 spec 三件套**（>500行/3+组件/跨前后端）；**改动后必 Playwright 实测**
- **UI 全中文化**；**报表金额默认"元"**；**中文场景全链路不能崩**
- **底稿表格UI统一规范**：表格字体13px；AI+复核按钮右对齐在section标题同行；公式列虚线下划线+cursor:help+tooltip来源；列宽min-width自适应；审计说明/结论el-card包裹；编制提示details折叠底部
- **🔴 底稿导入导出统一规范**：el-dropdown"导入导出▾"(导出模板/导出数据/导入数据)，复用`useXImportExport`composable(后端三端点)。多区块分sheet导出。动态行表格才需要导入导出
- **🔴 D~N底稿跨模块联动标准（6大集成）**：①版本链(useVersionTrail主入口集成+autoSnapshot) ②抽凭引擎(检查表GtVoucherSamplingEngine dialog→样本填入) ③截止自动提取(useCutoffAutoSampling→序时账±5天) ④附注EventBus(subscribe substantive:adjudicated刷新+publish disclosure:note-text-updated) ⑤行级OCR(📎列POST contract-ocr→ElMessageBox确认→merge) ⑥复核对话(主入口provide openReviewDialog→子组件inject→section标题栏右侧按钮)
- **不要考虑轻量**：要考虑针对性、联动性、美观性、实操性、易懂性；审计UI要有逻辑追溯能力
- **🔴 G4复盘改进方向（业务层）**：①附注自动从审定表/明细表抓数(EventBus不够,需主动拉取) ②G4-4利率合理性校验(effectiveRate与couponRate差>200bp告警+IRR反推) ③到期日预警+逾期检测(关联ECL Stage升级信号) ④跨底稿勾稽面板(G4-1↔G4-2合计/G4-ecl减值↔G4-1减值小计) ⑤截止测试改为跨期利息检查(非序时账模式)
- **🔴 G类开发效率改进**：①任务颗粒度压缩(PBT合并/Checkpoint去掉/验证合并,71→35) ②composable工厂化(DualMode/FormData/ImportExport参数化) ③render策略工厂化(create_cycle_render_strategy) ④并发3+stagger 5s ⑤代码预生成脚本(generate_g_cycle_spec.py)
- **动态行新增交互**：需命名的动态行必须先弹ElMessageBox.prompt输入名称确认后再创建
- **复杂底稿填报说明**：多步骤底稿顶部增加蓝色渐变引导区(序号步骤,2列grid)
- **源模板红字内容融入**：嵌入对应功能区域上方作为"方法论上下文"(琥珀色左边线+浅黄背景)
- **多section底稿每个文本区都要AI辅助**：section标题行右侧放AI按钮，不只底部有
- **🔴 交互点选优先(尤其C类控制测试等判断型底稿)**：判断/枚举字段一律下拉/单选/多选tag/按钮点选，减少手打；长文本才用autosize textarea+AI辅助。跳转联动一键完成(汇总↔子页↔B23/B50/A14一键带入)。必要处(样本证据/凭证/审计证据/过程记录)加📎附件上传+OCR识别自动填充。结论/缺陷/偏差回写(→B50 EventBus/→A14缺陷底稿/→C21-1汇总/→汇总表"是否偏差")。多加操作提示(顶部蓝色渐变引导区+方法论上下文琥珀块+字段tooltip+编制提示details)
- **叙述式底稿UI规范**：仅核对+结论的底稿不加独立审计意见区；textarea用autosize
- **抽凭表行级OCR**：📎附件列上传后复用`/d4/contract-ocr`端点OCR识别→确认弹窗填入
- **🔴 示例内嵌编制参考（非Drawer被动查看）**：源模板示例内容必须内嵌到对应步骤/过程记录的编制界面中，用户填写时直接看到参照+一键套用，不是藏在Drawer里让用户主动找。核心：参照示例要求来完善底稿开发，让用户点点点就能完成编制
- 功能收敛；git 单 commit；**push 前必先 fetch**；**协作走 PR 不直推 main**
- **spec 归档按功能分类**（05-business-features / 04-infra 等），不按日期批次建目录
- 目标并发 6000 人；底稿编码致同 2025 修订版
- 5 角色轮转：审计助理/现场经理/业务合伙人/质量控制复核合伙人/EQCR技术复核人
- **v3.0 愿景方向**：项目级知识自动提取+跨年度续审继承（当前不做）

## MCP 使用铁律

- **🔴 工具选型阶梯**：符号/调用链/影响面→`codegraph`；wp_code/componentType/spec 进度→`gt-plan`；库表实证→`postgres`；容器日志/健康→`docker`；PR/CI→`github`；框架 API→`context7`；用户可见行为→`playwright`；非符号纯文本→`grep`（末位）
- **🔴 gt-plan 优先于手翻 JSON**：查 wp_code、spec tasks、迁移 V 号先 `wp_lookup` / `spec_status` / `migration_status`
- **🔴 postgres 只读**：仅 `restricted` 模式；禁止经 MCP INSERT/UPDATE/DELETE/DROP；写库验证用 pytest 或现有脚本
- **docker 默认只读**：优先 `list_containers` / `container_logs`；`stop`/`remove`/`restart` 须用户明确要求
- **github 默认只读**：优先查 PR/check/diff；`create_*` / `delete_*` 须用户明确要求
- **context7 补框架文档**：Vue/Element Plus/FastAPI 用法；审计业务规则仍以 spec 三件套为准
- **禁止 MCP 叠床架屋**：同一问题只选一主工具；codegraph 已够勿 postgres 扫源码
- **MCP 失败降级**：服务不可用→回退终端命令并说明；密钥仅 `.cursor/mcp.env`（不进仓库）；改 MCP 配置后 `python tools/mcp-smoke-test.py` 全绿再继续

## 底稿开发铁律

- **风险导向审计**：B50风险→D~N程序表→A13评价错报，全链可追溯
- **componentType 选型**：结构化=d-form-table / 复杂Excel=OnlyOffice / 文档=word-template / 程序表=a-program-console / 函证=confirmation-*（9类）
- **三表HTML渲染**：底稿目录+审定表+附注全走HTML，仅复杂公式/DCF/图表留OnlyOffice
- **联动是核心价值**：ref_index chip+auto_data_source实时取数；孤立底稿=无价值
- **🔴 函证模块跨循环共享**：D0的9个confirmation-*组件跨循环复用(E0/F0/G0/H0/K0/L0)，不为每循环独立开发
- **开发前必先逐sheet读源模板**；**导入导出三级**；**适用性自动判断**
- **模板预填优先于AI生成**：有固定骨架的章节用CHAPTER_TEMPLATE+变量替换做预填，AI仅用于复杂章节
- **🔴 D~N专属组件开发标准模板**：Phase0双源输入(openpyxl脚本读xlsx+底稿模板库md交叉验证)→Phase1三件套→Phase2开发8步(①registry+yaml ②composable分层useXFormulaEngine纯函数 ③主入口sheetName v-if分发defineAsyncComponent lazy ④后端3-4py ⑤注册四件套 ⑥联动TB回写+EventBus+GtIndexChip ⑦UI铁律 ⑧功能方向:联动/美观/溯源/易操作/导入导出/AI/双三模式)
- **🔴 宽表拆分策略**：>15列宽表必须拆分提升可操作性。方案按场景选择：①区段Tab(明细表32列→3区段Tab切换,行同步) ②借方/贷方独立区块(检查表→两区块el-table) ③固定列+滚动列(凭证基础列固定,证据列横滚) ④左右视觉分组(记账凭证|检查证据)。优先减少横滚,让用户单屏看到关键信息
- **通用schema复用**：`{wp_code}-generic.yaml` + pattern matching
- **OO sheet-name必须与源xlsx tab名完全一致**；**多sheet workbook OO隐藏非目标tab**
- **D~N循环全sheet HTML组件化**：OnlyOffice仅为降级/偏好切换
- **🔴 G4-9类列式转置结构**：源模板中"投资项目作为列头+检查项作为行"的转置表必须在前端转换为行式交互视图（列式→行式），不能直接套行式表格模板

## 环境配置

- Python 3.12 / Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`
- vLLM：Qwen3.5-27B-NVFP4，APC+fp8 kv-cache
- Docker：postgres(5432)/redis(6379)/metabase(3000)/pgbouncer(6432)/OCR(8200)
- DB_DISABLE_SSL=True；连接池 150 / PG max_connections=200
- 前端唯一路径：`audit-platform/frontend/`
- **codegraph v0.9.9**；**MCP 7 个**：codegraph/playwright/postgres/github/gt-plan/docker/context7（配置 `.cursor/mcp.json`）；**rtk 0.42.1**；**OnlyOffice 9.4.0**
- 部署v2.0：瘦客户端(Electron)+内网全栈

## PG schema

- **🔴 序时账分录项目级缓存**：`useLedgerCache` composable 模块级单例(key=projectId:year)，C24/截止测试等共享。首次全量拉取后内存缓存30分钟，项目切换自动清空。后端`entries-all` page>1跳过COUNT。最高迁移V098
- trial_balance=standard_account_code/unadjusted_amount/aje_adjustment/audited_amount
- working_paper 无 wp_code（在 wp_index，JOIN）
- recalc 铁律：`tb_balance` v1 口径（借正贷负），`trial_balance` v2 正数；只汇总叶子；损益取发生额
- **tb_ledger人员列**：仅有`preparer`列（制单人），无poster/reviewer；C24-4异常账户测试基于preparer统计
- 契约测试：schema_contract(表级)+column_contract(列级)+componentType 契约 vitest

## 任务状态

### 完成度概览（2026-07-10 归档刷新）
- **340+ spec archived**（含本次121个从active归入）；FE registry **195** componentType；WHOLE 整册专属 **65**（`DEDICATED_COMPONENT_TYPES` 单一来源）
- **A~N + S 全部循环底稿100%完成**；基础设施100%完成
- **Active spec = 0**（全部归档至 `_archive/05-business-features/`）

### git
- 分支 `work/2026-05-30-wp-specs`；最高迁移 V099（以 `migration_status` 为准）
- `origin/HEAD→origin/master` 落后 main 隐患仍在

### 循环进度表（✅完成 / 🟡部分 / 🔵待开发）

| 循环 | 状态 | 备注 |
|------|------|------|
| A/B | ✅ | Dashboard/bundle/风险等已落地 |
| C | ✅为主 | C1 向导+C2~C15+C22~C26 完成；Cx 新增弹窗增强(编制提示/附件OCR)仍待 |
| D | ✅ | D1~D7全部完成✅；D2-refactor完成✅(49/49) |
| E | ✅ | E1 货币资金完成 |
| F | ✅ | F1/F2/F3/F4/F5/F0 全部完成✅ |
| G | ✅ | G1~G14全部完成✅；G0函证完成✅；G5完成✅(含Task11三阶段+ECL) |
| H | ✅为主 | H0/H1~H4/H6/H8~H10 完成；**H5完成✅**(40任务/24sheet/10PBT/行业守卫oil_gas+mining/折耗单位产量法/四区块审定表/EventBus 3事件/TB回写1631+1632)；**H7完成✅**(44任务/26sheet/12PBT/行业守卫agriculture+forestry+livestock+fishery/双计量模式cost+fair_value/产量记录H7独有/互转三方向/直线法折旧/TB回写1621) |
| I | ✅ | I1~I6 全部完成 |
| J | ✅ | J1/J2/J3 + orchestration 全部完成 |
| K | ✅为主 | K0~K9 完成；**K10 全部完成**(31任务/10sheet/6PBT/损益6117发生额贷-借/政府补助核对引擎联动K7/抽凭OCR/EventBus TB回写+A13)；**K11 全部完成**；**K12 全部完成**(29任务/9sheet/5PBT/损益6301发生额贷-借/抽凭OCR/EventBus TB回写+A13)；**K13 全部完成**(29任务/9sheet/5PBT/损益6711发生额借-贷/抽凭OCR/税前扣除性/EventBus TB回写+A13) |
| L | ✅ | L1~L8完成；**L0函证完成✅** |
| M | ✅ | **M1~M10 全部完成**（含 M6 未分配利润枢纽） |
| N | ✅ | N1/N2/N3/N4/N5 全部完成；**N4**(29任务/9sheet/6PBT/损益6403发生额借-贷/多税种测算与N2同源/N2计提对应/EventBus TB回写+A利润表勾稽) |
| S | ✅ | S3~S6/S12~S15/S20/S21/S32/S33/S34/S35全部完成✅ |

### 活跃待办（排期优先）
- **✅ 全部完成**：A~N全部循环底稿+函证+D2-refactor+G5 / S全部 / F循环全部 / L循环全部 / 基础设施(版本链/复核/抽凭/截止测试) — **无活跃待办**
- **🟡 C2~C15 新增弹窗增强**：编制提示琥珀块 + 附件 OCR 作 AI context
- **🟡 B40** 需重建 spec；**B60** 待 vLLM Phase3；AI 对话流 / 存货监盘 P2 / voucher-attachment P2
- **基础设施**：version-trail/audit-review-dialog/全局一致性/voucher-sampling完成✅；cutoff-auto-sampling **未动工**
- **🔴 科目方向铁律**：资产期末=期初+借-贷；负债/权益=期初+贷-借；**M3 库存股=权益备抵借方**；损益取发生额（H10/I6/K8~K13/L8/N4/N5）
- **🔴 向导式隐藏子 sheet**：overrides 标 skip + 保留 WHOLE + skip 过滤须头部 `re.match` 提编码
- **注册表维护**：`dedicated_component_types.py` → WHOLE；契约 `test_dedicated_component_registry_contract.py`（WHOLE⊆VALID∩FE；WHOLE−DISPATCH⊆WHITELIST∪CONFIRMATION）
- **架构债**：拆 event_handlers / Top-5 巨型 Vue / services 按域分包；OCR=RapidOCR 单机；评估见 `docs/proposals/ai-infra-evaluation-2026-07.md`
- **🟡 增强方向**：D2往来款账龄枚举可配置化 — **spec就绪(aging-config-enhancement, 15 tasks)**
- **🟡 增强方向**：C2~C15弹窗增强(琥珀块+OCR AI context) — **spec就绪(c-control-test-popup-enhance, 14 tasks)**
- **🟡 增强方向**：抽凭/版本链模式统一(collapse→dialog, useVersionTrail→Toolbar) — **spec就绪(ui-pattern-unification, 10 tasks)**

## 踩坑铁律（高频）

### 后端
- **大文件导入期间禁改后端代码**→ uvicorn reload 杀 worker
- **event_bus publish 只传 EventPayload**；轻量通知用 broadcast_raw
- **asyncpg不支持IN tuple参数**：必须用`= ANY(:codes)` + `list(...)`
- **router_registry 必查**；**service 只 flush 不 commit**
- **新增 componentType 必须同步更新 VALID_COMPONENT_TYPES**
- **Bundle wpIdMap必须用item.wp_id不能用item.id**
- **D~N专属组件必须有RENDERER_DISPATCH注册**（否则被onlyoffice-sheet吞掉）——C类同理！c1-entity-level-control曾因缺render策略py+DISPATCH注册导致前端只显示OO。**C22再次踩坑：_c22_itgc.py写好但忘了在__init__.py import+注册到DISPATCH dict**
- **🔴 新增 item_id 前缀必须在 checklist_responses.py 白名单注册**：C23A-/C24-/C25-/C26-/C22. 前缀已改为 `pass`(跳过校验)，因为这些专属组件存freeform文本(分析结论/类别/要素等)。其他新专属组件的 item_id 前缀仍需在保存端点的校验链中添加对应 `elif` 分支或 pass
- **🔴 独立子底稿(如C23-1/C23-2)必须在wp_code_overrides中也映射到父组件**：平台可能把多sheet工作簿拆成独立底稿(各有wp_id)，不映射则走OO兜底。**C24-0~C24-5同理已加入**
- **🔴 多底稿共享数据问题**：C24子底稿(C24-3跳号等)各有独立wpId但分录数据存在主C24下→selfLoad数据为空→解法：selfLoad结束后如果journalEntries空+非程序表页→自动调loadFromLedger()从序时账拉取
- **D~N专属组件不能有内部el-tabs**：接sheetName prop用v-if分发
- **🔴 禁止用PowerShell Set-Content/Get-Content操作Vue文件**：会破坏UTF-8编码(中文变乱码)→编译报错。必须只用str_replace工具修改文件内容。C24曾因`-replace`+`Set-Content`导致全文件乱码需git checkout恢复
- **🔴 专属组件复盘3查（F5血泪）**：①双模式别漏——主入口HTML sheet顶部必须放el-segmented(HTML/OO)+useXDualMode，否则Req双模式回归且composable变死代码 ②EventBus跨表值(如审定成本)必须持久化到checklist_responses(独立item_id)+render策略回读seed，只靠同会话事件刷新后丢失 ③TB自动取数字段(只读)必须真接线：render策略查tb_balance(get_active_filter)→html_data返回→FormData提取→组件watch seed setTbValues，光有setter没人调=假只读手填
- **account_package_registry sheets顺序=目录行顺序**
- **导入导出composable必须用http(axios)不能用原生fetch**（无Authorization header→401）
- **StreamingResponse中文文件名必须RFC5987编码**
- **🔴 禁止逐行存储大量数据到checklist_responses**：C24-5异常分录曾逐行存34万×3字段=102万行→selfLoad 14秒。改为JSON打包存1条(`C24-5-anomaly-notes`)。规则：>100行的动态数据必须JSON打包或不存(从源重算)
- **GtOnlyOfficeSheet健康检查响应解析**：`health.data?.data?.healthy`双层兼容
- **OO sheet_name→wp_code解析必须头尾双匹配**：尾部`re.search(r"([A-Z]\d+(?:-\d+)?[A-Z]?)\s*$")`匹配"xxx**D4-5**"；头部`re.match(r"([A-Z]\d+(?:-\d+)?[A-Z]?)\s*")`匹配"**C14-2**评价控制偏差"——两处端点(config+wopi)必须同步
- **聚合包内独立sheet三端点wp_code必须一致**（config/WOPI/callback统一用sheet级解析）
- **project_assignments列名是staff_id不是user_id**
- **结构化章节数据不能存到textarea content**（用独立item_id分别存checklist_responses）
- **CREATE TABLE IF NOT EXISTS 遇旧表列不同不报错但 CREATE INDEX 会炸**：迁移必须用 DO $$ + information_schema 检测列存在性再 ALTER 补齐/RENAME
- **schema漂移修复模式**：`db_extra`类型漂移=DB有列/表但ORM未定义→在ORM模型中补齐列声明即可（不需要新迁移）；V033遗留列(`is_locked`/`bound_dataset_id`)已补入WorkpaperSnapshot；V095 `review_threads`表+`review_messages.thread_id`/`sender_role`已补入phase10_models；V099 `target_user_id`/`target_user_name`/`target_role`已补入ReviewMessage

### 前端
- **底稿编码→实际内容必须查源模板**：不能凭编码猜内容
- **🔴 computed传prop的深层响应陷阱**：`computed(() => state.value.arr[idx])` 只追踪数组元素引用不追踪属性变化→子组件收到prop不更新→"点击没反应"。**修复：`return { ...s }` 展开读取所有属性建立依赖**（C15-2偏差评价决策树踩坑）
- **专属组件跨sheet跳转标准模式**：子组件emit('navigate-sheet', sheetName)→GtWpRenderer.onChildNavigateSheet按sheet_name模糊匹配切换activeSheetName。已注册全局通道，所有专属组件可复用
- **C24四表联动端点**：`GET /ledger/entries-all?year=&page=&page_size=` 全量序时账查询(不限科目,max 5000/页)，供C24细节测试一键拉取分录自动分析
- **render-config返回结构是`{sheets:[{html_data:{...}}]}`**
- **新专属组件必须有selfLoad逻辑**（bundle内嵌场景htmlData为null）
- **A1 Dashboard子Tab组件必须自加载**
- **GtIndexChip的prop名是`value`不是`wp`**
- **API调用可能触发全局404弹窗**：预期404请求加`{_silent:true}`
- **naive UTC时间戳前端少8小时**：补`Z`标记再交fmtDateTime
- **GtAProgramConsole需selfLoad**（bundle内嵌场景）
- **通用AI文本生成端点**：`POST /api/workpapers/{wp_id}/ai/generate-text`在`wp_guidance_chat.py`中，接收prompt/context/existingContent/section，调用`chat_completion`返回内容；所有底稿的AI辅助按钮统一调用此端点
- **Cx-2独立底稿wpCode含"-2"后缀**：`extractCycleNumber`正则不能用`$`锚定尾部；传入composable前必须`.replace(/-\d+$/, '')`去后缀，否则cycleNum=0数据全丢
- **C2~C15 conclusion白名单必须含null守卫+决策树值"是/否"**：`checklist_responses.py`中C2~C15校验缺`and item.conclusion`守卫→null触发422；决策树step1/step4值"是/否"也需加入allowed元组

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
