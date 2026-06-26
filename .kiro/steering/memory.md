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
- 功能收敛；git 单 commit；**push 前必先 fetch**；**协作走 PR 不直推 main**
- 目标并发 6000 人；底稿编码致同 2025 修订版
- 5 角色轮转：审计助理/现场经理/业务合伙人/质量控制复核合伙人/EQCR技术复核人
- **v3.0 愿景方向**：项目级知识自动提取+跨年度续审继承（当前不做）

## 底稿开发铁律

- **风险导向审计**：B50风险→D~N程序表→A13评价错报，全链可追溯
- **componentType 选型**：结构化=d-form-table / 复杂Excel=OnlyOffice / 文档=word-template / 程序表=a-program-console / 函证=confirmation-*（9类）
- **三表HTML渲染**：底稿目录+审定表+附注全走HTML，仅复杂公式/DCF/图表留OnlyOffice
- **联动是核心价值**：ref_index chip+auto_data_source实时取数；孤立底稿=无价值
- **通用schema复用**：`{wp_code}-generic.yaml` + pattern matching
- **开发前必先逐sheet读源模板**；**导入导出三级**；**适用性自动判断**

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

### 🟢 里程碑（181 archived / 5 active）
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
- **✅ a1-15-disclosure-checklist**(2026-06-25 完成)：A1-15企业会计准则财务报表列报及披露核对表专属组件，10/10任务全绿（41 PBT fast-check + 17 hypothesis + 32 vitest + 5后端集成 + 16注册契约 + 5 Playwright E2E = 111测试）。新componentType `a1-15-disclosure-checklist`，useA115Checklist+useA115Navigation 2 composables+GtA115DisclosureChecklist.vue。35章节卡片UI+左侧导航+section-based lazy rendering(IntersectionObserver±1)+Y/N/NA色彩编码+CAS_Ref索引号+Cross_Reference_Map(11映射)科目跳转联动(GtIndexChip)+TOC适用性级联NA+debounce 2s自动保存+双模式(el-segmented)+OnlyOffice健康检查禁用。后端复用`_parse_a1_15`+`format_a115_to_summary` round-trip
- **🔴 公式管理可编辑(待 spec)**：D0-1「fx 公式」弹窗只读→需可编辑
- **✅ b50-risk-assessment**(2026-06-23 完成)：B50风险评估矩阵专属组件，35/35任务全绿（12 PBT + 19 vitest + 1 hypothesis）。3 composables + 750行 Vue 组件 + CAS强制 + EventBus联动
- **✅ b22a-control-matrix**(2026-06-23 完成)：B22A内控五要素矩阵专属组件，38/38任务全绿（20 PBT fast-check + 27 vitest + 1 hypothesis）。3 composables + 6-tab + IT子区6面板 + Element_Score自动计算 + 续审继承 + 3 EventBus事件
- **✅ b22b-deficiency-evaluation**(2026-06-23 完成)：B22B内控缺陷评价表，42/42任务全绿（16 PBT fast-check + 40 vitest + 1 hypothesis）。3 composables + 900行 Vue + 严重程度建议算法 + B15重要性对比 + B22A→B22B→B50 EventBus三方闭环
- **✅ b23-process-control**(2026-06-23 完成)：B23业务流程与控制了解表，59/59任务全绿（12 PBT fast-check + 66 vitest + 1 hypothesis）。3 composables + 8流程卡片 + 穿行测试 + 状态仪表盘 + 导入导出三级 + 关联流程图SVG + B22A→B23→B50→D~N四方联动。PBT发现并修复elementScores浅拷贝bug
- **✅ b30-group-audit**(2026-06-24 完成)：B30集团审计范围确定底稿，25/25必做任务全绿（37 optional测试待执行）。3 composables(1134行主composable) + 969行 Vue + 集团结构树(el-tree拖拽5层) + 组成部分分类(15%阈值) + 重要性分配(0.75系数,clamp[15%,85%]) + 覆盖率热力图(加权1.0/0.5/0.25/0.0) + 组成部分审计师 + B15→B30→B50三方联动 + 导入导出三级
- **🟡 B60 LLM辅助策略文档**：待 LLM Phase3 接入后，用 vLLM 辅助生成总体审计策略文档（不需专属组件，需 resolver + /ai-generate 接口）
- **❌ b40-sampling-strategy 已删除**(2026-06-24)：B40 实际是"项目组讨论程序表"(CAS 1211)而非"审计抽样策略"，requirements 已删除需重新建 spec
- **🟡 B类全面专属组件升级计划**(2026-06-24确认)：用户要求所有B类底稿均升级为专属组件(12个待做)。B40=项目组讨论(XLSX+DOCX备忘录+SCOT再评估)。B19保留a-program-console，B15已redirect，B60待LLM
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
- **✅ a1-dashboard-bundle-upgrade**(2026-06-24 完成)：A1 Dashboard子底稿内嵌，14/14必做全绿。useA1SubWorkpapers(196行)+GtA1Dashboard增量修改。8子底稿Tab(A1-11~A1-18)+依赖链A17→A1-11→A1-15+进度环集成+EventBus。6-25修正label对齐源模板+新增A1-17/A1-18
- **✅ a10-bundle + a12-bundle + review-bundle**(2026-06-24 完成)：A10(3 Tab,96行) + A12(2 Tab,76行) + GtReviewBundle(107行,A21~A25复用×5)。A类底稿聚合全面完成：9组46个子底稿全skip+主组件均有Tab内嵌
- D0 函证统一性治理（useConfirmationExcelIO 抽取 + defineExpose 统一 + 导入预览弹窗）
- **LLM 接入**：Phase3=POST /ai-generate 接 vLLM → Phase4=跨底稿上下文注入
- D2 聚合 12 空白 tab；A 循环 docx 弹窗（30 个待加 WpPopupDocxEditor）
- **✅ useEditorMode.spec.ts 断言已修复**：htmlRendererRegistry.spec.ts expected 列表已更新至 52 componentType（含 b23-process-control）
- 外部依赖：LLM embedding / 合并 UAT / GitHub 默认分支改 main / MinerU+OCR
- **架构优化**：①拆 event_handlers.py ②前端 Top-5 巨型 Vue 拆分 ③services/ 按域建子包

## 踩坑铁律（高频）

### 后端
- **🔴 大文件导入期间禁改后端代码**→ uvicorn reload 杀 worker
- **🔴 event_bus publish 只传 EventPayload**；轻量通知用 broadcast_raw
- **🔴 测试掩盖 bug**：mock 不存在方法 = 把 bug 编进测试
- **🔴 余额表 KEY_COLUMNS 勿加 account_name**；SELECT tb_balance 必含 direction
- **🔴 PG ON CONFLICT DO NOTHING 不返回跳过行**：需二次查询得 skipped
- **router_registry 必查**；**service 只 flush 不 commit**
- **🔴 新增 componentType 必须同步更新 `VALID_COMPONENT_TYPES`**（`wp_classification_service.py`），否则 `validate_overrides` 启动时 raise ValueError 阻止 uvicorn 启动
- **地址坐标库 single-flight + 增量失效**；**WorkpaperSaveOrchestrator 统一 after_save**

### 前端
- **🔴 底稿编码→实际内容必须查源模板**：不能凭编码猜内容（B40≠抽样策略，实际是项目组讨论CAS1211）；**开发前必先逐sheet读源模板**
- **🔴 大章节底稿聚合模式**：A17/A16/B30 等大章节底稿需做"统一入口组件+子表作为tab"模式（参考函证D0/B22A），子底稿映射skip由主组件内tab切换渲染
- **🔴 A1 Dashboard子Tab组件必须自加载**：GtA1Dashboard只传wpId不传htmlData，子组件（GtAnalyticalReview/GtChecklistTable等）需在htmlData未提供时自行调render-config获取数据。render-config已支持`?force_component_type=`查询参数强制指定渲染策略（解决skip映射底稿在Dashboard内嵌时无法触发正确renderer的问题）
- **🔴 contenteditable v-model** 必加 isInternalChange/focus guard
- **🔴 附注按 sort_order 排序**，禁中文字符串排序
- **多 sheet 底稿**：各 sheet 按 class_code 独立派生
- **GtWpToolbar 委托模式**：activeComponentRef 转发 defineExpose 方法
- **confirmation _format 统一规则**：有 `_format`→可编辑；无→空态；有 cells 无 _format→旧格式只读
- **聚合程序表**：用 sheet 级编码(D2A)查模板，非父码(D2)
- **wp_code_overrides 支持 sheet_name key**：按完整 sheet_name 映射 `skip` 可隐藏多 sheet 底稿的辅助 sheet；`component_type=="skip"` 的 sheet 不渲染为 tab
- **🔴 API调用可能触发全局404弹窗**：http.ts拦截器默认对404弹ElMessage。组件内预期可能404的请求必须加`{_silent:true} as any`配置项避免全局弹错（如useA1SubWorkpapers.refreshDependencyStatus）

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
