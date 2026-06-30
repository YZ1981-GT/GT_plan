---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤ 200 行**。完成事项明细 → `#dev-history`；技术决策 → `#architecture`；规范铁律 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）
- **输出分步但连续做完**；**任务标记不能假绿**；**彻底解决不绕开**；**optional(*)任务也要做完**
- **🔴 codegraph 优先于 grep**：79k 节点/160k 边/4449 文件；grep 仅用于非符号文本
- **触类旁通**；**改动前先 spec 三件套**（>500行/3+组件/跨前后端）；**改动后必 Playwright 实测**
- **UI 全中文化**；**报表金额默认"元"**；**中文场景全链路不能崩**
- **不要考虑轻量**：要考虑针对性、联动性、美观性、实操性、易懂性；审计UI要有逻辑追溯能力
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
- **A17系列联动策略(2026-06-26确认)**：只做GtIndexChip跳转，不做EventBus数据自动同步（A17-1引用A17-2-1/A17-3/B50/A13/A1-15均为跳转；A17-3-1对A17-3为只读引用展示）
- **✅ A3合并系列治理(2026-06-28完成)**：**第一步**：①overrides补齐(A3-1/-2/-4/-5/-6/-7→skip合并模块镜像,A3-3→audit-sheet) ②GtA3ConsolidationConsole加「合并底稿索引」区(7行route:chip跳合并模块Tab) ③修复ConsolidationIndex的route.query.tab→activeTab别名同步(TAB_ALIAS:scope→structure/trial→consol_tb/notes→consol_note)。**第二步**：A3-8商誉减值测试专属组件`a3-8-goodwill-impairment`，9/9任务全绿(47测试:12 PBT+14单元+16注册契约+5后端)。useA38Goodwill公式引擎(减值=max(diff,0)/CAPM Ke=Rf+β(Rm-Rf)/WACC,D+E=0→null/DCF折现/终值base(1+g)/(r-g)/可收回孰高/减值损失先冲商誉再按比例二次分摊总和守恒)；GtA38GoodwillImpairment.vue 4Tab+双模式+GtIndexChip(I3-2/I3-6/I3-7只跳转)。**A3-8↔I3=合并层↔单体层**(I3-6减值/I3-7可收回=单体,A3-8=合并)。**第三步**：GtA3ConsolidationConsole升级为el-tabs bundle(3Tab:程序表/A3-3 OO/A3-8专属),子底稿wpId通过getWpIndex解析,v-if按wpIdMap动态显示。注：测试项目0ec33无A3-8 wp实例,全UI流程待合并项目验证
- **通用schema复用**：`{wp_code}-generic.yaml` + pattern matching
- **开发前必先逐sheet读源模板**；**导入导出三级**；**适用性自动判断**
- **模板预填优先于AI生成(2026-06-28)**：结构化章节组件中，源模板有固定骨架文本的章节优先用CHAPTER_TEMPLATE+projectContext变量替换做预填（即时无网络），AI仅用于需跨底稿总结/判断的复杂章节
- **结构化章节编制提示模式(2026-06-28)**：源模板红色提示文字用`<details>`折叠展示(蓝左边线+浅蓝背景)，默认收起不干扰编辑；有表格结构的子节用el-table动态行而非textarea(如Ch4特别风险4列/职业判断4列)；持久化用独立item_id前缀+JSON.stringify rows
- **A17-1第8章自动取数模式(2026-06-28)**：GtA171Chapter8从A1-13/A1-14 analytical_review_service自动拉取显著变动项(resolver:`a17_ch08_analytical_review`注册于`_a17_ch08.py`)，前端调`/api/projects/{pid}/auto-data/a17_ch08_analytical_review?year=`展示表格，AI生成时把变动列表作为existing_content传给LLM
- **AI生成表格数据规范(2026-06-28)**：表格型子节的AI guidance要求LLM按JSON数组返回(每行含各列字段名)，前端用`utils/aiJsonParse.ts`的`tryParseJsonArray`三层容错解析(直接parse/代码块/[]提取)，失败降级填第一列

## 环境配置

- Python 3.12 / Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`
- **vLLM**：`cu130-nightly`，Qwen3.5-27B-NVFP4，APC+fp8 kv-cache
- **rtk 0.42.1**：CLI token 压缩代理
- Docker：postgres(5432)/redis(6379)/metabase(3000)/pgbouncer(6432)/OCR(8200)
- **DB_DISABLE_SSL=True**；连接池 150 / PG max_connections=200
- **前端唯一路径**：`audit-platform/frontend/`
- **codegraph v0.9.8**：hook 自动 sync
- **OnlyOffice 9.4.0**：见踩坑节
- **部署v2.0**：瘦客户端(Electron)+内网全栈(FastAPI+PG+Redis+vLLM+MinIO)

## 迁移与 PG schema

- MigrationRunner（非 alembic）；V+R 配对；`IF NOT EXISTS`；**最高 V094**
- **真实列速查**：trial_balance=standard_account_code/unadjusted_amount/aje_adjustment/audited_amount；working_paper 无 wp_code（在 wp_index，JOIN）
- **recalc 铁律**：`tb_balance` v1 口径（借正贷负），`trial_balance` v2 正数；只汇总叶子；损益取发生额
- **报表引擎**：统一从 trial_balance 取数，TB()/SUM_TB() 公式路径
- **契约测试**：schema_contract(表级)+column_contract(列级)+componentType 契约 vitest

## 任务状态

### 🟢 里程碑（219 archived / 10 active）
- **🔵 全局一致性治理 3 spec**（2026-06-23 开，三件套齐全，复盘确认未做才建的）：①`display-format-single-source`(P0金额/时间格式化收口displayPrefs+CI守卫,43处formatAmount+70处裸toLocaleString) ②`cycle-palette-single-source`(P0循环色板cyclePalette.ts+--gt-cycle-*,4处分裂) ③`stale-propagation-cleanup-doc`(P2删死代码+分层文档)。**注：建议书原列P0安全项(report-cache-year/custom-query-auth/authz-baseline)+联动收口均已6-23归档,故不重复建**
- **✅ a1-12-dual-mode-checklist**（2026-06-25 完成）：A1-12重大事项检查表双模式渲染，9/9必做任务全绿（23 PBT fast-check + 9 hypothesis + 9 vitest + 4后端集成 + 2 Playwright E2E = 99测试）。新componentType `a1-12-dual-checklist`，专属卡片UI(14项适用性+索引跳转+进度色块+签字联动+第二类动态添加)+OnlyOffice双模式切换+debounce自动保存。后端DOCX解析器+round-trip验证
- **✅ a1-11-signing-control-form**（2026-06-23 完成）：A1-11签发流转表HTML专用组件，26/26任务全绿（含8 PBT fast-check + 30 vitest + 1 hypothesis集成测试）
- **2026-06-23 归档 12 spec**：a17-summary-enhancement / a-cycle-docx-online / a-review-checklist-rbac / a13-misstatement-aggregation / cross-workpaper-dispatch-persistence / authorization-enforcement-baseline / custom-query-authorization-hardening / qc-python-rule-load-hardening / report-cache-year-isolation / single-source-cleanup / multi-worker-readiness / workpaper-save-orchestrator
- **D0 函证模块**（2026-06-22）：10 spec / 283 任务 / 9 componentType。已 Playwright 验证
- **A~S 全循环底稿**（2026-06-19）：13循环 / 568 任务 / ~815 wp_code / 2457 测试
- **底稿模块治理 6 spec + 底稿优化 4 项 + A1-12 核查表**

### git 状态
- 分支 `work/2026-05-30-wp-specs`，最高迁移 V093
- **远程默认分支隐患**：`origin/HEAD→origin/master` 落后 main 298 commit

### 待办
- **✅ a1-15-disclosure-checklist**(2026-06-25 完成)：A1-15企业会计准则财务报表列报及披露核对表专属组件，10/10任务全绿（41 PBT fast-check + 17 hypothesis + 32 vitest + 5后端集成 + 16注册契约 + 5 Playwright E2E = 111测试）。新componentType `a1-15-disclosure-checklist`，useA115Checklist+useA115Navigation 2 composables+GtA115DisclosureChecklist.vue。35章节卡片UI+左侧导航+section-based lazy rendering(IntersectionObserver±1)+Y/N/NA色彩编码+CAS_Ref索引号+Cross_Reference_Map(11映射)科目跳转联动(GtIndexChip)+TOC适用性级联NA+debounce 2s自动保存+双模式(el-segmented)+OnlyOffice健康检查禁用。后端复用`_parse_a1_15`+`format_a115_to_summary` round-trip。**A1-16也复用此componentType**(render函数用ctx.wp_code动态分发)
- **✅ a1-17-corresponding-data**(2026-06-26)：A1-17对应数据程序表专属组件，极简5条卡片。新componentType`a1-17-corresponding-data`+GtA117CorrespondingData.vue(~250行)。序号标签+是/否/不适用+执行人+执行情况textarea+索引号+进度条+debounce自动保存。后端`_a117_corresponding.py`从checklist_responses读JSON remark
- **✅ a9-1-deficiency-letter**(2026-06-27 完成)：A9-1内控缺陷沟通函专属组件，22/22全绿（12 hypothesis + 18 fast-check + 50 vitest + 4 Playwright E2E = 84测试）。新componentType`a9-1-deficiency-letter`，useA91DeficiencyLetter+GtA91DeficiencyLetter.vue(~600行)。7区块卡片UI(收件人自动填+独立性Y/N+内控缺陷B22B联动+审计委员会可选+签发+管理层回复)+左侧mini导航+双模式+AI整改建议disabled预留。B22B按severity自动分组+EventBus `deficiency:severity-evaluated`实时刷新+2s debounce自动保存+JSON remark持久化
- **✅ a9-2-deficiency-letter-governance**(2026-06-27 完成)：复用GtA91DeficiencyLetter+variant='governance'，13/13全绿（119测试含A91回归）。差异：收件人=董事会、无一般缺陷、无管理层回复区、item_id用a92-隔离。后端`_a91_deficiency_letter.py`重构为`_load_section_data(ctx,prefix)`+`_load_project_context`复用
- **✅ a17-6-closing-meeting**(2026-06-28 升级完成)：从极简6字段卡片升级为源模板对齐结构。10项会议议题卡片+元信息(12字段:含会议地点/组织者/召集人/记录员)+编制提示折叠(10项AGENDA_GUIDANCE)+双模式(el-segmented)+双向回写(a176_docx_sync.py generate-docx/sync-from-docx)+AI功能(复用a171/ai-generate端点per-agenda-item)+OO健康检查降级。Bundle kind从word→closing-meeting，新增a176_docx_sync.py路由+service。item_id前缀`a176-meta-*`/`a176-agenda-{1-10}`
- **✅ A17-5核对表UI修复(2026-06-29)**：①GtA17Bundle A17-5 tab增加el-segmented子表切换(财报审计/内控审计/IPO/新三板/函证)，按项目实际生成的A17-5-x子底稿动态显示；②GtChecklistNav对"审计目标"section改为不可点击header+6个圆形数字tag(目标筛选器)；③GtChecklistTable新增OBJECTIVE_PROGRAM_MAP静态映射(6目标→47程序多对多)，工具栏"按目标筛选"下拉+左侧tag联动过滤核对程序项。纯前端方案不改后端
- **✅ a18-1-regulatory-submission**(2026-06-26 完成)：极简3区块(收件人前缀+正文自动填+签发)。15/15全绿(26测试)。新componentType`a18-1-regulatory-submission`
- **✅ a18-2-regulatory-communication**(2026-06-26 完成)：5区块(4事项Y/N/NA适用性+双CPA签+提示折叠)。15/15全绿(80测试)。新componentType`a18-2-regulatory-communication`
- **✅ a8-1-other-info-representation**(2026-06-26 完成)：6条声明卡片(3含动态文件清单+1日期+1 Y/N+1 textarea)+签字区。17/17全绿(106测试)。新componentType`a8-1-other-info-representation`
- **✅ a11-1-subsequent-events-inquiry**(2026-06-26 完成)：10个CAS QA卡片+元信息+证据+左侧12项导航。17/17全绿(103测试)。新componentType`a11-1-subsequent-events-inquiry`
- **✅ a17-3-consultation-record**(2026-06-26 完成)：元信息+4章+文件tag+AI准则查询disabled。16/16全绿(88测试)。新componentType`a17-3-consultation-record`
- **✅ a17-3-1-consultation-execution**(2026-06-26 完成)：极简5区块+A17-3引用联动(只读)。16/16全绿(69测试)。新componentType`a17-3-1-consultation-execution`。**2026-06-28升级完成**：Bundle路由改专属组件+projectId+OO双模式+编制提示+Section三拆3子区(Y/N radio-button×2条件展开)+全Section AI按钮+A17-3实时联动(只读摘要+🔄刷新)+AI生成传A17-3摘要作context
- **✅ a17-4-disagreement-record**(2026-06-26 完成)：人员动态表+6章+签字区。17/17全绿(75测试)。新componentType`a17-4-disagreement-record`
- **✅ a17-7-independence-declaration**(2026-06-26 完成)：variant双变体(team/committee)+签字表预填+威胁记录3类。22/22全绿(102测试)。新componentType`a17-7-independence-declaration`。**2026-06-29升级完成**：从5区块卡片升级为A17-1模式5章节结构。左侧导航(completionDots)+5章折叠卡片(Ch1声明正文+期间/Ch2承诺事项5项Y/N/Ch3签字确认表+批量签署弹窗/Ch4合伙人审查+按钮签字/Ch5威胁记录3类)+编制提示(CHAPTER_GUIDANCE×5折叠)+AI辅助(`POST /a177/ai-generate`)+双模式(`POST /a177/generate-docx`+`POST /a177/sync-from-docx`)+`a177_docx_sync.py`双向同步服务+`a177_ai_generate.py`路由注册到router_registry"AI与辅助"组。签字采用按钮弹窗确认模式(ElMessageBox.confirm显示签署人+不可撤销警告)。"发送确认"按钮调用IndependenceSigningService批量推送全员电子签署
- **✅ word-template-dual-mode**(2026-06-27 完成)：所有word-template底稿(25个wp_code)统一双模式框架，33/33任务全绿（7 PBT fast-check + 4 PBT GtView + 32 vitest + 9 guidance + 17 import + 5 Playwright E2E = ~120测试）。el-segmented切换(结构化视图/在线编辑)+后端python-docx模板解析器+占位符提取+checklist_responses持久化(item_id=`wt-{wp_code}-{field_id}`)+AI预填按钮(disabled占位)+导出占位符回写+OO callback反写+导出Word(合并responses)+导出模板(带蓝色说明事项include_guidance)+导入数据(POST import-structured离线docx解析回写)。不新建componentType，WorkpaperWordEditor内部增加结构化视图+toolbar三按钮
- **✅ a17-1-audit-summary**(2026-06-27 完成)：A17-1重大事项概要汇总专属组件，22/22全绿（85测试）。新componentType`a17-1-audit-summary`，useA171AuditSummary+useA171Navigation(scrollspy+completionDots)+GtA171AuditSummary.vue(~280行)。签字表10×3+16章折叠卡片(10 textarea+2 table动态增删+4 Y/N条件展开)+GtIndexChip(B50/A13/A1-15)+左侧导航(完成指示)+AI disabled按钮+2s debounce自动保存
- **✅ a17-2-1-kam**(2026-06-27 完成)：A17-2-1关键审计事项(KAM)专属组件，18/18全绿（92测试: 2 hypothesis + 30 fast-check + 43 vitest + 19后端 + 4 Playwright E2E）。新componentType`a17-2-1-kam`，useA1721Kam+GtA1721Kam.vue(~435行)。候选清单el-table(4列+communicate高亮)+KAM动态卡片(6 textarea+GtIndexChip+el-popconfirm删除)+附注per KAM+适用性el-switch(隐藏section 2/3)+EventBus `kam:updated`+2s debounce自动保存
- **✅ a10-1-governance-communication**(2026-06-27 完成)：A10-1与治理层沟通函专属组件，22/22全绿（77测试）。新componentType`a10-1-governance-communication`，useA101GovernanceCommunication+useA101Navigation(scrollspy)+GtA101GovernanceCommunication.vue(~280行)。左侧导航(180px sticky)+16章折叠卡片(ch1-5展开/ch6-16折叠)+ch3服务费el-table(5行+合计)+ch9 GtIndexChip(A9-2)+ch13 GtIndexChip(A13)+签发区+提示折叠+2s debounce自动保存
- **✅ a12-1-legal-confirmation**(2026-06-27 完成)：A12-1法律事务确认函专属组件，19/19全绿（91测试）。新componentType`a12-1-legal-confirmation`，useA121LegalConfirmation+GtA121LegalConfirmation.vue(~290行)。发函(白卡片:收件人+3问询+诉讼动态列表+签章+回函信息)+回函(浅蓝卡片:诉讼radio条件展开+费用radio条件展开+律师签字)+GtIndexChip(A5-3)+2s debounce自动保存
- **✅ a27-1-it-audit-memo**(2026-06-27 完成)：A27-1 IT审计总结备忘录专属组件，22/22全绿（83测试）。新componentType`a27-1-it-audit-memo`，useA271ItAuditMemo+GtA271ItAuditMemo.vue(~280行)。备忘录抬头4字段+IT团队动态表+7章卡片(ch3/ch6三选一radio+ch3→ch4条件联动)+4个GtIndexChip(B22A-4-3/C22/C21-1/B23-15)+2s debounce自动保存
- **🔵 a18-1-regulatory-submission**(2026-06-26 开，三件套齐全)：A18-1向监管部门报送审计小结。极简3区块(收件人前缀+正文自动填+签发)。~150行。15任务
- **🔵 a18-2-regulatory-communication**(2026-06-26 开，三件套齐全)：A18-2与监管层沟通函。5区块(4事项Y/N/NA适用性+双CPA签+提示折叠)。~300行。15任务
- **✅ a5-1-cashflow-audit**(2026-06-27 完成)：A5-1现金流量表审计精美HTML专属组件，22/22必做全绿（57测试: 47 vitest + 10后端）。新componentType`a5-1-cashflow-audit`，useA51CashflowAudit(公式引擎)+useA51EditorMode+GtA51CashflowAudit.vue(~250行)。6 Tab(程序表21步Y/N/NA+审定表8行公式+勾稽4组差异高亮+核查子公司+核查明细+其他CF 3类收支)+会计提示el-drawer(480px 4节)+el-segmented双模式+CashFlowVerification.vue内嵌A5-1 Tab
- **✅ b50-risk-assessment**(2026-06-23 完成)：B50风险评估矩阵专属组件，35/35任务全绿（12 PBT + 19 vitest + 1 hypothesis）。3 composables + 750行 Vue 组件 + CAS强制 + EventBus联动
- **✅ b22a-control-matrix**(2026-06-23 完成)：B22A内控五要素矩阵专属组件，38/38任务全绿（20 PBT fast-check + 27 vitest + 1 hypothesis）。3 composables + 6-tab + IT子区6面板 + Element_Score自动计算 + 续审继承 + 3 EventBus事件
- **✅ b22b-deficiency-evaluation**(2026-06-23 完成)：B22B内控缺陷评价表，42/42任务全绿（16 PBT fast-check + 40 vitest + 1 hypothesis）。3 composables + 900行 Vue + 严重程度建议算法 + B15重要性对比 + B22A→B22B→B50 EventBus三方闭环
- **✅ b23-process-control**(2026-06-23 完成)：B23业务流程与控制了解表，59/59任务全绿（12 PBT fast-check + 66 vitest + 1 hypothesis）。3 composables + 8流程卡片 + 穿行测试 + 状态仪表盘 + 导入导出三级 + 关联流程图SVG + B22A→B23→B50→D~N四方联动。PBT发现并修复elementScores浅拷贝bug
- **✅ b30-group-audit**(2026-06-24 完成)：B30集团审计范围确定底稿，25/25必做任务全绿（37 optional测试待执行）。3 composables(1134行主composable) + 969行 Vue + 集团结构树(el-tree拖拽5层) + 组成部分分类(15%阈值) + 重要性分配(0.75系数,clamp[15%,85%]) + 覆盖率热力图(加权1.0/0.5/0.25/0.0) + 组成部分审计师 + B15→B30→B50三方联动 + 导入导出三级
- **🟡 B60 LLM辅助策略文档**：待 LLM Phase3 接入后，用 vLLM 辅助生成总体审计策略文档（不需专属组件，需 resolver + /ai-generate 接口）
- **❌ b40-sampling-strategy 已删除**(2026-06-24)：B40 实际是"项目组讨论程序表"(CAS 1211)而非"审计抽样策略"，requirements 已删除需重新建 spec
- **✅ b1-4-due-diligence-report**(2026-06-27 完成)：B1-4尽职调查报告专属组件，24/24全绿（12 hypothesis + 20 fast-check + 28 vitest + 17后端集成 + 16契约 + 4 Playwright E2E = 97测试）。新componentType`b1-4-due-diligence-report`，useB14DueDiligence+useB14Navigation 2 composables+GtB14DueDiligenceReport.vue(~450行)。13章折叠卡片(textarea/table/mixed)+左侧导航(180px sticky scrollspy+完成点+进度条)+标准版/简化版双变体(ch11/ch12可见性控制)+签字区(partner/manager/report_date)+GtIndexChip(B15/B22A/B50)+AI辅助生成(POST b14/chapters/{chId}/ai-generate+知识库检索+跨章上下文+CPA专属prompt)+2s debounce自动保存+双模式(el-segmented)+OO健康检查
- **🟡 B类全面专属组件升级计划**(2026-06-24确认)：用户要求所有B类底稿均升级为专属组件(12个待做)。B40=项目组讨论(XLSX+DOCX备忘录+SCOT再评估)。B19保留a-program-console，B15已redirect，B60待LLM。**6-27复盘结论：B类完成度最高，6核心专属(含B1-4)+4 bundle全绿。真缺口仅B40(需重建spec)+B60(待LLM)。✅P0已完成：32个B类docx批量注册word-template(B5约定书11+B2沟通函6+B1承接3+B18内审2+B40备忘录2+B60策略8)**
- **✅ B2/B13/B19/B51 bundle + B23/B30 附件Tab**(2026-06-24 完成)：4个简单bundle(b2/b13/b19/b51) + B23追加8附件Tab(穿行测试) + B30追加7附件Tab(集团附件)。B类48个子底稿全skip+主组件全有Tab内嵌。使用GtWpRenderer lazy渲染附件
- **🔴 D~N循环专属组件方案**(2026-06-24决定)：不做通用substantive-bundle——各循环业务差异大，通用组件不精美。每个D~N循环做独立专属组件(参照D0函证模式)。D1=应收票据（不是采购付款！又犯了凭编码猜内容的错）。必须先查源模板确认实际内容再建spec
- **✅ d1-notes-receivable**(2026-06-24 完成)：D1应收票据专属组件，76/76全绿（13 PBT fast-check + 88 vitest + 1 hypothesis）。useD1FormData(180行)+useD1NotesReceivable(1237行)+useD1Review(106行)+GtD1NotesReceivable(580行)。21 Sheet→18 Tab统一入口+审定表D1-1跨sheet公式联动(D1-2!B14等)+ECL坏账准备(迁徙率连乘/个别)+SPPI业务模式+背书贴现终止确认+贴息P×R×D/360+监盘倒推A+B-C+质押>50%警告+关联方自动匹配+附注披露(上市/国企)+调整分录↔审定表双向同步+trail_balance回写+B50/C2/A13四方EventBus
- **✅ d2-accounts-receivable**(2026-06-25 完成)：D2应收账款专属组件，76/76全绿（13 PBT + 89 vitest + 1 hypothesis）。useD2FormData(180行)+useD2AccountsReceivable(1123行)+useD2Review(106行)+GtD2AccountsReceivable(553行)。20 Sheet→17 Tab+SUMIF三分类(单项/账龄/客户类型)聚合D2-2+ECL双sheet(D2-9+D2-10)+D0函证联动+截止测试(determineCutoff)+保理终止确认(CAS23)+分析程序(周转天数>30%警告)+trail_balance回写(科目1122)+B50/C3/D0/A13五方EventBus
- **✅ A1 Dashboard 子Tab不显示问题已修复**(2026-06-25)：根因=`/wp-index` API原返回`wp_index.id`作为`id`字段，前端WorkpaperList用`i.id===w.wp_index_id`匹配（正确），但useA1SubWorkpapers需要`working_paper.id`来渲染子组件。修复：API新增`wp_id`字段(=working_paper.id)，`id`保持为wp_index.id（向后兼容）；useA1SubWorkpapers用`item.wp_id||item.id`。子Tab改为顶层el-tabs平级结构（"A1程序表|签发流转控制表|..."），GtWpRenderer对a1-dashboard跳过编制信息和toolbar（移入组件内部"main"tab-pane），chain_orchestrator也加了第8步为skip子底稿创建wp_index
- **✅ c-control-test-component**(2026-06-24 完成)：C类控制测试专属组件，25/25必做全绿。useCControlTestData(167行)+useCControlTest(770行)+GtCControlTest(872行)。14循环(C2~C15)共用，卡片式UI+偏差率自动计算(偏差÷有效样本)+三档结论建议+循环汇总+B23→C→B50→D~N闭环EventBus+证据Tab+复核签字
- **🔴 优先级转向A类底稿修复**(2026-06-24)：用户要求先修复A类底稿聚合。需做聚合升级的组：A11(期后事项,子底稿未skip)/A13(错报,子底稿未skip)/A16(管理层声明,7子表无统一入口)/A17(审计总结,11子表无统一入口)。D~N循环不需要（已有multi-sheet tab通用模式）。先做A17
- **✅ a17-audit-summary-bundle**(2026-06-24 完成)：A17审计总结聚合，17/17必做全绿。9 Tab+联动锁定+签发前置条件+KAM引用+仪表盘
- **✅ a16-representation-bundle**(2026-06-24 完成)：A16管理层声明书聚合，11/11必做全绿。95行极简bundle，7 word-template Tab
- **✅ A11/A13/A15 子底稿skip修复**(2026-06-24)：A11-1~3/A13-2~5/A15-1→skip
- **✅ A类全面聚合完成**(2026-06-24)：46个子底稿全部skip。A1(6)/A10(2)/A11(3)/A12(1)/A13(4)/A15(1)/A16(7)/A17(12)/A21~A25(10)。主组件均已内嵌子表渲染能力
- **🔴 A1/A10/A12/A21~A25 skip后主组件未内嵌问题**(2026-06-24)：A16/A17/A11/A13/A15 的主组件已有Tab内嵌子表能力(安全skip)。但 A1(dashboard)/A10(程序表)/A12(程序表)/A21~A25(review-checklist) 标skip后主组件不渲染子底稿→用户无法访问。需要为这些主组件添加内嵌Tab+联动逻辑。优先级：A1(签发链路)>A21~A25(复核)>A10/A12(简单)
- **✅ a1-dashboard-bundle-upgrade**(2026-06-24 完成)：A1 Dashboard子底稿内嵌，14/14必做全绿。useA1SubWorkpapers(196行)+GtA1Dashboard增量修改。8子底稿Tab(A1-11~A1-18)+依赖链A17→A1-11→A1-15+进度环集成+EventBus。6-25修正label对齐源模板+新增A1-17/A1-18。**6-27修复子底稿进度计算**：原硬编码not_started→改为基于checklist-responses填写率的三态(completed/in_progress/not_started)+workpaper:saved实时刷新
- **✅ a10-bundle + a12-bundle + review-bundle**(2026-06-24 完成)：A10(3 Tab,96行) + A12(2 Tab,76行) + GtReviewBundle(107行,A21~A25复用×5)。A类底稿聚合全面完成：9组46个子底稿全skip+主组件均有Tab内嵌
- D0 函证统一性治理（useConfirmationExcelIO 抽取 + defineExpose 统一 + 导入预览弹窗）
- **LLM 接入**：Phase3=POST /ai-generate 接 vLLM → Phase4=跨底稿上下文注入
- D2 聚合 12 空白 tab；A 循环 docx 弹窗（30 个待加 WpPopupDocxEditor）
- **✅ useEditorMode.spec.ts 断言已修复**：htmlRendererRegistry.spec.ts expected 列表已更新至 82 componentType（含 A17-1/A17-2-1/A5-1 + 9 个 A17/A18/A8/A11 专属组件）
- 外部依赖：LLM embedding / 合并 UAT / GitHub 默认分支改 main / MinerU+OCR
- **✅ A17-1签字表按钮弹窗确认模式(2026-06-28)**：签字表从手动input改为按钮弹窗确认（ElMessageBox.confirm显示操作/角色/当前用户/不可撤销警告→确认后自动填用户名+当天日期）。与A1-11签发流转表交互一致。useAuthStore取当前用户。4角色。61测试全绿
- **✅ A17-1各章编制提示+标题对齐源模板(2026-06-28)**：新增CHAPTER_GUIDANCE常量(16章×源模板蓝色字体提示)，每章卡片内折叠"📋编制提示"区(蓝色左边线+浅蓝背景pre-wrap)。DEFAULT_CHAPTERS标题同步对齐源模板完整名称。左侧导航标签同步更新
- **✅ A17-1 AI章节生成端点(2026-06-28)**：新增`POST /api/workpapers/{wp_id}/a171/ai-generate`(`a171_ai_generate.py`，注册到router_registry AI与辅助组)。按B14模式：加载project_context+知识库(用户指定doc_ids或ReferenceDocService自动检索)+CPA专属system prompt+编制提示注入→chat_completion(RAG context_documents)。前端点击🤖AI→弹el-dialog选知识库文档(checkbox-group)→确认后调端点→结果填textarea
- **✅ A17-1签字角色按business_category联动(2026-06-28)**：4角色基础(编制人/复核人/质控/EQCR)。A类=4全显/B类=跳过质控显3(编制+复核+EQCR)/C类=只显2(编制+复核)。前后端SIGNATURE_ROLES统一为4行
- **🟡 AI对话模式(2026-06-28用户要求)**：AI辅助缺少信息时应采用对话方式追问用户(而非报错)。需在章节AI区增加轻量chat对话流+LLM服务降级时友好提示而非红色错误。当前已做降级友好提示，对话流待下轮
- **架构优化**：①拆 event_handlers.py ②前端 Top-5 巨型 Vue 拆分 ③services/ 按域建子包
- **🟡 omp(can1357/oh-my-pi)借鉴点**(2026-06-28,待LLM Phase3+)：①Hashline内容锚定→底稿并发冲突field-level检测 ②Subagent隔离+schema-validated output→/ai-generate结构化返回 ③Hindsight项目记忆→v3.0跨年续审知识继承(retain/recall模式) ④Stream Rules实时拦截→QC规则在LLM生成阶段截断重试
- **✅ A15 财务指标自动取数**(2026-06-27)：`_going_concern.py` resolver从TB自动算流动比率/速动比率/资产负债率/净资产/累计未分配利润+三色风险等级。GtA15Bundle增加指标卡片。通用`GET /api/projects/{pid}/auto-data/{source}?year=`端点（可复用于任何resolver）
- **✅ A13 错报汇总自动聚合**(已确认完成)：`_misstatement_aggregation.py`+`a13_event_handler.py`+MisstatementSummaryView全链路完整（之前误判为未做）
- **✅ A类底稿P1全完成确认**(2026-06-27)：A13聚合/A15取数/A21~25 RBAC(REVIEW_ROLE_MAP+evaluate_guard)/A1-13~14分析性复核(analytical_review_service从financial_report取数)/A17-1 GtIndexChip(3关键位置)——全部已有实现
- **✅ A2借贷校验+AJE→A13联动**(已确认完成)：Adjustments.vue已有实时balanceDiff(红色差额+按钮禁用)+convertAjeToMisstatement一键转错报
- **✅ word-template占位符审计**(2026-06-27)：8个word-template底稿中4个有占位符(正常)，3个无占位符(A26-2/A8-2/S34-1-1低频)，1个缺模板。影响可忽略，不需要补充
- **✅ d4-operating-revenue(2026-06-30 全量完成)**：D4营业收入专属组件，25/25必做+20 optional PBT全绿（169测试：124 vitest + 45 pytest）。平台最大单科目底稿：8xlsx/42sheet/~280+公式。新componentType`d4-operating-revenue`+38个wp_code映射。16 composable(useD4FormulaEngine17纯函数+useD4FormData+useD4CrossSheet+useD4Adjudication/RevenueDetail/OtherRevenue/Adjustment+useD4PolicyCheck+useD4Analysis+useD4Inspection+useD4RelatedPrice+useD4Ipo+useD4OtherGroup+useD4ImportExport+useD4DualMode)+38个Vue子组件+GtD4OperatingRevenue主入口(defineAsyncComponent lazy)+后端3py(_d4_import_export 3端点+_d4_resolvers 3 resolver+_d4_ai_generate 8 section)+_d4_operating_revenue render策略+account_package_registry 41 sheet。嵌套Tab(一级7组→二级各sheet)+IPO条件可见+出口适用性+D4-2↔D4-1行同步+附注成本跨循环+统一目录42行进度条+双模式OO
- **🔵 d3-prepaid-accounts(2026-06-29 三件套齐全,复盘优化)**：D3预收账款专属组件。源模板10 sheet,294公式,科目2203贷方。25需求+20P+33任务。后端4py(_d3_import_export/_d3_resolvers/_d3_ai_generate/render策略)。核心：D3-2→D3-1双维度聚合+D3-2↔D3-7期后结转联动(R23)+D3↔D7合同负债CAS14区分(R24)+RENDERER_DISPATCH+resolver注册(R25)。5方EventBus+GtIndexChip 7处(含D7)+AI 9section+复核对话+TB三级取数+导入导出三级+双模式
- **✅ d5-receivables-financing(2026-06-30 全量完成)**：D5应收款项融资专属组件，24/24必做+11 optional PBT全绿（43测试：41 vitest + 2 hypothesis）。新componentType`d5-receivables-financing`+5个wp_code映射(D5/D5-1~D5-4)。8 composable(useD5FormulaEngine14纯函数+useD5FormData+useD5CrossSheet+useD5Adjudication+useD5Detail+useD5FairValue+useD5Adjustment+useD5Disclosure)+6个Vue子组件+GtD5ReceivablesFinancing主入口(defineAsyncComponent lazy)+后端3py(_d5_import_export 4端点+_d5_resolvers 1 resolver+_d5_ai_generate 5 section)+_d5_receivables_financing render策略+account_package_registry 7 sheet。核心：贴现公式(票面×利率×天数/360)+审定表OCI特殊减项(FV合计=小计-OCI变动)+D5-2→D5-1按类别聚合+D5-4→D5-1 OCI变动+D1/D2出售模式导入+tb_aux_balance科目1124导入+TB回写+双模式+附注上市/国企双版本+减值准备变动动态行
- **✅ d6-contract-assets(2026-06-30 全量完成)**：D6合同资产专属组件，33/33必做+20 optional PBT全绿（42测试：39 vitest + 5 hypothesis）。新componentType`d6-contract-assets`+10个wp_code映射(D6/D6-1~D6-9)。11 composable(useD6FormulaEngine16纯函数+useD6FormData+useD6CrossSheet+useD6Adjudication三区块+useD6Detail30列+useD6ImpairmentDetail双分类+useD6Adjustment借贷平衡+useD6RelatedParty+useD6EclCalculation双组合+useD6Inspection双区块+useD6Disclosure5子节)+11个Vue子组件+GtD6ContractAssets主入口(defineAsyncComponent lazy sheetName v-if分发)+后端4py(_d6_import_export 4端点+_d6_resolvers 2 resolver+_d6_ai_generate 16 section+_d6_contract_assets render策略)+account_package_registry 12 sheet。核心：三区块审定净值=原值-坏账跨区块联动+ECL双组合(单项+账龄组合×多组合)+30列最宽明细表+163公式附注5子节+段落式政策D6-7+D6-2↔D6-6期后结转联动+ECL→D6-3→D6-1联动链+TB回写1402+双模式+导入导出三级
- **🔵 D7合同负债三件套齐全(2026-06-30)**：D7合同负债(25需求+17P+31任务,9sheet/314公式,科目2205贷方,双区块审定+分析Top10+D3↔D7 CAS14联动)
- **✅ d2-accounts-receivable-refactor**(2026-06-30 必做任务全绿,104测试通过)：D2应收账款精细化组件拆分完成。useD2AccountsReceivable.ts(1123行)→18个独立composable+15个Vue子组件+1后端端点(35新文件)。useD2FormulaEngine(12纯函数)+useD2Adjudication(SUMIF三分类聚合)+useD2Detail(39列宽表)+useD2BadDebt(三分类动态行)+useD2Adjustment(借贷平衡)+useD2Analysis(周转率警告)+useD2Ecl(单项ECL+迁徙率连乘)+useD2RelatedParty+useD2VoucherCheck+useD2PolicyCheck(段落6项)+useD2WriteoffCheck(双段)+useD2PledgeCheck(CAS23)+useD2BizModel(决策树)+useD2Cutoff(determineCutoff)+useD2Disclosure(4版本切换)+useD2Procedure(7步骤EventBus)+useD2ImportExport(8sheet导入导出)+useD2DualMode(OO健康检查)。后端_d2_import_export.py(openpyxl 3端点)。联动加强：①D0函证→D2-2自动标Y ②从余额表导入(merge模式) ③D2-5→A1-13推送 ④复核对话inject ⑤GtIndexChip 7处
- **✅ F2-22/F2-23监盘计划+小结render schema**(2026-06-27)：源模板仅标题行(xlsx空白模板设计)→新增render schema预设结构(F2-22=18行4分区/F2-23=21行6分区)，用户打开即有框架可填。**经验：源模板为空的audit-sheet底稿，统一通过render schema提供预设行结构解决"空白页"问题**
- **🟡 存货监盘模块改进规划**(2026-06-27)：F2-21A~F2-26共6 sheet全是独立audit-sheet无统一入口。P1建议：①f2-stocktake-bundle统一入口(6Tab) ②F2-22/F2-23改word-template(叙述性文档不适合表格行) ③F2-25→F2-26差异自动联动。P2：监盘照片管理+GPS标注+OCR盘点表+差异率预警→A13。**P1①已完成**：GtF2StocktakeBundle(7Tab,程序表+6子底稿OO在线编辑)+overrides改skip+htmlRendererRegistry注册+VALID_COMPONENT_TYPES注册
- **🔵 voucher-sampling-engine(2026-06-29 三件套齐全,P0)**：通用抽凭引擎组件。5种抽样算法(random/stratified/specific_item/systematic/MUS)+预审/年审阶段隔离(phase字段+年审append-only不覆盖预审)+版本链(workpaper_extraction_log复用+compare diff)+CAS1314合规检查(覆盖率<60%警告)+edit_trail行级留痕+随机种子可复现。14需求+12P+19任务。复用LedgerSamplingService+V095表(extraction_type='voucher_sampling')无新迁移。适用D2-7/D4-14/D4-15/E2-7。GtVoucherSamplingEngine.vue+5个子组件+3个composable+后端voucher_sampling_algorithms.py(5种算法纯函数)
- **🔵 cutoff-test-auto-sampling(2026-06-29 三件套齐全,P0)**：通用截止测试自动提取组件。GtCutoffAutoSampling.vue+useCutoffAutoSampling.ts+cutoffJudgment.ts(3模式:post/pre/window)+LedgerSamplingService(共享后端)+CutoffPreviewDialog+CutoffHistoryDrawer。11需求+10P+18任务。V095 workpaper_extraction_log。props配置化适配D2/D4/F2/E2。填充append/replace/merge+撤销before_data
- **🔵 workpaper-version-trail(2026-06-29 三件套齐全,P1)**：底稿field-level版本链通用组件。VersionTrailService(create/list/detail/diff/rollback/lifecycle)+GtWpVersionTrail.vue(el-drawer时间线)+VersionDiffPanel.vue+useVersionTrail.ts。12需求+8P+19任务。V096 workpaper_snapshots表(JSONB快照+50上限+2MB降级+manual永不清理)。触发：手动/auto_sampling/auto_import/review_sign/status_change/rollback 6种类型。Diff=item_id集合比较+字段值对比(added/deleted/modified/unchanged)。回滚=事务(读快照→删responses→插入快照行→创建rollback版本)。权限：回滚仅现场经理+，不可删除快照
- **🟡 voucher-attachment-intelligence(2026-06-29规划,P2)**：凭证附件智能化处理链。三层：①凭证-附件1:N锁死绑定(workpaper_attachments表,voucher_no关联,双入口:抽凭表页面+附件模块项目/科目/底稿路径)②OCR(8200)+LLM(vLLM 8100)分析流水线(异步任务5-15s,识别单据类型+提取关键字段→结构化JSON)③分析结果→底稿字段回填(审计说明/核查结论/备注/检查表列)+生成analysis_result衍生文档。依赖voucher-sampling-engine先完成(凭证行数据结构需稳定)。适用：抽凭表+检查表(D2-7/D4-14等)

## 踩坑铁律（高频）

### 后端
- **🔴 大文件导入期间禁改后端代码**→ uvicorn reload 杀 worker
- **🔴 event_bus publish 只传 EventPayload**；轻量通知用 broadcast_raw
- **🔴 测试掩盖 bug**：mock 不存在方法 = 把 bug 编进测试
- **🔴 余额表 KEY_COLUMNS 勿加 account_name**；SELECT tb_balance 必含 direction
- **🔴 PG ON CONFLICT DO NOTHING 不返回跳过行**：需二次查询得 skipped
- **🔴 project_assignments列名是staff_id不是user_id(2026-06-29)**：`_a177_independence_declaration.py`的`_load_team_members`原用`pa.user_id`查询报`UndefinedColumnError`，正确列名`pa.staff_id`。且此错误会abort事务导致后续查询级联失败(InFailedSQLTransactionError)
- **🔴 asyncpg不支持IN tuple参数(2026-06-28)**：`sa.text("...IN :codes")` + `{"codes": tuple(...)}` asyncpg报语法错误。必须用`= ANY(:codes)` + `list(...)`。错误会abort事务导致后续所有查询级联失败
- **router_registry 必查**；**service 只 flush 不 commit**
- **🔴 GtA17Bundle独立性Tab引用旧组件(2026-06-29修复)**：原`IndependenceSigning.vue`(旧签署进度组件)改为`GtA177IndependenceDeclaration.vue`(新5章节专属组件)。bundle的`kind:'independence'`分支需同步更新import+template引用
- **🔴 fsWrite对编辑器打开的文件可能不落盘(2026-06-29踩坑)**：Kiro的fsWrite/fsAppend在文件被编辑器占用时可能写入内存缓冲但不刷盘，导致Vite读到旧文件。解决：先`Remove-Item -Force`确认删除，再用`node -e "fs.writeFileSync(...)"`直接写磁盘
- **🔴 Bundle wpIdMap必须用item.wp_id不能用item.id(2026-06-28)**：`getWpIndex`返回的`id`是wp_index表id，`wp_id`才是working_paper表id。Bundle传给子组件的wpId必须用`item.wp_id`，否则checklist_responses的FK约束(wp_id→working_paper.id)报ForeignKeyViolationError。A17Bundle已修复
- **🔴 新增 componentType 必须同步更新 `VALID_COMPONENT_TYPES`**（`wp_classification_service.py`），否则 `validate_overrides` 启动时 raise ValueError 阻止 uvicorn 启动
- **🔴 报告正文生成空白根因**：`audit_report_template`表空(未seed)→`load_body_template`返回空sections→docx只有【草稿DRAFT】水印。修复`POST /api/audit-report/templates/load-seed`(种子`backend/data/audit_report_templates_seed.json`,28段落=4意见类型×2公司类型)。**重建DB后会复现，初始化需含此seed**
- **🔴 删除主表前必清FK子表**：`delete_task`需先删`export_job_items_v2`+`deliverable_section_state`再删`word_export_task_versions`+`word_export_task`，否则FK约束500
- **🔴 结构化章节数据不能存到textarea content(2026-06-28踩坑)**：A17-1第3章把JSON结构化数据存入chapters['3'].content导致乱码——hydrate时JSON字符串被当textarea文本显示。正确做法：结构化章节的各字段用独立item_id前缀(如`a171-ch3-mod-*`/`a171-ch3-mat-*`)分别存checklist_responses，不经过content字段。已git恢复，待重做
- **✅ A17-1双向互转实现(2026-06-28)**：结构化视图↔OnlyOffice Word编辑。checklist_responses为主存储，切OO时POST generate-docx(python-docx填充模板)→OO编辑，切回时POST sync-from-docx(解析docx 16章Title段落边界回写DB)。`a171_docx_sync.py`~150行。只同步textarea章节(1-5,7,13-16)，table/yn不走docx。项目级文件存`storage/projects/{pid}/workpapers/A/A17-1.docx`
- **🔴 D~N专属组件不能有内部el-tabs(2026-06-30)**：GtWpRenderer外层已有sheet目录行(el-tabs card chips)，专属组件(D4/D5等)接收`sheetName` prop用v-if分发到子组件，不再自己搞嵌套Tab(否则双层Tab)。sheetName是完整中文名(如"营业收入审定表D4-1")，需regex提取末尾编码(D4-1)匹配。附注sheet用includes('上市'/'国企')特殊匹配。D3待后续统一
- **🔴 account_package_registry sheets顺序=目录行顺序(2026-06-30)**：`_get_render_config_impl`中当pkg_sheets非None(来自registry)时跳过xlsx排序(`not pkg_sheets`条件)，直接使用registry声明的数组顺序。否则registry中文名与模板xlsx sheet tab名不匹配导致排到999乱序
- **🔴 pkg_sheets模式下无编码sheet统一用wp_code override(2026-06-30)**：render-config dispatch循环中，当`pkg_sheets`非None且`_sheet_ovr`为None时：①合成底稿目录(class_code前缀"B-")走`derive_component_type`→`b-index`(保留原生架构树GtBIndex) ②其他sheet(附注/明细等)直接用`ovr`(wp_code级override如`d4-operating-revenue`)。D4A等有sheet级override的走`_sheet_ovr`分支不受影响
- **🔴 D~N循环全sheet HTML组件化策略(2026-06-29最终确认)**：所有D1 sheet（含31列宽表D1-7/D1-8）都做HTML精美组件，OnlyOffice仅为降级/偏好切换。核心逻辑：固定骨架上填数据，区别只是骨架复杂度。宽表用el-table横向滚动+列语义化(日期选择器/金额格式化/关联方匹配)。变动行=el-table动态添加行。导入导出三级(导出空模板→离线填写→导入解析识别动态行)解决批量数据场景。跨sheet公式=从TB/明细表取数(resolver)，前端composable公式引擎重算
- **🟡 D1专属组件拆分计划(2026-06-29)**：useD1NotesReceivable.ts(1237行)太大，按Tab拆成独立子composable+子Vue组件，每文件200-400行。基于源模板实际sheet内容逐个补全占位Tab。分6个spec+1通用组件推进：①d1-adjudication-table(审定+明细+坏账,三件套齐全) ②d1-disclosure-note(附注上市+国企,三件套齐全,20需求) ③d1-endorsement-discount(业务模式+备查簿+贴现背书+贴息,三件套齐全,18需求) ④d1-inspection-check(三件套齐全,18需求8P: D1-10监盘15列宽表+D1-11关联方13列+D1-12质押16列+D1-13凭证抽样) ⑤d1-ecl-provision(三件套齐全,16需求8P: D1-14段落式政策检查左右分栏+D1-15八列测算表D=B×C/F=E-D) ⑥d1-writeoff-check(三件套齐全,12需求6P: D1-16坏账转回8列+核销5列双段表) ⑦audit-review-dialog(通用复核对话,三件套齐全,13需求)
- **🟡 D1联动优化待办(2026-06-29复盘)**：P0:D1-12从D1-7"已质押"行导入(类似D1-8从D1-7导入贴现行)+D1-15 E列从D1-4自动取数(跨sheet auto_pull)。P1:D1-11从related_parties表导入关联方清单+D1-16差异不一致时"同步到D1-4"按钮+D1-10核对区增倒推调节子区域(当监盘日≠报表日)。P2:差异超标自动创建复核线程+跨spec复核链路(D1-15差异→A13错报通知)。**架构P0**：抽取d1SharedFormulas.ts(纯函数)/useD1ImportExport.ts(导入导出通用)/useD1DualMode.ts(双模式)/D1AuditNoteSection.vue(审计说明通用组件)
- **🔴 D1 spec间数据契约(2026-06-29)**：Spec1(审定表)写入`D1-adj-{section}-{type}-{period}-audited`格式item_id，Spec2(附注)通过computed从同一allResponses Map读取这些key。8个跨spec item_id构成契约接口。行类型三分：fixed(不可删)/dynamic(浮动可增删)/summary(自动合计不可编辑)。提示文字用`<details>`折叠(蓝左边线+浅蓝背景默认收起)。GtIndexChip跳转审定表/坏账/附注模块
- **🔴 披露表"说明"vs"提示"双层设计(2026-06-29)**："说明："=可编辑textarea(对上方表格数据补充说明，双向回写到附注模块，EventBus `disclosure:note-text-updated`/`note:section-updated`双向同步，last-write-wins冲突策略)。"【提示：】"=只读折叠区(编制指导告诉用户何时/如何填写，`<details>`默认收起)。两者在UI上通过样式区分，不可混淆
- **🔴 底稿"说明"文本区三种模式(2026-06-29通用规范)**：①纯文本说明(textarea直接编辑+双向回写附注) ②适用性判断+预填(先radio选场景如终止/未终止/均有→预填模板文本→可编辑→双向回写) ③动态行提示(浅灰占位行"可无限量添加行"→点击addRow，不持久化纯UI)。持久化：①item_id含note前缀remark存文本 ②item_id含judgment前缀conclusion存判断值remark存编辑后文本 ③不存储
- **🟡 audit-review-dialog(2026-06-29,三件套齐全)**：通用审计复核对话组件`GtReviewDialog.vue`(~400行)+`useReviewDialog.ts`(~300行)+`useReviewDialogProvider.ts`(~80行全局注入)。**全局可激活**：不限于审计说明/结论，底稿任意位置可右键"发起复核对话"(sectionId=任意字符串如`D1-adj-bank-current`)。三种激活方式：固定按钮/右键菜单(@cell-contextmenu)/选中文本工具栏。上下文摘要卡片(数据快照)+消息引用(quote类型)。活跃线程蓝/红圆点标记。后端V095_review_threads+review_messages。13需求+14 properties+39任务
- **🟡 双模式双向回写联动规划(2026-06-28)**：以A17-1为契机推广到全平台。Phase1=A17-1验证(已完成) Phase2=通用DocxSyncService配置化覆盖25个word-template Phase3=Excel双向(OO xlsx callback→openpyxl解析→parsed_data / Univer保存→回写xlsx)。设计原则：明确主存储+切换时同步不实时双写+降级容错
- **🔴 导入导出composable必须用http(axios)不能用原生fetch(2026-06-30)**：`useD4ImportExport`原用`fetch`发POST请求不带Authorization header→后端401"Not authenticated"。必须用项目`@/utils/http`(axios实例，拦截器自动加Bearer token)。blob下载：`http.post(url, null, {params, responseType:'blob'})`→`new Blob([response.data])`。文件上传：`http.post(url, formData, {params, headers:{'Content-Type':'multipart/form-data'}})`
- **🔴 StreamingResponse中文文件名必须RFC5987编码(2026-06-30)**：`Content-Disposition: attachment; filename="D4-2_模板.xlsx"`中含中文字符→UnicodeEncodeError('latin-1')。修复：`from urllib.parse import quote; headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}`。D3/D4/D5全部导出端点已统一修复
- **🔴 导出模板表头必须与前端页面一致(2026-06-30)**：导出xlsx含自动计算列(灰底不可编辑列如合计/审定/变动率)，导入时忽略这些列只读取可编辑列。用户体验：导出→离线填写→导入，模板格式与在线页面完全一致
- **🔴 GtOnlyOfficeSheet健康检查响应解析(2026-06-28修复)**：`http.get`返回AxiosResponse，`health.data`是ResponseWrapperMiddleware信封`{code,message,data:{healthy:true}}`，直接`.data?.healthy`拿到undefined→永远降级。修复：`health.data?.data?.healthy ?? health.data?.healthy`双层兼容
- **地址坐标库 single-flight + 增量失效**；**WorkpaperSaveOrchestrator 统一 after_save**

### 前端
- **🔴 底稿编码→实际内容必须查源模板**：不能凭编码猜内容（B40≠抽样策略，实际是项目组讨论CAS1211）；**开发前必先逐sheet读源模板**
- **🔴 account_package_registry sheets数组顺序=tab顺序**：必须严格对齐源模板xlsx的sheet顺序（含D0函证插入位置），`resolve_package_sheets`按数组序返回classifications。sheet_name也必须与模板实际名完全一致
- **🔴 大章节底稿聚合模式**：A17/A16/B30 等大章节底稿需做"统一入口组件+子表作为tab"模式（参考函证D0/B22A），子底稿映射skip由主组件内tab切换渲染
- **🔴 A1 Dashboard子Tab组件必须自加载**：GtA1Dashboard只传wpId不传htmlData，子组件（GtAnalyticalReview/GtChecklistTable等）需在htmlData未提供时自行调render-config获取数据。render-config已支持`?force_component_type=`查询参数强制指定渲染策略（解决skip映射底稿在Dashboard内嵌时无法触发正确renderer的问题）
- **🔴 子底稿wp_code_overrides必须保持skip**：A1-11~A1-17在overrides中必须是`skip`（否则在底稿列表中平铺显示），Dashboard内嵌时通过`force_component_type`指定真实componentType。改为非skip会导致列表中子底稿暴露
- **✅ 底稿列表子表折叠+目录化(2026-06-28)**：WorkpaperWorkbenchView增加buildTree父子折叠(最长前缀+'-'自动识别)，子行去掉GtRowActions(纯目录条目)，点击子行→router.push到父底稿编辑器+?sheet=childCode定位Tab。父行点击→直接打开编辑器(onWorkbenchRowClick)，折叠箭头单独@click.stop控制展开收起
- **🔴 WorkpaperEditor locate-cell误触发修复(2026-06-28)**：`?sheet=`单独存在时不再触发`workpaper:locate-cell`事件（原逻辑`if(querySheet||queryCell)`改为`if(queryCell)`）。单独sheet是Tab切换信号由bundle组件watcher处理，非Excel单元格定位。否则bundle底稿打开时弹"未找到对应科目位置"误报
- **🔴 Bundle子Tab组件必须守卫wpId为空(2026-06-28)**：A17Bundle/A1Dashboard等bundle内嵌子底稿组件时，若`getTabWpId(tab)`返回空串（子底稿未生成），必须`v-if`守卫不渲染组件，否则组件selfLoad请求404触发http.ts全局拦截器弹"Not Found(ID:xxx)"。修复：空wpId时显示"该子底稿尚未生成"占位提示
- **🔴 GtAProgramConsole需selfLoad(2026-06-28)**：原组件无selfLoad，完全依赖父组件(GtWpRenderer)传htmlData。bundle内嵌场景(A17Bundle等)不传htmlData→程序表为空。修复：onMounted增加selfLoad，当htmlData.programs为空时调render-config?force_component_type=a-program-console获取后端生成的程序数据
- **🔴 render-config返回结构是`{sheets:[{html_data:{...}}]}`**：自加载组件从`res.sheets[0].html_data`取渲染器输出，非顶层`res.template`。A1-15已踩坑修复（空白页根因）
- **GtOnlyOfficeSheet 内置全屏**：改用浏览器原生`requestFullscreen()` API（CSS position:fixed在有transform的父容器中失效），`fullscreenchange`事件同步状态，ESC/按钮均可退出
- **🔴 contenteditable v-model** 必加 isInternalChange/focus guard
- **🔴 附注按 sort_order 排序**，禁中文字符串排序
- **多 sheet 底稿**：各 sheet 按 class_code 独立派生
- **GtWpToolbar 委托模式**：activeComponentRef 转发 defineExpose 方法
- **confirmation _format 统一规则**：有 `_format`→可编辑；无→空态；有 cells 无 _format→旧格式只读
- **聚合程序表**：用 sheet 级编码(D2A)查模板，非父码(D2)
- **wp_code_overrides 支持 sheet_name key**：按完整 sheet_name 映射 `skip` 可隐藏多 sheet 底稿的辅助 sheet；`component_type=="skip"` 的 sheet 不渲染为 tab
- **🔴 API调用可能触发全局404弹窗**：http.ts拦截器默认对404弹ElMessage。组件内预期可能404的请求必须加`{_silent:true} as any`配置项避免全局弹错（如useA1SubWorkpapers.refreshDependencyStatus）。**useA17BundleState的loadResponses/loadKamReferences也已修复(2026-06-28)**
- **🔴 http.ts 5xx重试弹窗去重**：重试提示用全局单例(`_retryInflight`计数+共用一个toast)，多并发请求只显一个、全完成自动关。禁止每请求各弹`duration:0`永不消失的toast（会疯狂堆叠）
- **🔴 Docker端口转发故障诊断**：宿主机连PG/Redis报`connection was closed in the middle`/`connection_lost()`（非`Connect call failed`）= Docker端口转发层坏。`docker exec psql`能连但宿主机asyncpg连不上→`docker restart audit-postgres audit-redis`刷新转发。后端reload模式会自动重连。另：宿主机后端进程在DB起来前启动会卡死503(postgres/redis unavailable)，需杀进程(含multiprocessing-fork孤儿子进程)重启。**OnlyOffice 8080端口同样会坏**：容器healthy但宿主机`curl localhost:8080/healthcheck`返000、容器内部200→后端health_check失败→前端降级→xlsx预览显示"格式不支持"。修复`docker restart audit-onlyoffice`
- **🔴 交付件预览previewType支持xlsx**：DeliverablePreview/OnlyOfficeEditor/DeliverableCenter的previewType联合类型已含`'xlsx'`（用`@vue-office/excel`，已装），后端`/preview-url`端点suffix白名单含`.xlsx`。OnlyOffice降级时xlsx也能只读预览（纵深防御）。报告正文生成对话框(AuditReportEditor+DeliverableCenter)顶部加了意见类型选择警告提示+required
- **✅ 交付件报告正文走真实Word模板(2026-06-28)**：DeliverableCenter"生成报告"原调legacy `renderReportBody`(/report-body/render,docxtpl极简自动模板39KB)→改为两阶段`previewReportBody→OPT弹窗→confirmReportBody`(TemplateFillService真实模板155KB,与AuditReportEditor同路径)。弹窗用`OptionalSectionDialog`(props:optional-sections/missing-fields/template-version/company-subtype-resolved/confirm-loading,emit confirm)。Playwright实测v3生成=152KB真实模板✓
- **✅ OnlyOffice"10人编辑"误报修复(2026-06-28)**：`onlyoffice_session_limiter.py`原用独立计数器`onlyoffice:session_count`(无TTL)与session key(有TTL)脱节,OO持续降级致release从不触发,计数虚高到10。重写为SCAN统计去重user_id数作席位(自愈),删独立计数器。`deliverable.py`的`onlyoffice_config`端点只在edit mode(`oos._editor_mode(status)=="edit"`)才acquire_session,只读预览不占席位。同一用户多文档/版本只占1席
- **✅ 版本链下载用认证下载(2026-06-28)**：`DeliverableVersionList.vue`原用`el-button :href target=_blank`不带Bearer token→改为`downloadFile`(axios blob)。`get_version_chain`排序加`version_no.desc()`次级排序(created_at同秒时确定性)
- **🔴 naive UTC时间戳前端少8小时(2026-06-28)**：后端`func.now()`/`datetime.utcnow`存的是naive UTC(无时区标记如`2026-06-28T04:06:49`)，前端`new Date()`按本地时间解析→中国少8小时。修复：补`Z`标记`/[zZ]|[+-]\d{2}:?\d{2}$/.test(v)?v:v+'Z'`再交`displayPrefs.fmtDateTime`转本地。已修DeliverableVersionList+DeliverableGroupList导出时间。**其他显示后端时间戳的组件同理需补Z**
- **🔴 新专属组件必须有selfLoad逻辑**：当htmlData prop为null(bundle内嵌场景)，组件onMounted必须自行调`render-config?force_component_type=xxx`加载数据。否则bundle内Tab显示空白。A17-1/A17-2-1/A1-12(2026-06-28)已踩坑修复。**A1-12根因**：GtA112DualChecklist的loadRenderConfig漏带`?force_component_type=a1-12-dual-checklist`，A1-12映射skip→默认render走通用策略不返回checklistData→结构化视图空白(只剩签字区骨架)。后端_a112_dual解析器本身正常(2分类14项4签字)
- **🔴 新专属组件的bundle集成三件事**：①wp_code_overrides保持`skip`(子底稿不在列表暴露) ②父bundle的Tab kind+组件引用切换到新组件 ③composable函数签名调用别传错(对象vs直接ref)
- **🔴 WorkpaperWordEditor健康检查+OO加载已修复(2026-06-26)**：①健康检查原错误调`/api/deliverables/onlyoffice/health`(不存在)→改为`/api/workpapers/onlyoffice/health`(返回`{healthy:bool}`) ②`initGenericEditor`原调不存在的`/onlyoffice-config?version=`端点→改为与GtOnlyOfficeSheet相同的`/sheets/{sheetName}/onlyoffice-config`+project_id参数 ③直接透传后端返回的完整config给DocEditor（不再前端自己拼）

### OnlyOffice（4 层坑）
1. JWT：开发环境 `JWT_ENABLED=false`
2. URL：`ONLYOFFICE_CALLBACK_BASE=http://host.docker.internal:9980`
3. Middleware：callback 返回裸 `{"error":0}`
4. 缓存：改 URL 后需 `docker restart` 清 session
5. **内嵌编辑统一用 `GtOnlyOfficeSheet`**：健康端点=`/api/workpapers/onlyoffice/health`(字段`healthy`)，配置=`/api/workpapers/{wpId}/sheets/{sheetName}/onlyoffice-config`。禁止自己手写 DocsAPI 集成——A1-12 已踩坑（错误健康端点+自定义嵌入→"Word编辑不可用"）
6. **🔴 fileType 动态检测已修复**：`get_sheet_onlyoffice_config`原硬编码`fileType:"xlsx"`+`documentType:"cell"`，docx文件被当xlsx打开报"扩展名不匹配"。现从`file_path`后缀推断(docx→word/pptx→slide/其余→cell)，actionLink仅对cell类型注入。`_resolve_wp_file`也改为保留模板原始后缀(不再硬编码.xlsx)，含旧文件自动重命名兼容。**修复后需 `docker restart audit-onlyoffice` 清缓存+删旧存储文件**

### 函证模块
- 10 组件统一模式：types→composable→UI→assembly→register；共享层 `coordination/`
- D0-8 跨循环复用（D0-8/E0-8/F0-8/K0-8 同 componentType）
- 状态机 12 态；枚举 11 类；分发按科目路由 D0-5(合同负债)/D0-6(应收)

## 关键引用

- spec 状态 → `.kiro/specs/INDEX.md`（181 archived / 0 active）
- 领域术语 → glossary.md（inclusion:always）
- **A类底稿打磨路线图** → `docs/A类底稿精细化打磨建议.md`
- 架构改进审查 → `docs/architecture-improvement-proposals.md`
- **全局体验与一致性建议** → `docs/平台全局体验与一致性建议.md`（5角色分层+收口/分层/贯通三主轴；§七codegraph实证）

## 全局治理实证（2026-06-23 codegraph 复核，80785节点）

- ✅ **写入收口已完成**：4 条写入路径(univer/html/onlyoffice/snapshot_writer)全收口 `WorkpaperSaveOrchestrator.after_save`；孤立 EventBus 已删(metrics.py留注释)。`single-source-cleanup`+`workpaper-save-orchestrator` 成果
- ✅ **死代码已删**：`stale_incremental_propagation.py` 已删除+分层文档 `backend/docs/STALE-PROPAGATION-LAYERS.md` 已产出（`stale-propagation-cleanup-doc` spec 5/5 done）
- ✅ **循环色板已统一**：`constants/cyclePalette.ts`+`--gt-cycle-*`+守卫脚本，4 处收口+测试全绿（`cycle-palette-single-source` 9/10 done，剩 Playwright 回归）
- ✅ **金额格式化统一出口已建**：`displayPrefs.fmt/fmtAmount/fmtPercent/fmtDateTime` 33 测试全绿+CI 守卫(71存量豁免)；`utils/formatAmount.ts`+`formatters.ts` 标 deprecated 转发（`display-format-single-source` 7/12 done，剩阶段三存量迁移3批+全量回归）
- 📊 **巨型文件实测**：event_handlers.py=1719行(后端最大god)、LedgerPenetration.vue=3706行(前端最大)；stale_propagation_engine.py=336行(健康，stale唯一对外入口=`StalePropagationEngine.on_change`)
- 📊 **循环色板4处分裂实测**：同一D循环 WorkbenchView=#E8590C橙/panorama=#1976D2蓝/DependencyGraph=#52b788绿/ganttUtils=#409EFF蓝
