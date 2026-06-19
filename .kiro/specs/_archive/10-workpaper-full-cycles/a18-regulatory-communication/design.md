# A18 监管沟通函 — 设计文档

## 前置依赖

> **权威定义**：[completion-phase-infra](../completion-phase-infra/requirements.md)。  
> A18-P2 **依赖 A17-core 章节数据源**（2026-06-18：A17-1/KAM 已就绪，见 [linkage.md](../completion-phase-infra/linkage.md)）。

---

## 架构决策

### 双模式处理

| 底稿 | 模式 | componentType |
|------|------|---------------|
| A18-1 | WpPopupDocxEditor 弹窗 | （无独立 componentType，走弹窗） |
| A18-2 | 结构化 HTML 表单 | `regulatory-letter` |

### 与 A17-1 共享抽象

见 A17 design §「结构化函件编辑」— 共用 checklist_responses 契约、颜色语义、export-word 端点、提示栏 CSS。

差异：A18-2 有信函表头+签名区+4 固定议题；A17-1 为 16 章节导航无表头。

### componentType: `regulatory-letter`

仅 **A18-2** 使用。

```python
_WP_CODE_OVERRIDE["A18-2"] = "regulatory-letter"
# A18-1 无 override：从程序表 chip 弹窗打开，不独立路由
```

### 前端：GtRegulatoryLetter.vue

三段式布局：

1. **表头区**：监管机构（输入/下拉：证监会XX局/银保监/其他）+ 公司名 + 年度
2. **议题卡片区**（4 卡片）：适用 Y/N + textarea + GtIndexChip wp_ref + 议题 3 三选一 radio
3. **签名区**：致同 + 合伙人 + 日期
4. **工具栏**：导出 Word + 检查未完成项

每议题顶部：**提示栏**（折叠，准则引用，不导出）。

### 数据存储

复用 `checklist_responses` — 见 [persistence.md](../completion-phase-infra/persistence.md)。

### A18 程序表

✅ `procedure_table_templates.json` **A18** 2 步（seq2 ref `A18-1,A18-2`）；`applicable_categories: ["A","B"]`。

---

## Word 导出

### 引擎

- 共享 `docx_template_filler.py`（PRE-2，**不在本 spec 实现**）
- A18 编排：`regulatory_letter_service.py` → 调用 filler，传入议题数据 + 表头

### 颜色语义流程

1. 复制 `A18-2 与监管层沟通函 (通用)2019.docx` 模板
2. 红色段落 → 占位符替换（XX/201X）
3. 蓝色段落 → 适用且已填→替换为描述；适用未填→保留并标记未完成；不适用→删除
4. 不适用议题整段删除（标题到下一标题）
5. 注释表格删除
6. 签名区替换

### API 端点（统一命名，与 A17 共用 export-word 路由）

```
GET /api/projects/{pid}/working-papers/{wp_id}/export-word
GET /api/projects/{pid}/working-papers/{wp_id}/export-word/check-incomplete
```

后端按 `wp_code`（A18-2）或 `component_type=regulatory-letter` 分发到 `regulatory_letter_service`。

~~废弃~~：`/regulatory-letter/export` 专用路径（design 旧版，已统一到 export-word）。

---

## 联动取数（P1，修正版）

### issue_tickets

见 [completion-phase-infra §issue_tickets](../completion-phase-infra/requirements.md#issue_tickets-取数映射舞弊违规)。A18 P1 实现 `get_regulatory_issue_hints()` 返回计数+标题，不写入 remark。

### A8 其他信息

- 读 A8 程序表 seq 3/4/5 的 `status`（completed/in_progress/pending）
- 映射到议题 3 的 radio 建议值（用户可覆盖）

### P0 不做自动联动

P0 仅手动 GtIndexChip 引用。

---

## 不做

- 富文本编辑（纯文本足够）
- A18-1 专用 HTML 组件（弹窗够用）
- P0/P1 自动填充议题正文
- A18-1 审计小结生成（P2 ✅ — `a18_summary_generator` + 弹窗 UI）

---

## 技术方案

### 后端

| 文件 | 分期 | 职责 |
|------|------|------|
| `regulatory_letter_service.py` | P1 | ✅ 导出编排 + 未完成检测 + issue_hints |
| `a18_summary_generator.py` | P2 | ✅ 章节+KAM 生成；prefilled-download 注入 docx |
| checklist_responses 既有端点 | P0 | 议题 CRUD |

### 前端

| 文件 | 分期 |
|------|------|
| `GtRegulatoryLetter.vue` | P0 | ✅ |
| htmlRendererRegistry `regulatory-letter` | P0 | ✅ |
| E2E | P0/P1 | ✅ `e2e/a18-regulatory.spec.ts` |

### _WP_CODE_OVERRIDE

```python
"A18-2": "regulatory-letter",
```
