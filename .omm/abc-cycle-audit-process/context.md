# 上下文：A/B/C 循环特有机制

通用机制见 `.omm/d-cycle-sales/context.md` 与 `shared-runtime/`。本文只写 A/B/C 特有部分。

## 1. 大量走 `a-program-console`（程序表控制台）

A1/A2/A3 dashboard 及各程序表（xxxA）走 `render_a_program`，前端 `GtAProgramConsole`：
程序清单（seq/content/ref_index/auto_data_source/applicable_default）+ 类别筛选（常规★/IPO加项/备选/舞弊应对）
+ 多选批量裁剪 + `auto_data_source` 自动取数（resolver）+ `@jump-to-workpaper`。
程序表模板在 `procedure_table_templates.json`（A/B/C1/D/E/F/K 有 JSON，其余 render 时从源 xlsx `extract_program_rows` 兜底）。

## 2. B22B/B22C/B23 是整册纯前端专属组件（易被 grid shadow）

`b22a-control-matrix` / `b22b-control-matrix` / `b22c-design-effectiveness` / `b23-process-control` / `b19-bundle` /
`b50-risk-assessment` / `b1-risk-assessment` / `b60-strategy` 都是**整册纯前端聚合组件**，render 策略返回
`{component_type, project_context}` **无 cells**——若 render 输出 cells 会触发 `noRendererGridFallback`
被 GtGridSheet shadow（B19/B22/B23/B50/B60 都踩过，注册到 `_SELF_CONTAINED_DEDICATED` 折叠为单 sheet + 清空 html_data）。

## 3. 风险导向链的数据流

- **B50 风险评估**是源头：Tab3 计划矩阵（科目 × 认定 × 综合风险）+ CAS 应对方案（综合性/实质性），
  循环码 → D~N 程序；风险因素接收 B22（控制风险）/ B2（前任）/ B23（业务层）/ B1（承接）的推送
- **B60 总体策略**的 Table26 认定层次应对（底稿索引 / 综合性or实质性 / 循环代码 / 程序底稿索引 / **B50 行号**）
  是"风险 → 循环 → 程序"的路由表，接 `b50_risk_reader` 单一真源
- **A13 未更正错报**是各底稿 `a13:push-misstatement` 的**唯一全局消费者**（`useA13MisstatementBridge` 挂 WorkpaperEditor Shell）

## 4. A9 缺陷函读 B22B/B22C

`_a91_deficiency_letter` / `_a92`（管理层 / 治理层缺陷函）从 B22C（缺陷严重程度评价）读缺陷分组
（`_load_b22c_deficiencies` + 旧格式兼容 `_load_b22b_deficiencies`）。
**平台级坑**：多个跨底稿 loader 曾写 `JOIN working_papers`（复数，真实表 `working_paper` 单数）→ 查询恒抛错被静默吞
（A9/A27-1/A12-1/A10-1 都中招，已修）。

## 5. B19 关联方是全平台关联方唯一真源

`b19-bundle` 的结构化清单直连 eqcr `related-party-transactions` / `related-parties` CRUD →
写入 `related_party_registry`（D1/D2/D5/D6/D7/E1/F1/F2/F4/F5/G1/H1/H2/K1 等十几个 render 策略据此做关联方完整性核对）。
**列名真源**：`name` / `relation_type` / `is_controlled_by_same_party`（消费者曾用 `party_name`/`relationship_type` 撞列名恒空，已修）。

## 6. B1/B22/B23/B50/B60 双模式与目录

这些整册组件已补 OnlyOffice 双模式（`useWorkpaperEntryDualMode` / `useB60DualMode`，切 OO 前预拉 config「拉取成功才切」）
+ 底稿目录（GtBArchitectureTree 4 阶段泳道 或 GtBIndex）。程序表控制台类不参与双模式。

## 7. B1/B2/B60 子底稿结构化 + 手册

B1（7 sheet 承接决策链）、B2（前任沟通流程台账 + 适用性裁剪）、B60（38 表 + 8 子底稿结构化 subSheetSchemas）
都做了源模板结构化重建 + `handbooks/` + 承接决策看板/流程总览。
