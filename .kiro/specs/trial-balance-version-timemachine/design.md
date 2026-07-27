# Design Document

## Architecture

单表快照 + 后端薄服务 + 前端抽屉面板。

### Data Model

```
trial_balance_snapshots (新表, V128)
├── id: UUID PK
├── project_id: UUID NOT NULL FK → projects
├── year: INTEGER NOT NULL
├── version_no: INTEGER NOT NULL (auto-increment per project+year)
├── trigger: VARCHAR(30) NOT NULL (recalc / manual_save / import / adjustment_approved / restore)
├── actor_id: UUID NULL (system operations = NULL)
├── content_hash: VARCHAR(64) NOT NULL
├── snapshot_data: JSONB NOT NULL ({detail_rows: [...], summary_rows: [...]})
├── row_count: INTEGER NOT NULL
├── audited_total: NUMERIC NULL
├── created_at: TIMESTAMPTZ NOT NULL DEFAULT now()
└── UNIQUE(project_id, year, version_no)
    INDEX(project_id, year, created_at DESC)
```

### Components

**Backend:**
- `app/services/tb_snapshot_service.py` — `create_snapshot(db, pid, year, trigger, actor_id, detail_rows, summary_rows)` / `list_snapshots(db, pid, year, limit=50)` / `get_snapshot(db, pid, year, version_no)` / `restore_snapshot(db, pid, year, version_no, actor_id)` / `diff_snapshots(db, pid, year, v1, v2)`
- `app/routers/tb_snapshot.py` — 5 端点挂 `/api/projects/{pid}/trial-balance/snapshots`
- `migrations/V128__trial_balance_snapshots.sql`

**Frontend:**
- `components/trial-balance/TbVersionDrawer.vue` — 抽屉面板（版本列表 + 详情 + diff）
- `TrialBalance.vue` — 工具栏加「⏱ 版本历史」按钮 + 集成

### Integration Points

- `recalcTrialBalance` 成功后 → `POST .../snapshots { trigger: 'recalc' }`
- `saveTbSummary` 成功后 → `POST .../snapshots { trigger: 'manual_save' }`
- Content hash dedup: 连续相同 hash 不创建新版本（返回 `{created: false, existing_version}`）

## Components and Interfaces

### TbSnapshotService

```python
class TbSnapshotService:
    async def create_snapshot(self, db, project_id, year, trigger, actor_id=None) -> dict:
        """Capture current trial_balance + saved summary → JSONB snapshot"""

    async def list_snapshots(self, db, project_id, year, limit=50) -> list[dict]:
        """Return [{version_no, trigger, actor_id, created_at, content_hash, row_count, audited_total}]"""

    async def get_snapshot(self, db, project_id, year, version_no) -> dict:
        """Return full snapshot_data + metadata"""

    async def restore_snapshot(self, db, project_id, year, version_no, actor_id) -> dict:
        """1. Create restore-snapshot of current; 2. Overwrite trial_balance; 3. Return new version_no"""

    async def diff_snapshots(self, db, project_id, year, v1, v2) -> dict:
        """Return {changed_rows: [...], added: [...], removed: [...], stats: {}}"""
```

### TbVersionDrawer.vue

Props: `projectId`, `year`, `visible`
Emits: `close`, `restored`

Sections:
1. 版本列表（el-timeline, 倒序, 每项: 版本号+触发类型图标+操作人+时间+变化行数 badge）
2. 版本详情（只读 el-table 同 summary 列结构）
3. 双版本 diff（inline 高亮变化行, 红/绿底色）
4. 恢复按钮（manager+ 门控, 确认弹窗"恢复将创建新快照保留当前状态"）

## Correctness Properties

### Property 1: Snapshot Immutability
Once created, a snapshot record SHALL never be modified or deleted by application code. Validates: Requirement 5.

### Property 2: Deduplication
Consecutive snapshots with identical content_hash SHALL NOT create duplicate records. Validates: Requirement 1.

### Property 3: Restore Preserves Trail
A restore operation SHALL always create a new snapshot (trigger='restore') of the current state BEFORE overwriting. Validates: Requirement 3.

### Property 4: Fail-Open
Snapshot creation failure SHALL NOT block or roll back the triggering operation (recalc/save). Validates: Requirement 6.

### Property 5: Version Monotonicity
version_no within (project_id, year) SHALL be strictly monotonically increasing. Validates: Requirement 2.

### Property 6: Diff Correctness
diff_snapshots(v, v) SHALL return zero changed rows. diff_snapshots(v1, v2) changed set SHALL equal diff_snapshots(v2, v1) changed set (symmetric). Validates: Requirement 4.

### Property 7: Restore Triggers Downstream
After restore, the system SHALL emit event/signal that causes downstream recalc (reports, workpapers). Validates: Requirement 3.

### Property 8: Retention Limit
list_snapshots SHALL return at most 50 versions. Purge SHALL require admin role + explicit confirmation. Validates: Requirement 5.

## Error Handling

- Snapshot JSONB too large (>10MB): log warning, truncate summary_rows to row_code+audited only
- DB constraint violation on version_no: retry with SELECT MAX + 1 (race condition recovery)
- Restore target version not found: 404 with clear message
- Content hash collision (theoretically impossible with SHA-256): log + create anyway (dedup is optimization not correctness)

## Testing Strategy

- PBT: P1 immutability (no UPDATE/DELETE in service code) + P2 dedup + P5 monotonicity
- Integration: create→list→get→restore→diff round-trip with real PG
- Frontend: TbVersionDrawer mount + timeline rendering + diff highlighting
