# 实施计划：五类角色作业台与质量闭环

## 任务总览

> 本节保留主任务索引；实际排期和执行以“详细落地拆解”为准。本 spec 依赖 Context / Linkage / Evidence 的 P0，不建议提前开工。

- [ ] 1. RoleWorkbenchFacade
  - [ ] 1.1 新建 `role_workbench_facade.py`
  - [ ] 1.2 聚合待办、复核、质量、工时、风险、stale 指标
  - [ ] 1.3 API：`GET /api/projects/{pid}/role-workbench`
  - [ ] 1.4 测试：不同角色返回不同区块
  - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [ ] 2. 前端 RoleWorkbenchShell
  - [ ] 2.1 新建 `RoleWorkbenchShell.vue`
  - [ ] 2.2 按角色渲染助理/经理/QC/合伙人/EQCR 入口
  - [ ] 2.3 接入项目上下文与权限矩阵
  - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [ ] 3. 审计助理作业台
  - [ ] 3.1 聚合今日待办、退回复核、资料缺口、AI 建议
  - [ ] 3.2 待办点击直接定位目标对象
  - [ ] 3.3 显示截止日、责任人、下一步动作
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] 4. 项目经理经营驾驶舱
  - [ ] 4.1 实现进度、质量、预算、风险四象限
  - [ ] 4.2 接入工时预算消耗率和人员负荷
  - [ ] 4.3 接入复核 Aging 与质量分
  - [ ] 4.4 异常指标一键下钻
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 5. 质控闭环工作台
  - [ ] 5.1 QC 问题关联底稿/单元格/附件/复核记录
  - [ ] 5.2 实现问题状态流转
  - [ ] 5.3 问题关闭要求关闭依据
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] 6. 合伙人签发风险雷达
  - [ ] 6.1 聚合重大事项、关键调整、未关闭复核、AI 未确认内容
  - [ ] 6.2 接入签发阻断项
  - [ ] 6.3 支持合伙人确认与审计日志
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 7. EQCR 独立复核工作台
  - [ ] 7.1 聚合 KAM、重大估计、关联方、持续经营、集团范围
  - [ ] 7.2 区分普通复核与 EQCR 批注
  - [ ] 7.3 建立 EQCR 签出 checklist
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 8. 质量问题类型库
  - [ ] 8.1 新增问题类型模型或配置
  - [ ] 8.2 复核/QC 问题支持归类
  - [ ] 8.3 问题类型用于培训和规则优化导出
  - _Requirements: 6.1, 6.2_

- [ ] 9. 验收
  - [ ]* 五类角色 UAT 各 1 条主路径
  - [ ]* pytest facade 聚合测试通过
  - [ ]* Vitest workbench 渲染测试通过

---

## 详细落地拆解（执行以本节为准）

### P0-MVP：开工前置与最小验证

- [x] MVP-1. 完成数据来源盘点，不开发新 dashboard
- [x] MVP-2. 冻结 5 个核心指标口径：完成率、Aging、预算消耗率、质量分、签发阻断项
- [x] MVP-3. 定义 RoleWorkbench DTO 示例
- [x] MVP-4. 仅实现后端 facade mock/fixture 测试，不接页面
- [x] MVP-5. 测试文件落地：
  - `backend/tests/test_role_workbench_facade.py`
  - `audit-platform/frontend/src/views/__tests__/RoleWorkbench.spec.ts`
  - **验收标准**：后端 pytest mock DB in-memory 可跑；前端 vitest mock API shallow mount；核心 Property 对应 case 必须覆盖

### P0：前置依赖检查与数据口径冻结

- [ ] P0-1. 前置依赖确认
  - [ ] P0-1.1 确认 `platform-context-permission-foundation` P0 已提供角色/职责/权限
  - [ ] P0-1.2 确认 `platform-linkage-contract-stale` P0 已提供 route resolver
  - [ ] P0-1.3 确认复核、QC、EQCR 现有 service 可查询基础数据
  - [ ] P0-1.4 输出 `docs/reference/role-workbench-data-sources.md`
  - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [ ] P0-2. 指标口径冻结
  - [ ] P0-2.1 定义底稿完成率口径
  - [ ] P0-2.2 定义复核 Aging 口径
  - [ ] P0-2.3 定义工时预算消耗率口径
  - [ ] P0-2.4 定义签发阻断项口径
  - [ ] P0-2.5 形成 `docs/reference/workbench-metric-semantics.md`
  - [ ] P0-2.6 定义 `RoleWorkbenchDTO` JSON 示例
  - [ ] P0-2.7 数据可用性审计：确认每个指标依赖的 DB 字段非空（workhour.budget、qc_score、task_due_date 等），字段缺失的指标标记"待补数据"
  - _Requirements: 2.2, 4.2_

### P1：三类高频角色入口

- [ ] P1-1. RoleWorkbenchFacade 最小版
  - [ ] P1-1.1 新建 `backend/app/services/role_workbench_facade.py`
  - [ ] P1-1.2 聚合 `my_todo_service`、`dashboard_aggregator_service`、`review_conversation_service`
  - [ ] P1-1.3 聚合 stale、AI 未确认、资料缺口
  - [ ] P1-1.4 API：`GET /api/projects/{pid}/role-workbench`
  - [ ] P1-1.5 pytest：auditor/manager/partner 返回区块不同
  - [ ] P1-1.6 所有 item 必须包含 `route` 或 `missing_reason`
  - _Requirements: 1.1, 2.1, 4.1_

- [ ] P1-2. RoleWorkbenchShell 前端
  - [ ] P1-2.1 新建 `views/RoleWorkbench.vue`
  - [ ] P1-2.2 新建 `components/dashboard/RoleWorkbenchShell.vue`
  - [ ] P1-2.3 按 role 渲染区块
  - [ ] P1-2.4 接入 ProjectContext 和 PermissionMatrix
  - _Requirements: 1.1, 2.1, 4.1_

- [ ] P1-3. 审计助理作业台
  - [ ] P1-3.1 聚合今日待办、被退回复核、即将截止、资料缺口、AI 建议
  - [ ] P1-3.2 每项待办返回 route / missing reason
  - [ ] P1-3.3 接入底稿、附件、复核、任务树定位
  - [ ] P1-3.4 UAT：助理从待办直接进入底稿单元格或复核意见
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] P1-4. 项目经理经营驾驶舱
  - [ ] P1-4.1 四象限：进度、质量、预算、风险
  - [ ] P1-4.2 接入工时预算消耗率和人员负荷
  - [ ] P1-4.3 接入复核 Aging 和质量分
  - [ ] P1-4.4 每个红色指标支持下钻
  - [ ] P1-4.5 如工时预算口径不足，先补 `workhour_service` 聚合方法
  - [ ] P1-4.6 UAT：经理定位逾期复核意见与责任人
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] P1-5. 合伙人签发风险雷达
  - [ ] P1-5.1 聚合重大事项、关键调整、未关闭复核、AI 未确认内容
  - [ ] P1-5.2 接入 stale/conflict/交付件缺失阻断项
  - [ ] P1-5.3 每个阻断项支持跳转
  - [ ] P1-5.4 合伙人确认 warning 项写审计日志
  - _Requirements: 4.1, 4.2, 4.3_

### P2：QC、EQCR 与问题沉淀

- [ ] P2-1. 质控闭环工作台
  - [ ] P2-1.1 聚合 QC 规则命中、抽查任务、问题整改、质量趋势
  - [ ] P2-1.2 QC 问题关联底稿、单元格、附件、复核记录
  - [ ] P2-1.3 问题状态流：identified/assigned/responded/verified/closed
  - [ ] P2-1.4 关闭问题必须填写依据或 EvidenceRef
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] P2-2. EQCR 独立复核工作台
  - [ ] P2-2.1 聚合 KAM、重大估计、持续经营、关联方、集团范围、重大调整
  - [ ] P2-2.2 区分普通复核与 EQCR 批注
  - [ ] P2-2.3 建立 EQCR checklist
  - [ ] P2-2.4 EQCR 签出要求 checklist 完成
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] P2-3. 质量问题类型库
  - [ ] P2-3.1 先出 ADR：问题类型用配置文件还是新表
  - [ ] P2-3.2 如需新表，编写 Vxxx migration + rollback
  - [ ] P2-3.3 同步 ORM、Pydantic schema、service
  - [ ] P2-3.4 编写三层一致契约测试
  - [ ] P2-3.5 定义问题类型配置：程序遗漏、证据不足、金额不一致、回复不充分等
  - [ ] P2-3.6 复核/QC 问题支持归类
  - [ ] P2-3.7 统计重复问题
  - [ ] P2-3.8 导出培训材料候选清单
  - _Requirements: 6.1, 6.2_

### 验收与回归

- [ ] UAT-1 助理：从作业台处理一条退回复核
- [ ] UAT-2 经理：从驾驶舱定位超预算与复核逾期
- [ ] UAT-3 QC：创建并关闭一条带证据链的问题
- [ ] UAT-4 合伙人：签发雷达定位阻断项并确认 warning
- [ ] UAT-5 EQCR：完成 checklist 并签出
- [ ] CI-1 facade pytest 覆盖 5 类角色
- [ ] CI-2 workbench Vitest 渲染测试通过
