# Design Document

## Overview

本设计把已建成但从未接线的出品物溯源/回填能力接通，并修正三处会污染审计留痕的缺陷。核心判断：**不重建任何机制** —— `LinkageFacadeService`、`StalePropagationEngine`、`TraceEventService`、`DeliverableSectionStateService`、`DeliverableWritebackService`、`DeliverableRefreshService`、`content_control_injector` 全部已存在且逻辑正确，缺的只是「生产导出路径没调用锚点写入 + 没落章节状态」这一个物理前提，以及标记清理后的锚点定位函数。

四波推进，每波独立可发布：

| Wave | 目标 | 交付判据 |
|------|------|----------|
| 1 | 接线：锚点写入 + 章节状态落库 + 锚点定位 + 三处逻辑修正 + 入口门控 | 真实交付件 `/section-states` 非空、回填真改 DB |
| 2 | 留痕正确性：快照继承 + doc_key + 真实编辑人 + 护栏接线 | OO 保存不洗 stale、版本链作者正确、被拒变更有留痕 |
| 3 | 报告正文段落级回填到 `report_body_json` | 人工润色重新生成后不丢 |
| 4 | xlsx 差异告警 + 溯源可视化 | 手工改数字被告警拦住 confirmed；版本链显示快照 |

### 关键设计决策

| 决策点 | 备选 | 选择 | 理由 |
|--------|------|------|------|
| 锚点形式 | 隐藏书签 / 内容控件 / 二者并存 | **二者并存** | 书签给 python-docx 侧定位（回填/刷新），内容控件给 OnlyOffice 连接器（光标跟随）；`content_control_injector` 已按「只包内部内容、开闭标记留 body 级」实现，两者互不干扰 |
| 暴露 kept_codes | 改 `export` 签名 / 实例属性 / 新方法 | **新方法 `export_with_meta`** | `export` 有 3 个生产调用方 + 大量测试；additive 新方法零回归，`export` 内部委托 |
| 人工编辑检测 | 复用 `source_snapshot_hash` / 复用 `last_writeback_baseline_hash` / 新列 | **新列 `rendered_block_hash`** | 前两者哈希域是「DB 源数据」，与「块内渲染文字」不可比；复用必然恒真（现状即此缺陷） |
| 刷新插入位置 | 文末追加 / 记录索引后 insert / `addprevious` | **`addprevious` 到区间首元素前** | 锚点 `bookmarkStart` 在区间外，`addprevious` 到首内元素前即落在锚点区间内，无需算索引 |
| xlsx 回写 | 单元格级双向 / 只读+差异告警 | **只读 + 差异告警** | 报表数字唯一合法来源是试算表+调整分录，允许改数字回写即绕过调整分录 |
| 报告正文回填目标 | `DisclosureNote` / `report_body_json` | **`report_body_json`** | 段落标识来自模板 placeholder/OPT，与附注章节号不同命名空间；写 `DisclosureNote` 必 0 行 |
| doc_type 支持矩阵 | 前后端各写 / 单一真源 | **后端常量 + 端点下发** | 避免前后端漂移；前端从 `/deliverables` DTO 读能力标志 |

## Architecture

```
【正向（不改）】
trial_balance + report_config ──► ReportExcelExporter ──┐
disclosure_notes ──► NoteWordExporter(template) ────────┼──► DeliverableService.render_and_store ──► 版本链
AuditReport + manifest ──► TemplateFillService ─────────┘

【Wave 1 新增接线（★=本 spec）】
NoteWordExporter.export_with_meta
   ├─ step6.4 ★ write_section_anchors(doc, kept_blocks)  → anchor_map
   ├─ step6.5   inject_content_controls_for_blocks(doc)   （灰度默认改 True）
   ├─ step7     remove_section_markers(doc)               （锚点/控件存活）
   └─ 返回 (BytesIO, NoteExportMeta{kept_codes, anchor_map, rendered_block_hashes})
        │
        ▼（router / FullDeliverablesExecutor）
render_and_store → version_no
        │
        ▼ ★
DeliverableSectionStateService.snapshot_on_confirm(
    task_id, project_id, year, kept_codes,
    anchor_map=…, version_no=…, rendered_block_hashes=…)
        │
        ▼
deliverable_section_state（表首次有数据）
        │
   ┌────┴───────────────┬──────────────────┬─────────────────┐
   ▼                    ▼                  ▼                 ▼
/section-states     /trace            StalePropagation   /writeback /refresh-*
（溯源面板下拉）   （上游链条）        （章节级 stale）    （★ 改走 scan_anchor_blocks）
```

**Wave 1 的物理前提链**：`write_section_anchors` → 标记清理后仍可定位 → `scan_anchor_blocks`（新增纯函数）→ 回填/刷新工作在真实交付件上。三者缺一，整链仍空转。

## Components and Interfaces

### 1. `section_anchor_utils.scan_anchor_blocks`（新增纯函数，Wave 1）

```python
@dataclass
class AnchorBlock:
    section_code: str
    anchor_name: str
    start_el: Any          # w:bookmarkStart
    end_el: Any            # w:bookmarkEnd
    elements: list[Any]    # 区间内 body 级 w:p / w:tbl（不含书签本身）

def scan_anchor_blocks(doc: DocumentObject) -> list[AnchorBlock]: ...
```

- 遍历 `doc.element.body` 直接子元素，按 `w:bookmarkStart[@w:name]` 以 `sec_` 开头开块，按同 `w:id` 的 `w:bookmarkEnd` 闭块。
- 只收集区间内 `w:p` / `w:tbl`（与 `word_doc_utils._body_block_elements` 同口径）。
- `section_code` 经 `section_code_from_anchor` 反解；反解失败跳过并 warning。
- 同名重复取首个 + warning（需求 2.5）。
- 无锚点返回 `[]`（需求 2.2）。

### 2. `word_doc_utils` / `section_anchor_utils` 统一块定位（Wave 1）

新增薄封装 `resolve_section_blocks(doc) -> tuple[str, list[BlockLike]]`：

1. 先 `scan_anchor_blocks`，非空 → `("anchor", blocks)`；
2. 否则 `scan_section_blocks`，非空 → `("marker", blocks)`；
3. 都空 → `("none", [])`。

`DeliverableWritebackService._extract_sections_from_docx` 与 `DeliverableRefreshService.refresh_section` 改调此函数（需求 2.3）。`BlockLike` 鸭子类型只要求 `section_code` + `elements`。

### 3. `NoteWordExporter.export_with_meta`（Wave 1）

```python
@dataclass
class NoteExportMeta:
    kept_codes: list[str]
    anchor_map: dict[str, str]              # section_code → anchor_name
    rendered_block_hashes: dict[str, str]   # section_code → sha256(规范化块内文字)
    variant_key: str

async def export_with_meta(self, ...) -> tuple[BytesIO, NoteExportMeta]: ...
async def export(self, ...) -> BytesIO:      # 委托，签名与返回值不变
```

- 锚点写入插在 step6（`_fill_seq_placeholders`）后：重新 `scan_section_blocks(doc)`（因裁剪已删块），过滤 `kept_codes`，转 `section_anchor_utils.SectionBlock` 后调 `write_section_anchors`。
- `rendered_block_hashes` 在标记清理前按块内非标记段落文字算，口径与 `_detect_user_edits` 完全一致。**共用真源落在 `section_anchor_utils`**，导出：`block_text_of(elements)` → `normalize_block_text(text)` → `block_text_hash(elements)`（三者公开，导出侧与刷新侧共同 import，禁各写一份）。
  - 命名注：本文件早期草稿写作私有 `_normalize_block_text`，落地时因需跨模块共用而改为公开的 `normalize_block_text` / `block_text_hash`。**写守卫请按后者**，按前者 grep 会 0 命中变成空转断言。
- programmatic 模式无 SECTION 块 → meta 三项均空，行为与现状一致。

### 4. `DeliverableSectionStateService`（Wave 1 additive 扩展）

```python
async def snapshot_on_confirm(
    self, word_export_task_id, project_id, year, kept_codes,
    *,
    anchor_map: dict[str, str] | None = None,
    version_no: int | None = None,
    rendered_block_hashes: dict[str, str] | None = None,
) -> None: ...
```

三个新 kwarg 默认 None ⇒ 与引入前逐字节等价。

### 5. `DeliverableRefreshService`（Wave 1 重写两处）

- `_detect_user_edits`：改比 `rendered_block_hash`；列为 NULL 时返 False（需求 4.4）。
- `_insert_refreshed_content` → `_replace_block_content(block, text)`：先对 `block.elements[0].addprevious(new_p)` 逐段插入，再 `remove` 旧 elements；区间为空时对 `block.start_el.addnext(...)` 逆序插入。刷新后重算 `rendered_block_hash` 并随 `clear_section_stale` 落库。

### 6. `DeliverableWritebackService`（Wave 1 + Wave 2）

- Wave 1：`_write_text_content` / `_resolve_conflict_and_write` 返回 `rowcount`；0 行 → 计入新增 `failed` 列表并留痕，不更新基线。`WritebackResult` additive 加 `failed: list[WritebackResultItem]`。
- Wave 2：第 4a 步改调 `_classify_change(code, db_text, block_xml)`；块 XML 由 `resolve_section_blocks` 的 elements 序列化拼接得到。

### 7. `deliverable_capabilities`（新增单一真源，Wave 1）

```python
WRITEBACK_SUPPORTED_DOC_TYPES: frozenset[str]   # Wave1: {disclosure_notes}；Wave3 加 audit_report
SECTION_REFRESH_SUPPORTED_DOC_TYPES: frozenset[str]

def supports_writeback(doc_type: str) -> bool: ...
def supports_section_refresh(doc_type: str) -> bool: ...
```

后端端点前置校验（需求 6.4）；`DeliverableDTOSchema` additive 加 `supports_writeback` / `supports_section_refresh` 布尔，前端据此门控（需求 6.5）。

### 8. `OnlyOfficeCallbackService`（Wave 2）

- `build_editor_config`：`doc_key = f"{task.id}_{version.version_no}"`（去时间戳，需求 7.4）；席位 key 复用同一函数 `deliverable_doc_key(task_id, version_no)`。
- `handle_callback`：Snapshot_Ref 改 `inherit`（读上一版 `source_snapshot_refs`）；编辑人从回调 `users[0]` / `actions[].userid` 解析，解析不出记 None + warning（需求 7.2/7.3）。
- `render_and_store` 新增 `inherit_snapshot_refs: bool = False`：为 True 时不覆盖 `task.source_snapshot_refs`（需求 7.1）。

### 9. 报告正文回填（Wave 3）

- `TemplateFillService.confirm_report_body` 后写入段落锚点（复用 `write_section_anchors`，`section_code` 取模板 section_id，`anchor_name` 前缀区分 `sec_rb_`）。
- 新增 `ReportBodyWritebackAdapter`：`read_upstream(section_id)` / `write_upstream(section_id, text)` 操作 `AuditReport.report_body_json`；`DeliverableWritebackService` 按 `doc_type` 选适配器（附注适配器为现有逻辑抽出）。
- 派生段落（placeholder 填充结果）由 manifest 的 placeholder 清单判定，一律拒绝 + 留痕（需求 9.4）。

### 10. xlsx 差异告警（Wave 4）

- `FinancialReportDriftService.detect(task_id, version_no)`：按 `cell_mapping.json` 读 xlsx 单元格值 vs `ReportExcelExporter` 重算值。返回值区分三态（需求 10.5 / 10.6 / 10.8）：

| 情形 | 返回 / 落库 `drift_report` | `confirm_deliverable` |
|------|---------------------------|----------------------|
| 映射文件不存在（未配映射） | `None` | 放行（fail-open） |
| 映射可解析且全部一致 | `{"diffs": []}` | 放行 |
| 映射可解析且存在不一致 | `{"diffs": [{row_code, sheet, cell, file_value, recomputed_value, diff}]}` | **拒绝** |
| 映射存在但解析失败 | `{"unavailable": "<原因>"}` | **拒绝**（fail-closed，配置坏了不得放行） |

- OO callback 保存 xlsx 后异步触发，结果落 `word_export_task_versions.drift_report` JSONB；`confirm_deliverable` 前置校验按上表判定（需求 10.4 / 10.6 / 10.8）。**判据不是「非空即拒绝」** —— `{"diffs": []}` 非空但表示已比对且一致，必须放行；否则每个配了映射的报表都永远确认不了。

## Data Models

### 迁移 V141（Wave 1）

> **编号说明**：立项时写的 V139 已被 `sampling-compliance-closure` 的 `V139__sampling_registry_batch_binding.sql` 占用（并发 spec），按「迁移版本号永不复用」改用 **V141**（磁盘实际落地号）。

```sql
ALTER TABLE deliverable_section_state
  ADD COLUMN IF NOT EXISTS rendered_block_hash VARCHAR(64);
```

ORM `DeliverableSectionState.rendered_block_hash: Mapped[str | None]`，契约测试 `test_deliverable_section_state_contract` 的期望列集同步 +1。

### 迁移 V143（Wave 4）

> **编号沿革（两次顺延，勿再复用）**：立项写 V140 → 被 `sampling-compliance-closure` 的
> `V140__sampled_vouchers_manual_scope_unique.sql` 占用 → 改 V142 → **又被本 spec Wave 2 的
> `V142__deliverable_version_editor_identity.sql` 占用（已应用真实库）** → 最终用 **V143**。
> 本 spec 迁移编号定稿：Wave 1 = V141（`rendered_block_hash`）/ Wave 2 = V142（`edited_by`、`edited_at`）/ Wave 4 = **V143**（`drift_report`）。
> 落地前仍须再查一次 `backend/migrations/` 最高号（并发会话可能又加了新迁移）。

```sql
ALTER TABLE word_export_task_versions
  ADD COLUMN IF NOT EXISTS drift_report JSONB;
```

### `WritebackResult`（additive）

```python
class WritebackResult(TypedDict):
    written: list[str]
    rejected: list[ChangeClassification]
    conflicts: list[WritebackConflict]
    skipped: list[str]
    failed: list[WritebackFailure]      # ★ 新增：{section_code, reason}
    trace_id: str | None
```

### `DeliverableVersionSchema`（Wave 2 additive）

```python
created_via: str | None          # 已有
source_snapshot_refs: dict | None  # ★
edited_by_name: str | None         # ★
is_stale: bool | None              # ★（相对当前 tb_hash）
```

## Error Handling

| 失败场景 | 处理 | 依据 |
|----------|------|------|
| 锚点写入抛异常 | 捕获 + warning，导出照常完成（交付件仍可用，只是失去溯源能力） | 需求 1.6 |
| `snapshot_on_confirm` 落库失败 | 捕获 + warning，不回滚已落盘的交付件版本 | 需求 1.6 |
| 内容控件注入失败 | 捕获 + warning，跳过注入 | 需求 3.2（既有行为，保留） |
| `section_code_from_anchor` 反解失败 | 跳过该锚点 + warning，其余锚点照常 | 需求 2.1 |
| 同 `section_code` 多锚点 | 取首个 + warning，**禁止静默合并** | 需求 2.5 |
| docx 下载失败 / 解析失败 | 返回全空 `WritebackResult`，保留原值 | 既有行为，保留 |
| 写入影响 0 行 | 计入 `failed` + 可读原因，**不计入 `written`**、不更新基线 | 需求 5.1、5.4 |
| 交付件处于终态 | 回填/刷新一律 409 拒绝，提示走撤回/解锁流程 | 既有行为，保留 |
| 不支持的 `doc_type` | 端点 400 明确错误，不依赖前端门控 | 需求 6.4 |
| 回调无法识别编辑人 | 记 None + warning，**禁止回退 `task.created_by`** | 需求 7.3 |
| `cell_mapping.json` **不存在**（该项目未配映射） | warning + 放行（fail-open），`drift_report` 留 `null` | 需求 10.5 |
| `cell_mapping.json` **存在但解析失败** | warning + `drift_report={"unavailable":原因}` → **拒绝 confirmed**（fail-closed） | 需求 10.6 |
| 留痕写入失败 | warning，不阻断主业务 | 既有语义，保留 |
| 溯源查询超时（>2s） | 504 + 明确原因，前端显示不空白 | 既有行为 + 需求 11.6 |

统一原则：**「失去附加能力」可以 fail-open，「写错数据」必须 fail-closed**。锚点/控件/留痕/差异检测属前者；回填写入、终态校验、能力门控、差异阻断确认属后者。

## Testing Strategy

三层，且**顶层是真实链路**：

1. **纯函数层（单元 + PBT，`max_examples=5`）** —— `scan_anchor_blocks` / `resolve_section_blocks` / `normalize_block_text` / `block_text_hash` / `anchor_name` 往返 / `deliverable_doc_key` / 能力矩阵 / 回填五类互斥。合成 docx 在这一层是合法夹具。
2. **服务层（mock DB / SQLite 内存）** —— `snapshot_on_confirm` upsert、零行写入分类、人工编辑三态、快照继承、护栏拒绝留痕、差异阻断确认。
3. **真实链路层（唯一的任务完成判据）** —— 真实项目 + 真实 PG：生成附注交付件 → `/section-states` 非空且 `anchor_name` 与 `section_code` 一一对应 → 回填一段文字 → `disclosure_notes.text_content` 真变 → 复原。配浏览器实测（chrome-devtools + postgres 只读）确认前端门控与提示。**合成 docx 测试全绿不构成完成判据**（前序 spec 22/22 假绿的直接教训）。

反向自检（Property 25）：每处修复配一条「复现旧行为则守卫打红」用例，并实际做一次变异检验确认它会红 —— 包括「零行写入计入 written」「用 `source_snapshot_hash` 比块文本」「硬编码 `kind=TEXT`」「回退 `task.created_by`」「`doc_key` 含时间戳」五条。

零回归基线：改动前先跑一遍 `test_deliverable_*` / `test_content_control_*` / `test_note_*` 与前端 `deliverable` 目录，记录失败集合；改动后失败集合不得新增（判归属看 traceback 行号是否落在本次改动行上）。

## Correctness Properties

### Property 1: 锚点仅覆盖保留章节

对任意「保留 / 裁剪」章节集合划分，导出后文档中 `sec_*` 书签名集合恰等于 `{anchor_name(c) for c in kept_codes}`。

**Validates: Requirements 1.1, 1.2**

### Property 2: 锚点写入不改变可见内容

对同一输入，写入锚点前后文档全部段落文字序列逐字相等。

**Validates: Requirements 1.3, 3.2**

### Property 3: 章节状态与锚点一一对应

`snapshot_on_confirm` 后，`deliverable_section_state` 中该 task 的 `section_code` 集合等于 `kept_codes`，且每行 `anchor_name == anchor_name(section_code)`。

**Validates: Requirements 1.4**

### Property 4: 锚点扫描与写入互逆

对任意 kept 集合，`scan_anchor_blocks(写入锚点并清理标记后的 doc)` 得到的 `section_code` 集合等于 kept 集合。

**Validates: Requirements 2.1, 2.4**

### Property 5: 块定位降级链单调

`resolve_section_blocks` 在有锚点时返回 `anchor`、仅有标记时返回 `marker`、皆无时返回 `none` 且 `[]`，三种输入下均不抛异常。

**Validates: Requirements 2.2, 2.3**

### Property 6: 内容控件关闭时逐字节等价

灰度关闭时导出结果与引入内容控件前逐字节等价（`sdt` 元素数为 0）。

**Validates: Requirements 3.1, 3.3, 3.5**

### Property 7: 人工编辑检测精确性

块内文字未变时判定「无人工编辑」；块内文字改动任一字符时判定「有人工编辑」；`rendered_block_hash` 为 NULL 时判定「无人工编辑」。

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 8: 刷新保持文档位置

刷新单章节后，该章节在文档中的**序号位置**与刷新前相同，且其余章节文字逐字不变。

**Validates: Requirements 4.5, 4.6**

### Property 9: 零行写入不得计入成功

当写入语句影响 0 行时，`written` 不含该 `section_code`，`failed` 含之且带原因；基线 hash 不变。

**Validates: Requirements 5.1, 5.4**

### Property 10: 回填结果五类互斥且完备

`written` / `rejected` / `conflicts` / `skipped` / `failed` 五类的 `section_code` 集合两两不交，并集等于参与比对的变更章节集合。

**Validates: Requirements 5.2, 5.3**

### Property 11: 能力矩阵前后端一致

对任意 `doc_type`，后端端点是否放行与 DTO 下发的能力布尔值一致；不支持的类型端点返回明确错误。

**Validates: Requirements 6.1, 6.2, 6.4, 6.5**

### Property 12: 无章节状态时给出明确提示

章节状态为空时前端显示「无章节锚点」提示且不渲染空下拉。

**Validates: Requirements 6.3, 11.6**

### Property 13: OO 编辑不改变快照绑定

OO 回调保存产生的新版本，其 `source_snapshot_refs` 与上一版逐字相等；`tb_hash` 变化时该交付件仍被判为 stale。

**Validates: Requirements 7.1**

### Property 14: 编辑人如实记录

回调携带可识别编辑人时记录该人；不携带时记 None 并写 warning；任何情况下不得记为 `task.created_by`。

**Validates: Requirements 7.2, 7.3**

### Property 15: doc_key 确定性且与席位同源

同一 `(task_id, version_no)` 多次请求 config 得到相同 `doc_key`；席位占用与释放使用同一 key。

**Validates: Requirements 7.4, 7.5**

### Property 16: 护栏拒绝表格数字与标题

块内含数字单元格的表格变更被判 TABLE 并拒绝；块首标题段落变更被判 TITLE 并拒绝；两者均产生拒绝留痕。

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**

### Property 17: 报告正文回填目标正确

报告正文回填只写 `AuditReport.report_body_json`，`DisclosureNote` 行数与内容不变。

**Validates: Requirements 9.2**

### Property 18: 派生段落不可回填

placeholder 填充产生的段落被拒绝回填并留痕。

**Validates: Requirements 9.4**

### Property 19: 回填内容在重新生成后保留

回填后重新生成报告正文，已回填段落文字仍在输出中。

**Validates: Requirements 9.6**

### Property 20: xlsx 无回写通道

全仓不存在把 xlsx 单元格值写入 `trial_balance` / `report_config` / `AuditReport` 的代码路径。

**Validates: Requirements 10.1**

### Property 21: 差异告警阻断确认

存在 Cell_Mapping 覆盖单元格的数值不一致时，`confirm_deliverable` 被拒绝；数值一致或**映射文件不存在**时放行；**映射文件存在但解析失败**时同样拒绝（检测不可用不得当作检测通过）。三态由 `drift_report` 的 `null` / `{"unavailable":…}` / `{"diffs":[…]}` 区分。

**Validates: Requirements 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8**

（三态判据：`null` 放行 / `{"unavailable"}` 阻断 / `{"diffs"}` 非空阻断）

### Property 22: 版本链展示中文化且含快照

版本链每项 `created_via` 呈现为中文标签，且展示 `tb_hash` 短标识与 stale 状态。

**Validates: Requirements 11.1, 11.2, 11.6**

### Property 23: 三件套一致性可定位滞后类别

三类绑定 hash 不一致时，返回结果能指出哪一类与多数不同。

**Validates: Requirements 11.3, 11.4**

### Property 24: 正向输出零回归

对同一输入，报表 xlsx 与报告正文 docx 字节不变；附注 docx 的可见段落文字序列不变。

**Validates: Requirements 12.4**

### Property 25: 反向自检有效性

每处修复均有一条「复现旧行为则守卫打红」的自检用例，且该自检在旧实现下确实失败。

**Validates: Requirements 12.5**

### Property 26: 迁移幂等且三层一致

V141 / V142 重复执行不报错；DDL 列集、ORM 字段、service 读写三者一致。

**Validates: Requirements 12.6**
