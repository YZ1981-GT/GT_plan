# 附录 A：数据表清单（按业务域）

> 由脚本从代码静态抽取生成，不连数据库。生产库的实际表以 `information_schema` 现查为准。
> 「来源」：orm = `backend/app/models` 里有 ORM 模型；mig = 迁移脚本 `backend/migrations/V*.sql` 里有建表语句；
> 两者都有记 orm+mig。「写入方」= 静态扫描到对该表做 INSERT/UPDATE/DELETE 或构造 ORM 对象的代码文件（前 3 个，路径省略 `backend/app/`）；
> 扫不到写入方的表不一定没人写（可能经通用函数写入），需要人工核对。

| 业务域 | 表数 | 带 project_id | 静态扫不到写入方 |
|---|---:|---:|---:|
| D01 用户、组织与权限 | 20 | 8 | 1 |
| D02 项目与项目管理 | 27 | 20 | 14 |
| D03 账表导入与数据集 | 16 | 15 | 5 |
| D04 科目映射与试算表 | 13 | 9 | 0 |
| D05 调整分录与错报 | 11 | 9 | 2 |
| D06 报表、审计报告与交付件 | 21 | 13 | 0 |
| D07 附注 | 15 | 7 | 0 |
| D08 公式、取数与查询配置 | 21 | 13 | 0 |
| D09 底稿 | 60 | 34 | 15 |
| D10 底稿在线编辑同步（OnlyOffice） | 30 | 9 | 3 |
| D11 合并 | 36 | 28 | 5 |
| D12 附件、证据、函证与归档 | 47 | 32 | 13 |
| D13 复核、质控与签字门禁 | 29 | 18 | 3 |
| D14 AI 与知识库 | 33 | 15 | 12 |
| D15 后台任务、事件与系统基础设施 | 21 | 10 | 1 |
| 合计 | 400 | 240 | 74 |

已在迁移里删除的表（仍列出以便核对）：`consol_note_mapping_rule_template`, `consol_note_structure_lock`, `consol_note_structure_lock_entity`, `consol_note_value_confirmation`, `workpaper_editing_locks`

## D01 用户、组织与权限（20 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `annual_independence_declarations` | 年度独立性声明（R5 需求 12）+ 项目级独立性声明（R1 需求 10 合并）。 | `projects`、`users` | orm+mig | 1 / `services/eqcr_independence_service.py` |
| `dispatch_records` | 分发记录 — 描述「哪条函证行被分发到了哪个下游底稿」 | `projects`、`users` | orm+mig | 2 / `services/dispatch_service.py`、`services/workpaper_sync/close_intent.py` |
| `handover_records` | 人员交接记录 | `users` | orm+mig | 1 / `services/handover_service.py` |
| `logs` | 操作日志 | `users` | orm | 9 / `core/audit_decorator.py`、`middleware/audit_log.py`、`middleware/audit_log_middleware.py` |
| `notifications` | 系统通知 | `users` | orm | 7 / `routers/notifications.py`、`services/adjustment_hall_notify.py`、`services/assignment_service.py` |
| `partner_rotation_overrides` | 合伙人轮换 Override | `users` | orm+mig | 1 / `routers/rotation.py` |
| `project_assignments` | 项目团队委派 | `projects`、`staff_members`、`users` | orm | 2 / `services/assignment_service.py`、`services/handover_service.py` |
| `project_creation_grants` | admin 授予 manager 对一个精确 USCC 的项目创建权。 | `users` | orm+mig | 1 / `services/project_creation_grant_service.py` |
| `project_user_level_backfill` |  | — | mig | 未扫到 |
| `project_users` | 项目成员关联 | `projects`、`users` | orm | 3 / `services/assignment_service.py`、`services/continuous_audit_service.py`、`services/staff_account_binding_service.py` |
| `staff_members` | 全局人员库 | `users` | orm | 3 / `routers/staff.py`、`services/staff_account_binding_service.py`、`services/staff_service.py` |
| `sys_dept` | 部门组织架构 | `users` | orm+mig | 1 / `routers/departments.py` |
| `sys_role` | 角色（数据权限维度）。 | — | orm+mig | 1 / `services/role_service.py` |
| `sys_role_project` | 角色-自定义项目多对多（仅 data_scope=2 使用）。 | `projects`、`sys_role` | orm+mig | 1 / `services/role_service.py` |
| `sys_user_role` | 账号-角色多对多绑定。 | `sys_role`、`users` | orm+mig | 2 / `services/role_service.py`、`services/user_role_service.py` |
| `temporary_grants` | 临时授权记录 | — | orm+mig | 1 / `services/temporary_grant_service.py` |
| `user_display_preferences` | 账号级显示偏好（一对一，user_id 主键）。 | `users` | orm+mig | 1 / `services/user_display_preferences_service.py` |
| `users` | 系统用户 | — | orm | 1 / `services/auth_service.py` |
| `work_hour_entries` | 工时填报条目（三级粒度） | `projects`、`users` | orm+mig | 4 / `routers/workhour_entries.py`、`routers/workhours.py`、`services/work_hour_auto_collector.py` |
| `work_hours` | 工时记录 — DEPRECATED: V117 迁移后由 work_hour_entries 替代。 | `projects`、`staff_members`、`users` | orm | 3 / `routers/eqcr/time_tracking.py`、`routers/workhours.py`、`services/workhour_service.py` |

## D02 项目与项目管理（27 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `audit_findings` |  | `projects`、`users` | orm | 未扫到 |
| `audit_plans` |  | `projects`、`users` | orm | 1 / `services/b60_plan_service.py` |
| `audit_procedures` |  | `projects`、`users` | orm | 未扫到 |
| `budget_hours` | 预算工时 | `projects` | orm | 未扫到 |
| `check_ins` |  | `staff_members` | orm | 1 / `routers/report_trace.py` |
| `forum_comments` |  | `forum_posts`、`users` | orm | 1 / `services/forum_service.py` |
| `forum_posts` |  | `users` | orm | 1 / `services/forum_service.py` |
| `going_concern_evaluations` |  | `projects`、`users` | orm | 未扫到 |
| `going_concern_indicators` |  | `going_concern_evaluations` | orm | 未扫到 |
| `interim_survival_checks` |  | `projects` | orm+mig | 1 / `services/interim_survival.py` |
| `issue_tickets` | 统一问题单（对齐 v2 4.5.15A） | — | orm | 10 / `routers/eqcr_issues.py`、`services/event_handlers_cycle_linkage.py`、`services/handover_service.py` |
| `management_letters` |  | `projects`、`users` | orm | 未扫到 |
| `pbc_checklist` | PBC 清单项 | `projects`、`users` | orm | 1 / `services/pbc_service.py` |
| `project_batch_import_plans` | 一次上传产生的规范化计划、预览与可重放最终回执。 | `users` | orm+mig | 1 / `services/batch_project_execution.py` |
| `project_classification_v219_backup` |  | — | mig | 未扫到 |
| `project_sync` | 项目同步状态 | `projects`、`users` | orm | 未扫到 |
| `project_timeline` | 项目时间线/里程碑 | `projects` | orm | 未扫到 |
| `projects` | 审计项目 | `accounting_standards`、`users` | orm | 9 / `services/acnr/project_registry_lock.py`、`services/consol_enhanced_service.py`、`services/continuous_audit_service.py` |
| `related_party_registry` | 关联方主数据（项目级）。 | `projects` | orm | 1 / `routers/eqcr/related_parties.py` |
| `related_party_transactions` | 关联方交易明细。 | `projects`、`related_party_registry` | orm | 2 / `routers/eqcr/related_parties.py`、`services/related_party_disclosure_adapter.py` |
| `risk_assessments` |  | `projects`、`users` | orm | 未扫到 |
| `risk_matrix_records` |  | `projects` | orm | 未扫到 |
| `se_checklist` |  | `projects`、`users` | orm | 未扫到 |
| `subsequent_events` |  | `projects`、`users` | orm | 1 / `routers/subsequent_events.py` |
| `sync_logs` | 同步日志 | `projects`、`users` | orm | 未扫到 |
| `task_events` | 事件总线与补偿队列 | — | orm | 4 / `core/events/adapters.py`、`services/procedure_delivery_dispatcher.py`、`services/procedure_task_transition_service.py` |
| `task_tree_nodes` | 四级任务树节点：unit/account/workpaper/evidence | — | orm | 未扫到 |

## D03 账表导入与数据集（16 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `activation_records` | 激活/回滚操作留痕 | `ledger_datasets`、`projects`、`users` | orm | 2 / `routers/dataset_force_unbind.py`、`services/dataset_service.py` |
| `direction_override` | 方向覆盖 overlay 表 — 用户确认/修正方向时记录，不改写原始四表导入行。 | `projects`、`staff_members` | orm+mig | 未扫到 |
| `event_outbox_dlq` | 事件广播死信队列（F45）。 | `import_event_outbox`、`projects`、`users` | orm+mig | 1 / `services/import_event_outbox_service.py` |
| `import_artifacts` | 上传产物 — 平台级文件引用 | `projects`、`users` | orm | 3 / `services/import_artifact_service.py`、`services/ledger_import/orchestrator.py`、`services/ledger_import/retention_policy.py` |
| `import_batches` | 导入批次 | `projects`、`users` | orm | 6 / `services/account_chart_service.py`、`services/import_queue_service.py`、`services/import_service.py` |
| `import_column_mapping_history` | 列映射历史记录（F52 / Sprint 8.34 扩展版）。 | `projects` | orm | 1 / `services/ledger_import/column_mapping_service.py` |
| `import_event_consumptions` | 事件消费幂等记录。 | `projects` | orm | 3 / `services/event_handlers/_impl.py`、`services/import_event_consumption_service.py`、`services/workpaper_sync/outbox.py` |
| `import_event_outbox` | 导入域事件 outbox。 | `projects` | orm | 2 / `services/import_event_outbox_service.py`、`services/workpaper_sync/outbox.py` |
| `import_jobs` | 导入作业 — 关注任务执行过程 | `import_artifacts`、`projects`、`users` | orm | 3 / `services/import_job_runner.py`、`services/import_job_service.py`、`services/ledger_import/orchestrator.py` |
| `ledger_datasets` | 业务级数据集版本 | `import_jobs`、`projects`、`users` | orm | 2 / `services/dataset_service.py`、`services/ledger_import/retention_policy.py` |
| `ledger_import_attempts` | 一次账套导入 attempt 的最小不可变合同与状态记录。 | `ledger_datasets`、`projects`、`users` | orm+mig | 1 / `services/ledger_import/attempt_service.py` |
| `tb_aux_balance` | 辅助余额表 | `import_batches`、`projects` | orm | 未扫到 |
| `tb_aux_balance_summary` |  | — | mig | 1 / `services/smart_import_engine.py` |
| `tb_aux_ledger` | 辅助明细账 — 按 year 分区 | `import_batches`、`projects` | orm | 未扫到 |
| `tb_balance` | 科目余额表 | `import_batches`、`projects` | orm | 未扫到 |
| `tb_ledger` | 序时账（总账明细）— 按 year 分区 | `import_batches`、`projects` | orm | 未扫到 |

## D04 科目映射与试算表（13 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `account_chart` | 科目表（标准科目 + 客户科目） | `projects` | orm | 4 / `routers/report_line_mapping.py`、`services/account_chart_service.py`、`services/mapping_service.py` |
| `account_mapping` | 科目映射关系 | `projects`、`users` | orm | 2 / `services/continuous_audit_service.py`、`services/mapping_service.py` |
| `aging_segments` | 账龄段枚举配置（每个底稿一条，关联 wp_index_id） | `wp_index` | orm+mig | 3 / `routers/wp_render_strategies/_f1_import_export.py`、`services/aging_config_service.py`、`services/aging_segment_service.py` |
| `bad_debt_detail_rows` | 坏账准备明细表 D2-3 嵌套行（父行与子行统一存储） | `wp_index` | orm+mig | 2 / `services/aging_segment_service.py`、`services/bad_debt_nested_table_service.py` |
| `custom_account_packages` |  | — | mig | 1 / `services/custom_account_package_service.py` |
| `materiality` | 重要性水平 | `projects`、`users` | orm | 1 / `services/materiality_service.py` |
| `report_line_mapping` | 报表行次映射（标准科目→报表行次） | `projects`、`users` | orm | 3 / `routers/report_line_mapping.py`、`services/report_line_mapping_reference_copy.py`、`services/report_line_mapping_service.py` |
| `t_account_entries` | T型账户分录 | `t_accounts` | orm | 1 / `services/t_account_service.py` |
| `t_accounts` | T型账户 | `projects`、`users` | orm | 1 / `services/t_account_service.py` |
| `tb_change_history` |  | `projects`、`users` | orm+mig | 1 / `services/linkage_service.py` |
| `tb_publish_ack` | 审定表→试算表"发布"耐久确认/幂等表（对应迁移 V162）。 | — | orm+mig | 2 / `services/event_handlers_cycle_linkage.py`、`services/tb_publish_service.py` |
| `trial_balance` | 试算表（四列结构） | `projects` | orm | 12 / `services/adjustment_review_coordinator.py`、`services/continuous_audit_service.py`、`services/event_handlers_cycle_linkage.py` |
| `trial_balance_snapshots` | 试算平衡表版本快照 - 记录每次审定表变更时的试算表完整状态 | `projects` | orm+mig | 1 / `services/tb_snapshot_service.py` |

## D05 调整分录与错报（11 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `adjustment_client_bookings` | 客户已入账的追加式标记/撤销历史。 | `ledger_datasets`、`projects`、`users` | orm+mig | 1 / `services/adjustment_client_booking.py` |
| `adjustment_collaboration` | 调整分录协作记录（分录组级转派→知晓→补充→确认）。 | `projects`、`users` | orm+mig | 1 / `services/adjustment_collaboration_service.py` |
| `adjustment_collaboration_event` | 协作历史事件（append-only，仅 INSERT）。 | `adjustment_collaboration`、`users` | orm+mig | 1 / `services/adjustment_collaboration_service.py` |
| `adjustment_editing_locks` |  | `projects`、`users` | orm+mig | 1 / `services/conflict_guard_service.py` |
| `adjustment_entries` | 调整分录明细行（独立于 adjustments 头表） | `adjustments` | orm | 2 / `routers/recycle_bin.py`、`services/adjustment_group_writer.py` |
| `adjustment_import_batches` |  | `projects`、`users` | orm+mig | 未扫到 |
| `adjustment_import_group_results` |  | `adjustment_import_batches`、`projects` | orm+mig | 未扫到 |
| `adjustment_review_tasks` | 一笔调整分录的一轮持久化复核任务。 | `projects`、`users` | orm+mig | 1 / `services/adjustment_review_task_service.py` |
| `adjustment_treatment_events` | 调整财务处理的追加式事件，不覆盖历史。 | `adjustment_client_bookings`、`ledger_datasets`、`projects`、`unadjusted_misstatements`、`users` | orm+mig | 1 / `services/adjustment_treatment_service.py` |
| `adjustments` | 审计调整分录（AJE / RJE） | `adjustment_import_batches`、`projects`、`users` | orm | 3 / `routers/recycle_bin.py`、`services/adjustment_group_writer.py`、`services/adjustment_import_service.py` |
| `unadjusted_misstatements` | 未更正错报汇总 | `adjustments`、`ledger_datasets`、`projects`、`users` | orm | 2 / `services/continuous_audit_service.py`、`services/misstatement_service.py` |

## D06 报表、审计报告与交付件（21 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `accounting_standards` | 会计准则 | — | orm | 1 / `services/accounting_standard_service.py` |
| `audit_report` | 审计报告 | `ledger_datasets`、`projects`、`users` | orm | 5 / `routers/deliverable.py`、`routers/wp_editor_router.py`、`services/audit_report_service.py` |
| `audit_report_template` | 审计报告段落模板 | — | orm | 2 / `services/audit_report_service.py`、`services/report_body_service.py` |
| `cf_verification_results` | CF 核查结果缓存 + 用户差异说明 | — | orm+mig | 1 / `services/cash_flow_verification_service.py` |
| `cfs_adjustments` | 现金流量表调整分录 | `projects`、`users` | orm | 1 / `services/cfs_worksheet_engine.py` |
| `deliverable_section_state` | 出品物章节级状态承载表（V067）。 | — | orm+mig | 4 / `services/deliverable_section_state_service.py`、`services/deliverable_service.py`、`services/deliverable_writeback_service.py` |
| `deliverable_snapshots` | 不可变交付快照。 | `projects` | orm+mig | 1 / `routers/deliverable.py` |
| `export_job_attempts` | 后台导出任务 attempt 历史。 | `export_job_items_v2`、`export_jobs_v2` | orm+mig | 2 / `services/export_job_service.py`、`services/full_deliverables_executor.py` |
| `export_job_items_v2` | 后台导出任务明细 | `export_jobs_v2`、`word_export_task` | orm | 3 / `services/deliverable_service.py`、`services/export_job_service.py`、`services/full_deliverables_executor.py` |
| `export_jobs_v2` | 后台导出任务（全套导出/批量渲染/重试/三件套） | `projects`、`users` | orm | 1 / `services/export_job_service.py` |
| `export_tasks` | PDF导出任务 | `projects`、`users` | orm | 2 / `services/export_progress_service.py`、`services/pdf_export_engine.py` |
| `fill_preview_sessions` | 报告正文模板填充 preview 会话（audit-report-template-integration V066） | `projects`、`users` | orm+mig | 1 / `services/template_fill_service.py` |
| `financial_report` | 生成的财务报表数据 | `projects`、`report_generation_run` | orm | 9 / `routers/reports.py`、`services/consol_report_service.py`、`services/event_handlers/_impl.py` |
| `regulatory_filing` | 监管备案 | `projects` | orm | 1 / `services/regulatory_service.py` |
| `report_config` | 报表格式配置（行次定义+取数公式）；V199 formula_version：全局行 = 定义版本、项目行 = 本地修订号（CAS） | — | orm | 4 / `services/event_handlers/_impl.py`、`services/formula_settings/effective_report.py`、`services/formula_settings/stores.py` |
| `report_config_baseline` | 报表配置主模板回填候选（项目优化→主模板评审通道） | — | orm+mig | 1 / `services/report_config_service.py` |
| `report_format_templates` |  | — | orm | 1 / `routers/report_trace.py` |
| `report_generation_run` | 一次报表计算的不可变运行摘要与规范行快照。 | `consol_operation`、`projects`、`users` | orm+mig | 2 / `services/consol_report_run_service.py`、`services/report_provenance.py` |
| `report_snapshot` | 报表数据快照（导出时从快照读取，不重复计算） | `projects`、`users` | orm | 1 / `services/report_snapshot_service.py` |
| `word_export_task` | Word导出主任务 | `projects`、`users` | orm | 3 / `services/batch_brief_service.py`、`services/deliverable_service.py`、`services/export_task_service.py` |
| `word_export_task_versions` | Word导出版本快照 | `users`、`word_export_task` | orm | 2 / `services/deliverable_service.py`、`services/export_task_service.py` |

## D07 附注（15 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `account_note_mapping` | 科目→附注行映射 — 维护科目名称到附注表格行的映射关系 | — | orm+mig | 1 / `routers/account_note_mapping.py` |
| `disclosure_notes` | 财务报表附注 | `ledger_datasets`、`projects`、`users`、`working_paper` | orm | 10 / `services/disclosure_engine.py`、`services/group_note_baseline_service.py`、`services/note_conversion_service.py` |
| `group_note_template_baseline` | 集团附注模板基线（D6） | `projects`、`users` | orm+mig | 1 / `services/group_note_baseline_service.py` |
| `group_note_templates` |  | — | mig | 1 / `services/note_group_template_service.py` |
| `note_account_mappings` | 附注科目对照映射 — 报表行次 → 附注章节 → 表格的三级映射 | — | orm+mig | 1 / `services/note_account_mapping_service.py` |
| `note_content_template_versions` | 模板的不可变正文快照。 | `note_content_templates`、`projects`、`users` | orm+mig | 1 / `services/note_content_template_snapshot.py` |
| `note_content_templates` | 个人或集团可见的附注内容模板目录。 | `note_content_template_versions`、`projects`、`users` | orm+mig | 1 / `services/note_content_template_snapshot.py` |
| `note_formula_run` | 一个章节一次附注公式执行的可查询运行记录。 | `projects`、`users` | orm+mig | 1 / `services/note_formula_provenance.py` |
| `note_section_instances` | 附注章节实例（裁剪后的章节） | `projects` | orm | 1 / `services/note_trim_service.py` |
| `note_section_locks` |  | — | mig | 1 / `services/note_section_lock_service.py` |
| `note_section_templates` |  | — | mig | 1 / `services/note_custom_section_service.py` |
| `note_section_version_tree` | 章节版本树（D11） | `projects`、`users` | orm+mig | 1 / `services/note_offline_import_governance.py` |
| `note_text_batch_applications` | 一次成功的附注正文原子批量应用审计。 | `note_content_template_versions`、`projects`、`users` | orm+mig | 1 / `services/note_text_batch_apply.py` |
| `note_trim_schemes` | 附注裁剪方案 | `projects`、`users` | orm | 2 / `services/continuous_audit_service.py`、`services/note_trim_service.py` |
| `note_validation_results` | 附注校验结果 | `projects`、`users` | orm | 1 / `services/note_validation_engine.py` |

## D08 公式、取数与查询配置（21 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `acnr_project_overlay` | ACNR L2 ProjectOverlay 持久化 — 项目级别名/CUST覆盖/binding。 | `projects`、`working_paper` | orm+mig | 1 / `services/acnr/overlay_repository.py` |
| `advanced_query_writeback` | 高级查询回写身份 / 审计记录表 [advanced-query-module Task 1.3] | — | orm+mig | 1 / `services/custom_query/snapshot_writer.py` |
| `config_references` | 配置引用记录——记录哪个项目引用了哪个模板 | `projects`、`shared_config_templates`、`users` | orm+mig | 1 / `services/shared_config_service.py` |
| `custom_query_templates` | 自定义查询模板。 | `users` | orm+mig | 1 / `services/custom_query/template_service.py` |
| `draft_marker` | 初稿标记（V100 formula-management-library）。 | — | orm+mig | 1 / `services/draft_refresh_service.py` |
| `draft_refresh_audit` | 初稿刷新审计留痕（append-only，V100 formula-management-library）。 | — | orm+mig | 2 / `services/draft_refresh_service.py`、`services/formula_management/cross_check_run.py` |
| `draft_refresh_snapshot` | 初稿刷新回滚快照（V100 formula-management-library）。 | `draft_refresh_audit` | orm+mig | 1 / `services/draft_refresh_service.py` |
| `enum_dict_overrides` | 枚举字典覆盖（label / color 可改，value 不可改） | — | orm+mig | 1 / `routers/system_dicts.py` |
| `formula_publish` | 发布记录。``status=pending`` 承载非 admin 提交的全局候选（admin 审核后执行）。 | — | orm+mig | 5 / `services/formula_settings/apply_ops.py`、`services/formula_settings/custom_presets.py`、`services/formula_settings/publish.py` |
| `formula_push_run` | 公式推送运行记录（面板「最近推送」）。 | `projects` | orm+mig | 3 / `services/formula_push/engine.py`、`services/formula_push/persistence.py`、`services/formula_push/state_store.py` |
| `formula_push_state` | 公式推送目标级状态。 | `formula_push_run`、`projects`、`working_paper` | orm+mig | 2 / `services/formula_push/persistence.py`、`services/formula_push/state_store.py` |
| `formula_runtime_outbox` | 公式运行时事务 Outbox — 与业务写入同事务提交，提交后可靠发布 stale/invalidation 事件。 | `draft_refresh_audit` | orm+mig | 1 / `services/formula_runtime/outbox.py` |
| `formula_setting` | 统一公式设置行：``layer`` = global（全局）/ project（本项目适配）/ template（模板）。 | `formula_template`、`projects` | orm+mig | 4 / `services/formula_settings/custom_presets.py`、`services/formula_settings/stores.py`、`services/formula_settings/template_service.py` |
| `formula_sync_item` | 待项目确认的同步事项。同一项目同一公式位只保留一条 pending（后续发布更新它）。 | `projects` | orm+mig | 2 / `services/formula_settings/pending.py`、`services/formula_settings/template_sync.py` |
| `formula_template` | 可共享的公式模板（名称 / 共享范围 / 适用准则 / 当前版本）。 | `projects`、`users` | orm+mig | 2 / `services/formula_settings/custom_presets.py`、`services/formula_settings/template_service.py` |
| `formula_template_subscription` | 项目订阅模板（每个项目每个域最多一个有效订阅）。 | `formula_template`、`projects` | orm+mig | 1 / `services/formula_settings/template_sync.py` |
| `formula_template_version` | 模板每次发布的冻结快照（三方比对、回看、暂缓订阅者读取）。 | `formula_template` | orm+mig | 2 / `services/formula_settings/template_service.py`、`services/formula_settings/template_sync.py` |
| `query_artifacts` | 一次「导出全部」生成的不可变查询证据清单。 | `projects`、`query_runs`、`users` | orm+mig | 2 / `services/custom_query/query_artifacts.py`、`workers/export_cleanup_worker.py` |
| `query_runs` | 一次查询定义在一个来源版本上的不可变运行记录。 | `projects`、`users` | orm+mig | 3 / `routers/query_evidence.py`、`services/custom_query/query_runs.py`、`workers/export_cleanup_worker.py` |
| `shared_config_templates` | 共享配置模板 | `projects`、`users` | orm+mig | 1 / `services/shared_config_service.py` |
| `wp_formula` | 自定义底稿公式绑定（独立表，custom-workpaper-formula-binding） | `projects`、`users`、`working_paper` | orm+mig | 3 / `services/draft_refresh_service.py`、`services/formula_settings/domain_stores.py`、`services/wp_formula_service.py` |

## D09 底稿（60 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `account_package_program_status` | 科目工作包程序状态 | `projects`、`staff_members` | orm+mig | 1 / `services/account_package_program_status_service.py` |
| `checklist_responses` |  | — | mig | 75 / `routers/a21_review.py`、`routers/checklist_responses.py`、`routers/d2_sync_router.py` |
| `custom_workbook_unit_authorities` |  | `users`、`working_paper` | orm+mig | 未扫到 |
| `editing_locks` | 通用编辑锁 | `users` | orm+mig | 1 / `services/editing_lock_service.py` |
| `gt_wp_coding` | 致同底稿编码 | — | orm | 1 / `services/gt_coding_service.py` |
| `guidance_consumer_ack` | durable、幂等的 ConsumerAck ledger 行。 | — | orm+mig | 1 / `services/guidance_handoff_consumer_service.py` |
| `guidance_exemption_record` | guidance 有效豁免记录。 | `projects` | orm+mig | 1 / `services/guidance_exemption_service.py` |
| `guidance_handoff_visibility` | finalize visibility saga 的 guidance 侧视图。 | — | orm+mig | 1 / `services/guidance_handoff_consumer_service.py` |
| `guidance_publication` | guidance 发布主体。 | — | orm+mig | 1 / `services/guidance_publication_service.py` |
| `guidance_publication_event` | 发布生命周期事件。 | `guidance_publication` | orm+mig | 1 / `services/guidance_publication_service.py` |
| `procedure_instance_identity_v217_backup` |  | — | mig | 未扫到 |
| `procedure_instances` | 审计程序实例（裁剪后的程序步骤） | `projects`、`staff_members` | orm | 4 / `routers/wp_relation_router.py`、`services/procedure_catalog.py`、`services/procedure_service.py` |
| `procedure_operation_previews` | 敏感操作 server-side 一次性预览凭证（裁剪/委派/转派）。 | `projects`、`users` | orm+mig | 1 / `services/procedure_operation_preview.py` |
| `procedure_row_definition_revisions` | Revision membership: 哪些 definition_key 属于 (template_code, revision_has | `procedure_row_definitions` | orm+mig | 未扫到 |
| `procedure_row_definitions` | 模板级程序行定义真源（跨项目稳定）。 | — | orm+mig | 3 / `services/procedure_definition_importer.py`、`services/procedure_row_definitions.py`、`services/procedure_row_trim_service.py` |
| `procedure_row_task_history` | 程序行任务追加式历史（不可覆盖）。 | `procedure_row_tasks`、`projects`、`staff_members`、`users` | orm+mig | 3 / `services/procedure_reconcile_service.py`、`services/procedure_task_transition_service.py`、`services/wp_visibility/delegation_transaction.py` |
| `procedure_row_tasks` | 项目级程序行任务真源（先委派后生成底稿）。 | `procedure_row_definitions`、`projects`、`staff_members`、`working_paper`、`wp_index` | orm+mig | 3 / `services/procedure_backfill_runner.py`、`services/procedure_row_trim_service.py`、`services/procedure_task_materialization_service.py` |
| `procedure_template_revisions` | Current-revision registry；每个 template_code 最多一个 active current。 | `users` | orm+mig | 未扫到 |
| `procedure_trim_cycle_confirmations` | 每项目每循环当前粗裁确认投影；历史真源仍是 consumed preview。 | `procedure_operation_previews`、`projects`、`users` | orm+mig | 未扫到 |
| `procedure_trim_schemes` | 审计程序裁剪方案 | `projects`、`users` | orm | 1 / `services/procedure_trim_service.py` |
| `project_guidance_supplement` | 项目级 guidance 补充。 | `guidance_publication`、`projects` | orm+mig | 1 / `services/project_guidance_supplement_service.py` |
| `project_template_selections` | 项目模板选择记录 | `projects`、`template_library`、`users` | orm+mig | 1 / `services/template_library_service.py` |
| `project_workbook_instance` |  | — | orm+mig | 未扫到 |
| `project_workbook_sheet_entry` |  | — | orm+mig | 未扫到 |
| `project_workpaper_sheet_override` | 项目级底稿 sheet 归类覆盖 | `projects`、`users` | orm+mig | 未扫到 |
| `sampled_vouchers` | 抽样凭证（抽凭联动） | `projects`、`users` | orm+mig | 1 / `routers/voucher_links.py` |
| `sampling_config` | 抽样配置 | `projects`、`users` | orm | 1 / `services/sampling_service.py` |
| `sampling_records` | 抽样记录 | `projects`、`sampling_config`、`users`、`working_paper` | orm | 2 / `services/sampling_registry_service.py`、`services/sampling_service.py` |
| `template_library` | 模板库条目 | `projects`、`users` | orm | 1 / `services/template_library_service.py` |
| `working_paper` | 底稿文件 | `ledger_datasets`、`projects`、`users`、`wp_index` | orm | 33 / `routers/wp_functional_actions.py`、`routers/wp_html_save.py`、`routers/wp_render_strategies/_f0_import_export.py` |
| `workpaper_delegation_history` | History_Set 唯一来源：append-only 委派历史快照。 | `procedure_row_tasks`、`projects`、`staff_members`、`users`、`working_paper`、`wp_index` | orm+mig | 1 / `services/wp_visibility/delegation_transaction.py` |
| `workpaper_editing_locks` |  | — | mig（已删） | 未扫到 |
| `workpaper_extraction_log` | 底稿提取日志 — 记录截止测试/抽凭引擎的执行留痕和填充前快照，支持撤销功能。 | `projects`、`working_paper` | orm+mig | 1 / `services/ledger_sampling_service.py` |
| `workpaper_field_overrides` | 统一字段覆盖值 | `users` | orm+mig | 2 / `routers/wp_procedure_tables.py`、`services/field_override_service.py` |
| `workpaper_generation_items` | 生成操作内的一份底稿及其可恢复文件 manifest。 | `workpaper_generation_operations` | orm+mig | 1 / `services/wp_generation_operation_service.py` |
| `workpaper_generation_operations` | 一次可恢复的底稿生成操作。 | `projects`、`users`、`wp_template_set` | orm+mig | 1 / `services/wp_generation_operation_service.py` |
| `workpaper_lifecycle_events` | 一张底稿（wp_index + 名下 working_paper）的一次移入 / 恢复回收站。 | `projects` | orm+mig | 1 / `services/workpaper_recycle_service.py` |
| `workpaper_procedures` | 审计程序清单 | `projects`、`working_paper` | orm+mig | 1 / `services/wp_procedure_service.py` |
| `workpaper_row_name_mapping` | 一行的行名对齐映射（版本行）。 | `users` | orm+mig | 1 / `services/row_name_mapping_service.py` |
| `workpaper_row_name_mapping_target` | 映射目标身份明细（让身份可 SQL 查询：判 stale / 多对一交集）。 | `workpaper_row_name_mapping` | orm+mig | 1 / `services/row_name_mapping_service.py` |
| `workpaper_sheet_classification` | 底稿 sheet 归类（9 类：A~I） | `workpaper_template_version` | orm+mig | 未扫到 |
| `workpaper_snapshots` | 底稿版本快照 — field-level 数据版本历史，支持时间线展示、diff 对比、回滚。 | `projects`、`working_paper` | orm+mig | 1 / `services/version_trail_service.py` |
| `workpaper_template_override_version` |  | — | mig | 未扫到 |
| `workpaper_template_version` | 底稿模板版本 | — | orm+mig | 未扫到 |
| `wp_access_security_outbox` | 内部安全审计发件箱（append-only）：保留真实拒绝原因，对外统一 404/429。 | `projects`、`users`、`working_paper`、`wp_index` | orm+mig | 1 / `services/wp_visibility/denial.py` |
| `wp_cross_ref` | 底稿交叉引用 | `projects`、`working_paper` | orm | 未扫到 |
| `wp_edit_sessions` | 底稿编辑时间采集（WOPI lock/unlock 自动记录）。 | `users`、`working_paper` | orm | 未扫到 |
| `wp_export_snapshot` | 底稿导出快照 — 记录每次导出时的内容哈希，用于导入冲突检测 | `projects`、`users`、`working_paper` | orm+mig | 1 / `services/wp_export/export_engine.py` |
| `wp_index` | 底稿索引 | `projects`、`users` | orm | 11 / `routers/procedures.py`、`routers/wp_template.py`、`routers/wp_template_copy_router.py` |
| `wp_migration_snapshots` |  | — | mig | 1 / `services/wp_migration_service.py` |
| `wp_recommendation_feedback` | 底稿推荐反馈记录（采纳/跳过/手动添加）。 | `projects`、`users` | orm | 未扫到 |
| `wp_sheet_locks` |  | — | mig | 1 / `services/wp_sheet_lock_service.py` |
| `wp_template` | 底稿模板 | `users` | orm | 1 / `services/template_engine.py` |
| `wp_template_custom` | 自定义底稿模板 | `users` | orm | 1 / `services/custom_template_service.py` |
| `wp_template_meta` | 模板元数据（命名区域定义） | `wp_template` | orm | 1 / `services/template_engine.py` |
| `wp_template_metadata` | 底稿模板元数据 | `wp_template` | orm+mig | 2 / `routers/template_library_mgmt.py`、`routers/wp_template_metadata.py` |
| `wp_template_set` | 底稿模板集 | — | orm | 2 / `services/builtin_template_sets.py`、`services/template_engine.py` |
| `wp_version_archive` | 底稿版本归档 — 记录版本元数据（文件可能已清理但元数据保留） | `projects`、`users`、`working_paper` | orm+mig | 1 / `services/wp_export/version_manager.py` |
| `wp_visibility_invalidation_outbox` | 可见性失效发件箱（append-only）：与 policy epoch 递增同事务写入。 | `projects`、`users` | orm+mig | 1 / `services/wp_visibility/delegation_transaction.py` |
| `wp_visibility_policy_epoch` | 每项目持久单调 policy epoch（可变；BEFORE UPDATE 触发器强制非递减）。 | `projects` | orm+mig | 1 / `services/wp_visibility/delegation_transaction.py` |

## D10 底稿在线编辑同步（OnlyOffice）（30 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `working_paper_artifact` | 内容寻址不可变文件登记表。 | `projects`、`working_paper`、`working_paper_callback_delivery`、`working_paper_sync_operation` | orm+mig | 3 / `services/workpaper_sync/artifacts.py`、`services/workpaper_sync/repository.py`、`services/workpaper_sync/retention.py` |
| `working_paper_callback_delivery` | 每次 callback 投递。归属只以 immutable `durable_at` 判定。 | `projects`、`working_paper`、`working_paper_artifact`、`working_paper_callback_recovery_case`、`working_paper_content_application`、`working_paper_forcesave_request`、`working_paper_oo_room`、`working_paper_sync_operation` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_callback_recovery_case` | 无法唯一归组的 durable incoming 的可审计恢复案例。claim 前三实体恒空。 | `projects`、`working_paper`、`working_paper_artifact`、`working_paper_content_application`、`working_paper_forcesave_request`、`working_paper_oo_client_confirmation`、`working_paper_oo_participant`、`working_paper_oo_room`、`working_paper_sync_definition_bundle`、`working_paper_sync_operation` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_callback_recovery_case_event` | recovery case 的独立 append-only timeline（与 operation timeline 分离）。 | `working_paper_callback_recovery_case`、`working_paper_oo_client_confirmation` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_content_application` | durable incoming 对业务状态的一次逻辑应用；`application_key` 的唯一 owner。 | `projects`、`working_paper`、`working_paper_artifact`、`working_paper_content_representation`、`working_paper_content_version`、`working_paper_forcesave_request`、`working_paper_oo_room`、`working_paper_sync_definition_artifact`、`working_paper_sync_definition_bundle` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_content_application_event` | application 的 append-only timeline（含 `sequence_folded` 审计）。 | `working_paper_content_application`、`working_paper_forcesave_request` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_content_representation` | 同一 content version 的 1:N immutable OOXML representation generation。 | `working_paper`、`working_paper_artifact`、`working_paper_content_version`、`working_paper_sync_definition_artifact`、`working_paper_sync_definition_bundle` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_content_revision_backfill_ledger` | V151 revision 0 回填台账：只记录，不创建 content version/representation。 | `projects`、`working_paper` | orm+mig | 未扫到 |
| `working_paper_content_version` | immutable 业务内容版本。`revision` 只因业务 projection/权威内容变化递增。 | `users`、`working_paper`、`working_paper_artifact`、`working_paper_sync_operation` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_entry_evidence_scenario` | 逐 scenario 证据行。download-only/recovery-reject 场景 operation/application  | `working_paper_artifact`、`working_paper_sync_test_run` | orm+mig | 1 / `services/workpaper_sync/pilot_harness.py` |
| `working_paper_forcesave_request` | Command Service 调用前冻结的 request。 | `working_paper_content_representation`、`working_paper_content_version`、`working_paper_oo_participant`、`working_paper_oo_room`、`working_paper_sync_definition_artifact`、`working_paper_sync_definition_bundle` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_oo_client_confirmation` | DocEditor `onDocumentReady` 后的 descriptor 逐项确认。 | `working_paper_content_representation`、`working_paper_content_version`、`working_paper_oo_participant`、`working_paper_oo_room`、`working_paper_sync_definition_bundle` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_oo_close_intent` | clean close intent；只有 reconciler 可把 deterministic leader CAS 提升为 close | `working_paper_forcesave_request`、`working_paper_oo_client_confirmation`、`working_paper_oo_participant`、`working_paper_oo_room` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_oo_close_intent_event` | close intent 的 append-only eligibility/leader timeline。 | `working_paper_oo_close_intent` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_oo_content_revision` |  | — | mig | 未扫到 |
| `working_paper_oo_participant` | 逐用户 participant lease。`closing` 是 close intent 创建时的原子中间态。 | `users`、`working_paper_oo_room` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_oo_room` | 共享 OO room：server last-applied 与 client-confirmed 是两套独立指针。 | `projects`、`working_paper`、`working_paper_content_application`、`working_paper_content_representation`、`working_paper_content_version`、`working_paper_oo_close_intent`、`working_paper_sync_definition_bundle` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_pending_mutation` | HTML flush 产生的短 TTL 单次逻辑消费 mutation token。 | `projects`、`users`、`working_paper`、`working_paper_artifact`、`working_paper_content_version`、`working_paper_sync_operation` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_representation_candidate_event` | candidate contract/bundle attach 的 append-only 审计事件（V153）。 | `users`、`working_paper_representation_upgrade_candidate`、`working_paper_sync_definition_artifact`、`working_paper_sync_definition_bundle` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_representation_upgrade_candidate` | non-current representation 升级候选：resolver/room/current pointer 均不得读取。 | `working_paper`、`working_paper_artifact`、`working_paper_content_representation`、`working_paper_content_version`、`working_paper_sync_definition_artifact`、`working_paper_sync_definition_bundle` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_sync_conflict` | 字段级冲突记录（双侧可追溯 + canonical application fence）。 | `users`、`working_paper_content_application`、`working_paper_sync_operation` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_sync_definition_artifact` | immutable template / instrumentation / contract / authority_model 定义快照 | `working_paper_artifact` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_sync_definition_bundle` | authority model + template/instrumentation/contract 三类 typed canonical | `working_paper_artifact`、`working_paper_sync_definition_artifact` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_sync_definition_null_marker` | optional child 的版本化 typed null marker registry（禁 SQL NULL/空串/全零 hash）。 | — | orm+mig | 未扫到 |
| `working_paper_sync_entry_state` | entry 级 current representation pointer（candidate 不可引用）。 | `working_paper`、`working_paper_content_representation` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_sync_operation` | 用户轮询/执行/timeline 容器；**不承担** application identity。 | `projects`、`users`、`working_paper`、`working_paper_content_application`、`working_paper_forcesave_request`、`working_paper_oo_participant`、`working_paper_oo_room`、`working_paper_sync_definition_artifact`、`working_paper_sync_definition_bundle` | orm+mig | 2 / `services/workpaper_sync/materialize_coordinator.py`、`services/workpaper_sync/repository.py` |
| `working_paper_sync_operation_contributor` | 聚合 callback 的 contributor 快照（initiator / route / contributor 三者分离）。 | `users`、`working_paper_oo_participant`、`working_paper_sync_operation` | orm+mig | 1 / `services/workpaper_sync/rooms.py` |
| `working_paper_sync_operation_event` | operation 的 append-only transition event（current state 只是它的投影）。 | `working_paper_sync_operation` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_sync_scope_index` | authorization-before-business-read 的非敏感归属索引。 | `projects`、`working_paper` | orm+mig | 1 / `services/workpaper_sync/repository.py` |
| `working_paper_sync_test_run` | 一次可复现验收执行（source-backed capability identity，禁自由文本覆写）。 | `working_paper_artifact` | orm+mig | 1 / `services/workpaper_sync/pilot_harness.py` |

## D11 合并（36 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `companies` | 公司信息表 | `projects` | orm | 未扫到 |
| `component_auditors` | 组成部分审计师表 | `projects` | orm | 1 / `services/component_auditor_service.py` |
| `component_instructions` | 组成部分审计指令表 | `component_auditors`、`projects`、`users` | orm | 1 / `services/component_auditor_service.py` |
| `component_results` | 组成部分审计结果表 | `component_auditors`、`projects` | orm | 1 / `services/component_auditor_service.py` |
| `consol_artifact` | 绑定已发布 report run 的不可变合并 Excel artifact。 | `consol_operation`、`projects`、`report_generation_run`、`users` | orm+mig | 1 / `services/consol_artifact_service.py` |
| `consol_cell_comments` | 单元格批注与复核标记 — 支持所有模块的单元格级批注和复核状态持久化 | — | orm+mig | 1 / `routers/consol_cell_comments.py` |
| `consol_note_data` | 合并附注用户数据存储 — 按项目+年度+章节存储用户编辑的附注数据 | — | orm+mig | 8 / `services/consol_node_scope.py`、`services/consol_note_detail_apply_service.py`、`services/consol_note_formula_service.py` |
| `consol_note_detail_template` | 合并附注明细模板——按 template_type + section_id 组织。 | `users` | orm+mig | 1 / `services/consol_note_detail_template_service.py` |
| `consol_note_detail_template_version` | 模板不可变版本。rows JSONB 格式： | `consol_note_detail_template`、`users` | orm+mig | 1 / `services/consol_note_detail_template_service.py` |
| `consol_note_formula` | 合并附注单元格取数公式（语法同报表公式：TB / SUM_TB / REPORT / ROW）。 | — | orm+mig | 2 / `services/consol_note_formula_service.py`、`services/formula_settings/domain_stores.py` |
| `consol_note_mapping_binding` | 企业级绑定——记录每家企业确认使用哪条规则，以及绑定时的来源结构指纹。 | `consol_note_mapping_rule`、`projects` | orm+mig | 1 / `services/consol_note_mapping_rule_service.py` |
| `consol_note_mapping_rule` | 映射规则。mappings JSONB 格式： | `consol_note_detail_template_version`、`projects`、`users` | orm+mig | 1 / `services/consol_note_mapping_rule_service.py` |
| `consol_note_mapping_rule_template` |  | — | mig（已删） | 未扫到 |
| `consol_note_structure_lock` |  | — | mig（已删） | 未扫到 |
| `consol_note_structure_lock_entity` |  | — | mig（已删） | 未扫到 |
| `consol_note_template_binding` | 项目绑定到某一模板版本——一个项目一个章节只绑一个版本。 | `consol_note_detail_template_version`、`projects`、`users` | orm+mig | 1 / `services/consol_note_detail_template_service.py` |
| `consol_note_template_push_log` | 合并附注模板推送日志 —— 仅 ORM 映射，写入走 raw SQL。 | — | orm+mig | 1 / `services/consol_note_template_push_service.py` |
| `consol_note_value_confirmation` |  | — | mig（已删） | 未扫到 |
| `consol_operation` | 一次可恢复、可比较输入版本的合并运行。 | `projects`、`users` | orm+mig | 1 / `services/consol_operation_service.py` |
| `consol_push_run` | 合并推送运行记录（公式管理「合并推送」页）。 | `consol_operation`、`projects` | orm+mig | 2 / `services/consol_push_failure_record.py`、`services/consol_push_service.py` |
| `consol_query_template` | 自定义查询模板 | `projects` | orm | 1 / `services/consol_pivot_service.py` |
| `consol_scope` | 合并范围表 | `projects` | orm+mig | 2 / `services/consol_scope_service.py`、`services/g7_consol_linkage_service.py` |
| `consol_scope_confirmation_nodes` | 某确认版本中的角色投影；不是 projects 或金额数据的副本。 | `consol_scope_confirmations`、`projects` | orm+mig | 1 / `services/consol_scope_confirmation_service.py` |
| `consol_scope_confirmations` | 合并企业树版本（V183 起名「范围确认」；V206 起推送时自动记录，手动记录仍可）。 | `projects`、`users` | orm+mig | 1 / `services/consol_scope_confirmation_service.py` |
| `consol_snapshots` |  | `projects`、`users` | orm+mig | 1 / `services/consol_snapshot_service.py` |
| `consol_trial` | 合并试算表 | `projects` | orm+mig | 3 / `services/consol_trial_service.py`、`services/consol_trial_stale_handler.py`、`services/group_links.py` |
| `consol_workpaper_instance` | 合并项目/年度与 A3-CONSOL 薄底稿壳的关联及最近正式产物指针。 | `consol_artifact`、`consol_operation`、`projects`、`working_paper`、`wp_index` | orm+mig | 1 / `services/consol_workpaper_shell.py` |
| `consol_worksheet` | 合并差额表 — 每个企业树节点 × 科目 × 年度一行。 | `projects` | orm+mig | 1 / `services/consol_worksheet_engine.py` |
| `consol_worksheet_data` | 合并工作底稿数据存储 — 通用 JSON 存储，支持所有 16 张表 | — | orm+mig | 3 / `routers/consol_worksheet_data.py`、`services/formula_runtime/adapters/consol_worksheet.py`、`services/g7_consol_linkage_service.py` |
| `elimination_entries` | 抵消分录表 | `projects`、`users` | orm+mig | 3 / `services/consol_auto_elimination_service.py`、`services/consol_elimination_sheet_service.py`、`services/elimination_service.py` |
| `forex_translation` | 外币折算表 | `projects` | orm | 1 / `services/forex_service.py` |
| `goodwill_calc` | 商誉计算表 | `projects` | orm | 1 / `services/goodwill_service.py` |
| `internal_ar_ap` | 内部往来表 | `projects` | orm | 1 / `services/internal_trade_service.py` |
| `internal_trade` | 内部交易表 | `projects` | orm | 1 / `services/internal_trade_service.py` |
| `minority_interest` | 少数股东权益表 | `projects` | orm | 1 / `services/minority_interest_service.py` |
| `share_change_event` | 动态股比变动事件。 | `projects` | orm+mig | 1 / `services/share_change_event_service.py` |

## D12 附件、证据、函证与归档（47 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `ai_content_governance` | AiContentGovernance（design §4.6 / AIEvidenceGate；R8/P17/P18/P19）—— AI  | `projects`、`service_identities`、`users` | orm+mig | 1 / `services/evidence_governance/ai_evidence_gate.py` |
| `archive_checklists` |  | `projects`、`users` | orm | 未扫到 |
| `archive_jobs` | 归档编排作业 | `projects`、`users` | orm | 1 / `services/archive_orchestrator.py` |
| `archive_manifest_edges` | ArchiveManifestEdge（design §4.6；R11/P23）—— manifest 冻结的证据图边；append-onl | `archive_manifests` | orm+mig | 1 / `routers/archive_manifest_router.py` |
| `archive_manifest_entries` | ArchiveManifestEntry（design §4.6；R11/P23）—— manifest 覆盖的证据节点；append-on | `archive_manifests` | orm+mig | 1 / `routers/archive_manifest_router.py` |
| `archive_manifests` | ArchiveManifest（design §4.6/§5.5；R11/P24）—— sealed 后不可变，每次归档递增版本。 | `projects`、`service_identities`、`users` | orm+mig | 2 / `routers/archive_manifest_router.py`、`services/evidence_governance/archive_manifest_service.py` |
| `archive_modifications` |  | `projects`、`users` | orm | 未扫到 |
| `asset_blobs` |  | `service_identities`、`users` | orm+mig | 1 / `services/asset_blob_service.py` |
| `attachment_lineage` | 附件溯源关联 | — | orm+mig | 1 / `routers/attachment_lineage.py` |
| `attachment_versions` | 不可变内容快照（design §4.3）。 | `asset_blobs`、`service_identities`、`users` | orm+mig | 6 / `services/attachment_asset_projection.py`、`services/evidence_governance/backfill_runner.py`、`services/evidence_governance/quarantine_reaper.py` |
| `attachment_working_paper` | 附件-底稿关联 | `attachments`、`users`、`working_paper` | orm | 1 / `services/attachment_service.py` |
| `attachments` | 附件 | `projects`、`service_identities`、`users` | orm | 7 / `services/attachment_service.py`、`services/evidence_governance/backfill_runner.py`、`services/evidence_governance/quarantine_reaper.py` |
| `citation_snapshots` | CitationSnapshot（design §4.6；R7/P15/P16）—— 不可变（immutable 触发器）。 | `ai_content_log`、`evidence_refs`、`projects`、`service_identities`、`users` | orm+mig | 1 / `services/evidence_governance/citation_snapshot_service.py` |
| `confirmation_action_log` | 函证操作审计留痕（append-only，DB 触发器禁 UPDATE/DELETE） | — | orm+mig | 2 / `services/confirmation_evidence_service.py`、`services/confirmation_service.py` |
| `confirmation_ai_check` | 函证AI检查 | `confirmation_lists`、`users` | orm | 未扫到 |
| `confirmation_attachment_link` | 函证↔附件关联（含角色、强配对、匹配状态） | `attachments`、`confirmations` | orm+mig | 1 / `services/confirmation_evidence_service.py` |
| `confirmation_attachments` |  | `confirmation_lists`、`users` | orm | 未扫到 |
| `confirmation_letters` | 询证函模板/内容 | `confirmation_lists` | orm | 未扫到 |
| `confirmation_lists` |  | `projects`、`users` | orm | 未扫到 |
| `confirmation_results` |  | `confirmation_lists`、`users` | orm | 未扫到 |
| `confirmation_summaries` | 询证函汇总 | `confirmation_lists`、`users` | orm | 未扫到 |
| `confirmations` | 函证记录 | `projects`、`users`、`working_paper` | orm+mig | 1 / `services/confirmation_service.py` |
| `evidence_audit_command_roots` | command-root（design §7.1；R12/P25）—— 每敏感命令+幂等键+scope 恰一个 root。 | `projects`、`service_identities`、`users` | orm+mig | 未扫到 |
| `evidence_audit_transitions` | command-root 的多行 transition 审计（design §7.1；R12/P25）—— append-only。 | `evidence_audit_command_roots`、`service_identities`、`users` | orm+mig | 1 / `services/evidence_governance/command_audit.py` |
| `evidence_dependencies` | 统一依赖图的动态边 source→target（design §4.4；R9/P20）。 | `evidence_refs`、`projects`、`service_identities`、`users` | orm+mig | 2 / `services/evidence_governance/evidence_ref_query_service.py`、`services/evidence_governance/evidence_ref_service.py` |
| `evidence_hash_checks` |  | — | orm | 1 / `services/export_integrity_service.py` |
| `evidence_inbox` | inbox（design §5.4；R12）—— 按 event_id 幂等消费，避免重复副作用。 | `projects`、`service_identities`、`users` | orm+mig | 未扫到 |
| `evidence_links` | 证据链 | `attachments`、`working_paper` | orm+mig | 1 / `services/wp_evidence_service.py` |
| `evidence_migration_checkpoints` | 迁移 checkpoint（design §8.2 M1；R14/P28）—— batch_key 幂等，重跑从检查点恢复不重复对象。 | `projects`、`service_identities`、`users` | orm+mig | 1 / `services/evidence_governance/backfill_runner.py` |
| `evidence_outbox` | 事务性 outbox（design §5.4/§7.1；R12/R9）—— 按 event_id 幂等，有界退避 + dead_letter | `evidence_audit_command_roots`、`projects`、`service_identities`、`users` | orm+mig | 未扫到 |
| `evidence_quality_snapshots` | 质量快照（design §9；R16/P30）—— 固定不可变快照（immutable 触发器），可复算。 | `projects`、`service_identities`、`users` | orm+mig | 未扫到 |
| `evidence_quarantine_handles` | 隔离/暂存句柄 —— 内容不可公开读取（design §4.0）。 | `evidence_upload_attempts`、`projects`、`service_identities`、`users` | orm+mig | 2 / `services/evidence_governance/quarantine_reaper.py`、`services/evidence_governance/secure_attachment_gateway.py` |
| `evidence_refs` | 持久 EvidenceRef（design §4.4；R3.1）—— 可查询、可保留的持久记录（非 per-request DTO）。 | `attachment_versions`、`projects`、`service_identities`、`users` | orm+mig | 3 / `services/deliverable_center_integration.py`、`services/evidence_governance/evidence_ref_query_service.py`、`services/evidence_governance/evidence_ref_service.py` |
| `evidence_tombstones` | 不可变墓碑 —— 对象被清理后保留的永久审计痕迹。 | `projects`、`users` | orm+mig | 1 / `services/evidence_governance/retention_legal_hold_service.py` |
| `evidence_upload_attempts` | UploadAttempt —— 内容验证前的最小上传审计（design §4.0 / R1.1 / R12）。 | `projects`、`service_identities`、`users` | orm+mig | 1 / `services/evidence_governance/secure_attachment_gateway.py` |
| `legacy_attachment_alias` | 旧附件 ID → (新聚合根, 确定版本) 解析别名（design §4.1）。 | `projects` | orm+mig | 3 / `services/attachment_asset_projection.py`、`services/attachment_permanent_delete_service.py`、`services/evidence_governance/backfill_runner.py` |
| `legal_hold_scopes` | LegalHoldScope（design §4.6；R13/P26）—— 固化 direct/transitive 范围；范围历史不删除。 | `legal_holds`、`projects` | orm+mig | 1 / `services/evidence_governance/retention_legal_hold_service.py` |
| `legal_holds` | LegalHold（design §4.6/§5.5；R13/P26/P27）—— released_by_user_id 人工专属（rel | `projects`、`service_identities`、`users` | orm+mig | 1 / `services/evidence_governance/retention_legal_hold_service.py` |
| `ocr_confirmations` | OCRConfirmation（design §4.5；R6.2/P12）—— append-only 人工确认修订。 | `ocr_jobs`、`ocr_results`、`projects`、`users` | orm+mig | 1 / `services/evidence_governance/ocr_confirmation_service.py` |
| `ocr_job_transitions` | OCRJobTransition（design §4.5）—— 每次状态迁移一条，关联 command-root；append-only。 | `evidence_audit_command_roots`、`ocr_jobs`、`service_identities`、`users` | orm+mig | 2 / `services/evidence_governance/ocr_governance.py`、`services/evidence_governance/ocr_retry_service.py` |
| `ocr_jobs` | OCRJob（design §4.5；R5/P9）—— 绑定确定版本/hash/config/幂等键/lease/actor。 | `attachment_versions`、`evidence_audit_command_roots`、`projects`、`service_identities`、`users` | orm+mig | 1 / `services/evidence_governance/ocr_governance.py` |
| `ocr_results` | OCRResult（design §4.5；R6.1/P11）—— 不可变原始识别结果（immutable 触发器）。 | `attachment_versions`、`ocr_jobs`、`projects`、`service_identities`、`users` | orm+mig | 1 / `services/evidence_governance/ocr_confirmation_service.py` |
| `ocr_writeback_staging` | staged-external 写回暂存（design §4.5；R6.4/P13）—— 目标模块以幂等键消费后回执推进。 | `ocr_writebacks`、`projects` | orm+mig | 1 / `services/evidence_governance/ocr_writeback_service.py` |
| `ocr_writebacks` | OCRWriteback（design §4.5；R6.4/P13/P14）—— 目标版本/mapping/confirmation IDs | `evidence_audit_command_roots`、`ocr_jobs`、`projects`、`users` | orm+mig | 1 / `services/evidence_governance/ocr_writeback_service.py` |
| `review_closes` | ReviewClose（design §4.6；R10.2/P21）—— closed_by_user_id NOT NULL（人工专属）。 | `evidence_audit_command_roots`、`projects`、`users` | orm+mig | 1 / `routers/review_evidence_router.py` |
| `review_evidence_snapshots` | ReviewEvidenceSnapshot（design §4.6；R10/P22）—— 冻结提出/关闭时 ref/version/has | `evidence_refs`、`projects`、`service_identities`、`users` | orm+mig | 2 / `routers/review_evidence_router.py`、`services/evidence_governance/review_evidence_service.py` |
| `service_identities` | 系统作业主体（Service Identity）—— actor XOR 的 service 侧 FK 目标。 | — | orm+mig | 未扫到 |

## D13 复核、质控与签字门禁（29 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `audit_check_signoff` | 审计检查复核门禁签认（audit-check-review-gate-hardening / V126）。 | — | orm+mig | 1 / `routers/audit_check.py` |
| `cell_annotations` |  | `projects`、`users` | orm | 2 / `services/annotation_service.py`、`services/wp_cell_annotation_service.py` |
| `consistency_gate_acknowledgements` | 门禁逐项确认留痕表 | — | orm+mig | 1 / `services/gate_acknowledgement_service.py` |
| `cross_check_results` | 跨科目校验结果 | `projects` | orm+mig | 3 / `services/formula_management/cross_check_run.py`、`services/formula_management/logic_check.py`、`services/wp_cross_check_service.py` |
| `eqcr_disagreement_resolutions` | EQCR 与项目组意见不一致时触发的合议结论。 | `eqcr_opinions`、`projects` | orm | 1 / `routers/eqcr/gate.py` |
| `eqcr_opinions` | EQCR 对判断类事项的意见留痕。 | `projects`、`users` | orm | 2 / `routers/eqcr/gate.py`、`services/eqcr_domain_service.py` |
| `eqcr_review_notes` | EQCR 独立复核笔记（默认仅 EQCR 可见）。 | `projects`、`users` | orm | 1 / `routers/eqcr/notes.py` |
| `eqcr_shadow_computations` | EQCR 独立跑一遍勾稽的结果永久留痕。 | `projects`、`users` | orm | 1 / `services/eqcr_shadow_compute_service.py` |
| `eqcr_snapshots` | EQCR 快照 — 聚合项目数据供独立复核使用。 | `projects`、`users` | orm+mig | 2 / `routers/eqcr_judgment.py`、`services/eqcr_snapshot_service.py` |
| `gate_decisions` | 门禁决策记录表 | — | orm | 2 / `services/consistency_gate/_decision.py`、`services/gate_engine.py` |
| `gate_rule_configs` | 门禁规则配置表 — 平台强制 vs 租户可配置分层 | — | orm | 未扫到 |
| `independence_signing_tasks` | A17-7 独立性声明书电子签署任务 | — | orm+mig | 1 / `services/independence_signing_service.py` |
| `project_quality_ratings` | 项目质量评级 | — | orm+mig | 1 / `services/quality_rating_service.py` |
| `qc_case_library` | QC 案例库条目 | — | orm+mig | 1 / `services/qc_case_library_service.py` |
| `qc_inspection_items` | 质控抽查子项 | `qc_inspections` | orm+mig | 1 / `services/qc_inspection_service.py` |
| `qc_inspection_records` | 质控独立复核记录 | `qc_inspection_items` | orm+mig | 未扫到 |
| `qc_inspections` | 质控抽查批次 | `projects` | orm+mig | 1 / `services/qc_inspection_service.py` |
| `qc_rule_definitions` | QC 规则定义表 — 元数据 + 开关 | — | orm+mig | 1 / `services/qc_rule_definition_service.py` |
| `review_checklist_records` | 复核检查表记录（A21~A25 各级勾选+意见） | — | orm+mig | 1 / `services/review_workflow_service.py` |
| `review_conversations` |  | `projects`、`users` | orm | 2 / `services/procedure_review_service.py`、`services/review_conversation_service.py` |
| `review_messages` |  | `review_conversations`、`users` | orm | 3 / `routers/review_dialog.py`、`services/procedure_review_service.py`、`services/review_conversation_service.py` |
| `review_records` | 复核批注 | `review_conversations`、`users`、`working_paper` | orm | 1 / `services/wp_review_service.py` |
| `review_templates` | 复核意见模板 | `users` | orm+mig | 1 / `routers/review_templates.py` |
| `review_threads` | V095: 复核对话线程 — 每个底稿区域一个线程 | `projects`、`users`、`working_paper` | orm+mig | 1 / `routers/review_dialog.py` |
| `reviewer_metrics_snapshots` | 复核人深度指标快照 | — | orm+mig | 1 / `services/reviewer_metrics_service.py` |
| `signature_records` | 签名记录 | `users` | orm | 3 / `routers/eqcr/gate.py`、`services/independence_service.py`、`services/sign_service.py` |
| `trace_events` | 统一过程留痕主表 | — | orm | 1 / `services/trace_event_service.py` |
| `workpaper_review_records` | 工作底稿复核记录 | `projects`、`users` | orm | 未扫到 |
| `wp_qc_results` | 底稿质量自检结果 | `users`、`working_paper` | orm | 1 / `services/qc_engine.py` |

## D14 AI 与知识库（33 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `ai_analysis_item` | AI分析报告条目 | `ai_analysis_report` | orm | 未扫到 |
| `ai_analysis_report` | AI分析报告 | `projects` | orm | 未扫到 |
| `ai_chat_action_receipts` | note save / adopt 的通用幂等收据（Req 8.2/8.3 · Property 21）。 | `ai_chat_session`、`users` | orm+mig | 1 / `services/ai_chat/persistence.py` |
| `ai_chat_attachments` | 会话附件 metadata（Req 7.3）。 | `ai_chat_runs`、`ai_chat_session`、`projects`、`users` | orm+mig | 1 / `services/ai_chat/attachment_service.py` |
| `ai_chat_history` | AI对话历史 | `projects`、`users` | orm | 未扫到 |
| `ai_chat_mcp_call_log` |  | — | mig | 未扫到 |
| `ai_chat_mcp_token_revocations` |  | — | mig | 未扫到 |
| `ai_chat_message` | AI问答消息（详细消息记录） | `ai_chat_runs`、`ai_chat_session` | orm | 3 / `services/ai_chat/persistence.py`、`services/ai_chat/run_service.py`、`services/doc_chat_persistence.py` |
| `ai_chat_run_resources` |  | `ai_chat_runs`、`ai_chat_session`、`asset_blobs`、`attachment_versions`、`users` | orm+mig | 1 / `services/ai_chat/run_resource_service.py` |
| `ai_chat_runs` | Chat Run —— 一次模型/Agent 执行的持久化摘要。 | `ai_chat_session`、`projects`、`users` | orm+mig | 3 / `services/ai_chat/persistence.py`、`services/ai_chat/run_coordinator.py`、`services/ai_chat/run_service.py` |
| `ai_chat_session` | AI问答会话（会话维度聚合） | `projects`、`users` | orm | 3 / `services/ai_chat/persistence.py`、`services/ai_chat/review_mode.py`、`services/doc_chat_persistence.py` |
| `ai_chat_tool_calls` | 工具调用摘要（Req 11.10：每次调用产生 started + finished/failed 记录）。 | `ai_chat_runs` | orm+mig | 未扫到 |
| `ai_confirmation_audit` | AI函证审核记录 | `projects`、`users` | orm | 未扫到 |
| `ai_content` | AI生成内容 | `projects`、`users` | orm | 9 / `routers/review_prompt.py`、`services/ai_review_artifact.py`、`services/batch_review_service.py` |
| `ai_content_log` | AI 生成内容溯源日志 — 字段级追踪 AI 输出及人工确认状态 | `ai_chat_message`、`citation_snapshots`、`evidence_refs`、`projects`、`users` | orm+mig | 2 / `routers/citation_router.py`、`services/ai_content_log_service.py` |
| `ai_evidence_chains` | AI证据链 | `projects` | orm | 未扫到 |
| `ai_evidence_items` | AI证据项 | `ai_evidence_chains` | orm | 未扫到 |
| `ai_knowledge_base` | AI知识库文档索引 | `projects` | orm | 未扫到 |
| `ai_model_config` | AI模型配置 | — | orm | 3 / `core/seed_ai_models.py`、`routers/ai_models.py`、`services/ai_service.py` |
| `ai_plugins` | AI插件 | — | orm | 1 / `services/ai_plugin_service.py` |
| `ai_task_items` |  | `ai_chat_message`、`ai_task_jobs` | orm+mig | 1 / `services/ai_task_job_service.py` |
| `ai_task_jobs` |  | `projects`、`users` | orm+mig | 未扫到 |
| `ai_workpaper_fills` | AI底稿填充记录 | `ai_workpaper_tasks`、`working_paper` | orm | 1 / `services/wp_fill/_fill_task.py` |
| `ai_workpaper_tasks` | AI底稿填充任务 | `working_paper` | orm | 1 / `services/wp_fill/_fill_task.py` |
| `document_extracted` | 单据结构化提取数据 | `document_scan`、`users` | orm | 1 / `services/ocr_service_v2.py` |
| `document_match` | 单据与账面数据匹配 | `document_scan` | orm | 1 / `services/ocr_service_v2.py` |
| `document_scan` | 单据扫描件 | `projects`、`users` | orm | 1 / `services/ocr_service_v2.py` |
| `evidence_chain` | 证据链 | `projects` | orm | 未扫到 |
| `knowledge_documents` | 知识库文档 | `asset_blobs`、`knowledge_folders`、`users` | orm+mig | 2 / `services/knowledge_folder_service.py`、`services/knowledge_ocr_service.py` |
| `knowledge_evidence_promotions` |  | `asset_blobs`、`attachment_versions`、`attachments`、`knowledge_documents`、`projects`、`users` | orm+mig | 1 / `services/knowledge_evidence_promotion_service.py` |
| `knowledge_folders` | 知识库文件夹（树形目录） | `users` | orm+mig | 2 / `routers/knowledge_base.py`、`services/knowledge_folder_service.py` |
| `knowledge_index` | 知识库索引 | — | orm | 4 / `routers/knowledge_folders.py`、`services/indexing_pipeline.py`、`services/knowledge_index_service.py` |
| `wp_ai_generations` | AI生成历史记录，完整留痕每次生成的prompt/model/输出/确认信息。 | `users`、`working_paper` | orm | 1 / `services/wp_explanation_service.py` |

## D15 后台任务、事件与系统基础设施（21 张）

| 表名 | 说明 | 外键指向 | 来源 | 写入方（文件数 / 前 3 个） |
|---|---|---|---|---|
| `acnr_invalidation_epoch` | ACNR Durable_Epoch — per-project 失效计数器（DB 权威，Redis 仅 fan-out）。 | — | orm+mig | 1 / `services/acnr/cache_epoch.py` |
| `acnr_invalidation_outbox` | ACNR Invalidation_Outbox — 业务变更同事务写入，dispatcher 至少一次投递。 | — | orm+mig | 1 / `services/acnr/invalidation_outbox.py` |
| `app_audit_log` |  | — | mig | 8 / `routers/eqcr_judgment.py`、`routers/password_confirm.py`、`routers/project_wizard.py` |
| `audit_chain_head` | 每条审计链的事务内权威链尾。 | — | orm+mig | 1 / `services/audit_chain/head.py` |
| `audit_log_entries` | 审计日志条目 — 不可变追加式 | — | orm+mig | 2 / `services/audit_chain/forks.py`、`services/audit_chain/head.py` |
| `background_job_items` | 后台长任务明细项。 | `background_jobs`、`working_paper` | orm | 1 / `services/background_job_service.py` |
| `background_jobs` | 后台长任务主表（批量刷新/生成/提交/下载等）。 | `projects`、`users` | orm | 1 / `services/background_job_service.py` |
| `chain_executions` | 全链路执行记录 | — | orm+mig | 2 / `services/chain_orchestrator.py`、`services/note_conversion_service.py` |
| `cross_module_conflicts` | 跨模块冲突调解记录 — 上游数据变更与手工覆盖的冲突追踪 | `projects`、`users` | orm+mig | 1 / `services/conflict_resolution_service.py` |
| `data_snapshots` |  | — | mig | 1 / `services/note_data_lock_service.py` |
| `event_cascade_log` |  | — | orm+mig | 1 / `services/linkage_service.py` |
| `feature_flags` | Feature flag 功能开关（zero-downtime-deployment 组件 8）。 | — | orm+mig | 1 / `services/feature_flag_service.py` |
| `offline_conflicts` |  | — | orm | 1 / `services/offline_conflict_service.py` |
| `platform_job_attempts` |  | `platform_jobs` | orm+mig | 1 / `services/platform_job_service.py` |
| `platform_jobs` |  | `projects`、`users` | orm+mig | 1 / `services/platform_job_service.py` |
| `schema_drift_log` |  | — | mig | 1 / `core/schema_drift_detector.py` |
| `schema_migration_failures` |  | — | mig | 1 / `core/migration_runner.py` |
| `schema_version` |  | — | mig | 1 / `core/migration_runner.py` |
| `system_settings` |  | — | mig | 未扫到 |
| `time_machine_snapshots` | 时光机增量快照 — RFC 6902 JSON Patch 反向 diff | `projects`、`users` | orm+mig | 1 / `services/time_machine_service.py` |
| `version_line_stamps` |  | — | orm | 1 / `services/version_line_service.py` |

