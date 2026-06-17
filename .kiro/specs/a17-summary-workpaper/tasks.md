# Implementation Plan

## P0: 快速配置 + 组件骨架

- [ ] 1. A17-3/3-1/4/6 加入 WpPopupDocxEditor 弹窗配置（DOCX_CONFIGS + INLINE_POPUP_WP_CODES）
- [ ] 2. A17-7/7A 确认 `_WP_CODE_OVERRIDE` 映射到 `independence-signing`
- [ ] 3. A17-5-1~5-5 加入 `_WP_CODE_OVERRIDE` → `checklist-table` + xlsx→checklist 数据解析器
- [ ] 4. A17 程序表加 `applicable_categories: ["A"]` + 步骤扩充（从 xlsx 模板提取）
- [ ] 5. `backend/data/a17_chapter_definitions.json`（11 章节 id/标题/提示文字/数据来源/是否必填）
- [ ] 6. `GtA17Summary.vue` 组件骨架（左侧目录 + 右侧章节区：提示栏折叠+正文 textarea+工具按钮）
- [ ] 7. 章节数据保存（debounce → PUT checklist_responses, item_id A17-1-ch01~ch11）
- [ ] 8. htmlRendererRegistry 注册 `a17-summary` + `_WP_CODE_OVERRIDE` 加 A17-1

## P1: 章节取数 + KAM 组件 + 表格渲染

- [ ] 9. `a17_summary_service.py`：章节数据聚合（从项目信息/A15/A10/issue_tickets 等取数）
- [ ] 10. 各章节"从关联模块拉取"按钮（调 summary_service 填充该章节）
- [ ] 11. 章节内嵌表格渲染（el-table 只读展示从关联模块拉取的结构化数据）
- [ ] 12. 简单章节格式化输出（约定范围/独立性等不需 RAG 的章节，直接模板化生成）
- [ ] 13. `GtKamWorkpaper.vue` 组件（KAM 列表 + 3 要素编辑 + 引用底稿 + 提示栏）
- [ ] 14. htmlRendererRegistry 注册 `kam-workpaper` + `_WP_CODE_OVERRIDE` 加 A17-2-1
- [ ] 15. KAM 数据存储（checklist_responses, item_id KAM-001~NNN, remark=JSON）

## P2: LLM 辅助 + 独立性增强

- [ ] 16. `a17_llm_service.py`（章节生成 + KAM 描述生成）
- [ ] 17. Prompt 模板文件 `backend/data/wp_llm_prompts/a17/`（章节通用 + KAM 专用）
- [ ] 18. 知识库 RAG 检索（同行业 KAM 案例 + 概要范例）
- [ ] 19. 前端"AI 生成"按钮 + 生成结果预览弹窗（用户编辑后采纳）
- [ ] 20. A17-7 独立性增强：逐条确认弹窗（利益冲突/近亲属/证券等）+ B3 联动预警

## P3: Word 导出 + 审计报告联动

- [ ] 21. `docx_template_filler.py` 通用 Word 导出引擎（颜色语义+占位符替换+注释删除+未完成检测）
- [ ] 22. A17-1 Word 导出（章节组装，调用通用引擎）
- [ ] 23. A17-2-1 KAM Word 导出（动态 KAM 表格行 + 蓝色删除）
- [ ] 24. KAM → 审计报告正文"关键审计事项"段落单向同步（底稿为权威源→push 到报告）
- [ ] 25. 完整性检查：导出前检测未填章节/未完成 KAM → 弹窗警告

## P4: 集成验证

- [ ] 26. Playwright E2E（A17-1 章节编辑 + 拉取 + AI 生成 + 导出）
- [ ] 27. Playwright E2E（A17-2-1 KAM 新增 + 编辑 + 同步报告 + 导出）
