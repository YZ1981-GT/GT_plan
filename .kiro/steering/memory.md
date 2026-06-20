---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤ 200 行**。完成事项明细 → `#dev-history`；技术决策 → `#architecture`；规范铁律 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller 不要 .bat）
- **输出分步但连续做完**；**任务标记不能假绿**；**彻底解决不绕开**
- **🔴 codegraph 优先于 grep（铁律）**：搜符号/查调用链/看影响面第一选择永远是 codegraph（77k 节点/157k 边）；**grep 仅用于**非符号文本
- **触类旁通**：发现一处反模式立即全仓找同类一次修完
- **改动前先 spec 三件套**（>500 行/3+组件/跨前后端）；**改动后必 Playwright 实测**
- **UI 全中文化**；**报表金额默认"元"**；**中文场景全链路不能崩**
- 功能收敛；git 单 commit；**push 前必先 fetch**；**协作走 PR 不直推 main**
- 目标并发 6000 人；底稿编码致同 2025 修订版（`wp_account_mapping.json`）
- 审计循环代号：A报表 B控制了解 C控制测试 D销售 E货币 F采购存货 G投资 H固定 I无形 J薪酬 K管理 L筹资 M权益 N税费 S专项

## 底稿开发铁律

- **风险导向审计**：B50风险→D~N程序表→A13评价错报，全链可追溯
- **componentType 选型**：结构化联动=d-form-table / 复杂Excel=OnlyOffice / 文档=word-template / 程序表=a-program-console
- **三表HTML渲染**：底稿目录+审定表+附注全走HTML，仅复杂公式/DCF/图表保留OnlyOffice
- **联动是核心价值**：ref_index chip跳转/弹窗+auto_data_source实时取数；孤立底稿=无价值
- **通用schema复用**：`{wp_code}-generic.yaml` + pattern matching
- **开发前必先逐sheet读取源xlsx/docx模板**：从 `backend/wp_templates/{cycle}/` 实物提取
- **导入导出支持三级**（单个/勾选批量/全部一键）
- **适用性自动判断**：`applicable_when` 控制可见性

## 环境配置

- Python 3.12 / Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`
- **rtk 0.42.1**：CLI token 压缩代理（git/pytest/vitest/playwright/eslint/tsc/docker 加前缀）
- Docker：`audit-postgres`(5432)/`audit-redis`(6379)/`audit-metabase`(3000)/`audit-pgbouncer`(6432)
- **host→Docker 连接失败**=vpnkit 端口转发卡死，`docker restart` 即恢复
- **DB_DISABLE_SSL=True**；连接池 150 但 PG max_connections=200（已提）
- **前端唯一路径**：`audit-platform/frontend/`
- **codegraph v0.9.8**：`npx -y @colbymchenry/codegraph`，双机免改配置；hook 自动 sync
- **OnlyOffice 9.4.0**：JWT secret=`onlyoffice-dev-2026`（config.py+docker-compose+local.json 三处一致）
- **scripts 规约**：`_` 前缀=临时用完即删；`backend/scripts/` 分 8 子目录
- **部署v2.0**：瘦客户端(Electron)+内网全栈服务器(FastAPI+PG+Redis+vLLM+MinIO)
- **MinerU 装服务器端**；OCR 走异步任务队列

## 迁移与 PG schema

- MigrationRunner 运行时迁移（非 alembic）；V+R 配对；`IF NOT EXISTS`；**最高 V088**
- **🔴 `from backend.app.` 路径已全量修复（2026-06-19）**：源码7文件+测试19文件统一改为 `from app.`；`_execute_*` 抽到 `note_validation_executors.py`；`_chat_history` 已删（历史改DB持久化）；V083/V084/V086 补齐 R 回滚文件。16699 测试零 collection error
- **🔴 真实列速查**：trial_balance=standard_account_code/unadjusted_amount/aje_adjustment/audited_amount/opening_balance；working_paper 无 wp_code（在 wp_index，JOIN wp_index_id）
- **recalc 铁律**：`tb_balance` 保留 v1 口径（借正贷负），`trial_balance` 必 v2 正数；只汇总叶子；损益取发生额
- **报表引擎**：统一从 trial_balance 取数，TB()/SUM_TB() 公式路径
- **契约测试**：`test_raw_sql_schema_contract`(表级)+`test_raw_sql_column_contract`(列级)

## 任务状态

### 底稿模块（A~S 全循环 2026-06-19 完成）
- **568 任务全绿**，31 个 spec 统一归档到 `_archive/10-A~S-workpaper-all-cycles-complete/`
- wp_account_mapping 900+ 条；_WP_CODE_OVERRIDE 550+ 条；procedure_table_templates 100+ 程序表；auto_data_resolvers 35+ 个
- **render-config 冒烟测试 1096 passed**（覆盖全部 wp_code+componentType+端点调用链）
- **各循环验证测试**：C(75+43)+D(63)+E(50)+F(124)+G(172)+H(144)+I(107)+J(126)+K(262)+L(110)+M(114)+N(87)+S(72) = **2457 passed**
- **event_handlers_cycle_linkage.py**：C/F/D~N 联动（~500行拆出），`register_cycle_linkage_handlers()` 注册5个handler
- **auto_data_resolvers.py**：28 passed（含 control_deficiency_count），异常返回 `{"_error":True}` 供前端区分

### 其他已完成模块
- 合并模块 4 Phase ✅（归档 `_archive/09-consolidation-phases/`）；卡点=0个consolidated项目
- 全局 7 模块改进 ✅；LLM vLLM 跑通（embedding 404 降级 ilike）；知识库收口完成
- A7-A15/A16/A17/A18 完成阶段底稿 ✅；a21-a25 复核底稿 ✅；核对表/弹窗/分析复核 ✅

### git 状态（2026-06-21）
- 分支 `work/2026-05-30-wp-specs`，HEAD `edfbb74f`（前端 Top3 大组件拆分 + spec 任务状态收尾，已推送），最高迁移 V088
- **active spec=1**：audit-report-template-integration 185/190；workpaper-module-health-pass2 ✅ 全部完成（2026-06-21）
- **远程默认分支隐患**：`origin/HEAD→origin/master` 落后 main 298 commit，需 GitHub 改

### wp_render_config 策略拆分（2026-06-19 完成，spec: workpaper-render-config-refactor）
- **✅ P0~P2 全部 21 任务完成**，3772 测试全绿零回归
- `wp_render_config.py` 1474→1156 行；`get_render_config` 475→119 行（dispatch 模式）
- 7 策略文件 `wp_render_strategies/`：_b_index/_a_program/_audit_sheet/_checklist/_analytical_review/_c_note/_univer_grid
- `_resolve_legacy_source` 已删；`control_deficiency_count` 迁入 _REGISTRY（28 测试）
- `wp_component_type_mapping.py` 单一真源；两处 derive_component_type 已改造
- `_WP_CODE_OVERRIDE` 910 条按 15 循环分区注释
- 新增 19 个 cycle_linkage_handlers 集成测试（D/C/F handler）
- **🟡 待 commit**：无（已推送 1fc133da）

### A1-11 签字流转控制表（2026-06-20 修复）
- **修复**：注册 `wp-popup-signing` componentType → `WpPopupSigning.vue`（已有组件，之前仅弹窗模式使用）
- override `"univer"` → `"wp-popup-signing"`；前后端 4 文件改动；1096 冒烟全绿

### 待办
- **✅ workpaper-module-health-pass2（2026-06-21 全部完成，2026-06-20 复查健康）**：9 项 P1/P2 治理，1152 测试零回归
  - `wp_render_config.py` 1156→747；`wp_classification_service.py` 1319→310；`wp_template_files.py` 1160→301
  - 新建 5 service + 2 router（xlsx 652/docx 77）+ 1 JSON（910 条热重载）+ 20 新测试；51 resolver docstring 全覆盖
  - router_registry 启动校验 + CI 测试就位；`_EXCLUDED_ROUTERS` 现仅剩 eqcr 子模块（父包聚合注册），3 个待注册模块已正式注册
  - **复查验证**：app 正常加载 1522 路由、xlsx(4)/docx(1) 端点可达、启动校验无遗漏 WARNING；核心 26 + 冒烟/auto_data 1124 全绿
- **✅ 5 项后续治理 + 6 PBT 已完成（2026-06-21）**：注册 router + 精简 xlsx(758) + skip stub + 联动文档化 + 删 8 孤儿 + 6 PBT(P2~P7) 全绿；workpaper_summaries 无需拆分(37+299行)
- **✅ workpaper-silent-exception-cleanup（P1，2026-06-20 完成）**：底稿模块 70 处宽异常静默吞全部补分级日志留痕，零控制流变更
  - A:working_paper(9) B:模板/网格(16) C+D:交叉核对/离线(8) E:18循环router UUID解析(18) F+G+H:render/其它router/填充(19)
  - 分级:DB/IO/事务/取数失败→warning，样式/UUID入参/LLM降级→debug
  - 新建 `test_wp_silent_exception_guard.py` AST 守卫(CI 阻断新增，白名单空)；守卫 70→0 全绿；1144 测试零回归；app 1522 路由不变
- **底稿改进建议（2026-06-20 调研）**：~~①P0 大文件拆分~~ spec 已立项 `workpaper-module-large-file-split`（pass3）；~~②P1 吞异常~~ ✅；~~③P2 override key 契约~~ ✅；~~④P3 spec 收口~~ ✅
- **✅ P2 override key 契约（2026-06-20）**：新建 `test_wp_code_override_key_contract.py`，聚合全部 data JSON 的 wp_code 全集，override key 须命中或去合法后缀(程序表 A/子表 -N)后命中；30 个孤儿全部通过后缀归一；3 passed
- **✅ P3 spec 收口（2026-06-20）**：`audit-report-template-integration` 归档至 `_archive/05-business-features/`（185/190，剩 3 项 `[ ]*` 人工/外部依赖）；INDEX 更新 active=3（均底稿治理 spec：render-config-refactor/health-pass2/silent-exception-cleanup，待归档）
- **✅ workpaper-module-large-file-split（P0/pass3，2026-06-21 全部完成）**：3 文件拆 ≤800，零行为变更
  - Sprint A `auto_data_resolvers` 1626→域子包(__init__ 97行+6子模块)，51 source 不变；`test_k_cycle` inspect.getsource 改查 `get_registered_sources()`
  - Sprint B `workpaper_fill_service` 1819→30行 Mixin 组合（`wp_fill/` 5 mixin，45 方法仍挂实例供 `service._x()` 测试）；⚠`_review_prompt.load_review_prompt` 因深一层加 1 次 `os.path.dirname` 保 TSJ 路径不变（唯一非逐字改）；顺手删孤儿测试 `TestAIChatService`（引用已删模块 ai_chat_service）
  - Sprint C `working_paper` 1937→400行，共享请求模型抽到 `schemas/workpaper_requests.py`，拆 4 子 router：`wp_editor_router`(727)/`wp_review_router`(405)/`wp_batch_router`(261)/`wp_relation_router`(312)，全部同前缀注册到 router_registry「生命周期/复核」组；helper 随唯一调用方迁移 + working_paper re-export 保向后兼容（test_a16/test_reassignment 依赖）
  - 守卫 `test_wp_large_file_size_guard.py` 转绿；1193+18 测试零回归；app 1522 路由不变；无循环导入
- **底稿改进调研（2026-06-21，pass3 后）**：silent-exception 清零、override 契约已守卫、3 P0 大文件已拆。剩余项：
  - **①pass4 大文件(P1，2026-06-21 完成，spec workpaper-module-large-file-split-pass4)**：3 服务文件拆 ≤800，零行为变更，1222 测试零回归，app 1522 路由不变
    - Sprint A `wp_template_init_service` 1208→769：平级子模块 `wp_template_finder.py`(283)+`wp_template_xlsx_ops.py`(223)，主文件 re-export 保导入路径
    - Sprint B `wp_standard_conversion_service` 934→584：`wp_conversion/_generate.py` WpConversionGenerateMixin(生成6方法)，mixin 组合保方法挂实例
    - Sprint C `wp_fine_rule_engine` 892→569：`wp_fine_rule_checks.py`(315)+`wp_fine_rule_util.py`(24,_safe_num)，单向链 engine→checks→util 避循环
    - 守卫扩 pass4 三目标转绿；`workpaper_models`(826) 本轮未拆(ORM 循环导入风险，后续单独评估)
  - **②skip 测试盲区(P2)**：~~已实测推翻~~ 真实 D1 模板在仓库内(`wp_templates/D/D1 应收票据.xlsx`)，3 文件 31 测试全 PASSED；skipif 仅精简环境降级且各有合成模板兜底，非盲区，**撤销此建议**
  - **③凭证 OCR(P2)**：`wp_evidence_ocr_service.py:224` TODO LLM 链路待接入(stub,外部依赖 vLLM/MinerU)
  - **④resolver 契约(P3,2026-06-21 完成 A 增强版)**：新增全量 resolver 成功契约守卫 PBT(`test_auto_data_resolvers.py`,参数化遍历 51 resolver 喂空结果 mock 断言①不裸抛②返回含非空 summary 的 dict)；**当场抓出 2 个真 bug 并修**：`b3_independence_status`(导入不存在的 ORM 类 ChecklistResponse + 查不存在的 wp_code 列→改裸 SQL JOIN checklist_responses→working_paper→wp_index 按 wp_code='B3')、`related_party_disclosure_check`(导入不存在的 app.models.disclosure_models→改 report_models)；resolver 测试 80 passed,1214 测试零回归,app 1522 路由不变
  - **⚠ 预存失败(非本次范围)**：`test_checklist_responses_crud` 422(PUT body 校验失败,checklist 路由 schema 问题)，依赖真实 DB、与 resolver 改动无关，先于本次存在，待单独修
  - **⑤前端底稿组件健康度（2026-06-21 扫描+清理）**：`components/workpaper/` 反模式债≈0（无空 catch）；**已清 3 处预留 console.log→emit 事件**：GtAnalyticalReview(navigate-row)/AccountPackageFieldSource(navigate-sheet)/AccountPackageConclusionEntry(enter-conclusion)，非破坏(父组件原未监听)，GtAnalyticalReview spec 6 passed。剩唯一债=大文件 8 个>800(GtAProgramConsole 1625/GtChecklistTable 1437/GtAuditSheet 1405/GtAnalyticalReview 1336 等，.vue 含 template+script+style 三段)。**前端拆分风险/成本远高于后端**(抽 composable+拆子组件易破坏响应式/事件流，且每个拆完必 Playwright 实测)，建议单独立 spec 逐组件验证、非紧急。views 层更大(LedgerPenetration 3977/TrialBalance 2945)但非底稿核心组件。**已立 spec `workpaper-frontend-large-component-split`(2026-06-21,vitest/tsc 完成，Playwright 待实测)**：Top 3 抽 composable+子组件
    - Sprint A `GtAProgramConsole` 1626→1144：3 composable(useAProgramReview/Data/Popups)+1 子组件(GtAProgramLinkedChips)。**800 红线结构性达不到**(模板465+样式109+必留script280含 emit-wiring 不能进 composable)，公认地板，30 测试绿零行为变更
    - Sprint B `GtChecklistTable` 1438→752 ✅：3 composable(useChecklistResponses/Search/Applicability)+2 子组件(GtChecklistNav/Section)+checklistTypes.ts，4 测试绿
    - Sprint C `GtAuditSheet` 1406→786 ✅：3 composable(useAuditSheetTable/Columns/Sections)+auditSheetTypes.ts，71 测试绿
    - 守卫 `large_component_guard.spec.ts`：GtChecklistTable/GtAuditSheet 断言 ≤800，GtAProgramConsole 设上限 1200 防回升(不强求≤800)；2 个预存失败(htmlRendererRegistry/GtIndexChip)经 git stash 验证与拆分无关
    - **结论：前端硬 800 红线不普适**，emit-wiring 不能进 composable；composable 不 emit(回调 wire)、保响应式、单向依赖
    - **🟢 Playwright 实测通过(2026-06-21)**：GtAProgramConsole(A1程序表:21行渲染/4阶段/chip点击跳转A15成功/状态下拉)、GtChecklistTable(A15-1调查表:左导航+右条目+适用性弹窗+填 Y 进度 0→1/22 自动保存)均 0 组件级 error；GtAuditSheet 实时 bundle import 无错+71 vitest 覆盖(项目无 audit-sheet 数据未走 UI)。spec 全部任务收口
    - **⚠ 预存非本次**：`/api/workpapers/{id}/save` 422(缺 html_data) 由 GtWpRenderer 父组件(未碰)构造 save body 引起，与拆分无关，同 test_checklist_responses_crud 422 同源，待单独修
- 外部依赖：LLM embedding / 合并 UAT 数据 / GitHub 默认分支改 main
- A 循环 docx 弹窗（30个待加 WpPopupDocxEditor）
- A3-8 商誉减值 / A4 经营分部 / A5 现金流（spec 已建未实施）
- 数据管理"删除"后重导入唯一约束冲突（需 hard_delete 或 DELETE+INSERT）
- 预设映射 seed 权益类 10 条待补

## 操作铁律摘要

完整明细见 `#conventions`（已补 event_bus/测试反模式/asyncpg/router/前端UI/附注/导入/OnlyOffice 各章节）。此处列最高频踩坑（带关键细节避免再犯）：

- **🔴 大文件导入期间禁改后端代码**：app/*.py mtime 变化→uvicorn `--reload` 杀 worker→导入卡死无报错。**含 git stash/pop/checkout/pull**（重写工作区文件）。诊断=`py-spy dump` 看 worker StartTime 晚于 job started_at
- **🔴 event_bus publish 只传 EventPayload**：禁裸 dict/关键字参数（`_build_dedup_key` 访问 `.event_type` 抛异常被 `try/except:pass` 吞→联动断裂）；轻量通知用 `broadcast_raw(event_type, extra)`
- **🔴 测试掩盖 bug 反模式**：mock 不存在的方法/错误签名=把 bug 编进测试（永绿但生产崩）；禁 `try/except:pass` 包被测调用；用 `assert_awaited_once` 验真调用
- **🔴 余额表 KEY_COLUMNS 勿加 account_name**（升 key 会整行跳过删汇总行）；SELECT tb_balance 返前端的端点必须含 direction 字段
- **🔴 同名项目陷阱**：报"修复没生效"先查 `client_name LIKE` 是否多个同名项目+比对 created_at
- **🔴 contenteditable v-model** 必加 isInternalChange/focus guard（否则光标丢失）
- **🔴 el-tooltip 包非单元素根组件**失效→套 `<span style="display:inline-block">`
- **🔴 附注按 sort_order 排序**，禁中文 note_section 字符串排序（Unicode 码点乱套）
- **🔴 freeze_panes xlsx 加载 crash**：`coordinate_to_tuple(str(ws.freeze_panes))`（影响所有冻结窗格底稿）
- **router_registry 必查**：新 router 必注册；静态路径在通配之前；改后重启
- **后端端点双态返回**必在前端 API 层归一化（`Array.isArray` 兜底）
- **service 只 flush 不 commit**：router 统一 commit 保原子；asyncpg 事务 aborted 后修最先失败的 SQL
- **数据管理删除后重导入唯一约束冲突**：需 `hard_delete:true` 或 recalc 改 DELETE+INSERT
- **OnlyOffice 调试**：先确认 git HEAD 正确→只改 .env 对齐 secret+重启；禁 docker exec 手改容器
- **PowerShell 写中文用 fsWrite**；fsWrite ≥100 行会截断→分批 append；长 commit msg 用 `git commit --% -m`

## 关键引用指南

- **仅 memory.md `inclusion: always`**（≤200 行）；其余 manual 引用
- 技术事实/修复明细 → `#dev-history`
- 架构/MCP/数据流 → `#architecture`
- 编码规范/UI/PG运维 → `#conventions`
- spec 状态 → `.kiro/specs/INDEX.md`

- **✅ A 类底稿 Playwright 实操体检（2026-06-20，项目经理视角逐张测）**：项目 `0ec33ac9`(94 张 A 类)，发现并修复 **5 个真 bug**（均导致底稿打不开/报错/保存失败的硬故障）：
  1. **10 张 docx 文档底稿空白页**(A18/A18-1/A26/A26-1~4/A27/A27-1)：根因 seed 脚本只从 xlsx 扫描的 `workpaper_template_analysis.json` 灌分类，docx 函件/清单/备忘录从未入 `workpaper_sheet_classification` → render-config 返回空 sheets。新建 `backend/scripts/seed/seed_docx_document_classification.py`(幂等补 10 行，class_code=`A-报告文档`)。componentType 走 class_code 派生=`a-program-console`(与同类 docx 函件 A9-1/A10-1/A12-1 一致)，**不要**用 word-template(那是 A16 声明书硬编码专用组件 WorkpaperWordEditor，误用会渲染成声明书界面)
  2. **6 文件裸 SQL 表名错** `working_papers`(复数)→`working_paper`(单数,真实表名)：`review_checklist_service`/`a16_version_service`(+列 `wp.wp_code` 不存在改 JOIN wp_index + `pi.working_paper_id`→`pi.wp_id`)/`completion_phase`(3处)/`time_machine`(3处 table_map)/`status_machine`(1处 table_map)。导致复核签字状态/A16 推荐版本等多端点 500。`adjustments`/`disclosure_notes`/`procedure_instances` 是对的复数，勿动
  3. **GtRegulatoryLetter.vue 导入路径错** `@/components/common/GtIndexChip.vue`→`@/components/workpaper/GtIndexChip.vue`(全仓唯一错处)：A18-2 监管沟通函永远打不开(Vite 500)
  4. **AuditLegendPanel.vue field-overrides 契约错**：用了 `/api/workpapers/{wpId}/field-overrides?scope&key`(路径含 wpId+key 参数)，真实契约是 `/api/workpapers/field-overrides` POST body `{project_id,year,scope,item_key,field,value}` / GET query `{project_id,year,scope}` 返回 `{item_key:{field:value}}` 批量。补 year prop(GtWpRenderer 已传)，GET 读 `data.custom_items.value`。A31 审计标识 404 修复
  5. **GtWpRenderer.onSave 缺防御 → /save 422**(memory 预存问题根因)：WpPopupSigning 等自持久化组件(PUT checklist-responses)`emit('save')` 无参，onSave 仍包装成 `{sheet_name, html_data:undefined}` emit save-success → 外层 POST /save 缺 html_data 触发 422。修复:onSave 判 data 为空(null/非 object/数组)时改 `emit('saved-notify')` 仅刷新不发 /save；新增 saved-notify emit 声明 + WorkpaperEditor `@saved-notify="onChildSaved"` wiring。A1-11 切 tab/签字自动保存 422 消除
  6. **extractTableCode undefined 崩溃**(a11-bundle/a15-bundle 嵌套渲染 GtAProgramConsole，sheetName 为 undefined)：`useAProgramPopups.ts`+`useAProgramReview.ts` 两处 `sheetName.match(...)` 改 `sheetName?.match(...)`。A11/A15 bundle 从 8 error→0（拆分前同款无防御代码，bundle 场景才暴露）
  7. **prefill-suggestions 500**(`review_checklist_service.get_prefill_suggestions`)：查 `WorkingPaper.status.in_(["completed","reviewed"])` 但 `wp_file_status` 枚举无这俩值（合法值 draft/edit_complete/under_review/revision_required/review_passed/archived）→ 改 `["edit_complete","review_passed","archived"]`。A21 复核表 500 修复
  8. **review-definitions 父码 404**(A21/A22…父码)：`get_review_definition_for_wp` 对父码 A2[1-5] 先调 `resolve_review_wp_code` 解析为适用子码(A21-1/A21-2)再查定义。前端无需改，所有调用方受益
  - **已 UI 实测 0 error 的 A 类 componentType（全覆盖）**：a1-dashboard(A1)/a-program-console(A18/A8/A9-1/A30/A17系列)/checklist-table(A1-12/A17-5-1)/analytical-review(A1-13)/misstatement-workpaper(A13)/audit-sheet(A4-1/A5-1)/a2-adjustment-console(A2)/a3-consolidation-console(A3)/audit-legend(A31)/regulatory-letter(A18-2)/wp-popup-signing(A1-11,含4tab+签字)/word-template(A16)/cf-verification(A5)/c-note-table(A5-4/A7-2)/b-index(A6-1)/d-form-confirmation(A10-2)/a11-bundle(A11)/a15-bundle(A15)/a14-3-workbook(A14-3)/e-control-test(A14-6)/review-checklist(A21)/a17-summary(A17-1)/d-form-table(A7-1)。**A 类 94 张全部体检通过，0 残留 error**
  - **🟢 B/C 类底稿体检（2026-06-20 续）**：B 类 18 张 + C 类 21 张全部测完。C 类全绿（a-program-console/d-form-table/audit-sheet 三型）。B 类发现 **第 9 个 bug + 1 个同类 docx 缺失**：
    - **B5 业务约定书控制表空白页**：同 A18 docx 模式（docx 未被 xlsx 扫描器收录 → 分类缺失）。扩展 `seed_docx_document_classification.py` 支持 per-entry class_code，补 B5(`B-报告文档`)+ override JSON `B5→a-program-console`。⚠ `find_template_file_any("B5")` 前缀模糊匹配误命中 `B50`（已知小瑕疵，未修）
    - **9. procedure_table 未知 code 500 → 优雅空表降级**：`procedure_table_auto_service.get_procedure_table` 对无模板 code 原 `raise ValueError`→FastAPI 500。改为返回空表 `{items:[]}`（前端 a-program-console 渲染空表+可手动加行，绝不 500）。系统级健壮性，所有无模板/自定义底稿受益。B5 走 a-program-console 渲染空程序表（临时方案，理想是配真实控制表模板，记待办）
    - B15 重要性计算表 `redirect:true→/materiality` 空 sheets 是**预期**（重定向重要性模块），非 bug
    - **已 UI 实测 0 error**：B 类 univer/e-control-test/h-static-doc(B23)/d-form-table(B1)/checklist-table(B3)/audit-sheet(B60)/a-program-console(B10/B5)；C 类 a-program-console(C1)/d-form-table(C10)/audit-sheet(C22)
    - **🟡 待 commit 追加**：`procedure_table_auto_service.py`(空表降级) + seed 脚本 per-entry class_code + override JSON(B5)+1 行 DB(B5 分类)
  - **🟢 D~N+S 全循环体检（2026-06-20，后端 API 全扫 + 前端抽测）**：D/E/F/G/H/I/J/L/M/N 全绿 0 problems。componentType 分布:DEFGH=confirmation-hub/d-form-table/audit-sheet；I=d-form-table/audit-sheet；J=单底稿八合一(b-index/a-program-console/audit-sheet/c-note-table/univer/d-form-table/skip/h-static-doc)；KLMN=c-note-table/audit-sheet/confirmation-hub；S=a-program-console/d-form-table/audit-sheet/h-static-doc/skip
    - **K14~K18 + S17 空白页修复**：本项目 wp_index 用了标准模板库无的编码(K14资产处置收益/K15其他收益/K16投资收益/K17公允价值变动收益/K18递延收益审定表，标准 K 模板仅到 K13)；S17 非经常性损益模板是旧版 `.xls`(analyze 脚本只扫 .xlsx 漏)。均分类缺失→空白。扩展 seed 补 6 行(class_code K-审定表/S-审定表)+override JSON K14~K18→audit-sheet(S17 已有)。audit-sheet 无模板优雅降空表(K14 UI 实测:工具栏齐全+空态提示「请等待模板初始化或手动新增行」+一键刷新 TB 取数)，0 error
    - **已 UI 实测 0 error**：confirmation-hub(D0)/audit-sheet(D2-2/K14/S17)/八合一(J1)/c-note-table(K1/M1)
    - **B15 同类**：重要性计算表 redirect→/materiality 空 sheets 是预期非 bug
    - **🟡 遗留小瑕疵**：`find_template_file_any` 前缀模糊匹配(B5 误命中 B50、K14 命中 None 但实际无模板)+ analyze 脚本只扫 .xlsx 漏 .xls/.docx → 待单独修模板查找器；K14~K18 用非标准编码是该项目 wp_index seed 数据问题(其他项目同码 name 各异)，根治需规范 wp_index 编码
    - **🟡 待 commit 追加**：seed 脚本(K14~K18/S17 共 6 entry) + override JSON(K14~K18) + 6 行 DB
  - **render-config 体检法**：`GET /api/workpapers/{id}/render-config` 看 `sheets[].componentType`，sheets 空=分类缺失；override JSON 改后需 touch 一个 app/*.py 触发 uvicorn reload(JSON 改动不触发 reload，且 `_WP_CODE_OVERRIDE` 是模块级快照非热重载到消费方)
