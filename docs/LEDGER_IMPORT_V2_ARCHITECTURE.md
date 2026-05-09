# 账表导入 v2 引擎架构文档

> 最后更新：2026-05-09 Sprint 7

## 1. 模块总览

```
backend/app/services/ledger_import/
├── __init__.py              # 统一入口导出
├── pipeline.py              # 数据管线（execute_pipeline + PipelineResult）
├── orchestrator.py          # API 编排（detect/submit/resume）
├── detector.py              # 文件探测（xlsx/csv/zip → SheetDetection）
├── identifier.py            # 3 级识别（L1 sheet 名 / L2 表头 / L3 内容）
├── converter.py             # 数据转换（raw → 4 表标准行）
├── validator.py             # 分层校验（L1 列级 / L2 借贷平衡 / L3 跨表一致）
├── writer.py                # 写入层（bulk_insert_staged / raw_extra / activate）
├── aux_dimension.py         # 辅助维度解析（8 种格式 + 智能逗号分隔）
├── detection_types.py       # Pydantic schema（单一真源）
├── errors.py                # 错误码枚举 + make_error 工厂
├── encoding_detector.py     # CSV 编码自适应
├── year_detector.py         # 年度识别（5 级优先）
├── merge_strategy.py        # 多 sheet 合并策略
├── column_mapping_service.py # 列映射历史 CRUD
├── content_validators.py    # 列内容验证器（date/numeric/code）
├── parsers/
│   ├── excel_parser.py      # xlsx 流式解析 + read_only 回退 + forward-fill
│   ├── csv_parser.py        # CSV 流式解析 + 编码自适应
│   └── zip_parser.py        # ZIP 解压递归
└── adapters/                # 别名包（不做运行时 match）
    ├── __init__.py          # AdapterRegistry
    ├── base.py / generic.py / yonyou.py / kingdee.py / sap.py / ...
    └── json_driven.py       # JSON 配置驱动适配器
```

## 2. 数据流

```
用户上传文件
    │
    ▼
[detect] ─── detector → identifier → year_detector → merge_strategy
    │         返回 LedgerDetectionResult（前端预检弹窗）
    ▼
[submit] ─── 创建 ImportJob + ImportArtifact → Worker 拾取
    │
    ▼
[Worker: _execute_v2] ─── 薄包装（状态机 + 锁 + artifact）
    │
    ▼
[pipeline.execute_pipeline] ─── 纯数据管线
    │
    ├── Phase 1: detect_file_from_path → identify（每 sheet）
    ├── Phase 2: create_staged（DatasetService）
    ├── Phase 3: 流式 parse → prepare_rows_with_raw_extra → validate_l1
    │            → convert_balance/ledger_rows → bulk_insert_staged
    ├── Phase 4: evaluate_activation（gate 通过 → activate_dataset）
    └── Phase 5: rebuild_aux_balance_summary
```

## 3. 关键设计决策

### 3.1 Staged 原子激活（S6-13）

- 所有 insert 带 `dataset_id=staging_id` + `is_deleted=True`
- 数据写入期间对外不可见（查询走 `is_deleted=false` 过滤）
- Gate 通过后 `activate_dataset()` 原子切换：旧 active → superseded，新 staged → active
- 失败时 `DatasetService.mark_failed()` 清理孤儿数据

### 3.2 Worker 薄包装 vs Pipeline 纯数据（S6-3 / S7-6）

- `import_job_runner._execute_v2`（573 行）：只管 Job 状态机 + ImportQueueService 锁 + artifact 消费
- `pipeline.execute_pipeline`（346 行）：纯数据流，通过 `progress_cb` / `cancel_check` 回调抽象 Worker 细节
- 未来换调度器（Celery/RQ）只需改 runner 层

### 3.3 bulk_insert_staged 自省（S7-2）

- 按 `table_model.__table__.columns` 自动过滤 row 字典里不存在的字段
- 自动注入 id/project_id/year/dataset_id/is_deleted 公共字段
- NOT NULL 兜底：company_code → "default"，currency_code → "CNY"
- 新增字段只改 converter + ORM 模型，无需改 insert 函数

### 3.4 L1 强信号锁定（S6-9）

- `MATCHING_CONFIG.l1_lock_threshold`（默认 85）
- Sheet 名命中且 score ≥ 阈值时，L1 锁定 table_type，L2 只做列映射不投票
- 解决"和平物流余额表被 L2 误投 ledger"的问题

### 3.5 辅助维度智能逗号分隔（aux_dimension.py）

- 逗号只在"后接 `类型:`"时作为多维度分隔符（`_smart_comma_split`）
- 避免误切"金融机构:YG0001,工商银行"这种单维度格式
- 分号 `;` / `；` 始终作为强分隔符

### 3.6 动态容差（S7 validator）

- `tolerance = min(1.0 + magnitude × 0.00001, 100.0)`
- 小金额（<10 万）≈ 1 元，大金额（亿级）≈ 10-100 元
- 避免浮点精度导致的误报

### 3.7 多对一列映射保留（S6-6）

- `prepare_rows_with_raw_extra`：首个非空值保留到 std_field
- 被丢弃的非空值进 `raw_extra["_discarded_mappings"][std_field]`
- 不再静默丢失

## 4. 回调契约

```python
# pipeline.py 导出
ProgressCallback = Callable[[int, str], Awaitable[None]]  # (pct, message)
CancelChecker = Callable[[], Awaitable[bool]]  # returns True if canceled
```

Worker 实现：
- `progress_cb` → `ImportJobService.set_progress(job_id, pct, message)`
- `cancel_check` → 查 `ImportJob.status == canceled`

## 5. PipelineResult 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 是否成功激活 |
| dataset_id | UUID | 激活的 dataset |
| balance_rows | int | tb_balance 写入行数 |
| aux_balance_rows | int | tb_aux_balance 写入行数 |
| ledger_rows | int | tb_ledger 写入行数 |
| aux_ledger_rows | int | tb_aux_ledger 写入行数 |
| total_rows_parsed | int | 总解析行数 |
| warnings | int | 非阻塞 warning 数 |
| blocking_findings | int | 阻塞 finding 数 |
| year | int | 会计年度 |

## 6. Alembic 迁移链

```
001_consolidated → phase13_001 → ... → phase17_005
→ round1_review_closure_20260508 → round1_long_term_compliance_20260508
→ round2_budget_handover_20260510 → round2_batch3_arch_fixes_20260506
→ round3_qc_governance_20260506 → round5_eqcr_20260506
→ round4_editing_lock_20260506 → round4_ocr_fields_cache_20260506（分支终点）
→ round5_eqcr_20260505 → round5_independence_20260506
→ round5_eqcr_check_constraints_20260506 → round6_qc_rule_definitions_20260507
→ round6_review_binding_20260507 → round7_section_progress_gin_20260507
→ round7_clients_20260508 → ledger_import_column_mapping_20260508
→ ledger_import_raw_extra_20260508 → ledger_import_aux_triplet_idx_20260508
→ ledger_import_raw_extra_gin_20260509
```

**重要**：所有迁移必须放 `backend/alembic/versions/`，不能放 `backend/app/migrations/`。

## 7. 测试策略

| 层级 | 文件 | 用例数 | 说明 |
|------|------|--------|------|
| 单元 | test_detector/identifier/validator/... | ~100 | 纯函数，SQLite |
| 集成 | test_bulk_insert_staged | 8 | SQLite 内存库真写入 |
| E2E | test_execute_v2_e2e | 2 | YG36 完整管线 |
| 真实样本 | test_9_samples_e2e | 10 | 9 家企业参数化 |
| Smoke | test_minimal_sample_smoke | 4 | 合成样本，CI 必跑 |
| 拓扑 | test_alembic_migrations | 5 | 迁移链正确性 |

CI 两层策略：
1. 最小合成样本 smoke（必跑，0.45s）
2. 真实 9 家样本 E2E（可选，~3min，数据/ 缺失时 skip）

## 8. 已知限制

1. `execute_pipeline` 的 4 个 `_insert` 闭包仍在 pipeline.py 内（已用 bulk_insert_staged 简化但未完全消除闭包）
2. 辅助维度类型重名（"税率"跨科目）靠三元组查询区分，但 tb_aux_ledger 本身无上下文字段
3. 大文件（600MB+ CSV）全量导入的内存/耗时基准未建立 CI 门禁
4. adapter 目录保留但 detect_best 已移除，如需恢复需重新接入 orchestrator
5. Alembic round-trip 测试需 PG 环境（本地 skip，CI 里跑）
