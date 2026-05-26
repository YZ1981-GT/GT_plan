# 附注模块全栈改进 — 设计文档

> **版本**：v1.0（2026-05-26）
> **基于**：requirements.md 59 验收标准 + v2 提案文档 1196 行
> **核心设计原则**：渐进兼容（不重写） + 模板与绑定分离 + DSL 沉淀（不重新发明） + 致同实测真源

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户界面层（5700 行存量）                    │
├─────────────────────────────────────────────────────────────────┤
│ DisclosureEditor.vue (3500)  │  StructureEditor.vue (900)        │
│  ├─ ⚙️ 公式管理               │   ├─ 公式 Tab                     │
│  ├─ 📐 表样编辑               │   └─ 表格结构 Tab                 │
│  ├─ 一键清除公式 / 恢复自动   │  ConsolNoteTab.vue (1300)         │
│  └─ ➕ 新增章节(R4 新增)      │   └─ ❌ 删除内置 dialog (R4)      │
├─────────────────────────────────────────────────────────────────┤
│                       公共组件层                                 │
├─────────────────────────────────────────────────────────────────┤
│  FormulaManagerDialog.vue (scope: note|consol_note|report)      │
│  CellTraceDialog.vue (R3 新增，三栏穿透展示)                    │
├─────────────────────────────────────────────────────────────────┤
│                       后端服务层                                 │
├─────────────────────────────────────────────────────────────────┤
│  DisclosureEngine    │  NoteFormulaGenerator                     │
│  ├─ generate_notes   │  ├─ =TB / =ROW / =PRIOR                   │
│  ├─ update_note_values│  ├─ =AGING (R3 新增)                     │
│  ├─ _build_table_data│  └─ trace_cell (R3 新增)                  │
│  └─ _build_with_binding(R1新增)                                  │
│                                                                  │
│  NoteWordExporter (R5 重写)                                      │
│  ├─ load_template "note_export_template.docx"                   │
│  ├─ render_multi_table (P0 修复)                                 │
│  ├─ apply_gt_three_line / apply_gt_dual_font                    │
│  └─ fill_multi_header (rowspan/colspan)                         │
│                                                                  │
│  NoteColumnSemantics (R1 新增)                                   │
│  └─ 20 个标准列语义 ID 自动识别                                  │
├─────────────────────────────────────────────────────────────────┤
│                       数据层                                     │
├─────────────────────────────────────────────────────────────────┤
│ note_template_{soe,listed}.json     ← 173/187 章节基线（不动）   │
│ note_template_bindings.json         ← R1 新建：列语义+source映射 │
│ custom_note_template_{pid}.json     ← R4 新建：项目级自定义      │
│ note_export_template.docx           ← R5 新建：致同样式 docx     │
│ DisclosureNote.table_data (PG JSONB) ← sidecar 字段渐进扩展     │
│ note_account_mappings (280 条)      ← 复用 note-account-seed    │
│ EventBus + linkage_graph (现有)     ← R2 复用                   │
└─────────────────────────────────────────────────────────────────┘
```

## 二、关键设计决策（D1-D8）

### D1：渐进兼容现有 `_cell_modes` 行级 dict

**背景**：前后端已运行的 schema 是 `row.values=[number]` + `row._cell_modes={"0":"auto","1":"manual"}` 行级 dict + `row.formula_type` 行级公式类型。前端 5 处取数函数（`getCellValue/getCellMode/recalcHorizontalFormula/isFormulaMismatch/onClearAllFormulas`）+ 后端 2 个端点（`POST /clear-formulas` / `POST /restore-auto`）+ 三式联动入口（`triple_format_adapter.update_note_from_structure`）已运行。

**决策**：**新字段以 sidecar 形式追加，不替代现有结构**。

```python
row = {
    # ───── 现有字段（前端老代码继续用，禁止破坏）─────
    "label": "银行存款",
    "values": [12345.67, 11000.00],
    "_cell_modes": {"0": "auto", "1": "manual"},
    "is_total": False,
    "formula_type": "opening_plus_changes",

    # ───── v2 新增 sidecar（老代码读到未知字段忽略）─────
    "row_type": "data",                          # data/header_label/subtotal/total/dynamic_detail/formula
    "_cell_meta": {
        "0": {"manual_value": None, "semantic": "closing_balance",  "binding_id": "F22-1.r3.c1"},
        "1": {"manual_value": 11000.00, "semantic": "opening_balance", "binding_id": "F22-1.r3.c2"}
    }
}
```

**引擎重生成规则（generate_notes / update_note_values）**：
- `_cell_modes[i] == "auto"` → 按 binding 重算 `values[i]` 写入 + 更新 `_cell_meta[i].binding_id`
- `_cell_modes[i] == "manual"` → 保留 `values[i]`；若 `_cell_meta[i].manual_value` 为空则把当前 `values[i]` 备份进去
- `_cell_modes[i] == "locked"` → 连 `values[i]` 都不重算，公式跳过

**为什么必须这样设计**：避免 5700 行已运行代码全要重写；用户手工值原始备份（manual_value）是 v2 新功能"恢复自动提数"的真正价值。

### D2：模板与绑定分离

```
note_template_{soe,listed}.json  ← 章节结构 + headers + rows.label，不动
note_template_bindings.json      ← 数据绑定层（新建）
custom_note_template_{pid}.json  ← 项目级 sections 数组（新建）
```

**绑定文件 schema**：

```json
{
  "version": "2026-1",
  "bindings": {
    "八、22": {
      "wp_code": "F-1",
      "tables": [
        {
          "table_index": 0,
          "table_name": "项目-账面价值",
          "header_normalize": [
            {"text": "项目", "semantic": "row_label"},
            {"text": "期末账面价值", "semantic": "closing_carrying_value"},
            {"text": "期初账面价值", "semantic": "opening_carrying_value"}
          ],
          "rows": {
            "固定资产": {
              "row_type": "data",
              "binding": {
                "closing_carrying_value": {
                  "source": "trial_balance",
                  "field": "audited_amount",
                  "account_codes": ["1601", "1602"],
                  "agg": "sum",
                  "abs_for": ["liability"],
                  "mode": "auto"
                },
                "opening_carrying_value": {
                  "source": "trial_balance",
                  "field": "opening_balance",
                  "account_codes": ["1601", "1602"],
                  "mode": "auto"
                }
              }
            },
            "合计": {"row_type": "subtotal", "formula": "sum(detail)", "mode": "auto"}
          }
        }
      ]
    }
  }
}
```

**字段说明**：
- `agg`：sum / sum_minus（用于负债类）/ avg / max / min / first
- `abs_for`：账户类别列表（asset/liability/equity/revenue/expense），匹配时取绝对值
- `mode`：auto / manual / locked（与单元格 _cell_modes 对齐）

### D3：模板基线 + 项目自定义 union 算法

```python
def merge_templates(baseline_sections: list, custom_sections: list) -> list:
    """合并基线 + 自定义模板，遵守优先级：custom > baseline"""
    baseline_map = {s["section_number"]: s for s in baseline_sections}
    custom_map = {s["section_number"]: s for s in custom_sections}

    # 1. 自定义覆盖基线同 section_number 章节
    merged_map = {**baseline_map, **custom_map}

    # 2. 自定义新增章节（不在 baseline 的）按 sort_order 插入
    new_sections = [s for sn, s in custom_map.items() if sn not in baseline_map]

    # 3. 排序输出
    return sorted(merged_map.values(), key=lambda x: x.get("sort_order", 0))
```

**冲突解决**：
- `section_number` 相同 → 用户自定义版本（含 tables / text_sections 全替换）
- `section_number` 不同 → 按 sort_order 插入

### D4：公式 DSL 沉淀（不重新发明）

`note_formula_generator.execute_note_formulas` 已支持的函数（grep 自源码 + ConsolNoteTab.vue:1212）：

| 函数 | 语法 | 实现入口 | 文档化（R3） |
|------|------|---------|--------------|
| `=TB(account, field)` | TB("货币资金", "期末余额") | `_resolve_tb` | ✓ |
| `=ROW(row_id, col_id)` | ROW(R3, "C2") | `_resolve_row_ref` | ✓ |
| `=PRIOR(account, field)` | PRIOR("货币资金", "期末") | `_resolve_prior` | ✓ |
| `=AGING(account, bucket)` | AGING("应收账款", "1年以内") | **本 spec 新建** | ✓ |
| `=SUM(...)` | SUM(R3:R5) | `_resolve_aggregate` | ✓ |
| `=AVG(...)` / `=MAX(...)` | 标准 Excel 函数 | `_resolve_aggregate` | ✓ |

**=AGING 实现**（R1.2 新增）：

```python
async def resolve_aging(self, account: str, bucket: str, project_id, year):
    """从 TbAuxLedger 反推账龄分桶
    - bucket: "1年以内" / "1-2年" / "2-3年" / "3-5年" / "5年以上"
    - 实现：按 account_code 过滤 → group by aux_code → sum balance →
            for each 挂账记录 voucher_date 计算账龄天数 → 桶分布
    """
    bucket_days = {
        "1年以内": (0, 365), "1-2年": (366, 730), "2-3年": (731, 1095),
        "3-5年": (1096, 1825), "5年以上": (1826, 999999)
    }
    if bucket not in bucket_days:
        raise ValueError(f"Unknown aging bucket: {bucket}")
    if not project_has_aux_ledger(project_id, year):
        return None  # 客户未提供辅助序时账，章节标 not_applicable
    # ... PG 查询 + Python 端分桶
```

### D5：CellTrace 溯源链（R3）

**端点**：`GET /api/disclosure-notes/{note_id}/cells/{row_idx}/{col_idx}/trace`

**实现**（`disclosure_engine.trace_cell`）：

```python
async def trace_cell(self, note_id, row_idx, col_idx) -> dict:
    note = await self._load_note(note_id)
    row = note.table_data["rows"][row_idx]
    cell_meta = row.get("_cell_meta", {}).get(str(col_idx), {})
    binding_id = cell_meta.get("binding_id")

    if not binding_id:
        return {"error": "no_binding", "computed_value": row["values"][col_idx]}

    # 1. 从 binding_id 反查 binding 定义
    binding = self._lookup_binding(note, binding_id)

    # 2. 重新解析公式（不重算，仅展开）
    formula_resolved = self._expand_formula(binding)

    # 3. 拉取证据数据行（限制 sample 100 行）
    evidence = await self._gather_evidence(binding, project_id, year)

    return {
        "binding": binding,
        "formula_resolved": formula_resolved,
        "computed_value": row["values"][col_idx],
        "evidence": evidence,
        "computed_at": cell_meta.get("computed_at")
    }
```

**前端 CellTraceDialog.vue**（新建）三栏布局：
- 左栏：binding 元数据（source / account_codes / agg）
- 中栏：公式展开过程（逐步分解 `=SUM(TB('1601','期末'), TB('1602','期末'))`）
- 右栏：命中数据行表格（点击行 → emit `penetrate-to-tb`，由 `usePenetrate` composable 跳转）

### D6：联动机制（R2）EventBus 订阅

**事件订阅表**（`disclosure_engine.on_event_*`）：

| 事件 | 处理逻辑 | 影响范围 |
|------|---------|---------|
| `LEDGER_DATASET_ACTIVATED` | UPDATE disclosure_notes SET is_stale=true WHERE project_id=? AND year=? | 全部该 project+year 章节 |
| `WORKPAPER_REVIEWED` | 走 linkage_graph 反查 NOTE 节点 → 标 stale | 该底稿引用的章节 |
| `ADJUSTMENT_APPROVED` | 同 LEDGER_DATASET_ACTIVATED | 全部该 project+year 章节 |
| `LEDGER_DATASET_ROLLED_BACK` | 同上 | 全部 |

**前端响应**：
```typescript
// DisclosureEditor.vue
import { useLinkageEvents } from '@/composables/useLinkageEvents'
const { onNoteStale } = useLinkageEvents()
onNoteStale((event) => {
  const section = noteList.value.find(n => n.note_section === event.note_section)
  if (section) section.is_stale = true  // 红点显示
})
```

**重算 != 覆盖**：用户点"重算此章节" → 调 `update_note_values` → 仍走 D1 三态规则，manual/locked 不动。

### D7：致同 Word 排版规范单一真源

**实测来源**：`附注模版/上市报表附注.md` 第 1-30 行 + `附注模版/国企报表附注.md` 第 1-26 行

**模板 docx 结构**（`scripts/build_note_export_template.py` 生成）：

```
backend/data/note_export_template.docx
├─ 段落样式
│  ├─ GTNoteHeading1   仿宋_GB2312 小四 加粗 + 左缩进 -2 字符 + 段前 0 段后 0.9 行 + 居左
│  ├─ GTNoteHeading2   同 H1（致同不靠字号区分层级）
│  ├─ GTNoteHeading3   同上
│  ├─ GTNoteBody       仿宋_GB2312 小四 + 首行不缩进 + 段前 0 段后 0.9 行
│  ├─ GTNoteAfterTable 段前 0.5 行 段后 0.9 行
│  └─ GTNoteUnit       居右（"金额单位：人民币元"）
├─ 字符样式
│  └─ GTNoteNumberRun  Arial Narrow（中文走 eastAsia=仿宋 / 数字走 ascii=Arial Narrow）
├─ 表格样式 GTNoteThreeLine
│  ├─ tblBorders.top    sz="8" (1 磅)
│  ├─ tblBorders.bottom sz="8" (1 磅)
│  ├─ tblBorders.{left,right,insideH,insideV} = nil
│  └─ 表头 cell tcBorders.bottom sz="4" (1/2 磅)
├─ 默认行属性 trHeight hRule="exact" val="397" (0.7cm) + cantSplit
└─ 页面 pgMar top=1814 bottom=1440 left=1701 right=1803 (twip)
```

**关键 OOXML 操作**（详见 v2 §3.2，本 spec 不重复粘贴）：
- `apply_gt_dual_font(run)`：双字体 rPr 注入
- `apply_gt_three_line(table)`：三线表
- `fill_multi_header(table, header_rows, total_cols)`：rowspan/colspan grid 二阶段填充
- `apply_gt_row_height(row, cm=0.7)`：固定行高 + 关闭标题行重复
- `fmt_amount_gt(val)`：空值/零值留白
- `add_landscape_section(doc)`：章节级横向

### D8：自定义模板存储与版本

**文件路径**：`backend/storage/projects/{project_id}/templates/custom_note_template.json`

**Schema**：

```json
{
  "version": 3,
  "updated_at": "2026-05-26T14:00:00Z",
  "updated_by": "uuid-of-user",
  "history": [
    {"version": 1, "snapshot_path": "v1.json", "updated_at": "..."},
    {"version": 2, "snapshot_path": "v2.json", "updated_at": "..."}
  ],
  "sections": [
    {
      "section_number": "八、X1",
      "section_title": "递延收益（用户自定义）",
      "account_name": "递延收益",
      "content_type": "mixed",
      "scope": "both",
      "sort_order": 8990,
      "tables": [...],
      "text_sections": [...],
      "_custom": true
    }
  ]
}
```

**版本回滚**：`POST /api/projects/{pid}/note-template/restore?version=2`，从 history 中读 snapshot.json 替换当前。

**与基线 union**（`disclosure_engine._load_templates`）：
1. 读基线 `note_template_{type}.json`
2. 读 `custom_note_template_{pid}.json`（不存在则跳过）
3. 调 `merge_templates(baseline, custom)`（D3 算法）
4. 返回 union 后的 sections 数组

---

## 三、6 Sprint 拆解

### 前置（1 人天，外部依赖）

```
列语义 review 0.5d  +  致同 PDF 视觉基准 0.5d  +  .md 公式预解析（并入 1.5）
```

**产出**：50+ 变动表 binding 草稿（老审计师标注） + 5-10 张致同 PDF 截图基准库 + `note_validation_rules.json`（从 `附注模版/{soe,listed}版校验公式预设.md` 解析）

---

### Sprint 0（1 人天）：模板治理 + Word P0 修复 + 数据迁移

**0.1 `scripts/cleanup_note_templates.py`**（一次性）：
- 删 headers 中的空字符串占位（约 800+ 处）
- 给每个 row 打 `row_type`（按 label vs headers[0] 启发式 + 人工 review）
- 输出 diff 报告

**0.2 `scripts/migrate_disclosure_notes_to_v2.py`**（幂等）：
- 历史 DisclosureNote.table_data.row 升级为含 `row_type + _cell_meta`
- 前端老代码读 `values + _cell_modes` 仍能跑零回归

**0.3 Word 多表渲染 P0 bug 修复**（30 分钟）：
```python
# note_word_exporter.py 当前
table = doc.add_table(rows=1+len(rows), cols=len(headers))

# 修复后
tables_to_render = note.table_data.get("_tables") or [note.table_data]
for tbl in tables_to_render:
    if tbl.get("name"):
        doc.add_heading(tbl["name"], level=3)  # 多表加表名 H3
    headers = [h for h in tbl.get("headers", []) if h and str(h).strip()]  # 空列裁剪
    self._render_table(doc, tbl)
```

**CI 卡点**：grep `_tables` 必须出现在 `note_word_exporter.py`

---

### Sprint 1（5-6 人天）：数据绑定层 + 列语义识别 + 引擎兼容层

**1.1 新建 `note_template_bindings.json`**（D2 schema）

**1.2 `backend/app/services/note_column_semantics.py`** 列语义识别引擎：
```python
class NoteColumnSemantics:
    def identify(self, header_text: str) -> str:
        """模糊匹配 20 个标准语义"""
        # 期末余额/期末数/期末账面价值 → "closing_balance"
        # 1 年以内/1-2 年/2-3 年 → "aging_bucket_within_1y" / "_1_2y" / "_2_3y"
        # ...
```

**1.3 引擎改造 `disclosure_engine._build_table_data`**：
```python
async def _build_table_data(self, project_id, year, table_template, *, binding=None):
    if binding:
        return await self._build_with_binding(project_id, year, table_template, binding)
    return await self._build_legacy(project_id, year, table_template)  # 兼容层
```

**1.4 模板绑定一次性生成脚本**：
- 90 张"3 列标准表" 自动生成（基于 wp_account_mapping.json 88 条）
- 50+ 变动表人工标注（前置 1d 已完成草稿）

**1.5 .md 公式预解析**（前置并入）：
- `scripts/parse_validation_preset_md.py` 解析两份 `.md` → `note_validation_rules.json` + `note_wide_table_preset.json`

**CI 卡点**：模板 JSON 中 `account_codes` 引用 = 0；后端单测断言 `row._cell_modes[i] in {auto, manual, locked}`

---

### Sprint 1.5（2 人天）：公式 DSL 沉淀 + 三式联动整合

**1.5.1 `docs/NOTE_FORMULA_DSL.md`** 完整 DSL 语法参考（5 函数 + 边界 case）

**1.5.2 ConsolNoteTab 重复公式 dialog 收敛**：
- 删除 `ConsolNoteTab.vue:424` 内置 dialog
- `FormulaManagerDialog` 加 `scope: 'note' | 'consol_note' | 'report'` prop

**1.5.3 单元格级公式 `_formulas` 数组**（不污染 row 结构）：
```python
note.table_data["_formulas"] = [
    {
        "row": 3, "col": 1,
        "expr": '=TB("货币资金","期末余额")',
        "binding_id": "F1-1.r3.c1",
        "evaluated_at": "2026-05-26T10:00:00Z"
    }
]
```

**1.5.4 ADR-007**：`docs/adr/ADR-007-note-triple-format-source-of-truth.md`
- DisclosureNote.table_data 是唯一真源
- structure.json 是镜像（StructureEditor 编辑/HTML 渲染时生成）
- xlsx 是导出/导入交换格式
- 任何写入必须经 `triple_format_adapter.update_note_from_structure` 单入口

**CI 卡点**：grep `noteFormulaRules.value` 在 `ConsolNoteTab.vue` 应消失

---

### Sprint 2（3.5 人天）：Word 真致同样式 + CellTrace + 联动事件

**2.1 `scripts/build_note_export_template.py`** 一次性生成 docx 模板

**2.2 `NoteWordExporter` 重写**（D7 关键 OOXML）：
- `apply_gt_dual_font(run)`
- `apply_gt_three_line(table)`
- `fill_multi_header(table, header_rows, total_cols)`
- `apply_gt_row_height(row, cm=0.7)`
- `fmt_amount_gt(val)`
- `add_landscape_section(doc)`

**2.3 CellTrace 端点**（R3）：
- `GET /api/disclosure-notes/{note_id}/cells/{row_idx}/{col_idx}/trace`
- 前端 `CellTraceDialog.vue` 三栏布局

**2.4 EventBus 订阅 4 类事件**（R2.1）：
- `disclosure_engine.on_event_ledger_activated`
- `disclosure_engine.on_event_workpaper_reviewed`
- `disclosure_engine.on_event_adjustment_approved`
- `disclosure_engine.on_event_ledger_rolled_back`

**2.5 视觉回归测试**：`tests/test_note_export_visual.py` 11 项断言

**CI 卡点**：11 项视觉断言全绿；docx 样式名 grep `GTNote*` 前缀

---

### Sprint 3（3.5 人天）：自定义编辑 + 联动 UI + 智能裁剪

**3.1 StructureEditor 新增能力**（R4.1）：
- ➕ 新增章节按钮
- ➕ 加表 / ➕ 加列 / 列语义下拉
- 删除自定义条目（二次确认 + 回收站）

**3.2 自定义模板存储**（D8）：
- `custom_note_template_{pid}.json` 文件 + 版本历史
- `POST /api/projects/{pid}/note-template/save` / `restore?version=N`

**3.3 联动 UI**（R2.1 前端）：
- 章节列表红点 + tooltip
- 右键"重算此章节"
- `POST /disclosure-notes/{id}/dismiss-stale`

**3.4 NoteTrimService.auto_trim**（v2 §5.3，本 spec 简化版）：
- 检查 binding.skip_if_all_zero 列出科目，TrialBalance 全为 0 → skip
- 期望中小项目 30%+ 章节自动跳过

**3.5 上年附注引用 UI**：
- 复用现有 priorYearNote 数据流
- `POST /api/disclosure-notes/{pid}/{year}/import-prior-year`（仅入口，全量解析留独立 spec）

**CI 卡点**：`auto_trim` 单测覆盖率 ≥ 80%

---

### Sprint 4（2.5 人天）：check_presets 接入 + linkage 增强 + NoteFormatConfig

**4.1 `check_presets` 接入校验引擎**（v2 §5.4）：
```python
PRESET_TO_RULE = {
    "余额": "BALANCE_TIE", "宽表": "WIDE_TABLE_HORIZONTAL",
    "纵向": "VERTICAL_CARRY", "交叉": "CROSS_TABLE_TIE",
    "跨科目": "CROSS_ACCOUNT_TIE", "其中项": "WHEREOF_SUM",
    "二级明细": "DETAIL_LEVEL2_TIE", "完整性": "ROW_COMPLETENESS",
    "账龄衔接": "AGING_PROGRESSION", "LLM审核": "LLM_SEMANTIC_REVIEW",
    "描述": "SKIP",
}
```

**4.2 linkage_graph_builder 增强**（R2.2）：
- 从 `referenced_accounts` 自动生成 NOTE→TB→WP 双向边
- NOTE 节点 ≥ 200（从当前 115 提升）

**4.3 报表 ReportView "附注引用我"侧栏**

**4.4 `note_format_config.py`** 抽出（v2 §5.4）：
- `@dataclass(frozen=True) NoteFormatConfig` 21 项排版参数
- 前端 `GET /api/disclosure-notes/format-config` 拉取应用 CSS 变量

**CI 卡点**：`PRESET_TO_RULE` 必须覆盖 `check_presets` 全部 11 个枚举

---

## 四、风险与缓解

### 风险 1：5700 行已运行代码兼容期破坏

**缓解**：
- D1 sidecar 设计原则：所有新字段不替代现有字段
- 前端老代码读到未知字段必须忽略而非报错（CI 单测断言）
- Sprint 1 上线后，前端不修改任何代码运行 1 周无回归

### 风险 2：50+ 变动表绑定文件人工标注质量

**缓解**：
- 前置 1d 老审计师参与 review
- 列语义识别引擎自动生成草稿，人工只做修正
- Sprint 1 末期跑 3 个真实项目（陕西华氏 / 安徽骨科 / Listed）UAT，命中率 < 95% 时回炉

### 风险 3：致同 Word 视觉基准不可量化

**缓解**：
- 11 项视觉断言转 Python OOXML 解析（不依赖人眼）
- 5-10 张真实 PDF 截图作为 reference，diff 工具人工确认
- 字体名/字号/缩进/边框磅数都可硬断言

### 风险 4：=AGING 函数无辅助序时账时章节生成失败

**缓解**：
- 客户未提供辅助序时账时，对应章节自动标 `not_applicable`（不抛错）
- 前端 UI 显示"本章节因缺少辅助序时账无法自动取数，请手工填写"提示
- 章节裁剪 R3.4 的 auto_trim 自动 skip 这类章节

### 风险 5：自定义模板版本回滚冲突

**缓解**：
- 历史版本 snapshot 存于 `backend/storage/projects/{pid}/templates/v{N}.json` 不可变
- 回滚操作产生新版本（version+1），不覆盖历史
- 用户级 + 项目级权限隔离（仅 admin/manager 可改模板）

---

## 五、ADR 链表（产出物）

本 spec 实施后产生的 ADR 文档：

| 编号 | 标题 | 关联 Sprint |
|------|------|------------|
| ADR-007 | Note triple format source of truth | Sprint 1.5 |
| ADR-008 | Note cell mode persistence (auto/manual/locked) | Sprint 1 |
| ADR-009 | GT Word template style namespace (GTNote*) | Sprint 2 |
| ADR-010 | Note custom template versioning | Sprint 3 |

---

## 六、验收完成标志（Done Definition）

- [ ] requirements.md 全部 59 验收标准 PASS
- [ ] 6 项 CI 防回归卡点全绿
- [ ] 至少 3 个真实项目 UAT 通过（数字 95% 准确 + 视觉 11 项断言）
- [ ] 4 个新增 ADR 入库
- [ ] vue-tsc 0 错误，pytest 全绿
- [ ] memory.md 任务状态从"待办"转"已完成"
- [ ] 文档 `docs/DISCLOSURE_NOTE_IMPROVEMENT_PROPOSAL.md` 顶部加"已实施"标记 + commit hash

