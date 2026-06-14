# 附注多表格 per-table 提示文字治理

## 背景与现状实证（2026-06-13 codegraph + DB 核查）

### 模板层（note_template_soe.json）
- `content_type: "mixed"` 章节：**117 个**
- 多表格（`tables.length > 1`）：**53 个**
- `text_sections` 含 `###`/`####` 标题行：**38 个**

### 后端生成逻辑现状（已实现，非待做）
`disclosure_engine.py` 已有成熟的三分类：
- `is_guidance_paragraph(para)` → 提示类（`（...）`/`【...】` 包裹且含指引关键词）→ 写入章节级 `guidance_text`
- `_is_table_title_paragraph(para)` → 标题行（`#` 开头 或 `（N）` 编号 或 ≤20字）→ `continue` **跳过，不进 text_content**
- 其余 → substantive 正文 → 写入 `text_content`
- `_infer_table_names_from_text()` 已把 text_sections 标题按序号/顺序回填到 `_tables[n].name`

**结论：新生成的附注，标题行已不进入 text_content（原 R2 已天然成立）。** 截图所见"标题行出现在富文本中"是**旧存量数据**。

### DB 存量实证（生产/dev 库真实数据）
| 指标 | 数量 |
|------|------|
| `content_type='mixed'` 总数 | 742 |
| `text_content` 仍含 `###` 标题行（旧数据） | **174** |
| `table_data` 已有 `guidance` key | **0** |
| 章节级 `guidance_text` 非空 | 141 |

### Word 导出现状实证
`note_word_exporter.py` **完全不渲染 `guidance_text`**（grep `guidance` 零命中）。
→ per-table guidance 进 Word 是**新增功能**，非修改。

## 真正的缺口

唯一未解决的核心问题：**guidance 全部塞进章节级 `guidance_text` 单一字符串**，`classify_template_content` 把所有 guidance 段落 `\n\n` join，丢失了"哪段提示属于哪个表格"的归属信息。导致多表 Tab 切换时提示条不跟随切换。

## 需求（收窄后）

### R1: 表格级 guidance 字段（核心）
- 增强 `classify_template_content`：返回 `per_table_guidance: dict[int, str]`（table_idx → 该表的提示文字）
- 分配算法复用现有 `is_guidance_paragraph` / `_is_table_title_paragraph` 检测，**用标题行作为游标推进** table_idx
- 生成附注时把 `per_table_guidance` 写入 `_tables[n].guidance`
- 章节级 `guidance_text` 保留（作为无 per-table 归属时的通用提示 / 降级）

### R2: 单表章节零回归（边界铁律）
- 117 mixed 中有 64 个是单表 + 742 DB mixed 中大量单表
- 单表章节（`_tables.length <= 1`）：guidance 仍走章节级 `guidance_text`，行为完全不变
- per-table guidance 仅对多表章节生效

### R3: 前端按 Tab 切换显示
- `activeTableGuidance` computed：`_tables[activeIdx].guidance` 优先，降级章节级 `guidance_text`
- guidance bar 显示内容、`v-if` 判定、关闭按钮均按 `activeTableGuidance`
- `dismissGuidance` 改为 `section:tabIdx` 粒度（各 Tab 独立关闭记忆）

### R4: 存量数据迁移（174 条 ###，必做非可选）
- 174 条 `text_content` 残留 `###` 标题行需清理
- 迁移脚本：识别标题行 → 移除；紧跟标题行的提示段 → 移入对应 `_tables[idx].guidance`
- dry-run 优先 + 按项目执行 + 备份原 text_content

### R5: Word 导出 per-table guidance（新增）
- `note_word_exporter` 各表格渲染前输出该表 `_tables[n].guidance`（作为提示性段落，可加灰色/小字样式区分正文）
- 章节级 `guidance_text` 也应输出（此前完全没输出，是既有缺陷，顺带补）
- 注意：guidance 是"指引性文字"，导出到正式交付件时是否应保留需确认（参考 `note-guidance-text-separation` spec 中"提示语不进交付件"的讨论）

## 模板数据结构实证

### 货币资金（八、1）— 最小典型（2 表）
```
tables: [货币资金, 受限制的货币资金明细]
text_sections: [
  "（注：如有因抵押...）",          → 提示，归 tables[0]（标题行前）
  "（提示：企业持有...）",          → 提示，归 tables[0]
  "### 受限制的货币资金明细"        → 标题行，游标推进到 tables[1]
]
预期: _tables[0].guidance = "（注：...）\n（提示：...）"
      _tables[1].guidance = null
```

### 应收账款（八、5）— 多表复杂（11 表 7 text_sections）
```
text_sections 全是标题行（（1）~（6）+ #### 期末单项...）
无实质 guidance/正文 → 各表 guidance 均为 null，仅用于 name 回填
```

### 分配游标规则
- 遍历 text_sections，维护 `current_idx`（初始 0）
- 遇标题行 → 解析对应 table_idx，`current_idx = 该 idx`（标题行本身丢弃）
- 遇 guidance → append 到 `per_table_guidance[current_idx]`
- 遇正文 → 仍归章节级 text_content（多表场景正文罕见，保持简单）

## 影响面

| 组件 | 改动类型 |
|------|---------|
| `disclosure_engine.classify_template_content` | 增强返回 per_table_guidance |
| `disclosure_engine` 生成流程 | 写 `_tables[n].guidance` |
| `DisclosureEditor.vue` | activeTableGuidance computed + dismiss 粒度 |
| `note_word_exporter.py` | 新增 guidance 段落渲染（此前零渲染） |
| 迁移脚本 | 174 条存量清理 |
| `note_offline_export_service.py` | 离线导出带 guidance（可选） |

## 不做

- 不加 DB 列（guidance 存 `table_data` JSON 内）
- 不动单表章节逻辑
- 不重写已成熟的标题/guidance 检测函数（复用）
