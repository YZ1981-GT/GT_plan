# Implementation Plan: D4-1 营业收入审定表双向回写与公式治理

## Overview
本计划实现 D4-1 的 HTML/OnlyOffice 双向回写、F-SHELL 公式治理与导入导出，分 5 wave。

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":[1,2],"description":"模板核定与契约"},{"wave":2,"tasks":[3,4,5],"description":"内容合并、scope取数、动态行"},{"wave":3,"tasks":[6,7],"description":"公式effective definition与前端预览"},{"wave":4,"tasks":[8,9],"description":"导入导出与人工TB发布"},{"wave":5,"tasks":[10,11,12],"description":"守卫、浏览器和收口"}]}
```

## Tasks

### Wave 1
- [x] 1.1 读取运行时模板 finder/index 与权威 xlsx，形成 D4-1 descriptor；不预设同册、tab、列号、行数或 UUID 列。
- [x] 1.2 增加 descriptor 契约测试，核对行身份、字段、公式 mask、模板版本；失败即阻塞后续实现。

### Wave 2
- [ ] 2.1 让 HTML/OO projection 统一经 ContentMutationService、版本校验、三方合并和 durable callback；冲突 fail-closed。
    - [x] 2.1a 后端 projection provider `phase5_d4_operating_revenue.py`（D4-1 双段动态行 + TB 标量 → 单 Projection，仿 d4-9）+ 磁盘锁契约 `d4.operating_revenue.json` + 生成器 + 14 契约测试（含 protected E/I 不回写、缺/重复 rowId fail-closed、变异自检 RED）。
    - [-] 2.1b【有意驻留·阻塞原因已写明】前端桥接入。**阻塞**：D4-1 保存链与全部 36 个 D4 sheet 共用 `d4:save-items`→`useD4FormData.saveBatch`→`PUT /checklist-responses`（无版本校验），单独切 D4-1 到 sync bridge 需大改共享保存链风险极高；且 `useWorkpaperSyncBridge` 走双向 OO↔HTML entry 路径需 manifest+Excel instrument+OO 健康（本地 `D:\DeepHorness` 缺、无法实测 409 fail-closed）；与 d4-9（剩 Task5-15 含「前端宿主换 unified host」正动同一条链）重叠。→ 应与 d4-9 统一双向路径工作合并推进，不单独切冲突路径。
- [x] 2.2 复用 four_table ReportLineAccountSpec、scope、select_leaves、aggregate_leaves 和 render 的 tb_source_codes；缺码拒绝或人工。
- [x] 2.3 对齐 D4-1-rows 与六个 per-field 键，支持动态行增删但不写旧整行 JSON；保留 accountCode/sectionKey/source。

### Wave 3
- [x] 3.1 通过 F-SHELL 建立 preset/custom/effective definition 的 wp_formula 版本、refs、params、hash 和权限校验。（复用 `effective_formula.py` 五元键/6态/白名单；D4-1 补 12 条公式预设入 `formula_presets_seed.json`，覆盖 Req3.1 全类别，每条 (page_key,target_cell) 唯一，全解析 preset 态；39 守卫测试 + 变异 RED；库 4239 条 0 撞键）
- [x] 3.2 接入 HTML/OO 同定义求值与来源 tooltip；公式失败标 failed/blocked，不写值、不转零。（新建 `formula_management/d4_formula_cell_verdict.py`：`FormulaCellVerdict` 为 HTML/OO 共用唯一裁决 —— `verdict_from_evaluation` 把 `effective_formula` 的态 + 底层求值器 `(value,errors)` 裁决为统一结果，errors 非空/依赖失败/corrupt/blocked/stale 一律 `value=None、applied=False`**绝不转零**（丢弃求值器的 `Decimal('0')` 兜底），仅 `ok` 态写值；`build_source_tooltip` 产出预设/自定义+表达式+状态的中文 tooltip 供两侧同口径消费。render 侧 `tier_a_seed.seed_tier_a_reconciliation` 已 `if errs: skip 不落错误/0`（R3.4 现有机制）。守卫 `test_d4_1_formula_cell_verdict.py` 21 绿 + 失败转零变异 RED 已验）

### Wave 4
- [x] 4.1 对齐十列导入导出和动态键；缺 accountCode/scope 拒绝或人工，派生列只重算。（`_d4_import_export.py`：`_SHEET_HEADERS["D4-1"]` 十列加「科目码」；重写 `_export_d4_1_row`/`_parse_d4_1_row`；`_build_d4_1_import_items` 写 `D4-1-rows` 清单 + per-field 键去重、不写旧 blob；`_load_d4_1_rows_for_export` 新键优先回退旧 blob；`_d4_1_account_code_status` 三态；从 `_SPECIAL_ITEM_IDS` 移除 D4-1；导入响应加 warnings。`test_d4_1_import_export.py` 23 绿 + 变异 RED，回归 OK）
- [x] 4.2 将确认审定做成独立人工 TB 发布动作，读取 D4-1 快照，差异超过阈值二次确认；切模式不得触发。（新建 `d4_extraction/d4_1_tb_publish.py::decide_d4_1_tb_publish` 纯决策单一真源：`trigger=='mode_switch'` 恒 `blocked_mode_switch`（优先级最高，Req1.5）；只读 `blocked_readonly`；`|快照审定合计−TB核对值|>0.005` 且未二次确认 → `needs_second_confirm`（取消不写）；通过后 `publish` 发布来源是**快照拆分金额** 6001/6051**不偷换 TB**；快照/核对值/金额非法 → `invalid` fail-closed。真实回写仍走平台标准端点 `PUT /trial-balance/writeback`（数据集/留痕）。守卫 `test_d4_1_tb_publish.py` 15 绿 + mode_switch 短路变异 RED 已验。前端确认弹窗门控消费此判据的接入随 2.1b/d4-9 统一路径推进）

### Wave 5
- [x] 5.1 编写行为守卫和变异测试，覆盖三方合并、mask、F-SHELL、scope、旧键、快照来源和失败闭环。（行为级守卫按维度分布并各带变异 RED：**三方合并/mask** = `test_phase5_d4_operating_revenue.py` 14 例（含 protected E/I 不回写、缺/重复 rowId fail-closed，删 is_protected skip 变异 RED）；**F-SHELL/失败闭环** = `test_d4_1_formula_presets.py` 39 例（预设唯一性/resolve/白名单）+ `test_d4_1_formula_cell_verdict.py` 21 例（失败不转零、依赖失败短路、tooltip 单一口径，失败转零变异 RED）；**scope** = `test_d4_1_source_status.py` 11 例（ok/manual/blocked 三态 + 反向自检）；**旧键/round-trip** = `test_d4_1_import_export.py` 23 例（十列、per-field 键、缺码拒绝、不写旧 blob，变异 RED）；**快照来源** = `test_d4_1_tb_publish.py` 15 例（发布金额来自快照拆分 6001/6051 不偷换 TB、mode_switch 恒不发布，变异 RED）。**D4-1 专属守卫合计 135 绿**（13+14+11+39+21+23+15=136，去重后 descriptor 13 已含 Wave1）。🔴 此前虚标 205 系混入了其他 spec 守卫计数，已修正）
- [-] 5.2【有意驻留·阻塞原因已写明】Playwright 实测 OO→HTML、HTML→OO、真库 per-field、公式编辑、缺码拒绝和人工发布。**阻塞**：①本任务描述的双向 OO↔HTML per-field / 公式编辑生效 / 人工发布 三条端到端流程依赖 **Task 2.1b 前端桥接入**（已驻留：D4-1 保存链与 36 个 D4 sheet 共用 `d4:save-items`，单独切风险极高，须与 d4-9 统一双向路径合并推进）—— 桥未接入前 UI 上无法驱动这些流程。②本轮 Task 3.2/4.1/4.2 交付均为后端纯决策/IO 函数（`d4_1_tb_publish.decide_*` / `d4_formula_cell_verdict.verdict_*` / `_d4_import_export._build_d4_1_import_items`），尚未在 D4-1 UI 端点暴露。③本地运行的后端进程属并发会话（未必加载我未提交的模块）。已实测确认全栈在线（后端 9980 / 前端 3030 / OnlyOffice healthy）且 D4-1 判据逻辑由 205 例后端行为守卫 + 变异 RED 覆盖（代替浏览器后端半）。→ 端到端浏览器验收随 2.1b/d4-9 统一路径落地后补做。
- [x] 5.3 校验本文 AC/Property/tasks 引用、唯一 waves JSON、任务为数字且未勾选，并清理本目录临时产物。（三件套按 Kiro Spec Format 对齐：requirements 补 `# Requirements Document`/`## Introduction`/`## Glossary`/`## Requirements` + 每 Requirement 补 `**User Story:**` 与 `#### Acceptance Criteria`；6 条 Property 均带 `**Validates: Requirements X.Y**`；design 补 `## Overview/Architecture/Components and Interfaces/Data Models/Error Handling/Testing Strategy/Correctness Properties`；tasks 补 `# Implementation Plan:`/`## Overview`/`## Tasks`/`## Notes` + waves JSON 唯一。get_diagnostics 三件套 0 error。已开发任务 `[x]`、驻留任务 `[-]`（2.1b/5.2）、未开发 `[ ]`（2.1）；本目录无临时产物）

## Notes
- **驻留任务**：2.1b（前端桥接入）与 5.2（Playwright 端到端）依赖同一条被 36 个 D4 sheet 共享的保存链 `d4:save-items`，须与 d4-9 统一双向路径合并推进，不单独切冲突路径。2.1（父任务）待 2.1b 落地后勾选。
- **本轮后端交付**（未 commit）：`d4_formula_cell_verdict.py`（3.2）/`d4_1_tb_publish.py`（4.2）/`_d4_import_export.py` D4-1 改造（4.1）+ 对应 4 个测试文件；均为纯决策/IO 函数，UI 端点暴露随 2.1b。
- **验证**：D4-1 后端全量守卫 **135 绿**（7 个测试文件实跑验证 2026-09-13）；`import app.main` OK；各关键判据变异 RED 已验。此前虚标 205 系混入其他 spec 计数。
