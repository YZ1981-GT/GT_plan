# A18 监管沟通函结构化底稿

## 背景

A18-1（向监管部门报送审计小结的函）和 A18-2（与监管层沟通函）是审计完成阶段向证监会/银保监等监管机构提交的正式文件。

| 底稿 | 格式 | 模式 |
|------|------|------|
| A18 程序表 | xlsx | a-program-console（JSON ✅ 2 步） |
| A18-1 审计小结函 | docx | WpPopupDocxEditor 弹窗 |
| A18-2 与监管层沟通函 | docx | 结构化 HTML `regulatory-letter` + export-word |

**相关 spec**：

- [completion-phase-infra](../completion-phase-infra/requirements.md) — PRE-1~3、PRE-2、issue_tickets
- [linkage.md](../completion-phase-infra/linkage.md) — A8/A17 联动、全局排期

## 前置依赖

> **权威定义**：[completion-phase-infra](../completion-phase-infra/requirements.md)

| 依赖 | 阻塞范围 |
|------|----------|
| PRE-1/3 | A18-1 弹窗下载 |
| PRE-2 | A18-P1（= **core**）Word 导出 |
| A17-core | A18-P2 审计小结生成 | ✅ `a18_summary_generator` + generate-summary API |

## 分期对照

| 本 spec | 等价 | 范围 | DoD |
|---------|------|------|-----|
| **A18-P0** | **lite** | 程序表 + A18-2 表单 + 保存 | 填 4 议题→刷新不丢；A18-1 弹窗下载 |
| **A18-P1** | **core** | Word 导出 + issue/A8 提示 | 导出无 XX；不适用议题已删 |
| **A18-P2** | **plus** | A18-1 小结生成 + E2E | ✅ 生成 API + 弹窗 UI |

## 适用条件

- 程序表 `applicable_categories: ["A", "B"]`（与 [infra 统一口径](../completion-phase-infra/requirements.md#适用性统一口径) 一致）
- ⚠️ 不用 `template_type == 'listed'`

## 模板颜色语义

与 [infra PRE-2](../completion-phase-infra/requirements.md#pre-2docx_template_fillerpyword-导出引擎) 一致。

---

## 需求

### A18 程序表

- ✅ `procedure_table_templates.json` **A18** 2 步（seq2 ref A18-1,A18-2）

### A18-1 — 弹窗模式

- 配置已在 `wpPopupDocxConfigs.ts`（PRE-1 后验证）
- 自动填充：公司名、审计年度、监管局名称、合伙人姓名
- **P2/plus 增强**：从 A17-1 章节 + 审计意见 + KAM 生成审计小结框架（A17-core ✅；编排服务待建）

### A18-2 — 结构化表单

- componentType = `regulatory-letter`
- 4 议题卡片：舞弊 / 重大违法 / 年报信息（三选一 radio）/ 其他
- 提示栏（折叠，不导出）；与 A17-1 共用「结构化函件编辑」抽象（见 A17 design）
- 数据：`checklist_responses`（item_id 见 [persistence.md](../completion-phase-infra/persistence.md)）

### Word 导出

- 调用 PRE-2 + `regulatory_letter_service.py`
- 端点：`.../export-word` + `.../export-word/check-incomplete`（见 infra）

### 联动

| 阶段 | 方式 | 详情 |
|------|------|------|
| P0/lite | 手动 GtIndexChip | — |
| P1/core | issue_hints + A8 step status 建议 | [linkage.md](../completion-phase-infra/linkage.md) |
| P2/plus | A18-1 ← A17-1 | A17-core ✅；生成待做 |

issue_tickets：**禁止** `category='fraud'`（见 infra）。

## 关联模块

- A13 / A14（舞弊线索，手动引用）
- A8 其他信息（议题 3 建议值）
- A17 重大事项概要（A18-1 P2 来源）

---

## 现状与差距

> **2026-06-18 codegraph 实证**：P0+P1 闭合；P2 仅剩 A18-1 小结生成。

| 能力 | 目标 | 代码现状 | 分期 |
|------|------|----------|------|
| A18 程序表 JSON | 2 步 | ✅ `procedure_table_templates.json` A18 | P0/lite |
| A18-1 弹窗 | prefilled-download | ✅ 配置 + E13 spec | P0/lite |
| GtRegulatoryLetter | regulatory-letter | ✅ 4 议题 + debounce 保存 | P0/lite |
| export-word | PRE-2 + service | ✅ `regulatory_letter_service.py` + E14 spec | P1/core |
| A8 step 建议 UI | issue_hints 消费 | ❌ guidance 待接 | P1/core |
| A18-1 小结生成 | A17 章节编排 | ✅ API + 弹窗 + prefilled-download 注入 A17 正文 | P2/plus |
| E2E | E13 + E14 | ✅ `e2e/a18-regulatory.spec.ts` | P0/P1 |
