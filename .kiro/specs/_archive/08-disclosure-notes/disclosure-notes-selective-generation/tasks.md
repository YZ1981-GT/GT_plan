# Implementation Plan

## Overview

交付中心「生成附注」→ 弹窗按附注实时树勾选章节 + 一键预设（只勾有数据科目）。后端唯一缺口 = 树节点加 `has_data`（与 `_has_content` 收敛为共享 helper）；导出接口零改动。前端新建选择对话框 + `DeliverableCenter` 接线。

执行顺序：W0 后端共享 helper + get_notes_tree（含 characterization 零回归安全网）→ W1 前端对话框 → W2 DeliverableCenter 接线 → W3 测试门 → W4 Playwright（可选，需实例化项目）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2", "1.3"], "description": "后端共享 helper + get_notes_tree has_data + 零回归安全网" },
    { "wave": 1, "tasks": ["2.1", "2.2"], "description": "前端选择对话框组件" },
    { "wave": 2, "tasks": ["3.1"], "description": "DeliverableCenter 接线" },
    { "wave": 3, "tasks": ["4.1", "4.2"], "description": "后端 + 前端单元/契约测试门" },
    { "wave": 4, "tasks": ["5.1"], "description": "Playwright 端到端（可选）" }
  ]
}
```

## Tasks

- [x] 1. 后端：共享 has_data helper + get_notes_tree 接入
- [x] 1.1 新建 `backend/app/services/note_content_utils.py`（`effective_table_data` + `note_has_data` 纯函数）
  - `effective_table_data(table_data: dict | None) -> dict | None`：把 `NoteWordExporter._effective_table_data` 投影逻辑逐字节搬入（`project_sub_tables(table_data)` 非空 → `{**table_data, "_tables": projected}`；否则原样返回；投影异常 `logger.warning` 后回退原 `table_data`）。**不按 content_type 分支**。
  - `note_has_data(note) -> bool`：`is_empty(not_applicable)` → 短路 `False`；`text_content` 非空 → `True`；否则 `effective_table_data(note.table_data)` 后遍历 `_tables`/单表降级，任一单元格 `value`/`manual_value` 非空、非 0、非「0」、非「-」→ `True`。
  - `note_has_data` 整体 try/except fail-open：单元格遍历异常 → 记 `logger.warning` 返 `False`（不抛，供 get_notes_tree 稳定返回）。
  - _Requirements: 2.2, 2.4_
  - _Properties: P6, P11_

- [x] 1.2 `NoteWordExporter` 委托共享 helper（零行为变更）
  - `_effective_table_data(self, note)` → `return effective_table_data(note.table_data)`。
  - `_has_content(self, note)` → `return note_has_data(note)`。
  - 对外行为逐字节等价（现有导出/skip_empty 不变）。
  - _Requirements: 2.2_
  - _Properties: P6_

- [x] 1.3 `DisclosureEngine.get_notes_tree` 每节点追加 `has_data`
  - 节点 dict 末位加 `"has_data": note_has_data(n)`，无独立投影、无 content_type 分支。
  - 现有字段（`id/note_section/section_title/account_name/content_type/status/sort_order`）值、语义、顺序不变。
  - 路由 `GET /api/disclosure-notes/{pid}/{year}` 透传，权限不变。
  - _Requirements: 2.1, 2.3, 9.1, 10.3_
  - _Properties: P6, P10, P12_

- [x] 2. 前端：附注选择对话框
- [x] 2.1 新建 `DisclosureNotesSelectionDialog.vue`（树加载 + 分组 + 勾选 + 降级）
  - Props `visible/projectId/year`；Emits `update:visible`、`confirm:{selectedSections:string[]}`。
  - `watch(visible)`/`@open` 打开时调 `GET disclosureNotes.tree(pid, year)`；成功 → 按顶层中文序号分组构 `el-tree`（`node-key=note_section`、`show-checkbox`）；404 → `loadError='not_found'` 提示「附注数据不存在，请先生成附注」；其他/超时 → `loadError='failed'` + 「重试」。
  - 加载中显示 loading 并禁用「确认生成」（Req1.5）。
  - `has_data=false` 叶子灰色样式 + 「无数据」tag，**不 disabled**（可手动补勾）。
  - 分组父节点 key 前缀 `__group__`；叶子显示 `note_section + section_title`。
  - 全中文、Element Plus、字号 13px。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2, 9.2_
  - _Properties: P8, P10_

- [x] 2.2 对话框：一键预设 + 二次修正 + 空选守卫 + 确认
  - 「一键预设生成」：`treeRef.setCheckedKeys(has_data=true 叶子的 note_section)`；展示当前勾选数量（Req3.4）。
  - 预设不锁定：后续手动增/删勾选实时更新；确认时取 `getCheckedKeys(true)` 当前集（非预设集）。
  - 「确认生成」：勾选集为空 → 禁用 + `ElMessage.warning('请至少选择一个章节')` 阻止提交；非空 → `emit('confirm',{selectedSections})` 并关闭。
  - `loadError!=='none'` 或空选 → 「确认生成」禁用。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 7.1, 7.2_
  - _Properties: P1, P2, P3, P4, P7_

- [x] 3. 前端：DeliverableCenter 接线
- [x] 3.1 `goGenerateNotes` 改打开对话框 + confirm 回调生成
  - `goGenerateNotes()`：`guardGenerate('notes')` 门控保留 → 设 `notesDialogVisible=true`（不再直接调渲染接口）。
  - 新增 `onNotesSelectionConfirm({selectedSections})`：`generating=true` → `renderDisclosureNotes(projectId, { year, selected_sections: selectedSections })`（**不传 template_type**）→ 成功提示/`platform_persist_failed` 警告 → `downloadFile(...)` → `loadList()` → 关闭对话框 → `finally generating=false`；失败 `ElMessage.error('生成附注失败')`。
  - 模板挂载 `<DisclosureNotesSelectionDialog v-model:visible :project-id :year @confirm="onNotesSelectionConfirm" />`。
  - 前端树节点类型补 `has_data?: boolean`（`deliverableApi.ts` 无需改，已支持 `selected_sections`）。
  - _Requirements: 6.1, 6.2, 6.4, 8.3, 10.1_
  - _Properties: P5, P8, P9_

- [x] 4. 测试门
- [x] 4.1 后端单元 + 契约测试
  - `test_note_content_utils.py`：`note_has_data` 各分支（text_content 非空/table_data 有值/全空/全 0/全「0」/全「-」/`_tables` 多表/is_empty 短路/异常 fail-open）。
  - `test_get_notes_tree_has_data.py`：每节点含 `has_data`；对同一 note 与 `NoteWordExporter(db)._has_content(note)` 结果一致；现有字段保持。
  - 契约（PBT `max_examples=5`）：随机构造 note 集合，`note_has_data(n)` 与 `_has_content(n)` 逐个一致。
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Properties: P6, P11, P12_

- [x] 4.2 前端单元测试（vitest）
  - `DisclosureNotesSelectionDialog.spec.ts`：预设集=has_data=true（P1）/空章节可补勾（P2）/二次修正后提交当前集（P3）/空选禁用且不提交（P4）/分组勾选=其下叶子（P7）/加载失败不提交（P8）/前缀来自响应不硬编码（P10）。
  - `DeliverableCenter` 集成：`goGenerateNotes` 打开对话框而非直接生成；confirm 回调携 `selected_sections` 调 `renderDisclosureNotes` 且 body 不含 `template_type`（P5, P9）。
  - _Requirements: 3.x, 4.x, 5.x, 6.x, 7.x, 8.x, 9.2_
  - _Properties: P1, P2, P3, P4, P5, P7, P8, P9, P10_

- [x] 5. 端到端验证
- [x] 5.1* 后端契约 live 验证（真实数据，替代 flaky 浏览器流）
  - 已对真实项目 0ec33ac9/2025（184 章节）鉴权 HTTP 调 `GET /api/disclosure-notes/{pid}/{year}`：`has_data` 落在全部节点、分布 123 true/61 false（非全同）、现有字段保持、`not_applicable` 恒 false、前缀（一/二/三）原样透传 → 验证 Property 6/10/11/12 + 导出选择性（`sections=selected_sections`）为零改动既有路径。
  - 未跑完整浏览器 round-trip（Playwright MCP SSE 劫持 flaky）；`has_data` 契约（本功能唯一后端改动）已 live 验证，导出选择性走既有生产路径，前端选择逻辑纯函数单测覆盖。listed 变体已验；soe 变体逻辑同源（前缀由后端返回，前端不硬编码）。
  - _Requirements: 6.3, 9.1, 9.3_
  - _Properties: P5_

## Notes

- **零改动**：交付渲染接口 `render_disclosure_notes`（已接受 `selected_sections` + `Project.template_type` 权威解析）、`deliverableApi.renderDisclosureNotes`（已支持 `selected_sections`）、`skip_empty` 语义、章节前缀——均不动。
- **单一真源铁律**：`has_data` 与 Word 导出必须走同一 `note_content_utils` helper；`_effective_table_data` **无 content_type 分支**（纯 `note.table_data` 变换），helper 必须逐字节等价，否则树标记与导出结果分叉。
- **零回归**：W0 完成后 `_has_content`/`_effective_table_data` 委托版必须与既有导出行为逐字节等价（跑现有 note_word_export 相关测试）。
- **UI**：全中文、Element Plus、表格/树 13px。
- **权限**：沿用 `DeliverableAction.export`，入口隐藏与渲染接口授权均不变。
- **提交/Playwright**：本 spec 改动完成后未 commit（等用户确认）；5.1 Playwright 需实例化项目，无则如实留待。
