# 全局联动架构改进方案

> 目标：彻底双向联动、完整性、企业级、可扩展
> 日期：2026-05-17
> 基于：代码考古实测（非推测）

---

## 一、现状诊断（基于 grep + 代码阅读）

### 1.1 底稿模板了解程度

| 维度 | 状态 | 数据量 |
|------|------|--------|
| 477 文件名称 | ✅ 全部清楚 | 179 主编码 |
| 2737 sheet 名称 | ✅ 全部扫描 | template_content_map.json |
| 行/列表头语义 | ✅ 启发式抓取 | 239,693 锚点 |
| 关键单元格物理坐标 | ✅ 已入库 | 374,826 个 |
| 跨 sheet 公式依赖 | ✅ 自动提取 | 42,163 条 |
| 109 个 docx 内容 | ❌ 完全未扫描 | 0 |
| 单元格业务语义核对 | ⚠️ 机器抓取未人工校对 | 误差率未知 |

### 1.2 现有联动机制（两套并存，互不通信）

```
机制 A：EventBus 事件驱动（后端，已跑通）
─────────────────────────────────────────
ADJUSTMENT_CREATED/UPDATED/DELETED
  → TrialBalanceService.on_adjustment_changed → TB 重算
  → mark_stale(project_id, account_codes) → WorkingPaper.prefill_stale=True
  → _invalidate_formula_cache → Redis 清缓存

DATA_IMPORTED / LEDGER_DATASET_ACTIVATED
  → TrialBalanceService.on_data_imported → TB 全量重算
  → mark_stale(project_id) → 全部底稿 prefill_stale=True
  → _invalidate_formula_cache_all

TRIAL_BALANCE_UPDATED
  → ReportEngine.on_trial_balance_updated → 报表增量更新
  → 发布 REPORTS_UPDATED

REPORTS_UPDATED
  → DisclosureEngine.on_reports_updated → 附注增量更新
  → AuditReportService.on_reports_updated → 审计报告刷新

WORKPAPER_SAVED
  → consistency_check → 一致性校验
  → 前端 eventBus 'workpaper:saved' → 附注同步

LEDGER_DATASET_ROLLED_BACK
  → AuditReport.is_stale=True + DisclosureNote.is_stale=True

机制 B：Address Registry V2（前端+后端，刚做）
─────────────────────────────────────────
WorkpaperEditor.onSave
  → useStaleImpact.notify({sheet})
  → POST /v2/notify-cell-change
  → 后端 BFS resolved_refs + L3 公式依赖
  → 返回 stale_targets[] 给前端展示
```

### 1.3 两套机制的断裂点

| 场景 | 机制 A | 机制 B | 结果 |
|------|--------|--------|------|
| 调整分录改 → 底稿 stale | ✅ mark_stale | ❌ 不触发 | 底稿标 stale 但前端无即时反馈 |
| 底稿保存 → 下游底稿 stale | ❌ 不触发 | ✅ BFS 计算 | 前端看到但后端不标 prefill_stale |
| 报表改 → 底稿 stale | ❌ 无 | ❌ 无 | 完全断裂 |
| 公式管理改 → 底稿 stale | ❌ 无 | ❌ 无 | 完全断裂 |
| 附注改 → 底稿 stale | ❌ 无 | ❌ 无 | 完全断裂 |
| 底稿保存 → 附注 stale | ✅ eventBus | ❌ 不触发 | 只走 A 不走 B |

### 1.4 预填充双路径并存

```
路径 1：生成时（wp_template_init_service.py）
  读 prefill_formula_mapping.json → 按语义名称（"期初余额"）找行 → openpyxl 写值
  119 条映射 / 9 种公式类型 / 语义行匹配

路径 2：编辑时（prefill_engine.py:prefill_workpaper_real）
  直接扫 xlsx 内嵌 =TB()/=WP() 公式 → FormulaEngine 执行 → 写 structure.json
  不读 mapping json / 物理坐标匹配

两条路径数据源不同、匹配方式不同、写入目标不同。
```

### 1.5 公式引擎现状

```
report_engine.py:ReportFormulaParser
  → 解析 report_config.formula 字段
  → TB()/SUM_TB()/ROW()/SUM_ROW()/PREV()
  → 从 trial_balance 表取数
  → 写入 financial_report 表

prefill_engine.py:FormulaEngine
  → 解析底稿 xlsx 内嵌公式
  → TB/SUM_TB/WP/AUX/PREV/ADJ/LEDGER/NOTE/TB_AUX
  → 从 trial_balance/tb_ledger/tb_aux_balance/adjustments/disclosure_notes 取数
  → 写入 structure.json

formula_unified.py
  → 统一公式引擎（兼容旧 API）
  → safe_eval + FormulaResult

三套公式引擎并存，各管一段。
```

---

## 二、核心问题总结

1. **单向链路**：数据只从上游流向下游（TB→报表→附注），反向无感知
2. **两套 stale 机制不互通**：后端 prefill_stale 字段 vs 前端 Address Registry BFS
3. **公式管理改动无联动**：report_config.formula 改了，不通知任何底稿
4. **三套公式引擎各管一段**：report_engine / prefill_engine / formula_unified 不共享依赖图
5. **docx 类底稿完全脱离**：109 个 Word 底稿不在任何联动链路中
6. **语义→物理翻译不可靠**：L2 锚点启发式抓取，"审定数"在不同 sheet 可能落在不同列

---

## 三、改进方案：统一联动总线（Unified Linkage Bus）

### 3.1 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    Unified Linkage Bus                            │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ 底稿模块  │  │ 报表模块  │  │ 附注模块  │  │ 调整分录  │        │
│  │ Workpaper │  │ Report   │  │ Note     │  │ Adjustment│        │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘        │
│        │              │              │              │              │
│        ▼              ▼              ▼              ▼              │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │           Dependency Graph（统一依赖图）                   │     │
│  │                                                          │     │
│  │  节点 = 任何可寻址对象：                                    │     │
│  │    WP:D2:审定表D2-1:C10  （底稿单元格）                    │     │
│  │    REPORT:BS-005          （报表行次）                     │     │
│  │    NOTE:5.7:row3:col2     （附注表格单元格）               │     │
│  │    ADJ:1122:aje_net       （调整分录科目净额）             │     │
│  │    TB:1122:closing        （试算表科目余额）               │     │
│  │    FORMULA:BS-005         （公式配置行）                   │     │
│  │                                                          │     │
│  │  边 = 数据依赖关系：                                       │     │
│  │    TB:1122 → WP:D2:审定表:未审数  （TB 供数给底稿）        │     │
│  │    WP:D2:审定表:审定数 → REPORT:BS-005 （底稿供数给报表）  │     │
│  │    WP:D2:审定表:审定数 → NOTE:5.7:row1 （底稿供数给附注）  │     │
│  │    ADJ:1122:aje → WP:D2:审定表:AJE调整 （调整供数给底稿）  │     │
│  │    FORMULA:BS-005 → REPORT:BS-005 （公式定义→报表行）      │     │
│  │                                                          │     │
│  └─────────────────────────────────────────────────────────┘     │
│        │                                                          │
│        ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │           Stale Propagation Engine                        │     │
│  │                                                          │     │
│  │  任何节点变更 → BFS 遍历出边 → 标记下游 stale             │     │
│  │  支持双向：                                               │     │
│  │    正向：源改 → 下游 stale                                │     │
│  │    反向：公式/配置改 → 所有引用该公式的节点 stale          │     │
│  │                                                          │     │
│  └─────────────────────────────────────────────────────────┘     │
│        │                                                          │
│        ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │           Notification Layer                              │     │
│  │                                                          │     │
│  │  后端：写 DB stale 字段 + 发 EventBus 事件                │     │
│  │  前端：SSE 推送 + 编辑器黄条 + 模块级 badge               │     │
│  │                                                          │     │
│  └─────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 统一寻址格式（URI）

```
格式：{module}:{code}:{sheet_or_section}:{cell_or_field}

示例：
  WP:D2:审定表D2-1:C10           底稿 D2 审定表 C10 单元格
  WP:H1:折旧分配分析表H1-13:E15  底稿 H1 折旧分配表 E15
  REPORT:BS-005:current           报表资产负债表第 5 行当期金额
  REPORT:IS-001:current           利润表第 1 行
  NOTE:5.7:应收账款:期末余额      附注 5.7 节应收账款期末余额
  ADJ:1122:aje_net                科目 1122 的 AJE 净额
  ADJ:1122:rje_net                科目 1122 的 RJE 净额
  TB:1122:closing_balance         试算表 1122 期末余额
  TB:1122:opening_balance         试算表 1122 期初余额
  FORMULA:BS-005                  报表公式配置（改公式本身）
  FORMULA:prefill:D2:期初余额     预填充公式配置
```

### 3.3 依赖图构建来源（5 个数据源合并）

| 数据源 | 产出边类型 | 数量级 |
|--------|-----------|--------|
| `prefill_formula_mapping.json` | TB/ADJ → WP | ~500 边 |
| `cross_wp_references.json` | WP → WP / WP → NOTE / WP → REPORT | 107 边 |
| `report_config.formula` 字段 | TB → REPORT / REPORT → REPORT (ROW) | ~300 边 |
| `address_registry_l3_dependencies.json` | WP:sheet → WP:sheet（同文件跨 sheet） | 42,163 边 |
| `note_account_mapping` 表 | WP → NOTE（底稿→附注章节） | ~50 边 |

**合并后总边数**：~43,000 条（去重后）

### 3.4 变更触发点（7 个入口）

| 触发点 | 当前实现 | 改进后 |
|--------|---------|--------|
| 底稿保存 | eventBus WORKPAPER_SAVED + useStaleImpact | 统一走 Linkage Bus |
| 调整分录增删改 | eventBus ADJUSTMENT_* → mark_stale | 统一走 Linkage Bus |
| 账表导入/激活 | eventBus DATA_IMPORTED → 全量 stale | 统一走 Linkage Bus |
| 报表重新生成 | eventBus REPORTS_UPDATED | 统一走 Linkage Bus |
| 公式管理改配置 | ❌ 无 | **新增**：FORMULA_CHANGED → Linkage Bus |
| 附注编辑保存 | ❌ 无 | **新增**：NOTE_SAVED → Linkage Bus |
| 试算表手动编辑 | ❌ 无 | **新增**：TB_MANUAL_EDIT → Linkage Bus |

---

## 四、实施方案（4 个 Sprint）

### Sprint 1：统一依赖图构建（2 天）

**目标**：把 5 个数据源合并为一个 `unified_dependency_graph.json`

```python
# 新建 backend/app/services/linkage_graph_builder.py
class LinkageGraphBuilder:
    """从 5 个数据源构建统一依赖图"""
    
    def build(self) -> dict:
        edges = []
        edges += self._from_prefill_mapping()      # TB/ADJ → WP
        edges += self._from_cross_wp_references()   # WP → WP/NOTE/REPORT
        edges += self._from_report_config()         # TB → REPORT
        edges += self._from_l3_dependencies()       # WP:sheet → WP:sheet
        edges += self._from_note_account_mapping()  # WP → NOTE
        
        # 反向边（公式配置→引用方）
        edges += self._build_formula_reverse_index()
        
        return {
            "nodes": self._collect_nodes(edges),
            "edges": self._deduplicate(edges),
            "stats": {...}
        }
```

**产出**：
- `backend/data/unified_dependency_graph.json`（~2MB，去重后 ~5000 条有效边）
- `GET /api/linkage/graph` 端点
- `GET /api/linkage/impact?uri=WP:D2:审定表D2-1:C10` 端点

### Sprint 2：Stale Propagation Engine 统一化（2 天）

**目标**：用统一依赖图替代现有两套 stale 机制

```python
# 新建 backend/app/services/stale_propagation_engine.py
class StalePropagationEngine:
    """统一 stale 传播引擎"""
    
    async def propagate(self, changed_uri: str, max_depth: int = 5) -> list[str]:
        """BFS 遍历依赖图，返回所有受影响的 URI 列表"""
        
    async def mark_stale_by_uri(self, uris: list[str]):
        """按 URI 类型分发标记：
        WP:* → WorkingPaper.prefill_stale = True
        REPORT:* → FinancialReport.is_stale = True
        NOTE:* → DisclosureNote.is_stale = True
        """
        
    async def on_change(self, source_uri: str, project_id: UUID, year: int):
        """统一入口：任何变更 → 传播 → 标记 → 通知"""
        affected = await self.propagate(source_uri)
        await self.mark_stale_by_uri(affected)
        await self._notify_frontend(project_id, affected)  # SSE 推送
```

**迁移策略**：
- 保留 event_handlers.py 现有逻辑（向后兼容）
- 在每个 handler 末尾追加 `await stale_engine.on_change(uri, ...)`
- 前端 useStaleImpact 改调统一端点

### Sprint 3：反向联动 + 公式管理联动（2 天）

**目标**：实现"报表改→底稿 stale"和"公式管理改→底稿 stale"

```python
# 反向索引构建
class FormulaReverseIndex:
    """从 report_config.formula 解析出 TB 引用，建立反向索引
    
    例：report_config BS-005 formula = "TB('1122','期末余额')"
    → 反向索引：TB:1122 被 REPORT:BS-005 引用
    → 当 TB:1122 变了，REPORT:BS-005 需要 stale
    
    例：prefill_formula_mapping D2 cells[0] formula = "=TB('1122','期初余额')"
    → 反向索引：TB:1122 被 WP:D2:审定表D2-1:期初余额 引用
    → 当 TB:1122 变了，WP:D2 需要 stale
    """
```

**新增事件**：
- `FORMULA_CONFIG_CHANGED`：report_config 表 formula 字段被修改
- `NOTE_SECTION_SAVED`：附注章节保存
- `TB_MANUAL_EDITED`：试算表手动编辑（非公式计算）

### Sprint 4：docx 底稿 + 前端统一展示（2 天）

**目标**：109 个 Word 底稿纳入联动 + 前端统一 stale 展示

**docx 处理**：
```python
# 扫描 docx 占位符 → 注册为 L2 锚点
# 占位符格式：{{company_name}} / {{partner_name}} / {{materiality_level}}
# 来源：wp_prefill_context 端点的字段
```

**前端统一展示**：
- 所有模块（底稿/报表/附注/调整分录）统一 stale badge 样式
- SSE 推送 `linkage:stale-changed` 事件
- 各模块订阅 → 自动刷新 badge

---

## 五、与现有代码的兼容策略

| 现有组件 | 处置 | 理由 |
|---------|------|------|
| event_handlers.py | **保留** + 追加 | 已跑通的联动不动，在末尾追加统一引擎调用 |
| prefill_engine.py | **保留** | 底稿内嵌公式执行逻辑不变 |
| prefill_formula_mapping.json | **保留** | 作为依赖图的数据源之一 |
| cross_wp_references.json | **保留** | 作为依赖图的数据源之一 |
| address_registry_v2 | **升级** | 从独立 BFS 改为调用统一引擎 |
| useStaleImpact.ts | **升级** | 改调统一端点 `/api/linkage/impact` |
| WorkingPaper.prefill_stale | **保留** | 统一引擎写入此字段 |
| AuditReport.is_stale | **保留** | 统一引擎写入此字段 |
| DisclosureNote.is_stale | **保留** | 统一引擎写入此字段 |

---

## 六、可扩展性设计

### 6.1 新增模块接入（3 步）

```
1. 定义 URI 格式：NEW_MODULE:{code}:{field}
2. 在 linkage_graph_builder.py 添加数据源方法
3. 在 stale_propagation_engine.py 添加 mark_stale 分支
```

### 6.2 用户自定义联动规则

```json
// 用户在前端配置：
{
  "source": "WP:D2:审定表D2-1:审定数",
  "target": "NOTE:5.7:应收账款:期末余额",
  "type": "data_flow",
  "severity": "blocking"
}
// 写入 sheet_mapping_rules.json 的 custom_rules
// 统一引擎自动纳入依赖图
```

### 6.3 插件化公式类型

```python
# 新增公式类型只需：
# 1. 在 _FORMULA_RESOLVERS 字典注册
# 2. 实现 async def _resolve_xxx(db, project_id, year, args) → Decimal
# 3. 在 linkage_graph_builder 添加对应边提取逻辑
```

---

## 七、工时估算与优先级

| Sprint | 内容 | 工时 | 价值 |
|--------|------|------|------|
| 1 | 统一依赖图构建 | 2 天 | 基础设施（后续全依赖） |
| 2 | Stale 传播引擎统一化 | 2 天 | 消除两套机制并存 |
| 3 | 反向联动 + 公式管理 | 2 天 | 解决最大断裂点 |
| 4 | docx + 前端统一展示 | 2 天 | 完整性收尾 |
| **合计** | | **8 天** | |

**推荐执行顺序**：Sprint 1 → 2 → 3 → 4（严格串行，每步依赖前步产出）

---

## 八、验收标准

| # | 验收项 | 量化指标 |
|---|--------|---------|
| 1 | 调整分录改 → 底稿+报表+附注全部 stale | 3 模块同时标记 |
| 2 | 底稿保存 → 下游底稿+报表+附注 stale | BFS ≤ 3 层 |
| 3 | 公式管理改 → 引用该公式的报表行 stale | 反向索引命中 |
| 4 | 附注改 → 引用该附注的底稿 stale | 反向边 |
| 5 | 前端任何模块看到 stale badge | SSE ≤ 2s 延迟 |
| 6 | 109 个 docx 底稿纳入联动 | 占位符注册率 ≥ 90% |
| 7 | 统一 URI 格式覆盖全部 5 模块 | 0 遗漏 |
| 8 | 用户自定义联动规则可用 | 前端配置 → 即时生效 |

---

## 九、风险与缓解

| 风险 | 缓解 |
|------|------|
| 依赖图 43000 边 BFS 性能 | 预计算 + Redis 缓存 + max_depth=5 截断 |
| 循环依赖（A→B→A） | visited set 防环 + 检测告警 |
| 旧 event_handlers 与新引擎重复标记 | 幂等设计（已 stale 不重复标） |
| L2 锚点误匹配 | 统一引擎优先用 L1 物理坐标，L2 仅兜底 |
| docx 占位符格式不统一 | 定义标准格式 `{{field_name}}`，扫描时容错 |
