# 约束（J 循环）

平台通用铁律见 `.omm/d-cycle-sales/constraint.md`。以下为 J 循环附加约束。

1. **循环 IE 的 `sheet` / `sheet_type` 必须走 `params`**（后端是 `Query` 不是 Form），
   且该 sheet 必须已在后端 `SHEET_TYPES` / `_SPECS` 注册，否则导入会按默认值解析进错表。
2. **后端直接 `INSERT checklist_responses` 必须带 `project_id`**（NOT NULL；
   `ON CONFLICT DO UPDATE` 也会先校验 NOT NULL → 漏了恒 500）。
3. **`import http from '@/utils/http'`**（default-only 导出），禁 `import { http }`（运行时 ESM 崩，静态检查查不出）。
4. **注释里禁出现 `*/` 组合**（如 `unadjVsPrior*/auditedVsPrior*`）→ 提前闭合块注释，只有 Vite transform 暴露。
5. **AI `context` 必须是 `dict[str,str]`**（值全转字符串），走 `POST /api/workpapers/{wp_id}/ai/generate-text`；
   禁 `JSON.stringify(context)`（后端类型是 dict → 422）。
6. **审定表「上期审定数」= 本表「期初审定数」**，不引第二数据源；变动列字段名必须与模板消费端一致。
7. **分配/归属类取数不臆造**：对方科目缺失的金额进 `unattributedAmount` 如实提示，不强行分摊。
8. **J2 六要素表按 variant 用各自结构**（上市 3 张独立表 / 国企 1 张合并表），
   计划资产不适用单元格显 "—" 不填 0，期末 = 期初 + 损益 + OCI **−** 其他变动。
9. **审计结论不提供 A/B/C 套用模板按钮**（直接输入或 AI）；多 section 底稿每个文本区都要有 AI 辅助。
10. **宽表（>10 列）录入用引导式弹窗**（分组卡片 + 点点点 + 实时分析面板 + 确认回写），
    主表退化为只读/矩阵视图；批量场景保留完整表格 + 导入导出两条路并存。
11. **目录跳转三条链按各自机制接**（J1 `provide('jumpToSection')` / J2 主入口必须 provide / J3 `@navigate-sheet` emit）。
