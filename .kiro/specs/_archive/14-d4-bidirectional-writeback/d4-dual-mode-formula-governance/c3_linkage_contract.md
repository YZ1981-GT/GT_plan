# C3 联动契约 — D4 双模式公式治理

> 状态：FROZEN（依据 grep 实证，无 D4 专有联动代码，仅平台通用机制）
> 依据：Requirements 4.1, 4.2, 5.1（`d4-dual-mode-formula-governance/requirements.md`）
> Grep 时间：2026-05-31（当前 HEAD `732ddbbd`）

---

## A. DAG 约束（Requirement 4.1）

### A.1 冻结规则

| 规则 | 契约 |
|------|------|
| 表内公式依赖（同 sheet 跨单元格） | 允许，不以表号或 sheet 编号禁止合理引用 |
| 表间公式依赖（D4-1 依赖 D4-2 等不同 wp_code） | 允许，须在公式依赖图中显式声明（`=WP('D4-2', ...)` 或 `=PREV('D4-2', ...)`） |
| 循环依赖（A→B→A 或更长） | 必须**显式失败**（`topological_sort()` 抛 `ValueError`），不得静默通过 |
| Stale 依赖（上游变更，下游未刷新） | 必须**显式标记**（`prefill_stale=true`），不得静默推进 |
| 同 scope（wp_id）只有一个公式 writer | 冲突写入必须阻断或轨迹记录，禁止并发静默覆盖 |

### A.2 现状实现（grep 实证）

**公式 DAG 核心模块**：`backend/app/services/wp_formula_dependency.py`
- `DependencyGraph` 数据结构：`edges`（wp_code → 被依赖 wp_codes 集合）+ `reverse_edges`
- `extract_wp_dependencies(formula_type, raw_args)`：仅 `=WP()` 和 `=PREV()` 产生底稿间依赖；`=TB()`/`=LEDGER()`/`=AUX()`/`=ADJ()`/`=NOTE()` 依赖外部数据源，不产生底稿间循环风险
- `detect_cycles(graph)`：DFS + `rec_stack` 检测循环，返回循环路径列表
- `topological_sort(graph)`：Kahn's BFS，存在循环时抛 `ValueError(f"循环引用检测：以下底稿存在循环依赖: {remaining}")`
- `mark_stale_downstream(db, project_id, changed_wp_code, graph)`：BFS 遍历 `reverse_edges`，将下游底稿标记 `prefill_stale=true`
- `incremental_refresh()`：标记 stale + 按拓扑序逐个重算受影响公式
- PBT 守护：`test_wp_optimization_properties.py::test_property_16_dag_topological_sort_succeeds` 和 `test_property_16_cycle_detection`（`max_examples=5`）

**跨 wp 静态依赖图**：`backend/app/services/stale_propagation_engine.py`
- `StalePropagationEngine._load_graph()`：从 `backend/data/unified_dependency_graph.json` 加载邻接表（source → targets）
- `StalePropagationEngine._bfs(start, max_depth=5)`：BFS + `visited` 防环 + `max_depth` 截断
- URI 格式：`WP:{wp_code}:{sheet}:{cell}`（legacy）或 addr_id `{wp_code}/{sheet_code}/{cell}`
- 降级模式：图加载失败 / Redis 断连 → `_fallback_mark_stale()` 粗粒度标记
- 写 DB：`UPDATE working_paper SET prefill_stale=true`（wp_code 批量）/ `UPDATE financial_report SET is_stale=true` / `UPDATE disclosure_notes SET is_stale=true`
- `on_change(source_uri, project_id, year)`：唯一对外入口

**cross_wp_references 静态数据**：`backend/data/cross_wp_references.json`
- 跨循环引用注册（D~S 循环共 35+ 条），`ref_id` 全局唯一（PBT P3/P4 守护）
- D4 相关引用：CW-417~422（`patch_b60_p3_data.py`）为 B60 相关，**非 D4 专有**
- D 循环无专门 cross_wp_references 条目（grep 未发现 source_wp='D4' 或 source_wp='D2' 等 D4 前缀条目）

**D4 专有 DAG 实现**：**未发现**
- `app/services/d4_extraction/` 目录下无公式 DAG 构建代码
- D4 render 层（`_d4_operating_revenue.py`）仅消费 `tb_fetch` / `D4AccountScope` 做取数，不构建底稿间依赖图

### A.3 契约冻结结论

1. **通用公式 DAG 机制可用**：`wp_formula_dependency.py` 提供完整的 build→detect→sort→mark_stale→refresh 管线；循环检测、拓扑排序、stale 标记均有实现和 PBT 守护
2. **D4 未接入公式 DAG**：D4 渲染层（render 策略）不构建底稿间公式依赖图；若 D4 需要跨表公式联动，须先接入 `wp_formula_dependency.build_dependency_graph` 管线
3. **跨循环 stale 传播依赖静态 JSON**：`unified_dependency_graph.json` 和 `cross_wp_references.json` 是声明式依赖，不经过公式解析器；D4 在 `unified_dependency_graph.json` 中是否有条目**待确认（UNVERIFIABLE）**
4. **单 writer 冲突**：未发现专门的单 writer 仲裁机制；`_on_d_audit_determination_saved` 直接执行 `UPDATE trial_balance SET audited_amount` 无并发锁；并发写入 trial_balance 的冲突检测**待补（TODO）**

---

## B. TB/A13 发布边界（Requirement 4.2）

### B.1 冻结规则

| 规则 | 契约 |
|------|------|
| TB（trial_balance）发布必须显式确认 | 须由用户操作触发，不得后台自动写入 |
| TB 发布必须幂等 | 同一操作重复执行结果一致（无重复记录或重复金额叠加） |
| TB 发布后必须 durable ack | 发布操作完成须有持久化确认记录 |
| A13（错报评价汇总）发布必须显式确认 | 同 TB 规则 |
| 模式切换（HTML↔Excel）不得触发 TB/A13 发布 | 模式切换仅改变渲染，不改变数值 |
| 风险发现 ≠ 错报 | 检测到风险信号不得自动调整 TB/A13；必须人工确认后发布 |

### B.2 现状实现（grep 实证）

**审定表 → TB 回写路径**：`backend/app/services/event_handlers_cycle_linkage.py::_on_d_audit_determination_saved`

```python
async def _on_d_audit_determination_saved(payload: EventPayload) -> None:
    # 正则：^[D-N]\d+-1$（匹配 D4-1 等各循环审定表）
    wp_code = payload.extra.get("wp_code", "")
    if not re.match(r"^[D-N]\d+-1$", wp_code):
        return

    # 遍历 parsed_data.rows，对每行提取 account_code + audited_amount
    # UPDATE trial_balance SET audited_amount = ? WHERE project/year/standard_account_code
    # 成功则 publish_immediate(TRIAL_BALANCE_UPDATED)
```

**关键约束违反点**：

| 违反项 | 现状 | 说明 |
|--------|------|------|
| 显式确认 | **缺失** | `_on_d_audit_determination_saved` 在 `WORKPAPER_SAVED` 事件自动触发，无用户确认步骤；D4-1 审定表保存即自动写 TB |
| 幂等性 | **部分** | `UPDATE ... SET audited_amount=?` 是按 `standard_account_code` 覆盖，重复写入不叠加；但无审计轨迹记录每次发布的幂等确认 |
| durable ack | **缺失** | 回写成功后仅 `logger.info()`，无持久化确认表（如 `tb_publish_ack`） |
| 模式切换不得触发 | **符合** | 模式切换（HTML↔Excel）在 `ContentMutationService` 层，不触发 `WORKPAPER_SAVED` 事件（C1 sync 契约已冻结） |
| 风险发现 ≠ 错报 | **符合** | `_on_b515_high_risk` 触发 D4 IPO 底稿**加载**（创建 wp_index 记录），不修改 TB/A13；风险发现不触发 TB 写入 |

**级联效果**（`TRIAL_BALANCE_UPDATED` 订阅方）：

```
_on_d_audit_determination_saved（审定表 → TB）
    → publish_immediate(TRIAL_BALANCE_UPDATED)
        → ReportEngine.on_trial_balance_updated（报表自动重算）
            → publish_immediate(REPORTS_UPDATED)
                → DisclosureEngine.on_reports_updated（附注增量更新）
                → AuditReportService.on_reports_updated（审计报告刷新）
```

**A13（错报评价）**：grep 发现 `A13` 相关代码仅在测试文件 `test_e1_prefill_no_overwrite.py`（Excel 行 A13 表头）和 `test_e2e_audit_flow.py` 中出现，**无专门的 A13 发布 handler**；A13 是否通过 `TrialBalanceService.on_adjustment_changed` 自动更新**待确认（UNVERIFIABLE）**

### B.3 契约冻结结论

1. **`_on_d_audit_determination_saved` 违反"显式确认"规则**：D4-1 审定表保存自动写 TB，无确认步骤。修复方向：在 D4-1 审定表 handler 中增加 `PUBLISH_CONFIRMATION_REQUIRED=True` 门槛，或引入 `POST /api/tb/publish/confirm` 端点（**TODO，归入 C3 实现任务**）
2. **幂等性部分满足**：SQL UPDATE 覆盖式写入天然幂等（重复执行不叠加）；但缺审计轨迹，无法满足"durable ack"
3. **A13 无专属发布路径**：A13 错报汇总的触发机制**待确认**；grep 未发现 `EventType.A13_UPDATED` 或类似事件
4. **模式切换和风险评估不触发 TB 写入**：符合 Requirement 4.2 冻结规则

---

## C. 四表取数复用（Requirement 5.1）

### C.1 冻结规则

| 规则 | 契约 |
|------|------|
| 所有 D4 科目取数必须通过 `app/services/four_table/` | 禁止在 D4 render/handler 中直接写 TB/tb_balance/tb_ledger 的 SELECT SQL |
| 必须使用 `ReportLineAccountSpec` 声明科目 | 禁止在 D4 代码中硬编码科目码集合 |
| 禁止复制科目 SQL 片段 | 取数逻辑必须委托共享件（`tb_fetch.py` / `report_line_accounts.py`） |

### C.2 现状实现（grep 实证）

**D4 取数路径**（`app/services/d4_extraction/account_scope.py`）：

```python
from app.services.four_table import (
    RESOLVED_FROM_FALLBACK,
    LeafRow,
    ReportLineAccountSpec,           # ← 合规：使用共享 ReportLineAccountSpec
    filter_by_code_specs,
    resolve_report_line_accounts,   # ← 合规：使用共享解析件
)
from app.services.four_table.tb_fetch import (
    fetch_tb_balance_leaves,        # ← 合规：使用共享取数件
    fetch_trial_balance_amounts,
    load_project_context,
)
```

**D4AccountScope 链路**（实证 docstring）：

```
report_config（按准则）       IS-001 = SUM_TB('6001~6099','本期发生额')
                               IS-002 = SUM_TB('6401~6499','本期发生额')
    ↓ resolve_report_line_accounts（共享件；区间码原样返回）
标准码规格集（含区间）
    ↓ to_original_codes_with_flag（共享件；account_mapping 反解，逐项目）
客户原始码前缀集
    ↓ sql_prefixes_for_specs + filter_by_code_specs + select_leaves（共享件）
叶子科目行
```

**D4 在 d_account_resolver 中的登记**（`d_account_resolver.py`）：
- D4 有意**不纳入** `d_account_resolver`（NOT_IN_SCOPE = `{"D1": "...", "D4": "D4 已有自己的 D4AccountScope"}`）
- D4 直接走 `four_table` 共享件，不经过 `d_account_resolver` 中转

**D4 render 层取数**（`_d4_operating_revenue.py`）：
- `build_d4_tb_values(leaves, scope)`：纯函数，从 `fetch_d4_leaf_rows()` 返回的叶子行计算 TB 核对值
- `build_d4_adjudication_prefill(leaves, scope)`：从叶子行生成审定表预填充数据
- `fetch_d4_leaf_rows`（`d4_extraction/d_tb_fetch.py`）：调用 `four_table.leaf_aggregation.select_leaves` 过滤叶子

**违规检查**（grep `LIKE.*6001|LIKE.*6401|FROM trial_balance|FROM tb_balance` in `app/services/d4_extraction/`）：

| 文件 | 是否违规 | 说明 |
|------|----------|------|
| `d4_extraction/account_scope.py` | **合规** | 通过 `get_active_filter` + `resolve_report_line_accounts` 取数 |
| `d4_extraction/d_tb_fetch.py` | **合规** | 委托 `four_table.leaf_aggregation.select_leaves` |
| `routers/wp_render_strategies/_d4_operating_revenue.py` | **合规** | `build_d4_tb_values` 是纯函数，不做 SQL |

**D4-1 审定表 TB 回写**（`event_handlers_cycle_linkage.py`）：
- **写操作**：`UPDATE trial_balance SET audited_amount` 是**写操作**，不属于"取数"范畴；Requirement 5.1 的"四表取数必须复用"针对**读**路径
- 回写路径走 `UPDATE trial_balance` 不经过 `four_table/` 服务，但这是**写入 trial_balance**（不是读取），不违反 Requirement 5.1

### C.3 契约冻结结论

1. **D4 取数完全合规**：`D4AccountScope` + `resolve_report_line_accounts` + `fetch_trial_balance_amounts` 全链路走 `four_table` 共享件，无硬编码科目码 SQL
2. **`ReportLineAccountSpec` 被正确使用**：`D4AccountScope` 构造时传入 `ReportLineAccountSpec(row_code="IS-001"/"IS-002", ...)`，区间码 `SUM_TB('6001~6099')` 由 `resolve_report_line_accounts` 处理
3. **D4 未纳入 `d_account_resolver` 是有意的架构决策**：D4 收入/成本子科目结构高度动态（后缀镜像配对），已有自己的 `D4AccountScope` 处理，且 `NOT_IN_SCOPE` 已登记守卫
4. **回写路径（TB write）不违反 Req 5.1**：Requirement 5.1 约束的是"四表**取数**"（读路径），`_on_d_audit_determination_saved` 的 `UPDATE trial_balance` 是写路径，不在 5.1 范围内

---

## D. WORKPAPER_SAVED 联动接收端

### D.1 冻结规则

| 规则 | 契约 |
|------|------|
| D4-1（审定表）保存后，TB 联动必须通过 EventBus `WORKPAPER_SAVED` 事件触发 | 不得在 save 路径内直接调用 TB 写入 |
| 联动接收端必须可追踪 | handler 名称和订阅关系必须在 `register_event_handlers()` / `register_cycle_linkage_handlers()` 中显式注册 |
| 模式切换不得触发 `WORKPAPER_SAVED` | 模式切换（HTML↔Excel）在 `ContentMutationService` 层处理，不发布 `WORKPAPER_SAVED` 事件 |

### D.2 现状接入（grep 实证）

**`WORKPAPER_SAVED` 事件订阅清单**（grep `event_bus.subscribe(EventType.WORKPAPER_SAVED` in `backend/app`）：

| Handler | 文件 | 订阅位置 | D4 相关性 |
|---------|------|----------|-----------|
| `_on_workpaper_saved` | `event_handlers/_impl.py` | `register_event_handlers()` | **相关**：触发 `ConsistencyCheckService.update_workpaper_consistency()`（比对审定数与试算表） |
| `_on_b515_high_risk` | `event_handlers/_impl.py` | `register_event_handlers()` | **相关**：B51-5 高风险 → 加载 D4-22~D4-32（IPO 应对底稿） |
| `_on_b514_high_risk` | `event_handlers/_impl.py` | `register_event_handlers()` | 不相关（F2 IPO） |
| `_on_c_control_test_saved` | `event_handlers_cycle_linkage.py` | `register_cycle_linkage_handlers()` | 不相关（C 控制测试） |
| `_on_c_deviation_saved` | `event_handlers_cycle_linkage.py` | `register_cycle_linkage_handlers()` | 不相关 |
| `_on_c22_itgc_saved` | `event_handlers_cycle_linkage.py` | `register_cycle_linkage_handlers()` | 不相关 |
| `_on_f_workpaper_conclusion_saved` | `event_handlers_cycle_linkage.py` | `register_cycle_linkage_handlers()` | 不相关 |
| **`_on_d_audit_determination_saved`** | `event_handlers_cycle_linkage.py` | `register_cycle_linkage_handlers()` | **直接相关**：`^[D-N]\d+-1$` 匹配 D4-1，回写 `trial_balance.audited_amount` |
| `_mark_disclosure_stale` | `event_handlers_cycle_linkage.py` | `register_cycle_linkage_handlers()` | **相关**：底稿保存 → 附注章节标记过期（兜底，`DISCLOSURE_AUTO_SYNC_ENABLED` 灰度控制） |
| `_on_h9_save` / `_on_h87_save` | H 循环 event_handlers | — | 不相关 |
| `_on_i2_save` / `_on_i6_save` | I 循环 event_handlers | — | 不相关 |
| F2/B51-4 handler | `event_handlers/_impl.py` | `register_event_handlers()` | 不相关 |

**D4-1 审定表 save 路径**（`_d4_operating_revenue.py` render 层 → 前端 save API）：
- 前端 save API（`POST /api/workpapers/{id}`）更新底稿后发布 `WORKPAPER_SAVED`
- `_on_d_audit_determination_saved` 订阅此事件，**不**在 save 路径内直接调用 TB 写入
- **符合冻结规则**：TB 写入通过 EventBus 事件触发，不在 save 路径内

**`WORKPAPER_SAVED` 事件 payload 结构**（从 handler 读取字段实证）：
```python
EventPayload(
    event_type=EventType.WORKPAPER_SAVED,
    project_id=UUID,
    year=int,
    account_codes=list[str] | None,
    batch_id=str | None,
    entry_group_id=str | None,
    extra={
        "wp_id": str,         # 底稿 ID
        "wp_code": str,       # 底稿编码（如 "D4-1"）
        "parsed_data": {
            "rows": [...],    # 审定表行数据
            "conclusion": {...},  # B51-5 结论（含 risk_level）
        },
        "risk_level": str | None,  # B51-5 风险评估
        "__event_id": str,     # 幂等去重（ImportEventConsumption 表）
    },
)
```

### D.3 契约冻结结论

1. **D4-1 审定表 → TB 联动通过 EventBus**：符合"不得在 save 路径内直接调用 TB 写入"规则
2. **`_on_d_audit_determination_saved` 订阅位置明确**：`register_cycle_linkage_handlers()` 末尾，与 `CONFIRMATION_RECEIVED` 和 `_mark_disclosure_stale` 同一注册批次
3. **D4 IPO 应对底稿加载也通过 WORKPAPER_SAVED**：B51-5 高风险评估保存触发 `_on_b515_high_risk` → `_ensure_d4_ipo_loaded()`，不修改 TB
4. **无 D4 专有的 WORKPAPER_SAVED handler**：D4-1 以外的 D4 底稿（D4-2~D4-36）保存后无专属联动接收端；若需要 D4 内部表间联动（如 D4-2 客户结构 → D4-1 审定表），**待补（TODO，归入 C3 实现任务）**

---

## E. 实现缺口（UNVERIFIABLE / TODO）

### E.1 UNVERIFIABLE（真实数据/环境依赖）

| 缺口 | 原因 | 验证条件 |
|------|------|----------|
| D4 在 `unified_dependency_graph.json` 中是否有 DAG 条目 | grep 未检查该 JSON 文件内容 | 直接读取 `backend/data/unified_dependency_graph.json`，过滤 D4 前缀节点 |
| A13 错报评价汇总的触发路径 | grep 未发现 `A13_UPDATED` 事件或专属 handler | 需确认 A13 是否通过 `TrialBalanceService.on_adjustment_changed` 自动更新，或有独立端点 |
| D4-1 审定表 `parsed_data.rows` 的实际结构 | grep 仅读到 handler 读取 `rows` 字段，未见 D4-1 实际保存的 payload 样本 | 需从真实 PG 或 E2E 项目读取 D4-1 保存后的 `parsed_data` |
| `_on_d_audit_determination_saved` 在 D4-1 保存时的真实触发行为 | 测试文件有源码字符串断言（`inspect.getsource()`），但未见集成级测试直接调用 handler | 需 PG 环境运行 `test_d_cycle_audit_determination_writeback.py` 或类似 |
| `prefill_stale` 标记在 D4 底稿上的实际传播效果 | `StalePropagationEngine._mark_stale_by_uri` 按 wp_code 批量更新，但 D4 在 `unified_dependency_graph.json` 中的节点 URI 格式待确认 | 需确认 D4 节点 URI 前缀（`WP:D4-x:...` vs addr_id 格式） |

### E.2 TODO（需新增实现）

| 缺口 | Requirement | 优先级 | 建议实现 |
|------|-------------|--------|----------|
| D4-1 审定表 TB 发布需**显式用户确认** | Req 4.2 | **P0** | 在 `_on_d_audit_determination_saved` 中增加 `PUBLISH_CONFIRMATION_REQUIRED` 门槛；或新增 `POST /api/tb/publish/confirm` 端点 |
| TB 发布 durable ack 记录 | Req 4.2 | P1 | 新建 `tb_publish_ack` 表或复用 `audit_log`（`event_type='tb_publish_confirmed'`） |
| 单 writer 冲突仲裁 | Req 4.1 | P1 | 对 `trial_balance.audited_amount` 写入增加行级 advisory lock 或 `WHERE` 乐观锁 |
| D4 内部表间联动（D4-2 客户结构 → D4-1 审定表等） | Req 4.1 | P2 | 在 `unified_dependency_graph.json` 中补充 D4 节点边，或新增 D4 专有 `WORKPAPER_SAVED` handler |
| D4 接入 `wp_formula_dependency` 公式 DAG | Req 4.1 | P2 | D4 render 层若需跨表公式（`WP('D4-2', ...)`），须先调用 `build_dependency_graph` |
| A13 发布路径确认 | Req 4.2 | P1 | 确认 A13 是否已有发布机制，或新增 `EventType.A13_UPDATED` |
| `cross_wp_references.json` 补充 D4 专有跨表引用 | Req 4.1 | P3 | 若 D4-2 客户结构有下游（D4-3/4/5...），在 JSON 中登记 `source_wp='D4-2'` 条目 |

### E.3 与 C1/C2 的交叉引用

| 契约 | 文件 | C3 与本契约的交叉点 |
|------|------|---------------------|
| C1 sync | `c1_sync_contract.md` | 模式切换（HTML↔Excel）不触发 `WORKPAPER_SAVED`，与 C3 D.1 冻结规则一致 |
| C2 formula | `c2_formula_contract.md` | 公式 DAG（Req 4.1 A.2）与 C2 公式定义（Req 3）的边界：C2 定义公式语法和白名单，C3 约束公式执行的 DAG 传播 |
| C0 owner | `c0_owner_matrix.md` | D4-1..36 owner 矩阵，C3 D4 联动缺口与 owner 状态相关 |

---

## F. 附录：关键文件索引

| 文件路径 | 关键符号 |
|----------|----------|
| `backend/app/services/wp_formula_dependency.py` | `DependencyGraph`, `detect_cycles`, `topological_sort`, `mark_stale_downstream`, `incremental_refresh` |
| `backend/app/services/stale_propagation_engine.py` | `StalePropagationEngine`, `on_change`, `_bfs`, `_mark_stale_by_uri` |
| `backend/app/services/event_handlers_cycle_linkage.py` | `_on_d_audit_determination_saved`, `register_cycle_linkage_handlers` |
| `backend/app/services/event_handlers/_impl.py` | `_on_workpaper_saved`, `_on_b515_high_risk`, `register_event_handlers` |
| `backend/app/services/d4_extraction/account_scope.py` | `D4AccountScope`, `fetch_d4_leaf_rows`（通过 `d_tb_fetch`） |
| `backend/app/services/d4_extraction/d_tb_fetch.py` | `fetch_d4_leaf_rows`, `build_parent_check` |
| `backend/app/services/four_table/report_line_accounts.py` | `ReportLineAccountSpec`, `resolve_report_line_accounts` |
| `backend/app/services/four_table/tb_fetch.py` | `fetch_trial_balance_amounts`, `fetch_tb_balance_leaves` |
| `backend/data/unified_dependency_graph.json` | DAG 邻接表（D4 节点待确认） |
| `backend/data/cross_wp_references.json` | 跨循环引用注册（D4 前缀条目待确认） |
| `backend/app/routers/wp_render_strategies/_d4_operating_revenue.py` | `build_d4_tb_values`, `build_d4_adjudication_prefill` |
| `backend/app/services/wp_template_init_service.py` | `_ensure_d4_ipo_loaded`, `D4_IPO_CODES` |
