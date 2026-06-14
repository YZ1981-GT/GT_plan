# 任务清单：附注 per-table guidance（收窄版）

## Phase 0: 决策确认

- [x] 0.1 确认 guidance 是否进 Word 交付件（参考 `note-guidance-text-separation` 的"提示语不进交付件"裁定）→ 决定 Phase 4 是否做
  - **决策（2026-06-13）：进交付件**。Word 各表格前渲染 per-table guidance（区分样式），Phase 4（4.1/4.2）执行。

## Phase 1: 后端 classify_template_content 增强

- [x] 1.1 增强 `classify_template_content` 新增 `tables` 参数，返回三元组 `(substantive, section_guidance, per_table_guidance: dict[int,str])`，游标算法复用 `is_guidance_paragraph`/`_is_table_title_paragraph`
- [x] 1.2 实现 `_match_title_to_table_idx`（精确/编号/包含/游标兜底四级匹配）
- [x] 1.3 grep 所有 `classify_template_content` 调用点，适配三元组解构（旧二元组解构会崩）
- [x] 1.4 生成流程接入：`per_table_guidance` 写入 `built_tables[idx]["guidance"]`
- [x] 1.5 单表章节零回归：`len(tables)<=1` 时 per_table_guidance 为空，guidance 全归章节级
- [x] 1.6 单元测试：货币资金（2表，tables[0].guidance 含注+提示，tables[1] 无）+ 应收账款（11表，全标题无 guidance）+ 单表章节（走章节级）

## Phase 2: 前端显示适配

- [x] 2.1 新增 `activeTableGuidance` computed（per-table 优先，章节级 guidance_text 降级）
- [x] 2.2 guidance bar 两处模板（table + text/mixed 区域）显示内容改为 `activeTableGuidance`
- [x] 2.3 `dismissGuidance` + `showGuidance` 改为 `section:tabIdx` 粒度
- [x] 2.4 单表章节验证：行为不变（仍显示章节级 guidance）
- [x] 2.5 vitest：activeTableGuidance 降级逻辑 + dismiss 粒度

## Phase 3: 存量迁移（174 条）

- [x] 3.1 编写 `backend/scripts/fix/fix_note_per_table_guidance.py`，复用生产 `classify_template_content` 保证规则一致
- [x] 3.2 dry-run 模式：打印每章节变更计划（移除标题行 / 分配 guidance / 保留正文），不写库
- [x] 3.3 对辽宁卫生 + 和平药房 dry-run 验证输出合理
- [x] 3.4 savepoint 事务 + 备份原 text_content + 按 `--project-id` 执行实际迁移
- [x] 3.5 迁移后验证：DB 中目标章节 `_tables[n].guidance` 已写入 + text_content 不再含 `###`

## Phase 4: Word 导出 per-table guidance（依赖 0.1 决策）

- [x] 4.1* 若 0.1 决策"进交付件"：`note_word_exporter` 各表格前渲染 `_tables[n].guidance` + 章节级 guidance（此前零渲染）
- [x] 4.2* 验证 Word 导出格式正确（提示用区分样式，不与正文混淆）

## Phase 5: 端到端验证

- [x] 5.1 Playwright：货币资金切第二个 Tab，guidance bar 内容变化/消失
- [x] 5.2 Playwright：应收账款多 Tab 切换，各 Tab guidance 独立（全为空则均不显示）
- [x] 5.3 重新生成附注验证 per-table guidance 正确写入

## Phase 6: 离线导出（可选）

- [x] 6.1* `note_offline_export_service` 各 sheet 带 guidance 行
