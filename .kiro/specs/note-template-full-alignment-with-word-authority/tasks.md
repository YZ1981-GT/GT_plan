# 附注模板全量对齐 Word 权威源 — 任务清单

## Phase 0: 工具基础（前置）

- [x] 1. 编写 `sync_note_templates_from_word.py` 核心框架：Word 解析 + 合并单元格提取 + tag 解析 + 四文件匹配管线，放 `backend/scripts/seed/`（长期可重跑）
- [x] 2. 编写辅助函数：multi_header 标准化（去换行/strip）、列数对齐（expand/shrink headers+rows）、columns.group 反推

## Phase 1: 合并模板——列不一致修复（实测 soe 17 + listed 10 = 27 张）

- [x] 3. 国企合并 soe：17 张列不一致表，以 Word 列数为准重建 headers/rows 并写入 multi_header
- [x] 4. 上市合并 listed：10 张列不一致表同上处理
- [x] 5. 回归测试：test_consol_note_column_groups + test_consol_note_formulas 全绿，SEED_COUNTS soe 51 / listed 39

## Phase 2: 合并模板——缺失表新增（实测 soe 70 + listed 9 = 79 张）

- [x] 6. 国企合并 soe：70 张 Word 有但 JSON 缺的表——从 Word 提取完整结构并新增
- [x] 7. 上市合并 listed：9 张同上处理
- [x] 8. 回归测试通过

## Phase 3: 合并模板——非报表注释章节（soe 30 + listed 141 = 171 张）

- [x] 9. 设计 section_id 体系：`{章号}-{节序}-{表序}`（如 `七-1-4`、`十一-关联交易情况-3`）
- [x] 10. 国企合并 soe：30 张（四/五/六/七/九/十一/十二）
- [x] 11. 上市合并 listed：141 张（三/四/六/七/八/九/十/十一/十二/十三/十四/十五/十六/十七）
- [x] 12. 回归测试通过

## Phase 4: 单体模板——columns.group 补齐

- [x] 13. 经核查不需要操作：soe/listed 所有表已有 group 或 flat（缺口=0），之前底稿披露表修复轮已补齐

## Phase 5-6: 收尾守卫

- [x] 14. 新增守卫 `test_note_template_word_alignment.py`（16 个测试）：
  - multi_header 表的 _column_groups 一致性
  - 无 multi_header 的表无孤立 _column_groups
  - multi_header 无换行符
  - multi_header 行列数 == headers 列数
  - 合并模板覆盖率基线（soe ≥321 表 / listed ≥432 表；mh soe ≥37 / listed ≥115）
  - 单体模板全表有 group 或 flat
  - 单体模板 columns.label/group 无换行符
- [x] 15. 全套 5 文件 108 测试最终确认全绿
- [x] 16. 一次性探针已清理，只保留 `sync_note_templates_from_word.py` 长期工具

## 最终交付统计

| 模板 | 更新前 | 更新后 | 增量 |
|------|--------|--------|------|
| consol_note_sections_soe.json | 221 表 (4 mh) | 321 表 (37 mh) | +100 表, +33 mh |
| consol_note_sections_listed.json | 282 表 (13 mh) | 432 表 (115 mh) | +150 表, +102 mh |
| note_template_soe.json | 不变（304 表, 69 group） | — | P4 不需要 |
| note_template_listed.json | 不变（516 表, 95 group） | — | P4 不需要 |

已知例外：五-64-1（未分配利润）有 _column_groups 但 value_column 空列名检查先于 cg 导致跳过，待 value_column 逻辑修正。
