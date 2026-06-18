# 完成阶段公共基础设施 — 设计

> 契约见 [requirements.md](./requirements.md)；持久化见 [persistence.md](./persistence.md)；联动见 [linkage.md](./linkage.md)。

---

## 组件关系

```
procedure_table_templates.json
        │
        ▼
  GtAProgramConsole ──chip──┬──► INLINE_POPUP ──► WpPopupDocxEditor
                            │         │
                            │         └── prefilled-download (PRE-1)
                            ├──► navigate ──► htmlRendererRegistry
                            │                      ├─ checklist-table (PRE-4)
                            │                      ├─ a17-summary / regulatory-letter
                            │                      ├─ misstatement-workpaper / a14-3-workbook
                            │                      └─ word-template (A16)
                            └──► 灰显 (applicable=false)

checklist_responses ◄── GtChecklistTable / GtA17Summary / GtRegulatoryLetter / d-form
field_overrides     ◄── WorkpaperWordEditor (A16 only)

export-word (PRE-2) ◄── a17_word_exporter / regulatory_letter_service / (optional A8 export)
```

---

## docx 弹窗全量清单（19 个）

配置源：`wpPopupDocxConfigs.ts` + `INLINE_POPUP_WP_CODES` + 程序表 `ref_index`（PRE-3）。

| wp_code | Spec | chip 来源 | PRE-1 smoke |
|---------|------|-----------|-------------|
| A8-1 | A7–A15 | A8 seq2 | ✅ 套件 |
| A8-2 | A7–A15 | A8 seq3 | |
| A9-1 | A7–A15 | A9 seq2 | ✅ 套件 |
| A9-2 | A7–A15 | A9 seq4 | |
| A10-1 | A7–A15 | A10 seq7 | |
| A11-1 | A7–A15 | A11 seq1 | |
| A12-1 | A7–A15 | A12 seq1 | |
| A16-1~6 | A16 | A16 seq2 | A16-1 入套件 |
| A16-7 | A16 | A16 seq3 | |
| A17-3 | A17 | 程序表 | ✅ 套件 |
| A17-3-1 | A17 | 程序表 | |
| A17-4 | A17 | 程序表 | |
| A17-6 | A17 | 程序表 | |
| A18-1 | A18 | A18 程序表 | ✅ 套件 |

**不走弹窗**：A16 索引 A16 / seq4 → `word-template` 跳转页。

**大 docx export（plus，optional）**：A8-2、A10-1 等仍优先 OnlyOffice 交付；若做 export-word，须走 PRE-2 filler，**不做** structured HTML 中间层。

---

## PRE-3 ref_index 审计清单

程序表 `ref_index` 待补/待验（实现时勾选）：

| 程序表 | 待办 | 负责 spec |
|--------|------|-----------|
| A9 | seq2/4 → A9-1/2；seq1 → A14 | A7–A15 lite |
| A10 | seq6/7/4.8 → A10-2/1 | A7–A15 lite |
| A11 | seq1/2 → A11-1/A11-2 | A7–A15 lite |
| A12 | seq1 → A12-1 | A7–A15 lite |
| A16 | seq2 全量 A16-1~6；seq3 A16-7；seq4 A16 | A16 lite |
| A17 | 步骤扩充 + → A17-3/4/6/5-x | A17 lite |
| A18 | **新建** JSON + → A18-1/2 | A18 P0 |

验证：chip 点击行为与 `INLINE_POPUP_WP_CODES` 一致；不适用步骤灰显。

---

## audit-xlsx 产出物索引

| 产出 JSON | 范围 | 状态 | 脚本 |
|-----------|------|------|------|
| `a7_a15_xlsx_audit.json` | A7–A15（26 文件） | ✅（⚠️ A7/A8 `procedure_table_diff` 为程序表扩充前旧快照，须 `--diff-only` 重跑） | `audit_a7_a15_xlsx.py` |
| `a17_xlsx_audit.json` | A17 程序表 + A17-5-1~5（6 xlsx） | ❌ 待 X-A17 | 待建或扩展现有脚本 |
| docx 占位 | A16-1/2 等 | 部分 | `docx_placeholder_registry.json` |

CI（INFRA-3）：`audit_a7_a15_xlsx.py --diff-only`（顺带重验 A7/A8）；A17 audit 就绪后纳入同门禁。✅ CI job `audit-xlsx-drift` 已建（`continue-on-error` 建议观察期后转 hard fail）。

---

## 摘要 API 响应占位（plus）

`GET /api/projects/{pid}/workpaper-summaries/{key}`

```json
{
  "ready": true,
  "key": "misstatement",
  "source_wp": ["A13-1", "A13-4"],
  "summary": { "uncorrected_count": 0, "items": [] }
}
```

`ready: false` 时：`{ "ready": false, "reason": "A13 Tab 未落地" }` → 前端 toast，HTTP 200（**实施决策：统一用 200，非 409**）。

key 列表见 [linkage.md §摘要 API](./linkage.md#摘要-api-契约plus待实现)。

---

## 前端消费约定（INFRA-1 / INFRA-2）

### issue-hints

- A17-1 ch15 编辑页 `onMounted` 拉取 `GET /api/projects/{pid}/issue-hints`
- A18-2 议题 1/2 初始化时同样拉取
- `count > 0` 时显示 `GtGuidanceBanner`（amber 色 + "仅供提示，召回不完备"措辞）
- **不自动写入正文**；用户点"引用"按钮才追加到对应章节/议题 remark
- `heuristic_only=true` 时 banner 必须含"仅关键词匹配"提示

### workpaper-summaries

- 消费方 `onMounted` 拉取 `GET /api/projects/{pid}/workpaper-summaries/{key}`
- `ready=false` → `ElMessage.info(reason)` 一次性 toast，不阻断编辑
- `ready=true` → 按 `summary` 结构渲染（各 key 的 summary schema 待各 spec 定义）
- 前端缓存策略：session 级缓存（同一编辑会话不重复拉取，保存/刷新后清缓存重拉）
