# 约束（L 循环）

平台通用铁律见 `.omm/d-cycle-sales/constraint.md`。以下为 L 循环附加约束。

1. **审定表 X-1 双期结构**：源模板有"期初数/期末数各(未审/账项调整/重分类/审定)"即双期，禁用单期 roll-forward；
   带一年内到期的（L3/L4/L5）加"减一年内到期 → 披露审定数"列（披露审定 = 审定 − 一年内到期）。
2. **审定表必须 hydrate + update 必须 persist**：从 allResponses 同步 + async watch 二次（一次性 guard，
   L5-1 用 `_hydratedOnce` 而非 length===0）；save 用 `JSON.stringify(整行)` 不挑字段（防 lossy）。
3. **动态行表 rows = JSON-array 存单键**（`L{n}-L{n}-{sheet}-rows`）+ hydrate，禁 flat per-field keys + 无 hydration；
   内部↔后端字段用 toBackend/fromBackend 映射保模板零改。
4. **多消费者共读的键必须与 writer 一致**（明细 hydrate / 附注聚合 / 审定带入 / 交叉验证四方读同一 JSON 键）。
5. **交叉验证读计算列须现算**（endBalance 是 computed 不落库），consumer 直接读会恒 0；总额键命名要与 writer 对齐。
6. **检查表对照源模板判类型**：凭证级 → useL{n}VoucherCheck（记账凭证行 + 核对①~⑤ + 检查比例来自明细本期发生额），
   非合规 radio 清单。
7. **导入导出 `INSERT checklist_responses` 带 `project_id`**（从 working_paper 反查）；
   `_SHEET_ITEM_ID` = 前端存储键，`_FIELD_MAPS`/`_NUMERIC_FIELDS` 与前端字段一致。
8. **利息测算 365 天制**（本金×利率×天数/365）联动 L2/L8；资本化部分进 H2（CAS17）。
9. **一年内到期重分类**（RJE）：L3/L4/L5 一年内到期 → 流动列报；逾期银承 → L1 2001。
10. **报告期用 props.year**，不硬编码 `new Date()`。
11. **整册 inject 共享 formData 时父入口必须 provide**（L3 曾漏 provide 致整册崩，Playwright 才能抓）。
12. **带入调整双期审定表 target 期末列**（endAje/endRje），负债贷方 direction=credit（净额=贷−借）。
