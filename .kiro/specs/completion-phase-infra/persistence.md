# 持久化与 wp_code 契约（A7–A18 共用）

> 各 spec 的 item_id / scope 须与本文件一致；局部 spec 不得另定冲突命名。

---

## 存储决策树

```
底稿打开
  ├─ 程序表步骤状态 ──────────→ procedure_table（已有）
  ├─ docx 弹窗（19 个）lite ──→ OnlyOffice 文件 / prefilled-download（无 checklist_responses）
  │     plus 可选 ───────────→ export-word check-incomplete 或文件已保存
  ├─ A16 跳转页 ─────────────→ field_overrides（sign_status / selected_version）
  ├─ checklist-table ────────→ checklist_responses
  ├─ structured HTML ────────→ checklist_responses（A17-1 / A18-2 / KAM）
  └─ d-form-table ───────────→ checklist_responses（item_id 带 section/row 前缀）
```

| 模式 | 表 / 字段 | 完成态（见 requirements §checkCompletion） |
|------|-----------|------------------------------------------|
| A16 主/补声明 | `field_overrides` | `word_template:A16:{version}` sign_status=signed |
| checklist / 问卷 | `checklist_responses` | 必填 conclusion 已填 |
| A17-1 章节 | `checklist_responses` | conclusion=done |
| A17-2-1 KAM | `checklist_responses` | remark JSON 必填字段完整 |
| A18-2 议题 | `checklist_responses` | 适用议题 conclusion=Y 且 remark 非空 |
| d-form 行 | `checklist_responses` | 按 section 必填规则 |

---

## wp_code 别名与虚拟码

| 用户可见码 | 实际路由 | 说明 |
|------------|----------|------|
| A16-1~A16-6 | `A16?version=A16-x` | 虚拟子码；**不**建独立 WorkingPaper |
| A16-7 | 弹窗或 `A16` 补充区 | 与主版本签回 **分离** |
| A11-1（程序表 chip） | INLINE_POPUP → docx 问询函 | |
| A11-1（底稿目录 F 列） | `A11` + `{ sheet: 'A11-WP-1' }` | xlsx 审定表；**非** docx |
| A11-2 / A11-3 | `A11` + sheet 或独立 checklist | |
| A13（Tab） | `A13` + `{ tab: 'A13-2' }` 等 | 单文件 8 sheet |
| A14-3 | `a14-3-workbook` 多 Tab | 非单一 wp_code 打开 |
| A15 guidance | `A15` + `{ sheet: 'guidance' }` | 只读，不持久化 |

解析优先级：独立物理文件 wp_code → bundle sheet alias → 程序表 chip ref_index。

---

## item_id 注册表

### checklist-table（固定问卷）

| wp_code | item_id 模式 | conclusion | remark |
|---------|--------------|------------|--------|
| A11-2 | `A11-2-01` … `A11-2-13` | yes/no/na | 简要说明 |
| A11-3 | `A11-3-01` … `A11-3-10` | yes/no/na | 简要说明 |
| A15-1 财务 | `A15-1-fin-01` … `A15-1-fin-11` | yes/no/na | 说明 |
| A15-1 经营 | `A15-1-ops-01` … `A15-1-ops-06` | yes/no/na | 说明 |
| A15-1 其他 | `A15-1-oth-01` … `A15-1-oth-04` | yes/no/na | 说明 |
| A15-1 结论 | `A15-1-conclusion` | — | 调查结论文本 |
| A17-5-x | `A17-5-{x}-{seq}`（实现时与 parser section 对齐） | 按模板列 | 按模板列 |

### checklist-table（动态行）

| wp_code | item_id 模式 | 定案 |
|---------|--------------|------|
| A14-1 | `A14-1-row-001` … 自增 | 认定 6 列矩阵 → **remark JSON**（固定 schema）；不拆列 item_id |

A14-1 remark JSON（P1 schema，前后端校验）：

```json
{
  "defect_no": "string",
  "process": "string",
  "description": "string",
  "assertions": { "existence": "Y|N|NA", "..." : "..." },
  "compensating_control": "string"
}
```

### structured HTML

| wp_code | item_id | remark |
|---------|---------|--------|
| A17-1 | `A17-1-ch01` … `A17-1-ch11` | 章节正文；conclusion=done/pending/na |
| A17-2-1 KAM | `A17-2-1-KAM-001` … | remark=KAM JSON（见 A17 design） |
| A18-2 议题 | `A18-2-001` … `A18-2-004` | 议题描述 |
| A18-2 表头 | `A18-2-header` | JSON：regulator、sub_choice_3 等 |

### d-form（section 前缀）

| wp_code | item_id 模式 | 示例 |
|---------|--------------|------|
| A13-2~5 | `A13-2-row-{nn}` / `A13-3-{section}-{nn}` | 按 audit 列映射 |
| A14-2~5 | `A14-2-step1-{field}` 等 | 按 Step 节 |
| A10-2 | `A10-2-t1-row-{nn}` / `A10-2-t2-row-{nn}` | 模板1/2 |
| A11-WP-1 | `A11-WP-1-row-{nn}` | 审定表动态行 |

### field_overrides（仅 A16）

| scope | field | 值 |
|-------|-------|-----|
| `word_template:A16` | `selected_version` | A16-1~6 |
| `word_template:A16:{version}` | `sign_status` | pending/sent/signed |
| `word_template:A16:A16-7` | `sign_status` / `enabled` | 补充声明独立 |

---

## 结构化函件最小共享（A17-1 / A18-2）

| 共享项 | 位置（规划） | 说明 |
|--------|--------------|------|
| 提示栏 CSS 令牌 | `GtStructuredSection` 或 shared styles | 折叠；**不导出** |
| debounce 保存 | composable `useChecklistDebounceSave` | 2s → PUT checklist_responses |
| export-word | PRE-2 + 各 spec 编排服务 | 颜色语义只在 filler |

不强制共用一个 Vue 页面组件；**契约**（item_id、export、提示栏行为）必须一致。
