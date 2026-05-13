# 业务流程端到端联调 — 技术设计文档

> 版本：v1.0
> 日期：2026-05-13
> 对应需求：requirements.md F1-F15

---

## D1 试算表 recalc HTTP 500 修复（F1）

### 现状

`full_recalc` 直接 Python 调用成功，HTTP 层 500 是 uvicorn `--reload` 模式下 auto-match 写入大量 ORM 对象触发 `.pyc` 文件变化 → worker 重启 → 正在执行的请求被杀。

### 设计决策

**方案 A（推荐）**：`start-dev.bat` 中 uvicorn 加 `--reload-exclude "*.pyc" --reload-exclude "__pycache__"`

**方案 B（备选）**：前端 `onRecalc` 加 retry 逻辑（已有 http.ts 5xx 重试，但 recalc 可能超过默认超时）

### 改动文件

| 文件 | 改动 |
|------|------|
| start-dev.bat | uvicorn 命令加 --reload-exclude |

---

## D2 报表生成前置检查 + 公式填充（F3, F14, F15）

### 现状

- `ReportEngine.generate_all_reports()` 从 `report_config` 读取 formula 字段执行公式
- **report_config 表中 1191 行的 formula 字段全部为 NULL**（seed 加载时未填充公式）
- `multi_standard_report_formats.json` 中有完整的 TB()/ROW()/SUM_TB() 公式（CAS 标准）
- `report_excel_formulas.json` 中有 Excel 行间计算公式（小计/合计行）
- `soe_listed_mapping_preset.json` 中有国企版→上市版行次名称映射

### 设计决策

**核心任务**：为 report_config 表的每一行填充 formula 字段。数据来源：
1. `multi_standard_report_formats.json` 的 CAS.BS/IS/CFS 公式（按 row_code 匹配）
2. `wp_account_mapping.json` 的 report_row → account_codes 映射（补充未覆盖的行）
3. `report_excel_formulas.json` 的行间计算公式（ROW() 合计行）

**国企版/上市版处理**：
- 国企版（soe_consolidated/soe_standalone）：行次多（129 行），含△/▲特殊行业行
- 上市版（listed_consolidated/listed_standalone）：行次少（88 行），标准 A 股格式
- 两版共享同一套标准科目编码，公式逻辑相同，只是行次结构不同
- `soe_listed_mapping_preset.json` 提供行次名称对照关系

**实现方案**：新建 `scripts/fill_report_formulas.py` 脚本：
1. 读取 `multi_standard_report_formats.json` 的 CAS 公式
2. 按 row_name 模糊匹配 report_config 中的行
3. 匹配成功的写入 formula 字段
4. 未匹配的合计行从 `report_excel_formulas.json` 提取 ROW() 公式
5. 支持 `--standard soe|listed` 参数分别处理两版

### 改动文件

| 文件 | 改动 |
|------|------|
| scripts/fill_report_formulas.py | 新建（一次性脚本，填充后可删） |
| backend/app/routers/report_config.py | seed 端点增加 formula 填充逻辑 |

---

## D3 底稿生成流程（F6-F8）

### 现状

`generate_project_workpapers` 函数存在于 `template_engine.py`，从 `gt_template_library.json` 的模板集生成底稿。需要：
1. 项目已选择模板集（`project_template_selections` 表）
2. 模板集中有模板文件路径

### 设计决策

在试算表页面的"下一步"引导中加"生成底稿"按钮：
1. 检查项目是否已选择模板集 → 未选则弹窗让用户选择
2. 调用 `POST /api/projects/{pid}/working-papers/generate-from-codes` 生成底稿
3. 底稿生成后自动建立 wp_mapping（从 `wp_account_mapping.json` 读取）

### 改动文件

| 文件 | 改动 |
|------|------|
| 前端 TrialBalance.vue 或 ReportView.vue | 加"生成底稿"引导按钮 |
| backend/app/services/template_engine.py | 确认 generate 逻辑正确 |

---

## D4 附注生成流程（F9-F11）

### 现状

`DisclosureEngine.generate_notes()` 从模板（`note_template_soe.json` / `note_template_listed.json`）生成附注章节。每个章节有 `table_data` 和 `text_content`。

表格自动取数依赖 `note_wp_mapping_rules.json`（附注章节 → 科目编码 → 取数公式）。

### 设计决策

1. 附注生成入口放在 ReportView 的"下一步"引导中
2. 生成时自动从试算表审定数填充表格的"本期金额"列
3. 前端 DisclosureEditor 已有完整 UI，只需确保后端返回正确数据

### 改动文件

| 文件 | 改动 |
|------|------|
| backend/app/services/disclosure_engine.py | 确认 generate_notes 正确读取模板 |
| 前端 ReportView.vue | 加"生成附注"引导按钮 |

---

## D5 流程引导设计（F12）

### 设计决策

在每个环节的页面顶部加一个"流程进度条"组件，显示当前在哪一步：

```
导入 ✓ → 映射 ✓ → 试算表 ✓ → 报表 → 底稿 → 附注
```

每步完成后高亮"下一步"按钮。实现方式：
- 新建 `components/common/WorkflowProgress.vue` 组件
- 在 TrialBalance / ReportView / WorkpaperList / DisclosureEditor 顶部引入
- 进度状态从后端 `/api/projects/{pid}/workflow-status` 端点获取（或前端按数据存在性推断）

### 改动文件

| 文件 | 改动 |
|------|------|
| components/common/WorkflowProgress.vue | 新建 |
| 各视图页面 | 引入 WorkflowProgress |

---

## D6 科目映射独立页面（F13）

### 现状

当前无 `/projects/:id/mapping` 路由。映射数据在 `account_mapping` 表中，有 CRUD API。

### 设计决策

新建 `views/AccountMappingPage.vue`：
- 左侧：客户科目列表（从 account_chart source=client 读取）
- 右侧：对应的标准科目（从 account_mapping 读取）
- 顶部：完成率进度条 + "自动匹配"按钮
- 支持手动拖拽/选择修改映射

### 改动文件

| 文件 | 改动 |
|------|------|
| views/AccountMappingPage.vue | 新建 |
| router/index.ts | 新增路由 |

---

## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| report_line_mapping 缺失导致报表全 0 | 高 | D2 前置检查自动加载 |
| 底稿模板文件路径不存在 | 中 | 生成时只建元数据不依赖物理文件 |
| 附注取数公式解析失败 | 中 | 降级为空值，不阻断生成 |
| uvicorn --reload 杀 worker | 低 | D1 加 exclude 解决 |
