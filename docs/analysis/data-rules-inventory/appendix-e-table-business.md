# 附录 E：表与业务的关系（逐表）

> 「写入业务」「读取业务」按写 / 读这张表的代码文件归类到业务域，括号里是文件数。静态扫描，可能漏掉经通用函数读写的情况。

## D01 用户、组织与权限（20 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `annual_independence_declarations` | 年度独立性声明（R5 需求 12）+ 项目级独立性声明（R1 需求 10 合并）。 | D13（1） | D13（1） |
| `dispatch_records` | 分发记录 — 描述「哪条函证行被分发到了哪个下游底稿」 | D15（1）、D10（1） | D15（1） |
| `handover_records` | 人员交接记录 | D01（1） | 未扫到 |
| `logs` | 操作日志 | D15（4）、D09（2）、D05（1）、D03（1）、D10（1） | D01（1）、D09（1）、D15（1） |
| `notifications` | 系统通知 | D02（2）、D09（2）、D05（1）、D13（1）、D15（1） | D02（2）、D09（1） |
| `partner_rotation_overrides` | 合伙人轮换 Override | D13（1） | D13（1） |
| `project_assignments` | 项目团队委派 | D13（1）、D01（1） | D09（11）、D01（10）、D13（9）、D02（5）、D08（3）、D15（3）、D05（1） |
| `project_creation_grants` | admin 授予 manager 对一个精确 USCC 的项目创建权。 | D01（1） | D01（1） |
| `project_user_level_backfill` |  | 未扫到 | 未扫到 |
| `project_users` | 项目成员关联 | D13（1）、D15（1）、D01（1） | D15（10）、D12（8）、D08（6）、D01（5）、D13（4）、D02（2）、D09（2）、D06（1）、D05（1）、D14（1）、D10（1） |
| `staff_members` | 全局人员库 | D01（3） | D09（19）、D13（9）、D01（8）、D02（4）、D08（4）、D15（4）、D05（2）、D12（1）、D07（1）、D06（1） |
| `sys_dept` | 部门组织架构 | D01（1） | D01（2）、D15（1） |
| `sys_role` | 角色（数据权限维度）。 | D01（1） | D01（3） |
| `sys_role_project` | 角色-自定义项目多对多（仅 data_scope=2 使用）。 | D01（1） | D01（2） |
| `sys_user_role` | 账号-角色多对多绑定。 | D01（2） | D01（2） |
| `temporary_grants` | 临时授权记录 | D01（1） | D01（1） |
| `user_display_preferences` | 账号级显示偏好（一对一，user_id 主键）。 | D01（1） | D01（1） |
| `users` | 系统用户 | D01（1） | D01（11）、D09（9）、D15（6）、D10（4）、D13（4）、D08（4）、D03（3）、D02（3）、D12（3）、D05（2）、D06（2）、D14（1）、D11（1）、D07（1） |
| `work_hour_entries` | 工时填报条目（三级粒度） | D01（2）、D15（2） | D01（6）、D15（2） |
| `work_hours` | 工时记录 — DEPRECATED: V117 迁移后由 work_hour_entries 替代。 | D01（2）、D13（1） | D02（3）、D01（2）、D13（1） |

## D02 项目与项目管理（27 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `audit_findings` |  | 未扫到 | D15（1） |
| `audit_plans` |  | D09（1） | D09（1） |
| `audit_procedures` |  | 未扫到 | 未扫到 |
| `budget_hours` | 预算工时 | 未扫到 | 未扫到 |
| `check_ins` |  | D06（1） | D06（1） |
| `forum_comments` |  | D15（1） | D15（1） |
| `forum_posts` |  | D15（1） | D15（1） |
| `going_concern_evaluations` |  | 未扫到 | D13（1）、D02（1） |
| `going_concern_indicators` |  | 未扫到 | D13（1） |
| `interim_survival_checks` |  | D15（1） | D15（1）、D12（1） |
| `issue_tickets` | 统一问题单（对齐 v2 4.5.15A） | D09（3）、D13（2）、D15（2）、D02（2）、D01（1） | D02（6）、D13（5）、D15（4）、D09（2）、D01（1） |
| `management_letters` |  | 未扫到 | 未扫到 |
| `pbc_checklist` | PBC 清单项 | D02（1） | D02（1）、D01（1） |
| `project_batch_import_plans` | 一次上传产生的规范化计划、预览与可重放最终回执。 | D02（1） | D02（1） |
| `project_classification_v219_backup` |  | 未扫到 | 未扫到 |
| `project_sync` | 项目同步状态 | 未扫到 | 未扫到 |
| `project_timeline` | 项目时间线/里程碑 | 未扫到 | D13（1） |
| `projects` | 审计项目 | D07（3）、D15（2）、D02（2）、D08（1）、D11（1） | D09（220）、D08（29）、D15（28）、D13（27）、D02（21）、D06（18）、D07（18）、D11（17）、D12（14）、D14（12）、D01（12）、D04（8）、D03（3）、D10（3）、D05（1） |
| `related_party_registry` | 关联方主数据（项目级）。 | D13（1） | D09（22）、D13（2） |
| `related_party_transactions` | 关联方交易明细。 | D13（1）、D07（1） | D13（2） |
| `risk_assessments` |  | 未扫到 | 未扫到 |
| `risk_matrix_records` |  | 未扫到 | 未扫到 |
| `se_checklist` |  | 未扫到 | 未扫到 |
| `subsequent_events` |  | D02（1） | D02（1） |
| `sync_logs` | 同步日志 | 未扫到 | 未扫到 |
| `task_events` | 事件总线与补偿队列 | D09（2）、D15（1）、D02（1） | D02（2）、D09（1） |
| `task_tree_nodes` | 四级任务树节点：unit/account/workpaper/evidence | 未扫到 | D02（2） |

## D03 账表导入与数据集（16 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `activation_records` | 激活/回滚操作留痕 | D03（2） | D03（4） |
| `direction_override` | 方向覆盖 overlay 表 — 用户确认/修正方向时记录，不改写原始四表导入行。 | 未扫到 | 未扫到 |
| `event_outbox_dlq` | 事件广播死信队列（F45）。 | D03（1） | D15（1） |
| `import_artifacts` | 上传产物 — 平台级文件引用 | D03（3） | D03（2） |
| `import_batches` | 导入批次 | D03（5）、D04（1） | D03（3） |
| `import_column_mapping_history` | 列映射历史记录（F52 / Sprint 8.34 扩展版）。 | D03（1） | D03（1） |
| `import_event_consumptions` | 事件消费幂等记录。 | D15（1）、D03（1）、D10（1） | D03（1） |
| `import_event_outbox` | 导入域事件 outbox。 | D03（1）、D10（1） | D03（2）、D15（1）、D08（1）、D13（1） |
| `import_jobs` | 导入作业 — 关注任务执行过程 | D03（3） | D03（9）、D15（1） |
| `ledger_datasets` | 业务级数据集版本 | D03（2） | D03（14）、D15（3）、D12（2）、D09（2）、D14（2）、D05（1）、D13（1）、D08（1）、D06（1）、D04（1） |
| `ledger_import_attempts` | 一次账套导入 attempt 的最小不可变合同与状态记录。 | D03（1） | D03（2） |
| `tb_aux_balance` | 辅助余额表 | 未扫到 | D09（6）、D03（5）、D15（5）、D07（4）、D08（3）、D14（2）、D06（1）、D04（1）、D13（1） |
| `tb_aux_balance_summary` |  | D03（1） | D03（2） |
| `tb_aux_ledger` | 辅助明细账 — 按 year 分区 | 未扫到 | D07（2）、D09（1）、D03（1）、D12（1） |
| `tb_balance` | 科目余额表 | 未扫到 | D09（52）、D03（12）、D15（6）、D06（2）、D13（2）、D07（1）、D05（1）、D02（1）、D14（1）、D04（1） |
| `tb_ledger` | 序时账（总账明细）— 按 year 分区 | 未扫到 | D09（9）、D03（6）、D12（3）、D15（3）、D14（2）、D05（1）、D07（1）、D08（1）、D13（1） |

## D04 科目映射与试算表（13 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `account_chart` | 科目表（标准科目 + 客户科目） | D04（3）、D03（1） | D04（5）、D03（5）、D05（3）、D09（2）、D15（2） |
| `account_mapping` | 科目映射关系 | D15（1）、D04（1） | D15（5）、D03（5）、D04（4）、D05（2）、D02（1）、D06（1） |
| `aging_segments` | 账龄段枚举配置（每个底稿一条，关联 wp_index_id） | D04（2）、D09（1） | D04（1） |
| `bad_debt_detail_rows` | 坏账准备明细表 D2-3 嵌套行（父行与子行统一存储） | D04（2） | D04（2）、D08（1）、D09（1） |
| `custom_account_packages` |  | D04（1） | D04（1） |
| `materiality` | 重要性水平 | D04（1） | D13（7）、D09（5）、D05（2）、D08（1）、D04（1）、D02（1） |
| `report_line_mapping` | 报表行次映射（标准科目→报表行次） | D04（3） | D04（3）、D06（2）、D15（2）、D07（1）、D05（1）、D09（1） |
| `t_account_entries` | T型账户分录 | D04（1） | D04（1） |
| `t_accounts` | T型账户 | D04（1） | D04（1） |
| `tb_change_history` |  | D15（1） | D15（1） |
| `tb_publish_ack` | 审定表→试算表"发布"耐久确认/幂等表（对应迁移 V162）。 | D15（1）、D04（1） | D04（2） |
| `trial_balance` | 试算表（四列结构） | D09（4）、D15（3）、D04（3）、D05（1）、D03（1） | D09（54）、D15（18）、D08（10）、D07（9）、D06（9）、D04（7）、D13（5）、D03（5）、D14（3）、D11（3）、D05（2）、D02（1） |
| `trial_balance_snapshots` | 试算平衡表版本快照 - 记录每次审定表变更时的试算表完整状态 | D04（1） | D04（1） |

## D05 调整分录与错报（11 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `adjustment_client_bookings` | 客户已入账的追加式标记/撤销历史。 | D05（1） | D05（1） |
| `adjustment_collaboration` | 调整分录协作记录（分录组级转派→知晓→补充→确认）。 | D05（1） | D05（2） |
| `adjustment_collaboration_event` | 协作历史事件（append-only，仅 INSERT）。 | D05（1） | D05（1） |
| `adjustment_editing_locks` |  | D15（1） | D15（1） |
| `adjustment_entries` | 调整分录明细行（独立于 adjustments 头表） | D09（1）、D05（1） | D05（4）、D15（4）、D13（1）、D08（1）、D09（1） |
| `adjustment_import_batches` |  | 未扫到 | 未扫到 |
| `adjustment_import_group_results` |  | 未扫到 | 未扫到 |
| `adjustment_review_tasks` | 一笔调整分录的一轮持久化复核任务。 | D05（1） | D05（2） |
| `adjustment_treatment_events` | 调整财务处理的追加式事件，不覆盖历史。 | D05（1） | D05（1） |
| `adjustments` | 审计调整分录（AJE / RJE） | D05（2）、D09（1） | D05（11）、D15（6）、D13（4）、D09（3）、D04（2）、D14（1）、D06（1）、D12（1）、D02（1）、D01（1） |
| `unadjusted_misstatements` | 未更正错报汇总 | D15（1）、D05（1） | D05（7）、D15（2）、D13（2）、D03（1）、D02（1） |

## D06 报表、审计报告与交付件（21 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `accounting_standards` | 会计准则 | D06（1） | D09（1）、D06（1） |
| `audit_report` | 审计报告 | D06（2）、D09（2）、D15（1） | D13（6）、D09（5）、D06（4）、D15（4）、D03（2）、D12（2）、D02（1） |
| `audit_report_template` | 审计报告段落模板 | D06（2） | D09（1）、D06（1） |
| `cf_verification_results` | CF 核查结果缓存 + 用户差异说明 | D15（1） | D15（1） |
| `cfs_adjustments` | 现金流量表调整分录 | D06（1） | D06（1） |
| `deliverable_section_state` | 出品物章节级状态承载表（V067）。 | D06（3）、D15（1） | D06（3）、D15（2）、D12（1） |
| `deliverable_snapshots` | 不可变交付快照。 | D06（1） | D06（1） |
| `export_job_attempts` | 后台导出任务 attempt 历史。 | D06（2） | D06（1） |
| `export_job_items_v2` | 后台导出任务明细 | D06（3） | D06（2） |
| `export_jobs_v2` | 后台导出任务（全套导出/批量渲染/重试/三件套） | D06（1） | D06（2）、D13（1） |
| `export_tasks` | PDF导出任务 | D06（2） | D06（2） |
| `fill_preview_sessions` | 报告正文模板填充 preview 会话（audit-report-template-integrat | D09（1） | D09（1） |
| `financial_report` | 生成的财务报表数据 | D06（5）、D15（2）、D11（1）、D08（1） | D06（13）、D07（10）、D13（9）、D14（5）、D08（5）、D15（5）、D11（3）、D09（2）、D02（1）、D03（1） |
| `regulatory_filing` | 监管备案 | D06（1） | D06（1） |
| `report_config` | 报表格式配置（行次定义+取数公式）；V199 formula_version：全局行 = 定义版本、 | D08（2）、D15（1）、D06（1） | D08（8）、D06（4）、D03（3）、D11（2）、D15（2）、D04（2）、D09（1） |
| `report_config_baseline` | 报表配置主模板回填候选（项目优化→主模板评审通道） | D06（1） | D06（2） |
| `report_format_templates` |  | D06（1） | D06（1） |
| `report_generation_run` | 一次报表计算的不可变运行摘要与规范行快照。 | D11（1）、D06（1） | D11（2） |
| `report_snapshot` | 报表数据快照（导出时从快照读取，不重复计算） | D06（1） | D06（2）、D13（1） |
| `word_export_task` | Word导出主任务 | D06（2）、D15（1） | D06（12）、D15（2）、D12（1） |
| `word_export_task_versions` | Word导出版本快照 | D06（2） | D06（10）、D10（1） |

## D07 附注（15 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `account_note_mapping` | 科目→附注行映射 — 维护科目名称到附注表格行的映射关系 | D07（1） | D07（1）、D05（1） |
| `disclosure_notes` | 财务报表附注 | D07（8）、D15（2） | D07（45）、D15（11）、D08（8）、D14（7）、D13（4）、D11（3）、D06（3）、D09（3）、D03（1）、D02（1）、D12（1） |
| `group_note_template_baseline` | 集团附注模板基线（D6） | D07（1） | D07（1） |
| `group_note_templates` |  | D07（1） | D07（1） |
| `note_account_mappings` | 附注科目对照映射 — 报表行次 → 附注章节 → 表格的三级映射 | D07（1） | D07（2）、D08（1）、D15（1） |
| `note_content_template_versions` | 模板的不可变正文快照。 | D07（1） | D07（1） |
| `note_content_templates` | 个人或集团可见的附注内容模板目录。 | D07（1） | D07（1） |
| `note_formula_run` | 一个章节一次附注公式执行的可查询运行记录。 | D07（1） | 未扫到 |
| `note_section_instances` | 附注章节实例（裁剪后的章节） | D07（1） | D07（1） |
| `note_section_locks` |  | D07（1） | D07（1） |
| `note_section_templates` |  | D07（1） | D07（1） |
| `note_section_version_tree` | 章节版本树（D11） | D07（1） | D07（1） |
| `note_text_batch_applications` | 一次成功的附注正文原子批量应用审计。 | D07（1） | D07（1） |
| `note_trim_schemes` | 附注裁剪方案 | D15（1）、D07（1） | D15（1）、D07（1） |
| `note_validation_results` | 附注校验结果 | D07（1） | D07（2）、D13（1） |

## D08 公式、取数与查询（21 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `acnr_project_overlay` | ACNR L2 ProjectOverlay 持久化 — 项目级别名/CUST覆盖/binding。 | D08（1） | D08（1） |
| `advanced_query_writeback` | 高级查询回写身份 / 审计记录表 [advanced-query-module Task 1.3] | D08（1） | 未扫到 |
| `config_references` | 配置引用记录——记录哪个项目引用了哪个模板 | D15（1） | D15（1） |
| `custom_query_templates` | 自定义查询模板。 | D08（1） | D08（1） |
| `draft_marker` | 初稿标记（V100 formula-management-library）。 | D15（1） | D15（1） |
| `draft_refresh_audit` | 初稿刷新审计留痕（append-only，V100 formula-management-libra | D15（1）、D08（1） | D08（3）、D15（2） |
| `draft_refresh_snapshot` | 初稿刷新回滚快照（V100 formula-management-library）。 | D15（1） | D15（1） |
| `enum_dict_overrides` | 枚举字典覆盖（label / color 可改，value 不可改） | D08（1） | D08（1） |
| `formula_publish` | 发布记录。``status=pending`` 承载非 admin 提交的全局候选（admin 审核 | D08（5） | D08（5） |
| `formula_push_run` | 公式推送运行记录（面板「最近推送」）。 | D08（3） | D08（5） |
| `formula_push_state` | 公式推送目标级状态。 | D08（2） | D08（6）、D07（2） |
| `formula_runtime_outbox` | 公式运行时事务 Outbox — 与业务写入同事务提交，提交后可靠发布 stale/invalida | D15（1） | D08（1）、D15（1） |
| `formula_setting` | 统一公式设置行：``layer`` = global（全局）/ project（本项目适配）/ te | D08（4） | D08（8） |
| `formula_sync_item` | 待项目确认的同步事项。同一项目同一公式位只保留一条 pending（后续发布更新它）。 | D08（2） | D08（4） |
| `formula_template` | 可共享的公式模板（名称 / 共享范围 / 适用准则 / 当前版本）。 | D08（2） | D08（3） |
| `formula_template_subscription` | 项目订阅模板（每个项目每个域最多一个有效订阅）。 | D08（1） | D08（6） |
| `formula_template_version` | 模板每次发布的冻结快照（三方比对、回看、暂缓订阅者读取）。 | D08（2） | D08（3） |
| `query_artifacts` | 一次「导出全部」生成的不可变查询证据清单。 | D08（1）、D15（1） | D08（2）、D15（1） |
| `query_runs` | 一次查询定义在一个来源版本上的不可变运行记录。 | D08（2）、D15（1） | D08（2）、D15（1） |
| `shared_config_templates` | 共享配置模板 | D15（1） | D15（1） |
| `wp_formula` | 自定义底稿公式绑定（独立表，custom-workpaper-formula-binding） | D08（2）、D15（1） | D08（8）、D15（3） |

## D09 底稿（60 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `account_package_program_status` | 科目工作包程序状态 | D04（1） | D04（1） |
| `checklist_responses` |  | D09（65）、D10（5）、D13（2）、D15（2）、D03（1） | D09（226）、D13（6）、D10（5）、D08（5）、D15（4）、D03（2）、D14（1）、D02（1）、D12（1）、D11（1）、D06（1） |
| `custom_workbook_unit_authorities` |  | 未扫到 | 未扫到 |
| `editing_locks` | 通用编辑锁 | D15（1） | D15（1） |
| `gt_wp_coding` | 致同底稿编码 | D09（1） | D09（3） |
| `guidance_consumer_ack` | durable、幂等的 ConsumerAck ledger 行。 | D15（1） | 未扫到 |
| `guidance_exemption_record` | guidance 有效豁免记录。 | D15（1） | 未扫到 |
| `guidance_handoff_visibility` | finalize visibility saga 的 guidance 侧视图。 | D15（1） | 未扫到 |
| `guidance_publication` | guidance 发布主体。 | D15（1） | 未扫到 |
| `guidance_publication_event` | 发布生命周期事件。 | D15（1） | 未扫到 |
| `procedure_instance_identity_v217_backup` |  | 未扫到 | 未扫到 |
| `procedure_instances` | 审计程序实例（裁剪后的程序步骤） | D09（3）、D13（1） | D09（15）、D15（3）、D13（2） |
| `procedure_operation_previews` | 敏感操作 server-side 一次性预览凭证（裁剪/委派/转派）。 | D09（1） | D09（1） |
| `procedure_row_definition_revisions` | Revision membership: 哪些 definition_key 属于 (templat | 未扫到 | 未扫到 |
| `procedure_row_definitions` | 模板级程序行定义真源（跨项目稳定）。 | D09（3） | D09（4） |
| `procedure_row_task_history` | 程序行任务追加式历史（不可覆盖）。 | D09（2）、D15（1） | D09（3） |
| `procedure_row_tasks` | 项目级程序行任务真源（先委派后生成底稿）。 | D09（3） | D09（15）、D15（2）、D01（1）、D08（1）、D13（1） |
| `procedure_template_revisions` | Current-revision registry；每个 template_code 最多一个 ac | 未扫到 | 未扫到 |
| `procedure_trim_cycle_confirmations` | 每项目每循环当前粗裁确认投影；历史真源仍是 consumed preview。 | 未扫到 | 未扫到 |
| `procedure_trim_schemes` | 审计程序裁剪方案 | D09（1） | D09（2） |
| `project_guidance_supplement` | 项目级 guidance 补充。 | D02（1） | 未扫到 |
| `project_template_selections` | 项目模板选择记录 | D09（1） | D09（1） |
| `project_workbook_instance` |  | 未扫到 | D15（1） |
| `project_workbook_sheet_entry` |  | 未扫到 | D15（1） |
| `project_workpaper_sheet_override` | 项目级底稿 sheet 归类覆盖 | 未扫到 | D09（1） |
| `sampled_vouchers` | 抽样凭证（抽凭联动） | D03（1） | D12（2）、D03（1） |
| `sampling_config` | 抽样配置 | D12（1） | D12（1） |
| `sampling_records` | 抽样记录 | D12（2） | D12（4） |
| `template_library` | 模板库条目 | D09（1） | D09（4） |
| `working_paper` | 底稿文件 | D09（19）、D08（6）、D15（3）、D12（1）、D11（1）、D01（1）、D10（1）、D14（1） | D09（233）、D13（30）、D15（29）、D08（29）、D10（22）、D14（21）、D12（16）、D02（11）、D07（8）、D03（6）、D06（6）、D04（4）、D11（3）、D05（2）、D01（2） |
| `workpaper_delegation_history` | History_Set 唯一来源：append-only 委派历史快照。 | D15（1） | D15（1）、D08（1） |
| `workpaper_editing_locks` |  | 未扫到 | 未扫到 |
| `workpaper_extraction_log` | 底稿提取日志 — 记录截止测试/抽凭引擎的执行留痕和填充前快照，支持撤销功能。 | D03（1） | D12（4）、D03（1）、D13（1）、D15（1） |
| `workpaper_field_overrides` | 统一字段覆盖值 | D09（1）、D15（1） | D15（1）、D09（1） |
| `workpaper_generation_items` | 生成操作内的一份底稿及其可恢复文件 manifest。 | D09（1） | D09（2） |
| `workpaper_generation_operations` | 一次可恢复的底稿生成操作。 | D09（1） | D09（1） |
| `workpaper_lifecycle_events` | 一张底稿（wp_index + 名下 working_paper）的一次移入 / 恢复回收站。 | D09（1） | D09（1） |
| `workpaper_procedures` | 审计程序清单 | D09（1） | D09（2）、D13（1）、D12（1） |
| `workpaper_row_name_mapping` | 一行的行名对齐映射（版本行）。 | D04（1） | D04（1） |
| `workpaper_row_name_mapping_target` | 映射目标身份明细（让身份可 SQL 查询：判 stale / 多对一交集）。 | D04（1） | D04（1） |
| `workpaper_sheet_classification` | 底稿 sheet 归类（9 类：A~I） | 未扫到 | D09（2） |
| `workpaper_snapshots` | 底稿版本快照 — field-level 数据版本历史，支持时间线展示、diff 对比、回滚。 | D15（1） | D15（1）、D09（1） |
| `workpaper_template_override_version` |  | 未扫到 | 未扫到 |
| `workpaper_template_version` | 底稿模板版本 | 未扫到 | D09（1） |
| `wp_access_security_outbox` | 内部安全审计发件箱（append-only）：保留真实拒绝原因，对外统一 404/429。 | D15（1） | 未扫到 |
| `wp_cross_ref` | 底稿交叉引用 | 未扫到 | D09（5）、D15（1）、D13（1） |
| `wp_edit_sessions` | 底稿编辑时间采集（WOPI lock/unlock 自动记录）。 | 未扫到 | 未扫到 |
| `wp_export_snapshot` | 底稿导出快照 — 记录每次导出时的内容哈希，用于导入冲突检测 | D09（1） | D03（1）、D09（1） |
| `wp_index` | 底稿索引 | D09（8）、D15（2）、D11（1） | D09（90）、D08（30）、D13（20）、D15（20）、D12（15）、D14（13）、D07（8）、D06（8）、D02（5）、D10（5）、D05（5）、D03（4）、D04（3）、D01（2）、D11（2） |
| `wp_migration_snapshots` |  | D09（1） | D09（1） |
| `wp_recommendation_feedback` | 底稿推荐反馈记录（采纳/跳过/手动添加）。 | 未扫到 | 未扫到 |
| `wp_sheet_locks` |  | D09（1） | D09（1） |
| `wp_template` | 底稿模板 | D09（1） | D09（3） |
| `wp_template_custom` | 自定义底稿模板 | D09（1） | D09（1） |
| `wp_template_meta` | 模板元数据（命名区域定义） | D09（1） | 未扫到 |
| `wp_template_metadata` | 底稿模板元数据 | D09（2） | D09（4）、D15（1）、D08（1）、D14（1）、D13（1） |
| `wp_template_set` | 底稿模板集 | D09（2） | D09（6） |
| `wp_version_archive` | 底稿版本归档 — 记录版本元数据（文件可能已清理但元数据保留） | D09（1） | D03（1）、D09（1） |
| `wp_visibility_invalidation_outbox` | 可见性失效发件箱（append-only）：与 policy epoch 递增同事务写入。 | D15（1） | D15（1） |
| `wp_visibility_policy_epoch` | 每项目持久单调 policy epoch（可变；BEFORE UPDATE 触发器强制非递减）。 | D15（1） | D15（1） |

## D10 底稿在线编辑同步（30 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `working_paper_artifact` | 内容寻址不可变文件登记表。 | D10（3） | D10（15） |
| `working_paper_callback_delivery` | 每次 callback 投递。归属只以 immutable `durable_at` 判定。 | D10（1） | D10（4） |
| `working_paper_callback_recovery_case` | 无法唯一归组的 durable incoming 的可审计恢复案例。claim 前三实体恒空。 | D10（1） | D10（5） |
| `working_paper_callback_recovery_case_event` | recovery case 的独立 append-only timeline（与 operation | D10（1） | D10（1） |
| `working_paper_content_application` | durable incoming 对业务状态的一次逻辑应用；`application_key` 的唯 | D10（1） | D10（10） |
| `working_paper_content_application_event` | application 的 append-only timeline（含 `sequence_fol | D10（1） | D10（3） |
| `working_paper_content_representation` | 同一 content version 的 1:N immutable OOXML represent | D10（1） | D10（51） |
| `working_paper_content_revision_backfill_ledger` | V151 revision 0 回填台账：只记录，不创建 content version/repre | 未扫到 | 未扫到 |
| `working_paper_content_version` | immutable 业务内容版本。`revision` 只因业务 projection/权威内容变化 | D10（1） | D10（7） |
| `working_paper_entry_evidence_scenario` | 逐 scenario 证据行。download-only/recovery-reject 场景 op | D10（1） | D10（2） |
| `working_paper_forcesave_request` | Command Service 调用前冻结的 request。 | D10（1） | D10（7） |
| `working_paper_oo_client_confirmation` | DocEditor `onDocumentReady` 后的 descriptor 逐项确认。 | D10（1） | D10（4） |
| `working_paper_oo_close_intent` | clean close intent；只有 reconciler 可把 deterministic  | D10（1） | D10（4） |
| `working_paper_oo_close_intent_event` | close intent 的 append-only eligibility/leader time | D10（1） | D10（2） |
| `working_paper_oo_content_revision` |  | 未扫到 | 未扫到 |
| `working_paper_oo_participant` | 逐用户 participant lease。`closing` 是 close intent 创建时 | D10（1） | D10（7） |
| `working_paper_oo_room` | 共享 OO room：server last-applied 与 client-confirmed  | D10（1） | D10（11） |
| `working_paper_pending_mutation` | HTML flush 产生的短 TTL 单次逻辑消费 mutation token。 | D10（1） | D10（2） |
| `working_paper_representation_candidate_event` | candidate contract/bundle attach 的 append-only 审计事 | D10（1） | 未扫到 |
| `working_paper_representation_upgrade_candidate` | non-current representation 升级候选：resolver/room/curr | D10（1） | D10（5） |
| `working_paper_sync_conflict` | 字段级冲突记录（双侧可追溯 + canonical application fence）。 | D10（1） | D10（1） |
| `working_paper_sync_definition_artifact` | immutable template / instrumentation / contract /  | D10（1） | D10（11） |
| `working_paper_sync_definition_bundle` | authority model + template/instrumentation/contrac | D10（1） | D10（10） |
| `working_paper_sync_definition_null_marker` | optional child 的版本化 typed null marker registry（禁 S | 未扫到 | 未扫到 |
| `working_paper_sync_entry_state` | entry 级 current representation pointer（candidate 不 | D10（1） | D10（16） |
| `working_paper_sync_operation` | 用户轮询/执行/timeline 容器；**不承担** application identity。 | D10（2） | D10（13） |
| `working_paper_sync_operation_contributor` | 聚合 callback 的 contributor 快照（initiator / route / c | D10（1） | D10（1） |
| `working_paper_sync_operation_event` | operation 的 append-only transition event（current s | D10（1） | D10（1） |
| `working_paper_sync_scope_index` | authorization-before-business-read 的非敏感归属索引。 | D10（1） | D10（2） |
| `working_paper_sync_test_run` | 一次可复现验收执行（source-backed capability identity，禁自由文本覆 | D10（1） | D10（4） |

## D11 合并（36 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `companies` | 公司信息表 | 未扫到 | D11（2）、D15（1） |
| `component_auditors` | 组成部分审计师表 | D11（1） | D13（1）、D11（1） |
| `component_instructions` | 组成部分审计指令表 | D11（1） | D13（1）、D11（1） |
| `component_results` | 组成部分审计结果表 | D11（1） | D13（1）、D11（1） |
| `consol_artifact` | 绑定已发布 report run 的不可变合并 Excel artifact。 | D11（1） | D11（4） |
| `consol_cell_comments` | 单元格批注与复核标记 — 支持所有模块的单元格级批注和复核状态持久化 | D11（1） | D11（1） |
| `consol_note_data` | 合并附注用户数据存储 — 按项目+年度+章节存储用户编辑的附注数据 | D11（6）、D08（2） | D11（9）、D08（1） |
| `consol_note_detail_template` | 合并附注明细模板——按 template_type + section_id 组织。 | D11（1） | D11（4） |
| `consol_note_detail_template_version` | 模板不可变版本。rows JSONB 格式： | D11（1） | D11（6） |
| `consol_note_formula` | 合并附注单元格取数公式（语法同报表公式：TB / SUM_TB / REPORT / ROW）。 | D11（1）、D08（1） | D11（3）、D08（2） |
| `consol_note_mapping_binding` | 企业级绑定——记录每家企业确认使用哪条规则，以及绑定时的来源结构指纹。 | D11（1） | D11（11） |
| `consol_note_mapping_rule` | 映射规则。mappings JSONB 格式： | D11（1） | D11（6） |
| `consol_note_mapping_rule_template` |  | 未扫到 | 未扫到 |
| `consol_note_structure_lock` |  | 未扫到 | 未扫到 |
| `consol_note_structure_lock_entity` |  | 未扫到 | 未扫到 |
| `consol_note_template_binding` | 项目绑定到某一模板版本——一个项目一个章节只绑一个版本。 | D11（1） | D11（7） |
| `consol_note_template_push_log` | 合并附注模板推送日志 —— 仅 ORM 映射，写入走 raw SQL。 | D11（1） | 未扫到 |
| `consol_note_value_confirmation` |  | 未扫到 | 未扫到 |
| `consol_operation` | 一次可恢复、可比较输入版本的合并运行。 | D11（1） | D11（4）、D08（1） |
| `consol_push_run` | 合并推送运行记录（公式管理「合并推送」页）。 | D11（2） | D11（1） |
| `consol_query_template` | 自定义查询模板 | D11（1） | D11（1） |
| `consol_scope` | 合并范围表 | D11（2） | D11（2）、D08（1）、D07（1） |
| `consol_scope_confirmation_nodes` | 某确认版本中的角色投影；不是 projects 或金额数据的副本。 | D11（1） | 未扫到 |
| `consol_scope_confirmations` | 合并企业树版本（V183 起名「范围确认」；V206 起推送时自动记录，手动记录仍可）。 | D11（1） | D11（3） |
| `consol_snapshots` |  | D11（1） | D06（1）、D11（1） |
| `consol_trial` | 合并试算表 | D11（2）、D15（1） | D11（5）、D15（1） |
| `consol_workpaper_instance` | 合并项目/年度与 A3-CONSOL 薄底稿壳的关联及最近正式产物指针。 | D11（1） | D11（1） |
| `consol_worksheet` | 合并差额表 — 每个企业树节点 × 科目 × 年度一行。 | D11（1） | D11（7）、D15（1） |
| `consol_worksheet_data` | 合并工作底稿数据存储 — 通用 JSON 存储，支持所有 16 张表 | D11（3） | D11（9）、D08（1）、D15（1） |
| `elimination_entries` | 抵消分录表 | D11（3） | D11（8）、D13（1） |
| `forex_translation` | 外币折算表 | D11（1） | D11（1） |
| `goodwill_calc` | 商誉计算表 | D11（1） | D11（1） |
| `internal_ar_ap` | 内部往来表 | D11（1） | D11（1） |
| `internal_trade` | 内部交易表 | D11（1） | D11（1） |
| `minority_interest` | 少数股东权益表 | D11（1） | D11（1） |
| `share_change_event` | 动态股比变动事件。 | D02（1） | D02（1） |

## D12 附件、证据、函证与归档（47 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `ai_content_governance` | AiContentGovernance（design §4.6 / AIEvidenceGate；R | D12（1） | D14（1）、D12（1） |
| `archive_checklists` |  | 未扫到 | 未扫到 |
| `archive_jobs` | 归档编排作业 | D12（1） | D12（2） |
| `archive_manifest_edges` | ArchiveManifestEdge（design §4.6；R11/P23）—— manifes | D12（1） | D12（1） |
| `archive_manifest_entries` | ArchiveManifestEntry（design §4.6；R11/P23）—— manife | D12（1） | D12（1） |
| `archive_manifests` | ArchiveManifest（design §4.6/§5.5；R11/P24）—— sealed | D12（2） | D12（1） |
| `archive_modifications` |  | 未扫到 | 未扫到 |
| `asset_blobs` |  | D15（1） | D15（1） |
| `attachment_lineage` | 附件溯源关联 | D12（1） | D12（2）、D02（1） |
| `attachment_versions` | 不可变内容快照（design §4.3）。 | D12（5）、D14（1） | D12（11）、D05（1）、D02（1） |
| `attachment_working_paper` | 附件-底稿关联 | D12（1） | D12（3）、D11（1）、D02（1） |
| `attachments` | 附件 | D12（5）、D14（1）、D15（1） | D12（24）、D15（3）、D14（2）、D09（1）、D13（1）、D11（1）、D02（1） |
| `citation_snapshots` | CitationSnapshot（design §4.6；R7/P15/P16）—— 不可变（imm | D12（1） | D12（2） |
| `confirmation_action_log` | 函证操作审计留痕（append-only，DB 触发器禁 UPDATE/DELETE） | D12（2） | 未扫到 |
| `confirmation_ai_check` | 函证AI检查 | 未扫到 | 未扫到 |
| `confirmation_attachment_link` | 函证↔附件关联（含角色、强配对、匹配状态） | D12（1） | D12（2）、D13（1）、D02（1） |
| `confirmation_attachments` |  | 未扫到 | 未扫到 |
| `confirmation_letters` | 询证函模板/内容 | 未扫到 | 未扫到 |
| `confirmation_lists` |  | 未扫到 | 未扫到 |
| `confirmation_results` |  | 未扫到 | 未扫到 |
| `confirmation_summaries` | 询证函汇总 | 未扫到 | 未扫到 |
| `confirmations` | 函证记录 | D12（1） | D12（4）、D04（1）、D13（1）、D02（1） |
| `evidence_audit_command_roots` | command-root（design §7.1；R12/P25）—— 每敏感命令+幂等键+scop | 未扫到 | 未扫到 |
| `evidence_audit_transitions` | command-root 的多行 transition 审计（design §7.1；R12/P25 | D12（1） | D12（1） |
| `evidence_dependencies` | 统一依赖图的动态边 source→target（design §4.4；R9/P20）。 | D12（2） | D12（4） |
| `evidence_hash_checks` |  | D06（1） | D06（2）、D12（1） |
| `evidence_inbox` | inbox（design §5.4；R12）—— 按 event_id 幂等消费，避免重复副作用。 | 未扫到 | 未扫到 |
| `evidence_links` | 证据链 | D12（1） | D12（6）、D14（1）、D11（1）、D02（1） |
| `evidence_migration_checkpoints` | 迁移 checkpoint（design §8.2 M1；R14/P28）—— batch_key  | D12（1） | D12（1） |
| `evidence_outbox` | 事务性 outbox（design §5.4/§7.1；R12/R9）—— 按 event_id 幂 | 未扫到 | D12（1） |
| `evidence_quality_snapshots` | 质量快照（design §9；R16/P30）—— 固定不可变快照（immutable 触发器），可 | 未扫到 | 未扫到 |
| `evidence_quarantine_handles` | 隔离/暂存句柄 —— 内容不可公开读取（design §4.0）。 | D12（2） | D12（2） |
| `evidence_refs` | 持久 EvidenceRef（design §4.4；R3.1）—— 可查询、可保留的持久记录（非  | D12（2）、D06（1） | D12（10）、D13（1）、D05（1）、D14（1） |
| `evidence_tombstones` | 不可变墓碑 —— 对象被清理后保留的永久审计痕迹。 | D12（1） | 未扫到 |
| `evidence_upload_attempts` | UploadAttempt —— 内容验证前的最小上传审计（design §4.0 / R1.1 / | D12（1） | D12（1） |
| `legacy_attachment_alias` | 旧附件 ID → (新聚合根, 确定版本) 解析别名（design §4.1）。 | D12（3） | D12（3） |
| `legal_hold_scopes` | LegalHoldScope（design §4.6；R13/P26）—— 固化 direct/tr | D12（1） | D12（4） |
| `legal_holds` | LegalHold（design §4.6/§5.5；R13/P26/P27）—— released | D12（1） | D12（4） |
| `ocr_confirmations` | OCRConfirmation（design §4.5；R6.2/P12）—— append-onl | D12（1） | D12（3） |
| `ocr_job_transitions` | OCRJobTransition（design §4.5）—— 每次状态迁移一条，关联 comman | D12（2） | D12（1） |
| `ocr_jobs` | OCRJob（design §4.5；R5/P9）—— 绑定确定版本/hash/config/幂等键 | D12（1） | D12（5） |
| `ocr_results` | OCRResult（design §4.5；R6.1/P11）—— 不可变原始识别结果（immuta | D12（1） | D12（2） |
| `ocr_writeback_staging` | staged-external 写回暂存（design §4.5；R6.4/P13）—— 目标模块以 | D12（1） | D12（1） |
| `ocr_writebacks` | OCRWriteback（design §4.5；R6.4/P13/P14）—— 目标版本/mapp | D12（1） | D12（1） |
| `review_closes` | ReviewClose（design §4.6；R10.2/P21）—— closed_by_use | D13（1） | D13（1） |
| `review_evidence_snapshots` | ReviewEvidenceSnapshot（design §4.6；R10/P22）—— 冻结提出 | D13（1）、D12（1） | D13（1） |
| `service_identities` | 系统作业主体（Service Identity）—— actor XOR 的 service 侧 F | 未扫到 | D12（1） |

## D13 复核、质控与签字门禁（29 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `audit_check_signoff` | 审计检查复核门禁签认（audit-check-review-gate-hardening / V12 | D13（1） | D13（1） |
| `cell_annotations` |  | D02（2） | D02（3）、D13（2）、D09（1）、D06（1） |
| `consistency_gate_acknowledgements` | 门禁逐项确认留痕表 | D14（1） | D14（1）、D13（1） |
| `cross_check_results` | 跨科目校验结果 | D08（3） | D08（2）、D09（1） |
| `eqcr_disagreement_resolutions` | EQCR 与项目组意见不一致时触发的合议结论。 | D13（1） | D13（2） |
| `eqcr_opinions` | EQCR 对判断类事项的意见留痕。 | D13（2） | D13（7） |
| `eqcr_review_notes` | EQCR 独立复核笔记（默认仅 EQCR 可见）。 | D13（1） | D13（2） |
| `eqcr_shadow_computations` | EQCR 独立跑一遍勾稽的结果永久留痕。 | D13（1） | D13（2） |
| `eqcr_snapshots` | EQCR 快照 — 聚合项目数据供独立复核使用。 | D13（2） | D13（3） |
| `gate_decisions` | 门禁决策记录表 | D13（2） | D08（1）、D15（1） |
| `gate_rule_configs` | 门禁规则配置表 — 平台强制 vs 租户可配置分层 | 未扫到 | D13（2） |
| `independence_signing_tasks` | A17-7 独立性声明书电子签署任务 | D13（1） | D13（1） |
| `project_quality_ratings` | 项目质量评级 | D15（1） | D15（2）、D13（1） |
| `qc_case_library` | QC 案例库条目 | D13（1） | D13（1） |
| `qc_inspection_items` | 质控抽查子项 | D13（1） | D13（2） |
| `qc_inspection_records` | 质控独立复核记录 | 未扫到 | 未扫到 |
| `qc_inspections` | 质控抽查批次 | D13（1） | D13（2） |
| `qc_rule_definitions` | QC 规则定义表 — 元数据 + 开关 | D13（1） | D13（6） |
| `review_checklist_records` | 复核检查表记录（A21~A25 各级勾选+意见） | D13（1） | D13（1） |
| `review_conversations` |  | D09（1）、D13（1） | D09（2）、D13（2）、D02（1）、D15（1） |
| `review_messages` |  | D13（2）、D09（1） | D13（3）、D09（2）、D15（1） |
| `review_records` | 复核批注 | D13（1） | D13（3）、D12（2）、D02（2）、D15（2）、D01（1） |
| `review_templates` | 复核意见模板 | D13（1） | D13（1） |
| `review_threads` | V095: 复核对话线程 — 每个底稿区域一个线程 | D13（1） | D13（1） |
| `reviewer_metrics_snapshots` | 复核人深度指标快照 | D13（1） | D13（2） |
| `signature_records` | 签名记录 | D13（3） | D12（1）、D13（1） |
| `trace_events` | 统一过程留痕主表 | D15（1） | D15（1） |
| `workpaper_review_records` | 工作底稿复核记录 | 未扫到 | 未扫到 |
| `wp_qc_results` | 底稿质量自检结果 | D13（1） | D13（4）、D15（2）、D08（1）、D02（1）、D09（1） |

## D14 AI 与知识库（33 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `ai_analysis_item` | AI分析报告条目 | 未扫到 | 未扫到 |
| `ai_analysis_report` | AI分析报告 | 未扫到 | 未扫到 |
| `ai_chat_action_receipts` | note save / adopt 的通用幂等收据（Req 8.2/8.3 · Property 2 | D14（1） | D14（1） |
| `ai_chat_attachments` | 会话附件 metadata（Req 7.3）。 | D14（1） | D14（1） |
| `ai_chat_history` | AI对话历史 | 未扫到 | 未扫到 |
| `ai_chat_mcp_call_log` |  | 未扫到 | 未扫到 |
| `ai_chat_mcp_token_revocations` |  | 未扫到 | 未扫到 |
| `ai_chat_message` | AI问答消息（详细消息记录） | D14（3） | D14（5） |
| `ai_chat_run_resources` |  | D14（1） | D14（1） |
| `ai_chat_runs` | Chat Run —— 一次模型/Agent 执行的持久化摘要。 | D14（3） | D14（4） |
| `ai_chat_session` | AI问答会话（会话维度聚合） | D14（3） | D14（3） |
| `ai_chat_tool_calls` | 工具调用摘要（Req 11.10：每次调用产生 started + finished/failed  | 未扫到 | 未扫到 |
| `ai_confirmation_audit` | AI函证审核记录 | 未扫到 | 未扫到 |
| `ai_content` | AI生成内容 | D13（5）、D14（1）、D09（1）、D15（1）、D07（1） | D13（2）、D15（1） |
| `ai_content_log` | AI 生成内容溯源日志 — 字段级追踪 AI 输出及人工确认状态 | D12（1）、D14（1） | D14（5）、D15（3）、D12（2）、D04（1）、D06（1）、D09（1） |
| `ai_evidence_chains` | AI证据链 | 未扫到 | 未扫到 |
| `ai_evidence_items` | AI证据项 | 未扫到 | 未扫到 |
| `ai_knowledge_base` | AI知识库文档索引 | 未扫到 | 未扫到 |
| `ai_model_config` | AI模型配置 | D14（2）、D15（1） | D14（3）、D15（1）、D12（1） |
| `ai_plugins` | AI插件 | D14（1） | D14（1） |
| `ai_task_items` |  | D14（1） | D14（3） |
| `ai_task_jobs` |  | 未扫到 | D14（3）、D13（1） |
| `ai_workpaper_fills` | AI底稿填充记录 | D02（1） | D02（1） |
| `ai_workpaper_tasks` | AI底稿填充任务 | D02（1） | D02（1） |
| `document_extracted` | 单据结构化提取数据 | D14（1） | D14（1） |
| `document_match` | 单据与账面数据匹配 | D14（1） | 未扫到 |
| `document_scan` | 单据扫描件 | D14（1） | D15（1） |
| `evidence_chain` | 证据链 | 未扫到 | 未扫到 |
| `knowledge_documents` | 知识库文档 | D14（2） | D14（12）、D07（1）、D15（1） |
| `knowledge_evidence_promotions` |  | D14（1） | D14（1） |
| `knowledge_folders` | 知识库文件夹（树形目录） | D14（2） | D14（9） |
| `knowledge_index` | 知识库索引 | D14（2）、D15（2） | D14（3）、D15（1） |
| `wp_ai_generations` | AI生成历史记录，完整留痕每次生成的prompt/model/输出/确认信息。 | D09（1） | D13（1）、D09（1） |

## D15 后台任务与基础设施（21 张）

| 表 | 说明 | 写入业务 | 读取业务 |
|---|---|---|---|
| `acnr_invalidation_epoch` | ACNR Durable_Epoch — per-project 失效计数器（DB 权威，Redis | D08（1） | D08（1） |
| `acnr_invalidation_outbox` | ACNR Invalidation_Outbox — 业务变更同事务写入，dispatcher 至少 | D08（1） | D08（1） |
| `app_audit_log` |  | D13（3）、D02（3）、D01（2） | D02（1） |
| `audit_chain_head` | 每条审计链的事务内权威链尾。 | D15（1） | 未扫到 |
| `audit_log_entries` | 审计日志条目 — 不可变追加式 | D15（2） | D15（4）、D08（3）、D11（2）、D09（2）、D02（1）、D13（1） |
| `background_job_items` | 后台长任务明细项。 | D15（1） | D15（1） |
| `background_jobs` | 后台长任务主表（批量刷新/生成/提交/下载等）。 | D15（1） | D13（1）、D15（1） |
| `chain_executions` | 全链路执行记录 | D15（1）、D07（1） | D15（1）、D07（1） |
| `cross_module_conflicts` | 跨模块冲突调解记录 — 上游数据变更与手工覆盖的冲突追踪 | D15（1） | D15（2） |
| `data_snapshots` |  | D07（1） | D07（1） |
| `event_cascade_log` |  | D15（1） | D15（2） |
| `feature_flags` | Feature flag 功能开关（zero-downtime-deployment 组件 8）。 | D15（1） | D15（1） |
| `offline_conflicts` |  | D15（1） | D15（1） |
| `platform_job_attempts` |  | D15（1） | 未扫到 |
| `platform_jobs` |  | D15（1） | D15（2）、D06（1） |
| `schema_drift_log` |  | D15（1） | D15（1） |
| `schema_migration_failures` |  | D15（1） | D15（1） |
| `schema_version` |  | D15（1） | D15（1） |
| `system_settings` |  | 未扫到 | D15（2）、D13（1） |
| `time_machine_snapshots` | 时光机增量快照 — RFC 6902 JSON Patch 反向 diff | D15（1） | D15（1） |
| `version_line_stamps` |  | D02（1） | D02（1） |

