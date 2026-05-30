# 全局联动总线（Unified Linkage Bus）— 设计文档

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v1.0 | 2026-05-17 | 初始版本 | requirements.md v1.0 |

---

## D1 统一 URI 寻址格式

**格式**：`{module}:{code}:{sheet_name}:{label}`

| 段 | 含义 | 示例 |
|----|------|------|
| module | 模块标识 | WP / REPORT / NOTE / ADJ / TB / FORMULA / MAPPING |
| code | 模块内编码 | D2 / BS-005 / 5.7 / 1122 |
| sheet_name | Excel sheet 精确标签名（非 Excel 模块留空） | 审定表D2-1 / 折旧分配分析表H1-13 |
| label | 语义标签 | 期初余额 / 销售费用折旧 / aje_net |

**设计决策**：
- label 用语义描述（稳定，不受插入行影响）
- 物理坐标（D13/C10）只在运行时动态解析，不存入依赖图
- sheet_name 用 Excel 精确标签名（天然唯一）
- `=WP('H1','折旧分配分析表H1-13','销售费用折旧')` 公式三参数恰好是 URI 后三段

---

## D2 统一依赖图数据结构

```python
# backend/data/unified_dependency_graph.json
{
  "nodes": [
    {"uri": "WP:D2:审定表D2-1:未审数", "module": "WP", "code": "D2"},
    {"uri": "TB:1122::期末余额", "module": "TB", "code": "1122"},
    {"uri": "REPORT:BS-005::当期金额", "module": "REPORT", "code": "BS-005"},
  ],
  "edges": [
    {"source": "TB:1122::期末余额", "target": "WP:D2:审定表D2-1:未审数", "type": "data_flow", "severity": "blocking"},
    {"source": "WP:D2:审定表D2-1:审定数", "target": "REPORT:BS-005::当期金额", "type": "data_flow", "severity": "warning"},
  ]
}
```

**6 个数据源 → 边提取逻辑**：

| 数据源 | 边提取方式 |
|--------|-----------|
| prefill_formula_mapping.json | 解析 cells[].formula 中的 TB()/ADJ()/WP()/PREV() → 构建 source→target 边 |
| cross_wp_references.json | source_wp:source_sheet:source_cell → targets[].wp_code:sheet:cell |
| report_config.formula | 解析 TB()/SUM_TB()/ROW() → TB:code → REPORT:row_code |
| L3 dependencies | source_wp:source_sheet:source_cell → same_wp:target_sheet:target_cell |
| note_account_mapping | WP:code:sheet:label → NOTE:section:field |
| account_mapping | MAPPING:code → TB:code / WP:code / REPORT:code |

---

## D3 Stale Propagation Engine

```python
class StalePropagationEngine:
    def __init__(self):
        self._graph: dict[str, list[str]] = {}  # adjacency list
        self._reverse_graph: dict[str, list[str]] = {}  # for reverse lookup
        self._degraded: bool = False
    
    async def on_change(self, source_uri: str, project_id: UUID, year: int) -> dict:
        """统一入口：变更 → BFS → 写 DB → SSE 推送"""
        if self._degraded:
            return await self._fallback_mark_stale(project_id)
        
        affected_uris = self._bfs(source_uri, max_depth=5)
        await self._mark_stale_by_uri(affected_uris, project_id, year)
        await self._notify_frontend(project_id, affected_uris)
        await self._write_audit_log(source_uri, affected_uris, project_id)
        return {"affected": affected_uris, "total": len(affected_uris)}
    
    def _bfs(self, start: str, max_depth: int) -> list[str]:
        """BFS 遍历，visited 防环，max_depth 截断"""
        
    async def _mark_stale_by_uri(self, uris: list[str], project_id, year):
        """按 URI 前缀分发：WP→prefill_stale / REPORT→is_stale / NOTE→is_stale"""
        
    async def _notify_frontend(self, project_id, affected_uris):
        """SSE 推送 linkage:stale-changed 事件"""
```

---

## D4 FormulaReverseIndex

```python
class FormulaReverseIndex:
    """被引用方 → 引用方 反向索引"""
    
    # 产出示例：
    # "TB:1122::期末余额" → ["WP:D2:审定表D2-1:未审数", "REPORT:BS-005::当期金额"]
    # "WP:H1:折旧分配分析表H1-13:销售费用折旧" → ["WP:K8:审定表K8-1:折旧"]
    
    def build(self) -> dict[str, list[str]]:
        """从 3 个数据源构建反向索引"""
        # 1. prefill_formula_mapping: 解析每条公式的引用目标
        # 2. report_config.formula: 解析 TB()/ROW() 引用
        # 3. cross_wp_references: targets[].formula 中的 =WP() 引用
```

---

## D5 运行时 Label 解析器

```python
class LinkageLabelResolver:
    """语义 label → 物理坐标 (row, col)"""
    
    # 三层优先级：
    # 1. address_label_overrides.json overrides（用户手动指定）
    # 2. address_label_overrides.json header_rules（用户指定数据起始行）
    # 3. 启发式全 sheet 扫描（找"数据区域首行"）
    
    # 缓存：Redis key = resolve:{project_id}:{wp_code}:{sheet_name}:{label}
    # TTL = 24h，底稿保存时清除该 wp 缓存
```

---

## D6 降级策略

```
正常模式：on_change → BFS → mark_stale → SSE
降级模式：on_change → 跳过 BFS → 回退 event_handlers 粗粒度 mark_stale
触发条件：依赖图加载失败 / Redis 断连
恢复条件：下次 on_change 时自动检测 Redis 可用 → 清除 _degraded
前端降级：/api/linkage/impact 返回 503 → useStaleImpact 静默（不显示黄条，不阻断保存）
```

---

## D7 新增事件类型

| 事件 | 触发点 | payload |
|------|--------|---------|
| FORMULA_CONFIG_CHANGED | report_config PUT | {row_code, old_formula, new_formula} |
| PREFILL_MAPPING_CHANGED | seed-all 端点 | {changed_wp_codes} |
| NOTE_SECTION_SAVED | disclosure_notes PUT | {project_id, year, section_code} |
| ACCOUNT_MAPPING_CHANGED | account_mapping CRUD | {project_id, affected_account_codes} |
| REPORT_ROW_CHANGED | generate_all_reports 完成 | {project_id, year, changed_row_codes} |
| TB_MANUAL_EDITED | trial_balance 手动编辑 | {project_id, year, account_codes} |

---

## D8 API 端点清单

| 端点 | 方法 | 用途 |
|------|------|------|
| /api/linkage/graph | GET | 获取统一依赖图（全局） |
| /api/linkage/impact | GET/POST | BFS 下游影响（替代 /v2/notify-cell-change） |
| /api/linkage/resolve | GET | 语义 URI → 物理坐标 |
| /api/linkage/formula-usage | GET | 从公式找引用方 |
| /api/linkage/formulas-for | GET | 从文档找公式 |
| /api/linkage/cell-detail | GET | 单元格完整公式详情 |
| /api/linkage/override | POST/GET/DELETE | 用户手动校正 |
| /api/linkage/header-rule | POST/GET | 表头规则 |
| /api/linkage/audit-log | GET | 传播审计日志 |
| /api/linkage/health | GET | 引擎健康检查 |

---

## D9 前端组件变更

| 组件 | 动作 | 内容 |
|------|------|------|
| useStaleImpact.ts | 升级 | 改调 /api/linkage/impact |
| WorkpaperEditor.vue | 追加 | 右键"查看公式详情" |
| ReportView.vue | 追加 | 行右键"查看公式来源" |
| DisclosureEditor.vue | 追加 | 单元格右键"查看数据来源" |
| TrialBalance.vue | 追加 | 科目行右键"查看引用方" |
| Adjustments.vue | 追加 | 分录行右键"查看影响范围" |
| FormulaManagerDialog.vue | 增强 | 引用方列 + 健康度卡片 + URI 搜索 |
| WorkpaperSidePanel.vue | 追加 | 新 Tab "公式"（DocumentFormulaList） |
| CellFormulaDetail.vue | 新建 | 单元格公式详情弹窗 |

---

## D10 兼容策略

- event_handlers.py：保留全部 handler，末尾追加 `stale_engine.on_change()`
- /v2/notify-cell-change：保留 30 天后删除，标 deprecated
- prefill_engine.py / report_engine.py / formula_unified.py：不改
- WorkingPaper.prefill_stale / AuditReport.is_stale / DisclosureNote.is_stale：保留，统一引擎写入
