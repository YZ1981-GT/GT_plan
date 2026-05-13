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

## D2 报表生成前置检查（F3, F14, F15）

### 现状

`ReportEngine.generate_all_reports()` 需要：
1. `trial_balance` 表有数据（recalc 后产出）
2. `report_config` 表有对应 `applicable_standard` 的行次配置（seed 已加载）
3. `report_line_mapping` 表有行次→科目映射（**可能缺失**）

### 设计决策

在 `generate_all_reports()` 开头加前置检查：
1. 检查 trial_balance 是否有数据 → 无则提示"请先重算试算表"
2. 检查 report_config 是否有对应标准的配置 → 无则自动从 seed 加载
3. 检查 report_line_mapping 是否有数据 → 无则从 `soe_listed_mapping_preset.json` 自动加载

### 改动文件

| 文件 | 改动 |
|------|------|
| backend/app/services/report_engine.py | generate_all_reports 加前置检查 |
| backend/app/services/report_line_mapping_service.py | 新增 auto_load_from_preset() |

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
