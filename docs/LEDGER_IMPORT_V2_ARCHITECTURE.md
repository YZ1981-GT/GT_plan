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

---

## 9. 可见性架构（B' 视图重构，2026-05-10）

> 对应 spec：`.kiro/specs/ledger-import-view-refactor/` · ADR-002
>
> 历史背景：原"行级 is_deleted"架构下，每次 activate 需要 UPDATE 4 张 Tb* 表
> 数百万行 `is_deleted=true → false`。YG2101（200 万行）实测 activate 单阶段
> 耗时 **127-193s**，占整体导入耗时的 25-40%，且与 PG WAL 写入带宽成正比。

### 9.1 核心转变

| 维度 | 旧架构（is_deleted） | B' 新架构（metadata） |
|------|---------------------|---------------------|
| 可见性控制 | `TbX.is_deleted` 行级标志 | `LedgerDataset.status = 'active'` 元数据 |
| activate 代价 | UPDATE N 行 Tb* 数据 | UPDATE 2 行 `ledger_datasets` |
| YG2101 实测 | 127-193s | < 1s |
| WAL 写入 | O(row_count) | O(1) |
| 表膨胀 | 每次 activate 200 万 dead tuple | 无额外 dead tuple |
| autovacuum 压力 | 高 | 低 |

### 9.2 查询层：get_active_filter

所有账表四表（TbBalance / TbLedger / TbAuxBalance / TbAuxLedger）查询统一
通过 `app.services.dataset_query.get_active_filter`：

```python
from app.services.dataset_query import get_active_filter

cond = await get_active_filter(db, TbLedger.__table__, project_id, year)
rows = await db.execute(sa.select(TbLedger).where(cond))
```

返回的 WHERE 条件：

```sql
project_id = :pid
AND year = :yr
AND dataset_id = :active_id        -- 优先（若当前 year 有 active dataset）
AND is_deleted = false             -- 兜底（双保险 + 向后兼容 Day 0-7 过渡期）
```

**两种降级模式**：
1. 当前 project+year 无 active dataset → 降级为仅 `project + year + is_deleted=false`
   （老数据依然能看到；B' 架构前写入的 active 行仍是 is_deleted=false）
2. `force_dataset_id` 参数（F50 合规绑定）→ 强制锁定某个历史 dataset，
   供 Workpaper/AuditReport 签字后的冻结查询

### 9.3 写入层：pipeline 始终写 is_deleted=false

pipeline._insert 统一：
```python
row["is_deleted"] = False  # B' 架构下新数据写入即 false
row["dataset_id"] = staging_dataset_id  # 关键：靠 dataset.status 控制可见性
```

Staged dataset 的行和 active dataset 的行物理上都是 is_deleted=false；
但查询层 `get_active_filter` 返回的条件会把 staged 过滤掉（dataset_id ≠ active_id）。

### 9.4 activate 精简路径

```python
# app/services/dataset_service.py::DatasetService.activate
async def activate(db, dataset_id, ...):
    dataset.status = DatasetStatus.active
    # 旧 active → superseded
    await db.execute(
        sa.update(LedgerDataset).where(...).values(status=superseded)
    )
    # 不再 UPDATE 物理行 — _set_dataset_visibility 已 no-op 化
    db.add(ActivationRecord(...))
    # 发 LEDGER_DATASET_ACTIVATED 事件到 outbox
    await ImportEventOutboxService.enqueue(...)
```

**_set_dataset_visibility 的命运**：保留方法签名作向后兼容，实际体内只
`logger.warning + return`。上游代码可能还引用，但执行时间 0ms 无副作用。

### 9.5 rollback 对称处理

`DatasetService.rollback` 完全镜像 activate：
- 当前 active → rolled_back（不动物理行）
- previous → active（不动物理行）
- 写 ActivationRecord(action=rollback)
- 发 LEDGER_DATASET_ROLLED_BACK 事件（含 `old_dataset_id` + `new_active_dataset_id`）

### 9.6 三阶段部署路径（Day 0 / Day 7 / Day 30）

见 `docs/adr/ADR-002-ledger-view-refactor.md`：

| 阶段 | 动作 | 风险 |
|------|------|------|
| Day 0 | deploy B' 代码 + 新索引 `idx_tb_*_active_queries` | 零停机，双模式并存 |
| Day 7 | Alembic `view_refactor_cleanup_old_deleted_20260517` 分块 UPDATE 老 active 行 is_deleted=true→false | 一次性 180-200s，不锁表（100k/批 + pg_sleep(1)） |
| Day 30 | DROP INDEX `idx_tb_*_activate_staged`（~55MB 回收） | 只影响已无业务意义的索引 |

Day 7 迁移**仅对 PG 生效**，SQLite 环境直接 return（见 `test_migration_day7_update.py`）。

### 9.7 CI 护栏（防回归）

`.github/workflows/ci.yml` 的 `backend-lint` job 扫：

```
grep -rE "Tb(Balance|Ledger|AuxBalance|AuxLedger)\.is_deleted\s*==" backend/app/
```

命中数 > baseline（6 处兜底分支）即 CI fail。见 `.kiro/steering/conventions.md`
账表四表查询规约。

---

## 10. 下游绑定（合规关键 / F50）

> 对应需求：`requirements.md` F50 / F53
>
> 业务诉求：审计报表一旦签字（transition_to_final），所引用的账表数据版本
> 必须被"快照冻结"。下次导入新版本或回滚都不能影响已签字报表看到的数据。

### 10.1 bound_dataset_id 字段

4 张下游表新增字段：

| 下游表 | 绑定字段 | 写入时机 |
|--------|---------|---------|
| `workpapers` | `bound_dataset_id` / `dataset_bound_at` | 底稿首次生成时 |
| `audit_reports` | `bound_dataset_id` / `dataset_bound_at` | transition_to_final 时 |
| `disclosure_notes` | `bound_dataset_id` / `dataset_bound_at` | 附注创建时 |
| `unadjusted_misstatements` | `bound_dataset_id` / `dataset_bound_at` | 错报建单时 |

对应 Alembic：`view_refactor_dataset_binding_20260519.py`。

### 10.2 绑定时机差异

**细粒度策略**：不同下游对象的"生命周期"不同，绑定时机不一

- Workpaper：首次生成即绑定（助理从 V1 开始做稿，中途 V2 导入不应让稿数
  字漂移）
- DisclosureNote：创建时即绑定（同上）
- UnadjustedMisstatement：建单时即绑定
- AuditReport：**仅 final 时锁定**（draft/review 阶段不绑定，允许跟随最新 active
  数据更新；一旦签字 transition_to_final 立即 freeze）

### 10.3 查询路径

下游 service 查询 Tb* 时优先用 bound_dataset_id：

```python
from app.services.dataset_query import get_active_filter

# 优先使用绑定的版本（合规关键）
dataset_id = workpaper.bound_dataset_id  # 可能为 None（未绑定或旧数据）

cond = await get_active_filter(
    db, TbLedger.__table__, project_id, year,
    force_dataset_id=dataset_id,  # F50 关键参数
)
```

`get_active_filter` 在 `force_dataset_id` 非 None 时直接使用该 id（忽略
`status=active` 查询），保证查看的就是绑定时的数据快照。

### 10.4 Rollback 保护（F50 合规 gate）

`DatasetService.rollback` 在执行前检查当前 active dataset 是否被 final/eqcr_approved
状态的 AuditReport 绑定：

```python
# app/services/dataset_service.py::rollback
bound_reports = await db.execute(
    sa.select(AuditReport.id, AuditReport.status, AuditReport.year)
    .where(
        AuditReport.bound_dataset_id == current.id,
        AuditReport.status.in_((ReportStatus.final, ReportStatus.eqcr_approved)),
    )
)
if bound_reports:
    raise HTTPException(409, detail={
        "error_code": "SIGNED_REPORTS_BOUND",
        "message": f"无法回滚：{len(bound_reports)} 份已定稿/EQCR 复核报表...",
        "reports": [...],
    })
```

### 10.5 force-unbind 逃生舱（双人授权）

极端场景（审计复核发现数据确需撤回）：

```
POST /api/datasets/{id}/force-unbind
Body: {
  "reason": "复核发现 V2 数据异常，需要撤回已签字报表",
  "admin_pin": "xxx",
  "co_signer_user_id": "uuid-of-2nd-admin"
}
```

- 需 admin 角色 + 2 人共同确认（类似 EQCR 双签）
- 解除 bound_dataset_id 后 rollback 才能执行
- 解绑动作写 `security_audit_log`（AL-06 级别）

见 `.kiro/specs/ledger-import-view-refactor/design.md` D13 决策细节。

### 10.6 retention 保留期联动（F53）

`ImportArtifact.retention_class` 三档：

| retention_class | 触发条件 | 保留期 | 描述 |
|-----------------|---------|--------|------|
| `transient` | 无下游对象引用 | 90 天 | 临时导入文件 |
| `archived` | 被 Workpaper/Misstatement 引用 | 3 年 | 一般审计档案 |
| `legal_hold` | 被 final/eqcr_approved AuditReport 引用 | 10 年 | 会计档案管理办法要求 |

`purge_old_datasets` 定时任务（每晚 03:00）遵守此分类：
- transient 超期 → 可 purge
- archived / legal_hold → 永不 purge（除非 force-unbind）

### 10.7 下游 stale 联动（F46）

`rollback` 发布 `LEDGER_DATASET_ROLLED_BACK` 事件：

```
event_handlers._mark_downstream_stale_on_rollback(event):
    # 把 bound_dataset_id == old_active_id 的 Workpaper/Report/Note
    # 标记 is_stale=true，前端显示"数据源已回滚，请确认"横幅
```

见 R1 event_handlers.py + `test_rollback_downstream_stale.py`。

### 10.8 一致性检查点（CI 强制）

- `test_workpaper_dataset_binding.py` — 底稿生成必须绑定
- `test_signed_report_rollback_protection.py` — 已签字报表拒绝 rollback
- `test_purge_respects_bindings.py` — purge 任务不得误删被绑 artifact
- CI `ledger-import-smoke` job 全部必跑

