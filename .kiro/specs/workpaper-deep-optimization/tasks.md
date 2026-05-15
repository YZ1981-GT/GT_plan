# 实施计划：底稿深度优化

## 概述

基于 design.md 的 10 个架构决策，按依赖顺序分 8 个 Sprint 推进。前 4 个 Sprint 为核心功能（P0），后 4 个为增强功能（P1-P2）。

## Tasks

- [x] 1. Sprint 1：数据模型与基础设施
  - [x] 1.1 创建 Alembic 迁移：wp_template_metadata 表
  - [x] 1.2 创建 Alembic 迁移：workpaper_procedures 表
  - [x] 1.3 创建 Alembic 迁移：cross_check_results 表
  - [x] 1.4 创建 Alembic 迁移：evidence_links 表
  - [x] 1.5 创建 Alembic 迁移：workpaper_snapshots 表
  - [x] 1.6 创建 Alembic 迁移：working_paper 表新增 quality_score / consistency_status / procedure_completion_rate / wp_status 列
  - [x] 1.7 创建 Alembic 迁移：cell_annotations 表
  - [x] 1.8 创建 ORM 模型 wp_optimization_models.py（6 个新模型类，含 CellAnnotation）
  - [x] 1.9 创建 cross_account_rules.json 规则库（8 条内置规则）
  - [x] 1.10 创建 wp_template_metadata 种子数据脚本（从 wp_account_mapping.json 88 条生成初始元数据）
  - [x] 1.11 Checkpoint

- [x] 2. Sprint 2：程序管理与裁剪
  - [x] 2.1 实现 wp_procedure_service.py（CRUD + 裁剪 + 完成标记 + 完成率计算）
  - [x] 2.2 实现 wp_procedures.py 路由（GET 清单 / PATCH 完成 / PATCH 裁剪 / POST 自定义 / POST 从上年复制）
  - [x] 2.3 实现前端 ProcedurePanel.vue（程序清单展示 + 勾选完成 + 裁剪操作）
  - [x] 2.4 实现前端 ProcedureFlowChart.vue（mermaid 流程图，从 procedure_steps 动态生成）
  - [x] 2.5 实现 useProcedures.ts composable
  - [x] 2.6 集成到 WorkpaperSidePanel（新增"程序"Tab）
  - [x] 2.7 实现程序完成率→quality_score 联动（完成率变化时触发重算）
  - [x] 2.8 Checkpoint

- [x] 3. Sprint 3：公式引擎扩展
  - [x] 3.1 扩展 prefill_engine.py 新增 6 种公式解析（=WP/=LEDGER/=AUX/=PREV/=ADJ/=NOTE）
  - [x] 3.2 实现依赖图构建 + 拓扑排序 + 循环引用检测
  - [x] 3.3 实现增量刷新（stale 标记 + 只重算受影响公式）
  - [x] 3.4 实现 provenance 记录扩展（新公式类型的来源追踪）
  - [x] 3.5 实现前端公式状态展示（侧面板"公式"Tab：🟢/🟡/🔴/⏳）
  - [x] 3.6 实现前端公式单元格 hover tooltip（来源摘要）
  - [x] 3.7 实现前端"查看来源"右键菜单→侧面板穿透展示
  - [x] 3.8 实现批量预填充（按依赖顺序处理多底稿）
  - [x] 3.9 Checkpoint

- [x] 4. Sprint 4：跨科目校验与一致性
  - [x] 4.1 实现 wp_cross_check_service.py（规则加载 + 执行 + 结果持久化）
  - [x] 4.2 实现 wp_cross_check.py 路由（POST 执行 / GET 结果 / GET 规则 / POST 自定义规则）
  - [x] 4.3 实现 L1 单底稿校验（审定数 vs 试算表）
  - [x] 4.4 实现 L2 跨科目等式校验（解析规则公式 + 从底稿取值 + 比较）
  - [x] 4.5 实现校验触发时机（保存时增量 / 手动全量 / 签字前门禁 blocking）
  - [x] 4.6 实现前端 CrossCheckPanel.vue（校验结果展示 + 差异明细）
  - [x] 4.7 实现 useCrossCheck.ts composable
  - [x] 4.8 集成到签字前门禁 gate_engine（CROSS_CHECK_PASSED 规则）
  - [x] 4.9 Checkpoint

- [x] 5. Sprint 5：编辑器组件体系
  - [x] 5.1 重构 WorkpaperEditor.vue 为路由分发器（动态组件加载）
  - [x] 5.2 实现 WorkpaperFormEditor.vue（el-form + JSON schema 驱动，支持 B 类/C 类表单底稿）
  - [x] 5.3 实现 WorkpaperWordEditor.vue（Univer Doc 模式或 docx 字段填充+预览模式）
  - [x] 5.4 实现 WorkpaperTableEditor.vue（GtEditableTable 封装，支持 CRUD + 筛选 + 导入）
  - [x] 5.5 实现 WorkpaperHybridEditor.vue（表单+表格+附件三段式布局）
  - [x] 5.6 实现编辑器共享工具栏（保存/导出/版本/公式/面板 统一）
  - [x] 5.7 实现 component_type 路由逻辑（从 wp_template_metadata 读取类型→加载对应组件）
  - [x] 5.8 Checkpoint

- [x] 6. Sprint 6：证据链与附件管理
  - [x] 6.1 实现 wp_evidence_service.py（创建/删除/批量关联/充分性检查）
  - [x] 6.2 实现 wp_evidence.py 路由（GET / POST link / DELETE / POST batch-link）
  - [x] 6.3 实现前端 EvidenceLinkPanel.vue（证据清单 + 关联操作）
  - [x] 6.4 实现 Univer 右键菜单"引用附件"/"上传并引用"/"查看引用的附件"
  - [x] 6.5 实现单元格📎图标渲染 + hover 预览
  - [x] 6.6 实现 useEvidenceLink.ts composable
  - [x] 6.7 实现证据充分性检查（保存时校验必做程序有附件）
  - [x] 6.8 实现归档时自动生成 evidence_index.xlsx
  - [x] 6.9 Checkpoint

- [x] 7. Sprint 7：智能辅助（OCR + LLM）
  - [x] 7.1 实现凭证 OCR 结构化提取模板（unified_ocr_service 扩展）
  - [x] 7.2 实现 OCR 结果→抽凭表自动填充逻辑
  - [x] 7.3 实现前端 OCRResultPanel.vue（识别结果展示 + 置信度标记 + 批量修正）
  - [x] 7.4 实现凭证照片↔抽凭表行双向关联
  - [x] 7.5 实现 LLM 审计说明生成 prompt 模板（变动分析/结论/差异说明/假设说明）
  - [x] 7.6 实现前端 AISuggestionPopover.vue（确认/修改/拒绝三按钮）
  - [x] 7.7 实现合同/对账单 OCR 提取→台账自动填充
  - [x] 7.8 Checkpoint

- [x] 8. Sprint 8：质量评分 + 快照 + 风险追溯 + 仪表盘
  - [x] 8.1 实现 wp_quality_score_service.py（5 维度加权计算 + 触发时机）
  - [x] 8.2 实现 wp_snapshot_service.py（自动创建 + 对比 + 锁定）
  - [x] 8.3 实现 wp_risk_trace_service.py（风险-底稿映射 + 链路完整性检查）
  - [x] 8.4 实现 wp_conclusion_service.py（结论提取 + 汇总 + 分类）
  - [x] 8.5 实现前端 QualityScoreBadge.vue + 仪表盘视图扩展
  - [x] 8.6 实现前端 SnapshotCompare.vue（快照对比 + 差异高亮）
  - [x] 8.7 实现前端 RiskTraceGraph.vue（风险追溯链路图）
  - [x] 8.8 实现前端 ConclusionOverview.vue（结论总览视图）
  - [x] 8.9 实现 wp_sampling_engine.py（统计/非统计/MUS 三种方法）
  - [x] 8.10 实现前端 SamplingWizard.vue（抽样向导）
  - [x] 8.11 Checkpoint

- [ ]* 9. Sprint 9：属性测试与集成测试
  - [x]* 9.1 Property 1+8：质量评分幂等性+边界
  - [x]* 9.2 Property 5：程序完成率严格递增
  - [x]* 9.3 Property 7：预填充幂等性
  - [x]* 9.4 Property 9：跨科目校验等式对称性
  - [x]* 9.5 Property 16：公式依赖图无环
  - [x]* 9.6 Property 13：快照不变性
  - [x]* 9.7 Property 11：审计轨迹不可篡改性
  - [x]* 9.8 集成测试：底稿保存→校验→stale→SSE 全链路
  - [x]* 9.9 集成测试：OCR 上传→识别→填表 全链路
  - [x]* 9.10 集成测试：预填充→provenance→穿透 全链路

- [x] 10. Sprint 10：复核批注 + 批量操作 + 事件联动（覆盖缺口）
  - [x] 10.1 实现 wp_cell_annotation_service.py（创建/回复/解决/按状态查询）
  - [x] 10.2 实现 wp_cell_annotations.py 路由（POST 创建 / PATCH 回复 / PATCH 解决 / GET 列表）
  - [x] 10.3 实现前端 CellAnnotationPanel.vue（批注列表+状态筛选+点击定位）
  - [x] 10.4 实现 Univer 右键菜单"添加复核意见"+单元格红色三角标记渲染
  - [x] 10.5 实现复核检查清单服务（从模板元数据加载检查项+勾选+自动推进状态）
  - [x] 10.6 实现前端 ReviewChecklistPanel.vue（检查项列表+进度条+通过/退回按钮）
  - [x] 10.7 实现批量预填充端点（POST /batch-prefill，并行执行+SSE 进度推送）
  - [x] 10.8 实现批量导出 PDF 端点（POST /batch-export，逐个转换+ZIP 打包+页眉页脚）
  - [x] 10.9 实现批量提交复核端点（POST /batch-submit，blocking 跳过+结果清单）
  - [x] 10.10 实现前端批量操作 UI（选中+操作按钮+进度条+结果摘要弹窗）
  - [x] 10.11 实现 EventType 注册（5 个新事件）+ event_handlers 订阅（stale 传播+试算表重算+附注刷新）
  - [x] 10.12 实现 wp_note_linkage_service.py（附注取数+一致性校验+一键取数）
  - [x] 10.13 Checkpoint

- [x] 11. Sprint 11：权限 + EQCR + 交叉索引 + 审计轨迹 + 可观测性（覆盖缺口）
  - [x] 11.1 实现底稿权限粒度（项目级/循环级/单底稿级 三层权限检查中间件）
  - [x] 11.2 实现单元格级锁定（合伙人专属单元格标记，助理不可编辑）
  - [x] 11.3 实现 EQCR 充分性评价端点（POST /eqcr-evaluation，充分/需补充/重大疑虑）
  - [x] 11.4 实现前端 EQCR 充分性评价视图（关键底稿筛选+快捷评价+IssueTicket 联动）
  - [x] 11.5 实现交叉索引解析（Univer 单元格中 →底稿编码-页码 格式自动识别+双向链接）
  - [x] 11.6 实现前端交叉索引 Tab（引用了/被引用 双向清单+点击跳转）
  - [x] 11.7 实现底稿审计轨迹扩展（审定数修改/程序标记/裁剪/预填充 写入 audit_log_entries 哈希链）
  - [x] 11.8 实现前端"查看修改历史"右键菜单（单元格级时间线）
  - [x] 11.9 实现签字日期链校验（编制日期≤复核日期≤合伙人签字日期≤审计报告日）
  - [x] 11.10 实现底稿健康监控仪表盘端点（GET /admin/workpaper-health）
  - [x] 11.11 实现底稿全文搜索端点（GET /search，搜索内容/公式/批注/附件名）
  - [x] 11.12 实现前端公式管理依赖图视图（有向图+stale 高亮+编制顺序建议）
  - [x] 11.13 Checkpoint

## UAT 验收清单

1. 审计助理打开 D2 底稿，侧面板展示 12 个程序步骤（含流程图），逐项勾选完成
2. 项目经理对 D2 底稿裁剪"专项-IPO"类程序，助理看不到被裁剪的程序
3. 底稿执行预填充后，=TB/=WP 公式自动取数，hover 显示来源 tooltip
4. 修改 H1 折旧审定数后，K8/K9 底稿自动标记 stale（黄色背景）
5. 执行跨科目校验，折旧分摊不一致时显示差异明细
6. 上传 10 张凭证照片，OCR 自动识别并填入抽凭表
7. 点击"AI 生成说明"，LLM 生成变动分析文本，确认后写入底稿（浅蓝色标记）
8. 在 Univer 单元格右键"引用附件"，选择凭证照片，单元格显示📎图标
9. 合伙人打开"风险追溯视图"，点击某风险看到完整 B→C→D→A 链路
10. 项目经理查看仪表盘，按循环看到质量评分热力图

## Notes

- 标记 `*` 的任务为可选（测试类），可跳过以加速 MVP
- 每个 Sprint 末尾有 Checkpoint 确保增量验证
- Sprint 1-4 为 P0 核心功能（数据模型+程序+公式+校验）
- Sprint 5-8 为 P1 增强功能（编辑器+证据链+智能+质量）
- Sprint 9 为属性测试（可选）
- Sprint 10-11 为覆盖缺口补齐（复核批注+批量+权限+EQCR+交叉索引+审计轨迹+可观测性）
- 预计总工期：11 Sprint × 1 周 = 11 周（单人），可并行压缩到 6-7 周
- 建议实施顺序：Sprint 1→2→3→4→10（P0 核心+复核）→5→6→7→8→11→9
