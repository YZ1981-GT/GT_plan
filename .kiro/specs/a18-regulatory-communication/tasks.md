# Implementation Plan

## P0: A18-1 弹窗 + A18-2 结构化表单基础

- [ ] 1. A18-1 加入 WpPopupDocxEditor 配置（DOCX_CONFIGS + INLINE_POPUP_WP_CODES + WpInlinePopup）
- [ ] 2. A18 程序表加 `applicable_categories: ["A", "B"]`（procedure_table_templates.json）
- [ ] 3. `GtRegulatoryLetter.vue` 组件骨架（三段式布局：表头+议题区+签名区）
- [ ] 4. 4 议题卡片静态渲染（标题+说明文字+折叠）
- [ ] 5. 议题交互：适用性 Y/N toggle + 描述 textarea + 议题 3 三选一 radio
- [ ] 6. 自动保存（debounce 2s → PUT checklist_responses，item_id A18-2-001~004 + header）
- [ ] 7. htmlRendererRegistry 注册 `regulatory-letter` + `_WP_CODE_OVERRIDE` 加 A18-2
- [ ] 8. 表头自动填充（监管机构输入/下拉 + 公司名/年度/合伙人从项目信息自动取）

## P1: Word 导出 + 提示栏 + 颜色语义处理

- [ ] 9. 各议题提示栏（折叠面板，展示编制说明/准则引用，不导出）
- [ ] 10. `docx_template_filler.py` 通用 Word 导出引擎（与 A17 共享：颜色语义+占位符+注释删除+未完成检测）
- [ ] 11. 不适用议题整段删除（标题到下一标题之间）+ 蓝色占位符替换/删除 + 注释表格删除
- [ ] 12. "未完成项"检测端点 `GET /working-papers/{wp_id}/export-word/check-incomplete`
- [ ] 13. 前端导出按钮（`GET /working-papers/{wp_id}/export-word`）+ 未完成项弹窗警告
- [ ] 14. 自动联动取数：舞弊/违规从 issue_tickets + 信息不一致从 A8 状态

## P2: 增强 + 集成验证

- [ ] 15. A18-1 审计小结结构化生成（从 A17 重大事项+审计意见提取框架）
- [ ] 16. Playwright E2E（打开 A18-2 → 填写 4 议题 → 导出 → 验证 Word 内容正确）
