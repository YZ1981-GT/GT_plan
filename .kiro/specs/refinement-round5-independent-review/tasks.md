# Refinement Round 5 — 任务清单

按 README 约定：一轮 ≤ 20 任务，分 **2 个 Sprint**。前置依赖：R1 全部完成（签字流水、归档章节化、枚举预留），R3 可选（质控合议场景需要）。

## Sprint 1：基础设施 + 工作台 + 判断类事项（需求 1, 2, 4）

- [x] 1. 数据模型迁移：EQCR 全套表 + 状态机扩展
  - 新建 `backend/app/models/eqcr_models.py`（EqcrOpinion / EqcrReviewNote / EqcrShadowComputation / EqcrDisagreementResolution）
  - 新建 `backend/app/models/related_party_models.py`（RelatedPartyRegistry + RelatedPartyTransaction）
  - `ReportStatus` 枚举插入 `eqcr_approved`
  - `GateType` 新增 `eqcr_approval`
  - `WorkHourRecord.purpose` 新字段
  - Alembic 脚本 `round5_eqcr_{date}.py`
  - 导入 `app/models/__init__.py`
  - _依赖_ README 跨轮约束 3；_需求_ 1, 2, 4, 5, 6, 8

- [x] 2. 权限与 SOD：角色四点同步 + EQCR 独立性规则
  - `AssignmentRole` 已在 R1 预留 eqcr，本轮确认 `assignment_service.ROLE_MAP` 新增条目
  - `role_context_service._ROLE_PRIORITY` 加 `eqcr: 5`（与 partner 同级）
  - 前端 `ROLE_MAP` 加 `eqcr=独立复核合伙人`
  - `composables/usePermission.ts` 新动作 `view_eqcr / record_opinion / shadow_compute / approve_eqcr`
  - `sod_guard_service` 注册 `EqcrIndependenceRule`
  - _依赖_ README 跨轮约束 2, 4, 7；_需求_ 1

- [x] 3. 后端：EQCR 工作台 service
  - `backend/app/services/eqcr_service.py`
  - `GET /api/eqcr/projects` 返回本人 EQCR 项目
  - `GET /api/eqcr/projects/{id}/overview` 总览
  - _需求_ 1

- [x] 4. 前端：EqcrWorkbench 页面
  - `src/views/eqcr/EqcrWorkbench.vue` 工作台
  - 项目卡片（签字日、我的 EQCR 进度、判断事项未复核/已复核数）
  - 路由 `/eqcr/workbench`，权限 `role in ('partner','admin') and project_assignment.role='eqcr'`
  - _需求_ 1

- [x] 5. 后端：5 判断域聚合 API
  - `GET /materiality / estimates / related-parties / going-concern / opinion-type`
  - 持续经营直接复用 `GoingConcernEvaluation` 模型查询，不重建
  - `POST /api/eqcr/opinions` + `PATCH`
  - _需求_ 2

- [x] 6. 前端：EqcrProjectView + 5 Tab 组件
  - `src/views/eqcr/EqcrProjectView.vue` 主壳
  - `EqcrMateriality.vue` / `EqcrEstimates.vue` / `EqcrRelatedParties.vue` / `EqcrGoingConcern.vue` / `EqcrOpinionType.vue`
  - 每 Tab 底部嵌 `EqcrOpinionForm.vue` 录入意见
  - _需求_ 2

- [x] 7. 前端：关联方最小建模 UI
  - 关联方 Tab 内嵌 CRUD 表单（注册 + 交易）
  - 权限：EQCR 只读 + 经理级可写
  - _需求_ 2

- [x] 8. 后端：影子计算复用一致性引擎
  - `POST /api/eqcr/shadow-compute` 调 `consistency_replay_engine` with `caller_context='eqcr'`
  - 结果存 `eqcr_shadow_computations` 表
  - 与项目组结果对比 `has_diff` 字段
  - 限流：每项目每天 20 次（Redis）
  - _需求_ 4

- [x] 9. 前端：EqcrShadowCompute 组件
  - 选择计算类型 + 参数 + 执行
  - 差异红标展示
  - _需求_ 4

- [x] Sprint 1 验收
  - 单元测试：SOD `EqcrIndependenceRule` 4 场景
  - 集成测试：`test_eqcr_workbench.py`（委派 EQCR → 录意见 → 影子计算）
  - 数据扫描：上线前扫描现有 ProjectAssignment，标记潜在 SOD 冲突由 admin 确认
  - UAT：requirements.md UAT 第 1/2/4 条走完

## Sprint 2：门禁 + 状态机锁定 + 备忘录 + 指标（需求 3, 5, 6, 7, 8, 9, 10）

- [~] 10. 后端：EQCR 独立复核笔记（不对外联络）
  - 新建 `eqcr_review_notes` 表（已在任务 1 建模）
  - `GET/POST/PATCH/DELETE /api/eqcr/projects/{id}/notes`
  - 默认 `shared_to_team=false` 项目组不可见；`POST /api/eqcr/notes/{id}/share-to-team` 分享到 `Project.wizard_state.communications`（复用 R2 需求 5 沟通记录），注明来源"EQCR 独立复核笔记"
  - **独立性边界**：笔记为内部留痕，不提供对外联络通道；与客户核实通过签字合伙人转达
  - _需求_ 3（已按 requirements v1.2 收窄）

- [~] 11. 前端：EqcrReviewNotesPanel
  - Tab 外独立面板，录入/查看笔记
  - "分享给项目组"按钮（单条）
  - _需求_ 3

- [~] 12. 后端：EQCR 新门禁阶段
  - `gate_engine` 新增 `GateType.eqcr_approval`
  - 基础规则：已有 opinion 覆盖 5 个 domain 且无 unresolved disagreement
  - `POST /api/eqcr/projects/{id}/approve` 触发 gate → 通过则切 `AuditReport.status=eqcr_approved`
  - `POST /api/eqcr/projects/{id}/unlock-opinion` 回退到 review
  - _需求_ 5, 6

- [~] 13. 后端：状态机锁定联动
  - `AuditReportService.update_paragraph` 扩展检查：`eqcr_approved` 态下禁改 `opinion_type` 和段落，返回 403 `OPINION_LOCKED_BY_EQCR`
  - `SignService.sign` 最高级（order=4 EQCR）签字完后切状态（R1 需求 4 机制复用，本轮只扩展到 EQCR）
  - order=5 归档前最后一级签字完后 `eqcr_approved → final`
  - _需求_ 5, 6

- [~] 14. 前端：AuditReportEditor 状态标签
  - 根据 `status` 显示不同图标 + 文案：draft/review/🔒EQCR已锁/🔒已定稿
  - eqcr_approved 态 opinion_type 下拉置 disabled
  - _需求_ 6

- [~] 15. 后端：历年 EQCR 对比
  - `GET /api/eqcr/projects/{id}/prior-year-comparison`
  - 按 client_name 精确匹配近 N 年项目 EQCR 意见
  - 差异点标记；本年意见新增"差异原因"必填字段
  - 手动指定上年项目端点（兜底）`POST .../link-prior-year`
  - _需求_ 7

- [~] 16. 前端：EqcrPriorYearCompare
  - "历年对比" Tab
  - 差异高亮 + 强制写原因才能 approve
  - 未找到项目时"手动关联"按钮
  - _需求_ 7

- [~] 17. 后端：EQCR 工时追踪
  - `WorkHourRecord.purpose='eqcr'` 字段使用
  - `EqcrProjectView` "开始复核"按钮调后端开始计时，"提交意见"调结束 → 生成一条 purpose=eqcr 的工时记录
  - EQCR 可再手工修正
  - _需求_ 8

- [~] 18. 后端：EQCR 备忘录生成
  - `POST /api/eqcr/projects/{id}/memo` 组装 Word（模板 `eqcr_memo.docx`）
  - `PUT .../memo` 编辑保存
  - `POST .../memo/finalize` 定稿 → PDF
  - 注册到 R1 `archive_section_registry`：`('02', 'eqcr_memo.pdf', eqcr_memo_pdf_generator)`
  - _需求_ 9，依赖 R1 归档章节化

- [~] 19. 前端：EqcrMemoEditor
  - 模板预览 + 富文本编辑 + 定稿按钮
  - _需求_ 9

- [~] 20. 后端 + 前端：EQCR 指标仪表盘
  - `GET /api/eqcr/metrics?year=` 返回 `[{eqcr_id, name, project_count, total_hours, disagreement_count, disagreement_rate, material_findings_count}]`
  - `src/views/eqcr/EqcrMetrics.vue` 页面（admin + qc 合伙人可见）
  - 差异率 > 20% 绿标 / = 0% 黄标 + 文案"异议率不是负面指标"
  - _需求_ 10

- [~] Sprint 2 验收
  - 单元测试：状态机转移 hypothesis 属性测试
  - 集成测试：`test_eqcr_full_flow.py`（完整链：委派 → 5 Tab → 影子计算 → 审批 → 状态锁 → 签字 → final → 备忘录进归档包）
  - 回归：AuditReport draft/review/final 原有流程不变
  - UAT：requirements.md UAT 第 3/5/6/7/8/9 条走完

## 完成标志

- 所有任务 `[x]`
- UAT 9 项有通过记录
- SOD 规则测试通过，无潜在数据冲突
- 归档包验证含 `02-EQCR备忘录.pdf` 章节
- 5 轮全部完成，启动跨角色总复盘（README "终止条件"判定）

## Sprint 3：集团审计 + 年度独立性（需求 11~12，新增）

4 个任务。依赖 R1 Sprint 3（独立性声明框架）完成。

- [~] 21. 后端：组成部分审计师聚合 API
  - `GET /api/eqcr/projects/{id}/component-auditors` 聚合 ComponentAuditor + Instructions + Results
  - `eqcr_opinions.domain` 枚举扩展 `component_auditor`
  - _需求_ 11

- [~] 22. 前端：组成部分审计师 Tab
  - `src/components/eqcr/EqcrComponentAuditors.vue`
  - `project.report_scope == 'consolidated'` 时在 `EqcrProjectView` 展示
  - 能力 C/D 评级行高亮，EQCR 意见表单
  - _需求_ 11

- [~] 23. 后端：年度独立性声明
  - `independence_declarations.declaration_scope` 扩展 `project|annual` 枚举（R1 已建表，本轮只扩 enum）
  - `backend/data/independence_questions_annual.json` seed 30+ 题
  - 登录守卫：EQCR/partner/qc 无本年度 annual 声明时阻断访问 EQCR 工作台
  - _需求_ 12

- [~] 24. 前端：年度声明弹窗 + 抽查入口
  - 登录后首访 EQCR 工作台弹窗"提交年度独立性声明"
  - admin 新增"年度声明抽查"页面（简版，复用 R3 抽查框架组件）
  - 备忘录（R5 需求 9）章节追加"组成部分审计师复核"
  - _需求_ 11, 12

- [~] Sprint 3 验收
  - 集成测试：`test_eqcr_component_auditor_review.py`
  - UAT 新增：
    - 合并项目的 EQCR 看到组成部分 Tab，录意见后进备忘录
    - 新年度首次登录 EQCR 工作台弹年度声明弹窗，未填不能进
