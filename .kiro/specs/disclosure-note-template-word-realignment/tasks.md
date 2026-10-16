# 任务：附注模板按四版 Word 重新对齐

> 约束：每组 红测 → 修 → 变异 → 更新本文件 → 提交 → 中转工作树推送。真库写入先 dry-run 报数、再备份、再写。
> 种子只经脚本修改；并发会话也在改种子，运行前看 `git status`，对方有未提交改动时等其提交后重放。

## Phase 1 比对工具

- [ ] 1. `backend/scripts/check/check_note_template_word_tree.py`：Word 解析（章 / 节 / 小标题 / 表格归属）、种子解析（按 scope 派生口径）、章配对、节匹配、差异分类、`--json` / `--check`；自检用例用合成 docx 证明放错章 / 缺节 / 多节 / scope / 顺序 / 表头差异都能检出。
- [ ] 2. 首跑四个口径：差异计数与清单写入下方「比对基线」；每类抽 3 条打开 Word 核对；守卫 `test_note_template_word_tree_alignment.py` 以 `xfail(strict=True)` 入库。

## Phase 2 种子修复

- [ ] 3. 编号别名：种子 `legacy_section_numbers` + `normalize_section_code` 两个准则都查别名；守卫「别名不与现行编号相同」。
- [ ] 4. 修复器 `backend/scripts/seed/realign_note_templates_to_word.py`：章（章名、`scope_titles`、缺章、多章）。
- [ ] 5. 修复器：节（放错章改挂并换编号前缀、补 Word 有种子无的节、删提示语节、scope、章内顺序）。
- [ ] 6. 修复器：表格（表名、列、多级表头、行标签、表数），保留机器字段；与逐循环表格脚本冲突处逐条登记。
- [ ] 7. 运行期按口径取章名（`scope_titles`）：生成链、目录树、Word 导出。
- [ ] 8. 衍生数据重生成；`backend/scripts/migrate/rename_note_section_codes.py` 改数据文件与前端映射中的旧编号；各 `--check` 通过。
- [ ] 9. 既有守卫与测试更新（覆盖率下限、scope、章节类型索引、逐循环测试中的硬编码编号）；`WORD_TITLE_ALIASES` 改为「旧系统标题 → Word 标题」；Task 2 守卫去掉 xfail 转真绿。

## Phase 3 存量项目修复

- [ ] 10. `backend/scripts/fix/realign_project_notes.py` dry-run：改编号、树字段、补章、脱树旧行、关联表；7 个目标项目报数。
- [ ] 11. 表格结构量化（一致 / 表头文字 / 列增减 / 行增减 / 表数五类）+ 读时增强 `note_table_enrichment` 在新种子下的输出核对。
- [ ] 12. 表格结构写库：按新结构搬值，孤儿值保留在 `_realign_orphans` 并报告；断言非空值多重集合不变、正文哈希不变。
- [ ] 13. 备份 / 恢复（先实测恢复路径）；`note_section_instances.section_number` 列宽不足时加 V188 / R188。
- [ ] 14. 测试集团甲 / 乙先行 `--apply` → 再 dry-run 为空 → 浏览器；再安徽 / 医疗器械 / 华氏 / 宜宾 / 首汽。

## Phase 4 编辑留痕

- [ ] 15. 继承上年 / 上年 Word 导入：`note_advanced.py` 补鉴权与当前用户；修 `note.title`、`_extract_to_opening_balance`、年度写死；写入行盖章。
- [ ] 16. 集团基线下发、集团模板下发盖章；`_upsert_section` 的 `level` 写数字层级。
- [ ] 17. 三格式保存、离线导入（路由补 commit）、单元格模式切换（新对象赋值 + 校验行属本项目）、回收站恢复（`note_section`）、程序裁剪联动盖章。
- [ ] 18. 系统路径不清空编辑人：公式推送事件、公式运行时附注适配器、模板回流。
- [ ] 19. AST 守卫扩到全部写入方 + 每个写入方一条行为测试 + 变异。

## Phase 5 大模型只在手动单击时调用

- [ ] 20. 全仓核实附注域大模型调用点，分「自动 / 手动」写入本文件。
- [ ] 21. 生成附注删除 RAG 回退与通用大模型两级；无调用方的函数删除。
- [ ] 22. 校验 `LLM_REVIEW` 与公式引擎 `LLMReview` 自动路径跳过并给出「需手动 AI 检查」。
- [ ] 23. 前端自动拉取改按钮触发；生成确认框文案。
- [ ] 24. 守卫：生成全流程大模型计数桩 0 次、手动入口仍调到、AST；变异。

## Phase 6 和平药房重建

- [ ] 25. 备份；核验 `pg_indexes` 与外键；删除计划报数（dry-run）。
- [ ] 26. 物理删除 → 生成（不调大模型）→ 公式推送。
- [ ] 27. 验证：行数、章节树、无「五、N」旧行、抽查科目合计 = 试算表审定数、浏览器。

## Phase 7 收口

- [ ] 28. INDEX / memory 同步；提交推送；汇报。

## 比对基线

（Task 2 填写）
