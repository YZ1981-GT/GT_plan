# Phase 16: 取证包与版本链闭环 - 实施任务（企业级落地版）

## 阶段0: 规格硬化与实施前置

- [x] 1. 口径冻结
  - [x] 1.1 冻结版本戳对象范围枚举，写入 `backend/app/models/phase16_enums.py::VersionObjectType(str, Enum)`：`report/note/workpaper/procedure`
  - [x] 1.2 冻结冲突处置方式枚举 `ConflictResolution(str, Enum)`：`accept_local/accept_remote/manual_merge`
  - [x] 1.3 冻结冲突状态枚举 `ConflictStatus(str, Enum)`：`open/resolved/rejected`
  - [x] 1.4 冻结取证包校验状态枚举 `HashCheckStatus(str, Enum)`：`passed/failed`
  - [x] 1.5 冻结一致性复算五层链路口径：`tb_balance→trial_balance→financial_report→disclosure_notes→working_papers→trial_balance`
  - [x] 1.6 冻结阅读包/取证包字段清单，产出《导出字段字典.md》
  - [x] 1.7 冻结脱敏规则（引用 Phase 14 design §12.2）：审计助理脱敏3字段/项目经理脱敏+金额阈值/质控脱敏客户识别/合伙人默认不脱敏

## 阶段1: 版本链主链路

- [x] 2. 版本链数据模型与服务
  - [x] 2.1 创建 `backend/app/models/phase16_models.py`：
    - `VersionLineStamp` ORM：`id(UUID PK), project_id(UUID), object_type(VARCHAR32), object_id(UUID), version_no(INT), source_snapshot_id(VARCHAR64 nullable), trace_id(VARCHAR64), created_at`
    - `EvidenceHashCheck` ORM：`id(UUID PK), export_id(UUID), file_path(TEXT), sha256(VARCHAR64), signature_digest(VARCHAR128 nullable), check_status(VARCHAR16), checked_at`
    - `OfflineConflict` ORM：`id(UUID PK), project_id(UUID), wp_id(UUID), procedure_id(UUID), field_name(VARCHAR64), local_value(JSONB nullable), remote_value(JSONB nullable), merged_value(JSONB nullable), status(VARCHAR16), resolver_id(UUID nullable), reason_code(VARCHAR64 nullable), qc_replay_job_id(UUID nullable), trace_id(VARCHAR64), created_at, resolved_at(TIMESTAMP nullable)`
  - [x] 2.2 创建 Alembic 迁移 `backend/alembic/versions/phase16_001_version_integrity_conflict.py`：建 version_line_stamps + evidence_hash_checks + offline_conflicts 三张表 + 全部索引（对齐 migration.sql）
  - [x] 2.3 创建 `backend/app/services/version_line_service.py`：
    - `async write_stamp(db, project_id, object_type, object_id, version_no, source_snapshot_id=None, trace_id=None) -> VersionLineStamp`
      - 连续性守卫：查询同 object_type+object_id 最大 version_no，新 version_no 必须 = max+1，否则抛 `HTTPException(409, 'VERSION_LINE_GAP')`
    - `async query_lineage(db, project_id, object_type=None, object_id=None) -> list[VersionLineStamp]`
    - `async get_latest_version(db, project_id, object_type, object_id) -> int`
  - [x] 2.4 接入版本写入 4 个触发点：
    - `backend/app/services/report_engine.py::generate_all_reports()` → `version_line_service.write_stamp(object_type='report')`
    - `backend/app/services/disclosure_engine.py::generate_notes()` → `version_line_service.write_stamp(object_type='note')`
    - `backend/app/services/wopi_service.py::put_file()` → `version_line_service.write_stamp(object_type='workpaper')`
    - `backend/app/routers/procedures.py::update_trim_status()` → `version_line_service.write_stamp(object_type='procedure')`
  - [x] 2.5 创建 `backend/app/routers/version_line.py`：
    - `GET /api/version-line/{project_id}?object_type=&object_id=` → 调用 `version_line_service.query_lineage()`
  - [x] 2.6 注册路由到 `router_registry.py`

## 阶段2: 取证完整性主链路

- [x] 3. 取证校验服务
  - [x] 3.1 创建 `backend/app/services/export_integrity_service.py`：
    - `async build_manifest(export_id, files: list[str]) -> dict` — 遍历文件列表，生成 `{"files": [{"path": "...", "sha256": "..."}], "manifest_hash": "sha256_of_manifest_json"}`
    - `async calc_hash(file_path: str) -> str` — `hashlib.sha256` 分块读取（64KB chunks），返回 hex digest
    - `async verify_package(db, export_id) -> dict` — 从 evidence_hash_checks 读取记录，逐文件比对 sha256，任一不匹配 → check_status='failed'
    - `async persist_checks(db, export_id, file_checks: list[dict]) -> None` — 批量写入 evidence_hash_checks
  - [x] 3.2 接入导出流程：`backend/app/services/export_task_service.py::execute_export()` 完成后调用：
    - `export_integrity_service.build_manifest(export_id, output_files)`
    - `export_integrity_service.persist_checks(db, export_id, manifest['files'])`
    - 写 trace_events(event_type='export_integrity_checked')
  - [x] 3.3 创建 `backend/app/routers/export_integrity.py`：
    - `GET /api/exports/{export_id}/integrity` → 调用 `export_integrity_service.verify_package()`
  - [x] 3.4 篡改检测：`verify_package()` 中任一文件 hash 不匹配 → 返回 `{"check_status": "failed", "mismatched_files": [...]}` + 写 trace_events(event_type='integrity_check_failed', decision='block')

## 阶段3: 离线冲突治理闭环

- [x] 4. 冲突检测与合并服务
  - [x] 4.1 创建 `backend/app/services/offline_conflict_service.py`：
    - `async detect(db, project_id, wp_id) -> list[OfflineConflict]`：
      - 查询 working_paper 的 parsed_data 与上传版本的 parsed_data 逐字段比对
      - 粒度：`procedure_id + field_name`（如 `proc_001.audited_amount`, `proc_001.conclusion`）
      - 差异写入 offline_conflicts(status='open')
      - 写 trace_events(event_type='conflict_detected')
    - `async assign(db, conflict_id, resolver_id) -> OfflineConflict` — 更新 resolver_id
    - `async resolve(db, conflict_id, resolution, merged_value, resolver_id, reason_code) -> OfflineConflict`：
      - 校验 status='open'，否则 409 CONFLICT_ALREADY_RESOLVED
      - 更新 status='resolved'/merged_value/reason_code/resolved_at
      - 触发 QC 重跑：`asyncio.create_task(qc_engine.check(db, wp_id))` → 记录 qc_replay_job_id
      - 写 trace_events(event_type='conflict_resolved', reason_code=reason_code)
    - `async list_conflicts(db, project_id, status=None, page=1, page_size=50) -> dict`
  - [x] 4.2 接入离线上传：`backend/app/services/wp_download_service.py::upload_file()` 在版本冲突检测后调用 `offline_conflict_service.detect()`
  - [x] 4.3 创建 `backend/app/routers/offline_conflicts.py`：
    - `POST /api/offline/conflicts/detect` body: `{project_id, wp_id}`
    - `POST /api/offline/conflicts/resolve` body: `{conflict_id, resolution, merged_value?, resolver_id, reason_code}`
    - `GET /api/offline/conflicts?project_id=&status=&page=&page_size=`
  - [x] 4.4 注册路由到 `router_registry.py`

## 阶段4: 可复算一致性引擎

- [x] 5. 一致性复算服务
  - [x] 5.1 创建 `backend/app/services/consistency_replay_engine.py`：
    - `async replay_consistency(db, project_id, snapshot_id=None) -> ConsistencyReplayResult`：
      - Layer 1: `SELECT SUM(closing_balance) FROM tb_balance WHERE project_id=:pid AND year=:y GROUP BY account_code` vs `SELECT unadjusted_amount FROM trial_balance WHERE project_id=:pid AND year=:y`，diff > 0.01 → inconsistent
      - Layer 2: `financial_report.amount` vs `trial_balance` 公式驱动取数结果，diff > 0.01 → inconsistent
      - Layer 3: `disclosure_notes` 关键科目金额 vs `financial_report` 对应行，diff > 0.01 → inconsistent
      - Layer 4: `working_papers.parsed_data.audited_amount` vs `disclosure_notes` 对应章节金额，diff > 0.01 → inconsistent
      - Layer 5: `working_papers.parsed_data.audited_amount` vs `trial_balance.audited_amount`（反向校验），diff > 0.01 → inconsistent
      - 返回 `ConsistencyReplayResult(snapshot_id, layers: list[ConsistencyLayer], overall_status, blocking_count, trace_id)`
    - `async generate_consistency_report(db, project_id) -> dict` — 调用 replay_consistency + 格式化为报告结构
    - `class ConsistencyLayer`: `from_table: str, to_table: str, status: str, diffs: list[ConsistencyDiff]`
    - `class ConsistencyDiff`: `object_type, object_id, field, expected: Decimal, actual: Decimal, diff: Decimal, severity: str`
  - [x] 5.2 创建 `backend/app/routers/consistency_replay.py`：
    - `POST /api/consistency/replay` body: `{project_id, snapshot_id?}` → 调用 `consistency_replay_engine.replay_consistency()`
    - `GET /api/consistency/report/{project_id}` → 调用 `consistency_replay_engine.generate_consistency_report()`
  - [x] 5.3 联动签字门禁：`consistency_replay_engine.replay_consistency()` 结果中 blocking_count > 0 时，写入 `gate_decisions(gate_type='sign_off', decision='block', hit_rules=[{rule_code:'CONSISTENCY_BLOCKING_DIFF', ...}])`
  - [x] 5.4 一致性报告附在取证包：`export_task_service.py::execute_export()` 中，如果 export_type='evidence_package'，自动调用 `generate_consistency_report()` 并写入导出目录
  - [x] 5.5 注册路由到 `router_registry.py`

## 阶段5: 增强能力

- [x] 6. 增强项
  - [x] 6.1 回放中心：`trace.py` 路由增加 `GET /api/trace?object_type=offline_conflict&object_id={conflict_id}` 支持冲突处置回放
  - [x] 6.2 取证包模板化：创建 `backend/data/evidence_package_template.json` 定义阅读包/取证包字段映射
  - [x] 6.3 双通道字段字典：阅读包字段 = 业务可读字段（中文列名），取证包字段 = 全量字段 + hash + trace_id

## 阶段6: 企业级增强

- [x] 7. 运维监控
  - [x] 7.1 Prometheus 指标：
    - `export_integrity_check_total` (counter, labels: check_status)
    - `export_build_duration_seconds` (histogram)
    - `offline_conflict_detected_total` (counter)
    - `offline_conflict_resolved_total` (counter, labels: resolution)
    - `consistency_replay_duration_seconds` (histogram)
    - `consistency_blocking_diff_total` (counter)
  - [x] 7.2 告警规则：
    - `export_integrity_check_total{check_status="failed"} > 0` → P0
    - `histogram_quantile(0.95, export_build_duration_seconds) > 60` → P1
    - `offline_conflict_detected_total - offline_conflict_resolved_total > 20` 持续 24h → P1
    - `consistency_blocking_diff_total > 0` 且 gate_decisions 无对应 block 记录 → P0

- [x] 8. 数据迁移
  - [x] 8.1 创建 `backend/scripts/phase16/init_version_line.py`：从 working_papers.version + report_snapshots 构建初始 version_line_stamps（version_no=当前版本号，trace_id='INIT_MIGRATION'）
  - [x] 8.2 历史导出包兼容：上线后新导出必须有 hash，历史导出包无 evidence_hash_checks 记录（不追溯）
  - [x] 8.3 现有离线冲突兼容：`wp_download_service.py::upload_file()` 的旧版本冲突检测保留，新增 `offline_conflict_service.detect()` 作为增强层

- [x] 9. 灰度与回滚
  - [x] 9.1 创建 `backend/scripts/phase16/rollback_version_line.py`：TRUNCATE version_line_stamps（不影响业务数据）
  - [x] 9.2 创建 `backend/scripts/phase16/rollback_integrity.py`：TRUNCATE evidence_hash_checks + 导出功能降级为无校验模式（feature_flag）
  - [x] 9.3 创建 `backend/scripts/phase16/rollback_conflicts.py`：offline_conflicts 全部回退到 open + 清理 qc_replay_job_id
  - [x] 9.4 执行一次完整回滚演练，产出《Phase16回滚演练报告.md》

- [x] 10. 取证包脱敏
  - [x] 10.1 创建 `backend/app/services/export_mask_service.py`：
    - `MASK_RULES: dict[str, list[str]]` — 按角色定义脱敏字段列表
    - `async apply_mask(data: dict, actor_role: str, mask_policy: str) -> dict` — 遍历字段，命中规则的替换为 `***`
    - `async check_export_permission(actor_id, actor_role, export_scope) -> bool` — 完整导出需上级审批
  - [x] 10.2 接入导出流程：`export_task_service.py::execute_export()` 中调用 `export_mask_service.apply_mask()`
  - [x] 10.3 导出链接一次性令牌：`export_integrity.py::download_export()` 生成 `token=uuid, TTL=600s` 写入 Redis，下载时校验并删除

- [x] 11. 前端交互
  - [x] 11.1 创建 `audit-platform/frontend/src/views/OfflineConflictWorkbench.vue`：
    - 左栏：冲突列表（按 wp_code 分组，状态色 open 红/resolved 绿/rejected 灰）
    - 中栏：冲突详情（field_name + local_value vs remote_value 双栏对比，差异高亮）
    - 右栏：处置操作（accept_local/accept_remote/manual_merge 三选一 + reason_code 下拉 + 确认按钮）
    - 确认后显示 QC 重跑状态（loading → passed/failed）
  - [x] 11.2 创建 `audit-platform/frontend/src/components/integrity/IntegrityCheckPanel.vue`：
    - 文件列表：file_path + sha256 + check_status（passed 绿勾/failed 红叉）
    - 失败文件可点击定位到导出包中的具体文件
    - manifest_hash 显示在顶部
  - [x] 11.3 创建 `audit-platform/frontend/src/components/consistency/ConsistencyReplayPanel.vue`：
    - 五层链路可视化（竖向流程图，每层 consistent 绿/inconsistent 红）
    - 点击 inconsistent 层展开差异明细表（object_type/field/expected/actual/diff/severity）
    - blocking 级差异红色高亮 + "跳转修复"按钮
  - [x] 11.4 创建 `audit-platform/frontend/src/components/version/VersionLineTimeline.vue`：
    - 时间线组件：按 created_at 排序，每个节点显示 object_type 图标 + version_no + trace_id
    - 点击节点查看 snapshot 详情（如果 L2/L3 回放可用）
  - [x] 11.5 创建 `audit-platform/frontend/src/services/phase16Api.ts`：
    - `queryVersionLine(projectId, objectType?, objectId?)`, `checkExportIntegrity(exportId)`
    - `detectConflicts(projectId, wpId)`, `resolveConflict(params)`, `listConflicts(params)`
    - `replayConsistency(projectId, snapshotId?)`, `getConsistencyReport(projectId)`

- [x] 12. CI 门槛
  - [x] 12.1 PR 阶段：`python -m pytest backend/tests/test_phase16*.py -v` 通过率 = 100%
  - [x] 12.2 预发阶段：全量 IT + 篡改检测通过率 = 100%
  - [x] 12.3 生产前：`check_version_line_continuity.py` + `check_export_integrity_hash.py` + `check_offline_conflict_detection.py` + `check_consistency_replay.py` 全部 PASS

## 测试与验收

- [x] 13. 单元测试 `backend/tests/test_phase16_version.py`
  - [x] P16-UT-001: write_stamp version_no=1 → 成功
  - [x] P16-UT-002: write_stamp version_no=3（跳号，当前 max=1）→ 409 VERSION_LINE_GAP
  - [x] P16-UT-003: write_stamp version_no=2（连续）→ 成功
  - [x] P16-UT-004: query_lineage 返回按 version_no 升序
  - [x] P16-UT-005: get_latest_version 返回最大 version_no

- [x] 14. 单元测试 `backend/tests/test_phase16_integrity.py`
  - [x] P16-UT-006: calc_hash 对已知文件 → 返回正确 SHA-256
  - [x] P16-UT-007: build_manifest 3 个文件 → manifest 含 3 条 + manifest_hash
  - [x] P16-UT-008: verify_package 全部匹配 → check_status='passed'
  - [x] P16-UT-009: verify_package 1 个文件被篡改 → check_status='failed' + mismatched_files 含该文件
  - [x] P16-UT-010: persist_checks 写入 evidence_hash_checks 记录数正确

- [x] 15. 单元测试 `backend/tests/test_phase16_conflict.py`
  - [x] P16-UT-011: detect 2 个字段差异 → 返回 2 个 OfflineConflict(status='open')
  - [x] P16-UT-012: detect 无差异 → 返回空列表
  - [x] P16-UT-013: resolve accept_local → merged_value=local_value + status='resolved' + qc_replay_job_id 非空
  - [x] P16-UT-014: resolve 已 resolved 的冲突 → 409 CONFLICT_ALREADY_RESOLVED
  - [x] P16-UT-015: resolve 缺 reason_code → 400
  - [x] P16-UT-016: resolve manual_merge 无 merged_value → 400

- [x] 16. 单元测试 `backend/tests/test_phase16_consistency.py`
  - [x] P16-UT-017: Layer 1 tb_balance vs trial_balance 一致 → status='consistent'
  - [x] P16-UT-018: Layer 1 差异 500 元 → status='inconsistent' + diff=500 + severity='blocking'
  - [x] P16-UT-019: Layer 2 report vs trial_balance 一致 → consistent
  - [x] P16-UT-020: Layer 3 note vs report 差异 → inconsistent
  - [x] P16-UT-021: Layer 4 workpaper vs note 一致 → consistent
  - [x] P16-UT-022: Layer 5 workpaper vs trial_balance 差异 → inconsistent
  - [x] P16-UT-023: overall_status = inconsistent 当任一层 inconsistent
  - [x] P16-UT-024: blocking_count 正确统计
  - [x] P16-UT-025: generate_consistency_report 返回含 replay_at + trace_id

- [x] 17. 单元测试 `backend/tests/test_phase16_mask.py`
  - [x] P16-UT-026: apply_mask assistant 角色 → 3 个字段被替换为 ***
  - [x] P16-UT-027: apply_mask partner 角色 → 不脱敏
  - [x] P16-UT-028: check_export_permission assistant 完整导出 → False
  - [x] P16-UT-029: check_export_permission partner 完整导出 → True

- [x] 18. 集成测试 `backend/tests/test_phase16_integration.py`
  - [x] P16-IT-001: 报表生成 → version_line_stamps 写入 → query_lineage 返回
  - [x] P16-IT-002: 导出 → build_manifest → persist_checks → verify_package → 全部 passed
  - [x] P16-IT-003: 篡改文件 → verify_package → failed + trace_events 有 integrity_check_failed 记录
  - [x] P16-IT-004: 离线上传冲突 → detect → resolve → QC 重跑 → trace_events 完整链路
  - [x] P16-IT-005: consistency replay blocking → gate_decisions 写入 sign_off block
  - [x] P16-IT-006: 取证包导出含一致性报告附件

- [x] 19. 非功能测试
  - [x] P16-PERF-001: 单次取证包构建（50 文件）P95 <= 30s
  - [x] P16-PERF-002: 500 张底稿项目一致性复算 P95 <= 10s
  - [x] P16-SEC-001: 篡改检测命中率 = 100%（10 个篡改样本全部检出）
  - [x] P16-CONTRACT-001: `/api/version-line/{project_id}` 合同测试
  - [x] P16-CONTRACT-002: `/api/exports/{export_id}/integrity` 合同测试
  - [x] P16-CONTRACT-003: `/api/offline/conflicts/resolve` 合同测试
  - [x] P16-CONTRACT-004: `/api/consistency/replay` 合同测试

## 验收脚本（必须产出）

- [x] 20. 脚本化验收
  - [x] 20.1 `backend/scripts/phase16/check_version_line_continuity.py` — 遍历所有 object_type+object_id 组合，断言 version_no 连续无跳号
  - [x] 20.2 `backend/scripts/phase16/check_export_integrity_hash.py` — 随机选 5 个导出包，verify_package 断言全部 passed
  - [x] 20.3 `backend/scripts/phase16/check_offline_conflict_detection.py` — 模拟上传冲突文件，断言 detect 返回非空 + 字段级粒度
  - [x] 20.4 `backend/scripts/phase16/check_conflict_merge_qc_replay.py` — resolve 后断言 qc_replay_job_id 非空 + QC 结果已刷新
  - [x] 20.5 `backend/scripts/phase16/check_consistency_replay.py` — 调用 replay_consistency，断言五层结果均有返回 + blocking_count 与实际差异一致

## 放行门槛（Go/No-Go）

- [x] G1 版本戳贯通率 = 100%：P16-UT-001~005 + P16-IT-001 + check_version_line_continuity.py 通过
- [x] G2 取证包 hash 校验通过率 = 100%：P16-UT-006~010 + P16-IT-002 + check_export_integrity_hash.py 通过
- [x] G3 冲突漏检 = 0：P16-UT-011~016 + P16-IT-004 + check_offline_conflict_detection.py 通过
- [x] G4 回放成功率 >= 99%：trace_events 链路完整（P16-IT-004 trace 断言）
- [x] G5 取证包构建性能 P95 <= 30s：P16-PERF-001 通过
- [x] G6 一致性引擎上线，关键口径差异 <= 0.01：P16-UT-017~025 + P16-IT-005 + check_consistency_replay.py 通过
- [x] G7 阻断级差异联动签字门禁：P16-IT-005 通过
- [x] G8 篡改检测命中率 = 100%：P16-SEC-001 通过
- [x] G9 脱敏规则生效：P16-UT-026~029 通过
- [x] G10 灰度回滚演练通过 + CI 门槛全部 PASS
