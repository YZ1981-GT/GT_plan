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
- **codegraph v0.9.8**；**rtk 0.42.1**；**OnlyOffice 9.4.0**
- 部署v2.0：瘦客户端(Electron)+内网全栈

## PG schema

- MigrationRunner（非 alembic）；V+R 配对；`IF NOT EXISTS`；**最高 V097**
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
- **🔵 F2存货(方案B三组拆分)**：✅f2-inventory-main全部完成；✅f2-inventory-valuation-impairment全部完成(19必做任务/44测试全绿/defineAsyncComponent lazy化/F2ValuationTestSheet通用组件+scoped slot)；✅f2-inventory-special全部完成(18sheet/22需求/12PBT全绿/94测试全通过/18任务组全完成)
- **✅ F3应付票据**：全部完成(10sheet/14需求/8PBT/10波次/79测试全绿，主入口+9子组件+10composable+后端3py+导入导出7sheet spec+6大集成)
- **🔵 F4应付账款**：三件套已创建(12sheet/16需求/8PBT/10波次，两级审定+未入账反向截止+供应商融资3区域)
- **✅ F5营业成本**：全部完成(9sheet/14需求/10PBT/10波次全绿)。主入口sheetName v-if分发8专属组件(F5-1审定/F5-2月度2区段/F5-3其他成本/F5-4调整/F5-5比较/F5-6数量核对+OCR/F5-7成本倒轧4区/F5-8重大调整+抽凭)+F5A/未迁移OO兜底；useF5CosOfFormulaEngine 12纯函数；后端render+import_export(6sheet)+AI(5section)+contract-ocr全注册；44测试全绿(15契约+13PBT+6审定+10集成)。命名沿用CosOf/CosSal前缀。EventBus substantive:adjudicated(6401)→F5-7校验区消费
- **🔵 G0投资循环函证**：三件套已创建(9sheet/7需求/8PBT/7波次，复用D0+新建证券差异核对+投资替代程序29列)
- **✅ G1交易性金融资产**：全部完成(16sheet/16需求/12PBT/10波次/75集成测试全绿，主入口sheetName v-if分发+15子组件(core/valuation/classification/inspection)+15composable+后端3py+useG1TraFinFormulaEngine 12纯函数+公允价值Level1-3+SPPI+证券监盘+衍生工具+6大集成)
- **✅ G2应收利息**：全部完成(10sheet/15需求/10PBT/10波次/61测试全绿，主入口sheetName v-if分发+9子组件+2附注+11composable+后端3py+useG2IntRecFormulaEngine 10纯函数+利息365天+ECL三阶段+103行借贷区块+逾期阶段转移+6大集成+双模式)
- **✅ G3应收股利**：全部完成(7sheet/9需求/10PBT/10波次/39任务全绿，主入口sheetName分发+G3-1审定表+G3-2明细33列4区段+G3-3调整分录+G3-4测算2区段+G3-5逾期检查+附注+后端3py+useG3FormulaEngine 8函数+10PBT+52前端+23后端集成测试)
- **✅ G4债权投资-main**：全部完成(8sheet/11需求/13PBT/71任务全绿，主入口sheetName v-if分发+8子组件(core7+measurement1)+useG4MainFormulaEngine 14纯函数+三层审定表+44列5区段Tab+实际利率法双section+附注130行虚拟滚动+导入导出3表9端点+AI 4section+6大集成+76测试+27pytest+20 E2E)
- **✅ G4债权投资-sppi**：全部完成(4sheet/9需求/13PBT/45任务全绿，主入口sheetName分发+4子组件(classification2+inspection2)+useG4SppiFormulaEngine 12函数+业务模式问卷chip+SPPI三步法+证券盘点+倒轧3区段Tab+后端3py+38单元测试)
- **✅ G4债权投资-ecl**：全部完成(7sheet/11需求/14PBT/25必做任务全绿，主入口sheetName v-if分发+7子组件(impairment4+voucher1+reference2)+8composable+后端3py+useG4EclFormulaEngine 14纯函数+三阶段Stage判定+ECL公式链⑥=⑤×②A+①×(②A-②)+凭证OCR+抽凭引擎+借贷平衡+转回校验+导入导出4表9端点+AI 5section+6大集成+18PBT全绿)。复盘修复：useG4EclStageClassification补齐5个缺失方法(init/updateCheckValue/updateCompanyStage/updateAuditStage/updateDiscrepancyNote)+G4TabStageClassification.vue修复3处展开行数据绑定(checks.xxx→sectionXxxChecks)
- **✅ G6其他债权投资-main**：全部完成(43/43任务全绿，主入口+8子组件+4composable+后端4py+useG6MainFormulaEngine 10函数+14PBT+45单元+五大集成+导入导出3表9端点+AI 2section)
- **✅ G6其他债权投资-sppi**：全部完成(45/45任务全绿，主入口sheetName v-if分发+6子组件(fair-value/interest/classification×2/inspection×2)+10composable+后端3py+useG6SppiFormulaEngine 6纯函数+6PBT+SPPI六section80行+业务模式三section问卷+利息实际利率法分组+公允价值Level1-3+盘点倒轧2区段Tab+导入导出4表12端点+AI 4section+版本链+复核对话+141测试全绿)
- **🔵 G5长期应收款**：三件套齐全待开发(16sheet/18需求/18PBT/design+tasks已完成)
- **✅ G8其他权益工具投资**：全部完成(10sheet/CAS22适当性+Level3+OCI凭证/E2E 23+前端29+后端8)
- **✅ G9其他非流动金融资产**：全部完成(AJE/RJE回写+满列UI+AI结论+虚拟滚动+validate/E2E，前端26+后端9测试)
- **✅ G10交易性金融负债**：全部完成(12sheet/10需求/6PBT/17任务全绿，审定24行×3组+validate-formulas API，前端29+后端10测试，E2E 23 passed)
- **✅ G11投资收益**：全部完成(9sheet/9需求/7PBT/12任务7波次全绿)
- **🔵 G12净敞口套期收益**：三件套齐全待开发(9sheet/6需求/7PBT/15任务9波次,套期有效性+净敞口79行+calcHedgeIneffectiveness)
- **🔵 G13公允价值变动收益**：三件套齐全待开发(6sheet/4需求/6PBT/8任务6波次，最简洁)
- **🔵 G14信用减值损失**：三件套齐全待开发(6sheet/4需求/7PBT/8任务6波次，坏账滚动)
- **✅ G6其他债权投资-ecl**：全部完成(39/39任务全绿，主入口sheetName v-if分发+5子组件(impairment4+voucher1)+8composable+后端3py+useG6EclFormulaEngine 8纯函数+三阶段Stage判定+ECL公式链⑥=⑤×②A+①×(②A-②)+凭证OCR+抽凭引擎+借贷平衡+转回校验+导入导出3表9端点+AI 4section+6PBT+33单元+16组件逻辑+20集成测试)
- **🔵 G6/G7三组拆分**：
  - G6其他债权投资：~~main~~✅/~~sppi~~✅/~~ecl~~✅ 全部完成
  - G7长期股权投资：✅**main全部完成(42/42)**+✅**equity-method全部完成(42/42)**+✅**subsidiary全部完成(50/50)**，主入口sheetName v-if分发+7子组件(G7A程序表+G7-1审定表97行5组+G7-2明细表54列5区段Tab+G7-3调整分录+底稿目录+附注上市253行+附注国企355行)+4composable+后端4py+useG7FormulaEngine 8纯函数+9PBT(fast-check)+4单元测试文件(67tests)+后端12PBT(hypothesis)+11集成测试=90测试全绿+6大集成+导入导出2表6端点+AI 2section；权益法组主入口+8子组件(info3+calculation3+impairment2)+4composable+后端3py+useG7EquityMethodFormulaEngine 9纯函数+14PBT(fast-check)+36前端单元测试+21后端测试=71测试全绿+导入导出7表21端点+AI 4section；子公司组主入口sheetName v-if分发+7子组件(initial3+subsequent1+disposal2+voucher1)+4composable+后端4py+useG7SubFormulaEngine 8纯函数+8PBT(fast-check 10tests)+前端152单元测试+后端13PBT+14单元+16集成=205测试全绿+6大集成+导入导出6表18端点+AI 5section+G7-18 3区段Tab+虚拟滚动降级分页
- **🔵 G13公允价值变动收益**：requirements已创建(8sheet/4需求/6PBT，最简单损益+交叉勾稽)待design+tasks
- **🔵 G14信用减值损失**：requirements已创建(8sheet/4需求/7PBT，借方费用+ECL汇总勾稽)待design+tasks
- **✅ voucher-sampling-engine**：全部完成(5种算法+4端点+5Vue组件+D2集成+8后端PBT+13前端PBT+21集成+81单元=123测试全绿)
- **✅ cutoff-test-auto-sampling**：全部完成(V096迁移+LedgerSamplingService+4端点+3Vue组件+D2集成+10PBT+集成测试)
- **✅ workpaper-version-trail**：全部完成(V097迁移+VersionTrailService+5端点+useVersionTrail+GtWpVersionTrail+VersionDiffPanel+5自动钩子+7后端PBT+9前端PBT+16集成+24单元=62测试全绿)
- **✅ 全局一致性治理 3 spec**：~~display-format-single-source~~✅(12任务全完,统一出口fmt/fmtDateTime/fmtPercent+批1-3迁移58文件+CI守卫+Playwright E2E+豁免清单仅剩D循环128条)/~~cycle-palette-single-source~~✅(11任务全完)/~~stale-propagation-cleanup-doc~~✅(全6任务完成)
- **🟡 B40项目组讨论**：需重建spec(实际是CAS1211不是审计抽样)
- **🟡 B60 LLM辅助策略**：待vLLM Phase3
- **🟡 AI对话模式**：章节AI追问用户而非报错，对话流待做
- **🟡 存货监盘P2**：照片+GPS+OCR+差异预警
- **🟡 voucher-attachment-intelligence**：P2凭证附件智能化(依赖voucher-sampling-engine)
- **✅ audit-review-dialog**：通用复核对话(45任务全部完成,V095迁移+router+composable+Vue组件+PBT+集成测试)
- **🔵 H1固定资产**：三件套齐全待开发(26sheet/19需求/17PBT/~83任务,折旧4方法+3分支+54列4区段+监盘+减值DCF+折旧分摊)
- **🔵 H2在建工程**：三件套齐全待开发(21sheet/14需求/12PBT/~55任务,利息资本化2分支+转固联动H1+CAS4五条件+造价14公式)
- **🔵 H3投资性房地产**：三件套齐全待开发(22sheet/16需求/14PBT/~60任务,双计量模式+互转三方向25公式+公允复核+租金27公式)
- **🔵 H4工程物资**：三件套齐全待开发(13sheet/8需求/6PBT/~30任务,标准资产+联动H2)
- **🔵 H5油气资产**：三件套齐全待开发(24sheet/12需求/10PBT/~50任务,行业守卫oil_gas/mining+折耗单位产量法+双分支)
- **🔵 H6固定资产清理**：三件套齐全待开发(8sheet/6需求/5PBT/~25任务,过渡科目期末=0+联动H1+H10)
- **🔵 H7生产性生物资产**：三件套齐全待开发(26sheet/14需求/12PBT/~55任务,双计量+行业守卫农林牧渔+产量记录+互转)
- **🔵 H8使用权资产**：三件套齐全待开发(20sheet/11需求/10PBT/~50任务,CAS21核心+H9强联动+H8-6/H8-8双分支+简化处理)
- **🔵 H9租赁负债**：三件套齐全待开发(~10sheet/8需求/8PBT/~35任务,CAS21配对+负债贷方+摊销表实际利率法+现值折现)
- **✅ H10资产处置损益**：`h10-asset-disposal-income` 全量完成(8sheet/6115损益类发生额/7审定行+3区段明细+检查表+附注；vitest 24 + pytest 11 + E2E 10)
- **🔵 I1无形资产**：三件套齐全待开发(18sheet/14需求/12PBT/~55任务,摊销2分支+DCF减值+三科目+权属94行+I2转入)
- **🔵 I2开发支出**：三件套齐全待开发(21sheet/14需求/10PBT/~55任务,CAS6五条件核心+I6↔I2双向+I1转入+4类检查+截止双向)
- **🔵 I3商誉**：三件套齐全待开发(15sheet/10需求/8PBT/~40任务,不摊销!仅年度减值+DCF/CGU+先冲商誉再分摊+100×16+153行)
- **🔵 I4长期待摊费用**：三件套齐全待开发(12sheet/8需求/6PBT/~30任务,摊销2方法分支直线+工作量)
- **🔵 I5其他非流动资产**：三件套齐全待开发(9sheet/6需求/5PBT/~25任务,最简标准底稿)
- **🔵 I6研发费用**：三件套齐全待开发(11sheet/10需求/8PBT/~35任务,损益类取发生额+I6↔I2双向VR-I6-01+月度12列+截止双向)
- **🔵 J循环三件套齐全待开发**：J1应付职工薪酬(16sheet,负债贷方+月度12列+5类检查+工资社保测算+K8K9联动)/J2设定受益计划(9sheet,负债+精算假设DBO+精算师ISA620+B51联动)/J3股份支付(6sheet,无独立科目跨M4/K8/J1+Black-Scholes+等待期分摊)
- **🔵 K循环K1~K13三件套齐全待开发(跳过K0走函证)**：K1其他应收款(ECL三阶段)/K2其他流动资产(合同成本摊销)/K3其他应付款(负债)/K4其他流动负债(负债)/K5预计负债(或有事项三级+最佳估计)/K6持有待售(CAS42五条件+减值孰低)/K7递延收益(负债+政府补助分摊)/K8销售费用+K9管理费用(损益+截止双向+实质性分析)/K10其他收益+K11资产减值损失+K12营业外收入+K13营业外支出(损益类取发生额)
- **🔵 L1短期借款**：进行中(25/34任务,Phase0~4全部完成)
- **🔵 L2应付利息**：进行中(14/29任务,Phase0~3全完+Phase4进行中:4.1目录✅4.2审定表✅4.3明细表in_progress)
- **🔵 L循环L3~L8三件套齐全待开发(跳过L0走函证)**：L3长期借款(负债+利息测算+征信+逾期+抵质押)/L4应付债券(负债+实际利率法EIR2分支+权益负债划分+89列宽表)/L5长期应付款(负债+未确认融资费用摊销)/L6专项应付款+L7其他非流动负债(负债)/L8财务费用(损益+利息汇聚L1L3L4L5+截止)
- **🔵 M循环M1~M10三件套齐全待开发**：M1应付股利(负债+外币汇率)/M2实收资本(权益+验资+上市非上市双版本)/M3库存股(**权益备抵借方!期末=期初+借-贷**)/M4资本公积(权益+接收J3)/M5盈余公积(权益+10%计提)/M6未分配利润(权益+利润分配结转枢纽)/M7专项储备(权益+安全生产费)/M8一般风险准备(权益+金融行业守卫)/M9其他综合收益(权益+接收G8/J2)/M10其他权益工具(权益+CAS37负债权益区分)
- **🔵 N循环N1~N5三件套齐全待开发**：N1递延所得税资产(资产借方+暂时性差异×税率+可弥补亏损)/N2应交税费(负债+多税种测算增值税房产税土增税+出口退税)/N3递延所得税负债(负债+与N1对应)/N4税金及附加(损益+多税种+N2计提对应)/N5所得税费用(损益+当期所得税计算+纳税调整107行大表+研发加计接I6I2+递延核对N1N3+高新认定)
- **🔵 H0/K0/L0函证三件套齐全待开发(复用D0共享9组件)**：H0固定资产循环函证(9sheet,新建H0-5替代程序抵押担保)/K0管理循环函证(11sheet,新建K0-5其他应收款+K0-6其他应付款替代程序)/L0债务循环函证(10sheet,新建L0-5长期应付款替代程序+银行函证)
- **✅ D~N全循环spec三件套齐全**：D/E/F/G/H/I/J/K/L/M/N + H0/K0/L0函证 全部创建完成(仅待开发)，均对齐D4标准(sheetName v-if分发+composable分层+PBT+Phase0~7)
- **🔵 S类特定项目程序6 spec三件套齐全待开发**(源模板87 xlsx，分析工具backend/scripts/analyze_s_category.py+dump_s34/s_special_content.py)：
  - `s34-ipo-review-bundle`(IPO大组件,S34-0~41共41底稿,一行分组页签8主题+S34-0核查清单总览+法规溯源证监会沪深北+公式子检查表,12需求/7波)
  - `s32-fraud-response-bundle`(551文舞弊13情形,导引表IC-0/披露格式参考IC-X子sheet,8需求/7波)
  - `s33-announcement14-bundle`(14号公告9核查,S33-4隐藏程序表变体,8需求/7波)
  - `s35-refinancing-bundle`(再融资5核查+明细子表,8需求/7波)
  - `s-estimate-calculation-workpapers`(计算型专属4componentType:s15-eps-roe/s21-data-asset/s20-revenue-deduction/s3-policy-change,纯函数公式引擎EPS加权股数+ROE+资本化归集,审定回写,11需求/8波)
  - `s-special-transaction-workpapers`(交易/专家/检查型:6专属s4/s5/s6/s12/s13/s14+检查表型走a-program-console,S4商业实质IF/S5债权债务人损益/S12专家3分支/S17旧xls转换,11需求/8波)
  - bundle类均对齐a17-bundle;专属类均对齐D4;S类程序表主体用a-program-console embedded
- **✅ C1企业层面控制重构完成**：从sheetName v-if平铺改为"主控台+多级Dialog/Drawer向导模式"（九段折叠进度→步骤弹窗55%→过程记录全屏Dialog→嵌套Detail 70%→样本表85%→示例Drawer 45%），1908行SFC，0 TS诊断。子sheet(C1-1~C1-4-6)在wp_code_overrides标记skip+从_WHOLE_WP_MULTISHEET_DEDICATED移除→外层tab只显示主程序表1个页签
- **🔴 向导式组件隐藏子sheet tab方法**：①wp_code_overrides子编码标skip ②保留_WHOLE_WP_MULTISHEET_DEDICATED(否则主sheet走class_code派生丢专属组件) ③wp_render_config的skip过滤用`_SHEET_CODE_RE`尾部正则匹配不到头部编码(如"C1-1 xx")→需补充`re.match(r'([A-Z]\d+(?:-\d+)*)', sheet_name)`头部提取
- **🔵 C类控制测试5 spec三件套齐全待开发**(源模板36 xlsx无VBA,导航靠底稿目录+命名区域下拉,分析工具backend/scripts/analyze_c_category.py+dump_c_content.py。C2~C15已归档c-control-test-component)：
  - **✅ C2~C15统一方向已完成**：c-control-test从视图切换改为弹窗层叠模式(L0汇总表始终可见+L1控制详情Dialog 80%+L2偏差评价Dialog 65%嵌套)，14循环共用，子组件(SummaryTable/SubPage/DecisionTree)不动
  - **✅ C2~C15新增控制点交互已完成**："+新增"→弹出65% Dialog填写15字段(3列grid+AI辅助描述)+频率→样本量建议提示→保存入库→汇总表自动增行；FAB"+"同入口；汇总表保留inline快编辑
  - **🔵 C2~C15新增弹窗增强**：待实现①编制提示(琥珀色块)放弹窗顶部供用户参考+作为AI system context ②附件上传区(右上卡片)上传制度/访谈/合同→OCR识别→作为AI生成"控制描述"的参考材料
  - `c1-entity-level-control`(C1企业层面控制,COSO五要素分组程序中控台+C1-4财报内控6子表样本勾稽,8需求/6波)
  - `c22-itgc-bundle`(C22 IT一般控制34sheet:SA信息安全/PE运行维护/PM程序变更/NS新系统4大类+主矩阵总览+缺陷联动汇总C21-1,含C21 IT专业成员,9需求/7波)
  - `c23-c24-journal-entry-testing`(C23分录控制测试人员核对+C24分录细节测试useC24AnalyticsEngine:借贷平衡/科目对比/跳号/异常筛选/本福特首位数分布,分录导入,8需求/7波) ✅**全部完成(25/25任务)**
  - `c25-c26-internal-audit-info-control`(C25利用内审10步评估+命名下拉/C26信息处理控制矩阵动态行+四要素完整性准确性授权访问限制,7需求/6波) ✅**全部完成(20/20任务)**
  - `c-control-test-refresh`(C2~C15翻新真实结构:目录+汇总表15列+Cx-1-X控制测试抽样+Cx-2偏差评价6步决策树IF驱动+样本规模建议+缺陷联动A14+B23/B50 EventBus,沿用c-control-test类型兼容C{n}-历史数据,取代c-control-test-component,8需求/7波) ✅**全部完成(25/25任务)**
- **🔵 L1短期借款**：进行中(25/34任务,Phase0~4全部完成:双源验证+注册+公式引擎365天制+利息引擎+PBT P1-P8+13 composable+12 Vue组件全部创建,Phase5后端ready)
- **🔴 科目方向铁律(spec已落实)**：资产类期末=期初+借-贷；负债类/权益类期末=期初+贷-借；**库存股M3是权益备抵借方(期末=期初+借-贷)**；损益类取发生额(从tb_ledger,非余额)——H10/I6/K8~K13/L8/N4/N5同款
- **🔵 D2 refactor 待出 spec**：去el-tabs→sheetName分发+OO双模式+composable拆分+子目录重组（对齐D4标准）
- **架构优化**：①拆 event_handlers.py ②前端 Top-5 巨型 Vue 拆分 ③services/ 按域建子包
- 外部依赖：LLM embedding / 合并 UAT / GitHub 默认分支改 main / MinerU+OCR
- **🟡 Unlimited-OCR 评估**：综合评估文档已升级为`docs/proposals/ai-infra-evaluation-2026-07.md`(OCR+Zvec+Embedding+MinerU+vLLM+GitHub Top20+部署方案+上线Checklist)
- **🔴 单机OCR方案决策**：单机版用RapidOCR(pip install rapidocr-onnxruntime,50MB ONNX,CPU<1s/页)替代PaddleOCR Docker；有GPU用户选装Unlimited-OCR-NVFP4；云端保留Docker容器
- **🟡 Zvec 向量数据库候选**：alibaba/zvec v0.5(进程内嵌入式,DiskANN+FTS+混合检索,pip install zvec)，替代ChromaDB做RAG/语义搜索，适合内网单机部署
- **🟡 GitHub Top20 借鉴**：RAGFlow(分块+引用溯源UI+Reranker,P1)/Mem0(持久记忆→跨年度续审,P2-v3.0)/Browser-use(审计数据自动采集,P3-Electron后)

## 踩坑铁律（高频）

### 后端
- **大文件导入期间禁改后端代码**→ uvicorn reload 杀 worker
- **event_bus publish 只传 EventPayload**；轻量通知用 broadcast_raw
- **asyncpg不支持IN tuple参数**：必须用`= ANY(:codes)` + `list(...)`
- **router_registry 必查**；**service 只 flush 不 commit**
- **新增 componentType 必须同步更新 VALID_COMPONENT_TYPES**
- **Bundle wpIdMap必须用item.wp_id不能用item.id**
- **D~N专属组件必须有RENDERER_DISPATCH注册**（否则被onlyoffice-sheet吞掉）——C类同理！c1-entity-level-control曾因缺render策略py+DISPATCH注册导致前端只显示OO
- **D~N专属组件不能有内部el-tabs**：接sheetName prop用v-if分发
- **🔴 专属组件复盘3查（F5血泪）**：①双模式别漏——主入口HTML sheet顶部必须放el-segmented(HTML/OO)+useXDualMode，否则Req双模式回归且composable变死代码 ②EventBus跨表值(如审定成本)必须持久化到checklist_responses(独立item_id)+render策略回读seed，只靠同会话事件刷新后丢失 ③TB自动取数字段(只读)必须真接线：render策略查tb_balance(get_active_filter)→html_data返回→FormData提取→组件watch seed setTbValues，光有setter没人调=假只读手填
- **account_package_registry sheets顺序=目录行顺序**
- **导入导出composable必须用http(axios)不能用原生fetch**（无Authorization header→401）
- **StreamingResponse中文文件名必须RFC5987编码**
- **GtOnlyOfficeSheet健康检查响应解析**：`health.data?.data?.healthy`双层兼容
- **聚合包内独立sheet三端点wp_code必须一致**（config/WOPI/callback统一用sheet级解析）
- **project_assignments列名是staff_id不是user_id**
- **结构化章节数据不能存到textarea content**（用独立item_id分别存checklist_responses）
- **CREATE TABLE IF NOT EXISTS 遇旧表列不同不报错但 CREATE INDEX 会炸**：迁移必须用 DO $$ + information_schema 检测列存在性再 ALTER 补齐/RENAME
- **schema漂移修复模式**：`db_extra`类型漂移=DB有列/表但ORM未定义→在ORM模型中补齐列声明即可（不需要新迁移）；V033遗留列(`is_locked`/`bound_dataset_id`)已补入WorkpaperSnapshot；V095 `review_threads`表+`review_messages.thread_id`/`sender_role`已补入phase10_models

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
