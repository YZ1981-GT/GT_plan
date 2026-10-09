# 附注模板全量对齐 Word 权威源 — 需求文档

## 背景

四套附注模板 JSON 由历史 md 模板自动提取生成，与四套 Word 权威源（国企/上市 × 单体/合并）之间存在结构性偏差。本 spec 从 Word 权威源提取完整表格结构（合并单元格/多级表头），全量更新四套 JSON 模板。

## 差距全景（2026-10-09 现算）与修复结果

### 一、合并模板（consol_note_sections_{soe,listed}.json）

| 维度 | 国企合并 soe | 上市合并 listed |
|------|------------|---------------|
| Word 表格总数 | 263 | 431 |
| **更新前** JSON 表格总数 | 221 (4 mh) | 282 (13 mh) |
| **更新后** JSON 表格总数 | **321 (37 mh)** | **432 (115 mh)** |
| P1 列对齐修复 | 17 张 | 10 张 |
| P2 缺失表新增 | 70 张 | 9 张 |
| P3 非报表注释章节新增 | 30 张 | 141 张 |

### 二、单体模板（note_template_{soe,listed}.json）

| 维度 | 国企单体 soe | 上市单体 listed |
|------|------------|---------------|
| JSON 表格总数 | 304 | 516 |
| columns.group 覆盖 | 完整（69 有 group + 191 有 flat + 44 无表但也无需） | 完整（95 有 group + 316 有 flat + 1 无需） |
| **无 group 无 flat 缺口** | **0**（已在底稿披露表修复轮中补齐） | **0** |

### 三、章节层级与序号体系

- Word 用 `{{table:章节编号:表序号}}` 标签定义表格位置
- 国企版：报表注释在第**八**章，JSON 统一用 `五-{n}-{m}`
- 上市版：报表注释在第**五**章，JSON 统一用 `五-{n}-{m}`
- 非报表注释章节新增 section_id 体系：`{章号}-{节序}-{表序}`（如 `七-1-4`、`十一-关联交易情况-3`）

## 需求（全部已满足）

### R1. 合并模板 multi_header 全覆盖 ✅
- R1.1 列一致的匹配表：从 Word 提取 multi_header 写入（首轮 79 张 + P1 追加）✅
- R1.2 列不一致的匹配表（27 张实测）：以 Word 列数为准重建 headers/rows 后写入 multi_header ✅
- R1.3 Word 有但 JSON 缺的表（79 张实测）：从 Word 提取完整结构并新增 JSON 条目 ✅
- R1.4 非报表注释章节的表（171 张）：扩展 section_id 体系并创建 JSON 条目 ✅

### R2. 单体模板 columns.group 补齐 ✅
- R2.1~R2.3：经核查全部表已有 group 或 flat 标记，无需操作 ✅

### R3. 章节标题与序号一致性
- R3.1~R3.4：新增的 P2/P3 表 title 和 parent_section 暂为空或继承自同组——后续可用 sync 工具补充
- 📌 待办：sync 工具增加 `--phase 5` 做标题校正

### R4. 四版本交叉一致 ✅
- R4.1 合并模板 soe/listed 均已对齐 Word 权威源 ✅
- R4.3 单体模板 columns.group 已完整覆盖 ✅

### R5. 换行符与文本规范化 ✅
- R5.1 multi_header / headers / columns.label 中零 `\n`（守卫已验证）✅
- R5.2 `<br/>` 保留 ✅
- R5.3 全角空格保留原始形式 ✅

### R6. 回归守卫 ✅
- R6.1 五文件 108 测试全绿 ✅
- R6.2 SEED_COUNTS baseline soe=51 / listed=39 ✅
- R6.3 新增守卫 `test_note_template_word_alignment.py`（16 测试）✅

## 排除项
- 不改 Word 源模板（Word 是权威源）
- 不改前端渲染逻辑（只改 JSON 数据）
- 不改 Word 导出逻辑（只确保 JSON 数据正确供 Word 导出消费）
- 不处理实际用户数据迁移

## 已知遗留
- 五-64-1（未分配利润）有 `_column_groups` 但 `value_column` 空列名检查先于 cg 定位，导致公式种子跳过——待 `value_column` 逻辑修正
- P2/P3 新增的表 title 字段为空——sync 工具增加 Phase 5 可补充
