# ADR-009: 致同 Word 导出 — `GTNote*` 样式命名空间隔离

**Status**: Accepted
**Date**: 2026-05-27
**Sprint**: disclosure-note-full-revamp / Sprint 2 Task 2.8

## 背景

附注 Word 导出（`backend/app/services/note_word_exporter.py`）需要严格匹配致同（GT）的 21 项排版规范：仿宋_GB2312 小四 12pt + Arial Narrow 数字 / 三线表 1pt 顶底 + 1/2pt 表头下 / 行高 0.7cm exact / 标题左缩进 -2 字符 / 段后 0.9 行 / 标题行不重复（无 `w:tblHeader`）等。

直接用 `python-docx` 默认生成的 docx 携带 Word 内置样式（Heading1 / Heading2 / Normal / TableGrid 等），存在 3 个问题：

1. **默认样式被污染** — Heading1 默认含粗体 + 较大字号 + 段前 24pt 等，与致同规范完全不同；强行覆盖会让用户复用 Word 模板时本地样式被改。
2. **多模板冲突** — 用户的本地致同模板可能也叫"标题 1"，加载到附注 docx 时会发生样式名重名。
3. **CI 视觉断言不稳定** — `test_note_export_visual.py` 的 11 项 OOXML 断言依赖样式名定位 `<w:style w:styleId="...">` 块；用 Word 内置名容易和其他模块（审计报告 / 底稿）的样式串台。

## 决策

附注 Word 导出**所有自定义样式**统一加 `GTNote` 前缀，与 Word 内置样式 + 其他模块样式完全隔离。

### 决策 1：`GTNote*` 样式清单（10 个）

| styleId | type | 用途 | 关键属性 |
|---------|------|------|---------|
| `GTNoteHeading1` | paragraph | 章节一级标题（"五、合并财务报表项目注释"） | bold + leftChars=-200 + 段后 216 twip |
| `GTNoteHeading2` | paragraph | 章节二级标题（"（一）货币资金"） | bold + leftChars=-100 + 段后 216 twip |
| `GTNoteHeading3` | paragraph | 章节三级标题（"1. 库存现金"） | bold + 段后 216 twip |
| `GTNoteBody` | paragraph | 正文段落 | firstLine=0 + 段后 216 twip + sz=24 |
| `GTNoteAfterTable` | paragraph | 表格后说明文字 | 段后 216 twip + 段前 120 twip |
| `GTNoteUnit` | paragraph | "金额单位：元"行 | right align + sz=22 |
| `GTNoteNumberRun` | character | 数字 run（双字体注入：仿宋_GB2312 + Arial Narrow） | rPr.rFonts.eastAsia + ascii |
| `GTNoteThreeLine` | table | 三线表样式 | 顶/底 sz=8 + 表头 cell.bottom sz=4 |
| `GTNoteFormulaCell` | cell-shading sidecar | D1 公式 cell 视觉提示 | shading fill #E6FFE6 |
| `GTNoteManualCell` | cell-border sidecar | D1 手工 cell 视觉提示 | 灰色边框 #808080 |

**生成入口**：`scripts/build_note_export_template.py --apply` 一次性生成 `backend/data/note_export_template.docx`，导出时 `_new_document` 优先加载该模板（缺失时降级 `Document()`）。

### 决策 2：API 命名遵循 GTNote 命名空间

`note_word_exporter.py` 暴露的 6 个 helper 函数全部以 `apply_gt_*` / `fmt_*_gt` 命名，对应 GTNote* 样式：

```
apply_gt_dual_font(run)        → GTNoteNumberRun（双字体 rPr 注入）
apply_gt_three_line(table)     → GTNoteThreeLine（三线表）
apply_gt_row_height(row)       → 0.7cm exact（无 w:tblHeader）
fill_multi_header(...)         → GTNoteThreeLine + 多层表头合并
fmt_amount_gt(val)             → 空值/零值留白 ""
add_landscape_section(doc)     → 章节级横向（next page）
```

### 决策 3：CI 卡点 — `GTNote*` 前缀必检

CI 测试 `test_note_export_visual.py::test_assert_11_gt_note_styles_count_at_least_7` 断言：

- `word/styles.xml` 中 `w:styleId="GTNote*"` 至少出现 ≥ 7 次（6 段落 + 1 字符；表格样式可选断言）。
- 缺失时构建失败，强制运行 `scripts/build_note_export_template.py --apply` 重生成。

`grep` 卡点：

- `note_word_exporter.py` 中所有 `_set_run_font` / `apply_*` 函数引用的 styleId 必须以 `GTNote` 开头。
- 模板文件 `backend/data/note_export_template.docx` 反编译后 `word/styles.xml` 不允许出现 `Heading1` / `Heading2` / `Heading3` / `Body Text` 等 Word 内置自定义样式（默认样式仍存在但不被使用）。

### 决策 4：与其他模块的隔离

| 模块 | 样式前缀 | 模板文件 |
|------|---------|---------|
| 附注 | `GTNote*` | `backend/data/note_export_template.docx` |
| 审计报告 | `GTReport*`（Phase 13 已落地） | `backend/data/audit_report_template.docx` |
| 底稿 docx 导出 | （沿用 Word 内置） | 无独立模板 |

三个模块的样式名完全不重合，方便在同一文档内嵌入（如审计报告引用附注片段）。

## 后果

### 正面

- **样式无污染**：用户拿到的 docx 即使在 Word 中"另存为模板"，自定义样式也只多 10 个 `GTNote*`，不动 Heading1 等内置样式，避免本地模板被覆盖。
- **CI 视觉断言稳定**：11 项 OOXML 断言全部可以按 `GTNote*` 精确定位样式块，跨版本 docx 解析鲁棒。
- **多文档拼接安全**：未来"打包导出（附注 + 报告 + 底稿）"场景，三套 GTxxx 命名空间可在同 docx 共存。
- **可复用性强**：将来 SOE / Listed 双版本附注样式微调，只需在 GTNote* 命名空间内分支（如 `GTNoteHeading1Listed`），不影响默认。

### 代价

- 用户在 Word 中按 Tab/快捷键应用样式时，需要选择 `GTNoteHeading1` 而不是熟悉的"标题 1"；需要短训练。
- `python-docx` 默认 `Document.add_heading()` 用的是内置 Heading1，附注导出代码必须显式 `paragraph.style = doc.styles["GTNoteHeading1"]`。
- 添加新样式需要同步更新：① 模板生成脚本 ② note_word_exporter helper ③ test_note_export_visual.py 断言清单 ④ 本 ADR 表格 — 4 个地方一致才合规。

### CI 卡点

- `test_note_export_visual.py::test_template_docx_exists`（模板必须存在）。
- `test_note_export_visual.py::test_assert_11_gt_note_styles_count_at_least_7`（≥ 7 个 GTNote* 样式）。
- `test_note_export_visual.py::test_assert_1_dual_font_applied_in_document`（Arial Narrow + 仿宋_GB2312 双字体注入）。
- 所有 11 项视觉断言必须全绿（详见 spec design D7 + Sprint 2 Task 2.6）。

## 关联

- **ADR-007**：附注三式联动单一真源（Word 是镜像，table_data 才是真源）。
- **ADR-008**：附注单元格三态模式持久化（`GTNoteFormulaCell` / `GTNoteManualCell` 是 D1 sidecar 的 Word 视觉表达）。
- **Spec**：`.kiro/specs/disclosure-note-full-revamp/` D7 致同 Word 排版规范单一真源 + R5.2 21 项验收。
- **代码**：
  - 模板生成：`scripts/build_note_export_template.py`（一次性，幂等可重跑）
  - 模板文件：`backend/data/note_export_template.docx`（生成产物，不进 git LFS — 体积 < 30KB 可直接 commit）
  - 导出引擎：`backend/app/services/note_word_exporter.py`（11 helper + Class）
  - 视觉测试：`backend/tests/services/test_note_export_visual.py`（11 项 OOXML 断言）

## 考虑过但未采用

### 直接覆盖 Word 内置 Heading1 / Heading2 等

**否决原因**：Word 内置样式被附注模块改了之后，用户在自己的本地 Word 中打开任何文档都会受到影响（Word 会全局应用 Normal.dotm 中的内置样式定义）。隔离命名空间是稳健做法。

### 用 `gt-note-*` 小写连字符命名

**否决原因**：OOXML `w:styleId` 历史习惯是 PascalCase（如 `Heading1`），保持一致性；连字符还会与 CSS 命名混淆。

### 不做模板 docx 文件，全部代码生成样式

**否决原因**：代码生成 ~30 行 OOXML 每样式 × 10 样式 = 300 行；模板 docx 把这部分声明性资产外置为单一文件，可视化预览（在 Word 中直接看效果）+ 一次生成多次复用，工程上更清晰。`scripts/build_note_export_template.py` 一次性生成且幂等，不需要 runtime 计算。
