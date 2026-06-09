# 全链路数据溯源 + 回填：现状分析（建 spec 前置）

> 目的：在建 `disclosure-note-deliverable-linkage`（暂名）spec 前，用 codegraph 摸清**已有基础设施 vs 真实空白**，避免重建轮子。
> 分析日期：2026-06-09　分析工具：codegraph（59540 节点已索引）

---

## 一、用户需求拆解

用户要的是**全链路双向数据流**，跨越审计数据全栈：

```
调整分录 adjustments
    ↓ recalc
审定表 trial_balance (audited_amount)
    ↓ 映射
财务报表 financial_report (row_code)
    ↓ bindings 取数
附注表格 disclosure_notes.table_data + text_content
    ↓ 生成
附注出品物 Word (deliverable)
    ↑━━━━━━━━━━━━━━ 回填 ━━━━━━━━━━━━━━┛
```

四个核心诉求：
1. **正向溯源**：点出品物章节 → 看到数据从哪来（左侧引用面板）
2. **跨层跳转**：溯源面板可跳转到上游模块（附注编辑器/报表/审定表/调整分录）
3. **数据刷新感知**：上游变了 → 下游标记"已过期"（stale），可刷新
4. **反向回填**：出品物里改的文字 → 回写到 disclosure_notes.text_content（甚至更上游）

---

## 二、已有基础设施（大量！勿重建）

### 2.1 联动/溯源服务层 ✅ 已存在

| 组件 | 文件 | 能力 |
|------|------|------|
| **LinkageFacadeService** | `linkage_facade_service.py` | 统一穿透入口 `trace(source_type, source_id)`，支持 tb/workpaper/note/report 四类源，返回 LinkageContract + conflict/stale 状态 |
| **wp_trace_service** | `wp_trace_service.py` | `trace_upstream` / `trace_downstream` 双向溯源 |
| **LinkageService** | （已有） | `get_workpapers_for_tb_row` / `get_adjustments_for_tb_row` |
| **WpNoteLinkageService** | （已有） | 底稿↔附注数据联动 `fetch_note_data` |
| **ReportTraceService** | （已有） | 报表行穿透 |
| **TraceEventService** | `trace_event_service.py` | 留痕 + `replay(trace_id, level)` L1/L2/L3 回放（含 before/after snapshot + content_hash） |

### 2.2 事件总线 + Stale 传播 ✅ 已存在

| 组件 | 文件 | 能力 |
|------|------|------|
| **EventBus** | `event_bus.py` | debounce 事件总线 + Redis Stream 持久化 + SSE 推送前端 |
| **StalePropagationEngine** | `stale_propagation_engine.py` | 统一 stale 传播 `on_change(uri, project_id, year)`，URI 格式 `NOTE:code::` / `WP:code:sheet:` |
| **event_handlers** | `event_handlers.py` | 已订阅大量级联：<br>• 调整分录变更 → 标 report + note `is_stale`<br>• REPORTS_UPDATED → DisclosureEngine.on_reports_updated（附注增量更新）<br>• 账套 rollback → 下游 WP/AuditReport/DisclosureNote is_stale<br>• NOTE_SECTION_SAVED → stale_engine 标引用该附注的底稿 |

### 2.3 反向回填 ✅ 部分已存在

| 已有回填链路 | 文件 | 说明 |
|--------------|------|------|
| H9→H8 租赁两表反向回填 | event_handlers.py | ADR-H5 |
| I6↔I2 研发费用↔开发支出 | event_handlers.py | ADR-I4 |
| 底稿审计说明 → 工作簿回写 | wp_explanation_service.py | `_write_back_to_workbook` |
| structure.json → Excel 回写 | wp_structure_bridge.py | 三式联动 |
| 报表主模板回填 | report_config_service.py | suggest/review/diff/apply_master |
| Issue 反向同步 | issue_ticket_service.py | REVIEW_RECORD 双向 |

### 2.4 前端溯源 UI ✅ 已存在

| 组件 | 文件 | 说明 |
|------|------|------|
| **CellTraceDialog** | `notes/CellTraceDialog.vue` | 附注单元格溯源弹窗（trial_balance/ledger/aux_balance 三 tab）|
| **GtTraceabilityDialog** | `workpaper/GtTraceabilityDialog.vue` | 底稿溯源 |
| **TraceSourcePopover** | `common/TraceSourcePopover.vue` | TB 科目/报表行溯源气泡 |
| **DrillDownNavigator** | `extension/DrillDownNavigator.vue` | 穿透导航 |
| **ReportTracePanel** | `views/ReportTracePanel.vue` | 报表溯源面板 |
| **useReportTrace / useLinkageTraceDrawer** | composables | 溯源抽屉状态 |

### 2.5 DisclosureNote 模型 ✅ 已有关键字段

- `is_stale`（过期标记，已被多个 handler 维护）
- `text_content`（文字内容，回填目标）
- `table_data`（表格数据）
- `note_section`（= section_code 主键）

---

## 三、真实空白（需要新建）

经 codegraph 确认，**唯一的真实空白是"出品物层"未接入溯源体系**：

| 空白点 | 现状 | 需要做 |
|--------|------|--------|
| **deliverable 不在 source_type** | LinkageFacade 支持 tb/workpaper/note/report，**无 deliverable** | 加 `source_type='deliverable'`，map deliverable 段落 → section_code |
| **出品物 Word 无段落锚点** | confirm 后 `##SECTION:` 标记已清除，成品里无 section_code 锚 | confirm 时写 hidden bookmark / docProperty 保留 section_code↔段落映射 |
| **OnlyOffice 编辑 → 回填附注** | 现有回填都是 DB↔DB 或 structure↔xlsx，**无 OnlyOffice docx → disclosure_notes.text_content** | OnlyOffice callback 解析 → diff → 回写 text_content（最难） |
| **出品物 stale 感知** | note/report 有 is_stale，**deliverable 无"源已变"标记** | deliverable 版本绑定源数据快照 hash，源变则标 stale |

---

## 四、关键技术难点

### 难点 1：出品物段落 ↔ section_code 映射（P0 基础）

confirm 阶段 `remove_section_markers` 把 `##SECTION:code##` 清掉了，成品 docx 没有锚点。

**方案**：confirm 时不删 section_code，改为写入 Word **隐藏书签**（`w:bookmarkStart name="sec_八_1"`）或 **自定义文档属性**。OnlyOffice 和 python-docx 都能读书签定位段落。

### 难点 2：OnlyOffice 段落级 diff（P2 回填核心）

OnlyOffice callback 只给"文件已保存"信号 + 下载 URL，**不给段落级 diff**。

**方案**：
- 回填时下载编辑后 docx → 按书签定位每个 section 块 → 提取 text → 与 DB `text_content` 比对 → 仅回写变更段
- 表格数字改动**不回填**（审定数是上游算出来的，改了要走调整分录，不能从出品物倒灌）—— 这是审计合规底线

### 难点 3：回填的边界（合规约束）

| 出品物里改的内容 | 能否回填 | 原因 |
|------------------|----------|------|
| 章节说明文字（text_content） | ✅ 可回填 | 文字是人写的，附注模块是其归属 |
| 表格数字（table_data） | ❌ 禁止回填 | 数字来自审定数→报表，改数字必须走调整分录 |
| 章节标题 | ⚠️ 谨慎 | 标题由 section_code + seq 生成，改了会破坏编号 |

**核心原则**：回填只允许"文字说明"这种**叶子内容**，**计算派生数据**（金额）严禁反向倒灌——否则破坏审计数据链可信度。

---

## 五、优先级建议

| 优先级 | 范围 | 依赖 | 工作量 |
|--------|------|------|--------|
| **P0** | 出品物章节溯源面板（复用 LinkageFacade，加 deliverable source_type + 段落锚点）| confirm 写书签 | 中 |
| **P0** | 溯源面板跨层跳转（已有 route 字段，前端接入） | P0 上 | 小 |
| **P1** | 出品物 stale 感知（源数据 hash 快照 + 源变标记） | 已有 is_stale 机制 | 中 |
| **P1** | 单章节增量刷新（不全量重生成） | 附注 template 模式 task 10.2 | 中 |
| **P2** | OnlyOffice 文字回填 disclosure_notes.text_content | 难点 1+2 | 大 |
| **P2** | 回填合规护栏（仅文字、禁金额、冲突检测） | P2 上 | 中 |

---

## 六、与现有 spec 的关系

| 现有 spec | 关系 |
|-----------|------|
| `global-linkage-bus` | **复用** EventBus + 5 反向联动事件 |
| `v3-linkage-stale-propagation` | **复用** StalePropagationEngine |
| `disclosure-note-full-revamp` | **复用** CellTraceDialog + NOTE_SECTION_SAVED 事件 |
| `enterprise-linkage` | **复用** LinkageFacade + 全景图 |
| `audit-report-template-integration` | **依赖** 附注 template 模式（task 10.2）+ confirm 流程改造（写书签）|

**结论**：这个 feature **不是从零建**，而是"**把出品物层接入已有的全链路溯源/stale/回填体系**"。80% 基础设施已就位，新建的主要是：
1. deliverable source_type 适配器（接 LinkageFacade）
2. confirm 写段落锚点（改 TemplateFillService / NoteWordExporter）
3. OnlyOffice 回填管道（P2，最重）

---

## 七、建 spec 前待用户确认的决策点

1. **MVP 切面**：先做 P0（只读溯源面板 + 跳转）验证价值，还是一次做到 P1（含 stale + 增量刷新）？
2. **回填范围**：P2 文字回填是否本期做？还是先只读溯源，回填后续单独立项？
3. **回填合规**：确认"金额禁止从出品物回填，必须走调整分录"这条底线是否符合你的预期？
4. **出品物锚点形式**：隐藏书签 vs docProperty —— 影响 OnlyOffice 兼容性，需实测（建议 spec 设计阶段做 POC）
5. **依赖时序**：此 spec 依赖 `audit-report-template-integration` 的附注 template 模式（task 10.2）真正可用（须先完成 0.6 模板整理）。是否等模板整理完再启动？

---

## 八、命名建议

`deliverable-lineage-and-writeback`（出品物溯源与回填）
- 比 `disclosure-note-deliverable-linkage` 更准确（范围含报告正文/报表，不止附注）
- 强调两大能力：lineage（溯源）+ writeback（回填）
