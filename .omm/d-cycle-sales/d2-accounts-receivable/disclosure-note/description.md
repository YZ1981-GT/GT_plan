# D2 披露表 ↔ 附注模块（嵌套元素）

D2 是"底稿披露表结构化推送到附注模块"的完整实现，其他科目照此范式铺开。

## 两个独立对象，别混

| | 底稿披露表 | 附注模块 |
|---|---|---|
| 位置 | `D2TabDisclosure` + `D2DisclosureNoteBody` | `DisclosureEditor.vue`（独立模块） |
| 存储 | `checklist_responses`（`D2-disc-{variant}-*`） | `disclosure_notes` 表（`table_data` / `text_content`） |
| 表头 | 支持多级表头 | **只渲染扁平单级表头** |

## 推送链（单向）

```
D2 披露表「同步到附注」
  → POST /api/wp-disclosure-sync/sync-from-workpaper
     body: { wp_id, sheet_name, section_id, current_standard, sub_table_data, columns, year }
  → sub_table_data 各子表键 ↔ columns 键必须同名（投影器按名匹配）
  → _note_texts（list of {section,title,text}）被服务端 pop 成 text_content
  → disclosure_notes.table_data + _sub_table_columns
  → GET note detail 时 note_sub_table_projector 投影成 _tables[] 供前端与 Word 导出渲染
```

## 章节与变体

- 上市 `五、5` / 国企 `八、5`（权威源 `note_template_variant_matrix.json`）
- **章节号判定必须精确 `===`**（`五、5` 用 `startsWith` 会串到 `五、50`+）
- **年度必须显式传 `year`**（不传则后端 fallback 到服务器自然年 → 跨年审计写错年度记录，附注模块按 `audit_year` 渲染就看不到）
- 变体权威源是 `projects.template_type`（不是 `applicable_standard_v2.entity_type`）

## 双向跳转

- 正向（附注 → 披露表）：`noteDisclosureJump.resolveNoteDisclosureJumpTarget` 按章节号精确谓词路由到 D2 披露 sheet；sheet 名必须是 `workpaper_sheet_classification` 里的**真实 tab 名**
- 反向（披露表 → 附注）：`noteDisclosureReverseJump.buildNoteJumpRoute` → `/projects/{pid}/disclosure-notes?section=五、5&noteTemplate=listed`
- 反向 map 的章节号与正向谓词由守卫测试 cross-check 防漂移

## 推送范围

11 张子表（账龄 / 分类期末+上年末 / 单项计提明细 / **每组合一张分表** / 变动 / 重要转回 / 核销金额 + 逐项 / 前五名 + 国企专有的其他组合方法、终止确认）+ 7 段说明文本。

组合分表按项目实际组合动态生成，**同名冲突用 `groupId` 后缀兜底**（早期实现 `continue` 会静默丢表）。
