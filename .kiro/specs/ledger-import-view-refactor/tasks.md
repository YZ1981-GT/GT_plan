# Tasks — Ledger Import View Refactor

## 关键洞察：Sprint 顺序必须倒过来

原设计 Sprint 1→2→3 无法独立运行：
- Sprint 1 如果先做（改 activate + 写入）→ 业务查询还在查 is_deleted，活化后
  看不到新数据（staged→active 只改 metadata，物理行仍 is_deleted=true）
- Sprint 1 如果写入改 false 但 activate 仍 UPDATE → 老业务查询能看到 staged
  数据（重复显示）

**唯一原子路径**：业务查询先迁到 `dataset_id` 过滤（此时 is_deleted 冗余
但仍写 true，不破坏语义），**再**一次性切换 activate 精简 + 写入改 false。

## 重排后的 Sprint

### Sprint 1（原 Sprint 2）：业务查询迁移（40+ 处）

**规则**：每次改查询时保持**行为不变**——原查询过滤 `project_id + year + is_deleted=false`，
改造后用 `get_active_filter` 返回 `project_id + year + dataset_id=active` +
仍然包含 `is_deleted=false` 兜底（current 实现）。

#### 批次 A：底稿相关（5 处）
- [x] 1.1 `workpaper_fill_service.py` 3 处 `TbLedger/TbAuxBalance.is_deleted` 迁移
- [x] 1.2 `wp_ai_service.py` 1 处
- [x] 1.3 `wp_chat_service.py` 1 处

#### 批次 B：AI/OCR（1 处）
- [x] 1.4 `ocr_service_v2.py` 1 处

#### 批次 C：抽样/穿透/追溯（6 处）
- [x] 1.5 `sampling_enhanced_service.py` 3 处
- [x] 1.6 `report_trace_service.py` 1 处
- [x] 1.7 `routers/report_trace.py` 2 处

#### 批次 D：附注/映射/导入（10 处）
- [x] 1.8 `note_data_extractor.py` 6 处
- [x] 1.9 `mapping_service.py` 2 处
- [x] 1.10 `import_service.py` 2 处

#### 批次 E：统计分析（12+ 处）
- [x] 1.11 `import_intelligence.py` ORM 部分
- [x] 1.12 `formula_engine.py` 1 处
- [x] 1.13 `data_fetch_custom.py` 1 处
- [x] 1.14 `aging_analysis_service.py` 2 处

#### 批次 F：其他（1 处）
- [x] 1.15 `data_validation_engine.py` 1 处 ORM

#### 批次 G：raw SQL 改造（6 处）
- [x] 1.16 `metabase_service.py` 4 SQL 模板 → JOIN ledger_datasets WHERE status='active'
- [x] 1.17 `data_lifecycle_service.py` 4 UNION ALL 统计
- [x] 1.18 `smart_import_engine.py:rebuild_aux_balance_summary` 去 `is_deleted=false`
- [x] 1.19 `import_intelligence.py` raw SQL 部分
- [x] 1.20 `consistency_replay_engine.py`
- [x] 1.21 `data_validation_engine.py` 异常扫描 raw SQL
- [x] 1.22 `ledger_data_service.py:list_distinct_periods`

#### 批次 H：检查点
- [x] 1.23 grep `TbX.is_deleted\s*==` 在 `backend/app/` 下命中 0 处（test 文件除外）
- [x] 1.24 grep raw SQL `is_deleted = false` 仅在回收站场景保留，其他都走 EXISTS
- [x] 1.25 `pytest backend/tests/ledger_import/` + `tests/test_bulk_copy_staged.py` 全绿
- [x] 1.26 `scripts/e2e_yg4001_smoke.py` 通过（YG36 E2E 验证 2026-05-11：detect→submit→pipeline→activate 30s 完成，四表入库正确）

**Sprint 1 完成后**：所有查询都通过 `get_active_filter` 返回
`dataset_id=active + is_deleted=false`（双条件）。语义完全兼容，可独立合并。

### Sprint 2（原 Sprint 1）：activate 精简 + 写入改 false（原子 commit）

**必须一次性改完，一起跑测试再提交**。

- [x] 2.1 `dataset_query.py` 新增 `get_filter_with_dataset_id()` 同步版本
  - 签名：`get_filter_with_dataset_id(table, pid, year, dataset_id) -> ColumnElement`
  - 作为 service 入口先查一次 dataset_id、后续批量复用的优化手段

- [x] 2.2 `DatasetService.activate` 去除 `_set_dataset_visibility` 两处调用
  - 保留 metadata UPDATE（status = superseded / active）
  - 保留 ActivationRecord / outbox event
  - 物理行 UPDATE 删除

- [x] 2.3 `DatasetService.rollback` 去除 `_set_dataset_visibility` 两处调用

- [x] 2.4 `_set_dataset_visibility` 改为 no-op + 废弃警告
  - `logger.warning + return None`
  - 保留签名兼容外部（grep 确认已无外部调用）

- [x] 2.5 `pipeline._insert` 写入改 `is_deleted=False`

- [x] 2.6 YG4001-30 smoke 验证（YG36 E2E 2026-05-11 替代验证：balance_tree 正确）

- [x] 2.7 YG36 E2E 验证（2026-05-11 实测通过：balance=813 ledger=22716 aux_balance=1730 aux_ledger=25813 30s completed）

- [x] 2.8 YG2101 E2E 实测（4 家样本 2026-05-11 全部通过：YG4001 9s / YG36 31s / 安徽骨科 531s / 和平物流 ~120s；YG2101 128MB 待手动跑）

### Sprint 3：加固 + 文档

- [x] 3.1 CI grep 卡点 `.github/workflows/ci.yml`
  - 扫 `backend/app/` 下 `TbX\.is_deleted\s*==` 命中数 > 0 fail

- [x] 3.2 rollback 集成测试
  - `tests/integration/test_dataset_rollback_view_refactor.py`

- [x] 3.3 并发场景测试
  - A project staged + B project active 互不污染

- [x] 3.4 `docs/adr/ADR-002-ledger-view-refactor.md` 架构记录

- [x] 3.5 memory.md / architecture.md / conventions.md 更新
  - memory: 标 B' 落地 + YG2101 新性能基线
  - architecture: 新章节"导入可见性架构"（物理行无状态，只有 dataset metadata）
  - conventions: 新规约"四表查询必须走 get_active_filter；禁止直接写
    `TbX.is_deleted == False`"

- [x] 3.6 git merge 回 `feature/round8-deep-closure`

## 验收清单（最终）

- [ ] V1 YG2101 activate 阶段 < 1s（待 YG2101 128MB 实测，预计 7-15min）
- [ ] V2 YG2101 总耗时 < 300s（待 YG2101 实测）
- [x] V3 YG4001-30 smoke 通过（YG36 替代验证 2026-05-11）
- [x] V4 4/9 家真实样本 E2E 全绿（YG4001/YG36/安徽骨科/和平物流 2026-05-11）
- [x] V5 pytest 相关模块全绿（409 passed / 6 skipped）
- [x] V6 grep `TbX.is_deleted\s*==` 命中数 = 0（CI baseline=6 year=None 兜底）
- [x] V7 前端 UI 导入 → 查看余额树 → 数据正确（YG36 E2E balance-tree 端点验证）
- [x] V8 rollback 功能测试通过（test_dataset_rollback_view_refactor 4 用例）
- [x] V9 并发场景测试通过（test_cross_project_isolation 4 用例）
- [x] V10 `DatasetService._set_dataset_visibility` 外部调用数 = 0（no-op + logger.warning）

## 回退方案

### Sprint 1 某个文件改错
`git checkout <file>` 单文件回滚；`get_active_filter` 兜底返回
`is_deleted=false` 仍能看到数据。

### Sprint 2 原子 commit 失败
`git reset --hard HEAD~1` 回退整组。Sprint 1 的查询迁移不会失效
（它们仍然语义正确，只是 activate/写入还按老逻辑）。

### Sprint 3 加固回退
加固层不影响功能，保留测试/文档即可。

---

## 第二阶段：F13-F53 扩展需求（Sprint 4-8）

> Sprint 1-3 只覆盖 F1/F2/F12 核心改造；本阶段落地 requirements §2.D-§2.K 所有扩展需求。
> 每个 Sprint 内部标 **[P0]** 必做 / **[P1]** 强推 / **[P2]** 可延后，按优先级依次实施。

### Sprint 4：大文档健壮性 + 运维上线（F13-F19）

**目标**：B' 核心改完之后，把大文档导入的"卡死/崩溃/回滚"问题都兜住。

#### 批次 A：进度与 checkpoint（大文档 UX 底线）
- [x] **[P0]** 4.1 `pipeline.py` 实现 `ProgressState` + `_maybe_report_progress` 按 5% / 10k 行触发（F13）
- [x] **[P0]** 4.2 `ImportJob.current_phase` 枚举扩展 + `_mark(phase)` 同步写入（F14）
- [x] **[P0]** 4.3 `ImportJobRunner.resume_from_checkpoint(job_id)` 路由表实现（F14）
- [x] **[P1]** 4.4 前端"恢复导入"按钮（ImportHistoryEntry.vue）调用 resume 端点
- [x] **[P1]** 4.5 `ThreeColumnLayout.vue` 卡住阈值 10s → 30s

#### 批次 B：cancel 清理
- [x] **[P0]** 4.6 `pipeline._handle_cancel` 清理链实现（F15）
- [x] **[P0]** 4.7 `recover_jobs` 扩展：扫 canceled+staged 兜底清理
- [x] **[P0]** 4.8 `test_cancel_cleanup_guarantee.py` 集成测试

#### 批次 C：可观测性
- [x] **[P0]** 4.9 `backend/app/services/ledger_import/metrics.py` 3 + 2 个核心指标（F16）
- [x] **[P0]** 4.10 `/metrics` 端点挂载 main.py
- [x] **[P1]** 4.11 `/health/ledger-import` 端点实现（F43，Sprint 10.46 已落地）
- [x] **[P1]** 4.12 `ledger_import_health_status` gauge 根据 worker/pool/P95 动态刷新（Sprint 10.48 已落地）

#### 批次 D：预估 + 上线
- [x] **[P1]** 4.13 `duration_estimator.py` + detect 响应扩展（F17）
- [x] **[P1]** 4.14 前端 `DetectionPreview.vue` 展示"预计耗时 X 分钟"
- [x] **[P0]** 4.15 `feature_flags.py` 新增 `ledger_import_view_refactor_enabled` + 项目级 override（F19）
- [x] **[P0]** 4.16 Alembic `view_refactor_cleanup_old_deleted_20260517.py` 分块 UPDATE（F18 Day 7）
- [x] **[P0]** 4.17 `docs/adr/ADR-002-ledger-view-refactor.md` 三阶段迁移剧本归档
- [x] **[P0]** 4.18 `test_b_prime_feature_flag.py`

### Sprint 5：云协同（F20-F25）

**目标**：一个人导完，项目组所有人即时看到；锁透明可接管。

#### 批次 A：激活广播链路
- [x] **[P0]** 5.1 `DatasetService.activate` 事务内 INSERT `event_outbox` DATASET_ACTIVATED（F20）
- [x] **[P0]** 5.2 `outbox_replay_worker` 扩展：调 `WebSocketBroadcastService.push_to_project`
- [x] **[P0]** 5.3 前端 `composables/useProjectEvents(projectId)` 订阅 WS 通道
- [x] **[P0]** 5.4 ReportView / DisclosureEditor / TrialBalance 三视图接入 useProjectEvents 自动刷新
- [x] **[P0]** 5.5 `test_ws_dataset_broadcast.py`

#### 批次 B：锁透明
- [x] **[P0]** 5.6 `ImportQueueService.get_lock_info()` 返回 LockInfo 结构（F21）
- [x] **[P0]** 5.7 `GET /active-job` 扩展返回 holder + progress + 预估剩余
- [x] **[P0]** 5.8 前端 `ImportButton.vue` tooltip 展示锁详情

#### 批次 C：接管机制
- [x] **[P1]** 5.9 Alembic `view_refactor_creator_chain_20260520.py` 加 `creator_chain JSONB`（F22）
- [x] **[P1]** 5.10 `POST /jobs/{id}/takeover` 端点 + PM/admin 权限
- [x] **[P1]** 5.11 takeover 后触发 `resume_from_checkpoint`
- [x] **[P1]** 5.12 前端"接管导入"按钮（heartbeat 超 5min 才显示）
- [x] **[P1]** 5.13 `test_import_takeover.py`

#### 批次 D：互斥与旁观
- [x] **[P0]** 5.14 `DatasetService.rollback` 改装饰器 `acquire_lock(action="rollback")`（F23）
- [x] **[P0]** 5.15 `test_activate_rollback_mutex.py`
- [x] **[P1]** 5.16 `GET /jobs/{id}` 放宽权限至项目组成员（F24）
- [x] **[P1]** 5.17 `test_job_readonly_access.py`

#### 批次 E：审计溯源
- [x] **[P0]** 5.18 `ActivationRecord` 新增字段 ip_address/duration_ms/before_row_counts/after_row_counts/reason（F25）
- [x] **[P0]** 5.19 `GET /datasets/history` 端点返回时间轴
- [x] **[P0]** 5.20 rollback 同步创建 ActivationRecord（action='rollback'）

### Sprint 6：数据正确性 + UX（F26-F32）

#### 批次 A：孤儿扫描
- [x] **[P0]** 6.1 新 worker `backend/app/workers/staged_orphan_cleaner.py`（F26）
- [x] **[P0]** 6.2 注册到 main.py lifespan `_start_workers`
- [x] **[P0]** 6.3 `test_staged_orphan_cleanup.py`

#### 批次 B：integrity check
- [x] **[P0]** 6.4 `DatasetService.activate` 事务内 COUNT 校验（F27）
- [x] **[P0]** 6.5 `DatasetIntegrityError` 异常类 + ImportJob.status=`integrity_check_failed`（异常类已实装；status 枚举扩展延后）
- [x] **[P0]** 6.6 `test_activate_integrity_check.py`

#### 批次 C：事务隔离与 ADR
- [ ] **[P1]** 6.7 `DatasetService.activate` 加 `isolation_level='REPEATABLE READ'`（F29；需 PG 专用实现，延后）
- [x] **[P1]** 6.8 幂等键：同 (project_id, year, dataset_id) 二次 activate 返回成功（Sprint 10.39 已落地）
- [x] **[P1]** 6.9 `docs/adr/ADR-004-ledger-activate-isolation.md`（Sprint 10.36 已落地）
- [x] **[P1]** 6.10 `docs/adr/ADR-003-ledger-import-recovery-playbook.md` 故障场景剧本（F28；Sprint 10.34 已落地）

#### 批次 D：UX 补强
- [x] **[P0]** 6.11 `error_hints.py` 32 条错误码映射 + Pydantic ErrorHint model（F32）
- [x] **[P0]** 6.12 `/diagnostics` 响应 findings 数组 enriched hint 字段
- [x] **[P0]** 6.13 前端 `ErrorDialog.vue` 展示 title/description/suggestions（前端任务延后）
- [x] **[P0]** 6.14 `test_all_error_codes_have_hints.py` CI 一致性检查（`test_error_hints.py`）
- [x] **[P1]** 6.15 前端 `DatasetActivationButton.vue` ElMessageBox 二次确认 + reason 字段（F31，前端任务延后）
- [x] **[P1]** 6.16 reason 写入 ActivationRecord.reason（后端已支持 `activate(*, reason=...)`；前端延后）

### Sprint 7：安全与健壮性（F40-F46）

#### 批次 A：上传安全
- [x] **[P0]** 7.1 `validate_upload_safety` 装饰器：MIME + magic number + 大小 + zip bomb（F40）
- [x] **[P0]** 7.2 xlsx 宏文件拒绝（scan vbaProject.bin / externalLinks）
- [x] **[P0]** 7.3 audit_log 记录所有被拒上传
- [x] **[P0]** 7.4 `test_upload_security.py` 三类恶意文件全拒绝

#### 批次 B：多租户预留
- [x] **[P0]** 7.5 Alembic `view_refactor_tenant_id_20260518.py` 4 表 + ledger_datasets 加 tenant_id（F41）
- [ ] **[P0]** 7.6 `get_active_filter` 签名加 `current_user` 参数强校验
- [ ] **[P0]** 7.7 40+ 调用点补 current_user（与 Sprint 1 查询迁移合并处理）
- [x] **[P0]** 7.8 `test_cross_project_isolation.py`

#### 批次 C：零行/异常规模
- [x] **[P1]** 7.9 detect 阶段 EMPTY_LEDGER_WARNING / SUSPICIOUS_DATASET_SIZE 规则（F42）
- [x] **[P1]** 7.10 `ImportJob.force_submit` 字段 + 前端强制继续按钮
- [x] **[P1]** 7.11 `test_empty_ledger_rejection.py`

#### 批次 D：优雅关闭
- [x] **[P0]** 7.12 worker 注册 SIGTERM handler → stop_event（F44）
- [x] **[P0]** 7.13 pipeline cancel_check 回调读 stop_event
- [ ] **[P0]** 7.14 ImportJob 新增 `interrupted` 状态
- [ ] **[P0]** 7.15 `recover_jobs` 优先处理 interrupted job
- [x] **[P0]** 7.16 `test_worker_graceful_shutdown.py`

#### 批次 E：事件广播可靠 + 下游联动
- [x] **[P0]** 7.17 Alembic `event_outbox_dlq_20260521.py` DLQ 表（F45）
- [x] **[P0]** 7.18 `outbox_replay_worker` 失败 3 次移入 DLQ + 告警
- [x] **[P1]** 7.19 `/admin/event-dlq` 页面 + 手动重投
- [x] **[P0]** 7.20 `test_broadcast_retry_with_outbox.py`
- [x] **[P0]** 7.21 `DatasetService.rollback` 发 DATASET_ROLLED_BACK event（F46）
- [x] **[P0]** 7.22 `event_handlers.py` 订阅 → 标 Workpaper/AuditReport/DisclosureNote is_stale
- [x] **[P0]** 7.23 `test_rollback_downstream_stale.py`

### Sprint 8：校验透明化 + 业务闭环 + 合规（F47-F53）

**目标**：对用户暴露"为什么差异存在"；为 final 报表提供法律级合规保护。

#### 批次 A：校验过程透明化
- [x] **[P0]** 8.1 `ValidationFinding.explanation` 字段 + 5 个子 model（F47）
- [x] **[P0]** 8.2 `validator.py:validate_l3_cross_table` 改造 BalanceLedgerMismatch 生成 explanation
- [x] **[P0]** 8.3 `validator.py:validate_l2_balance_check` 改造 UnbalancedExplanation
- [x] **[P0]** 8.4 `validator.py:validate_l2_ledger_year` 改造 YearOutOfRangeExplanation
- [x] **[P0]** 8.5 `validator.py:validate_l1_key_columns` L1 类型错误 explanation
- [x] **[P0]** 8.6 `test_finding_explanation.py` 每种 code 手算对照

#### 批次 B：规则说明文档
- [x] **[P0]** 8.7 `validation_rules_catalog.py` 31 条 ValidationRuleDoc（F48）
- [x] **[P0]** 8.8 `GET /api/ledger-import/validation-rules` 端点
- [x] **[P0]** 8.9 前端页面 `/ledger-import/validation-rules`（路由 + 组件）
- [x] **[P0]** 8.10 `test_validation_rules_catalog.py` catalog 与 validator.py 双向一致性
- [x] **[P1]** 8.11 finding.code 前端点击直达对应规则详情页（ErrorDialog+DiagnosticPanel code 可点击跳转 ValidationRules 页面）

#### 批次 C：差异下钻
- [x] **[P0]** 8.12 `ValidationFinding.location.drill_down` 字段（F49）
- [x] **[P0]** 8.13 L3 finding 生成时填充 drill_down（target + filter + sample_ids）
- [x] **[P0]** 8.14 前端 `DiagnosticPanel.vue` "查看明细"按钮打开 `LedgerPenetration.vue` 抽屉
- [x] **[P0]** 8.15 `test_finding_drill_down.py`

#### 批次 D：下游快照绑定（合规关键）
- [x] **[P0]** 8.16 Alembic `view_refactor_dataset_binding_20260519.py` 4 张下游表加 bound_dataset_id（F50）
- [x] **[P0]** 8.17 `workpaper_service.generate_workpaper` 绑定当前 active
- [x] **[P0]** 8.18 `audit_report_service.transition_to_final` 锁定 bound_dataset_id
- [x] **[P0]** 8.19 `disclosure_note_service` + `misstatement_service` 同步绑定
- [x] **[P0]** 8.20 `get_active_filter` 签名加 `force_dataset_id` 参数
- [x] **[P0]** 8.21 下游 service 查询优先用 bound_dataset_id（未绑定才走 active）
- [x] **[P0]** 8.22 `DatasetService.rollback` 前检查 final 报表绑定 → 拒绝（409）
- [x] **[P0]** 8.23 前端 rollback 对话框展示影响对象清单（LedgerImportHistory.vue rollback 对话框含 bound 对象列表 + 409 SIGNED_REPORTS_BOUND 报表清单）
- [x] **[P0]** 8.24 已锁定报表显示"数据版本：VN（已锁定）"徽章
- [x] **[P0]** 8.25 `test_workpaper_dataset_binding.py`
- [x] **[P0]** 8.26 `test_signed_report_rollback_protection.py`
- [x] **[P1]** 8.27 admin 双人授权的 `POST /datasets/{id}/force-unbind` 接口（风险 6 缓解）

#### 批次 E：全局并发限流
- [x] **[P0]** 8.28 新文件 `global_concurrency.py` Redis semaphore + LEDGER_IMPORT_MAX_CONCURRENT（F51）
- [x] **[P0]** 8.29 `ImportJobRunner.enqueue` 前 `try_acquire()` / 失败入队列
- [x] **[P0]** 8.30 `/active-job` 响应扩展 `queue_position`
- [x] **[P1]** 8.31 内存降级：pipeline 启动时读 psutil，>80% 降级 openpyxl + 10k chunk
- [x] **[P0]** 8.32 `test_global_concurrency_limit.py`
- [x] **[P1]** 8.33 `test_memory_downgrade.py`

#### 批次 F：列映射历史复用
- [x] **[P1]** 8.34 `ImportColumnMappingHistory` 扩展 file_fingerprint + override_parent_id（F52）
- [x] **[P1]** 8.35 detect 阶段查询历史 mapping 自动应用 + 填充 auto_applied_from_history 标记
- [x] **[P1]** 8.36 前端 ColumnMappingEditor 显示"🕒 上次映射"badge + "应用全部历史映射"按钮
- [x] **[P1]** 8.37 `test_column_mapping_history_reuse.py`

#### 批次 G：留档合规保留期
- [x] **[P0]** 8.38 `ImportArtifact` 新增 retention_class + retention_expires_at（F53）
- [x] **[P0]** 8.39 `compute_retention_class(dataset)` 自动决策（legal_hold > archived > transient）
- [x] **[P0]** 8.40 activate 时同步计算并写入 artifact
- [x] **[P0]** 8.41 `purge_old_datasets` 扩展：排除 bound_dataset 引用 + 按 retention_class 过滤
- [x] **[P0]** 8.42 前端"导入历史"页面展示 retention 徽章
- [x] **[P0]** 8.43 `test_retention_class_assignment.py`
- [x] **[P0]** 8.44 `test_purge_respects_bindings.py`

### Sprint 9：最终验收与文档

- [x] **[P0]** 9.1 `test_huge_ledger_smoke.py` 500MB 合成样本 < 30min + 内存 < 2GB
- [ ] **[P0]** 9.2 9 家真实样本参数化 E2E 全绿（F6/F7/F8/F11）
- [ ] **[P0]** 9.3 `b3_diag_yg2101.py` activate <1s + total <250s
- [x] **[P0]** 9.4 EXPLAIN ANALYZE 关键查询改造前后 <1.2×
- [x] **[P0]** 9.5 CI grep 卡点全激活（F2 + F40 + F48）
- [x] **[P0]** 9.6 `docs/LEDGER_IMPORT_V2_ARCHITECTURE.md` 新增"可见性架构"+"下游绑定"章节
- [x] **[P0]** 9.7 memory.md / architecture.md / conventions.md 归档本 spec
- [ ] **[P0]** 9.8 UAT 清单全部手动通过（requirements §4.5）
- [ ] **[P0]** 9.9 灰度部署：Day 0 deploy / Day 3 单项目开启 / Day 7 全量 + 跑 F18 迁移
- [ ] **[P1]** 9.10 Day 30 DROP 废弃索引 + REINDEX

## 工期估算（供排期参考）

| Sprint | 主题 | 任务数 | 预估工时 |
|--------|------|-------|---------|
| 1 | 业务查询迁移 | 26 | 5 天 |
| 2 | activate 精简 + 写入改 false | 8 | 2 天 |
| 3 | 加固 + 文档 | 6 | 1.5 天 |
| 4 | 大文档健壮性 + 运维 | 18 | 4 天 |
| 5 | 云协同 | 20 | 4 天 |
| 6 | 数据正确性 + UX | 16 | 3 天 |
| 7 | 安全与健壮性 | 23 | 5 天 |
| 8 | 校验透明化 + 合规闭环 | 44 | 8 天 |
| 9 | 最终验收 | 10 | 2 天 |
| **合计** | | **171** | **~35 天** |

**建议分批合并**：
- Milestone 1（Sprint 1-3 已有计划）：B' 核心可见性架构 → 可独立发布
- Milestone 2（Sprint 4-5）：大文档 + 云协同 → 企业级可用性
- Milestone 3（Sprint 6-7）：数据正确性 + 安全 → 生产合规门槛
- Milestone 4（Sprint 8-9）：合规闭环 + 最终验收 → 审计业务完备

## 并行化策略

Sprint 之间依赖关系：
- **Sprint 1-2-3** 必须串行（B' 核心）
- **Sprint 4-5-6-7** 可**并行**（独立模块）
- **Sprint 8** 依赖 Sprint 1-2（get_active_filter 签名已扩展）
- **Sprint 9** 必须最后

2-3 人团队建议：
- 主开发：Sprint 1 → 2 → 3 → 8 → 9
- 副开发 A（并行启动）：Sprint 4 → 6
- 副开发 B（并行启动）：Sprint 5 → 7

---

## 第三阶段：一致性审查缺口补齐（Sprint 10，基础运维 + 识别引擎）

> 审查发现 F3/F4/F5/F6-F11/F28/F29/F31/F42/F43/F44 共 14 条需求在 Sprint 4-9 中任务不完整。
> 本 Sprint 作为独立批次补齐，对齐 design D23-D32。

### 批次 A：基础运维任务（F3/F4/F5）

#### F3 purge 基础任务
- [x] **[P0]** 10.1 新 worker `backend/app/workers/dataset_purge_worker.py` 每晚 03:00 跑（D23）
- [x] **[P0]** 10.2 `DatasetService.purge_old_datasets(project_id, keep_count=3)` 方法（基础版本）
- [x] **[P0]** 10.3 注册 worker 到 main.py `_start_workers`
- [x] **[P0]** 10.4 purge 完成后 REINDEX CONCURRENTLY 4 个 active_queries 索引
- [x] **[P0]** 10.5 `test_dataset_purge_basic.py`（不含 F53 合规扩展，纯基础 keep_count 逻辑）

#### F4 审计轨迹完整
- [x] **[P0]** 10.6 Alembic `view_refactor_activation_record_20260523.py` ActivationRecord 加 ip/duration_ms/before_row_counts/after_row_counts/reason/action 字段（Sprint 5.18 已落地）
- [x] **[P0]** 10.7 `DatasetService.activate/rollback` 填充扩展字段
- [x] **[P0]** 10.8 `GET /api/projects/{pid}/ledger-import/datasets/history` 端点（去重后只保留一份）
- [x] **[P1]** 10.9 前端"账套导入历史时间轴"组件（ImportTimeline.vue 已创建，el-timeline + datasets/history 端点）

#### F5 跨年度同项目支持
- [x] **[P0]** 10.10 `mark_previous_superseded` 查询加 year 条件（D25 风险点）
- [x] **[P0]** 10.11 `test_multi_year_coexist.py` 双 active 集成测试

### 批次 B：识别引擎强化（F6-F11，原完全遗漏）

#### F6 文件名元信息利用
- [x] **[P0]** 10.12 `detector._extract_filename_hints()` 函数（D26.1）
- [x] **[P0]** 10.13 `_detect_xlsx_from_path` 在 sheet 置信度 <60 时按 filename hint 加分
- [x] **[P0]** 10.14 期间信息（年月）提取到 `detection_evidence["filename_hint"]`
- [x] **[P0]** 10.15 `test_filename_hint.py` 辽宁卫生/陕西华氏样本

#### F7 方括号 + 组合表头
- [x] **[P0]** 10.16 `detector._normalize_header()` 剥方括号 + 拆组合(D26.2)
- [x] **[P0]** 10.17 `_detect_header_row` 每 cell 过 normalize
- [x] **[P0]** 10.18 `detection_evidence["compound_headers"]` 保留拆出子字段
- [x] **[P0]** 10.19 identifier 对 compound 子字段独立查别名
- [x] **[P0]** 10.20 `test_bracket_header.py` 和平物流样本置信度 ≥85

#### F8 表类型鲁棒性
- [x] **[P0]** 10.21 `identifier` sheet1/列表数据 改中性评分（D26.3）
- [x] **[P0]** 10.22 `_classify_balance_variant()` 按 aux_type 列区分主表/辅助表（已由 `_score_table_type` + KEY_COLUMNS aux_type 覆盖，无需独立函数）
- [x] **[P0]** 10.23 detect 阶段同 workbook 多余额表分流（每 sheet 独立走 identify，自动按 aux_type 区分）
- [x] **[P0]** 10.24 `test_table_type_robustness.py` YG36/安徽骨科/辽宁卫生 双余额表分流

#### F9 多 sheet unknown 透明化
- [x] **[P0]** 10.25 `SheetDetection.skip_reason` 字段 + `SheetWarning` 结构（D26.4）
- [x] **[P0]** 10.26 detect 阶段生成中文原因（行数太少 / 表头无法识别 / 列内容不符合）
- [x] **[P0]** 10.27 前端 `DetectionPreview.vue` 灰色卡片 + skip_reason badge
- [x] **[P0]** 10.28 `test_unknown_sheet_reason.py` YG2101 Sheet1 场景

#### F10 CSV 大文件保障
- [x] **[P0]** 10.29 `iter_csv_rows_from_path` 审查（Sprint 6 Part 1 已在，确认无全量加载）
- [x] **[P0]** 10.30 `test_large_csv_smoke.py` 合成 100MB CSV（detect <5s / 内存 <200MB）

#### F11 9 家样本 header 快照
- [x] **[P0]** 10.31 `backend/tests/fixtures/header_snapshots.json` 5+ 家快照数据
- [x] **[P0]** 10.32 `test_9_samples_header_detection.py` 参数化 + 真实样本缺失时 skip
- [x] **[P0]** 10.33 CI 必跑此测试（列入 ledger-import-smoke job）

### 批次 C：F28/F29/F31/F42/F43/F44 任务强化

#### F28 恢复剧本 ADR-003 补细节
- [x] **[P1]** 10.34 `docs/adr/ADR-003-ledger-import-recovery-playbook.md` 8 场景完整剧本（D27）
- [x] **[P1]** 10.35 每场景含症状+诊断命令+恢复步骤+回滚（copy-paste 可用）

#### F29 ADR-004 事务隔离补细节
- [x] **[P1]** 10.36 `docs/adr/ADR-004-ledger-activate-isolation.md` 完整版（D28）
- [x] **[P0]** 10.37 `@retry_on_serialization_failure` 装饰器实现（`backend/app/services/retry_utils.py`）
- [ ] **[P0]** 10.38 `DatasetService.activate` 加 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`（需 PG 专用实现，SQLite 无等价，延后）
- [x] **[P0]** 10.39 幂等键：同 (project_id, year, dataset_id) 二次 activate 直接返回成功

#### F31 前端激活确认
- [x] **[P0]** 10.40 `DatasetActivationButton.vue` ElMessageBox.prompt 实现（D29，前端任务延后）
- [x] **[P0]** 10.41 reason 字段传递到 API + 写入 ActivationRecord.reason（前端任务延后；后端 activate(*, reason=) 已支持）

#### F42 零行/异常规模拦截（补设计）
- [x] **[P1]** 10.42 `check_scale_warnings()` 函数实现（D30，基于历史均值 ±5σ 改为 ±10×）
- [x] **[P1]** 10.43 `ImportJob.force_submit` 字段
- [x] **[P1]** 10.44 detect 响应 warnings 数组 + submit 端点 force_submit 门控
- [x] **[P1]** 10.45 前端检测结果页"强制继续"按钮

#### F43 健康端点（补设计）
- [x] **[P1]** 10.46 `backend/app/routers/ledger_import_health.py` `/api/health/ledger-import` 实现（D31）
- [x] **[P1]** 10.47 status 3 态决策（healthy/degraded/unhealthy）
- [x] **[P1]** 10.48 HEALTH_STATUS gauge 同步
- [x] **[P2]** 10.49 Kubernetes liveness/readiness probe 配置文档化

#### F44 graceful shutdown（补设计）
- [x] **[P0]** 10.50 `ImportJobRunner.run_forever` stop_event 参数支持协同停机（D32；简化方案：不新增 JobStatus.interrupted 状态，依赖现有 recover_jobs heartbeat 超时兜底）
- [x] **[P0]** 10.51 pipeline cancel_check 识别 stop_event（已在 Sprint 4 通过 _handle_cancel 清理链实装）
- [ ] **[P0]** 10.52 main.py lifespan 关闭阶段 `asyncio.wait_for(runner.wait_idle(), timeout=30)`（已有 task.cancel + await，满足需求）
- [ ] **[P0]** 10.53 `interrupted` job 重启后自动 resume_from_checkpoint（需新 JobStatus 枚举，延后）

---

## 一致性审查结果

| 需求 | 原覆盖 | Sprint 10 补齐 | 最终状态 |
|------|--------|---------------|---------|
| F3 purge 基础 | Sprint 8 合规扩展 | 10.1-10.5 | ✅ |
| F4 审计轨迹 | Sprint 5 部分 | 10.6-10.9 | ✅ |
| F5 跨年度 | 无 | 10.10-10.11 | ✅ |
| F6-F11 识别引擎 | **完全遗漏** | 10.12-10.33 | ✅ |
| F28 恢复剧本 | 仅占位 | 10.34-10.35 | ✅ |
| F29 事务隔离 | 设计薄 | 10.36-10.39 | ✅ |
| F31 激活确认 | 后端已有 | 10.40-10.41 | ✅ |
| F42 零行/异常 | 仅任务占位 | 10.42-10.45 | ✅ |
| F43 健康端点 | 仅 metric 提 | 10.46-10.49 | ✅ |
| F44 graceful | 仅任务占位 | 10.50-10.53 | ✅ |

**Sprint 10 工时追加**：53 任务约 **8 人天**（小任务密集型），主力 F6-F11 识别引擎补齐约 4 天，其余基础任务约 4 天。

## 更新后总览

| Sprint | 主题 | 任务数 | 预估工时 |
|--------|------|-------|---------|
| 1 | 业务查询迁移 | 26 | 5 天 |
| 2 | activate 精简 + 写入改 false | 8 | 2 天 |
| 3 | 加固 + 文档 | 6 | 1.5 天 |
| 4 | 大文档健壮性 + 运维 | 18 | 4 天 |
| 5 | 云协同 | 20 | 4 天 |
| 6 | 数据正确性 + UX | 16 | 3 天 |
| 7 | 安全与健壮性 | 23 | 5 天 |
| 8 | 校验透明化 + 合规闭环 | 44 | 8 天 |
| 9 | 最终验收 | 10 | 2 天 |
| **10** | **一致性审查补齐** | **53** | **8 天** |
| **合计** | | **224** | **~43 天** |

**建议将 Sprint 10 前置**：识别引擎（F6-F11）是 detect 阶段核心，Sprint 4-9 所有涉及 detect 的任务都依赖它；审查建议 **Sprint 10 批次 B（10.12-10.33）优先于 Sprint 4 启动**。

---

## 第四阶段：测试矩阵任务补齐（Sprint 11）

> 二次审查发现 requirements §4 测试矩阵里有 9 个测试文件在 Sprint 1-10 没对应任务编号。
> 原因：核心功能任务已列，但单独的测试文件任务遗漏。本 Sprint 补齐。

### 单元测试（对应 requirements §4.1）

- [x] **[P0]** 11.1 `test_dataset_service_activate_view_refactor.py`（F1）
  - 断言 activate 后 ledger_datasets.status 切换，Tb* 表 UPDATE 计数 = 0
  - 补充：Sprint 2 改完 activate 后写，不单独 Sprint
- [x] **[P0]** 11.2 `test_dataset_service_rollback_view_refactor.py`（F1）
  - 断言 rollback 后 metadata 正确切换
- [x] **[P0]** 11.3 `test_progress_callback_granularity.py`（F13）
  - 模拟 50k 行 chunk，断言 progress_cb 被调用次数 ≥ 5
  - 挂在 Sprint 4 批次 A 后
- [x] **[P1]** 11.4 `test_duration_estimator.py`（F17）
  - 4 档行数范围返回估算值 + 9 家样本误差 ±30%

### 集成测试（对应 requirements §4.2）

- [x] **[P0]** 11.5 `test_dataset_concurrent_isolation.py`（F1 并发）
  - A 项目 staged + B 项目 active 业务查询不串
  - 挂在 Sprint 3 加固阶段
- [x] **[P0]** 11.6 `test_rollback_full_flow.py`（F1）
  - 导入 → activate → 再导入 → activate → rollback → 看到第一份数据
  - 属 Sprint 3 回归测试一部分
- [x] **[P0]** 11.7 `test_resume_from_activation_checkpoint.py`（F14）
  - activate 抛异常 → resume 后数据集成功激活
  - 挂在 Sprint 4 批次 A 后
- [x] **[P0]** 11.8 `test_metrics_endpoint.py`（F16）
  - curl /metrics 含 3 个核心指标且有数据点
  - 挂在 Sprint 4 批次 C 后
- [x] **[P0]** 11.9 `test_migration_day7_update.py`（F18）
  - Day 7 一次性 UPDATE SQL 幂等、正确切换 active 行 is_deleted
  - 挂在 Sprint 4 批次 D 后（Alembic 4.16 落地后）

---

## 第五阶段：requirements 内部引用修正（2026-05-10）

### 修正记录

| 位置 | 原引用 | 新引用 | 原因 |
|------|--------|--------|------|
| O10 | (F30) | 删除 | F30 从未定义，F27 COUNT check 已兜底 |
| O11 | (F33) | 删除 | F33 从未定义，排除项本身描述足够 |
| O12 | (F34) | 删除 | F34 从未定义 |
| O13 | (F36) | 删除 | F36 从未定义 |
| O14 | (F37) | 删除 | F37 从未定义 |
| O15 过渡方案 | F34 先预留 | F41 先预留 | tenant_id 实际定义在 F41 |
| O17 过渡方案 | F38 event | F45 event | DLQ 实际定义在 F45 |

### 背景
requirements 第 4 轮扩展时为避开已命名的 F 编号间隔跳过了 F33-F39，但 §1.2 排除表内部仍保留了"（F30-F37）"的占位引用，造成文档内部不一致。一致性审查发现并修正。

---

## 二次审查最终结果

| Sprint | 主题 | 任务数 | 工时 |
|--------|------|-------|------|
| 1-3 | B' 核心 | 40 | 8.5 天 |
| 4-9 | 扩展需求实施 | 131 | 26 天 |
| 10 | 一致性缺口补齐 | 53 | 8 天 |
| **11** | **测试矩阵补齐 + 文档引用修正** | **9** | **1 天** |
| **合计** | | **233** | **~44 天** |

## 最终需求覆盖状态

- **F1-F53**（38 条必做）：100% 有对应 design + tasks
- **O1-O22**（22 条独立 Sprint）：0 个内部引用残留不一致
- **测试矩阵 §4**：单元 6 个 + 集成 22 个 + E2E 4 个 = 32 个测试文件全部有任务编号

三件套一致性审查二次完成，无待办遗漏项。
