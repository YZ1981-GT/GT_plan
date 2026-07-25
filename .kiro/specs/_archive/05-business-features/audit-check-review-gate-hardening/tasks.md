# Implementation Plan

## Overview

把「审计检查」升级为「聚合运行时校验源的复核收口面板」。按 M0→M3 分阶段：M0 后端可算聚合骨架 + summary + 新鲜度 + 通过率口径；M1 展示 + 定位；M2 更多真源 + 前端上报（G 循环 + 审定表试点）；M3 收口（导出 + 签认 + 权限）。

**关键约束**：
- 后端可算真源（S1-S5）由 `AuditCheckAggregator` 算并写；前端 composable 真源（S6）经 `report` 端点上报，二者写同一 `parsed_data.audit_checks`，`summary` 一处读。
- 复用既有服务判定口径（`cycle_review_context`/`d2_review_context`/`NoteValidationEngine`/`QCEngine`/`UnadjustedMisstatementService`），**不新造第二套判定**。
- `audit_checks` 新字段与 legacy `fine_checks`/`fine_summary`/`fine_extracted_at` **并存零回归**，QC-27/28、`fine-extract` 语义不动。
- S6 首版仅在 G 循环（`useReportCrossCheck`）+ 若干审定表（`tbReconcile`/`adjustmentReconcile`）试点，其余循环由「未覆盖」口径如实呈现，后续增量。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "desc": "安全网 + 统一模型/骨架" },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"], "desc": "M0 后端可算聚合 + summary + 新鲜度 + 口径 + PBT" },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "desc": "M1 面板展示 + 重算 + 定位/筛选/循环补M" },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3", "4.4"], "desc": "M2 更多真源 + report 上报端点 + G循环/审定表试点 + PBT" },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3", "5.4"], "desc": "M3 V126签认 + 导出 + 权限 + 前端收口" },
    { "wave": 5, "tasks": ["6.1", "6.2", "6.3"], "desc": "零回归门 + 全量测试 + Playwright(可选)" }
  ]
}
```

## Tasks

- [x] 1. 安全网 + 统一检查项模型与聚合器骨架
- [x] 1.1 建立零回归 characterization 基线
  - 为 legacy `fine_checks`/`fine_summary`/`fine_extracted_at` 的读取路径、`GET /fine-checks/summary`、QC-27/QC-28（`FineCheckBlockingRule`/`FineCheckWarningRule`）、`POST .../fine-extract` 语义各写 characterization 测试，锁定当前行为作为零回归基线
  - _Requirements: 10.2, 10.3, 10.4_

- [x] 1.2 `AuditCheckItem` 模型 + `audit_check` 服务包骨架
  - 新建 `app/services/audit_check/models.py`（`AuditCheckItem` dataclass + `ProjectCheckSummary` + source 枚举）与 `aggregator.py` 空骨架（`recompute_workpaper`/`recompute_project` 签名 + fail-open 结构）
  - `AuditCheckItem` 字段与 legacy `fine_checks` 项字段超集兼容（供前端统一渲染）
  - _Requirements: 4.4, 4.5_

- [x] 2. M0 — 后端可算聚合 + summary + 新鲜度 + 通过率口径
- [x] 2.1 `cycle_review_context` / `d2_review_context` 新增结构化产出
  - 在 `cycle_review_context.py` 新增 `build_cycle_reconciliation_findings(wp_id, wp_code) -> list[dict]`，与现有文本版**共用同一 `_REGISTRY` 与计算**，返回结构化 `{code,passed,actual,expected,diff,message,severity,check_type}`（审定↔明细、审定↔TB、未审→审定幅度[info]）；文本版改为调用它再格式化，保证单一判定口径
  - `d2_review_context` 同款新增结构化产出
  - 单测：结构化产出与文本版口径一致（同数据同判定）
  - _Requirements: 4.2, 3.1, 3.2_

- [x] 2.2 `AuditCheckAggregator` 落地 S1 + S2 + 去重 + 写缓存
  - `recompute_workpaper`：S1 把 `parsed_data.fine_checks` 归并为 `source=fine_rule` 项（补 `wp_code`/`produced_at=fine_extracted_at`）；S2 调 2.1 结构化产出转 `AuditCheckItem`；合并去重（同 `(wp_code, 勾稽语义)` 优先级 `cycle_recon > fine_rule`）；写 `parsed_data.audit_checks`/`audit_checks_at`（不改其他字段）
  - `recompute_project`：遍历底稿逐张 `recompute_workpaper`
  - 每来源独立 try/except fail-open，异常来源相关项标 `passed=null`
  - _Requirements: 3.1, 3.3, 3.4, 4.1, 4.3, 4.5_

- [x] 2.3 `GET /api/projects/{pid}/audit-checks/summary` 端点
  - 新建 `app/routers/audit_check.py`；读合并 `audit_checks`（无则退回 legacy `fine_checks` 补 `source=fine_rule` — 向后兼容）；每底稿返回 `checked_at`/`updated_at`/`stale`/`never_checked`；项目汇总 `ProjectCheckSummary`（`decided`/`passed`/`failed`/`uncovered`/`pass_rate`[分母=decided，不含 null]/`blocking_open`）；注册到 router_registry；项目只读权限
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 5.1, 5.2, 5.3, 5.4, 10.1, 10.4_

- [x] 2.4 M0 通过率/新鲜度/兼容 PBT
  - hypothesis（max_examples=5）：P1（通过率分母不含 null）、P2（uncovered>0 不输出全绿结论）、P3（stale 单调 + never_checked）、P4（未检查底稿不计通过率）、P5（同一勾稽去重至多一条）、P13（无 audit_checks 退回 fine_checks 不报错）
  - _Requirements: 5.2, 5.4, 1.2, 1.3, 4.3, 10.4_

- [x] 2.5 summary 契约与权限测试
  - 契约：summary 汇总字段齐全（decided/passed/failed/uncovered/pass_rate/blocking_open）+ 每底稿新鲜度字段齐全；权限：summary 仅需项目只读，不放宽
  - _Requirements: 1.4, 5.1, 10.1_

- [x] 3. M1 — 面板展示 + 主动重算 + 定位/筛选/循环覆盖
- [x] 3.1 `AuditCheckDashboard.vue` 数据源与口径改造
  - 数据源改 `GET /audit-checks/summary`；汇总卡增「未覆盖」列 + 「已判定通过率」（分母不含 null）；每底稿显示 `checked_at` + 陈旧/未检查 tag；每 check 行显示 `source` 来源芯片
  - `CYCLE_NAMES` 补 `M: '权益循环'`；无数据循环显式「暂无检查数据」
  - _Requirements: 1.1, 1.2, 1.3, 5.2, 5.3, 5.4, 4.4, 9.1, 9.3_

- [x] 3.2 `POST /audit-checks/recompute` 端点 + 前端重算入口
  - 端点：触发 `AuditCheckAggregator`（可选 body `wp_id` 单张），并发去重/幂等保护，编制权限；单底稿失败不阻断其余并如实标记失败原因
  - 前端「重新检查全部」+ 每底稿「重新检查」按钮（进行中禁重复，完成刷新）；无权限隐藏/禁用
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 8.2_

- [x] 3.3 未通过项定位跳转 + 筛选 + 置顶 + 依赖图循环
  - 点击未通过 check → `router.push` + `?sheet={sheet_hint}` 跳转底稿（复用 `GtWpRenderer initial-sheet`）；无 `sheet_hint` 不可跳并提示
  - 筛选（全部/未通过/未覆盖/阻断）+ 未通过与阻断项默认置顶
  - 依赖图循环列表改由实际有数据循环动态生成（含 M）
  - _Requirements: 6.1, 6.2, 6.3, 9.2_

- [x] 4. M2 — 聚合更多真源 + 前端上报（G循环 + 审定表试点）
- [x] 4.1 聚合器接入 S3/S4/S5（项目级真源）
  - S3：`NoteValidationEngine.validate_all(project_id, year)` findings → check（skip → `passed=null`）；S4：`QCEngine` findings → check（severity 对齐，含 QC-27/28）；S5：`UnadjustedMisstatementService.list_misstatements` 有错报 → warning 提示项；项目级来源归 `wp_code="__PROJECT__"` 分组
  - 每来源 fail-open
  - _Requirements: 4.1, 4.2, 4.4, 4.5_

- [x] 4.2 `POST .../workpapers/{wp_id}/audit-checks/report` 上报端点
  - 按 `source` 命名空间 upsert（同 source 重报覆盖不累积）；`recompute` 只清后端自算 source（S1-S5）不清上报 source（S6）；校验 `source ∈ 前端可上报枚举`（tb_recon/adjustment_recon/report_cross_check/cross_sheet），拒绝伪造后端专属 source（400）；编制权限
  - _Requirements: 3.1, 3.3, 4.1_

- [x] 4.3 `useAuditCheckReport` + G循环/审定表试点上报
  - 前端 `composables/useAuditCheckReport.ts`（`reportAuditChecks(pid, wpId, items)`，items 由底稿现有 composable 判定映射，source 明确不新造判定）
  - G 循环底稿接 `useReportCrossCheck` 结果上报（source=report_cross_check）；若干审定表接 `tbReconcile`/`adjustmentReconcile` 上报（source=tb_recon/adjustment_recon），保存成功后上报
  - _Requirements: 3.1, 3.3, 4.1_

- [x] 4.4 M2 上报/fail-open PBT + 去重优先级单测
  - PBT：P6（同 source 重报覆盖幂等 + recompute 不清 S6）、P7（随机来源抛异常不影响其余，异常来源标 null）；单测：去重优先级 cycle_recon > fine_rule
  - _Requirements: 4.1, 4.3, 4.5, 3.3_

- [x] 5. M3 — 收口（签认 + 导出 + 权限）
- [x] 5.1 V126 `audit_check_signoff` 迁移 + ORM
  - 执行前以磁盘实际最高迁移号 +1 取号（当前假定 V126，磁盘现最高 V125）；`CREATE TABLE IF NOT EXISTS` 幂等 + 索引；ORM 模型同步；`SchemaDriftDetector` drift=0
  - _Requirements: 8.2_

- [x] 5.2 签认端点 + 前端签认入口（只提示不阻断）
  - `POST .../audit-checks/signoff`：记 `signed_by`/`signed_at`/`summary_snapshot`（与当时 summary 一致）/`blocking_present`；有未处理阻断项时响应标记但**仍成功**（不拒绝）；`GET` 读最近一次；复核权限
  - 前端签认按钮：有阻断项弹提示确认（不阻断）；无权限隐藏/禁用
  - PBT/单测：P10（快照一致）、P14（有阻断仍可签认）
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 5.3 `POST .../audit-checks/export` 导出留痕
  - 后端生成 xlsx（每底稿检查项：编号/描述/来源/severity/判定/消息 + 汇总统计 + 导出时间），中文名 RFC5987；前端「导出」按钮；无数据导出空模板不报错；导出权限
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 5.4 端点权限全面校验（零回归）
  - summary/signoff-GET 项目只读；recompute/report/export/signoff-POST 按对应角色；契约测试覆盖权限矩阵；确认不放宽既有授权
  - _Requirements: 10.1, 2.5, 7.4, 8.4_

- [x] 6. 验证与收尾
- [x] 6.1 零回归门
  - 确认 legacy `fine_checks`/`fine_summary`/`fine_extracted_at` 读取路径、QC-27/28 门禁、`fine-extract` Excel/OnlyOffice 语义与基线（1.1）逐字节不变
  - _Requirements: 10.2, 10.3, 10.4_

- [x] 6.2 全量测试门 + Property 覆盖核对
  - 后端 audit_check 全套 + 相关既有套件绿；前端相关 vitest 绿；核对 P1-P14 均有测试覆盖；get_diagnostics 全清 + 改动前端文件 Vite transform 200
  - _Requirements: 全部_

- [x]* 6.3 Playwright 端到端（可选，需实例化项目）
  - 面板加载 → 重新检查 → 未覆盖口径展示 → 点击未通过项跳转定位 → 导出 → 签认（有阻断项提示不阻断）
  - _Requirements: 1.1, 2.1, 5.3, 6.1, 7.1, 8.3_

## Notes

- **迁移取号**：W4/5.1 执行前必以 `migration_status` / 磁盘实际最高号复核，当前假定 V126（磁盘现最高 V125，`balance-import-annual-column-semantics` spec 亦声明 V125 但未实现，须避冲突）。
- **零回归红线**：不改 `fine-extract` 对 Excel/OnlyOffice 的提取语义；不改 QC-27/28 提交门禁；`audit_checks` 与 legacy `fine_checks` 并存。
- **S6 边界**：首版仅 G 循环 + 审定表试点上报，其余循环前端勾稽由「未覆盖」口径如实呈现，不假装通过；后续增量按循环铺开。
- **单一判定口径**：S2 结构化产出与 `cycle_review_context` 文本版共用 `_REGISTRY`，AI 复核与审计检查面板同源，杜绝第三套口径。
- **可选任务**：6.3 需实例化项目 + vLLM/服务在线，按条件执行。
