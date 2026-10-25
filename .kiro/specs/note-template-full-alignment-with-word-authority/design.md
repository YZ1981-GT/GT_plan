# 附注模板全量对齐 Word 权威源 — 设计文档

## 架构概览

本工程**只改 JSON 数据文件**（2 个合并模板）和测试 baseline。核心工具是一个**幂等的 Python 同步脚本**，从 Word 提取 → 匹配 → 写入 JSON → 验证。脚本本身也是交付物（放 `backend/scripts/seed/`，长期可重跑）。

## 分阶段策略与实际执行结果

### Phase 1: 报表注释章节——列不一致修复（实测 soe 17 + listed 10 = 27 张）

Word 和 JSON 列数不同的表。优先**信任 Word**（权威源），以 Word 列数为准重建 JSON 的 headers / rows，然后写入 multi_header。

**处置策略**：`phase1_consol` 函数统一处理——列一致的直接写入 mh，列不一致的以 Word 列数为准替换 headers + 对齐 rows 列数。

**不变量**：id / section_id / parent_section / parent_seq / seq / standard / rows[*][0]（行标签列）。

### Phase 2: 缺失表新增（实测 soe 70 + listed 9 = 79 张）

Word 有 tag 但 JSON 无对应 section_id 的表。从 Word 完整提取 headers / multi_header / rows（含模板行）、继承同组 parent_section，生成新 UUID 条目。

### Phase 3: 非报表注释章节（soe 30 + listed 141 = 171 张）

合并模板中"五-"编号体系不覆盖的章节。section_id 体系：

- 数字节号：`{章号}-{节序}-{表序}`（如 `七-1-4`、`六-1-2`）
- 中文名节号：`{章号}-{名称简写}-{表序}`（如 `十一-关联交易情况-3`）

覆盖国企 7 个章节（四/五/六/七/九/十一/十二）和上市 14 个章节（三/四/六/七/八/九/十/十一/十二/十三/十四/十五/十六/十七）。

### Phase 4: 单体模板 columns.group 补齐

经核查**不需要操作**——全部表已有 group 或 flat 标记（之前底稿披露表修复轮已补齐）。

## 工具

`backend/scripts/seed/sync_note_templates_from_word.py`

```
用法：python sync_note_templates_from_word.py [--dry-run] [--phase 1|2|3|4|all] [--std soe|listed|all] [-v]
```

功能：读 4 个 Word → 匹配 → 按 phase 更新 2 个合并模板 JSON → 幂等写入。

## 幂等性

- 写入前比对新旧值，无变化不写
- indent=2, ensure_ascii=False，排序稳定（`sort_consol_json` 按 section_id 排序）
- UUID 保留不重生成
- 验证：连续两次执行，第二次 "0 更新 / 0 新增 / (无变化)"

## 守卫

`test_note_template_word_alignment.py`（16 测试）：
- multi_header ↔ _column_groups 一致性（有 mh 必有正确 cg / 无 mh 必无 cg）
- multi_header 无换行符
- multi_header 行列数 == headers 列数
- 覆盖率基线棘轮（soe ≥321 表/37 mh，listed ≥432 表/115 mh）
- 单体模板全表有 group 或 flat
- 单体模板 columns 无换行符
