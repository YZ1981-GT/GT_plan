# 需求：公式管理阻断缺陷收口（formula-hub-release-blockers）

> 母 spec：`formula-hub-integrity-closure`（48/54）。本 spec 收口第六轮（2026-11-01）全面评估发现的
> **P0 阻断缺陷**——不修则公式管理在真实共享库上"返回成功但实际未落库""显示最新但实际过期""界面可点但必失败"。

## R1　冲突确认事务完整性

- R1.1 `POST /api/projects/{pid}/formula-settings/pending/resolve` 必须在
  `resolve_items` + `record_changes` 之后执行 `commit` 和 `publish_pending`，
  与同一路由文件内的 `save_overrides`、`restore_global`、`apply` 三个端点行为一致。
- R1.2 现有端点测试 `test_pending_read_resolve_permissions` 必须恢复绿色：
  第二次同 revision 提交应返回 409。
- R1.3 前端 `FormulaPendingSyncDialog` 加载失败时必须显示错误态，而非静默把
  `items` 置空（否则角标消失，用户以为没有待确认）。

## R2　共享库 schema 对齐

- R2.1 V246、V248、V251 按依赖顺序在共享库安全执行（V246 含
  `report_generation_run` 表和 `financial_report.run_id/provenance`，
  V248 含 `formula_push_state.provenance`，V251 重复建相同表但添加了
  financial_report 外键——两者幂等收敛即可）。
- R2.2 执行前备份受影响表；执行后 `MigrationRunner.inspect_readiness`
  的 `is_complete` 与 `critical_count` 均为 0。
- R2.3 共享库 2935 条报表行的 `calc_version` 仍保持 NULL（不批量回填），
  由下一次各项目正常报表生成或 stale 重算按正确计算版本逐项目写入。

## R3　项目与主模板比对修复

- R3.1 `FormulaManagerDialog.vue` 中被未闭合 `/**` 吞掉的
  `loadMasterDiff()` 恢复可执行。
- R3.2 现有守卫 `formulaManagerMasterDiff.spec.ts` 恢复绿色。

## R4　报表过期判据修复

- R4.1 `report_freshness.row_status()` 当 `definition_hash` 参数不为 None
  且检测到 hash 漂移时，返回值的 `is_stale` 必须为 True。
- R4.2 补一条仅覆盖 `definition_hash` 分支的单测，用真实 `row_status` 函数
  而非 mock 调用。

## R5　项目报表删除 CAS 修复

- R5.1 `legacy_report.delete_row()` 对 `project:{id}` 行调用
  `restore_global` 时，必须传入调用方提供的 `expected_version`
  （当前为 `None`，绕过了 CAS）。

## R6　底稿新增公式落库

- R6.1 `FormulaManagerDialog.onFormulaEditSave` 的 `_isNew` 分支对
  `dispatch === 'wp'` 必须走 `wpFormula.upsert` 落库，而非无条件 return。

## R7　旧 Excel 导入下线

- R7.1 旧"📥 Excel导入"按钮要么移除，要么跳转到现有可用的公式包导入入口。
  当前引用的 `save_formula_batch` 在全仓不存在。

## R8　历史回滚角色对齐

- R8.1 前端 `ROLLBACK_ROLES` 与后端 `require_role` 参数集合必须完全一致。
  `signing_partner` 如果后端不认，前端也不能显示按钮。
  如果产品要求 `signing_partner` 可回滚，则后端 `require_role` 要同步加入。
- R8.2 现有守卫 `formulaHistoryRollbackGate.spec.ts` 不得人为豁免差异。

## R9　只读页面能力传递

- R9.1 TrialBalance、ReportView、DisclosureEditor 挂载
  `FormulaManagerDialog` 时，必须基于项目能力传入 `:read-only`。

## R10　调试面板作用域

- R10.1 `FormulaEditDialog` 的 `FormulaDebugPanel` 必须传入当前实际域
  （`scope` prop），不能固定 `"report"`。

## R11　时间线年度过滤

- R11.1 `_audit_log_events` 必须按 `payload->>'year'` 过滤，
  使 `/formula-timeline/{project}/{year}` 只返回指定年度的公式变更。

## 范围外（本 spec 不做）

- tb_detail 后端执行消费方接线
- 统一 strict 执行结果协议
- 旧 wp_cross_check_service 退役
- 全域来源信封补齐与 V246/V248/V251 以外的新迁移
- 公式模板双项目 UAT
- 全局—模板—项目统一发布编排器
- 审计批次改逐 slot 子记录
- 并发优化与 6000 并发验收
