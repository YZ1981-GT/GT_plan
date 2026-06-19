# A13 错报底稿套件（子 spec）

> **父 spec**：[a7-a15-completion-workpapers](../a7-a15-completion-workpapers/requirements.md)  
> **公共依赖**：[completion-phase-infra](../completion-phase-infra/requirements.md)  
> **联动**：[linkage.md](../completion-phase-infra/linkage.md)  
> **audit 权威**：`backend/data/a7_a15_xlsx_audit.json`（X-A13 ✅）

## 范围

单文件 **8 sheet**：底稿目录 / A13 程序表 / A13-1 汇总 / A13-2~5 表单。

| sheet / wp | runtime | 分期 |
|------------|---------|------|
| A13 程序表 | a-program-console（Tab 内） | lite |
| A13-1 | misstatement-summary | lite 验收 / core Tab |
| A13-2~5 | d-form-table | core |

程序表：**5 步 + 13 子项**；**K 列**索引号；seq3→A13-1；3.1→A13-3,A13-5；4/5→A13-4。

## 架构

`wp_code=A13` → **`misstatement-workpaper`** Tab 容器：

```
程序表 | A13-1 汇总 | A13-2 | A13-3 | A13-4 | A13-5
```

路由见父 spec design §Sheet 路由：`navigate('A13', { tab: 'A13-3' })`。

## 下游消费

| 消费方 | 内容 |
|--------|------|
| A16 | `misstatements/for-letter` alert |
| A17 ch07 舞弊 | A13-4 + 摘要 API `misstatement` |
| A18 议题 1 | 手动 chip 引用 |

## 任务

详单：[tasks.md](./tasks.md)（镜像父 spec 编号 13、17–22）。

## 设计

[design.md](./design.md)

## 现状

| 项 | 状态 | 实证 |
|----|------|------|
| audit X-A13 | ✅ | `a7_a15_xlsx_audit.json` |
| A13-1 汇总 | ✅ | `MisstatementSummaryView.vue` Tab 内嵌 |
| Tab 套件 override | ✅ | `_WP_CODE_OVERRIDE["A13"]` → `misstatement-workpaper` |
| A13-2~5 d-form | ✅ | `GtMisstatementWorkpaper.vue` + `A13.yaml` schema + `test_render_config_d_form_table_a14.py` 同类契约 |
| 下游 A16 alert | ✅ | `misstatements/for-letter` + `test_misstatement_for_letter.py` |
