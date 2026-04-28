# Phase 14: 统一门禁引擎与治理收敛 - 设计文档

---

## 1. 核心设计理念

### 1.1 三入口统一判定原则

```
提交复核 / 签字 / 导出
        ↓
   统一 GateEngine
        ↓
 RuleRegistry（QC-01~QC-26）
        ↓
 DecisionAssembler（block/warn/allow）
        ↓
 gate_decisions + trace_events
```

关键原则：
- 同一上下文在三入口必须得到同一判定结果。
- 阻断类规则必须同时返回“定位 + 修复建议”。
- 所有门禁结果必须具备 `trace_id`，可回放、可审计。

### 1.2 规则分层原则

| 层级 | 说明 |
|------|------|
| 平台强制规则 | 不允许租户覆盖（如关键合规阻断） |
| 租户可配置规则 | 允许调整阈值（如告警阈值） |
| 解释模板层 | 规则命中后输出统一修复建议文案 |

---

## 2. 系统架构

### 2.1 逻辑架构

```
API 入口层
  submit-review / sign-off / export
         ↓
GateEngine.evaluate()
         ↓
RuleRegistry + ContextResolver
         ↓
DecisionAssembler
         ↓
Persistence(gate_decisions) + Trace(trace_events)
```

### 2.2 模块职责

| 模块 | 职责 |
|------|------|
| `GateEngine` | 统一调度规则、输出决策 |
| `RuleRegistry` | 注册规则与入口适用范围 |
| `ContextResolver` | 组装规则执行上下文 |
| `DecisionAssembler` | 聚合命中规则并排序 |
| `GateDecisionService` | 门禁结果落库与查询 |

---

## 3. 数据模型变更

```sql
CREATE TABLE gate_decisions (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    wp_id UUID NULL,
    gate_type VARCHAR(32) NOT NULL, -- submit_review/sign_off/export_package
    decision VARCHAR(16) NOT NULL,  -- allow/warn/block
    hit_rules JSONB NOT NULL,
    actor_id UUID NOT NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_gate_decisions_project_gate
ON gate_decisions(project_id, gate_type, created_at DESC);
```

---

## 4. 核心服务设计

### 4.1 GateEngine 服务

```python
class GateEngine:
    async def evaluate(self, gate_type, project_id, wp_id, actor_id, context) -> dict:
        """
        1. 解析上下文（快照、版本、AI确认状态）
        2. 加载适用规则（入口+租户配置）
        3. 执行规则并按 severity 排序
        4. 生成 decision（allow/warn/block）
        5. 落库 gate_decisions + trace_id
        """
```

### 4.2 规则执行顺序

1. 合规阻断（mandatory）  
2. 数据一致性阻断（consistency）  
3. AI确认与冲突阻断（ai/rule-conflict）  
4. 警告与提示（warning/info）

---

## 5. API 设计

### 5.1 门禁评估 API

```yaml
POST /api/gate/evaluate
  body:
    gate_type: submit_review|sign_off|export_package
    project_id: uuid
    wp_id: uuid?
    actor_id: uuid
    context: object
  response:
    decision: allow|warn|block
    hit_rules[]:
      - rule_code
      - error_code
      - severity
      - message
      - location
      - suggested_action
    trace_id: string
```

### 5.2 关键错误码

| 错误码 | http | 含义 |
|------|---:|------|
| `QC_LLM_PENDING_CONFIRMATION` | 409 | 关键LLM内容未确认 |
| `QC_LLM_TRIM_CONFLICT` | 409 | LLM采纳与裁剪冲突 |
| `QC_REPORT_NOTE_VERSION_STALE` | 409 | 正文引用附注版本过期 |
| `QC_NOTE_SOURCE_MAPPING_MISSING` | 409 | 关键披露缺来源映射 |
| `GATE_CONTEXT_INVALID` | 400 | 上下文字段缺失 |

---

## 6. 关键规则与机制

| 规则 | 触发条件 | 结果 |
|------|---------|------|
| `QC-21` | 关键结论 `evidence_refs` 为空 | 阻断 |
| `QC-22` | 单证据且低置信支撑关键结论 | 阻断 |
| `QC-23` | `pending_user_confirm` 存在 | 阻断 |
| `QC-24` | LLM采纳与裁剪策略冲突 | 阻断 |
| `QC-25` | 正文引用附注版本过期 | 阻断 |
| `QC-26` | 关键披露缺 `source_cells` | 阻断 |

---

## 7. 测试与灰度策略

### 7.1 测试矩阵

| 测试层 | 用例 | 通过标准 |
|------|------|---------|
| UT | `QC-21~QC-26` 分支覆盖 | 每条规则通过/阻断各1例 |
| IT | 三入口一致性 | 判定一致率=100% |
| E2E | 前端阻断定位+修复后重提 | 可定位、可修复、可通过 |
| SEC | 越权写入攻击回归 | 越权写入=0 |

### 7.2 灰度放量

- `10% -> 30% -> 100%` 项目放量，每阶段观察 24h。  
- 任一阶段误阻断率 > 3% 即回滚到上一阶段。  
- 回滚不清理 `gate_decisions`，仅回滚执行路径与规则配置。

