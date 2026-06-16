# Bugfix Requirements Document

## Introduction

A1-15（企业会计准则有关财务报表列报及披露核对表）底稿在底稿编辑器中仅显示 18 个粗粒度程序步骤，而非 Word 模板中的完整核对条目。用户反映"之前都是可以的"。

**实证数据**（python-docx 解析确认）：
- A1-15: 3 个 Word 表格。表1=封面(25行)、表2=目录(49行/35章节)、表3=核对表主体(934行×3列)
  - 逻辑列：准则索引号 | 核对条目正文 | 适用(Y)/不适用(N)
  - 35 个章节（1.1~5.0），363 个小节标题行 + 570 个数据行
- A1-16: 1 个 Word 表格(653行×14物理列→3逻辑列，大量合并单元格)
  - 逻辑列：法规索引 | 核对条目正文 | 适用标记（最后一列）

**根因**：A1-15/A1-16 的 wp_code 未在 `_WP_CODE_OVERRIDE` 注册，落入 class_code "A-程序表" 前缀匹配 → `a-program-console`。该组件数据来源是 `procedure_table_templates.json`（18 个程序步骤），完全无法展示 docx 内的核对表格内容。

**影响范围**：A1-15、A1-16 两份 docx 格式核对表底稿。用户无法看到和操作核对表的具体条目，必须另开 Word 文件手工核对。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN 用户打开 A1-15 底稿 THEN 系统仅显示 18 个程序步骤，而非 docx 中 934 行核对条目（35 章节，涵盖 CAS 全部列报和披露要求）

1.2 WHEN A1-15/A1-16 底稿被 render-config 处理 THEN `derive_component_type` 按 "A-程序表" 前缀匹配返回 `a-program-console`，docx 内容完全丢失

1.3 WHEN 用户需要逐项核对财务报表列报和披露要求 THEN 系统无法展示各准则对应的核对条目和适用性标记

### Expected Behavior (Correct)

2.1 WHEN 用户打开 A1-15/A1-16 底稿 THEN 系统 SHALL 完整渲染 docx 核对表内容：
- A1-15: 目录(35章节可折叠) + 核对表主体(934行，按章节分组)
- A1-16: 核对表(653行，按章节分组)
- 每行显示：准则/法规索引 | 核对条目正文 | 适用性标记(Y/N/NA)

2.2 WHEN 用户在核对表条目中操作 THEN 系统 SHALL 支持：
- 填写适用性标记（是Y / 否N / 不适用NA）
- 填写备注说明（原模板无此列，平台新增）
- 填写底稿索引引用（原模板无此列，平台新增）

2.3 WHEN 核对表内容量大(934行) THEN 系统 SHALL 提供：
- 章节目录导航（快速跳转到 35 个章节中任意一个）
- 章节折叠/展开
- 进度统计（已填/总数/完成率，按章节和总体）

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 用户打开 xlsx 格式的 A 循环底稿（A1~A14 等） THEN 系统 SHALL CONTINUE TO 按现有 a-program-console 组件正常渲染

3.2 WHEN 其他循环底稿使用 render-config THEN 路由不受影响

3.3 WHEN procedure_table_templates.json 中的程序表数据 THEN 自动汇总值（AJE/RJE 笔数）正常展示

3.4 WHEN 用户对 A1-15 执行下载/导出 THEN 原始 docx 模板文件仍可获取
