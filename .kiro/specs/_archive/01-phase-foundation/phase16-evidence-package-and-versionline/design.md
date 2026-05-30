# Phase 16: 取证包与版本链闭环 - 设计文档

---

## 1. 核心设计理念

### 1.1 三链路闭环原则

```
版本链（Version Line）
        +
取证链（Integrity Chain）
        +
冲突链（Conflict/Merge Chain）
        ↓
统一 Trace 回放
```

设计原则：
- 版本号连续可校验，禁止无版本导出。
- 取证包必须可验真，禁止静默降级为通过。
- 冲突必须可处置可回放，禁止“无痕人工修正”。

---

## 2. 系统架构

### 2.1 逻辑架构

```
对象变更（四表/附注/正文/底稿）
          ↓
VersionLineService
          ↓
ExportIntegrityService
          ↓
OfflineConflictService
          ↓
MergeQueueService + QC Replay
          ↓
TraceReplayService
```

### 2.2 模块职责

| 模块 | 职责 |
|------|------|
| `VersionLineService` | 统一版本戳写入与映射查询 |
| `ExportIntegrityService` | 生成 `manifest`、hash与签名摘要 |
| `OfflineConflictService` | 细粒度冲突检测与分组 |
| `MergeQueueService` | 冲突分配、人工合并、复验回放 |

---

## 3. 数据模型变更

```sql
CREATE TABLE version_line_stamps (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    object_type VARCHAR(32) NOT NULL,   -- report/note/workpaper/procedure
    object_id UUID NOT NULL,
    version_no INT NOT NULL,
    source_snapshot_id VARCHAR(64) NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE evidence_hash_checks (
    id UUID PRIMARY KEY,
    export_id UUID NOT NULL,
    file_path TEXT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    signature_digest VARCHAR(128) NULL,
    check_status VARCHAR(16) NOT NULL,  -- passed/failed
    checked_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE offline_conflicts (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    wp_id UUID NOT NULL,
    procedure_id UUID NOT NULL,
    field_name VARCHAR(64) NOT NULL,
    local_value JSONB,
    remote_value JSONB,
    status VARCHAR(16) NOT NULL,        -- open/resolved/rejected
    resolver_id UUID NULL,
    reason_code VARCHAR(64) NULL,       -- 处置原因码（对齐 v2 4.5.6 统一原因码）
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP NULL
);
```

---

## 4. 核心服务设计

### 4.1 VersionLineService

```python
class VersionLineService:
    async def write_stamp(self, project_id, object_type, object_id, version_no, trace_id): ...
    async def query_lineage(self, project_id, filters): ...
```

约束：同对象 `version_no` 必须连续递增，不允许跳号。

### 4.2 ExportIntegrityService

```python
class ExportIntegrityService:
    async def build_manifest(self, export_id, files): ...
    async def calc_hash(self, file_path): ...
    async def verify_package(self, export_id): ...
```

约束：`manifest` 清单与导出文件一一对应，任一文件 hash 不匹配即判定失败。

### 4.3 OfflineConflictService / MergeQueueService

```python
class OfflineConflictService:
    async def detect(self, project_id, wp_id): ...

class MergeQueueService:
    async def assign(self, conflict_id, resolver_id): ...
    async def resolve(self, conflict_id, resolution, merged_value, reason_code): ...
```

约束：冲突关闭前必须触发 QC 重跑并记录结果。

### 4.4 ConsistencyReplayEngine（对齐 v2 WP-ENT-07）

```python
class ConsistencyReplayEngine:
    """可复算一致性引擎：按快照复算并输出差异项"""

    async def replay_consistency(self, project_id, snapshot_id=None) -> dict:
        """
        按快照复算五层一致性链路：
        1. 四表(tb_balance) -> 试算表(trial_balance)：未审数汇总一致
        2. 试算表 -> 报表(financial_report)：公式驱动取数一致
        3. 报表 -> 附注(disclosure_notes)：关键科目金额一致
        4. 附注 -> 底稿(working_papers.parsed_data)：审定数/结论一致
        5. 底稿 -> 试算表：审定数反向校验

        输出：
        {
            "snapshot_id": "snap_xxx",
            "layers": [
                {
                    "from": "tb_balance",
                    "to": "trial_balance",
                    "status": "consistent",  # consistent/inconsistent
                    "diffs": []
                },
                {
                    "from": "trial_balance",
                    "to": "financial_report",
                    "status": "inconsistent",
                    "diffs": [
                        {
                            "object_type": "report_line",
                            "object_id": "xxx",
                            "field": "audited_amount",
                            "expected": 12000.00,
                            "actual": 12500.00,
                            "diff": 500.00,
                            "severity": "blocking"  # blocking if diff > 0.01
                        }
                    ]
                }
            ],
            "overall_status": "inconsistent",
            "blocking_count": 1,
            "trace_id": "trc_xxx"
        }
        """

    async def generate_consistency_report(self, project_id) -> dict:
        """
        生成可复算一致性报告（附在导出包中）：
        - 复算时间戳
        - 各层级一致性状态
        - 差异明细（含 object_type/field/expected/actual/diff）
        - 阻断级差异数量
        - trace_id 可回溯
        """
```

---

## 5. API 设计

```yaml
GET /api/version-line/{project_id}
  - 返回版本链节点与映射

GET /api/exports/{export_id}/integrity
  - 返回 manifest_hash + file_checks + trace_id

POST /api/offline/conflicts/detect
  - 输入: project_id, wp_id
  - 输出: 冲突列表

POST /api/offline/conflicts/resolve
  - 输入: conflict_id, resolution, merged_value?, resolver_id, reason_code
  - 输出: resolved/rejected + qc_replay_job_id

POST /api/consistency/replay
  - 输入: project_id, snapshot_id?
  - 输出: layers[], overall_status, blocking_count, trace_id
  - 对齐 v2 WP-ENT-07

GET /api/consistency/report/{project_id}
  - 输出: 可复算一致性报告（附在导出包中）
```

关键错误码：
- `VERSION_LINE_NOT_FOUND`
- `EVIDENCE_HASH_MISMATCH`
- `CONFLICT_RESOLUTION_INVALID`
- `CONFLICT_ALREADY_RESOLVED`
- `REPLAY_TRACE_INCOMPLETE`
- `CONSISTENCY_REPLAY_FAILED` — 复算引擎执行失败
- `CONSISTENCY_BLOCKING_DIFF` — 存在阻断级差异（diff > 0.01）

---

## 6. 关键机制

### 6.1 完整性校验机制

1. 构建 `manifest.json`。  
2. 逐文件计算 `sha256`。  
3. 按导出批次写入 `evidence_hash_checks`。  
4. 任一失败则阻断取证包发布。

### 6.2 冲突治理机制

1. 以 `procedure_id + field_name + version` 检测冲突。  
2. 冲突入队并分配处理人。  
3. 人工合并后触发 QC 重跑。  
4. 处置结果写入 `trace_events`，可按 `trace_id` 回放。

---

## 7. 测试与回滚策略

| 测试层 | 用例 | 通过标准 |
|------|------|---------|
| UT | 版本戳、hash、冲突比较器 | 核心分支覆盖 >= 80% |
| IT | 导出完整性校验链路 | 校验通过率 = 100% |
| E2E | 检测->合并->QC重跑 | 漏检=0，链路可回放 |
| SEC | 篡改检测样本 | 命中率 = 100% |

回滚策略：
- 校验失败时保留阅读包，不发布取证包。
- 冲突处理失败回滚到 `open` 状态并保留处置记录。
- 版本链写入失败时阻断签字放行并告警。

